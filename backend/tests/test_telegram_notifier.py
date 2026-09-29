import json
import sqlite3

import pytest

from app.services import telegram_notifier as notifier


@pytest.fixture
def outbox_db(tmp_path):
    path = tmp_path / "telegram.db"
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("""CREATE TABLE notification_outbox (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_key TEXT NOT NULL UNIQUE,
        notification_type TEXT NOT NULL,
        food_id TEXT,
        reading_id INTEGER,
        payload_json TEXT NOT NULL,
        delivery_status TEXT NOT NULL DEFAULT 'PENDING',
        attempt_count INTEGER NOT NULL DEFAULT 0,
        last_error TEXT,
        created_at TEXT NOT NULL,
        delivered_at TEXT
        , claim_token TEXT, lease_until TEXT
    )""")
    connection.commit()
    connection.close()

    def connect():
        result = sqlite3.connect(path)
        result.row_factory = sqlite3.Row
        return result

    return connect


def add_row(connect, event_key, status="FOOD_CHECK_FOOD", attempts=0):
    connection = connect()
    connection.execute(
        """INSERT INTO notification_outbox
           (event_key, notification_type, food_id, payload_json,
            attempt_count, created_at)
           VALUES (?, ?, 'F1', ?, ?, '2026-09-28T12:00:00Z')""",
        (event_key, status, json.dumps({
            "notification_type": status,
            "food_name": "Beef",
            "category": "MEAT",
            "previous_status": "Fresh / Normal",
            "current_status": "Check Food",
            "freshness_reason": "test reason",
            "device_id": "D1",
            "reading_timestamp": "2026-09-28T12:00:00Z",
        }), attempts),
    )
    connection.commit()
    connection.close()


def rows(connect):
    connection = connect()
    try:
        return connection.execute(
            "SELECT * FROM notification_outbox ORDER BY id"
        ).fetchall()
    finally:
        connection.close()


class Response:
    status = 200
    def __init__(self, value):
        self.value = value

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, _limit):
        return json.dumps(self.value).encode()


def test_success_marks_delivered_and_message_uses_payload(monkeypatch):
    captured = {}

    def opener(request, timeout):
        captured["body"] = json.loads(request.data)
        captured["timeout"] = timeout
        return Response({"ok": True, "result": {"message_id": 1}})

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "secret-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat")
    payload = {
        "notification_type": "FOOD_USE_SOON", "food_name": "Beef",
        "category": "MEAT", "freshness_reason": "Near expiry",
        "device_id": "D1", "reading_timestamp": "now",
    }
    notifier.send_telegram_message(payload, opener=opener)
    assert "Beef" in captured["body"]["text"]
    assert "secret-token" not in captured["body"]["text"]
    assert captured["timeout"] == notifier.REQUEST_TIMEOUT_SECONDS


@pytest.mark.parametrize("response", [{"ok": False}, {"unexpected": True}, "not-json"])
def test_sender_rejects_bad_telegram_responses(monkeypatch, response):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat")

    def opener(_request, timeout):
        class RawResponse(Response):
            def read(self, _limit):
                return (json.dumps(response).encode()
                        if not isinstance(response, str)
                        else response.encode())
        return RawResponse(response)

    with pytest.raises(notifier.TelegramDeliveryError):
        notifier.send_telegram_message({
            "notification_type": "FOOD_CHECK_FOOD", "food_name": "Beef",
            "category": "MEAT", "freshness_reason": "reason",
            "device_id": "D1", "reading_timestamp": "now",
        }, opener=opener)


@pytest.mark.parametrize("error", [
    notifier.TelegramDeliveryError("network error"),
    notifier.TelegramDeliveryError("HTTP 500"),
])
def test_worker_retries_failures_and_eventually_marks_failed(
    outbox_db, monkeypatch, error
):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat")
    add_row(outbox_db, "k1")
    worker = notifier.TelegramNotificationWorker(
        connection_factory=outbox_db, sender=lambda _payload: (_ for _ in ()).throw(error),
        max_attempts=3,
    )
    worker.run_once()
    assert rows(outbox_db)[0]["delivery_status"] == "PENDING"
    assert rows(outbox_db)[0]["attempt_count"] == 1
    worker.run_once()
    worker.run_once()
    row = rows(outbox_db)[0]
    assert row["delivery_status"] == "FAILED"
    assert row["attempt_count"] == 3
    assert "token" not in row["last_error"]


