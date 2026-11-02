import { useEffect, useState } from "react";
import type { PauseContext } from "../types";
import { createWhatIfRecipe, granaryPolicyValue, portableWhatIfManifest, readWhatIfRecipe,
  recipeLiveMismatch, recipePreparedMismatch, whatIfActive, whatIfInterventionLabel,
  type WhatIfControls, type WhatIfManifest, type WhatIfPair, type WhatIfRecipe } from "../lib/whatIf";
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
  const [recipe, setRecipe] = useState<WhatIfRecipe | null>(null);
  const [recipeMessage, setRecipeMessage] = useState("");
  const [recipeError, setRecipeError] = useState("");
  const [verification, setVerification] = useState<{ recipe: WhatIfRecipe; manifest: WhatIfManifest; error: string | null } | null>(null);
  const status = controls.status;
  const active = whatIfActive(status);
  const manifest = status?.manifest;
  useEffect(() => {
    if (!recipe || !manifest) return;
    let cancelled = false;
    void recipePreparedMismatch(recipe, manifest).then((error) => {
      if (!cancelled) setVerification({ recipe, manifest, error });
    }).catch((error: unknown) => {
      if (!cancelled) setVerification({ recipe, manifest,
        error: error instanceof Error ? error.message : "Recipe identity could not be verified." });
    });
    return () => { cancelled = true; };
  }, [recipe, manifest]);
  const verified = !!recipe && verification?.recipe === recipe && verification.manifest === manifest;
  const liveMismatch = recipe ? recipeLiveMismatch(recipe, controls.bundle, context.turn, context.civs) : null;
  const recipeRunReady = !recipe || !liveMismatch && verified && verification?.error === null;
  const valid = (control === "stability" ? context.civs.includes(civ) && Number.isInteger(value) && value >= 1 && value <= 100
    : policyBefore !== null)
    && Number.isInteger(turns) && turns >= 1 && turns <= 20;

  async function importRecipe(file: File) {
    setRecipeError("");
    try {
      if (file.size > 1024 * 1024) throw new Error("Recipe exceeds the 1 MiB limit.");
      const parsed = readWhatIfRecipe(JSON.parse(new TextDecoder().decode(await file.arrayBuffer())));
      if (!parsed) throw new Error("Unsupported or malformed recipe. Only stability and global granary priority recipes are supported.");
      const mismatch = recipeLiveMismatch(parsed, controls.bundle, context.turn, context.civs);
      if (mismatch) throw new Error(mismatch);
      setRecipe(parsed);
      setTurns(parsed.turns);
      setControl(parsed.control.kind);
      if (parsed.control.kind === "stability") { setCiv(parsed.control.civ); setValue(parsed.control.value); }
      else setPolicy(parsed.control.value);
      setRecipeMessage("Recipe loaded into the preparation form. No command was sent. Prepare to verify its exact checkpoint, source and settings.");
    } catch (error) {
      setRecipeError(error instanceof Error ? error.message : "Could not read this recipe.");
    }
  }

  async function exportRecipe() {
    if (!manifest) return;
    setRecipeError("");
    try {
      const exported = await createWhatIfRecipe(manifest, status?.pair);
      const url = URL.createObjectURL(new Blob([JSON.stringify(exported, null, 2) + "\n"], { type: "application/json" }));
      const anchor = document.createElement("a");
      anchor.href = url; anchor.download = "chronicler-what-if-recipe.json"; anchor.click();
      setTimeout(() => URL.revokeObjectURL(url), 0);
      setRecipeMessage("Recipe downloaded with basename-only artifact identities and supported settings.");
    } catch (error) {
      setRecipeError(error instanceof Error ? error.message : "Could not export this recipe.");
    }
  }

  function prepare() {
    if (recipe) {
      const mismatch = recipeLiveMismatch(recipe, controls.bundle, context.turn, context.civs);
      if (mismatch) { setRecipeError(mismatch); return; }
    }
    if (control === "stability") controls.prepare(civ, value, turns);
    else controls.preparePolicy(policy, turns);
  }
  return <section className="what-if-panel" aria-label="Bounded what-if">
    <h3>Try a bounded what-if</h3>
    <p>Compare an unchanged continuation with one supported intervention from the same exact checkpoint.
      Both runs are simulate-only. Your original world stays paused.</p>
    <p>A saved world state is a fork, which cannot preserve the entire runtime. This workflow requires
      a compatible exact checkpoint and a simulate-only live session launched with PYTHONHASHSEED=0.</p>
    <div className="what-if-recipes" aria-label="Saved comparison recipe">
      <label>Import recipe<input type="file" accept=".json,application/json" aria-label="Import what-if recipe"
        disabled={active || !controls.connected} onChange={(event) => {
          const file = event.target.files?.[0]; event.target.value = ""; if (file) void importRecipe(file);
        }} /></label>
      {manifest && <button type="button" onClick={() => void exportRecipe()}>Download recipe</button>}
      {recipe && <button type="button" disabled={active} onClick={() => {
        setRecipe(null); setRecipeError(""); setRecipeMessage("Imported recipe cleared; the form is a new preparation.");
      }}>Clear imported recipe</button>}
      {recipeMessage && <p role="status">{recipeMessage}</p>}
      {recipeError && <p role="alert">{recipeError}</p>}
      {recipe && <details><summary>Imported recipe preview</summary>
        <p>Seed {recipe.source.seed} · {recipe.source.mode} · turn {recipe.source.start_turn} → {recipe.end_turn}.
          Saved output identities are references to the exported result, not commands to load or execute it.</p>
        <pre>{JSON.stringify(recipe, null, 2)}</pre>
      </details>}
    </div>
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
      <button type="button" disabled={!valid} onClick={prepare}>Prepare comparison</button>
    </fieldset>
    {manifest && <div className="what-if-manifest" aria-label="Prepared what-if">
      <p><strong>{whatIfInterventionLabel(manifest)}</strong></p>
      <p>Seed {manifest.seed} · {manifest.mode} · starting at turn {manifest.start_turn},
        continuing {manifest.turns} turns through {manifest.end_turn}.</p>
      <p>Both arms restore the same exact runtime. One deterministic pair describes this case;
        it does not establish a general benefit. The override applies after the starting snapshot.</p>
      <details><summary>Source and runtime identity</summary><pre>{JSON.stringify(portableWhatIfManifest(manifest).source, null, 2)}</pre></details>
      {recipe && <p role={liveMismatch || verified && verification?.error ? "alert" : "status"}>
        {liveMismatch ?? (verified ? verification?.error ?? "Imported recipe checkpoint, source, runtime, settings, control and horizon match this preparation."
          : "Verifying imported recipe identity; running remains disabled.")}
      </p>}
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
      {status?.state === "prepared" && <button type="button" disabled={!controls.connected || !recipeRunReady}
        onClick={() => { if (recipeRunReady) controls.run(); }}>Run both continuations</button>}
      {active && <button type="button" disabled={!controls.connected} onClick={controls.cancel}>Cancel comparison</button>}
      {status?.pair && <button type="button" onClick={() => onCompare(status.pair!)}>Compare what-if results</button>}
    </div>
  </section>;
}
