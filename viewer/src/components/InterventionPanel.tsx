import { useState, useCallback } from "react";
import type { PauseContext, Command, PendingAction, InjectCommand } from "../types";

interface InterventionPanelProps {
  pauseContext: PauseContext;
  sendCommand: (cmd: Command) => void;
  forkedPath?: string | null;
  forkedHint?: string | null;
}

let nextId = 0;

export function InterventionPanel({
  pauseContext,
  sendCommand,
  forkedPath,
  forkedHint,
}: InterventionPanelProps) {
  const [injectEvent, setInjectEvent] = useState(pauseContext.injectable_events[0] || "");
  const [injectCiv, setInjectCiv] = useState(pauseContext.civs[0] || "");
  const [setCiv, setSetCiv] = useState(pauseContext.civs[0] || "");
  const [setStat, setSetStat] = useState(pauseContext.settable_stats[0] || "");
  const [setValue, setSetValue] = useState(5);
  const [pendingActions, setPendingActions] = useState<PendingAction[]>([]);

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

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="bg-gray-800 rounded-lg shadow-2xl p-6 w-[500px] max-h-[80vh] overflow-y-auto space-y-6">
        <h2 className="text-lg font-bold text-gray-100">
          Paused at Turn {pauseContext.turn}
        </h2>

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
            <p>Fork saved to: <code className="text-green-400">{forkedPath}</code></p>
            {forkedHint && (
              <p className="text-gray-400 text-xs font-mono">{forkedHint}</p>
            )}
          </div>
        )}

        {/* Action buttons */}
        <div className="flex gap-3 justify-between">
          <div className="flex gap-2">
            <button
              onClick={() => sendCommand({ type: "fork" })}
              className="px-4 py-2 bg-gray-600 hover:bg-gray-500 text-gray-200 rounded text-sm"
            >
              Fork
            </button>
            <button
              onClick={() => sendCommand({ type: "quit" })}
              className="px-4 py-2 bg-red-800 hover:bg-red-700 text-gray-200 rounded text-sm"
            >
              Quit
            </button>
          </div>
          <button
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
