import { isRecord } from "./bundleValidation";
import type { Bundle } from "../types";
import { BundleDecodeError, decodeBundlePayload } from "./bundleCodec";
import { looksLikeBundleV2Manifest, parseBundleV2Manifest, type BundleV2Manifest } from "./bundleV2";

const LEGACY_REQUIRED_KEYS: (keyof Bundle)[] = [
  "world_state",
  "history",
  "events_timeline",
  "named_events",
  "chronicle_entries",
  "era_reflections",
  "metadata",
];

export type BundleLoaderDiagnosticCode =
  | "INVALID_JSON"
  | "INVALID_ROOT_OBJECT"
  | "MISSING_REQUIRED_KEYS"
  | "INVALID_HISTORY_DELTA"
  | "INVALID_STRUCTURE"
  | "STATE_JSON"
  | "MANIFEST_SCHEMA_ERROR"
  | "BUNDLE_V2_NOT_ACTIVE";

export interface BundleLoaderDiagnostic {
  code: BundleLoaderDiagnosticCode;
  message: string;
  manifest_version?: number;
  layer_id?: string;
  path?: string;
}

export type BundleLoaderResult =
  | {
      kind: "legacy";
      bundle: Bundle;
      diagnostics: [];
    }
  | {
      kind: "manifest_v2";
      manifest: BundleV2Manifest;
      diagnostics: [BundleLoaderDiagnostic];
    }
  | {
      kind: "error";
      diagnostics: BundleLoaderDiagnostic[];
    };

function toErrorResult(diagnostic: BundleLoaderDiagnostic): BundleLoaderResult {
  return {
    kind: "error",
    diagnostics: [diagnostic],
  };
}

export function classifyParsedBundlePayload(parsed: unknown): BundleLoaderResult {
  if (!isRecord(parsed)) {
    return toErrorResult({
      code: "INVALID_ROOT_OBJECT",
      message: "Invalid JSON: expected an object",
    });
  }

  const raw = parsed as Record<string, unknown>;
  if (looksLikeBundleV2Manifest(raw)) {
    const v2 = parseBundleV2Manifest(raw);
    if (v2.error) {
      return toErrorResult({
        code: "MANIFEST_SCHEMA_ERROR",
        message: v2.error,
      });
    }

    return {
      kind: "manifest_v2",
      manifest: v2.manifest!,
      diagnostics: [
        {
          code: "BUNDLE_V2_NOT_ACTIVE",
          message:
            "Bundle v2 manifest detected. Phase 7.5 layered loading is not active in this viewer build yet. " +
            "Use the legacy single-artifact adapter export for now.",
          manifest_version: v2.manifest!.manifest_version,
        },
      ],
    };
  }

  // A bare world state is a CLI fork/legacy-resume input, never history.
  if (!("world_state" in raw) && ["regions", "civilizations", "turn", "seed", "name"].every((key) => key in raw)) {
    if (typeof raw.name !== "string" || typeof raw.seed !== "number" || !Number.isInteger(raw.turn)
      || (raw.turn as number) < 0 || !Array.isArray(raw.regions) || !raw.regions.every(isRecord)
      || !Array.isArray(raw.civilizations) || !raw.civilizations.every(isRecord)) {
      return toErrorResult({ code: "INVALID_STRUCTURE", message:
        "Incomplete or malformed world state JSON. Its required name, seed, turn, regions or civilizations are invalid. " +
        "Open a complete chronicle_bundle.json to view history, or use a complete state.json with the CLI." });
    }
    return toErrorResult({ code: "STATE_JSON", message:
      "World state JSON detected. This is a final state, not a viewable history bundle. " +
      "Open the run's chronicle_bundle.json to explore recorded history. " +
      "Use the CLI with --fork /path/to/state.json --seed NEW_SEED to branch, or --resume /path/to/state.json for a legacy, non-exact continuation. " +
      "A state JSON cannot recover earlier history or provide an exact checkpoint resume." });
  }

  // Bundle version 6 writes the history as deltas (lib/bundleCodec.ts).
  let obj: Record<string, unknown>;
  try {
    obj = decodeBundlePayload(raw);
  } catch (error) {
    if (!(error instanceof BundleDecodeError)) {
      throw error;
    }
    return toErrorResult({
      code: "INVALID_HISTORY_DELTA",
      message: `Invalid bundle history: ${error.message}`,
    });
  }
  if (!Array.isArray(obj.history) && "history" in obj) {
    return toErrorResult({
      code: "INVALID_HISTORY_DELTA",
      message: "Invalid bundle history: history must be a list",
    });
  }
  const missing = LEGACY_REQUIRED_KEYS.filter((k) => !(k in obj));
  if (missing.length > 0) {
    return toErrorResult({
      code: "MISSING_REQUIRED_KEYS",
      message: `Missing required keys: ${missing.join(", ")}`,
    });
  }

  // Classification/codec adapters may use deliberate partial payloads. File
  // uploads validate the expanded structure and viewability in bundleFile.
  return {
    kind: "legacy",
    bundle: obj as unknown as Bundle,
    diagnostics: [],
  };
}

export function parseBundleJsonPayload(jsonString: string): BundleLoaderResult {
  let parsed: unknown;
  try {
    parsed = JSON.parse(jsonString);
  } catch {
    return toErrorResult({
      code: "INVALID_JSON",
      message: "Invalid JSON: could not parse file",
    });
  }

  return classifyParsedBundlePayload(parsed);
}

export function formatBundleLoaderDiagnostics(diagnostics: BundleLoaderDiagnostic[]): string {
  return diagnostics
    .map((diagnostic) => {
      if (diagnostic.manifest_version !== undefined) {
        return `${diagnostic.message} (manifest_version=${diagnostic.manifest_version})`;
      }
      return diagnostic.message;
    })
    .join(" ");
}
