from datetime import date, timedelta

import pytest

from app.services.freshness import (
    FreshnessStatus,
    evaluate_temperature,
    evaluate_humidity,
    evaluate_gas,
    evaluate_freshness,
    evaluate_door,
    evaluate_door_timeout,
)


def test_temperature_fresh():
    result = evaluate_temperature(4)

    assert result.status == FreshnessStatus.FRESH


def test_temperature_use_soon():
    result = evaluate_temperature(10)

    assert result.status == FreshnessStatus.USE_SOON


def test_temperature_check_food():
    result = evaluate_temperature(15)

    assert result.status == FreshnessStatus.CHECK_FOOD


def test_temperature_sensor_fault():
    result = evaluate_temperature(None)

    assert result.status == FreshnessStatus.CHECK_FOOD


def test_humidity_sensor_fault():
    result = evaluate_humidity(None)

    assert result.status == FreshnessStatus.CHECK_FOOD


def test_gas_sensor_fault():
    result = evaluate_gas(None)

    assert result.status == FreshnessStatus.CHECK_FOOD


def test_freshness_all_sensors_normal():
    result = evaluate_freshness(
        temperature_c=4,
        humidity_pct=60,
        gas_raw=330,
        door_open=False,
        open_duration_seconds=0
    )
    assert result.status == FreshnessStatus.FRESH

    assert result.status == FreshnessStatus.FRESH


def test_door_closed():
    result = evaluate_door_timeout(False, 0)

    assert result.status == FreshnessStatus.FRESH


def test_door_open():
    result = evaluate_door_timeout(True, 10)

    assert result.status == FreshnessStatus.USE_SOON


def test_door_open_too_long():
    result = evaluate_door_timeout(True, 35)

    assert result.status == FreshnessStatus.CHECK_FOOD


def evaluate_with_optional_food(category=None, days_stored=None, expiry_offset=None, **overrides):
    today = date.today()
    arguments = {
        "temperature_c": 5,
        "humidity_pct": 70,
        "gas_raw": 150,
        "door_open": False,
        "open_duration_seconds": 0,
        "category": category,
        "inserted_at": today - timedelta(days=days_stored) if days_stored is not None else None,
        "expiry_date": today + timedelta(days=expiry_offset) if expiry_offset is not None else None,
    }
    arguments.update(overrides)
    return evaluate_freshness(**arguments)


@pytest.mark.parametrize(
    ("category", "days_stored", "expected_status"),
    [
        ("MEAT", 1, FreshnessStatus.FRESH),
        ("MEAT", 2, FreshnessStatus.USE_SOON),
        ("MEAT", 3, FreshnessStatus.USE_SOON),
        ("MEAT", 4, FreshnessStatus.CHECK_FOOD),
        ("DAIRY", 13, FreshnessStatus.USE_SOON),
        ("DAIRY", 14, FreshnessStatus.USE_SOON),
        ("DAIRY", 15, FreshnessStatus.CHECK_FOOD),
    ],
)
def test_storage_duration_boundaries(category, days_stored, expected_status):
    result = evaluate_with_optional_food(category, days_stored)

    assert result.status == expected_status


@pytest.mark.parametrize(
    ("expiry_offset", "expected_status"),
    [
        (2, FreshnessStatus.FRESH),
        (1, FreshnessStatus.USE_SOON),
        (0, FreshnessStatus.USE_SOON),
        (-1, FreshnessStatus.CHECK_FOOD),
        (None, FreshnessStatus.FRESH),
    ],
)
def test_expiry_date_boundaries(expiry_offset, expected_status):
    result = evaluate_with_optional_food(expiry_offset=expiry_offset)

    assert result.status == expected_status


@pytest.mark.parametrize(
    ("days_stored", "expiry_offset", "expected_status"),
    [
        (4, 2, FreshnessStatus.CHECK_FOOD),
        (1, -1, FreshnessStatus.CHECK_FOOD),
        (2, -1, FreshnessStatus.CHECK_FOOD),
    ],
)
def test_storage_and_expiry_aggregate_by_max(days_stored, expiry_offset, expected_status):
    result = evaluate_with_optional_food(
        "MEAT",
        days_stored,
        expiry_offset,
    )

    assert result.status == expected_status


