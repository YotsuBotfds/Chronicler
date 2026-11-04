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
 *
 * Decoding checks every patch against the format and throws
 * `BundleDecodeError` naming the snapshot and the problem (the Python codec
 * raises the same errors); the loader turns it into a readable message.
 * The common object patch takes a fast path (a shallow copy, then the
 * changed keys); every other patch, and every malformed one, goes through
 * the reference implementation, so results and errors are the same.
 * Large files are decoded in a worker (lib/bundleDecode.ts).
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

/** A version-6 bundle whose `history_delta` does not follow the patch format. */
export class BundleDecodeError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "BundleDecodeError";
  }
}

function kindOf(value: unknown): string {
  return value === null ? "null" : Array.isArray(value) ? "list" : typeof value;
}

function isIndex(value: unknown): value is number {
  return typeof value === "number" && Number.isInteger(value);
}

function isObject(value: unknown): value is JsonObject {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function hasOwn(object: JsonObject, key: string): boolean {
  return Object.prototype.hasOwnProperty.call(object, key);
}

function setOwn(object: JsonObject, key: string, value: unknown): void {
  Object.defineProperty(object, key, {
    value, writable: true, enumerable: true, configurable: true,
  });
}

function applyPatch(previous: unknown, patch: unknown): unknown {
  if (isObject(patch)) {
    if (hasOwn(patch, REPLACE)) {
      if (Object.keys(patch).length !== 1) {
        throw new BundleDecodeError(`'${REPLACE}' patch with other keys: ${Object.keys(patch).sort().join(", ")}`);
      }
      return patch[REPLACE];
    }
    if (isObject(previous)) {
      return applyObjectPatch(previous, patch);
    }
    if (Array.isArray(previous)) {
      return applyListPatch(previous, patch);
    }
    const reserved = Object.keys(patch).filter((key) => RESERVED.has(key));
    if (reserved.length > 0) {
      throw new BundleDecodeError(`patch ${reserved.sort().join(", ")} against a ${kindOf(previous)}`);
    }
  }
  return patch;
}

let fastObjectPatches = true;

/** Tests: decode object patches with the reference implementation only (the format as defined). */
export function setReferenceObjectPatches(reference: boolean): void {
  fastObjectPatches = !reference;
}

function applyObjectPatch(previous: JsonObject, patch: JsonObject): JsonObject {
  return (fastObjectPatches ? applyObjectPatchFast(previous, patch) : null)
    ?? applyObjectPatchReference(previous, patch);
}

const PROTO = "__proto__";

/**
 * The common patch, quickly: no reserved key (so no deleted keys and no key
 * order) and no `__proto__` key on either side. A shallow copy of the
 * previous object keeps its key order; changed keys are replaced in place
 * and new ones follow in the patch's order, which is the order
 * `applyObjectPatchReference` builds. Anything else, and any malformed
 * patch, returns null: the reference decodes it, or throws the same
 * `BundleDecodeError` it always did (the first error in its order).
 * `bundleCodecFast.test.ts` compares the two on random histories.
 */
function applyObjectPatchFast(previous: JsonObject, patch: JsonObject): JsonObject | null {
  if (hasOwn(patch, PROTO) || hasOwn(previous, PROTO)) {
    return null;
  }
  const keys = Object.keys(patch);
  for (const key of keys) {
    if (RESERVED.has(key)) {
      return null;
    }
  }
  const out: JsonObject = { ...previous };
  try {
    for (const key of keys) {
      setOwn(out, key, hasOwn(previous, key) ? applyPatch(previous[key], patch[key]) : patch[key]);
    }
  } catch (error) {
    if (error instanceof BundleDecodeError) {
      return null;
    }
    throw error;
  }
  return out;
}

function applyObjectPatchReference(previous: JsonObject, patch: JsonObject): JsonObject {
  const unexpected = Object.keys(patch).filter((key) => RESERVED.has(key) && key !== DEL && key !== ORDER);
  if (unexpected.length > 0) {
    throw new BundleDecodeError(`object patch holds list keys ${unexpected.sort().join(", ")}`);
  }
  const deleted = patch[DEL];
  if (deleted !== undefined && (!Array.isArray(deleted)
      || deleted.some((key) => typeof key !== "string" || !hasOwn(previous, key)))) {
    throw new BundleDecodeError(`'${DEL}' must list existing keys, got ${JSON.stringify(deleted)}`);
  }
  const removed = deleted ? new Set(deleted as string[]) : null;
  const out: JsonObject = {};
  for (const [key, value] of Object.entries(previous)) {
    if (removed?.has(key)) {
      continue;
    }
    setOwn(out, key, hasOwn(patch, key) ? applyPatch(value, patch[key]) : value);
  }
  for (const [key, value] of Object.entries(patch)) {
    if (!RESERVED.has(key) && !hasOwn(previous, key)) {
      setOwn(out, key, value);
    }
  }
  const order = patch[ORDER];
  if (order !== undefined) {
    const keys = Object.keys(out);
    if (!Array.isArray(order) || order.length !== keys.length
        || order.some((key) => typeof key !== "string" || !hasOwn(out, key))
        || new Set(order).size !== order.length) {
      throw new BundleDecodeError(`'${ORDER}' must list the object's keys once each, got ${JSON.stringify(order)}`);
    }
    const ordered: JsonObject = {};
    for (const key of order as string[]) {
      setOwn(ordered, key, out[key]);
    }
    return ordered;
  }
  return out;
}

function applyListPatch(previous: unknown[], patch: JsonObject): unknown[] {
  const keys = Object.keys(patch);
  if (!hasOwn(patch, LIST) || keys.some((key) => key !== LIST && key !== TAIL && key !== LEN)) {
    throw new BundleDecodeError(`list patch needs '${LIST}' and only list keys, got ${keys.sort().join(", ")}`);
  }
  const out = previous.slice();
  const length = patch[LEN];
  if (length !== undefined) {
    if (!isIndex(length) || length < 0 || length > out.length) {
      throw new BundleDecodeError(`'${LEN}' must be a length up to ${out.length}, got ${JSON.stringify(length)}`);
    }
    out.length = length;
  }
  const changes = patch[LIST];
  if (!Array.isArray(changes)) {
    throw new BundleDecodeError(`'${LIST}' must be a list, got ${kindOf(changes)}`);
  }
  for (const change of changes) {
    if (!Array.isArray(change) || change.length !== 2 || !isIndex(change[0])
        || change[0] < 0 || change[0] >= out.length) {
      throw new BundleDecodeError(`'${LIST}' item must be [index < ${out.length}, patch], got ${JSON.stringify(change)}`);
    }
    const [index, item] = change as [number, unknown];
    out[index] = applyPatch(out[index], item);
  }
  const tail = patch[TAIL];
  if (tail !== undefined && !Array.isArray(tail)) {
    throw new BundleDecodeError(`'${TAIL}' must be a list, got ${kindOf(tail)}`);
  }
  if (Array.isArray(tail)) {
    for (const item of tail) {
      out.push(item);
    }
  }
  return out;
}

/** The snapshots of a `history_delta`; throws `BundleDecodeError` for a malformed patch. */
export function decodeHistory(encoded: unknown): unknown[] {
  if (!Array.isArray(encoded)) {
    throw new BundleDecodeError(`${HISTORY_DELTA_KEY} must be a list, got ${kindOf(encoded)}`);
  }
  const history: unknown[] = [];
  let previous: unknown = undefined;
  encoded.forEach((item, index) => {
    try {
      previous = index === 0 ? item : applyPatch(previous, item);
    } catch (error) {
      if (error instanceof BundleDecodeError) {
        throw new BundleDecodeError(`${HISTORY_DELTA_KEY}[${index}]: ${error.message}`);
      }
      throw error;
    }
    if (!isObject(previous)) {
      throw new BundleDecodeError(`${HISTORY_DELTA_KEY}[${index}]: a snapshot must be an object, got ${kindOf(previous)}`);
    }
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
 * Throws `BundleDecodeError` for a malformed `history_delta`.
 */
export function decodeBundlePayload(bundle: JsonObject): JsonObject {
  if (!isEncodedBundle(bundle)) {
    return bundle;
  }
  const out: JsonObject = {};
  for (const [key, value] of Object.entries(bundle)) {
    if (key === HISTORY_DELTA_KEY) {
      out.history = decodeHistory(value);
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
