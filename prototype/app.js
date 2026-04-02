/* ============================================================
   Chronicler 7.5 Viewer Prototype — Application Logic
   ============================================================ */

// ============ FAKE DATA ============
const REGIONS = [
  { name: 'Thornwall',     cx: 320, cy: 180, r: 55, owner: 0 },
  { name: 'Eastmarch',     cx: 480, cy: 150, r: 48, owner: 0 },
  { name: 'Greymoor',      cx: 200, cy: 260, r: 50, owner: 1 },
  { name: 'Valkenreach',   cx: 560, cy: 260, r: 52, owner: 2 },
  { name: 'Ashfold',       cx: 380, cy: 310, r: 45, owner: 3 },
  { name: 'Duskhollow',    cx: 140, cy: 140, r: 42, owner: 1 },
  { name: 'Sunhaven',      cx: 650, cy: 180, r: 40, owner: 4 },
  { name: 'Ironmere',      cx: 270, cy: 400, r: 50, owner: 5 },
  { name: 'Keldrath',      cx: 500, cy: 400, r: 55, owner: 3 },
  { name: 'Stormveil',     cx: 420, cy: 470, r: 48, owner: 6 },
  { name: 'Brightwater',   cx: 600, cy: 360, r: 42, owner: 4 },
  { name: 'Fellmark',      cx: 160, cy: 380, r: 38, owner: 5 },
  { name: 'Wyrmrest',      cx: 700, cy: 450, r: 45, owner: 7 },
  { name: 'Oldgate',       cx: 340, cy: 100, r: 40, owner: 0 },
  { name: 'Mistholm',      cx: 520, cy: 520, r: 44, owner: 6 },
];

const SETTLEMENTS = [
  { name: 'Thornwall',       x: 320, y: 180, size: 5 },
  { name: 'Greymoor Keep',   x: 200, y: 260, size: 4 },
  { name: 'Valkenrath',      x: 560, y: 260, size: 4 },
  { name: 'Ashfold',         x: 380, y: 310, size: 3 },
  { name: 'Ironmere',        x: 270, y: 400, size: 3 },
  { name: 'Keldrath',        x: 500, y: 400, size: 4 },
  { name: 'Stormveil',       x: 420, y: 470, size: 3 },
  { name: 'Eastmarch',       x: 480, y: 150, size: 3 },
  { name: 'Sunhaven',        x: 650, y: 180, size: 3 },
  { name: 'Brightwater',     x: 600, y: 360, size: 2 },
  { name: 'Duskhollow',      x: 140, y: 140, size: 2 },
  { name: 'Wyrmrest',        x: 700, y: 450, size: 3 },
  { name: 'Oldgate',         x: 340, y: 100, size: 2 },
];

const CIV_COLORS = [
  '#5ba4b5', '#b8976a', '#8a6ab8', '#5aaa6a',
  '#c49b4a', '#b05555', '#6a8ab8', '#aa7a5a'
];

const TRADE_ROUTES = [
  { from: [320,180], to: [480,150], label: 'Thornwall-Eastmarch' },
  { from: [480,150], to: [650,180], label: 'Eastmarch-Sunhaven' },
  { from: [320,180], to: [380,310], label: 'Thornwall-Ashfold' },
  { from: [200,260], to: [270,400], label: 'Greymoor-Ironmere' },
  { from: [560,260], to: [600,360], label: 'Valkenreach-Brightwater' },
  { from: [500,400], to: [420,470], label: 'Keldrath-Stormveil' },
  { from: [380,310], to: [500,400], label: 'Ashfold-Keldrath' },
  { from: [600,360], to: [700,450], label: 'Brightwater-Wyrmrest' },
];

const CAMPAIGN_PATHS = [
  { from: [320,180], to: [200,260], label: 'II Legion', army: 'Thornwall II' },
  { from: [480,150], to: [560,260], label: 'Eastern Host', army: 'Eastern Vanguard' },
  { from: [500,400], to: [420,470], label: 'Keldrath Militia', army: 'Militia' },
];

const BATTLE_SITES = [
  { x: 260, y: 220, label: 'Battle of Grey Ford' },
  { x: 520, y: 200, label: 'Siege of Valkenrath' },
  { x: 460, y: 440, label: 'Stormveil Skirmish' },
];

const CHRONICLES = [
  { era: 'Late Decay', title: 'The Collapse of the Aetherian Compact', body: 'When the last imperial governor abandoned Oldgate, three successor states claimed legitimacy over the northern provinces. The compact, held together by trade and shared faith for six centuries, fractured irreversibly.', turn: 3780 },
  { era: 'Late Decay', title: 'Eadric\'s March on Greymoor', body: 'With supply lines severed and the Thornwall garrison depleted, Eadric led the remnant II Legion through the Fellmark passes — a gamble that would either restore order or accelerate collapse.', turn: 3805 },
  { era: 'Late Decay', title: 'The Schism Deepens', body: 'Clergy in the eastern provinces formally rejected the Thornwall Articles, splitting the dominant faith into two irreconcilable branches. Pilgrim routes collapsed within a season.', turn: 3812 },
  { era: 'Fragmentation', title: 'Loss of the Southern Granaries', body: 'Stormveil\'s fertile lowlands changed hands for the third time in a decade. Each transition stripped more infrastructure, and the region\'s food surplus — once the empire\'s insurance against famine — dwindled.', turn: 3740 },
  { era: 'Fragmentation', title: 'Nomadic Confederation Forms', body: 'The horse peoples of the eastern steppe united under a single khan for the first time in living memory. Their raids on Sunhaven and Brightwater were no longer opportunistic but strategic.', turn: 3695 },
];

