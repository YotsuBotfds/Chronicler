const worldMeta = {
  world: "Aethelgard Reborn",
  scenario: "Migration Era Decay",
  seed: "4ASF-9B1D-7C6E",
  schema: "v7.5.12",
  turn: 3812,
  totalTurns: 5000,
  interestingness: 0.73,
  performance: "14.2 ms/turn",
  mode: "ARCHIVE",
};

const civSummary = {
  name: "Thornwall March",
  capital: "Thornwall",
  population: "4.8M",
  urbanization: "31%",
  wealth: "182M thalers",
  tradeDependency: "41%",
  classTension: "0.27",
  asabiya: "0.61",
  succession: "Prince Caedmon, then Lady Ysabet",
  faith: [
    { name: "Thorn Rite", value: 52 },
    { name: "Old Basilica", value: 29 },
    { name: "Pilgrim Houses", value: 19 },
  ],
  factions: [
    { name: "Crown", value: 34 },
    { name: "Nobility", value: 27 },
    { name: "Merchants", value: 21 },
    { name: "Clergy", value: 18 },
  ],
  cultures: [
    { name: "Marcher", value: 46 },
    { name: "Aurelian", value: 31 },
    { name: "Steppe-born", value: 23 },
  ],
};

const characterSummary = {
  name: "Eadric of Thornwall",
  stableId: "GP-00481",
  title: "Regent of the March",
  location: "Greyfen Basin",
  dynasty: "House Thornwall",
  muleSource: "Siege of Greyfen",
  muleTurns: 11,
  artifact: "Seal of Alder Moot",
  activePressures: [
    "hold Thornwall succession bloc",
    "protect Kestrel grain convoys",
    "avoid clerical fracture after the schism",
  ],
};

const tradeSummary = {
  route: "Amber Corridor",
  stableId: "RT-018",
  routeProfit: "126k / turn",
  routeMargin: "18.4%",
  staleBelief: "0.91",
  currentBelief: "1.04",
  inTransit: "grain, saffron, worked iron",
  merchantPlan: "hold at Kestrel until famine premium resolves",
  confidence: "0.82",
  freshness: "3 turns",
  market: "Greyfen Basin",
  supplyDemand: "1.18 / 0.92",
  stockpileTrend: "rising 6 turns",
  foodSufficiency: "0.94",
  importShare: "42%",
  tradeDependency: "38%",
  settlementRole: "river hinge / redistribution",
};

const campaignSummary = {
  army: "III Thornwall Field Army",
  stableId: "AR-022",
  morale: "0.62",
  supply: "19 days",
  targetRationale: "hold Saint's Ford before Salt Step cavalry reaches the orchard road",
  battleOutcome: "defensive victory at Greyfen Ford",
  casualties: "1,840",
  occupiedRegions: "2 contested, 1 held",
  freshness: "2 turns",
  staleness: "14%",
  confidence: "0.78",
  familiarity: "0.84",
};

const batchRows = [
  {
    world: "Aethelgard Reborn",
    seed: "4ASF-9B1D-7C6E",
    score: "0.73",
    wars: 12,
    collapses: 3,
    namedEvents: 18,
    techMovement: "late iron drift",
    anomalies: "schism + convoy cascade",
  },
  {
    world: "Aethelgard Reborn",
    seed: "5CQP-8K2E-1M4A",
    score: "0.68",
    wars: 9,
    collapses: 2,
    namedEvents: 14,
    techMovement: "river scripts",
    anomalies: "merchant lock-in",
  },
  {
    world: "Aethelgard Reborn",
    seed: "9YTR-3L8M-2J5H",
    score: "0.64",
    wars: 14,
    collapses: 4,
    namedEvents: 16,
    techMovement: "frontier steel",
    anomalies: "oracle drift spike",
  },
  {
    world: "Aethelgard Reborn",
    seed: "2HTA-0B9V-3S8P",
    score: "0.58",
    wars: 7,
    collapses: 1,
    namedEvents: 11,
    techMovement: "grain mills",
    anomalies: "settlement overhang",
  },
];

