# -*- coding: utf-8 -*-
# 調査結果（数値・出典）。 A=制度・統計 / B=法規制 / C=相場・費用・事例
KYUCHI = '2級地-1'
HOUSING_AID = 43_000
HOUSING_AID_2P = 52_000
SEIKATSU_65 = 72_490      # 生活扶助 単身65〜74歳 2級地-1（令和7年10月〜）
SEIKATSU_75 = 66_390
SEIKATSU_65_R8 = 73_490   # 令和8年10月〜（案）
CARE_KYUCHI = '6級地（上乗せ6%・訪問介護 10.42円/単位、令和6〜8年度）'
POP = 228_809; POP65 = 71_746; AGING = 0.313; AGING_2030 = 0.323; AGING_2040 = 0.367; AGING_SHOWA = 0.336
NINTEI_TOTAL_N = 14_154; NINTEI_3PLUS = 5_274; NINTEI_TOTAL = '14,154人（令和7年12月末）'
HOMON_COUNT_N = 59; HOMON_COUNT = '59'
HOMON_DENSITY_N = round(NINTEI_TOTAL_N / HOMON_COUNT_N); HOMON_DENSITY = f'{HOMON_DENSITY_N}人/所'
TOKUYO = 16; GH = 16; YURO_KAIGO = 9; YURO_JUTAKU = 11; SAKOJU = 25
FACILITY_N = TOKUYO + GH + YURO_KAIGO + YURO_JUTAKU
FACILITY_DENSITY_N = round(NINTEI_TOTAL_N / FACILITY_N)
FACILITY_DENSITY_SAKOJU_N = round(NINTEI_TOTAL_N / (FACILITY_N + SAKOJU))
SEIHO_HOUSEHOLDS = 2_946; SEIHO_PERSONS = 3_680; SEIHO_RATE = 16.3; SEIHO_RATE_LATEST = 16.6; SEIHO_RATE_PREF = 13.4; SEIHO_RATE_JP = 16.1
BREAKEVEN_RES = 6
AREA_OK_COUNT = 5
HAZARD_SUMMARY = '洪水浸水想定区域内。想定最大規模で浸水深0.5〜3.0m、浸水継続時間12時間未満、家屋倒壊等氾濫想定区域は該当なし（国交省ハザードマップタイルの地点判読＝推定。市ハザードマップ庄和地区面・浸水ナビで要確認）'
HAZARD_LEVEL = 'mid'
AID_AREA_RULE_TEXT = ('平成27年7月の住宅扶助見直しにより、<b>単身世帯</b>は住居の床面積に応じて限度額が減額される：<b>15㎡超＝満額（43,000円）／11〜15㎡＝▲10%（39,000円）／7〜10㎡＝▲20%（34,000円）／6㎡以下＝▲30%（30,000円）</b>（厚労省説明資料、埼玉県2級地への当てはめは二次資料の転記）。'
                      '無料低額宿泊所等の利用者には床面積別限度額は適用されない（社援保発0513第1号）。共用設備（台所・浴室・便所）分として8.5㎡を加算して判定するという説明が複数の二次資料にあるが一次資料では未確認のため、<b>春日部市生活支援課への事前照会事項</b>とする。'
                      '特定施設・GH向けの特別基準（1.3倍＝55,900円）は住宅型有料老人ホームの家賃には当然には適用されない。')
SP_RULE_TEXT = ('有料老人ホームは消防法施行令別表第一の<b>(6)項ロ</b>（避難が困難な要介護者＝要介護3〜5を「主として」＝定員の半数以上入居させるもの、消防予第81号）か<b>(6)項ハ</b>（それ以外）に区分される。'
  '<b>ロ</b>：スプリンクラー（令12条1項1号ロ・面積不問。規則12条の2の免除構造は「居室を準耐火構造の壁・床で区画＋内装準不燃＋防火戸」等で、2階に居室を置く木造既存住宅では成立しにくい）、自火報、自火報連動の火災通報装置、誘導灯、消火器がすべて必要。収容人員10人以上（入居9人＋従業者）で防火管理者選任・消防計画・年2回訓練。'
  '<b>ハ</b>：自火報（入居施設は面積不問）・誘導灯・消火器が中心で、SPと通報装置は不要（500㎡未満）。'
  '判定は入居者の要介護度の実態で変動するため、開設後に要介護3以上が半数を超えた時点でロの設備義務が発生する。元P/Lの「上限寄り＝要介護3中心」シナリオはロ判定と表裏一体である。')
