/**
 * 店舗開発部 業務管理システム - 日報シート（Block A）
 */

/**
 * 今月の日報シートを全メンバー分生成
 */
function generateCurrentMonthSheets() {
  var now = new Date();
  var members = getActiveMembers_();
  var ss = getSpreadsheet_();
  var year = now.getFullYear();
  var month = now.getMonth() + 1;

  for (var i = 0; i < members.length; i++) {
    var sheetName = getDailySheetName_(members[i].name);
    var sheet = ss.getSheetByName(sheetName);
    if (sheet) {
      // 既存シートの月データをリフレッシュ
      populateMonthDates_(sheet, year, month);
    } else {
      createDailyReportSheet_(ss, members[i].name, year, month);
    }
  }
  logInfo_(year + '年' + month + '月の日報シートを生成しました');
}

/**
 * 日報シートを新規作成
 * @param {SpreadsheetApp.Spreadsheet} ss
 * @param {string} memberName
 * @param {number} year
 * @param {number} month
 */
function createDailyReportSheet_(ss, memberName, year, month) {
  var sheetName = getDailySheetName_(memberName);

  // 既に存在する場合はスキップ
  if (ss.getSheetByName(sheetName)) return;

  var sheet = ss.insertSheet(sheetName);

  // ===== 行1: タイトル =====
  sheet.getRange(1, 1).setValue('日報 - ' + memberName);
  sheet.getRange(1, 1).setFontSize(14).setFontWeight('bold');

  // ===== 行2: 月選択 =====
  sheet.getRange(2, 1).setValue('対象月:');
  sheet.getRange(2, 2).setValue(year + '年' + ('0' + month).slice(-2) + '月');
  sheet.getRange(2, 2).setFontWeight('bold');

  // ===== 行3: ヘッダー =====
  var headers = buildDailyHeaders_();
  sheet.getRange(3, 1, 1, headers.length).setValues([headers]);
  sheet.getRange(3, 1, 1, headers.length)
    .setFontWeight('bold')
    .setBackground('#4a86c8')
    .setFontColor('white')
    .setWrap(true)
    .setVerticalAlignment('middle');

  // ===== 行4〜: 日次データ =====
  populateMonthDates_(sheet, year, month);

  // ===== 書式設定 =====
  formatDailySheet_(sheet);

  // ===== シート保護（SVコメント列以外を他者から保護）=====
  sheet.setFrozenRows(3);

  logInfo_('日報シート作成: ' + sheetName);
}

/**
 * 日報ヘッダー行を構築
 * @return {Array<string>}
 */
function buildDailyHeaders_() {
  var headers = ['日付', '曜日', '出勤', '退勤', '勤務時間'];

  // コアタイム列（9時間 × 2列）
  for (var i = 0; i < CORE_HOURS.length; i++) {
    var h = CORE_HOURS[i];
    var nextH = h + 1;
    var timeLabel = ('0' + h).slice(-2) + ':00-' + ('0' + nextH).slice(-2) + ':00';
    headers.push(timeLabel + '\nアウトプット');
    headers.push(timeLabel + '\nカレンダー');
  }

  headers.push('日次メモ');
  headers.push('日次所感サマリー');
  headers.push('SVコメント');
  headers.push('Cal同期');

  return headers;
}

/**
 * 指定月の日付データを展開
 * @param {SpreadsheetApp.Sheet} sheet
 * @param {number} year
 * @param {number} month
 */