const leftRailData = {
  setup: {
    chronicle: {
      title: "Launch Manifest",
      chips: ["setup", "scenario", "preview"],
      footer: `
        <div class="rail-kpi-row">
          <span class="kpi-chip">procedural and scenario entry</span>
          <span class="kpi-chip">narration framed as Off / Local / API</span>
        </div>
        <div class="footer-note">The shell stays intact here so the front door already feels like the product, not a temporary launcher.</div>
      `,
      entries: [
        {
          title: "Migration Era Decay loaded",
          tag: "scenario",
          copy: "Post-imperial fragmentation, convoy stress, religious fracture, and migration pressure are all seeded into the launch brief.",
        },
        {
          title: "Preview map pressure bands",
          tag: "atlas",
          copy: "Greyfen Basin and Kestrel Port are pre-highlighted as the main narrative and logistics hinges.",
        },
        {
          title: "Narration mode staging",
          tag: "runtime",
          copy: "Operators can choose Off, Local, or API without leaving the shell or losing the map-first setup context.",
        },
      ],
    },
    events: {
      title: "Setup Events",
      chips: ["entry", "handoff"],
      footer: `<div class="footer-note">Open Existing remains implied, but the recordable happy path is configure, run, and open straight into the archive shell.</div>`,
      entries: [
        {
          title: "Scenario preset applied",
          tag: "launch",
          copy: "12 civilizations, 48 regions, 5000 turns.",
        },
        {
          title: "Atlas preview generated",
          tag: "visual",
          copy: "Parchment contours, settlement seeds, and frontier hints are ready before compute begins.",
        },
        {
          title: "Batch lab available",
          tag: "lab",
          copy: "Operators can pivot to interestingness ranking without leaving the app family.",
        },
      ],
    },
  },
  progress: {
    chronicle: {
      title: "Run Chronicle",
      chips: ["simulation", "curator", "narration"],
      footer: `
        <div class="rail-kpi-row">
          <span class="kpi-chip">turn queue active</span>
          <span class="kpi-chip">interestingness estimate rising</span>
          <span class="kpi-chip">handoff on completion</span>
        </div>
      `,
      entries: [
        {
          title: "Topology generated",
          tag: "phase 1",
          copy: "Hydrology, climate, and frontier seams locked into the turn loop.",
        },
        {
          title: "Settlement seeds placed",
          tag: "phase 2",
          copy: "Thornwall, Greyfen, Kestrel Port, and Red Salt initialized as anchor nodes.",
        },
        {
          title: "Curator staging",
          tag: "queue",
          copy: "Named events and gap summaries are being assembled for archive opening.",
        },
      ],
    },
    events: {
      title: "Run Events",
      chips: ["runtime", "metrics"],
      footer: `<div class="footer-note">The progress pass is short on purpose: enough to feel real on video, not long enough to stall the walkthrough.</div>`,
      entries: [
        { title: "Turn 912", tag: "perf", copy: "Simulation settled near 13.8 ms/turn after map initialization." },
        { title: "Turn 2264", tag: "signal", copy: "Interestingness estimate crossed 0.61 as the schism tree opened." },
        { title: "Turn 3812", tag: "handoff", copy: "Archive shell preloaded and inspector cached for the first overview frame." },
      ],
    },
  },
  overview: {
    chronicle: {
      title: "Chronicle / Late Decay",
      chips: ["overview", "curated", "archive"],
      footer: `
        <div class="rail-kpi-row">
          <span class="kpi-chip">era reflection ready</span>
          <span class="kpi-chip">4 linked causal chains</span>
          <span class="kpi-chip">7 active overlays</span>
        </div>
        <div class="footer-note">Overview stays map-first while still preserving Chronicler's editorial voice through grouped chronicle entries and era reflections.</div>
      `,
      entries: [
        {
          title: "Imperial collapse becomes administrative fact",
          tag: "reflection",
          copy: "The archive now treats the empire as memory infrastructure: tax roads still bind the map long after legitimacy disappeared.",
        },
        {
          title: "Greyfen convoy law keeps Thornwall solvent",
          tag: "curator",
          copy: "Trade dependency rises, but convoy control also prevents class tension from spiking past 0.30.",
        },
        {
          title: "Eadric emerges as a stabilizer, not a conqueror",
          tag: "character",
          copy: "His rise is narratively linked to logistics triage, inherited trauma, and dynastic vacuum.",
        },
      ],
    },
    events: {
      title: "Event Log / Grouped",
      chips: ["war", "trade", "faith", "filters"],
      footer: `<div class="footer-note">Grouped mechanical rows keep the left rail dense without letting repetitive simulation events bury the narrative surface.</div>`,
      entries: [
        { title: "36 convoy skirmishes around Greyfen", tag: "war", copy: "Mostly low-casualty interdictions with one escalatory breakthrough at Saint's Ford." },
        { title: "12 market shocks in Kestrel corridor", tag: "trade", copy: "Price beliefs diverged faster than merchant familiarity could recover." },
        { title: "4 schism-linked legitimacy events", tag: "faith", copy: "Clerical influence rose in Thornwall after the basilica exodus." },
      ],
    },
  },
  character: {
    chronicle: {
      title: "Character Dossier",
      chips: ["memory", "mule", "dynasty"],
      footer: `
        <div class="rail-kpi-row">
          <span class="kpi-chip">stable ID GP-00481</span>
          <span class="kpi-chip">memory intensity sorted</span>
          <span class="kpi-chip">movement inset pinned</span>
        </div>
      `,
      entries: [
        { title: "Siege of Greyfen remains dominant memory", tag: "shock", copy: "Intensity 0.91, source war, legacy risk still active through the current Mule window." },
        { title: "Alder Moot oath anchors his legitimacy", tag: "legacy", copy: "Family oath memory keeps loyalty pressure from flipping into open revolt utility." },
        { title: "Artifact chain reconnects him to the orchard road", tag: "artifact", copy: "The Seal of Alder Moot has passed through three hands and two dynastic collapses." },
      ],
    },
    events: {
      title: "Character Events",
      chips: ["relationships", "movements"],
      footer: `<div class="footer-note">Character detail stays inside the same workstation shell so it reads as a dense inspection mode, not a separate poster-like dossier product.</div>`,
      entries: [
        { title: "Turn 3794: held council at Greyfen", tag: "decision", copy: "Merchant and clergy blocs both pulled on food convoy policy." },
        { title: "Turn 3802: memory flare from siege echo", tag: "memory", copy: "Need stack briefly shifted toward safety and duty at the expense of belonging." },
        { title: "Turn 3810: returned Seal of Alder Moot", tag: "artifact", copy: "Dynastic legibility improved across Thornwall and Saint's Ford alike." },
      ],
    },
  },
  trade: {
    chronicle: {
      title: "Trade Diagnostics",
      chips: ["route", "beliefs", "markets"],
      footer: `
        <div class="rail-kpi-row">
          <span class="kpi-chip">current vs stale beliefs</span>
          <span class="kpi-chip">merchant plan exposed</span>
          <span class="kpi-chip">route flow animated</span>
        </div>
      `,
      entries: [
        { title: "Amber Corridor remains profitable despite fear pricing", tag: "route", copy: "Current margin is healthy, but stale price beliefs still overstate risk on the final Kestrel leg." },
        { title: "Greyfen stocks are rising too late", tag: "market", copy: "Food sufficiency recovered from 0.81 to 0.94 after merchant plans reweighted around convoy freshness." },
        { title: "Last Orchard acts as buffer, not sink", tag: "settlement", copy: "Redistribution into the orchard road keeps the march from consuming its own reserve floor." },
      ],
    },
    events: {
      title: "Trade Events",
      chips: ["flows", "hubs"],
      footer: `<div class="footer-note">Trade view leans into observability language without sterilizing the world into a generic business dashboard.</div>`,
      entries: [
        { title: "Merchant route plan updated", tag: "plan", copy: "Hold at Kestrel until salt premium softens and the Greyfen demand pulse normalizes." },
        { title: "Belief freshness recovered", tag: "knowledge", copy: "Packet-driven familiarity cut the stale spread from 0.22 to 0.13." },
        { title: "In-transit goods reprioritized", tag: "cargo", copy: "Grain and worked iron displaced dyestuffs after the Saint's Ford disruption." },
      ],
    },
  },
  campaign: {
    chronicle: {
      title: "Campaign Intelligence",
      chips: ["validation", "march", "fog"],
      footer: `
        <div class="rail-kpi-row">
          <span class="kpi-chip">determinism checks green</span>
          <span class="kpi-chip">supply diagnostics exposed</span>
          <span class="kpi-chip">knowledge fog active</span>
        </div>
      `,
      entries: [
        { title: "Saint's Ford front stabilizes", tag: "front", copy: "The march line bends south once supply drops under twenty days and confidence degrades east of Halewatch." },
        { title: "Pattern oracle accepts the campaign shape", tag: "oracle", copy: "Late-decay movement matches expected raid-to-frontier compression instead of drifting into implausible map-wide pursuit." },
        { title: "Knowledge freshness explains the hesitation", tag: "fog", copy: "Fresh local intelligence is high, but eastern familiarity remains sparse and stale." },
      ],
    },
    events: {
      title: "Campaign Events",
      chips: ["army", "battle", "oracle"],
      footer: `<div class="footer-note">The validation ribbon sits above the same map and inspector rather than pulling campaign review into a separate QA dashboard.</div>`,
      entries: [
        { title: "Turn 3788: cavalry raid at Halewatch", tag: "battle", copy: "Supply loss was small, but familiarity cratered east of the front." },
        { title: "Turn 3806: march pivots toward Saint's Ford", tag: "march", copy: "Target rationale updated when the orchard road became the decisive artery." },
        { title: "Turn 3812: defensive victory holds", tag: "result", copy: "Morale improves despite casualty concentration because the route network remains open." },
      ],
    },
  },
  batch: {
    chronicle: {
      title: "Batch Lab",
      chips: ["ranking", "interestingness", "compare"],
      footer: `
        <div class="rail-kpi-row">
          <span class="kpi-chip">interestingness-ranked results</span>
          <span class="kpi-chip">side-by-side compare</span>
          <span class="kpi-chip">open selected run</span>
        </div>
      `,
      entries: [
        { title: "Top-ranked run preserved for direct handoff", tag: "rank 1", copy: "4ASF-9B1D-7C6E stays pinned because it balances war, collapse, and named-character clarity." },
        { title: "Second-ranked run kept for compare", tag: "rank 2", copy: "5CQP-8K2E-1M4A has cleaner convoy recovery but weaker dynastic drama." },
        { title: "Batch remains part of the same product family", tag: "flow", copy: "No sidecar tool styling, no dead-end report page, and no manual file hunting after selection." },
      ],
    },
    events: {
      title: "Batch Events",
      chips: ["compare", "selection"],
      footer: `<div class="footer-note">Batch is setup-adjacent and still keeps the atlas visible, so the handoff into the full viewer feels immediate.</div>`,
      entries: [
        { title: "Top run selected", tag: "select", copy: "The same canonical seed used in the main walkthrough remains the chosen archive." },
        { title: "Compare affordance enabled", tag: "compare", copy: "Operators can stack outcomes without flooding the main map shell with secondary chrome." },
        { title: "Open in viewer", tag: "handoff", copy: "Selection returns to Overview with the archive shell already warm." },
      ],
    },
  },
};

const validationPills = [
  ["Determinism checks", "200/200 match"],
  ["Perf baseline", "+6.1% within target"],
  ["Trade baseline", "delta 0.03"],
  ["Settlement plausibility", "pass"],
  ["Pattern oracle", "late-decay match"],
];

const regions = {
  thornwall: { title: "Thornwall", copy: "Dynastic core with steady clergy pull and above-baseline legitimacy recovery." },
  greyfen: { title: "Greyfen Basin", copy: "Granary hinge with river toll control and elevated merchant familiarity." },
  kestrel: { title: "Kestrel Port", copy: "Convoy terminus where stale price beliefs linger longer than stockpile truth." },
  hollowmere: { title: "Hollowmere", copy: "Transition zone where class tension rises fastest when food sufficiency slips." },
  saltstep: { title: "Salt Step Reach", copy: "Frontier corridor with active cavalry pressure and patchy knowledge freshness." },
  redsalt: { title: "Red Salt", copy: "Dry hinterland reserve that amplifies route profit when convoy security holds." },
  lastorchard: { title: "Last Orchard", copy: "Buffer region whose stockpiles matter more than its legitimacy share." },
};

