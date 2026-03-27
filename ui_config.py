"""
UI Configuration for the Oil Tanker Flow Simulation.

Contains all visual settings, colors, dimensions, and UI constants.
"""

from dataclasses import dataclass
from enum import Enum, auto


# Window dimensions
WINDOW_WIDTH = 1400
WINDOW_HEIGHT = 900

# Layout dimensions
STRAIT_PANEL_WIDTH = 900
STATS_PANEL_WIDTH = WINDOW_WIDTH - STRAIT_PANEL_WIDTH
CONTROL_PANEL_HEIGHT = 120
MAP_HEIGHT = WINDOW_HEIGHT - CONTROL_PANEL_HEIGHT

# Strait visualization
STRAIT_X_START = 50
STRAIT_X_END = STRAIT_PANEL_WIDTH - 50
STRAIT_Y_CENTER = MAP_HEIGHT // 2
STRAIT_WIDTH = 200  # Visual width of the navigable channel
STRAIT_LENGTH = STRAIT_X_END - STRAIT_X_START

# Queue visualization
QUEUE_X = STRAIT_X_START - 30
QUEUE_Y_START = STRAIT_Y_CENTER - 250
QUEUE_SPACING = 35

# Tanker sizes (visual, by type)
TANKER_SIZES = {
    "VLCC": (40, 16),
    "SUEZMAX": (35, 14),
    "AFRAMAX": (30, 12),
    "PANAMAX": (25, 10),
}


class Colors:
    """Color palette for the UI."""
    # Background colors
    BACKGROUND = (20, 25, 35)
    PANEL_BG = (30, 35, 50)
    PANEL_BORDER = (60, 70, 90)

    # Water and land
    WATER_DEEP = (15, 40, 80)
    WATER_SHALLOW = (25, 60, 110)
    WATER_CHANNEL = (20, 50, 95)
    LAND_IRAN = (80, 65, 45)
    LAND_UAE = (90, 75, 55)
    LAND_OMAN = (85, 70, 50)

    # Tanker colors by type
    TANKER_VLCC = (220, 80, 60)       # Red-orange
    TANKER_SUEZMAX = (60, 160, 220)   # Blue
    TANKER_AFRAMAX = (80, 200, 120)   # Green
    TANKER_PANAMAX = (220, 180, 60)   # Yellow

    # Tanker states
    TANKER_WAITING = (150, 150, 150)
    TANKER_BLOCKED = (200, 50, 50)
    TANKER_HIGHLIGHT = (255, 255, 255)

    # UI elements
    TEXT_PRIMARY = (240, 240, 245)
    TEXT_SECONDARY = (160, 165, 180)
    TEXT_ACCENT = (100, 180, 255)
    TEXT_WARNING = (255, 180, 60)
    TEXT_DANGER = (255, 80, 80)
    TEXT_SUCCESS = (80, 220, 120)

    # Buttons
    BUTTON_NORMAL = (50, 55, 75)
    BUTTON_HOVER = (70, 75, 100)
    BUTTON_ACTIVE = (90, 95, 120)
    BUTTON_DISABLED = (40, 42, 55)

    # Status indicators
    STATUS_NORMAL = (80, 220, 120)
    STATUS_WARNING = (255, 180, 60)
    STATUS_CRITICAL = (255, 80, 80)
    STATUS_BLOCKED = (180, 40, 40)

    # Disruption overlay
    DISRUPTION_OVERLAY = (255, 60, 60, 40)

    # Grid and guides
    GRID = (40, 45, 60)


# Tanker color mapping
TANKER_COLORS = {
    "VLCC": Colors.TANKER_VLCC,
    "SUEZMAX": Colors.TANKER_SUEZMAX,
    "AFRAMAX": Colors.TANKER_AFRAMAX,
    "PANAMAX": Colors.TANKER_PANAMAX,
}


@dataclass
class UIState:
    """Tracks the current state of the UI."""
    running: bool = False
    paused: bool = False
    speed_multiplier: float = 1.0
    selected_tanker_id: int = -1
    show_grid: bool = False
    show_labels: bool = True
    dark_mode: bool = True


class SimSpeed(Enum):
    """Simulation speed options."""
    SLOW = 0.5
    NORMAL = 1.0
    FAST = 2.0
    VERY_FAST = 5.0
    MAX = 10.0


# Font sizes
FONT_SIZES = {
    "title": 28,
    "header": 20,
    "normal": 16,
    "small": 14,
    "tiny": 12,
}

# Animation settings
ANIMATION_FPS = 60
TANKER_MOVE_SPEED = 2.0  # pixels per frame at normal speed

# Statistics update interval (in simulation time)
STATS_UPDATE_INTERVAL = 0.1  # hours

# Basemap tile configuration (OpenStreetMap standard style)
MAP_TILE_URL_TEMPLATE = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
MAP_TILE_CACHE_DIR = ".tile_cache/osm"
MAP_TILE_MIN_ZOOM = 5
MAP_TILE_MAX_ZOOM = 8
MAP_TILE_TIMEOUT_SECONDS = 3.0
MAP_TILE_ATTRIBUTION = "Map data: OpenStreetMap contributors"
