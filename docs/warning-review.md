# Inspectable warnings and user decisions

Public QA still reports deterministic formatting and structural warnings, not linguistic approval. Raw `issues` are preserved. `findings` adds source/target UTF-16 ranges for React text highlighting. The browser renders text nodes and `<mark>` only, never document HTML.

`POST /api/qa/review` accepts one explicit human judgment: `operation: accept|restore`, `row_id`, exact `issue`, and current `fingerprint`, plus the same rows, checks and previous decisions. The server reruns rules and validates content binding. A stale target returns 409. Active warnings exclude accepted issues; other findings remain. A changed source, translation or row position invalidates the old judgment. Decisions survive same-content checks and check-scope changes. The coordinator carries decisions through QA tools but does not send them or document text to the model. The model cannot accept or restore findings.

These are anonymous, session-held review annotations, not authenticated approval records. Refresh/new QA clears them; no content or judgments are stored on the server. The XLSX retains raw findings, active findings, user-accepted findings and a User Decisions sheet (UTC time, content fingerprint). User acceptance never means automated clearance or linguistic quality verification.

## Paired deployment

Deploy this backend with the matching website warning-review UI. Back up current static assets, Nginx snippet and service commit first. Update the QA repository and install the changed `deploy/public-qa-location.conf` snippet (now includes `review`). Run tests, restart `ltli-public-qa`, retry loopback health until 200, then `nginx -t` and reload. Build and install the website only after the backend is ready. Retain the existing TLS, rate limits and admin authentication.

Smoke check using synthetic source/translation: highlight a number mismatch, accept just that warning, inspect Accepted, restore it, download the report and confirm user-decision scope. If rollback is needed, restore the previous static assets, snippet and QA commit together, restart the API, check health and reload Nginx. Existing Streamlit admin QA remains compatible with the exporter's optional argument.
