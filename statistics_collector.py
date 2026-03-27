"""
Statistics collection and analysis module for the Oil Tanker Flow Simulation.

Provides comprehensive metrics tracking, aggregation, and analysis capabilities
for simulation runs.
"""

from __future__ import annotations

import statistics as stats
from dataclasses import dataclass, field
from typing import Optional
from collections import defaultdict

from config import TankerType, DisruptionType


@dataclass
class TankerRecord:
    """Record of a single tanker's journey through the simulation."""
    tanker_id: int
    tanker_type: TankerType
    arrival_time: float
    start_transit_time: Optional[float] = None
    end_transit_time: Optional[float] = None
    waiting_time: Optional[float] = None
    transit_time: Optional[float] = None
    total_time: Optional[float] = None
    cargo_barrels: int = 0
    was_rerouted: bool = False
    during_disruption: bool = False


@dataclass
class TimeSeriesPoint:
    """A single point in time series data."""
    time: float
    value: float


@dataclass
class DisruptionRecord:
    """Record of a disruption event."""
    disruption_type: DisruptionType
    start_time: float
    end_time: Optional[float] = None
    capacity_reduction: float = 0.0


@dataclass
class AggregateMetrics:
    """Aggregated metrics for analysis and reporting."""
    # Throughput metrics
    total_tankers_processed: int = 0
    total_tankers_arrived: int = 0
    total_tankers_rerouted: int = 0
    tankers_by_type: dict = field(default_factory=dict)

    # Time metrics (in hours)
    avg_waiting_time: float = 0.0
    max_waiting_time: float = 0.0
    min_waiting_time: float = 0.0
    std_waiting_time: float = 0.0

    avg_transit_time: float = 0.0
    max_transit_time: float = 0.0

    avg_total_time: float = 0.0
    max_total_time: float = 0.0

    # Queue metrics
    avg_queue_length: float = 0.0
    max_queue_length: int = 0
    queue_length_95th: float = 0.0

    # Throughput
    throughput_per_hour: float = 0.0
    throughput_per_day: float = 0.0

    # Oil delivery
    total_oil_delivered_barrels: int = 0
    oil_per_day_barrels: float = 0.0

    # Utilization
    strait_utilization: float = 0.0

    # Disruption impact
    avg_waiting_time_normal: float = 0.0
    avg_waiting_time_disruption: float = 0.0
    throughput_reduction_during_disruption: float = 0.0


