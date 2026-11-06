/**
 * The feature catalog a live server sends in its lobby `init` message
 * (`feature_catalog`, built by `chronicler.feature_catalog`): the feature
 * switches a Batch Lab batch or a live new world may request, their modes
 * and their dependencies. The reader is strict: anything malformed is
 * reported, never guessed, and an absent catalog (an older server) is
 * distinct from an invalid one. The server validates every request again.
 */
import type { FeatureSelection } from "../types";

export type FeatureRequirement =
  | { kind: "agents"; modes: string[]; reason: string }
  | { kind: "feature"; key: string; reason: string }
  | { kind: "choice"; key: string; values: string[]; reason: string }
  | { kind: "setting"; key: string; reason: string }
  | { kind: "any"; parts: FeatureRequirement[]; reason: string }
  /** The condition must not hold (two mutually exclusive switches each declare one). */
  | { kind: "not"; part: FeatureRequirement; reason: string };

export interface FeatureEntry {
  key: string;
  flag: string;
  label: string;
  help: string;
  kind: "bool" | "choice";
  /** The choices of a `choice` entry; the first is the run's default. */
  choices: string[] | null;
  /** The switch a mode belongs to (shown only while that switch is on). */
  parent: string | null;
  requires: FeatureRequirement[];
  group: string;
  experimental: boolean;
}

/** What a request on one surface inherits from the server. */
export interface FeatureSurface {
  agents: string | null;
  agentModes: string[];
  /** Catalog values the server's command line already sets. */
  values: FeatureSelection;
  settings: Record<string, boolean>;
  newWorldsOnly: boolean;
}

export interface FeatureCatalog {
  features: FeatureEntry[];
  settings: Record<string, string>;
  surfaces: { live: FeatureSurface; batch: FeatureSurface };
}

export type FeatureSurfaceName = keyof FeatureCatalog["surfaces"];

export type FeatureCatalogReading =
  | { status: "absent" }
  | { status: "invalid"; error: string }
  | { status: "ok"; catalog: FeatureCatalog };

class CatalogError extends Error {}

