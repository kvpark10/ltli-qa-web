# Minimal QA execution log

Only /api/qa/check records successful or failed execution; explain_id requests, preparation, reports and warning decisions are excluded. Repeated explicit checks count separately. Malformed JSON and transport-level rejection are excluded.

Existing analytics_events!A:D columns: UTC timestamp, empty session ID, qa_completed/qa_failed, JSON metadata containing outcome, elapsed_ms and (on success) segment_count and warning_count. No email, IP, session ID, file name, source or translation. warning_count counts rule warnings, not warned segments.

Server activation: install requirements.txt in the QA service virtualenv. Set LTLI_QA_SHEETS_ENABLED=1 in the systemd service environment via an override, then daemon-reload and restart the public QA service. Default is disabled. Credentials default to /etc/ltli/secrets/google-service-account.json; optional LTLI_QA_SHEETS_CREDENTIALS and LTLI_QA_SHEETS_ID override the path/target. Share the sheet with the service account as Editor; do not publish credentials. Verify analytics_events exists and use a sample check to confirm one appended row, then explanation/review/report produce none. Existing historical rows are unchanged.

One daemon worker with a memory queue of 100; no automatic retries. Failed writes, queue overflow, or shutdown can lose events. This is operational counting, not an audit/billing ledger. QA responses do not wait for Sheets. Disable via LTLI_QA_SHEETS_ENABLED=0 and restart. Nginx settings are unaffected. No real Sheets write or production restart was performed during implementation.
