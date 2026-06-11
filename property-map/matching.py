"""物件 × 顧客 マッチングエンジン (Phase1)

役割:
- 構造化済み物件レコード（extractor.py出力）に対し、希望条件を持つ顧客をスコアリングし
  「提案すべき顧客」をランキングする。Faciloの一斉提案・マッチングスコアに相当。
- マッチ理由を返し、なぜ提案候補なのかを営業が即判断できるようにする。
- 顧客の希望条件(criteria)は将来Salesforceから一方向同期する想定（現状はcustomers.json）。

スコア配分（合計100、業種適合は加点）:
  物件種目 30 / 予算 30 / 面積 20 / エリア・駅 20 / 業種適合 +最大10
"""
from __future__ import annotations

import os

W_TYPE = 30
W_BUDGET = 30
W_AREA = 20
W_LOCATION = 20
W_BUSINESS = 10


def _type_score(prop: dict, c: dict) -> tuple[float, str | None]:
    ptype = prop.get("property_type") or ""
    wants = c.get("property_types") or []
    if not wants:
        return W_TYPE * 0.5, None
    for w in wants:
        if w in ptype:
            return W_TYPE, f"種目一致（{w}）"
    return 0.0, None


def _budget_score(prop: dict, c: dict) -> tuple[float, str | None]:
    rent = prop.get("rent_yen")
    lo, hi = c.get("budget_min"), c.get("budget_max")
    if rent is None or hi is None:
        return W_BUDGET * 0.5, None
    if (lo is None or rent >= lo) and rent <= hi:
        return W_BUDGET, f"予算内（{rent:,}円 ≤ {hi:,}円）"
    if rent <= hi * 1.1:
        return W_BUDGET * 0.5, f"予算やや超過（{rent:,}円, 上限{hi:,}円）"
    return 0.0, f"予算オーバー（{rent:,}円 > {hi:,}円）"


def _area_score(prop: dict, c: dict) -> tuple[float, str | None]:
    area = prop.get("area_sqm")
    lo, hi = c.get("area_sqm_min"), c.get("area_sqm_max")
    if area is None:
        return W_AREA * 0.5, None
    lo_ok = lo is None or area >= lo * 0.9
    hi_ok = hi is None or area <= hi * 1.1
    if lo_ok and hi_ok:
        return W_AREA, f"面積適合（{area}㎡）"
    return 0.0, f"面積不一致（{area}㎡, 希望{lo}〜{hi}㎡）"


def _location_score(prop: dict, c: dict) -> tuple[float, str | None]:
    address = prop.get("address") or ""
    prop_stations = {s.get("station", "") for s in (prop.get("stations") or [])}
    areas = c.get("areas") or []
    stations = set(c.get("stations") or [])

    area_hit = next((a for a in areas if a and a in address), None)
    station_hit = prop_stations & stations
    if area_hit and station_hit:
        return W_LOCATION, f"エリア・駅一致（{area_hit} / {'・'.join(station_hit)}駅）"
    if area_hit:
        return W_LOCATION * 0.8, f"エリア一致（{area_hit}）"
    if station_hit:
        return W_LOCATION * 0.8, f"駅一致（{'・'.join(station_hit)}駅）"
    return 0.0, None


def _business_score(prop: dict, c: dict) -> tuple[float, str | None]:
    allowed = prop.get("allowed_business") or []
    wants = c.get("business_use") or []
    if not allowed or not wants:
        return 0.0, None
    for w in wants:
        for a in allowed:
            if w in a or a in w:
                return W_BUSINESS, f"出店業種適合（{w}）"
    return 0.0, None


def _restriction_block(prop: dict, c: dict) -> str | None:
    """物件の禁止業種と顧客の希望業種が衝突する場合に理由を返す（=提案不可）。"""
    restricted = prop.get("restricted_business") or []
    wants = c.get("business_use") or []
    if not restricted or not wants:
        return None
    for r in restricted:
        for w in wants:
            if r and w and (r in w or w in r):
                return f"出店不可業種に該当（{r}）"
    return None


