# 孫LOVE 画像素材プロンプト集（ChatGPT / Midjourney / Vertex AI 用）

アプリの「ギルド設定 → シーン背景・UI素材」にドロップすると、その場面の背景やセリフ枠として使われます。
同じ設定画面の「📋 プロンプト」ボタンからもコピーできます。「✨ 生成」を押せばアプリ内（Vertex AI）で直接生成もできます。

## 使い方（ChatGPT の場合）
1. ChatGPT で「画像を生成して」と伝え、下の英語プロンプトを貼り付ける（日本語の補足を添えてもOK）
2. できた画像を保存し、アプリの該当スロットにドロップ
3. 気に入らなければ「もっと明るく」「窓を大きく」など追加指示で作り直す

## 統一スタイル（すべてのプロンプトの末尾に付けると雰囲気が揃います）
```
painterly anime background art, high-quality JRPG cutscene quality, soft volumetric light, rich but harmonious colors (deep navy, warm gold, rose-pink accents), no people, no text, no watermark
```

## シーン背景（16:9 推奨 1920×1080、JPG/PNG）

### 🏰 ギルドホール（拠点。キャラが立ち、行き先を選ぶ部屋）
```
A grand fantasy guild hall interior at golden hour, wide angle, empty (no people), warm candlelight and sunbeams through tall windows, wooden beams, a large map table in the center-left, a quest notice board on the right wall, bookshelves, a brass clock, crates near the door, soft depth of field, painterly anime background art (like a high-quality JRPG cutscene), 16:9, no text
```
日本語補足: 右側1/3はキャラクターが立つので、右側は物を置かず少し空けてください。

### 🗺️ ワールドマップ（地図の机）
```
A cartographer's room in a fantasy guild, an enormous parchment map spread on an oak table with compasses, magnifying glass and brass instruments, moonlight and blue-teal magical glow, empty (no people), painterly anime background art, 16:9, no text
```

### 📜 クエスト掲示板
```
A wooden quest notice board in a fantasy guild hall covered with parchment scrolls, wax seals and pinned notes, warm amber lantern light, empty (no people), painterly anime background art, 16:9, no text
```

### 📖 物件図鑑（書庫）
```
A cozy fantasy library alcove with tall bookshelves, leather-bound tomes, an open illustrated encyclopedia on a lectern, green-gold lamplight, dust motes, empty (no people), painterly anime background art, 16:9, no text
```

### 🕰️ 冒険の暦（大時計）
```
A fantasy clock tower interior with a giant brass astronomical clock, gears, hanging calendars and star charts, night sky through the window, violet and indigo tones, empty (no people), painterly anime background art, 16:9, no text
```

### 📦 素材の搬入（倉庫）
```
A fantasy guild storeroom with wooden crates, rolled blueprints, scrolls and a delivery cart, warm brown tones, lantern light, empty (no people), painterly anime background art, 16:9, no text
```

### 🏥 街の施設（街へ出る）
```
A charming fantasy town street at sunset seen from the guild entrance, a clinic with a red cross sign, a town hall with a clock, small shops, warm orange light, empty (no people), painterly anime background art, 16:9, no text
```

### 📈 領地の統計（観測所）
```
A fantasy observatory room with a brass telescope, glowing star charts, floating holographic graphs and population maps, deep indigo and cyan light, empty (no people), painterly anime background art, 16:9, no text
```

### 📯 ギルド日誌（受付の台帳）
```
A fantasy guild receptionist's desk with an open ledger, quill, candle, wax seals and stacked letters, warm golden light, empty (no people), painterly anime background art, 16:9, no text
```

### ⚙️ ギルド設定（受付）
```
A fantasy guild reception desk with a brass bell, ledgers, a key rack and a stone wall with hanging crests, neutral gray-gold tones, empty (no people), painterly anime background art, 16:9, no text
```

## UI 素材（PNG・背景透過）

### セリフ枠（1024×512、中央は半透明の濃紺、縁に金の装飾）
```
A fantasy RPG dialogue box frame, ornate gold filigree border with rounded corners on a dark navy semi-transparent panel, empty inside, symmetrical, clean edges, game UI asset, transparent background, 2:1, no text
```
日本語補足: 四隅の装飾は端から 120px 以内に収め、辺の中央部は同じ模様の繰り返しにすると、どんな長さの文章でも自然に伸びます。

### ボタン（512×160）
```
A fantasy RPG UI button, rounded rectangle, rose-pink to crimson gradient with gold trim and a subtle inner glow, empty (no text), game UI asset, transparent background, 3:1
```

### 紋章・ロゴ（1024×1024）
```
A guild emblem for a caring senior-home company named 孫LOVE: a warm heart with a small house and a sprout, gold and rose-pink metallic, fantasy RPG crest style, centered, transparent background, no text
```

## キャラクター（元画像は白背景・全身。アプリが自動で透過します）
既存の4キャラの表情は、アプリの「表情を生成」で元画像から作るのが最も一致します。ChatGPT で作る場合は、元画像を添付して次のように指示してください。
```
Generate the SAME character: identical face, hairstyle, animal ears, outfit, accessories, art style and proportions. Keep the full-body standing pose and a plain pure-white background. Change only the expression and gesture to: {表情}. Single character, centered, no text.
```
表情の例: `big happy smile, waving one hand` / `excited cheering pose with both fists raised` / `surprised, wide eyes, mouth open` / `thoughtful, one hand on chin` / `worried, eyebrows raised, hands clasped` / `sleepy, yawning`

## 新しいキャラを追加したい場合（例）
```
Full-body anime illustration of a friendly caregiver character with cat ears and a fluffy tail, mid-20s, light green polo shirt and white apron with a paw-print name tag reading nothing, sneakers, standing, gentle smile, plain pure-white background, single character, centered, no text
```
（アプリ側のキャラ枠を増やすには開発者にご相談ください）
