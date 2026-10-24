"""CPI outage recovery must retain BLS levels, history, and publication evidence."""

from __future__ import annotations

import hashlib
import json
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
import requests

from src import build_cpi_inflation as cpi
from src import cpi_sources
from src import incremental_update as update
from scripts import check_daily_diff as gate


# February is intentionally unpublished, like October 2025 in the real series.
MONTHLY = [(date(2026, 1, 1), 300.0), (date(2026, 3, 1), 310.0),
           (date(2026, 4, 1), 320.0), (date(2026, 5, 1), 321.0), (date(2026, 6, 1), 322.0)]
FRED_CSV = ("observation_date,CPIAUCSL\n2026-01-01,300\n2026-02-01,.\n2026-03-01,310\n"
            "2026-04-01,320\n2026-05-01,321\n2026-06-01,322\n2026-07-01,323\n")
TARGET = date(2026, 7, 16)
FRED_TABLE = ("<table><tr><th>Series ID</th><td>CPIAUCSL</td></tr>"
              "<tr><th>Source</th><td>U.S. Bureau of Labor Statistics</td></tr>"
              "<tr><th>Seasonal Adjustment</th><td>Seasonally Adjusted</td></tr>"
              "<tr><th>Frequency</th><td>Monthly</td></tr>"
              "<tr><th>Units</th><td>Index 1982-1984=100</td></tr></table>"
              "<table><tr><th>DATE</th><th>VALUE</th></tr>"
              + "".join(f"<tr><td>{line.split(',')[0]}</td><td>{line.split(',')[1]}</td></tr>"
                        for line in FRED_CSV.splitlines()[1:]) + "</table>")


def bls_payload() -> dict:
    return {"status": "REQUEST_SUCCEEDED", "Results": {"series": [{"seriesID": cpi.BLS_SERIES, "data": [
        {"year": str(day.year), "period": f"M{day.month:02}", "value": str(value)}
        for day, value in MONTHLY + [(date(2026, 7, 1), 323.0)]
    ]}]}}


class Session:
    def __init__(self, *, body=None, post_error=None, content=FRED_CSV, get_error=None,
                 csv_error=None, table_content=FRED_TABLE):
        self.body, self.post_error, self.content, self.get_error = body, post_error, content, get_error
        self.csv_error, self.table_content = csv_error, table_content
        self.get_calls = 0

    def post(self, *args, **kwargs):
        if self.post_error is not None:
            raise self.post_error
        response = requests.Response()
        response.status_code = 200
        response._content = json.dumps(self.body).encode()
        return response

    def get(self, *args, **kwargs):
        self.get_calls += 1
        if self.get_error is not None:
            raise self.get_error
        if args[0] == cpi_sources.FRED_URL and self.csv_error is not None:
            raise self.csv_error
        response = requests.Response()
        response.status_code = 200
        response._content = (self.table_content if args[0] == cpi_sources.FRED_TABLE_URL else self.content).encode()
        return response


@pytest.fixture
def baseline(tmp_path: Path):
    processed = tmp_path / "data/processed"
    manifests = tmp_path / "sources/manifests"
    processed.mkdir(parents=True)
    manifests.mkdir(parents=True)
    rows, previous = [], None
    day = date(2026, 1, 1)
    while day <= date(2026, 7, 15):
        level, flag, notes = cpi.daily_cpi_level(day, MONTHLY)
        value = cpi.round_float(level)
        daily_return = "" if previous is None else cpi.round_float(level / previous - 1)
        rows.append({"Date": day.isoformat(), "Open": "", "High": "", "Low": "", "Close": value,
                     "Adj Close": value, "Volume": "", "Price Return": daily_return, "Total Return": daily_return,
                     "Source": cpi.SOURCE, "Quality Flag": flag, "Source Notes": notes})
        previous = level
        day += timedelta(days=1)
    path = processed / "cpi_inflation.csv"
    update.write_rows(path, rows)
    update.write_parquet(path, path.with_suffix(".parquet"))
    metadata = {"latest_monthly_observation": "2026-06-01", "row_count": len(rows),
                "first_date": rows[0]["Date"], "last_date": rows[-1]["Date"], "csv_sha256": update.checksum(path)}
    (manifests / "cpi_inflation_build.json").write_text(json.dumps(metadata), encoding="utf-8")
    return tmp_path, rows


