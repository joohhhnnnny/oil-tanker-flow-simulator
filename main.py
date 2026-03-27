#!/usr/bin/env python3
"""
Oil Tanker Flow Simulator - Strait of Hormuz

A discrete event simulation (DES) model for analyzing oil tanker traffic
through the Strait of Hormuz, including disruption scenarios and mitigation
strategies.

Usage:
    python main.py                      # Run all scenarios
    python main.py --scenario baseline  # Run specific scenario
    python main.py --verbose            # Enable detailed output
    python main.py --help               # Show help

Author: Oil Tanker Flow Simulation Project
License: MIT
"""

import argparse
import sys
from pathlib import Path
from dataclasses import dataclass
from datetime import datetime

from config import (
    SimulationConfig, DisruptionConfig, DisruptionType,
    MitigationStrategy, SCENARIOS, StraitConfig
)
from simulation import (
    OilTankerSimulation, run_scenario, compare_scenarios,
    run_mitigation_comparison
)
from statistics_collector import AggregateMetrics
from visualization import (
    plot_queue_length_over_time,
    plot_waiting_time_distribution,
    plot_throughput_comparison,
    plot_waiting_time_comparison,
    plot_oil_delivery_impact,
    create_dashboard,
    save_all_plots
)

import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend
import matplotlib.pyplot as plt


def run_baseline_scenario(config: SimulationConfig = None, verbose: bool = False):
    """
    Run the baseline scenario with no disruptions.

    This establishes normal operating conditions for comparison.
    """
    print("\n" + "="*70)
    print("BASELINE SCENARIO: Normal Operations")
    print("="*70)

    if config is None:
        config = SimulationConfig(
            duration_hours=168.0,  # 1 week
            warmup_hours=24.0,
            disruption_config=DisruptionConfig(disruption_type=DisruptionType.NONE),
            mitigation_strategy=MitigationStrategy.NONE,
            verbose=verbose
        )

    stats, metrics = run_scenario("baseline", config, verbose)

    print("\n" + stats.summary_report(config.duration_hours))

    return stats, metrics


def run_disruption_scenarios(verbose: bool = False):
    """
    Run multiple disruption scenarios for comparison.
    """
    print("\n" + "="*70)
    print("DISRUPTION SCENARIO COMPARISON")
    print("="*70)

    scenarios = {
        "Baseline (No Disruption)": SimulationConfig(
            duration_hours=168.0,
            warmup_hours=24.0,
            disruption_config=DisruptionConfig(disruption_type=DisruptionType.NONE)
        ),
        "Partial Blockade (50%)": SimulationConfig(
            duration_hours=168.0,
            warmup_hours=24.0,
            disruption_config=DisruptionConfig(
                disruption_type=DisruptionType.PARTIAL_BLOCKADE,
                start_time_hours=48.0,
                duration_hours=72.0,
                capacity_reduction=0.5,
                transit_time_multiplier=1.5
            )
        ),
        "Complete Blockade (48h)": SimulationConfig(
            duration_hours=168.0,
            warmup_hours=24.0,
            disruption_config=DisruptionConfig(
                disruption_type=DisruptionType.COMPLETE_BLOCKADE,
                start_time_hours=48.0,
                duration_hours=48.0,
                capacity_reduction=1.0
            )
        ),
        "Severe Weather": SimulationConfig(
            duration_hours=168.0,
            warmup_hours=24.0,
            disruption_config=DisruptionConfig(
                disruption_type=DisruptionType.WEATHER_DELAY,
                start_time_hours=24.0,
                duration_hours=12.0,
                capacity_reduction=0.3,
                transit_time_multiplier=2.0
            )
        ),
    }

    results = compare_scenarios(scenarios, verbose)
    return results


def run_mitigation_analysis(verbose: bool = False):
    """
    Analyze the effectiveness of different mitigation strategies.
    """
    print("\n" + "="*70)
    print("MITIGATION STRATEGY ANALYSIS")
    print("="*70)

    # Use partial blockade as the test disruption
    disruption_config = DisruptionConfig(
        disruption_type=DisruptionType.PARTIAL_BLOCKADE,
        start_time_hours=48.0,
        duration_hours=72.0,
        capacity_reduction=0.5,
        transit_time_multiplier=1.5
    )

    scenarios = {
        "No Mitigation": SimulationConfig(
            duration_hours=168.0,
            warmup_hours=24.0,
            disruption_config=disruption_config,
            mitigation_strategy=MitigationStrategy.NONE
        ),
        "Priority Scheduling": SimulationConfig(
            duration_hours=168.0,
            warmup_hours=24.0,
            disruption_config=disruption_config,
            mitigation_strategy=MitigationStrategy.PRIORITY_SCHEDULING
        ),
        "Alternative Routing": SimulationConfig(
            duration_hours=168.0,
            warmup_hours=24.0,
            disruption_config=disruption_config,
            mitigation_strategy=MitigationStrategy.ALTERNATIVE_ROUTING
        ),
    }

    results = compare_scenarios(scenarios, verbose)
    return results


