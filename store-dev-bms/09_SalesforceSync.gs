/**
 * 店舗開発部 業務管理システム - Salesforce連携（Block F）
 *
 * 連携対象オブジェクト:
 *   - Activity（活動）: 日報サマリー → Task/Event レコード
 *   - Opportunity（商談）: タスク管理の店舗開発案件 → Opportunity紐付け
 *   - Lead（リード）: 新規開発候補地 → Lead登録
 *
 * 認証方式: OAuth 2.0 Username-Password Flow（追加コスト不要）
 */

// ===== Salesforce 認証 =====

/**
 * Salesforce OAuth トークンを取得/更新
 * @return {Object|null} {instanceUrl, accessToken}
 */
function getSalesforceAuth_() {
  var accessToken = getPropertySafe_(PROP_KEYS.SF_ACCESS_TOKEN);
  var instanceUrl = getPropertySafe_(PROP_KEYS.SF_INSTANCE_URL);

  // トークンが有効か確認
  if (accessToken && instanceUrl) {
    if (testSalesforceConnection_(instanceUrl, accessToken)) {
      return { instanceUrl: instanceUrl, accessToken: accessToken };
    }
  }

  // トークン更新
  return refreshSalesforceToken_();
}

/**
 * Salesforce接続テスト
 */
function testSalesforceConnection_(instanceUrl, accessToken) {
  try {
    var response = UrlFetchApp.fetch(instanceUrl + '/services/data/v58.0/', {
      headers: { 'Authorization': 'Bearer ' + accessToken },
      muteHttpExceptions: true
    });
    return response.getResponseCode() === 200;
  } catch (e) {
    return false;
  }
}

/**
 * Salesforceトークンを更新（Username-Password Flow）
 * @return {Object|null}
 */
function refreshSalesforceToken_() {
  var clientId = getPropertySafe_(PROP_KEYS.SF_CLIENT_ID);
  var clientSecret = getPropertySafe_(PROP_KEYS.SF_CLIENT_SECRET);
  var username = getPropertySafe_('SF_USERNAME');
  var password = getPropertySafe_('SF_PASSWORD');
  var securityToken = getPropertySafe_('SF_SECURITY_TOKEN');

  if (!clientId || !clientSecret || !username || !password) {
    logWarn_('Salesforce認証情報が未設定です');
    return null;
  }

  try {
    var payload = {
      grant_type: 'password',
      client_id: clientId,
      client_secret: clientSecret,
      username: username,
      password: password + (securityToken || '')
    };

    var response = UrlFetchApp.fetch('https://login.salesforce.com/services/oauth2/token', {
      method: 'post',
      payload: payload,
      muteHttpExceptions: true
    });

    if (response.getResponseCode() !== 200) {
      logError_('SF認証エラー: ' + response.getContentText().substring(0, 200));
      return null;
    }

    var json = JSON.parse(response.getContentText());
    setPropertySafe_(PROP_KEYS.SF_ACCESS_TOKEN, json.access_token);
    setPropertySafe_(PROP_KEYS.SF_INSTANCE_URL, json.instance_url);

    logInfo_('Salesforceトークン更新成功');
    return { instanceUrl: json.instance_url, accessToken: json.access_token };
  } catch (e) {
    logError_('SF認証例外: ' + e.message);
    return null;
  }
}

// ===== Salesforce REST API ヘルパー =====

/**
 * Salesforce REST APIリクエスト
 * @param {string} method - GET/POST/PATCH
 * @param {string} path - APIパス（例: /services/data/v58.0/sobjects/Task）
 * @param {Object} [body] - リクエストボディ
 * @return {Object|null} レスポンス
 */
function sfApiRequest_(method, path, body) {
  var auth = getSalesforceAuth_();
  if (!auth) return null;

  try {
    var options = {
      method: method.toLowerCase(),
      headers: {
        'Authorization': 'Bearer ' + auth.accessToken,
        'Content-Type': 'application/json'
      },
      muteHttpExceptions: true
    };

    if (body) {
      options.payload = JSON.stringify(body);
    }

    var response = UrlFetchApp.fetch(auth.instanceUrl + path, options);
    var code = response.getResponseCode();

    if (code >= 200 && code < 300) {
      var text = response.getContentText();
      return text ? JSON.parse(text) : { success: true };
    } else {
      logError_('SF API エラー (' + method + ' ' + path + '): HTTP ' + code + ' - ' + response.getContentText().substring(0, 200));
      return null;
    }
  } catch (e) {
    logError_('SF API 例外: ' + e.message);
    return null;
  }
}

// ===== 日報 → Activity（活動）連携 =====

/**
 * 日報サマリーをSalesforce Activityとして登録
 * @param {string} memberName
 * @param {Date} date
 * @param {string} summary
 */
