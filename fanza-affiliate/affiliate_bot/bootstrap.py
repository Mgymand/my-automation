"""`python -m affiliate_bot bootstrap` — 対話型の初期設定エージェント。

方針: 「人間が手順を理解して作業する」のではなく「AI が全体を主導し、本人にしかできない瞬間だけ人間を呼ぶ」。
- 各ステップは冪等・再開可能（途中で終了しても再実行すれば続きから）
- Secret は getpass で入力し、画面・ログ・Git・LLM に出さない
- 入力直後に最小コストで疎通確認し、成功したら自動で次へ
- 最終画面は READY / ACTION REQUIRED / BLOCKED の 3 状態
- 全項目 READY のときだけ DRY_RUN=false へ移行でき、その際も「本番運用開始」の明示承認を 1 回だけ要求する
"""
from __future__ import annotations

import getpass
import importlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import requests

from . import attention, patterns, policy, tracking
from .config import BASE_DIR, Settings, load_settings
from .db import Database, utcnow
from .secrets_store import (GitHubActionsStore, GoogleSecretManagerStore, LocalEnvStore, VercelEnvStore, gitignored,
                            mask, tracked_secret_files)

READY, ACTION, BLOCKED = "READY", "ACTION REQUIRED", "BLOCKED"
HUMAN = "★ここだけ人間★"


@dataclass
class StepResult:
    status: str
    summary: str
    details: list[str] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)   # 人間がやること（必要なときだけ）


class IO:
    """入出力の抽象化（テストで差し替える）。--check では質問せず既定値を返す。"""

    def __init__(self, interactive: bool = True, answers: list[str] | None = None, secrets: list[str] | None = None,
                 out=None):
        self.interactive = interactive
        self._answers = list(answers or [])
        self._secrets = list(secrets or [])
        self.out = out or sys.stdout

    def say(self, text: str = "") -> None:
        print(text, file=self.out)

    def ask(self, prompt: str, default: str = "") -> str:
        if self._answers:
            return self._answers.pop(0)
        if not self.interactive:
            return default
        try:
            v = input(f"{prompt}{' [' + default + ']' if default else ''}: ").strip()
        except EOFError:
            return default
        return v or default

    def confirm(self, prompt: str, default: bool = False) -> bool:
        v = self.ask(prompt + (" (y/N)" if not default else " (Y/n)"), "y" if default else "n").lower()
        return v in ("y", "yes", "はい")

    def secret(self, prompt: str) -> str:
        if self._secrets:
            return self._secrets.pop(0)
        if not self.interactive:
            return ""
        try:
            return getpass.getpass(f"{prompt}（入力は表示されません）: ").strip()
        except EOFError:
            return ""


@dataclass
class Ctx:
    settings: Settings
    db: Database
    io: IO
    store: LocalEnvStore
    repo_root: Path
    project_dir: Path
    network: bool = True
    results: dict[str, StepResult] = field(default_factory=dict)

    @property
    def readonly(self) -> bool:
        """--check（非対話）では .env に一切書き込まない。"""
        return not self.io.interactive

    def reload(self) -> None:
        """環境変数から設定を読み直す（data_dir はテスト等で上書きされていることがあるため引き継ぐ）。"""
        data_dir = self.settings.data_dir
        self.settings = load_settings()
        self.settings.data_dir = data_dir

    def save_secret(self, key: str, value: str, extra_stores: list | None = None) -> list[str]:
        """ローカル .env に保存し、利用可能な外部ストアにも書く。保存先名のリストを返す。"""
        if self.readonly:
            os.environ[key] = value
            self.reload()
            return ["(check モード: 保存しない)"]
        self.store.set(key, value)
        saved = [self.store.name]
        for st in extra_stores or []:
            try:
                if st.available() and st.set(key, value):
                    saved.append(st.name)
            except Exception:  # noqa: BLE001
                pass
        self.reload()
        return saved

    def set_env(self, key: str, value: str) -> None:
        if self.readonly:
            os.environ[key] = value
        else:
            self.store.set(key, value)
        self.reload()


# ---------------------------------------------------------------- 1. 環境
def step_environment(ctx: Ctx) -> StepResult:
    d = []
    py = sys.version.split()[0]
    ok_py = sys.version_info >= (3, 11)
    d.append(f"Python {py} {'OK' if ok_py else '要 3.11 以上'} / {platform.platform()}")
    env_kind = detect_platform()
    d.append(f"実行環境: {env_kind}")
    for tool in ("git", "gcloud", "vercel", "npx", "gh", "docker"):
        d.append(f"{tool}: {'あり' if shutil.which(tool) else 'なし'}")
    try:
        r = subprocess.run(["git", "status", "--porcelain=v1", "-b"], cwd=ctx.repo_root, capture_output=True, text=True, timeout=10)
        lines = r.stdout.splitlines()
        branch = lines[0][3:] if lines else "?"
        dirty = len([x for x in lines[1:] if x.strip()])
        d.append(f"Git: {branch} / 未コミット {dirty} ファイル")
    except (OSError, subprocess.SubprocessError):
        d.append("Git: 取得不可")
    ctx.db.set_setting("env_platform", env_kind)
    return StepResult(READY if ok_py else BLOCKED, f"Python {py} / {env_kind}", d)


def detect_platform() -> str:
    e = os.environ
    if e.get("K_SERVICE"):
        return "cloud_run"
    if e.get("VERCEL"):
        return "vercel"
    if e.get("GITHUB_ACTIONS"):
        return "github_actions"
    if e.get("RENDER"):
        return "render"
    if Path("/.dockerenv").exists():
        return "docker"
    return "local"


# ---------------------------------------------------------------- 2. 依存
def step_dependencies(ctx: Ctx) -> StepResult:
    missing = []
    for mod in ("requests", "anthropic"):
        try:
            importlib.import_module(mod)
        except ImportError:
            missing.append(mod)
    if missing and ctx.io.interactive:
        ctx.io.say(f"不足パッケージ {missing} をインストールします…")
        r = subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-r", str(ctx.project_dir / "requirements.txt")],
                           capture_output=True, text=True)
        if r.returncode == 0:
            missing = [m for m in missing if not _importable(m)]
    if missing:
        return StepResult(ACTION, f"不足: {missing}", actions=[f"pip install -r {ctx.project_dir / 'requirements.txt'}"])
    return StepResult(READY, "requests / anthropic 利用可能")


