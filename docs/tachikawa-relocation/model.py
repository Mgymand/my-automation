# -*- coding: utf-8 -*-
"""中野サロン移転 賃貸 vs 購入 モデル（立川2物件版）"""
import json, math

# ---- 元表「直営仕入れ中野」2026/09〜2027/08（以降は2027/08で横ばい） ----
MONTHS = ['2026/09','2026/10','2026/11','2026/12','2027/01','2027/02',
          '2027/03','2027/04','2027/05','2027/06','2027/07','2027/08']
URIAGE  = [1500000,1600000,1900000,2200000,2300000,2500000,2600000,2600000,2700000,2700000,2800000,2800000]
BUSSHOU = [139300,151253,182780,215307,228927,253000,267453,271787,286740,291240,306693,311360]
GENKA   = [132411,142527,170221,198670,209071,228853,239662,241519,252573,254245,265544,267299]
HANKAN  = [735811,739561,750811,762061,765811,773311,777061,777061,780811,780811,784561,784561]
OLD_RENT = 126500          # 元表「地代家賃」＝旧店舗家賃（販管費計に含まれる）

N = 121                    # 2026/09 を 0 として 10年（120ヶ月）＋開始月
def series(base):
    return [base[i] if i < len(base) else base[-1] for i in range(N)]
S_URIAGE, S_BUSSHOU, S_GENKA, S_HANKAN = map(series, (URIAGE, BUSSHOU, GENKA, HANKAN))
S_BUTSUHAN_ARARI = [S_BUSSHOU[i] - S_GENKA[i] for i in range(N)]

# ---- 共通の一時費用 ----
NAISOU      = 2_000_000    # 新店舗 内装工事費
GENJOU_KYU  =   800_000    # 旧店舗 原状回復費
HIKKOSHI    =   300_000    # 引越・移設費
GENJOU_SHIN =   800_000    # 新店舗 原状回復費（賃貸のみ・10年後退去時）

# ---- 賃貸シナリオ前提 ----
RENT_BASE   = 240_000      # ユーザー指定上限
KANRI_M     = 6            # 保証金 ヶ月
REIKIN_M    = 1
CHUKAI_M    = 1.1
HOSHOU_M    = 1.0
SHOUKYAKU   = 0.20         # 保証金償却率
KASAI_CHIN  = 30_000       # 火災保険（年）借主
KOUSHIN_M   = 1            # 更新料 2年毎

def rent_case(rent):
    hoshoukin = rent*KANRI_M
    return dict(rent=rent, hoshoukin=hoshoukin, reikin=rent*REIKIN_M,
                chukai=rent*CHUKAI_M, hoshougaisha=rent*HOSHOU_M,
                koushin=rent*KOUSHIN_M, henkan=hoshoukin*(1-SHOUKYAKU),
                shokihiyou=rent*(KANRI_M+REIKIN_M+CHUKAI_M+HOSHOU_M))

# ---- 物件データ ----
PROPS = {
 'A': dict(
   key='A', name='立川シティハイツ 404号室', short='立川シティハイツ404',
   price=44_990_000, senyu=56.14, madori='2LDK', balcony=2.67,
   built='昭和58年4月(1983/4)', age=43, shinkaishin=True,
   floor='8階建 4階部分', kouzou='RC・SRC造', sougodo=44,
   kanrihi=10_400, shuzen=12_800, kumiai=200,
   kotoze_actual=81_100,   # 令和7年度 実額
   eki='JR中央線・青梅線・南武線「立川」駅 徒歩6分 / 多摩都市モノレール「立川南」駅 徒歩7分',
   jimusho='不可（図面明記）',
   pet='不可', genkyou='空室・即引渡可',
   torihiki='売主 / 手数料3%(税込)表記',
   shuzen_total=42_637_673,
   tokki=['大規模修繕 平成31年 実施済','共用給排水管更新 平成28年3月','共用部LED化 平成27年2月',
          '増圧給水ポンプ更新 令和元年11月','オートロック・宅配BOX・防犯カメラ・内廊下・EV',
          '管理員 週6日勤務／全部委託(巡回)・大成有楽不動産',
          '新規リノベーション 令和8年9月18日完了予定（住居仕様）'],
 ),
 'B': dict(
   key='B', name='サンパレス立川 302号室', short='サンパレス立川302',
   price=19_800_000, senyu=48.05, madori='1LDK', balcony=7.50,
   built='1981年5月', age=45, shinkaishin=False,
   floor='9階建 3階部分', kouzou='SRC・RC造', sougodo=26,
   kanrihi=14_400, shuzen=20_400, kumiai=0,
   kotoze_actual=None,     # 未開示 → 推計
   eki='JR中央線「立川」駅 徒歩7分',
   jimusho='記載なし（管理規約要確認）',
   pet='不可', genkyou='空室・即引渡可',
   torihiki='売主 / 手数料3%(税込)表記・広告不可',
   shuzen_total=None,
   tokki=['商業地域・防火地域／土地持分 330/10,000（敷地295.76㎡）',
          '管理: 東急コミュニティー／全部委託(巡回)',
          '新規リフォーム済（クロス・CF・フローリング上張り、浴室/キッチン/洗面交換、',
          '  建具・給湯器・TVモニターインターホン交換、洗濯機パン設置）'],
 ),
}

