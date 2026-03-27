const STRAIT_BOUNDS = L.latLngBounds([
  [25.75, 55.55],
  [26.90, 57.15],
]);

const map = L.map("map", {
  zoomControl: true,
  minZoom: 9,
  maxZoom: 12,
  maxBounds: STRAIT_BOUNDS,
  maxBoundsViscosity: 1.0,
  worldCopyJump: false,
}).setView([26.35, 56.42], 10);

L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}", {
  maxZoom: 16,
  attribution: "Tiles &copy; Esri",
  noWrap: true,
}).addTo(map);

const routeLayer = L.layerGroup().addTo(map);
const shipLayer = L.layerGroup().addTo(map);
const shipMarkers = new Map();
let pollTimer = null;

const tankerColor = {
  VLCC: "#d84b3d",
  SUEZMAX: "#307ad8",
  AFRAMAX: "#2d9962",
  PANAMAX: "#c8982e",
};

// Distinct colors for each route (by origin port)
const routeColors = {
  // Eastbound export routes (solid colors)
  ras_tanura_export: "#e63946",    // Red
  kharg_export: "#f4a261",         // Orange
  das_export: "#2a9d8f",           // Teal
  ras_laffan_export: "#9b59b6",    // Purple
  ruwais_export: "#3498db",        // Blue
  // Westbound inbound routes (similar but different shades)
  ras_tanura_inbound: "#c0392b",   // Dark red
  kharg_inbound: "#e67e22",        // Dark orange
  das_inbound: "#16a085",          // Dark teal
  ras_laffan_inbound: "#8e44ad",   // Dark purple
  ruwais_inbound: "#2980b9",       // Dark blue
};

// Lane colors for TSS
const laneColors = {
  eastbound: "#0b6ea9",  // Blue for outbound
  westbound: "#b4582f",  // Orange/rust for inbound
};

map.panInsideBounds(STRAIT_BOUNDS, { animate: false });
map.on("drag", () => {
  map.panInsideBounds(STRAIT_BOUNDS, { animate: false });
});

const el = {
  duration: document.getElementById("duration"),
  arrival: document.getElementById("arrival"),
  capacity: document.getElementById("capacity"),
  disruption: document.getElementById("disruption"),
  mitigation: document.getElementById("mitigation"),
  speed: document.getElementById("speed"),
  start: document.getElementById("startBtn"),
  pause: document.getElementById("pauseBtn"),
  resume: document.getElementById("resumeBtn"),
  stop: document.getElementById("stopBtn"),
  simTime: document.getElementById("simTime"),
  arrivals: document.getElementById("arrivals"),
  completed: document.getElementById("completed"),
  queue: document.getElementById("queue"),
  transit: document.getElementById("transit"),
  avgWait: document.getElementById("avgWait"),
  throughput: document.getElementById("throughput"),
  status: document.getElementById("status"),
};

function shipFill(type, status) {
  if (status === "blocked") {
    return "#7a1414";
  }
  return tankerColor[type] || "#c8982e";
}

function shipStyle(type, status) {
  const fill = shipFill(type, status);
  const isWaiting = status === "waiting";
  return {
    radius: 6,
    color: "#1e2a36",
    weight: 1,
    fillColor: fill,
    fillOpacity: isWaiting ? 0.55 : 0.85,
    opacity: 0.9,
  };
}

function updateStats(payload) {
  el.simTime.textContent = `${payload.sim_time_hours.toFixed(1)}h`;
  el.arrivals.textContent = String(payload.stats.total_arrivals);
  el.completed.textContent = String(payload.stats.total_completed);
  el.queue.textContent = String(payload.stats.queue_length);
  el.transit.textContent = String(payload.stats.in_transit);
  el.avgWait.textContent = `${payload.stats.avg_wait_hours.toFixed(2)}h`;
  el.throughput.textContent = `${payload.stats.throughput_per_day.toFixed(2)}/day`;

  if (!payload.running) {
    el.status.textContent = "Stopped";
  } else if (payload.paused) {
    el.status.textContent = "Paused";
  } else if (payload.disruption_active) {
    el.status.textContent = "Disruption Active";
  } else {
    el.status.textContent = "Running";
  }
}

function renderShips(payload) {
  const active = new Set();

  for (const ship of payload.ships) {
    active.add(ship.id);
    const latLng = [ship.lat, ship.lon];

    if (!shipMarkers.has(ship.id)) {
      const marker = L.circleMarker(latLng, shipStyle(ship.type, ship.status)).addTo(shipLayer);
      const routeLabel = ship.route_name || ship.route_id || ship.direction;
      marker.bindTooltip(
        `#${ship.id} ${ship.type}<br/>${routeLabel}`,
        { direction: "top", sticky: true }
      );
      shipMarkers.set(ship.id, marker);
      continue;
    }

    const marker = shipMarkers.get(ship.id);

    marker.setLatLng(latLng);
    marker.setStyle(shipStyle(ship.type, ship.status));
  }

  for (const [shipId, marker] of shipMarkers.entries()) {
    if (!active.has(shipId)) {
      shipLayer.removeLayer(marker);
      shipMarkers.delete(shipId);
    }
  }
}

