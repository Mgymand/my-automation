# -*- coding: utf-8 -*-
"""
住まいの修理マッチング ブログジェネレーター
東京23区・即日対応の住宅修理に関するSEO記事を静的HTMLで生成する。
各記事末尾にはゼヒトモ連携用スニペットを埋め込む。

使い方:
    python3 build.py
出力:
    zehitomo-blog/ 直下に style.css, index.html, 各記事HTML を生成
"""
import os
import html
import json

OUT_DIR = os.path.dirname(os.path.abspath(__file__))

# このブログの公開ドメイン（Vercel）
DOMAIN = "https://my-automation-seven.vercel.app"
BLOG_NAME = "住まいの修理コラム"
PUBLISH_DATE = "2026-06-05"

# サイト本体（誘導先）
SITE_URL = "https://site-five-blush-72.vercel.app"
SITE_NAME = "住まいの修理マッチング"
TEL = "090-1386-7439"
TEL_LINK = "tel:09013867439"
TEL_E164 = "+81-90-1386-7439"
EMAIL = "gtiwamoto@gmail.com"
EMAIL_LINK = "mailto:gtiwamoto@gmail.com?subject=" + "住まいの修理のお問い合わせ"
LINE_URL = "https://lin.ee/Q03KlWx"
AREA = "東京23区全域"

# 対応エリア（東京23区）
WARDS = [
    "千代田区", "中央区", "港区", "新宿区", "文京区", "台東区", "墨田区", "江東区",
    "品川区", "目黒区", "大田区", "世田谷区", "渋谷区", "中野区", "杉並区", "豊島区",
    "北区", "荒川区", "板橋区", "練馬区", "足立区", "葛飾区", "江戸川区",
]

# ゼヒトモ連携スニペット（各記事末尾に必須）
ZEHITOMO_SNIPPET = (
    "<p id=\"ref_6953ac0c3fcfbbee9aa49aaa_home-reform-general\">"
    "<a href='https://www.zehitomo.com/profile/%E5%B2%A9%E6%9C%AC-%E8%B3%A2%E4%BC%B8-v15BjMo3R/pro' target='_blank'>"
    "ゼヒトモ内でのプロフィール: 岩本 賢伸</a>,&nbsp;"
    "<a href='https://www.zehitomo.com/home/reform/theme/home-reform-general' target='_blank'>"
    "ゼヒトモのリフォーム・リノベーション・内装工事（大工・工務店）サービス</a>,&nbsp;"
    "<a href='https://www.zehitomo.com' target='_blank'>"
    "仕事をお願いしたい依頼者と様々な「プロ」をつなぐサービス</a></p>"
)

