import type { Bundle } from "../types";
import type { ArtifactIdentity } from "./artifactIdentity";
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
export function whatIfInterventionLabel(manifest: WhatIfManifest): string {
  const action = manifest.intervention;
  return manifest.schema_version === 2
    ? `World granary priority: ${action.before === 0 ? "reserve fill first (0)" : "shortfall first (1)"} → ${action.value === 0 ? "reserve fill first (0)" : "shortfall first (1)"}`
    : `${action.civ}: stability ${action.before} → ${action.value}`;
}
export function whatIfArmLabel(manifest: WhatIfManifest): string {
  return manifest.schema_version === 2 ? "Global granary priority intervention" : "Stability intervention";
}
export function readWhatIfManifest(value: unknown): WhatIfManifest | null {
  if (!record(value) || ![1, 2].includes(value.schema_version as number) || value.semantics !== "exact_checkpoint_pair"
    || typeof value.request_id !== "string" || !/^[A-Za-z0-9_-]{1,80}$/.test(value.request_id)
    || !record(value.source) || typeof value.mode !== "string"
    || !Number.isSafeInteger(value.seed) || !Number.isSafeInteger(value.start_turn) || (value.start_turn as number) < 0
    || !Number.isSafeInteger(value.end_turn) || !validWhatIfHorizon(value.turns as number)
    || (value.end_turn as number) !== (value.start_turn as number) + (value.turns as number)
    || !record(value.intervention)) return null;
  const action = value.intervention;
  const allowed = value.schema_version === 1 ? ["command", "civ", "stat", "before", "value"]
    : ["command", "civ", "stat", "before", "value", "scope"];
  if (Object.keys(action).some((key) => !allowed.includes(key)) || action.command !== "set") return null;
  if (value.schema_version === 1) {
    if (action.stat !== "stability" || typeof action.civ !== "string" || !action.civ
      || /[\r\n\x00]/.test(action.civ) || !Number.isFinite(action.before) || !Number.isInteger(action.value)
      || (action.value as number) < 1 || (action.value as number) > 100) return null;
  } else if (value.mode !== "hybrid" || action.stat !== "grain_reserves.shortfall_priority"
    || action.civ !== "@world" || action.scope !== "world" || !binary(action.before) || !binary(action.value)) return null;
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
  const baseline = readArm(value.baseline, "Unchanged continuation");
  const intervention = readArm(value.intervention, manifest ? whatIfArmLabel(manifest) : "Intervention");
  return manifest && baseline && intervention ? { manifest, baseline, intervention } : null;
}
