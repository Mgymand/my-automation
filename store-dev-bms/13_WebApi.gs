/**
 * 店舗開発部 業務管理システム - WebApi（Slack Slash Commands受付）
 */

/**
 * GAS Web App: GETリクエスト処理
 */
function doGet(e) {
  return ContentService.createTextOutput('Store Dev BMS API is running.')
    .setMimeType(ContentService.MimeType.TEXT);
}

/**
 * GAS Web App: POSTリクエスト処理（Slack Slash Commands）
 * @param {Object} e - リクエストオブジェクト
 */
function doPost(e) {
  try {
    var params = e.parameter;

    // Slackコマンドのルーティング
    var command = params.command || '';
    var text = params.text || '';
    var userId = params.user_id || '';
    var userName = params.user_name || '';

    logInfo_('WebApi受信: command=' + command + ', text=' + text + ', user=' + userName);

    var response;

    switch (command) {
      case '/task':
        response = handleTaskCommand_(text, userName);
        break;
      case '/cal':
        response = handleCalCommand_(text, userName);
        break;
      case '/report':
        response = handleReportCommand_(text, userName);
        break;
      case '/status':
        response = handleStatusCommand_(userName);
        break;
      default:
        response = { text: '不明なコマンドです。使用可能: /task, /cal, /report, /status' };
    }

    return ContentService.createTextOutput(JSON.stringify(response))
      .setMimeType(ContentService.MimeType.JSON);
  } catch (error) {
    logError_('WebApi エラー: ' + error.message);
    return ContentService.createTextOutput(JSON.stringify({
      text: 'エラーが発生しました: ' + error.message
    })).setMimeType(ContentService.MimeType.JSON);
  }
}

/**
 * /task コマンド処理
 * 書式: /task @担当者 2026-04-10 タスク内容
 * @param {string} text
 * @param {string} requesterName
 * @return {Object} Slackレスポンス
 */
function handleTaskCommand_(text, requesterName) {
  var parts = text.trim().split(/\s+/);
  if (parts.length < 3) {
    return {
      text: ':information_source: 使い方: `/task 担当者名 期限(yyyy-MM-dd) タスク内容`\n' +
        '例: `/task 山田太郎 2026-04-10 提案書の作成`'
    };
  }

  var assignee = parts[0].replace('@', '');
  var deadline = parts[1];
  var content = parts.slice(2).join(' ');

  // 日付バリデーション
  if (!/^\d{4}-\d{2}-\d{2}$/.test(deadline)) {
    return { text: ':x: 期限の形式が正しくありません。yyyy-MM-dd で入力してください。' };
  }

  var data = {
    requester: requesterName,
    assignee: assignee,
    deadline: deadline,
    content: content,
    priority: PRIORITY.MEDIUM,
    notes: 'Slackから登録'
  };

  var result = createTask(data);
  return { text: ':white_check_mark: ' + result };
}

/**
 * /cal コマンド処理
 * 書式: /cal 2026-04-03 10:00 11:00 打合せ
 * @param {string} text
 * @param {string} userName
 * @return {Object} Slackレスポンス
 */
function handleCalCommand_(text, userName) {
  var parts = text.trim().split(/\s+/);
  if (parts.length < 4) {
    return {
      text: ':information_source: 使い方: `/cal 日付(yyyy-MM-dd) 開始(HH:mm) 終了(HH:mm) タイトル`\n' +
        '例: `/cal 2026-04-03 10:00 11:00 チームMTG`'
    };
  }

  var dateStr = parts[0];
  var startTime = parts[1];
  var endTime = parts[2];
  var title = parts.slice(3).join(' ');

  // バリデーション
  if (!/^\d{4}-\d{2}-\d{2}$/.test(dateStr)) {
    return { text: ':x: 日付の形式が正しくありません。yyyy-MM-dd で入力してください。' };
  }
  if (!/^\d{2}:\d{2}$/.test(startTime) || !/^\d{2}:\d{2}$/.test(endTime)) {
    return { text: ':x: 時刻の形式が正しくありません。HH:mm で入力してください。' };
  }

  // Slackユーザー名からメンバーを検索
  var members = getActiveMembers_();
  var member = null;
  for (var i = 0; i < members.length; i++) {
    if (members[i].slackName === userName) {
      member = members[i];
      break;
    }
  }

  if (!member) {
    return { text: ':x: メンバーが見つかりません。メンバー一覧にSlackユーザー名を登録してください。' };
  }

  var success = createCalendarEvent_(member.email, dateStr, startTime, endTime, title);
  if (success) {
    return { text: ':white_check_mark: カレンダーに登録しました: ' + title + ' (' + dateStr + ' ' + startTime + '-' + endTime + ')' };
  } else {
    return { text: ':x: カレンダー登録に失敗しました。' };
  }
}

