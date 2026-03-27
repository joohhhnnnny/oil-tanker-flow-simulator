"""
Disruption scenario handlers for the Oil Tanker Flow Simulation.

Manages the lifecycle of various disruption events including blockades,
weather delays, and military exercises.
"""

from __future__ import annotations

import simpy
from typing import TYPE_CHECKING, Generator, Any, Callable, Optional
from dataclasses import dataclass

from config import DisruptionType, DisruptionConfig

if TYPE_CHECKING:
    from entities import StraitOfHormuz
    from statistics import SimulationStatistics


@dataclass
class DisruptionEvent:
    """Records details of a disruption event."""
    disruption_type: DisruptionType
    start_time: float
    end_time: Optional[float]
    capacity_reduction: float
    transit_multiplier: float
    tankers_affected: int = 0
    tankers_rerouted: int = 0


class DisruptionManager:
    """
    Manages disruption scenarios during simulation.

    Handles the timing and activation of disruptions, their effects on
    the strait, and recovery after disruptions end.
    """

    def __init__(
        self,
        env: simpy.Environment,
        strait: 'StraitOfHormuz',
        config: DisruptionConfig,
        statistics: 'SimulationStatistics',
        verbose: bool = False
    ):
        self.env = env
        self.strait = strait
        self.config = config
        self.statistics = statistics
        self.verbose = verbose

        self.current_event: Optional[DisruptionEvent] = None
        self.events_history: list[DisruptionEvent] = []

        # Event callbacks for external monitoring
        self._on_disruption_start: list[Callable] = []
        self._on_disruption_end: list[Callable] = []

    def register_callback(
        self,
        on_start: Optional[Callable] = None,
        on_end: Optional[Callable] = None
    ) -> None:
        """Register callbacks for disruption events."""
        if on_start:
            self._on_disruption_start.append(on_start)
        if on_end:
            self._on_disruption_end.append(on_end)

    def run(self) -> Generator[Any, Any, None]:
        """
        Main disruption management process.

        This should be started as a SimPy process to handle disruption
        timing automatically.

        Yields:
            SimPy events for disruption timing
        """
        if self.config.disruption_type == DisruptionType.NONE:
            return

        # Wait until disruption start time
        if self.config.start_time_hours > 0:
            yield self.env.timeout(self.config.start_time_hours)

        # Activate disruption
        yield from self._activate_disruption()

        # If duration is specified, wait and then deactivate
        if self.config.duration_hours is not None:
            yield self.env.timeout(self.config.duration_hours)
            yield from self._deactivate_disruption()

    def _activate_disruption(self) -> Generator[Any, Any, None]:
        """Activate the configured disruption."""
        is_complete_blockade = (
            self.config.disruption_type == DisruptionType.COMPLETE_BLOCKADE
        )

        # Create event record
        self.current_event = DisruptionEvent(
            disruption_type=self.config.disruption_type,
            start_time=self.env.now,
            end_time=None,
            capacity_reduction=self.config.capacity_reduction,
            transit_multiplier=self.config.transit_time_multiplier
        )

        # Apply disruption to strait
        self.strait.activate_disruption(
            capacity_reduction=self.config.capacity_reduction,
            transit_multiplier=self.config.transit_time_multiplier,
            is_complete_blockade=is_complete_blockade
        )

        # Record in statistics
        self.statistics.record_disruption_start(
            self.config.disruption_type,
            self.env.now,
            self.config.capacity_reduction
        )

        # Notify callbacks
        for callback in self._on_disruption_start:
            callback(self.current_event)

        if self.verbose:
            print(f"\n{'='*60}")
            print(f"DISRUPTION EVENT: {self.config.disruption_type.name}")
            print(f"Start Time: {self.env.now:.1f}h")
            print(f"Capacity Reduction: {self.config.capacity_reduction*100:.0f}%")
            print(f"Transit Time Multiplier: {self.config.transit_time_multiplier:.1f}x")
            if self.config.duration_hours:
                print(f"Expected Duration: {self.config.duration_hours:.1f}h")
            print(f"{'='*60}\n")

        yield self.env.timeout(0)  # Yield control

    def _deactivate_disruption(self) -> Generator[Any, Any, None]:
        """Deactivate the current disruption."""
        if self.current_event is None:
            return

        # Update event record
        self.current_event.end_time = self.env.now

        # Count affected tankers
        self.current_event.tankers_affected = self.statistics.get_tankers_during_disruption()

        # Store in history
        self.events_history.append(self.current_event)

        # Deactivate on strait
        self.strait.deactivate_disruption()

        # Record in statistics
        self.statistics.record_disruption_end(
            self.config.disruption_type,
            self.env.now
        )

        # Notify callbacks
        for callback in self._on_disruption_end:
            callback(self.current_event)

        if self.verbose:
            print(f"\n{'='*60}")
            print(f"DISRUPTION ENDED: {self.config.disruption_type.name}")
            print(f"Duration: {self.env.now - self.current_event.start_time:.1f}h")
            print(f"Tankers Affected: {self.current_event.tankers_affected}")
            print(f"{'='*60}\n")

        self.current_event = None
        yield self.env.timeout(0)


