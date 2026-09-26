"""Regression checks for fixed historical inputs shared by dataset builders."""

import json

import pytest

from src.historical_sources import (
    load_historical_source,
    read_json,
    validate_dated_rows,
    validate_yahoo_chart,
    write_json,
)


def _validate(payload):
    validate_dated_rows(payload["rows"], "2000-01-03", "2000-01-05", 3)


def _good_payload():
    return {"rows": [
        {"Date": "2000-01-03", "Close": 100},
        {"Date": "2000-01-04", "Close": 101},
        {"Date": "2000-01-05", "Close": 102},
    ]}


def test_valid_historical_cache_never_fetches(tmp_path):
    path = tmp_path / "source.json"
    write_json(path, _good_payload())
    calls = []

    def fetch():
        calls.append(True)
        raise RuntimeError("endpoint unavailable")

    payload, mode = load_historical_source(path, read_json, write_json, _validate, fetch)
    assert mode == "cached"
    assert payload == _good_payload()
    assert not calls


def test_failed_refresh_retains_valid_cache_and_invalid_cache_fails(tmp_path):
    path = tmp_path / "source.json"
    write_json(path, _good_payload())
    before = path.read_bytes()

    def fetch():
        raise RuntimeError("404 Not Found")

    _, mode = load_historical_source(path, read_json, write_json, _validate, fetch, refresh=True)
    assert mode == "cached_after_fetch_error"
    assert path.read_bytes() == before

    path.write_text(json.dumps({"rows": [{"Date": "2000-01-03", "Close": 100}]}), encoding="utf-8")
    with pytest.raises(RuntimeError, match="no valid cache"):
        load_historical_source(path, read_json, write_json, _validate, fetch)


def test_missing_cache_fetches_and_validates_before_write(tmp_path):
    path = tmp_path / "source.json"
    payload, mode = load_historical_source(path, read_json, write_json, _validate, _good_payload)
    assert mode == "fetched"
    assert read_json(path) == payload


def test_historical_chart_rejects_wrong_symbol_and_gaps():
    payload = {"chart": {"result": [{"meta": {"symbol": "OLD"}}]}}
    rows = _good_payload()["rows"]
    with pytest.raises(ValueError, match="symbol"):
        validate_yahoo_chart(payload, "EXPECTED", lambda _: rows, "2000-01-03", "2000-01-05", 3)

    payload["chart"]["result"][0]["meta"]["symbol"] = "EXPECTED"
    long_gap = [
        {"Date": "2000-01-03", "Close": 100, "Adj Close": 100},
        {"Date": "2000-01-20", "Close": 101, "Adj Close": 101},
    ]
    with pytest.raises(ValueError, match="gap"):
        validate_yahoo_chart(payload, "EXPECTED", lambda _: long_gap, "2000-01-03", "2000-01-20", 2)
