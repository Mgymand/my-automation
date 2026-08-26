# -*- coding: utf-8 -*-
import sys, os, html
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from model import *

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'out')
def y(v):  return f"{round(v):,}"
def man(v):
    m = v/10000
    if abs(m) < 1:    return '%s円' % y(v)
    if abs(m) < 1000: return '%s万円' % f"{m:,.1f}"
    return '%s万円' % f"{m:,.0f}"
def pc(v, d=1): return ('%.*f%%' % (d, v*100))

CSS = """
@page { size: A4; margin: 9mm 9mm 8mm 9mm; }
* { box-sizing: border-box; }
body { font-family: "IPAGothic","IPAPGothic",sans-serif; font-size: 7.7pt; line-height:1.34;
       color:#1a1d21; margin:0; }
h1 { font-size: 12.6pt; margin:0 0 .7mm; letter-spacing:.01em; }
.sub { font-size:7pt; color:#5b6470; margin:0; }
.hdr { border-bottom:2pt solid #16304d; padding-bottom:1.6mm; margin-bottom:2mm;
       display:flex; justify-content:space-between; align-items:flex-end; gap:6mm;}
.badge { background:#16304d; color:#fff; font-size:7.6pt; padding:1mm 2.6mm; border-radius:1mm;
         white-space:nowrap; font-weight:bold;}
h2 { font-size:8.8pt; margin:2mm 0 .9mm; padding-left:2mm; border-left:2.6pt solid #16304d;
     color:#16304d; }
h2:first-of-type{margin-top:1mm}
table { width:100%; border-collapse:collapse; font-size:7.2pt; }
th,td { border:0.35pt solid #c3cbd4; padding:0.6mm 1.1mm; vertical-align:middle; }
th { background:#eef2f6; font-weight:bold; text-align:left; color:#2a3540; }
td.n, th.n { text-align:right; font-variant-numeric:tabular-nums; }
td.c, th.c { text-align:center; }
tr.tot td { background:#f5f8fb; font-weight:bold; }
tr.hi td { background:#fff8e6; }
.pos { color:#0a6b3d; font-weight:bold; }
.neg { color:#b3261e; font-weight:bold; }
.two { display:flex; gap:2.6mm; }
.two > * { flex:1; min-width:0; }
.kpi { display:flex; gap:1.4mm; margin:1.4mm 0; }
.kpi div { flex:1; border:0.4pt solid #c3cbd4; border-top:2pt solid #16304d; padding:1.2mm 1.5mm;
           background:#fbfcfd; }
.kpi .l { font-size:6.4pt; color:#5b6470; display:block; line-height:1.25; }
.kpi .v { font-size:10.2pt; font-weight:bold; display:block; margin-top:.4mm; letter-spacing:-.01em;}
.kpi .s { font-size:6.2pt; color:#77808c; display:block; }
.warn { border:0.5pt solid #d4a017; background:#fffaeb; padding:1.4mm 2mm; margin:1.4mm 0;
        font-size:7pt; line-height:1.42; }
.warn b { color:#8a5a00; }
.note { font-size:6.3pt; color:#6b7480; margin:0.8mm 0 0; line-height:1.35; }
ul { margin:.5mm 0 0; padding-left:3.4mm; }
li { margin-bottom:.35mm; }
.concl { border:0.5pt solid #16304d; background:#f3f7fb; padding:1.8mm 2.4mm; margin-top:1.6mm; }
.concl h3 { margin:0 0 .7mm; font-size:8.4pt; color:#16304d; }
.pb { page-break-before: always; }
.foot { margin-top:1.4mm; border-top:0.35pt solid #c3cbd4; padding-top:.8mm; font-size:5.5pt; color:#8a929c; }
.tag { display:inline-block; font-size:6.6pt; padding:.3mm 1.4mm; border-radius:.8mm;
       background:#e6ebf1; color:#3c4855; margin-left:1mm;}
.tag.est { background:#fdecec; color:#a03028; }
.tag.act { background:#e4f3ea; color:#0a6b3d; }
"""

def kpi(items):
    s = '<div class="kpi">'
    for l, v, sub, cls in items:
        s += f'<div><span class="l">{l}</span><span class="v {cls}">{v}</span><span class="s">{sub}</span></div>'
    return s + '</div>'

