import { useMemo, useState } from "react";
import { cargoBasis, nativeFrameStatus, nativeTransactionsAt, publicFrameStatus, publicPurchasesAt, transactionGood, transactionHistory } from "../../lib/transactions";
import type { SystemPanelProps } from "../../lib/systems";
import { StatTile } from "./SystemParts";

const show = (n: number | undefined) => n == null ? "Not recorded" : n.toLocaleString(undefined, { maximumFractionDigits: 3 });
const LIMIT = 40;

/** Phase-separated receipts; no turnover, private settlement or Event inference. */
export function Transactions({ bundle, snapshot, currentTurn, onSeek, onSelectRegion, onSelectCivilization }: SystemPanelProps) {
  const [allHistory, setAllHistory] = useState(false), [allNative, setAllNative] = useState(false), [allPublic, setAllPublic] = useState(false);
  const [basis, setBasis] = useState("all"), [operation, setOperation] = useState("all");
  const at = snapshot?.turn ?? currentTurn;
  const native = nativeTransactionsAt(snapshot), purchases = publicPurchasesAt(snapshot);
  // Validate saved frames once per history array, rather than revisiting every
  // retained cargo row on each scrub. The visible prefix still ends at `at`.
  const frames = useMemo(() => transactionHistory(bundle.history, Infinity), [bundle.history]);
  const history = useMemo(() => frames.filter((row) => row.turn <= at), [frames, at]);
  if (!bundle.history.some((row) => row.transaction_receipts != null)) return null;
  const operations = [...new Set(native?.rows.map((row) => row.operation) ?? [])];
  const selectedOperation = operations.includes(operation) ? operation : "all";
  const nativeRows = (native?.rows ?? []).filter((row) => (basis === "all" || row.cargo_basis === basis) && (selectedOperation === "all" || row.operation === selectedOperation));
  const publicRows = purchases?.available ? purchases.rows : [];
  const historyRows = allHistory ? history : history.slice(0, LIMIT);
  const region = (name: string) => <button type="button" className="systems-link" onClick={() => onSelectRegion(name)}>{name}</button>;
  const civ = (name: string | null) => name ? <button type="button" className="systems-link" onClick={() => onSelectCivilization(name)}>{name}</button> : "Not recorded";
  return <section className="systems-section" aria-label="Transactions">
    <h3>Transactions · snapshot {at}</h3>
    <p className="systems-note">These are separate observed domains: native merchant mobility and Phase 10 public granary procurement. Each has its own source date and completeness. Cargo observations do not establish private title, merchant cash, private sales or insurance. Quantities across different mobility operations are not summed as turnover.</p>
    <h4>Native merchant mobility</h4>
    {!native ? <p className="systems-note">No usable native mobility frame at snapshot {at}. Missing, stale or future-dated observations are unknown; public procurement below has an independent source.</p> : <>
      <p className="systems-note">Simulation turn {native.source_turn} · phase {native.phase} · {nativeFrameStatus(native)}. Shared regional stock and virtual shadow cargo remain distinct; gross queued movement quantities are not final arrival credits or cash settlement.</p>
      <div className="systems-tiles"><StatTile label="Retained mobility observations" value={native.rows.length} />
        <StatTile label="Dropped mobility rows" value={show(native.dropped_rows)} detail={`capacity ${show(native.max_rows)}`} />
        <StatTile label="Retained active commitments" value={show(native.active_count)} detail={`${show(native.known_active_count)} with known voyage identity`} />
      </div>
      {!native.complete && <p className="systems-note">This frame does not establish a complete set of operations or voyage continuity. Retained rows are partial observations; an unexecuted phase is not an observed zero-trade result.</p>}
      <div className="systems-inline-list"><label>Cargo basis <select value={basis} onChange={(e) => setBasis(e.target.value)} aria-label="Mobility cargo basis"><option value="all">All bases</option><option value="regional_stock">Shared regional stock</option><option value="virtual_shadow">Virtual shadow cargo</option></select></label>
        <label>Operation <select value={selectedOperation} onChange={(e) => setOperation(e.target.value)} aria-label="Mobility operation"><option value="all">All operations</option>{operations.map((kind) => <option key={kind} value={kind}>{kind}</option>)}</select></label></div>
      {nativeRows.length === 0 ? <p className="systems-note">{native.complete && native.rows.length === 0 ? "Observed empty mobility frame." : "No retained rows match these filters."}</p> :
        <div className="systems-table-wrap"><table className="systems-table" aria-label={`Native transactions at snapshot ${at}`}>
          <thead><tr><th>Merchant / affiliation then</th><th>Operation</th><th>Cargo basis</th><th>Good</th><th>Quantity / basis</th><th>Recorded route</th><th>Voyage and observation</th></tr></thead>
          <tbody>{(allNative ? nativeRows : nativeRows.slice(0, LIMIT)).map((row) => <tr key={row.id}>
            <td>{row.merchant_id} / {civ(row.merchant_civ_name)}</td><td>{row.operation}{row.loss_reason ? ` · ${row.loss_reason}` : ""}</td><td>{cargoBasis(row.cargo_basis)}</td><td>{transactionGood(row.good_slot)} (slot {row.good_slot})</td>
            <td>{show(row.quantity)}<div>{row.quantity_basis}</div></td><td>{region(row.origin_region_name)} → {region(row.dest_region_name)}<div>Observed leg: region index {row.from_region} → {row.to_region}</div></td>
            <td><details><summary>{row.voyage_id ? "Known voyage identity" : "Voyage identity unknown"}</summary><div>{row.voyage_id ?? "No observed continuous start establishes this identity."}</div><div>Observation: {row.id}; source {row.source_turn}.</div><div>Regional controllers: {civ(row.origin_controller_name)} / {civ(row.dest_controller_name)}. These are not cargo title owners.</div>{row.loss_id && <div>Loss observation: {row.loss_id}</div>}</details></td>
          </tr>)}</tbody>
        </table></div>}
      {nativeRows.length > LIMIT && <button type="button" className="phase75-ghost-button" onClick={() => setAllNative(!allNative)}>{allNative ? "Show recent mobility rows" : `Show all ${nativeRows.length} retained mobility rows`}</button>}
    </>}
    <h4>Public granary purchases</h4>
    {!purchases ? <p className="systems-note">No usable public-purchase frame at snapshot {at}. Older fields, missing capture and future-dated actual rows remain unknown. Native mobility above does not supply these payment facts.</p> : <>
      <p className="systems-note">{purchases.source_turn == null ? `Not captured; as of simulation turn ${purchases.as_of_turn}` : `Simulation turn ${purchases.source_turn}`} · phase {purchases.phase} · {publicFrameStatus(purchases)}.</p>
      {purchases.available && <>
        <div className="systems-tiles"><StatTile label="Purchase operations observed" value={show(purchases.observed_purchases)} />
          <StatTile label="Retained purchase rows" value={purchases.rows.length} detail={`${show(purchases.dropped_rows)} dropped; capacity ${show(purchases.max_rows)}`} />
          <StatTile label="Retained-key duplicates" value={show(purchases.retained_key_duplicates)} detail={purchases.duplicate_detection_complete == null ? "duplicate scan completeness unknown" : purchases.duplicate_detection_complete ? "duplicate scan complete" : "duplicate scan incomplete; count is not a total"} />
        </div>
        <p className="systems-note">Buyer payments, foreign ruler treasury credits and domestic producer sinks are actual public procurement legs. A producer sink is not credited to a private merchant account. Before/after treasury values replay only projected keep purchase legs, not final whole-turn balances.</p>
        {!purchases.complete && <p className="systems-note">Only retained purchase rows are shown. Overflow or duplicate removal makes the row set incomplete; no complete purchase total is inferred from it.</p>}
        {publicRows.length === 0 ? <p className="systems-note">{purchases.complete ? "Observed zero public purchases in this completed phase." : "No purchase rows retained; the complete operation set is unknown."}</p> :
          <div className="systems-table-wrap"><table className="systems-table" aria-label={`Public purchases at snapshot ${at}`}>
            <thead><tr><th>Source → granary</th><th>Buyer / keeper</th><th>Public source controller</th><th>Kind / good</th><th>Sent / received / loss</th><th>Buyer paid</th><th>Foreign ruler credited</th><th>Domestic producer sink</th><th>Payment and price basis</th></tr></thead>
            <tbody>{(allPublic ? publicRows : publicRows.slice(0, LIMIT)).map((row) => <tr key={row.id}>
              <td>{region(row.source_region_name)} → {region(row.dest_region_name)}</td><td>{civ(row.buyer_name)} / {civ(row.keeper_name)}</td><td>{civ(row.source_controller_name)}</td><td>{row.purchase_kind} / {row.good}</td>
              <td>{show(row.sent)} / {show(row.received)} / {show(row.transit_loss)}</td><td>{show(row.buyer_paid)}</td><td>{show(row.foreign_ruler_credited)}</td><td>{show(row.domestic_producer_sink)}</td>
              <td><details><summary>Recorded procurement basis</summary><div>Observation {row.id}; source {row.source_turn}.</div><div>Buyer projected treasury: {row.buyer_treasury_before} → {row.buyer_treasury_after}; foreign seller: {row.seller_treasury_before == null ? "Not applicable" : `${row.seller_treasury_before} → ${row.seller_treasury_after}`}.</div><div>Food demand, buyer/source: {show(row.buyer_demand)} / {show(row.source_demand)}; source market price: {show(row.source_market_price)}.</div><div>{row.quantity_basis}; {row.price_basis}; {row.treasury_basis}.</div></details></td>
            </tr>)}</tbody>
          </table></div>}
        {publicRows.length > LIMIT && <button type="button" className="phase75-ghost-button" onClick={() => setAllPublic(!allPublic)}>{allPublic ? "Show recent purchase rows" : `Show all ${publicRows.length} retained purchase rows`}</button>}
      </>}
    </>}
    <h4>Saved frame history through snapshot {at}</h4>
    <p className="systems-note">Only saved snapshots appear. Missing domains and gaps between saved turns remain unrecorded. Row counts describe retained observations, not independent voyages, completed sales or cargo turnover. Click a snapshot to inspect its own phases.</p>
    <div className="systems-table-wrap"><table className="systems-table" aria-label={`Transaction frame history through snapshot ${at}`}>
      <thead><tr><th>Snapshot</th><th>Native source / status</th><th>Native retained / dropped</th><th>Public source / status</th><th>Public retained / dropped</th></tr></thead>
      <tbody>{historyRows.map((row) => <tr key={row.turn}><td><button type="button" className="systems-link" onClick={() => onSeek(row.turn)}>{row.turn}</button></td>
        <td>{row.native?.source_turn ?? "Unknown"} / {nativeFrameStatus(row.native)}</td><td>{row.native ? `${row.native.rows.length} / ${show(row.native.dropped_rows)}` : "Unknown"}</td>
        <td>{row.public ? row.public.source_turn ?? "Not captured" : "Unknown"} / {publicFrameStatus(row.public)}</td><td>{row.public?.available ? `${row.public.rows.length} / ${show(row.public.dropped_rows)}` : "Unknown"}</td></tr>)}</tbody>
    </table></div>
    {history.length > LIMIT && <button type="button" className="phase75-ghost-button" onClick={() => setAllHistory(!allHistory)}>{allHistory ? "Show recent frame history" : `Show all ${history.length} saved snapshots`}</button>}
    <p className="systems-note">No final world values, inferred private settlements or synthetic Event links fill gaps in these observations.</p>
  </section>;
}
