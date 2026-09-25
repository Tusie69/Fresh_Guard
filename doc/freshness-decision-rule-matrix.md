# Freshness Decision Rule Matrix

This document describes the rules implemented in `backend/app/services/freshness.py`. The engine is the source of truth for the thresholds and outcomes below. These prototype profiles are not general food-safety standards.

## Status and severity

| Severity | Status |
| ---: | --- |
| 0 | Fresh / Normal |
| 1 | Use Soon |
| 2 | Check Food |

The engine maps severity to status through `severity_to_status()`. `evaluate_freshness()` evaluates all six rule groups and selects the maximum severity.

## Sensor validity

Numeric sensor inputs must be finite `int` or `float` values; booleans are not accepted as numeric values.

| Input | `None` behavior | Other invalid input behavior |
| --- | --- | --- |
| Temperature | Severity 2, `Temperature sensor fault.` | Severity 2, `Invalid temperature value.` |
| Humidity | Severity 2, `Humidity sensor fault.` | Severity 2, `Invalid humidity value.` |
| Gas | Severity 2, `Gas sensor fault.` | Severity 2, `Invalid gas reading.` |
| Door state | Severity 2, `Door sensor fault.` | Severity 2, `Invalid door state.` unless it is exactly `True` or `False` |

For an open door, `open_duration_seconds` must be finite and non-negative. Otherwise the door rule returns severity 2 with `Invalid door open duration.` A closed door returns severity 0 without checking the duration value.

## Temperature

| Temperature | Severity | Status |
| --- | ---: | --- |
| `temperature_c <= 8` | 0 | Fresh / Normal |
| `8 < temperature_c <= 12` | 1 | Use Soon |
| `temperature_c > 12` | 2 | Check Food |

The boundaries are inclusive as shown: exactly 8 is Fresh / Normal; exactly 12 is Use Soon.

## Humidity

Humidity has an availability and finite-number validity check only. Any finite numeric value, including values outside the usual 0-100 percentage range, returns severity 0. A humidity quality threshold is **Not implemented yet**.

## Gas

Gas has an availability and finite-number validity check only. Any finite numeric `gas_raw` value returns severity 0. A calibrated gas or ppm threshold is **Not implemented yet**.

## Door

`DOOR_OPEN_TIMEOUT_SECONDS` is 30 seconds. In `evaluate_freshness()` the rule behaves as follows:

| Door state | Duration | Severity | Status |
| --- | --- | ---: | --- |
| Closed (`False`) | Any value; ignored by this rule | 0 | Fresh / Normal |
| Open (`True`) | `0 <= duration < 30` seconds | 1 | Use Soon |
| Open (`True`) | `duration >= 30` seconds | 2 | Check Food |

Thus, exactly 30 seconds is Check Food. The standalone compatibility helper `evaluate_door(door_open)` has no duration argument and reports an open door as Use Soon; `evaluate_freshness()` uses the timeout rule above.

## Food storage duration

The storage-duration rule runs only when both `category` and `inserted_at` are provided. A missing category or insertion date skips this rule at severity 0. Unknown categories and invalid insertion dates return severity 2.

The engine converts `inserted_at` to a calendar date, then calculates whole calendar days as `(today - insertion_date).days`; it does not calculate elapsed hours. A future insertion date is invalid and returns severity 2. For each category, the warning period is one day:

| Duration in calendar days | Severity | Status |
| --- | ---: | --- |
| `< max_duration_days - warning_days` | 0 | Fresh / Normal |
| `max_duration_days - warning_days` through `max_duration_days`, inclusive | 1 | Use Soon |
| `> max_duration_days` | 2 | Check Food |

Consequently, the exact maximum storage day is Use Soon; Check Food begins the next calendar day.

## Expiry

The expiry rule converts a supported `expiry_date` to a calendar date and compares it with today:

| Expiry value | Severity | Status |
| --- | ---: | --- |
| Missing (`None`) | 0 | Fresh / Normal |
| Today | 1 | Use Soon |
| Tomorrow | 1 | Use Soon |
| Later than tomorrow | 0 | Fresh / Normal |
| Before today | 2 | Check Food |
| Invalid / unsupported date | 2 | Check Food |

Expiry on the current day is not considered past expiry. Invalid values return `Invalid expiry date.`

## Aggregation and reasons

The final severity is the maximum severity returned by the temperature, humidity, gas, door, storage-duration, and expiry rules. For example, Temperature = Fresh, Storage Duration = Use Soon, and Expiry = Fresh produce final status **Use Soon**.

Every rule with severity greater than 0 contributes its reason, joined with `; ` in rule order. Multiple warnings and faults are therefore retained together. If every rule is severity 0, the reason is `All sensor readings are available`.

## Data model / input meaning

- `inserted_at` is the date FreshGuard uses as the beginning of tracked storage for the food item.
- `manufacture_date` is stored by the Food API, but the Freshness Engine does not receive or use it.
- `expiry_date` is an independent input to the expiry rule.

## Current Prototype Limitations

- Humidity quality thresholds are **Not implemented yet**; finite numeric values are treated as available.
- A calibrated gas/ppm threshold is **Not implemented yet**; `gas_raw` is checked for presence and numeric validity only.
- Storage and expiry rules use calendar dates and the host's `date.today()` when no test date is injected internally; they do not use elapsed-time freshness calculations.
- Missing food category/insertion date skips the storage-duration rule, and missing expiry date skips the expiry rule.
- Storage profiles are prototype configuration in code and are explicitly not general food-safety standards.
- Door timeout and temperature limits are fixed constants/branches in the current engine; no runtime profile-specific sensor thresholds are implemented.