const EVENT_LOG = [
  { turn: 3812, type: 'religion', text: 'Eastern Schism declared — Sunhaven clergy reject Thornwall Articles' },
  { turn: 3810, type: 'war', text: 'II Legion departs Thornwall — 2,400 troops, 18 days supply' },
  { turn: 3808, type: 'economy', text: 'Thornwall-Ashfold trade route disrupted — banditry severity 0.72' },
  { turn: 3805, type: 'culture', text: 'Eadric promoted to Great Person (GP-00481) — military/cultural hybrid' },
  { turn: 3802, type: 'diplomacy', text: 'Greymoor-Ironmere mutual defense pact signed' },
  { turn: 3798, type: 'war', text: 'Keldrath militia engages Stormveil garrison — inconclusive' },
  { turn: 3795, type: 'economy', text: 'Ironmere iron exports reach 10-year high' },
  { turn: 3790, type: 'religion', text: 'Pilgrim route Thornwall-Sunhaven suspended' },
  { turn: 3785, type: 'culture', text: 'Valkenreach scholars preserve imperial archives' },
  { turn: 3780, type: 'war', text: 'Imperial Compact formally dissolved' },
  { turn: 3775, type: 'diplomacy', text: 'Eastmarch declares neutrality' },
  { turn: 3770, type: 'economy', text: 'Keldrath market prices surge — grain +40%' },
];

const BATCH_SEEDS = [
  { seed: '4ASF-9B1D-7C6E', score: 0.73, wars: 14, collapses: 3, named: 47, tech: '+2.1', anomalies: 2 },
  { seed: '7BCD-4E2F-1A9D', score: 0.71, wars: 11, collapses: 4, named: 42, tech: '+1.8', anomalies: 1 },
  { seed: '9F1A-3C8B-6D2E', score: 0.68, wars: 16, collapses: 2, named: 38, tech: '+2.4', anomalies: 3 },
  { seed: '2E5D-8A1F-4B7C', score: 0.65, wars: 9, collapses: 5, named: 35, tech: '+1.5', anomalies: 1 },
  { seed: '5C3A-1D9E-8F2B', score: 0.62, wars: 12, collapses: 2, named: 31, tech: '+1.9', anomalies: 0 },
  { seed: '8D2B-6F4A-3E1C', score: 0.59, wars: 8, collapses: 3, named: 28, tech: '+1.2', anomalies: 2 },
  { seed: '1A9C-5E3D-7B8F', score: 0.57, wars: 13, collapses: 1, named: 33, tech: '+2.0', anomalies: 1 },
  { seed: '6F8E-2B1A-9D4C', score: 0.54, wars: 7, collapses: 4, named: 25, tech: '+1.1', anomalies: 0 },
  { seed: '3B7D-9C5F-1A2E', score: 0.51, wars: 10, collapses: 2, named: 22, tech: '+1.6', anomalies: 1 },
  { seed: '4D1F-8A6B-2C9E', score: 0.48, wars: 6, collapses: 3, named: 19, tech: '+0.9', anomalies: 0 },
];

// ============ STATE ============
let currentScreen = 'setup';
let currentMode = 'overview';
let demoRunning = false;
let demoTimeout = null;

// ============ INIT ============
document.addEventListener('DOMContentLoaded', () => {
  generateSetupMap();
  generateMainMap();
  populateChronicle();
  populateEventLog();
  populateBatchTable();
  setupInspector('overview');
  bindEvents();
});

// ============ MAP GENERATION ============
function generateSetupMap() {
  const svg = document.getElementById('setup-svg');
  let html = '';
  // Topographic contours
  for (let i = 0; i < 8; i++) {
    const cx = 80 + Math.random() * 240;
    const cy = 60 + Math.random() * 180;
    const rx = 40 + Math.random() * 60;
    const ry = 30 + Math.random() * 50;
    html += `<ellipse cx="${cx}" cy="${cy}" rx="${rx}" ry="${ry}" class="topo-contour"/>`;
  }
  // Regions
  REGIONS.forEach((r, i) => {
    const sx = r.cx * 0.5, sy = r.cy * 0.5, sr = r.r * 0.45;
    html += generateVoronoiRegion(sx, sy, sr, CIV_COLORS[r.owner % 8], 0.08);
  });
  // Settlements
  SETTLEMENTS.forEach(s => {
    const sx = s.x * 0.5, sy = s.y * 0.5;
    html += `<circle cx="${sx}" cy="${sy}" r="${s.size * 0.6}" class="settlement-dot"/>`;
    html += `<text x="${sx + 6}" y="${sy + 3}" class="settlement-label">${s.name}</text>`;
  });
  svg.innerHTML = html;
}

