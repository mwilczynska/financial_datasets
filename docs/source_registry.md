# Source Registry

## Status Levels

- `approved`: usable for dataset production after licensing and retrieval details are recorded.
- `validation`: usable as an independent cross-check, but not necessarily as the production source.
- `candidate`: requires more review before use.
- `rejected`: reviewed and unsuitable for this project.

## U.S. Large-Cap Equities / S&P 500 Equivalent

### S&P Dow Jones Indices

- Status: `candidate`
- URL: https://www.spglobal.com/spdji/en/indices/equity/sp-500/
- Role: authoritative index owner and methodology source.
- Current finding: S&P DJI describes the S&P 500 as a leading large-cap U.S. equity gauge covering approximately 80% of available market capitalization.
- Caveat: licensing and redistribution terms must be reviewed before storing or publishing index history.

### FRED SP500

- Status: `validation`
- URL: https://fred.stlouisfed.org/series/SP500
- Role: recent official daily close-level validation source.
- Current finding: daily close index values sourced from S&P Dow Jones Indices.
- Caveats:
  - Price index only; it does not include dividends.
  - FRED currently exposes 10 years of daily history for S&P and Dow Jones series.
  - Copyright and reproduction restrictions apply.

### Yahoo Finance / yfinance

- Status: `candidate`; Yahoo Finance chart API is `active` for U.S. large-cap price-index and post-1988 total-return data.
- URL: https://pypi.org/project/yfinance/
- Chart endpoint: https://query1.finance.yahoo.com/v8/finance/chart/%5EGSPC
- Total-return chart endpoint: https://query1.finance.yahoo.com/v8/finance/chart/%5ESP500TR
- Role: output compatibility reference and possible source for recent ETF/index-style series.
- Current finding: yfinance provides a Pythonic way to fetch Yahoo Finance-style market data.
- Caveats:
  - yfinance states it is not affiliated with, endorsed by, or vetted by Yahoo.
  - Yahoo terms of use must be reviewed before storing downloaded data.
  - Many ETF or fund tickers do not meet the `1970-01-01` coverage requirement.
  - For `^GSPC`, Yahoo `Adj Close` should not be treated as a dividend-reinvested total-return series.
  - Yahoo `^SP500TR` daily data starts in 1988, so it cannot by itself satisfy the 1970 total-return coverage requirement.

### Kenneth French Data Library / CRSP Size Portfolios

- Status: `active`
- URL: https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/Portfolios_Formed_on_ME_daily_CSV.zip
- Role: daily U.S. large-cap/blend total-return source before Yahoo `^SP500TR` can supply daily returns.
- Current finding: the daily file is created from the CRSP database and contains value-weighted returns for size portfolios. `Hi 30` is used as the U.S. large-cap total-return proxy.
- Caveats:
  - This is a U.S. large-cap/blend proxy, not the official S&P 500 total-return index.
  - The source provides daily returns, not OHLCV price levels.
  - Use only as documented; do not describe pre-1988 `Adj Close` as official S&P 500 total return.

### Portfolio Visualizer Asset-Class Data Sources

- Status: `candidate_reference`
- URL: https://www.portfoliovisualizer.com/faq#marketData
- Role: reference for future asset-class source selection and terminology.
- Current finding: user identified this FAQ as a useful source list for asset-class returns.
- Caveats:
  - Treat as a methodology/source-reference page unless export rights and direct downloadable data access are confirmed.
  - Do not use Portfolio Visualizer as a raw dataset source without reviewing its terms and reproducibility.

### Bogleheads Simba's Backtesting Spreadsheet

- Status: `candidate_reference_unverified`
- URL: https://www.bogleheads.org/wiki/Simba%27s_backtesting_spreadsheet
- Role: possible reference list for future asset-class return data sources.
- Current finding: user identified this page as a potentially useful source reference.
- Caveats:
  - Direct fetch returned `403 Forbidden` during this session, so source details were not verified.
  - Likely annual-return oriented; do not use as a daily raw data source unless a linked daily source is separately verified.
  - Treat as a pointer to references, not as a canonical dataset.

### S&P 500 Annual Return Reference Table

- Status: `validation`
- URL: https://en.wikipedia.org/wiki/S%26P_500
- Role: independent annual sanity check for pre-1988 USLCAP adjusted returns.
- Current finding: includes annual S&P 500 total return including dividends.
- Caveats:
  - Secondary reference, not raw official data.
  - Annual frequency only; cannot validate individual daily rows.
  - Differences are expected because pre-1988 USLCAP is a CRSP large-cap/blend proxy.

### Robert Shiller Data

- Status: `rejected_for_daily_total_return_requirement`
- URL: https://www.econ.yale.edu/~shiller/data.htm
- Role: possible long-run monthly equity market data source for reconstruction and cross-checking.
- Current finding: direct access failed during initial research with `502 Bad Gateway`.
- Caveats:
  - Must be directly retrieved and documented before use.
  - Monthly data cannot be treated as raw daily data.
  - Not suitable for the current USLCAP adjusted-series requirement because the user explicitly required daily data and no estimates.

## Future Asset Classes

To be added after U.S. large-cap equities:

- U.S. nominal bonds.
- U.S. TIPS.
- Broad commodities.
- Cash or Treasury bills.
- Inflation/CPI series for real-return calculations. Initial CPI-U deflator is now implemented as
  `CPI`; future work may add alternative inflation measures.

## Short-Term U.S. Treasury / SHY-like 1-3 Year Government Bonds

### iShares SHY

- Status: `target_definition_and_validation`
- URL: https://www.ishares.com/us/products/239452/ishares-13-year-treasury-bond-etf
- Role: defines the target exposure and provides post-2002 public ETF return data.
- Current finding: iShares describes SHY as tracking an index of U.S. Treasury bonds with remaining maturities between 1 and 3 years. The benchmark is the ICE US Treasury 1-3 Year Bond Index.
- Caveat: inception is July 2002, so SHY cannot satisfy the 1970 coverage requirement by itself.

### Yahoo Finance / SHY and VFISX

