# -*- coding: utf-8 -*-
"""
稟議書 収支・価格モデル  ―  春日部市東中野1523-13（南桜井）木造2階建 6DK
すべて円。税引前・償却前。パラメータは PARAMS に集約（出典・確度を併記）。
"""
import json, math, copy

TSUBO = 3.305785
JO = 1.62  # 1帖=1.62㎡（不動産の表示に関する公正競争規約 施行規則）

# ---------------------------------------------------------------- 物件・相場
PARAMS = dict(
    price_ask      = 9_300_000,     # 売出価格（税込表示）
    land_area      = 164.0,         # ㎡
    road_area      = 139.0, road_share = 0.25,   # 私道 持分1/4
    gfa            = 118.92, f1 = 73.48, f2 = 45.44,
    # --- 相場（円/㎡）: 調査結果で更新する ---
    koji_unit      = 50_000,        # 基準地 春日部(県)-11 西金野井字谷頭（一低専・駅1.4km）R7 50,000円/㎡。南桜井駅圏公示平均52,628
    rosenka_unit   = 43_000,        # 令和7年分 路線価 43E（東中野1523街区南側接面）
    deal_land_unit = 45_000,        # 本件更地の実勢推定 40,000〜46,000円/㎡（基準地50,000に駅距離・私道・地目で減価）
    land_fixed_eval_ratio = 0.70,   # 固定資産税評価 ≒ 公示×0.7
    bldg_fixed_eval = 2_400_000,    # 建物 固定資産税評価額【推定 築45年木造】
    # --- 費用単価 ---
    demolition_per_tsubo = 45_000,  # 木造解体 春日部市実績3.5万/坪〜2026年5〜7万/坪の中庸
    demolition_misc = 350_000,      # 残置物・付帯（ブロック塀・庭木等）
    # --- 生活保護（春日部市 2級地-1）---
    housing_aid    = 43_000,        # 住宅扶助 特別基準 単身（埼玉県2級地）
    common_fee     = 20_000,        # 共益費（入居者負担）
    meal_fee       = 30_000,        # 食費（保険外・訪問介護事業所へ）
    # --- 介護報酬（春日部市 地域区分 6級地想定）---
    unit_price     = 10.42,         # 円/単位【要確認】
    tokutei_kasan  = 0.10,          # 特定事業所加算Ⅱ
    shogu_kasan    = 0.249,         # 介護職員等処遇改善加算Ⅱイ（令和8年6月〜 24.9%。元P/Lの22.4%は令和6〜8年5月の率）
    genzan_same_bldg = 0.12,        # 同一建物等居住者90%以上 減算（2024新設）
)

# 諸費用の税率等（2026年9月時点の想定・要確認）
TAX = dict(reg_land=0.015, reg_land_honsoku=0.020, reg_bldg=0.020, acq_land=0.03, acq_bldg=0.03,
           land_acq_half=True, stamp_le_10m=5_000, judicial=70_000, chimoku_change=50_000,
           inspection=70_000, zanchi=250_000, tax_proration=40_000)

def yen(x): return f"{int(round(x)):,}"

# ---------------------------------------------------------------- 取得諸費用
def broker_fee(price):
    """仲介手数料（税込）。800万円以下は低廉空家特例（上限33万円）を仲介が請求する前提。"""
    if price <= 8_000_000:
        return 330_000
    return int(round((price * 0.03 + 60_000) * 1.10))

def land_fixed_eval(p=PARAMS):
    return p['koji_unit'] * p['land_fixed_eval_ratio'] * p['land_area']

