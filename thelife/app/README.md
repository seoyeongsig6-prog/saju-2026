# 더 노벨리스트 네이티브 앱 출시 안내

이 폴더는 Capacitor 7 기반 iOS/Android 앱입니다. `www/`는 생성물이므로 직접 수정하지 말고
`../web/`을 수정한 뒤 다시 빌드합니다. 패키지 ID는 두 플랫폼 모두 `com.thenovelist.app`, 버전은 1.0.0입니다.

## 출시 빌드에 반드시 필요한 공개 설정

아래 값은 비밀키가 아니지만 실제 계정에서 만든 정확한 값이어야 합니다. 하나라도 없으면
`RELEASE_BUILD=1` 빌드가 의도적으로 중단됩니다.

- `API_BASE`: 운영 HTTPS 서버 주소
- `RC_IOS_KEY`: RevenueCat iOS 공개 SDK 키(`appl_...`)
- `RC_ANDROID_KEY`: RevenueCat Android 공개 SDK 키(`goog_...`)
- `PRODUCT_MASTER`: `novelist.master.monthly`
- `PRODUCT_PRO`: `novelist.pro.monthly`
- `ADMOB_IOS_APP_ID`, `ADMOB_ANDROID_APP_ID`: AdMob 앱 ID(`ca-app-pub-...~...`)
- `ADMOB_IOS_BANNER`, `ADMOB_ANDROID_BANNER`: 배너 광고 단위 ID
- `ADMOB_IOS_INTERSTITIAL`, `ADMOB_ANDROID_INTERSTITIAL`: 전면 광고 단위 ID

광고는 비개인 맞춤 광고(`npa`)로 요청합니다. 소스의 Google 테스트 앱 ID는 개발용이며 출시 빌드
검사에서 거절됩니다.

## 상품 설정

| 표시명 | 상품 ID | 가격 | RevenueCat entitlement |
|---|---|---:|---|
| MASTER | `novelist.master.monthly` | 4,900원/월 | `light` |
| PRO | `novelist.pro.monthly` | 9,900원/월 | `pro` |

`light`는 기존 데이터 호환을 위한 내부 이름일 뿐 화면에는 MASTER로 표시됩니다. 소모성·연간·펜
상품은 만들지 않습니다. RevenueCat Current Offering에 두 월 구독을 넣고, 웹훅 Authorization 값은
서버 `REVENUECAT_WEBHOOK_AUTH`와 같게 설정합니다.

## 빌드 순서

Node.js 22 이상, pnpm, Android Studio, Android SDK 36이 필요합니다. iOS는 macOS의 최신 Xcode와
CocoaPods가 필요합니다.

1. `pnpm install`
2. 위 환경변수를 설정하고 `RELEASE_BUILD=1 pnpm run build:web`
3. `pnpm exec cap sync`
4. Android: `cd android` 후 `./gradlew bundleRelease`
5. iOS: `cd ios/App && pod install`, Xcode에서 App workspace를 열어 Product → Archive

Android 업로드 키는 저장소 밖에 보관하고 Play App Signing을 사용합니다. iOS에서는 본인의 Apple
Developer Team과 배포 인증서를 선택합니다. 키·인증서·프로비저닝 파일은 Git에 넣지 않습니다.

## 출시 전 필수 확인

- Render `/api/health`의 `ready`가 `true`
- 새 설치 → 작품 생성 → 세계관/인물/줄거리 → 직접 집필 → 저장 → 재실행 복구
- FREE/MASTER/PRO 각각 정확한 횟수와 작품 수
- MASTER/PRO 구매, 해지, 만료, 구매 복원
- FREE 광고 표시와 유료 광고 미표시
- 계정 삭제, 개인정보 사본 받기, 기기 변경 복구 코드
- 비행기 모드·서버 오류·AI 한도 오류에서 기존 글이 보존되는지

`APP_AUTH_SECRET`을 운영 후 변경하면 모든 기기 인증·복구 코드가 무효가 되므로 백업 후 고정합니다.
서버 시크릿과 스토어 절차는 `../../docs/STORE_RELEASE.md`를 따릅니다.