- Status: `active_for_provisional_public_dataset`
- SHY endpoint: https://query1.finance.yahoo.com/v8/finance/chart/SHY
- VFISX endpoint: https://query1.finance.yahoo.com/v8/finance/chart/VFISX
- Role: public daily close and adjusted-close returns for the fund-backed dataset.
- Current finding: Yahoo chart data provides VFISX history from approximately 1991-10-29 and SHY history from 2002-07-30.
- Caveat: VFISX is a short-term Treasury fund proxy, not SHY's benchmark; Yahoo terms must be reviewed before redistribution.

### Federal Reserve Nominal Yield Curve (STT)

- Status: `active`
- URL: https://www.federalreserve.gov/data/nominal-yield-curve.htm
- CSV: https://www.federalreserve.gov/data/yield-curve-tables/feds200628.csv
- Role: primary public-source model input for the 1970-to-VFISX synthetic short Treasury segment.
- Current finding: the Federal Reserve provides daily estimated nominal yield curve parameters and smoothed yields from 1961 to the present.
- Caveats:
  - This is a Federal Reserve staff research product, not an official statistical release.
  - It provides fitted curves, not observed index total returns.
  - The pre-VFISX short Treasury segment is model-derived at 2-year maturity, with coupon carry computed by the project builder.

### CRSP US Treasury Database (STT)

- Status: `candidate_upgrade`
- URL: https://www.crsp.org/
- Role: preferred future source for a true constituent-level daily 1970+ SHY-like Treasury total-return index.
- Current finding: CRSP/WRDS Treasury issue-level data is the appropriate source class for daily prices/returns, coupon cash flows, maturities, and market values back before 1970.
- Caveat: likely requires licensed access through WRDS or another CRSP subscription.

## Intermediate-Term U.S. Treasury / IEF-like 7-10 Year Government Bonds

### iShares IEF

- Status: `target_definition_and_validation`
- URL: https://www.ishares.com/us/products/239456/ishares-710-year-treasury-bond-etf
- Role: defines the target exposure and provides post-2002 public ETF return data.
- Current finding: iShares describes IEF as tracking an index of U.S. Treasury bonds with remaining maturities between 7 and 10 years. The benchmark is the ICE US Treasury 7-10 Year Bond Index.
- Caveat: inception is July 2002, so IEF cannot satisfy the 1970 coverage requirement by itself.

### Yahoo Finance / IEF and VFITX

- Status: `active_for_provisional_public_dataset`
- IEF endpoint: https://query1.finance.yahoo.com/v8/finance/chart/IEF
- VFITX endpoint: https://query1.finance.yahoo.com/v8/finance/chart/VFITX
- Role: public daily close and adjusted-close returns for the fund-backed dataset.
- Current finding: Yahoo chart data provides VFITX history from approximately 1991-10-29 and IEF history from 2002-07-30.
- Caveat: VFITX is an intermediate-term Treasury fund proxy, not IEF's benchmark; Yahoo terms must be reviewed before redistribution.

### Federal Reserve Nominal Yield Curve (ITT)

- Status: `active`
- URL: https://www.federalreserve.gov/data/nominal-yield-curve.htm
- CSV: https://www.federalreserve.gov/data/yield-curve-tables/feds200628.csv
- Role: primary public-source model input for the 1970-to-VFITX synthetic intermediate Treasury segment.
- Current finding: the Federal Reserve provides daily estimated nominal yield curve parameters and smoothed yields from 1961 to the present.
- Caveats:
  - This is a Federal Reserve staff research product, not an official statistical release.
  - It provides fitted curves, not observed index total returns.
  - The pre-VFITX intermediate Treasury segment is model-derived at 8.5-year maturity, with coupon carry computed by the project builder.

### CRSP US Treasury Database (ITT)

- Status: `candidate_upgrade`
- URL: https://www.crsp.org/
- Role: preferred future source for a true constituent-level daily 1970+ IEF-like Treasury total-return index.
- Current finding: CRSP/WRDS Treasury issue-level data is the appropriate source class for daily prices/returns, coupon cash flows, maturities, and market values back before 1970.
- Caveat: likely requires licensed access through WRDS or another CRSP subscription.

## Long-Term U.S. Treasury / TLT-like 20+ Year Government Bonds

### iShares TLT

- Status: `target_definition_and_validation`
- URL: https://www.ishares.com/us/products/239454/ishares-20-year-treasury-bond-etf
- Role: defines the target exposure and provides post-2002 public ETF return data.
- Current finding: iShares describes TLT as tracking an index of U.S. Treasury bonds with remaining maturities greater than twenty years. The benchmark is the ICE US Treasury 20+ Year Bond Index.
- Caveat: inception is July 2002, so TLT cannot satisfy the 1970 coverage requirement by itself.

### Yahoo Finance / TLT and VUSTX

- Status: `active_for_provisional_public_dataset`
- TLT endpoint: https://query1.finance.yahoo.com/v8/finance/chart/TLT
- VUSTX endpoint: https://query1.finance.yahoo.com/v8/finance/chart/VUSTX
- Role: public daily close and adjusted-close returns for the provisional fund-backed dataset.
- Current finding: Yahoo chart data provides VUSTX history from 1986-05-19 and TLT history from 2002-07-30.
- Caveat: VUSTX is a long-term Treasury fund proxy, not TLT's benchmark; Yahoo terms must be reviewed before redistribution.

### Yahoo Finance / ^TYX (30-Year Treasury Yield)

- Status: `active`
- Endpoint: https://query1.finance.yahoo.com/v8/finance/chart/%5ETYX
- Role: observed daily 30-year Treasury yield used as the primary yield input for the 1977-02-15 to 1985-11-24 sub-period of the Fed model segment.
- Current finding: Yahoo chart data provides daily ^TYX history from 1977-02-15 onward. Values are quoted in percent (e.g., 7.50 = 7.50%).
- Caveats:
  - Not a total-return index; it is a yield observation.
  - Daily yield is used to price a synthetic 25-year par bond; the bond pricing introduces a flat-yield curve assumption.
  - Yahoo terms must be reviewed before redistribution.

### FRED DGS30

