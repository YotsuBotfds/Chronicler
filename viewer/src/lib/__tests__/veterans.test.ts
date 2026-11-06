import { describe, expect, it } from "vitest";
import type { TurnSnapshot } from "../../types";
import { unmetByReason, veteranFunnel, veteranOutcomeCounts, veteransAt } from "../veterans";

/** Constructed observations to test the reader; not a simulation run. */
const placed = {
  record_id: 0, agent_id: 10, civ: 0, army_id: "army-3", war_key: "A:B", war_start: 2, cause: "demobilised",
  released_turn: 4, released_region: 1, region: 1, age: 30, status: "placed", reason: null,
  closed_turn: null, closed_reason: null, placements: 1, placed_turns: 2,
  spells: [{ kind: "placed:crew", site: 0, region: 1, start_turn: 5, last_turn: 6, turns: 2, prioritised: true }],
  outcomes: [{ turn: 4, kind: "waiting", detail: { region: 1 } },
    { turn: 5, kind: "placed:crew", detail: { site: 0, region: 1, prioritised: true } }],
  outcomes_dropped: 0,
};
const waiting = { ...placed, record_id: 1, agent_id: 11, cause: "desertion", status: "waiting", placements: 0,
  placed_turns: 0, spells: [], outcomes: [{ turn: 4, kind: "waiting", detail: { region: 1 } }] };
const lost = { ...waiting, record_id: 2, agent_id: 12, status: "ineligible", reason: "control_lost", region: 2,
  outcomes: [...waiting.outcomes, { turn: 6, kind: "migrated", detail: { from: 1, to: 2 } },
    { turn: 6, kind: "control_lost", detail: { region: 2, controller: 1 } }] };
const died = { ...waiting, record_id: 3, agent_id: 13, status: "closed", closed_turn: 6, closed_reason: "died",
  outcomes: [...waiting.outcomes, { turn: 6, kind: "died", detail: { region: 1 } }] };
const frame = {
  turn: 6, priority_applied: true,
  captured: [{ agent_id: 20, civ: 0, army_id: "army-5", war_key: "A:B", war_start: 2, cause: "scattered", region: 0 }],
  captured_total: 1, captured_by_cause: { scattered: 1 }, offered: [[1, [10, 11]]],
  placed: [{ agent_id: 10, kind: "placed:crew", region: 1, site: 0, prioritised: true, new_spell: false }],
  waiting: [{ agent_id: 11, region: 1, reason: "not_crew_eligible" }, { agent_id: 13, region: 1, reason: "no_site" }],
  outcomes: [{ agent_id: 13, record_id: 3, kind: "died", detail: { region: 1 } }],
  counts: { open: 3, waiting: 2 }, rows_dropped: 0,
};
const record = {
  schema_version: 1, stage: "RS3", enabled: true, mode: "priority", source_turn: 6, frame,
  veterans: [placed, waiting, lost], veterans_omitted: 0, closed: [died],
  counters: { captured: 5, offered: 7, placements: 1, placement_turns: 2, people_placed: 1, closed_died: 1,
    waiting_turns: 6, control_lost: 1 },
  parameters: { eligible_turns: 20, costs: "none" },
};
const snap = (veteran_reintegration: unknown, turn = 7) =>
  ({ turn, livelihoods: { schema_version: 1, veteran_reintegration } } as unknown as TurnSnapshot);

