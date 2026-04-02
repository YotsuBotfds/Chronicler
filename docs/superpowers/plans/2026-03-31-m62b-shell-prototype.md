# Phase 7.5 Shell Prototype Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a static HTML/CSS/JS prototype at `prototype/cici/` that demonstrates the unified Phase 7.5 viewer shell across all modes (Setup, Progress, Overview, Character, Trade, Campaign, Batch Lab), merging the best patterns from the Antigravity and GPT-5 prototypes into one canonical product shell.

**Architecture:** Single HTML page with four app-states (setup, progress, viewer, batch). The viewer state hosts a shared shell with mode tabs switching content within fixed layout rails. No build tools, no framework -- pure HTML/CSS/JS that opens directly in a browser. Canvas 2D for map rendering. CSS custom properties for the design system. ES module-style JS files loaded via `<script>` tags.

**Tech Stack:** HTML5, CSS3 custom properties, vanilla JavaScript, Canvas 2D API, Google Fonts (Playfair Display, Inter, JetBrains Mono).

---

## Agent Team Configuration

Launch with 4 teammates. Each owns distinct files with no write conflicts.

| Teammate | Role | Owns | Tasks |
|----------|------|------|-------|
| `foundations` | HTML structure, tokens, mock data | `index.html`, `tokens.css`, `data.js` | 1, 2, 3 |
| `styles` | All CSS styling | `layout.css`, `states.css`, `components.css`, `map.css` | 4, 5, 6, 7 |
| `core-logic` | State management, timeline, map | `state.js`, `timeline.js`, `map.js` | 8, 9, 10 |
| `content` | Rails, setup, batch, demo | `rails.js`, `setup.js`, `batch.js`, `demo.js` | 11, 12, 13, 14 |

### Dependency chain

```
Phase 1:  [foundations: Tasks 1-3]  (no dependencies)
Phase 2:  [styles: Tasks 4-7]      (needs tokens.css from Task 1)
Phase 3:  [core-logic: Tasks 8-10] (needs index.html from Task 3, data.js from Task 2)
Phase 4:  [content: Tasks 11-14]   (needs state.js from Task 8, data.js from Task 2)
```

Teammates can start in parallel if given the shared contracts below. Foundations should finish first; the other three can overlap heavily.

### Teammate spawn prompts

When launching the agent team, each teammate should receive:
1. This plan document path
2. Their assigned task numbers
3. The "Shared Contracts" section below (copy into their prompt)
4. Reference prototype paths: `viewer/antigravity-prototype/` and `prototype/gpt5/`
5. Target directory: `prototype/cici/`

---

## Shared Contracts

These contracts define the interfaces between files. All teammates must use these exact names.

### CSS custom property names (tokens.css)

All components reference these `var(--*)` names. Do not invent new tokens -- extend this list only if needed and document why.

```
--bg-deepest, --bg-deep, --bg-surface, --bg-raised, --bg-hover, --bg-active
--map-water, --map-land, --map-land-light
--chrome-border, --chrome-border-light, --chrome-gold, --chrome-gold-dim, --chrome-gold-bright
--accent-cyan, --accent-cyan-bright, --accent-cyan-dim, --accent-cyan-glow
--text-primary, --text-secondary, --text-tertiary, --text-label, --text-heading
--status-green, --status-green-bg, --status-amber, --status-amber-bg, --status-red, --status-red-bg
--trade-gold, --trade-gold-dim
--campaign-crimson, --campaign-crimson-bright
--font-heading, --font-ui, --font-mono
--rail-width, --inspector-width, --header-height, --timeline-height, --ribbon-height
--panel-bg, --panel-border, --panel-shadow, --panel-radius
```

### HTML element IDs (index.html)

JS files reference these IDs via `document.getElementById()`:

```
App states:      state-setup, state-progress, state-viewer, state-batch
Header:          viewer-header, mode-tabs
Timeline:        timeline-rail, timeline-track, timeline-events, timeline-narrated, timeline-playhead
Workspace:       workspace, left-rail, left-rail-content, map-column, map-viewport, main-map, right-rail, inspector-body
Validation:      validation-ribbon
Setup:           input-scenario, input-seed, input-turns, input-civs, input-regions, btn-run-world, setup-preview-map
                 val-turns, val-civs, val-regions
Progress:        sim-progress-fill, progress-turn, progress-speed, progress-log,
                 ind-sim, ind-narr, ind-bundle, ind-interest
Batch:           batch-table-body
Demo:            demo-controls, btn-auto-demo, btn-pause-demo, demo-jumps
Map:             map-controls, map-legend, map-hover-card, map-overlays
Layer chips:     layer-chips
```

### HTML CSS classes (shared vocabulary)

```
.app-state, .app-state.active       -- app state visibility
.panel                               -- glass-morphism card treatment
.mono                                -- monospace font
.tiny-label                          -- uppercase 10px label
.mode-tab, .mode-tab.active         -- header mode tabs
.rail-tab, .rail-tab.active         -- left rail tabs
.layer-chip, .layer-chip.active     -- map overlay toggles
.filter-chip, .filter-chip.active   -- batch filter buttons
.toggle-btn, .toggle-btn.active     -- setup toggle groups
.btn-primary, .btn-secondary        -- action buttons
.btn-sm, .btn-icon                  -- button variants
.form-label, .form-input, .form-select, .form-range  -- form elements
.tag                                 -- small tag pill
.version-pill                        -- version badge
.mode-badge                          -- ARCHIVE/LIVE badge
.val-check, .val-check.pass, .val-check.warn, .val-check.oracle  -- validation ribbon
.inspector-card                      -- right rail card
.kpi-row, .kpi-item                 -- key performance indicators
.chronicle-entry                     -- left rail narrative entry
.event-row                           -- left rail event log row
.jump-btn                            -- demo jump buttons
```

### State management API (state.js)

All JS files call these functions. Do not access `APP` directly from other files.

```javascript
// Global state object
window.APP = {
  state: 'setup',           // 'setup' | 'progress' | 'viewer' | 'batch'
  mode: 'overview',         // 'overview' | 'character' | 'trade' | 'campaign'
  selectedCiv: 0,           // index into DATA.civs
  selectedEntity: null,     // { type: 'region'|'character'|'route'|'army', id: string } | null
  hoveredRegion: -1,        // index into DATA.regions, -1 = none
  currentTurn: 3812,        // current playhead position
  leftTab: 'chronicle',     // 'chronicle' | 'events'
  activeOverlays: new Set(['borders', 'settlements']),
  demoRunning: false,
  demoStep: 0,
};

// State transitions -- each calls registered listeners
window.setState = function(newState) { ... }
window.setMode = function(newMode) { ... }
window.selectEntity = function(type, id) { ... }
window.scrubTimeline = function(turn) { ... }
window.toggleOverlay = function(layer) { ... }

// Listener registry
window.onStateChange = function(callback) { ... }  // called on any state change
window.onModeChange = function(callback) { ... }    // called on mode switch
window.onEntitySelect = function(callback) { ... }  // called on entity selection
window.onTurnChange = function(callback) { ... }     // called on timeline scrub
```

### Data model shape (data.js)

```javascript
window.DATA = {
  meta: { world, scenario, seed, schema, totalTurns, interestingness, performance },
  eras: [ { name, startPct, widthPct } ],
  events: [ { turn, pctLeft, type, title } ],
  narratedSpans: [ { leftPct, widthPct } ],
  regions: [ { id, name, path, cx, cy, civIdx, color } ],
  civs: [ { name, color, colorDark } ],
  tradeRoutes: [ { id, name, points, label } ],
  campaignLines: [ { type, points } ],
  battleSites: [ { cx, cy, r } ],
  settlements: [ { name, region, x, y, r } ],
  leftRail: { [mode]: { chronicle: { title, entries }, events: { title, entries } } },
  inspector: { overview: {...}, character: {...}, trade: {...}, campaign: {...} },
  batch: [ { seed, score, wars, collapses, namedEvents, techMovement, anomalies } ],
};
```

---

## File Map

All files created under `prototype/cici/`.

| File | Responsibility | Lines (est.) |
|------|----------------|-------------|
| `tokens.css` | Design system custom properties, reset, base typography | ~100 |
| `layout.css` | Shell grid, header, timeline rail, workspace rails | ~200 |
| `states.css` | Setup sidebar/form, progress card, batch table layout | ~250 |
| `components.css` | Cards, tabs, buttons, forms, badges, inspector pieces | ~300 |
| `map.css` | Map viewport, controls, legend, hover card, overlays | ~120 |
| `data.js` | All mock data for every mode | ~350 |
| `index.html` | Complete HTML structure with all app states | ~350 |
| `state.js` | APP object, state transitions, listener registry | ~120 |
| `timeline.js` | Timeline rail rendering and interaction | ~100 |
| `map.js` | Canvas map rendering, mouse interaction | ~350 |
| `rails.js` | Left rail + right inspector content generation | ~300 |
| `setup.js` | Setup form interaction, progress animation | ~120 |
| `batch.js` | Batch table rendering, filters, row interaction | ~100 |
| `demo.js` | Automated walkthrough sequence | ~120 |

**Total:** ~2,880 lines across 14 files.

---

## Task 1: Design System Tokens

**Teammate:** `foundations`
**Files:** Create `prototype/cici/tokens.css`

Merge the Antigravity token set (systematic background scale, precise chrome/accent values) with GPT-5's panel treatment (backdrop-filter, subtle gradients). Antigravity values are canonical; GPT-5 contributes the `--panel-*` family.

- [ ] **Step 1: Create tokens.css**

```css
/* ============================================================
   Chronicler 7.5 — Design System Tokens
   Dark Atlas Workstation
   ============================================================ */

:root {
  /* Backgrounds (6-stop scale, darkest to lightest) */
  --bg-deepest: #0e0e14;
  --bg-deep: #14141c;
  --bg-surface: #1c1c26;
  --bg-raised: #242430;
  --bg-hover: #2c2c3a;
  --bg-active: #343442;

  /* Map terrain */
  --map-water: #12141e;
  --map-land: #2a2720;
  --map-land-light: #353028;

  /* Chrome (borders, dividers, gold accents) */
  --chrome-border: #2e2e3c;
  --chrome-border-light: #3a3a4a;
  --chrome-gold: #9d8a5e;
  --chrome-gold-dim: #6a5d3a;
  --chrome-gold-bright: #c4aa6a;

  /* Accent (cyan for interaction state) */
  --accent-cyan: #4a9ebb;
  --accent-cyan-bright: #62c8e8;
  --accent-cyan-dim: #2a6a80;
  --accent-cyan-glow: rgba(74, 158, 187, 0.15);

  /* Text (5-stop scale) */
  --text-primary: #ddd8cc;
  --text-secondary: #9e978a;
  --text-tertiary: #68635a;
  --text-label: #87827a;
  --text-heading: #e8e4da;

  /* Status */
  --status-green: #5a9a5a;
  --status-green-bg: rgba(90, 154, 90, 0.12);
  --status-amber: #c4a030;
  --status-amber-bg: rgba(196, 160, 48, 0.12);
  --status-red: #b05050;
  --status-red-bg: rgba(176, 80, 80, 0.12);

  /* Trade overlay */
  --trade-gold: #c4a04a;
  --trade-gold-dim: #8a7030;

  /* Campaign overlay */
  --campaign-crimson: #8a4040;
  --campaign-crimson-bright: #b05555;

  /* Fonts */
  --font-heading: 'Playfair Display', Georgia, 'Times New Roman', serif;
  --font-ui: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  --font-mono: 'JetBrains Mono', 'Cascadia Code', 'Fira Code', monospace;

  /* Layout dimensions */
  --rail-width: 260px;
  --inspector-width: 310px;
  --header-height: 42px;
  --timeline-height: 52px;
  --ribbon-height: 32px;

  /* Panel treatment (from GPT-5 glass-morphism) */
  --panel-bg: rgba(19, 22, 22, 0.94);
  --panel-border: rgba(183, 151, 94, 0.24);
  --panel-shadow: 0 18px 48px rgba(0, 0, 0, 0.42);
  --panel-radius: 8px;
}

/* ============================================================
   Reset & Base
   ============================================================ */
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

html, body {
  width: 100%; height: 100%;
  overflow: hidden;
  background: var(--bg-deepest);
  color: var(--text-primary);
  font-family: var(--font-ui);
  font-size: 13px;
  line-height: 1.45;
  -webkit-font-smoothing: antialiased;
}

h1, h2, h3, h4, h5 {
  font-family: var(--font-heading);
  color: var(--text-heading);
  font-weight: 600;
}

.mono { font-family: var(--font-mono); font-size: 0.92em; }

.tiny-label {
  text-transform: uppercase;
  letter-spacing: 0.1em;
  font-size: 10px;
  font-weight: 600;
  color: var(--text-tertiary);
}

::selection { background: var(--accent-cyan-dim); color: var(--text-primary); }

::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: var(--chrome-border-light); border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: var(--text-tertiary); }

.panel {
  background: linear-gradient(180deg, rgba(255,255,255,0.016), transparent 14%), var(--panel-bg);
  border: 1px solid var(--panel-border);
  border-radius: var(--panel-radius);
  box-shadow: var(--panel-shadow);
  backdrop-filter: blur(8px);
}
```

- [ ] **Step 2: Verify file created**

Run: `ls -la prototype/cici/tokens.css`
Expected: file exists, ~100 lines

---

## Task 2: Mock Data Model

**Teammate:** `foundations`
**Files:** Create `prototype/cici/data.js`

Adapt from GPT-5 prototype's `app.js` data structures. Include mock data for all modes, all inspector variants, all left-rail content, timeline eras/events, map regions, and batch results.

- [ ] **Step 1: Create data.js**