# ---- 記事データ ----------------------------------------------------------
# 各記事: slug, title, keyword(検索ワード), desc, lead, symptoms[], causes[],
#         diy[], pro[], price[(項目, 目安)], faq[(Q,A)]
ARTICLES = [
    {
        "slug": "toilet-water-not-stopping",
        "title": "トイレの水が止まらない・流れない｜原因と修理方法【東京23区・即日対応】",
        "keyword": "トイレ 修理 水が止まらない",
        "desc": "トイレの水が止まらない・流れないときの原因と対処法、修理費用の目安を解説。東京23区なら最短即日で出張修理に対応します。",
        "lead": "「トイレの水がチョロチョロ止まらない」「レバーを回しても流れない」——トイレのトラブルは生活に直結するため、放置すると水道代の高騰や水漏れ被害につながります。本記事では原因の見分け方と、自分でできる応急処置、プロに頼むべきケースまで分かりやすく解説します。",
        "symptoms": [
            "タンク内で水がチョロチョロ流れ続ける",
            "レバーを回しても水が流れない・流れが弱い",
            "便器内に水がたまらない／溢れそうになる",
            "床が濡れている・タンク下から水漏れ",
        ],
        "causes": [
            "ゴムフロート（フロートバルブ）の劣化・ずれ",
            "ボールタップ・浮き球の故障による給水の止まらない不具合",
            "鎖（チェーン）の絡まり・外れ",
            "排水路のつまり（トイレットペーパー・異物）",
            "パッキンや給水管の劣化による水漏れ",
        ],
        "diy": [
            "止水栓（壁・床際のマイナスねじ）を閉めて給水を止める",
            "タンクのフタを開け、鎖の絡まりやフロートのずれを直す",
            "軽いつまりはラバーカップ（スッポン）でゆっくり加圧する",
        ],
        "pro": [
            "止水栓を閉めても水漏れが止まらない",
            "便器と床の間（給水管・排水部）から水が漏れている",
            "ラバーカップでも詰まりが解消しない／異物を落とした",
            "ウォシュレットや配管からの漏水で電気系統が心配なとき",
        ],
        "price": [
            ("軽度のつまり除去", "5,000円〜"),
            ("ゴムフロート・ボールタップ交換", "8,000円〜"),
            ("ウォシュレット・便器の脱着を伴う修理", "15,000円〜"),
            ("便器交換（本体別途）", "30,000円〜"),
        ],
        "faq": [
            ("夜間や休日でも来てもらえますか？", "東京23区内であれば最短即日・時間帯のご相談も可能です。まずはお電話かメールでお問い合わせください。"),
            ("見積もりだけでも料金はかかりますか？", "出張費・見積費用は0円です。金額にご納得いただいてから作業します。"),
            ("賃貸でも修理できますか？", "可能です。ただし設備の交換は管理会社・大家さんの確認が必要な場合があるため、事前にご相談ください。"),
        ],
    },
    {
        "slug": "kitchen-faucet-leak",
        "title": "蛇口・キッチンの水漏れ修理｜パッキン交換から蛇口交換まで【東京23区】",
        "keyword": "蛇口 水漏れ 修理",
        "desc": "キッチンや洗面の蛇口から水漏れする原因と修理方法、パッキン交換・蛇口交換の費用目安を解説。東京23区は出張費・見積無料で即日対応。",
        "lead": "蛇口の付け根やハンドルからのポタポタ水漏れは、パッキンの劣化が原因のことが多く、放置するとシンク下のカビや床材の腐食につながります。原因箇所別の対処法と費用の目安をまとめました。",
        "symptoms": [
            "ハンドルやレバーの根元から水がにじむ",
            "蛇口の先端（スパウト）からポタポタ落ちる",
            "シンク下の収納が湿っている・カビ臭い",
            "止水しても完全に水が止まらない",
        ],
        "causes": [
            "ケレップ（コマパッキン）・Oリングの経年劣化",
            "カートリッジ（シングルレバー混合栓）の摩耗",
            "ナットの緩み・シールテープの劣化",
            "給水・給湯ホースの接続部からの漏れ",
        ],
        "diy": [
            "シンク下の止水栓を閉めて水を止める",
            "ナットの緩みはモンキーレンチで軽く締め直す",
            "ホームセンターの汎用パッキンで応急交換（型番要確認）",
        ],
        "pro": [
            "シングルレバー混合栓のカートリッジ交換が必要",
            "壁付き蛇口の根元（クランク部）から漏れている",
            "蛇口本体の交換・取り付けが必要なとき",
            "シンク下の配管接続部から漏水しているとき",
        ],
        "price": [
            ("パッキン・Oリング交換", "5,000円〜"),
            ("カートリッジ交換", "8,000円〜"),
            ("蛇口・混合栓の交換（本体別途）", "12,000円〜"),
            ("給水管・止水栓の交換", "10,000円〜"),
        ],
        "faq": [
            ("どのメーカーの蛇口でも対応できますか？", "TOTO・LIXIL・KVK・SAN-EIなど主要メーカーに対応しています。型番が分かる写真を送っていただくとスムーズです。"),
            ("水漏れがひどく今すぐ止めたいです", "まず止水栓を閉めてください。東京23区なら最短即日でお伺いします。お電話かメールでご連絡ください。"),
            ("古い蛇口でも部品はありますか？", "汎用部品で対応できるケースが多いですが、廃番の場合は蛇口交換をご提案します。費用は事前にお見積もりします。"),
        ],
    },
    {
        "slug": "drain-clog",
        "title": "排水溝・排水管のつまり解消｜キッチン・お風呂・洗面の即日修理【東京23区】",
        "keyword": "排水溝 つまり 修理",
        "desc": "キッチン・お風呂・洗面の排水つまりの原因と解消法、業者依頼の費用目安を解説。東京23区なら高圧洗浄も最短即日で対応します。",
        "lead": "排水の流れが悪い・ゴボゴボ音がする・悪臭がする——こうした症状は油汚れや髪の毛、石けんカスの蓄積が原因です。市販品で改善しない頑固なつまりは、配管内部の高圧洗浄で根本的に解消できます。",
        "symptoms": [
            "水を流すと逆流する・水位が下がらない",
            "排水時にゴボゴボと空気の音がする",
            "排水口から下水のような悪臭がする",
            "複数の排水口で同時に流れが悪い",
        ],
        "causes": [
            "キッチン：油・食材カスの固着",
            "お風呂・洗面：髪の毛と石けんカスの絡まり",
            "排水トラップの汚れ・ヘアキャッチャーの目詰まり",
            "屋外排水桝（ます）や排水管本体のつまり",
        ],
        "diy": [
            "ヘアキャッチャー・ワントラップを外して髪やゴミを除去",
            "ぬるま湯＋重曹＋クエン酸で軽い油・ぬめりを分解",
            "ラバーカップやワイヤーブラシで物理的に押し流す",
        ],
        "pro": [
            "市販のパイプクリーナーでも改善しない",
            "複数箇所で同時に流れが悪い（排水管本体のつまり）",
            "悪臭・逆流が続く／屋外桝から溢れている",
            "配管の高圧洗浄が必要なとき",
        ],
        "price": [
            ("軽度のつまり除去（局所）", "5,000円〜"),
            ("薬剤・ワイヤーによる本格的な除去", "8,000円〜"),
            ("排水管の高圧洗浄", "15,000円〜"),
            ("屋外排水桝の清掃", "12,000円〜"),
        ],
        "faq": [
            ("どのくらいで直りますか？", "局所的なつまりは30分〜1時間程度が目安です。高圧洗浄でも当日中に完了するケースがほとんどです。"),
            ("マンションでも対応できますか？", "可能です。専有部の排水であれば即日対応します。共用部に及ぶ場合は管理会社への確認をご案内します。"),
            ("再発を防ぐ方法は？", "油を流さない・ヘアキャッチャーをこまめに掃除することが有効です。定期的な高圧洗浄もおすすめです。"),
        ],
    },
    {
        "slug": "water-heater-no-hot-water",
        "title": "給湯器の故障でお湯が出ない｜修理・交換の費用と即日対応【東京23区】",
        "keyword": "給湯器 故障 修理 交換",
        "desc": "給湯器からお湯が出ない・エラーが出るときの原因と、修理・交換の費用目安を解説。東京23区なら最短即日で現地調査・お見積もりします。",
        "lead": "急にお湯が出なくなると入浴も家事も止まってしまいます。給湯器のトラブルはエラーコードや使用年数で原因をある程度判断できます。修理で直るケースと交換が必要なケースの見分け方を解説します。",
        "symptoms": [
            "蛇口をひねってもお湯が出ない・ぬるい",
            "リモコンにエラーコードが表示される",
            "点火時に異音・異臭がする",
            "本体や配管から水漏れしている",
        ],
        "causes": [
            "点火不良・センサーの故障",
            "凍結や配管トラブルによる給水不良",
            "経年劣化（一般的に10〜15年が寿命の目安）",
            "ガス・電源・水栓側の一時的な不具合",
        ],
        "diy": [
            "ガスの元栓・給水元栓・電源が入っているか確認",
            "リモコンの電源を入れ直し、エラーコードを控える",
            "冬季はお湯側の蛇口を少し開けて凍結を予防",
        ],
        "pro": [
            "エラーコードが消えない・繰り返し出る",
            "本体や配管から水漏れ・ガス臭がする",
            "使用10年以上で故障した（交換推奨のサイン）",
            "号数アップや追い焚き機能の追加を検討したいとき",
        ],
        "price": [
            ("現地調査・お見積もり", "0円"),
            ("部品交換による修理", "8,000円〜"),
            ("給湯専用機の交換（本体別途）", "60,000円〜"),
            ("追い焚き付き給湯器の交換（本体別途）", "90,000円〜"),
        ],
        "faq": [
            ("修理と交換どちらが得ですか？", "使用10年未満なら修理、それ以上は交換がおすすめです。現地調査のうえ、両案の費用をご提示します。"),
            ("今日中にお湯を使えるようにできますか？", "在庫状況によりますが、東京23区なら即日復旧できるケースが多いです。まずはご連絡ください。"),
            ("ガス会社を変えなくても交換できますか？", "はい、ガス契約はそのままで給湯器のみ交換可能です。"),
        ],
    },
    {
        "slug": "lock-replacement",
        "title": "鍵交換・鍵開け（玄関・防犯）｜料金相場と即日対応【東京23区】",
        "keyword": "鍵 交換 鍵開け 即日",
        "desc": "玄関の鍵交換・鍵開け・防犯対策の料金相場と、東京23区での即日対応について解説。鍵の紛失や引っ越し時の交換もお任せください。",
        "lead": "鍵をなくした、引っ越しで前の入居者の鍵が心配、防犯性を高めたい——鍵のトラブルは緊急性が高く、防犯にも直結します。鍵の種類別の費用目安と、即日で対応できるケースを紹介します。",
        "symptoms": [
            "鍵を紛失して家に入れない",
            "鍵が回らない・抜けない・刺さりにくい",
            "引っ越し直後で防犯のため鍵を替えたい",
            "ピッキングに弱い古いシリンダーを交換したい",
        ],
        "causes": [
            "シリンダー内部の経年劣化・ホコリの蓄積",
            "鍵（キー）の摩耗・変形",
            "ドア建て付けのズレによる施錠不良",
            "防犯性の低い旧型ディスクシリンダー錠の使用",
        ],
        "diy": [
            "鍵穴に市販の鍵穴専用潤滑剤を少量さす（油はNG）",
            "鍵の変形は予備キーで開閉できるか確認",
            "ドアの建て付けズレは丁番のネジを軽く調整",
        ],
        "pro": [
            "鍵を紛失して開錠が必要なとき（解錠作業）",
            "防犯性の高いディンプルキーへ交換したいとき",
            "引っ越し・退去に伴うシリンダー交換",
            "補助錠の増設など防犯強化をしたいとき",
        ],
        "price": [
            ("鍵開け（解錠）", "8,000円〜"),
            ("シリンダー交換（一般的なディスク錠）", "12,000円〜"),
            ("ディンプルキーへの交換（防犯性高）", "18,000円〜"),
            ("補助錠の増設", "15,000円〜"),
        ],
        "faq": [
            ("どんな鍵でも開けられますか？", "多くの一般住宅錠に対応します。特殊錠の場合は事前に型番・写真をいただけると確実です。"),
            ("本人確認はありますか？", "防犯のため、解錠作業時はその住居の居住者であることの確認をお願いしています。"),
            ("合鍵も作れますか？", "シリンダー交換時に必要本数の鍵をお渡しします。追加作製もご相談ください。"),
        ],
    },
    {
        "slug": "wallpaper-cloth-repair",
        "title": "壁紙（クロス）の張り替え・補修｜剥がれ・カビ・穴の費用目安【東京23区】",
        "keyword": "壁紙 クロス 張り替え 補修",
        "desc": "壁紙（クロス）の剥がれ・カビ・穴あきの補修と張り替え費用の目安を解説。東京23区なら無料見積・最短即日で内装の修繕に対応します。",
        "lead": "壁紙の剥がれや変色、画びょう跡やペットによる傷は、部屋の印象を大きく左右します。部分補修で済むケースと、面（壁一面）で張り替えた方がきれいに仕上がるケースの判断ポイントを解説します。",
        "symptoms": [
            "継ぎ目や端が剥がれてめくれている",
            "結露や水回りでカビ・黒ずみが発生",
            "画びょう跡・穴・ひっかき傷がある",
            "日焼け・タバコのヤニで変色している",
        ],
        "causes": [
            "経年劣化・接着剤（のり）の弱まり",
            "結露・湿気によるカビの繁殖",
            "下地（石こうボード）の傷み",
            "生活キズ（家具の擦れ・ペット・子ども）",
        ],
        "diy": [
            "めくれは壁紙用補修のりで貼り直す",
            "小さな穴は補修用パテで埋めて平滑にする",
            "軽いカビは中性洗剤で拭き取り、乾燥させる",
        ],
        "pro": [
            "広範囲の剥がれ・変色で張り替えたいとき",
            "下地まで傷んでいる・カビが再発するとき",
            "柄合わせや継ぎ目をきれいに仕上げたいとき",
            "退去前の原状回復で部屋単位の張り替えが必要なとき",
        ],
        "price": [
            ("部分補修（小さな剥がれ・穴）", "8,000円〜"),
            ("壁一面の張り替え（量産クロス）", "1㎡あたり 1,200円〜"),
            ("お部屋まるごと張り替え（6畳目安）", "40,000円〜"),
            ("下地補修を含む張り替え", "別途お見積もり"),
        ],
        "faq": [
            ("一部だけ張り替えると色が浮きませんか？", "既存クロスが日焼けしていると差が出る場合があります。気になる場合は壁一面単位での張り替えをおすすめします。"),
            ("どのくらいの日数がかかりますか？", "1部屋であれば1日で完了することが多いです。範囲に応じて事前にお伝えします。"),
            ("家具があっても作業できますか？", "可能です。当日に軽く移動して施工し、作業後に戻します。大型家具は事前にご相談ください。"),
        ],
    },
    {
        "slug": "flooring-repair",
        "title": "フローリング・床の傷／きしみ補修｜張り替え費用と即日対応【東京23区】",
        "keyword": "フローリング 補修 張り替え きしみ",
        "desc": "フローリングの傷・へこみ・きしみ・浮きの補修と張り替えの費用目安を解説。東京23区なら無料見積で床の修繕に最短即日対応します。",
        "lead": "歩くたびにギシギシ鳴る、家具で付いた傷やへこみ、水こぼしによる膨れ——床のトラブルは見た目だけでなく、放置すると下地の傷みにつながります。補修で直る範囲と張り替えの判断を解説します。",
        "symptoms": [
            "歩くと床がきしむ・ギシギシ鳴る",
            "表面に傷・へこみ・剥がれがある",
            "水濡れで膨れ・浮き・変色している",
            "床が一部沈む・フワフワする",
        ],
        "causes": [
            "下地（根太・合板）の緩みや釘鳴り",
            "家具・落下物による生活キズ",
            "水こぼし・結露による膨張",
            "経年劣化による表面材の剥離",
        ],
        "diy": [
            "浅い傷は補修クレヨン・かくれん棒で色を合わせる",
            "きしみは専用の床鳴り止めビスで軽減（要下地確認）",
            "小さなへこみは固く絞った布＋アイロンで戻ることも",
        ],
        "pro": [
            "広範囲の傷み・浮き・膨れで張り替えが必要なとき",
            "床が沈む・下地が傷んでいる可能性があるとき",
            "数枚単位での部分張り替え（はぎ替え）をしたいとき",
            "フロアタイル・クッションフロアへの変更を検討するとき",
        ],
        "price": [
            ("傷・へこみの部分補修", "8,000円〜"),
            ("床鳴り（きしみ）の補修", "10,000円〜"),
            ("フローリング部分張り替え（数枚）", "20,000円〜"),
            ("クッションフロア張り替え（6畳目安）", "35,000円〜"),
        ],
        "faq": [
            ("傷一つでも来てもらえますか？", "もちろん可能です。小さな補修でも東京23区なら出張費0円でお伺いします。"),
            ("元の床と同じ柄にできますか？", "近い色柄の材料をご用意します。廃番品の場合は近似品をご提案します。"),
            ("マンションの防音規定が心配です", "管理規約の遮音等級（LL-45など）に適合した床材をご提案できます。事前にお知らせください。"),
        ],
    },
    {
        "slug": "aircon-repair",
        "title": "エアコンの水漏れ・効かない｜修理とクリーニングの費用【東京23区】",
        "keyword": "エアコン 水漏れ 効かない 修理",
        "desc": "エアコンから水漏れする・冷えない／暖まらないときの原因と、修理・クリーニングの費用目安を解説。東京23区なら最短即日で対応します。",
        "lead": "エアコンの水漏れや効きの悪さは、ドレン詰まりやフィルター汚れなど身近な原因が多くを占めます。買い替える前に確認したいポイントと、プロのクリーニング・修理で改善するケースを紹介します。",
        "symptoms": [
            "室内機から水がポタポタ落ちる",
            "冷えない・暖まらない・風が弱い",
            "運転中にカビ臭い・異音がする",
            "リモコン操作に反応しない・エラー表示",
        ],
        "causes": [
            "ドレンホースの詰まり・勾配不良による水漏れ",
            "フィルター・熱交換器の汚れによる能力低下",
            "冷媒ガス不足（効きが悪い主因のひとつ）",
            "基板・センサーの故障",
        ],
        "diy": [
            "フィルターを外して掃除機・水洗いで清掃",
            "ドレンホースの先端のゴミを取り除く",
            "リモコンの電池交換・設定（運転モード/温度）を確認",
        ],
        "pro": [
            "ドレン詰まりの本格洗浄が必要なとき",
            "分解を伴うエアコンクリーニングをしたいとき",
            "冷媒ガス補充・基板交換など内部修理が必要なとき",
            "取り付け・取り外し・移設をしたいとき",
        ],
        "price": [
            ("水漏れ（ドレン詰まり）修理", "8,000円〜"),
            ("壁掛けエアコンクリーニング（1台）", "11,000円〜"),
            ("お掃除機能付きエアコンのクリーニング", "18,000円〜"),
            ("取り付け・取り外し", "12,000円〜"),
        ],
        "faq": [
            ("水漏れはすぐ直りますか？", "ドレン詰まりが原因であれば当日中に解消できることがほとんどです。"),
            ("クリーニングはどのくらい時間がかかりますか？", "1台あたり1〜1.5時間が目安です。複数台もまとめて対応できます。"),
            ("古いエアコンでも修理できますか？", "可能な範囲で修理しますが、部品供給が終了している場合は買い替え・取り付けをご提案します。"),
        ],
    },
    {
        "slug": "door-screen-repair",
        "title": "ドア・建具・網戸の修理｜立て付け・蝶番・網戸張り替え【東京23区】",
        "keyword": "ドア 建具 網戸 修理 張り替え",
        "desc": "ドアの立て付け不良・蝶番のゆるみ・網戸の張り替えなど建具の修理費用を解説。東京23区なら無料見積で建具トラブルに即日対応します。",
        "lead": "ドアが閉まりにくい、きしむ、網戸が破れた——建具の不具合は毎日のストレスになり、防犯・虫除けにも影響します。蝶番の調整から網戸の張り替えまで、症状別の対処法と費用を解説します。",
        "symptoms": [
            "ドアが閉まりにくい・床に擦れる",
            "開閉時にキィキィ音がする",
            "ドアノブ・レバーがぐらつく・回らない",
            "網戸が破れている・外れる・建て付けが悪い",
        ],
        "causes": [
            "蝶番（丁番）の緩み・経年でのズレ",
            "建物の歪み・湿気による建具の膨張",
            "ドアノブ・ラッチ機構の摩耗",
            "網（ネット）の劣化・戸車の損傷",
        ],
        "diy": [
            "蝶番のネジをドライバーで軽く締め直す",
            "きしみは蝶番の軸に少量の潤滑剤をさす",
            "網戸のたるみは戸車の高さ調整ネジで微調整",
        ],
        "pro": [
            "調整しても立て付けが直らないとき",
            "ドアノブ・レバーハンドルの交換が必要なとき",
            "網戸の網張り替え・戸車交換をしたいとき",
            "ドア本体・引き戸の交換が必要なとき",
        ],
        "price": [
            ("蝶番調整・立て付け直し", "6,000円〜"),
            ("ドアノブ・レバーハンドル交換", "9,000円〜"),
            ("網戸の網張り替え（1枚）", "4,000円〜"),
            ("戸車交換・引き戸調整", "8,000円〜"),
        ],
        "faq": [
            ("網戸1枚だけでも頼めますか？", "はい、1枚から承ります。複数枚まとめてのご依頼もお得です。"),
            ("ペット対応の丈夫な網はありますか？", "ペット用の強度が高い網もご用意できます。ご希望をお知らせください。"),
            ("玄関ドアの調整もできますか？", "可能です。建て付けや戸当たりの調整、ドアクローザーの交換にも対応します。"),
        ],
    },
    {
        "slug": "outlet-switch-light",
        "title": "コンセント・スイッチ・照明の電気工事｜即日対応と費用相場【東京23区】",
        "keyword": "コンセント スイッチ 照明 電気工事",
        "desc": "コンセントの増設・交換、スイッチの故障、照明器具の取り付け・交換など電気工事の費用相場を解説。東京23区なら有資格者が最短即日で対応します。",
        "lead": "コンセントが使えない、スイッチが効かない、照明がチカチカする——電気のトラブルは火災や感電のリスクがあり、DIYが難しい分野です。電気工事士の資格が必要な作業も含め、プロに任せるべき理由と費用を解説します。",
        "symptoms": [
            "コンセントが使えない・差込口が焦げ臭い",
            "スイッチを押しても反応しない・効きが悪い",
            "照明がチカチカする・つかない",
            "コンセントを増やしたい・位置を変えたい",
        ],
        "causes": [
            "配線の緩み・劣化・接触不良",
            "スイッチ・コンセント本体の故障",
            "照明器具・安定器・LEDドライバーの寿命",
            "容量不足・ブレーカーの不具合",
        ],
        "diy": [
            "電球・蛍光灯の交換、LEDへの付け替え",
            "ブレーカーが落ちていないか確認・復帰",
            "タコ足配線を見直して容量超過を避ける",
        ],
        "pro": [
            "コンセント・スイッチの交換／増設（電気工事士が必要）",
            "差込口の焦げ・発熱など発火リスクがあるとき",
            "照明器具の取り付け・引掛シーリングの新設",
            "アンテナ・インターホンの設置や配線工事",
        ],
        "price": [
            ("コンセント・スイッチ交換", "6,000円〜"),
            ("コンセント増設（配線含む）", "12,000円〜"),
            ("照明器具の取り付け・交換", "7,000円〜"),
            ("インターホン交換", "10,000円〜"),
        ],
        "faq": [
            ("資格を持った人が来ますか？", "コンセントや配線を扱う作業は、電気工事士の資格を持つスタッフが施工します。安心してお任せください。"),
            ("焦げ臭いのですが急いで見てほしい", "発火の危険があるため、まず該当ブレーカーを落としてください。東京23区なら最短即日でお伺いします。"),
            ("照明器具は持ち込みでもいいですか？", "はい、お客様ご支給の器具の取り付けにも対応します。適合の可否は事前に写真でご確認します。"),
        ],
    },
]


