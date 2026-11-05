/**
 * "Experimental features (off by default)": the feature switches a Batch Lab
 * batch or a live new world may request, rendered from the catalog the
 * server sent in its lobby message (lib/featureCatalog). Nothing is selected
 * by default. A switch whose requirements are not met is disabled with the
 * reason; turning a prerequisite off drops what depends on it. The section
 * is hidden when the server sent no catalog (an older server) and replaced
 * by a notice when the catalog cannot be read.
 */
import { useId, useMemo, useState } from "react";
import type { FeatureSelection } from "../types";
import {
  choiceValue,
  effectiveValues,
  isOn,
  normalizeSelection,
  readFeatureCatalog,
  selectionFlags,
  unmetRequirements,
  type FeatureCatalog,
  type FeatureEntry,
  type FeatureRequirement,
  type FeatureSurface,
  type FeatureSurfaceName,
} from "../lib/featureCatalog";

export interface FeatureOptionsProps {
  /** The lobby message's `feature_catalog` field, unread. */
  catalog: unknown;
  surface: FeatureSurfaceName;
  selection: FeatureSelection;
  onSelectionChange: (selection: FeatureSelection) => void;
  /** Batch Lab: the agent mode chosen for the runs (null: the server's). */
  agents?: string | null;
  onAgentsChange?: (agents: string | null) => void;
  disabled?: boolean;
  /** Why no feature can be requested right now (shown, everything disabled). */
  unavailable?: string | null;
}

const WRAP = "min-w-0 max-w-full [overflow-wrap:anywhere]";

function agentContext(surfaceName: FeatureSurfaceName, agents: string | null): string {
  const mode = agents ?? "unknown";
  return surfaceName === "live" ? ` (this server runs --agents ${mode})` : ` (these runs use --agents ${mode})`;
}

function reasonText(req: FeatureRequirement, surfaceName: FeatureSurfaceName, agents: string | null): string {
  return req.kind === "agents" ? req.reason + agentContext(surfaceName, agents) : req.reason;
}

export function FeatureOptions({
  catalog: raw,
  surface: surfaceName,
  selection,
  onSelectionChange,
  agents: agentsOverride = null,
  onAgentsChange,
  disabled = false,
  unavailable = null,
}: FeatureOptionsProps) {
  const reading = useMemo(() => readFeatureCatalog(raw), [raw]);
  const [open, setOpen] = useState(false);
  const panelId = useId();

  if (reading.status === "absent") return null;
  if (reading.status === "invalid") {
    return (
      <div role="status" className={`text-xs text-amber-300 bg-amber-900/30 border border-amber-800 rounded px-2 py-1.5 ${WRAP}`}>
        Experimental features are unavailable: the server sent a feature list this viewer cannot read
        ({reading.error}).
      </div>
    );
  }
  const catalog = reading.catalog;
  if (catalog.features.length === 0) return null;
  const surface = catalog.surfaces[surfaceName];
  const agents = agentsOverride ?? surface.agents;
  const count = Object.keys(selection).length;

  return (
    <section className={`border border-gray-700 rounded ${WRAP}`} aria-label="Experimental features">
      <button
        type="button"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen(!open)}
        className={`w-full text-left text-xs text-gray-300 hover:text-gray-100 px-2 py-1.5 ${WRAP}`}
      >
        <span aria-hidden="true">{open ? "▼" : "▶"} </span>Experimental features (off by default)
        {count > 0 ? ` \u00B7 ${count} selected` : ""}
      </button>
      {open && (
        <FeatureOptionsBody
          id={panelId}
          catalog={catalog}
          surface={surface}
          surfaceName={surfaceName}
          agents={agents}
          agentsOverride={agentsOverride}
          onAgentsChange={onAgentsChange}
          selection={selection}
          onSelectionChange={onSelectionChange}
          disabled={disabled || !!unavailable}
          unavailable={unavailable}
        />
      )}
    </section>
  );
}

