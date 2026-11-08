import json
import threading
import unittest
import urllib.request
from unittest.mock import patch
from public_api import execute,InputError,BoundedServer,Handler
from qa_findings import review

ROWS=[{'source':'Save 2 files to {folder}.','target':'파일 3개를 저장하세요.'}]
class LocalExplanationTests(unittest.TestCase):
    def test_http_explanation_without_ai_configuration_consent_or_provider(self):
        server=BoundedServer(('127.0.0.1',0),Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            with patch('qa_orchestrator.coordinate',side_effect=AssertionError('No AI coordination')),patch('qa_orchestrator.post',side_effect=AssertionError('No provider call')),patch('qa_orchestrator.Budget.reserve',side_effect=AssertionError('No AI budget')):
                for language in ('ko','en'):
                    request=urllib.request.Request(f'http://127.0.0.1:{server.server_port}/api/qa/check',data=json.dumps({'action':'qa','rows':ROWS,'explain_id':1,'language':language}).encode(),headers={'Content-Type':'application/json'})
                    with urllib.request.urlopen(request) as response:result=json.load(response)
                    self.assertIn('["2"]',result['explanation']);self.assertIn('["3"]',result['explanation']);self.assertIn('{folder}',result['explanation'])
                    self.assertEqual(result['explained_id'],1);self.assertEqual(result['rows'][0]['target'],ROWS[0]['target'])
        finally:server.shutdown();server.server_close();thread.join()
    def test_accepted_findings_stay_hidden_and_decisions_remain(self):
        result=execute({'action':'qa','rows':ROWS})
        result=review(result,{'operation':'accept','row_id':1,'issue':'Number mismatch','fingerprint':result['rows'][0]['fingerprint']})
        result=execute({'action':'qa','rows':ROWS,'decisions':result['decisions'],'explain_id':1})
        self.assertNotIn('숫자 또는 등장 횟수',result['explanation']);self.assertIn('자리표시자',result['explanation']);self.assertEqual(result['accepted_count'],1)
    def test_invalid_segment_and_language_fail_closed(self):
        for extra in ({'explain_id':0},{'explain_id':2},{'explain_id':True},{'explain_id':1,'language':'shell'}):
            with self.assertRaisesRegex(InputError,'explain_request'):execute({'action':'qa','rows':ROWS,**extra})
