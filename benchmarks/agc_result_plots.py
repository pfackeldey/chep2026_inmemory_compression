"""Plot AGC benchmark results from JSON files.

This script reads JSON result files under `results/agc/*.json` and creates four figures:
1. Peak RSS (GB) vs entry stop (number of events)
2. Runtime (s) vs entry stop (number of events)
3. Relative Peak RSS improvement (%) vs entry stop (baseline: inmemory + none)
4. Relative Runtime improvement (%) vs entry stop (baseline: inmemory + none)

Each line in the plots represents a unique combination of cache and codec.
"""

import json
import os
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker


def _densify_ticks(ax):
    """Set x ticks at 100 k-event intervals and increase y ticks (~50% more)."""
    ax.xaxis.set_major_locator(mticker.MultipleLocator(100_000))
    ax.locator_params(axis="y", nbins=int(ax.yaxis.get_tick_space() * 1.5))


def parse_filename(filename: str) -> dict:
    """Parse benchmark result filename to extract metadata.

    Filenames follow the pattern:
    - {cache}_{codec}_{entry_stop}.json
    - e.g. ondisk_blosc_1000000.json
    - e.g. inmemory_lru_500MiB_blosc_1000000.json
    """
    stem = Path(filename).stem
    parts = stem.split("_")
    entry_stop = int(parts[-1])
    codec = parts[-2]
    cache = "_".join(parts[:-2])
    return {"cache": cache, "codec": codec, "entry_stop": entry_stop}


def collect_data(results_dir: str) -> dict:
    """Collect and aggregate benchmark data from JSON files.

    Returns a dict keyed by (cache, codec) with values being lists of
    (entry_stop, peak_rss_gb, runtime_s) tuples.
    """
    data = defaultdict(list)
    for filepath in sorted(Path(results_dir).glob("*.json")):
        meta = parse_filename(filepath.name)
        with open(filepath, "r") as f:
            content = json.load(f)
        peak_rss_gb = content["peak_rss"] / (1024**3)
        runtime_s = content["execution_time"]
        data[(meta["cache"], meta["codec"])].append(
            (meta["entry_stop"], peak_rss_gb, runtime_s)
        )

    # Sort each series by entry_stop for proper line plotting
    for key in data:
        data[key].sort(key=lambda x: x[0])

    return data


def compute_relative(data: dict, baseline_key: tuple, metric_index: int) -> dict:
    """Compute relative improvement of each series against the baseline.

    Parameters
    ----------
    data : dict
        Mapping (cache, codec) -> list of (entry_stop, peak_rss_gb, runtime_s).
    baseline_key : tuple
        (cache, codec) key to use as baseline.
    metric_index : int
        Index of the metric in the value tuple (1 = peak_rss_gb, 2 = runtime_s).

    Returns
    -------
    dict
        Same structure as ``data`` but with relative improvement percentages,
        i.e. (baseline - value) / baseline * 100. Only entry_stop values that
        exist in the baseline are included.
    """
    baseline_points = {p[0]: p[metric_index] for p in data.get(baseline_key, [])}
    rel_data = {}
    for key, points in data.items():
        series = []
        for p in points:
            es = p[0]
            base = baseline_points.get(es)
            if base is not None and base != 0:
                rel = (base - p[metric_index]) / base * 100
                series.append((es, rel))
        if series:
            rel_data[key] = series
    return rel_data