# ---- テンプレート --------------------------------------------------------
def esc(s):
    return html.escape(s, quote=True)


CSS = """:root{
  --brand:#1f6feb; --brand-dark:#0b4fbf; --ink:#1a1a1a; --muted:#5b6470;
  --line:#e6e8eb; --bg:#f7f9fc; --accent:#ff7a18;
}
*{box-sizing:border-box}
body{margin:0;font-family:-apple-system,BlinkMacSystemFont,"Hiragino Kaku Gothic ProN","Noto Sans JP",sans-serif;
  color:var(--ink);background:var(--bg);line-height:1.8;-webkit-font-smoothing:antialiased}
a{color:var(--brand);text-decoration:none}
a:hover{text-decoration:underline}
.container{max-width:760px;margin:0 auto;padding:0 20px}
header.site{background:#fff;border-bottom:1px solid var(--line);position:sticky;top:0;z-index:10}
header.site .container{display:flex;align-items:center;justify-content:space-between;height:60px}
header.site .brand{font-weight:700;font-size:17px;color:var(--ink)}
header.site .tel{font-weight:700;color:var(--brand)}
.hero{background:linear-gradient(135deg,var(--brand),var(--brand-dark));color:#fff;padding:40px 0}
.hero h1{margin:0 0 8px;font-size:24px;line-height:1.4}
.hero p{margin:0;opacity:.95}
.badges{display:flex;gap:8px;flex-wrap:wrap;margin-top:14px}
.badge{background:rgba(255,255,255,.18);border:1px solid rgba(255,255,255,.35);
  border-radius:999px;padding:4px 12px;font-size:13px}
main{padding:28px 0 56px}
article h2{font-size:20px;margin:32px 0 12px;padding-left:12px;border-left:5px solid var(--brand)}
article h3{font-size:17px;margin:22px 0 8px}
article p{margin:12px 0}
ul.check{list-style:none;padding:0;margin:12px 0}
ul.check li{position:relative;padding:6px 0 6px 28px}
ul.check li::before{content:"✓";position:absolute;left:0;top:6px;color:var(--brand);font-weight:700}
ul.warn li::before{content:"!";color:var(--accent)}
table.price{width:100%;border-collapse:collapse;margin:14px 0;background:#fff;
  border:1px solid var(--line);border-radius:10px;overflow:hidden}
table.price th,table.price td{padding:12px 14px;border-bottom:1px solid var(--line);text-align:left}
table.price th{background:#eef4ff;width:62%}
table.price tr:last-child td,table.price tr:last-child th{border-bottom:0}
.note{font-size:13px;color:var(--muted)}
.faq{background:#fff;border:1px solid var(--line);border-radius:10px;padding:6px 18px;margin:10px 0}
.faq dt{font-weight:700;margin:14px 0 4px}
.faq dt::before{content:"Q. ";color:var(--brand)}
.faq dd{margin:0 0 14px;color:#333}
.faq dd::before{content:"A. ";color:var(--accent);font-weight:700}
.cta{background:#fff;border:2px solid var(--brand);border-radius:14px;padding:24px;margin:34px 0;text-align:center}
.cta h3{margin:0 0 6px;font-size:19px}
.cta p{margin:4px 0 16px;color:var(--muted)}
.cta-btns{display:flex;gap:12px;flex-wrap:wrap;justify-content:center}
.btn{display:inline-block;padding:14px 26px;border-radius:999px;font-weight:700;font-size:16px}
.btn-tel{background:var(--brand);color:#fff}
.btn-line{background:#06c755;color:#fff}
.btn-mail{background:var(--accent);color:#fff}
.cta .consult{display:inline-block;margin-bottom:10px;font-weight:700;color:var(--accent);
  font-size:15px;letter-spacing:.04em}
.cta .mailrow{margin-top:14px;font-size:14px;color:var(--muted)}
.btn-site{background:#fff;color:var(--brand);border:2px solid var(--brand)}
.btn:hover{opacity:.9;text-decoration:none}
.related{margin:34px 0}
.related h2{border-left-color:var(--accent)}
.related ul{padding-left:18px}
.related li{margin:6px 0}
#ref_6953ac0c3fcfbbee9aa49aaa_home-reform-general{
  font-size:12px;color:var(--muted);border-top:1px solid var(--line);
  margin-top:40px;padding-top:16px;line-height:1.7}
footer.site{background:#0d1b2a;color:#c7d0db;padding:28px 0;font-size:13px}
footer.site a{color:#9ec5ff}
footer.site .row{display:flex;justify-content:space-between;flex-wrap:wrap;gap:10px}
.card-list{display:grid;grid-template-columns:1fr;gap:14px;margin:20px 0}
@media(min-width:640px){.card-list{grid-template-columns:1fr 1fr}}
.card{background:#fff;border:1px solid var(--line);border-radius:12px;padding:18px;transition:.15s}
.card:hover{box-shadow:0 6px 18px rgba(0,0,0,.06);transform:translateY(-2px)}
.card a{font-weight:700;font-size:16px;line-height:1.5}
.card .kw{display:inline-block;margin-top:8px;font-size:12px;color:var(--muted);
  background:#eef4ff;border-radius:6px;padding:2px 8px}
.breadcrumb{font-size:13px;color:var(--muted);margin:18px 0 0}
"""


