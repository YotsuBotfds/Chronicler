/// <reference types="node" />
/**
 * The scrub indexes (lib/bundleIndex) return what the per-render filters
 * they replace returned, in the same order, at every turn. The reference
 * implementations below are those filters as they were on main 2f654a8.
 *
 * Set VIEWER_EQUIVALENCE_BUNDLES to a list of bundle files (path-separated)
 * to compare on generated bundles as well (docs/performance/viewer-2026-10.md).
 */
import { readFileSync } from "node:fs";
import { delimiter } from "node:path";
import { beforeAll, describe, expect, it } from "vitest";
import type { Bundle, Event, TurnSnapshot } from "../../types";
import { buildEventFeed, eventProvenance, terrainAt } from "../../components/phase75/appShellHelpers";
import {
  actorEventsUpTo, eventByKey, eventKey, eventsOfType, eventsUpTo, typedEventsUpTo,
} from "../bundleIndex";
import { decodeBundlePayload } from "../bundleCodec";
import { massMigrations } from "../food";
import { practisedTechniques, practisedTechniquesBy } from "../mapLayers";
import { eventsOfTypes, SYSTEM_EVENT_TYPES } from "../systems";
import systemsFixture from "../../__fixtures__/systems_bundle.json";
import transportFixture from "../../__fixtures__/transport_bundle.json";
import citiesFixture from "../../__fixtures__/cities_bundle.json";
import movementsFixture from "../../__fixtures__/movements_bundle.json";
import learningFixture from "../../__fixtures__/learning_bundle.json";
import sampleFixture from "../../__fixtures__/sample_bundle.json";

// --- The filters as they were (main 2f654a8) ---------------------------------

function referenceEventFeed(events: Event[], currentTurn: number, civ: string | null): Event[] {
  const visible = events
    .filter((event) => event.turn <= currentTurn)
    .sort((left, right) => right.turn - left.turn);
  if (civ === null) {
    return visible.slice(0, 24);
  }
  const focused = visible.filter((event) => event.actors.includes(civ));
  if (focused.length >= 8) {
    return focused.slice(0, 24);
  }
  const merged = [...focused];
  for (const event of visible) {
    if (merged.length >= 24) {
      break;
    }
    if (!merged.includes(event)) {
      merged.push(event);
    }
  }
  return merged;
}

function referenceEventsOfTypes(events: Event[], types: readonly string[], upToTurn: number): Event[] {
  const wanted = new Set(types);
  return events
    .map((event, index) => ({ event, index }))
    .filter(({ event }) => wanted.has(event.event_type) && event.turn <= upToTurn)
    .sort((left, right) => right.event.turn - left.event.turn || left.index - right.index)
    .map(({ event }) => event);
}

function referenceProvenance(events: Event[], selected: Event | null, upToTurn?: number) {
  if (!selected?.event_id) {
    return { causes: [], effects: [] };
  }
  const selectedId = selected.event_id;
  const wanted = new Set(selected.causes ?? []);
  const causes: Event[] = [];
  const effects: Event[] = [];
  for (const event of events) {
    if (upToTurn !== undefined && event.turn > upToTurn) {
      continue;
    }
    if (event.event_id && wanted.has(event.event_id)) {
      causes.push(event);
    }
    if (event.causes?.includes(selectedId)) {
      effects.push(event);
    }
  }
  return { causes, effects };
}

const TERRAIN_TRANSITION = /^(.*) transforms from (\S+) to (\S+)$/;

function referenceTerrainAt(events: Event[], region: string, finalTerrain: string, turn: number): string | null {
  let first: { turn: number; from: string | null } | null = null;
  for (const event of events) {
    if (event.event_type !== "terrain_transition" || event.turn <= turn) {
      continue;
    }
    const match = TERRAIN_TRANSITION.exec(event.description ?? "");
    if (match && match[1] !== region) {
      continue;
    }
    if (!match && !(event.description ?? "").startsWith(region)) {
      continue;
    }
    if (!first || event.turn < first.turn) {
      first = { turn: event.turn, from: match ? match[2] : null };
    }
  }
  return first ? first.from : finalTerrain;
}

function referenceMassMigrations(events: Event[], turn: number, window: number): Event[] {
  return events.filter((event) => event.event_type === "mass_migration" && !!event.region
    && event.turn <= turn && event.turn > turn - window);
}

