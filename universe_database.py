from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    desc,
    select,
)
from sqlalchemy.engine import Engine


metadata = MetaData()

universe_scans = Table(
    "universe_scans",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("scan_group", String(80), nullable=False, index=True),
    Column("scanned_at", DateTime(timezone=True), nullable=False, index=True),
    Column("ticker", String(20), nullable=False, index=True),
    Column("company_name", String(200), nullable=False),
    Column("sector", String(120), nullable=False, index=True),
    Column("sub_industry", String(160), nullable=False),
    Column("latest_price", Float, nullable=False),
    Column("daily_change_pct", Float, nullable=False),
    Column("technical_score", Integer, nullable=False),
    Column("score_confidence", Integer, nullable=False),
    Column("relative_strength_score", Integer, nullable=False),
    Column("relative_strength_trend", String(50), nullable=False),
    Column("market_regime", String(50), nullable=False),
    Column("trend", String(50), nullable=False),
    Column("setup_type", String(30), nullable=False),
    Column("setup_status", String(50), nullable=False, index=True),
    Column("entry_low", Float, nullable=False),
    Column("entry_high", Float, nullable=False),
    Column("breakout_entry_low", Float, nullable=False),
    Column("breakout_entry_high", Float, nullable=False),
    Column("invalidation", Float, nullable=False),
    Column("target_1_low", Float, nullable=False),
    Column("target_1_high", Float, nullable=False),
    Column("target_2_low", Float, nullable=False),
    Column("target_2_high", Float, nullable=False),
    Column("risk_reward_1", Float, nullable=True),
    Column("price_plan_confidence", Integer, nullable=False),
    Column("attention_score", Integer, nullable=False, index=True),
    Column("attention_reason", Text, nullable=False),
    Column("cdr_available", Boolean, nullable=False),
    Column("cdr_symbol", String(30), nullable=True),
    Column("cdr_price_cad", Float, nullable=True),
    Column("cdr_pullback_low_cad", Float, nullable=True),
    Column("cdr_pullback_high_cad", Float, nullable=True),
    Column("cdr_breakout_low_cad", Float, nullable=True),
    Column("cdr_breakout_high_cad", Float, nullable=True),
    Column("cdr_invalidation_cad", Float, nullable=True),
    Column("cdr_target_1_low_cad", Float, nullable=True),
    Column("cdr_target_1_high_cad", Float, nullable=True),
    Column("cdr_warning", Text, nullable=True),
)


def initialize_universe_tables(engine: Engine) -> None:
    metadata.create_all(engine)


def save_universe_scan(
    engine: Engine,
    *,
    scan_group: str,
    results: list[dict[str, Any]],
) -> None:
    if not results:
        return

    rows = [{"scan_group": scan_group, **item} for item in results]

    with engine.begin() as connection:
        connection.execute(universe_scans.insert(), rows)


def get_latest_universe_scan(
    engine: Engine,
    *,
    limit: int = 500,
) -> list[dict[str, Any]]:
    with engine.connect() as connection:
        latest_group = connection.execute(
            select(universe_scans.c.scan_group)
            .order_by(desc(universe_scans.c.scanned_at))
            .limit(1)
        ).scalar_one_or_none()

        if latest_group is None:
            return []

        rows = connection.execute(
            select(universe_scans)
            .where(universe_scans.c.scan_group == latest_group)
            .order_by(desc(universe_scans.c.attention_score))
            .limit(limit)
        ).mappings().all()

    return [dict(row) for row in rows]
