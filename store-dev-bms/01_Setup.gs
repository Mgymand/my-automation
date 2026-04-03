/**
 * 店舗開発部 業務管理システム - 初期セットアップ
 */

/**
 * スプレッドシート起動時にカスタムメニューを表示
 */
function onOpen() {
  var ui = SpreadsheetApp.getUi();
  ui.createMenu('業務管理システム')
    .addItem('初期セットアップ', 'initialSetup')
    .addSeparator()
    .addSubMenu(ui.createMenu('日報')
      .addItem('今日のカレンダーを同期', 'syncCalendarForToday')
      .addItem('今月のシートを生成', 'generateCurrentMonthSheets'))
    .addSubMenu(ui.createMenu('タスク')
      .addItem('タスクを新規登録', 'showTaskInputDialog')
      .addItem('期限切れタスクをチェック', 'checkTaskDeadlines'))
    .addSubMenu(ui.createMenu('月次評価')
      .addItem('月次評価を実行', 'runMonthlyEvaluations')
      .addItem('月次目標シートを生成', 'generateCurrentMonthlyGoalSheet'))
    .addSubMenu(ui.createMenu('管理')
      .addItem('メンバーシート一括生成', 'batchCreateMemberSheets')
      .addItem('トリガー設定', 'setupAllTriggers')
      .addItem('トリガー全削除', 'removeAllTriggers')
      .addItem('API設定', 'showApiSettingsDialog'))
    .addToUi();
}

/**
 * 初期セットアップ：全システムシートを作成
 */
function initialSetup() {
  var ss = getSpreadsheet_();
  var ui = SpreadsheetApp.getUi();

  var result = ui.alert(
    '初期セットアップ',
    'システムシート（設定・メンバー一覧・タスク管理・ログ）を作成します。\n既存シートは上書きされません。',
    ui.ButtonSet.OK_CANCEL
  );
  if (result !== ui.Button.OK) return;

  // 設定シート作成
  createSettingsSheet_(ss);
  // メンバー一覧シート作成
  createMemberRegistrySheet_(ss);
  // タスク管理シート作成
  createTaskSheet_(ss);
  // ログシート作成
  createLogSheet_(ss);

  logInfo_('初期セットアップ完了');
  ui.alert('初期セットアップが完了しました。\nメンバー一覧を入力後、「メンバーシート一括生成」を実行してください。');
}

/**
 * 設定シートを作成
 */
function createSettingsSheet_(ss) {
  var sheet = ss.getSheetByName(SHEET_NAMES.SETTINGS);
  if (sheet) return;

  sheet = ss.insertSheet(SHEET_NAMES.SETTINGS);
  var headers = [['設定項目', '値', '説明']];
  var settings = [
    ['CORE_TIME_START', '10', 'コアタイム開始（時）'],
    ['CORE_TIME_END', '19', 'コアタイム終了（時）'],
    ['SLACK_CHANNEL_DAILY', SLACK_CHANNELS.DAILY_REPORTS, '日報投稿チャンネル'],
    ['SLACK_CHANNEL_TASKS', SLACK_CHANNELS.TASK_UPDATES, 'タスク通知チャンネル'],
    ['SLACK_CHANNEL_ALERTS', SLACK_CHANNELS.ALERTS, 'アラートチャンネル'],
    ['REPORT_FOLDER_ID', '', '月次レポート保存先DriveフォルダID'],
    ['SV_COMMENT_DEADLINE_HOURS', '24', '上司コメント期限（時間）'],
    ['EMPTY_ESCALATION_DAYS', '2', '未記入エスカレーション日数'],
    ['AI_PROVIDER', 'anthropic', 'AI評価プロバイダ（anthropic / slack）']
  ];

  sheet.getRange(1, 1, 1, 3).setValues(headers).setFontWeight('bold').setBackground('#4a86c8').setFontColor('white');
  sheet.getRange(2, 1, settings.length, 3).setValues(settings);
  sheet.setColumnWidth(1, 250);
  sheet.setColumnWidth(2, 300);
  sheet.setColumnWidth(3, 300);
  sheet.setFrozenRows(1);
  sheet.protect().setWarningOnly(true);
}

/**
 * メンバー一覧シートを作成
 */
function createMemberRegistrySheet_(ss) {
  var sheet = ss.getSheetByName(SHEET_NAMES.MEMBER_REGISTRY);
  if (sheet) return;

  sheet = ss.insertSheet(SHEET_NAMES.MEMBER_REGISTRY);
  var headers = [['ID', '氏名', 'メールアドレス', 'Slackユーザー名', 'SlackユーザーID', '役割', '日報シート名', 'ステータス']];
  sheet.getRange(1, 1, 1, 8).setValues(headers).setFontWeight('bold').setBackground('#4a86c8').setFontColor('white');

  // 役割のドロップダウン
  var roleRule = SpreadsheetApp.newDataValidation()
    .requireValueInList([MEMBER_ROLE.GENERAL, MEMBER_ROLE.SUPERVISOR])
    .setAllowInvalid(false)
    .build();
  sheet.getRange('F2:F100').setDataValidation(roleRule);

  // ステータスのドロップダウン
  var statusRule = SpreadsheetApp.newDataValidation()
    .requireValueInList(['有効', '無効'])
    .setAllowInvalid(false)
    .build();
  sheet.getRange('H2:H100').setDataValidation(statusRule);

  sheet.setFrozenRows(1);
  sheet.setColumnWidths(1, 8, 150);
}

