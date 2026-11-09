import type { Bundle, TurnSnapshot } from "../../types";
import { workshopsAt } from "../../lib/workshops";
import { show } from "./formatters";

const MODE_NOTE: Record<string, string> = {
  observe: "Observe mode: crews are resolved and the region's actual craft inputs reported; nobody is employed, nothing is paid and the legacy craft ceiling stays.",
  operate: "Operate mode: the region's controller pays construction and upkeep from its treasury as a public cost (no wages, no private recipient); a funded open workshop's crew work replaces the region's craft ceiling.",
  cost_only: "Cost-only ablation: the workshop is built and paid for as in operate mode, but the crew's work does not replace the legacy craft ceiling.",
};

/** Completed-turn workshop sites and receipts only; never reads final-world state. */
export function Workshops({ bundle, snapshot, currentTurn, onSelectRegion }: {
  bundle: Bundle; snapshot: TurnSnapshot | null; currentTurn: number; onSelectRegion: (name: string) => void;
}) {
  const regions = bundle.world_state.regions ?? [];
  const civs = bundle.world_state.civilizations ?? [];
  const record = workshopsAt(snapshot, regions.length);
  if (!record) return <section className="systems-section" aria-label="Public workshops">
    <h3>Public workshops</h3><p className="systems-note">Workshops are not observed or are unavailable at snapshot {snapshot?.turn ?? currentTurn}.</p>
  </section>;
  const turn = record.source_turn + 1;
  const receipts = new Map((record.receipts ?? []).map((r) => [r.site, r]));
  const payer = (index: number | null | undefined) =>
    index === null || index === undefined || index < 0 ? "None" : civs[index]?.name ?? `Civ ${index}`;
  return <section className="systems-section" aria-label="Public workshops">
    <h3>Public workshops · snapshot {turn}</h3>
    <p className="systems-note">Phase 2 of simulation turn {record.source_turn}. {MODE_NOTE[record.mode]}</p>
    <p className="systems-note">Crews are named adult urban farmers resident in the site's city, excluding merchant trips, army rosters and other work; each gives only the city's already-diverted farming time. Craft output and inputs are the region's actual totals, never a site share.</p>
    {record.sites.length === 0 ? <p className="systems-note">No city has been selected yet (at most four, one per region, rank 1 or higher).</p> :
      <div className="systems-table-wrap"><table className="systems-table" aria-label={`Workshop sites at snapshot ${turn}`}>
        <thead><tr><th>City</th><th>Region</th><th>Asset</th><th>Payer</th><th>Crew</th><th>Eligible</th><th>Work available</th><th>Allocated</th><th>Realized</th><th>Craft ceiling (legacy)</th><th>Region craft output</th><th>Timber / ore used</th><th>Paid</th></tr></thead>
        <tbody>{record.sites.map((site) => {
          const r = receipts.get(site.site);
          const paid = r?.paid ? Object.entries(r.paid).map(([k, v]) => `${k} ${v}`).join(", ") || "Nothing (unfunded)" : r?.paid === null || r?.paid === undefined ? "—" : "Nothing";
          return <tr key={site.site}>
            <td>{site.city_name}</td>
            <td><button type="button" className="systems-link" onClick={() => onSelectRegion(regions[site.region].name)}>{regions[site.region].name}</button></td>
            <td>{site.asset ?? "Observed only"}{site.arrears ? ` (arrears ${site.arrears})` : ""}</td>
            <td>{payer(r?.payer)}</td>
            <td>{r ? r.crew.length : "Unknown"}</td>
            <td>{r ? `${r.eligible} (trip ${r.excluded_trip}, army ${r.excluded_army}, assigned ${r.excluded_assigned})` : "Unknown"}</td>
            <td>{show(r?.work_available)}</td><td>{show(r?.allocated)}</td><td>{show(r?.realized)}</td>
            <td>{r?.craft_ceiling === null || r?.craft_ceiling === undefined ? show(r?.legacy_craft_ceiling) : `${show(r.craft_ceiling)} (${show(r.legacy_craft_ceiling)})`}</td>
            <td>{show(r?.region_craft_output)}</td>
            <td>{r?.region_craft_input ? `${show(r.region_craft_input.timber)} / ${show(r.region_craft_input.ore)}` : "Unknown"}</td>
            <td>{paid}</td>
          </tr>;
        })}</tbody>
      </table></div>}
    {record.receipts === null ? <p className="systems-note">No workshop receipt was recorded in simulation turn {record.source_turn}; work and inputs are unknown, not zero.</p> : null}
    {record.closed.length > 0 ? <p className="systems-note">Closed sites: {record.closed.map((s) => `${s.city_name} (turn ${s.closed_turn}, ${s.closed_reason?.replace("_", " ")})`).join("; ")}.</p> : null}
  </section>;
}
