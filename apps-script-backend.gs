/**
 * AXIS AX 조직문화 진단 - 리드(고객정보+점수) 저장용 Google Apps Script
 *
 * 설치 방법 (코드를 몰라도 순서대로만 따라하면 됩니다):
 * 1. sheets.google.com 에서 새 스프레드시트를 만든다 (이름은 자유롭게, 예: "AXIS AX진단 리드").
 * 2. 상단 메뉴 확장 프로그램(Extensions) > Apps Script 클릭.
 * 3. 편집기에 기본으로 있던 코드를 전부 지우고, 이 파일 내용을 전부 붙여넣는다.
 * 4. 저장(Ctrl+S 또는 플로피 디스크 아이콘).
 * 5. 우측 상단 "배포(Deploy)" > "새 배포(New deployment)" 클릭.
 * 6. 유형 선택에서 톱니바퀴 아이콘 클릭 > "웹 앱(Web app)" 선택.
 * 7. "실행 계정"은 "나(Me)", "액세스 권한이 있는 사용자"는 "모든 사용자(Anyone)"로 설정.
 * 8. "배포" 클릭 → 권한 요청 화면이 뜨면 본인 계정으로 승인
 *    ("Google에서 확인하지 않은 앱" 경고가 떠도 내가 만든 스크립트이므로 "고급" > "이동"을 눌러 계속 진행).
 * 9. 배포가 끝나면 나오는 "웹 앱 URL"을 복사한다.
 * 10. index.html 안의 CONFIG.SUBMIT_ENDPOINT_URL 값을 그 URL로 바꾼다.
 *
 * 이미 배포한 뒤 이 코드를 다시 바꿨다면, 코드만 저장해서는 반영되지 않습니다.
 * "배포(Deploy)" > "배포 관리(Manage deployments)" > 연필(수정) 아이콘 > 버전을 "새 버전"으로
 * 선택 > "배포"를 다시 눌러야 실제 웹 앱에 반영됩니다 (URL은 그대로 유지됩니다).
 *
 * 이후 진단 완료 후 "진단 결과 다운로드"를 누르면:
 *  - 고객은 결과서 PDF를 자신의 브라우저로 바로 다운로드 받고,
 *  - 이 스프레드시트의 "Leads" 시트에는 응답자 정보 + 점수가 한 줄씩 쌓입니다 (마케팅 DB 용도).
 *  - 고객에게 이메일은 발송되지 않습니다.
 */

var SHEET_NAME = 'Leads';

function doPost(e) {
  var data = JSON.parse(e.postData.contents);

  if (data.type === 'diagnosis') {
    saveLead_(data);
  }

  return ContentService
    .createTextOutput(JSON.stringify({ ok: true }))
    .setMimeType(ContentService.MimeType.JSON);
}

function saveLead_(data) {
  var sheet = getSheet_();
  sheet.appendRow([
    new Date(),
    data.name || '',
    data.company || '',
    data.email || '',
    data.phone || '',
    data.overallPct || '',
    data.level || '',
    JSON.stringify(data.dimScores || {})
  ]);
}

function getSheet_() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sheet = ss.getSheetByName(SHEET_NAME);
  if (!sheet) {
    sheet = ss.insertSheet(SHEET_NAME);
    sheet.appendRow(['제출일시', '이름', '회사명', '이메일', '연락처', 'AX 준비도 점수', '단계', '영역별 점수(JSON)']);
  }
  return sheet;
}
