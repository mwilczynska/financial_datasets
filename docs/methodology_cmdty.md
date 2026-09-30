# CMDTY - Broad Commodities (DBC-like, Diversified Futures Total Return)

Dataset identifier: `broad_commodities`

Backtest alias: `CMDTY`

Status: complete model-derived public-source dataset. The 1970-1991 history is reconstructed from the **S&P GSCI Total Return** index (roll yield + T-bill collateral + production weights), replacing the earlier World Bank monthly spot model (1970-1983) and the spot-only GSCI segment (1984-1991).

## Asset Definition

`CMDTY` approximates DBC-like diversified commodity futures total return: broad commodity exposure with energy, metals, and agricultural participation, including **futures roll yield** and **T-bill collateral** income.

- `Close` / `Price Return`: normalized **excess-return** level (spot + roll, no collateral). In Segments 0-1 this is the GSCI total-return level with the daily `^IRX` collateral stripped back out; in Segment 2 it is the `^BCOM` excess-return level; in Segment 3 it is the DBC close return.
- `Adj Close` / `Total Return`: normalized **total-return** level (excess return + T-bill collateral). The backtester reads `Adj Close`. In Segments 0-1 this is the S&P GSCI Total Return; in Segment 2 it is `^BCOM` excess return + `^IRX` collateral; in Segment 3 it is DBC adjusted close.

Important: Segments 0-1 (1970-1991) are a reconstruction anchored to the S&P GSCI Total Return index. The anchor carries genuine roll yield, collateral, and GSCI production weights, but it is republished at ~bi-monthly resolution. Segment 0 (1970-1983) is therefore smoothed to daily; Segment 1 (1984-1991) overlays the anchor onto the genuine daily `^SPGSCI` spot shape.

## Output Files

| File | Path |
|---|---|
| CSV | `data/processed/broad_commodities.csv` |
| Parquet | `data/processed/broad_commodities.parquet` |
| GSCI TR anchor (static) | `sources/raw/broad_commodities_gsci_tr_macromicro.csv` |
| Manifest | `sources/manifests/broad_commodities.yml` |
| Citation notes | `sources/citations/broad_commodities.md` |
| Build script | `src/build_broad_commodities.py` |
| Update script | `src/update_broad_commodities.py` |
| Test file | `tests/validation/test_broad_commodities_contract.py` |

Coverage starts on `1970-01-02`. The 2026-09-26 update produced 14,227 rows through `2026-09-25` (segment counts: GSCI-smoothed 3,487, GSCI-shape 1,768, BCOM 3,781, DBC 5,191).

## Source Chain

| Segment | Dates | Source | `Close` (excess return) | `Adj Close` (total return) | Quality flag |
|---|---|---|---|---|---|
| 0 | 1970-01-02 - 1984-01-03 | S&P GSCI Total Return anchor (MacroMicro), `^IRX` | GSCI TR with daily `^IRX` collateral stripped out | GSCI TR anchor, log-linear daily smoothing | `model_gsci_total_return_anchor_smoothed_daily` |
| 1 | 1984-01-04 - 1991-01-02 | S&P GSCI TR anchor + Yahoo `^SPGSCI` spot, `^IRX` | Total return minus daily `^IRX` collateral | `^SPGSCI` daily spot shape overlaid per anchor interval to the GSCI TR | `model_gsci_total_return_anchor_with_spgsci_spot_daily_shape` |
| 2 | 1991-01-03 - 2006-02-06 | Yahoo `^BCOM` excess return + Yahoo `^IRX` | Compounds `^BCOM` close returns | `^BCOM` close returns x (1 + IRX%/100/365) | `model_bcom_excess_return_plus_tbill_collateral` |
| 3 | 2006-02-07 - present | Yahoo `DBC` adjusted close | Compounds DBC close returns | Compounds DBC adjusted-close returns | `observed_yahoo_dbc_dblci_total_return_etf` |

## S&P GSCI Total Return Anchor

The 1970-1991 reconstruction is anchored to the **S&P GSCI Total Return Index**, obtained from MacroMicro's free republication (`https://en.macromicro.me/series/2692/sp-gsci-index`). The free tier serves the full 1970-present range normalized to 100 at 1970-01-02 but **downsampled to ~358 points (~57-day spacing)**; full daily history is paywalled. The series is retained in the local source cache `sources/raw/broad_commodities_gsci_tr_macromicro.csv` and does not change (it is historical). The raw cache is not part of the public release by default; only the DBC tail refreshes from Yahoo on update.

