/**
 * 店舗開発部 業務管理システム - タスク管理（Block D）
 */

/**
 * タスク入力ダイアログを表示
 */
function showTaskInputDialog() {
  var members = getActiveMembers_();
  var memberOptions = members.map(function(m) {
    return '<option value="' + escapeHtml_(m.name) + '">' + escapeHtml_(m.name) + '</option>';
  }).join('');

  var html = HtmlService.createHtmlOutput(
    '<style>body{font-family:sans-serif;padding:16px}label{display:block;margin:10px 0 4px;font-weight:bold}' +
    'input,select,textarea{width:100%;padding:6px;box-sizing:border-box}' +
    'button{margin-top:16px;padding:8px 24px;background:#4a86c8;color:white;border:none;border-radius:4px;cursor:pointer}</style>' +
    '<h3>タスク登録</h3>' +
    '<label>依頼者</label><select id="requester">' + memberOptions + '</select>' +
    '<label>担当者</label><select id="assignee">' + memberOptions + '</select>' +
    '<label>期限</label><input type="date" id="deadline">' +
    '<label>タスク内容</label><textarea id="content" rows="3"></textarea>' +
    '<label>優先度</label><select id="priority">' +
    '<option value="中">中</option><option value="高">高</option><option value="低">低</option></select>' +
    '<label>備考</label><input id="notes">' +
    '<button onclick="submit()">登録</button>' +
    '<script>' +
    'function submit(){' +
    'var data={requester:document.getElementById("requester").value,' +
    'assignee:document.getElementById("assignee").value,' +
    'deadline:document.getElementById("deadline").value,' +
    'content:document.getElementById("content").value,' +
    'priority:document.getElementById("priority").value,' +
    'notes:document.getElementById("notes").value};' +
    'if(!data.content){alert("タスク内容を入力してください");return}' +
    'if(!data.deadline){alert("期限を入力してください");return}' +
    'google.script.run.withSuccessHandler(function(r){alert(r);google.script.host.close()}).createTask(data);}' +
    '</script>'
  ).setWidth(450).setHeight(520);
  SpreadsheetApp.getUi().showModalDialog(html, 'タスク登録');
}

/**
 * タスクを新規作成
 * @param {Object} data - {requester, assignee, deadline, content, priority, notes}
 * @return {string} 結果メッセージ
 */
function createTask(data) {
  var lock = LockService.getScriptLock();
  if (!lock.tryLock(5000)) return 'ロック取得失敗。再度お試しください。';

  try {
    var sheet = getSheet_(SHEET_NAMES.TASK);
    if (!sheet) return 'タスク管理シートが見つかりません。';

    // タスクID生成
    var lastRow = sheet.getLastRow();
    var taskId = 'T-' + ('000' + lastRow).slice(-4);

    var row = [
      taskId,
      new Date(),              // 登録日
      data.requester,
      data.assignee,
      data.deadline ? new Date(data.deadline) : '',
      data.content,
      data.priority || PRIORITY.MEDIUM,
      TASK_STATUS.NOT_STARTED,
      false,                   // カレンダー反映済
      false,                   // Slack通知済
      '',                      // 完了日
      data.notes || ''
    ];

    sheet.appendRow(row);

    // Googleカレンダーにイベント作成
    if (data.deadline && data.assignee) {
      syncTaskToCalendar_(data.assignee, taskId, data.content, data.deadline);
      // カレンダー反映済フラグをON
      sheet.getRange(lastRow + 1, TASK_COLS.CAL_SYNCED + 1).setValue(true);
    }

    // Slack通知
    try {
      notifyTaskCreated_(taskId, data);
      sheet.getRange(lastRow + 1, TASK_COLS.SLACK_NOTIFIED + 1).setValue(true);
    } catch (e) {
      logWarn_('タスク作成通知失敗: ' + e.message);
    }

    logInfo_('タスク作成: ' + taskId + ' - ' + data.content);
    return 'タスク ' + taskId + ' を登録しました。';
  } finally {
    lock.releaseLock();
  }
}

/**
 * タスクをGoogleカレンダーに反映
 * @param {string} assigneeName
 * @param {string} taskId
 * @param {string} content
 * @param {string} deadlineStr
 */
function syncTaskToCalendar_(assigneeName, taskId, content, deadlineStr) {
  var members = getActiveMembers_();
  var member = null;
  for (var i = 0; i < members.length; i++) {
    if (members[i].name === assigneeName) {
      member = members[i];
      break;
    }
  }

  if (!member || !member.email) {
    logWarn_('タスクカレンダー同期: メンバー不明 - ' + assigneeName);
    return;
  }

  try {
    var calendar = CalendarApp.getCalendarById(member.email);
    if (!calendar) calendar = CalendarApp.getDefaultCalendar();

    var deadline = new Date(deadlineStr);
    // 終日イベントとして作成
    calendar.createAllDayEvent(
      '[タスク] ' + taskId + ': ' + content,
      deadline,
      { description: 'タスクID: ' + taskId + '\n内容: ' + content }
    );

    logInfo_('タスクカレンダー反映: ' + taskId + ' → ' + assigneeName);
  } catch (e) {
    logError_('タスクカレンダー同期エラー: ' + e.message);
  }
}

/**
 * タスク作成をSlackに通知
 * @param {string} taskId
 * @param {Object} data
 */
