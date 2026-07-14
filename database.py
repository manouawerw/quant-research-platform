from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
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
    create_engine,
    desc,
    select,
)
from sqlalchemy.engine import Engine


metadata = MetaData()

analysis_runs = Table(
    "analysis_runs",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("ticker", String(20), nullable=False, index=True),
    Column("analyzed_at", DateTime(timezone=True), nullable=False, index=True),
    Column("latest_price", Float, nullable=False),
    Column("previous_close", Float, nullable=False),
    Column("daily_change_pct", Float, nullable=False),
    Column("trend", String(50), nullable=False),
    Column("setup_status", String(100), nullable=False),
    Column("technical_score", Integer, nullable=False),
    Column("confidence", Integer, nullable=False),
    Column("rsi_14", Float, nullable=False),
    Column("atr_14", Float, nullable=False),
    Column("volatility_20", Float, nullable=False),
    Column("relative_volume", Float, nullable=False),
    Column("sma_20", Float, nullable=False),
    Column("sma_50", Float, nullable=False),
    Column("support_low", Float, nullable=False),
    Column("support_high", Float, nullable=False),
    Column("resistance_low", Float, nullable=False),
    Column("resistance_high", Float, nullable=False),
    Column("pullback_entry_low", Float, nullable=False),
    Column("pullback_entry_high", Float, nullable=False),
    Column("breakout_entry_low", Float, nullable=False),
    Column("breakout_entry_high", Float, nullable=False),
    Column("invalidation_level", Float, nullable=False),
    Column("profit_zone_1_low", Float, nullable=False),
    Column("profit_zone_1_high", Float, nullable=False),
    Column("profit_zone_2_low", Float, nullable=False),
    Column("profit_zone_2_high", Float, nullable=False),
    Column("risk_reward", Float, nullable=True),
    Column("model_version", String(50), nullable=False, default="technical-v3"),
)

ai_reports = Table(
    "ai_reports",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("ticker", String(20), nullable=False, index=True),
    Column("generated_at", DateTime(timezone=True), nullable=False, index=True),
    Column("expires_at", DateTime(timezone=True), nullable=False, index=True),
    Column("trigger_type", String(30), nullable=False),
    Column("technical_score", Integer, nullable=False),
    Column("relative_strength_score", Integer, nullable=False),
    Column("market_regime", String(50), nullable=False),
    Column("model", String(100), nullable=False),
    Column("report_markdown", Text, nullable=False),
    Column("sources_json", Text, nullable=False),
    Column("search_queries_json", Text, nullable=False),
)

watchlist_snapshots = Table(
    "watchlist_snapshots",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("scan_group", String(80), nullable=False, index=True),
    Column("scanned_at", DateTime(timezone=True), nullable=False, index=True),
    Column("ticker", String(20), nullable=False, index=True),
    Column("benchmark", String(20), nullable=False),
    Column("latest_price", Float, nullable=False),
    Column("daily_change_pct", Float, nullable=False),
    Column("technical_score", Integer, nullable=False),
    Column("score_confidence", Integer, nullable=False),
    Column("relative_strength_score", Integer, nullable=False),
    Column("relative_strength_trend", String(50), nullable=False),
    Column("market_regime", String(50), nullable=False),
    Column("trend", String(50), nullable=False),
    Column("setup_type", String(30), nullable=False),
    Column("setup_status", String(50), nullable=False),
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
    Column("risk_reward_2", Float, nullable=True),
    Column("price_plan_confidence", Integer, nullable=False),
    Column("relative_volume", Float, nullable=False),
    Column("rsi_14", Float, nullable=False),
    Column("volatility_20_pct", Float, nullable=False),
    Column("attention_score", Integer, nullable=False, index=True),
    Column("attention_reason", Text, nullable=False),
    Column("warnings_json", Text, nullable=False),
)


def get_database_engine() -> Engine:
    database_url = os.environ.get("DATABASE_URL")

    if not database_url:
        raise RuntimeError("DATABASE_URL is missing from the environment.")

    if database_url.startswith("postgres://"):
        database_url = database_url.replace(
            "postgres://",
            "postgresql://",
            1,
        )

    return create_engine(
        database_url,
        pool_pre_ping=True,
        pool_recycle=300,
    )


