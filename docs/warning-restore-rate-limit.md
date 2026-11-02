# Warning restore request limits

Accept/restore actions previously shared the 6 requests/minute upload/check/AI quota. Several rapid warning decisions can exhaust that bucket and receive HTTP 429. The production sample succeeded when requests were spaced; the screenshot's exact failure status has not been captured.

Give /api/qa/review an independent 30 requests/minute quota with burst 10. Preserve the 29 MiB body cap, connection cap, backend concurrency cap, timeouts and no-content-logging policy. Upload/check/report/assist/prepare use 30 requests/minute with the existing burst 3, matching the manually updated production setting. Review uses a separate 30 requests/minute bucket with burst 10.

Deployment: back up both existing Nginx snippets. Install public-qa-http.conf before public-qa-location.conf; both must be present before nginx -t and reload. Verify the actual include paths first. A git update alone does not install these files. No Python service restart is needed for this configuration-only behavior change. Rollback both snippets together, nginx -t, then reload.

Validate with the public sample: accept Number/Placeholder/Bracket warnings then restore each quickly. Verify no decisions remain and all warnings return. Confirm the separate review limit still returns 429 on excess and the original check limit remains enforced. No Gemini call is needed. Local warning-review regression: 8 tests passed; Nginx binary unavailable locally, so nginx -t and rapid production browser validation remain deployment checks.
