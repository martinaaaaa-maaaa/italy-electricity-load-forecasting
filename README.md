# Italy day-ahead electricity load forecasting

Forecast Italian hourly electricity demand for local day D, using only information available at **10:00 Europe/Rome on day D-1**, and compare that forecast with Terna’s published day-ahead forecast. The target is national load in MW (`actual_load_mw`). A target day is every hour whose Europe/Rome date is D: 24 hours on a normal day, 23 on the spring-forward Sunday, and 25 on the fall-back Sunday.

The common rules are in [`task_briefing.ipynb`](task_briefing.ipynb). The code that implements them is [`split_config.py`](split_config.py).

## Status

**Completed**

- Hourly national load, Terna’s day-ahead forecast, calendar features, and six-city ERA5 weather for 2022–2025, merged into one modeling table.
- Shared chronological splits and leakage checks.
- Seasonal baselines, Tomas’s Ridge regression, two separate LightGBM point-forecast implementations (Marco and Martina), and Marco’s 80% prediction intervals.
- 2024 validation scores for those models. The 2025 test year has not been scored.

**Unresolved**

- The archived GFS weather file uses a cutoff that has not been accepted as the 10:00 Europe/Rome issuance. No forecast-weather model has been trained.
- Terna’s forecast vintage (the original day-ahead file versus a later revision) has not been checked.
- The Ridge model, the two LightGBM models, and the conformal model are not one shared training pipeline.
- Both interval methods cover less than their nominal 80% on 2024, especially on holidays.

**Proposed, not started**

- A consolidated error analysis.
- The single final evaluation on local year 2025.
- A 2020 lockdown extension, outside the 2022–2025 table.

## Forecasting protocol

Import dates, column names, and lag lengths from `split_config.py`. The functions `split` and `validation_index` return training and 2024 validation only. Local year 2025 stays closed until the project leader calls `final_test(df, confirm=True)` once, after the dataset and the chosen models are frozen.

| Slice | Europe/Rome dates | Role |
|---|---|---|
| Train | 2022-01-16 through 2023-12-31 | 17,160 hours. Fitting, hyperparameter search, and interval calibration. |
| Validation | 2024-01-01 through 2024-12-31 | 8,784 hours. The holdout used to compare models. |
| Test | 2025-01-01 through 2025-12-31 | Closed. |

Training starts on 16 January 2022 because that is the first complete local day on which every hour has a 336-hour history. Year boundaries follow local dates: `2023-12-31 23:00 UTC` is 1 January 2024 in Rome and belongs to validation. `2024-12-31 23:00 UTC` is 1 January 2025 in Rome and belongs to the test set.

Leakage rules enforced by the shared code:

- The issuance time is civil 10:00 Europe/Rome on D-1, including clock-change Sundays. It is that clock time, rather than midnight plus ten UTC hours.
- An hour is treated as published two hours after it starts. That is the Regulation 543/2013 deadline (one hour after the operating hour ends), not a measured ENTSO-E delay.
- Legal load lags are fixed UTC shifts of 48, 168, and 336 hours. A 24-hour lag is not legal for every hour of day D.
- Those shifts are model features. The seasonal naive baseline is a different object: the same Europe/Rome clock time seven local days earlier.
- Terna’s forecast is a benchmark. It is not a model feature.
- Anything fitted — encoders, hyperparameters, quantile models, conformal widths — is fitted on training days only. The 2024 scores are for comparison, not for choosing the model.

## Data

The modeling table is [`data/processed/dataset_no_weather.csv`](data/processed/dataset_no_weather.csv): 35,064 consecutive UTC hours from `2022-01-01 00:00Z` through `2025-12-31 23:00Z`, with no duplicate timestamps. It is the inner join, in [`notebooks/martina/merge_dataset.ipynb`](notebooks/martina/merge_dataset.ipynb), of:

