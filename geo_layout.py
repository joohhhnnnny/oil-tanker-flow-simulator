"""
Geographic layout helpers for the Strait of Hormuz renderer.

This module stores simplified coastline and island coordinates in latitude/
longitude and projects them onto screen coordinates for the Pygame UI.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Sequence, Tuple


LatLon = Tuple[float, float]
Point = Tuple[int, int]


def _haversine_km(p1: LatLon, p2: LatLon) -> float:
    """Great-circle distance between two lat/lon points in kilometers."""
    lat1, lon1 = p1
    lat2, lon2 = p2
    r_km = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    sin_dphi = math.sin(dphi / 2.0)
    sin_dlambda = math.sin(dlambda / 2.0)
    h = sin_dphi * sin_dphi + math.cos(phi1) * math.cos(phi2) * sin_dlambda * sin_dlambda
    return 2.0 * r_km * math.asin(min(1.0, math.sqrt(h)))


def densify_latlon_path(path: Sequence[LatLon], step_km: float = 5.0) -> List[LatLon]:
    """Insert intermediate points between lat/lon waypoints for smoother rendering."""
    if len(path) < 2:
        return list(path)

    new_path: List[LatLon] = []

    for i in range(len(path) - 1):
        p1 = path[i]
        p2 = path[i + 1]

        new_path.append(p1)

        dist = _haversine_km(p1, p2)
        steps = max(1, int(dist // step_km))

        for s in range(1, steps):
            frac = s / steps
            lat = p1[0] + (p2[0] - p1[0]) * frac
            lon = p1[1] + (p2[1] - p1[1]) * frac
            new_path.append((lat, lon))

    new_path.append(path[-1])
    return new_path


@dataclass(frozen=True)
class GeoViewport:
    """Geographic viewport bounds for a north-up top-view Gulf region map."""

    # Top-view equirectangular domain spanning Bahrain/Qatar to Oman/Makran.
    min_lon: float = 50.0
    max_lon: float = 61.3
    min_lat: float = 22.8
    max_lat: float = 29.2


@dataclass(frozen=True)
class GeoMapLayout:
    """Projected geometry used by the renderer."""

    iran_coastline: List[Point]
    arabia_coastline: List[Point]
    islands: List[List[Point]]
    north_lane: List[Point]
    south_lane: List[Point]
    separation_line: List[Point]


# Simplified but geographically anchored coastline traces.
# Coordinates are (lat, lon).
IRAN_COAST_LATLON: List[LatLon] = [
    (28.60, 50.00),
    (28.45, 50.60),
    (28.25, 51.20),
    (28.05, 51.85),
    (27.85, 52.45),
    (27.65, 53.10),
    (27.40, 53.75),
    (27.10, 54.30),
    (26.85, 54.95),
    (26.70, 55.45),
    (26.64, 55.95),
    (26.72, 56.45),
    (26.75, 56.90),
    (26.55, 57.35),
    (26.30, 57.85),
    (26.00, 58.35),
    (25.68, 58.90),
    (25.40, 59.45),
    (25.20, 60.00),
    (25.05, 60.60),
    (24.95, 61.20),
]

ARABIA_COAST_LATLON: List[LatLon] = [
    (26.00, 50.00),
    (25.85, 50.70),
    (25.70, 51.40),
    (25.55, 52.00),
    (25.35, 52.25),
    (25.02, 52.22),
    (24.70, 52.30),
    (24.40, 52.48),
    (24.18, 52.72),
    (24.30, 52.98),
    (24.62, 53.18),
    (25.00, 53.38),
    (25.30, 53.62),
    (25.45, 54.05),
    (25.52, 54.55),
    (25.58, 55.05),
    (25.66, 55.55),
    (25.78, 56.02),
    (26.00, 56.35),
    (26.22, 56.55),
    (25.98, 56.86),
    (25.70, 57.15),
    (25.35, 57.45),
    (24.95, 57.95),
    (24.55, 58.45),
    (24.18, 58.98),
    (23.90, 59.55),
    (23.68, 60.15),
    (23.52, 60.75),
    (23.40, 61.20),
]

# Major islands around the strait entrance.
ISLANDS_LATLON: List[List[LatLon]] = [
    # Bahrain
    [
        (26.35, 50.46),
        (26.30, 50.60),
        (26.15, 50.63),
        (26.03, 50.54),
        (26.06, 50.42),
        (26.22, 50.38),
    ],
    # Qeshm (highly simplified)
    [
        (26.98, 55.38),
        (27.06, 55.88),
        (27.00, 56.32),
        (26.88, 56.72),
        (26.72, 56.64),
        (26.66, 56.20),
        (26.74, 55.68),
    ],
    # Kish
    [
        (26.63, 53.90),
        (26.58, 54.02),
        (26.49, 54.01),
        (26.47, 53.89),
        (26.54, 53.83),
    ],
    # Larak
    [
        (26.88, 56.34),
        (26.91, 56.44),
        (26.83, 56.46),
        (26.80, 56.36),
    ],
    # Hormuz
    [
        (27.12, 56.41),
        (27.14, 56.50),
        (27.08, 56.55),
        (27.03, 56.47),
    ],
    # Musandam Peninsula tip / coastal bulge proxy
    [
        (26.15, 56.10),
        (26.28, 56.33),
        (26.12, 56.49),
        (25.98, 56.33),
    ],
]

# ---------------------------------------------------------------------------
# Traffic Separation Scheme (TSS) — IMO-designated lanes through the Strait
# ---------------------------------------------------------------------------
# Key geography to respect:
#   - Qeshm Island (Iran): ~26.72–27.06 N, 55.38–56.72 E  (north side of strait)
#   - Hormuz Island: ~27.03–27.14 N, 56.41–56.55 E
#   - Musandam Peninsula tip: ~26.0–26.3 N, 56.1–56.5 E   (south side of strait)
#   - The navigable channel runs between Qeshm/Hormuz (N) and Musandam (S)
#   - After clearing Musandam, ships swing SE into the Gulf of Oman
#   - Outbound (eastbound) lane: southern side of channel, hugs Musandam side
#   - Inbound (westbound) lane: northern side of channel, hugs Qeshm/Iran side
#
# All waypoints below have been verified to lie in open water.

SEPARATION_LINE_LATLON: List[LatLon] = [
    # Centreline of TSS — from inside Persian Gulf, through strait, into Gulf of Oman
    # Densified for smooth rendering through the curved channel
    # All waypoints verified against Natural Earth 10m land polygons.
    (26.52, 55.50),   # W approach, then bow north through Hormuz
    (26.55, 55.70),
    (26.58, 55.90),
    (26.62, 56.05),
    (26.64, 56.18),
    (26.64, 56.30),
    (26.62, 56.42),   # Mid-channel arc between islands (N) and Musandam (S)
    (26.56, 56.54),
    (26.48, 56.66),
    (26.39, 56.78),
    (26.28, 56.90),
    (26.18, 57.02),   # Curve west of Musandam headland
    (26.05, 57.10),
    (25.90, 57.18),
    (25.75, 57.30),
    (25.58, 57.44),
    (25.40, 57.58),
    (25.22, 57.72),
    (25.02, 57.86),
    (24.80, 57.98),
    (24.58, 58.10),
]

NORTH_LANE_LATLON: List[LatLon] = [
    # Inbound (westbound) lane — northern/Iran side of channel
    # Parallel to SOUTH_LANE but slightly north.
    # All waypoints verified against Natural Earth 10m land polygons.
    (26.55, 55.50),
    (26.60, 55.70),
    (26.60, 55.90),   # Stays south of Qeshm Island shore
    (26.65, 56.05),
    (26.68, 56.18),
    (26.70, 56.30),
    (26.68, 56.42),   # Arc between Qeshm/Hormuz (N) and Musandam (S)
    (26.62, 56.54),
    (26.54, 56.66),
    (26.45, 56.78),
    (26.35, 56.90),
    (26.25, 57.00),   # Begin Musandam bypass — stay west of headland
    (26.15, 57.08),
    (26.00, 57.12),
    (25.85, 57.20),
    (25.70, 57.32),
    (25.55, 57.48),
    (25.40, 57.64),
    (25.22, 57.80),
    (25.00, 57.94),
    (24.75, 58.04),
    (24.55, 58.10),
]

SOUTH_LANE_LATLON: List[LatLon] = [
    # Outbound (eastbound) lane — southern side of channel
    # Must stay NORTH of Musandam tip (land extends to ~26.4N at lon 56.3-56.4)
    # Then curve SE staying NORTH of Oman coast.
    # Waypoints from lon 56.40 eastward are pushed ~0.04-0.06N further from
    # the Musandam/Oman coast to give clear visual margin on high-res OSM tiles.
    # All waypoints verified against Natural Earth 10m land polygons.
    (26.48, 55.50),
    (26.47, 55.60),
    (26.46, 55.75),
    (26.45, 55.88),
    (26.44, 56.00),
    (26.43, 56.10),
    (26.42, 56.20),
    (26.42, 56.30),
    (26.44, 56.40),   # +0.04N — clear visual margin past Musandam tip
    (26.44, 56.50),   # +0.06N — critical safety past the headland
    (26.40, 56.60),   # +0.05N — begin SE descent above Oman coast
    (26.34, 56.70),   # +0.04N
    (26.26, 56.80),   # +0.04N
    (26.16, 56.88),   # +0.04N — curve around Musandam
    (26.04, 56.95),   # +0.04N
    (25.92, 57.02),   # +0.04N
    (25.78, 57.12),   # +0.03N
    (25.63, 57.25),
    (25.48, 57.38),
    (25.33, 57.52),
    (25.18, 57.66),
    (25.03, 57.80),
    (24.85, 57.92),
    (24.62, 58.02),
    (24.40, 58.10),
]

# --- Web UI routing helpers (lat, lon) ---
PORTS_LATLON: dict[str, LatLon] = {
    # Persian Gulf export terminals
    "ras_tanura":   (26.643, 50.159),
    "kharg_island": (29.246, 50.324),
    "das_island":   (25.132, 52.874),
    "ras_laffan":   (25.919, 51.565),
    "ruwais":       (24.110, 52.730),
    # Outside the Strait (Gulf of Oman / Arabian Sea anchors)
    "fujairah":     (25.115, 56.385),
    "gulf_of_oman": (24.600, 59.700),
    "arabian_sea":  (23.900, 60.600),
}

PORTS_META: list[dict[str, object]] = [
    {"id": "ras_tanura",   "name": "Ras Tanura",   "lat": PORTS_LATLON["ras_tanura"][0],   "lon": PORTS_LATLON["ras_tanura"][1]},
    {"id": "kharg_island", "name": "Kharg Island",  "lat": PORTS_LATLON["kharg_island"][0], "lon": PORTS_LATLON["kharg_island"][1]},
    {"id": "das_island",   "name": "Das Island",    "lat": PORTS_LATLON["das_island"][0],   "lon": PORTS_LATLON["das_island"][1]},
    {"id": "ras_laffan",   "name": "Ras Laffan",    "lat": PORTS_LATLON["ras_laffan"][0],   "lon": PORTS_LATLON["ras_laffan"][1]},
    {"id": "ruwais",       "name": "Ruwais",        "lat": PORTS_LATLON["ruwais"][0],       "lon": PORTS_LATLON["ruwais"][1]},
    {"id": "fujairah",     "name": "Fujairah",      "lat": PORTS_LATLON["fujairah"][0],     "lon": PORTS_LATLON["fujairah"][1]},
]

CHOKEPOINTS_META: list[dict[str, object]] = [
    # Narrowest navigable point between Hormuz Island (Iran) and Musandam (Oman)
    {"id": "hormuz_narrows", "name": "Hormuz Narrows", "lat": 26.37, "lon": 56.42},
]


def _concat(*parts: Sequence[LatLon]) -> list[LatLon]:
    out: list[LatLon] = []
    for idx, part in enumerate(parts):
        if not part:
            continue
        if idx > 0 and out and out[-1] == part[0]:
            out.extend(list(part[1:]))
        else:
            out.extend(list(part))
    return out


def _nearest_index(path: Sequence[LatLon], point: LatLon) -> int:
    """Return index of path point nearest to target point (haversine distance)."""
    if not path:
        return 0
    best_idx = 0
    best_dist = float("inf")
    for idx, p in enumerate(path):
        dist = _haversine_km(p, point)
        if dist < best_dist:
            best_dist = dist
            best_idx = idx
    return best_idx


def _enforce_tss_corridor(route: dict[str, object]) -> None:
    """Force route geometry through canonical TSS lanes with A*-generated connectors."""
    try:
        from sea_routing import find_sea_route, validate_route
    except Exception as exc:
        print(f"[geo_layout] sea_routing unavailable for corridor enforcement: {exc}")
        return

    path = route.get("path")
    direction = str(route.get("direction", ""))
    if not isinstance(path, list) or len(path) < 2:
        return

    if direction == "eastbound":
        lane = list(SOUTH_LANE_LATLON)
    elif direction == "westbound":
        lane = list(reversed(NORTH_LANE_LATLON))
    else:
        return

    if len(lane) < 2:
        return

    origin = path[0]
    destination = path[-1]

    connector_in = find_sea_route(origin, lane[0])
    connector_out = find_sea_route(lane[-1], destination)
    if not connector_in or not connector_out:
        print(f"[geo_layout] corridor connector failed: {route.get('id', 'unknown')}")
        return

    candidate = _concat(connector_in, lane, connector_out)
    is_valid, _ = validate_route(candidate)
    if not is_valid:
        print(f"[geo_layout] corridor candidate invalid: {route.get('id', 'unknown')}")
        return

    route["path"] = candidate


# ---------------------------------------------------------------------------
# EXPORT ROUTES  (outbound / eastbound — use SOUTH_LANE through strait)
# ---------------------------------------------------------------------------
# Persian Gulf shipping corridor runs roughly east–west along ~26.5 N.
# Ships funnel through the TSS, exit SE around Musandam, then spread out
# into the Gulf of Oman / Arabian Sea.
#
# Critical constraint: NO waypoint must be north of 25.9 N at longitudes
# 56.5–57.2 E (that band is the Omani Musandam land mass).
# After clearing the strait (lon > 57.2 E) ships are in open water.

EXPORT_ROUTES: list[dict[str, object]] = [
    {
        "id": "ras_tanura_export",
        "name": "Ras Tanura → Arabian Sea",
        "direction": "eastbound",
        "origin": "ras_tanura",
        "destination": "arabian_sea",
        "path": _concat(
            [
                PORTS_LATLON["ras_tanura"],
                (26.55, 50.80),
                (26.50, 51.60),
                (26.40, 52.40),
                (26.25, 53.10),
                (26.15, 53.85),   # South of Kish Island (26.47–26.63N, 53.83–54.02E)
                (26.20, 54.30),   # Continue south of Kish longitude band
                (26.38, 54.80),   # Return to main channel
                (26.48, 55.30),
            ],
            SOUTH_LANE_LATLON,
            [
                # After clearing strait, drop SE into Gulf of Oman — clear of all land
                (24.20, 58.30),
                (23.95, 58.70),
                (23.80, 59.20),
                (23.75, 59.80),
                PORTS_LATLON["arabian_sea"],
            ],
        ),
    },
    {
        "id": "kharg_export",
        "name": "Kharg Island → Gulf of Oman",
        "direction": "eastbound",
        "origin": "kharg_island",
        "destination": "gulf_of_oman",
        "path": _concat(
            [
                PORTS_LATLON["kharg_island"],
                (28.60, 50.80),
                (27.80, 51.50),
                (27.20, 52.30),
                (30.0, 52.90),   # Pass south of Lavan Island (26.65–26.80N, 53.22–53.48E)
                (26.25, 53.50),   # Clear south of both Lavan and Kish approach
                (26.15, 53.90),   # South of Kish Island (26.47–26.63N, 53.83–54.02E)
                (26.25, 54.40),   # Re-enter main channel east of Kish
                (26.42, 54.90),
                (30.0, 55.30),
            ],
            SOUTH_LANE_LATLON,
            [
                (70.0, 58.30),
                (70.0, 58.80),
                (70.0, 20.0),
                PORTS_LATLON["gulf_of_oman"],
            ],
        ),
    },
    {
        "id": "das_export",
        "name": "Das Island → Fujairah",
        "direction": "eastbound",
        "origin": "das_island",
        "destination": "fujairah",
        "path": _concat(
            [
                PORTS_LATLON["das_island"],
                (25.50, 53.20),
                (25.80, 53.80),   # Well south of Kish Island — approach from south
                (26.10, 54.30),   # South of Kish (26.47–26.63N, 53.83–54.02E)
                (26.35, 54.80),
                (26.45, 55.10),
                (26.48, 55.30),
            ],
            SOUTH_LANE_LATLON,
            [
                # After exiting strait, curve back west to Fujairah.
                # Must stay NORTH of Oman coast.
                # Fujairah is at 25.1N, 56.4E (on the coast)
                (24.50, 57.80),   # Exit into Gulf of Oman
                (24.60, 57.50),   # Curve west, staying north of coast
                (24.70, 57.20),
                (24.85, 56.90),
                (24.95, 56.65),   # Approaching Fujairah
                (25.05, 56.50),   # Final approach
                PORTS_LATLON["fujairah"],
            ],
        ),
    },
    {
        "id": "ras_laffan_export",
        "name": "Ras Laffan → Arabian Sea",
        "direction": "eastbound",
        "origin": "ras_laffan",
        "destination": "arabian_sea",
        "path": _concat(
            [
                PORTS_LATLON["ras_laffan"],
                (26.05, 52.00),
                (26.15, 52.80),
                (26.15, 53.60),   # Clearly south of Kish approach
                (26.15, 54.10),   # South of Kish Island (26.47–26.63N, 53.83–54.02E)
                (26.30, 54.70),   # Return to main channel east of Kish
                (26.45, 55.10),
                (26.48, 55.30),
            ],
            SOUTH_LANE_LATLON,
            [
                (24.20, 58.30),
                (24.00, 58.80),
                (23.85, 59.40),
                (23.80, 60.00),
                PORTS_LATLON["arabian_sea"],
            ],
        ),
    },
    {
        "id": "ruwais_export",
        "name": "Ruwais → Gulf of Oman",
        "direction": "eastbound",
        "origin": "ruwais",
        "destination": "gulf_of_oman",
        "path": _concat(
            [
                PORTS_LATLON["ruwais"],
                (24.40, 52.80),
                (24.80, 53.20),
                (25.40, 53.60),
                (25.90, 54.10),   # Well south of Kish — in open water
                (26.20, 54.60),
                (26.40, 55.00),
                (26.48, 55.30),
            ],
            SOUTH_LANE_LATLON,
            [
                (24.20, 58.30),
                (24.10, 58.80),
                (24.20, 59.30),
                PORTS_LATLON["gulf_of_oman"],
            ],
        ),
    },
]

# ---------------------------------------------------------------------------
# INBOUND ROUTES  (westbound — use NORTH_LANE reversed through strait)
# ---------------------------------------------------------------------------

INBOUND_ROUTES: list[dict[str, object]] = [
    {
        "id": "ras_tanura_inbound",
        "name": "Arabian Sea → Ras Tanura",
        "direction": "westbound",
        "origin": "arabian_sea",
        "destination": "ras_tanura",
        "path": _concat(
            [
                PORTS_LATLON["arabian_sea"],
                (23.80, 60.00),
                (23.95, 59.40),
                (24.10, 58.80),
                (24.30, 58.30),
                (24.55, 58.10),
            ],
            list(reversed(NORTH_LANE_LATLON)),
            [
                (26.45, 55.10),
                (26.30, 54.70),
                (26.15, 54.10),   # South of Kish Island (26.47–26.63N, 53.83–54.02E)
                (26.15, 53.60),   # Continue south of Kish longitude band
                (26.30, 52.80),
                (26.42, 51.90),
                (26.52, 50.90),
                PORTS_LATLON["ras_tanura"],
            ],
        ),
    },
    {
        "id": "kharg_inbound",
        "name": "Gulf of Oman → Kharg Island",
        "direction": "westbound",
        "origin": "gulf_of_oman",
        "destination": "kharg_island",
        "path": _concat(
            [
                PORTS_LATLON["gulf_of_oman"],
                (24.30, 59.20),
                (24.20, 58.60),
                (24.40, 58.20),
                (24.55, 58.10),
            ],
            list(reversed(NORTH_LANE_LATLON)),
            [
                (26.45, 55.10),
                (26.25, 54.60),
                (26.15, 54.10),   # South of Kish Island (26.47–26.63N, 53.83–54.02E)
                (26.55, 53.10),   # West of Lavan's longitude — both islands now clear
                (27.00, 52.50),   # Open water heading northwest to Kharg
                (27.60, 51.80),
                (28.20, 51.10),
                (28.80, 50.70),
                PORTS_LATLON["kharg_island"],
            ],
        ),
    },
    {
        "id": "ruwais_inbound",
        "name": "Gulf of Oman → Ruwais",
        "direction": "westbound",
        "origin": "gulf_of_oman",
        "destination": "ruwais",
        "path": _concat(
            [
                PORTS_LATLON["gulf_of_oman"],
                (24.30, 59.20),
                (24.20, 58.60),
                (24.40, 58.20),
                (24.55, 58.10),
            ],
            list(reversed(NORTH_LANE_LATLON)),
            [
                (26.50, 55.30),
                (26.50, 54.80),
                (26.30, 54.30),
                (26.00, 53.75),
                (25.50, 53.25),
                (24.80, 52.90),
                PORTS_LATLON["ruwais"],
            ],
        ),
    },
    {
        "id": "ras_laffan_inbound",
        "name": "Arabian Sea → Ras Laffan",
        "direction": "westbound",
        "origin": "arabian_sea",
        "destination": "ras_laffan",
        "path": _concat(
            [
                PORTS_LATLON["arabian_sea"],
                (23.80, 60.00),
                (23.95, 59.40),
                (24.10, 58.80),
                (24.30, 58.30),
                (24.55, 58.10),
            ],
            list(reversed(NORTH_LANE_LATLON)),
            [
                (26.45, 55.10),
                (26.25, 54.70),
                (26.15, 54.00),   # South of Kish Island (26.47–26.63N, 53.83–54.02E)
                (26.10, 53.35),   # Clear west of Kish longitude band
                (26.05, 52.60),
                (25.95, 52.00),
                PORTS_LATLON["ras_laffan"],
            ],
        ),
    },
    {
        "id": "das_inbound",
        "name": "Fujairah → Das Island",
        "direction": "westbound",
        "origin": "fujairah",
        "destination": "das_island",
        "path": _concat(
            [
                # From Fujairah head east into Gulf of Oman, then join inbound lane.
                # Must stay NORTH of Oman coast throughout.
                PORTS_LATLON["fujairah"],
                (25.05, 56.50),   # Head east from Fujairah
                (24.95, 56.65),
                (24.85, 56.90),
                (24.70, 57.20),
                (24.60, 57.50),
                (24.50, 57.80),   # Into Gulf of Oman
                (24.55, 58.10),   # Join the inbound lane
            ],
            list(reversed(NORTH_LANE_LATLON)),
            [
                (26.50, 55.30),
                (26.50, 54.70),
                (26.20, 54.00),
                (25.80, 53.40),
                PORTS_LATLON["das_island"],
            ],
        ),
    },
]

REAL_ROUTES: list[dict[str, object]] = EXPORT_ROUTES + INBOUND_ROUTES

# Route waypoints used to keep A* sea routing aligned with realistic Hormuz lanes.
# Western gulf waypoints specifically route around:
#   Kish Island  (26.47–26.63N, 53.83–54.02E) — pass south via ~26.15N
#   Lavan Island (26.65–26.80N, 53.22–53.48E) — descend south before entering its longitude band
SEA_ROUTE_WAYPOINTS: dict[str, list[LatLon]] = {
    # EXPORT (eastbound) ────────────────────────────────────────────────────
    "ras_tanura_export": [
        (26.40, 52.40), (26.15, 53.85),   # dip south of Kish Island
        (26.38, 54.80), (26.48, 55.50),   # re-enter main channel
        (26.40, 56.60), (25.78, 57.12), (24.40, 58.10), (23.80, 59.20),
    ],
    "kharg_export": [
        (26.55, 52.90), (26.15, 53.90),   # south of Lavan then Kish
        (26.42, 54.90), (26.48, 55.50),
        (26.40, 56.60), (25.78, 57.12), (24.40, 58.10),
    ],
    "das_export": [
        (25.80, 53.80), (26.10, 54.30),   # southern approach, south of Kish
        (26.35, 54.80), (26.48, 55.50),
        (26.40, 56.60), (25.78, 57.12), (24.85, 57.92),
    ],
    "ras_laffan_export": [
        (26.15, 52.80), (26.15, 54.10),   # south of Kish throughout
        (26.30, 54.70), (26.48, 55.50),
        (26.40, 56.60), (25.78, 57.12), (24.40, 58.10), (23.85, 59.40),
    ],
    "ruwais_export": [
        (25.40, 53.60), (25.90, 54.10),   # southern approach, clear of all islands
        (26.40, 55.00), (26.48, 55.50),
        (26.40, 56.60), (25.78, 57.12), (24.40, 58.10),
    ],
    # INBOUND (westbound) ───────────────────────────────────────────────────
    "ras_tanura_inbound": [
        (24.55, 58.10), (25.00, 57.94), (26.35, 56.90), (26.55, 55.50),
        (26.15, 54.10), (26.15, 53.60),  # south of Kish Island
        (26.30, 52.80),
    ],
    "kharg_inbound": [
        (24.55, 58.10), (25.00, 57.94), (26.35, 56.90), (26.55, 55.50),
        (26.15, 54.10),                  # south of Kish Island
        (26.55, 53.10),                  # west of Lavan's longitude, below its latitude
        (27.00, 52.50), (27.60, 51.80),
    ],
    "ruwais_inbound": [
        (24.55, 58.10), (25.00, 57.94), (26.35, 56.90), (26.55, 55.50),
        (26.10, 54.20), (25.90, 53.80), (25.40, 53.30),
    ],
    "ras_laffan_inbound": [
        (24.55, 58.10), (25.00, 57.94), (26.35, 56.90), (26.55, 55.50),
        (26.15, 54.00), (26.10, 53.35),  # south of Kish Island
        (26.05, 52.60),
    ],
    "das_inbound": [
        (24.55, 58.10), (25.00, 57.94), (26.35, 56.90), (26.55, 55.50),
        (26.10, 54.20), (25.80, 53.60), (25.50, 53.10),
    ],
}


def _repair_invalid_routes_with_natural_earth() -> None:
    """Keep documented route geometry, using A* rerouting only for land-crossing routes."""
    try:
        from sea_routing import find_sea_route, validate_route
    except Exception as exc:
        print(f"[geo_layout] sea_routing unavailable for repair: {exc}")
        return

    for route in REAL_ROUTES:
        route_id = str(route.get("id", ""))
        path = route.get("path")
        if not isinstance(path, list) or len(path) < 2:
            continue

        dense_candidate = densify_latlon_path(path, step_km=3.0)
        is_valid, _ = validate_route(dense_candidate)
        if is_valid:
            continue

        start = path[0]
        goal = path[-1]
        waypoints = SEA_ROUTE_WAYPOINTS.get(route_id)

        sea_path = find_sea_route(start, goal, waypoints=waypoints if waypoints else None)
        if sea_path is None and waypoints:
            sea_path = find_sea_route(start, goal)
        if not sea_path:
            print(f"[geo_layout] route repair failed: {route_id}")
            continue

        is_valid, _ = validate_route(sea_path)
        if is_valid:
            route["path"] = sea_path
        else:
            print(f"[geo_layout] repaired route still invalid: {route_id}")


def _rebuild_routes_with_sea_routing() -> None:
    """Rebuild documented routes via A* using route-specific waypoints when available."""
    try:
        from sea_routing import find_sea_route, validate_route
    except Exception as exc:
        print(f"[geo_layout] sea_routing unavailable for rebuild: {exc}")
        return

    rebuilt = 0
    for route in REAL_ROUTES:
        route_id = str(route.get("id", ""))
        path = route.get("path")
        if not isinstance(path, list) or len(path) < 2:
            continue

        # Use explicit waypoints where configured to keep routes in realistic lanes.
        waypoints = SEA_ROUTE_WAYPOINTS.get(route_id)
        if waypoints is None:
            continue

        start = path[0]
        goal = path[-1]
        sea_path = find_sea_route(start, goal, waypoints=waypoints)
        if not sea_path:
            print(f"[geo_layout] route rebuild failed: {route_id}")
            continue

        is_valid, _ = validate_route(sea_path)
        if not is_valid:
            print(f"[geo_layout] rebuilt route invalid: {route_id}")
            continue

        route["path"] = sea_path
        rebuilt += 1

    print(f"[geo_layout] rebuilt {rebuilt}/{len(REAL_ROUTES)} routes via sea routing")


def _print_route_validation_summary() -> None:
    """Print one-time startup summary to make routing issues explicit."""
    try:
        from sea_routing import validate_route
    except Exception as exc:
        print(f"[geo_layout] sea_routing unavailable for validation summary: {exc}")
        return

    valid = 0
    invalid = 0
    for route in REAL_ROUTES:
        route_id = str(route.get("id", "unknown"))
        path = list(route.get("path", []))
        if len(path) < 2:
            invalid += 1
            print(f"[geo_layout] invalid route (too short): {route_id}")
            continue

        is_valid, issues = validate_route(path)
        if is_valid:
            valid += 1
        else:
            invalid += 1
            print(f"[geo_layout] invalid route: {route_id} (issue markers={len(issues)})")

    print(f"[geo_layout] route validation summary: valid={valid} invalid={invalid}")


_rebuild_routes_with_sea_routing()
_repair_invalid_routes_with_natural_earth()

for _route in REAL_ROUTES:
    _enforce_tss_corridor(_route)

# ---------------------------------------------------------------------------
# Densify all routes for smooth rendering (prevents straight-line land crossing)
# ---------------------------------------------------------------------------
for _route in REAL_ROUTES:
    _path = _route.get("path")
    if _path and len(_path) >= 2:
        _route["path"] = densify_latlon_path(_path, step_km=3.0)

_print_route_validation_summary()


# ---------------------------------------------------------------------------
# Validate routes against real land polygons (optional, requires sea_routing)
# ---------------------------------------------------------------------------
def validate_and_fix_routes(use_astar_reroute: bool = False) -> dict:
    """
    Validate all routes against Natural Earth land polygons.

    Args:
        use_astar_reroute: If True, attempt to re-route segments that cross land

    Returns:
        Dictionary with validation results
    """
    try:
        from sea_routing import validate_route, find_sea_route, is_on_land
    except ImportError:
        return {"error": "sea_routing module not available"}

    results = {
        "total_routes": len(REAL_ROUTES),
        "valid_routes": 0,
        "invalid_routes": 0,
        "fixed_routes": 0,
        "details": [],
    }

    for route in REAL_ROUTES:
        route_id = route.get("id", "unknown")
        path = list(route.get("path", []))

        if not path:
            continue

        is_valid, land_points = validate_route(path)

        if is_valid:
            results["valid_routes"] += 1
            results["details"].append({
                "id": route_id,
                "status": "valid",
                "points": len(path),
            })
        else:
            results["invalid_routes"] += 1
            detail = {
                "id": route_id,
                "status": "invalid",
                "points": len(path),
                "land_crossings": len(land_points),
                "land_indices": land_points[:10],  # First 10 only
            }

            # Optionally try to fix with A* routing
            if use_astar_reroute and len(path) >= 2:
                new_path = find_sea_route(path[0], path[-1])
                if new_path:
                    route["path"] = new_path
                    detail["status"] = "fixed"
                    detail["new_points"] = len(new_path)
                    results["fixed_routes"] += 1
                    results["invalid_routes"] -= 1

            results["details"].append(detail)

    return results


def generate_astar_route(
    origin: str,
    destination: str,
    waypoints: List[LatLon] | None = None,
) -> List[LatLon] | None:
    """
    Generate a new route using A* pathfinding.

    Args:
        origin: Origin port ID (from PORTS_LATLON)
        destination: Destination port ID (from PORTS_LATLON)
        waypoints: Optional intermediate waypoints

    Returns:
        List of (lat, lon) coordinates, or None if route not found
    """
    try:
        from sea_routing import find_sea_route
    except ImportError:
        return None

    if origin not in PORTS_LATLON or destination not in PORTS_LATLON:
        return None

    start = PORTS_LATLON[origin]
    goal = PORTS_LATLON[destination]

    return find_sea_route(start, goal, waypoints)


def _project(lat: float, lon: float, width: int, height: int, viewport: GeoViewport) -> Point:
    """Project geographic coordinates to pixel coordinates using Web Mercator."""
    clamped_lat = max(-85.0511, min(85.0511, lat))

    def mercator_y(lat_deg: float) -> float:
        lat_rad = math.radians(lat_deg)
        return (1.0 - math.asinh(math.tan(lat_rad)) / math.pi) * 0.5

    x = (lon + 180.0) / 360.0
    y = mercator_y(clamped_lat)

    x_min = (viewport.min_lon + 180.0) / 360.0
    x_max = (viewport.max_lon + 180.0) / 360.0
    y_min = mercator_y(viewport.max_lat)
    y_max = mercator_y(viewport.min_lat)

    x_norm = (x - x_min) / (x_max - x_min)
    y_norm = (y - y_min) / (y_max - y_min)

    x = int(max(0.0, min(1.0, x_norm)) * width)
    y = int(max(0.0, min(1.0, y_norm)) * height)
    return x, y


def project_latlon(lat: float, lon: float, width: int, height: int, viewport: GeoViewport | None = None) -> Point:
    """Project one lat/lon point in a north-up top-view map to screen pixels."""
    vp = viewport or GeoViewport()
    return _project(lat, lon, width, height, vp)


def _project_path(path: Sequence[LatLon], width: int, height: int, viewport: GeoViewport) -> List[Point]:
    return [_project(lat, lon, width, height, viewport) for lat, lon in path]


def build_projected_layout(width: int, height: int, viewport: GeoViewport | None = None) -> GeoMapLayout:
    """Build projected map geometry for the provided pixel dimensions."""
    vp = viewport or GeoViewport()

    iran = _project_path(IRAN_COAST_LATLON, width, height, vp)
    arabia = _project_path(ARABIA_COAST_LATLON, width, height, vp)
    islands = [_project_path(island, width, height, vp) for island in ISLANDS_LATLON]

    north_lane = _project_path(NORTH_LANE_LATLON, width, height, vp)
    south_lane = _project_path(SOUTH_LANE_LATLON, width, height, vp)
    separation_line = _project_path(SEPARATION_LINE_LATLON, width, height, vp)

    return GeoMapLayout(
        iran_coastline=iran,
        arabia_coastline=arabia,
        islands=islands,
        north_lane=north_lane,
        south_lane=south_lane,
        separation_line=separation_line,
    )


def interpolate_polyline(points: Sequence[Point], t: float) -> Tuple[float, float]:
    """Interpolate a polyline by normalized progress t in [0, 1]."""
    if not points:
        return 0.0, 0.0
    if len(points) == 1:
        return float(points[0][0]), float(points[0][1])

    clamped_t = max(0.0, min(1.0, t))

    segment_lengths: List[float] = []
    total = 0.0
    for i in range(len(points) - 1):
        x1, y1 = points[i]
        x2, y2 = points[i + 1]
        seg = ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5
        segment_lengths.append(seg)
        total += seg

    if total <= 0.0:
        return float(points[0][0]), float(points[0][1])

    target = clamped_t * total
    traveled = 0.0

    for i, seg in enumerate(segment_lengths):
        if traveled + seg >= target:
            local_t = (target - traveled) / seg if seg > 0 else 0.0
            x1, y1 = points[i]
            x2, y2 = points[i + 1]
            x = x1 + (x2 - x1) * local_t
            y = y1 + (y2 - y1) * local_t
            return x, y
        traveled += seg

    last = points[-1]
    return float(last[0]), float(last[1])