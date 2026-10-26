"""Regression checks for the boundary between UI copy and canonical QA data.

Run with: python -m unittest discover -s tests
Uses AST to load helpers without starting the Streamlit UI or telemetry.
"""
import ast
import io
import re
import unittest
from collections import Counter
from pathlib import Path

import pandas as pd
from docx import Document


def load_helpers():
    path = Path(__file__).resolve().parents[1] / "ltli_qa_web.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    constants = {"LANGUAGE", "MAX_FILE_SIZE_BYTES", "ISSUE_LABELS_KO"}
    nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef) or (
        isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id in constants
            for target in node.targets
        )
    )]
    namespace = dict(io=io, re=re, pd=pd, Document=Document, Counter=Counter, UI_LANGUAGE="ko")
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), "exec"), namespace)
    return namespace, tree


class LocalizationTests(unittest.TestCase):
    def setUp(self):
        self.helpers, self.tree = load_helpers()

    def test_all_literal_ui_keys_have_korean_copy(self):
        keys = {node.args[0].value for node in ast.walk(self.tree)
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == "L" and isinstance(node.args[0], ast.Constant)}
        self.assertFalse(keys - self.helpers["LANGUAGE"]["ko"].keys())

    def test_korean_results_do_not_mutate_canonical_report(self):
        original = pd.DataFrame({"Source": ["a"], "Target": ["b"],
                                 "QA Issues": ["Whitespace warning: Leading space, Tab character"],
                                 "QA Result": ["Error"]})
        before = original.copy(deep=True)
        translated = self.helpers["localized_results"](original)
        self.assertEqual(translated["검출 사항"][0], "공백 주의: 앞쪽 공백, 탭 문자")
        self.assertEqual(translated["검사 결과"][0], "검토 필요")
        pd.testing.assert_frame_equal(original, before)
        self.helpers["UI_LANGUAGE"] = "en"
        pd.testing.assert_frame_equal(self.helpers["localized_results"](original), before)

    def test_summary_labels_preserve_counts(self):
        summary = pd.DataFrame({"Issue Type": ["Number mismatch"], "Count": [3]})
        translated = self.helpers["localized_results"](summary)
        self.assertEqual(translated.to_dict("records"), [{"문제 유형": "숫자 불일치", "건수": 3}])

    def test_qa_identifiers_are_language_independent(self):
        for language in ("ko", "en"):
            self.helpers["UI_LANGUAGE"] = language
            self.assertEqual(self.helpers["run_qa_check"]("hello", ""), ["Missing translation"])
            self.assertIn("Number mismatch", self.helpers["run_qa_check"]("2 files.", "3개 파일."))

    def test_validation_preserves_literal_filename_braces(self):
        file = io.BytesIO(b"")
        file.name, file.size = "empty{literal}.txt", 0
        for language, expected in (("ko", "비어"), ("en", "is empty")):
            self.helpers["UI_LANGUAGE"] = language
            with self.assertRaises(ValueError) as error:
                self.helpers["validate_file_size"](file)
            self.assertIn(expected, str(error.exception))
            self.assertIn(file.name, str(error.exception))


if __name__ == "__main__":
    unittest.main()
