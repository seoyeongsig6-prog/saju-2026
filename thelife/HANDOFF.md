# 더 노벨리스트 인수인계 (판매 앱 기준)

이 브랜치는 과거 The Life 게임이나 AI 장편 대필 앱이 아니라, 스토어에 판매할 **더 노벨리스트**만
서비스합니다. 서버 시작점은 `server.novelist_main:app`, 앱 화면은 `web/writer.html`입니다.

## 제품 경계

- AI 제공: 세계관, 등장인물, 회차별 줄거리, 약 1,000자 본문 예시
- 작가 제공: 실제 본문 직접 집필·수정·저장
- 제공하지 않음: AI 장편 본문 대필, 집필 가이드, 펜/소모성 상품, 숨은 일일 한도
- 플랜: FREE / MASTER(내부 호환키 `light`) / PRO
- 상품: `novelist.master.monthly`, `novelist.pro.monthly` 월 구독 두 개만

플랜 한도는 `server/writer.py`의 `TIERS`가 단일 기준이며, 화면은 `/api/writer/config` 응답만 표시합니다.
FREE/MASTER/PRO 외의 기능 제한을 별도로 추가하지 않습니다.

## 운영 안전장치

- 모든 사용자 API는 X-User-Id와 서버 서명 X-Device-Token을 확인합니다.
- 설치 변경은 설정의 복구 코드로 같은 익명 계정을 복구합니다.
- 이용량 차감은 DB 원자 연산으로 동시 요청 중복 사용을 막습니다.
- 구독은 RevenueCat 서버 재확인과 웹훅으로만 부여합니다.
- 개인정보 사본과 삭제는 모든 플랜에 열려 있고, 작품 `.txt` 내보내기는 MASTER부터입니다.
- `/api/health`가 `ready:true`가 아니면 스토어 빌드를 배포하지 않습니다.

## 수정 전에 반드시 확인

1. `docs/STORE_RELEASE.md`
2. `thelife/app/README.md`
3. `tests/test_release.py`

변경 후 Python 단위 테스트, JavaScript 문법 검사, 웹 번들, Capacitor 동기화, Android AAB 및 iOS Archive를
순서대로 검증합니다. 실제 계정 키와 서명 파일은 저장소에 커밋하지 않습니다.