- Status: `candidate_model_input`
- URL: https://fred.stlouisfed.org/series/DGS30
- Role: alternative to Yahoo ^TYX for the 1977–1985 sub-period; not currently used because FRED CSV retrieval timed out in this environment.
- Current finding: FRED documents DGS30 as a daily 30-year Treasury constant maturity yield sourced from Federal Reserve H.15.
- Caveats:
  - The 30-year series was discontinued from 2002-02-18 to 2006-02-09.
  - A yield series is not a coupon-aware observed total-return index.
  - CSV retrieval timed out in this environment during initial implementation.

### Federal Reserve Nominal Yield Curve

- Status: `active`
- URL: https://www.federalreserve.gov/data/nominal-yield-curve.htm
- CSV: https://www.federalreserve.gov/data/yield-curve-tables/feds200628.csv
- Role: primary public-source model input for the 1970-to-VUSTX synthetic long Treasury segment; `SVENY10` used as a yield proxy for 1971–1977; `SVENY25`/`SVENY30` used for Nov 1985 to VUSTX start.
- Current finding: the Federal Reserve provides daily estimated nominal yield curve parameters and smoothed yields from 1961 to the present. `SVENY25` is `NaN` before November 1985, indicating the Svensson extrapolation is unreliable at that maturity for the early period.
- Caveats:
  - This is a Federal Reserve staff research product, not an official statistical release.
  - It provides fitted curves, not observed index total returns.
  - The Svensson BETA0 parameter is numerically ill-conditioned at very long maturities (25y+) in the early 1970s; direct Svensson extrapolation to 25 years is not used for this reason.

### CRSP US Treasury Database

- Status: `candidate_upgrade`
- URL: https://www.crsp.org/
- Role: preferred future source for a true constituent-level daily 1970+ TLT-like Treasury total-return index.
- Current finding: CRSP/WRDS Treasury issue-level data is the appropriate source class for daily prices/returns, coupon cash flows, maturities, and market values back before 1970.
- Caveat: likely requires licensed access through WRDS or another CRSP subscription.

## Gold (GLD-tracking) / GOLDPM

`GOLDPM` is built to track SPDR Gold Shares (`GLD`) including its fee drag, extended to 1970.
`Close` = LBMA PM pure spot (drives `Price Return`); `Adj Close` = GLD-tracking total return
(spot − 0.40% expense drag pre-2004, then observed GLD).

### LBMA Gold Price PM

- Status: `active`
- URL: https://prices.lbma.org.uk/json/gold_pm.json
- Public page: https://www.lbma.org.uk/prices-and-data/precious-metal-prices
- Role: drives `Close` / `Price Return` (pure spot) across 1970-present and the modeled `Adj Close`
  before GLD inception.
- Current finding: public JSON endpoint is reachable and provides daily PM gold prices back before 1970. The first JSON value is USD per troy ounce.
- Caveats:
  - This is a daily benchmark/fixing price (London PM, ~10am ET), not OHLCV and not the US close.
  - It is not a futures total-return index and not an ETF return series.

### SPDR Gold Shares (GLD) — Yahoo chart API

- Status: `active_from_2004`
- URL: https://query1.finance.yahoo.com/v8/finance/chart/GLD
- Role: drives `Adj Close` / `Total Return` from 2004-11-19; `Adj Close` is exactly proportional to
  GLD's adjusted close in this era.
- Current finding: GLD inception 2004-11-18; adjusted close embeds the 0.40% expense erosion. GLD
  underperformed pure spot by ~0.49%/yr over 2004-2026 (mostly the fee), the drag folded in here.
- Caveat: 4pm ET close vs the LBMA PM fix; zero-mean for cumulative return. US-holiday rows flat.

### US-close gold base (COMEX futures / Stooq) — deferred daily-fidelity upgrade

- Status: `blocked` (Stooq returns an anti-bot challenge in this environment; Yahoo `GC=F` only
  reaches 2000-08).
- Role: a US-4pm-aligned gold base would raise daily correlation with GLD from ~0.65 (PM fix) to
  ~0.89; deferred because the timing basis does not bias cumulative return.

### LBMA Gold Price AM

- Status: `validation`
- URL: https://prices.lbma.org.uk/json/gold_am.json
- Role: same-administrator sanity reference.
- Caveat: useful for gross checks, but not independent from LBMA PM.

### FRED Gold PM

- Status: `candidate_validation_source`
- URL: https://fred.stlouisfed.org/series/GOLDPMGBD228NLBM
- Role: candidate validation source for London PM gold prices.
- Current finding: FRED API metadata requires an API key, and the graph CSV endpoint timed out during initial implementation.
- Caveat: likely mirrors the same London PM benchmark, so it is not methodologically independent from LBMA.

### Nasdaq Data Link LBMA/GOLD

- Status: `blocked`
- URL: https://data.nasdaq.com/api/v3/datasets/LBMA/GOLD.csv
- Role: candidate mirror of LBMA gold data.
- Current finding: endpoint returned `403` from this environment.

## Broad Commodities / DBC-like Diversified Futures Total Return

### S&P GSCI Total Return anchor (MacroMicro republication)

- Status: `active_anchor_segments_0_1` (static committed file)
- URL: https://en.macromicro.me/series/2692/sp-gsci-index
- Raw file: `sources/raw/broad_commodities_gsci_tr_macromicro.csv`
- Role: anchor for the 1970-1991 reconstruction. Adj Close (total return) tracks this series; Close (excess return) strips the daily `^IRX` collateral.
- Current finding (2026-06-26): free programmatic S&P GSCI Total Return is paywalled everywhere (Yahoo `^SPGSCITR` empty; `GSG` 2006+; FRED/DBnomics none; Investing.com and Barchart blocked). MacroMicro's free series page renders the data in a Highcharts object; extracted in-browser (Claude-in-Chrome) and saved as a static CSV. Full 1970-01-02 -> 2026-06-25 range, base 100 at 1970-01-02, downsampled to 358 points (~57-day spacing).
- Validation: GSCI TR grew 3.08x vs `^SPGSCI` spot 1.04x over 1984-1991 (collateral ~1.64x + residual ~1.8x => ~9%/yr roll yield); 3.06x vs `^BCOM` ER 1.83x over 1991-2006 (~1.67x = collateral + GSCI energy tilt). Confirms roll-inclusive, collateralized total return.
- Caveats:
  - Downsampled republication, not a licensed daily S&P feed. Adj Close tracks the index to within ~5% at sample dates; Segment 0 daily volatility is smoothed and Segment 1's daily shape is `^SPGSCI` spot.
  - S&P GSCI is back-tested before its 1991 launch and is more energy-heavy than DBC.
  - S&P-derived via a third-party republication; review licensing before redistributing derived data.

