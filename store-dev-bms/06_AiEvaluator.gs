/**
 * 店舗開発部 業務管理システム - AI評価・レポート生成（Block B）
 */

/**
 * 全メンバーの月次評価を実行
 */
function runMonthlyEvaluations() {
  var lock = LockService.getScriptLock();
  if (!lock.tryLock(10000)) {
    logWarn_('月次評価: ロック取得失敗（別プロセス実行中）');
    return;
  }

  try {
    var now = new Date();
    var year = now.getFullYear();
    var month = now.getMonth() + 1;
    var members = getActiveMembers_();

    logInfo_('月次評価開始: ' + year + '年' + month + '月 (' + members.length + '名)');

    for (var i = 0; i < members.length; i++) {
      try {
        evaluateMember_(members[i].name, year, month);
        // API制限対策: 1.5秒待機
        Utilities.sleep(1500);
      } catch (e) {
        logError_('月次評価エラー(' + members[i].name + '): ' + e.message);
      }
    }

    logInfo_('月次評価完了: ' + year + '年' + month + '月');
  } finally {
    lock.releaseLock();
  }
}

/**
 * 指定メンバーの月次評価を実行
 * @param {string} memberName
 * @param {number} year
 * @param {number} month
 */
function evaluateMember_(memberName, year, month) {
  // データ収集
  var data = collectMonthlyData_(memberName, year, month);

  if (data.dailySummaries.length === 0) {
    logWarn_('月次評価スキップ(' + memberName + '): 日報データなし');
    return;
  }

  // プロンプト構築
  var prompt = buildEvalPrompt_(memberName, year, month, data);

  // AI API呼び出し
  var evalResult = callAiApi_(prompt);
  if (!evalResult) {
    logError_('月次評価エラー(' + memberName + '): AI API応答なし');
    return;
  }

  // レスポンス解析
  var parsed = parseEvalResponse_(evalResult);

  // Google Docsレポート生成
  var reportUrl = generateEvalReport_(memberName, year, month, parsed);

  // 月次目標シートに結果書き込み
  writeMonthlyEvalResult_(memberName, year, month, parsed.score, parsed.summary, reportUrl);

  logInfo_('月次評価完了: ' + memberName + ' (スコア: ' + parsed.score + ')');
}

/**
 * 評価プロンプトを構築
 */
function buildEvalPrompt_(memberName, year, month, data) {
  var summariesText = '';
  for (var i = 0; i < data.dailySummaries.length; i++) {
    var s = data.dailySummaries[i];
    summariesText += s.date + '(' + s.dayOfWeek + '): ' + s.summary + '\n';
  }

  var goalsText = 'メイン目標: ' + (data.mainGoal || '未設定') + '\n';
  if (data.subGoals.length > 0) {
    goalsText += 'サブ目標:\n';
    for (var j = 0; j < data.subGoals.length; j++) {
      goalsText += '- ' + data.subGoals[j] + '\n';
    }
  }
  goalsText += '自己申告達成度: ' + data.achievement + '%\n';

  return 'あなたは店舗開発部のマネジメント支援AIです。以下のメンバーの月次評価を行ってください。\n\n' +
    '対象者: ' + memberName + '\n' +
    '対象月: ' + year + '年' + month + '月\n\n' +
    '【月次目標】\n' + goalsText + '\n' +
    '【日報データ（日次所感サマリー）】\n' + summariesText + '\n\n' +
    '以下の7つのセクションに分けて評価を記述してください。各セクションは「◆①」「◆②」...の形式で始めてください。\n\n' +
    '◆① 今月の目標と達成度（出店進捗）\n' +
    '◆② 今月のアウトプット\n' +
    '◆③ 今月の成果\n' +
    '◆④ 課題（構造整理）\n' +
    '◆⑤ 成長した点（行動の変化）\n' +
    '◆⑥ 来月に向けたToDo\n' +
    '◆⑦ バリュー体現・自己評価（Open / Professional / Top speed / One team）\n\n' +
    '最後に、100点満点での総合スコアを「【総合スコア】XX点」の形式で記述してください。\n' +
    '1行で要約コメントも「【要約】...」の形式で記述してください。';
}

/**
 * AI APIを呼び出し
 * @param {string} prompt
 * @return {string|null} 応答テキスト
 */
function callAiApi_(prompt) {
  // Anthropic APIを試行
  var anthropicKey = getPropertySafe_(PROP_KEYS.ANTHROPIC_API_KEY);
  if (anthropicKey) {
    var result = callAnthropicApi_(prompt, anthropicKey);
    if (result) return result;
    logWarn_('Anthropic API失敗、フォールバック確認中...');
  }

  // フォールバック: Slack AI Bot（設定があれば）
  logWarn_('AI API: 使用可能なプロバイダなし。Anthropic APIキーを設定してください。');
  return null;
}

/**
 * Anthropic APIを呼び出し
 * @param {string} prompt
 * @param {string} apiKey
 * @return {string|null}
 */
