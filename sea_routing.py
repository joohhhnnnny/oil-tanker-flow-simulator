"""
Sea routing module for the Oil Tanker Flow Simulator.

Uses Natural Earth 10m land polygons for accurate land detection and
implements A* pathfinding for realistic sea routes that avoid land.
"""

from __future__ import annotations

import heapq
import math
import pickle
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import LineString, Point, box
from shapely.prepared import prep
from shapely.strtree import STRtree

# Type aliases
LatLon = Tuple[float, float]

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Bounding box for Persian Gulf / Gulf of Oman region
REGION_BOUNDS = {
    "min_lat": 22.5,
    "max_lat": 30.0,
    "min_lon": 48.0,
    "max_lon": 62.0,
}

# Grid resolution for A* routing (degrees)
GRID_RESOLUTION = 0.02  # ~2.2 km at this latitude

# Path to Natural Earth data
NE_DATA_DIR = Path("/home/johnbenedict/Downloads/10m_physical")

# Cache file for precomputed ocean grid
CACHE_DIR = Path(__file__).parent / ".route_cache"
OCEAN_GRID_CACHE = CACHE_DIR / "ocean_grid.pkl"
LAND_GEOMETRY_CACHE = CACHE_DIR / "land_geometry.pkl"


class LandDetector:
    """Detects whether coordinates are on land using Natural Earth data."""

    def __init__(self, ne_data_dir: Path = NE_DATA_DIR):
        self.ne_data_dir = ne_data_dir
        self._land_gdf: Optional[gpd.GeoDataFrame] = None
        self._prepared_geom = None
        self._spatial_index: Optional[STRtree] = None
        self._region_land = None

    def _load_data(self) -> None:
        """Load and prepare land geometry data."""
        if self._prepared_geom is not None:
            return

        # Check cache first
        CACHE_DIR.mkdir(exist_ok=True)
        if LAND_GEOMETRY_CACHE.exists():
            try:
                with open(LAND_GEOMETRY_CACHE, "rb") as f:
                    cached = pickle.load(f)
                    self._region_land = cached["region_land"]
                    self._prepared_geom = prep(self._region_land)
                    return
            except Exception as e:
                print(f"[LandDetector] Cache load failed: {e}")

        print("[LandDetector] Loading Natural Earth data...")

        # Load main land polygons
        land_shp = self.ne_data_dir / "ne_10m_land.shp"
        if not land_shp.exists():
            raise FileNotFoundError(f"Land shapefile not found: {land_shp}")

        self._land_gdf = gpd.read_file(land_shp)

        # Load minor islands (important for Strait of Hormuz)
        minor_islands_shp = self.ne_data_dir / "ne_10m_minor_islands.shp"
        if minor_islands_shp.exists():
            minor_islands = gpd.read_file(minor_islands_shp)
            self._land_gdf = gpd.GeoDataFrame(
                pd.concat([self._land_gdf, minor_islands], ignore_index=True),
                crs=self._land_gdf.crs,
            )
            print(f"[LandDetector] Loaded {len(minor_islands)} minor islands")

        # Clip to region of interest for faster queries
        region_box = box(
            REGION_BOUNDS["min_lon"],
            REGION_BOUNDS["min_lat"],
            REGION_BOUNDS["max_lon"],
            REGION_BOUNDS["max_lat"],
        )

        # Clip land to region
        self._land_gdf = self._land_gdf.clip(region_box)

        # Combine all land into single geometry for faster point-in-polygon
        self._region_land = self._land_gdf.union_all()
        self._prepared_geom = prep(self._region_land)

        print(f"[LandDetector] Loaded {len(self._land_gdf)} land features")

        # Cache for future use
        try:
            with open(LAND_GEOMETRY_CACHE, "wb") as f:
                pickle.dump({"region_land": self._region_land}, f)
            print("[LandDetector] Cached land geometry")
        except Exception as e:
            print(f"[LandDetector] Failed to cache: {e}")

    def is_on_land(self, lat: float, lon: float) -> bool:
        """Check if a point is on land."""
        self._load_data()
        point = Point(lon, lat)  # Note: shapely uses (x, y) = (lon, lat)
        return self._prepared_geom.contains(point)

    def is_in_water(self, lat: float, lon: float) -> bool:
        """Check if a point is in water."""
        return not self.is_on_land(lat, lon)

    def filter_water_points(self, points: List[LatLon]) -> List[LatLon]:
        """Filter a list of points to only include those in water."""
        self._load_data()
        return [(lat, lon) for lat, lon in points if self.is_in_water(lat, lon)]