### World Bank Commodity Markets Pink Sheet Total Commodity Index (superseded)

- Status: `superseded_by_gsci_tr_anchor` (was `active_segment_0_model_input` 2026-06 to 2026-06-26)
- URL: https://thedocs.worldbank.org/en/doc/5d903e848db1d1b83e0ec8f744e55570-0350012021/related/CMO-Historical-Data-Monthly.xlsx
- Role (former): Segment 0 (1970-01-02 to 1984-01-03) broad commodity model input.
- Why superseded: spot-only monthly index — no futures roll yield, and 67%-energy Laspeyres export-value weights differ materially from DBC/GSCI. Replaced by the GSCI Total Return anchor, which carries roll + collateral + production weights. Raw workbook retained but no longer in the active build path.

### 1970-1983 Daily Source Search - Rejected or Blocked

- **Yahoo `^CRB`, `^TRJEFFCRB`, `^RJI`, `^CCI`, futures `XX=F`, `CIY=F`, `CRB=F`**: no usable 1970-1983 daily broad commodity history; Yahoo continuous futures generally start around 2000.
- **Stooq.com**: direct CSV request returned a JavaScript verification page.
- **CRBTrader**: public CRB data page did not expose a clean unauthenticated data table.
- **Nasdaq Data Link / Quandl CHRIS continuous futures**: direct API request was blocked by Incapsula from this environment.
- **FRED CSV endpoints**: timed out in prior sessions; relevant broad commodity series are generally monthly.
- **EIA WTI daily**: starts 1986; after the gap.
- **BLS / NBER / AQR / IMF**: monthly or otherwise not clean observed daily broad futures-index data.
- **Bloomberg BCOM TR, S&P GSCI back-history, Refinitiv/LSEG, CRSP, vendor futures databases**: licensed access required.
- **Conclusion**: no clean public observed daily broad-commodity index source was found for 1970-1983; the implemented public-source fix is a broad monthly model, not a precious-metals-only proxy.

### Yahoo Finance / ^SPGSCI

- Status: `active_segment_1_daily_shape`
- Endpoint: https://query1.finance.yahoo.com/v8/finance/chart/%5ESPGSCI
- Role: Segment 1 (1984-01-04 to 1991-01-02) daily spot **shape** source. The daily `^SPGSCI` returns are rescaled per anchor interval so each interval compounds to the GSCI Total Return anchor — this supplies the daily shape (genuine moves and event timing, ~16%/yr vol), while the anchor supplies the level (roll + collateral).
- Current finding: available daily from 1984-01-03 (10,703 rows as of 2026-06-26). `adj close == close` (spot index, no distributions).
- Caveats:
  - Spot only — it supplies the shape, not the level. The roll/collateral that lift it to total return come from the GSCI TR anchor as a smooth per-interval overlay.
  - Pre-1991 GSCI data is retroactive back-history.

### Yahoo Finance / ^BCOM

- Status: `active_segment_2`
- Endpoint: https://query1.finance.yahoo.com/v8/finance/chart/%5EBCOM
- Role: Segment 2 (1991-01-03 to 2006-02-06) excess return (spot + roll yield) source.
- Current finding: available daily from 1991-01-02 (8,900 rows as of 2026-06-12). `adj close == close` (no distributions). Verified as the Bloomberg Commodity **Excess Return** index by checking 2021 annual return (27.06%) against BCOM ER 2021 (~27.1%); the BCOM Spot Return 2021 (~25.5%) did not match.
- Caveats:
  - Different commodity weights and index methodology from GSCI, World Bank, and DBC. The 1991 splice is a methodology switch, not a seamless continuation.
  - Yahoo index-type verification is indirect; the raw Yahoo payload does not provide official Bloomberg metadata.
  - `^IRX` collateral is a project model for total return; official BCOMTR daily levels are not available for validation. Yahoo `^BCOMTR` returns only 1 row and is not usable.

### Yahoo Finance / DBC

- Status: `active_segment_3`
- Endpoint: https://query1.finance.yahoo.com/v8/finance/chart/DBC
- Role: Segment 3 (2006-02-07 to present) observed ETF total return.
- Current finding: available daily from 2006-02-06 (5,122 rows as of 2026-06-16). `adj close ≠ close` (Yahoo adj close captures accumulated T-bill collateral distributions — confirmed good total return proxy).
- Caveats:
  - Tracks DBLCI/DBIQ exposure using optimum-yield rolling, different from GSCI/BCOM roll rules and World Bank spot prices.
  - ETF net returns include expense drag, fund operations, tracking error, and distribution handling. The expense ratio is about 0.89% annually, so DBC slightly understates gross benchmark returns.
  - Yahoo adjusted close is the production source; tests validate against Yahoo raw payload rather than Invesco official NAV total-return history.

### Yahoo Finance / ^IRX

- Status: `active_segments_0_1_and_2`
- Endpoint: https://query1.finance.yahoo.com/v8/finance/chart/%5EIRX
- Role: Segment 0 trading calendar and T-bill collateral rate model for Segments 0, 1, and 2.
- Current finding: available daily from 1970-01-02. The close column is the 13-week T-bill annualized rate in percent. Daily collateral accrual = `IRX_close / 100 / 365` (actual/365, matching the GSCI Total Return definition).
- Caveats:
  - `^IRX` is a proxy collateral rate; official index collateral conventions may differ by vendor and period.
  - In Segment 0 it is also used as a daily calendar for a monthly global commodity index, which is a project convention.
  - FRED DTB3/TB3MS timed out and was not used. Missing IRX dates are forward-filled.

