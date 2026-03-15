import { useMemo, useCallback, useRef } from "react";
import type { NamedEvent, TurnSnapshot, BundleChronicle, GapSummary, NewChronicleEntry } from "../types";
import type { TechEra } from "../types";
import { isLegacyBundle } from "../types";
import { ERA_LABELS, ERA_ORDER } from "../lib/format";

interface TimelineScrubberProps {
  currentTurn: number;
  maxTurn: number;
  playing: boolean;
  speed: number;
  history: TurnSnapshot[];
  namedEvents: NamedEvent[];
  onSeek: (turn: number) => void;
  onPlay: () => void;
  onPause: () => void;
  onSetSpeed: (speed: number) => void;
  followMode?: boolean;
  onToggleFollowMode?: () => void;
  // M20a: segmented timeline props
  chronicleEntries?: BundleChronicle;
  gapSummaries?: GapSummary[];
  onNarrateRange?: (startTurn: number, endTurn: number) => void;
  showCausalLinks?: boolean;
}

const ROLE_COLORS: Record<string, string> = {
  inciting: "#3b82f6",    // blue
  escalation: "#f97316",  // orange
  climax: "#ef4444",      // red
  resolution: "#22c55e",  // green
  coda: "#9ca3af",        // gray
};

/** Find the first turn any civ reaches each era. */
function computeEraBoundaries(
  history: TurnSnapshot[],
): { turn: number; era: TechEra }[] {
  const seen = new Set<TechEra>();
  const boundaries: { turn: number; era: TechEra }[] = [];
  for (const snap of history) {
    for (const civ of Object.values(snap.civ_stats)) {
      if (!seen.has(civ.tech_era)) {
        seen.add(civ.tech_era);
        boundaries.push({ turn: snap.turn, era: civ.tech_era });
      }
    }
  }
  return boundaries.sort(
    (a, b) => ERA_ORDER.indexOf(a.era) - ERA_ORDER.indexOf(b.era),
  );
}

/** Pick top N events by importance that fit without overlapping. */
function selectEventDots(
  events: NamedEvent[],
  maxTurn: number,
  maxDots: number,
): NamedEvent[] {
  const sorted = [...events].sort((a, b) => b.importance - a.importance);
  const used: number[] = [];
  const minGap = maxTurn * 0.02;
  const selected: NamedEvent[] = [];

  for (const ev of sorted) {
    if (selected.length >= maxDots) break;
    const tooClose = used.some((t) => Math.abs(t - ev.turn) < minGap);
    if (!tooClose) {
      selected.push(ev);
      used.push(ev.turn);
    }
  }
  return selected;
}

type Segment =
  | { kind: "narrated"; entry: NewChronicleEntry; startTurn: number; endTurn: number }
  | { kind: "mechanical"; gap: GapSummary; startTurn: number; endTurn: number };

/** Build ordered segments from chronicle entries and gap summaries. */
function buildSegments(
  entries: NewChronicleEntry[],
  gaps: GapSummary[],
): Segment[] {
  const segments: Segment[] = [];
  for (const entry of entries) {
    segments.push({
      kind: "narrated",
      entry,
      startTurn: entry.covers_turns[0],
      endTurn: entry.covers_turns[1],
    });
  }
  for (const gap of gaps) {
    segments.push({
      kind: "mechanical",
      gap,
      startTurn: gap.turn_range[0],
      endTurn: gap.turn_range[1],
    });
  }
  segments.sort((a, b) => a.startTurn - b.startTurn);
  return segments;
}

