"""Audit a publicly posted daily GSCI history; never rebuild production data.

Inputs stay in ignored sources/raw/cmdty_1970s_research. Optional corroboration
uses the large public portfolio database if already downloaded. --download
fetches the small primary inputs from pinned/hashed public URLs. Excel readers
openpyxl and xlrd are research dependencies; matplotlib is optional.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sqlite3
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

COMMIT = 'f5ecf1507fb9cc98ffcc1f69c217793f5f9272a3'
INVESTING_SHA256 = '4320308a7a5715337e28c2f601db19d14c3a67425ae9a7aae7cfe397d8fd5ad5'
BASE = f'https://raw.githubusercontent.com/yessinemx/Trading_Commo/{COMMIT}/'
SOURCES = {
    'trading_commo_data.xlsx': (BASE + 'data/GSCI_Data.xlsx', '918e4046300180e0274781bfa6f1f5dcf2dc7df61b9229f9d4a9ea124da2a9f8', 'Daily Spot, ER and TR; author-claimed Bloomberg extract with weekday carry-forward.'),
    'trading_commo_notebook.json': (BASE + 'notebook/main.ipynb', '207727833bb7e364533df9401444123d7e5eac0bfb66abece79d81ebbcdd08cc', 'Provenance code inspected as text, never executed.'),
    'trading_commo_config.py': (BASE + 'config.py', '25f2e0954e898797bb10421db1f99aefd984ef5297b7ce30339adce97814e9a3', 'Requested index tickers and date range; inspected as text only.'),
    'duke_gsci_0406.xls': ('https://people.duke.edu/~charvey/Teaching/BA453_2005/GSCI_0406.xls', 'ae7c428e26ba56c1fb433d75db58d8c51105d1a95b63eb2745e5eb7841f0b37a', 'Older Goldman monthly index/constituent data and unvalidated weight worksheet.'),
    'quantpedia_spgscitr.csv': ('https://data.quantpedia.com/backtesting_data/index/SPGSCITR.csv', 'd29812e8c8917797725f0e3e4e5f0caf9e8d81bdd8bd09087eb1e6f4dcabeb4b', 'Daily TR delivery from 1980; upstream independence is not established.'),
    'sec_gsci_reference.pdf': ('https://www.sec.gov/files/rules/sro/nyse/2006/34-53658.pdf', '155e74ebbccb684b3146496372d7dfe4b7a1383403117bc536ffad51deea9710', 'SEC notice, dated historical TR levels, PDF pages 29-30.'),
    'kaplan_lummer_reference.pdf': ('https://www.etf.com/docs/20040913_GSCI.pdf', '7ef9683a16799cc5b55a8987eeabf0538d7f18e71124a43465ce75ae1524acc3', 'Kaplan/Lummer annual TR reference, PDF page 13; published rounding applies.'),
}
ANNUAL_TR = {
    1970: 15.10, 1971: 21.08, 1972: 42.43, 1973: 74.96, 1974: 39.51,
    1975: -17.22, 1976: -11.92, 1977: 10.37, 1978: 31.61, 1979: 33.81,
    1980: 11.08, 1981: -23.01, 1982: 11.56, 1983: 16.26, 1984: 1.05,
    1985: 10.01, 1986: 2.04, 1987: 23.77, 1988: 27.93, 1989: 38.28,
    1990: 29.08, 1991: -6.13,
}
SEC_TR = {
    '1970-01-02': 100, '1971-01-04': 115.78, '1972-01-03': 138.90,
    '1973-01-02': 198.45, '1974-01-02': 354.32, '1975-01-02': 478.50,
    '1976-01-02': 400.02, '1977-01-03': 351.05, '1978-01-03': 390.02,
    '1979-01-02': 515.25, '1980-01-02': 692.40, '1981-01-02': 764.66,
    '1982-01-04': 593.61, '1983-01-03': 657.98, '1984-01-03': 747.23,
    '1985-01-03': 760.67, '1986-01-02': 833.67, '1987-01-02': 868.83,
    '1988-01-04': 1105.18, '1989-01-03': 1371.33, '1990-01-02': 1937.46,
    '1991-01-02': 2346.03,
}


def digest(path: Path) -> str:
    with path.open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def acquire(raw: Path) -> None:
    raw.mkdir(parents=True, exist_ok=True)
    for name, (url, expected, _) in SOURCES.items():
        path = raw / name
        if not path.exists():
            request = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (public financial data research)'})
            with urllib.request.urlopen(request, timeout=30) as response:
                payload = response.read()
            if hashlib.sha256(payload).hexdigest() != expected:
                raise ValueError(f'Unexpected source version: {name}')
            path.write_bytes(payload)
            path.with_suffix(path.suffix + '.retrieval.json').write_text(json.dumps({
                'requested_url': url, 'retrieved_utc': datetime.now(timezone.utc).isoformat(),
                'sha256': expected, 'bytes': len(payload),
            }, indent=2) + '\n', encoding='utf-8')
        elif digest(path) != expected:
            raise ValueError(f'Cached source hash mismatch: {name}')


def inventory(raw: Path) -> list[dict]:
    items = []
    for name, (url, expected, note) in SOURCES.items():
        path = raw / name
        if not path.exists() or digest(path) != expected:
            raise ValueError(f'Missing or changed input {name}; run with --download')
        sidecar = path.with_suffix(path.suffix + '.retrieval.json')
        timing = json.loads(sidecar.read_text(encoding='utf-8')) if sidecar.exists() else {}
        items.append({
            'file': 'sources/raw/cmdty_1970s_research/' + name, 'source_url': url, 'sha256': expected,
            'bytes': path.stat().st_size, 'retrieved_utc': timing.get('retrieved_utc'),
            'documented_access_date': '2026-09-30', 'qualification': note,
            'redistribution': 'Public availability does not establish rights to republish vendor prices.',
        })
    return items


def compare_levels(a: pd.Series, b: pd.Series) -> dict:
    common = a.index.intersection(b.index)
    if len(common) < 2:
        raise ValueError('No meaningful comparison overlap')
    aa, bb = a.reindex(common), b.reindex(common)
    error = np.log(aa).diff() - np.log(bb).diff()
    difference = aa - bb
    return {
        'common_dates': len(common), 'first_date': str(common.min().date()),
        'last_date': str(common.max().date()), 'exact_level_matches': int(difference.eq(0).sum()),
        'max_absolute_level_difference': float(difference.abs().max()),
        'maximum_relative_difference_bps': float((aa / bb - 1).abs().max() * 10000),
        'daily_common_interval_log_return_correlation': float(np.log(aa).diff().corr(np.log(bb).diff())),
        'daily_common_interval_log_return_rmse_bps': float(np.sqrt(np.mean(error.dropna() ** 2)) * 10000),
        'log_return_pairs_matching_to_1e_7': int(error.dropna().abs().lt(1e-7).sum()),
        'return_pairs': int(error.notna().sum()),
    }


def metrics(levels: pd.Series) -> dict:
    log = np.log(levels).diff().dropna()
    simple = levels.pct_change(fill_method=None).dropna()
    drawdown = levels / levels.cummax() - 1
    return {
        'return_observations': len(log), 'annualized_simple_return_std': float(simple.std() * np.sqrt(252)),
        'annualized_log_return_std': float(log.std() * np.sqrt(252)),
        'lag_one_log_return_autocorrelation': float(log.autocorr()),
        'max_drawdown': float(drawdown.min()), 'drawdown_trough_date': str(drawdown.idxmin().date()),
        'growth_between_endpoints': float(levels.iloc[-1] / levels.iloc[0] - 1),
    }


def monthly_check(raw: Path, daily: pd.DataFrame) -> dict:
    results = {}
    book = pd.ExcelFile(raw / 'duke_gsci_0406.xls')
    for sheet, label in [('GSCI-TR', 'GSCI_TR'), ('GSCI-ER', 'GSCI_ER'), ('Spot', 'GSCI_Spot')]:
        frame = pd.read_excel(book, sheet_name=sheet, header=None)
        dates = pd.to_datetime(frame.iloc[2:, 0], errors='raise')
        monthly = pd.Series(pd.to_numeric(frame.iloc[2:, 1], errors='raise').to_numpy(), index=dates).loc['1970':'1991']
        # Month-end labels may be weekends. The sampled value is the last prior
        # weekday observation, not an interpolation or a later day's close.
        sampled = daily[label].reindex(monthly.index, method='ffill')
        error = sampled - monthly
        early = error.loc['1970':'1979']
        if len(early) != 120 or len(monthly) != 264 or sampled.isna().any():
            raise ValueError(f'Incomplete monthly comparison: {sheet}')
        results[sheet] = {
            '1970s_months': len(early), '1970_1991_months': len(monthly),
            'exact_1970s_month_end_matches': int(early.eq(0).sum()),
            'max_absolute_1970s_difference': float(early.abs().max()),
            'max_absolute_1970_1991_difference': float(error.abs().max()),
        }
    return results


def database_check(raw: Path, daily: pd.DataFrame) -> dict:
    path = raw / 'portfolio_app_history.db'
    if not path.exists():
        return {'available': False, 'qualification': 'Optional corroboration; absence does not substitute fabricated observations.'}
    if digest(path) != 'deecf9a9cca87f79f60543b1390ed731f6553782bd4f456038f152141d37faed':
        raise ValueError('Unexpected portfolio database version')
    with sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True) as db:
        db.execute('PRAGMA query_only = ON')
        prices = pd.read_sql_query('SELECT date, close FROM FACT_HISTPRICES WHERE ticker = ? ORDER BY date', db, params=('COM',), parse_dates=['date']).set_index('date')['close']
        metadata = pd.read_sql_query('SELECT * FROM DIM_STOCKS WHERE ticker = ?', db, params=('COM',)).to_dict('records')
    return {
        'available': True, 'sha256': digest(path), 'rows': len(prices),
        'first_date': str(prices.index.min().date()), 'last_date': str(prices.index.max().date()),
        'asset_metadata': metadata,
        '1970s_comparison': compare_levels(daily.GSCI_TR.loc['1970':'1979'], prices.loc['1970':'1979']),
        '1970_1991_comparison': compare_levels(daily.GSCI_TR.loc['1970':'1991'], prices.loc['1970':'1991']),
        'qualification': 'Separate public delivery with uncertain upstream source and documented cleaning. Later daily errors and level drift disqualify it as a preferred production source.',
    }


def run(root: Path, download: bool) -> dict:
    raw = root / 'sources/raw/cmdty_1970s_research'
    out = root / 'docs/research'
    production = root / 'data/processed/broad_commodities.csv'
    builder = root / 'src/build_broad_commodities.py'
    before = {'published_cmdty_sha256': digest(production), 'production_builder_sha256': digest(builder)}
    if download:
        acquire(raw)
    manifest = inventory(raw)
    daily = pd.read_excel(raw / 'trading_commo_data.xlsx', sheet_name='Données GSCI')
    if list(daily.columns) != ['Date', 'GSCI_Spot', 'GSCI_ER', 'GSCI_TR']:
        raise ValueError('Unexpected daily workbook schema')
    daily['Date'] = pd.to_datetime(daily['Date'], errors='raise')
    daily = daily.set_index('Date')
    if not daily.index.is_monotonic_increasing or daily.index.has_duplicates:
        raise ValueError('Daily dates are unsorted or duplicated')
    values = daily.to_numpy(dtype=float)
    if not np.isfinite(values).all() or (values <= 0).any():
        raise ValueError('Daily levels must be finite and positive')
    expected = pd.bdate_range('1970-01-02', '2025-12-31')
    if not daily.index.equals(expected):
        raise ValueError('The verified snapshot should contain the complete weekday calendar')
    annual = []
    for year, target in ANNUAL_TR.items():
        previous = daily.GSCI_TR.loc[:f'{year-1}-12-31']
        base = previous.iloc[-1] if len(previous) else daily.GSCI_TR.iloc[0]
        actual = float(100 * (daily.GSCI_TR.loc[str(year)].iloc[-1] / base - 1))
        annual.append({'year': year, 'reference_pct': target, 'workbook_pct': actual, 'within_reference_rounding': abs(actual - target) < 0.0050000001})
    sec = [{'date': day, 'reference_level': level, 'workbook_level': float(daily.at[pd.Timestamp(day), 'GSCI_TR']), 'matches_to_published_precision': abs(float(daily.at[pd.Timestamp(day), 'GSCI_TR']) - level) < 0.0050000001} for day, level in SEC_TR.items()]
    investing_path = root / 'sources/raw/cmdty_daily_research/investing_gsci_tr_1979_1991.csv'
    if not investing_path.exists():
        raise ValueError('The manually acquired Investing TR CSV is required for this audit')
    if digest(investing_path) != INVESTING_SHA256:
        raise ValueError('The manual Investing CSV differs from the verified research snapshot')
    inv = pd.read_csv(investing_path)
    inv['date'] = pd.to_datetime(inv['Date'], format='%m/%d/%Y', errors='raise')
    inv['close'] = pd.to_numeric(inv['Price'].astype(str).str.replace(',', '', regex=False), errors='raise')
    investing = inv.set_index('date')['close'].sort_index()
    if investing.index.has_duplicates or not np.isfinite(investing).all() or (investing <= 0).any():
        raise ValueError('Invalid Investing source observations')
    qp = pd.read_csv(raw / 'quantpedia_spgscitr.csv', parse_dates=['date']).set_index('date')['close'].sort_index()
    published_pair = pd.read_csv(production, usecols=['Date', 'Close', 'Adj Close'], parse_dates=['Date']).set_index('Date')
    published = published_pair['Adj Close']
    common = published.loc['1970':'1990'].index.intersection(daily.index)
    matched = pd.concat([published.reindex(common).rename('published'), daily.GSCI_TR.reindex(common).rename('daily')], axis=1)
    comparisons = {}
    for label, start, end in [('1970_1979', '1970', '1979'), ('1970_1983', '1970', '1983'), ('1980_1983', '1980', '1983'), ('1984_1990', '1984', '1990')]:
        sample = matched.loc[start:end]
        error = np.log(sample.daily).diff() - np.log(sample.published).diff()
        comparisons[label] = {
            'common_level_dates': len(sample), 'first_date': str(sample.index.min().date()), 'last_date': str(sample.index.max().date()),
            'workbook': metrics(sample.daily), 'published': metrics(sample.published),
            'common_interval_log_return_correlation': float(np.log(sample.daily).diff().corr(np.log(sample.published).diff())),
            'common_interval_log_return_rmse_bps': float(np.sqrt(np.mean(error.dropna() ** 2)) * 10000),
            'calendar_note': 'Both paths use the same published CMDTY dates. Gaps yield common multi-day intervals; no target return rows are discarded before cumulation.',
        }
    annual_vol = []
    matched_log_returns = np.log(matched).diff()
    for year, group in matched_log_returns.groupby(matched_log_returns.index.year):
        if year > 1983:
            continue
        annual_vol.append({'year': int(year), 'daily_log_return_vol': float(group.daily.std() * np.sqrt(252)), 'published_log_return_vol': float(group.published.std() * np.sqrt(252))})
    early = daily.loc['1970':'1979']
    er_tr_ratios = []
    for day in ['1970-01-02', '1979-12-31', '1983-12-30', '1991-01-02']:
        source_row, published_row = daily.loc[day], published_pair.loc[day]
        er_tr_ratios.append({
            'date': day, 'source_ER': float(source_row.GSCI_ER), 'source_TR': float(source_row.GSCI_TR),
            'source_TR_over_ER': float(source_row.GSCI_TR / source_row.GSCI_ER),
            'published_ER': float(published_row['Close']), 'published_TR': float(published_row['Adj Close']),
            'published_TR_over_ER': float(published_row['Adj Close'] / published_row['Close']),
        })
    monthly_results = monthly_check(raw, daily)
    investing_result = compare_levels(daily.GSCI_TR, investing)
    monthly_gate = all(r['exact_1970s_month_end_matches'] == 120 and r['max_absolute_1970_1991_difference'] < 0.0050000001 for r in monthly_results.values())
    investing_gate = investing_result['common_dates'] == 3035 and not len(investing.index.difference(daily.index)) and investing_result['max_absolute_level_difference'] < 0.001001
    if not monthly_gate or not investing_gate:
        raise ValueError('A required monthly or daily-source comparison gate failed')
    report = {
        'research_date': '2026-09-30', 'source_snapshot_commit': COMMIT,
        'coverage': {'all_rows': len(daily), 'first_date': str(daily.index.min().date()), 'last_date': str(daily.index.max().date()), '1970s_rows': len(early), '1970_1991_rows': len(daily.loc['1970':'1991']), 'calendar': 'All Monday-Friday dates; upstream previous-value fill on non-trading weekdays.', 'duplicate_dates': 0, 'missing_or_nonfinite_values': 0, 'nonpositive_levels': 0},
        '1970s_daily_shape': {'distinct_log_returns_rounded_8decimals': int(np.log(early.GSCI_TR).diff().round(8).nunique()), 'joint_unchanged_weekday_rows': int(early.diff().eq(0).all(axis=1).sum()), 'all_weekday_log_return_vol': metrics(early.GSCI_TR)['annualized_log_return_std'], 'historical_price_precision_note': 'Early levels are rounded; zero moves alone cannot identify holidays or prove a market was inactive.'},
        'annual_TR_reference_checks': annual, 'SEC_dated_TR_reference_checks': sec,
        'all_22_annual_checks_pass': all(x['within_reference_rounding'] for x in annual),
        'all_22_SEC_level_checks_pass': all(x['matches_to_published_precision'] for x in sec),
        'duke_monthly_checks': monthly_results, 'monthly_comparison_gate_pass': monthly_gate,
        'investing_comparison': investing_result, 'investing_comparison_gate_pass': investing_gate,
        'investing_dates_missing_in_workbook': len(investing.index.difference(daily.index)),
        'quantpedia_comparison_1980_1991': compare_levels(daily.GSCI_TR.loc['1980':'1991'], qp.loc['1980':'1991']),
        'public_database_corroboration': database_check(raw, daily),
        'published_CMDTY_comparisons': comparisons, 'annual_common_calendar_volatility': annual_vol,
        'ER_TR_ratio_diagnostic': er_tr_ratios,
        'ER_TR_ratio_interpretation': 'Direct ER/TR identifies a substantially different cumulative TR-to-ER uplift from the current modeled stripping. Calendar omissions and bill-yield conventions remain separate explanations; the ratio alone does not assign all discrepancy to weekends.',
        'source_independence_note': 'Deliveries and publication vintages differ; independence of their upstream index calculations is not established. Sparse published references do not independently validate every daily 1970s value.',
        'manual_investing_input': {'file': 'sources/raw/cmdty_daily_research/investing_gsci_tr_1979_1991.csv', 'sha256': digest(investing_path), 'source_url': 'https://www.investing.com/indices/sp-gsci-commodity-total-return-historical-data', 'exact_retrieval_timestamp': None, 'documented_access_date': '2026-09-30'},
        'production_before': before,
        'calculation_versions': {'python': platform.python_version(), 'pandas': pd.__version__, 'numpy': np.__version__, 'script_sha256': digest(Path(__file__))},
    }
    if not report['all_22_annual_checks_pass'] or not report['all_22_SEC_level_checks_pass']:
        raise ValueError('A required published reference check failed')
    try:
        import matplotlib.pyplot as plt
        figure, axis = plt.subplots(figsize=(10, 4.3))
        x = np.array([r['year'] for r in annual_vol])
        axis.bar(x - 0.18, [100 * r['daily_log_return_vol'] for r in annual_vol], width=0.36, color='#265c84', label='Daily GSCI TR workbook')
        axis.bar(x + 0.18, [100 * r['published_log_return_vol'] for r in annual_vol], width=0.36, color='#bd9f77', label='Published CMDTY')
        axis.set_ylabel('Annualized daily log-return volatility (%)')
        axis.set_title('Early commodity risk recovered by daily index data')
        axis.set_xticks(x)
        axis.spines[['top', 'right']].set_visible(False)
        axis.legend(frameon=False)
        axis.grid(axis='y', alpha=0.15)
        axis.set_axisbelow(True)
        figure.text(0.01, 0.005, 'Same CMDTY observation dates for both paths; sqrt(252), sample standard deviation. Research only.', fontsize=8, color='#555555')
        figure.tight_layout(rect=(0, 0.04, 1, 1))
        figure.savefig(out / 'cmdty_full_history_volatility.png', dpi=160)
        plt.close(figure)
        report['figure_created'] = True
    except ImportError:
        report['figure_created'] = False
    after = {'published_cmdty_sha256': digest(production), 'production_builder_sha256': digest(builder)}
    if before != after:
        raise RuntimeError('Production files changed while research was running')
    report['production_after'] = after
    report['production_files_unchanged'] = True
    database = raw / 'portfolio_app_history.db'
    if database.exists():
        sidecar = json.loads(database.with_suffix('.db.retrieval.json').read_text(encoding='utf-8'))
        manifest.append({
            'file': 'sources/raw/cmdty_1970s_research/portfolio_app_history.db',
            'source_url': sidecar['source_url'], 'sha256': sidecar['sha256'], 'bytes': sidecar['bytes'],
            'retrieved_utc': sidecar['retrieved_utc'], 'documented_access_date': '2026-09-30',
            'qualification': 'Read-only COM data corroboration; uncertain upstream source and later errors. Public LFS content hash verified.',
            'redistribution': 'Raw vendor observations remain ignored; no blanket redistribution permission established.',
        })
    (out / 'cmdty_full_history_retrieval_manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    (out / 'cmdty_full_history_findings.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({
        'coverage': report['coverage'], 'all_22_annual_checks_pass': report['all_22_annual_checks_pass'],
        'all_22_SEC_level_checks_pass': report['all_22_SEC_level_checks_pass'],
        'monthly_comparison_gate_pass': monthly_gate, 'investing_comparison_gate_pass': investing_gate,
        '1970s_public_database_comparison': report['public_database_corroboration'].get('1970s_comparison'),
        '1970s_published_CMDTY_comparison': comparisons['1970_1979'],
        'production_files_unchanged': True,
    }, indent=2))
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--download', action='store_true')
    args = parser.parse_args()
    run(Path(__file__).resolve().parents[1], args.download)
