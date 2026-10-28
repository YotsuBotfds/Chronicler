import { useMemo, useState } from "react";
import {
  fallLabel, LEVEL_COLORS, LEVEL_LABELS, levelLabel, PATRON_LABELS, SEAT_COUNTERS, seatHistory, seatKeys,
  seatLevelRows, seatRecordAt, seatScholarSeries, seatsAt, seatStanding,
} from "../../lib/learning";
import { eventsOfTypes, recordedSpan, SYSTEM_EVENT_TYPES, type SystemPanelProps } from "../../lib/systems";
import { CivLineChart, StatTile, StripLegend, SystemEventList, TurnStrip } from "./SystemParts";
import { ScientificClaims } from "./ScientificClaims";

const SCHOLARS = "Scholars";

/** Which seats of learning stand, who keeps them, their scholars, and one seat's history. */
export function LearningPanel({
  bundle, snapshot, currentTurn, onSeek, onSelectEvent, onSelectRegion, onSelectCivilization,
}: SystemPanelProps) {
  const history = bundle.history;
  const keys = useMemo(() => seatKeys(history), [history]);
  const rows = useMemo(() => seatLevelRows(history, keys), [history, keys]);
  const { first, end } = recordedSpan(history);
  const state = snapshot?.scholarship;
  const at = snapshot?.turn ?? currentTurn;
  const living = seatsAt(snapshot);
  // Seats recorded by the scrubbed turn (a later seat is not the default focus).
  const known = useMemo(
    () => seatKeys(history.filter((row) => row.turn <= currentTurn)), [history, currentTurn]);
  const [chosen, setChosen] = useState<number | null>(null);
  const selected = chosen ?? living[0]?.id ?? known[known.length - 1]?.id ?? null;
  const selectedName = keys.find((key) => key.id === selected)?.name ?? null;
  const scholars = selected == null ? [] : seatScholarSeries(history, selected, SCHOLARS);
  const record = selected == null ? null : seatRecordAt(bundle, selected, currentTurn);
  const moments = selected == null ? [] : seatHistory(bundle, selected, currentTurn);
  const events = eventsOfTypes(bundle.events_timeline, SYSTEM_EVENT_TYPES.learning, currentTurn);
  const regions = bundle.world_state.regions;
  const civs = bundle.world_state.civilizations;

  return (
    <div className="systems-panel-body" aria-label="Seats of learning">
      <ScientificClaims bundle={bundle} snapshot={snapshot} currentTurn={currentTurn} onSeek={onSeek}
        onSelectEvent={onSelectEvent} onSelectRegion={onSelectRegion} onSelectCivilization={onSelectCivilization} />
      {state ? (
        <div className="systems-tiles">
          <StatTile label="Seats of learning" value={living.length} detail={`turn ${at}`} />
          <StatTile label="Great seats" value={living.filter((row) => row.level >= 3).length} />
          <StatTile
            label="Scholars"
            value={living.reduce((sum, row) => sum + row.scholars, 0).toFixed(0)}
            detail="at all standing seats"
          />
          <StatTile label="Great scholars teaching" value={living.reduce((sum, row) => sum + row.masters, 0)} />
          <StatTile label="Fallen so far" value={state.fallen} />
        </div>
      ) : (
        <div className="phase75-empty-state">No record of seats of learning at turn {at}.</div>
      )}

      <section className="systems-section">
        <h3>Seats over time</h3>
        <p className="systems-note">
          Academies kept by rulers, temple schools by their temples and libraries by their cities, by level from
          founding to fall; select one to follow it below.
        </p>
        <StripLegend items={[1, 2, 3].map((level) => ({ label: LEVEL_LABELS[level], color: LEVEL_COLORS[level] }))} />
        <TurnStrip
          rows={rows}
          firstTurn={first}
          endTurn={end}
          currentTurn={currentTurn}
          label="Level of each seat of learning over time"
          emptyText="No seat of learning was founded in this run."
          onSeek={onSeek}
          onSelectRow={(row) => setChosen(Number(row.id))}
          isRowSelected={(row) => Number(row.id) === selected}
        />
      </section>

      {state && (
        <section className="systems-section">
          <h3>Seats of learning at turn {at}</h3>
          {living.length === 0 ? (
            <div className="phase75-empty-state">No seat of learning stands at turn {at}.</div>
          ) : (
            <div className="systems-table-wrap">
              <table className="systems-table" aria-label={`Seats of learning at turn ${at}`}>
                <thead>
                  <tr>
                    <th>Seat</th><th>Kind</th><th>Region</th><th>Ruler</th><th>Kept by</th><th>Level</th>
                    <th>Scholars</th><th>Great scholars</th><th>Standing</th>
                  </tr>
                </thead>
                <tbody>
                  {living.map((row) => (
                    <tr key={row.id} aria-selected={row.id === selected}>
                      <td><button type="button" className="systems-link" onClick={() => setChosen(row.id)}>{row.name}</button></td>
                      <td>{row.kind}</td>
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
                      <td>{PATRON_LABELS[row.kind] ?? "-"}</td>
                      <td>{levelLabel(row.level)}</td>
                      <td>{row.scholars.toFixed(1)}</td>
                      <td>{row.masters}</td>
                      <td>{seatStanding(row)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <div className="systems-counters" aria-label={`Seat totals by turn ${at}`}>
            {SEAT_COUNTERS.map(([key, label]) => (
              <div key={key} className="phase75-stat-row">
                <span>{label}</span>
                <strong>{Number(state.counters[key] ?? 0).toLocaleString(undefined, { maximumFractionDigits: 0 })}</strong>
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
              {regions[record.record.region]?.name ?? `Region ${record.record.region}`}; founded turn{" "}
              {record.record.founded_turn}
              {record.record.founder >= 0 && civs[record.record.founder] ? ` under ${civs[record.record.founder].name}` : ""}
              {record.peakLevel > 0
                ? `; peak by turn ${currentTurn} ${levelLabel(record.peakLevel)} (${record.peakScholars.toFixed(1)} scholars)`
                : ""}
              {record.fell ? `; ${fallLabel(bundle, record.record)}` : ""}.
            </p>
          )}
          <CivLineChart
            data={scholars}
            civs={[SCHOLARS]}
            color={() => "#9a7fc4"}
            currentTurn={currentTurn}
            label={`Scholars of ${selectedName}`}
            format={(value) => value.toFixed(1)}
          />
          <SystemEventList
            events={moments.flatMap((moment) => (moment.event ? [moment.event] : []))}
            label={`Recorded moments of ${selectedName}`}
            emptyText={`No recorded moment of ${selectedName} by turn ${currentTurn}.`}
            onSelectEvent={onSelectEvent}
          />
        </section>
      )}

      <section className="systems-section">
        <h3>Foundings, rises, falls and flights</h3>
        <SystemEventList
          events={events}
          label="Seat of learning events"
          emptyText={`No seat of learning event by turn ${currentTurn}.`}
          onSelectEvent={onSelectEvent}
        />
      </section>
    </div>
  );
}