function FeatureOptionsBody({
  id, catalog, surface, surfaceName, agents, agentsOverride, onAgentsChange, selection, onSelectionChange,
  disabled, unavailable,
}: {
  id: string;
  catalog: FeatureCatalog;
  surface: FeatureSurface;
  surfaceName: FeatureSurfaceName;
  agents: string | null;
  agentsOverride: string | null;
  onAgentsChange?: (agents: string | null) => void;
  selection: FeatureSelection;
  onSelectionChange: (selection: FeatureSelection) => void;
  disabled: boolean;
  unavailable: string | null;
}) {
  const effective = effectiveValues(surface, selection);
  const update = (next: FeatureSelection, nextAgents: string | null = agents) =>
    onSelectionChange(normalizeSelection(catalog, surface, nextAgents, next));
  const topLevel = catalog.features.filter((entry) => entry.parent === null);
  const groups: string[] = [];
  for (const entry of topLevel) if (!groups.includes(entry.group)) groups.push(entry.group);
  // Experimental groups first, prerequisites after them.
  groups.sort((a, b) => Number(!topLevel.some((e) => e.group === a && e.experimental))
    - Number(!topLevel.some((e) => e.group === b && e.experimental)));
  const flags = selectionFlags(catalog, selection);
  const inherited = selectionFlags(catalog, surface.values);
  const canChooseAgents = surfaceName === "batch" && !!onAgentsChange && surface.agentModes.length > 1;

  return (
    <div id={id} className={`px-2 pb-2 space-y-3 ${WRAP}`}>
      <p className={`text-[11px] text-gray-500 ${WRAP}`}>
        Each switch stays off unless you select it here; a selected switch is passed to the run as its
        command-line flag, and the server checks its requirements before anything starts.
        {surface.newWorldsOnly ? " These options apply to new worlds." : ""}
      </p>
      {unavailable && <p role="note" className={`text-xs text-amber-300 ${WRAP}`}>{unavailable}</p>}

      {canChooseAgents ? (
        <label className={`block text-xs text-gray-400 ${WRAP}`}>
          Agent mode for these runs
          <select
            value={agentsOverride ?? ""}
            disabled={disabled}
            onChange={(event) => {
              const next = event.target.value === "" ? null : event.target.value;
              onAgentsChange!(next);
              update(selection, next ?? surface.agents);
            }}
            className="block w-full max-w-full mt-1 bg-gray-700 text-gray-200 rounded px-2 py-1 text-xs border border-gray-600 disabled:opacity-50"
          >
            <option value="">Server default (--agents {surface.agents ?? "unknown"})</option>
            {surface.agentModes.map((mode) => (
              <option key={mode} value={mode}>--agents {mode}</option>
            ))}
          </select>
        </label>
      ) : (
        <p className={`text-xs text-gray-400 ${WRAP}`}>
          Agent mode: --agents {agents ?? "unknown"}
          {surfaceName === "live" ? " (set when the server was started)" : ""}
        </p>
      )}

      {groups.map((group) => (
        <fieldset key={group} className={`space-y-2 ${WRAP}`} disabled={disabled}>
          <legend className="text-[10px] text-gray-500 uppercase mb-1">{group}</legend>
          {topLevel.filter((entry) => entry.group === group).map((entry) => (
            <FeatureRow
              key={entry.key}
              entry={entry}
              catalog={catalog}
              surface={surface}
              surfaceName={surfaceName}
              agents={agents}
              effective={effective}
              selection={selection}
              disabled={disabled}
              update={update}
            />
          ))}
        </fieldset>
      ))}

      <div aria-live="polite" className={`text-xs text-gray-400 border-t border-gray-700 pt-2 ${WRAP}`}>
        {flags.length > 0 ? (
          <>Selected: <code className={WRAP}>{flags.join(" ")}</code></>
        ) : (
          "Selected: none."
        )}
        {inherited.length > 0 && (
          <div className={WRAP}>
            Already on the server&apos;s command line: <code className={WRAP}>{inherited.join(" ")}</code>
          </div>
        )}
        {surfaceName === "batch" && agentsOverride !== null && (
          <div className={WRAP}>Agent mode: <code>--agents {agentsOverride}</code></div>
        )}
      </div>
    </div>
  );
}

