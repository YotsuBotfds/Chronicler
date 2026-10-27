import { describe, expect, it } from "vitest";
import type { Bundle, NewChronicleEntry } from "../../types";
import { passageSources, resolveFact } from "../narrationSources";

const bundle = {
  events_timeline: [
    { turn: 3, event_type: "war", actors: ["Kethani Empire"], description: "Kethani Empire goes to war", consequences: [], importance: 7, event_id: "3:war:0" },
    { turn: 9, event_type: "famine", actors: ["Ashkari Nomads"], description: "", consequences: [], importance: 8, event_id: "9:famine:0" },
  ],
  named_events: [{ name: "Battle of the Ford", event_type: "battle", turn: 3, actors: [], region: null, description: "A great battle", importance: 7 }],
  world_state: {
    civilizations: [
      { name: "Kethani Empire", great_persons: [{ name: "General Asha", agent_id: 41 }] },
      { name: "Ashkari Nomads" },
    ],
    regions: [{ name: "Iron Peaks" }, { name: "Amber Valley" }],
    retired_persons: [{ name: "Consul Ulveth", agent_id: 7 }],
    artifacts: [{ artifact_id: 2, name: "The Obelisk", origin_turn: 1 }],
  },
  historiography: { chroniclers: [{ id: "court:0", name: "the Kethani chronicles" }] },
} as unknown as Bundle;

const entry = {
  turn: 3, covers_turns: [3, 5], events: [], named_events: [], narrative: "The war began. The obelisk stood.",
  importance: 1, narrative_role: "climax",
  causal_links: [{ cause_turn: 1, cause_event_type: "drought", effect_turn: 3, effect_event_type: "war", pattern: "drought→war" }],
  provenance: {
    v: 1, narrator: "llm", as_of: 5, names: [],
    facts: [["art2", 1], ["e0", 3], ["n0", 3], ["e1", 9, "r"], "court:0/e0"],
    spans: [[0, 14, ["e0", "n0"]], [15, 33, ["art2"]]],
  },
} as unknown as NewChronicleEntry;

describe("resolveFact", () => {
  it("names each record the id names", () => {
    const r = (id: string, turn: number | null = null) => resolveFact(bundle, entry, id, turn);
    expect(r("e0")).toMatchObject({ kind: "event", turn: 3, label: "war: Kethani Empire goes to war" });
    expect(r("e1").label).toBe("famine: Ashkari Nomads");
    expect(r("e9")).toMatchObject({ kind: "event", label: "an event this bundle does not hold", turn: null });
    expect(r("n0")).toMatchObject({ kind: "landmark", label: "Battle of the Ford: A great battle", turn: 3 });
    expect(r("court:0/e0", 3)).toMatchObject({ kind: "account", label: "the Kethani chronicles on war: Kethani Empire goes to war" });
    expect(r("p41").label).toBe("General Asha");
    expect(r("p7").label).toBe("Consul Ulveth");
    expect(r("art2")).toMatchObject({ kind: "artifact", label: "The Obelisk", turn: 1 });
    expect(r("s6.ruler.c0")).toMatchObject({ kind: "state", label: "State after turn 5: ruler of Kethani Empire", turn: 5 });
    expect(r("s6.war.c0-c1").label).toBe("State after turn 5: war of Kethani Empire and Ashkari Nomads");
    expect(r("s6.food.r1").label).toBe("State after turn 5: food in Amber Valley");
    expect(r("d2-6.c1.stability")).toMatchObject({ kind: "change", label: "Change of Ashkari Nomads stability, turns 1 to 5", turn: 5 });
    expect(r("d2-6.r0").label).toBe("Change of control of Iron Peaks, turns 1 to 5");
    expect(r("w3-5")).toMatchObject({ kind: "window", label: "Other events in turns 3-5", turn: 5 });
    expect(r("o5.displacement")).toMatchObject({ kind: "observation", turn: 5 });
    expect(r("L.r0", 5)).toMatchObject({ kind: "names", label: "In-world names of Iron Peaks" });
    expect(r("k0").label).toBe("drought→war");
  });
});

describe("passageSources", () => {
  it("lists the cited facts first, then the others given", () => {
    const out = passageSources(bundle, entry)!;
    expect(out.narrator).toBe("llm");
    expect(out.cited).toBe(3);
    expect(out.given).toBe(5);
    expect(out.sources.map((s) => [s.id, s.cited, s.retrospective])).toEqual([
      ["e0", true, false], ["n0", true, false], ["art2", true, false],
      ["e1", false, true], ["court:0/e0", false, false],
    ]);
    expect(out.sources[0].event?.event_id).toBe("3:war:0");
    expect(out.sources[4].turn).toBe(5);  // a bare id is dated the passage's own turn
  });

  it("is null without provenance", () => {
    expect(passageSources(bundle, { ...entry, provenance: undefined })).toBeNull();
  });
});