def run_sensitivity_analysis(verbose: bool = False):
    """
    Perform sensitivity analysis on arrival rates.
    """
    print("\n" + "="*70)
    print("SENSITIVITY ANALYSIS: Arrival Rate Impact")
    print("="*70)

    arrival_rates = [0.5, 0.7, 0.9, 1.1]  # tankers per hour
    results = {}

    for rate in arrival_rates:
        print(f"\nTesting arrival rate: {rate} tankers/hour ({rate*24:.1f}/day)")

        strait_config = StraitConfig(mean_arrival_rate_per_hour=rate)
        config = SimulationConfig(
            duration_hours=168.0,
            warmup_hours=24.0,
            strait_config=strait_config,
            disruption_config=DisruptionConfig(disruption_type=DisruptionType.NONE)
        )

        stats, metrics = run_scenario(f"rate_{rate}", config, verbose)
        results[f"{rate} tankers/h"] = (stats, metrics)

        print(f"  Throughput: {metrics.throughput_per_day:.1f} tankers/day")
        print(f"  Avg Wait:   {metrics.avg_waiting_time:.2f}h")
        print(f"  Max Queue:  {metrics.max_queue_length}")

    return results


def generate_report(results: dict, output_dir: Path):
    """
    Generate a comprehensive report with visualizations.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    print("\n" + "="*70)
    print("GENERATING REPORT AND VISUALIZATIONS")
    print("="*70)

    # Prepare metrics for comparison plots
    metrics_list = [(name, metrics) for name, (stats, metrics) in results.items()]

    # Generate comparison plots
    print("\nGenerating throughput comparison...")
    fig = plot_throughput_comparison(metrics_list, save_path=output_dir / "throughput_comparison.png")
    plt.close(fig)

    print("Generating waiting time comparison...")
    fig = plot_waiting_time_comparison(metrics_list, save_path=output_dir / "waiting_time_comparison.png")
    plt.close(fig)

    print("Generating oil delivery impact...")
    fig = plot_oil_delivery_impact(metrics_list, save_path=output_dir / "oil_delivery_impact.png")
    plt.close(fig)

    # Generate individual scenario dashboards
    for name, (stats, metrics) in results.items():
        safe_name = name.replace(" ", "_").replace("(", "").replace(")", "").replace("%", "pct")
        print(f"Generating dashboard for {name}...")
        save_all_plots(stats, metrics, safe_name, output_dir)

    # Generate summary report text
    report_path = output_dir / "simulation_report.txt"
    with open(report_path, 'w') as f:
        f.write("="*70 + "\n")
        f.write("OIL TANKER FLOW SIMULATION - STRAIT OF HORMUZ\n")
        f.write("Comprehensive Analysis Report\n")
        f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("="*70 + "\n\n")

        for name, (stats, metrics) in results.items():
            f.write(f"\n{'='*60}\n")
            f.write(f"SCENARIO: {name}\n")
            f.write(f"{'='*60}\n")
            f.write(stats.summary_report(168.0))
            f.write("\n")

    print(f"\nReport saved to: {output_dir}")
    print(f"  - Text report: simulation_report.txt")
    print(f"  - Visualizations: *.png")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Oil Tanker Flow Simulator - Strait of Hormuz",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                          Run all scenarios
  %(prog)s --scenario baseline      Run baseline only
  %(prog)s --scenario disruption    Run disruption comparison
  %(prog)s --scenario mitigation    Run mitigation analysis
  %(prog)s --scenario sensitivity   Run sensitivity analysis
  %(prog)s --verbose                Enable detailed output
  %(prog)s --output ./results       Specify output directory
        """
    )

    parser.add_argument(
        '--scenario', '-s',
        choices=['all', 'baseline', 'disruption', 'mitigation', 'sensitivity'],
        default='all',
        help='Scenario to run (default: all)'
    )

    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose output'
    )

    parser.add_argument(
        '--output', '-o',
        type=Path,
        default=Path('./output'),
        help='Output directory for reports (default: ./output)'
    )

    parser.add_argument(
        '--duration',
        type=float,
        default=168.0,
        help='Simulation duration in hours (default: 168 = 1 week)'
    )

    parser.add_argument(
        '--seed',
        type=int,
        default=42,
        help='Random seed for reproducibility (default: 42)'
    )

    args = parser.parse_args()

    print("\n" + "="*70)
    print("   OIL TANKER FLOW SIMULATOR - STRAIT OF HORMUZ")
    print("   Discrete Event Simulation using SimPy")
    print("="*70)
    print(f"\nConfiguration:")
    print(f"  Scenario:  {args.scenario}")
    print(f"  Duration:  {args.duration}h ({args.duration/24:.1f} days)")
    print(f"  Seed:      {args.seed}")
    print(f"  Output:    {args.output}")

    all_results = {}

    try:
        if args.scenario in ['all', 'baseline']:
            stats, metrics = run_baseline_scenario(verbose=args.verbose)
            all_results["Baseline"] = (stats, metrics)

        if args.scenario in ['all', 'disruption']:
            results = run_disruption_scenarios(verbose=args.verbose)
            all_results.update(results)

        if args.scenario in ['all', 'mitigation']:
            results = run_mitigation_analysis(verbose=args.verbose)
            all_results.update(results)

        if args.scenario in ['all', 'sensitivity']:
            results = run_sensitivity_analysis(verbose=args.verbose)
            all_results.update(results)

        # Generate report if we have results
        if all_results:
            generate_report(all_results, args.output)

        print("\n" + "="*70)
        print("SIMULATION COMPLETE")
        print("="*70)
        print(f"\nResults saved to: {args.output.absolute()}")

    except KeyboardInterrupt:
        print("\n\nSimulation interrupted by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\n\nError during simulation: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