class OceanGrid:
    """Pre-computed grid of ocean points for A* routing."""

    def __init__(
        self,
        land_detector: LandDetector,
        resolution: float = GRID_RESOLUTION,
        bounds: Dict = REGION_BOUNDS,
        coast_buffer_deg: float = 0.025,
    ):
        self.land_detector = land_detector
        self.resolution = resolution
        self.bounds = bounds
        self.coast_buffer_deg = coast_buffer_deg
        self._grid: Set[Tuple[int, int]] = set()
        self._lat_to_idx: Dict[float, int] = {}
        self._lon_to_idx: Dict[float, int] = {}
        self._idx_to_lat: Dict[int, float] = {}
        self._idx_to_lon: Dict[int, float] = {}

    def _snap_to_grid(self, lat: float, lon: float) -> Tuple[int, int]:
        """Snap a coordinate to the nearest grid point."""
        lat_idx = round((lat - self.bounds["min_lat"]) / self.resolution)
        lon_idx = round((lon - self.bounds["min_lon"]) / self.resolution)
        return (lat_idx, lon_idx)

    def _idx_to_coord(self, lat_idx: int, lon_idx: int) -> LatLon:
        """Convert grid indices to coordinates."""
        lat = self.bounds["min_lat"] + lat_idx * self.resolution
        lon = self.bounds["min_lon"] + lon_idx * self.resolution
        return (lat, lon)

    def build(self, force_rebuild: bool = False) -> None:
        """Build the ocean grid, using cache if available."""
        CACHE_DIR.mkdir(exist_ok=True)

        # Try loading from cache
        if not force_rebuild and OCEAN_GRID_CACHE.exists():
            try:
                with open(OCEAN_GRID_CACHE, "rb") as f:
                    cached = pickle.load(f)
                    cached_resolution = float(cached.get("resolution", -1.0))
                    cached_bounds = cached.get("bounds")
                    cached_buffer = float(cached.get("coast_buffer_deg", 0.0))
                    if (
                        cached_resolution == float(self.resolution)
                        and cached_bounds == self.bounds
                        and cached_buffer == float(self.coast_buffer_deg)
                        and "grid" in cached
                    ):
                        self._grid = cached["grid"]
                        print(f"[OceanGrid] Loaded {len(self._grid)} ocean points from cache")
                        return
                    print("[OceanGrid] Cache metadata mismatch; rebuilding ocean grid")
            except Exception as e:
                print(f"[OceanGrid] Cache load failed: {e}")

        print(f"[OceanGrid] Building ocean grid (coast_buffer={self.coast_buffer_deg}deg, may take a minute)...")

        # Build buffered land geometry for coast safety margin.
        # This keeps A* routes at least coast_buffer_deg away from any coastline,
        # so routes appear clearly in open water on high-resolution basemaps.
        self.land_detector._load_data()
        if self.coast_buffer_deg > 0:
            buffered_land = self.land_detector._region_land.buffer(self.coast_buffer_deg)
            check_geom = prep(buffered_land)
            def _is_navigable(lat: float, lon: float) -> bool:
                return not check_geom.contains(Point(lon, lat))
        else:
            def _is_navigable(lat: float, lon: float) -> bool:
                return self.land_detector.is_in_water(lat, lon)

        # Generate grid points
        lat_range = np.arange(
            self.bounds["min_lat"],
            self.bounds["max_lat"] + self.resolution,
            self.resolution,
        )
        lon_range = np.arange(
            self.bounds["min_lon"],
            self.bounds["max_lon"] + self.resolution,
            self.resolution,
        )

        total_points = len(lat_range) * len(lon_range)
        water_count = 0

        for lat_idx, lat in enumerate(lat_range):
            for lon_idx, lon in enumerate(lon_range):
                if _is_navigable(lat, lon):
                    self._grid.add((lat_idx, lon_idx))
                    water_count += 1

            # Progress indicator
            if lat_idx % 50 == 0:
                pct = (lat_idx * len(lon_range)) / total_points * 100
                print(f"  {pct:.1f}% complete...")

        print(f"[OceanGrid] Built grid: {water_count} water points out of {total_points}")

        # Cache the grid
        try:
            with open(OCEAN_GRID_CACHE, "wb") as f:
                pickle.dump(
                    {
                        "grid": self._grid,
                        "resolution": self.resolution,
                        "bounds": self.bounds,
                        "coast_buffer_deg": self.coast_buffer_deg,
                    },
                    f,
                )
            print("[OceanGrid] Cached ocean grid")
        except Exception as e:
            print(f"[OceanGrid] Failed to cache: {e}")

    def is_navigable(self, lat: float, lon: float) -> bool:
        """Check if a coordinate is in navigable water (on the grid)."""
        idx = self._snap_to_grid(lat, lon)
        return idx in self._grid

    def get_neighbors(self, lat_idx: int, lon_idx: int) -> List[Tuple[int, int]]:
        """Get navigable neighbors for a grid cell."""
        # 8-directional movement
        moves = [
            (0, 1), (0, -1), (1, 0), (-1, 0),  # Cardinal
            (1, 1), (1, -1), (-1, 1), (-1, -1),  # Diagonal
        ]

        neighbors = []
        for dlat, dlon in moves:
            n = (lat_idx + dlat, lon_idx + dlon)
            if n in self._grid:
                neighbors.append(n)

        return neighbors