def acquisition_costs(price, p=PARAMS, t=TAX):
    le, be = land_fixed_eval(p), p['bldg_fixed_eval']
    items = [
        ("仲介手数料（税込）", broker_fee(price), "宅建業法46条・報酬告示。800万円以下は低廉空家特例（上限33万円）"),
        ("登録免許税（土地 移転1.5%）", le * t['reg_land'], "固定資産税評価額×1.5%（軽減措置前提。本則2.0%なら+" + yen(le*(t['reg_land_honsoku']-t['reg_land'])) + "円）"),
        ("登録免許税（建物 移転2.0%）", be * t['reg_bldg'], "事業用のため住宅用家屋軽減（0.3%）は不適用"),
        ("司法書士報酬", t['judicial'], "所有権移転・（抵当権なし）"),
        ("不動産取得税（土地）", le * (0.5 if t['land_acq_half'] else 1) * t['acq_land'], "宅地評価1/2特例×3%（令和9年3月31日まで）"),
        ("不動産取得税（建物）", be * t['acq_bldg'], "住宅3%。自己居住でないため中古住宅控除は不適用"),
        ("印紙税（売買契約書）", t['stamp_le_10m'], "1,000万円以下・軽減後"),
        ("地目変更登記（山林→宅地）", t['chimoku_change'], "土地家屋調査士。不動産登記法37条（1か月以内の申請義務）"),
        ("建物インスペクション・簡易耐震確認", t['inspection'], "契約不適合免責を受ける前提の自衛"),
        ("残置物撤去・初期清掃", t['zanchi'], "空家・建物現況渡し→買主負担想定（交渉で売主負担化を狙う）"),
        ("固定資産税・都市計画税 精算", t['tax_proration'], "引渡日以降の日割"),
    ]
    total = sum(v for _, v, _ in items)
    return items, total

# ---------------------------------------------------------------- 改修プラン
def reno_items(plan):
    """plan: '9室' '7室' '6室' 'GH' 'LIGHT'"""
    n = {'9室':9, '7室':7, '6室':6, 'GH':6, 'LIGHT':0}[plan]
    parts = {'9室':3, '7室':1, '6室':0, 'GH':0, 'LIGHT':0}[plan]   # 新設間仕切（居室分割）箇所
    it = []
    if plan in ('9室','7室','6室'):
        it += [
            ("居室間仕切壁 新設（石膏ボード両面二重張り・遮音・小屋裏/天井裏処置）", 280_000*parts, f"{parts}箇所。令114条2項の防火上主要な間仕切壁対応（小規模緩和の適用可否は設計者確認）"),
            ("居室ドア（鍵付・レバーハンドル・自閉装置）新設/交換", 95_000*n, f"{n}室。告示860号の常時閉鎖式戸"),
            ("各居室エアコン（6畳用・工事込）", 110_000*n, f"{n}室"),
            ("各居室 内装（クロス・床CF・巾木・照明）", 95_000*n, f"{n}室。和室は洋室化"),
            ("電気設備増設（各室コンセント回路・分電盤増設・引込容量UP）", 650_000, "9室同時空調に耐える容量へ"),
            ("共用部内装（DK・廊下・階段・玄関）＋手すり（廊下・階段・トイレ・浴室）", 700_000, "高齢者対応"),
            ("浴室（既存ユニット活用＋シャワー・手すり・暖房乾燥機）", 550_000, "全面交換なら+60万円"),
            ("トイレ2箇所（温水洗浄便座・手すり・引戸化）", 320_000, "1階・2階"),
            ("洗面台増設（2階）＋給排水", 300_000, "2階6室が1階洗面のみは実用上不可"),
            ("給湯器交換（プロパン 24号）", 260_000, "築45年→交換前提"),
            ("キッチン（既存活用・コンロ/水栓交換・IH化検討）", 250_000, "調理は訪問介護事業所の保険外委託。IH化で火気リスク低減"),
            ("玄関スロープ・段差解消・屋外手すり", 150_000, ""),
            ("外装・屋根 補修（雨漏り・瓦ずれ・樋）", 500_000, "築45年 瓦葺。現地調査で増減"),
            ("消防：無線式連動型 自動火災報知設備（受信機＋各室感知器）", 450_000, "有老（6項ロ/ハ）・寄宿舎いずれも自火報は必須想定"),
            ("消防：消防機関へ通報する火災報知設備・誘導灯2台・消火器", 550_000, "通報装置25万〜・誘導灯14〜16万/台・消火器0.8万/本（消防テック料金表）"),
            ("設計・各種申請・消防協議（建築士・行政書士）", 350_000, "用途変更確認申請は不要（200㎡以下）だが実体規定適合を設計者が確認"),
            ("見守りセンサー・Wi-Fi初期", 150_000, ""),
            ("非常用照明（各居室・廊下・階段 約12台）", 360_000, "令126条の4。老人ホームの居室は寄宿舎の寝室と異なり除外されない（告示1411号による免除は設計者確認）"),
        ]
    elif plan == 'GH':
        it += [
            ("軽微内装（クロス・床CF 全室）", 700_000, "障がい者GH事業者向け一棟貸し。事業者側で追加改修が通例"),
            ("手すり・段差解消・給湯器交換", 450_000, ""),
            ("外装・屋根 補修", 500_000, ""),
            ("自動火災報知設備（無線式）", 450_000, "GH（6項ロ/ハ）自火報必須"),
        ]
    elif plan == 'LIGHT':
        it += [
            ("クリーニング・簡易補修（転売用）", 300_000, "三為・転売時の最低限"),
        ]
    sub = sum(v for _, v, _ in it)
    it.append(("予備費（10%）", round(sub*0.10), "見積乖離・隠れ瑕疵"))
    return it, sum(v for _, v, _ in it)

