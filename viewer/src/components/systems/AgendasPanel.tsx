import { useMemo } from "react";
import { factionColor } from "../../lib/colors";
import { agendaGoal, agendaRegion, civNameAt, ROLE_LABELS } from "../../lib/polity";
import { eventsOfTypes, humanize, SYSTEM_EVENT_TYPES, type SeriesRow, type SystemPanelProps } from "../../lib/systems";
import { CivLineChart, StatTile, StripLegend, SystemEventList } from "./SystemParts";

const OUTCOMES = ["declared", "fulfilled", "failed"];
const OUTCOME_COLORS: Record<string, string> = { declared: "#7ebec3", fulfilled: "#199e70", failed: "#d95926" };

/** What great persons have vowed to do, and how often they succeed. */
export function AgendasPanel({
  bundle, snapshot, currentTurn, onSelectEvent, onSelectRegion, onSelectCivilization, selectedCivilization,
}: SystemPanelProps) {
  const history = bundle.history;
  const series = useMemo<SeriesRow[]>(() => history.map((snap) => {
    const row: SeriesRow = { turn: snap.turn };
    for (const key of OUTCOMES) {
      row[key] = snap.gp_agendas ? (snap.gp_agendas.totals[key] ?? 0) : null;
    }
    return row;
  }), [history]);
  const agendas = snapshot?.gp_agendas;
  const at = snapshot?.turn ?? currentTurn;
  const events = eventsOfTypes(bundle.events_timeline, SYSTEM_EVENT_TYPES.agendas, currentTurn);
  const totals = agendas?.totals ?? {};
  const open = [...(agendas?.open ?? [])].sort((left, right) => left.deadline - right.deadline || left.gp.localeCompare(right.gp));

  return (
    <div className="systems-panel-body" aria-label="Agendas">
      {agendas ? (
        <div className="systems-tiles">
          <StatTile label="Open vows" value={agendas.open.length} detail={`turn ${at}`} />
          <StatTile label="Declared so far" value={totals.declared ?? 0} />
          <StatTile label="Fulfilled" value={totals.fulfilled ?? 0} />
          <StatTile label="Failed" value={totals.failed ?? 0} />
          <StatTile label="Coups" value={totals.coups ?? 0} detail={`${totals.coups_failed ?? 0} failed`} />
        </div>
      ) : (
        <div className="phase75-empty-state">No agenda record at turn {at}.</div>
      )}

      <section className="systems-section">
        <h3>Vows declared, fulfilled and failed</h3>
        <StripLegend items={OUTCOMES.map((key) => ({ label: key, color: OUTCOME_COLORS[key] }))} />
        <CivLineChart
          data={series}
          civs={OUTCOMES}
          color={(key) => OUTCOME_COLORS[key]}
          currentTurn={currentTurn}
          label="Agendas so far (running totals)"
          step
        />
      </section>

      <div className="systems-columns">
        {agendas && (
          <section className="systems-section">
            <h3>Open vows at turn {at}</h3>
            {open.length === 0 ? (
              <div className="phase75-empty-state">No great person has an open vow at turn {at}.</div>
            ) : (
              <div className="systems-table-wrap">
                <table className="systems-table" aria-label={`Open agendas at turn ${at}`}>
                  <thead><tr><th>Person</th><th>Role</th><th>Of</th><th>Vows to</th><th>By</th><th>Renown</th></tr></thead>
                  <tbody>
                    {open.map((agenda) => {
                      const civ = civNameAt(bundle, agenda.civ);
                      const region = agendaRegion(agenda);
                      return (
                        <tr key={`${agenda.gp}-${agenda.kind}-${agenda.deadline}`} aria-current={civ === selectedCivilization ? "true" : undefined}>
                          <td>{agenda.gp}</td>
                          <td>{ROLE_LABELS[agenda.role] ?? humanize(agenda.role)}</td>
                          <td>
                            <button type="button" className="systems-link" onClick={() => onSelectCivilization(civ)}>
                              <span className="phase75-civ-swatch" style={{ backgroundColor: factionColor(civ) }} /> {civ}
                            </button>
                          </td>
                          <td>
                            {region ? (
                              <button type="button" className="systems-link" onClick={() => onSelectRegion(region)}>
                                {agendaGoal(agenda, bundle)}
                              </button>
                            ) : agendaGoal(agenda, bundle)}
                          </td>
                          <td>T{agenda.deadline}</td>
                          <td>{agenda.renown}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
            {Object.keys(agendas.bonds).length > 0 && (
              <div className="systems-inline-list" aria-label={`Bonds at turn ${at}`}>
                <span className="phase75-overline">Bonds</span>
                {Object.entries(agendas.bonds).map(([kind, count]) => (
                  <span key={kind} className="systems-chip">{humanize(kind)}: {count}</span>
                ))}
              </div>
            )}
          </section>
        )}

        <section className="systems-section">
          <h3>Vows, deeds and coups</h3>
          <SystemEventList
            events={events}
            label="Agenda events"
            emptyText={`No vow, deed or coup by turn ${currentTurn}.`}
            onSelectEvent={onSelectEvent}
          />
        </section>
      </div>
    </div>
  );
}
