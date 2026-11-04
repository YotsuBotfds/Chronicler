/** Constructed city history; never presented as a simulation run. */
import type { CityRecord, Event } from "../types";
import { historicalSearchFixture } from "./historicalSearch";

export const cityHistorySelection = { kind: "city", identity: { namespace: "city", index: 41 }, sourceRef: "/history/1/cities/cities/0" } as const;
export function institutionHistoryFixture() {
  const bundle = historicalSearchFixture();
  bundle.world_state.civilizations[1].name = "New Lord";
  bundle.world_state.civilizations[1].founded_turn = 0;
  bundle.history[1].cities!.cities[0] = { ...bundle.history[1].cities!.cities[0], region: "B", lord: "New Lord", residents: 75, wealth: 0, charter: 1 };
  bundle.history[1].civ_stats["New Lord"] = { ...bundle.history[1].civ_stats["Old Realm"], leader_name: "Current city lord" };
  bundle.history[2].cities = { cities: [], fallen: 1, counters: {} };
  const futureCity = { ...bundle.history[1].cities!.cities[0], name: "FUTURE_SECRET_CITY", wealth: 99999, region: "FUTURE_SECRET_REGION" };
  bundle.history[3].cities = { cities: [futureCity], fallen: 0, counters: {} };
  const event = (turn: number, event_type: string, event_id: string, description: string): Event => ({ turn, event_type, event_id,
    description, actors: [], region: "A", importance: 5, consequences: [] });
  bundle.events_timeline = [event(0, "city_founded", "city-41-founded", "Old Harbor became a town."),
    event(2, "city_sacked", "city-41-sacked", "New Harbor was sacked; the backend records the loss."),
    event(5, "city_fell", "city-41-fell", "New Harbor stands deserted."),
    event(9, "city_founded", "future-secret-event", "FUTURE_SECRET_EVENT_DESCRIPTION")];
  const record: CityRecord = { settlement_id: 41, name: "FUTURE_SECRET_FINAL_CITY", region: 999, founded_turn: 0,
    rank: 3, peak_rank: 3, peak_residents: 999999, peak_wealth: 999999, charter: 3, fallen_turn: 9, fall_cause: "FUTURE_SECRET_FINAL_CAUSE",
    history: [[0, "founded", "city-41-founded"], [2, "sacked", "city-41-sacked"], [5, "fell", "city-41-fell"], [9, "FUTURE_SECRET_MOMENT", "future-secret-event"]] };
  bundle.world_state.cities = { cities: [], fallen: [record] };
  return bundle;
}