class SimulationStatistics:
    """
    Comprehensive statistics collector for simulation runs.

    Tracks all relevant metrics throughout the simulation and provides
    methods for aggregation, analysis, and export.
    """

    def __init__(self, warmup_hours: float = 0.0):
        self.warmup_hours = warmup_hours
        self._in_warmup = True

        # Raw data storage
        self.tanker_records: list[TankerRecord] = []
        self.queue_length_series: list[TimeSeriesPoint] = []
        self.throughput_series: list[TimeSeriesPoint] = []

        # Disruption tracking
        self.disruption_records: list[DisruptionRecord] = []
        self._current_disruption: Optional[DisruptionRecord] = None
        self._disruption_active = False

        # Counters
        self._arrivals_count = 0
        self._completions_count = 0
        self._reroutes_count = 0

        # For incremental throughput calculation
        self._hourly_completions: dict[int, int] = defaultdict(int)

        # Capacity for utilization calculation
        self._total_transit_capacity_hours = 0.0
        self._used_transit_capacity_hours = 0.0

    def end_warmup(self) -> None:
        """Mark the end of the warmup period."""
        self._in_warmup = False

    def record_arrival(self, tanker, time: float) -> None:
        """Record a tanker arrival."""
        if self._in_warmup:
            return

        record = TankerRecord(
            tanker_id=tanker.tanker_id,
            tanker_type=tanker.tanker_type,
            arrival_time=time,
            cargo_barrels=tanker.cargo_barrels,
            during_disruption=self._disruption_active
        )
        self.tanker_records.append(record)
        self._arrivals_count += 1

    def record_transit_start(self, tanker, time: float, queue_length: int) -> None:
        """Record when a tanker begins transit."""
        if self._in_warmup:
            return

        # Update the tanker record
        for record in reversed(self.tanker_records):
            if record.tanker_id == tanker.tanker_id:
                record.start_transit_time = time
                record.waiting_time = time - record.arrival_time
                break

        # Record queue length
        self.queue_length_series.append(TimeSeriesPoint(time=time, value=queue_length))

    def record_completion(self, tanker, time: float) -> None:
        """Record a tanker completing transit."""
        if self._in_warmup:
            return

        # Update the tanker record
        for record in reversed(self.tanker_records):
            if record.tanker_id == tanker.tanker_id:
                record.end_transit_time = time
                if record.start_transit_time is not None:
                    record.transit_time = time - record.start_transit_time
                record.total_time = time - record.arrival_time
                break

        self._completions_count += 1

        # Track hourly completions
        hour = int(time)
        self._hourly_completions[hour] += 1

        # Update capacity utilization
        if tanker.transit_time is not None:
            self._used_transit_capacity_hours += tanker.transit_time

    def record_reroute(self, tanker, time: float) -> None:
        """Record a tanker being rerouted."""
        if self._in_warmup:
            return

        for record in reversed(self.tanker_records):
            if record.tanker_id == tanker.tanker_id:
                record.was_rerouted = True
                break

        self._reroutes_count += 1

    def record_disruption_start(
        self,
        disruption_type: DisruptionType,
        time: float,
        capacity_reduction: float
    ) -> None:
        """Record the start of a disruption."""
        self._disruption_active = True
        self._current_disruption = DisruptionRecord(
            disruption_type=disruption_type,
            start_time=time,
            capacity_reduction=capacity_reduction
        )

    def record_disruption_end(self, disruption_type: DisruptionType, time: float) -> None:
        """Record the end of a disruption."""
        self._disruption_active = False
        if self._current_disruption:
            self._current_disruption.end_time = time
            self.disruption_records.append(self._current_disruption)
            self._current_disruption = None

    def get_tankers_during_disruption(self) -> int:
        """Get count of tankers affected during current disruption."""
        return sum(1 for r in self.tanker_records if r.during_disruption)

    def record_queue_snapshot(self, time: float, queue_length: int) -> None:
        """Record a queue length snapshot for time series."""
        if not self._in_warmup:
            self.queue_length_series.append(TimeSeriesPoint(time=time, value=queue_length))

    def set_total_capacity(self, capacity_hours: float) -> None:
        """Set total available transit capacity for utilization calculation."""
        self._total_transit_capacity_hours = capacity_hours

    def calculate_aggregate_metrics(self, simulation_hours: float) -> AggregateMetrics:
        """
        Calculate all aggregate metrics from collected data.

        Args:
            simulation_hours: Total simulation time in hours

        Returns:
            AggregateMetrics object with all calculated values
        """
        metrics = AggregateMetrics()

        # Filter completed records
        completed = [r for r in self.tanker_records
                     if r.end_transit_time is not None and not r.was_rerouted]

        if not completed:
            return metrics

        # Basic counts
        metrics.total_tankers_processed = len(completed)
        metrics.total_tankers_arrived = self._arrivals_count
        metrics.total_tankers_rerouted = self._reroutes_count

        # Count by type
        for tanker_type in TankerType:
            metrics.tankers_by_type[tanker_type.name] = sum(
                1 for r in completed if r.tanker_type == tanker_type
            )

        # Waiting time statistics
        waiting_times = [r.waiting_time for r in completed if r.waiting_time is not None]
        if waiting_times:
            metrics.avg_waiting_time = stats.mean(waiting_times)
            metrics.max_waiting_time = max(waiting_times)
            metrics.min_waiting_time = min(waiting_times)
            if len(waiting_times) > 1:
                metrics.std_waiting_time = stats.stdev(waiting_times)

        # Transit time statistics
        transit_times = [r.transit_time for r in completed if r.transit_time is not None]
        if transit_times:
            metrics.avg_transit_time = stats.mean(transit_times)
            metrics.max_transit_time = max(transit_times)

        # Total time statistics
        total_times = [r.total_time for r in completed if r.total_time is not None]
        if total_times:
            metrics.avg_total_time = stats.mean(total_times)
            metrics.max_total_time = max(total_times)

        # Queue statistics
        if self.queue_length_series:
            queue_values = [p.value for p in self.queue_length_series]
            metrics.avg_queue_length = stats.mean(queue_values)
            metrics.max_queue_length = int(max(queue_values))
            sorted_queues = sorted(queue_values)
            idx_95 = int(len(sorted_queues) * 0.95)
            metrics.queue_length_95th = sorted_queues[idx_95] if sorted_queues else 0

        # Throughput
        effective_hours = simulation_hours - self.warmup_hours
        if effective_hours > 0:
            metrics.throughput_per_hour = metrics.total_tankers_processed / effective_hours
            metrics.throughput_per_day = metrics.throughput_per_hour * 24

        # Oil delivery
        metrics.total_oil_delivered_barrels = sum(r.cargo_barrels for r in completed)
        if effective_hours > 0:
            metrics.oil_per_day_barrels = (
                metrics.total_oil_delivered_barrels / effective_hours * 24
            )

        # Utilization
        if self._total_transit_capacity_hours > 0:
            metrics.strait_utilization = (
                self._used_transit_capacity_hours / self._total_transit_capacity_hours
            )

        # Disruption impact analysis
        normal_records = [r for r in completed if not r.during_disruption]
        disruption_records = [r for r in completed if r.during_disruption]

        if normal_records:
            normal_waiting = [r.waiting_time for r in normal_records if r.waiting_time]
            if normal_waiting:
                metrics.avg_waiting_time_normal = stats.mean(normal_waiting)

        if disruption_records:
            disruption_waiting = [r.waiting_time for r in disruption_records if r.waiting_time]
            if disruption_waiting:
                metrics.avg_waiting_time_disruption = stats.mean(disruption_waiting)

        # Calculate throughput reduction during disruption
        if metrics.avg_waiting_time_normal > 0 and metrics.avg_waiting_time_disruption > 0:
            metrics.throughput_reduction_during_disruption = (
                (metrics.avg_waiting_time_disruption - metrics.avg_waiting_time_normal)
                / metrics.avg_waiting_time_normal
            )

        return metrics

    def get_time_series_data(self) -> dict:
        """
        Get time series data for plotting.

        Returns:
            Dictionary with time series arrays
        """
        return {
            "queue_length": {
                "times": [p.time for p in self.queue_length_series],
                "values": [p.value for p in self.queue_length_series]
            },
            "disruptions": [
                {"start": d.start_time, "end": d.end_time, "type": d.disruption_type.name}
                for d in self.disruption_records
            ]
        }

    def get_waiting_time_distribution(self) -> dict:
        """
        Get waiting time distribution data.

        Returns:
            Dictionary with distribution statistics
        """
        completed = [r for r in self.tanker_records
                     if r.waiting_time is not None and not r.was_rerouted]

        if not completed:
            return {"times": [], "by_type": {}}

        waiting_times = [r.waiting_time for r in completed]

        by_type = {}
        for tanker_type in TankerType:
            type_times = [r.waiting_time for r in completed
                         if r.tanker_type == tanker_type and r.waiting_time is not None]
            if type_times:
                by_type[tanker_type.name] = {
                    "mean": stats.mean(type_times),
                    "max": max(type_times),
                    "count": len(type_times)
                }

        return {
            "times": waiting_times,
            "by_type": by_type
        }

    def summary_report(self, simulation_hours: float) -> str:
        """
        Generate a text summary report of statistics.

        Args:
            simulation_hours: Total simulation time

        Returns:
            Formatted string report
        """
        metrics = self.calculate_aggregate_metrics(simulation_hours)

        lines = [
            "=" * 70,
            "SIMULATION STATISTICS SUMMARY",
            "=" * 70,
            "",
            "THROUGHPUT METRICS",
            "-" * 40,
            f"  Total Tankers Processed:    {metrics.total_tankers_processed:,}",
            f"  Total Tankers Arrived:      {metrics.total_tankers_arrived:,}",
            f"  Tankers Rerouted:           {metrics.total_tankers_rerouted:,}",
            f"  Throughput (per day):       {metrics.throughput_per_day:.1f} tankers",
            "",
            "  By Tanker Type:",
        ]

        for ttype, count in metrics.tankers_by_type.items():
            lines.append(f"    {ttype:12}: {count:,}")

        lines.extend([
            "",
            "TIMING METRICS (hours)",
            "-" * 40,
            f"  Average Waiting Time:       {metrics.avg_waiting_time:.2f}",
            f"  Maximum Waiting Time:       {metrics.max_waiting_time:.2f}",
            f"  Std Dev Waiting Time:       {metrics.std_waiting_time:.2f}",
            "",
            f"  Average Transit Time:       {metrics.avg_transit_time:.2f}",
            f"  Maximum Transit Time:       {metrics.max_transit_time:.2f}",
            "",
            f"  Average Total Time:         {metrics.avg_total_time:.2f}",
            f"  Maximum Total Time:         {metrics.max_total_time:.2f}",
            "",
            "QUEUE METRICS",
            "-" * 40,
            f"  Average Queue Length:       {metrics.avg_queue_length:.2f}",
            f"  Maximum Queue Length:       {metrics.max_queue_length}",
            f"  95th Percentile Queue:      {metrics.queue_length_95th:.1f}",
            "",
            "OIL DELIVERY",
            "-" * 40,
            f"  Total Oil Delivered:        {metrics.total_oil_delivered_barrels:,} barrels",
            f"  Oil Delivery Rate:          {metrics.oil_per_day_barrels:,.0f} barrels/day",
            "",
            "UTILIZATION",
            "-" * 40,
            f"  Strait Utilization:         {metrics.strait_utilization*100:.1f}%",
        ])

        if metrics.avg_waiting_time_disruption > 0:
            lines.extend([
                "",
                "DISRUPTION IMPACT",
                "-" * 40,
                f"  Avg Wait (Normal):          {metrics.avg_waiting_time_normal:.2f}h",
                f"  Avg Wait (Disruption):      {metrics.avg_waiting_time_disruption:.2f}h",
                f"  Wait Time Increase:         {metrics.throughput_reduction_during_disruption*100:.1f}%",
            ])

        lines.extend(["", "=" * 70])

        return "\n".join(lines)


