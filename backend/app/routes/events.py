from flask import Blueprint, request
from sqlite3 import IntegrityError

from app.database import get_db_connection


events_bp = Blueprint("events", __name__)


@events_bp.post("/events")
def create_event():
    data = request.get_json()

    required_fields = [
        "event_id",
        "device_id",
        "timestamp",
        "event_type"
    ]

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

    connection = get_db_connection()

    try:
        connection.execute(
            """
            INSERT INTO events (
                event_id,
                device_id,
                timestamp,
                event_type,
                payload
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                data["event_id"],
                data["device_id"],
                data["timestamp"],
                data["event_type"],
                str(data.get("payload", {}))
            )
        )

        connection.commit()

        return {
            "success": True,
            "message": "Event saved",
            "event_id": data["event_id"],
            "duplicate": False
        }, 201

    except IntegrityError:
        connection.rollback()

        return {
            "success": True,
            "message": "Event already exists",
            "event_id": data["event_id"],
            "duplicate": True
        }, 200

    finally:
        connection.close()