def initialize_database(engine: Engine) -> None:
    metadata.create_all(engine)


def save_analysis(
    engine: Engine,
    *,
    ticker: str,
    latest_price: float,
    previous_close: float,
    daily_change_pct: float,
    trend: str,
    setup_status: str,
    technical_score: int,
    confidence: int,
    latest: Any,
    zones: dict[str, float],
    risk_reward: float | None,
) -> int:
    values = {
        "ticker": ticker.upper(),
        "analyzed_at": datetime.now(timezone.utc),
        "latest_price": float(latest_price),
        "previous_close": float(previous_close),
        "daily_change_pct": float(daily_change_pct),
        "trend": trend,
        "setup_status": setup_status,
        "technical_score": int(technical_score),
        "confidence": int(confidence),
        "rsi_14": float(latest["rsi_14"]),
        "atr_14": float(latest["atr_14"]),
        "volatility_20": float(latest["volatility_20"]),
        "relative_volume": float(latest["relative_volume"]),
        "sma_20": float(latest["sma_20"]),
        "sma_50": float(latest["sma_50"]),
        "support_low": float(zones["support_low"]),
        "support_high": float(zones["support_high"]),
        "resistance_low": float(zones["resistance_low"]),
        "resistance_high": float(zones["resistance_high"]),
        "pullback_entry_low": float(zones["pullback_entry_low"]),
        "pullback_entry_high": float(zones["pullback_entry_high"]),
        "breakout_entry_low": float(zones["breakout_entry_low"]),
        "breakout_entry_high": float(zones["breakout_entry_high"]),
        "invalidation_level": float(zones["invalidation_level"]),
        "profit_zone_1_low": float(zones["profit_zone_1_low"]),
        "profit_zone_1_high": float(zones["profit_zone_1_high"]),
        "profit_zone_2_low": float(zones["profit_zone_2_low"]),
        "profit_zone_2_high": float(zones["profit_zone_2_high"]),
        "risk_reward": float(risk_reward) if risk_reward is not None else None,
        "model_version": "technical-v3",
    }

    with engine.begin() as connection:
        result = connection.execute(
            analysis_runs.insert().values(**values)
        )
        return int(result.inserted_primary_key[0])


def get_recent_analyses(
    engine: Engine,
    ticker: str,
    limit: int = 20,
) -> list[dict[str, Any]]:
    query = (
        select(analysis_runs)
        .where(analysis_runs.c.ticker == ticker.upper())
        .order_by(desc(analysis_runs.c.analyzed_at))
        .limit(limit)
    )

    with engine.connect() as connection:
        rows = connection.execute(query).mappings().all()

    return [dict(row) for row in rows]


def save_ai_report(
    engine: Engine,
    *,
    ticker: str,
    trigger_type: str,
    technical_score: int,
    relative_strength_score: int,
    market_regime: str,
    model: str,
    report_markdown: str,
    sources: list[dict[str, str]],
    search_queries: list[str],
    cache_hours: int = 12,
) -> int:
    generated_at = datetime.now(timezone.utc)

    values = {
        "ticker": ticker.upper(),
        "generated_at": generated_at,
        "expires_at": generated_at + timedelta(hours=cache_hours),
        "trigger_type": trigger_type,
        "technical_score": int(technical_score),
        "relative_strength_score": int(relative_strength_score),
        "market_regime": market_regime,
        "model": model,
        "report_markdown": report_markdown,
        "sources_json": json.dumps(sources),
        "search_queries_json": json.dumps(search_queries),
    }

    with engine.begin() as connection:
        result = connection.execute(
            ai_reports.insert().values(**values)
        )
        return int(result.inserted_primary_key[0])


