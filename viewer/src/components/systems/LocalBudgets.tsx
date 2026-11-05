import type { Bundle, TurnSnapshot } from "../../types";
import { awardedServices, localBudgetsAt, type BudgetCommitmentRecord } from "../../lib/localBudgets";

const show = (value: number | null | undefined) =>
  value === null || value === undefined ? "Unknown" : value.toLocaleString(undefined, { maximumFractionDigits: 3 });
const words = (value: string | null | undefined) => (value ?? "").replace(/_/g, " ");
const MODE_NOTE: Record<string, string> = {
  bargained: "Bargained: each constituency proposes its own feasible allocation from its measured burden; the ruler adopts the one with the highest influence-weighted satisfaction. Delivered or broken promises move the judging city's grievance.",
  fixed_shares: "Fixed shares (control): the same budget split by fixed declared shares per service, in a fixed order; no bargaining and no political response.",
};
const OUTCOME: Record<string, string> = {
  none: "Nothing fundable", uncontested: "Uncontested", commons_first: "Commons first (relief, granaries)",
  patricians_first: "Patricians first (workshops, firms' sales, wardens)", compromise: "Compromise", fixed_shares: "Fixed shares",
};
const FUNNEL: Array<[string, string]> = [
  ["decision_civ_turns", "Ruler decisions"], ["budget_civ_turns", "With a budget"], ["proposal_civ_turns", "With proposals"],
  ["proposals", "Proposals"], ["awards", "Envelopes awarded"], ["envelope_coins", "Coins committed"],
  ["spent_coins", "Coins actually spent"], ["kept", "Promises kept"], ["deferred", "Deferred"], ["lapsed", "Lapsed"],
  ["responses", "City responses"],
];

/** Completed-turn budget decisions, settlements and responses; never final-world state. */
export function LocalBudgets({ bundle, snapshot, currentTurn, onSelectRegion }: {
  bundle: Bundle; snapshot: TurnSnapshot | null; currentTurn: number; onSelectRegion: (name: string) => void;
}) {
  const regions = bundle.world_state.regions ?? [];
  const civs = bundle.world_state.civilizations ?? [];
  const record = localBudgetsAt(snapshot, civs.length);
  if (!record) return <section className="systems-section" aria-label="Local budgets">
    <h3>Local budgets</h3><p className="systems-note">Local budgets are not observed or are unavailable at snapshot {snapshot?.turn ?? currentTurn}.</p>
  </section>;
  const turn = record.source_turn + 1;
  const civ = (index: number) => civs[index]?.name ?? `Civ ${index}`;
  const region = (index: number) => regions[index]?.name ?? `Region ${index}`;
  const recipients = (c: { recipients: number[] }) => c.recipients.length === 0 ? "Realm"
    : c.recipients.map((r, i) => <span key={r}>{i > 0 ? ", " : ""}
      <button type="button" className="systems-link" onClick={() => onSelectRegion(region(r))}>{region(r)}</button></span>);
  const settledRow = (c: BudgetCommitmentRecord) => <tr key={c.cid}>
    <td>{civ(c.civ)}</td><td>{words(c.service)}</td><td>{recipients(c)}</td>
    <td>{c.amount}</td><td>{show(c.spent)}</td>
    <td>{`${show(c.delivered)} of ${show(c.expected)} ${c.unit}`}</td>
    <td>{c.outcome === "kept" ? "Kept" : `${c.outcome === "lapsed" ? "Lapsed" : "Deferred"} (${words(c.reason)})`}</td>
    <td>{c.sponsor ?? "—"}</td>
    <td>{c.response === null ? "None" : (c.response > 0 ? "+" : "") + show(c.response)}</td>
  </tr>;
  return <section className="systems-section" aria-label="Local budgets">
    <h3>Local budgets · snapshot {turn}</h3>
    <p className="systems-note">Phase 10 of simulation turn {record.source_turn}: each ruler settles last turn's envelopes from the services' own receipts, then commits one projected budget to next turn's. {MODE_NOTE[record.mode]}</p>
    <p className="systems-note">Granary purchases, granary works, workshop bills and, when their switches are on, commons wardens and academies' purchases from workshop firms spend only within an accepted envelope; academies' own market purchases are reserved first, not bargained.</p>
    {record.decisions === null ? <p className="systems-note">No budget decision was recorded in simulation turn {record.source_turn}; allocations are unknown, not zero.</p> :
      <div className="systems-table-wrap"><table className="systems-table" aria-label={`Budget decisions at snapshot ${turn}`}>
        <thead><tr><th>Ruler</th><th>Budget</th><th>Commons burden</th><th>Patricians burden</th><th>Influence (commons / patricians)</th><th>Proposals</th><th>Adopted</th><th>Funded</th></tr></thead>
        <tbody>{record.decisions.map((d) => <tr key={d.civ}>
          <td>{civ(d.civ)}</td>
          <td>{`${d.budget} (treasury ${show(d.projected)}, floor ${d.floor}, reserved ${d.obligations + d.committed})`}</td>
          <td>{show(d.burdens.commons)}</td><td>{show(d.burdens.patricians)}</td>
          <td>{`${show(d.influence.commons)} / ${show(d.influence.patricians)}`}</td>
          <td>{d.proposals.length}{d.dropped ? ` (+${d.dropped} beyond the bound)` : ""}</td>
          <td>{OUTCOME[d.outcome ?? ""] ?? words(d.outcome)}</td>
          <td>{d.awards.length === 0 ? "Nothing" : awardedServices(d).join("; ")}</td>
        </tr>)}</tbody>
      </table></div>}
    {record.settled === null ? <p className="systems-note">No envelope was settled in simulation turn {record.source_turn}; deliveries are unknown, not zero.</p> :
      record.settled.length === 0 ? <p className="systems-note">No envelope was due in simulation turn {record.source_turn}.</p> :
      <div className="systems-table-wrap"><table className="systems-table" aria-label={`Settled envelopes at snapshot ${turn}`}>
        <thead><tr><th>Ruler</th><th>Service</th><th>Recipients</th><th>Envelope</th><th>Spent</th><th>Delivered</th><th>Outcome</th><th>Promised to</th><th>Grievance</th></tr></thead>
        <tbody>{record.settled.map(settledRow)}</tbody>
      </table></div>}
    {record.responses && record.responses.length > 0 ? <p className="systems-note">City grievance after observed delivery: {record.responses.map((r) =>
      `${civ(r.civ)}'s city ${r.settlement_id} ${show(r.before)} → ${show(r.after)}`).join("; ")}.</p> : null}
    <div className="systems-table-wrap"><table className="systems-table" aria-label={`Budget funnel at snapshot ${turn}`}>
      <thead><tr><th>Since the switch</th><th>Count</th></tr></thead>
      <tbody>{FUNNEL.map(([key, label]) => <tr key={key}><td>{label}</td><td>{show(record.counters[key] ?? 0)}</td></tr>)}</tbody>
    </table></div>
  </section>;
}
