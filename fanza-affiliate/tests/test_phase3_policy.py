"""方針の検証: X への自動投稿機能が存在しないこと、HARD BLOCK が維持されていること、投稿文の規約チェック。"""
import inspect
import re
from pathlib import Path

import affiliate_bot.x_client as xc
from affiliate_bot import compliance, policy

PKG = Path(__file__).resolve().parent.parent / "affiliate_bot"


def test_x_client_has_no_write_capability():
    src = inspect.getsource(xc)
    for forbidden in ("create_post", "upload_media", "delete_post", "paid_partnership", "OAuth1", "media/upload", "oauth_signature"):
        assert forbidden not in src, forbidden
    assert re.search(r'self\.s\.(post|put|delete)\(', src) is None
    assert not hasattr(xc.XReadClient, "create_post")


def test_no_module_posts_to_x():
    for f in PKG.glob("*.py"):
        src = f.read_text(encoding="utf-8")
        assert "api.x.com/2/tweets\"" not in src.replace("'", '"') or "search/recent" in src
        assert "POST /2/tweets" not in src or f.name == "policy.py" or "禁止" in src or "存在しない" in src
    assert not (PKG / "publisher.py").exists()
    assert not (PKG / "tracking.py").exists()


def test_hard_block_registry_unchanged():
    assert policy.x_affiliate_hard_block("FANZA").blocked
    assert policy.x_affiliate_hard_block("DMM.com", genres=["アダルト"]).blocked
    assert "adult_sexual_products" in policy.X_PAID_PARTNERSHIP_PROHIBITED
    assert "HUMAN_POSTING_NOTICE" in dir(policy) and "投稿者本人" in policy.HUMAN_POSTING_NOTICE
    # 設定・環境変数で解除するフラグが存在しない
    from affiliate_bot.config import Settings
    assert not any("adult" in f.lower() and "ack" in f.lower() for f in Settings.__dataclass_fields__)


def test_check_text_rules():
    assert not compliance.check_text("作品名 見どころ").ok
    assert not compliance.check_text("女子高生 が主役【PR】").ok
    assert compliance.check_text("作品の紹介です【PR】", "https://pics.dmm.co.jp/a.jpg").ok
    assert not compliance.check_text("作品【PR】", "https://example.com/stolen.jpg").ok
    r = compliance.check_text("作品【PR】 https://example.com/x")
    assert r.ok and any("URL" in x for x in r.reasons)


def test_parse_post_id():
    assert xc.parse_post_id("https://x.com/user/status/1970000000000000001") == "1970000000000000001"
    assert xc.parse_post_id("https://twitter.com/user/status/123456789?s=20") == "123456789"
    assert xc.parse_post_id("1970000000000000001") == "1970000000000000001"
    assert xc.parse_post_id("https://x.com/user") is None