def header_html(active_home=False):
    home = "index.html"
    return f"""<header class="site"><div class="container">
  <a class="brand" href="{home}">{esc(SITE_NAME)}</a>
  <a class="tel" href="{TEL_LINK}">☎ {TEL}</a>
</div></header>"""


def footer_html():
    return f"""<footer class="site"><div class="container">
  <div class="row">
    <div><strong>{esc(SITE_NAME)}</strong><br>東京23区全域・住宅の修理／リフォーム</div>
    <div>
      <a href="{TEL_LINK}">☎ {TEL}</a>
      <a href="{LINE_URL}" target="_blank" rel="noopener">LINEで相談</a>
      <a href="{EMAIL_LINK}">✉ {EMAIL}</a><br>
      <a href="{SITE_URL}" target="_blank" rel="noopener">公式サイトはこちら</a>
    </div>
  </div>
  <p class="note" style="margin-top:14px;color:#7f8a99">壁・床・水回り・鍵・電気など100種類以上の修理に対応。無料見積もり・追加料金なし・施工保証。</p>
</div></footer>"""


def cta_html(topic):
    return f"""<div class="cta">
  <span class="consult">＼ ご相談はこちら ／</span>
  <h3>{esc(topic)}でお困りなら、まずは無料相談</h3>
  <p>東京23区全域・最短即日対応／出張費・見積費用0円／追加料金なしの明朗会計</p>
  <div class="cta-btns">
    <a class="btn btn-tel" href="{TEL_LINK}">☎ 電話で相談（{TEL}）</a>
    <a class="btn btn-line" href="{LINE_URL}" target="_blank" rel="noopener">LINEで相談する</a>
    <a class="btn btn-site" href="{SITE_URL}" target="_blank" rel="noopener">公式サイトを見る</a>
  </div>
  <p class="mailrow">メールでのご相談は <a href="{EMAIL_LINK}">{EMAIL}</a> まで</p>
</div>"""


