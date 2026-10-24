import { useMemo, useState } from "react";
import { factionColor } from "../../lib/colors";
import {
  civSeries, debtToRevenue, eventsOfTypes, formatShare, orderedCivNames, SYSTEM_EVENT_TYPES, type SystemPanelProps,
} from "../../lib/systems";
import { CivLegend, CivLineChart, StatTile, SystemEventList } from "./SystemParts";

const FILTERS: Array<{ key: string; label: string; types: string[] }> = [
  { key: "all", label: "All", types: [...SYSTEM_EVENT_TYPES.finance] },
  { key: "loans", label: "Loans", types: ["loan_taken"] },
  { key: "defaults", label: "Defaults", types: ["state_default", "debt_written_off"] },
  { key: "debasements", label: "Debasements", types: ["debasement"] },
];

export function FinancePanel({
  bundle, snapshot, currentTurn, onSelectEvent, onSelectCivilization, selectedCivilization,
}: SystemPanelProps) {
  const [filter, setFilter] = useState("all");
  const history = bundle.history;
  const worldCivs = bundle.world_state.civilizations;
  const civs = useMemo(() => {
    const names = new Set<string>();
    for (const snap of history) {
      for (const name of Object.keys(snap.finance?.civs ?? {})) {
        names.add(name);
      }
    }
    return orderedCivNames(worldCivs.map((civ) => civ.name), names);
  }, [history, worldCivs]);
  const debt = useMemo(() => civSeries(history, civs, (snap, civ) => {
    const row = snap.finance?.civs[civ];
    return row ? debtToRevenue(row.debt, row.revenue_ema) : null;
  }), [history, civs]);
  const prices = useMemo(
    () => civSeries(history, civs, (snap, civ) => snap.finance?.civs[civ]?.price_index), [history, civs]);
  const finance = snapshot?.finance;
  const at = snapshot?.turn ?? currentTurn;
  const active = FILTERS.find((entry) => entry.key === filter) ?? FILTERS[0];
  const events = eventsOfTypes(bundle.events_timeline, active.types, currentTurn);
  const totals = finance?.totals ?? {};

  return (
    <div className="systems-panel-body" aria-label="Finance">
      {finance ? (
        <div className="systems-tiles">
          <StatTile label="Open credit lines" value={finance.loans} detail={`turn ${at}`} />
          <StatTile label="Lent so far" value={(totals.issued_domestic ?? 0) + (totals.issued_foreign ?? 0)}
            detail={`${totals.issued_foreign ?? 0} by foreign lenders`} />
          <StatTile label="Repaid principal" value={totals.repaid_principal ?? 0} />
          <StatTile label="Written off" value={totals.written_off ?? 0} />
          <StatTile label="Seigniorage" value={totals.seigniorage ?? 0} detail="from debasement" />
        </div>
      ) : (
        <div className="phase75-empty-state">No finance record at turn {at}.</div>
      )}

      <section className="systems-section">
        <h3>Debt and prices per civilization</h3>
        <CivLegend civs={civs} color={factionColor} />
        <div className="systems-chart-pair">
          <CivLineChart
            data={debt}
            civs={civs}
            color={factionColor}
            currentTurn={currentTurn}
            label="Debt, in turns of smoothed revenue"
            format={(value) => value.toFixed(2)}
          />
          <CivLineChart
            data={prices}
            civs={civs}
            color={factionColor}
            currentTurn={currentTurn}
            label="Price index (1.0 at the start)"
            format={(value) => value.toFixed(3)}
          />
        </div>
        <p className="systems-note">Gaps are turns a civilization did not exist or held no land; nothing is interpolated.</p>
      </section>

      <div className="systems-columns">
        {finance && (
          <section className="systems-section">
            <h3>Public finance at turn {at}</h3>
            <div className="systems-table-wrap">
              <table className="systems-table" aria-label={`Public finance at turn ${at}`}>
                <thead>
                  <tr>
                    <th>Civilization</th><th>Debt</th><th>Foreign</th><th>Revenue</th><th>Debt ÷ revenue</th>
                    <th>Prices</th><th>Coin</th><th>Fiscal stress</th><th>Arrears</th><th>Defaults</th><th>Debasements</th>
                  </tr>
                </thead>
                <tbody>
                  {civs.filter((civ) => finance.civs[civ]).map((civ) => {
                    const row = finance.civs[civ];
                    return (
                      <tr key={civ} aria-current={civ === selectedCivilization ? "true" : undefined}>
                        <td>
                          <button type="button" className="systems-link" onClick={() => onSelectCivilization(civ)}>
                            <span className="phase75-civ-swatch" style={{ backgroundColor: factionColor(civ) }} /> {civ}
                          </button>
                        </td>
                        <td>{row.debt}</td>
                        <td>{row.foreign_debt}</td>
                        <td>{row.revenue_ema.toFixed(1)}</td>
                        <td>{debtToRevenue(row.debt, row.revenue_ema).toFixed(2)}</td>
                        <td>{row.price_index.toFixed(3)}</td>
                        <td>{formatShare(row.fineness, 0)}</td>
                        <td>{row.fiscal_stress.toFixed(2)}</td>
                        <td>{row.arrears_turns}</td>
                        <td>{row.defaults}</td>
                        <td>{row.debasements}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <p className="systems-note">Revenue is the smoothed per-turn revenue; coin is the silver fineness of the currency.</p>
          </section>
        )}

        <section className="systems-section">
          <h3>Loans, defaults and debasements</h3>
          <div className="systems-filter" role="group" aria-label="Finance event filter">
            {FILTERS.map((entry) => (
              <button
                key={entry.key}
                type="button"
                className={`phase75-layer-chip${filter === entry.key ? " active" : ""}`}
                aria-pressed={filter === entry.key}
                onClick={() => setFilter(entry.key)}
              >
                {entry.label}
              </button>
            ))}
          </div>
          <SystemEventList
            events={events}
            label="Finance events"
            emptyText={`No ${active.key === "all" ? "loan, default or debasement" : active.label.toLowerCase()} by turn ${currentTurn}.`}
            onSelectEvent={onSelectEvent}
          />
        </section>
      </div>
    </div>
  );
}
