/**
 * Read-only helpers for agent movements (`history[n].agent_movements`,
 * `world_state.agent_movements`; `--agent-movements`). A movement's identity
 * is its index in the world's movement list; a lasting reform's its index in
 * the reform list. Civs and regions are indices into `world_state`. Nothing
 * here infers a value the bundle does not record: a movement absent from a
 * snapshot is not living there.
 */
import type {
  AgentMovementsSnapshot, Bundle, Event, MovementRecord, MovementSnapshotRow, ReformRecord,
  ReformSnapshotRow, TurnSnapshot,
} from "../types";
import { buildSegments, type StripRow } from "./systems";

const LIGHT_INK = "#f0efec";
const DARK_INK = "#0b0b0b";

/** `agent_movements_state.CREED_NAMES`. */
export const CREED_LABELS = ["commons", "liberty", "sect"] as const;
/** `agent_movements_state.END_NAMES` (0 while living). */
export const END_LABELS = ["", "faded", "won", "seceded", "schism", "crushed", "dissolved"] as const;
/** `agent_movements_state.REFORM_NAMES`, as the record names them. */
export const REFORM_LABELS: Record<string, string> = {
  relief: "poor relief",
  home_rule: "home rule",
  toleration: "toleration",
};
const REFORM_KINDS = ["relief", "home_rule", "toleration"] as const;
/** `agent_movements_state.REPEAL_NAMES` (0 in force). */
export const REPEAL_LABELS = ["", "neglect", "opposition", "ruler", "fiscal", "inquisition", "lapsed"] as const;
const INSTITUTION_LABELS: Record<string, string> = {
  commons_management: "Commons Management",
  written_law: "Written Law",
};

/** By stage: gathering quiet, pressing and rising loud, suppressed dark, satisfied green. */
export const STAGE_COLORS: Record<string, string> = {
  gathering: "#7d8a96",
  pressing: "#c2924a",
  suppressed: "#6b4a5a",
  rising: "#d9644a",
  satisfied: "#6aa36f",
};
export const STAGE_ORDER = ["gathering", "pressing", "suppressed", "rising", "satisfied"] as const;

export { MOVEMENT_EVENT_TYPES } from "./movementEvents";

/** Running totals shown in the Movements tab (`agent_movements_state.COUNTER_KEYS`, a subset). */
export const MOVEMENT_COUNTERS: Array<[string, string]> = [
  ["founded", "Movements founded"],
  ["demands", "Demands"],
  ["reforms", "Demands granted"],
  ["refusals", "Refusals"],
  ["crackdowns", "Crackdowns"],
  ["martyrs", "Martyrs"],
  ["risings", "Risings"],
  ["secessions", "Secessions"],
  ["schisms", "Schisms"],
  ["enacted", "Lasting reforms enacted"],
  ["repealed", "Reforms repealed"],
  ["restored", "Reforms restored"],
  ["leaders", "Leaders raised"],
];

export function movementsOf(snapshot: TurnSnapshot | null | undefined): AgentMovementsSnapshot | null {
  return snapshot?.agent_movements ?? null;
}

export interface MovementKey {
  id: number;
  name: string;
  creed: string;
}

/** Every movement that was ever living in a snapshot, in order of first appearance. */
export function movementKeys(history: TurnSnapshot[]): MovementKey[] {
  const seen = new Map<number, MovementKey>();
  for (const snapshot of history) {
    for (const row of snapshot.agent_movements?.living ?? []) {
      if (!seen.has(row.id)) {
        seen.set(row.id, { id: row.id, name: row.name, creed: row.creed });
      }
    }
  }
  return [...seen.values()];
}

/** The movement's row in a snapshot, or null when it is not living there. */
export function movementRow(snapshot: TurnSnapshot | null | undefined, id: number): MovementSnapshotRow | null {
  return snapshot?.agent_movements?.living.find((row) => row.id === id) ?? null;
}

/** One strip row per movement: its stage over the snapshots it lived in. */
export function movementStageRows(history: TurnSnapshot[], keys: MovementKey[]): StripRow[] {
  const turns = history.map((snapshot) => snapshot.turn);
  return keys.map(({ id, name, creed }) => {
    const stages = history.map((snapshot) => movementRow(snapshot, id)?.stage ?? null);
    const segments = buildSegments(turns, stages).map((segment) => ({
      start: segment.start,
      end: segment.end,
      color: STAGE_COLORS[segment.key] ?? STAGE_COLORS.gathering,
      label: `${name} (${creed}): ${segment.key}, turns ${segment.start}-${segment.end - 1}`,
      text: segment.key,
      textColor: segment.key === "pressing" || segment.key === "satisfied" ? DARK_INK : LIGHT_INK,
    }));
    return { id: String(id), label: `${name} (${creed})`, segments };
  });
}

export type MovementSeriesRow = { turn: number } & Record<string, number | null>;

