from __future__ import annotations

from pathlib import Path

import pytest

PUBLIC_RAW_SKIP_REASON = (
    "This test needs a downloaded raw source cache that is intentionally not "
    "published by default. Run it in a data-enabled checkout after retrieving "
    "the source described by its manifest."
)

REQUIRED_RAW_BY_TEST = {
    "test_broad_commodities_contract.py::test_broad_commodities_scaffold_paths_exist": Path(
        "sources/raw/broad_commodities_gsci_tr_macromicro.csv"
    ),
    "test_global_bonds_contract.py::test_global_bonds_basket_weights_are_economically_sane": Path(
        "sources/raw/global_bonds_jst_macrohistory_r6.xlsx"
    ),
    "test_global_bonds_contract.py::test_global_bonds_early_segment_anchors_to_jst_annual_returns": Path(
        "sources/raw/global_bonds_jst_macrohistory_r6.xlsx"
    ),
    "test_global_short_term_bonds_contract.py::test_glstbond_basket_weights_are_economically_sane": Path(
        "sources/raw/global_short_term_bonds_jst_macrohistory_r6.xlsx"
    ),
    "test_global_stocks_contract.py::test_global_stocks_ff_segment_matches_raw_fama_french_developed_returns": Path(
        "sources/raw/Developed_3_Factors_Daily_CSV.zip"
    ),
    "test_global_stocks_contract.py::test_global_stocks_vt_segment_matches_raw_vt_adjusted_returns": Path(
        "sources/raw/global_stocks_yahoo_vt_chart.json"
    ),
    "test_intermediate_term_us_treasury_contract.py::test_intermediate_treasury_has_fed_modelled_pre_vfitx_segment": Path(
        "sources/raw/intermediate_term_us_treasury_fed_nominal_yield_curve.csv"
    ),
    "test_long_term_us_treasury_contract.py::test_long_term_treasury_has_fed_modelled_pre_vustx_segment": Path(
        "sources/raw/long_term_us_treasury_fed_nominal_yield_curve.csv"
    ),
    "test_short_term_us_treasury_contract.py::test_short_treasury_has_fed_modelled_pre_vfisx_segment": Path(
        "sources/raw/short_term_us_treasury_fed_nominal_yield_curve.csv"
    ),
}


def pytest_collection_modifyitems(config, items):
    del config
    skip_missing_raw = pytest.mark.skip(reason=PUBLIC_RAW_SKIP_REASON)
    for item in items:
        key = f"{Path(str(item.fspath)).name}::{item.name}"
        required_raw = REQUIRED_RAW_BY_TEST.get(key)
        if required_raw is not None and not required_raw.is_file():
            item.add_marker(skip_missing_raw)
