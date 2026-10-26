/**
 * Thematic map layers for the atlas: one question per layer, drawn from the
 * bundle's own records at the scrubbed snapshot. A layer only recolours
 * region nodes and adds marks (flows, markers, sea-zone hubs); positions stay
 * the atlas layout's. Nothing here is inferred beyond what the bundle carries.
 */
import type { Bundle, TurnSnapshot } from "../types";
import { factionColor, UNCONTROLLED_COLOR } from "./colors";
import {
  AID_COLOR, crisesAtSnapshot, DEARTH_COLOR, FAMINE_COLOR, FED_COLOR, hasFamineRecord, hasFoodRecord, hasMigrationRecord,
  massMigrations, MIGRATION_COLOR, migrationDriverKind, migrationFlows, netMigration, SHORT_COLOR, SHORT_OF_FOOD,
  sufficiencyByRegion, type FamineSpan,
} from "./food";
import {
  BLOCKADE_COLOR, CONTESTED_COLOR, formatShare, pathogenColor, pathogenLabel, techniqueLabel,
} from "./systems";
import { hasCampaignRecord } from "./wars";

export type MapLayerKey = "control" | "food" | "epidemics" | "wars" | "migration" | "techniques" | "sea";

export const MAP_LAYER_LABELS: Record<MapLayerKey, string> = {
  control: "Control",
  food: "Food",
  epidemics: "Epidemics",
  wars: "Wars",
  migration: "Migration",
  techniques: "Techniques",
  sea: "Sea",
};

const LAYER_ORDER: MapLayerKey[] = ["control", "food", "epidemics", "wars", "migration", "techniques", "sea"];

/** Turns of agent migration summed on the migration layer. */
export const MIGRATION_WINDOW = 10;
/** Flows drawn on the migration layer (largest first). */
const MIGRATION_FLOW_LIMIT = 40;

/** Layers the bundle has data for, in chip order ("control" always). */
export function availableMapLayers(bundle: Bundle | null): MapLayerKey[] {
  if (!bundle) {
    return ["control"];
  }
  const history = bundle.history;
  const has: Record<MapLayerKey, boolean> = {
    control: true,
    food: hasFoodRecord(history) || hasFamineRecord(bundle.events_timeline),
    epidemics: history.some((snapshot) => snapshot.epidemics != null),
    wars: hasCampaignRecord(history),
    migration: hasMigrationRecord(history),
    techniques: history.some((snapshot) => snapshot.techniques?.regions != null),
    sea: history.some((snapshot) => (snapshot.maritime?.zones.length ?? 0) > 0),
  };
  return LAYER_ORDER.filter((key) => has[key]);
}

export interface LayerFlow {
  from: string;
  to: string;
  /** Drawn width in viewBox units. */
  width: number;
  color: string;
  title: string;
  dashed?: boolean;
}

export interface LayerMarker {
  region: string;
  color: string;
  /** Radius in viewBox units. */
  size: number;
  shape: "dot" | "burst";
  title: string;
}

export interface SeaHub {
  id: string;
  /** Map coordinates in the regions' pin space, or null to sit between the ports. */
  x: number | null;
  y: number | null;
  ports: string[];
  fill: string;
  ring: string | null;
  label: string;
  title: string;
}

export interface LegendItem {
  label: string;
  color: string;
  kind: "fill" | "line" | "dot" | "ring";
}

export interface MapLayerView {
  key: MapLayerKey;
  /** Region fill; regions without one are drawn dim (controller colour) or neutral. */
  fills: Map<string, string>;
  /** Fill opacity per region (default 1). */
  opacity: Map<string, number>;
  /** Draw regions without a layer fill in their controller's colour, dimmed. */
  dimControl: boolean;
  /** Outline colour per region (dashed ring). */
  outlines: Map<string, string>;
  /** Hover text per region. */
  titles: Map<string, string>;
  flows: LayerFlow[];
  markers: LayerMarker[];
  hubs: SeaHub[];
  legend: LegendItem[];
  /** One line on what the layer shows. */
  note: string;
}

export interface MapLayerInput {
  bundle: Bundle;
  snapshot: TurnSnapshot | null;
  /** Food-crisis spans of the run, both labels (`lib/food.foodCrisisSpans`). */
  famine: FamineSpan[];
  technique: string | null;
}

