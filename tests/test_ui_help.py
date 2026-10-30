"""Exercise help and the real QA/report path without calling telemetry services."""
import io
import sys
import types
import unittest
from unittest.mock import patch

import pandas as pd
from streamlit.testing.v1 import AppTest


def telemetry_stub():
    module = types.ModuleType('telemetry')
    module.APP_VERSION = 'test'
    module.elapsed_milliseconds = lambda started: 1
    module.file_size_bucket = lambda size: 'test'
    module.telemetry_enabled = lambda: False
    module.track_event = lambda *args, **kwargs: None
    module.track_once = lambda *args, **kwargs: None
    return module


class UiHelpTests(unittest.TestCase):
    def test_upload_guidance_in_both_languages(self):
        with patch.dict(sys.modules, {'telemetry': telemetry_stub()}):
            app = AppTest.from_file('../ltli_qa_web.py', default_timeout=15)
            app.query_params['lang'] = 'ko'
            app.run()
            self.assertFalse(app.exception)
            self.assertIn('사용 방법', [x.label for x in app.expander])
            self.assertTrue(app.file_uploader(key='source_document_uploader').proto.help)
            self.assertNotIn('glossary_uploader', [x.key for x in app.file_uploader])
            self.assertFalse(any('용어집' in x.label or 'glossary' in x.label.lower() for x in app.expander))
            app.selectbox[0].select('English').run()
            self.assertFalse(app.exception)
            self.assertIn('How to use', [x.label for x in app.expander])
            self.assertNotIn('glossary_uploader', [x.key for x in app.file_uploader])

    def test_qa_help_does_not_change_results_or_report(self):
        buffer = io.BytesIO()
        pd.DataFrame({'Source': ['There are 2 files.', 'Save {0}.'], 'Target': ['파일은 3개입니다.', '{0}을 저장하세요.']}).to_excel(buffer, index=False)
        with patch.dict(sys.modules, {'telemetry': telemetry_stub()}):
            app = AppTest.from_file('../ltli_qa_web.py', default_timeout=15)
            app.query_params['lang'] = 'ko'
            app.run()
            app.file_uploader(key='bilingual_xlsx_uploader').set_value(('sample.xlsx', buffer.getvalue(), 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')).run()
            self.assertFalse(app.exception)
            self.assertTrue(any('다시 실행' in x.value for x in app.caption))
            self.assertIn('현재 업로드', app.button[0].proto.help)
            app.button[0].click().run()
            self.assertFalse(app.exception)
            results = app.session_state['qa_result_dataframe']
            self.assertIn('Number mismatch', results.iloc[0]['QA Issues'])
            self.assertNotIn('Number mismatch', results.iloc[1]['QA Issues'])
            self.assertEqual(len(results), 2)
            self.assertNotIn('Terminology mismatch', app.session_state['qa_issue_summary']['Issue Type'].tolist())
            self.assertTrue(any('의미 정확성' in x.value for x in app.info))
            self.assertTrue(all(x.proto.help for x in app.metric))
            download = app.get('download_button')[-1]
            self.assertIn('원문', download.proto.help)
            self.assertEqual(download.proto.label, 'Excel 보고서 다운로드 ↓')
            from test_localization import load_helpers
            helpers, _ = load_helpers()
            convert_dataframe_to_excel = helpers['convert_dataframe_to_excel']
            exported = pd.read_excel(io.BytesIO(convert_dataframe_to_excel(results)))
            self.assertEqual(exported['Source'].tolist(), results['Source'].tolist())

