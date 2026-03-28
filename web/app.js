// ═══════════════════════════════════════════════════════════════════════════
//  Simple 2-D Flow Diagram — Oil Tanker Strait Simulation
//  Straight channel + colour-coded dashed branches + animated ships
// ═══════════════════════════════════════════════════════════════════════════

/* ---------- Canvas ---------- */
const canvas = document.getElementById("simCanvas");
const ctx    = canvas.getContext("2d");

new ResizeObserver(() => {
  canvas.width  = canvas.offsetWidth;
  canvas.height = canvas.offsetHeight;
}).observe(canvas);
canvas.width  = canvas.offsetWidth;
canvas.height = canvas.offsetHeight;

/* ---------- Layout (fractions of canvas W / H) ---------- */
const LAY = {
  landTop: 0.12,   // bottom edge of top land strip (Iran)
  landBot: 0.88,   // top edge of bottom land strip (Arabia)
  laneL:   0.22,   // strait entrance X
  laneR:   0.78,   // strait exit X
  outY:    0.44,   // outbound lane centre Y
  inY:     0.56,   // inbound  lane centre Y
  brL:     0.14,   // left shoreline X — export ports sit here
  brR:     0.86,   // right shoreline X — import ports sit here
};

/* ---------- Port definitions ---------- */
const EXP = [
  { id: "kharg_island", y: 0.24, label: "Kharg Island", color: "#FF8C00" },
  { id: "ras_tanura",   y: 0.50, label: "Ras Tanura",   color: "#FFA500" },
  { id: "jebel_dhanna", y: 0.76, label: "Jebel Dhanna", color: "#FF5733" },
];
const IMP = [
  { id: "fujairah",       y: 0.28, label: "Fujairah",  color: "#00BFFF" },
  { id: "mumbai_port",    y: 0.50, label: "Mumbai",     color: "#4169E1" },
  { id: "singapore_port", y: 0.72, label: "Singapore",  color: "#1E90FF" },
];

/* ---------- Route definitions ---------- */
const RDEFS = {
  kharg_to_singapore:       { exp: 0, imp: 2, dir: "out", color: "#FF8C00" },
  ras_tanura_to_mumbai:     { exp: 1, imp: 1, dir: "out", color: "#FFA500" },
  jebel_dhanna_to_fujairah: { exp: 2, imp: 0, dir: "out", color: "#FF5733" },
  singapore_to_kharg:       { exp: 0, imp: 2, dir: "in",  color: "#1E90FF" },
  mumbai_to_ras_tanura:     { exp: 1, imp: 1, dir: "in",  color: "#4169E1" },
  fujairah_to_jebel_dhanna: { exp: 2, imp: 0, dir: "in",  color: "#00BFFF" },
};

/* ---------- Smoothstep branch curve builder ---------- */
function ss(t) { return t * t * (3 - 2 * t); }

function branchPts(x0, y0, x1, y1, n = 24) {
  const pts = [];
  for (let i = 0; i <= n; i++) {
    const t = i / n;
    pts.push([x0 + t * (x1 - x0), y0 + ss(t) * (y1 - y0)]);
  }
  return pts;
}

/* ---------- Pre-build schematic paths (pct coords) per route ---------- */
const SPATHS = {};
for (const [id, r] of Object.entries(RDEFS)) {
  const ep = EXP[r.exp], ip = IMP[r.imp];
  if (r.dir === "out") {
    const lb = branchPts(LAY.brL, ep.y, LAY.laneL, LAY.outY);
    const rb = branchPts(LAY.laneR, LAY.outY, LAY.brR, ip.y);
    SPATHS[id] = [...lb, [LAY.laneR, LAY.outY], ...rb.slice(1)];
  } else {
    const rb = branchPts(LAY.brR, ip.y, LAY.laneR, LAY.inY);
    const lb = branchPts(LAY.laneL, LAY.inY, LAY.brL, ep.y);
    SPATHS[id] = [...rb, [LAY.laneL, LAY.inY], ...lb.slice(1)];
  }
}

/* ---------- Runtime state ---------- */
let geoPaths  = {};   // route_id → [[lat,lon], …]
let geoDistC  = {};   // route_id → { cum[], total }
let liveShips = [];
let pollTimer = null;

/* ---------- Simulation session state ---------- */
let simStopTimer       = null;   // auto-stop after 60s real time
let simStartWall       = 0;      // Date.now() when Start clicked
let simRunning         = false;  // backend reports running
let simPaused          = false;  // backend reports paused
let weatherPaused      = false;  // true while backend is paused for weather delay
let activeDisruption   = "NONE"; // disruption selected at start
let disruptionActiveTS = null;   // Date.now() when disruption_active first reported
let disruptionLive     = false;  // current disruption_active from backend
let oilPriceFrozen     = false;  // true once disruption ends — price stays at peak
let pricePauseStart    = null;   // Date.now() when user-paused — freezes price clock
let weatherVisualEnd   = 0;      // Date.now() + 10s  (weather visual clearing time)
let currentOilPrice    = 95.0;   // live price $/bbl