def write_ondisk_disk_usage_tables(results_dir: str, output_dir: str) -> None:
    """Write markdown tables of total 'touched' bytes for ondisk cases.

    One table per codec ('none' and 'blosc'), one row per entry_stop.
    """
    rows_none = []
    rows_blosc = []

    for filepath in sorted(Path(results_dir).glob("ondisk_*.json")):
        meta = parse_filename(filepath.name)
        with open(filepath, "r") as f:
            content = json.load(f)
        total_bytes = sum(content.get("touched", {}).values())
        total_gb = total_bytes / (1024**3)
        row = (meta["entry_stop"], total_gb)
        if meta["codec"] == "none":
            rows_none.append(row)
        elif meta["codec"] == "blosc":
            rows_blosc.append(row)

    lines = ["# Disk Usage for `ondisk` Cache Configurations\n"]
    lines.append(
        "These tables show the total size of buffers written to the on-disk cache, "
        "calculated from the `touched` field in the benchmark results.\n"
    )

    for title, rows in [("ondisk + none", rows_none), ("ondisk + blosc", rows_blosc)]:
        if not rows:
            continue
        rows.sort(key=lambda x: x[0])
        lines.append(f"## {title}\n")
        lines.append("| Entry stop (events) | Total disk size (GB) |")
        lines.append("|--------------------:|---------------------:|")
        for entry_stop, gb in rows:
            lines.append(f"| {entry_stop:,} | {gb:.3f} |")
        lines.append("")

    output_path = Path(output_dir) / "ondisk_disk_usage.md"
    output_path.write_text("\n".join(lines))
    print(f"Disk usage tables written to {output_path}")


def _prettify_label(cache: str, codec: str) -> str:
    """Pretty-print a cache+codec combination for the legend."""
    codec_label = "uncompressed" if codec == "none" else codec.capitalize()

    match cache:
        case "inmemory":
            return f"In-memory ({codec_label})"
        case "ondisk":
            return f"On-disk ({codec_label})"
        case "inmemory_lru_100MiB":
            return f"In-memory LRU 100 MiB ({codec_label})"
        case "inmemory_lru_500MiB":
            return f"In-memory LRU 500 MiB ({codec_label})"
        case _:  # pragma: no cover
            return f"{cache} ({codec_label})"


def _resolve_style(key: tuple, all_keys: list) -> dict:
    """Return matplotlib line style: highlighted or faded with distinct colors."""
    highlight = {
        ("inmemory", "none"): {"color": "black", "linewidth": 2.2, "zorder": 3},
        ("inmemory", "blosc"): {"color": "#0072B2", "linewidth": 2.2, "zorder": 3},
        ("ondisk", "none"): {"color": "#D55E00", "linewidth": 2.2, "zorder": 3},
    }
    if key in highlight:
        return highlight[key]

    # Assign a stable, distinct color from tab20 for every non-highlight series
    cmap = plt.get_cmap("tab20")
    other = [k for k in all_keys if k not in highlight]
    idx = other.index(key)
    color = cmap(idx % cmap.N)
    return {"color": color, "linewidth": 1.0, "alpha": 0.45, "zorder": 1}


