from base64 import b64encode
from io import BytesIO
import json
import re
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from openpyxl import load_workbook
from public_api import BoundedServer, Handler, RULES, SAMPLES
from qa_localization import MESSAGES, messages
from qa_workbooks import FONTS


class LocalizedWorkbooksTests(unittest.TestCase):
    def test_catalog_complete_and_safe_default(self):
        baseline = MESSAGES['en']
        self.assertEqual(set(MESSAGES),{'ko','en','zh-CN','zh-TW'})
        codes = {code.rstrip(':') for group in RULES.values() for code in group}
        for copy in MESSAGES.values():
            self.assertEqual(set(copy),set(baseline))
            self.assertEqual(set(copy['issues']),codes)
            self.assertTrue(all(label and description for label,description in copy['issues'].values()))
        self.assertIs(messages('zh-HK'),baseline)

    def test_public_sample_and_localized_report_workflow(self):
        server=BoundedServer(('127.0.0.1',0),Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True)
        thread.start()
        self.addCleanup(thread.join)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        def post(route,payload):
            url=f'http://127.0.0.1:{server.server_port}/api/qa/{route}'
            return urlopen(Request(url,data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'}))
        with patch('qa_orchestrator.post',side_effect=AssertionError('provider called')) as ai, \
             patch('public_api.record_qa'), patch('public_api.notify_qa'):
            for lang, sample in SAMPLES.items():
                with self.subTest(lang=lang):
                    request={'action':'sample','language':lang}
                    with post('prepare',request) as response:
                        self.assertEqual(response.headers['Content-Language'],lang)
                        self.assertEqual(json.load(response)['rows'],sample['rows'])
                    with post('prepare',{**request,'format':'xlsx'}) as response:
                        filename=f'ltli_qa_sample_{lang}.xlsx'
                        self.assertEqual(response.headers['Content-Language'],lang)
                        self.assertIn(filename,response.headers['Content-Disposition'])
                        files=[{'name':filename,'data':b64encode(response.read()).decode()}]
                    with post('prepare',{'action':'prepare','files':files}) as response:
                        prepared=json.load(response)
                    self.assertEqual(prepared['rows'],sample['rows'])
                    self.assertEqual(prepared['glossary'],sample['glossary'])
                    for row in prepared['rows']:
                        self.assertEqual(bool(re.search('[가-힣]', row['source'])), lang == 'en')
                        if row['target']:
                            self.assertEqual(bool(re.search('[가-힣]', row['target'])), lang == 'ko')
                            self.assertEqual(bool(re.search('[一-鿿]', row['target'])), lang.startswith('zh-'))
                    with post('check',{'action':'qa','files':files,'explain_id':1,'language':lang}) as response:
                        result=json.load(response)
                    actual=[{issue.split(':')[0] for issue in row['issues']} for row in result['rows']]
                    for issues,expected in zip(actual,('Number mismatch','Terminology mismatch','Missing translation','Placeholder mismatch')):
                        self.assertIn(expected,issues)
                    self.assertIn(MESSAGES[lang]['issues']['Number mismatch'][1],result['explanation'])
                    # Keep nonlocalized document data literal, even with an Excel formula prefix.
                    literal={'source':'=公式保留／원문','target':'+ＱＡ 文件'}
                    with post('report',{'action':'qa','report_language':lang,'rows':[*sample['rows'],literal],
                                        'glossary':sample['glossary']}) as response:
                        self.assertIn(f"LTLI-QA-report-{lang}.xlsx", response.headers["Content-Disposition"])
                        self.assertEqual(response.headers["Content-Language"], lang)
                        self.assertEqual(response.headers["Cache-Control"], "no-store")
                        book=load_workbook(BytesIO(response.read()))
                    copy=MESSAGES[lang]
                    self.assertEqual(book.properties.title,copy['title'])
                    self.assertEqual(book.properties.language,lang)
                    self.assertIn(copy['generated'],[cell.value for cell in book[copy['summary']]['A']])
                    self.assertEqual(book.sheetnames, [copy['summary'],copy['results'],copy['findings']])
                    self.assertEqual(dict(book[copy['summary']].values)[copy['scope']], copy['scope_note'])
                    sheet=book[copy['results']]
                    self.assertEqual(tuple(cell.value for cell in sheet[1]),
                                     tuple(copy[k] for k in ('segment','source','target','status')))
                    findings = book[copy['findings']]
                    self.assertEqual(findings['F2'].value,copy['issues']['Number mismatch'][1])
                    self.assertEqual(findings['E2'].value,copy['review'])
                    if lang == 'zh-TW':
                        self.assertIn('團隊雲端硬碟',sheet['C2'].value)
                        self.assertIn('手機號碼',' '.join(
                            str(cell.value or '') for cell in findings['G']))

                    self.assertEqual(sheet['B2'].value,sample['rows'][0]['source'])
                    self.assertEqual(sheet['C2'].value,sample['rows'][0]['target'])
                    self.assertEqual(sheet['B6'].value,literal['source'])
                    self.assertEqual(sheet['C6'].value,literal['target'])
                    self.assertEqual(sheet['B6'].data_type,'s')
                    self.assertEqual(sheet['B1'].font.name,FONTS[lang])
                    self.assertIn(copy['issues']['Terminology mismatch'][0],[c.value for c in book[copy['findings']]['C']])
                    book.close()
            # The old UI submitted exactly this payload without a report locale.
            for locale in ({}, {'report_language':'zh-Hant'}):
                with self.assertRaises(HTTPError) as legacy:
                    post('report', {'action':'qa','rows':[
                        {'source':'Save 2 files to {folder}.','target':'파일 3개를 저장하세요.'},
                        {'source':'Welcome.','target':'환영합니다.'},
                    ], **locale})
                with legacy.exception as response:
                    self.assertEqual(response.code,400)
                    self.assertEqual(json.load(response),{'error':'report_language'})
            with self.assertRaises(HTTPError) as rejected:
                post('assist',{'action':'assist','consent':True})
            self.assertEqual(rejected.exception.code,403)
            rejected.exception.close()
            ai.assert_not_called()
