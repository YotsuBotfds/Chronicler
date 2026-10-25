import { describe, expect, it } from "vitest";
import systemsFixture from "../../__fixtures__/systems_bundle.json";
import sampleFixture from "../../__fixtures__/sample_bundle.json";
import type { Bundle, CampaignWar, TurnSnapshot } from "../../types";
import {
  agendaGoal, agendaRegion, formPalette, formRows, governanceCivs, hasGovernanceRecord, herdCivs, modeRows,
} from "../polity";
import { battleLosses, battlesUpTo, hasCampaignRecord, warLeader, warRows } from "../wars";

const systems = systemsFixture as unknown as Bundle;
const sample = sampleFixture as unknown as Bundle;
const worldCivs = systems.world_state.civilizations.map((civ) => civ.name);

function snap(turn: number, extra: Partial<TurnSnapshot> = {}): TurnSnapshot {
  return { turn, civ_stats: {}, region_control: {}, relationships: {}, ...extra };
}

function war(score: number, start = 1): CampaignWar {
  return { war: "A:B", attacker: "A", defender: "B", aim: "conquest", aim_region: "R", score, start_turn: start, battles: 0 };
}

describe("wars", () => {
  it("names the side ahead on war score", () => {
    expect(warLeader(war(12))).toBe("A");
    expect(warLeader(war(-3))).toBe("B");
    expect(warLeader(war(0))).toBeNull();
  });

  it("builds one row per war, split where the lead changes", () => {
    const empty = { armies: [], battles: [], occupations: [] };
    const history = [
      snap(1, { campaign: { ...empty, wars: [war(0)] } }),
      snap(2, { campaign: { ...empty, wars: [war(10)] } }),
      snap(3, { campaign: { ...empty, wars: [war(20), war(0, 3)] } }),
      snap(4, { campaign: { ...empty, wars: [] } }),
    ];
    const rows = warRows(history, () => "#123456");
    expect(rows.map((row) => row.id)).toEqual(["A:B@1", "A:B@3"]);
    expect(rows[0].segments.map((segment) => [segment.start, segment.end, segment.text])).toEqual([
      [1, 2, "level"], [2, 4, "A"],
    ]);
    expect(rows[0].segments[1].label).toContain("score 10 to 20");
  });

  it("collects the battles recorded up to a turn from the real fixture", () => {
    expect(hasCampaignRecord(systems.history)).toBe(true);
    expect(hasCampaignRecord(sample.history)).toBe(false);
    const all = battlesUpTo(systems.history, 999);
    const total = systems.history.reduce((sum, snapshot) => sum + (snapshot.campaign?.battles.length ?? 0), 0);
    expect(all).toHaveLength(total);
    expect(battlesUpTo(systems.history, 0)).toEqual([]);
    expect(battleLosses(all)).toBe(all.reduce((sum, b) => sum + b.attacker_losses + b.defender_losses, 0));
  });
});

describe("nomads", () => {
  it("keeps rows only for peoples that ever herded", () => {
    const history = [
      snap(1, { nomads: { modes: { A: "sedentary", B: "nomadic" }, herds: { B: 20 }, herd_total: 20, tributes: [], hordes: [], counters: {} } }),
      snap(5, { nomads: { modes: { A: "sedentary", B: "agro_pastoral" }, herds: {}, herd_total: 0, tributes: [], hordes: [], counters: {} } }),
    ];
    const rows = modeRows(history, ["A", "B"], () => "#fff");
    expect(rows.map((row) => row.id)).toEqual(["B"]);
    expect(rows[0].segments.map((segment) => segment.text)).toEqual(["Nomadic", "Agro-pastoral"]);
    expect(herdCivs(history, ["A", "B"])).toEqual(["B"]);
    expect(modeRows(systems.history, worldCivs, () => "#fff").length).toBeGreaterThan(0);
  });
});

describe("agendas", () => {
  it("phrases a vow as the simulation does, resolving civ targets to names", () => {
    expect(agendaGoal({ kind: "protect_trade_route", target: "1" }, systems))
      .toBe(`keep the trade road to ${worldCivs[1]} open`);
    expect(agendaGoal({ kind: "lead_campaign", target: "Dadun Grasslands" }, systems))
      .toBe("lead a campaign to take Dadun Grasslands");
    expect(agendaGoal({ kind: "invent_technique", target: "bronze_working" }, systems)).toBe("discover bronze working");
    expect(agendaGoal({ kind: "advance_learning", target: "iron" }, systems)).toBe("carry learning into the iron era");
    expect(agendaGoal({ kind: "lend_to_crown", target: null }, systems)).toBe("lend to the crown");
    expect(agendaRegion({ kind: "found_shrine", target: "X" })).toBe("X");
    expect(agendaRegion({ kind: "open_trade_route", target: "2" })).toBeNull();
  });
});

describe("governance", () => {
  it("reads forms of government and PSI-crisis marks from civ rows", () => {
    expect(hasGovernanceRecord(systems.history)).toBe(true);
    expect(hasGovernanceRecord(sample.history)).toBe(false);
    const civs = governanceCivs(systems.history, worldCivs);
    expect(civs.length).toBeGreaterThan(0);
    const palette = formPalette(systems.history);
    const rows = formRows(systems.history, civs, palette, () => "#fff");
    expect(rows).toHaveLength(civs.length);
    const colors = new Set(palette.values());
    expect(rows.every((row) => row.segments.every((segment) => colors.has(segment.color)))).toBe(true);
    const crisisTurns = systems.history.filter((snapshot) =>
      Object.values(snapshot.civ_stats).some((row) => row.governance?.psi_crisis));
    expect(rows.some((row) => (row.marks?.length ?? 0) > 0)).toBe(crisisTurns.length > 0);
  });
});
