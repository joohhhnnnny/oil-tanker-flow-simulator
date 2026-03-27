"""
Core simulation module for the Oil Tanker Flow Simulation.

This module ties together all components and provides the main simulation
runner functionality.
"""

from __future__ import annotations

import random
from typing import Generator, Any, Optional

import simpy

from config import (
    SimulationConfig, TankerType, DisruptionType,
    MitigationStrategy, DEFAULT_TANKER_CONFIGS
)
from entities import Tanker, StraitOfHormuz
from statistics_collector import SimulationStatistics, AggregateMetrics, MultiRunStatistics
from disruptions import DisruptionManager, create_disruption_manager


class TankerGenerator:
    """
    Generates tanker arrivals according to configured arrival patterns.

    Uses exponential inter-arrival times to model a Poisson arrival process,
    which is typical for maritime traffic models.
    """

    def __init__(
        self,
        env: simpy.Environment,
        strait: StraitOfHormuz,
        config: SimulationConfig,
        rng: random.Random
    ):
        self.env = env
        self.strait = strait
        self.config = config
        self.rng = rng
        self._tanker_counter = 0

    def _select_tanker_type(self) -> TankerType:
        """
        Select tanker type based on configured proportions.

        Returns:
            Selected TankerType
        """
        r = self.rng.random()
        cumulative = 0.0

        for tanker_type, tanker_config in self.config.tanker_configs.items():
            cumulative += tanker_config.proportion
            if r <= cumulative:
                return tanker_type

        # Fallback to last type
        return list(self.config.tanker_configs.keys())[-1]

    def _create_tanker(self) -> Tanker:
        """
        Create a new tanker instance.

        Returns:
            New Tanker object
        """
        self._tanker_counter += 1
        tanker_type = self._select_tanker_type()
        tanker_config = self.config.tanker_configs[tanker_type]

        return Tanker(
            tanker_id=self._tanker_counter,
            tanker_type=tanker_type,
            config=tanker_config
        )

    def run(self) -> Generator[Any, Any, None]:
        """
        Main generator process.

        Continuously generates tankers at random intervals.

        Yields:
            SimPy timeout events for inter-arrival times
        """
        while True:
            # Generate inter-arrival time (exponential distribution)
            mean_interarrival = 1.0 / self.config.strait_config.mean_arrival_rate_per_hour
            interarrival_time = self.rng.expovariate(1.0 / mean_interarrival)

            yield self.env.timeout(interarrival_time)

            # Create and process tanker
            tanker = self._create_tanker()
            self.env.process(self.strait.process_tanker(tanker))


class QueueMonitor:
    """
    Monitors queue length at regular intervals.

    Provides periodic snapshots for time series analysis.
    """

    def __init__(
        self,
        env: simpy.Environment,
        strait: StraitOfHormuz,
        statistics: SimulationStatistics,
        interval_hours: float = 1.0
    ):
        self.env = env
        self.strait = strait
        self.statistics = statistics
        self.interval = interval_hours

    def run(self) -> Generator[Any, Any, None]:
        """Monitor queue at regular intervals."""
        while True:
            yield self.env.timeout(self.interval)
            self.statistics.record_queue_snapshot(
                self.env.now,
                self.strait.queue_length
            )