function emptyView(key: MapLayerKey, note: string): MapLayerView {
  return {
    key, fills: new Map(), opacity: new Map(), dimControl: false, outlines: new Map(), titles: new Map(),
    flows: [], markers: [], hubs: [], legend: [], note,
  };
}

/** Fill and opacity of a region the layer has nothing for (see AppShell's layer fill). */
export const NO_DATA_FILL = UNCONTROLLED_COLOR;
export const NO_DATA_OPACITY = 0.3;
/** How a no-data region looks on the dark map, for the legend swatch. */
const NO_DATA = "#2b3035";

function mixHex(from: string, to: string, t: number): string {
  const parse = (hex: string) => [1, 3, 5].map((index) => parseInt(hex.slice(index, index + 2), 16));
  const [a, b] = [parse(from), parse(to)];
  const clamped = Math.max(0, Math.min(1, t));
  return `rgb(${a.map((value, index) => Math.round(value + (b[index] - value) * clamped)).join(", ")})`;
}

function foodLayer({ bundle, snapshot, famine }: MapLayerInput): MapLayerView {
  const at = snapshot?.turn ?? 0;
  const names = bundle.world_state.regions.map((region) => region.name);
  const view = emptyView("food", snapshot?.food
    ? "Food on hand over need at this turn: amber where short (brighter is shorter), orange in famine; green arrows are relief convoys within a realm."
    : "Regions in famine (orange) and dearth (pale amber) at this turn (this bundle does not export regional food sufficiency).");
  const sufficiency = sufficiencyByRegion(snapshot, names);
  const crises = new Map(crisesAtSnapshot(famine, at).map((span) => [span.region, span]));
  for (const name of names) {
    const value = sufficiency.get(name);
    const span = crises.get(name);
    const parts: string[] = [name];
    if (value !== undefined) {
      parts.push(`food ${value.toFixed(2)} of need`);
      view.fills.set(name, value < SHORT_OF_FOOD ? mixHex("#6b5a2a", SHORT_COLOR, 1 - value) : FED_COLOR);
    }
    if (span) {
      parts.push(`${span.kind} since T${span.start}`);
      // A dearth keeps its food shading where the bundle has it; a famine is always orange.
      if (span.kind === "famine") {
        view.fills.set(name, FAMINE_COLOR);
      } else if (value === undefined) {
        view.fills.set(name, DEARTH_COLOR);
      }
    }
    if (value === undefined && !span && snapshot?.food) {
      parts.push("not observed (no owner or nobody living there)");
    }
    view.titles.set(name, parts.join(" · "));
  }
  for (const [donor, recipient, amount] of snapshot?.food?.aid ?? []) {
    const from = names[donor];
    const to = names[recipient];
    if (from && to) {
      view.flows.push({ from, to, width: 2 + Math.min(6, Math.sqrt(amount)), color: AID_COLOR,
        title: `Relief: ${amount.toFixed(1)} food from ${from} to ${to}` });
    }
  }
  view.legend = [
    { label: "famine", color: FAMINE_COLOR, kind: "fill" },
    ...(!snapshot?.food && famine.some((span) => span.kind === "dearth")
      ? [{ label: "dearth", color: DEARTH_COLOR, kind: "fill" as const }] : []),
    ...(snapshot?.food ? [
      { label: "short of food", color: SHORT_COLOR, kind: "fill" as const },
      { label: "fed", color: FED_COLOR, kind: "fill" as const },
      { label: "relief convoy", color: AID_COLOR, kind: "line" as const },
    ] : []),
    { label: "not observed", color: NO_DATA, kind: "fill" },
  ];
  return view;
}

/** Prevalence at which an outbreak's fill is fully opaque. */
const PREVALENCE_FULL = 0.05;