def _importable(mod: str) -> bool:
    try:
        importlib.import_module(mod)
        return True
    except ImportError:
        return False


# ---------------------------------------------------------------- 3. Secret 安全性
def step_secrets_safety(ctx: Ctx) -> StepResult:
    d, actions = [], []
    rel = os.path.relpath(ctx.store.path, ctx.repo_root)
    ign = gitignored(ctx.repo_root, rel)
    d.append(f".env の gitignore: {'OK' if ign else 'NG'}")
    tracked = tracked_secret_files(ctx.repo_root)
    if tracked:
        d.append(f"Git に追跡された .env: {tracked}")
        actions.append(f"git rm --cached {' '.join(tracked)} を実行し、含まれていた Secret をすべて再発行")
    if not ctx.store.permissions_ok():
        ctx.store.harden()
        d.append(".env のパーミッションを 600 に修正")
    stores = []
    for st in (GoogleSecretManagerStore(), VercelEnvStore(ctx.project_dir / "deploy" / "vercel-tracking"), GitHubActionsStore()):
        try:
            if st.available():
                stores.append(st.name)
        except Exception:  # noqa: BLE001
            pass
    d.append("外部 Secret ストア: " + (", ".join(stores) if stores else "なし（ローカル .env のみ）"))
    ctx.db.set_setting("secret_stores", json.dumps(stores))
    if not ign:
        actions.append(f"{rel} を .gitignore に追加")
    status = BLOCKED if tracked else (ACTION if actions else READY)
    return StepResult(status, "Secret はローカル .env（600）" + (f" + {', '.join(stores)}" if stores else ""), d, actions)


# ---------------------------------------------------------------- 4. DB
def step_database(ctx: Ctx) -> StepResult:
    n = patterns.ensure_seed(ctx.db)
    attention.ensure_schema(ctx.db)
    if not ctx.db.one("SELECT 1 FROM accounts WHERE name=?", (ctx.settings.x_account_name,)):
        ctx.db.exec("INSERT INTO accounts(name,theme,target_audience,content_strategy,created_at) VALUES(?,?,?,?,?)",
                    (ctx.settings.x_account_name, "", "", "", utcnow()))
    counts = {t: ctx.db.one(f"SELECT COUNT(*) c FROM {t}")["c"] for t in ("products", "patterns", "posts")}
    return StepResult(READY, f"SQLite {ctx.settings.db_path.name}（patterns {counts['patterns']}, products {counts['products']}, posts {counts['posts']}）",
                      [f"シード追加 {n}"])


# ---------------------------------------------------------------- 5. Compliance
def step_compliance(ctx: Ctx) -> StepResult:
    d, actions = [], []
    site = ctx.settings.dmm_site
    hb = policy.x_affiliate_hard_block(site)
    if hb.blocked:
        d.append(f"DMM_SITE={site}: {hb.reason}")
        d.append("センシティブメディアとして投稿できることと、有料パートナーシップとして宣伝できることは別です。")
        if ctx.io.interactive and ctx.io.confirm("X で運用可能な DMM.com（一般商品）に切り替えますか？", default=True):
            ctx.set_env("DMM_SITE", "DMM.com")
            ctx.set_env("DMM_SERVICE", ctx.io.ask("DMM_SERVICE", "digital"))
            ctx.set_env("DMM_FLOOR", ctx.io.ask("DMM_FLOOR（例: videoa=動画, ebook=電子書籍, pcgame=PCゲーム）", "videoa"))
            d.append("DMM_SITE=DMM.com に切替")
        else:
            return StepResult(BLOCKED, "DMM_SITE=FANZA（成人向け）は X への投稿が規約上 HARD BLOCK", d,
                              ["DMM_SITE=DMM.com（一般商品）へ変更する。FANZA を X で宣伝する設定は存在しません"])
    d.append(f"X 有料パートナーシップ方針: 台帳 v{policy.POLICY_VERSION}（成人向け商品は HARD BLOCK）")
    if ctx.network:
        res = policy.verify_policy(ctx.db)
        for k, v in res.items():
            d.append(f"{k}: {v['status']}")
            if v["status"] in ("changed", "phrase_missing"):
                attention.raise_item(ctx.db, "policy_change", f"規約ページの変更を検知: {k}", detail=json.dumps(v),
                                     action="一次情報を確認し policy.py を更新", severity="critical")
                actions.append(f"{v['url']} を確認（{v['status']}）")
    d.append("広告表示: 全投稿に『【PR】』＋ API の paid_partnership ラベル（景表法ステマ規制 / DMM 規約）")
    if not ctx.settings.sensitive_media_setting_confirmed:
        d.append("X 設定『投稿するメディアをセンシティブな内容としてマーク』: 未確認（水着・グラビア等の商品を扱う場合に必要）")
        if ctx.io.interactive:
            ctx.io.say(f"{HUMAN} X → 設定とプライバシー → プライバシーと安全 → 投稿 → 『投稿するメディアをセンシティブな内容としてマーク』を ON")
            if ctx.io.confirm("ON にしましたか？（扱わない場合は n でも運用可能）"):
                ctx.set_env("SENSITIVE_MEDIA_SETTING_CONFIRMED", "true")
    status = ACTION if actions else READY
    return StepResult(status, f"DMM_SITE={ctx.settings.dmm_site} / 成人向けは HARD BLOCK / PR 表記強制", d, actions)


