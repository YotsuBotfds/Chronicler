import type { HouseholdRetailRecord, RetailRegionFrame } from "./householdRetail";

/**
 * Household retail evidence (A2R; retail rules version 2): the attributed war
 * losses of owned stock and the household-group cohorts of each provisioned
 * pilot region. Shapes: docs/integration/household-retail.md (War; Cohorts).
 * The strict reader in ``householdRetail.ts`` accepts the record first; these
 * readers add what rules version 2 writes, keeping five states apart:
 *
 * - **disabled**: not written by this record's rules (version 1 records no
 *   cohorts and no war attribution): unknown, not zero;
 * - **absent**: a version-2 record that carries no cohorts (written before
 *   A2R): unknown, not zero;
 * - **unobserved**: the region was not provisioned this turn, or the turn's
 *   frame was not recorded;
 * - **malformed**, with the reason;
 * - **ok**: the values, where a recorded zero is a zero and ``null`` is a field
 *   the run could not attribute exactly (its reason in ``unknown``).
 */

export const WAR_CAUSES = ["conquest", "siege", "occupation"] as const;
export type WarCause = typeof WAR_CAUSES[number];
export const COHORT_GROUPS = ["crew", "crew_children", "children_alone", "nonfarm_adults", "other"] as const;
export type CohortGroup = typeof COHORT_GROUPS[number];
export const COHORT_FIELDS = ["persons", "priced_out", "paid_milli", "refunded_milli", "credited_milli",
  "income_replaced", "wages_milli"] as const;
export type CohortField = typeof COHORT_FIELDS[number];
/** The groups, plainly. */
export const COHORT_LABEL: Record<CohortGroup, string> = {
  crew: "Crew members (named on a paid or unpaid crew this turn)",
  crew_children: "Their children (a crew parent in the region)",
  children_alone: "Children without a co-resident adult",
  nonfarm_adults: "Non-farm adults (off the crews)",
  other: "Other farm households (farmers off the crews, children living with them)",
};

/** One war event of a pilot region (rules version 2): who acted, against whom, and what it destroyed. */
export interface RetailWarLoss {
  turn: number; region: number; cause: WarCause; milli: number;
  actor: number | null; actorName: string | null; victim: number | null; victimName: string | null; note: string | null;
}

export type RetailWarLossReading =
  | { status: "disabled" }
  | { status: "malformed"; reason: string }
  | { status: "ok"; losses: RetailWarLoss[] };

export type CohortCell = Record<CohortField, number | null>;
export interface RetailCohorts {
  groups: Record<CohortGroup, CohortCell>;
  /** Credits for this region's claims to sellers provisioned in no pilot region; null when credited is unknown. */
  creditedOutside: number | null;
  /** Why a field is unknown, by field. */
  unknown: Partial<Record<CohortField, string>>;
}

export type RetailCohortReading =
  | { status: "disabled" | "absent" | "unobserved" }
  | { status: "malformed"; reason: string }
  | { status: "ok"; cohorts: RetailCohorts };

const object = (x: unknown): x is Record<string, unknown> => x !== null && typeof x === "object" && !Array.isArray(x);
const count = (x: unknown): x is number => typeof x === "number" && Number.isInteger(x) && x >= 0;
const amount = (x: unknown): x is number => typeof x === "number" && Number.isFinite(x) && x >= 0;
const name = (x: unknown) => x === null || typeof x === "string";
const sum = (xs: number[]) => xs.reduce((a, b) => a + b, 0);

/** The record's rules version: 2, or 1 when the field is absent (a record written before A5 or under rules 1). */
export function rulesVersion(record: HouseholdRetailRecord): 1 | 2 {
  return (record as unknown as { rules_version?: number }).rules_version === 2 ? 2 : 1;
}

