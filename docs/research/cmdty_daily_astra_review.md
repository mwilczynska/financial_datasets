# Independent Astra review: CMDTY daily reconstruction

Review date: 2026-09-30. This reviews the completed research report, calculation
script, findings JSON, source inventory, existing CMDTY methodology, and
production builder. Production data and the main report were not modified by
this review. Findings below describe the research snapshot presented for review;
subsequent author amendments should be assessed against these findings.

**Decision: viable research approach; not ready for a production replacement.**
Individual delivery prices are the right route to recover actual daily market
information. The acquired archives establish meaningful pre-1984 coverage, but
neither a complete historical GSCI portfolio nor its daily total return has yet
been reconstructed and independently validated. The report is appropriately
explicit about this limitation. Its most consequential empirical correction is
the treatment of missing dates in the endpoint experiment.

1. **High priority: preserve the real calendar before constructing endpoint
   constraints.** In `scripts/research_cmdty_daily.py`, `dropna()` occurs before
   the validation target is divided into 40-row blocks. Summing the surviving
   one-day log returns does not reproduce returns between actual observed index
   levels when intervening days have been removed. In 1990 the full Yahoo spot
   path returns **+6.14%**, whereas the retained 245-day pseudo-path returns
   **-3.40%**. Excluded observations include 1990-11-23 (+3.68%) and 1990-12-26
   (+2.31%). Thus the published numbers are reproducible complete-case
   diagnostics, but are materially invalid as a test that hides a real observed
   path behind its actual endpoints. The report discloses excluded rows and
   synthetic endpoints; it should also explain this consequence or repair the
   experiment.

   I reproduced every reported multisector correlation and RMSE. I also kept
   all target dates, used the same fitted coefficients, supplied a zero
   predicted log return only on dates without a complete predictor set, and
   conditioned both methods on identical full-calendar endpoint changes:

   | Year | Complete / all dates | Full-calendar smoothing RMSE | Full-calendar daily bridge RMSE | Reduction |
   |---|---:|---:|---:|---:|
   | 1987 | 249 / 253 | 77.98 bp | 47.72 bp | 38.8% |
   | 1988 | 251 / 253 | 93.50 bp | 43.63 bp | 53.3% |
   | 1989 | 248 / 252 | 76.02 bp | 38.31 bp | 49.6% |
   | 1990 | 245 / 252 | 168.57 bp | 91.87 bp | 45.5% |

   This sensitivity preserves the qualitative finding. The zero prediction is
   an explicitly assumed fallback for this diagnostic, not an observed zero
   futures return or a recommended production treatment. A revised experiment
   should retain all target dates, state its fallback, record excluded or
   imputed inputs, and use a common calendar for grain and multisector
   comparisons. Distinguish exchange closures, permitted stale settlements, and
   genuinely absent records.

2. **High priority: keep the validated claim narrow.** The experiment demonstrates
   predictive daily information about 1987-1990 GSCI **spot** movements. It does
   not validate futures carry, collateral, 1970-1983 exposures, or improvement
   over the existing 1984-1991 spot-shaped CMDTY segment. Training precedes each
   test year, and predictor scaling uses training data, so I found no hidden
   train/test leakage in that regression. The endpoint bridge deliberately uses
   future values, however. All model selection, uncertainty estimates, and
   downstream trading-signal comparisons must preserve that distinction.
   High correlation with the target, together with the large 1990 volatility
   shortfall, is insufficient for production acceptance. The report's warning
   against promoting the incomplete regression should remain prominent.