/** One chart row per snapshot with the movement's members; null where it is not living. */
export function memberSeries(history: TurnSnapshot[], id: number, key: string): MovementSeriesRow[] {
  return history.map((snapshot) => {
    const row = movementRow(snapshot, id);
    return { turn: snapshot.turn, [key]: row ? row.members : null } as MovementSeriesRow;
  });
}

/** Name of a civ index in the final world state. */
export function civName(bundle: Bundle, index: number): string | null {
  return bundle.world_state.civilizations[index]?.name ?? null;
}

/** Name of a region index in the final world state. */
export function regionName(bundle: Bundle, index: number | undefined): string | null {
  if (index == null || index < 0) {
    return null;
  }
  return bundle.world_state.regions[index]?.name ?? null;
}

function faithName(bundle: Bundle, faith: number | undefined): string | null {
  if (faith == null) {
    return null;
  }
  return bundle.world_state.belief_registry?.find((belief) => belief.faith_id === faith)?.name ?? null;
}

/** How the record names a reform (`agent_movements.reform_name`). */
export function reformName(
  bundle: Bundle,
  reform: { kind: string; regions?: number[]; faith?: number; church?: boolean },
): string {
  if (reform.kind === "home_rule") {
    const names = (reform.regions ?? []).map((index) => regionName(bundle, index)).filter((name) => name != null);
    return names.length ? `home rule of ${names.join(", ")}` : "home rule";
  }
  if (reform.kind === "toleration") {
    const faith = faithName(bundle, reform.faith);
    if (reform.church) {
      return faith ? `reform of the ${faith}` : "reform of the church";
    }
    return faith ? `toleration of the ${faith}` : "toleration";
  }
  return REFORM_LABELS[reform.kind] ?? reform.kind;
}

export function institutionLabel(institution: string | undefined): string | null {
  if (!institution) {
    return null;
  }
  return INSTITUTION_LABELS[institution] ?? institution.replace(/_/g, " ");
}

/** The lasting reforms in force at a snapshot (bundles from slice 2 on), or []. */
export function reformsInForce(snapshot: TurnSnapshot | null | undefined): ReformSnapshotRow[] {
  return snapshot?.agent_movements?.reforms ?? [];
}

/** The movement's final record in `world_state.agent_movements`, if the bundle carries it. */
export function movementRecord(bundle: Bundle, id: number): MovementRecord | null {
  return bundle.world_state.agent_movements?.movements?.[id] ?? null;
}

/** The reform's final record in `world_state.agent_movements`, if the bundle carries it. */
export function reformRecord(bundle: Bundle, id: number): ReformRecord | null {
  return bundle.world_state.agent_movements?.reforms?.[id] ?? null;
}

/** The reform's kind name from its record (`REFORM_NAMES` order). */
export function reformKind(record: ReformRecord): string {
  return REFORM_KINDS[record.kind] ?? `reform ${record.kind}`;
}

function eventIndex(bundle: Bundle): Map<string, Event> {
  const byId = new Map<string, Event>();
  for (const event of bundle.events_timeline) {
    if (event.event_id) {
      byId.set(event.event_id, event);
    }
  }
  return byId;
}

export interface MovementMoment {
  turn: number;
  kind: string;
  event: Event | null;
}

/**
 * The movement's recorded moments up to `upToTurn`, latest first, with the
 * event the simulation wrote; then its lasting reform's repeal, if any.
 */
export function movementHistory(bundle: Bundle, id: number, upToTurn: number): MovementMoment[] {
  const record = movementRecord(bundle, id);
  if (!record) {
    return [];
  }
  const byId = eventIndex(bundle);
  const moments: MovementMoment[] = record.history
    .filter(([turn]) => turn <= upToTurn)
    .map(([turn, kind, eventId]) => ({ turn, kind, event: byId.get(eventId) ?? null }));
  const reform = record.reform != null && record.reform >= 0 ? reformRecord(bundle, record.reform) : null;
  if (reform && reform.repeal && reform.repealed_turn != null && reform.repealed_turn <= upToTurn) {
    moments.push({
      turn: reform.repealed_turn,
      kind: REPEAL_LABELS[reform.repeal] === "lapsed" ? "reform lapsed" : "reform repealed",
      event: byId.get(reform.repeal_event_id) ?? null,
    });
  }
  return moments.sort((left, right) => left.turn - right.turn).reverse();
}

/** Living movements per creed in each snapshot (a chart row per snapshot). */
export function creedSeries(history: TurnSnapshot[]): MovementSeriesRow[] {
  return history.map((snapshot) => {
    const living = snapshot.agent_movements?.living;
    const row: MovementSeriesRow = { turn: snapshot.turn };
    for (const creed of CREED_LABELS) {
      row[creed] = living ? living.filter((entry) => entry.creed === creed).length : null;
    }
    return row;
  });
}

export const CREED_COLORS: Record<string, string> = {
  commons: "#e8b84a",
  liberty: "#5a8fd9",
  sect: "#b07ad9",
};
