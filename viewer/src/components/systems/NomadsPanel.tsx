import { useMemo } from "react";
import { factionColor } from "../../lib/colors";
import { herdCivs, MODE_COLORS, MODE_ORDER, modeLabel, modeRows, NOMAD_COUNTERS } from "../../lib/polity";
import {
  civSeries, eventsOfTypes, orderedCivNames, recordedSpan, SYSTEM_EVENT_TYPES, type SystemPanelProps,
} from "../../lib/systems";
import { CivLegend, CivLineChart, StatTile, StripLegend, SystemEventList, TurnStrip } from "./SystemParts";

/** Who lives by herds, whom they raid and who pays them tribute. */
export function NomadsPanel({
  bundle, snapshot, currentTurn, onSeek, onSelectEvent, onSelectCivilization, selectedCivilization,
}: SystemPanelProps) {
  const history = bundle.history;
  const worldCivs = useMemo(() => bundle.world_state.civilizations.map((civ) => civ.name), [bundle.world_state.civilizations]);
  const civs = useMemo(() => {
    const names = new Set<string>();
    for (const snap of history) {
      for (const name of Object.keys(snap.nomads?.modes ?? {})) {
        names.add(name);
      }
    }
    return orderedCivNames(worldCivs, names);
  }, [history, worldCivs]);
  const rows = useMemo(() => modeRows(history, civs, factionColor), [history, civs]);
  const herders = useMemo(() => herdCivs(history, worldCivs), [history, worldCivs]);
  // A living civ with no herds recorded has none (the summary omits zeros); a dead one is a gap.
  const herds = useMemo(() => civSeries(history, herders, (snap, civ) => (
    snap.nomads && civ in snap.nomads.modes ? (snap.nomads.herds[civ] ?? 0) : null
  )), [history, herders]);
  const { first, end } = recordedSpan(history);
  const nomads = snapshot?.nomads;
  const at = snapshot?.turn ?? currentTurn;
  const events = eventsOfTypes(bundle.events_timeline, SYSTEM_EVENT_TYPES.nomads, currentTurn);
  const modes = Object.values(nomads?.modes ?? {});

  return (
    <div className="systems-panel-body" aria-label="Nomads">
      {nomads ? (
        <div className="systems-tiles">
          <StatTile label="Nomadic peoples" value={modes.filter((mode) => mode === "nomadic").length} detail={`turn ${at}`} />
          <StatTile label="Agro-pastoral" value={modes.filter((mode) => mode === "agro_pastoral").length} />
          <StatTile label="Herds" value={nomads.herd_total.toFixed(0)} detail="head, all regions" />
          <StatTile label="Hordes riding" value={nomads.hordes.length} />
          <StatTile label="Raids so far" value={nomads.counters.raids ?? 0} detail={`${nomads.counters.plunder ?? 0} plunder`} />
        </div>
      ) : (
        <div className="phase75-empty-state">No nomad record at turn {at}.</div>
      )}

      <section className="systems-section">
        <h3>Ways of life</h3>
        <p className="systems-note">Peoples that were ever herders, by subsistence mode over time; the rest stayed settled.</p>
        <StripLegend items={MODE_ORDER.map((mode) => ({ label: modeLabel(mode), color: MODE_COLORS[mode] }))} />
        <TurnStrip
          rows={rows}
          firstTurn={first}
          endTurn={end}
          currentTurn={currentTurn}
          label="Subsistence mode of each civilization over time"
          emptyText="Every people stayed settled in this run."
          onSeek={onSeek}
          onSelectRow={(row) => onSelectCivilization(row.id)}
          isRowSelected={(row) => row.id === selectedCivilization}
        />
      </section>

      {herders.length > 0 && (
        <section className="systems-section">
          <h3>Herds per civilization</h3>
          <CivLegend civs={herders} color={factionColor} />
          <CivLineChart
            data={herds}
            civs={herders}
            color={factionColor}
            currentTurn={currentTurn}
            label="Herd head on each civilization's land"
            format={(value) => value.toFixed(1)}
          />
        </section>
      )}

      <div className="systems-columns">
        {nomads && (
          <section className="systems-section">
            <h3>Hordes and tribute at turn {at}</h3>
            {nomads.hordes.length === 0 ? (
              <div className="phase75-empty-state">No horde rides at turn {at}.</div>
            ) : nomads.hordes.map((horde) => (
              <div key={horde.name} className="phase75-mini-card">
                <strong>{horde.name}</strong>
                <span>Khan: {horde.khan} · {horde.members.join(", ")}</span>
              </div>
            ))}
            {nomads.tributes.length === 0 ? (
              <div className="phase75-empty-state">No tribute is paid at turn {at}.</div>
            ) : (
              <div className="systems-table-wrap">
                <table className="systems-table" aria-label={`Tribute at turn ${at}`}>
                  <thead><tr><th>Payer</th><th>Paid to</th><th>Per turn</th></tr></thead>
                  <tbody>
                    {nomads.tributes.map((tribute) => (
                      <tr key={`${tribute.payer}-${tribute.recipient}`}>
                        <td><button type="button" className="systems-link" onClick={() => onSelectCivilization(tribute.payer)}>{tribute.payer}</button></td>
                        <td><button type="button" className="systems-link" onClick={() => onSelectCivilization(tribute.recipient)}>{tribute.recipient}</button></td>
                        <td>{tribute.amount}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            <div className="systems-counters" aria-label={`Nomad totals by turn ${at}`}>
              {NOMAD_COUNTERS.map(([key, label]) => (
                <div key={key} className="phase75-stat-row">
                  <span>{label}</span>
                  <strong>{Number(nomads.counters[key] ?? 0).toLocaleString(undefined, { maximumFractionDigits: 1 })}</strong>
                </div>
              ))}
            </div>
          </section>
        )}

        <section className="systems-section">
          <h3>Raids, hordes and herds</h3>
          <SystemEventList
            events={events}
            label="Nomad events"
            emptyText={`No raid, tribute, horde or dzud by turn ${currentTurn}.`}
            onSelectEvent={onSelectEvent}
          />
        </section>
      </div>
    </div>
  );
}
