# Processed Data

Store final backtest-ready datasets here.

Each final dataset should have:

- A CSV file.
- A Parquet file.
- A source manifest under `sources/manifests/`.
- Validation coverage under `tests/validation/`.
- Documentation in docs/source_registry.md, the relevant methodology file, source manifest, and citation note.

The daily workflow publishes validated CSV/Parquet pairs, build metadata, and
the README coverage table together. Current dates come from those generated
artifacts rather than dated implementation snapshots in methodology notes.
Actual recent delivery provenance, including BLS or FRED for CPI, is recorded
in each build manifest. See the
[daily refresh operations guide](../../docs/operations/daily-refresh.md).