function epidemicsLayer({ bundle, snapshot }: MapLayerInput): MapLayerView {
  const view = emptyView("epidemics",
    "Each region's strongest outbreak at this turn, by pathogen; a stronger fill is a higher prevalence. Hover a region for its cases and quarantine.");
  const epidemics = snapshot?.epidemics;
  const seen = new Set<string>();
  const strongest = new Map<string, number>();
  for (const outbreak of epidemics?.active ?? []) {
    const current = view.titles.get(outbreak.region);
    const line = `${pathogenLabel(outbreak.pathogen)} ${formatShare(outbreak.prevalence, 2)}, ${outbreak.deaths} deaths`
      + (outbreak.virgin ? ", virgin soil" : "");
    view.titles.set(outbreak.region, current ? `${current} · ${line}` : `${outbreak.region} · ${line}`);
    if ((strongest.get(outbreak.region) ?? -1) < outbreak.prevalence) {
      strongest.set(outbreak.region, outbreak.prevalence);
      view.fills.set(outbreak.region, pathogenColor(outbreak.pathogen));
      view.opacity.set(outbreak.region, 0.35 + 0.65 * Math.min(1, outbreak.prevalence / PREVALENCE_FULL));
    }
    seen.add(outbreak.pathogen);
  }
  // Quarantine is named in the hover text, not drawn: most realms close their borders at once.
  const quarantined = new Set(epidemics?.quarantine ?? []);
  for (const region of bundle.world_state.regions) {
    const controller = snapshot?.region_control[region.name];
    const base = view.titles.get(region.name) ?? `${region.name} · no reportable outbreak`;
    view.titles.set(region.name, controller && quarantined.has(controller) ? `${base} · ${controller} in quarantine` : base);
  }
  view.legend = [
    ...[...seen].sort().map((name) => ({ label: pathogenLabel(name), color: pathogenColor(name), kind: "fill" as const })),
    { label: "no outbreak", color: NO_DATA, kind: "fill" },
  ];
  if (!epidemics) {
    view.note = "No epidemiology record at this turn.";
  }
  return view;
}

function warsLayer({ bundle, snapshot }: MapLayerInput): MapLayerView {
  const view = emptyView("wars",
    "Armies (dots, size by soldiers) and their march to the objective; battles of the last turn; dashed rings are occupied regions.");
  view.dimControl = true;
  const campaign = snapshot?.campaign;
  const at = snapshot?.turn ?? 0;
  for (const army of campaign?.armies ?? []) {
    view.markers.push({
      region: army.region,
      color: factionColor(army.civ),
      size: 4 + Math.min(10, Math.sqrt(army.soldiers) * 1.6),
      shape: "dot",
      title: `${army.name}: ${army.soldiers} soldiers, ${army.phase.replace(/_/g, " ")}${army.objective ? ` toward ${army.objective}` : ""}`,
    });
    if (army.objective && army.objective !== army.region) {
      view.flows.push({ from: army.region, to: army.objective, width: 2, color: factionColor(army.civ), dashed: true,
        title: `${army.name} marches on ${army.objective}` });
    }
  }
  for (const battle of campaign?.battles ?? []) {
    view.markers.push({
      region: battle.region,
      color: "#f2c14e",
      size: 9,
      shape: "burst",
      title: `${battle.name} (T${battle.turn}): ${battle.winner ?? "undecided"}; losses ${battle.attacker_losses} / ${battle.defender_losses}`,
    });
  }
  for (const occupation of campaign?.occupations ?? []) {
    view.outlines.set(occupation.region, factionColor(occupation.occupier));
    view.titles.set(occupation.region,
      `${occupation.region} · held by ${occupation.occupier} since T${occupation.since_turn} (owner ${occupation.owner})`);
  }
  for (const event of bundle.events_timeline) {
    if (event.event_type === "raid" && event.region && event.turn === at - 1) {
      view.markers.push({ region: event.region, color: "#e3b341", size: 6, shape: "burst", title: event.description });
    }
  }
  view.legend = [
    { label: "army (in its civ's colour)", color: "#d9d4c7", kind: "dot" },
    { label: "march to objective", color: "#d9d4c7", kind: "line" },
    { label: "battle or raid", color: "#f2c14e", kind: "dot" },
    { label: "occupied (occupier's colour)", color: "#d9d4c7", kind: "ring" },
  ];
  if (!campaign) {
    view.note = "No campaign record at this turn.";
  } else if (campaign.armies.length === 0 && campaign.occupations.length === 0 && campaign.battles.length === 0) {
    view.note = "No army in the field, battle or occupation at this turn.";
  }
  return view;
}

