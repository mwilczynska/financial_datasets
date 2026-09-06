"""Create the fixed-size GitHub social-preview image.

This deliberately reuses the same processed series and rebasing rules as
``create_readme_chart.py``.  Run it from the repository root after installing
``requirements-visuals.txt``:

    python src/create_social_preview.py
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter, LogLocator

from create_readme_chart import DATASETS, load_series


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
        help="PNG output path (default: docs/assets/social-preview.png)",
    )
    return parser.parse_args()


def build_social_preview(root: Path, output: Path) -> tuple[int, int]:
    series = load_series(root)
    common_start = max(values.index.min() for values in series.values())
    common_end = min(values.index.max() for values in series.values())
    if common_start >= common_end:
        raise ValueError("Selected datasets do not have a shared date range")
    colors = ["#56b4e9", "#55c99a", "#c7a0ff", "#b9c7d8", "#f6c85f", "#ff9f68"]
    fig, ax = plt.subplots(figsize=(12.8, 6.4), dpi=100)
    background = "#132238"
    fig.patch.set_facecolor(background)
    ax.set_facecolor(background)
    for (asset_id, label), color in zip(DATASETS.items(), colors):
        values = series[asset_id].loc[common_start:common_end]
        rebased = values / values.iloc[0] * 100.0
        ax.plot(
            rebased.index,
            rebased,
            label=label,
            color=color,
            linewidth=1.9,
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
    ax.grid(axis="y", which="major", color="#31465f", linewidth=0.75)
    ax.grid(axis="x", which="major", color="#223850", linewidth=0.55)
    ax.set_axisbelow(True)
    ax.tick_params(axis="both", colors="#b9c7d8", labelsize=8.5, length=0)
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.set_ylabel("Growth of $100 (log scale)", color="#dce5ef", fontsize=9)
    ax.set_xlabel("Observation date", color="#dce5ef", fontsize=9, labelpad=7)
    fig.suptitle(
        "Financial Datasets",
        x=0.065,
        y=0.95,
        ha="left",
        fontsize=23,
        fontweight="bold",
        color="#f5f8fb",
    )
    fig.text(
        0.065,
        0.895,
        "Long-horizon daily asset-class datasets for Python portfolio backtesting",
        ha="left",
        fontsize=10.5,
        color="#b9c7d8",
    )
    fig.text(
        0.065,
        0.855,
        f"Selected total-return proxies | {common_start:%Y-%m-%d} to {common_end:%Y-%m-%d}",
        ha="left",
        fontsize=9,
        color="#8fa5bc",
    )
    legend = ax.legend(
        loc="upper left",
        bbox_to_anchor=(0.01, 1.0),
        frameon=False,
        ncol=3,
        fontsize=8.2,
        columnspacing=1.5,
        handlelength=2.0,
        borderaxespad=0,
    )
    for text in legend.get_texts():
        text.set_color("#dce5ef")
    fig.subplots_adjust(left=0.065, right=0.985, top=0.72, bottom=0.15)
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(
        output,
        dpi=100,
        facecolor=fig.get_facecolor(),
        edgecolor="none",
        metadata={"Software": "financial_datasets create_social_preview.py"},
    )
    plt.close(fig)
    return 1280, 640


def main() -> None:
    args = parse_args()
    root = args.root.resolve()
    output = args.output or root / "docs" / "assets" / "social-preview.png"
    output = output if output.is_absolute() else root / output
    width, height = build_social_preview(root, output)
    print(f"Wrote {output} ({width}x{height})")


if __name__ == "__main__":
    main()
