"""Consumers obtain precise dollars and separate actual from modeled timing."""

from decimal import Decimal as D
from pathlib import Path

import pytest

from examples.usd_distributions import fund_position, synthetic_position

ROOT = Path(__file__).resolve().parents[2]


def test_issuer_precision_reaches_fund_position_in_both_formats():
    csv = fund_position(ROOT, "SHY", D(100), "2025-12-18", "2025-12-31", ".csv")
    parquet = fund_position(ROOT, "SHY", D(100), "2025-12-18", "2025-12-31")
    assert csv == parquet
    assert D(csv["cash_entitlement_usd"]) == D("25.4847")
    assert D(csv["cash_paid_by_end_on_verified_dates_usd"]) == D("25.4847")


def test_synthetic_position_accounts_for_cash_once_in_both_formats():
    csv = synthetic_position(ROOT, "GLBOND", D(10000), "2025-01-02", "2025-12-31", ".csv")
    parquet = synthetic_position(ROOT, "GLBOND", D(10000), "2025-01-02", "2025-12-31")
    assert csv == parquet
    assert abs(D(csv["cash_entitlement_usd"]) - D(csv["receivable_usd"]) -
               D(csv["cash_paid_on_verified_dates_usd"]) - D(csv["cash_paid_on_modeled_dates_usd"])) < D("0.000000001")


def test_unavailable_fund_does_not_become_zero_cash():
    with pytest.raises(ValueError, match="Unknown fund"):
        fund_position(ROOT, "MISSING", D(100), "2025-12-18", "2025-12-31")
