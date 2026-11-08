# 公開 QA / 관리자 QA 배포

## 경계

- ltli.ai: 기존 Next.js 정적 사이트에 대화형 QA 화면. 같은 출처 `/api/qa/check`, `/api/qa/report`만 호출.
- 공개 API: `public_api.py`, loopback 8510. `action=qa` 외 요청 거부. 번역/계획/셸/모델 도구 없음.
- qa.ltli.ai: 기존 Streamlit 관리자 화면. Translate와 같은 Nginx Basic Auth 파일 재사용.
- 번역 화면의 기존 관리자 인증은 그대로 유지. 회원 로그인/구독 검증은 아직 연결하지 않으며 유료회원 기능을 실제 제공한다고 표시하지 않는다.

이번 공개 대화는 사전 정의된 QA 작업 안내이다. LLM 자유 대화 또는 의미 평가 Agent는 아니다.
숫자/단위, 누락, 동일 번역, 태그/자리표시자/괄호, URL/이메일/파일명/단축키, 구두점/공백을 기존 qa_engine으로 실행한다.
용어집 업로드는 다음 범위이며 현재 공개 화면에서 광고하지 않는다.

## 검증 환경 → 운영 순서

두 PR을 먼저 검토·병합한다. 운영 루트 경로는 현 서버 설정과 대조한다.
1. 기존 홈페이지 out와 QA 커밋, Nginx 설정을 백업한다. 사용자 작업이 없는 때에 진행한다.
2. QA 저장소를 /home/ubuntu/ltli/ltli-qa-web에 갱신. 기존 .venv에 requirements 설치.
3. `sudo install -m 644 deploy/ltli-public-qa.service /etc/systemd/system/ltli-public-qa.service`
4. `sudo systemctl daemon-reload` 후 `sudo systemctl enable --now ltli-public-qa.service`
5. `curl -fsS http://127.0.0.1:8510/api/qa/health` → {"status":"ok"}.
6. 테스트용 JSON POST로 실제 엔진 확인. 원문/번역문을 로그에 출력하지 않는다.
7. `deploy/public-qa-http.conf`를 /etc/nginx/conf.d/ltli-public-qa.conf에 설치한다(기본 conf.d include가 http 문맥인지 nginx -T로 먼저 확인).
8. `deploy/public-qa-location.conf`를 /etc/nginx/snippets/ltli-public-qa-location.conf에 설치하고,
   기존 /etc/nginx/sites-enabled/ltli-homepage의 **ltli.ai HTTPS server**에 한 줄 추가:
   `include /etc/nginx/snippets/ltli-public-qa-location.conf;`
   다른 server/root/TLS/redirect는 변경하지 않는다. 중복 include하지 않는다.
9. nginx -t 성공 후 reload. 기존 홈페이지를 유지한 채 API 먼저 점검.
10. 홈페이지 저장소에서 npm ci, npm run build. 빌드된 out를 기존 Nginx root로 원자적으로 교체한다.
    실제 root는 현 서버의 ltli-homepage 설정에서 확인해야 하며 여기서 경로를 추정하지 않는다.
11. ltli.ai에서 샘플, XLSX, DOCX/TXT 쌍, 경고 상세, 보고서 다운로드, 모바일 입력을 확인.
12. 새 공개 QA 동작 확인 후 QA 저장소에서 `sudo python3 deploy/protect-qa-admin.py` 실행.
    /etc/nginx/sites-enabled/ltli-qa-public의 HTTPS 블록만 보호하며 인증 파일은 읽거나 변경하지 않는다.
    자동 백업: /var/backups/ltli-nginx. nginx -t 또는 reload 실패 시 설정 복구.
13. `curl -I https://qa.ltli.ai` → 401. 브라우저에서 기존 Translate 관리자 계정 로그인 확인.
    `curl -I https://ltli.ai` → 200. 익명 공개 QA가 계속 동작해야 한다.
    /api/qa/translate 등은 404, action=translate는 403. 관리자 화면 인증을 해제하는 예외 location을 만들지 않는다.

## 보관과 한도

API는 업로드/대화/본문을 디스크·DB·분석 서비스에 저장하지 않는다. 원문·번역문은 처리 메모리에서만 사용한다.
브라우저 새로고침으로 작업 소실. 보고서는 원문·번역문을 포함하므로 공유 전 확인한다.
Nginx proxy_request_buffering off로 요청 임시파일 생성을 피한다. HTTP 본문을 기록하는 별도 프록시 로깅을 도입하지 않는다.
API access log는 비활성화하며 일반 HTTP 운영 오류와 사용자 콘텐츠 수집을 구분한다.
기존 telemetry 모듈은 호환용 no-op으로 변경하여 관리자 앱에서도 외부 이벤트를 전송하지 않는다.
최대 파일당10MiB, 압축해제50MiB,2000ZIP항목,5000구간,구간별20000자/합계100만자.
동시 처리2개, IP당6요청/분(burst3), 연결2개. API key/Gemini 환경 변수 불필요.
XLSX 첫 시트 Source/Target 열, DOCX 본문 일반 문단(표/머리말 제외), TXT 비어 있지 않은 줄을 순서대로 대응.
원본 파일을 수정하지 않는다. 구간 수가 같아도 의미 대응은 사람이 확인해야 한다.

## 복구

- 새 API가 실패하면 홈페이지의 이전 out로 복원하고 API location include를 제거한 뒤 nginx -t/reload.
- API 서비스를 stop/disable하면 공개 QA는 일시 이용 불가로 표시하며 가짜 결과를 만들지 않는다.
- qa.ltli.ai 관리자 인증은 원칙적으로 유지한다. 설정 문제일 때만 /var/backups/ltli-nginx 백업으로 복구.
- 기존 Streamlit QA 회귀 발생 시 이전 커밋으로 되돌리고 기존 QA 서비스를 재시작.
- DB 마이그레이션, 유료 번역 API 공개, 원본 문서 마이그레이션은 없다.

## 다국어 XLSX 배포 확인

- API와 Streamlit을 갱신한 다음 해당 릴리스의 정적 웹을 반영한다. 공개 보고서 API는 `report_language`가 없으면 HTTP 400을 반환한다. 이전 탭은 새로고침해야 한다.
- 공개 URL에서 받은 HTML이 배포한 빌드의 스크립트 경로를 참조하는지 확인한다. HTML은 Nginx와 CDN에서 재검증되도록 설정하고 버전이 포함된 `/_next/static/` 자산에는 기존 캐시 정책을 적용한다. 이전 탭의 자산이 필요할 수 있으므로 배포 즉시 삭제하지 않는다.
- 익명 `ltli.ai`와 인증 후 `qa.ltli.ai`에서 **繁體中文**을 선택한다. 두 사이트에서 새 샘플을 검사한다. Streamlit에서는 샘플 XLSX를 받아 다시 업로드한다.
- 실제로 내려받은 `LTLI-QA-report-zh-TW.xlsx`를 열어 검사 요약, 결과, 경고 상세 시트의 제목·열·범위 안내·설명이 번체인지 확인한다. 새 샘플은 영어 원문과 번체 번역문이어야 한다. 기존 업로드 문서는 UI 언어를 바꿔 다시 내려받아도 원문·번역문이 그대로인지 확인한다.
- 공개 사이트의 샘플 및 보고서 응답에서 `Content-Language: zh-TW`와 `Cache-Control: no-store`를 확인한다. 홈의 HTTP 200과 서비스 health는 위 다운로드 검증을 대체하지 않는다.
