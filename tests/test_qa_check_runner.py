"""Reporting must not turn missing, skipped or failed checks into passes."""
import io
import socket
import unittest
from scripts.check_qa_workflows import RecordedResult, scenario_results, loopback_address


class QaCheckRunnerTests(unittest.TestCase):
    def test_missing_skipped_and_empty_mappings_are_incomplete(self):
        records = [{'id': 'ok', 'status': 'passed'}, {'id': 'skip', 'status': 'skipped'}]
        mapping = {'ok': ['ok'], 'missing': ['absent'], 'skip': ['skip'], 'empty': []}
        rows = scenario_results(records, mapping)
        self.assertEqual([r['status'] for r in rows], ['passed', 'incomplete', 'incomplete', 'incomplete'])
        self.assertEqual(rows[1]['unexecuted'], ['absent'])

    def test_failure_dominates_partial_success_and_omission(self):
        records = [{'id': 'ok', 'status': 'passed'}, {'id': 'bad', 'status': 'error'}]
        rows = scenario_results(records, {'S': ['ok', 'bad', 'omitted']}, {'omitted'})
        self.assertEqual(rows[0]['status'], 'failed')
        self.assertEqual(rows[0]['unexecuted'], ['omitted'])

    def test_subtest_failure_is_retained_without_success_record(self):
        class Fixture(unittest.TestCase):
            def runTest(self):
                with self.subTest(item='first'):
                    self.assertEqual(1, 2)
                with self.subTest(item='second'):
                    self.assertEqual(2, 2)
        case = Fixture()
        result = unittest.TextTestRunner(stream=io.StringIO(), resultclass=RecordedResult).run(case)
        self.assertFalse(result.wasSuccessful())
        self.assertEqual([r['status'] for r in result.records], ['failed'])
        self.assertEqual(scenario_results(result.records, {'S': [case.id()]})[0]['status'], 'failed')

    def test_class_setup_failure_is_recorded_without_start_test(self):
        class Fixture(unittest.TestCase):
            @classmethod
            def setUpClass(cls):
                raise RuntimeError('missing prerequisite')

            def test_never_executed(self):
                raise AssertionError('must not run')
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(Fixture)
        result = unittest.TextTestRunner(stream=io.StringIO(), resultclass=RecordedResult).run(suite)
        self.assertEqual(result.testsRun, 0)
        self.assertFalse(result.wasSuccessful())
        self.assertEqual([r['status'] for r in result.records], ['error'])

    def test_only_numeric_loopback_and_unix_are_allowed(self):
        self.assertTrue(loopback_address(socket.AF_INET, ('127.0.0.1', 8510)))
        self.assertTrue(loopback_address(socket.AF_INET6, ('::1', 8510, 0, 0)))
        self.assertTrue(loopback_address(socket.AF_UNIX, '/tmp/local-ipc'))
        for host in ['8.8.8.8', '10.0.0.1', '169.254.169.254', 'example.com', '127.0.0.1.example.com']:
            self.assertFalse(loopback_address(socket.AF_INET, (host, 443)))