/* ---------- Cache cumulative geo distances ---------- */
function cacheGeoDist(rid, path) {
  let total = 0;
  const cum = [0];
  for (let i = 1; i < path.length; i++) {
    total += Math.hypot(path[i][0] - path[i - 1][0], path[i][1] - path[i - 1][1]);
    cum.push(total);
  }
  geoDistC[rid] = { cum, total };
}

/* ---------- Ship progress along its geo route (0 → 1) ---------- */
function geoProgress(lat, lon, rid) {
  const path = geoPaths[rid], c = geoDistC[rid];
  if (!path || !c || c.total === 0) return 0;
  let best = Infinity, bp = 0;
  for (let i = 0; i < path.length - 1; i++) {
    const [a, b] = path[i], [p, q] = path[i + 1];
    const dx = p - a, dy = q - b, sl = dx * dx + dy * dy;
    let t = sl > 0 ? ((lat - a) * dx + (lon - b) * dy) / sl : 0;
    t = Math.max(0, Math.min(1, t));
    const d = (lat - a - t * dx) ** 2 + (lon - b - t * dy) ** 2;
    if (d < best) {
      best = d;
      bp = (c.cum[i] + t * (c.cum[i + 1] - c.cum[i])) / c.total;
    }
  }
  return Math.max(0, Math.min(1, bp));
}

/* ---------- Map progress → canvas position on schematic path ---------- */
function schematicXY(rid, prog) {
  const sp = SPATHS[rid];
  if (!sp || sp.length < 2) return null;
  const W = canvas.width, H = canvas.height;
  const pts = sp.map(([x, y]) => [x * W, y * H]);
  let total = 0;
  const cl = [0];
  for (let i = 1; i < pts.length; i++) {
    total += Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]);
    cl.push(total);
  }
  if (total === 0) return pts[0];
  const tgt = prog * total;
  for (let i = 1; i < pts.length; i++) {
    if (cl[i] >= tgt) {
      const s = cl[i] - cl[i - 1];
      const t = s > 0 ? (tgt - cl[i - 1]) / s : 0;
      return [
        pts[i - 1][0] + t * (pts[i][0] - pts[i - 1][0]),
        pts[i - 1][1] + t * (pts[i][1] - pts[i - 1][1]),
      ];
    }
  }
  return pts[pts.length - 1];
}

/* ---------- Tanker colours ---------- */
const TC = {
  VLCC: "#d84b3d", SUEZMAX: "#307ad8",
  AFRAMAX: "#2d9962", PANAMAX: "#c8982e",
  blocked: "#7a1414",
};

/* ---------- Tanker icon sizes (half-length L, half-beam B in px) ---------- */
const SHIP_CFG = {
  VLCC:    { L: 12, B: 6.0 },   // supertanker — widest, most massive
  SUEZMAX: { L: 10, B: 5.0 },   // Suez-sized — wide beam
  AFRAMAX: { L:  9, B: 4.2 },   // medium
  PANAMAX: { L:  8, B: 3.5 },   // narrowest — canal-optimised
};

/**
 * Draw a top-down ship silhouette centred at (cx, cy).
 *   pointRight : true → bow faces right (outbound); false → faces left (inbound)
 *   scale      : uniform scale factor (default 1; use ~0.62 for legend)
 */
function drawTankerIcon(cx, cy, type, color, alpha, pointRight, scale = 1) {
  const raw = SHIP_CFG[type] || SHIP_CFG.PANAMAX;
  const L = raw.L * scale;
  const B = raw.B * scale;

  ctx.save();
  ctx.translate(cx, cy);
  if (!pointRight) ctx.scale(-1, 1);
  ctx.globalAlpha = alpha;

  // Hull outline — bezier stern + parallel sides + tapered bow
  ctx.beginPath();
  ctx.moveTo(-L, -B * 0.60);
  ctx.bezierCurveTo(-L * 1.12, -B * 0.28, -L * 1.12, B * 0.28, -L, B * 0.60);
  ctx.lineTo( L * 0.35,  B);
  ctx.lineTo( L,         0);
  ctx.lineTo( L * 0.35, -B);
  ctx.closePath();
  ctx.fillStyle = color;
  ctx.fill();
  ctx.strokeStyle = "rgba(20,30,40,0.75)";
  ctx.lineWidth = 0.8;
  ctx.stroke();

  // Deck centre stripe (lighter — suggests tank tops / cargo deck)
  ctx.beginPath();
  ctx.moveTo(-L * 0.52, -B * 0.36);
  ctx.lineTo( L * 0.28, -B * 0.48);
  ctx.lineTo( L * 0.78,  0);
  ctx.lineTo( L * 0.28,  B * 0.48);
  ctx.lineTo(-L * 0.52,  B * 0.36);
  ctx.closePath();
  ctx.fillStyle = "rgba(255,255,255,0.18)";
  ctx.fill();

  // Bridge / accommodation block near stern
  const bW = L * 0.30, bH = B * 0.65;
  ctx.fillStyle = "rgba(255,255,255,0.42)";
  ctx.beginPath();
  ctx.roundRect(-L * 0.78, -bH / 2, bW, bH, bW * 0.22);
  ctx.fill();

  ctx.globalAlpha = 1;
  ctx.restore();
}