export function TimelineScrubber({
  currentTurn,
  maxTurn,
  playing,
  speed,
  history,
  namedEvents,
  onSeek,
  onPlay,
  onPause,
  onSetSpeed,
  followMode,
  onToggleFollowMode,
  chronicleEntries,
  gapSummaries,
  onNarrateRange,
  showCausalLinks,
}: TimelineScrubberProps) {
  const trackRef = useRef<HTMLDivElement>(null);

  const eraBoundaries = useMemo(
    () => computeEraBoundaries(history),
    [history],
  );

  const eventDots = useMemo(
    () => selectEventDots(namedEvents, maxTurn, 20),
    [namedEvents, maxTurn],
  );

  const handleTrackClick = useCallback(
    (e: React.MouseEvent<HTMLDivElement>) => {
      if (!trackRef.current) return;
      const rect = trackRef.current.getBoundingClientRect();
      const pct = (e.clientX - rect.left) / rect.width;
      onSeek(Math.round(pct * maxTurn) || 1);
    },
    [maxTurn, onSeek],
  );

  const pct = ((currentTurn - 1) / Math.max(maxTurn - 1, 1)) * 100;

  const useSegmented = chronicleEntries !== undefined && !isLegacyBundle(chronicleEntries);

  const segments = useMemo(() => {
    if (!useSegmented || !chronicleEntries || isLegacyBundle(chronicleEntries)) return [];
    return buildSegments(chronicleEntries, gapSummaries ?? []);
  }, [useSegmented, chronicleEntries, gapSummaries]);

  // Build causal link arcs for SVG overlay
  const causalArcs = useMemo(() => {
    if (!showCausalLinks || !useSegmented || !chronicleEntries || isLegacyBundle(chronicleEntries)) return [];
    const arcs: { causeTurn: number; effectTurn: number; pattern: string }[] = [];
    for (const entry of chronicleEntries) {
      for (const link of entry.causal_links) {
        arcs.push({
          causeTurn: link.cause_turn,
          effectTurn: link.effect_turn,
          pattern: link.pattern,
        });
      }
    }
    return arcs;
  }, [showCausalLinks, useSegmented, chronicleEntries]);

  const turnToPct = (turn: number) =>
    ((turn - 1) / Math.max(maxTurn - 1, 1)) * 100;

  return (
    <div className="px-4 py-2 bg-gray-800 border-b border-gray-700">
      <div className="flex items-center gap-3">
        <button
          onClick={playing ? onPause : onPlay}
          className="px-3 py-1 rounded bg-gray-700 hover:bg-gray-600 text-gray-200 text-sm font-mono w-12"
        >
          {playing ? "||" : ">"}
        </button>
        <select
          value={speed}
          onChange={(e) => onSetSpeed(Number(e.target.value))}
          className="bg-gray-700 text-gray-200 text-sm rounded px-2 py-1"
        >
          {[1, 2, 5, 10].map((s) => (
            <option key={s} value={s}>
              {s}x
            </option>
          ))}
        </select>

        <div
          ref={trackRef}
          onClick={handleTrackClick}
          className="relative flex-1 h-8 bg-gray-700 rounded cursor-pointer"
        >
          {/* Era boundaries */}
          {eraBoundaries.map(({ turn, era }) => (
            <div
              key={era}
              className="absolute top-0 h-full border-l border-gray-500"
              style={{ left: `${turnToPct(turn)}%` }}
            >
              <span className="absolute -top-4 text-[10px] text-gray-400 -translate-x-1/2">
                {ERA_LABELS[era]}
              </span>
            </div>
          ))}

          {useSegmented ? (
            <>
              {/* Segmented bar */}
              {segments.map((seg, idx) => {
                const left = turnToPct(seg.startTurn);
                const right = turnToPct(seg.endTurn);
                const width = right - left;
                if (width <= 0) return null;

                if (seg.kind === "narrated") {
                  const color = ROLE_COLORS[seg.entry.narrative_role] ?? "#6b7280";
                  return (
                    <div
                      key={`seg-${idx}`}
                      className="absolute top-1 bottom-1 rounded-sm opacity-80 hover:opacity-100"
                      style={{
                        left: `${left}%`,
                        width: `${width}%`,
                        backgroundColor: color,
                      }}
                      title={`${seg.entry.narrative_role} (Turns ${seg.startTurn}-${seg.endTurn})`}
                    />
                  );
                } else {
                  return (
                    <div
                      key={`seg-${idx}`}
                      className="absolute top-1 bottom-1 rounded-sm bg-gray-600 opacity-60 hover:opacity-90 group"
                      style={{
                        left: `${left}%`,
                        width: `${width}%`,
                      }}
                      title={`Mechanical (Turns ${seg.startTurn}-${seg.endTurn}, ${seg.gap.event_count} events)`}
                    >
                      {onNarrateRange && (
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            onNarrateRange(seg.startTurn, seg.endTurn);
                          }}
                          className="absolute inset-0 flex items-center justify-center text-[9px] text-gray-300 opacity-0 group-hover:opacity-100 bg-gray-700/70 rounded-sm"
                        >
                          Narrate
                        </button>
                      )}
                    </div>
                  );
                }
              })}

              {/* Causal link arcs */}
              {showCausalLinks && causalArcs.length > 0 && (
                <svg className="absolute inset-0 w-full h-full pointer-events-none overflow-visible">
                  {causalArcs.map((arc, i) => {
                    const x1 = turnToPct(arc.causeTurn);
                    const x2 = turnToPct(arc.effectTurn);
                    const midX = (x1 + x2) / 2;
                    const arcHeight = Math.min(Math.abs(x2 - x1) * 0.4, 20);
                    return (
                      <path
                        key={`arc-${i}`}
                        d={`M ${x1}% 50% Q ${midX}% ${50 - arcHeight}% ${x2}% 50%`}
                        fill="none"
                        stroke="#a78bfa"
                        strokeWidth="1.5"
                        strokeDasharray="3 2"
                        opacity="0.6"
                      >
                        <title>{arc.pattern}</title>
                      </path>
                    );
                  })}
                </svg>
              )}
            </>
          ) : (
            <>
              {/* Legacy: Event dots */}
              {eventDots.map((ev) => (
                <div
                  key={`${ev.turn}-${ev.name}`}
                  className="absolute top-1/2 -translate-y-1/2 w-2 h-2 rounded-full bg-amber-400 hover:bg-amber-300"
                  style={{
                    left: `${turnToPct(ev.turn)}%`,
                  }}
                  title={`${ev.name} (Turn ${ev.turn})`}
                />
              ))}
            </>
          )}

          {/* Thumb */}
          <div
            className="absolute top-0 h-full w-1 bg-blue-400 rounded"
            style={{ left: `${pct}%` }}
          />
        </div>

        <span className="text-sm font-mono text-gray-300 w-10 text-right">
          {currentTurn}
        </span>
        {followMode !== undefined && onToggleFollowMode && (
          <button
            onClick={onToggleFollowMode}
            className={`px-2 py-1 rounded text-xs ${
              followMode
                ? "bg-green-700 text-green-200"
                : "bg-gray-700 text-gray-400 hover:text-gray-200"
            }`}
            title={followMode ? "Following latest turn" : "Click to follow latest turn"}
          >
            {followMode ? "Following" : "Follow"}
          </button>
        )}
      </div>
    </div>
  );
}