function generateMainMap() {
  const svg = document.getElementById('main-map');
  let html = '';

  // Defs
  html += `<defs>
    <marker id="arrowhead" markerWidth="8" markerHeight="6" refX="8" refY="3" orient="auto">
      <polygon points="0 0, 8 3, 0 6" fill="#b05555"/>
    </marker>
    <filter id="glow"><feGaussianBlur stdDeviation="2" result="blur"/>
      <feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge>
    </filter>
  </defs>`;

  // Grid
  for (let x = 0; x <= 800; x += 40) {
    html += `<line x1="${x}" y1="0" x2="${x}" y2="600" stroke="rgba(180,170,140,0.04)" stroke-width="0.5"/>`;
  }
  for (let y = 0; y <= 600; y += 40) {
    html += `<line x1="0" y1="${y}" x2="800" y2="${y}" stroke="rgba(180,170,140,0.04)" stroke-width="0.5"/>`;
  }

  // Topographic contours
  for (let i = 0; i < 15; i++) {
    const cx = 50 + Math.random() * 700;
    const cy = 50 + Math.random() * 500;
    const rx = 50 + Math.random() * 100;
    const ry = 40 + Math.random() * 80;
    html += `<ellipse cx="${cx}" cy="${cy}" rx="${rx}" ry="${ry}" class="topo-contour"/>`;
  }

  // Region polygons (irregular)
  REGIONS.forEach((r, i) => {
    html += generateVoronoiRegion(r.cx, r.cy, r.r, CIV_COLORS[r.owner % 8], 0.1, `region-${i}`);
  });

  // Borders (as thicker strokes between owned regions)
  const borderPairs = [
    [0,1],[0,3],[0,4],[1,6],[2,5],[2,7],[3,4],[3,8],[4,9],[6,10],[8,9],[8,10],[9,14],[10,12],[7,11]
  ];
  html += `<g class="borders-group">`;
  borderPairs.forEach(([a,b]) => {
    const ra = REGIONS[a], rb = REGIONS[b];
    if (ra.owner !== rb.owner) {
      const mx = (ra.cx + rb.cx)/2, my = (ra.cy + rb.cy)/2;
      const dx = rb.cx - ra.cx, dy = rb.cy - ra.cy;
      const len = Math.sqrt(dx*dx + dy*dy);
      const nx = -dy/len * 20, ny = dx/len * 20;
      html += `<line x1="${mx-nx}" y1="${my-ny}" x2="${mx+nx}" y2="${my+ny}"
        stroke="rgba(184,151,106,0.25)" stroke-width="1.5" stroke-dasharray="4 2"/>`;
    }
  });
  html += `</g>`;

  // Trade routes (hidden by default, shown in trade mode)
  html += `<g class="trade-routes-group" style="display:none">`;
  TRADE_ROUTES.forEach((route, i) => {
    const [x1,y1] = route.from, [x2,y2] = route.to;
    const mx = (x1+x2)/2, my = (y1+y2)/2 - 20;
    html += `<path d="M${x1},${y1} Q${mx},${my} ${x2},${y2}" class="trade-route-glow" data-route="${i}"/>`;
    html += `<path d="M${x1},${y1} Q${mx},${my} ${x2},${y2}" class="trade-route" data-route="${i}"/>`;
  });
  html += `</g>`;

  // Campaign paths (hidden by default)
  html += `<g class="campaign-group" style="display:none">`;
  CAMPAIGN_PATHS.forEach((path, i) => {
    const [x1,y1] = path.from, [x2,y2] = path.to;
    const mx = (x1+x2)/2 + 15, my = (y1+y2)/2 - 15;
    html += `<path d="M${x1},${y1} Q${mx},${my} ${x2},${y2}" class="campaign-path" data-campaign="${i}"/>`;
    // Army chip
    const chipX = (x1+x2)/2, chipY = (y1+y2)/2 - 8;
    html += `<rect x="${chipX-25}" y="${chipY-7}" width="50" height="14" class="army-chip-bg"/>`;
    html += `<text x="${chipX}" y="${chipY+3}" text-anchor="middle" class="army-chip">${path.army}</text>`;
  });
  // Supply lines
  html += `<line x1="320" y1="180" x2="340" y2="100" class="supply-line"/>`;
  html += `<line x1="480" y1="150" x2="520" y2="80" class="supply-line"/>`;
  // Battle markers
  BATTLE_SITES.forEach(b => {
    html += `<polygon points="${b.x},${b.y-6} ${b.x+5},${b.y+4} ${b.x-5},${b.y+4}" class="battle-marker"/>`;
  });
  html += `</g>`;

  // Settlements
  SETTLEMENTS.forEach(s => {
    html += `<circle cx="${s.x}" cy="${s.y}" r="${s.size}" class="settlement-dot"
      data-settlement="${s.name}"/>`;
    html += `<text x="${s.x + s.size + 4}" y="${s.y + 3}" class="settlement-label">${s.name}</text>`;
  });

  svg.innerHTML = html;

  // Hover events
  svg.querySelectorAll('.settlement-dot').forEach(dot => {
    dot.addEventListener('mouseenter', (e) => {
      const name = dot.dataset.settlement;
      showHoverCard(e.clientX, e.clientY, name, 'Pop: ' + (1200 + Math.floor(Math.random() * 5000)));
    });
    dot.addEventListener('mouseleave', hideHoverCard);
  });
}

function generateVoronoiRegion(cx, cy, r, color, opacity, id = '') {
  // Generate irregular polygon
  const points = [];
  const n = 8 + Math.floor(Math.random() * 4);
  for (let i = 0; i < n; i++) {
    const angle = (i / n) * Math.PI * 2;
    const variation = 0.7 + Math.random() * 0.6;
    const px = cx + Math.cos(angle) * r * variation;
    const py = cy + Math.sin(angle) * r * variation;
    points.push(`${px},${py}`);
  }
  return `<polygon points="${points.join(' ')}" class="region-path"
    ${id ? `data-region="${id}"` : ''}
    style="fill:${color};fill-opacity:${opacity}"/>`;
}

// ============ POPULATE LEFT RAIL ============
function populateChronicle() {
  const container = document.getElementById('rail-chronicle');
  container.innerHTML = CHRONICLES.map((c, i) => `
    <div class="chronicle-entry${i === 2 ? ' active' : ''}" data-index="${i}">
      <div class="chronicle-era">${c.era}</div>
      <div class="chronicle-title">${c.title}</div>
      <div class="chronicle-body">${c.body}</div>
      <div class="chronicle-turn">Turn ${c.turn}</div>
    </div>
  `).join('');
}

function populateEventLog() {
  const container = document.getElementById('rail-events');
  container.innerHTML = EVENT_LOG.map(e => `
    <div class="event-entry ${e.type}">
      <span class="event-turn">${e.turn}</span>
      <span class="event-text">${e.text}</span>
    </div>
  `).join('');
}

// ============ POPULATE BATCH TABLE ============
function populateBatchTable() {
  const tbody = document.getElementById('batch-tbody');
  tbody.innerHTML = BATCH_SEEDS.map((s, i) => `
    <tr class="${i === 0 ? 'highlight' : ''}">
      <td class="rank-col">${i + 1}</td>
      <td class="seed-col">${s.seed}</td>
      <td class="score-col">${s.score.toFixed(2)}</td>
      <td>${s.wars}</td>
      <td>${s.collapses}</td>
      <td>${s.named}</td>
      <td>${s.tech}</td>
      <td>${s.anomalies}</td>
      <td><button class="open-btn" data-seed="${s.seed}">Open</button></td>
    </tr>
  `).join('');
}

