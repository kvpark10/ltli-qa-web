import io
import re
from collections import Counter

import pandas as pd
import streamlit as st
from docx import Document


st.set_page_config(
    page_title="LTLI QA",
    page_icon="🔎",
    layout="wide"
)

st.title("🔎 LTLI QA")
st.subheader("Localization Quality Assurance")

st.info(
    "Public Beta · Free translation QA for XLSX, DOCX, and TXT files"
)

st.write(
    """
    Upload one bilingual XLSX file, or upload separate source and target
    DOCX/TXT files.
    """
)

st.warning(
    "For the initial beta, upload public test data only. Do not upload "
    "personal information, customer-confidential files, diplomatic documents, "
    "or unpublished commercial content. Maximum file size: 10 MB."
)

st.caption(
    "Questions or feedback: contact@ltli.kr · Website: https://ltli.kr"
)


# --------------------------------------------------
# 공통 함수
# --------------------------------------------------
def normalize_text(text):
    if pd.isna(text):
        return ""

    return str(text).strip()


def normalize_bilingual_columns(dataframe):
    """Return a copy whose source/target columns use canonical names.

    Column matching ignores case and common separators, so both the legacy
    ``Source``/``Target`` format and files using ``source``/``target`` are
    accepted. Other metadata columns are preserved unchanged.
    """
    normalized_dataframe = dataframe.copy()
    normalized_dataframe.columns = [
        str(column).strip().lstrip("\ufeff")
        for column in normalized_dataframe.columns
    ]

    column_lookup = {}
    for column in normalized_dataframe.columns:
        normalized_name = re.sub(r"[\s_-]+", "", column).casefold()
        column_lookup.setdefault(normalized_name, []).append(column)

    source_columns = column_lookup.get("source", [])
    target_columns = column_lookup.get("target", [])

    if len(source_columns) != 1 or len(target_columns) != 1:
        raise ValueError(
            "The file must contain exactly one Source column and one Target "
            "column. Column names are case-insensitive."
        )

    return normalized_dataframe.rename(
        columns={
            source_columns[0]: "Source",
            target_columns[0]: "Target",
        }
    )


MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024


def validate_file_size(uploaded_file):
    """Reject empty files and files larger than the MVP upload limit."""
    file_size = getattr(uploaded_file, "size", None)

    if file_size == 0:
        raise ValueError(f"{uploaded_file.name} is empty.")

    if file_size is not None and file_size > MAX_FILE_SIZE_BYTES:
        raise ValueError(
            f"{uploaded_file.name} exceeds the 10 MB file-size limit."
        )


def get_file_extension(uploaded_file):
    file_name = uploaded_file.name

    if "." not in file_name:
        return ""

    return file_name.rsplit(".", 1)[-1].lower()


def read_docx_segments(uploaded_file):
    """Read non-empty DOCX paragraphs in document order."""
    validate_file_size(uploaded_file)

    try:
        document = Document(io.BytesIO(uploaded_file.getvalue()))
    except Exception as error:
        raise ValueError(
            f"Failed to read DOCX file {uploaded_file.name}: {error}"
        ) from error

    return [
        paragraph.text.strip()
        for paragraph in document.paragraphs
        if paragraph.text.strip()
    ]


def decode_text_bytes(raw_bytes, file_name):
    """Decode common Korean and Unicode TXT encodings without guessing silently."""
    if raw_bytes.startswith((b"\xff\xfe", b"\xfe\xff")):
        encodings = ("utf-16",)
    else:
        encodings = ("utf-8-sig", "utf-8", "cp949")

    for encoding in encodings:
        try:
            return raw_bytes.decode(encoding), encoding
        except (UnicodeDecodeError, UnicodeError):
            continue

    raise ValueError(
        f"Could not decode {file_name}. Save it as UTF-8, UTF-16, or CP949."
    )


def read_txt_segments(uploaded_file):
    """Read non-empty TXT lines in file order."""
    validate_file_size(uploaded_file)
    decoded_text, encoding = decode_text_bytes(
        uploaded_file.getvalue(),
        uploaded_file.name
    )
    segments = [line.strip() for line in decoded_text.splitlines() if line.strip()]
    return segments, encoding


