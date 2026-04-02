// Chronicler 7.5 Prototype — Application Logic
// State management, map rendering, UI generation, demo automation

const APP = {
  state: 'setup',
  mode: 'overview',
  selectedCiv: 0,
  hoveredRegion: -1,
  currentTurn: 3812,
  demoRunning: false,
  demoTimeout: null,
  demoStep: 0,
  canvas: null,
  ctx: null,
  previewCanvas: null,
  previewCtx: null,
  tradeAnimOffset: 0,
  tradeAnimId: null,
  mapW: 1000,
  mapH: 720
};

// ============================================================
// INITIALIZATION
// ============================================================
document.addEventListener('DOMContentLoaded', () => {
  initTimelineMarkers();
  initBatchTable();
  initLeftRail();
  initEventListeners();
  initMap();
  initPreviewMap();
  updateInspector();
  updateLegend();
  updateOverlayChips();
  setState('setup');
});

function initEventListeners() {
  // Setup controls
  document.getElementById('btn-run-world').addEventListener('click', () => {
    setState('progress');
    runProgressAnimation();
  });
  document.getElementById('nav-batch-lab').addEventListener('click', () => setState('batch'));
  document.getElementById('batch-nav-new').addEventListener('click', () => setState('setup'));

  // Range sliders
  ['turns','civs','regions'].forEach(k => {
    const inp = document.getElementById('input-' + k);
    const val = document.getElementById('val-' + k);
    if (inp && val) inp.addEventListener('input', () => {
      val.textContent = k === 'turns' ? Number(inp.value).toLocaleString() : inp.value;
    });
  });

  // Toggle buttons
  document.querySelectorAll('.toggle-group').forEach(g => {
    g.querySelectorAll('.toggle-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        g.querySelectorAll('.toggle-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
      });
    });
  });

  // Mode tabs
  document.querySelectorAll('.mode-tab').forEach(tab => {
    tab.addEventListener('click', () => setMode(tab.dataset.mode));
  });

  // Rail tabs
  document.querySelectorAll('.rail-tab').forEach(tab => {
    tab.addEventListener('click', () => {
      document.querySelectorAll('.rail-tab').forEach(t => t.classList.remove('active'));
      tab.classList.add('active');
      initLeftRail(tab.dataset.tab);
    });
  });

  // Timeline scrub
  const track = document.getElementById('timeline-track');
  if (track) {
    track.addEventListener('click', (e) => {
      const rect = track.getBoundingClientRect();
      const pct = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
      scrubTimeline(Math.round(pct * 5000));
    });
  }

  // Map interaction
  const mapEl = document.getElementById('map-viewport');
  if (mapEl) {
    mapEl.addEventListener('mousemove', onMapMouseMove);
    mapEl.addEventListener('mouseleave', () => { APP.hoveredRegion = -1; renderMap(); hideHoverCard(); });
    mapEl.addEventListener('click', onMapClick);
  }

  // Demo controls
  document.getElementById('btn-auto-demo').addEventListener('click', startDemo);
  document.getElementById('btn-pause-demo').addEventListener('click', pauseDemo);
  document.querySelectorAll('.jump-btn').forEach(btn => {
    btn.addEventListener('click', () => jumpTo(btn.dataset.jump));
  });

  // Filter chips
  document.querySelectorAll('.filter-chip').forEach(chip => {
    chip.addEventListener('click', () => {
      document.querySelectorAll('.filter-chip').forEach(c => c.classList.remove('active'));
      chip.classList.add('active');
    });
  });
}

// ============================================================
// STATE MANAGEMENT
// ============================================================
function setState(newState) {
  APP.state = newState;
  document.querySelectorAll('.app-state').forEach(el => el.classList.remove('active'));
  const stateMap = { setup:'state-setup', progress:'state-progress', viewer:'state-viewer', batch:'state-batch' };
  const el = document.getElementById(stateMap[newState]);
  if (el) {
    el.classList.add('active');
    if (newState === 'viewer') {
      setTimeout(() => { resizeMap(); renderMap(); }, 50);
    }
  }
  // Update jump buttons
  document.querySelectorAll('.jump-btn').forEach(b => b.classList.remove('active'));
  const jumpMap = { setup:'setup', progress:'progress', viewer:'overview', batch:'batch' };
  const activeJump = jumpMap[newState] || APP.mode;
  document.querySelector(`.jump-btn[data-jump="${activeJump}"]`)?.classList.add('active');
}

function setMode(newMode) {
  APP.mode = newMode;
  document.querySelectorAll('.mode-tab').forEach(t => t.classList.remove('active'));
  document.querySelector(`.mode-tab[data-mode="${newMode}"]`)?.classList.add('active');

  // Validation ribbon
  const ribbon = document.getElementById('validation-ribbon');
  if (newMode === 'campaign') ribbon.classList.remove('hidden');
  else ribbon.classList.add('hidden');

  updateInspector();
  updateLegend();
  updateOverlayChips();
  renderMap();

  // Update jump buttons
  document.querySelectorAll('.jump-btn').forEach(b => b.classList.remove('active'));
  document.querySelector(`.jump-btn[data-jump="${newMode}"]`)?.classList.add('active');
}

function scrubTimeline(turn) {
  APP.currentTurn = turn;
  const pct = (turn / 5000) * 100;
  const ph = document.getElementById('timeline-playhead');
  ph.style.left = pct + '%';
  ph.querySelector('.playhead-label').textContent = 'T' + turn;
}