class SeaRouter:
    """A* pathfinding for sea routes that avoid land."""

    def __init__(self, ocean_grid: OceanGrid):
        self.ocean_grid = ocean_grid

    def _heuristic(self, a: Tuple[int, int], b: Tuple[int, int]) -> float:
        """Heuristic function (Euclidean distance in grid units)."""
        return math.hypot(a[0] - b[0], a[1] - b[1])

    def _movement_cost(self, current: Tuple[int, int], neighbor: Tuple[int, int]) -> float:
        """Cost of moving from current to neighbor."""
        # Diagonal moves cost sqrt(2), cardinal moves cost 1
        dlat = abs(neighbor[0] - current[0])
        dlon = abs(neighbor[1] - current[1])
        if dlat + dlon == 2:  # Diagonal
            return 1.414
        return 1.0

    def _segment_crosses_land(self, a: LatLon, b: LatLon) -> bool:
        """Check if straight segment between points cuts across land interior."""
        return route_intersects_land([a, b], safety_margin_deg=0.002)

    def _simplify_path(self, path: List[LatLon], max_skip: int = 20) -> List[LatLon]:
        """Simplify an A* path by skipping unnecessary intermediate points over open water."""
        if len(path) < 3:
            return path

        simplified: List[LatLon] = [path[0]]
        i = 0
        last = len(path) - 1

        while i < last:
            best_j = i + 1
            upper = min(last, i + max_skip)

            for j in range(upper, i + 1, -1):
                if not self._segment_crosses_land(path[i], path[j]):
                    best_j = j
                    break

            simplified.append(path[best_j])
            i = best_j

        return simplified

    def find_route(
        self,
        start: LatLon,
        goal: LatLon,
        waypoints: Optional[List[LatLon]] = None,
    ) -> Optional[List[LatLon]]:
        """
        Find a sea route from start to goal, optionally via waypoints.

        Returns a list of (lat, lon) coordinates, or None if no route found.
        """
        if waypoints:
            # Route through each waypoint
            full_path = []
            points = [start] + list(waypoints) + [goal]

            for i in range(len(points) - 1):
                raw_segment = self._find_segment(points[i], points[i + 1])
                if raw_segment is None:
                    return None

                segment = self._simplify_path(raw_segment)
                valid, _ = validate_route(segment)
                if not valid:
                    segment = raw_segment

                # Avoid duplicating connection points
                if full_path and segment:
                    full_path.extend(segment[1:])
                else:
                    full_path.extend(segment)

            return full_path
        else:
            raw_segment = self._find_segment(start, goal)
            if raw_segment is None:
                return None

            segment = self._simplify_path(raw_segment)
            valid, _ = validate_route(segment)
            if not valid:
                return raw_segment
            return segment

    def _find_segment(self, start: LatLon, goal: LatLon) -> Optional[List[LatLon]]:
        """Find route between two points using A*."""
        grid = self.ocean_grid

        # Snap to grid
        start_idx = grid._snap_to_grid(start[0], start[1])
        goal_idx = grid._snap_to_grid(goal[0], goal[1])

        # Check if start/goal are navigable
        if start_idx not in grid._grid:
            # Find nearest navigable point
            start_idx = self._find_nearest_navigable(start_idx)
            if start_idx is None:
                print(f"[SeaRouter] Start {start} not navigable")
                return None

        if goal_idx not in grid._grid:
            goal_idx = self._find_nearest_navigable(goal_idx)
            if goal_idx is None:
                print(f"[SeaRouter] Goal {goal} not navigable")
                return None

        # A* algorithm
        open_set = []
        heapq.heappush(open_set, (0, start_idx))

        came_from: Dict[Tuple[int, int], Tuple[int, int]] = {}
        g_score: Dict[Tuple[int, int], float] = {start_idx: 0}

        iterations = 0
        max_iterations = 100000

        while open_set and iterations < max_iterations:
            iterations += 1
            _, current = heapq.heappop(open_set)

            # Goal reached?
            if current == goal_idx:
                # Reconstruct path
                path = [current]
                while current in came_from:
                    current = came_from[current]
                    path.append(current)
                path.reverse()

                # Convert to coordinates
                coords = [grid._idx_to_coord(idx[0], idx[1]) for idx in path]
                if coords:
                    # Preserve exact endpoints from caller for stable route anchors.
                    coords[0] = start
                    coords[-1] = goal
                return coords

            # Explore neighbors
            for neighbor in grid.get_neighbors(current[0], current[1]):
                tentative_g = g_score[current] + self._movement_cost(current, neighbor)

                if neighbor not in g_score or tentative_g < g_score[neighbor]:
                    came_from[neighbor] = current
                    g_score[neighbor] = tentative_g
                    f_score = tentative_g + self._heuristic(neighbor, goal_idx)
                    heapq.heappush(open_set, (f_score, neighbor))

        print(f"[SeaRouter] No route found after {iterations} iterations")
        return None

    def _find_nearest_navigable(
        self, idx: Tuple[int, int], max_search: int = 20
    ) -> Optional[Tuple[int, int]]:
        """Find the nearest navigable grid point."""
        grid = self.ocean_grid

        for radius in range(1, max_search):
            for dlat in range(-radius, radius + 1):
                for dlon in range(-radius, radius + 1):
                    if abs(dlat) == radius or abs(dlon) == radius:
                        candidate = (idx[0] + dlat, idx[1] + dlon)
                        if candidate in grid._grid:
                            return candidate
        return None


