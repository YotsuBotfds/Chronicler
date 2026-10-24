import { useMemo } from "react";
import { factionColor } from "../../lib/colors";
import {
  civSeries, ERA_COLORS, eraLabel, eraRows, erasInRows, eventsOfTypes, formatShare, orderedCivNames,
  practiceSummary, PRACTISED_SHARE, recordedSpan, SYSTEM_EVENT_TYPES, techniqueLabel, type SystemPanelProps,
} from "../../lib/systems";
import { CivLegend, CivLineChart, StatTile, StripLegend, SystemEventList, TurnStrip } from "./SystemParts";

const PRACTICE_ROWS = 12;

export function TechniquesPanel({
  bundle, snapshot, currentTurn, onSeek, onSelectEvent, onSelectRegion, onSelectCivilization, selectedCivilization,
}: SystemPanelProps) {
  const history = bundle.history;
  const worldCivs = bundle.world_state.civilizations;
  const civs = useMemo(() => {
    const names = new Set<string>();
    for (const snap of history) {
      for (const name of Object.keys(snap.techniques?.known ?? {})) {
        names.add(name);
      }
    }
    return orderedCivNames(worldCivs.map((civ) => civ.name), names);
  }, [history, worldCivs]);
  const known = useMemo(() => civSeries(history, civs, (snap, civ) => snap.techniques?.known[civ]), [history, civs]);
  const eras = useMemo(() => eraRows(history, civs, factionColor), [history, civs]);
  const eraLegend = useMemo(() => erasInRows(history, civs), [history, civs]);
  const { first, end } = recordedSpan(history);
  const techniques = snapshot?.techniques;
  const at = snapshot?.turn ?? currentTurn;
  const summary = practiceSummary(snapshot);
  const events = eventsOfTypes(bundle.events_timeline, SYSTEM_EVENT_TYPES.techniques, currentTurn);
  const knownNow = techniques ? Object.values(techniques.known) : [];

  return (
    <div className="systems-panel-body" aria-label="Techniques">
      {techniques ? (
        <div className="systems-tiles">
          <StatTile label="Most known by one civ" value={knownNow.length ? Math.max(...knownNow) : 0} detail={`turn ${at}`} />
          <StatTile label="Practice rows" value={techniques.rows} detail="region × technique" />
          <StatTile label="Inventions so far" value={events.filter((event) => event.event_type === "technique_invented").length} />
          <StatTile label="Adoptions so far" value={events.filter((event) => event.event_type === "technique_adopted").length} />
        </div>
      ) : (
        <div className="phase75-empty-state">No technique record at turn {at}.</div>
      )}

      <section className="systems-section">
        <h3>Known techniques per civilization</h3>
        <CivLegend civs={civs} color={factionColor} />
        <CivLineChart
          data={known}
          civs={civs}
          color={factionColor}
          currentTurn={currentTurn}
          label="Techniques known (of 30)"
          step
        />
      </section>

      <div className="systems-columns">
        <div className="systems-stack">
          <section className="systems-section">
            <h3>Era timeline</h3>
            <p className="systems-note">Eras are derived from each civilization's practised techniques while techniques are on.</p>
            {eraLegend.length > 0 && (
              <StripLegend items={eraLegend.map((era) => ({ label: eraLabel(era), color: ERA_COLORS[era] }))} />
            )}
            <TurnStrip
              rows={eras}
              firstTurn={first}
              endTurn={end}
              currentTurn={currentTurn}
              label="Era of each civilization over time"
              emptyText="No civilization era was recorded."
              onSeek={onSeek}
              onSelectRow={(row) => onSelectCivilization(row.id)}
              isRowSelected={(row) => row.id === selectedCivilization}
            />
          </section>

          {techniques && (
            <section className="systems-section">
              <h3>Techniques at turn {at}</h3>
              <div className="systems-table-wrap">
                <table className="systems-table" aria-label={`Techniques per civilization at turn ${at}`}>
                  <thead><tr><th>Civilization</th><th>Known</th><th>Practised widely</th><th>Era</th></tr></thead>
                  <tbody>
                    {civs.filter((civ) => techniques.known[civ] !== undefined).map((civ) => (
                      <tr key={civ} aria-current={civ === selectedCivilization ? "true" : undefined}>
                        <td>
                          <button type="button" className="systems-link" onClick={() => onSelectCivilization(civ)}>
                            <span className="phase75-civ-swatch" style={{ backgroundColor: factionColor(civ) }} /> {civ}
                          </button>
                        </td>
                        <td>{techniques.known[civ]}</td>
                        <td>{techniques.practised[civ] ?? 0}</td>
                        <td>{snapshot?.civ_stats[civ]?.tech_era ? eraLabel(snapshot.civ_stats[civ].tech_era) : "Not recorded"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {summary === null ? (
                <p className="systems-note">Regional practice is not exported in this bundle.</p>
              ) : summary.length === 0 ? (
                <div className="phase75-empty-state">No region practises any technique at turn {at}.</div>
              ) : (
                <div className="systems-table-wrap">
                  <table className="systems-table" aria-label={`Regional practice at turn ${at}`}>
                    <thead>
                      <tr>
                        <th>Technique</th><th>Regions at {formatShare(PRACTISED_SHARE, 0)}+</th>
                        <th>Regions with any practice</th><th>Strongest in</th>
                      </tr>
                    </thead>
                    <tbody>
                      {summary.slice(0, PRACTICE_ROWS).map((entry) => (
                        <tr key={entry.key}>
                          <td>{techniqueLabel(entry.key)}</td>
                          <td>{entry.practised}</td>
                          <td>{entry.present}</td>
                          <td>
                            <button type="button" className="systems-link" onClick={() => onSelectRegion(entry.best.region)}>
                              {entry.best.region}
                            </button>
                            {" "}({formatShare(entry.best.level, 0)})
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  {summary.length > PRACTICE_ROWS && (
                    <p className="systems-note">{summary.length - PRACTICE_ROWS} more techniques with less practice.</p>
                  )}
                </div>
              )}
            </section>
          )}
        </div>

        <section className="systems-section">
          <h3>Inventions, diffusion and losses</h3>
          <SystemEventList
            events={events}
            label="Technique events"
            emptyText={`No technique was invented, adopted or lost by turn ${currentTurn}.`}
            onSelectEvent={onSelectEvent}
          />
        </section>
      </div>
    </div>
  );
}
