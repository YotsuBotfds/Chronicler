/**
 * Read-only helpers for the simulation systems carried by a bundle's history
 * snapshots (`history[n].epidemics`, `.finance`, `.diplomacy`, `.techniques`,
 * `.maritime`, `.campaign`, `.food`, `.nomads`, `.gp_agendas`, `.contact`,
 * `.cities`, `.agent_movements`, `.scholarship`,
 * civ rows' `governance`) and its event timeline. Nothing here infers a value
 * the bundle does not record: missing snapshots stay missing. Helpers for the
 * later systems live in `food.ts`, `wars.ts` and `polity.ts`.
 */
import type {
  Bundle,
  Event,
  EpidemicOutbreak,
  TechEra,
  TurnSnapshot,
} from "../types";
import { typedEventsUpTo } from "./bundleIndex";
import { ERA_LABELS, ERA_ORDER } from "./format";
import { MOVEMENT_EVENT_TYPES } from "./movementEvents";

export type SystemKey =
  | "epidemics"
  | "food"
  | "wars"
  | "finance"
  | "diplomacy"
  | "techniques"
  | "maritime"
  | "nomads"
  | "agendas"
  | "governance"
  | "contact"
  | "cities"
  | "movements"
  | "faiths"
  | "learning";

/** What every system panel receives from the shell. */
export interface SystemPanelProps {
  bundle: Bundle;
  /** The snapshot the shell shows for the scrubbed turn (latest at or before it). */
  snapshot: TurnSnapshot | null;
  currentTurn: number;
  onSeek: (turn: number) => void;
  onSelectEvent: (event: Event) => void;
  onSelectRegion: (region: string) => void;
  onSelectCivilization: (civ: string) => void;
  selectedRegion?: string | null;
  selectedCivilization?: string | null;
}

/** The system a shell surface opens on when the viewer has not picked one. */
export function preferredSystem(surface: string, present: SystemKey[]): SystemKey | null {
  const preferences: Record<string, SystemKey[]> = {
    trade: ["finance", "contact", "maritime"],
    campaign: ["wars", "diplomacy", "maritime"],
    character: ["techniques", "agendas", "governance", "diplomacy"],
  };
  for (const key of preferences[surface] ?? []) {
    if (present.includes(key)) {
      return key;
    }
  }
  return present[0] ?? null;
}

/** First recorded turn and the turn after the last one. */
export function recordedSpan(history: TurnSnapshot[]): { first: number; end: number } {
  const first = history[0]?.turn ?? 1;
  const last = history[history.length - 1]?.turn ?? first;
  return { first, end: last + 1 };
}

/** Display order of the systems panel tabs. */
export const SYSTEM_KEYS: SystemKey[] = [
  "epidemics", "food", "wars", "finance", "diplomacy", "techniques", "maritime", "nomads", "agendas", "governance",
  "contact", "cities", "movements", "faiths", "learning",
];

export const SYSTEM_LABELS: Record<SystemKey, string> = {
  epidemics: "Epidemics",
  food: "Food",
  wars: "Wars",
  finance: "Finance",
  diplomacy: "Diplomacy",
  techniques: "Techniques",
  maritime: "Maritime",
  nomads: "Nomads",
  agendas: "Agendas",
  governance: "Governance",
  contact: "Contact",
  cities: "Cities",
  movements: "Movements",
  faiths: "Faiths",
  learning: "Learning",
};

/** Snapshot field each system writes (governance lives on civ rows; food may come from events alone). */
const SNAPSHOT_FIELDS: Partial<Record<SystemKey, keyof TurnSnapshot>> = {
  epidemics: "epidemics",
  food: "food",
  wars: "campaign",
  finance: "finance",
  diplomacy: "diplomacy",
  techniques: "techniques",
  maritime: "maritime",
  nomads: "nomads",
  agendas: "gp_agendas",
  contact: "contact",
  cities: "cities",
  movements: "agent_movements",
  learning: "scholarship",
};

/**
 * Systems the bundle records, in tab order: a snapshot field in at least one
 * snapshot, governance stats on a civ row, or (food) famine events that name
 * their region and episode (bundle version 4+).
 */