const stateLabels = {
  setup: "Setup / New World",
  progress: "Run Progress",
  overview: "Overview / Strategic Command",
  character: "Character Detail / Great Person",
  trade: "Trade Diagnostics / Logistics",
  campaign: "Campaign & Validation / Military Intelligence",
  batch: "Batch Lab / Interestingness Ranking",
};

const app = document.getElementById("app");
const leftRail = document.getElementById("left-rail-content");
const leftRailTitle = document.getElementById("left-rail-title");
const leftToolbarChips = document.getElementById("left-toolbar-chips");
const leftFooter = document.getElementById("left-rail-footer");
const inspectorBody = document.getElementById("inspector-body");
const inspectorKicker = document.getElementById("inspector-kicker");
const inspectorTitle = document.getElementById("inspector-title");
const inspectorSubtitle = document.getElementById("inspector-subtitle");
const viewportKicker = document.getElementById("viewport-kicker");
const viewportTitle = document.getElementById("viewport-title");
const mapOverlay = document.getElementById("map-overlay");
const validationRibbon = document.getElementById("validation-ribbon");
const railTitle = document.getElementById("rail-title");
const railChipLive = document.getElementById("rail-chip-live");
const turnReadout = document.getElementById("turn-readout");
const interestingnessReadout = document.getElementById("interestingness-readout");
const performanceReadout = document.getElementById("performance-readout");
const turnTrack = document.getElementById("turn-track");
const playhead = document.getElementById("playhead");
const playheadLabel = document.getElementById("playhead-label");
const hoverCard = document.getElementById("hover-card");
const hoverTitle = document.getElementById("hover-title");
const hoverCopy = document.getElementById("hover-copy");
const armyChip = document.getElementById("army-chip");
const demoStateLabel = document.getElementById("demo-state-label");
const modeSwitches = Array.from(document.querySelectorAll(".mode-switch"));
const jumpPills = Array.from(document.querySelectorAll(".jump-pill"));
const flowSteps = Array.from(document.querySelectorAll(".flow-step"));
const railTabs = Array.from(document.querySelectorAll(".rail-tab"));
const layerChips = Array.from(document.querySelectorAll(".layer-chip"));
const regionNodes = Array.from(document.querySelectorAll(".region"));
const trackMarkers = Array.from(document.querySelectorAll(".track-marker"));
const eadricMarker = document.getElementById("eadric-marker");
const tradeRoutes = Array.from(document.querySelectorAll(".trade-route"));

const state = {
  mode: "setup",
  leftTab: "chronicle",
  hoverRegion: "greyfen",
  progress: 0,
  progressTurn: 0,
  turn: worldMeta.turn,
  selectedBatch: 0,
  routeFocus: "amber-loop",
  armyPhase: 0,
  layers: {
    borders: true,
    settlements: true,
    chronicle: true,
    trade: false,
    campaign: false,
    fog: false,
    asabiya: false,
  },
};

const demoTimeline = [
  { key: "setup", duration: 7000 },
  { key: "progress", duration: 6500 },
  { key: "overview", duration: 10000 },
  { key: "character", duration: 8500 },
  { key: "trade", duration: 8500 },
  { key: "campaign", duration: 9000 },
  { key: "batch", duration: 8500 },
  { key: "overview", duration: 5000 },
];

const demo = {
  playing: true,
  stepIndex: 0,
  stepElapsed: 0,
  lastTs: null,
};

function pctFromTurn(turn) {
  return ((turn - 1) / (worldMeta.totalTurns - 1)) * 100;
}

function addPanelEnter(node) {
  node.classList.remove("panel-enter");
  void node.offsetWidth;
  node.classList.add("panel-enter");
}

function renderRail() {
  const tabData = leftRailData[state.mode][state.leftTab];
  leftRailTitle.textContent = tabData.title;
  leftToolbarChips.innerHTML = tabData.chips.map((chip) => `<span class="kpi-chip">${chip}</span>`).join("");
  leftRail.innerHTML = tabData.entries.map((entry, index) => `
    <article class="rail-entry ${index === 0 ? "active" : ""}" data-rail-index="${index}">
      <div class="entry-header"><strong>${entry.title}</strong><span class="entry-tag">${entry.tag}</span></div>
      <div class="list-copy">${entry.copy}</div>
    </article>
  `).join("");
  leftFooter.innerHTML = tabData.footer;
  addPanelEnter(leftRail);
  addPanelEnter(leftFooter);
}

function renderOverviewInspector() {
  return `
    <section class="inspector-section">
      <h4>Civilization Snapshot</h4>
      <div class="status-pair"><span>Capital</span><strong>${civSummary.capital}</strong></div>
      <div class="status-pair"><span>Population</span><strong>${civSummary.population}</strong></div>
      <div class="status-pair"><span>Urbanization</span><strong>${civSummary.urbanization}</strong></div>
      <div class="status-pair"><span>Wealth</span><strong>${civSummary.wealth}</strong></div>
    </section>
    <section class="inspector-section">
      <h4>Faction Influence</h4>
      <div class="metric-stack">
        ${civSummary.factions.map((row) => `
          <div class="metric-row">
            <label>${row.name}</label>
            <div class="metric-bar"><span style="width:${row.value}%"></span></div>
            <strong>${row.value}%</strong>
          </div>
        `).join("")}
      </div>
    </section>
    <section class="inspector-section">
      <h4>Faith and Culture</h4>
      <div class="metric-stack">
        ${civSummary.faith.map((row) => `
          <div class="metric-row">
            <label>${row.name}</label>
            <div class="metric-bar"><span style="width:${row.value}%"></span></div>
            <strong>${row.value}%</strong>
          </div>
        `).join("")}
        ${civSummary.cultures.map((row) => `
          <div class="metric-row">
            <label>${row.name}</label>
            <div class="metric-bar"><span style="width:${row.value}%"></span></div>
            <strong>${row.value}%</strong>
          </div>
        `).join("")}
      </div>
    </section>
    <section class="inspector-section">
      <h4>Structural Pressures</h4>
      <div class="status-pair"><span>Trade dependency</span><strong>${civSummary.tradeDependency}</strong></div>
      <div class="status-pair"><span>Class tension</span><strong>${civSummary.classTension}</strong></div>
      <div class="status-pair"><span>Asabiya</span><strong>${civSummary.asabiya}</strong></div>
      <div class="status-pair"><span>Succession</span><strong>${civSummary.succession}</strong></div>
    </section>
  `;
}

function renderCharacterInspector() {
  return `
    <section class="inspector-section">
      <h4>Identity</h4>
      <div class="status-pair"><span>Stable ID</span><strong>${characterSummary.stableId}</strong></div>
      <div class="status-pair"><span>Title</span><strong>${characterSummary.title}</strong></div>
      <div class="status-pair"><span>Dynasty</span><strong>${characterSummary.dynasty}</strong></div>
      <div class="status-pair"><span>Location</span><strong>${characterSummary.location}</strong></div>
    </section>
    <section class="inspector-section">
      <div class="mule-banner">
        <div class="tiny-label">Mule Indicator</div>
        <strong>${characterSummary.muleSource}</strong>
        <div class="metric-note">Memory warped this character's utility weighting. Active for ${characterSummary.muleTurns} more turns.</div>
      </div>
    </section>
    <section class="inspector-section">
      <h4>Active Decision Pressures</h4>
      ${characterSummary.activePressures.map((item) => `<div class="status-pair"><span>${item}</span><strong>active</strong></div>`).join("")}
    </section>
    <section class="inspector-section">
      <h4>Artifact Provenance</h4>
      <div class="status-pair"><span>Current holder</span><strong>${characterSummary.name}</strong></div>
      <div class="status-pair"><span>Artifact</span><strong>${characterSummary.artifact}</strong></div>
      <div class="status-pair"><span>Legacy effect</span><strong>succession legitimacy + oath memory</strong></div>
    </section>
  `;
}

