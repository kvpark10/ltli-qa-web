#!/usr/bin/env python3
"""Manually run QA engine/API/admin checks with synthetic data and mock services."""
import argparse
from collections import Counter
from contextlib import ExitStack, redirect_stderr, redirect_stdout
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import ipaddress
import json
import os
from pathlib import Path
import platform
import socket
import subprocess
import sys
import time
import unittest
from unittest.mock import patch
import uuid

ROOT = Path(__file__).resolve().parents[1]
GROUPS = {
    'ENGINE': ['test_engine_rule_contract'],
    'INPUT_REPORT': ['test_qa_workflow_contract'],
    'PUBLIC_API': ['test_public_api', 'test_upload_prepare'],
    'REVIEW_EXPLANATION': ['test_warning_review', 'test_local_explanation'],
    'ADMIN_UI': ['test_ui_help', 'test_localization'],
    'MOCK_AI': ['test_qa_orchestrator'],
    'PRIVACY_NOTIFICATIONS': ['test_minimal_logging', 'test_qa_notifications'],
    'RUNNER': ['test_qa_check_runner'],
}
MANUAL = [
    {'id': 'PRODUCTION', 'status': 'not_run', 'reason': 'No production domain, Nginx authentication, TLS or deployment check.'},
    {'id': 'BROWSER', 'status': 'not_run', 'reason': 'No real browser upload/download, mobile or reconnect check; AppTest only.'},
    {'id': 'EXCEL_VISUAL', 'status': 'not_run', 'reason': 'Workbook contents are parsed; Excel/LibreOffice visual display is not checked.'},
    {'id': 'EXTERNAL_SERVICES', 'status': 'not_run', 'reason': 'AI, SMTP and Google Sheets use mocks; no real provider operation.'},
    {'id': 'LINGUISTIC', 'status': 'not_run', 'reason': 'Rule QA does not certify meaning, fluency or linguistic approval.'},
]


def git(*args):
    return subprocess.check_output(['git', '-C', str(ROOT), *args], text=True).strip()


def loopback_address(family, address):
    if family == socket.AF_UNIX:
        return True
    if family not in (socket.AF_INET, socket.AF_INET6):
        return False
    try:
        return ipaddress.ip_address(address[0]).is_loopback
    except (ValueError, TypeError, IndexError):
        return False


