"""Exercise help and the real QA/report path without calling telemetry services."""
import io
from pathlib import Path
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
            app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'ltli_qa_web.py'), default_timeout=15)
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
            app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'ltli_qa_web.py'), default_timeout=15)
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
            from qa_workbooks import localized_report
            from qa_localization import messages
            report = helpers["report_from_frames"](results, 1, False)
            for locale in ("ko", "zh-TW"):
                copy = messages(locale)
                exported = pd.read_excel(io.BytesIO(localized_report(report, locale)), sheet_name=copy["results"])
                self.assertEqual(exported[copy["source"]].tolist(), results["Source"].tolist())
                self.assertEqual(exported[copy["target"]].tolist(), results["Target"].tolist())
            # Changing presentation language keeps the uploaded content and QA result.
            app.selectbox[0].select("繁體中文").run()
            self.assertFalse(app.exception)
            pd.testing.assert_frame_equal(app.session_state["qa_result_dataframe"], results)
            self.assertNotEqual(download.proto.url, app.get("download_button")[-1].proto.url)


    def test_streamlit_downloads_real_workbooks_in_each_selected_locale(self):
        from openpyxl import load_workbook
        import streamlit as st
        from qa_localization import messages

        mime = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        for ui, locale in [('ko','ko'), ('en','en'), ('zh-Hans','zh-CN'), ('zh-Hant','zh-TW')]:
            with self.subTest(locale=locale), patch.dict(sys.modules, {'telemetry': telemetry_stub()}), \
                    patch('qa_orchestrator.post', side_effect=AssertionError('provider called')) as provider, \
                    patch.object(st, 'download_button', wraps=st.download_button) as downloads:
                app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'ltli_qa_web.py'), default_timeout=15)
                app.query_params['lang'] = ui
                app.run()
                sample = next(call.kwargs for call in downloads.call_args_list
                              if call.kwargs.get('key') == f'qa_localized_sample_download_{locale}')
                self.assertEqual(sample['file_name'], f'ltli_qa_sample_{locale}.xlsx')
                with io.BytesIO(sample['data']) as raw:
                    book = load_workbook(raw)
                    expected_rows = [(source or '', target or '') for source, target in list(book.active.values)[1:]]
                    book.close()
                app.file_uploader(key='bilingual_xlsx_uploader').set_value(
                    (sample['file_name'], sample['data'], mime)).run()
                app.button[0].click().run()
                self.assertFalse(app.exception)
                report = next(call.kwargs for call in downloads.call_args_list
                              if call.kwargs.get('key') == f'qa_localized_report_{locale}')
                self.assertEqual(report['file_name'], f'LTLI-QA-report-{locale}.xlsx')
                book = load_workbook(io.BytesIO(report['data']))
                copy = messages(locale)
                self.assertEqual(book.properties.language, locale)
                self.assertEqual(book.sheetnames, [copy['summary'], copy['results'], copy['findings']])
                self.assertEqual(dict(book[copy['summary']].values)[copy['scope']], copy['scope_note'])
                rows = list(book[copy['results']].values)
                self.assertEqual(rows[0], tuple(copy[key] for key in ('segment', 'source', 'target', 'status')))
                self.assertEqual([(row[1] or '', row[2] or '') for row in rows[1:]], expected_rows)
                self.assertIn(copy['issues']['Number mismatch'][1], [c.value for c in book[copy['findings']]['F']])
                if locale == 'zh-TW':
                    self.assertIn('團隊雲端硬碟', rows[1][2])
                book.close()
                provider.assert_not_called()
