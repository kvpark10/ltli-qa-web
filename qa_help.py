"""Contextual QA help. Keep operational guidance separate from rule logic."""
HELP = {
    'xlsx': ('원문과 번역문이 같은 XLSX 파일에 있어야 합니다. Source와 Target 열을 각각 하나씩 만들고 같은 행끼리 대응시키세요. 최대 10MB입니다.', 'Use one XLSX file containing exactly one Source and one Target column, with matching texts on the same row. Maximum 10 MB.'),
    'source': ('번역 전 원문 DOCX 또는 TXT 파일입니다. 번역문과 같은 형식을 사용하세요. DOCX는 비어 있지 않은 문단, TXT는 비어 있지 않은 줄끼리 순서대로 비교합니다.', 'Original DOCX or TXT file. Use the same type as the translation. Non-empty DOCX paragraphs or non-empty TXT lines are paired in order.'),
    'target': ('검사할 번역문 파일입니다. 원문과 비어 있지 않은 문단/줄의 수와 순서를 맞추세요. 개수가 같아도 내용의 대응이 정확한지는 미리보기에서 확인해야 합니다.', 'Translation to check. Match the source count and order of non-empty paragraphs/lines. Equal counts do not guarantee correct pairing; inspect the preview.'),
    'run': ('현재 업로드한 파일로 QA를 실행합니다. 번역을 생성하거나 원문/번역문을 수정하지 않습니다. 파일을 바꾸면 다시 실행하세요.', 'Run QA on the current files. Does not generate translations or edit your text. Rerun after changing files.'),
    'report': ('전체 세그먼트와 QA 결과를 Excel로 받습니다. 원문·번역문도 포함되므로 공유 전에 확인하세요. 다운로드가 원본 파일을 수정하지는 않습니다.', 'Download all segments and QA results as Excel. Contains source and target text; check before sharing. Does not modify the original files.'),
    'sample': ('가상의 데이터와 의도된 문제를 포함한 테스트 파일입니다. Excel은 하나, Word는 원문/번역문 두 파일을 받으세요. 다운로드만으로 QA는 실행되지 않습니다.', 'Fictional test data with intentional issues. Download one Excel file or both Word files. Downloading alone does not run QA.'),
    'template': ('직접 입력할 빈 양식입니다. Excel에는 Source/Target 열을 사용하고 Word는 원문/번역문 문단의 수와 순서를 맞추세요.', 'Blank templates for your own content. Use Source/Target columns in Excel, or aligned source/target paragraph counts and order in Word.'),
    'total': ('현재 QA 실행 결과의 전체 문구 수입니다. DOCX/TXT에서는 정렬된 비어 있지 않은 문단/줄을 세그먼트로 계산합니다.', 'Total segments in this QA run. DOCX/TXT segments are paired non-empty paragraphs/lines.'),
    'passed': ('현재 자동 검사에서 문제가 검출되지 않은 문구 수입니다. 번역 의미의 정확성이나 인간 언어 검수 승인을 뜻하지 않습니다.', 'Segments with no detected QA issues. Does not establish semantic accuracy or human approval.'),
    'issues': ('문제가 하나 이상 검출된 문구 수입니다. 한 문구에 여러 문제가 있어도 이 수치는 1개로 계산합니다. 의도된 표현일 수 있으므로 언어 검수하세요.', 'Segments with one or more detected issues. Each segment counts once even with multiple issues. Review findings; some may be intentional.'),
    'rate': ('자동 검사 통과 문구 수 ÷ 전체 문구 수 × 100입니다. 의미 품질 점수나 번역 정확도가 아닙니다.', 'Segments passing automated checks ÷ all segments × 100. Not a translation accuracy or semantic quality score.'),
}
GUIDE = {
    'ko': ('사용 방법', [
        '1. 이중언어 XLSX 1개 또는 같은 형식의 원문·번역문 DOCX/TXT 파일 쌍을 준비합니다.',
        '2. 파일을 업로드합니다.',
        '3. 미리보기에서 같은 행의 원문·번역문이 정확히 대응하는지 확인합니다.',
        '4. QA 검사 실행을 누르고 검토가 필요한 문구와 문제 유형을 확인합니다.',
        '5. 수정은 원본 파일에서 진행하고 다시 업로드하여 QA를 재실행합니다. 화면에서 직접 편집하는 도구는 아닙니다.',
        '6. Excel 보고서를 다운로드합니다. 자동 검사 통과와 인간 최종 언어 검수는 별개입니다.',
    ]),
    'en': ('How to use', [
        '1. Prepare one bilingual XLSX or a same-format source/target pair of DOCX or TXT files.',
        '2. Upload the files.',
        '3. Inspect the preview to confirm source and translation correspond on each row.',
        '4. Run QA and review flagged segments and issue types.',
        '5. Edit your original files, reupload, then rerun QA. This screen is not a text editor.',
        '6. Download the Excel report. Passing automated checks is separate from final human linguistic review.',
    ])
}
NOTICES = {
    'alignment': ('미리보기에서 원문·번역문의 대응을 확인하세요. XLSX와 파일 쌍을 동시에 올리면 XLSX가 우선되므로 다른 형식을 쓰려면 XLSX를 지우세요.', 'Inspect source/target alignment in the preview. If XLSX and a file pair are both uploaded, XLSX takes precedence; clear it to use the pair.'),
    'rerun': ('파일을 변경한 경우 반드시 QA를 다시 실행하세요. 버튼을 누르기 전 기존 결과가 표시되어 있으면 이전 실행 결과입니다.', 'Rerun QA after changing any file. Any results shown before you rerun belong to the previous run.'),
    'results': ('통과는 자동 검사에서 문제가 검출되지 않았다는 뜻입니다. 검토 필요가 곧 오역은 아니며, 브랜드명·문체에 따른 의도된 차이일 수 있습니다. QA는 의미 정확성을 보증하지 않습니다.', 'Pass means no automated issue was detected. Flagged text is not necessarily mistranslated; brands or intentional stylistic differences may trigger checks. QA does not guarantee meaning.'),
    'summary': ('문제 유형별 건수는 해당 유형이 검출된 세그먼트 수입니다. 한 세그먼트가 여러 유형에 포함될 수 있으므로 유형별 합계는 검토 필요 문구 수보다 클 수 있습니다.', 'Issue-type counts measure affected segments per type. One segment can appear in multiple types, so their sum may exceed the number of flagged segments.'),
    'download': ('보고서에는 원문·번역문이 포함됩니다. 공유 전에 내용을 확인하세요. 수정은 원본 파일에서 한 뒤 다시 업로드·실행하세요.', 'Reports include source and target text. Check before sharing. Make corrections in your original files, then reupload and rerun.'),
}


def help_for(key, language):
    return HELP[key][0 if language == 'ko' else 1]


def notice_for(key, language):
    return NOTICES[key][0 if language == 'ko' else 1]