function notifyTaskCreated_(taskId, data) {
  var webhookUrl = getPropertySafe_(PROP_KEYS.SLACK_WEBHOOK_TASKS);
  if (!webhookUrl) return;

  var message = ':clipboard: *新規タスク登録*\n' +
    '> *タスクID:* ' + taskId + '\n' +
    '> *依頼者:* ' + escapeSlack_(data.requester) + '\n' +
    '> *担当者:* ' + escapeSlack_(data.assignee) + '\n' +
    '> *期限:* ' + (data.deadline || '未設定') + '\n' +
    '> *優先度:* ' + (data.priority || '中') + '\n' +
    '> *内容:* ' + escapeSlack_(data.content);

  sendSlackWebhook_(webhookUrl, message);
}

/**
 * タスク期限チェック
 */
function checkTaskDeadlines() {
  var sheet = getSheet_(SHEET_NAMES.TASK);
  if (!sheet) return;

  var lastRow = sheet.getLastRow();
  if (lastRow < 2) return;

  var data = sheet.getRange(2, 1, lastRow - 1, 12).getValues();
  var today = getToday_();
  var tomorrow = new Date(today);
  tomorrow.setDate(tomorrow.getDate() + 1);

  var overdueItems = [];
  var dueTomorrowItems = [];

  for (var i = 0; i < data.length; i++) {
    var status = data[i][TASK_COLS.STATUS];
    if (status === TASK_STATUS.DONE || status === TASK_STATUS.ON_HOLD) continue;

    var deadline = data[i][TASK_COLS.DEADLINE];
    if (!(deadline instanceof Date)) continue;

    var deadlineDate = new Date(deadline.getFullYear(), deadline.getMonth(), deadline.getDate());

    if (deadlineDate < today) {
      overdueItems.push({
        taskId: data[i][TASK_COLS.TASK_ID],
        assignee: data[i][TASK_COLS.ASSIGNEE],
        content: data[i][TASK_COLS.CONTENT],
        deadline: formatDate_(deadline)
      });
    } else if (deadlineDate.getTime() === tomorrow.getTime()) {
      dueTomorrowItems.push({
        taskId: data[i][TASK_COLS.TASK_ID],
        assignee: data[i][TASK_COLS.ASSIGNEE],
        content: data[i][TASK_COLS.CONTENT],
        deadline: formatDate_(deadline)
      });
    }
  }

  // Slack通知
  if (overdueItems.length > 0) {
    notifyOverdueTasks_(overdueItems);
  }
  if (dueTomorrowItems.length > 0) {
    notifyUpcomingTasks_(dueTomorrowItems);
  }
}

/**
 * 期限超過タスクをSlack通知
 */
function notifyOverdueTasks_(items) {
  var webhookUrl = getPropertySafe_(PROP_KEYS.SLACK_WEBHOOK_TASKS);
  if (!webhookUrl) return;

  var lines = [':warning: *期限超過タスク*'];
  for (var i = 0; i < items.length; i++) {
    var item = items[i];
    var assigneeSlackId = getMemberSlackId_(item.assignee);
    var mention = assigneeSlackId ? '<@' + assigneeSlackId + '>' : item.assignee;
    lines.push('> ' + item.taskId + ' | ' + mention + ' | 期限: ' + item.deadline + ' | ' + escapeSlack_(item.content));
  }

  sendSlackWebhook_(webhookUrl, lines.join('\n'));
}

/**
 * 明日期限タスクをSlack通知
 */
function notifyUpcomingTasks_(items) {
  var webhookUrl = getPropertySafe_(PROP_KEYS.SLACK_WEBHOOK_TASKS);
  if (!webhookUrl) return;

  var lines = [':bell: *明日期限のタスク*'];
  for (var i = 0; i < items.length; i++) {
    var item = items[i];
    var assigneeSlackId = getMemberSlackId_(item.assignee);
    var mention = assigneeSlackId ? '<@' + assigneeSlackId + '>' : item.assignee;
    lines.push('> ' + item.taskId + ' | ' + mention + ' | ' + escapeSlack_(item.content));
  }

  sendSlackWebhook_(webhookUrl, lines.join('\n'));
}

/**
 * メンバー名からSlack IDを取得
 * @param {string} memberName
 * @return {string|null}
 */
function getMemberSlackId_(memberName) {
  var members = getActiveMembers_();
  for (var i = 0; i < members.length; i++) {
    if (members[i].name === memberName) {
      return members[i].slackId;
    }
  }
  return null;
}

/**
 * タスクステータスを更新
 * @param {string} taskId
 * @param {string} newStatus
 */
function updateTaskStatus_(taskId, newStatus) {
  var sheet = getSheet_(SHEET_NAMES.TASK);
  if (!sheet) return;

  var lastRow = sheet.getLastRow();
  if (lastRow < 2) return;

  var ids = sheet.getRange(2, 1, lastRow - 1, 1).getValues();
  for (var i = 0; i < ids.length; i++) {
    if (ids[i][0] === taskId) {
      var row = i + 2;
      sheet.getRange(row, TASK_COLS.STATUS + 1).setValue(newStatus);
      if (newStatus === TASK_STATUS.DONE) {
        sheet.getRange(row, TASK_COLS.COMPLETED_DATE + 1).setValue(new Date());
      }
      logInfo_('タスクステータス更新: ' + taskId + ' → ' + newStatus);
      return;
    }
  }
}