KOJI_TAG='[公表]'; KOJI_NOTE='埼玉県地価調査 R7 基準地 西金野井字谷頭1704-32（一低専50/80・駅1.4km）。南桜井駅圏公示平均52,628円/㎡'
ROSENKA_TAG='[公表]'; ROSENKA_NOTE='国税庁 令和7年分 路線価図37153。東中野1523街区南側接面 43E（借地権割合50%）'
DEAL_TAG='[推定]'; DEAL_NOTE='基準地50,000円/㎡に駅距離▲5%・私道▲5〜8%・地目等▲2%を減価（40,000〜46,000円/㎡の中庸）'
DEMO_TAG='[実勢]'; DEMO_NOTE='春日部市実績35,285円/坪（2025）〜2026年5〜7万円/坪。本体125〜175万＋付帯で150〜250万円'
RENT_TAG='[実勢]'; RENT_NOTE='春日部市 築35〜47年・100㎡超戸建の賃料7.0〜8.5万円。本件は駅22分・現況で6.5〜8.0万円'
GH_TAG='[推定]'; GH_NOTE='中古戸建6室のGH借上げ15〜20万円/月（入居者家賃3.6〜3.7万円×6が上限を規定）'
SP_COST_TAG='[実勢]'; SP_COST_NOTE='特定施設水道連結型SP 100〜150㎡で200〜300万円（消防テック・建築×消防ラボ）。給水引込増径は別途'