# ---------------------------------------------------------------- 6. Anthropic
def step_anthropic(ctx: Ctx) -> StepResult:
    from .llm import FALLBACK_CHAIN, resolve_models
    d, actions = [], []
    if not ctx.settings.anthropic_api_key:
        if not ctx.io.interactive:
            return StepResult(ACTION, "ANTHROPIC_API_KEY 未設定", actions=["bootstrap を対話モードで実行（不足する認証情報を順に案内します）"])
        ctx.io.say(f"\n{HUMAN} Anthropic API キーの発行")
        ctx.io.say("  1. https://console.anthropic.com/settings/keys を開く（ログイン）")
        ctx.io.say("  2. 『Create Key』→ 名前: affiliate-bot → Workspace: Default → Create")
        ctx.io.say("  3. 表示されたキー（sk-ant-… 一度しか表示されません）をコピーして貼り付け")
        ctx.io.say("  ※ 課金: Billing で残高（Prepaid credits）があることを確認。月の見込みは AI 合計 ¥500 前後")
        key = ctx.io.secret("ANTHROPIC_API_KEY")
        if not key:
            return StepResult(ACTION, "ANTHROPIC_API_KEY 未入力", actions=["再実行してキーを入力"])
        ctx.save_secret("ANTHROPIC_API_KEY", key, [GoogleSecretManagerStore()])
    d.append(f"ANTHROPIC_API_KEY: {mask(ctx.settings.anthropic_api_key)}")
    if not ctx.network:
        return StepResult(READY, "キー設定済み（疎通は未確認: --no-network）", d)
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=ctx.settings.anthropic_api_key)
        res = resolve_models(client, ctx.settings, ctx.db)
        for role, v in res.items():
            d.append(f"{role}: {v['requested']} → {v['resolved'] or '利用不可'}{'（代替）' if v['fallback'] else ''}")
        if any(v["resolved"] is None for v in res.values()):
            return StepResult(BLOCKED, "利用可能なモデルがありません", d, ["Anthropic Console で組織のモデルアクセスを確認"])
        # 最小コストの疎通（出力 1 トークン）
        ping_model = res["sonnet"]["resolved"]
        r = client.messages.create(model=ping_model, max_tokens=1, messages=[{"role": "user", "content": "ping"}])
        d.append(f"疎通 OK（{ping_model}, {r.usage.input_tokens} in / {r.usage.output_tokens} out）")
        ctx.db.set_setting("anthropic_verified_at", utcnow())
        fb = [r_ for r_, v in res.items() if v["fallback"]]
        return StepResult(READY, "疎通 OK" + (f" / 代替ルーティング: {fb}" if fb else ""), d)
    except Exception as e:  # noqa: BLE001
        name = e.__class__.__name__
        if "Authentication" in name or "401" in str(e):
            attention.raise_item(ctx.db, "auth_expired", "Anthropic API キーが無効", action="キーを再発行して bootstrap")
            ctx.store.set("ANTHROPIC_API_KEY", "")
            return StepResult(ACTION, f"認証失敗（{name}）", d, ["キーを再発行して bootstrap を再実行"])
        return StepResult(ACTION, f"疎通失敗（{name}）", d + [str(e)[:200]], ["ネットワーク/残高を確認して再実行"])


# ---------------------------------------------------------------- 7. DMM
DMM_AFFILIATE_ID_RE = re.compile(r"^[A-Za-z0-9_\-]+-99[0-9]$")


def step_dmm(ctx: Ctx) -> StepResult:
    from .dmm_client import DMMClient, DMMError
    d, actions = [], []
    s = ctx.settings
    if not (s.dmm_api_id and s.dmm_affiliate_id):
        if not ctx.io.interactive:
            return StepResult(ACTION, "DMM_API_ID / DMM_AFFILIATE_ID 未設定", actions=["bootstrap を対話モードで実行（不足する認証情報を順に案内します）"])
        ctx.io.say(f"\n{HUMAN} DMM アフィリエイト API の発行")
        ctx.io.say("  1. https://affiliate.dmm.com/ にログイン（アカウントがなければ『新規登録』→ 本人確認・規約同意）")
        ctx.io.say("  2. 上部メニュー『API』→ https://affiliate.dmm.com/api/ → 『API ID を発行』（利用規約に同意）")
        ctx.io.say("  3. 表示された API ID をコピー")
        ctx.io.say("  4. アフィリエイト ID は同ページの『アフィリエイト ID』欄。API 用は末尾 -990〜-999 の形式（例: yourid-990）")
        api_id = ctx.io.secret("DMM_API_ID")
        aff = ctx.io.ask("DMM_AFFILIATE_ID（例: yourid-990）")
        if not api_id or not aff:
            return StepResult(ACTION, "DMM 認証情報が未入力", actions=["再実行して入力"])
        if not DMM_AFFILIATE_ID_RE.match(aff):
            return StepResult(ACTION, f"アフィリエイト ID の形式が不正: {aff}", actions=["末尾を -990〜-999 にする（API 用 ID）"])
        ctx.save_secret("DMM_API_ID", api_id, [GoogleSecretManagerStore()])
        ctx.set_env("DMM_AFFILIATE_ID", aff)
        s = ctx.settings
    d.append(f"DMM_API_ID: {mask(s.dmm_api_id)} / DMM_AFFILIATE_ID: {s.dmm_affiliate_id}")
    if ctx.network:
        try:
            c = DMMClient(s.dmm_api_id, s.dmm_affiliate_id)
            fl = c.floor_list()
            n = sum(len(sv.get("floor", [])) for site in fl.get("site", []) for sv in site.get("service", []))
            d.append(f"疎通 OK（FloorList: {n} フロア）")
            ctx.db.set_setting("dmm_verified_at", utcnow())
        except DMMError as e:
            attention.raise_item(ctx.db, "auth_expired", "DMM API 認証失敗", detail=str(e)[:200], action="API ID を確認")
            return StepResult(ACTION, "DMM API 疎通失敗", d + [str(e)[:200]], ["API ID / アフィリエイト ID を確認して再実行"])
        except requests.RequestException as e:
            return StepResult(ACTION, f"DMM API 到達不能（{e.__class__.__name__}）", d, ["ネットワークを確認して再実行"])
    # 媒体登録
    if not s.dmm_media_registered:
        app = media_application_text(ctx)
        path = s.data_dir / "dmm_media_application.md"
        path.write_text(app, encoding="utf-8")
        d.append(f"媒体登録の申請文を生成: {path}")
        if ctx.io.interactive:
            ctx.io.say(f"\n{HUMAN} DMM アフィリエイトの媒体（サイト）登録 — 申請そのものは本人操作が必要です")
            ctx.io.say("  1. https://affiliate.dmm.com/ → 『サイト登録』（媒体管理）→ 『新規登録』")
            ctx.io.say(f"  2. 下記の申請文（{path}）を貼り付け。媒体 URL は X のプロフィール URL")
            ctx.io.say("  3. 審査申請 → 承認メールが届いたら bootstrap を再実行（続きから再開します）")
            ctx.io.say("----- 申請文 -----\n" + app + "\n------------------")
            ans = ctx.io.ask("承認済みなら『承認済み』と入力（未承認なら Enter）")
            if ans == "承認済み":
                ctx.set_env("DMM_MEDIA_REGISTERED", "true")
                attention.resolve_by_category(ctx.db, "review_needed")
                d.append("媒体登録: 承認済み")
                return StepResult(READY, "疎通 OK / 媒体登録 承認済み", d)
        attention.raise_item(ctx.db, "review_needed", "DMM 媒体登録（X アカウント）の審査申請が必要",
                             action=f"申請文 {path} を DMM 管理画面『サイト登録』へ。承認後 bootstrap 再実行", severity="warn",
                             dedupe_key="dmm_media_registration")
        return StepResult(ACTION, "疎通 OK / 媒体登録 未承認", d, ["DMM 管理画面で媒体登録を申請し、承認後に bootstrap を再実行"])
    return StepResult(READY, "疎通 OK / 媒体登録 承認済み", d)


