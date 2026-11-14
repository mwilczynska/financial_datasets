# AUDUSD, EURUSD, GBPUSD - Daily Spot Exchange Rates Against the U.S. Dollar

Dataset identifiers: `fx_aud_usd`, `fx_eur_usd`, `fx_gbp_usd`

Backtest/utility aliases: `AUDUSD`, `EURUSD`, `GBPUSD`

Status: observed daily reference rates from 1970, except a modeled 1970 for AUD and a Deutsche Mark proxy for EUR before 1999

## Asset Definition

Each dataset is a spot exchange rate quoted as **U.S. dollars per one unit of the foreign currency**, the usual market convention for these three pairs. A rising level means the foreign currency strengthened against the dollar.

- `Close`: spot rate, USD per 1 AUD, EUR, or GBP.
- `Adj Close`: equal to `Close`.
- `Price Return` and `Total Return`: daily change in the spot rate. Both are identical.
- `Open`, `High`, `Low`, `Volume`: blank.

These are conversion series, not investable total-return assets. Holding a foreign currency also earns that currency's interest rate; the datasets carry no interest income, so `Adj Close` must not be read as the return on a currency deposit. They are not part of the USD cash-distribution companions.

To convert a USD asset level to AUD, divide by `AUDUSD` on the same date (see the timing caveat below).

## Output Files

| File | Path |
|---|---|
| CSV | `data/processed/fx_aud_usd.csv`, `fx_eur_usd.csv`, `fx_gbp_usd.csv` |
| Parquet | `data/processed/fx_aud_usd.parquet`, `fx_eur_usd.parquet`, `fx_gbp_usd.parquet` |
| Manifests | `sources/manifests/fx_aud_usd.yml`, `fx_eur_usd.yml`, `fx_gbp_usd.yml` (plus `*_build.json`) |
| Citation notes | `sources/citations/fx_rates.md` |
| Shared module | `src/fx_rates.py` |
| Build scripts | `src/build_fx_aud_usd.py`, `build_fx_eur_usd.py`, `build_fx_gbp_usd.py` |
| Update scripts | `src/update_fx_aud_usd.py`, `update_fx_eur_usd.py`, `update_fx_gbp_usd.py` |
| Test files | `tests/validation/test_fx_rates_contract.py`, `tests/automation/test_fx_rates.py` |

Coverage starts on `1970-01-02`. Rows exist only on days the source published a rate, so the calendar follows BIS observation days before 1999 and ECB (TARGET) business days afterward. It is not the U.S. trading calendar and no rate is carried forward across holidays.

## Segments

| Pair | Period | Source | Quality flag |
|---|---|---|---|
| AUDUSD | 1970-01-02 to 1970-12-31 | Modeled from BIS daily GBP per USD and the sterling peg | `model_sterling_peg_cross_from_bis_gbp_usd` |
| AUDUSD | 1971-01-04 to 1998-12-31 | BIS `WS_XRU` `D.AU.AUD.A`, inverted | `observed_bis_daily_aud_usd` |
| AUDUSD | 1999-01-04 onward | ECB reference rates, USD/EUR divided by AUD/EUR | `observed_ecb_reference_rate_cross_aud_usd` |
| EURUSD | 1970-01-02 to 1998-12-31 | BIS `WS_XRU` `D.DE.EUR.A`, inverted (Deutsche Mark at 1.95583 DEM per EUR) | `proxy_bis_deutsche_mark_at_fixed_euro_conversion_rate` |
| EURUSD | 1999-01-04 onward | ECB USD/EUR reference rate as published | `observed_ecb_reference_rate_eur_usd` |
| GBPUSD | 1970-01-02 to 1998-12-31 | BIS `WS_XRU` `D.GB.GBP.A`, inverted | `observed_bis_daily_gbp_usd` |
| GBPUSD | 1999-01-04 onward | ECB reference rates, USD/EUR divided by GBP/EUR | `observed_ecb_reference_rate_cross_gbp_usd` |

## Production Sources

- **BIS bilateral exchange rates (`WS_XRU`)**, daily, local currency per USD, fetched from the BIS SDMX API. Used for 1970-1998 only.
- **ECB euro foreign exchange reference rates**, the complete history file `eurofxref-hist.zip`. Used from the first euro reference rate (1999-01-04) and for every daily update.

BIS states that the ECB is its primary source of recent daily data and that it releases updates weekly. A weekly release cannot keep a daily dataset inside the publication gate's five-day staleness limit, so the datasets read the ECB file directly from 1999. The builder verifies that this does not change the values: over the 259 common observation days in 1999, the inverse BIS rate and the ECB rate or cross agree within a relative difference of 8.0e-7 for all three pairs, which is the rounding of the six-decimal BIS quote. A separate check on 2026-11-14 found the BIS AUD series identical to the ECB cross at six decimals on all 7,133 common days from 1999-01-04 to 2026-11-10.