function renderTradeInspector() {
  return `
    <section class="inspector-section">
      <h4>Route Inspection</h4>
      <div class="status-pair"><span>Stable ID</span><strong>${tradeSummary.stableId}</strong></div>
      <div class="status-pair"><span>Profit</span><strong>${tradeSummary.routeProfit}</strong></div>
      <div class="status-pair"><span>Margin</span><strong>${tradeSummary.routeMargin}</strong></div>
      <div class="status-pair"><span>Beliefs</span><strong>${tradeSummary.staleBelief} stale / ${tradeSummary.currentBelief} current</strong></div>
      <div class="status-pair"><span>In-transit goods</span><strong>${tradeSummary.inTransit}</strong></div>
      <div class="status-pair"><span>Merchant plan</span><strong>${tradeSummary.merchantPlan}</strong></div>
      <div class="status-pair"><span>Confidence</span><strong>${tradeSummary.confidence}</strong></div>
      <div class="status-pair"><span>Freshness</span><strong>${tradeSummary.freshness}</strong></div>
    </section>
    <section class="inspector-section">
      <h4>Market Inspection</h4>
      <div class="status-pair"><span>Hub</span><strong>${tradeSummary.market}</strong></div>
      <div class="status-pair"><span>Supply / demand</span><strong>${tradeSummary.supplyDemand}</strong></div>
      <div class="status-pair"><span>Stockpile trend</span><strong>${tradeSummary.stockpileTrend}</strong></div>
      <div class="status-pair"><span>Food sufficiency</span><strong>${tradeSummary.foodSufficiency}</strong></div>
      <div class="status-pair"><span>Import share</span><strong>${tradeSummary.importShare}</strong></div>
      <div class="status-pair"><span>Trade dependency</span><strong>${tradeSummary.tradeDependency}</strong></div>
      <div class="status-pair"><span>Settlement role</span><strong>${tradeSummary.settlementRole}</strong></div>
    </section>
  `;
}

function renderCampaignInspector() {
  return `
    <section class="inspector-section">
      <h4>Army Snapshot</h4>
      <div class="status-pair"><span>Stable ID</span><strong>${campaignSummary.stableId}</strong></div>
      <div class="status-pair"><span>Composition</span><strong>38% spears / 24% cavalry / 20% levy / 18% archers</strong></div>
      <div class="status-pair"><span>Morale</span><strong>${campaignSummary.morale}</strong></div>
      <div class="status-pair"><span>Supply</span><strong>${campaignSummary.supply}</strong></div>
      <div class="status-pair"><span>Target rationale</span><strong>${campaignSummary.targetRationale}</strong></div>
    </section>
    <section class="inspector-section">
      <h4>Battle and Occupation</h4>
      <div class="status-pair"><span>Outcome</span><strong>${campaignSummary.battleOutcome}</strong></div>
      <div class="status-pair"><span>Casualties</span><strong>${campaignSummary.casualties}</strong></div>
      <div class="status-pair"><span>Occupied regions</span><strong>${campaignSummary.occupiedRegions}</strong></div>
      <div class="status-pair"><span>March timeline</span><strong>Greyfen -> Halewatch -> Saint's Ford</strong></div>
    </section>
    <section class="inspector-section">
      <h4>Knowledge Diagnostics</h4>
      <div class="status-pair"><span>Freshness</span><strong>${campaignSummary.freshness}</strong></div>
      <div class="status-pair"><span>Staleness</span><strong>${campaignSummary.staleness}</strong></div>
      <div class="status-pair"><span>Confidence</span><strong>${campaignSummary.confidence}</strong></div>
      <div class="status-pair"><span>Familiarity</span><strong>${campaignSummary.familiarity}</strong></div>
    </section>
  `;
}

function renderSetupInspector() {
  return `
    <section class="inspector-section">
      <h4>Scenario Summary</h4>
      <div class="manifest-copy">A once-unified empire decays under convoy strain, clerical fracture, and migration pressure. The chosen preset is tuned for strong archive readability and interestingness ranking.</div>
    </section>
    <section class="inspector-section">
      <h4>Launch Metrics</h4>
      <div class="status-pair"><span>Turns</span><strong>5000</strong></div>
      <div class="status-pair"><span>Civilizations</span><strong>12</strong></div>
      <div class="status-pair"><span>Regions</span><strong>48</strong></div>
      <div class="status-pair"><span>Narration</span><strong>API</strong></div>
      <div class="status-pair"><span>Generation</span><strong>Scenario</strong></div>
    </section>
    <section class="inspector-section">
      <h4>Recorder Readiness</h4>
      <div class="status-pair"><span>Capture path</span><strong>setup -> run -> archive shell</strong></div>
      <div class="status-pair"><span>Atlas continuity</span><strong>persistent</strong></div>
      <div class="status-pair"><span>Batch handoff</span><strong>available</strong></div>
    </section>
  `;
}

function renderProgressInspector() {
  return `
    <section class="inspector-section">
      <h4>Run Handoff</h4>
      <div class="status-pair"><span>Seed</span><strong>${worldMeta.seed}</strong></div>
      <div class="status-pair"><span>Schema</span><strong>${worldMeta.schema}</strong></div>
      <div class="status-pair"><span>Interestingness estimate</span><strong id="progress-interest-side">0.19</strong></div>
      <div class="status-pair"><span>Simulation status</span><strong id="progress-status-side">Initializing topology</strong></div>
    </section>
    <section class="inspector-section">
      <h4>Pipeline</h4>
      <div class="status-pair"><span>Curator link graph</span><strong>priming</strong></div>
      <div class="status-pair"><span>Era reflections</span><strong>queued</strong></div>
      <div class="status-pair"><span>Archive shell</span><strong>preloading</strong></div>
    </section>
    <section class="inspector-section">
      <h4>Capture Note</h4>
      <div class="manifest-copy">The progress state is intentionally brief and legible. It communicates real pipeline structure, then opens directly into the viewer shell without a dead-end completion screen.</div>
    </section>
  `;
}

function renderBatchInspector() {
  const top = batchRows[state.selectedBatch];
  return `
    <section class="inspector-section">
      <h4>Selected Result</h4>
      <div class="status-pair"><span>World</span><strong>${top.world}</strong></div>
      <div class="status-pair"><span>Seed</span><strong>${top.seed}</strong></div>
      <div class="status-pair"><span>Interestingness</span><strong>${top.score}</strong></div>
      <div class="status-pair"><span>Wars</span><strong>${top.wars}</strong></div>
      <div class="status-pair"><span>Collapses</span><strong>${top.collapses}</strong></div>
      <div class="status-pair"><span>Named events</span><strong>${top.namedEvents}</strong></div>
    </section>
    <section class="inspector-section">
      <h4>Open Result</h4>
      <div class="manifest-copy">This seed is selected because it balances campaign readability, character clarity, and trade diagnostics. The same archive shell opens immediately on selection.</div>
      <button class="open-viewer-button" id="open-selected-viewer">Open in Viewer</button>
    </section>
  `;
}

function renderInspector() {
  const map = {
    setup: {
      kicker: "Launch Packet",
      title: "Scenario manifest and recorder-ready setup",
      subtitle: "Same shell, same map, same inspector. The launch surface simply occupies them.",
      body: renderSetupInspector(),
    },
    progress: {
      kicker: "Run Packet",
      title: "Simulation progress and archive handoff",
      subtitle: "Progress stays short, information-rich, and tied to the eventual viewer shell.",
      body: renderProgressInspector(),
    },
    overview: {
      kicker: "Civilization Inspector",
      title: civSummary.name,
      subtitle: "Demographics, faction influence, faith and culture composition, wealth, trade dependency, class tension, and dynastic succession in one disciplined rail.",
      body: renderOverviewInspector(),
    },
    character: {
      kicker: "Character Inspector",
      title: `${characterSummary.name} · ${characterSummary.stableId}`,
      subtitle: "Memory, needs, relationships, movement, artifact provenance, and Mule state without leaving the atlas shell.",
      body: renderCharacterInspector(),
    },
    trade: {
      kicker: "Trade Inspector",
      title: `${tradeSummary.route} · ${tradeSummary.stableId}`,
      subtitle: "Route profitability and market health presented as the same right-rail inspector, not a separate dashboard product.",
      body: renderTradeInspector(),
    },
    campaign: {
      kicker: "Campaign Inspector",
      title: `${campaignSummary.army} · ${campaignSummary.stableId}`,
      subtitle: "Army composition, march rationale, battle summary, and knowledge diagnostics under the validation ribbon.",
      body: renderCampaignInspector(),
    },
    batch: {
      kicker: "Batch Inspector",
      title: "Interestingness-ranked archive selection",
      subtitle: "Batch Lab stays inside the same application family and opens directly back into Overview.",
      body: renderBatchInspector(),
    },
  }[state.mode];

  inspectorKicker.textContent = map.kicker;
  inspectorTitle.textContent = map.title;
  inspectorSubtitle.textContent = map.subtitle;
  inspectorBody.innerHTML = map.body;
  addPanelEnter(inspectorBody);

  const openSelected = document.getElementById("open-selected-viewer");
  if (openSelected) {
    openSelected.addEventListener("click", () => {
      demo.playing = false;
      document.body.classList.add("demo-paused");
      setMode("overview");
    });
  }
}

