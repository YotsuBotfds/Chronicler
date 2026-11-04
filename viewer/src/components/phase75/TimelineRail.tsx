/**
 * The shell's timeline rail: the flow ladder, playback controls, the turn
 * slider (keyboard and pointer seeks, bounded by a live session's latest
 * turn) with its whole-run marks and the playhead. Presentation only:
 * AppShell owns the turn, playback and the track's seek handler.
 */
import { memo, useMemo } from "react";
import type { Bundle } from "../../types";
import { LiveInspectionControls } from "../LiveInspectionControls";
import { turnToPercent } from "./appShellHelpers";
import type { AppSurface, LiveTimelineControls } from "./appShellTypes";

const SPEED_OPTIONS = [1, 2, 5, 10];

export function TimelineRail({
  surface,
  flowSteps,
  currentTurn,
  totalTurns,
  bundle,
  eraBands,
  narratedSpans,
  namedEvents,
  trackRef,
  onTrackSeek,
  playing,
  speed,
  onPlay,
  onPause,
  onSetSpeed,
  liveTimeline,
  onSeek,
}: {
  onSeek: (turn: number) => void;
  liveTimeline?: LiveTimelineControls;
  surface: AppSurface;
  flowSteps: { surface: AppSurface; label: string; index: string }[];
  currentTurn: number;
  totalTurns: number;
  bundle: Bundle | null;
  eraBands: { label: string; start: number; end: number }[];
  narratedSpans: { start: number; end: number }[];
  namedEvents: Bundle["named_events"];
  trackRef: React.RefObject<HTMLDivElement | null>;
  onTrackSeek: (event: React.MouseEvent<HTMLDivElement>) => void;
  playing: boolean;
  speed: number;
  onPlay: () => void;
  onPause: () => void;
  onSetSpeed: (speed: number) => void;
}) {
  const visibleMarkers = useMemo(() => [...namedEvents]
    .sort((left, right) => right.importance - left.importance)
    .slice(0, 8), [namedEvents]);

  return (
    <section className="phase75-timeline-rail">
      <div className="phase75-flow-ladder">
        {flowSteps.map((step) => (
          <div key={step.surface} className={`phase75-flow-step${surface === step.surface ? " active" : ""}`}>
            <span className="phase75-flow-index">{step.index}</span>
            <span className="phase75-flow-name">{step.label}</span>
          </div>
        ))}
      </div>

      <div className="phase75-track-shell">
        {liveTimeline && <LiveInspectionControls {...liveTimeline} />}
        <div className="phase75-track-header">
          <div>
            <div className="phase75-overline">Timeline</div>
            <h2>
              {bundle ? "Choose a turn to explore its recorded history" : "Open a saved run or start a new world"}
            </h2>
          </div>

          <div className="phase75-track-actions">
            <button className="phase75-ghost-button" onClick={playing ? onPause : onPlay} disabled={!bundle}>
              {playing ? "Pause" : "Play"}
            </button>
            <select
              className="phase75-speed-select"
              aria-label="Playback speed"
              value={speed}
              onChange={(event) => onSetSpeed(Number(event.target.value))}
              disabled={!bundle}
            >
              {SPEED_OPTIONS.map((option) => (
                <option key={option} value={option}>
                  {option}x
                </option>
              ))}
            </select>
          </div>
        </div>

        <div
          ref={trackRef}
          className={`phase75-turn-track${bundle ? " interactive" : ""}`}
          onClick={onTrackSeek}
          role="slider" tabIndex={bundle ? 0 : -1} aria-label="Historical turn"
          aria-valuemin={1} aria-valuemax={liveTimeline?.latestTurn ?? totalTurns} aria-valuenow={currentTurn}
          onKeyDown={(event) => {
            if (!bundle) return;
            const latest = liveTimeline?.latestTurn ?? totalTurns;
            const next = event.key === "Home" ? 1 : event.key === "End" ? latest
              : event.key === "ArrowLeft" ? currentTurn - 1 : event.key === "ArrowRight" ? currentTurn + 1
                : event.key === "PageUp" ? currentTurn + 10 : event.key === "PageDown" ? currentTurn - 10 : null;
            if (next !== null) { event.preventDefault(); onSeek(Math.max(1, Math.min(latest, next))); }
          }}
        >
          <TrackMarks eraBands={eraBands} narratedSpans={narratedSpans} markers={visibleMarkers} totalTurns={totalTurns} />

          {bundle ? (
            <div className="phase75-playhead" style={{ left: `${turnToPercent(currentTurn, totalTurns)}%` }}>
              <div className="phase75-playhead-line" />
              <div className="phase75-playhead-label">T{currentTurn}</div>
            </div>
          ) : (
            <div className="phase75-frontdoor-callout">
              Your timeline appears when a run is loaded.
            </div>
          )}
        </div>
      </div>
    </section>
  );
}

/**
 * The track's whole-run marks: era bands, narrated spans and the leading
 * named events. They do not depend on the scrubbed turn, so scrubbing does
 * not render them again (the playhead follows them in the track).
 */
const TrackMarks = memo(function TrackMarks({
  eraBands,
  narratedSpans,
  markers,
  totalTurns,
}: {
  eraBands: { label: string; start: number; end: number }[];
  narratedSpans: { start: number; end: number }[];
  markers: Bundle["named_events"];
  totalTurns: number;
}) {
  return (
    <>
      {eraBands.map((band) => (
        <div
          key={`${band.label}-${band.start}`}
          className="phase75-era-band"
          style={{
            left: `${turnToPercent(band.start, totalTurns)}%`,
            width: `${Math.max(2, turnToPercent(band.end, totalTurns) - turnToPercent(band.start, totalTurns))}%`,
          }}
        >
          <span>{band.label}</span>
        </div>
      ))}

      {narratedSpans.map((span, index) => (
        <div
          key={`span-${index}`}
          className="phase75-narrated-span"
          style={{
            left: `${turnToPercent(span.start, totalTurns)}%`,
            width: `${Math.max(1.6, turnToPercent(span.end, totalTurns) - turnToPercent(span.start, totalTurns) + 1.5)}%`,
          }}
        />
      ))}

      {markers.map((marker) => (
        <button
          key={`${marker.turn}-${marker.name}`}
          type="button"
          className="phase75-track-marker"
          style={{ left: `${turnToPercent(marker.turn, totalTurns)}%` }}
          title={marker.name}
        />
      ))}
    </>
  );
});
