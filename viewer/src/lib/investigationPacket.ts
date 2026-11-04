/** Small, explicit, selected-turn evidence export. Never serialize raw metadata or private notes. */
import type { Bundle } from "../types";
import type { ArtifactIdentity } from "./artifactIdentity";
import { exactSnapshot, readEntityTurn } from "./historyComparison";
import { recordedTimeline } from "./investigation";
import { portableBookmarkArtifact, validInvestigationTarget, type InvestigationTarget } from "./investigationBookmarks";
export type { InvestigationTarget } from "./investigationBookmarks";

export function resolveInvestigationTarget(bundle: Bundle, target: InvestigationTarget, turn: number): string | null {
  if (!validInvestigationTarget(target) || !Number.isSafeInteger(turn) || turn < 1 || !exactSnapshot(bundle, turn))
    return "The saved turn or target is unavailable or ambiguous in this file. The current selection is kept.";
  const rows = target.kind === "region" ? bundle.world_state.regions : bundle.world_state.civilizations;
  if (rows[target.index]?.name !== target.name || rows.filter((row) => row.name === target.name).length !== 1)
    return "The saved entity identity is unavailable or ambiguous in this file. The current selection is kept.";
  if (target.kind === "civilization" && !Object.hasOwn(exactSnapshot(bundle, turn)!.civ_stats, target.name))
    return "The civilization has no recorded row at this turn. The current selection is kept.";
  return null;
}

export function investigationPacket(bundle: Bundle, identity: ArtifactIdentity | null, target: InvestigationTarget, turn: number) {
  const error = resolveInvestigationTarget(bundle, target, turn);
  if (error) throw new Error(error);
  const snapshot = exactSnapshot(bundle, turn)!;
  const snapshotIndex = bundle.history.indexOf(snapshot);
  const reading = readEntityTurn(bundle, target, turn);
  const from = Math.max(1, turn - 9);
  const reports = recordedTimeline(bundle, turn).filter((row) => row.snapshotTurn >= from && (target.kind === "region"
    ? row.event.region === target.name : row.event.actors.includes(target.name)));
  const metadata = bundle.metadata as unknown as Record<string, unknown>;
  // Values must be content hashes, not arbitrary source objects or machine-specific paths.
  const source = Object.fromEntries(["source_commit", "source_revision", "git_commit", "native_sha256"].flatMap((key) =>
    typeof metadata[key] === "string" && /^[a-f0-9]{7,64}$/.test(metadata[key]) ? [[key, metadata[key]]] : []));
  const artifact = portableBookmarkArtifact(identity);
  return {
    schema: "chronicler.investigation", version: 1,
    artifact: artifact ? { ...artifact, byteLength: identity!.byteLength } : null,
    source: Object.keys(source).length ? source : null,
    seed: Number.isSafeInteger(bundle.metadata.seed) ? bundle.metadata.seed : null,
    bundleVersion: bundle.metadata.bundle_version ?? null,
    target: { kind: target.kind, index: target.index, name: target.name },
    snapshotTurn: turn, sourceTick: turn - 1, snapshotRef: `/history/${snapshotIndex}`,
    status: reading.status, controller: reading.controller ?? null,
    observations: reading.metrics.map(({ id, label, value, note }) => ({ id, label, value, ...(note ? { note } : {}) })),
    reports: { fromSnapshot: from, throughSnapshot: turn, total: reports.length, included: Math.min(50, reports.length),
      selection: target.kind === "region" ? "Explicit region attribution only" : "Explicit named actor attribution only",
      items: reports.slice(-50).map(({ event, snapshotTurn, source }) => ({ sourceRef: source, snapshotTurn,
        sourceTick: event.turn, type: event.event_type, eventId: event.event_id ?? null })) },
    limitations: [
      "Descriptive evidence only. Nearby reports do not establish causes; references point into this exact source file.",
      "Snapshot T follows tick T−1. Missing observations remain null; no final-world outcome is substituted.",
      "Stable indices identify entities within this file only. Ambiguous names and missing snapshots are refused.",
      "At most the latest 50 explicitly attributed timeline reports in the 10-snapshot window are included; named chronicles and unexported activity are not exhaustive.",
      "This packet is not a saved world, checkpoint or reproducible experiment recipe. Private bookmark notes, raw metadata, runtime paths and credentials are excluded.",
      ...(!artifact ? ["Original file SHA-256 is unavailable: this live/in-memory selection cannot be bound to portable source bytes."] : []),
      ...(!Object.keys(source).length ? ["Source version hashes are not recorded in this bundle."] : []),
    ],
  };
}
export function investigationMarkdown(packet: ReturnType<typeof investigationPacket>): string {
  // JSON fences preserve exact strings/unknowns without interpreting names as Markdown links.
  return `# Chronicler investigation\n\nSelected observations and source references. Null means unknown.\n\n\`\`\`json\n${JSON.stringify(packet, null, 2).replace(/`/g, "\\u0060")}\n\`\`\`\n`;
}
