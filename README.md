# Oil Tanker Flow Simulator - Strait of Hormuz

A professional Discrete Event Simulation (DES) model for analyzing oil tanker traffic flow through the Strait of Hormuz, including disruption scenarios and mitigation strategies.

## Overview

The Strait of Hormuz is one of the world's most critical maritime chokepoints, handling approximately 20% of global oil trade. This simulator models:

- **Normal tanker traffic flow** with realistic arrival patterns
- **Disruption scenarios** (partial blockades, complete blockades, weather delays)
- **Mitigation strategies** (priority scheduling, alternative routing)
- **Key performance metrics** (waiting times, throughput, oil delivery rates)

## Features

- Realistic tanker type distribution (VLCC, Suezmax, Aframax, Panamax)
- Configurable strait capacity and transit times
- Multiple disruption scenario modeling
- Statistical analysis with confidence intervals
- **Real-time web map UI** powered by Leaflet + Leaflet.Motion
- **OpenStreetMap basemap** with geospatial route overlays
- **WebSocket streaming** for live tanker state updates
- Comprehensive visualization and reporting
- Reproducible results via random seeding

## Installation

```bash
# Clone or download the project
cd oil-tanker-flow-simulator

# Create virtual environment (recommended)
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

## Quick Start

### Real-Time Web Visualization (Recommended)

```bash
# Launch FastAPI backend + Leaflet frontend
python ui_app.py
```

Then open `http://localhost:8000` in your browser.

The web UI provides:
- **Leaflet map visualization** of the Strait region with OSM tiles
- **Animated tanker movement** with Leaflet.Motion smoothing
- **Interactive controls** for start/pause/resume/stop
- **Scenario and mitigation selection**
- **Speed control** (0.5x to 10x)
- **Live metrics panel** fed by WebSocket snapshots

### Command-Line Interface

```bash
# Run all scenarios with default settings
python main.py

# Run specific scenario
python main.py --scenario baseline
python main.py --scenario disruption
python main.py --scenario mitigation

# Enable verbose output
python main.py --verbose

# Custom duration and output
python main.py --duration 336 --output ./my_results
```

## Project Structure

```
oil-tanker-flow-simulator/
├── ui_app.py               # FastAPI + WebSocket simulation server
├── web/
│   ├── index.html          # Leaflet UI shell
│   ├── app.js              # Realtime map logic + controls
│   └── styles.css          # UI styling
├── ui_config.py            # Shared timing constants
├── geo_layout.py           # Geospatial lane definitions
├── main.py                 # CLI entry point
├── config.py               # Configuration and parameters
├── entities.py             # Tanker and Strait classes
├── simulation.py           # Core simulation engine
├── disruptions.py          # Disruption scenario handlers
├── statistics_collector.py # Statistics and metrics
├── visualization.py        # Matplotlib plotting
├── requirements.txt        # Python dependencies
└── README.md               # This file
```

## Web UI Controls

| Control | Action |
|---------|--------|
| **Start** | Begin simulation |
| **Pause** | Pause simulation |
| **Resume** | Resume simulation |
| **Stop** | Stop and reset simulation |
| **Speed Dropdown** | Adjust simulation speed (0.5x - 10x) |
| **Scenario Dropdown** | Select disruption scenario |
| **Mitigation Dropdown** | Select mitigation strategy |
| **Hover Tanker** | Show tanker ID/type/direction |

## Configuration

### Tanker Types

| Type     | Capacity (barrels) | Transit Time | Proportion | Color |
|----------|-------------------|--------------|------------|-------|
| VLCC     | 2,000,000         | 8 hours      | 45%        | Red   |
| Suezmax  | 1,000,000         | 6 hours      | 30%        | Blue  |
| Aframax  | 700,000           | 5 hours      | 15%        | Green |
| Panamax  | 500,000           | 4 hours      | 10%        | Yellow|

### Strait Parameters

- **Arrival Rate**: ~0.7 tankers/hour (~17/day)
- **Concurrent Transits**: 3 vessels maximum
- **Safety Separation**: 30 minutes between vessels

### Disruption Scenarios

