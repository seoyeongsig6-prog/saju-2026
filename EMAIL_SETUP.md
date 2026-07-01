# 진단 결과 이메일 발송 / 데이터 저장 연동 설정

`axis-ax-diagnostic.html`은 정적 페이지라 자체적으로 이메일을 보내거나 데이터를 저장할 수 없습니다.
아래 단계대로 Google Apps Script를 5분 정도 설정하면, 진단 결과와 상담 신청이 **구글 시트에 자동 저장**되고
**담당자 이메일로 알림**이 발송됩니다.

## 1. 구글 시트 만들기
1. Google Drive에서 새 스프레드시트를 만듭니다. (예: `AXIS 진단 리드`)
2. 상단 메뉴 `확장 프로그램 > Apps Script`를 클릭합니다.

## 2. 백엔드 코드 붙여넣기
1. 열린 Apps Script 편집기에서 기본 코드를 모두 지웁니다.
2. 이 저장소의 `apps-script-backend.gs` 파일 내용을 전부 복사해 붙여넣습니다.
3. 코드 상단의 `NOTIFY_EMAIL` 값을 실제 알림을 받을 회사 이메일 주소로 바꿉니다.
   ```js
   var NOTIFY_EMAIL = 'contact@axis-company.com';
   ```

## 3. 웹 앱으로 배포
1. 우측 상단 `배포 > 새 배포`를 클릭합니다.
2. 유형 선택에서 `웹 앱`을 선택합니다.
3. "실행 사용자"는 `나`, "액세스 권한"은 `모든 사용자`로 설정합니다. (익명 방문자가 폼을 제출할 수 있어야 하므로 필요합니다)
4. 배포를 누르면 `https://script.google.com/macros/s/xxxxxxx/exec` 형태의 웹 앱 URL이 발급됩니다.
5. 최초 배포 시 Google 권한 승인 화면이 나오면 본인 계정으로 승인합니다.

## 4. HTML에 URL 연결
`axis-ax-diagnostic.html` 상단 `<script>` 안의 `CONFIG` 값을 아래처럼 바꿉니다.

```js
const CONFIG = {
  SUBMIT_ENDPOINT_URL: 'https://script.google.com/macros/s/xxxxxxx/exec'
};
```

## 5. 확인
1. 브라우저에서 `axis-ax-diagnostic.html`을 열고 진단을 끝까지 진행합니다.
2. 연결된 구글 시트에 `AX진단_리드` 탭이 생기고 응답 행이 추가되는지 확인합니다.
3. `NOTIFY_EMAIL`로 알림 메일이 도착하는지 확인합니다.
4. 하단 "무료 상담 신청" 폼도 같은 방식으로 `상담신청` 탭에 저장되고 이메일이 발송됩니다.

## 참고
- 코드를 수정한 뒤에는 `배포 > 배포 관리`에서 기존 배포를 `수정`하고 새 버전으로 다시 배포해야 반영됩니다.
- 진단 페이지의 회사 이메일 입력란은 네이버/지메일 등 개인 이메일 도메인을 자동으로 거부합니다. 허용되지 않는 도메인을 추가/제거하려면 `axis-ax-diagnostic.html`의 `FREE_EMAIL_DOMAINS` 배열을 수정하세요.
