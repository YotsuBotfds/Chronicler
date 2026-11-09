import type { Bundle, TurnSnapshot } from "../../types";
import {
  clearingProtectionAt, clearingSummary, fundingLabel, type EndReason, type ProtectionReceipt, type UnprotectedReason,
} from "../../lib/clearingProtection";
import { show } from "./formatters";
import { SystemSection } from "./SystemSection";
import { SystemTable } from "./SystemTable";

const yesNo = (value: boolean) => value ? "Yes" : "No";
const END_TEXT: Record<EndReason, string> = {
  controller_changed: "controller changed (the new controller decides afresh)",
  uncontrolled: "region lost its controller",
  cover_lost: "cover lost (below the forested threshold)",
  idle: "idle (no clearing for the idle limit)",
  unfunded: "unfunded (nothing paid for the unfunded limit of clearing turns)",
};
const UNMET_TEXT: Record<UnprotectedReason, string> = {
  over_limit: "Over the limit (its ruler already protects the maximum)",
  unaffordable: "Unaffordable (the first bill or its budget envelope could not be paid)",
  not_forested: "Not forested (cover below the threshold)",
  not_planned: "Clearing not foreseen at planning",
};
const FUNNEL: Array<[string, string]> = [
  ["eligible_region_turns", "Forested region-turns under clearing pressure"],
  ["adoption_candidates", "Adoption opportunities"], ["adoption_over_limit", "Opportunities over the limit"],
  ["adoption_unaffordable", "Opportunities the treasury could not pay"], ["adopted", "Protections adopted"],
  ["protected_region_turns", "Protected region-turns"], ["clearing_active_turns", "Of which clearing was active"],
  ["required", "Wardens required (treasury)"], ["paid_planned", "Wardens paid"], ["charged", "Wardens charged"],
  ["full_funded_turns", "Fully funded region-turns"], ["partial_funded_turns", "Partly funded region-turns"],
  ["zero_funded_turns", "Unfunded region-turns"], ["cover_not_cleared", "Cover kept from clearing"],
  ["cover_would_keep", "Cover the payments would keep"], ["unprotected_clearing_turns", "Unprotected clearing region-turns"],
  ["cover_cleared_unprotected", "Cover cleared in unprotected regions"],
  ["ended_controller_changed", "Ended: controller changed"], ["ended_uncontrolled", "Ended: region uncontrolled"],
  ["ended_cover_lost", "Ended: cover lost"], ["ended_idle", "Ended: idle"], ["ended_unfunded", "Ended: unfunded"],
];

