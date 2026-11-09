/** Per-entity descriptive comparisons. Matching evidence and missing observations stay explicit. */
import type { Bundle } from "../types";
import type { CompletedRun } from "./completedRunComparison";
import { compareReadings, exactSnapshot, NATIVE_FOOD_NOTE, readEntityTurn, type HistoryEntity } from "./historyComparison";
import { readWhatIfManifest } from "./whatIf";

export type EntityRunKind = HistoryEntity["kind"];
export const ENTITY_RUN_MEASURES = [
  { id: "population", label: "Population", kinds: ["civilization", "region"], note: "Civilization snapshot population or completed regional model population, depending on entity kind. Higher is a larger recorded count, not a welfare judgment." },
  { id: "territory", label: "Controlled regions", kinds: ["civilization"], note: "Recorded controlled-region count. Higher means more territory; no conquest, utility or success is inferred." },
  { id: "food", label: "Food / need", kinds: ["civilization", "region"], note: "Regional ratio, or unweighted mean of every recorded controlled region for a civilization. Recorded food summaries can include public relief. A regional native-ledger fallback is before public relief; differing recorded bases are not compared. This is not an overall welfare score." },
  { id: "weightedFood", label: "Population-weighted food / need", kinds: ["civilization"], note: "Recorded Phase 2 population weights and ownership; excludes unknown ratios with denominator coverage. Higher is a larger ratio, not a universal benefit." },
  { id: "treasury", label: "Treasury", kinds: ["civilization"], note: "Recorded public treasury. Higher means more stored public money, not more household wealth or overall benefit." },
  { id: "debt", label: "Outstanding debt", kinds: ["civilization"], note: "Recorded principal, already including foreign debt. Lower means less debt, not necessarily lower cost or a better outcome." },
] as const;
export type EntityRunMeasure = typeof ENTITY_RUN_MEASURES[number]["id"];
export interface EntityRunSide {
  name: string | null;
  index: number | null;
  value: number | null;
  status: string;
  note: string | null;
}
export interface EntityRunRow {
  key: string;
  name: string;
  matching: "checkpoint-index" | "name-only" | "unmatched" | "ambiguous";
  identityVerified: boolean;
  left: EntityRunSide;
  right: EntityRunSide;
  delta: number | null;
  percent: number | null;
}
export interface EntityRunMatching {
  mode: "checkpoint-index" | "observed-name";
  checkpointSha256: string | null;
  sourcePackageDigest: string | null;
  checkpointTurn: number | null;
  sharedCivilizations: number | null;
  sharedRegions: number | null;
  warnings: string[];
}
export interface EntityRunComparisonSummary {
  kind: "entity-run-descriptive-comparison";
  version: 1;
  snapshotTurn: number;
  entityKind: EntityRunKind;
  measure: EntityRunMeasure;
  measureLabel: string;
  measureNote: string;
  matching: EntityRunMatching;
  rows: EntityRunRow[];
  counts: { entities: number; numericPairs: number; unknownDifferences: number; ambiguous: number };
  limits: readonly string[];
}
export const ENTITY_RUN_LIMITS = [
  "Right minus left compares one chosen measure at an exact completed snapshot. Higher/lower is not an overall winner, utility score or causal conclusion.",
  "Only entities observed through this selected turn are listed. Missing snapshots, pruned civilization rows, shorter tails and unsupported regional observations stay unknown, never zero or carried forward.",
  "Recorded alive=false means landless/fallen in the snapshot writer; it does not prove permanent extinction. First observation is not foundation.",
  "Checkpoint matching verifies recorded metadata consistency, not checkpoint bytes or independently authenticated provenance. Equal seeds, names or array positions alone never prove shared identity.",
  "Only civilizations already present in a verified common checkpoint share indices. Post-fork appended civilizations remain separate even when names and new indices happen to agree.",
  "Name-only matches in unrelated or insufficiently documented runs have unverified identity. Ambiguous names and unrecorded aliases cannot establish a match or numeric difference.",
  "Percentage is (right−left)/abs(left) × 100. A zero left baseline has no percentage; missing and non-finite differences remain unknown.",
] as const;
const record = (value: unknown): Record<string, unknown> | null => value !== null && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : null;
const digest = (value: unknown): value is string => typeof value === "string" && /^[a-f0-9]{64}$/.test(value);
const finite = (value: number | null) => value !== null && Number.isFinite(value) ? value : null;
function stable(value: unknown): string {
  const row = record(value);
  return Array.isArray(value) ? `[${value.map(stable).join(",")}]` : row
    ? `{${Object.keys(row).sort().map((key) => `${JSON.stringify(key)}:${stable(row[key])}`).join(",")}}` : JSON.stringify(value) ?? "null";
}
const validCount = (value: unknown): value is number => typeof value === "number" && Number.isSafeInteger(value) && value >= 0;

