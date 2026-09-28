"""`python -m affiliate_bot bootstrap` — 対話型の初期設定エージェント（Phase 3: 手動投稿アシスト）。

人間にしかできない瞬間（ログイン・規約同意・課金・キーのコピー・審査申請）だけ `★ここだけ人間★` と表示する。
設定するもの: DMM API（FloorList 疎通）/ DMM 媒体登録（申請文を生成）/ X READ（Bearer, 投稿権限不要）/ Anthropic（モデル可用性）/ 常駐。
X の書込権限や自動投稿の設定項目は存在しない。Secret は getpass で入力し画面・ログ・Git・LLM に出さない。
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
from pathlib import Path

import requests

from . import attention, patterns, policy
from .config import BASE_DIR, Settings, load_settings
from .db import Database, utcnow
from .secrets_store import GitHubActionsStore, GoogleSecretManagerStore, LocalEnvStore, gitignored, mask, tracked_secret_files

READY, ACTION, BLOCKED = "READY", "ACTION REQUIRED", "BLOCKED"
HUMAN = "★ここだけ人間★"
DMM_AFFILIATE_ID_RE = re.compile(r"^[A-Za-z0-9_\-]+-99[0-9]$")


@dataclass
class StepResult:
    status: str
    summary: str
    details: list[str] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)


class IO:
    def __init__(self, interactive: bool = True, answers: list[str] | None = None, secrets: list[str] | None = None, out=None):
        self.interactive, self._answers, self._secrets, self.out = interactive, list(answers or []), list(secrets or []), out or sys.stdout

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
        return self.ask(prompt + (" (Y/n)" if default else " (y/N)"), "y" if default else "n").lower() in ("y", "yes", "はい")

    def secret(self, prompt: str) -> str:
        if self._secrets:
            return self._secrets.pop(0)
        if not self.interactive:
            return ""
        try:
            return getpass.getpass(f"{prompt}（入力は表示されません）: ").strip()
        except EOFError:
            return ""


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
        return not self.io.interactive

    @property
    def platform(self) -> str:
        return self.db.get_setting("env_platform") or detect_platform()

    @property
    def local_env_allowed(self) -> bool:
        return self.platform in ("local", "docker")

    def reload(self) -> None:
        data_dir = self.settings.data_dir
        self.settings = load_settings()
        self.settings.data_dir = data_dir

    def save_secret(self, key: str, value: str, extra_stores: list | None = None) -> list[str]:
        if self.readonly:
            os.environ[key] = value
            self.reload()
            return ["(check モード: 保存しない)"]
        saved: list[str] = []
        for st in extra_stores or []:
            try:
                if st.available() and st.set(key, value):
                    saved.append(st.name)
            except Exception:  # noqa: BLE001
                pass
        if self.local_env_allowed:
            self.store.set(key, value)
            saved.insert(0, self.store.name)
        else:
            os.environ[key] = value
            if not saved:
                self.db.log_event("warn", "secret_not_persisted", f"{key}: クラウド実行のため .env には保存しません。外部 Secret ストアが利用できず永続化できていません")
        self.reload()
        return saved

    def set_env(self, key: str, value: str) -> None:
        if self.readonly or not self.local_env_allowed:
            os.environ[key] = value
        else:
            self.store.set(key, value)
        self.reload()


# ---------------------------------------------------------------- steps
def step_environment(ctx: Ctx) -> StepResult:
    d = [f"Python {sys.version.split()[0]} / {platform.platform()}", f"実行環境: {detect_platform()}"]
    d += [f"{t}: {'あり' if shutil.which(t) else 'なし'}" for t in ("git", "gcloud", "gh")]
    try:
        r = subprocess.run(["git", "status", "--porcelain=v1", "-b"], cwd=ctx.repo_root, capture_output=True, text=True, timeout=10)
        lines = r.stdout.splitlines()
        d.append(f"Git: {lines[0][3:] if lines else '?'} / 未コミット {len([x for x in lines[1:] if x.strip()])} ファイル")
    except (OSError, subprocess.SubprocessError):
        d.append("Git: 取得不可")
    ctx.db.set_setting("env_platform", detect_platform())
    ok = sys.version_info >= (3, 11)
    return StepResult(READY if ok else BLOCKED, f"Python {sys.version.split()[0]} / {detect_platform()}", d)


def _importable(mod: str) -> bool:
    try:
        importlib.import_module(mod)
        return True
    except ImportError:
        return False


def step_dependencies(ctx: Ctx) -> StepResult:
    missing = [m for m in ("requests", "anthropic") if not _importable(m)]
    if missing and ctx.io.interactive:
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-r", str(ctx.project_dir / "requirements.txt")], capture_output=True, text=True)
        missing = [m for m in missing if not _importable(m)]
    return StepResult(ACTION if missing else READY, f"不足: {missing}" if missing else "requests / anthropic 利用可能",
                      actions=[f"pip install -r {ctx.project_dir / 'requirements.txt'}"] if missing else [])


def step_secrets_safety(ctx: Ctx) -> StepResult:
    d, actions = [], []
    rel = os.path.relpath(ctx.store.path, ctx.repo_root)
    ign = gitignored(ctx.repo_root, rel)
    d.append(f".env の gitignore: {'OK' if ign else 'NG'}")
    tracked = tracked_secret_files(ctx.repo_root)
    if tracked:
        actions.append(f"git rm --cached {' '.join(tracked)} を実行し、含まれていた Secret をすべて再発行")
    if not ctx.store.permissions_ok():
        ctx.store.harden()
    stores = [st.name for st in (GoogleSecretManagerStore(), GitHubActionsStore()) if _safe_available(st)]
    d.append("外部 Secret ストア: " + (", ".join(stores) if stores else "なし"))
    if not ign:
        actions.append(f"{rel} を .gitignore に追加")
    primary = ("ローカル .env（600）" + (f" + 複製: {', '.join(stores)}" if stores else "")) if ctx.local_env_allowed else (
        f"{stores[0]}（クラウド実行のため .env には書かない）" if stores else "なし（クラウド実行で外部ストアが利用不可）")
    if not ctx.local_env_allowed and not stores:
        actions.append("Secret Manager か GitHub Actions Secrets を利用可能にする（gcloud / gh の認証）")
    return StepResult(BLOCKED if tracked else (ACTION if actions else READY), f"Secret の保存先: {primary}", d, actions)


def _safe_available(st) -> bool:
    try:
        return st.available()
    except Exception:  # noqa: BLE001
        return False


def step_database(ctx: Ctx) -> StepResult:
    n = patterns.ensure_seed(ctx.db)
    attention.ensure_schema(ctx.db)
    ctx.db.exec("INSERT OR IGNORE INTO accounts(name,theme,target_audience,content_strategy,created_at) VALUES(?,?,?,?,?)",
                (ctx.settings.x_account_name, "", "", "", utcnow()))
    c = {t: ctx.db.one(f"SELECT COUNT(*) c FROM {t}")["c"] for t in ("products", "patterns", "posts", "research_posts")}
    return StepResult(READY, f"SQLite（patterns {c['patterns']}, products {c['products']}, posts {c['posts']}, research {c['research_posts']}）", [f"シード追加 {n}"])


def step_compliance(ctx: Ctx) -> StepResult:
    d, actions = [], []
    d.append("X への投稿は人間が行う。システムは投稿権限を持たない（x_client は READ ONLY、publisher は存在しない）")
    d.append(f"成人向け商品の X 自動投稿: HARD BLOCK（policy v{policy.POLICY_VERSION}）。人間投稿の注意を全パッケージに添付")
    d.append("素材: DMM 公式素材のみ（他者投稿からの転載禁止）。本文に【PR】必須。NG ワード辞書で未成年・非同意想起表現を排除")
    if ctx.network:
        for k, v in policy.verify_policy(ctx.db).items():
            d.append(f"{k}: {v['status']}" + (f"（source={v['source']}。proxy は参考のみ）" if v.get("source") == "proxy" else ""))
            if v["status"] in ("changed", "phrase_missing"):
                attention.raise_item(ctx.db, "policy_change", f"規約ページの変更を検知: {k}", detail=json.dumps(v), action="一次情報を確認し policy.py を更新", severity="critical")
                actions.append(f"{v['url']} を確認（{v['status']}）")
    return StepResult(ACTION if actions else READY, "READ ONLY / HARD BLOCK 維持 / PR 表記強制", d, actions)


def step_anthropic(ctx: Ctx) -> StepResult:
    from .llm import resolve_models
    d = []
    if not ctx.settings.anthropic_api_key:
        if not ctx.io.interactive:
            return StepResult(ACTION, "ANTHROPIC_API_KEY 未設定", actions=["bootstrap を対話モードで実行（不足する認証情報を順に案内します）"])
        ctx.io.say(f"\n{HUMAN} Anthropic API キーの発行")
        ctx.io.say("  1. https://console.anthropic.com/settings/keys （ログイン）→ 『Create Key』→ 名前: affiliate-bot → Create")
        ctx.io.say("  2. 表示されたキー（sk-ant-…）をコピーして貼り付け。Billing で残高を確認（AI 費の目安 ¥500/月前後）")
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
        r = client.messages.create(model=res["sonnet"]["resolved"], max_tokens=1, messages=[{"role": "user", "content": "ping"}])
        d.append(f"疎通 OK（{res['sonnet']['resolved']}, {r.usage.input_tokens} in / {r.usage.output_tokens} out）")
        ctx.db.set_setting("anthropic_verified_at", utcnow())
        fb = [k for k, v in res.items() if v["fallback"]]
        return StepResult(READY, "疎通 OK" + (f" / 代替ルーティング: {fb}" if fb else ""), d)
    except Exception as e:  # noqa: BLE001
        name = e.__class__.__name__
        if "Authentication" in name or "401" in str(e):
            ctx.store.set("ANTHROPIC_API_KEY", "")
            return StepResult(ACTION, f"認証失敗（{name}）", d, ["キーを再発行して bootstrap を再実行"])
        return StepResult(ACTION, f"疎通失敗（{name}）", d + [str(e)[:200]], ["ネットワーク/残高を確認して再実行"])


def step_dmm(ctx: Ctx) -> StepResult:
    from .dmm_client import DMMClient, DMMError
    d = []
    s = ctx.settings
    if not (s.dmm_api_id and s.dmm_affiliate_id):
        if not ctx.io.interactive:
            return StepResult(ACTION, "DMM_API_ID / DMM_AFFILIATE_ID 未設定", actions=["bootstrap を対話モードで実行（不足する認証情報を順に案内します）"])
        ctx.io.say(f"\n{HUMAN} DMM アフィリエイト API の発行")
        ctx.io.say("  1. https://affiliate.dmm.com/ にログイン（未登録なら新規登録 → 本人確認・規約同意）")
        ctx.io.say("  2. 上部メニュー『API』→ https://affiliate.dmm.com/api/ → 『API ID を発行』（利用規約に同意）→ API ID をコピー")
        ctx.io.say("  3. アフィリエイト ID は同ページの表示。API 用は末尾 -990〜-999（例: yourid-990）")
        api_id = ctx.io.secret("DMM_API_ID")
        aff = ctx.io.ask("DMM_AFFILIATE_ID（例: yourid-990）")
        if not api_id or not aff:
            return StepResult(ACTION, "DMM 認証情報が未入力", actions=["再実行して入力"])
        if not DMM_AFFILIATE_ID_RE.match(aff):
            return StepResult(ACTION, f"アフィリエイト ID の形式が不正: {aff}", actions=["末尾を -990〜-999 にする（API 用 ID）"])
        ctx.save_secret("DMM_API_ID", api_id, [GoogleSecretManagerStore()])
        ctx.set_env("DMM_AFFILIATE_ID", aff)
        s = ctx.settings
    d.append(f"DMM_API_ID: {mask(s.dmm_api_id)} / DMM_AFFILIATE_ID: {s.dmm_affiliate_id} / site={s.dmm_site} floor={s.dmm_floor}")
    if ctx.network:
        try:
            fl = DMMClient(s.dmm_api_id, s.dmm_affiliate_id).floor_list()
            n = sum(len(sv.get("floor", [])) for site in fl.get("site", []) for sv in site.get("service", []))
            d.append(f"疎通 OK（FloorList: {n} フロア）")
            ctx.db.set_setting("dmm_verified_at", utcnow())
            attention.resolve_by_category(ctx.db, "fanza_auth")
        except DMMError as e:
            attention.raise_item(ctx.db, "fanza_auth", "FANZA API 認証失敗", detail=str(e)[:200], action="API ID を確認して bootstrap")
            return StepResult(ACTION, "DMM API 疎通失敗", d + [str(e)[:200]], ["API ID / アフィリエイト ID を確認して再実行"])
        except requests.RequestException as e:
            return StepResult(ACTION, f"DMM API 到達不能（{e.__class__.__name__}）", d, ["ネットワークを確認して再実行"])
    if not s.dmm_media_registered:
        app = media_application_text(ctx)
        path = s.data_dir / "dmm_media_application.md"
        path.write_text(app, encoding="utf-8")
        d.append(f"媒体登録の申請文を生成: {path}")
        if ctx.io.interactive:
            ctx.io.say(f"\n{HUMAN} DMM アフィリエイトの媒体（サイト）登録 — 申請そのものは本人操作")
            ctx.io.say("  1. https://affiliate.dmm.com/ → 『サイト登録』→ 『新規登録』。媒体 URL は X のプロフィール URL")
            ctx.io.say(f"  2. 下記の申請文（{path}）を貼り付け → 審査申請 → 承認後に bootstrap を再実行")
            ctx.io.say("----- 申請文 -----\n" + app + "\n------------------")
            if ctx.io.ask("承認済みなら『承認済み』と入力（未承認なら Enter）") == "承認済み":
                ctx.set_env("DMM_MEDIA_REGISTERED", "true")
                return StepResult(READY, "疎通 OK / 媒体登録 承認済み", d)
        return StepResult(ACTION, "疎通 OK / 媒体登録 未承認（パッケージ生成は可能。成果計上には承認が必要）", d,
                          ["DMM 管理画面で媒体登録を申請し、承認後に bootstrap を再実行"])
    return StepResult(READY, "疎通 OK / 媒体登録 承認済み", d)


def media_application_text(ctx: Ctx) -> str:
    s = ctx.settings
    ctx.db.exec("INSERT OR IGNORE INTO accounts(name,theme,target_audience,content_strategy,created_at) VALUES(?,?,?,?,?)", (s.x_account_name, "", "", "", utcnow()))
    acc = ctx.db.one("SELECT * FROM accounts WHERE name=?", (s.x_account_name,))
    handle = s.x_username or ctx.db.get_setting("x_username") or (ctx.io.ask("X のユーザー名（@なし）", "") if ctx.io.interactive else "")
    if handle:
        ctx.db.set_setting("x_username", handle)
    theme = (acc["theme"] if acc and acc["theme"] else "") or (ctx.io.ask("アカウントのテーマ（例: 新作・セール紹介）", "FANZA 動画の新作・セール情報") if ctx.io.interactive else "FANZA 作品紹介")
    ctx.db.exec("UPDATE accounts SET theme=? WHERE name=?", (theme, s.x_account_name))
    url = f"https://x.com/{handle}" if handle else "https://x.com/（ユーザー名）"
    facts = {"site": s.dmm_site, "floor": s.dmm_floor, "theme": theme, "url": url, "posts_per_day": s.posts_per_day}
    try:
        from .llm import LLMRouter
        llm = LLMRouter(s, ctx.db)
        if llm.enabled and ctx.network:
            res = llm.call("sonnet", "あなたはアフィリエイト媒体登録の申請文を書く担当者です。誇張せず、審査担当者が運営内容を理解できる具体的な文章を日本語で書きます。出力は JSON。",
                           "媒体情報: " + json.dumps(facts, ensure_ascii=False) + "\n『媒体名』『媒体URL』『媒体説明(150〜250字)』『運営内容(箇条書き3〜5)』『広告掲載方法』を作成。【PR】表記と 18 歳未満閲覧不可の明記を含める。",
                           schema={"type": "object", "properties": {"name": {"type": "string"}, "url": {"type": "string"}, "description": {"type": "string"},
                                                                     "operations": {"type": "array", "items": {"type": "string"}}, "ad_method": {"type": "string"}},
                                   "required": ["name", "url", "description", "operations", "ad_method"], "additionalProperties": False},
                           max_tokens=1200, ref="media_application")
            p = res.parsed
            return (f"媒体名: {p['name']}\n媒体URL: {p['url']}\n媒体説明:\n{p['description']}\n運営内容:\n" + "\n".join(f"- {o}" for o in p["operations"]) + f"\n広告掲載方法: {p['ad_method']}\n")
    except Exception:  # noqa: BLE001
        pass
    return (f"媒体名: {theme}（X アカウント @{handle or '…'}）\n媒体URL: {url}\n媒体説明:\n{s.dmm_site} で配信されている作品（{s.dmm_floor}）を、価格・配信日・レビュー等の客観情報とともに紹介する X アカウントです。"
            f"1 日 {s.posts_per_day} 件程度、投稿は運営者本人が手動で行い、公式のサンプル画像・動画のみを使用し、全投稿に【PR】表記と 18 歳未満閲覧不可の注意を明記します。\n"
            f"運営内容:\n- 新作・セール情報の紹介\n- 公式素材のみ使用（無断転載なし）\n- 広告表示（【PR】）の徹底\n- 自動投稿・自動いいね・自動フォローは行わない\n広告掲載方法: 投稿のリプライにアフィリエイトリンクを掲載\n")


def step_x_read(ctx: Ctx) -> StepResult:
    from .pricing import verify_x_pricing, x_pricing
    from .x_client import XError, XReadClient
    d = []
    s = ctx.settings
    if not s.x_bearer_token:
        if not ctx.io.interactive:
            return StepResult(ACTION, "X_BEARER_TOKEN 未設定（任意: なくても plan は動く。指標は手入力）",
                              actions=["bootstrap を対話モードで実行（不足する認証情報を順に案内します）"])
        ctx.io.say(f"\n{HUMAN} X Developer（READ ONLY。投稿権限は不要）")
        ctx.io.say("  1. https://developer.x.com/en/portal/dashboard にログイン → 未登録なら Sign up（規約同意）")
        ctx.io.say("  2. Developer Console → Billing → クレジット購入（読取のみ: 目安 $3〜10/月）")
        ctx.io.say("  3. Projects & Apps → App → 『Keys and tokens』→ Bearer Token: Generate → コピー")
        ctx.io.say("     ※ App permissions は Read のままで OK。OAuth 1.0a の Access Token は不要")
        ctx.io.say("  4. 自分の X ユーザー名（@なし）も入力（自分の投稿の指標取得・調査に使用）")
        tok = ctx.io.secret("X_BEARER_TOKEN")
        if not tok:
            if ctx.io.confirm("X 読取なしで進めますか？（指標は CSV / 手入力、調査は CSV 取込）", default=True):
                ctx.db.set_setting("x_read_optional", "1")
                return StepResult(READY, "X 読取なし（指標・調査は CSV / 手入力）", d)
            return StepResult(ACTION, "X_BEARER_TOKEN 未入力", actions=["再実行して入力"])
        ctx.save_secret("X_BEARER_TOKEN", tok, [GoogleSecretManagerStore()])
        uname = ctx.io.ask("X_USERNAME（@なし）", s.x_username)
        if uname:
            ctx.set_env("X_USERNAME", uname)
        s = ctx.settings
    d.append(f"X_BEARER_TOKEN: {mask(s.x_bearer_token)} / X_USERNAME: {s.x_username or '-'}")
    if not ctx.network:
        return StepResult(READY, "トークン設定済み（疎通は未確認）", d)
    try:
        x = XReadClient(s.x_bearer_token, pricing=x_pricing(s, ctx.db))
        if s.x_username:
            me = x.user_by_username(s.x_username)
            d.append(f"疎通 OK: @{me.get('username')} (id {me.get('id')}, フォロワー {(me.get('public_metrics') or {}).get('followers_count', '?')})")
            ctx.db.exec("UPDATE accounts SET x_user_id=?, x_username=?, followers=? WHERE name=?",
                        (me.get("id"), me.get("username"), (me.get("public_metrics") or {}).get("followers_count"), s.x_account_name))
            ctx.db.add_cost("x_api", x.pricing.read_user * s.usd_jpy, ref="bootstrap:user")
        else:
            posts, cost = x.search_recent("FANZA -is:retweet lang:ja", max_results=10)
            d.append(f"疎通 OK: 検索 {len(posts)} 件")
            ctx.db.add_cost("x_api", cost * s.usd_jpy, ref="bootstrap:search")
        ctx.db.set_setting("x_verified_at", utcnow())
        attention.resolve_by_category(ctx.db, "x_read_auth")
    except XError as e:
        if e.is_auth:
            attention.raise_item(ctx.db, "x_read_auth", f"X READ API 認証失敗 {e.status}", detail=e.body[:200], action="Bearer Token を再生成")
            ctx.store.set("X_BEARER_TOKEN", "")
            return StepResult(ACTION, f"X API 認証失敗（HTTP {e.status}）", d + [e.body[:200]], ["Bearer Token を再生成し bootstrap 再実行"])
        return StepResult(ACTION, f"X API エラー {e.status}", d + [e.body[:200]], ["再実行"])
    except requests.RequestException as e:
        return StepResult(ACTION, f"X API 到達不能（{e.__class__.__name__}）", d, ["ネットワークを確認"])
    pv = verify_x_pricing(s, ctx.db)
    d.append(f"X API 価格: {pv['status']}")
    return StepResult(READY, f"疎通 OK / 価格 {pv['status']}", d)


def step_deployment(ctx: Ctx) -> StepResult:
    d = []
    dep = ctx.db.get_setting("bot_deploy")
    if dep:
        info = json.loads(dep)
        return StepResult(READY, f"{info.get('provider')}: {info.get('detail')}", d)
    unit = ctx.settings.data_dir / "affiliate-bot.service"
    unit.write_text("[Unit]\nDescription=affiliate-bot loop\nAfter=network-online.target\n\n[Service]\n"
                    f"WorkingDirectory={ctx.project_dir}\nExecStart={sys.executable} -m affiliate_bot loop\nRestart=always\nRestartSec=30\n"
                    f"EnvironmentFile={ctx.store.path}\n\n[Install]\nWantedBy=multi-user.target\n", encoding="utf-8")
    cmd = f"cd {ctx.project_dir} && nohup {sys.executable} -m affiliate_bot loop >> {ctx.settings.data_dir}/loop.log 2>&1 &"
    d += [f"systemd ユニット: {unit}", f"簡易起動: {cmd}", "loop は毎朝 06:00 JST に fetch-products → learn → report → plan → export を実行し、毎時 metrics を取得します"]
    if ctx.io.interactive:
        ctx.io.say("常駐（loop）または毎朝 `python -m affiliate_bot plan` の手動実行のどちらでも運用できます。")
        if ctx.io.confirm("loop を常駐させましたか？（後で行う場合は n）"):
            ctx.db.set_setting("bot_deploy", json.dumps({"provider": "local_loop", "detail": "systemd/nohup", "at": utcnow()}))
            if not ctx.settings.slack_webhook_url and not ctx.settings.notify_console_delivery and ctx.io.confirm(
                    "要対応通知は loop.log（stdout）に出ます。loop.log を人間が監視しますか？（n なら Slack 設定まで通知は毎回再表示）"):
                ctx.set_env("NOTIFY_CONSOLE_DELIVERY", "true")
            return StepResult(READY, "ローカル/VPS で loop 常駐", d)
        return StepResult(READY, "手動運用（毎朝 plan / today を実行）", d)
    return StepResult(ACTION, "常駐先が未確定（手動運用も可）", d, ["loop を常駐させるか、毎朝 `plan` → `today` を手動実行"])


BOARD_KEYS = [("dmm", "FANZA API"), ("x", "X READ"), ("anthropic", "Anthropic"), ("database", "Database"), ("compliance", "Compliance"),
              ("secrets", "Secrets"), ("deployment", "Deployment")]
STEPS = [("environment", "環境", step_environment), ("dependencies", "依存パッケージ", step_dependencies), ("secrets", "Secret 保存", step_secrets_safety),
         ("database", "データベース", step_database), ("compliance", "コンプライアンス", step_compliance), ("anthropic", "Anthropic", step_anthropic),
         ("dmm", "FANZA / DMM", step_dmm), ("x", "X READ", step_x_read), ("deployment", "常駐", step_deployment)]


def run(settings: Settings, db: Database, io: IO, network: bool = True, only: list[str] | None = None) -> dict[str, StepResult]:
    ctx = Ctx(settings=settings, db=db, io=io, store=LocalEnvStore(BASE_DIR / ".env"), repo_root=BASE_DIR.parent, project_dir=BASE_DIR, network=network)
    prev = json.loads(db.get_setting("bootstrap_state", "{}") or "{}")
    io.say("=" * 64)
    io.say(" affiliate-bot bootstrap — FANZA 手動投稿アシストの初期設定（人間は認証・同意・課金・審査のみ）")
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
        except Exception as e:  # noqa: BLE001
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
        if res.status == BLOCKED and key in ("environment", "secrets"):
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
    overall = BLOCKED if any(st(k) == BLOCKED for k, _ in BOARD_KEYS) else (ACTION if any(st(k) != READY for k, _ in BOARD_KEYS) else READY)
    lines = ["┌" + "─" * 76 + "┐", "│ " + _pad(f"総合判定: {overall}", 75) + "│", "├" + "─" * 76 + "┤"]
    for k, label in BOARD_KEYS:
        r = results.get(k, StepResult(ACTION, "未実行"))
        lines.append("│ " + _pad(label, 12) + " " + _pad(r.status, 16) + " " + _pad(r.summary, 45) + "│")
    lines.append("└" + "─" * 76 + "┘")
    items = attention.open_items(db)
    if items:
        lines.append("要対応（Human Attention Queue）:")
        lines += [f"  #{it['id']} [{it['category']}] {it['title']}" + (f" → {it['action']}" if it["action"] else "") for it in items]
    acts = list(dict.fromkeys(a for k, _ in BOARD_KEYS for a in results.get(k, StepResult(READY, "")).actions))
    lines += (["次に人間がやること:"] + [f"  {HUMAN} {a}" for a in acts]) if acts else ["人間の作業: なし（毎朝 `today` を見て投稿するだけ）"]
    return "\n".join(lines)