def build_parallel_dataframe(source_file, target_file):
    """Build Source/Target rows from two structurally matching documents."""
    source_extension = get_file_extension(source_file)
    target_extension = get_file_extension(target_file)

    if source_extension != target_extension:
        raise ValueError(
            "Source and target files must use the same format (DOCX + DOCX or TXT + TXT)."
        )

    metadata = {"format": source_extension.upper()}

    if source_extension == "docx":
        source_segments = read_docx_segments(source_file)
        target_segments = read_docx_segments(target_file)
        metadata["unit"] = "paragraphs"
    elif source_extension == "txt":
        source_segments, source_encoding = read_txt_segments(source_file)
        target_segments, target_encoding = read_txt_segments(target_file)
        metadata.update(
            {
                "unit": "lines",
                "source_encoding": source_encoding,
                "target_encoding": target_encoding,
            }
        )
    else:
        raise ValueError("Only DOCX and TXT file pairs are supported.")

    if not source_segments:
        raise ValueError("No non-empty source segments were found.")

    if not target_segments:
        raise ValueError("No non-empty target segments were found.")

    metadata["source_count"] = len(source_segments)
    metadata["target_count"] = len(target_segments)

    if len(source_segments) != len(target_segments):
        raise ValueError(
            "Document structure mismatch: "
            f"source has {len(source_segments)} {metadata['unit']}, "
            f"but target has {len(target_segments)}. "
            "Align the documents before running QA."
        )

    dataframe = pd.DataFrame(
        {
            "Segment": range(1, len(source_segments) + 1),
            "Source": source_segments,
            "Target": target_segments,
        }
    )
    return dataframe, metadata


def compare_items(source_items, target_items):
    return Counter(source_items) != Counter(target_items)


def normalize_term(text):
    """용어 비교를 위해 공백과 영문 대소문자를 정규화합니다."""
    if pd.isna(text):
        return ""

    normalized = re.sub(r"\s+", " ", str(text).strip())
    return normalized.casefold()


def load_glossary(glossary_file):
    """XLSX/CSV 용어집을 읽고 원문·번역문 열 이름의 표기 차이를 허용합니다."""
    if glossary_file is None:
        return []

    file_name = glossary_file.name.lower()

    try:
        if file_name.endswith(".xlsx"):
            glossary_dataframe = pd.read_excel(glossary_file)
        elif file_name.endswith(".csv"):
            try:
                glossary_dataframe = pd.read_csv(
                    glossary_file,
                    encoding="utf-8-sig"
                )
            except UnicodeDecodeError:
                glossary_file.seek(0)
                glossary_dataframe = pd.read_csv(
                    glossary_file,
                    encoding="cp949"
                )
        else:
            raise ValueError("Glossary file must be XLSX or CSV.")
    except Exception as error:
        raise ValueError(
            f"Failed to read glossary file: {error}"
        ) from error

    glossary_dataframe.columns = [str(column).strip() for column in glossary_dataframe.columns]

    # "Source Term"과 "source_term"처럼 공백·밑줄·대소문자만 다른
    # 열 이름을 동일하게 취급합니다. 기존 회귀 용어집과 일반 운영용
    # 용어집을 모두 지원하기 위한 하위 호환 규칙입니다.
    normalized_columns = {
        re.sub(r"[\s_-]+", "", column).casefold(): column
        for column in glossary_dataframe.columns
    }
    source_column = normalized_columns.get("sourceterm")
    target_column = normalized_columns.get("targetterm")

    if source_column is None or target_column is None:
        raise ValueError(
            "Glossary file must contain source and target term columns. "
            "Supported names: Source Term/Target Term or "
            "source_term/target_term."
        )

    glossary_entries = []

    for _, row in glossary_dataframe.iterrows():
        source_term = normalize_text(row[source_column])
        target_term_text = normalize_text(row[target_column])

        if not source_term or not target_term_text:
            continue

        approved_targets = [
            target.strip()
            for target in target_term_text.split("|")
            if target.strip()
        ]

        if approved_targets:
            glossary_entries.append(
                {
                    "source_term": source_term,
                    "approved_targets": approved_targets
                }
            )

    return glossary_entries