function syncDailyReportToActivity_(memberName, date, summary) {
  if (!summary) return;

  var taskBody = {
    Subject: '[日報] ' + memberName + ' - ' + formatDate_(date),
    Description: summary,
    Status: 'Completed',
    ActivityDate: Utilities.formatDate(date, 'Asia/Tokyo', 'yyyy-MM-dd'),
    Type: 'Other',
    // OwnerId は Salesforceユーザーとの紐付けが必要（別途マッピング）
  };

  var result = sfApiRequest_('POST', '/services/data/v58.0/sobjects/Task', taskBody);
  if (result && result.id) {
    logInfo_('SF Activity作成: ' + result.id + ' (' + memberName + ')');
  }
}

/**
 * 前日分の全日報をSalesforceに同期
 */
function syncDailyReportsToSalesforce() {
  var auth = getSalesforceAuth_();
  if (!auth) {
    logWarn_('Salesforce同期スキップ: 認証失敗');
    return;
  }

  var yesterday = getYesterday_();
  var members = getActiveMembers_();
  var ss = getSpreadsheet_();

  for (var i = 0; i < members.length; i++) {
    var sheet = ss.getSheetByName(members[i].sheetName);
    if (!sheet) continue;

    var row = getDailyRowForDate_(sheet, yesterday);
    if (row === -1) continue;

    var summary = sheet.getRange(row, DAILY_COLS.SUMMARY + 1).getValue();
    if (summary && String(summary).trim()) {
      syncDailyReportToActivity_(members[i].name, yesterday, String(summary));
      Utilities.sleep(500); // API制限対策
    }
  }

  logInfo_('Salesforce日報同期完了: ' + formatDate_(yesterday));
}

// ===== タスク → Opportunity（商談）連携 =====

/**
 * タスクをSalesforce Opportunityに紐付け
 * @param {string} taskId
 * @param {string} content
 * @param {string} assigneeName
 * @param {Date} deadline
 * @param {string} [opportunityId] - 既存Opportunity ID（任意）
 */
function syncTaskToOpportunity_(taskId, content, assigneeName, deadline, opportunityId) {
  if (opportunityId) {
    // 既存Opportunityにメモを追加
    var noteBody = {
      ParentId: opportunityId,
      Title: '[タスク] ' + taskId,
      Body: content + '\n担当: ' + assigneeName + '\n期限: ' + formatDate_(deadline)
    };
    sfApiRequest_('POST', '/services/data/v58.0/sobjects/ContentNote', noteBody);
  } else {
    // 新規Opportunityとして作成（店舗開発案件）
    var oppBody = {
      Name: '[店舗開発] ' + content,
      StageName: 'Prospecting',
      CloseDate: Utilities.formatDate(deadline, 'Asia/Tokyo', 'yyyy-MM-dd'),
      Description: 'タスクID: ' + taskId + '\n担当: ' + assigneeName
    };

    var result = sfApiRequest_('POST', '/services/data/v58.0/sobjects/Opportunity', oppBody);
    if (result && result.id) {
      logInfo_('SF Opportunity作成: ' + result.id + ' (' + taskId + ')');
    }
  }
}

// ===== リード連携 =====

/**
 * 新規開発候補地をSalesforce Leadとして登録
 * @param {Object} leadData - {company, lastName, description, source}
 * @return {string|null} Lead ID
 */
function createSalesforceLead_(leadData) {
  var body = {
    Company: leadData.company || '新規候補地',
    LastName: leadData.lastName || '店舗開発部',
    Description: leadData.description || '',
    LeadSource: leadData.source || 'Store Development',
    Status: 'Open - Not Contacted'
  };

  var result = sfApiRequest_('POST', '/services/data/v58.0/sobjects/Lead', body);
  if (result && result.id) {
    logInfo_('SF Lead作成: ' + result.id);
    return result.id;
  }
  return null;
}

// ===== Salesforce設定ダイアログ =====

/**
 * Salesforce設定を保存
 * @param {Object} data
 */
function saveSalesforceSettings(data) {
  if (data.clientId) setPropertySafe_(PROP_KEYS.SF_CLIENT_ID, data.clientId);
  if (data.clientSecret) setPropertySafe_(PROP_KEYS.SF_CLIENT_SECRET, data.clientSecret);
  if (data.username) setPropertySafe_('SF_USERNAME', data.username);
  if (data.password) setPropertySafe_('SF_PASSWORD', data.password);
  if (data.securityToken) setPropertySafe_('SF_SECURITY_TOKEN', data.securityToken);

  // 接続テスト
  var auth = refreshSalesforceToken_();
  if (auth) {
    logInfo_('Salesforce接続成功: ' + auth.instanceUrl);
    return 'Salesforce接続成功';
  } else {
    return 'Salesforce接続失敗。認証情報を確認してください。';
  }
}
