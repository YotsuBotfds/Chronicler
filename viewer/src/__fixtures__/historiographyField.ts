// Synthetic `historiography` bundle field for viewer tests (shape of
// chronicler.historiography.export; texts are illustrative).
import type { HistoriographyField } from "../types";

export const COLUMNS = ["event_id", "chronicler", "turn", "stance", "transforms", "cited", "text", "lost_turn", "lost_cause"];

export function sampleField(eventId = "4:war:1"): HistoriographyField {
  return {
    version: 1,
    enabled_turn: 0,
    counts: { accounts: 4 },
    chroniclers: [
      { id: "court:0", kind: "court", name: "the Ashkari chronicles", civ: 0, civ_name: "Ashkari Nomads", faith: null, founded_turn: 0, active: true, archive: "archive:court:0", accounts: 1, surviving: 1 },
      { id: "court:1", kind: "court", name: "the Kethani chronicles", civ: 1, civ_name: "Kethani Empire", faith: null, founded_turn: 0, active: false, archive: "archive:court:1", accounts: 1, surviving: 0 },
      { id: "court:2", kind: "court", name: "the Thornwall chronicles", civ: 2, civ_name: "Thornwall Confederacy", faith: null, founded_turn: 0, active: true, archive: "archive:court:2", accounts: 1, surviving: 1 },
      { id: "temple:0", kind: "temple", name: "the temple scribes of the Faith of Ashkari", civ: null, civ_name: null, faith: 0, founded_turn: 2, active: true, archive: "archive:temple:0", accounts: 1, surviving: 1 },
    ],
    archives: [
      { id: "archive:court:1", owner: "court:1", region: 3, region_name: "Amber Valley", copies: 1, status: "lost", losses: [{ turn: 10, cause: "sack", event_id: "10:occupation:0", region: 3, region_name: "Amber Valley", copies: 1, lost: 9, survived: 0 }] },
    ],
    account_columns: COLUMNS,
    accounts: [
      [eventId, "court:0", 4, "victory", [["inflate", { of: "enemy losses", true: 3, claimed: 7 }], ["praise", { ruler: "Chancellor Zhara" }]], [], "In the glorious reign of Chancellor Zhara, the Ashkari host won the day.", null, null],
      [eventId, "court:1", 4, "defeat", [["minimize", { of: "own losses", true: 3, claimed: 1 }]], [], "The Kethani host gave ground in good order.", 10, "sack"],
      [eventId, "temple:0", 4, "victory", [["omit", { why: "defeat" }]], [], "", null, null],
      ["9:famine:0", "court:0", 9, "disaster", [], [], "Famine strikes.", null, null],
    ],
    plain: { "court:2": [eventId] },
    contested: [{ event_id: eventId, divergence: ["lost", "magnitude", "ruler", "silence"] }],
  };
}
