from enum import Enum



DOOR_OPEN_TIMEOUT_SECONDS = 30

class FreshnessStatus(Enum):
    FRESH = "Fresh / Normal"
    USE_SOON = "Use Soon"
    CHECK_FOOD = "Check Food"


class FreshnessResult:
    def __init__(self, status, reason):
        self.status = status
        self.reason = reason


def evaluate_temperature(temperature_c):
    if temperature_c is None:
        return FreshnessResult(
            FreshnessStatus.CHECK_FOOD,
            "Temperature sensor fault"
        )

    if temperature_c <= 8:
        return FreshnessResult(
            FreshnessStatus.FRESH,
            "Temperature is within safe range"
        )

    if temperature_c <= 12:
        return FreshnessResult(
            FreshnessStatus.USE_SOON,
            "Temperature is above normal range"
        )

    return FreshnessResult(
        FreshnessStatus.CHECK_FOOD,
        "Temperature is too high"
    )

def evaluate_humidity(humidity_pct):
    if humidity_pct is None:
        return FreshnessResult(
            FreshnessStatus.CHECK_FOOD,
            "Humidity sensor fault"
        )

    return FreshnessResult(
        FreshnessStatus.FRESH,
        "Humidity reading available"
    )

def evaluate_gas(gas_raw):
    if gas_raw is None:
        return FreshnessResult(
            FreshnessStatus.CHECK_FOOD,
            "Gas sensor fault"
        )

    return FreshnessResult(
        FreshnessStatus.FRESH,
        "Gas reading available"
    )

def evaluate_freshness(
    temperature_c,
    humidity_pct,
    gas_raw,
    door_open,
    open_duration_seconds
):
    temperature_result = evaluate_temperature(temperature_c)

    if temperature_result.status == FreshnessStatus.CHECK_FOOD:
        return temperature_result

    humidity_result = evaluate_humidity(humidity_pct)

    if humidity_result.status == FreshnessStatus.CHECK_FOOD:
        return humidity_result

    gas_result = evaluate_gas(gas_raw)

    if gas_result.status == FreshnessStatus.CHECK_FOOD:
        return gas_result

    door_result = evaluate_door_timeout(
        door_open,
        open_duration_seconds
    )

    if door_result.status == FreshnessStatus.CHECK_FOOD:
        return door_result

    if temperature_result.status == FreshnessStatus.USE_SOON:
        return temperature_result

    if door_result.status == FreshnessStatus.USE_SOON:
        return door_result

    return FreshnessResult(
        FreshnessStatus.FRESH,
        "All sensor readings are available"
    )

def evaluate_door(door_open):
    if door_open is None:
        return FreshnessResult(
            FreshnessStatus.CHECK_FOOD,
            "Door sensor fault"
        )

    if door_open:
        return FreshnessResult(
            FreshnessStatus.USE_SOON,
            "Door is currently open"
        )

    return FreshnessResult(
        FreshnessStatus.FRESH,
        "Door is closed"
    )

def evaluate_door_timeout(door_open, open_duration_seconds):
    if door_open is None:
        return FreshnessResult(
            FreshnessStatus.CHECK_FOOD,
            "Door sensor fault"
        )

    if not door_open:
        return FreshnessResult(
            FreshnessStatus.FRESH,
            "Door is closed"
        )

    if open_duration_seconds >= DOOR_OPEN_TIMEOUT_SECONDS:
        return FreshnessResult(
            FreshnessStatus.CHECK_FOOD,
            "Door has been open too long"
        )

    return FreshnessResult(
        FreshnessStatus.USE_SOON,
        "Door is currently open"
    )