// =======================================================================
//  DRAW LAYERS
// =======================================================================

function drawBg() {
  const g = ctx.createLinearGradient(0, 0, canvas.width, 0);
  g.addColorStop(0, "#a4d0e5");
  g.addColorStop(0.5, "#8ec0d8");
  g.addColorStop(1, "#a4d0e5");
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, canvas.width, canvas.height);
}

function drawLand() {
  const W = canvas.width, H = canvas.height;
  const lx = LAY.brL * W;   // left shoreline x
  const rx = LAY.brR * W;   // right shoreline x

  // Helper: fill + stroke a closed path
  function landShape() {
    ctx.fillStyle = "#dbd0a2";
    ctx.fill();
    ctx.strokeStyle = "#c0a660";
    ctx.lineWidth = 1.5;
    ctx.stroke();
  }

  // ── Left coast — export terminal side ─────────────────────────────────
  // Shore runs from top to bottom at x≈lx.  Small headlands between ports
  // (control points pushed seaward) create subtle coves at each terminal.
  ctx.beginPath();
  ctx.moveTo(0, 0);
  ctx.lineTo(lx, 0);
  ctx.quadraticCurveTo(W * (LAY.brL + 0.03), H * 0.14, lx, EXP[0].y * H);
  ctx.quadraticCurveTo(W * (LAY.brL + 0.03), H * 0.37, lx, EXP[1].y * H);
  ctx.quadraticCurveTo(W * (LAY.brL + 0.03), H * 0.63, lx, EXP[2].y * H);
  ctx.quadraticCurveTo(W * (LAY.brL + 0.03), H * 0.87, lx, H);
  ctx.lineTo(0, H);
  ctx.closePath();
  landShape();

  // ── Right coast — import destination side ─────────────────────────────
  ctx.beginPath();
  ctx.moveTo(W, 0);
  ctx.lineTo(rx, 0);
  ctx.quadraticCurveTo(W * (LAY.brR - 0.03), H * 0.14, rx, IMP[0].y * H);
  ctx.quadraticCurveTo(W * (LAY.brR - 0.03), H * 0.37, rx, IMP[1].y * H);
  ctx.quadraticCurveTo(W * (LAY.brR - 0.03), H * 0.63, rx, IMP[2].y * H);
  ctx.quadraticCurveTo(W * (LAY.brR - 0.03), H * 0.87, rx, H);
  ctx.lineTo(W, H);
  ctx.closePath();
  landShape();

  // ── Top strip — Iran (caps left/right land at the top) ────────────────
  ctx.beginPath();
  ctx.moveTo(0, 0);
  ctx.lineTo(W, 0);
  ctx.lineTo(W, LAY.landTop * H);
  ctx.quadraticCurveTo(W * 0.5, (LAY.landTop + 0.04) * H, 0, LAY.landTop * H);
  ctx.closePath();
  landShape();

  // ── Bottom strip — Arabia / Oman ──────────────────────────────────────
  ctx.beginPath();
  ctx.moveTo(0, H);
  ctx.lineTo(W, H);
  ctx.lineTo(W, LAY.landBot * H);
  ctx.quadraticCurveTo(W * 0.5, (LAY.landBot - 0.04) * H, 0, LAY.landBot * H);
  ctx.closePath();
  landShape();

  // ── Land labels ───────────────────────────────────────────────────────
  ctx.save();
  ctx.font = "bold 11px Manrope, sans-serif";
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillStyle = "#8a7a50";
  ctx.fillText("IRAN", W * 0.5, LAY.landTop * H * 0.45);
  ctx.fillText("ARABIAN PENINSULA", W * 0.5, H - (1 - LAY.landBot) * H * 0.45);

  // Side coast labels (rotated, inside the land)
  ctx.font = "bold 9px Manrope, sans-serif";
  ctx.fillStyle = "#9a8a60";

  ctx.save();
  ctx.translate(lx * 0.45, H * 0.5);
  ctx.rotate(-Math.PI / 2);
  ctx.fillText("PERSIAN GULF COAST", 0, 0);
  ctx.restore();

  ctx.save();
  ctx.translate(rx + (W - rx) * 0.55, H * 0.5);
  ctx.rotate(Math.PI / 2);
  ctx.fillText("GULF OF OMAN / ARABIAN SEA", 0, 0);
  ctx.restore();

  ctx.restore();
}

