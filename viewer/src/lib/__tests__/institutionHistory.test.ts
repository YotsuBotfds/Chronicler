import { describe, expect, it } from "vitest";
import { cityHistorySelection, institutionHistoryFixture } from "../../__fixtures__/institutionHistory";
import { institutionObservationValues, readInstitutionHistory } from "../institutionHistory";

describe("city institutional history", () => {
  it("uses selected snapshot relationships and values with real settlement identity", () => {
    const reading = readInstitutionHistory(institutionHistoryFixture(), 3, cityHistorySelection);
    expect(reading).toMatchObject({ supported: true, name: "New Harbor", id: 41, firstRecordedTurn: 1, lastRecordedTurn: 3 });
    expect(reading.selected).toMatchObject({ status: "recorded", sourceRef: "/history/1/cities/cities/0", row: { residents: 75, wealth: 0, region: "B" } });
    expect(reading.related).toEqual([{ kind: "region", name: "B" }, { kind: "civilization", name: "New Lord" }]);
    expect(institutionObservationValues(reading.selected!.row!).find((field) => field.label === "Civic purse")?.value).toBe("0");
  });

  it("excludes all final side fields and future lifecycle values", () => {
    const bundle = institutionHistoryFixture();
    const reading = readInstitutionHistory(bundle, 3, cityHistorySelection);
    expect(JSON.stringify(reading)).not.toContain("FUTURE_SECRET");
    expect(JSON.stringify(reading)).not.toContain("999999");
    expect(reading.moments.map((moment) => moment.kind)).toEqual(["sacked", "founded"]);
  });

  it("gates lifecycle and event tick T at completed snapshot T+1", () => {
    const bundle = institutionHistoryFixture();
    expect(readInstitutionHistory(bundle, 0, cityHistorySelection).moments).toEqual([]);
    expect(readInstitutionHistory(bundle, 2, cityHistorySelection).moments.map((moment) => moment.kind)).toEqual(["founded"]);
    const moment = readInstitutionHistory(bundle, 3, cityHistorySelection).moments[0];
    expect(moment).toMatchObject({ kind: "sacked", sourceTurn: 2, turn: 3, eventRef: "/events_timeline/1", sourceRef: "/world_state/cities/fallen/0/history/1" });
    expect(readInstitutionHistory(bundle, 5, cityHistorySelection).moments.some((item) => item.kind === "fell")).toBe(false);
    expect(readInstitutionHistory(bundle, 6, cityHistorySelection).moments[0].kind).toBe("fell");
  });

  it("compares exact named endpoint windows without inferring timing or benefits", () => {
    const change = readInstitutionHistory(institutionHistoryFixture(), 3, cityHistorySelection).changes[0];
    expect(change).toMatchObject({ from: 1, to: 3, continuousCoverage: false });
    expect(change.fields.find((field) => field.label === "Residents")).toMatchObject({ before: "100", after: "75", delta: -25,
      beforeSource: "/history/0/cities/cities/0/residents", afterSource: "/history/1/cities/cities/0/residents" });
    expect(change.fields.find((field) => field.label === "Recorded name")).toMatchObject({ before: "Old Harbor", after: "New Harbor", delta: null });
    expect(change.fields.find((field) => field.label === "Recorded region")).toMatchObject({ before: "A", after: "B" });
    expect(change.fields.find((field) => field.label === "Charter")).toMatchObject({ before: "none", after: "market rights", delta: 1 });
  });

  it("leaves sparse selected turns unknown instead of carrying earlier values or relations", () => {
    const reading = readInstitutionHistory(institutionHistoryFixture(), 4, cityHistorySelection);
    expect(reading.selected).toMatchObject({ turn: 4, status: "unavailable", row: null, sourceRef: "/history" });
    expect(reading.related).toEqual([]);
    expect(reading.lastRecordedTurn).toBe(3);
    expect(reading.status).toContain("earlier values are not carried forward");
  });

  it("distinguishes unavailable, absent and duplicate city observations", () => {
    const bundle = institutionHistoryFixture();
    delete bundle.history[0].cities;
    bundle.history[1].cities!.cities.push({ ...bundle.history[1].cities!.cities[0], wealth: 555 });
    const reading = readInstitutionHistory(bundle, 6, cityHistorySelection);
    expect(reading.observations.map((item) => item.status)).toEqual(["unavailable", "ambiguous", "absent"]);
    expect(reading.observations.every((item) => item.row === null)).toBe(true);
    expect(reading.name).toBe("City 41 (name unknown)");
    expect(reading.changes).toEqual([]);
  });

  it("excludes duplicate snapshot endpoints without mutating out-of-order input", () => {
    const bundle = institutionHistoryFixture();
    bundle.history.push(structuredClone(bundle.history[1]));
    bundle.history.reverse();
    const before = JSON.stringify(bundle);
    const reading = readInstitutionHistory(bundle, 3, cityHistorySelection);
    expect(reading.selected!.status).toBe("ambiguous");
    expect(reading.firstRecordedTurn).toBe(1);
    expect(reading.lastRecordedTurn).toBe(1);
    expect(reading.observations[0].sourceRef).toBe("/history/4/cities/cities/0");
    expect(JSON.stringify(bundle)).toBe(before);
  });

  it("never joins different settlement IDs with the same display name", () => {
    const bundle = institutionHistoryFixture();
    bundle.history[1].cities!.cities[0] = { ...bundle.history[1].cities!.cities[0], id: 99, name: "Old Harbor" };
    const reading = readInstitutionHistory(bundle, 3, cityHistorySelection);
    expect(reading.lastRecordedTurn).toBe(1);
    expect(reading.selected!.status).toBe("absent");
    expect(reading.changes).toEqual([]);
  });

  it("does not call reappearance or increased wealth a restoration or recovery", () => {
    const reading = readInstitutionHistory(institutionHistoryFixture(), 10, cityHistorySelection);
    const window = reading.changes.find((item) => item.to === 10)!;
    expect(window).toMatchObject({ from: 3, to: 10, continuousCoverage: false });
    expect(window.fields.find((field) => field.label === "Civic purse")?.delta).toBe(99999);
    expect(reading.coverage.join(" ")).toContain("Reappearance, resiting and restoration are not inferred");
    expect(reading.moments.some((moment) => ["restored", "recovered", "destroyed"].includes(moment.kind))).toBe(false);
  });

  it("does not infer life dates from standalone final dates or first/last observations", () => {
    const bundle = institutionHistoryFixture();
    bundle.world_state.cities!.fallen![0].history = [];
    const reading = readInstitutionHistory(bundle, 10, cityHistorySelection);
    expect(reading.moments).toEqual([]);
    expect(reading.firstRecordedTurn).toBe(1);
    expect(reading.lastRecordedTurn).toBe(10);
  });

  it("refuses duplicate final records rather than selecting one lifecycle", () => {
    const bundle = institutionHistoryFixture();
    bundle.world_state.cities!.cities!.push({ ...bundle.world_state.cities!.fallen![0] });
    const reading = readInstitutionHistory(bundle, 6, cityHistorySelection);
    expect(reading.moments).toEqual([]);
    expect(reading.coverage.join(" ")).toContain("Duplicate final city IDs");
    expect(reading.firstRecordedTurn).toBe(1);
  });

  it("keeps missing, duplicate and wrong-clock event links unresolved without guessing", () => {
    const bundle = institutionHistoryFixture();
    bundle.events_timeline.push({ ...bundle.events_timeline[0] });
    bundle.events_timeline[1].turn = 9;
    const reading = readInstitutionHistory(bundle, 3, cityHistorySelection);
    expect(reading.moments).toHaveLength(2);
    expect(reading.moments.every((moment) => moment.event === null && moment.eventRef === null)).toBe(true);
    expect(JSON.stringify(reading)).not.toContain("FUTURE_SECRET_EVENT_DESCRIPTION");
    bundle.events_timeline = [];
    expect(readInstitutionHistory(bundle, 3, cityHistorySelection).moments[0].status).toContain("No event is guessed");
  });

  it("only links exact selected relationships when their name identity is unambiguous", () => {
    const bundle = institutionHistoryFixture();
    bundle.world_state.regions.push({ ...bundle.world_state.regions[1] });
    delete bundle.history[1].civ_stats["New Lord"];
    expect(readInstitutionHistory(bundle, 3, cityHistorySelection).related).toEqual([]);
    bundle.world_state.civilizations.push({ ...bundle.world_state.civilizations[0] });
    bundle.history[1].cities!.cities[0].lord = "Old Realm";
    expect(readInstitutionHistory(bundle, 3, cityHistorySelection).related).toEqual([]);
  });

  it("handles older bundles and unsupported identities honestly", () => {
    const bundle = institutionHistoryFixture();
    delete bundle.world_state.cities;
    bundle.history.forEach((snapshot) => delete snapshot.cities);
    const reading = readInstitutionHistory(bundle, 3, cityHistorySelection);
    expect(reading.moments).toEqual([]);
    expect(reading.selected!.row).toBeNull();
    expect(reading.coverage.join(" ")).toContain("No final city-ID history record");
    expect(readInstitutionHistory(bundle, 3, { kind: "institution", identity: { namespace: "scholarship", index: 7 }, sourceRef: "/history/1/scholarship/seats/0" }).supported).toBe(false);
    expect(readInstitutionHistory(bundle, 3, { ...cityHistorySelection, identity: null }).status).toContain("identity is unresolved");
    expect(readInstitutionHistory(bundle, NaN, cityHistorySelection).supported).toBe(false);
  });

  it("preserves unknown optional values instead of treating them as measured changes", () => {
    const bundle = institutionHistoryFixture();
    bundle.history[0].cities!.cities[0].crafts = 0;
    delete bundle.history[1].cities!.cities[0].crafts;
    const reading = readInstitutionHistory(bundle, 3, cityHistorySelection);
    expect(reading.changes[0].fields.some((field) => field.label === "Wares")).toBe(false);
    expect(institutionObservationValues(reading.selected!.row!).find((field) => field.label === "Wares")?.value).toBe("Not recorded");
  });
});
