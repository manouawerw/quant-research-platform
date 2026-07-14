from __future__ import annotations

import os
import time
from datetime import datetime, timezone

from database import (
    get_database_engine,
    initialize_database,
)
from universe import fetch_universe
from universe_database import (
    initialize_universe_tables,
    save_universe_scan,
)
from universe_scanner import scan_universe


def run_once() -> None:
    universe_name = os.getenv(
        "UNIVERSE_NAME",
        "US Liquid 1500",
    )
    benchmark = os.getenv(
        "UNIVERSE_BENCHMARK",
        "SPY",
    ).upper()
    target_size = int(
        os.getenv("UNIVERSE_TARGET_SIZE", "1500")
    )
    minimum_price = float(
        os.getenv("UNIVERSE_MIN_PRICE", "2")
    )
    minimum_dollar_volume = float(
        os.getenv(
            "UNIVERSE_MIN_DOLLAR_VOLUME",
            "2000000",
        )
    )
    cdr_top = int(
        os.getenv("CDR_LOOKUP_TOP_N", "25")
    )

    engine = get_database_engine()
    initialize_database(engine)
    initialize_universe_tables(engine)

    members = fetch_universe(universe_name)

    results, errors = scan_universe(
        members,
        benchmark=benchmark,
        target_size=target_size,
        minimum_price=minimum_price,
        minimum_dollar_volume=(
            minimum_dollar_volume
        ),
        include_cdr_for_top=cdr_top,
    )

    scan_group = (
        datetime.now(timezone.utc).isoformat()
    )

    save_universe_scan(
        engine,
        scan_group=scan_group,
        results=[
            result.to_dict()
            for result in results
        ],
    )

    print(
        {
            "scan_group": scan_group,
            "universe": universe_name,
            "candidate_members": len(members),
            "saved_results": len(results),
            "errors": len(errors),
        }
    )


if __name__ == "__main__":
    run_forever = os.getenv(
        "UNIVERSE_RUN_FOREVER",
        "false",
    ).lower() == "true"

    interval = max(
        300,
        int(
            os.getenv(
                "UNIVERSE_INTERVAL_SECONDS",
                "300",
            )
        ),
    )

    if run_forever:
        while True:
            started = time.time()

            try:
                run_once()
            except Exception as exc:
                print(
                    {
                        "universe_worker_error": (
                            str(exc)
                        )
                    }
                )

            elapsed = time.time() - started
            time.sleep(
                max(60, interval - elapsed)
            )
    else:
        run_once()