function drawBranches() {
  const W = canvas.width, H = canvas.height;
  ctx.save();
  ctx.lineWidth = 2.5;
  ctx.lineCap = "round";
  ctx.lineJoin = "round";
  ctx.setLineDash([8, 5]);

  for (const [, r] of Object.entries(RDEFS)) {
    const ep = EXP[r.exp], ip = IMP[r.imp];
    ctx.strokeStyle = r.color;

    if (r.dir === "out") {
      strokePts(branchPts(LAY.brL, ep.y, LAY.laneL, LAY.outY), W, H);
      strokePts(branchPts(LAY.laneR, LAY.outY, LAY.brR, ip.y), W, H);
    } else {
      strokePts(branchPts(LAY.brR, ip.y, LAY.laneR, LAY.inY), W, H);
      strokePts(branchPts(LAY.laneL, LAY.inY, LAY.brL, ep.y), W, H);
    }
  }
  ctx.restore();
}

function strokePts(pts, W, H) {
  ctx.beginPath();
  ctx.moveTo(pts[0][0] * W, pts[0][1] * H);
  for (let i = 1; i < pts.length; i++) ctx.lineTo(pts[i][0] * W, pts[i][1] * H);
  ctx.stroke();
}

function drawLanes() {
  const W = canvas.width, H = canvas.height;
  const x0 = LAY.laneL * W, x1 = LAY.laneR * W;

  ctx.save();
  ctx.lineCap = "round";

  // Outbound — solid orange
  ctx.strokeStyle = "#e87800";
  ctx.lineWidth = 7;
  ctx.beginPath();
  ctx.moveTo(x0, LAY.outY * H);
  ctx.lineTo(x1, LAY.outY * H);
  ctx.stroke();

  // Inbound — solid blue
  ctx.strokeStyle = "#1455a8";
  ctx.lineWidth = 7;
  ctx.beginPath();
  ctx.moveTo(x1, LAY.inY * H);
  ctx.lineTo(x0, LAY.inY * H);
  ctx.stroke();

  // Separation line
  const midY = (LAY.outY + LAY.inY) / 2 * H;
  ctx.strokeStyle = "rgba(255,255,255,0.45)";
  ctx.lineWidth = 1;
  ctx.setLineDash([6, 4]);
  ctx.beginPath();
  ctx.moveTo(x0, midY);
  ctx.lineTo(x1, midY);
  ctx.stroke();
  ctx.setLineDash([]);
  ctx.restore();

  // Direction arrows
  ctx.save();
  ctx.fillStyle = "rgba(255,255,255,0.75)";
  for (let i = 1; i <= 4; i++) {
    const ax = x0 + (i / 5) * (x1 - x0);
    tri(ax, LAY.outY * H, 6, "right");
  }
  for (let i = 1; i <= 4; i++) {
    const ax = x1 - (i / 5) * (x1 - x0);
    tri(ax, LAY.inY * H, 6, "left");
  }
  ctx.restore();

  // Lane labels — positioned above / below the lanes
  const cx = (x0 + x1) / 2;
  ctx.save();
  ctx.font = "bold 10px Manrope, sans-serif";
  ctx.textAlign = "center";

  ctx.textBaseline = "bottom";
  ctx.strokeStyle = "rgba(255,255,255,0.8)";
  ctx.lineWidth = 3;
  ctx.strokeText("OUTBOUND / EXPORT  \u25B6", cx, LAY.outY * H - 6);
  ctx.fillStyle = "#c05e00";
  ctx.fillText("OUTBOUND / EXPORT  \u25B6", cx, LAY.outY * H - 6);

  ctx.textBaseline = "top";
  ctx.strokeStyle = "rgba(255,255,255,0.8)";
  ctx.strokeText("\u25C0  INBOUND / IMPORT", cx, LAY.inY * H + 6);
  ctx.fillStyle = "#0d3f7a";
  ctx.fillText("\u25C0  INBOUND / IMPORT", cx, LAY.inY * H + 6);
  ctx.restore();

  // Strait label
  ctx.save();
  ctx.font = "italic 11px Manrope, sans-serif";
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillStyle = "rgba(11,61,82,0.3)";
  ctx.fillText("STRAIT OF HORMUZ", cx, midY);
  ctx.restore();
}

function tri(x, y, sz, dir) {
  ctx.beginPath();
  if (dir === "right") {
    ctx.moveTo(x - sz, y - sz * 0.6);
    ctx.lineTo(x + sz, y);
    ctx.lineTo(x - sz, y + sz * 0.6);
  } else {
    ctx.moveTo(x + sz, y - sz * 0.6);
    ctx.lineTo(x - sz, y);
    ctx.lineTo(x + sz, y + sz * 0.6);
  }
  ctx.closePath();
  ctx.fill();
}

function drawPortLabels() {
  const W = canvas.width, H = canvas.height;
  ctx.save();
  ctx.font = "bold 10px Manrope, sans-serif";
  ctx.textBaseline = "middle";

  // Export ports — dot at shore, label written on the left land
  ctx.textAlign = "right";
  for (const p of EXP) {
    const x = LAY.brL * W, y = p.y * H;
    dot(x, y, 4, p.color);
    label(p.label, x - 8, y);
  }

  // Import ports — dot at shore, label written on the right land
  ctx.textAlign = "left";
  for (const p of IMP) {
    const x = LAY.brR * W, y = p.y * H;
    dot(x, y, 4, p.color);
    label(p.label, x + 8, y);
  }
  ctx.restore();
}