### Bloomberg BCOM Total Return (BCOMTR)

- Status: `validation`
- Role: ideal validation source for Segment 2 Adj Close levels.
- Current finding: not publicly available without a Bloomberg terminal subscription.

### S&P GSCI Total Return Index (licensed daily)

- Status: `validation` / `candidate_upgrade`
- Role: a licensed **daily** S&P GSCI Total Return feed would replace the downsampled MacroMicro anchor (removing the smoothing/interpolation) and serve as ideal validation.
- Current finding: free daily history is paywalled (Yahoo `^SPGSCITR` empty; `GSG` 2006+; FRED/DBnomics none; Investing.com/Barchart blocked). The build uses MacroMicro's free ~bi-monthly republication as the anchor (see active anchor entry above).

### AQR Commodities for the Long Run (rejected anchor candidate)

- Status: `rejected`
- URL: https://www.aqr.com/Insights/Datasets/Commodities-for-the-Long-Run-Index-Level-Data-Monthly
- Role: alternative roll-inclusive monthly total-return anchor back to 1877; confirmed freely downloadable.
- Why rejected: equal-weighted, so not the energy-tilted DBC-like exposure chosen for this dataset. Retained as a documented alternative anchor.

## 3x U.S. Large Cap (UPRO-like) / USLCAP3X

Derived leveraged dataset. The underlying exposure is the project's own `USLCAP` total-return
series; `^IRX` supplies the financing benchmark; `UPRO` is the live-overlap calibration and
post-inception return source.

### USLCAP base dataset (us_large_cap_sp500)

- Status: `active`
- Path: `data/processed/us_large_cap_sp500.csv`
- Role: underlying daily total return (`u`) for the 3x daily-reset model.
- Current finding: the `Total Return` column is S&P 500 daily total return (French/CRSP large-cap
  before `^SP500TR`, then `^SP500TR`) from 1970-01-02.
- Caveats: pre-1988 underlying is a CRSP large-cap proxy; the synthetic 3x series inherits that
  approximation.

### Yahoo Finance / ^IRX (financing benchmark)

- Status: `active`
- Endpoint: https://query1.finance.yahoo.com/v8/finance/chart/%5EIRX
- Role: financing-rate benchmark for the borrowed (2x) exposure, 1970-present.
- Current finding: 13-week T-bill annualized discount yield (percent), daily from 1970-01-02.
  A calibrated borrowing spread is added; financing accrues actual/360 on the `(L-1)` exposure.
- Caveats: `^IRX` is a T-bill proxy for the fund's swap/borrowing rate; the true rate is closer
  to the overnight/fed-funds rate plus a time-varying counterparty spread. Missing dates are
  forward-filled.

### Yahoo Finance / UPRO (observed ETF + calibration target)

- Status: `active_from_2009`
- Endpoint: https://query1.finance.yahoo.com/v8/finance/chart/UPRO
- Role: observed adjusted-close total returns from inception, and calibration target for the
  synthetic pre-inception model.
- Current finding: daily adjusted history from 2009-06-25. The calibrated model reproduces UPRO
  over the overlap at 0.998 daily correlation, ~3.2% annualized tracking error, and cumulative
  growth within ~0.01%.
- Caveats: Yahoo/yfinance data rights must be reviewed before redistribution; official ProShares
  NAV total-return history was not used.

### ProShares UPRO prospectus / fund page

- Status: `reference`
- URL: https://www.proshares.com/our-etfs/leveraged-and-inverse/upro
- Role: parameter reference (3x daily S&P 500 objective; 0.91% expense ratio).

## 3x Long-Term Treasury (TMF-like) / LTT3X

Derived leveraged dataset. The underlying exposure is the project's own `LTT` total-return
series; `^IRX` supplies the financing benchmark; `TMF` is the live-overlap calibration and
post-inception return source.

### LTT base dataset (long_term_us_treasury)

- Status: `active`
- Path: `data/processed/long_term_us_treasury.csv`
- Role: underlying daily total return (`u`) for the 3x daily-reset model.
- Current finding: the `Total Return` column is TLT-like long-Treasury daily total return (Fed
  yield-curve 25-year par model before VUSTX, then VUSTX, then TLT) from 1970-01-02.
- Caveats: pre-2002 underlying is a Fed 25-year par model and VUSTX, not the ICE 20+ Year index
  TMF tracks — a documented duration/exposure mismatch the synthetic 3x series inherits.

### Yahoo Finance / ^IRX (financing benchmark)

- Status: `active`
- Endpoint: https://query1.finance.yahoo.com/v8/finance/chart/%5EIRX
- Role: financing-rate benchmark for the borrowed (2x) exposure, 1970-present (shared with
  USLCAP3X and the broad-commodities collateral model).
- Current finding: 13-week T-bill annualized discount yield (percent), daily from 1970-01-02.
  A calibrated borrowing spread is added; financing accrues actual/360 on the `(L-1)` exposure.
- Caveats: `^IRX` is a T-bill proxy for the fund's swap/futures financing rate. Missing dates
  are forward-filled.

### Yahoo Finance / TMF (observed ETF + calibration target)

- Status: `active_from_2009`
- Endpoint: https://query1.finance.yahoo.com/v8/finance/chart/TMF
- Role: observed adjusted-close total returns from inception, and calibration target for the
  synthetic pre-inception model.
- Current finding: daily adjusted history from 2009-04-16. The calibrated model reproduces TMF
  over the overlap at 0.997 daily correlation, ~3.7% annualized tracking error, and cumulative
  growth within ~0.04%. TMF's cumulative return over the rising-rate overlap is well below 1.0
  (large leverage decay).
- Caveats: Yahoo/yfinance data rights must be reviewed before redistribution; official Direxion
  NAV total-return history was not used.

### Direxion TMF prospectus / fund page

- Status: `reference`
- URL: https://www.direxion.com/product/daily-20-year-treasury-bull-bear-3x-etfs
- Role: parameter reference (3x daily ICE U.S. Treasury 20+ Year Bond Index objective; ~1.06% ER).