// --- Inputs ------------------------------------------------------------------

function lcg(seed: number) {
  let state = seed >>> 0;
  return () => {
    state = (Math.imul(state, 1664525) + 1013904223) >>> 0;
    return state / 2 ** 32;
  };
}

const REGIONS = ["Ashfall", "Ash", "Brine Coast", "Cold Reach"];
const TYPES = ["war_declared", "famine", "raid", "terrain_transition", "mass_migration", "treaty_signed",
  "technique_invented", "city_founded", "embargo", "drought"];
const CIVS = ["Aria", "Bel", "Cor", "Dun", "Ess"];

/** A timeline with ties, out-of-order turns, repeated actors, missing and repeated ids, cycles of causes. */
function syntheticEvents(seed: number, count: number): Event[] {
  const next = lcg(seed);
  const pick = <T,>(list: readonly T[]) => list[Math.floor(next() * list.length)];
  const events: Event[] = [];
  for (let index = 0; index < count; index += 1) {
    // Mostly ascending turns with ties, a few out of order.
    const turn = next() < 0.1 ? 1 + Math.floor(next() * 40) : Math.min(40, 1 + Math.floor(index / 4));
    const type = pick(TYPES);
    const actors = Array.from({ length: Math.floor(next() * 4) }, () => pick(CIVS));
    const region = next() < 0.8 ? pick(REGIONS) : null;
    const id = next() < 0.85 ? `e${next() < 0.05 ? Math.floor(next() * index + 1) : index}` : undefined;
    const causes = next() < 0.6
      ? Array.from({ length: 1 + Math.floor(next() * 3) }, () => `e${Math.floor(next() * count)}`)
      : undefined;
    const description = type === "terrain_transition"
      ? (next() < 0.85 ? `${region ?? pick(REGIONS)} transforms from ${pick(["forest", "plains"])} to ${pick(["desert", "plains"])}`
        : `${pick(REGIONS)} changes oddly`)
      : `${type} ${index}`;
    events.push({
      turn, event_type: type, actors, description, consequences: [], importance: Math.floor(next() * 10),
      ...(id === undefined ? {} : { event_id: id }),
      ...(causes === undefined ? {} : { causes }),
      region,
    });
  }
  return events;
}

const fixtures: Array<[string, Bundle]> = [
  ["systems", systemsFixture as unknown as Bundle],
  ["transport", decodeBundlePayload(structuredClone(transportFixture) as Record<string, unknown>) as unknown as Bundle],
  ["cities", citiesFixture as unknown as Bundle],
  ["movements", movementsFixture as unknown as Bundle],
  ["learning", learningFixture as unknown as Bundle],
  ["sample", sampleFixture as unknown as Bundle],
];

const generated: Array<[string, Bundle]> = (process.env.VIEWER_EQUIVALENCE_BUNDLES ?? "")
  .split(delimiter)
  .filter(Boolean)
  .map((file) => [file, decodeBundlePayload(JSON.parse(readFileSync(file, "utf8"))) as unknown as Bundle]);

function turnsOf(events: Event[], history: TurnSnapshot[]): number[] {
  const last = Math.max(1, ...events.map((event) => event.turn), ...history.map((snapshot) => snapshot.turn));
  return Array.from({ length: last + 2 }, (_, index) => index);
}

/** Every index lookup against its reference at every turn. */
function timelineComparison(events: Event[], history: TurnSnapshot[], regions: string[], stride = 1) {
  const turns = turnsOf(events, history).filter((_, index) => index % stride === 0);
  const actors = [...new Set(events.flatMap((event) => event.actors ?? []))].slice(0, 12);
  const selectable = events.filter((_, index) => index % Math.max(1, Math.floor(events.length / 40)) === 0);
  return { events, regions, turns, actors, selectable };
}

type TimelineComparison = ReturnType<typeof timelineComparison>;

