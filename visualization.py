"""
Visualization module for the Oil Tanker Flow Simulation.

Provides plotting functions for simulation results, including time series,
distributions, and scenario comparisons.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np

from statistics_collector import SimulationStatistics, AggregateMetrics, MultiRunStatistics
from config import TankerType


# Style configuration
plt.style.use('seaborn-v0_8-whitegrid')
COLORS = {
    'primary': '#2E86AB',
    'secondary': '#A23B72',
    'accent': '#F18F01',
    'success': '#C73E1D',
    'neutral': '#3B3B3B',
    'disruption': '#FF6B6B',
    'normal': '#4ECDC4',
}

TANKER_COLORS = {
    'VLCC': '#2E86AB',
    'SUEZMAX': '#A23B72',
    'AFRAMAX': '#F18F01',
    'PANAMAX': '#C73E1D',
}


def setup_figure(figsize: tuple = (12, 6)) -> tuple:
    """Create a figure with consistent styling."""
    fig, ax = plt.subplots(figsize=figsize)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    return fig, ax


def plot_queue_length_over_time(
    statistics: SimulationStatistics,
    title: str = "Queue Length Over Time",
    save_path: Optional[Path] = None
) -> plt.Figure:
    """
    Plot queue length time series with disruption periods highlighted.

    Args:
        statistics: Simulation statistics object
        title: Plot title
        save_path: Optional path to save figure

    Returns:
        Matplotlib figure
    """
    fig, ax = setup_figure((14, 6))

    time_series = statistics.get_time_series_data()

    times = time_series["queue_length"]["times"]
    values = time_series["queue_length"]["values"]

    if times:
        ax.plot(times, values, color=COLORS['primary'], linewidth=1.5, alpha=0.8)
        ax.fill_between(times, values, alpha=0.3, color=COLORS['primary'])

    # Highlight disruption periods
    for disruption in time_series["disruptions"]:
        start = disruption["start"]
        end = disruption["end"] if disruption["end"] else max(times) if times else start
        ax.axvspan(start, end, alpha=0.2, color=COLORS['disruption'],
                   label=f"Disruption: {disruption['type']}")

    ax.set_xlabel("Time (hours)", fontsize=12)
    ax.set_ylabel("Queue Length (tankers)", fontsize=12)
    ax.set_title(title, fontsize=14, fontweight='bold')

    # Add legend if there are disruptions
    if time_series["disruptions"]:
        handles = [
            mpatches.Patch(color=COLORS['primary'], alpha=0.3, label='Queue Length'),
            mpatches.Patch(color=COLORS['disruption'], alpha=0.2, label='Disruption Period')
        ]
        ax.legend(handles=handles, loc='upper right')

    plt.tight_layout()

    if save_path:
        fig.savefig(save_path, dpi=150, bbox_inches='tight')

    return fig


def plot_waiting_time_distribution(
    statistics: SimulationStatistics,
    title: str = "Waiting Time Distribution",
    save_path: Optional[Path] = None
) -> plt.Figure:
    """
    Plot histogram of waiting times.

    Args:
        statistics: Simulation statistics object
        title: Plot title
        save_path: Optional path to save figure

    Returns:
        Matplotlib figure
    """
    fig, ax = setup_figure((10, 6))

    dist_data = statistics.get_waiting_time_distribution()
    waiting_times = dist_data["times"]

    if waiting_times:
        bins = min(30, max(10, len(waiting_times) // 10))
        ax.hist(waiting_times, bins=bins, color=COLORS['primary'],
                edgecolor='white', alpha=0.7)

        # Add mean line
        mean_wait = np.mean(waiting_times)
        ax.axvline(mean_wait, color=COLORS['accent'], linestyle='--',
                   linewidth=2, label=f'Mean: {mean_wait:.2f}h')

        # Add 95th percentile line
        p95 = np.percentile(waiting_times, 95)
        ax.axvline(p95, color=COLORS['secondary'], linestyle=':',
                   linewidth=2, label=f'95th %ile: {p95:.2f}h')

        ax.legend()

    ax.set_xlabel("Waiting Time (hours)", fontsize=12)
    ax.set_ylabel("Frequency", fontsize=12)
    ax.set_title(title, fontsize=14, fontweight='bold')

    plt.tight_layout()

    if save_path:
        fig.savefig(save_path, dpi=150, bbox_inches='tight')

    return fig


def plot_waiting_time_by_tanker_type(
    statistics: SimulationStatistics,
    title: str = "Average Waiting Time by Tanker Type",
    save_path: Optional[Path] = None
) -> plt.Figure:
    """
    Plot bar chart of waiting times by tanker type.

    Args:
        statistics: Simulation statistics object
        title: Plot title
        save_path: Optional path to save figure

    Returns:
        Matplotlib figure
    """
    fig, ax = setup_figure((10, 6))

    dist_data = statistics.get_waiting_time_distribution()
    by_type = dist_data["by_type"]

    if by_type:
        types = list(by_type.keys())
        means = [by_type[t]["mean"] for t in types]
        colors = [TANKER_COLORS.get(t, COLORS['neutral']) for t in types]

        bars = ax.bar(types, means, color=colors, edgecolor='white', linewidth=1.5)

        # Add value labels on bars
        for bar, mean in zip(bars, means):
            height = bar.get_height()
            ax.annotate(f'{mean:.2f}h',
                        xy=(bar.get_x() + bar.get_width() / 2, height),
                        xytext=(0, 3),
                        textcoords="offset points",
                        ha='center', va='bottom', fontsize=10)

    ax.set_xlabel("Tanker Type", fontsize=12)
    ax.set_ylabel("Average Waiting Time (hours)", fontsize=12)
    ax.set_title(title, fontsize=14, fontweight='bold')

    plt.tight_layout()

    if save_path:
        fig.savefig(save_path, dpi=150, bbox_inches='tight')

    return fig


def plot_throughput_comparison(
    metrics_list: list[tuple[str, AggregateMetrics]],
    title: str = "Throughput Comparison Across Scenarios",
    save_path: Optional[Path] = None
) -> plt.Figure:
    """
    Plot bar chart comparing throughput across scenarios.

    Args:
        metrics_list: List of (scenario_name, AggregateMetrics) tuples
        title: Plot title
        save_path: Optional path to save figure

    Returns:
        Matplotlib figure
    """
    fig, ax = setup_figure((12, 6))

    scenarios = [name for name, _ in metrics_list]
    throughputs = [m.throughput_per_day for _, m in metrics_list]

    colors = [COLORS['primary'] if i == 0 else COLORS['secondary']
              for i in range(len(scenarios))]

    bars = ax.bar(scenarios, throughputs, color=colors, edgecolor='white', linewidth=1.5)

    # Add value labels
    for bar, tp in zip(bars, throughputs):
        height = bar.get_height()
        ax.annotate(f'{tp:.1f}',
                    xy=(bar.get_x() + bar.get_width() / 2, height),
                    xytext=(0, 3),
                    textcoords="offset points",
                    ha='center', va='bottom', fontsize=10, fontweight='bold')

    ax.set_xlabel("Scenario", fontsize=12)
    ax.set_ylabel("Throughput (tankers/day)", fontsize=12)
    ax.set_title(title, fontsize=14, fontweight='bold')

    # Rotate x labels if needed
    plt.xticks(rotation=30, ha='right')
    plt.tight_layout()

    if save_path:
        fig.savefig(save_path, dpi=150, bbox_inches='tight')

    return fig


def plot_waiting_time_comparison(
    metrics_list: list[tuple[str, AggregateMetrics]],
    title: str = "Average Waiting Time Comparison",
    save_path: Optional[Path] = None
) -> plt.Figure:
    """
    Plot bar chart comparing waiting times across scenarios.

    Args:
        metrics_list: List of (scenario_name, AggregateMetrics) tuples
        title: Plot title
        save_path: Optional path to save figure

    Returns:
        Matplotlib figure
    """
    fig, ax = setup_figure((12, 6))

    scenarios = [name for name, _ in metrics_list]
    avg_waits = [m.avg_waiting_time for _, m in metrics_list]
    max_waits = [m.max_waiting_time for _, m in metrics_list]

    x = np.arange(len(scenarios))
    width = 0.35

    ax.bar(x - width/2, avg_waits, width, label='Average', color=COLORS['primary'])
    ax.bar(x + width/2, max_waits, width, label='Maximum', color=COLORS['secondary'])

    ax.set_xlabel("Scenario", fontsize=12)
    ax.set_ylabel("Waiting Time (hours)", fontsize=12)
    ax.set_title(title, fontsize=14, fontweight='bold')
    ax.set_xticks(x)
    ax.set_xticklabels(scenarios, rotation=30, ha='right')
    ax.legend()

    plt.tight_layout()

    if save_path:
        fig.savefig(save_path, dpi=150, bbox_inches='tight')

    return fig


def plot_oil_delivery_impact(
    metrics_list: list[tuple[str, AggregateMetrics]],
    title: str = "Oil Delivery Impact by Scenario",
    save_path: Optional[Path] = None
) -> plt.Figure:
    """
    Plot oil delivery comparison across scenarios.

    Args:
        metrics_list: List of (scenario_name, AggregateMetrics) tuples
        title: Plot title
        save_path: Optional path to save figure

    Returns:
        Matplotlib figure
    """
    fig, ax = setup_figure((12, 6))

    scenarios = [name for name, _ in metrics_list]
    oil_delivery = [m.oil_per_day_barrels / 1_000_000 for _, m in metrics_list]  # Convert to millions

    # Calculate percentage of baseline
    baseline = oil_delivery[0] if oil_delivery else 1
    percentages = [od / baseline * 100 for od in oil_delivery]

    colors = [COLORS['success'] if p >= 90 else COLORS['accent'] if p >= 70
              else COLORS['disruption'] for p in percentages]

    bars = ax.bar(scenarios, oil_delivery, color=colors, edgecolor='white', linewidth=1.5)

    # Add percentage labels
    for bar, pct in zip(bars, percentages):
        height = bar.get_height()
        ax.annotate(f'{pct:.0f}%',
                    xy=(bar.get_x() + bar.get_width() / 2, height),
                    xytext=(0, 3),
                    textcoords="offset points",
                    ha='center', va='bottom', fontsize=10, fontweight='bold')

    ax.set_xlabel("Scenario", fontsize=12)
    ax.set_ylabel("Oil Delivery (million barrels/day)", fontsize=12)
    ax.set_title(title, fontsize=14, fontweight='bold')
    plt.xticks(rotation=30, ha='right')

    plt.tight_layout()

    if save_path:
        fig.savefig(save_path, dpi=150, bbox_inches='tight')

    return fig


def plot_multi_run_confidence_intervals(
    multi_run_stats: list[MultiRunStatistics],
    metric: str = "avg_waiting_time",
    title: str = "Comparison with 95% Confidence Intervals",
    save_path: Optional[Path] = None
) -> plt.Figure:
    """
    Plot comparison of scenarios with confidence intervals from multiple runs.

    Args:
        multi_run_stats: List of MultiRunStatistics objects for each scenario
        metric: Which metric to plot
        title: Plot title
        save_path: Optional path to save figure

    Returns:
        Matplotlib figure
    """
    fig, ax = setup_figure((12, 6))

    scenarios = []
    means = []
    errors = []

    for mrs in multi_run_stats:
        summary = mrs.summary()
        if metric in summary:
            scenarios.append(summary["scenario"])
            mean, lower, upper = summary[metric]
            means.append(mean)
            errors.append([mean - lower, upper - mean])

    if means:
        x = np.arange(len(scenarios))
        errors_array = np.array(errors).T

        ax.bar(x, means, yerr=errors_array, capsize=5,
               color=COLORS['primary'], edgecolor='white',
               error_kw={'elinewidth': 2, 'capthick': 2})

        ax.set_xticks(x)
        ax.set_xticklabels(scenarios, rotation=30, ha='right')

    metric_labels = {
        "avg_waiting_time": "Average Waiting Time (hours)",
        "throughput_per_day": "Throughput (tankers/day)",
        "avg_queue_length": "Average Queue Length"
    }

    ax.set_xlabel("Scenario", fontsize=12)
    ax.set_ylabel(metric_labels.get(metric, metric), fontsize=12)
    ax.set_title(title, fontsize=14, fontweight='bold')

    plt.tight_layout()

    if save_path:
        fig.savefig(save_path, dpi=150, bbox_inches='tight')

    return fig


def create_dashboard(
    statistics: SimulationStatistics,
    metrics: AggregateMetrics,
    scenario_name: str = "Simulation",
    save_path: Optional[Path] = None
) -> plt.Figure:
    """
    Create a comprehensive dashboard with multiple plots.

    Args:
        statistics: Simulation statistics object
        metrics: Aggregate metrics
        scenario_name: Name of scenario for title
        save_path: Optional path to save figure

    Returns:
        Matplotlib figure
    """
    fig = plt.figure(figsize=(16, 12))

    # Queue length over time
    ax1 = fig.add_subplot(2, 2, 1)
    time_series = statistics.get_time_series_data()
    times = time_series["queue_length"]["times"]
    values = time_series["queue_length"]["values"]
    if times:
        ax1.plot(times, values, color=COLORS['primary'], linewidth=1.5)
        ax1.fill_between(times, values, alpha=0.3, color=COLORS['primary'])
        for d in time_series["disruptions"]:
            start, end = d["start"], d["end"] or max(times)
            ax1.axvspan(start, end, alpha=0.2, color=COLORS['disruption'])
    ax1.set_xlabel("Time (hours)")
    ax1.set_ylabel("Queue Length")
    ax1.set_title("Queue Length Over Time")

    # Waiting time histogram
    ax2 = fig.add_subplot(2, 2, 2)
    dist_data = statistics.get_waiting_time_distribution()
    waiting_times = dist_data["times"]
    if waiting_times:
        ax2.hist(waiting_times, bins=20, color=COLORS['primary'],
                 edgecolor='white', alpha=0.7)
        ax2.axvline(np.mean(waiting_times), color=COLORS['accent'],
                    linestyle='--', label=f'Mean: {np.mean(waiting_times):.2f}h')
        ax2.legend()
    ax2.set_xlabel("Waiting Time (hours)")
    ax2.set_ylabel("Frequency")
    ax2.set_title("Waiting Time Distribution")

    # Waiting time by tanker type
    ax3 = fig.add_subplot(2, 2, 3)
    by_type = dist_data["by_type"]
    if by_type:
        types = list(by_type.keys())
        means = [by_type[t]["mean"] for t in types]
        colors = [TANKER_COLORS.get(t, COLORS['neutral']) for t in types]
        ax3.bar(types, means, color=colors, edgecolor='white')
    ax3.set_xlabel("Tanker Type")
    ax3.set_ylabel("Avg Waiting Time (hours)")
    ax3.set_title("Waiting Time by Tanker Type")

    # Key metrics summary
    ax4 = fig.add_subplot(2, 2, 4)
    ax4.axis('off')

    summary_text = f"""
    KEY METRICS SUMMARY
    {'='*40}

    Throughput
    ----------
    Tankers Processed:  {metrics.total_tankers_processed:,}
    Per Day:            {metrics.throughput_per_day:.1f} tankers

    Timing (hours)
    --------------
    Avg Waiting Time:   {metrics.avg_waiting_time:.2f}
    Max Waiting Time:   {metrics.max_waiting_time:.2f}
    Avg Transit Time:   {metrics.avg_transit_time:.2f}

    Queue
    -----
    Avg Queue Length:   {metrics.avg_queue_length:.2f}
    Max Queue Length:   {metrics.max_queue_length}

    Oil Delivery
    ------------
    Total Delivered:    {metrics.total_oil_delivered_barrels/1e6:.2f}M barrels
    Per Day:            {metrics.oil_per_day_barrels/1e6:.2f}M barrels/day
    """

    ax4.text(0.1, 0.9, summary_text, transform=ax4.transAxes,
             fontsize=11, verticalalignment='top', fontfamily='monospace',
             bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))

    fig.suptitle(f"{scenario_name} - Simulation Dashboard",
                 fontsize=16, fontweight='bold', y=1.02)

    plt.tight_layout()

    if save_path:
        fig.savefig(save_path, dpi=150, bbox_inches='tight')

    return fig


def save_all_plots(
    statistics: SimulationStatistics,
    metrics: AggregateMetrics,
    scenario_name: str,
    output_dir: Path
) -> list[Path]:
    """
    Generate and save all standard plots.

    Args:
        statistics: Simulation statistics object
        metrics: Aggregate metrics
        scenario_name: Name of scenario
        output_dir: Directory to save plots

    Returns:
        List of paths to saved figures
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    saved_paths = []

    # Queue length
    path = output_dir / f"{scenario_name}_queue_length.png"
    plot_queue_length_over_time(statistics, save_path=path)
    saved_paths.append(path)
    plt.close()

    # Waiting time distribution
    path = output_dir / f"{scenario_name}_waiting_dist.png"
    plot_waiting_time_distribution(statistics, save_path=path)
    saved_paths.append(path)
    plt.close()

    # Waiting by type
    path = output_dir / f"{scenario_name}_waiting_by_type.png"
    plot_waiting_time_by_tanker_type(statistics, save_path=path)
    saved_paths.append(path)
    plt.close()

    # Dashboard
    path = output_dir / f"{scenario_name}_dashboard.png"
    create_dashboard(statistics, metrics, scenario_name, save_path=path)
    saved_paths.append(path)
    plt.close()

    return saved_paths