# 出典一覧（別紙A）。(区分, タイトル, URL, 備考)
SOURCES_A = [
 ('制度','埼玉県「住宅扶助基準額（生活保護法）」（2級地 単身43,000円）','https://www.pref.saitama.lg.jp/a0602/seihozenpan/910-20091209-89.html','平成27年7月〜'),
 ('制度','春日部市「生活保護制度」（2級地-1）','https://www.city.kasukabe.lg.jp/soshikikarasagasu/seikatsushienka/gyomuannai/20/14534.html',''),
 ('制度','厚労省 説明資料「生活保護における住宅扶助基準の見直しについて」（床面積別減額）','https://saitama.zennichi.or.jp/honbu/wp-content/uploads/702af7cd142b2d868ce8ebf1da5e3a8a.pdf','全日埼玉本部掲載'),
 ('制度','厚労省 社援保発0513第1号「住宅扶助の認定にかかる留意事項について」（平成27年5月13日）','https://www.mhlw.go.jp/web/t_doc?dataId=00tc1034&dataType=1&pageNo=1','無低は床面積別限度額の適用外'),
 ('制度','厚労省「生活扶助基準額の算出方法（令和8年4月）」','https://www.mhlw.go.jp/content/001152601.pdf','2級地-1 単身65歳 72,490円'),
 ('制度','厚労省 第55回生活保護基準部会 資料4「令和8年度生活扶助基準の見直しについて」','https://www.mhlw.go.jp/content/12002000/001662704.pdf','令和8年10月〜 特例加算2,500円'),
 ('制度','厚労省 第224回介護給付費分科会 資料6「地域区分」（令和6年度〜 市町村一覧）','https://www.mhlw.go.jp/content/12300000/001146441.pdf','春日部市・越谷市 6級地'),
 ('制度','厚労省 第252回介護給付費分科会 資料2「地域区分について（報告）」','https://www.mhlw.go.jp/content/12300000/001623470.pdf','6級地 訪問介護10.42円・令和9年度見直し'),
 ('制度','厚労省「介護報酬の算定構造」（令和6年4月）','https://www.mhlw.go.jp/content/12300000/001195509.pdf','同一建物減算・特定事業所加算・訪問介護単位数'),
 ('制度','厚労省 老発0313第6号（令和8年3月13日）介護職員等処遇改善加算 事務処理手順','https://www.mhlw.go.jp/shogu-kaizen/download/6_tsuuchi_kihontekikangaekata_jimushoritejun.pdf','令和8年6月〜 Ⅱイ24.9%'),
 ('制度','厚労省「有料老人ホームにおける望ましいサービス提供のあり方に関する検討会」とりまとめ（令和7年11月5日）','https://www.mhlw.go.jp/content/12300000/001591085.pdf','囲い込み・登録制'),
 ('制度','全国有料老人ホーム協会 介護保険最新情報vol.1518（改正法 令和8年6月25日公布）','https://www.yurokyo.or.jp/info/view/6616','登録制は公布後2年以内'),
 ('制度','「生活保護法による介護扶助の運営要領について」社援第825号','https://www.mhlw.go.jp/web/t_doc?dataId=00ta8490&dataType=1&pageNo=1','ケアプラン確認・限度額内'),
 ('統計','春日部市統計書 令和8年版 第2章 人口','https://www.city.kasukabe.lg.jp/material/files/group/16/dai2syou2.xlsx',''),
 ('統計','春日部市 令和8年 人口・世帯数（月次）','https://www.city.kasukabe.lg.jp/soshikikarasagasu/shiseijohoka/gyomuannai/4/1/34916.html','令和8年8月1日 228,809人'),
 ('統計','第9期春日部市高齢者保健福祉計画及び介護保険事業計画（令和6年3月）','https://www.city.kasukabe.lg.jp/material/files/group/23/dai9kihokennhukusikeikakuissiki.pdf','圏域・推計・施設整備'),
 ('統計','春日部市統計書 第6章 6-9 要介護（要支援）認定者数の推移','https://www.city.kasukabe.lg.jp/material/files/group/16/dai6syou.xlsx','令和7年12月末 14,154人'),
 ('統計','埼玉県 指定事業所・施設一覧（令和8年8月1日）','https://www.pref.saitama.lg.jp/documents/32749/2026080102.xlsx','訪問介護59'),
 ('統計','埼玉県 有料老人ホーム一覧表（令和8年6月1日）','https://www.pref.saitama.lg.jp/documents/49465/r806-yuryo-list.xlsx','介護付9・住宅型12件'),
 ('統計','埼玉県 特別養護老人ホーム名簿','https://www.pref.saitama.lg.jp/documents/8505/tokuyoumibo.pdf','市内16施設'),
 ('統計','サービス付き高齢者向け住宅情報提供システム（春日部市）','https://www.satsuki-jutaku.mlit.go.jp/search/list.php?pref_code%5B%5D=11&city_code=11214','25棟1,037戸'),
 ('統計','埼玉県「埼玉県の生活保護」統計（市町村別保護率 令和7年11月速報）','https://www.pref.saitama.lg.jp/documents/20638/3-11sichosonbetuhogoritunojoukyo112025.pdf','春日部市16.6‰'),
 ('統計','春日部市 地域包括支援センター一覧','https://www.city.kasukabe.lg.jp/soshikikarasagasu/kaigohokenka/gyomuannai/1/5/3662.html','第8包括（庄和）'),
 ('統計','埼玉県 令和5年住宅・土地統計調査 県分概要','https://www.pref.saitama.lg.jp/documents/240159/jyutyo_saitamakenbun.pdf','春日部市 空き家率6.3%'),
]
SOURCES_B = [
 ('法規','建築基準法（e-Gov）別表第二(い)項三号・六号、6条1項、87条','https://laws.e-gov.go.jp/law/325AC0000000201','第一種低層で老人ホーム・寄宿舎可'),
 ('法規','建築基準法施行令（e-Gov）19条・114条2項・121条・126条の4・23条・128条の5','https://laws.e-gov.go.jp/law/325CO0000000338','児童福祉施設等＝有料老人ホーム'),
 ('法規','国交省リーフレット「小規模な建築物の用途変更の手続きが不要となりました」（2019年6月25日施行）','https://www.mlit.go.jp/common/001299734.pdf','200㎡以下'),
 ('法規','埼玉県建築基準法取扱集（令和5年9月7日版）','https://www.pref.saitama.lg.jp/documents/182701/toriatsukai230907.pdf','有老該当→老人ホーム、非該当→寄宿舎'),
 ('法規','埼玉県「建築行政の窓口」（春日部市＝特定行政庁）','https://www.pref.saitama.lg.jp/a1106/madoguti/madogutiannai.html',''),
 ('法規','国交省 国住指第1784号（平成26年告示860号 間仕切壁の緩和）','https://www.mlit.go.jp/common/001053547.pdf',''),
 ('法規','埼玉県有料老人ホーム設置運営指導指針（令和6年12月6日改正）','https://www.pref.saitama.lg.jp/documents/19824/kaiseigozennbunn2.pdf','居室13.2㎡・特例6(1)(3)・職員7(1)'),
 ('法規','埼玉県 有料老人ホーム設置要綱（令和4年4月1日）','https://www.pref.saitama.lg.jp/documents/19824/040401yuryo_youkou.pdf','事前相談→事前協議→設置届、着工は届出受理後'),
 ('法規','埼玉県 有料老人ホーム手続フロー図','https://www.pref.saitama.lg.jp/documents/19824/yuuryou-tetudukihuro-zu.pdf','着工6か月前/4か月前/1か月前'),
 ('法規','埼玉県 有料老人ホーム設置の手引き（令和6年4月）','https://www.pref.saitama.lg.jp/documents/19824/yuuryou-tebiki-0604kaisei.pdf','審査2週間〜1か月'),
 ('法規','消防法施行令（e-Gov）別表第一・10条・12条・21条・23条・26条・1条の2・35条','https://laws.e-gov.go.jp/law/336CO0000000037',''),
 ('法規','消防法施行規則（e-Gov）5条5項・12条の2・25条・28条の2','https://laws.e-gov.go.jp/law/336M50000008006','要介護3〜5＝避難困難'),
 ('法規','日本消防設備安全センター 福祉施設の防火対策（(6)項ロ／ハの判定、消防予第81号）','https://www.fesc.or.jp/ihanzesei/data/pdf/fukushi_bouka2.pdf','定員の半数以上'),
 ('法規','消防庁 スプリンクラー免除構造（規則12条の2）検討資料','https://www.fdma.go.jp/singi_kento/kento/items/kento133_33_shiryo4-4.pdf',''),
 ('法規','春日部市消防本部 予防課（住宅用火災警報器・火災予防条例）','https://www.city.kasukabe.lg.jp/soshikikarasagasu/yoboka/gyomuannai/2/2/1/5988.html','048-738-3117'),
 ('法規','埼玉県建築基準法施行条例と解説（令和7年9月25日版）','https://www.pref.saitama.lg.jp/documents/183175/saitamakenjyourei_ver20250925.pdf','老人ホーム固有の接道規定なし'),
 ('法規','埼玉県福祉のまちづくり条例 施行規則 別表第三（令和7年6月1日）','https://www.pref.saitama.lg.jp/documents/12467/070601fukumachi_beppyo3.pdf','老人ホームは規模不問で届出'),
 ('法規','埼玉県福祉のまちづくり条例 届出窓口（春日部市建築課）','https://www.pref.saitama.lg.jp/b1105/hukumachi-todokede-madoguchi.html',''),
 ('法規','水防法（e-Gov）15条の3','https://laws.e-gov.go.jp/law/324AC0000000193','避難確保計画'),
 ('法規','春日部市 要配慮者利用施設の避難確保計画','https://www.city.kasukabe.lg.jp/soshikikarasagasu/bosaitaisakuka/gyomuannai/3/1/5900.html','対象一覧に有料老人ホーム区分'),
 ('法規','春日部市 災害ハザードマップ（令和3年3月）','https://www.city.kasukabe.lg.jp/soshikikarasagasu/bosaitaisakuka/gyomuannai/3/5880.html',''),
 ('法規','国交省 ハザードマップポータル（重ねるハザードマップ）','https://disaportal.gsi.go.jp/','地点判読に使用'),
 ('法規','老人福祉法（e-Gov）29条・40条','https://laws.e-gov.go.jp/law/338AC0000000133','有料老人ホームの定義・無届罰則'),
 ('法規','厚労省 介護保険最新情報Vol.1518（令和8年法律第51号 公布通知）','https://www.mhlw.go.jp/content/001715668.pdf','登録有料老人ホーム事業'),
 ('法規','厚労省 第16回 有料老人ホーム指導状況等フォローアップ調査','https://www.mhlw.go.jp/content/12304250/001513174.pdf','未届584件・埼玉県所管11件'),
 ('法規','埼玉県 被保護者等住居・生活サービス提供事業条例（令和7年7月4日改正）','https://www.pref.saitama.lg.jp/documents/20667/r70901jourei.pdf','無低 居室7.43㎡・定員5人以上'),
 ('法規','国交省 住宅セーフティネット法 登録基準告示（令和7年10月1日施行）','https://www.mlit.go.jp/jutakukentiku/house/content/001913788.pdf','共同居住型 15A+10㎡・専用9㎡'),
 ('法規','不動産登記法（e-Gov）37条・164条','https://laws.e-gov.go.jp/law/416AC0000000123','地目変更1か月・過料10万円'),
 ('法規','日本土地家屋調査士会連合会 報酬ガイド（2022年度）','https://www.chosashi.or.jp/media/hoshuguide_single_r04.pdf','地目変更 平均46,589円'),
 ('法規','日本法令索引 昭和55年政令第196号（新耐震基準・昭和56年6月1日施行）','https://hourei.ndl.go.jp/simple/detail?lawId=0000068884&current=-1',''),
 ('法規','民法（e-Gov）562条・566条・572条／宅建業法40条・35条','https://laws.e-gov.go.jp/law/129AC0000000089','契約不適合責任'),
 ('法規','指定障害福祉サービス基準省令 210条（共同生活援助）','https://laws.e-gov.go.jp/law/418M60000100171','居室7.43㎡・定員10人以下'),
 ('法規','埼玉県 共同生活援助 指定の手引（令和8年7月）','https://www.pref.saitama.lg.jp/documents/32595/shiteinotebikir807.pdf',''),
 ('法規','春日部市 第7期障害福祉計画','https://www.city.kasukabe.lg.jp/material/files/group/24/dai7kikasukabeshishougaihukushikeikaku.pdf','GH 目標49→実績78か所・空室'),
 ('法規','春日部市 開発事業の手続及び基準に関する条例','https://www.kasukabe-shigikai.jp/voices/GikaiDoc/attach/Gk/Gk1075_94.pdf','特定開発事業 非該当'),
 ('法規','春日部市 空き家リノベーション助成制度','https://www.city.kasukabe.lg.jp/kurashi/sumai/akiyataisaku/10465.html','住宅・店舗用途に限定'),
]
SOURCES_C = []