## 3x Intermediate-Term Treasury (TYD-like) / ITT3X

Derived leveraged dataset. The underlying exposure is the project's own `ITT` total-return
series; `^IRX` supplies the financing benchmark; `TYD` is the live-overlap calibration and
post-inception return source. Note: the genuine 3x 7-10 year Treasury ETF is Direxion **TYD**;
ProShares **UST** is a **2x** fund despite the backlog's "3x UST" label.

### ITT base dataset (intermediate_term_us_treasury)

- Status: `active`
- Path: `data/processed/intermediate_term_us_treasury.csv`
- Role: underlying daily total return (`u`) for the 3x daily-reset model.
- Current finding: the `Total Return` column is IEF-like intermediate-Treasury daily total return
  (Fed yield-curve 8.5-year par model before VFITX, then VFITX, then IEF) from 1970-01-02.
- Caveats: pre-2002 underlying is a Fed 8.5-year par model and VFITX, not the ICE 7-10 Year index
  TYD tracks.

### Yahoo Finance / ^IRX (financing benchmark)

- Status: `active`
- Endpoint: https://query1.finance.yahoo.com/v8/finance/chart/%5EIRX
- Role: financing-rate benchmark for the borrowed (2x) exposure, 1970-present (shared across the
  leveraged datasets and the broad-commodities collateral model).
- Current finding: 13-week T-bill annualized discount yield (percent), daily from 1970-01-02.

### Yahoo Finance / TYD (observed ETF + calibration target)

- Status: `active_from_2009`
- Endpoint: https://query1.finance.yahoo.com/v8/finance/chart/TYD
- Role: observed adjusted-close total returns from inception, and calibration target for the
  synthetic pre-inception model.
- Current finding: daily adjusted history from 2009-04-16. The calibrated model matches TYD's
  cumulative growth within ~0.02%, but full-overlap daily correlation is only ~0.88 (~10% ann.
  TE): correlation is 0.92-0.996 in 2009-2013 and 2019-2026 but collapses to 0.37-0.66 in
  2014-2018, reflecting TYD's thin trading and stale/illiquid Yahoo closes in that low-AUM period.
- Caveats: cumulative growth (robust to mean-reverting stale-price noise) is the calibration
  target; daily fidelity is validated on the clean recent era. Yahoo/yfinance data rights apply.

### Direxion TYD prospectus / fund page

- Status: `reference`
- URL: https://www.direxion.com/product/daily-7-10-year-treasury-bull-bear-3x-etfs
- Role: parameter reference (3x daily ICE U.S. Treasury 7-10 Year Bond Index objective; ~1.09% ER).

### ProShares UST (rejected — wrong leverage)

- Status: `rejected`
- URL: https://www.proshares.com/our-etfs/leveraged-and-inverse/ust
- Role: none for ITT3X. UST is ProShares Ultra 7-10 Year Treasury, a **2x** fund (not 3x); it is
  the future validation target for a separate `ITT2X` (2x) dataset.

## 2x Gold (UGL-like) / GOLD2X

Derived leveraged dataset. The underlying exposure is the project's own `GOLDPM` LBMA PM spot
series; `^IRX` supplies the financing benchmark; `UGL` is the live-overlap calibration and
post-inception return source; `GLD` is a timing-basis cross-check only.

### GOLDPM base dataset (gold)

- Status: `active`
- Path: `data/processed/gold.csv`
- Role: underlying daily return (`u`) for the 2x daily-reset model.
- Current finding: the **`Price Return`** column is the pure LBMA Gold Price PM spot return from
  1970-01-02. Price Return (not Total Return) is used because GOLDPM was redefined to track GLD —
  its Total Return now carries GLD's 0.40% expense drag — so the 2x fund builds on pure spot and
  applies its own financing/fee once. (Holiday double-count fixed 2026-06-20; see methodology.)
- Caveats: LBMA PM fix (~10:30am ET), a spot fixing struck ~5.5 hours before UGL's 4pm US close
  (timing basis, see below).

### Yahoo Finance / ^IRX (financing benchmark)

- Status: `active`
- Endpoint: https://query1.finance.yahoo.com/v8/finance/chart/%5EIRX
- Role: financing-rate benchmark for the borrowed (1x) exposure of the 2x fund, 1970-present.

### Yahoo Finance / UGL (observed ETF + calibration target)

- Status: `active_from_2008`
- Endpoint: https://query1.finance.yahoo.com/v8/finance/chart/UGL
- Role: observed adjusted-close total returns from inception, and calibration target.
- Current finding: daily adjusted history from 2008-12-03. The calibrated model matches UGL's
  cumulative growth within ~0.07%, but full-overlap daily correlation is only ~0.67 (~28% ann. TE),
  roughly constant across years — a timing basis, not a data problem.

### Yahoo Finance / GLD (timing-basis cross-check)

- Status: `validation`
- Endpoint: https://query1.finance.yahoo.com/v8/finance/chart/GLD
- Role: diagnostic only (not in the build). UGL daily returns vs 2x-GLD correlate at ~0.997 (both
  at US close), while LBMA PM-fix returns vs same-day GLD correlate at ~0.66 — proving the modest
  UGL-vs-model correlation is the LBMA-fix vs US-close clock offset, and the 2x model logic is right.

### ProShares UGL prospectus / fund page

- Status: `reference`
- URL: https://www.proshares.com/our-etfs/leveraged-and-inverse/ugl
- Role: parameter reference (2x daily Bloomberg Gold Subindex objective; 0.95% ER). Benchmark is
  futures-based; the model underlying is LBMA spot, with the calibrated spread absorbing roll/storage.

## U.S. CPI-U Inflation Index / CPI

Calendar-daily inflation deflator for real-return backtesting analysis. BLS publishes the active source
monthly, so daily rows are explicitly model-derived.

### BLS CPI-U / CUSR0000SA0

- Status: `active`
- Endpoint: https://api.bls.gov/publicAPI/v2/timeseries/data/
- Role: primary monthly CPI-U source.
- Current finding: monthly seasonally adjusted CPI-U, all urban consumers, U.S. city average, all
  items, index 1982-84=100. The current build has monthly observations from 1970-01-01 through
  2026-05-01.
