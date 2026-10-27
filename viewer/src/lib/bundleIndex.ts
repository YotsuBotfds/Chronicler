/**
 * Lookups over a loaded bundle, built once and reused while scrubbing.
 *
 * The shell and the systems panels read the event timeline and the history
 * at every scrubbed turn: the latest events up to the turn, the events of a
 * system's types, the event pinned in the inspector and its causes and
 * consequences, a region's terrain transitions, the raids of a turn, the
 * techniques practised by the turn. Each used to filter (and sort) the whole
 * timeline or history on every render; these indexes do that work once per
 * array and answer each turn with a binary search or a map lookup.
 *
 * Every index is keyed by the identity of the array it reads (a WeakMap,
 * like `civRows`): a new upload, a Batch Lab bundle and every live `turn`
 * message bring new `history` and `events_timeline` arrays (the live hook
 * replaces them, it never mutates them in place), so they get new indexes
 * and the old ones are collected with their arrays. An array whose length
 * changed since it was indexed (an in-place append) is indexed again.
 *
 * Every lookup returns what the filter it replaces returned, in the same
 * order (`__tests__/bundleIndex.test.ts` compares them turn by turn).
 */
import type { TurnSnapshot } from "../types";

/** The event fields the indexes read. */
export interface IndexedEvent {
  turn: number;
  event_type: string;
  event_id?: string;
  causes?: string[];
  actors?: string[];
}

/** Selection key for an event: its recorded id, else the legacy turn-type key. */
export function eventKey(event: { turn: number; event_type: string; event_id?: string }): string {
  return event.event_id || `${event.turn}-${event.event_type}`;
}

/** Timeline positions latest first (ties in timeline order) and their turns. */
interface LatestFirst {
  positions: number[];
  turns: number[];
}

interface EventIndex {
  length: number;
  latest: LatestFirst | null;
  byKey: Map<string, number> | null;
  byId: Map<string, number[]> | null;
  citedBy: Map<string, number[]> | null;
  byType: Map<string, number[]> | null;
  byActor: Map<string, LatestFirst> | null;
  byTypes: Map<string, LatestFirst>;
}

const eventIndexes = new WeakMap<readonly IndexedEvent[], EventIndex>();

function eventIndex(events: readonly IndexedEvent[]): EventIndex {
  const cached = eventIndexes.get(events);
  if (cached && cached.length === events.length) {
    return cached;
  }
  const index: EventIndex = {
    length: events.length, latest: null, byKey: null, byId: null, citedBy: null, byType: null, byActor: null,
    byTypes: new Map(),
  };
  eventIndexes.set(events, index);
  return index;
}

function withTurns(events: readonly IndexedEvent[], positions: number[]): LatestFirst {
  return { positions, turns: positions.map((position) => events[position].turn) };
}

function latest(events: readonly IndexedEvent[], index: EventIndex): LatestFirst {
  if (!index.latest) {
    const positions = events.map((_, position) => position)
      .sort((left, right) => events[right].turn - events[left].turn || left - right);
    index.latest = withTurns(events, positions);
  }
  return index.latest;
}

/** First position in a descending list of turns whose turn is at or before `turn` (the length if none). */
function firstAtOrBefore(turnsDescending: number[], turn: number): number {
  let low = 0;
  let high = turnsDescending.length;
  while (low < high) {
    const middle = (low + high) >> 1;
    if (turnsDescending[middle] <= turn) {
      high = middle;
    } else {
      low = middle + 1;
    }
  }
  return low;
}

function upTo<E>(events: readonly E[], list: LatestFirst, turn: number): E[] {
  const out: E[] = [];
  for (let at = firstAtOrBefore(list.turns, turn); at < list.positions.length; at += 1) {
    out.push(events[list.positions[at]]);
  }
  return out;
}

function pushTo<K>(map: Map<K, number[]>, key: K, position: number) {
  const list = map.get(key);
  if (list) {
    list.push(position);
  } else {
    map.set(key, [position]);
  }
}

/**
 * Events recorded by `turn`, latest first and in timeline order within a turn:
 * `events.filter((e) => e.turn <= turn)` stably sorted by turn, descending.
 */
export function eventsUpTo<E extends IndexedEvent>(events: readonly E[], turn: number): E[] {
  return upTo(events, latest(events, eventIndex(events)), turn);
}

/**
 * Events with `actor` among their actors recorded by `turn`, in the order of
 * `eventsUpTo` (`eventsUpTo(...).filter((e) => e.actors.includes(actor))`).
 */
export function actorEventsUpTo<E extends IndexedEvent>(events: readonly E[], actor: string, turn: number): E[] {
  const index = eventIndex(events);
  if (!index.byActor) {
    const positions = new Map<string, number[]>();
    for (const position of latest(events, index).positions) {
      for (const name of new Set(events[position].actors ?? [])) {
        pushTo(positions, name, position);
      }
    }
    index.byActor = new Map([...positions].map(([name, list]) => [name, withTurns(events, list)]));
  }
  const list = index.byActor.get(actor);
  return list ? upTo(events, list, turn) : [];
}

