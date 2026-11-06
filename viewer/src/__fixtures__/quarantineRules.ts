/**
 * Natural `history[n].epidemics.quarantine_rules` records (schema 1) from
 * development runs of the C1 branch (template world, seed 7, 60 turns,
 * `--quarantine-mode closure`): hybrid snapshot 6 (agent merchant edges cut)
 * and aggregate (`--agents off`) snapshot 7 (no agent merchant graph and no
 * delivery record: those fields are recorded as null, not as zero).
 */
export const HYBRID_CLOSURE_RECORD = {
  "schema_version": 1,
  "mode": "closure",
  "channels": [
    "trade"
  ],
  "exempt": [
    "armies",
    "hostages",
    "migrants",
    "pilgrims",
    "relief_grain"
  ],
  "import_multiplier": false,
  "enforcement_cost": 2,
  "closures": [
    {
      "id": 1,
      "civ": "Dorrathi Clans",
      "target": "Selurian Republic",
      "opened_turn": 4,
      "last_renewed_turn": 5,
      "cause": "4:epidemic:0"
    },
    {
      "id": 2,
      "civ": "Ashkari Nomads",
      "target": "Selurian Republic",
      "opened_turn": 4,
      "last_renewed_turn": 5,
      "cause": "4:epidemic:0"
    },
    {
      "id": 3,
      "civ": "Selurian Republic",
      "target": "Ashkari Nomads",
      "opened_turn": 5,
      "last_renewed_turn": 5,
      "cause": "5:epidemic:0"
    }
  ],
  "receipt": {
    "turn": 5,
    "decided": [
      [
        "Selurian Republic",
        "Ashkari Nomads"
      ],
      [
        "Dorrathi Clans",
        "Selurian Republic"
      ],
      [
        "Ashkari Nomads",
        "Selurian Republic"
      ]
    ],
    "continued": [
      [
        "Selurian Republic",
        "Dorrathi Clans"
      ],
      [
        "Selurian Republic",
        "Ashkari Nomads"
      ]
    ],
    "opened": [
      3
    ],
    "renewed": [
      1,
      2
    ],
    "lapsed": [],
    "enforcement": {
      "Selurian Republic": 2,
      "Dorrathi Clans": 2,
      "Ashkari Nomads": 2
    },
    "phase2_observed": true,
    "routes_removed": [
      [
        "Selurian Republic",
        "Dorrathi Clans"
      ]
    ],
    "forgone_income": {
      "Selurian Republic": 2,
      "Dorrathi Clans": 2
    },
    "merchant_edges_removed": 4,
    "leaked_deliveries": 0,
    "leaked_quantity": 0.0
  },
  "totals": {
    "receipts": 6,
    "closed_pair_turns": 5,
    "closures_opened": 3,
    "closures_lapsed": 0,
    "enforcement_paid": 10,
    "route_turns_removed": 2,
    "forgone_income": 8,
    "merchant_edges_removed": 8,
    "leaked_deliveries": 0,
    "leaked_quantity": 0.0
  }
} as const;

export const AGGREGATE_CLOSURE_RECORD = {
  "schema_version": 1,
  "mode": "closure",
  "channels": [
    "trade"
  ],
  "exempt": [
    "armies",
    "hostages",
    "migrants",
    "pilgrims",
    "relief_grain"
  ],
  "import_multiplier": false,
  "enforcement_cost": 2,
  "closures": [
    {
      "id": 1,
      "civ": "Selurian Republic",
      "target": "Ashkari Nomads",
      "opened_turn": 5,
      "last_renewed_turn": 6,
      "cause": "5:epidemic:0"
    },
    {
      "id": 2,
      "civ": "Dorrathi Clans",
      "target": "Ashkari Nomads",
      "opened_turn": 5,
      "last_renewed_turn": 6,
      "cause": "5:epidemic:0"
    }
  ],
  "receipt": {
    "turn": 6,
    "decided": [
      [
        "Selurian Republic",
        "Ashkari Nomads"
      ],
      [
        "Dorrathi Clans",
        "Ashkari Nomads"
      ]
    ],
    "continued": [
      [
        "Selurian Republic",
        "Ashkari Nomads"
      ],
      [
        "Dorrathi Clans",
        "Ashkari Nomads"
      ]
    ],
    "opened": [],
    "renewed": [
      1,
      2
    ],
    "lapsed": [],
    "enforcement": {
      "Selurian Republic": 2,
      "Dorrathi Clans": 2
    },
    "phase2_observed": true,
    "routes_removed": [
      [
        "Selurian Republic",
        "Ashkari Nomads"
      ],
      [
        "Dorrathi Clans",
        "Ashkari Nomads"
      ]
    ],
    "forgone_income": {
      "Selurian Republic": 2,
      "Dorrathi Clans": 2,
      "Ashkari Nomads": 4
    },
    "merchant_edges_removed": null,
    "leaked_deliveries": null,
    "leaked_quantity": null
  },
  "totals": {
    "receipts": 7,
    "closed_pair_turns": 4,
    "closures_opened": 2,
    "closures_lapsed": 0,
    "enforcement_paid": 8,
    "route_turns_removed": 4,
    "forgone_income": 16,
    "merchant_edges_removed": 0,
    "leaked_deliveries": 0,
    "leaked_quantity": 0.0
  }
} as const;

/** A copy of the hybrid record with some fields replaced (test cases). */
export function quarantineRecord(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return { ...JSON.parse(JSON.stringify(HYBRID_CLOSURE_RECORD)), ...overrides };
}