function callAnthropicApi_(prompt, apiKey) {
  try {
    var payload = {
      model: AI_CONFIG.ANTHROPIC_MODEL,
      max_tokens: AI_CONFIG.MAX_TOKENS,
      messages: [
        { role: 'user', content: prompt }
      ]
    };

    var options = {
      method: 'post',
      contentType: 'application/json',
      headers: {
        'x-api-key': apiKey,
        'anthropic-version': AI_CONFIG.ANTHROPIC_VERSION
      },
      payload: JSON.stringify(payload),
      muteHttpExceptions: true
    };

    var response = UrlFetchApp.fetch(AI_CONFIG.ANTHROPIC_API_URL, options);
    var code = response.getResponseCode();

    if (code !== 200) {
      logError_('Anthropic API エラー (HTTP ' + code + '): ' + response.getContentText().substring(0, 200));
      return null;
    }

    var json = JSON.parse(response.getContentText());
    if (json.content && json.content.length > 0) {
      return json.content[0].text;
    }
    return null;
  } catch (e) {
    logError_('Anthropic API 例外: ' + e.message);
    return null;
  }
}

/**
 * AI応答を解析
 * @param {string} responseText
 * @return {Object} {sections: Array, score: number, summary: string}
 */
function parseEvalResponse_(responseText) {
  var result = {
    sections: [],
    score: 0,
    summary: '',
    fullText: responseText
  };

  // 7セクションを抽出
  for (var i = 1; i <= 7; i++) {
    var marker = '◆' + ['①','②','③','④','⑤','⑥','⑦'][i-1];
    var nextMarker = i < 7 ? '◆' + ['①','②','③','④','⑤','⑥','⑦'][i] : '【総合スコア】';
    var startIdx = responseText.indexOf(marker);
    var endIdx = responseText.indexOf(nextMarker);

    if (startIdx !== -1) {
      var sectionText = endIdx !== -1
        ? responseText.substring(startIdx, endIdx).trim()
        : responseText.substring(startIdx).trim();
      result.sections.push({
        title: REPORT_SECTIONS[i-1],
        content: sectionText.replace(marker, '').trim()
      });
    }
  }

  // スコア抽出
  var scoreMatch = responseText.match(/【総合スコア】(\d+)点/);
  if (scoreMatch) {
    result.score = parseInt(scoreMatch[1], 10);
  }

  // 要約抽出
  var summaryMatch = responseText.match(/【要約】(.+)/);
  if (summaryMatch) {
    result.summary = summaryMatch[1].trim();
  }

  return result;
}

/**
 * Google Docsで月次評価レポートを生成
 * @param {string} memberName
 * @param {number} year
 * @param {number} month
 * @param {Object} parsed - parseEvalResponse_の結果
 * @return {string} Google DocsのURL
 */
function generateEvalReport_(memberName, year, month, parsed) {
  var title = '月次評価レポート_' + memberName + '_' + year + '年' + ('0' + month).slice(-2) + '月';

  var doc = DocumentApp.create(title);
  var body = doc.getBody();

  // タイトル
  body.appendParagraph(title)
    .setHeading(DocumentApp.ParagraphHeading.HEADING1)
    .setAlignment(DocumentApp.HorizontalAlignment.CENTER);

  // メタ情報
  body.appendParagraph('対象者: ' + memberName + '　｜　対象月: ' + year + '年' + month + '月　｜　評価日: ' + formatDate_(new Date()));
  body.appendHorizontalRule();

  // 総合スコア
  if (parsed.score > 0) {
    body.appendParagraph('総合スコア: ' + parsed.score + ' / 100点')
      .setHeading(DocumentApp.ParagraphHeading.HEADING2);
  }
  if (parsed.summary) {
    body.appendParagraph(parsed.summary)
      .setItalic(true);
  }
  body.appendParagraph('');

  // 各セクション
  for (var i = 0; i < parsed.sections.length; i++) {
    var section = parsed.sections[i];
    body.appendParagraph('◆' + ['①','②','③','④','⑤','⑥','⑦'][i] + ' ' + section.title)
      .setHeading(DocumentApp.ParagraphHeading.HEADING2);
    body.appendParagraph(section.content);
    body.appendParagraph('');
  }

  // フッター
  body.appendHorizontalRule();
  body.appendParagraph('※ このレポートはAI（Anthropic Claude）により自動生成されたものです。')
    .setFontSize(9)
    .setForegroundColor('#888888');

  doc.saveAndClose();

  // 指定フォルダに移動
  var folderId = getPropertySafe_(PROP_KEYS.REPORT_FOLDER_ID);
  if (folderId) {
    try {
      var file = DriveApp.getFileById(doc.getId());
      var folder = DriveApp.getFolderById(folderId);
      file.moveTo(folder);
    } catch (e) {
      logWarn_('レポートのフォルダ移動に失敗: ' + e.message);
    }
  }

  var url = doc.getUrl();
  logInfo_('月次評価レポート生成: ' + title + ' (' + url + ')');
  return url;
}
