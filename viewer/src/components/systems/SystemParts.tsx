import { useState } from "react";
import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { Event } from "../../types";
import type { SeriesRow, StripRow } from "../../lib/systems";
import { humanize } from "../../lib/systems";

const STRIP_ROW_LIMIT = 24;

/**
 * Rows of run-length segments over the recorded turns. Each segment carries
 * its own title (hover); clicking the track seeks the timeline.
 */
export function TurnStrip({
  rows,
  firstTurn,
  endTurn,
  currentTurn,
  label,
  emptyText,
  onSeek,
  onSelectRow,
  isRowSelected,
}: {
  rows: StripRow[];
  firstTurn: number;
  /** Turn after the last recorded one. */
  endTurn: number;
  currentTurn: number;
  label: string;
  emptyText: string;
  onSeek?: (turn: number) => void;
  onSelectRow?: (row: StripRow) => void;
  isRowSelected?: (row: StripRow) => boolean;
}) {
  const [expanded, setExpanded] = useState(false);
  if (rows.length === 0) {
    return <div className="phase75-empty-state">{emptyText}</div>;
  }
  const span = Math.max(1, endTurn - firstTurn);
  const visible = expanded ? rows : rows.slice(0, STRIP_ROW_LIMIT);
  const percent = (turn: number) => `${((Math.min(Math.max(turn, firstTurn), endTurn) - firstTurn) / span) * 100}%`;
  const width = (start: number, end: number) => `${Math.max(0.35, ((end - start) / span) * 100)}%`;
  const seekFrom = (event: React.MouseEvent<HTMLDivElement>) => {
    if (!onSeek) {
      return;
    }
    const rect = event.currentTarget.getBoundingClientRect();
    const fraction = rect.width > 0 ? (event.clientX - rect.left) / rect.width : 0;
    onSeek(Math.min(endTurn - 1, Math.max(firstTurn, firstTurn + Math.floor(fraction * span))));
  };

  return (
    <div className="systems-strip" role="group" aria-label={label}>
      {visible.map((row) => (
        <div key={row.id} className={`systems-strip-row${isRowSelected?.(row) ? " active" : ""}`}>
          {onSelectRow ? (
            <button type="button" className="systems-strip-label" onClick={() => onSelectRow(row)} title={row.label}>
              {row.swatch && <span className="phase75-civ-swatch" style={{ backgroundColor: row.swatch }} />}
              <span>{row.label}</span>
            </button>
          ) : (
            <span className="systems-strip-label" title={row.label}>
              {row.swatch && <span className="phase75-civ-swatch" style={{ backgroundColor: row.swatch }} />}
              <span>{row.label}</span>
            </span>
          )}
          <div
            className={`systems-strip-track${onSeek ? " interactive" : ""}`}
            role="img"
            aria-label={`${row.label}: ${row.segments.map((segment) => segment.label).join("; ") || "nothing recorded"}`}
            onClick={seekFrom}
          >
            {row.segments.map((segment) => (
              <div
                key={`${segment.start}-${segment.color}`}
                className={`systems-strip-segment${row.marks ? " with-marks" : ""}`}
                style={{
                  left: percent(segment.start),
                  width: width(segment.start, segment.end),
                  backgroundColor: segment.color,
                  color: segment.textColor,
                }}
                title={segment.label}
              >
                {segment.text && (segment.end - segment.start) / span >= 0.08 ? segment.text : null}
              </div>
            ))}
            {row.marks?.map((mark) => (
              <div
                key={`mark-${mark.start}`}
                className="systems-strip-mark"
                style={{ left: percent(mark.start), width: width(mark.start, mark.end), backgroundColor: mark.color }}
                title={mark.label}
              />
            ))}
            <div className="systems-strip-cursor" style={{ left: percent(currentTurn) }} />
          </div>
        </div>
      ))}
      <div className="systems-strip-axis" aria-hidden="true">
        <span />
        <div>
          <span>T{firstTurn}</span>
          <span>T{endTurn - 1}</span>
        </div>
      </div>
      {rows.length > STRIP_ROW_LIMIT && (
        <button type="button" className="phase75-ghost-button systems-more" onClick={() => setExpanded(!expanded)}>
          {expanded ? "Show fewer rows" : `Show all ${rows.length} rows`}
        </button>
      )}
    </div>
  );
}