| File | Contents |
|---|---|
| [`data/processed/electricity_clean.csv`](data/processed/electricity_clean.csv) | ENTSO-E actual total load and day-ahead total load forecast, area `10YIT-GRTN-----B`, both in MW. Built in [`notebooks/marco/01_electricity_data.ipynb`](notebooks/marco/01_electricity_data.ipynb). |
| [`data/processed/calendar_features.csv`](data/processed/calendar_features.csv) | Local calendar fields. Built in [`notebooks/tomas/calendar_features.ipynb`](notebooks/tomas/calendar_features.ipynb). |
| [`data/processed/weather_clean.csv`](data/processed/weather_clean.csv) | ERA5 for Milano, Torino, Bologna, Roma, Napoli, and Palermo: temperature, relative humidity, and cloud cover. Joined in the modeling notebooks. It is not stored inside `dataset_no_weather.csv`. |

Actual load has no missing hours. Terna’s forecast is missing for one hour, `2024-12-31T23:00:00Z` (local 1 January 2025, 00:00). A second API request covering that hour also returned no value. The cell is left empty. It sits in the test year, so the 2024 Terna benchmark is complete. See [`data/processed/electricity_missing_details.csv`](data/processed/electricity_missing_details.csv).

Hourly load is a duration-weighted mean of the native 15-minute or 60-minute ENTSO-E intervals. An hour is kept only when it has 60 minutes of non-missing coverage. The source series were not interpolated, zero-filled, or replaced with each other. [`data/processed/electricity_anomaly_flags.csv`](data/processed/electricity_anomaly_flags.csv) contains no flagged hours. Raw XML is gitignored and is not in the repository.

Calendar columns use Europe/Rome. Monday is 0. Weekend is Saturday and Sunday. `is_holiday` comes from the `holidays` package for Italy; the first Sunday of November is stored as 0. `is_summer` is June–August. `is_christmas_period` is 24 December through 6 January. There is no `daylight_hours` column. A comment in `split_config.py` still describes those November Sundays as holidays; the CSV, which the models use, does not.

[`notebooks/giovanni/data_quality_report.ipynb`](notebooks/giovanni/data_quality_report.ipynb) reviews `electricity_clean.csv`. The plots it writes under `quality_outputs/` are not committed.

## Models

### Seasonal baselines

Implemented in `split_config.py` and scored for 2024 in [`notebooks/marco/02_lightgbm_prediction_intervals.ipynb`](notebooks/marco/02_lightgbm_prediction_intervals.ipynb).

- **Seasonal naive:** load at the same Europe/Rome clock time seven days earlier. In 2024 the source hour does not exist for 7 April at 02:00, so that hour is omitted (`n = 8,783`). A repeated fall-back hour uses the earlier UTC instant.
- **Seasonal average:** mean load by local hour and weekday, estimated on the training rows available at the first 2024 cutoff.
- **Terna:** `terna_forecast_mw`, unchanged.

Separate baseline prediction files were not saved. The scores are in [`notebooks/marco/results/validation_baseline_comparison.csv`](notebooks/marco/results/validation_baseline_comparison.csv).

### Ridge regression (Tomas)

[`notebooks/tomas/linear_regression.ipynb`](notebooks/tomas/linear_regression.ipynb) fits scikit-learn `Ridge` on the training split. Features are one-hot local hour, weekday, and month, plus `is_weekend`, `is_holiday`, `is_summer`, `is_christmas_period`, and the 168-hour and 336-hour load lags. The encoder is fit on training rows only. There is no weather, no Terna column, and no 48-hour lag. Predictions: [`predictions/linreg_noweather.csv`](predictions/linreg_noweather.csv), checked with `check_predictions`.

The notebook also ranks holiday and Christmas-period days by mean absolute error. The largest 2024 daily errors are 25 December (about 12,217 MW), 26 December, and 24 December. On nine of the ten largest days the model over-predicts.

### LightGBM point forecasts (Marco)

