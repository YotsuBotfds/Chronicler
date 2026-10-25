import { useMemo } from "react";
import {
  aidFlows, FAMINE_COLOR, faminesAt, famineRows, famineSpans, foodSeries, regionNamesOf, SHORT_COLOR,
  SHORT_OF_FOOD, sufficiencyByRegion,
} from "../../lib/food";
import { eventsOfTypes, recordedSpan, SYSTEM_EVENT_TYPES, type SystemPanelProps } from "../../lib/systems";
import { CivLineChart, StatTile, StripLegend, SystemEventList, TurnStrip } from "./SystemParts";

const SERIES = ["Short of food", "In famine"];
const SERIES_COLORS: Record<string, string> = { "Short of food": SHORT_COLOR, "In famine": FAMINE_COLOR };
const TABLE_ROWS = 15;

/** Where food is short, how long famines last, and who sends relief. */
export function FoodPanel({
  bundle, snapshot, currentTurn, onSeek, onSelectEvent, onSelectRegion, selectedRegion,
}: SystemPanelProps) {
  const history = bundle.history;
  const regionNames = useMemo(() => regionNamesOf(bundle), [bundle]);
  const spans = useMemo(() => famineSpans(bundle.events_timeline), [bundle.events_timeline]);
  const { first, end } = recordedSpan(history);
  const rows = useMemo(() => famineRows(spans, regionNames, end - 1), [spans, regionNames, end]);
  const series = useMemo(() => foodSeries(history, spans), [history, spans]);
  const at = snapshot?.turn ?? currentTurn;
  const hasFood = !!snapshot?.food;
  const sufficiency = sufficiencyByRegion(snapshot, regionNames);
  const famines = faminesAt(spans, at);
  const famineByRegion = new Map(famines.map((span) => [span.region, span]));
  const aid = aidFlows(snapshot, regionNames);
  const aidIn = new Map<string, number>();
  for (const flow of aid) {
    aidIn.set(flow.to, (aidIn.get(flow.to) ?? 0) + flow.amount);
  }
  const events = eventsOfTypes(bundle.events_timeline, SYSTEM_EVENT_TYPES.food, currentTurn);
  const convoys = events.filter((event) => event.turn === at - 1 && event.event_type === "aid_convoy").length;
  const onsets = spans.filter((span) => span.start <= at).length;
  const short = [...sufficiency.values()].filter((value) => value < SHORT_OF_FOOD).length;
  const hungry = regionNames
    .filter((name) => famineByRegion.has(name) || (sufficiency.get(name) ?? SHORT_OF_FOOD) < SHORT_OF_FOOD)
    .sort((left, right) => (sufficiency.get(left) ?? 0) - (sufficiency.get(right) ?? 0) || left.localeCompare(right));
  const showChart = series.some((row) => (row["Short of food"] ?? 0) > 0 || (row["In famine"] ?? 0) > 0);

  return (
    <div className="systems-panel-body" aria-label="Food">
      <div className="systems-tiles">
        <StatTile label="Regions in famine" value={famines.length} detail={`turn ${at}`} />
        <StatTile label="Famines so far" value={onsets} />
        {hasFood && <StatTile label="Short of food" value={short} detail="regions below their need" />}
        {hasFood && <StatTile label="Relief convoys" value={aid.length} detail="within a realm, this turn" />}
        <StatTile label="Allied aid" value={convoys} detail="convoys to famine-struck allies, this turn" />
      </div>

      {showChart && (
        <section className="systems-section">
          <h3>Hunger over time</h3>
          <StripLegend items={SERIES.filter((name) => hasFood || name === "In famine")
            .map((name) => ({ label: name, color: SERIES_COLORS[name] }))} />
          <CivLineChart
            data={series}
            civs={hasFood ? SERIES : ["In famine"]}
            color={(name) => SERIES_COLORS[name]}
            currentTurn={currentTurn}
            label="Regions short of food and regions in famine"
            step
          />
          {!hasFood && (
            <p className="systems-note">
              This bundle does not export regional food sufficiency (it needs an agent mode with mutual aid on), so only
              famines are counted.
            </p>
          )}
        </section>
      )}

      <div className="systems-columns">
        <div className="systems-stack">
          <section className="systems-section">
            <h3>Famines by region</h3>
            <p className="systems-note">A bar runs from a famine&apos;s onset to its recorded end; click a region to inspect it.</p>
            <TurnStrip
              rows={rows}
              firstTurn={first}
              endTurn={end}
              currentTurn={currentTurn}
              label="Famines by region over time"
              emptyText="No famine with a recorded region in this run."
              onSeek={onSeek}
              onSelectRow={(row) => onSelectRegion(row.id)}
              isRowSelected={(row) => row.id === selectedRegion}
            />
          </section>

          <section className="systems-section">
            <h3>Hungry regions at turn {at}</h3>
            {hungry.length === 0 ? (
              <div className="phase75-empty-state">No region is in famine{hasFood ? " or short of food" : ""} at turn {at}.</div>
            ) : (
              <div className="systems-table-wrap">
                <table className="systems-table" aria-label={`Hungry regions at turn ${at}`}>
                  <thead>
                    <tr>
                      <th>Region</th><th>Held by</th>{hasFood && <th>Food ÷ need</th>}<th>Famine since</th>
                      {hasFood && <th>Relief received</th>}
                    </tr>
                  </thead>
                  <tbody>
                    {hungry.slice(0, TABLE_ROWS).map((name) => {
                      const span = famineByRegion.get(name);
                      const value = sufficiency.get(name);
                      return (
                        <tr key={name} aria-current={name === selectedRegion ? "true" : undefined}>
                          <td><button type="button" className="systems-link" onClick={() => onSelectRegion(name)}>{name}</button></td>
                          <td>{snapshot?.region_control[name] ?? <span className="systems-muted">Nobody</span>}</td>
                          {hasFood && <td>{value === undefined ? "Not observed" : value.toFixed(2)}</td>}
                          <td>{span ? `T${span.start}` : <span className="systems-muted">No famine</span>}</td>
                          {hasFood && <td>{aidIn.has(name) ? (aidIn.get(name) ?? 0).toFixed(1) : ""}</td>}
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
                {hungry.length > TABLE_ROWS && <p className="systems-note">{hungry.length - TABLE_ROWS} more hungry regions.</p>}
              </div>
            )}
            {hasFood && aid.length > 0 && (
              <div className="systems-inline-list" aria-label={`Relief convoys at turn ${at}`}>
                <span className="phase75-overline">Relief</span>
                {aid.map((flow) => (
                  <span key={`${flow.from}-${flow.to}`} className="systems-chip">{flow.from} → {flow.to}: {flow.amount.toFixed(1)}</span>
                ))}
              </div>
            )}
            {hasFood && (
              <p className="systems-note">
                Food ÷ need is the region&apos;s food on hand over what its people eat in a turn (capped at 2); below 1 the
                region is short. Relief is food moved between neighbouring regions of one realm.
              </p>
            )}
          </section>
        </div>

        <section className="systems-section">
          <h3>Famine and relief events</h3>
          <SystemEventList
            events={events}
            label="Food events"
            emptyText={`No famine, relief or fishery event by turn ${currentTurn}.`}
            onSelectEvent={onSelectEvent}
          />
        </section>
      </div>
    </div>
  );
}
