#!/usr/bin/env bash
# 物件の住所から、無料のオープンデータ・公開APIをまとめて取得する。
#
#   ./fetch-opendata.sh "埼玉県春日部市東中野1523-13" [出力先ディレクトリ]
#
# 取得するもの
#   - 座標（国土地理院 アドレス検索API）
#   - 標高（国土地理院 標高API）
#   - 表層地盤・微地形区分・増幅率（防災科研 J-SHIS）
#   - 洪水浸水想定／浸水継続時間／家屋倒壊等氾濫想定区域／土砂災害（重ねるハザードマップのタイル）
#   - 用途地域・建ぺい率・容積率（国土数値情報 A29）
#   - 地価公示の最寄り標準地（国土数値情報 L01）
#
# 必要なもの: curl, python3（pillow）
set -euo pipefail

ADDR="${1:?住所を指定してください}"
OUT="${2:-./opendata}"
mkdir -p "$OUT"

python3 - "$ADDR" "$OUT" <<'PY'
# -*- coding: utf-8 -*-
import sys, os, json, math, urllib.parse, urllib.request

ADDR, OUT = sys.argv[1], sys.argv[2]
UA = {'User-Agent': 'Mozilla/5.0'}

def get(url, binary=False, timeout=60):
    req = urllib.request.Request(url, headers=UA)
    d = urllib.request.urlopen(req, timeout=timeout).read()
    return d if binary else json.loads(d)

# --- 1. ジオコーディング ---
q = urllib.parse.quote(ADDR)
res = get(f'https://msearch.gsi.go.jp/address-search/AddressSearch?q={q}')
if not res:
    sys.exit(f'住所が見つかりません: {ADDR}')
lon, lat = res[0]['geometry']['coordinates']
print(f'■ 座標  緯度 {lat} / 経度 {lon}   （{res[0]["properties"]["title"]}）')

# --- 2. 標高 ---
try:
    e = get(f'https://cyberjapandata2.gsi.go.jp/general/dem/scripts/getelevation.php?lon={lon}&lat={lat}&outtype=JSON')
    print(f'■ 標高  {e["elevation"]} m（{e["hsrc"]}）')
except Exception as ex:
    print(f'■ 標高  取得失敗: {ex}')

# --- 3. 表層地盤 ---
try:
    j = get(f'https://www.j-shis.bosai.go.jp/map/api/sstrct/V2/meshinfo.geojson?position={lon},{lat}&epsg=4301')
    p = j['features'][0]['properties']
    print(f'■ 地盤  微地形={p["JNAME"]}  AVS30={p["AVS"]} m/s  増幅率={p["ARV"]}')
except Exception as ex:
    print(f'■ 地盤  取得失敗: {ex}')

# --- 4. ハザード（タイルの色で判定）---
Z = 16
n = 2 ** Z
tx = int((lon + 180) / 360 * n)
ty = int((1 - math.log(math.tan(math.radians(lat)) + 1 / math.cos(math.radians(lat))) / math.pi) / 2 * n)
px = int(((lon + 180) / 360 * n - tx) * 256)
py = int(((1 - math.log(math.tan(math.radians(lat)) + 1 / math.cos(math.radians(lat))) / math.pi) / 2 * n - ty) * 256)

DEPTH = {(247,245,169):'0.5m未満',(255,216,192):'0.5〜3.0m未満',(255,183,183):'3.0〜5.0m未満',
         (255,145,145):'5.0〜10.0m未満',(242,133,201):'10.0〜20.0m未満',(220,122,220):'20.0m以上'}
HOURS = {(160,210,255):'12時間未満',(0,65,255):'12時間〜1日未満',(250,245,0):'1日〜3日未満',
         (255,153,0):'3日〜1週間未満',(255,40,0):'1週間〜2週間未満',(180,0,104):'2週間〜4週間未満',(255,0,255):'4週間以上'}
LAYERS = [
    ('洪水浸水想定（想定最大規模）', '01_flood_l2_shinsuishin_data', DEPTH),
    ('洪水浸水想定（計画規模）',     '01_flood_l1_shinsuishin_newlegend_data', DEPTH),
    ('浸水継続時間',                 '01_flood_l2_keizoku_data', HOURS),
    ('家屋倒壊等氾濫想定（氾濫流）', '01_flood_l2_kaokutokai_hanran_data', None),
    ('家屋倒壊等氾濫想定（河岸侵食）','01_flood_l2_kaokutokai_kagan_data', None),
    ('土砂災害警戒区域（土石流）',   '05_dosekiryukeikaikuiki', None),
    ('津波浸水想定',                 '04_tsunami_newlegend_data', None),
    ('高潮浸水想定',                 '03_hightide_l2_shinsuishin_data', None),
]
os.makedirs(f'{OUT}/tiles', exist_ok=True)
try:
    from PIL import Image
except ImportError:
    Image = None
    print('■ ハザード  pillow が無いため色判定をスキップします（pip install pillow）')

