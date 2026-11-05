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
// The checked-in fixture predates food accounting, household mobility and the
// livelihoods sprint record. This current example exercises the new fields without
// rewriting that historical fixture.
const currentBundle: Bundle = {
  ...staticBundle,
  history: staticBundle.history.map((snapshot) => ({
    ...snapshot,
    food_accounting: {
      schema_version: 1, mode: "off", source_turn: snapshot.turn - 1,
      completed_turn: snapshot.turn, timing: "phase2", units: "model_food_goods",
      transport: "none", regions: [], procurement: [],
    },
    household_mobility: {
      schema_version: 1, source_turn: snapshot.turn - 1, completed_turn: snapshot.turn,
      timing: "agent_decision_post_consolidation", mode: "hybrid",
      wealth_units: "native_agent_wealth", person_units: "native_agents",
      passed_means: "gate_passed_not_observed_move", requirement_per_native_person: 1,
      proposed_groups: 0, proposed_native_persons: 0, passed_groups: 0,
      passed_native_persons: 0, blocked_groups: 0, blocked_native_persons: 0,
      dropped_samples: 0, samples: [],
    },
    livelihoods: { schema_version: 1 },
  })),
};

describe("transport contract", () => {
  it("is the file the Python side reads", () => {
    // Tests run from viewer/; the contract lives in the Python package.
    const python = JSON.parse(readFileSync(resolve(process.cwd(), "../src/chronicler/transport_contract.json"),
      "utf-8"));
    expect([...SNAPSHOT_SYSTEMS]).toEqual(python.snapshot_systems);
    expect([...SNAPSHOT_FIELDS]).toEqual(python.snapshot_fields);
    expect([...BUNDLE_SYSTEMS]).toEqual(python.bundle_systems);
  });

  it("names every field of historical and current snapshots, with all current systems", () => {
    const named = new Set<string>([...SNAPSHOT_FIELDS, ...SNAPSHOT_SYSTEMS]);
    for (const snapshot of staticBundle.history) {
      expect(snapshot.food_accounting).toBeUndefined();
      expect("household_mobility" in snapshot).toBe(false);
      expect("livelihoods" in snapshot).toBe(false);
    }
    for (const snapshot of currentBundle.history) {
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
    for (const snapshot of [...staticBundle.history, ...currentBundle.history]) {
      const message = { ...snapshot, type: "turn", chronicle_text: "t", events: [], named_events: [] };
      expect(snapshotFromMessage(message)).toEqual(snapshot);
      expect(Object.keys(snapshotFromMessage(message)).some((k) => TURN_MESSAGE_KEYS.includes(k))).toBe(false);
    }
  });

  it("rebuilds the static bundle from a reconnect init, and merges completion systems", () => {
    // Round-trip both the historical and current bundle through batch parsing.
    const batch = parseBundle(JSON.stringify(currentBundle)).bundle as Bundle;
    expect(batch).toEqual(currentBundle);
    const init = {
      type: "init", state: "running", world_state: currentBundle.world_state, history: currentBundle.history,
      events_timeline: staticBundle.events_timeline, named_events: staticBundle.named_events,
      chronicle_entries: staticBundle.chronicle_entries, gap_summaries: staticBundle.gap_summaries,
      era_reflections: staticBundle.era_reflections, metadata: staticBundle.metadata,
      historiography: staticBundle.historiography, languages: staticBundle.languages,
      pruned_civ_stats: staticBundle.pruned_civ_stats,
    };
    expect(bundleFromInitMessage(init)).toEqual(currentBundle);
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
