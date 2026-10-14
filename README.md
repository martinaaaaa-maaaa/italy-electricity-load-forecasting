# italy-electricity-load-forecasting
 Beating the grid operator: forecasting Italy’s electricity demand

## Goal
Build a model that forecasts Italy's day-ahead electricity demand and compare it with Terna's own published forecast, using only information available at forecast time.

**Current phase:** build one clean hourly dataset (2022–2025, if data allows) with:
- actual Italian electricity demand
- Terna's day-ahead forecast
- weather for six cities (Milano, Torino, Bologna, Roma, Napoli, Palermo)
- calendar and holiday information
- past demand features (e.g. same hour 7 and 14 days earlier), built without leakage

## Team and responsibilities
| Part | Owner | Output |
|---|---|---|
| Electricity data (ENTSO-E) | [Marco] | `electricity_clean.csv` + notebook |
| Weather (Open-Meteo) | [Francesco] | `weather_clean.csv` + notebook |
| Calendar features | [Tomas] | `calendar_features.csv` + notebook |
| Data quality and exploration | [Giovanni] | `data_quality_report.ipynb` |
| Integration, features, coordination | [Martina] | `modeling_dataset.csv` + script |

[See after ## Notes paragraph for guidelines]

## Rules for everyone
1. All timestamps in UTC, format `2025-07-10T14:00:00Z`.
2. Never edit original data: raw files go in `data/raw/`, cleaned files in `data/processed/`.
3. Never fill missing values with zero. Missing is not zero.
4. Never use information that was not available at forecast time (data leakage).
5. Don't delete rows with missing values before analysing them.
6. Column names in English, lowercase, with underscores.
7. Document every change you make to the data.
8. Don't aim for a dataset with zero missing values. Report gaps.

## Working with the repo
- Each person works in their own folder: `notebooks/[name]/`.
- Before you start: **pull**. When you finish: **commit** and **push**.
- No branches or pull requests for now, work on the main branch.
- Never put tokens, passwords or `.env` files in the repo.

## Timeline
November 2nd

## Notes
For the final day-ahead model we need *archived* weather forecasts, not observed weather. [Open-Meteo coverage: to be checked.]

## Electricity variables
Source: ENTSO-E Transparency Platform (Actual Total Load and Day-ahead Total Load Forecast, Italy).

| Variable | Column | Unit |
|---|---|---|
| Time (key) | `timestamp_utc` | UTC, format `2025-07-10T14:00:00Z` |
| Actual national demand | `actual_load_mw` | MW |
| Terna's day-ahead forecast | `terna_forecast_mw` | MW |

Steps:
1. Download both series for 2022–2025 (if available) and save them untouched in `data/raw/`.
2. Check the original frequency (15, 30 or 60 minutes).
3. Convert timestamps to UTC.
4. Convert to hourly. If the values are average power in MW, take the **mean** of the sub-hourly values, not the sum. If they are energy in MWh, the procedure is different: ask before converting.
5. Check that both series cover the **same national perimeter** (Italy as a whole, not a single market zone).
6. Check for missing hours, NaN, duplicates and suspicious values.
7. Save `data/processed/electricity_clean.csv` and a short NaN report.

**How to deal with missing data**
1. **Never replace missing values with zero.**
2. **Never invent values.** No filling in, no interpolating, at this stage.
3. **Whole hour missing?** Add the row anyway, with empty (NaN) values.
4. **`actual_load_mw` missing?** Leave it empty.
5. **`terna_forecast_mw` missing?** Leave it empty. Don't use the actual demand instead.
6. **Only some 15-minute values missing in an hour?** Don't average the ones you have. Mark the hour as incomplete.
7. **Duplicate timestamps?** Check why before removing them. They could be the same record twice, or an updated version.
8. **Strange value?** Flag it. Don't delete it.
9. **Data not found?** First check your download (dates, settings). If it really isn't there, leave it empty.
10. **Write down** how many values are missing, where, and why (if you know).

## Weather variables
Same variables for all six cities, same naming pattern: `variable_city_unit`.

| Variable | Column example | Unit |
|---|---|---|
| Time (key) | `timestamp_utc` | UTC, format `2025-07-10T14:00:00Z` |
| Temperature | `temp_milano_c` | °C |
| Relative humidity | `humidity_milano_pct` | % |
| Cloud cover | `cloud_cover_milano_pct` | % |
| [Solar radiation (optional, to be confirmed)] | `solar_radiation_milano_wm2` | W/m² |

Notes:
- Daylight hours (day length) don't need to be downloaded: they depend only on date and latitude, so they are computed with the calendar features. 
- Observed weather and archived forecasts must be kept in **separate files**, and each column must be documented as one or the other.
- The final day-ahead model needs *archived forecasts*, not observed weather. 
- Possible later additions: precipitation, wind, apparent temperature.

Steps:
1. Download temperature, humidity and cloud cover for the six cities, for the same period as the electricity data. Save the files untouched in `data/raw/`.
2. Convert timestamps to UTC.
3. Check for missing hours, duplicates and impossible values.
4. Rename the columns following the pattern above.
5. Save `data/processed/weather_clean.csv` and a short NaN report.

Output: `weather_clean.csv` (`timestamp_utc` + the weather columns) + notebook with temperature plots. [Archived forecasts go in a separate file: `issue_time_utc`, `target_time_utc`, `city` + forecast variables. To be confirmed once we know what Open-Meteo offers.]

**How to deal with missing data**
1. **Never replace missing values with zero.** For rain, zero means "no rain", not "unknown".
2. **Never invent values.** No filling in, no interpolating, at this stage.
3. **Whole hour missing?** Keep the row, with empty (NaN) values.
4. **Only 1–2 hours missing?** Don't fix them yet. Report them.
5. **Many hours missing?** First check your download (dates, city, settings). If the data really isn't there, leave it empty.
6. **Observed vs forecast:** keep them in separate files. Never use observed weather to fill in forecast data.
7. **Different forecast runs?** Don't mix them unless you write down the rule you used to choose.
8. **Write down** how many values are missing, where, and why (if you know).

## Calendar features
Output: `data/processed/calendar_features.csv`, one row per hour of the period.

| Column | Meaning |
|---|---|
| `timestamp_utc` | Key. Same format as the other files |
| `hour_local` | Hour in Italian local time (Europe/Rome) |
| `day_of_week` | 0–6 [confirm: Monday = 0] |
| `month` | 1–12 |
| `year` | |
| `is_weekend` | 0/1 |
| `is_holiday` | 0/1, Italian public holidays |
| `is_summer` | 0/1 [define the months] |
| `is_christmas_period` | 0/1 [define the dates] |
| [`daylight_hours`] | Day length, computed from date and latitude [if the team confirms] |

Steps:
1. Build a table with every hour of the period, with `timestamp_utc` as the key.
2. Compute calendar information in local time (Europe/Rome), starting from the UTC timestamp.
3. Use the `holidays` Python package for Italian public holidays.
4. Write down in the notebook how `is_summer` and `is_christmas_period` are defined.
5. Save `calendar_features.csv`.

Rules:
- Basic calendar features should have **no NaN**. If one is NaN, fix the code or the timestamp instead of filling it in.
- `is_holiday = 0` only if the day was checked and is not a holiday.
- Watch out for daylight saving time: on the changeover days some local hours are repeated or don't exist. Check that those days have the right number of hours and no duplicates.

## Data quality and exploration
This part checks the files produced by the others. It does **not** modify them.

Steps:
1. Start with the first months of electricity data, without waiting for the full dataset.
2. For each column, count missing values (number and %).
3. Look for missing and duplicated timestamps. Distinguish a **missing row** (the whole hour is absent) from a **NaN cell** (the row exists but the value is empty).
4. Find consecutive stretches of missing data. Say whether NaN are isolated or concentrated in specific periods.
5. Plot the distribution of demand, and average demand by hour, month and day of week.
6. Plot suspicious values and possible anomalies.
7. Write a short report of the problems found.

For each problem, report:
- column
- time interval
- number of values involved
- possible cause
- proposed correction (the implementation is left to the owner of that dataset)

Rules:
- Never edit other people's CSV files.
- Flag anomalies.

Output: `data_quality_report.ipynb` + `missing_values_report.csv` (`dataset, column, missing_count, missing_pct`) + 4–5 plots and a table of problems.

## Integration and features 
Goal: merge all files into one dataset for the model, without leakage.

Steps:
1. Fix the common format: `timestamp_utc`, units, column names.
2. Merge electricity, weather and calendar on `timestamp_utc`. Check that the merge doesn't create duplicates or lose hours.
3. Build past-demand features (e.g. same hour 7 and 14 days earlier).
4. Build simple benchmarks to beat: same hour last week, a seasonal baseline, and Terna's forecast.
5. For every feature, check that it was available at forecast time.
6. Save `src/features/build_dataset.py`, `modeling_dataset.csv` and a short report of the checks.

Missing data:
- Keep a version of the dataset with the original NaN.
- Don't use `dropna()` blindly.
- Exclude from training the rows without actual demand.
- To compare with Terna, use only hours where both values exist.
- Decide later whether to leave NaN, impute, or add a "missing" flag. Compute any imputation statistics on the training data only, never on the whole dataset.