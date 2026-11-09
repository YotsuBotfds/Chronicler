import { describe, expect, it } from "vitest";
import type { BatchRunSummary, Bundle, TurnSnapshot } from "../../types";
import sample from "../../__fixtures__/sample_bundle.json";
import {
  buildChronicleFeed, buildEraBands, buildNarratedSpans, findCurrentSnapshot, selectionDescription, totalTurnsFor,
} from "../shellFeed";

const sampleBundle = () => structuredClone(sample) as unknown as Bundle;

function eraSnapshot(turn: number, eras: Record<string, string>): TurnSnapshot {
  return {
    turn,
    civ_stats: Object.fromEntries(Object.entries(eras).map(([name, era]) => [name, { tech_era: era }])),
    region_control: {},
    relationships: {},
  } as unknown as TurnSnapshot;
}

describe("shell feed helpers", () => {
  it("shows the latest snapshot at or before the turn, and none before the first", () => {
    const bundle = sampleBundle();
    bundle.history = bundle.history.filter((row) => row.turn >= 3 && row.turn !== 5);
    expect(findCurrentSnapshot(null, 4)).toBeNull();
    expect(findCurrentSnapshot(bundle, 2)).toBeNull();
    expect(findCurrentSnapshot(bundle, 3)?.turn).toBe(3);
    expect(findCurrentSnapshot(bundle, 5)?.turn).toBe(4);
    expect(findCurrentSnapshot(bundle, 99)?.turn).toBe(10);
  });

  it("takes the run's length from its metadata, then its history", () => {
    const bundle = sampleBundle();
    expect(totalTurnsFor(null)).toBe(1);
    expect(totalTurnsFor(bundle)).toBe(10);
    const unrecorded = { ...bundle, metadata: { ...bundle.metadata, total_turns: undefined } } as unknown as Bundle;
    expect(totalTurnsFor(unrecorded)).toBe(bundle.history.length);
  });

  it("splits a run without history into five fallback eras", () => {
    expect(buildEraBands([], 10)).toEqual([
      { label: "Founding", start: 1, end: 2 },
      { label: "Expansion", start: 3, end: 4 },
      { label: "Maturity", start: 5, end: 6 },
      { label: "Fracture", start: 7, end: 8 },
      { label: "Late Age", start: 9, end: 10 },
    ]);
  });

  it("starts an era band where any civilization first reaches the era", () => {
    const history = [
      eraSnapshot(1, { A: "tribal", B: "tribal" }),
      eraSnapshot(4, { A: "bronze", B: "tribal" }),
      eraSnapshot(7, { A: "bronze", B: "an unlisted era" }),
    ];
    expect(buildEraBands(history, 12)).toEqual([
      { label: "Tribal", start: 1, end: 3 },
      { label: "Bronze Age", start: 4, end: 6 },
      { label: "an unlisted era", start: 7, end: 12 },
    ]);
    expect(buildEraBands([{ ...eraSnapshot(2, {}) }], 5)).toEqual([{ label: "Recorded Era", start: 1, end: 5 }]);
  });

  it("marks narrated spans of curated entries and of a legacy turn map, in turn order", () => {
    expect(buildNarratedSpans(undefined)).toEqual([]);
    expect(buildNarratedSpans({ "7": "b", x: "skipped", "2": "a" })).toEqual([
      { start: 2, end: 2 },
      { start: 7, end: 7 },
    ]);
    const curated = [{ covers_turns: [5, 8] }, { covers_turns: [1, 3] }] as unknown as Bundle["chronicle_entries"];
    expect(buildNarratedSpans(curated)).toEqual([{ start: 1, end: 3 }, { start: 5, end: 8 }]);
  });

  it("shows a curated entry and a gap summary once their last turn has passed", () => {
    const bundle = sampleBundle();
    bundle.chronicle_entries = [
      { ...(bundle.chronicle_entries as unknown[])[0] as object, covers_turns: [2, 4], narrative: "Rise", narrative_role: "climax" },
    ] as unknown as Bundle["chronicle_entries"];
    bundle.era_reflections = { "3": "Looking back" };
    bundle.gap_summaries = [{ turn_range: [5, 6], event_count: 3, territory_changes: 1, top_event_type: "raid" }] as Bundle["gap_summaries"];
    expect(buildChronicleFeed(null, 10)).toEqual([]);
    expect(buildChronicleFeed(bundle, 3).map((item) => item.id)).toEqual(["reflection-3"]);
    const feed = buildChronicleFeed(bundle, 6);
    expect(feed.map((item) => [item.id, item.turn, item.accent])).toEqual([
      ["segment-0", 2, "ember"],
      ["reflection-3", 3, "gold"],
      ["gap-0", 5, "stone"],
    ]);
    expect(feed[0].title).toBe("Turns 2-4");
    expect(feed[0].entry).toBe((bundle.chronicle_entries as unknown[])[0]);
    expect(feed[2].body).toBe("3 events, 1 territorial shifts, dominant type raid.");
  });

  it("keeps the latest fourteen legacy entries and reflections up to the turn", () => {
    const bundle = sampleBundle();
    bundle.chronicle_entries = Object.fromEntries(Array.from({ length: 20 }, (_, index) => [String(index + 1), `Turn text ${index + 1}`]));
    bundle.era_reflections = { "10": "Era ten" };
    const feed = buildChronicleFeed(bundle, 18);
    expect(feed).toHaveLength(14);
    expect(feed[0].turn).toBe(6);
    expect(feed.at(-1)).toMatchObject({ id: "chronicle-18", title: "Turn 18", eyebrow: "Chronicle", accent: "cyan" });
    expect(feed.filter((item) => item.id === "reflection-10")).toHaveLength(1);
  });

  it("describes the selection, a pinned event not yet recorded and the batch summary", () => {
    const summary = { signal_flags: ["collapse", "war"] } as unknown as BatchRunSummary;
    expect(selectionDescription("batch", null, null, 3)).toBe("Ranked run summaries appear here after a batch completes.");
    expect(selectionDescription("batch", null, { signal_flags: [] } as unknown as BatchRunSummary, 3))
      .toBe("Balanced run with no standout anomaly signals.");
    expect(selectionDescription("batch", null, summary, 3)).toBe("collapse · war");
    expect(selectionDescription("overview", null, null, 3)).toBe("Choose a region, civilization, or event to view its recorded details.");
    const event = { kind: "event" as const, id: "e1", label: "Siege", turn: 5 };
    expect(selectionDescription("overview", event, null, 4)).toBe("Pinned event not yet recorded at turn 4.");
    expect(selectionDescription("overview", event, null, 5, false)).toBe("Pinned event not yet recorded at turn 5.");
    expect(selectionDescription("overview", event, null, 5)).toBe("Pinned to Siege at turn 5.");
    expect(selectionDescription("overview", { kind: "region", id: "R", label: "R" }, null, 5)).toBe("Region selected: R.");
    expect(selectionDescription("overview", { kind: "civilization", id: "C", label: "C" }, null, 5)).toBe("Focus selected: C.");
  });
});