export function presentSystems(history: TurnSnapshot[], events: Event[] = [], faiths = false): SystemKey[] {
  return SYSTEM_KEYS.filter((key) => {
    if (key === "faiths") {
      // The caller reads the faith table (lib/faiths `hasFaithRecord`, kept
      // out of the entry chunk): permanent faith ids, or an older bundle
      // whose record holds a schism.
      return faiths || history.some((snapshot) => snapshot.ritual_gatherings != null);
    }
    if (key === "governance") {
      return history.some((snapshot) => Object.values(snapshot.civ_stats).some((row) => row.governance != null));
    }
    const field = SNAPSHOT_FIELDS[key];
    if (field && history.some((snapshot) => snapshot[field] != null)) {
      return true;
    }
    if (key === "epidemics" && history.some((snapshot) => snapshot.health_care != null)) {
      return true;
    }
    if (key === "learning" && history.some((snapshot) => snapshot.scientific_claims != null)) return true;
    if (key === "food" && history.some((snapshot) => snapshot.grain_reserves != null || snapshot.harvest_forecasts != null || snapshot.transaction_receipts != null)) {
      return true;
    }
    return key === "food" && events.some((event) => (event.event_type === "famine" || event.event_type === "dearth")
      && !!event.region && !!event.episode);
  });
}

/** Event types each system emits (see each system's doc in docs/integration/). */
export const SYSTEM_EVENT_TYPES: Record<SystemKey, readonly string[]> = {
  epidemics: [
    "epidemic_arrival", "epidemic", "epidemic_ended", "pathogen_mutation", "quarantine", "quarantine_ended",
    "occupational_injury",
  ],
  finance: ["loan_taken", "state_default", "debasement", "debt_written_off"],
  diplomacy: [
    "treaty_signed", "treaty_renewed", "treaty_expired", "treaty_broken", "call_to_arms", "aid_convoy",
    "vassalization", "vassal_promoted", "vassal_loosened", "union_annexation",
  ],
  techniques: ["technique_invented", "technique_adopted", "technique_lost", "tech_advancement", "tech_regression"],
  maritime: [
    "fleet_commissioned", "fleet_storm", "fleet_lost", "naval_battle", "sea_control", "sea_contested",
    "sea_control_lost", "blockade", "blockade_lifted", "piracy", "piracy_ended", "amphibious_landing",
  ],
  food: [
    "famine", "famine_ended", "dearth", "dearth_ended", "aid_convoy", "mutual_aid", "locust_swarm",
    "fishery_collapse", "fishery_recovery",
    "granary_opened", "granary_exhausted", "grain_bought",
    "harvest_forecast_issued", "harvest_forecast_delivered", "harvest_forecast_resolved", "harvest_preparedness",
  ],
  wars: [
    "war_declared", "peace_treaty", "war_ended", "army_raised", "army_destroyed", "siege_begun", "occupation",
    "occupation_revolt", "liberation", "civ_conquered", "annexation", "general_fallen", "scorched_earth",
    "congress_peace", "congress_ceasefire", "congress_collapse",
  ],
  nomads: [
    "raid", "raid_repulsed", "tribute_agreed", "tribute_ended", "horde_formed", "horde_rides", "horde_fragmented",
    "horde_dissolved", "dzud", "pasture_drought", "pasture_abandoned", "sedentarization",
  ],
  agendas: [
    "agenda_declared", "agenda_fulfilled", "agenda_failed", "war_agitation", "campaign_victory", "gp_coup",
    "gp_coup_failed", "trade_mission", "trading_house_founded", "crown_loan", "preaching", "shrine_commissioned",
    "shrine_consecrated", "gp_alliance_formed", "gp_rivalry_formed", "succession_backed",
  ],
  governance: [
    "government_transition", "psi_crisis", "psi_recovery", "institution_enacted", "institution_repealed",
    "institution_enforcement_lapse", "institutional_regime_shift", "elite_overproduction", "legitimacy_crisis",
    "revolt", "reform_pressure", "ambition_declared", "ambition_fulfilled", "ambition_failed", "secession_suppressed",
  ],
  contact: ["embargo", "first_contact"],
  cities: [
    "city_founded", "city_grew", "city_declined", "city_fell", "city_lord_changed", "city_charter",
    "charter_refused", "urban_revolt", "urban_concession", "revolt_suppressed", "free_city", "city_sacked",
    "city_walls",
    // Guilds (--guilds).
    "guild_founded", "guild_privilege", "guild_privilege_lost", "guild_levy", "guild_dissolved",
  ],
  movements: MOVEMENT_EVENT_TYPES,
  learning: [
    "seat_founded", "seat_rose", "seat_declined", "seat_patron", "seat_master", "seat_fell", "scholars_fled",
  ],
  faiths: ["Schism", "Reformation", "temple_destroyed", "Persecution", "harvest_gathering_held", "harvest_gathering_cancelled"],
};

