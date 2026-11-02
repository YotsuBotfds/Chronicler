/** Exact completed-turn ownership comparisons. Names are legacy keys, never aliases. */
import type { Bundle, TurnSnapshot } from "../types";
import { comparisonTurns, exactSnapshot } from "./historyComparison";

export type TerritoryStatus = "gained" | "lost" | "transferred" | "unchanged" | "outside" | "unknown";
export interface TerritoryController {
  known: boolean;
  /** Stable index in world.civilizations; null means explicitly uncontrolled. */
  civilizationId: number | null;
  label: string;
  reason?: string;
}
export interface TerritoryChange {
  /** Stable index in world.regions. */
  regionId: number;
  name: string;
  inspectable: boolean;
  before: TerritoryController;
  after: TerritoryController;
  status: TerritoryStatus;
}
export interface TerritoryComparison {
  fromTurn: number | null;
  toTurn: number;
  civilization: string | null;
  civilizationIndex: number | null;
  valid: boolean;
  status: string;
  rows: TerritoryChange[];
  counts: Record<TerritoryStatus, number>;
}
const unknown = (reason: string): TerritoryController => ({ known: false, civilizationId: null, label: "Unknown", reason });
const uniqueNameId = (rows: { name: string }[], name: string): number | null => {
  const ids = rows.flatMap((row, id) => row.name === name ? [id] : []);
  return ids.length === 1 ? ids[0] : null;
};

/** Only unique, earlier recorded turns. Never carry a record across the selected endpoint. */
export function territoryEarlierTurns(bundle: Bundle, currentTurn: number): number[] {
  return comparisonTurns(bundle, currentTurn).filter((turn) => turn < currentTurn);
}

function controller(bundle: Bundle, snapshot: TurnSnapshot | null, regionId: number): TerritoryController {
  if (!snapshot) return unknown("Exact endpoint not recorded or ambiguous");
  const name = bundle.world_state.regions[regionId].name;
  if (uniqueNameId(bundle.world_state.regions, name) !== regionId) return unknown("Region name is ambiguous");
  if (!Object.hasOwn(snapshot.region_control, name)) return unknown("Region name not recorded at this endpoint; no historical alias is inferred");
  const recorded = snapshot.region_control[name];
  if (recorded === null) return { known: true, civilizationId: null, label: "Uncontrolled" };
  if (typeof recorded !== "string") return unknown("Controller not recorded");
  const civilizationId = uniqueNameId(bundle.world_state.civilizations, recorded);
  if (civilizationId === null || !Object.hasOwn(snapshot.civ_stats, recorded)) {
    return unknown(`Controller ${recorded} has no unambiguous recorded civilization identity`);
  }
  return { known: true, civilizationId, label: recorded };
}

function classify(before: TerritoryController, after: TerritoryController, focus: number | null): TerritoryStatus {
  if (!before.known || !after.known) return "unknown";
  if (focus !== null) {
    if (before.civilizationId === focus && after.civilizationId === focus) return "unchanged";
    if (after.civilizationId === focus) return "gained";
    if (before.civilizationId === focus) return "lost";
    return "outside";
  }
  if (before.civilizationId === after.civilizationId) return "unchanged";
  if (before.civilizationId === null) return "gained";
  if (after.civilizationId === null) return "lost";
  return "transferred";
}

/** Explicit earlier choices must exist and precede the exact selected turn. */
export function compareTerritory(bundle: Bundle, currentTurn: number, fromTurn?: number | null, civilizationIndex: number | null = null): TerritoryComparison {
  const earlier = territoryEarlierTurns(bundle, currentTurn);
  const from = fromTurn === undefined ? earlier.at(-1) ?? null : fromTurn;
  const validFrom = from !== null && earlier.includes(from);
  const after = Number.isSafeInteger(currentTurn) && currentTurn >= 1 ? exactSnapshot(bundle, currentTurn) : null;
  const before = validFrom ? exactSnapshot(bundle, from) : null;
  const civilization = civilizationIndex === null ? null : bundle.world_state.civilizations[civilizationIndex]?.name ?? null;
  const focus = civilizationIndex;
  const validFocus = focus === null || (Number.isSafeInteger(focus) && focus >= 0 && civilization !== null
    && uniqueNameId(bundle.world_state.civilizations, civilization) === focus);
  const valid = before !== null && after !== null && validFocus;
  const counts: TerritoryComparison["counts"] = { gained: 0, lost: 0, transferred: 0, unchanged: 0, outside: 0, unknown: 0 };
  const rows = bundle.world_state.regions.map((region, regionId): TerritoryChange => {
    const first = controller(bundle, before, regionId), last = controller(bundle, after, regionId);
    const status = valid ? classify(first, last, focus) : "unknown";
    counts[status]++;
    return { regionId, name: region.name, inspectable: uniqueNameId(bundle.world_state.regions, region.name) === regionId,
      before: first, after: last, status };
  });
  return { fromTurn: from, toTurn: currentTurn, civilization, civilizationIndex, valid, rows, counts,
    status: !after ? "Selected snapshot not recorded or ambiguous"
      : !before ? "Choose an earlier recorded turn; no values fill missing endpoints"
      : !validFocus ? "Civilization identity is unknown or ambiguous"
      : `${counts.unknown} of ${rows.length} regions have unknown ownership at one or both endpoints` };
}

export const TERRITORY_COLORS: Record<TerritoryStatus, string> = {
  gained: "#4caf83", lost: "#df865b", transferred: "#c4a6ee", unchanged: "#637c8f", outside: "#3c4852", unknown: "#2b3035",
};
export const TERRITORY_LABELS: Record<TerritoryStatus, string> = {
  gained: "Gained", lost: "Lost", transferred: "Transferred", unchanged: "Unchanged", outside: "Outside focus", unknown: "Unknown",
};