```javascript
// Chronicler 7.5 Shell Prototype — Mock Data
// All mock data for every mode and panel

window.DATA = {
  // --- Run metadata (header + progress) ---
  meta: {
    world: 'Aethelgard Reborn',
    scenario: 'Migration Era Decay',
    seed: '4ASF-9B1D-7C6E',
    schema: 'v7.5.12',
    totalTurns: 5000,
    interestingness: 0.73,
    performance: '14.2 ms/turn',
  },

  // --- Timeline ---
  eras: [
    { name: 'Founding',        startPct: 0,  widthPct: 10 },
    { name: 'Early Expansion',  startPct: 10, widthPct: 14 },
    { name: 'Golden Age',       startPct: 24, widthPct: 16 },
    { name: 'Age of Conflict',  startPct: 40, widthPct: 20 },
    { name: 'Migration Decay',  startPct: 60, widthPct: 24 },
    { name: 'Late Period',      startPct: 84, widthPct: 16 },
  ],

  events: [
    { turn: 612,  pctLeft: 12, type: 'war',      title: 'First border war' },
    { turn: 1270, pctLeft: 25, type: 'culture',   title: 'Aurelian schools reunified' },
    { turn: 2091, pctLeft: 42, type: 'collapse',  title: 'Great famine' },
    { turn: 2784, pctLeft: 55, type: 'war',       title: 'March succession crisis' },
    { turn: 3160, pctLeft: 63, type: 'faith',     title: 'Schism of Thornwall' },
    { turn: 3472, pctLeft: 72, type: 'war',       title: 'Salt Step invasion' },
    { turn: 3812, pctLeft: 81, type: 'collapse',  title: 'Imperial collapse' },
    { turn: 3886, pctLeft: 88, type: 'character', title: 'Rise of Eadric' },
  ],

  narratedSpans: [
    { leftPct: 5,  widthPct: 11 },
    { leftPct: 22, widthPct: 12 },
    { leftPct: 44, widthPct: 9 },
    { leftPct: 66, widthPct: 8 },
    { leftPct: 80, widthPct: 9 },
  ],

  // --- Civilizations ---
  civs: [
    { name: 'Thornwall March',   color: '#5b8a72', colorDark: '#3a5c4a' },
    { name: 'Aurelian Republic', color: '#8a7b5b', colorDark: '#5c5240' },
    { name: 'Kestrel Dominion',  color: '#5b6e8a', colorDark: '#3d4a5c' },
    { name: 'Salt Step Khanate', color: '#8a5b5b', colorDark: '#5c3d3d' },
    { name: 'Saints Vale',       color: '#7b5b8a', colorDark: '#523d5c' },
  ],

  // --- Regions (SVG-coordinate polygons for canvas rendering) ---
  regions: [
    { id: 'thornwall',    name: 'Thornwall',      path: [[138,136],[246,102],[328,132],[306,232],[212,262],[144,222]], cx: 230, cy: 180, civIdx: 0 },
    { id: 'greyfen',      name: 'Greyfen Basin',  path: [[306,132],[442,108],[540,156],[492,268],[356,286],[306,232]], cx: 407, cy: 195, civIdx: 0 },
    { id: 'kestrel',      name: 'Kestrel Port',   path: [[540,156],[678,132],[798,184],[734,296],[562,296],[492,268]], cx: 634, cy: 220, civIdx: 2 },
    { id: 'aurelian',     name: 'Aurelian Gate',  path: [[144,222],[212,262],[198,392],[110,420],[48,306],[86,234]],   cx: 133, cy: 306, civIdx: 1 },
    { id: 'hollowmere',   name: 'Hollowmere',     path: [[212,262],[356,286],[382,414],[256,456],[198,392]],          cx: 281, cy: 362, civIdx: 0 },
    { id: 'lastorchard',  name: 'Last Orchard',   path: [[356,286],[562,296],[554,430],[382,414]],                    cx: 464, cy: 356, civIdx: 1 },
    { id: 'saltstep',     name: 'Salt Step',      path: [[562,296],[734,296],[852,352],[788,488],[554,430]],          cx: 698, cy: 372, civIdx: 3 },
    { id: 'saintsvale',   name: "Saint's Vale",   path: [[110,420],[256,456],[238,594],[106,632],[52,516]],           cx: 152, cy: 524, civIdx: 4 },
    { id: 'ashspine',     name: 'Ashspine',       path: [[256,456],[554,430],[528,610],[286,628],[238,594]],          cx: 372, cy: 524, civIdx: 1 },
    { id: 'redsalt',      name: 'Red Salt',       path: [[554,430],[788,488],[934,564],[860,658],[528,610]],          cx: 733, cy: 550, civIdx: 3 },
  ],

  // --- Settlements ---
  settlements: [
    { name: 'Thornwall',       region: 'thornwall',   x: 234, y: 178, r: 8 },
    { name: 'Greyfen',         region: 'greyfen',     x: 368, y: 236, r: 7 },
    { name: 'Kestrel Port',    region: 'kestrel',     x: 704, y: 220, r: 8 },
    { name: 'Aurelian Gate',   region: 'aurelian',    x: 110, y: 300, r: 6 },
    { name: 'Last Orchard',    region: 'lastorchard', x: 466, y: 360, r: 6 },
    { name: 'Halewatch',       region: 'saltstep',    x: 734, y: 362, r: 7 },
    { name: "Saint's Ford",    region: 'saintsvale',  x: 154, y: 520, r: 6 },
    { name: 'Red Salt',        region: 'redsalt',     x: 786, y: 564, r: 8 },
  ],

  // --- Trade routes ---
  tradeRoutes: [
    { id: 'amber-loop',    name: 'Amber Corridor',       points: [[338,248],[452,234],[566,216],[704,220]], labelX: 472, labelY: 212 },
    { id: 'grain-road',    name: 'Greyfen Grain Road',   points: [[340,316],[420,330],[500,344],[612,364]], labelX: 458, labelY: 352 },
    { id: 'orchard-salt',  name: 'Orchard Salt Loop',    points: [[404,452],[522,444],[624,470],[760,536]], labelX: 606, labelY: 518 },
  ],

  // --- Campaign lines ---
  campaignLines: [
    { type: 'supply',   points: [[698,244],[722,296],[732,340],[742,382]] },
    { type: 'campaign', points: [[706,252],[724,304],[752,342],[768,384],[792,446],[820,514]] },
    { type: 'front',    points: [[618,338],[686,312],[742,312],[814,338]] },
  ],
  battleSites: [
    { cx: 770, cy: 384, r: 10 },
    { cx: 826, cy: 518, r: 8 },
  ],

  // --- Named character marker ---
  characterMarker: { name: 'Eadric of Thornwall', x: 404, y: 348 },
  armyChip: { name: 'III Field', x: 706, y: 252 },

  // --- Contour lines (terrain feel) ---
  contours: [
    [[42,112],[220,48],[420,72],[642,112],[918,138],[980,112]],
    [[36,184],[214,120],[436,132],[626,170],[904,212],[970,184]],
    [[26,256],[210,196],[408,224],[606,268],[886,304],[970,274]],
    [[18,330],[170,296],[372,304],[586,348],[870,398],[958,362]],
    [[24,424],[164,402],[344,410],[556,452],[814,496],[942,470]],
    [[40,520],[204,500],[370,494],[566,534],[826,584],[968,548]],
  ],

  // --- Rivers ---
  rivers: [
    [[240,90],[280,156],[286,214],[328,286],[372,454],[422,586]],
    [[580,118],[624,168],[650,230],[656,278],[714,406],[790,498]],
  ],

  // --- Left rail content per mode ---
  leftRail: {
    overview: {
      chronicle: {
        title: 'Chronicle of Aethelgard',
        entries: [
          { tag: 'era', title: 'Migration Decay begins', body: 'The frontier provinces fracture as Salt Step cavalry raids intensify along the orchard road. Thornwall attempts to hold the grain convoys but treasury reserves are dangerously low.' },
          { tag: 'war', title: 'Salt Step Invasion (T3472)', body: 'Khan Borte commits three field armies through the Last Orchard corridor. Kestrel Port closes its harbor to all Thornwall shipping.' },
          { tag: 'faith', title: 'Schism of Thornwall (T3160)', body: 'The Thorn Rite clergy split over the question of Salt Step converts. The Old Basilica faction allies with Aurelian merchants.' },
          { tag: 'collapse', title: 'Imperial collapse (T3812)', body: 'Prince Caedmon declares the March independent after the Aurelian Republic recalls its garrison. The trade network fractures along religious lines.' },
        ],
      },
      events: {
        title: 'Event Log',
        entries: [
          { turn: 3812, type: 'political', text: 'Thornwall March declares independence from the Aurelian Republic' },
          { turn: 3810, type: 'military',  text: 'III Field Army retreats to Greyfen Basin after supply failure' },
          { turn: 3808, type: 'economic',  text: 'Amber Corridor trade volume drops 34% as Kestrel imposes embargo' },
          { turn: 3805, type: 'religious', text: 'Thorn Rite clergy consolidate after schism; Pilgrim Houses lose 40% adherents' },
          { turn: 3801, type: 'cultural',  text: 'Marcher identity movement gains traction in Hollowmere' },
          { turn: 3798, type: 'military',  text: 'Salt Step raiding party repelled at Ashspine border' },
          { turn: 3795, type: 'economic',  text: 'Grain stockpiles in Greyfen reach critical minimum' },
          { turn: 3790, type: 'political', text: 'Lady Ysabet named second in succession after Prince Caedmon' },
        ],
      },
    },
    character: {
      chronicle: {
        title: 'Eadric of Thornwall',
        entries: [
          { tag: 'memory', title: 'Siege of Greyfen (Mule source)', body: 'The 40-day siege left Eadric with a permanent warping of decision utility. He over-indexes defensive positioning and under-values offensive opportunity.' },
          { tag: 'arc', title: 'Regent of the March', body: 'Promoted to regent after the imperial collapse. Currently holding the succession bloc while managing clergy fracture.' },
          { tag: 'relationship', title: 'Rivalry with Khan Borte', body: 'Personal enmity since the Salt Step invasion. Borte destroyed Eadric\'s family estate in Hollowmere.' },
          { tag: 'dynasty', title: 'House Thornwall', body: 'Third generation. Father was Lord Aldric (killed at Greyfen). Mother Lady Maeven holds the Ashspine dowry lands.' },
        ],
      },
      events: {
        title: 'Character Events',
        entries: [
          { turn: 3886, type: 'promotion',  text: 'Eadric promoted to Regent of the March' },
          { turn: 3812, type: 'political',   text: 'Eadric endorses independence declaration' },
          { turn: 3780, type: 'military',    text: 'Eadric commands defense of Greyfen Ford' },
          { turn: 3750, type: 'relationship', text: 'Marriage alliance proposed with Saints Vale' },
          { turn: 3720, type: 'memory',      text: 'Siege of Greyfen — Mule event triggered' },
        ],
      },
    },
    trade: {
      chronicle: {
        title: 'Trade Diagnostics',
        entries: [
          { tag: 'route', title: 'Amber Corridor under stress', body: 'Profit margin dropped from 24% to 18% after Kestrel embargo. Merchants rerouting through Last Orchard incur higher transport costs.' },
          { tag: 'market', title: 'Greyfen grain crisis', body: 'Food sufficiency at 0.94 and falling. Import share at 42% makes the settlement critically dependent on convoy reliability.' },
          { tag: 'belief', title: 'Price belief divergence', body: 'Stale belief (0.91) vs current (1.04) shows merchants operating on outdated price information from 3 turns ago.' },
        ],
      },
      events: {
        title: 'Trade Events',
        entries: [
          { turn: 3812, type: 'embargo',   text: 'Kestrel Port imposes full trade embargo on Thornwall' },
          { turn: 3808, type: 'volume',    text: 'Amber Corridor volume down 34%' },
          { turn: 3800, type: 'price',     text: 'Grain price spike in Greyfen (+22%)' },
          { turn: 3795, type: 'stockpile', text: 'Greyfen grain stockpile hits critical minimum' },
          { turn: 3788, type: 'route',     text: 'Orchard Salt Loop profit margin exceeds Amber Corridor' },
        ],
      },
    },
    campaign: {
      chronicle: {
        title: 'Campaign Intelligence',
        entries: [
          { tag: 'army', title: 'III Thornwall Field Army', body: 'Morale at 0.62 after the Greyfen Ford engagement. 19 days of supply remaining. Target: hold Saint\'s Ford before Salt Step cavalry reaches the orchard road.' },
          { tag: 'battle', title: 'Greyfen Ford (T3780)', body: 'Defensive victory. 1,840 casualties. Salt Step lost their forward supply depot but retained the Ashspine staging ground.' },
          { tag: 'knowledge', title: 'Intelligence freshness', body: 'Familiarity 0.84, confidence 0.78. Salt Step troop movements are 2 turns stale. Ashspine border scouts report increased cavalry concentration.' },
        ],
      },
      events: {
        title: 'Military Events',
        entries: [
          { turn: 3812, type: 'strategic', text: 'Imperial collapse removes Aurelian garrison from Thornwall' },
          { turn: 3810, type: 'movement',  text: 'III Field Army retreats to Greyfen Basin' },
          { turn: 3805, type: 'supply',    text: 'Supply convoy from Saints Vale arrives (19 days)' },
          { turn: 3800, type: 'intel',     text: 'Scouts report Salt Step cavalry massing near Ashspine' },
          { turn: 3780, type: 'battle',    text: 'Battle of Greyfen Ford — defensive victory' },
        ],
      },
    },
  },

  // --- Right inspector content per mode ---
  inspector: {
    overview: {
      title: 'Thornwall March',
      subtitle: 'Civilization Overview',
      sections: [
        { label: 'Capital', value: 'Thornwall' },
        { label: 'Population', value: '4.8M' },
        { label: 'Wealth', value: '182M thalers' },
        { label: 'Trade Dependency', value: '41%' },
        { label: 'Class Tension', value: '0.27' },
        { label: 'Asabiya', value: '0.61' },
        { label: 'Tech Era', value: 'Late Iron' },
        { label: 'Succession', value: 'Prince Caedmon, then Lady Ysabet' },
      ],
      distributions: [
        { label: 'Faith', items: [{ name: 'Thorn Rite', pct: 52 }, { name: 'Old Basilica', pct: 29 }, { name: 'Pilgrim Houses', pct: 19 }] },
        { label: 'Factions', items: [{ name: 'Crown', pct: 34 }, { name: 'Nobility', pct: 27 }, { name: 'Merchants', pct: 21 }, { name: 'Clergy', pct: 18 }] },
        { label: 'Culture', items: [{ name: 'Marcher', pct: 46 }, { name: 'Aurelian', pct: 31 }, { name: 'Steppe-born', pct: 23 }] },
      ],
    },
    character: {
      title: 'Eadric of Thornwall',
      subtitle: 'Regent of the March',
      stableId: 'GP-00481',
      sections: [
        { label: 'Location', value: 'Greyfen Basin' },
        { label: 'Dynasty', value: 'House Thornwall' },
        { label: 'Mule Source', value: 'Siege of Greyfen' },
        { label: 'Mule Turns Left', value: '11' },
        { label: 'Artifact', value: 'Seal of Alder Moot' },
      ],
      pressures: [
        'Hold Thornwall succession bloc',
        'Protect Kestrel grain convoys',
        'Avoid clerical fracture after the schism',
      ],
      needs: [
        { name: 'Security', value: 0.82 },
        { name: 'Belonging', value: 0.65 },
        { name: 'Esteem', value: 0.71 },
        { name: 'Legacy', value: 0.58 },
      ],
    },
    trade: {
      title: 'Amber Corridor',
      subtitle: 'Trade Route Diagnostics',
      stableId: 'RT-018',
      sections: [
        { label: 'Route Profit', value: '126k / turn' },
        { label: 'Route Margin', value: '18.4%' },
        { label: 'Stale Belief', value: '0.91' },
        { label: 'Current Belief', value: '1.04' },
        { label: 'In Transit', value: 'grain, saffron, worked iron' },
        { label: 'Confidence', value: '0.82' },
        { label: 'Freshness', value: '3 turns' },
      ],
      market: {
        name: 'Greyfen Basin',
        supplyDemand: '1.18 / 0.92',
        stockpileTrend: 'rising 6 turns',
        foodSufficiency: '0.94',
        importShare: '42%',
        tradeDependency: '38%',
        role: 'river hinge / redistribution',
      },
    },
    campaign: {
      title: 'III Thornwall Field Army',
      subtitle: 'Campaign Status',
      stableId: 'AR-022',
      sections: [
        { label: 'Morale', value: '0.62' },
        { label: 'Supply', value: '19 days' },
        { label: 'Occupied Regions', value: '2 contested, 1 held' },
        { label: 'Casualties', value: '1,840' },
        { label: 'Freshness', value: '2 turns' },
        { label: 'Staleness', value: '14%' },
        { label: 'Confidence', value: '0.78' },
        { label: 'Familiarity', value: '0.84' },
      ],
      target: 'Hold Saint\'s Ford before Salt Step cavalry reaches the orchard road',
      lastBattle: 'Defensive victory at Greyfen Ford',
    },
  },

  // --- Validation ribbon checks ---
  validation: [
    { label: 'Determinism',            status: 'pass' },
    { label: 'Perf Baseline',          status: 'pass' },
    { label: 'Trade Baseline',         status: 'warn' },
    { label: 'Settlement Plausibility', status: 'pass' },
    { label: 'Pattern Oracle',         status: 'oracle', value: '0.91' },
  ],

  // --- Batch results ---
  batch: [
    { rank: 1, seed: '4ASF-9B1D-7C6E', score: 0.73, wars: 12, collapses: 3, namedEvents: 18, techMovement: 'late iron drift',   anomalies: 'schism + convoy cascade' },
    { rank: 2, seed: '5CQP-8K2E-1M4A', score: 0.68, wars: 9,  collapses: 2, namedEvents: 14, techMovement: 'river scripts',     anomalies: 'merchant lock-in' },
    { rank: 3, seed: '9YTR-3L8M-2J5H', score: 0.64, wars: 14, collapses: 4, namedEvents: 16, techMovement: 'frontier steel',    anomalies: 'oracle drift spike' },
    { rank: 4, seed: '2HTA-0B9V-3S8P', score: 0.58, wars: 7,  collapses: 1, namedEvents: 11, techMovement: 'grain mills',       anomalies: 'settlement overhang' },
    { rank: 5, seed: '7MNR-4F2K-8Q1L', score: 0.54, wars: 10, collapses: 2, namedEvents: 12, techMovement: 'cavalry reform',    anomalies: 'none' },
    { rank: 6, seed: '3BWX-6J7P-0D9T', score: 0.51, wars: 8,  collapses: 3, namedEvents: 9,  techMovement: 'copper depletion',  anomalies: 'migration surge' },
    { rank: 7, seed: '8VCZ-1A5N-4R6E', score: 0.47, wars: 6,  collapses: 1, namedEvents: 7,  techMovement: 'trade scripts',     anomalies: 'none' },
    { rank: 8, seed: '6GYH-9S3W-2K0M', score: 0.42, wars: 5,  collapses: 0, namedEvents: 6,  techMovement: 'irrigation reform', anomalies: 'stagnation cycle' },
  ],
};
```

