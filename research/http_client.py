from __future__ import annotations

import time
from typing import Any

import requests


class ResearchHTTPClient:
    def __init__(
        self,
        *,
        user_agent: str,
        timeout: int = 20,
        minimum_interval_seconds: float = 0.15,
    ) -> None:
        self.timeout = timeout
        self.minimum_interval_seconds = minimum_interval_seconds
        self._last_request_at = 0.0
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": user_agent,
                "Accept-Encoding": "gzip, deflate",
                "Accept": "application/json,text/html;q=0.9,*/*;q=0.8",
            }
        )

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_request_at
        delay = self.minimum_interval_seconds - elapsed
        if delay > 0:
            time.sleep(delay)

    def get_json(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self._throttle()
        response = self.session.get(
            url,
            params=params,
            timeout=self.timeout,
        )
        self._last_request_at = time.monotonic()
        response.raise_for_status()
        return response.json()

    def get_text(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> str:
        self._throttle()
        response = self.session.get(
            url,
            params=params,
            timeout=self.timeout,
        )
        self._last_request_at = time.monotonic()
        response.raise_for_status()
        return response.text
