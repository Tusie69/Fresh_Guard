import pytest

from app.services.freshness import FreshnessStatus, evaluate_freshness, evaluate_temperature


@pytest.mark.parametrize(
    ("temperature", "status", "warning"),
    [
        (4.0, FreshnessStatus.FRESH, ""),
        (5.0, FreshnessStatus.FRESH, ""),
        (5.1, FreshnessStatus.FRESH, "Temperature Warning"),
        (8.0, FreshnessStatus.FRESH, "Temperature Warning"),
        (8.1, FreshnessStatus.FRESH, "High Temperature Warning"),
        (12.0, FreshnessStatus.FRESH, "High Temperature Warning"),
        (12.1, FreshnessStatus.CHECK_FOOD, "Critical Temperature"),
        (30.0, FreshnessStatus.CHECK_FOOD, "Critical Temperature"),
    ],
)
def test_temperature_boundaries(temperature, status, warning):
    result = evaluate_temperature(temperature)
    assert result.status == status
    if warning:
        assert warning in result.reason
    else:
        assert result.reason == ""


def test_temperature_exposure_and_instant_severity_are_combined():
    exact = evaluate_temperature(6, exposure_hours=2)
    assert exact.status == FreshnessStatus.FRESH
    assert "Temperature Warning" in exact.reason

    exceeded = evaluate_temperature(6, exposure_hours=2.001)
    assert exceeded.status == FreshnessStatus.CHECK_FOOD
    assert "exposure" in exceeded.reason.lower()

    critical = evaluate_freshness(
        temperature_c=30, humidity_pct=60, gas_raw=100, door_open=False,
    )
    assert critical.status == FreshnessStatus.CHECK_FOOD
    assert "Critical Temperature" in critical.reason


def test_temperature_null_remains_sensor_fault_behavior():
    result = evaluate_temperature(None)
    assert result.status == FreshnessStatus.CHECK_FOOD
    assert "sensor fault" in result.reason.lower()