describe("veterans reader", () => {
  it("reads dated, well-formed records only", () => {
    expect(veteransAt(snap(record), 3)?.veterans.map((v) => v.agent_id)).toEqual([10, 11, 12]);
    expect(veteransAt(snap(record, 8), 3)).toBeNull();                    // misdated
    expect(veteransAt(snap(record), 2)).toBeNull();                       // region out of range
    expect(veteransAt(snap({ ...record, stage: "RS0" }), 3)).toBeNull();
    expect(veteransAt(snap({ ...record, mode: "sometimes" }), 3)).toBeNull();
    expect(veteransAt(null, 3)).toBeNull();
  });

  it("refuses inconsistent statuses, wars, closures and outcomes", () => {
    const bad = (v: unknown) => veteransAt(snap({ ...record, veterans: [v] , frame: null }), 3);
    expect(bad({ ...placed, spells: [{ ...placed.spells[0], last_turn: 5, turns: 1 }] })).toBeNull();  // placed, not this turn
    expect(bad({ ...waiting, reason: "minor" })).toBeNull();
    expect(bad({ ...lost, reason: null })).toBeNull();
    expect(bad({ ...waiting, war_start: null })).toBeNull();               // half a war identity
    expect(bad({ ...waiting, cause: "retired" })).toBeNull();
    expect(bad({ ...waiting, outcomes: [{ turn: 9, kind: "waiting", detail: null }] })).toBeNull();     // future
    expect(bad({ ...waiting, outcomes: [...lost.outcomes].reverse() })).toBeNull();                     // undated order
    expect(bad({ ...waiting, placed_turns: 0, placements: 1 })).toBeNull();
    expect(veteransAt(snap({ ...record, veterans: [waiting, { ...waiting, record_id: 9 }] }), 3)).toBeNull();
    expect(veteransAt(snap({ ...record, closed: [{ ...died, closed_turn: 5 }] }), 3)).toBeNull();
    expect(veteransAt(snap({ ...record, closed: [{ ...died, closed_reason: "expired" }] }), 3)).toBeNull();
  });

  it("refuses priority in the control and an unbalanced frame", () => {
    expect(veteransAt(snap({ ...record, mode: "record_only" }), 3)).toBeNull();
    const control = { ...record, mode: "record_only", veterans: [waiting, lost], frame: { ...frame,
      priority_applied: false, placed: [{ ...frame.placed[0], prioritised: false }] } };
    expect(veteransAt(snap(control), 3)?.mode).toBe("record_only");
    expect(veteransAt(snap({ ...record, frame: { ...frame, captured_total: 2 } }), 3)).toBeNull();
    expect(veteransAt(snap({ ...record, frame: { ...frame, waiting: [{ agent_id: 10, region: 1, reason: "no_site" }] } }), 3)).toBeNull();
    expect(veteransAt(snap({ ...record, frame: { ...frame, waiting: [{ agent_id: 11, region: 1, reason: "busy" }] } }), 3)).toBeNull();
    expect(veteransAt(snap({ ...record, frame: { ...frame, turn: 5 } }), 3)).toBeNull();
  });

  it("accepts one veteran placed on the crew and as an apprentice in one turn (RS1 rules version 2)", () => {
    // Version 2 trains an apprentice on the planned crew, so both placements are dated the same turn.
    const both = { ...frame, placed: [...frame.placed, { ...frame.placed[0], kind: "placed:apprentice", new_spell: true }] };
    expect(veteransAt(snap({ ...record, frame: both }), 3)?.frame?.placed).toHaveLength(2);
    const twice = { ...frame, placed: [...frame.placed, { ...frame.placed[0] }] };
    expect(veteransAt(snap({ ...record, frame: twice }), 3)).toBeNull();     // the same opening twice
  });

  it("keeps an unobserved turn unknown, not zero, and counts outcomes", () => {
    const parsed = veteransAt(snap({ ...record, frame: null }), 3)!;
    expect(parsed.frame).toBeNull();
    expect(unmetByReason(parsed)).toBeNull();
    expect(unmetByReason({ ...parsed, frame: { ...frame, offered: null } } as never)).toBeNull();
    const full = veteransAt(snap(record), 3)!;
    expect([...unmetByReason(full)!]).toEqual([["not_crew_eligible", [11]], ["no_site", [13]]]);
    expect(veteranFunnel(full)[0]).toEqual(["Released alive from armies (captured)", 5]);
    expect(veteranFunnel(full).at(-1)).toEqual(["People placed (distinct)", 1]);
    expect(veteranOutcomeCounts(full).find(([k]) => k === "Expired")?.[1]).toBe(0);
    expect(veteranOutcomeCounts(full).find(([k]) => k === "Died")?.[1]).toBe(1);
  });
});