# ---------- 定性比較（共通） ----------
QUAL = [
 ('初期資金・資金拘束','小さい。保証金・礼金・仲介・保証料の計{RENT_INIT}＋内装等{COMMON}＝<b>{RENT_TOT}</b>。解約時に保証金の8割が戻る','大きい。物件代金＋諸費用{BUY_TOKA}＋内装等{COMMON}＝<b>{BUY_TOT}</b>を一括拘束'),
 ('月々の固定費','賃料24.0万円＋火災保険で<b>月24.3万円</b>。更新のたびに増額交渉リスク','管理費・修繕積立金・固都税・保険・修繕予備で<b>月{HOYUU}</b>。賃料値上げも立退きもない'),
 ('造作・レイアウトの自由度','貸主承諾が必要。給排水・換気ダクト・電気容量の増設、床壁の躯体加工、看板位置に制約。<b>退去時は原状回復義務（約80万円）</b>','<b>自社所有のため造作は自由</b>。シャンプー台・給排水・24時間換気・分電盤増設・サイン計画を将来の業態変更まで見据えて施工でき、原状回復義務もない'),
 ('撤退・移転の柔軟性','<b>高い</b>。解約予告6ヶ月程度で退去可能。不採算なら傷が浅い','低い。売却に数ヶ月〜、売却価格は市況次第。撤退コストが読みにくい'),
 ('出口（事業売却時）','店舗の営業権・加盟契約のみが売却対象。買い手は別途物件を手当てする必要があり、<b>成約のハードルが上がる</b>','<b>加盟契約・営業権と物件をセットで売却できる</b>。買い手は即営業開始でき評価が上がりやすく、事業譲渡益に加えて<b>不動産の売却益（値上がり分）も取り込める</b>'),
 ('損益計算書への影響','家賃 年約291万円が全額損金。利益を圧縮し法人税は軽くなる','損金は減価償却{SHOU}／年（{SHOUNEN}年間）＋保有コスト{HOYUUY}／年。物件代金は資産計上され、<b>自己資本・与信・担保余力が増える</b>'),
 ('修繕・老朽化リスク','建物の大規模修繕・共用部は貸主負担が基本','<b>自己負担</b>。修繕積立金の値上げ・一時金徴収・専有部設備更新のリスクを負う'),
 ('資産価格の変動','負わない（そのかわり値上がり益も得られない）','負う。下落すれば含み損、上昇すれば含み益。<b>立川は駅前再開発が進む商圏で土地値の下支えが期待できる</b>'),
]

BUY_MERIT = """
<ol style="margin:.5mm 0 0;padding-left:3.8mm">
<li><b>造作が自由</b> — 貸主承諾・原状回復義務がないため、給排水/換気/電気容量/サイン計画を「10年使う店」の設計で一度に作り込める。眉毛サロンから将来アイラッシュ・脱毛等へ業態を広げる際も改装が自由。賃貸なら退去時に発生する新店舗の原状回復費（約80万円）も不要。</li>
<li><b>事業ごと売却して売却益を取れる</b> — 加盟契約（FC権）・営業権・スタッフ・顧客基盤に<b>物件をセットで</b>譲渡できる。買い手は物件探し・契約審査・内装工事を省いて即日営業を開始でき、そのぶん譲渡価格が付きやすい。出口では「事業譲渡益」＋「不動産の売却代金（含み益があればその分）」の<b>二階建てで回収</b>できる。賃貸では店舗を畳めば内装は原状回復で消えるだけ。</li>
<li><b>コストが固定される</b> — 賃料改定・更新料・立退き要求がない。10年・20年と続ける前提なら、インフレ局面ほど購入が効いてくる。</li>
<li><b>バランスシートが厚くなる</b> — 物件は資産計上され、自己資本と担保余力が増える。次の出店資金を借りる際の与信にプラス。</li>
</ol>"""

def qual_table(d, res):
    r = res['r']
    common = NAISOU+GENJOU_KYU+HIKKOSHI
    repl = dict(RENT_INIT=man(r['shokihiyou']), COMMON=man(common),
                RENT_TOT=man(r['shokihiyou']+common), BUY_TOKA=man(d['toka']),
                BUY_TOT=man(d['initial_buy']), HOYUU=man(d['hoyuu_m']).replace('万円','.0万円') if False else ('%.1f万円'%(d['hoyuu_m']/10000)),
                SHOU=man(d['shoukyaku_y']), SHOUNEN=str(d['shou_nen']), HOYUUY=man(d['hoyuu_y']))
    rows=''
    for k, a, b in QUAL:
        rows += '<tr><th style="width:20%%">%s</th><td style="width:37%%">%s</td><td>%s</td></tr>' % (
            k, a.format(**repl), b.format(**repl))
    return '<table><tr><th style="width:20%">観点</th><th style="width:37%">賃貸（月24万円）</th><th>売買（現金一括購入）</th></tr>'+rows+'</table>'