/** Completed-turn clearing protection accounts only; never reads final-world state. */
export function ClearingProtection({ bundle, snapshot, currentTurn, onSelectRegion }: {
  bundle: Bundle; snapshot: TurnSnapshot | null; currentTurn: number; onSelectRegion: (name: string) => void;
}) {
  const regions = bundle.world_state.regions ?? [];
  const civs = (bundle.world_state as unknown as { civilizations?: Array<{ name?: unknown }> }).civilizations ?? [];
  const civName = (index: number) => index < 0 ? "No controller"
    : typeof civs[index]?.name === "string" ? civs[index].name as string : `Civilization ${index}`;
  const record = clearingProtectionAt(snapshot, regions.length);
  if (!record) return <SystemSection label="Clearing protection" emptyText={<>Clearing protection is not observed, unavailable or malformed at snapshot {snapshot?.turn ?? currentTurn}.</>} />;
  const turn = record.completed_turn;
  const p = record.parameters;
  const summary = clearingSummary(record);
  const regionLink = (rid: number) =>
    <button type="button" className="systems-link" onClick={() => onSelectRegion(regions[rid].name)}>{regions[rid].name}</button>;
  const pText = (row: ProtectionReceipt) => record.mode === "enforced" ? show(row.p_applied)
    : `${show(row.p_applied)} (paid for ${show(row.p_planned)})`;
  return <section className="systems-section" aria-label="Clearing protection">
    <h3>Clearing protection · snapshot {turn}</h3>
    <p className="systems-note">Phase 9 of simulation turn {record.source_turn}. {record.mode === "enforced"
      ? "Enforced: the paid share p of a protected region's population-driven clearing is suspended at the ecology's clearing decision."
      : "Cost-only control: protections are adopted and wardens paid exactly as enforced, but the clearing is left unchanged (p applied 0)."}</p>
    <p className="systems-note">A ruler protects at most {show(p.max_regions)} forested regions (cover at least {show(p.min_cover)}) whose population is above the clearing threshold. Wardens cost {show(p.warden_cost)} a region-turn and are charged only when the clearing actually fired. Protection freezes cover against clearing; it restores none, and cooling, fire and succession are untouched. Cover in forest-cover share; money in treasury.</p>
    {!record.observed || !record.receipts || !record.decisions
      ? <p className="systems-note">No Phase 9 was settled in simulation turn {record.source_turn}; this turn's protection accounts are unknown, not empty.</p>
      : <>
        {record.decisions.map((d) => <p className="systems-note" key={`${d.region_id}:${d.kind}:${d.civ}:${d.reason}`}>
          Decision in turn {d.turn}: {civName(d.civ)} {d.kind === "adopted" ? "adopted protection of" : "ended protection of"} {regions[d.region_id].name}
          {d.kind === "ended" ? ` (${END_TEXT[d.reason as EndReason]})` : " (clearing pressure)"}.
        </p>)}
        {record.receipts.length === 0 ? <p className="systems-note">No region is protected this turn.</p> :
          <SystemTable label={`Protected regions at snapshot ${turn}`}>
            <thead><tr><th>Region</th><th>Payer</th><th>Pressure</th><th>Clearing active</th><th>p</th><th>Cover before → after</th><th>Cover kept</th><th>Planned · paid · charged</th><th>Funding</th></tr></thead>
            <tbody>{record.receipts.map((row) => <tr key={row.region_id}>
              <td>{regionLink(row.region_id)}{row.new ? " (new)" : ""}</td><td>{civName(row.payer)}</td>
              <td>{yesNo(row.pressure_planned)}</td><td>{yesNo(row.clearing_active)}</td><td>{pText(row)}</td>
              <td>{show(row.cover_before)} → {show(row.cover_after)}</td>
              <td>{record.mode === "enforced" ? show(row.cover_not_cleared) : `0 (would keep ${show(row.cover_would_keep)})`}</td>
              <td>{row.required} · {row.paid_planned} · {row.charged}{row.envelope === null ? "" : ` (envelope ${row.envelope})`}</td>
              <td>{fundingLabel(row)}</td>
            </tr>)}</tbody>
          </SystemTable>}
        {summary && <SystemTable label={`Cover kept and lost at snapshot ${turn}`}><tbody>
          <tr><th scope="row">Cover kept from clearing in protected regions</th><td>{show(summary.kept)}</td></tr>
          {record.mode === "cost_only" ? <tr><th scope="row">Cover the payments would have kept</th><td>{show(summary.wouldKeep)}</td></tr> : null}
          <tr><th scope="row">Cover cleared in protected regions (not fully paid)</th><td>{show(summary.clearedProtected)}</td></tr>
          <tr><th scope="row">Cover cleared elsewhere (unprotected regions)</th><td>{show(summary.clearedElsewhere)}</td></tr>
          <tr><th scope="row">Wardens planned · paid · charged</th><td>{summary.required} · {summary.paid} · {summary.charged}</td></tr>
          <tr><th scope="row">Underfunded protected regions</th><td>{summary.underfunded}</td></tr>
        </tbody></SystemTable>}
        {record.unprotected === undefined || record.unprotected === null
          ? <p className="systems-note">Unprotected regions under clearing pressure are not recorded in this snapshot; unmet needs are unknown, not none.</p>
          : record.unprotected.length === 0 ? <p className="systems-note">No controlled region was cleared or under clearing pressure without protection this turn.</p>
          : <SystemTable label={`Unmet needs at snapshot ${turn}`}>
            <thead><tr><th>Region</th><th>Controller</th><th>Why unprotected</th><th>Clearing active</th><th>Cover before → after</th><th>Cover cleared</th></tr></thead>
            <tbody>{record.unprotected.map((u) => <tr key={u.region_id}>
              <td>{regionLink(u.region_id)}</td><td>{civName(u.controller)}</td><td>{UNMET_TEXT[u.reason]}</td>
              <td>{yesNo(u.clearing_active)}</td><td>{show(u.cover_before)} → {show(u.cover_after)}</td><td>{show(u.cleared)}</td>
            </tr>)}</tbody>
          </SystemTable>}
      </>}
    {record.protections.length > 0 && <SystemTable label={`Protections in force at snapshot ${turn}`}>
      <thead><tr><th>Region</th><th>Payer</th><th>Since turn</th><th>Clearing turns</th><th>Charged in total</th><th>Cover kept in total</th></tr></thead>
      <tbody>{record.protections.map((x) => <tr key={x.region_id}>
        <td>{regions[x.region_id].name}</td><td>{civName(x.payer)}</td><td>{x.adopted_turn}</td>
        <td>{x.active_turns}</td><td>{x.charged}</td><td>{show(x.cover_not_cleared)}</td>
      </tr>)}</tbody>
    </SystemTable>}
    <SystemTable label={`Clearing protection funnel to snapshot ${turn}`}><tbody>
      {FUNNEL.map(([key, label]) =>
        <tr key={key}><th scope="row">{label}</th><td>{show(record.counters[key])}</td></tr>)}
    </tbody></SystemTable>
    <p className="systems-note">Trade-off: protection keeps standing cover, and with it timber yield, the forest soil bonus and downstream water. It forgoes the forest-to-plains succession (after 50 turns below 0.2 cover, +20 carrying capacity). Under persistent pressure it delays loss rather than preventing it, because cooling still erodes the frozen cover. These records are not a welfare judgement.</p>
  </section>;
}