## Build Method

1. Fetch the BIS series for 1969-12-01 to 1999-12-31 in three decade-long requests and cache the combined CSV under `sources/raw/`. Single long requests have arrived truncated; each chunk must start and end within ten days of its requested range. Days BIS marks `NaN` are dropped.
2. Fetch the ECB history file and compute USD per unit: the USD rate itself for EUR, and the USD rate divided by the currency's rate for AUD and GBP. A day on which either leg is `N/A` produces no row.
3. For 1970-01-02 through 1998-12-31, take the inverse of the BIS rate.
4. **AUD in 1970 (modeled).** BIS has no daily AUD observation before 1971-01-04. The Australian dollar was pegged to sterling until December 1971, so USD per AUD is the observed daily BIS sterling rate divided by a fixed AUD-per-GBP ratio. The ratio is the median of the observed daily AUD/GBP ratio from 1971-01-04 to 1971-06-30 (2.1514; the 125 daily ratios in that window range from 2.1512 to 2.1550, and the builder rejects a spread above 0.3%). The 251 modeled rows therefore have exactly the daily returns of GBPUSD and lie between USD 1.107 and USD 1.120 per AUD.
5. Append the ECB series from 1999-01-04.
6. Check the 1999 BIS/ECB overlap (at least 200 days, relative difference at most 1e-5), reject any daily move above 25%, and require sorted unique dates starting on 1970-01-02.
7. Set `Adj Close` equal to `Close` and compute returns from the stored ten-decimal levels.

## Update Method

The ordinary update starts from the committed processed CSV and reads only the ECB history file. It takes the last committed row more than 14 days before the committed end as an anchor, requires that row to be in the ECB segment and to match the freshly downloaded ECB value within 1e-9, and recalculates every later row. Levels come straight from the source rather than from compounded returns, so an unchanged source reproduces the file byte for byte. The update fails without writing if the ECB file would drop a committed date, disagrees at the anchor, or has no observation within five days of the target date.

`scripts/check_daily_diff.py` then rechecks the saved ECB response independently: the last row must be the latest ECB date on or before the target, recent dates must equal the ECB calendar, and each examined rate must equal the ECB value.

`--full-rebuild` runs the historical builder, reusing the cached BIS files; `--refresh-historical-sources` refetches them.

## Tests

`tests/validation/test_fx_rates_contract.py` checks, for each pair: schema, the 1970-01-02 start, sorted unique weekday dates with no gap above ten days and at least 240 rows in every complete year, spot-only columns, level bounds, return arithmetic, the segment flags above (251 modeled rows for AUD, none elsewhere), quote direction against dated events (the November 1976 and March 1983 AUD devaluations, the Plaza Accord, the November 1978 dollar rescue, the 2016 EU referendum and the 1992 ERM exit), splice continuity at 1971-01-04 and 1999-01-04, that modeled 1970 AUD returns equal GBPUSD returns, and CSV/Parquet/metadata agreement.

`tests/automation/test_fx_rates.py` checks ECB parsing and crosses, catch-up and repeat-run stability, the publication gate, fail-closed behavior, an in-window revision, and the 1970 peg model and splice check on synthetic inputs.

## Caveats

- **Timing.** ECB reference rates are set around 14:15 CET, several hours before the U.S. close used by the asset datasets. Converting a USD asset to another currency day by day therefore mixes observation times. The effect averages out over longer horizons but distorts single-day converted returns. The ECB describes the rates as published for information purposes only.
- **Pre-1999 fixing unknown.** BIS does not state a fixing time for its older daily observations; it names the Bundesbank and IMF International Financial Statistics as main historical sources. The series label is "average of observations through period".
- **EUR before 1999 is a proxy.** There was no euro. The German series is the Deutsche Mark converted at the irrevocable 1.95583 rate, a common convention. BIS also publishes a euro-area series from 1974-06-28 whose pre-1999 values differ slightly; how it is constructed was not established, and it is not used.
- **AUD in 1970 is modeled.** It assumes the sterling peg held daily as it did in early 1971. The calibrated ratio of 2.1514 is about 0.4% above the official cross parity of 2.1429 (USD 2.40 per GBP over USD 1.12 per AUD); the reason was not established, and the ratio was chosen to join the observed 1971 series without a step. BIS monthly data show the official par of USD 1.12 throughout 1970.
- **Managed rates are real.** AUD moves in steps during 1972-1976 and all three rates are nearly flat before August 1971, reflecting pegs rather than missing data. The ten-day gap ending 1971-08-23 is the market closure after the U.S. suspended gold convertibility.
- **Not independently cross-validated.** FRED H.10 series and RBA historical rates would be natural checks; both downloads failed from the build machine on 2026-11-14 (connection failure and HTTP 403).
- **Redistribution.** See `sources/citations/fx_rates.md`; both sources require attribution and BIS limits some commercial use.
