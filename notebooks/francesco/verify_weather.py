"""Independent, read-only audit of the delivered CSV against every raw API response."""
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
CITIES = ['milano', 'torino', 'bologna', 'roma', 'napoli', 'palermo']
VARIABLES = {
    'temperature_2m': ('temp', 'c', '°C'),
    'relative_humidity_2m': ('humidity', 'pct', '%'),
    'cloud_cover': ('cloud_cover', 'pct', '%'),
}


def verify(root=ROOT):
    root = Path(root)
    data_path = root / 'data/processed/weather_clean.csv'
    csv = pd.read_csv(data_path)
    times = csv.pop('timestamp_utc')
    assert times.str.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:00:00Z').all()
    idx = pd.DatetimeIndex(pd.to_datetime(times, utc=True))
    expected = pd.date_range('2022-01-01', '2026-01-01', freq='h', inclusive='left', tz='UTC')
    assert idx.equals(expected) and not idx.has_duplicates
    columns = [f'{prefix}_{city}_{suffix}' for city in CITIES
               for prefix, suffix, unit in VARIABLES.values()]
    assert list(csv.columns) == columns
    assert np.isfinite(csv.to_numpy()).all()
    meta = json.loads((root / 'reports/weather/weather_clean.metadata.json').read_text())
    assert meta['model'] == 'era5' and meta['source_kind'] == 'reanalysis'
    assert meta['day_ahead_eligible'] is False and meta['rows'] == len(expected)
    provenance = pd.read_csv(root / 'reports/weather/provenance.csv').set_index('raw_file')
    assert not provenance.index.has_duplicates
    assert len(provenance) == len(meta['requests']) == 288
    seen = set()
    coverage = {city: [] for city in CITIES}
    coordinates = {}
    checked = 0
    for request in meta['requests']:
        assert request['raw_file'] not in seen
        seen.add(request['raw_file'])
        path = (root / request['raw_file']).resolve()
        assert path.is_relative_to(root.resolve())
        body = path.read_bytes()
        checksum = hashlib.sha256(body).hexdigest()
        original_meta = json.loads(path.with_suffix('.metadata.json').read_text())
        assert checksum == request['sha256'] == original_meta['sha256']
        assert checksum == provenance.loc[request['raw_file'], 'sha256']
        params = original_meta['params']
        assert params['models'] == 'era5' and params['timezone'] == 'UTC'
        assert params['start_date'] == request['start_date']
        assert params['end_date'] == request['end_date']
        assert params['hourly'].split(',') == list(VARIABLES)
        payload = json.loads(body)
        assert payload['utc_offset_seconds'] == 0
        timestamps = pd.DatetimeIndex(pd.to_datetime(payload['hourly']['time'], utc=True))
        wanted = pd.date_range(request['start_date'],
                               pd.Timestamp(request['end_date']) + pd.Timedelta(days=1),
                               freq='h', inclusive='left', tz='UTC')
        assert timestamps.equals(wanted)
        city = request['city']
        coverage[city].extend(timestamps.tolist())
        coordinates[city] = {key: request[key] for key in [
            'requested_latitude', 'requested_longitude', 'returned_latitude',
            'returned_longitude', 'returned_elevation']}
        positions = idx.get_indexer(timestamps)
        assert (positions >= 0).all()
        for key, (prefix, suffix, unit) in VARIABLES.items():
            assert payload['hourly_units'][key] == unit
            raw_values = np.asarray(payload['hourly'][key], dtype=float)
            clean_values = csv.iloc[positions][f'{prefix}_{city}_{suffix}'].to_numpy()
            assert np.array_equal(raw_values, clean_values, equal_nan=True), (city, key, request['start_date'])
            checked += len(raw_values)
    for city in CITIES:
        assert pd.DatetimeIndex(coverage[city]).sort_values().equals(expected)
    assert checked == len(expected) * 18
    report = pd.read_csv(root / 'reports/weather/missing_values_report.csv').set_index('column')
    assert set(report.index) == set(columns)
    assert (report['missing_count'] == csv.isna().sum()).all()
    assert (report['missing_pct'] == 0).all()
    assert len(pd.read_csv(root / 'reports/weather/missing_intervals.csv')) == 0
    threshold_count = 0
    for col in csv:
        low, high = (-50, 60) if col.startswith('temp_') else (0, 100)
        threshold_count += int((~csv[col].between(low, high)).sum())
    assert threshold_count == len(pd.read_csv(root / 'reports/weather/anomalies.csv')) == 0
    local_days = pd.Series(1, index=idx.tz_convert('Europe/Rome')).resample('D').sum().iloc[1:-1]
    assert int((local_days == 23).sum()) == 4
    assert int((local_days == 25).sum()) == 4
    result = {
        'status': 'passed', 'source_kind': 'reanalysis', 'model': 'era5',
        'first_timestamp_utc': times.iloc[0], 'last_timestamp_utc': times.iloc[-1],
        'rows': len(csv), 'weather_columns': len(csv.columns), 'raw_responses': len(seen),
        'raw_hashes_verified': len(seen), 'cells_exactly_matched_to_raw': checked,
        'missing_cells': int(csv.isna().sum().sum()), 'duplicated_timestamps': int(idx.duplicated().sum()),
        'flagged_by_thresholds': threshold_count, 'local_days_23h': 4, 'local_days_25h': 4,
        'clean_csv_sha256': hashlib.sha256(data_path.read_bytes()).hexdigest(),
        'day_ahead_eligible': False, 'coordinates': coordinates,
    }
    return result


if __name__ == '__main__':
    print(json.dumps(verify(), indent=2))
