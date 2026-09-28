import sqlite3
from dataclasses import FrozenInstanceError, replace

import pytest

from app.services.freshness import FreshnessStatus, evaluate_freshness, evaluate_temperature
from app.services.gas_anomaly import update_gas_anomaly_state
from app.services.rule_provider import (
    DEFAULT_RULES,
    FoodCategory,
    FreshnessRuleProvider,
    get_freshness_rules,
)
from app.services.temperature_exposure import update_temperature_exposure


def _temperature_state_connection():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.execute("""CREATE TABLE temperature_exposure_state (
        device_id TEXT NOT NULL, food_id TEXT NOT NULL DEFAULT '',
        exposure_seconds REAL NOT NULL DEFAULT 0,
        exposure_active INTEGER NOT NULL DEFAULT 0,
        exposure_exceeded INTEGER NOT NULL DEFAULT 0,
        last_valid_temperature_timestamp TEXT NULL,
        continuity_broken INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY(device_id, food_id)
    )""")
    return connection


def _gas_state_connection():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.execute("""CREATE TABLE gas_anomaly_state (
        device_id TEXT NOT NULL, food_id TEXT NOT NULL DEFAULT '',
        baseline REAL NULL, baseline_sample_count INTEGER NOT NULL DEFAULT 0,
        baseline_sum REAL NOT NULL DEFAULT 0,
        consecutive_anomaly_count INTEGER NOT NULL DEFAULT 0,
        anomaly_active INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY(device_id, food_id)
    )""")
    return connection


def test_default_provider_snapshot_contains_current_rules():
    rules = get_freshness_rules()

    assert isinstance(rules, type(DEFAULT_RULES))
    assert rules.temperature_hot_threshold_c == 5.0
    assert rules.temperature_critical_threshold_c == 12.0
    assert rules.temperature_exposure_limit_seconds == 7200
    assert rules.temperature_continuity_gap_seconds == 10
    assert rules.gas_baseline_sample_count == 10
    assert rules.gas_anomaly_deviation_ratio == 0.30
    assert rules.gas_required_consecutive_readings == 3
    assert (rules.humidity_vegetable_min_pct, rules.humidity_vegetable_max_pct) == (80, 95)
    assert (rules.humidity_fruit_min_pct, rules.humidity_fruit_max_pct) == (80, 95)
    assert rules.door_open_timeout_seconds == 30
    assert rules.expiry_use_soon_window_days == 1
    assert rules.storage_profiles[FoodCategory.MEAT].max_duration_days == 3
    assert rules.storage_profiles[FoodCategory.DAIRY].max_duration_days == 14
    assert rules.storage_profiles[FoodCategory.VEGETABLE].max_duration_days == 7
    assert rules.storage_profiles[FoodCategory.FRUIT].max_duration_days == 14
    assert rules.storage_profiles[FoodCategory.COOKED_FOOD].max_duration_days == 4


def test_provider_snapshot_is_immutable():
    rules = get_freshness_rules()

    with pytest.raises(FrozenInstanceError):
        rules.temperature_hot_threshold_c = 7
    with pytest.raises(TypeError):
        rules.storage_profiles[FoodCategory.MEAT] = rules.storage_profiles[FoodCategory.DAIRY]


def test_temperature_engine_and_exposure_use_one_custom_snapshot():
    rules = replace(
        DEFAULT_RULES,
        temperature_hot_threshold_c=7.0,
        temperature_exposure_limit_seconds=20,
        temperature_continuity_gap_seconds=4,
    )
    connection = _temperature_state_connection()
    try:
        # 6 C is cold under this same snapshot in both layers.
        assert evaluate_temperature(6, 99, rules).status == FreshnessStatus.FRESH
        update_temperature_exposure(connection, "D", None, 6, "2026-09-26T00:00:00+00:00", rules)
        state = connection.execute("SELECT * FROM temperature_exposure_state").fetchone()
        assert state["exposure_active"] == 0

        # 8 C is hot, and the custom gap/limit are used by the state processor.
        update_temperature_exposure(connection, "D", None, 8, "2026-09-26T00:00:04+00:00", rules)
        update = update_temperature_exposure(connection, "D", None, 8, "2026-09-26T00:00:25+00:00", rules)
        assert update.exposure_seconds == 0
        assert update.exceeded_transition is False
    finally:
        connection.close()


def test_gas_processor_uses_provider_snapshot():
    rules = replace(
        DEFAULT_RULES,
        gas_baseline_sample_count=2,
        gas_anomaly_deviation_ratio=0.50,
        gas_required_consecutive_readings=2,
    )
    connection = _gas_state_connection()
    try:
        assert update_gas_anomaly_state(connection, "D", None, 100, rules) is False
        assert update_gas_anomaly_state(connection, "D", None, 100, rules) is False
        assert update_gas_anomaly_state(connection, "D", None, 151, rules) is False
        assert update_gas_anomaly_state(connection, "D", None, 151, rules) is True
        row = connection.execute("SELECT * FROM gas_anomaly_state").fetchone()
        assert row["baseline_sample_count"] == 2
        assert row["baseline"] == 100
        assert row["consecutive_anomaly_count"] == 2
    finally:
        connection.close()


def test_default_provider_preserves_existing_freshness_behavior():
    result = evaluate_freshness(
        temperature_c=5,
        humidity_pct=60,
        gas_raw=100,
        door_open=False,
        category="MEAT",
    )
    assert result.status == FreshnessStatus.FRESH
    assert result.reason == "All sensor readings are available"


def test_critical_threshold_is_provider_backed_and_preserves_strict_boundary():
    assert evaluate_temperature(12, 2.01).status == FreshnessStatus.CHECK_FOOD
    assert evaluate_temperature(12.01, 0).status == FreshnessStatus.CHECK_FOOD
    custom = replace(DEFAULT_RULES, temperature_critical_threshold_c=20.0)
    assert evaluate_temperature(15, 0, custom).status == FreshnessStatus.FRESH


def test_provider_object_returns_the_same_immutable_snapshot():
    provider = FreshnessRuleProvider(DEFAULT_RULES)
    assert provider.snapshot() is provider.snapshot()
    assert provider.snapshot() is DEFAULT_RULES
