from datetime import datetime
import sqlite3

from flask import Blueprint, request

from app.database import get_db_connection


events_bp = Blueprint("events", __name__)


@events_bp.get("/events")
def list_events():
    limit = request.args.get("limit", default=50, type=int)
    event_type = request.args.get("event_type")
    if limit < 1:
        return {
            "success": False,
            "error": "INVALID_LIMIT",
            "message": "Limit must be greater than 0",
        }, 400
    limit = min(limit, 100)
    if event_type is not None and not event_type.strip():
        return {
            "success": False,
            "error": "INVALID_EVENT_TYPE",
            "message": "event_type must not be empty",
        }, 400
    connection = get_db_connection()
    try:
        event_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(events)")
        }
        optional_select = ", door_open" if "door_open" in event_columns else ", 0 AS door_open"
        optional_select += (
            ", open_duration_seconds" if "open_duration_seconds" in event_columns
            else ", 0 AS open_duration_seconds"
        )
        select_sql = (
            "SELECT id, event_id, device_id, timestamp, event_type, payload, "
            "created_at" + optional_select + " FROM events"
        )
        if event_type:
            rows = connection.execute(
                select_sql + " WHERE event_type = ? ORDER BY id DESC LIMIT ?",
                (event_type.strip(), limit),
            ).fetchall()
        else:
            rows = connection.execute(
                select_sql + " ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return {"success": True, "events": [dict(row) for row in rows]}, 200
    finally:
        connection.close()


def _valid_timestamp(value):
    if not isinstance(value, str) or not value.strip():
        return False
    if not any(separator in value for separator in ("T", "t", " ")):
        return False
    try:
        datetime.fromisoformat(value)
    except ValueError:
        return False
    return True


@events_bp.post("/events")
def create_event():
    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return {
            "success": False,
            "error": "INVALID_JSON",
            "message": "Request body must be a JSON object"
        }, 400

    required_fields = ("event_id", "device_id", "timestamp", "event_type")

    missing_fields = [
        field for field in required_fields
        if field not in data
    ]

    if missing_fields:
        return {
            "success": False,
            "error": "MISSING_FIELDS",
            "fields": missing_fields
        }, 400

    for field in ("event_id", "device_id", "event_type"):
        value = data[field]
        if not isinstance(value, str) or not value.strip():
            return {
                "success": False,
                "error": "INVALID_FIELD",
                "message": f"{field} must be a non-empty string",
                "field": field
            }, 400

    if not _valid_timestamp(data["timestamp"]):
        return {
            "success": False,
            "error": "INVALID_TIMESTAMP",
            "message": "timestamp must be a valid ISO datetime"
        }, 400

    connection = get_db_connection()

    try:
        duplicate = connection.execute(
            "SELECT 1 FROM events WHERE event_id = ?",
            (data["event_id"],)
        ).fetchone()
        if duplicate:
            return {
                "success": True,
                "message": "Event already exists",
                "event_id": data["event_id"],
                "duplicate": True
            }, 200

        # The project has legacy events schemas with different optional columns.
        # Supply safe defaults only for columns present in the active database.
        event_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(events)")
        }
        columns = ["event_id", "device_id", "timestamp", "event_type", "payload"]
        values = [
            data["event_id"],
            data["device_id"],
            data["timestamp"],
            data["event_type"],
            str(data.get("payload", {})),
        ]
        if "door_open" in event_columns:
            columns.append("door_open")
            values.append(0)
        if "open_duration_seconds" in event_columns:
            columns.append("open_duration_seconds")
            values.append(0)

        column_sql = ", ".join(columns)
        placeholders = ", ".join("?" for _ in values)
        connection.execute(
            f"INSERT INTO events ({column_sql}) VALUES ({placeholders})",
            values
        )

        connection.commit()

        return {
            "success": True,
            "message": "Event saved",
            "event_id": data["event_id"],
            "duplicate": False
        }, 201

    except sqlite3.IntegrityError:
        connection.rollback()
        duplicate = connection.execute(
            "SELECT 1 FROM events WHERE event_id = ?",
            (data["event_id"],)
        ).fetchone()
        if duplicate:
            return {
                "success": True,
                "message": "Event already exists",
                "event_id": data["event_id"],
                "duplicate": True
            }, 200
        return {
            "success": False,
            "error": "INVALID_EVENT",
            "message": "Event could not be saved with the supplied data"
        }, 400

    finally:
        connection.close()
