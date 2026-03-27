export type BundleV2LayerKind =
  | "summary"
  | "entities"
  | "timeline"
  | "metrics"
  | "overlays"
  | "networks"
  | "detail";

export interface BundleV2LayerRef {
  id: string;
  kind: BundleV2LayerKind;
  version: string;
  path: string;
  required: boolean;
}

export interface BundleV2Manifest {
  manifest_version: number;
  bundle_schema_version: string;
  seed: number;
  total_turns: number;
  summary_layer: string;
  layers: BundleV2LayerRef[];
}

const V2_LAYER_KINDS: BundleV2LayerKind[] = [
  "summary",
  "entities",
  "timeline",
  "metrics",
  "overlays",
  "networks",
  "detail",
];

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function isLayerKind(value: unknown): value is BundleV2LayerKind {
  return typeof value === "string" && V2_LAYER_KINDS.includes(value as BundleV2LayerKind);
}

function isLayerRef(value: unknown): value is BundleV2LayerRef {
  if (!isObject(value)) {
    return false;
  }

  return (
    typeof value.id === "string" &&
    isLayerKind(value.kind) &&
    typeof value.version === "string" &&
    typeof value.path === "string" &&
    typeof value.required === "boolean"
  );
}

export function looksLikeBundleV2Manifest(value: unknown): boolean {
  if (!isObject(value)) {
    return false;
  }

  return "manifest_version" in value || "layers" in value || "bundle_schema_version" in value;
}

export function parseBundleV2Manifest(value: unknown): {
  manifest: BundleV2Manifest | null;
  error: string | null;
} {
  if (!isObject(value)) {
    return {
      manifest: null,
      error: "Bundle v2 manifest error: expected an object",
    };
  }

  if (typeof value.manifest_version !== "number") {
    return {
      manifest: null,
      error: "Bundle v2 manifest error: missing numeric manifest_version",
    };
  }

  if (typeof value.bundle_schema_version !== "string") {
    return {
      manifest: null,
      error: "Bundle v2 manifest error: missing string bundle_schema_version",
    };
  }

  if (typeof value.seed !== "number" || typeof value.total_turns !== "number") {
    return {
      manifest: null,
      error: "Bundle v2 manifest error: missing numeric seed/total_turns",
    };
  }

  if (typeof value.summary_layer !== "string") {
    return {
      manifest: null,
      error: "Bundle v2 manifest error: missing string summary_layer",
    };
  }

  if (!Array.isArray(value.layers)) {
    return {
      manifest: null,
      error: "Bundle v2 manifest error: missing layers array",
    };
  }

  if (value.layers.some((layer) => !isLayerRef(layer))) {
    return {
      manifest: null,
      error: "Bundle v2 manifest error: invalid layer descriptor",
    };
  }

  const layers = value.layers as BundleV2LayerRef[];
  const summaryLayer = layers.find((layer) => layer.id === value.summary_layer);
  if (!summaryLayer) {
    return {
      manifest: null,
      error: "Bundle v2 manifest error: summary_layer not found in layers",
    };
  }

  if (!summaryLayer.required) {
    return {
      manifest: null,
      error: "Bundle v2 manifest error: summary_layer must be required",
    };
  }

  return {
    manifest: value as unknown as BundleV2Manifest,
    error: null,
  };
}