- Caveats: BLS does not publish observed daily CPI. The processed daily dataset uses constant log
  interpolation between monthly observations and carries the latest monthly level forward after
  the last release.

### FRED CPIAUCSL

- Status: `validation`
- URL: https://fred.stlouisfed.org/series/CPIAUCSL
- Role: validation/reference source for the same seasonally adjusted CPI-U concept.
- Current finding: direct FRED CSV retrieval timed out in this environment, so BLS is the active
  source for the local build.

## Global All-World Stocks / GLSTOCK

Long-horizon global equity total-return proxy. The target style is VT / MSCI ACWI / FTSE
All-World. Public daily all-world total-return history back to 1970 was not available without a
licensed source, so the early history is model-derived and heavily caveated.

### MSCI World Annual Gross Total Returns

- Status: `active_model_input`
- Role: annual return anchor for the 1970-1989 model segment.
- Current finding: MSCI World has public annual gross total-return history from 1970.
- Caveats: annual returns are not daily observations. The build uses USLCAP daily returns as the
  within-year path and applies a constant log overlay so each calendar year matches the annual
  MSCI World gross return.

### USLCAP Base Dataset

- Status: `active_model_input`
- Path: `data/processed/us_large_cap_sp500.csv`
- Role: early daily path proxy and short 1990 gap fill.
- Caveats: U.S.-biased proxy, not global equity history.

### Kenneth French Data Library / Developed 3 Factors Daily

- Status: `active`
- URL: https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/Developed_3_Factors_Daily_CSV.zip
- Role: daily developed-market total-return source from 1990-07-02 to the VT splice.
- Current finding: daily `Mkt-RF` and `RF`; the build uses `(Mkt-RF + RF) / 100`.
- Caveats: developed markets only; excludes emerging markets before VT.

### Yahoo Finance / VT

- Status: `active_from_2008`
- Endpoint: https://query1.finance.yahoo.com/v8/finance/chart/VT
- Role: observed Vanguard Total World Stock ETF adjusted-close total-return segment.
- Current finding: adjusted-close history starts on 2008-06-26; build uses observed VT returns from
  the next row onward.
- Caveats: ETF net returns include expenses, sampling/tracking differences, and Yahoo adjusted-close
  dependence.

### Licensed MSCI ACWI / FTSE All-World Daily Total Return

- Status: `candidate_upgrade`
- Role: preferred future replacement for the model-derived/public-source proxy chain.
- Caveats: requires licensed access and redistribution review.

## Unhedged Global Bonds / GLBOND

Long-horizon unhedged global bond proxy. The early-segment daily path is reconstructed from
observed daily FX (BIS) and observed monthly government-bond yields (OECD MEI), GDP-weighted
across 16 advanced economies, and rescaled so each calendar year matches the JST annual basket.
The observed segment uses a daily BND/BWX unhedged blend.

### Jorda-Schularick-Taylor Macrohistory Database

- Status: `active_model_input`
- URL: https://www.macrohistory.net/database/
- Role: annual level anchor + GDP weights for 1970-2007. Each calendar year of the early
  segment is rescaled to compound to the recomputed JST GDP-weighted unhedged USD basket.
  Weights use comparable real GDP (`rgdpmad` x `pop`), not nominal `gdp` (whose units are
  inconsistent across countries — see caveat).
- Current finding: annual government bond total returns, USD exchange rates, real GDP per
  capita (`rgdpmad`), population, and nominal GDP for 18 advanced economies since 1870;
  16 contribute valid data every year 1970-2007.
- Caveats: annual frequency; supplies the level anchor only, not the within-year path. Do
  not weight by `gdp / xrusd`: JST nominal `gdp` is in inconsistent local-currency units
  (US in billions, Spain in millions of pesetas), which mis-weights the basket toward small
  economies (US ~0.3%). Weight by real GDP instead. JST has
  non-commercial license terms; review before redistribution.

### BIS Daily Exchange Rates (`WS_XRU`, via DBnomics)

- Status: `active_model_input`
- Endpoint: https://api.db.nomics.world/v22/series/BIS/WS_XRU/D.<area>.<ccy>.A
- Role: genuine daily FX leg of the 1970-2007 path (local currency per USD), for all 16
  countries. Euro-legacy countries use the chained `.EUR.` series.
- Current finding: daily rates back to the 1950s-1971 (JPN from 1969-12, AUS/FIN from 1971-01);
  uniformly quoted as local currency per USD (same convention as JST `xrusd`). Key-less.
- Caveats: pre-1971 FX is fixed (Bretton Woods), so genuinely flat there; daily series sampled
  onto the U.S. trading-day grid by forward-fill.

### OECD MEI Long-Term Interest Rates (`IRLTLT01`, via DBnomics)

- Status: `active_model_input`
- Endpoint: https://api.db.nomics.world/v22/series/OECD/MEI/<ISO3>.IRLTLT01.ST.M
- Role: monthly 10-year government-bond yield leg for countries without a daily source. Each
  month a constant-maturity 10y par bond is repriced (price move + coupon carry), smoothed
  within month.
- Current finding: monthly yields from 1970 or earlier for 9 of 16 countries (US, Germany, UK,
  Canada, France, Netherlands, Switzerland, Belgium, Australia); Japan from 1989, Italy 1991,
  Spain 1980, Nordics in the 1980s. Key-less.
- Caveats: monthly frequency (not daily); countries without an early yield are basket-proxied on
  the bond-price leg until their data begins, but still carry daily FX.

### MoF Japan historical JGB yields (`jgbcm_all.csv`)

- Status: `active_model_input`
- Endpoint: https://www.mof.go.jp/jgbs/reference/interest_rate/data/jgbcm_all.csv
- Role: genuine daily 10y JGB yield for the Japanese bond leg (daily par-bond TR).
- Current finding: daily yields for 1-40y maturities; the 10y column is continuous from
  1986-07-05 (sparse "-" before that). cp932-encoded, Japanese-era dates (S/H/R). Full file
  (~1.2 MB) cached to sources/raw.