def related_html(current_slug):
    items = [a for a in ARTICLES if a["slug"] != current_slug][:4]
    lis = "\n".join(
        f'    <li><a href="{a["slug"]}.html">{esc(a["title"])}</a></li>' for a in items
    )
    return f"""<section class="related">
  <h2>関連記事</h2>
  <ul>
{lis}
  </ul>
</section>"""


def article_html(a):
    symptoms = "\n".join(f"    <li>{esc(s)}</li>" for s in a["symptoms"])
    causes = "\n".join(f"    <li>{esc(s)}</li>" for s in a["causes"])
    diy = "\n".join(f"    <li>{esc(s)}</li>" for s in a["diy"])
    pro = "\n".join(f"    <li>{esc(s)}</li>" for s in a["pro"])
    price_rows = "\n".join(
        f"    <tr><th>{esc(item)}</th><td>{esc(val)}</td></tr>" for item, val in a["price"]
    )
    faq = "\n".join(
        f"    <dt>{esc(q)}</dt>\n    <dd>{esc(ans)}</dd>" for q, ans in a["faq"]
    )
    topic = a["title"].split("｜")[0].split("（")[0]

    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(a["title"])}</title>
<meta name="description" content="{esc(a["desc"])}">
<meta name="keywords" content="{esc(a["keyword"])},東京23区,即日,修理,リフォーム">
<meta name="robots" content="index,follow,max-image-preview:large">
<meta name="author" content="{esc(SITE_NAME)}">
<meta property="og:title" content="{esc(a["title"])}">
<meta property="og:description" content="{esc(a["desc"])}">
<meta property="og:type" content="article">
<meta property="og:url" content="{DOMAIN}/{a['slug']}.html">
<meta property="og:site_name" content="{esc(BLOG_NAME)}">
<meta property="og:locale" content="ja_JP">
<meta name="twitter:card" content="summary">
<meta name="twitter:title" content="{esc(a["title"])}">
<meta name="twitter:description" content="{esc(a["desc"])}">
<link rel="canonical" href="{DOMAIN}/{a['slug']}.html">
<link rel="stylesheet" href="style.css">
<script type="application/ld+json">
{article_jsonld(a, topic)}
</script>
</head>
<body>
{header_html()}
<div class="hero"><div class="container">
  <h1>{esc(a["title"])}</h1>
  <p>{esc(a["desc"])}</p>
  <div class="badges">
    <span class="badge">東京23区全域</span>
    <span class="badge">最短即日対応</span>
    <span class="badge">出張・見積0円</span>
    <span class="badge">追加料金なし</span>
  </div>