/** Safe export: only digest/count provenance is returned, never raw headers or private paths. */
export function entityRunMatching(left: CompletedRun, right: CompletedRun): EntityRunMatching {
  const fallback: EntityRunMatching = { mode: "observed-name", checkpointSha256: null, sourcePackageDigest: null,
    checkpointTurn: null, sharedCivilizations: null, sharedRegions: null,
    warnings: ["Identity unverified: only unique observed names are matched; indices are not shared between these inputs."] };
  const rawA = record((left.bundle.metadata as unknown as Record<string, unknown>).what_if);
  const rawB = record((right.bundle.metadata as unknown as Record<string, unknown>).what_if);
  const a = readWhatIfManifest(rawA), b = readWhatIfManifest(rawB);
  if (!a || !b) return fallback;
  const ah = record(a.source.header), bh = record(b.source.header);
  const ac = record(a.source.checkpoint), bc = record(b.source.checkpoint);
  const ai = record(ah?.identity), bi = record(bh?.identity);
  const as = record(ai?.source), bs = record(bi?.source), an = record(ai?.native), bn = record(bi?.native);
  const aw = record(ah?.world), bw = record(bh?.world);
  const nativeKnown = an?.status === "absent" || (an?.status === "found" && digest(an.sha256));
  const arms = [rawA?.arm, rawB?.arm];
  const currentCompatible = (source: Record<string, unknown>, saved: Record<string, unknown> | null) => {
    if (source.current_identity == null) return true;
    const current = record(source.current_identity), savedSource = record(saved?.source), currentSource = record(current?.source);
    return current !== null && currentSource?.package_digest === savedSource?.package_digest
      && stable(record(current.native)) === stable(record(saved?.native));
  };
  const verified = arms.includes("baseline") && arms.includes("intervention") && a.request_id === b.request_id
    && a.seed === b.seed && left.bundle.metadata.seed === a.seed && right.bundle.metadata.seed === b.seed && a.start_turn === b.start_turn && a.end_turn === b.end_turn && a.mode === b.mode
    && stable(a.intervention) === stable(b.intervention)
    && ah?.exact === true && bh?.exact === true && ah.turn === a.start_turn && bh.turn === b.start_turn
    && ah.seed === a.seed && bh.seed === b.seed
    && digest(ac?.sha256) && ac.sha256 === bc?.sha256
    && digest(as?.package_digest) && as.package_digest === bs?.package_digest && stable(as) === stable(bs)
    && nativeKnown && stable(an) === stable(bn) && stable(ai) === stable(bi)
    && currentCompatible(a.source, ai) && currentCompatible(b.source, bi)
    && aw !== null && bw !== null && validCount(aw.regions) && validCount(aw.civilizations) && stable(aw) === stable(bw)
    && aw.regions === left.bundle.world_state.regions.length && aw.regions === right.bundle.world_state.regions.length
    && aw.civilizations <= left.bundle.world_state.civilizations.length && aw.civilizations <= right.bundle.world_state.civilizations.length;
  if (!verified || !aw || !ah || !as || !ac) return { ...fallback, warnings: [...fallback.warnings, "Recorded exact-pair metadata is insufficient or inconsistent; stable-index matching was refused."] };
  const compatible = (["regions", "civilizations"] as const).every((kind) => {
    const count = aw[kind] as number;
    return left.bundle.world_state[kind].slice(0, count).every((row, index) => row.name === right.bundle.world_state[kind][index].name);
  });
  if (!compatible) return { ...fallback, warnings: [...fallback.warnings, "Checkpoint entity prefixes disagree in name/order; stable-index matching was refused. No alias or reordered identity is inferred."] };
  return { mode: "checkpoint-index", checkpointSha256: ac.sha256 as string, sourcePackageDigest: as.package_digest as string,
    checkpointTurn: ah.turn as number, sharedCivilizations: aw.civilizations as number, sharedRegions: aw.regions as number,
    warnings: ["Recorded common-checkpoint metadata supports matching checkpoint-existing indices; checkpoint bytes were not independently reopened."] };
}
interface Candidate { name: string; index: number | null; ambiguous: boolean }
function candidates(bundle: Bundle, turn: number, kind: EntityRunKind): Candidate[] {
  const counts = new Map<number, number>();
  for (const row of bundle.history) if (row.turn <= turn) counts.set(row.turn, (counts.get(row.turn) ?? 0) + 1);
  const names = new Set<string>();
  for (const snapshot of bundle.history) {
    if (!Number.isSafeInteger(snapshot.turn) || snapshot.turn < 1 || snapshot.turn > turn || counts.get(snapshot.turn) !== 1) continue;
    for (const name of Object.keys(kind === "civilization" ? snapshot.civ_stats : snapshot.region_control)) names.add(name);
  }
  const world = kind === "civilization" ? bundle.world_state.civilizations : bundle.world_state.regions;
  return [...names].sort().map((name) => {
    const indices = world.flatMap((row, index) => row.name === name ? [index] : []);
    return { name, index: indices.length === 1 ? indices[0] : null, ambiguous: indices.length > 1 };
  });
}
function reading(bundle: Bundle, candidate: Candidate | null, kind: EntityRunKind, measure: EntityRunMeasure, turn: number): EntityRunSide {
  const unknown = { name: candidate?.name ?? null, index: candidate?.index ?? null, value: null, status: "Entity not observed through selected turn", note: null };
  if (!candidate) return unknown;
  if (candidate.ambiguous) return { ...unknown, status: "Ambiguous world name; numeric reading refused" };
  if (kind === "region" && candidate.index === null) return { ...unknown, status: "Historical region name has no unambiguous world index" };
  const snapshot = exactSnapshot(bundle, turn);
  if (!snapshot) return { ...unknown, status: "Exact snapshot not recorded or ambiguous" };
  const row = kind === "civilization" ? snapshot.civ_stats[candidate.name] : null;
  if (kind === "civilization" && !row) return { ...unknown, status: "Civilization row not recorded; missing/pruned values stay unknown" };
  const read = readEntityTurn(bundle, { kind, name: candidate.name }, turn);
  const metric = read.metrics.find((item) => item.id === measure);
  const ambiguousRegions = kind === "civilization" && ["food", "territory"].includes(measure) && Array.isArray(row?.regions) && row.regions.some((name) =>
    bundle.world_state.regions.filter((region) => region.name === name).length !== 1);
  return { name: candidate.name, index: candidate.index, value: ambiguousRegions ? null : metric?.value ?? null,
    status: ambiguousRegions ? "Controlled region names are unresolved or ambiguous" : kind === "region" ? "Exact regional snapshot observation"
      : row?.alive === false ? "Recorded landless/fallen (alive=false); permanence unknown" : "Exact civilization row recorded",
    note: ambiguousRegions ? "No array position or alias is invented for an ambiguous region name." : metric?.note ?? null };
}

