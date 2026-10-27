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
import { faithLabel, faithTable, resolveFaith } from "./faiths";
import { buildSegments, type StripRow } from "./systems";

const LIGHT_INK = "#f0efec";
const DARK_INK = "#0b0b0b";

/** `agent_movements_state.CREED_NAMES`. */
export const CREED_LABELS = ["commons", "liberty", "sect", "guild"] as const;
/** `agent_movements_state.END_NAMES` (0 while living). */
export const END_LABELS = ["", "faded", "won", "seceded", "schism", "crushed", "dissolved"] as const;
/** `agent_movements_state.REFORM_NAMES`, as the record names them. */
export const REFORM_LABELS: Record<string, string> = {
  relief: "poor relief",
  home_rule: "home rule",
  toleration: "toleration",
  guild_charter: "guild charter",
};
const REFORM_KINDS = ["relief", "home_rule", "toleration", "guild_charter"] as const;
/** `agent_movements_state.REPEAL_NAMES` (0 in force). */
export const REPEAL_LABELS = ["", "neglect", "opposition", "ruler", "fiscal", "inquisition", "lapsed"] as const;
const INSTITUTION_LABELS: Record<string, string> = {
  commons_management: "Commons Management",
  written_law: "Written Law",
  merchant_courts: "Merchant Courts",
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

/**
 * A faith a record names, by permanent identity: "Faith of X (founded turn
 * 12)". `turn` is when the record was written (an older bundle names faiths
 * by slot, resolved as the slot stood then; null: the end of the run).
 */
export function faithName(bundle: Bundle, faith: number | undefined, turn: number | null = null): string | null {
  const table = faithTable(bundle);
  return faithLabel(table, resolveFaith(table, faith, turn));
}

/**
 * How the record names a reform (`agent_movements.reform_name`), a
 * toleration's faith by its permanent identity (name and founding turn).
 * `turn`: when the row was written (a snapshot of turn T: T - 1), which an
 * older bundle's slot needs.
 */
export function reformName(
  bundle: Bundle,
  reform: { kind: string; regions?: number[]; faith?: number; church?: boolean },
  turn: number | null = null,
): string {
  if (reform.kind === "home_rule") {
    const names = (reform.regions ?? []).map((index) => regionName(bundle, index)).filter((name) => name != null);
    return names.length ? `home rule of ${names.join(", ")}` : "home rule";
  }
  if (reform.kind === "toleration") {
    const faith = faithName(bundle, reform.faith, turn);
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

/**
 * Leader name -> turn of the first `movement_martyr` event naming them. A
 * movement keeps its dead leader's name in the snapshot; the martyrdom is the
 * record that they died.
 */
export function martyrdoms(events: Event[]): Map<string, number> {
  const out = new Map<string, number>();
  for (const event of events) {
    const leader = event.actors[1];
    if (event.event_type === "movement_martyr" && leader && !out.has(leader)) {
      out.set(leader, event.turn);
    }
  }
  return out;
}

/** The leader cell: the name, marked once the leader was martyred by `turn`. */
export function leaderLabel(leader: string | undefined, martyred: Map<string, number>, turn: number): string {
  if (!leader) {
    return "-";
  }
  const died = martyred.get(leader);
  return died != null && died <= turn ? `${leader} (martyred T${died})` : leader;
}

/** How a movement's end reads (`END_LABELS` order). */
const END_PHRASES: Record<string, string> = {
  faded: "faded away",
  won: "won its demand",
  seceded: "seceded",
  schism: "broke away in a schism",
  crushed: "was crushed",
  dissolved: "dissolved",
};

function count(n: number, noun: string): string {
  return `${n} ${noun}${n === 1 ? "" : "s"}`;
}

/** A movement's record as known at `upToTurn` (never a value the record dates later). */
export interface MovementRecordAt {
  record: MovementRecord;
  /** Civ index it opposed in its latest row by then (the record's otherwise). */
  target: number;
  /** Its leader in its latest row by then (the record's leader is the last one). */
  leader: string | null;
  /** Peak members over its rows by then; its demands and martyrs recorded by then. */
  peakMembers: number;
  demands: number;
  martyrs: number;
  /** Whether it had ended by `upToTurn`. */
  ended: boolean;
  /** A sect: its church by then, by permanent identity ("Faith of X (founded turn 0)"). */
  church: string | null;
  /** A sect that broke away by then: the church it became, by permanent identity. */
  becameChurch: string | null;
}

/**
 * The movement as known at `upToTurn`; null before its founding. The final
 * `world_state` record holds the whole run (peak, totals, end, last leader),
 * so the values come from its history rows and dated moments up to the turn.
 */
export function movementRecordAt(bundle: Bundle, id: number, upToTurn: number): MovementRecordAt | null {
  const record = movementRecord(bundle, id);
  if (!record || record.founded_turn > upToTurn) {
    return null;
  }
  let latest: MovementSnapshotRow | null = null;
  let peakMembers = 0;
  for (const snapshot of bundle.history) {
    if (snapshot.turn > upToTurn) {
      continue;
    }
    const row = movementRow(snapshot, id);
    if (row) {
      latest = row;
      peakMembers = Math.max(peakMembers, row.members);
    }
  }
  const dated = record.history.filter(([turn]) => turn <= upToTurn);
  // A sect's church: the one it broke from once it has a schism, else its
  // members' faith at its last record (permanent ids; slots in older bundles).
  let church: string | null = null;
  let becameChurch: string | null = null;
  if (CREED_LABELS[record.creed] === "sect") {
    const schism = record.schism_turn ?? null;
    church = schism != null
      ? faithName(bundle, record.schism_from, schism)
      : faithName(bundle, record.faith, record.ended_turn ?? null);
    if (schism != null && schism <= upToTurn) {
      becameChurch = faithName(bundle, record.schism_to, schism);
    }
  }
  return {
    record,
    target: latest?.target ?? record.target,
    leader: latest ? (latest.leader ?? null) : null,
    peakMembers,
    demands: dated.filter(([, kind]) => kind === "demand").length,
    martyrs: latest ? latest.martyrs : dated.filter(([, kind]) => kind === "martyr").length,
    ended: record.ended_turn != null && record.ended_turn <= upToTurn,
    church,
    becameChurch,
  };
}

/** One sentence for a movement as known at the turn (`movementRecordAt`). */
export function movementRecordNote(
  known: MovementRecordAt, target: string | null, home: string | null, currentTurn: number,
): string {
  const { record } = known;
  const creed = CREED_LABELS[record.creed] ?? "movement";
  const of = known.church ? ` of the ${known.church}` : "";
  let text = `A ${creed} movement${of} against ${target ?? "?"}, founded turn ${record.founded_turn} in ${home ?? "?"}`;
  if (known.leader) {
    text += `, led by ${known.leader}`;
  }
  text += `. By turn ${currentTurn}: peak ${count(known.peakMembers, "member")}, ${count(known.demands, "demand")}, `
    + `${count(known.martyrs, "martyr")}`;
  const end = END_LABELS[record.end] ?? "";
  if (known.ended && end && record.ended_turn != null) {
    text += `; ${END_PHRASES[end] ?? end} at turn ${record.ended_turn}`;
    if (end === "schism" && known.becameChurch) {
      text += `, becoming the church of the ${known.becameChurch}`;
    }
  }
  return `${text}.`;
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
  guild: "#5aa88f",
};
