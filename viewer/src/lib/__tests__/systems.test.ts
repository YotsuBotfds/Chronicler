import { describe, expect, it } from "vitest";
import systemsFixture from "../../__fixtures__/systems_bundle.json";
import sampleFixture from "../../__fixtures__/sample_bundle.json";
import type { Bundle, Event, TurnSnapshot } from "../../types";
import {
  buildSegments, civSeries, debtToRevenue, epidemicRows, eraRows, eventsOfTypes, ladderRows, pairMatrix,
  practiceSummary, preferredSystem, presentSystems, regionOutbreaks, regionPractice, trustColor, zonePorts, zoneRows,
} from "../systems";

const systems = systemsFixture as unknown as Bundle;
const sample = sampleFixture as unknown as Bundle;
const last = systems.history[systems.history.length - 1];

function snap(turn: number, extra: Partial<TurnSnapshot> = {}): TurnSnapshot {
  return { turn, civ_stats: {}, region_control: {}, relationships: {}, ...extra };
}

describe("systems helpers", () => {
  it("finds the systems a bundle records, and none in a bundle without them", () => {
    expect(presentSystems(systems.history)).toEqual(["epidemics", "finance", "diplomacy", "techniques", "maritime"]);
    expect(presentSystems(sample.history)).toEqual([]);
    const partial = systems.history.map((snapshot) => ({ ...snapshot, finance: undefined }));
    expect(presentSystems(partial)).not.toContain("finance");
  });

  it("merges consecutive snapshots into segments that end at the next recorded turn", () => {
    expect(buildSegments([1, 3, 5, 9], ["a", "a", null, "b"])).toEqual([
      { start: 1, end: 5, key: "a", from: 0, to: 1 },
      { start: 9, end: 10, key: "b", from: 3, to: 3 },
    ]);
    expect(buildSegments([1, 2, 3], ["a", "b", "a"]).map((segment) => segment.key)).toEqual(["a", "b", "a"]);
  });

  it("builds one outbreak row per region and pathogen, in region order", () => {
    const history = [
      snap(1, { epidemics: { active: [
        { region: "B", pathogen: "flux", prevalence: 0.02, immune: 0.1, cases: 3, deaths: 1, virgin: false },
        { region: "A", pathogen: "pox", prevalence: 0.05, immune: 0, cases: 9, deaths: 2, virgin: true },
      ], deaths: 3, deaths_by_pathogen: {}, deaths_total: 3, quarantine: [], strains: {} } }),
      snap(2, { epidemics: { active: [
        { region: "A", pathogen: "pox", prevalence: 0.08, immune: 0.2, cases: 4, deaths: 5, virgin: true },
      ], deaths: 5, deaths_by_pathogen: {}, deaths_total: 8, quarantine: [], strains: {} } }),
    ];
    const rows = epidemicRows(history, ["A", "B"]);
    expect(rows.map((row) => row.id)).toEqual(["A|pox", "B|flux"]);
    expect(rows[0].label).toBe("A · Pox");
    expect(rows[0].segments).toHaveLength(1);
    expect(rows[0].segments[0]).toMatchObject({ start: 1, end: 3 });
    expect(rows[0].segments[0].label).toContain("peak prevalence 8.0%");
    expect(rows[0].segments[0].label).toContain("7 deaths");
    expect(rows[0].segments[0].label).toContain("virgin soil");
    expect(rows[1].segments[0]).toMatchObject({ start: 1, end: 2 });
  });

  it("reads per-region epidemic and technique state from the real fixture", () => {
    const outbreaks = regionOutbreaks(last, "Dililene Coast");
    expect(outbreaks).toHaveLength(1);
    expect(outbreaks[0].pathogen).toBe("fever");
    expect(regionOutbreaks(last, "Nowhere")).toEqual([]);
    const practice = regionPractice(last, Object.keys(last.techniques?.regions ?? {})[0]);
    expect(practice?.length).toBeGreaterThan(0);
    expect(regionPractice(snap(1, { techniques: { known: {}, practised: {}, rows: 0 } }), "A")).toBeNull();
    expect(practiceSummary(snap(1))).toBeNull();
    const summary = practiceSummary(last);
    expect(summary?.[0].present).toBeGreaterThan(0);
  });

  it("keeps civ series gaps as null instead of zero", () => {
    const history = [snap(1, { finance: { civs: { A: { debt: 10, revenue_ema: 4 } }, loans: 1, totals: {} } as never }), snap(2)];
    const rows = civSeries(history, ["A"], (s, civ) => {
      const row = s.finance?.civs[civ];
      return row ? debtToRevenue(row.debt, row.revenue_ema) : null;
    });
    expect(rows).toEqual([{ turn: 1, A: 2.5 }, { turn: 2, A: null }]);
    expect(debtToRevenue(5, 0)).toBe(5);
  });

  it("uses the full pair matrix when exported and falls back to the top grievances", () => {
    const full = pairMatrix(last);
    expect(full.complete).toBe(true);
    const [holder, row] = Object.entries(last.diplomacy?.pairs ?? {})[0];
    const [target, [trust, grievance]] = Object.entries(row)[0];
    expect(full.cells.get(holder)?.get(target)).toEqual({ trust, grievance });

    const older = { ...last.diplomacy!, pairs: undefined };
    const fallback = pairMatrix({ ...last, diplomacy: older });
    expect(fallback.complete).toBe(false);
    expect(fallback.cells.size).toBeGreaterThan(0);
    expect(pairMatrix(snap(1)).civs).toEqual([]);
  });

  it("colours trust on a diverging scale with a neutral midpoint", () => {
    expect(trustColor(0)).toBe("rgb(56, 56, 53)");
    expect(trustColor(80)).toBe("rgb(57, 135, 229)");
    expect(trustColor(-80)).toBe("rgb(230, 103, 103)");
  });

  it("builds ladder, era and sea-zone rows from the real fixture", () => {
    const ladder = ladderRows(systems.history);
    expect(ladder.map((row) => row.label)).toEqual(["Doguri Republic → League of Fewen"]);
    expect(ladder[0].segments[0].text).toBe("client");

    const eras = eraRows(systems.history, ["Thyrodori Confederacy"], () => "#fff");
    expect(eras[0].segments[0].text).toBe("Tribal");

    const zones = zoneRows(systems.history, () => "#123456");
    expect(zones).toHaveLength(7);
    const morendor = zones.find((row) => row.id === "the Morendor Bight");
    expect(morendor?.segments.some((segment) => segment.label.includes("controlled by"))).toBe(true);
    expect(morendor?.marks?.[0].label).toContain("Thyrodori Confederacy blockades League of Fewen");

    const ports = zonePorts(systems.world_state.maritime?.zones, systems.world_state.regions.map((region) => region.name));
    expect(ports.get("the Morendor Bight")).toHaveLength(6);
  });

  it("lists system events latest first up to the scrubbed turn", () => {
    const events = [
      { turn: 3, event_type: "loan_taken", description: "a" },
      { turn: 9, event_type: "debasement", description: "b" },
      { turn: 5, event_type: "war", description: "c" },
      { turn: 3, event_type: "state_default", description: "d" },
    ] as Event[];
    expect(eventsOfTypes(events, ["loan_taken", "debasement", "state_default"], 8).map((event) => event.description))
      .toEqual(["a", "d"]);
  });

  it("opens the system that fits the shell surface", () => {
    expect(preferredSystem("trade", ["epidemics", "finance"])).toBe("finance");
    expect(preferredSystem("campaign", ["epidemics", "maritime"])).toBe("maritime");
    expect(preferredSystem("overview", ["finance", "techniques"])).toBe("finance");
    expect(preferredSystem("overview", [])).toBeNull();
  });
});
