"""
Entity classes for the Oil Tanker Flow Simulation.

Defines the core simulation entities: Tankers and the Strait of Hormuz.
"""

from __future__ import annotations

import simpy
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional, Generator, Any
from enum import Enum, auto

from config import TankerType, TankerConfig, StraitConfig, MitigationStrategy

if TYPE_CHECKING:
    from statistics_collector import SimulationStatistics


class TankerStatus(Enum):
    """Current status of a tanker in the simulation."""
    APPROACHING = auto()
    WAITING = auto()
    IN_TRANSIT = auto()
    COMPLETED = auto()
    REROUTED = auto()
    BLOCKED = auto()


@dataclass
class Tanker:
    """
    Represents an oil tanker vessel in the simulation.

    Attributes:
        tanker_id: Unique identifier
        tanker_type: Classification (VLCC, Suezmax, etc.)
        config: Configuration parameters for this tanker type
        arrival_time: Simulation time when tanker arrived at strait
        start_transit_time: Time when transit began
        end_transit_time: Time when transit completed
        status: Current status of the tanker
        priority: Scheduling priority (used with priority mitigation)
    """
    tanker_id: int
    tanker_type: TankerType
    config: TankerConfig
    arrival_time: float = 0.0
    start_transit_time: Optional[float] = None
    end_transit_time: Optional[float] = None
    status: TankerStatus = TankerStatus.APPROACHING
    priority: int = 1
    cargo_barrels: int = 0

    def __post_init__(self):
        self.cargo_barrels = self.config.capacity_barrels
        self.priority = self.config.priority

    @property
    def waiting_time(self) -> Optional[float]:
        """Calculate time spent waiting in queue."""
        if self.start_transit_time is not None:
            return self.start_transit_time - self.arrival_time
        return None

    @property
    def transit_time(self) -> Optional[float]:
        """Calculate actual transit time through strait."""
        if self.start_transit_time is not None and self.end_transit_time is not None:
            return self.end_transit_time - self.start_transit_time
        return None

    @property
    def total_time(self) -> Optional[float]:
        """Calculate total time from arrival to completion."""
        if self.end_transit_time is not None:
            return self.end_transit_time - self.arrival_time
        return None

    def __repr__(self) -> str:
        return f"Tanker({self.tanker_id}, {self.tanker_type.name}, {self.status.name})"


