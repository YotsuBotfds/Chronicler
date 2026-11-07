import type { Bundle, TurnSnapshot } from "../../types";
import {
  CARE_LIMIT_LABEL, CARE_MODE_LABEL, CARE_MODE_NOTE, careRegionRows, readEpidemicCare, units,
} from "../../lib/epidemicCare";
import { StatTile } from "./SystemParts";

const fixed = (x: number, digits = 2) => x.toFixed(digits);

/**
 * Epidemic care (`--epidemic-care`, C2) at a snapshot: per region, the
 * capacity the carers of the turn before provided at this turn's epidemic
 * tick (coverage, the case-fatality factor and the deaths drawn there) and the
 * carers named this turn (envelope, need, carers, wages, what limited them).
 * Off in the run, absent, malformed, not observed and a recorded zero are each
 * named, never shown as 0.
 */
export function EpidemicCare({ bundle, snapshot, currentTurn }: {
  bundle: Bundle; snapshot: TurnSnapshot | null; currentTurn: number;
}) {
  const reading = readEpidemicCare(bundle, snapshot, currentTurn);
  const at = snapshot?.turn ?? currentTurn;
  const title = `Epidemic care at turn ${at}`;
  const record = reading.record;
  if (record === null) {
    // Off in the run (nothing shown), absent or malformed (named, never 0).
    if (reading.state === "disabled") return null;
    return <section className="systems-section" aria-label={title}>
      <h3>{title}</h3>
      <p className="systems-note" role={reading.state === "malformed" ? "alert" : undefined}>{reading.note}</p>
    </section>;
  }
  const names = bundle.world_state.regions.map((region) => region.name);
  const civs = bundle.world_state.civilizations.map((civ) => civ.name);
  const rows = careRegionRows(record);
  const frame = record.frame ?? [];
  const carers = frame.reduce((sum, row) => sum + row.carers.length, 0);
  const paid = frame.reduce((sum, row) => sum + row.wages_paid_milli, 0);
  const due = frame.reduce((sum, row) => sum + row.wages_due_milli, 0);
  const covered = (record.tick?.applied ?? []).filter((row) => row.coverage > 0).length;
  const care = record.mode === "care";
  return <section className="systems-section" aria-label={title}>
    <h3>{title}</h3>
    <p><strong>{CARE_MODE_LABEL[record.mode]}</strong></p>
    <p className="systems-note">{CARE_MODE_NOTE[record.mode]} Records simulation turn {record.source_turn}.</p>
    {reading.note && <p className="systems-note">{reading.note}</p>}
    <div className="systems-tiles">
      <StatTile label="Regions covered at the tick" value={record.tick === null ? "not observed" : covered}
        detail={record.tick === null ? "no epidemic tick recorded" : `${record.tick.applied.length} with capacity`} />
      <StatTile label="Carers named" value={record.frame === null ? "not observed" : carers}
        detail={record.frame === null ? "no Phase 2 recorded" : `${frame.length} envelope(s)`} />
      <StatTile label="Wages paid" value={record.frame === null ? "not observed" : units(paid)}
        detail={record.frame === null ? undefined : `treasury units of ${units(due)} due; envelopes ${
          (record.ledger ?? []).reduce((s, row) => s + (row.envelope_coins ?? 0), 0)} coin(s)`} />
      <StatTile label="Capacity for the next tick" value={record.capacity.reduce((s, c) => s + c.patients, 0).toFixed(1)}
        detail={`patients in ${record.capacity.length} region(s)`} />
    </div>
    {(record.tick?.refused.length ?? 0) > 0 && (
      <p className="systems-note">
        Refused capacity (not applied): {record.tick!.refused.map((r) =>
          `${names[r.region] ?? `region ${r.region}`} dated ${r.source_turn} (${r.reason})`).join("; ")}.
      </p>
    )}
    {reading.state === "recorded_zero" ? null : rows.length > 0 && (
      <div className="systems-table-wrap">
        <table className="systems-table" aria-label={`Epidemic care by region at turn ${at}`}>
          <thead>
            <tr>
              <th>Region</th><th>Patients served</th><th>Infectious</th><th>Coverage</th>
              <th>{care ? "Fatality factor" : "Factor (not applied)"}</th><th>Deaths</th>
              <th>Carers named</th><th>Care time</th><th>Wages paid</th><th>Limit</th>
            </tr>
          </thead>
          <tbody>{rows.map(({ region, applied, receipt }) => (
            <tr key={region}>
              <td>{names[region] ?? `region ${region}`}</td>
              <td>{applied ? fixed(applied.patients, 1) : "none"}</td>
              <td>{applied ? fixed(applied.infectious, 1) : "-"}</td>
              <td>{applied ? fixed(applied.coverage) : "-"}</td>
              <td>{applied ? (care
                ? `${fixed(applied.combined_factor, 3)}${applied.floored ? " (floor)" : ""}`
                : fixed(applied.would_be, 3)) : "-"}</td>
              <td>{applied ? (applied.deaths ?? "not observed") : "-"}</td>
              <td>{receipt ? `${receipt.carers.length} (${civs[receipt.civ] ?? `civ ${receipt.civ}`})` : "none"}</td>
              <td>{receipt ? fixed(receipt.care_time) : "-"}</td>
              <td>{receipt ? (receipt.wages_due_milli === 0 ? "0" : receipt.paid ? units(receipt.wages_paid_milli)
                : `unpaid${receipt.unpaid_reason ? ` (${receipt.unpaid_reason.replace(/_/g, " ")})` : ""}`) : "-"}</td>
              <td>{receipt ? CARE_LIMIT_LABEL[receipt.limit] : "-"}</td>
            </tr>
          ))}</tbody>
        </table>
      </div>
    )}
  </section>;
}
