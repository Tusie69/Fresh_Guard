"""Channel-neutral outbox delivery through the Telegram Bot API."""

import json
import logging
import os
import re
import threading
import uuid
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.database import get_db_connection


LOGGER = logging.getLogger("app.telegram")
POLL_INTERVAL_SECONDS = 5
BATCH_SIZE = 10
MAX_ATTEMPTS = 3
REQUEST_TIMEOUT_SECONDS = 5
CLAIM_LEASE_SECONDS = 120
_WORKER_LOCK = threading.Lock()
_WORKER_INSTANCE = None


class TelegramDeliveryError(RuntimeError):
    """A safe, concise delivery failure that never contains credentials."""


def telegram_configured():
    values = [os.environ.get(key, "").strip()
              for key in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID")]
    return all(value and not any(c.isspace() for c in value) for value in values)


def _safe_error(error):
    # Never persist arbitrary exception strings (URLs can contain the token).
    value = str(error)
    if isinstance(error, TelegramDeliveryError) and (
        value in {"timeout", "network error", "malformed Telegram response",
                  "Telegram API returned ok=false", "missing Telegram message result",
                  "unsupported notification type", "invalid notification payload",
                  "Telegram notifications are unconfigured"}
        or re.fullmatch(r"HTTP [1-5][0-9]{2}", value)
    ):
        return value
    return "unexpected delivery error"


def _display(payload, key, limit=256):
    value = payload.get(key)
    return "N/A" if value is None else str(value)[:limit]


def build_message(payload):
    if not isinstance(payload, dict):
        raise TelegramDeliveryError("invalid notification payload")
    notification_type = payload.get("notification_type")
    food = payload.get("food_name") or payload.get("food_id") or "Unknown food"
    category = payload.get("category") or "Unknown"
    reason = payload.get("freshness_reason") or "No reason provided"
    device = payload.get("device_id") or "Unknown device"
    timestamp = payload.get("reading_timestamp") or "Unknown time"
    if notification_type == "FOOD_CHECK_FOOD":
        title = "🚨 FreshGuard — Check Food"
        status = "Status: Check Food"
    elif notification_type == "FOOD_USE_SOON":
        title = "⚠️ FreshGuard — Use Soon"
        status = "Status: Use Soon"
    elif notification_type == "FOOD_RECOVERED":
        title = "✅ FreshGuard — Recovered"
        status = (
            f"Previous: {payload.get('previous_status') or 'Unknown'}\n"
            f"Current: {payload.get('current_status') or 'Unknown'}"
        )
    else:
        raise TelegramDeliveryError("unsupported notification type")
    door = payload.get("door_open")
    door_text = "Open" if door is True else "Closed" if door is False else "N/A"
    text = (
        f"{title}\n\n"
        f"Food: {str(food)[:256]}\n"
        f"Category: {str(category)[:128]}\n"
        f"{status}\n"
        f"Temperature: {_display(payload, 'temperature_c')} C\n"
        f"Humidity: {_display(payload, 'humidity_pct')} %\n"
        f"Gas: {_display(payload, 'gas_raw')}\n"
        f"Door: {door_text}\n"
        f"Device: {str(device)[:256]}\n"
        f"Captured at: {str(timestamp)[:128]}\n"
        f"Reason: {str(reason)[:512]}"
    )
    # Plain text: no Markdown/HTML escaping needed. Bound UTF-16 length too.
    return text.encode("utf-16-le")[:8000].decode("utf-16-le", errors="ignore")


def send_telegram_message(payload, opener=None):
    return send_telegram_text(build_message(payload), opener=opener)


def send_telegram_text(text, opener=None):
    """Transport shared by outbox delivery and the explicit manual smoke test."""
    opener = opener or urlopen
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not telegram_configured():
        raise TelegramDeliveryError("Telegram notifications are unconfigured")
    body = json.dumps({"chat_id": chat_id, "text": text}).encode("utf-8")
    request = Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with opener(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            if not 200 <= response.status < 300:
                raise TelegramDeliveryError(f"HTTP {response.status}")
            raw = response.read(64 * 1024)
    except HTTPError as exc:
        raise TelegramDeliveryError(f"HTTP {exc.code}") from None
    except TimeoutError:
        raise TelegramDeliveryError("timeout") from None
    except (URLError, OSError):
        raise TelegramDeliveryError("network error") from None
    try:
        result = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise TelegramDeliveryError("malformed Telegram response") from None
    if not isinstance(result, dict) or result.get("ok") is not True:
        raise TelegramDeliveryError("Telegram API returned ok=false")
    message = result.get("result")
    if not isinstance(message, dict) or type(message.get("message_id")) is not int:
        raise TelegramDeliveryError("missing Telegram message result")
    return result


def _utc_now():
    return datetime.now(timezone.utc).isoformat()


class TelegramNotificationWorker:
    def __init__(self, connection_factory=None, sender=None,
                 poll_interval=POLL_INTERVAL_SECONDS, batch_size=BATCH_SIZE,
                 max_attempts=MAX_ATTEMPTS):
        self.connection_factory = connection_factory or get_db_connection
        self.sender = sender or send_telegram_message
        self.poll_interval = poll_interval
        self.batch_size = batch_size
        self.max_attempts = max_attempts
        self._stop = threading.Event()
        self._thread = None

    def start(self):
        if self._thread and self._thread.is_alive():
            return self._thread
        self._thread = threading.Thread(
            target=self.run, name="freshguard-telegram", daemon=True,
        )
        self._thread.start()
        return self._thread

    def stop(self):
        self._stop.set()

    def run(self):
        while not self._stop.is_set():
            try:
                self.run_once()
            except Exception:
                LOGGER.error("[TELEGRAM FAILED] reason=worker_cycle_failure; pending lease will expire")
            self._stop.wait(self.poll_interval)

    def run_once(self):
        if not telegram_configured():
            LOGGER.info("[TELEGRAM DISABLED] missing/blank or malformed config")
            return 0
        connection = self.connection_factory()
        try:
            # Crashes consume an attempt too; do not leave the final claim
            # PENDING forever after its lease expires.
            expired = connection.execute(
                """UPDATE notification_outbox SET delivery_status='FAILED',
                       claim_token=NULL, lease_until=NULL, last_error='delivery outcome unknown'
                   WHERE delivery_status='PENDING' AND attempt_count >= ?
                     AND (lease_until IS NULL OR lease_until <= ?)""",
                (self.max_attempts, _utc_now()),
            ).rowcount
            connection.commit()
            if expired:
                LOGGER.warning("[TELEGRAM FAILED] reason=attempt_limit_after_expired_claim count=%s", expired)
            rows = connection.execute(
                """SELECT * FROM notification_outbox
                   WHERE delivery_status = 'PENDING'
                     AND attempt_count < ?
                     AND (lease_until IS NULL OR lease_until <= ?)
                   ORDER BY id LIMIT ?""",
                (self.max_attempts, _utc_now(), self.batch_size),
            ).fetchall()
            processed = 0
            for row in rows:
                row = self._claim(connection, row["id"])
                if row is None:
                    continue
                processed += 1
                try:
                    payload = json.loads(row["payload_json"])
                    self.sender(payload)
                except Exception as exc:
                    self._record_failure(connection, row, _safe_error(exc))
                else:
                    self._record_success(connection, row)
            return processed
        finally:
            connection.close()

    def _claim(self, connection, row_id):
        now = _utc_now()
        expires = (datetime.fromisoformat(now) + timedelta(seconds=CLAIM_LEASE_SECONDS)).isoformat()
        token = str(uuid.uuid4())
        updated = connection.execute(
            """UPDATE notification_outbox SET claim_token=?, lease_until=?,
                   attempt_count=attempt_count+1
               WHERE id=? AND delivery_status='PENDING' AND attempt_count < ?
                 AND (lease_until IS NULL OR lease_until <= ?)""",
            (token, expires, row_id, self.max_attempts, now),
        ).rowcount
        row = connection.execute("SELECT * FROM notification_outbox WHERE id=?", (row_id,)).fetchone() if updated else None
        connection.commit()  # Never hold the SQLite writer lock during HTTP.
        return row

    def _context(self, row):
        try:
            payload = json.loads(row["payload_json"])
            if not isinstance(payload, dict):
                return "payload=invalid"
            return "device=%r reading_id=%r status=%r" % (
                _display(payload, "device_id"),
                payload.get("device_reading_id") or row["reading_id"],
                _display(payload, "current_status"),
            )
        except (ValueError, TypeError):
            return "payload=invalid"

    def _record_success(self, connection, row):
        updated = connection.execute(
            """UPDATE notification_outbox
               SET delivery_status = 'DELIVERED', delivered_at = ?, last_error = NULL,
                   claim_token=NULL, lease_until=NULL
               WHERE id = ? AND delivery_status = 'PENDING' AND claim_token=?""",
            (_utc_now(), row["id"], row["claim_token"]),
        ).rowcount
        connection.commit()
        if updated:
            LOGGER.info("[TELEGRAM SENT] outbox_id=%s %s chat=***", row["id"], self._context(row))
        else:
            LOGGER.warning("[TELEGRAM FAILED] outbox_id=%s reason=claim_lost outcome=unknown", row["id"])

    def _record_failure(self, connection, row, error):
        attempt_count = row["attempt_count"]
        status = "FAILED" if attempt_count >= self.max_attempts else "PENDING"
        connection.execute(
            """UPDATE notification_outbox
               SET delivery_status = ?, last_error = ?, claim_token=NULL, lease_until=NULL
               WHERE id = ? AND delivery_status = 'PENDING' AND claim_token=?""",
            (status, error[:200], row["id"], row["claim_token"]),
        )
        connection.commit()
        LOGGER.warning("[TELEGRAM FAILED] outbox_id=%s %s error=%s attempt=%s delivery_status=%s",
                       row["id"], self._context(row), error, attempt_count, status)


def start_telegram_worker(app=None):
    global _WORKER_INSTANCE
    if not telegram_configured():
        LOGGER.info("[TELEGRAM DISABLED] missing/blank or malformed config")
        return None
    with _WORKER_LOCK:
        if (_WORKER_INSTANCE is None or _WORKER_INSTANCE._thread is None
                or not _WORKER_INSTANCE._thread.is_alive()):
            _WORKER_INSTANCE = TelegramNotificationWorker()
            _WORKER_INSTANCE.start()
        worker = _WORKER_INSTANCE
    if app is not None:
        app.extensions["telegram_notification_worker"] = worker
    return worker
