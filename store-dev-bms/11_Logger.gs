/**
 * 店舗開発部 業務管理システム - ログユーティリティ
 */

/**
 * ログシートにINFOレベルのログを記録
 * @param {string} message
 */
function logInfo_(message) {
  writeLog_('INFO', message);
}

/**
 * ログシートにERRORレベルのログを記録
 * @param {string} message
 */
function logError_(message) {
  writeLog_('ERROR', message);
  console.error(message);
}

/**
 * ログシートにWARNレベルのログを記録
 * @param {string} message
 */
function logWarn_(message) {
  writeLog_('WARN', message);
  console.warn(message);
}

/**
 * ログをシートに書き込み
 * @param {string} level - INFO/WARN/ERROR
 * @param {string} message
 */
function writeLog_(level, message) {
  try {
    var sheet = getSheet_(SHEET_NAMES.LOG);
    if (!sheet) return;

    var now = Utilities.formatDate(new Date(), 'Asia/Tokyo', 'yyyy-MM-dd HH:mm:ss');
    sheet.appendRow([now, level, message]);

    // ログが1000行を超えたら古いものを削除
    var lastRow = sheet.getLastRow();
    if (lastRow > 1000) {
      sheet.deleteRows(2, lastRow - 500);
    }
  } catch (e) {
    console.error('ログ書き込みエラー: ' + e.message);
  }
}