SPRINKLER = 3_000_000   # 特定施設水道連結型SP（6項ロ判定時）100〜150㎡で200〜300万円＋余裕
STAIRS = 900_000        # 階段架け替え（令23条：踏面19cm未満・両側手すりで不適合の場合）要実測
WATER_MAIN = 800_000    # 給水引込増径（水圧不足時）・私道掘削承諾込【暫定】

# ---------------------------------------------------------------- 居室プラン
ROOMS = {  # 専用部分 ㎡（帖×1.62＋収納概算）
    '9室': [6.4, 6.4, 7.2, 7.2, 10.5, 10.5, 6.3, 6.3, 10.5],
    '7室': [12.9, 7.2, 7.2, 10.5, 10.5, 12.7, 10.5],
    '6室': [12.9, 14.5, 10.5, 10.5, 12.7, 10.5],
}
def shared_area(plan):
    return PARAMS['gfa'] - sum(ROOMS[plan])

def aid_coef(area):
    """住宅扶助 床面積別限度額（単身・平成27年7月〜）: 15㎡超=満額 / 11〜15㎡=▲10% / 7〜10㎡=▲20% / 6㎡以下=▲30%（厚労省説明資料）"""
    if area > 15: return 1.0
    if area >= 11: return 0.9
    if area >= 7:  return 0.8
    return 0.7

def housing_revenue(plan, include_shared=True, p=PARAMS):
    rooms = ROOMS[plan]; sh = shared_area(plan)/len(rooms)
    rent = 0
    detail = []
    for a in rooms:
        eff = a + (sh if include_shared else 0)
        c = aid_coef(eff)
        rent += p['housing_aid']*c
        detail.append((a, eff, c))
    return rent, detail

# ---------------------------------------------------------------- A: 住宅事業（月次）
FACILITY_STAFF = {'none':0, 'shukuchoku':650_000, 'yakin':1_000_000}   # 県指針7(1)二ロ 直接処遇職員（日中常勤1名31.5万＋夜間宿直33万／夜勤なら＋35万）

