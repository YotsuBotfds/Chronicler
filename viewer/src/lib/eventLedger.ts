import type { Event } from "../types";

export interface EventLedgerQuery {
  currentTurn: number;
  /** OR within types; AND with civilization and the inclusive turn range. */
  eventTypes?: readonly string[];
  /** Exact exported actor name. Event has no general entity-ID field. */
  civilization?: string | null;
  fromTurn?: number;
  throughTurn?: number;
  page?: number;
  pageSize?: number;
}

export interface EventLedgerEntry {
  /** Position in the original input array, never a filtered-array position. */
  sourceIndex: number;
  /** The original object, without synthesis or cloning. */
  event: Event;
}

export interface EventLedgerGroup {
  key: string;
  turn: number;
  eventType: string;
  /** Records on this page only; a burst may continue on the next page. */
  entries: EventLedgerEntry[];
}

export interface EventLedgerPage {
  entries: EventLedgerEntry[];
  groups: EventLedgerGroup[];
  total: number;
  page: number;
  pageCount: number;
  pageSize: number;
  start: number;
  end: number;
  validRange: boolean;
}

export const EVENT_LEDGER_PAGE_SIZE = 24;
export const EVENT_LEDGER_MAX_PAGE_SIZE = 100;

/** Newest turn first, then original input order. No actor backfill or deduplication.
 * Source indices identify records within one immutable artifact array. Integrators
 * should remount the component when replacing that artifact, not mutate it in place.
 */
export function buildEventLedger(events: readonly Event[], query: EventLedgerQuery): EventLedgerPage {
  const { currentTurn, fromTurn, throughTurn } = query;
  const validRange = Number.isInteger(currentTurn) && currentTurn >= 0
    && (fromTurn === undefined || (Number.isInteger(fromTurn) && fromTurn >= 0))
    && (throughTurn === undefined || (Number.isInteger(throughTurn) && throughTurn >= 0))
    && (fromTurn === undefined || throughTurn === undefined || fromTurn <= throughTurn);
  const pageSize = Number.isInteger(query.pageSize) && query.pageSize! > 0
    ? Math.min(query.pageSize!, EVENT_LEDGER_MAX_PAGE_SIZE) : EVENT_LEDGER_PAGE_SIZE;
  const types = new Set(query.eventTypes);
  const matching = validRange ? events.map((event, sourceIndex) => ({ event, sourceIndex }))
    .filter(({ event }) => Number.isInteger(event.turn) && event.turn >= 0
      && event.turn <= currentTurn
      && (fromTurn === undefined || event.turn >= fromTurn)
      && (throughTurn === undefined || event.turn <= throughTurn)
      && (types.size === 0 || types.has(event.event_type))
      && (query.civilization == null || (event.actors ?? []).includes(query.civilization)))
    .sort((a, b) => b.event.turn - a.event.turn || a.sourceIndex - b.sourceIndex) : [];
  const total = matching.length;
  const pageCount = Math.max(1, Math.ceil(total / pageSize));
  const requestedPage = Number.isInteger(query.page) && query.page! > 0 ? query.page! : 1;
  const page = Math.min(requestedPage, pageCount);
  const offset = (page - 1) * pageSize;
  const entries = matching.slice(offset, offset + pageSize);
  const groups = new Map<string, EventLedgerGroup>();
  for (const entry of entries) {
    const { turn, event_type: eventType } = entry.event;
    const key = JSON.stringify([turn, eventType]);
    let group = groups.get(key);
    if (!group) {
      group = { key, turn, eventType, entries: [] };
      groups.set(key, group);
    }
    group.entries.push(entry);
  }
  return { entries, groups: [...groups.values()], total, page, pageCount, pageSize,
    start: total === 0 ? 0 : offset + 1, end: offset + entries.length, validRange };
}
