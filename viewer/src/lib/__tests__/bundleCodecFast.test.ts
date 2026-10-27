/// <reference types="node" />
/**
 * The object-patch fast path (bundleCodec.applyObjectPatchFast) decodes
 * exactly what the reference implementation decodes, key order included,
 * and every malformed history fails with the reference's message.
 * Randomized histories mix valid and malformed patches; fixtures and
 * (with VIEWER_EQUIVALENCE_BUNDLES) generated bundles are compared too.
 */
import { readFileSync } from "node:fs";
import { delimiter } from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import { decodeHistory, setReferenceObjectPatches } from "../bundleCodec";
import transportFixture from "../../__fixtures__/transport_bundle.json";
import citiesV6 from "../../__fixtures__/cities_bundle_v6.json";

afterEach(() => setReferenceObjectPatches(false));

type Outcome = { ok: true; json: string } | { ok: false; error: string };

function decodeWith(reference: boolean, text: string): Outcome {
  setReferenceObjectPatches(reference);
  try {
    return { ok: true, json: JSON.stringify(decodeHistory(JSON.parse(text))) };
  } catch (error) {
    return { ok: false, error: `${(error as Error).name}: ${(error as Error).message}` };
  } finally {
    setReferenceObjectPatches(false);
  }
}

function lcg(seed: number) {
  let state = seed >>> 0;
  return () => {
    state = (Math.imul(state, 1664525) + 1013904223) >>> 0;
    return state / 2 ** 32;
  };
}

const KEYS = ["a", "b", "c", "d", "0", "7", "10", "turn", "__proto__", "~d", "~o"];
const RESERVED = ["~d", "~o", "~r", "~l", "~t", "~n"];

