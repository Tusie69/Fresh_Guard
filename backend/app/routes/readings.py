from flask import Blueprint, request

from app.database import get_db_connection
from app.services.freshness import evaluate_freshness


readings_bp = Blueprint("readings", __name__)


@readings_bp.post("/readings")
def create_reading():
    data = request.get_json()

    if not data:
        return {
            "success": False,
            "error": "INVALID_JSON",
            "message": "Request body must be JSON"
        }, 400

    required_fields = [
        "device_id",
        "timestamp",
        "temperature_c",
        "humidity_pct",
        "gas_raw",
        "door_open"
    ]

    missing_fields = [
        field for field in required_fields
        if field not in data
    ]

    if missing_fields:
        return {
            "success": False,
            "error": "MISSING_FIELDS",
            "message": "Missing required fields",
            "fields": missing_fields
        }, 400

    freshness_result = evaluate_freshness(
    temperature_c=data["temperature_c"],
    humidity_pct=data["humidity_pct"],
    gas_raw=data["gas_raw"],
    door_open=data["door_open"],
    open_duration_seconds=data.get("open_duration_seconds", 0)
)

    connection = get_db_connection()

    cursor = connection.execute(
    """
    INSERT INTO sensor_readings (
        device_id,
        timestamp,
        temperature_c,
        humidity_pct,
        gas_raw,
        door_open,
        open_duration_seconds
    )
    VALUES (?, ?, ?, ?, ?, ?, ?)
    """,
    (
        data["device_id"],
        data["timestamp"],
        data["temperature_c"],
        data["humidity_pct"],
        data["gas_raw"],
        int(data["door_open"]),
        data.get("open_duration_seconds", 0)
    )
)

    connection.commit()

    reading_id = cursor.lastrowid

    connection.close()

    return {
        "success": True,
        "message": "Reading saved",
        "reading_id": reading_id,
        "freshness": {
            "status": freshness_result.status.value,
            "reason": freshness_result.reason
        }
    }, 201

@readings_bp.get("/readings/latest")
def get_latest_reading():
    connection = get_db_connection()

    row = connection.execute(
        """
        SELECT
            id,
            device_id,
            timestamp,
            temperature_c,
            humidity_pct,
            gas_raw,
            door_open,
            open_duration_seconds,
            created_at
        FROM sensor_readings
        ORDER BY id DESC
        LIMIT 1
        """
    ).fetchone()

    connection.close()

    if row is None:
        return {
            "success": False,
            "error": "NO_DATA",
            "message": "No sensor readings found"
        }, 404

    data = dict(row)

    freshness_result = evaluate_freshness(
        temperature_c=data["temperature_c"],
        humidity_pct=data["humidity_pct"],
        gas_raw=data["gas_raw"],
        door_open=bool(data["door_open"]),
        open_duration_seconds=data["open_duration_seconds"]
    )

    data["freshness"] = {
        "status": freshness_result.status.value,
        "reason": freshness_result.reason
    }

    data["door_open"] = bool(data["door_open"])

    return {
        "success": True,
        "data": data
    }, 200

@readings_bp.get("/readings")
def get_readings():
    limit = request.args.get("limit", default=20, type=int)

    if limit < 1:
        return {
            "success": False,
            "error": "INVALID_LIMIT",
            "message": "Limit must be greater than 0"
        }, 400

    if limit > 100:
        limit = 100

    connection = get_db_connection()

    rows = connection.execute(
        """
        SELECT
            id,
            device_id,
            timestamp,
            temperature_c,
            humidity_pct,
            gas_raw,
            door_open,
            open_duration_seconds,
            created_at
        FROM sensor_readings
        ORDER BY id DESC
        LIMIT ?
        """,
        (limit,)
    ).fetchall()

    connection.close()

    data = []

    for row in rows:
        reading = dict(row)

        freshness_result = evaluate_freshness(
            temperature_c=reading["temperature_c"],
            humidity_pct=reading["humidity_pct"],
            gas_raw=reading["gas_raw"],
            door_open=bool(reading["door_open"]),
            open_duration_seconds=reading["open_duration_seconds"]
)

        reading["door_open"] = bool(reading["door_open"])

        reading["freshness"] = {
            "status": freshness_result.status.value,
            "reason": freshness_result.reason
        }

        data.append(reading)

    return {
        "success": True,
        "limit": limit,
        "count": len(data),
        "data": data
    }, 200
