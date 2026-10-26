import { useMemo, useState } from "react";
import {
  civName, CREED_COLORS, CREED_LABELS, creedSeries, institutionLabel, leaderLabel, martyrdoms, memberSeries,
  MOVEMENT_COUNTERS, movementHistory, movementKeys, movementRecord, movementRecordAt, movementRecordNote,
  movementStageRows, reformName, reformsInForce, regionName, STAGE_COLORS, STAGE_ORDER,
} from "../../lib/movements";
import { eventsOfTypes, recordedSpan, SYSTEM_EVENT_TYPES, type SystemPanelProps } from "../../lib/systems";
import { CivLegend, CivLineChart, StatTile, StripLegend, SystemEventList, TurnStrip } from "./SystemParts";

const MEMBERS = "Members";

/** Who is organised against whom, what they won and lost, and one movement's history. */
export function MovementsPanel({
  bundle, snapshot, currentTurn, onSeek, onSelectEvent, onSelectRegion, onSelectCivilization,
}: SystemPanelProps) {
  const history = bundle.history;
  const keys = useMemo(() => movementKeys(history), [history]);
  const rows = useMemo(() => movementStageRows(history, keys), [history, keys]);
  const creeds = useMemo(() => creedSeries(history), [history]);
  const martyred = useMemo(() => martyrdoms(bundle.events_timeline), [bundle.events_timeline]);
  // The guild creed only where the run records guilds (--guilds); legend and chart agree.
  const creedsShown = useMemo(
    () => CREED_LABELS.filter((creed) => creed !== "guild" || history.some((h) => h.guilds)), [history]);
  const { first, end } = recordedSpan(history);
  const state = snapshot?.agent_movements;
  const at = snapshot?.turn ?? currentTurn;
  const living = state?.living ?? [];
  const reforms = reformsInForce(snapshot);
  // Movements recorded by the scrubbed turn (a later one is not the default focus).
  const known = useMemo(
    () => movementKeys(history.filter((row) => row.turn <= currentTurn)), [history, currentTurn]);
  const [chosen, setChosen] = useState<number | null>(null);
  const selected = chosen ?? living[0]?.id ?? known[known.length - 1]?.id ?? null;
  const selectedName = keys.find((key) => key.id === selected)?.name ?? null;
  const members = selected == null ? [] : memberSeries(history, selected, MEMBERS);
  const record = selected == null ? null : movementRecordAt(bundle, selected, currentTurn);
  const moments = selected == null ? [] : movementHistory(bundle, selected, currentTurn);
  const events = eventsOfTypes(bundle.events_timeline, SYSTEM_EVENT_TYPES.movements, currentTurn);

  return (
    <div className="systems-panel-body" aria-label="Movements">
      {state ? (
        <div className="systems-tiles">
          <StatTile label="Living movements" value={living.length} detail={`turn ${at}`} />
          <StatTile label="Members" value={living.reduce((sum, row) => sum + row.members, 0)} detail="all living movements" />
          <StatTile label="Reforms in force" value={reforms.length} />
          <StatTile label="Founded so far" value={Number(state.counters.founded ?? 0)} />
          <StatTile label="Ended so far" value={state.ended} />
        </div>
      ) : (
        <div className="phase75-empty-state">No movement record at turn {at}.</div>
      )}

      <section className="systems-section">
        <h3>Movements over time</h3>
        <p className="systems-note">
          Each movement by stage from its founding to its end; select one to follow it below.
        </p>
        <StripLegend items={STAGE_ORDER.map((stage) => ({ label: stage, color: STAGE_COLORS[stage] }))} />
        <TurnStrip
          rows={rows}
          firstTurn={first}
          endTurn={end}
          currentTurn={currentTurn}
          label="Stage of each movement over time"
          emptyText="No movement was founded in this run."
          onSeek={onSeek}
          onSelectRow={(row) => setChosen(Number(row.id))}
          isRowSelected={(row) => Number(row.id) === selected}
        />
        <CivLegend civs={creedsShown} color={(creed) => CREED_COLORS[creed] ?? "#7d8a96"} />
        <CivLineChart
          data={creeds}
          civs={creedsShown}
          color={(creed) => CREED_COLORS[creed] ?? "#7d8a96"}
          currentTurn={currentTurn}
          label="Living movements by creed"
          step
          format={(value) => value.toFixed(0)}
        />
      </section>

      {state && (
        <section className="systems-section">
          <h3>Movements at turn {at}</h3>
          {living.length === 0 ? (
            <div className="phase75-empty-state">No movement is living at turn {at}.</div>
          ) : (
            <div className="systems-table-wrap">
              <table className="systems-table" aria-label={`Movements at turn ${at}`}>
                <thead>
                  <tr>
                    <th>Movement</th><th>Creed</th><th>Against</th><th>Stage</th><th>Members</th><th>Strength</th>
                    <th>Stronghold</th><th>Leader</th><th>Martyrs</th>
                  </tr>
                </thead>
                <tbody>
                  {living.map((row) => {
                    const target = civName(bundle, row.target);
                    const stronghold = regionName(bundle, row.stronghold);
                    return (
                      <tr key={row.id} aria-selected={row.id === selected}>
                        <td><button type="button" className="systems-link" onClick={() => setChosen(row.id)}>{row.name}</button></td>
                        <td>{row.creed}</td>
                        <td>
                          {target ? (
                            <button type="button" className="systems-link" onClick={() => onSelectCivilization(target)}>{target}</button>
                          ) : "-"}
                        </td>
                        <td>{row.stage}</td>
                        <td>{row.members}</td>
                        <td>{`${Math.round(100 * row.strength)}%`}</td>
                        <td>
                          {stronghold ? (
                            <button type="button" className="systems-link" onClick={() => onSelectRegion(stronghold)}>{stronghold}</button>
                          ) : "-"}
                        </td>
                        <td>{leaderLabel(row.leader, martyred, at)}</td>
                        <td>{row.martyrs}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </section>
      )}

      {state && (
        <section className="systems-section">
          <h3>Lasting reforms at turn {at}</h3>
          {reforms.length === 0 ? (
            <div className="phase75-empty-state">No lasting reform is in force at turn {at}.</div>
          ) : (
            <div className="systems-table-wrap">
              <table className="systems-table" aria-label={`Lasting reforms at turn ${at}`}>
                <thead>
                  <tr><th>Reform</th><th>Realm</th><th>Since</th><th>Institution</th><th>Won by</th></tr>
                </thead>
                <tbody>
                  {reforms.map((row) => {
                    const realm = civName(bundle, row.civ);
                    const winner = movementRecord(bundle, row.movement)?.name ?? null;
                    return (
                      <tr key={row.id}>
                        <td>{reformName(bundle, row)}</td>
                        <td>
                          {realm ? (
                            <button type="button" className="systems-link" onClick={() => onSelectCivilization(realm)}>{realm}</button>
                          ) : "-"}
                        </td>
                        <td>{row.since}</td>
                        <td>{institutionLabel(row.institution) ?? "-"}</td>
                        <td>
                          {winner ? (
                            <button type="button" className="systems-link" onClick={() => setChosen(row.movement)}>{winner}</button>
                          ) : "-"}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
          <div className="systems-counters" aria-label={`Movement totals by turn ${at}`}>
            {MOVEMENT_COUNTERS.map(([key, label]) => (
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
          {record ? (
            <p className="systems-note">
              {movementRecordNote(record, civName(bundle, record.target), regionName(bundle, record.record.home_region),
                currentTurn)}
            </p>
          ) : movementRecord(bundle, selected) && (
            <p className="systems-note">Not yet founded at turn {currentTurn}.</p>
          )}
          <CivLineChart
            data={members}
            civs={[MEMBERS]}
            color={() => "#c2924a"}
            currentTurn={currentTurn}
            label={`Members of ${selectedName}`}
            format={(value) => value.toFixed(0)}
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
        <h3>Foundings, demands, reforms, risings and repeals</h3>
        <SystemEventList
          events={events}
          label="Movement events"
          emptyText={`No movement event by turn ${currentTurn}.`}
          onSelectEvent={onSelectEvent}
        />
      </section>
    </div>
  );
}
