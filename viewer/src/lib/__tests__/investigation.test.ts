import { expect, it } from "vitest";
import { comparisonBundle } from "../../__fixtures__/completedRunHistory";
import { regionalFixture } from "../../__fixtures__/regionalPopulation";
import { interestingPeriods, recordedTimeline, regionInvestigation } from "../investigation";
it("uses exact population/ownership and never final values or neighbouring snapshot rows", () => {
  const bundle = regionalFixture();
  expect(regionInvestigation(bundle, 0, 2)?.reading?.metrics.find((r) => r.id === "population")?.value).toBe(100);
  bundle.history = [bundle.history[0], bundle.history[2]];
  const gap = regionInvestigation(bundle, 0, 2)!;
  expect(gap.owner).toBeUndefined(); expect(gap.reading?.recorded).toBe(false);
  bundle.history.push(structuredClone(bundle.history[0]));
  expect(regionInvestigation(bundle, 0, 1)?.owner).toBeUndefined();
});
it("keeps uncontrolled separate from unknown and refuses duplicate canonical region identity", () => {
  const bundle = comparisonBundle(); bundle.history[0].region_control.A = null;
  expect(regionInvestigation(bundle, 0, 1)?.owner).toBeNull();
  bundle.world_state.regions[1].name = "A";
  expect(regionInvestigation(bundle, 0, 1)).toMatchObject({ unique: false, reading: null, owner: undefined });
});
it("only assigns events with explicit region attribution and respects tick completion", () => {
  const bundle = comparisonBundle();
  bundle.events_timeline = [
    { ...bundle.events_timeline[0], event_id: "local", turn: 1, region: "A" },
    { ...bundle.events_timeline[0], event_id: "civ", turn: 1, actors: ["A"] },
    { ...bundle.events_timeline[0], event_id: "future", turn: 2, region: "A", description: "SECRET" },
  ];
  expect(regionInvestigation(bundle, 0, 1)?.events).toHaveLength(0);
  expect(regionInvestigation(bundle, 0, 2)?.events.map((r) => r.event.event_id)).toEqual(["local"]);
  expect(JSON.stringify(regionInvestigation(bundle, 0, 2))).not.toContain("SECRET");
});
it("groups only known activity into fixed windows and exposes all underlying source reports", () => {
  const bundle = comparisonBundle();
  expect(interestingPeriods(bundle, 1)).toHaveLength(0); // exact duplicate war is one report
  const periods = interestingPeriods(bundle, 3);
  expect(periods).toHaveLength(1);expect(periods[0]).toMatchObject({ start: 1, end: 3 });
  expect(periods[0].events.map((r) => r.source)).toEqual(["/events_timeline/0", "/events_timeline/2"]);
  const before = JSON.stringify(periods);
  bundle.events_timeline.push({ ...bundle.events_timeline[0], turn: 9, description: "FUTURE SECRET" });
  expect(JSON.stringify(interestingPeriods(bundle, 3))).toBe(before);
});
it("retains conflicting id reports as unpinnable, not a fabricated single event", () => {
  const bundle = comparisonBundle();bundle.events_timeline = [bundle.events_timeline[0], { ...bundle.events_timeline[0], description: "different report" }];
  const rows = recordedTimeline(bundle, 1);expect(rows).toHaveLength(2);expect(rows.every((r) => !r.canPin)).toBe(true);
});