def fingerprints(root: Path) -> dict:
    paths = [root / "data/processed/cpi_inflation.csv", root / "data/processed/cpi_inflation.parquet",
             root / "sources/manifests/cpi_inflation_build.json"]
    return {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}


def records(root: Path) -> dict:
    metadata = json.loads((root / "sources/manifests/cpi_inflation_build.json").read_text(encoding="utf-8"))
    return metadata["incremental_update"]["recent_sources"]


def check_publication(root: Path, original: list, monkeypatch):
    import io
    import csv
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=update.OUTPUT_COLUMNS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(original)
    monkeypatch.setattr(gate.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(stdout=stream.getvalue()))
    return gate.check_one(root, "HEAD", "cpi_inflation", TARGET)


@pytest.mark.parametrize("outage", [requests.exceptions.RetryError("too many 503 error responses"),
                                  requests.Timeout("BLS timed out"), requests.ConnectionError("BLS unavailable")])
def test_outage_catchup_passes_publication_without_rewriting_history(baseline, monkeypatch, outage):
    root, original = baseline
    session = Session(post_error=outage)
    assert update.update_asset("cpi_inflation", root, TARGET, session=session)
    result = update.read_rows(root / "data/processed/cpi_inflation.csv")
    assert [row for row in result if row["Date"] <= "2026-06-01"] == [row for row in original if row["Date"] <= "2026-06-01"]
    assert result[-1]["Date"] == TARGET.isoformat()
    assert next(row for row in result if row["Date"] == "2026-07-01")["Close"] == "323"
    assert next(row for row in result if row["Date"] == "2026-06-15")["Quality Flag"] == cpi.INTERPOLATED_FLAG
    assert next(row for row in result if row["Date"] == "2026-02-01")["Quality Flag"] == cpi.INTERPOLATED_FLAG
    assert session.get_calls == 1
    assert set(records(root)) == {"FRED_CPIAUCSL"}
    assert "2026-07-16" in check_publication(root, original, monkeypatch)


def test_primary_and_idempotent_response_refresh_pass_publication(baseline, monkeypatch):
    root, original = baseline
    body = bls_payload()
    session = Session(body=body)
    assert update.update_asset("cpi_inflation", root, TARGET, session=session)
    before = fingerprints(root)
    old_hash = records(root)["BLS_CUSR0000SA0"]["sha256"]
    body["responseTime"] = 123
    assert not update.update_asset("cpi_inflation", root, TARGET, session=session)
    after = fingerprints(root)
    assert all(before[path] == after[path] for path in before if not path.endswith(".json"))
    assert old_hash != records(root)["BLS_CUSR0000SA0"]["sha256"]
    assert session.get_calls == 0
    check_publication(root, original, monkeypatch)


def test_csv_outage_recovers_through_verified_public_table(baseline, monkeypatch):
    root, original = baseline
    session = Session(post_error=requests.exceptions.RetryError("BLS 503"), csv_error=requests.Timeout("CSV timeout"))
    assert update.update_asset("cpi_inflation", root, TARGET, session=session)
    assert session.get_calls == 2
    assert set(records(root)) == {"FRED_CPIAUCSL_TABLE"}
    check_publication(root, original, monkeypatch)


@pytest.mark.parametrize("wrong", [FRED_TABLE.replace("CPIAUCSL", "CPIAUCNS"),
                                  FRED_TABLE.replace("Seasonally Adjusted", "Not Seasonally Adjusted"),
                                  FRED_TABLE.replace("Index 1982-1984=100", "Percent Change")])
def test_public_table_requires_correct_series_definition(baseline, wrong):
    root, _ = baseline
    before = fingerprints(root)
    with pytest.raises(RuntimeError, match="incorrect CPI series"):
        update.update_asset("cpi_inflation", root, TARGET, session=Session(
            post_error=requests.exceptions.RetryError("503"), csv_error=requests.Timeout("CSV timeout"),
            table_content=wrong))
    assert fingerprints(root) == before