// ============ RIGHT INSPECTOR CONTENT ============
function setupInspector(mode) {
  const container = document.getElementById('inspector-content');
  container.style.opacity = '0';

  setTimeout(() => {
    switch (mode) {
      case 'overview': container.innerHTML = getOverviewInspector(); break;
      case 'character': container.innerHTML = getCharacterInspector(); break;
      case 'trade': container.innerHTML = getTradeInspector(); break;
      case 'campaign': container.innerHTML = getCampaignInspector(); break;
      default: container.innerHTML = getOverviewInspector();
    }
    container.style.opacity = '1';
    container.style.transition = 'opacity 0.3s ease';
  }, 150);
}

function getOverviewInspector() {
  return `
    <div class="insp-header">
      <div class="insp-civ-name" style="color:${CIV_COLORS[0]}">Thornwall Confederacy</div>
      <div class="insp-civ-sub">4 regions &middot; 14,200 pop &middot; Era: Late Decay</div>
    </div>
    <div class="insp-section">
      <div class="insp-section-title">Demographics</div>
      <div class="insp-row"><span class="insp-label">Population</span><span class="insp-value">14,218</span></div>
      <div class="insp-row"><span class="insp-label">Growth</span><span class="insp-value warn">-0.3%</span></div>
      <div class="insp-row"><span class="insp-label">Agents</span><span class="insp-value">2,847</span></div>
      <div class="insp-row"><span class="insp-label">Great Persons</span><span class="insp-value">3</span></div>
    </div>
    <div class="insp-section">
      <div class="insp-section-title">Faction Influence</div>
      ${factionBar('Military', 42, 'red')}
      ${factionBar('Merchant', 28, 'amber')}
      ${factionBar('Cultural', 18, 'purple')}
      ${factionBar('Clergy', 12, 'green')}
    </div>
    <div class="insp-section">
      <div class="insp-section-title">Faith Composition</div>
      ${factionBar('Aetherian Orthodox', 62, 'cyan')}
      ${factionBar('Eastern Reform', 24, 'brass')}
      ${factionBar('Old Ways', 14, 'amber')}
    </div>
    <div class="insp-section">
      <div class="insp-section-title">Economy</div>
      <div class="insp-row"><span class="insp-label">Treasury</span><span class="insp-value">2,847 g</span></div>
      <div class="insp-row"><span class="insp-label">Income</span><span class="insp-value good">+124 g/t</span></div>
      <div class="insp-row"><span class="insp-label">Trade Dep.</span><span class="insp-value warn">0.38</span></div>
      <div class="insp-row"><span class="insp-label">Gini</span><span class="insp-value warn">0.42</span></div>
      <div class="insp-row"><span class="insp-label">Class Tension</span><span class="insp-value warn">-0.12</span></div>
    </div>
    <div class="insp-section">
      <div class="insp-section-title">Stability</div>
      <div class="insp-row"><span class="insp-label">Asabiya</span><span class="insp-value warn">0.41</span></div>
      <div class="insp-row"><span class="insp-label">Prestige</span><span class="insp-value">0.58</span></div>
      <div class="insp-row"><span class="insp-label">Satisfaction</span><span class="insp-value warn">0.52</span></div>
      <div class="insp-row"><span class="insp-label">Food Suff.</span><span class="insp-value good">0.91</span></div>
    </div>
    <div class="insp-section">
      <div class="insp-section-title">Dynastic Succession</div>
      <div class="dynasty-strip">
        <div class="dynasty-chip extinct">Aelric I</div>
        <div class="dynasty-chip extinct">Aelric II</div>
        <div class="dynasty-chip">Brynhild</div>
        <div class="dynasty-chip active">Eadric</div>
      </div>
    </div>
  `;
}

function getCharacterInspector() {
  return `
    <div class="insp-header">
      <div class="insp-civ-name" style="color:${CIV_COLORS[0]}">Eadric of Thornwall</div>
      <div class="insp-civ-sub">
        GP-00481 &middot; Military Commander &middot; Age 34
        <br><span style="color:var(--text-tertiary)">Stable ID: GP-00481 &middot; Agent #4812</span>
      </div>
    </div>
    <div class="insp-section">
      <div class="insp-section-title">Needs Radar</div>
      <div class="radar-container">
        <canvas id="radar-canvas" width="140" height="140"></canvas>
      </div>
      <div style="text-align:center;font-size:10px;color:var(--text-tertiary)">
        Security &middot; Wealth &middot; Faith &middot; Culture &middot; Social &middot; Power
      </div>
    </div>
    <div class="insp-section">
      <div class="insp-section-title">Active Decision Pressures</div>
      <div class="insp-row"><span class="insp-label">Primary</span><span class="insp-value bad">March on Greymoor</span></div>
      <div class="insp-row"><span class="insp-label">Secondary</span><span class="insp-value warn">Secure supply line</span></div>
      <div class="insp-row"><span class="insp-label">Utility</span><span class="insp-value">0.74 (WAR)</span></div>
      <div class="insp-row"><span class="insp-label">Confidence</span><span class="insp-value warn">0.61</span></div>
    </div>
    <div class="insp-section">
      <div class="insp-section-title">Mule Status</div>
      <div class="mule-badge">MULE &middot; 4 turns remaining</div>
      <div style="font-size:11px;color:var(--text-secondary);margin-top:6px">
        Warped by: <span style="color:var(--brass)">Imperial Collapse (T3780)</span>
        <br>Effect: +0.3 military utility, -0.2 diplomacy weight
      </div>
    </div>
    <div class="insp-section">
      <div class="insp-section-title">Memory Timeline</div>
      <div class="memory-timeline">
        <div class="memory-node legacy">
          <div class="mem-turn">T3780</div>
          <div class="mem-text">Witnessed Imperial Collapse at Oldgate</div>
        </div>
        <div class="memory-node intense">
          <div class="mem-turn">T3795</div>
          <div class="mem-text">Promoted to Legion Commander after Fellmark defense</div>
        </div>
        <div class="memory-node">
          <div class="mem-turn">T3802</div>
          <div class="mem-text">Greymoor pact perceived as betrayal of Thornwall interests</div>
        </div>
        <div class="memory-node intense">
          <div class="mem-turn">T3805</div>
          <div class="mem-text">Great Person promotion — cultural/military hybrid</div>
        </div>
        <div class="memory-node">
          <div class="mem-turn">T3810</div>
          <div class="mem-text">Ordered march on Greymoor — supply risk acknowledged</div>
        </div>
      </div>
    </div>
    <div class="insp-section">
      <div class="insp-section-title">Relationships</div>
      <div class="insp-row"><span class="insp-label">Brynhild (mentor)</span><span class="insp-value good">+0.72</span></div>
      <div class="insp-row"><span class="insp-label">Aldric of Greymoor</span><span class="insp-value bad">-0.45</span></div>
      <div class="insp-row"><span class="insp-label">Seren (spouse)</span><span class="insp-value good">+0.81</span></div>
    </div>
    <div class="insp-section">
      <div class="insp-section-title">Dynastic Lineage</div>
      <div class="dynasty-strip">
        <div class="dynasty-chip extinct">Aelric I</div>
        <div class="dynasty-chip">Brynhild</div>
        <div class="dynasty-chip active">Eadric</div>
      </div>
    </div>
    <div class="insp-section">
      <div class="insp-section-title">Movement</div>
      <div class="insp-row"><span class="insp-label">Current</span><span class="insp-value">Fellmark Pass</span></div>
      <div class="insp-row"><span class="insp-label">Heading</span><span class="insp-value">Greymoor Keep</span></div>
      <div class="insp-row"><span class="insp-label">ETA</span><span class="insp-value warn">~8 turns</span></div>
    </div>
  `;
}