function FeatureRow({
  entry, catalog, surface, surfaceName, agents, effective, selection, disabled, update,
}: {
  entry: FeatureEntry;
  catalog: FeatureCatalog;
  surface: FeatureSurface;
  surfaceName: FeatureSurfaceName;
  agents: string | null;
  effective: FeatureSelection;
  selection: FeatureSelection;
  disabled: boolean;
  update: (next: FeatureSelection) => void;
}) {
  const helpId = useId();
  const needsId = useId();
  const unmet = unmetRequirements(catalog, entry, effective, surface, agents);
  const on = isOn(entry, effective);
  const children = catalog.features.filter((child) => child.parent === entry.key);
  const described = entry.requires.length > 0 ? `${helpId} ${needsId}` : helpId;

  const control = entry.kind === "bool" ? (
    <label className={`flex items-start gap-2 text-sm text-gray-200 ${WRAP}`}>
      <input
        type="checkbox"
        className="mt-1 rounded shrink-0"
        checked={on}
        disabled={disabled || unmet.length > 0}
        aria-describedby={described}
        onChange={(event) => update({ ...selection, [entry.key]: event.target.checked })}
      />
      <span className={WRAP}>
        {entry.label} <code className="text-[10px] text-gray-500">{entry.flag}</code>
      </span>
    </label>
  ) : (
    <label className={`block text-sm text-gray-200 ${WRAP}`}>
      {entry.label} <code className="text-[10px] text-gray-500">{entry.flag}</code>
      <select
        value={typeof selection[entry.key] === "string" ? String(selection[entry.key]) : ""}
        disabled={disabled || unmet.length > 0}
        aria-describedby={described}
        onChange={(event) => {
          const next = { ...selection };
          if (event.target.value === "") delete next[entry.key];
          else next[entry.key] = event.target.value;
          update(next);
        }}
        className="block w-full max-w-full mt-1 bg-gray-700 text-gray-200 rounded px-2 py-1 text-xs border border-gray-600 disabled:opacity-50"
      >
        <option value="">Not set (the run&apos;s default: {entry.choices![0]})</option>
        {entry.choices!.map((choice) => <option key={choice} value={choice}>{choice}</option>)}
      </select>
    </label>
  );

  return (
    <div className={`space-y-1 ${WRAP}`}>
      {control}
      <p id={helpId} className={`text-[11px] text-gray-500 ${WRAP}`}>{entry.help}</p>
      {entry.requires.length > 0 && (
        <p id={needsId} className={`text-[11px] ${unmet.length > 0 ? "text-amber-300" : "text-gray-500"} ${WRAP}`}>
          {unmet.length > 0
            ? `Unavailable: ${unmet.map((req) => reasonText(req, surfaceName, agents)).join("; ")}.`
            : `Needs: ${entry.requires.map((req) => req.reason.replace(/^requires /, "")).join("; ")} (met).`}
        </p>
      )}
      {on && entry.kind === "bool" && children.map((child) => (
        <ModeSelect key={child.key} entry={child} effective={effective} selection={selection}
          disabled={disabled} update={update} />
      ))}
    </div>
  );
}

function ModeSelect({ entry, effective, selection, disabled, update }: {
  entry: FeatureEntry;
  effective: FeatureSelection;
  selection: FeatureSelection;
  disabled: boolean;
  update: (next: FeatureSelection) => void;
}) {
  const helpId = useId();
  return (
    <div className={`ml-6 ${WRAP}`}>
      <label className={`block text-xs text-gray-300 ${WRAP}`}>
        {entry.label} <code className="text-[10px] text-gray-500">{entry.flag}</code>
        <select
          value={choiceValue(entry, effective)}
          disabled={disabled}
          aria-describedby={helpId}
          onChange={(event) => update({ ...selection, [entry.key]: event.target.value })}
          className="block w-full max-w-full mt-1 bg-gray-700 text-gray-200 rounded px-2 py-1 text-xs border border-gray-600 disabled:opacity-50"
        >
          {entry.choices!.map((choice, index) => (
            <option key={choice} value={choice}>{index === 0 ? `${choice} (default)` : choice}</option>
          ))}
        </select>
      </label>
      <p id={helpId} className={`text-[11px] text-gray-500 ${WRAP}`}>{entry.help}</p>
    </div>
  );
}
