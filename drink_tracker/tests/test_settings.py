from __future__ import annotations

import json

from drink_tracker.settings import PERSISTED_SECRETS_FILE, PostgresSettings, load_settings


def test_load_settings_reuses_persisted_secret_fields(tmp_path, monkeypatch) -> None:
    config_path = tmp_path / "options.json"
    config_path.write_text(
        json.dumps(
            {
                "recipient_address": "dmace@icloud.com",
                "bluebubbles": {"host": "http://192.168.0.163:1234", "password": ""},
                "postgres": {"host": "db21ed7f_postgres_latest", "password": ""},
                "dashboard": {"username": "dmace", "password": ""},
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / PERSISTED_SECRETS_FILE).write_text(
        json.dumps(
            {
                "bluebubbles": {"password": "blue-secret"},
                "postgres": {"password": "pg-secret"},
                "dashboard": {"password": "dash-secret"},
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("DRINK_TRACKER_CONFIG_PATH", str(config_path))
    monkeypatch.setenv("DRINK_TRACKER_DATA_DIR", str(tmp_path))

    settings = load_settings()

    assert settings.bluebubbles.password == "blue-secret"
    assert settings.postgres.password == "pg-secret"
    assert settings.dashboard.password == "dash-secret"


def test_load_settings_persists_latest_secret_values(tmp_path, monkeypatch) -> None:
    config_path = tmp_path / "options.json"
    config_path.write_text(
        json.dumps(
            {
                "recipient_address": "dmace@icloud.com",
                "bluebubbles": {"host": "http://192.168.0.163:1234", "password": "blue-secret"},
                "postgres": {"host": "db21ed7f_postgres_latest", "password": "pg-secret"},
                "dashboard": {"username": "dmace", "password": "dash-secret"},
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("DRINK_TRACKER_CONFIG_PATH", str(config_path))
    monkeypatch.setenv("DRINK_TRACKER_DATA_DIR", str(tmp_path))

    load_settings()

    persisted = json.loads((tmp_path / PERSISTED_SECRETS_FILE).read_text(encoding="utf-8"))
    assert persisted["bluebubbles"]["password"] == "blue-secret"
    assert persisted["postgres"]["password"] == "pg-secret"
    assert persisted["dashboard"]["password"] == "dash-secret"


def test_postgres_build_url_normalizes_host_with_embedded_port_mapping() -> None:
    settings = PostgresSettings(
        host="db21ed7f_postgres_latest:5432:5432",
        port=5432,
        database="Progress",
        username="postgres",
        password="homeassistant",
        ssl_mode="disable",
    )

    assert settings.normalized_endpoint() == ("db21ed7f-postgres-latest", 5432)
    assert settings.build_url() == "postgresql+psycopg://postgres:homeassistant@db21ed7f-postgres-latest:5432/Progress?sslmode=disable"
