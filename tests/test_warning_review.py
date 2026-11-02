import io
import json
import threading
import unittest
import urllib.request
import urllib.error
from copy import deepcopy
from unittest.mock import Mock
from openpyxl import load_workbook
from public_api import execute, Handler, BoundedServer
from qa_findings import review, ReviewError, finding
from qa_orchestrator import coordinate

ROWS=[{'source':'😀 Save 2 files to {folder}.','target':'파일 3개를 저장하세요.'}]

def accept(result,issue='Number mismatch'):
    return review(result,{'operation':'accept','row_id':1,'issue':issue,'fingerprint':result['rows'][0]['fingerprint']})

class WarningReviewTests(unittest.TestCase):
    def test_exact_highlights_utf16_and_missing_placeholder(self):
        result=execute({'action':'qa','rows':ROWS});row=result['rows'][0]
        f=next(f for f in row['findings'] if f['issue']=='Number mismatch')
        self.assertEqual(f['source_spans'],[[8,9]])
        self.assertEqual(f['target_spans'],[[3,4]])
        f=next(f for f in row['findings'] if f['issue']=='Placeholder mismatch')
        self.assertEqual(f['source_spans'],[[19,27]]);self.assertEqual(f['target_spans'],[])
        row={'source':'2 2 2026','target':'2 2026'}
        self.assertEqual(finding(row,'Number mismatch')['source_spans'],[[2,3]])
    def test_tags_and_unsafe_html_remain_literal_data(self):
        row={'source':'<script>alert(1)</script>','target':'텍스트'}
        f=finding(row,'Tag mismatch')
        self.assertEqual(f['source_spans'],[[0,8],[16,25]])
        self.assertEqual(row['source'],'<script>alert(1)</script>')
        self.assertEqual(finding({'source':'Hello','target':' x  y\t'},'Whitespace warning: Repeated spaces')['target_spans'],[[0,1],[2,4],[5,6]])
        self.assertEqual(finding({'source':'x','target':'(x]'},'Unbalanced target brackets')['target_spans'],[[2,3],[0,1]])
    def test_accept_only_one_warning_restore_and_immutable_text(self):
        original=deepcopy(ROWS);result=accept(execute({'action':'qa','rows':ROWS}))
        row=result['rows'][0]
        self.assertIn('Number mismatch',row['issues']);self.assertNotIn('Number mismatch',row['active_issues'])
        self.assertIn('Placeholder mismatch',row['active_issues']);self.assertEqual(result['accepted_count'],1)
        result=review(result,{'operation':'restore','row_id':1,'issue':'Number mismatch','fingerprint':row['fingerprint']})
        self.assertEqual(result['accepted_count'],0);self.assertIn('Number mismatch',result['rows'][0]['active_issues'])
        self.assertEqual(ROWS,original)
    def test_multiple_warning_decisions_restore_in_sequence(self):
        rows=[{'source':'Save 2 files to {folder}.','target':'파일 3개를 저장하세요.'}]
        result=execute({'action':'qa','rows':rows})
        issues=list(result['rows'][0]['issues'])
        self.assertEqual(len(issues),3)
        for operation in ('accept','restore'):
            for index,issue in enumerate(issues,1):
                result=execute({'action':'qa','rows':rows,'decisions':result['decisions']})
                result=review(result,{'operation':operation,'row_id':1,'issue':issue,
                                     'fingerprint':result['rows'][0]['fingerprint']})
                expected=index if operation=='accept' else len(issues)-index
                self.assertEqual(result['accepted_count'],expected)
        self.assertEqual(result['rows'][0]['active_issues'],issues)
        self.assertEqual(result['decisions'],[])

    def test_content_changes_invalidate_decision_and_old_action(self):
        result=accept(execute({'action':'qa','rows':ROWS}));old=deepcopy(result)
        changed=[{'source':ROWS[0]['source'],'target':'파일 4개를 저장하세요.'}]
        current=execute({'action':'qa','rows':changed,'decisions':result['decisions']})
        self.assertEqual(current['accepted_count'],0);self.assertEqual(current['decisions'],[])
        with self.assertRaisesRegex(ReviewError,'stale_review'):
            review(current,{'operation':'accept','row_id':1,'issue':'Number mismatch','fingerprint':old['rows'][0]['fingerprint']})
    def test_acceptance_survives_rechecks_and_scope_changes(self):
        result=accept(execute({'action':'qa','rows':ROWS}))
        scoped=execute({'action':'qa','rows':ROWS,'checks':['structure'],'decisions':result['decisions']})
        self.assertEqual(len(scoped['decisions']),1)
        full=execute({'action':'qa','rows':ROWS,'decisions':scoped['decisions']})
        self.assertEqual(full['rows'][0]['accepted_issues'],['Number mismatch'])
        for invalid in ({},'all',[{'id':1}]):
            with self.assertRaises(ReviewError):execute({'action':'qa','rows':ROWS,'decisions':invalid})
    def test_coordinator_keeps_decisions_without_sending_them_or_source_to_model(self):
        result=accept(execute({'action':'qa','rows':ROWS}))
        transport=Mock(return_value={'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':json.dumps({'action':'run_qa','checks':['numbers'],'segment_id':0,'question':'scope'})}]}}]})
        payload={'action':'assist','request_id':'test-review-request-123','message':'숫자 검사','consent':True,'previous_checks':['numbers'],'decisions':result['decisions']}
        response=coordinate(payload,ROWS,execute,transport,Mock())
        self.assertEqual(response['qa']['flagged'],0);self.assertEqual(response['qa']['accepted_count'],1)
        sent=json.dumps(transport.call_args.args)
        self.assertNotIn(result['rows'][0]['fingerprint'],sent);self.assertNotIn(ROWS[0]['source'],sent)
    def test_http_review_report_restore_and_stale_conflict(self):
        server=BoundedServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        def post(path,payload,raw=False):
            request=urllib.request.Request(f'http://127.0.0.1:{server.server_port}/api/qa/'+path,data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'})
            with urllib.request.urlopen(request) as response:return response.read() if raw else json.load(response)
        try:
            result=post('check',{'action':'qa','rows':ROWS,'checks':['numbers']})
            action={'action':'review','rows':ROWS,'checks':['numbers'],'decisions':[],'operation':'accept','row_id':1,'issue':'Number mismatch','fingerprint':result['rows'][0]['fingerprint']}
            result=post('review',action);self.assertEqual(result['flagged'],0)
            book=load_workbook(io.BytesIO(post('report',{'action':'qa','rows':ROWS,'checks':['numbers'],'decisions':result['decisions']},True)))
            self.assertIn('User Decisions',book.sheetnames);self.assertEqual(book['User Decisions']['C2'].value,'Accepted by user')
            self.assertIn('User accepted warnings',[c.value for c in book.active[2]])
            self.assertIn('Number mismatch',[c.value for c in book.active[2]])
            action.update(operation='restore',decisions=result['decisions']);self.assertEqual(post('review',action)['flagged'],1)
            action['fingerprint']='outdated'
            with self.assertRaises(urllib.error.HTTPError) as e:post('review',action)
            self.assertEqual(e.exception.code,409)
        finally:server.shutdown();server.server_close();thread.join()

