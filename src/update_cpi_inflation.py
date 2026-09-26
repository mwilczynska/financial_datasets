"""Incrementally update cpi_inflation; use --full-rebuild for the historical builder."""

from incremental_update import main_for_asset


if __name__ == "__main__":
    main_for_asset("cpi_inflation")