def housing_pl(plan='9室', n_res=None, aid_mode='shared', with_manager=False, occupancy=1.0, staff='shukuchoku', p=PARAMS):
    rooms = ROOMS[plan]; N = len(rooms)
    n_res = N if n_res is None else n_res
    if aid_mode == 'full':
        rent_full = p['housing_aid']*N
    else:
        rent_full, _ = housing_revenue(plan, include_shared=(aid_mode=='shared'), p=p)
    rent = rent_full * n_res / N * occupancy
    common = p['common_fee'] * n_res * occupancy
    rev = rent + common
    cost = [
        ("水道光熱費（全館）", 12_000*n_res),
        ("火災保険・施設賠償保険", 15_000),
        ("修繕・消耗品積立", 30_000),
        ("固定資産税・都市計画税（月割）", 6_000),
        ("通信・見守りセンサー", 5_280),
        ("清掃委託（共用部）", 20_000),
        ("消防設備点検・法定点検（月割）", 5_000),
        ("入居者入替コスト（紹介料10万円×年間入替30%）", round(100_000*0.30*N/12)),
    ]
    if staff != 'none':
        cost.append((f"施設 直接処遇職員（県指針7(1)二ロ：日中常勤1名＋{'夜間宿直' if staff=='shukuchoku' else '夜勤'}）", FACILITY_STAFF[staff]))
    if with_manager:
        cost.append(("施設管理・生活相談（パート常駐/巡回）", 100_000))
    tc = sum(v for _, v in cost)
    return dict(plan=plan, N=N, n_res=n_res, rent=rent, common=common, rev=rev, cost=cost, tc=tc, cf=rev-tc)

# ---------------------------------------------------------------- B: 訪問介護事業（月次）
def care_pl(n_res=9, scenario='標準', genzan=False, p=PARAMS):
    units = {'保守':(14_000,1_000), '標準':(18_000,1_500), '上限寄り':(20_500,1_500)}[scenario]
    u = sum(units)  # 1人あたり月単位数
    base = u * n_res * p['unit_price']
    if genzan:
        base *= (1 - p['genzan_same_bldg'])
    tokutei = base * p['tokutei_kasan']
    shogu = (base + tokutei) * p['shogu_kasan']
    meal = p['meal_fee'] * n_res
    rev = base + tokutei + shogu + meal
    extra = {'保守':176_000, '標準':186_000, '上限寄り':206_000}[scenario]
    cost = [
        ("人件費（常勤3人 27.3万×法定福利1.155）", 946_000),
        ("予備人件費＋朝夕ピークパート", extra),
        ("食材費（食費の50%）", round(meal*0.5)),
        ("事業所経費（家賃・車両・ソフト・保険）", 200_000),
    ]
    tc = sum(v for _, v in cost)
    return dict(scenario=scenario, n_res=n_res, units=u, base=base, tokutei=tokutei, shogu=shogu, meal=meal, rev=rev, cost=cost, tc=tc, cf=rev-tc, genzan=genzan)

# ---------------------------------------------------------------- 投資総額・利回り
def total_investment(price, plan='9室', sprinkler=False, water_main=False, p=PARAMS):
    _, acq = acquisition_costs(price, p)
    _, reno = reno_items(plan)
    extra = (SPRINKLER if sprinkler else 0) + (WATER_MAIN if water_main else 0)
    return dict(price=price, acq=acq, reno=reno, extra=extra, total=price+acq+reno+extra)

def gross_yield(price, plan='9室', sprinkler=False, p=PARAMS):
    ti = total_investment(price, plan, sprinkler, p=p)
    N = len(ROOMS[plan])
    annual = (p['housing_aid'] + p['common_fee']) * N * 12   # 社内定義: 扶助額+2万円
    return annual / ti['total'], annual, ti

def max_price_for_total(cap, plan='9室', sprinkler=False, p=PARAMS):
    """総投資額capに収まる最大の物件価格（諸費用は価格連動のため反復）"""
    lo, hi = 0, cap
    for _ in range(60):
        mid = (lo+hi)/2
        if total_investment(mid, plan, sprinkler, p=p)['total'] <= cap: lo = mid
        else: hi = mid
    return math.floor(lo/10_000)*10_000

def max_price_for_yield(target, plan='9室', sprinkler=False, p=PARAMS):
    lo, hi = 0, 50_000_000
    for _ in range(60):
        mid = (lo+hi)/2
        if gross_yield(mid, plan, sprinkler, p=p)[0] >= target: lo = mid
        else: hi = mid
    return math.floor(lo/10_000)*10_000

# ---------------------------------------------------------------- 物件単体の価値（3手法）
def land_value(p=PARAMS):
    return p['deal_land_unit'] * p['land_area']

