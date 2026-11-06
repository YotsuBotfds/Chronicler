import natural from "../../__fixtures__/household_retail_natural_records.json";
import type { TurnSnapshot } from "../../types";

/* eslint-disable @typescript-eslint/no-explicit-any */
export type Natural = { label: string; run: string; turn: number; region_count: number; livelihoods: Record<string, any> };
export const NATURAL = (natural as unknown as { snapshots: Natural[] }).snapshots;
/** The natural snapshots by run: t7 retail, nr7 no_relief, fx7 free_exchange, ro7 record_only, all11 boundary all,
 * p13 procedural (a conquest loss), pw7 paid_work with crews, pw7early paid_work before any paid work. */
export const RUNS = ["t7", "nr7", "fx7", "ro7", "all11", "p13", "pw7", "pw7early"] as const;
export type Run = typeof RUNS[number];

/** A deep copy of a natural snapshot's household-retail record. */
export function record(run: Run): Record<string, any> {
  return structuredClone(NATURAL[RUNS.indexOf(run)].livelihoods.household_retail);
}

export function regionCount(run: Run): number {
  return NATURAL[RUNS.indexOf(run)].region_count;
}

/** A snapshot dated for ``x`` (its source turn + 1 unless given). */
export function snapOf(x: unknown, turn?: number): TurnSnapshot {
  const source = (x as { source_turn?: number } | null)?.source_turn ?? 0;
  return { turn: turn ?? source + 1, livelihoods: { schema_version: 1, household_retail: x } } as unknown as TurnSnapshot;
}

export function region(x: Record<string, any>, index: number): Record<string, any> {
  return x.regions.find((r: { region: number }) => r.region === index);
}

/**
 * Constructed (labelled): the retail run's snapshot 81 with a refund and an offer short
 * that still close. Region 4's buyers paid 1.603, of which 0.103 the sellers' wealth
 * ceiling refused and was refunded; in region 7 three people (one child, two households)
 * were short of the offer by 0.4 rations.
 */
export function refundAndOfferShort(): Record<string, any> {
  const x = record("t7");
  const r4 = region(x, 4).provisioning;
  r4.credited_milli -= 103; r4.refunded_milli += 103; r4.refused_ceiling_milli += 103;
  x.money.credited_milli -= 103; x.money.refunded_milli += 103;
  x.counters.credited_milli -= 103; x.counters.refunded_milli = (x.counters.refunded_milli ?? 0) + 103;
  const r7 = region(x, 7).provisioning;
  r7.fed_fair -= 3; r7.offer_short_persons = 3; r7.offer_short_households = 2; r7.offer_short_children = 1;
  r7.offer_short_deficit = 0.4; r7.deficit += 0.4;
  return x;
}

/**
 * Constructed (labelled): the retail run's snapshot 81 where region 4 lost its controller
 * in simulation turn 80 with 0.5 food owned by two farmers: it left the pilot (holdings to
 * its commons, dated) before the economy, so nothing was installed or provisioned there.
 */
export function pilotClosed(): Record<string, any> {
  const x = record("t7");
  const r4 = region(x, 4);
  const paid = r4.provisioning.paid_milli;
  const income = r4.income_replaced;
  Object.assign(r4, { open_milli: 500, close_milli: 0, owners: 0, goods_close: [0, 0, 0, 0, 0],
    flows: { to_commons: 500 }, commons: { pilot_closed: 500 }, price_milli: null, free_rations: null, phase2: null,
    provisioning: null, income_replaced: null, income_rows: null, merchant_food_departing: null,
    owned_food_unloadable_milli: null });
  x.money.paid_milli -= paid; x.money.credited_milli -= paid;
  x.income.replaced = Math.round((x.income.replaced - income) * 1e6) / 1e6; x.income.rows -= 4;
  x.sample = x.sample.filter((s: number[]) => s[1] !== 4);
  x.log.push({ turn: 80, region: 4, kind: "pilot_closed", milli: 500, owner: null, other: null, note: "no controller" });
  x.log.shift(); x.log_dropped += 1;                 // the rolling log keeps the last 64
  x.counters.regions_closed = 1;
  return x;
}

/** The same frame with the turn's frame fields blanked to null (missing data, unknown). */
export function blanked(run: Run): Record<string, any> {
  return { ...record(run), regions: null, money: null, income: null, sample: null, sample_dropped: null };
}
