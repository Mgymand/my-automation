/**
 * 店舗開発部 業務管理システム - メンバー管理
 */

/**
 * メンバー一覧から全有効メンバーの日報シートを一括生成
 */
function batchCreateMemberSheets() {
  var members = getActiveMembers_();
  if (members.length === 0) {
    SpreadsheetApp.getUi().alert('有効なメンバーが登録されていません。\nメンバー一覧シートにメンバーを登録してください。');
    return;
  }

  var ss = getSpreadsheet_();
  var now = new Date();
  var year = now.getFullYear();
  var month = now.getMonth() + 1;
  var created = 0;

  for (var i = 0; i < members.length; i++) {
    var sheetName = getDailySheetName_(members[i].name);
    if (!ss.getSheetByName(sheetName)) {
      createDailyReportSheet_(ss, members[i].name, year, month);
      created++;
    }
    // メンバー一覧のシート名列を更新
    updateMemberSheetName_(members[i].id, sheetName);
  }

  // 月次目標シートも生成
  var monthlyName = getMonthlySheetName_(year, month);
  if (!ss.getSheetByName(monthlyName)) {
    createMonthlyGoalSheet_(ss, year, month, members);
  }

  logInfo_(created + '名分の日報シートを生成しました');
  SpreadsheetApp.getUi().alert(created + '名分の日報シートを新規作成しました。');
}

/**
 * メンバー一覧のシート名列を更新
 * @param {number} memberId
 * @param {string} sheetName
 */
function updateMemberSheetName_(memberId, sheetName) {
  var sheet = getSheet_(SHEET_NAMES.MEMBER_REGISTRY);
  if (!sheet) return;

  var lastRow = sheet.getLastRow();
  if (lastRow < 2) return;

  var ids = sheet.getRange(2, 1, lastRow - 1, 1).getValues();
  for (var i = 0; i < ids.length; i++) {
    if (ids[i][0] === memberId) {
      sheet.getRange(i + 2, MEMBER_COLS.SHEET_NAME + 1).setValue(sheetName);
      return;
    }
  }
}

/**
 * メンバーを追加（プログラムから）
 * @param {string} name
 * @param {string} email
 * @param {string} slackName
 * @param {string} slackId
 * @param {string} role
 */
function addMember_(name, email, slackName, slackId, role) {
  var sheet = getSheet_(SHEET_NAMES.MEMBER_REGISTRY);
  if (!sheet) return;

  var lastRow = sheet.getLastRow();
  var newId = lastRow; // 簡易的なID割当

  var sheetName = getDailySheetName_(name);
  sheet.appendRow([newId, name, email, slackName, slackId, role || MEMBER_ROLE.GENERAL, sheetName, '有効']);

  // 日報シートも作成
  var now = new Date();
  createDailyReportSheet_(getSpreadsheet_(), name, now.getFullYear(), now.getMonth() + 1);

  logInfo_('メンバー追加: ' + name);
}