def contains_source_term(source_text, source_term):
    """원문에서 용어를 검색하며 영문 용어에는 단어 경계를 적용합니다."""
    normalized_source = normalize_term(source_text)
    normalized_term = normalize_term(source_term)

    if not normalized_term:
        return False

    is_word_based = bool(
        re.fullmatch(r"[A-Za-z0-9 _.-]+", source_term)
    )

    if is_word_based:
        pattern = (
            r"(?<!\w)"
            + re.escape(normalized_term)
            + r"(?!\w)"
        )
        return bool(re.search(pattern, normalized_source))

    return normalized_term in normalized_source


def contains_approved_target(target_text, approved_targets):
    """번역문에 승인 번역어 중 하나가 포함되어 있는지 확인합니다."""
    normalized_target = normalize_term(target_text)

    return any(
        normalize_term(approved_target) in normalized_target
        for approved_target in approved_targets
        if normalize_term(approved_target)
    )


def check_terminology(source_text, target_text, glossary_entries):
    """원문 용어가 있을 때 승인 번역어 사용 여부를 검사합니다."""
    terminology_issues = []

    for entry in glossary_entries or []:
        source_term = entry["source_term"]
        approved_targets = entry["approved_targets"]

        if not contains_source_term(source_text, source_term):
            continue

        if contains_approved_target(target_text, approved_targets):
            continue

        terminology_issues.append(
            f"{source_term} → {' / '.join(approved_targets)}"
        )

    return terminology_issues


# --------------------------------------------------
# 숫자 검사
# --------------------------------------------------
def extract_numbers(text):
    text = normalize_text(text)

    pattern = r"\d+(?:,\d{3})*(?:\.\d+)?"

    return re.findall(pattern, text)


# --------------------------------------------------
# 문장 끝 구두점 검사
# --------------------------------------------------
def extract_end_punctuation(text):
    text = normalize_text(text)

    if not text:
        return ""

    match = re.search(r"[.!?:;]+$", text)

    if match:
        return match.group()

    return ""


# --------------------------------------------------
# 태그 검사
# --------------------------------------------------
def extract_tags(text):
    text = normalize_text(text)

    pattern = r"</?[A-Za-z][^>]*?>"

    return re.findall(pattern, text)


# --------------------------------------------------
# 자리표시자 검사
# --------------------------------------------------
def extract_placeholders(text):
    text = normalize_text(text)

    patterns = [
        r"\{[^{}]+\}",          # {0}, {name}
        r"%[-+#0 ]*\d*(?:\.\d+)?[a-zA-Z]",  # %s, %d, %02d
        r"\$\{[^{}]+\}",        # ${name}
        r"\{\{\s*[^{}]+\s*\}\}",  # {{name}}
    ]

    placeholders = []

    for pattern in patterns:
        placeholders.extend(re.findall(pattern, text))

    return placeholders


# --------------------------------------------------
# 괄호 검사
# --------------------------------------------------
def extract_brackets(text):
    text = normalize_text(text)

    return re.findall(r"[\(\)\[\]\{\}]", text)


def check_balanced_brackets(text):
    text = normalize_text(text)

    bracket_pairs = {
        ")": "(",
        "]": "[",
        "}": "{"
    }

    opening_brackets = set(bracket_pairs.values())
    closing_brackets = set(bracket_pairs.keys())

    stack = []

    for character in text:
        if character in opening_brackets:
            stack.append(character)

        elif character in closing_brackets:
            if not stack:
                return False

            if stack[-1] != bracket_pairs[character]:
                return False

            stack.pop()

    return len(stack) == 0


# --------------------------------------------------
# URL 검사
# --------------------------------------------------
def extract_urls(text):
    text = normalize_text(text)

    pattern = r"https?://[^\s<>\"]+"

    return re.findall(pattern, text)


# --------------------------------------------------
# 이메일 주소 검사
# --------------------------------------------------
def extract_emails(text):
    text = normalize_text(text)

    pattern = r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"

    return re.findall(pattern, text)