# ---------- 物件別の個別コメント ----------
SPECIFIC = {
 'A': dict(
  verdict='購入は「10年純資産」では有利だが、キャッシュ回収は21年超。<b>用途制限（事務所利用不可）が解消できなければ検討対象外</b>',
  verdict_cls='neg',
  warn='<b>【最重要】この物件は図面に「事務所利用 不可」と明記されています。</b>分譲マンションの管理規約上、'
       'サロン（美容所）としての営業はほぼ認められません。まず管理組合に用途変更の可否を照会し、'
       '書面で可否を取得するまでは本試算は「仮に営業できた場合」の参考値です。'
       'あわせて保健所の美容所登録（構造設備基準：区画・洗場・採光換気等）の適合確認が必要です。',
  strong=['<b>新耐震基準</b>（昭和58年4月築）。融資・保険・将来売却で不利になりにくい',
          '<b>修繕積立金 総額 4,263万円／44戸＝約97万円/戸</b>と潤沢。大規模修繕も平成31年に実施済、'
          '共用給排水管も平成28年に更新済で、当面の一時金リスクが小さい',
          '管理費＋修繕積立金＋組合費が<b>月23,400円（417円/㎡）</b>と割安。保有コストが軽い',
          '<b>固都税は年81,100円の実額開示</b>（令和7年度）。推計誤差がない',
          '専有56.14㎡（約17.0坪）＝ブース2台＋待合・カウンセリング室を確保しやすい',
          'オートロック・内廊下・宅配BOX・防犯カメラ・管理員週6日。女性客の来店動線として印象が良い'],
  weak=['<b>事務所利用不可</b>（上記警告）。ペット不可と併記され、居住専用色が強い',
        '㎡単価 <b>801,389円</b>。同駅徒歩7分のB物件（412,071円/㎡）の<b>約1.9倍</b>。'
        '住居としてリノベーション済（令和8年9月完成予定）のプレミアムが乗っており、'
        '<b>サロンに転用するとその内装費は大半が無駄になる</b>',
        '単純回収年数 <b>21.2年</b>。10年の勘定は「最後に物件が残る」ことで成立しており、'
        '売却できなければ回収できない',
        '取引態様「売主」と「手数料3%」が併記。仲介手数料155万円の要否を必ず確認（不要なら投下資金が155万円減る）'],
 ),
 'B': dict(
  verdict='<b>投資効率は明確に良好</b>（単純回収9.9年・実質利回り10.1%）。旧耐震と管理規約の用途制限がクリアできるかが唯一の関門',
  verdict_cls='pos',
  warn='<b>【要確認】分譲マンションのため、管理規約でサロン（美容所）営業が認められるか未確認です。</b>'
       '用途地域は商業地域で行政上の制約はありませんが、区分所有の管理規約が「住宅専用」であれば営業できません。'
       'また<b>1981年5月築で旧耐震基準の可能性が高く</b>、耐震診断・改修の有無、将来の売却・融資・地震保険料に影響します。'
       '保健所の美容所登録（構造設備基準）の適合確認も必要です。',
  strong=['<b>㎡単価 412,071円</b>。A物件の約1/2で、駅距離（徒歩7分）はほぼ同等。'
          '投下資金が<b>2,105万円</b>とAの44%で済む',
          '<b>単純回収年数 9.9年・実質利回り 10.1%</b>（家賃24万円回避ベース）。'
          '10年でキャッシュベースでも賃貸を上回る（+333万円）',
          '<b>商業地域・防火地域</b>。店舗用途に対する行政上の制約が最も緩い区分',
          '<b>賃貸が有利に反転する分岐点は「余剰資金を年12.1%で回せるか」</b>。'
          'Aの4.99%より高く、購入判断が下振れに強い',
          '新規リフォーム済（水回り3点・建具・給湯器・インターホン交換）で、'
          '躯体側の追加投資が当面小さい'],
  weak=['<b>1981年5月築＝旧耐震の可能性が高い</b>（新耐震は建築確認1981年6月1日以降）。'
        '出口で買い手の融資が付きにくく、10年後の売却価格が読みにくい',
        '<b>管理費＋修繕積立金 月34,800円（724円/㎡）とA物件の1.7倍。</b>'
        '築45年・総戸数26戸の小規模マンションで、修繕積立金の値上げ・一時金徴収リスクがある'
        '（積立総額は未開示 → <b>要・重要事項調査報告書</b>）',
        '専有48.05㎡（約14.5坪）でAより8.1㎡狭い。ブース2台＋待合は組めるがバックヤードが窮屈',
        '<b>固都税は未開示のため年69,432円と推計</b>（A物件の㎡単価で按分）。実額で要検証',
        '「広告不可」の非公開物件。相場比較の材料が乏しく、価格妥当性の検証がしにくい'],
 ),
}