def plot_agc_results(data: dict, output_dir: str) -> None:
    """Create two figures: peak RSS vs entry stop and runtime vs entry stop."""
    os.makedirs(output_dir, exist_ok=True)

    # --- Figure 1: Peak RSS vs Entry Stop ---
    fig, ax = plt.subplots(figsize=(10, 6))
    keys_sorted = sorted(data.keys())
    for (cache, codec), points in sorted(data.items()):
        entry_stops = [p[0] for p in points]
        peak_rss = [p[1] for p in points]
        label = _prettify_label(cache, codec)
        style = _resolve_style((cache, codec), keys_sorted)
        mkargs = {"marker": "o"} if (cache, codec) in {
            ("inmemory", "none"), ("inmemory", "blosc"), ("ondisk", "none")
        } else {"marker": "o", "markersize": 3}
        ax.plot(entry_stops, peak_rss, label=label, **mkargs, **style)

    ax.set_xlabel("Number of events")
    ax.set_ylabel("Peak RSS (GB)")
    ax.set_title("Peak RSS vs Number of Events")
    ax.legend(title="Buffer Cache", loc="best")
    ax.grid(True, linestyle="--", alpha=0.5)
    _densify_ticks(ax)
    fig.tight_layout()
    fig.savefig(os.path.join(output_dir, "peak_rss_vs_entry_stop.pdf"))
    plt.close(fig)

    # --- Figure 2: Runtime vs Entry Stop ---
    fig, ax = plt.subplots(figsize=(10, 6))
    keys_sorted = sorted(data.keys())
    for (cache, codec), points in sorted(data.items()):
        entry_stops = [p[0] for p in points]
        runtimes = [p[2] for p in points]
        label = _prettify_label(cache, codec)
        style = _resolve_style((cache, codec), keys_sorted)
        mkargs = {"marker": "o"} if (cache, codec) in {
            ("inmemory", "none"), ("inmemory", "blosc"), ("ondisk", "none")
        } else {"marker": "o", "markersize": 3}
        ax.plot(entry_stops, runtimes, label=label, **mkargs, **style)

    ax.set_xlabel("Number of events")
    ax.set_ylabel("Runtime (s)")
    ax.set_title("Runtime vs Number of Events")
    ax.legend(title="Buffer Cache", loc="best")
    ax.grid(True, linestyle="--", alpha=0.5)
    _densify_ticks(ax)
    fig.tight_layout()
    fig.savefig(os.path.join(output_dir, "runtime_vs_entry_stop.pdf"))
    plt.close(fig)

    baseline_key = ("inmemory", "none")
    if baseline_key not in data:
        print(f"Warning: baseline {baseline_key} not found; skipping relative plots")
        return

    # --- Figure 3: Relative Peak RSS Improvement ---
    rel_peak = compute_relative(data, baseline_key, metric_index=1)
    fig, ax = plt.subplots(figsize=(10, 6))
    keys_sorted = sorted(rel_peak.keys())
    for (cache, codec), points in sorted(rel_peak.items()):
        entry_stops = [p[0] for p in points]
        improvements = [p[1] for p in points]
        label = _prettify_label(cache, codec)
        style = _resolve_style((cache, codec), keys_sorted)
        mkargs = {"marker": "o"} if (cache, codec) in {
            ("inmemory", "none"), ("inmemory", "blosc"), ("ondisk", "none")
        } else {"marker": "o", "markersize": 3}
        ax.plot(entry_stops, improvements, label=label, **mkargs, **style)

    ax.axhline(0, color="black", linestyle="-", linewidth=0.8)
    ax.set_xlabel("Number of events")
    ax.set_ylabel("Relative improvement (%)")
    ax.set_title("Peak RSS Relative Improvement (inmemory + none as baseline)")
    ax.legend(title="Buffer Cache", loc="best")
    ax.grid(True, linestyle="--", alpha=0.5)
    _densify_ticks(ax)
    fig.tight_layout()
    fig.savefig(os.path.join(output_dir, "peak_rss_relative_improvement.pdf"))
    plt.close(fig)

    # --- Figure 4: Relative Runtime Improvement ---
    rel_runtime = compute_relative(data, baseline_key, metric_index=2)
    fig, ax = plt.subplots(figsize=(10, 6))
    keys_sorted = sorted(rel_runtime.keys())
    for (cache, codec), points in sorted(rel_runtime.items()):
        entry_stops = [p[0] for p in points]
        improvements = [p[1] for p in points]
        label = _prettify_label(cache, codec)
        style = _resolve_style((cache, codec), keys_sorted)
        mkargs = {"marker": "o"} if (cache, codec) in {
            ("inmemory", "none"), ("inmemory", "blosc"), ("ondisk", "none")
        } else {"marker": "o", "markersize": 3}
        ax.plot(entry_stops, improvements, label=label, **mkargs, **style)

    ax.axhline(0, color="black", linestyle="-", linewidth=0.8)
    ax.set_xlabel("Number of events")
    ax.set_ylabel("Relative improvement (%)")
    ax.set_title("Runtime Relative Improvement (inmemory + none as baseline)")
    ax.legend(title="Buffer Cache", loc="best")
    ax.grid(True, linestyle="--", alpha=0.5)
    _densify_ticks(ax)
    fig.tight_layout()
    fig.savefig(os.path.join(output_dir, "runtime_relative_improvement.pdf"))
    plt.close(fig)


def main() -> None:
    script_dir = Path(__file__).parent.resolve()
    results_dir = script_dir / "results" / "agc"
    output_dir = script_dir / "plots"

    data = collect_data(str(results_dir))
    if not data:
        print(f"No JSON files found in {results_dir}")
        return

    plot_agc_results(data, str(output_dir))
    write_ondisk_disk_usage_tables(str(results_dir), str(output_dir))
    print(f"Plots saved to {output_dir}")


if __name__ == "__main__":
    main()
