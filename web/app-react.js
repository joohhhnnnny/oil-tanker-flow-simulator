const { useEffect, useMemo, useRef, useState } = React;

const STRAIT_BOUNDS = L.latLngBounds([
  [23.5, 50.0],
  [27.5, 61.0],
]);

const INITIAL_FORM = {
  duration_hours: 168,
  arrival_rate_per_hour: 0.7,
  max_concurrent_transits: 3,
  disruption: "NONE",
  mitigation: "NONE",
  speed: 1,
};

const INITIAL_SNAPSHOT = {
  sim_time_hours: 0,
  running: false,
  paused: false,
  disruption_active: false,
  stats: {
    total_arrivals: 0,
    total_completed: 0,
    queue_length: 0,
    in_transit: 0,
    avg_wait_hours: 0,
    throughput_per_day: 0,
  },
  ships: [],
};

const TANKER_COLOR = {
  VLCC: "#d84b3d",
  SUEZMAX: "#307ad8",
  AFRAMAX: "#2d9962",
  PANAMAX: "#c8982e",
};

// Distinct colors for each route
const ROUTE_COLORS = {
  // Eastbound (outbound) export routes
  ras_tanura_export: "#e63946",    // Red
  kharg_export: "#f4a261",         // Orange
  das_export: "#2a9d8f",           // Teal
  ras_laffan_export: "#9b59b6",    // Purple
  ruwais_export: "#3498db",        // Blue
  // Westbound (inbound) routes
  ras_tanura_inbound: "#c0392b",   // Dark red
  kharg_inbound: "#e67e22",        // Dark orange
  das_inbound: "#16a085",          // Dark teal
  ras_laffan_inbound: "#8e44ad",   // Dark purple
  ruwais_inbound: "#2980b9",       // Dark blue
};

// Lane colors
const LANE_COLORS = {
  eastbound: "#0b6ea9",  // Blue for outbound
  westbound: "#b4582f",  // Orange/rust for inbound
};

// Route legend data
const ROUTE_LEGEND = [
  { id: "eastbound_lane", name: "Outbound Lane (Eastbound)", color: LANE_COLORS.eastbound, dash: false },
  { id: "westbound_lane", name: "Inbound Lane (Westbound)", color: LANE_COLORS.westbound, dash: true },
  { id: "ras_tanura_export", name: "Ras Tanura Export", color: ROUTE_COLORS.ras_tanura_export, dash: false },
  { id: "kharg_export", name: "Kharg Island Export", color: ROUTE_COLORS.kharg_export, dash: false },
  { id: "das_export", name: "Das Island Export", color: ROUTE_COLORS.das_export, dash: false },
  { id: "ras_laffan_export", name: "Ras Laffan Export", color: ROUTE_COLORS.ras_laffan_export, dash: false },
  { id: "ruwais_export", name: "Ruwais Export", color: ROUTE_COLORS.ruwais_export, dash: false },
];

function shipStyle(type, status) {
  const blocked = status === "blocked";
  const waiting = status === "waiting";
  return {
    radius: 6,
    color: "#1e2a36",
    weight: 1,
    fillColor: blocked ? "#7a1414" : (TANKER_COLOR[type] || "#c8982e"),
    fillOpacity: waiting ? 0.55 : 0.85,
    opacity: 0.9,
  };
}

async function postJSON(url, payload = null) {
  const options = {
    method: "POST",
    headers: { "Content-Type": "application/json" },
  };
  if (payload !== null) {
    options.body = JSON.stringify(payload);
  }
  const res = await fetch(url, options);
  if (!res.ok) {
    throw new Error(`Request failed: ${url}`);
  }
  return res.json();
}

function useStatusLabel(snapshot) {
  return useMemo(() => {
    if (!snapshot.running) {
      return "Stopped";
    }
    if (snapshot.paused) {
      return "Paused";
    }
    if (snapshot.disruption_active) {
      return "Disruption Active";
    }
    return "Running";
  }, [snapshot]);
}

