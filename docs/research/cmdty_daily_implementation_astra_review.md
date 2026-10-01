# Independent Astra Max review: CMDTY daily GSCI implementation

Review date: 2026-09-30. Reviewed the local migration, including
[the builder](../../src/build_broad_commodities.py),
[the pinned source loader](../../src/gsci_daily.py),
[migration tests](../../tests/automation/test_cmdty_gsci_migration.py),
[production contract tests](../../tests/validation/test_broad_commodities_contract.py),
and [the build manifest](../../sources/manifests/broad_commodities_build.json).

**Decision: the authorized local migration passes this review.** The current
outputs correctly import the selected GSCI ER/TR levels, preserve the existing
calendar and later returns, and agree across CSV and Parquet. The concrete
failure-handling issues found during review have been repaired. No remaining
material correctness issue was found in the reviewed scope.

I independently read the raw workbook, obtained the pre-migration CSV directly
from Git, and compared every output row without importing the migration code.
The baseline is commit `20396a64b4203cb9d06b4d096e473f268a57684b`, with CSV SHA-256
`d31df07d79f778ce48069c383342e2784d837c4d3dfbd58da921b4685f8856d7`.
Its archived bytes match Git exactly. The imported workbook matches the
previously reviewed commit `f5ecf1507fb9cc98ffcc1f69c217793f5f9272a3` and SHA-256
`918e4046300180e0274781bfa6f1f5dcf2dc7df61b9229f9d4a9ea124da2a9f8`.

| Check | Independent result |
|---|---|
| Early source levels | All 5,255 `Close` values equal normalized source ER and all 5,255 `Adj Close` values equal normalized source TR exactly |
| Calendar | All 14,228 dates equal the baseline dates, from 1970-01-02 through 2026-09-28; the preserved early-calendar file also matches |
| Early return calculation | Returns use consecutive selected levels; maximum rounding error is below 5e-11 for both columns |
| Skipped and flat dates | Growth across 224 unselected source weekdays is retained in consecutive selected-level ratios; all nine selected flat ER/TR intervals are retained |
| Later returns | All 17,946 return-field cells across 8,973 later rows are unchanged as strings |
| Later level ratios | Maximum differences from baseline are 2.6723531e-13 for `Close` and 4.3118752e-14 for `Adj Close`, below the 1e-10 gate |
| CSV and Parquet | Every date, numeric value, text field and missing value agrees exactly; both file hashes match the manifest |
| Segment counts | 5,255 GSCI, 3,781 BCOM and 5,192 DBC rows, matching the manifest |

The two splice rows preserve each incoming segment's baseline return separately:

| Return date | Prior date | Price return | Total return |
|---|---|---:|---:|
| 1991-01-03 | 1991-01-02 | -0.9100036621% | -0.8925203859% |
| 2006-02-07 | 2006-02-06 | -2.8925650449% | -2.8925536438% |

The new January 2, 1991 endpoints are ER **458.48** and TR **2346.026**.
The later `Close` and `Adj Close` paths have separate scale factors, approximately
0.6168038423 and 1.0645832735. No early IRX stripping, added collateral, or old
sparse-anchor constraint enters the imported values. The migration preserves
the existing BCOM collateral model and DBC return definitions.

The reviewed CSV SHA-256 is
`b9d2d29988a7f36f61a58d2c3458d50e623375beae818955104dabe6b8e34ceb`;
the Parquet SHA-256 is
`ffbbaac959a8750c688900ac71f9517fc3137e0d67f7da544cdc41a297a273c9`.
These outputs remained unchanged during the independent review.

Three implementation findings were addressed:

1. **Partial output replacement.** Originally, failure replacing the final
   Parquet or manifest could leave files from different generations. I reproduced
   both failures in isolated scratch directories. The revised writer stages and
   validates the files first, then restores the prior artifacts if final
   replacement fails. Repeating both cases restored all three originals
   byte-for-byte. If restoration itself fails, recovery copies are retained and
   their paths are reported; the corresponding regression test passes.
2. **Baseline change after reading.** Originally, migration could calculate from
   an old CSV and subsequently guard against a newer version's hash, overwriting
   that newer data. The implementation now parses one captured byte snapshot,
   binds metadata and the Git archive to its original hash, and checks that hash
   again before applying outputs. My simulated newer six-row baseline is now
   rejected as a migration input change and preserved intact.
3. **Full-build contract mismatch.** Migration-specific tests originally required
   a migration record even after a normal raw-source full build. They now require
   BCOM/IRX/DBC provenance for that alternative build path and skip only the
   inapplicable migration-baseline comparisons. Direct-source, arithmetic,
   calendar and applicable raw-cache checks remain in place.

The focused migration, production-contract and incremental-update checks passed
**32 tests**, with **two skips** for unavailable historical BCOM/DBC chart caches.
The pinned loader enforces source size and hash, schema, ordered complete weekday
coverage, finite positive levels, initial normalization and all 44 published
reference checks. The independent reference transcriptions and upstream source
checks are documented in the [research review](cmdty_full_history_astra_review.md).
Regression coverage includes skipped-date growth, flat rows, separate splice
columns, missing/duplicate/invalid inputs, repeated migration, source rejection,
staging failures, replacement failures and changed-baseline rejection.

Later-history verification establishes preservation of the committed baseline.
It does not newly authenticate those BCOM/DBC returns against vendor feeds; the
manifest explicitly records that distinction. A complete fresh rebuild against
live historical feeds was not performed in this review.

The source and output labels correctly describe an author-claimed Bloomberg
extraction, previous-value fill on non-trading weekdays, and provider
back-calculation before May 1, 1991. These are not contemporaneously published
1970s index observations or a DBC-equivalent portfolio. Upstream authentication
and vendor/derived redistribution rights remain unverified. Those are source
and future-publication limitations, not a claim of licensing clearance for this
authorized local migration.

This review did not modify production data, raw inputs, implementation code or
tests. Independent diagnostics and fault-injection fixtures remain in ignored
`data/interim/`; this document is the review's durable output.

**Formatting addendum, 2026-09-30.** The final CSV and frozen calendar use LF
record endings. Reinstating CRLF reproduces their previously reviewed hashes
exactly, and independently parsed cells and dates are unchanged: 14,228 dataset
rows and 5,255 calendar rows. The final CSV SHA-256, superseding the CSV
fingerprint above, is
`6fd799eaac01d2a31bceebc1936bf2e6b501e91fb43a7fa89ec10c3b458f52f2`.
The final calendar SHA-256 is
`22c8176d209ce07481e7adab51af1dce3472873228a2718a74ceacece3e3b630`.
Both manifests match these fingerprints. The Parquet bytes and SHA-256 remain
unchanged. The CSV writers explicitly emit LF, and Git attributes preserve the
calendar bytes and enforce LF for the CMDTY output. The review conclusion is
unchanged; this follow-up contains no substantive data change.
