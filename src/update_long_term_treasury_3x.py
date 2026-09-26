"""Incrementally update long_term_us_treasury_3x; use --full-rebuild for the historical builder."""

from incremental_update import main_for_asset


if __name__ == "__main__":
    main_for_asset("long_term_us_treasury_3x")