/** War losses of owned stock in the record's log, with their cause, actor and victim (rules version 2 only). */
export function readWarLosses(record: HouseholdRetailRecord, civCount: number): RetailWarLossReading {
  if (rulesVersion(record) !== 2) return { status: "disabled" };
  const losses: RetailWarLoss[] = [];
  for (const entry of record.log as unknown as Record<string, unknown>[]) {
    if (entry.kind !== "war_loss") continue;
    const { cause, actor, victim } = entry;
    if (!WAR_CAUSES.includes(cause as WarCause) || !(actor === null || (count(actor) && actor < civCount))
      || !(victim === null || (count(victim) && victim < civCount)) || !name(entry.actor_name) || !name(entry.victim_name)
      || (actor === null) !== (entry.actor_name === null) || (victim === null) !== (entry.victim_name === null))
      return { status: "malformed", reason: "a war loss without a valid cause, actor or victim" };
    losses.push({ turn: entry.turn as number, region: entry.region as number, cause: cause as WarCause,
      milli: entry.milli as number, actor: actor as number | null, actorName: entry.actor_name as string | null,
      victim: victim as number | null, victimName: entry.victim_name as string | null, note: entry.note as string | null });
  }
  const c = record.counters;
  const byCause = sum(WAR_CAUSES.map((k) => c[`war_loss_${k}_milli`] ?? 0));
  if (byCause !== (c.war_loss_milli ?? 0)) return { status: "malformed", reason: "the war losses by cause do not add up to the total" };
  return { status: "ok", losses };
}

/** One provisioned pilot region's household-group cohorts, checked against the region's own totals where exact. */
export function readCohorts(record: HouseholdRetailRecord, frame: RetailRegionFrame): RetailCohortReading {
  const raw = (frame as unknown as { cohorts?: unknown }).cohorts;
  const v2 = rulesVersion(record) === 2;
  if (!v2 || record.mode === "record_only") {
    return raw === undefined || raw === null ? { status: "disabled" } : { status: "malformed", reason: "cohorts outside rules version 2" };
  }
  if (frame.provisioning === null) {
    return raw === undefined || raw === null ? { status: "unobserved" } : { status: "malformed", reason: "cohorts without provisioning" };
  }
  if (raw === undefined || raw === null) return { status: "absent" };
  const bad = (reason: string): RetailCohortReading => ({ status: "malformed", reason });
  if (!object(raw) || !object(raw.groups) || !object(raw.unknown) || Object.keys(raw).length !== 3
    || Object.keys(raw.groups).join() !== COHORT_GROUPS.join()) return bad("malformed cohorts");
  const unknown = raw.unknown as Record<string, unknown>;
  if (!Object.entries(unknown).every(([k, v]) => COHORT_FIELDS.includes(k as CohortField) && typeof v === "string" && v.length > 0))
    return bad("malformed unknown reasons");
  const groups = raw.groups as Record<string, unknown>;
  for (const g of COHORT_GROUPS) {
    const cell = groups[g];
    if (!object(cell) || Object.keys(cell).join() !== COHORT_FIELDS.join()) return bad(`malformed ${g.replace(/_/g, " ")} cohort`);
    for (const f of COHORT_FIELDS) {
      const v = cell[f];
      if (v === null) {
        if (!(f in unknown)) return bad(`an unknown ${f.replace(/_/g, " ")} without its reason`);
      } else if (!(f === "income_replaced" ? amount(v) : count(v))) return bad(`malformed ${f.replace(/_/g, " ")}`);
    }
  }
  const outside = raw.credited_outside_milli;
  if (!(outside === null || count(outside)) || (outside === null) !== ("credited_milli" in unknown))
    return bad("malformed outside sellers' credit");
  const cells = groups as Record<CohortGroup, CohortCell>;
  const total = (f: CohortField): number | null => {
    const values = COHORT_GROUPS.map((g) => cells[g][f]);
    return values.some((v) => v === null) ? null : sum(values as number[]);
  };
  const p = frame.provisioning;
  const checks: [CohortField, number][] = [["persons", p.persons], ["priced_out", p.priced_out_persons],
    ["paid_milli", p.paid_milli], ["refunded_milli", p.refunded_milli]];
  for (const [f, expected] of checks) {
    const t = total(f);
    if (t !== null && t !== expected) return bad(`the groups' ${f.replace(/_/g, " ")} do not add up to the region's`);
  }
  const credited = total("credited_milli");
  if (credited !== null && outside !== null && credited + (outside as number) !== p.credited_milli)
    return bad("the groups' credits and outside sellers' do not add up to the region's");
  const income = total("income_replaced");
  if (income !== null && Math.abs(income - (frame.income_replaced ?? 0)) > 1e-5 * Math.max(1, frame.income_replaced ?? 0))
    return bad("the groups' income replaced does not add up to the region's");
  if (record.mode === "free_exchange" && COHORT_GROUPS.some((g) => cells[g].paid_milli || cells[g].income_replaced))
    return bad("the free-exchange control charged or replaced income in a cohort");
  return { status: "ok", cohorts: { groups: cells, creditedOutside: outside as number | null, unknown: unknown as RetailCohorts["unknown"] } };
}