@pytest.mark.parametrize("content", [
    FRED_CSV.replace("CPIAUCSL", "CPIAUCNS"),
    FRED_CSV.replace("2026-05-01,321", "2026-05-01,999"),
    FRED_CSV.replace("2026-05-01,321\n", ""),
    FRED_CSV.replace("2026-06-01,322\n", ""),
    FRED_CSV + "2026-07-01,323\n",
    FRED_CSV.replace("2026-07-01", "2026-07-02"),
    FRED_CSV.replace("2026-07-01,323", "2026-07-01,nan"),
    FRED_CSV.replace("2026-07-01,323", "2026-07-01,inf"),
    FRED_CSV.replace("2026-07-01,323", "2026-07-01,0"),
    FRED_CSV.replace("2026-05-01,321", "2026-05-01,."),
    FRED_CSV.replace("2026-02-01,.", "2026-02-01,305"),
    "<html>Service unavailable</html>",
])
def test_untrusted_fallback_leaves_all_outputs_untouched(baseline, content):
    root, _ = baseline
    before = fingerprints(root)
    with pytest.raises((RuntimeError, ValueError)):
        update.update_asset("cpi_inflation", root, TARGET,
                            session=Session(post_error=requests.exceptions.RetryError("503"), content=content))
    assert fingerprints(root) == before


def test_both_routes_unavailable_leave_all_outputs_untouched(baseline):
    root, _ = baseline
    before = fingerprints(root)
    with pytest.raises(requests.ConnectionError, match="FRED unavailable"):
        update.update_asset("cpi_inflation", root, TARGET,
                            session=Session(post_error=requests.exceptions.RetryError("503"),
                                            get_error=requests.ConnectionError("FRED unavailable")))
    assert fingerprints(root) == before


def test_stale_fallback_is_rejected(baseline):
    root, _ = baseline
    before = fingerprints(root)
    with pytest.raises(RuntimeError, match="stale"):
        update.update_asset("cpi_inflation", root, date(2026, 11, 1),
                            session=Session(post_error=requests.exceptions.RetryError("503")))
    assert fingerprints(root) == before


def test_new_unconfirmed_gap_is_rejected(baseline):
    root, _ = baseline
    before = fingerprints(root)
    with pytest.raises(RuntimeError, match="missing new monthly"):
        update.update_asset("cpi_inflation", root, date(2026, 9, 16),
                            session=Session(post_error=requests.exceptions.RetryError("503"),
                                            content=FRED_CSV + "2026-09-01,325\n"))
    assert fingerprints(root) == before


@pytest.mark.parametrize("invalid", ["wrong_series", "failed_status", "forbidden"])
def test_primary_contract_errors_are_not_hidden_by_fallback(baseline, invalid):
    root, _ = baseline
    body = bls_payload()
    error = None
    if invalid == "wrong_series":
        body["Results"]["series"][0]["seriesID"] = "CUUR0000SA0"
    elif invalid == "failed_status":
        body["status"] = "REQUEST_FAILED"
    else:
        response = requests.Response()
        response.status_code = 403
        error = requests.HTTPError("Forbidden", response=response)
    session = Session(body=body, post_error=error)
    with pytest.raises((RuntimeError, requests.HTTPError)):
        update.update_asset("cpi_inflation", root, TARGET, session=session)
    assert session.get_calls == 0


def test_publication_rejects_tampered_raw_fallback(baseline, monkeypatch):
    root, original = baseline
    update.update_asset("cpi_inflation", root, TARGET, session=Session(post_error=requests.exceptions.RetryError("503")))
    (root / cpi_sources.SOURCE_FILES["FRED_CPIAUCSL"]).write_text(FRED_CSV.replace("323", "999"), encoding="utf-8")
    with pytest.raises(RuntimeError, match="hash"):
        check_publication(root, original, monkeypatch)


@pytest.mark.parametrize("field,value", [("path", "../other.csv"), ("url", "https://example.com/cpi"),
                                        ("series_id", "CPIAUCNS"), ("accessed_at_utc", "2026-01-01T00:00:00+00:00")])
def test_publication_rejects_untrusted_provenance(baseline, field, value):
    root, original = baseline
    update.update_asset("cpi_inflation", root, TARGET, session=Session(body=bls_payload()))
    source_records = records(root)
    source_records["BLS_CUSR0000SA0"][field] = value
    with pytest.raises(RuntimeError):
        cpi_sources.load_recent_monthly(root, source_records, TARGET, original)