function dot(x, y, r, color) {
  ctx.beginPath();
  ctx.arc(x, y, r, 0, Math.PI * 2);
  ctx.fillStyle = color;
  ctx.fill();
  ctx.strokeStyle = "#fff";
  ctx.lineWidth = 1.5;
  ctx.stroke();
}

function label(text, x, y) {
  ctx.strokeStyle = "rgba(255,255,255,0.85)";
  ctx.lineWidth = 3;
  ctx.strokeText(text, x, y);
  ctx.fillStyle = "#1e2a36";
  ctx.fillText(text, x, y);
}

/* ---------- Oil price engine ---------- */
function computeOilPrice() {
  if (oilPriceFrozen) return currentOilPrice;   // hold peak after disruption ends
  const base = 95.0;
  if (!disruptionActiveTS) return base;
  // Use frozen clock when user-paused so price stops ticking
  const now = (pricePauseStart && simPaused && !weatherPaused) ? pricePauseStart : Date.now();
  const sec = (now - disruptionActiveTS) / 1000;
  switch (activeDisruption) {
    case "PARTIAL_BLOCKADE":  return Math.min(135, base + sec * 0.50);
    case "COMPLETE_BLOCKADE": return Math.min(185, base + sec * 2.00);
    case "WEATHER_DELAY":     return Math.min(115, base + sec * 0.25);
    default: return base;
  }
}

function oilTrendLabel() {
  if (oilPriceFrozen) return "Elevated";
  if (!disruptionActiveTS) return "Stable";
  switch (activeDisruption) {
    case "PARTIAL_BLOCKADE":  return "Rising";
    case "COMPLETE_BLOCKADE": return "Surging";
    case "WEATHER_DELAY":     return "Slight Rise";
    default: return "Stable";
  }
}

/* ---------- Weather overlay drawing ---------- */
function drawCloud(cx, cy, sc) {
  ctx.save();
  ctx.translate(cx, cy);
  ctx.scale(sc, sc);
  ctx.fillStyle = "rgba(82,92,108,0.78)";
  ctx.beginPath();
  ctx.arc(0, 0, 22, 0, Math.PI * 2);
  ctx.arc(-18, 5, 16, 0, Math.PI * 2);
  ctx.arc(18, 5, 17, 0, Math.PI * 2);
  ctx.arc(-8, -10, 14, 0, Math.PI * 2);
  ctx.arc(10, -9, 15, 0, Math.PI * 2);
  ctx.fill();
  ctx.restore();
}

function drawRainDrops(x, y, w, h) {
  const now = Date.now();
  ctx.save();
  ctx.strokeStyle = "rgba(90,150,225,0.50)";
  ctx.lineWidth = 1.5;
  ctx.lineCap = "round";
  for (let i = 0; i < 55; i++) {
    const rx = x + ((i * 37 + Math.sin(i * 2.3) * 18) % w);
    const ry = y + ((now * 0.15 + i * 43) % h);
    ctx.beginPath();
    ctx.moveTo(rx, ry);
    ctx.lineTo(rx - 1, ry + 10);
    ctx.stroke();
  }
  ctx.restore();
}

function drawWeatherOverlay() {
  if (weatherVisualEnd <= 0 || Date.now() >= weatherVisualEnd) return;

  const W = canvas.width, H = canvas.height;
  const fade = Math.min(1, (weatherVisualEnd - Date.now()) / 3000); // fade out last 3s

  const lx = LAY.laneL * W, rx = LAY.laneR * W;
  const areaW = rx - lx;
  const cy = (LAY.outY + LAY.inY) / 2 * H;
  const topY = LAY.landTop * H;
  const botY = LAY.landBot * H;

  ctx.save();
  ctx.globalAlpha = fade;

  // Dark rain overlay over strait area
  ctx.fillStyle = "rgba(35,50,65,0.30)";
  ctx.fillRect(lx - 15, topY, areaW + 30, botY - topY);

  // Clouds
  const cx0 = (lx + rx) / 2;
  drawCloud(cx0 - areaW * 0.28, cy - 22, 1.3);
  drawCloud(cx0,                 cy - 32, 1.6);
  drawCloud(cx0 + areaW * 0.28, cy - 18, 1.2);

  // Rain
  drawRainDrops(lx, cy - 5, areaW, (botY - topY) * 0.45);

  // Label
  ctx.font = "bold 13px Manrope, sans-serif";
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.strokeStyle = "rgba(35,50,65,0.85)";
  ctx.lineWidth = 3;
  ctx.strokeText("WEATHER DELAY ACTIVE", cx0, cy + (botY - topY) * 0.32);
  ctx.fillStyle = "rgba(255,255,255,0.92)";
  ctx.fillText("WEATHER DELAY ACTIVE", cx0, cy + (botY - topY) * 0.32);

  // Countdown
  const secLeft = Math.ceil((weatherVisualEnd - Date.now()) / 1000);
  ctx.font = "11px Manrope, sans-serif";
  ctx.strokeText(`Clearing in ${secLeft}s...`, cx0, cy + (botY - topY) * 0.32 + 18);
  ctx.fillText(`Clearing in ${secLeft}s...`, cx0, cy + (botY - topY) * 0.32 + 18);

  ctx.globalAlpha = 1;
  ctx.restore();
}

