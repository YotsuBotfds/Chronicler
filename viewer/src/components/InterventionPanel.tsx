import { useState, useCallback, useEffect, useRef } from "react";
import { useDialogFocus } from "../hooks/useDialogFocus";
import type { PauseContext, Command, PendingAction, InjectCommand, CheckpointStatus } from "../types";

import { WhatIfPanel } from "./WhatIfPanel";
import { whatIfActive, type WhatIfControls, type WhatIfPair } from "../lib/whatIf";

interface InterventionPanelProps {
  pauseContext: PauseContext;
  sendCommand: (cmd: Command) => void;
  forkedPath?: string | null;
  forkedHint?: string | null;
  /** Ask for an exact checkpoint; shown when the server lists `checkpoint`. */
  onSaveCheckpoint?: () => void;
  checkpointStatus?: CheckpointStatus | null;
  whatIf?: WhatIfControls;
  onCompareWhatIf?: (pair: WhatIfPair) => void;
  onInspectWorld?: () => void;
  inspectionHidden?: boolean;
}

let nextId = 0;

function CheckpointResult({ status }: { status: CheckpointStatus }) {
  if (status.state === "saving") {
    return <p className="text-sm text-gray-300" role="status">Saving checkpoint…</p>;
  }
  if (status.state === "error") {
    return <p className="text-sm text-red-400" role="status">{status.message}</p>;
  }
  return (
    <div className="bg-gray-700 rounded p-3 text-sm text-gray-300 space-y-1" role="status">
      <p>
        Checkpoint saved at turn {status.turn}: <code className="text-green-400 break-all">{status.path}</code>
      </p>
      {status.resumeHint && (
        <p className="text-gray-400 text-xs font-mono break-all">{status.resumeHint}</p>
      )}
    </div>
  );
}

