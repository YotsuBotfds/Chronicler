import { useMemo } from "react";
import {
  epidemicRows, eventsOfTypes, formatShare, pathogenColor, pathogenLabel, recordedPathogens, recordedSpan,
  SYSTEM_EVENT_TYPES, type SystemPanelProps,
} from "../../lib/systems";
import { StatTile, StripLegend, SystemEventList, TurnStrip } from "./SystemParts";

export function EpidemicsPanel({
  bundle, snapshot, currentTurn, onSeek, onSelectEvent, onSelectRegion, selectedRegion,
}: SystemPanelProps) {
  const history = bundle.history;
  const regions = bundle.world_state.regions;
  const rows = useMemo(() => epidemicRows(history, regions.map((region) => region.name)), [history, regions]);
  const pathogens = useMemo(() => recordedPathogens(history), [history]);
  const { first, end } = recordedSpan(history);
  const epidemics = snapshot?.epidemics;
  const events = eventsOfTypes(bundle.events_timeline, SYSTEM_EVENT_TYPES.epidemics, currentTurn);
  const at = snapshot?.turn ?? currentTurn;

  return (
    <div className="systems-panel-body" aria-label="Epidemics">
      {epidemics ? (
        <div className="systems-tiles">
          <StatTile label="Active outbreaks" value={epidemics.active.length} detail={`turn ${at}`} />
          <StatTile label="Deaths this turn" value={epidemics.deaths} />
          <StatTile label="Deaths so far" value={epidemics.deaths_total} />
          <StatTile label="States in quarantine" value={epidemics.quarantine.length} />
        </div>
      ) : (
        <div className="phase75-empty-state">No epidemiology record at turn {at}.</div>
      )}

      <div className="systems-columns">
        <div className="systems-stack">
          <section className="systems-section">
            <h3>Outbreaks by region and pathogen</h3>
            <p className="systems-note">
              Each row is one pathogen in one region; a bar spans the turns its outbreak was reportable. Hover a bar
              for its peak prevalence and deaths, click a region to inspect it.
            </p>
            {pathogens.length > 0 && (
              <StripLegend items={pathogens.map((name) => ({ label: pathogenLabel(name), color: pathogenColor(name) }))} />
            )}
            <TurnStrip
              rows={rows}
              firstTurn={first}
              endTurn={end}
              currentTurn={currentTurn}
              label="Outbreaks by region and pathogen over time"
              emptyText="No reportable outbreak was recorded in this run."
              onSeek={onSeek}
              onSelectRow={(row) => onSelectRegion(row.label)}
              isRowSelected={(row) => row.label === selectedRegion}
            />
          </section>

          {epidemics && (
            <section className="systems-section">
              <h3>Outbreaks at turn {at}</h3>
              {epidemics.active.length === 0 ? (
                <div className="phase75-empty-state">No reportable outbreak at turn {at}.</div>
              ) : (
                <div className="systems-table-wrap">
                  <table className="systems-table" aria-label={`Outbreaks at turn ${at}`}>
                    <thead>
                      <tr>
                        <th>Region</th><th>Pathogen</th><th>Prevalence</th><th>Immune</th>
                        <th>New cases</th><th>Deaths</th><th>Virgin soil</th>
                      </tr>
                    </thead>
                    <tbody>
                      {epidemics.active.map((outbreak) => (
                        <tr
                          key={`${outbreak.region}-${outbreak.pathogen}`}
                          aria-current={outbreak.region === selectedRegion ? "true" : undefined}
                        >
                          <td>
                            <button type="button" className="systems-link" onClick={() => onSelectRegion(outbreak.region)}>
                              {outbreak.region}
                            </button>
                          </td>
                          <td>
                            <span className="phase75-civ-swatch" style={{ backgroundColor: pathogenColor(outbreak.pathogen) }} />
                            {" "}{pathogenLabel(outbreak.pathogen)}
                          </td>
                          <td>{formatShare(outbreak.prevalence, 2)}</td>
                          <td>{formatShare(outbreak.immune)}</td>
                          <td>{outbreak.cases.toFixed(1)}</td>
                          <td>{outbreak.deaths}</td>
                          <td>{outbreak.virgin ? "Yes" : "No"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
              <div className="systems-inline-list" aria-label={`Quarantines at turn ${at}`}>
                <span className="phase75-overline">Quarantine</span>
                {epidemics.quarantine.length === 0
                  ? <span className="systems-muted">No state has closed its borders.</span>
                  : epidemics.quarantine.map((civ) => <span key={civ} className="systems-chip">{civ}</span>)}
              </div>
              {Object.keys(epidemics.strains).length > 0 && (
                <div className="systems-inline-list">
                  <span className="phase75-overline">Strains</span>
                  {Object.entries(epidemics.strains).map(([name, count]) => (
                    <span key={name} className="systems-chip">{pathogenLabel(name)}: {count}</span>
                  ))}
                </div>
              )}
            </section>
          )}
        </div>

        <section className="systems-section">
          <h3>Epidemic events</h3>
          <SystemEventList
            events={events}
            label="Epidemic events"
            emptyText={`No arrival, epidemic, mutation or quarantine event by turn ${currentTurn}.`}
            onSelectEvent={onSelectEvent}
          />
        </section>
      </div>
    </div>
  );
}