function drawBlockadeOverlay() {
  if (!disruptionLive || activeDisruption !== "COMPLETE_BLOCKADE") return;

  const W = canvas.width, H = canvas.height;
  const lx = LAY.laneL * W, rx = LAY.laneR * W;
  const topY = LAY.landTop * H, botY = LAY.landBot * H;
  const cx = (lx + rx) / 2;
  const cy = (topY + botY) / 2;

  ctx.save();

  // Red-tinted overlay across strait
  ctx.fillStyle = "rgba(120,18,18,0.18)";
  ctx.fillRect(lx - 10, topY, rx - lx + 20, botY - topY);

  // Blocked banner
  ctx.font = "bold 14px Manrope, sans-serif";
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.strokeStyle = "rgba(140,20,20,0.85)";
  ctx.lineWidth = 3;
  ctx.strokeText("STRAIT BLOCKED", cx, cy);
  ctx.fillStyle = "rgba(255,240,240,0.95)";
  ctx.fillText("STRAIT BLOCKED", cx, cy);

  ctx.font = "11px Manrope, sans-serif";
  ctx.strokeText("Complete Blockade — No Vessels Transiting", cx, cy + 18);
  ctx.fillText("Complete Blockade — No Vessels Transiting", cx, cy + 18);

  ctx.restore();
}

function drawShips() {
  // During weather visual, hold ships at port (don't render in-transit)
  const weatherHold = weatherVisualEnd > 0 && Date.now() < weatherVisualEnd;
  // During complete blockade, show ships frozen at port
  const blockadeHold = disruptionLive && activeDisruption === "COMPLETE_BLOCKADE";

  const W = canvas.width, H = canvas.height;

  // ── 1. Compute every ship's raw position ──────────────────────────────
  const items = [];
  for (const ship of liveShips) {
    const rid = ship.route_id;
    if (!SPATHS[rid]) continue;

    let pos;
    if (weatherHold || blockadeHold) {
      pos = schematicXY(rid, 0);
    } else {
      const p = geoProgress(ship.lat, ship.lon, rid);
      pos = schematicXY(rid, p);
    }
    if (!pos) continue;

    const dir   = RDEFS[rid]?.dir;
    const color = (blockadeHold || ship.status === "blocked") ? TC.blocked : (TC[ship.type] || TC.PANAMAX);
    const alpha = (weatherHold || blockadeHold) ? 0.30 : (ship.status === "waiting" ? 0.45 : 0.9);
    items.push({ ship, pos: [pos[0], pos[1]], dir, color, alpha });
  }

  // ── 2. Anti-collision in the shared lane segment ──────────────────────
  //   In the lane region (laneL..laneR) all outbound ships share one Y and
  //   all inbound ships share another, so the only axis that matters is X.
  //   Sort by "who's in front" and push any follower back if too close.
  const laneL  = LAY.laneL * W;
  const laneR  = LAY.laneR * W;
  const GAP    = 28;              // min pixels between ship centres

  for (const direction of ["out", "in"]) {
    const group = items.filter(
      s => s.dir === direction && s.pos[0] >= laneL && s.pos[0] <= laneR
    );
    if (group.length < 2) continue;

    if (direction === "out") {
      // Outbound moves left→right; leader has the highest X
      group.sort((a, b) => b.pos[0] - a.pos[0]);
      for (let i = 1; i < group.length; i++) {
        const maxX = group[i - 1].pos[0] - GAP;
        if (group[i].pos[0] > maxX) group[i].pos[0] = Math.max(laneL, maxX);
      }
    } else {
      // Inbound moves right→left; leader has the lowest X
      group.sort((a, b) => a.pos[0] - b.pos[0]);
      for (let i = 1; i < group.length; i++) {
        const minX = group[i - 1].pos[0] + GAP;
        if (group[i].pos[0] < minX) group[i].pos[0] = Math.min(laneR, minX);
      }
    }
  }

  // ── 3. Draw ───────────────────────────────────────────────────────────
  ctx.save();
  for (const { ship, pos, dir, color, alpha } of items) {
    drawTankerIcon(pos[0], pos[1], ship.type, color, alpha, dir === "out");
  }
  ctx.restore();
}

