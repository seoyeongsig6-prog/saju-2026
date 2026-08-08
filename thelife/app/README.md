# 더 노벨리스트 — 앱 출시 가이드 (App Store · Google Play)

이 폴더(`thelife/app`)는 웹앱을 감싸 **진짜 앱**으로 만드는 껍데기(Capacitor)와
**인앱 결제(RevenueCat)** 연결이 들어 있습니다. 웹 화면(`../web`)을 그대로 앱 안에
넣고, 결제만 네이티브로 붙입니다. 웹을 고치면 앱도 같이 바뀝니다(재빌드만 하면 됨).

> 서버 코드는 이미 준비돼 있습니다. 이 문서는 **당신 컴퓨터에서만 할 수 있는 일**
> (맥 + Xcode, 안드로이드 스튜디오, 스토어 계정)을 순서대로 안내합니다.

---

## 0. 미리 필요한 것 (돈/계정)

| 항목 | 용도 | 비용 |
|---|---|---|
| **맥(Mac) + Xcode** | iOS 빌드·제출 (애플은 맥이 반드시 필요) | 보유 시 무료 |
| **Android Studio** | 안드로이드 빌드 | 무료 |
| **Apple Developer** | App Store 출시 | 연 $99 |
| **Google Play Developer** | Play 출시 | 최초 1회 $25 |
| **RevenueCat** | 인앱 결제 연결·영수증 검증 | 무료(월 매출 일정액까지) |

안드로이드만 먼저 낼 수도 있습니다(맥 없이 가능). iOS는 맥이 있어야 합니다.

---

## 1. 설정값 채우기 (제일 중요)

빌드는 아래 값들을 환경변수로 받습니다. 값이 없으면 placeholder로 빌드되고 결제가 안 됩니다.

| 환경변수 | 뜻 | 예시 |
|---|---|---|
| `API_BASE` | 배포된 백엔드 주소 | `https://thelife.onrender.com` |
| `RC_IOS_KEY` | RevenueCat **iOS 공개** SDK 키 | `appl_xxxxx` |
| `RC_ANDROID_KEY` | RevenueCat **Android 공개** SDK 키 | `goog_xxxxx` |
| `PRODUCT_LIGHT` | 라이트 구독 상품 ID | `novelist.light.monthly` |
| `PRODUCT_PRO` | 프로 구독 상품 ID | `novelist.pro.monthly` |

`capacitor.config.json` 의 `appId`(`com.thenovelist.app`)와 `appName`(`더 노벨리스트`)도
**당신 소유의 값**으로 바꾸세요. appId는 스토어에서 앱을 식별하는 고유값입니다.

---

## 2. 빌드 & 네이티브 프로젝트 생성

```bash
cd thelife/app
npm install

# 설정값을 넣어 웹 자산을 www/ 로 굽는다
API_BASE="https://당신-백엔드" \
RC_IOS_KEY="appl_..." RC_ANDROID_KEY="goog_..." \
PRODUCT_LIGHT="novelist.light.monthly" PRODUCT_PRO="novelist.pro.monthly" \
npm run build:web

# 네이티브 프로젝트 추가 (한 번만)
npm run add:android      # 안드로이드
npm run add:ios          # iOS (맥에서만)

# 이후 웹을 고칠 때마다
npm run sync             # build:web + cap sync
```

아이콘/스플래시는 `@capacitor/assets`로 한 번에 생성할 수 있습니다:
```bash
npm i -D @capacitor/assets
# 1024x1024 아이콘을 assets/icon.png 로 두고
npx capacitor-assets generate
```

---

## 3. RevenueCat 설정 (결제의 핵심)