1. **No Disruption**: Normal operations
2. **Partial Blockade**: 50% capacity reduction for 24 hours
3. **Complete Blockade**: Full closure for 12 hours
4. **Weather Delay**: 30% reduction with 2x transit time

### Mitigation Strategies

- **None**: No mitigation applied
- **Priority Scheduling**: Larger tankers get priority
- **Alternative Routing**: Reroute via Cape of Good Hope after 24h wait

## Output

### Web UI Statistics Panel

The real-time web UI displays:
- **Sim Time**: Current simulation time (hours/days)
- **Arrivals**: Total tankers arrived
- **Completed**: Total tankers that completed transit
- **Queue**: Current queue length (red warning if > 10)
- **In Transit**: Tankers currently in the strait
- **Avg Wait**: Average waiting time
- **Max Wait**: Maximum waiting time
- **Throughput**: Tankers per day
- **Oil Delivered**: Total oil transported (million barrels)

### CLI Output

The CLI generates:
1. **Text Report** (`simulation_report.txt`): Detailed statistics
2. **Dashboards** (`*_dashboard.png`): Per-scenario visualizations
3. **Comparisons**: Cross-scenario metric charts

## Example Usage

### Custom Scenario (Programmatic)

```python
from config import SimulationConfig, DisruptionConfig, DisruptionType
from simulation import OilTankerSimulation

config = SimulationConfig(
    duration_hours=336,  # 2 weeks
    warmup_hours=48,
    disruption_config=DisruptionConfig(
        disruption_type=DisruptionType.PARTIAL_BLOCKADE,
        start_time_hours=72,
        duration_hours=96,
        capacity_reduction=0.6
    ),
    verbose=True
)

sim = OilTankerSimulation(config)
metrics = sim.run()

print(f"Throughput: {metrics.throughput_per_day:.1f} tankers/day")
print(f"Avg Wait: {metrics.avg_waiting_time:.2f} hours")
```

### Multiple Replications

```python
from simulation import OilTankerSimulation
from config import SimulationConfig

config = SimulationConfig(duration_hours=168)
sim = OilTankerSimulation(config)

# Run 10 replications for statistical validity
multi_stats = sim.run_multiple(num_runs=10)
summary = multi_stats.summary()

mean, lower, upper = summary["avg_waiting_time"]
print(f"Avg Wait: {mean:.2f}h (95% CI: [{lower:.2f}, {upper:.2f}])")
```

## Technical Details

### Simulation Model

- **Arrival Process**: Poisson (exponential inter-arrival times)
- **Service Process**: Deterministic transit times with disruption multipliers
- **Queue Discipline**: FIFO or Priority (configurable)
- **Resources**: Strait modeled as SimPy Resource with capacity

### Web Architecture

- **FastAPI**: Control endpoints and static frontend hosting
- **WebSocket**: `/ws/state` stream for live simulation snapshots
- **Leaflet**: Geospatial rendering on OpenStreetMap tiles
- **Leaflet.Motion**: Smooth visual movement trails between updates
- **Threading + SimPy**: Simulation engine runs in background thread

### Statistics Collection

- Warmup period to reach steady state
- Time-series data for queue dynamics
- Per-tanker-type breakdowns
- Normal vs. disruption period comparisons

## API Endpoints

- `GET /state`: Current simulation snapshot
- `GET /routes`: Geospatial lanes and chokepoints
- `POST /start`: Start simulation with selected parameters
- `POST /pause`: Pause simulation clock
- `POST /resume`: Resume simulation clock
- `POST /stop`: Stop simulation
- `POST /speed`: Update simulation speed multiplier
- `WS /ws/state`: Realtime stream of ship and metrics updates

## Requirements

- Python 3.9+
- SimPy 4.0+
- FastAPI 0.115+
- Uvicorn 0.30+
- Matplotlib 3.5+
- NumPy 1.20+

## References

This simulation is based on real-world data about:
- Strait of Hormuz geography and traffic patterns
- Oil tanker classifications and capacities
- Historical disruption events
- EIA and maritime industry reports

## License

MIT License
