# Broad commodities source notes

Accessed: 2026-09-30 for the direct daily GSCI snapshot and corroborating sources.
The implemented dataset replaces the old early reconstruction; redistribution
rights remain unverified.

## Direct daily GSCI ER/TR, 1970-01-02–1991-01-02

- Source: [Trading_Commo public university project](https://github.com/yessinemx/Trading_Commo).
- [Pinned workbook](https://raw.githubusercontent.com/yessinemx/Trading_Commo/f5ecf1507fb9cc98ffcc1f69c217793f5f9272a3/data/GSCI_Data.xlsx), commit `f5ecf1507fb9cc98ffcc1f69c217793f5f9272a3`.
- SHA-256: `918e4046300180e0274781bfa6f1f5dcf2dc7df61b9229f9d4a9ea124da2a9f8`; 442,834 bytes.
- Local cache: `sources/raw/broad_commodities_gsci_daily.xlsx`, excluded from release by default.
- Observed coverage: 14,609 ordered weekday rows, 1970-01-02–2025-12-31,
  in sheet `Données GSCI`, with Spot, ER and TR columns.
- Use: import `GSCI_ER` into Close and `GSCI_TR` into Adj Close,
  normalize each separately, and sample on 5,255 preserved CMDTY dates
  through 1991-01-02. Spot is a corroborating companion, not the return driver.

The [companion configuration](https://github.com/yessinemx/Trading_Commo/blob/f5ecf1507fb9cc98ffcc1f69c217793f5f9272a3/config.py)
and [notebook](https://github.com/yessinemx/Trading_Commo/blob/f5ecf1507fb9cc98ffcc1f69c217793f5f9272a3/notebook/main.ipynb)
were inspected as text. They request Bloomberg index tickers and daily
`PX_LAST`, with `NON_TRADING_WEEKDAYS` / `PREVIOUS_VALUE` fill.
That is author-supported provenance, not authentication of a terminal export.
Holiday values may be carried. The
[S&P GSCI index page](https://www.spglobal.com/spdji/en/indices/commodities/sp-gsci/)
and research references identify May 1, 1991 as the launch; the entire imported
segment is provider back-calculated history.

Corroboration and hash-enforced acquisition are recorded in the
[follow-up research](../../docs/research/cmdty_daily_1970s_followup.md),
[retrieval manifest](../../docs/research/cmdty_full_history_retrieval_manifest.json),
and [Astra Max review](../../docs/research/cmdty_full_history_astra_review.md):

- All 2,607 1970s TR dates agree with a separately delivered public portfolio
  database within floating-point precision. Upstream independence is unknown.
- All 120 monthly Spot, ER and TR values in the 1970s match the older
  [Duke/Goldman workbook](https://people.duke.edu/~charvey/Teaching/BA453_2005/GSCI_0406.xls):
  360 exact matches. Its weight worksheet is unsuitable for a constituent rebuild.
- All 22 annual TR returns from
  [Kaplan/Lummer Appendix A, PDF page 13](https://www.etf.com/docs/20040913_GSCI.pdf)
  and all 22 dated levels in
  [SEC Release 34-53658, PDF pages 29–30](https://www.sec.gov/files/rules/sro/nyse/2006/34-53658.pdf)
  pass published rounding. These 44 gates run when the production workbook is loaded.
- The user-supplied Investing TR export contains 3,035 common dates,
  1979-12-27–1991-12-31, with maximum level difference 0.001.
  Quantpedia corroborates its overlapping delivery. Neither reaches the early 1970s.

Daily ER has less external daily corroboration than TR. These comparisons
identify and corroborate the same underlying history; they do not reconstruct
an independent daily benchmark. The original Bloomberg extraction and rights
remain unverified. Public downloadability and any repository code license do
not grant redistribution rights to vendor data or derived outputs.

## Preserved BCOM/IRX/DBC history and active DBC updates

The migration preserves ratios from the versioned processed baseline:
Git `20396a64b4203cb9d06b4d096e473f268a57684b`, CSV SHA-256
`d31df07d79f778ce48069c383342e2784d837c4d3dfbd58da921b4685f8856d7`.
The old complete Yahoo chart caches are absent from this checkout. No later
vendor observations were newly verified during this migration. An identical
local archive and exact per-column scaling/splice checks are recorded in build metadata.

- [Yahoo BCOM chart](https://query1.finance.yahoo.com/v8/finance/chart/%5EBCOM):
  excess-return proxy, 1991-01-03–2006-02-06, with January 2 overlap.
  The index type was inferred from annual-return behavior, not authenticated
  official metadata. Its live endpoint returned 404 in September 2026.
- [Yahoo IRX chart](https://query1.finance.yahoo.com/v8/finance/chart/%5EIRX):
  annualized 13-week T-bill percentage rate, forward-filled. BCOM TR uses
  `1 + IRX / 100 / 365` per observation. The existing approximation does
  not accrue extra collateral across skipped calendar days. IRX is not applied
  to the direct GSCI segment.
- [Yahoo DBC chart](https://query1.finance.yahoo.com/v8/finance/chart/DBC):
  ETF price/adjusted-close returns from 2006-02-07, with February 6 overlap.
  Ordinary updates request only recent DBC history. This is fund net return,
  affected by expenses, distributions and Yahoo adjustments, not gross DBIQ return.

A raw-source full rebuild still needs valid permitted BCOM/IRX historical
caches. Cache identity, required overlap coverage, finite values and dates are
validated before use. Failed forced refreshes preserve valid caches.

## Superseded sources and enduring qualifications

MacroMicro's sparse GSCI TR republication and Yahoo SPGSCI's spot-shape overlay
are retired from the active build. Their smoothing, interval-overlay boundary
bias and IRX-derived ER are documented in the historical research.
The earlier World Bank monthly spot model, LBMA metals fill, and equal-weighted
AQR alternative remain superseded or rejected candidates.

GSCI is production-weighted and has different constituent weights and roll
rules from DBC. BCOM changes the benchmark family in 1991; DBC changes it
again in 2006. Numerical continuity does not create identical economic exposure.
Pre-launch back-calculation and weekday filling remain explicit row labels.
See [the implemented methodology](../../docs/methodology_cmdty.md) and
[DATA_LICENSE.md](../../DATA_LICENSE.md) before any redistribution.
