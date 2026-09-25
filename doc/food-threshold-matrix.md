# Food Threshold Matrix

The values below are copied from `FOOD_STORAGE_PROFILES` in `backend/app/services/freshness.py`. They are prototype storage profiles, not general food-safety standards.

| Category | Max Storage Duration | Warning Period | Fresh | Use Soon | Check Food |
| --- | ---: | ---: | --- | --- | --- |
| MEAT | 3 calendar days | 1 day | 0 to 1 days stored | 2 to 3 days stored | More than 3 days |
| DAIRY | 14 calendar days | 1 day | 0 to 12 days stored | 13 to 14 days stored | More than 14 days |
| VEGETABLE | 7 calendar days | 1 day | 0 to 5 days stored | 6 to 7 days stored | More than 7 days |
| FRUIT | 14 calendar days | 1 day | 0 to 12 days stored | 13 to 14 days stored | More than 14 days |
| COOKED_FOOD | 4 calendar days | 1 day | 0 to 2 days stored | 3 to 4 days stored | More than 4 days |

## Boundary behavior

The engine computes `duration_days = (today - inserted_at_date).days` using calendar dates. It returns Use Soon when `duration_days >= max_duration_days - warning_days` and `duration_days <= max_duration_days`. The exact maximum day is therefore **Use Soon**. Check Food begins only when storage duration is greater than the maximum. A future `inserted_at` date is invalid and returns Check Food.

If `category` or `inserted_at` is missing, the storage-duration rule is skipped and contributes Fresh / Normal. An unrecognized category or invalid insertion date returns Check Food. Category names are the exact enum values listed in the table.

## Data model / input meaning

- `inserted_at` is the date FreshGuard starts tracking/storing the food item for this duration rule.
- `manufacture_date` is recorded by the Food API but is not used by the Freshness Engine's storage-duration calculation.
- `expiry_date` is evaluated by a separate rule; it does not change the profile's maximum duration or warning period.

## Current Prototype Limitations

- These category durations and warning periods are fixed prototype configuration in `FOOD_STORAGE_PROFILES`; they are not asserted as general food-safety guidance.
- The duration rule uses whole calendar-day difference, not elapsed hours or a temperature-adjusted storage model.
- Per-category values are currently only maximum duration and warning period. Category-specific temperature, humidity, or gas thresholds are **Not implemented yet**.
- If category or `inserted_at` is absent, this rule contributes no warning; it does not infer a category or start date.
- `manufacture_date` does not currently affect freshness status.