Initial provenance check: the anchor's growth was compared with repo data. Those comparisons were interpreted as consistent with roll-inclusive, collateralized total return, but growth ratios alone do not establish series identity. The [2026-09-30 research](research/cmdty_daily_reconstruction.md) obtained an independent daily TR export for 1979-1991 and checked its identity against published SEC levels and annual returns. It also found level drift relative to current CMDTY. The original sparse anchor cache is absent from this checkout, so its identity, timestamps, and values still require direct verification.

### Segment 0 - GSCI TR anchor, smoothed (1970-1983)

The initial build did not obtain a daily broad-commodity index before 1984, so Segment 0 log-linearly interpolates the GSCI TR anchor onto the `^IRX` trading calendar. Subsequent research acquired daily individual futures contracts reaching 1959 and a daily GSCI TR export starting 1979-12-27; these have not yet replaced production Segment 0:

```text
Adj Close[t] = exp( interp_log_anchor(date[t]) )      # tracks the GSCI TR anchor
Total Return[t] = Adj Close[t] / Adj Close[t-1] - 1
Price Return[t] = (1 + Total Return[t]) / (1 + IRX%/100/365) - 1   # strip collateral -> excess return
```

The level carries genuine roll yield, collateral, and GSCI composition, but **within-period daily volatility is smoothed (model-derived)**. This is the deliberate "honest-smoothed" choice: rather than fabricate daily volatility from an unrepresentative metals-only proxy, the daily path is a constant-geometric interpolation between anchor points.

### Segment 1 - GSCI TR anchor with `^SPGSCI` daily spot shape (1984-1991)

From 1984 the daily `^SPGSCI` spot index is available. Segment 1 keeps that genuine daily shape but rescales it so each anchor interval compounds to the GSCI TR. For each anchor interval, with daily spot log-returns `g_d` and target log-return `ln(L_{i+1}/L_i)`:

```text
overlay   = ( ln(L_{i+1}/L_i) - sum(g_d) ) / N        # constant per-day overlay
Total Return[d] = exp(g_d + overlay) - 1
Price Return[d] = (1 + Total Return[d]) / (1 + IRX%/100/365) - 1
```

This injects the roll yield and collateral the spot index omits (~9%/yr roll + ~7%/yr collateral) while preserving real daily moves and event timing. The reconstructed segment carries ~16%/yr annualized daily volatility (vs ~0 under the previous smoothing). This is the same per-period multiplicative-overlay de-smoothing pattern used by `GLSTOCK`/`GLBOND`.

## Splice Logic

Levels (`Close`, `Adj Close`) compound continuously from 100 without resetting at boundaries.

