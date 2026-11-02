import { memo, useEffect, useMemo, useRef, useState } from "react";
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { Bundle } from "../types";
import type { ArtifactIdentity } from "../lib/artifactIdentity";
import { decodeBundleBytes } from "../lib/bundleFile";
import {
  alignCompletedRuns, COMPARISON_LIMITS, completedComparisonSummary, completedRunIdentity, comparisonMarkdown,
  RUN_METRICS, type AlignedRunPoint, type CompletedRun, type RunMetric,
} from "../lib/completedRunComparison";
import "./completedRunCompare.css";

import { EntityRunComparison } from "./EntityRunComparison";
import { artifactBasename, portableRuntime, portableSettings, portableWhatIfManifest,
  whatIfArmLabel, whatIfInterventionLabel, type WhatIfPair } from "../lib/whatIf";

type Side = "left" | "right";
interface Slot { run: CompletedRun | null; error: string | null; loading: boolean }
const value = (number: number | null | undefined) => number == null ? "Not recorded"
  : number.toLocaleString(undefined, { maximumFractionDigits: 3 });

/** Sharing keeps named settings and content identities, never arbitrary metadata. */
function shareIdentity(input: ReturnType<typeof completedRunIdentity>) {
  const word = (value: unknown) => typeof value === "string" && /^[A-Za-z0-9_.+-]{1,120}$/.test(value) ? value : null;
  const modes = ["off", "off (aggregate)", "hybrid", "shadow", "demographics-only"];
  const rawSource = input.source as Record<string, unknown> | null;
  let source = portableRuntime(rawSource);
  if (!source && rawSource) {
    source = {};
    for (const key of ["source_commit", "source_revision", "git_commit", "native_sha256"]) {
      const item = rawSource[key];
      if (typeof item === "string" && /^[a-f0-9]{40,64}$/.test(item)) source[key] = item;
    }
    const nested = rawSource.source;
    if (nested && typeof nested === "object" && !Array.isArray(nested)) {
      const known = nested as Record<string, unknown>;
      source.source = Object.fromEntries(Object.entries(known).filter(([key, item]) =>
        ["git_sha", "package_digest"].includes(key) && typeof item === "string" && /^[a-f0-9]{40,64}$/.test(item)));
    }
    if (!Object.keys(source).length) source = null;
  }
  const final = input.settings.finalSettings;
  const safeFinal = { ...portableSettings({ tuning_overrides: final.tuning_overrides }),
    ...(modes.includes(final.agent_mode as string) ? { agent_mode: final.agent_mode } : {}),
    ...(typeof final.chaos_multiplier === "number" && Number.isFinite(final.chaos_multiplier)
      ? { chaos_multiplier: final.chaos_multiplier } : {}) };
  return { ...input, label: artifactBasename(input.label) ?? "Run", world: artifactBasename(input.world) ?? "Not recorded",
    agentMode: modes.includes(input.agentMode ?? "") ? input.agentMode : null, source,
    file: input.file ? { name: artifactBasename(input.file.name) ?? "bundle.json", byteLength: input.file.byteLength,
      sha256: input.file.sha256 && /^[a-f0-9]{64}$/.test(input.file.sha256) ? input.file.sha256 : null } : null,
    settings: { ...input.settings, scenario: artifactBasename(input.settings.scenario),
      configuration: input.settings.configuration ? portableSettings(input.settings.configuration) : null,
      finalSettings: safeFinal,
      whatIf: input.settings.whatIf ? { ...portableWhatIfManifest(input.settings.whatIf), arm: input.settings.whatIf.arm } : null,
      models: { simulation: word(input.settings.models.simulation), narration: word(input.settings.models.narration),
        narratorMode: word(input.settings.models.narratorMode) },
      geography: word(input.settings.geography) } };
}