</div></div>
<main><div class="container">
<p class="breadcrumb"><a href="index.html">記事一覧</a> ＞ {esc(topic)}</p>
<article>
  <p>{esc(a["lead"])}</p>

  <h2>こんな症状はありませんか？</h2>
  <ul class="check">
{symptoms}
  </ul>

  <h2>主な原因</h2>
  <ul class="check">
{causes}
  </ul>

  <h2>自分でできる応急処置</h2>
  <ul class="check">
{diy}
  </ul>
  <p class="note">※無理な作業はかえって被害を広げることがあります。不安な場合は触らずにご相談ください。</p>

  <h2>プロに依頼すべきケース</h2>
  <ul class="check warn">
{pro}
  </ul>

  <h2>修理費用の目安</h2>
  <table class="price">
    <tr><th>作業内容</th><td>料金目安（税込）</td></tr>
{price_rows}
  </table>
  <p class="note">※症状・部材により変動します。作業前に必ず無料でお見積もりし、ご納得いただいてから着手します。</p>

  <h2>ご依頼の流れ</h2>
  <ul class="check">
    <li>お電話（{TEL}）・LINE・メール（{EMAIL}）で症状をご連絡（写真があるとスムーズ）</li>
    <li>訪問日時の調整（東京23区は最短即日）</li>
    <li>現地確認・無料お見積もり</li>
    <li>ご納得のうえで作業／お支払い・施工保証のご案内</li>
  </ul>

  <h2>対応エリア</h2>
  <p>{esc(AREA)}（千代田・中央・港・新宿・文京・台東・墨田・江東・品川・目黒・大田・世田谷・渋谷・中野・杉並・豊島・北・荒川・板橋・練馬・足立・葛飾・江戸川）に対応しています。</p>

  <h2>よくある質問</h2>
  <dl class="faq">
{faq}
  </dl>

