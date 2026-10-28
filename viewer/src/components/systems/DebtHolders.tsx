import { useMemo, useState } from "react";
import { factionColor } from "../../lib/colors";
import {
  borrowers, civDebtHolders, creditEventsOf, DETAIL_NOTES, foreignLenderSeries, groupsInSeries, HOLDER_COLORS,
  HOLDER_GROUPS, HOLDER_LABELS, holderDetail, holderSeries, realmsInDebt, troubleRows, writeOffs,
  type CivDebtHolders, type HolderGroup, type HolderRow,
} from "../../lib/debtHolders";
import {
  debtToRevenue, eventsOfTypes, formatShare, recordedSpan, SYSTEM_EVENT_TYPES, type SystemPanelProps,
} from "../../lib/systems";
import { CivLineChart, StackedAreaChart, StatTile, StripLegend, SystemEventList, TurnStrip } from "./SystemParts";

function rateText(rate: number | null): string {
  return rate == null ? "-" : `${(rate * 100).toFixed(1)}%`;
}

function interestText(value: number | null): string {
  return value == null ? "-" : value.toFixed(1);
}

function lendingText(count: number): string {
  if (count === 0) {
    return "no foreign lender";
  }
  return count === 1 ? "1 lending civilization" : `${count} lending civilizations`;
}

function share(part: number, whole: number): string {
  return whole > 0 ? formatShare(part / whole, 0) : "-";
}

function barLabel(entry: CivDebtHolders): string {
  const parts = HOLDER_GROUPS.filter((group) => entry.groups[group] > 0)
    .map((group) => `${HOLDER_LABELS[group].toLowerCase()} ${entry.groups[group]} (${share(entry.groups[group], entry.debt)})`);
  return `${entry.civ} owes ${entry.debt}: ${parts.join(", ")}`;
}

/** Rows of one holder group: the group line, then its named lenders (if the bundle names them). */
function groupRows(entry: CivDebtHolders, group: HolderGroup): { total: number; interest: number | null; named: HolderRow[] } {
  const rows = entry.rows.filter((row) => row.group === group);
  const interest = rows.every((row) => row.interest != null)
    ? rows.reduce((sum, row) => sum + (row.interest ?? 0), 0)
    : null;
  return {
    total: rows.reduce((sum, row) => sum + row.amount, 0),
    interest,
    named: rows.filter((row) => row.label !== HOLDER_LABELS[group]),
  };
}

/**
 * Who holds each realm's debt (Finance panel): every indebted civilization
 * at the scrubbed turn by holder, and one borrower in detail: its holders
 * over time and at the turn, foreign lenders by name, interest, and its
 * arrears, defaults and write-offs. What it can name depends on the bundle
 * (lib/debtHolders `holderDetail`).
 */
