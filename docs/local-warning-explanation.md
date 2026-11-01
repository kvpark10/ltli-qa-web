# Local warning explanations

The explicit Explain warnings button uses POST /api/qa/check with explain_id and language (ko/en). The server recomputes scoped rules and formats evidence with the existing deterministic explanation function. No coordinator, provider request, AI consent, API key or AI quota is needed. Accepted findings are omitted from the explanation while their decisions and raw findings are retained. Text and decisions are not changed by explanation.

Deploy the backend first, restart ltli-public-qa, verify health, then rebuild/install the matching website. No new Nginx route is required. If reverting, revert the website first, then backend. General free-text requests to /assist still use the existing consent-gated AI coordinator; this change targets the explicit warning-explanation button only.
