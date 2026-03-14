import { useState, useCallback, useRef } from "react";
import type { LobbyInit, StartCommand, ScenarioInfo, WorldState } from "../types";
import { RegionMap } from "./RegionMap";

interface SetupLobbyProps {
  lobbyInit: LobbyInit;
  onLaunch: (params: Omit<StartCommand, "type">) => void;
  starting: boolean;
  error: string | null;
}

export function SetupLobby({ lobbyInit, onLaunch, starting, error }: SetupLobbyProps) {
  const { scenarios, models, defaults } = lobbyInit;

  const [scenario, setScenario] = useState<string>("");
  const [seed, setSeed] = useState<string>("");
  const [turns, setTurns] = useState(defaults.turns);
  const [civs, setCivs] = useState(defaults.civs);
  const [regions, setRegions] = useState(defaults.regions);
  const [simModel, setSimModel] = useState(models[0] || "");
  const [narrativeModel, setNarrativeModel] = useState(models[0] || "");
  const [customSimModel, setCustomSimModel] = useState("");
  const [customNarrativeModel, setCustomNarrativeModel] = useState("");
  const [resumeState, setResumeState] = useState<WorldState | null>(null);
  const [resumeTurn, setResumeTurn] = useState<number | null>(null);
  const [resumeError, setResumeError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const selectedScenario: ScenarioInfo | null =
    scenarios.find((s) => s.file === scenario) ?? null;

  const civsDisabled = resumeState !== null || (selectedScenario?.civs?.length ?? 0) > 0;
  const regionsDisabled = resumeState !== null || (selectedScenario?.regions?.length ?? 0) > 0;

  const handleResumeFile = useCallback((file: File) => {
    const reader = new FileReader();
    reader.onload = () => {
      try {
        const parsed = JSON.parse(reader.result as string);
        if (typeof parsed.turn !== "number" || !Array.isArray(parsed.civilizations)) {
          setResumeError("Invalid save file \u2014 missing required fields");
          return;
        }
        setResumeState(parsed as WorldState);
        setResumeTurn(parsed.turn);
        setResumeError(null);
      } catch {
        setResumeError("Invalid save file \u2014 not valid JSON");
      }
    };
    reader.readAsText(file);
  }, []);

  const clearResume = useCallback(() => {
    setResumeState(null);
    setResumeTurn(null);
    setResumeError(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
  }, []);

  const handleLaunch = useCallback(() => {
    if (turns <= 0) return;

    const resolvedSimModel = simModel === "__custom__" ? customSimModel : simModel;
    const resolvedNarrativeModel = narrativeModel === "__custom__" ? customNarrativeModel : narrativeModel;

    onLaunch({
      scenario: resumeState ? null : (scenario || null),
      turns,
      seed: seed === "" ? null : Number(seed),
      civs: resumeState
        ? resumeState.civilizations.length
        : civsDisabled
          ? (selectedScenario?.civs?.length || defaults.civs)
          : civs,
      regions: resumeState
        ? resumeState.regions.length
        : regionsDisabled
          ? (selectedScenario?.regions?.length || defaults.regions)
          : regions,
      sim_model: resolvedSimModel,
      narrative_model: resolvedNarrativeModel,
      resume_state: resumeState,
    });
  }, [
    scenario, seed, turns, civs, regions, simModel, narrativeModel,
    customSimModel, customNarrativeModel, resumeState, civsDisabled,
    regionsDisabled, selectedScenario, defaults, onLaunch,
  ]);

  // Preview data
  const previewRegions = resumeState
    ? resumeState.regions.map((r) => ({ name: r.name, terrain: r.terrain, x: r.x, y: r.y }))
    : selectedScenario?.regions ?? [];

  const previewControllers = resumeState
    ? Object.fromEntries(resumeState.regions.map((r) => [r.name, r.controller]))
    : undefined;

  const previewCivs = resumeState
    ? resumeState.civilizations.map((c) => ({ name: c.name, values: c.values ?? [] }))
    : selectedScenario?.civs ?? [];

  return (
    <div className="min-h-screen bg-gray-900 text-gray-100 flex">
      {/* Sidebar */}
      <div className="w-[300px] bg-gray-800 border-r border-gray-700 p-5 flex flex-col">
        <div className="mb-6">
          <h1 className="text-lg font-bold text-red-400 tracking-wider">CHRONICLER</h1>
          <p className="text-xs text-gray-500 mt-1">Setup</p>
        </div>

        <div className="flex-1 space-y-4 overflow-y-auto">
          {/* Scenario */}
          <div>
            <label htmlFor="scenario-select" className="block text-[10px] text-gray-500 uppercase mb-1">Scenario</label>
            <select
              id="scenario-select"
              aria-label="Scenario"
              value={scenario}
              onChange={(e) => setScenario(e.target.value)}
              disabled={resumeState !== null}
              className="w-full bg-gray-700 text-gray-200 rounded px-2 py-1.5 text-sm border border-gray-600 disabled:opacity-50"
            >
              <option value="">(Procedural)</option>
              {scenarios.map((s) => (
                <option key={s.file} value={s.file}>{s.name}</option>
              ))}
            </select>
          </div>

          {/* Seed */}
          <div>
            <label htmlFor="seed-input" className="block text-[10px] text-gray-500 uppercase mb-1">Seed</label>
            <div className="flex gap-1">
              <input
                id="seed-input"
                aria-label="Seed"
                type="number"
                min={0}
                placeholder="Random"
                value={seed}
                onChange={(e) => setSeed(e.target.value)}
                className="flex-1 bg-gray-700 text-gray-200 rounded px-2 py-1.5 text-sm border border-gray-600 placeholder-gray-500"
              />
              <button
                onClick={() => setSeed(String(Math.floor(Math.random() * 2147483647)))}
                className="px-2 py-1.5 bg-gray-700 text-red-400 rounded text-sm border border-gray-600 hover:bg-gray-600"
                title="Random seed"
              >
                &#x1F3B2;
              </button>
            </div>
          </div>

          {/* Turns */}
          <div>
            <label htmlFor="turns-input" className="block text-[10px] text-gray-500 uppercase mb-1">Turns</label>
            <input
              id="turns-input"
              aria-label="Turns"
              type="number"
              min={1}
              value={turns}
              onChange={(e) => setTurns(Number(e.target.value) || 1)}
              className="w-full bg-gray-700 text-gray-200 rounded px-2 py-1.5 text-sm border border-gray-600"
            />
          </div>

          {/* Civs / Regions */}
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label htmlFor="civs-input" className="block text-[10px] text-gray-500 uppercase mb-1">Civs</label>
              <input
                id="civs-input"
                aria-label="Civs"
                type="number"
                min={1}
                value={civsDisabled ? (selectedScenario?.civs?.length || civs) : civs}
                onChange={(e) => setCivs(Number(e.target.value) || 1)}
                disabled={civsDisabled}
                className="w-full bg-gray-700 text-gray-200 rounded px-2 py-1.5 text-sm border border-gray-600 disabled:opacity-50"
              />
            </div>
            <div>
              <label htmlFor="regions-input" className="block text-[10px] text-gray-500 uppercase mb-1">Regions</label>
              <input
                id="regions-input"
                aria-label="Regions"
                type="number"
                min={1}
                value={regionsDisabled ? (selectedScenario?.regions?.length || regions) : regions}
                onChange={(e) => setRegions(Number(e.target.value) || 1)}
                disabled={regionsDisabled}
                className="w-full bg-gray-700 text-gray-200 rounded px-2 py-1.5 text-sm border border-gray-600 disabled:opacity-50"
              />
            </div>
          </div>

          {/* Model selectors */}
          <div>
            <label htmlFor="sim-model-select" className="block text-[10px] text-gray-500 uppercase mb-1">Sim Model</label>
            <select
              id="sim-model-select"
              aria-label="Sim Model"
              value={simModel}
              onChange={(e) => setSimModel(e.target.value)}
              className="w-full bg-gray-700 text-gray-200 rounded px-2 py-1.5 text-sm border border-gray-600"
            >
              {models.map((m) => (
                <option key={m} value={m}>{m || "(Default)"}</option>
              ))}
              <option value="__custom__">Custom...</option>
            </select>
            {simModel === "__custom__" && (
              <input
                type="text"
                placeholder="Model name or endpoint"
                value={customSimModel}
                onChange={(e) => setCustomSimModel(e.target.value)}
                className="w-full mt-1 bg-gray-700 text-gray-200 rounded px-2 py-1.5 text-sm border border-gray-600 placeholder-gray-500"
              />
            )}
          </div>

          <div>
            <label htmlFor="narrative-model-select" className="block text-[10px] text-gray-500 uppercase mb-1">Narrative Model</label>
            <select
              id="narrative-model-select"
              aria-label="Narrative Model"
              value={narrativeModel}
              onChange={(e) => setNarrativeModel(e.target.value)}
              className="w-full bg-gray-700 text-gray-200 rounded px-2 py-1.5 text-sm border border-gray-600"
            >
              {models.map((m) => (
                <option key={m} value={m}>{m || "(Default)"}</option>
              ))}
              <option value="__custom__">Custom...</option>
            </select>
            {narrativeModel === "__custom__" && (
              <input
                type="text"
                placeholder="Model name or endpoint"
                value={customNarrativeModel}
                onChange={(e) => setCustomNarrativeModel(e.target.value)}
                className="w-full mt-1 bg-gray-700 text-gray-200 rounded px-2 py-1.5 text-sm border border-gray-600 placeholder-gray-500"
              />
            )}
          </div>

          {/* Resume / Fork */}
          <div>
            <label className="block text-[10px] text-gray-500 uppercase mb-1">Resume / Fork</label>
            {resumeState ? (
              <div className="bg-gray-700 rounded px-3 py-2 text-sm border border-green-800 flex items-center justify-between">
                <span className="text-green-400">Resuming from Turn {resumeTurn}</span>
                <button
                  onClick={clearResume}
                  className="text-gray-400 hover:text-red-400 text-xs ml-2"
                  aria-label="Clear resume"
                >
                  &#x2715;
                </button>
              </div>
            ) : (
              <div
                className="bg-gray-700 rounded px-3 py-2 text-sm border border-dashed border-gray-600 text-gray-500 cursor-pointer hover:border-gray-500"
                onClick={() => fileInputRef.current?.click()}
                onDragOver={(e) => e.preventDefault()}
                onDrop={(e) => {
                  e.preventDefault();
                  const file = e.dataTransfer.files[0];
                  if (file) handleResumeFile(file);
                }}
              >
                Drop state.json or click to browse...
              </div>
            )}
            <input
              ref={fileInputRef}
              type="file"
              accept=".json"
              className="hidden"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) handleResumeFile(file);
              }}
            />
            {resumeError && (
              <p className="text-red-400 text-xs mt-1">{resumeError}</p>
            )}
          </div>
        </div>

        {/* Error banner */}
        {error && (
          <div className="bg-red-900/50 border border-red-800 rounded px-3 py-2 text-sm text-red-300 mt-4">
            {error}
          </div>
        )}

        {/* Launch button */}
        <button
          onClick={handleLaunch}
          disabled={starting || turns <= 0}
          className="w-full mt-4 py-3 bg-green-600 hover:bg-green-500 disabled:bg-gray-600 disabled:cursor-not-allowed text-white rounded-lg font-bold text-base tracking-wide transition-colors"
        >
          {starting ? (
            <span className="flex items-center justify-center gap-2">
              <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
              Starting...
            </span>
          ) : (
            "\u25B6 LAUNCH SIMULATION"
          )}
        </button>
      </div>

      {/* Preview Panel */}
      <div className="flex-1 p-6 overflow-y-auto">
        {!selectedScenario && !resumeState ? (
          <div className="h-full flex items-center justify-center text-gray-500">
            <div className="text-center">
              <div className="text-5xl mb-3">{"\uD83D\uDDFA\uFE0F"}</div>
              <p>Select a scenario to preview</p>
              <p className="text-sm mt-1">or use procedural generation</p>
            </div>
          </div>
        ) : (
          <div className="space-y-6">
            {/* Header */}
            <div>
              <h2 className="text-xl font-bold text-gray-100">
                {resumeState ? resumeState.name : selectedScenario!.name}
              </h2>
              {!resumeState && selectedScenario?.world_name && (
                <p className="text-sm text-gray-500 mt-0.5">{selectedScenario.world_name}</p>
              )}
              <p className="text-gray-400 text-sm mt-2">
                {resumeState
                  ? `Saved state at turn ${resumeTurn} with ${resumeState.civilizations.length} civilizations`
                  : selectedScenario!.description}
              </p>
            </div>

            {/* Region Map */}
            {previewRegions.length > 0 && (
              <div>
                <h3 className="text-sm font-semibold text-gray-400 uppercase mb-2">Regions</h3>
                <RegionMap regions={previewRegions} controllers={previewControllers} />
              </div>
            )}

            {/* Civ List */}
            {previewCivs.length > 0 && (
              <div>
                <h3 className="text-sm font-semibold text-gray-400 uppercase mb-2">Civilizations</h3>
                <div className="grid grid-cols-2 gap-2">
                  {previewCivs.map((c) => (
                    <div key={c.name} className="bg-gray-800 rounded px-3 py-2 border border-gray-700">
                      <p className="text-sm font-medium text-gray-200">{c.name}</p>
                      {c.values.length > 0 && (
                        <p className="text-xs text-gray-500 mt-0.5">{c.values.join(", ")}</p>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