function getTradeInspector() {
  return `
    <div class="insp-header">
      <div class="insp-civ-name" style="color:var(--gold)">Trade Diagnostics</div>
      <div class="insp-civ-sub">8 active routes &middot; 4 market hubs</div>
    </div>
    <div class="insp-section">
      <div class="insp-section-title">Route Inspection</div>
      <div class="trade-route-card">
        <div class="route-header">
          <span class="route-name">Thornwall &rarr; Eastmarch</span>
          <span class="route-profit" style="color:var(--green)">+42 g/t</span>
        </div>
        <div class="insp-row"><span class="insp-label">Margin</span><span class="insp-value good">18.4%</span></div>
        <div class="insp-row"><span class="insp-label">In-Transit</span><span class="insp-value">Iron (24u), Grain (60u)</span></div>
        <div class="insp-row"><span class="insp-label">Freshness</span><span class="insp-value good">Current</span></div>
        <div class="insp-row"><span class="insp-label">Confidence</span><span class="insp-value">0.84</span></div>
      </div>
      <div class="trade-route-card">
        <div class="route-header">
          <span class="route-name">Thornwall &rarr; Ashfold</span>
          <span class="route-profit" style="color:var(--red)">-8 g/t</span>
        </div>
        <div class="insp-row"><span class="insp-label">Margin</span><span class="insp-value bad">-3.2%</span></div>
        <div class="insp-row"><span class="insp-label">Status</span><span class="insp-value bad">Disrupted</span></div>
        <div class="insp-row"><span class="insp-label">Stale Belief</span><span class="insp-value warn">Iron @ 4.2 (actual: 6.8)</span></div>
        <div class="insp-row"><span class="insp-label">Freshness</span><span class="insp-value bad">Stale (12 turns)</span></div>
      </div>
    </div>
    <div class="insp-section">
      <div class="insp-section-title">Market — Thornwall</div>
      <div class="insp-row"><span class="insp-label">Role</span><span class="insp-value">Hub</span></div>
      <div class="insp-row"><span class="insp-label">Supply Score</span><span class="insp-value good">0.88</span></div>
      <div class="insp-row"><span class="insp-label">Demand Score</span><span class="insp-value">0.72</span></div>
      ${factionBar('Food Suff.', 91, 'green')}
      ${factionBar('Import Share', 38, 'amber')}
      ${factionBar('Trade Dep.', 42, 'cyan')}
    </div>
    <div class="insp-section">
      <div class="insp-section-title">Stockpile Trends</div>
      ${factionBar('Grain', 68, 'green')}
      ${factionBar('Iron', 45, 'brass')}
      ${factionBar('Salt', 72, 'amber')}
      ${factionBar('Timber', 54, 'green')}
    </div>
    <div class="insp-section">
      <div class="insp-section-title">Merchant Intelligence</div>
      <div class="insp-row"><span class="insp-label">Active Merchants</span><span class="insp-value">148</span></div>
      <div class="insp-row"><span class="insp-label">Avg. Plan Horizon</span><span class="insp-value">6.2 turns</span></div>
      <div class="insp-row"><span class="insp-label">Belief Staleness</span><span class="insp-value warn">22%</span></div>
      <div class="insp-row"><span class="insp-label">Merchant Margin</span><span class="insp-value good">0.14</span></div>
    </div>
  `;
}

