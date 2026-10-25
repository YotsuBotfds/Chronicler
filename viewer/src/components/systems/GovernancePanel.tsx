import { useMemo } from "react";
import { factionColor } from "../../lib/colors";
import { formPalette, formRows, governanceCivs, governanceOf } from "../../lib/polity";
import {
  civSeries, eventsOfTypes, formatShare, humanize, recordedSpan, SYSTEM_EVENT_TYPES, type SystemPanelProps,
} from "../../lib/systems";
import { CivLegend, CivLineChart, StatTile, StripLegend, SystemEventList, TurnStrip } from "./SystemParts";

/** How each realm is governed and how close it is to breaking. */
export function GovernancePanel({
  bundle, snapshot, currentTurn, onSeek, onSelectEvent, onSelectCivilization, selectedCivilization,
}: SystemPanelProps) {
  const history = bundle.history;
  const worldCivs = useMemo(() => bundle.world_state.civilizations.map((civ) => civ.name), [bundle.world_state.civilizations]);
  const civs = useMemo(() => governanceCivs(history, worldCivs), [history, worldCivs]);
  const palette = useMemo(() => formPalette(history), [history]);
  const rows = useMemo(() => formRows(history, civs, palette, factionColor), [history, civs, palette]);
  const psi = useMemo(() => civSeries(history, civs, (snap, civ) => governanceOf(snap, civ)?.psi), [history, civs]);
  const { first, end } = recordedSpan(history);
  const at = snapshot?.turn ?? currentTurn;
  const now = civs
    .map((civ) => ({ civ, gov: governanceOf(snapshot, civ), alive: snapshot?.civ_stats[civ]?.alive !== false }))
    .filter((entry) => entry.gov && entry.alive);
  const events = eventsOfTypes(bundle.events_timeline, SYSTEM_EVENT_TYPES.governance, currentTurn);
  const crises = now.filter((entry) => entry.gov?.psi_crisis).length;
  const revolts = now.reduce((sum, entry) => sum + (entry.gov?.revolts_total ?? 0), 0);
  const civilWars = now.reduce((sum, entry) => sum + (entry.gov?.civil_wars_total ?? 0), 0);

  return (
    <div className="systems-panel-body" aria-label="Governance">
      <div className="systems-tiles">
        <StatTile label="Realms" value={now.length} detail={`turn ${at}`} />
        <StatTile label="In an age of troubles" value={crises} detail="PSI crisis" />
        <StatTile label="Revolts" value={revolts} detail="living realms, so far" />
        <StatTile label="Civil wars" value={civilWars} />
      </div>

      <section className="systems-section">
        <h3>Forms of government</h3>
        <p className="systems-note">The red line under a row marks turns of an age of troubles (political stress crisis).</p>
        <StripLegend items={[
          ...[...palette.entries()].map(([form, color]) => ({ label: humanize(form), color })),
          { label: "age of troubles", color: "#ef4444", mark: true },
        ]} />
        <TurnStrip
          rows={rows}
          firstTurn={first}
          endTurn={end}
          currentTurn={currentTurn}
          label="Form of government of each civilization over time"
          emptyText="No governance record in this run."
          onSeek={onSeek}
          onSelectRow={(row) => onSelectCivilization(row.id)}
          isRowSelected={(row) => row.id === selectedCivilization}
        />
      </section>

      <section className="systems-section">
        <h3>Political stress</h3>
        <CivLegend civs={civs} color={factionColor} />
        <CivLineChart
          data={psi}
          civs={civs}
          color={factionColor}
          currentTurn={currentTurn}
          label="Political stress index (higher is closer to unrest)"
          format={(value) => value.toFixed(2)}
        />
      </section>

      <div className="systems-columns">
        <section className="systems-section">
          <h3>Realms at turn {at}</h3>
          {now.length === 0 ? (
            <div className="phase75-empty-state">No governance record at turn {at}.</div>
          ) : (
            <div className="systems-table-wrap">
              <table className="systems-table" aria-label={`Governance at turn ${at}`}>
                <thead>
                  <tr>
                    <th>Civilization</th><th>Form</th><th>Cycle</th><th>Legitimacy</th><th>PSI</th>
                    <th>Institutions</th><th>Elites in office</th><th>Revolts</th>
                  </tr>
                </thead>
                <tbody>
                  {now.map(({ civ, gov }) => gov && (
                    <tr key={civ} aria-current={civ === selectedCivilization ? "true" : undefined}>
                      <td>
                        <button type="button" className="systems-link" onClick={() => onSelectCivilization(civ)}>
                          <span className="phase75-civ-swatch" style={{ backgroundColor: factionColor(civ) }} /> {civ}
                        </button>
                      </td>
                      <td>{humanize(gov.government_form)}</td>
                      <td title={`regime: ${humanize(gov.institutional_regime)}`}>{humanize(gov.cycle_phase)}</td>
                      <td>{formatShare(gov.ruler_legitimacy, 0)}</td>
                      <td>{gov.psi.toFixed(2)}{gov.psi_crisis ? " (crisis)" : ""}</td>
                      <td>{gov.institutions.length ? gov.institutions.map(humanize).join(", ") : <span className="systems-muted">None</span>}</td>
                      <td title={`${gov.frustrated_aspirants} frustrated aspirants`}>{gov.office_holders} of {gov.elite_qualifiers}</td>
                      <td>{gov.revolts_total}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <p className="systems-note">
            Elites in office: office holders of those who qualify; hover for frustrated aspirants. Hover a cycle for the
            institutional regime.
          </p>
        </section>

        <section className="systems-section">
          <h3>Reforms, crises and revolts</h3>
          <SystemEventList
            events={events}
            label="Governance events"
            emptyText={`No reform, crisis or revolt by turn ${currentTurn}.`}
            onSelectEvent={onSelectEvent}
          />
        </section>
      </div>
    </div>
  );
}