# --------------------------------------------------
# 공백 검사
# --------------------------------------------------
def check_whitespace_issues(text):
    """
    Target 문장 내부의 비정상적인 공백을 검사합니다.

    검사 대상:
    - 문장 앞 공백
    - 문장 뒤 공백
    - 두 칸 이상의 연속 공백
    - 탭 문자
    """
    if pd.isna(text):
        return []

    original_text = str(text)
    issues = []

    if original_text.startswith(" "):
        issues.append("Leading space")

    if original_text.endswith(" "):
        issues.append("Trailing space")

    if re.search(r" {2,}", original_text):
        issues.append("Multiple spaces")

    if "\t" in original_text:
        issues.append("Tab character")

    return issues


# --------------------------------------------------
# 파일명 검사
# --------------------------------------------------
def extract_file_names(text):
    """
    확장자를 포함한 파일명을 추출합니다.

    예:
    config.yaml
    README.md
    install.exe
    archive.tar.gz
    """
    text = normalize_text(text)

    pattern = (
        r"\b"
        r"[A-Za-z0-9_-]+"
        r"(?:\.[A-Za-z0-9_-]+)+"
        r"\b"
    )

    return re.findall(pattern, text)


# --------------------------------------------------
# 키보드 단축키 검사
# --------------------------------------------------
def extract_shortcuts(text):
    """
    키보드 단축키를 추출합니다.

    예:
    Ctrl+C
    Ctrl + C
    Alt+F4
    Shift+Enter
    F5
    """
    text = normalize_text(text)

    pattern = (
        r"\b(?:Ctrl|Alt|Shift|Command|Cmd|Option|Windows|Win)"
        r"\s*\+\s*"
        r"(?:[A-Za-z0-9]+|F\d{1,2})\b"
        r"|"
        r"\bF(?:[1-9]|1[0-2])\b"
    )

    shortcuts = re.findall(
        pattern,
        text,
        flags=re.IGNORECASE
    )

    # Ctrl + C와 Ctrl+C를 동일하게 비교하기 위한 정규화
    normalized_shortcuts = []

    for shortcut in shortcuts:
        normalized = re.sub(
            r"\s+",
            "",
            shortcut
        ).upper()

        normalized_shortcuts.append(normalized)

    return normalized_shortcuts


# --------------------------------------------------
# 단위 검사
# --------------------------------------------------
def extract_units(text):
    if not isinstance(text, str):
        return []

    units = [
        "mm", "cm", "m", "km",
        "mg", "g", "kg",
        "ml", "l",
        "ms", "sec", "second", "seconds",
        "min", "minute", "minutes",
        "hour", "hours",
        "kb", "mb", "gb", "tb",
        "hz", "khz", "mhz", "ghz",
        "v", "w", "kw",
        "%", "°c", "°f"
    ]

    # 정규식 특수문자를 안전하게 처리
    escaped_units = [re.escape(unit) for unit in units]

    unit_pattern = (
        r"\b\d+(?:[.,]\d+)?\s*(?:"
        + "|".join(escaped_units)
        + r")\b"
    )

    return re.findall(
        unit_pattern,
        text,
        flags=re.IGNORECASE
    )


