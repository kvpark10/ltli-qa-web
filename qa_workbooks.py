"""XLSX files for the public QA service."""
from datetime import datetime, timezone
from io import BytesIO
import json
from pathlib import Path
from openpyxl import Workbook
from openpyxl.cell import Cell
from openpyxl.utils import get_column_letter
from openpyxl.styles import Alignment, Font
from qa_localization import issue_details, messages

SAMPLES = json.loads(Path(__file__).with_name("qa_samples.json").read_text(encoding="utf-8"))
GLOSSARY_SHEET = 'LTLI Glossary'
GLOSSARY_HEADER = ('Source term', 'Approved translation')
WRAP = Alignment(wrap_text=True,vertical='top')
FONTS = {'ko':'Malgun Gothic','en':'Calibri','zh-CN':'Microsoft YaHei','zh-TW':'Microsoft JhengHei','ja':'Yu Gothic'}


def append_text(sheet, values, font=None):
    cells = []
    for value in values:
        cell = Cell(sheet,value=value)
        if isinstance(value,str):
            cell.data_type = 's'  # Preserve literal text, including formula-like prefixes.
        if font is not None:
            cell.font = font
            cell.alignment = WRAP
        cells.append(cell)
    sheet.append(cells)


def formatted_sheet(book, title, widths):
    sheet = book.create_sheet(title)
    sheet.freeze_panes = 'A2'
    for index,width in enumerate(widths,1):
        sheet.column_dimensions[get_column_letter(index)].width = width
    return sheet


def workbook_bytes(workbook):
    output = BytesIO()
    workbook.save(output)
    workbook.close()
    return output.getvalue()


def sample_workbook(sample):
    book = Workbook()
    sheet = book.active
    sheet.title = 'QA Input'
    sheet.append(('Source','Target'))
    for row in sample['rows']:
        append_text(sheet, (row['source'],row['target']))
    sheet = book.create_sheet(GLOSSARY_SHEET)
    sheet.append(GLOSSARY_HEADER)
    for entry in sample['glossary']:
        for target in entry['approved_targets']:
            append_text(sheet, (entry['source_term'],target))
    return workbook_bytes(book)


def report_filename(language):
    return f"LTLI-QA-report-{language}.xlsx"


def localized_report(result, language):
    c = messages(language)
    book = Workbook()
    book.remove(book.active)
    book.properties.title = c['title']
    book.properties.language = language
    summary = formatted_sheet(book,c['summary'],(28,95))
    font = Font(name=FONTS.get(language,FONTS['en']))
    header = Font(name=font.name,bold=True)
    append_text(summary,(c['title'],),header)
    items = [
        ('generated',datetime.now(timezone.utc).isoformat(timespec='seconds')),
        ('language',language),
        ('checks',', '.join(c[rule] for rule in result['checks'])),
        ('total',result['total']),('flagged',result['flagged']),
        ('warnings',sum(len(row['issues']) for row in result['rows'])),
        ('accepted_count',result['accepted_count']),('scope',c['scope_note']),
    ]
    for label,value in items:
        append_text(summary,(c[label],value),font)
    metadata_columns = result.get('metadata_columns', [])
    data = formatted_sheet(book,c['results'],(12,60,60,20,*([24] * len(metadata_columns))))
    append_text(data, (*(c[k] for k in ('segment','source','target','status')), *metadata_columns),header)
    warnings = formatted_sheet(book,c['findings'],(12,32,24,13,20,45,38,48,27))
    append_text(warnings, tuple(c[k] for k in ('segment','code','issue','severity','status','description','detail','advice','accepted_at')),header)
    decisions = {(d['id'],d['issue']):d['accepted_at'] for d in result['decisions']}
    for row in result['rows']:
        status = 'review' if row['active_issues'] else 'accepted' if row['accepted_issues'] else 'clear'
        append_text(data,(row['id'],row['source'],row['target'],c[status],*row.get('metadata', [])),font)
        for issue in row['issues']:
            code,name,description,detail = issue_details(issue,language)
            accepted = decisions.get((row['id'],issue),'')
            append_text(warnings,(row['id'],code,name,c['warning'],c['accepted' if accepted else 'review'],
                                  description,detail,c['recommend'],accepted),font)
    data.auto_filter.ref = f"A1:{get_column_letter(4 + len(metadata_columns))}{result['total']+1}"
    warnings.auto_filter.ref = f"A1:I{sum(len(row['issues']) for row in result['rows'])+1}"
    if decisions:
        review = formatted_sheet(book,c['decisions'],(12,32,26,42,28))
        append_text(review,tuple(c[k] for k in ('segment','code','issue','detail','accepted_at')),header)
        for (segment,issue),accepted in decisions.items():
            code,name,_,detail = issue_details(issue,language)
            append_text(review,(segment,code,name,detail,accepted),font)
    return workbook_bytes(book)