function getCampaignInspector() {
  return `
    <div class="insp-header">
      <div class="insp-civ-name" style="color:var(--red)">II Legion — Greymoor Campaign</div>
      <div class="insp-civ-sub">Thornwall Confederacy &middot; Active</div>
    </div>
    <div class="insp-section">
      <div class="insp-section-title">Army Composition</div>
      <div class="army-card">
        <div class="army-name">II Legion</div>
        <div class="army-sub">Commander: Eadric of Thornwall (GP-00481)</div>
      </div>
      <div class="insp-row"><span class="insp-label">Strength</span><span class="insp-value">2,400</span></div>
      <div class="insp-row"><span class="insp-label">Morale</span><span class="insp-value warn">0.64</span></div>
      <div class="insp-row"><span class="insp-label">Supply</span><span class="insp-value bad">12 turns</span></div>
      <div class="insp-row"><span class="insp-label">Asabiya</span><span class="insp-value warn">0.41</span></div>
    </div>
    <div class="insp-section">
      <div class="insp-section-title">Target Rationale</div>
      <div style="font-size:11px;color:var(--text-secondary);line-height:1.5">
        Greymoor Keep controls the western passes and the Ironmere supply corridor. Capture would sever the Greymoor-Ironmere mutual defense pact and restore Thornwall access to iron.
      </div>
    </div>
    <div class="insp-section">
      <div class="insp-section-title">Battle Outcomes</div>
      <div class="insp-row"><span class="insp-label">Grey Ford</span><span class="insp-value good">Victory (T3798)</span></div>
      <div class="insp-row"><span class="insp-label">Casualties</span><span class="insp-value warn">340 / 2,740</span></div>
      <div class="insp-row"><span class="insp-label">Occupied</span><span class="insp-value">Fellmark (partial)</span></div>
    </div>
    <div class="insp-section">
      <div class="insp-section-title">March Timeline</div>
      <div class="memory-timeline">
        <div class="memory-node">
          <div class="mem-turn">T3810</div>
          <div class="mem-text">Departed Thornwall &mdash; 2,400 troops</div>
        </div>
        <div class="memory-node intense">
          <div class="mem-turn">T3812</div>
          <div class="mem-text">Entering Fellmark Pass &mdash; supply risk elevated</div>
        </div>
        <div class="memory-node" style="opacity:0.4">
          <div class="mem-turn">T3820?</div>
          <div class="mem-text">Projected arrival at Greymoor Keep</div>
        </div>
      </div>
    </div>
    <div class="insp-section">
      <div class="insp-section-title">Knowledge Diagnostics</div>
      <div class="insp-row"><span class="insp-label">Freshness</span><span class="insp-value warn">Partial</span></div>
      <div class="insp-row"><span class="insp-label">Staleness</span><span class="insp-value warn">3 regions</span></div>
      <div class="insp-row"><span class="insp-label">Confidence</span><span class="insp-value">0.58</span></div>
      <div class="insp-row"><span class="insp-label">Familiarity</span><span class="insp-value warn">Low (first campaign)</span></div>
    </div>
  `;
}

function factionBar(name, pct, color) {
  return `
    <div class="insp-bar-row">
      <div class="insp-bar-label"><span>${name}</span><span>${pct}%</span></div>
      <div class="insp-bar-track"><div class="insp-bar-fill ${color}" style="width:${pct}%"></div></div>
    </div>
  `;
}

// ============ HOVER CARD ============
function showHoverCard(x, y, title, body) {
  const card = document.getElementById('hover-card');
  card.querySelector('.hover-title').textContent = title;
  card.querySelector('.hover-body').textContent = body;
  card.classList.remove('hidden');
  // Position relative to map viewport
  const viewport = document.getElementById('map-viewport');
  const rect = viewport.getBoundingClientRect();
  card.style.left = (x - rect.left + 12) + 'px';
  card.style.top = (y - rect.top - 10) + 'px';
}

function hideHoverCard() {
  document.getElementById('hover-card').classList.add('hidden');
}

// ============ RADAR CHART (Character mode) ============
function drawRadar() {
  const canvas = document.getElementById('radar-canvas');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  const cx = 70, cy = 70, r = 55;
  const values = [0.8, 0.45, 0.3, 0.55, 0.65, 0.9]; // security, wealth, faith, culture, social, power
  const n = 6;

  ctx.clearRect(0, 0, 140, 140);

  // Grid rings
  for (let ring = 1; ring <= 4; ring++) {
    ctx.beginPath();
    for (let i = 0; i <= n; i++) {
      const angle = (i / n) * Math.PI * 2 - Math.PI / 2;
      const px = cx + Math.cos(angle) * r * ring / 4;
      const py = cy + Math.sin(angle) * r * ring / 4;
      if (i === 0) ctx.moveTo(px, py);
      else ctx.lineTo(px, py);
    }
    ctx.strokeStyle = 'rgba(180,170,140,0.12)';
    ctx.lineWidth = 0.5;
    ctx.stroke();
  }

  // Axes
  for (let i = 0; i < n; i++) {
    const angle = (i / n) * Math.PI * 2 - Math.PI / 2;
    ctx.beginPath();
    ctx.moveTo(cx, cy);
    ctx.lineTo(cx + Math.cos(angle) * r, cy + Math.sin(angle) * r);
    ctx.strokeStyle = 'rgba(180,170,140,0.1)';
    ctx.lineWidth = 0.5;
    ctx.stroke();
  }

  // Data polygon
  ctx.beginPath();
  for (let i = 0; i <= n; i++) {
    const idx = i % n;
    const angle = (idx / n) * Math.PI * 2 - Math.PI / 2;
    const px = cx + Math.cos(angle) * r * values[idx];
    const py = cy + Math.sin(angle) * r * values[idx];
    if (i === 0) ctx.moveTo(px, py);
    else ctx.lineTo(px, py);
  }
  ctx.fillStyle = 'rgba(91,164,181,0.15)';
  ctx.fill();
  ctx.strokeStyle = 'rgba(91,164,181,0.6)';
  ctx.lineWidth = 1.5;
  ctx.stroke();

  // Data points
  for (let i = 0; i < n; i++) {
    const angle = (i / n) * Math.PI * 2 - Math.PI / 2;
    const px = cx + Math.cos(angle) * r * values[i];
    const py = cy + Math.sin(angle) * r * values[i];
    ctx.beginPath();
    ctx.arc(px, py, 2.5, 0, Math.PI * 2);
    ctx.fillStyle = '#5ba4b5';
    ctx.fill();
  }
}

// ============ SCREEN TRANSITIONS ============
function switchScreen(name) {
  document.querySelectorAll('.screen').forEach(s => s.classList.remove('active'));
  const target = document.getElementById('screen-' + name);
  if (target) {
    target.classList.add('active');
    currentScreen = name;
  }
}

