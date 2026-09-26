from datetime import date, datetime, timezone
import json
import math
import sqlite3
import uuid

from flask import Blueprint, request

from app.database import get_db_connection
from app.services.freshness import evaluate_freshness
from app.services.gas_anomaly import (
    get_gas_anomaly_state,
    is_valid_gas_reading,
    update_gas_anomaly_state,
)
from app.services.qr_category import (
    QR_CATEGORY_MAPPING,
    category_for_qr_code,
    is_supported_category,
)
from app.services.temperature_exposure import (
    TEMPERATURE_EXPOSURE_LIMIT_SECONDS,
    update_temperature_exposure,
)
from app.services.sensor_fault import update_sensor_fault_states
from app.services.reading_protocol import (
    COMPACT_OPTIONAL_FIELDS,
    COMPACT_REQUIRED_FIELDS,
    ReadingProtocolError,
    decode_compact_reading,
)


readings_bp = Blueprint("readings", __name__)


def _is_finite_sensor_number(value):
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    try:
        return math.isfinite(value)
    except (OverflowError, TypeError):
        return False


def _is_valid_timestamp(value):
    if not isinstance(value, str) or not value.strip():
        return False
    if not any(separator in value for separator in ("T", "t", " ")):
        return False
    try:
        datetime.fromisoformat(value)
    except ValueError:
        return False
    return True


def _persist_gas_transition_event(connection, data, food_id, previous_active,
                                  current_active, reading_id):
    """Persist one gas state transition alongside the reading transaction."""
    if previous_active == current_active:
        return
    if not current_active and not is_valid_gas_reading(data["gas_raw"]):
        return

    event_type = (
        "GAS_ANOMALY_STARTED" if current_active
        else "GAS_ANOMALY_RECOVERED"
    )
    state = get_gas_anomaly_state(connection, data["device_id"], food_id)
    baseline = state["baseline"] if state is not None else None
    payload = {"gas_raw": data["gas_raw"]}
    if baseline is not None:
        payload["baseline"] = baseline
        if baseline > 0:
            payload["deviation"] = (data["gas_raw"] - baseline) / baseline
    if current_active and state is not None:
        payload["consecutive_readings"] = state["consecutive_anomaly_count"]

    identity = data.get("device_reading_id") or str(reading_id)
    event_id = str(uuid.uuid5(
        uuid.NAMESPACE_URL,
        f"freshguard:gas:{data['device_id']}:{identity}:{event_type}",
    ))
    columns = {
        row[1] for row in connection.execute("PRAGMA table_info(events)")
    }
    names = ["event_id", "device_id", "timestamp", "event_type", "payload"]
    values = [
        event_id, data["device_id"], data["timestamp"], event_type, str(payload)
    ]
    if "door_open" in columns:
        names.append("door_open")
        values.append(0)
    if "open_duration_seconds" in columns:
        names.append("open_duration_seconds")
        values.append(0)
    connection.execute(
        f"INSERT INTO events ({', '.join(names)}) "
        f"VALUES ({', '.join('?' for _ in values)})",
        values,
    )


def _persist_temperature_exposure_event(connection, data, reading_id,
                                         exposure_seconds):
    event_type = "TEMPERATURE_EXPOSURE_EXCEEDED"
    identity = data.get("device_reading_id") or str(reading_id)
    event_id = str(uuid.uuid5(
        uuid.NAMESPACE_URL,
        f"freshguard:temperature:{data['device_id']}:{identity}:{event_type}",
    ))
    payload = {
        "temperature": data["temperature_c"],
        "exposure_seconds": exposure_seconds,
        "threshold_seconds": TEMPERATURE_EXPOSURE_LIMIT_SECONDS,
    }
    columns = {
        row[1] for row in connection.execute("PRAGMA table_info(events)")
    }
    names = ["event_id", "device_id", "timestamp", "event_type", "payload"]
    values = [event_id, data["device_id"], data["timestamp"], event_type, str(payload)]
    if "door_open" in columns:
        names.append("door_open")
        values.append(0)
    if "open_duration_seconds" in columns:
        names.append("open_duration_seconds")
        values.append(0)
    connection.execute(
        f"INSERT INTO events ({', '.join(names)}) "
        f"VALUES ({', '.join('?' for _ in values)})",
        values,
    )


