"""Application settings and runtime configuration loading."""

from __future__ import annotations

import json
import os
import secrets
from hashlib import sha256
from pathlib import Path
from typing import Literal
from urllib.parse import quote_plus

from pydantic import BaseModel, ConfigDict, Field


class BlueBubblesSettings(BaseModel):
    host: str = ""
    password: str = ""
    ssl: bool = False
    send_method: Literal["private-api", "apple-script"] = "private-api"
    webhook_secret: str = ""


class ScheduleSettings(BaseModel):
    daily_prompt_time: str = "09:00"
    weekly_summary_day: Literal["mon", "tue", "wed", "thu", "fri", "sat", "sun"] = "mon"
    weekly_summary_time: str = "09:05"
    reminder_delay_minutes: int = 60
    reminder_window_minutes: int = 60


class PostgresSettings(BaseModel):
    host: str = ""
    port: int = 5432
    database: str = "Progress"
    username: str = "postgres"
    password: str = ""
    ssl_mode: Literal["disable", "allow", "prefer", "require"] = "prefer"

    def build_url(self) -> str:
        encoded_password = quote_plus(self.password)
        ssl_query = f"?sslmode={self.ssl_mode}" if self.ssl_mode else ""
        return (
            f"postgresql+psycopg://{self.username}:{encoded_password}"
            f"@{self.host}:{self.port}/{self.database}{ssl_query}"
        )


class DashboardSettings(BaseModel):
    username: str = "dmace"
    password: str = ""


class TargetSettings(BaseModel):
    weekly_drinks: int = 8
    weekly_dry_days: int = 4
    monday: int = 0
    tuesday: int = 0
    wednesday: int = 3
    thursday: int = 2
    friday: int = 0
    saturday: int = 3
    sunday: int = 0

    def by_weekday(self) -> dict[int, int]:
        return {
            0: self.monday,
            1: self.tuesday,
            2: self.wednesday,
            3: self.thursday,
            4: self.friday,
            5: self.saturday,
            6: self.sunday,
        }


class Settings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    time_zone: str = "America/New_York"
    recipient_address: str = ""
    bluebubbles: BlueBubblesSettings = Field(default_factory=BlueBubblesSettings)
    schedules: ScheduleSettings = Field(default_factory=ScheduleSettings)
    postgres: PostgresSettings = Field(default_factory=PostgresSettings)
    dashboard: DashboardSettings = Field(default_factory=DashboardSettings)
    targets: TargetSettings = Field(default_factory=TargetSettings)

    data_dir: str = "/data"
    config_path: str = "/data/options.json"
    database_url_override: str = ""
    supervisor_url: str = "http://supervisor"
    webhook_secret_resolved: str = ""

    @property
    def data_path(self) -> Path:
        return Path(self.data_dir)

    def ensure_webhook_secret(self) -> str:
        if self.webhook_secret_resolved:
            return self.webhook_secret_resolved

        if self.bluebubbles.webhook_secret:
            self.webhook_secret_resolved = self.bluebubbles.webhook_secret
            return self.webhook_secret_resolved

        secret_file = self.data_path / "webhook_secret.txt"
        if secret_file.exists():
            self.webhook_secret_resolved = secret_file.read_text(encoding="utf-8").strip()
            return self.webhook_secret_resolved

        generated = secrets.token_urlsafe(24)
        secret_file.parent.mkdir(parents=True, exist_ok=True)
        secret_file.write_text(generated, encoding="utf-8")
        self.webhook_secret_resolved = generated
        return generated

    def session_secret(self) -> str:
        digest = sha256(
            f"{self.ensure_webhook_secret()}::{self.dashboard.password}::{self.recipient_address}".encode("utf-8")
        )
        return digest.hexdigest()


def load_settings() -> Settings:
    config_path = Path(os.environ.get("DRINK_TRACKER_CONFIG_PATH", "/data/options.json"))
    raw: dict[str, object] = {}
    if config_path.exists():
        raw = json.loads(config_path.read_text(encoding="utf-8"))

    raw["config_path"] = str(config_path)
    raw["data_dir"] = os.environ.get("DRINK_TRACKER_DATA_DIR", "/data")
    raw["database_url_override"] = os.environ.get("DRINK_TRACKER_DATABASE_URL", "")
    raw["supervisor_url"] = os.environ.get(
        "DRINK_TRACKER_SUPERVISOR_URL",
        os.environ.get("SUPERVISOR_URL", "http://supervisor"),
    )
    settings = Settings.model_validate(raw)
    settings.ensure_webhook_secret()
    return settings

