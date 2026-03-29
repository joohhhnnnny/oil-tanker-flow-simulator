"""
Web UI server for the Oil Tanker Flow Simulation.

This module replaces the previous Pygame stack with:
- FastAPI for control/state APIs
- WebSocket transport for live updates
- Static frontend served from ./web (Leaflet + Leaflet.Motion)

Simulation logic remains SimPy-based.
"""

from __future__ import annotations

import asyncio
import math
import os
import random
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Generator, Optional

import simpy
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from config import (
    DisruptionConfig,
    DisruptionType,
    MitigationStrategy,
    SimulationConfig,
    StraitConfig,
    TankerType,
)
from disruptions import create_disruption_manager
from entities import Tanker, TankerStatus, StraitOfHormuz
from geo_layout import CHOKEPOINTS_META, NORTH_LANE_LATLON, PORTS_META, REAL_ROUTES, SOUTH_LANE_LATLON
from statistics_collector import SimulationStatistics
from ui_config import ANIMATION_FPS


def _heading_from_points(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Return compass heading in degrees from point a(lat, lon) to b(lat, lon)."""
    d_lat = b[0] - a[0]
    d_lon = b[1] - a[1]
    if d_lat == 0.0 and d_lon == 0.0:
        return 0.0
    angle = 90.0 - math.degrees(math.atan2(d_lat, d_lon))
    return angle % 360.0


def _interpolate_latlon(route: list[tuple[float, float]], t: float) -> tuple[float, float]:
    """Interpolate a lat/lon polyline by normalized progress t in [0, 1]."""
    if not route:
        return 0.0, 0.0
    if len(route) == 1:
        return route[0]

    clamped = max(0.0, min(1.0, t))
    segment_lengths: list[float] = []
    total = 0.0
    for i in range(len(route) - 1):
        a = route[i]
        b = route[i + 1]
        # Small-area approximation is sufficient at this map scale.
        seg = ((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2) ** 0.5
        segment_lengths.append(seg)
        total += seg

    if total <= 0.0:
        return route[0]

    target = clamped * total
    traveled = 0.0
    for i, seg in enumerate(segment_lengths):
        if traveled + seg >= target:
            local_t = (target - traveled) / seg if seg > 0 else 0.0
            lat = route[i][0] + (route[i + 1][0] - route[i][0]) * local_t
            lon = route[i][1] + (route[i + 1][1] - route[i][1]) * local_t
            return lat, lon
        traveled += seg

    return route[-1]


def _haversine_nm(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Great-circle distance between two lat/lon points in nautical miles."""
    lat1, lon1 = a
    lat2, lon2 = b
    r_nm = 3440.065
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    sin_dphi = math.sin(dphi / 2.0)
    sin_dlambda = math.sin(dlambda / 2.0)
    h = sin_dphi * sin_dphi + math.cos(phi1) * math.cos(phi2) * sin_dlambda * sin_dlambda
    return 2.0 * r_nm * math.asin(min(1.0, math.sqrt(h)))


def _route_distance_nm(route: list[tuple[float, float]]) -> float:
    if len(route) < 2:
        return 0.0
    return sum(_haversine_nm(route[i], route[i + 1]) for i in range(len(route) - 1))


@dataclass
class ShipTrack:
    """Runtime state for one vessel used by the frontend."""

    tanker_id: int
    tanker_type: str
    status: str
    direction: str
    route_id: str
    route_name: str
    origin: str
    destination: str
    cargo_barrels: int
    lat: float
    lon: float
    heading: float
    speed_knots: float
    progress: float = 0.0
    waiting_time: float = 0.0
    created_at: float = 0.0


class StartRequest(BaseModel):
    duration_hours: float = Field(default=168.0, gt=0)
    arrival_rate_per_hour: float = Field(default=0.7, gt=0)
    export_count: int = Field(default=6, ge=0, le=20)
    import_count: int = Field(default=6, ge=0, le=20)
    disruption: str = Field(default="NONE")
    mitigation: str = Field(default="NONE")


class SpeedRequest(BaseModel):
    speed: float = Field(default=1.0, ge=0.1, le=25.0)


class WebSimulationBridge:
    """SimPy runner that exposes map-oriented state snapshots for web clients."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._paused = False
        self._speed = 1.0

        self.env: Optional[simpy.Environment] = None
        self.strait: Optional[StraitOfHormuz] = None
        self.statistics: Optional[SimulationStatistics] = None
        self.config: Optional[SimulationConfig] = None

        self.rng = random.Random(42)
        self._tanker_counter = 0
        self._ship_tracks: Dict[int, ShipTrack] = {}
        self._active_tankers: Dict[int, Tanker] = {}

        self._route_defs: list[dict[str, object]] = list(REAL_ROUTES)
        self._route_by_id: dict[str, dict[str, object]] = {
            str(r["id"]): r for r in self._route_defs if "id" in r
        }
        self._routes_by_direction: dict[str, list[dict[str, object]]] = {
            "eastbound": [r for r in self._route_defs if r.get("direction") == "eastbound"],
            "westbound": [r for r in self._route_defs if r.get("direction") == "westbound"],
        }

        self._disruption_active = False
        self._total_arrivals = 0
        self._total_completed = 0
        self._total_deployed = 0
        self._oil_delivered_total = 0
        self._wait_times: list[float] = []
        self._export_count = 6
        self._import_count = 6

    def start(self, req: StartRequest) -> None:
        self.stop()
        with self._lock:
            self.config = self._build_config(req)
            self._ship_tracks.clear()
            self._active_tankers.clear()
            self._tanker_counter = 0
            self._disruption_active = False
            self._total_arrivals = 0
            self._total_completed = 0
            self._total_deployed = 0
            self._oil_delivered_total = 0
            self._wait_times.clear()
            self._export_count = req.export_count
            self._import_count = req.import_count
            self._running = True
            self._paused = False

        self._thread = threading.Thread(target=self._run_simulation, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        with self._lock:
            self._running = False
            self._paused = False
        if self._thread:
            self._thread.join(timeout=1.0)
            self._thread = None

    def pause(self) -> None:
        with self._lock:
            self._paused = True

    def resume(self) -> None:
        with self._lock:
            self._paused = False

    def set_speed(self, speed: float) -> None:
        with self._lock:
            self._speed = max(0.1, min(speed, 25.0))

    def _build_config(self, req: StartRequest) -> SimulationConfig:
        disruption = DisruptionType[req.disruption]
        mitigation = MitigationStrategy[req.mitigation]

        if disruption == DisruptionType.PARTIAL_BLOCKADE:
            disruption_config = DisruptionConfig(
                disruption_type=disruption,
                start_time_hours=1.0,
                duration_hours=200.0,
                capacity_reduction=0.5,
                transit_time_multiplier=1.5,
            )
        elif disruption == DisruptionType.COMPLETE_BLOCKADE:
            disruption_config = DisruptionConfig(
                disruption_type=disruption,
                start_time_hours=0.0,
                duration_hours=200.0,
                capacity_reduction=1.0,
            )
        elif disruption == DisruptionType.WEATHER_DELAY:
            disruption_config = DisruptionConfig(
                disruption_type=disruption,
                start_time_hours=0.5,
                duration_hours=200.0,
                capacity_reduction=0.3,
                transit_time_multiplier=2.0,
            )
        else:
            disruption_config = DisruptionConfig(disruption_type=DisruptionType.NONE)

        return SimulationConfig(
            duration_hours=req.duration_hours,
            warmup_hours=0.0,
            random_seed=42,
            strait_config=StraitConfig(
                mean_arrival_rate_per_hour=req.arrival_rate_per_hour,
                max_concurrent_transits=max(1, req.export_count + req.import_count),
            ),
            disruption_config=disruption_config,
            mitigation_strategy=mitigation,
            verbose=False,
        )

    def _run_simulation(self) -> None:
        self.env = simpy.Environment()
        self.statistics = SimulationStatistics(warmup_hours=0)

        self.strait = StraitOfHormuz(
            env=self.env,
            config=self.config.strait_config,
            statistics=self.statistics,
            mitigation_strategy=self.config.mitigation_strategy,
            verbose=False,
        )

        disruption_manager = create_disruption_manager(
            env=self.env,
            strait=self.strait,
            config=self.config.disruption_config,
            statistics=self.statistics,
            verbose=False,
        )

        self.env.process(self._tanker_generator())
        self.env.process(disruption_manager.run())
        self.env.process(self._disruption_monitor())

        while True:
            with self._lock:
                running = self._running
                paused = self._paused
                speed = self._speed

            if not running:
                break
            if paused:
                time.sleep(0.1)
                continue
            if self.env.now >= self.config.duration_hours:
                with self._lock:
                    self._running = False
                break

            try:
                step_size = speed / ANIMATION_FPS
                self.env.run(until=self.env.now + step_size)
                time.sleep(1.0 / ANIMATION_FPS)
            except simpy.core.EmptySchedule:
                time.sleep(0.1)

    def _tanker_generator(self) -> Generator[Any, Any, None]:
        """Spawn a fixed set of tankers: export_count eastbound + import_count westbound."""
        total = self._export_count + self._import_count
        if total == 0:
            return

        eastbound_routes = self._routes_by_direction.get("eastbound") or []
        westbound_routes = self._routes_by_direction.get("westbound") or []

        # Build the manifest: interleave export/import for maximum spacing
        manifest: list[tuple[str, dict[str, object]]] = []
        ei, ii = 0, 0
        while ei < self._export_count or ii < self._import_count:
            if ei < self._export_count:
                route = eastbound_routes[ei % len(eastbound_routes)] if eastbound_routes else {"id": "fallback", "name": "Fallback", "direction": "eastbound", "path": []}
                manifest.append(("eastbound", route))
                ei += 1
            if ii < self._import_count:
                route = westbound_routes[ii % len(westbound_routes)] if westbound_routes else {"id": "fallback", "name": "Fallback", "direction": "westbound", "path": []}
                manifest.append(("westbound", route))
                ii += 1

        # Stagger spawns: 0.6h between each → same-direction gap ≈ 1.2h ≈ 15.6 NM (>1 ship-length gap)
        for idx, (direction, route) in enumerate(manifest):
            if idx > 0:
                yield self.env.timeout(0.6)

            with self._lock:
                if not self._running:
                    break

            self._tanker_counter += 1
            tanker_type = self._select_tanker_type()
            tanker_config = self.config.tanker_configs[tanker_type]

            tanker = Tanker(
                tanker_id=self._tanker_counter,
                tanker_type=tanker_type,
                config=tanker_config,
            )
            self._active_tankers[tanker.tanker_id] = tanker
            self._total_deployed += 1

            queue_lat, queue_lon = self._queue_anchor(route)
            speed_knots = self._speed_knots_for_type(tanker_type)
            self._ship_tracks[tanker.tanker_id] = ShipTrack(
                tanker_id=tanker.tanker_id,
                tanker_type=tanker_type.name,
                status="waiting",
                direction=direction,
                route_id=str(route.get("id", "")),
                route_name=str(route.get("name", "Route")),
                origin=str(route.get("origin", "origin")),
                destination=str(route.get("destination", "destination")),
                cargo_barrels=tanker.cargo_barrels,
                lat=queue_lat,
                lon=queue_lon,
                heading=90.0 if direction == "eastbound" else 270.0,
                speed_knots=speed_knots,
                created_at=self.env.now,
            )
            self._refresh_waiting_positions()

            self.env.process(self._process_tanker(tanker, direction))

    def _process_tanker(self, tanker: Tanker, direction: str) -> Generator[Any, Any, None]:
        tanker.arrival_time = self.env.now
        tanker.status = TankerStatus.WAITING

        if self.config.mitigation_strategy == MitigationStrategy.PRIORITY_SCHEDULING:
            request = self.strait._resource.request(priority=10 - tanker.priority)
        else:
            request = self.strait._resource.request()

        while self.strait._blocked:
            tanker.status = TankerStatus.BLOCKED
            track = self._ship_tracks.get(tanker.tanker_id)
            if track:
                track.status = "blocked"
            yield self.env.timeout(0.5)

        yield request

        try:
            tanker.start_transit_time = self.env.now
            tanker.status = TankerStatus.IN_TRANSIT
            wait_time = tanker.waiting_time or 0.0
            self._wait_times.append(wait_time)

            track = self._ship_tracks.get(tanker.tanker_id)
            if track:
                track.status = "in_transit"
                track.waiting_time = wait_time

            route_id = track.route_id if track else ""
            route_def = self._route_by_id.get(route_id)
            route = list(route_def.get("path", [])) if route_def else []
            base_speed = track.speed_knots if track else self._speed_knots_for_type(tanker.tanker_type)
            route_distance_nm = _route_distance_nm(route)
            route_time = (route_distance_nm / base_speed) if base_speed > 0 else 1.0

            # Preserve disruption/transit multipliers from the underlying Strait model.
            nominal = tanker.config.transit_time_hours or 1.0
            effective = self.strait.get_transit_time(tanker)
            multiplier = max(0.25, effective / nominal)

            transit_time = max(0.5, route_time * multiplier)
            start_time = self.env.now

            while self.env.now < start_time + transit_time:
                progress = min(1.0, (self.env.now - start_time) / transit_time) if transit_time > 0 else 1.0
                lat, lon = _interpolate_latlon(route, progress)
                h_from = _interpolate_latlon(route, max(0.0, progress - 0.01))
                h_to = _interpolate_latlon(route, min(1.0, progress + 0.01))

                current = self._ship_tracks.get(tanker.tanker_id)
                if current:
                    current.lat = lat
                    current.lon = lon
                    current.heading = _heading_from_points(h_from, h_to)
                    current.progress = progress
                    current.status = "in_transit"
                yield self.env.timeout(0.1)

            tanker.end_transit_time = self.env.now
            tanker.status = TankerStatus.COMPLETED
            self._total_arrivals += 1
            self._total_completed += 1
            self._oil_delivered_total += tanker.cargo_barrels

            self._ship_tracks.pop(tanker.tanker_id, None)
            self._active_tankers.pop(tanker.tanker_id, None)
            self._refresh_waiting_positions()
        finally:
            self.strait._resource.release(request)

    def _disruption_monitor(self) -> Generator[Any, Any, None]:
        while True:
            with self._lock:
                if not self._running:
                    break
            self._disruption_active = self.strait._disruption_active
            yield self.env.timeout(0.25)

    def _select_tanker_type(self) -> TankerType:
        r = self.rng.random()
        cumulative = 0.0
        for tanker_type, tanker_config in self.config.tanker_configs.items():
            cumulative += tanker_config.proportion
            if r <= cumulative:
                return tanker_type
        return list(self.config.tanker_configs.keys())[-1]

    def _speed_knots_for_type(self, tanker_type: TankerType) -> float:
        # Uniform speed for all types so ships never overtake one another visually.
        return 13.0

    def _queue_anchor(self, route: dict[str, object]) -> tuple[float, float]:
        path = list(route.get("path", []))
        if path:
            lat, lon = path[0]
            return float(lat), float(lon)
        return 26.20, 55.70

    def _refresh_waiting_positions(self) -> None:
        waiting = [s for s in self._ship_tracks.values() if s.status in {"waiting", "blocked"}]
        waiting.sort(key=lambda s: (s.route_id, s.created_at))

        last_route = None
        idx_in_route = 0
        for ship in waiting:
            if ship.route_id != last_route:
                last_route = ship.route_id
                idx_in_route = 0
            route_def = self._route_by_id.get(ship.route_id)
            base = list(route_def.get("path", [])) if route_def else []
            if base:
                base_lat, base_lon = base[0]
            else:
                base_lat, base_lon = (26.20, 55.70)

            # Create a small “anchorage queue” near the route start.
            sign = -1.0 if ship.direction == "eastbound" else 1.0
            ship.lat = float(base_lat) + sign * (idx_in_route * 0.010)
            ship.lon = float(base_lon) - sign * (idx_in_route * 0.008)
            ship.heading = 90.0 if ship.direction == "eastbound" else 270.0
            idx_in_route += 1

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            running = self._running
            paused = self._paused
            speed = self._speed

        sim_time = self.env.now if self.env else 0.0
        queue_length = sum(1 for t in self._ship_tracks.values() if t.status in ("waiting", "blocked"))
        in_transit = sum(1 for t in self._ship_tracks.values() if t.status == "in_transit")
        # Complete blockade: strait is fully closed — no ships should register as in-transit
        if self.strait and self.strait._blocked:
            in_transit = 0
        avg_wait = (sum(self._wait_times) / len(self._wait_times)) if self._wait_times else 0.0
        throughput = (self._total_completed / sim_time * 24.0) if sim_time > 0 else 0.0

        return {
            "timestamp": time.time(),
            "sim_time_hours": sim_time,
            "running": running,
            "paused": paused,
            "speed": speed,
            "disruption_active": self._disruption_active,
            "stats": {
                "total_arrivals": self._total_arrivals,
                "total_completed": self._total_completed,
                "total_deployed": self._total_deployed,
                "queue_length": queue_length,
                "in_transit": in_transit,
                "avg_wait_hours": avg_wait,
                "throughput_per_day": throughput,
                "oil_delivered_barrels": self._oil_delivered_total,
            },
            "ships": [
                {
                    "id": s.tanker_id,
                    "type": s.tanker_type,
                    "status": s.status,
                    "direction": s.direction,
                    "route_id": s.route_id,
                    "route_name": s.route_name,
                    "origin": s.origin,
                    "destination": s.destination,
                    "lat": s.lat,
                    "lon": s.lon,
                    "heading": s.heading,
                    "speed_knots": s.speed_knots,
                    "progress": s.progress,
                    "waiting_time": s.waiting_time,
                }
                for s in self._ship_tracks.values()
            ],
        }

    def routes(self) -> dict[str, Any]:
        routes_out: list[dict[str, object]] = []
        for r in self._route_defs:
            path = list(r.get("path", []))
            routes_out.append(
                {
                    "id": r.get("id"),
                    "name": r.get("name"),
                    "direction": r.get("direction"),
                    "origin": r.get("origin"),
                    "destination": r.get("destination"),
                    "path": [[float(lat), float(lon)] for (lat, lon) in path],
                }
            )

        return {
            "lanes": {
                "eastbound": [[float(lat), float(lon)] for (lat, lon) in SOUTH_LANE_LATLON],
                "westbound": [[float(lat), float(lon)] for (lat, lon) in NORTH_LANE_LATLON],
            },
            "connectors": [],
            "routes": routes_out,
            "ports": PORTS_META,
            "chokepoints": CHOKEPOINTS_META,
        }


ROOT = Path(__file__).parent
WEB_DIR = ROOT / "web"

app = FastAPI(title="Oil Tanker Flow Simulator API", version="2.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

bridge = WebSimulationBridge()
app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/routes")
async def get_routes() -> dict[str, Any]:
    return bridge.routes()


@app.get("/state")
async def get_state() -> dict[str, Any]:
    return bridge.snapshot()


@app.post("/start")
async def start_sim(req: StartRequest) -> dict[str, str]:
    bridge.start(req)
    return {"status": "started"}


@app.post("/pause")
async def pause_sim() -> dict[str, str]:
    bridge.pause()
    return {"status": "paused"}


@app.post("/resume")
async def resume_sim() -> dict[str, str]:
    bridge.resume()
    return {"status": "running"}


@app.post("/stop")
async def stop_sim() -> dict[str, str]:
    bridge.stop()
    return {"status": "stopped"}


@app.post("/speed")
async def set_speed(req: SpeedRequest) -> dict[str, float]:
    bridge.set_speed(req.speed)
    return {"speed": req.speed}


@app.websocket("/ws/state")
async def ws_state(ws: WebSocket) -> None:
    await ws.accept()
    try:
        while True:
            await ws.send_json(bridge.snapshot())
            await asyncio.sleep(0.2)
    except WebSocketDisconnect:
        return


def main() -> None:
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("ui_app:app", host="0.0.0.0", port=port, reload=False)


if __name__ == "__main__":
    main()