function populateMonthDates_(sheet, year, month) {
  var daysInMonth = getDaysInMonth_(year, month);
  var rows = [];

  for (var d = 1; d <= daysInMonth; d++) {
    var date = new Date(year, month - 1, d);
    var row = new Array(DAILY_TOTAL_COLS).fill('');
    row[DAILY_COLS.DATE] = date;
    row[DAILY_COLS.DAY_OF_WEEK] = getDayOfWeek_(date);
    row[DAILY_COLS.CAL_SYNCED] = false; // チェックボックス用
    rows.push(row);
  }

  // データ開始行からデータを書き込み
  var range = sheet.getRange(DAILY_DATA_START_ROW, 1, daysInMonth, DAILY_TOTAL_COLS);
  range.setValues(rows);

  // 日付列のフォーマット
  sheet.getRange(DAILY_DATA_START_ROW, 1, daysInMonth, 1).setNumberFormat('yyyy/mm/dd');

  // 勤務時間列に数式を設定
  for (var r = 0; r < daysInMonth; r++) {
    var rowNum = DAILY_DATA_START_ROW + r;
    // 勤務時間 = 退勤 - 出勤（両方入力済みの場合のみ）
    var formula = '=IF(AND(C' + rowNum + '<>"",D' + rowNum + '<>""),D' + rowNum + '-C' + rowNum + ',"")';
    sheet.getRange(rowNum, DAILY_COLS.WORK_HOURS + 1).setFormula(formula);
  }

  // カレンダー同期列にチェックボックスを設定
  sheet.getRange(DAILY_DATA_START_ROW, DAILY_COLS.CAL_SYNCED + 1, daysInMonth, 1).insertCheckboxes();

  // 土日の行に色を付ける
  for (var r2 = 0; r2 < daysInMonth; r2++) {
    var date2 = new Date(year, month - 1, r2 + 1);
    var dayOfWeek = date2.getDay();
    var rowNum2 = DAILY_DATA_START_ROW + r2;
    if (dayOfWeek === 0) {
      // 日曜：薄い赤
      sheet.getRange(rowNum2, 1, 1, DAILY_TOTAL_COLS).setBackground('#fce4ec');
    } else if (dayOfWeek === 6) {
      // 土曜：薄い青
      sheet.getRange(rowNum2, 1, 1, DAILY_TOTAL_COLS).setBackground('#e3f2fd');
    }
  }
}

/**
 * 日報シートの書式を設定
 * @param {SpreadsheetApp.Sheet} sheet
 */
function formatDailySheet_(sheet) {
  // 列幅設定
  sheet.setColumnWidth(1, 100);  // 日付
  sheet.setColumnWidth(2, 40);   // 曜日
  sheet.setColumnWidth(3, 70);   // 出勤
  sheet.setColumnWidth(4, 70);   // 退勤
  sheet.setColumnWidth(5, 70);   // 勤務時間

  // コアタイム列
  for (var i = 0; i < CORE_HOURS.length; i++) {
    var outCol = getCoreOutputCol(i) + 1;
    var calCol = getCoreCalendarCol(i) + 1;
    sheet.setColumnWidth(outCol, 180);  // アウトプット列
    sheet.setColumnWidth(calCol, 120);  // カレンダー列
  }

  sheet.setColumnWidth(DAILY_COLS.MEMO + 1, 250);       // 日次メモ
  sheet.setColumnWidth(DAILY_COLS.SUMMARY + 1, 300);     // 日次所感サマリー
  sheet.setColumnWidth(DAILY_COLS.SV_COMMENT + 1, 250);  // SVコメント
  sheet.setColumnWidth(DAILY_COLS.CAL_SYNCED + 1, 60);   // Cal同期

  // 出勤・退勤列の書式
  sheet.getRange(DAILY_DATA_START_ROW, 3, 31, 2).setNumberFormat('HH:mm');
  // 勤務時間列の書式
  sheet.getRange(DAILY_DATA_START_ROW, 5, 31, 1).setNumberFormat('[h]:mm');

  // カレンダー列の背景色（薄いグレー）
  for (var j = 0; j < CORE_HOURS.length; j++) {
    var calCol2 = getCoreCalendarCol(j) + 1;
    sheet.getRange(DAILY_DATA_START_ROW, calCol2, 31, 1).setBackground('#f5f5f5');
  }

  // テキストの折り返し
  sheet.getRange(DAILY_DATA_START_ROW, 1, 31, DAILY_TOTAL_COLS).setWrap(true);
  sheet.getRange(DAILY_DATA_START_ROW, 1, 31, DAILY_TOTAL_COLS).setVerticalAlignment('top');
}