/**
 * Events of the given types up to `upToTurn`, latest first (stable within a
 * turn). The timeline is indexed once per array (`lib/bundleIndex`).
 */
export function eventsOfTypes(events: Event[], types: readonly string[], upToTurn: number): Event[] {
  return typedEventsUpTo(events, types, upToTurn);
}

// --- Turn strips (run-length segments over the recorded snapshots) ---

export interface TurnSegment {
  /** First turn of the segment. */
  start: number;
  /** Turn after the segment ends (the next snapshot's turn, or the last turn + 1). */
  end: number;
  key: string;
  /** Snapshot indices covered, inclusive. */
  from: number;
  to: number;
}

/**
 * Merge consecutive snapshots with the same key. A snapshot covers the turns
 * up to the next snapshot; `null` keys (nothing recorded) are gaps.
 */
export function buildSegments(turns: number[], keys: Array<string | null>): TurnSegment[] {
  const segments: TurnSegment[] = [];
  for (let index = 0; index < turns.length; index += 1) {
    const key = keys[index];
    if (key == null) {
      continue;
    }
    const end = index + 1 < turns.length ? turns[index + 1] : turns[index] + 1;
    const previous = segments[segments.length - 1];
    if (previous && previous.key === key && previous.to === index - 1) {
      previous.end = end;
      previous.to = index;
    } else {
      segments.push({ start: turns[index], end, key, from: index, to: index });
    }
  }
  return segments;
}

export interface StripSegment {
  start: number;
  end: number;
  color: string;
  /** Hover text: what the segment is and the turns it covers. */
  label: string;
  /** Short text drawn inside the segment when it is wide enough. */
  text?: string;
  textColor?: string;
}

export interface StripRow {
  id: string;
  label: string;
  swatch?: string;
  segments: StripSegment[];
  /** Thin marks drawn under the row (for example blockades). */
  marks?: StripSegment[];
}

// --- Epidemics ---

/** Pathogens in the simulation's registry order (`epidemiology.PATHOGENS`). */
export const PATHOGEN_ORDER = ["plague", "pox", "fever", "flux", "pestilence"] as const;

export const PATHOGEN_LABELS: Record<string, string> = {
  plague: "Plague",
  pox: "Pox",
  fever: "Marsh fever",
  flux: "Bloody flux",
  pestilence: "Great pestilence",
};

/** Categorical slots, fixed per pathogen (validated for the dark surface). */
export const PATHOGEN_COLORS: Record<string, string> = {
  plague: "#3987e5",
  pox: "#d95926",
  fever: "#199e70",
  flux: "#c98500",
  pestilence: "#d55181",
};

export const OTHER_COLOR = "#898781";

export function pathogenLabel(name: string): string {
  return PATHOGEN_LABELS[name] ?? name;
}

export function pathogenColor(name: string): string {
  return PATHOGEN_COLORS[name] ?? OTHER_COLOR;
}

function pathogenRank(name: string): number {
  const rank = (PATHOGEN_ORDER as readonly string[]).indexOf(name);
  return rank === -1 ? PATHOGEN_ORDER.length : rank;
}

export function formatShare(value: number, digits = 1): string {
  return `${(value * 100).toFixed(digits)}%`;
}

