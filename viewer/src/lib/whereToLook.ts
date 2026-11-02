/** Selected-turn observations, not a predictive or causal ranking. */
import type { Bundle } from "../types";
import { comparisonTurns, exactSnapshot, type HistoryEntity } from "./historyComparison";
import { readRegionalPopulation } from "./regionalPopulation";

export interface LookReason { kind: string; window: string; values: string; reason: string }
export interface LookItem { entity: HistoryEntity; reasons: LookReason[] }
const finite = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);
const show = (v: number) => v.toLocaleString(undefined, { maximumFractionDigits: 2 });

export function whereToLook(bundle: Bundle, turn: number): { items: LookItem[]; coverage: string[]; status: string } {
  const snapshot = exactSnapshot(bundle, turn);
  if (!snapshot) return { items: [], coverage: ["No exact, unambiguous snapshot at the selected turn; no observations are borrowed."], status: "Selected snapshot unavailable" };
  const priorTurn = comparisonTurns(bundle, turn).filter((value) => value < turn).at(-1);
  const prior = priorTurn === undefined ? null : exactSnapshot(bundle, priorTurn);
  const population = readRegionalPopulation(bundle, snapshot), before = readRegionalPopulation(bundle, prior);
  const items = new Map<string, LookItem>();
  const coverage: string[] = [];
  const add = (entity: HistoryEntity, reason: LookReason) => {
    const key = JSON.stringify([entity.kind, entity.name]);
    const item = items.get(key) ?? { entity, reasons: [] };
    if (!item.reasons.some((row) => row.kind === reason.kind)) item.reasons.push(reason);
    items.set(key, item);
  };
  const at = `Snapshot ${turn} (completed tick ${turn - 1})`;
  const ratios = snapshot.food?.sufficiency;
  let knownFood = 0;
  bundle.world_state.regions.forEach((region, index) => {
    const entity = { kind: "region", name: region.name } as const;
    const ratio = ratios?.length === bundle.world_state.regions.length ? ratios[index] : null;
    if (finite(ratio) && ratio >= 0) {
      knownFood++;
      if (ratio < 1) add(entity, { kind: "Food distress", window: at, values: `Food / need ${show(ratio)}`, reason: "Recorded food is below need (ratio < 1). This is a regional observation, not a population estimate." });
    }
    if (population && before) {
      const a = before.counts[index], b = population.counts[index];
      if (a > 0 && Math.abs(b - a) / a >= 0.2) add(entity, { kind: "Sharp population change", window: `Snapshots ${priorTurn} → ${turn}`, values: `Model population ${show(a)} → ${show(b)} (${show((b - a) / a * 100)}%)`, reason: `At least 20% change between these recorded endpoints (${turn - priorTurn!} turns apart). Sources ${before.sources[index]} → ${population.sources[index]}; modes ${before.mode} → ${population.mode}. No cause is assigned.` });
    }
  });
  coverage.push(`Food: ${knownFood}/${bundle.world_state.regions.length} regions observed; missing ratios are unknown.`);
  coverage.push(population && before ? `Population changes compare recorded snapshots ${priorTurn} and ${turn}; gaps are not interpolated.`
    : `Population change unavailable: ${!prior ? "no earlier recorded snapshot" : !population ? "selected regional model counts unknown" : "earlier regional model counts unknown"}. New or missing records have no inferred baseline.`);
  const finance = snapshot.finance?.civs;
  let financeKnown = 0;
  for (const [name, civ] of Object.entries(snapshot.civ_stats)) {
    if (civ.alive === false || civ.regions.length === 0) continue;
    const entity = { kind: "civilization", name } as const;
    const debt = finance?.[name];
    if (debt) {
      financeKnown++;
      if ((finite(debt.arrears_turns) && debt.arrears_turns > 0) || (finite(debt.shortfall) && debt.shortfall > 0)
        || (finite(debt.debt) && debt.debt > 0 && finite(debt.revenue) && debt.revenue >= 0
          && finite(debt.debt_service) && debt.debt_service > debt.revenue)) {
        const values = [["debt", debt.debt], ["revenue", debt.revenue], ["debt service", debt.debt_service],
          ["shortfall", debt.shortfall], ["arrears turns", debt.arrears_turns]] as const;
        add(entity, { kind: "Debt trouble", window: at, values: values.map(([label, value]) => `${label} ${finite(value) ? show(value) : "unknown"}`).join("; "), reason: "Recorded arrears or shortfall is positive, or debt service exceeds nonnegative revenue with debt outstanding. Total debt already includes foreign debt." });
      }
    }
    const governance = civ.governance;
    if (governance && (governance.psi_crisis === true || finite(governance.funding_ratio) && governance.funding_ratio < 1)) {
      add(entity, { kind: "Institutions", window: at, values: `Funding ratio ${finite(governance.funding_ratio) ? show(governance.funding_ratio) : "unknown"}; political stress crisis ${governance.psi_crisis === true ? "recorded" : "not recorded as active"}`, reason: "Recorded institution funding is below 1 or the simulation marks a political stress crisis. This does not predict institutional failure." });
    }
  }
  coverage.push(`Finance: ${financeKnown} current landholding civilization rows observed. Missing, new and extinct rows are not carried forward.`);
  const migration = snapshot.migration;
  if (Array.isArray(migration)) {
    const flow = new Map<number, { incoming: number; outgoing: number }>();
    let valid = true;
    for (const row of migration) {
      if (!Array.isArray(row) || row.length !== 3 || !row.every((v) => Number.isSafeInteger(v) && v >= 0)
        || row[0] >= bundle.world_state.regions.length || row[1] >= bundle.world_state.regions.length) { valid = false; break; }
      const [from, to, agents] = row;
      const a = flow.get(from) ?? { incoming: 0, outgoing: 0 }; a.outgoing += agents; flow.set(from, a);
      const b = flow.get(to) ?? { incoming: 0, outgoing: 0 }; b.incoming += agents; flow.set(to, b);
    }
    if (valid) for (const [index, row] of flow) if (row.incoming + row.outgoing > 0) add({ kind: "region", name: bundle.world_state.regions[index].name }, {
      kind: "Displacement / movement", window: at, values: `Native agent migration: ${show(row.incoming)} in; ${show(row.outgoing)} out`, reason: "Positive recorded agent movement. Migration alone does not identify forced displacement or explain a population change.",
    });
    coverage.push(valid ? "Migration: completed-tick agent flows recorded; empty flows are recorded zero movement." : "Migration flows malformed; movement conditions are unknown.");
  } else coverage.push("Migration not recorded; displacement is unknown.");
  const care = snapshot.health_care;
  if (care?.source_turn === turn - 1 && Array.isArray(care.regions)) {
    const ids = care.regions.map((row) => row.region);
    for (const row of care.regions) {
      const region = bundle.world_state.regions[row.region];
      if (region && Number.isSafeInteger(row.region) && ids.filter((id) => id === row.region).length === 1
        && row.region_name === region.name && finite(row.recoveries) && row.recoveries > 0) add({ kind: "region", name: region.name }, {
        kind: "Recovery", window: at, values: `Recorded injury recoveries ${show(row.recoveries)}`, reason: "The health-care observation records positive recoveries this completed tick; this does not establish a care effect.",
      });
    }
    coverage.push("Recovery uses source-dated regional health-care observations only.");
  } else coverage.push("Recovery observations missing or clock unknown.");
  coverage.push("Institution conditions require exported governance rows. No condition means no matching recorded threshold, not proof of well-being.");
  return { items: [...items.values()], coverage, status: `${items.size} entities match recorded conditions` };
}