/**
 * タスク管理シートを作成
 */
function createTaskSheet_(ss) {
  var sheet = ss.getSheetByName(SHEET_NAMES.TASK);
  if (sheet) return;

  sheet = ss.insertSheet(SHEET_NAMES.TASK);
  var headers = [['タスクID', '登録日', '依頼者', '担当者', '期限', 'タスク内容', '優先度', 'ステータス', 'カレンダー反映済', 'Slack通知済', '完了日', '備考']];
  sheet.getRange(1, 1, 1, 12).setValues(headers).setFontWeight('bold').setBackground('#4a86c8').setFontColor('white');

  // 優先度ドロップダウン
  var priorityRule = SpreadsheetApp.newDataValidation()
    .requireValueInList([PRIORITY.HIGH, PRIORITY.MEDIUM, PRIORITY.LOW])
    .setAllowInvalid(false)
    .build();
  sheet.getRange('G2:G500').setDataValidation(priorityRule);

  // ステータスドロップダウン
  var statusRule = SpreadsheetApp.newDataValidation()
    .requireValueInList([TASK_STATUS.NOT_STARTED, TASK_STATUS.IN_PROGRESS, TASK_STATUS.DONE, TASK_STATUS.ON_HOLD])
    .setAllowInvalid(false)
    .build();
  sheet.getRange('H2:H500').setDataValidation(statusRule);

  // チェックボックス
  sheet.getRange('I2:J500').insertCheckboxes();

  sheet.setFrozenRows(1);
  sheet.setColumnWidth(6, 400); // タスク内容列を広く
}

/**
 * ログシートを作成
 */
function createLogSheet_(ss) {
  var sheet = ss.getSheetByName(SHEET_NAMES.LOG);
  if (sheet) return;

  sheet = ss.insertSheet(SHEET_NAMES.LOG);
  var headers = [['日時', '種別', 'メッセージ']];
  sheet.getRange(1, 1, 1, 3).setValues(headers).setFontWeight('bold').setBackground('#4a86c8').setFontColor('white');
  sheet.setFrozenRows(1);
  sheet.setColumnWidth(3, 600);
}

/**
 * API設定ダイアログを表示
 */
function showApiSettingsDialog() {
  var html = HtmlService.createHtmlOutput(
    '<style>body{font-family:sans-serif;padding:16px}label{display:block;margin:12px 0 4px;font-weight:bold}input{width:100%;padding:6px;box-sizing:border-box}button{margin-top:16px;padding:8px 24px;background:#4a86c8;color:white;border:none;border-radius:4px;cursor:pointer}</style>' +
    '<h3>API設定</h3>' +
    '<p>各APIキーはPropertiesServiceに安全に保存されます。</p>' +
    '<label>Slack Bot Token</label><input id="slackToken" placeholder="xoxb-..."><br>' +
    '<label>Slack Webhook URL (日報)</label><input id="slackWebhookDaily" placeholder="https://hooks.slack.com/..."><br>' +
    '<label>Slack Webhook URL (タスク)</label><input id="slackWebhookTasks" placeholder="https://hooks.slack.com/..."><br>' +
    '<label>Anthropic API Key</label><input id="anthropicKey" placeholder="sk-ant-..."><br>' +
    '<label>レポート保存先フォルダID</label><input id="folderId" placeholder="Google Drive フォルダID"><br>' +
    '<button onclick="save()">保存</button>' +
    '<script>' +
    'function save(){' +
    'var data={slackToken:document.getElementById("slackToken").value,' +
    'slackWebhookDaily:document.getElementById("slackWebhookDaily").value,' +
    'slackWebhookTasks:document.getElementById("slackWebhookTasks").value,' +
    'anthropicKey:document.getElementById("anthropicKey").value,' +
    'folderId:document.getElementById("folderId").value};' +
    'google.script.run.withSuccessHandler(function(){alert("保存しました");google.script.host.close()}).saveApiSettings(data);}' +
    '</script>'
  ).setWidth(500).setHeight(500);
  SpreadsheetApp.getUi().showModalDialog(html, 'API設定');
}

/**
 * API設定を保存
 * @param {Object} data
 */
function saveApiSettings(data) {
  if (data.slackToken) setPropertySafe_(PROP_KEYS.SLACK_BOT_TOKEN, data.slackToken);
  if (data.slackWebhookDaily) setPropertySafe_(PROP_KEYS.SLACK_WEBHOOK_DAILY, data.slackWebhookDaily);
  if (data.slackWebhookTasks) setPropertySafe_(PROP_KEYS.SLACK_WEBHOOK_TASKS, data.slackWebhookTasks);
  if (data.anthropicKey) setPropertySafe_(PROP_KEYS.ANTHROPIC_API_KEY, data.anthropicKey);
  if (data.folderId) setPropertySafe_(PROP_KEYS.REPORT_FOLDER_ID, data.folderId);
  logInfo_('API設定が更新されました');
}
