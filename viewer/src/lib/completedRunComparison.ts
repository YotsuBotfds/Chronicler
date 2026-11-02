/** Descriptive completed-run comparisons, using exact recorded snapshots only. */
import type { Bundle, CivSnapshot, TurnSnapshot } from "../types";
import type { ArtifactIdentity } from "./artifactIdentity";
import { readWhatIfManifest } from "./whatIf";
import { enabledSavedSystems } from "./savedWorldSummary";
import { populationWeightedFood, readRegionalPopulation, weightedFoodNote } from "./regionalPopulation";

export interface CompletedRun { bundle: Bundle; identity: ArtifactIdentity | null; label: string }
export const RUN_METRICS = [
  { key: "population", label: "Landholding population", note: "Sum of current landholding civilizations; fallen rows are excluded." },
  { key: "regionalPopulation", label: "Regional model population", note: "Sum of completed model Region.population over every region, including uncontrolled regions; unknown in older or invalid records." },
  { key: "nativePopulation", label: "Native agents alive", note: "Sum of actual completed native pool counts; separate from regional model population, especially in shadow and demographics-only modes." },
  { key: "weightedFood", label: "Population-weighted food / need", note: "Known food ratios weighted by Phase 2 agent counts; denominator excludes unknown ratios. Phase 2 ownership and weights are not completed model or native counts." },
  { key: "food", label: "Regional food / need", note: "Unweighted mean of observed regions, not population weighted; regional coverage is shown separately." },
  { key: "short", label: "Regions short of food", note: "Food below 1; requires an observation for every region." },
  { key: "wars", label: "Active conflict pairs", note: "Unique unordered pairs in active_wars, not declarations or causes." },
  { key: "incidents", label: "Conflict event incidents", note: "Cumulative exported war, declaration, battle, siege, occupation and army-destruction reports; deduplicated by ID or exact content." },
  { key: "treasury", label: "Public treasury", note: "Sum of current landholding civilizations' treasuries." },
  { key: "debt", label: "Outstanding debt", note: "Total principal already includes foreign debt; foreign_debt and lender claims are not added again." },
  { key: "revenue", label: "Revenue this tick", note: "Sum of current landholding civilizations' recorded finance revenue." },
  { key: "economy", label: "Aggregate economy score", note: "Sum of simulation economy scores, not money, output or wealth." },
] as const;
export type RunMetric = typeof RUN_METRICS[number]["key"];
export type RunReading = Record<RunMetric, number | null> & { foodObserved: number | null; foodRegions: number; weightedFoodCoverage: string };
export interface AlignedRunPoint { turn: number; left: RunReading | null; right: RunReading | null }
const record = (value: unknown): Record<string, unknown> | null =>
  value !== null && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : null;
const finite = (value: unknown): number | null => typeof value === "number" && Number.isFinite(value) ? value : null;

