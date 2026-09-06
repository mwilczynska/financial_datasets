"""Create the static asset-class chart used by the repository README.

The chart is intentionally generated from the published processed CSV files so
that it can be refreshed after a dataset update.  It uses each series' total
return level (``Adj Close``), rebased to 100 on the common start date, and
stops at the common latest observation so the comparison has one shared
endpoint.

Example:
    python src/create_readme_chart.py
    python src/create_readme_chart.py --output docs/assets/asset-class-growth.png
"""

from __future__ import annotations

import argparse
from collections import OrderedDict
from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.ticker import FuncFormatter, LogLocator


DATASETS = OrderedDict(
    (
        ("us_large_cap_sp500", "U.S. large-cap stocks"),
        ("global_stocks", "Global stocks"),
        ("long_term_us_treasury", "Long-term U.S. Treasuries"),
        ("global_bonds", "Global bonds"),
        ("gold", "Gold"),
        ("broad_commodities", "Broad commodities"),
    )
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Repository root (default: the parent of src/)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="PNG output path (default: docs/assets/asset-class-growth.png)",
    )
    return parser.parse_args()


def load_series(root: Path) -> dict[str, pd.Series]:
    """Load positive adjusted-close levels for the selected unlevered series."""

    processed = root / "data" / "processed"
    loaded: dict[str, pd.Series] = {}
    for asset_id in DATASETS:
        path = processed / f"{asset_id}.csv"
        if not path.exists():
            raise FileNotFoundError(f"Processed dataset not found: {path}")

        frame = pd.read_csv(path, usecols=["Date", "Adj Close"])
        frame["Date"] = pd.to_datetime(frame["Date"], errors="raise")
        frame["Adj Close"] = pd.to_numeric(frame["Adj Close"], errors="raise")
        frame = frame.dropna(subset=["Date", "Adj Close"])
        frame = frame.drop_duplicates(subset="Date", keep="last").sort_values("Date")
        if frame.empty or (frame["Adj Close"] <= 0).any():
            raise ValueError(f"{asset_id} contains no valid positive Adj Close history")
        loaded[asset_id] = frame.set_index("Date")["Adj Close"]

    return loaded


def build_chart(root: Path, output: Path) -> tuple[pd.Timestamp, pd.Timestamp]:
    series = load_series(root)
    common_start = max(values.index.min() for values in series.values())
    common_end = min(values.index.max() for values in series.values())
    if common_start >= common_end:
        raise ValueError("Selected datasets do not have a shared date range")

    colors = ["#1769aa", "#00897b", "#6a3d9a", "#34495e", "#c58b00", "#d95f02"]
    fig, ax = plt.subplots(figsize=(12.8, 7.2), dpi=180)
    fig.patch.set_facecolor("#ffffff")
    ax.set_facecolor("#ffffff")

    for (asset_id, label), color in zip(DATASETS.items(), colors):
        values = series[asset_id].loc[common_start:common_end]
        rebased = values / values.iloc[0] * 100.0
        ax.plot(
            rebased.index,
            rebased,
            label=label,
            color=color,
            linewidth=2.0,
            solid_capstyle="round",
        )

    ax.set_yscale("log")
    ax.set_ylim(bottom=50)
    ax.yaxis.set_major_locator(LogLocator(base=10, subs=(1.0, 2.0, 5.0)))
    ax.yaxis.set_major_formatter(
        FuncFormatter(lambda value, _: f"${value:,.0f}" if value >= 1 else "")
    )
    ax.xaxis.set_major_locator(mdates.YearLocator(10))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax.set_xlim(common_start, common_end)
    ax.grid(axis="y", which="major", color="#d9e0e8", linewidth=0.8)
    ax.grid(axis="x", which="major", color="#edf0f4", linewidth=0.6)
    ax.set_axisbelow(True)
    ax.tick_params(axis="both", colors="#52606d", labelsize=9, length=0)
    for spine in ("top", "right", "left"):
        ax.spines[spine].set_visible(False)
    ax.spines["bottom"].set_color("#b7c2ce")
    ax.set_ylabel("Growth of $100 (log scale)", color="#273444", fontsize=10)
    ax.set_xlabel("Observation date", color="#273444", fontsize=10, labelpad=8)

    fig.suptitle(
        "Long-horizon asset-class total-return proxies",
        x=0.08,
        y=0.965,
        ha="left",
        fontsize=17,
        fontweight="bold",
        color="#17212b",
    )
    fig.text(
        0.08,
        0.925,
        f"Indexed to 100 on {common_start:%Y-%m-%d}; common history through {common_end:%Y-%m-%d}",
        ha="left",
        fontsize=10,
        color="#52606d",
    )
    legend = ax.legend(
        loc="upper left",
        bbox_to_anchor=(0.012, 0.995),
        frameon=False,
        ncol=2,
        fontsize=9,
        columnspacing=1.4,
        handlelength=2.4,
        borderaxespad=0,
    )
    for text in legend.get_texts():
        text.set_color("#273444")
    fig.text(
        0.08,
        0.015,
        "Total return uses each dataset's Adj Close. Series may include documented model or source-spliced segments; see the methodology files.",
        ha="left",
        fontsize=8.5,
        color="#667584",
    )
    fig.subplots_adjust(left=0.08, right=0.98, top=0.82, bottom=0.13)

    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(
        output,
        dpi=180,
        facecolor=fig.get_facecolor(),
        edgecolor="none",
        metadata={"Software": "financial_datasets create_readme_chart.py"},
    )
    plt.close(fig)
    return common_start, common_end


def main() -> None:
    args = parse_args()
    root = args.root.resolve()
    output = args.output or root / "docs" / "assets" / "asset-class-growth.png"
    output = output if output.is_absolute() else root / output
    start, end = build_chart(root, output)
    print(f"Wrote {output} ({start:%Y-%m-%d} to {end:%Y-%m-%d})")


if __name__ == "__main__":
    main()
