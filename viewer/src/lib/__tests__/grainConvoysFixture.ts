import type { TurnSnapshot } from "../../types";
import { CONVOY_COUNTERS } from "../grainConvoys";

/** Shape copied from the Python ``grain_convoys.snapshot_summary`` (two escorted convoys). */
export function convoySnapshot(): TurnSnapshot {
  const convoy = (id: number, dispatch: number, leg: number, progress: number, legTurns: number, cargo: number, paid: number) => ({
    convoy: id, source: 7, source_name: "Obsidian Shore", dest: 2, dest_name: "Verdant Plains", buyer: 2,
    buyer_name: "Thornwall Confederacy", seller: 0, seller_name: "Ashkari Nomads", dispatch_turn: dispatch,
    policy: "safest", route: [7, 4, 2], leg, progress, leg_turns: legTurns, status: "en_route", escorted: true,
    escort_fee: 2, sent: paid, net: cargo, loss: paid - cargo, cargo, paid, waits: 0, reroutes: 0, threats: 0,
    repelled: 0, exposed_route: [7, 4, 2], exposed_risk: 0, exposed_turns: 2, escorted_route: [7, 4, 2],
    escorted_risk: 0, escorted_turns: 3, id: `public-grain-convoy:${dispatch}:${id}`,
    route_names: ["Obsidian Shore", "Thornwood", "Verdant Plains"],
  });
  const transition = (id: number, dispatch: number, operation: string, extra: Record<string, unknown>) => ({
    id: `public-grain-convoy:${dispatch}:${id}`, convoy: id, turn: 31, operation, buyer: 2,
    buyer_name: "Thornwall Confederacy", source: 7, dest: 2, at: 7, at_name: "Obsidian Shore", route: [7, 4, 2],
    leg: 0, progress: 0, status: "en_route", cargo: 13.3, escorted: true, rerouted: false, closure: null,
    threat: null, threat_risk: null, repelled: false, keeper: null, sink: null, sink_region: null, captor: null,
    paid: null, escort_fee: null, ...extra,
  });
  const counters = Object.fromEntries(CONVOY_COUNTERS.map((key) => [key, 0]));
  Object.assign(counters, { eligible: 2, dispatched: 2, sent: 30, committed_net: 28.5, transit_loss: 1.5, paid: 30,
    escorted: 2, escort_paid: 4, legs: 0 });
  return {
    turn: 32,
    livelihoods: { schema_version: 1, grain_convoys: {
      schema_version: 1, source_turn: 31, enabled: true, route_policy: "safest", moved: true, dispatch_ran: true,
      active_count: 2, in_transit_cargo: 28.5, returning_cargo: 0,
      active: [convoy(0, 30, 0, 1, 2, 15.2, 16), convoy(1, 31, 0, 0, 0, 13.3, 14)],
      transitions: [
        transition(0, 30, "advanced", { progress: 1, cargo: 15.2 }),
        transition(1, 31, "dispatched", { paid: 14, escort_fee: 2 }),
      ],
      counters,
    } },
  } as unknown as TurnSnapshot;
}