def build_html(key):
    p = PROPS[key]; d = build(p); res = compare(d); r = res['r']
    sp = SPECIFIC[key]
    common = NAISOU+GENJOU_KYU+HIKKOSHI
    rent_tot = r['shokihiyou']+common
    est = lambda b: '<span class="tag est">推計</span>' if b else '<span class="tag act">実額</span>'

    # --- 資金計画表 ---
    shikin = f"""<table>
<tr><th style="width:34%">項目</th><th class="n" style="width:20%">賃貸</th><th class="n" style="width:20%">売買（現金一括）</th><th>備考</th></tr>
<tr><td>物件代金</td><td class="n">—</td><td class="n">{y(d['price'])}</td><td>販売価格（税込）</td></tr>
<tr><td>保証金（{KANRI_M}ヶ月）</td><td class="n">{y(r['hoshoukin'])}</td><td class="n">—</td><td>解約時 {pc(1-SHOUKYAKU,0)} 返還想定</td></tr>
<tr><td>礼金・仲介・保証会社</td><td class="n">{y(r['reikin']+r['chukai']+r['hoshougaisha'])}</td><td class="n">—</td><td>各1ヶ月（仲介は税込1.1）</td></tr>
<tr><td>仲介手数料</td><td class="n">—</td><td class="n">{y(d['chukai'])}</td><td>価格3%+6万円+税（売主直取引なら不要）</td></tr>
<tr><td>登録免許税・不動産取得税</td><td class="n">—</td><td class="n">{y(d['touroku']+d['shutoku'])}</td><td>評価額{y(d['hyouka'])}円（価格の50%）で推計</td></tr>
<tr><td>司法書士報酬・印紙税</td><td class="n">—</td><td class="n">{y(d['shihou']+d['inshi'])}</td><td>所有権移転登記／契約書印紙</td></tr>
<tr class="tot"><td>物件取得・契約費用 計</td><td class="n">{y(r['shokihiyou'])}</td><td class="n">{y(d['toka'])}</td><td>諸費用は価格の{pc(d['shohiyou']/d['price'],1)}</td></tr>
<tr><td>内装工事費</td><td class="n">{y(NAISOU)}</td><td class="n">{y(NAISOU)}</td><td>坪30万円×{d['tsubo']:.1f}坪相当（サロン仕様）</td></tr>
<tr><td>旧店舗 原状回復・引越</td><td class="n">{y(GENJOU_KYU+HIKKOSHI)}</td><td class="n">{y(GENJOU_KYU+HIKKOSHI)}</td><td>両シナリオ共通</td></tr>
<tr class="tot hi"><td>初期支出 合計</td><td class="n">{y(rent_tot)}</td><td class="n">{y(d['initial_buy'])}</td><td>差額 <b>{man(d['initial_buy']-rent_tot)}</b>（購入が多く必要）</td></tr>
</table>"""

    # --- 月額ランニング ---
    kotoze_tag = est(d['kotoze_est'])
    running = f"""<table>
<tr><th style="width:34%">月額ランニング</th><th class="n" style="width:20%">賃貸</th><th class="n" style="width:20%">売買</th><th>備考</th></tr>
<tr><td>賃料（共益費込）</td><td class="n">{y(RENT_BASE)}</td><td class="n">0</td><td>購入後は賃料ゼロ</td></tr>
<tr><td>管理費＋修繕積立金{'＋組合費' if p['kumiai'] else ''}</td><td class="n">—</td><td class="n">{y(d['kanri_gokei'])}</td><td>{y(d['kanri_gokei']/p['senyu'])}円/㎡月</td></tr>
<tr><td>固定資産税・都市計画税</td><td class="n">—</td><td class="n">{y(d['kotoze_year']/12)}</td><td>年{y(d['kotoze_year'])}円 {kotoze_tag}</td></tr>
<tr><td>火災保険</td><td class="n">{y(KASAI_CHIN/12)}</td><td class="n">{y(KASAI_SHOYU/12)}</td><td>借主／所有者</td></tr>
<tr><td>専有部 修繕予備費</td><td class="n">—</td><td class="n">{y(SHUZEN_YOBI)}</td><td>築古区分の設備更新に備えた自主積立</td></tr>
<tr class="tot hi"><td>月額計</td><td class="n">{y(RENT_BASE+KASAI_CHIN/12)}</td><td class="n">{y(d['hoyuu_m'])}</td><td>購入が月 <b class="pos">{man(abs(res['tsuki_sa']))}</b> 軽い</td></tr>
</table>"""

    # --- 年次比較表 ---
    yrs = [1,2,3,5,7,10]
    def row(label, fn, cls=''):
        return '<tr%s><td>%s</td>' % ((' class="%s"'%cls) if cls else '', label) + ''.join(
            '<td class="n">%s</td>' % fn(n-1) for n in yrs) + '</tr>'
    rfy, bfy = res['rfy'], res['bfy']
    diff10 = [bfy[i]['cum']-rfy[i]['cum'] for i in range(10)]
    shisan = [diff10[i] + d['price']*(1.0) - (r['henkan']-GENJOU_SHIN) for i in range(10)]
    nenji = ('<table><tr><th style="width:28%">［万円］年度末（FY1=2026/9〜2027/8）</th>'
             + ''.join('<th class="n">%d年目</th>'%n for n in yrs) + '</tr>'
             + row('賃貸 累計キャッシュフロー', lambda i: '%s'%f"{rfy[i]['cum']/10000:,.0f}")
             + row('売買 累計キャッシュフロー', lambda i: '%s'%f"{bfy[i]['cum']/10000:,.0f}")
             + row('累計CF差（売買−賃貸）', lambda i: '<span class="%s">%s</span>'%('pos' if diff10[i]>=0 else 'neg', f"{diff10[i]/10000:+,.0f}"), 'tot')
             + row('＋ 手元に残る資産の差', lambda i: '%s'%f"{(d['price']-(r['henkan']-GENJOU_SHIN))/10000:+,.0f}")
             + row('純資産込み 累計差', lambda i: '<span class="%s">%s</span>'%('pos' if shisan[i]>=0 else 'neg', f"{shisan[i]/10000:+,.0f}"), 'tot hi')
             + '</table>')

    # --- 感応度 ---
    rents = (150000,180000,210000,240000)
    sens_rent = ('<table><tr><th style="width:40%">回避できる家賃の前提</th>'
                 + ''.join('<th class="n">%s円/月</th>'%f"{x:,}" for x in rents) + '</tr>')
    cs = {x: compare(d, x) for x in rents}
    sens_rent += '<tr><td>実質利回り（家賃回避÷投下資金）</td>' + ''.join('<td class="n">%s</td>'%pc(cs[x]['jisshitsu'],2) for x in rents) + '</tr>'
    sens_rent += '<tr><td>10年 累計CF差［万円］</td>' + ''.join('<td class="n"><span class="%s">%s</span></td>'%('pos' if cs[x]['cum10_diff']>=0 else 'neg', f"{cs[x]['cum10_diff']/10000:+,.0f}") for x in rents) + '</tr>'
    sens_rent += '<tr class="tot"><td>10年 純資産込み差［万円］</td>' + ''.join('<td class="n"><span class="%s">%s</span></td>'%('pos' if cs[x]['shisan_diff10']>=0 else 'neg', f"{cs[x]['shisan_diff10']/10000:+,.0f}") for x in rents) + '</tr>'
    sens_rent += '<tr><td>賃貸が有利に反転する運用利回り</td>' + ''.join('<td class="n">%s</td>'%pc(cs[x]['bunki'],2) for x in rents) + '</tr></table>'

    kvs = (0.7,0.9,1.1)
    sens_val = ('<table><tr><th style="width:40%">10年後の物件価値（取得価格比）</th>'
                + ''.join('<th class="n">%d%%</th>'%int(k*100) for k in kvs) + '</tr>'
                + '<tr><td>想定売却価格［万円］</td>' + ''.join('<td class="n">%s</td>'%f"{d['price']*k/10000:,.0f}" for k in kvs) + '</tr>'
                + '<tr class="tot"><td>10年 純資産込み差［万円］</td>' + ''.join(
                    '<td class="n"><span class="%s">%s</span></td>'%(
                      'pos' if compare(d,240000,k)['shisan_diff10']>=0 else 'neg',
                      f"{compare(d,240000,k)['shisan_diff10']/10000:+,.0f}") for k in kvs) + '</tr></table>')

    ss = [(dr,)+sales_stress(d,RENT_BASE,dr) for dr in (0,0.2,0.3)]
    sens_sales = ('<table><tr><th style="width:40%">売上が予測から下振れした場合（定常月・2027/8水準）</th>'
                  + ''.join('<th class="n">%s</th>'%(('予測どおり' if x[0]==0 else '▲%d%%'%(x[0]*100))) for x in ss) + '</tr>'
                  + '<tr><td>賃貸シナリオ 月次CF</td>' + ''.join('<td class="n">%s円</td>'%y(x[1]) for x in ss) + '</tr>'
                  + '<tr><td>売買シナリオ 月次CF</td>' + ''.join('<td class="n">%s円</td>'%y(x[2]) for x in ss) + '</tr></table>')

    # --- 物件概要 ---
    gaiyou = f"""<table>
<tr><th style="width:15%">所在・交通</th><td colspan="3">{p['eki']}</td></tr>
<tr><th>販売価格</th><td style="width:23%"><b>{man(d['price'])}</b>（税込）／㎡単価 {y(d['tanka_m2'])}円</td>
    <th style="width:15%">専有面積</th><td>{p['senyu']}㎡（約{d['tsubo']:.1f}坪）・{p['madori']}／バルコニー{p['balcony']}㎡</td></tr>
<tr><th>築年月</th><td>{p['built']}（築{p['age']}年）／{'<b class="pos">新耐震基準</b>' if p['shinkaishin'] else '<b class="neg">旧耐震の可能性大</b>'}</td>
    <th>構造・階数</th><td>{p['kouzou']} {p['floor']}／総戸数{p['sougodo']}戸</td></tr>
<tr><th>管理費等</th><td>管理費{y(p['kanrihi'])}＋修繕積立金{y(p['shuzen'])}{('＋組合費%s'%y(p['kumiai'])) if p['kumiai'] else ''}＝<b>月{y(d['kanri_gokei'])}円</b></td>
    <th>固都税</th><td>年{y(d['kotoze_year'])}円 {est(d['kotoze_est'])}</td></tr>
<tr><th>事務所利用</th><td>{p['jimusho']}</td><th>現況・取引</th><td>{p['genkyou']}／{p['torihiki']}</td></tr>
<tr><th>特記</th><td colspan="3">{'／'.join(p['tokki'])}</td></tr>
</table>"""

    # --- 物件A/B 比較表 ---
    dA, dB = build(PROPS['A']), build(PROPS['B'])
    rA, rB = compare(dA), compare(dB)
    AB = [
      ('販売価格',        lambda x,q: man(x['price']),                       'low'),
      ('専有面積／間取り', lambda x,q: '%.2f㎡（%.1f坪）・%s'%(x['senyu'],x['tsubo'],x['madori']), 'high'),
      ('㎡単価',          lambda x,q: y(x['tanka_m2'])+'円',                 'low'),
      ('築年・耐震',      lambda x,q: '築%d年／%s'%(x['age'],'新耐震' if x['shinkaishin'] else '旧耐震の可能性大'), 'low'),
      ('管理費＋修繕積立金',lambda x,q: '月%s円（%s円/㎡）'%(y(x['kanri_gokei']),y(x['kanri_gokei']/x['senyu'])), 'low'),
      ('投下資金（価格＋諸費用）',lambda x,q: man(x['toka']),                 'low'),
      ('購入 初期支出 合計',lambda x,q: man(x['initial_buy']),               'low'),
      ('月額 保有コスト',  lambda x,q: man(x['hoyuu_m']),                     'low'),
      ('実質利回り',      lambda x,q: pc(q['jisshitsu'],2),                  'high'),
      ('単純回収年数',    lambda x,q: '%.1f年'%(x['toka']/q['nen_setsuyaku']),'low'),
      ('10年 純資産込み差',lambda x,q: man(q['shisan_diff10']),              'high'),
      ('賃貸が逆転する運用利回り',lambda x,q: pc(q['bunki'],2),              'high'),
      ('店舗（美容所）用途',lambda x,q: x['jimusho'],                        'na'),
    ]
    def cell(lbl, fn, better, which):
        va, vb = fn(dA,rA), fn(dB,rB)
        raw = {'販売価格':(dA['price'],dB['price']),'㎡単価':(dA['tanka_m2'],dB['tanka_m2']),
               '専有面積／間取り':(dA['senyu'],dB['senyu']),'築年・耐震':(dA['age'],dB['age']),
               '管理費＋修繕積立金':(dA['kanri_gokei'],dB['kanri_gokei']),
               '投下資金（価格＋諸費用）':(dA['toka'],dB['toka']),
               '購入 初期支出 合計':(dA['initial_buy'],dB['initial_buy']),
               '月額 保有コスト':(dA['hoyuu_m'],dB['hoyuu_m']),
               '実質利回り':(rA['jisshitsu'],rB['jisshitsu']),
               '単純回収年数':(dA['toka']/rA['nen_setsuyaku'],dB['toka']/rB['nen_setsuyaku']),
               '10年 純資産込み差':(rA['shisan_diff10'],rB['shisan_diff10']),
               '賃貸が逆転する運用利回り':(rA['bunki'],rB['bunki'])}.get(lbl)
        mark = ['','']
        if raw and better in ('low','high'):
            lo, hi = min(abs(raw[0]),abs(raw[1])), max(abs(raw[0]),abs(raw[1]))
            if hi > 0 and (hi-lo)/hi >= 0.03:      # 差が3%未満なら実質互角として色を付けない
                win = 0 if ((raw[0]<raw[1]) == (better=='low')) else 1
                mark[win] = ' style="background:#e9f5ee;font-weight:bold"'
        return va, vb, mark
    ab_rows = ''
    for lbl, fn, better in AB:
        va, vb, mk = cell(lbl, fn, better, None)
        me = 0 if key=='A' else 1
        ab_rows += '<tr><th style="width:24%%">%s</th><td%s style="width:38%%">%s</td><td%s>%s</td></tr>' % (
            lbl, mk[0], va, mk[1], vb)
    ab_table = ('<table><tr><th>比較項目</th><th>物件A 立川シティハイツ404%s</th>'
                '<th>物件B サンパレス立川302%s</th></tr>%s</table>') % (
                '（本書）' if key=='A' else '', '（本書）' if key=='B' else '', ab_rows)

    K = kpi([
      ('初期に必要な資金の差<br>（売買 − 賃貸）', man(d['initial_buy']-rent_tot), '賃貸%s → 売買%s'%(man(rent_tot),man(d['initial_buy'])), 'neg'),
      ('月々の負担が軽くなる額', man(abs(res['tsuki_sa'])), '月24.3万円 → 月%.1f万円'%(d['hoyuu_m']/10000), 'pos'),
      ('実質利回り<br>（家賃回避÷投下資金）', pc(res['jisshitsu'],2), '年%s の家賃回避'%man(res['nen_setsuyaku']), 'pos'),
      ('単純回収年数', '%.1f年'%(d['toka']/res['nen_setsuyaku']), '投下資金%s'%man(d['toka']), 'pos' if d['toka']/res['nen_setsuyaku']<15 else 'neg'),
      ('10年 純資産込み<br>有利不利（売買−賃貸）', man(res['shisan_diff10']), '税引後 %s'%man(res['zeigo_shisan10']), 'pos' if res['shisan_diff10']>0 else 'neg'),
      ('賃貸が逆転する<br>資金の運用利回り', pc(res['bunki'],2), 'これ以上で回せるなら賃貸', ''),
    ])

    strong = '<ul>' + ''.join('<li>%s</li>'%x for x in sp['strong']) + '</ul>'
    weak   = '<ul>' + ''.join('<li>%s</li>'%x for x in sp['weak']) + '</ul>'

    body = f"""
<div class="hdr">
  <div><h1>サロン移転 収支予測 ─ 賃貸 vs 売買｜{p['name']}</h1>
  <p class="sub">対象事業：S中野（眉毛サロン）移転計画　│　営業前提の出典：「直営仕入れ中野」2026/10〜2027/8 予測（以降は2027/8水準で横ばい）　│　金額は税込・円　│　作成 2026-08-26</p></div>
  <div class="badge">物件{key}</div>
</div>

<div class="warn">{sp['warn']}</div>

<h2>1. 物件概要</h2>
{gaiyou}

<h2>2. 判定サマリー</h2>
{K}
<p class="note">※「10年 純資産込み有利不利」＝10年間の累計キャッシュフロー差に、10年後に手元へ残る資産の差（売買＝物件、賃貸＝保証金返還{man(r['henkan'])}−新店舗原状回復{man(GENJOU_SHIN)}）を加えた額。物件価値は取得価格と同額（横ばい）を基準とし、感応度は次頁。「賃貸が逆転する運用利回り」＝売買に多く必要な資金 {man(d['initial_buy']-rent_tot)} を他（新規出店等）に回して年何%で回せれば賃貸が有利になるかの分岐点。</p>

<h2>3. 資金計画（初期支出）</h2>
{shikin}

<h2>4. 月額ランニングコスト</h2>
{running}

<h2>5. もう1件の候補との比較</h2>
{ab_table}
<p class="note"><b>緑の網掛け＝その項目で有利な方</b>（差が3%未満は実質互角として無色）。両物件とも立川駅徒歩6〜7分・空室即引渡し・ペット不可の分譲マンション1室。営業収支の前提は完全に同一で、違いは価格・面積・築年・保有コストのみ。<b>この表の判断は「サロン営業が管理規約上できる」ことが前提</b>で、用途可否が確認できない物件は金額の優劣以前に候補から外れる。</p>

<div class="pb"></div>
<div class="hdr"><div><h1>{p['short']}　／　10年比較・感応度・売買のメリット</h1>
<p class="sub">賃貸は月額24.0万円・保証金6ヶ月・更新料2年毎1ヶ月を前提。売買は融資を使わない現金一括（返済・金利・保証料・抵当権設定費用は発生しない）。</p></div><div class="badge">物件{key}</div></div>

<h2>6. 10年間の比較</h2>
{nenji}
<p class="note">FY1（2026/9〜2027/8）は移転年で、内装・原状回復・引越の一時費用と契約費用（または物件取得）が集中する。両シナリオとも移転直後の2026/10から単月黒字を維持する見込み。「手元に残る資産の差」は各年度末に取得価格と同額で売却できた場合の簡便値で、売却時の仲介手数料・譲渡課税は未考慮。</p>

<h2>7. 感応度分析</h2>
<p class="note" style="margin-bottom:1mm"><b>①「回避できる家賃」の前提を動かす</b>──月24万円は中野で設定した上限額。立川駅徒歩7分・{p['senyu']}㎡の店舗賃料が実際にいくらかで結論は動く。</p>
{sens_rent}
<div class="two" style="margin-top:1.4mm">
<div><p class="note" style="margin:0 0 .8mm"><b>② 10年後の物件価値</b>──10年後は築{p['age']+10}年。建物価値はほぼ残らず土地値が下支え。</p>{sens_val}</div>
<div><p class="note" style="margin:0 0 .8mm"><b>③ 売上の下振れ</b>──商圏が中野→立川に変わるため既存顧客の離脱を織り込む。</p>{sens_sales}</div>
</div>

<h2>8. 賃貸と売買の違い</h2>
{qual_table(d,res)}

<h2>9. 売買（購入）の戦略的メリット</h2>
{BUY_MERIT}

<h2>10. この物件の強み／弱み</h2>
<div class="two">
<div><table><tr><th>強み</th></tr><tr><td>{strong}</td></tr></table></div>
<div><table><tr><th>弱み・リスク</th></tr><tr><td>{weak}</td></tr></table></div>
</div>

<div class="concl"><h3>結論</h3>
<p style="margin:0">{sp['verdict']}</p>
<p class="note" style="margin-top:1.5mm">次アクション：①管理組合へ<b>店舗（美容所）用途の可否を書面照会</b>　②<b>重要事項調査報告書</b>で修繕積立金残高・長期修繕計画・滞納・値上げ予定を確認　③保健所に<b>美容所登録の構造設備基準</b>を事前相談　④仲介手数料の要否（取引態様）と固定資産税評価証明を取得　⑤立川駅圏の<b>店舗賃料の実勢</b>を3件以上取得し、感応度表⑦-①のどの列が実態かを確定</p>
</div>

<div class="foot">前提の出所：営業収支＝「直営仕入れ中野」シート／賃貸条件＝前提条件シート（保証金6ヶ月・礼金1・仲介1.1・保証料1・更新料2年毎1ヶ月・償却20%）／購入諸費用＝仲介(価格3%+6万)×1.1、登録免許税＝評価額×1.7%、不動産取得税＝評価額×2.5%、司法書士10万円、印紙1万円。固定資産税評価額は価格の50%と推計。減価償却は建物比率40%・中古簡便法{d['shou_nen']}年。実効法人税率33%。<b>推計値は物件ごとに評価証明・管理規約・重要事項調査報告書で要検証。</b></div>
"""
    return f'<meta charset="utf-8"><style>{CSS}</style>{body}'

if __name__ == '__main__':
    os.makedirs(OUT, exist_ok=True)
    for k in ('A','B'):
        f = os.path.join(OUT, 'r_%s.html'%k)
        open(f,'w',encoding='utf-8').write(build_html(k))
        print('wrote', f)
