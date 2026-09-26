"""Incrementally update global_short_term_bonds; use --full-rebuild for the historical builder."""

from incremental_update import main_for_asset


if __name__ == "__main__":
    main_for_asset("global_short_term_bonds")
