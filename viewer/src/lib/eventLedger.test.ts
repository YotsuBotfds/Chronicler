import { describe, expect, it } from "vitest";
import type { Event } from "../types";
import { buildEventLedger } from "./eventLedger";

const event = (turn: number, actors: string[] = ["Alpha"], event_type = "migration"): Event =>
  ({ turn, actors, event_type, description: "Duplicate-looking migration", consequences: [], importance: 1 });

describe("eventLedger", () => {
  it("returns every matching original record exactly once across bounded pages, including identical-looking records", () => {
    const events = Array.from({ length: 73 }, (_, i) => event(1 + i % 6));
    events.splice(9, 0, event(3, ["Beta"]), event(99));
    const before = JSON.stringify(events);
    const query = { currentTurn: 6, civilization: "Alpha", pageSize: 24 };
    const first = buildEventLedger(events, query);
    expect(first.total).toBe(73);
    const entries = Array.from({ length: first.pageCount }, (_, i) => buildEventLedger(events, { ...query, page: i + 1 }))
      .flatMap(page => page.entries);
    expect(new Set(entries.map(entry => entry.sourceIndex)).size).toBe(73);
    expect(entries.map(entry => entry.sourceIndex).sort((a, b) => a - b))
      .toEqual(events.flatMap((e, i) => e.turn <= 6 && e.actors.includes("Alpha") ? [i] : []));
    entries.forEach(entry => expect(entry.event).toBe(events[entry.sourceIndex]));
    expect(JSON.stringify(events)).toBe(before);
    expect(first.entries).toHaveLength(24);
    expect(first.start).toBe(1);
    expect(buildEventLedger(events, { ...query, page: 4 }).end).toBe(73);
  });

  it("intersects exact actor, type and inclusive range with the mandatory current-turn cutoff", () => {
    const events = [event(0), event(2), event(3, ["Alpha", "Beta"], "war"), event(3, ["AlphaBeta"], "war"),
      event(3, [], "war"), event(4, ["Alpha"], "war"), event(5, ["Alpha"], "war")];
    expect(buildEventLedger(events, { currentTurn: 3, civilization: "Alpha", eventTypes: ["war"], fromTurn: 2, throughTurn: 5 })
      .entries.map(e => e.sourceIndex)).toEqual([2]);
    expect(buildEventLedger(events, { currentTurn: 3, eventTypes: ["migration", "war"], fromTurn: 2, throughTurn: 3 }).total).toBe(4);
    expect(buildEventLedger(events, { currentTurn: 0 }).entries[0].sourceIndex).toBe(0);
    expect(buildEventLedger(events, { currentTurn: 5, civilization: "Nobody" }).total).toBe(0);
  });

  it("groups by turn/type without inventing a merged event or losing duplicate or missing-actor records", () => {
    const missing = { ...event(2), actors: undefined } as unknown as Event;
    const events = [event(2), event(2), event(2, [], "war"), missing, event(1)];
    const page = buildEventLedger(events, { currentTurn: 2 });
    expect(page.groups.map(g => g.entries.map(e => e.sourceIndex))).toEqual([[0, 1, 3], [2], [4]]);
    expect(page.groups.flatMap(g => g.entries).map(e => e.sourceIndex).sort()).toEqual([0, 1, 2, 3, 4]);
    expect(buildEventLedger(events, { currentTurn: 2, civilization: "Alpha" }).entries.map(e => e.sourceIndex)).toEqual([0, 1, 4]);
    expect(page.entries.map(e => e.sourceIndex)).toEqual([0, 1, 2, 3, 4]);
    expect(buildEventLedger(events, { currentTurn: 2 })).toEqual(page);
  });

  it("splits a large same-turn burst only at record-page boundaries and clamps stale pages", () => {
    const events = Array.from({ length: 55 }, () => event(7));
    const pages = [1, 2, 3].map(page => buildEventLedger(events, { currentTurn: 7, page }));
    expect(pages.map(page => page.groups[0].entries.length)).toEqual([24, 24, 7]);
    expect(pages.flatMap(page => page.groups[0].entries).map(e => e.sourceIndex)).toEqual(events.map((_, i) => i));
    expect(buildEventLedger(events.slice(0, 2), { currentTurn: 7, page: 9 }).page).toBe(1);
  });

  it("handles empty and invalid queries safely and bounds rendering requests", () => {
    expect(buildEventLedger([], { currentTurn: 1, page: 5 })).toMatchObject({ total: 0, start: 0, end: 0, page: 1, pageCount: 1 });
    for (const range of [{ fromTurn: 3, throughTurn: 2 }, { fromTurn: -1 }, { throughTurn: NaN }, { currentTurn: Infinity }, { fromTurn: 1.5 }]) {
      expect(buildEventLedger([event(2)], { currentTurn: 2, ...range })).toMatchObject({ total: 0, validRange: false });
    }
    expect(buildEventLedger([event(2)], { currentTurn: 2, page: NaN, pageSize: 0 })).toMatchObject({ page: 1, pageSize: 24 });
    expect(buildEventLedger([event(2)], { currentTurn: 2, pageSize: 10000 }).pageSize).toBe(100);
  });
});
