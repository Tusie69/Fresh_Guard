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

    assert result.status == FreshnessStatus.FRESH


def test_temperature_check_food():
    result = evaluate_temperature(15, 2.1)

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

    assert result.status == FreshnessStatus.FRESH


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
    ("category", "max_days"),
    [("MEAT", 3), ("DAIRY", 14), ("VEGETABLE", 7), ("FRUIT", 14), ("COOKED_FOOD", 4)],
)
def test_storage_profile_thresholds_for_all_categories(category, max_days):
    assert evaluate_with_optional_food(category, max_days - 2).status == FreshnessStatus.FRESH
    assert evaluate_with_optional_food(category, max_days - 1).status == FreshnessStatus.USE_SOON
    assert evaluate_with_optional_food(category, max_days).status == FreshnessStatus.USE_SOON
    assert evaluate_with_optional_food(category, max_days + 1).status == FreshnessStatus.CHECK_FOOD


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
        (10, None, None, None, FreshnessStatus.FRESH),
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
        temperature_exposure_hours=3,
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
        (29, FreshnessStatus.FRESH),
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
        (5, FreshnessStatus.FRESH),
        (5.01, FreshnessStatus.FRESH),
        (8, FreshnessStatus.FRESH),
        (8.01, FreshnessStatus.FRESH),
        (12, FreshnessStatus.FRESH),
        (12.01, FreshnessStatus.FRESH),
    ],
)
def test_temperature_threshold_boundaries(temperature_c, expected_status):
    result = evaluate_with_optional_food(temperature_c=temperature_c)

    assert result.status == expected_status


@pytest.mark.parametrize("temperature", [5.01, 8, 12, 15])
def test_temperature_exposure_rule(temperature):
    assert evaluate_temperature(temperature, 2).status == FreshnessStatus.FRESH
    result = evaluate_temperature(temperature, 2.01)
    assert result.status == FreshnessStatus.CHECK_FOOD
    assert "exceeded 2 hours" in result.reason


def test_temperature_recovery_at_or_below_five_resets_exposure():
    assert evaluate_temperature(5, 10).status == FreshnessStatus.FRESH
    assert evaluate_temperature(4, 10).status == FreshnessStatus.FRESH


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("temperature_c", float("nan")),
        ("temperature_c", float("inf")),
        ("humidity_pct", float("nan")),
        ("humidity_pct", float("inf")),
        ("gas_raw", float("nan")),
        ("gas_raw", float("inf")),
        ("gas_raw", -1),
    ],
)
def test_non_finite_or_negative_sensor_data_is_never_fresh(field, value):
    result = evaluate_with_optional_food(**{field: value})
    assert result.status == FreshnessStatus.CHECK_FOOD


def test_invalid_sensor_dominates_another_rule_use_soon():
    result = evaluate_with_optional_food(
        category="MEAT", days_stored=2, humidity_pct=float("nan")
    )
    assert result.status == FreshnessStatus.CHECK_FOOD
    assert "humidity" in result.reason.lower()
    assert "storage duration" in result.reason.lower()


@pytest.mark.parametrize("humidity", [79.9, 80, 95, 95.1])
def test_valid_humidity_does_not_change_severity(humidity):
    assert evaluate_humidity(humidity, "VEGETABLE").status == FreshnessStatus.FRESH


@pytest.mark.parametrize(
    ("humidity", "expected_warning"),
    [(79.9, "low humidity"), (95.1, "high humidity")],
)
def test_produce_humidity_warnings_are_reported_without_increasing_severity(
    humidity, expected_warning
):
    result = evaluate_freshness(
        temperature_c=5, humidity_pct=humidity, gas_raw=100,
        door_open=False, category="VEGETABLE",
    )
    assert result.status == FreshnessStatus.FRESH
    assert expected_warning in result.reason.lower()


@pytest.mark.parametrize("category", ["MEAT", "DAIRY", "COOKED_FOOD"])
def test_non_produce_humidity_does_not_create_warning(category):
    result = evaluate_freshness(
        temperature_c=5, humidity_pct=50, gas_raw=100,
        door_open=False, category=category,
    )
    assert result.status == FreshnessStatus.FRESH
    assert "humidity" not in result.reason.lower()


