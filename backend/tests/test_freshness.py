from app.services.freshness import (
    FreshnessStatus,
    evaluate_temperature,
    evaluate_humidity,
    evaluate_gas,
    evaluate_freshness,
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