class OilTankerSimulation:
    """
    Main simulation class that orchestrates the entire simulation.

    Manages the simulation environment, all components, and execution.
    """

    def __init__(self, config: SimulationConfig):
        self.config = config
        self.env: Optional[simpy.Environment] = None
        self.strait: Optional[StraitOfHormuz] = None
        self.statistics: Optional[SimulationStatistics] = None
        self.disruption_manager: Optional[DisruptionManager] = None

        # Random number generator for reproducibility
        self.rng = random.Random(config.random_seed)

    def setup(self) -> None:
        """Initialize all simulation components."""
        # Create SimPy environment
        self.env = simpy.Environment()

        # Create statistics collector
        self.statistics = SimulationStatistics(
            warmup_hours=self.config.warmup_hours
        )

        # Create the strait
        self.strait = StraitOfHormuz(
            env=self.env,
            config=self.config.strait_config,
            statistics=self.statistics,
            mitigation_strategy=self.config.mitigation_strategy,
            verbose=self.config.verbose
        )

        # Create disruption manager
        self.disruption_manager = create_disruption_manager(
            env=self.env,
            strait=self.strait,
            config=self.config.disruption_config,
            statistics=self.statistics,
            verbose=self.config.verbose
        )

        # Create tanker generator
        self.generator = TankerGenerator(
            env=self.env,
            strait=self.strait,
            config=self.config,
            rng=self.rng
        )

        # Create queue monitor
        self.monitor = QueueMonitor(
            env=self.env,
            strait=self.strait,
            statistics=self.statistics
        )

    def _warmup_complete(self) -> Generator[Any, Any, None]:
        """Process to mark end of warmup period."""
        yield self.env.timeout(self.config.warmup_hours)
        self.statistics.end_warmup()
        if self.config.verbose:
            print(f"\n[{self.env.now:.1f}h] WARMUP PERIOD COMPLETE - Statistics collection started\n")

    def run(self) -> AggregateMetrics:
        """
        Execute the simulation.

        Returns:
            AggregateMetrics with simulation results
        """
        # Setup components
        self.setup()

        # Start processes
        self.env.process(self.generator.run())
        self.env.process(self.monitor.run())
        self.env.process(self.disruption_manager.run())

        # Handle warmup period
        if self.config.warmup_hours > 0:
            self.env.process(self._warmup_complete())

        # Set total capacity for utilization calculation
        effective_hours = self.config.duration_hours - self.config.warmup_hours
        total_capacity = (
            effective_hours *
            self.config.strait_config.max_concurrent_transits
        )
        self.statistics.set_total_capacity(total_capacity)

        # Run simulation
        if self.config.verbose:
            print(f"\n{'='*60}")
            print(f"STARTING SIMULATION")
            print(f"Duration: {self.config.duration_hours}h ({self.config.duration_hours/24:.1f} days)")
            print(f"Warmup: {self.config.warmup_hours}h")
            print(f"Disruption: {self.config.disruption_config.disruption_type.name}")
            print(f"Mitigation: {self.config.mitigation_strategy.name}")
            print(f"{'='*60}\n")

        self.env.run(until=self.config.duration_hours)

        # Calculate and return metrics
        metrics = self.statistics.calculate_aggregate_metrics(
            self.config.duration_hours
        )

        if self.config.verbose:
            print(self.statistics.summary_report(self.config.duration_hours))

        return metrics

    def run_multiple(self, num_runs: int, verbose_runs: bool = False) -> MultiRunStatistics:
        """
        Run multiple replications for statistical validity.

        Args:
            num_runs: Number of replications
            verbose_runs: Show progress for each run

        Returns:
            MultiRunStatistics with aggregated results
        """
        multi_stats = MultiRunStatistics()

        base_seed = self.config.random_seed or 42

        for i in range(num_runs):
            # Update seed for each run
            self.config.random_seed = base_seed + i
            self.rng = random.Random(self.config.random_seed)

            # Temporarily disable verbose for individual runs
            original_verbose = self.config.verbose
            self.config.verbose = verbose_runs

            metrics = self.run()
            multi_stats.add_run(metrics)

            self.config.verbose = original_verbose

            if not verbose_runs:
                print(f"  Completed run {i+1}/{num_runs}")

        return multi_stats


def run_scenario(
    scenario_name: str,
    config: SimulationConfig,
    verbose: bool = False
) -> tuple[SimulationStatistics, AggregateMetrics]:
    """
    Run a single scenario and return results.

    Args:
        scenario_name: Name of the scenario
        config: Simulation configuration
        verbose: Enable verbose output

    Returns:
        Tuple of (SimulationStatistics, AggregateMetrics)
    """
    config.verbose = verbose
    sim = OilTankerSimulation(config)
    metrics = sim.run()

    return sim.statistics, metrics


def compare_scenarios(
    scenarios: dict[str, SimulationConfig],
    verbose: bool = False
) -> dict[str, tuple[SimulationStatistics, AggregateMetrics]]:
    """
    Run and compare multiple scenarios.

    Args:
        scenarios: Dictionary mapping scenario names to configurations
        verbose: Enable verbose output

    Returns:
        Dictionary mapping scenario names to (statistics, metrics) tuples
    """
    results = {}

    for name, config in scenarios.items():
        print(f"\nRunning scenario: {name}")
        print("-" * 40)

        stats, metrics = run_scenario(name, config, verbose)
        results[name] = (stats, metrics)

        # Print summary
        print(f"  Throughput: {metrics.throughput_per_day:.1f} tankers/day")
        print(f"  Avg Wait:   {metrics.avg_waiting_time:.2f}h")
        print(f"  Max Wait:   {metrics.max_waiting_time:.2f}h")
        print(f"  Oil/Day:    {metrics.oil_per_day_barrels/1e6:.2f}M barrels")

    return results


def run_mitigation_comparison(
    base_disruption_config,
    duration_hours: float = 168.0,
    num_runs: int = 5
) -> dict[str, MultiRunStatistics]:
    """
    Compare different mitigation strategies for a given disruption.

    Args:
        base_disruption_config: Disruption configuration to test
        duration_hours: Simulation duration
        num_runs: Number of runs per strategy

    Returns:
        Dictionary mapping strategy names to multi-run statistics
    """
    strategies = [
        MitigationStrategy.NONE,
        MitigationStrategy.PRIORITY_SCHEDULING,
        MitigationStrategy.CONVOY_SYSTEM,
        MitigationStrategy.ALTERNATIVE_ROUTING,
    ]

    results = {}

    for strategy in strategies:
        print(f"\nTesting mitigation: {strategy.name}")
        print("-" * 40)

        config = SimulationConfig(
            duration_hours=duration_hours,
            disruption_config=base_disruption_config,
            mitigation_strategy=strategy,
            verbose=False
        )

        sim = OilTankerSimulation(config)
        multi_stats = sim.run_multiple(num_runs, verbose_runs=False)
        multi_stats.scenario_name = strategy.name
        results[strategy.name] = multi_stats

        summary = multi_stats.summary()
        mean_wait, lower, upper = summary["avg_waiting_time"]
        print(f"  Avg Wait: {mean_wait:.2f}h (95% CI: [{lower:.2f}, {upper:.2f}])")

    return results