class StraitOfHormuz:
    """
    Represents the Strait of Hormuz as a SimPy resource.

    Models the strait as a limited capacity resource that tankers must
    acquire before transiting. Supports priority-based scheduling and
    disruption handling.
    """

    def __init__(
        self,
        env: simpy.Environment,
        config: StraitConfig,
        statistics: 'SimulationStatistics',
        mitigation_strategy: MitigationStrategy = MitigationStrategy.NONE,
        verbose: bool = False
    ):
        self.env = env
        self.config = config
        self.statistics = statistics
        self.mitigation_strategy = mitigation_strategy
        self.verbose = verbose

        # Create the main transit resource
        if mitigation_strategy == MitigationStrategy.PRIORITY_SCHEDULING:
            self._resource = simpy.PriorityResource(
                env,
                capacity=config.max_concurrent_transits
            )
        else:
            self._resource = simpy.Resource(
                env,
                capacity=config.max_concurrent_transits
            )

        # Disruption state
        self._disruption_active = False
        self._current_capacity_reduction = 0.0
        self._current_transit_multiplier = 1.0
        self._blocked = False

        # Queue tracking
        self._queue: list[Tanker] = []
        self._in_transit: list[Tanker] = []

    @property
    def current_capacity(self) -> int:
        """Get current effective capacity accounting for disruptions."""
        if self._blocked:
            return 0
        base_capacity = self.config.max_concurrent_transits
        reduction = int(base_capacity * self._current_capacity_reduction)
        return max(0, base_capacity - reduction)

    @property
    def queue_length(self) -> int:
        """Current number of tankers waiting."""
        return len(self._queue)

    @property
    def in_transit_count(self) -> int:
        """Current number of tankers in transit."""
        return len(self._in_transit)

    def activate_disruption(
        self,
        capacity_reduction: float,
        transit_multiplier: float,
        is_complete_blockade: bool = False
    ) -> None:
        """
        Activate a disruption scenario.

        Args:
            capacity_reduction: Fraction of capacity to reduce (0.0 to 1.0)
            transit_multiplier: Factor to multiply transit times
            is_complete_blockade: If True, completely block the strait
        """
        self._disruption_active = True
        self._current_capacity_reduction = capacity_reduction
        self._current_transit_multiplier = transit_multiplier
        self._blocked = is_complete_blockade

        if self.verbose:
            print(f"[{self.env.now:.1f}h] DISRUPTION ACTIVATED: "
                  f"capacity={self.current_capacity}, "
                  f"transit_multiplier={transit_multiplier:.1f}x, "
                  f"blocked={is_complete_blockade}")

    def deactivate_disruption(self) -> None:
        """Deactivate current disruption, restoring normal operations."""
        self._disruption_active = False
        self._current_capacity_reduction = 0.0
        self._current_transit_multiplier = 1.0
        self._blocked = False

        if self.verbose:
            print(f"[{self.env.now:.1f}h] DISRUPTION ENDED: Normal operations resumed")

    def get_transit_time(self, tanker: Tanker) -> float:
        """
        Calculate transit time for a specific tanker.

        Args:
            tanker: The tanker to calculate transit time for

        Returns:
            Transit time in hours
        """
        base_time = tanker.config.transit_time_hours
        return base_time * self._current_transit_multiplier

    def process_tanker(self, tanker: Tanker) -> Generator[Any, Any, None]:
        """
        Process a tanker through the strait.

        This is the main simulation process for each tanker.

        Args:
            tanker: The tanker to process

        Yields:
            SimPy events for resource acquisition and transit
        """
        tanker.arrival_time = self.env.now
        tanker.status = TankerStatus.WAITING
        self._queue.append(tanker)

        if self.verbose:
            print(f"[{self.env.now:.1f}h] {tanker} ARRIVED, queue length: {self.queue_length}")

        # Record arrival
        self.statistics.record_arrival(tanker, self.env.now)

        # Check if strait is completely blocked
        while self._blocked:
            tanker.status = TankerStatus.BLOCKED
            yield self.env.timeout(1.0)  # Check every hour

            # If mitigation allows rerouting, handle it
            if self.mitigation_strategy == MitigationStrategy.ALTERNATIVE_ROUTING:
                if self.env.now - tanker.arrival_time > 24.0:  # Wait max 24 hours
                    tanker.status = TankerStatus.REROUTED
                    self._queue.remove(tanker)
                    self.statistics.record_reroute(tanker, self.env.now)
                    if self.verbose:
                        print(f"[{self.env.now:.1f}h] {tanker} REROUTED via Cape of Good Hope")
                    return

        # Request access to the strait
        if self.mitigation_strategy == MitigationStrategy.PRIORITY_SCHEDULING:
            # Higher priority = lower number in SimPy
            priority = 10 - tanker.priority
            request = self._resource.request(priority=priority)
        else:
            request = self._resource.request()

        try:
            yield request

            # Start transit
            self._queue.remove(tanker)
            self._in_transit.append(tanker)
            tanker.start_transit_time = self.env.now
            tanker.status = TankerStatus.IN_TRANSIT

            # Record queue statistics at transit start
            self.statistics.record_transit_start(tanker, self.env.now, self.queue_length)

            if self.verbose:
                wait_time = tanker.waiting_time
                print(f"[{self.env.now:.1f}h] {tanker} STARTED TRANSIT "
                      f"(waited {wait_time:.1f}h)")

            # Transit through strait
            transit_time = self.get_transit_time(tanker)
            yield self.env.timeout(transit_time)

            # Safety separation delay
            separation_hours = self.config.safety_separation_minutes / 60.0
            yield self.env.timeout(separation_hours)

            # Complete transit
            self._in_transit.remove(tanker)
            tanker.end_transit_time = self.env.now
            tanker.status = TankerStatus.COMPLETED

            # Record completion
            self.statistics.record_completion(tanker, self.env.now)

            if self.verbose:
                print(f"[{self.env.now:.1f}h] {tanker} COMPLETED TRANSIT "
                      f"(transit={tanker.transit_time:.1f}h, total={tanker.total_time:.1f}h)")

        finally:
            self._resource.release(request)

    def get_state_snapshot(self) -> dict:
        """Get current state of the strait for monitoring."""
        return {
            "time": self.env.now,
            "queue_length": self.queue_length,
            "in_transit": self.in_transit_count,
            "capacity": self.current_capacity,
            "disruption_active": self._disruption_active,
            "blocked": self._blocked,
            "transit_multiplier": self._current_transit_multiplier
        }