def media_application_text(ctx: Ctx) -> str:
    """媒体登録申請の文面。LLM（Sonnet）が使えれば生成、無ければテンプレート。API キーは LLM に渡さない。"""
    s = ctx.settings
    ctx.db.exec("INSERT OR IGNORE INTO accounts(name,theme,target_audience,content_strategy,created_at) VALUES(?,?,?,?,?)",
                (s.x_account_name, "", "", "", utcnow()))
    acc = ctx.db.one("SELECT * FROM accounts WHERE name=?", (s.x_account_name,))
    handle = ctx.db.get_setting("x_username") or (ctx.io.ask("X のユーザー名（@なし）", "") if ctx.io.interactive else "")
    if handle:
        ctx.db.set_setting("x_username", handle)
    theme = (acc["theme"] if acc and acc["theme"] else "") or (ctx.io.ask("アカウントのテーマ（例: 動画レビュー・新作紹介）", "DMM 動画の新作・セール情報") if ctx.io.interactive else "DMM 商品紹介")
    ctx.db.exec("UPDATE accounts SET theme=? WHERE name=?", (theme, s.x_account_name))
    url = f"https://x.com/{handle}" if handle else "https://x.com/（ユーザー名）"
    facts = {"site": s.dmm_site, "floor": s.dmm_floor, "theme": theme, "url": url, "posts_per_day": s.posts_per_day}
    try:
        from .llm import LLMRouter, LLMUnavailable
        llm = LLMRouter(s, ctx.db)
        if llm.enabled and ctx.network:
            res = llm.call("sonnet",
                           "あなたはアフィリエイト媒体登録の申請文を書く担当者です。誇張せず、審査担当者が運営内容を理解できる具体的な文章を日本語で書きます。出力は JSON。",
                           "媒体情報: " + json.dumps(facts, ensure_ascii=False) +
                           "\n『媒体名』『媒体URL』『媒体説明(150〜250字)』『運営内容(箇条書き3〜5)』『広告掲載方法』を作成。広告表示（【PR】）と18歳未満閲覧不可の明記を含める。",
                           schema={"type": "object", "properties": {"name": {"type": "string"}, "url": {"type": "string"},
                                                                     "description": {"type": "string"},
                                                                     "operations": {"type": "array", "items": {"type": "string"}},
                                                                     "ad_method": {"type": "string"}},
                                   "required": ["name", "url", "description", "operations", "ad_method"], "additionalProperties": False},
                           max_tokens=1200, ref="media_application")
            p = res.parsed
            return (f"媒体名: {p['name']}\n媒体URL: {p['url']}\n媒体説明:\n{p['description']}\n運営内容:\n" +
                    "\n".join(f"- {o}" for o in p["operations"]) + f"\n広告掲載方法: {p['ad_method']}\n")
    except Exception:  # noqa: BLE001 - LLMUnavailable 等はテンプレートへ
        pass
    return (f"媒体名: {theme}（X アカウント @{handle or '…'}）\n媒体URL: {url}\n"
            f"媒体説明:\n{s.dmm_site} で配信されている商品（{s.dmm_floor}）を、価格・配信日・レビュー等の客観情報とともに紹介する X アカウントです。"
            f"1 日 {s.posts_per_day} 件程度、公式のサンプル画像・動画のみを使用し、全投稿に【PR】表記と 18 歳未満閲覧不可の注意を明記します。\n"
            f"運営内容:\n- 新作・セール情報の紹介\n- 公式素材のみ使用（無断転載なし）\n- 広告表示（【PR】）の徹底\n- 自動いいね・自動フォロー等は行わない\n"
            f"広告掲載方法: 投稿のリプライにアフィリエイトリンクを掲載\n")


