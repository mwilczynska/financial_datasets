# Agent Instructions

> **Editing this file:** Always edit `AGENTS.md`. `CLAUDE.md` is a hard link to `AGENTS.md` and will reflect any changes automatically. Never edit `CLAUDE.md` directly.

## Project Goal

Build long-horizon daily asset-class datasets for Python portfolio backtesting. Prioritize correctness, source provenance, and compatibility with scripts that previously used Yahoo Finance or `yfinance` data.

## Ground Rules

- Preserve Yahoo-compatible output columns where possible: `Date`, `Open`, `High`, `Low`, `Close`, `Adj Close`, `Volume`.
- Add project-specific columns only after the Yahoo-style fields.
- Target `1970-01-01` as the minimum start date for core datasets; go earlier only when source quality and methodology support it.
- Keep price-return and total-return data separate in methodology and tests.
- Clearly flag reconstructed, estimated, incomplete, or source-spliced data.
- Do not present reconstructed total return as raw observed index data.
- Record source URLs, retrieval dates, transformations, and validation decisions in `LOG.md` and the relevant source files.
- When adding or changing datasets, update `docs/source_registry.md`, `docs/validation.md`, and any related manifest under `sources/manifests/`.
- Each dataset should include an update path that refetches a recent overlap window from a Yahoo-compatible API source, stitches by `Date`, recomputes returns, and rewrites CSV/Parquet outputs together.
- Use `python src/update_all_datasets.py` to refresh every processed dataset in dependency order. It delegates to each dataset's update script, requests data through the chosen `--end-date`, rewrites CSV/Parquet/metadata through the underlying scripts, and runs `tests/validation` by default after successful updates.
- "Current" means current to the latest observation exposed by each source. On weekends, market holidays, delayed monthly sources, or static historical anchors, the last row may be earlier than the script's requested `--end-date`.
- `GLBOND` and `GLSTBOND` reuse cached historical JST/BIS/OECD/MoF/BoE raw files during ordinary daily updates. Use `--refresh-static-sources` only when those heavy historical inputs need to be refetched.

## File Expectations

- `PLAN.md` describes project direction and the canonical dataset contract.
- `LOG.md` is chronological and should explain what changed and why.
- `docs/methodology.md` describes general transformation and return methodology.
- `docs/dataset_methodologies.md` is the index of per-dataset methodology files.
- `docs/methodology_<alias>.md` is the per-dataset methodology file (e.g., `methodology_uslcap.md`).
- `docs/source_registry.md` lists approved, candidate, and rejected sources.
- `docs/validation.md` defines tests and acceptance criteria.
- `sources/citations/` stores human-readable source notes.
- `sources/manifests/` stores machine-readable source metadata.
- `data/processed/` stores final CSV and Parquet outputs.
- `tests/validation/` stores dataset validation tests.
- `src/update_*.py` scripts perform incremental dataset updates.

## Testing Expectations

- Add or update validation tests with every dataset-producing change.
- Tests should verify schema, date coverage, return arithmetic, missing values, duplicate dates, and independent-source agreement.
- If source data is unavailable locally, tests may skip with a clear reason rather than silently passing.
- After a bulk refresh, either let `src/update_all_datasets.py` run its default validation step or run `$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'; python -m pytest -q tests/validation` manually.

## Documentation Discipline

Every data decision should answer:

- What source was used?
- Why was it chosen?
- What are its licensing or redistribution limits?
- What transformations were applied?
- How was the output checked against an independent source?

---

## Adding a New Dataset — Step-by-Step

Follow this sequence for every new dataset. Do not skip steps or reorder them.

### Step 1 — Define the asset contract

Before writing any code, write down in plain language:

- What real-world asset or exposure does this dataset represent?
- What does `Close` mean for this asset (price index, spot fixing, fund NAV, model level)?
- What does `Adj Close` mean (total return with income reinvested, or equal to `Close` if no income stream)?
- What is the backtest alias (e.g., `ITT`, `STT`, `GOLDPM`)?
- What is the dataset identifier (snake_case filename stem, e.g., `short_term_us_treasury`)?
- What is the minimum required coverage date? Aim for `1970-01-01`.

Do not proceed until these are written down. Ambiguity here propagates into every downstream decision.

### Step 2 — Search for and classify sources

Search broadly. Do not assume the most obvious ETF or ticker is the right primary source.

For each candidate source, record:
- URL or API endpoint.
- Coverage dates.
- Whether it is a price index, total-return index, spot price, fund NAV, futures, or model output.
- Licensing and redistribution constraints.
- Whether it provides daily data or only monthly/annual.

Classify every source as one of: `active` (will be used), `validation` (cross-check only), `candidate` (needs more review), `rejected` (unsuitable), or `blocked` (inaccessible in this environment).

Record all sources in `docs/source_registry.md` under the new dataset heading and in `sources/manifests/<asset_id>.yml`.

Rules:
- Prefer official or primary-market sources over aggregators.
- Daily observed data is always preferred over model-derived data.
- Monthly data must never be interpolated to daily and presented as observed daily data.
- If the ideal source requires a licence (e.g., CRSP/WRDS), document it as a candidate upgrade and implement with the best available public-source alternative, clearly labelled as provisional or model-derived.

### Step 3 — Design the source chain

Most datasets require chaining sources to reach `1970-01-01`. A typical chain is:

