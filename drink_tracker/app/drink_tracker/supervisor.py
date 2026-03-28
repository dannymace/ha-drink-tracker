"""Supervisor API helpers."""

from __future__ import annotations

import os
from typing import Any

import httpx


class SupervisorClient:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = os.environ.get("SUPERVISOR_TOKEN", "")

    def available(self) -> bool:
        return bool(self.token)

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}

    def discover_postgres_host(self) -> str:
        if not self.available():
            return ""

        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.get(f"{self.base_url}/addons", headers=self._headers())
                response.raise_for_status()
                addons: list[dict[str, Any]] = response.json().get("data", {}).get("addons", [])
                postgres_slug = ""
                for addon in addons:
                    slug = str(addon.get("slug", ""))
                    name = str(addon.get("name", ""))
                    if "postgres" in slug.lower() or "postgres" in name.lower():
                        postgres_slug = slug
                        break
                if not postgres_slug:
                    return ""

                detail = client.get(
                    f"{self.base_url}/addons/{postgres_slug}/info",
                    headers=self._headers(),
                )
                detail.raise_for_status()
                return str(detail.json().get("data", {}).get("hostname", ""))
        except httpx.HTTPError:
            return ""