export function StripLegend({ items }: { items: Array<{ label: string; color: string; mark?: boolean }> }) {
  return (
    <div className="systems-legend" aria-label="Legend">
      {items.map((item) => (
        <span key={item.label} className="systems-legend-item">
          <span className={item.mark ? "systems-legend-mark" : "phase75-civ-swatch"} style={{ backgroundColor: item.color }} />
          {item.label}
        </span>
      ))}
    </div>
  );
}

const EVENT_PAGE = 30;

/** System events as the shell's event rows; selecting one pins it in the inspector (Because / Led to). */
export function SystemEventList({
  events,
  label,
  emptyText,
  onSelectEvent,
}: {
  events: Event[];
  label: string;
  emptyText: string;
  onSelectEvent: (event: Event) => void;
}) {
  const [limit, setLimit] = useState(EVENT_PAGE);
  if (events.length === 0) {
    return <div className="phase75-empty-state">{emptyText}</div>;
  }
  return (
    <div className="systems-events" role="list" aria-label={label}>
      {events.slice(0, limit).map((event, index) => (
        <button
          key={event.event_id ?? `${event.turn}-${event.event_type}-${index}`}
          type="button"
          role="listitem"
          className="phase75-event-row"
          onClick={() => onSelectEvent(event)}
        >
          <div className="phase75-event-turn">T{event.turn}</div>
          <div className="phase75-event-copy">
            <strong>{humanize(event.event_type)}</strong>
            <span>{event.description}</span>
          </div>
          <div className="phase75-event-importance">{event.importance}</div>
        </button>
      ))}
      {events.length > limit && (
        <button type="button" className="phase75-ghost-button systems-more" onClick={() => setLimit(limit + EVENT_PAGE)}>
          Show {Math.min(EVENT_PAGE, events.length - limit)} more of {events.length - limit}
        </button>
      )}
    </div>
  );
}

export function CivLegend({ civs, color }: { civs: string[]; color: (civ: string) => string }) {
  return <StripLegend items={civs.map((civ) => ({ label: civ, color: color(civ) }))} />;
}

const TOOLTIP_STYLE = {
  backgroundColor: "#1f2937",
  border: "1px solid #374151",
  borderRadius: "4px",
  fontSize: "12px",
};

/** One measure per chart (no second axis), one line per civilization, the scrubbed turn marked. */
export function CivLineChart({
  data,
  civs,
  color,
  currentTurn,
  label,
  step = false,
  format,
}: {
  data: SeriesRow[];
  civs: string[];
  color: (civ: string) => string;
  currentTurn: number;
  label: string;
  step?: boolean;
  format?: (value: number) => string;
}) {
  return (
    <figure className="systems-chart" aria-label={label}>
      <figcaption>{label}</figcaption>
      <ResponsiveContainer width="100%" height={210}>
        <LineChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: -8 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
          <XAxis dataKey="turn" type="number" domain={["dataMin", "dataMax"]} stroke="#6b7280" tick={{ fontSize: 10 }} />
          <YAxis stroke="#6b7280" tick={{ fontSize: 10 }} allowDecimals={!step} />
          <Tooltip
            contentStyle={TOOLTIP_STYLE}
            labelFormatter={(turn) => `Turn ${turn}`}
            formatter={(value) => (typeof value === "number" && format ? format(value) : value)}
          />
          <ReferenceLine x={currentTurn} stroke="#7ebec3" strokeWidth={2} />
          {civs.map((civ) => (
            <Line
              key={civ}
              type={step ? "stepAfter" : "monotone"}
              dataKey={civ}
              name={civ}
              stroke={color(civ)}
              strokeWidth={2}
              dot={false}
              connectNulls={false}
              isAnimationActive={false}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </figure>
  );
}

export function StatTile({ label, value, detail }: { label: string; value: string | number; detail?: string }) {
  return (
    <div className="systems-tile">
      <span className="phase75-overline">{label}</span>
      <strong>{value}</strong>
      {detail && <small>{detail}</small>}
    </div>
  );
}