3. **High priority: acquire the historically dominant exposure and identify the
   target before estimating weights.** The early cattle emphasis is supported
   by the cited research. The four-versus-five discrepancy is real: Erb and
   Harvey describe four initial contracts, whereas Bhardwaj and coauthors
   describe five and report 55% cattle in February 1970. Neither establishes the
   exact annual CPWs needed here. Do not silently select the convenient list.
   Retrieve historical membership, CPWs, contract substitutions, and the
   original back-calculation rules. A 1980s unrestricted regression cannot
   identify the 1970s portfolio; sparse aggregate returns cannot identify both
   missing cattle returns and flexible constituent weights. Moreover, the GSCI
   backfilled universe is itself retrospective, so reproducing it does not
   remove all selection bias from an early investable-history claim.
   [Erb and Harvey, p. 12](https://people.duke.edu/~charvey/Research/Working_Papers/W77_The_tactical_and.pdf),
   [Bhardwaj, Janardanan, and Rouwenhorst](https://www.sciencedirect.com/science/article/pii/S2405851320300349).

4. **Medium priority: separate a vendor's quotation history from a usable
   contract panel.** All 14 local ZIP hashes match the published inventory. The
   archive evidence is materially stronger than a catalog date, and the report
   correctly leaves settlement identity, upstream provenance, outliers, and
   derived-use permission unresolved. CSI's cattle entry explicitly lists
   settlement data beginning 1964-11-30, making it a strong acquisition lead.
   The early copper entry is specifically `MCU3`, **Copper 3-Month (Ring)**,
   beginning 1968-01-02. That does not establish a history of fixed prompt-date
   contracts: a rolling three-month quotation changes maturity each day and
   cannot alone supply the same-contract price changes required by the proposed
   P&L engine. Obtain the required prompt/curve or index-compatible data and
   confirm the historical reference-price convention. The report should make
   this distinction explicit before presenting CSI copper as a solved source
   route. [CSI commodity factsheet](https://apps.csidata.com/factsheets.php?type=commodity&format=csv).

5. **The central P&L and collateral reasoning is sound, with implementation work
   still required.** The two-contract diagnostic uses yesterday's holdings and
   same-contract changes, avoiding artificial cross-contract price jumps. The
   proposed portfolio formula requires positions and their capital denominator
   to evolve consistently; combining constituent returns with constant daily
   weights would not reproduce fixed annual production quantities. The current
   contract-month schedules agree with current S&P documentation, but are not
   evidence of historical roll rules. The stated auction-discount conversion,
   prior available rate, and nonbusiness-day accrual agree with the 2016 S&P
   reference guide. The generic and exact-index conventions must remain clearly
   distinguished. [S&P reference guide, pp. 3 and 10-11](https://www.spglobal.com/spdji/en/documents/methodologies/methodology-sp-gsci-quick-guide.pdf).

   The production collateral and boundary findings are legitimate. I reran the
   boundary example and obtained a level of 110 on January 9 although the
   target anchor is January 12. Exact-anchor bucketing also uses the following
   interval. The missing original anchor cache prevents measuring the actual
   historical distortion. Likewise, the 4.891 collateral sensitivity is not an
   official correction, and adding it to already TR-anchored early `Adj Close`
   would double count collateral. Treat these defects as separate work with
   return-level and splice checks when implementation begins.

6. **Medium priority: strengthen reproducibility before reuse.** Preserve a
   durable retrieval manifest for Yahoo, the CSI factsheet, and downloaded
   source pages as well as the ZIPs: URL, retrieval timestamp, hash, coverage,
   and price/permission qualifications. File modification time is not a reliable
   retrieval timestamp after files are copied or restored. Record the script,
   builder, and dependency versions used for the numerical baseline. The
   current script can silently omit unavailable non-grain archives or the Yahoo
   experiment; a claimed complete rerun should fail clearly when those required
   inputs are absent. The existing production documentation's absolute
   statements that free early daily data does not exist, and that growth ratios
   confirm the anchor's TR identity, should be corrected or linked to these new
   research qualifications.

The strongest next acquisition is a permitted, independently identified **daily
GSCI TR extract** for 1970-1991, together with the missing original anchor cache.
If that cannot be obtained, the highest-value constituent acquisition is
**live-cattle individual deliveries covering 1969-1991**, with a checked 1970
sample and an overlap sample. CSI is a concrete lead, not validated possession
of that data. Obtain historical weights and rules alongside the prices. A
manual third-party export would still require identity, frequency, coverage,
date, and value checks before it can change this decision.

Independent calculations are saved locally in ignored
`data/interim/cmdty_astra_audit.py` and `data/interim/cmdty_astra_audit.json`.
They read the acquired inputs and write only review diagnostics. No vendor was
contacted, no data was purchased, and no full 1970-1983 replacement is validated
by this review.

**Follow-up assessment, 2026-09-30: amended research and acquired daily TR.**

The amendments resolve the initial experiment's material calendar defect and
the copper-source and retrieval-provenance qualifications. The held-out target
now retains every observed index date; both predictor sets receive the same
endpoint calendar; unavailable predictions have an explicit diagnostic fallback.
The revised results agree with my independent full-calendar sensitivity above,
and recorded endpoint errors are approximately 1e-17. The recorded research
script and builder hashes match the files reviewed. The manifest now preserves
source hashes and coverage while honestly leaving unknown initial retrieval
timestamps null. I found no new material numerical error in these amendments.

The manually acquired TR export materially improves the evidence and narrows
the unsolved period. I independently parsed the snapshot with SHA-256
`4320308a7a5715337e28c2f601db19d14c3a67425ae9a7aae7cfe397d8fd5ad5`:
it contains 3,035 positive, finite levels, without duplicate dates or weekend
observations, from 1979-12-27 through 1991-12-31. Full calendar years contain
252-253 observations; the first partial year has three. Printed percentage
changes agree with price ratios to their stated precision. These are useful
internal consistency checks, rather than independent proof of the daily values.

I checked the transcriptions against the primary-document text. All 12 dated
early-January levels match the SEC-hosted historical GSCI TR table; the largest
CSV difference is 0.0041 index points, within its two-decimal rounding. All 12
annual returns match Kaplan and Lummer's Appendix A within rounding; the largest
difference is 0.004947 percentage points. Their preface and endnote 3 explicitly
identify Goldman Sachs' official TR series. These checks strongly support
**GSCI TR identity and scale**. The documents are separate publications of the
same underlying index history, not two independently constructed economic
benchmarks, and neither validates all 3,035 daily observations.
[SEC filing, pp. 29-30](https://www.sec.gov/rules/sro/nyse/2006/34-53658.pdf),
[Kaplan and Lummer, Appendix A and endnote 3](https://www.etf.com/docs/20040913_GSCI.pdf).

The report now correctly describes these as dated early-January observations:
the SEC table's 1985 reference is January 3 even though the CSV also contains
January 2. The SEC filing also explicitly identifies its pre-May-1991 history
as hypothetical. The export should retain a back-calculated-index designation;
it is stronger evidence than a fitted proxy, without becoming a contemporaneously
published or traded 1980 index portfolio.
[SEC filing, p. 29](https://www.sec.gov/rules/sro/nyse/2006/34-53658.pdf).

I independently reproduced the published-series comparisons:

| Period | Verified comparison |
|---|---|
| 1980-1983 | Downloaded TR volatility 13.5759% on its own calendar; common-interval TR volatility 13.6535% versus current CMDTY 2.6415%; correlation 0.18497 and log-return RMSE 84.5328 bp |
| 1984-1990 | Common-interval correlation 0.99035 and log-return RMSE 13.6899 bp; growth factors 3.26764 for downloaded TR and 3.03855 for current CMDTY |
| 1984-1990 normalized levels | Current/downloaded endpoint ratio 0.929892, or current CMDTY 7.0108% below the downloaded series after common-start normalization |

The amended comparison aligns **levels before differencing**, so unmatched
observations are aggregated into the enclosing return interval. This fixes the
previously identified loss of cumulative target movements. Fourteen TR dates
and two current-series dates are unmatched during 1980-1983; one TR date is
unmatched during 1984-1990. Consequently, common-interval statistics should
remain labeled as such; they are not exclusively consecutive single-index-day
statistics. The source's own daily volatility and the paired-calendar volatility
are slightly different, as shown above. The 7.01% relative endpoint discrepancy
is verified, but it does not identify its cause or prove every intervening
source value correct. The missing original anchor cache still limits causal
diagnosis of that discrepancy.

**Updated decision: the amended research supports the proposed two-part
implementation route.** The acquired TR is the preferred candidate for returns
from 1979-12-28 onward, with December 27 supplying the initial overlap level.
The report's splice clarification and inverse collateral formula are correct
under the cited collateral convention. Do not add collateral to the acquired
TR again; recovering ER remains a separate problem if the historical auction
rates and conventions are unavailable.

Missing constituent weights do **not** prevent adopting an adequately validated
direct TR source for this later segment. They remain essential to the earlier
constituent reconstruction and to independent portfolio replication. Before
production promotion, check daily samples across years, roll windows, unusual
calendar dates, and large moves against another daily source, establish the
applicable source-use terms, and validate the implemented splices and ER
calculation. The full 1970-1991 replacement is still not production-ready; the
research recommendation itself is now supported more strongly and concretely.

The highest-value missing direct acquisition is now **1970-1979 daily GSCI TR**.
If unavailable, cattle deliveries and historical weights/rules remain the
highest-value constituent work for the 1970s, with the acquired 1980s TR serving
as a validation overlap. Source metadata and reference checks should be carried
into implementation. A production importer should explicitly require finite
values and all expected reference checks; the research code's conditional
reference selection should not allow a shortened future file to pass silently.
The particular reviewed snapshot contains every required reference date and
passes those checks.

Follow-up calculations are preserved locally in ignored
`data/interim/cmdty_astra_followup.py` and
`data/interim/cmdty_astra_followup.json`. This follow-up changed only the separate
review and ignored review diagnostics; it did not modify the main report,
research script, or production data.