async function loadRoutes() {
  const res = await fetch("/routes");
  const data = await res.json();

  routeLayer.clearLayers();

  const allPoints = [];

  if (data.lanes) {
    const eastLane = data.lanes.eastbound || [];
    const westLane = data.lanes.westbound || [];

    // Draw the main TSS lanes (thicker, more prominent)
    if (eastLane.length >= 2) {
      L.polyline(eastLane, {
        color: laneColors.eastbound,
        weight: 6,
        opacity: 0.9,
      }).addTo(routeLayer).bindTooltip("Outbound TSS Lane (Eastbound)");
      allPoints.push(...eastLane);
    }
    if (westLane.length >= 2) {
      L.polyline(westLane, {
        color: laneColors.westbound,
        weight: 6,
        opacity: 0.9,
        dashArray: "10 6",
      }).addTo(routeLayer).bindTooltip("Inbound TSS Lane (Westbound)");
      allPoints.push(...westLane);
    }

    // Draw documented full routes with distinct colors per route
    for (const r of (data.routes || [])) {
      const path = r.path || [];
      const routeId = r.id || "";
      const isWest = r.direction === "westbound";

      // Get color for this specific route
      const color = routeColors[routeId] || (isWest ? "#cc7a57" : "#2a8cc2");

      if (path.length >= 2) {
        L.polyline(path, {
          color: color,
          weight: 3,
          opacity: 0.8,
          dashArray: isWest ? "6 4" : "",
        }).addTo(routeLayer).bindTooltip(r.name || r.id || "Route");
        allPoints.push(...path);
      }
    }
  } else {
    // Backwards-compat: older API returned just two lanes.
    if (Array.isArray(data.eastbound)) {
      L.polyline(data.eastbound, { color: "#0b6ea9", weight: 4, opacity: 0.9 }).addTo(routeLayer);
      allPoints.push(...data.eastbound);
    }
    if (Array.isArray(data.westbound)) {
      L.polyline(data.westbound, { color: "#b4582f", weight: 4, opacity: 0.9, dashArray: "10 6" }).addTo(routeLayer);
      allPoints.push(...data.westbound);
    }
  }

  // Draw port markers
  for (const p of (data.ports || [])) {
    L.circleMarker([p.lat, p.lon], {
      radius: 7,
      color: "#1a5276",
      weight: 2,
      fillColor: "#3498db",
      fillOpacity: 0.7,
    }).addTo(routeLayer).bindTooltip(p.name);
    allPoints.push([p.lat, p.lon]);
  }

  // Draw chokepoint markers
  for (const c of (data.chokepoints || [])) {
    L.circleMarker([c.lat, c.lon], {
      radius: 8,
      color: "#8a1f1f",
      weight: 2,
      fillOpacity: 0.2,
    }).addTo(routeLayer).bindTooltip(c.name);
    allPoints.push([c.lat, c.lon]);
  }

  map.fitBounds(STRAIT_BOUNDS.pad(0.05));
}

async function fetchAndRenderState() {
  try {
    const res = await fetch("/state");
    if (!res.ok) {
      return;
    }
    const payload = await res.json();
    updateStats(payload);
    renderShips(payload);
  } catch {
    // Keep polling even if one request fails.
  }
}

function startPollingFallback() {
  if (pollTimer !== null) {
    return;
  }
  pollTimer = window.setInterval(fetchAndRenderState, 500);
}

function stopPollingFallback() {
  if (pollTimer !== null) {
    window.clearInterval(pollTimer);
    pollTimer = null;
  }
}

async function postJSON(url, payload = null) {
  const options = {
    method: "POST",
    headers: { "Content-Type": "application/json" },
  };
  if (payload) {
    options.body = JSON.stringify(payload);
  }
  const res = await fetch(url, options);
  if (!res.ok) {
    throw new Error(`Request failed: ${url}`);
  }
  return res.json();
}

el.start.addEventListener("click", async () => {
  const payload = {
    duration_hours: Number(el.duration.value),
    arrival_rate_per_hour: Number(el.arrival.value),
    max_concurrent_transits: Number(el.capacity.value),
    disruption: el.disruption.value,
    mitigation: el.mitigation.value,
  };
  await postJSON("/start", payload);
});

el.pause.addEventListener("click", async () => {
  await postJSON("/pause");
});

el.resume.addEventListener("click", async () => {
  await postJSON("/resume");
});

el.stop.addEventListener("click", async () => {
  await postJSON("/stop");
});

el.speed.addEventListener("change", async () => {
  await postJSON("/speed", { speed: Number(el.speed.value) });
});

function connectSocket() {
  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${protocol}://${window.location.host}/ws/state`);

  ws.onopen = () => {
    stopPollingFallback();
  };

  ws.onmessage = (event) => {
    const payload = JSON.parse(event.data);
    updateStats(payload);
    renderShips(payload);
  };

  ws.onerror = () => {
    startPollingFallback();
  };

  ws.onclose = () => {
    startPollingFallback();
    setTimeout(connectSocket, 1000);
  };
}

(async function bootstrap() {
  await loadRoutes();
  connectSocket();
})();
