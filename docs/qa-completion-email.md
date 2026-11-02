# QA completion email

Recipient is fixed at contact@ltli.kr, including the SMTP envelope. Only successful /api/qa/check executions notify; explanation, report, prepare, review/restore and failed requests are excluded. Each email contains UTC completion time, segment count, rule-warning count and elapsed milliseconds. No source/target text, filename, IP, session ID or user email is included.

Notifications use an independent bounded memory queue (100 events) and daemon worker. SMTP failure, overflow or process shutdown can lose an alert; no automatic retry, persistence or change to QA results. Sheets logging remains independent. Sanitized failure messages appear in the service journal without provider details or credentials.

Default is disabled. Configure the following variables in a restricted root-owned EnvironmentFile, e.g. /etc/ltli/secrets/qa-mail.env (0600), then add EnvironmentFile=/etc/ltli/secrets/qa-mail.env in a systemd override for ltli-public-qa:

```
LTLI_QA_EMAIL_ENABLED=1
LTLI_QA_SMTP_HOST=YOUR_PROVIDER_SMTP_HOST
LTLI_QA_SMTP_PORT=587
LTLI_QA_SMTP_USER=YOUR_SENDING_ACCOUNT
LTLI_QA_SMTP_PASSWORD=YOUR_SMTP_PASSWORD
LTLI_QA_SMTP_FROM=YOUR_VERIFIED_SENDER_ADDRESS
```

Obtain settings from the actual mail provider. Never commit or paste real credentials into chat. Port 465 uses SMTP-over-TLS; all other ports require STARTTLS with certificate validation. Plaintext fallback is not allowed. No extra Python dependency is required.

Deploy updated source, run tests, systemctl daemon-reload, restart ltli-public-qa, verify loopback health and run one sample QA. Confirm receipt at contact@ltli.kr. API health alone does not confirm delivery. Check journal for sanitized failure notifications if absent. Disable by setting LTLI_QA_EMAIL_ENABLED=0 and restarting. No Nginx configuration change is needed. No actual email or server configuration was performed during development.
