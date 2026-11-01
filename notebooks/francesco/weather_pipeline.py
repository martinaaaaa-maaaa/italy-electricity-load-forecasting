"""Open-Meteo ERA5 extraction. Reanalysis is for exploration, not day-ahead inputs."""
from __future__ import annotations

import argparse
import hashlib
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

CITIES = {
    'milano': (45.4642, 9.1900),
    'torino': (45.0703, 7.6869),
    'bologna': (44.4949, 11.3426),
    'roma': (41.9028, 12.4964),
    'napoli': (40.8518, 14.2681),
    'palermo': (38.1157, 13.3615),
}
VARIABLES = {
    'temperature_2m': ('temp', 'c', '°C'),
    'relative_humidity_2m': ('humidity', 'pct', '%'),
    'cloud_cover': ('cloud_cover', 'pct', '%'),
}
ENDPOINT = 'https://archive-api.open-meteo.com/v1/archive'
MODEL = 'era5'


def utc_now():
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def hourly_index(start, end):
    """Inclusive UTC calendar dates: the end includes its entire final day."""
    a, b = pd.Timestamp(start, tz='UTC'), pd.Timestamp(end, tz='UTC')
    if a != a.normalize() or b != b.normalize() or b < a:
        raise ValueError('Use ordered date-only bounds YYYY-MM-DD.')
    return pd.date_range(a, b + pd.Timedelta(days=1), freq='h', inclusive='left', name='timestamp_utc')


def chunks(start, end):
    index = hourly_index(start, end)
    day = index[0]
    last = index[-1].normalize()
    while day <= last:
        stop = min(day + pd.offsets.MonthEnd(0), last)
        yield str(day.date()), str(stop.date())
        day = stop + pd.Timedelta(days=1)


def request_params(city, start, end):
    lat, lon = CITIES[city]
    return dict(latitude=lat, longitude=lon, start_date=start, end_date=end,
                hourly=','.join(VARIABLES), models=MODEL, timezone='UTC',
                temperature_unit='celsius', timeformat='iso8601')


def url_for(city, start, end):
    return ENDPOINT + '?' + urllib.parse.urlencode(request_params(city, start, end))


def load_payload(content):
    payload = json.loads(content)
    if not isinstance(payload, dict) or payload.get('error') or 'hourly' not in payload:
        raise ValueError('Invalid API response: ' + str(payload)[:240])
    return payload


def parse_hourly(payload, city, start, end):
    """Reject duplicates/units/time errors; retain NaN and anomalies unchanged."""
    if payload.get('utc_offset_seconds') != 0:
        raise ValueError('Response is not UTC.')
    hourly, units = payload['hourly'], payload.get('hourly_units', {})
    idx = pd.DatetimeIndex(pd.to_datetime(hourly['time'], utc=True), name='timestamp_utc')
    if idx.hasnans or idx.has_duplicates:
        raise ValueError(f'{city}: invalid or duplicate timestamps; inspect raw response.')
    expected = hourly_index(start, end)
    if not idx.isin(expected).all():
        raise ValueError(f'{city}: off-hour or out-of-range timestamps.')
    data = {}
    for key, (prefix, suffix, unit) in VARIABLES.items():
        if units.get(key) != unit:
            raise ValueError(f'{city}/{key}: unexpected or absent unit {units.get(key)!r}.')
        values = hourly.get(key)
        if not isinstance(values, list) or len(values) != len(idx):
            raise ValueError(f'{city}/{key}: absent array or length mismatch.')
        numeric = pd.to_numeric(pd.Series(values), errors='raise').to_numpy(dtype=float)
        data[f'{prefix}_{city}_{suffix}'] = numeric
    # No aggregation or interpolation: ERA5 hourly values are used as returned.
    return pd.DataFrame(data, index=idx).sort_index()