for name, path, table in LAYERS:
    url = f'https://disaportaldata.gsi.go.jp/raster/{path}/{Z}/{tx}/{ty}.png'
    try:
        d = get(url, binary=True, timeout=30)
    except Exception:
        print(f'■ {name}  該当なし')
        continue
    f = f'{OUT}/tiles/{path}.png'
    open(f, 'wb').write(d)
    if Image is None:
        print(f'■ {name}  タイルあり（{f}）')
        continue
    im = Image.open(f).convert('RGBA')
    c = im.getpixel((px, py))
    if c[3] == 0:
        print(f'■ {name}  該当なし（着色なし）')
    elif table:
        best = min(table.items(), key=lambda kv: sum((a-b)**2 for a, b in zip(c[:3], kv[0])))
        print(f'■ {name}  {best[1]}')
    else:
        print(f'■ {name}  該当あり RGBA={c}')

# --- 5. 用途地域・地価公示（国土数値情報）---
pref = None
title = res[0]['properties']['title']
PREFS = {'北海道':'01','青森':'02','岩手':'03','宮城':'04','秋田':'05','山形':'06','福島':'07','茨城':'08',
 '栃木':'09','群馬':'10','埼玉':'11','千葉':'12','東京':'13','神奈川':'14','新潟':'15','富山':'16','石川':'17',
 '福井':'18','山梨':'19','長野':'20','岐阜':'21','静岡':'22','愛知':'23','三重':'24','滋賀':'25','京都':'26',
 '大阪':'27','兵庫':'28','奈良':'29','和歌山':'30','鳥取':'31','島根':'32','岡山':'33','広島':'34','山口':'35',
 '徳島':'36','香川':'37','愛媛':'38','高知':'39','福岡':'40','佐賀':'41','長崎':'42','熊本':'43','大分':'44',
 '宮崎':'45','鹿児島':'46','沖縄':'47'}
for k, v in PREFS.items():
    if title.startswith(k):
        pref = v
        break
if not pref:
    print('■ 都道府県コードが判定できず、用途地域・地価公示はスキップします')
    sys.exit()

def inside(pt, ring):
    x, y = pt; ins = False; j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i][0], ring[i][1]; xj, yj = ring[j][0], ring[j][1]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi) + xi):
            ins = not ins
        j = i
    return ins

import zipfile, glob, io
# 用途地域 A29
try:
    z = get(f'https://nlftp.mlit.go.jp/ksj/gml/data/A29/A29-19/A29-19_{pref}_GML.zip', binary=True, timeout=300)
    zipfile.ZipFile(io.BytesIO(z)).extractall(f'{OUT}/A29')
    hit = None
    for f in glob.glob(f'{OUT}/A29/**/*.geojson', recursive=True):
        g = json.load(open(f, encoding='utf-8'))
        for ft in g['features']:
            gm = ft.get('geometry')
            if not gm or gm.get('type') not in ('Polygon', 'MultiPolygon'):
                continue
            polys = [gm['coordinates']] if gm['type'] == 'Polygon' else gm['coordinates']
            if any(inside((lon, lat), poly[0]) for poly in polys):
                hit = ft['properties']; break
        if hit: break
    if hit:
        print(f'■ 用途地域  {hit["A29_005"]}  建ぺい率 {hit["A29_006"]}%  容積率 {hit["A29_007"]}%')
    else:
        print('■ 用途地域  指定範囲外（市街化調整区域など）の可能性')
except Exception as ex:
    print(f'■ 用途地域  取得失敗: {ex}')

# 地価公示 L01（新しい年から順に）
for year in ('26', '25', '24'):
    try:
        z = get(f'https://nlftp.mlit.go.jp/ksj/gml/data/L01/L01-{year}/L01-{year}_{pref}_GML.zip', binary=True, timeout=300)
    except Exception:
        continue
    zipfile.ZipFile(io.BytesIO(z)).extractall(f'{OUT}/L01')
    fs = glob.glob(f'{OUT}/L01/**/*.geojson', recursive=True)
    if not fs: break
    g = json.load(open(fs[0], encoding='utf-8'))
    rows = []
    for ft in g['features']:
        if not ft.get('geometry'):
            continue
        c = ft['geometry']['coordinates']
        d = math.hypot((c[0]-lon)*math.cos(math.radians(lat))*111.32, (c[1]-lat)*110.57)
        rows.append((d, ft['properties']))
    rows.sort(key=lambda r: r[0])
    print(f'■ 地価公示（20{year}年）最寄りの標準地')
    for d, p in rows[:4]:
        pr = p.get('L01_008')
        print(f'    {d:5.2f}km  {pr:>9,} 円/㎡ ({pr*3.30578:>9,.0f} 円/坪)  変動 {p.get("L01_009")}%  '
              f'{p.get("L01_028")}  前面道路 {p.get("L01_040")}  {p.get("L01_025")}')
    break
PY