- [ ] **Step 2: Verify file created**

Run: `ls -la prototype/cici/data.js`
Expected: file exists

---

## Task 3: HTML Shell Structure

**Teammate:** `foundations`
**Files:** Create `prototype/cici/index.html`

This is the canonical HTML that all other files build against. Four app states: setup, progress, viewer, batch. The viewer state contains the unified shell. Script and stylesheet loading order matters.

- [ ] **Step 1: Create index.html**

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Chronicler 7.5 — Phase 7.5 Shell Prototype</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,400;0,600;0,700;1,400&family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="tokens.css">
  <link rel="stylesheet" href="layout.css">
  <link rel="stylesheet" href="states.css">
  <link rel="stylesheet" href="components.css">
  <link rel="stylesheet" href="map.css">
</head>
<body>

  <!-- ===== APP STATE: SETUP ===== -->
  <div id="state-setup" class="app-state active">
    <div class="setup-container">
      <aside class="setup-sidebar">
        <div class="setup-logo-area">
          <h1 class="logo-text">Chronicler</h1>
          <span class="version-pill">v7.5</span>
        </div>
        <nav class="setup-nav">
          <a class="setup-nav-item active" data-section="new-world">New World</a>
          <a class="setup-nav-item" data-section="batch-lab" id="nav-batch-lab">Batch Lab</a>
          <a class="setup-nav-item" data-section="recent">Recent Worlds</a>
          <a class="setup-nav-item" data-section="settings">Settings</a>
        </nav>
        <div class="setup-footer-meta">
          <div>Schema v7.5.12</div>
          <div>Engine 4.1.0</div>
        </div>
      </aside>
      <main class="setup-main">
        <div class="setup-form-area">
          <h2 class="setup-heading">New World</h2>
          <div class="setup-form-grid">
            <div class="form-section">
              <h3 class="form-section-title">World Configuration</h3>
              <div class="form-group">
                <label class="form-label">Scenario</label>
                <div class="select-wrap">
                  <select id="input-scenario" class="form-select">
                    <option selected>Migration Era Decay</option>
                    <option>Bronze Age Collapse</option>
                    <option>Renaissance Divergence</option>
                    <option>Steppe Domination</option>
                  </select>
                </div>
              </div>
              <div class="form-group">
                <label class="form-label">Generation</label>
                <div class="toggle-group">
                  <button class="toggle-btn active" data-value="procedural">Procedural</button>
                  <button class="toggle-btn" data-value="scenario">Scenario</button>
                </div>
              </div>
              <div class="form-group">
                <label class="form-label">Seed</label>
                <div class="input-with-action">
                  <input type="text" class="form-input mono" id="input-seed" value="4ASF-9B1D-7C6E" readonly>
                  <button class="btn-icon" title="Randomize seed">&#x27F3;</button>
                </div>
              </div>
            </div>
            <div class="form-section">
              <h3 class="form-section-title">Scale</h3>
              <div class="form-group">
                <label class="form-label">Turns <span class="form-value" id="val-turns">5,000</span></label>
                <input type="range" class="form-range" id="input-turns" min="500" max="10000" value="5000" step="100">
              </div>
              <div class="form-group">
                <label class="form-label">Civilizations <span class="form-value" id="val-civs">5</span></label>
                <input type="range" class="form-range" id="input-civs" min="2" max="12" value="5">
              </div>
              <div class="form-group">
                <label class="form-label">Regions <span class="form-value" id="val-regions">24</span></label>
                <input type="range" class="form-range" id="input-regions" min="8" max="64" value="24">
              </div>
            </div>
            <div class="form-section">
              <h3 class="form-section-title">Narration</h3>
              <div class="form-group">
                <label class="form-label">Narration Mode</label>
                <div class="toggle-group triple">
                  <button class="toggle-btn" data-value="off">Off</button>
                  <button class="toggle-btn active" data-value="local">Local</button>
                  <button class="toggle-btn" data-value="api">API</button>
                </div>
              </div>
            </div>
          </div>
          <div class="setup-actions">
            <button class="btn-secondary">Import Bundle</button>
            <button class="btn-primary" id="btn-run-world">
              <span class="btn-icon-left">&#9654;</span> Run World
            </button>
          </div>
        </div>
        <div class="setup-preview">
          <canvas id="setup-preview-map" width="440" height="320"></canvas>
          <div class="scenario-description">
            <h4 class="scenario-title">Migration Era Decay</h4>
            <p class="scenario-text">Five civilizations contest a fragmenting continent as environmental pressure drives mass migration and political collapse. Trade networks strain under competing loyalties while border regions face cascading instability.</p>
            <div class="scenario-tags">
              <span class="tag">Ecological Pressure</span>
              <span class="tag">Migration</span>
              <span class="tag">Trade Disruption</span>
              <span class="tag">Political Fragmentation</span>
            </div>
          </div>
        </div>
      </main>
    </div>
  </div>

  <!-- ===== APP STATE: PROGRESS ===== -->
  <div id="state-progress" class="app-state">
    <div class="progress-container">
      <div class="progress-header">
        <h1 class="logo-text">Chronicler</h1>
        <span class="version-pill">v7.5</span>
      </div>
      <div class="progress-card">
        <h2 class="progress-title">Simulating World</h2>
        <div class="progress-world-name">Aethelgard Reborn</div>
        <div class="progress-meta-row">
          <span>Seed: <strong class="mono">4ASF-9B1D-7C6E</strong></span>
          <span>Scenario: <strong>Migration Era Decay</strong></span>
          <span>Civilizations: <strong>5</strong></span>
        </div>
        <div class="progress-bar-wrap">
          <div class="progress-bar"><div class="progress-bar-fill" id="sim-progress-fill"></div></div>
          <div class="progress-stats">
            <span id="progress-turn">Turn 0 / 5,000</span>
            <span id="progress-speed">&mdash; ms/turn</span>
          </div>
        </div>
        <div class="progress-indicators">
          <div class="progress-indicator">
            <div class="indicator-label">Simulation</div>
            <div class="indicator-status running" id="ind-sim">Running</div>
          </div>
          <div class="progress-indicator">
            <div class="indicator-label">Narration</div>
            <div class="indicator-status pending" id="ind-narr">Pending</div>
          </div>
          <div class="progress-indicator">
            <div class="indicator-label">Bundle</div>
            <div class="indicator-status pending" id="ind-bundle">Pending</div>
          </div>
          <div class="progress-indicator">
            <div class="indicator-label">Interestingness</div>
            <div class="indicator-value" id="ind-interest">&mdash;</div>
          </div>
        </div>
        <div class="progress-log" id="progress-log">
          <div class="log-line">Initializing world state&hellip;</div>
        </div>
      </div>
    </div>
  </div>

  <!-- ===== APP STATE: VIEWER (unified shell) ===== -->
  <div id="state-viewer" class="app-state">
    <!-- Header -->
    <header id="viewer-header">
      <div class="header-section header-left">
        <span class="header-logo">Chronicler</span>
        <span class="header-divider"></span>
        <span class="header-world" id="header-world">Aethelgard Reborn</span>
        <span class="header-scenario" id="header-scenario">Migration Era Decay</span>
      </div>
      <div class="header-section header-center">
        <div class="mode-tabs" id="mode-tabs">
          <button class="mode-tab active" data-mode="overview">Overview</button>
          <button class="mode-tab" data-mode="character">Character</button>
          <button class="mode-tab" data-mode="trade">Trade</button>
          <button class="mode-tab" data-mode="campaign">Campaign</button>
        </div>
      </div>
      <div class="header-section header-right">
        <div class="header-meta">
          <span class="meta-item">Seed <strong class="mono" id="header-seed">4ASF-9B1D-7C6E</strong></span>
          <span class="meta-divider"></span>
          <span class="meta-item">Schema <strong id="header-schema">v7.5.12</strong></span>
          <span class="meta-divider"></span>
          <span class="meta-item perf"><span class="perf-dot"></span><strong id="header-perf">14.2</strong> ms/turn</span>
        </div>
        <span class="mode-badge">ARCHIVE</span>
      </div>
    </header>

    <!-- Validation Ribbon (campaign mode only) -->
    <div id="validation-ribbon" class="validation-ribbon hidden"></div>

    <!-- Timeline Rail -->
    <div id="timeline-rail">
      <div class="timeline-container">
        <div class="timeline-track" id="timeline-track">
          <div class="timeline-eras" id="timeline-eras"></div>
          <div class="timeline-events" id="timeline-events"></div>
          <div class="timeline-narrated" id="timeline-narrated"></div>
          <div class="timeline-playhead" id="timeline-playhead">
            <div class="playhead-line"></div>
            <div class="playhead-label" id="playhead-label">T3812</div>
          </div>
        </div>
        <div class="timeline-labels" id="timeline-labels"></div>
      </div>
    </div>

    <!-- Workspace (3-column: left-rail | map-column | right-rail) -->
    <div id="workspace">
      <!-- Left Rail -->
      <aside id="left-rail">
        <div class="rail-tabs">
          <button class="rail-tab active" data-tab="chronicle">Chronicle</button>
          <button class="rail-tab" data-tab="events">Event Log</button>
        </div>
        <div class="rail-toolbar">
          <span class="tiny-label">Narrative Context</span>
          <span class="rail-toolbar-title" id="left-rail-title">Chronicle of Aethelgard</span>
        </div>
        <div class="rail-scroller" id="left-rail-content"></div>
      </aside>

      <!-- Map Column -->
      <section id="map-column">
        <div class="viewport-toolbar">
          <div class="viewport-heading">
            <span class="tiny-label" id="viewport-kicker">Strategic Overview</span>
            <span class="viewport-title" id="viewport-title">Map-first workspace with overlay control</span>
          </div>
          <div class="layer-chips" id="layer-chips">
            <button class="layer-chip active" data-layer="borders">Borders</button>
            <button class="layer-chip active" data-layer="settlements">Settlements</button>
            <button class="layer-chip" data-layer="trade">Trade</button>
            <button class="layer-chip" data-layer="campaign">Campaign</button>
            <button class="layer-chip" data-layer="fog">Knowledge Fog</button>
            <button class="layer-chip" data-layer="asabiya">Asabiya</button>
          </div>
        </div>
        <div id="map-viewport">
          <canvas id="main-map"></canvas>
          <div class="map-controls" id="map-controls">
            <button class="map-ctrl" id="map-zoom-in" title="Zoom In">+</button>
            <button class="map-ctrl" id="map-zoom-out" title="Zoom Out">&minus;</button>
            <button class="map-ctrl" id="map-reset" title="Reset View">&#8962;</button>
          </div>
          <div class="map-legend" id="map-legend"></div>
          <div class="map-hover-card" id="map-hover-card"></div>
        </div>
      </section>

      <!-- Right Rail (Inspector) -->
      <aside id="right-rail">
        <div class="inspector-header">
          <span class="tiny-label" id="inspector-kicker">Civilization</span>
          <div class="inspector-title" id="inspector-title">Thornwall March</div>
          <div class="inspector-subtitle" id="inspector-subtitle">Strategic overview at T3812</div>
        </div>
        <div class="inspector-body" id="inspector-body"></div>
      </aside>
    </div>
  </div>

  <!-- ===== APP STATE: BATCH LAB ===== -->
  <div id="state-batch" class="app-state">
    <div class="setup-container">
      <aside class="setup-sidebar">
        <div class="setup-logo-area">
          <h1 class="logo-text">Chronicler</h1>
          <span class="version-pill">v7.5</span>
        </div>
        <nav class="setup-nav">
          <a class="setup-nav-item" data-section="new-world" id="batch-nav-new">New World</a>
          <a class="setup-nav-item active" data-section="batch-lab">Batch Lab</a>
          <a class="setup-nav-item" data-section="recent">Recent Worlds</a>
          <a class="setup-nav-item" data-section="settings">Settings</a>
        </nav>
        <div class="setup-footer-meta">
          <div>Schema v7.5.12</div>
          <div>Engine 4.1.0</div>
        </div>
      </aside>
      <main class="batch-main">
        <div class="batch-header-bar">
          <h2 class="setup-heading">Batch Lab</h2>
          <div class="batch-summary">
            <span class="batch-stat">200 seeds completed</span>
            <span class="batch-stat">Scenario: <strong>Migration Era Decay</strong></span>
            <span class="batch-stat">Avg Interestingness: <strong>0.51</strong></span>
          </div>
        </div>
        <div class="batch-toolbar">
          <div class="batch-filters">
            <button class="filter-chip active">All</button>
            <button class="filter-chip">Wars &ge; 3</button>
            <button class="filter-chip">Collapses</button>
            <button class="filter-chip">Anomalies</button>
          </div>
          <button class="btn-secondary btn-sm">Compare Selected</button>
        </div>
        <div class="batch-table-wrap">
          <table class="batch-table">
            <thead>
              <tr>
                <th>#</th>
                <th>Seed</th>
                <th>Score</th>
                <th>Wars</th>
                <th>Collapses</th>
                <th>Named Events</th>
                <th>Tech Mv.</th>
                <th>Anomalies</th>
                <th></th>
              </tr>
            </thead>
            <tbody id="batch-table-body"></tbody>
          </table>
        </div>
      </main>
    </div>
  </div>

  <!-- ===== DEMO CONTROLS ===== -->
  <div id="demo-controls">
    <button class="demo-btn" id="btn-auto-demo" title="Play automated walkthrough">&#9654; Demo</button>
    <button class="demo-btn" id="btn-pause-demo" title="Pause demo" style="display:none">&#9646;&#9646; Pause</button>
    <div class="demo-jumps" id="demo-jumps">
      <button class="jump-btn" data-jump="setup">Setup</button>
      <button class="jump-btn" data-jump="progress">Progress</button>
      <button class="jump-btn" data-jump="overview">Overview</button>
      <button class="jump-btn" data-jump="character">Character</button>
      <button class="jump-btn" data-jump="trade">Trade</button>
      <button class="jump-btn" data-jump="campaign">Campaign</button>
      <button class="jump-btn" data-jump="batch">Batch</button>
    </div>
  </div>

  <!-- Scripts (order matters: data first, then state, then rendering, then interaction) -->
  <script src="data.js"></script>
  <script src="state.js"></script>
  <script src="timeline.js"></script>
  <script src="map.js"></script>
  <script src="rails.js"></script>
  <script src="setup.js"></script>
  <script src="batch.js"></script>
  <script src="demo.js"></script>