def obtain_raw(root, city, start, end, offline=False):
    """Cache original bytes using exclusive create. Existing files never overwritten."""
    params = request_params(city, start, end)
    digest = hashlib.sha256(json.dumps(params, sort_keys=True).encode()).hexdigest()[:12]
    directory = Path(root) / 'data/raw/weather_reanalysis'
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f'{city}_{start}_{end}_{digest}.json'
    meta_path = path.with_suffix('.metadata.json')
    cached = path.exists()
    if cached:
        content = path.read_bytes()
    else:
        if offline:
            raise FileNotFoundError(f'Raw response absent: {path.name}')
        request = urllib.request.Request(url_for(city, start, end),
                                        headers={'User-Agent': 'BSML-weather-student-project/1.0'})
        for attempt in range(4):
            try:
                with urllib.request.urlopen(request, timeout=60) as response:
                    content = response.read()
                load_payload(content)
                break
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode('utf-8', errors='replace')[:400]
                if exc.code not in (429, 500, 502, 503, 504) or attempt == 3:
                    raise RuntimeError(f'Open-Meteo HTTP {exc.code}: {detail}') from exc
                time.sleep(2 ** attempt)
            except (urllib.error.URLError, TimeoutError):
                if attempt == 3:
                    raise
                time.sleep(2 ** attempt)
        with path.open('xb') as handle:
            handle.write(content)
        meta = dict(url=url_for(city, start, end), params=params, retrieved_at_utc=utc_now(),
                    sha256=hashlib.sha256(content).hexdigest(), source_kind='reanalysis', model=MODEL)
        with meta_path.open('x', encoding='utf-8') as handle:
            json.dump(meta, handle, indent=2)
        time.sleep(0.6)
    payload = load_payload(content)
    checksum = hashlib.sha256(content).hexdigest()
    if meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding='utf-8'))
        if meta.get('sha256') != checksum or meta.get('params') != params:
            raise ValueError(f'Raw integrity/request mismatch: {path}')
    else:
        meta = dict(retrieved_at_utc=None)
    provenance = dict(city=city, start_date=start, end_date=end,
                      raw_file=path.relative_to(root).as_posix(), sha256=checksum,
                      retrieved_at_utc=meta.get('retrieved_at_utc'), reused_cache=cached,
                      requested_latitude=CITIES[city][0], requested_longitude=CITIES[city][1],
                      returned_latitude=payload.get('latitude'), returned_longitude=payload.get('longitude'),
                      returned_elevation=payload.get('elevation'), model=MODEL, source_kind='reanalysis',
                      url=url_for(city, start, end))
    return payload, provenance


def quality_tables(frame, absent_by_city):
    summary, gaps, anomalies = [], [], []
    for col in frame:
        missing = frame[col].isna()
        city = next(city for city in CITIES if f'_{city}_' in col)
        absent = absent_by_city[city]
        summary.append(dict(dataset='weather_clean_reanalysis', column=col,
                            missing_count=int(missing.sum()), missing_pct=round(100 * missing.mean(), 6),
                            absent_hour_count=int(absent.sum()),
                            missing_cell_existing_hour_count=int((missing & ~absent).sum())))
        for kind, mask in [('absent_hour', missing & absent), ('missing_cell', missing & ~absent)]:
            positions = np.flatnonzero(mask.to_numpy())
            for group in np.split(positions, np.where(np.diff(positions) != 1)[0] + 1):
                if len(group):
                    gaps.append(dict(column=col, start_utc=frame.index[group[0]], end_utc=frame.index[group[-1]],
                                     hours=len(group), kind=kind, cause='not supplied by API; cause unknown'))
        v = frame[col]
        bounds = (-50, 60) if col.startswith('temp_') else (0, 100)
        bad = v.notna() & ((v < bounds[0]) | (v > bounds[1]) | ~np.isfinite(v))
        for timestamp, value in v[bad].items():
            anomalies.append(dict(timestamp_utc=timestamp, column=col, value=value,
                                  rule=f'outside [{bounds[0]}, {bounds[1]}] or non-finite',
                                  action='flagged; original value retained'))
    return (pd.DataFrame(summary),
            pd.DataFrame(gaps, columns=['column', 'start_utc', 'end_utc', 'hours', 'kind', 'cause']),
            pd.DataFrame(anomalies, columns=['timestamp_utc', 'column', 'value', 'rule', 'action']))


def save_csv(frame, path, index=False):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=index, na_rep='', date_format='%Y-%m-%dT%H:%M:%SZ')