function stable(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(stable).join(",")}]`;
  const row = record(value);
  return row ? `{${Object.keys(row).sort().map((key) => `${JSON.stringify(key)}:${stable(row[key])}`).join(",")}}`
    : JSON.stringify(value) ?? "null";
}

function snapshots(bundle: Bundle): Map<number, TurnSnapshot | null> {
  const result = new Map<number, TurnSnapshot | null>();
  for (const row of bundle.history) {
    if (Number.isSafeInteger(row.turn) && row.turn >= 0) result.set(row.turn, result.has(row.turn) ? null : row);
  }
  return result;
}

function landholdingRows(bundle: Bundle, snapshot: TurnSnapshot): Array<[string, CivSnapshot]> | null {
  const rows = record(snapshot.civ_stats), control = record(snapshot.region_control);
  if (!rows || !control || bundle.world_state.regions.some((region) => !(region.name in control))) return null;
  const names = new Set<string>();
  for (const owner of Object.values(control)) {
    if (owner !== null && typeof owner !== "string") return null;
    if (typeof owner === "string") names.add(owner);
  }
  for (const [name, raw] of Object.entries(rows)) {
    const row = record(raw);
    if (!row || !Array.isArray(row.regions)) return null;
    if (row.alive !== false && row.regions.length > 0) names.add(name);
  }
  const selected: Array<[string, CivSnapshot]> = [];
  for (const name of names) {
    const row = record(rows[name]);
    if (!row || row.alive === false || !Array.isArray(row.regions) || row.regions.length === 0) return null;
    selected.push([name, row as unknown as CivSnapshot]);
  }
  return selected;
}

function total(values: unknown[] | null): number | null {
  if (!values || values.some((value) => finite(value) === null)) return null;
  const sum = (values as number[]).reduce((a, b) => a + b, 0);
  return finite(sum);
}

const CONFLICT_EVENTS = new Set(["war", "war_declared", "battle", "siege_begun", "occupation", "army_destroyed"]);
function incidentTurns(bundle: Bundle): number[] {
  const unique = new Map<string, number>();
  for (const event of bundle.events_timeline) {
    if (!CONFLICT_EVENTS.has(event.event_type) || !Number.isSafeInteger(event.turn) || event.turn < 0) continue;
    const id = event.event_id ?? stable([event.turn, event.event_type, event.region, event.actors, event.description]);
    unique.set(id, event.turn + 1); // Every event tick t is reflected at snapshot t+1.
  }
  return [...unique.values()].sort((a, b) => a - b);
}

function read(bundle: Bundle, snapshot: TurnSnapshot, incidents: number[]): RunReading {
  const rows = landholdingRows(bundle, snapshot);
  const stat = (key: "population" | "treasury" | "economy") => total(rows?.map(([, row]) => row[key]) ?? null);
  const finance = record(snapshot.finance?.civs);
  const fin = (key: "debt" | "revenue") => finance
    ? total(rows?.map(([name]) => record(finance[name])?.[key]) ?? null) : null;
  const regional = readRegionalPopulation(bundle, snapshot);
  const weighted = populationWeightedFood(bundle, snapshot);
  const rawFood = snapshot.food?.sufficiency;
  const foodRegions = bundle.world_state.regions.length;
  const foodShape = Array.isArray(rawFood) && rawFood.length === foodRegions;
  const food = foodShape ? rawFood.filter((value): value is number => finite(value) !== null) : [];
  const foodTotal = total(food);
  let wars: number | null = null;
  if (Array.isArray(snapshot.active_wars) && snapshot.active_wars.every((pair) =>
    Array.isArray(pair) && pair.length === 2 && pair.every((name) => typeof name === "string") && pair[0] !== pair[1])) {
    wars = new Set(snapshot.active_wars.map((pair) => stable([...pair].sort()))).size;
  }
  return {
    regionalPopulation: regional ? total(regional.counts) : null,
    nativePopulation: regional?.agent_counts ? total(regional.agent_counts) : null,
    weightedFood: weighted.value, weightedFoodCoverage: weightedFoodNote(weighted),
    population: stat("population"), treasury: stat("treasury"), economy: stat("economy"), debt: fin("debt"), revenue: fin("revenue"),
    food: food.length && foodTotal !== null ? foodTotal / food.length : null,
    short: foodShape && food.length === foodRegions ? food.filter((value) => value < 1).length : null,
    foodObserved: foodShape ? food.length : null, foodRegions, wars,
    incidents: incidents.filter((turn) => turn <= snapshot.turn).length,
  };
}

/** Add only gap boundaries, avoiding both interpolation and huge sparse-turn allocations. */
export function alignCompletedRuns(left: Bundle, right: Bundle): AlignedRunPoint[] {
  const a = snapshots(left), b = snapshots(right);
  const turns = [...new Set([...a.keys(), ...b.keys()])].sort((x, y) => x - y);
  const expanded = new Set(turns);
  for (let i = 1; i < turns.length; i++) {
    if (turns[i] - turns[i - 1] > 1) {
      expanded.add(turns[i - 1] + 1);
      expanded.add(turns[i] - 1);
    }
  }
  const ai = incidentTurns(left), bi = incidentTurns(right);
  return [...expanded].sort((x, y) => x - y).map((turn) => ({ turn,
    left: a.get(turn) ? read(left, a.get(turn)!, ai) : null,
    right: b.get(turn) ? read(right, b.get(turn)!, bi) : null,
  }));
}

export function completedRunIdentity(run: CompletedRun) {
  const metadata = run.bundle.metadata as unknown as Record<string, unknown>;
  const world = run.bundle.world_state as unknown as Record<string, unknown>;
  const tag = readWhatIfManifest(metadata.what_if);
  const rawTag = record(metadata.what_if);
  const arm = rawTag?.arm === "baseline" || rawTag?.arm === "intervention" ? rawTag.arm : null;
  const header = tag && arm ? record(tag.source.header) : null;
  const checkpoint = record(tag?.source.checkpoint);
  const checkpointValid = header?.exact === true && header.turn === tag?.start_turn
    && header.seed === tag?.seed && typeof checkpoint?.sha256 === "string" && /^[a-f0-9]{64}$/.test(checkpoint.sha256);
  const checkpointIdentity = checkpointValid ? record(header.identity) : null;
  const checkpointConfig = checkpointValid ? record(header.run_config) : null;
  const source = Object.fromEntries(["source", "source_commit", "source_revision", "git_commit", "native_sha256"]
    .filter((key) => metadata[key] != null).map((key) => [key, metadata[key]]));
  const exportedConfiguration = record(metadata.simulation_config) ?? record(metadata.simulation_args);
  const configuration = exportedConfiguration ?? record(checkpointConfig?.simulation_args);
  const recordedPair = checkpointValid && tag ? { ...tag, arm } : null;
  const finalSettings = Object.fromEntries(["agent_mode", "tuning_overrides", "chaos_multiplier"]
    .filter((key) => key in world).map((key) => [key, world[key]]));
  const turns = snapshots(run.bundle);
  const valid = [...turns].filter(([, row]) => row !== null).map(([turn]) => turn).sort((a, b) => a - b);
  return { label: run.label, file: run.identity, world: run.bundle.world_state.name,
    seed: finite(metadata.seed), horizon: finite(metadata.total_turns), bundleVersion: finite(metadata.bundle_version),
    firstSnapshot: valid[0] ?? null, lastSnapshot: valid.at(-1) ?? null,
    snapshots: valid.length, ambiguousTurns: [...turns.values()].filter((row) => row === null).length,
    agentMode: Object.hasOwn(world, "agent_mode") && (world.agent_mode === null || world.agent_mode === "off") ? "off (aggregate)"
      : typeof world.agent_mode === "string" ? world.agent_mode : null,
    source: Object.keys(source).length ? source : checkpointIdentity,
    settings: { scenario: metadata.scenario_name ?? null, configuration, finalSettings,
      configurationOrigin: exportedConfiguration ? "bundle metadata" : configuration && tag ? `exact checkpoint at turn ${tag.start_turn}` : null,
      whatIf: recordedPair,
      enabledFinalSystems: enabledSavedSystems(world),
      models: { simulation: metadata.sim_model ?? null, narration: metadata.narrative_model ?? null,
        narratorMode: metadata.narrator_mode ?? null },
      geography: run.bundle.world_state.geography?.generator ?? null,
      regions: run.bundle.world_state.regions.length },
  };
}

export const COMPARISON_LIMITS = [
  "Descriptive comparison only. Equal seeds do not establish a controlled experiment.",
  "Snapshot T reflects completed tick T−1; event incidents use that same clock. Gaps and shorter tails stay unknown, never zero or interpolated.",
  "Civilization population, treasury and economy cover current landholding civilizations only. Totals require every relevant current row; no fallen civilization is carried forward.",
  "Observed food is an unweighted regional mean, not a population-weighted measure. Population-weighted food uses only recorded Phase 2 agent counts and ownership with known ratios; unknown ratios are excluded and denominator coverage is reported. Missing weights or a zero denominator stays unknown. Neither completed model population nor completed native counts substitute for Phase 2 weights.",
  "Event incidents cover the exported timeline only; repeated IDs or exact duplicate reports count once. They are not war counts or causal evidence.",
  "Source versions and full initial settings often are not embedded. Final-world settings may have changed during a run; final-world outcome values are never used.",
];

export function comparisonWarnings(left: CompletedRun, right: CompletedRun): string[] {
  const a = completedRunIdentity(left), b = completedRunIdentity(right);
  const warnings = [COMPARISON_LIMITS[0]];
  for (const [key, label] of [["seed", "Seeds"], ["horizon", "Recorded horizons"], ["bundleVersion", "Bundle formats"], ["agentMode", "Agent modes"],
    ["source", "Source versions"], ["settings", "Recorded settings"]] as const) {
    if (a[key] === null || b[key] === null) warnings.push(`${label}: not recorded for one or both inputs.`);
    else if (stable(a[key]) !== stable(b[key])) warnings.push(`${label} differ.`);
  }
  if (!a.file?.sha256 || !b.file?.sha256) warnings.push("An original-file SHA-256 is not recorded for one or both inputs.");
  if (a.settings.whatIf || b.settings.whatIf) warnings.push("What-if configuration is recorded at the common checkpoint; earlier interventions may have changed it. Compare subsequent snapshots for the labeled control, not the unchanged starting snapshot.");
  if (!a.settings.configuration || !b.settings.configuration) warnings.push("Full initial simulation settings are not recorded; matching final settings cannot establish equivalence.");
  if (a.ambiguousTurns || b.ambiguousTurns) warnings.push("Duplicate snapshot turns are ambiguous and excluded.");
  if (a.firstSnapshot !== b.firstSnapshot || a.lastSnapshot !== b.lastSnapshot) warnings.push("Recorded snapshot ranges differ; shorter tails and gaps remain unknown.");
  for (const [name, id] of [["Left", a], ["Right", b]] as const) {
    if (id.lastSnapshot !== id.horizon) warnings.push(`${name} history does not end at its recorded horizon; completion cannot be verified from these snapshots.`);
  }
  return warnings;
}

export function completedComparisonSummary(left: CompletedRun, right: CompletedRun, points: AlignedRunPoint[], turn: number) {
  const at = points.find((point) => point.turn === turn);
  return { kind: "completed-run-descriptive-comparison", version: 1,
    inputs: { left: completedRunIdentity(left), right: completedRunIdentity(right) },
    warnings: comparisonWarnings(left, right), limits: COMPARISON_LIMITS, snapshotTurn: turn,
    foodCoverage: { left: at?.left ? `${at.left.foodObserved ?? "unknown"}/${at.left.foodRegions}` : "Not recorded",
      right: at?.right ? `${at.right.foodObserved ?? "unknown"}/${at.right.foodRegions}` : "Not recorded" },
    weightedFoodCoverage: { left: at?.left?.weightedFoodCoverage ?? "Not recorded", right: at?.right?.weightedFoodCoverage ?? "Not recorded" },
    metrics: RUN_METRICS.map((metric) => {
      const a = at?.left?.[metric.key] ?? null, b = at?.right?.[metric.key] ?? null;
      return { ...metric, left: a, right: b, delta: a !== null && b !== null ? b - a : null,
        coverage: { left: points.filter((point) => point.left?.[metric.key] != null).length,
          right: points.filter((point) => point.right?.[metric.key] != null).length,
          leftSnapshots: left.bundle.history.length, rightSnapshots: right.bundle.history.length } };
    }),
  };
}

export function comparisonMarkdown(summary: ReturnType<typeof completedComparisonSummary>): string {
  const text = (value: unknown) => String(value ?? "Not recorded").replace(/[|\r\n]/g, " ");
  const lines = ["# Completed-run comparison", "", ...summary.limits.map((line) => `- ${line}`), "",
    "## Inputs", "", "| Input | File | SHA-256 (original bytes) | Seed | Horizon | Agent mode | Source |",
    "|---|---|---|---|---|---|---|"];
  for (const [side, input] of Object.entries(summary.inputs)) lines.push(
    `| ${side} | ${text(input.file?.name ?? input.label)} | ${text(input.file?.sha256)} | ${text(input.seed)} | ${text(input.horizon)} | ${text(input.agentMode)} | ${text(input.source ? stable(input.source) : null)} |`);
  lines.push("", "## Recorded settings", "", "```json", JSON.stringify({ left: summary.inputs.left.settings,
    right: summary.inputs.right.settings }, null, 2), "```", "", "## Warnings", "",
    ...summary.warnings.map((line) => `- ${line}`), "", `## Snapshot ${summary.snapshotTurn}`, "",
    `Observed food regions: left ${summary.foodCoverage.left}; right ${summary.foodCoverage.right}.`, "",
    `Weighted food left: ${summary.weightedFoodCoverage.left}`, `Weighted food right: ${summary.weightedFoodCoverage.right}`, "",
    "| Metric | Left | Right | Right − left | Recorded snapshots left / right |", "|---|---|---|---|---|");
  for (const metric of summary.metrics) lines.push(`| ${metric.label} | ${text(metric.left)} | ${text(metric.right)} | ${text(metric.delta)} | ${metric.coverage.left}/${metric.coverage.leftSnapshots} / ${metric.coverage.right}/${metric.coverage.rightSnapshots} |`);
  lines.push("", ...summary.metrics.map((metric) => `- ${metric.label}: ${metric.note}`));
  return lines.join("\n") + "\n";
}
