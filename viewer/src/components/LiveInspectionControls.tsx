import "./live-inspection.css";

interface LiveInspectionControlsProps {
  followMode: boolean;
  inspectionLocked: boolean;
  newTurns: number;
  latestTurn: number;
  onReturnToLive: () => void;
  onLock: () => void;
}

export function LiveInspectionControls({
  followMode,
  inspectionLocked,
  newTurns,
  latestTurn,
  onReturnToLive,
  onLock,
}: LiveInspectionControlsProps) {
  return (
    <div className="live-inspection-controls" aria-label="Live timeline controls">
      <div className="live-inspection-status" role="status" aria-live="polite" aria-atomic="true">
        <strong>{inspectionLocked ? "Inspecting history" : followMode ? "Following live" : "Live follow ready"}</strong>
        <span>
          {inspectionLocked && newTurns > 0
            ? `${newTurns} new ${newTurns === 1 ? "turn" : "turns"} available · `
            : ""}
          Latest available: turn {latestTurn}
        </span>
      </div>
      {inspectionLocked ? (
        <button type="button" className="live-inspection-return" onClick={onReturnToLive}>
          Return to live
        </button>
      ) : (
        <button type="button" className="live-inspection-lock" onClick={onLock}>
          Inspect this turn
        </button>
      )}
    </div>
  );
}
