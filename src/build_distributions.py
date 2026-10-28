"""Build USD cash-distribution companion datasets from their documented sources."""

try:
    from .distributions_pipeline import cli
except ImportError:
    from distributions_pipeline import cli

if __name__ == "__main__":
    cli(full_default=True)
