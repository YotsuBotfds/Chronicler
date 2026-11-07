import type { TurnSnapshot } from "../types";

/**
 * Reader of the D2 attribution records (`snapshot.livelihoods.attribution_records`,
 * `--attribution-records`; Python reference `chronicler.attribution_records.record_status`).
 * Types live here, not in the pinned `types.ts`.
 *
 * Six readings stay distinct: `disabled` (no snapshot of the run carries the
 * record: the switch is off), `absent` (the run records it, this snapshot does
 * not: unknown, not zero), `malformed` (present and refused, with the reason),
 * `unobserved` (a valid record whose turn was not observed: `frame: null`,
 * unknown, not zero), `recorded_zero` (observed; nothing was attributed that
 * turn) and `recorded`. Inside a frame zeros are recorded zeros and nulls are
 * unknown (a granary `unattributed` of null: granaries inactive). Never reads
 * final-world state.
 */
export const CASUALTY_CAUSES = ["battle", "trapped", "revolt", "attrition", "natural"] as const;
export const CASUALTY_CLASSES = ["combat", "attrition", "natural"] as const;
export const NATURES = ["transfer", "minted", "destroyed", "restriction"] as const;
export const UNITS = ["treasury", "food", "goods", "grain", "milli_food", "routes"] as const;
export const IDENTITY_KINDS = ["restored", "revived", "name_reused", "renamed"] as const;

export type CasualtyCause = (typeof CASUALTY_CAUSES)[number];
export type CasualtyClass = (typeof CASUALTY_CLASSES)[number];
export type BurdenNature = (typeof NATURES)[number];
export type BurdenUnit = (typeof UNITS)[number];
export type IdentityKind = (typeof IDENTITY_KINDS)[number];
/** The class of each cause (``attribution_records_state.CASUALTY_CLASS``). */
export const CLASS_OF: Record<CasualtyCause, CasualtyClass> = {
  battle: "combat", trapped: "combat", revolt: "combat", attrition: "attrition", natural: "natural",
};

export interface CasualtyRow {
  war: string | null; war_start: number | null;
  victim: number | null; victim_name: string | null;
  /** The other side of the battle record (combat); null for attrition and natural deaths. */
  actor: number | null; actor_name: string | null;
  opponent: number | null; opponent_name: string | null;
  cause: CasualtyCause; class: CasualtyClass; kind: string | null; deaths: number;
}

export interface ArmyClosure {
  army: string; civ: number | null; civ_name: string | null; recorded: number;
  /** Null: no baseline (the army is new to the records, or gone). */
  counter_change: number | null; closes: boolean | null;
}

export interface GranarySeizure {
  region: number; flow: number; grain: number; cause: string; via: string | null;
  actor: number | null; actor_name: string | null; victim: number | null; victim_name: string | null;
  books_owner: number | null; books_owner_name: string | null; owner_stale: boolean;
}

export interface BurdenPair {
  kind: string; nature: BurdenNature; unit: BurdenUnit; authority: string;
  actor: number | null; actor_name: string | null; victim: number | null; victim_name: string | null;
  amount: number; unknown: number; events: number; internal: boolean;
}

export interface BurdenEntry {
  kind: string; nature: BurdenNature; unit: BurdenUnit;
  actor: number | null; actor_name: string | null; victim: number | null; victim_name: string | null;
  amount: number | null; region: number | null; city: number | null; cause: string | null;
  receipt?: Record<string, unknown>; detail?: Record<string, unknown>;
}

export interface IdentityEvent { turn: number; kind: IdentityKind; civ: number; name: string; detail: Record<string, unknown> }

export interface AttributionFrame {
  turn: number;
  casualties: {
    rows: CasualtyRow[]; by_class: Record<string, number>; by_cause: Record<string, number>;
    unresolved: number; armies: ArmyClosure[];
  };
  granary: { active: boolean; seizures: GranarySeizure[]; unattributed: number | null };
  burdens: { pairs: BurdenPair[]; entries: BurdenEntry[]; entries_dropped: number; retail_unattributed: number | null };
  identity: IdentityEvent[];
}