# ---------------------------------------------------------------- 8. X
def step_x(ctx: Ctx) -> StepResult:
    from .pricing import verify_x_pricing, x_pricing
    from .x_client import XClient, XError
    d, actions = [], []
    s = ctx.settings
    if not s.x_credentials_present():
        if not ctx.io.interactive:
            return StepResult(ACTION, "X API 認証情報 未設定", actions=["bootstrap を対話モードで実行（不足する認証情報を順に案内します）"])
        cb = (s.tracking_base_url.rstrip("/") + "/callback") if s.tracking_base_url else "https://localhost/callback"
        site_url = f"https://x.com/{ctx.db.get_setting('x_username') or ''}"
        ctx.io.say(f"\n{HUMAN} X Developer の設定（所要 5 分）")
        ctx.io.say("  1. https://developer.x.com/en/portal/dashboard にログイン → 未登録なら『Sign up』（用途: Making a bot / 規約同意）")
        ctx.io.say("  2. 課金: Developer Console → Billing → クレジット購入（pay-per-use。目安 $10〜20/月）")
        ctx.io.say("  3. Projects & Apps → 既定の App → ⚙ Settings → 『User authentication settings』→ Set up")
        ctx.io.say("       App permissions: ★Read and write★ / Type of App: Web App, Automated App or Bot")
        ctx.io.say(f"       Callback URI: {cb}   Website URL: {site_url}   → Save")
        ctx.io.say("  4. 『Keys and tokens』タブ → API Key and Secret: Generate（Consumer Keys）")
        ctx.io.say("  5. 同タブ → Access Token and Secret: Generate（権限変更後に生成。『Created with Read and Write permissions』を確認）")
        ctx.io.say("  6. 4 つの値を順に貼り付け（表示されません）")
        ck = ctx.io.secret("X_CONSUMER_KEY (API Key)")
        cs = ctx.io.secret("X_CONSUMER_SECRET (API Key Secret)")
        at = ctx.io.secret("X_ACCESS_TOKEN")
        ats = ctx.io.secret("X_ACCESS_TOKEN_SECRET")
        if not all([ck, cs, at, ats]):
            return StepResult(ACTION, "X API 認証情報が未入力", actions=["再実行して 4 つの値を入力"])
        for k, v in (("X_CONSUMER_KEY", ck), ("X_CONSUMER_SECRET", cs), ("X_ACCESS_TOKEN", at), ("X_ACCESS_TOKEN_SECRET", ats)):
            ctx.save_secret(k, v, [GoogleSecretManagerStore()])
        s = ctx.settings
    d.append("X 認証情報: " + ", ".join(f"{k}={mask(getattr(s, k.lower()))}" for k in ("X_CONSUMER_KEY", "X_ACCESS_TOKEN")))
    if not ctx.network:
        return StepResult(READY, "認証情報 設定済み（疎通は未確認）", d)
    try:
        x = XClient(s.x_consumer_key, s.x_consumer_secret, s.x_access_token, s.x_access_token_secret, pricing=x_pricing(s, ctx.db))
        me = x.me().get("data") or {}
        uname, uid = me.get("username"), me.get("id")
        d.append(f"疎通 OK: @{uname} (id {uid}, フォロワー {(me.get('public_metrics') or {}).get('followers_count', '?')})")
        ctx.db.set_setting("x_username", uname or "")
        ctx.db.exec("UPDATE accounts SET x_user_id=? WHERE name=?", (uid, s.x_account_name))
        ctx.db.add_cost("x_api", x.pricing.owned_read * s.usd_jpy, ref="bootstrap:users/me")
        ctx.db.set_setting("x_verified_at", utcnow())
    except XError as e:
        if e.is_auth_or_policy:
            attention.raise_item(ctx.db, "auth_expired", f"X API 認証失敗 {e.status}", detail=e.body[:200], action="キー/トークンを再生成（Read and Write）")
            for k in ("X_CONSUMER_KEY", "X_CONSUMER_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_TOKEN_SECRET"):
                ctx.store.set(k, "")
            return StepResult(ACTION, f"X API 認証失敗（HTTP {e.status}）", d + [e.body[:200]],
                              ["Keys and tokens で Access Token を『Read and Write』で再生成し bootstrap 再実行"])
        if e.status == 402:
            attention.raise_item(ctx.db, "billing_cap", "X API クレジット不足", action="Developer Console → Billing でクレジット購入")
            return StepResult(ACTION, "X API クレジット不足（402）", d, ["クレジットを購入して再実行"])
        return StepResult(ACTION, f"X API エラー {e.status}", d + [e.body[:200]], ["再実行"])
    except requests.RequestException as e:
        return StepResult(ACTION, f"X API 到達不能（{e.__class__.__name__}）", d, ["ネットワークを確認"])
    # 価格の検証（固定値に依存しない）
    pv = verify_x_pricing(s, ctx.db)
    d.append(f"X API 価格: {pv['status']} " + json.dumps(pv["pricing"]))
    if pv["status"] == "changed":
        attention.raise_item(ctx.db, "policy_change", "X API 価格の変更を検知", detail=json.dumps(pv["changed"]),
                             action="コスト見積を確認（利益計算は新価格で継続）")
    return StepResult(READY, f"疎通 OK（@{ctx.db.get_setting('x_username')}）/ 価格 {pv['status']}", d)


