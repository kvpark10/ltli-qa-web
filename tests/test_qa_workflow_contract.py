"""Synthetic file-input and Excel-report contracts; no production endpoints."""
import base64
from copy import deepcopy
from io import BytesIO
import unittest
from xml.etree import ElementTree as ET
from zipfile import ZipFile

import pandas as pd
from openpyxl import Workbook, load_workbook
from public_api import execute
from qa_engine import convert_dataframe_to_excel


ROWS = [{'source': 'Save 2 files.', 'target': '파일 3개 저장.'},
        {'source': 'Hello {name}', 'target': '안녕 {name}'}]


def encoded(name, data):
    return {'name': name, 'data': base64.b64encode(data).decode('ascii')}


def docx(values):
    ns = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
    root = ET.Element('{%s}document' % ns)
    body = ET.SubElement(root, '{%s}body' % ns)
    for value in values:
        paragraph = ET.SubElement(body, '{%s}p' % ns)
        run = ET.SubElement(paragraph, '{%s}r' % ns)
        ET.SubElement(run, '{%s}t' % ns).text = value
    output = BytesIO()
    with ZipFile(output, 'w') as archive:
        archive.writestr('word/document.xml', ET.tostring(root))
    return output.getvalue()


def files(kind):
    if kind == 'xlsx':
        book = Workbook()
        book.active.append(['Source', 'Target'])
        for row in ROWS:
            book.active.append([row['source'], row['target']])
        output = BytesIO()
        book.save(output)
        return [encoded('synthetic.xlsx', output.getvalue())]
    values = [[row[key] for row in ROWS] for key in ('source', 'target')]
    data = [docx(v) if kind == 'docx' else '\n'.join(v).encode() for v in values]
    return [encoded('source.' + kind, data[0]), encoded('target.' + kind, data[1])]


class WorkflowContractTests(unittest.TestCase):
    def check_file(self, kind):
        payload = {'action': 'qa', 'files': files(kind)}
        before = deepcopy(payload)
        result = execute(payload)
        self.assertEqual(result['total'], 2)
        self.assertEqual(result['flagged'], 1)
        self.assertEqual(result['rows'][0]['issues'], ['Number mismatch'])
        self.assertEqual(result['rows'][1]['issues'], [])
        self.assertEqual([{k: row[k] for k in ('source', 'target')} for row in result['rows']], ROWS)
        corrected = deepcopy(ROWS)
        corrected[0]['target'] = '파일 2개 저장.'
        updated = execute({'action': 'qa', 'rows': corrected})
        self.assertEqual(updated['flagged'], 0)
        self.assertEqual(result['flagged'], 1)
        self.assertEqual(payload, before)

    def test_xlsx_input_recheck_and_immutable_source(self):
        self.check_file('xlsx')

    def test_txt_pair_recheck_and_immutable_source(self):
        self.check_file('txt')

    def test_docx_pair_recheck_and_immutable_source(self):
        self.check_file('docx')

    def test_excel_report_literal_formula_prefixes_and_scope(self):
        values = ['=SUM(A1:A2)', '+1+1', '-1+1', '@SUM(A1)', '普通文字 😀']
        frame = pd.DataFrame({'Source': values, 'Target': list(reversed(values)),
                              'QA Issues': ['Number mismatch'] * len(values)})
        before = frame.copy(deep=True)
        book = load_workbook(BytesIO(convert_dataframe_to_excel(frame)), data_only=False)
        self.assertIn('QA Scope', book.sheetnames)
        for index in range(len(values)):
            for column, expected in [(1, values[index]), (2, values[-index - 1])]:
                cell = book['QA Results'].cell(index + 2, column)
                self.assertEqual(cell.data_type, 's')
                self.assertIsNone(cell.hyperlink)
                escaped = "'" + expected if expected.startswith(('=', '+', '-', '@')) else expected
                self.assertEqual(cell.value, escaped)
        self.assertTrue(any('Meaning accuracy' in str(cell.value) for row in book['QA Scope'] for cell in row))
        pd.testing.assert_frame_equal(frame, before)