function switchMode(mode) {
  currentMode = mode;

  // Update tab state
  document.querySelectorAll('.mode-tab').forEach(t => {
    t.classList.toggle('active', t.dataset.mode === mode);
  });

  // Validation ribbon
  const ribbon = document.getElementById('validation-ribbon');
  ribbon.classList.toggle('hidden', mode !== 'campaign');

  // Batch overlay
  const batch = document.getElementById('batch-overlay');
  batch.classList.toggle('hidden', mode !== 'batch');

  // Map layers
  const tradeGroup = document.querySelector('.trade-routes-group');
  const campaignGroup = document.querySelector('.campaign-group');
  if (tradeGroup) tradeGroup.style.display = mode === 'trade' ? 'block' : 'none';
  if (campaignGroup) campaignGroup.style.display = mode === 'campaign' ? 'block' : 'none';

  // Layer chips
  const layers = document.getElementById('map-layers');
  if (mode === 'trade') {
    layers.innerHTML = `
      <div class="layer-chip active">Routes</div>
      <div class="layer-chip active">Markets</div>
      <div class="layer-chip">Flow Volume</div>
      <div class="layer-chip">Stockpiles</div>
      <div class="layer-chip">Disruptions</div>
    `;
  } else if (mode === 'campaign') {
    layers.innerHTML = `
      <div class="layer-chip active">March Routes</div>
      <div class="layer-chip active">Battles</div>
      <div class="layer-chip">Supply Lines</div>
      <div class="layer-chip">Knowledge Fog</div>
      <div class="layer-chip">Asabiya</div>
    `;
  } else {
    layers.innerHTML = `
      <div class="layer-chip active">Borders</div>
      <div class="layer-chip active">Settlements</div>
      <div class="layer-chip">Routes</div>
      <div class="layer-chip">Terrain</div>
      <div class="layer-chip">Faith</div>
    `;
  }

  // Animate trade routes on
  if (mode === 'trade') {
    setTimeout(() => {
      document.querySelectorAll('.trade-route').forEach((r, i) => {
        r.classList.add('route-animate');
        r.style.animationDelay = (i * 0.15) + 's';
      });
    }, 100);
  }

  // Update inspector
  setupInspector(mode);

  // Draw radar if character mode
  if (mode === 'character') {
    setTimeout(drawRadar, 300);
  }

  // Adjust viewer body height for ribbon
  const body = document.getElementById('viewer-body');
  if (mode === 'campaign') {
    body.style.height = `calc(100vh - ${44 + 56 + 32}px)`;
  } else {
    body.style.height = `calc(100vh - ${44 + 56}px)`;
  }
}

// ============ EVENTS ============
function bindEvents() {
  // Demo controls
  document.getElementById('btn-demo-play').addEventListener('click', startDemo);
  document.getElementById('btn-demo-pause').addEventListener('click', pauseDemo);

  // Manual state nav
  document.querySelectorAll('.demo-nav button').forEach(btn => {
    btn.addEventListener('click', () => {
      pauseDemo();
      goToState(btn.dataset.state);
    });
  });

  // Run world button
  document.getElementById('btn-run-world').addEventListener('click', () => {
    goToState('progress');
  });

  // Mode tabs
  document.querySelectorAll('.mode-tab').forEach(tab => {
    tab.addEventListener('click', () => {
      switchMode(tab.dataset.mode);
    });
  });

  // Rail tabs
  document.querySelectorAll('.rail-tab').forEach(tab => {
    tab.addEventListener('click', () => {
      document.querySelectorAll('.rail-tab').forEach(t => t.classList.remove('active'));
      tab.classList.add('active');
      document.getElementById('rail-chronicle').classList.toggle('hidden', tab.dataset.rail !== 'chronicle');
      document.getElementById('rail-events').classList.toggle('hidden', tab.dataset.rail !== 'events');
    });
  });

  // Layer chips (toggle)
  document.getElementById('map-layers').addEventListener('click', (e) => {
    if (e.target.classList.contains('layer-chip')) {
      e.target.classList.toggle('active');
    }
  });

  // Timeline scrub (click to move playhead)
  document.getElementById('timeline-rail').addEventListener('click', (e) => {
    const track = document.querySelector('.timeline-track');
    const rect = track.getBoundingClientRect();
    const pct = Math.max(0, Math.min(100, ((e.clientX - rect.left) / rect.width) * 100));
    const turn = Math.round(pct / 100 * 5000);
    movePlayhead(pct, turn);
  });

  // Batch table open buttons
  document.getElementById('batch-tbody').addEventListener('click', (e) => {
    if (e.target.classList.contains('open-btn')) {
      switchMode('overview');
    }
  });
}

function movePlayhead(pct, turn) {
  const playhead = document.getElementById('timeline-playhead');
  playhead.style.left = pct + '%';
  playhead.querySelector('.playhead-label').textContent = turn;
}

// ============ STATE MACHINE ============
function goToState(state) {
  // Update demo nav
  document.querySelectorAll('.demo-nav button').forEach(b => {
    b.classList.toggle('active', b.dataset.state === state);
  });

  switch(state) {
    case 'setup':
      switchScreen('setup');
      break;

    case 'progress':
      switchScreen('progress');
      animateProgress();
      break;

    case 'overview':
      switchScreen('viewer');
      switchMode('overview');
      break;

    case 'character':
      switchScreen('viewer');
      switchMode('character');
      break;

    case 'trade':
      switchScreen('viewer');
      switchMode('trade');
      break;

    case 'campaign':
      switchScreen('viewer');
      switchMode('campaign');
      break;

    case 'batch':
      switchScreen('viewer');
      switchMode('batch');
      break;
  }
}