/**
 * Events of the given types recorded by `turn`, latest first and in timeline
 * order within a turn (`lib/systems.eventsOfTypes`).
 */
export function typedEventsUpTo<E extends IndexedEvent>(events: readonly E[], types: readonly string[], turn: number): E[] {
  const index = eventIndex(events);
  const key = types.join("\u0000");
  let list = index.byTypes.get(key);
  if (!list) {
    const wanted = new Set(types);
    list = withTurns(events, latest(events, index).positions.filter((position) => wanted.has(events[position].event_type)));
    index.byTypes.set(key, list);
  }
  return upTo(events, list, turn);
}

/** The first event whose `eventKey` is `key` (`events.find`), or null. */
export function eventByKey<E extends IndexedEvent>(events: readonly E[], key: string): E | null {
  const index = eventIndex(events);
  if (!index.byKey) {
    const byKey = new Map<string, number>();
    events.forEach((event, position) => {
      const value = eventKey(event);
      if (!byKey.has(value)) {
        byKey.set(value, position);
      }
    });
    index.byKey = byKey;
  }
  const position = index.byKey.get(key);
  return position === undefined ? null : events[position];
}

/** Events of one type, in timeline order (`events.filter((e) => e.event_type === type)`). */
export function eventsOfType<E extends IndexedEvent>(events: readonly E[], type: string): E[] {
  const index = eventIndex(events);
  if (!index.byType) {
    const byType = new Map<string, number[]>();
    events.forEach((event, position) => pushTo(byType, event.event_type, position));
    index.byType = byType;
  }
  return (index.byType.get(type) ?? []).map((position) => events[position]);
}

/**
 * Recorded provenance of one event: the events it cites as causes and the
 * events that cite it, each in timeline order; with `upToTurn`, only those
 * recorded by then.
 */
export function provenanceOf<E extends IndexedEvent>(
  events: readonly E[],
  selected: IndexedEvent,
  upToTurn?: number,
): { causes: E[]; effects: E[] } {
  const index = eventIndex(events);
  if (!index.byId || !index.citedBy) {
    const byId = new Map<string, number[]>();
    const citedBy = new Map<string, number[]>();
    events.forEach((event, position) => {
      if (event.event_id) {
        pushTo(byId, event.event_id, position);
      }
      for (const cause of new Set(event.causes ?? [])) {
        pushTo(citedBy, cause, position);
      }
    });
    index.byId = byId;
    index.citedBy = citedBy;
  }
  const recorded = (position: number) => upToTurn === undefined || events[position].turn <= upToTurn;
  const causes: number[] = [];
  for (const id of new Set(selected.causes ?? [])) {
    causes.push(...(index.byId.get(id) ?? []));
  }
  causes.sort((left, right) => left - right);
  return {
    causes: causes.filter(recorded).map((position) => events[position]),
    effects: (index.citedBy.get(selected.event_id ?? "") ?? []).filter(recorded).map((position) => events[position]),
  };
}

// --- History ---------------------------------------------------------------

interface HistoryIndex {
  length: number;
  techniques: Array<{ key: string; firstTurn: number }> | null;
}

const historyIndexes = new WeakMap<readonly TurnSnapshot[], HistoryIndex>();

function historyIndex(history: readonly TurnSnapshot[]): HistoryIndex {
  const cached = historyIndexes.get(history);
  if (cached && cached.length === history.length) {
    return cached;
  }
  const index: HistoryIndex = { length: history.length, techniques: null };
  historyIndexes.set(history, index);
  return index;
}

/**
 * The techniques of `practisedTechniques(history.filter((s) => s.turn <= turn))`:
 * those in some regional practice of a snapshot recorded by `turn`, ordered
 * by `compare` (ties in the order they first appear).
 */
export function techniquesPractisedBy(
  history: readonly TurnSnapshot[],
  turn: number,
  compare: (left: string, right: string) => number,
): string[] {
  const index = historyIndex(history);
  if (!index.techniques) {
    const firstTurn = new Map<string, number>();
    for (const snapshot of history) {
      for (const practice of Object.values(snapshot.techniques?.regions ?? {})) {
        for (const key of Object.keys(practice)) {
          const seen = firstTurn.get(key);
          if (seen === undefined || snapshot.turn < seen) {
            firstTurn.set(key, snapshot.turn);
          }
        }
      }
    }
    index.techniques = [...firstTurn.entries()]
      .map(([key, first]) => ({ key, firstTurn: first }))
      .sort((left, right) => compare(left.key, right.key));
  }
  return index.techniques.filter((entry) => entry.firstTurn <= turn).map((entry) => entry.key);
}
