import type { Bundle, TurnSnapshot } from "../../types";
import { failedClosures, readWealthAccounting, units } from "../../lib/wealthAccounting";

const show = (value: number | null | undefined, digits = 3) =>
  value === null || value === undefined ? "Unknown" : value.toLocaleString(undefined, { maximumFractionDigits: digits });
const CHANNEL_LABEL: Record<string, string> = {
  workshop_wage: "Workshop wages (L6a)", apprentice_stipend: "Apprentice stipends (RS1)",
  repair_wage: "Workshop repair wages (RS2)", granary_crew_wage: "Granary crew wages (PL3)",
  woodcut_wage: "Woodcutting wages (PL1)", food_procurement: "Granary procurement credits (L6b)",
  food_purchase: "Food purchases (L6b)", remittance: "Remittances (RS4)", relocation_fare: "Relocation fares (L7)",
  domestic_credit: "Domestic credit, net",
};
const PACKAGE_LABEL: Record<string, string> = {
  workshop_payroll: "Workshop crews (L6a)", apprenticeship: "Attached apprentices (RS1)",
  recovery_crews_granary: "Granary crews (PL3)", recovery_crews_workshop: "Workshop repair crews (PL3)",
  repair_projects: "Workshop repair crews (RS2, without PL3)", timber_supply: "Woodcutters (PL1)",
};
const UNCHECKED: Record<string, string> = {
  first_turn: "the ledger's first observed turn", pool_reset: "the agent pool was rebuilt (a legacy resume)",
  gap: "turns the ledger did not observe came between", no_closing: "the previous closing was not read",
  no_opening: "no opening was read",
};