def _persist_sensor_fault_event(connection, data, reading_id, transition):
    identity = data.get("device_reading_id") or str(reading_id)
    logical_identity = json.dumps(
        [
            data["device_id"],
            transition["food_id"],
            transition["sensor_name"],
            identity,
            transition["event_type"],
        ],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    event_id = str(uuid.uuid5(
        uuid.NAMESPACE_URL, f"freshguard:sensor-fault:{logical_identity}"
    ))
    payload = {
        "sensor_name": transition["sensor_name"],
        "sensor_value": transition["sensor_value"],
        "food_id": transition["food_id"],
    }
    columns = {
        row[1] for row in connection.execute("PRAGMA table_info(events)")
    }
    names = ["event_id", "device_id", "timestamp", "event_type", "payload"]
    values = [
        event_id,
        data["device_id"],
        data["timestamp"],
        transition["event_type"],
        str(payload),
    ]
    if "door_open" in columns:
        names.append("door_open")
        values.append(0)
    if "open_duration_seconds" in columns:
        names.append("open_duration_seconds")
        values.append(0)
    connection.execute(
        f"INSERT INTO events ({', '.join(names)}) "
        f"VALUES ({', '.join('?' for _ in values)})",
        values,
    )


def _normalize_device_reading_id(value):
    if not isinstance(value, str):
        return None
    try:
        parsed = uuid.UUID(value)
    except (ValueError, AttributeError):
        return None
    if parsed.version != 4 or str(parsed) != value.lower():
        return None
    return str(parsed)


def _reading_payload_matches(row, payload):
    return all(
        row[field] == value
        for field, value in payload.items()
    )


def _reading_response(row, duplicate):
    return {
        "success": True,
        "message": "Reading already exists" if duplicate else "Reading saved",
        "reading_id": row["id"],
        "device_reading_id": row["device_reading_id"],
        "duplicate": duplicate,
        "freshness": {
            "status": row["freshness_status"],
            "reason": row["freshness_reason"]
        }
    }


def _parse_food_date(value, field_name, required=False):
    if value is None:
        if required:
            return None, f"{field_name} is required"
        return None, None

    if not isinstance(value, str):
        return None, f"{field_name} must use YYYY-MM-DD format"

    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        return None, f"{field_name} must use YYYY-MM-DD format"

    if parsed.isoformat() != value:
        return None, f"{field_name} must use YYYY-MM-DD format"

    return value, None


def _food_dict(row):
    return dict(row)


def _next_generated_food_id(connection):
    sequence = connection.execute(
        "SELECT seq FROM sqlite_sequence WHERE name = 'food_items'"
    ).fetchone()
    largest_id = connection.execute(
        "SELECT COALESCE(MAX(id), 0) FROM food_items"
    ).fetchone()[0]
    next_id = max(largest_id, sequence[0] if sequence is not None else 0) + 1

    while True:
        food_id = f"FG-FOOD-{next_id:05d}"
        duplicate = connection.execute(
            "SELECT 1 FROM food_items WHERE food_id = ?", (food_id,)
        ).fetchone()
        if duplicate is None:
            return next_id, food_id
        next_id += 1


@readings_bp.post("/foods")
def create_food():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return {
            "success": False,
            "error": "INVALID_JSON",
            "message": "Request body must be a JSON object"
        }, 400

    required_fields = ("food_name", "inserted_at")
    missing_fields = [field for field in required_fields if field not in data]
    if "food_id" not in data and "qr_code" not in data:
        missing_fields.append("food_id")
    if "category" not in data and "qr_code" not in data:
        missing_fields.append("category")
    if missing_fields:
        return {
            "success": False,
            "error": "MISSING_FIELDS",
            "message": "Missing required fields",
            "fields": missing_fields
        }, 400

    string_fields = ["food_name"]
    if "food_id" in data:
        string_fields.append("food_id")
    if "category" in data:
        string_fields.append("category")
    for field in string_fields:
        value = data[field]
        if not isinstance(value, str) or not value.strip():
            return {
                "success": False,
                "error": "INVALID_FIELD",
                "message": f"{field} must be a non-empty string",
                "field": field
            }, 400
        data[field] = value.strip()

    if "qr_code" in data:
        qr_category = category_for_qr_code(data["qr_code"])
        if qr_category is None:
            supported_codes = ", ".join(QR_CATEGORY_MAPPING)
            return {
                "success": False,
                "error": "INVALID_QR_CODE",
                "message": f"qr_code must be one of: {supported_codes}",
                "field": "qr_code",
            }, 400
        if "category" in data and data["category"] != qr_category:
            return {
                "success": False,
                "error": "QR_CATEGORY_CONFLICT",
                "message": "category does not match qr_code",
                "field": "category",
            }, 400
        data["category"] = qr_category

    if not is_supported_category(data["category"]):
        return {
            "success": False,
            "error": "INVALID_CATEGORY",
            "message": "category must be one of the supported food categories",
            "field": "category",
        }, 400

    inserted_at, error = _parse_food_date(data["inserted_at"], "inserted_at", required=True)
    if error:
        return {"success": False, "error": "INVALID_DATE", "message": error}, 400

    parsed_dates = {"inserted_at": inserted_at}
    for field in ("manufacture_date", "expiry_date"):
        parsed_dates[field], error = _parse_food_date(data.get(field), field)
        if error:
            return {"success": False, "error": "INVALID_DATE", "message": error}, 400

    quantity = data.get("quantity")
    if quantity is not None:
        if not isinstance(quantity, (int, float)) or isinstance(quantity, bool):
            return {
                "success": False,
                "error": "INVALID_QUANTITY",
                "message": "quantity must be a non-negative finite number"
            }, 400
        try:
            valid_quantity = math.isfinite(quantity) and quantity >= 0
        except (OverflowError, TypeError):
            valid_quantity = False
        if not valid_quantity:
            return {
                "success": False,
                "error": "INVALID_QUANTITY",
                "message": "quantity must be a non-negative finite number"
            }, 400

    storage_location = data.get("storage_location")
    if storage_location is not None and not isinstance(storage_location, str):
        return {
            "success": False,
            "error": "INVALID_FIELD",
            "message": "storage_location must be a string",
            "field": "storage_location"
        }, 400

    connection = get_db_connection()
    try:
        generated_food_id = "food_id" not in data
        if generated_food_id:
            # Reserve the SQLite AUTOINCREMENT value and food_id atomically.
            connection.execute("BEGIN IMMEDIATE")
            row_id, food_id = _next_generated_food_id(connection)
            cursor = connection.execute(
                """INSERT INTO food_items (
                    id, food_id, food_name, category, quantity, inserted_at,
                    manufacture_date, expiry_date, storage_location
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    row_id, food_id, data["food_name"], data["category"], quantity,
                    parsed_dates["inserted_at"], parsed_dates["manufacture_date"],
                    parsed_dates["expiry_date"], storage_location,
                ),
            )
        else:
            food_id = data["food_id"]
            duplicate = connection.execute(
                "SELECT 1 FROM food_items WHERE food_id = ?", (food_id,)
            ).fetchone()
            if duplicate:
                return {
                    "success": False,
                    "error": "DUPLICATE_FOOD_ID",
                    "message": "food_id already exists"
                }, 409

            cursor = connection.execute(
                """INSERT INTO food_items (
                    food_id, food_name, category, quantity, inserted_at,
                    manufacture_date, expiry_date, storage_location
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    food_id, data["food_name"], data["category"], quantity,
                    parsed_dates["inserted_at"], parsed_dates["manufacture_date"],
                    parsed_dates["expiry_date"], storage_location,
                ),
            )
        connection.commit()
        row = connection.execute(
            "SELECT * FROM food_items WHERE id = ?",
            (cursor.lastrowid,)
        ).fetchone()
        return {
            "success": True,
            "message": "Food created",
            "food": _food_dict(row)
        }, 201
    except sqlite3.IntegrityError:
        connection.rollback()
        return {
            "success": False,
            "error": "DUPLICATE_FOOD_ID",
            "message": "food_id already exists"
        }, 409
    finally:
        connection.close()


@readings_bp.get("/foods")
def get_foods():
    connection = get_db_connection()
    try:
        rows = connection.execute(
            "SELECT * FROM food_items ORDER BY id"
        ).fetchall()
        return {"success": True, "data": [_food_dict(row) for row in rows]}, 200
    finally:
        connection.close()


@readings_bp.get("/foods/<food_id>")
def get_food(food_id):
    connection = get_db_connection()
    try:
        row = connection.execute(
            "SELECT * FROM food_items WHERE food_id = ?",
            (food_id,)
        ).fetchone()
        if row is None:
            return {
                "success": False,
                "error": "FOOD_NOT_FOUND",
                "message": "Food item not found"
            }, 404
        return {"success": True, "food": _food_dict(row)}, 200
    finally:
        connection.close()


@readings_bp.post("/readings")
def create_reading():
    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return {
            "success": False,
            "error": "INVALID_JSON",
            "message": "Request body must be a JSON object"
        }, 400

    compact_fields = COMPACT_REQUIRED_FIELDS | COMPACT_OPTIONAL_FIELDS
    if data.keys() & compact_fields:
        try:
            data = decode_compact_reading(data)
        except ReadingProtocolError as error:
            return {
                "success": False,
                "error": "INVALID_COMPACT_PAYLOAD",
                "message": str(error)
            }, 400

    required_fields = [
        "device_id",
        "device_reading_id",
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

    if not isinstance(data["device_id"], str) or not data["device_id"].strip():
        return {
            "success": False,
            "error": "INVALID_DEVICE_ID",
            "message": "device_id must be a non-empty string"
        }, 400

    device_reading_id = _normalize_device_reading_id(data["device_reading_id"])
    if device_reading_id is None:
        return {
            "success": False,
            "error": "INVALID_DEVICE_READING_ID",
            "message": "device_reading_id must be a canonical UUID v4"
        }, 400

    if not _is_valid_timestamp(data["timestamp"]):
        return {
            "success": False,
            "error": "INVALID_TIMESTAMP",
            "message": "timestamp must be a valid ISO datetime"
        }, 400

    for field in ("temperature_c", "humidity_pct", "gas_raw"):
        value = data[field]
        if value is not None and not _is_finite_sensor_number(value):
            return {
                "success": False,
                "error": "INVALID_SENSOR_VALUE",
                "message": f"{field} must be a finite number or null",
                "field": field
            }, 400

    if not isinstance(data["door_open"], bool):
        return {
            "success": False,
            "error": "INVALID_DOOR_STATE",
            "message": "door_open must be a boolean"
        }, 400

    open_duration_seconds = data.get("open_duration_seconds", 0)
    if (
        not isinstance(open_duration_seconds, int)
        or isinstance(open_duration_seconds, bool)
        or open_duration_seconds < 0
    ):
        return {
            "success": False,
            "error": "INVALID_OPEN_DURATION",
            "message": "open_duration_seconds must be a non-negative integer"
        }, 400

    food_id = data.get("food_id")
    if food_id is not None:
        if not isinstance(food_id, str) or not food_id.strip():
            return {
                "success": False,
                "error": "INVALID_FOOD_ID",
                "message": "food_id must be a non-empty string"
            }, 400
        food_id = food_id.strip()

    canonical_payload = {
        "device_id": data["device_id"],
        "timestamp": data["timestamp"],
        "temperature_c": data["temperature_c"],
        "humidity_pct": data["humidity_pct"],
        "gas_raw": data["gas_raw"],
        "door_open": int(data["door_open"]),
        "open_duration_seconds": open_duration_seconds,
        "food_id": food_id,
    }

    connection = get_db_connection()
    try:
        if device_reading_id is not None:
            # Serialize check/insert pairs; the unique index remains the final
            # protection against duplicate device identities.
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT * FROM sensor_readings "
                "WHERE device_id = ? AND device_reading_id = ?",
                (data["device_id"], device_reading_id)
            ).fetchone()
            if existing is not None:
                if _reading_payload_matches(existing, canonical_payload):
                    connection.rollback()
                    return _reading_response(existing, True), 200
                connection.rollback()
                return {
                    "success": False,
                    "error": "DEVICE_READING_ID_CONFLICT",
                    "message": "device_reading_id was already used with a different payload",
                    "device_reading_id": device_reading_id
                }, 409

        food = None
        if food_id is not None:
            food = connection.execute(
                "SELECT category, inserted_at, expiry_date "
                "FROM food_items WHERE food_id = ?",
                (food_id,)
            ).fetchone()
            if food is None:
                return {
                    "success": False,
                    "error": "FOOD_NOT_FOUND",
                    "message": "food_id does not identify a registered food item"
                }, 404

        if device_reading_id is None:
            connection.execute("BEGIN IMMEDIATE")
        previous_gas_state = get_gas_anomaly_state(
            connection, data["device_id"], food_id
        )
        previous_gas_active = bool(
            previous_gas_state["anomaly_active"]
            if previous_gas_state is not None else False
        )
        gas_anomaly_active = update_gas_anomaly_state(
            connection, data["device_id"], food_id, data["gas_raw"]
        )
        sensor_fault_transitions = update_sensor_fault_states(
            connection,
            data["device_id"],
            food_id,
            data["timestamp"],
            data,
        )
        exposure_update = update_temperature_exposure(
            connection,
            data["device_id"],
            food_id,
            data["temperature_c"],
            data["timestamp"],
        )
        freshness_result = evaluate_freshness(
            temperature_c=data["temperature_c"],
            humidity_pct=data["humidity_pct"],
            gas_raw=data["gas_raw"],
            door_open=data["door_open"],
            open_duration_seconds=open_duration_seconds,
            category=food["category"] if food else None,
            inserted_at=food["inserted_at"] if food else None,
            expiry_date=food["expiry_date"] if food else None,
            temperature_exposure_hours=exposure_update.exposure_seconds / 3600,
            gas_anomaly_active=gas_anomaly_active
        )

        freshness_status = freshness_result.status.value
        freshness_reason = freshness_result.reason
        freshness_evaluated_at = datetime.now(timezone.utc).isoformat()

        try:
            cursor = connection.execute(
                """
                INSERT INTO sensor_readings (
                    device_id, timestamp, temperature_c, humidity_pct, gas_raw,
                    door_open, open_duration_seconds, food_id, device_reading_id,
                    freshness_status, freshness_reason, freshness_evaluated_at,
                    gas_anomaly_active
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    data["device_id"], data["timestamp"], data["temperature_c"],
                    data["humidity_pct"], data["gas_raw"], int(data["door_open"]),
                    open_duration_seconds, food_id, device_reading_id,
                    freshness_status, freshness_reason, freshness_evaluated_at,
                    int(gas_anomaly_active)
                )
            )
        except sqlite3.IntegrityError as error:
            connection.rollback()
            if device_reading_id is None:
                raise
            expected_unique_error = (
                "UNIQUE constraint failed: "
                "sensor_readings.device_id, sensor_readings.device_reading_id"
            )
            if str(error) != expected_unique_error:
                raise
            existing = connection.execute(
                "SELECT * FROM sensor_readings "
                "WHERE device_id = ? AND device_reading_id = ?",
                (data["device_id"], device_reading_id)
            ).fetchone()
            if existing is None:
                raise
            if _reading_payload_matches(existing, canonical_payload):
                return _reading_response(existing, True), 200
            return {
                "success": False,
                "error": "DEVICE_READING_ID_CONFLICT",
                "message": "device_reading_id was already used with a different payload",
                "device_reading_id": device_reading_id
            }, 409
        _persist_gas_transition_event(
            connection,
            {**data, "device_reading_id": device_reading_id},
            food_id,
            previous_gas_active,
            gas_anomaly_active,
            cursor.lastrowid,
        )
        if exposure_update.exceeded_transition:
            _persist_temperature_exposure_event(
                connection,
                {**data, "device_reading_id": device_reading_id},
                cursor.lastrowid,
                exposure_update.exposure_seconds,
            )
        for transition in sensor_fault_transitions:
            _persist_sensor_fault_event(
                connection,
                {**data, "device_reading_id": device_reading_id},
                cursor.lastrowid,
                transition,
            )
        connection.commit()
        stored = connection.execute(
            "SELECT * FROM sensor_readings WHERE id = ?", (cursor.lastrowid,)
        ).fetchone()
        if device_reading_id is not None:
            return _reading_response(stored, False), 201
        return {
            "success": True,
            "message": "Reading saved",
            "reading_id": cursor.lastrowid,
            "freshness": {
                "status": freshness_status,
                "reason": freshness_reason
            }
        }, 201
    finally:
        connection.close()

@readings_bp.get("/readings/latest")
def get_latest_reading():
    connection = get_db_connection()
    try:
        row = connection.execute(
            """
            SELECT
                r.id,
                r.device_id,
                r.timestamp,
                r.temperature_c,
                r.humidity_pct,
                r.gas_raw,
                r.door_open,
                r.open_duration_seconds,
                r.food_id,
                r.freshness_status,
                r.freshness_reason,
                r.gas_anomaly_active,
                r.created_at,
                f.category AS _food_category,
                f.inserted_at AS _food_inserted_at,
                f.expiry_date AS _food_expiry_date
            FROM sensor_readings AS r
            LEFT JOIN food_items AS f ON f.food_id = r.food_id
            ORDER BY r.id DESC
            LIMIT 1
            """
        ).fetchone()
    finally:
        connection.close()

    if row is None:
        return {
            "success": False,
            "error": "NO_DATA",
            "message": "No sensor readings found"
        }, 404

    data = dict(row)

    freshness = {"status": data["freshness_status"], "reason": data["freshness_reason"]}
    if freshness["status"] is None:
        freshness_result = evaluate_freshness(
            temperature_c=data["temperature_c"], humidity_pct=data["humidity_pct"],
            gas_raw=data["gas_raw"], door_open=bool(data["door_open"]),
            open_duration_seconds=data["open_duration_seconds"],
            category=data["_food_category"], inserted_at=data["_food_inserted_at"],
            expiry_date=data["_food_expiry_date"],
            gas_anomaly_active=bool(data["gas_anomaly_active"])
        )
        freshness = {"status": freshness_result.status.value, "reason": freshness_result.reason}

    data.pop("_food_category")
    data.pop("_food_inserted_at")
    data.pop("_food_expiry_date")
    data.pop("freshness_status")
    data.pop("freshness_reason")

    data["freshness"] = freshness

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
    try:
        rows = connection.execute(
            """
            SELECT
                r.id,
                r.device_id,
                r.timestamp,
                r.temperature_c,
                r.humidity_pct,
                r.gas_raw,
                r.door_open,
                r.open_duration_seconds,
                r.food_id,
                r.freshness_status,
                r.freshness_reason,
                r.gas_anomaly_active,
                r.created_at,
                f.category AS _food_category,
                f.inserted_at AS _food_inserted_at,
                f.expiry_date AS _food_expiry_date
            FROM sensor_readings AS r
            LEFT JOIN food_items AS f ON f.food_id = r.food_id
            ORDER BY r.id DESC
            LIMIT ?
            """,
            (limit,)
        ).fetchall()
    finally:
        connection.close()

    data = []

    for row in rows:
        reading = dict(row)

        freshness = {"status": reading["freshness_status"], "reason": reading["freshness_reason"]}
        if freshness["status"] is None:
            freshness_result = evaluate_freshness(
                temperature_c=reading["temperature_c"], humidity_pct=reading["humidity_pct"],
                gas_raw=reading["gas_raw"], door_open=bool(reading["door_open"]),
                open_duration_seconds=reading["open_duration_seconds"],
                category=reading["_food_category"], inserted_at=reading["_food_inserted_at"],
                expiry_date=reading["_food_expiry_date"],
                gas_anomaly_active=bool(reading["gas_anomaly_active"])
            )
            freshness = {"status": freshness_result.status.value, "reason": freshness_result.reason}

        reading.pop("_food_category")
        reading.pop("_food_inserted_at")
        reading.pop("_food_expiry_date")
        reading.pop("freshness_status")
        reading.pop("freshness_reason")

        reading["door_open"] = bool(reading["door_open"])

        reading["freshness"] = freshness

        data.append(reading)

    return {
        "success": True,
        "limit": limit,
        "count": len(data),
        "data": data
    }, 200
