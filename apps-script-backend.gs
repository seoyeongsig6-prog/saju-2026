/**
 * AXIS AX 조직문화 진단 툴킷 - 백엔드 (Google Apps Script)
 *
 * 이 코드는 axis-ax-diagnostic.html 에서 fetch(POST)로 전송하는 데이터를
 * 1) 구글 시트에 행으로 저장하고
 * 2) 담당자 이메일로 알림을 발송합니다.
 *
 * 설치 방법은 EMAIL_SETUP.md 를 참고하세요.
 */

// TODO: 결과 알림을 받을 실제 담당자 이메일 주소로 변경하세요.
var NOTIFY_EMAIL = 'REPLACE_WITH_AXIS_TEAM_EMAIL@yourdomain.com';

function doPost(e) {
  var data = JSON.parse(e.postData.contents);

  if (data.type === 'consult_request') {
    saveConsultRequest(data);
    sendConsultEmail(data);
  } else {
    saveDiagnosis(data);
    sendDiagnosisEmail(data);
  }

  return ContentService
    .createTextOutput(JSON.stringify({ ok: true }))
    .setMimeType(ContentService.MimeType.JSON);
}

function getSheet(name, headers) {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sheet = ss.getSheetByName(name);
  if (!sheet) {
    sheet = ss.insertSheet(name);
    sheet.appendRow(headers);
  }
  return sheet;
}

function saveDiagnosis(data) {
  var sheet = getSheet('AX진단_리드', [
    '제출시각', '이름', '회사명/직책', '회사이메일', '연락처',
    '종합점수', '등급', '영역별점수(JSON)'
  ]);
  sheet.appendRow([
    new Date(),
    data.name,
    data.company,
    data.email,
    data.phone,
    data.overallPct,
    data.level,
    JSON.stringify(data.dimScores)
  ]);
}

function saveConsultRequest(data) {
  var sheet = getSheet('상담신청', [
    '제출시각', '이름', '회사명', '연락처/이메일', '문의내용'
  ]);
  sheet.appendRow([
    new Date(),
    data.name,
    data.company,
    data.contact,
    data.message
  ]);
}

function sendDiagnosisEmail(data) {
  var dimLines = Object.keys(data.dimScores || {})
    .map(function (k) { return '- ' + k + ': ' + data.dimScores[k] + ' / 5'; })
    .join('\n');

  var body =
    'AX 조직문화 진단 신규 응답이 접수되었습니다.\n\n' +
    '이름: ' + data.name + '\n' +
    '회사명/직책: ' + data.company + '\n' +
    '회사 이메일: ' + data.email + '\n' +
    '연락처: ' + data.phone + '\n\n' +
    '종합 점수: ' + data.overallPct + '점 (' + data.level + ')\n\n' +
    '영역별 점수:\n' + dimLines;

  MailApp.sendEmail(NOTIFY_EMAIL, '[AX 진단] 신규 응답 - ' + data.company, body);
}

function sendConsultEmail(data) {
  var body =
    '무료 상담 신청이 접수되었습니다.\n\n' +
    '이름: ' + data.name + '\n' +
    '회사명: ' + data.company + '\n' +
    '연락처/이메일: ' + data.contact + '\n\n' +
    '문의 내용:\n' + (data.message || '(없음)');

  MailApp.sendEmail(NOTIFY_EMAIL, '[AX 진단] 상담 신청 - ' + data.company, body);
}