/** One row per (region, pathogen) that ever had a reportable outbreak, in region index order. */
export function epidemicRows(history: TurnSnapshot[], regionOrder: string[]): StripRow[] {
  const turns = history.map((snapshot) => snapshot.turn);
  const pairs = new Map<string, { region: string; pathogen: string }>();
  for (const snapshot of history) {
    for (const outbreak of snapshot.epidemics?.active ?? []) {
      pairs.set(`${outbreak.region}\u0000${outbreak.pathogen}`, { region: outbreak.region, pathogen: outbreak.pathogen });
    }
  }
  const regionRank = new Map(regionOrder.map((name, index) => [name, index]));
  const ordered = [...pairs.values()].sort((left, right) =>
    (regionRank.get(left.region) ?? Number.MAX_SAFE_INTEGER) - (regionRank.get(right.region) ?? Number.MAX_SAFE_INTEGER)
    || pathogenRank(left.pathogen) - pathogenRank(right.pathogen)
    || left.region.localeCompare(right.region));

  return ordered.map(({ region, pathogen }) => {
    const rows: Array<EpidemicOutbreak | null> = history.map((snapshot) =>
      snapshot.epidemics?.active.find((outbreak) => outbreak.region === region && outbreak.pathogen === pathogen) ?? null);
    const segments = buildSegments(turns, rows.map((row) => (row ? "active" : null))).map((segment) => {
      const covered = rows.slice(segment.from, segment.to + 1).filter((row): row is EpidemicOutbreak => row !== null);
      const peak = Math.max(...covered.map((row) => row.prevalence));
      const deaths = covered.reduce((sum, row) => sum + row.deaths, 0);
      const virgin = covered.some((row) => row.virgin);
      return {
        start: segment.start,
        end: segment.end,
        color: pathogenColor(pathogen),
        label: `${region}: ${pathogenLabel(pathogen)}, turns ${segment.start}-${segment.end - 1}`
          + ` · peak prevalence ${formatShare(peak)} · ${deaths} death${deaths === 1 ? "" : "s"}${virgin ? " · virgin soil" : ""}`,
      };
    });
    return { id: `${region}|${pathogen}`, label: `${region} · ${pathogenLabel(pathogen)}`, swatch: pathogenColor(pathogen), segments };
  });
}

/** Pathogens recorded anywhere in the history, in registry order. */
export function recordedPathogens(history: TurnSnapshot[]): string[] {
  const names = new Set<string>();
  for (const snapshot of history) {
    for (const outbreak of snapshot.epidemics?.active ?? []) {
      names.add(outbreak.pathogen);
    }
    for (const name of Object.keys(snapshot.epidemics?.deaths_by_pathogen ?? {})) {
      names.add(name);
    }
  }
  return [...names].sort((left, right) => pathogenRank(left) - pathogenRank(right) || left.localeCompare(right));
}

export function regionOutbreaks(snapshot: TurnSnapshot | null, region: string): EpidemicOutbreak[] {
  return (snapshot?.epidemics?.active ?? [])
    .filter((outbreak) => outbreak.region === region)
    .sort((left, right) => pathogenRank(left.pathogen) - pathogenRank(right.pathogen));
}

// --- Civilization series (finance, techniques) ---

/** Civilization names in world index order, then any other name a snapshot carries. */
export function orderedCivNames(worldCivs: string[], names: Iterable<string>): string[] {
  const wanted = new Set(names);
  const ordered = worldCivs.filter((name) => wanted.has(name));
  const extra = [...wanted].filter((name) => !worldCivs.includes(name)).sort();
  return [...ordered, ...extra];
}

export type SeriesRow = { turn: number } & Record<string, number | null>;

/**
 * One chart row per snapshot with a value per civilization; a civ without a
 * value in that snapshot is null (a gap), never zero.
 */
export function civSeries(
  history: TurnSnapshot[],
  civs: string[],
  value: (snapshot: TurnSnapshot, civ: string) => number | null | undefined,
): SeriesRow[] {
  return history.map((snapshot) => {
    const row: SeriesRow = { turn: snapshot.turn };
    for (const civ of civs) {
      const raw = value(snapshot, civ);
      row[civ] = raw == null || Number.isNaN(raw) ? null : raw;
    }
    return row;
  });
}

/** Debt in turns of smoothed revenue (the finance analytics' debt-to-revenue measure). */
export function debtToRevenue(debt: number, revenueEma: number): number {
  return Math.round((debt / Math.max(revenueEma, 1)) * 100) / 100;
}