function migrationLayer({ bundle, snapshot }: MapLayerInput): MapLayerView {
  const at = snapshot?.turn ?? 0;
  const names = bundle.world_state.regions.map((region) => region.name);
  const flows = migrationFlows(bundle.history, at, MIGRATION_WINDOW, names);
  const view = emptyView("migration",
    `Agents who moved between regions in the last ${MIGRATION_WINDOW} recorded turns (arrow width by people).`);
  view.dimControl = true;
  const max = Math.max(1, ...flows.map((flow) => flow.amount));
  for (const flow of flows.slice(0, MIGRATION_FLOW_LIMIT)) {
    view.flows.push({ from: flow.from, to: flow.to, width: 1.5 + 7 * Math.sqrt(flow.amount / max), color: MIGRATION_COLOR,
      title: `${flow.amount} moved from ${flow.from} to ${flow.to}` });
  }
  const net = netMigration(flows);
  // Mass departures in the window, with what moved them when the bundle records it.
  const waves = new Map<string, string[]>();
  const kinds = new Map<string, number>();
  for (const event of massMigrations(bundle.events_timeline, at, MIGRATION_WINDOW)) {
    const kind = migrationDriverKind(event.driver);
    const region = event.region as string;
    waves.set(region, [...(waves.get(region) ?? []), `mass departure T${event.turn}${kind ? `: ${kind}` : ""}`]);
    if (kind) {
      kinds.set(kind, (kinds.get(kind) ?? 0) + 1);
    }
  }
  for (const name of names) {
    const value = net.get(name);
    const parts = [value === undefined ? `${name} · no recorded moves` : `${name} · net ${value > 0 ? "+" : ""}${value} people`,
      ...(waves.get(name) ?? [])];
    view.titles.set(name, parts.join(" · "));
  }
  if (flows.length === 0) {
    view.note = `No agent moved between regions in the ${MIGRATION_WINDOW} turns to ${at}.`;
  } else if (flows.length > MIGRATION_FLOW_LIMIT) {
    view.note += ` The ${MIGRATION_FLOW_LIMIT} largest of ${flows.length} are drawn.`;
  }
  if (kinds.size > 0) {
    view.note += ` Mass departures: ${[...kinds.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
      .map(([kind, count]) => `${count} ${kind}`).join(", ")}.`;
  }
  view.legend = [{ label: "people moving", color: MIGRATION_COLOR, kind: "line" }];
  return view;
}

const PRACTICE_LOW = "#1d4f8c";
const PRACTICE_HIGH = "#9ec5f4";

/** Techniques recorded in any snapshot's regional practice, by key. */
export function practisedTechniques(history: TurnSnapshot[]): string[] {
  const keys = new Set<string>();
  for (const snapshot of history) {
    for (const practice of Object.values(snapshot.techniques?.regions ?? {})) {
      for (const key of Object.keys(practice)) {
        keys.add(key);
      }
    }
  }
  return [...keys].sort((left, right) => techniqueLabel(left).localeCompare(techniqueLabel(right)));
}

/**
 * The technique to show first: the one spreading most at the snapshot
 * (regions with some but not full practice), then the most widely present.
 */
export function defaultTechnique(snapshot: TurnSnapshot | null, options: string[]): string | null {
  const regions = snapshot?.techniques?.regions;
  if (!regions) {
    return options[0] ?? null;
  }
  const spreading = new Map<string, number>();
  const present = new Map<string, number>();
  for (const practice of Object.values(regions)) {
    for (const [key, level] of Object.entries(practice)) {
      present.set(key, (present.get(key) ?? 0) + 1);
      if (level < 0.75) {
        spreading.set(key, (spreading.get(key) ?? 0) + 1);
      }
    }
  }
  const ranked = [...present.keys()].sort((left, right) => (spreading.get(right) ?? 0) - (spreading.get(left) ?? 0)
    || (present.get(right) ?? 0) - (present.get(left) ?? 0) || left.localeCompare(right));
  return ranked[0] ?? options[0] ?? null;
}

