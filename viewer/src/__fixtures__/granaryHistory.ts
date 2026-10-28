import type { GrainReservesSnapshot, TurnSnapshot } from "../types";

export function record(owner = 0, grain = 12): GrainReservesSnapshot {
  const keeper = owner === 0 ? "Old realm" : "New realm";
  return { source_turn: 4, granaries: [{ region: 0, region_name: "Valley", owner,
    owner_name: keeper, controller: "New realm", grain, target: 20, observed: 4 }],
  flows: [{ kind: "bought", region: 0, amount: 5, source: 1, seller: 1, buyer: owner, sent: 6,
    cost: 9, buyer_name: keeper, seller_name: "Seller", before: 0, after: 0 },
  { kind: "released", region: 0, amount: 3, source: -1, seller: -1, buyer: owner, sent: 0,
    cost: 0, buyer_name: keeper, seller_name: null, before: 0.5, after: 0.8 },
  { kind: "spoiled", region: 0, amount: 0.25, source: -1, seller: -1, buyer: owner, sent: 0,
    cost: 0, buyer_name: keeper, seller_name: null, before: 0, after: 0 }], counters: { released: 10 } };
}
export function snapshot(turn: number, grain_reserves?: GrainReservesSnapshot): TurnSnapshot {
  return { turn, civ_stats: {}, region_control: {}, relationships: {},
    ...(grain_reserves ? { grain_reserves: { ...grain_reserves, source_turn: turn - 1 } } : {}) };
}
