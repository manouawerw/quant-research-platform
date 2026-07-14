from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from .http_client import ResearchHTTPClient


FRED_OBSERVATIONS_URL = (
    "https://api.stlouisfed.org/fred/series/observations"
)

DEFAULT_SERIES = {
    "DFF": "Federal funds effective rate",
    "DGS10": "10-year Treasury yield",
    "DGS2": "2-year Treasury yield",
    "VIXCLS": "CBOE volatility index",
    "DTWEXBGS": "Trade-weighted U.S. dollar index",
}


class FREDClient:
    def __init__(self) -> None:
        self.api_key = os.getenv("FRED_API_KEY")
        self.http = ResearchHTTPClient(
            user_agent="QuantResearchPlatform/1.0",
            minimum_interval_seconds=0.2,
        )

    def available(self) -> bool:
        return bool(self.api_key)

    def latest_observation(
        self,
        series_id: str,
    ) -> dict[str, Any] | None:
        if not self.api_key:
            return None

        payload = self.http.get_json(
            FRED_OBSERVATIONS_URL,
            params={
                "series_id": series_id,
                "api_key": self.api_key,
                "file_type": "json",
                "sort_order": "desc",
                "limit": 10,
            },
        )

        for observation in payload.get("observations", []):
            value = observation.get("value")

            if value in {None, "."}:
                continue

            return {
                "series_id": series_id,
                "date": observation.get("date"),
                "value": float(value),
                "retrieved_at": datetime.now(timezone.utc).isoformat(),
            }

        return None

    def snapshot(self) -> dict[str, Any]:
        if not self.api_key:
            return {
                "available": False,
                "message": (
                    "FRED_API_KEY is not configured. Macro evidence omitted."
                ),
            }

        data: dict[str, Any] = {"available": True, "series": {}}

        for series_id, label in DEFAULT_SERIES.items():
            observation = self.latest_observation(series_id)
            if observation:
                data["series"][series_id] = {
                    "label": label,
                    **observation,
                }

        return data
