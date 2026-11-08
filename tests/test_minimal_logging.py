import json
import os
import threading
import unittest
import urllib.request
import urllib.error
from unittest.mock import patch
import google_sheets_storage as storage
from public_api import BoundedServer, Handler

class MinimalLogTests(unittest.TestCase):
    def test_allowlist_and_no_identifier(self):
        with patch.dict(os.environ, {'LTLI_QA_SHEETS_ENABLED':'1'}), patch.object(storage, '_WORKER') as worker, patch.object(storage._EVENTS, 'put_nowait') as put:
            worker.is_alive.return_value=True
            storage.record_qa('success', 12, segments=2, warnings=1)
            row=put.call_args.args[0]
            self.assertEqual(row[1], '')
            self.assertEqual(row[2], 'qa_completed')
            self.assertEqual(json.loads(row[3]), {'outcome':'success','elapsed_ms':12,'segment_count':2,'warning_count':1})
    def test_disabled_and_full_queue_do_not_raise(self):
        import queue
        with patch.dict(os.environ, {'LTLI_QA_SHEETS_ENABLED':'0'}), patch.object(storage._EVENTS,'put_nowait') as put:
            storage.record_qa('failed', 1)
            put.assert_not_called()
        with patch.dict(os.environ, {'LTLI_QA_SHEETS_ENABLED':'1'}), patch.object(storage,'_WORKER') as worker, patch.object(storage._EVENTS,'put_nowait',side_effect=queue.Full):
            worker.is_alive.return_value=True
            storage.record_qa('failed',1)
    def test_only_check_requests_are_recorded(self):
        server=BoundedServer(('127.0.0.1',0),Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        payload={'action':'qa','rows':[{'source':'Save 2','target':'저장 3'}]}
        def post(route, data):
            req=urllib.request.Request(f'http://127.0.0.1:{server.server_port}/api/qa/{route}',data=json.dumps(data).encode(),headers={'Content-Type':'application/json'})
            try:
                with urllib.request.urlopen(req) as response: response.read()
            except urllib.error.HTTPError as error: error.read()
        failed_logged=threading.Event()
        def on_record(outcome,*args,**kwargs):
            if outcome=='failed':
                failed_logged.set()
        try:
            with patch('public_api.record_qa',side_effect=on_record) as record:
                post('check',payload)
                post('report',payload)
                post('check',dict(payload,explain_id=1))
                post('prepare',{'action':'prepare','rows':payload['rows']})
                self.assertEqual(record.call_count,1)
                self.assertEqual(record.call_args.args[0],'success')
                self.assertEqual(record.call_args.kwargs,{'segments':1,'warnings':1})
                post('check',{'action':'qa','rows':[]})
                self.assertTrue(failed_logged.wait(2))
                self.assertEqual(record.call_count,2)
                self.assertEqual(record.call_args.args[0],'failed')
        finally:
            server.shutdown();server.server_close();thread.join()
