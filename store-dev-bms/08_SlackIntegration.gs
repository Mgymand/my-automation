/**
 * 店舗開発部 業務管理システム - Slack連携（Block E）
 */

// ===== メイン自動投稿関数 =====

/**
 * 前日分の全メンバー日次所感サマリーをSlackに投稿
 * トリガー: 毎日 10:00
 */
function postDailySummaries() {
  var lock = LockService.getScriptLock();
  if (!lock.tryLock(10000)) {
    logWarn_('日次サマリー投稿: ロック取得失敗');
    return;
  }

  try {
    var yesterday = getYesterday_();
    var yesterdayStr = formatDate_(yesterday);
    var members = getActiveMembers_();
    var ss = getSpreadsheet_();

    var summaries = [];
    var emptyMembers = [];

    for (var i = 0; i < members.length; i++) {
      var member = members[i];
      if (member.role === MEMBER_ROLE.SUPERVISOR) continue; // SVは日報対象外の場合スキップ

      var sheet = ss.getSheetByName(member.sheetName);
      if (!sheet) continue;

      var row = getDailyRowForDate_(sheet, yesterday);
      if (row === -1) continue;

      var summary = sheet.getRange(row, DAILY_COLS.SUMMARY + 1).getValue();
      if (summary && String(summary).trim()) {
        summaries.push({
          name: member.name,
          summary: String(summary).trim()
        });
      } else {
        emptyMembers.push(member);
      }
    }

    // サマリー投稿
    if (summaries.length > 0) {
      postSummaryToSlack_(yesterdayStr, summaries);
    }

    // 未記入チェック（同時実行）
    if (emptyMembers.length > 0) {
      remindEmptyMembers_(yesterdayStr, emptyMembers);
    }

    logInfo_('日次サマリー投稿完了: ' + yesterdayStr + ' (' + summaries.length + '名記入済, ' + emptyMembers.length + '名未記入)');
  } finally {
    lock.releaseLock();
  }
}

/**
 * 日次サマリーをSlack投稿
 */
function postSummaryToSlack_(dateStr, summaries) {
  var webhookUrl = getPropertySafe_(PROP_KEYS.SLACK_WEBHOOK_DAILY);
  if (!webhookUrl) {
    logWarn_('Slack Webhook URL (日報) 未設定');
    return;
  }

  var lines = [':memo: *' + dateStr + ' 日報サマリー*\n'];
  for (var i = 0; i < summaries.length; i++) {
    lines.push('*' + escapeSlack_(summaries[i].name) + '*');
    lines.push('> ' + escapeSlack_(summaries[i].summary));
    lines.push('');
  }

  sendSlackWebhook_(webhookUrl, lines.join('\n'));
}

/**
 * 未記入メンバーにSlackリマインド
 * トリガー: 毎日 10:05
 */
function checkEmptyImpressions() {
  var yesterday = getYesterday_();
  var members = getActiveMembers_();
  var ss = getSpreadsheet_();
  var emptyMembers = [];

  for (var i = 0; i < members.length; i++) {
    var member = members[i];
    if (member.role === MEMBER_ROLE.SUPERVISOR) continue;

    var sheet = ss.getSheetByName(member.sheetName);
    if (!sheet) continue;

    var row = getDailyRowForDate_(sheet, yesterday);
    if (row === -1) continue;

    var summary = sheet.getRange(row, DAILY_COLS.SUMMARY + 1).getValue();
    if (!summary || !String(summary).trim()) {
      emptyMembers.push(member);
    }
  }

  if (emptyMembers.length > 0) {
    remindEmptyMembers_(formatDate_(yesterday), emptyMembers);
  }
}

/**
 * 未記入メンバーをSlackでメンション
 */
function remindEmptyMembers_(dateStr, emptyMembers) {
  var botToken = getPropertySafe_(PROP_KEYS.SLACK_BOT_TOKEN);
  if (!botToken) {
    // Webhookフォールバック
    var webhookUrl = getPropertySafe_(PROP_KEYS.SLACK_WEBHOOK_DAILY);
    if (!webhookUrl) return;

    var names = emptyMembers.map(function(m) { return m.name; }).join(', ');
    sendSlackWebhook_(webhookUrl, ':bell: *' + dateStr + ' 日報未記入*\n' + names + ' さん、日次所感サマリーの記入をお願いします。');
    return;
  }

  // Bot Token使用でメンション
  var mentions = emptyMembers.map(function(m) {
    return m.slackId ? '<@' + m.slackId + '>' : m.name;
  }).join(' ');

  var message = ':bell: *' + dateStr + ' 日報未記入リマインド*\n' +
    mentions + '\n日次所感サマリーの記入をお願いします。';

  sendSlackBotMessage_(SLACK_CHANNELS.DAILY_REPORTS, message, botToken);
}

/**
 * 2日連続未記入メンバーの上司にエスカレーション
 * トリガー: 毎日 10:00
 */