export interface AttributionRecord {
  schema_version: 1; stage: "D2"; source_turn: number;
  frame: AttributionFrame | null;
  lifetime: Record<string, number>; counters: Record<string, number>;
  identity_log: IdentityEvent[]; identity_dropped: number;
  log: { turn: number; kind: string; detail: Record<string, unknown> }[]; log_dropped: number;
  labels: Record<string, string>; parameters: Record<string, unknown>;
}

export type AttributionReading =
  | { state: "disabled" }
  | { state: "absent" }
  | { state: "malformed"; reason: string }
  | { state: "unobserved"; record: AttributionRecord }
  | { state: "recorded_zero"; record: AttributionRecord; frame: AttributionFrame }
  | { state: "recorded"; record: AttributionRecord; frame: AttributionFrame };

const object = (x: unknown): x is Record<string, unknown> => x !== null && typeof x === "object" && !Array.isArray(x);
const finite = (x: unknown): x is number => typeof x === "number" && Number.isFinite(x);
const count = (x: unknown): x is number => Number.isInteger(x) && (x as number) >= 0;
const text = (x: unknown): x is string => typeof x === "string";
const optionalText = (x: unknown) => x === null || text(x);
const index = (x: unknown, size: number) => x === null || (count(x) && x < size);
const one = <T extends string>(values: readonly T[], x: unknown): x is T => values.includes(x as T);

/** Whether a snapshot carries the record at all (a presence test; the reader parses). */
export function carriesAttribution(snapshot: TurnSnapshot | null | undefined): boolean {
  const livelihoods = (snapshot as unknown as Record<string, unknown> | null)?.livelihoods;
  return object(livelihoods) && livelihoods.attribution_records !== undefined && livelihoods.attribution_records !== null;
}

/** Whether any snapshot of the run carries the record (the switch was on). */
export function attributionOn(history: readonly TurnSnapshot[] | null | undefined): boolean {
  return Array.isArray(history) && history.some((s) => s !== null && typeof s === "object" && carriesAttribution(s));
}

function casualtyProblem(c: unknown, civs: number): string | null {
  if (!object(c) || !Array.isArray(c.rows) || !object(c.by_class) || !object(c.by_cause) || !count(c.unresolved)
    || !Array.isArray(c.armies)) return "malformed casualties";
  for (const r of c.rows) {
    if (!object(r) || !optionalText(r.war) || !(r.war_start === null || count(r.war_start)) || !index(r.victim, civs)
      || !index(r.actor, civs) || !index(r.opponent, civs) || !optionalText(r.victim_name) || !optionalText(r.actor_name)
      || !one(CASUALTY_CAUSES, r.cause) || !one(CASUALTY_CLASSES, r.class) || !optionalText(r.kind) || !count(r.deaths))
      return "malformed casualty row";
    if (CLASS_OF[r.cause as CasualtyCause] !== r.class) return "a casualty row in the wrong class";
    if (r.class !== "combat" && r.actor !== null) return "an actor on a non-combat death";
  }
  for (const a of c.armies) {
    if (!object(a) || !text(a.army) || !index(a.civ, civs) || !count(a.recorded)
      || !(a.counter_change === null || Number.isInteger(a.counter_change))
      || !(a.closes === null || typeof a.closes === "boolean")) return "malformed army closure";
  }
  return null;
}

function granaryProblem(g: unknown, civs: number, regions: number): string | null {
  if (!object(g) || typeof g.active !== "boolean" || !Array.isArray(g.seizures)
    || !(g.unattributed === null || count(g.unattributed))) return "malformed granary record";
  if (!g.active && (g.seizures.length || g.unattributed !== null)) return "inactive granaries with seizures";
  for (const s of g.seizures) {
    if (!object(s) || !count(s.region) || s.region >= regions || !count(s.flow) || !finite(s.grain) || s.grain < 0
      || !text(s.cause) || !index(s.actor, civs) || !index(s.victim, civs) || !index(s.books_owner, civs)
      || typeof s.owner_stale !== "boolean") return "malformed granary seizure";
  }
  return null;
}

