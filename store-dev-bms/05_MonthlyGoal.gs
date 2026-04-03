/**
 * 店舗開発部 業務管理システム - 月次目標・評価シート（Block B）
 */

/**
 * 今月の月次目標シートを生成
 */
function generateCurrentMonthlyGoalSheet() {
  var now = new Date();
  var year = now.getFullYear();
  var month = now.getMonth() + 1;
  var members = getActiveMembers_();
  var ss = getSpreadsheet_();

  var sheetName = getMonthlySheetName_(year, month);
  if (ss.getSheetByName(sheetName)) {
    SpreadsheetApp.getUi().alert(sheetName + ' は既に存在します。');
    return;
  }

  createMonthlyGoalSheet_(ss, year, month, members);
  SpreadsheetApp.getUi().alert(sheetName + ' を作成しました。');
}

/**
 * 月次目標シートを作成
 * @param {SpreadsheetApp.Spreadsheet} ss
 * @param {number} year
 * @param {number} month
 * @param {Array<Object>} members
 */
function createMonthlyGoalSheet_(ss, year, month, members) {
  var sheetName = getMonthlySheetName_(year, month);
  if (ss.getSheetByName(sheetName)) return;

  var sheet = ss.insertSheet(sheetName);

  // タイトル
  sheet.getRange(1, 1).setValue('月次目標・評価 - ' + year + '年' + month + '月');
  sheet.getRange(1, 1).setFontSize(14).setFontWeight('bold');

  // ヘッダー
  var headers = ['メンバー名', 'メイン目標', 'サブ目標1', 'サブ目標2', 'サブ目標3',
    '達成度(%)', 'AI評価スコア', 'AI評価コメント', '評価レポートURL', '評価日時'];
  sheet.getRange(3, 1, 1, headers.length).setValues([headers]);
  sheet.getRange(3, 1, 1, headers.length)
    .setFontWeight('bold')
    .setBackground('#4a86c8')
    .setFontColor('white');

  // メンバー名を展開
  var rows = [];
  for (var i = 0; i < members.length; i++) {
    var row = new Array(headers.length).fill('');
    row[MONTHLY_COLS.MEMBER_NAME] = members[i].name;
    rows.push(row);
  }

  if (rows.length > 0) {
    sheet.getRange(4, 1, rows.length, headers.length).setValues(rows);
  }

  // 達成度列のドロップダウン
  var achRule = SpreadsheetApp.newDataValidation()
    .requireNumberBetween(0, 100)
    .setAllowInvalid(true)
    .build();
  sheet.getRange(4, MONTHLY_COLS.ACHIEVEMENT + 1, members.length, 1).setDataValidation(achRule);

  // 列幅
  sheet.setColumnWidth(1, 120);
  sheet.setColumnWidth(2, 300);
  sheet.setColumnWidth(3, 200);
  sheet.setColumnWidth(4, 200);
  sheet.setColumnWidth(5, 200);
  sheet.setColumnWidth(6, 80);
  sheet.setColumnWidth(7, 100);
  sheet.setColumnWidth(8, 400);
  sheet.setColumnWidth(9, 250);
  sheet.setColumnWidth(10, 150);

  sheet.setFrozenRows(3);

  logInfo_('月次目標シート作成: ' + sheetName);
}

/**
 * 指定メンバーの月次データを収集
 * @param {string} memberName
 * @param {number} year
 * @param {number} month
 * @return {Object} {dailySummaries, mainGoal, subGoals, achievement}
 */
function collectMonthlyData_(memberName, year, month) {
  var ss = getSpreadsheet_();
  var result = {
    dailySummaries: [],
    mainGoal: '',
    subGoals: [],
    achievement: 0
  };

  // 日報データ収集
  var dailySheet = ss.getSheetByName(getDailySheetName_(memberName));
  if (dailySheet) {
    var lastRow = dailySheet.getLastRow();
    if (lastRow >= DAILY_DATA_START_ROW) {
      var data = dailySheet.getRange(DAILY_DATA_START_ROW, 1, lastRow - DAILY_DATA_START_ROW + 1, DAILY_TOTAL_COLS).getValues();
      for (var i = 0; i < data.length; i++) {
        var date = data[i][DAILY_COLS.DATE];
        var summary = data[i][DAILY_COLS.SUMMARY];
        if (date instanceof Date && summary) {
          result.dailySummaries.push({
            date: formatDate_(date),
            dayOfWeek: data[i][DAILY_COLS.DAY_OF_WEEK],
            summary: String(summary),
            workHours: data[i][DAILY_COLS.WORK_HOURS]
          });
        }
      }
    }
  }

  // 月次目標データ収集
  var monthlySheetName = getMonthlySheetName_(year, month);
  var monthlySheet = ss.getSheetByName(monthlySheetName);
  if (monthlySheet) {
    var lastRow2 = monthlySheet.getLastRow();
    if (lastRow2 >= 4) {
      var goalData = monthlySheet.getRange(4, 1, lastRow2 - 3, 10).getValues();
      for (var j = 0; j < goalData.length; j++) {
        if (goalData[j][MONTHLY_COLS.MEMBER_NAME] === memberName) {
          result.mainGoal = goalData[j][MONTHLY_COLS.MAIN_GOAL] || '';
          result.subGoals = [
            goalData[j][MONTHLY_COLS.SUB_GOAL_1],
            goalData[j][MONTHLY_COLS.SUB_GOAL_2],
            goalData[j][MONTHLY_COLS.SUB_GOAL_3]
          ].filter(function(g) { return g; });
          result.achievement = goalData[j][MONTHLY_COLS.ACHIEVEMENT] || 0;
          break;
        }
      }
    }
  }

  return result;
}

/**
 * 月次目標シートのAI評価結果を書き込み
 * @param {string} memberName
 * @param {number} year
 * @param {number} month
 * @param {number} score
 * @param {string} comment
 * @param {string} reportUrl
 */
function writeMonthlyEvalResult_(memberName, year, month, score, comment, reportUrl) {
  var ss = getSpreadsheet_();
  var monthlySheetName = getMonthlySheetName_(year, month);
  var sheet = ss.getSheetByName(monthlySheetName);
  if (!sheet) return;

  var lastRow = sheet.getLastRow();
  if (lastRow < 4) return;

  var names = sheet.getRange(4, 1, lastRow - 3, 1).getValues();
  for (var i = 0; i < names.length; i++) {
    if (names[i][0] === memberName) {
      var row = i + 4;
      sheet.getRange(row, MONTHLY_COLS.AI_SCORE + 1).setValue(score);
      sheet.getRange(row, MONTHLY_COLS.AI_COMMENT + 1).setValue(comment);
      sheet.getRange(row, MONTHLY_COLS.REPORT_URL + 1).setValue(reportUrl);
      sheet.getRange(row, MONTHLY_COLS.EVAL_DATE + 1).setValue(new Date());
      return;
    }
  }
}