def demolition_cost(p=PARAMS):
    return p['demolition_per_tsubo'] * (p['gfa']/TSUBO) + p['demolition_misc']

def cost_approach(p=PARAMS):
    """積算: 土地(実勢単価×面積) + 建物（築45年木造の市場残存価値 150万円［実勢: 東中野の築40年超成約の建物相当分150〜250万円］）"""
    land = land_value(p)
    bldg = 1_500_000
    return dict(land=land, bldg=bldg, total=land+bldg)

def income_approach_normal_rent(rent=75_000, cap=0.10, p=PARAMS):
    """通常戸建賃貸としての収益価格（表面）"""
    return dict(rent=rent, annual=rent*12, price=rent*12/cap)

def land_less_demolition(p=PARAMS):
    return land_value(p) - demolition_cost(p)

# ---------------------------------------------------------------- 出口
def exit_package(plan='9室', cap_rates=(0.15, 0.18, 0.20), price=None, sprinkler=False, p=PARAMS):
    N = len(ROOMS[plan])
    gross = (p['housing_aid'] + p['common_fee']) * N * 12
    out = []
    ti = total_investment(price, plan, sprinkler, p=p)['total'] if price else None
    for c in cap_rates:
        sale = gross / c
        fee = (sale*0.03+60_000)*1.1
        net = sale - fee
        out.append(dict(cap=c, sale=sale, fee=fee, net=net, gain=(net - ti) if ti else None))
    return gross, out

def exit_gh(price, rent=180_000, cap_rates=(0.10, 0.12), p=PARAMS):
    _, acq = acquisition_costs(price, p)
    _, reno = reno_items('GH')
    ti = price + acq + reno
    out = []
    for c in cap_rates:
        sale = rent*12/c; fee=(sale*0.03+60_000)*1.1
        out.append(dict(cap=c, sale=sale, net=sale-fee, gain=sale-fee-ti))
    return dict(ti=ti, acq=acq, reno=reno, annual=rent*12, yield_on_cost=rent*12/ti, exits=out)

def exit_flip(price, sale_price, p=PARAMS):
    _, acq = acquisition_costs(price, p)
    _, reno = reno_items('LIGHT')
    ti = price + acq + reno
    fee = (sale_price*0.03+60_000)*1.1
    return dict(ti=ti, sale=sale_price, fee=fee, gain=sale_price-fee-ti)

# ---------------------------------------------------------------- 実行
if __name__ == '__main__':
    p = PARAMS
    print("土地固定資産税評価(推定)", yen(land_fixed_eval()))
    for price in (9_300_000, 8_500_000, 8_000_000, 7_500_000, 7_000_000):
        items, acq = acquisition_costs(price)
        y, annual, ti = gross_yield(price, '9室')
        y2, _, ti2 = gross_yield(price, '9室', sprinkler=True)
        print(f"価格 {yen(price)}: 諸費用 {yen(acq)} / 改修 {yen(ti['reno'])} / 総投資 {yen(ti['total'])} 表面 {y:.1%} | SP込 総投資 {yen(ti2['total'])} 表面 {y2:.1%}")
    print("改修9室:"); 
    for n,v,c in reno_items('9室')[0]: print("  ", n, yen(v))
    print("改修7室 合計", yen(reno_items('7室')[1]), " 6室", yen(reno_items('6室')[1]), " GH", yen(reno_items('GH')[1]))
    print("cap2000万 max price 9室:", yen(max_price_for_total(20_000_000,'9室')), " SP込:", yen(max_price_for_total(20_000_000,'9室',True)))
    for plan in ROOMS:
        r_sh,_ = housing_revenue(plan, True); r_ex,_ = housing_revenue(plan, False)
        print(plan, "共用按分あり 家賃計", yen(r_sh), " 専有のみ", yen(r_ex), " 満額", yen(p['housing_aid']*len(ROOMS[plan])), " 共用/人", round(shared_area(plan)/len(ROOMS[plan]),1))
    for sc in ('保守','標準','上限寄り'):
        b = care_pl(9, sc); bg = care_pl(9, sc, genzan=True)
        a = housing_pl('9室', aid_mode='full')
        print(sc, "B CF", yen(b['cf']), " 減算時", yen(bg['cf']), " A CF", yen(a['cf']), " 連結", yen(a['cf']+b['cf']))
    print("積算", cost_approach(), "土地-解体", yen(land_less_demolition()), "解体", yen(demolition_cost()))
    g, ex = exit_package('9室', price=9_300_000); print("package gross", yen(g), [(e['cap'], yen(e['sale']), yen(e['gain'])) for e in ex])
    print("GH", {k:(yen(v) if isinstance(v,(int,float)) and k!='yield_on_cost' else v) for k,v in exit_gh(8_000_000).items() if k!='exits'})