def test_temperature_does_not_override_storage_use_soon():
    result = evaluate_with_optional_food("MEAT", 2, temperature_c=15)
    assert result.status == FreshnessStatus.USE_SOON


@pytest.mark.parametrize(
    ("case", "expected_status", "expected_reasons"),
    [
        ("all_fresh", FreshnessStatus.FRESH, ()),
        ("storage_soon", FreshnessStatus.USE_SOON, ("storage duration",)),
        ("expiry_soon", FreshnessStatus.USE_SOON, ("expiry",)),
        ("gas_anomaly", FreshnessStatus.CHECK_FOOD, ("gas",)),
        ("temperature_exposure", FreshnessStatus.CHECK_FOOD, ("temperature",)),
        ("door_timeout", FreshnessStatus.CHECK_FOOD, ("door",)),
        ("gas_and_expiry", FreshnessStatus.CHECK_FOOD, ("gas", "expiry")),
        ("temperature_and_expiry", FreshnessStatus.CHECK_FOOD, ("temperature", "expiry")),
        ("gas_and_storage", FreshnessStatus.CHECK_FOOD, ("gas", "storage duration")),
        ("recovered_gas_and_temperature", FreshnessStatus.CHECK_FOOD, ("temperature",)),
        ("recovered_gas_and_expiry", FreshnessStatus.USE_SOON, ("expiry",)),
        ("humidity_warning_and_storage", FreshnessStatus.USE_SOON, ("low humidity", "storage duration")),
        ("humidity_warning_and_gas", FreshnessStatus.CHECK_FOOD, ("low humidity", "gas")),
        ("short_door_open_fresh", FreshnessStatus.FRESH, ("door",)),
        ("short_door_open_storage", FreshnessStatus.USE_SOON, ("door", "storage duration")),
    ],
)
def test_cross_rule_integration(case, expected_status, expected_reasons):
    today = date.today()
    args = {
        "temperature_c": 5,
        "temperature_exposure_hours": 0,
        "humidity_pct": 90,
        "gas_raw": 100,
        "gas_anomaly_active": False,
        "door_open": False,
        "open_duration_seconds": 0,
        "category": "MEAT",
        "inserted_at": today,
        "expiry_date": today + timedelta(days=2),
    }
    if case in ("storage_soon", "gas_and_storage", "humidity_warning_and_storage", "short_door_open_storage"):
        args["inserted_at"] = today - timedelta(days=2 if args["category"] == "MEAT" else 6)
    if case in ("expiry_soon", "gas_and_expiry", "temperature_and_expiry", "recovered_gas_and_expiry"):
        args["expiry_date"] = today + timedelta(days=1)
    if case in ("gas_anomaly", "gas_and_expiry", "gas_and_storage", "humidity_warning_and_gas"):
        args["gas_anomaly_active"] = True
    if case in ("temperature_exposure", "temperature_and_expiry", "recovered_gas_and_temperature"):
        args["temperature_c"] = 10
        args["temperature_exposure_hours"] = 2.1
    if case == "door_timeout":
        args["door_open"] = True
        args["open_duration_seconds"] = 30
    if case in ("humidity_warning_and_storage", "humidity_warning_and_gas"):
        args["category"] = "VEGETABLE"
        args["humidity_pct"] = 79
        if case == "humidity_warning_and_storage":
            args["inserted_at"] = today - timedelta(days=6)
    if case in ("short_door_open_fresh", "short_door_open_storage"):
        args["door_open"] = True
        args["open_duration_seconds"] = 29

    result = evaluate_freshness(**args)
    assert result.status == expected_status
    for fragment in expected_reasons:
        assert fragment in result.reason.lower()


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
        (True, FreshnessStatus.FRESH, "Door is open."),
    ],
)
def test_evaluate_door_wrapper(door_open, expected_status, expected_reason):
    result = evaluate_door(door_open)

    assert result.status == expected_status
    assert result.reason == expected_reason