TATEMONO_RITSU = 0.40      # 建物比率（要・契約書/評価額按分で確定）
HYOUKA_RITSU   = 0.50      # 固定資産税評価額／価格（推計）
KASAI_SHOYU    = 60_000    # 火災保険（年）所有者
SHUZEN_YOBI    = 20_000    # 専有部修繕予備費（月）
SHIHOU         = 100_000
INSHI          = 10_000    # 1,000万超5,000万以下 軽減
JISSHOU_ZEI    = 0.33      # 実効法人税率（簡易）

def build(p):
    d = dict(p)
    price = p['price']
    # 購入諸費用
    d['chukai']  = round((price*0.03 + 60_000)*1.1)
    d['hyouka']  = round(price*HYOUKA_RITSU)
    d['touroku'] = round(d['hyouka']*0.017)          # 土地1.5%/非住宅建物2.0%のブレンド
    d['shutoku'] = round(d['hyouka']*0.025)          # 土地3%×宅地1/2 + 非住宅建物4% のブレンド
    d['shihou']  = SHIHOU
    d['inshi']   = INSHI
    d['shohiyou']= d['chukai']+d['touroku']+d['shutoku']+d['shihou']+d['inshi']
    d['toka']    = price + d['shohiyou']             # 投下資金（物件のみ）
    # 保有コスト（月）
    d['kanri_gokei'] = p['kanrihi']+p['shuzen']+p['kumiai']
    kotoze = p['kotoze_actual'] if p['kotoze_actual'] else round(1445*p['senyu'])  # A実額の㎡単価で按分推計
    d['kotoze_year'] = kotoze
    d['kotoze_est']  = p['kotoze_actual'] is None
    d['hoyuu_m'] = d['kanri_gokei'] + kotoze/12 + KASAI_SHOYU/12 + SHUZEN_YOBI
    d['hoyuu_y'] = d['hoyuu_m']*12
    # 減価償却（中古簡便法・法定39年RC店舗用、築>39年 → 39×0.2=7年）
    d['tatemono'] = round(price*TATEMONO_RITSU)
    d['shou_nen'] = max(2, math.floor(39*0.2)) if p['age'] >= 39 else max(2, math.floor((39-p['age'])+p['age']*0.2))
    d['shoukyaku_y'] = d['tatemono']/d['shou_nen']
    d['tsubo'] = p['senyu']/3.30578
    d['tanka_m2'] = price/p['senyu']
    d['initial_buy'] = d['toka'] + NAISOU + GENJOU_KYU + HIKKOSHI
    return d

# ---- 月次キャッシュフロー ----
def monthly(d, rent, scenario):
    r = rent_case(rent)
    rows=[]
    cum=0
    for i in range(N):
        # 販管費：0月目(2026/09)は旧店舗のみ。以降は新店舗へ切替
        if i == 0:
            chidai = OLD_RENT + (rent if scenario=='rent' else 0)   # 賃貸は二重家賃
        else:
            chidai = rent if scenario=='rent' else 0
        hankan = S_HANKAN[i] - OLD_RENT + chidai
        eigyou = S_URIAGE[i] - hankan
        if scenario=='rent':
            hoyuu = KASAI_CHIN/12
        else:
            hoyuu = d['hoyuu_m']
        cf_ops = eigyou + S_BUTSUHAN_ARARI[i] - hoyuu
        # 一時費用
        ichiji = 0
        if i == 0:
            if scenario=='rent':
                ichiji = r['shokihiyou'] + NAISOU + GENJOU_KYU + HIKKOSHI
            else:
                ichiji = d['initial_buy']
        if scenario=='rent' and i>0 and i % 24 == 0:      # 更新料 2年毎
            ichiji += r['koushin']
        cf = cf_ops - ichiji
        cum += cf
        rows.append(dict(m=i, eigyou=eigyou, cf_ops=cf_ops, ichiji=ichiji, cf=cf, cum=cum))
    return rows, r

def fy_agg(rows):
    """FY1=2026/09〜2027/08 = index 0..11"""
    out=[]
    for y in range(10):
        sl = rows[y*12:(y+1)*12]
        out.append(dict(cf_ops=sum(x['cf_ops'] for x in sl),
                        ichiji=sum(x['ichiji'] for x in sl),
                        cf=sum(x['cf'] for x in sl),
                        cum=sl[-1]['cum']))
    return out