class MultiRunStatistics:
    """
    Aggregates statistics across multiple simulation runs.

    Used for analyzing results across replications and scenarios.
    """

    def __init__(self):
        self.run_metrics: list[AggregateMetrics] = []
        self.scenario_name: str = ""

    def add_run(self, metrics: AggregateMetrics) -> None:
        """Add metrics from a single run."""
        self.run_metrics.append(metrics)

    def calculate_confidence_interval(
        self,
        values: list[float],
        confidence: float = 0.95
    ) -> tuple[float, float, float]:
        """
        Calculate mean and confidence interval.

        Args:
            values: List of values from multiple runs
            confidence: Confidence level (default 95%)

        Returns:
            Tuple of (mean, lower_bound, upper_bound)
        """
        if not values or len(values) < 2:
            mean_val = values[0] if values else 0.0
            return mean_val, mean_val, mean_val

        import math

        n = len(values)
        mean = stats.mean(values)
        std = stats.stdev(values)

        # t-value for 95% CI (approximation)
        t_values = {5: 2.571, 10: 2.228, 20: 2.086, 30: 2.042}
        t = t_values.get(n, 1.96)

        margin = t * (std / math.sqrt(n))
        return mean, mean - margin, mean + margin

    def summary(self) -> dict:
        """
        Generate summary statistics across all runs.

        Returns:
            Dictionary with mean and CI for key metrics
        """
        if not self.run_metrics:
            return {}

        waiting_times = [m.avg_waiting_time for m in self.run_metrics]
        throughputs = [m.throughput_per_day for m in self.run_metrics]
        queue_lengths = [m.avg_queue_length for m in self.run_metrics]

        return {
            "num_runs": len(self.run_metrics),
            "scenario": self.scenario_name,
            "avg_waiting_time": self.calculate_confidence_interval(waiting_times),
            "throughput_per_day": self.calculate_confidence_interval(throughputs),
            "avg_queue_length": self.calculate_confidence_interval(queue_lengths),
        }