[`notebooks/marco/02_lightgbm_prediction_intervals.ipynb`](notebooks/marco/02_lightgbm_prediction_intervals.ipynb). Shared features are sine and cosine of local hour, weekday, and month; the four calendar flags; and lags of 48, 168, and 336 hours. The final fit keeps training targets that are already published at the first 2024 cutoff, and then stays fixed through validation.

Hyperparameters are chosen by pooled MAE on four expanding local-day folds inside the training index. The selected point-forecast settings are 500 trees, 31 leaves, learning rate 0.05, and `min_child_samples` 30. The same search on the ERA5 temperatures selects the same tree settings. The 168-hour lag accounts for 81.4% of gain in the no-weather model ([`lgbm_noweather_feature_importance.csv`](notebooks/marco/results/lgbm_noweather_feature_importance.csv)).

- No weather: [`predictions/lgbm_noweather.csv`](predictions/lgbm_noweather.csv)
- ERA5 temperatures, labelled upper bound: [`predictions/lgbm_obs_upper_bound.csv`](predictions/lgbm_obs_upper_bound.csv)

### LightGBM point forecasts (Martina)

[`notebooks/martina/task3_lgbm.ipynb`](notebooks/martina/task3_lgbm.ipynb) is a separate implementation. It adds a holiday-eve flag and a bridge-day flag, encodes hour and weekday as sine and cosine, and refits on the whole training split. The upper-bound version adds the six ERA5 temperatures and heating and cooling degree-hours at a base of 18°C, using the six-city mean at the target hour. The hyperparameter grid is `n_estimators` in {200, 400, 800}, `learning_rate` in {0.05, 0.1, 0.2}, and `num_leaves` in {15, 31, 63}, scored on the same style of training-only local-day folds. The notebook copy in the repository has no stored cell output, so the chosen hyperparameters are not recorded.

Saved 2024 files:

- [`notebooks/martina/predictions/lgbm_martina_noweather.csv`](notebooks/martina/predictions/lgbm_martina_noweather.csv)
- [`notebooks/martina/predictions/lgbm_martina_obs_upper_bound.csv`](notebooks/martina/predictions/lgbm_martina_obs_upper_bound.csv)

### Prediction intervals (Marco)

Built on the no-weather feature set in the same notebook. Nominal coverage is 80%. The 2024 coverage was not used to choose the width or the method.

- **Quantile regression** (`lgbm_quantile80_noweather`): LightGBM quantiles at 0.10 and 0.90, with the point-model hyperparameters and the same eligible training rows. Seventeen hours have crossed quantiles; the endpoints are ordered before the interval metrics. The stored `y_pred` is the point forecast. File: [`predictions/lgbm_quantile80_noweather.csv`](predictions/lgbm_quantile80_noweather.csv).
- **Sequential conformal** (`lgbm_conformal80_expanding_noweather`): a separate model is fit only on development days available before October 2023. October–December 2023 is the initial calibration block. From each daily cutoff, the radius is the empirical 80% quantile of absolute errors already published, and that one radius is applied to every hour of the target day. File: [`predictions/lgbm_conformal80_expanding_noweather.csv`](predictions/lgbm_conformal80_expanding_noweather.csv).

Coverage tables and the two 2024 interval figures are under [`notebooks/marco/results/`](notebooks/marco/results).

## 2024 validation results

MAE and RMSE are in MW. Marco’s rows are the saved `all_available` scores. Martina’s and the Ridge rows are the scores of the saved prediction files, which contain every 2024 validation hour. On the 8,783 hours where the seasonal naive is also defined, Marco’s ordering is unchanged; both scopes are in the comparison CSV.

| Model | n | MAE | RMSE |
|---|---:|---:|---:|
| Seasonal naive | 8,783 | 1,975.1 | 3,177.2 |
| Seasonal average | 8,784 | 2,718.7 | 3,654.0 |
| Terna day-ahead forecast | 8,784 | 603.9 | 816.3 |
| Ridge, no weather (Tomas) | 8,784 | 2,019.9 | 3,106.7 |
| LightGBM, no weather (Marco) | 8,784 | 1,137.0 | 1,623.2 |
| LightGBM, ERA5 upper bound (Marco) | 8,784 | 1,046.5 | 1,524.1 |
| LightGBM, no weather (Martina) | 8,784 | 1,106.0 | 1,553.8 |
| LightGBM, ERA5 upper bound (Martina) | 8,784 | 1,008.7 | 1,438.3 |