function techniquesLayer({ bundle, snapshot, technique }: MapLayerInput): MapLayerView {
  const label = technique ? techniqueLabel(technique) : "a technique";
  const view = emptyView("techniques", `How widely each region practises ${label} at this turn (share of its people).`);
  const regions = snapshot?.techniques?.regions;
  for (const region of bundle.world_state.regions) {
    const level = technique ? regions?.[region.name]?.[technique] : undefined;
    if (level !== undefined) {
      view.fills.set(region.name, mixHex(PRACTICE_LOW, PRACTICE_HIGH, level));
      view.titles.set(region.name, `${region.name} · ${label} ${formatShare(level, 0)}`);
    } else {
      view.titles.set(region.name, `${region.name} · ${label} not practised (below 3%)`);
    }
  }
  view.legend = [
    { label: "3%", color: mixHex(PRACTICE_LOW, PRACTICE_HIGH, 0.03), kind: "fill" },
    { label: "50%", color: mixHex(PRACTICE_LOW, PRACTICE_HIGH, 0.5), kind: "fill" },
    { label: "100%", color: PRACTICE_HIGH, kind: "fill" },
    { label: "not practised", color: NO_DATA, kind: "fill" },
  ];
  if (!regions) {
    view.note = "No regional practice record at this turn.";
  }
  return view;
}

function seaLayer({ bundle, snapshot }: MapLayerInput): MapLayerView {
  const view = emptyView("sea",
    "Sea zones (diamonds) linked to their ports: filled by the controlling civilization, grey when contested, red ring under blockade; the number is ships at sea.");
  view.dimControl = true;
  const names = bundle.world_state.regions.map((region) => region.name);
  const ports = new Map((bundle.world_state.maritime?.zones ?? []).map((zone) => [
    zone.name, (zone.ports ?? []).map((index) => names[index]).filter((name): name is string => !!name),
  ]));
  const positions = new Map((bundle.world_state.geography?.sea_zones ?? []).map((zone) => [zone.name, zone]));
  const maritime = snapshot?.maritime;
  const blockaded = new Set((maritime?.blockades ?? []).map((blockade) => blockade.zone));
  for (const zone of maritime?.zones ?? []) {
    const ships = Object.values(zone.ships).reduce((sum, count) => sum + count, 0);
    const place = positions.get(zone.zone);
    const holder = zone.status === "controlled" && zone.controller ? zone.controller : null;
    const fleets = Object.entries(zone.ships).map(([civ, count]) => `${civ} ${count}`).join(", ");
    view.hubs.push({
      id: zone.zone,
      x: typeof place?.x === "number" ? place.x : null,
      y: typeof place?.y === "number" ? place.y : null,
      ports: ports.get(zone.zone) ?? [],
      fill: holder ? factionColor(holder) : zone.status === "contested" ? CONTESTED_COLOR : "#1f2a33",
      ring: blockaded.has(zone.zone) ? BLOCKADE_COLOR : null,
      label: ships > 0 ? String(ships) : "",
      title: `${zone.zone}: ${holder ? `held by ${holder}` : zone.status}`
        + `${fleets ? ` · ships ${fleets}` : " · no ships"} · pirates ${formatShare(zone.pirates)}`
        + ` · sea trade ${zone.sea_trade.toFixed(2)}${blockaded.has(zone.zone) ? " · blockaded" : ""}`,
    });
  }
  view.legend = [
    { label: "held (in the holder's colour)", color: "#d9d4c7", kind: "fill" },
    { label: "contested", color: CONTESTED_COLOR, kind: "fill" },
    { label: "open sea", color: "#1f2a33", kind: "fill" },
    { label: "blockade", color: BLOCKADE_COLOR, kind: "ring" },
  ];
  if (!maritime) {
    view.note = "No maritime record at this turn.";
  }
  return view;
}

/** The layer's marks at the snapshot; null for the plain control map. */
export function buildMapLayer(key: MapLayerKey, input: MapLayerInput): MapLayerView | null {
  switch (key) {
    case "food": return foodLayer(input);
    case "epidemics": return epidemicsLayer(input);
    case "wars": return warsLayer(input);
    case "migration": return migrationLayer(input);
    case "techniques": return techniquesLayer(input);
    case "sea": return seaLayer(input);
    default: return null;
  }
}