function renderOverviewOverlay() {
  return `
    <div class="overlay-header">
      <div>
        <div class="tiny-label">Strategic Command</div>
        <div class="overlay-title">Map-first civilization overview with chronicle-linked analytics</div>
      </div>
      <div class="overlay-actions">
        <button class="mini-chip">summary</button>
        <button class="mini-chip">detail</button>
        <button class="mini-chip">overlays</button>
        <button class="mini-chip">metrics</button>
      </div>
    </div>
    <div class="summary-grid">
      <div class="summary-card"><span>Selected civ</span><strong>${civSummary.name}</strong></div>
      <div class="summary-card"><span>Interestingness</span><strong>${worldMeta.interestingness}</strong></div>
      <div class="summary-card"><span>Trade dependency</span><strong>${civSummary.tradeDependency}</strong></div>
      <div class="summary-card"><span>Class tension</span><strong>${civSummary.classTension}</strong></div>
    </div>
    <div class="callout-card">
      <h4>Era Reflection</h4>
      <div class="callout-copy">Late Decay is being held together by corridor management rather than imperial confidence. The shell emphasizes that truth by keeping the map visible while the inspector explains pressure and composition.</div>
    </div>
  `;
}

function renderSetupOverlay() {
  return `
    <div class="overlay-header">
      <div>
        <div class="tiny-label">New World</div>
        <div class="overlay-title">Front door inside the same atlas workstation</div>
      </div>
      <div class="overlay-actions">
        <button class="mini-chip">manifest</button>
        <button class="mini-chip">layers</button>
        <button class="mini-chip">summary</button>
      </div>
    </div>
    <div class="setup-grid">
      <div class="callout-card">
        <div class="summary-band">
          <h4>Generation Mode</h4>
          <div class="toggle-group dual">
            <div class="toggle-pill">Procedural</div>
            <div class="toggle-pill active">Scenario</div>
          </div>
        </div>
        <div class="form-grid">
          <div class="form-field"><span class="field-label">Scenario</span><div class="field-box"><span>${worldMeta.scenario}</span><span>▾</span></div></div>
          <div class="form-field"><span class="field-label">Seed</span><div class="field-box"><span class="mono">${worldMeta.seed}</span><span>regenerate</span></div></div>
          <div class="form-field"><span class="field-label">Turns</span><div class="field-box"><span>5000</span><span>archive preset</span></div></div>
          <div class="form-field"><span class="field-label">Civilizations</span><div class="field-box"><span>12</span><span>scenario locked</span></div></div>
          <div class="form-field"><span class="field-label">Regions</span><div class="field-box"><span>48</span><span>atlas density</span></div></div>
          <div class="form-field">
            <span class="field-label">Narration</span>
            <div class="toggle-group">
              <div class="toggle-pill">Off</div>
              <div class="toggle-pill">Local</div>
              <div class="toggle-pill active">API</div>
            </div>
          </div>
        </div>
        <div class="inline-actions">
          <button class="launch-button" id="run-world-button">Run World</button>
          <button class="ghost-button" id="open-batch-button">Batch Lab</button>
        </div>
      </div>
      <div class="callout-card">
        <h4>Scenario Summary</h4>
        <div class="mini-map-card"><div class="mini-map"></div></div>
        <div class="callout-copy">Successor marches inherit the empire's roads but not its legitimacy. Migration pressure pushes east-west, faith fractures follow logistics, and the old capital now matters mostly as memory infrastructure.</div>
        <div class="manifest-grid">
          <div class="manifest-card"><span>Civilizations</span><strong>12</strong></div>
          <div class="manifest-card"><span>Regions</span><strong>48</strong></div>
          <div class="manifest-card"><span>Faith seeds</span><strong>4</strong></div>
          <div class="manifest-card"><span>Start eras</span><strong>3</strong></div>
        </div>
      </div>
    </div>
  `;
}

function renderProgressOverlay() {
  return `
    <div class="overlay-header">
      <div>
        <div class="tiny-label">Run Progress</div>
        <div class="overlay-title">Simulation handoff into the archive viewer</div>
      </div>
      <div class="overlay-actions">
        <button class="mini-chip">seed locked</button>
        <button class="mini-chip">curator queued</button>
        <button class="mini-chip">viewer preload</button>
      </div>
    </div>
    <div class="summary-grid">
      <div class="progress-card"><span>World</span><strong>${worldMeta.world}</strong></div>
      <div class="progress-card"><span>Scenario</span><strong>${worldMeta.scenario}</strong></div>
      <div class="progress-card"><span>Seed</span><strong class="mono">${worldMeta.seed}</strong></div>
      <div class="progress-card"><span>Schema</span><strong class="mono">${worldMeta.schema}</strong></div>
    </div>
    <div class="progress-readout">
      <div class="progress-header"><div class="status-pair"><span>Turn progress</span><strong id="progress-turn-readout">0 / 5000</strong></div></div>
      <div class="progress-bar"><div class="progress-fill" id="progress-fill"></div></div>
      <div class="progress-stats">
        <div class="progress-card"><span>Simulation status</span><strong id="progress-status-card">Initializing topology</strong></div>
        <div class="progress-card"><span>Interestingness est.</span><strong id="progress-interest-card">0.19</strong></div>
        <div class="progress-card"><span>Performance</span><strong id="progress-perf-card">13.6 ms/turn</strong></div>
        <div class="progress-card"><span>Narration queue</span><strong id="progress-narration-card"><span class="pulse-dot"></span>warming</strong></div>
      </div>
    </div>
  `;
}

