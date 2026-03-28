"""BlueBubbles API client."""

from __future__ import annotations

from typing import Iterable

import httpx


class BlueBubblesClient:
    def __init__(self, host: str, password: str, verify_ssl: bool, method: str) -> None:
        self.host = host.rstrip("/")
        self.password = password
        self.verify_ssl = verify_ssl
        self.method = method

    def send_to_addresses(self, addresses: Iterable[str], message: str) -> None:
        payload = {
            "addresses": [address.strip() for address in addresses if address.strip()],
            "message": message,
            "method": self.method,
        }
        with httpx.Client(timeout=20.0, verify=self.verify_ssl) as client:
            response = client.post(
                f"{self.host}/api/v1/chat/new",
                params={"password": self.password},
                json=payload,
            )
            response.raise_for_status()

    def send_to_chat_guid(self, chat_guid: str, text: str) -> None:
        payload = {"chatGuid": chat_guid, "text": text, "method": self.method}
        with httpx.Client(timeout=20.0, verify=self.verify_ssl) as client:
            response = client.post(
                f"{self.host}/api/v1/message/text",
                params={"password": self.password},
                json=payload,
                headers={"Content-Type": "application/json"},
            )
            response.raise_for_status()

