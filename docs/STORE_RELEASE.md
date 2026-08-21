# 더 노벨리스트 1.0 — 스토어 제출 체크리스트

## 1. 출시 구성

- 앱 이름: 더 노벨리스트 / The Novelist
- Bundle ID·Application ID: `com.thenovelist.app`
- 버전: 1.0.0, Android versionCode 1, iOS build 1
- Android target/compile SDK: 36
- 최소 OS: Android 6(API 23), iOS 14
- 카메라·마이크·위치 권한 없음
- 서버 API 문서 비공개, HTTPS 강제, 기기 서명 인증, 원자적 이용량 차감
- AI: Google Gemini `gemini-3.6-flash`(GA), 장애 시 `gemini-3.7-flash`(GA)

## 2. Render 운영 환경변수

필수:

- `DATABASE_URL`: 영구 Postgres 주소
- `GEMINI_API_KEY`: 더 노벨리스트 전용 Google Cloud 프로젝트 키
- `LLM_PROVIDER=gemini`
- `GEMINI_MODEL=gemini-3.6-flash`
- `WRITER_LAUNCH_MODE=1`
- `APP_AUTH_SECRET`: Render 자동 생성값. 출시 후 변경 금지
- `REVENUECAT_SECRET`: RevenueCat secret API key
- `REVENUECAT_WEBHOOK_AUTH`: 길고 무작위인 웹훅 공유 비밀

운영 전용:

- `ADMIN_SECRET`: 개인 테스트 화면용 비밀. 일반 URL이나 앱에 넣지 않음
- `NOVELIST_DEMO_MODE=0`

Render는 무료가 아닌 상시 실행 플랜을 사용합니다. `/api/health`에서 `ready:true`,
`database:postgres`, `ai_connected:true`, `auth_configured:true`를 확인한 뒤 제출합니다.

## 3. Apple App Store Connect

1. Bundle ID와 앱을 생성하고 iOS 앱을 RevenueCat에 연결합니다.
2. 구독 그룹 하나에 MASTER/PRO 월 구독을 만들고 4,900원/9,900원으로 설정합니다.
3. 구독 화면 스크린샷, 설명, 개인정보처리방침 URL, 이용약관 URL을 입력합니다.
4. App Privacy에 사용자 ID, 사용자 콘텐츠, 구매 항목, 광고 데이터 처리를 신고합니다.
5. 연령 등급은 사용자 작성 소설과 AI 생성 가능성을 고려해 답합니다.
6. Xcode에서 본인 Team을 선택하고 Archive → Validate App → Distribute App을 실행합니다.

## 4. Google Play Console

1. Play App Signing을 사용하고 서명된 AAB를 내부 테스트 트랙에 먼저 올립니다.
2. MASTER/PRO 월 구독과 기본 요금제를 만든 후 RevenueCat에 연결합니다.
3. Data safety에 사용자 콘텐츠, 기기 식별값, 구매, 광고 SDK 처리와 삭제 기능을 신고합니다.
4. 개인정보처리방침 공개 URL은 `/privacy`, 계정·데이터 삭제 URL은 `/delete-account`를 입력합니다.
5. 콘텐츠 등급, 광고 포함, 타깃 연령(만 14세 미만 대상 아님)을 표시합니다.
6. 내부 테스트 → 비공개 테스트 → 프로덕션 순으로 승격합니다.

## 5. 계정에서 사람이 넣어야 하는 값

코드로 대신 만들 수 없는 항목입니다: Apple/Google 법적 판매자 정보, 세금·은행 계약, 서명 인증서,
Android 업로드 키, RevenueCat 키, AdMob 앱·광고 단위 ID, 스토어 스크린샷, 지원 URL과 최종
개인정보처리방침 URL. 모두 입력하기 전에는 제출하지 않습니다.

## 6. 운영과 롤백

- Postgres 자동 백업과 실제 복구 시험을 먼저 합니다.
- 오류율, AI 429/5xx, 결제 웹훅 실패 알림을 설정합니다.
- Gemini 비용 예산 알림은 설정하되 약속한 플랜 한도를 임의로 바꾸지 않습니다.
- 장애 배포는 이전 Render 커밋으로 롤백합니다.
