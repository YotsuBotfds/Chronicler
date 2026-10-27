/**
 * Faiths by permanent identity (docs/integration/permanent-faiths.md).
 *
 * A faith's native id is a reusable slot: when the 16-faith registry is full
 * a sect takes the slot of a faith no one holds any more, so one slot can
 * name two unrelated churches over a run. Bundles from the permanent-faith
 * change on carry `world_state.faiths` (index = permanent id) and their
 * records name faiths by that id. Older bundles name faiths by slot: their
 * table is rebuilt here from the final registry and the `Schism` events (as
 * `chronicler.faiths.reconstruct` does), and a slot reference is resolved by
 * the turn it was written (`resolveFaith`). A faith whose slot's earlier
 * holders cannot be determined is marked unresolved.
 */
import type { Bundle, Event, FaithRecord } from "../types";

export const NO_FAITH = 255;

export interface FaithTable {
  faiths: FaithRecord[];
  /** The bundle predates permanent ids: its records name faiths by slot. */
  legacy: boolean;
}

const tables = new WeakMap<Bundle, FaithTable>();

/** The bundle's faith table (rebuilt once per bundle for an older one). */
export function faithTable(bundle: Bundle): FaithTable {
  const cached = tables.get(bundle);
  if (cached) {
    return cached;
  }
  const ws = bundle.world_state;
  const table: FaithTable = ws.faiths?.length
    ? { faiths: ws.faiths, legacy: false }
    : {
      faiths: reconstructFaiths(
        ws.belief_registry ?? [], bundle.events_timeline ?? [],
        ws.civilizations.map((civ) => civ.name), ws.regions.map((region) => region.name),
        (ws.agent_movements?.movements ?? []).map((movement) => movement.name),
      ),
      legacy: true,
    };
  tables.set(bundle, table);
  return table;
}

/** Permanent id of the faith holding `slot` at the end of `turn` (null: at the end of the run). */
export function faithAt(faiths: FaithRecord[], slot: number, turn: number | null): number | null {
  let found: number | null = null;
  faiths.forEach((rec, id) => {
    if (rec.slot !== slot) {
      return;
    }
    if (turn != null && rec.founded_turn != null && rec.founded_turn > turn) {
      return;
    }
    if (rec.released_turn != null && (turn == null || rec.released_turn <= turn)) {
      return;
    }
    found = id;
  });
  return found;
}

/**
 * The faith a record names: a permanent id, or in an older bundle the slot
 * as it stood at `turn` (the end of that turn; a history snapshot of turn T
 * holds the end of T - 1). Null for no faith or an unknown one.
 */
export function resolveFaith(table: FaithTable, ref: number | null | undefined, turn: number | null): number | null {
  if (ref == null || ref < 0 || ref === NO_FAITH) {
    return null;
  }
  if (!table.legacy) {
    return ref < table.faiths.length ? ref : null;
  }
  return faithAt(table.faiths, ref, turn) ?? faithAt(table.faiths, ref, null);
}

/** "Faith of X (founded turn 12)": a faith shown where two may share a name or a slot. */
export function faithLabel(table: FaithTable, id: number | null): string | null {
  const rec = id != null ? table.faiths[id] : undefined;
  if (!rec) {
    return null;
  }
  const founded = rec.founded_turn != null ? `founded turn ${rec.founded_turn}` : "founding not recorded";
  return `${rec.name} (${founded})`;
}

/** The faiths founded by `turn` (a faith of unknown founding counts from the start), by id. */
export function faithsKnownAt(table: FaithTable, turn: number): number[] {
  return table.faiths.flatMap((rec, id) => (
    rec.origin !== "reserved" && (rec.founded_turn == null || rec.founded_turn <= turn) ? [id] : []));
}

/** Whether the faith still held its slot at the end of `turn`. */
export function holdsSlotAt(rec: FaithRecord, turn: number): boolean {
  return rec.released_turn == null || rec.released_turn > turn;
}

/** The other faiths that held the faith's slot by `turn`, in founding order. */
export function slotSharers(table: FaithTable, id: number, turn: number): number[] {
  const rec = table.faiths[id];
  if (!rec || (rec.founded_turn != null && rec.founded_turn > turn)) {
    return [];
  }
  return faithsKnownAt(table, turn).filter((other) => other !== id && table.faiths[other].slot === rec.slot);
}

