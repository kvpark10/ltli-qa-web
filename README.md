# LTLI QA Public Beta

Streamlit-based translation QA for bilingual XLSX and aligned DOCX/TXT files.

## Main files

- `ltli_qa_web.py`: application and QA interface
- `telemetry.py`: privacy-first anonymous usage events and feedback storage
- `supabase_schema.sql`: Supabase tables and row-level security policies
- `ANALYTICS_SETUP.md`: setup, privacy design, and deployment checklist
- `.streamlit/secrets.toml.example`: Streamlit Secrets template

Run locally:

```bash
python -m pip install -r requirements.txt
python -m streamlit run ltli_qa_web.py
```

The QA app continues to work when Supabase Secrets are absent or telemetry is
temporarily unavailable.
