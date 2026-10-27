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
