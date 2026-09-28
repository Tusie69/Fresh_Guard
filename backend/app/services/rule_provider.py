"""Immutable FreshGuard freshness-rule snapshots and SQLite loading."""

from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Mapping
import math


class FoodCategory(Enum):
    MEAT = "MEAT"
    DAIRY = "DAIRY"
    VEGETABLE = "VEGETABLE"
    FRUIT = "FRUIT"
    COOKED_FOOD = "COOKED_FOOD"


@dataclass(frozen=True)
class StorageProfile:
    max_duration_days: int
    warning_days: int


@dataclass(frozen=True)
class FreshnessRules:
    temperature_hot_threshold_c: float
    temperature_critical_threshold_c: float
    temperature_exposure_limit_seconds: int
    temperature_continuity_gap_seconds: int
    gas_baseline_sample_count: int
    gas_anomaly_deviation_ratio: float
    gas_required_consecutive_readings: int
    humidity_vegetable_min_pct: float
    humidity_vegetable_max_pct: float
    humidity_fruit_min_pct: float
    humidity_fruit_max_pct: float
    door_open_timeout_seconds: int
    storage_profiles: Mapping[FoodCategory, StorageProfile]
    expiry_use_soon_window_days: int


DEFAULT_RULES = FreshnessRules(
    temperature_hot_threshold_c=5.0,
    temperature_critical_threshold_c=12.0,
    temperature_exposure_limit_seconds=2 * 60 * 60,
    temperature_continuity_gap_seconds=10,
    gas_baseline_sample_count=10,
    gas_anomaly_deviation_ratio=0.30,
    gas_required_consecutive_readings=3,
    humidity_vegetable_min_pct=80,
    humidity_vegetable_max_pct=95,
    humidity_fruit_min_pct=80,
    humidity_fruit_max_pct=95,
    door_open_timeout_seconds=30,
    storage_profiles=MappingProxyType({
        FoodCategory.MEAT: StorageProfile(3, 1),
        FoodCategory.DAIRY: StorageProfile(14, 1),
        FoodCategory.VEGETABLE: StorageProfile(7, 1),
        FoodCategory.FRUIT: StorageProfile(14, 1),
        FoodCategory.COOKED_FOOD: StorageProfile(4, 1),
    }),
    expiry_use_soon_window_days=1,
)


class FreshnessRuleProviderError(RuntimeError):
    """The persisted rule set is unavailable or internally inconsistent."""


def _default_rule_values(rules):
    values = {
        "temperature.hot_threshold_c": ("float", rules.temperature_hot_threshold_c),
        "temperature.critical_threshold_c": ("float", rules.temperature_critical_threshold_c),
        "temperature.exposure_limit_seconds": ("int", rules.temperature_exposure_limit_seconds),
        "temperature.continuity_gap_seconds": ("int", rules.temperature_continuity_gap_seconds),
        "gas.baseline_sample_count": ("int", rules.gas_baseline_sample_count),
        "gas.anomaly_increase_pct": ("float_pct", rules.gas_anomaly_deviation_ratio * 100),
        "gas.anomaly_consecutive_readings": ("int", rules.gas_required_consecutive_readings),
        "humidity.vegetable.min_pct": ("float", rules.humidity_vegetable_min_pct),
        "humidity.vegetable.max_pct": ("float", rules.humidity_vegetable_max_pct),
        "humidity.fruit.min_pct": ("float", rules.humidity_fruit_min_pct),
        "humidity.fruit.max_pct": ("float", rules.humidity_fruit_max_pct),
        "door.open_duration_seconds": ("int", rules.door_open_timeout_seconds),
        "expiry.use_soon_window_days": ("int", rules.expiry_use_soon_window_days),
    }
    for category, profile in rules.storage_profiles.items():
        values[f"storage.{category.value}.max_duration_days"] = ("int", profile.max_duration_days)
        values[f"storage.{category.value}.warning_days"] = ("int", profile.warning_days)
    return values


DEFAULT_RULE_VALUES = _default_rule_values(DEFAULT_RULES)
RULE_KEYS = frozenset(DEFAULT_RULE_VALUES)


def seed_default_rules(connection):
    """Insert missing defaults without overwriting existing persisted values."""
    connection.executemany(
        "INSERT OR IGNORE INTO freshness_rules "
        "(rule_key, rule_value, value_type) VALUES (?, ?, ?)",
        ((key, str(value), value_type)
         for key, (value_type, value) in DEFAULT_RULE_VALUES.items()),
    )


