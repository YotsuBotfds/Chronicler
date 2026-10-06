import { useId, useLayoutEffect, useRef, useState } from "react";
import type { Event } from "../../types";
import { buildEventLedger, EVENT_LEDGER_PAGE_SIZE } from "../../lib/eventLedger";
import "./app-shell.css";

export interface GroupedEventLedgerProps {
  events: readonly Event[];
  currentTurn: number;
  /** External map focus; changes reset the local query. */
  selectedCivilization?: string | null;
  /** Supply exported civilization names; otherwise names come from visible actors. */
  civilizations?: readonly string[];
  /** Use an external shared selector; Reset filters keeps its actor scope. */
  lockCivilization?: boolean;
  pageSize?: number;
  onSelectEvent?: (event: Event, sourceIndex: number) => void;
}

const controlStyle = { padding: "8px", borderRadius: "8px", border: "1px solid var(--phase75-edge-strong)",
  background: "var(--phase75-bg)", color: "var(--phase75-ink)", width: "100%", minWidth: 0 };
// Empty turn fields rely on their boundary to identify the editable area.
const turnControlStyle = { ...controlStyle, borderColor: "var(--phase75-gold)" };

/** Standalone, static-artifact ledger. Mount only after the production gate opens.
 * Use an artifact key when replacing the source array to reset local UI state.
 */
export function GroupedEventLedger(props: GroupedEventLedgerProps) {
  // A map-focus change also cancels an interrupted local query or expansion.
  return <LedgerQuery key={JSON.stringify([props.selectedCivilization ?? null])} {...props} />;
}

function LedgerQuery({ events, currentTurn, selectedCivilization, civilizations, lockCivilization = false, pageSize = EVENT_LEDGER_PAGE_SIZE,
  onSelectEvent }: GroupedEventLedgerProps) {
  const id = useId();
  const [eventType, setEventType] = useState<string | null>(null);
  const [civilization, setCivilization] = useState<string | null>(selectedCivilization ?? null);
  const [fromTurn, setFromTurn] = useState("");
  const [throughTurn, setThroughTurn] = useState("");
  const queryKey = JSON.stringify([eventType, civilization, fromTurn, throughTurn, currentTurn, pageSize]);
  const [position, setPosition] = useState({ queryKey, page: 1 });
  if (position.queryKey !== queryKey) {
    setPosition({ queryKey, page: 1 });
  }
  const result = buildEventLedger(events, { currentTurn, eventTypes: eventType === null ? [] : [eventType],
    civilization, fromTurn: fromTurn === "" ? undefined : Number(fromTurn),
    throughTurn: throughTurn === "" ? undefined : Number(throughTurn), pageSize,
    page: position.queryKey === queryKey ? position.page : 1 });
  if (position.queryKey === queryKey && position.page !== result.page) {
    setPosition({ queryKey, page: result.page });
  }
  const previousButton = useRef<HTMLButtonElement>(null);
  const nextButton = useRef<HTMLButtonElement>(null);
  const pendingFocus = useRef<"previous" | "next" | null>(null);
  useLayoutEffect(() => {
    if (pendingFocus.current) {
      (pendingFocus.current === "previous" ? previousButton : nextButton).current?.focus();
      pendingFocus.current = null;
    }
  }, [result.page]);
  // Keep native controls mounted so keyboard focus survives pagination/filtering.
  const visibleEvents = events.filter(event => event.turn <= currentTurn);
  const types = [...new Set([...visibleEvents.map(event => event.event_type), ...(eventType === null ? [] : [eventType])])].sort();
  const civs = [...new Set([...(civilizations ?? visibleEvents.flatMap(event => event.actors ?? [])),
    ...(civilization === null ? [] : [civilization])])].sort();
  function reset() {
    setEventType(null); setCivilization(selectedCivilization ?? null); setFromTurn(""); setThroughTurn("");
    setPosition({ queryKey: "", page: 1 });
  }
  return <section aria-labelledby={`${id}-title`} className="phase75-panel" style={{ padding: 16, minWidth: 0 }}>
    <h2 id={`${id}-title`} style={{ fontFamily: "var(--phase75-serif)", marginTop: 0 }}>Event ledger</h2>
    <p className="phase75-detail-copy">Recorded events through turn {currentTurn}. Civilization matches exported actor names.
      General entity IDs are unavailable in this event format.</p>
    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))", gap: 12 }}>
      <div><label htmlFor={`${id}-type`}>Event type</label><select id={`${id}-type`} style={controlStyle}
        value={eventType === null ? "" : JSON.stringify(eventType)}
        onChange={e => setEventType(e.target.value === "" ? null : JSON.parse(e.target.value) as string)}>
        <option value="">All types</option>{types.map(type => <option key={type} value={JSON.stringify(type)}>{type || "Unspecified type"}</option>)}
      </select></div>
      <div><label htmlFor={`${id}-civ`}>Civilization</label><select id={`${id}-civ`} style={controlStyle}
        disabled={lockCivilization}
        value={civilization === null ? "" : JSON.stringify(civilization)}
        onChange={e => setCivilization(e.target.value === "" ? null : JSON.parse(e.target.value) as string)}>
        <option value="">All civilizations</option>{civs.map(civ => <option key={civ} value={JSON.stringify(civ)}>{civ || "Empty actor name"}</option>)}
      </select></div>
      <div><label htmlFor={`${id}-from`}>From turn</label><input id={`${id}-from`} style={turnControlStyle} type="number" min={0} step={1} value={fromTurn}
        aria-invalid={!result.validRange} aria-describedby={!result.validRange ? `${id}-range` : undefined}
        onChange={e => setFromTurn(e.target.value)} /></div>
      <div><label htmlFor={`${id}-through`}>Through turn</label><input id={`${id}-through`} style={turnControlStyle} type="number" min={0} step={1} value={throughTurn}
        aria-invalid={!result.validRange} aria-describedby={!result.validRange ? `${id}-range` : undefined}
        onChange={e => setThroughTurn(e.target.value)} /></div>
    </div>
    <button className="phase75-ghost-button" type="button" onClick={reset} style={{ marginTop: 12 }}>Reset filters</button>
    {!result.validRange && <p role="alert" id={`${id}-range`}>Choose nonnegative whole turns with From turn no later than Through turn.</p>}
    <p role="status" aria-live="polite" aria-atomic="true">{result.start}–{result.end} of {result.total} events · Page {result.page} of {result.pageCount}</p>
    {result.total === 0 && <p className="phase75-empty-state">No events match these filters through the current turn.</p>}
    <div className="phase75-feed" key={`${queryKey}:${result.page}`}>
      {result.groups.map((group, groupIndex) => <EventGroup key={group.key} group={group}
        id={`${id}-group-${groupIndex}`} onSelectEvent={onSelectEvent} />)}
    </div>
    <nav aria-label="Event ledger pages" style={{ display: "flex", flexWrap: "wrap", gap: 12, marginTop: 16 }}>
      <button ref={previousButton} type="button" className="phase75-ghost-button" disabled={result.page <= 1}
        onClick={e => {
          if (result.page === 2 && document.activeElement === e.currentTarget) pendingFocus.current = "next";
          setPosition({ queryKey, page: result.page - 1 });
        }}>Previous events</button>
      <button ref={nextButton} type="button" className="phase75-ghost-button" disabled={result.page >= result.pageCount}
        onClick={e => {
          if (result.page === result.pageCount - 1 && document.activeElement === e.currentTarget) pendingFocus.current = "previous";
          setPosition({ queryKey, page: result.page + 1 });
        }}>Next events</button>
    </nav>
  </section>;
}

