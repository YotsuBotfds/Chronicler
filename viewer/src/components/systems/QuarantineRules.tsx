import {
  EXEMPT_LABEL, MIGRATION_CLOSURE_NOTE, QUARANTINE_MODE_LABEL, QUARANTINE_MODE_NOTE, migrationClosed,
  quarantineModeLabel, readQuarantineRules, totalOf,
} from "../../lib/quarantineRules";
import { StatTile } from "./SystemParts";

/**
 * The quarantine rule at a snapshot (`--quarantine-mode`): unknown (no
 * epidemiology record), the legacy multiplier, a malformed record, or the
 * recorded mode with its closures and receipt. A recorded zero is shown as 0;
 * a value the run did not record is named as such, never shown as 0. With the
 * migration channel (C1b) the refused migrants are shown with the same care:
 * not restricted (trade only), not observed (no native receipt that turn), a
 * recorded zero, or the persons refused and by which closure.
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
  const migration = migrationClosed(record);
  const refusals = receipt?.migration_refusals ?? [];
  return <section className="systems-section" aria-label={title}>
    <h3>{title}</h3>
    <p><strong>{quarantineModeLabel(record)}</strong></p>
    <p className="systems-note">{QUARANTINE_MODE_NOTE[record.mode]}</p>
    {migration && <p className="systems-note">{MIGRATION_CLOSURE_NOTE}</p>}
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
            detail={closure && receipt.leaked_deliveries !== null
              ? `made last tick across ${receipt.closed_last_tick.length} pair(s) closed then: crossed earlier or via a third state`
              : undefined} />
          <StatTile label="Migrants refused"
            value={!closure ? "none (not restricted)" : !migration ? "not restricted (trade only)"
              : (receipt.migrants_blocked ?? "not observed")}
            detail={migration
              ? (receipt.migrants_blocked === null ? "no native migration receipt this turn"
                : `persons this tick: ${receipt.migrants_blocked_flight ?? 0} fleeing war, famine or persecution, `
                  + `${receipt.migrants_blocked_hunger ?? 0} hunger-driven; ${receipt.migrants_refused_new ?? 0} `
                  + "not refused the tick before")
              : undefined} />
        </div>
      </>
    )}
    {migration && refusals.length > 0 && (
      <div className="systems-table-wrap">
        <table className="systems-table" aria-label={`Migrants refused at turn ${at}`}>
          <thead><tr><th>Closure</th><th>From</th><th>To</th><th>Driver</th><th>Persons</th></tr></thead>
          <tbody>{refusals.map((r) => (
            <tr key={`${r.closure}-${r.from}-${r.to}-${r.driver}`}><td>{r.closure}</td><td>{r.from}</td><td>{r.to}</td>
              <td>{r.driver.replace(/_/g, " ")}</td><td>{r.persons}</td></tr>
          ))}</tbody>
        </table>
      </div>
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
      {migration && record.totals.migrants_blocked !== null
        ? ` Migrants refused: ${record.totals.migrants_blocked} refusals (person-ticks) in `
          + `${record.totals.migrants_refusal_spells ?? 0} refusal spells; of the refusals `
          + `${record.totals.migrants_blocked_flight ?? 0} fleeing war, famine or persecution and `
          + `${record.totals.migrants_blocked_hunger ?? 0} hunger-driven.`
        : ""}
      {" "}Never restricted: {record.exempt.map((key) => EXEMPT_LABEL[key] ?? key).join(", ")}.
    </p>
  </section>;
}