def temperature_plots(frame, directory):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    columns = [f'temp_{city}_c' for city in CITIES]
    # Aggregations used only in plots; no values are filled in the clean dataset.
    daily = frame[columns].resample('D').mean()
    fig, axes = plt.subplots(3, 2, figsize=(13, 10), sharex=True)
    for ax, city, col in zip(axes.flat, CITIES, columns):
        ax.plot(daily.index, daily[col], lw=0.7)
        ax.set(title=city.capitalize(), ylabel='Temperature (°C)')
        ax.grid(alpha=0.2)
    fig.suptitle('ERA5 reanalysis — daily means of available hourly temperatures')
    fig.tight_layout()
    fig.savefig(directory / 'temperature_daily.png', dpi=150)
    plt.close(fig)
    fig, ax = plt.subplots(figsize=(11, 5))
    month = frame[columns].groupby(frame.index.month).mean()
    for city, col in zip(CITIES, columns):
        ax.plot(month.index, month[col], marker='o', label=city.capitalize())
    ax.set(xlabel='Month (UTC)', ylabel='Temperature (°C)',
           title='ERA5 reanalysis — monthly means of available hours', xticks=range(1, 13))
    ax.legend(ncol=3)
    ax.grid(alpha=0.2)
    fig.tight_layout()
    fig.savefig(directory / 'temperature_monthly.png', dpi=150)
    plt.close(fig)


def run(root, start='2022-01-01', end='2025-12-31', offline=False):
    root = Path(root).resolve()
    expected = hourly_index(start, end)
    reports = root / 'reports/weather'
    reports.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    log_path = reports / f'extraction_{run_id}.json'
    status = dict(start_date=start, end_date=end, started_at_utc=utc_now(), status='running',
                  source_kind='reanalysis', model=MODEL, day_ahead_eligible=False, requests=[])
    frames, absent_by_city = [], {}
    try:
        for city in CITIES:
            parts = []
            for a, b in chunks(start, end):
                print(f'{city}: {a} → {b}', flush=True)
                payload, provenance = obtain_raw(root, city, a, b, offline=offline)
                try:
                    part = parse_hourly(payload, city, a, b)
                except Exception:
                    status['failed_raw_file'] = provenance['raw_file']
                    raise
                status['requests'].append(provenance)
                parts.append(part)
            frame = pd.concat(parts).sort_index()
            if frame.index.has_duplicates:
                raise ValueError(f'{city}: duplicates across chunks; no automatic removal.')
            absent_by_city[city] = pd.Series(~expected.isin(frame.index), index=expected)
            frames.append(frame.reindex(expected))
        clean = pd.concat(frames, axis=1)
        if clean.index.has_duplicates or len(clean.columns) != 18 or len(clean) != len(expected):
            raise ValueError('Final structural check failed.')
        missing, gaps, anomalies = quality_tables(clean, absent_by_city)
        # Publish only after all six cities have been extracted and validated.
        save_csv(clean, root / 'data/processed/weather_clean.csv', index=True)
        save_csv(missing, reports / 'missing_values_report.csv')
        save_csv(gaps, reports / 'missing_intervals.csv')
        save_csv(anomalies, reports / 'anomalies.csv')
        save_csv(pd.DataFrame(status['requests']), reports / 'provenance.csv')
        dictionary = []
        for city in CITIES:
            for api, (prefix, suffix, unit) in VARIABLES.items():
                dictionary.append(dict(column=f'{prefix}_{city}_{suffix}', city=city,
                                       api_variable=api, unit=unit, model=MODEL,
                                       source_kind='reanalysis', day_ahead_eligible=False))
        save_csv(pd.DataFrame(dictionary), reports / 'data_dictionary.csv')
        temperature_plots(clean, reports)
        status.update(status='complete_reanalysis_only', rows=len(clean),
                      total_missing_cells=int(clean.isna().sum().sum()), flagged_values=len(anomalies),
                      finished_at_utc=utc_now())
        (reports / 'weather_clean.metadata.json').write_text(json.dumps(status, indent=2), encoding='utf-8')
        print(f'Created {len(clean):,} hourly rows and 18 weather columns. REANALYSIS ONLY.')
        return clean, missing, gaps, anomalies
    except Exception as exc:
        status.update(status='failed', error=f'{type(exc).__name__}: {exc}', finished_at_utc=utc_now())
        raise
    finally:
        log_path.write_text(json.dumps(status, indent=2), encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument('--start', default='2022-01-01')
    parser.add_argument('--end', default='2025-12-31')
    parser.add_argument('--offline', action='store_true', help='Use existing raw JSON only.')
    args = parser.parse_args()
    run(args.root, args.start, args.end, args.offline)


if __name__ == '__main__':
    main()
