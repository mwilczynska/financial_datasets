"""The committed companion contract is validated even without raw-source caches."""

from pathlib import Path

from src.distribution_validation import check_distributions


def test_published_cash_companions_match_all_canonical_histories_and_hashes():
    result = check_distributions(Path(__file__).resolve().parents[2])
    assert result["assets"] == 13
    assert result["fund_events"] > 1500
