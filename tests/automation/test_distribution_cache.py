"""Failed deliveries cannot replace validated source evidence or become zero."""

import hashlib
from types import SimpleNamespace

import pytest
import requests

from src.distribution_sources import SourceCache


def test_offline_cache_is_verified_and_error_response_preserves_accepted_bytes(tmp_path):
    content = b'{"financial_fact": "0.123456"}'
    cache = SourceCache(tmp_path, offline=True)
    record = {"url": "https://example.test/facts", "sha256": hashlib.sha256(content).hexdigest(),
              "http_status": 200, "retrieved_at_utc": "2025-01-02T00:00:00+00:00"}
    cache.accept("issuer.json", content, record)
    assert cache.get("issuer.json", record["url"])[0] == content
    def rejected():
        raise requests.HTTPError("403 source delivery failure")
    response = SimpleNamespace(content=b"denied", status_code=403, url=record["url"], raise_for_status=rejected)
    session = SimpleNamespace(headers={}, get=lambda *args, **kwargs: response)
    live = SourceCache(tmp_path, session=session)
    with pytest.raises(requests.HTTPError):
        live.get("issuer.json", record["url"], refresh=True)
    assert not live.records["issuer.json"]["accepted"]
    assert cache.get("issuer.json", record["url"])[0] == content
    (cache.directory / "issuer.json").write_bytes(b"tampered")
    with pytest.raises(ValueError, match="checksum"):
        cache.get("issuer.json", record["url"])


def test_missing_offline_response_is_not_an_empty_history(tmp_path):
    with pytest.raises(FileNotFoundError):
        SourceCache(tmp_path, offline=True).get("missing.json", "https://example.test/facts")
