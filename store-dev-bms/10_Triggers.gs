/**
 * 店舗開発部 業務管理システム - トリガー管理
 */

/**
 * 全トリガーを設定
 */
function setupAllTriggers() {
  // 既存トリガーを削除してから再設定
  removeAllTriggers();

  var ss = getSpreadsheet_();

  // 1. 毎日 10:00 - 日次サマリー投稿 + エスカレーション
  ScriptApp.newTrigger('postDailySummaries')
    .timeBased()
    .atHour(10)
    .everyDays(1)
    .create();

  // 2. 毎日 10:05 - 未記入チェックリマインド
  ScriptApp.newTrigger('checkEmptyImpressions')
    .timeBased()
    .atHour(10)
    .nearMinute(5)
    .everyDays(1)
    .create();

  // 3. 毎日 10:10 - エスカレーション（2日連続未記入→上司）
  ScriptApp.newTrigger('escalateToSupervisor')
    .timeBased()
    .atHour(10)
    .nearMinute(10)
    .everyDays(1)
    .create();

  // 4. 毎日 18:00 - SVコメント未記入リマインド
  ScriptApp.newTrigger('remindSupervisorComments')
    .timeBased()
    .atHour(18)
    .everyDays(1)
    .create();

  // 5. 毎月1日 0:00 - 翌月シート準備
  ScriptApp.newTrigger('generateCurrentMonthSheets')
    .timeBased()
    .onMonthDay(1)
    .atHour(0)
    .create();

  // 6. 毎月1日 0:30 - 月次目標シート生成
  ScriptApp.newTrigger('generateCurrentMonthlyGoalSheet')
    .timeBased()
    .onMonthDay(1)
    .atHour(0)
    .nearMinute(30)
    .create();

  // 7. 毎月28日 22:00 - 月次AI評価実行
  ScriptApp.newTrigger('runMonthlyEvaluations')
    .timeBased()
    .onMonthDay(28)
    .atHour(22)
    .create();

  // 8. 6時間ごと - タスク期限チェック
  ScriptApp.newTrigger('checkTaskDeadlines')
    .timeBased()
    .everyHours(6)
    .create();

  // 9. 毎日 3:00 - メンテナンス（ログクリーンアップ等）
  ScriptApp.newTrigger('dailyMaintenance')
    .timeBased()
    .atHour(3)
    .everyDays(1)
    .create();

  // 10. onEdit トリガー（タスクステータス変更検知）
  ScriptApp.newTrigger('onEditTrigger')
    .forSpreadsheet(ss)
    .onEdit()
    .create();

  logInfo_('全トリガーを設定しました（10個）');
  SpreadsheetApp.getUi().alert('全トリガーを設定しました。');
}

/**
 * 全トリガーを削除
 */
function removeAllTriggers() {
  var triggers = ScriptApp.getProjectTriggers();
  for (var i = 0; i < triggers.length; i++) {
    ScriptApp.deleteTrigger(triggers[i]);
  }
  logInfo_('全トリガーを削除しました（' + triggers.length + '個）');
}

/**
 * onEditトリガーハンドラ
 * @param {Object} e - 編集イベント
 */
function onEditTrigger(e) {
  if (!e) return;

  var sheet = e.source.getActiveSheet();
  var sheetName = sheet.getName();
  var range = e.range;

  // タスク管理シートのステータス変更を検知
  if (sheetName === SHEET_NAMES.TASK) {
    handleTaskStatusChange_(sheet, range, e.value, e.oldValue);
  }
}

/**
 * タスクステータス変更を処理
 */
function handleTaskStatusChange_(sheet, range, newValue, oldValue) {
  var col = range.getColumn();
  var row = range.getRow();

  // ステータス列（H列 = 8）の変更のみ
  if (col !== TASK_COLS.STATUS + 1 || row < 2) return;

  var taskId = sheet.getRange(row, TASK_COLS.TASK_ID + 1).getValue();
  var assignee = sheet.getRange(row, TASK_COLS.ASSIGNEE + 1).getValue();

  // 完了に変更された場合
  if (newValue === TASK_STATUS.DONE) {
    sheet.getRange(row, TASK_COLS.COMPLETED_DATE + 1).setValue(new Date());

    // Slack通知
    var webhookUrl = getPropertySafe_(PROP_KEYS.SLACK_WEBHOOK_TASKS);
    if (webhookUrl) {
      var content = sheet.getRange(row, TASK_COLS.CONTENT + 1).getValue();
      sendSlackWebhook_(webhookUrl,
        ':white_check_mark: *タスク完了*\n> ' + taskId + ' | ' + assignee + ' | ' + escapeSlack_(String(content))
      );
    }
  }

  logInfo_('タスクステータス変更: ' + taskId + ' (' + oldValue + ' → ' + newValue + ')');
}

/**
 * 日次メンテナンス
 * トリガー: 毎日 3:00
 */
function dailyMaintenance() {
  // ログシートの古いログを削除（500行以上の場合）
  var logSheet = getSheet_(SHEET_NAMES.LOG);
  if (logSheet) {
    var lastRow = logSheet.getLastRow();
    if (lastRow > 500) {
      logSheet.deleteRows(2, lastRow - 300);
      logInfo_('ログクリーンアップ: ' + (lastRow - 300) + '行削除');
    }
  }

  logInfo_('日次メンテナンス完了');
}
