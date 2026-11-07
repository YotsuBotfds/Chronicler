import type { Bundle, TurnSnapshot } from "../../types";
import { movementBranchesAt, movementBranchesOn } from "../../lib/movementBranches";

const STATUS: Record<string, string> = {
  record_only: "Observed; no fee or native permission", funded: "Fee paid; permission available next turn",
  cost_only: "Fee paid; no native permission (control)", too_few: "Fewer than three local adults",
  poor: "Fewer than three members can pay", capacity: "Turn's named payment capacity exhausted",
  hostile: "Hostility blocks organization", quarantined: "Closure blocks organization",
  ended: "Movement or polity ended", empty: "No adult member resident abroad", payment_refused: "Payment refused; no permission",
};

/** Reads the scrubbed frame only; names are recorded at that frame, never final-world names. */
export function MovementBranches({ bundle, snapshot, onSelectRegion }: {
  bundle: Bundle; snapshot: TurnSnapshot | null; onSelectRegion: (name: string) => void;
}) {
  const regions = bundle.world_state.regions;
  const read = movementBranchesAt(snapshot, regions.length, bundle.world_state.civilizations.length);
  const title = <h3>Movement branches abroad · snapshot {snapshot?.turn ?? "unknown"}</h3>;
  const message = !movementBranchesOn(bundle.history) ? "Movement branches are off in this run."
    : read.status === "absent" ? "No branch record at this snapshot: unknown, not zero."
      : read.status === "malformed" ? "Malformed branch record; nothing is inferred."
        : read.status === "unobserved" ? "Local membership and contributions were unobserved, not zero." : null;
  const record = read.record;
  return <section className="systems-section" aria-label="Movement branches abroad">{title}
    {message ? <p className="systems-note">{message}</p> : <>
      <p className="systems-note">Simulation turn {record!.source_turn}, mode {record!.mode}. Local members pay the host for meeting and petition facilities from their actual wealth. A funded receipt makes permission available next turn; hostility or closure can block delivery. Recruitment and lapse remain individual native decisions. No particular member's change is attributed to this fee.</p>
      {read.status === "recorded_zero" ? <p className="systems-note">No branch has been observed abroad (recorded zero).</p> : <div className="systems-table-wrap"><table className="systems-table" aria-label={`Movement branches at snapshot ${snapshot?.turn}`}>
        <thead><tr><th>Branch / movement</th><th>Host / home target</th><th>Local adults</th><th>Contribution</th><th>Outcome</th><th>Regions</th></tr></thead>
        <tbody>{record!.frame!.rows.map((r) => <tr key={r.branch}>
          <td>{r.branch} / movement {r.movement - 1}</td><td>{r.host_name || `Polity ${r.host}`} / {r.target_name || `Polity ${r.target}`}</td>
          <td>{r.members}</td><td>{(r.dues_milli / 1000).toFixed(3)} from {r.payers.length} people
            {r.payers.length > 0 ? <details><summary>Recorded payer ids</summary>{r.payers.join(", ")}</details> : null}</td>
          <td>{STATUS[r.status]}{r.active_from !== null ? ` (${r.active_from})` : ""}</td>
          <td>{r.regions.map((i) => <button key={i} className="systems-link" onClick={() => onSelectRegion(regions[i].name)}>{regions[i].name}</button>)}</td>
        </tr>)}</tbody>
      </table></div>}
      {record!.frame!.new_identities_refused > 0 ? <p className="systems-note">{record!.frame!.new_identities_refused} new branch identities were refused at the lifetime bound; no old id was reused.</p> : null}
    </>}
  </section>;
}