/** Same assertions and order, scheduled in bounded groups of turns for fixture histories. */
function compareTimelineTurns({ events, regions, actors, selectable }: TimelineComparison, turns: number[]) {
  for (const turn of turns) {
    expect(buildEventFeed(events, turn, null)).toEqual(referenceEventFeed(events, turn, null));
    for (const civ of [...actors, "Nobody"]) {
      const feed = buildEventFeed(events, turn, civ);
      const reference = referenceEventFeed(events, turn, civ);
      expect(feed).toHaveLength(reference.length);
      feed.forEach((event, index) => expect(event).toBe(reference[index]));
    }
    for (const types of Object.values(SYSTEM_EVENT_TYPES)) {
      const indexed = eventsOfTypes(events, types, turn);
      const reference = referenceEventsOfTypes(events, types, turn);
      expect(indexed).toHaveLength(reference.length);
      indexed.forEach((event, index) => expect(event).toBe(reference[index]));
    }
    for (const selected of selectable) {
      const indexed = eventProvenance(events, selected, turn);
      const reference = referenceProvenance(events, selected, turn);
      expect(indexed.causes).toEqual(reference.causes);
      expect(indexed.effects).toEqual(reference.effects);
    }
    for (const region of regions) {
      expect(terrainAt(events, region, "final", turn)).toBe(referenceTerrainAt(events, region, "final", turn));
    }
    expect(massMigrations(events, turn, 10)).toEqual(referenceMassMigrations(events, turn, 10));
    expect(eventsOfType(events, "raid").filter((event) => event.region && event.turn === turn - 1))
      .toEqual(events.filter((event) => event.event_type === "raid" && event.region && event.turn === turn - 1));
  }
}

/** Once-per-timeline lookups without a turn cutoff, kept outside the turn batches. */
function compareTimelineRemainder({ events, selectable }: TimelineComparison) {
  for (const selected of selectable) {
    const indexed = eventProvenance(events, selected);
    const reference = referenceProvenance(events, selected);
    expect(indexed).toEqual(reference);
    expect(eventByKey(events, eventKey(selected))).toBe(events.find((event) => eventKey(event) === eventKey(selected)));
  }
  expect(eventByKey(events, "no-such-event")).toBeNull();
}

function compareTimeline(events: Event[], history: TurnSnapshot[], regions: string[], stride = 1) {
  const comparison = timelineComparison(events, history, regions, stride);
  compareTimelineTurns(comparison, comparison.turns);
  compareTimelineRemainder(comparison);
}

function compareTechniques(history: TurnSnapshot[], turns: number[]) {
  for (const turn of turns) {
    expect(practisedTechniquesBy(history, turn))
      .toEqual(practisedTechniques(history.filter((snapshot) => snapshot.turn <= turn)));
  }
}

const TURNS_PER_TEST = 20;

/** Slice the original ordered domain: no skipped, duplicated or newly sampled turns. */
function turnRanges(turns: number[]): Array<[number, number, number[]]> {
  const ranges: Array<[number, number, number[]]> = [];
  for (let offset = 0; offset < turns.length; offset += TURNS_PER_TEST) {
    const chunk = turns.slice(offset, offset + TURNS_PER_TEST);
    ranges.push([chunk[0], chunk[chunk.length - 1], chunk]);
  }
  return ranges;
}

