import { useMemo } from "react";
import { factionColor } from "../../lib/colors";
import { eventsOfTypes, humanize, recordedSpan, SYSTEM_EVENT_TYPES, type SystemPanelProps } from "../../lib/systems";
import { battleLosses, battlesUpTo, warLeader, warRows } from "../../lib/wars";
import { StatTile, SystemEventList, TurnStrip } from "./SystemParts";

const BATTLE_ROWS = 15;

function CivLink({ civ, onSelect }: { civ: string; onSelect: (civ: string) => void }) {
  return (
    <button type="button" className="systems-link" onClick={() => onSelect(civ)}>
      <span className="phase75-civ-swatch" style={{ backgroundColor: factionColor(civ) }} /> {civ}
    </button>
  );
}

function RegionLink({ region, onSelect }: { region: string | null; onSelect: (region: string) => void }) {
  if (!region) {
    return <span className="systems-muted">None</span>;
  }
  return <button type="button" className="systems-link" onClick={() => onSelect(region)}>{region}</button>;
}

/** Who is fighting whom, where, and who is winning (the campaign layer). */
export function WarsPanel({
  bundle, snapshot, currentTurn, onSeek, onSelectEvent, onSelectRegion, onSelectCivilization,
}: SystemPanelProps) {
  const history = bundle.history;
  const rows = useMemo(() => warRows(history, factionColor), [history]);
  const { first, end } = recordedSpan(history);
  const campaign = snapshot?.campaign;
  const at = snapshot?.turn ?? currentTurn;
  const battles = useMemo(() => battlesUpTo(history, at), [history, at]);
  const events = eventsOfTypes(bundle.events_timeline, SYSTEM_EVENT_TYPES.wars, currentTurn);
  const soldiers = campaign?.armies.reduce((sum, army) => sum + army.soldiers, 0) ?? 0;

  return (
    <div className="systems-panel-body" aria-label="Wars">
      {campaign ? (
        <div className="systems-tiles">
          <StatTile label="Wars" value={campaign.wars.length} detail={`turn ${at}`} />
          <StatTile label="Armies in the field" value={campaign.armies.length} detail={`${soldiers} soldiers`} />
          <StatTile label="Occupied regions" value={campaign.occupations.length} />
          <StatTile label="Battles so far" value={battles.length} detail={`${battleLosses(battles)} soldiers lost`} />
        </div>
      ) : (
        <div className="phase75-empty-state">No campaign record at turn {at}.</div>
      )}

      <section className="systems-section">
        <h3>Wars over time</h3>
        <p className="systems-note">
          One row per war. A bar is coloured (and initialled) by the side ahead on war score, grey while level; hover
          for the aim and the score range.
        </p>
        <TurnStrip
          rows={rows}
          firstTurn={first}
          endTurn={end}
          currentTurn={currentTurn}
          label="Wars over time"
          emptyText="No war was fought in this run."
          onSeek={onSeek}
        />
      </section>

      <div className="systems-columns">
        <div className="systems-stack">
          {campaign && (
            <section className="systems-section">
              <h3>Wars at turn {at}</h3>
              {campaign.wars.length === 0 ? (
                <div className="phase75-empty-state">No war at turn {at}.</div>
              ) : (
                <div className="systems-table-wrap">
                  <table className="systems-table" aria-label={`Wars at turn ${at}`}>
                    <thead>
                      <tr><th>Attacker</th><th>Defender</th><th>Aim</th><th>Score</th><th>Ahead</th><th>Since</th><th>Battles</th></tr>
                    </thead>
                    <tbody>
                      {campaign.wars.map((war) => {
                        const leader = warLeader(war);
                        return (
                          <tr key={`${war.war}@${war.start_turn}`}>
                            <td><CivLink civ={war.attacker} onSelect={onSelectCivilization} /></td>
                            <td><CivLink civ={war.defender} onSelect={onSelectCivilization} /></td>
                            <td>
                              {humanize(war.aim)}
                              {war.aim_region && <> of <RegionLink region={war.aim_region} onSelect={onSelectRegion} /></>}
                            </td>
                            <td>{war.score}</td>
                            <td>{leader ?? "Level"}</td>
                            <td>T{war.start_turn}</td>
                            <td>{war.battles}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
              <p className="systems-note">War score runs from -100 to 100; above zero favours the attacker.</p>
            </section>
          )}

          {campaign && (
            <section className="systems-section">
              <h3>Armies at turn {at}</h3>
              {campaign.armies.length === 0 ? (
                <div className="phase75-empty-state">No army in the field at turn {at}.</div>
              ) : (
                <div className="systems-table-wrap">
                  <table className="systems-table" aria-label={`Armies at turn ${at}`}>
                    <thead>
                      <tr>
                        <th>Army</th><th>Civilization</th><th>In</th><th>Objective</th><th>Doing</th>
                        <th>Soldiers</th><th>Morale</th><th>Rations</th><th>General</th>
                      </tr>
                    </thead>
                    <tbody>
                      {campaign.armies.map((army) => (
                        <tr key={army.id}>
                          <td>{army.name}</td>
                          <td><CivLink civ={army.civ} onSelect={onSelectCivilization} /></td>
                          <td><RegionLink region={army.region} onSelect={onSelectRegion} /></td>
                          <td><RegionLink region={army.objective} onSelect={onSelectRegion} /></td>
                          <td>{humanize(army.phase)}{army.siege_turns > 0 ? ` (${army.siege_turns} turns)` : ""}</td>
                          <td>{army.soldiers}</td>
                          <td>{(army.morale / 10).toFixed(0)}%</td>
                          <td>{army.rations}</td>
                          <td>{army.general ?? <span className="systems-muted">None</span>}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
              {campaign.occupations.length > 0 && (
                <div className="systems-table-wrap">
                  <table className="systems-table" aria-label={`Occupations at turn ${at}`}>
                    <thead><tr><th>Occupied region</th><th>Owner</th><th>Occupier</th><th>Since</th><th>Unrest</th><th>Revolts</th></tr></thead>
                    <tbody>
                      {campaign.occupations.map((occupation) => (
                        <tr key={occupation.region}>
                          <td><RegionLink region={occupation.region} onSelect={onSelectRegion} /></td>
                          <td><CivLink civ={occupation.owner} onSelect={onSelectCivilization} /></td>
                          <td><CivLink civ={occupation.occupier} onSelect={onSelectCivilization} /></td>
                          <td>T{occupation.since_turn}</td>
                          <td>{(occupation.unrest / 10).toFixed(0)}%</td>
                          <td>{occupation.revolts}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </section>
          )}

          <section className="systems-section">
            <h3>Battles up to turn {at}</h3>
            {battles.length === 0 ? (
              <div className="phase75-empty-state">No battle recorded by turn {at}.</div>
            ) : (
              <div className="systems-table-wrap">
                <table className="systems-table" aria-label={`Battles up to turn ${at}`}>
                  <thead><tr><th>Turn</th><th>Battle</th><th>Where</th><th>Winner</th><th>Soldiers</th><th>Lost</th></tr></thead>
                  <tbody>
                    {battles.slice(0, BATTLE_ROWS).map((battle) => (
                      <tr key={`${battle.turn}-${battle.name}-${battle.attacker}`}>
                        <td>
                          <button type="button" className="systems-link" onClick={() => onSeek(battle.turn + 1)}>T{battle.turn}</button>
                        </td>
                        <td title={`${battle.attacker} attacked ${battle.defender} (${battle.kind})`}>{battle.name}</td>
                        <td><RegionLink region={battle.region} onSelect={onSelectRegion} /></td>
                        <td>{battle.winner ?? "Undecided"}</td>
                        <td>{battle.attacker_soldiers} v {battle.defender_soldiers}</td>
                        <td>{battle.attacker_losses} / {battle.defender_losses}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {battles.length > BATTLE_ROWS && (
                  <p className="systems-note">{battles.length - BATTLE_ROWS} earlier battles not listed.</p>
                )}
              </div>
            )}
          </section>
        </div>

        <section className="systems-section">
          <h3>War events</h3>
          <SystemEventList
            events={events}
            label="War events"
            emptyText={`No declaration, siege, occupation or peace by turn ${currentTurn}.`}
            onSelectEvent={onSelectEvent}
          />
        </section>
      </div>
    </div>
  );
}