export function CompletedRunCompare({ initialBundle, initialIdentity, initialPair }: {
  initialPair?: WhatIfPair | null;
  initialBundle?: Bundle | null; initialIdentity?: ArtifactIdentity | null;
}) {
  const [slots, setSlots] = useState<Record<Side, Slot>>(() => ({
    left: { run: initialPair?.baseline ?? null, error: null, loading: false },
    right: { run: initialPair?.intervention ?? (initialBundle ? { bundle: initialBundle, identity: initialIdentity ?? null,
      label: initialIdentity?.name ?? "Current viewer bundle" } : null), error: null, loading: false },
  }));
  const pending = useRef({ left: 0, right: 0 });
  useEffect(() => {
    const requests = pending.current;
    return () => { requests.left++; requests.right++; };
  }, []);
  const [selectedTurn, setSelectedTurn] = useState<number | null>(null);
  const [financialMetric, setFinancialMetric] = useState<RunMetric>("treasury");
  const [exportStatus, setExportStatus] = useState("");
  const left = slots.left.run, right = slots.right.run;
  const points = useMemo(() => left && right ? alignCompletedRuns(left.bundle, right.bundle) : [], [left, right]);
  const shared = points.filter((point) => point.left && point.right);
  const turn = selectedTurn !== null && points.some((point) => point.turn === selectedTurn) ? selectedTurn
    : shared.at(-1)?.turn ?? points.at(-1)?.turn ?? 0;
  const summary = useMemo(() => left && right ? completedComparisonSummary(left, right, points, turn) : null,
    [left, right, points, turn]);

  const pairManifest = initialPair && left === initialPair.baseline && right === initialPair.intervention
    ? initialPair.manifest : null;
  const safeSummary = summary ? { ...summary, inputs: { left: shareIdentity(summary.inputs.left), right: shareIdentity(summary.inputs.right) } } : null;
  const safeManifest = pairManifest ? portableWhatIfManifest(pairManifest) : null;
  const shareSummary = safeSummary && safeManifest ? { ...safeSummary, what_if: safeManifest } : safeSummary;
  function shareMarkdown() {
    return safeSummary ? comparisonMarkdown(safeSummary) + (safeManifest
      ? "\n## Exact what-if provenance\n\nOne deterministic pair; no claim of general benefit. The override follows the starting snapshot.\n\n```json\n"
        + JSON.stringify(safeManifest, null, 2) + "\n```\n" : "") : "";
  }

  async function load(side: Side, file: File) {
    const request = ++pending.current[side];
    setSlots((current) => ({ ...current, [side]: { ...current[side], error: null, loading: true } }));
    try {
      const decoded = await decodeBundleBytes(file.name, await file.arrayBuffer());
      if (!decoded.bundle) throw new Error(decoded.error ?? "This file is not a supported completed-run bundle.");
      if (pending.current[side] !== request) return;
      setSlots((current) => ({ ...current, [side]: { run: { bundle: decoded.bundle!, identity: decoded.identity,
        label: file.name }, error: null, loading: false } }));
      setExportStatus("");
    } catch (error) {
      if (pending.current[side] !== request) return;
      setSlots((current) => ({ ...current, [side]: { ...current[side], loading: false,
        error: error instanceof Error ? error.message : "Could not read this file." } }));
    }
  }

  function download(format: "json" | "markdown") {
    if (!summary) return;
    const blob = new Blob([format === "json" ? JSON.stringify(shareSummary, null, 2) + "\n" : shareMarkdown()],
      { type: format === "json" ? "application/json" : "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `completed-run-comparison.${format === "json" ? "json" : "md"}`;
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 0);
  }

  async function copy() {
    if (!summary) return;
    try {
      await navigator.clipboard.writeText(shareMarkdown());
      setExportStatus("Comparison copied as Markdown.");
    } catch {
      setExportStatus("Copy is unavailable here. Download the summary instead.");
    }
  }

  return <div className="completed-compare" aria-label="Completed-run comparison">
    {pairManifest && <aside aria-label="What-if provenance" className="completed-compare-warnings">
      <strong>Exact checkpoint pair: {whatIfInterventionLabel(pairManifest)}</strong>
      <p>Common starting turn {pairManifest.start_turn}; {pairManifest.turns} additional turns.
        The starting snapshot precedes the override. This pair describes one bounded case, not general balance.</p>
    </aside>}
    <p className="completed-compare-intro">Compare two saved run bundles. Files stay in this browser; no simulation or narration runs.</p>
    <div className="completed-compare-inputs">
      {(["left", "right"] as const).map((side) => <section key={side} className="completed-compare-input"
        onDragOver={(event) => event.preventDefault()} onDrop={(event) => {
          event.preventDefault(); const file = event.dataTransfer.files[0]; if (file) void load(side, file);
        }} aria-label={`${side === "left" ? "Left" : "Right"} run`}>
        <div className="completed-compare-heading"><h3>{side === "left" ? "Left run" : "Right run"}</h3>
          <label className="completed-compare-load">Load {side} run
            <input type="file" accept=".json,application/json" aria-label={`Load ${side} run`} onChange={(event) => {
              const file = event.target.files?.[0]; event.target.value = ""; if (file) void load(side, file);
            }} />
          </label>
        </div>
        {slots[side].loading && <p role="status">Reading run…</p>}
        {slots[side].error && <p role="alert">{slots[side].error} Previously loaded runs are kept.</p>}
        {slots[side].run ? <RunIdentity run={slots[side].run} />
          : <p>Drop a chronicle bundle here, or choose a file above.</p>}
      </section>)}
    </div>
    {summary ? <>
      <aside className="completed-compare-warnings" aria-label="Comparison warnings">
        <ul>{summary.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul>
      </aside>
      <p>Snapshot T reflects completed tick T−1. Lines stop at missing observations; no values are interpolated.</p>
      <EntityRunComparison left={left!} right={right!} turn={turn} />
      <div className="completed-compare-charts">
        <Trajectory points={points} metric="population" />
        <Trajectory points={points} metric="food" />
        <Trajectory points={points} metric="weightedFood" />
        <div><label className="completed-compare-select">Additional trajectory
          <select value={financialMetric} onChange={(event) => setFinancialMetric(event.target.value as RunMetric)}>
            {RUN_METRICS.filter((metric) => !["population", "food", "weightedFood"].includes(metric.key)).map((metric) =>
              <option key={metric.key} value={metric.key}>{metric.label}</option>)}
          </select></label><Trajectory points={points} metric={financialMetric} />
        </div>
      </div>
      <section className="completed-compare-endpoint">
        <div className="completed-compare-heading"><h3>At the same recorded turn</h3>
          <label>Snapshot <select aria-label="Comparison snapshot" value={turn} onChange={(event) => setSelectedTurn(Number(event.target.value))}>
            {points.map((point) => <option value={point.turn} key={point.turn}>{point.turn}
              {point.left && point.right ? " · both runs" : " · missing observations"}</option>)}
          </select></label>
        </div>
        <p>Food regions observed: left {summary.foodCoverage.left}; right {summary.foodCoverage.right}.</p>
        <p>Weighted food left: {summary.weightedFoodCoverage.left}</p>
        <p>Weighted food right: {summary.weightedFoodCoverage.right}</p>
        {shared.length === 0 && <p>No unambiguous snapshot turn is shared. Cross-run differences stay unknown.</p>}
        <div className="completed-compare-table-wrap" role="region" aria-label="Scrollable run metrics" tabIndex={0}>
          <table aria-label={`Run metrics at snapshot ${turn}`}>
          <thead><tr><th>Metric</th><th>Left</th><th>Right</th><th>Right − left</th><th>Observed snapshots: left / right</th></tr></thead>
          <tbody>{summary.metrics.map((metric) => <tr key={metric.key}>
            <th scope="row" title={metric.note}>{metric.label}</th><td>{value(metric.left)}</td><td>{value(metric.right)}</td>
            <td>{value(metric.delta)}</td><td>{metric.coverage.left}/{metric.coverage.leftSnapshots} / {metric.coverage.right}/{metric.coverage.rightSnapshots}</td>
          </tr>)}</tbody>
        </table></div>
      </section>
      <details><summary>Metric definitions and source limits</summary><ul>{RUN_METRICS.map((metric) =>
        <li key={metric.key}><strong>{metric.label}:</strong> {metric.note}</li>)}
        {COMPARISON_LIMITS.slice(1).map((limit) => <li key={limit}>{limit}</li>)}</ul></details>
      <div className="completed-compare-actions" aria-label="Share comparison">
        <button type="button" onClick={() => download("json")}>Download JSON</button>
        <button type="button" onClick={() => download("markdown")}>Download Markdown</button>
        <button type="button" onClick={() => void copy()}>Copy Markdown</button>
        <span role="status">{exportStatus}</span>
      </div>
    </> : <p className="completed-compare-warnings">{COMPARISON_LIMITS[0]} Load both runs to see aligned trajectories and a shareable summary.</p>}
  </div>;
}

function RunIdentity({ run }: { run: CompletedRun }) {
  const identity = completedRunIdentity(run);
  return <div className="completed-compare-identity">
    <strong>{run.label}</strong>
    <dl><dt>World</dt><dd>{identity.world}</dd>
      <dt>Seed / recorded horizon</dt><dd>{value(identity.seed)} / {value(identity.horizon)}</dd>
      <dt>Snapshots</dt><dd>{identity.firstSnapshot ?? "None"}–{identity.lastSnapshot ?? "None"} ({identity.snapshots} unambiguous)</dd>
      {identity.settings.whatIf && <><dt>Recorded what-if arm</dt><dd>
        {identity.settings.whatIf.arm === "baseline" ? "Unchanged continuation; no override. Paired control:" : `${whatIfArmLabel(identity.settings.whatIf)}:`}
        {whatIfInterventionLabel(identity.settings.whatIf)};
        turns {identity.settings.whatIf.start_turn}–{identity.settings.whatIf.end_turn}
      </dd></>}
      <dt>Agent mode</dt><dd>{identity.agentMode ?? "Not recorded"}</dd>
      <dt>Bundle format version</dt><dd>{value(identity.bundleVersion)}</dd>
      <dt>File bytes</dt><dd>{value(run.identity?.byteLength)}</dd>
      <dt>SHA-256 · original bytes</dt><dd><code>{run.identity?.sha256 ?? "Not recorded"}</code></dd>
      <dt>Source version</dt><dd><code>{identity.source ? JSON.stringify(identity.source) : "Not recorded"}</code></dd>
    </dl>
    <details><summary>Recorded settings</summary><pre>{JSON.stringify(identity.settings, null, 2)}</pre>
      <p>Final settings may differ from initial settings. Missing configuration is unknown.</p></details>
  </div>;
}

const Trajectory = memo(function Trajectory({ points, metric }: { points: AlignedRunPoint[]; metric: RunMetric }) {
  const definition = RUN_METRICS.find((entry) => entry.key === metric)!;
  const data = points.map((point) => ({ turn: point.turn, left: point.left?.[metric] ?? null, right: point.right?.[metric] ?? null }));
  const observed = data.some((point) => point.left !== null || point.right !== null);
  return <section className="completed-compare-trajectory" aria-label={`${definition.label} trajectory`}>
    <h4>{definition.label}</h4>
    {observed ? <ResponsiveContainer width="100%" height={190}>
      <LineChart data={data} margin={{ left: 4, right: 12, top: 6, bottom: 4 }}>
        <CartesianGrid stroke="#363938" strokeDasharray="3 3" /><XAxis dataKey="turn" type="number" domain={["dataMin", "dataMax"]} />
        <YAxis width={55} /><Tooltip /><Legend />
        <Line name="Left run" dataKey="left" stroke="#7ebec3" type="linear" connectNulls={false} isAnimationActive={false} dot={{ r: 1.5 }} />
        <Line name="Right run" dataKey="right" stroke="#e0b14c" type="linear" connectNulls={false} isAnimationActive={false} dot={{ r: 1.5 }} />
      </LineChart>
    </ResponsiveContainer> : <p>No observations recorded in either run.</p>}
    <p>{definition.note}</p>
  </section>;
});