function drawLegend() {
  const lw = 158, lh = 112;
  const lx = canvas.width - lw - 12;
  const ly = LAY.landTop * canvas.height + 8;

  ctx.save();
  ctx.fillStyle = "rgba(249,250,248,0.9)";
  ctx.beginPath();
  ctx.roundRect(lx, ly, lw, lh, 8);
  ctx.fill();
  ctx.strokeStyle = "rgba(100,120,140,0.25)";
  ctx.lineWidth = 1;
  ctx.stroke();

  ctx.font = "bold 10px Manrope, sans-serif";
  ctx.textAlign = "left";
  ctx.textBaseline = "middle";
  ctx.fillStyle = "#14303d";
  ctx.fillText("TANKER TYPES", lx + 10, ly + 14);

  const types = [
    ["VLCC",    TC.VLCC],
    ["SUEZMAX", TC.SUEZMAX],
    ["AFRAMAX", TC.AFRAMAX],
    ["PANAMAX", TC.PANAMAX],
  ];
  types.forEach(([name, c], i) => {
    const ty = ly + 30 + i * 19;
    drawTankerIcon(lx + 18, ty, name, c, 1, true, 0.62);
    ctx.font = "10px Manrope, sans-serif";
    ctx.fillStyle = "#1e2a36";
    ctx.textAlign = "left";
    ctx.fillText(name, lx + 34, ty);
  });
  ctx.restore();
}

function drawTitle() {
  ctx.save();
  ctx.textAlign = "left";
  ctx.textBaseline = "top";
  const tx = 12, ty = LAY.landTop * canvas.height + 8;

  ctx.font = "bold 15px Manrope, sans-serif";
  ctx.strokeStyle = "rgba(255,255,255,0.7)";
  ctx.lineWidth = 3;
  ctx.strokeText("Strait of Hormuz", tx, ty);
  ctx.fillStyle = "#0b3d52";
  ctx.fillText("Strait of Hormuz", tx, ty);

  ctx.font = "11px Manrope, sans-serif";
  ctx.strokeText("Oil Tanker Flow Simulation", tx, ty + 18);
  ctx.fillStyle = "#1e4a5e";
  ctx.fillText("Oil Tanker Flow Simulation", tx, ty + 18);
  ctx.restore();
}

/* ---------- Main render loop ---------- */
function frame() {
  drawBg();
  drawLand();
  drawBranches();
  drawLanes();
  drawPortLabels();
  drawShips();
  drawBlockadeOverlay();
  drawWeatherOverlay();
  drawLegend();
  drawTitle();

  // Tick oil price smoothly every frame
  currentOilPrice = computeOilPrice();
  if (el.oilPrice) el.oilPrice.textContent = `$${currentOilPrice.toFixed(2)}/bbl`;
  if (el.oilTrend) el.oilTrend.textContent = oilTrendLabel();

  // Dynamic running timer (0s / 60s) — keep ticking during weather pause too
  if (simStartWall > 0 && simRunning && (!simPaused || weatherPaused)) {
    const elapsed = Math.min(60, Math.floor((Date.now() - simStartWall) / 1000));
    el.status.textContent = `${elapsed}s / 60s`;
  }

  requestAnimationFrame(frame);
}

// =======================================================================
//  STATS PANEL (DOM — preserved from original)
// =======================================================================
const el = {
  duration:   document.getElementById("duration"),
  arrival:    document.getElementById("arrival"),
  capacity:   document.getElementById("capacity"),
  disruption: document.getElementById("disruption"),
  mitigation: document.getElementById("mitigation"),
  speed:      document.getElementById("speed"),
  start:      document.getElementById("startBtn"),
  pause:      document.getElementById("pauseBtn"),
  resume:     document.getElementById("resumeBtn"),
  stop:       document.getElementById("stopBtn"),
  simTime:    document.getElementById("simTime"),
  arrivals:   document.getElementById("arrivals"),
  completed:  document.getElementById("completed"),
  queue:      document.getElementById("queue"),
  transit:    document.getElementById("transit"),
  avgWait:    document.getElementById("avgWait"),
  throughput: document.getElementById("throughput"),
  status:     document.getElementById("status"),
  oilPrice:   document.getElementById("oilPrice"),
  oilTrend:   document.getElementById("oilTrend"),
};

function updateStats(payload) {
  el.simTime.textContent    = `${payload.sim_time_hours.toFixed(1)}h`;
  el.arrivals.textContent   = String(payload.stats.total_arrivals);
  el.completed.textContent  = String(payload.stats.total_completed);
  el.queue.textContent      = String(payload.stats.queue_length);
  el.transit.textContent    = String(payload.stats.in_transit);
  el.avgWait.textContent    = `${payload.stats.avg_wait_hours.toFixed(2)}h`;
  el.throughput.textContent = `${payload.stats.throughput_per_day.toFixed(2)}/day`;

  const wasPaused = simPaused;
  simRunning = !!payload.running;
  simPaused  = !!payload.paused;
  disruptionLive = !!payload.disruption_active;

  // Pause/resume oil price clock so paused time is excluded
  if (simPaused && !wasPaused && disruptionActiveTS && !weatherPaused) {
    pricePauseStart = Date.now();
  }
  if (!simPaused && wasPaused && pricePauseStart && disruptionActiveTS) {
    // Shift the start timestamp forward by the pause duration
    disruptionActiveTS += (Date.now() - pricePauseStart);
    pricePauseStart = null;
  }

  // Status — only override for stopped / user-pause (timer handled in frame loop)
  if (!payload.running) { el.status.textContent = "Stopped"; simStartWall = 0; }
  else if (payload.paused && !weatherPaused) el.status.textContent = "Paused";

  // Track disruption activation for oil price scaling
  if (payload.disruption_active && !disruptionActiveTS) {
    disruptionActiveTS = Date.now();
  } else if (!payload.disruption_active && disruptionActiveTS) {
    // Disruption ended — freeze price at current level (don't snap back)
    oilPriceFrozen = true;
    disruptionActiveTS = null;
  }
}

