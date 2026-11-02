"""Minimal aggregate QA events. No content, identifiers or email is collected."""
import datetime
import json
import os
import queue
import threading

_EVENTS = queue.Queue(maxsize=100)
_LOCK = threading.Lock()
_WORKER = None

def _append(row):
    # Lazy imports keep disabled logging independent of Google dependencies.
    from google.oauth2 import service_account
    from google.auth.transport.requests import AuthorizedSession
    credentials = service_account.Credentials.from_service_account_file(
        os.environ.get('LTLI_QA_SHEETS_CREDENTIALS', '/etc/ltli/secrets/google-service-account.json'),
        scopes=['https://www.googleapis.com/auth/spreadsheets'])
    sheet = os.environ.get('LTLI_QA_SHEETS_ID', '1ikhPeouuKeFuvYgglIjtNguygKjJmsKmfqarDLwsiQY')
    with AuthorizedSession(credentials) as session:
        response = session.post(
            f'https://sheets.googleapis.com/v4/spreadsheets/{sheet}/values/analytics_events!A:D:append',
            params={'valueInputOption':'RAW','insertDataOption':'INSERT_ROWS'},
            json={'values':[row]}, timeout=5)
        response.raise_for_status()

def _consume():
    while True:
        row = _EVENTS.get()
        try:
            _append(row)
        except Exception:
            # Never expose credential/provider errors or block a QA request.
            pass
        finally:
            _EVENTS.task_done()

def record_qa(outcome, elapsed_ms, *, segments=None, warnings=None):
    """Best-effort, bounded and nonblocking. Enable explicitly on the server."""
    if os.environ.get('LTLI_QA_SHEETS_ENABLED') != '1':
        return
    try:
        metadata = {'outcome': 'success' if outcome == 'success' else 'failed',
                    'elapsed_ms': max(0, int(elapsed_ms))}
        for key, value in (('segment_count', segments), ('warning_count', warnings)):
            if type(value) is int and value >= 0:
                metadata[key] = value
        row = [datetime.datetime.now(datetime.timezone.utc).isoformat(), '',
               'qa_completed' if outcome == 'success' else 'qa_failed',
               json.dumps(metadata, ensure_ascii=False)]
        global _WORKER
        with _LOCK:
            if _WORKER is None or not _WORKER.is_alive():
                _WORKER = threading.Thread(target=_consume, daemon=True)
                _WORKER.start()
        _EVENTS.put_nowait(row)
    except Exception:
        pass
