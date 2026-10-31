"""Incrementally update global_stocks_2x; use --full-rebuild for the historical builder."""

from incremental_update import main_for_asset


if __name__ == "__main__":
    main_for_asset("global_stocks_2x")
