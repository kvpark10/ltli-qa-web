# LTLI QA public beta deployment

## Application

- Entry point: `ltli_qa_web.py`
- Runtime: Python 3.12
- Framework: Streamlit
- Public service domain: `qa.ltli.kr`
- Contact: `contact@ltli.kr`

## Local verification

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m streamlit run ltli_qa_web.py
```

Open `http://localhost:8501` and test XLSX, DOCX, TXT and glossary uploads.

## Recommended first deployment

1. Create a private GitHub repository for this deployment package.
2. Upload the files in the package root without changing their names.
3. In Streamlit Community Cloud, create an app from the repository.
4. Set the main file path to `ltli_qa_web.py` and Python to 3.12.
5. Deploy and verify the temporary `*.streamlit.app` address.
6. In the hosting service, add the custom domain `qa.ltli.kr` if the selected plan supports it.
7. At Gabia DNS, add the CNAME value supplied by the hosting service for host `qa`.
8. After HTTPS is active, change the LTLI homepage beta CTA to `https://qa.ltli.kr`.

Do not guess the CNAME target. Copy the exact value shown by the hosting provider.

## Release checks

- XLSX file with exactly one Source and one Target column is accepted.
- DOCX source and target files with matching non-empty paragraph counts are accepted.
- TXT source and target files with matching non-empty line counts are accepted.
- XLSX/CSV glossary with Source Term and Target Term columns is accepted.
- Empty files and files over 10 MB are rejected.
- Generated QA results can be downloaded.
- Uploaded files are not intentionally persisted by the application.
- `contact@ltli.kr` and the privacy warning are visible on the homepage.

## Beta notice

Users should upload only public test files during the initial beta. They should not upload personal information, customer confidential material, diplomatic documents, or unpublished commercial content.
