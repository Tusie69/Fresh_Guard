from copy import deepcopy
import math
import uuid

import pytest

from app.services.reading_protocol import (
    ReadingProtocolError,
    decode_compact_reading,
)


@pytest.fixture
def compact_payload():
    return {
        "id": str(uuid.uuid4()),
        "d": "esp32_01",
        "t": 1727253000,
        "tc": 5.2,
        "h": 61.5,
        "g": 302,
        "o": 0,
        "od": 0,
        "f": "FOOD001",
    }


def test_valid_compact_payload_maps_all_fields(compact_payload):
    decoded = decode_compact_reading(compact_payload)

    assert decoded == {
        "device_reading_id": compact_payload["id"],
        "device_id": "esp32_01",
        "timestamp": "2024-09-25T15:30:00+07:00",
        "temperature_c": 5.2,
        "humidity_pct": 61.5,
        "gas_raw": 302,
        "door_open": False,
        "open_duration_seconds": 0,
        "food_id": "FOOD001",
    }


def test_reading_id_is_preserved_without_regeneration(compact_payload):
    assert decode_compact_reading(compact_payload)["device_reading_id"] == compact_payload["id"]


@pytest.mark.parametrize(
    ("compact_key", "canonical_key", "value"),
    [
        ("d", "device_id", "device-42"),
        ("tc", "temperature_c", 8.25),
        ("h", "humidity_pct", 44.5),
        ("g", "gas_raw", 303),
    ],
)
def test_sensor_and_device_fields_are_mapped_without_coercion(
    compact_payload, compact_key, canonical_key, value
):
    compact_payload[compact_key] = value
    assert decode_compact_reading(compact_payload)[canonical_key] == value


@pytest.mark.parametrize(("door_value", "expected"), [(0, False), (1, True)])
def test_door_values_map_exactly(compact_payload, door_value, expected):
    compact_payload["o"] = door_value
    assert decode_compact_reading(compact_payload)["door_open"] is expected


@pytest.mark.parametrize("door_value", [True, False, 2, -1, "1", "0", None, 1.0])
def test_invalid_door_values_are_rejected(compact_payload, door_value):
    compact_payload["o"] = door_value
    with pytest.raises(ReadingProtocolError, match="integer 0 or 1"):
        decode_compact_reading(compact_payload)


def test_unix_timestamp_seconds_use_sagion_offset(compact_payload):
    assert decode_compact_reading(compact_payload)["timestamp"] == (
        "2024-09-25T15:30:00+07:00"
    )


def test_timestamp_conversion_is_deterministic(compact_payload):
    first = decode_compact_reading(compact_payload)
    second = decode_compact_reading(deepcopy(compact_payload))
    assert first["timestamp"] == second["timestamp"]


def test_millisecond_timestamp_is_rejected_as_out_of_range(compact_payload):
    compact_payload["t"] = 1727253000000
    with pytest.raises(ReadingProtocolError, match="supported timestamp range"):
        decode_compact_reading(compact_payload)


@pytest.mark.parametrize("missing", ["id", "d", "t", "tc", "h", "g", "o"])
def test_missing_required_compact_field_is_rejected(compact_payload, missing):
    del compact_payload[missing]
    with pytest.raises(ReadingProtocolError, match=missing):
        decode_compact_reading(compact_payload)


def test_omitted_duration_defaults_to_zero(compact_payload):
    del compact_payload["od"]
    assert decode_compact_reading(compact_payload)["open_duration_seconds"] == 0


def test_omitted_food_maps_to_none(compact_payload):
    del compact_payload["f"]
    assert decode_compact_reading(compact_payload)["food_id"] is None


@pytest.mark.parametrize(
    "timestamp",
    ["1727253000", None, True, math.nan, math.inf, -math.inf],
)
def test_invalid_timestamp_types_and_values_are_rejected(compact_payload, timestamp):
    compact_payload["t"] = timestamp
    with pytest.raises(ReadingProtocolError, match="Unix timestamp in seconds"):
        decode_compact_reading(compact_payload)


def test_out_of_range_integer_timestamp_is_rejected(compact_payload):
    compact_payload["t"] = 10**1000
    with pytest.raises(ReadingProtocolError, match="supported timestamp range"):
        decode_compact_reading(compact_payload)


@pytest.mark.parametrize(
    ("field", "value"), [("id", ""), ("id", 123), ("d", " "), ("d", 123)]
)
def test_invalid_required_string_fields_are_rejected(compact_payload, field, value):
    compact_payload[field] = value
    with pytest.raises(ReadingProtocolError):
        decode_compact_reading(compact_payload)


def test_mixed_compact_and_canonical_fields_are_rejected(compact_payload):
    compact_payload["temperature_c"] = 5
    with pytest.raises(ReadingProtocolError, match="cannot be mixed"):
        decode_compact_reading(compact_payload)


def test_canonical_only_payload_is_not_treated_as_compact(compact_payload):
    canonical = {
        "device_id": compact_payload["d"],
        "timestamp": "2026-09-25T15:00:00+07:00",
        "temperature_c": 5.2,
        "humidity_pct": 61.5,
        "gas_raw": 302,
        "door_open": False,
    }
    with pytest.raises(ReadingProtocolError, match="Missing required compact fields"):
        decode_compact_reading(canonical)


def test_decoder_does_not_access_database_or_freshness(compact_payload, monkeypatch):
    from app import database
    from app.services import freshness

    def unexpected_call(*_args, **_kwargs):
        raise AssertionError("decoder must remain independent of application services")

    monkeypatch.setattr(database, "get_db_connection", unexpected_call)
    monkeypatch.setattr(freshness, "evaluate_freshness", unexpected_call)
    assert decode_compact_reading(compact_payload)["device_reading_id"] == compact_payload["id"]