export function InterventionPanel({
  pauseContext,
  sendCommand,
  forkedPath,
  forkedHint,
  onSaveCheckpoint,
  checkpointStatus,
  whatIf,
  onCompareWhatIf,
  onInspectWorld,
  inspectionHidden = false,
}: InterventionPanelProps) {
  const comparisonActive = whatIfActive(whatIf?.status);
  const canCheckpoint = !!onSaveCheckpoint && pauseContext.valid_commands.includes("checkpoint");
  const [injectEvent, setInjectEvent] = useState(pauseContext.injectable_events[0] || "");
  const [injectCiv, setInjectCiv] = useState(pauseContext.civs[0] || "");
  const [setCiv, setSetCiv] = useState(pauseContext.civs[0] || "");
  const [setStat, setSetStat] = useState(pauseContext.settable_stats[0] || "");
  const [setValue, setSetValue] = useState(5);
  const [pendingActions, setPendingActions] = useState<PendingAction[]>([]);

  useEffect(() => {
    setInjectEvent(pauseContext.injectable_events[0] || "");
    setInjectCiv(pauseContext.civs[0] || "");
    setSetCiv(pauseContext.civs[0] || "");
    setSetStat(pauseContext.settable_stats[0] || "");
    setSetValue(5);
    setPendingActions([]);
  }, [pauseContext]);

  const stageInject = useCallback(() => {
    const cmd: InjectCommand = { type: "inject", event_type: injectEvent, civ: injectCiv };
    setPendingActions((prev) => [...prev, { id: String(++nextId), command: cmd, status: "staged" }]);
  }, [injectEvent, injectCiv]);

  const removePending = useCallback((id: string) => {
    setPendingActions((prev) => prev.filter((a) => a.status !== "staged" || a.id !== id));
  }, []);

  const handleContinue = useCallback(() => {
    for (const action of pendingActions) {
      if (action.status === "staged") {
        sendCommand(action.command);
      }
    }
    sendCommand({ type: "continue" });
    setPendingActions([]);
  }, [pendingActions, sendCommand]);

  const handleSet = useCallback(() => {
    sendCommand({ type: "set", civ: setCiv, stat: setStat, value: setValue });
  }, [sendCommand, setCiv, setStat, setValue]);
  const dialogRef = useRef<HTMLDivElement>(null);
  // Escape never silently resumes a world or cancels a running pair. Those
  // state-changing actions retain their explicit buttons inside the dialog.
  useDialogFocus(dialogRef, !inspectionHidden);

  return (
    <div hidden={inspectionHidden} inert={inspectionHidden} style={inspectionHidden ? { display: "none" } : undefined} className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div ref={dialogRef} tabIndex={-1} role="dialog" aria-modal="true" aria-label={`Paused simulation at turn ${pauseContext.turn}`} className="bg-gray-800 rounded-lg shadow-2xl p-4 sm:p-6 w-[600px] max-w-[calc(100vw-24px)] max-h-[90vh] overflow-y-auto space-y-6">
        <h2 className="text-lg font-bold text-gray-100">
          Paused at Turn {pauseContext.turn}
        </h2>
        {onInspectWorld && <div>
          <button type="button" disabled={comparisonActive} onClick={onInspectWorld}
            className="min-h-11 px-4 py-2 bg-gray-700 text-gray-100 rounded">Inspect world while paused</button>
          <p className="text-sm text-gray-300">Inspect recorded conditions without continuing the simulation. Return to these controls when ready.
            {comparisonActive && " Cancel or finish this comparison first so its reviewed recipe remains bound."}</p>
        </div>}

        {whatIf && onCompareWhatIf && pauseContext.valid_commands.includes("what_if_prepare") && <WhatIfPanel context={pauseContext} controls={whatIf} onCompare={onCompareWhatIf} />}
        {comparisonActive && <p role="status" className="text-sm text-amber-200">The original world is locked while a comparison is prepared or running. Cancel it to change or continue this world.</p>}
        <fieldset disabled={comparisonActive} className="space-y-6 min-w-0">
        {/* Event Injection */}
        <div className="space-y-2">
          <h3 className="text-sm font-semibold text-gray-300">Stage Event</h3>
          <div className="flex gap-2">
            <label className="sr-only" htmlFor="inject-event">Event type</label>
            <select
              id="inject-event"
              aria-label="Event type"
              value={injectEvent}
              onChange={(e) => setInjectEvent(e.target.value)}
              className="flex-1 bg-gray-700 text-gray-200 rounded px-2 py-1 text-sm"
            >
              {pauseContext.injectable_events.map((ev) => (
                <option key={ev} value={ev}>{ev.charAt(0).toUpperCase() + ev.slice(1)}</option>
              ))}
            </select>
            <label className="sr-only" htmlFor="inject-civ">Target civ</label>
            <select
              id="inject-civ"
              aria-label="Target civ"
              value={injectCiv}
              onChange={(e) => setInjectCiv(e.target.value)}
              className="flex-1 bg-gray-700 text-gray-200 rounded px-2 py-1 text-sm"
            >
              {pauseContext.civs.map((c) => (
                <option key={c} value={c}>{c}</option>
              ))}
            </select>
            <button
              onClick={stageInject}
              className="px-3 py-1 bg-amber-600 hover:bg-amber-500 text-white rounded text-sm"
            >
              Inject
            </button>
          </div>
        </div>

        {/* Stat Override */}
        <div className="space-y-2">
          <h3 className="text-sm font-semibold text-gray-300">Override Stat</h3>
          <div className="flex gap-2">
            <label className="sr-only" htmlFor="set-civ">Stat civ</label>
            <select
              id="set-civ"
              aria-label="Stat civ"
              value={setCiv}
              onChange={(e) => setSetCiv(e.target.value)}
              className="flex-1 bg-gray-700 text-gray-200 rounded px-2 py-1 text-sm"
            >
              {pauseContext.civs.map((c) => (
                <option key={c} value={c}>{c}</option>
              ))}
            </select>
            <label className="sr-only" htmlFor="set-stat">Stat name</label>
            <select
              id="set-stat"
              aria-label="Stat name"
              value={setStat}
              onChange={(e) => setSetStat(e.target.value)}
              className="flex-1 bg-gray-700 text-gray-200 rounded px-2 py-1 text-sm"
            >
              {pauseContext.settable_stats.map((s) => (
                <option key={s} value={s}>{s}</option>
              ))}
            </select>
            <label className="sr-only" htmlFor="set-value">Stat value</label>
            <input
              id="set-value"
              aria-label="Stat value"
              type="number"
              value={setValue}
              onChange={(e) => setSetValue(Number(e.target.value))}
              className="w-16 bg-gray-700 text-gray-200 rounded px-2 py-1 text-sm text-center"
            />
            <button
              onClick={handleSet}
              className="px-3 py-1 bg-blue-600 hover:bg-blue-500 text-white rounded text-sm"
            >
              Set
            </button>
          </div>
        </div>

        {/* Pending actions queue */}
        {pendingActions.length > 0 && (
          <div className="space-y-2">
            <h3 className="text-sm font-semibold text-gray-300">Pending Actions</h3>
            <ul className="space-y-1">
              {pendingActions.map((action) => (
                <li key={action.id} className="flex items-center gap-2 text-sm text-gray-300 bg-gray-700 rounded px-2 py-1">
                  {action.status === "sent" ? (
                    <span className="text-green-400" title="Sent">&#10003;</span>
                  ) : (
                    <button
                      aria-label="remove"
                      onClick={() => removePending(action.id)}
                      className="text-red-400 hover:text-red-300"
                    >
                      &#10005;
                    </button>
                  )}
                  <span>
                    {action.command.type === "inject"
                      ? `${(action.command as InjectCommand).event_type} -> ${(action.command as InjectCommand).civ}`
                      : JSON.stringify(action.command)}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Fork info */}
        {forkedPath && (
          <div className="bg-gray-700 rounded p-3 text-sm text-gray-300 space-y-1">
            <p>Fork saved to: <code className="text-green-400 break-all">{forkedPath}</code></p>
            {forkedHint && (
              <p className="text-gray-400 text-xs font-mono break-all">{forkedHint}</p>
            )}
          </div>
        )}

        {/* Checkpoint result */}
        {canCheckpoint && checkpointStatus && <CheckpointResult status={checkpointStatus} />}

        </fieldset>
        {/* Action buttons */}
        <div className="flex gap-3 justify-between">
          <div className="flex gap-2">
            <button
              disabled={comparisonActive}
              onClick={() => sendCommand({ type: "fork" })}
              className="px-4 py-2 bg-gray-600 hover:bg-gray-500 text-gray-200 rounded text-sm"
            >
              Fork
            </button>
            {canCheckpoint && (
              <button
                onClick={onSaveCheckpoint}
                disabled={comparisonActive || checkpointStatus?.state === "saving"}
                className="px-4 py-2 bg-gray-600 hover:bg-gray-500 disabled:opacity-50 text-gray-200 rounded text-sm"
              >
                Save checkpoint
              </button>
            )}
            <button
              onClick={() => sendCommand({ type: "quit" })}
              className="px-4 py-2 bg-red-800 hover:bg-red-700 text-gray-200 rounded text-sm"
            >
              Quit
            </button>
          </div>
          <button
            disabled={comparisonActive}
              onClick={handleContinue}
            className="px-6 py-2 bg-green-600 hover:bg-green-500 text-white rounded text-sm font-semibold"
          >
            Continue
          </button>
        </div>
      </div>
    </div>
  );
}