/** A random history: its snapshots as JSON texts (JSON.parse makes `__proto__` an own key, as in a real file). */
function randomHistoryText(seed: number): string[] {
  const next = lcg(seed);
  const pick = <T,>(list: readonly T[]): T => list[Math.floor(next() * list.length)];
  const chance = (p: number) => next() < p;

  const value = (depth: number): string => {
    const roll = next();
    if (depth > 2 || roll < 0.35) {
      return pick(["1", "1.0", "true", "null", '"x"', "-0.0", "0", "[]", "{}"]);
    }
    if (roll < 0.65) {
      return `[${Array.from({ length: Math.floor(next() * 4) }, () => value(depth + 1)).join(",")}]`;
    }
    return object(depth);
  };
  const object = (depth: number): string => {
    // Reserved names also occur as plain data keys (the encoder writes such a history whole).
    const keys = [...new Set(Array.from({ length: Math.floor(next() * 5) }, () => pick(KEYS)))]
      .filter((key) => !RESERVED.includes(key) || chance(0.5));
    return `{${keys.map((key) => `${JSON.stringify(key)}:${value(depth + 1)}`).join(",")}}`;
  };

  // Patches are built against a parsed copy of the previous value (decoded with the reference).
  // `bad` is the chance of each malformation (low, so most histories decode).
  const bad = 0.02;
  const patchFor = (previous: unknown, depth: number): string => {
    if (chance(0.05)) {
      return `{"~r":${value(depth)}${chance(bad * 10) ? ',"x":1' : ""}}`;
    }
    if (Array.isArray(previous)) {
      if (chance(0.3)) return value(depth);
      const changes = Array.from({ length: Math.floor(next() * 3) }, () => {
        const index = chance(1 - bad) ? Math.floor(next() * Math.max(previous.length, 1)) : previous.length + 3;
        return `[${index},${index < previous.length ? patchFor(previous[index], depth + 1) : value(depth + 1)}]`;
      });
      const parts = [`"~l":${chance(1 - bad) ? `[${changes.join(",")}]` : "3"}`];
      if (chance(0.3)) parts.push(`"~t":[${value(depth + 1)}]`);
      if (chance(0.2)) {
        parts.push(`"~n":${chance(1 - bad * 5) ? Math.floor(next() * (previous.length + 1)) : previous.length + 2}`);
      }
      if (chance(bad)) parts.push('"~d":["a"]');
      return `{${parts.join(",")}}`;
    }
    if (typeof previous === "object" && previous !== null) {
      const own = Object.keys(previous as object);
      const entries: string[] = [];
      for (const key of own) {
        // Patching a data key named like a reserved key is (nearly always) malformed: rarely.
        if (chance(0.4) && (!RESERVED.includes(key) || chance(bad * 5))) {
          entries.push(`${JSON.stringify(key)}:${patchFor((previous as Record<string, unknown>)[key], depth + 1)}`);
        }
      }
      const added = KEYS.filter((key) => !own.includes(key) && !RESERVED.includes(key) && chance(0.15));
      for (const key of added) {
        entries.push(`${JSON.stringify(key)}:${value(depth + 1)}`);
      }
      let kept = own;
      if (chance(0.15)) {
        const deleted = own.filter(() => chance(0.4));
        kept = own.filter((key) => !deleted.includes(key));
        entries.push(`"~d":${chance(1 - bad * 5) ? JSON.stringify(deleted) : JSON.stringify(["missing"])}`);
      }
      if (chance(0.1)) {
        // A key order: a permutation of the result's keys, or (rarely) one naming a missing key.
        const shuffled = [...kept, ...added].sort(() => next() - 0.5);
        entries.push(`"~o":${JSON.stringify(chance(1 - bad * 10) ? shuffled : [...shuffled, "nope"])}`);
      }
      if (chance(bad)) {
        entries.push(`${JSON.stringify(pick(["~l", "~t", "~n"]))}:[]`);
      }
      return `{${entries.join(",")}}`;
    }
    return chance(1 - bad * 5) ? value(depth) : `{"~t":[]}`;
  };

  const first = object(0);
  const snapshots = [first];
  setReferenceObjectPatches(true);
  try {
    let previous: unknown = JSON.parse(first);
    for (let index = 0; index < 6; index += 1) {
      const patch = patchFor(previous, 0);
      snapshots.push(patch);
      try {
        previous = decodeHistory(JSON.parse(`[${snapshots.join(",")}]`)).at(-1);
      } catch {
        break;
      }
    }
  } finally {
    setReferenceObjectPatches(false);
  }
  return snapshots;
}

describe("the object-patch fast path against the reference", () => {
  it("decodes 600 random histories identically, or fails with the same message", () => {
    let decoded = 0;
    let failed = 0;
    for (let seed = 1; seed <= 600; seed += 1) {
      const snapshots = randomHistoryText(seed);
      // Every prefix: the valid ones decode, a malformed last patch fails.
      for (let length = 1; length <= snapshots.length; length += 1) {
        const text = `[${snapshots.slice(0, length).join(",")}]`;
        const reference = decodeWith(true, text);
        expect(decodeWith(false, text), `seed ${seed}: ${text}`).toEqual(reference);
        if (reference.ok) decoded += 1; else failed += 1;
      }
    }
    // The generator exercises both outcomes.
    expect(decoded).toBeGreaterThan(1500);
    expect(failed).toBeGreaterThan(50);
  });

  it.each([
    ["transport", transportFixture],
    ["cities v6", citiesV6],
  ])("decodes the %s fixture identically", (_name, bundle) => {
    const text = JSON.stringify((bundle as { history_delta: unknown }).history_delta);
    expect(decodeWith(false, text)).toEqual(decodeWith(true, text));
  });

  const generated = (process.env.VIEWER_EQUIVALENCE_BUNDLES ?? "").split(delimiter).filter(Boolean);
  it.runIf(generated.length > 0).each(generated)("decodes generated bundle %s identically", (file) => {
    const text = JSON.stringify(JSON.parse(readFileSync(file, "utf8")).history_delta);
    expect(decodeWith(false, text)).toEqual(decodeWith(true, text));
  });
});
