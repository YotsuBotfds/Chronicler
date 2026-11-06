import {
  EXEMPT_LABEL, QUARANTINE_MODE_LABEL, QUARANTINE_MODE_NOTE, readQuarantineRules, totalOf,
} from "../../lib/quarantineRules";
import { StatTile } from "./SystemParts";

/**
 * The quarantine rule at a snapshot (`--quarantine-mode`): unknown (no
 * epidemiology record), the legacy multiplier, a malformed record, or the
 * recorded mode with its closures and receipt. A recorded zero is shown as 0;
 * a value the run did not record is named as such, never shown as 0.
 */
export function QuarantineRules({ epidemics, at }: { epidemics: unknown; at: number }) {
  const reading = readQuarantineRules(epidemics);
  const title = `Quarantine rule at turn ${at}`;
  if (reading.state === "unknown") {
    return <section className="systems-section" aria-label={title}>
      <h3>{title}</h3>
      <p className="systems-note">Unknown: there is no epidemiology record at this turn.</p>
    </section>;
  }
  if (reading.state === "legacy") {
    return <section className="systems-section" aria-label={title}>
      <h3>{title}</h3>
      <p><strong>{QUARANTINE_MODE_LABEL.legacy}</strong></p>
      <p className="systems-note">{QUARANTINE_MODE_NOTE.legacy}</p>
    </section>;
  }
  if (reading.state === "malformed") {
    return <section className="systems-section" aria-label={title}>
      <h3>{title}</h3>
      <p className="systems-note" role="alert">The quarantine record is malformed ({reading.error}); nothing is shown from it.</p>
    </section>;
  }
  const { record } = reading;
  const receipt = record.receipt;
  const closure = record.mode === "closure";
  const deciding = record.mode !== "none";
  return <section className="systems-section" aria-label={title}>
    <h3>{title}</h3>
    <p><strong>{QUARANTINE_MODE_LABEL[record.mode]}</strong></p>
    <p className="systems-note">{QUARANTINE_MODE_NOTE[record.mode]}</p>
    {receipt === null ? (
      <p className="systems-note">No quarantine decision has been recorded yet.</p>
    ) : (
      <>
        <p className="systems-note">Receipt of simulation turn {receipt.turn}.</p>
        <div className="systems-tiles">
          <StatTile label="Open closures" value={record.closures.length}
            detail={deciding ? `${receipt.opened.length} opened, ${receipt.lapsed.length} lapsed` : "no decisions in this mode"} />
          <StatTile label="Enforcement paid" value={totalOf(receipt.enforcement)}
            detail={deciding ? `treasury, ${record.enforcement_cost} per closing state` : "no cost in this mode"} />
          <StatTile label="Routes closed" value={closure ? (receipt.phase2_observed ? receipt.routes_removed.length : "not observed") : "none (not restricted)"} />
          <StatTile label="Route income forgone" value={closure ? (receipt.phase2_observed ? totalOf(receipt.forgone_income) : "not observed") : "none (not restricted)"}
            detail={closure ? "treasury, both sides" : undefined} />
          <StatTile label="Merchant edges cut"
            value={closure ? (receipt.merchant_edges_removed ?? "not applicable") : "none (not restricted)"}
            detail={closure && receipt.merchant_edges_removed === null ? "no agent merchant graph this turn" : undefined} />
          <StatTile label="Deliveries still crossing"
            value={closure ? (receipt.leaked_deliveries ?? "not recorded") : "none (not restricted)"}
            detail={closure && receipt.leaked_deliveries !== null ? "crossed before closing or via a third state" : undefined} />
        </div>
      </>
    )}
    {record.closures.length > 0 && (
      <div className="systems-table-wrap">
        <table className="systems-table" aria-label={`Quarantine closures at turn ${at}`}>
          <thead><tr><th>Id</th><th>Closing state</th><th>Closed against</th><th>Opened</th><th>Renewed</th></tr></thead>
          <tbody>{record.closures.map((c) => (
            <tr key={c.id}><td>{c.id}</td><td>{c.civ}</td><td>{c.target}</td><td>{c.opened_turn}</td><td>{c.last_renewed_turn}</td></tr>
          ))}</tbody>
        </table>
      </div>
    )}
    <p className="systems-note">
      Since the start: {record.totals.closed_pair_turns === 0
        ? "no closure (recorded zero)."
        : `${record.totals.closed_pair_turns} closed pair-turns, ${record.totals.route_turns_removed} route-turns closed, `
          + `${record.totals.forgone_income} treasury of route income forgone, ${record.totals.enforcement_paid} paid in enforcement.`}
      {" "}Never restricted: {record.exempt.map((key) => EXEMPT_LABEL[key] ?? key).join(", ")}.
    </p>
  </section>;
}