// ============================================================
// MAP RENDERING
// ============================================================
function initMap() {
  APP.canvas = document.getElementById('main-map');
  APP.ctx = APP.canvas.getContext('2d');
  window.addEventListener('resize', () => { resizeMap(); renderMap(); });
  resizeMap();
}

function resizeMap() {
  if (!APP.canvas) return;
  const parent = APP.canvas.parentElement;
  const dpr = window.devicePixelRatio || 1;
  APP.canvas.width = parent.clientWidth * dpr;
  APP.canvas.height = parent.clientHeight * dpr;
  APP.canvas.style.width = parent.clientWidth + 'px';
  APP.canvas.style.height = parent.clientHeight + 'px';
  APP.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
}

function mapX(x) { return (x / APP.mapW) * (APP.canvas.width / (window.devicePixelRatio||1)); }
function mapY(y) { return (y / APP.mapH) * (APP.canvas.height / (window.devicePixelRatio||1)); }

function renderMap() {
  const ctx = APP.ctx;
  if (!ctx) return;
  const w = APP.canvas.width / (window.devicePixelRatio||1);
  const h = APP.canvas.height / (window.devicePixelRatio||1);
  ctx.clearRect(0, 0, w, h);

  drawWater(ctx, w, h);
  drawContinent(ctx, w, h);
  drawRegionFills(ctx, w, h);
  drawContourLines(ctx, w, h);
  drawBorders(ctx, w, h);
  drawCoastline(ctx, w, h);

  if (APP.mode === 'trade') drawTradeRoutes(ctx, w, h);
  if (APP.mode === 'campaign') drawCampaignOverlay(ctx, w, h);

  drawSettlements(ctx, w, h);
  drawRegionLabels(ctx, w, h);
  drawHoverEffect(ctx, w, h);
}

function getContinentPath(ctx) {
  // Build the full continent outline from all region outer edges
  // For simplicity, draw all regions filled — the continent IS the union of regions
  ctx.beginPath();
  REGIONS.forEach(r => {
    ctx.moveTo(mapX(r.poly[0][0]), mapY(r.poly[0][1]));
    for (let i = 1; i < r.poly.length; i++) ctx.lineTo(mapX(r.poly[i][0]), mapY(r.poly[i][1]));
    ctx.closePath();
  });
}

function drawWater(ctx, w, h) {
  const grd = ctx.createRadialGradient(w/2, h/2, 0, w/2, h/2, Math.max(w,h)*0.7);
  grd.addColorStop(0, '#1a1c28');
  grd.addColorStop(1, '#0e1018');
  ctx.fillStyle = grd;
  ctx.fillRect(0, 0, w, h);

  // Subtle water noise
  ctx.globalAlpha = 0.03;
  for (let i = 0; i < 200; i++) {
    const x = seededRandom(i * 7) * w;
    const y = seededRandom(i * 13 + 5) * h;
    ctx.fillStyle = '#4a6a8a';
    ctx.fillRect(x, y, 2, 1);
  }
  ctx.globalAlpha = 1;
}

function drawContinent(ctx, w, h) {
  // Fill all regions with land base color
  REGIONS.forEach(r => {
    ctx.beginPath();
    ctx.moveTo(mapX(r.poly[0][0]), mapY(r.poly[0][1]));
    for (let i = 1; i < r.poly.length; i++) ctx.lineTo(mapX(r.poly[i][0]), mapY(r.poly[i][1]));
    ctx.closePath();
    ctx.fillStyle = '#2a2720';
    ctx.fill();
  });
}

function drawRegionFills(ctx, w, h) {
  REGIONS.forEach((r, idx) => {
    ctx.beginPath();
    ctx.moveTo(mapX(r.poly[0][0]), mapY(r.poly[0][1]));
    for (let i = 1; i < r.poly.length; i++) ctx.lineTo(mapX(r.poly[i][0]), mapY(r.poly[i][1]));
    ctx.closePath();
    ctx.fillStyle = CIVS[r.owner].fill;
    ctx.fill();
  });
}

function drawContourLines(ctx, w, h) {
  ctx.save();
  // Clip to continent
  getContinentPath(ctx);
  ctx.clip();
  ctx.strokeStyle = 'rgba(200,190,170,0.06)';
  ctx.lineWidth = 0.5;
  for (let y = 30; y < APP.mapH; y += 25) {
    ctx.beginPath();
    for (let x = 0; x <= APP.mapW; x += 5) {
      const ny = y + Math.sin(x * 0.015 + y * 0.01) * 8 + Math.sin(x * 0.03) * 4;
      if (x === 0) ctx.moveTo(mapX(x), mapY(ny));
      else ctx.lineTo(mapX(x), mapY(ny));
    }
    ctx.stroke();
  }
  ctx.restore();
}

function drawBorders(ctx, w, h) {
  ctx.strokeStyle = 'rgba(157,138,94,0.35)';
  ctx.lineWidth = 1.2;
  REGIONS.forEach(r => {
    ctx.beginPath();
    ctx.moveTo(mapX(r.poly[0][0]), mapY(r.poly[0][1]));
    for (let i = 1; i < r.poly.length; i++) ctx.lineTo(mapX(r.poly[i][0]), mapY(r.poly[i][1]));
    ctx.closePath();
    ctx.stroke();
  });
}

