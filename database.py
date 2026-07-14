import os
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    Integer,
    MetaData,
    String,
    Table,
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
    Column(
        "analyzed_at",
        DateTime(timezone=True),
        nullable=False,
        index=True,
    ),
    Column("latest_price", Float, nullable=False),
    Column("previous_close", Float, nullable=False),
    Column("daily_change_pct", Float, nullable=False),
    Column("trend", String(50), nullable=False),
    Column("setup_status", String(100), nullable=False),
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
    Column(
        "model_version",
        String(50),
        nullable=False,
        default="technical-v1",
    ),
)


def get_database_engine() -> Engine:
    """Create a SQLAlchemy engine using Railway's DATABASE_URL."""

    database_url = os.environ.get("DATABASE_URL")

    if not database_url:
        raise RuntimeError(
            "DATABASE_URL is missing from Railway Variables."
        )

    # Some providers still return postgres://, while SQLAlchemy expects
    # postgresql://.
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
    """Create application tables when they do not already exist."""

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
    latest: Any,
    zones: dict[str, float],
    risk_reward: float | None,
) -> int:
    """Save one complete technical-analysis snapshot."""

    values = {
        "ticker": ticker.upper(),
        "analyzed_at": datetime.now(timezone.utc),
        "latest_price": float(latest_price),
        "previous_close": float(previous_close),
        "daily_change_pct": float(daily_change_pct),
        "trend": trend,
        "setup_status": setup_status,
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
        "pullback_entry_low": float(
            zones["pullback_entry_low"]
        ),
        "pullback_entry_high": float(
            zones["pullback_entry_high"]
        ),
        "breakout_entry_low": float(
            zones["breakout_entry_low"]
        ),
        "breakout_entry_high": float(
            zones["breakout_entry_high"]
        ),
        "invalidation_level": float(
            zones["invalidation_level"]
        ),
        "profit_zone_1_low": float(
            zones["profit_zone_1_low"]
        ),
        "profit_zone_1_high": float(
            zones["profit_zone_1_high"]
        ),
        "profit_zone_2_low": float(
            zones["profit_zone_2_low"]
        ),
        "profit_zone_2_high": float(
            zones["profit_zone_2_high"]
        ),
        "risk_reward": (
            float(risk_reward)
            if risk_reward is not None
            else None
        ),
        "model_version": "technical-v1",
    }

    with engine.begin() as connection:
        result = connection.execute(
            analysis_runs.insert().values(**values)
        )

        inserted_id = result.inserted_primary_key[0]

    return int(inserted_id)


def get_recent_analyses(
    engine: Engine,
    ticker: str,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Return recent saved analyses for one ticker."""

    query = (
        select(analysis_runs)
        .where(analysis_runs.c.ticker == ticker.upper())
        .order_by(desc(analysis_runs.c.analyzed_at))
        .limit(limit)
    )

    with engine.connect() as connection:
        rows = connection.execute(query).mappings().all()

    return [dict(row) for row in rows]