{cta_html(topic)}

{related_html(a["slug"])}

  {ZEHITOMO_SNIPPET}
</article>
</div></main>
{footer_html()}
</body>
</html>
"""


def _dump(obj):
    return json.dumps(obj, ensure_ascii=False, indent=2)


def local_business_node():
    """全ページ共通の地域ビジネス（ローカルSEO）ノード"""
    return {
        "@type": ["LocalBusiness", "HomeAndConstructionBusiness"],
        "@id": DOMAIN + "/#business",
        "name": SITE_NAME,
        "url": SITE_URL,
        "telephone": TEL_E164,
        "email": EMAIL,
        "image": DOMAIN + "/index.html",
        "description": "東京23区全域に対応する住宅修理・リフォームサービス。"
        "壁・床・水回り・鍵・電気など100種類以上の修理に最短即日で対応。"
        "出張費・見積費用0円、追加料金なしの明朗会計、施工保証あり。",
        "areaServed": [
            {"@type": "AdministrativeArea", "name": "東京都" + w} for w in WARDS
        ],
        "address": {"@type": "PostalAddress", "addressRegion": "東京都", "addressCountry": "JP"},
        "priceRange": "¥¥",
        "openingHours": "Mo-Su 08:00-21:00",
        "sameAs": [
            "https://www.zehitomo.com/profile/%E5%B2%A9%E6%9C%AC-%E8%B3%A2%E4%BC%B8-v15BjMo3R/pro"
        ],
    }


def article_jsonld(a, topic):
    page_url = DOMAIN + "/" + a["slug"] + ".html"
    blog_posting = {
        "@type": "BlogPosting",
        "@id": page_url + "#article",
        "headline": a["title"],
        "description": a["desc"],
        "url": page_url,
        "mainEntityOfPage": page_url,
        "inLanguage": "ja",
        "datePublished": PUBLISH_DATE,
        "dateModified": PUBLISH_DATE,
        "keywords": a["keyword"] + ",東京23区,即日,修理,リフォーム",
        "articleSection": topic,
        "author": {"@id": DOMAIN + "/#business"},
        "publisher": {"@id": DOMAIN + "/#business"},
    }
    breadcrumb = {
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "記事一覧", "item": DOMAIN + "/"},
            {"@type": "ListItem", "position": 2, "name": topic, "item": page_url},
        ],
    }
    faq = {
        "@type": "FAQPage",
        "@id": page_url + "#faq",
        "mainEntity": [
            {
                "@type": "Question",
                "name": q,
                "acceptedAnswer": {"@type": "Answer", "text": ans},
            }
            for q, ans in a["faq"]
        ],
    }
    graph = {"@context": "https://schema.org", "@graph": [local_business_node(), blog_posting, breadcrumb, faq]}
    return _dump(graph)


def index_jsonld():
    items = {
        "@type": "ItemList",
        "itemListElement": [
            {
                "@type": "ListItem",
                "position": i + 1,
                "url": DOMAIN + "/" + a["slug"] + ".html",
                "name": a["title"],
            }
            for i, a in enumerate(ARTICLES)
        ],
    }
    website = {
        "@type": "WebSite",
        "@id": DOMAIN + "/#website",
        "url": DOMAIN + "/",
        "name": BLOG_NAME,
        "inLanguage": "ja",
        "publisher": {"@id": DOMAIN + "/#business"},
    }
    graph = {"@context": "https://schema.org", "@graph": [local_business_node(), website, items]}
    return _dump(graph)


def index_html():
    cards = "\n".join(
        f"""  <div class="card">
    <a href="{a['slug']}.html">{esc(a['title'])}</a><br>
    <span class="kw">検索ワード: {esc(a['keyword'])}</span>
  </div>"""
        for a in ARTICLES
    )
    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>住まいの修理コラム｜東京23区・即日対応の住宅修理／リフォーム</title>
<meta name="description" content="トイレ・蛇口・排水・給湯器・鍵・壁紙・床・エアコン・建具・電気まで。東京23区の住宅修理に役立つコラムと、最短即日・無料見積もりの修理サービスをご案内します。">
<meta name="robots" content="index,follow,max-image-preview:large">
<meta property="og:title" content="住まいの修理コラム｜東京23区・即日対応の住宅修理／リフォーム">
<meta property="og:description" content="東京23区の住宅修理に役立つコラム。トイレ・蛇口・排水・給湯器・鍵・壁紙・床・エアコン・建具・電気まで最短即日・無料見積もりで対応。">
<meta property="og:type" content="website">
<meta property="og:url" content="{DOMAIN}/">
<meta property="og:site_name" content="{esc(BLOG_NAME)}">
<meta property="og:locale" content="ja_JP">
<meta name="twitter:card" content="summary">
<link rel="canonical" href="{DOMAIN}/">
<link rel="stylesheet" href="style.css">
<script type="application/ld+json">
{index_jsonld()}
</script>
</head>
<body>
{header_html()}
<div class="hero"><div class="container">
  <h1>住まいの修理コラム</h1>
  <p>東京23区の「困った」を最短即日で解決。水回り・鍵・内装・電気まで100種類以上の修理に対応します。</p>
  <div class="badges">
    <span class="badge">東京23区全域</span>
    <span class="badge">最短即日対応</span>
    <span class="badge">出張・見積0円</span>
    <span class="badge">施工保証あり</span>
  </div>
</div></div>
<main><div class="container">
  <h2 style="border-left:5px solid var(--brand);padding-left:12px">記事一覧</h2>
  <div class="card-list">
{cards}
  </div>
{cta_html("住まいの修理")}
</div></main>
{footer_html()}
</body>
</html>
"""