/** The faith that took the faith's slot when it vanished (by `turn`), if any. */
export function successorInSlot(table: FaithTable, id: number, turn: number): number | null {
  const rec = table.faiths[id];
  if (!rec || rec.released_turn == null || rec.released_turn > turn) {
    return null;
  }
  const next = table.faiths.findIndex((other) => other.slot === rec.slot && other.founded_turn === rec.released_turn
    && other !== rec);
  return next >= 0 ? next : null;
}

/** Whether a bundle's faiths are worth a tab: a recorded table, or an older bundle with a schism. */
export function hasFaithRecord(bundle: Bundle): boolean {
  const ws = bundle.world_state;
  if (ws.faiths?.length) {
    return true;
  }
  if (!ws.belief_registry?.length) {
    return false;
  }
  return faithTable(bundle).faiths.some((rec) => rec.origin !== "founding" || rec.released_turn != null);
}

const TEMPLE = /^Temple of faith (\d+) (destroyed|replaced) in (.+)$/;

/**
 * The recorded events about a faith up to `turn`: its founding schism, the
 * schism of a sect taking its place, reformations to it, and its temples
 * destroyed or replaced.
 */
export function faithEvents(bundle: Bundle, table: FaithTable, id: number, turn: number): Event[] {
  const rec = table.faiths[id];
  if (!rec) {
    return [];
  }
  const quoted = `'${rec.name}'`;
  const within = (event: Event) => (rec.founded_turn == null || event.turn >= rec.founded_turn)
    && (rec.released_turn == null || event.turn <= rec.released_turn);
  return bundle.events_timeline.filter((event) => {
    if (event.turn > turn) {
      return false;
    }
    if (event.event_type === "Schism" || event.event_type === "Reformation") {
      return event.description.includes(quoted) && within(event);
    }
    if (event.event_type === "temple_destroyed") {
      const match = TEMPLE.exec(event.description);
      return match != null && resolveFaith(table, Number(match[1]), event.turn) === id;
    }
    return false;
  });
}

/** A `Temple of faith <id> destroyed in <region>` record told by the faith's name. */
export function templeEventText(table: FaithTable, event: Event): string | null {
  const match = event.event_type === "temple_destroyed" ? TEMPLE.exec(event.description) : null;
  if (!match) {
    return null;
  }
  const label = faithLabel(table, resolveFaith(table, Number(match[1]), event.turn));
  return label ? `The temple of the ${label} is ${match[2]} in ${match[3]}` : null;
}

// --- Rebuilding an older bundle's table (chronicler.faiths.reconstruct) ---

const SECT_FOUNDED = "' is founded";
const SECT_IN_PLACE = "' is founded in place of the vanished '";
const SECT_BREAKS = " breaks away from the ";
const RELIGION_SPLITS = "' splits from the majority faith in ";
const RELIGION_FRACTURES = "A schism fractures ";

interface ParsedSchism {
  newName: string;
  parent: string | null;
  vanished: string | null;
  region: string | null;
  movement: string | null;
  kind: "schism" | "sect";
  civ: string | null;
}

/** The faiths a `Schism` event names (the religion's and the sect's wordings), or null. */
export function parseSchism(description: string): ParsedSchism | null {
  const desc = description ?? "";
  if (desc.startsWith(RELIGION_FRACTURES) && desc.includes(RELIGION_SPLITS) && desc.includes(": '")) {
    const civ = desc.slice(RELIGION_FRACTURES.length).split(": '")[0];
    const after = desc.slice(desc.indexOf(": '") + 3);
    const cut = after.indexOf(RELIGION_SPLITS);
    const rest = after.slice(cut + RELIGION_SPLITS.length);
    const ratio = rest.lastIndexOf(" (minority_ratio=");
    return {
      newName: after.slice(0, cut), parent: null, vanished: null,
      region: ratio >= 0 ? rest.slice(0, ratio) : rest, movement: null, kind: "schism", civ,
    };
  }
  if (!desc.includes(SECT_BREAKS) || !desc.includes(": '")) {
    return null;
  }
  let head: string;
  let vanished: string | null = null;
  if (desc.endsWith("'") && desc.includes(SECT_IN_PLACE)) {
    const at = desc.lastIndexOf(SECT_IN_PLACE);
    head = desc.slice(0, at);
    vanished = desc.slice(at + SECT_IN_PLACE.length, -1);
  } else if (desc.endsWith(SECT_FOUNDED)) {
    head = desc.slice(0, -SECT_FOUNDED.length);
  } else {
    return null;
  }
  const quote = head.lastIndexOf(": '");
  const pre = head.slice(0, quote);
  const breaks = pre.indexOf(SECT_BREAKS);
  const after = pre.slice(breaks + SECT_BREAKS.length);
  const inAt = after.lastIndexOf(" in ");
  return {
    newName: head.slice(quote + 3),
    parent: inAt >= 0 ? after.slice(0, inAt) : after,
    vanished,
    region: inAt >= 0 ? after.slice(inAt + 4) : null,
    movement: pre.slice(0, breaks) || null,
    kind: "sect",
    civ: null,
  };
}

