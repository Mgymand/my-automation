/**
 * 店舗開発部 業務管理システム - ユーティリティ
 */

/**
 * 指定月の日数を返す
 * @param {number} year
 * @param {number} month - 1始まり
 * @return {number}
 */
function getDaysInMonth_(year, month) {
  return new Date(year, month, 0).getDate();
}

/**
 * 曜日文字列を返す
 * @param {Date} date
 * @return {string}
 */
function getDayOfWeek_(date) {
  var days = ['日', '月', '火', '水', '木', '金', '土'];
  return days[date.getDay()];
}

/**
 * 日付をyyyy-MM-dd形式にフォーマット
 * @param {Date} date
 * @return {string}
 */
function formatDate_(date) {
  return Utilities.formatDate(date, 'Asia/Tokyo', 'yyyy-MM-dd');
}

/**
 * 日付をyyyy年MM月形式にフォーマット
 * @param {Date} date
 * @return {string}
 */
function formatYearMonth_(date) {
  return Utilities.formatDate(date, 'Asia/Tokyo', 'yyyy年MM月');
}

/**
 * HH:mm形式の文字列をDate相対値に変換
 * @param {string} timeStr - "10:00"形式
 * @return {Date|null}
 */
function parseTime_(timeStr) {
  if (!timeStr) return null;
  var parts = String(timeStr).split(':');
  if (parts.length !== 2) return null;
  var d = new Date(1899, 11, 30); // Sheets基準日
  d.setHours(parseInt(parts[0], 10));
  d.setMinutes(parseInt(parts[1], 10));
  return d;
}

/**
 * 今日の日付（時刻なし）を返す
 * @return {Date}
 */
function getToday_() {
  var now = new Date();
  return new Date(now.getFullYear(), now.getMonth(), now.getDate());
}

/**
 * 昨日の日付を返す
 * @return {Date}
 */
function getYesterday_() {
  var today = getToday_();
  today.setDate(today.getDate() - 1);
  return today;
}

/**
 * 指定年月のシート名を生成
 * @param {number} year
 * @param {number} month - 1始まり
 * @return {string}
 */
function getMonthlySheetName_(year, month) {
  var m = ('0' + month).slice(-2);
  return SHEET_NAMES.MONTHLY_PREFIX + year + '年' + m + '月';
}

/**
 * 日報シート名を生成
 * @param {string} memberName
 * @return {string}
 */
function getDailySheetName_(memberName) {
  return SHEET_NAMES.DAILY_PREFIX + memberName;
}

/**
 * 有効メンバー一覧を取得
 * @return {Array<Object>} [{name, email, slackName, slackId, role, sheetName}]
 */
function getActiveMembers_() {
  var sheet = getSheet_(SHEET_NAMES.MEMBER_REGISTRY);
  if (!sheet) return [];

  var lastRow = sheet.getLastRow();
  if (lastRow < 2) return [];

  var data = sheet.getRange(2, 1, lastRow - 1, 8).getValues();
  var members = [];

  for (var i = 0; i < data.length; i++) {
    if (data[i][MEMBER_COLS.STATUS] === '有効') {
      members.push({
        id: data[i][MEMBER_COLS.ID],
        name: data[i][MEMBER_COLS.NAME],
        email: data[i][MEMBER_COLS.EMAIL],
        slackName: data[i][MEMBER_COLS.SLACK_NAME],
        slackId: data[i][MEMBER_COLS.SLACK_ID],
        role: data[i][MEMBER_COLS.ROLE],
        sheetName: data[i][MEMBER_COLS.SHEET_NAME]
      });
    }
  }
  return members;
}

/**
 * スーパーバイザーのみ取得
 * @return {Array<Object>}
 */
function getSupervisors_() {
  return getActiveMembers_().filter(function(m) {
    return m.role === MEMBER_ROLE.SUPERVISOR;
  });
}

/**
 * 日付に対応する日報シートの行番号を返す
 * @param {Date} targetDate
 * @return {number} 行番号（1始まり）、見つからない場合は-1
 */
function getDailyRowForDate_(sheet, targetDate) {
  var lastRow = sheet.getLastRow();
  if (lastRow < DAILY_DATA_START_ROW) return -1;

  var dates = sheet.getRange(DAILY_DATA_START_ROW, 1, lastRow - DAILY_DATA_START_ROW + 1, 1).getValues();
  var targetStr = formatDate_(targetDate);

  for (var i = 0; i < dates.length; i++) {
    if (dates[i][0] instanceof Date && formatDate_(dates[i][0]) === targetStr) {
      return i + DAILY_DATA_START_ROW;
    }
  }
  return -1;
}

/**
 * HTML特殊文字をエスケープ
 * @param {string} str
 * @return {string}
 */
function escapeHtml_(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

/**
 * Slack用テキストエスケープ
 * @param {string} str
 * @return {string}
 */
function escapeSlack_(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}