Both LightGBM implementations beat the seasonal baselines. Terna’s published forecast remains substantially more accurate. The ERA5 versions reduce error relative to the no-weather model from the same notebook. They are upper bounds: ERA5 at the target hour was not known at 10:00 on D-1. Martina’s and Marco’s LightGBM models use different features, grids, and fitting windows, so the gap between them is not a controlled comparison.

The Ridge forecast is less accurate than the seasonal naive. A plain 168-hour UTC lag, which is not the seasonal naive, has MAE 1,986.7 MW on the same 8,784 hours in Tomas’s notebook.

### Interval coverage on 2024

Nominal level: 80%. Source: [`interval_validation_comparison.csv`](notebooks/marco/results/interval_validation_comparison.csv).

| Method | Empirical coverage | Mean width (MW) | Coverage gap |
|---|---:|---:|---:|
| Quantile regression | 66.35% | 2,723 | −13.65 pp |
| Sequential conformal | 74.92% | 3,189 | −5.08 pp |

The conformal procedure’s own point forecast, stored in its prediction file, has MAE 1,154.5 MW and RMSE 1,652.5 MW. That is a shorter training fit than `lgbm_noweather`.

Coverage is uneven. On the 287 holiday hours it is 35.19% (quantile) and 51.22% (conformal). On 15 August it is 4.17% and 50%; every miss is above the upper endpoint. Over 12–18 August it is 66.07% and 57.14%. Over the training-selected window 19–25 August, plotted because those calendar dates were the warmest seven-day June–September spell in the training temperatures, it is 50.60% and 36.90%. Summer conformal coverage is 64.86%, below the quantile method, while autumn conformal coverage is 82.84%.

The shared heatwave label — the 95th percentile of training June–September days, using the mean of the six ERA5 temperatures, in spells of at least three days — matches no day in 2024. Heatwave coverage is undefined (`n = 0`). June–September as a whole has 2,928 hours, with coverage 66.36% and 67.66%.

## Weather experiments

**ERA5 upper bound, completed.** `weather_clean.csv` has no missing values. Marco adds the six temperatures. Martina adds those temperatures and degree-hours. Humidity and cloud cover are in the file and are unused by the current models. Results that use this file are labelled upper bound.

**Archived GFS, not an operational feature.** [`data/processed/weather_forecast_clean.zip`](data/processed/weather_forecast_clean.zip) contains one long-format CSV, 210,384 rows (six cities, every UTC hour of 2022–2025), model `gfs_global_0p25`, with temperature, humidity, and cloud cover. Each target UTC day is taken from the run initialized at 12:00 UTC on the previous UTC day. Leads are 12–35 hours. The file’s `cutoff_time_utc` is 00:00 UTC on the target UTC day, and `archive_last_modified_utc` is earlier than that cutoff. [`notebooks/francesco/01_weather_forecast.ipynb`](notebooks/francesco/01_weather_forecast.ipynb) states that this operational cutoff still needs to be confirmed with the team.

That construction does not match the project issuance. 10:00 Europe/Rome is 08:00 or 09:00 UTC, so a run initialized at 12:00 UTC is later than the cutoff. `split_config.py` still points at a different, absent file, `data/processed/weather_forecast_gfs.csv`, with the Open-Meteo `temperature_2m_previous_day2` contract (a fixed lead of about 48 hours, not one 10:00 run). `FORECAST_COVERAGE_VERIFIED` is `False`. No `lgbm_fc_gfs` predictions exist.