// --- Techniques and eras ---

/** Ordinal ramp, earliest era darkest (dark surface); segments also carry the era's name. */
export const ERA_COLORS: Record<TechEra, string> = {
  tribal: "#184f95",
  bronze: "#256abf",
  iron: "#3987e5",
  classical: "#6da7ec",
  medieval: "#86b6ef",
  renaissance: "#9ec5f4",
  industrial: "#b7d3f6",
  information: "#cde2fb",
};

const LIGHT_INK = "#f0efec";
const DARK_INK = "#0b0b0b";
const LIGHT_FILLS = new Set(["#6da7ec", "#86b6ef", "#9ec5f4", "#b7d3f6", "#cde2fb"]);

/** Short label for a civilization: initials of its capitalised words. */
export function civInitials(name: string): string {
  const letters = name.split(/\s+/).filter((word) => /^[A-Z]/.test(word)).map((word) => word[0]).join("");
  return letters.slice(0, 3) || name.slice(0, 3);
}

/** Text ink for a label drawn on a ramp fill. */
export function inkOn(fill: string): string {
  return LIGHT_FILLS.has(fill) ? DARK_INK : LIGHT_INK;
}

export function eraLabel(era: string): string {
  return ERA_LABELS[era as TechEra] ?? era;
}

/** One row per civilization: its recorded era over time. */
export function eraRows(history: TurnSnapshot[], civs: string[], color: (civ: string) => string): StripRow[] {
  const turns = history.map((snapshot) => snapshot.turn);
  return civs.map((civ) => {
    const eras = history.map((snapshot) => {
      const stats = snapshot.civ_stats[civ];
      return stats && stats.alive !== false ? stats.tech_era : null;
    });
    const segments = buildSegments(turns, eras).map((segment) => {
      const color = ERA_COLORS[segment.key as TechEra] ?? OTHER_COLOR;
      return {
        start: segment.start,
        end: segment.end,
        color,
        label: `${civ}: ${eraLabel(segment.key)}, turns ${segment.start}-${segment.end - 1}`,
        text: eraLabel(segment.key),
        textColor: inkOn(color),
      };
    });
    return { id: civ, label: civ, swatch: color(civ), segments };
  });
}

/** Eras that appear in the rows, in era order. */
export function erasInRows(history: TurnSnapshot[], civs: string[]): TechEra[] {
  const seen = new Set<string>();
  for (const snapshot of history) {
    for (const civ of civs) {
      const era = snapshot.civ_stats[civ]?.tech_era;
      if (era) {
        seen.add(era);
      }
    }
  }
  return ERA_ORDER.filter((era) => seen.has(era));
}

export function techniqueLabel(key: string): string {
  const text = key.replace(/_/g, " ");
  return text.charAt(0).toUpperCase() + text.slice(1);
}

/** Practice share that counts toward an era (`techniques.PRACTISED`). */
export const PRACTISED_SHARE = 0.25;

/**
 * Per technique at the snapshot: regions practising it at `PRACTISED_SHARE`
 * or more, regions with any exported practice, and where it is strongest.
 * Null when the bundle does not export regional practice.
 */
export function practiceSummary(snapshot: TurnSnapshot | null): Array<{
  key: string;
  practised: number;
  present: number;
  best: { region: string; level: number };
}> | null {
  const regions = snapshot?.techniques?.regions;
  if (!regions) {
    return null;
  }
  const byKey = new Map<string, { key: string; practised: number; present: number; best: { region: string; level: number } }>();
  for (const [region, practice] of Object.entries(regions)) {
    for (const [key, level] of Object.entries(practice)) {
      const entry = byKey.get(key) ?? { key, practised: 0, present: 0, best: { region, level } };
      entry.present += 1;
      if (level >= PRACTISED_SHARE) {
        entry.practised += 1;
      }
      if (level > entry.best.level) {
        entry.best = { region, level };
      }
      byKey.set(key, entry);
    }
  }
  return [...byKey.values()].sort((left, right) =>
    right.practised - left.practised || right.present - left.present || left.key.localeCompare(right.key));
}

