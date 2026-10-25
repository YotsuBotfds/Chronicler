/**
 * Bundle version 6: the history is written as changes between snapshots.
 *
 * The file stores `history_delta` instead of `history`: the first snapshot,
 * then one patch per snapshot against the one before it. Its `world_state`
 * holds `null` for `events_timeline` and `named_events`, which repeat the
 * top-level fields. Decoding gives the version-5 layout the viewer reads.
 * The encoder and the patch format are in src/chronicler/bundle_codec.py;
 * see docs/performance/bundle-v6.md.
 *
 * Decoded snapshots share unchanged values with the snapshot before them;
 * the viewer treats bundles as read-only.
 */

export const HISTORY_DELTA_KEY = "history_delta";
const SHARED_WORLD_FIELDS = ["events_timeline", "named_events"] as const;

const DEL = "~d";
const ORDER = "~o";
const REPLACE = "~r";
const LIST = "~l";
const TAIL = "~t";
const LEN = "~n";
const RESERVED = new Set([DEL, ORDER, REPLACE, LIST, TAIL, LEN]);

type JsonObject = Record<string, unknown>;

function isObject(value: unknown): value is JsonObject {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function hasOwn(object: JsonObject, key: string): boolean {
  return Object.prototype.hasOwnProperty.call(object, key);
}

function applyPatch(previous: unknown, patch: unknown): unknown {
  if (isObject(patch)) {
    if (hasOwn(patch, REPLACE)) {
      return patch[REPLACE];
    }
    if (isObject(previous)) {
      return applyObjectPatch(previous, patch);
    }
    if (Array.isArray(previous)) {
      return applyListPatch(previous, patch);
    }
  }
  return patch;
}

function applyObjectPatch(previous: JsonObject, patch: JsonObject): JsonObject {
  const removed = Array.isArray(patch[DEL]) ? new Set(patch[DEL] as string[]) : null;
  const out: JsonObject = {};
  for (const [key, value] of Object.entries(previous)) {
    if (removed?.has(key)) {
      continue;
    }
    out[key] = hasOwn(patch, key) ? applyPatch(value, patch[key]) : value;
  }
  for (const [key, value] of Object.entries(patch)) {
    if (!RESERVED.has(key) && !hasOwn(previous, key)) {
      out[key] = value;
    }
  }
  const order = patch[ORDER];
  if (Array.isArray(order)) {
    const ordered: JsonObject = {};
    for (const key of order as string[]) {
      ordered[key] = out[key];
    }
    return ordered;
  }
  return out;
}

function applyListPatch(previous: unknown[], patch: JsonObject): unknown[] {
  const out = previous.slice();
  const length = patch[LEN];
  if (typeof length === "number") {
    out.length = length;
  }
  for (const [index, item] of (patch[LIST] ?? []) as [number, unknown][]) {
    out[index] = applyPatch(out[index], item);
  }
  const tail = patch[TAIL];
  if (Array.isArray(tail)) {
    for (const item of tail) {
      out.push(item);
    }
  }
  return out;
}

/** The snapshots of a `history_delta`. */
export function decodeHistory(encoded: unknown[]): unknown[] {
  const history: unknown[] = [];
  let previous: unknown = undefined;
  encoded.forEach((item, index) => {
    previous = index === 0 ? item : applyPatch(previous, item);
    history.push(previous);
  });
  return history;
}

/** Whether a parsed bundle is in the version-6 file layout. */
export function isEncodedBundle(bundle: JsonObject): boolean {
  if (hasOwn(bundle, HISTORY_DELTA_KEY)) {
    return true;
  }
  const world = bundle.world_state;
  return isObject(world) && SHARED_WORLD_FIELDS.some(
    (field) => hasOwn(world, field) && world[field] === null && hasOwn(bundle, field),
  );
}

/**
 * A parsed bundle in the layout the viewer reads. Version-6 files are
 * decoded; earlier versions (and decoded bundles) are returned unchanged.
 */
export function decodeBundlePayload(bundle: JsonObject): JsonObject {
  if (!isEncodedBundle(bundle)) {
    return bundle;
  }
  const out: JsonObject = {};
  for (const [key, value] of Object.entries(bundle)) {
    if (key === HISTORY_DELTA_KEY) {
      out.history = Array.isArray(value) ? decodeHistory(value) : value;
    } else if (key === "world_state" && isObject(value)) {
      const world: JsonObject = { ...value };
      for (const field of SHARED_WORLD_FIELDS) {
        if (hasOwn(world, field) && world[field] === null && hasOwn(bundle, field)) {
          world[field] = bundle[field];
        }
      }
      out[key] = world;
    } else {
      out[key] = value;
    }
  }
  return out;
}