# ---------------------------------------------------------------- 価格戦略（指値・妥協・撤退）
PRICING = dict(
    comp_value   = 8_800_000,   # 取引事例比較法による比準価格（Ⅰ-6）
    normal_rent  = 72_000,      # 通常戸建賃貸 想定賃料（築35〜47年・100㎡超 7.0〜8.5万の下寄り）
    gh_rent      = 150_000,     # 障がい者GH一棟貸し（中古戸建6室 15〜20万/月の下限。春日部市はGH供給過多のため保守的に）
    cap_total    = 20_000_000,  # 社内基準: 総投資額上限
    target_yield = 0.30,        # 社内目標: 表面利回り（扶助+2万×室数÷総投資額）下限
    offer_ratio  = 0.85,        # 指値 = 妥協上限×0.85（交渉余地）
)

def pricing(p=PARAMS, pr=PRICING):
    p_cap    = max_price_for_total(pr['cap_total'], '9室', False, p)
    p_cap_sp = max_price_for_total(pr['cap_total'], '9室', True, p)
    p_yield  = max_price_for_yield(pr['target_yield'], '9室', False, p)
    p_comp   = pr['comp_value']
    v_land_net = land_less_demolition(p)
    v_cost   = cost_approach(p)['total']
    v_income = income_approach_normal_rent(pr['normal_rent'], 0.10, p)['price']
    # 通常転売でも損しない上限（比準価格 − 取得諸費用 − 売却諸費用 − 軽微整備）
    _, acq_at_comp = acquisition_costs(p_comp, p)
    p_exit_safe = p_comp - acq_at_comp - ((p_comp*0.03+60_000)*1.1) - 300_000
    compromise = min(p_cap, p_comp, p_yield)
    compromise = math.floor(compromise/100_000)*100_000
    offer = math.floor(compromise*pr['offer_ratio']/100_000)*100_000
    # 更地−解体 を下回る指値は売主が更地売りに逃げるため、指値の下限は更地−解体
    offer = max(offer, math.floor(v_land_net/100_000)*100_000)
    return dict(p_cap=p_cap, p_cap_sp=p_cap_sp, p_yield=p_yield, p_comp=p_comp, v_land_net=v_land_net,
                v_cost=v_cost, v_income=v_income, p_exit_safe=p_exit_safe, compromise=compromise, offer=offer,
                discount_offer=1-offer/p['price_ask'], discount_comp=1-compromise/p['price_ask'])

if __name__ == '__main__':
    pr = pricing()
    print({k:(yen(v) if isinstance(v,(int,float)) and abs(v)>1 else v) for k,v in pr.items()})

def max_price_for_payback(months, plan='9室', scenario='標準', init_biz=9_662_000, staff='shukuchoku', p=PARAMS):
    a = housing_pl(plan, aid_mode='full', staff=staff, p=p); b = care_pl(len(ROOMS[plan]), scenario, p=p)
    cf = a['cf'] + b['cf']
    lo, hi = 0, 60_000_000
    for _ in range(60):
        mid = (lo+hi)/2
        if total_investment(mid, plan, False, p=p)['total'] + init_biz <= cf*months: lo = mid
        else: hi = mid
    return math.floor(lo/10_000)*10_000