- Segments 0-1 are self-contained (the anchor/overlay yields each day's return directly); the level simply continues compounding across the 1984 boundary.
- The 1991 (GSCI shape -> BCOM) and 2006 (BCOM -> DBC) boundaries use the existing overlap-anchor pattern: the incoming source has a value on the prior date, and the first return in the new segment is its own ratio.

## Collateral Rate Model

`^IRX` is the 13-week T-bill annualized rate in percent; missing dates are forward-filled. One-day collateral growth is `1 + IRX%/100/365` (actual/365). Segments 0-1 derive `Close` by stripping this collateral out of the total-return path; Segment 2 adds it to the `^BCOM` excess return; Segment 3 relies on DBC's adjusted close, which already reflects distributions.

## Production Sources

- **S&P GSCI Total Return anchor (MacroMicro)**: treated as a republished S&P GSCI Total Return Index, base 100 at 1970-01-02, ~bi-monthly. Static raw cache, not included in this checkout. Used as the roll/collateral/production-weighted level target for the 1970-1991 reconstruction; independent identity verification of that cache remains outstanding.
- **Yahoo `^SPGSCI`**: S&P GSCI Spot Index, from `1984-01-03`. Used only for the daily spot **shape** in Segment 1.
- **Yahoo `^BCOM`**: Bloomberg Commodity Index (excess return), from `1991-01-02`.
- **Yahoo `DBC`**: Invesco DB Commodity Index Tracking Fund, from `2006-02-06`; Yahoo adjusted close for total return.
- **Yahoo `^IRX`**: 13-week T-bill annualized rate, collateral model for Segments 0-2.

## Validation Sources

- GSCI TR anchor: `Adj Close` at anchor sample dates (1970-1991) must stay within 5% of the GSCI TR anchor (base 100), confirming the reconstruction tracks the index.
- De-smoothing check: Segment 1 annualized daily total-return volatility must exceed 8% (confirms the spot shape is restored, not smoothed).
- Raw `^BCOM` Yahoo chart payload: BCOM segment `Price Return` matches raw close returns.
- Raw DBC Yahoo chart payload: DBC segment `Price Return` and `Total Return` match raw close and adjusted-close returns.
- Collateral relationship: `Adj Close >= Close` throughout; within Segment 1, `Adj Close / Close` grows by more than 1.3x over the high-rate era.

## Rejected or Limited Sources

- Initial searches did not locate adequate free daily history before 1984. The 2026-09-30 research supersedes that assessment: TurtleTrader provides individual delivery histories reaching 1959, although the important early cattle constituent is still missing from the acquired archive panel.
- A full daily GSCI TR extract for 1970-1991 has not been acquired. Automated Investing.com access failed, but the user obtained daily TR for 1979-1991 manually. This export supports a direct daily upgrade for that period after validation; the production build still uses MacroMicro's downsampled anchor.
- AQR "Commodities for the Long Run" (monthly, roll-inclusive, back to 1877) is freely downloadable but equal-weighted, so it was not chosen as the energy-tilted DBC-like anchor.
- Licensed daily S&P GSCI / Bloomberg BCOM total-return history, or a constituent-level futures reconstruction, remain the preferred quality upgrades.

## Build Method

1. Validate and reuse the historical Yahoo `^SPGSCI`, `^BCOM`, and `^IRX` charts under `sources/raw/`; fetch any missing or invalid chart. Fetch current `DBC` history from Yahoo and store its JSON under `sources/raw/`.
2. Load the static S&P GSCI Total Return anchor from `sources/raw/broad_commodities_gsci_tr_macromicro.csv`.
3. Determine source boundaries (Segment 0: `^IRX` dates 1970-01-02 .. 1984-01-03; Segment 1: `^SPGSCI` 1984-01-04 .. 1991-01-02; Segment 2: `^BCOM` 1991-01-03 .. 2006-02-06; Segment 3: DBC 2006-02-07 onward).
4. Build Segment 0 returns by log-linear anchor interpolation; build Segment 1 returns by per-anchor-interval overlay of the `^SPGSCI` spot shape; keep Segments 2-3 as raw-ratio + collateral / observed ETF.
5. Compound normalized `Close` (excess return) and `Adj Close` (total return) from 100 without resetting at boundaries.
6. Write the processed CSV and Parquet outputs and build metadata JSON. Any interim copy is a local build artifact and is not published.

## Update Method

The ordinary update starts from the committed processed CSV, fetches a 14-calendar-day Yahoo overlap, preserves unchanged historical rows, and compounds only revised or new observations. It rewrites CSV, Parquet, interim CSV, and build metadata together. A full historical reconstruction remains available with `--full-rebuild`; it requires the documented historical sources. The live input is Yahoo DBC. The GSCI/`^SPGSCI`/`^BCOM`/`^IRX` historical segments remain unchanged; `^BCOM` returned HTTP 404 on 2026-09-26, so a clean full rebuild still needs a permitted historical cache or a reviewed source decision.

## Tests

See `tests/validation/test_broad_commodities_contract.py`. Key assertions:

| Test | Assertion |
|---|---|
| Scaffold paths exist | Manifest YAML, citation MD, and the static GSCI TR anchor CSV exist |
| Processed outputs exist | CSV and Parquet exist and are non-empty |
| Yahoo-compatible schema | Yahoo-style columns come first |
| Coverage starts at 1970 | First date is `1970-01-02`; dates are unique and sorted |
| Levels positive and returns recompute | `Close` and `Adj Close` positive; return columns match level arithmetic |
| Total return is collateralized excess return | `Adj Close >= Close` everywhere |
| DBC raw-source match | DBC close and adjusted-close returns match raw Yahoo returns |
| BCOM raw-source match | BCOM close returns match raw Yahoo returns |
| GSCI anchor segment present and growing | Segment 0 starts 1970-01-02, is flagged GSCI/total-return/roll/smoothed, and Adj Close grows >1.5x |
| Adj Close tracks GSCI anchor | Adj Close stays within 5% of the GSCI TR anchor through 1970-1991 |
| Segment 1 de-smoothed | Segment 1 annualized volatility > 8%; internal collateral ratio grows |
| Quality flag counts | All rows assigned to exactly one expected source flag |
| Historical cache handling | Valid BCOM cache avoids the live endpoint; a failed forced refresh preserves it; incomplete cache fails clearly |

## Current Gaps And Limitations

`CMDTY` is a public-source long-horizon commodity proxy, not a single observed investable index from 1970 to present.

### Segments 0-1: 1970-1991 - GSCI Total Return reconstruction

1. **Anchor is downsampled and republished**: the GSCI TR anchor is MacroMicro's free ~bi-monthly republication of the S&P GSCI Total Return Index, not a licensed daily S&P feed. The level tracks the index to within a few percent at sample dates; intervening daily levels are interpolated (Segment 0) or overlaid (Segment 1).
2. **Segment 0 daily volatility is smoothed**: the production build still uses sparse anchors, so within-period volatility, drawdowns, and event timing in 1970-1983 are model-derived (constant-geometric interpolation). Suitable daily source leads and a 1979-onward daily TR export are now documented but not integrated. Month/interval-end levels are anchored; daily paths are not observed in this segment.
3. **Segment 1 shape is spot, level is total return**: the daily shape comes from `^SPGSCI` spot, rescaled to the GSCI TR per anchor interval. Daily moves are genuine spot moves; the roll/collateral that lifts them to total return is added as a smooth per-interval overlay, not a daily-observed roll.
4. **GSCI is not DBC**: the S&P GSCI is production-weighted and becomes energy-heavy in later decades. Its earliest basket is dominated by livestock and agriculture; energy is absent initially. Its weights and roll rules differ from DBC/DBLCI.
5. **Back-calculated history**: the S&P GSCI launched in 1991; pre-1991 values are S&P's own back-tested reconstruction.
6. **License**: the GSCI TR levels derive from S&P data via a third-party republication. Review licensing before redistributing derived data outside this project.

### Segment 2: 1991-2006 - BCOM Excess Return Plus T-Bill Model

1. **Different benchmark family**: Bloomberg Commodity Index methodology differs from GSCI and DBC in constituents, weights, caps, and roll rules. The 1991 splice is an economic benchmark change.
2. **Index-type verification is indirect**: `^BCOM` is treated as excess return from annual-return behavior; the raw Yahoo payload carries no official Bloomberg metadata.
3. **Collateral model approximates total return**: `^IRX` collateral is added to BCOM ER; the exact official collateral convention is not independently verified.

### Segment 3: 2006-present - DBC ETF Observed Returns

1. **ETF net return, not gross index return**: DBC includes ~0.89%/yr expenses, trading costs, and tracking differences.
2. **Yahoo adjusted-close dependency**: `Adj Close` relies on Yahoo's distribution adjustment.
3. **Optimum-yield roll** differs from BCOM and GSCI roll methodologies.

### Chain-Level Gaps

1. **Two major methodology breaks remain**: 1991 (GSCI Total Return to BCOM ER) and 2006 (BCOM ER to DBC ETF). Normalized levels are continuous; exposures are not methodologically continuous. (The 1984 boundary is now internal to the GSCI reconstruction.)
2. **No single roll methodology**: GSCI roll (Segments 0-1, smoothed/overlaid), BCOM roll (Segment 2), DBC optimum-yield roll (Segment 3).
3. **No OHLCV for reconstructed/model rows**: `Open`, `High`, `Low`, `Volume` are blank for index/model segments.
4. **Backtest interpretation**: report results by `Quality Flag`; do not treat 1970-present CMDTY as one homogeneous observed series.

## Known Caveats Summary

1. Segments 0-1 (1970-1991) are anchored to the S&P GSCI Total Return (roll + collateral + GSCI weights), but the anchor is a downsampled republication; Segment 0 daily volatility is smoothed and Segment 1's daily shape is spot.
2. The S&P GSCI has different exposures from DBC, becomes energy-heavy in later decades, and is back-tested before 1991.
3. GSCI, BCOM, and DBC use different commodity universes and weighting/roll methodologies; the 1991 and 2006 splices are methodology breaks.
4. Segment 3 is ETF net return, not gross index return.
5. Official licensed daily total-return validation is unavailable for the pre-DBC history.

## Future Upgrade

Replace the sparse GSCI TR anchor with verified **daily** S&P GSCI Total Return history, starting with the acquired 1979-1991 export. For the unresolved 1970s, obtain full daily index history or build a constituent-level futures reconstruction with documented contracts, rolls, weights, and collateral. Phase each constituent in at its historical index admission, which may be later than its futures launch.

The [2026-09-30 daily-data research](research/cmdty_daily_reconstruction.md)
identifies freely downloadable individual daily futures histories reaching
1959, vendor leads for missing early cattle and LME reference prices, a
user-acquired daily TR export starting 1979-12-27, and a reproducible overlap
experiment reviewed by Astra Max. Useful pre-1984 daily commodity data exists,
although a complete validated 1970s GSCI basket has not yet been assembled. The research
also documents collateral-calendar and anchor-boundary issues to address in
an upgrade. The production construction described on this page remains the
current published method.
