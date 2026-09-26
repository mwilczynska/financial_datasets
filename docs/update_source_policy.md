# Dataset Update Source Policy

Ordinary updates reuse a raw source only when that source is used for a fixed historical segment. A reusable cache is checked for its required dates, minimum observations, order, duplicates, and gaps before it is accepted. Yahoo chart caches are also checked for symbol and positive finite levels. A missing or invalid cache is refetched; if that retrieval fails, the dataset update fails. An optional historical refresh preserves a valid cache if the remote source is unavailable. Build metadata for the newly covered datasets records historical file SHA-256 and whether the file was cached or fetched.

The public repository excludes downloaded files under `sources/raw/`. A fresh checkout must retrieve each required historical source or receive a permitted local cache before it can rebuild every dataset. In particular, Yahoo's `^BCOM` endpoint returned HTTP 404 on 2026-09-26, so CMDTY cannot be rebuilt from a fresh checkout until that historical chart is supplied locally or an approved replacement source is implemented. The published processed dataset remains available for backtests.

| Alias | Fixed historical input reused on ordinary updates | Current source fetched on every update |
|---|---|---|
| USLCAP | Kenneth French/CRSP Hi 30 ZIP through 1988 | Yahoo `^GSPC` and `^SP500TR` |
| STT | Fed nominal curve and VFISX through fixed handoffs | Yahoo SHY |
| ITT | Fed nominal curve and VFITX through fixed handoffs | Yahoo IEF |
| LTT | Fed nominal curve, `^TYX`, and VUSTX through fixed handoffs | Yahoo TLT |
| GOLDPM | None; LBMA spot is also used for current `Close` | LBMA Gold PM and Yahoo GLD |
| CMDTY | GSCI TR anchor and validated `^SPGSCI`, `^BCOM`, `^IRX` charts | Yahoo DBC |
| CPI | None; monthly BLS observations determine the latest deflator | BLS `CUSR0000SA0` |
| GLSTOCK | Fixed MSCI annual anchors and Fama/French developed-market ZIP through VT inception | Yahoo VT and refreshed USLCAP dependency |
| GLBOND | Existing JST/BIS/OECD/MoF/BoE historical caches | Yahoo BND/BWX and refreshed ITT dependency |
| GLSTBOND | Existing JST/BIS/OECD/MoF/BoE historical caches | Yahoo SHY/ISHG/BWZ and refreshed STT dependency |
| USLCAP3X | None; `^IRX` also feeds current overlap calibration | Yahoo `^IRX` and UPRO, refreshed USLCAP dependency |
| LTT3X | None; `^IRX` also feeds current overlap calibration | Yahoo `^IRX` and TMF, refreshed LTT dependency |
| ITT3X | None; `^IRX` also feeds current overlap calibration | Yahoo `^IRX` and TYD, refreshed ITT dependency |
| GOLD2X | None; `^IRX` also feeds current overlap calibration | Yahoo `^IRX` and UGL, refreshed GOLDPM dependency |

`python src/update_all_datasets.py --refresh-historical-sources` requests a refresh for USLCAP, STT, ITT, LTT, CMDTY, and GLSTOCK. `--refresh-static-sources` continues to refresh the separate heavy historical inputs for GLBOND and GLSTBOND. Neither option permits an unavailable current source to be silently replaced with an old raw file.