function drawCoastline(ctx, w, h) {
  // Draw outer edges with slightly brighter gold
  ctx.strokeStyle = 'rgba(157,138,94,0.5)';
  ctx.lineWidth = 1.8;
  REGIONS.forEach(r => {
    ctx.beginPath();
    ctx.moveTo(mapX(r.poly[0][0]), mapY(r.poly[0][1]));
    for (let i = 1; i < r.poly.length; i++) ctx.lineTo(mapX(r.poly[i][0]), mapY(r.poly[i][1]));
    ctx.closePath();
    ctx.stroke();
  });
}

function drawSettlements(ctx, w, h) {
  REGIONS.forEach(r => {
    r.settlements.forEach(s => {
      const sx = mapX(s.x), sy = mapY(s.y);
      const size = s.cap ? 5 : 3;
      // Glow
      ctx.shadowColor = s.cap ? 'rgba(196,170,106,0.4)' : 'rgba(200,195,180,0.3)';
      ctx.shadowBlur = s.cap ? 8 : 4;
      ctx.fillStyle = s.cap ? '#c4aa6a' : '#b0a890';
      if (s.cap) {
        // Diamond
        ctx.beginPath();
        ctx.moveTo(sx, sy - size); ctx.lineTo(sx + size, sy);
        ctx.lineTo(sx, sy + size); ctx.lineTo(sx - size, sy);
        ctx.closePath(); ctx.fill();
      } else {
        ctx.beginPath(); ctx.arc(sx, sy, size, 0, Math.PI * 2); ctx.fill();
      }
      ctx.shadowBlur = 0;
      // Label
      ctx.font = `${s.cap ? '600 11' : '10'}px Inter, sans-serif`;
      ctx.fillStyle = s.cap ? '#ddd8cc' : '#9e978a';
      ctx.textAlign = 'center';
      ctx.fillText(s.name, sx, sy + (s.cap ? 14 : 12));
    });
  });
}

function drawRegionLabels(ctx, w, h) {
  ctx.font = '500 9px Inter, sans-serif';
  ctx.textAlign = 'center';
  ctx.fillStyle = 'rgba(200,195,180,0.25)';
  REGIONS.forEach(r => {
    const cx = r.poly.reduce((a, p) => a + p[0], 0) / r.poly.length;
    const cy = r.poly.reduce((a, p) => a + p[1], 0) / r.poly.length;
    ctx.fillText(r.name.toUpperCase(), mapX(cx), mapY(cy) - 4);
  });
}

function drawTradeRoutes(ctx, w, h) {
  // Animate offset
  const offset = APP.tradeAnimOffset;
  TRADE_ROUTES.forEach((route, i) => {
    const fx = mapX(route.from.x), fy = mapY(route.from.y);
    const tx = mapX(route.to.x), ty = mapY(route.to.y);
    // Route line
    ctx.save();
    ctx.strokeStyle = parseFloat(route.margin) < 0 ? 'rgba(176,80,80,0.5)' : 'rgba(196,160,74,0.5)';
    ctx.lineWidth = 2.5;
    ctx.setLineDash([8, 6]);
    ctx.lineDashOffset = -offset;
    ctx.beginPath(); ctx.moveTo(fx, fy); ctx.lineTo(tx, ty); ctx.stroke();
    ctx.setLineDash([]);
    ctx.restore();
    // Route label at midpoint
    const mx = (fx + tx) / 2, my = (fy + ty) / 2;
    ctx.font = '500 9px Inter, sans-serif';
    ctx.fillStyle = 'rgba(196,160,74,0.7)';
    ctx.textAlign = 'center';
    ctx.fillText(route.label, mx, my - 6);
    // Flow dots
    const t = ((offset / 50) + i * 0.3) % 1;
    const dx = fx + (tx - fx) * t, dy = fy + (ty - fy) * t;
    ctx.beginPath(); ctx.arc(dx, dy, 3, 0, Math.PI * 2);
    ctx.fillStyle = 'rgba(196,170,106,0.8)'; ctx.fill();
  });
}

