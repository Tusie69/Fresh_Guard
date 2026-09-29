# Freshness Decision Rule Matrix

This document records the verified behavior of the current backend. The implementation is the source of truth; these prototype profiles are not general food-safety standards.

## Status, severity, and aggregation

| Severity | Status |
| ---: | --- |
| 0 | Fresh / Normal |
| 1 | Use Soon |
| 2 | Check Food |

`evaluate_freshness()` evaluates temperature, humidity, gas, door, storage duration, and expiry, then returns the maximum applicable severity. A warning in a reason string does not by itself raise the status to Use Soon. Reasons from applicable rules are joined with `; ` in rule order. If all rules are clear, the reason is `All sensor readings are available`.

## Persisted rules and configurability

The current database contains all 23 provider keys. The admin API exposes 17 editable rules and 6 locked rules.

| Rule family | Current value(s) | Persistence | Admin |
| --- | --- | --- | --- |
| Temperature hot threshold | 5.0°C | FreshRule | Editable |
| Temperature critical threshold | 12.0°C | FreshRule | Locked |
| Temperature exposure limit | 7200 seconds | FreshRule | Editable |
| Temperature continuity gap | 10 seconds | FreshRule | Locked |
| Gas baseline samples / increase / consecutive count | 10 / 30% / 3 | FreshRule | Locked |
| Humidity vegetable and fruit ranges | 80–95% | FreshRule | Editable |
| Door open timeout | 30 seconds | FreshRule | Locked |
| Storage profiles | see table below | FreshRule | Editable |
| Expiry Use Soon window | 1 calendar day | FreshRule | Editable |

## Sensor validity and faults

Numeric values must be finite `int` or `float`; booleans are not numeric sensor values. `None`/unavailable or malformed sensor values produce `Check Food` for that rule (`Temperature sensor fault.`, `Humidity sensor fault.`, `Gas sensor fault.`, or the corresponding invalid-value reason). For an open door, duration must also be finite and non-negative. A closed door ignores its duration value. Fault events are transition-based in the event/state layer; each freshness evaluation still treats the current fault as severity 2. A malformed API request is rejected by request validation and is not an accepted null sensor reading.

## Temperature

Current persisted values are hot threshold 5.0°C, critical threshold 12.0°C, exposure limit 7200 seconds, and continuity gap 10 seconds.

| Condition | Severity/status | Reason behavior |
| --- | --- | --- |
| `T <= hot_threshold_c` | 0 / Fresh / Normal | No temperature warning |
| `hot_threshold_c < T <= critical_threshold_c` and exposure `<=` limit | 0 / Fresh / Normal | Warning reason is returned |
| `hot_threshold_c < T <= critical_threshold_c` and exposure `>` limit | 2 / Check Food | Exposure exceeded reason |
| `T > critical_threshold_c` | 2 / Check Food | Critical temperature reason; exposure is irrelevant |

Temperature exposure is accumulated by `temperature_exposure.py` only between valid hot readings whose timestamp gap is greater than 0 and at most the 10-second continuity gap. A gap over 10 seconds, an invalid reading, or a non-increasing timestamp breaks continuity. A reading at or below the hot threshold resets exposure to zero. The limit is exceeded strictly when `exposure_seconds > exposure_limit_seconds`.

The 8°C distinction is **not a FreshRule** and is not configurable. It is a fixed reason-text branch in `_evaluate_temperature_rule()` in `backend/app/services/freshness.py`:

```python
if temperature_c > 8:
    warning = "High Temperature Warning."
elif temperature_c > rules.temperature_hot_threshold_c:
    warning = "Temperature Warning."
```

It changes only the warning text, not severity. It is therefore a legacy presentation/reason threshold, not a separate Use Soon threshold.

Verified boundaries:

| Temperature | Status | Reason |
| ---: | --- | --- |
| 5.0°C | Fresh / Normal | none |
| 5.1°C | Fresh / Normal | Temperature Warning. |
| 8.0°C | Fresh / Normal | Temperature Warning. |
| 8.1°C | Fresh / Normal | High Temperature Warning. |
| 12.0°C | Fresh / Normal | High Temperature Warning. |
| 12.1°C | Check Food | Critical Temperature: temperature is too high. |

## Humidity

For VEGETABLE and FRUIT, the configured inclusive target range is 80–95%. Values below the minimum return a `Low humidity warning.` and values above the maximum return a `High humidity warning.`; both remain severity 0 (`Fresh / Normal`) for the humidity rule. Other finite humidity values have no humidity reason. The overall reading can still become Use Soon or Check Food when another rule has greater severity.

## Gas

Gas state is maintained per device/food context by `gas_anomaly.py`:

1. The first 10 valid, non-negative finite readings learn the baseline.
2. After baseline completion, a reading at least 30% above baseline increments the consecutive anomaly count.
3. Three consecutive anomaly readings activate the anomaly.
4. A valid reading below the anomaly threshold resets the count and clears the active anomaly; invalid/missing readings reset the consecutive count but do not prove that an active anomaly ended.

While `gas_anomaly_active` is true, freshness returns severity 2 with `Gas level is significantly above baseline.`. Null, invalid, or negative gas data returns severity 2. A valid non-anomalous gas value contributes severity 0; no calibrated ppm limit is implemented.

## Door

The backend decision uses the persisted 30-second timeout:

| Door state | Duration | Severity/status | Reason |
| --- | --- | --- | --- |
| Closed | ignored | 0 / Fresh / Normal | none |
| Open | `0 <= duration < 30` seconds | 0 / Fresh / Normal | `Door is open.` |
| Open | `duration >= 30` seconds | 2 / Check Food | Maximum open duration exceeded |

The MC-38 firmware priority reading at 30 seconds is a transport/capture trigger. It is separate from, and does not replace, this backend freshness decision.

## Food storage duration

This rule runs only when both category and `inserted_at` are present. Missing values skip the rule at severity 0; unknown categories, invalid dates, and future insertion dates return Check Food. Duration is whole calendar days: `(today - insertion_date).days`.

| Category | Maximum | Warning window |
| --- | ---: | ---: |
| MEAT | 3 days | 1 day |
| DAIRY | 14 days | 1 day |
| VEGETABLE | 7 days | 1 day |
| FRUIT | 14 days | 1 day |
| COOKED_FOOD | 4 days | 1 day |

For each profile, `< max - warning` is Fresh / Normal, `max - warning` through `max` inclusive is Use Soon, and `> max` is Check Food.

## Expiry

Dates are compared as calendar dates using the configured one-day Use Soon window:

| Expiry date | Status |
| --- | --- |
| Before today | Check Food |
| Today or tomorrow | Use Soon |
| Later than tomorrow | Fresh / Normal |
| Missing | Fresh / Normal |
| Invalid/unsupported | Check Food |

## Multiple active foods

One ESP32 environmental reading is evaluated independently against every Active Food. The backend persists one `food_freshness_snapshot` per active food, and the top-level reading freshness is the worst (maximum severity) among those food evaluations. With zero Active Foods, the existing foodless environment evaluation is preserved. The ESP32 does not select one food ID for this decision.

## Remaining fixed behavior

The 8°C warning-text boundary is the remaining undocumented-style magic number identified by this audit. It does not change business severity. No other runtime or database rule was changed as part of this documentation alignment.
