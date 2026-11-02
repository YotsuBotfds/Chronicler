import { useState } from "react";
import type { PauseContext } from "../types";
import { granaryPolicyValue, whatIfActive, whatIfInterventionLabel, type WhatIfControls, type WhatIfPair } from "../lib/whatIf";
import "./what-if.css";

export function WhatIfPanel({ context, controls, onCompare }: {
  context: PauseContext; controls: WhatIfControls; onCompare: (pair: WhatIfPair) => void;
}) {
  const [civ, setCiv] = useState(context.civs[0] ?? "");
  const [value, setValue] = useState(50);
  const [turns, setTurns] = useState(5);
  const [control, setControl] = useState<"stability" | "granary_shortfall_priority">("stability");
  const [policy, setPolicy] = useState<0 | 1>(1);
  const policyBefore = granaryPolicyValue(controls.bundle);
  const status = controls.status;
  const active = whatIfActive(status);
  const manifest = status?.manifest;
  const valid = (control === "stability" ? context.civs.includes(civ) && Number.isInteger(value) && value >= 1 && value <= 100
    : policyBefore !== null)
    && Number.isInteger(turns) && turns >= 1 && turns <= 20;
  return <section className="what-if-panel" aria-label="Bounded what-if">
    <h3>Try a bounded what-if</h3>
    <p>Compare an unchanged continuation with one supported intervention from the same exact checkpoint.
      Both runs are simulate-only. Your original world stays paused.</p>
    <p>A saved world state is a fork, which cannot preserve the entire runtime. This workflow requires
      a compatible exact checkpoint and a simulate-only live session launched with PYTHONHASHSEED=0.</p>
    <fieldset disabled={active || !controls.connected}>
      <legend>Label the intervention before running</legend>
      <label>Control<select aria-label="What-if control" value={control} onChange={(e) => setControl(e.target.value as typeof control)}>
        <option value="stability">Civilization stability</option>
        <option value="granary_shortfall_priority" disabled={policyBefore === null}>Global granary procurement priority</option>
      </select></label>
      {control === "stability" ? <><label>Civilization<select aria-label="What-if civilization" value={civ} onChange={(e) => setCiv(e.target.value)}>
        {context.civs.map((name) => <option key={name}>{name}</option>)}
      </select></label>
      <label>Set stability to<input aria-label="What-if stability" type="number" min={1} max={100}
        value={value} onChange={(e) => setValue(Number(e.target.value))} /></label></>
        : <><label>Priority<select aria-label="What-if granary priority" value={policy} onChange={(e) => setPolicy(Number(e.target.value) as 0 | 1)}>
          <option value={0}>Reserve fill first (0)</option><option value={1}>Food shortfall first (1)</option>
        </select></label>
        <p>World scope: every existing public granary. Baseline priority {policyBefore}; intervention priority {policy}.
          Purchase ordering changes within domestic and foreign passes. This does not enable granaries or create grain or money.
          {policyBefore === policy && " The selected value is unchanged; this is a no-op control."}</p></>}
      {policyBefore === null && <p>Global granary priority requires hybrid mode and already-enabled public granaries with a binary saved priority.</p>}
      <label>Additional turns<input aria-label="What-if horizon" type="number" min={1} max={20}
        value={turns} onChange={(e) => setTurns(Number(e.target.value))} /></label>
      <button type="button" disabled={!valid} onClick={() => control === "stability"
        ? controls.prepare(civ, value, turns) : controls.preparePolicy(policy, turns)}>Prepare comparison</button>
    </fieldset>
    {manifest && <div className="what-if-manifest" aria-label="Prepared what-if">
      <p><strong>{whatIfInterventionLabel(manifest)}</strong></p>
      <p>Seed {manifest.seed} · {manifest.mode} · starting at turn {manifest.start_turn},
        continuing {manifest.turns} turns through {manifest.end_turn}.</p>
      <p>Both arms restore the same exact runtime. One deterministic pair describes this case;
        it does not establish a general benefit. The override applies after the starting snapshot.</p>
      <details><summary>Source and runtime identity</summary><pre>{JSON.stringify(manifest.source, null, 2)}</pre></details>
    </div>}
    {status && <p role={status.state === "error" ? "alert" : "status"}>
      {status.state === "preparing" ? "Preparing exact checkpoint…" : status.state === "prepared" ? "Ready. Review the intervention, then run both continuations."
        : status.state === "running" ? `Running ${status.arm ?? "paired continuations"}…`
        : status.state === "completed" ? "Both continuations completed. Your original world is still paused."
        : status.state === "cancelled" ? "Comparison cancelled. Partial outputs are retained on the server." : "Comparison could not finish."}
      {status.message && ` ${status.message}`}
    </p>}
    {!controls.connected && <p role="status">Connection lost. Reconnecting; server runs remain bounded. Cancel when connected.</p>}
    <div className="what-if-actions">
      {status?.state === "prepared" && <button type="button" disabled={!controls.connected} onClick={controls.run}>Run both continuations</button>}
      {active && <button type="button" disabled={!controls.connected} onClick={controls.cancel}>Cancel comparison</button>}
      {status?.pair && <button type="button" onClick={() => onCompare(status.pair!)}>Compare what-if results</button>}
    </div>
  </section>;
}