# ---------------------------------------------------------------------------
# High-level API
# ---------------------------------------------------------------------------

_land_detector: Optional[LandDetector] = None
_ocean_grid: Optional[OceanGrid] = None
_sea_router: Optional[SeaRouter] = None


def get_land_detector() -> LandDetector:
    """Get or create the singleton LandDetector."""
    global _land_detector
    if _land_detector is None:
        _land_detector = LandDetector()
    return _land_detector


def get_ocean_grid() -> OceanGrid:
    """Get or create the singleton OceanGrid."""
    global _ocean_grid
    if _ocean_grid is None:
        _ocean_grid = OceanGrid(get_land_detector())
        _ocean_grid.build()
    return _ocean_grid


def get_sea_router() -> SeaRouter:
    """Get or create the singleton SeaRouter."""
    global _sea_router
    if _sea_router is None:
        _sea_router = SeaRouter(get_ocean_grid())
    return _sea_router


def is_on_land(lat: float, lon: float) -> bool:
    """Check if a point is on land."""
    return get_land_detector().is_on_land(lat, lon)


def is_in_water(lat: float, lon: float) -> bool:
    """Check if a point is in water."""
    return get_land_detector().is_in_water(lat, lon)


def find_sea_route(
    start: LatLon,
    goal: LatLon,
    waypoints: Optional[List[LatLon]] = None,
) -> Optional[List[LatLon]]:
    """
    Find a sea route from start to goal that avoids land.

    Args:
        start: Starting coordinates (lat, lon)
        goal: Goal coordinates (lat, lon)
        waypoints: Optional list of intermediate waypoints

    Returns:
        List of (lat, lon) coordinates forming the route, or None if no route found.
    """
    return get_sea_router().find_route(start, goal, waypoints)