def rules_as_dict(rules):
    """Return the public, human-readable representation of one snapshot."""
    return {
        "temperature": {
            "hot_threshold_c": rules.temperature_hot_threshold_c,
            "critical_threshold_c": rules.temperature_critical_threshold_c,
            "exposure_limit_seconds": rules.temperature_exposure_limit_seconds,
            "continuity_gap_seconds": rules.temperature_continuity_gap_seconds,
        },
        "gas": {
            "baseline_sample_count": rules.gas_baseline_sample_count,
            "anomaly_increase_pct": rules.gas_anomaly_deviation_ratio * 100,
            "anomaly_consecutive_readings": rules.gas_required_consecutive_readings,
        },
        "humidity": {
            "vegetable": {"min_pct": rules.humidity_vegetable_min_pct, "max_pct": rules.humidity_vegetable_max_pct},
            "fruit": {"min_pct": rules.humidity_fruit_min_pct, "max_pct": rules.humidity_fruit_max_pct},
        },
        "door": {"open_duration_seconds": rules.door_open_timeout_seconds},
        "storage": {
            category.value: {
                "max_duration_days": profile.max_duration_days,
                "warning_days": profile.warning_days,
            }
            for category, profile in rules.storage_profiles.items()
        },
        "expiry": {"use_soon_window_days": rules.expiry_use_soon_window_days},
    }


def _parse_rule_rows(rows):
    values = {}
    for row in rows:
        key = row["rule_key"]
        if key not in RULE_KEYS or row["value_type"] != DEFAULT_RULE_VALUES[key][0]:
            raise FreshnessRuleProviderError(f"Invalid freshness rule metadata: {key}")
        raw = row["rule_value"]
        try:
            if row["value_type"] == "int":
                value = int(raw)
                if float(raw) != value:
                    raise ValueError
            else:
                value = float(raw)
                if not math.isfinite(value):
                    raise ValueError
                if row["value_type"] == "float_pct":
                    value /= 100
        except (TypeError, ValueError, OverflowError):
            raise FreshnessRuleProviderError(f"Invalid freshness rule value: {key}") from None
        values[key] = value
    if set(values) != RULE_KEYS:
        missing = sorted(RULE_KEYS - set(values))
        raise FreshnessRuleProviderError(f"Incomplete freshness rules; missing: {', '.join(missing)}")

    storage = {
        category: StorageProfile(
            int(values[f"storage.{category.value}.max_duration_days"]),
            int(values[f"storage.{category.value}.warning_days"]),
        ) for category in FoodCategory
    }
    if values["temperature.hot_threshold_c"] >= values["temperature.critical_threshold_c"]:
        raise FreshnessRuleProviderError(
            "Invalid freshness rule relationship: temperature.hot_threshold_c must be below temperature.critical_threshold_c"
        )
    return FreshnessRules(
        temperature_hot_threshold_c=values["temperature.hot_threshold_c"],
        temperature_critical_threshold_c=values["temperature.critical_threshold_c"],
        temperature_exposure_limit_seconds=int(values["temperature.exposure_limit_seconds"]),
        temperature_continuity_gap_seconds=int(values["temperature.continuity_gap_seconds"]),
        gas_baseline_sample_count=int(values["gas.baseline_sample_count"]),
        gas_anomaly_deviation_ratio=values["gas.anomaly_increase_pct"],
        gas_required_consecutive_readings=int(values["gas.anomaly_consecutive_readings"]),
        humidity_vegetable_min_pct=values["humidity.vegetable.min_pct"],
        humidity_vegetable_max_pct=values["humidity.vegetable.max_pct"],
        humidity_fruit_min_pct=values["humidity.fruit.min_pct"],
        humidity_fruit_max_pct=values["humidity.fruit.max_pct"],
        door_open_timeout_seconds=int(values["door.open_duration_seconds"]),
        storage_profiles=MappingProxyType(storage),
        expiry_use_soon_window_days=int(values["expiry.use_soon_window_days"]),
    )


class FreshnessRuleProvider:
    """Return one immutable rule snapshot for a processing operation."""

    def __init__(self, rules=DEFAULT_RULES):
        if not isinstance(rules, FreshnessRules):
            raise TypeError("rules must be a FreshnessRules snapshot")
        if rules.temperature_hot_threshold_c >= rules.temperature_critical_threshold_c:
            raise FreshnessRuleProviderError(
                "temperature.hot_threshold_c must be below temperature.critical_threshold_c"
            )
        self._rules = rules

    def snapshot(self):
        return self._rules

    @classmethod
    def from_connection(cls, connection):
        try:
            rows = connection.execute(
                "SELECT rule_key, rule_value, value_type FROM freshness_rules"
            ).fetchall()
            return cls(_parse_rule_rows(rows))
        except FreshnessRuleProviderError:
            raise
        except Exception as exc:
            raise FreshnessRuleProviderError("Unable to load freshness rules") from exc


DEFAULT_RULE_PROVIDER = FreshnessRuleProvider()


def get_freshness_rules(connection=None):
    """Return one snapshot, loading the complete persisted set when supplied."""
    if connection is None:
        return DEFAULT_RULE_PROVIDER.snapshot()
    return FreshnessRuleProvider.from_connection(connection).snapshot()