function renderCharacterOverlay() {
  return `
    <div class="overlay-header">
      <div>
        <div class="tiny-label">Great Person Deep-Dive</div>
        <div class="overlay-title">${characterSummary.name} · stable ID ${characterSummary.stableId}</div>
      </div>
      <div class="overlay-actions">
        <button class="mini-chip">memory</button>
        <button class="mini-chip">relationships</button>
        <button class="mini-chip">movement</button>
        <button class="mini-chip">artifacts</button>
      </div>
    </div>
    <div class="metric-grid">
      <div class="inspector-card"><span>Role</span><strong>${characterSummary.title}</strong></div>
      <div class="inspector-card"><span>Location</span><strong>${characterSummary.location}</strong></div>
      <div class="inspector-card"><span>Dynasty</span><strong>${characterSummary.dynasty}</strong></div>
      <div class="inspector-card"><span>Mule window</span><strong>${characterSummary.muleTurns} turns</strong></div>
    </div>
    <div class="memory-line">
      <div class="memory-node shock"><strong>Siege of Greyfen</strong><div class="metric-note">Intensity 0.91 · war</div></div>
      <div class="memory-node"><strong>Convoy famine winter</strong><div class="metric-note">Intensity 0.68 · scarcity</div></div>
      <div class="memory-node legacy"><strong>Alder Moot oath</strong><div class="metric-note">Legacy marker · dynasty</div></div>
      <div class="memory-node"><strong>Kestrel compromise</strong><div class="metric-note">Intensity 0.44 · trade</div></div>
    </div>
    <div class="route-inspector-split">
      <div class="radar-shell">
        <div class="tiny-label">6-axis needs radar</div>
        <svg class="radar-svg" viewBox="0 0 240 220">
          <polygon class="radar-grid" points="120,24 197,70 197,150 120,196 43,150 43,70"></polygon>
          <polygon class="radar-grid" points="120,48 178,82 178,138 120,172 62,138 62,82"></polygon>
          <polygon class="radar-grid" points="120,72 159,94 159,126 120,148 81,126 81,94"></polygon>
          <polygon class="radar-shape" points="120,56 180,92 164,150 120,168 86,134 74,86"></polygon>
          <text x="108" y="16">Safety</text><text x="194" y="72">Duty</text><text x="192" y="160">Belonging</text>
          <text x="106" y="212">Autonomy</text><text x="8" y="160">Status</text><text x="6" y="74">Meaning</text>
        </svg>
      </div>
      <div class="graph-shell">
        <div class="tiny-label">Relationship graph</div>
        <svg class="graph-svg" viewBox="0 0 240 220">
          <line x1="118" y1="104" x2="56" y2="56"></line><line x1="118" y1="104" x2="188" y2="70"></line>
          <line x1="118" y1="104" x2="76" y2="176"></line><line x1="118" y1="104" x2="180" y2="164"></line>
          <circle class="graph-node primary" cx="118" cy="104" r="18"></circle>
          <circle class="graph-node" cx="56" cy="56" r="12"></circle><circle class="graph-node" cx="188" cy="70" r="12"></circle>
          <circle class="graph-node" cx="76" cy="176" r="12"></circle><circle class="graph-node" cx="180" cy="164" r="12"></circle>
          <text x="95" y="109">Eadric</text><text x="27" y="52">Ysabet</text><text x="170" y="66">Brother Calve</text>
          <text x="42" y="194">Caedmon</text><text x="164" y="183">Marshal Oren</text>
        </svg>
      </div>
    </div>
    <div class="route-inspector-split">
      <div class="callout-card">
        <h4>Dynastic Strip</h4>
        <div class="dynasty-strip">
          <div class="dynasty-node"><strong>Alda II</strong><div class="metric-note">collapsed</div></div>
          <div class="dynasty-node"><strong>Merek</strong><div class="metric-note">line break</div></div>
          <div class="dynasty-node"><strong>Eadric</strong><div class="metric-note">active regency</div></div>
          <div class="dynasty-node"><strong>Caedmon</strong><div class="metric-note">heir presumptive</div></div>
        </div>
      </div>
      <div class="callout-card">
        <h4>Artifact Provenance</h4>
        <div class="artifact-strip">
          <div class="artifact-node"><strong>Alder Moot</strong><div class="metric-note">forged</div></div>
          <div class="artifact-node"><strong>Greyfen Vault</strong><div class="metric-note">hidden</div></div>
          <div class="artifact-node"><strong>Marshal Oren</strong><div class="metric-note">held</div></div>
          <div class="artifact-node"><strong>Eadric</strong><div class="metric-note">current holder</div></div>
        </div>
      </div>
    </div>
    <div class="movement-inset">
      <div class="tiny-label">Movement inset</div>
      <svg class="movement-svg" viewBox="0 0 320 120">
        <rect x="12" y="14" width="296" height="92" rx="14" fill="rgba(255,255,255,0.03)" stroke="rgba(255,255,255,0.05)"></rect>
        <path class="movement-path" d="M 42 86 C 82 78 132 62 168 56 S 246 48 286 24"></path>
        <circle class="movement-point" cx="42" cy="86" r="5"></circle><circle class="movement-point" cx="102" cy="70" r="5"></circle>
        <circle class="movement-point" cx="168" cy="56" r="5"></circle><circle class="movement-point" cx="238" cy="44" r="5"></circle>
        <circle class="movement-point" cx="286" cy="24" r="6"></circle>
        <text x="34" y="103">Thornwall</text><text x="152" y="78">Greyfen</text><text x="256" y="46">Kestrel</text>
      </svg>
    </div>
  `;
}

function renderTradeOverlay() {
  return `
    <div class="overlay-header">
      <div>
        <div class="tiny-label">Logistics Observability</div>
        <div class="overlay-title">${tradeSummary.route} highlighted across markets and beliefs</div>
      </div>
      <div class="selection-chips">
        <button class="mini-chip">route inspection</button>
        <button class="mini-chip">market inspection</button>
        <button class="mini-chip">belief freshness</button>
      </div>
    </div>
    <div class="route-inspector-split">
      <div class="callout-card">
        <h4>Route Diagnostics</h4>
        <div class="metric-stack">
          <div class="status-pair"><span>Profit</span><strong>${tradeSummary.routeProfit}</strong></div>
          <div class="status-pair"><span>Margin</span><strong>${tradeSummary.routeMargin}</strong></div>
          <div class="status-pair"><span>Stale vs current beliefs</span><strong>${tradeSummary.staleBelief} / ${tradeSummary.currentBelief}</strong></div>
          <div class="status-pair"><span>Merchant plan</span><strong>${tradeSummary.merchantPlan}</strong></div>
          <div class="status-pair"><span>Confidence</span><strong>${tradeSummary.confidence}</strong></div>
          <div class="status-pair"><span>Freshness</span><strong>${tradeSummary.freshness}</strong></div>
        </div>
      </div>
      <div class="callout-card">
        <h4>Market Diagnostics</h4>
        <div class="sparkline-box">
          <div class="tiny-label">Stockpile trend</div>
          <svg class="sparkline-svg" viewBox="0 0 280 100">
            <path class="sparkline-path" d="M 10 78 C 42 68 74 60 98 58 S 150 42 184 38 S 228 30 270 26"></path>
            <text x="8" y="92">Food</text><text x="226" y="18">rising 6 turns</text>
          </svg>
        </div>
        <div class="metric-stack">
          <div class="status-pair"><span>Supply / demand</span><strong>${tradeSummary.supplyDemand}</strong></div>
          <div class="status-pair"><span>Food sufficiency</span><strong>${tradeSummary.foodSufficiency}</strong></div>
          <div class="status-pair"><span>Import share</span><strong>${tradeSummary.importShare}</strong></div>
          <div class="status-pair"><span>Trade dependency</span><strong>${tradeSummary.tradeDependency}</strong></div>
          <div class="status-pair"><span>Settlement role</span><strong>${tradeSummary.settlementRole}</strong></div>
        </div>
      </div>
    </div>
  `;
}

function renderCampaignOverlay() {
  return `
    <div class="overlay-header">
      <div>
        <div class="tiny-label">Military Intelligence</div>
        <div class="overlay-title">Campaign view with validation ribbon and march timeline</div>
      </div>
      <div class="selection-chips">
        <button class="mini-chip">fronts</button>
        <button class="mini-chip">supply</button>
        <button class="mini-chip">knowledge</button>
        <button class="mini-chip">asabiya</button>
      </div>
    </div>
    <div class="metric-grid">
      <div class="inspector-card"><span>Army</span><strong>${campaignSummary.army}</strong></div>
      <div class="inspector-card"><span>Morale</span><strong>${campaignSummary.morale}</strong></div>
      <div class="inspector-card"><span>Supply</span><strong>${campaignSummary.supply}</strong></div>
      <div class="inspector-card"><span>Freshness</span><strong>${campaignSummary.freshness}</strong></div>
    </div>
    <div class="callout-card">
      <h4>March Timeline</h4>
      <div class="march-strip">
        <div class="march-node"><strong>Greyfen</strong><div class="metric-note">assembly</div></div>
        <div class="march-node"><strong>Halewatch</strong><div class="metric-note">raid screened</div></div>
        <div class="march-node"><strong>Saint's Ford</strong><div class="metric-note">front held</div></div>
        <div class="march-node"><strong>Orchard road</strong><div class="metric-note">target corridor</div></div>
      </div>
    </div>
    <div class="callout-card">
      <h4>Knowledge Diagnostics</h4>
      <div class="callout-copy">Fresh local reports remain strong west of the front, while eastward familiarity decays under raid disruption. The fog overlay and inspector numbers stay tightly linked.</div>
    </div>
  `;
}