// =======================================================================
//  NETWORKING
// =======================================================================
async function fetchAndRenderState() {
  try {
    const res = await fetch("/state");
    if (!res.ok) return;
    const payload = await res.json();
    updateStats(payload);
    liveShips = payload.ships || [];
  } catch { /* keep polling */ }
}

function startPollingFallback() {
  if (pollTimer !== null) return;
  pollTimer = window.setInterval(fetchAndRenderState, 500);
}
function stopPollingFallback() {
  if (pollTimer !== null) { clearInterval(pollTimer); pollTimer = null; }
}

async function postJSON(url, body = null) {
  const opts = { method: "POST", headers: { "Content-Type": "application/json" } };
  if (body) opts.body = JSON.stringify(body);
  const res = await fetch(url, opts);
  if (!res.ok) throw new Error(`POST ${url} failed`);
  return res.json();
}

/* Controls */
el.start.addEventListener("click", async () => {
  // Clear any previous session timer
  if (simStopTimer) { clearTimeout(simStopTimer); simStopTimer = null; }

  activeDisruption   = el.disruption.value;
  simStartWall       = Date.now();
  disruptionActiveTS = null;
  disruptionLive     = false;
  oilPriceFrozen     = false;
  currentOilPrice    = 95.0;
  weatherPaused      = false;
  weatherVisualEnd   = activeDisruption === "WEATHER_DELAY" ? Date.now() + 10000 : 0;

  await postJSON("/start", {
    duration_hours:          Number(el.duration.value),
    arrival_rate_per_hour:   Number(el.arrival.value),
    max_concurrent_transits: Number(el.capacity.value),
    disruption:              el.disruption.value,
    mitigation:              el.mitigation.value,
  });

  // Weather delay: pause the backend so ships truly don't move during the storm,
  // then resume after 10 seconds so ships start fresh from port.
  if (activeDisruption === "WEATHER_DELAY") {
    weatherPaused = true;
    await postJSON("/pause");
    setTimeout(async () => {
      weatherPaused = false;
      try { await postJSON("/resume"); } catch {}
    }, 10000);
  }

  // Auto-stop after 60 seconds of wall-clock time
  simStopTimer = setTimeout(async () => {
    try { await postJSON("/stop"); } catch {}
    resetUI();
  }, 60000);
});
el.pause.addEventListener("click",  () => postJSON("/pause"));
el.resume.addEventListener("click", () => postJSON("/resume"));
el.stop.addEventListener("click", async () => {
  await postJSON("/stop");
  resetUI();
});
el.speed.addEventListener("change", () => postJSON("/speed", { speed: Number(el.speed.value) }));

function resetUI() {
  liveShips = [];
  if (simStopTimer) { clearTimeout(simStopTimer); simStopTimer = null; }
  simStartWall       = 0;
  simRunning         = false;
  simPaused          = false;
  weatherPaused      = false;
  activeDisruption   = "NONE";
  disruptionActiveTS = null;
  disruptionLive     = false;
  oilPriceFrozen     = false;
  weatherVisualEnd   = 0;
  currentOilPrice    = 95.0;

  el.simTime.textContent    = "0.0h";
  el.arrivals.textContent   = "0";
  el.completed.textContent  = "0";
  el.queue.textContent      = "0";
  el.transit.textContent    = "0";
  el.avgWait.textContent    = "0.00h";
  el.throughput.textContent = "0.00/day";
  el.status.textContent     = "Stopped";
  el.oilPrice.textContent   = "$95.00/bbl";
  el.oilTrend.textContent   = "Stable";
}

/* WebSocket */
function connectSocket() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${proto}://${location.host}/ws/state`);
  ws.onopen    = () => stopPollingFallback();
  ws.onmessage = (e) => {
    const p = JSON.parse(e.data);
    updateStats(p);
    liveShips = p.ships || [];
  };
  ws.onerror = () => startPollingFallback();
  ws.onclose = () => { startPollingFallback(); setTimeout(connectSocket, 1000); };
}

/* Route loader */
async function loadRoutes() {
  const res  = await fetch("/routes");
  const data = await res.json();
  for (const r of (data.routes || [])) {
    if (r.path && r.path.length >= 2) {
      geoPaths[r.id] = r.path;
      cacheGeoDist(r.id, r.path);
    }
  }
}

/* Bootstrap */
(async function () {
  await loadRoutes();
  connectSocket();
  requestAnimationFrame(frame);
})();
