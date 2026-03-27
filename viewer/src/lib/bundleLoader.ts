import type { Bundle } from "../types";
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
  if (typeof parsed !== "object" || parsed === null) {
    return toErrorResult({
      code: "INVALID_ROOT_OBJECT",
      message: "Invalid JSON: expected an object",
    });
  }

  const obj = parsed as Record<string, unknown>;
  if (looksLikeBundleV2Manifest(obj)) {
    const v2 = parseBundleV2Manifest(obj);
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

  const missing = LEGACY_REQUIRED_KEYS.filter((k) => !(k in obj));
  if (missing.length > 0) {
    return toErrorResult({
      code: "MISSING_REQUIRED_KEYS",
      message: `Missing required keys: ${missing.join(", ")}`,
    });
  }

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