class PartialBlockadeHandler:
    """
    Specialized handler for partial blockade scenarios.

    Models scenarios where only certain vessel types are affected
    or where capacity is reduced but not eliminated.
    """

    def __init__(
        self,
        env: simpy.Environment,
        strait: 'StraitOfHormuz',
        affected_types: list,
        capacity_reduction: float = 0.5
    ):
        self.env = env
        self.strait = strait
        self.affected_types = affected_types
        self.capacity_reduction = capacity_reduction

    def is_tanker_affected(self, tanker_type) -> bool:
        """Check if a tanker type is affected by the blockade."""
        if not self.affected_types:
            return True  # All types affected
        return tanker_type in self.affected_types


class CompleteBlockadeHandler:
    """
    Handler for complete blockade scenarios.

    Models scenarios where the strait is completely closed to traffic.
    """

    def __init__(
        self,
        env: simpy.Environment,
        strait: 'StraitOfHormuz',
        allow_rerouting: bool = True,
        max_wait_before_reroute_hours: float = 24.0
    ):
        self.env = env
        self.strait = strait
        self.allow_rerouting = allow_rerouting
        self.max_wait_hours = max_wait_before_reroute_hours
        self.rerouted_tankers: list = []

    def get_alternative_route_time(self) -> float:
        """
        Get estimated time for alternative route (Cape of Good Hope).

        Returns:
            Additional transit time in hours
        """
        # Cape of Good Hope route adds approximately 15-20 days
        return 15 * 24  # 15 days in hours


class WeatherDelayHandler:
    """
    Handler for weather-related delays.

    Models temporary slowdowns due to adverse weather conditions.
    """

    def __init__(
        self,
        env: simpy.Environment,
        strait: 'StraitOfHormuz',
        severity: float = 0.5  # 0.0 (mild) to 1.0 (severe)
    ):
        self.env = env
        self.strait = strait
        self.severity = severity

    def get_delay_multiplier(self) -> float:
        """Calculate transit time multiplier based on weather severity."""
        # Mild weather: 1.2x, Severe: 2.5x
        return 1.0 + (1.5 * self.severity)

    def get_capacity_impact(self) -> float:
        """Calculate capacity reduction based on weather severity."""
        # Mild weather: 10% reduction, Severe: 50% reduction
        return 0.1 + (0.4 * self.severity)


def create_disruption_manager(
    env: simpy.Environment,
    strait: 'StraitOfHormuz',
    config: DisruptionConfig,
    statistics: 'SimulationStatistics',
    verbose: bool = False
) -> DisruptionManager:
    """
    Factory function to create appropriate disruption manager.

    Args:
        env: SimPy environment
        strait: The strait resource
        config: Disruption configuration
        statistics: Statistics collector
        verbose: Enable verbose output

    Returns:
        Configured DisruptionManager instance
    """
    return DisruptionManager(
        env=env,
        strait=strait,
        config=config,
        statistics=statistics,
        verbose=verbose
    )
