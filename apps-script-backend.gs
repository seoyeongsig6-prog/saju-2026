/**
 * AXIS AX 조직문화 진단 - 리드 저장 + 결과 이메일 발송용 Google Apps Script
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
 * 이후 진단 완료 후 "진단결과 메일로 받기"를 누르면:
 *  - 이 스프레드시트의 "Leads" 시트에 응답자 정보 + 점수가 한 줄씩 쌓이고 (마케팅 DB 용도),
 *  - 응답자가 입력한 이메일로 진단결과 PDF가 자동으로 발송됩니다.
 */

var SHEET_NAME = 'Leads';

// 진단 결과 이메일을 이 주소로도 참조(BCC)받고 싶다면 이메일 주소를 입력하세요. 필요 없으면 빈 문자열로 둡니다.
var BCC_EMAIL = '';

function doPost(e) {
  var data = JSON.parse(e.postData.contents);

  if (data.type === 'diagnosis') {
    saveLead_(data);
    if (data.email && data.pdfBase64) {
      sendReportEmail_(data);
    }
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

function sendReportEmail_(data) {
  var pdfBlob = Utilities.newBlob(
    Utilities.base64Decode(data.pdfBase64),
    'application/pdf',
    'AXIS_AX조직문화_진단결과서.pdf'
  );

  var body =
    data.name + '님, 안녕하세요.\n\n' +
    'AXIS AX 조직문화 진단 결과서를 첨부파일로 보내드립니다.\n\n' +
    'AX 준비도 점수: ' + data.overallPct + '점 (' + data.level + ')\n\n' +
    '더 자세한 진단과 맞춤 전략이 궁금하시다면 아래 링크에서 상담을 신청해주세요.\n' +
    'http://axisway.co.kr/Contact\n\n' +
    '감사합니다.\nAXIS 드림';

  var options = { attachments: [pdfBlob] };
  if (BCC_EMAIL) options.bcc = BCC_EMAIL;

  MailApp.sendEmail(data.email, '[AXIS] AX 조직문화 진단결과서', body, options);
}