def clean_route(path: List[LatLon]) -> List[LatLon]:
    """Filter a route to only include points that are in water."""
    return get_land_detector().filter_water_points(path)


def route_intersects_land(path: List[LatLon], safety_margin_deg: float = 0.0) -> bool:
    """Check if any segment of a route intersects land geometry."""
    if len(path) < 2:
        return False

    detector = get_land_detector()
    detector._load_data()
    if detector._region_land is None:
        return False

    land_geom = detector._region_land.buffer(safety_margin_deg) if safety_margin_deg > 0.0 else detector._region_land
    line = LineString([(lon, lat) for (lat, lon) in path])

    # Treat endpoint/coastline touching as acceptable, but reject true crossings.
    if line.within(land_geom) or line.crosses(land_geom):
        return True
    if line.intersects(land_geom) and not line.touches(land_geom):
        return True
    return False


def validate_route(
    path: List[LatLon],
    allow_terminal_landfall: bool = True,
    terminal_tolerance_points: int = 3,
) -> Tuple[bool, List[int]]:
    """
    Validate that a route doesn't cross land.

    Returns:
        Tuple of (is_valid, list of issue indices).
        Issue indices include on-land point indices and segment-start indices for
        sampled segment crossings.
    """
    detector = get_land_detector()
    issue_indices: List[int] = []

    last_idx = len(path) - 1
    tolerance = max(1, terminal_tolerance_points)

    for i, (lat, lon) in enumerate(path):
        if allow_terminal_landfall and (i < tolerance or i > last_idx - tolerance):
            continue
        if detector.is_on_land(lat, lon):
            issue_indices.append(i)

    # Segment sampling catches cases where endpoints are water but the segment
    # still cuts across land.
    for i in range(len(path) - 1):
        if allow_terminal_landfall and (i < tolerance or i > (len(path) - 2 - tolerance)):
            continue

        a_lat, a_lon = path[i]
        b_lat, b_lon = path[i + 1]
        delta = max(abs(b_lat - a_lat), abs(b_lon - a_lon))
        samples = max(1, int(delta / 0.01))

        crossing_found = False
        for s in range(1, samples):
            t = s / samples
            lat = a_lat + (b_lat - a_lat) * t
            lon = a_lon + (b_lon - a_lon) * t
            if detector.is_on_land(lat, lon):
                issue_indices.append(i)
                crossing_found = True
                break

        if crossing_found:
            continue

    # Line-level geometry check as a final guard.
    line_check_path = path
    if allow_terminal_landfall and len(path) > (2 * tolerance + 1):
        line_check_path = path[tolerance:-tolerance]

    if route_intersects_land(line_check_path):
        issue_indices.append(-1)

    deduped = sorted(set(issue_indices))
    return (len(deduped) == 0, deduped)


if __name__ == "__main__":
    # Test the routing system
    print("Testing Sea Routing System")
    print("=" * 50)

    # Test land detection
    print("\n1. Testing land detection...")
    detector = get_land_detector()

    test_points = [
        (26.5, 56.0, "Strait of Hormuz (water)"),
        (25.0, 51.5, "Qatar (land)"),
        (26.0, 50.5, "Bahrain area"),
        (24.5, 54.5, "UAE coast"),
        (27.0, 56.5, "Near Qeshm Island"),
    ]

    for lat, lon, name in test_points:
        on_land = detector.is_on_land(lat, lon)
        print(f"  {name}: {'LAND' if on_land else 'WATER'}")

    # Test A* routing
    print("\n2. Testing A* routing...")

    # Ras Tanura to Fujairah
    start = (26.643, 50.159)  # Ras Tanura
    goal = (25.115, 56.385)  # Fujairah

    print(f"  Finding route from Ras Tanura to Fujairah...")
    route = find_sea_route(start, goal)

    if route:
        print(f"  Found route with {len(route)} points")
        print(f"  First 3: {route[:3]}")
        print(f"  Last 3: {route[-3:]}")

        # Validate
        valid, land_pts = validate_route(route)
        print(f"  Route valid: {valid} (land crossings: {len(land_pts)})")
    else:
        print("  No route found!")