The forecast notebook also expects an unzipped CSV and metadata files that are not in the repository. Its optional downloader imports `collect_batch` from [`download_weather.py`](download_weather.py); the current script does not define that function. `download_weather.py` is a separate Open-Meteo archive example for Milan and does not rebuild `weather_clean.csv`.

## Limitations

**Terna revisions.** Lags and `terna_forecast_mw` are the values in the current ENTSO-E extract, not a snapshot taken at 10:00 on D-1. Whether the forecast column is the original day-ahead publication or a later revision is unresolved. The comparison with Terna is a comparison with this file.

**Training is not consistent across models.** Tomas omits the 48-hour lag and one-hot encodes the calendar. Martina refits on every training row and adds eve, bridge, and degree-hour features. Marco drops training rows that are still unpublished at the first cutoff of each fit, and the conformal model stops before October 2023. Quantile intervals and conformal intervals therefore compare two full procedures. The difference is not the interval rule alone.

**Interval calibration.** Neither method reaches 80% on 2024. The conformal rule uses an expanding window of residuals that are already available at each cutoff. Load errors are temporally dependent, so the usual exchangeability coverage guarantee does not apply. Coverage is computed hour by hour; one radius is used for every hour of that forecast day. The reported 2024 coverage checks a rule that was fixed beforehand. Widening the intervals after seeing this year, and then quoting the new coverage on the same year, would no longer be an honest check.

Two further limits belong in the report. 2022, an unusual demand year, is inside the training set. The seasonal naive follows the local clock, while the 168-hour model lag follows UTC; they differ for about a week after each clock change.

## Reproducing the results

From the repository root, with that directory on `PYTHONPATH`:

```python
from split_config import load_data, split, check_predictions, validation_index

df = load_data()
train, val = split(df)
check_predictions(
    "predictions/lgbm_noweather.csv",
    validation_index(df),
    reference_y=df["actual_load_mw"],
)
```

`load_data` reads the whole processed file. `split` does not return 2025. Leave `final_test` for the single leader run.

To regenerate the saved scores, run:

- [`notebooks/tomas/linear_regression.ipynb`](notebooks/tomas/linear_regression.ipynb)
- [`notebooks/martina/task3_lgbm.ipynb`](notebooks/martina/task3_lgbm.ipynb)
- [`notebooks/marco/02_lightgbm_prediction_intervals.ipynb`](notebooks/marco/02_lightgbm_prediction_intervals.ipynb)

[`requirements.txt`](requirements.txt) pins the Open-Meteo client stack. The modeling notebooks also need `lightgbm`, `scikit-learn`, and `matplotlib`. The calendar notebook needs `holidays`. Re-downloading ENTSO-E requires a token in an untracked `.env`; [`test_entsoe.py`](test_entsoe.py) only checks a short connection. The processed tables used above are already in `data/processed/`.

## GitHub workflow

Work on a feature branch and open a pull request into `main`. The repository history is already organized that way. Keep each person’s notebooks under `notebooks/<name>/`. Do not commit API tokens, `.env` files, or raw downloads. `data/raw/` is gitignored. Review the pull request before merging, and leave the 2025 test year unread on the branch.

## Remaining work

**Error analysis.** Ridge holiday errors and the 2024 interval breakdowns by season, holiday, Ferragosto, and the training-selected August window are done. A consolidated error analysis — where each model fails, including August holidays and the heatwave definition — is still open. It belongs with the leader comparison of the existing prediction files.

**Final 2025 evaluation.** Run once, only for the baselines and the models chosen before looking at 2025. Call `final_test(df, confirm=True)`. The planned score uses 8,760 hours for the models and 8,759 hours for Terna, and names the excluded timestamp `2024-12-31T23:00:00Z`. This evaluation has not been run.

**2020 lockdown extension, proposed.** It needs 2018–2020 load and a model trained only on data from before the lockdown. It stays outside the 2022–2025 results. No such series or model is in the repository.

The forecast-weather experiment stays blocked until a file is shown to be available at 10:00 Europe/Rome on D-1, for the hours and cities used in training and validation, with missing runs left empty.