function renderBatchOverlay() {
  return `
    <div class="overlay-header">
      <div>
        <div class="tiny-label">Batch Lab</div>
        <div class="overlay-title">Interestingness-ranked runs with compare and direct open affordance</div>
      </div>
      <div class="overlay-actions">
        <button class="mini-chip">ranked</button>
        <button class="mini-chip">compare</button>
        <button class="mini-chip">open selected</button>
      </div>
    </div>
    <div class="batch-table-header">
      <span>Seed</span><span>Score</span><span>Wars</span><span>Collapses</span>
      <span>Named events</span><span>Tech movement</span><span>Anomalies</span><span>Action</span>
    </div>
    <div class="batch-table">
      ${batchRows.map((row, index) => `
        <div class="batch-row ${index === state.selectedBatch ? "selected" : ""}" data-batch-index="${index}">
          <strong class="mono">${row.seed}</strong>
          <span class="score-pill">${row.score}</span>
          <strong>${row.wars}</strong>
          <strong>${row.collapses}</strong>
          <strong>${row.namedEvents}</strong>
          <strong>${row.techMovement}</strong>
          <strong>${row.anomalies}</strong>
          <button class="compare-toggle">${index === state.selectedBatch ? "Selected" : "Open"}</button>
        </div>
      `).join("")}
    </div>
    <div class="compare-row">
      <div class="compare-card">
        <h4>Side-by-side compare</h4>
        <div class="batch-meta">Rank 1 stays stronger on named character clarity and campaign legibility. Rank 2 recovers logistics faster but produces a flatter late-decay arc.</div>
      </div>
      <div class="compare-card">
        <h4>Selection note</h4>
        <div class="batch-meta">Opening the top-ranked run returns immediately to the main archive shell without leaving the application frame.</div>
      </div>
    </div>
  `;
}

function renderOverlay() {
  const map = {
    setup: {
      kicker: "Setup Surface",
      title: "Unified shell with launch, archive, and observability modes",
      overlay: renderSetupOverlay(),
      railTitle: "Launch Corridor and Archive Context",
      railChip: "setup aligned",
    },
    progress: {
      kicker: "Run Surface",
      title: "Short, polished progress state before archive handoff",
      overlay: renderProgressOverlay(),
      railTitle: "Runtime progress and archive preload",
      railChip: "handoff warming",
    },
    overview: {
      kicker: "Strategic Command",
      title: "Overview anchors the reusable viewer shell",
      overlay: renderOverviewOverlay(),
      railTitle: "Era boundaries, narrated spans, and causal arcs",
      railChip: `turn ${state.turn} pinned`,
    },
    character: {
      kicker: "Great Person Deep-Dive",
      title: "Character detail within the same atlas shell",
      overlay: renderCharacterOverlay(),
      railTitle: "Character memory and timeline context",
      railChip: `memory focus ${characterSummary.stableId}`,
    },
    trade: {
      kicker: "Logistics Observability",
      title: "Trade mode reuses the shell and lets the map stay heroic",
      overlay: renderTradeOverlay(),
      railTitle: "Trade spans, market shocks, and route causality",
      railChip: `${tradeSummary.route} active`,
    },
    campaign: {
      kicker: "Campaign & Validation",
      title: "Operational map with validation ribbon and knowledge fog",
      overlay: renderCampaignOverlay(),
      railTitle: "Campaign path and validation context",
      railChip: `${campaignSummary.army} selected`,
    },
    batch: {
      kicker: "Batch Lab",
      title: "Interestingness ranking and direct open within the same app family",
      overlay: renderBatchOverlay(),
      railTitle: "Batch ranking and archive handoff",
      railChip: "rank 1 pinned",
    },
  }[state.mode];

  viewportKicker.textContent = map.kicker;
  viewportTitle.textContent = map.title;
  railTitle.textContent = map.railTitle;
  railChipLive.textContent = map.railChip;
  mapOverlay.innerHTML = map.overlay;
  addPanelEnter(mapOverlay);

  Array.from(mapOverlay.querySelectorAll("[data-batch-index]")).forEach((row) => {
    row.addEventListener("click", () => {
      state.selectedBatch = Number(row.getAttribute("data-batch-index"));
      renderOverlay();
      renderInspector();
    });
  });

  const runWorldButton = document.getElementById("run-world-button");
  if (runWorldButton) {
    runWorldButton.addEventListener("click", () => {
      demo.playing = false;
      document.body.classList.add("demo-paused");
      setMode("progress");
    });
  }

  const openBatchButton = document.getElementById("open-batch-button");
  if (openBatchButton) {
    openBatchButton.addEventListener("click", () => {
      demo.playing = false;
      document.body.classList.add("demo-paused");
      setMode("batch");
    });
  }
}

function renderValidationRibbon() {
  if (state.mode !== "campaign") {
    validationRibbon.classList.remove("active");
    validationRibbon.innerHTML = "";
    return;
  }

  validationRibbon.classList.add("active");
  validationRibbon.innerHTML = validationPills
    .map(([title, value]) => `
      <div class="validation-pill">
        <strong>${title}</strong>
        <span>${value}</span>
      </div>
    `)
    .join("");
}

function renderTrack() {
  const turnValue = state.mode === "progress" ? Math.max(state.progressTurn, 1) : state.turn;
  playhead.style.left = `${pctFromTurn(turnValue)}%`;
  playheadLabel.textContent = `${turnValue}`;
  turnReadout.textContent = `${turnValue} / ${worldMeta.totalTurns}`;
  interestingnessReadout.textContent = state.mode === "progress"
    ? (0.19 + state.progress * 0.54).toFixed(2)
    : worldMeta.interestingness.toFixed(2);
  performanceReadout.textContent = state.mode === "progress"
    ? `${(13.6 + state.progress * 0.6).toFixed(1)} ms/turn`
    : worldMeta.performance;
}

function renderMapLayers() {
  app.dataset.mode = state.mode;
  Object.entries(state.layers).forEach(([key, value]) => {
    app.dataset[`layer${key.charAt(0).toUpperCase()}${key.slice(1)}`] = value ? "on" : "off";
  });
  layerChips.forEach((chip) => {
    const layer = chip.getAttribute("data-layer");
    chip.classList.toggle("active", Boolean(state.layers[layer]));
  });
}

function renderModeChrome() {
  demoStateLabel.textContent = stateLabels[state.mode];
  modeSwitches.forEach((btn) => btn.classList.toggle("active", btn.getAttribute("data-state") === state.mode));
  jumpPills.forEach((btn) => btn.classList.toggle("active", btn.getAttribute("data-state") === state.mode));
  flowSteps.forEach((step) => step.classList.toggle("active", step.getAttribute("data-state") === state.mode));
  railTabs.forEach((tab) => tab.classList.toggle("active", tab.getAttribute("data-left-tab") === state.leftTab));
}

function renderHover() {
  const region = regions[state.hoverRegion] || regions.greyfen;
  hoverTitle.textContent = region.title;
  hoverCopy.textContent = region.copy;
  hoverCard.style.opacity = state.mode === "progress" ? "0.2" : "1";
  hoverCard.style.transform = state.mode === "progress" ? "translateY(-4px)" : "translateY(0)";
}

function renderProgressSide() {
  const fill = document.getElementById("progress-fill");
  const turnNode = document.getElementById("progress-turn-readout");
  const statusCard = document.getElementById("progress-status-card");
  const interestCard = document.getElementById("progress-interest-card");
  const perfCard = document.getElementById("progress-perf-card");
  const narrationCard = document.getElementById("progress-narration-card");
  const statusSide = document.getElementById("progress-status-side");
  const interestSide = document.getElementById("progress-interest-side");

  if (!fill) {
    return;
  }

  const statusMessages = [
    "Initializing topology",
    "Resolving settlement seeds",
    "Running political cascade",
    "Curating named events",
    "Assembling archive shell",
  ];
  const progressIndex = Math.min(statusMessages.length - 1, Math.floor(state.progress * statusMessages.length));
  const interest = (0.19 + state.progress * 0.54).toFixed(2);
  const perf = `${(13.6 + state.progress * 0.6).toFixed(1)} ms/turn`;

  fill.style.width = `${Math.round(state.progress * 100)}%`;
  turnNode.textContent = `${state.progressTurn} / ${worldMeta.totalTurns}`;
  statusCard.textContent = statusMessages[progressIndex];
  interestCard.textContent = interest;
  perfCard.textContent = perf;
  narrationCard.innerHTML = state.progress > 0.7
    ? "<span class=\"pulse-dot\"></span>readying reflections"
    : "<span class=\"pulse-dot\"></span>warming";

  if (statusSide) statusSide.textContent = statusMessages[progressIndex];
  if (interestSide) interestSide.textContent = interest;
}

