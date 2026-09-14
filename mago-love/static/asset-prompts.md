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

## ギルドホールの「場面画像」（キャラがその場所にいる絵）
「ギルドホール」スロットに 16:9 の背景を入れると、拠点画面は **場面画像モード** になります。キャラを動かすのではなく、
「地図の机に座っている」「掲示板の前に立っている」など **場所ごとの完成画像** をあらかじめ用意し、クリックした場所の絵へゆっくりクロスフェードします。

- 生成はアプリ内で: ギルド設定 → 「🎞 ホールの場面画像」 → 人物を選び「この人物の全場面を生成」（10枚）。ホール背景＋キャラ元画像を渡して合成します
- ChatGPT で作る場合: ホール背景とキャラの元画像の **2枚を添付** して、「📋 プロンプト」でコピーした指示文を貼り付けます。できた画像をその場面の枠にドロップ
- 場面画像がない場所は、ホール背景のまま画面が切り替わります（エラーにはなりません）
- 仲間は持ち場（ルカ=地図の机、ハルト施設長=掲示板、コタロウ=暖炉、モモ=扉）に顔チップで立ち、クリックすると話しかけられ、その人の場面画像があればそれに切り替わって案内してくれます
- セリフ枠の左に話し手の顔が出て、表情画像がここで切り替わります
- **話しかける（モンハン風）**: 場面画像の中のキャラは呼吸するように僅かに動き、マウスを乗せると「💬 話す」が出ます。クリックするとカメラがそのキャラに寄って背景がぼけ、正面を向いた立ち絵が現れて表情を変えながら話します。「◀ 戻る」か背景クリックで引きます
- キャラの位置（カメラが寄る範囲）は、場面画像と背景の差分から自動で検出します。設定のサムネイルに金色の枠で表示され、ずれていれば「🎯 焦点」で検出し直せます

### ChatGPT 用の合成プロンプト（2枚添付: 1枚目=ホール背景、2枚目=キャラ）
```
Image 1 is a background painting of a fantasy guild hall. Image 2 is a character illustration on a white background. Create ONE new image: the exact same guild hall from image 1 (same composition, camera angle, furniture, lighting and colors, nothing added or removed), with the character from image 2 placed naturally inside it, {場所の指示}. Keep the character's identity exactly: same face, hairstyle, animal ears, outfit and colors. Match the character's scale to the perspective of the room, match the warm lighting and cast a soft shadow on the floor so the character looks like they belong there. Single character only, no other people, no text, no speech bubbles, no watermark. Painterly anime style consistent with the background. Aspect ratio 16:9.
```
場所の指示の例（アプリの各場面と同じ）:
- ギルドホール（拠点）: `sitting relaxed on a chair at the large map table in the left foreground, one hand resting on the map, looking toward the viewer with a welcoming smile`
- ワールドマップ: `standing at the large map table in the left foreground, leaning over the map and pointing at a spot on it`
- クエスト掲示板: `standing in front of the quest notice board on the right wall, looking up at the pinned notices`
- 物件図鑑: `standing at the tall bookshelf on the left, pulling out a book`
- 冒険の暦: `standing near the lantern below the balcony in the center-right, looking up at it`
- 素材の搬入: `standing beside the wooden crates on the right, checking a rolled scroll`
- 街の施設: `standing in the open doorway in the center, looking out at the town`
- 領地の統計: `standing beside the globe in the left foreground, one hand on the globe`
- ギルド日誌: `sitting in the armchair by the fireplace on the left, reading a ledger`
- ギルド設定: `standing at the foot of the staircase in the center, one hand on the railing`

## 動画クリップ（本当に生きているホール）
場面画像を **最初のフレーム** にして、数秒の動画を作ります。ホールでは待機ループが流れ続け、キャラをクリックすると会話クリップに切り替わります。

- アプリ内で生成: ギルド設定 → 「🎬 動画クリップ」 → 「待機ループを全部生成」「会話クリップを全部生成」（Veo、Cloud Run 上で自動認証。1本 1〜3分、百数十円〜数百円程度）
- 他のツールで作る場合: 各行の 📋 で指示文をコピーし、Veo（Google AI Studio）/ Runway / Kling / Luma などの「画像から動画」に、その場面の画像と一緒に貼り付けます。できた MP4 を 📁 でアップロード
- 待機ループは「最後のフレームが最初のフレームに近い」ように指示してあります。アプリ側でも終わり際に次の再生を重ねてクロスフェードするので、つなぎ目は目立ちません

### 待機ループ（画像から動画）
```
Cinematic idle loop of the same scene. The character stays in place and {場所の指示}, breathing softly, shifting weight slightly, blinking and glancing around the room naturally. Candle light flickers, dust motes drift in the sunbeams. The camera holds almost still with a very slow, subtle drift. No speech, no text, no captions, no new people. The final frame should closely match the first frame so the clip can loop seamlessly. Painterly anime style consistent with the image.
```
### 会話クリップ（画像から動画）
```
The camera slowly pushes in toward the character. The character notices the viewer, turns to face the camera, smiles warmly and starts talking with natural, lively gestures and clear mouth movement, like a friendly guild member greeting a visitor. Warm lighting, shallow depth of field on the background. No text, no captions, no new people. Painterly anime style consistent with the image.
```

## 声と環境音
- セリフは Google Cloud Text-to-Speech（日本語 Neural2 の声）で読み上げます。キャラごとに声の高さと速さを変えてあります。利用できない環境ではブラウザの読み上げで代用します
- 環境音は「🔈 声と環境音」に MP3 をドロップするとループ再生されます（例: 暖炉の音、酒場のざわめき、静かなハープ。フリー音源サイトや Suno / Udio などで作成）。未設定のときは暖炉のパチパチ音を自動合成します
- ホール右上の「🔊 声」「🎵 環境音」で ON/OFF できます

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