function App() {
  const [form, setForm] = useState(INITIAL_FORM);
  const [snapshot, setSnapshot] = useState(INITIAL_SNAPSHOT);
  const [routeData, setRouteData] = useState(null);

  const mapRef = useRef(null);
  const routeLayerRef = useRef(null);
  const shipLayerRef = useRef(null);
  const shipMarkersRef = useRef(new Map());
  const pollTimerRef = useRef(null);

  const statusLabel = useStatusLabel(snapshot);

  useEffect(() => {
    const map = L.map("map", {
      zoomControl: true,
      minZoom: 8,
      maxZoom: 10,
      maxBounds: STRAIT_BOUNDS,
      maxBoundsViscosity: 1.0,
      worldCopyJump: false,
      preferCanvas: true,
    }).setView([26.2, 56.45], 9);

    L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}", {
      maxZoom: 16,
      attribution: "Tiles &copy; Esri",
      noWrap: true,
    }).addTo(map);

    map.fitBounds(STRAIT_BOUNDS.pad(-0.03));
    map.on("drag", () => {
      map.panInsideBounds(STRAIT_BOUNDS, { animate: false });
    });

    mapRef.current = map;
    routeLayerRef.current = L.layerGroup().addTo(map);
    shipLayerRef.current = L.layerGroup().addTo(map);

    return () => {
      if (pollTimerRef.current !== null) {
        window.clearInterval(pollTimerRef.current);
      }
      map.remove();
      mapRef.current = null;
    };
  }, []);

  useEffect(() => {
    const loadRoutes = async () => {
      const res = await fetch("/routes");
      const data = await res.json();
      setRouteData(data);
    };

    loadRoutes().catch(() => {
      // Ignore one-off load errors; websocket/state loop will still function.
    });
  }, []);

  useEffect(() => {
    const layer = routeLayerRef.current;
    if (!layer || !routeData) {
      return;
    }

    layer.clearLayers();

    if (routeData.lanes) {
      const eastLane = routeData.lanes.eastbound || [];
      const westLane = routeData.lanes.westbound || [];

      // Draw main TSS lanes (thicker, more prominent)
      if (eastLane.length >= 2) {
        L.polyline(eastLane, {
          color: LANE_COLORS.eastbound,
          weight: 6,
          opacity: 0.9,
        }).addTo(layer).bindTooltip("Outbound TSS Lane (Eastbound)");
      }

      if (westLane.length >= 2) {
        L.polyline(westLane, {
          color: LANE_COLORS.westbound,
          weight: 6,
          opacity: 0.9,
          dashArray: "10 6",
        }).addTo(layer).bindTooltip("Inbound TSS Lane (Westbound)");
      }

      // Draw documented full routes with distinct colors per route
      for (const route of (routeData.routes || [])) {
        const path = route.path || [];
        const routeId = route.id || "";
        const isWest = route.direction === "westbound";
        if (path.length < 2) {
          continue;
        }
        const color = ROUTE_COLORS[routeId] || (isWest ? "#cc7a57" : "#2a8cc2");
        L.polyline(path, {
          color: color,
          weight: 3,
          opacity: 0.8,
          dashArray: isWest ? "6 4" : "",
        }).addTo(layer).bindTooltip(route.name || route.id || "Route");
      }
    }

    // Draw port markers
    for (const p of (routeData.ports || [])) {
      L.circleMarker([p.lat, p.lon], {
        radius: 7,
        color: "#1a5276",
        weight: 2,
        fillColor: "#3498db",
        fillOpacity: 0.7,
      }).addTo(layer).bindTooltip(p.name);
    }

    // Draw chokepoint markers
    for (const c of (routeData.chokepoints || [])) {
      L.circleMarker([c.lat, c.lon], {
        radius: 8,
        color: "#8a1f1f",
        weight: 2,
        fillOpacity: 0.2,
      }).addTo(layer).bindTooltip(c.name);
    }
  }, [routeData]);

  useEffect(() => {
    const shipLayer = shipLayerRef.current;
    if (!shipLayer) {
      return;
    }

    const active = new Set();
    for (const ship of snapshot.ships || []) {
      active.add(ship.id);
      const latLng = [ship.lat, ship.lon];
      const markers = shipMarkersRef.current;

      if (!markers.has(ship.id)) {
        const marker = L.circleMarker(latLng, shipStyle(ship.type, ship.status)).addTo(shipLayer);
        const routeLabel = ship.route_name || ship.route_id || ship.direction;
        marker.bindTooltip(`#${ship.id} ${ship.type}<br/>${routeLabel}`, { direction: "top", sticky: true });
        markers.set(ship.id, marker);
      } else {
        const marker = markers.get(ship.id);
        marker.setLatLng(latLng);
        marker.setStyle(shipStyle(ship.type, ship.status));
      }
    }

    for (const [shipId, marker] of shipMarkersRef.current.entries()) {
      if (!active.has(shipId)) {
        shipLayer.removeLayer(marker);
        shipMarkersRef.current.delete(shipId);
      }
    }
  }, [snapshot]);

  useEffect(() => {
    const fetchState = async () => {
      const res = await fetch("/state");
      if (!res.ok) {
        return;
      }
      const payload = await res.json();
      setSnapshot(payload);
    };

    const startPolling = () => {
      if (pollTimerRef.current !== null) {
        return;
      }
      pollTimerRef.current = window.setInterval(() => {
        fetchState().catch(() => {
          // Retry next tick.
        });
      }, 500);
    };

    const stopPolling = () => {
      if (pollTimerRef.current !== null) {
        window.clearInterval(pollTimerRef.current);
        pollTimerRef.current = null;
      }
    };

    const protocol = window.location.protocol === "https:" ? "wss" : "ws";
    let closed = false;
    let ws = null;

    const connect = () => {
      if (closed) {
        return;
      }

      ws = new WebSocket(`${protocol}://${window.location.host}/ws/state`);
      ws.onopen = () => {
        stopPolling();
      };

      ws.onmessage = (event) => {
        const payload = JSON.parse(event.data);
        setSnapshot(payload);
      };

      ws.onerror = () => {
        startPolling();
      };

      ws.onclose = () => {
        startPolling();
        if (!closed) {
          window.setTimeout(connect, 1000);
        }
      };
    };

    connect();

    return () => {
      closed = true;
      stopPolling();
      if (ws) {
        ws.close();
      }
    };
  }, []);

  const setField = (key, parser = Number) => (event) => {
    const value = parser(event.target.value);
    setForm((prev) => ({ ...prev, [key]: value }));
  };

  const onStart = async () => {
    await postJSON("/start", {
      duration_hours: Number(form.duration_hours),
      arrival_rate_per_hour: Number(form.arrival_rate_per_hour),
      max_concurrent_transits: Number(form.max_concurrent_transits),
      disruption: form.disruption,
      mitigation: form.mitigation,
    });
  };

  const onPause = async () => {
    await postJSON("/pause");
  };

  const onResume = async () => {
    await postJSON("/resume");
  };

  const onStop = async () => {
    await postJSON("/stop");
  };

  const onSpeed = async (event) => {
    const speed = Number(event.target.value);
    setForm((prev) => ({ ...prev, speed }));
    await postJSON("/speed", { speed });
  };

  return (
    <div className="app-shell">
      <aside className="control-panel">
        <h1>Strait Flow Control</h1>
        <p className="subtitle">React frontend + Leaflet map + FastAPI/SimPy backend</p>

        <div className="group">
          <label htmlFor="duration">Duration (hours)</label>
          <input id="duration" type="number" min="1" value={form.duration_hours} onChange={setField("duration_hours")} />
        </div>

        <div className="group">
          <label htmlFor="arrival">Arrival rate (/hour)</label>
          <input id="arrival" type="number" min="0.1" step="0.1" value={form.arrival_rate_per_hour} onChange={setField("arrival_rate_per_hour")} />
        </div>

        <div className="group">
          <label htmlFor="capacity">Concurrent transits</label>
          <input id="capacity" type="number" min="1" max="20" value={form.max_concurrent_transits} onChange={setField("max_concurrent_transits")} />
        </div>

        <div className="group">
          <label htmlFor="disruption">Disruption</label>
          <select id="disruption" value={form.disruption} onChange={setField("disruption", (x) => x)}>
            <option value="NONE">No Disruption</option>
            <option value="PARTIAL_BLOCKADE">Partial Blockade</option>
            <option value="COMPLETE_BLOCKADE">Complete Blockade</option>
            <option value="WEATHER_DELAY">Weather Delay</option>
          </select>
        </div>

        <div className="group">
          <label htmlFor="mitigation">Mitigation</label>
          <select id="mitigation" value={form.mitigation} onChange={setField("mitigation", (x) => x)}>
            <option value="NONE">None</option>
            <option value="PRIORITY_SCHEDULING">Priority Scheduling</option>
            <option value="ALTERNATIVE_ROUTING">Alternative Routing</option>
          </select>
        </div>

        <div className="group">
          <label htmlFor="speed">Speed</label>
          <select id="speed" value={String(form.speed)} onChange={onSpeed}>
            <option value="0.5">0.5x</option>
            <option value="1">1x</option>
            <option value="2">2x</option>
            <option value="5">5x</option>
            <option value="10">10x</option>
          </select>
        </div>

        <div className="button-row">
          <button id="startBtn" onClick={onStart}>Start</button>
          <button id="pauseBtn" onClick={onPause}>Pause</button>
          <button id="resumeBtn" onClick={onResume}>Resume</button>
          <button id="stopBtn" onClick={onStop}>Stop</button>
        </div>

        <section className="stats">
          <h2>Live Metrics</h2>
          <div className="stat"><span>Sim Time</span><strong>{snapshot.sim_time_hours.toFixed(1)}h</strong></div>
          <div className="stat"><span>Arrivals</span><strong>{snapshot.stats.total_arrivals}</strong></div>
          <div className="stat"><span>Completed</span><strong>{snapshot.stats.total_completed}</strong></div>
          <div className="stat"><span>Queue</span><strong>{snapshot.stats.queue_length}</strong></div>
          <div className="stat"><span>In Transit</span><strong>{snapshot.stats.in_transit}</strong></div>
          <div className="stat"><span>Avg Wait</span><strong>{snapshot.stats.avg_wait_hours.toFixed(2)}h</strong></div>
          <div className="stat"><span>Throughput</span><strong>{snapshot.stats.throughput_per_day.toFixed(2)}/day</strong></div>
          <div className="stat"><span>Status</span><strong>{statusLabel}</strong></div>
        </section>

        <section className="legend">
          <h2>Route Legend</h2>
          {ROUTE_LEGEND.map((item) => (
            <div key={item.id} className="legend-item">
              <span
                className="legend-line"
                style={{
                  backgroundColor: item.color,
                  backgroundImage: item.dash ? `repeating-linear-gradient(90deg, ${item.color} 0px, ${item.color} 6px, transparent 6px, transparent 10px)` : "none",
                  background: item.dash ? `repeating-linear-gradient(90deg, ${item.color} 0px, ${item.color} 6px, transparent 6px, transparent 10px)` : item.color,
                }}
              ></span>
              <span className="legend-label">{item.name}</span>
            </div>
          ))}
        </section>

        <section className="legend tanker-legend">
          <h2>Tanker Types</h2>
          {Object.entries(TANKER_COLOR).map(([type, color]) => (
            <div key={type} className="legend-item">
              <span className="legend-dot" style={{ backgroundColor: color }}></span>
              <span className="legend-label">{type}</span>
            </div>
          ))}
        </section>
      </aside>

      <main className="map-wrap">
        <div id="map"></div>
      </main>
    </div>
  );
}

const root = ReactDOM.createRoot(document.getElementById("root"));
root.render(<App />);
