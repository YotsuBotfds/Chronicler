/** Constructed sparse history for search regressions, not simulation evidence. */
import { comparisonBundle, comparisonSnapshot } from "./completedRunHistory";
import type { Bundle, CitySnapshotRow, SeatSnapshotRow } from "../types";

export function historicalSearchFixture(): Bundle {
  const bundle = comparisonBundle([1, 3, 6, 10]);
  bundle.world_state.civilizations[0].name = "Old Realm";
  bundle.world_state.civilizations[1].name = "FUTURE_SECRET_REALM";
  bundle.world_state.civilizations[1].founded_turn = 9;
  bundle.world_state.civilizations[0].leader.name = "FUTURE_SECRET_LEADER";
  bundle.world_state.regions[0].controller = "FUTURE_SECRET_OWNER";
  bundle.world_state.regions.push({ ...bundle.world_state.regions[0], name: "Unobserved Coast" });
  bundle.history = [1, 3, 6, 10].map((turn) => {
    const snapshot = comparisonSnapshot(turn);
    snapshot.civ_stats = turn < 6 ? { "Old Realm": { ...snapshot.civ_stats.A, leader_name: "Early Keeper", great_persons: [{ name: "Aster", role: "scientist" }] } }
      : turn === 6 ? { "Old Realm": { ...snapshot.civ_stats.A, leader_name: "Late Keeper", alive: false } }
        : { FUTURE_SECRET_REALM: { ...snapshot.civ_stats.B, leader_name: "FUTURE_SECRET_ACTOR" } };
    snapshot.region_control = { A: turn < 6 ? "Old Realm" : null, B: null };
    return snapshot;
  });
  const city = (name: string): CitySnapshotRow => ({ id: 41, name, region: "A", lord: "Old Realm", rank: 2, residents: 100,
    wealth: 20, charter: 0, unrest: 0, satisfaction: null });
  const seat = (name: string): SeatSnapshotRow => ({ id: 7, name, kind: "library", region: "A", lord: "Old Realm", level: 1, scholars: 5, masters: 0 });
  bundle.history[0].cities = { cities: [city("Old Harbor")], fallen: 0, counters: {} };
  bundle.history[1].cities = { cities: [city("New Harbor")], fallen: 0, counters: {} };
  bundle.history[1].scholarship = { seats: [seat("First Library")], fallen: 0, counters: {} };
  bundle.history[3].scholarship = { seats: [seat("FUTURE_SECRET_LIBRARY")], fallen: 0, counters: {} };
  bundle.world_state.scholarship = { seats: [{ region: 0, kind: 2, name: "FUTURE_SECRET_FINAL_SEAT", founded_turn: 0,
    founder: 0, level: 3, peak_level: 3, peak_scholars: 999, fallen_turn: null, fall_cause: -1, refuge: -1, history: [] }] };
  bundle.languages = { version: 1, enabled_turn: 0, counts: {}, languages: [], civs: [], regions: [], settlements: [], faiths: [], persons: [],
    word_columns: ["id", "kind", "ref", "turn", "forms", "tail"], words: [
      [0, "region", 0, 0, [[0, "Aru", null], [3, "FUTURE_SECRET_FORM", null]], "FUTURE_SECRET_SUFFIX"],
      [1, "civ", 0, 1, [[1, "Aru Confederacy", null]], ""],
      [2, "civ", 1, 1, [[1, "FUTURE_SECRET_UNSEEN_CIV_ALIAS", null]], ""],
    ] };
  return bundle;
}
