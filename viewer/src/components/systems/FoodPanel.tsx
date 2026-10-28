import { useMemo } from "react";
import {
  aidFlows, crisesAtSnapshot, DEARTH_COLOR, FAMINE_COLOR, famineRows, foodCrisisSpans, foodSeries, regionNamesOf,
  SHORT_COLOR, SHORT_OF_FOOD, spansOfKind, sufficiencyByRegion,
} from "../../lib/food";
import { eventsOfTypes, recordedSpan, SYSTEM_EVENT_TYPES, type SystemPanelProps } from "../../lib/systems";
import { CivLineChart, StatTile, StripLegend, SystemEventList, TurnStrip } from "./SystemParts";
import { Granaries } from "./Granaries";
import { HarvestForecasts } from "./HarvestForecasts";
import { observationEventKnown } from "../../lib/observedSystems";
import { Transactions } from "./Transactions";

const SERIES = ["Short of food", "In dearth", "In famine"];
const SERIES_COLORS: Record<string, string> = {
  "Short of food": SHORT_COLOR, "In dearth": DEARTH_COLOR, "In famine": FAMINE_COLOR,
};
const CRISIS_SERIES = ["In dearth", "In famine"];
const TABLE_ROWS = 15;

/** Where food is short, how long dearths and famines last, and who sends relief. */
export function FoodPanel({
  bundle, snapshot, currentTurn, onSeek, onSelectEvent, onSelectRegion, onSelectCivilization, selectedRegion,
}: SystemPanelProps) {
  const history = bundle.history;
  const regionNames = useMemo(() => regionNamesOf(bundle), [bundle]);
  const spans = useMemo(() => foodCrisisSpans(bundle.events_timeline), [bundle.events_timeline]);
  const { first, end } = recordedSpan(history);
  const rows = useMemo(() => famineRows(spans, regionNames, end - 1), [spans, regionNames, end]);
  const series = useMemo(() => foodSeries(history, spans), [history, spans]);
  const at = snapshot?.turn ?? currentTurn;
  const hasFood = !!snapshot?.food;
  const sufficiency = sufficiencyByRegion(snapshot, regionNames);
  // The snapshot holds the state after turn at - 1: its food and the crises reported by then.
  const running = crisesAtSnapshot(spans, at);
  const famines = spansOfKind(running, "famine");
  const dearths = spansOfKind(running, "dearth");
  const crisisByRegion = new Map(running.map((span) => [span.region, span]));
  const aid = aidFlows(snapshot, regionNames);
  const aidIn = new Map<string, number>();
  for (const flow of aid) {
    aidIn.set(flow.to, (aidIn.get(flow.to) ?? 0) + flow.amount);
  }
  const events = eventsOfTypes(bundle.events_timeline, SYSTEM_EVENT_TYPES.food, currentTurn)
    .filter((event) => observationEventKnown(event, at - 1));
  const convoys = events.filter((event) => event.turn === at - 1 && event.event_type === "aid_convoy").length;
  const onsets = spansOfKind(spans, "famine").filter((span) => span.start <= at - 1).length;
  const hasDearth = spans.some((span) => span.kind === "dearth");
  const short = [...sufficiency.values()].filter((value) => value < SHORT_OF_FOOD).length;
  // Shortest food first; regions not observed at this turn after every observed one.
  const hungry = regionNames
    .filter((name) => crisisByRegion.has(name) || (sufficiency.get(name) ?? SHORT_OF_FOOD) < SHORT_OF_FOOD)
    .sort((left, right) => (sufficiency.get(left) ?? Infinity) - (sufficiency.get(right) ?? Infinity)
      || left.localeCompare(right));
  const shown = SERIES.filter((name) => (hasFood || CRISIS_SERIES.includes(name)) && (name !== "In dearth" || hasDearth));
  const showChart = series.some((row) => shown.some((name) => (row[name] ?? 0) > 0));

  return (
    <div className="systems-panel-body" aria-label="Food">
      <Transactions bundle={bundle} snapshot={snapshot} currentTurn={currentTurn} onSeek={onSeek}
        onSelectEvent={onSelectEvent} onSelectRegion={onSelectRegion} onSelectCivilization={onSelectCivilization} />
      <HarvestForecasts bundle={bundle} snapshot={snapshot} currentTurn={currentTurn} onSeek={onSeek}
        onSelectEvent={onSelectEvent} onSelectRegion={onSelectRegion} onSelectCivilization={onSelectCivilization} />
      <Granaries bundle={bundle} snapshot={snapshot} currentTurn={currentTurn} onSeek={onSeek}
        onSelectEvent={onSelectEvent} onSelectRegion={onSelectRegion} onSelectCivilization={onSelectCivilization} />
      <div className="systems-tiles">
        <StatTile label="Regions in famine" value={famines.length} detail={`turn ${at}`} />
        {hasDearth && <StatTile label="Regions in dearth" value={dearths.length} detail={`turn ${at}`} />}
        <StatTile label="Famines so far" value={onsets} />
        {hasFood && <StatTile label="Short of food" value={short} detail="regions below their need" />}
        {hasFood && <StatTile label="Relief convoys" value={aid.length} detail="within a realm, this turn" />}
        <StatTile label="Allied aid" value={convoys} detail="convoys to hungry allies, this turn" />
      </div>

      {showChart && (
        <section className="systems-section">
          <h3>Hunger over time</h3>
          <StripLegend items={shown.map((name) => ({ label: name, color: SERIES_COLORS[name] }))} />
          <CivLineChart
            data={series}
            civs={shown}
            color={(name) => SERIES_COLORS[name]}
            currentTurn={currentTurn}
            label="Regions short of food, in dearth and in famine"
            step
          />
          {!hasFood && (
            <p className="systems-note">
              This bundle does not export regional food sufficiency (it needs an agent mode with mutual aid on), so only
              recorded dearths and famines are counted.
            </p>
          )}
        </section>
      )}

      <div className="systems-columns">
        <div className="systems-stack">
          <section className="systems-section">
            <h3>Famines by region</h3>
            <p className="systems-note">
              A bar runs from a report to the next report or the recorded end: orange while the simulation reports
              famine (a season or more of severe shortage), pale amber while it reports dearth (a lean season). Click a
              region to inspect it.
            </p>
            {hasDearth && (
              <StripLegend items={[{ label: "famine", color: FAMINE_COLOR }, { label: "dearth", color: DEARTH_COLOR }]} />
            )}
            <TurnStrip
              rows={rows}
              firstTurn={first}
              endTurn={end}
              currentTurn={currentTurn}
              label="Famines by region over time"
              emptyText="No famine or dearth with a recorded region in this run."
              onSeek={onSeek}
              onSelectRow={(row) => onSelectRegion(row.id)}
              isRowSelected={(row) => row.id === selectedRegion}
            />
          </section>

          <section className="systems-section">
            <h3>Hungry regions at turn {at}</h3>
            {hungry.length === 0 ? (
              <div className="phase75-empty-state">No region is in famine or dearth{hasFood ? " or short of food" : ""} at turn {at}.</div>
            ) : (
              <div className="systems-table-wrap">
                <table className="systems-table" aria-label={`Hungry regions at turn ${at}`}>
                  <thead>
                    <tr>
                      <th>Region</th><th>Held by</th>{hasFood && <th>Food ÷ need</th>}<th>Reported since</th>
                      {hasFood && <th>Relief received</th>}
                    </tr>
                  </thead>
                  <tbody>
                    {hungry.slice(0, TABLE_ROWS).map((name) => {
                      const span = crisisByRegion.get(name);
                      const value = sufficiency.get(name);
                      return (
                        <tr key={name} aria-current={name === selectedRegion ? "true" : undefined}>
                          <td><button type="button" className="systems-link" onClick={() => onSelectRegion(name)}>{name}</button></td>
                          <td>{snapshot?.region_control[name] ?? <span className="systems-muted">Nobody</span>}</td>
                          {hasFood && <td>{value === undefined ? "Not observed" : value.toFixed(2)}</td>}
                          <td>{span ? `${span.kind === "famine" ? "Famine" : "Dearth"} since T${span.start}`
                            : <span className="systems-muted">Nothing reported</span>}</td>
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
          <h3>Dearth, famine and relief events</h3>
          <SystemEventList
            events={events}
            label="Food events"
            emptyText={`No dearth, famine, relief or fishery event by turn ${currentTurn}.`}
            onSelectEvent={onSelectEvent}
          />
        </section>
      </div>
    </div>
  );
}
