"""Shared day-ahead protocol for the Italy load-forecasting project.

Run notebooks with this repository available on ``sys.path``. Paths are
resolved from this file, not from the process working directory.

Protocol
--------
- Issuance: 10:00 Europe/Rome on local day D-1.
- Target: every UTC hour whose Europe/Rome calendar date is D
  (23, 24 or 25 hours).
- Train: local dates 2022-01-16 through 2023-12-31.
- Validation: local dates 2024-01-01 through 2024-12-31.
- Test: local dates 2025-01-01 through 2025-12-31. Not returned unless
  ``final_test(..., confirm=True)`` is called by the leader.

The series starts at 2022-01-01 00:00 UTC, which is 01:00 in Rome, so
local 2022-01-15 00:00 does not have a 336-hour history. Training
therefore starts on local 2022-01-16, the first complete local day on
which every hour has that lag. The year boundaries are local dates:
2023-12-31 23:00 UTC is 2024-01-01 00:00 in Rome and belongs to
validation, and 2024-12-31 23:00 UTC is 2025-01-01 00:00 in Rome and
belongs to the test set.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent

DATA_PATH = REPO_ROOT / "data" / "processed" / "dataset_no_weather.csv"
WEATHER_OBSERVED_PATH = REPO_ROOT / "data" / "processed" / "weather_clean.csv"
# Not in the repository. Francesco creates this only after the coverage
# check in the briefing. Do not point it at weather_clean.csv.
WEATHER_FORECAST_PATH = REPO_ROOT / "data" / "processed" / "weather_forecast_gfs.csv"

TIMESTAMP_COL = "timestamp_utc"
TARGET_COL = "actual_load_mw"
TERNA_COL = "terna_forecast_mw"
CALENDAR_COLUMNS = (
    "hour_local",
    "day_of_week",
    "month",
    "year",
    "is_weekend",
    "is_holiday",
    "is_summer",
    "is_christmas_period",
)

LOCAL_TZ = "Europe/Rome"
CUTOFF_HOUR = 10
CUTOFF_TZ = LOCAL_TZ

# Fixed UTC-hour shifts. These are not "same local clock hour" lags.
# A lag shorter than 48 h is not legal for every hour of day D at 10:00.
SAFE_LAGS_HOURS = (48, 168, 336)
PUBLICATION_LAG_HOURS = 2  # interval end plus the H+1 publication deadline

TRAIN_LOCAL_START = "2022-01-16"
TRAIN_LOCAL_END = "2023-12-31"
VAL_LOCAL_START = "2024-01-01"
VAL_LOCAL_END = "2024-12-31"
TEST_LOCAL_START = "2025-01-01"
TEST_LOCAL_END = "2025-12-31"

# Only missing Terna hour in the merged file. It is local 2025-01-01 00:00,
# so it sits in the test set, not in the 2024 validation set.
TERNA_MISSING_TS = pd.Timestamp("2024-12-31T23:00:00Z")

# First Sunday of November. is_holiday is 1 here, but these are not civil
# public holidays. They are already Sundays. Do not edit the CSV here.
NON_CIVIL_HOLIDAY_DATES = (
    "2022-11-06",
    "2023-11-05",
    "2024-11-03",
    "2025-11-02",
)

OBSERVED_TEMP_COLUMNS = (
    "temp_milano_c",
    "temp_torino_c",
    "temp_bologna_c",
    "temp_roma_c",
    "temp_napoli_c",
    "temp_palermo_c",
)
# Contract for the file that does not exist yet. Same city order.
FORECAST_TEMP_COLUMNS = tuple(
    "temp_fc_" + column.removeprefix("temp_") for column in OBSERVED_TEMP_COLUMNS
)
# Previous Runs API, fixed lead of about 48 h before each valid hour.
# This is not one GFS run issued at 10:00 for the whole of day D.
GFS_MODEL = "gfs_seamless"
FC_VARIABLE = "temperature_2m_previous_day2"
FORECAST_COVERAGE_VERIFIED = False

HEATWAVE_PCTL = 0.95
HEATWAVE_MIN_DAYS = 3
HEATWAVE_MONTHS = (6, 7, 8, 9)  # not is_summer, which is June-August only

PREDICTION_COLUMNS = ("timestamp", "y_true", "y_pred", "model")
SEASONAL_NAIVE_MODEL = "seasonal_naive"
TERNA_MODEL = "terna"


def _as_utc_index(index) -> pd.DatetimeIndex:
    idx = pd.DatetimeIndex(index)
    if idx.tz is None:
        raise ValueError("Timestamps must be timezone-aware UTC, not naive.")
    return idx.tz_convert("UTC")


def _assert_complete_hourly(index) -> None:
    idx = _as_utc_index(index)
    if idx.has_duplicates or not idx.is_monotonic_increasing:
        raise ValueError("The hourly UTC index must be unique and sorted.")
    expected = pd.date_range(idx.min(), idx.max(), freq="h", tz="UTC")
    if len(expected) != len(idx) or not idx.equals(expected):
        raise ValueError("Lag shifts require a complete hourly UTC index.")


def local_midnight(index) -> pd.DatetimeIndex:
    """Europe/Rome midnight of each timestamp, including 23- and 25-hour days."""
    return _as_utc_index(index).tz_convert(LOCAL_TZ).floor("D")


def _local_date_mask(index, start: str, end: str) -> np.ndarray:
    days = local_midnight(index)
    start_ts = pd.Timestamp(start, tz=LOCAL_TZ)
    end_ts = pd.Timestamp(end, tz=LOCAL_TZ)
    return (days >= start_ts) & (days <= end_ts)


def cutoff_timestamps(index) -> pd.DatetimeIndex:
    """10:00 Europe/Rome on the local day before each target timestamp."""
    issued_on = local_midnight(index) - pd.DateOffset(days=1)
    return pd.DatetimeIndex(issued_on) + pd.Timedelta(hours=CUTOFF_HOUR)


def assert_lags_available(index, lags=SAFE_LAGS_HOURS) -> None:
    """Fail if any lag would still be unpublished at the 10:00 cutoff.

    An hour starting at t is treated as published at t + 2 hours: the
    operating hour has ended, and Regulation 543/2013 requires publication
    no later than one hour after that. This is a deadline, not a measured
    ENTSO-E delay.
    """
    idx = _as_utc_index(index)
    cutoff = cutoff_timestamps(idx)
    for lag in lags:
        if lag < 48:
            raise ValueError(f"Lag {lag} h is not safe for every hour of day D.")
        available_at = idx - pd.Timedelta(hours=lag) + pd.Timedelta(
            hours=PUBLICATION_LAG_HOURS
        )
        if (available_at > cutoff).any():
            raise ValueError(f"Lag {lag} h is not available at every cutoff.")


def assert_calendar_matches(df: pd.DataFrame) -> None:
    local = df.index.tz_convert(LOCAL_TZ)
    checks = {
        "hour_local": local.hour,
        "day_of_week": local.dayofweek,
        "month": local.month,
        "year": local.year,
        "is_weekend": (local.dayofweek >= 5).astype(int),
    }
    for column, expected in checks.items():
        if not np.array_equal(df[column].to_numpy(), np.asarray(expected)):
            raise ValueError(f"{column} does not match Europe/Rome.")


def load_data(path=DATA_PATH) -> pd.DataFrame:
    df = pd.read_csv(path)
    missing = {TIMESTAMP_COL, TARGET_COL, TERNA_COL, *CALENDAR_COLUMNS} - set(df.columns)
    if missing:
        raise ValueError(f"Unexpected columns, missing: {sorted(missing)}")
    df[TIMESTAMP_COL] = pd.to_datetime(df[TIMESTAMP_COL], utc=True)
    df = df.sort_values(TIMESTAMP_COL).set_index(TIMESTAMP_COL)
    df.index.name = "timestamp"
    _assert_complete_hourly(df.index)
    assert_calendar_matches(df)
    return df


def split(df: pd.DataFrame):
    """Return train and validation only. The 2025 test set stays closed."""
    train = df.loc[_local_date_mask(df.index, TRAIN_LOCAL_START, TRAIN_LOCAL_END)]
    val = df.loc[_local_date_mask(df.index, VAL_LOCAL_START, VAL_LOCAL_END)]
    if train.empty or val.empty:
        raise ValueError("Train or validation slice is empty.")
    if local_midnight(train.index).max() >= local_midnight(val.index).min():
        raise ValueError("Train and validation local dates overlap.")
    return train, val


def final_test(df: pd.DataFrame, confirm: bool = False) -> pd.DataFrame:
    """Leader-only access to local year 2025."""
    if not confirm:
        raise RuntimeError(
            "The 2025 test set is closed. The leader calls final_test(df, confirm=True) once."
        )
    return df.loc[_local_date_mask(df.index, TEST_LOCAL_START, TEST_LOCAL_END)].copy()


def validation_index(df: pd.DataFrame) -> pd.DatetimeIndex:
    return split(df)[1].index


def add_lags(df: pd.DataFrame, target: str = TARGET_COL, lags=SAFE_LAGS_HOURS) -> pd.DataFrame:
    """Fixed UTC-hour shifts on a complete hourly index. Not local-clock lags."""
    _assert_complete_hourly(df.index)
    assert_lags_available(df.index, lags)
    out = df.copy()
    for hours in lags:
        out[f"{target}_lag{hours}h"] = out[target].shift(int(hours))
    return out


def calendar_local(index) -> pd.DataFrame:
    """Local clock features. Prefer the CSV calendar columns for holidays."""
    local = _as_utc_index(index).tz_convert(LOCAL_TZ)
    return pd.DataFrame(
        {
            "hour": local.hour,
            "dow": local.dayofweek,
            "month": local.month,
            "year": local.year,
            "date": local.date,
        },
        index=pd.DatetimeIndex(index),
    )


def same_local_clock_source(index, days: int = 7) -> pd.DatetimeIndex:
    """UTC instant of the same Europe/Rome clock time ``days`` earlier.

    Nonexistent source times (the 02:00 that spring-forward removes) are NaT.
    A repeated source time (the 02:00 that fall-back creates) uses the earlier
    UTC instant.
    """
    local = _as_utc_index(index).tz_convert(LOCAL_TZ)
    naive = pd.DatetimeIndex(local.tz_localize(None) - pd.DateOffset(days=int(days)))
    shifted = naive.tz_localize(LOCAL_TZ, nonexistent="NaT", ambiguous=False)
    return shifted.tz_convert("UTC")


def seasonal_naive(df: pd.DataFrame, target: str = TARGET_COL, days: int = 7) -> pd.Series:
    """Load at the same local clock time seven days earlier.

    This is the Task 1 baseline. It is not ``shift(168)``. Around each clock
    change, a fixed 168-hour UTC shift lands on a different local hour for
    about seven days. Hours whose source clock time does not exist are NaN
    and are left out of this baseline's score.
    """
    source = same_local_clock_source(df.index, days=days)
    predicted = pd.Series(np.nan, index=df.index, dtype=float)
    valid = source.notna()
    predicted.loc[valid] = df[target].reindex(source[valid]).to_numpy()
    predicted.name = SEASONAL_NAIVE_MODEL
    return predicted


def seasonal_naive_undefined(index) -> pd.DatetimeIndex:
    source = same_local_clock_source(index, days=7)
    idx = _as_utc_index(index)
    return idx[source.isna()]


def seasonal_average_prediction(train: pd.DataFrame, val: pd.DataFrame, target: str = TARGET_COL) -> pd.Series:
    """Mean load by local hour and weekday, estimated on training rows only."""
    train_cal = calendar_local(train.index)
    val_cal = calendar_local(val.index)
    profile = train[target].groupby(train_cal["dow"] * 24 + train_cal["hour"]).mean()
    keys = val_cal["dow"] * 24 + val_cal["hour"]
    predicted = keys.map(profile)
    predicted.index = val.index
    predicted.name = "seasonal_avg"
    return predicted.astype(float)


def chronological_local_day_folds(index, n_splits: int = 4):
    """Expanding folds that cut on local dates, inside the training index only.

    Do not use a row-wise ``TimeSeriesSplit`` directly: it can place hours of
    the same local day on both sides of a fold. Do not include 2024.
    """
    days = pd.Index(local_midnight(index).unique()).sort_values()
    n_days = len(days)
    val_size = n_days // (n_splits + 1)
    if n_splits < 2 or val_size < 1:
        raise ValueError("Not enough local days for the requested folds.")
    folds = []
    for fold in range(n_splits):
        val_end = n_days - (n_splits - fold - 1) * val_size
        val_start = val_end - val_size
        train_days = days[:val_start]
        val_days = days[val_start:val_end]
        if len(train_days) < val_size or len(val_days) == 0:
            raise ValueError("A chronological fold is empty.")
        folds.append((train_days, val_days))
    return folds


def rows_on_local_days(df: pd.DataFrame, days) -> pd.DataFrame:
    mask = local_midnight(df.index).isin(pd.DatetimeIndex(days))
    return df.loc[mask]


def load_observed_weather(path=WEATHER_OBSERVED_PATH) -> pd.DataFrame:
    """ERA5 reanalysis. Upper-bound experiment only; not a day-ahead feature."""
    weather = pd.read_csv(path)
    weather[TIMESTAMP_COL] = pd.to_datetime(weather[TIMESTAMP_COL], utc=True)
    weather = weather.sort_values(TIMESTAMP_COL).set_index(TIMESTAMP_COL)
    missing = set(OBSERVED_TEMP_COLUMNS) - set(weather.columns)
    if missing:
        raise ValueError(f"Observed weather is missing {sorted(missing)}")
    return weather


def heatwave_local_dates(weather: pd.DataFrame, train_index) -> pd.DatetimeIndex:
    """Local dates of heatwaves, for error tables only. Not a model feature.

    The daily value is the unweighted mean of the six ERA5 city temperatures.
    The threshold is the training-set percentile of June-September days.
    """
    temperature = weather[list(OBSERVED_TEMP_COLUMNS)].mean(axis=1)
    daily = temperature.groupby(local_midnight(temperature.index)).mean()
    train_days = pd.Index(local_midnight(train_index).unique())
    reference = daily.index.isin(train_days) & daily.index.month.isin(HEATWAVE_MONTHS)
    if reference.sum() == 0:
        raise ValueError("No training summer days are available for the heatwave threshold.")
    threshold = float(daily.loc[reference].quantile(HEATWAVE_PCTL))
    hot = daily >= threshold
    run_id = (hot != hot.shift(fill_value=False)).cumsum()
    run_length = hot.groupby(run_id).transform("sum")
    return daily.index[hot & (run_length >= HEATWAVE_MIN_DAYS)]


def metrics(y_true, y_pred) -> dict:
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    if len(y_true) != len(y_pred) or len(y_true) == 0:
        raise ValueError("Metrics need a non-empty pair of equal length.")
    if not (np.isfinite(y_true).all() and np.isfinite(y_pred).all()):
        raise ValueError("Metrics received a missing or infinite value.")
    error = y_true - y_pred
    return {
        "n": int(len(error)),
        "MAE": float(np.mean(np.abs(error))),
        "RMSE": float(np.sqrt(np.mean(error**2))),
    }


def _expected_for_model(model: str, expected_index: pd.DatetimeIndex) -> pd.DatetimeIndex:
    expected = _as_utc_index(expected_index)
    if model == TERNA_MODEL:
        return expected.difference(pd.DatetimeIndex([TERNA_MISSING_TS]))
    if model == SEASONAL_NAIVE_MODEL:
        return expected.difference(seasonal_naive_undefined(expected))
    return expected


def check_predictions(path, expected_index, reference_y=None) -> pd.DataFrame:
    """Validate a prediction CSV against the shared timestamp set.

    ``seasonal_naive`` may omit hours whose same local clock time did not
    exist seven days earlier. ``terna`` may omit ``TERNA_MISSING_TS`` when
    that hour is in ``expected_index`` (the 2025 test). Every other model
    must contain every expected hour, with a finite prediction. ``y_true``
    must agree across models and, when supplied, with ``reference_y``.
    """
    raw_timestamp = pd.read_csv(path, usecols=["timestamp"], dtype=str)["timestamp"]
    explicit_utc = raw_timestamp.str.contains(r"(?:Z|\+00:00)$", regex=True)
    if not bool(explicit_utc.all()):
        raise AssertionError("Every timestamp must be explicit UTC (Z or +00:00).")

    predictions = pd.read_csv(path)
    missing_columns = set(PREDICTION_COLUMNS) - set(predictions.columns)
    if missing_columns:
        raise AssertionError(f"Missing columns: {sorted(missing_columns)}")
    predictions["timestamp"] = pd.to_datetime(predictions["timestamp"], utc=True)
    for column in ("y_true", "y_pred"):
        predictions[column] = pd.to_numeric(predictions[column], errors="coerce")
    if predictions["model"].isna().any() or (predictions["model"].astype(str).str.len() == 0).any():
        raise AssertionError("Every row needs a model name.")

    expected = _as_utc_index(expected_index)
    if predictions.duplicated(["model", "timestamp"]).any():
        raise AssertionError("Duplicate (model, timestamp) rows.")

    truth = predictions.groupby("timestamp")["y_true"].nunique(dropna=False)
    if (truth > 1).any():
        raise AssertionError("y_true differs across models at the same timestamp.")

    for model, group in predictions.groupby("model", sort=False):
        model_expected = _expected_for_model(str(model), expected)
        found = pd.DatetimeIndex(group["timestamp"])
        missing = model_expected.difference(found)
        extra = found.difference(expected)
        if len(missing):
            raise AssertionError(f"{model}: {len(missing)} required hours are missing.")
        if len(extra):
            raise AssertionError(f"{model}: {len(extra)} timestamps are outside the expected set.")
        omitted = expected.difference(found)
        allowed = expected.difference(model_expected)
        if len(omitted.difference(allowed)):
            raise AssertionError(f"{model}: omitted a timestamp that must be predicted.")
        if not np.isfinite(group["y_true"].to_numpy(dtype=float)).all():
            raise AssertionError(f"{model}: y_true has a missing or infinite value.")
        if not np.isfinite(group["y_pred"].to_numpy(dtype=float)).all():
            raise AssertionError(f"{model}: y_pred has a missing or infinite value.")
        if reference_y is not None:
            reference = pd.Series(reference_y).copy()
            reference.index = _as_utc_index(reference.index)
            aligned = reference.reindex(found)
            if aligned.isna().any() or not np.allclose(
                aligned.to_numpy(dtype=float),
                group["y_true"].to_numpy(dtype=float),
                rtol=0.0,
                atol=1e-6,
            ):
                raise AssertionError(f"{model}: y_true is not actual_load_mw.")
    return predictions


__all__ = [
    "CALENDAR_COLUMNS",
    "CUTOFF_HOUR",
    "CUTOFF_TZ",
    "DATA_PATH",
    "FC_VARIABLE",
    "FORECAST_COVERAGE_VERIFIED",
    "FORECAST_TEMP_COLUMNS",
    "GFS_MODEL",
    "HEATWAVE_MIN_DAYS",
    "HEATWAVE_MONTHS",
    "HEATWAVE_PCTL",
    "LOCAL_TZ",
    "NON_CIVIL_HOLIDAY_DATES",
    "OBSERVED_TEMP_COLUMNS",
    "REPO_ROOT",
    "SAFE_LAGS_HOURS",
    "SEASONAL_NAIVE_MODEL",
    "TARGET_COL",
    "TERNA_COL",
    "TERNA_MISSING_TS",
    "TERNA_MODEL",
    "TEST_LOCAL_END",
    "TEST_LOCAL_START",
    "TIMESTAMP_COL",
    "TRAIN_LOCAL_END",
    "TRAIN_LOCAL_START",
    "VAL_LOCAL_END",
    "VAL_LOCAL_START",
    "WEATHER_FORECAST_PATH",
    "WEATHER_OBSERVED_PATH",
    "add_lags",
    "assert_lags_available",
    "calendar_local",
    "check_predictions",
    "chronological_local_day_folds",
    "cutoff_timestamps",
    "final_test",
    "heatwave_local_dates",
    "load_data",
    "load_observed_weather",
    "local_midnight",
    "metrics",
    "rows_on_local_days",
    "seasonal_average_prediction",
    "seasonal_naive",
    "seasonal_naive_undefined",
    "split",
    "validation_index",
]