function EventGroup({ group, id, onSelectEvent }: { group: ReturnType<typeof buildEventLedger>["groups"][number];
  id: string; onSelectEvent: GroupedEventLedgerProps["onSelectEvent"] }) {
  const [expanded, setExpanded] = useState(false);
  const grouped = group.entries.length > 1;
  return <div className="phase75-feed-card" style={{ overflowWrap: "anywhere" }}>
    {grouped ? <button type="button" className="phase75-section-toggle" aria-expanded={expanded} aria-controls={id}
      onClick={() => setExpanded(value => !value)}>
      Turn {group.turn} · {group.eventType || "Unspecified type"} · {group.entries.length} events on this page
    </button> : <h3 style={{ marginTop: 0 }}>Turn {group.turn} · {group.eventType || "Unspecified type"}</h3>}
    <ol id={id} hidden={grouped && !expanded} aria-label={`Turn ${group.turn} ${group.eventType} records`}
      style={{ paddingLeft: 24, marginBottom: 0 }}>
      {group.entries.map(({ event, sourceIndex }) => <li key={sourceIndex} data-source-index={sourceIndex} style={{ marginBlock: 12 }}>
        <p style={{ marginBlock: 4 }}>{event.description || "No description recorded."}</p>
        <p className="phase75-detail-copy" style={{ marginBlock: 4 }}>
          Actors: {(event.actors ?? []).length ? event.actors.join(" · ") : "No actors recorded."} · Importance: {event.importance}
        </p>
        {event.consequences.length > 0 && <ul aria-label="Recorded consequences">
          {event.consequences.map((consequence, index) => <li key={index}>{consequence}</li>)}
        </ul>}
        <small className="phase75-detail-copy">Source event #{sourceIndex + 1}</small>
        {onSelectEvent && <button type="button" className="phase75-ghost-button" style={{ marginLeft: 8 }}
          onClick={() => onSelectEvent(event, sourceIndex)}>Inspect source event #{sourceIndex + 1}</button>}
      </li>)}
    </ol>
  </div>;
}
