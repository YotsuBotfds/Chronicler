import { useState, useSyncExternalStore } from "react";
import type { CompletedRun } from "../lib/completedRunComparison";
import { GALLERY_LIMIT, gallerySnapshot, keepComparison, removeComparison, subscribeGallery, type ComparisonCase } from "../lib/comparisonGallery";
import { artifactBasename, whatIfInterventionLabel, type WhatIfPair } from "../lib/whatIf";

const value = (v: number | null) => v === null ? "Not recorded" : v !== 0 && Math.abs(v) < .001 ? v.toExponential(3) : v.toLocaleString(undefined, { maximumFractionDigits: 3 });
export function ComparisonGallery({ left, right, turn, pair, onOpen }: {
  left: CompletedRun | null; right: CompletedRun | null; turn: number; pair: WhatIfPair | null;
  onOpen: (entry: ComparisonCase) => void;
}) {
  const cases = useSyncExternalStore(subscribeGallery, gallerySnapshot, gallerySnapshot);
  const [title, setTitle] = useState("");
  const [message, setMessage] = useState("");
  return <section className="comparison-gallery" aria-label="Crisis comparison gallery">
    <div className="completed-compare-heading"><h3>Comparison gallery</h3>
      <button type="button" disabled={!left || !right} onClick={() => {
        if (left && right) setMessage(keepComparison(left, right, turn, pair, title));
      }}>Keep this comparison</button></div>
    <p>Keep up to {GALLERY_LIMIT} loaded or completed comparisons and reopen their selected snapshot.
      Inputs stay in memory for this browser session, including when this panel closes. Reloading the page clears them.
      Remove cases to release their retained inputs.</p>
    <label className="comparison-gallery-label">Case label (optional)<input aria-label="Gallery case label" maxLength={120} value={title}
      placeholder="e.g. Receiving service: route closure" onChange={(event) => setTitle(event.target.value)} /></label>
    {message && <p role="status">{message}</p>}
    {!cases.length ? <p>No cases kept yet. Load two real run bundles or complete a live what-if, then keep the comparison.
      Missing evidence stays unknown; cards do not rank policies or claim recovery.</p>
      : <div className="comparison-gallery-grid">{cases.map((entry) => <article key={entry.id} aria-label={`Gallery case ${entry.id}`}>
        <h4>{entry.title ?? (entry.pair ? whatIfInterventionLabel(entry.pair.manifest)
          : `${artifactBasename(entry.left.label) ?? "Left run"} / ${artifactBasename(entry.right.label) ?? "Right run"}`)}</h4>
        <p>Snapshot {entry.turn} · {entry.pair ? "Exact pair provenance recorded" : "Descriptive loaded-run comparison"}</p>
        {entry.pair && entry.turn <= entry.pair.manifest.start_turn && <p>Starting snapshot precedes the intervention; no response is shown here.</p>}
        <dl>{entry.summary.metrics.filter((metric) => ["population", "food", "treasury"].includes(metric.key)).map((metric) =>
          <div key={metric.key}><dt>{metric.label}</dt><dd>Left {value(metric.left)} · Right {value(metric.right)} · Δ {value(metric.delta)}</dd></div>)}</dl>
        <p>Food regions: left {entry.summary.foodCoverage.left}; right {entry.summary.foodCoverage.right}.
          Deltas describe recorded measures, not overall benefit.</p>
        <div className="completed-compare-actions">
          <button type="button" onClick={() => { onOpen(entry); setMessage(`Case ${entry.id} opened at snapshot ${entry.turn}.`); }}>Open case {entry.id}</button>
          <button type="button" onClick={() => { removeComparison(entry.id); setMessage("Case removed from this session."); }}>Remove case {entry.id}</button>
        </div>
      </article>)}</div>}
  </section>;
}