# --------------------------------------------------
# QA 규칙
# --------------------------------------------------
def run_qa_check(source, target, glossary_entries=None):
    if glossary_entries is None:
        glossary_entries = []

    source_text = normalize_text(source)
    target_text = normalize_text(target)

    issues = []

    # 번역 누락
    if not target_text:
        issues.append("Missing translation")
        return issues

    # 원문과 번역문 동일
    if source_text == target_text:
        issues.append(
            "Source and target are identical"
        )

    # 숫자
    if compare_items(
        extract_numbers(source_text),
        extract_numbers(target_text)
    ):
        issues.append("Number mismatch")

    # 문장 끝 구두점
    if (
        extract_end_punctuation(source_text)
        != extract_end_punctuation(target_text)
    ):
        issues.append("Punctuation mismatch")

    # HTML/XML 태그
    if compare_items(
        extract_tags(source_text),
        extract_tags(target_text)
    ):
        issues.append("Tag mismatch")

    # 자리표시자
    if compare_items(
        extract_placeholders(source_text),
        extract_placeholders(target_text)
    ):
        issues.append("Placeholder mismatch")

    # 괄호 문자
    if compare_items(
        extract_brackets(source_text),
        extract_brackets(target_text)
    ):
        issues.append("Bracket mismatch")

    # Target 내부 괄호 균형
    if not check_balanced_brackets(target_text):
        issues.append(
            "Unbalanced target brackets"
        )

    # URL
    if compare_items(
        extract_urls(source_text),
        extract_urls(target_text)
    ):
        issues.append("URL mismatch")

    # 이메일
    if compare_items(
        extract_emails(source_text),
        extract_emails(target_text)
    ):
        issues.append("Email mismatch")

    # 공백
    whitespace_issues = check_whitespace_issues(
        target
    )

    if whitespace_issues:
        issues.append(
            "Whitespace warning: "
            + ", ".join(whitespace_issues)
        )

    # 파일명
    if compare_items(
        extract_file_names(source_text),
        extract_file_names(target_text)
    ):
        issues.append("File name mismatch")

    # 키보드 단축키
    if compare_items(
        extract_shortcuts(source_text),
        extract_shortcuts(target_text)
    ):
        issues.append("Shortcut mismatch")

    # 단위
    if compare_items(
        extract_units(source_text),
        extract_units(target_text)
    ):
        issues.append("Unit mismatch")

    # 용어집 기반 Terminology QA
    terminology_issues = check_terminology(
        source_text,
        target_text,
        glossary_entries
    )

    for terminology_issue in terminology_issues:
        issues.append(
            "Terminology mismatch: "
            + terminology_issue
        )

    return issues


def convert_dataframe_to_excel(dataframe):
    output = io.BytesIO()

    # Prevent uploaded text from being interpreted as a spreadsheet formula
    # when a user opens the downloaded QA report.
    safe_dataframe = dataframe.map(
        lambda value: "'" + value
        if isinstance(value, str) and value.startswith(("=", "+", "-", "@"))
        else value
    )

    with pd.ExcelWriter(
        output,
        engine="openpyxl"
    ) as writer:
        safe_dataframe.to_excel(
            writer,
            index=False,
            sheet_name="QA Results"
        )

    return output.getvalue()


# --------------------------------------------------
# 파일 업로드
# --------------------------------------------------
input_mode = st.radio(
    "Input method",
    options=["Bilingual XLSX", "Separate source and target files"],
    horizontal=True,
)

uploaded_file = None
source_file = None
target_file = None

if input_mode == "Bilingual XLSX":
    uploaded_file = st.file_uploader(
        "Choose a bilingual XLSX file",
        type=["xlsx"],
        help="Required columns: Source and Target",
    )
else:
    source_column, target_column = st.columns(2)

    with source_column:
        source_file = st.file_uploader(
            "Upload source file",
            type=["docx", "txt"],
            key="source_document_uploader",
        )

    with target_column:
        target_file = st.file_uploader(
            "Upload target file",
            type=["docx", "txt"],
            key="target_document_uploader",
        )

    st.caption(
        "DOCX files are aligned by non-empty paragraph; TXT files are aligned "
        "by non-empty line. Both files must contain the same number of units."
    )

glossary_file = st.file_uploader(
    "Upload terminology glossary (optional)",
    type=["csv", "xlsx"],
    key="glossary_uploader",
    help=(
        "Required columns: Source Term/Target Term or "
        "source_term/target_term"
    )
)

glossary_entries = []

if glossary_file is not None:
    try:
        glossary_entries = load_glossary(glossary_file)
        st.success(
            f"Loaded {len(glossary_entries)} glossary entries."
        )
    except ValueError as error:
        st.error(str(error))
        st.stop()


alignment_metadata = None

if input_mode == "Bilingual XLSX":
    if uploaded_file is None:
        st.info("Please upload a bilingual XLSX file.")
        st.stop()

    try:
        validate_file_size(uploaded_file)
        dataframe = pd.read_excel(uploaded_file)
    except Exception as error:
        st.error(f"Failed to read the file: {error}")
        st.stop()

    st.success(f"Uploaded: {uploaded_file.name}")