# ---------------------------------------------------------------- 9. Tracking（自動構築）
def step_tracking(ctx: Ctx) -> StepResult:
    from .failsafe import check_tracking_endpoint
    d, actions = [], []
    s = ctx.settings
    if not s.tracking_secret:
        ctx.save_secret("TRACKING_SECRET", tracking.new_secret())
        s = ctx.settings
        d.append("TRACKING_SECRET を生成")
    if s.tracking_base_url:
        probs = check_tracking_endpoint(s) if ctx.network else []
        if not probs:
            return StepResult(READY, f"{s.tracking_base_url}（mode={tracking.tracking_mode(s)}）", d + ["healthz / 署名リダイレクト OK"])
        d += [m for _, m in probs]
        attention.raise_item(ctx.db, "tracking_failure", "トラッキング URL が正常に応答しない", detail="; ".join(m for _, m in probs),
                             action="bootstrap で再デプロイ")
    if ctx.db.get_setting("tracking_direct_links") == "1" and not s.tracking_base_url:
        return StepResult(READY, "直リンク運用（投稿単位クリックは X 指標から推定）", d)
    # 自動構築: Vercel（無料）→ Cloud Run（従量・ほぼ無料）→ 直リンク
    vdir = ctx.project_dir / "deploy" / "vercel-tracking"
    token = os.environ.get("VERCEL_TOKEN") or ctx.store.get("VERCEL_TOKEN")
    vstore = VercelEnvStore(vdir, token)
    if ctx.network and vstore._cli():
        if not vstore.available() and ctx.io.interactive:
            ctx.io.say(f"\n{HUMAN} Vercel（無料枠）でトラッキング用リダイレクトを自動構築します")
            ctx.io.say("  1. https://vercel.com/signup でアカウント作成（GitHub ログイン可）")
            ctx.io.say("  2. https://vercel.com/account/settings/tokens → Create → 名前: affiliate-tracking / Scope: Full / Expiration: 任意 → Create")
            ctx.io.say("  3. トークンを貼り付け（表示されません）")
            tok = ctx.io.secret("VERCEL_TOKEN")
            if tok:
                ctx.save_secret("VERCEL_TOKEN", tok)
                vstore = VercelEnvStore(vdir, tok)
        if vstore.available():
            url = deploy_vercel_tracking(ctx, vstore, d)
            if url:
                ctx.set_env("TRACKING_BASE_URL", url)
                probs = check_tracking_endpoint(ctx.settings)
                if not probs:
                    return StepResult(READY, f"{url}（Vercel, stateless）", d + ["healthz / 署名リダイレクト OK"])
                d += [m for _, m in probs]
                actions.append("Vercel のデプロイログを確認（TRACKING_SECRET の反映に数十秒かかる場合は再実行）")
    gstore = GoogleSecretManagerStore()
    if ctx.network and shutil.which("gcloud") and gstore.available():
        url = deploy_cloudrun_tracking(ctx, gstore.project, d)
        if url:
            ctx.set_env("TRACKING_BASE_URL", url)
            probs = check_tracking_endpoint(ctx.settings)
            if not probs:
                return StepResult(READY, f"{url}（Cloud Run, stateless）", d)
            d += [m for _, m in probs]
    if ctx.io.interactive:
        ctx.io.say("自動構築できる環境（Vercel トークン / gcloud 認証）がありません。")
        if ctx.io.confirm("直リンク運用（アフィリエイト URL を直接掲載。投稿単位のクリックは X の url_link_clicks から推定）で進めますか？", default=True):
            ctx.db.set_setting("tracking_direct_links", "1")
            return StepResult(READY, "直リンク運用（X 指標からクリック推定）", d)
    actions.append("Vercel トークン（vercel.com/account/settings/tokens）を用意して bootstrap 再実行、または直リンク運用を選択")
    return StepResult(ACTION, "トラッキング URL 未構築", d, actions)


def deploy_vercel_tracking(ctx: Ctx, vstore: VercelEnvStore, d: list[str]) -> str | None:
    cli = vstore._cli() or []
    base = cli + (["--token", vstore.token] if vstore.token else []) + ["--cwd", str(vstore.project_dir), "--yes"]
    try:
        vstore.set("TRACKING_SECRET", ctx.settings.tracking_secret)
        r = subprocess.run(base + ["--prod", "--name", "affiliate-tracking"], capture_output=True, text=True, timeout=600)
        out = r.stdout + r.stderr
        m = re.findall(r"https://[a-z0-9\-]+\.vercel\.app", out)
        if r.returncode != 0 or not m:
            d.append("Vercel デプロイ失敗: " + out[-300:].replace(vstore.token or "\x00", "***"))
            return None
        url = sorted(set(m), key=len)[0]
        # 本番エイリアス（affiliate-tracking-<team>.vercel.app 等）が別に出る場合はそれを優先
        alias = [u for u in set(m) if "affiliate-tracking" in u and not re.search(r"-[a-z0-9]{9}-", u)]
        url = alias[0] if alias else url
        d.append(f"Vercel デプロイ OK: {url}")
        ctx.db.set_setting("tracking_deploy", json.dumps({"provider": "vercel", "url": url, "at": utcnow()}))
        return url
    except (OSError, subprocess.SubprocessError) as e:
        d.append(f"Vercel デプロイ例外: {e.__class__.__name__}")
        return None


def deploy_cloudrun_tracking(ctx: Ctx, project: str, d: list[str]) -> str | None:
    region = os.environ.get("REGION", "asia-northeast1")
    try:
        GoogleSecretManagerStore(project).set("TRACKING_SECRET", ctx.settings.tracking_secret)
        cmd = ["gcloud", "run", "deploy", "affiliate-tracking", "--project", project, "--region", region,
               "--source", str(ctx.project_dir), "--allow-unauthenticated", "--max-instances", "1", "--memory", "256Mi",
               "--command", "python", "--args", "-m,affiliate_bot,serve-tracking",
               "--set-secrets", "TRACKING_SECRET=TRACKING_SECRET:latest", "--set-env-vars", "DATA_DIR=/tmp", "--quiet"]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
        if r.returncode != 0:
            d.append("Cloud Run デプロイ失敗: " + (r.stderr or r.stdout)[-300:])
            return None
        r2 = subprocess.run(["gcloud", "run", "services", "describe", "affiliate-tracking", "--project", project, "--region", region,
                             "--format", "value(status.url)"], capture_output=True, text=True, timeout=120)
        url = r2.stdout.strip()
        if url:
            d.append(f"Cloud Run デプロイ OK: {url}")
            ctx.db.set_setting("tracking_deploy", json.dumps({"provider": "cloud_run", "url": url, "at": utcnow()}))
        return url or None
    except (OSError, subprocess.SubprocessError) as e:
        d.append(f"Cloud Run デプロイ例外: {e.__class__.__name__}")
        return None