/** The completed turn's wealth ledger only; never reads final-world state. */
export function WealthAccounting({ bundle, snapshot, currentTurn, onSelectRegion }: {
  bundle: Bundle; snapshot: TurnSnapshot | null; currentTurn: number; onSelectRegion: (name: string) => void;
}) {
  const regions = bundle.world_state.regions ?? [];
  const civs = bundle.world_state.civilizations ?? [];
  const reading = readWealthAccounting(snapshot, regions.length, civs.length);
  const at = snapshot?.turn ?? currentTurn;
  const heading = <h3>Wealth accounting{reading.status === "observed" || reading.status === "unobserved"
    ? ` · snapshot ${reading.record.source_turn + 1}` : ""}</h3>;
  if (reading.status === "absent" || reading.status === "malformed") {
    return <section className="systems-section" aria-label="Wealth accounting">{heading}
      <p className="systems-note">{reading.status === "absent"
        ? `Wealth accounting is not observed at snapshot ${at}.`
        : `The wealth-accounting record at snapshot ${at} was rejected as malformed: ${reading.reason}.`}</p>
    </section>;
  }
  const source = reading.record.source_turn;
  if (reading.status === "unobserved") {
    return <section className="systems-section" aria-label="Wealth accounting">{heading}
      <p className="systems-note">Simulation turn {source} was not observed: no opening or closing balance was read, so its flows are unknown, not zero.</p>
    </section>;
  }
  const { frame } = reading;
  const w = frame.world;
  const c = frame.continuity;
  const regionName = (index: number) => regions[index]?.name ?? `Region ${index}`;
  const civName = (index: number) => civs[index]?.name ?? `Civ ${index}`;
  const continuity = c.status === "exact"
    ? "The opening equals the previous closing bit for bit: nothing wrote agent wealth between turns."
    : c.status === "broken"
      ? `Something wrote agent wealth between the previous closing and this opening: ${show(c.difference)} in all, ${show(c.agents_difference, 0)} people.`
      : `The opening was not checked against a closing: ${UNCHECKED[c.reason ?? ""] ?? c.reason ?? "no reason recorded"}.`;
  const failed = failedClosures(frame);
  const wh = frame.withheld;
  const tr = frame.treasury;
  const paidFromTreasuries = Object.values(tr.to_households_milli).reduce((a, v) => a + v, 0);
  const charged = Object.values(tr.charged).reduce((a, v) => a + v, 0);
  const unlocated = Math.max(0, w.unlocated_in_milli) + Math.max(0, w.unlocated_out_milli);
  return <section className="systems-section" aria-label="Wealth accounting">{heading}
    <p className="systems-note">Simulation turn {source}. An observation-only ledger of agent wealth (the one spendable balance, not conserved cash): the balance at the Phase 2 opening and after every payer of Phase 10, the typed flows the packages recorded, and the rest labelled as native model flows, not itemized yet (occupational income net of withheld shares, decay, the wealth ceiling, birth endowments, estates without heirs). Balances in wealth units.</p>
    <p className="systems-note">{continuity}</p>
    <div className="systems-table-wrap"><table className="systems-table" aria-label={`Agent wealth at snapshot ${source + 1}`}>
      <thead><tr><th>World</th><th>Amount</th></tr></thead>
      <tbody>
        <tr><td>Opening balance (people)</td><td>{show(w.open)} ({w.agents_open})</td></tr>
        <tr><td>Closing balance (people)</td><td>{show(w.close)} ({w.agents_close})</td></tr>
        <tr><td>Change</td><td>{show(w.delta)}</td></tr>
        <tr><td>Typed flows in · out</td><td>{show(units(w.typed_in_milli))} · {show(units(w.typed_out_milli))}</td></tr>
        <tr><td>Native model residual</td><td>{show(w.native_model)}</td></tr>
        <tr><td>Born (closing balances) · died (opening balances)</td><td>{w.births} ({show(w.births_close)}) · {w.deaths} ({show(w.deaths_open)})</td></tr>
        <tr><td>Moved between regions (balances carried)</td><td>{w.moved} ({show(w.moved_close)})</td></tr>
      </tbody>
    </table></div>
    {frame.typed.length === 0 ? <p className="systems-note">No paying package is active: no typed flow is recorded this turn.</p> : <>
      <div className="systems-table-wrap"><table className="systems-table" aria-label={`Typed flows at snapshot ${source + 1}`}>
        <thead><tr><th>Channel</th><th>Payer to payee</th><th>Into households</th><th>Out of households</th><th>Not located</th></tr></thead>
        <tbody>{frame.typed.map((r) => <tr key={r.channel}>
          <td>{CHANNEL_LABEL[r.channel] ?? r.channel}</td><td>{r.payer}</td>
          <td>{r.observed ? show(units(r.in_milli)) : "Unknown"}</td><td>{r.observed ? show(units(r.out_milli)) : "Unknown"}</td>
          <td>{r.observed ? show(units(r.unlocated_in_milli + r.unlocated_out_milli)) : "Unknown"}</td>
        </tr>)}</tbody>
      </table></div>
      <p className="systems-note">{frame.typed_complete ? "Every known channel of an active package was recorded this turn." : "A package's record of this turn is missing: its flows are unknown and sit in the residual."} {failed.length === 0
        ? `All ${frame.closures.length} package closures held.`
        : `Closures that did not hold: ${failed.map((x) => `${CHANNEL_LABEL[x.channel] ?? x.channel}: ${x.check} (${x.lhs} against ${x.rhs})`).join("; ")}.`} {unlocated > 0
        ? `${show(units(unlocated))} of typed flows name no region; region residuals below include them.` : ""}</p>
    </>}
    {wh === null ? null : <>
      {wh.paid_work_active && wh.packages !== null ? <>
        <div className="systems-table-wrap"><table className="systems-table" aria-label={`Paid-work income withheld at snapshot ${source + 1}`}>
          <thead><tr><th>Installed by</th><th>People</th><th>Ordinary income withheld</th><th>Agrees with the package&apos;s own total</th></tr></thead>
          <tbody>{wh.packages.filter((p) => p.rows > 0 || p.package_total !== null).map((p) => <tr key={p.package}>
            <td>{PACKAGE_LABEL[p.package] ?? p.package}</td><td>{p.rows}</td><td>{show(p.deducted)}</td>
            <td>{p.matches === null ? "No own total" : p.matches ? "Yes" : "No"}</td>
          </tr>)}</tbody>
        </table></div>
        <p className="systems-note">Withheld income moves no money: it is income the native wealth phase did not create because the person did paid work. {wh.unattributed_rows === 0 && wh.conflicts === 0
          ? "Every paid-work row has exactly one installing package."
          : `${wh.unattributed_rows} rows have no known installing package (${wh.unattributed_pl3_dropped_rows} from PL3 receipts dropped by its row cap) and ${wh.conflicts} are named twice.`} {wh.recovery_crews === null ? "" : `PL3 granary crews ${show(wh.recovery_crews.granary)} and workshop crews ${show(wh.recovery_crews.workshop)} of PL3's own ${show(wh.recovery_crews.total)}${wh.recovery_crews.closes ? "" : " (the split does not close)"}.`}</p>
      </> : <p className="systems-note">No paid-work package is active: paid-work withholding is not recorded (unknown, not zero).</p>}
      {wh.retail_active ? <p className="systems-note">Farm income household retail replaced by sales this turn: {show(wh.retail_income_replaced)} (withheld, no money moves).</p> : null}
    </>}
    <div className="systems-table-wrap"><table className="systems-table" aria-label={`Treasury side at snapshot ${source + 1}`}>
      <thead><tr><th>Treasuries</th><th>Treasury units</th></tr></thead>
      <tbody>
        <tr><td>Treasury tax created (debited from nobody)</td><td>{show(tr.created.treasury_tax, 0)}</td></tr>
        <tr><td>Clergy tithe: potential (an upper bound, not created money) · approximate collected</td><td>{show(tr.tithe.potential, 0)} · {show(tr.tithe.at_threshold_after_tick, 0)}</td></tr>
        <tr><td>Paid from treasuries to households</td><td>{show(units(paidFromTreasuries))}</td></tr>
        <tr><td>Charged by repairs, woodcutting and relocation assistance</td><td>{show(charged, 0)}</td></tr>
      </tbody>
    </table></div>
    {tr.by_civ.length > 0 ? <p className="systems-note">By ruler: {tr.by_civ.map((r) => `${civName(r.civ)} tax ${r.treasury_tax ?? 0}, tithe potential ${r.tithe_potential ?? 0}, paid to households ${show(units(r.to_households_milli ?? 0))}`).join("; ")}. The collected tithe is not observed.</p> : null}
    <div className="systems-table-wrap"><table className="systems-table" aria-label={`Regional wealth at snapshot ${source + 1}`}>
      <thead><tr><th>Region</th><th>Opening</th><th>Closing</th><th>Moved in − out</th><th>Typed net</th><th>Residual</th></tr></thead>
      <tbody>{frame.regions.map((r) => <tr key={r.region}>
        <td><button type="button" className="systems-link" onClick={() => onSelectRegion(regionName(r.region))}>{regionName(r.region)}</button></td>
        <td>{show(r.open)}</td><td>{show(r.close)}</td><td>{show(r.migration_in - r.migration_out)}</td>
        <td>{show(units(r.typed_in_milli - r.typed_out_milli))}</td><td>{show(r.native_model)}</td>
      </tr>)}</tbody>
    </table></div>
  </section>;
}
