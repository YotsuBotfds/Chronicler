/** A small D2 attribution record (two civilizations, three regions) for the reader and panel tests. */
export const frame = {
  turn: 9,
  casualties: {
    rows: [
      { war: "Ashkari:Selurian", war_start: 3, victim: 0, victim_name: "Ashkari", actor: 1, actor_name: "Selurian",
        opponent: 1, opponent_name: "Selurian", cause: "battle", class: "combat", kind: "field", deaths: 4 },
      { war: "Ashkari:Selurian", war_start: 3, victim: 0, victim_name: "Ashkari", actor: null, actor_name: null,
        opponent: 1, opponent_name: "Selurian", cause: "natural", class: "natural", kind: null, deaths: 2 },
    ],
    by_class: { combat: 4, attrition: 0, natural: 2 },
    by_cause: { battle: 4, trapped: 0, revolt: 0, attrition: 0, natural: 2 },
    unresolved: 0,
    armies: [{ army: "army-1", civ: 0, civ_name: "Ashkari", recorded: 6, counter_change: 6, closes: true }],
    battle_checks: [{ battle: 4, side: "Ashkari", recorded: 4, battle_losses: 5, holds: true }],
    war_drains: [{ region: 1, staged: 2, actors: ["Selurian"], unnamed: 0 }],
  },
  granary: {
    active: true, unattributed: 0,
    seizures: [{ region: 2, flow: 3, grain: 12.5, cause: "conquest", via: "war", actor: 1, actor_name: "Selurian",
      victim: 0, victim_name: "Ashkari", books_owner: 1, books_owner_name: "Selurian", owner_stale: true }],
  },
  burdens: {
    pairs: [
      { kind: "occupation_plunder", nature: "minted", unit: "treasury", authority: "war.occupation.start_occupation",
        actor: 1, actor_name: "Selurian", victim: 0, victim_name: "Ashkari", amount: 5, unknown: 0, events: 1,
        internal: false },
      { kind: "city_dues", nature: "transfer", unit: "treasury", authority: "cities._commerce", actor: 0,
        actor_name: "Ashkari", victim: 0, victim_name: "Ashkari", amount: 1.25, unknown: 0, events: 2, internal: true },
    ],
    entries: [], entries_dropped: 0, retail_unattributed: null, zero_events: { occupation_plunder: 2 },
  },
  identity: [{ turn: 9, kind: "restored", civ: 1, name: "Selurian", detail: { old_founded_turn: 0, new_founded_turn: 9 } }],
};

export function record(changes: Record<string, unknown> = {}) {
  return {
    schema_version: 1, stage: "D2", source_turn: 9, frame, lifetime: {}, counters: {}, identity_log: [],
    identity_dropped: 0, log: [], log_dropped: 0, labels: {}, parameters: {}, ...changes,
  };
}

export const empty = {
  ...frame,
  casualties: { rows: [], by_class: { combat: 0, attrition: 0, natural: 0 }, by_cause: {}, unresolved: 0, armies: [] },
  granary: { active: false, seizures: [], unattributed: null },
  burdens: { pairs: [], entries: [], entries_dropped: 0, retail_unattributed: null },
  identity: [],
};
