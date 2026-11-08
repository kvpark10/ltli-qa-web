import io
import json
import threading
import unittest
import urllib.request
import urllib.error
from unittest.mock import patch
from openpyxl import load_workbook
from public_api import BoundedServer,Handler

class PreparationTests(unittest.TestCase):
    def setUp(self):
        self.server=BoundedServer(('127.0.0.1',0),Handler)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
    def tearDown(self):self.server.shutdown();self.server.server_close();self.thread.join()
    def send(self,path,payload):
        return urllib.request.urlopen(urllib.request.Request(f'http://127.0.0.1:{self.server.server_port}'+path,
            data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'}))
    def test_prepare_returns_alignment_without_running_checks_or_ai(self):
        rows=[{'source':'Save 2 files.','target':'파일 3개.'},{'source':'Hello','target':''}]
        with patch('public_api.run_qa_check') as qa,patch('qa_orchestrator.coordinate') as ai:
            with self.send('/api/qa/prepare',{'action':'prepare','rows':rows}) as output:prepared=json.load(output)
            self.assertEqual(prepared['rows'],rows);self.assertEqual(prepared['total'],2)
            qa.assert_not_called();ai.assert_not_called()
        with self.send('/api/qa/check',{'action':'qa','rows':prepared['rows']}) as output:result=json.load(output)
        self.assertIn('Number mismatch',result['rows'][0]['issues'])
        self.assertIn('Missing translation',result['rows'][1]['issues'])
    def test_prepare_rejects_tool_injection_and_oversized_content(self):
        for payload in ({'action':'translate','rows':[]}, {'action':'prepare','rows':[],'tool':'shell'},
                        {'action':'prepare','rows':[{'source':'a','target':'b'}]*5001}):
            with self.assertRaises(urllib.error.HTTPError) as error:self.send('/api/qa/prepare',payload)
            self.assertEqual(error.exception.code,400)
    def test_report_explicitly_excludes_linguistic_validation(self):
        with self.send('/api/qa/report',{'action':'qa','rows':[{'source':'Hello.','target':'안녕하세요.'}]}) as output:
            book=load_workbook(io.BytesIO(output.read()))
        self.assertEqual(book.sheetnames[0],'QA Results')
        self.assertIn('QA Scope',book.sheetnames)
        text=' '.join(str(row[0]) for row in book['QA Scope'].values)
        self.assertIn('의미 정확성·문법·자연스러움은 검사하지 않습니다',text)
        self.assertIn('Meaning accuracy, grammar and fluency are not evaluated',text)