export function DebtHolders({
  bundle, snapshot, currentTurn, onSeek, onSelectEvent, onSelectRegion, onSelectCivilization, selectedCivilization,
  civs,
}: SystemPanelProps & { civs: string[] }) {
  const history = bundle.history;
  const detail = useMemo(() => holderDetail(history), [history]);
  const candidates = useMemo(() => borrowers(history, civs), [history, civs]);
  const isCandidate = (name: string | null | undefined): name is string => !!name && candidates.includes(name);
  const [chosen, setChosen] = useState<string | null>(isCandidate(selectedCivilization) ? selectedCivilization : null);
  const [seenSelection, setSeenSelection] = useState(selectedCivilization ?? null);
  if ((selectedCivilization ?? null) !== seenSelection) {
    // A civilization selected elsewhere in the shell becomes the borrower shown.
    setSeenSelection(selectedCivilization ?? null);
    if (isCandidate(selectedCivilization)) {
      setChosen(selectedCivilization);
    }
  }
  const civ = isCandidate(chosen) ? chosen : (candidates[0] ?? null);
  const level = detail ?? "totals";
  const series = useMemo(() => (civ ? holderSeries(history, civ, level) : []), [history, civ, level]);
  const stacked = useMemo(() => groupsInSeries(series), [series]);
  const foreign = useMemo(
    () => (civ && level === "lenders" ? foreignLenderSeries(history, civ, civs) : { lenders: [], data: [] }),
    [history, civ, civs, level]);
  const trouble = useMemo(() => (civ ? troubleRows(history, civ, level) : []), [history, civ, level]);
  const losses = useMemo(
    () => (civ ? writeOffs(history, civ, bundle.events_timeline, level) : []), [history, civ, bundle.events_timeline, level]);

  if (!detail) {
    return null;
  }
  const at = snapshot?.turn ?? currentTurn;
  const realms = realmsInDebt(snapshot, civs, detail);
  const widest = Math.max(1, ...realms.map((entry) => entry.debt));
  const realmGroups = HOLDER_GROUPS.filter((group) => realms.some((entry) => entry.groups[group] > 0));
  const current = civ ? civDebtHolders(snapshot, civ, detail) : null;
  const { first, end } = recordedSpan(history);
  const lossesSoFar = losses.filter((loss) => loss.turn <= currentTurn).reverse();
  const events = civ
    ? creditEventsOf(eventsOfTypes(bundle.events_timeline, SYSTEM_EVENT_TYPES.finance, currentTurn), civ)
    : [];
  const lenders = detail === "lenders";

  return (
    <>
      <section className="systems-section" aria-label="Who holds the debt">
        <h3>Who holds the debt at turn {at}</h3>
        <p className="systems-note">{DETAIL_NOTES[detail]}</p>
        {realms.length === 0 ? (
          <div className="phase75-empty-state">No civilization owes anything at turn {at}.</div>
        ) : (
          <>
            <StripLegend items={realmGroups.map((group) => ({ label: HOLDER_LABELS[group], color: HOLDER_COLORS[group] }))} />
            <div className="debt-realms" role="list" aria-label={`Debt by holder at turn ${at}`}>
              {realms.map((entry) => (
                <div key={entry.civ} role="listitem" className={`debt-realm${entry.civ === civ ? " active" : ""}`}>
                  <button
                    type="button"
                    className="systems-link debt-realm-name"
                    aria-pressed={entry.civ === civ}
                    onClick={() => setChosen(entry.civ)}
                    title={`Show the creditors of ${entry.civ}`}
                  >
                    <span className="phase75-civ-swatch" style={{ backgroundColor: factionColor(entry.civ) }} />
                    <span>{entry.civ}</span>
                  </button>
                  <span className="debt-realm-total">{entry.debt}</span>
                  <div className="debt-realm-track" role="img" aria-label={barLabel(entry)}>
                    <div className="debt-realm-bar" style={{ width: `${(entry.debt / widest) * 100}%` }}>
                      {HOLDER_GROUPS.filter((group) => entry.groups[group] > 0).map((group) => (
                        <span
                          key={group}
                          style={{ flexGrow: entry.groups[group], backgroundColor: HOLDER_COLORS[group] }}
                          title={`${HOLDER_LABELS[group]}: ${entry.groups[group]} (${share(entry.groups[group], entry.debt)})`}
                        />
                      ))}
                    </div>
                  </div>
                </div>
              ))}
            </div>
            <p className="systems-note">Bars share one scale: the longest is the largest debt at this turn.</p>
          </>
        )}
      </section>

      {civ && (
        <section className="systems-section" aria-label={`Creditors of ${civ}`}>
          <div className="debt-detail-head">
            <h3>Creditors of {civ}</h3>
            {candidates.length > 1 && (
              <label className="phase75-layer-select">
                <span>Borrower</span>
                <select value={civ} onChange={(event) => setChosen(event.target.value)}>
                  {candidates.map((name) => <option key={name} value={name}>{name}</option>)}
                </select>
              </label>
            )}
          </div>

          {current ? (
            <div className="systems-tiles debt-tiles">
              <StatTile label="Debt" value={current.debt}
                detail={`${debtToRevenue(current.debt, current.revenue).toFixed(2)} turns of revenue`} />
              <StatTile label="Domestic" value={current.domestic} detail={`${share(current.domestic, current.debt)} of the debt`} />
              <StatTile label="Foreign" value={current.foreign}
                detail={lenders ? lendingText(current.rows.filter((row) => row.group === "foreign" && row.civ).length) : "one total"} />
              <StatTile label="Interest paid" value={current.interestPaid} detail="in this turn's fiscal tick" />
              {current.interestDue != null && (
                <StatTile label="Interest due" value={current.interestDue.toFixed(1)} detail="per turn at the lines' rates" />
              )}
              <StatTile label="Arrears" value={current.arrears} detail={current.arrears === 1 ? "turn running" : "turns running"} />
              <StatTile label="Defaults" value={current.defaults} detail="so far" />
              {current.writtenOff != null && <StatTile label="Written off" value={current.writtenOff} detail="on its debts so far" />}
            </div>
          ) : (
            <div className="phase75-empty-state">{civ} has no finance record at turn {at}.</div>
          )}

          <div className="systems-chart-pair">
            <div className="debt-chart">
              <StackedAreaChart
                data={series}
                series={stacked.map((group) => ({ key: group, label: HOLDER_LABELS[group], color: HOLDER_COLORS[group] }))}
                currentTurn={currentTurn}
                label={`Debt of ${civ} by holder`}
              />
              <StripLegend items={stacked.map((group) => ({ label: HOLDER_LABELS[group], color: HOLDER_COLORS[group] }))} />
            </div>
            {foreign.lenders.length > 0 && (
              <div className="debt-chart">
                <CivLineChart
                  data={foreign.data}
                  civs={foreign.lenders}
                  color={factionColor}
                  currentTurn={currentTurn}
                  label={`Foreign debt of ${civ} by lender`}
                  step
                />
                <StripLegend items={foreign.lenders.map((name) => ({ label: name, color: factionColor(name) }))} />
              </div>
            )}
          </div>

          <div className="systems-columns">
            <div className="systems-stack">
              {current && current.rows.length > 0 ? (
                <div className="systems-table-wrap">
                  <table className="systems-table debt-holders-table" aria-label={`Holders of the debt of ${civ} at turn ${at}`}>
                    <thead>
                      <tr>
                        <th>Holder</th><th>Owed</th><th className="debt-col-share">Share</th>
                        {lenders && <><th>Rate</th><th>Interest</th></>}
                      </tr>
                    </thead>
                    <tbody>
                      {HOLDER_GROUPS.filter((group) => current.groups[group] > 0).map((group) => {
                        const { total, interest, named } = groupRows(current, group);
                        const single = named.length === 0 ? current.rows.find((row) => row.group === group) : undefined;
                        return [
                          <tr key={group} className="debt-group-row">
                            <th scope="row">
                              <span className="phase75-civ-swatch" style={{ backgroundColor: HOLDER_COLORS[group] }} /> {HOLDER_LABELS[group]}
                            </th>
                            <td>{total}</td>
                            <td className="debt-col-share">{share(total, current.debt)}</td>
                            {lenders && <><td>{rateText(single ? single.rate : null)}</td><td>{interestText(interest)}</td></>}
                          </tr>,
                          ...named.map((row) => (
                            <tr key={row.id} className="debt-member-row">
                              <td>
                                {row.civ ? (
                                  <button type="button" className="systems-link" onClick={() => onSelectCivilization(row.civ!)}>{row.label}</button>
                                ) : row.region ? (
                                  <button type="button" className="systems-link" onClick={() => onSelectRegion(row.region!)}>{row.label}</button>
                                ) : row.label}
                              </td>
                              <td>{row.amount}</td>
                              <td className="debt-col-share">{share(row.amount, current.debt)}</td>
                              {lenders && <><td>{rateText(row.rate)}</td><td>{interestText(row.interest)}</td></>}
                            </tr>
                          )),
                        ];
                      })}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="phase75-empty-state">{civ} owes nothing at turn {at}.</div>
              )}
              <p className="systems-note">
                {lenders
                  ? "Interest is due per turn at the line's rate. Merchants are named by the region they live in; "
                    + "foreign lenders and regions open in the inspector."
                  : "The bundle does not name individual lenders."}
              </p>
            </div>

            <div className="systems-stack">
              <TurnStrip
                rows={trouble}
                firstTurn={first}
                endTurn={end}
                currentTurn={currentTurn}
                label={`Arrears, defaults and write-offs of ${civ} over time`}
                emptyText={`No finance record for ${civ}.`}
                onSeek={onSeek}
              />
              {lossesSoFar.length === 0 ? (
                <div className="phase75-empty-state">No default or write-off on the debts of {civ} by turn {currentTurn}.</div>
              ) : (
                <div className="systems-table-wrap">
                  <table className="systems-table" aria-label={`Defaults and write-offs of ${civ}`}>
                    <thead>
                      <tr><th>Turn</th><th>Written off</th><th>What</th></tr>
                    </thead>
                    <tbody>
                      {lossesSoFar.map((loss) => (
                        <tr key={loss.turn}>
                          <td>{loss.events.length > 0 ? loss.events[0].turn : `by ${loss.turn}`}</td>
                          <td>{loss.amount ?? "-"}</td>
                          <td>
                            {loss.events.length > 0 ? loss.events.map((event, index) => (
                              <button
                                key={event.event_id ?? index}
                                type="button"
                                className="systems-link debt-event-link"
                                onClick={() => onSelectEvent(event)}
                              >
                                {event.description}
                              </button>
                            )) : (loss.defaulted ? "Default" : "Claims lost or lapsed")}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </div>

          <SystemEventList
            events={events}
            label={`Credit events of ${civ}`}
            emptyText={`No loan, default or debasement of ${civ} by turn ${currentTurn}.`}
            onSelectEvent={onSelectEvent}
          />
        </section>
      )}
    </>
  );
}