- Caveats: 10y benchmark unavailable daily before 1986-07, so Japan stays basket-proxied
  1970-1986; ~4% scattered blanks after are forward-filled.

### Bank of England GLC nominal daily yield curve

- Status: `active_model_input`
- Endpoint: https://www.bankofengland.co.uk/-/media/boe/files/statistics/yield-curves/glcnominalddata.zip
- Role: genuine daily 10y nominal spot gilt yield for the UK bond leg (daily par-bond TR).
- Current finding: zip of yearly Excel workbooks; the "4. nominal spot curve" sheet holds
  0.5y-step spot yields with the 10y column from 1979-01. Parsed manually (no openpyxl
  dependency). The 39 MB archive is fetched at build time but not committed; only the compact
  extracted 10y series (`global_bonds_boe_gilt_10y.csv`, ~140 KB) is persisted.
- Caveats: spot (zero-coupon) yields used as the par-model input (minor for a ~flat curve);
  daily from 1979 only.

### In-repo U.S. 7-10y Treasury total return

- Status: `active_model_input`
- Path: `data/processed/intermediate_term_us_treasury.csv`
- Role: genuine daily U.S. bond leg (1970+), reusing the project's Fed-yield-curve-derived
  intermediate Treasury total return rather than re-modelling US rates.
- Caveats: ~8.5y constant maturity (vs 10y for the par-model countries); immaterial and
  absorbed by the annual overlay.

### FRED CSV / stooq daily FX

- Status: `blocked`
- Finding: the FRED `fredgraph.csv` download endpoint and stooq CSV both fail in this
  environment (connection reset / bot challenge). FRED daily H.10 FX and stooq daily FX were
  therefore not used; BIS `WS_XRU` via DBnomics supplies daily FX instead.

### Yahoo Finance / BND

- Status: `active_segment`
- Endpoint: https://query1.finance.yahoo.com/v8/finance/chart/BND
- Role: U.S. bond component in the observed daily blend.
- Current finding: adjusted-close history from 2007-04-10.

### Yahoo Finance / BWX

- Status: `active_segment`
- Endpoint: https://query1.finance.yahoo.com/v8/finance/chart/BWX
- Role: international unhedged bond component in the observed daily blend.
- Current finding: adjusted-close history from 2007-10-11. BWX is local-currency international
  treasury exposure, so its USD adjusted-close returns include currency effects.

### Licensed Global Bond Index History

- Status: `candidate_upgrade`
- Role: preferred replacement for annual-smoothed model data.
- Candidate sources: FTSE World Government Bond Index total returns, Bloomberg Global Aggregate
  unhedged daily total return, or a constituent-level global sovereign reconstruction.

## Unhedged Global Short-Term (1-3yr) Government Bonds / GLSTBOND

Reuses the GLBOND FX (BIS) and JST inputs. Short-end-specific sources below; status keys as
elsewhere.

### Jorda-Schularick-Taylor (GDP weights + pre-OECD short-rate fallback)

- Status: `active_model_input`
- URL: https://www.macrohistory.net/database/
- Role: prior-year real-GDP (`rgdpmad` x `pop`) basket weights and US-vs-ex-US split; annual
  `stir`/`ltrate` (percent) interpolated to 2yr as the pre-OECD monthly-yield fallback. NB: no
  annual return overlay - `bond_tr` is a 10yr long-bond return, wrong for a 1-3yr series.

### OECD MEI 3-month interbank rate (`IR3TIB01` via DBnomics)

- Status: `active_model_input`
- Endpoint: https://api.db.nomics.world/v22/series/OECD/MEI/
- Role: short node of the 2yr interpolation (with `IRLTLT01`). Coverage varies (US/DEU/CAN from
  the 1960s; CHE from 1999, JPN from 2002), so JST fills the early gaps.

### OECD MEI 10-year rate (`IRLTLT01` via DBnomics)

- Status: `active_model_input`
- Role: long node of the 2yr interpolation; reused from GLBOND.

### MoF Japan historical JGB yields (2yr column)

- Status: `active_model_input`
- Endpoint: https://www.mof.go.jp/jgbs/reference/interest_rate/data/jgbcm_all.csv
- Role: genuine daily 2yr JGB yield. The 1-9yr nodes are continuous from **1974-09-25** -
  twelve years before the 10yr - giving Japan an early short-end daily rate leg.

### Bank of England GLC nominal daily yield curve (2yr node)

- Status: `active_model_input`
- Role: genuine daily 2yr nominal spot gilt yield from 1979 (parser selects the column nearest
  2.0y). Only the extracted 2yr series (`global_short_term_bonds_boe_gilt_2y.csv`) is persisted.

### In-repo U.S. 1-3yr Treasury total return (STT)

- Status: `active_model_input`
- Path: `data/processed/short_term_us_treasury.csv`
- Role: genuine daily US short bond leg (1970+), reusing the project's Fed-yield-curve-derived
  short Treasury rather than re-modelling US rates.

### Yahoo Finance / SHY, ISHG, BWZ

- Status: `active_segment`
- Endpoints: query1.finance.yahoo.com/v8/finance/chart/{SHY,ISHG,BWZ}
- Role: observed GDP-weighted blend. SHY (US 1-3yr Treasury, 2002-07) is the US leg; ISHG
  (iShares 1-3yr Intl Treasury, 2009-01-28) and BWZ (SPDR Short Term Intl Treasury, 2009-01-30)
  are averaged for the developed ex-US leg. Blend begins 2009-01-30.

### Market-cap (investable short sovereign debt) weighting

- Status: `candidate_upgrade`
- Role: preferred weighting basis for a bond fund (vs GDP). Candidate: BIS debt-securities
  statistics for outstanding short-maturity sovereign debt.

### Licensed Global Short Government Bond Index History

- Status: `candidate_upgrade`
- Candidate sources: FTSE WGBI Developed 1-3yr, Bloomberg Short Global Treasury unhedged daily
  total return, or daily per-country 2yr sovereign yields for the remaining markets.
