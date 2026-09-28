from datetime import date, datetime
from enum import Enum
import math

from app.services.rule_provider import (
    FoodCategory,
    get_freshness_rules,
)

FRESH_SEVERITY = 0
USE_SOON_SEVERITY = 1
CHECK_FOOD_SEVERITY = 2


# Compatibility view for callers that imported the old module-level name.
FOOD_STORAGE_PROFILES = get_freshness_rules().storage_profiles
DOOR_OPEN_TIMEOUT_SECONDS = get_freshness_rules().door_open_timeout_seconds


class FreshnessStatus(Enum):
    FRESH = "Fresh / Normal"
    USE_SOON = "Use Soon"
    CHECK_FOOD = "Check Food"


class FreshnessResult:
    def __init__(self, status, reason):
        self.status = status
        self.reason = reason

    @property
    def severity(self):
        return {
            FreshnessStatus.FRESH: FRESH_SEVERITY,
            FreshnessStatus.USE_SOON: USE_SOON_SEVERITY,
            FreshnessStatus.CHECK_FOOD: CHECK_FOOD_SEVERITY,
        }[self.status]


def severity_to_status(severity):
    return {
        FRESH_SEVERITY: FreshnessStatus.FRESH,
        USE_SOON_SEVERITY: FreshnessStatus.USE_SOON,
        CHECK_FOOD_SEVERITY: FreshnessStatus.CHECK_FOOD,
    }[severity]


def _is_finite_number(value):
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    try:
        return math.isfinite(value)
    except (OverflowError, TypeError):
        return False


def _evaluate_temperature_rule(temperature_c, exposure_hours=0, rules=None):
    rules = rules or get_freshness_rules()
    if temperature_c is None:
        return CHECK_FOOD_SEVERITY, "Temperature sensor fault."

    if not _is_finite_number(temperature_c):
        return CHECK_FOOD_SEVERITY, "Invalid temperature value."

    if not _is_finite_number(exposure_hours) or exposure_hours < 0:
        return CHECK_FOOD_SEVERITY, "Invalid temperature exposure duration."

    if temperature_c > rules.temperature_critical_threshold_c:
        return CHECK_FOOD_SEVERITY, "Critical Temperature: temperature is too high."

    warning = ""
    if temperature_c > 8:
        warning = "High Temperature Warning."
    elif temperature_c > rules.temperature_hot_threshold_c:
        warning = "Temperature Warning."

    if temperature_c <= rules.temperature_hot_threshold_c:
        return FRESH_SEVERITY, ""

    if exposure_hours <= rules.temperature_exposure_limit_seconds / 3600:
        return FRESH_SEVERITY, warning

    limit_hours = rules.temperature_exposure_limit_seconds / 3600
    return CHECK_FOOD_SEVERITY, f"Temperature exposure exceeded {limit_hours:g} hours."


def evaluate_temperature(temperature_c, exposure_hours=0, rules=None):
    severity, reason = _evaluate_temperature_rule(temperature_c, exposure_hours, rules)
    return FreshnessResult(severity_to_status(severity), reason)


def _evaluate_humidity_rule(humidity_pct, category=None, rules=None):
    rules = rules or get_freshness_rules()
    if humidity_pct is None:
        return CHECK_FOOD_SEVERITY, "Humidity sensor fault."
    if not _is_finite_number(humidity_pct):
        return CHECK_FOOD_SEVERITY, "Invalid humidity value."
    try:
        category = category if isinstance(category, FoodCategory) else FoodCategory(category)
    except (TypeError, ValueError):
        category = None
    if category in (FoodCategory.VEGETABLE, FoodCategory.FRUIT):
        if humidity_pct < (rules.humidity_vegetable_min_pct if category == FoodCategory.VEGETABLE else rules.humidity_fruit_min_pct):
            return FRESH_SEVERITY, "Low humidity warning."
        if humidity_pct > (rules.humidity_vegetable_max_pct if category == FoodCategory.VEGETABLE else rules.humidity_fruit_max_pct):
            return FRESH_SEVERITY, "High humidity warning."
    return FRESH_SEVERITY, ""


def evaluate_humidity(humidity_pct, category=None, rules=None):
    severity, reason = _evaluate_humidity_rule(humidity_pct, category, rules)
    return FreshnessResult(severity_to_status(severity), reason)


def _evaluate_gas_rule(gas_raw, anomaly_active=False):
    if gas_raw is None:
        return CHECK_FOOD_SEVERITY, "Gas sensor data unavailable."
    if not _is_finite_number(gas_raw):
        return CHECK_FOOD_SEVERITY, "Invalid gas sensor data."
    if gas_raw < 0:
        return CHECK_FOOD_SEVERITY, "Invalid gas sensor data."
    if anomaly_active:
        return CHECK_FOOD_SEVERITY, "Gas level is significantly above baseline."
    return FRESH_SEVERITY, ""


