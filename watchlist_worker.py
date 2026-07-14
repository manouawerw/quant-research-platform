from __future__ import annotations

import os
import time
from datetime import datetime, timezone

from database import (
    get_database_engine,
    initialize_database,
    save_watchlist_snapshot,
)
from watchlist_scanner import scan_watchlist


DEFAULT_INTERVAL_SECONDS = 300


def configured_watchlist() -> list[str]:
    raw = os.getenv(
        "RESEARCH_WATCHLIST",
        "MU,AMD,NVDA,AAPL,MSFT,GOOGL,META,AMZN,TSM,AVGO",
    )

    return [
        ticker.strip().upper()
        for ticker in raw.split(",")
        if ticker.strip()
    ]


def run_scan() -> None:
    benchmark = os.getenv("WATCHLIST_BENCHMARK", "SPY").upper()
    engine = get_database_engine()
    initialize_database(engine)

    results, errors = scan_watchlist(
        configured_watchlist(),
        benchmark=benchmark,
    )

    scan_group = datetime.now(timezone.utc).isoformat()

    for result in results:
        save_watchlist_snapshot(
            engine,
            result=result.to_dict(),
            benchmark=benchmark,
            scan_group=scan_group,
        )

    print(
        {
            "scan_group": scan_group,
            "benchmark": benchmark,
            "saved": len(results),
            "errors": errors,
        }
    )


if __name__ == "__main__":
    run_forever = os.getenv(
        "WATCHLIST_RUN_FOREVER",
        "false",
    ).lower() == "true"

    interval = int(
        os.getenv(
            "WATCHLIST_INTERVAL_SECONDS",
            str(DEFAULT_INTERVAL_SECONDS),
        )
    )

    if run_forever:
        while True:
            try:
                run_scan()
            except Exception as exc:
                print({"worker_error": str(exc)})

            time.sleep(max(interval, 60))
    else:
        run_scan()
