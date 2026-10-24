import { useMemo } from "react";
import { factionColor } from "../../lib/colors";
import {
  civInitials, eventsOfTypes, grievanceColor, humanize, LADDER_COLORS, LADDER_STAGES, ladderRows, maxGrievance, orderedCivNames,
  pairMatrix, recordedSpan, SYSTEM_EVENT_TYPES, trustColor, TRUST_SCALE, type PairCell, type SystemPanelProps,
} from "../../lib/systems";
import { StatTile, StripLegend, SystemEventList, TurnStrip } from "./SystemParts";

function PairTable({
  title, civs, cells, value, color, onSelectCivilization,
}: {
  title: string;
  civs: string[];
  cells: Map<string, Map<string, PairCell>>;
  value: (cell: PairCell) => number;
  color: (value: number) => string;
  onSelectCivilization: (civ: string) => void;
}) {
  return (
    <div className="systems-table-wrap">
      <table className="systems-table systems-matrix" aria-label={title}>
        <caption>{title}</caption>
        <thead>
          <tr>
            <th scope="col"><span className="systems-muted">holder ↓ / toward →</span></th>
            {civs.map((civ) => (
              <th key={civ} scope="col" title={civ}>
                <span className="phase75-civ-swatch" style={{ backgroundColor: factionColor(civ) }} /> {civInitials(civ)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {civs.map((holder) => (
            <tr key={holder}>
              <th scope="row">
                <button type="button" className="systems-link" onClick={() => onSelectCivilization(holder)}>
                  <span className="phase75-civ-swatch" style={{ backgroundColor: factionColor(holder) }} /> {holder}
                </button>
              </th>
              {civs.map((target) => {
                const cell = holder === target ? undefined : cells.get(holder)?.get(target);
                if (!cell) {
                  return (
                    <td key={target} className="systems-matrix-empty" title={holder === target ? "" : "No memory recorded"}>
                      {holder === target ? "" : "·"}
                    </td>
                  );
                }
                const number = value(cell);
                return (
                  <td
                    key={target}
                    className="systems-matrix-cell"
                    style={{ backgroundColor: color(number) }}
                    title={`${holder} toward ${target}: trust ${cell.trust.toFixed(1)}, grievance ${cell.grievance.toFixed(1)}`}
                  >
                    {number.toFixed(0)}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function DiplomacyPanel({
  bundle, snapshot, currentTurn, onSeek, onSelectEvent, onSelectCivilization,
}: SystemPanelProps) {
  const history = bundle.history;
  const ladder = useMemo(() => ladderRows(history), [history]);
  const grievanceMax = useMemo(() => maxGrievance(history), [history]);
  const { first, end } = recordedSpan(history);
  const diplomacy = snapshot?.diplomacy;
  const at = snapshot?.turn ?? currentTurn;
  const matrix = pairMatrix(snapshot);
  const civs = orderedCivNames(bundle.world_state.civilizations.map((civ) => civ.name), matrix.civs);
  const events = eventsOfTypes(bundle.events_timeline, SYSTEM_EVENT_TYPES.diplomacy, currentTurn);
  const counts = diplomacy?.counts ?? {};
  const countOf = (prefix: string) => Object.entries(counts)
    .filter(([key]) => key.startsWith(prefix)).reduce((sum, [, value]) => sum + value, 0);

  return (
    <div className="systems-panel-body" aria-label="Diplomacy">
      {diplomacy ? (
        <div className="systems-tiles">
          <StatTile label="Active treaties" value={diplomacy.treaties.length} detail={`turn ${at}`} />
          <StatTile label="Subjects" value={diplomacy.subjects.length} />
          <StatTile label="Signed so far" value={countOf("signed:")} />
          <StatTile label="Broken so far" value={countOf("broken:")} />
        </div>
      ) : (
        <div className="phase75-empty-state">No diplomacy record at turn {at}.</div>
      )}

      <div className="systems-columns">
        <div className="systems-stack">
          {diplomacy && (
            <section className="systems-section">
              <h3>Active treaties at turn {at}</h3>
              {diplomacy.treaties.length === 0 ? (
                <div className="phase75-empty-state">No treaty in force at turn {at}.</div>
              ) : (
                <div className="systems-table-wrap">
                  <table className="systems-table" aria-label={`Active treaties at turn ${at}`}>
                    <thead><tr><th>Treaty</th><th>Kind</th><th>Parties</th><th>Since</th><th>Expires</th></tr></thead>
                    <tbody>
                      {diplomacy.treaties.map((treaty) => (
                        <tr key={treaty.id}>
                          <td>{treaty.name || `Treaty ${treaty.id}`}</td>
                          <td>{humanize(treaty.kind)}</td>
                          <td>{treaty.parties.join(treaty.kind === "tribute" ? " pays " : " · ")}</td>
                          <td>T{treaty.start}</td>
                          <td>{treaty.expiry == null ? "Open-ended" : `T${treaty.expiry}`}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </section>
          )}

          <section className="systems-section">
            <h3>Vassal ladder</h3>
            <ol className="systems-ladder" aria-label="Ladder stages">
              {LADDER_STAGES.map((stage) => (
                <li key={stage}>
                  <span className="phase75-civ-swatch" style={{ backgroundColor: LADDER_COLORS[stage] }} />
                  {stage}
                </li>
              ))}
              <li><span className="systems-muted">annexation ends the relation</span></li>
            </ol>
            {diplomacy && diplomacy.subjects.length > 0 && (
              <div className="systems-table-wrap">
                <table className="systems-table" aria-label={`Subjects at turn ${at}`}>
                  <thead><tr><th>Overlord</th><th>Subject</th><th>Stage</th><th>Since</th><th>Integration</th></tr></thead>
                  <tbody>
                    {diplomacy.subjects.map((subject) => (
                      <tr key={`${subject.overlord}-${subject.vassal}`}>
                        <td>{subject.overlord}</td>
                        <td>{subject.vassal}</td>
                        <td>{subject.stage ?? "vassal"}</td>
                        <td>{subject.since == null ? "Not recorded" : `T${subject.since}`}</td>
                        <td>{subject.integration == null ? "Not recorded" : `${subject.integration.toFixed(1)} / 100`}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            {diplomacy && diplomacy.subjects.length === 0 && (
              <div className="phase75-empty-state">No subject polity at turn {at}.</div>
            )}
            <TurnStrip
              rows={ladder}
              firstTurn={first}
              endTurn={end}
              currentTurn={currentTurn}
              label="Overlord and subject stages over time"
              emptyText="No polity entered the ladder in this run."
              onSeek={onSeek}
            />
          </section>

          {diplomacy && (
            <section className="systems-section">
              <h3>Trust and grievance at turn {at}</h3>
              {civs.length === 0 ? (
                <div className="phase75-empty-state">No pair memory recorded at turn {at}.</div>
              ) : (
                <>
                  <StripLegend items={[
                    { label: `distrust (−${TRUST_SCALE} or less)`, color: trustColor(-TRUST_SCALE) },
                    { label: "neutral", color: trustColor(0) },
                    { label: `trust (+${TRUST_SCALE} or more)`, color: trustColor(TRUST_SCALE) },
                  ]} />
                  <PairTable
                    title={`Trust of each row civilization toward each column civilization, turn ${at} (−100 to 100)`}
                    civs={civs}
                    cells={matrix.cells}
                    value={(cell) => cell.trust}
                    color={trustColor}
                    onSelectCivilization={onSelectCivilization}
                  />
                  <StripLegend items={[
                    { label: "no grievance", color: grievanceColor(0, grievanceMax) },
                    { label: `largest in the run (${grievanceMax.toFixed(0)})`, color: grievanceColor(grievanceMax, grievanceMax) },
                  ]} />
                  <PairTable
                    title={`Total grievance of each row civilization against each column civilization, turn ${at}`}
                    civs={civs}
                    cells={matrix.cells}
                    value={(cell) => cell.grievance}
                    color={(value) => grievanceColor(value, grievanceMax)}
                    onSelectCivilization={onSelectCivilization}
                  />
                </>
              )}
              {!matrix.complete && (
                <p className="systems-note">
                  This bundle exports only the five largest grievances per turn; other pairs are not recorded.
                </p>
              )}
              {diplomacy.top_grievances.length > 0 && (
                <ul className="systems-grievances" aria-label={`Largest grievances at turn ${at}`}>
                  {diplomacy.top_grievances.map((entry) => (
                    <li key={`${entry.holder}-${entry.target}`} className="phase75-mini-card">
                      <strong>{entry.holder} → {entry.target}: {entry.grievance.toFixed(1)}</strong>
                      <span>
                        {Object.entries(entry.kinds).map(([kind, amount]) => `${kind} ${amount.toFixed(1)}`).join(" · ")}
                        {` · trust ${entry.trust.toFixed(1)}`}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          )}
        </div>

        <section className="systems-section">
          <h3>Treaty and ladder events</h3>
          <SystemEventList
            events={events}
            label="Diplomacy events"
            emptyText={`No treaty or ladder event by turn ${currentTurn}.`}
            onSelectEvent={onSelectEvent}
          />
        </section>
      </div>
    </div>
  );
}
