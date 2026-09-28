"""異常検知 → Human Attention Queue（Phase 3 では自動投稿が無いため「停止」は存在しない）。"""
from __future__ import annotations

from . import attention, products
from .config import Settings
from .db import Database


def run_checks(db: Database, settings: Settings) -> list[str]:
    reasons: list[str] = []
    attention.check_profit_negative(db)
    attention.check_data_stale(db)
    issues = products.check_consistency(db)
    if issues:
        attention.raise_item(db, "product_inconsistency", f"商品情報の不整合 {len(issues)} 件", detail="\n".join(issues[:20]),
                             action="fetch-products を再実行し、解消しなければ商品を除外", dedupe_key="product_inconsistency")
        reasons += issues[:5]
    unknown = db.one("SELECT COUNT(*) c FROM media_assets WHERE rights_status='needs_check'")
    if unknown and unknown["c"]:
        attention.raise_item(db, "media_rights", f"権利状態が未確認の素材 {unknown['c']} 件", action="素材の出所を確認し rights_status を更新",
                             dedupe_key="media_rights_needs_check")
    return reasons
