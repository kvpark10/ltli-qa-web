# 단계별 입력과 검사 범위 표시

`/api/qa/prepare`는 action=prepare와 기존 rows/files 계약만 허용한다.
기존 read_rows 검증과 파서를 그대로 사용해 최대5000개 대응 구간을 반환한다.
파일·본문 저장, AI 호출, QA 실행은 하지 않는다. 실제 QA는 사용자의 대응 확인 후 기존 check/assist로 진행한다.
압축해제/텍스트/파일 크기, 동일형식/문단·줄 수 제한은 기존과 같다.
Nginx 속도 제한과 loopback API 서비스는 그대로 유지한다.

화면과 Excel 보고서는 형식·구조 검사이며 의미 정확성·문법·자연스러움을 검사하지 않음을 명시한다.
공통 Excel 출력에 QA Scope 시트를 추가하되 기존 QA Results 시트와 열은 유지한다.

## 배포 순서

1. QA 저장소 갱신 후 tests 통과 확인, ltli-public-qa.service와 ltli-qa.service 재시작.
2. deploy/public-qa-location.conf를 /etc/nginx/snippets/ltli-public-qa-location.conf에 갱신한다.
   정규식에 prepare가 포함되어야 한다. nginx -t 통과 후 reload. 기존 인증은 유지한다.
3. /api/qa/prepare 테스트 후 홈페이지 저장소 갱신/빌드, 이전 out 백업 후 교체.
4. 원문 → 번역문 → 대응 확인 → QA 순서와 Excel QA Scope 시트 확인.
   준비 단계 자체에서는 Gemini가 호출되지 않아야 한다.

복구는 이전 홈페이지 out로 복원할 수 있다. prepare 추가는 기존 엔드포인트와 호환되므로 API를 먼저 제거할 필요는 없다.
기존 분석 제거·관리자 인증·Gemini 실행 한도는 변경하지 않는다.
