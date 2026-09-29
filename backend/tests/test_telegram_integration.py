"""Reading -> outbox -> Telegram tests. All HTTP calls are mocked."""

from datetime import date, datetime, timedelta, timezone
import json
import uuid
from urllib.error import HTTPError

import pytest

import app as app_module
from app import database
from app.init_db import init_db
from app.services import telegram_notifier as notifier


class Response:
    status = 200
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def read(self, limit):
        return b'{"ok":true,"result":{"message_id":123}}'


@pytest.fixture
def system(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DATABASE_PATH", tmp_path / "notifications.db")
    monkeypatch.setattr(app_module, "load_dotenv", lambda *a, **kw: None)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    client = app_module.create_app().test_client()
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:mock-secret")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "123456")
    calls = []
    def opener(request, timeout):
        calls.append(json.loads(request.data))
        assert timeout == notifier.REQUEST_TIMEOUT_SECONDS
        return Response()
    monkeypatch.setattr(notifier, "urlopen", opener)
    assert client.post("/api/v1/foods", json={
        "food_id": "F1", "food_name": "Beef", "category": "MEAT",
        "inserted_at": date.today().isoformat(),
    }).status_code == 201
    assert client.post("/api/v1/foods/F1/activate").status_code == 200
    return client, notifier.TelegramNotificationWorker(), calls


def reading(temp=4, delay=1):
    return {
        "device_id": "FG-ESP32-01", "device_reading_id": str(uuid.uuid4()),
        "timestamp": (datetime.now(timezone.utc) - timedelta(seconds=delay)).isoformat(),
        "temperature_c": temp, "humidity_pct": 60, "gas_raw": 100,
        "door_open": False,
    }


def outbox():
    c = database.get_db_connection()
    try:
        return [dict(r) for r in c.execute("SELECT * FROM notification_outbox ORDER BY id")]
    finally:
        c.close()


def test_fresh_and_recovered_ingest_alone_do_not_notify(system):
    client, worker, calls = system
    for delay, status in [(1, "LIVE"), (60, "DELAYED"), (1200, "OFFLINE_RECOVERED")]:
        response = client.post("/api/v1/readings", json=reading(delay=delay))
        assert response.status_code == 201
        assert response.json["ingest_status"] == status
        assert response.json["freshness"]["status"] == "Fresh / Normal"
    assert worker.run_once() == 0
    assert calls == []


def test_alert_once_duplicate_and_twenty_unchanged_readings(system, caplog):
    client, worker, calls = system
    payload = reading(temp=13, delay=1200)
    first = client.post("/api/v1/readings", json=payload)
    assert first.status_code == 201
    assert first.json["ingest_status"] == "OFFLINE_RECOVERED"
    assert calls == []  # HTTP delivery never happens inside the route.
    assert worker.run_once() == 1
    assert outbox()[0]["delivery_status"] == "DELIVERED"
    duplicate = client.post("/api/v1/readings", json=payload)
    assert duplicate.status_code == 200 and duplicate.json["duplicate"] is True
    for _ in range(19):
        assert client.post("/api/v1/readings", json=reading(temp=13)).status_code == 201
    assert worker.run_once() == 0
    assert len(calls) == 1 and len(outbox()) == 1
    assert "[TELEGRAM SENT]" in caplog.text
    assert "reason=duplicate_replay" in caplog.text
    assert "reason=status_unchanged" in caplog.text
    assert "Temperature: 13" in calls[0]["text"]
    assert "parse_mode" not in calls[0]


def test_alert_recovery_and_alert_again(system):
    client, worker, calls = system
    for temp in (13, 4, 13):
        assert client.post("/api/v1/readings", json=reading(temp=temp)).status_code == 201
        assert worker.run_once() == 1
    assert [r["notification_type"] for r in outbox()] == [
        "FOOD_CHECK_FOOD", "FOOD_RECOVERED", "FOOD_CHECK_FOOD",
    ]
    assert len(calls) == 3


def test_use_soon_sends_warning(system):
    client, worker, calls = system
    c = database.get_db_connection()
    c.execute("UPDATE food_items SET expiry_date=?", (date.today().isoformat(),))
    c.commit()
    c.close()
    assert client.post("/api/v1/readings", json=reading()).json["freshness"]["status"] == "Use Soon"
    worker.run_once()
    assert len(calls) == 1 and "Use Soon" in calls[0]["text"]


@pytest.mark.parametrize("code", [None, 400, 401, 403, 429, 500])
def test_delivery_failure_does_not_break_reading_ack(system, monkeypatch, caplog, code):
    client, worker, calls = system
    def fail(request, timeout):
        if code is None:
            raise TimeoutError("secret URL must not be logged")
        raise HTTPError(request.full_url, code, "error", {}, None)
    monkeypatch.setattr(notifier, "urlopen", fail)
    payload = reading(temp=13)
    response = client.post("/api/v1/readings", json=payload)
    assert response.status_code == 201 and response.json["success"] is True
    worker.run_once()
    assert "[TELEGRAM FAILED]" in caplog.text
    assert outbox()[0]["last_error"] == ("timeout" if code is None else f"HTTP {code}")
    assert "123:mock-secret" not in caplog.text
    assert client.get("/api/v1/readings").json["count"] == 1
    assert client.post("/api/v1/readings", json=payload).status_code == 200
    assert len(outbox()) == 1


def test_missing_config_startup_is_disabled(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(database, "DATABASE_PATH", tmp_path / "disabled.db")
    monkeypatch.setattr(app_module, "load_dotenv", lambda *a, **kw: None)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "  ")
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    app = app_module.create_app()
    assert "telegram_notification_worker" not in app.extensions
    assert "[TELEGRAM DISABLED]" in caplog.text
    assert app.test_client().post("/api/v1/readings", json=reading()).status_code == 201


def test_outbox_migration_preserves_pending_and_is_repeatable(system):
    client, worker, calls = system
    client.post("/api/v1/readings", json=reading(temp=13))
    c = database.get_db_connection()
    c.execute("ALTER TABLE notification_outbox DROP COLUMN claim_token")
    c.execute("ALTER TABLE notification_outbox DROP COLUMN lease_until")
    c.commit()
    c.close()
    init_db()
    init_db()
    assert len(outbox()) == 1 and outbox()[0]["claim_token"] is None
    assert worker.run_once() == 1 and len(calls) == 1


def test_env_file_loaded_without_overriding_process_environment(tmp_path, monkeypatch):
    from dotenv import load_dotenv
    path = tmp_path / ".env"
    path.write_text("TELEGRAM_BOT_TOKEN=123:file-token\nTELEGRAM_CHAT_ID=100\n")
    monkeypatch.setattr(database, "DATABASE_PATH", tmp_path / "config.db")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:process-token")
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    monkeypatch.setattr(app_module, "load_dotenv", lambda *a, **kw: load_dotenv(path, **kw))
    started = []
    monkeypatch.setattr(notifier, "start_telegram_worker", lambda app: started.append(notifier.telegram_configured()))
    app_module.create_app()
    assert notifier.os.environ["TELEGRAM_BOT_TOKEN"] == "123:process-token"
    assert notifier.os.environ["TELEGRAM_CHAT_ID"] == "100"
    assert started == [True]