</body>
</html>
```

- [ ] **Step 2: Verify file created**

Run: `ls -la prototype/cici/index.html`
Expected: file exists

---

## Task 4: Shell Layout Styles

**Teammate:** `styles`
**Files:** Create `prototype/cici/layout.css`

Grid layout for the viewer shell. References only token custom properties from `tokens.css`. Key dimensions: header 42px, timeline 52px, left rail 260px, right inspector 310px, map fills remainder.

- [ ] **Step 1: Create layout.css**

```css
/* ============================================================
   Shell Layout — Header, Timeline, Workspace Grid
   ============================================================ */

/* --- App states --- */
.app-state {
  position: absolute; inset: 0;
  display: flex; flex-direction: column;
  opacity: 0; pointer-events: none;
  transition: opacity 0.4s ease;
}
.app-state.active {
  opacity: 1; pointer-events: auto;
  z-index: 1;
}

/* --- Viewer header --- */
#viewer-header {
  height: var(--header-height);
  display: grid;
  grid-template-columns: 1fr auto 1fr;
  align-items: center;
  padding: 0 16px;
  background: var(--bg-deep);
  border-bottom: 1px solid var(--chrome-border);
  z-index: 10;
}

.header-section { display: flex; align-items: center; gap: 10px; }
.header-left { justify-self: start; }
.header-center { justify-self: center; }
.header-right { justify-self: end; }

.header-logo {
  font-family: var(--font-heading);
  font-size: 16px; font-weight: 700;
  color: var(--text-heading);
  letter-spacing: 0.02em;
}
.header-divider {
  width: 1px; height: 18px;
  background: var(--chrome-gold-dim);
}
.header-world {
  font-family: var(--font-heading);
  font-size: 14px; font-weight: 600;
  color: var(--text-primary);
}
.header-scenario {
  font-size: 11px; color: var(--text-tertiary);
}

.header-meta {
  display: flex; align-items: center; gap: 8px;
  font-size: 11px; color: var(--text-secondary);
}
.meta-item strong { color: var(--text-primary); }
.meta-divider {
  width: 1px; height: 12px;
  background: var(--chrome-border-light);
}
.perf-dot {
  display: inline-block;
  width: 6px; height: 6px; border-radius: 50%;
  background: var(--status-green);
  margin-right: 4px; vertical-align: middle;
}

.mode-badge {
  font-family: var(--font-mono);
  font-size: 9px; font-weight: 600;
  letter-spacing: 0.12em;
  padding: 3px 8px;
  border: 1px solid var(--chrome-gold-dim);
  border-radius: 3px;
  color: var(--chrome-gold);
  margin-left: 10px;
}

/* --- Validation ribbon --- */
.validation-ribbon {
  height: var(--ribbon-height);
  display: flex; align-items: center;
  gap: 12px; padding: 0 16px;
  background: var(--bg-surface);
  border-bottom: 1px solid var(--chrome-border);
  font-size: 11px;
}
.validation-ribbon.hidden { display: none; }

/* --- Timeline rail --- */
#timeline-rail {
  height: var(--timeline-height);
  background: var(--bg-deep);
  border-bottom: 1px solid var(--chrome-border);
  padding: 0 16px;
  display: flex; align-items: center;
}
.timeline-container { flex: 1; position: relative; }
.timeline-track {
  position: relative; height: 28px;
  cursor: pointer;
}
.timeline-eras {
  position: absolute; inset: 0;
  display: flex;
}
.timeline-events { position: absolute; inset: 0; pointer-events: none; }
.timeline-narrated { position: absolute; inset: 0; pointer-events: none; }
.timeline-labels {
  display: flex; justify-content: space-between;
  font-size: 9px; color: var(--text-tertiary);
  margin-top: 2px;
  font-family: var(--font-mono);
}

/* --- Workspace grid --- */
#workspace {
  flex: 1; display: grid;
  grid-template-columns: var(--rail-width) 1fr var(--inspector-width);
  overflow: hidden;
}

/* --- Left rail --- */
#left-rail {
  display: flex; flex-direction: column;
  background: var(--bg-deep);
  border-right: 1px solid var(--chrome-border);
  overflow: hidden;
}
.rail-tabs {
  display: flex;
  border-bottom: 1px solid var(--chrome-border);
}
.rail-toolbar {
  padding: 8px 12px;
  border-bottom: 1px solid var(--chrome-border);
  display: flex; flex-direction: column; gap: 2px;
}
.rail-toolbar-title {
  font-family: var(--font-heading);
  font-size: 13px; font-weight: 600;
  color: var(--text-primary);
}
.rail-scroller {
  flex: 1; overflow-y: auto;
  padding: 8px 12px;
}

/* --- Map column --- */
#map-column {
  display: flex; flex-direction: column;
  overflow: hidden;
}
.viewport-toolbar {
  display: flex; align-items: center;
  justify-content: space-between;
  padding: 6px 12px;
  background: var(--bg-surface);
  border-bottom: 1px solid var(--chrome-border);
  gap: 12px;
}
.viewport-heading { display: flex; flex-direction: column; gap: 1px; }
.viewport-title {
  font-size: 12px; color: var(--text-secondary);
}

/* --- Map viewport --- */
#map-viewport {
  flex: 1; position: relative;
  background: var(--map-water);
  overflow: hidden;
}
#main-map {
  position: absolute; inset: 0;
  width: 100%; height: 100%;
}

/* --- Right rail (inspector) --- */
#right-rail {
  display: flex; flex-direction: column;
  background: var(--bg-deep);
  border-left: 1px solid var(--chrome-border);
  overflow: hidden;
}
.inspector-header {
  padding: 12px 14px;
  border-bottom: 1px solid var(--chrome-border);
  display: flex; flex-direction: column; gap: 3px;
}
.inspector-title {
  font-family: var(--font-heading);
  font-size: 16px; font-weight: 600;
  color: var(--text-heading);
}
.inspector-subtitle {
  font-size: 11px; color: var(--text-secondary);
}
.inspector-body {
  flex: 1; overflow-y: auto;
  padding: 10px 14px;
}

/* --- Demo controls --- */
#demo-controls {
  position: fixed; bottom: 16px; right: 16px;
  display: flex; align-items: center; gap: 8px;
  z-index: 100;
  background: var(--bg-raised);
  border: 1px solid var(--chrome-border-light);
  border-radius: 8px;
  padding: 6px 10px;
}
.demo-jumps { display: flex; gap: 4px; }
```

- [ ] **Step 2: Verify file created**

Run: `ls -la prototype/cici/layout.css`
Expected: file exists

---

## Task 5: App State Styles

**Teammate:** `styles`
**Files:** Create `prototype/cici/states.css`

Styles for the setup sidebar/form, progress card, and batch table. These are the non-viewer app states.

- [ ] **Step 1: Create states.css**

```css
/* ============================================================
   App State Styles — Setup, Progress, Batch
   ============================================================ */

/* --- Setup container --- */
.setup-container {
  display: flex; width: 100%; height: 100%;
  background: var(--bg-deep);
}

.setup-sidebar {
  width: 200px; min-width: 200px;
  background: var(--bg-deepest);
  border-right: 1px solid var(--chrome-border);
  display: flex; flex-direction: column;
  padding: 24px 0;
}
.setup-logo-area {
  padding: 0 20px 24px;
  border-bottom: 1px solid var(--chrome-gold-dim);
  display: flex; align-items: baseline; gap: 8px;
}
.logo-text {
  font-family: var(--font-heading);
  font-size: 22px; font-weight: 700;
  color: var(--text-heading);
  letter-spacing: 0.02em;
}
.version-pill {
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--chrome-gold);
  background: rgba(157, 138, 94, 0.12);
  padding: 2px 6px; border-radius: 3px;
  letter-spacing: 0.05em;
}

.setup-nav {
  flex: 1; padding: 16px 0;
  display: flex; flex-direction: column; gap: 2px;
}
.setup-nav-item {
  display: block; padding: 8px 20px;
  color: var(--text-secondary);
  text-decoration: none; cursor: pointer;
  font-size: 13px; font-weight: 500;
  border-left: 2px solid transparent;
  transition: all 0.2s;
}
.setup-nav-item:hover { color: var(--text-primary); background: var(--bg-hover); }
.setup-nav-item.active {
  color: var(--accent-cyan);
  border-left-color: var(--accent-cyan);
  background: var(--accent-cyan-glow);
}
.setup-footer-meta {
  padding: 16px 20px 0;
  border-top: 1px solid var(--chrome-border);
  font-size: 11px; color: var(--text-tertiary);
  display: flex; flex-direction: column; gap: 4px;
}

.setup-main {
  flex: 1; display: flex;
  padding: 32px 40px; gap: 40px;
  overflow-y: auto;
}
.setup-form-area { flex: 1; min-width: 340px; max-width: 500px; }
.setup-heading {
  font-size: 26px; margin-bottom: 28px;
  color: var(--text-heading);
}
.setup-form-grid { display: flex; flex-direction: column; gap: 24px; }

.setup-preview {
  flex: 1; min-width: 300px; max-width: 460px;
  display: flex; flex-direction: column; gap: 20px;
}
#setup-preview-map {
  width: 100%; height: auto; max-height: 320px;
  border-radius: 6px; border: 1px solid var(--chrome-border);
  background: var(--map-water);
}
.scenario-description {
  background: var(--bg-surface);
  border: 1px solid var(--chrome-border);
  border-radius: 6px; padding: 16px;
}
.scenario-title {
  font-size: 16px; margin-bottom: 8px;
  color: var(--chrome-gold-bright);
  font-family: var(--font-heading);
}
.scenario-text { font-size: 12.5px; color: var(--text-secondary); line-height: 1.55; margin-bottom: 12px; }
.scenario-tags { display: flex; flex-wrap: wrap; gap: 6px; }

.setup-actions {
  display: flex; gap: 12px; margin-top: 28px;
  justify-content: flex-end;
}

/* --- Progress container --- */
.progress-container {
  flex: 1; display: flex; flex-direction: column;
  align-items: center; justify-content: center;
  background: var(--bg-deep);
}
.progress-header {
  display: flex; align-items: baseline; gap: 8px;
  margin-bottom: 40px;
}
.progress-card {
  width: 520px; max-width: 90vw;
  background: var(--bg-surface);
  border: 1px solid var(--chrome-border);
  border-radius: 8px; padding: 32px;
}
.progress-title {
  font-size: 12px; font-family: var(--font-ui);
  text-transform: uppercase; letter-spacing: 0.1em;
  color: var(--text-tertiary); font-weight: 600;
  margin-bottom: 4px;
}
.progress-world-name {
  font-family: var(--font-heading);
  font-size: 24px; color: var(--text-heading);
  margin-bottom: 16px;
}
.progress-meta-row {
  display: flex; gap: 16px; flex-wrap: wrap;
  font-size: 12px; color: var(--text-secondary);
  margin-bottom: 24px;
}
.progress-meta-row strong { color: var(--text-primary); }

.progress-bar-wrap { margin-bottom: 20px; }
.progress-bar {
  height: 6px; background: var(--bg-raised);
  border-radius: 3px; overflow: hidden;
  border: 1px solid var(--chrome-border);
}
.progress-bar-fill {
  height: 100%; width: 0%;
  background: linear-gradient(90deg, var(--accent-cyan-dim), var(--accent-cyan));
  border-radius: 3px;
  transition: width 0.15s linear;
}
.progress-stats {
  display: flex; justify-content: space-between;
  font-size: 11px; color: var(--text-tertiary);
  margin-top: 6px;
}

.progress-indicators {
  display: grid; grid-template-columns: repeat(4, 1fr);
  gap: 12px; margin-bottom: 20px;
}
.progress-indicator { text-align: center; }
.indicator-label {
  font-size: 10px; text-transform: uppercase;
  letter-spacing: 0.08em; color: var(--text-tertiary);
  margin-bottom: 4px;
}
.indicator-status, .indicator-value {
  font-size: 12px; font-weight: 600;
  padding: 3px 8px; border-radius: 4px;
  display: inline-block;
}
.indicator-status.running { color: var(--accent-cyan); background: var(--accent-cyan-glow); }
.indicator-status.pending { color: var(--text-tertiary); background: var(--bg-raised); }
.indicator-status.done { color: var(--status-green); background: var(--status-green-bg); }
.indicator-value { color: var(--text-secondary); }

.progress-log {
  max-height: 120px; overflow-y: auto;
  background: var(--bg-raised);
  border: 1px solid var(--chrome-border);
  border-radius: 4px; padding: 8px 10px;
  font-family: var(--font-mono);
  font-size: 11px; color: var(--text-tertiary);
  line-height: 1.6;
}
.log-line { white-space: nowrap; }

/* --- Batch main --- */
.batch-main {
  flex: 1; display: flex; flex-direction: column;
  padding: 24px 32px;
  overflow-y: auto;
}
.batch-header-bar {
  display: flex; align-items: baseline;
  justify-content: space-between;
  margin-bottom: 16px;
}
.batch-summary {
  display: flex; gap: 16px;
  font-size: 12px; color: var(--text-secondary);
}
.batch-summary strong { color: var(--text-primary); }