else:
    if source_file is None or target_file is None:
        st.info("Please upload both the source file and the target file.")
        st.stop()

    try:
        dataframe, alignment_metadata = build_parallel_dataframe(
            source_file,
            target_file,
        )
    except ValueError as error:
        st.error(str(error))
        st.stop()

    st.success(
        f"Aligned {alignment_metadata['source_count']} "
        f"{alignment_metadata['unit']}."
    )

    metric1, metric2, metric3 = st.columns(3)
    metric1.metric("Format", alignment_metadata["format"])
    metric2.metric("Source units", alignment_metadata["source_count"])
    metric3.metric("Target units", alignment_metadata["target_count"])


# --------------------------------------------------
# 열 확인 및 표준화
# --------------------------------------------------
try:
    dataframe = normalize_bilingual_columns(dataframe)
except ValueError as error:
    st.error(
        str(error)
    )

    st.write("Current columns:")
    st.write(list(dataframe.columns))

    st.stop()


# --------------------------------------------------
# 파일 미리보기
# --------------------------------------------------
st.subheader("File Preview")

st.dataframe(
    dataframe,
    use_container_width=True,
    hide_index=True
)

st.divider()


# --------------------------------------------------
# QA 실행
# --------------------------------------------------
if st.button("Run QA", type="primary"):
    result_dataframe = dataframe.copy()

    result_dataframe["QA Issues"] = (
        result_dataframe.apply(
            lambda row: run_qa_check(
                row["Source"],
                row["Target"],
                glossary_entries
            ),
            axis=1
        )
    )

    result_dataframe["QA Result"] = (
        result_dataframe["QA Issues"].apply(
            lambda issues: "Pass"
            if not issues
            else "Error"
        )
    )

    result_dataframe["QA Issues"] = (
        result_dataframe["QA Issues"].apply(
            lambda issues: ", ".join(issues)
        )
    )

    error_dataframe = result_dataframe[
        result_dataframe["QA Result"] == "Error"
    ].copy()

    total_segments = len(result_dataframe)
    error_count = len(error_dataframe)
    pass_count = total_segments - error_count

    pass_rate = (
        pass_count / total_segments * 100
        if total_segments > 0
        else 0
    )

    # --------------------------------------------------
    # 요약
    # --------------------------------------------------
    st.subheader("QA Summary")

    column1, column2, column3, column4 = st.columns(4)

    column1.metric("Total Segments", total_segments)
    column2.metric("Passed", pass_count)
    column3.metric("Errors", error_count)
    column4.metric("Pass Rate", f"{pass_rate:.1f}%")

    # --------------------------------------------------
    # 오류 유형별 집계
    # --------------------------------------------------
    issue_types = [
    "Missing translation",
    "Source and target are identical",
    "Number mismatch",
    "Punctuation mismatch",
    "Tag mismatch",
    "Placeholder mismatch",
    "Bracket mismatch",
    "Unbalanced target brackets",
    "URL mismatch",
    "Email mismatch",
    "Whitespace warning",
    "File name mismatch",
    "Shortcut mismatch",
    "Unit mismatch",
    "Terminology mismatch"
    ]

    issue_summary = pd.DataFrame(
        {
            "Issue Type": issue_types,
            "Count": [
                result_dataframe["QA Issues"]
                .str.contains(
                    issue,
                    regex=False
                )
                .sum()
                for issue in issue_types
            ]
        }
    )

    st.subheader("Issue Summary")

    st.dataframe(
        issue_summary,
        use_container_width=True,
        hide_index=True
    )

    # --------------------------------------------------
    # 전체 결과
    # --------------------------------------------------
    st.subheader("QA Results")

    st.dataframe(
        result_dataframe,
        use_container_width=True,
        hide_index=True
    )

    # --------------------------------------------------
    # 오류 결과
    # --------------------------------------------------
    if error_count > 0:
        st.error(
            f"{error_count} segment(s) contain QA issues."
        )

        st.subheader("Errors Only")

        st.dataframe(
            error_dataframe,
            use_container_width=True,
            hide_index=True
        )

    else:
        st.success("No QA issues were found.")

    # --------------------------------------------------
    # 다운로드
    # --------------------------------------------------
    excel_data = convert_dataframe_to_excel(
        result_dataframe
    )

    st.download_button(
        label="Download QA Results",
        data=excel_data,
        file_name="ltli_qa_results.xlsx",
        mime=(
            "application/vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet"
        )
    )