// ============ PROGRESS ANIMATION ============
function animateProgress(callback) {
  const fill = document.getElementById('progress-fill');
  const turnEl = document.getElementById('progress-turn');
  const pctEl = document.getElementById('progress-pct');
  const simStatus = document.getElementById('sim-status');
  const perfStatus = document.getElementById('perf-status');
  const interestStatus = document.getElementById('interest-status');
  const narrStatus = document.getElementById('narr-status');
  const loadingText = document.getElementById('progress-loading');

  const stages = [
    { pct: 0,   turn: 0,    sim: 'Initializing...', perf: '—', interest: '—', narr: 'Waiting...', text: 'Generating world topology...' },
    { pct: 5,   turn: 250,  sim: 'Running', perf: '12.8 ms/t', interest: '—', narr: 'Queued', text: 'Seeding civilizations...' },
    { pct: 20,  turn: 1000, sim: 'Running', perf: '13.4 ms/t', interest: '0.31', narr: '12 entries', text: 'Foundation era emerging...' },
    { pct: 45,  turn: 2250, sim: 'Running', perf: '14.0 ms/t', interest: '0.52', narr: '28 entries', text: 'First wars detected...' },
    { pct: 70,  turn: 3500, sim: 'Running', perf: '14.1 ms/t', interest: '0.68', narr: '41 entries', text: 'Fragmentation era detected...' },
    { pct: 90,  turn: 4500, sim: 'Running', perf: '14.2 ms/t', interest: '0.71', narr: '45 entries', text: 'Late decay phase...' },
    { pct: 100, turn: 5000, sim: 'Complete', perf: '14.2 ms/t', interest: '0.73', narr: '47 entries', text: 'Assembling bundle...' },
  ];

  let idx = 0;
  function next() {
    if (idx >= stages.length) {
      if (callback) setTimeout(callback, 800);
      return;
    }
    const s = stages[idx];
    fill.style.width = s.pct + '%';
    turnEl.textContent = s.turn;
    pctEl.textContent = s.pct + '%';
    simStatus.textContent = s.sim;
    perfStatus.textContent = s.perf;
    interestStatus.textContent = s.interest;
    narrStatus.textContent = s.narr;
    loadingText.textContent = s.text;

    // Dot colors
    if (s.pct > 0) {
      document.querySelectorAll('.status-dot')[0].className = 'status-dot green';
      document.querySelectorAll('.status-dot')[1].className = 'status-dot amber';
    }
    if (s.interest !== '—') {
      document.querySelectorAll('.status-dot')[2].className = 'status-dot cyan';
    }
    if (s.narr !== 'Waiting...') {
      document.querySelectorAll('.status-dot')[3].className = 'status-dot green';
    }

    idx++;
    progressTimer = setTimeout(next, demoRunning ? 600 : 500);
  }
  next();
}

let progressTimer = null;

// ============ DEMO SEQUENCE ============
const DEMO_SEQUENCE = [
  { state: 'setup',     duration: 4000 },
  { state: 'progress',  duration: 5000 },
  { state: 'overview',  duration: 8000, actions: [
    { delay: 1500, fn: () => movePlayhead(60, 3000) },
    { delay: 3000, fn: () => movePlayhead(76.24, 3812) },
    { delay: 4500, fn: () => {
      // Switch to event log tab
      document.querySelectorAll('.rail-tab')[1].click();
    }},
    { delay: 6000, fn: () => {
      document.querySelectorAll('.rail-tab')[0].click();
    }},
  ]},
  { state: 'character', duration: 7000, actions: [
    { delay: 2000, fn: () => movePlayhead(71, 3550) },
    { delay: 4000, fn: () => movePlayhead(76.24, 3812) },
  ]},
  { state: 'trade',     duration: 7000, actions: [
    { delay: 2000, fn: () => {
      // Highlight a trade route
      const routes = document.querySelectorAll('.trade-route');
      if (routes[0]) routes[0].classList.add('active');
    }},
    { delay: 4000, fn: () => {
      document.querySelectorAll('.trade-route').forEach(r => r.classList.remove('active'));
      const routes = document.querySelectorAll('.trade-route');
      if (routes[3]) routes[3].classList.add('active');
    }},
    { delay: 5500, fn: () => {
      document.querySelectorAll('.trade-route').forEach(r => r.classList.remove('active'));
    }},
  ]},
  { state: 'campaign',  duration: 7000, actions: [
    { delay: 2000, fn: () => movePlayhead(71, 3550) },
    { delay: 4000, fn: () => movePlayhead(76.24, 3812) },
  ]},
  { state: 'batch',     duration: 6000, actions: [
    { delay: 3000, fn: () => {
      // Simulate opening top seed
      const btn = document.querySelector('.batch-table .open-btn');
      if (btn) {
        btn.style.borderColor = 'var(--cyan)';
        btn.style.color = 'var(--cyan)';
      }
    }},
    { delay: 4500, fn: () => {
      switchMode('overview');
    }},
  ]},
];

let demoStepIndex = 0;
let demoActionTimers = [];

function startDemo() {
  demoRunning = true;
  demoStepIndex = 0;
  document.getElementById('btn-demo-play').style.display = 'none';
  document.getElementById('btn-demo-pause').style.display = 'inline-block';
  runDemoStep();
}

function pauseDemo() {
  demoRunning = false;
  document.getElementById('btn-demo-play').style.display = 'inline-block';
  document.getElementById('btn-demo-pause').style.display = 'none';
  if (demoTimeout) clearTimeout(demoTimeout);
  demoActionTimers.forEach(t => clearTimeout(t));
  demoActionTimers = [];
}

function runDemoStep() {
  if (!demoRunning || demoStepIndex >= DEMO_SEQUENCE.length) {
    pauseDemo();
    return;
  }

  const step = DEMO_SEQUENCE[demoStepIndex];
  goToState(step.state);

  // Schedule sub-actions
  if (step.actions) {
    step.actions.forEach(a => {
      const t = setTimeout(() => {
        if (demoRunning) a.fn();
      }, a.delay);
      demoActionTimers.push(t);
    });
  }

  demoStepIndex++;
  demoTimeout = setTimeout(() => runDemoStep(), step.duration);
}

// ============ KEYBOARD SHORTCUTS ============
document.addEventListener('keydown', (e) => {
  if (e.key === ' ' || e.code === 'Space') {
    e.preventDefault();
    if (demoRunning) pauseDemo();
    else startDemo();
  }
  if (e.key >= '1' && e.key <= '7') {
    const states = ['setup', 'progress', 'overview', 'character', 'trade', 'campaign', 'batch'];
    pauseDemo();
    goToState(states[parseInt(e.key) - 1]);
  }
});