def evaluate_gas(gas_raw):
    severity, reason = _evaluate_gas_rule(gas_raw)
    return FreshnessResult(severity_to_status(severity), reason)


def _evaluate_door_rule(door_open, open_duration_seconds, rules=None):
    rules = rules or get_freshness_rules()
    if door_open is None:
        return CHECK_FOOD_SEVERITY, "Door sensor fault."

    if not isinstance(door_open, bool):
        return CHECK_FOOD_SEVERITY, "Invalid door state."

    if not door_open:
        return FRESH_SEVERITY, ""

    if not _is_finite_number(open_duration_seconds) or open_duration_seconds < 0:
        return CHECK_FOOD_SEVERITY, "Invalid door open duration."

    if open_duration_seconds >= rules.door_open_timeout_seconds:
        return CHECK_FOOD_SEVERITY, "Door has exceeded the maximum open duration."

    return FRESH_SEVERITY, "Door is open."


def _to_calendar_date(inserted_at):
    if isinstance(inserted_at, datetime):
        return inserted_at.date()
    if isinstance(inserted_at, date):
        return inserted_at
    if isinstance(inserted_at, str):
        try:
            return date.fromisoformat(inserted_at)
        except ValueError:
            return datetime.fromisoformat(inserted_at).date()
    raise ValueError("Unsupported insertion date")


def _evaluate_storage_duration_rule(category, inserted_at, current_date=None, rules=None):
    rules = rules or get_freshness_rules()
    if category is None or inserted_at is None:
        return FRESH_SEVERITY, ""

    try:
        category = category if isinstance(category, FoodCategory) else FoodCategory(category)
    except (TypeError, ValueError):
        return CHECK_FOOD_SEVERITY, "Unknown food category."

    try:
        insertion_date = _to_calendar_date(inserted_at)
    except (TypeError, ValueError, OverflowError):
        return CHECK_FOOD_SEVERITY, "Invalid food insertion date."

    today = current_date or date.today()
    if isinstance(today, datetime):
        today = today.date()

    duration_days = (today - insertion_date).days
    if duration_days < 0:
        return CHECK_FOOD_SEVERITY, "Invalid food insertion date."

    profile = rules.storage_profiles[category]
    max_duration_days = profile.max_duration_days
    warning_days = profile.warning_days

    if duration_days > max_duration_days:
        return CHECK_FOOD_SEVERITY, "Food has exceeded the recommended storage duration."

    if duration_days >= max_duration_days - warning_days:
        return USE_SOON_SEVERITY, "Food is nearing the recommended storage duration."

    return FRESH_SEVERITY, ""


def _evaluate_expiry_rule(expiry_date, current_date=None, rules=None):
    rules = rules or get_freshness_rules()
    if expiry_date is None:
        return FRESH_SEVERITY, ""

    try:
        expiration_day = _to_calendar_date(expiry_date)
    except (TypeError, ValueError, OverflowError):
        return CHECK_FOOD_SEVERITY, "Invalid expiry date."

    today = current_date or date.today()
    if isinstance(today, datetime):
        today = today.date()

    days_until_expiry = (expiration_day - today).days

    if days_until_expiry < 0:
        return CHECK_FOOD_SEVERITY, "Food has passed its expiry date."

    if days_until_expiry <= rules.expiry_use_soon_window_days:
        return USE_SOON_SEVERITY, "Food is approaching its expiry date."

    return FRESH_SEVERITY, ""


def evaluate_door(door_open):
    if door_open is True:
        return FreshnessResult(FreshnessStatus.FRESH, "Door is open.")

    severity, reason = _evaluate_door_rule(door_open, 0)
    return FreshnessResult(severity_to_status(severity), reason)


def evaluate_door_timeout(door_open, open_duration_seconds, rules=None):
    severity, reason = _evaluate_door_rule(door_open, open_duration_seconds, rules)
    return FreshnessResult(severity_to_status(severity), reason)


def evaluate_freshness(
    temperature_c,
    humidity_pct,
    gas_raw,
    door_open,
    open_duration_seconds=0,
    category=None,
    inserted_at=None,
    expiry_date=None,
    temperature_exposure_hours=0,
    gas_anomaly_active=False,
    rules=None,
):
    rules = rules or get_freshness_rules()
    rule_results = (
        _evaluate_temperature_rule(temperature_c, temperature_exposure_hours, rules),
        _evaluate_humidity_rule(humidity_pct, category, rules),
        _evaluate_gas_rule(gas_raw, gas_anomaly_active),
        _evaluate_door_rule(door_open, open_duration_seconds, rules),
        _evaluate_storage_duration_rule(category, inserted_at, rules=rules),
        _evaluate_expiry_rule(expiry_date, rules=rules),
    )

    final_severity = max(severity for severity, _ in rule_results)
    reasons = [
        reason
        for severity, reason in rule_results
        if severity > FRESH_SEVERITY or reason
    ]

    return FreshnessResult(
        severity_to_status(final_severity),
        "; ".join(reasons) if reasons else "All sensor readings are available"
    )
