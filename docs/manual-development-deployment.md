# 수동 개발·검증·배포
작성: 2026-11-04. 운영 방식: GitHub 버전 관리, 개발자가 명시적으로 검사·빌드·배포.

## 전환 범위와 남은 확인
main의 기존 워크플로는 원문 그대로 `.github/manual-workflows/`에 보관합니다. 이 경로는 Actions 실행 경로가 아닙니다. 테스트·애플리케이션·서비스 설정은 변경하지 않습니다.
**2026-11-04 GitHub Settings → Actions → General에서 Disable actions를 저장·확인했습니다.** 저장소 전체에서 과거 브랜치를 포함한 워크플로 실행이 차단됩니다. Git push와 PR은 계속 사용할 수 있으며 검증·배포는 명시적으로 실행합니다. 새 브랜치는 전환 후 main에서 만들고, 기존 브랜치는 main을 반영하여 보관 전 워크플로가 재도입되지 않도록 합니다.
GitHub 플러그인의 보호 규칙 조회는 403이었으나, 승인된 브라우저 작업에서 Branches와 Rulesets 화면을 확인했습니다. 기존 브랜치 보호 규칙과 Rulesets는 없으며, 제거할 Required Status Checks도 없습니다. 보호 규칙은 변경하지 않았습니다. 최종 API 조회에서 실행·대기 중인 Actions는 각각 0건입니다. Secrets·Variables의 값은 열람하거나 변경하지 않았으며 외부 연동 조사에는 미확인 항목이 남아 있습니다.
트리 조사에서 Dependabot 설정과 재사용 워크플로 호출은 발견되지 않았습니다. GitHub App·외부 서버·계정 수준 자동화는 별도 미확인입니다.
예산 US$5 및 기존 차단 설정은 변경하지 않습니다. 이 문서 변경은 운영 배포가 아닙니다.

## 작업 기록과 Git
```bash
git status --short
git rev-parse HEAD
git diff --check
```
작업 트리가 깨끗한지 확인하고 검사 대상 SHA, UTC 시각, 런타임 버전, 실행 명령, 종료 코드, 실행/실패/건너뜀 수와 사유를 PR 본문 또는 개발 기록에 남깁니다. 고객 파일·키·환경 변수·본문은 기록하지 않습니다.
작은 수정은 관련 테스트, 주요 변경은 기능 전체, 병합 전 영향 범위 통합 검사, 배포 전 아래 전체 필수 검사, 배포 후 health·핵심 기능을 검사합니다. 건너뜀은 통과로 세지 않습니다.
```bash
git switch -c fix/작업명
# 코드 변경 및 명시적 검사 후
git diff --check
git add -- 수정한파일
git commit -m "변경 내용"
git push -u origin HEAD
```
새 작업 브랜치명은 실제 작업명으로 대체합니다. PR에는 수동 검사 기록을 첨부합니다. 중단된 Actions의 필수 검사만 필요한 범위에서 해제하며 다른 보호 기능을 유지합니다.

## 서버 작업 공통 전제
현재 서버에 직접 접속하지 않았으므로 아래는 **저장소·기존 경로에 근거한 절차이며 현 서버에서 실행 검증되지 않았습니다.**
기존 SSH 인증 오류가 해결되고 `git ls-remote origin HEAD`가 성공할 때까지 코드 갱신을 진행하지 않습니다. 키·인증 파일을 변경하거나 출력하지 않습니다.
배포 전 사용자 작업을 저장하고 유지보수 시간을 확보합니다. 검증된 정확한 SHA를 지정하고, 깨끗하지 않은 작업 트리에서는 중단합니다. `git pull`로 임의 최신 버전을 배포하거나 `reset --hard`로 변경을 버리지 않습니다.
운영용 환경변수·비밀파일은 읽거나 로그로 출력하지 않습니다. `systemctl show -p WorkingDirectory -p FragmentPath 서비스명`으로 경로만 확인하고, 실행 Python 버전은 기존 가상환경의 `.venv/bin/python --version`으로 확인합니다.
코드 백업은 기존 커밋 SHA로 보존하고 의존성 버전 목록은 비공개 복구 기록에 저장합니다. 기존 가상환경·런타임도 복구할 수 있는 백업을 별도로 확보합니다. DB·사용자 파일·비밀정보는 코드 백업에 섞지 않습니다. 의존성 복구 수단이 없으면 배포를 중단합니다.
```bash
git status --short
git rev-parse HEAD
git fetch origin
# 배포 SHA가 수동 검증한 커밋인지 대조한 뒤
git switch --detach 검증된전체커밋SHA
```
배포 SHA와 이전 SHA를 별도 기록합니다. 서비스별로 배포하고 실패하면 이전 SHA와 의존성 환경을 함께 복구합니다. 시스템 패키지 설치는 개발/격리 검증 환경에서 수행하며 운영 서버 구성 변경은 이 전환 작업에 포함하지 않습니다.
Nginx 설정·TLS·systemd 자동 재시작·보안·백업·DB는 변경하지 않습니다.

## Actions 복구
먼저 비용·필수 검사 정책을 승인받습니다. 보관 파일을 `.github/workflows/`의 원래 이름으로 이동하고 변경 내용을 검토한 뒤 커밋합니다. 저장소 설정에서 Actions/워크플로를 다시 활성화해야 할 수 있습니다. 한 회만 실행하고 SHA·결과·비용을 확인합니다.
워크플로 복원은 자동 실행을 다시 허용하는 변경이므로 수동 운영 중에는 하지 않습니다.

## QA 개발 검증
Python 3.12(기존 CI 기준), 별도 개발 가상환경에서:
```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m unittest discover -s tests -v
```
Windows에서는 `.venv/Scripts/python.exe`를 사용합니다. 운영 가상환경을 이 명령으로 재생성하지 않습니다.
현재 main에는 unittest 테스트 모듈 9개가 있으며 최근 CI는 **47개 검사 성공**입니다. 과거 pytest 65/Selenium 12 기록과 일치하지 않습니다. 현재 트리에 별도 Selenium 테스트나 pytest 설정은 발견되지 않아 77개 통과로 보고하지 않습니다. 새 패키지·대체 테스트를 임의 도입하지 않습니다.
공개 API·QA 엔진·업로드·알림·보고서 관련 검사는 현 unittest 명령으로 실행합니다. 실제 외부 AI·SMTP·Google 연결 검증은 별도 승인과 비고객 샘플로 수행합니다. 전체 결과·건너뜀을 기록합니다.

## QA 배포·복구
경로: `/home/ubuntu/ltli/ltli-qa-web`. 위 공통 전제로 SHA·의존성 백업 및 검증을 완료합니다.
현 서비스 경로를 대조하고 해당 서비스만 재시작합니다.
```bash
sudo systemctl restart ltli-public-qa
sudo systemctl is-active ltli-public-qa
curl -fsS http://127.0.0.1:8510/api/qa/health
```
내부 QA 변경이 있을 때만 별도로:
```bash
sudo systemctl restart ltli-qa
sudo systemctl is-active ltli-qa
```
공개 홈페이지에서 원문/번역 샘플을 검사하고 경고 상세·Excel 보고서 열기까지 확인합니다. 관리자 화면의 기존 인증도 유지되는지 확인합니다.
실패하면 기록한 이전 SHA로 전환하고 이전 의존성 환경 복구 후 영향받은 서비스만 재시작하고 같은 health·보고서 검증을 반복합니다.
기존 `docs/public-qa-deployment.md`의 초기 설치·Nginx·인증 변경 명령은 이번 운영 방식 전환에 실행하지 않습니다.