function drawCampaignOverlay(ctx, w, h) {
  // Army paths
  CAMPAIGN_ARMIES.forEach(army => {
    ctx.save();
    const color = army.civ === 0 ? 'rgba(138,64,64,0.7)' : army.civ === 2 ? 'rgba(180,120,50,0.6)' : 'rgba(106,74,122,0.6)';
    ctx.strokeStyle = color;
    ctx.lineWidth = 3;
    ctx.setLineDash([6, 4]);
    ctx.beginPath();
    army.path.forEach((p, i) => {
      if (i === 0) ctx.moveTo(mapX(p[0]), mapY(p[1]));
      else ctx.lineTo(mapX(p[0]), mapY(p[1]));
    });
    ctx.stroke();
    ctx.setLineDash([]);

    // Arrow at end
    const last = army.path[army.path.length - 1];
    const prev = army.path[army.path.length - 2];
    const angle = Math.atan2(mapY(last[1]) - mapY(prev[1]), mapX(last[0]) - mapX(prev[0]));
    const ax = mapX(last[0]), ay = mapY(last[1]);
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.moveTo(ax + Math.cos(angle) * 10, ay + Math.sin(angle) * 10);
    ctx.lineTo(ax + Math.cos(angle + 2.5) * 8, ay + Math.sin(angle + 2.5) * 8);
    ctx.lineTo(ax + Math.cos(angle - 2.5) * 8, ay + Math.sin(angle - 2.5) * 8);
    ctx.closePath(); ctx.fill();

    // Army chip
    const chipX = mapX(army.path[0][0]), chipY = mapY(army.path[0][1]) - 16;
    ctx.fillStyle = 'rgba(20,20,28,0.85)';
    ctx.strokeStyle = color;
    ctx.lineWidth = 1;
    roundRect(ctx, chipX - 40, chipY - 10, 80, 20, 3);
    ctx.fill(); ctx.stroke();
    ctx.font = '600 9px Inter, sans-serif';
    ctx.fillStyle = '#ddd8cc';
    ctx.textAlign = 'center';
    ctx.fillText(army.name, chipX, chipY + 3);
    ctx.restore();
  });

  // Battle sites
  BATTLE_SITES.forEach(b => {
    const bx = mapX(b.x), by = mapY(b.y);
    ctx.save();
    ctx.shadowColor = 'rgba(176,80,80,0.5)';
    ctx.shadowBlur = 8;
    ctx.fillStyle = '#b05555';
    ctx.beginPath();
    // X mark
    ctx.font = 'bold 16px Inter, sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText('✕', bx, by + 5);
    ctx.shadowBlur = 0;
    ctx.font = '500 9px Inter, sans-serif';
    ctx.fillStyle = 'rgba(176,85,85,0.8)';
    ctx.fillText(b.name, bx, by + 18);
    ctx.restore();
  });
}

function drawHoverEffect(ctx, w, h) {
  if (APP.hoveredRegion < 0) return;
  const r = REGIONS[APP.hoveredRegion];
  ctx.save();
  ctx.beginPath();
  ctx.moveTo(mapX(r.poly[0][0]), mapY(r.poly[0][1]));
  for (let i = 1; i < r.poly.length; i++) ctx.lineTo(mapX(r.poly[i][0]), mapY(r.poly[i][1]));
  ctx.closePath();
  ctx.fillStyle = 'rgba(74,158,187,0.12)';
  ctx.fill();
  ctx.strokeStyle = 'rgba(74,158,187,0.5)';
  ctx.lineWidth = 2;
  ctx.stroke();
  ctx.restore();
}

function roundRect(ctx, x, y, w, h, r) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.lineTo(x + w - r, y); ctx.quadraticCurveTo(x + w, y, x + w, y + r);
  ctx.lineTo(x + w, y + h - r); ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
  ctx.lineTo(x + r, y + h); ctx.quadraticCurveTo(x, y + h, x, y + h - r);
  ctx.lineTo(x, y + r); ctx.quadraticCurveTo(x, y, x + r, y);
  ctx.closePath();
}

function seededRandom(seed) {
  const x = Math.sin(seed * 127.1 + 311.7) * 43758.5453;
  return x - Math.floor(x);
}

// ============================================================
// MAP INTERACTION
// ============================================================
function onMapMouseMove(e) {
  const rect = APP.canvas.getBoundingClientRect();
  const mx = (e.clientX - rect.left) / rect.width * APP.mapW;
  const my = (e.clientY - rect.top) / rect.height * APP.mapH;

  let found = -1;
  for (let i = 0; i < REGIONS.length; i++) {
    if (pointInPoly(mx, my, REGIONS[i].poly)) { found = i; break; }
  }
  if (found !== APP.hoveredRegion) {
    APP.hoveredRegion = found;
    renderMap();
    if (found >= 0) showHoverCard(e, REGIONS[found]);
    else hideHoverCard();
  } else if (found >= 0) {
    moveHoverCard(e);
  }
}

function onMapClick(e) {
  if (APP.hoveredRegion >= 0) {
    APP.selectedCiv = REGIONS[APP.hoveredRegion].owner;
    updateInspector();
  }
}