function compareBundleInRanges(bundle: Bundle, stride = 1) {
  // Decode and prepare each fixture once. All tests retain the same arrays,
  // so production WeakMap indexes are reused across adjacent turn ranges.
  const comparison = timelineComparison(bundle.events_timeline, bundle.history,
    bundle.world_state.regions.map((region) => region.name), stride);
  const timelineRanges = turnRanges(comparison.turns);
  const techniqueTurns = turnsOf([], bundle.history);
  const techniqueRanges = turnRanges(techniqueTurns);
  beforeAll(() => {
    // Build lazy production indexes once outside timed range bodies. Expected
    // results remain independent filters, including every first/cold return.
    const events = comparison.events;
    expect(eventsUpTo(events, 0)).toEqual(events.filter((event) => event.turn <= 0)
      .sort((left, right) => right.turn - left.turn));
    const actor = comparison.actors[0] ?? "Nobody";
    expect(actorEventsUpTo(events, actor, 0)).toEqual(events
      .filter((event) => event.turn <= 0 && event.actors.includes(actor))
      .sort((left, right) => right.turn - left.turn));
    for (const types of Object.values(SYSTEM_EVENT_TYPES)) {
      expect(typedEventsUpTo(events, types, 0)).toEqual(referenceEventsOfTypes(events, types, 0));
    }
    expect(eventsOfType(events, "terrain_transition"))
      .toEqual(events.filter((event) => event.event_type === "terrain_transition"));
    const firstKey = comparison.selectable[0];
    if (firstKey) {
      expect(eventByKey(events, eventKey(firstKey)))
        .toBe(events.find((event) => eventKey(event) === eventKey(firstKey)));
    }
    expect(eventByKey(events, "no-such-event")).toBeNull();
    const selected = comparison.selectable.find((event) => event.event_id);
    if (selected) expect(eventProvenance(events, selected, 0)).toEqual(referenceProvenance(events, selected, 0));
    expect(practisedTechniquesBy(bundle.history, 0))
      .toEqual(practisedTechniques(bundle.history.filter((snapshot) => snapshot.turn <= 0)));
  });
  it("schedules every original timeline and technique turn once in order", () => {
    expect(timelineRanges.flatMap(([, , turns]) => turns)).toEqual(comparison.turns);
    expect(techniqueRanges.flatMap(([, , turns]) => turns)).toEqual(techniqueTurns);
  });
  it.each(timelineRanges)("timeline turns %i through %i", (_first, _last, turns) => {
    compareTimelineTurns(comparison, turns);
  });
  it("provenance and event keys without a turn cutoff", () => {
    compareTimelineRemainder(comparison);
  });
  it.each(techniqueRanges)("technique turns %i through %i", (_first, _last, turns) => {
    compareTechniques(bundle.history, turns);
  });
}

describe("scrub indexes against the filters they replace", () => {
  it.each([1, 2, 3, 4, 5])("synthetic timeline %i (ties, unordered turns, repeated ids and actors)", (seed) => {
    const events = syntheticEvents(seed, 260);
    compareTimeline(events, [], REGIONS);
  });

  describe.each(fixtures)("%s fixture", (_name, bundle) => {
    compareBundleInRanges(bundle);
  });

  describe.each(generated)("generated bundle %s", (_name, bundle) => {
    compareBundleInRanges(bundle, 7);
  });
});

describe("index invalidation", () => {
  it("indexes each new timeline array (a live turn appends by replacing the array)", () => {
    const all = syntheticEvents(11, 120).sort((left, right) => left.turn - right.turn);
    let events: Event[] = [];
    for (let turn = 1; turn <= 40; turn += 1) {
      // Each live `turn` message: a new array with that turn's events appended.
      events = [...events, ...all.filter((event) => event.turn === turn)];
      expect(eventsUpTo(events, turn)).toEqual(events.filter((event) => event.turn <= turn)
        .sort((left, right) => right.turn - left.turn));
      expect(buildEventFeed(events, turn, "Aria")).toEqual(referenceEventFeed(events, turn, "Aria"));
      expect(typedEventsUpTo(events, ["raid", "famine"], turn)).toEqual(referenceEventsOfTypes(events, ["raid", "famine"], turn));
      expect(eventByKey(events, eventKey(events[events.length - 1] ?? all[0]))).toBe(
        events.length ? events.find((event) => eventKey(event) === eventKey(events[events.length - 1])) : null);
    }
  });

  it("indexes an array again when its length changed in place", () => {
    const events = syntheticEvents(12, 60);
    expect(actorEventsUpTo(events, "Aria", 100)).toEqual(events.filter((event) => event.turn <= 100)
      .sort((left, right) => right.turn - left.turn).filter((event) => event.actors.includes("Aria")));
    const late: Event = { turn: 99, event_type: "raid", actors: ["Aria"], description: "late raid", consequences: [],
      importance: 1, event_id: "late", causes: [events[0].event_id ?? "e0"], region: "Ash" };
    events.push(late);
    expect(actorEventsUpTo(events, "Aria", 100)[0]).toBe(late);
    expect(eventsOfType(events, "raid")).toContain(late);
    expect(eventByKey(events, "late")).toBe(late);
    expect(eventProvenance(events, events[0]).effects).toContain(late);
  });

  it("indexes each new history array (techniques practised by the turn)", () => {
    const base = systemsFixture as unknown as Bundle;
    let history: TurnSnapshot[] = [];
    for (const snapshot of base.history) {
      history = [...history, snapshot];
      expect(practisedTechniquesBy(history, snapshot.turn)).toEqual(practisedTechniques(history));
    }
  });
});
