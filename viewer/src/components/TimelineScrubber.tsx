import { useMemo, useCallback, useRef } from "react";
import type { NamedEvent, TurnSnapshot } from "../types";
import type { TechEra } from "../types";
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
}

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
              style={{ left: `${((turn - 1) / Math.max(maxTurn - 1, 1)) * 100}%` }}
            >
              <span className="absolute -top-4 text-[10px] text-gray-400 -translate-x-1/2">
                {ERA_LABELS[era]}
              </span>
            </div>
          ))}

          {/* Event dots */}
          {eventDots.map((ev) => (
            <div
              key={`${ev.turn}-${ev.name}`}
              className="absolute top-1/2 -translate-y-1/2 w-2 h-2 rounded-full bg-amber-400 hover:bg-amber-300"
              style={{
                left: `${((ev.turn - 1) / Math.max(maxTurn - 1, 1)) * 100}%`,
              }}
              title={`${ev.name} (Turn ${ev.turn})`}
            />
          ))}

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