/** Practice in one region at the snapshot, highest first; null when the bundle does not export it. */
export function regionPractice(snapshot: TurnSnapshot | null, region: string): Array<[string, number]> | null {
  const regions = snapshot?.techniques?.regions;
  if (!regions) {
    return null;
  }
  return Object.entries(regions[region] ?? {}).sort((left, right) => right[1] - left[1] || left[0].localeCompare(right[0]));
}

// --- Diplomacy ---

/** Polity ladder stages in order (annexation ends the relation). */
export const LADDER_STAGES = ["client", "vassal", "union"] as const;

export const LADDER_COLORS: Record<string, string> = {
  client: "#184f95",
  vassal: "#2a78d6",
  union: "#6da7ec",
};

/** One row per overlord-subject pair over time, coloured by ladder stage. */
export function ladderRows(history: TurnSnapshot[]): StripRow[] {
  const turns = history.map((snapshot) => snapshot.turn);
  const pairs: string[] = [];
  for (const snapshot of history) {
    for (const subject of snapshot.diplomacy?.subjects ?? []) {
      const id = `${subject.overlord} → ${subject.vassal}`;
      if (!pairs.includes(id)) {
        pairs.push(id);
      }
    }
  }
  return pairs.map((id) => {
    const stages = history.map((snapshot) => {
      const subject = snapshot.diplomacy?.subjects.find((entry) => `${entry.overlord} → ${entry.vassal}` === id);
      return subject ? (subject.stage ?? "vassal") : null;
    });
    const segments = buildSegments(turns, stages).map((segment) => {
      const color = LADDER_COLORS[segment.key] ?? OTHER_COLOR;
      return {
        start: segment.start,
        end: segment.end,
        color,
        label: `${id}: ${segment.key}, turns ${segment.start}-${segment.end - 1}`,
        text: segment.key,
        textColor: inkOn(color),
      };
    });
    return { id, label: id, segments };
  });
}

export interface PairCell {
  trust: number;
  grievance: number;
}

/**
 * Directed pair memory at the snapshot: holder -> target -> cell. Uses the
 * full pair matrix when the bundle exports it; otherwise only the top
 * grievances (marked `complete: false`).
 */
export function pairMatrix(snapshot: TurnSnapshot | null): {
  cells: Map<string, Map<string, PairCell>>;
  civs: string[];
  complete: boolean;
} {
  const cells = new Map<string, Map<string, PairCell>>();
  const civs = new Set<string>();
  const diplomacy = snapshot?.diplomacy;
  const put = (holder: string, target: string, cell: PairCell) => {
    civs.add(holder);
    civs.add(target);
    if (!cells.has(holder)) {
      cells.set(holder, new Map());
    }
    cells.get(holder)?.set(target, cell);
  };
  if (diplomacy?.pairs) {
    for (const [holder, row] of Object.entries(diplomacy.pairs)) {
      for (const [target, [trust, grievance]] of Object.entries(row)) {
        put(holder, target, { trust, grievance });
      }
    }
    return { cells, civs: [...civs], complete: true };
  }
  for (const entry of diplomacy?.top_grievances ?? []) {
    put(entry.holder, entry.target, { trust: entry.trust, grievance: entry.grievance });
  }
  return { cells, civs: [...civs], complete: false };
}

/** Largest total grievance any exported pair reaches over the run (a stable colour scale). */
export function maxGrievance(history: TurnSnapshot[]): number {
  let max = 0;
  for (const snapshot of history) {
    const diplomacy = snapshot.diplomacy;
    if (!diplomacy) {
      continue;
    }
    if (diplomacy.pairs) {
      for (const row of Object.values(diplomacy.pairs)) {
        for (const [, grievance] of Object.values(row)) {
          max = Math.max(max, grievance);
        }
      }
    } else {
      for (const entry of diplomacy.top_grievances) {
        max = Math.max(max, entry.grievance);
      }
    }
  }
  return max;
}

const NEUTRAL: [number, number, number] = [0x38, 0x38, 0x35];
const TRUST_POSITIVE: [number, number, number] = [0x39, 0x87, 0xe5];
const TRUST_NEGATIVE: [number, number, number] = [0xe6, 0x67, 0x67];
const GRIEVANCE_HIGH: [number, number, number] = [0xd9, 0x59, 0x26];

