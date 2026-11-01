import base64
import importlib.util
import io
import json
import threading
import unittest
import urllib.request
import urllib.error
from pathlib import Path
from zipfile import ZipFile
from openpyxl import Workbook
from public_api import execute, InputError, BoundedServer, Handler
from qa_engine import run_qa_check


def encoded(name,data):return {'name':name,'data':base64.b64encode(data).decode()}
def docx(text):
    out=io.BytesIO()
    with ZipFile(out,'w') as z:z.writestr('word/document.xml',f'<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:body></w:document>')
    return out.getvalue()

class PublicApiTests(unittest.TestCase):
    def test_public_results_reuse_engine_and_do_not_change_inputs(self):
        payload={'action':'qa','rows':[{'source':'Save 2 files to {path}.','target':'파일 3개를 저장하세요.'}]}
        before=json.dumps(payload);result=execute(payload)
        self.assertEqual(result['rows'][0]['issues'],run_qa_check(**{'source':'Save 2 files to {path}.','target':'파일 3개를 저장하세요.'}))
        self.assertEqual(result['flagged'],1);self.assertEqual(json.dumps(payload),before)
    def test_no_translation_or_untrusted_tool_execution(self):
        for action in ('translate','plan','shell','qa; translate'):
            with self.assertRaisesRegex(InputError,'qa_only'):execute({'action':action,'rows':[]})
        with self.assertRaises(InputError):execute({'action':'qa','rows':[],'tool':'translate'})
    def test_file_pairs_and_mismatches(self):
        for name,a,b in [('txt',b'Save 2 files.', '파일 3개 저장.'.encode()),('docx',docx('Save 2 files.'),docx('파일 3개 저장.'))]:
            result=execute({'action':'qa','files':[encoded('a.'+name,a),encoded('b.'+name,b)]})
            self.assertIn('Number mismatch',result['rows'][0]['issues'])
        with self.assertRaisesRegex(InputError,'alignment'):
            execute({'action':'qa','files':[encoded('a.txt',b'a\nb'),encoded('b.txt',b'a')]})
    def test_xlsx_zero_missing_targets_and_duplicate_headers(self):
        book=Workbook();sheet=book.active;sheet.append(['Source','Target']);sheet.append([0,0]);sheet.append(['Hello',None]);out=io.BytesIO();book.save(out)
        r=execute({'action':'qa','files':[encoded('test.xlsx',out.getvalue())]})
        self.assertEqual(r['rows'][0]['source'],'0');self.assertIn('Missing translation',r['rows'][1]['issues'])
        sheet['C1']='Source';out=io.BytesIO();book.save(out)
        with self.assertRaisesRegex(InputError,'columns'):
            execute({'action':'qa','files':[encoded('duplicate.xlsx',out.getvalue())]})
    def test_invalid_xml_entities_size_and_encoding_fail_closed(self):
        out=io.BytesIO()
        with ZipFile(out,'w') as z:z.writestr('word/document.xml','<!DOCTYPE test [<!ENTITY x "secret">]><test/>')
        with self.assertRaisesRegex(InputError,'invalid_file'):execute({'action':'qa','files':[encoded('a.docx',out.getvalue()),encoded('b.docx',out.getvalue())]})
        with self.assertRaisesRegex(InputError,'row_limit'):execute({'action':'qa','rows':[{'source':'a','target':'b'}]*5001})
        with self.assertRaisesRegex(InputError,'text_limit'):execute({'action':'qa','rows':[{'source':'a'*20001,'target':'b'}]})
    def test_percentage_and_scoped_checks(self):
        self.assertNotIn('Placeholder mismatch',run_qa_check('97.7% voted.','97.7%가 투표했습니다.'))
        r=execute({'action':'qa','checks':['numbers'],'rows':[{'source':'Hello {name} 2.','target':'안녕 2.'}]})
        self.assertEqual(r['flagged'],0)
    def test_http_route_boundaries_and_no_store(self):
        server=BoundedServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            url=f'http://127.0.0.1:{server.server_port}'
            request=urllib.request.Request(url+'/api/qa/check',data=json.dumps({'action':'qa','rows':[{'source':'Hello','target':''}]}).encode(),headers={'Content-Type':'application/json'})
            with urllib.request.urlopen(request) as response:
                self.assertEqual(response.headers['Cache-Control'],'no-store');self.assertEqual(json.load(response)['flagged'],1)
            report=urllib.request.Request(url+'/api/qa/report',data=json.dumps({'action':'qa','rows':[{'source':'=SUM(A1:A2)','target':'@formula'}]}).encode(),headers={'Content-Type':'application/json'})
            with urllib.request.urlopen(report) as response:
                from openpyxl import load_workbook
                book=load_workbook(io.BytesIO(response.read()))
                self.assertEqual(book.active['B2'].data_type,'s')
                self.assertTrue(book.active['B2'].value.startswith("'="))
            request=urllib.request.Request(url+'/api/qa/translate',data=b'{}',headers={'Content-Type':'application/json'})
            with self.assertRaises(urllib.error.HTTPError) as e:urllib.request.urlopen(request)
            self.assertEqual(e.exception.code,404)
        finally:server.shutdown();server.server_close();thread.join()
    def test_admin_protection_preserves_other_servers_and_is_idempotent(self):
        spec=importlib.util.spec_from_file_location('protect',Path(__file__).resolve().parents[1]/'deploy/protect-qa-admin.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        original='server {\nlisten 443 ssl;\nserver_name qa.ltli.ai;\nlocation / { proxy_pass http://127.0.0.1:8501; }\n}\nserver {\nserver_name ltli.ai;\n}'
        result=module.protect(original)
        self.assertIn('auth_basic_user_file /etc/nginx/.htpasswd-ltli-translate;',result)
        self.assertTrue(result.endswith('server {\nserver_name ltli.ai;\n}'))
        self.assertEqual(module.protect(result),result)
        with self.assertRaises(ValueError):module.protect(original.replace('location / {','auth_basic off;\nlocation / {'))