.batch-toolbar {
  display: flex; justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.batch-filters { display: flex; gap: 6px; }

.batch-table-wrap { flex: 1; overflow-y: auto; }
.batch-table {
  width: 100%; border-collapse: collapse;
  font-size: 12px;
}
.batch-table th {
  text-align: left;
  padding: 8px 10px;
  background: var(--bg-surface);
  border-bottom: 1px solid var(--chrome-border);
  color: var(--text-tertiary);
  font-weight: 600;
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  position: sticky; top: 0;
}
.batch-table td {
  padding: 8px 10px;
  border-bottom: 1px solid var(--chrome-border);
  color: var(--text-secondary);
}
.batch-table tr:hover td {
  background: var(--bg-hover);
  color: var(--text-primary);
}
.batch-table .score-cell {
  font-family: var(--font-mono);
  font-weight: 600;
  color: var(--accent-cyan);
}
.batch-table .seed-cell { font-family: var(--font-mono); }
.batch-open-btn {
  font-size: 11px; padding: 3px 10px;
  background: transparent;
  border: 1px solid var(--chrome-border-light);
  color: var(--text-secondary);
  border-radius: 3px; cursor: pointer;
  transition: all 0.2s;
}
.batch-open-btn:hover {
  border-color: var(--accent-cyan-dim);
  color: var(--accent-cyan);
}
```

- [ ] **Step 2: Verify file created**

Run: `ls -la prototype/cici/states.css`
Expected: file exists

---

## Task 6: Component Styles

**Teammate:** `styles`
**Files:** Create `prototype/cici/components.css`

Reusable component styles: buttons, tabs, form controls, cards, badges, inspector pieces. These are shared across all app states.

- [ ] **Step 1: Create components.css**

```css
/* ============================================================
   Component Styles — Buttons, Tabs, Forms, Cards, Badges
   ============================================================ */

/* --- Form elements --- */
.form-section-title {
  font-family: var(--font-ui);
  font-size: 10px; font-weight: 600;
  text-transform: uppercase; letter-spacing: 0.1em;
  color: var(--chrome-gold);
  margin-bottom: 12px; padding-bottom: 6px;
  border-bottom: 1px solid var(--chrome-gold-dim);
}
.form-group {
  margin-bottom: 14px;
  display: flex; flex-direction: column; gap: 5px;
}
.form-label {
  font-size: 12px; font-weight: 500;
  color: var(--text-secondary);
  display: flex; align-items: center; justify-content: space-between;
}
.form-value {
  font-family: var(--font-mono); font-size: 12px;
  color: var(--accent-cyan);
}

.select-wrap { position: relative; }
.form-select {
  width: 100%; padding: 7px 10px;
  background: var(--bg-raised); border: 1px solid var(--chrome-border);
  color: var(--text-primary); border-radius: 4px;
  font-family: var(--font-ui); font-size: 13px;
  appearance: none; cursor: pointer;
  transition: border-color 0.2s;
}
.form-select:focus { outline: none; border-color: var(--accent-cyan-dim); }
.select-wrap::after {
  content: '\25BE'; position: absolute; right: 10px; top: 50%;
  transform: translateY(-50%);
  color: var(--text-tertiary); pointer-events: none; font-size: 11px;
}

.form-input {
  width: 100%; padding: 7px 10px;
  background: var(--bg-raised); border: 1px solid var(--chrome-border);
  color: var(--text-primary); border-radius: 4px;
  font-family: var(--font-ui); font-size: 13px;
  transition: border-color 0.2s;
}
.form-input:focus { outline: none; border-color: var(--accent-cyan-dim); }

.input-with-action { display: flex; gap: 6px; align-items: stretch; }
.input-with-action .form-input { flex: 1; }

.form-range {
  width: 100%; height: 4px;
  -webkit-appearance: none; appearance: none;
  background: var(--chrome-border);
  border-radius: 2px; outline: none; cursor: pointer;
}
.form-range::-webkit-slider-thumb {
  -webkit-appearance: none; appearance: none;
  width: 14px; height: 14px; border-radius: 50%;
  background: var(--accent-cyan); border: 2px solid var(--bg-deep);
  cursor: pointer;
}

/* --- Toggle groups --- */
.toggle-group {
  display: flex; gap: 0;
  border: 1px solid var(--chrome-border); border-radius: 4px;
  overflow: hidden;
}
.toggle-btn {
  flex: 1; padding: 6px 12px;
  background: var(--bg-raised); border: none;
  color: var(--text-secondary); cursor: pointer;
  font-family: var(--font-ui); font-size: 12px; font-weight: 500;
  transition: all 0.2s;
  border-right: 1px solid var(--chrome-border);
}
.toggle-btn:last-child { border-right: none; }
.toggle-btn:hover { background: var(--bg-hover); color: var(--text-primary); }
.toggle-btn.active {
  background: var(--accent-cyan-dim);
  color: var(--accent-cyan-bright);
}

/* --- Buttons --- */
.btn-primary {
  padding: 10px 24px;
  background: linear-gradient(135deg, var(--accent-cyan-dim), var(--accent-cyan));
  border: 1px solid var(--accent-cyan);
  color: #fff; border-radius: 5px;
  font-family: var(--font-ui); font-size: 14px; font-weight: 600;
  cursor: pointer; display: flex; align-items: center; gap: 8px;
  transition: all 0.25s; letter-spacing: 0.02em;
}
.btn-primary:hover {
  background: linear-gradient(135deg, var(--accent-cyan), var(--accent-cyan-bright));
  box-shadow: 0 0 20px rgba(74, 158, 187, 0.25);
}
.btn-secondary {
  padding: 10px 20px;
  background: transparent;
  border: 1px solid var(--chrome-border-light);
  color: var(--text-secondary); border-radius: 5px;
  font-family: var(--font-ui); font-size: 13px; font-weight: 500;
  cursor: pointer; transition: all 0.2s;
}
.btn-secondary:hover { border-color: var(--text-secondary); color: var(--text-primary); }
.btn-sm { padding: 6px 14px; font-size: 12px; }
.btn-icon {
  width: 34px; display: flex; align-items: center; justify-content: center;
  background: var(--bg-raised); border: 1px solid var(--chrome-border);
  color: var(--text-secondary); border-radius: 4px;
  cursor: pointer; font-size: 16px; transition: all 0.2s;
}
.btn-icon:hover { color: var(--accent-cyan); border-color: var(--accent-cyan-dim); }
.btn-icon-left { font-size: 11px; }

/* --- Tags and pills --- */
.tag {
  font-size: 10px; padding: 3px 8px;
  background: var(--bg-raised); border: 1px solid var(--chrome-border);
  border-radius: 3px; color: var(--text-label);
  letter-spacing: 0.03em;
}

/* --- Mode tabs --- */
.mode-tab {
  padding: 6px 14px;
  background: transparent; border: 1px solid var(--chrome-border);
  color: var(--text-secondary);
  border-radius: 4px; cursor: pointer;
  font-family: var(--font-ui); font-size: 12px; font-weight: 500;
  transition: all 0.2s;
}
.mode-tab:hover { color: var(--text-primary); border-color: var(--chrome-border-light); }
.mode-tab.active {
  color: var(--accent-cyan-bright);
  border-color: var(--accent-cyan);
  background: var(--accent-cyan-glow);
}
.mode-tabs { display: flex; gap: 4px; }

/* --- Rail tabs --- */
.rail-tab {
  flex: 1; padding: 7px 12px;
  background: var(--bg-surface); border: none;
  color: var(--text-secondary); cursor: pointer;
  font-family: var(--font-ui); font-size: 12px; font-weight: 500;
  transition: all 0.2s;
}
.rail-tab:hover { color: var(--text-primary); background: var(--bg-hover); }
.rail-tab.active {
  color: var(--accent-cyan);
  background: var(--bg-raised);
  border-bottom: 2px solid var(--accent-cyan);
}

/* --- Layer chips --- */
.layer-chips { display: flex; gap: 4px; flex-wrap: wrap; }
.layer-chip {
  padding: 4px 10px;
  background: transparent; border: 1px solid var(--chrome-border);
  color: var(--text-tertiary); border-radius: 3px;
  cursor: pointer; font-size: 11px; font-weight: 500;
  transition: all 0.2s;
}
.layer-chip:hover { color: var(--text-secondary); border-color: var(--chrome-border-light); }
.layer-chip.active {
  color: var(--accent-cyan);
  border-color: var(--accent-cyan-dim);
  background: var(--accent-cyan-glow);
}

/* --- Filter chips --- */
.filter-chip {
  padding: 5px 12px;
  background: var(--bg-raised); border: 1px solid var(--chrome-border);
  color: var(--text-secondary); border-radius: 4px;
  cursor: pointer; font-size: 12px; font-weight: 500;
  transition: all 0.2s;
}
.filter-chip:hover { color: var(--text-primary); border-color: var(--chrome-border-light); }
.filter-chip.active {
  color: var(--accent-cyan);
  border-color: var(--accent-cyan);
  background: var(--accent-cyan-glow);
}

/* --- Demo controls --- */
.demo-btn {
  padding: 5px 12px;
  background: var(--bg-surface); border: 1px solid var(--chrome-border-light);
  color: var(--text-secondary); border-radius: 4px;
  cursor: pointer; font-size: 12px;
  transition: all 0.2s;
}
.demo-btn:hover { color: var(--accent-cyan); border-color: var(--accent-cyan-dim); }

.jump-btn {
  padding: 3px 8px;
  background: transparent; border: 1px solid var(--chrome-border);
  color: var(--text-tertiary); border-radius: 3px;
  cursor: pointer; font-size: 10px;
  transition: all 0.2s;
}
.jump-btn:hover { color: var(--text-secondary); }
.jump-btn.active {
  color: var(--accent-cyan);
  border-color: var(--accent-cyan-dim);
}

/* --- Inspector cards --- */
.inspector-card {
  background: var(--bg-surface);
  border: 1px solid var(--chrome-border);
  border-radius: 6px;
  padding: 10px 12px;
  margin-bottom: 8px;
}
.inspector-card-title {
  font-size: 10px; font-weight: 600;
  text-transform: uppercase; letter-spacing: 0.08em;
  color: var(--chrome-gold);
  margin-bottom: 8px;
}

/* --- KPI rows --- */
.kpi-row {
  display: flex; justify-content: space-between;
  padding: 4px 0;
  border-bottom: 1px solid var(--chrome-border);
  font-size: 12px;
}
.kpi-row:last-child { border-bottom: none; }
.kpi-label { color: var(--text-secondary); }
.kpi-value { color: var(--text-primary); font-weight: 500; }

/* --- Distribution bars --- */
.dist-bar-wrap { margin-bottom: 10px; }
.dist-bar-label {
  font-size: 10px; font-weight: 600;
  text-transform: uppercase; letter-spacing: 0.06em;
  color: var(--text-tertiary);
  margin-bottom: 4px;
}
.dist-bar {
  display: flex; height: 6px;
  border-radius: 3px; overflow: hidden;
  background: var(--bg-raised);
}
.dist-bar-segment { height: 100%; transition: width 0.3s; }
.dist-bar-items {
  display: flex; gap: 8px; margin-top: 4px;
  font-size: 10px; color: var(--text-secondary);
}
.dist-bar-item { display: flex; align-items: center; gap: 4px; }
.dist-swatch {
  width: 8px; height: 8px; border-radius: 2px;
  display: inline-block;
}

/* --- Chronicle entries (left rail) --- */
.chronicle-entry {
  padding: 10px 0;
  border-bottom: 1px solid var(--chrome-border);
}
.chronicle-entry:last-child { border-bottom: none; }
.chronicle-entry-header {
  display: flex; align-items: center; gap: 6px;
  margin-bottom: 4px;
}
.chronicle-entry-tag {
  font-size: 9px; font-weight: 600;
  text-transform: uppercase; letter-spacing: 0.08em;
  padding: 2px 6px; border-radius: 2px;
}
.chronicle-entry-tag.era      { color: var(--chrome-gold); background: rgba(157,138,94,0.15); }
.chronicle-entry-tag.war      { color: var(--campaign-crimson-bright); background: rgba(138,64,64,0.15); }
.chronicle-entry-tag.faith    { color: #8a7bbf; background: rgba(138,123,191,0.12); }
.chronicle-entry-tag.collapse { color: var(--status-red); background: var(--status-red-bg); }
.chronicle-entry-tag.memory   { color: var(--accent-cyan); background: var(--accent-cyan-glow); }
.chronicle-entry-tag.arc      { color: var(--status-green); background: var(--status-green-bg); }
.chronicle-entry-tag.relationship { color: var(--status-amber); background: var(--status-amber-bg); }
.chronicle-entry-tag.dynasty  { color: var(--chrome-gold-bright); background: rgba(196,170,106,0.12); }
.chronicle-entry-tag.route    { color: var(--trade-gold); background: rgba(196,160,74,0.12); }
.chronicle-entry-tag.market   { color: var(--status-amber); background: var(--status-amber-bg); }
.chronicle-entry-tag.belief   { color: var(--accent-cyan); background: var(--accent-cyan-glow); }
.chronicle-entry-tag.army     { color: var(--campaign-crimson-bright); background: rgba(138,64,64,0.15); }
.chronicle-entry-tag.battle   { color: var(--status-red); background: var(--status-red-bg); }
.chronicle-entry-tag.knowledge { color: var(--accent-cyan); background: var(--accent-cyan-glow); }
.chronicle-entry-title {
  font-family: var(--font-heading);
  font-size: 13px; font-weight: 600;
  color: var(--text-heading);
}
.chronicle-entry-body {
  font-size: 12px; color: var(--text-secondary);
  line-height: 1.5; margin-top: 4px;
}

/* --- Event log rows (left rail) --- */
.event-row {
  display: flex; gap: 8px;
  padding: 5px 0;
  border-bottom: 1px solid var(--chrome-border);
  font-size: 11px;
}
.event-row:last-child { border-bottom: none; }
.event-turn {
  font-family: var(--font-mono);
  color: var(--text-tertiary);
  min-width: 42px;
  flex-shrink: 0;
}
.event-type-dot {
  width: 6px; height: 6px; border-radius: 50%;
  margin-top: 5px; flex-shrink: 0;
}
.event-type-dot.political  { background: var(--accent-cyan); }
.event-type-dot.military   { background: var(--campaign-crimson-bright); }
.event-type-dot.economic   { background: var(--trade-gold); }
.event-type-dot.religious  { background: #8a7bbf; }
.event-type-dot.cultural   { background: var(--chrome-gold-bright); }
.event-type-dot.promotion  { background: var(--status-green); }
.event-type-dot.relationship { background: var(--status-amber); }
.event-type-dot.memory     { background: var(--accent-cyan); }
.event-type-dot.embargo    { background: var(--status-red); }
.event-type-dot.volume     { background: var(--trade-gold); }
.event-type-dot.price      { background: var(--status-amber); }
.event-type-dot.stockpile  { background: var(--status-red); }
.event-type-dot.route      { background: var(--trade-gold-dim); }
.event-type-dot.strategic  { background: var(--accent-cyan-bright); }
.event-type-dot.movement   { background: var(--campaign-crimson); }
.event-type-dot.supply     { background: var(--status-amber); }
.event-type-dot.intel      { background: var(--accent-cyan-dim); }
.event-type-dot.battle     { background: var(--status-red); }
.event-text { color: var(--text-secondary); line-height: 1.4; }

/* --- Validation ribbon checks --- */
.val-check {
  display: flex; align-items: center; gap: 5px;
  font-size: 11px;
}
.val-icon { font-size: 12px; font-weight: 700; }
.val-check.pass .val-icon { color: var(--status-green); }
.val-check.pass .val-label { color: var(--text-secondary); }
.val-check.warn .val-icon { color: var(--status-amber); }
.val-check.warn .val-label { color: var(--status-amber); }
.val-check.oracle .val-icon { color: var(--accent-cyan); }
.val-check.oracle .val-label { color: var(--text-secondary); }
.val-value {
  font-family: var(--font-mono); font-weight: 600;
  color: var(--accent-cyan); margin-left: 4px;
}

/* --- Pressures list (character inspector) --- */
.pressure-list { list-style: none; padding: 0; margin: 0; }
.pressure-item {
  padding: 4px 0; font-size: 12px;
  color: var(--text-secondary);
  border-bottom: 1px solid var(--chrome-border);
  padding-left: 12px;
  position: relative;
}
.pressure-item::before {
  content: '\25B8';
  position: absolute; left: 0; color: var(--accent-cyan-dim);
}
.pressure-item:last-child { border-bottom: none; }

/* --- Needs bars (character inspector) --- */
.needs-bar-wrap { margin-bottom: 6px; }
.needs-bar-label {
  display: flex; justify-content: space-between;
  font-size: 11px; margin-bottom: 2px;
}
.needs-bar-name { color: var(--text-secondary); }
.needs-bar-value { font-family: var(--font-mono); color: var(--text-primary); }
.needs-bar {
  height: 4px; background: var(--bg-raised);
  border-radius: 2px; overflow: hidden;
}
.needs-bar-fill {
  height: 100%; border-radius: 2px;
  background: linear-gradient(90deg, var(--accent-cyan-dim), var(--accent-cyan));
  transition: width 0.3s;
}
```

- [ ] **Step 2: Verify file created**

Run: `ls -la prototype/cici/components.css`
Expected: file exists

---

## Task 7: Map Viewport Styles

**Teammate:** `styles`
**Files:** Create `prototype/cici/map.css`

Map-specific styles: viewport canvas, controls overlay, legend, hover card. Kept separate from layout to keep concerns clear.

- [ ] **Step 1: Create map.css**

```css
/* ============================================================
   Map Viewport Styles
   ============================================================ */

.map-controls {
  position: absolute; top: 10px; right: 10px;
  display: flex; flex-direction: column; gap: 4px;
  z-index: 5;
}
.map-ctrl {
  width: 28px; height: 28px;
  display: flex; align-items: center; justify-content: center;
  background: var(--bg-raised); border: 1px solid var(--chrome-border);
  color: var(--text-secondary); border-radius: 4px;
  cursor: pointer; font-size: 14px;
  transition: all 0.2s;
}
.map-ctrl:hover {
  color: var(--accent-cyan); border-color: var(--accent-cyan-dim);
  background: var(--bg-surface);
}

.map-legend {
  position: absolute; bottom: 10px; left: 10px;
  background: var(--bg-surface);
  border: 1px solid var(--chrome-border);
  border-radius: 6px;
  padding: 8px 12px;
  font-size: 10px;
  z-index: 5;
  max-width: 180px;
}
.legend-title {
  font-weight: 600; color: var(--text-tertiary);
  text-transform: uppercase; letter-spacing: 0.08em;
  margin-bottom: 6px;
}
.legend-row {
  display: flex; align-items: center; gap: 6px;
  padding: 2px 0; color: var(--text-secondary);
}
.legend-swatch {
  width: 12px; height: 4px; border-radius: 2px;
  display: inline-block;
}

.map-hover-card {
  position: absolute;
  background: var(--bg-surface);
  border: 1px solid var(--chrome-border-light);
  border-radius: 6px;
  padding: 10px 12px;
  pointer-events: none;
  opacity: 0;
  transition: opacity 0.15s;
  z-index: 10;
  max-width: 220px;
}
.map-hover-card.visible { opacity: 1; }
.hover-card-title {
  font-family: var(--font-heading);
  font-size: 13px; font-weight: 600;
  color: var(--text-heading);
  margin-bottom: 4px;
}
.hover-card-body {
  font-size: 11px; color: var(--text-secondary);
  line-height: 1.4;
}
.hover-card-meta {
  font-size: 10px; color: var(--text-tertiary);
  margin-top: 4px;
}

/* --- Timeline visual elements --- */
.era {
  position: absolute; height: 100%;
  border-right: 1px solid var(--chrome-border);
  display: flex; align-items: center;
  padding-left: 6px;
}
.era span {
  font-size: 9px; color: var(--text-tertiary);
  white-space: nowrap; overflow: hidden;
  text-overflow: ellipsis;
}

.track-marker {
  position: absolute; top: 50%;
  width: 8px; height: 8px; border-radius: 50%;
  transform: translate(-50%, -50%);
  border: none; cursor: pointer;
  transition: transform 0.15s;
  z-index: 2;
}
.track-marker:hover { transform: translate(-50%, -50%) scale(1.5); }
.track-marker.marker-war      { background: var(--campaign-crimson-bright); }
.track-marker.marker-culture   { background: var(--chrome-gold-bright); }
.track-marker.marker-collapse  { background: var(--status-red); }
.track-marker.marker-faith     { background: #8a7bbf; }
.track-marker.marker-character { background: var(--status-green); }

.narrated-span {
  position: absolute; top: 0; height: 100%;
  background: rgba(74, 158, 187, 0.08);
  border-left: 1px solid rgba(74, 158, 187, 0.2);
  border-right: 1px solid rgba(74, 158, 187, 0.2);
  pointer-events: none;
}

.timeline-playhead {
  position: absolute; top: -2px; bottom: -2px;
  width: 2px;
  transform: translateX(-50%);
  z-index: 5;
}
.playhead-line {
  position: absolute; inset: 0;
  background: var(--accent-cyan);
  box-shadow: 0 0 6px rgba(74, 158, 187, 0.5);
}
.playhead-label {
  position: absolute; top: -14px;
  left: 50%; transform: translateX(-50%);
  font-family: var(--font-mono);
  font-size: 9px; font-weight: 600;
  color: var(--accent-cyan);
  white-space: nowrap;
}
```

- [ ] **Step 2: Verify file created**

Run: `ls -la prototype/cici/map.css`
Expected: file exists

---

## Task 8: State Management

**Teammate:** `core-logic`
**Files:** Create `prototype/cici/state.js`

Core state object, transition functions, and listener registry. All other JS files register callbacks here rather than touching the DOM for state transitions directly.

- [ ] **Step 1: Create state.js**

```javascript
// Chronicler 7.5 Shell Prototype — State Management
// All other modules register callbacks via onStateChange/onModeChange/etc.

(function () {
  'use strict';

  // --- Listener registries ---
  const listeners = {
    state: [],
    mode: [],
    entity: [],
    turn: [],
    overlay: [],
  };

  // --- Global state ---
  window.APP = {
    state: 'setup',
    mode: 'overview',
    selectedCiv: 0,
    selectedEntity: null,
    hoveredRegion: -1,
    currentTurn: 3812,
    leftTab: 'chronicle',
    activeOverlays: new Set(['borders', 'settlements']),
    demoRunning: false,
    demoStep: 0,
  };

  // --- State transitions ---
  window.setState = function (newState) {
    APP.state = newState;
    document.querySelectorAll('.app-state').forEach(function (el) { el.classList.remove('active'); });
    var stateMap = { setup: 'state-setup', progress: 'state-progress', viewer: 'state-viewer', batch: 'state-batch' };
    var el = document.getElementById(stateMap[newState]);
    if (el) el.classList.add('active');
    listeners.state.forEach(function (fn) { fn(newState); });
  };

  window.setMode = function (newMode) {
    APP.mode = newMode;
    document.querySelectorAll('.mode-tab').forEach(function (t) { t.classList.remove('active'); });
    var tab = document.querySelector('.mode-tab[data-mode="' + newMode + '"]');
    if (tab) tab.classList.add('active');

    // Validation ribbon: visible only in campaign mode
    var ribbon = document.getElementById('validation-ribbon');
    if (ribbon) {
      if (newMode === 'campaign') ribbon.classList.remove('hidden');
      else ribbon.classList.add('hidden');
    }

    listeners.mode.forEach(function (fn) { fn(newMode); });
  };

  window.selectEntity = function (type, id) {
    APP.selectedEntity = type && id ? { type: type, id: id } : null;
    listeners.entity.forEach(function (fn) { fn(APP.selectedEntity); });
  };

  window.scrubTimeline = function (turn) {
    APP.currentTurn = Math.max(0, Math.min(turn, DATA.meta.totalTurns));
    listeners.turn.forEach(function (fn) { fn(APP.currentTurn); });
  };

  window.toggleOverlay = function (layer) {
    if (APP.activeOverlays.has(layer)) {
      APP.activeOverlays.delete(layer);
    } else {
      APP.activeOverlays.add(layer);
    }
    // Sync chip UI
    document.querySelectorAll('.layer-chip').forEach(function (chip) {
      var l = chip.dataset.layer;
      chip.classList.toggle('active', APP.activeOverlays.has(l));
    });
    listeners.overlay.forEach(function (fn) { fn(layer, APP.activeOverlays); });
  };

  // --- Listener registration ---
  window.onStateChange = function (fn) { listeners.state.push(fn); };
  window.onModeChange = function (fn) { listeners.mode.push(fn); };
  window.onEntitySelect = function (fn) { listeners.entity.push(fn); };
  window.onTurnChange = function (fn) { listeners.turn.push(fn); };
  window.onOverlayChange = function (fn) { listeners.overlay.push(fn); };

  // --- Init: wire up mode tabs, rail tabs, layer chips ---
  document.addEventListener('DOMContentLoaded', function () {
    // Mode tabs
    document.querySelectorAll('.mode-tab').forEach(function (tab) {
      tab.addEventListener('click', function () { setMode(tab.dataset.mode); });
    });

    // Rail tabs
    document.querySelectorAll('.rail-tab').forEach(function (tab) {
      tab.addEventListener('click', function () {
        document.querySelectorAll('.rail-tab').forEach(function (t) { t.classList.remove('active'); });
        tab.classList.add('active');
        APP.leftTab = tab.dataset.tab;
        // Trigger mode change to refresh rail content
        listeners.mode.forEach(function (fn) { fn(APP.mode); });
      });
    });

    // Layer chips
    document.querySelectorAll('.layer-chip').forEach(function (chip) {
      chip.addEventListener('click', function () { toggleOverlay(chip.dataset.layer); });
    });

    // Toggle groups (setup form)
    document.querySelectorAll('.toggle-group').forEach(function (g) {
      g.querySelectorAll('.toggle-btn').forEach(function (btn) {
        btn.addEventListener('click', function () {
          g.querySelectorAll('.toggle-btn').forEach(function (b) { b.classList.remove('active'); });
          btn.classList.add('active');
        });
      });
    });

    // Filter chips (batch)
    document.querySelectorAll('.filter-chip').forEach(function (chip) {
      chip.addEventListener('click', function () {
        document.querySelectorAll('.filter-chip').forEach(function (c) { c.classList.remove('active'); });
        chip.classList.add('active');
      });
    });
  });
})();
```

- [ ] **Step 2: Verify file created**

Run: `ls -la prototype/cici/state.js`
Expected: file exists

---

## Task 9: Timeline Rail

**Teammate:** `core-logic`
**Files:** Create `prototype/cici/timeline.js`

Renders era bands, event markers, narrated spans, playhead, and tick labels from `DATA`. Handles click-to-scrub interaction.

- [ ] **Step 1: Create timeline.js**

```javascript
// Chronicler 7.5 Shell Prototype — Timeline Rail
(function () {
  'use strict';

  function renderTimeline() {
    var erasEl = document.getElementById('timeline-eras');
    var eventsEl = document.getElementById('timeline-events');
    var narratedEl = document.getElementById('timeline-narrated');
    var labelsEl = document.getElementById('timeline-labels');
    if (!erasEl) return;

    // Era bands
    erasEl.innerHTML = DATA.eras.map(function (era) {
      return '<div class="era" style="left:' + era.startPct + '%;width:' + era.widthPct + '%"><span>' + era.name + '</span></div>';
    }).join('');

    // Event markers
    eventsEl.innerHTML = DATA.events.map(function (ev) {
      return '<button class="track-marker marker-' + ev.type + '" style="left:' + ev.pctLeft + '%" title="' + ev.title + '" data-turn="' + ev.turn + '"></button>';
    }).join('');

    // Narrated spans
    narratedEl.innerHTML = DATA.narratedSpans.map(function (s) {
      return '<div class="narrated-span" style="left:' + s.leftPct + '%;width:' + s.widthPct + '%"></div>';
    }).join('');

    // Tick labels
    var ticks = [];
    for (var i = 0; i <= DATA.meta.totalTurns; i += 1000) {
      ticks.push('<span>' + i + '</span>');
    }
    labelsEl.innerHTML = ticks.join('');

    // Position playhead
    updatePlayhead(APP.currentTurn);

    // Click event markers to scrub
    eventsEl.querySelectorAll('.track-marker').forEach(function (marker) {
      marker.addEventListener('click', function (e) {
        e.stopPropagation();
        scrubTimeline(parseInt(marker.dataset.turn, 10));
      });
    });
  }

  function updatePlayhead(turn) {
    var ph = document.getElementById('timeline-playhead');
    var label = document.getElementById('playhead-label');
    if (!ph) return;
    var pct = (turn / DATA.meta.totalTurns) * 100;
    ph.style.left = pct + '%';
    if (label) label.textContent = 'T' + turn;
  }

  // Click on track to scrub
  document.addEventListener('DOMContentLoaded', function () {
    var track = document.getElementById('timeline-track');
    if (track) {
      track.addEventListener('click', function (e) {
        var rect = track.getBoundingClientRect();
        var pct = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
        scrubTimeline(Math.round(pct * DATA.meta.totalTurns));
      });
    }

    renderTimeline();
  });

  // Listen for turn changes
  onTurnChange(updatePlayhead);

  // Re-render on state change (entering viewer)
  onStateChange(function (state) {
    if (state === 'viewer') {
      setTimeout(renderTimeline, 50);
    }
  });
})();
```

- [ ] **Step 2: Verify file created**

Run: `ls -la prototype/cici/timeline.js`
Expected: file exists

---

## Task 10: Map Rendering

**Teammate:** `core-logic`
**Files:** Create `prototype/cici/map.js`

Canvas-based map rendering with region fills, borders, contours, rivers, settlements, trade routes, campaign lines, fog layer, asabiya heatmap, hover cards, and click-to-select. Mode-aware overlay toggling.

- [ ] **Step 1: Create map.js**

```javascript
// Chronicler 7.5 Shell Prototype — Map Rendering
(function () {
  'use strict';

  var canvas, ctx;
  var mapW = 1000, mapH = 720;

  function initMap() {
    canvas = document.getElementById('main-map');
    if (!canvas) return;
    ctx = canvas.getContext('2d');
    window.addEventListener('resize', function () { resizeMap(); renderMap(); });

    canvas.parentElement.addEventListener('mousemove', onMouseMove);
    canvas.parentElement.addEventListener('mouseleave', function () {
      APP.hoveredRegion = -1;
      renderMap();
      hideHoverCard();
    });
    canvas.parentElement.addEventListener('click', onMapClick);

    resizeMap();
  }

  function resizeMap() {
    if (!canvas) return;
    var parent = canvas.parentElement;
    var dpr = window.devicePixelRatio || 1;
    canvas.width = parent.clientWidth * dpr;
    canvas.height = parent.clientHeight * dpr;
    canvas.style.width = parent.clientWidth + 'px';
    canvas.style.height = parent.clientHeight + 'px';
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }

  function mx(x) { return (x / mapW) * (canvas.width / (window.devicePixelRatio || 1)); }
  function my(y) { return (y / mapH) * (canvas.height / (window.devicePixelRatio || 1)); }

  function renderMap() {
    if (!ctx) return;
    var w = canvas.width / (window.devicePixelRatio || 1);
    var h = canvas.height / (window.devicePixelRatio || 1);
    ctx.clearRect(0, 0, w, h);

    // Water background
    ctx.fillStyle = getComputedStyle(document.documentElement).getPropertyValue('--map-water').trim();
    ctx.fillRect(0, 0, w, h);

    // Contour lines (terrain feel)
    ctx.strokeStyle = 'rgba(53,48,40,0.3)';
    ctx.lineWidth = 0.5;
    DATA.contours.forEach(function (pts) {
      ctx.beginPath();
      pts.forEach(function (p, i) {
        if (i === 0) ctx.moveTo(mx(p[0]), my(p[1]));
        else ctx.lineTo(mx(p[0]), my(p[1]));
      });
      ctx.stroke();
    });

    // Region fills
    var overlays = APP.activeOverlays;
    DATA.regions.forEach(function (r, idx) {
      ctx.beginPath();
      r.path.forEach(function (p, i) {
        if (i === 0) ctx.moveTo(mx(p[0]), my(p[1]));
        else ctx.lineTo(mx(p[0]), my(p[1]));
      });
      ctx.closePath();

      // Fill with civ color
      var civ = DATA.civs[r.civIdx];
      ctx.fillStyle = (idx === APP.hoveredRegion) ? civ.color : civ.colorDark;
      ctx.globalAlpha = 0.6;
      ctx.fill();
      ctx.globalAlpha = 1.0;

      // Borders
      if (overlays.has('borders')) {
        ctx.strokeStyle = 'rgba(157,138,94,0.3)';
        ctx.lineWidth = 1;
        ctx.stroke();
      }
    });

    // Rivers
    ctx.strokeStyle = 'rgba(74,158,187,0.2)';
    ctx.lineWidth = 1.5;
    DATA.rivers.forEach(function (pts) {
      ctx.beginPath();
      pts.forEach(function (p, i) {
        if (i === 0) ctx.moveTo(mx(p[0]), my(p[1]));
        else ctx.lineTo(mx(p[0]), my(p[1]));
      });
      ctx.stroke();
    });

    // Fog layer
    if (overlays.has('fog')) {
      ctx.fillStyle = 'rgba(14,14,20,0.5)';
      ctx.beginPath();
      ctx.moveTo(mx(638), my(122));
      ctx.lineTo(mx(934), my(208));
      ctx.lineTo(mx(970), my(666));
      ctx.lineTo(mx(612), my(666));
      ctx.lineTo(mx(574), my(332));
      ctx.closePath();
      ctx.fill();
    }

    // Asabiya heatmap
    if (overlays.has('asabiya')) {
      var circles = [[234, 212, 94], [398, 360, 82], [718, 346, 112]];
      circles.forEach(function (c) {
        var grad = ctx.createRadialGradient(mx(c[0]), my(c[1]), 0, mx(c[0]), my(c[1]), mx(c[2]) - mx(0));
        grad.addColorStop(0, 'rgba(74,158,187,0.15)');
        grad.addColorStop(1, 'rgba(74,158,187,0)');
        ctx.fillStyle = grad;
        ctx.beginPath();
        ctx.arc(mx(c[0]), my(c[1]), mx(c[2]) - mx(0), 0, Math.PI * 2);
        ctx.fill();
      });
    }

    // Trade routes
    if (overlays.has('trade') || APP.mode === 'trade') {
      ctx.strokeStyle = getComputedStyle(document.documentElement).getPropertyValue('--trade-gold').trim();
      ctx.lineWidth = 2;
      ctx.setLineDash([6, 4]);
      DATA.tradeRoutes.forEach(function (route) {
        ctx.beginPath();
        route.points.forEach(function (p, i) {
          if (i === 0) ctx.moveTo(mx(p[0]), my(p[1]));
          else ctx.lineTo(mx(p[0]), my(p[1]));
        });
        ctx.stroke();
        // Label
        ctx.setLineDash([]);
        ctx.font = '9px ' + getComputedStyle(document.documentElement).getPropertyValue('--font-ui').trim();
        ctx.fillStyle = 'rgba(196,160,74,0.7)';
        ctx.fillText(route.name, mx(route.labelX), my(route.labelY));
      });
      ctx.setLineDash([]);
    }

    // Campaign lines
    if (overlays.has('campaign') || APP.mode === 'campaign') {
      DATA.campaignLines.forEach(function (line) {
        ctx.beginPath();
        line.points.forEach(function (p, i) {
          if (i === 0) ctx.moveTo(mx(p[0]), my(p[1]));
          else ctx.lineTo(mx(p[0]), my(p[1]));
        });
        if (line.type === 'supply') {
          ctx.strokeStyle = 'rgba(138,64,64,0.4)';
          ctx.lineWidth = 1;
          ctx.setLineDash([4, 3]);
        } else if (line.type === 'campaign') {
          ctx.strokeStyle = getComputedStyle(document.documentElement).getPropertyValue('--campaign-crimson-bright').trim();
          ctx.lineWidth = 2;
          ctx.setLineDash([]);
        } else {
          ctx.strokeStyle = 'rgba(176,85,85,0.5)';
          ctx.lineWidth = 1.5;
          ctx.setLineDash([8, 4]);
        }
        ctx.stroke();
        ctx.setLineDash([]);
      });

      // Battle sites
      DATA.battleSites.forEach(function (b) {
        ctx.beginPath();
        ctx.arc(mx(b.cx), my(b.cy), b.r * 0.6, 0, Math.PI * 2);
        ctx.fillStyle = 'rgba(176,80,80,0.3)';
        ctx.fill();
        ctx.strokeStyle = getComputedStyle(document.documentElement).getPropertyValue('--campaign-crimson-bright').trim();
        ctx.lineWidth = 1.5;
        ctx.stroke();
      });
    }

    // Settlements
    if (overlays.has('settlements')) {
      DATA.settlements.forEach(function (s) {
        ctx.beginPath();
        ctx.arc(mx(s.x), my(s.y), s.r * 0.5, 0, Math.PI * 2);
        ctx.fillStyle = 'rgba(221,216,204,0.8)';
        ctx.fill();
        ctx.strokeStyle = 'rgba(157,138,94,0.5)';
        ctx.lineWidth = 1;
        ctx.stroke();
        // Label
        ctx.font = '10px ' + getComputedStyle(document.documentElement).getPropertyValue('--font-ui').trim();
        ctx.fillStyle = 'rgba(221,216,204,0.6)';
        ctx.fillText(s.name, mx(s.x) + s.r * 0.6 + 4, my(s.y) + 3);
      });
    }

    // Character marker (visible in character + overview modes)
    if (APP.mode === 'character' || APP.mode === 'overview') {
      var cm = DATA.characterMarker;
      var cmx = mx(cm.x), cmy = my(cm.y);
      ctx.beginPath();
      ctx.moveTo(cmx, cmy - 8);
      ctx.lineTo(cmx + 8, cmy);
      ctx.lineTo(cmx, cmy + 8);
      ctx.lineTo(cmx - 8, cmy);
      ctx.closePath();
      ctx.fillStyle = 'rgba(90,154,90,0.6)';
      ctx.fill();
      ctx.strokeStyle = getComputedStyle(document.documentElement).getPropertyValue('--status-green').trim();
      ctx.lineWidth = 1.5;
      ctx.stroke();
      ctx.font = '10px ' + getComputedStyle(document.documentElement).getPropertyValue('--font-ui').trim();
      ctx.fillStyle = 'rgba(221,216,204,0.7)';
      ctx.fillText(cm.name, cmx + 12, cmy + 3);
    }

    // Army chip (campaign mode)
    if (APP.mode === 'campaign') {
      var ac = DATA.armyChip;
      var acx = mx(ac.x), acy = my(ac.y);
      ctx.fillStyle = 'rgba(138,64,64,0.8)';
      roundRect(ctx, acx - 30, acy - 11, 60, 22, 8);
      ctx.fill();
      ctx.font = '10px ' + getComputedStyle(document.documentElement).getPropertyValue('--font-ui').trim();
      ctx.fillStyle = '#ddd8cc';
      ctx.textAlign = 'center';
      ctx.fillText(ac.name, acx, acy + 4);
      ctx.textAlign = 'start';
    }

    // Legend
    renderLegend();
  }

  function roundRect(c, x, y, w, h, r) {
    c.beginPath();
    c.moveTo(x + r, y);
    c.lineTo(x + w - r, y);
    c.quadraticCurveTo(x + w, y, x + w, y + r);
    c.lineTo(x + w, y + h - r);
    c.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
    c.lineTo(x + r, y + h);
    c.quadraticCurveTo(x, y + h, x, y + h - r);
    c.lineTo(x, y + r);
    c.quadraticCurveTo(x, y, x + r, y);
    c.closePath();
  }

  function renderLegend() {
    var el = document.getElementById('map-legend');
    if (!el) return;
    var rows = [
      '<div class="legend-title">Legend</div>',
    ];
    DATA.civs.forEach(function (c) {
      rows.push('<div class="legend-row"><span class="legend-swatch" style="background:' + c.color + '"></span><span>' + c.name + '</span></div>');
    });
    if (APP.activeOverlays.has('trade') || APP.mode === 'trade') {
      rows.push('<div class="legend-row"><span class="legend-swatch" style="background:var(--trade-gold)"></span><span>Trade route</span></div>');
    }
    if (APP.activeOverlays.has('campaign') || APP.mode === 'campaign') {
      rows.push('<div class="legend-row"><span class="legend-swatch" style="background:var(--campaign-crimson-bright)"></span><span>Campaign vector</span></div>');
    }
    el.innerHTML = rows.join('');
  }

  // --- Hit testing ---
  function hitTestRegion(px, py) {
    for (var i = 0; i < DATA.regions.length; i++) {
      var r = DATA.regions[i];
      ctx.beginPath();
      r.path.forEach(function (p, j) {
        if (j === 0) ctx.moveTo(mx(p[0]), my(p[1]));
        else ctx.lineTo(mx(p[0]), my(p[1]));
      });
      ctx.closePath();
      if (ctx.isPointInPath(px, py)) return i;
    }
    return -1;
  }

  function onMouseMove(e) {
    if (!canvas) return;
    var rect = canvas.getBoundingClientRect();
    var px = e.clientX - rect.left;
    var py = e.clientY - rect.top;
    var idx = hitTestRegion(px, py);

    if (idx !== APP.hoveredRegion) {
      APP.hoveredRegion = idx;
      renderMap();
      if (idx >= 0) {
        showHoverCard(e.clientX, e.clientY, DATA.regions[idx]);
      } else {
        hideHoverCard();
      }
    }
  }

  function onMapClick(e) {
    if (APP.hoveredRegion >= 0) {
      var r = DATA.regions[APP.hoveredRegion];
      selectEntity('region', r.id);
    } else {
      selectEntity(null, null);
    }
  }

  function showHoverCard(x, y, region) {
    var card = document.getElementById('map-hover-card');
    if (!card) return;
    var civ = DATA.civs[region.civIdx];
    card.innerHTML = '<div class="hover-card-title">' + region.name + '</div>' +
      '<div class="hover-card-body">Controlled by ' + civ.name + '</div>' +
      '<div class="hover-card-meta">Click to inspect</div>';
    card.style.left = (x + 12) + 'px';
    card.style.top = (y - 10) + 'px';
    card.classList.add('visible');
  }

  function hideHoverCard() {
    var card = document.getElementById('map-hover-card');
    if (card) card.classList.remove('visible');
  }

  // --- Init and listeners ---
  document.addEventListener('DOMContentLoaded', function () {
    initMap();
    // Delay first render until viewer is visible
    onStateChange(function (state) {
      if (state === 'viewer') {
        setTimeout(function () { resizeMap(); renderMap(); }, 50);
      }
    });
  });

  onModeChange(function () { renderMap(); });
  onOverlayChange(function () { renderMap(); });
})();
```

- [ ] **Step 2: Verify file created**

Run: `ls -la prototype/cici/map.js`
Expected: file exists

---

## Task 11: Left Rail & Inspector

**Teammate:** `content`
**Files:** Create `prototype/cici/rails.js`

Generates left rail content (chronicle entries and event log) and right inspector content based on the current mode and selection. Both update when mode changes, entity is selected, or turn scrubs.

- [ ] **Step 1: Create rails.js**

```javascript
// Chronicler 7.5 Shell Prototype — Left Rail & Right Inspector
(function () {
  'use strict';

  // --- Left Rail ---
  function renderLeftRail() {
    var contentEl = document.getElementById('left-rail-content');
    var titleEl = document.getElementById('left-rail-title');
    if (!contentEl) return;

    var modeData = DATA.leftRail[APP.mode];
    if (!modeData) return;

    var tabData = modeData[APP.leftTab];
    if (!tabData) return;

    if (titleEl) titleEl.textContent = tabData.title;

    if (APP.leftTab === 'chronicle') {
      contentEl.innerHTML = tabData.entries.map(function (entry) {
        return '<div class="chronicle-entry">' +
          '<div class="chronicle-entry-header">' +
            '<span class="chronicle-entry-tag ' + entry.tag + '">' + entry.tag + '</span>' +
            '<span class="chronicle-entry-title">' + entry.title + '</span>' +
          '</div>' +
          '<div class="chronicle-entry-body">' + entry.body + '</div>' +
        '</div>';
      }).join('');
    } else {
      contentEl.innerHTML = tabData.entries.map(function (entry) {
        return '<div class="event-row">' +
          '<span class="event-turn">T' + entry.turn + '</span>' +
          '<span class="event-type-dot ' + entry.type + '"></span>' +
          '<span class="event-text">' + entry.text + '</span>' +
        '</div>';
      }).join('');
    }
  }

  // --- Right Inspector ---
  function renderInspector() {
    var bodyEl = document.getElementById('inspector-body');
    var kickerEl = document.getElementById('inspector-kicker');
    var titleEl = document.getElementById('inspector-title');
    var subtitleEl = document.getElementById('inspector-subtitle');
    if (!bodyEl) return;

    var data = DATA.inspector[APP.mode];
    if (!data) return;

    if (kickerEl) kickerEl.textContent = modeKicker(APP.mode);
    if (titleEl) titleEl.textContent = data.title;
    if (subtitleEl) subtitleEl.textContent = data.subtitle + (data.stableId ? ' \u00B7 ' + data.stableId : '');

    var html = '';

    // KPI sections
    if (data.sections) {
      html += '<div class="inspector-card"><div class="inspector-card-title">Details</div>';
      data.sections.forEach(function (s) {
        html += '<div class="kpi-row"><span class="kpi-label">' + s.label + '</span><span class="kpi-value">' + s.value + '</span></div>';
      });
      html += '</div>';
    }

    // Distribution bars (overview)
    if (data.distributions) {
      var distColors = ['#5b8a72', '#8a7b5b', '#5b6e8a', '#8a5b5b', '#7b5b8a'];
      data.distributions.forEach(function (dist) {
        html += '<div class="inspector-card"><div class="inspector-card-title">' + dist.label + '</div>';
        html += '<div class="dist-bar-wrap"><div class="dist-bar">';
        dist.items.forEach(function (item, idx) {
          html += '<div class="dist-bar-segment" style="width:' + item.pct + '%;background:' + distColors[idx % distColors.length] + '"></div>';
        });
        html += '</div><div class="dist-bar-items">';
        dist.items.forEach(function (item, idx) {
          html += '<span class="dist-bar-item"><span class="dist-swatch" style="background:' + distColors[idx % distColors.length] + '"></span>' + item.name + ' ' + item.pct + '%</span>';
        });
        html += '</div></div></div>';
      });
    }

    // Pressures (character)
    if (data.pressures) {
      html += '<div class="inspector-card"><div class="inspector-card-title">Active Pressures</div>';
      html += '<ul class="pressure-list">';
      data.pressures.forEach(function (p) {
        html += '<li class="pressure-item">' + p + '</li>';
      });
      html += '</ul></div>';
    }

    // Needs bars (character)
    if (data.needs) {
      html += '<div class="inspector-card"><div class="inspector-card-title">Needs</div>';
      data.needs.forEach(function (n) {
        var pct = Math.round(n.value * 100);
        html += '<div class="needs-bar-wrap">' +
          '<div class="needs-bar-label"><span class="needs-bar-name">' + n.name + '</span><span class="needs-bar-value">' + n.value.toFixed(2) + '</span></div>' +
          '<div class="needs-bar"><div class="needs-bar-fill" style="width:' + pct + '%"></div></div>' +
        '</div>';
      });
      html += '</div>';
    }

    // Market details (trade)
    if (data.market) {
      var m = data.market;
      html += '<div class="inspector-card"><div class="inspector-card-title">Market: ' + m.name + '</div>';
      html += '<div class="kpi-row"><span class="kpi-label">Supply / Demand</span><span class="kpi-value">' + m.supplyDemand + '</span></div>';
      html += '<div class="kpi-row"><span class="kpi-label">Stockpile Trend</span><span class="kpi-value">' + m.stockpileTrend + '</span></div>';
      html += '<div class="kpi-row"><span class="kpi-label">Food Sufficiency</span><span class="kpi-value">' + m.foodSufficiency + '</span></div>';
      html += '<div class="kpi-row"><span class="kpi-label">Import Share</span><span class="kpi-value">' + m.importShare + '</span></div>';
      html += '<div class="kpi-row"><span class="kpi-label">Trade Dependency</span><span class="kpi-value">' + m.tradeDependency + '</span></div>';
      html += '<div class="kpi-row"><span class="kpi-label">Settlement Role</span><span class="kpi-value">' + m.role + '</span></div>';
      html += '</div>';
    }

    // Campaign target and last battle
    if (data.target) {
      html += '<div class="inspector-card"><div class="inspector-card-title">Target Rationale</div>';
      html += '<div class="chronicle-entry-body">' + data.target + '</div>';
      html += '</div>';
    }
    if (data.lastBattle) {
      html += '<div class="inspector-card"><div class="inspector-card-title">Last Battle</div>';
      html += '<div class="chronicle-entry-body">' + data.lastBattle + '</div>';
      html += '</div>';
    }

    bodyEl.innerHTML = html;
  }

  // --- Validation ribbon ---
  function renderValidationRibbon() {
    var el = document.getElementById('validation-ribbon');
    if (!el) return;

    if (APP.mode !== 'campaign') {
      el.classList.add('hidden');
      return;
    }
    el.classList.remove('hidden');
    el.innerHTML = DATA.validation.map(function (v) {
      var icon = v.status === 'pass' ? '\u2713' : v.status === 'warn' ? '!' : '\u25C8';
      var valueHtml = v.value ? '<span class="val-value">' + v.value + '</span>' : '';
      return '<div class="val-check ' + v.status + '"><span class="val-icon">' + icon + '</span><span class="val-label">' + v.label + '</span>' + valueHtml + '</div>';
    }).join('');
  }

  // --- Viewport toolbar ---
  function updateViewportToolbar() {
    var kicker = document.getElementById('viewport-kicker');
    var title = document.getElementById('viewport-title');
    if (!kicker || !title) return;

    var labels = {
      overview:  { kicker: 'Strategic Overview',   title: 'Civilization territories and settlement positions' },
      character: { kicker: 'Character Focus',       title: 'Named character positions and movement' },
      trade:     { kicker: 'Trade Diagnostics',     title: 'Route flows, price beliefs, and market pressure' },
      campaign:  { kicker: 'Campaign Intelligence', title: 'Army positions, supply lines, and fronts' },
    };
    var l = labels[APP.mode] || labels.overview;
    kicker.textContent = l.kicker;
    title.textContent = l.title;
  }

  function modeKicker(mode) {
    var kickers = { overview: 'Civilization', character: 'Great Person', trade: 'Trade Route', campaign: 'Army' };
    return kickers[mode] || 'Entity';
  }

  // --- Init and listeners ---
  document.addEventListener('DOMContentLoaded', function () {
    renderLeftRail();
    renderInspector();
    renderValidationRibbon();
    updateViewportToolbar();
  });

  onModeChange(function () {
    renderLeftRail();
    renderInspector();
    renderValidationRibbon();
    updateViewportToolbar();
  });

  onEntitySelect(function () {
    renderInspector();
  });
})();
```

- [ ] **Step 2: Verify file created**

Run: `ls -la prototype/cici/rails.js`
Expected: file exists

---

## Task 12: Setup & Progress

**Teammate:** `content`
**Files:** Create `prototype/cici/setup.js`

Setup form interaction (range sliders, seed randomize, run button) and progress animation (simulated progress bar, log lines, indicator status transitions).

- [ ] **Step 1: Create setup.js**

```javascript
// Chronicler 7.5 Shell Prototype — Setup & Progress
(function () {
  'use strict';

  document.addEventListener('DOMContentLoaded', function () {
    // Range slider value display
    ['turns', 'civs', 'regions'].forEach(function (k) {
      var inp = document.getElementById('input-' + k);
      var val = document.getElementById('val-' + k);
      if (inp && val) {
        inp.addEventListener('input', function () {
          val.textContent = k === 'turns' ? Number(inp.value).toLocaleString() : inp.value;
        });
      }
    });

    // Seed randomize
    var seedBtn = document.querySelector('.input-with-action .btn-icon');
    var seedInput = document.getElementById('input-seed');
    if (seedBtn && seedInput) {
      seedBtn.addEventListener('click', function () {
        var chars = '0123456789ABCDEFGHJKLMNPQRSTUVWXYZ';
        var seg = function () {
          var s = '';
          for (var i = 0; i < 4; i++) s += chars[Math.floor(Math.random() * chars.length)];
          return s;
        };
        seedInput.value = seg() + '-' + seg() + '-' + seg();
      });
    }

    // Run World button → progress
    var runBtn = document.getElementById('btn-run-world');
    if (runBtn) {
      runBtn.addEventListener('click', function () {
        setState('progress');
        runProgressAnimation();
      });
    }

    // Setup nav → batch
    var batchNav = document.getElementById('nav-batch-lab');
    if (batchNav) {
      batchNav.addEventListener('click', function () { setState('batch'); });
    }

    // Batch nav → setup
    var newNav = document.getElementById('batch-nav-new');
    if (newNav) {
      newNav.addEventListener('click', function () { setState('setup'); });
    }

    // Preview map (simple terrain sketch)
    renderPreviewMap();
  });

  function renderPreviewMap() {
    var canvas = document.getElementById('setup-preview-map');
    if (!canvas) return;
    var ctx = canvas.getContext('2d');
    var w = canvas.width, h = canvas.height;

    // Water
    ctx.fillStyle = '#12141e';
    ctx.fillRect(0, 0, w, h);

    // Simple terrain blobs
    ctx.fillStyle = '#2a2720';
    ctx.beginPath();
    ctx.ellipse(w * 0.5, h * 0.5, w * 0.38, h * 0.35, 0, 0, Math.PI * 2);
    ctx.fill();

    // Contour hint
    ctx.strokeStyle = 'rgba(53,48,40,0.4)';
    ctx.lineWidth = 0.5;
    for (var i = 0; i < 5; i++) {
      ctx.beginPath();
      ctx.ellipse(w * 0.5, h * 0.5, w * (0.15 + i * 0.06), h * (0.12 + i * 0.06), 0, 0, Math.PI * 2);
      ctx.stroke();
    }

    // Settlement dots
    var dots = [[0.25, 0.35], [0.45, 0.4], [0.7, 0.35], [0.35, 0.6], [0.6, 0.55], [0.8, 0.65]];
    ctx.fillStyle = 'rgba(221,216,204,0.5)';
    dots.forEach(function (d) {
      ctx.beginPath();
      ctx.arc(w * d[0], h * d[1], 3, 0, Math.PI * 2);
      ctx.fill();
    });
  }

  // --- Progress animation ---
  window.runProgressAnimation = function () {
    var fill = document.getElementById('sim-progress-fill');
    var turnEl = document.getElementById('progress-turn');
    var speedEl = document.getElementById('progress-speed');
    var logEl = document.getElementById('progress-log');
    var indSim = document.getElementById('ind-sim');
    var indNarr = document.getElementById('ind-narr');
    var indBundle = document.getElementById('ind-bundle');
    var indInterest = document.getElementById('ind-interest');

    var total = 5000;
    var turn = 0;
    var logMessages = [
      'Initializing world state\u2026',
      'Generating terrain and resources\u2026',
      'Placing civilizations\u2026',
      'Running Phase 1-3 (environment, economy, politics)\u2026',
      'Phase 4-6 (military, diplomacy, culture)\u2026',
      'Phase 7-9 (tech, actions, ecology)\u2026',
      'Agent tick: wealth, satisfaction, behavior\u2026',
      'Phase 10: consequences and emergence\u2026',
      'Curator selecting narration moments\u2026',
      'Narration complete. Assembling bundle\u2026',
    ];

    var interval = setInterval(function () {
      turn += Math.floor(Math.random() * 120 + 40);
      if (turn >= total) turn = total;

      var pct = (turn / total) * 100;
      if (fill) fill.style.width = pct + '%';
      if (turnEl) turnEl.textContent = 'Turn ' + turn.toLocaleString() + ' / ' + total.toLocaleString();
      if (speedEl) speedEl.textContent = (Math.random() * 8 + 10).toFixed(1) + ' ms/turn';

      // Log messages at thresholds
      var msgIdx = Math.min(Math.floor(pct / 11), logMessages.length - 1);
      if (logEl && logEl.children.length <= msgIdx) {
        var line = document.createElement('div');
        line.className = 'log-line';
        line.textContent = logMessages[msgIdx];
        logEl.appendChild(line);
        logEl.scrollTop = logEl.scrollHeight;
      }

      // Indicator transitions
      if (pct > 90 && indSim) { indSim.textContent = 'Done'; indSim.className = 'indicator-status done'; }
      if (pct > 92 && indNarr) { indNarr.textContent = 'Running'; indNarr.className = 'indicator-status running'; }
      if (pct > 96 && indNarr) { indNarr.textContent = 'Done'; indNarr.className = 'indicator-status done'; }
      if (pct > 97 && indBundle) { indBundle.textContent = 'Writing'; indBundle.className = 'indicator-status running'; }
      if (pct > 99 && indBundle) { indBundle.textContent = 'Done'; indBundle.className = 'indicator-status done'; }
      if (pct > 80 && indInterest) { indInterest.textContent = (0.5 + Math.random() * 0.3).toFixed(2); }

      if (turn >= total) {
        clearInterval(interval);
        if (indInterest) indInterest.textContent = '0.73';
        // Transition to viewer after brief pause
        setTimeout(function () {
          setState('viewer');
          setMode('overview');
        }, 800);
      }
    }, 60);
  };
})();
```

- [ ] **Step 2: Verify file created**

Run: `ls -la prototype/cici/setup.js`
Expected: file exists

---

## Task 13: Batch Lab

**Teammate:** `content`
**Files:** Create `prototype/cici/batch.js`

Renders the batch results table from `DATA.batch`. Supports row click to open in viewer.

- [ ] **Step 1: Create batch.js**

```javascript
// Chronicler 7.5 Shell Prototype — Batch Lab Table
(function () {
  'use strict';

  function renderBatchTable() {
    var tbody = document.getElementById('batch-table-body');
    if (!tbody) return;

    tbody.innerHTML = DATA.batch.map(function (row) {
      return '<tr>' +
        '<td>' + row.rank + '</td>' +
        '<td class="seed-cell">' + row.seed + '</td>' +
        '<td class="score-cell">' + row.score.toFixed(2) + '</td>' +
        '<td>' + row.wars + '</td>' +
        '<td>' + row.collapses + '</td>' +
        '<td>' + row.namedEvents + '</td>' +
        '<td>' + row.techMovement + '</td>' +
        '<td>' + row.anomalies + '</td>' +
        '<td><button class="batch-open-btn" data-seed="' + row.seed + '">Open</button></td>' +
      '</tr>';
    }).join('');

    // Open buttons → jump to viewer
    tbody.querySelectorAll('.batch-open-btn').forEach(function (btn) {
      btn.addEventListener('click', function () {
        setState('viewer');
        setMode('overview');
      });
    });
  }

  document.addEventListener('DOMContentLoaded', renderBatchTable);

  // Re-render if state changes to batch
  onStateChange(function (state) {
    if (state === 'batch') renderBatchTable();
  });
})();
```

- [ ] **Step 2: Verify file created**

Run: `ls -la prototype/cici/batch.js`
Expected: file exists

---

## Task 14: Demo Walkthrough

**Teammate:** `content`
**Files:** Create `prototype/cici/demo.js`

Automated walkthrough that cycles through all app states and viewer modes with timed transitions. Demo control buttons and jump shortcuts.

- [ ] **Step 1: Create demo.js**

```javascript
// Chronicler 7.5 Shell Prototype — Demo Walkthrough
(function () {
  'use strict';

  var demoSequence = [
    { action: function () { setState('setup'); }, label: 'setup', delay: 3000 },
    { action: function () { setState('progress'); runProgressAnimation(); }, label: 'progress', delay: 6000 },
    { action: function () { setState('viewer'); setMode('overview'); }, label: 'overview', delay: 4000 },
    { action: function () { scrubTimeline(2091); }, label: 'scrub-famine', delay: 2000 },
    { action: function () { scrubTimeline(3812); }, label: 'scrub-collapse', delay: 2000 },
    { action: function () { setMode('character'); }, label: 'character', delay: 4000 },
    { action: function () { setMode('trade'); }, label: 'trade', delay: 4000 },
    { action: function () { setMode('campaign'); }, label: 'campaign', delay: 4000 },
    { action: function () { setState('batch'); }, label: 'batch', delay: 4000 },
    { action: function () { setState('viewer'); setMode('overview'); }, label: 'overview-return', delay: 2000 },
  ];

  var demoTimeout = null;

  function startDemo() {
    APP.demoRunning = true;
    APP.demoStep = 0;
    document.getElementById('btn-auto-demo').style.display = 'none';
    document.getElementById('btn-pause-demo').style.display = '';
    runDemoStep();
  }

  function pauseDemo() {
    APP.demoRunning = false;
    clearTimeout(demoTimeout);
    document.getElementById('btn-auto-demo').style.display = '';
    document.getElementById('btn-pause-demo').style.display = 'none';
  }

  function runDemoStep() {
    if (!APP.demoRunning || APP.demoStep >= demoSequence.length) {
      pauseDemo();
      return;
    }
    var step = demoSequence[APP.demoStep];
    step.action();
    updateJumpButtons(step.label);
    APP.demoStep++;
    demoTimeout = setTimeout(runDemoStep, step.delay);
  }

  function jumpTo(target) {
    pauseDemo();
    var jumpMap = {
      setup:     function () { setState('setup'); },
      progress:  function () { setState('progress'); },
      overview:  function () { setState('viewer'); setMode('overview'); },
      character: function () { setState('viewer'); setMode('character'); },
      trade:     function () { setState('viewer'); setMode('trade'); },
      campaign:  function () { setState('viewer'); setMode('campaign'); },
      batch:     function () { setState('batch'); },
    };
    var fn = jumpMap[target];
    if (fn) fn();
    updateJumpButtons(target);
  }

  function updateJumpButtons(activeLabel) {
    document.querySelectorAll('.jump-btn').forEach(function (btn) {
      btn.classList.toggle('active', btn.dataset.jump === activeLabel);
    });
  }

  document.addEventListener('DOMContentLoaded', function () {
    var playBtn = document.getElementById('btn-auto-demo');
    var pauseBtn = document.getElementById('btn-pause-demo');
    if (playBtn) playBtn.addEventListener('click', startDemo);
    if (pauseBtn) pauseBtn.addEventListener('click', pauseDemo);

    document.querySelectorAll('.jump-btn').forEach(function (btn) {
      btn.addEventListener('click', function () { jumpTo(btn.dataset.jump); });
    });
  });
})();
```

- [ ] **Step 2: Verify file created**

Run: `ls -la prototype/cici/demo.js`
Expected: file exists

---

## Task 15: Integration Verification

**Teammate:** Lead (or any teammate after all files are written)

Open the prototype in a browser and verify all acceptance criteria.

- [ ] **Step 1: Verify all files exist**

Run: `ls -la prototype/cici/`
Expected: 14 files (index.html, tokens.css, layout.css, states.css, components.css, map.css, data.js, state.js, timeline.js, map.js, rails.js, setup.js, batch.js, demo.js)

- [ ] **Step 2: Verify HTML loads without console errors**

Open `prototype/cici/index.html` in a browser. Check the developer console for errors.
Expected: no errors, Setup screen visible.

- [ ] **Step 3: Verify Setup → Progress → Viewer flow**

Click "Run World" on the Setup screen.
Expected: Progress bar animates, indicators transition, auto-opens to Overview after completion.

- [ ] **Step 4: Verify all four viewer modes share the same shell**

Click each mode tab: Overview, Character, Trade, Campaign.
Expected:
- Header, timeline rail, and workspace grid remain identical.
- Left rail content changes per mode.
- Right inspector content changes per mode.
- Map renders mode-specific overlays (trade routes in Trade, campaign lines in Campaign).
- Validation ribbon appears only in Campaign mode.

- [ ] **Step 5: Verify Batch Lab flow**

Jump to Batch Lab. Click "Open" on a row.
Expected: Opens directly into the viewer in Overview mode.

- [ ] **Step 6: Verify demo walkthrough**

Click the Demo play button.
Expected: Automated walkthrough cycles through all states and modes.

---

## Acceptance Criteria Summary

| Criterion | Verified by |
|-----------|-------------|
| Overview, Character, Trade, Campaign share one shell | Task 15 Step 4 |
| Setup → Run → Viewer is seamless | Task 15 Step 3 |
| Batch results open directly into viewer | Task 15 Step 5 |
| Left rail preserves Chronicle/Event identity across modes | Task 15 Step 4 |
| Right inspector updates from mode changes | Task 15 Step 4 |
| No bespoke layouts that break shell cohesion | Task 15 Step 4 |
| Dark cartographic analytics mode is primary | Visual inspection |
| Map is the hero surface in all modes | Visual inspection |
| Timeline rail with era bands and event markers | Task 15 Step 3-4 |
| Demo walkthrough covers all states | Task 15 Step 6 |