def flatten(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from flatten(item)
        else:
            yield item


class RecordedResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.records = []

    def startTest(self, test):
        self.started = time.monotonic()
        self.record_start = len(self.records)
        super().startTest(test)

    def record(self, test, status, detail=None):
        row = {'id': test.id(), 'status': status,
               'seconds': round(time.monotonic() - getattr(self, 'started', time.monotonic()), 3)}
        if detail:
            row['detail'] = detail
        self.records.append(row)

    def addSuccess(self, test):
        super().addSuccess(test)
        if len(self.records) == self.record_start:
            self.record(test, 'passed')

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self.record(test, 'failed', self._exc_info_to_string(err, test))

    def addError(self, test, err):
        super().addError(test, err)
        self.record(test, 'error', self._exc_info_to_string(err, test))

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        self.record(test, 'skipped', reason)

    def addExpectedFailure(self, test, err):
        super().addExpectedFailure(test, err)
        self.record(test, 'expected_failure', self._exc_info_to_string(err, test))

    def addUnexpectedSuccess(self, test):
        super().addUnexpectedSuccess(test)
        self.record(test, 'unexpected_success')

    def addSubTest(self, test, subtest, err):
        super().addSubTest(test, subtest, err)
        if err is not None:
            status = 'failed' if issubclass(err[0], test.failureException) else 'error'
            self.record(test, status, self._exc_info_to_string(err, subtest))


def scenario_results(records, mapping, omitted=()):
    rows = []
    for scenario, names in mapping.items():
        states = {r['status'] for r in records if r['id'] in names}
        executed = {r['id'] for r in records}
        missing = [name for name in names if name in omitted or name not in executed]
        state = ('failed' if states & {'failed', 'error', 'unexpected_success'} else
                 'incomplete' if not names or missing or states - {'passed'} else 'passed')
        rows.append({'id': scenario, 'status': state, 'tests': names, 'unexecuted': missing})
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, help='New report directory; existing directories are not overwritten.')
    args = parser.parse_args()
    os.chdir(ROOT)
    sys.path[:0] = [str(ROOT), str(ROOT / 'tests')]
    started = datetime.now(timezone.utc)
    output = (args.output or Path('/workspace/scratch/qa-checks') / (started.strftime('%Y%m%dT%H%M%SZ-') + uuid.uuid4().hex[:8])).resolve()
    output.mkdir(parents=True, exist_ok=False)
    head, status = git('rev-parse', 'HEAD'), git('status', '--porcelain=v1', '--untracked-files=all')
    packages = {}
    for name in ('streamlit', 'pandas', 'openpyxl', 'python-docx', 'google-auth', 'requests'):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = 'not_installed'
    discovered = {p.stem for p in (ROOT / 'tests').glob('test_*.py')}
    declared = {name for modules in GROUPS.values() for name in modules}
    unmapped = sorted(discovered - declared)
    blocked = []
    local_connections = []
    original_connect, original_connect_ex = socket.socket.connect, socket.socket.connect_ex

    def guard(original):
        def connect(sock, address):
            if not loopback_address(sock.family, address):
                blocked.append(True)
                raise RuntimeError('Non-loopback connection disabled by QA workflow runner')
            if sock.family in (socket.AF_INET, socket.AF_INET6):
                local_connections.append(True)
            return original(sock, address)
        return connect

    mapping, unique = {}, {}
    with (output / 'tests.log').open('w', encoding='utf-8') as log, ExitStack() as stack:
        stack.enter_context(redirect_stdout(log))
        stack.enter_context(redirect_stderr(log))
        clean = {k: v for k, v in os.environ.items() if not k.startswith(('GEMINI_', 'LTLI_QA_')) and k != 'GOOGLE_APPLICATION_CREDENTIALS'}
        clean.update(LTLI_QA_AGENT_ENABLED='0', LTLI_QA_EMAIL_ENABLED='0', LTLI_QA_SHEETS_ENABLED='0', NO_PROXY='127.0.0.1,localhost,::1', no_proxy='127.0.0.1,localhost,::1')
        stack.enter_context(patch.dict(os.environ, clean, clear=True))
        stack.enter_context(patch('socket.socket.connect', guard(original_connect)))
        stack.enter_context(patch('socket.socket.connect_ex', guard(original_connect_ex)))
        for group, modules in GROUPS.items():
            names = []
            for module in modules:
                for case in flatten(unittest.defaultTestLoader.loadTestsFromName(module)):
                    names.append(case.id())
                    unique.setdefault(case.id(), case)
            mapping[group] = names
        suite = unittest.TestSuite(unique.values())
        result = unittest.TextTestRunner(stream=log, verbosity=2, resultclass=RecordedResult).run(suite)
    groups = scenario_results(result.records, mapping)
    counts = Counter(r['status'] for r in result.records)
    passed = (bool(result.testsRun) and result.wasSuccessful() and set(counts) <= {'passed'}
              and not blocked and not unmapped and all(row['status'] == 'passed' for row in groups))
    fixture_hashes = {name: hashlib.sha256((ROOT / 'tests' / name).read_bytes()).hexdigest()
                      for name in ('test_engine_rule_contract.py', 'test_qa_workflow_contract.py')}
    report = {
        'schema': 'ltli-qa-check-1', 'started_at_utc': started.isoformat(),
        'finished_at_utc': datetime.now(timezone.utc).isoformat(), 'location': str(ROOT),
        'commit': head, 'working_tree_status': status.splitlines(),
        'python': platform.python_version(), 'executable': sys.executable, 'packages': packages,
        'command': [sys.executable, *sys.argv],
        'network_policy': 'Python connect/connect_ex permit numeric loopback and AF_UNIX only; not an OS sandbox for subprocesses.',
        'blocked_network_attempts': len(blocked), 'local_tcp_connections': len(local_connections),
        'unmapped_test_modules': unmapped, 'tests_run': result.testsRun, 'outcomes': dict(counts),
        'records': result.records, 'automated_groups_passed': passed, 'groups': groups,
        'manual_checks': MANUAL, 'synthetic_fixture_source_sha256': fixture_hashes,
        'exit_code': 0 if passed else 1,
    }
    (output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    lines = ['# QA 엔진·API·관리자 화면 로컬 자동 검사', '',
             f'- 실행 SHA: `{head}`', f'- Python: {report["python"]}',
             f'- 실행 수: {result.testsRun}', f'- 결과: {dict(counts)}',
             f'- 자동 검사: {"통과" if passed else "실패 또는 불완전"}',
             f'- 미커밋 변경: {"있음 — report.json 참조" if status else "없음"}',
             f'- 미매핑 모듈: {unmapped}', f'- 차단된 외부 연결 시도: {len(blocked)}', '',
             '운영 사이트 검증이나 번역 의미 품질 인증이 아닙니다. 로컬 API와 AppTest를 구분합니다.', '',
             '| 검사 계층 | 결과 | 연결된 검사 수 |', '|---|---|---|']
    lines += [f'| {row["id"]} | {row["status"]} | {len(row["tests"])} |' for row in groups]
    lines += ['', '## 별도 확인 필요', ''] + [f'- {row["id"]}: 미실행 — {row["reason"]}' for row in MANUAL]
    lines += ['', 'report.json에 개별 결과·환경을, tests.log에 실행 출력을 보존합니다.', '']
    (output / 'report.md').write_text('\n'.join(lines), encoding='utf-8')
    print(f'Report: {output / "report.md"}')
    print(f'Tests: {result.testsRun}; outcomes: {dict(counts)}; exit: {report["exit_code"]}')
    return report['exit_code']


if __name__ == '__main__':
    raise SystemExit(main())
