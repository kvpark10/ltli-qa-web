"""Independent positive/negative synthetic expectations for public QA rules."""
import unittest
from qa_engine import run_qa_check

# name, expected warning prefix, source, matching target, mismatching target
CASES = [
    ('missing', 'Missing translation', 'Hello', '안녕', ''),
    ('identical', 'Source and target are identical', 'Hello', '안녕', 'Hello'),
    ('numbers', 'Number mismatch', 'Save 2 files.', '파일 2개 저장.', '파일 3개 저장.'),
    ('punctuation', 'Punctuation mismatch', 'Hello.', '안녕.', '안녕!'),
    ('tags', 'Tag mismatch', '<b>Hello</b>', '<b>안녕</b>', '<i>안녕</i>'),
    ('placeholders', 'Placeholder mismatch', 'Hello {name}', '안녕 {name}', '안녕 {other}'),
    ('brackets', 'Bracket mismatch', 'Open (file)', '열기 (파일)', '파일 열기'),
    ('unbalanced', 'Unbalanced target brackets', 'Open (file)', '열기 (파일)', '열기 (파일'),
    ('urls', 'URL mismatch', 'Open https://example.com/a', 'https://example.com/a 열기', 'https://example.com/b 열기'),
    ('emails', 'Email mismatch', 'Contact a@example.com', 'a@example.com 문의', 'b@example.com 문의'),
    ('whitespace', 'Whitespace warning:', 'Hello', '안녕', '  안녕  '),
    ('filenames', 'File name mismatch', 'Open config.json', 'config.json 열기', 'other.json 열기'),
    ('shortcuts', 'Shortcut mismatch', 'Press Ctrl+C', 'Ctrl+C 누르기', 'Ctrl+V 누르기'),
    ('units', 'Unit mismatch', 'Weight 2 kg', '무게 2 kg', '무게 2 g'),
]


class RuleMatrixTests(unittest.TestCase):
    def test_reordered_tokens_preserve_counts_but_missing_repetitions_warn(self):
        self.assertNotIn('Number mismatch', run_qa_check('Values 1 2 2', '값 2 1 2'))
        self.assertIn('Number mismatch', run_qa_check('Values 1 2 2', '값 1 2'))
        self.assertNotIn('Placeholder mismatch', run_qa_check('{a} {b} {a}', '{b} {a} {a} 번역'))
        self.assertIn('Placeholder mismatch', run_qa_check('{a} {b} {a}', '{b} {a} 번역'))


def rule_test(case):
    _, warning, source, good, bad = case

    def check(self):
        self.assertFalse(any(x.startswith(warning) for x in run_qa_check(source, good)))
        self.assertTrue(any(x.startswith(warning) for x in run_qa_check(source, bad)))
    return check


for case in CASES:
    setattr(RuleMatrixTests, 'test_' + case[0], rule_test(case))
