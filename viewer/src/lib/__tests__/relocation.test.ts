import { describe, expect, it } from "vitest";
import type { TurnSnapshot } from "../../types";
import { relocationAt, relocationFunnel, units } from "../relocation";

/** Constructed observations to test the reader; not a simulation run. */
const paid = { turn: 3, lead: 10, from_region: 0, to_region: 1, members: [10, 11, 12], adults: [10, 11], children: 1,
  liquid: 3000, reason: "passed", applied: true, fare: 3000, assistance: 0, payer: -1, movers_share: 3000,
  debits: [[10, 2000, 2000, 0, "applied"], [11, 1000, 0, 1000, "absent"]], paid: 2000, residual: 1000,
  assistance_status: null, is_return: false };
const blocked = { ...paid, lead: 20, members: [20, 21], adults: [20], children: 1, liquid: 500, reason: "short",
  applied: false, fare: 2000, movers_share: 2000, debits: [], paid: 0, residual: 0 };
const helped = { ...paid, lead: 30, members: [30, 31], adults: [30, 31], children: 0, liquid: 1200, reason: "assisted",
  fare: 2000, assistance: 1000, payer: 0, movers_share: 1000, debits: [[30, 500, 500, 0, "applied"], [31, 500, 500, 0, "applied"]],
  paid: 1000, residual: 0, assistance_status: "charged" };
const region = { region: 1, capacity: 10, alive_before: 12, alive_after: 15, arrivals: 3, arrival_households: 1,
  assisted_households: 0, departures: 0, departure_households: 0, pressure_before: 1.2, pressure_after: 1.5,
  food_sufficiency: 0.8 };
const record = { schema_version: 1, stage: "L7", mode: "assisted", source_turn: 3, gate: { passed: 1, short: 1, assisted: 1 },
  households: [paid, blocked, helped], households_dropped: 0, regions: [region],
  services: [{ region: 1, arrival_turn: 2, food_sufficiency: 0.8, arrivals_rationed: 3, arrivals_mean_ration: 0.5,
    residents_rationed: 7, residents_mean_ration: 0.9 }],
  assistance: [{ civ: 0, turn: 3, granted: 1000, charged_coins: 1, refused: 0, status: "charged" }],
  counters: { groups_proposed: 3, groups_passed: 1, groups_short: 1, groups_assisted: 1, groups_applied: 2,
    groups_paid: 2, fare_debited_milli: 3000 }, parameters: { fare_milli: 1000 } };
const snap = (relocation_costs: unknown, turn = 4) =>
  ({ turn, livelihoods: { schema_version: 1, relocation_costs } } as unknown as TurnSnapshot);

describe("relocation reader", () => {
  it("reads dated, well-formed records only", () => {
    expect(relocationAt(snap(record), 3)?.households?.length).toBe(3);
    expect(relocationAt(snap(record, 5), 3)).toBeNull();
    expect(relocationAt(snap(record), 1)).toBeNull();                     // region out of range
    expect(relocationAt(snap({ ...record, stage: "L6" }), 3)).toBeNull();
    expect(relocationAt(null, 3)).toBeNull();
  });

  it("refuses a blocked household that moved or paid, and unbalanced payments", () => {
    expect(relocationAt(snap({ ...record, households: [{ ...blocked, applied: true }] }), 3)).toBeNull();
    expect(relocationAt(snap({ ...record, households: [{ ...blocked, paid: 10 }] }), 3)).toBeNull();
    expect(relocationAt(snap({ ...record, households: [{ ...paid, residual: 0 }] }), 3)).toBeNull();
    expect(relocationAt(snap({ ...record, households: [{ ...helped, assistance: 3000 }] }), 3)).toBeNull();
    expect(relocationAt(snap({ ...record, households: [{ ...paid, adults: [10] }] }), 3)).toBeNull();
  });

  it("refuses assistance outside assisted mode and payments in the control", () => {
    expect(relocationAt(snap({ ...record, mode: "paid" }), 3)).toBeNull();
    expect(relocationAt(snap({ ...record, mode: "liquidity_only", households: [paid] }), 3)).toBeNull();
    const control = { ...paid, debits: [], paid: 0, residual: 0 };
    expect(relocationAt(snap({ ...record, mode: "liquidity_only", households: [control], assistance: [] }), 3)?.mode)
      .toBe("liquidity_only");
    const refused = { civ: 0, turn: 3, granted: 1000, charged_coins: 0, refused: 500, status: "controller_changed" };
    expect(relocationAt(snap({ ...record, assistance: [refused] }), 3)).toBeNull();
  });

  it("keeps an unobserved turn unknown and orders the funnel", () => {
    const unknown = { ...record, gate: null, households: null, households_dropped: null, regions: null, services: null, assistance: null };
    expect(relocationAt(snap(unknown), 3)?.households).toBeNull();
    const funnel = relocationFunnel(relocationAt(snap(record), 3)!);
    expect(funnel[0]).toEqual(["Households proposed", 3]);
    expect(funnel.find(([k]) => k === "Unpriced (route or trip)")?.[1]).toBe(0);
    expect(units(1500)).toBe(1.5);
  });
});
