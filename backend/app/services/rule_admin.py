"""Validation and persistence helpers for the ADMIN FreshRules API."""

import math

from app.services.rule_provider import (
    DEFAULT_RULE_VALUES,
    FreshnessRuleProviderError,
    FoodCategory,
    RULE_KEYS,
    get_freshness_rules,
)


EDITABLE_RULE_KEYS = frozenset({
    key for key in RULE_KEYS
    if key.startswith("humidity.") or key.startswith("storage.")
    or key == "expiry.use_soon_window_days"
    or key == "temperature.exposure_limit_seconds"
    or key == "temperature.hot_threshold_c"
})
STATEFUL_EDITABLE_RULE_KEYS = frozenset({
    "temperature.exposure_limit_seconds",
    "temperature.hot_threshold_c",
})
STATELESS_EDITABLE_RULE_KEYS = EDITABLE_RULE_KEYS - STATEFUL_EDITABLE_RULE_KEYS
LOCKED_RULE_KEYS = RULE_KEYS - EDITABLE_RULE_KEYS


class RuleUpdateError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def _snapshot_values(rules):
    values = {
        "temperature.hot_threshold_c": rules.temperature_hot_threshold_c,
        "temperature.critical_threshold_c": rules.temperature_critical_threshold_c,
        "temperature.exposure_limit_seconds": rules.temperature_exposure_limit_seconds,
        "humidity.vegetable.min_pct": rules.humidity_vegetable_min_pct,
        "humidity.vegetable.max_pct": rules.humidity_vegetable_max_pct,
        "humidity.fruit.min_pct": rules.humidity_fruit_min_pct,
        "humidity.fruit.max_pct": rules.humidity_fruit_max_pct,
        "expiry.use_soon_window_days": rules.expiry_use_soon_window_days,
    }
    for category, profile in rules.storage_profiles.items():
        values[f"storage.{category.value}.max_duration_days"] = profile.max_duration_days
        values[f"storage.{category.value}.warning_days"] = profile.warning_days
    return values


def _is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _validate_value(key, value):
    value_type = DEFAULT_RULE_VALUES[key][0]
    if key == "temperature.hot_threshold_c":
        if not _is_number(value) or not 0 <= value <= 50:
            raise RuleUpdateError("INVALID_RULE_VALUE", f"Invalid temperature threshold for {key}")
        return float(value)
    if key.startswith("humidity."):
        if not _is_number(value) or not 0 <= value <= 100:
            raise RuleUpdateError("INVALID_RULE_VALUE", f"Invalid humidity value for {key}")
        return float(value)
    if value_type == "int":
        minimum = 1 if key == "temperature.exposure_limit_seconds" else 0
        if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
            raise RuleUpdateError("INVALID_RULE_VALUE", f"Invalid integer value for {key}")
        return value
    raise RuleUpdateError("INVALID_RULE_VALUE", f"Invalid value for {key}")


def validate_rule_changes(connection, changes):
    if not isinstance(changes, dict) or not changes:
        raise RuleUpdateError("INVALID_RULES", "At least one rule is required")
    try:
        current = get_freshness_rules(connection)
    except FreshnessRuleProviderError as exc:
        raise RuleUpdateError("FRESHNESS_RULES_UNAVAILABLE", str(exc)) from exc
    effective = _snapshot_values(current)
    validated = []
    for key, value in changes.items():
        if key not in RULE_KEYS:
            raise RuleUpdateError("UNKNOWN_RULE", f"Unknown rule: {key}")
        if key not in EDITABLE_RULE_KEYS:
            raise RuleUpdateError("RULE_NOT_EDITABLE", f"Rule is not editable: {key}")
        new_value = _validate_value(key, value)
        effective[key] = new_value
        validated.append((key, effective[key], new_value))

    for category in ("vegetable", "fruit"):
        minimum = effective[f"humidity.{category}.min_pct"]
        maximum = effective[f"humidity.{category}.max_pct"]
        if minimum >= maximum:
            raise RuleUpdateError("INVALID_RULE_VALUE", f"Humidity min must be below max for {category}")
    if effective["temperature.hot_threshold_c"] >= effective["temperature.critical_threshold_c"]:
        raise RuleUpdateError(
            "INVALID_RULE_VALUE",
            "Temperature hot threshold must be below critical threshold",
        )
    for category in FoodCategory:
        prefix = f"storage.{category.value}"
        if effective[f"{prefix}.warning_days"] > effective[f"{prefix}.max_duration_days"]:
            raise RuleUpdateError("INVALID_RULE_VALUE", f"Storage warning exceeds max for {category.value}")

    # Return the original persisted value alongside the normalized new value.
    old_values = _snapshot_values(current)
    return [(key, old_values[key], new_value) for key, _effective, new_value in validated]


def metadata_for_rules(rules):
    values = _snapshot_values(rules)
    result = {
        "humidity": {"vegetable": {}, "fruit": {}},
        "storage": {},
        "expiry": {},
        "temperature": {},
        "gas": {},
        "door": {},
    }
    for key, value in values.items():
        parts = key.split(".")
        cursor = result
        for part in parts[:-1]:
            cursor = cursor.setdefault(part, {})
        cursor[parts[-1]] = {"value": value, "editable": key in EDITABLE_RULE_KEYS}
    # Include locked rules in their public sections.
    locked = {
        "temperature.hot_threshold_c": rules.temperature_hot_threshold_c,
        "temperature.exposure_limit_seconds": rules.temperature_exposure_limit_seconds,
        "temperature.continuity_gap_seconds": rules.temperature_continuity_gap_seconds,
        "temperature.critical_threshold_c": rules.temperature_critical_threshold_c,
        "gas.baseline_sample_count": rules.gas_baseline_sample_count,
        "gas.anomaly_increase_pct": rules.gas_anomaly_deviation_ratio * 100,
        "gas.anomaly_consecutive_readings": rules.gas_required_consecutive_readings,
        "door.open_duration_seconds": rules.door_open_timeout_seconds,
    }
    for key, value in locked.items():
        section, field = key.split(".", 1)
        result[section][field] = {"value": value, "editable": key in EDITABLE_RULE_KEYS}
    return result


def reset_editable_rules(connection):
    """Return persisted editable rows that differ from DEFAULT_RULES."""
    rows = {
        row["rule_key"]: row
        for row in connection.execute(
            "SELECT rule_key, rule_value, value_type FROM freshness_rules"
        ).fetchall()
    }
    changes = []
    for key in sorted(STATELESS_EDITABLE_RULE_KEYS):
        row = rows.get(key)
        if row is None:
            raise RuleUpdateError("FRESHNESS_RULES_UNAVAILABLE", f"Missing rule: {key}")
        value_type, default_value = DEFAULT_RULE_VALUES[key]
        try:
            current = float(row["rule_value"]) if value_type == "float" else int(row["rule_value"])
        except (TypeError, ValueError):
            raise RuleUpdateError("FRESHNESS_RULES_UNAVAILABLE", f"Invalid rule: {key}") from None
        if current != default_value:
            changes.append((key, row["rule_value"], str(default_value), value_type))
    return changes