def compare(d, rent=RENT_BASE, kachi_ritsu=1.00):
    rrows, r = monthly(d, rent, 'rent')
    brows, _ = monthly(d, rent, 'buy')
    rfy, bfy = fy_agg(rrows), fy_agg(brows)
    res = dict(rent=rent, r=r, rfy=rfy, bfy=bfy)
    res['cum5_diff']  = bfy[4]['cum'] - rfy[4]['cum']
    res['cum10_diff'] = bfy[9]['cum'] - rfy[9]['cum']
    # 純資産：購入=物件価値、賃貸=保証金返還−新店舗原状回復
    bukken10 = d['price']*kachi_ritsu
    res['bukken10'] = bukken10
    res['shisan_diff10'] = res['cum10_diff'] + bukken10 - (r['henkan'] - GENJOU_SHIN)
    # 税効果（運転項目のみ・実効税率33%）
    sonkin_rent = rent*12 + KASAI_CHIN
    res['zei10'] = 0
    for y in range(10):
        sr = sonkin_rent + (r['koushin'] if (y+1) in (3,5,7,9) else 0)
        sb = d['hoyuu_y'] + (d['shoukyaku_y'] if y < d['shou_nen'] else 0)
        res['zei10'] += (sr - sb)*JISSHOU_ZEI     # +は購入不利
    res['zeigo_shisan10'] = res['shisan_diff10'] - res['zei10']
    # 実質利回り
    res['nen_setsuyaku'] = rent*12 + KASAI_CHIN - d['hoyuu_y']
    res['jisshitsu'] = res['nen_setsuyaku']/d['toka']
    res['tsuki_sa'] = d['hoyuu_m'] - (rent + KASAI_CHIN/12)
    res['shoki_sa'] = d['initial_buy'] - (r['shokihiyou']+NAISOU+GENJOU_KYU+HIKKOSHI)
    # 分岐となる代替運用利回り（追加投下資金の単利）
    res['bunki'] = (res['shisan_diff10']/res['shoki_sa']/10) if res['shoki_sa']>0 else None
    return res

if __name__ == '__main__':
    data = {}
    for k in ('A','B'):
        d = build(PROPS[k])
        res = compare(d)
        data[k] = dict(d=d, res=res)
        print('='*70)
        print(k, d['name'])
        print(' 価格 %s円 / %.2f㎡ (%.2f坪) / ㎡単価 %s円' % (f"{d['price']:,}", d['senyu'], d['tsubo'], f"{round(d['tanka_m2']):,}"))
        print(' 諸費用計 %s (仲介%s 登免%s 取得税%s 司法%s 印紙%s)' % tuple(f"{d[x]:,}" for x in ('shohiyou','chukai','touroku','shutoku','shihou','inshi')))
        print(' 投下資金(物件) %s / 購入初期支出合計 %s' % (f"{d['toka']:,}", f"{d['initial_buy']:,}"))
        print(' 保有コスト 月%s円 (管理修繕%s + 固都税%s/12%s + 保険5,000 + 予備20,000)' % (
              f"{round(d['hoyuu_m']):,}", f"{d['kanri_gokei']:,}", f"{d['kotoze_year']:,}", '推計' if d['kotoze_est'] else '実額'))
        print(' 償却 %d年 × %s円/年' % (d['shou_nen'], f"{round(d['shoukyaku_y']):,}"))
        print(' 月額差(購入-賃貸) %s / 初期差 %s' % (f"{round(res['tsuki_sa']):,}", f"{round(res['shoki_sa']):,}"))
        print(' 実質利回り %.2f%%  年ネット節約 %s' % (res['jisshitsu']*100, f"{round(res['nen_setsuyaku']):,}"))
        print(' 5年累計CF差 %s / 10年累計CF差 %s' % (f"{round(res['cum5_diff']):,}", f"{round(res['cum10_diff']):,}"))
        print(' 10年純資産込み差 %s / 税引後 %s' % (f"{round(res['shisan_diff10']):,}", f"{round(res['zeigo_shisan10']):,}"))
        print(' 分岐代替運用利回り %.2f%%' % (res['bunki']*100))
        # 家賃感応度
        print(' 実質利回り@家賃:', ', '.join('%s円→%.2f%%' % (f"{rr:,}", compare(d, rr)['jisshitsu']*100) for rr in (150000,180000,210000,240000)))
        # 物件価値感応度
        print(' 10年純資産込み差@価値:', ', '.join('%d%%→%s' % (int(kv*100), f"{round(compare(d,240000,kv)['shisan_diff10']):,}") for kv in (0.8,1.0,1.2)))

def sales_stress(d, rent, drop):
    """売上下振れ時の定常月次CF（2027/08水準）"""
    u = S_URIAGE[-1]*(1-drop)
    # 変動費: 水道光熱1%, 支払手数料1.75% を売上連動とみなす（元表比率）
    hankan = S_HANKAN[-1] - OLD_RENT
    hendou = (28000+49000)  # 2027/08 水道光熱+支払手数料
    hankan_adj = hankan - hendou + hendou*(1-drop)
    arari = S_BUTSUHAN_ARARI[-1]*(1-drop)
    rent_cf = u - (hankan_adj + rent) + arari - KASAI_CHIN/12
    buy_cf  = u - hankan_adj + arari - d['hoyuu_m']
    return rent_cf, buy_cf
