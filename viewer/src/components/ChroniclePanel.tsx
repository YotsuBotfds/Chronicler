import { useEffect, useRef } from "react";
import type { BundleChronicle, GapSummary, NewChronicleEntry } from "../types";
import { isLegacyBundle } from "../types";

interface ChroniclePanelProps {
  chronicleEntries: BundleChronicle;
  gapSummaries?: GapSummary[];
  eraReflections: Record<string, string>;
  currentTurn: number;
  maxTurn: number;
  focusedSegment?: { type: "narrated" | "mechanical" | "reflection"; index: number } | null;
}

const ROLE_LABELS: Record<string, string> = {
  inciting: "Inciting",
  escalation: "Escalation",
  climax: "Climax",
  resolution: "Resolution",
  coda: "Coda",
};

/** Render a single new-format chronicle entry. */
function NarratedSegment({ entry }: { entry: NewChronicleEntry }) {
  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2">
        <span className="text-xs font-mono text-gray-500">
          Turns {entry.covers_turns[0]}-{entry.covers_turns[1]}
        </span>
        <span className="text-xs px-1.5 py-0.5 rounded bg-gray-700 text-gray-300">
          {ROLE_LABELS[entry.narrative_role] ?? entry.narrative_role}
        </span>
      </div>
      <p className="text-gray-200 leading-relaxed whitespace-pre-wrap">
        {entry.narrative}
      </p>
      {entry.events.length > 0 && (
        <details className="text-xs text-gray-400">
          <summary className="cursor-pointer hover:text-gray-300">
            {entry.events.length} event{entry.events.length !== 1 ? "s" : ""}
          </summary>
          <ul className="mt-1 space-y-0.5 pl-3">
            {entry.events.map((ev, i) => (
              <li key={i}>
                <span className="text-gray-500">T{ev.turn}</span>{" "}
                {ev.description}
              </li>
            ))}
          </ul>
        </details>
      )}
      {entry.causal_links.length > 0 && (
        <details className="text-xs text-gray-400">
          <summary className="cursor-pointer hover:text-gray-300">
            {entry.causal_links.length} causal link{entry.causal_links.length !== 1 ? "s" : ""}
          </summary>
          <ul className="mt-1 space-y-0.5 pl-3">
            {entry.causal_links.map((link, i) => (
              <li key={i}>
                T{link.cause_turn} ({link.cause_event_type}) &rarr; T{link.effect_turn} ({link.effect_event_type}): {link.pattern}
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}

/** Render a mechanical gap summary. */
function MechanicalSegment({ gap }: { gap: GapSummary }) {
  const deltaEntries = Object.entries(gap.stat_deltas);
  return (
    <div className="space-y-1">
      <div className="flex items-center gap-2">
        <span className="text-xs font-mono text-gray-500">
          Turns {gap.turn_range[0]}-{gap.turn_range[1]}
        </span>
        <span className="text-xs px-1.5 py-0.5 rounded bg-gray-800 text-gray-500">
          Mechanical
        </span>
      </div>
      <p className="text-sm text-gray-400">
        {gap.event_count} event{gap.event_count !== 1 ? "s" : ""} (top type: {gap.top_event_type})
        {gap.territory_changes > 0 && `, ${gap.territory_changes} territory change${gap.territory_changes !== 1 ? "s" : ""}`}
      </p>
      {deltaEntries.length > 0 && (
        <details className="text-xs text-gray-500">
          <summary className="cursor-pointer hover:text-gray-400">
            Stat changes
          </summary>
          <ul className="mt-1 pl-3 space-y-0.5">
            {deltaEntries.map(([civ, deltas]) => (
              <li key={civ}>
                <span className="text-gray-400">{civ}:</span>{" "}
                {Object.entries(deltas)
                  .map(([stat, val]) => `${stat} ${val >= 0 ? "+" : ""}${val}`)
                  .join(", ")}
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}

export function ChroniclePanel({
  chronicleEntries,
  gapSummaries,
  eraReflections,
  currentTurn,
  maxTurn,
  focusedSegment,
}: ChroniclePanelProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const turnRefs = useRef<Map<number, HTMLDivElement>>(new Map());
  const segmentRefs = useRef<Map<string, HTMLDivElement>>(new Map());

  useEffect(() => {
    if (focusedSegment) {
      const key = `${focusedSegment.type}-${focusedSegment.index}`;
      const el = segmentRefs.current.get(key);
      if (el) {
        el.scrollIntoView({ behavior: "smooth", block: "start" });
        return;
      }
    }
    const el = turnRefs.current.get(currentTurn);
    if (el) {
      el.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }, [currentTurn, focusedSegment]);

  // --- Legacy rendering path ---
  if (isLegacyBundle(chronicleEntries)) {
    const turns = Array.from({ length: maxTurn }, (_, i) => i + 1);

    return (
      <div ref={containerRef} className="overflow-y-auto h-full p-4 space-y-4">
        {turns.map((turn) => {
          const entry = chronicleEntries[String(turn)];
          const reflection = eraReflections[String(turn)];
          if (!entry && !reflection) return null;

          return (
            <div
              key={turn}
              ref={(el) => {
                if (el) turnRefs.current.set(turn, el);
              }}
              className={`${
                turn === currentTurn
                  ? "border-l-2 border-blue-400 pl-3"
                  : "pl-4 opacity-60"
              }`}
            >
              {reflection && (
                <div className="mb-3 p-3 bg-gray-800 rounded border border-gray-600 text-sm text-gray-300 whitespace-pre-wrap">
                  {reflection}
                </div>
              )}
              {entry && (
                <div>
                  <span className="text-xs text-gray-500 font-mono">
                    Turn {turn}
                  </span>
                  <p className="text-gray-200 leading-relaxed whitespace-pre-wrap">
                    {entry}
                  </p>
                </div>
              )}
            </div>
          );
        })}
      </div>
    );
  }

  // --- New format rendering path ---
  const entries = chronicleEntries;
  const gaps = gapSummaries ?? [];

  // Build interleaved list: narrated entries, gap summaries, and era reflections
  type Item =
    | { kind: "narrated"; entry: NewChronicleEntry; idx: number }
    | { kind: "mechanical"; gap: GapSummary; idx: number }
    | { kind: "reflection"; turn: number; text: string; idx: number };

  const items: Item[] = [];

  entries.forEach((entry, idx) => {
    items.push({ kind: "narrated", entry, idx });
  });

  gaps.forEach((gap, idx) => {
    items.push({ kind: "mechanical", gap, idx });
  });

  // Add era reflections as standalone items
  let reflectionIdx = 0;
  for (const [turnStr, text] of Object.entries(eraReflections)) {
    items.push({ kind: "reflection", turn: Number(turnStr), text, idx: reflectionIdx++ });
  }

  // Sort by start turn
  items.sort((a, b) => {
    const turnA = a.kind === "narrated" ? a.entry.covers_turns[0]
      : a.kind === "mechanical" ? a.gap.turn_range[0]
      : a.turn;
    const turnB = b.kind === "narrated" ? b.entry.covers_turns[0]
      : b.kind === "mechanical" ? b.gap.turn_range[0]
      : b.turn;
    return turnA - turnB;
  });

  return (
    <div ref={containerRef} className="overflow-y-auto h-full p-4 space-y-4">
      {items.map((item, i) => {
        const key = `${item.kind}-${item.idx}`;
        const isFocused =
          focusedSegment &&
          focusedSegment.type === item.kind &&
          focusedSegment.index === item.idx;

        return (
          <div
            key={`${item.kind}-${i}`}
            ref={(el) => {
              if (el) segmentRefs.current.set(key, el);
            }}
            className={`${
              isFocused
                ? "border-l-2 border-blue-400 pl-3"
                : "pl-4 opacity-70"
            }`}
          >
            {item.kind === "reflection" && (
              <div className="mb-3 p-3 bg-gray-800 rounded border border-gray-600 text-sm text-gray-300 whitespace-pre-wrap">
                {item.text}
              </div>
            )}
            {item.kind === "narrated" && <NarratedSegment entry={item.entry} />}
            {item.kind === "mechanical" && <MechanicalSegment gap={item.gap} />}
          </div>
        );
      })}
    </div>
  );
}