function fail(message: string): never {
  throw new CatalogError(message);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function stringList(value: unknown, where: string, { nonEmpty = true } = {}): string[] {
  if (!Array.isArray(value) || value.some((item) => typeof item !== "string")) {
    fail(`${where} must be a list of strings`);
  }
  if (nonEmpty && value.length === 0) fail(`${where} must not be empty`);
  if (new Set(value).size !== value.length) fail(`${where} has duplicates`);
  return [...value] as string[];
}

function text(value: unknown, where: string): string {
  if (typeof value !== "string") fail(`${where} must be a string`);
  return value;
}

const REQUIREMENT_KINDS = ["agents", "feature", "choice", "setting", "any", "not"] as const;

function readRequirement(raw: unknown, where: string): FeatureRequirement {
  if (!isRecord(raw)) fail(`${where} must be an object`);
  const kinds = REQUIREMENT_KINDS.filter((kind) => kind in raw);
  if (kinds.length !== 1) fail(`${where} must name exactly one condition`);
  const reason = text(raw.reason, `${where}.reason`);
  switch (kinds[0]) {
    case "agents":
      return { kind: "agents", modes: stringList(raw.agents, `${where}.agents`), reason };
    case "feature":
      return { kind: "feature", key: text(raw.feature, `${where}.feature`), reason };
    case "choice":
      return {
        kind: "choice",
        key: text(raw.choice, `${where}.choice`),
        values: stringList(raw.values, `${where}.values`),
        reason,
      };
    case "setting":
      return { kind: "setting", key: text(raw.setting, `${where}.setting`), reason };
    case "not":
      return { kind: "not", part: readRequirement(raw.not, `${where}.not`), reason };
    default: {
      if (!Array.isArray(raw.any) || raw.any.length === 0) fail(`${where}.any must be a non-empty list`);
      return { kind: "any", parts: raw.any.map((part, i) => readRequirement(part, `${where}.any[${i}]`)), reason };
    }
  }
}

function readEntry(raw: unknown, where: string): FeatureEntry {
  if (!isRecord(raw)) fail(`${where} must be an object`);
  const key = text(raw.key, `${where}.key`);
  const flag = text(raw.flag, `${where}.flag`);
  if (!key || !flag.startsWith("--")) fail(`${where} has no key or flag`);
  if (raw.kind !== "bool" && raw.kind !== "choice") fail(`${where}.kind must be bool or choice`);
  if (raw.default !== null) fail(`${where}.default must be null (features are off unless requested)`);
  const choices = raw.kind === "choice" ? stringList(raw.choices, `${where}.choices`) : null;
  if (raw.kind === "bool" && raw.choices !== null) fail(`${where}.choices must be null for a bool`);
  if (raw.parent !== null && typeof raw.parent !== "string") fail(`${where}.parent must be a string or null`);
  if (!Array.isArray(raw.requires)) fail(`${where}.requires must be a list`);
  if (typeof raw.experimental !== "boolean") fail(`${where}.experimental must be a boolean`);
  return {
    key,
    flag,
    label: text(raw.label, `${where}.label`),
    help: text(raw.help, `${where}.help`),
    kind: raw.kind,
    choices,
    parent: raw.parent,
    requires: raw.requires.map((req, i) => readRequirement(req, `${where}.requires[${i}]`)),
    group: text(raw.group, `${where}.group`),
    experimental: raw.experimental,
  };
}

function checkValue(entry: FeatureEntry, value: unknown, where: string): boolean | string {
  if (entry.kind === "bool") {
    if (typeof value !== "boolean") fail(`${where} must be a boolean`);
    return value;
  }
  if (typeof value !== "string" || !entry.choices!.includes(value)) fail(`${where} is not a choice of ${entry.key}`);
  return value;
}

function readSurface(raw: unknown, where: string, byKey: Map<string, FeatureEntry>,
  settingNames: string[]): FeatureSurface {
  if (!isRecord(raw)) fail(`${where} must be an object`);
  const agents = raw.agents === null ? null : text(raw.agents, `${where}.agents`);
  const agentModes = stringList(raw.agent_modes, `${where}.agent_modes`);
  if (agents !== null && !agentModes.includes(agents)) fail(`${where}.agents is not one of its agent modes`);
  if (!isRecord(raw.values)) fail(`${where}.values must be an object`);
  const values: FeatureSelection = {};
  for (const [key, value] of Object.entries(raw.values)) {
    const entry = byKey.get(key);
    if (!entry) fail(`${where}.values names an unknown feature ${key}`);
    values[key] = checkValue(entry, value, `${where}.values.${key}`);
  }
  if (!isRecord(raw.settings)) fail(`${where}.settings must be an object`);
  const settings: Record<string, boolean> = {};
  for (const name of settingNames) {
    const value = raw.settings[name];
    // A missing setting is unknown, not false: refuse the catalog.
    if (typeof value !== "boolean") fail(`${where}.settings.${name} must be a boolean`);
    settings[name] = value;
  }
  if (typeof raw.new_worlds_only !== "boolean") fail(`${where}.new_worlds_only must be a boolean`);
  return { agents, agentModes, values, settings, newWorldsOnly: raw.new_worlds_only };
}

function checkRequirementTerms(req: FeatureRequirement, where: string, byKey: Map<string, FeatureEntry>,
  settings: Record<string, string>): void {
  if (req.kind === "feature" && byKey.get(req.key)?.kind !== "bool") fail(`${where} names an unknown switch ${req.key}`);
  if (req.kind === "choice") {
    const entry = byKey.get(req.key);
    if (entry?.kind !== "choice" || req.values.some((value) => !entry.choices!.includes(value))) {
      fail(`${where} names an unknown choice ${req.key}`);
    }
  }
  if (req.kind === "setting" && !(req.key in settings)) fail(`${where} names an unknown setting ${req.key}`);
  if (req.kind === "any") req.parts.forEach((part, i) => checkRequirementTerms(part, `${where}.any[${i}]`, byKey, settings));
  if (req.kind === "not") checkRequirementTerms(req.part, `${where}.not`, byKey, settings);
}

/** Read the lobby's `feature_catalog` field (`undefined`: an older server). */
export function readFeatureCatalog(raw: unknown): FeatureCatalogReading {
  if (raw === undefined) return { status: "absent" };
  try {
    if (!isRecord(raw)) fail("feature_catalog must be an object");
    if (raw.schema_version !== 1) fail(`unsupported feature_catalog schema_version ${String(raw.schema_version)}`);
    if (!Array.isArray(raw.features)) fail("feature_catalog.features must be a list");
    const features = raw.features.map((entry, i) => readEntry(entry, `features[${i}]`));
    const byKey = new Map<string, FeatureEntry>();
    for (const entry of features) {
      if (byKey.has(entry.key)) fail(`feature ${entry.key} is listed twice`);
      byKey.set(entry.key, entry);
    }
    if (!isRecord(raw.settings)) fail("feature_catalog.settings must be an object");
    const settings: Record<string, string> = {};
    for (const [name, meaning] of Object.entries(raw.settings)) settings[name] = text(meaning, `settings.${name}`);
    for (const entry of features) {
      if (entry.parent !== null) {
        const parent = byKey.get(entry.parent);
        if (entry.kind !== "choice" || parent?.kind !== "bool") fail(`${entry.key} has an invalid parent`);
      }
      entry.requires.forEach((req, i) => checkRequirementTerms(req, `${entry.key}.requires[${i}]`, byKey, settings));
    }
    if (!isRecord(raw.surfaces)) fail("feature_catalog.surfaces must be an object");
    const names = Object.keys(settings);
    const surfaces = {
      live: readSurface(raw.surfaces.live, "surfaces.live", byKey, names),
      batch: readSurface(raw.surfaces.batch, "surfaces.batch", byKey, names),
    };
    return { status: "ok", catalog: { features, settings, surfaces } };
  } catch (error) {
    if (error instanceof CatalogError) return { status: "invalid", error: error.message };
    throw error;
  }
}

/** The values a request would run with: the server's, then the selection's. */
export function effectiveValues(surface: FeatureSurface, selection: FeatureSelection): FeatureSelection {
  return { ...surface.values, ...selection };
}

function entryByKey(catalog: FeatureCatalog, key: string): FeatureEntry | undefined {
  return catalog.features.find((entry) => entry.key === key);
}

/** A choice's value: its explicit value, else its first choice (the run's default). */
export function choiceValue(entry: FeatureEntry, effective: FeatureSelection): string {
  const value = effective[entry.key];
  return typeof value === "string" ? value : entry.choices![0];
}

function satisfied(catalog: FeatureCatalog, req: FeatureRequirement, effective: FeatureSelection,
  surface: FeatureSurface, agents: string | null): boolean {
  switch (req.kind) {
    case "agents":
      return agents !== null && req.modes.includes(agents);
    case "feature":
      return effective[req.key] === true;
    case "choice": {
      const entry = entryByKey(catalog, req.key);
      return !!entry && req.values.includes(choiceValue(entry, effective));
    }
    case "setting":
      return surface.settings[req.key] === true;
    case "not":
      return !satisfied(catalog, req.part, effective, surface, agents);
    default:
      return req.parts.some((part) => satisfied(catalog, part, effective, surface, agents));
  }
}

/** Requirements of `entry` that the effective values do not meet. */
export function unmetRequirements(catalog: FeatureCatalog, entry: FeatureEntry, effective: FeatureSelection,
  surface: FeatureSurface, agents: string | null): FeatureRequirement[] {
  return entry.requires.filter((req) => !satisfied(catalog, req, effective, surface, agents));
}

export function isOn(entry: FeatureEntry, effective: FeatureSelection): boolean {
  return entry.kind === "bool" ? effective[entry.key] === true : entry.key in effective;
}

function isNoOp(entry: FeatureEntry, surface: FeatureSurface, value: boolean | string): boolean {
  const inherited = surface.values[entry.key];
  if (entry.kind === "bool") return (inherited ?? false) === value;
  return (inherited ?? entry.choices![0]) === value;
}

/**
 * The selection a request can send: overrides that change nothing are
 * dropped, and so is every switch (or mode) whose requirements are no
 * longer met, until nothing changes. A switch the server turned on is
 * turned off explicitly when its requirements fail.
 */
export function normalizeSelection(catalog: FeatureCatalog, surface: FeatureSurface, agents: string | null,
  selection: FeatureSelection): FeatureSelection {
  const result: FeatureSelection = {};
  for (const [key, value] of Object.entries(selection)) {
    const entry = entryByKey(catalog, key);
    if (entry && !isNoOp(entry, surface, value)) result[key] = value;
  }
  for (let changed = true; changed;) {
    changed = false;
    const effective = effectiveValues(surface, result);
    for (const entry of catalog.features) {
      if (entry.kind === "bool" && effective[entry.key] === true
        && unmetRequirements(catalog, entry, effective, surface, agents).length > 0) {
        if (surface.values[entry.key] === true) result[entry.key] = false;
        else delete result[entry.key];
        changed = true;
        break;
      }
      if (entry.kind === "choice" && entry.key in result
        && unmetRequirements(catalog, entry, effective, surface, agents).length > 0) {
        delete result[entry.key];
        changed = true;
        break;
      }
    }
  }
  return result;
}

/** The selection as command-line flags, in catalog order (what the run is given). */
export function selectionFlags(catalog: FeatureCatalog, selection: FeatureSelection): string[] {
  const flags: string[] = [];
  for (const entry of catalog.features) {
    if (!(entry.key in selection)) continue;
    const value = selection[entry.key];
    if (entry.kind === "bool") flags.push(value ? entry.flag : `--no-${entry.flag.slice(2)}`);
    else flags.push(`${entry.flag}=${String(value)}`);
  }
  return flags;
}

/** Shown instead of feature options while a saved world is loaded. */
export const FEATURES_NEED_NEW_WORLD =
  "Feature options apply to new worlds only; clear the resumed save to choose them.";

/** The `features` field to send, or undefined when nothing is selected. */
export function featurePayload(selection: FeatureSelection): FeatureSelection | undefined {
  return Object.keys(selection).length > 0 ? { ...selection } : undefined;
}
