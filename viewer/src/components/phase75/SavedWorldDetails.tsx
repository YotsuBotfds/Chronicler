import { useMemo } from "react";
import type { Bundle } from "../../types";
import type { ArtifactIdentity } from "../../lib/artifactIdentity";
import { savedWorldSummary } from "../../lib/savedWorldSummary";

export function SavedWorldDetails({ bundle, identity }: { bundle: Bundle; identity?: ArtifactIdentity | null }) {
  const summary = useMemo(() => savedWorldSummary(bundle), [bundle]);
  return <details className="saved-world-details">
    <summary>Saved world details · Seed {bundle.metadata.seed} · {summary.snapshots} recorded snapshots</summary>
    <dl>
      <div><dt>File</dt><dd>{identity?.name ?? "Live session / file identity unavailable"}</dd></div>
      <div><dt>World</dt><dd>{bundle.world_state.name}</dd></div>
      <div><dt>Seed</dt><dd>{bundle.metadata.seed}</dd></div>
      <div><dt>Recorded turns</dt><dd>{summary.first === null ? "No recorded snapshots" : `${summary.first}–${summary.last} (${summary.snapshots} snapshots)`}</dd></div>
      <div><dt>Saved final turn</dt><dd>{bundle.world_state.turn}</dd></div>
      <div><dt>Simulation mode</dt><dd>{summary.mode}</dd></div>
      <div><dt>Known enabled at save</dt><dd>{summary.enabled.join(", ") || "Unknown — no enabled systems recorded"}</dd></div>
      <div><dt>System history recorded</dt><dd>{summary.recorded.join(", ") || "No system history recorded"}</dd></div>
      <div><dt>Other history</dt><dd>{bundle.events_timeline.length} events · {bundle.named_events.length} named events · {Object.keys(bundle.chronicle_entries).length} chronicle entries</dd></div>
      <div><dt>Bundle format</dt><dd>{bundle.metadata.bundle_version ? `Version ${bundle.metadata.bundle_version}` : "Older JSON (version not recorded)"}</dd></div>
      {identity && <div><dt>File identity</dt><dd>{identity.byteLength.toLocaleString()} bytes · SHA-256 {identity.sha256 ?? "unavailable"}</dd></div>}
    </dl>
    <p>History is available only at recorded snapshots; gaps are not reconstructed. Enabled systems describe the saved state. Missing fields are unknown, and final state does not establish earlier observations. A viewable bundle cannot provide an exact CLI resume; use an exact checkpoint for continuation.</p>
  </details>;
}
