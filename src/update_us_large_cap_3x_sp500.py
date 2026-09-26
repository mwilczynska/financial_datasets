"""Incrementally update us_large_cap_3x_sp500; use --full-rebuild for the historical builder."""

from incremental_update import main_for_asset


if __name__ == "__main__":
    main_for_asset("us_large_cap_3x_sp500")
