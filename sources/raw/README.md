# Raw Sources

Downloaded source files are local caches for builds and validation.
They are intentionally excluded from the public release by default because
source terms can differ from the terms for the generated datasets.

Each local raw file must have a matching manifest under sources/manifests/
that records source URL, retrieval date, coverage period, license notes, and
checksum when available. Publish a raw file only after its source terms have
been reviewed and explicitly permit redistribution.

Ordinary refreshes create fresh delivery evidence under `incremental/` without
needing historical raw caches. Source records are stored in each dataset's
`sources/manifests/*_build.json` under `incremental_update.recent_sources`.

CPI records exactly the accepted route for that update:

| Record key | Cached response under `sources/raw/incremental/` |
|---|---|
| `BLS_CUSR0000SA0` | `cpi_bls_recent.json` |
| `FRED_CPIAUCSL` | `cpi_fred_recent.csv` |
| `FRED_CPIAUCSL_TABLE` | `cpi_fred_recent.html` |

The CPI record includes the actual URL, series ID, SHA-256, retrieval timestamp,
requested end date, observed coverage, and fallback reason when applicable.
The publication gate reads that recorded route, not whichever old cache happens
to exist. All routes still require a fresh live fetch. The dataset's top-level
BLS source identifies the origin of the CPI observations; the incremental
record identifies their delivery route. See the
[operations guide](../../docs/operations/daily-refresh.md).
