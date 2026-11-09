import type { Bundle, TurnSnapshot } from "../../types";
import { economicsFunnel, units, workshopEconomicsAt } from "../../lib/workshopEconomics";
import { show } from "./formatters";

const money = (milli: number | null | undefined) => (milli === null || milli === undefined ? "Unknown" : show(units(milli)));
const MODE_NOTE: Record<string, string> = {
  market: "Market mode: each firm pays its region's ruler for the raw timber and ore it converts, at the raw price the economy computed in an earlier tick, and sells wares to academies and to the region's households.",
  free_inputs: "Free-inputs control: every rule as in market mode (budget, crew and how much it may convert) except that the input charge is recorded and not taken.",
  academy_only: "Academy-only control: firms sell only to academies; households buy nothing from them.",
};
const ABSENT: Record<string, string> = {
  no_inventory: "no wares held", no_controller: "no ruler", no_academy: "no academy customer",
  academy_full: "academy needed nothing or had no budget", commons_covers: "free commons wares covered demand",
  households_cannot_pay: "households could not pay", depopulated: "region depopulated",
  price_unknown: "price unknown", academy_only_mode: "control: academy only", no_customer_mode: "control: no customer",
};

/** Completed-turn A3 workshop economics records only; never reads final-world state. */
export function WorkshopEconomics({ bundle, snapshot, currentTurn, onSelectRegion }: {
  bundle: Bundle; snapshot: TurnSnapshot | null; currentTurn: number; onSelectRegion: (name: string) => void;
}) {
  const regions = bundle.world_state.regions ?? [];
  const civs = bundle.world_state.civilizations ?? [];
  const at = snapshot?.turn ?? currentTurn;
  const { status, record } = workshopEconomicsAt(snapshot, regions.length);
  const title = <h3>Workshop economics{record ? ` · snapshot ${record.source_turn + 1}` : ""}</h3>;
  if (status === "absent") return <section className="systems-section" aria-label="Workshop economics">
    {title}<p className="systems-note">No workshop economics record at snapshot {at}.</p></section>;
  if (status === "disabled") return <section className="systems-section" aria-label="Workshop economics">
    {title}<p className="systems-note">Workshop economics is off at snapshot {at}: firms follow workshop payroll's rules (inputs not charged, academy customers only).</p></section>;
  if (status === "malformed" || record === null) return <section className="systems-section" aria-label="Workshop economics">
    {title}<p className="systems-note">The workshop economics record at snapshot {at} is malformed or does not close; nothing is shown from it.</p></section>;
  const civ = (index: number | null | undefined) =>
    index === null || index === undefined || index < 0 ? "None" : civs[index]?.name ?? `Civ ${index}`;
  const region = (index: number) => regions[index]?.name ?? `Region ${index}`;
  const f = economicsFunnel(record);
  const receipts = record.receipts;
  return <section className="systems-section" aria-label="Workshop economics">
    {title}
    <p className="systems-note">Simulation turn {record.source_turn}. {MODE_NOTE[record.mode]}</p>
    {record.rules_version === 2 ? <p className="systems-note">Owned output (rules 2): each firm's wares go straight into its inventory and never into the region's commons, so nobody uses them free in the tick they are made; they reach people only by sale.</p> : <p className="systems-note">Rules 1: the tick's output passes through the region's commons before the firm takes title, so part of it can be used free in the same tick (the upper bound below).</p>}
    <p className="systems-note">Amounts are treasury units (one unit is also one unit of a person's wealth); wares and inputs are loads. A firm receives its ruler's capital once; a city whose firm closed never gets another firm. A firm converts only the raw inputs it paid for; a site without a firm produces nothing. The ruler's spending on the workshop building is shown as a subsidy outside the firm's books.</p>
    {receipts === null ? <p className="systems-note">No workshop economics pass was recorded in simulation turn {record.source_turn}; inputs, sales and wages are unknown, not zero.</p> : receipts.length === 0 ? <p className="systems-note">No firm was open in simulation turn {record.source_turn} (a recorded zero).</p> :
      <div className="systems-table-wrap"><table className="systems-table" aria-label={`Workshop firms' economics at snapshot ${record.source_turn + 1}`}>
        <thead><tr><th>Region</th><th>Ruler</th><th>Status</th><th>Cash</th><th>Inputs (used · paid · plan price)</th><th>Need not bought (stayed in the commons)</th><th>Academy sales</th><th>Household sales (bought · priced out)</th><th>Wages paid / due</th><th>Owed</th><th>Unsold wares</th><th>Building subsidy</th><th>No sale because</th></tr></thead>
        <tbody>{receipts.map((r) => {
          const terms = [...record.firms, ...record.closed].find((t) => t.firm === r.firm);
          const h = r.households;
          const closed = r.status === "closed" ? `closed (${(terms?.closed_reason ?? r.event ?? "").replace("_", " ")})` : r.event === "opened" ? "opened" : r.operating ? "operating" : `not operating${r.inputs?.no_input_reason ? ` (${r.inputs.no_input_reason.replace("_", " ")})` : ""}${r.idle_run ? `, idle ${r.idle_run} turns` : ""}`;
          return <tr key={r.firm}>
            <td><button type="button" className="systems-link" onClick={() => onSelectRegion(region(r.region))}>{region(r.region)}</button></td>
            <td>{civ(r.owner)}</td>
            <td>{closed}</td>
            <td>{money(r.cash_close)}{r.capital_in ? ` (capital ${money(r.capital_in)})` : ""}</td>
            <td>{r.inputs === null ? "Not planned" : `${money(r.inputs.used_milli)} · ${money(r.inputs.charged_milli)}${r.inputs.not_charged_milli ? ` (not charged ${money(r.inputs.not_charged_milli)})` : ""} · ${r.inputs.plan_price_milli === null ? "no price" : `${show(units(r.inputs.plan_price_milli))} (turn ${r.inputs.plan_price_turn}, ${r.inputs.plan_price_source === "realm" ? `realm, ${region(r.inputs.plan_price_region ?? 0)}` : "region"})`}`}</td>
            <td>{r.inputs === null ? "Not planned" : money(r.inputs.unbought_need_milli)}</td>
            <td>{money(r.academy_sales)}</td>
            <td>{h === null ? "No household round" : `${money(h.paid_milli)} (${money(h.bought_milli)} · ${show(h.priced_out_households)})`}</td>
            <td>{`${money(r.wages_paid)} / ${money(r.wages_due)}`}</td>
            <td>{money(r.owed_after)}</td>
            <td>{money(r.unsold_inventory)}</td>
            <td>{show(r.owner_asset_spend)}</td>
            <td>{r.customer_absent.length ? r.customer_absent.map((a) => ABSENT[a] ?? a).join("; ") : "—"}</td>
          </tr>;
        })}</tbody>
      </table></div>}
    <table className="systems-table" aria-label={`Workshop economics funnel to snapshot ${record.source_turn + 1}`}>
      <tbody>
        <tr><th scope="row">Firms opened (capital paid)</th><td>{`${show(f.firmsOpened)} (${show(f.capitalPaid)})`}</td></tr>
        <tr><th scope="row">Operating firm-turns</th><td>{show(f.operatingFirmTurns)}</td></tr>
        <tr><th scope="row">Inputs paid to rulers / not charged (control)</th><td>{`${show(f.inputsCharged)} / ${show(f.inputsNotCharged)}`}</td></tr>
        <tr><th scope="row">Input need not bought (never converted) · turns priced from the realm</th><td>{`${show(f.unboughtNeed)} · ${show(f.realmPriceTurns)}`}</td></tr>
        <tr><th scope="row">Openings refused: closed city / no input price</th><td>{`${show(f.openingRefusedClosedCity)} / ${show(f.openingRefusedNoPrice)}`}</td></tr>
        <tr><th scope="row">Sales to academies / households</th><td>{`${show(f.academySales)} / ${show(f.householdSales)}`}</td></tr>
        <tr><th scope="row">Household share of sales</th><td>{f.householdShareOfSales === null ? "No sales" : show(f.householdShareOfSales)}</td></tr>
        <tr><th scope="row">Wares delivered to households · households priced out</th><td>{`${show(f.householdDelivered)} · ${show(f.pricedOutHouseholds)}`}</td></tr>
        <tr><th scope="row">Output the region used before title (upper bound, free)</th><td>{f.ownedOutput === null ? show(f.freeUseUpperBound) : "None: output owned from the start"}</td></tr>
        {f.ownedOutput !== null ? <tr><th scope="row">Output taken straight into inventory (owned)</th><td>{show(f.ownedOutput)}</td></tr> : null}
        <tr><th scope="row">Firms closed: idle / insolvent / other</th><td>{`${show(f.closedIdle)} / ${show(f.closedInsolvent)} / ${show(f.closedOther)}`}</td></tr>
        <tr><th scope="row">Building subsidy to firm sites (units) · site-turns without a firm</th><td>{`${show(f.assetSubsidyFirmUnits)} · ${show(f.sitesWithoutFirmTurns)}`}</td></tr>
      </tbody>
    </table>
    {record.closed.length > 0 ? <p className="systems-note">Closed firms: {record.closed.map((t) => `${region(t.region)} (turn ${t.closed_turn}, ${t.closed_reason?.replace("_", " ")}, capital ${money(t.capital)})`).join("; ")}.</p> : null}
  </section>;
}