1. **Fed yield curve model segment** (1970 to earliest public fund) — use `feds200628.csv`, evaluate the Svensson zero curve at a representative maturity, price a synthetic par bond, and include daily coupon carry in `Adj Close`/`Total Return`. Choose the maturity to match the target exposure midpoint (e.g., 8.5 yr for ITT, 25 yr for LTT).
2. **Early public fund segment** (earliest available public fund until the target ETF starts) — use Yahoo adjusted-close returns; pick the longest-history fund that matches the target exposure.
3. **Target ETF segment** (from ETF inception onward) — use Yahoo adjusted-close returns for the target ETF.

At each source handoff:
- The first row of the incoming source provides the base for computing the first return; the return is computed against the overlap row from the outgoing source.
- Levels (`Close`, `Adj Close`) are normalized to 100 at the first row and compounded continuously; they are never reset or rescaled at a boundary.
- Assign a distinct `Quality Flag` to every segment so source boundaries are machine-detectable.

### Step 4 — Implement the build script

Create `src/build_<asset_id>.py`. Model it on an existing build script (e.g., `build_intermediate_term_us_treasury.py`). The script must:

- Accept `--end-date` and `--root` arguments.
- Fetch all raw sources and write them to `sources/raw/` before processing.
- Build the normalized row list in memory.
- Write CSV to both `data/interim/<asset_id>.csv` and `data/processed/<asset_id>.csv`.
- Write Parquet to `data/processed/<asset_id>.parquet` (via `write_parquet_if_available`).
- Write build metadata JSON to `sources/manifests/<asset_id>_build.json`.
- Print a summary: row count, first date, last date, Parquet status.

**Critical:** The Fed model segment must produce cumulative compounding `Close` and `Adj Close` levels before splicing, not single-day relative levels. There is a regression test for this; ensure the new dataset passes an equivalent check.

### Step 5 — Implement the update script

Create `src/update_<asset_id>.py`. For datasets whose full source chain must be rebuilt from scratch (Treasury datasets using the Fed yield curve), the update script simply calls `main()` from the build script. For datasets that can be incrementally stitched (e.g., `USLCAP`, `GOLDPM`), the update script must:

1. Read the existing processed CSV.
2. Refetch a configurable overlap window (default ~10 trading days) from the live source.
3. Replace overlapping rows, sort by `Date`, de-duplicate.
4. Recompute all return columns across the stitched dataset.
5. Rewrite CSV and Parquet together.
6. Write updated build metadata.

### Step 6 — Run the build and inspect outputs

```
python src/build_<asset_id>.py
```

After building, inspect the output before writing tests:

- Check row count and date range. Does coverage start on or immediately after `1970-01-01`?
- Check segment breakdown: confirm that each source segment (Fed model, fund proxy, target ETF) covers the expected date ranges.
- Confirm `Adj Close` grows substantially in the Fed model segment (not flat around 100). For a high-coupon-era model (1970s–80s), the level should roughly double or more by the time the fund segment starts.
- Spot-check returns at and around each source boundary for discontinuities.

### Step 7 — Write validation tests

Create `tests/validation/test_<asset_id>_contract.py`. Every test file must include:

| Test | What it checks |
|---|---|
| Scaffold paths exist | Manifest and citation file are present |
| Processed outputs exist | CSV and Parquet exist and are non-empty |
| Yahoo-compatible schema | First columns are the Yahoo-style columns; project columns follow |
| Coverage starts at 1970 | First date is `1970-01-02` (or documented alternative); dates are unique and sorted |
| Levels positive, returns recompute | `Close` and `Adj Close` > 0 throughout; `Price Return` and `Total Return` arithmetic matches levels within tolerance |
| Segment returns match raw source | For each Yahoo fund segment, daily `Total Return` exactly matches the raw Yahoo adjusted-close returns (tolerance `1e-10`); assert a minimum row count per segment |
| Fed model segment present and growing | Fed segment starts on `1970-01-02`, ends before fund start, has more than N rows, and `Adj Close` at the end is at least 1.5× the starting value |

Run all existing tests after adding the new file to ensure nothing is broken:

```
python -m pytest -q tests/validation
```

All tests must pass before proceeding.

### Step 8 — Write documentation

Create or update the following files. Do not skip any of them.

| File | Action |
|---|---|
| `docs/methodology_<alias_lower>.md` | Create. Use the template in `docs/dataset_methodologies.md`. Include the source chain table, build method steps, update method, test coverage summary, and caveats. |
| `docs/dataset_methodologies.md` | Add a row to the index table. |
| `docs/source_registry.md` | Add a section for the new dataset with all classified sources. |
| `docs/validation.md` | Add a bullet to the independent-source tests section describing the new dataset's validation requirements. |
| `sources/manifests/<asset_id>.yml` | Create. Record asset metadata, milestones, sources, and validation requirements. |
| `sources/citations/<asset_id>.md` | Create. Human-readable notes for each source: URL, access date, finding, and caveats. |
| `PLAN.md` | Add a milestones table for the new dataset with statuses. Mark the dataset status at the top of its section. |
| `LOG.md` | Add a dated entry describing what was built and why each decision was made. |
| `HANDOVER.md` | Add the new dataset to the Current Datasets section with alias, file path, definition, segments, and status. Update the To-Do list. |

### Step 9 — Commit

Stage all new and modified files explicitly (do not use `git add -A` without reviewing what would be staged). Commit with a message that names the dataset, summarises the source chain, and notes the row count and date range.

```
git add <all new and changed files>
git commit -m "Add <ALIAS> dataset (<description of source chain>)"
git push
```
