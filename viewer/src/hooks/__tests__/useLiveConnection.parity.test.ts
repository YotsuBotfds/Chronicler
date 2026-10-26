/**
 * Static upload, Batch Lab, streaming and reconnect carry the same bundle.
 *
 * One fixture holds every optional system (scripts/build_transport_fixture.py).
 * Each live path must give the bundle a static upload of the same file gives:
 * every snapshot key and every top-level system.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, renderHook } from "@testing-library/react";
import fixture from "../../__fixtures__/transport_bundle.json";
import { parseBundle } from "../useBundle";
import { useLiveConnection } from "../useLiveConnection";
import type { Bundle } from "../../types";

class MockWebSocket {
  static instances: MockWebSocket[] = [];
  onopen: (() => void) | null = null;
  onclose: (() => void) | null = null;
  onmessage: ((e: { data: string }) => void) | null = null;
  onerror: ((e: unknown) => void) | null = null;
  readyState = 0;
  static OPEN = 1;
  url: string;
  constructor(url: string) {
    this.url = url;
    MockWebSocket.instances.push(this);
    setTimeout(() => {
      this.readyState = 1;
      this.onopen?.();
    }, 0);
  }
  send() {}
  close() {
    this.readyState = 3;
    this.onclose?.();
  }
  simulateMessage(data: object) {
    this.onmessage?.({ data: JSON.stringify(data) });
  }
}

beforeEach(() => {
  MockWebSocket.instances = [];
  vi.stubGlobal("WebSocket", MockWebSocket);
  vi.useFakeTimers();
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

const staticBundle = parseBundle(JSON.stringify(fixture)).bundle as Bundle;
const TOP_LEVEL_SYSTEMS = ["historiography", "languages"] as const;

/** Every snapshot key and top-level system of the static bundle, as the live bundle holds them. */
function expectSameData(live: Bundle | null) {
  expect(live).not.toBeNull();
  expect(live!.history.length).toBe(staticBundle.history.length);
  live!.history.forEach((snapshot, index) => {
    const want = staticBundle.history[index] as unknown as Record<string, unknown>;
    const got = snapshot as unknown as Record<string, unknown>;
    for (const key of Object.keys(want)) {
      expect(got[key], `history[${index}].${key}`).toEqual(want[key]);
    }
  });
  for (const key of TOP_LEVEL_SYSTEMS) {
    expect(live![key], key).toEqual(staticBundle[key]);
  }
}

async function connect() {
  const hook = renderHook(() => useLiveConnection("ws://localhost:8765", "session-token"));
  await vi.advanceTimersByTimeAsync(10);
  return { hook, ws: MockWebSocket.instances[MockWebSocket.instances.length - 1] };
}

function runningInit(history: unknown[], extra: Record<string, unknown> = {}) {
  return {
    type: "init", state: "running", total_turns: 10, pause_every: 10, current_turn: 0,
    world_state: staticBundle.world_state, history, chronicle_entries: {}, events_timeline: [],
    named_events: [], era_reflections: {}, metadata: staticBundle.metadata, speed: 1, ...extra,
  };
}

describe("one fixture through every load path", () => {
  it("the fixture holds the optional systems", () => {
    for (const key of ["guilds", "cities", "agent_movements", "food", "migration", "campaign"]) {
      expect(staticBundle.history.every((s) => key in s), key).toBe(true);
    }
    for (const key of TOP_LEVEL_SYSTEMS) {
      expect(staticBundle[key], key).toBeTruthy();
    }
  });

  it("Batch Lab: bundle_loaded keeps every system", async () => {
    const { hook, ws } = await connect();
    act(() => ws.simulateMessage({ type: "bundle_loaded", bundle: staticBundle, path: "output/x.json", turns: 10 }));
    expectSameData(hook.result.current.bundle);
  });

  it("streaming: turn messages and completion keep every system", async () => {
    const { hook, ws } = await connect();
    act(() => ws.simulateMessage(runningInit([])));
    for (const snapshot of staticBundle.history) {
      act(() => ws.simulateMessage({ ...snapshot, type: "turn", chronicle_text: "", events: [], named_events: [] }));
    }
    act(() => ws.simulateMessage({
      type: "completed", total_turns: 10, bundle_path: "output/chronicle_bundle.json",
      systems: { historiography: staticBundle.historiography, languages: staticBundle.languages },
    }));
    expectSameData(hook.result.current.bundle);
  });

  it("reconnect: the init the server rebuilds keeps every system", async () => {
    const { hook, ws } = await connect();
    // The server's reconnect history rows are its turn messages without the turn-only keys.
    act(() => ws.simulateMessage(runningInit(staticBundle.history, {
      historiography: staticBundle.historiography, languages: staticBundle.languages,
    })));
    expectSameData(hook.result.current.bundle);
  });

  it("reconnect rows that still carry turn-message keys read as snapshots", async () => {
    const { hook, ws } = await connect();
    const rows = staticBundle.history.map((s) => ({ ...s, chronicle_text: "x", events: [], named_events: [] }));
    act(() => ws.simulateMessage(runningInit(rows)));
    const first = hook.result.current.bundle!.history[0] as unknown as Record<string, unknown>;
    expect("chronicle_text" in first || "events" in first).toBe(false);
  });
});

describe("live session token", () => {
  it("connects with the token from the viewer link", async () => {
    await connect();
    expect(MockWebSocket.instances[0].url).toBe("ws://localhost:8765/?token=session-token");
  });

  it("explains a refused connection", async () => {
    // Never opens: closes straight away, as a refused (403) handshake does.
    class Refused {
      static OPEN = 1;
      onopen: (() => void) | null = null;
      onclose: (() => void) | null = null;
      onmessage: ((e: { data: string }) => void) | null = null;
      onerror: ((e: unknown) => void) | null = null;
      readyState = 0;
      url: string;
      constructor(url: string) {
        this.url = url;
        setTimeout(() => {
          this.readyState = 3;
          this.onclose?.();
        }, 0);
      }
      send() {}
      close() {}
    }
    vi.stubGlobal("WebSocket", Refused);
    const hook = renderHook(() => useLiveConnection("ws://localhost:8765", null));
    await act(async () => { await vi.advanceTimersByTimeAsync(10); });
    expect(hook.result.current.error).toBeNull();
    await act(async () => { await vi.advanceTimersByTimeAsync(1100); });
    expect(hook.result.current.error).toMatch(/session token/);
    expect(hook.result.current.connected).toBe(false);
  });
});
