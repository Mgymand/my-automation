/**
 * 店舗開発部 業務管理システム - カレンダー連携（Block C）
 */

/**
 * アクティブセルの行（日付）に対してカレンダー同期を実行
 */
function syncCalendarForToday() {
  var sheet = SpreadsheetApp.getActiveSheet();
  var sheetName = sheet.getName();

  // 日報シートかどうか確認
  if (sheetName.indexOf(SHEET_NAMES.DAILY_PREFIX) !== 0) {
    SpreadsheetApp.getUi().alert('日報シートを選択してください。');
    return;
  }

  var activeRow = SpreadsheetApp.getActiveRange().getRow();
  if (activeRow < DAILY_DATA_START_ROW) {
    SpreadsheetApp.getUi().alert('データ行を選択してください。');
    return;
  }

  // メンバー名をシート名から取得
  var memberName = sheetName.replace(SHEET_NAMES.DAILY_PREFIX, '');

  // 日付を取得
  var dateCell = sheet.getRange(activeRow, DAILY_COLS.DATE + 1).getValue();
  if (!(dateCell instanceof Date)) {
    SpreadsheetApp.getUi().alert('日付が設定されていない行です。');
    return;
  }

  syncCalendarForRow_(sheet, activeRow, dateCell, memberName);
  SpreadsheetApp.getUi().alert(Utilities.formatDate(dateCell, 'Asia/Tokyo', 'MM/dd') + ' のカレンダー予定を同期しました。');
}

/**
 * 指定行にカレンダー予定を同期
 * @param {SpreadsheetApp.Sheet} sheet
 * @param {number} row - 行番号（1始まり）
 * @param {Date} date - 対象日
 * @param {string} memberName - メンバー名（ログ用）
 */
function syncCalendarForRow_(sheet, row, date, memberName) {
  // メンバーのメールアドレスからカレンダーを特定
  var members = getActiveMembers_();
  var member = null;
  for (var i = 0; i < members.length; i++) {
    if (members[i].name === memberName) {
      member = members[i];
      break;
    }
  }

  var calendar;
  if (member && member.email) {
    try {
      calendar = CalendarApp.getCalendarById(member.email);
    } catch (e) {
      // フォールバック: デフォルトカレンダー
      calendar = CalendarApp.getDefaultCalendar();
    }
  } else {
    calendar = CalendarApp.getDefaultCalendar();
  }

  // その日のイベントを取得
  var events = calendar.getEventsForDay(date);

  // コアタイム各時間枠にイベントをマッピング
  for (var h = 0; h < CORE_HOURS.length; h++) {
    var hour = CORE_HOURS[h];
    var slotStart = new Date(date.getFullYear(), date.getMonth(), date.getDate(), hour, 0);
    var slotEnd = new Date(date.getFullYear(), date.getMonth(), date.getDate(), hour + 1, 0);

    var eventsInSlot = [];

    for (var e = 0; e < events.length; e++) {
      var event = events[e];
      var eventStart = event.getStartTime();
      var eventEnd = event.getEndTime();

      // イベントがこの時間枠と重なるか判定
      if (eventStart < slotEnd && eventEnd > slotStart) {
        var title = event.getTitle();
        if (title) {
          eventsInSlot.push(title);
        }
      }
    }

    // カレンダー列に書き込み
    var calCol = getCoreCalendarCol(h) + 1;
    sheet.getRange(row, calCol).setValue(eventsInSlot.join('\n'));
  }

  // 出勤・退勤時刻の自動入力（最初のイベント開始〜最後のイベント終了）
  if (events.length > 0) {
    var clockIn = sheet.getRange(row, DAILY_COLS.CLOCK_IN + 1).getValue();
    var clockOut = sheet.getRange(row, DAILY_COLS.CLOCK_OUT + 1).getValue();

    // 出勤・退勤が未入力の場合のみ自動入力
    if (!clockIn) {
      var firstEvent = events[0].getStartTime();
      sheet.getRange(row, DAILY_COLS.CLOCK_IN + 1).setValue(firstEvent);
    }
    if (!clockOut) {
      var lastEvent = events[events.length - 1].getEndTime();
      sheet.getRange(row, DAILY_COLS.CLOCK_OUT + 1).setValue(lastEvent);
    }
  }

  // 同期フラグをON
  sheet.getRange(row, DAILY_COLS.CAL_SYNCED + 1).setValue(true);

  logInfo_('カレンダー同期: ' + memberName + ' - ' + formatDate_(date));
}

/**
 * 全メンバーの指定日のカレンダーを一括同期
 * @param {Date} date
 */
function syncAllMembersCalendar_(date) {
  var members = getActiveMembers_();
  var ss = getSpreadsheet_();

  for (var i = 0; i < members.length; i++) {
    var sheet = ss.getSheetByName(members[i].sheetName);
    if (!sheet) continue;

    var row = getDailyRowForDate_(sheet, date);
    if (row === -1) continue;

    try {
      syncCalendarForRow_(sheet, row, date, members[i].name);
    } catch (e) {
      logError_('カレンダー同期エラー: ' + members[i].name + ' - ' + e.message);
    }
  }
}

/**
 * Slackコマンドからカレンダーイベントを登録
 * @param {string} memberEmail - メンバーのメールアドレス
 * @param {string} dateStr - 日付（yyyy-MM-dd）
 * @param {string} startTime - 開始時刻（HH:mm）
 * @param {string} endTime - 終了時刻（HH:mm）
 * @param {string} title - イベントタイトル
 * @return {boolean} 成功/失敗
 */
function createCalendarEvent_(memberEmail, dateStr, startTime, endTime, title) {
  try {
    var calendar = CalendarApp.getCalendarById(memberEmail);
    if (!calendar) {
      calendar = CalendarApp.getDefaultCalendar();
    }

    var dateParts = dateStr.split('-');
    var year = parseInt(dateParts[0], 10);
    var month = parseInt(dateParts[1], 10) - 1;
    var day = parseInt(dateParts[2], 10);

    var startParts = startTime.split(':');
    var endParts = endTime.split(':');

    var start = new Date(year, month, day, parseInt(startParts[0], 10), parseInt(startParts[1], 10));
    var end = new Date(year, month, day, parseInt(endParts[0], 10), parseInt(endParts[1], 10));

    calendar.createEvent(title, start, end);
    logInfo_('カレンダーイベント作成: ' + title + ' (' + dateStr + ' ' + startTime + '-' + endTime + ')');
    return true;
  } catch (e) {
    logError_('カレンダーイベント作成エラー: ' + e.message);
    return false;
  }
}
