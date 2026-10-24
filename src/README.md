# Source Code

Pipeline code lives here.

Expected modules and scripts:

- Source download clients.
- Raw-to-interim normalizers.
- Interim-to-processed builders.
- Pandas loading helpers for backtest scripts.
- Shared validation utilities.
- Incremental update scripts that refetch recent API data, stitch by date, recompute returns, and rewrite synchronized CSV/Parquet outputs.
- `update_all_datasets.py`, the top-level updater for the full processed dataset suite.
- `incremental_update.py`, shared overlap, source retrieval, and output logic.
- `cpi_sources.py`, BLS/FRED delivery, CPI overlap checks, and source-evidence validation used by the publication gate.

## Updating All Datasets

Run from the project root:

```text
python src\update_all_datasets.py
```

The script updates all processed datasets in dependency order:

1. Base datasets: `USLCAP`, `STT`, `ITT`, `LTT`, `GOLDPM`, `CMDTY`, `CPI`.
2. Global blends that depend on base datasets: `GLSTOCK`, `GLBOND`, `GLSTBOND`.
3. Leveraged derived datasets: `USLCAP3X`, `LTT3X`, `ITT3X`, `GOLD2X`.

By default it:

- passes today's date as `--end-date` to each underlying update script;
- runs base datasets before derived datasets;
- stops on the first failure so dependent datasets are not rebuilt from stale bases;
- prints a final row-count/date-range summary; and
- runs `python -m pytest -q tests/validation tests/automation` after successful updates, with third-party pytest plugin autoload disabled by default.

The local command defaults to today's date. The scheduled workflow explicitly
targets yesterday in New York. Both stop before publication if an update,
validation check, or current-source publication check fails; running the local
orchestrator by itself does not commit or push.

Useful options:

```text
python src\update_all_datasets.py --list-datasets
python src\update_all_datasets.py --dry-run --no-tests
python src\update_all_datasets.py --end-date YYYY-MM-DD
python src\update_all_datasets.py --only USLCAP GOLDPM GOLD2X
python src\update_all_datasets.py --skip GLBOND --continue-on-error
python src\update_all_datasets.py --refresh-static-sources
python src\update_all_datasets.py --refresh-historical-sources
```

Notes:

- Replace `YYYY-MM-DD` with an inclusive date on or after every selected dataset's committed last date.
- Market datasets can end before `--end-date` on weekends, holidays, or source delays. CPI is calendar-daily and must reach the target, using the latest accepted monthly level for documented carry-forward rows; its monthly observation must be no more than 90 days old.
- The script delegates to the existing per-dataset update scripts rather than duplicating source logic.
- `--only` and `--skip` accept aliases, asset ids, output stems, or update script stems. Derived datasets require their base dependency to be selected unless `--allow-stale-dependencies` is used.
- Full `GLBOND` and `GLSTBOND` builders reuse cached historical JST/BIS/OECD/MoF/BoE raw files by default. Their ordinary updates need only the committed baselines, refreshed dependencies, and live ETF tails. Use `--refresh-static-sources` to invoke those historical builders and refetch their heavy inputs deliberately.
- Ordinary updates preserve fixed history from the committed CSV without opening its historical raw caches. The full builders for `USLCAP`, `STT`, `ITT`, `LTT`, `CMDTY`, and `GLSTOCK` validate and reuse those inputs. Use `--refresh-historical-sources` to invoke those builders and try refreshing their historical inputs; a valid cache is retained if an optional historical refresh fails.
- CPI tries BLS first, then FRED's standard CPIAUCSL CSV export after transient BLS failures, then FRED's public data table after a transient CSV failure. The same BLS monthly series, exact committed overlap, and fresh source evidence are required on every accepted route. Repeat CPI updates refresh the evidence metadata even when daily rows are unchanged. The explicit full CPI builder still requires BLS access.
- CMDTY now uses a hash-pinned daily GSCI ER/TR workbook on its preserved historical dates. `python src/build_broad_commodities.py --migrate-gsci` replaces the early segment while preserving a committed processed tail, with no Yahoo requests. Ordinary updates still fetch recent DBC only; raw-source full rebuilds need permitted BCOM/IRX historical caches. See [the methodology](../docs/methodology_cmdty.md).

The scheduled publisher runs the same two test suites, then
`scripts/check_daily_diff.py`, synchronizes README dates, and stages only the
explicit publication allowlist. Its checkout/setup actions use Node.js 24;
the dataset pipeline uses Python 3.11. See the
[daily refresh operations guide](../docs/operations/daily-refresh.md) for
commands, provenance fields, runtime settings, and recovery checks.

## README chart assets

Install `requirements-visuals.txt`, then regenerate both images from the current
processed `Adj Close` columns:

```text
python src/create_readme_chart.py
python src/create_social_preview.py
```

The README chart is 1920 × 1080 (1080p); the social preview is 1280 × 640.
Both show six unlevered proxies, rebased to 100 over their common date range,
including the implemented daily GSCI history in CMDTY.