function mix(from: [number, number, number], to: [number, number, number], t: number): string {
  const clamped = Math.max(0, Math.min(1, t));
  const channel = (index: number) => Math.round(from[index] + (to[index] - from[index]) * clamped);
  return `rgb(${channel(0)}, ${channel(1)}, ${channel(2)})`;
}

/** Trust colour domain: the scale saturates at this magnitude (trust runs -100..100). */
export const TRUST_SCALE = 50;

/** Diverging: distrust red, trust blue, neutral grey at zero. */
export function trustColor(trust: number): string {
  return trust >= 0 ? mix(NEUTRAL, TRUST_POSITIVE, trust / TRUST_SCALE) : mix(NEUTRAL, TRUST_NEGATIVE, -trust / TRUST_SCALE);
}

/** Sequential, one hue: no grievance grey, the run's largest grievance orange. */
export function grievanceColor(grievance: number, max: number): string {
  return mix(NEUTRAL, GRIEVANCE_HIGH, max > 0 ? grievance / max : 0);
}

// --- Maritime ---

export const CONTESTED_COLOR = "#6b7280";
export const BLOCKADE_COLOR = "#ef4444";

/** One row per sea zone: who held it over time, with blockade marks. */
export function zoneRows(history: TurnSnapshot[], color: (civ: string) => string): StripRow[] {
  const turns = history.map((snapshot) => snapshot.turn);
  const zones: string[] = [];
  for (const snapshot of history) {
    for (const zone of snapshot.maritime?.zones ?? []) {
      if (!zones.includes(zone.zone)) {
        zones.push(zone.zone);
      }
    }
  }
  return zones.map((name) => {
    const states = history.map((snapshot) => snapshot.maritime?.zones.find((zone) => zone.zone === name) ?? null);
    const keys = states.map((zone) => {
      if (!zone || zone.status === "uncontested") {
        return null;
      }
      return zone.status === "controlled" && zone.controller ? `controlled\u0000${zone.controller}` : "contested";
    });
    const segments = buildSegments(turns, keys).map((segment) => {
      const controller = segment.key.startsWith("controlled\u0000") ? segment.key.slice("controlled\u0000".length) : null;
      return {
        start: segment.start,
        end: segment.end,
        color: controller ? color(controller) : CONTESTED_COLOR,
        label: `${name}: ${controller ? `controlled by ${controller}` : "contested"}, turns ${segment.start}-${segment.end - 1}`,
        // Faction colours can collide, so the holder is also named in the bar.
        text: controller ? civInitials(controller) : "contested",
        textColor: controller ? DARK_INK : LIGHT_INK,
      };
    });
    const blockadeKeys = history.map((snapshot) => {
      const here = (snapshot.maritime?.blockades ?? []).filter((blockade) => blockade.zone === name);
      return here.length > 0
        ? here.map((blockade) => `${blockade.blockader ?? "?"} blockades ${blockade.target ?? "?"}`).sort().join("; ")
        : null;
    });
    const marks = buildSegments(turns, blockadeKeys).map((segment) => ({
      start: segment.start,
      end: segment.end,
      color: BLOCKADE_COLOR,
      label: `${name}: ${segment.key}, turns ${segment.start}-${segment.end - 1}`,
    }));
    return { id: name, label: name, segments, marks };
  });
}

/** Civilizations that controlled any zone, in first-control order. */
export function zoneControllers(history: TurnSnapshot[]): string[] {
  const names: string[] = [];
  for (const snapshot of history) {
    for (const zone of snapshot.maritime?.zones ?? []) {
      if (zone.status === "controlled" && zone.controller && !names.includes(zone.controller)) {
        names.push(zone.controller);
      }
    }
  }
  return names;
}

/** Port names of each zone from the final maritime state (zones and ports are fixed once built). */
export function zonePorts(
  zones: Array<{ name: string; ports?: number[] }> | undefined,
  regionNames: string[],
): Map<string, string[]> {
  const ports = new Map<string, string[]>();
  for (const zone of zones ?? []) {
    ports.set(zone.name, (zone.ports ?? []).map((index) => regionNames[index]).filter((name): name is string => !!name));
  }
  return ports;
}

export function humanize(text: string): string {
  return text.replace(/_/g, " ");
}