def sitemap_xml():
    urls = [DOMAIN + "/"] + [DOMAIN + "/" + a["slug"] + ".html" for a in ARTICLES]
    rows = []
    for i, u in enumerate(urls):
        prio = "1.0" if i == 0 else "0.8"
        rows.append(
            "  <url>\n"
            f"    <loc>{u}</loc>\n"
            f"    <lastmod>{PUBLISH_DATE}</lastmod>\n"
            "    <changefreq>weekly</changefreq>\n"
            f"    <priority>{prio}</priority>\n"
            "  </url>"
        )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "\n".join(rows)
        + "\n</urlset>\n"
    )


def robots_txt():
    return (
        "User-agent: *\n"
        "Allow: /\n\n"
        f"Sitemap: {DOMAIN}/sitemap.xml\n"
    )


def main():
    # CSS
    with open(os.path.join(OUT_DIR, "style.css"), "w", encoding="utf-8") as f:
        f.write(CSS)
    # index
    with open(os.path.join(OUT_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(index_html())
    # articles
    for a in ARTICLES:
        path = os.path.join(OUT_DIR, a["slug"] + ".html")
        with open(path, "w", encoding="utf-8") as f:
            f.write(article_html(a))
    # sitemap & robots
    with open(os.path.join(OUT_DIR, "sitemap.xml"), "w", encoding="utf-8") as f:
        f.write(sitemap_xml())
    with open(os.path.join(OUT_DIR, "robots.txt"), "w", encoding="utf-8") as f:
        f.write(robots_txt())
    print(
        f"Generated {len(ARTICLES)} articles + index.html + style.css "
        f"+ sitemap.xml + robots.txt in {OUT_DIR}"
    )


if __name__ == "__main__":
    main()
