# LTLI QA 익명 사용량 통계·피드백 설정

## 1. Supabase 설정

1. Supabase에서 새 프로젝트를 생성합니다.
2. SQL Editor에서 `supabase_schema.sql` 전체를 실행합니다.
3. Project Settings → API에서 Project URL과 `anon` public key를 확인합니다.
4. `service_role` 키는 앱에 입력하지 않습니다.

## 2. Streamlit Community Cloud Secrets

앱 관리 화면의 Settings → Secrets에 다음 값을 입력합니다.

```toml
SUPABASE_URL = "https://YOUR_PROJECT_REF.supabase.co"
SUPABASE_ANON_KEY = "YOUR_SUPABASE_ANON_KEY"
```

저장 후 앱을 재부팅합니다. Secrets가 없거나 Supabase가 일시적으로 응답하지
않아도 QA 기능은 계속 작동하며, 해당 이벤트만 기록되지 않습니다.

## 3. 개인정보 보호 구조

- 세션마다 무작위 UUID를 생성하며 계정·쿠키·IP 주소를 앱 코드에서 수집하지 않습니다.
- 이벤트 필드는 코드의 허용 목록으로 제한됩니다.
- 업로드 파일, 원문·번역문, 용어집 내용, 파일명, 이메일은 이벤트에 기록하지 않습니다.
- 정확한 파일 크기 대신 100 KB 미만, 100 KB–1 MB, 1–5 MB, 5–10 MB 구간만 기록합니다.
- 자유 의견은 피드백 테이블에, 선택 이메일은 별도 `interview_opt_ins` 테이블에 저장합니다.
- 익명 사용자는 세 테이블 모두 INSERT만 가능하고 조회·수정·삭제할 수 없습니다.

## 4. 정상 작동 확인

1. 앱 접속 후 `analytics_events`에서 `session_started` 한 건을 확인합니다.
2. XLSX 또는 DOCX/TXT 쌍을 업로드하고 `file_uploaded`를 확인합니다.
3. QA 실행 후 `qa_started`, `qa_completed`와 처리시간·규칙별 개수를 확인합니다.
4. 보고서 다운로드 후 `report_downloaded`를 확인합니다.
5. 피드백 제출 후 `beta_feedback`, `feedback_submitted`를 확인합니다.
6. 이메일 동의 시에만 `interview_opt_ins`에 이메일이 저장되는지 확인합니다.
7. 잘못된 파일을 올려 `qa_failed` 또는 읽기 단계 오류가 익명 유형만 남기는지 확인합니다.
8. 각 이벤트의 `event_data`에 파일명이나 텍스트가 없는지 표본 점검합니다.

## 5. 배포 전 권장 운영 설정

- Supabase Dashboard 계정에 다중 인증을 적용합니다.
- 피드백 보유기간을 정하고 정기적으로 불필요한 자유 의견·이메일을 삭제합니다.
- 공개 베타 개인정보 안내문과 실제 수집 항목이 계속 일치하는지 릴리스마다 확인합니다.