function escalateToSupervisor() {
  var today = getToday_();
  var yesterday = getYesterday_();
  var dayBefore = new Date(yesterday);
  dayBefore.setDate(dayBefore.getDate() - 1);

  var members = getActiveMembers_();
  var ss = getSpreadsheet_();
  var escalationMembers = [];

  for (var i = 0; i < members.length; i++) {
    var member = members[i];
    if (member.role === MEMBER_ROLE.SUPERVISOR) continue;

    var sheet = ss.getSheetByName(member.sheetName);
    if (!sheet) continue;

    // 昨日と一昨日の両方が未記入か確認
    var row1 = getDailyRowForDate_(sheet, yesterday);
    var row2 = getDailyRowForDate_(sheet, dayBefore);

    var empty1 = true, empty2 = true;
    if (row1 !== -1) {
      var s1 = sheet.getRange(row1, DAILY_COLS.SUMMARY + 1).getValue();
      empty1 = !s1 || !String(s1).trim();
    }
    if (row2 !== -1) {
      var s2 = sheet.getRange(row2, DAILY_COLS.SUMMARY + 1).getValue();
      empty2 = !s2 || !String(s2).trim();
    }

    if (empty1 && empty2) {
      escalationMembers.push(member);
    }
  }

  if (escalationMembers.length === 0) return;

  // 上司に通知
  var supervisors = getSupervisors_();
  var botToken = getPropertySafe_(PROP_KEYS.SLACK_BOT_TOKEN);
  if (!botToken) return;

  var svMentions = supervisors.map(function(sv) {
    return sv.slackId ? '<@' + sv.slackId + '>' : sv.name;
  }).join(' ');

  var memberNames = escalationMembers.map(function(m) { return m.name; }).join(', ');

  var message = ':rotating_light: *日報未記入エスカレーション*\n' +
    svMentions + '\n' +
    '以下のメンバーが2日連続で日報未記入です:\n' +
    '> ' + memberNames;

  sendSlackBotMessage_(SLACK_CHANNELS.ALERTS, message, botToken);
  logInfo_('エスカレーション通知: ' + memberNames);
}

/**
 * 上司コメント未記入チェック
 * トリガー: 毎日 18:00
 */
function remindSupervisorComments() {
  var yesterday = getYesterday_();
  var members = getActiveMembers_();
  var ss = getSpreadsheet_();
  var needsComment = [];

  for (var i = 0; i < members.length; i++) {
    var member = members[i];
    if (member.role === MEMBER_ROLE.SUPERVISOR) continue;

    var sheet = ss.getSheetByName(member.sheetName);
    if (!sheet) continue;

    var row = getDailyRowForDate_(sheet, yesterday);
    if (row === -1) continue;

    var summary = sheet.getRange(row, DAILY_COLS.SUMMARY + 1).getValue();
    var svComment = sheet.getRange(row, DAILY_COLS.SV_COMMENT + 1).getValue();

    // 日報が記入済みなのにSVコメントが未記入
    if (summary && String(summary).trim() && (!svComment || !String(svComment).trim())) {
      needsComment.push(member.name);
    }
  }

  if (needsComment.length === 0) return;

  var supervisors = getSupervisors_();
  var botToken = getPropertySafe_(PROP_KEYS.SLACK_BOT_TOKEN);
  if (!botToken) return;

  var svMentions = supervisors.map(function(sv) {
    return sv.slackId ? '<@' + sv.slackId + '>' : sv.name;
  }).join(' ');

  var message = ':speech_balloon: *SVコメント未記入リマインド*\n' +
    svMentions + '\n' +
    '以下のメンバーの日報(' + formatDate_(yesterday) + ')にコメントをお願いします:\n' +
    '> ' + needsComment.join(', ');

  sendSlackBotMessage_(SLACK_CHANNELS.ALERTS, message, botToken);
  logInfo_('SVコメントリマインド: ' + needsComment.join(', '));
}

// ===== Slack API ヘルパー =====

/**
 * Incoming Webhookでメッセージ送信
 * @param {string} webhookUrl
 * @param {string} text
 */
function sendSlackWebhook_(webhookUrl, text) {
  try {
    var payload = { text: text };
    var options = {
      method: 'post',
      contentType: 'application/json',
      payload: JSON.stringify(payload),
      muteHttpExceptions: true
    };

    var response = UrlFetchApp.fetch(webhookUrl, options);
    var code = response.getResponseCode();
    if (code !== 200) {
      logError_('Slack Webhook エラー (HTTP ' + code + '): ' + response.getContentText().substring(0, 100));
    }
  } catch (e) {
    logError_('Slack Webhook 例外: ' + e.message);
  }
}

/**
 * Slack Bot Tokenでメッセージ送信（@メンション可能）
 * @param {string} channel - チャンネル名 or ID
 * @param {string} text
 * @param {string} botToken
 */
function sendSlackBotMessage_(channel, text, botToken) {
  try {
    var payload = {
      channel: channel,
      text: text,
      unfurl_links: false
    };

    var options = {
      method: 'post',
      contentType: 'application/json',
      headers: {
        'Authorization': 'Bearer ' + botToken
      },
      payload: JSON.stringify(payload),
      muteHttpExceptions: true
    };

    var response = UrlFetchApp.fetch('https://slack.com/api/chat.postMessage', options);
    var code = response.getResponseCode();
    var body = JSON.parse(response.getContentText());

    if (code !== 200 || !body.ok) {
      logError_('Slack Bot メッセージエラー: ' + (body.error || 'HTTP ' + code));
    }
  } catch (e) {
    logError_('Slack Bot メッセージ例外: ' + e.message);
  }
}
