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
- runs `$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'; python -m pytest -q tests\validation` after successful updates.

Useful options:

```text
python src\update_all_datasets.py --list-datasets
python src\update_all_datasets.py --dry-run --no-tests
python src\update_all_datasets.py --end-date 2026-06-30
python src\update_all_datasets.py --only USLCAP GOLDPM GOLD2X
python src\update_all_datasets.py --skip GLBOND --continue-on-error
python src\update_all_datasets.py --refresh-static-sources
```

Notes:

- "Current" means current to the latest observation available from each source, not necessarily a row dated today. Weekend runs, market holidays, delayed monthly CPI releases, and static historical anchors may legitimately end before the requested `--end-date`.
- The script delegates to the existing per-dataset update scripts rather than duplicating source logic.
- `--only` and `--skip` accept aliases, asset ids, output stems, or update script stems. Derived datasets require their base dependency to be selected unless `--allow-stale-dependencies` is used.
- `GLBOND` and `GLSTBOND` reuse cached historical JST/BIS/OECD/MoF/BoE raw files by default. Their daily refresh only needs the live ETF tail. Use `--refresh-static-sources` when you intentionally want to refetch those heavy historical inputs.
