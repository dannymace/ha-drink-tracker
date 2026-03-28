from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.exc import OperationalError

from drink_tracker.models import DailyEntry, MessageRun
from drink_tracker import service as service_module
from drink_tracker.service import DrinkTrackerService
from drink_tracker.settings import Settings


class FakeBlueBubblesClient:
    def __init__(self) -> None:
        self.address_messages: list[tuple[list[str], str]] = []
        self.chat_messages: list[tuple[str, str]] = []
        self.fail_chat_messages = False

    def send_to_addresses(self, addresses, message) -> None:
        self.address_messages.append((list(addresses), message))

    def send_to_chat_guid(self, chat_guid: str, text: str) -> None:
        if self.fail_chat_messages:
            raise RuntimeError("chat send failed")
        self.chat_messages.append((chat_guid, text))


def make_service(tmp_path: Path) -> tuple[DrinkTrackerService, FakeBlueBubblesClient]:
    settings = Settings.model_validate(
        {
            "time_zone": "America/New_York",
            "recipient_address": "dmace@icloud.com",
            "bluebubbles": {
                "host": "http://192.168.0.163:1234",
                "password": "secret",
                "ssl": False,
                "send_method": "private-api",
            },
            "postgres": {
                "host": "localhost",
                "port": 5432,
                "database": "Progress",
                "username": "postgres",
                "password": "homeassistant",
                "ssl_mode": "disable",
            },
            "dashboard": {"username": "dmace", "password": "secret"},
            "database_url_override": f"sqlite+pysqlite:///{tmp_path / 'drink-tracker.sqlite3'}",
            "data_dir": str(tmp_path),
        }
    )
    service = DrinkTrackerService(settings)
    service.start()
    fake_client = FakeBlueBubblesClient()
    service.client = fake_client
    return service, fake_client


def test_daily_prompt_creates_pending_run(tmp_path: Path) -> None:
    service, fake_client = make_service(tmp_path)
    now = datetime(2026, 3, 28, 9, 0, tzinfo=ZoneInfo("America/New_York"))

    result = service.send_daily_prompt(now=now)

    assert result["status"] == "sent"
    assert fake_client.address_messages
    with service._session() as session:
        run = session.scalar(select(MessageRun))
        entry = session.scalar(select(DailyEntry))
        assert run is not None
        assert entry is not None
        assert run.tracked_date.isoformat() == "2026-03-27"
        assert entry.entry_date.isoformat() == "2026-03-27"
        assert entry.status == "pending"


def test_webhook_numeric_reply_is_stored_and_confirmed(tmp_path: Path) -> None:
    service, fake_client = make_service(tmp_path)
    now = datetime(2026, 3, 28, 9, 0, tzinfo=ZoneInfo("America/New_York"))
    service.send_daily_prompt(now=now)

    payload = {
        "type": "new-message",
        "data": {
            "isFromMe": False,
            "text": "4",
            "chats": [{"guid": "chat-guid-1"}],
            "handle": {"address": "dmace@icloud.com"},
        },
    }

    result = service.process_bluebubbles_webhook(payload)

    assert result["status"] == "stored"
    assert fake_client.chat_messages
    with service._session() as session:
        entry = session.scalar(select(DailyEntry))
        run = session.scalar(select(MessageRun))
        assert entry is not None
        assert run is not None
        assert entry.drinks == 4
        assert entry.status == "tracked"
        assert run.state == "answered"


def test_weekly_summary_sends_previous_week_every_time(tmp_path: Path) -> None:
    service, fake_client = make_service(tmp_path)

    first = service.send_weekly_summary(now=datetime(2026, 3, 28, 9, 5, tzinfo=ZoneInfo("America/New_York")))
    second = service.send_weekly_summary(now=datetime(2026, 3, 28, 9, 6, tzinfo=ZoneInfo("America/New_York")))

    assert first["status"] == "sent"
    assert second["status"] == "sent"
    assert first["week_start"] == "2026-03-16"
    assert first["week_end"] == "2026-03-22"
    assert len(fake_client.address_messages) == 2
    weekly_message = fake_client.address_messages[-1][1]
    assert "Drinks       →" in weekly_message
    assert "Dry Days     →" in weekly_message
    assert "Tracked Days →" in weekly_message
    assert "MON →" in weekly_message
    assert "│" in weekly_message
    with service._session() as session:
        summaries = session.scalars(select(service_module.WeeklySummary).order_by(service_module.WeeklySummary.week_start)).all()
        assert len(summaries) == 1
        assert summaries[0].summary_sent_at is not None


def test_daily_prompt_reports_existing_answered_run(tmp_path: Path) -> None:
    service, fake_client = make_service(tmp_path)
    now = datetime(2026, 3, 28, 9, 0, tzinfo=ZoneInfo("America/New_York"))
    service.send_daily_prompt(now=now)

    payload = {
        "type": "new-message",
        "data": {
            "isFromMe": False,
            "text": "5",
            "chats": [{"guid": "chat-guid-1"}],
            "handle": {"address": "dmace@icloud.com"},
        },
    }
    service.process_bluebubbles_webhook(payload)
    sent_before = len(fake_client.address_messages)

    result = service.send_daily_prompt(now=now)

    assert result["status"] == "skipped"
    assert result["reason"] == "already answered"
    assert result["tracked_date"] == "2026-03-27"
    assert result["drinks"] == 5
    assert len(fake_client.address_messages) == sent_before


def test_webhook_falls_back_to_address_when_chat_confirmation_fails(tmp_path: Path) -> None:
    service, fake_client = make_service(tmp_path)
    fake_client.fail_chat_messages = True
    now = datetime(2026, 3, 28, 9, 0, tzinfo=ZoneInfo("America/New_York"))
    service.send_daily_prompt(now=now)

    payload = {
        "type": "new-message",
        "data": {
            "isFromMe": False,
            "text": "5",
            "chats": [{"guid": "chat-guid-1"}],
            "handle": {"address": "dmace@icloud.com"},
        },
    }

    result = service.process_bluebubbles_webhook(payload)

    assert result["status"] == "stored"
    assert result["confirmation_delivery"] == "address-fallback"
    assert fake_client.address_messages
    with service._session() as session:
        entry = session.scalar(select(DailyEntry))
        run = session.scalar(select(MessageRun))
        assert entry is not None
        assert run is not None
        assert entry.drinks == 5
        assert entry.status == "tracked"
        assert run.state == "answered"


def test_start_keeps_service_alive_on_database_connection_error(tmp_path: Path, monkeypatch) -> None:
    settings = Settings.model_validate(
        {
            "time_zone": "America/New_York",
            "recipient_address": "dmace@icloud.com",
            "bluebubbles": {
                "host": "http://192.168.0.163:1234",
                "password": "secret",
                "ssl": False,
                "send_method": "private-api",
            },
            "postgres": {
                "host": "homeassistant.local",
                "port": 5432,
                "database": "Progress",
                "username": "postgres",
                "password": "homeassistant",
                "ssl_mode": "disable",
            },
            "dashboard": {"username": "dmace", "password": "secret"},
            "data_dir": str(tmp_path),
        }
    )

    def raise_operational_error(*_args, **_kwargs):
        raise OperationalError("statement", {}, Exception("connection refused"))

    monkeypatch.setattr(service_module, "create_session_factory", raise_operational_error)

    service = DrinkTrackerService(settings)
    service.start()

    assert service.session_factory is None
    assert service.client is not None
    assert service.health()["status"] == "error"
    assert any("Use the Postgres add-on hostname" in error for error in service.config_errors)
