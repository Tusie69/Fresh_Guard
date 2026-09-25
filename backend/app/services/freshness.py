from enum import Enum
from datetime import date, datetime
import math


DOOR_OPEN_TIMEOUT_SECONDS = 30

FRESH_SEVERITY = 0
USE_SOON_SEVERITY = 1
CHECK_FOOD_SEVERITY = 2


class FoodCategory(Enum):
    MEAT = "MEAT"
    DAIRY = "DAIRY"
    VEGETABLE = "VEGETABLE"
    FRUIT = "FRUIT"
    COOKED_FOOD = "COOKED_FOOD"


# Prototype profiles for FreshGuard; these are not general food-safety standards.
FOOD_STORAGE_PROFILES = {
    FoodCategory.MEAT: {"max_duration_days": 3, "warning_days": 1},
    FoodCategory.DAIRY: {"max_duration_days": 14, "warning_days": 1},
    FoodCategory.VEGETABLE: {"max_duration_days": 7, "warning_days": 1},
    FoodCategory.FRUIT: {"max_duration_days": 14, "warning_days": 1},
    FoodCategory.COOKED_FOOD: {"max_duration_days": 4, "warning_days": 1},
}


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


def _evaluate_temperature_rule(temperature_c):
    if temperature_c is None:
        return CHECK_FOOD_SEVERITY, "Temperature sensor fault."

    if not _is_finite_number(temperature_c):
        return CHECK_FOOD_SEVERITY, "Invalid temperature value."

    if temperature_c <= 8:
        return FRESH_SEVERITY, ""

    if temperature_c <= 12:
        return USE_SOON_SEVERITY, "Temperature is in the Use Soon range."

    return CHECK_FOOD_SEVERITY, "Temperature is above the Check Food threshold."


def evaluate_temperature(temperature_c):
    severity, reason = _evaluate_temperature_rule(temperature_c)
    return FreshnessResult(severity_to_status(severity), reason)


def _evaluate_humidity_rule(humidity_pct):
    if humidity_pct is None:
        return CHECK_FOOD_SEVERITY, "Humidity sensor fault."
    if not _is_finite_number(humidity_pct):
        return CHECK_FOOD_SEVERITY, "Invalid humidity value."
    return FRESH_SEVERITY, ""


def evaluate_humidity(humidity_pct):
    severity, reason = _evaluate_humidity_rule(humidity_pct)
    return FreshnessResult(severity_to_status(severity), reason)


def _evaluate_gas_rule(gas_raw):
    if gas_raw is None:
        return CHECK_FOOD_SEVERITY, "Gas sensor fault."
    if not _is_finite_number(gas_raw):
        return CHECK_FOOD_SEVERITY, "Invalid gas reading."
    return FRESH_SEVERITY, ""


def evaluate_gas(gas_raw):
    severity, reason = _evaluate_gas_rule(gas_raw)
    return FreshnessResult(severity_to_status(severity), reason)


def _evaluate_door_rule(door_open, open_duration_seconds):
    if door_open is None:
        return CHECK_FOOD_SEVERITY, "Door sensor fault."

    if not isinstance(door_open, bool):
        return CHECK_FOOD_SEVERITY, "Invalid door state."

    if not door_open:
        return FRESH_SEVERITY, ""

    if not _is_finite_number(open_duration_seconds) or open_duration_seconds < 0:
        return CHECK_FOOD_SEVERITY, "Invalid door open duration."

    if open_duration_seconds >= DOOR_OPEN_TIMEOUT_SECONDS:
        return CHECK_FOOD_SEVERITY, "Door has exceeded the maximum open duration."

    return USE_SOON_SEVERITY, "Door has been open for too long."


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


def _evaluate_storage_duration_rule(category, inserted_at, current_date=None):
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

    profile = FOOD_STORAGE_PROFILES[category]
    max_duration_days = profile["max_duration_days"]
    warning_days = profile["warning_days"]

    if duration_days > max_duration_days:
        return CHECK_FOOD_SEVERITY, "Food has exceeded the recommended storage duration."

    if duration_days >= max_duration_days - warning_days:
        return USE_SOON_SEVERITY, "Food is nearing the recommended storage duration."

    return FRESH_SEVERITY, ""


def _evaluate_expiry_rule(expiry_date, current_date=None):
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

    if days_until_expiry <= 1:
        return USE_SOON_SEVERITY, "Food is approaching its expiry date."

    return FRESH_SEVERITY, ""


def evaluate_door(door_open):
    if door_open is True:
        return FreshnessResult(FreshnessStatus.USE_SOON, "Door is open.")

    severity, reason = _evaluate_door_rule(door_open, 0)
    return FreshnessResult(severity_to_status(severity), reason)


def evaluate_door_timeout(door_open, open_duration_seconds):
    severity, reason = _evaluate_door_rule(door_open, open_duration_seconds)
    return FreshnessResult(severity_to_status(severity), reason)


def evaluate_freshness(
    temperature_c,
    humidity_pct,
    gas_raw,
    door_open,
    open_duration_seconds=0,
    category=None,
    inserted_at=None,
    expiry_date=None
):
    rule_results = (
        _evaluate_temperature_rule(temperature_c),
        _evaluate_humidity_rule(humidity_pct),
        _evaluate_gas_rule(gas_raw),
        _evaluate_door_rule(door_open, open_duration_seconds),
        _evaluate_storage_duration_rule(category, inserted_at),
        _evaluate_expiry_rule(expiry_date),
    )

    final_severity = max(severity for severity, _ in rule_results)
    reasons = [
        reason
        for severity, reason in rule_results
        if severity > FRESH_SEVERITY
    ]

    return FreshnessResult(
        severity_to_status(final_severity),
        "; ".join(reasons) if reasons else "All sensor readings are available"
    )