# ---------------------------------------------------------------- 10. Deployment（bot 本体）
def step_deployment(ctx: Ctx) -> StepResult:
    d, actions = [], []
    plat = ctx.db.get_setting("env_platform", "local")
    dep = ctx.db.get_setting("bot_deploy")
    if plat == "cloud_run":
        return StepResult(READY, "Cloud Run 上で稼働中（loop）", d)
    if dep:
        info = json.loads(dep)
        return StepResult(READY, f"{info.get('provider')}: {info.get('detail')}", d)
    gstore = GoogleSecretManagerStore()
    if ctx.network and shutil.which("gcloud") and gstore.available() and ctx.io.interactive:
        if ctx.io.confirm(f"Cloud Run（プロジェクト {gstore.project}）に常駐サービス（loop）をデプロイしますか？ 目安 ¥1,000〜1,500/月", default=True):
            url = deploy_cloudrun_bot(ctx, gstore.project, d)
            if url:
                ctx.db.set_setting("bot_deploy", json.dumps({"provider": "cloud_run", "detail": url, "at": utcnow()}))
                return StepResult(READY, f"Cloud Run: {url}", d)
    # ローカル / VPS: 常駐コマンドを用意し、本人が起動したことを確認する
    unit = ctx.settings.data_dir / "affiliate-bot.service"
    unit.write_text(
        "[Unit]\nDescription=affiliate-bot loop\nAfter=network-online.target\n\n[Service]\n"
        f"WorkingDirectory={ctx.project_dir}\nExecStart={sys.executable} -m affiliate_bot loop\nRestart=always\nRestartSec=30\n"
        f"EnvironmentFile={ctx.store.path}\n\n[Install]\nWantedBy=multi-user.target\n", encoding="utf-8")
    d.append(f"systemd ユニットを生成: {unit}")
    cmd = f"cd {ctx.project_dir} && nohup {sys.executable} -m affiliate_bot loop >> {ctx.settings.data_dir}/loop.log 2>&1 &"
    d.append(f"常駐コマンド: {cmd}")
    if ctx.io.interactive:
        ctx.io.say("bot 本体の常駐先: このマシン（または VPS）で loop を動かします。")
        ctx.io.say(f"  systemd: sudo cp {unit} /etc/systemd/system/ && sudo systemctl enable --now affiliate-bot")
        ctx.io.say(f"  簡易:    {cmd}")
        if ctx.io.confirm("loop を常駐させましたか？（後で行う場合は n）"):
            ctx.db.set_setting("bot_deploy", json.dumps({"provider": "local_loop", "detail": "systemd/nohup", "at": utcnow()}))
            return StepResult(READY, "ローカル/VPS で loop 常駐", d)
    actions.append("loop を常駐させる（systemd か nohup）か、gcloud 認証後に bootstrap で Cloud Run へ自動デプロイ")
    return StepResult(ACTION, "bot 本体の常駐先が未確定", d, actions)


def deploy_cloudrun_bot(ctx: Ctx, project: str, d: list[str]) -> str | None:
    region = os.environ.get("REGION", "asia-northeast1")
    bucket = f"{project}-affiliate-data"
    secrets_map = ",".join(f"{k}={k}:latest" for k in ("DMM_API_ID", "X_CONSUMER_KEY", "X_CONSUMER_SECRET", "X_ACCESS_TOKEN",
                                                       "X_ACCESS_TOKEN_SECRET", "ANTHROPIC_API_KEY", "TRACKING_SECRET"))
    envs = ",".join(f"{k}={getattr(ctx.settings, k.lower())}" for k in ("DMM_AFFILIATE_ID", "DMM_SITE", "DMM_SERVICE", "DMM_FLOOR",
                                                                     "TRACKING_BASE_URL", "POSTS_PER_DAY", "X_ACCOUNT_NAME")) + ",DATA_DIR=/var/data,DRY_RUN=true"
    try:
        subprocess.run(["gcloud", "storage", "buckets", "create", f"gs://{bucket}", "--project", project, "--location", region,
                        "--uniform-bucket-level-access"], capture_output=True, text=True, timeout=120)
        r = subprocess.run(["gcloud", "run", "deploy", "affiliate-bot", "--project", project, "--region", region,
                            "--source", str(ctx.project_dir), "--no-allow-unauthenticated", "--min-instances", "1", "--max-instances", "1",
                            "--memory", "512Mi", "--no-cpu-throttling", "--add-volume", f"name=data,type=cloud-storage,bucket={bucket}",
                            "--add-volume-mount", "volume=data,mount-path=/var/data", "--set-secrets", secrets_map,
                            "--set-env-vars", envs, "--quiet"], capture_output=True, text=True, timeout=900)
        if r.returncode != 0:
            d.append("Cloud Run デプロイ失敗: " + (r.stderr or r.stdout)[-300:])
            return None
        r2 = subprocess.run(["gcloud", "run", "services", "describe", "affiliate-bot", "--project", project, "--region", region,
                             "--format", "value(status.url)"], capture_output=True, text=True, timeout=120)
        d.append("注: Cloud Run 上の DRY_RUN は本番承認後に `gcloud run services update affiliate-bot --update-env-vars DRY_RUN=false`")
        return r2.stdout.strip() or "deployed"
    except (OSError, subprocess.SubprocessError) as e:
        d.append(f"Cloud Run デプロイ例外: {e.__class__.__name__}")
        return None


# ---------------------------------------------------------------- 11. DRY_RUN / 本番運用開始
BOARD_KEYS = [("dmm", "DMM API"), ("x", "X API"), ("anthropic", "Anthropic"), ("tracking", "Tracking"),
              ("database", "Database"), ("deployment", "Deployment"), ("compliance", "Compliance")]


