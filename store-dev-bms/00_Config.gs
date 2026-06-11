/**
 * 店舗開発部 業務管理システム - グローバル設定
 * 定数・シート名・列マップ・メンバー定義
 */

// ===== シート名定義 =====
var SHEET_NAMES = {
  SETTINGS: '設定',
  MEMBER_REGISTRY: 'メンバー一覧',
  TASK: 'タスク管理',
  LOG: 'ログ',
  DAILY_PREFIX: '日報_',          // 日報_{氏名}
  MONTHLY_PREFIX: '月次目標_'     // 月次目標_{YYYY年MM月}
};

// ===== コアタイム設定 =====
var CORE_HOURS = [10, 11, 12, 13, 14, 15, 16, 17, 18]; // 10:00-19:00

// ===== 日報シート列マップ（0始まり） =====
var DAILY_COLS = {
  DATE: 0,           // A: 日付
  DAY_OF_WEEK: 1,    // B: 曜日
  CLOCK_IN: 2,       // C: 出勤時刻
  CLOCK_OUT: 3,      // D: 退勤時刻
  WORK_HOURS: 4,     // E: 勤務時間
  // F〜W: コアタイム（9時間 × 2列 = 18列）
  // 各時間枠: OUTPUT列 = 5 + (hourIndex * 2), CALENDAR列 = 5 + (hourIndex * 2) + 1
  CORE_START: 5,     // F: コアタイム開始列
  MEMO: 23,          // X: 日次メモ
  SUMMARY: 24,       // Y: 日次所感サマリー
  SV_COMMENT: 25,    // Z: SVコメント
  CAL_SYNCED: 26     // AA: カレンダー同期済フラグ
};

// コアタイムの出力列・カレンダー列を取得するヘルパー
function getCoreOutputCol(hourIndex) {
  return DAILY_COLS.CORE_START + (hourIndex * 2);
}
function getCoreCalendarCol(hourIndex) {
  return DAILY_COLS.CORE_START + (hourIndex * 2) + 1;
}

// ===== 日報シートの総列数 =====
var DAILY_TOTAL_COLS = 27;

// ===== 日報シートのデータ開始行（1始まり）=====
var DAILY_DATA_START_ROW = 4; // 1:ヘッダー, 2:月選択, 3:空行, 4〜:日次データ

// ===== タスク管理シート列マップ（0始まり） =====
var TASK_COLS = {
  TASK_ID: 0,        // A
  CREATED_DATE: 1,   // B
  REQUESTER: 2,      // C
  ASSIGNEE: 3,       // D
  DEADLINE: 4,       // E
  CONTENT: 5,        // F
  PRIORITY: 6,       // G: 高/中/低
  STATUS: 7,         // H: 未着手/進行中/完了/保留
  CAL_SYNCED: 8,     // I: カレンダー反映済
  SLACK_NOTIFIED: 9, // J: Slack通知済
  COMPLETED_DATE: 10,// K
  NOTES: 11          // L
};

// ===== 月次目標シート列マップ（0始まり） =====
var MONTHLY_COLS = {
  MEMBER_NAME: 0,    // A
  MAIN_GOAL: 1,      // B
  SUB_GOAL_1: 2,     // C
  SUB_GOAL_2: 3,     // D
  SUB_GOAL_3: 4,     // E
  ACHIEVEMENT: 5,    // F: 達成度(%)
  AI_SCORE: 6,       // G
  AI_COMMENT: 7,     // H
  REPORT_URL: 8,     // I
  EVAL_DATE: 9       // J
};

// ===== メンバー一覧列マップ（0始まり） =====
var MEMBER_COLS = {
  ID: 0,
  NAME: 1,
  EMAIL: 2,
  SLACK_NAME: 3,
  SLACK_ID: 4,
  ROLE: 5,           // 一般 / スーパーバイザー
  SHEET_NAME: 6,
  STATUS: 7          // 有効 / 無効
};

// ===== 優先度・ステータス定数 =====
var PRIORITY = { HIGH: '高', MEDIUM: '中', LOW: '低' };
var TASK_STATUS = { NOT_STARTED: '未着手', IN_PROGRESS: '進行中', DONE: '完了', ON_HOLD: '保留' };
var MEMBER_ROLE = { GENERAL: '一般', SUPERVISOR: 'スーパーバイザー' };

// ===== Slack チャンネル名（新規作成） =====
var SLACK_CHANNELS = {
  DAILY_REPORTS: '#store-dev-daily',
  TASK_UPDATES: '#store-dev-tasks',
  ALERTS: '#store-dev-alerts'
};

// ===== AI設定 =====
var AI_CONFIG = {
  ANTHROPIC_MODEL: 'claude-sonnet-4-20250514',
  ANTHROPIC_API_URL: 'https://api.anthropic.com/v1/messages',
  ANTHROPIC_VERSION: '2023-06-01',
  MAX_TOKENS: 4096
};

// ===== レポートセクション定義 =====
var REPORT_SECTIONS = [
  '今月の目標と達成度（出店進捗）',
  '今月のアウトプット',
  '今月の成果',
  '課題（構造整理）',
  '成長した点（行動の変化）',
  '来月に向けたToDo',
  'バリュー体現・自己評価（Open / Professional / Top speed / One team）'
];

// ===== PropertiesService ヘルパー =====

/**
 * スクリプトプロパティを安全に取得
 * @param {string} key - プロパティキー
 * @return {string|null} プロパティ値
 */
function getPropertySafe_(key) {
  try {
    return PropertiesService.getScriptProperties().getProperty(key);
  } catch (e) {
    logError_('PropertiesService取得エラー: ' + key + ' - ' + e.message);
    return null;
  }
}

/**
 * スクリプトプロパティを設定
 * @param {string} key
 * @param {string} value
 */
function setPropertySafe_(key, value) {
  try {
    PropertiesService.getScriptProperties().setProperty(key, value);
  } catch (e) {
    logError_('PropertiesService設定エラー: ' + key + ' - ' + e.message);
  }
}

// ===== プロパティキー定数 =====
var PROP_KEYS = {
  SLACK_WEBHOOK_DAILY: 'SLACK_WEBHOOK_DAILY',
  SLACK_WEBHOOK_TASKS: 'SLACK_WEBHOOK_TASKS',
  SLACK_BOT_TOKEN: 'SLACK_BOT_TOKEN',
  SLACK_SIGNING_SECRET: 'SLACK_SIGNING_SECRET',
  ANTHROPIC_API_KEY: 'ANTHROPIC_API_KEY',
  SF_INSTANCE_URL: 'SF_INSTANCE_URL',
  SF_ACCESS_TOKEN: 'SF_ACCESS_TOKEN',
  SF_REFRESH_TOKEN: 'SF_REFRESH_TOKEN',
  SF_CLIENT_ID: 'SF_CLIENT_ID',
  SF_CLIENT_SECRET: 'SF_CLIENT_SECRET',
  REPORT_FOLDER_ID: 'REPORT_FOLDER_ID'
};

/**
 * アクティブなスプレッドシートを取得
 * @return {SpreadsheetApp.Spreadsheet}
 */
function getSpreadsheet_() {
  return SpreadsheetApp.getActiveSpreadsheet();
}

/**
 * 指定名のシートを取得（存在しなければnull）
 * @param {string} sheetName
 * @return {SpreadsheetApp.Sheet|null}
 */
function getSheet_(sheetName) {
  return getSpreadsheet_().getSheetByName(sheetName);
}
