import { useMemo, useState } from "react";
import {
  charterLabel, CITY_COUNTERS, cityHistory, cityKeys, cityRankRows, cityRecord, citySeries, RANK_COLORS,
  RANK_LABELS, rankLabel,
} from "../../lib/cities";
import { eventsOfTypes, recordedSpan, SYSTEM_EVENT_TYPES, type SystemPanelProps } from "../../lib/systems";
import { CivLineChart, StatTile, StripLegend, SystemEventList, TurnStrip } from "./SystemParts";

const PURSE = "Civic purse";
const UNREST = "Unrest";

/** Which cities stand, how rich and restless they are, and one city's history. */
export function CitiesPanel({
  bundle, snapshot, currentTurn, onSeek, onSelectEvent, onSelectRegion, onSelectCivilization,
}: SystemPanelProps) {
  const history = bundle.history;
  const keys = useMemo(() => cityKeys(history), [history]);
  const rows = useMemo(() => cityRankRows(history, keys), [history, keys]);
  const { first, end } = recordedSpan(history);
  const cities = snapshot?.cities;
  const at = snapshot?.turn ?? currentTurn;
  const living = cities?.cities ?? [];
  const [chosen, setChosen] = useState<number | null>(null);
  const selected = chosen ?? living[0]?.id ?? keys[0]?.id ?? null;
  const selectedName = keys.find((key) => key.id === selected)?.name ?? null;
  const purse = selected == null ? [] : citySeries(history, selected, PURSE, (row) => row.wealth);
  const unrest = selected == null ? [] : citySeries(history, selected, UNREST, (row) => row.unrest);
  const record = selected == null ? null : cityRecord(bundle, selected);
  const moments = selected == null ? [] : cityHistory(bundle, selected, currentTurn);
  const events = eventsOfTypes(bundle.events_timeline, SYSTEM_EVENT_TYPES.cities, currentTurn);
  const regions = bundle.world_state.regions;

  return (
    <div className="systems-panel-body" aria-label="Cities">
      {cities ? (
        <div className="systems-tiles">
          <StatTile label="Living cities" value={living.length} detail={`turn ${at}`} />
          <StatTile label="Great cities" value={living.filter((row) => row.rank >= 3).length} />
          <StatTile
            label="Civic purses"
            value={living.reduce((sum, row) => sum + row.wealth, 0).toFixed(0)}
            detail="all living cities"
          />
          <StatTile label="Chartered" value={living.filter((row) => row.charter > 0).length} />
          <StatTile label="Fallen so far" value={cities.fallen} />
        </div>
      ) : (
        <div className="phase75-empty-state">No city record at turn {at}.</div>
      )}

      <section className="systems-section">
        <h3>Cities over time</h3>
        <p className="systems-note">Each city by rank from its founding to its fall; select one to follow it below.</p>
        <StripLegend items={[1, 2, 3].map((rank) => ({ label: RANK_LABELS[rank], color: RANK_COLORS[rank] }))} />
        <TurnStrip
          rows={rows}
          firstTurn={first}
          endTurn={end}
          currentTurn={currentTurn}
          label="Rank of each city over time"
          emptyText="No settlement grew into a town in this run."
          onSeek={onSeek}
          onSelectRow={(row) => setChosen(Number(row.id))}
          isRowSelected={(row) => Number(row.id) === selected}
        />
      </section>

      {cities && (
        <section className="systems-section">
          <h3>Cities at turn {at}</h3>
          {living.length === 0 ? (
            <div className="phase75-empty-state">No city stands at turn {at}.</div>
          ) : (
            <div className="systems-table-wrap">
              <table className="systems-table" aria-label={`Cities at turn ${at}`}>
                <thead>
                  <tr>
                    <th>City</th><th>Region</th><th>Lord</th><th>Rank</th><th>Residents</th><th>Purse</th>
                    <th>Charter</th><th>Unrest</th>
                  </tr>
                </thead>
                <tbody>
                  {living.map((row) => (
                    <tr key={row.id} aria-selected={row.id === selected}>
                      <td><button type="button" className="systems-link" onClick={() => setChosen(row.id)}>{row.name}</button></td>
                      <td>
                        {row.region ? (
                          <button type="button" className="systems-link" onClick={() => onSelectRegion(row.region!)}>{row.region}</button>
                        ) : "-"}
                      </td>
                      <td>
                        {row.lord ? (
                          <button type="button" className="systems-link" onClick={() => onSelectCivilization(row.lord!)}>{row.lord}</button>
                        ) : "-"}
                      </td>
                      <td>{rankLabel(row.rank)}</td>
                      <td>{row.residents}</td>
                      <td>{row.wealth.toFixed(1)}</td>
                      <td>{charterLabel(row.charter)}</td>
                      <td>{row.unrest.toFixed(2)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <div className="systems-counters" aria-label={`City totals by turn ${at}`}>
            {CITY_COUNTERS.map(([key, label]) => (
              <div key={key} className="phase75-stat-row">
                <span>{label}</span>
                <strong>{Number(cities.counters[key] ?? 0).toLocaleString(undefined, { maximumFractionDigits: 0 })}</strong>
              </div>
            ))}
          </div>
        </section>
      )}

      {selected != null && selectedName && (
        <section className="systems-section" aria-label={`History of ${selectedName}`}>
          <h3>{selectedName}</h3>
          {record && (
            <p className="systems-note">
              {regions[record.region]?.name ?? `Region ${record.region}`}; founded turn {record.founded_turn};
              peak {rankLabel(record.peak_rank)} ({record.peak_residents} people), purse peak{" "}
              {record.peak_wealth.toFixed(0)}
              {record.fallen_turn != null ? `; fell at turn ${record.fallen_turn} (${record.fall_cause})` : ""}.
            </p>
          )}
          <div className="systems-chart-pair">
            <CivLineChart
              data={purse}
              civs={[PURSE]}
              color={() => "#e8b84a"}
              currentTurn={currentTurn}
              label={`Civic purse of ${selectedName}`}
              format={(value) => value.toFixed(1)}
            />
            <CivLineChart
              data={unrest}
              civs={[UNREST]}
              color={() => "#d9644a"}
              currentTurn={currentTurn}
              label={`Unrest of ${selectedName}`}
              format={(value) => value.toFixed(2)}
            />
          </div>
          <SystemEventList
            events={moments.flatMap((moment) => (moment.event ? [moment.event] : []))}
            label={`Recorded moments of ${selectedName}`}
            emptyText={`No recorded moment of ${selectedName} by turn ${currentTurn}.`}
            onSelectEvent={onSelectEvent}
          />
        </section>
      )}

      <section className="systems-section">
        <h3>Foundings, charters, revolts and falls</h3>
        <SystemEventList
          events={events}
          label="City events"
          emptyText={`No city event by turn ${currentTurn}.`}
          onSelectEvent={onSelectEvent}
        />
      </section>
    </div>
  );
}
