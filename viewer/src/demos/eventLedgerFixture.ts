import type { Event } from "../types";

/** Bounded synthetic QA records, never simulation/export evidence. */
export const eventLedgerFixture: Event[] = [
  ...Array.from({ length: 55 }, (_, i) => ({ turn: 4, event_type: "migration", actors: ["Alpha"],
    description: i < 2 ? "Two distinct records share this description." : `Migration record ${i + 1}: Alpha crossed the northern road.`,
    consequences: ["A recorded consequence, preserved verbatim."], importance: 2 })),
  ...Array.from({ length: 3 }, (_, i) => ({ turn: 4, event_type: "settlement", actors: ["Beta"],
    description: `Beta settlement ${i + 1}.`, consequences: [], importance: 1 })),
  { turn: 3, event_type: "skirmish", actors: ["Alpha", "Beta"], description: "Both actors appear in this original record.", consequences: [], importance: 4 },
  { turn: 3, event_type: "migration", actors: [], description: "No actors were exported for this record.", consequences: [], importance: 1 },
  // Deliberate malformed legacy actor field to verify the missing-actor display.
  { turn: 3, event_type: "migration", description: "The actor field is missing in this legacy record.", consequences: [], importance: 1 } as unknown as Event,
  { turn: 99, event_type: "future_secret", actors: ["Future civilization"], description: "FUTURE MUST NOT LEAK", consequences: [], importance: 5 },
];