@pytest.mark.parametrize(
    ("temperature_c", "expiry_offset", "category", "days_stored", "expected_status"),
    [
        (10, None, None, None, FreshnessStatus.USE_SOON),
        (5, None, "MEAT", 4, FreshnessStatus.CHECK_FOOD),
        (10, -1, None, None, FreshnessStatus.CHECK_FOOD),
    ],
)
def test_max_severity_across_rules(
    temperature_c, expiry_offset, category, days_stored, expected_status
):
    result = evaluate_with_optional_food(
        category,
        days_stored,
        expiry_offset,
        temperature_c=temperature_c,
    )

    assert result.status == expected_status


def test_all_active_rules_reasons_are_preserved():
    today = date.today()
    result = evaluate_freshness(
        temperature_c=15,
        humidity_pct=None,
        gas_raw=None,
        door_open=True,
        open_duration_seconds=40,
        category="MEAT",
        inserted_at=today - timedelta(days=5),
        expiry_date=today - timedelta(days=1),
    )

    assert result.status == FreshnessStatus.CHECK_FOOD
    for reason_fragment in ("Temperature", "Humidity", "Gas", "Door", "storage duration", "expiry date"):
        assert reason_fragment.lower() in result.reason.lower()


@pytest.mark.parametrize(
    ("overrides", "expected_reason"),
    [
        ({"temperature_c": "abc"}, "temperature"),
        ({"humidity_pct": "abc"}, "humidity"),
        ({"gas_raw": "abc"}, "gas"),
        ({"door_open": "true"}, "door"),
        ({"door_open": True, "open_duration_seconds": "30"}, "duration"),
        ({"door_open": True, "open_duration_seconds": None}, "duration"),
    ],
)
def test_malformed_sensor_inputs_return_check_food(overrides, expected_reason):
    result = evaluate_with_optional_food(**overrides)

    assert result.status == FreshnessStatus.CHECK_FOOD
    assert expected_reason in result.reason.lower()


@pytest.mark.parametrize("invalid_value", [True, False])
@pytest.mark.parametrize("field", ["temperature_c", "humidity_pct", "gas_raw"])
def test_boolean_sensor_values_are_invalid(field, invalid_value):
    result = evaluate_with_optional_food(**{field: invalid_value})

    assert result.status == FreshnessStatus.CHECK_FOOD


def test_negative_open_duration_is_invalid():
    result = evaluate_with_optional_food(
        door_open=True,
        open_duration_seconds=-1,
    )

    assert result.status == FreshnessStatus.CHECK_FOOD


@pytest.mark.parametrize(
    ("duration", "expected_status"),
    [
        (29, FreshnessStatus.USE_SOON),
        (30, FreshnessStatus.CHECK_FOOD),
        (31, FreshnessStatus.CHECK_FOOD),
    ],
)
def test_door_timeout_boundary(duration, expected_status):
    result = evaluate_with_optional_food(
        door_open=True,
        open_duration_seconds=duration,
    )

    assert result.status == expected_status


@pytest.mark.parametrize(
    ("temperature_c", "expected_status"),
    [
        (8, FreshnessStatus.FRESH),
        (8.01, FreshnessStatus.USE_SOON),
        (12, FreshnessStatus.USE_SOON),
        (12.01, FreshnessStatus.CHECK_FOOD),
    ],
)
def test_temperature_threshold_boundaries(temperature_c, expected_status):
    result = evaluate_with_optional_food(temperature_c=temperature_c)

    assert result.status == expected_status


def test_future_inserted_at_is_invalid():
    result = evaluate_with_optional_food(
        "MEAT",
        days_stored=-1,
    )

    assert result.status == FreshnessStatus.CHECK_FOOD
    assert "Invalid food insertion date." in result.reason


def test_unknown_food_category_is_invalid():
    result = evaluate_with_optional_food("UNKNOWN", 0)

    assert result.status == FreshnessStatus.CHECK_FOOD
    assert "Unknown food category." in result.reason


def test_invalid_expiry_date_is_invalid():
    result = evaluate_with_optional_food(expiry_date="not-a-date")

    assert result.status == FreshnessStatus.CHECK_FOOD
    assert "Invalid expiry date." in result.reason


def test_optional_food_data_does_not_change_normal_environment():
    result = evaluate_with_optional_food()

    assert result.status == FreshnessStatus.FRESH


@pytest.mark.parametrize(
    ("door_open", "expected_status", "expected_reason"),
    [
        (False, FreshnessStatus.FRESH, ""),
        (True, FreshnessStatus.USE_SOON, "Door is open."),
    ],
)
def test_evaluate_door_wrapper(door_open, expected_status, expected_reason):
    result = evaluate_door(door_open)

    assert result.status == expected_status
    assert result.reason == expected_reason
