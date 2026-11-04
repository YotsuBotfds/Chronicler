/**
 * The setup surface's launch form in the shell's left rail: scenario, seed,
 * world size, models and a resume/fork save. Presentation only: AppShell
 * owns every value and handler and passes them in.
 */
import type { LobbyInit, WorldState } from "../../types";

/** The setup form's values, as AppShell holds them. */
export type SetupState = {
  scenario: string;
  scenarios: LobbyInit["scenarios"];
  seed: string;
  turns: number;
  civs: number;
  regions: number;
  simModel: string;
  narrativeModel: string;
  models: string[];
  customSimModel: string;
  customNarrativeModel: string;
  starting: boolean;
  error: string | null;
  resumeState: WorldState | null;
  resumeTurn: number | null;
  resumeError: string | null;
  civsDisabled: boolean;
  regionsDisabled: boolean;
  lobbyReady: boolean;
};

export function SetupRail({
  state,
  onScenarioChange,
  onSeedChange,
  onTurnsChange,
  onCivsChange,
  onRegionsChange,
  onSimModelChange,
  onNarrativeModelChange,
  onCustomSimModelChange,
  onCustomNarrativeModelChange,
  onRandomSeed,
  onResumeBrowse,
  onResumeDrop,
  onClearResume,
  onLaunch,
}: {
  state: SetupState;
  onScenarioChange: (value: string) => void;
  onSeedChange: (value: string) => void;
  onTurnsChange: (value: number) => void;
  onCivsChange: (value: number) => void;
  onRegionsChange: (value: number) => void;
  onSimModelChange: (value: string) => void;
  onNarrativeModelChange: (value: string) => void;
  onCustomSimModelChange: (value: string) => void;
  onCustomNarrativeModelChange: (value: string) => void;
  onRandomSeed: () => void;
  onResumeBrowse: () => void;
  onResumeDrop: (file: File) => void;
  onClearResume: () => void;
  onLaunch: () => void;
}) {
  return (
    <div className="phase75-form-stack">
      <label className="phase75-field">
        <span>Scenario</span>
        <select
          value={state.scenario}
          onChange={(event) => onScenarioChange(event.target.value)}
          disabled={!state.lobbyReady || !!state.resumeState}
        >
          <option value="">Procedural</option>
          {state.scenarios.map((scenario) => (
            <option key={scenario.file} value={scenario.file}>
              {scenario.name}
            </option>
          ))}
        </select>
      </label>

      <div className="phase75-field">
        <span>Seed</span>
        <div className="phase75-inline-field">
          <input
            type="number"
            aria-label="Seed"
            value={state.seed}
            placeholder="Random"
            onChange={(event) => onSeedChange(event.target.value)}
            disabled={!state.lobbyReady}
          />
          <button type="button" className="phase75-ghost-button" onClick={onRandomSeed} disabled={!state.lobbyReady}>
            Randomize
          </button>
        </div>
      </div>

      <div className="phase75-two-up">
        <label className="phase75-field">
          <span>Turns</span>
          <input
            type="number"
            min={1}
            value={state.turns}
            onChange={(event) => onTurnsChange(Number(event.target.value) || 1)}
            disabled={!state.lobbyReady}
          />
        </label>
        <label className="phase75-field">
          <span>Civilizations</span>
          <input
            type="number"
            min={1}
            value={state.civs}
            onChange={(event) => onCivsChange(Number(event.target.value) || 1)}
            disabled={!state.lobbyReady || state.civsDisabled}
          />
        </label>
      </div>

      <div className="phase75-two-up">
        <label className="phase75-field">
          <span>Regions</span>
          <input
            type="number"
            min={1}
            value={state.regions}
            onChange={(event) => onRegionsChange(Number(event.target.value) || 1)}
            disabled={!state.lobbyReady || state.regionsDisabled}
          />
        </label>
        <label className="phase75-field">
          <span>Sim Model</span>
          <select value={state.simModel} onChange={(event) => onSimModelChange(event.target.value)} disabled={!state.lobbyReady}>
            {state.models.map((model) => (
              <option key={model} value={model}>
                {model || "(Default)"}
              </option>
            ))}
            <option value="__custom__">Custom...</option>
          </select>
        </label>
      </div>

      {state.simModel === "__custom__" && (
        <label className="phase75-field">
          <span>Custom Sim Endpoint</span>
          <input
            type="text"
            value={state.customSimModel}
            onChange={(event) => onCustomSimModelChange(event.target.value)}
          />
        </label>
      )}

      <label className="phase75-field">
        <span>Narrative Model</span>
        <select value={state.narrativeModel} onChange={(event) => onNarrativeModelChange(event.target.value)} disabled={!state.lobbyReady}>
          {state.models.map((model) => (
            <option key={model} value={model}>
              {model || "(Default)"}
            </option>
          ))}
          <option value="__custom__">Custom...</option>
        </select>
      </label>

      {state.narrativeModel === "__custom__" && (
        <label className="phase75-field">
          <span>Custom Narrative Endpoint</span>
          <input
            type="text"
            value={state.customNarrativeModel}
            onChange={(event) => onCustomNarrativeModelChange(event.target.value)}
          />
        </label>
      )}

      <div className="phase75-field">
        <span>Resume / Fork</span>
        {state.resumeState ? (
          <div className="phase75-resume-pill">
            <span>Resuming from turn {state.resumeTurn}</span>
            <button type="button" className="phase75-ghost-button" onClick={onClearResume}>
              Clear
            </button>
          </div>
        ) : (
          <div
            className="phase75-dropzone"
            onClick={onResumeBrowse}
            onDragOver={(event) => event.preventDefault()}
            onDrop={(event) => {
              event.preventDefault();
              const file = event.dataTransfer.files[0];
              if (file) {
                onResumeDrop(file);
              }
            }}
          >
            Drop `state.json` or click to browse
          </div>
        )}
        {state.resumeError && <div className="phase75-inline-error">{state.resumeError}</div>}
      </div>

      {!state.lobbyReady && (
        <div className="phase75-empty-state">
          Start the viewer from a live session to create a run, or choose Open Existing to explore a saved run.
        </div>
      )}

      <button
        type="button"
        className="phase75-primary-button"
        onClick={onLaunch}
        disabled={!state.lobbyReady || state.starting || state.turns <= 0}
      >
        {state.starting ? "Preparing World..." : "Run World"}
      </button>
    </div>
  );
}
