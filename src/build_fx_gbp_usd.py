"""Build the full GBP/USD spot history from BIS (1970-1998) and ECB reference rates (1999 onward)."""

from fx_rates import build_main


if __name__ == "__main__":
    build_main("fx_gbp_usd")
