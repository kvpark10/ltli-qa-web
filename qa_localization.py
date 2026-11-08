"""Shared copy for rule explanations and localized public reports."""
import json
from pathlib import Path
from qa_engine import extract_numbers, extract_tags, extract_placeholders, extract_urls, extract_emails

MESSAGES = json.loads(Path(__file__).with_name('qa_messages.json').read_text(encoding='utf-8'))
EVIDENCE = {'Number mismatch':extract_numbers,'Tag mismatch':extract_tags,
            'Placeholder mismatch':extract_placeholders,'URL mismatch':extract_urls,'Email mismatch':extract_emails}


def messages(language):
    return MESSAGES.get(language, MESSAGES['en'])


def issue_details(issue, language):
    code, _, detail = issue.partition(': ')
    copy = messages(language)
    name, description = copy['issues'].get(code, (copy['unknown'], copy['fallback']))
    if code == "Whitespace warning" and detail:
        labels = copy["whitespace_details"]
        detail = ", ".join(labels.get(item, item) for item in detail.split(", "))
    return code, name, description, detail


def localized_explanation(row, language):
    copy = messages(language)
    lines = [copy['opened'].format(id=row['id'])]
    if not row['issues']:
        lines.append(copy['empty'])
    for issue in row['issues']:
        code, _, description, detail = issue_details(issue, language)
        lines.append(description)
        if detail:
            lines.append((copy['terms'] if code=='Terminology mismatch' else copy['detail'])+': '+detail)
        if code in EVIDENCE:
            for side in ('source','target'):
                label = ('Source' if side=='source' else 'Translation') if language=='en' else copy[side]
                if language=='ko':
                    label += ' 검출'
                evidence = json.dumps(EVIDENCE[code](row[side])[:20],ensure_ascii=False)[:400]
                lines.append(label+': '+evidence)
    lines.append(copy['recommend'])
    return '\n'.join(lines)
