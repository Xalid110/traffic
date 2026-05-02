"""
api/client.py — HTTP Client for External Signal Controller Integration
========================================================================
Posts turning‑movement data to an external traffic management system.
"""

from __future__ import annotations

import logging
from typing import Dict, Optional

import requests

from core.counter import MovementSnapshot

logger = logging.getLogger(__name__)


class TrafficAPIClient:
    """
    Simple HTTP client that pushes movement data to an external
    traffic management / SCADA endpoint.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:9000",
        api_key: Optional[str] = None,
        timeout: float = 5.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._session = requests.Session()
        if api_key:
            self._session.headers["Authorization"] = f"Bearer {api_key}"
        self._session.headers["Content-Type"] = "application/json"

    def push_counts(self, snap: MovementSnapshot) -> bool:
        """POST current counts to the external endpoint."""
        url = f"{self.base_url}/api/v1/counts"
        try:
            resp = self._session.post(
                url, json=snap.to_dict(), timeout=self.timeout,
            )
            resp.raise_for_status()
            logger.debug("Pushed counts to %s — %d", url, resp.status_code)
            return True
        except requests.RequestException as exc:
            logger.warning("Failed to push counts: %s", exc)
            return False

    def push_phase_recommendation(
        self, phases: Dict[str, dict],
    ) -> bool:
        """POST phase recommendations to the external endpoint."""
        url = f"{self.base_url}/api/v1/phases"
        try:
            resp = self._session.post(
                url, json=phases, timeout=self.timeout,
            )
            resp.raise_for_status()
            return True
        except requests.RequestException as exc:
            logger.warning("Failed to push phases: %s", exc)
            return False