def score_match(prop: dict, customer: dict) -> dict:
    """物件×顧客のマッチスコアと理由を返す。

    物件の禁止業種に顧客業種が該当する場合は excluded=True とし、提案対象から外す。
    """
    c = customer.get("criteria") or {}
    block_reason = _restriction_block(prop, c)
    score = 0.0
    reasons: list[str] = []
    for fn in (_type_score, _budget_score, _area_score, _location_score, _business_score):
        s, reason = fn(prop, c)
        score += s
        if reason:
            reasons.append(reason)
    result = {
        "customer_id": customer["id"],
        "customer_name": customer.get("name", ""),
        "contact": customer.get("contact", ""),
        "tags": customer.get("tags", []),
        "score": round(min(score, 100.0), 1),
        "reasons": reasons,
    }
    if block_reason:
        result["excluded"] = True
        result["exclude_reason"] = block_reason
        result["score"] = 0.0
        result["reasons"] = [block_reason]
    return result


def rank_customers(prop: dict, customers: list[dict], proposed_ids: set[str] | None = None,
                   min_score: float = 40.0) -> list[dict]:
    """物件に対する候補顧客をスコア降順で返す。提案済みはフラグを立てる。"""
    proposed_ids = proposed_ids or set()
    ranked = []
    for cust in customers:
        m = score_match(prop, cust)
        if m.get("excluded"):  # 出店不可業種は提案対象から除外
            continue
        if m["score"] < min_score:
            continue
        m["already_proposed"] = cust["id"] in proposed_ids
        ranked.append(m)
    ranked.sort(key=lambda x: x["score"], reverse=True)
    return ranked


# ---------------------------------------------------------------------------
# 提案文面生成（Faciloの提案メールAI生成に相当）
# ---------------------------------------------------------------------------

def _proposal_template(prop: dict, customer: dict) -> str:
    name = customer.get("contact") or customer.get("name", "")
    bname = prop.get("building_name") or "ご紹介物件"
    room = prop.get("room") or ""
    rent = prop.get("rent_yen")
    rent_s = f"{rent:,}円/月" if rent else "応相談"
    area = prop.get("area_sqm")
    area_s = f"{area}㎡" if area else "—"
    addr = prop.get("address") or "—"
    stations = "、".join(
        f"{s.get('line','')}{s.get('station','')}駅 徒歩{s.get('walk_min','')}分"
        for s in (prop.get("stations") or [])[:2]
    ) or "—"
    return (
        f"{name}\n\n"
        f"いつもお世話になっております。\n"
        f"ご希望条件に合致する物件が出ましたのでご案内いたします。\n\n"
        f"■ {bname} {room}\n"
        f"・所在地：{addr}\n"
        f"・交通：{stations}\n"
        f"・賃料：{rent_s}\n"
        f"・面積：{area_s}（{prop.get('layout') or '—'}）\n"
        f"・現況：{prop.get('current_status') or '—'} / {prop.get('availability') or '—'}\n\n"
        f"ご興味ございましたら、内見の日程を調整いたします。\n"
        f"よろしくお願いいたします。"
    )


_PROPOSAL_SYSTEM = (
    "あなたは事業用不動産仲介の営業担当です。顧客の希望条件と物件情報をもとに、"
    "簡潔で礼儀正しい提案メール本文を日本語で書きます。誇張せず事実ベースで、"
    "顧客の業種・希望に物件がどう合うかを1〜2文添えてください。署名は不要。"
    "メール本文として送るため、マークダウン記法（**や#等）は使わずプレーンテキストで書く。"
)


def generate_proposal_text(prop: dict, customer: dict) -> str:
    """提案メール本文を生成。APIキーがあればClaude、なければテンプレート。"""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return _proposal_template(prop, customer)
    try:
        import json
        import anthropic
        client = anthropic.Anthropic()
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=700,
            system=[{"type": "text", "text": _PROPOSAL_SYSTEM,
                     "cache_control": {"type": "ephemeral"}}],
            messages=[{
                "role": "user",
                "content": (
                    f"顧客: {json.dumps(customer, ensure_ascii=False)}\n\n"
                    f"物件: {json.dumps(prop, ensure_ascii=False)}\n\n"
                    "上記をもとに提案メール本文を作成してください。"
                ),
            }],
        )
        return "".join(b.text for b in resp.content if b.type == "text").strip()
    except Exception as e:
        print(f"[matching] proposal LLM failed, using template: {e}")
        return _proposal_template(prop, customer)