function burdenProblem(b: unknown, civs: number): string | null {
  if (!object(b) || !Array.isArray(b.pairs) || !Array.isArray(b.entries) || !count(b.entries_dropped)
    || !(b.retail_unattributed === null || count(b.retail_unattributed))) return "malformed burdens";
  for (const p of b.pairs) {
    if (!object(p) || !text(p.kind) || !one(NATURES, p.nature) || !one(UNITS, p.unit) || !text(p.authority)
      || !index(p.actor, civs) || !index(p.victim, civs) || !finite(p.amount) || !count(p.unknown) || !count(p.events)
      || typeof p.internal !== "boolean") return "malformed burden pair";
  }
  for (const e of b.entries) {
    if (!object(e) || !text(e.kind) || !one(NATURES, e.nature) || !one(UNITS, e.unit) || !index(e.actor, civs)
      || !index(e.victim, civs) || !(e.amount === null || finite(e.amount))) return "malformed burden entry";
  }
  return null;
}

function identityProblem(events: unknown, civs: number): string | null {
  if (!Array.isArray(events)) return "malformed identity events";
  for (const e of events) {
    if (!object(e) || !count(e.turn) || !one(IDENTITY_KINDS, e.kind) || !count(e.civ) || e.civ >= civs || !text(e.name)
      || !object(e.detail)) return "malformed identity event";
  }
  return null;
}

/** One snapshot's record. ``on``: whether the run records it (``attributionOn``). */
export function readAttribution(snapshot: TurnSnapshot | null, on: boolean, regionCount: number,
  civCount: number): AttributionReading {
  if (!carriesAttribution(snapshot)) return on ? { state: "absent" } : { state: "disabled" };
  const livelihoods = (snapshot as unknown as Record<string, unknown>).livelihoods as Record<string, unknown>;
  const bad = (reason: string): AttributionReading => ({ state: "malformed", reason });
  if (livelihoods.schema_version !== 1) return bad("unknown livelihoods schema");
  const x = livelihoods.attribution_records;
  if (!object(x) || x.schema_version !== 1 || x.stage !== "D2") return bad("unknown attribution-records schema");
  if (!count(x.source_turn) || x.source_turn + 1 !== snapshot?.turn) return bad("misdated record");
  if (!object(x.lifetime) || !object(x.counters) || !Array.isArray(x.log) || !object(x.labels)
    || !count(x.identity_dropped) || !count(x.log_dropped)) return bad("malformed record");
  const logProblem = identityProblem(x.identity_log, civCount);
  if (logProblem) return bad(logProblem.replace("events", "log").replace("event", "log entry"));
  if (!("frame" in x)) return bad("the record has no frame");
  const record = x as unknown as AttributionRecord;
  if (x.frame === null) return { state: "unobserved", record };
  const f = x.frame;
  if (!object(f) || f.turn !== x.source_turn) return bad("misdated frame");
  const why = casualtyProblem(f.casualties, civCount) ?? granaryProblem(f.granary, civCount, regionCount)
    ?? burdenProblem(f.burdens, civCount) ?? identityProblem(f.identity, civCount);
  if (why) return bad(why);
  const frame = f as unknown as AttributionFrame;
  const empty = !frame.casualties.rows.length && !frame.burdens.pairs.length && !frame.identity.length
    && !frame.granary.seizures.length;
  return empty ? { state: "recorded_zero", record, frame } : { state: "recorded", record, frame };
}

/** Readable labels of the burden kinds the Python package declares. */
export const BURDEN_LABEL: Record<string, string> = {
  city_dues: "City dues to the lord", guild_levy: "Guild levy (raised dues)", city_sack: "City sack: plunder paid",
  city_sack_loss: "City sack: loot lost", occupation_plunder: "Occupation plunder",
  occupation_requisition: "Occupation requisition", occupation_tax_loss: "Owner's taxes lost to occupation",
  food_requisition: "Food requisitioned (commons)", conquest_stock_loss: "Stock destroyed in conquest",
  granary_seizure: "Granary grain seized", retail_war_loss: "Owned food lost to war",
  treaty_payment: "Treaty payment (reparations or tribute)", quarantine_closure: "Quarantine closure",
};
export const NATURE_LABEL: Record<BurdenNature, string> = {
  transfer: "transfer (paid by the victim to the actor)", minted: "minted (credited, taken from no one)",
  destroyed: "destroyed (received by no one)", restriction: "restriction (no amount moves)",
};
export const UNIT_LABEL: Record<BurdenUnit, string> = {
  treasury: "treasury", food: "food", goods: "goods", grain: "grain", milli_food: "milli-food", routes: "routes",
};
