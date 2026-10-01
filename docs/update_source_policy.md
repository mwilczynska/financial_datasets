# Dataset Update Source Policy

Ordinary updates start from the committed `data/processed/*.csv` files. Each updater fetches a recent source window, verifies the overlap, calculates only the new tail or a revised overlap, and rewrites its CSV, Parquet, interim CSV, and build metadata together. No ordinary update reads or retrieves fixed historical raw sources. Recent API responses are kept locally under the ignored `sources/raw/incremental/` directory so the publication gate can validate current source values. A missing baseline, missing adjusted close, invalid overlap, or unavailable current source fails the update.

The full `build_*.py` programs remain available for deliberate historical reconstruction with `--full-rebuild`. Their historical raw caches are validated for required dates, minimum observations, order, duplicates, and gaps before reuse. Optional historical refreshes invoke those builders; they do not change the ordinary daily path.

The public repository excludes downloaded files under `sources/raw/`. A fresh checkout can update every dataset from the committed processed baseline without those raw files. A full rebuild still needs its historical sources. In particular, Yahoo's `^BCOM` endpoint returned HTTP 404 on 2026-09-26, so CMDTY cannot be rebuilt from a fresh checkout until that historical chart is supplied locally or an approved replacement source is implemented.

| Alias | Fixed historical input used only by full rebuild | Current source fetched on every update |
|---|---|---|
| USLCAP | Kenneth French/CRSP Hi 30 ZIP through 1988 | Yahoo `^GSPC` and `^SP500TR` |
| STT | Fed nominal curve and VFISX through fixed handoffs | Yahoo SHY |
| ITT | Fed nominal curve and VFITX through fixed handoffs | Yahoo IEF |
| LTT | Fed nominal curve, `^TYX`, and VUSTX through fixed handoffs | Yahoo TLT |
| GOLDPM | Published pre-GLD model; explicit LBMA refresh optional | Yahoo GLD close and adjusted close only |
| CMDTY | GSCI TR anchor and validated `^SPGSCI`, `^BCOM`, `^IRX` charts | Yahoo DBC |
| CPI | None; monthly BLS observations determine the latest deflator | BLS `CUSR0000SA0` |
| GLSTOCK | Fixed MSCI annual anchors and Fama/French developed-market ZIP through VT inception | Yahoo VT and refreshed USLCAP dependency |
| GLBOND | Existing JST/BIS/OECD/MoF/BoE historical caches | Yahoo BND/BWX and refreshed ITT dependency |
| GLSTBOND | Existing JST/BIS/OECD/MoF/BoE historical caches | Yahoo SHY/ISHG/BWZ and refreshed STT dependency |
| USLCAP3X | `^IRX` for historical leverage model | Yahoo UPRO, refreshed USLCAP dependency |
| LTT3X | `^IRX` for historical leverage model | Yahoo TMF, refreshed LTT dependency |
| ITT3X | `^IRX` for historical leverage model | Yahoo TYD, refreshed ITT dependency |
| GOLD2X | `^IRX` and preserved spot inputs through UGL inception | Yahoo UGL, refreshed GOLDPM dependency |

`python src/update_all_datasets.py --refresh-historical-sources` invokes the historical builders for USLCAP, STT, ITT, LTT, CMDTY, and GLSTOCK. `--refresh-static-sources` invokes the historical GLBOND and GLSTBOND builders. Neither option permits an unavailable current source to be silently replaced with an old raw file. The unattended workflow never uses either option.