def step_go_live(ctx: Ctx) -> StepResult:
    s = ctx.settings
    approved = ctx.db.get_setting("go_live_approved_at")
    all_ready = all(ctx.results.get(k, StepResult(BLOCKED, "")).status == READY for k, _ in BOARD_KEYS)
    if not s.dry_run and approved:
        return StepResult(READY, f"本番運用中（承認 {approved}）")
    if not s.dry_run and not approved:
        ctx.set_env("DRY_RUN", "true")
        return StepResult(ACTION, "DRY_RUN=false だが本番承認が未記録のため DRY_RUN=true に戻しました", actions=["bootstrap で『本番運用開始』を承認"])
    if not all_ready:
        pending = [label for k, label in BOARD_KEYS if ctx.results.get(k, StepResult(BLOCKED, "")).status != READY]
        return StepResult(ACTION, f"DRY_RUN=true（{', '.join(pending)} が未完了のため本番移行不可）")
    if not ctx.io.interactive:
        return StepResult(ACTION, "DRY_RUN=true。全項目 READY。本番移行は対話モードで『本番運用開始』を入力")
    ctx.io.say(f"\n{HUMAN} すべて READY です。本番投稿を開始するには『本番運用開始』と入力してください（1 回だけ。以後の日次運用に人間確認は不要）")
    ctx.io.say("  ※ 本番では X API 料金（投稿 + リンクリプ）と AI 費が発生します。日次レポートは data/../reports/ に出力され、要対応時のみ通知します")
    ans = ctx.io.ask("入力")
    if ans.strip() == "本番運用開始":
        ctx.db.set_setting("go_live_approved_at", utcnow())
        ctx.db.set_setting("go_live_approved_by", os.environ.get("USER", "operator"))
        ctx.set_env("DRY_RUN", "false")
        ctx.db.log_event("info", "go_live", "本番運用開始を承認")
        return StepResult(READY, f"本番運用開始（承認 {utcnow()}）")
    return StepResult(ACTION, "DRY_RUN=true（本番承認は保留）")


# ---------------------------------------------------------------- 実行
STEPS = [
    ("environment", "環境", step_environment),
    ("dependencies", "依存パッケージ", step_dependencies),
    ("secrets", "Secret 保存", step_secrets_safety),
    ("database", "データベース", step_database),
    ("compliance", "コンプライアンス", step_compliance),
    ("anthropic", "Anthropic", step_anthropic),
    ("dmm", "DMM", step_dmm),
    ("x", "X", step_x),
    ("tracking", "トラッキング", step_tracking),
    ("deployment", "デプロイ", step_deployment),
    ("go_live", "DRY_RUN / 本番", step_go_live),
]


def run(settings: Settings, db: Database, io: IO, network: bool = True, only: list[str] | None = None) -> dict[str, StepResult]:
    ctx = Ctx(settings=settings, db=db, io=io, store=LocalEnvStore(BASE_DIR / ".env"), repo_root=BASE_DIR.parent,
              project_dir=BASE_DIR, network=network)
    prev = json.loads(db.get_setting("bootstrap_state", "{}") or "{}")
    io.say("=" * 64)
    io.say(" affiliate-bot bootstrap — AI 主導の初期設定（人間は認証・同意・課金・審査のみ）")
    io.say("=" * 64)
    for key, title, fn in STEPS:
        if only and key not in only:
            if key in prev:
                ctx.results[key] = StepResult(prev[key]["status"], prev[key]["summary"])
            continue
        io.say(f"\n▶ {title}")
        try:
            res = fn(ctx)
        except KeyboardInterrupt:
            io.say("中断しました。再実行すると続きから再開します。")
            break
        except Exception as e:  # noqa: BLE001 - 1 ステップの例外で全体を止めない
            res = StepResult(ACTION, f"エラー: {e.__class__.__name__}: {str(e)[:120]}", actions=["再実行。解決しない場合は events を確認"])
            db.log_event("warn", "bootstrap_error", f"{key}: {e}")
        ctx.results[key] = res
        for line in res.details:
            io.say(f"   - {line}")
        io.say(f"   → {res.status}: {res.summary}")
        for a in res.actions:
            io.say(f"   {HUMAN} {a}")
        prev[key] = {"status": res.status, "summary": res.summary, "ts": utcnow()}
        db.set_setting("bootstrap_state", json.dumps(prev, ensure_ascii=False))
        if res.status == BLOCKED and key in ("environment", "secrets", "compliance"):
            io.say("   ※ この項目が解決するまで以降のステップは意味がないため中断します")
            break
    io.say("\n" + render_board(ctx.results, ctx.settings, db))
    attention.notify_pending(db, ctx.settings)
    return ctx.results


def _w(s: str) -> int:
    import unicodedata
    return sum(2 if unicodedata.east_asian_width(c) in ("W", "F") else 1 for c in s)


def _pad(s: str, width: int) -> str:
    while _w(s) > width:
        s = s[:-1]
    return s + " " * (width - _w(s))


def render_board(results: dict[str, StepResult], settings: Settings, db: Database) -> str:
    def st(k):
        return results.get(k, StepResult(ACTION, "未実行")).status

    overall = READY
    if any(st(k) == BLOCKED for k, _ in BOARD_KEYS):
        overall = BLOCKED
    elif any(st(k) != READY for k, _ in BOARD_KEYS) or st("go_live") != READY:
        overall = ACTION
    lines = ["┌" + "─" * 76 + "┐", "│ " + _pad(f"総合判定: {overall}", 75) + "│", "├" + "─" * 76 + "┤"]
    for k, label in BOARD_KEYS:
        r = results.get(k, StepResult(ACTION, "未実行"))
        lines.append("│ " + _pad(label, 12) + " " + _pad(r.status, 16) + " " + _pad(r.summary, 45) + "│")
    go = results.get("go_live", StepResult(ACTION, "未実行"))
    dr = "false（本番）" if not settings.dry_run else "true（ドライラン）"
    lines.append("│ " + _pad("DRY_RUN", 12) + " " + _pad(go.status, 16) + " " + _pad(dr, 45) + "│")
    lines.append("└" + "─" * 76 + "┘")
    items = attention.open_items(db)
    if items:
        lines.append("要対応（Human Attention Queue）:")
        for it in items:
            lines.append(f"  #{it['id']} [{it['category']}] {it['title']}" + (f" → {it['action']}" if it["action"] else ""))
    acts = list(dict.fromkeys(a for k, _ in BOARD_KEYS + [("go_live", "")] for a in results.get(k, StepResult(READY, "")).actions))
    if acts:
        lines.append("次に人間がやること:")
        lines += [f"  {HUMAN} {a}" for a in acts]
    else:
        lines.append("人間の作業: なし")
    return "\n".join(lines)
