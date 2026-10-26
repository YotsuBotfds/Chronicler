/// <reference types="node" />
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import fixture from "../../__fixtures__/transport_bundle.json";
import { parseBundle } from "../../hooks/useBundle";
import type { Bundle } from "../../types";
import {
  applyCompletedMessage, BUNDLE_CARRIERS, BUNDLE_SYSTEMS, bundleFromInitMessage, SNAPSHOT_FIELDS,
  SNAPSHOT_SYSTEMS, snapshotFromMessage, TURN_MESSAGE_KEYS, withSessionToken,
} from "../transport";

const staticBundle = parseBundle(JSON.stringify(fixture)).bundle as Bundle;

describe("transport contract", () => {
  it("is the file the Python side reads", () => {
    // Tests run from viewer/; the contract lives in the Python package.
    const python = JSON.parse(readFileSync(resolve(process.cwd(), "../src/chronicler/transport_contract.json"),
      "utf-8"));
    expect([...SNAPSHOT_SYSTEMS]).toEqual(python.snapshot_systems);
    expect([...SNAPSHOT_FIELDS]).toEqual(python.snapshot_fields);
    expect([...BUNDLE_SYSTEMS]).toEqual(python.bundle_systems);
  });

  it("names every field of the fixture's snapshots, and the fixture holds every system", () => {
    const named = new Set<string>([...SNAPSHOT_FIELDS, ...SNAPSHOT_SYSTEMS]);
    for (const snapshot of staticBundle.history) {
      for (const key of Object.keys(snapshot)) {
        expect(named.has(key), key).toBe(true);
      }
      for (const key of SNAPSHOT_SYSTEMS) {
        expect(key in snapshot, key).toBe(true);
      }
    }
    for (const key of [...BUNDLE_SYSTEMS, ...BUNDLE_CARRIERS]) {
      expect(staticBundle[key], key).toBeTruthy();
    }
  });

  it("turns a turn message into the static snapshot", () => {
    for (const snapshot of staticBundle.history) {
      const message = { ...snapshot, type: "turn", chronicle_text: "t", events: [], named_events: [] };
      expect(snapshotFromMessage(message)).toEqual(snapshot);
      expect(Object.keys(snapshotFromMessage(message)).some((k) => TURN_MESSAGE_KEYS.includes(k))).toBe(false);
    }
  });

  it("rebuilds the static bundle from a reconnect init, and merges completion systems", () => {
    const init = {
      type: "init", state: "running", world_state: staticBundle.world_state, history: staticBundle.history,
      events_timeline: staticBundle.events_timeline, named_events: staticBundle.named_events,
      chronicle_entries: staticBundle.chronicle_entries, gap_summaries: staticBundle.gap_summaries,
      era_reflections: staticBundle.era_reflections, metadata: staticBundle.metadata,
      historiography: staticBundle.historiography, languages: staticBundle.languages,
      pruned_civ_stats: staticBundle.pruned_civ_stats,
    };
    expect(bundleFromInitMessage(init)).toEqual(staticBundle);
    const bare = bundleFromInitMessage({ ...init, historiography: undefined, languages: null });
    expect(bare.historiography).toBeUndefined();
    const done = applyCompletedMessage(bare, { type: "completed", systems: { historiography: staticBundle.historiography } });
    expect(done.historiography).toEqual(staticBundle.historiography);
    expect(applyCompletedMessage(bare, { type: "completed" })).toBe(bare);
  });

  it("adds the session token to the WebSocket URL once", () => {
    expect(withSessionToken("ws://localhost:8765", "abc")).toBe("ws://localhost:8765/?token=abc");
    expect(withSessionToken("ws://localhost:8765/?token=x", "abc")).toBe("ws://localhost:8765/?token=x");
    expect(withSessionToken("ws://localhost:8765", null)).toBe("ws://localhost:8765");
    expect(withSessionToken("ws://127.0.0.1:5173/qa-stream", "t")).toBe("ws://127.0.0.1:5173/qa-stream?token=t");
  });
});
