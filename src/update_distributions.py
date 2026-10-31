"""Refresh USD cash distributions, preserving frozen historical payout models."""

try:
    from .distributions_pipeline import cli
except ImportError:
    from distributions_pipeline import cli

if __name__ == "__main__":
    cli(full_default=False)
