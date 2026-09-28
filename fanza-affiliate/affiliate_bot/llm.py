"""Claude API ルーター。役割ごとにモデルを固定し、トークン使用量とコストを DB に記録する。

- Sonnet 5  : 投稿案の大量生成・リライト・分類・要約（日次で最も呼ばれる）
- Opus 5.5  : 日次の上位候補選定・品質チェック・A/B 設計・Sonnet 成果物レビュー
- Fable 5.1 : 週次レビューのみ（7 日に 1 回）
LLM で解く必要のない処理（集計・スコアリング・スケジューリング）は一切呼ばない。
API キーがない／DRY_RUN／予算超過／refusal の場合は呼び出し側が決定論的フォールバックを使う。
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from .config import Settings
from .db import Database

# USD / 1M tokens（claude-api スキルの価格表 2026-06 時点）
PRICING = {
    "claude-sonnet-5": {"in": 2.0, "out": 10.0, "cache": 0.20},
    "claude-opus-5-5": {"in": 4.0, "out": 20.0, "cache": 0.20},
    "claude-opus-5": {"in": 5.0, "out": 25.0, "cache": 0.50},
    "claude-fable-5-1": {"in": 10.0, "out": 50.0, "cache": 0.25},
    "claude-haiku-4-5": {"in": 1.0, "out": 5.0, "cache": 0.10},
}

ROLE_MODEL = {"sonnet": "model_sonnet", "opus": "model_opus", "fable": "model_fable"}
ROLE_EFFORT = {"sonnet": "low", "opus": "medium", "fable": "high"}


class LLMUnavailable(RuntimeError):
    """API キーなし／予算超過／refusal など。呼び出し側はフォールバックする。"""


@dataclass
class LLMResult:
    text: str
    parsed: Any
    model: str
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cost_jpy: float


def estimate_cost_usd(model: str, inp: int, out: int, cache: int = 0) -> float:
    p = PRICING.get(model) or {"in": 5.0, "out": 25.0, "cache": 0.5}
    return (inp * p["in"] + out * p["out"] + cache * p["cache"]) / 1_000_000


class LLMRouter:
    def __init__(self, settings: Settings, db: Database, client: Any = None):
        self.settings = settings
        self.db = db
        self._client = client
        self.enabled = bool(settings.anthropic_api_key) or client is not None

    # ---- 予算 ----
    def spent_today_jpy(self) -> float:
        now = datetime.now(timezone.utc)
        start = (now - timedelta(hours=24)).isoformat(timespec="seconds")
        return self.db.cost_between(start, now.isoformat(timespec="seconds"), kind="ai")

    def _check_budget(self, role: str) -> None:
        # 週次の Fable は日次予算の対象外（週次予算として別途管理）
        if role == "fable":
            return
        spent = self.spent_today_jpy()
        if spent >= self.settings.daily_ai_budget_jpy:
            raise LLMUnavailable(f"AI 日次予算超過: {spent:.0f}円 >= {self.settings.daily_ai_budget_jpy:.0f}円")

    def _get_client(self):
        if self._client is not None:
            return self._client
        if not self.settings.anthropic_api_key:
            raise LLMUnavailable("ANTHROPIC_API_KEY 未設定")
        import anthropic  # 遅延 import（未インストール環境でも他機能を動かす）

        self._client = anthropic.Anthropic(api_key=self.settings.anthropic_api_key)
        return self._client

    # ---- 呼び出し ----
    def call(
        self,
        role: str,
        system: str,
        user: str,
        schema: dict | None = None,
        max_tokens: int = 4000,
        ref: str | None = None,
    ) -> LLMResult:
        if role not in ROLE_MODEL:
            raise ValueError(f"unknown role {role}")
        if not self.enabled:
            raise LLMUnavailable("LLM 無効（API キー未設定）")
        self._check_budget(role)
        model = getattr(self.settings, ROLE_MODEL[role])
        client = self._get_client()

        kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            "messages": [{"role": "user", "content": user}],
            "output_config": {"effort": ROLE_EFFORT[role]},
        }
        if schema is not None:
            kwargs["output_config"]["format"] = {"type": "json_schema", "schema": schema}

        if role == "fable":
            # Fable 5.1: thinking は常時 ON（パラメータ省略）。安全分類器の refusal に備え
            # サーバーサイドの fallbacks を既定で有効化する。
            resp = client.beta.messages.create(
                betas=["server-side-fallback-2026-07-01"], fallbacks="default", **kwargs
            )
        else:
            resp = client.messages.create(**kwargs)

        usage = getattr(resp, "usage", None)
        inp = int(getattr(usage, "input_tokens", 0) or 0)
        out = int(getattr(usage, "output_tokens", 0) or 0)
        cache = int(getattr(usage, "cache_read_input_tokens", 0) or 0)
        served_model = getattr(resp, "model", model) or model
        cost_jpy = round(estimate_cost_usd(served_model, inp, out, cache) * self.settings.usd_jpy, 4)
        self.db.add_cost("ai", cost_jpy, model=served_model, input_tokens=inp, output_tokens=out,
                         cache_read_tokens=cache, ref=ref or role)

        if getattr(resp, "stop_reason", None) == "refusal":
            details = getattr(resp, "stop_details", None)
            self.db.log_event("warn", "llm_refusal", f"{served_model} refusal", {"ref": ref, "details": str(details)})
            raise LLMUnavailable("モデルが応答を拒否しました（refusal）")

        text = "".join(getattr(b, "text", "") for b in resp.content if getattr(b, "type", "") == "text")
        parsed = None
        if schema is not None:
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError as e:
                raise LLMUnavailable(f"JSON 解析失敗: {e}") from e
        return LLMResult(text=text, parsed=parsed, model=served_model, input_tokens=inp,
                         output_tokens=out, cache_read_tokens=cache, cost_jpy=cost_jpy)


class FakeLLMClient:
    """テスト用。固定の JSON を返す。"""

    def __init__(self, responses: list[str] | None = None, stop_reason: str = "end_turn"):
        self.responses = list(responses or ["{}"])
        self.calls: list[dict] = []
        self.stop_reason = stop_reason
        self.messages = self
        self.beta = self

    def create(self, **kwargs):
        self.calls.append(kwargs)
        text = self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]

        class _B:
            type = "text"

            def __init__(self, t):
                self.text = t

        class _U:
            input_tokens = 500
            output_tokens = 300
            cache_read_input_tokens = 0

        class _R:
            pass

        r = _R()
        r.content = [_B(text)]
        r.usage = _U()
        r.model = kwargs.get("model")
        r.stop_reason = self.stop_reason
        r.stop_details = None
        return r