def test_ok_false_malformed_response_and_delivered_not_resent(outbox_db, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat")
    add_row(outbox_db, "k1")
    calls = []

    def sender(payload):
        calls.append(payload)
        if len(calls) == 1:
            raise notifier.TelegramDeliveryError("Telegram API returned ok=false")

    worker = notifier.TelegramNotificationWorker(connection_factory=outbox_db, sender=sender)
    worker.run_once()
    assert rows(outbox_db)[0]["delivery_status"] == "PENDING"
    worker.run_once()
    assert rows(outbox_db)[0]["delivery_status"] == "DELIVERED"
    worker.run_once()
    assert len(calls) == 2


def test_missing_config_leaves_pending_and_does_not_crash(outbox_db, monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    add_row(outbox_db, "k1")
    worker = notifier.TelegramNotificationWorker(connection_factory=outbox_db)
    assert worker.run_once() == 0
    assert rows(outbox_db)[0]["delivery_status"] == "PENDING"


def test_oldest_first_and_batch_limit(outbox_db, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat")
    add_row(outbox_db, "k1")
    add_row(outbox_db, "k2")
    add_row(outbox_db, "k3")
    sent = []
    worker = notifier.TelegramNotificationWorker(
        connection_factory=outbox_db, sender=lambda payload: sent.append(payload), batch_size=2,
    )
    assert worker.run_once() == 2
    assert [row["delivery_status"] for row in rows(outbox_db)] == [
        "DELIVERED", "DELIVERED", "PENDING"
    ]
    assert len(sent) == 2


def test_pending_survives_new_worker_instance(outbox_db, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat")
    add_row(outbox_db, "k1")
    first = notifier.TelegramNotificationWorker(
        connection_factory=outbox_db,
        sender=lambda _payload: (_ for _ in ()).throw(notifier.TelegramDeliveryError("timeout")),
    )
    first.run_once()
    second = notifier.TelegramNotificationWorker(
        connection_factory=outbox_db, sender=lambda _payload: None,
    )
    second.run_once()
    assert rows(outbox_db)[0]["delivery_status"] == "DELIVERED"


def test_two_workers_cannot_send_same_pending_row(outbox_db, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat")
    add_row(outbox_db, "one-alert")
    entered, release = Event(), Event()
    sent = []
    def slow_sender(payload):
        sent.append(payload)
        entered.set()
        assert release.wait(5)
    first = notifier.TelegramNotificationWorker(outbox_db, slow_sender)
    second = notifier.TelegramNotificationWorker(outbox_db, lambda payload: sent.append(payload))
    with ThreadPoolExecutor(max_workers=1) as pool:
        task = pool.submit(first.run_once)
        try:
            assert entered.wait(5)
            assert second.run_once() == 0
            # Network wait holds no DB writer lock.
            connection = outbox_db()
            connection.execute("BEGIN IMMEDIATE")
            connection.rollback()
            connection.close()
        finally:
            release.set()
        assert task.result() == 1
    assert len(sent) == 1
    assert rows(outbox_db)[0]["attempt_count"] == 1


def test_expired_claim_retries_but_exhausted_claim_fails(outbox_db, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat")
    add_row(outbox_db, "retry", attempts=1)
    add_row(outbox_db, "exhausted", attempts=3)
    connection = outbox_db()
    connection.execute("UPDATE notification_outbox SET claim_token='old', lease_until='2000-01-01T00:00:00+00:00'")
    connection.commit()
    connection.close()
    sent = []
    notifier.TelegramNotificationWorker(outbox_db, lambda p: sent.append(p)).run_once()
    assert len(sent) == 1
    assert [row["delivery_status"] for row in rows(outbox_db)] == ["DELIVERED", "FAILED"]


def test_unexpected_exception_never_leaks_token(outbox_db, monkeypatch, caplog):
    secret = "123:SECRET_DO_NOT_LOG"
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", secret)
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat")
    add_row(outbox_db, "k1")
    def fail(payload):
        raise RuntimeError(f"URL https://api.telegram.org/bot{secret}/sendMessage failed")
    notifier.TelegramNotificationWorker(outbox_db, fail).run_once()
    assert rows(outbox_db)[0]["last_error"] == "unexpected delivery error"
    assert secret not in caplog.text


@pytest.mark.parametrize("value", [{"ok": True}, {"ok": True, "result": None},
                                  {"ok": True, "result": {"message_id": True}}])
def test_ok_without_message_result_is_not_success(monkeypatch, value):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat")
    with pytest.raises(notifier.TelegramDeliveryError, match="message result"):
        notifier.send_telegram_message({"notification_type": "FOOD_CHECK_FOOD"},
                                       opener=lambda *a, **kw: Response(value))


def test_plain_text_message_is_bounded_and_null_is_na():
    text = notifier.build_message({
        "notification_type": "FOOD_CHECK_FOOD", "food_name": "<beef>_*",
        "temperature_c": None, "humidity_pct": 0, "gas_raw": 0,
        "door_open": False, "freshness_reason": "x" * 10000,
    })
    assert "<beef>_*" in text
    assert "Temperature: N/A" in text
    assert "Humidity: 0" in text and "Gas: 0" in text
    assert "Door: Closed" in text
    assert len(text.encode("utf-16-le")) <= 8000


def test_http_failure_with_ok_body_is_not_success(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat")
    response = Response({"ok": True, "result": {"message_id": 1}})
    response.status = 503
    with pytest.raises(notifier.TelegramDeliveryError, match="HTTP 503"):
        notifier.send_telegram_message({"notification_type": "FOOD_CHECK_FOOD"},
                                       opener=lambda *args, **kwargs: response)
