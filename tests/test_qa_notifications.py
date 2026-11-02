from datetime import datetime
import json
import os
import queue
import unittest
from unittest.mock import Mock,patch
import qa_notifications as notifications

class NotificationTests(unittest.TestCase):
    def test_fixed_recipient_and_minimal_body(self):
        event={'completed_at':'2026-11-02T00:00:00+00:00','elapsed_ms':30,'segments':2,'warnings':1}
        message=notifications.build_message(event,'sender@example.com')
        self.assertEqual(message['To'],'contact@ltli.kr')
        self.assertIn('검사 구간 수: 2',message.get_content())
        self.assertNotIn('source',message.get_content())
        with self.assertRaises(ValueError):notifications.build_message(event,'bad\nBcc: other@example.com')
    def test_smtp_requires_tls_and_uses_fixed_envelope(self):
        event={'completed_at':'UTC','elapsed_ms':30,'segments':2,'warnings':1}
        env={'LTLI_QA_SMTP_HOST':'smtp.example.com','LTLI_QA_SMTP_USER':'sender@example.com','LTLI_QA_SMTP_PASSWORD':'test-secret','LTLI_QA_SMTP_PORT':'587'}
        with patch.dict(os.environ,env),patch('qa_notifications.smtplib.SMTP') as client:
            notifications._send(event)
            smtp=client.return_value.__enter__.return_value
            smtp.starttls.assert_called_once()
            smtp.login.assert_called_once_with('sender@example.com','test-secret')
            self.assertEqual(smtp.send_message.call_args.kwargs['to_addrs'],['contact@ltli.kr'])
    def test_disabled_invalid_and_full_queue_are_nonblocking(self):
        with patch.dict(os.environ,{'LTLI_QA_EMAIL_ENABLED':'0'}),patch.object(notifications._EVENTS,'put_nowait') as put:
            notifications.notify_qa(1,segments=2,warnings=0);put.assert_not_called()
        with patch.dict(os.environ,{'LTLI_QA_EMAIL_ENABLED':'1'}),patch.object(notifications,'_WORKER') as worker,patch.object(notifications._EVENTS,'put_nowait',side_effect=queue.Full):
            worker.is_alive.return_value=True
            notifications.notify_qa(1,segments=2,warnings=0)
    def test_only_successful_check_not_report_explanation_or_review(self):
        import threading
        import urllib.request
        import urllib.error
        from public_api import BoundedServer,Handler
        server=BoundedServer(('127.0.0.1',0),Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        payload={'action':'qa','rows':[{'source':'Save 2','target':'저장 3'}]}
        called=threading.Event()
        def post(route,data):
            request=urllib.request.Request(f'http://127.0.0.1:{server.server_port}/api/qa/{route}',data=json.dumps(data).encode(),headers={'Content-Type':'application/json'})
            try:
                with urllib.request.urlopen(request) as response:response.read()
            except urllib.error.HTTPError as error:error.read()
        try:
            with patch('public_api.notify_qa',side_effect=lambda *a,**k:called.set()) as notify:
                post('check',payload);self.assertTrue(called.wait(2))
                post('report',payload)
                post('check',dict(payload,explain_id=1))
                post('check',{'action':'qa','rows':[]})
                post('review',{'action':'review','rows':payload['rows']})
                self.assertEqual(notify.call_count,1)
                self.assertEqual(notify.call_args.kwargs,{'segments':1,'warnings':1})
        finally:server.shutdown();server.server_close();thread.join()