1. [RevenueCat](https://www.revenuecat.com) 가입 → **프로젝트 생성**.
2. 프로젝트에 **iOS 앱, Android 앱** 추가 → 각 **공개 SDK 키**를 위 `RC_IOS_KEY`,
   `RC_ANDROID_KEY` 에 넣는다.
3. **Entitlements** 를 서버 tier 이름과 **똑같이** 만든다: `light`, `pro`.
   (서버가 이 이름으로 등급을 판단합니다 — 철자 반드시 일치)
4. **Products** 에 위 상품 ID(`novelist.light.monthly`, `novelist.pro.monthly`)를 등록하고
   각각 `light` / `pro` entitlement 에 연결.
5. **Offerings** → 기본(current) offering 에 두 상품을 패키지로 넣는다.
6. **Webhooks** → URL 을 `https://당신-백엔드/api/writer/rc-webhook` 로,
   Authorization 헤더 값을 아무 긴 임의문자열로 정한다 → 그 값을 서버 환경변수
   `REVENUECAT_WEBHOOK_AUTH` 에 동일하게 넣는다.
7. **API keys → Secret key(v1)** 를 복사 → 서버 환경변수 `REVENUECAT_SECRET` 에 넣는다.

---

## 4. 스토어에 구독 상품 만들기

두 스토어 모두 RevenueCat 에 등록한 **상품 ID와 똑같이** 만들어야 합니다.

- **App Store Connect** → 앱 → 구독 → 그룹 생성 → 자동 갱신 구독 2개
  (`novelist.light.monthly` ₩4,900/월, `novelist.pro.monthly` ₩9,900/월).
  구독 화면에 **약관(EULA)·개인정보처리방침 링크**와 가격/기간이 보여야 심사 통과.
- **Google Play Console** → 수익 창출 → 구독 → 동일 ID 2개 생성.

앱 안에는 이미 다음이 들어 있습니다(심사 필수 항목):
- 플랜 화면의 가격·기간·자동갱신 고지, **구매 복원** 버튼, 약관/개인정보 링크
- 계정 데이터 **내보내기 / 삭제**(설정 화면)

---

## 5. 서버 환경변수 (Render)

Render 대시보드 → Environment 에 추가:

| 키 | 값 |
|---|---|
| `DATABASE_URL` | Neon 등 PostgreSQL 주소 **(데이터 영구 보관 — 필수)** |
| `REVENUECAT_SECRET` | RevenueCat v1 시크릿 키 |
| `REVENUECAT_WEBHOOK_AUTH` | 3단계 6번에서 정한 임의문자열 |
| `WRITER_LAUNCH_MODE` | 판매용 빌드면 `1` (소설 본문 집필 숨김) |

`REVENUECAT_SECRET` 가 없으면 결제는 안전하게 거부됩니다(가짜 결제 방지).

---

## 6. 데이터가 사라지지 않게 (가장 중요)

- 이용자 데이터(작품·회차)는 **DB에** 저장됩니다. `DATABASE_URL`(PostgreSQL)이
  연결돼 있으면 앱 업데이트·서버 재배포·수면 어떤 경우에도 **유지**됩니다.
  SQLite만 쓰면 Render 무료 서버 재배포 시 초기화되니 반드시 `DATABASE_URL` 을 붙이세요.
- 이제 **어떤 수정도 이미 쓴 회차 본문을 자동으로 바꾸지 않습니다.** (이름 일괄변경 기능 제거)
  표기 변경은 '고유명사 사전'에 등록 → **다음 회차부터만** 반영됩니다.
- 'AI 다시 쓰기'는 덮어쓰기 전에 이전 글을 자동 백업하고 **되돌리기**를 제공합니다.
- 상태 점검: `https://당신-백엔드/api/health` → `db.using` 이 `postgres` 인지 확인.

---

## 7. 제출

- **iOS**: `npm run open:ios` → Xcode 에서 서명(당신 팀) → Archive → App Store Connect 업로드 → 심사 제출.
- **Android**: `npm run open:android` → Android Studio 에서 서명된 AAB 빌드 → Play Console 업로드 → 심사 제출.

### 심사에서 자주 막히는 것 (미리 대비됨)
- *가격만 보이고 결제 안 됨* → 3~4단계로 실제 결제가 붙으면 해결.
- *webview 껍데기(애플 4.2)* → 네이티브 결제 + 스플래시/상태바 네이티브 기능으로 대비.
- *구매 복원 없음* → 플랜 화면 '구매 복원' 버튼으로 대비.
- *계정 삭제 없음* → 설정 화면 데이터 삭제로 대비.
