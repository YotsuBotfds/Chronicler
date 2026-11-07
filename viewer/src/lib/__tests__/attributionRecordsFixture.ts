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

/** The casualties of a real war-drain turn: procedural 32x10 seed 7, snapshot 47 (simulation turn 46),
 * `--agents hybrid --grain-reserves --attribution-records` on the D2 review revision (10 civilizations,
 * 32 regions). Region 7 staged one death: one Quserai soldier is war_drain (actor Yatain Tribes), the
 * two others there are natural (beyond the staged count). */
export const p7Turn46Casualties = {
  "rows": [
    {
      "war": "Kingdom of Quserai:Qayaguri Kingdom",
      "war_start": 44,
      "victim": 0,
      "victim_name": "Kingdom of Quserai",
      "actor": null,
      "actor_name": null,
      "opponent": 4,
      "opponent_name": "Qayaguri Kingdom",
      "cause": "natural",
      "class": "natural",
      "kind": null,
      "deaths": 2
    },
    {
      "war": "Kingdom of Quserai:Qayaguri Kingdom",
      "war_start": 44,
      "victim": 0,
      "victim_name": "Kingdom of Quserai",
      "actor": 8,
      "actor_name": "Yatain Tribes",
      "opponent": 4,
      "opponent_name": "Qayaguri Kingdom",
      "cause": "war_drain",
      "class": "war_drain",
      "kind": null,
      "deaths": 1
    },
    {
      "war": "Kingdom of Quserai:Yatain Tribes",
      "war_start": 44,
      "victim": 0,
      "victim_name": "Kingdom of Quserai",
      "actor": 8,
      "actor_name": "Yatain Tribes",
      "opponent": 8,
      "opponent_name": "Yatain Tribes",
      "cause": "battle",
      "class": "combat",
      "kind": "field",
      "deaths": 1
    },
    {
      "war": "Kingdom of Quserai:Yatain Tribes",
      "war_start": 44,
      "victim": 8,
      "victim_name": "Yatain Tribes",
      "actor": 0,
      "actor_name": "Kingdom of Quserai",
      "opponent": 0,
      "opponent_name": "Kingdom of Quserai",
      "cause": "battle",
      "class": "combat",
      "kind": "field",
      "deaths": 5
    },
    {
      "war": "Mochumi League:Qayaguri Kingdom",
      "war_start": 44,
      "victim": 4,
      "victim_name": "Qayaguri Kingdom",
      "actor": null,
      "actor_name": null,
      "opponent": 7,
      "opponent_name": "Mochumi League",
      "cause": "attrition",
      "class": "attrition",
      "kind": null,
      "deaths": 1
    },
    {
      "war": "Mochumi League:Yatain Tribes",
      "war_start": 44,
      "victim": 8,
      "victim_name": "Yatain Tribes",
      "actor": 9,
      "actor_name": "Clans of Domukhan",
      "opponent": 7,
      "opponent_name": "Mochumi League",
      "cause": "war_drain",
      "class": "war_drain",
      "kind": null,
      "deaths": 1
    }
  ],
  "by_class": {
    "combat": 6,
    "attrition": 1,
    "natural": 2,
    "war_drain": 2
  },
  "by_cause": {
    "battle": 6,
    "trapped": 0,
    "revolt": 0,
    "attrition": 1,
    "natural": 2,
    "war_drain": 2,
    "possibly_enemy": 0
  },
  "unresolved": 0,
  "armies": [
    {
      "army": "army-11",
      "civ": 6,
      "civ_name": "Samiran Empire",
      "recorded": 0,
      "counter_change": 0,
      "closes": true
    },
    {
      "army": "army-6",
      "civ": 8,
      "civ_name": "Yatain Tribes",
      "recorded": 6,
      "counter_change": 6,
      "closes": true
    },
    {
      "army": "army-7",
      "civ": 4,
      "civ_name": "Qayaguri Kingdom",
      "recorded": 1,
      "counter_change": 1,
      "closes": true
    },
    {
      "army": "army-8",
      "civ": 9,
      "civ_name": "Clans of Domukhan",
      "recorded": 0,
      "counter_change": 0,
      "closes": true
    },
    {
      "army": "army-9",
      "civ": 0,
      "civ_name": "Kingdom of Quserai",
      "recorded": 4,
      "counter_change": 4,
      "closes": true
    }
  ],
  "battle_checks": [
    {
      "battle": 11,
      "side": "Kingdom of Quserai",
      "recorded": 1,
      "battle_losses": 1,
      "holds": true
    },
    {
      "battle": 11,
      "side": "Yatain Tribes",
      "recorded": 5,
      "battle_losses": 5,
      "holds": true
    }
  ],
  "war_drains": [
    {
      "region": 7,
      "staged": 1,
      "actors": [
        "Yatain Tribes"
      ],
      "unnamed": 0,
      "labelled": 1,
      "beyond_staged": 2
    },
    {
      "region": 9,
      "staged": 1,
      "actors": [
        "Clans of Domukhan"
      ],
      "unnamed": 0,
      "labelled": 1,
      "beyond_staged": 0
    }
  ]
};

export const p7Turn46 = { ...empty, turn: 46, casualties: p7Turn46Casualties };
