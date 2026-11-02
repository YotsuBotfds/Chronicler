import type { Bundle } from "../types";
import type { ArtifactIdentity } from "./artifactIdentity";
import type { CompletedRun } from "./completedRunComparison";
import { classifyParsedBundlePayload } from "./bundleLoader";

export interface WhatIfManifest {
  schema_version: 1;
  request_id: string;
  source: Record<string, unknown>;
  mode: string;
  seed: number;
  start_turn: number;
  end_turn: number;
  turns: number;
  intervention: { command: "set"; civ: string; stat: "stability"; before: number; value: number };
  semantics: "exact_checkpoint_pair";
}
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
  run: () => void;
  cancel: () => void;
}
export function whatIfActive(status: WhatIfStatus | null | undefined): boolean {
  return !!status && ["preparing", "prepared", "running"].includes(status.state);
}
function record(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
export function readWhatIfManifest(value: unknown): WhatIfManifest | null {
  if (!record(value) || value.schema_version !== 1 || value.semantics !== "exact_checkpoint_pair"
    || typeof value.request_id !== "string" || !record(value.source) || typeof value.mode !== "string"
    || !Number.isInteger(value.seed) || !Number.isInteger(value.start_turn) || !Number.isInteger(value.end_turn)
    || !Number.isInteger(value.turns) || (value.turns as number) < 1 || (value.turns as number) > 20
    || (value.end_turn as number) !== (value.start_turn as number) + (value.turns as number)
    || !record(value.intervention)) return null;
  const action = value.intervention;
  if (action.command !== "set" || action.stat !== "stability" || typeof action.civ !== "string"
    || !Number.isFinite(action.before) || !Number.isInteger(action.value)
    || (action.value as number) < 1 || (action.value as number) > 100) return null;
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
  const intervention = readArm(value.intervention, "Stability intervention");
  return manifest && baseline && intervention ? { manifest, baseline, intervention } : null;
}
