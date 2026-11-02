import type { Bundle } from "../types";
import { identifyArtifact, type ArtifactIdentity } from "./artifactIdentity";
import type { CompletedRun } from "./completedRunComparison";
import { classifyParsedBundlePayload } from "./bundleLoader";

interface WhatIfManifestBase {
  request_id: string;
  source: Record<string, unknown>;
  mode: string;
  seed: number;
  start_turn: number;
  end_turn: number;
  turns: number;
  semantics: "exact_checkpoint_pair";
}
export type WhatIfManifest = WhatIfManifestBase & (
  { schema_version: 1; intervention: { command: "set"; civ: string; stat: "stability"; before: number; value: number } }
  | { schema_version: 2; intervention: { command: "set"; civ: "@world";
      stat: "grain_reserves.shortfall_priority"; before: 0 | 1; value: 0 | 1; scope: "world" } }
  | { schema_version: 3; intervention: { command: "set"; civ: "@transport"; stat: "lab.transport_disruption";
      before: number; value: number; scope: "region"; region_id: number; region_name: string; duration: number;
      prior_counter: number; effective_counter: number; effective_through_turn: number } }
);
export interface WhatIfPair {
  manifest: WhatIfManifest;
  baseline: CompletedRun;
  intervention: CompletedRun;
}
export interface WhatIfStatus {
  request_id: string;
  state: "preparing" | "prepared" | "running" | "completed" | "cancelled" | "error";
  arm?: string;
  message?: string;
  manifest?: WhatIfManifest;
  pair?: WhatIfPair;
}
export interface WhatIfControls {
  status: WhatIfStatus | null;
  connected: boolean;
  prepare: (civ: string, value: number, turns: number) => void;
  preparePolicy: (value: 0 | 1, turns: number) => void;
  prepareTransport: (regionId: number, duration: number, turns: number) => void;
  /** Current server bundle, used only for eligibility and recipe checks. */
  bundle?: Bundle | null;
  run: () => void;
  cancel: () => void;
}
export function whatIfActive(status: WhatIfStatus | null | undefined): boolean {
  return !!status && ["preparing", "prepared", "running"].includes(status.state);
}
function record(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
const binary = (value: unknown): value is 0 | 1 => value === 0 || value === 1;
export const validWhatIfHorizon = (turns: number) => Number.isSafeInteger(turns) && turns >= 1 && turns <= 20;
export function granaryPolicyValue(bundle?: Bundle | null): 0 | 1 | null {
  if (!bundle) return null;
  const world = bundle.world_state as unknown as Record<string, unknown>;
  if (world.agent_mode !== "hybrid") return null;
  if (!record(world.grain_reserves) || !Array.isArray(world.grain_reserves.granaries)) return null;
  const value = record(world.tuning_overrides) ? world.tuning_overrides["grain_reserves.shortfall_priority"] ?? 0 : 0;
  return binary(value) ? value : null;
}
/** Region indices are authoritative; an ambiguous or non-hybrid world cannot prepare this control. */
export function transportRegions(bundle?: Bundle | null): Array<{ id: number; name: string }> {
  if (!bundle || (bundle.world_state as unknown as Record<string, unknown>).agent_mode !== "hybrid"
    || !Array.isArray(bundle.world_state.regions)) return [];
  const regions = bundle.world_state.regions;
  if (!regions.length || regions.some((r) => !r || typeof r.name !== "string" || !r.name.trim()
    || r.name.length > 200 || /[\r\n\0]/.test(r.name)) || new Set(regions.map((r) => r.name)).size !== regions.length) return [];
  return regions.map((r, id) => ({ id, name: r.name }));
}
export const validTransportDuration = (duration: number) => Number.isSafeInteger(duration) && duration >= 1 && duration <= 6;

export function whatIfInterventionLabel(manifest: WhatIfManifest): string {
  if (manifest.schema_version === 3) {
    const a = manifest.intervention;
    return `Transport disruption: ${a.region_name} (#${a.region_id}), ${a.duration} turns; existing counter ${a.prior_counter}, effective counter ${a.effective_counter}, through simulation turn ${a.effective_through_turn}`;
  }
  if (manifest.schema_version === 2) {
    const a = manifest.intervention;
    return `World granary priority: ${a.before === 0 ? "reserve fill first (0)" : "shortfall first (1)"} → ${a.value === 0 ? "reserve fill first (0)" : "shortfall first (1)"}`;
  }
  return `${manifest.intervention.civ}: stability ${manifest.intervention.before} → ${manifest.intervention.value}`;
}
export function whatIfArmLabel(manifest: WhatIfManifest): string {
  return manifest.schema_version === 3 ? "Regional transport disruption" : manifest.schema_version === 2 ? "Global granary priority intervention" : "Stability intervention";
}
export function readWhatIfManifest(value: unknown): WhatIfManifest | null {
  if (!record(value) || ![1, 2, 3].includes(value.schema_version as number) || value.semantics !== "exact_checkpoint_pair"
    || typeof value.request_id !== "string" || !/^[A-Za-z0-9_-]{1,80}$/.test(value.request_id)
    || !record(value.source) || typeof value.mode !== "string"
    || !Number.isSafeInteger(value.seed) || !Number.isSafeInteger(value.start_turn) || (value.start_turn as number) < 0
    || !Number.isSafeInteger(value.end_turn) || !validWhatIfHorizon(value.turns as number)
    || (value.end_turn as number) !== (value.start_turn as number) + (value.turns as number)
    || !record(value.intervention)) return null;
  const action = value.intervention;
  const allowed = value.schema_version === 1 ? ["command", "civ", "stat", "before", "value"]
    : value.schema_version === 2 ? ["command", "civ", "stat", "before", "value", "scope"]
    : ["command", "civ", "stat", "before", "value", "scope", "region_id", "region_name", "duration", "prior_counter", "effective_counter", "effective_through_turn"];
  if (Object.keys(action).some((key) => !allowed.includes(key)) || action.command !== "set") return null;
  if (value.schema_version === 1) {
    if (action.stat !== "stability" || typeof action.civ !== "string" || !action.civ
      || /[\r\n]/.test(action.civ) || action.civ.includes("\0") || !Number.isFinite(action.before) || !Number.isInteger(action.value)
      || (action.value as number) < 1 || (action.value as number) > 100) return null;
  } else if (value.schema_version === 2) {
    if (value.mode !== "hybrid" || action.stat !== "grain_reserves.shortfall_priority"
      || action.civ !== "@world" || action.scope !== "world" || !binary(action.before) || !binary(action.value)) return null;
  } else if (value.mode !== "hybrid" || action.stat !== "lab.transport_disruption" || action.civ !== "@transport" || action.scope !== "region"
    || !Number.isSafeInteger(action.region_id) || (action.region_id as number) < 0 || typeof action.region_name !== "string"
    || !action.region_name.trim() || action.region_name.length > 200 || /[\r\n\0]/.test(action.region_name)
    || !validTransportDuration(action.duration as number) || !Number.isSafeInteger(action.value)
    || action.value !== (action.region_id as number) * 10 + (action.duration as number)
    || !Number.isSafeInteger(action.prior_counter) || (action.prior_counter as number) < 0 || action.before !== action.prior_counter
    || !Number.isSafeInteger(action.effective_counter) || action.effective_counter !== Math.max(action.prior_counter as number, (action.duration as number) + 1)
    || !Number.isSafeInteger(action.effective_through_turn) || action.effective_through_turn !== (value.start_turn as number) + (action.effective_counter as number) - 2) return null;
  return value as unknown as WhatIfManifest;
}
function readArm(value: unknown, label: string): CompletedRun | null {
  if (!record(value) || !record(value.identity)) return null;
  const identity = value.identity;
  if (typeof identity.name !== "string" || !Number.isInteger(identity.byteLength)
    || (identity.byteLength as number) < 1 || typeof identity.sha256 !== "string"
    || !/^[a-f0-9]{64}$/.test(identity.sha256)) return null;
  const parsed = classifyParsedBundlePayload(value.bundle);
  if (parsed.kind !== "legacy") return null;
  return { bundle: parsed.bundle as Bundle, identity: identity as unknown as ArtifactIdentity, label };
}
export function readWhatIfResult(value: unknown): WhatIfPair | null {
  if (!record(value)) return null;
  const manifest = readWhatIfManifest(value.manifest);
  if (value.request_id !== undefined && value.request_id !== manifest?.request_id) return null;
  const baseline = readArm(value.baseline, "Unchanged continuation");
  const intervention = readArm(value.intervention, manifest ? whatIfArmLabel(manifest) : "Intervention");
  return manifest && baseline && intervention ? { manifest, baseline, intervention } : null;
}

const SHA256 = /^[a-f0-9]{64}$/;
const exactKeys = (value: Record<string, unknown>, keys: string[]) => Object.keys(value).length === keys.length
  && Object.keys(value).every((key) => keys.includes(key));
const plain = (value: unknown): value is string => typeof value === "string" && value.length > 0 && value.length <= 200
  && !/[\r\n]/.test(value) && !value.includes("\0");
/** Export file identities as basenames. Imports already require this form. */
export function artifactBasename(value: unknown): string | null {
  if (!plain(value)) return null;
  const name = value.replace(/\\/g, "/").split("/").at(-1) ?? "";
  return name && name !== "." && name !== ".." && !/[?:#]/.test(name) ? name : null;
}
export function portableArtifact(value: unknown): ArtifactIdentity | null {
  if (!record(value)) return null;
  const name = artifactBasename(value.name);
  return name && Number.isSafeInteger(value.byteLength) && (value.byteLength as number) > 0
    && typeof value.sha256 === "string" && SHA256.test(value.sha256)
    ? { name, byteLength: value.byteLength as number, sha256: value.sha256 } : null;
}
const safeWord = (value: unknown): value is string => typeof value === "string" && /^[A-Za-z0-9_.+:-]{1,120}$/.test(value);
const SETTING_KEYS = ["agents", "agent_scale_mode", "worldgen", "regions", "civs", "turns", "reflection_interval",
  "aggression_bias", "cultural_drift_speed", "religion_intensity", "resource_abundance", "secession_likelihood",
  "severity_multiplier", "tech_diffusion_rate", "trade_friction", "campaigns", "capacity_aware_refugees",
  "cities", "community_anchoring", "contact_ledger", "diplomacy", "domestic_credit", "epidemiology", "finance",
  "fisheries", "governance", "gp_agendas", "grain_reserves", "guilds", "harvest_forecasts", "health_care",
  "historiography", "languages", "maritime", "mutual_aid", "nomads", "ritual_gatherings", "scholarship",
  "scientific_claims", "scientific_research_agendas", "techniques", "transaction_receipts", "public_grain_shipments",
  "decision_ablation", "ablation_start_turn", "preset"];
/** Display known settings only; the recipe hash binds the complete raw config. */
export function portableSettings(value: unknown): Record<string, unknown> {
  if (!record(value)) return {};
  const out: Record<string, unknown> = {};
  for (const key of SETTING_KEYS) {
    const item = value[key];
    if (item === null || typeof item === "boolean" || typeof item === "number" && Number.isFinite(item)
      || safeWord(item)) out[key] = item;
  }
  for (const key of ["scenario", "tuning"]) {
    if (value[key] === null) out[key] = null;
    else if (artifactBasename(value[key])) out[key] = artifactBasename(value[key]);
  }
  if (record(value.tuning_overrides)) {
    out.tuning_overrides = Object.fromEntries(Object.entries(value.tuning_overrides)
      .filter(([key, item]) => key === "grain_reserves.shortfall_priority" && binary(item)));
  }
  return out;
}
/** Fixed identity fields only: no package directories, endpoints or credentials. */
export function portableRuntime(value: unknown): Record<string, unknown> | null {
  if (!record(value) || !record(value.source) || !record(value.native) || !record(value.environment)) return null;
  const source = value.source, native = value.native, env = value.environment;
  if (typeof source.package_digest !== "string" || !SHA256.test(source.package_digest)
    || !(source.git_sha === null || typeof source.git_sha === "string" && /^[a-f0-9]{40}$/.test(source.git_sha))
    || !["found", "absent"].includes(native.status as string)
    || !safeWord(env.python) || !safeWord(env.implementation) || !safeWord(env.machine)) return null;
  const nativeOut: Record<string, unknown> = { status: native.status };
  if (native.status === "found") {
    if (typeof native.sha256 !== "string" || !SHA256.test(native.sha256)
      || !Number.isSafeInteger(native.bytes) || (native.bytes as number) < 1) return null;
    nativeOut.sha256 = native.sha256; nativeOut.bytes = native.bytes;
  }
  if (record(native.state_layouts)) nativeOut.state_layouts = Object.fromEntries(
    Object.entries(native.state_layouts).filter(([key, item]) => ["agent", "ecology", "politics"].includes(key)
      && typeof item === "string" && /^v\d+:[a-f0-9]+$/.test(item)));
  const environment: Record<string, unknown> = { python: env.python, implementation: env.implementation, machine: env.machine };
  if (Number.isSafeInteger(env.affinity_cpu_count) && (env.affinity_cpu_count as number) > 0) environment.affinity_cpu_count = env.affinity_cpu_count;
  if (env.hash_seed === "0") environment.hash_seed = "0";
  if (record(env.packages)) environment.packages = Object.fromEntries(Object.entries(env.packages)
    .filter(([key, item]) => ["numpy", "pyarrow", "pydantic", "scipy", "arro3-core", "chronicler-agents"].includes(key)
      && typeof item === "string" && /^[A-Za-z0-9_.+-]{1,80}$/.test(item)));
  if (record(env.thread_env)) environment.thread_env = Object.fromEntries(Object.entries(env.thread_env)
    .filter(([key, item]) => ["PYTHONHASHSEED", "PYTHON_CPU_COUNT", "RAYON_NUM_THREADS", "OMP_NUM_THREADS",
      "OPENBLAS_NUM_THREADS", "OPENBLAS_THREAD_TIMEOUT", "MKL_NUM_THREADS", "BLIS_NUM_THREADS", "GOTO_NUM_THREADS",
      "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"].includes(key)
      && (item === null || typeof item === "string" && /^\d{1,10}$/.test(item))));
  return { source: { git_sha: source.git_sha, package_digest: source.package_digest }, native: nativeOut, environment };
}

/** Public provenance is descriptive, not an executable backend manifest. */
export type PortableWhatIfManifest = WhatIfManifest | (WhatIfManifestBase & { schema_version: 3;
  intervention: { control: "regional_transport_disruption"; scope: "region"; region_id: number; region_name: string;
    duration: number; prior_counter: number; effective_counter: number; effective_through_turn: number } });
export function portableWhatIfManifest(manifest: WhatIfManifest): PortableWhatIfManifest {
  const source = manifest.source;
  const header = record(source.header) ? source.header : {};
  const config = record(header.run_config) ? header.run_config : {};
  const checkpoint = portableArtifact(source.checkpoint);
  const partial = record(source.checkpoint) && typeof source.checkpoint.sha256 === "string"
    && SHA256.test(source.checkpoint.sha256) ? { sha256: source.checkpoint.sha256 } : {};
  const common = { request_id: manifest.request_id, semantics: manifest.semantics,
    mode: manifest.mode, seed: manifest.seed, start_turn: manifest.start_turn,
    end_turn: manifest.end_turn, turns: manifest.turns, source: { checkpoint: checkpoint ?? partial,
    header: { exact: header.exact === true, turn: manifest.start_turn, seed: manifest.seed,
      identity: portableRuntime(header.identity), run_config: { simulation_args: portableSettings(config.simulation_args),
        output_args: { simulate_only: record(config.output_args) && config.output_args.simulate_only === true } } } } };
  if (manifest.schema_version === 3) {
    const a = manifest.intervention;
    return { ...common, schema_version: 3, intervention: { control: "regional_transport_disruption", scope: "region",
      region_id: a.region_id, region_name: a.region_name, duration: a.duration, prior_counter: a.prior_counter,
      effective_counter: a.effective_counter, effective_through_turn: a.effective_through_turn } };
  }
  if (manifest.schema_version === 2) return { ...common, schema_version: 2,
    intervention: { command: "set", civ: "@world", stat: "grain_reserves.shortfall_priority",
      scope: "world", before: manifest.intervention.before, value: manifest.intervention.value } };
  return { ...common, schema_version: 1, intervention: { ...manifest.intervention } };
}

type RecipeControl = { kind: "stability"; civ: string; value: number }
  | { kind: "granary_shortfall_priority"; value: 0 | 1 }
  | { kind: "regional_transport_disruption"; region_id: number; duration: number };
export interface WhatIfRecipe {
  kind: "chronicler-what-if-recipe";
  version: 1;
  source: { seed: number; mode: string; start_turn: number; checkpoint: ArtifactIdentity;
    runtime: Record<string, unknown>; runtime_sha256: string;
    settings: Record<string, unknown>; settings_sha256: string };
  control: RecipeControl;
  turns: number;
  end_turn: number;
  outputs: { baseline: ArtifactIdentity; intervention: ArtifactIdentity } | null;
}
function canonical(value: unknown, depth = 0): string {
  if (depth > 32) throw new Error("Recipe identity is too deeply nested.");
  if (Array.isArray(value)) return `[${value.map((item) => canonical(item, depth + 1)).join(",")}]`;
  return record(value) ? `{${Object.keys(value).filter((key) => value[key] !== undefined).sort()
    .map((key) => `${JSON.stringify(key)}:${canonical(value[key], depth + 1)}`).join(",")}}` : JSON.stringify(value) ?? "null";
}
async function fingerprint(value: unknown): Promise<string> {
  const bytes = new TextEncoder().encode(canonical(value));
  const identity = await identifyArtifact("identity.json", bytes.buffer);
  if (!identity.sha256) throw new Error("This browser cannot verify recipe identity hashes.");
  return identity.sha256;
}
export async function createWhatIfRecipe(manifest: WhatIfManifest, pair?: WhatIfPair): Promise<WhatIfRecipe> {
  if (!readWhatIfManifest(manifest)) throw new Error("Unsupported comparison manifest.");
  if (pair && canonical(pair.manifest) !== canonical(manifest)) throw new Error("Output identities belong to a different comparison plan.");
  const header = manifest.source.header;
  const checkpoint = portableArtifact(manifest.source.checkpoint);
  if (!record(header) || header.exact !== true || header.turn !== manifest.start_turn || header.seed !== manifest.seed
    || !record(header.run_config) || !record(header.run_config.simulation_args)
    || !record(header.run_config.output_args) || header.run_config.output_args.simulate_only !== true || !checkpoint) {
    throw new Error("A recipe requires a complete compatible exact-checkpoint manifest.");
  }
  const runtime = portableRuntime(header.identity);
  if (!runtime) throw new Error("The prepared manifest does not contain complete source and runtime identity.");
  const control: RecipeControl = manifest.schema_version === 3
    ? { kind: "regional_transport_disruption", region_id: manifest.intervention.region_id, duration: manifest.intervention.duration }
    : manifest.schema_version === 2 ? { kind: "granary_shortfall_priority", value: manifest.intervention.value }
      : { kind: "stability", civ: manifest.intervention.civ, value: manifest.intervention.value };
  const baseline = pair ? portableArtifact(pair.baseline.identity) : null;
  const intervention = pair ? portableArtifact(pair.intervention.identity) : null;
  if (pair && (!baseline || !intervention)) throw new Error("Recipe output identities are incomplete.");
  return { kind: "chronicler-what-if-recipe", version: 1,
    source: { seed: manifest.seed, mode: manifest.mode, start_turn: manifest.start_turn, checkpoint, runtime,
      runtime_sha256: await fingerprint(header.identity),
      settings: portableSettings(header.run_config.simulation_args), settings_sha256: await fingerprint(header.run_config) },
    control, turns: manifest.turns, end_turn: manifest.end_turn,
    outputs: baseline && intervention ? { baseline, intervention } : null };
}
function parseRecipe(value: unknown): WhatIfRecipe | null {
  if (!record(value) || !exactKeys(value, ["kind", "version", "source", "control", "turns", "end_turn", "outputs"])
    || value.kind !== "chronicler-what-if-recipe" || value.version !== 1 || !validWhatIfHorizon(value.turns as number)
    || !record(value.source) || !record(value.control)) return null;
  const source = value.source, control = value.control;
  if (!exactKeys(source, ["seed", "mode", "start_turn", "checkpoint", "runtime", "runtime_sha256", "settings", "settings_sha256"])
    || !Number.isSafeInteger(source.seed) || !Number.isSafeInteger(source.start_turn) || (source.start_turn as number) < 0
    || !["off", "hybrid", "shadow", "demographics-only"].includes(source.mode as string)
    || !Number.isSafeInteger(value.end_turn) || value.end_turn !== (source.start_turn as number) + (value.turns as number)
    || !record(source.checkpoint) || canonical(portableArtifact(source.checkpoint)) !== canonical(source.checkpoint)
    || !record(source.runtime) || !portableRuntime(source.runtime) || canonical(portableRuntime(source.runtime)) !== canonical(source.runtime)
    || !record(source.settings) || canonical(portableSettings(source.settings)) !== canonical(source.settings)
    || typeof source.runtime_sha256 !== "string" || !SHA256.test(source.runtime_sha256)
    || typeof source.settings_sha256 !== "string" || !SHA256.test(source.settings_sha256)) return null;
  if (control.kind === "stability") {
    if (!exactKeys(control, ["kind", "civ", "value"]) || !plain(control.civ)
      || !Number.isInteger(control.value) || (control.value as number) < 1 || (control.value as number) > 100) return null;
  } else if (control.kind === "granary_shortfall_priority") {
    if (source.mode !== "hybrid" || !exactKeys(control, ["kind", "value"]) || !binary(control.value)) return null;
  } else if (control.kind === "regional_transport_disruption") {
    if (source.mode !== "hybrid" || !exactKeys(control, ["kind", "region_id", "duration"])
      || !Number.isSafeInteger(control.region_id) || (control.region_id as number) < 0
      || !Number.isSafeInteger((control.region_id as number) * 10 + (control.duration as number))
      || !validTransportDuration(control.duration as number)) return null;
  } else return null;
  if (value.outputs !== null) {
    if (!record(value.outputs) || !exactKeys(value.outputs, ["baseline", "intervention"])) return null;
    for (const key of ["baseline", "intervention"]) {
      if (!record(value.outputs[key]) || canonical(portableArtifact(value.outputs[key])) !== canonical(value.outputs[key])) return null;
    }
  }
  return value as unknown as WhatIfRecipe;
}
export function readWhatIfRecipe(value: unknown): WhatIfRecipe | null {
  try { return parseRecipe(value); } catch { return null; }
}
/** Import fills a plan only; exact checkpoint/source/settings checks follow preparation. */
export function recipeLiveMismatch(recipe: WhatIfRecipe, bundle: Bundle | null | undefined, turn: number, civs: string[]): string | null {
  if (!bundle) return "Connect a compatible live world before importing a recipe.";
  const world = bundle.world_state as unknown as Record<string, unknown>;
  if (recipe.source.seed !== bundle.metadata.seed || recipe.source.mode !== (world.agent_mode ?? "off") || recipe.source.start_turn !== turn) {
    return "Recipe seed, mode or starting turn differs from this paused world.";
  }
  if (recipe.control.kind === "stability" && !civs.includes(recipe.control.civ)) return "Recipe civilization is unavailable in this paused world.";
  if (recipe.control.kind === "granary_shortfall_priority" && granaryPolicyValue(bundle) === null) return "Recipe requires already-enabled hybrid granaries.";
  if (recipe.control.kind === "regional_transport_disruption") {
    const regionId = recipe.control.region_id;
    if (!transportRegions(bundle).some((r) => r.id === regionId)) return "Recipe requires the selected region in an eligible hybrid world.";
  }
  return null;
}
export interface PreparedRecipeCheck {
  current: WhatIfRecipe;
  mismatch: "source" | "plan" | null;
  message: string | null;
}
export async function checkPreparedRecipe(recipe: WhatIfRecipe, manifest: WhatIfManifest): Promise<PreparedRecipeCheck> {
  const current = await createWhatIfRecipe(manifest);
  if (canonical(recipe.source) !== canonical(current.source)) return { current, mismatch: "source",
    message: "Recipe checkpoint, source, runtime or settings identity differs. This prepared comparison cannot run as the imported recipe." };
  if (canonical(recipe.control) !== canonical(current.control) || recipe.turns !== current.turns || recipe.end_turn !== current.end_turn) {
    return { current, mismatch: "plan", message: "The prepared control or horizon differs from the imported recipe." };
  }
  return { current, mismatch: null, message: null };
}
export async function recipePreparedMismatch(recipe: WhatIfRecipe, manifest: WhatIfManifest): Promise<string | null> {
  return (await checkPreparedRecipe(recipe, manifest)).message;
}
