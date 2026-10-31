# Dataset Update Source Policy

Ordinary updates start from the committed `data/processed/*.csv` files. Each updater fetches a recent source window, verifies the overlap, and calculates only the new tail or a revised overlap. Changed observations are written to CSV, Parquet, interim CSV, and build metadata. Unchanged historical rows are retained; an unchanged CPI update still refreshes its source-evidence metadata. No ordinary update reads or retrieves fixed historical raw sources. Recent JSON, CSV, or HTML source responses are kept locally under the ignored `sources/raw/incremental/` directory so the publication gate can validate current source values. A missing baseline, missing adjusted close, invalid overlap, or lack of any accepted live delivery route fails the update.

The full `build_*.py` programs remain available for deliberate historical reconstruction with `--full-rebuild`. Their historical raw caches are validated for required dates, minimum observations, order, duplicates, and gaps before reuse. Optional historical refreshes invoke those builders; they do not change the ordinary daily path.

The public repository excludes downloaded files under `sources/raw/`. A fresh checkout can update every dataset from the committed processed baseline without those raw files. A full rebuild still needs its historical sources. In particular, Yahoo's `^BCOM` endpoint returned HTTP 404 on 2026-09-26, so CMDTY cannot be rebuilt from a fresh checkout until that historical chart is supplied locally or an approved replacement source is implemented.

| Alias | Fixed historical input used only by full rebuild | Current source fetched on every update |
|---|---|---|
| USLCAP | Kenneth French/CRSP Hi 30 ZIP through 1988 | Yahoo `^GSPC` and `^SP500TR` |
| STT | Fed nominal curve and VFISX through fixed handoffs | Yahoo SHY |
| ITT | Fed nominal curve and VFITX through fixed handoffs | Yahoo IEF |
| LTT | Fed nominal curve, `^TYX`, and VUSTX through fixed handoffs | Yahoo TLT |
| GOLDPM | Published pre-GLD model; explicit LBMA refresh optional | Yahoo GLD close and adjusted close only |
| CMDTY | Pinned daily GSCI ER/TR workbook, preserved calendar, validated `^BCOM`/`^IRX` charts | Yahoo DBC |
| CPI | None; monthly BLS observations determine the latest deflator | BLS `CUSR0000SA0`; FRED `CPIAUCSL` CSV, then public data table, after transient delivery failures |
| GLSTOCK | Fixed MSCI annual anchors and Fama/French developed-market ZIP through VT inception | Yahoo VT and refreshed USLCAP dependency |
| GLBOND | Existing JST/BIS/OECD/MoF/BoE historical caches | Yahoo BND/BWX and refreshed ITT dependency |
| GLSTBOND | Existing JST/BIS/OECD/MoF/BoE historical caches | Yahoo SHY/ISHG/BWZ and refreshed STT dependency |
| USLCAP3X | `^IRX` for historical leverage model | Yahoo UPRO, refreshed USLCAP dependency |
| LTT3X | `^IRX` for historical leverage model | Yahoo TMF, refreshed LTT dependency |
| ITT3X | `^IRX` for historical leverage model | Yahoo TYD, refreshed ITT dependency |
| GOLD2X | `^IRX` and preserved spot inputs through UGL inception | Yahoo UGL, refreshed GOLDPM dependency |
| USLCAP2X | `^IRX` for historical leverage model | Yahoo SSO, refreshed USLCAP dependency |
| GLSTOCK2X | `^IRX` for historical leverage model | Yahoo WLDU, refreshed GLSTOCK dependency |
| GLBOND2X | None; every row is modeled | Yahoo `^IRX`, refreshed GLBOND dependency |
| STT2X | None; every row is modeled | Yahoo `^IRX`, refreshed STT dependency |
| ITT2X | `^IRX` for historical leverage model | Yahoo UST, refreshed ITT dependency |
| LTT2X | `^IRX` for historical leverage model | Yahoo UBT, refreshed LTT dependency |

## CPI delivery fallback

The ordinary CPI updater tries the BLS API first. Connection/time-out errors,
exhausted retries, or HTTP 429/500/502/503/504 permit a fresh FRED `CPIAUCSL`
download of the same seasonally adjusted BLS series. It uses the standard
complete-series CSV export with an identifying application User-Agent, then
filters the recent window locally. A transient CSV failure permits the public
FRED data table; that table must identify the correct series, BLS source,
monthly frequency, seasonal adjustment, and index units. A malformed source
payload or a non-transient HTTP error blocks the update.

FRED must contain the committed latest monthly anchor and at least three
matching committed monthly observations. Every observed month in the requested
historical overlap must be present and agree within `1e-9`, with no extra
observed months. Existing unpublished months, such as October 2025, retain
their established daily interpolation. New monthly observations must be
consecutive, and the latest monthly observation must be within 90 days of the
target. Daily CPI rows must reach the requested calendar date.

The actual delivery route is recorded in
`incremental_update.recent_sources` in `cpi_inflation_build.json`, together with
the series ID, URL, raw-response path and SHA-256, retrieval timestamp,
requested target, coverage, and fallback reason when applicable. The primary
dataset source remains BLS even when FRED delivers its observations. The
publication gate verifies this evidence independently; a cached file alone
cannot replace a failed live fetch. A repeat run can update this metadata
without changing the CSV or Parquet.

This fallback applies to the incremental updater. The explicit full CPI builder
continues to retrieve BLS history in 10-year chunks. See the
[CPI methodology](methodology_cpi.md) and
[operations guide](operations/daily-refresh.md).

## Deliberate historical changes

`python src/update_all_datasets.py --refresh-historical-sources` invokes the historical builders for USLCAP, STT, ITT, LTT, CMDTY, and GLSTOCK. `--refresh-static-sources` invokes the historical GLBOND and GLSTBOND builders. Neither option permits an unavailable current source to be silently replaced with an old raw file. The unattended workflow never uses either option.

CMDTY's explicit `python src/build_broad_commodities.py --migrate-gsci` path
replaces its early history with daily GSCI ER/TR while retaining the versioned
processed tail's return ratios. It does not need the missing Yahoo historical
caches or extend the end date. Its implementation and independent review
are documented in [the CMDTY methodology](methodology_cmdty.md); vendor and
derived-publication rights remain unverified.