def get_latest_ai_report(
    engine: Engine,
    ticker: str,
    *,
    fresh_only: bool = False,
) -> dict[str, Any] | None:
    query = (
        select(ai_reports)
        .where(ai_reports.c.ticker == ticker.upper())
        .order_by(desc(ai_reports.c.generated_at))
        .limit(1)
    )

    if fresh_only:
        query = query.where(
            ai_reports.c.expires_at > datetime.now(timezone.utc)
        )

    with engine.connect() as connection:
        row = connection.execute(query).mappings().first()

    if row is None:
        return None

    result = dict(row)
    result["sources"] = json.loads(result.pop("sources_json"))
    result["search_queries"] = json.loads(
        result.pop("search_queries_json")
    )

    return result


def count_ai_reports_today(engine: Engine) -> int:
    today = datetime.now(timezone.utc).date()

    start = datetime(
        today.year,
        today.month,
        today.day,
        tzinfo=timezone.utc,
    )

    query = select(ai_reports.c.id).where(
        ai_reports.c.generated_at >= start
    )

    with engine.connect() as connection:
        return len(connection.execute(query).all())


def save_watchlist_snapshot(
    engine: Engine,
    *,
    result: dict[str, Any],
    benchmark: str,
    scan_group: str,
) -> int:
    values = {
        "scan_group": scan_group,
        "scanned_at": result["scanned_at"],
        "ticker": result["ticker"],
        "benchmark": benchmark,
        "latest_price": float(result["latest_price"]),
        "daily_change_pct": float(result["daily_change_pct"]),
        "technical_score": int(result["technical_score"]),
        "score_confidence": int(result["score_confidence"]),
        "relative_strength_score": int(
            result["relative_strength_score"]
        ),
        "relative_strength_trend": result[
            "relative_strength_trend"
        ],
        "market_regime": result["market_regime"],
        "trend": result["trend"],
        "setup_type": result["setup_type"],
        "setup_status": result["setup_status"],
        "entry_low": float(result["entry_low"]),
        "entry_high": float(result["entry_high"]),
        "breakout_entry_low": float(
            result["breakout_entry_low"]
        ),
        "breakout_entry_high": float(
            result["breakout_entry_high"]
        ),
        "invalidation": float(result["invalidation"]),
        "target_1_low": float(result["target_1_low"]),
        "target_1_high": float(result["target_1_high"]),
        "target_2_low": float(result["target_2_low"]),
        "target_2_high": float(result["target_2_high"]),
        "risk_reward_1": (
            float(result["risk_reward_1"])
            if result["risk_reward_1"] is not None
            else None
        ),
        "risk_reward_2": (
            float(result["risk_reward_2"])
            if result["risk_reward_2"] is not None
            else None
        ),
        "price_plan_confidence": int(
            result["price_plan_confidence"]
        ),
        "relative_volume": float(result["relative_volume"]),
        "rsi_14": float(result["rsi_14"]),
        "volatility_20_pct": float(
            result["volatility_20_pct"]
        ),
        "attention_score": int(result["attention_score"]),
        "attention_reason": result["attention_reason"],
        "warnings_json": json.dumps(result["warnings"]),
    }

    with engine.begin() as connection:
        inserted = connection.execute(
            watchlist_snapshots.insert().values(**values)
        )
        return int(inserted.inserted_primary_key[0])


def get_latest_watchlist_snapshot(
    engine: Engine,
    *,
    limit: int = 100,
) -> list[dict[str, Any]]:
    latest_group_query = (
        select(watchlist_snapshots.c.scan_group)
        .order_by(desc(watchlist_snapshots.c.scanned_at))
        .limit(1)
    )

    with engine.connect() as connection:
        scan_group = connection.execute(
            latest_group_query
        ).scalar_one_or_none()

        if not scan_group:
            return []

        query = (
            select(watchlist_snapshots)
            .where(
                watchlist_snapshots.c.scan_group == scan_group
            )
            .order_by(
                desc(watchlist_snapshots.c.attention_score)
            )
            .limit(limit)
        )

        rows = connection.execute(query).mappings().all()

    output = []

    for row in rows:
        item = dict(row)
        item["warnings"] = json.loads(
            item.pop("warnings_json")
        )
        output.append(item)

    return output