/**
 * /report コマンド処理
 * 書式: /report メンバー名
 * @param {string} text
 * @param {string} userName
 * @return {Object} Slackレスポンス
 */
function handleReportCommand_(text, userName) {
  var memberName = text.trim();
  if (!memberName) {
    return { text: ':information_source: 使い方: `/report メンバー名`' };
  }

  var ss = getSpreadsheet_();
  var sheet = ss.getSheetByName(getDailySheetName_(memberName));
  if (!sheet) {
    return { text: ':x: ' + memberName + ' の日報シートが見つかりません。' };
  }

  var today = getToday_();
  var row = getDailyRowForDate_(sheet, today);
  if (row === -1) {
    return { text: ':x: 今日の日報データが見つかりません。' };
  }

  var summary = sheet.getRange(row, DAILY_COLS.SUMMARY + 1).getValue();
  var memo = sheet.getRange(row, DAILY_COLS.MEMO + 1).getValue();
  var clockIn = sheet.getRange(row, DAILY_COLS.CLOCK_IN + 1).getValue();
  var clockOut = sheet.getRange(row, DAILY_COLS.CLOCK_OUT + 1).getValue();

  var statusText = ':clipboard: *' + memberName + ' の今日の日報*\n';
  statusText += '> 出勤: ' + (clockIn ? Utilities.formatDate(new Date(clockIn), 'Asia/Tokyo', 'HH:mm') : '未入力') + '\n';
  statusText += '> 退勤: ' + (clockOut ? Utilities.formatDate(new Date(clockOut), 'Asia/Tokyo', 'HH:mm') : '未入力') + '\n';
  statusText += '> メモ: ' + (memo || '未記入') + '\n';
  statusText += '> 日次所感: ' + (summary || '*未記入*');

  return { text: statusText };
}

/**
 * /status コマンド処理
 * @param {string} userName
 * @return {Object} Slackレスポンス
 */
function handleStatusCommand_(userName) {
  var members = getActiveMembers_();
  var ss = getSpreadsheet_();
  var today = getToday_();

  var filled = [];
  var empty = [];

  for (var i = 0; i < members.length; i++) {
    var member = members[i];
    if (member.role === MEMBER_ROLE.SUPERVISOR) continue;

    var sheet = ss.getSheetByName(member.sheetName);
    if (!sheet) { empty.push(member.name); continue; }

    var row = getDailyRowForDate_(sheet, today);
    if (row === -1) { empty.push(member.name); continue; }

    var summary = sheet.getRange(row, DAILY_COLS.SUMMARY + 1).getValue();
    if (summary && String(summary).trim()) {
      filled.push(member.name);
    } else {
      empty.push(member.name);
    }
  }

  var total = filled.length + empty.length;
  var statusText = ':bar_chart: *本日の日報ステータス* (' + formatDate_(today) + ')\n';
  statusText += '記入済: ' + filled.length + '/' + total + '名\n';
  if (filled.length > 0) {
    statusText += ':white_check_mark: ' + filled.join(', ') + '\n';
  }
  if (empty.length > 0) {
    statusText += ':x: ' + empty.join(', ');
  }

  return { text: statusText };
}
