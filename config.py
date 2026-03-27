"""
Configuration module for Oil Tanker Flow Simulation.

Contains all simulation parameters, constants, and configuration classes
for the Strait of Hormuz tanker flow disruption simulation.
"""

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional


class TankerType(Enum):
    """Classification of oil tankers by size."""
    VLCC = auto()      # Very Large Crude Carrier (200,000+ DWT)
    SUEZMAX = auto()   # Suezmax (120,000-200,000 DWT)
    AFRAMAX = auto()   # Aframax (80,000-120,000 DWT)
    PANAMAX = auto()   # Panamax (60,000-80,000 DWT)


class DisruptionType(Enum):
    """Types of disruption scenarios."""
    NONE = auto()
    PARTIAL_BLOCKADE = auto()
    COMPLETE_BLOCKADE = auto()
    WEATHER_DELAY = auto()
    MILITARY_EXERCISE = auto()


class MitigationStrategy(Enum):
    """Available mitigation strategies."""
    NONE = auto()
    PRIORITY_SCHEDULING = auto()    # Priority based on cargo urgency/tanker size
    CONVOY_SYSTEM = auto()          # Group tankers into convoys
    ALTERNATIVE_ROUTING = auto()    # Reroute via alternative paths


@dataclass
class TankerConfig:
    """Configuration for tanker types and their properties."""
    tanker_type: TankerType
    capacity_barrels: int           # Cargo capacity in barrels
    transit_time_hours: float       # Base transit time through strait
    proportion: float               # Proportion of total traffic
    priority: int = 1               # Scheduling priority (higher = more urgent)

    @property
    def transit_time_minutes(self) -> float:
        return self.transit_time_hours * 60


# Default tanker configurations based on real-world data
DEFAULT_TANKER_CONFIGS = {
    TankerType.VLCC: TankerConfig(
        tanker_type=TankerType.VLCC,
        capacity_barrels=2_000_000,
        transit_time_hours=8.0,
        proportion=0.45,
        priority=4
    ),
    TankerType.SUEZMAX: TankerConfig(
        tanker_type=TankerType.SUEZMAX,
        capacity_barrels=1_000_000,
        transit_time_hours=6.0,
        proportion=0.30,
        priority=3
    ),
    TankerType.AFRAMAX: TankerConfig(
        tanker_type=TankerType.AFRAMAX,
        capacity_barrels=700_000,
        transit_time_hours=5.0,
        proportion=0.15,
        priority=2
    ),
    TankerType.PANAMAX: TankerConfig(
        tanker_type=TankerType.PANAMAX,
        capacity_barrels=500_000,
        transit_time_hours=4.0,
        proportion=0.10,
        priority=1
    ),
}


@dataclass
class StraitConfig:
    """Configuration for the Strait of Hormuz."""
    # Physical characteristics
    width_nautical_miles: float = 21.0
    navigable_width_nm: float = 6.0         # Two 2-mile-wide channels + buffer
    length_nautical_miles: float = 100.0

    # Capacity constraints
    max_concurrent_transits: int = 3        # Vessels that can transit simultaneously
    safety_separation_minutes: float = 30.0  # Minimum time between vessels

    # Traffic patterns (tankers per day - approximately 15-17 per day in reality)
    mean_arrival_rate_per_hour: float = 0.7  # ~17 tankers per day

    # Operating hours
    daylight_hours_only: bool = False        # If True, only operate during day


@dataclass
class DisruptionConfig:
    """Configuration for disruption scenarios."""
    disruption_type: DisruptionType = DisruptionType.NONE

    # Timing
    start_time_hours: float = 0.0           # When disruption begins
    duration_hours: Optional[float] = None   # Duration (None = indefinite)

    # Impact parameters
    capacity_reduction: float = 0.0          # 0.0 to 1.0 (1.0 = complete blockade)
    transit_time_multiplier: float = 1.0     # Increase in transit time

    # Partial blockade specific
    affected_tanker_types: list = field(default_factory=list)  # Types affected


@dataclass
class SimulationConfig:
    """Main simulation configuration."""
    # Simulation time
    duration_hours: float = 168.0           # Default: 1 week (168 hours)
    warmup_hours: float = 24.0              # Warmup period to reach steady state

    # Random seed for reproducibility
    random_seed: Optional[int] = 42

    # Number of replications for statistical validity
    num_replications: int = 10

    # Components
    strait_config: StraitConfig = field(default_factory=StraitConfig)
    disruption_config: DisruptionConfig = field(default_factory=DisruptionConfig)
    mitigation_strategy: MitigationStrategy = MitigationStrategy.NONE
    tanker_configs: dict = field(default_factory=lambda: DEFAULT_TANKER_CONFIGS.copy())

    # Output settings
    verbose: bool = False
    collect_detailed_logs: bool = True


# Predefined scenario configurations
SCENARIOS = {
    "baseline": SimulationConfig(
        disruption_config=DisruptionConfig(disruption_type=DisruptionType.NONE),
        mitigation_strategy=MitigationStrategy.NONE
    ),

    "partial_blockade": SimulationConfig(
        disruption_config=DisruptionConfig(
            disruption_type=DisruptionType.PARTIAL_BLOCKADE,
            start_time_hours=48.0,
            duration_hours=72.0,
            capacity_reduction=0.5,
            transit_time_multiplier=1.5
        ),
        mitigation_strategy=MitigationStrategy.NONE
    ),

    "complete_blockade": SimulationConfig(
        disruption_config=DisruptionConfig(
            disruption_type=DisruptionType.COMPLETE_BLOCKADE,
            start_time_hours=48.0,
            duration_hours=48.0,
            capacity_reduction=1.0
        ),
        mitigation_strategy=MitigationStrategy.NONE
    ),

    "partial_with_priority": SimulationConfig(
        disruption_config=DisruptionConfig(
            disruption_type=DisruptionType.PARTIAL_BLOCKADE,
            start_time_hours=48.0,
            duration_hours=72.0,
            capacity_reduction=0.5,
            transit_time_multiplier=1.5
        ),
        mitigation_strategy=MitigationStrategy.PRIORITY_SCHEDULING
    ),

    "weather_delay": SimulationConfig(
        disruption_config=DisruptionConfig(
            disruption_type=DisruptionType.WEATHER_DELAY,
            start_time_hours=24.0,
            duration_hours=12.0,
            capacity_reduction=0.3,
            transit_time_multiplier=2.0
        ),
        mitigation_strategy=MitigationStrategy.NONE
    ),
}
