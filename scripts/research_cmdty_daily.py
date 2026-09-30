"""Audit free daily futures archives and CMDTY's early daily reconstruction.

Research only: never writes production datasets. Downloaded inputs remain in
ignored sources/raw/cmdty_daily_research. Run with --download to obtain the
publicly linked TurtleTrader files, then run again offline to reproduce results.
Requires the project's pandas/numpy; matplotlib is optional for the figure.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import platform
import re
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

SYMBOLS = ['c', 's', 'w', 'sb', 'si', 'lh', 'ct', 'gc', 'hg', 'ho', 'cl', 'cr', 'kc', 'pb']
MONTH_CODES = 'FGHJKMNQUVXZ'
# Illustrative CURRENT schedules, not verified historical GSCI replication.
SCHEDULES = {
    'c': 'HHKKNNUUZZZH', 'w': 'HHKKNNUUZZZH',
    's': 'HHKKNNXXXXFF', 'sb': 'HHKKNNVVVHHH',
    'si': 'HHKKNNUUZZZH', 'ct': 'HHKKNNZZZZZH',
    'gc': 'GJJMMQQZZZZG', 'kc': 'HHKKNNUUZZZH',
    'lh': 'GJJMMNQVVZZG', 'ho': 'GHJKMNQUVXZF',
    'cl': 'GHJKMNQUVXZF',
}
YAHOO_SPGSCI_URL = 'https://query1.finance.yahoo.com/v8/finance/chart/%5ESPGSCI?period1=441763200&period2=694224000&interval=1d'
CSI_URL = 'https://apps.csidata.com/factsheets.php?type=commodity&format=csv'
INVESTING_TR_URL = 'https://www.investing.com/indices/sp-gsci-commodity-total-return-historical-data'
# Manually transcribed independent reference values, not fitted to the CSV.
SEC_TR_REFERENCE_URL = 'https://www.sec.gov/rules/sro/nyse/2006/34-53658.pdf'
SEC_TR_LEVELS = {
    '1980-01-02': 692.40, '1981-01-02': 764.66, '1982-01-04': 593.61,
    '1983-01-03': 657.98, '1984-01-03': 747.23, '1985-01-03': 760.67,
    '1986-01-02': 833.67, '1987-01-02': 868.83, '1988-01-04': 1105.18,
    '1989-01-03': 1371.33, '1990-01-02': 1937.46, '1991-01-02': 2346.03,
}
KAPLAN_LUMMER_URL = 'https://www.etf.com/docs/20040913_GSCI.pdf'
KAPLAN_LUMMER_ANNUAL_TR = {
    1980: 11.08, 1981: -23.01, 1982: 11.56, 1983: 16.26, 1984: 1.05,
    1985: 10.01, 1986: 2.04, 1987: 23.77, 1988: 27.93,
    1989: 38.28, 1990: 29.08, 1991: -6.13,
}
SOURCE_PAGES = {
    'turtle_page.html': 'https://www.turtletrader.com/hpd/',
    'cycle_catalog.html': 'https://cycle-trader.com/catalog/',
    **{f'cycle_{s}.html': f'https://cycle-trader.com/data/{s}/' for s in ['live-cattle', 'corn', 'soybeans', 'wheat']},
}

def remember_retrieval(path: Path, url: str) -> None:
    path.with_suffix(path.suffix + '.retrieval.json').write_text(json.dumps({
        'source_url': url,
        'retrieval_timestamp_utc': datetime.now(timezone.utc).isoformat(),
        'sha256_at_retrieval': hashlib.sha256(path.read_bytes()).hexdigest(),
    }, indent=2) + '\n', encoding='utf-8')

def source_metadata(path: Path, url: str, kind: str, root: Path) -> dict:
    sidecar = path.with_suffix(path.suffix + '.retrieval.json')
    timing = json.loads(sidecar.read_text(encoding='utf-8')) if sidecar.exists() else {
        'retrieval_timestamp_utc': None,
        'documented_access_date': '2026-09-30',
        'access_date_basis': 'Research-session date; exact original fetch timestamp was not retained.',
    }
    return {
        'path': path.relative_to(root).as_posix(), 'source_url': url, 'kind': kind,
        'bytes': path.stat().st_size, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
        **timing,
        'qualification': 'Access does not establish redistribution permission; vendor prices and conventions require independent checks.',
    }

def download_spot(raw: Path) -> None:
    path = raw / 'yahoo_spgsci.json'
    if not path.exists():
        request = urllib.request.Request(YAHOO_SPGSCI_URL, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = response.read()
        data = json.loads(payload)['chart']['result'][0]
        if data['meta']['symbol'] != '^SPGSCI':
            raise ValueError('Yahoo returned the wrong index')
        path.write_bytes(payload)
        remember_retrieval(path, YAHOO_SPGSCI_URL)

def boundary_audit(root: Path) -> dict:
    import importlib.util
    spec = importlib.util.spec_from_file_location('commodity_builder', root / 'src/build_broad_commodities.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    spot = [{'Date': d, 'Close': 100} for d in ['1984-01-03', '1984-01-04', '1984-01-05', '1984-01-06', '1984-01-09']]
    bcom = [{'Date': d, 'Close': 100} for d in ['1984-01-09', '1984-01-10', '1984-01-11']]
    dbc = [{'Date': d, 'Close': 100, 'Adj Close': 100} for d in ['1984-01-10', '1984-01-11', '1984-01-12']]
    irx = [{'Date': d, 'Close': 1} for d in ['1970-01-02', '1984-01-03', '1984-01-04', '1984-01-05', '1984-01-06', '1984-01-09']]
    anchors = [('1970-01-02', 100), ('1984-01-03', 100), ('1984-01-12', 110)]
    rows = module.build_normalized_rows(spot, bcom, dbc, irx, anchors)
    value = next(float(r['Adj Close']) for r in rows if r['Date'] == '1984-01-09')
    return {'synthetic_full_anchor_return': 0.10, 'synthetic_anchor_endpoint': '1984-01-12', 'shape_segment_last_date': '1984-01-09', 'level_at_shape_end': value, 'full_target_allocated_before_endpoint': math.isclose(value, 110), 'note': 'Structural reproduction only; actual historical bias cannot be measured without the original anchor cache.'}

def download(root: Path, symbol: str) -> dict:
    url = f'https://www.turtletrader.com/cddata/{symbol}.zip'
    path = root / f'turtle_{symbol}.zip'
    if not path.exists():
        request = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = response.read()
        if not zipfile.is_zipfile(io.BytesIO(payload)):
            raise ValueError(f'{url} did not return a ZIP file')
        path.write_bytes(payload)
        remember_retrieval(path, url)
    return {'symbol': symbol, 'url': url, 'path': str(path)}

def parse_archive(path: Path, symbol: str) -> tuple[pd.DataFrame, dict]:
    records, rejected, parse_errors = [], [], []
    with zipfile.ZipFile(path) as archive:
        for member in archive.namelist():
            match = re.fullmatch(re.escape(symbol) + r'(\d{2})([FGHJKMNQUVXZ])\.txt', Path(member).name, re.I)
            if not match:
                rejected.append(member)
                continue
            year = int(match[1]) + (1900 if int(match[1]) >= 50 else 2000)
            month = MONTH_CODES.index(match[2].upper()) + 1
            contract = f'{symbol.upper()}{year}{match[2].upper()}'
            reader = csv.reader(io.StringIO(archive.read(member).decode('utf-8', errors='replace')))
            for number, fields in enumerate(reader, 1):
                if not fields or fields[0].strip().lower() == 'date':
                    continue
                try:
                    stamp = fields[0].strip()
                    if '/' in stamp:
                        day = datetime.strptime(stamp, '%m/%d/%Y').date()
                    else:
                        yy = int(stamp[:2])
                        day = date(yy + (1900 if yy >= 50 else 2000), int(stamp[2:4]), int(stamp[4:6]))
                    values = [float(v) for v in fields[1:7]]
                    if len(values) != 6:
                        raise ValueError('Expected OHLC, volume and open interest')
                    records.append((day, contract, year, month, *values))
                except (ValueError, IndexError) as exc:
                    parse_errors.append(f'{member}:{number}: {exc}')
    columns = ['date', 'contract', 'year', 'month', 'open', 'high', 'low', 'close', 'volume', 'open_interest']
    frame = pd.DataFrame(records, columns=columns)
    frame['date'] = pd.to_datetime(frame['date'])
    duplicate = int(frame.duplicated(['date', 'contract']).sum())
    nonpositive = int((frame['close'] <= 0).sum())
    bad_ohlc = int(((frame['low'] > frame['high']) | (frame['close'] < frame['low']) | (frame['close'] > frame['high'])).sum())
    frame = frame.sort_values(['contract', 'date'])
    frame['contract_return'] = frame.groupby('contract')['close'].pct_change()
    early = frame[(frame['date'] >= '1970-01-01') & (frame['date'] <= '1991-01-02')]
    summary = {
        'symbol': symbol, 'source_url': f'https://www.turtletrader.com/cddata/{symbol}.zip',
        'documented_access_date': '2026-09-30',
        'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
        'bytes': path.stat().st_size, 'contracts': int(frame['contract'].nunique()),
        'first_date': frame['date'].min().date().isoformat(),
        'last_date': frame['date'].max().date().isoformat(),
        'records': len(frame), 'early_records': len(early),
        'early_unique_dates': int(early['date'].nunique()),
        'rejected_members': rejected, 'parse_errors': parse_errors,
        'duplicate_contract_dates': duplicate, 'nonpositive_closes': nonpositive,
        'ohlc_inconsistencies': bad_ohlc,
        'early_same_contract_moves_over_20pct': int((early['contract_return'].abs() > 0.20).sum()),
    }
    # Reject invalid arithmetic without silently clipping or correcting outliers.
    frame = frame.drop_duplicates(['date', 'contract']).set_index(['date', 'contract']).sort_index()
    return frame, summary

def contract_name(symbol: str, year: int, month: int, code: str) -> str:
    delivery_month = MONTH_CODES.index(code) + 1
    delivery_year = year + (delivery_month < month)
    return f'{symbol.upper()}{delivery_year}{code}'

def commodity_returns(frame: pd.DataFrame, symbol: str, calendar: pd.DatetimeIndex) -> tuple[pd.Series, dict]:
    """P&L on yesterday's two-contract quantities; no cross-contract price ratio.

    Roll fractions change after settlement on the fifth through ninth dates in
    each research calendar month. The calendar is the observed core-grain union.
    Missing prices produce missing returns rather than implicit zero returns.
    """
    schedule = SCHEDULES[symbol]
    prices = frame['close'].unstack('contract').reindex(calendar)
    day_number = pd.Series(np.arange(len(calendar)), index=calendar).groupby([calendar.year, calendar.month]).cumcount() + 1
    holdings = {}
    for day in calendar:
        month = day.month
        out_code = schedule[month - 1]
        next_month = month % 12 + 1
        in_code = schedule[next_month - 1]
        out_contract = contract_name(symbol, day.year, month, out_code)
        in_year = day.year + (month == 12)
        in_contract = contract_name(symbol, in_year, next_month, in_code)
        fraction = min(1.0, max(0.0, (int(day_number.loc[day]) - 4) / 5))
        holdings[day] = {out_contract: 1.0} if out_contract == in_contract else {out_contract: 1 - fraction, in_contract: fraction}
    returns = pd.Series(np.nan, index=calendar, dtype=float)
    unavailable = []
    for previous, day in zip(calendar, calendar[1:]):
        numerator = denominator = 0.0
        for contract, quantity in holdings[previous].items():
            if quantity == 0:
                continue
            if contract not in prices.columns:
                unavailable.append((day.date().isoformat(), contract))
                break
            before, after = prices.loc[previous, contract], prices.loc[day, contract]
            if not (np.isfinite(before) and np.isfinite(after) and before > 0 and after > 0):
                unavailable.append((day.date().isoformat(), contract))
                break
            numerator += quantity * (after - before)
            denominator += quantity * before
        else:
            if denominator > 0:
                returns.loc[day] = numerator / denominator
    return returns, {'valid_returns': int(returns.notna().sum()), 'missing_examples': unavailable[:12]}

def metrics(returns: pd.Series) -> dict:
    valid = returns.dropna()
    level = (1 + valid).cumprod()
    return {
        'rows': len(valid), 'annualized_volatility': float(valid.std(ddof=1) * math.sqrt(252)),
        'lag1_autocorrelation': float(valid.autocorr(1)),
        'best_day': float(valid.max()), 'worst_day': float(valid.min()),
        'max_drawdown': float((level / level.cummax() - 1).min()),
    }

def bridge(log_returns: np.ndarray, endpoints: list[int]) -> np.ndarray:
    """Constant geometric interpolation from observed endpoint log changes."""
    result = np.empty_like(log_returns)
    for left, right in zip(endpoints, endpoints[1:]):
        result[left:right] = log_returns[left:right].sum() / (right - left)
    return result

def audit_daily_tr(path: Path, current: pd.DataFrame, spot: pd.Series) -> dict:
    """Inspect a user-supplied third-party export without assuming its identity.

    Compare levels on a common calendar before differencing, so unmatched
    observation dates never silently disappear from cumulative target returns.
    """
    source = pd.read_csv(path)
    days = pd.to_datetime(source['Date'], format='%m/%d/%Y')
    values = pd.to_numeric(source['Price'].astype(str).str.replace(',', '', regex=False))
    if days.duplicated().any() or (values <= 0).any():
        raise ValueError('Daily TR export contains duplicate dates or nonpositive levels')
    levels = pd.Series(values.to_numpy(), index=days).sort_index()
    printed_changes = pd.Series(pd.to_numeric(source['Change %'].astype(str).str.rstrip('%')).to_numpy() / 100, index=days).sort_index()
    returns = levels.pct_change().dropna()
    change_error = (printed_changes.reindex(returns.index) - returns).abs()
    common = levels.index.intersection(current.index)
    common = common[common <= pd.Timestamp('1991-01-02')]
    comparison = pd.DataFrame({'downloaded_tr': levels.reindex(common), 'published_cmdty': current['Adj Close'].reindex(common)})
    periods = {}
    for label, start, end in [('1980_1983', '1980-01-02', '1983-12-30'), ('1984_1990', '1984-01-03', '1990-12-31')]:
        interval = comparison.loc[start:end]
        paired_returns = interval.pct_change().dropna()
        ratio = (interval['published_cmdty'] / interval['published_cmdty'].iloc[0]) / (interval['downloaded_tr'] / interval['downloaded_tr'].iloc[0])
        periods[label] = {
            'common_dates': len(interval), 'return_interval_count': len(paired_returns),
            'return_comparison': 'Level changes between consecutive common close dates; unmatched dates are aggregated into their enclosing interval, not omitted.',
            'downloaded_tr_metrics_on_own_calendar': metrics(returns.loc[start:end]),
            'downloaded_tr_metrics_on_common_intervals': metrics(paired_returns['downloaded_tr']),
            'published_cmdty_metrics_on_common_intervals': metrics(paired_returns['published_cmdty']),
            'raw_return_correlation_common_intervals': float(paired_returns.corr().loc['downloaded_tr', 'published_cmdty']),
            'daily_log_return_rmse_common_intervals_bps': float(np.sqrt(np.mean((np.log1p(paired_returns['downloaded_tr']) - np.log1p(paired_returns['published_cmdty']))**2)) * 10000),
            'downloaded_tr_growth_between_common_endpoints': float(interval['downloaded_tr'].iloc[-1] / interval['downloaded_tr'].iloc[0] - 1),
            'published_cmdty_growth_between_common_endpoints': float(interval['published_cmdty'].iloc[-1] / interval['published_cmdty'].iloc[0] - 1),
            'normalized_level_ratio_at_end': float(ratio.iloc[-1]),
            'normalized_level_ratio_min': float(ratio.min()), 'normalized_level_ratio_max': float(ratio.max()),
        }
    overlap = levels.index.intersection(spot.index)
    observed = pd.DataFrame({'tr': levels.reindex(overlap), 'spot': spot.reindex(overlap)})
    paired = observed.pct_change().dropna()
    annual = []
    for year, series in levels.groupby(levels.index.year):
        previous = levels.loc[levels.index < series.index.min()]
        annual.append({'year': int(year), 'rows': len(series), 'first_date': series.index.min().date().isoformat(), 'last_date': series.index.max().date().isoformat(), 'calendar_year_return_if_prior_close_available': float(series.iloc[-1] / previous.iloc[-1] - 1) if len(previous) else None})
    level_checks = [{'date': day, 'reference': value, 'downloaded': float(levels.loc[day]), 'absolute_error': abs(float(levels.loc[day]) - value)} for day, value in SEC_TR_LEVELS.items() if pd.Timestamp(day) in levels.index]
    annual_checks = [{'year': row['year'], 'reference_return_pct': KAPLAN_LUMMER_ANNUAL_TR[row['year']], 'downloaded_return_pct': row['calendar_year_return_if_prior_close_available'] * 100, 'absolute_error_percentage_points': abs(row['calendar_year_return_if_prior_close_available'] * 100 - KAPLAN_LUMMER_ANNUAL_TR[row['year']])} for row in annual if row['year'] in KAPLAN_LUMMER_ANNUAL_TR and row['calendar_year_return_if_prior_close_available'] is not None]
    return {
        'source_url': INVESTING_TR_URL, 'delivery': 'User-supplied CSV; source inferred from requested page and export filename, not authenticated official index metadata.',
        'price_field': 'Price', 'rows': len(levels), 'first_date': levels.index.min().date().isoformat(), 'last_date': levels.index.max().date().isoformat(),
        'weekend_observations': int((levels.index.weekday >= 5).sum()), 'largest_calendar_gap_days': int(levels.index.to_series().diff().dt.days.max()),
        'printed_change_max_absolute_error': float(change_error.max()), 'printed_change_errors_above_rounding_tolerance': int((change_error > 0.000051).sum()),
        'duplicate_dates': 0, 'annual_coverage_and_returns': annual, 'published_cmdty_comparison': periods,
        'independent_reference_checks': {
            'sec_2006_filing': {'url': SEC_TR_REFERENCE_URL, 'pages': '29-30', 'checks': level_checks, 'all_within_quoted_rounding': all(row['absolute_error'] <= 0.0051 for row in level_checks)},
            'kaplan_lummer_1997_official_gsci_series': {'url': KAPLAN_LUMMER_URL, 'location': 'Appendix A, page 13; preface and endnote 3 identify official Goldman Sachs TR data', 'checks': annual_checks, 'all_within_published_rounding': all(row['absolute_error_percentage_points'] <= 0.0051 for row in annual_checks)},
        },
        'spot_overlap': {
            'rows': len(paired), 'first_date': observed.index.min().date().isoformat(), 'last_date': observed.index.max().date().isoformat(),
            'daily_return_correlation': float(paired.corr().loc['tr', 'spot']),
            'tr_growth': float(observed['tr'].iloc[-1] / observed['tr'].iloc[0] - 1), 'spot_growth': float(observed['spot'].iloc[-1] / observed['spot'].iloc[0] - 1),
        },
        'qualification': 'Daily frequency, 12 official-reference date levels, and 12 independently published annual returns support GSCI TR identity. Sparse checks do not independently validate every daily value or establish publication rights. Pre-1991 history is back-calculated.',
    }

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path('.'))
    parser.add_argument('--download', action='store_true')
    args = parser.parse_args()
    root = args.root.resolve()
    raw = root / 'sources/raw/cmdty_daily_research'
    output = root / 'docs/research'
    raw.mkdir(parents=True, exist_ok=True)
    output.mkdir(parents=True, exist_ok=True)
    if args.download:
        with ThreadPoolExecutor(max_workers=4) as executor:
            for result in executor.map(lambda s: download(raw, s), SYMBOLS):
                print('downloaded', result['symbol'])
        download_spot(raw)
    frames, coverage = {}, []
    for symbol in SYMBOLS:
        path = raw / f'turtle_{symbol}.zip'
        if path.exists():
            frames[symbol], summary = parse_archive(path, symbol)
            coverage.append(summary)
    missing = [symbol for symbol in SYMBOLS if symbol not in frames]
    if missing or not (raw / 'yahoo_spgsci.json').exists():
        raise RuntimeError(f'Incomplete research inputs: missing archives {missing} or Yahoo spot JSON; rerun with --download')
    dates = set()
    for symbol in ['c', 's', 'w']:
        dates.update(frames[symbol].index.get_level_values('date'))
    calendar = pd.DatetimeIndex(sorted(d for d in dates if pd.Timestamp('1969-12-01') <= d <= pd.Timestamp('1991-01-02')))
    panel, roll_coverage = {}, {}
    for symbol in SCHEDULES:
        if symbol in frames:
            panel[symbol], roll_coverage[symbol] = commodity_returns(frames[symbol], symbol, calendar)
    panel = pd.DataFrame(panel)
    # An observed-data demonstration, not an estimate of GSCI composition.
    grains = panel[['c', 's', 'w']].mean(axis=1, skipna=False)
    current = pd.read_csv(root / 'data/processed/broad_commodities.csv', usecols=['Date', 'Adj Close', 'Total Return', 'Quality Flag'])
    current['Date'] = pd.to_datetime(current['Date'])
    current = current.set_index('Date')
    results = {
        'archive_coverage': coverage, 'illustrative_roll_coverage': roll_coverage, 'metrics': {},
        'input_hashes': {'published_cmdty_csv': hashlib.sha256((root / 'data/processed/broad_commodities.csv').read_bytes()).hexdigest()},
        'boundary_audit': boundary_audit(root),
        'calculation_versions': {
            'python': platform.python_version(), 'numpy': np.__version__, 'pandas': pd.__version__,
            'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'builder_sha256': hashlib.sha256((root / 'src/build_broad_commodities.py').read_bytes()).hexdigest(),
        },
    }
    manifest = [source_metadata(raw / f'turtle_{s}.zip', f'https://www.turtletrader.com/cddata/{s}.zip', 'individual_futures_archive', root) for s in SYMBOLS]
    manifest.append(source_metadata(raw / 'yahoo_spgsci.json', YAHOO_SPGSCI_URL, 'daily_index_comparison', root))
    if (raw / 'csi_factsheets.csv').exists():
        manifest.append(source_metadata(raw / 'csi_factsheets.csv', CSI_URL, 'vendor_coverage_claims', root))
    for filename, url in SOURCE_PAGES.items():
        if (raw / filename).exists():
            manifest.append(source_metadata(raw / filename, url, 'cached_source_page', root))
    for item in manifest:
        symbol = next((s for s in SYMBOLS if item['path'].endswith(f'turtle_{s}.zip')), None)
        if symbol:
            row = next(row for row in coverage if row['symbol'] == symbol)
            item['observed_coverage'] = {k: row[k] for k in ['first_date', 'last_date', 'records', 'contracts']}
    for label, start, end in [('1970_1983', '1970-01-02', '1983-12-30'), ('1984_1990', '1984-01-03', '1990-12-31')]:
        results['metrics'][label] = {
            'current_cmdty': metrics(current.loc[start:end, 'Total Return']),
            'illustrative_equal_weight_grains_er': metrics(grains.loc[start:end]),
        }
    yahoo_path = raw / 'yahoo_spgsci.json'
    if yahoo_path.exists():
        results['input_hashes']['yahoo_spgsci'] = {'sha256': hashlib.sha256(yahoo_path.read_bytes()).hexdigest(), 'url': YAHOO_SPGSCI_URL}
        data = json.loads(yahoo_path.read_text())['chart']['result'][0]
        spot = pd.Series(data['indicators']['quote'][0]['close'], index=pd.to_datetime(data['timestamp'], unit='s', utc=True).tz_convert('America/New_York').tz_localize(None).normalize()).dropna()
        next(item for item in manifest if item['kind'] == 'daily_index_comparison')['observed_coverage'] = {
            'first_date': spot.index.min().date().isoformat(), 'last_date': spot.index.max().date().isoformat(), 'records': len(spot),
            'symbol': data['meta']['symbol'], 'exchange': data['meta']['exchangeName'], 'price_field': 'close',
        }
        spot_returns = spot.pct_change().dropna().loc[:'1990-12-31']
        results['metrics']['observed_gsci_spot_1984_1990'] = metrics(spot_returns)
        # Contiguous test blocks; fitted coefficients are estimated on earlier
        # daily spot returns, never on the validation block or its endpoints.
        spot_calendar = spot.index
        spot_panel = pd.DataFrame({s: commodity_returns(frames[s], s, spot_calendar)[0] for s in SCHEDULES if s in frames})
        pairs = spot_panel.join(spot_returns.rename('target'), how='inner')
        all_predictors = [s for s in ['c', 's', 'w', 'sb', 'si', 'lh', 'ct', 'gc', 'ho', 'cl', 'kc'] if s in pairs]
        cv = []
        for year in [1987, 1988, 1989, 1990]:
            for predictor_set, names in [('grains_only', ['c', 's', 'w']), ('available_multisector', all_predictors)]:
                clean = pairs[names + ['target']].dropna()
                train = clean[clean.index.year < year]
                test = pairs[pairs.index.year == year]
                available = test[names].notna().all(axis=1)
                if len(train) < 300 or available.sum() < 100:
                    continue
                X, y = train[names].to_numpy(), train['target'].to_numpy()
                # Ridge regression through origin. Scale uses training data only.
                scale = X.std(axis=0)
                X = X / scale
                coefficients = np.linalg.solve(X.T @ X + 10 * np.eye(X.shape[1]), X.T @ y)
                pred = (test.loc[available, names].to_numpy() / scale) @ coefficients
                target_log = np.log1p(test['target'].to_numpy())
                endpoints = list(range(0, len(test), 40)) + [len(test)]
                smooth = bridge(target_log, endpoints)
                # Keep every observed index date in the target path. Explicit
                # diagnostic fallback on unavailable dates, never an assertion
                # that the underlying futures return actually equals zero.
                pred_log = np.zeros(len(test))
                pred_log[available.to_numpy()] = np.log1p(pred)
                anchored = pred_log + bridge(target_log - pred_log, endpoints)
                complete_target_log = target_log[available.to_numpy()]
                cv.append({
                    'year': year, 'predictors': predictor_set, 'train_rows': len(train), 'test_rows': len(test),
                    'complete_prediction_rows': int(available.sum()), 'fallback_rows': int((~available).sum()),
                    'fallback_policy': 'Zero predicted log return only where a full predictor set is unavailable; apply the common drift bridge afterward. Diagnostic assumption, not observed market returns.',
                    'unavailable_dates_and_target_returns': {day.date().isoformat(): float(value) for day, value in test.loc[~available, 'target'].items()},
                    'raw_daily_correlation_on_complete_dates': float(np.corrcoef(pred, test.loc[available, 'target'])[0, 1]),
                    'full_target_growth': float(np.expm1(target_log.sum())),
                    'complete_case_target_growth_for_audit': float(np.expm1(complete_target_log.sum())),
                    'max_endpoint_log_error': float(max(abs((anchored - target_log)[left:right].sum()) for left, right in zip(endpoints, endpoints[1:]))),
                    'smoothed_rmse_bps': float(np.sqrt(np.mean((smooth - target_log)**2)) * 10000),
                    'daily_proxy_bridged_rmse_bps': float(np.sqrt(np.mean((anchored - target_log)**2)) * 10000),
                    'observed_daily_log_volatility': float(target_log.std(ddof=1) * math.sqrt(252)),
                    'smoothed_daily_log_volatility': float(smooth.std(ddof=1) * math.sqrt(252)),
                    'daily_proxy_bridged_log_volatility': float(anchored.std(ddof=1) * math.sqrt(252)),
                    'coefficients_unscaled': dict(zip(names, (coefficients / scale).tolist())),
                })
        results['masked_endpoint_experiment_gsci_spot_only'] = cv
        tr_path = raw / 'investing_gsci_tr_1979_1991.csv'
        if tr_path.exists():
            tr_metadata = source_metadata(tr_path, INVESTING_TR_URL, 'user_supplied_daily_tr_export', root)
            results['user_supplied_daily_tr_audit'] = audit_daily_tr(tr_path, current, spot)
            tr_metadata['observed_coverage'] = {k: results['user_supplied_daily_tr_audit'][k] for k in ['rows', 'first_date', 'last_date', 'price_field']}
            tr_metadata['qualification'] = results['user_supplied_daily_tr_audit']['qualification']
            manifest.append(tr_metadata)
    # Audit the collateral ratio implied by the published early series.
    dataset = pd.read_csv(root / 'data/processed/broad_commodities.csv', usecols=['Date', 'Close', 'Adj Close'])
    dataset['Date'] = pd.to_datetime(dataset['Date'])
    dataset = dataset.set_index('Date').loc[:'1991-01-02']
    accrual = ((dataset['Adj Close'] / dataset['Close']).pct_change()).dropna()
    elapsed = dataset.index.to_series().diff().dt.days.reindex(accrual.index)
    results['collateral_audit'] = {
        'implemented_accumulation_factor': float((1 + accrual).prod()),
        'calendar_gap_accumulation_factor_using_same_implied_rates': float(((1 + accrual)**elapsed).prod()),
        'omitted_calendar_days': int((elapsed - 1).sum()),
        'note': 'Sensitivity using same-row implied rates, not an official GSCI collateral reconstruction; production uses one accrual per row.',
    }
    result_path = output / 'cmdty_daily_findings.json'
    result_path.write_text(json.dumps(results, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    (output / 'cmdty_daily_retrieval_manifest.json').write_text(json.dumps({'sources': manifest}, indent=2) + '\n', encoding='utf-8')
    # Aggregated findings only; no source observations are published here.
    pd.DataFrame([{k: v for k, v in row.items() if not isinstance(v, list)} for row in coverage]).to_csv(output / 'cmdty_daily_source_inventory.csv', index=False)
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        fig, axes = plt.subplots(2, 1, figsize=(11, 6), sharex=True)
        for ax, series, title in [(axes[0], current['Total Return'], 'Published CMDTY: smoothed total returns'), (axes[1], grains, 'Daily individual-contract grain basket: illustrative excess returns')]:
            sample = series.loc['1972-01-01':'1974-12-31']
            ax.plot(sample.index, sample * 100, linewidth=0.7, color='#145a75')
            ax.set_title(title, loc='left', fontsize=11)
            ax.set_ylabel('Daily return (%)')
            ax.grid(alpha=0.2)
            ax.set_ylim(-8, 8)
        fig.suptitle('Observed daily movements exist before 1984\nDifferent exposures: this demonstrates information lost to smoothing, not GSCI replication.', fontsize=12)
        fig.tight_layout()
        fig.savefig(output / 'cmdty_daily_vs_smoothing.png', dpi=160)
        plt.close(fig)
        tr_path = raw / 'investing_gsci_tr_1979_1991.csv'
        if tr_path.exists():
            source = pd.read_csv(tr_path)
            levels = pd.Series(pd.to_numeric(source['Price'].astype(str).str.replace(',', '', regex=False)).to_numpy(), index=pd.to_datetime(source['Date'], format='%m/%d/%Y')).sort_index()
            observed = levels.loc['1980-01-02':'1983-12-30']
            published = current.loc['1980-01-02':'1983-12-30', 'Adj Close']
            fig, axes = plt.subplots(2, 1, figsize=(11, 7), sharex=True)
            axes[0].plot(observed.index, observed / observed.iloc[0] * 100, color='#145a75', linewidth=1, label='Downloaded daily GSCI TR')
            axes[0].plot(published.index, published / published.iloc[0] * 100, color='#b66b28', linewidth=1, label='Current CMDTY')
            axes[0].set_ylabel('Level (Jan 2, 1980 = 100)')
            axes[0].legend(frameon=False, loc='lower left')
            axes[1].plot(observed.index, levels.pct_change().reindex(observed.index) * 100, color='#145a75', linewidth=0.7)
            axes[1].plot(published.index, current['Total Return'].reindex(published.index) * 100, color='#b66b28', linewidth=0.7)
            axes[1].set_ylabel('Daily return (%)')
            for ax in axes:
                ax.grid(alpha=0.2)
            fig.suptitle('1980–1983: daily GSCI TR export versus current smoothed CMDTY\nIndex identity supported by SEC levels and published annual returns; daily values remain vendor-sourced.', fontsize=11)
            fig.tight_layout()
            fig.savefig(output / 'cmdty_daily_tr_validation.png', dpi=160)
            plt.close(fig)
    except ImportError:
        pass
    print(json.dumps({'output': str(result_path), 'sources': len(coverage), 'metrics': results['metrics'], 'collateral': results['collateral_audit'], 'masked_endpoint_experiment': results.get('masked_endpoint_experiment_gsci_spot_only')}, indent=2))

if __name__ == '__main__':
    main()