function foundingName(name: string, slot: number, civNames: string[]): boolean {
  if (civNames.length) {
    return slot >= 0 && slot < civNames.length && name === `Faith of ${civNames[slot]}`;
  }
  return !name.includes(" (Reformed");
}

type Work = FaithRecord & { parentName?: string | null };

/**
 * An older run's faith table from its final registry and `Schism` events:
 * the live faiths first (permanent id == slot), then the faiths whose slot
 * was taken, in the order they gave it up.
 */
export function reconstructFaiths(
  registry: Array<{ faith_id: number; name: string; civ_origin?: number }>,
  events: Event[],
  civNames: string[] = [],
  regionNames: string[] = [],
  movementNames: string[] = [],
): FaithRecord[] {
  const live: Work[] = registry
    .map((belief) => ({
      name: belief.name, founded_turn: null, civ: belief.civ_origin ?? -1, origin: "founding",
      slot: belief.faith_id, legacy: "reconstructed",
    } as Work))
    .sort((a, b) => a.slot - b.slot);
  const holder = new Map<number, Work>(live.map((rec) => [rec.slot, rec]));
  if (holder.size !== live.length) {
    return live.map((rec) => ({ ...rec, legacy: "unresolved" }));
  }
  const pending = new Set<Work>(live);  // founding not yet found
  const released: Work[] = [];
  let unresolved = false;
  const schisms = events.filter((event) => event.event_type === "Schism");
  for (let k = schisms.length - 1; k >= 0; k -= 1) {
    const event = schisms[k];
    const parsed = parseSchism(event.description);
    if (!parsed) {
      unresolved = true;
      continue;
    }
    const slots = [...holder.entries()].filter(([, rec]) => rec.name === parsed.newName && pending.has(rec));
    if (slots.length !== 1) {
      unresolved = true;
      continue;
    }
    const [slot, rec] = slots[0];
    pending.delete(rec);
    rec.founded_turn = event.turn;
    rec.origin = parsed.kind;
    rec.parentName = parsed.parent;
    const region = parsed.region != null ? regionNames.indexOf(parsed.region) : -1;
    if (region >= 0) {
      rec.region = region;
    }
    if (parsed.kind === "schism" && parsed.civ != null && civNames.includes(parsed.civ)) {
      rec.civ = civNames.indexOf(parsed.civ);
    }
    if (parsed.movement != null && movementNames.filter((name) => name === parsed.movement).length === 1) {
      rec.movement = movementNames.indexOf(parsed.movement);
    }
    if (parsed.vanished != null) {
      const old: Work = {
        name: parsed.vanished, founded_turn: null, civ: -1, origin: "founding", slot,
        released_turn: event.turn, legacy: "reconstructed",
      };
      released.push(old);
      pending.add(old);
      holder.set(slot, old);
    } else {
      holder.delete(slot);
    }
  }
  for (const [slot, rec] of holder) {
    if (pending.has(rec)) {
      if (foundingName(rec.name, slot, civNames)) {
        rec.founded_turn = 0;
        if (rec.civ < 0) {
          rec.civ = slot;   // world generation: one founding faith per civ, in civ order
        }
      } else {
        rec.origin = "unrecorded";
        rec.legacy = "unresolved";
      }
    }
  }
  released.reverse();
  const out: Work[] = [...live, ...released];
  for (const rec of out) {
    let name = rec.parentName ?? null;
    delete rec.parentName;
    if (rec.origin === "schism" && name == null && rec.name.endsWith(")") && rec.name.includes(" (Reformed")) {
      name = rec.name.slice(0, rec.name.lastIndexOf(" (Reformed"));
    }
    if (name == null) {
      continue;
    }
    const t = rec.founded_turn;
    const candidates = out.flatMap((other, id) => (
      other !== rec && other.name === name
      && (other.founded_turn == null || t == null || other.founded_turn <= t)
      && (other.released_turn == null || t == null || other.released_turn > t) ? [id] : []));
    if (candidates.length === 1) {
      rec.parent = candidates[0];
    }
  }
  if (unresolved) {
    for (const rec of live) {
      if (rec.released_turn == null) {
        rec.legacy = "unresolved";
      }
    }
  }
  return out;
}
