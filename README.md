# LTLI QA

Free Translation Quality Assurance Web Application

Developed by the Language Technology & Localization Institute (LTLI).

## Official Service

https://qa.ltli.ai

## Features

- Bilingual XLSX quality assurance

- Aligned DOCX and TXT file support

- Translation consistency and formatting checks

- Number, punctuation, tag, and placeholder checks

- Terminology and glossary checks

- Downloadable Excel QA reports

- Korean and English user interface

## Technology

- Python and Streamlit

- AWS Lightsail (Seoul)

- Nginx reverse proxy

- HTTPS with Let's Encrypt

- Google Sheets API for anonymous usage analytics

## Privacy

LTLI QA records limited anonymous usage events.

Uploaded source and target texts, filenames, and glossary

contents are not included in usage analytics.

The application does not provide an in-app feedback form

or collect interview registration information.

## Local Development

Install dependencies:

    python -m pip install -r requirements.txt

Run the application:

    python -m streamlit run ltli_qa_web.py

## Production Deployment

The production application runs on AWS Lightsail

using the systemd service `ltli-qa`.

Nginx provides HTTPS access at https://qa.ltli.ai.

Google Sheets credentials are stored outside

the Git repository.

## Contact

Suggestions and inquiries:

contact@ltli.kr

## Contextual UI help

Korean/English contextual help uses the same approach as LTLI Translate: a collapsible workflow guide, native widget help tooltips, and persistent notices for alignment, rerunning QA and report contents. Tooltips cover input files, sample/template downloads, optional terminology, Run QA, result metrics and Excel download.

The screen explains that corrections are made in the original files, followed by reupload and rerun. Pass rate is an automated check statistic, not a semantic quality score. Reports include source and target text. QA rule logic, report format and telemetry are unchanged.

Validation: `python -m unittest discover -s tests -v` — 7 tests including localized UI AppTest, upload/run/report path and existing regression checks. UI tests stub telemetry and do not write analytics. Real browser hover/mobile checks remain part of deployment review.