function pointInPoly(x, y, poly) {
  let inside = false;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const xi = poly[i][0], yi = poly[i][1];
    const xj = poly[j][0], yj = poly[j][1];
    if ((yi > y) !== (yj > y) && x < (xj - xi) * (y - yi) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}

function showHoverCard(e, region) {
  const card = document.getElementById('map-hover-card');
  const civ = CIVS[region.owner];
  card.innerHTML = `
    <div class="hover-card-title">${region.name}</div>
    <div class="hover-card-owner">${civ.name}</div>
    <div class="hover-card-stat"><span>Settlements</span><strong>${region.settlements.length}</strong></div>
    <div class="hover-card-stat"><span>Control</span><strong>Stable</strong></div>
  `;
  card.classList.add('visible');
  moveHoverCard(e);
}

function moveHoverCard(e) {
  const card = document.getElementById('map-hover-card');
  const vp = document.getElementById('map-viewport').getBoundingClientRect();
  card.style.left = (e.clientX - vp.left + 14) + 'px';
  card.style.top = (e.clientY - vp.top - 10) + 'px';
}

function hideHoverCard() {
  document.getElementById('map-hover-card').classList.remove('visible');
}

// ============================================================
// PREVIEW MAP (setup)
// ============================================================
function initPreviewMap() {
  const c = document.getElementById('setup-preview-map');
  if (!c) return;
  const ctx = c.getContext('2d');
  const s = 0.48;
  // Water
  ctx.fillStyle = '#12141e';
  ctx.fillRect(0, 0, c.width, c.height);
  // Land
  REGIONS.forEach(r => {
    ctx.beginPath();
    ctx.moveTo(r.poly[0][0] * s, r.poly[0][1] * s);
    for (let i = 1; i < r.poly.length; i++) ctx.lineTo(r.poly[i][0] * s, r.poly[i][1] * s);
    ctx.closePath();
    ctx.fillStyle = CIVS[r.owner].fill.replace('0.35', '0.5');
    ctx.fill();
    ctx.strokeStyle = 'rgba(157,138,94,0.3)';
    ctx.lineWidth = 0.8;
    ctx.stroke();
  });
  // Settlements
  REGIONS.forEach(r => r.settlements.forEach(st => {
    ctx.beginPath(); ctx.arc(st.x * s, st.y * s, st.cap ? 3 : 1.5, 0, Math.PI * 2);
    ctx.fillStyle = st.cap ? '#c4aa6a' : '#8a8070';
    ctx.fill();
  }));
}

// ============================================================
// TIMELINE MARKERS
// ============================================================
function initTimelineMarkers() {
  const eventsEl = document.getElementById('timeline-events');
  const narrEl = document.getElementById('timeline-narrated');
  if (!eventsEl) return;

  TIMELINE_EVENTS.forEach(ev => {
    const dot = document.createElement('div');
    dot.className = 'timeline-event ' + ev.type;
    dot.style.left = ev.pos + '%';
    eventsEl.appendChild(dot);
  });

  NARRATED_SEGMENTS.forEach(seg => {
    const bar = document.createElement('div');
    bar.className = 'narrated-segment';
    bar.style.left = seg.start + '%';
    bar.style.width = (seg.end - seg.start) + '%';
    narrEl.appendChild(bar);
  });
}

// ============================================================
// LEFT RAIL CONTENT
// ============================================================
function initLeftRail(tab) {
  const el = document.getElementById('left-rail-content');
  if (!el) return;
  tab = tab || 'chronicle';
  if (tab === 'chronicle') {
    el.innerHTML = CHRONICLE_ENTRIES.map((c, i) => `
      <div class="chronicle-entry${i === 0 ? ' active' : ''}">
        <div class="chronicle-turn">Turn ${c.turn}</div>
        <div class="chronicle-text">${c.text}</div>
        <span class="chronicle-type ${c.type}">${c.type === 'narrated' ? 'Narrated' : 'Mechanical'}</span>
      </div>
    `).join('');
  } else {
    el.innerHTML = EVENT_LOG.map(ev => `
      <div class="event-entry">
        <span class="event-turn">T${ev.turn}</span>
        <span class="event-type-badge ${ev.type}">${ev.typeLabel}</span>
        <span class="event-desc">${ev.desc}</span>
      </div>
    `).join('');
  }
}

// ============================================================
// INSPECTOR (RIGHT RAIL)
// ============================================================
function updateInspector() {
  const el = document.getElementById('inspector');
  if (!el) return;
  el.className = 'inspector inspector-transition';
  switch (APP.mode) {
    case 'overview': el.innerHTML = getOverviewInspector(); break;
    case 'character': el.innerHTML = getCharacterInspector(); break;
    case 'trade': el.innerHTML = getTradeInspector(); break;
    case 'campaign': el.innerHTML = getCampaignInspector(); break;
  }
  // Re-trigger animation
  void el.offsetWidth;
}

function getOverviewInspector() {
  const c = CIVS[APP.selectedCiv];
  return `
    <div class="insp-header">
      <div class="insp-title">${c.name}</div>
      <div class="insp-subtitle">Turn ${APP.currentTurn} — Strategic Overview</div>
    </div>
    <div class="insp-section">
      <div class="insp-section-title">Demographics</div>
      ${inspRow('Population', c.pop)}
      ${inspRow('Growth', c.growth, c.growth.startsWith('+') ? 'positive' : 'negative')}
      ${inspRow('Urbanization', '34%')}
    </div>
    <div class="insp-section">
      <div class="insp-section-title">Faction Influence</div>
      ${inspBar('Military', 72, '#8a4040')}
      ${inspBar('Religious', 45, '#6a5a8a')}
      ${inspBar('Merchant', 58, '#c4a04a')}
      ${inspBar('Scholar', 33, '#4a9ebb')}
    </div>
    <div class="insp-section">
      <div class="insp-section-title">Economy</div>
      ${inspRow('Treasury', c.treasury, 'mono')}
      ${inspRow('Income', c.income, 'positive')}
      ${inspRow('Trade Balance', c.trade, c.trade.startsWith('+') ? 'positive' : 'negative')}
    </div>
    <div class="insp-section">
      <div class="insp-section-title">Stability</div>
      ${inspBar('Class Tension', 42, '#b05050')}
      ${inspBar('Faith Cohesion', 68, '#6a5a8a')}
      ${inspBar('Cultural Unity', 75, '#4a9ebb')}
      ${inspBar('Asabiya', 61, '#c4aa6a')}
    </div>
    <div class="insp-section">
      <div class="insp-section-title">Succession</div>
      ${inspRow('Ruler', 'Aldric the Elder')}
      ${inspRow('Heir', 'Mira Thornchild')}
      ${inspRow('Stability', 'Contested', 'amber')}
    </div>
  `;
}

function getCharacterInspector() {
  const ch = CHARACTER;
  return `
    <div class="insp-header">
      <div class="insp-title">${ch.name}</div>
      <div class="insp-subtitle">Stable ID: ${ch.stableId} · ${ch.occupation}</div>
    </div>
    <div class="insp-section">
      <div class="insp-section-title">Identity</div>
      ${inspRow('Born', 'Turn ' + ch.born)}
      ${inspRow('Age', ch.age + ' turns')}
      ${inspRow('Civilization', CIVS[ch.civ].short)}
      ${inspRow('Location', ch.location)}
    </div>
    ${ch.isMule ? `<div class="insp-section"><div class="insp-section-title">Mule Status</div>
      <div class="mule-indicator"><div class="mule-dot"></div>
      <div class="mule-text">Mule — warped by: ${ch.muleMemory}<br>Remaining: ${ch.muleTurns} active turns</div></div></div>` : ''}
    <div class="insp-section">
      <div class="insp-section-title">Needs (6-Axis)</div>
      ${Object.entries(ch.needs).map(([k, v]) => inspBar(k.charAt(0).toUpperCase() + k.slice(1), Math.round(v * 100), v > 0.7 ? '#5a9a5a' : v > 0.4 ? '#c4a030' : '#b05050')).join('')}
    </div>
    <div class="insp-section">
      <div class="insp-section-title">Key Memories</div>
      ${ch.memories.map(m => `
        <div class="event-entry" style="padding:4px 0;border:none">
          <span class="event-turn">T${m.turn}</span>
          <span class="event-desc">${m.text}</span>
          ${m.legacy ? '<span class="insp-tag" style="color:#c4aa6a;border-color:#6a5d3a">Legacy</span>' : ''}
        </div>`).join('')}
    </div>
    <div class="insp-section">
      <div class="insp-section-title">Relationships</div>
      ${ch.relationships.map(r => `
        <div class="insp-row">
          <span class="insp-row-label">${r.name} <span style="color:var(--text-tertiary);font-size:10px">(${r.relation})</span></span>
          <span class="insp-row-value ${r.strength > 0 ? 'positive' : 'negative'}">${r.strength > 0 ? '+' : ''}${r.strength.toFixed(2)}</span>
        </div>`).join('')}
    </div>
    <div class="insp-section">
      <div class="insp-section-title">Active Decision Pressures</div>
      ${ch.decisions.map(d => `<div style="font-size:11px;color:var(--text-secondary);padding:3px 0;border-bottom:1px solid var(--chrome-border)">▸ ${d}</div>`).join('')}
    </div>
    <div class="insp-section">
      <div class="insp-section-title">Dynasty</div>
      ${ch.dynasty.map(d => `<div style="font-size:11px;color:var(--text-secondary);padding:2px 0">· ${d}</div>`).join('')}
    </div>
  `;
}

function getTradeInspector() {
  const route = TRADE_ROUTES[2]; // Ashenmere-Harborlight
  return `
    <div class="insp-header">
      <div class="insp-title">Trade Diagnostics</div>
      <div class="insp-subtitle">${TRADE_ROUTES.length} active routes · Turn ${APP.currentTurn}</div>
    </div>
    <div class="insp-section">
      <div class="insp-section-title">Route Inspection</div>
      ${inspRow('Route', route.label)}
      ${inspRow('Profit', route.profit, 'positive')}
      ${inspRow('Margin', route.margin, 'positive')}
      ${inspRow('Goods', route.goods)}
      ${inspRow('Confidence', route.confidence, 'cyan')}
      ${inspRow('Freshness', '0.94', 'positive')}
      ${inspRow('In-Transit', '3 caravans')}
    </div>
    <div class="insp-section">
      <div class="insp-section-title">Price Beliefs</div>
      ${inspRow('Spices (Stale)', '14.2g', 'amber')}
      ${inspRow('Spices (Current)', '16.8g', 'positive')}
      ${inspRow('Textiles (Stale)', '8.1g', 'amber')}
      ${inspRow('Textiles (Current)', '7.9g', 'positive')}
      ${inspRow('Merchant Plan', 'Maximize margin')}
    </div>
    <div class="insp-section">
      <div class="insp-section-title">Market: Harborlight</div>
      ${inspBar('Food Sufficiency', 82, '#5a9a5a')}
      ${inspBar('Import Share', 38, '#c4a04a')}
      ${inspBar('Trade Dependency', 65, '#b05050')}
      ${inspRow('Settlement Role', 'Trade Hub')}
      ${inspRow('Supply/Demand', 'Surplus', 'positive')}
      ${inspRow('Stockpile Trend', '↑ Growing', 'positive')}
    </div>
  `;
}

function getCampaignInspector() {
  const army = CAMPAIGN_ARMIES[0];
  const battle = BATTLE_SITES[0];
  return `
    <div class="insp-header">
      <div class="insp-title">Campaign Intel</div>
      <div class="insp-subtitle">Military Intelligence · Turn ${APP.currentTurn}</div>
    </div>
    <div class="insp-section">
      <div class="insp-section-title">Army: ${army.name}</div>
      ${inspRow('Strength', army.strength)}
      ${inspRow('Morale', army.morale)}
      ${inspRow('Status', army.status, 'amber')}
      ${inspRow('Target', army.target)}
      ${inspRow('Supply', '72% capacity', 'amber')}
      ${inspRow('Target Rationale', 'Secure river crossing')}
    </div>
    <div class="insp-section">
      <div class="insp-section-title">Last Battle: ${battle.name}</div>
      ${inspRow('Turn', 'T' + battle.turn)}
      ${inspRow('Result', battle.result)}
      ${inspRow('Casualties', '340 total')}
      ${inspRow('Occupied', 'Deepmire Ford')}
    </div>
    <div class="insp-section">
      <div class="insp-section-title">Knowledge Diagnostics</div>
      ${inspBar('Freshness', 78, '#5a9a5a')}
      ${inspBar('Confidence', 65, '#c4a030')}
      ${inspBar('Familiarity', 82, '#4a9ebb')}
      ${inspRow('Staleness', '2 turns since update')}
      ${inspRow('Knowledge Fog', 'Partial — East border')}
    </div>
    <div class="insp-section">
      <div class="insp-section-title">March Timeline</div>
      <div style="font-size:11px;color:var(--text-secondary)">
        <div style="padding:3px 0">T3808 — Departed Thornwall</div>
        <div style="padding:3px 0">T3809 — Crossed Grey Highlands</div>
        <div style="padding:3px 0;color:var(--accent-cyan)">T3810 — Engaged at Deepmire Ford ✕</div>
        <div style="padding:3px 0">T3811 — Regrouped, advanced east</div>
        <div style="padding:3px 0;color:var(--text-tertiary)">T3812 — Current position (Sunken Reach border)</div>
      </div>
    </div>
  `;
}

// Inspector helpers
function inspRow(label, value, cls) {
  return `<div class="insp-row"><span class="insp-row-label">${label}</span><span class="insp-row-value${cls ? ' ' + cls : ''}">${value}</span></div>`;
}
function inspBar(label, pct, color) {
  return `<div class="insp-bar-row">
    <div class="insp-bar-label"><span>${label}</span><span>${pct}%</span></div>
    <div class="insp-bar"><div class="insp-bar-fill" style="width:${pct}%;background:${color}"></div></div>
  </div>`;
}

// ============================================================
// LEGEND & OVERLAYS
// ============================================================
function updateLegend() {
  const el = document.getElementById('map-legend');
  if (!el) return;
  let items = CIVS.map(c => `<div class="legend-item"><div class="legend-swatch" style="background:${c.color}"></div>${c.short}</div>`).join('');
  el.innerHTML = `<div class="legend-title">Civilizations</div>${items}`;
}

function updateOverlayChips() {
  const el = document.getElementById('map-overlays');
  if (!el) return;
  const chips = APP.mode === 'trade'
    ? ['Routes', 'Markets', 'Flow', 'Beliefs']
    : APP.mode === 'campaign'
    ? ['Armies', 'Fronts', 'Supply', 'Knowledge Fog', 'Asabiya']
    : ['Borders', 'Settlements', 'Terrain', 'Resources'];
  el.innerHTML = chips.map((c, i) => `<button class="overlay-chip${i < 2 ? ' active' : ''}">${c}</button>`).join('');
  el.querySelectorAll('.overlay-chip').forEach(chip => {
    chip.addEventListener('click', () => chip.classList.toggle('active'));
  });
}

// ============================================================
// BATCH TABLE
// ============================================================
function initBatchTable() {
  const tbody = document.getElementById('batch-table-body');
  if (!tbody) return;
  tbody.innerHTML = BATCH_RESULTS.map(r => `
    <tr data-seed="${r.seed}">
      <td>${r.rank}</td>
      <td class="seed-cell">${r.seed}</td>
      <td class="score-cell">${r.score.toFixed(2)}</td>
      <td>${r.wars}</td>
      <td>${r.collapses}</td>
      <td>${r.events}</td>
      <td>${r.tech}</td>
      <td class="${r.anomalies > 0 ? 'anomaly-cell' : ''}">${r.anomalies}</td>
      <td><button class="batch-open-btn" onclick="openBatchResult('${r.seed}')">Open</button></td>
    </tr>
  `).join('');
}

function openBatchResult(seed) {
  setState('viewer');
  setMode('overview');
}

// ============================================================
// PROGRESS ANIMATION
// ============================================================
function runProgressAnimation() {
  const fill = document.getElementById('sim-progress-fill');
  const turnEl = document.getElementById('progress-turn');
  const speedEl = document.getElementById('progress-speed');
  const logEl = document.getElementById('progress-log');
  const indSim = document.getElementById('ind-sim');
  const indNarr = document.getElementById('ind-narr');
  const indBundle = document.getElementById('ind-bundle');
  const indInterest = document.getElementById('ind-interest');

  const logLines = [
    'Generating terrain mesh…',
    'Placing civilizations…',
    'Initializing trade networks…',
    'Running simulation phases 1–10…',
    'Processing agent tick…',
    'Computing satisfaction models…',
    'Resolving military actions…',
    'Building narration queue…',
    'Generating era reflections…',
    'Computing interestingness…',
    'Bundling output…',
    'Finalizing manifest…'
  ];
  let progress = 0;
  let logIdx = 0;
  const totalDuration = APP.demoRunning ? 5000 : 6000;
  const interval = 50;
  const steps = totalDuration / interval;
  let step = 0;

  const timer = setInterval(() => {
    step++;
    progress = Math.min(100, (step / steps) * 100);
    const turn = Math.round((progress / 100) * 5000);
    fill.style.width = progress + '%';
    turnEl.textContent = `Turn ${turn.toLocaleString()} / 5,000`;
    speedEl.textContent = (10 + Math.random() * 8).toFixed(1) + ' ms/turn';

    if (progress > 20 && logIdx < 3) { addLog(logEl, logLines[logIdx++]); }
    if (progress > 40 && logIdx < 5) { addLog(logEl, logLines[logIdx++]); }
    if (progress > 60) { indSim.textContent = 'Complete'; indSim.className = 'indicator-status done'; }
    if (progress > 65 && logIdx < 8) { addLog(logEl, logLines[logIdx++]); indNarr.textContent = 'Running'; indNarr.className = 'indicator-status running'; }
    if (progress > 80) { indNarr.textContent = 'Complete'; indNarr.className = 'indicator-status done'; indInterest.textContent = '0.73'; indInterest.style.color = '#4a9ebb'; }
    if (progress > 85 && logIdx < 11) { addLog(logEl, logLines[logIdx++]); indBundle.textContent = 'Building'; indBundle.className = 'indicator-status running'; }
    if (progress > 95) { indBundle.textContent = 'Complete'; indBundle.className = 'indicator-status done'; }

    if (progress >= 100) {
      clearInterval(timer);
      while (logIdx < logLines.length) addLog(logEl, logLines[logIdx++]);
      addLog(logEl, 'World ready. Opening viewer…', true);
      setTimeout(() => { setState('viewer'); setMode('overview'); }, 800);
    }
  }, interval);
}

function addLog(el, text, highlight) {
  const line = document.createElement('div');
  line.className = 'log-line' + (highlight ? ' highlight' : '');
  line.textContent = text;
  el.appendChild(line);
  el.scrollTop = el.scrollHeight;
}

// ============================================================
// TRADE ANIMATION LOOP
// ============================================================
function startTradeAnim() {
  if (APP.tradeAnimId) return;
  function tick() {
    APP.tradeAnimOffset = (APP.tradeAnimOffset + 0.8) % 1000;
    if (APP.mode === 'trade' && APP.state === 'viewer') renderMap();
    APP.tradeAnimId = requestAnimationFrame(tick);
  }
  tick();
}

// Start trade anim on load
setTimeout(startTradeAnim, 100);

// ============================================================
// DEMO AUTOMATION
// ============================================================
const DEMO_SCRIPT = [
  { delay:0, fn:() => setState('setup') },
  { delay:2000, fn:() => {
    document.getElementById('input-turns').value = 5000;
    document.getElementById('val-turns').textContent = '5,000';
  }},
  { delay:1500, fn:() => {
    // Animate slider
    const sl = document.getElementById('input-civs');
    sl.value = 5; document.getElementById('val-civs').textContent = '5';
  }},
  { delay:1500, fn:() => {
    document.getElementById('btn-run-world').click();
  }},
  { delay:6500, fn:() => {} }, // Wait for progress to finish
  { delay:2000, fn:() => {
    // Hover a region
    APP.hoveredRegion = 4; // Thornwall March
    renderMap();
  }},
  { delay:2000, fn:() => {
    APP.selectedCiv = 0;
    updateInspector();
    APP.hoveredRegion = -1;
    renderMap();
  }},
  { delay:2000, fn:() => scrubTimeline(2800) },
  { delay:1500, fn:() => scrubTimeline(3812) },
  { delay:2000, fn:() => setMode('character') },
  { delay:3500, fn:() => setMode('trade') },
  { delay:3500, fn:() => setMode('campaign') },
  { delay:3500, fn:() => {
    setState('batch');
    setTimeout(() => {
      const row = document.querySelector('#batch-table-body tr:first-child');
      if (row) row.classList.add('highlighted');
    }, 500);
  }},
  { delay:3000, fn:() => {
    openBatchResult('4ASF-9B1D-7C6E');
  }},
  { delay:2500, fn:() => {
    pauseDemo();
  }}
];

function startDemo() {
  APP.demoRunning = true;
  APP.demoStep = 0;
  document.getElementById('btn-auto-demo').style.display = 'none';
  document.getElementById('btn-pause-demo').style.display = 'inline-block';
  runDemoStep();
}

function runDemoStep() {
  if (!APP.demoRunning || APP.demoStep >= DEMO_SCRIPT.length) {
    pauseDemo();
    return;
  }
  const step = DEMO_SCRIPT[APP.demoStep];
  APP.demoTimeout = setTimeout(() => {
    step.fn();
    APP.demoStep++;
    runDemoStep();
  }, step.delay);
}

function pauseDemo() {
  APP.demoRunning = false;
  if (APP.demoTimeout) clearTimeout(APP.demoTimeout);
  document.getElementById('btn-auto-demo').style.display = 'inline-block';
  document.getElementById('btn-pause-demo').style.display = 'none';
}

function jumpTo(target) {
  pauseDemo();
  switch (target) {
    case 'setup': setState('setup'); break;
    case 'progress': setState('progress'); runProgressAnimation(); break;
    case 'overview': setState('viewer'); setMode('overview'); break;
    case 'character': setState('viewer'); setMode('character'); break;
    case 'trade': setState('viewer'); setMode('trade'); break;
    case 'campaign': setState('viewer'); setMode('campaign'); break;
    case 'batch': setState('batch'); break;
  }
}