/** Pure, JSON-ready table. Default selection is civilization population. */
export function compareEntityRuns(left: CompletedRun, right: CompletedRun, turn: number,
  kind: EntityRunKind = "civilization", measure: EntityRunMeasure = "population"): EntityRunComparisonSummary {
  const definition = ENTITY_RUN_MEASURES.find((item) => item.id === measure && (item.kinds as readonly string[]).includes(kind))
    ?? ENTITY_RUN_MEASURES[0];
  measure = definition.id;
  const matching = entityRunMatching(left, right);
  const rows: EntityRunRow[] = [];
  const validTurn = Number.isSafeInteger(turn) && turn >= 1;
  const a = validTurn ? candidates(left.bundle, turn, kind) : [], b = validTurn ? candidates(right.bundle, turn, kind) : [];
  const used = new Set<Candidate>();
  const shared = kind === "civilization" ? matching.sharedCivilizations : matching.sharedRegions;
  const eligible = (row: Candidate) => !row.ambiguous && row.index !== null && shared !== null && row.index < shared;
  const append = (first: Candidate | null, last: Candidate | null, index: number) => {
    const pairAmbiguous = first?.ambiguous || last?.ambiguous;
    const indexMatch = matching.mode === "checkpoint-index" && ((first && eligible(first)) || (last && eligible(last))) && !pairAmbiguous;
    const nameMatch = matching.mode === "observed-name" && first !== null && last !== null && !pairAmbiguous;
    const ar = reading(left.bundle, first, kind, measure, turn), br = reading(right.bundle, last, kind, measure, turn);
    const changes = compareReadings({ turn, recorded: ar.value !== null, status: ar.status, metrics: [{ id: measure, label: definition.label, value: ar.value }] },
      { turn, recorded: br.value !== null, status: br.status, metrics: [{ id: measure, label: definition.label, value: br.value }] })[0];
    const sameFoodBasis = !(kind === "region" && measure === "food" && ar.value !== null && br.value !== null)
      || (ar.note === NATIVE_FOOD_NOTE) === (br.note === NATIVE_FOOD_NOTE);
    if (!sameFoodBasis) {
      const explanation = "Food bases differ; the difference is unknown.";
      ar.note = [ar.note, explanation].filter(Boolean).join(" ");
      br.note = [br.note, explanation].filter(Boolean).join(" ");
    }
    const comparable = (indexMatch || nameMatch) && sameFoodBasis;
    const delta = comparable ? finite(changes.delta) : null;
    const percent = comparable && delta !== null ? finite(changes.percent) : null;
    rows.push({ key: `${kind}:${index}`, name: first?.name ?? last!.name,
      matching: pairAmbiguous ? "ambiguous" : indexMatch ? "checkpoint-index" : nameMatch ? "name-only" : "unmatched",
      identityVerified: !!indexMatch, left: ar, right: br, delta, percent });
  };
  for (const first of a) {
    const last = b.find((row) => !used.has(row) && (matching.mode === "observed-name" ? row.name === first.name
      : eligible(first) && eligible(row) && row.index === first.index));
    if (last) used.add(last);
    append(first, last ?? null, rows.length);
  }
  for (const last of b) if (!used.has(last)) append(null, last, rows.length);
  if (matching.mode === "observed-name" && rows.some((row) => row.matching === "name-only" && row.left.index !== row.right.index))
    matching.warnings.push("Some matched names occupy different world indices. Their identity remains unverified; equal names do not establish the same world entity.");
  return { kind: "entity-run-descriptive-comparison", version: 1, snapshotTurn: turn, entityKind: kind, measure, measureLabel: definition.label,
    measureNote: definition.note, matching, rows, counts: { entities: rows.length,
      numericPairs: rows.filter((row) => row.delta !== null).length, unknownDifferences: rows.filter((row) => row.delta === null).length,
      ambiguous: rows.filter((row) => row.matching === "ambiguous").length }, limits: ENTITY_RUN_LIMITS };
}

/** Order one chosen measure; unknown differences always follow observed differences. */
export function orderEntityRunRows(rows: EntityRunRow[], order: "higher" | "lower" | "name"): EntityRunRow[] {
  return [...rows].sort((a, b) => order === "name" ? a.name.localeCompare(b.name) || a.key.localeCompare(b.key)
    : a.delta === null ? b.delta === null ? a.name.localeCompare(b.name) : 1 : b.delta === null ? -1
      : (order === "higher" ? b.delta - a.delta : a.delta - b.delta) || a.name.localeCompare(b.name));
}
