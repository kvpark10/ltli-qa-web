"""Shared rule-based QA. No UI, telemetry, translation or model calls."""
import io
import re
from collections import Counter
import pandas as pd

def normalize_text(text):
    if pd.isna(text):
        return ""

    return str(text).strip()

def compare_items(source_items, target_items):
    return Counter(source_items) != Counter(target_items)

def normalize_term(text):
    """용어 비교를 위해 공백과 영문 대소문자를 정규화합니다."""
    if pd.isna(text):
        return ""

    normalized = re.sub(r"\s+", " ", str(text).strip())
    return normalized.casefold()

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

def extract_numbers(text):
    text = normalize_text(text)

    pattern = r"\d+(?:,\d{3})*(?:\.\d+)?"

    return re.findall(pattern, text)

def extract_end_punctuation(text):
    text = normalize_text(text)

    if not text:
        return ""

    match = re.search(r"[.!?:;]+$", text)

    if match:
        return match.group()

    return ""

def extract_tags(text):
    text = normalize_text(text)

    pattern = r"</?[A-Za-z][^>]*?>"

    return re.findall(pattern, text)

def extract_placeholders(text):
    text = normalize_text(text)

    patterns = [
        r"\{[^{}]+\}",          # {0}, {name}
        r"%(?:\d+\$|\([^)]+\))?[-+#0]*\d*(?:\.\d+)?[diuoxXfFeEgGaAcspn@%](?![A-Za-z])",  # %s, %d, %02d
        r"\$\{[^{}]+\}",        # ${name}
        r"\{\{\s*[^{}]+\s*\}\}",  # {{name}}
    ]

    placeholders = []

    for pattern in patterns:
        placeholders.extend(re.findall(pattern, text))

    return placeholders

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

def extract_urls(text):
    text = normalize_text(text)

    pattern = r"https?://[^\s<>\"]+"

    return re.findall(pattern, text)

def extract_emails(text):
    text = normalize_text(text)

    pattern = r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"

    return re.findall(pattern, text)

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

def convert_dataframe_to_excel(dataframe, decisions=None):
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

        if decisions:
            pd.DataFrame([{'Segment':d['id'],'QA Issue':d['issue'],'Decision':'Accepted by user',
                           'Accepted at (UTC)':d['accepted_at'],'Content fingerprint':d['fingerprint']}
                          for d in decisions]).to_excel(writer,index=False,sheet_name='User Decisions')
        pd.DataFrame({'검사 범위 / Scope':[
            '형식·구조 검사 결과입니다. 의미 정확성·문법·자연스러움은 검사하지 않습니다.',
            '경고가 없더라도 번역의 언어적 품질이 검증된 것은 아닙니다. 최종 언어 검수는 별도로 진행해 주세요.',
            '사용자 문제없음 처리는 경고에 대한 사용자 판단이며, 검사 통과나 언어 검수 승인이 아닙니다.',
            'User-accepted warnings reflect user judgment, not automated clearance or linguistic approval.',
            'Checks formatting and structure only. Meaning accuracy, grammar and fluency are not evaluated.',
            'No warnings does not establish linguistic quality. Final linguistic review is still needed.'
        ]}).to_excel(writer,index=False,sheet_name='QA Scope')
        sheet=writer.sheets['QA Scope']
        sheet.column_dimensions['A'].width=105
        from openpyxl.styles import Alignment
        for row in sheet:
            for cell in row: cell.alignment=Alignment(wrap_text=True,vertical='top')
        for index in range(2,8): sheet.row_dimensions[index].height=42

    return output.getvalue()