function updateArmyPosition() {
  const points = [
    [706, 252],
    [724, 310],
    [748, 350],
    [770, 388],
    [792, 454],
    [820, 514],
  ];
  const scaled = state.armyPhase * (points.length - 1);
  const low = Math.floor(scaled);
  const high = Math.min(points.length - 1, low + 1);
  const t = scaled - low;
  const [x1, y1] = points[low];
  const [x2, y2] = points[high];
  const x = x1 + (x2 - x1) * t;
  const y = y1 + (y2 - y1) * t;
  armyChip.setAttribute("transform", `translate(${x.toFixed(1)} ${y.toFixed(1)})`);
}

function renderAll() {
  renderModeChrome();
  renderMapLayers();
  renderRail();
  renderInspector();
  renderOverlay();
  renderValidationRibbon();
  renderTrack();
  renderHover();
  updateArmyPosition();
  renderProgressSide();
}

function setMode(mode) {
  state.mode = mode;

  if (mode === "overview") {
    state.turn = worldMeta.turn;
    state.hoverRegion = "greyfen";
    state.layers.trade = true;
    state.layers.campaign = false;
    state.layers.fog = false;
    state.layers.asabiya = false;
  }
  if (mode === "character") {
    state.turn = 3886;
    state.hoverRegion = "greyfen";
    state.layers.trade = true;
    state.layers.campaign = false;
    state.layers.fog = false;
    state.layers.asabiya = false;
  }
  if (mode === "trade") {
    state.turn = 3812;
    state.hoverRegion = "kestrel";
    state.layers.trade = true;
    state.layers.campaign = false;
    state.layers.fog = false;
    state.layers.asabiya = false;
  }
  if (mode === "campaign") {
    state.turn = 3812;
    state.hoverRegion = "saltstep";
    state.layers.trade = true;
    state.layers.campaign = true;
    state.layers.fog = true;
    state.layers.asabiya = true;
  }
  if (mode === "batch") {
    state.turn = worldMeta.turn;
    state.hoverRegion = "greyfen";
    state.layers.trade = false;
    state.layers.campaign = false;
    state.layers.fog = false;
    state.layers.asabiya = false;
  }
  if (mode === "setup") {
    state.hoverRegion = "greyfen";
    state.layers.trade = false;
    state.layers.campaign = false;
    state.layers.fog = false;
    state.layers.asabiya = false;
  }
  if (mode === "progress") {
    state.progress = 0;
    state.progressTurn = 0;
    state.layers.trade = false;
    state.layers.campaign = false;
    state.layers.fog = false;
    state.layers.asabiya = false;
  }

  renderAll();
}

function updateDemo(stepKey, progress) {
  if (state.mode !== stepKey) {
    setMode(stepKey);
  }

  let nextLeftTab = state.leftTab;
  let nextHoverRegion = state.hoverRegion;
  let nextSelectedBatch = state.selectedBatch;

  switch (stepKey) {
    case "setup":
      nextLeftTab = progress > 0.55 ? "events" : "chronicle";
      nextHoverRegion = progress > 0.45 ? "thornwall" : "greyfen";
      break;
    case "progress":
      state.progress = Math.min(progress * 0.76, 0.76);
      state.progressTurn = Math.round(worldMeta.turn * state.progress / 0.76);
      break;
    case "overview":
      nextLeftTab = progress > 0.6 ? "events" : "chronicle";
      state.turn = Math.round(3670 + (worldMeta.turn - 3670) * progress);
      nextHoverRegion = progress > 0.62 ? "kestrel" : "greyfen";
      break;
    case "character":
      nextLeftTab = progress > 0.52 ? "events" : "chronicle";
      state.turn = 3880 + Math.round(progress * 6);
      nextHoverRegion = "greyfen";
      break;
    case "trade":
      nextLeftTab = progress > 0.56 ? "events" : "chronicle";
      state.turn = 3802 + Math.round(progress * 10);
      nextHoverRegion = progress > 0.48 ? "kestrel" : "greyfen";
      break;
    case "campaign":
      nextLeftTab = progress > 0.58 ? "events" : "chronicle";
      state.armyPhase = progress;
      state.turn = 3798 + Math.round(progress * 14);
      nextHoverRegion = progress > 0.45 ? "saltstep" : "lastorchard";
      break;
    case "batch":
      nextLeftTab = progress > 0.5 ? "events" : "chronicle";
      nextSelectedBatch = progress > 0.62 ? 0 : 1;
      break;
    default:
      break;
  }

  if (nextLeftTab !== state.leftTab) {
    state.leftTab = nextLeftTab;
    renderModeChrome();
    renderRail();
  }

  if (nextHoverRegion !== state.hoverRegion) {
    state.hoverRegion = nextHoverRegion;
    renderHover();
  }

  if (nextSelectedBatch !== state.selectedBatch) {
    state.selectedBatch = nextSelectedBatch;
    renderOverlay();
    renderInspector();
  }

  renderTrack();
  renderHover();
  updateArmyPosition();
  renderProgressSide();
}

function frame(ts) {
  if (demo.lastTs === null) {
    demo.lastTs = ts;
  }

  if (demo.playing) {
    const delta = ts - demo.lastTs;
    demo.stepElapsed += delta;
    const step = demoTimeline[demo.stepIndex];
    const progress = Math.min(1, demo.stepElapsed / step.duration);
    updateDemo(step.key, progress);

    if (demo.stepElapsed >= step.duration) {
      demo.stepIndex += 1;
      demo.stepElapsed = 0;
      if (demo.stepIndex >= demoTimeline.length) {
        demo.stepIndex = demoTimeline.length - 1;
        demo.playing = false;
        document.body.classList.add("demo-paused");
      }
    }
  }

  demo.lastTs = ts;
  requestAnimationFrame(frame);
}

function pauseDemo() {
  demo.playing = false;
  document.body.classList.add("demo-paused");
}

function playDemo() {
  demo.playing = true;
  document.body.classList.remove("demo-paused");
}

function restartDemo() {
  demo.stepIndex = 0;
  demo.stepElapsed = 0;
  demo.lastTs = null;
  playDemo();
}

document.getElementById("demo-play").addEventListener("click", playDemo);
document.getElementById("demo-pause").addEventListener("click", pauseDemo);
document.getElementById("demo-restart").addEventListener("click", restartDemo);

document.addEventListener("keydown", (event) => {
  if (event.code === "Space") {
    event.preventDefault();
    if (demo.playing) pauseDemo();
    else playDemo();
  }
});

modeSwitches.forEach((button) => {
  button.addEventListener("click", () => {
    pauseDemo();
    setMode(button.getAttribute("data-state"));
  });
});

jumpPills.forEach((button) => {
  button.addEventListener("click", () => {
    pauseDemo();
    setMode(button.getAttribute("data-state"));
  });
});

railTabs.forEach((button) => {
  button.addEventListener("click", () => {
    railTabs.forEach((tab) => tab.classList.remove("active"));
    button.classList.add("active");
    state.leftTab = button.getAttribute("data-left-tab");
    renderRail();
  });
});

layerChips.forEach((button) => {
  button.addEventListener("click", () => {
    const layer = button.getAttribute("data-layer");
    state.layers[layer] = !state.layers[layer];
    renderMapLayers();
  });
});

regionNodes.forEach((node) => {
  node.addEventListener("mouseenter", () => {
    state.hoverRegion = node.getAttribute("data-region");
    renderHover();
  });
});

trackMarkers.forEach((marker) => {
  marker.addEventListener("click", (event) => {
    event.stopPropagation();
    pauseDemo();
    state.turn = Number(marker.getAttribute("data-turn"));
    renderTrack();
  });
});

turnTrack.addEventListener("click", (event) => {
  pauseDemo();
  const rect = turnTrack.getBoundingClientRect();
  const pct = Math.min(1, Math.max(0, (event.clientX - rect.left) / rect.width));
  state.turn = Math.max(1, Math.round(pct * (worldMeta.totalTurns - 1)) + 1);
  if (state.mode === "campaign") {
    state.armyPhase = Math.min(1, Math.max(0, (state.turn - 3798) / 14));
    updateArmyPosition();
  }
  renderTrack();
});

eadricMarker.addEventListener("click", () => {
  pauseDemo();
  setMode("character");
});

armyChip.addEventListener("click", () => {
  pauseDemo();
  setMode("campaign");
});

tradeRoutes.forEach((route) => {
  route.addEventListener("click", () => {
    pauseDemo();
    state.routeFocus = route.getAttribute("data-route");
    setMode("trade");
  });
});

renderAll();
requestAnimationFrame(frame);
