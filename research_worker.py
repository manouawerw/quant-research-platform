from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone

from research import build_evidence_package


def configured_watchlist() -> list[str]:
    raw = os.getenv("RESEARCH_WATCHLIST", "MU,AMD,NVDA")
    return [
        ticker.strip().upper()
        for ticker in raw.split(",")
        if ticker.strip()
    ]


def run_once() -> None:
    for ticker in configured_watchlist():
        try:
            package = build_evidence_package(
                ticker=ticker,
                technical_context={},
                include_news=True,
                include_macro=True,
            )

            print(
                json.dumps(
                    {
                        "ticker": ticker,
                        "generated_at": package.generated_at.isoformat(),
                        "sources": len(package.sources),
                        "claims": len(package.claims),
                        "quality": package.quality.model_dump(),
                    },
                    default=str,
                )
            )
        except Exception as exc:
            print(
                json.dumps(
                    {
                        "ticker": ticker,
                        "error": str(exc),
                        "at": datetime.now(timezone.utc).isoformat(),
                    }
                )
            )


if __name__ == "__main__":
    run_once()
