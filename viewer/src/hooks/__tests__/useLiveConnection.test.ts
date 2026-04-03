import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useLiveConnection } from "../useLiveConnection";

class MockWebSocket {
  static instances: MockWebSocket[] = [];
  onopen: (() => void) | null = null;
  onclose: (() => void) | null = null;
  onmessage: ((e: { data: string }) => void) | null = null;
  onerror: ((e: unknown) => void) | null = null;
  readyState = 0;
  sent: string[] = [];
  static OPEN = 1;
  static CLOSED = 3;
  static CONNECTING = 0;

  url: string;
  constructor(url: string) {
    this.url = url;
    MockWebSocket.instances.push(this);
    setTimeout(() => {
      this.readyState = 1;
      this.onopen?.();
    }, 0);
  }

  send(data: string) {
    this.sent.push(data);
  }

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

const SAMPLE_INIT = {
  type: "init",
  total_turns: 50,
  pause_every: 10,
  current_turn: 0,
  world_state: { name: "TestWorld", seed: 42, turn: 0, regions: [], civilizations: [], relationships: {}, events_timeline: [], named_events: [], scenario_name: null },
  history: [],
  chronicle_entries: {},
  events_timeline: [],
  named_events: [],
  era_reflections: {},
  metadata: { seed: 42, total_turns: 50, generated_at: "", sim_model: "test", narrative_model: "test", scenario_name: null, interestingness_score: null },
  speed: 1.0,
};

describe("useLiveConnection", () => {
  it("does not connect when wsUrl is empty", async () => {
    renderHook(() => useLiveConnection(""));
    await vi.advanceTimersByTimeAsync(100);
    expect(MockWebSocket.instances.length).toBe(0);
  });

  it("connects and sets connected state on init", async () => {
    const { result } = renderHook(() => useLiveConnection("ws://localhost:8765"));
    await vi.advanceTimersByTimeAsync(10);
    expect(MockWebSocket.instances.length).toBe(1);

    act(() => {
      MockWebSocket.instances[0].simulateMessage(SAMPLE_INIT);
    });

    expect(result.current.connected).toBe(true);
    expect(result.current.bundle).not.toBeNull();
    expect(result.current.bundle?.world_state.name).toBe("TestWorld");
  });

  it("accumulates turn data into bundle", async () => {
    const { result } = renderHook(() => useLiveConnection("ws://localhost:8765"));
    await vi.advanceTimersByTimeAsync(10);
    const ws = MockWebSocket.instances[0];
    act(() => ws.simulateMessage(SAMPLE_INIT));

    act(() => {
      ws.simulateMessage({
        type: "turn",
        turn: 1,
        civ_stats: {},
        region_control: {},
        relationships: {},
        events: [],
        named_events: [],
        chronicle_text: "Turn 1 text",
      });
    });

    expect(result.current.bundle?.history.length).toBe(1);
    const entries = result.current.bundle?.chronicle_entries;
    expect(entries && !Array.isArray(entries) ? entries["1"] : undefined).toBe("Turn 1 text");
  });

  it("preserves gap summaries from live init payloads", async () => {
    const { result } = renderHook(() => useLiveConnection("ws://localhost:8765"));
    await vi.advanceTimersByTimeAsync(10);
    const ws = MockWebSocket.instances[0];

    act(() => {
      ws.simulateMessage({
        ...SAMPLE_INIT,
        gap_summaries: [
          {
            turn_range: [2, 4],
            event_count: 3,
            top_event_type: "trade",
            stat_deltas: {},
            territory_changes: 1,
          },
        ],
      });
    });

    expect(result.current.bundle?.gap_summaries).toHaveLength(1);
    expect(result.current.bundle?.gap_summaries?.[0]?.turn_range).toEqual([2, 4]);
  });

  it("preserves optional turn snapshot fields from live turn messages", async () => {
    const { result } = renderHook(() => useLiveConnection("ws://localhost:8765"));
    await vi.advanceTimersByTimeAsync(10);
    const ws = MockWebSocket.instances[0];
    act(() => ws.simulateMessage(SAMPLE_INIT));

    act(() => {
      ws.simulateMessage({
        type: "turn",
        turn: 2,
        civ_stats: {},
        region_control: {},
        relationships: {},
        trade_routes: [["Civ A", "Civ B"]],
        active_wars: [["Civ B", "Civ C"]],
        embargoes: [["Civ C", "Civ D"]],
        active_conditions: [{ type: "drought", severity: 20 }],
        settlement_source_turn: 1,
        founded_this_turn: [11],
        dissolved_this_turn: [9],
        urban_fraction: 0.4,
        events: [],
        named_events: [],
        chronicle_text: "Turn 2 text",
      });
    });

    const snapshot = result.current.bundle?.history[0];
    expect(snapshot?.trade_routes).toEqual([["Civ A", "Civ B"]]);
    expect(snapshot?.active_wars).toEqual([["Civ B", "Civ C"]]);
    expect(snapshot?.embargoes).toEqual([["Civ C", "Civ D"]]);
    expect(snapshot?.active_conditions).toEqual([{ type: "drought", severity: 20 }]);
    expect(snapshot?.settlement_source_turn).toBe(1);
    expect(snapshot?.founded_this_turn).toEqual([11]);
    expect(snapshot?.dissolved_this_turn).toEqual([9]);
    expect(snapshot?.urban_fraction).toBe(0.4);
  });

  it("sets paused state on paused message", async () => {
    const { result } = renderHook(() => useLiveConnection("ws://localhost:8765"));
    await vi.advanceTimersByTimeAsync(10);
    const ws = MockWebSocket.instances[0];
    act(() => ws.simulateMessage(SAMPLE_INIT));
    act(() => {
      ws.simulateMessage({
        type: "paused",
        turn: 10,
        reason: "era_boundary",
        valid_commands: ["continue", "inject"],
        injectable_events: ["plague"],
        settable_stats: ["military"],
        civs: ["Civ A"],
      });
    });

    expect(result.current.paused).toBe(true);
    expect(result.current.pauseContext?.civs).toEqual(["Civ A"]);
  });

  it("clears paused on ack with still_paused=false", async () => {
    const { result } = renderHook(() => useLiveConnection("ws://localhost:8765"));
    await vi.advanceTimersByTimeAsync(10);
    const ws = MockWebSocket.instances[0];
    act(() => ws.simulateMessage(SAMPLE_INIT));
    act(() => {
      ws.simulateMessage({ type: "paused", turn: 10, reason: "era_boundary", valid_commands: [], injectable_events: [], settable_stats: [], civs: [] });
    });
    expect(result.current.paused).toBe(true);

    act(() => {
      ws.simulateMessage({ type: "ack", command: "continue", detail: "Resumed", still_paused: false });
    });
    expect(result.current.paused).toBe(false);
  });

  it("keeps paused on ack with still_paused=true", async () => {
    const { result } = renderHook(() => useLiveConnection("ws://localhost:8765"));
    await vi.advanceTimersByTimeAsync(10);
    const ws = MockWebSocket.instances[0];
    act(() => ws.simulateMessage(SAMPLE_INIT));
    act(() => {
      ws.simulateMessage({ type: "paused", turn: 10, reason: "era_boundary", valid_commands: [], injectable_events: [], settable_stats: [], civs: [] });
    });

    act(() => {
      ws.simulateMessage({ type: "ack", command: "inject", detail: "Queued plague", still_paused: true });
    });
    expect(result.current.paused).toBe(true);
  });

  it("patches snapshot on set ack", async () => {
    const { result } = renderHook(() => useLiveConnection("ws://localhost:8765"));
    await vi.advanceTimersByTimeAsync(10);
    const ws = MockWebSocket.instances[0];

    const initWithHistory = {
      ...SAMPLE_INIT,
      history: [{ turn: 1, civ_stats: { "CivA": { military: 5 } }, region_control: {}, relationships: {} }],
      current_turn: 1,
    };
    act(() => ws.simulateMessage(initWithHistory));

    act(() => {
      ws.simulateMessage({ type: "ack", command: "set", detail: "Set", still_paused: true, civ: "CivA", stat: "military", value: 9 });
    });

    const lastSnap = result.current.bundle?.history[0];
    expect(lastSnap?.civ_stats["CivA"]?.military).toBe(9);
  });

  it("sets error state on error message", async () => {
    const { result } = renderHook(() => useLiveConnection("ws://localhost:8765"));
    await vi.advanceTimersByTimeAsync(10);
    const ws = MockWebSocket.instances[0];
    act(() => ws.simulateMessage(SAMPLE_INIT));

    act(() => {
      ws.simulateMessage({ type: "error", message: "Civ 'Foo' not found" });
    });

    expect(result.current.error).toBe("Civ 'Foo' not found");
  });

  it("sets connected false on close and attempts reconnect", async () => {
    const { result } = renderHook(() => useLiveConnection("ws://localhost:8765"));
    await vi.advanceTimersByTimeAsync(10);
    const ws = MockWebSocket.instances[0];
    act(() => ws.simulateMessage(SAMPLE_INIT));
    expect(result.current.connected).toBe(true);

    act(() => ws.close());
    expect(result.current.connected).toBe(false);

    // Should attempt reconnect after delay
    await vi.advanceTimersByTimeAsync(1500);
    expect(MockWebSocket.instances.length).toBe(2);
  });

  it("sends commands via sendCommand", async () => {
    const { result } = renderHook(() => useLiveConnection("ws://localhost:8765"));
    await vi.advanceTimersByTimeAsync(10);
    const ws = MockWebSocket.instances[0];
    act(() => ws.simulateMessage(SAMPLE_INIT));

    act(() => {
      result.current.sendCommand({ type: "continue" });
    });

    expect(ws.sent.length).toBe(1);
    expect(JSON.parse(ws.sent[0])).toEqual({ type: "continue" });
  });

  it("accepts validated live bundle payloads", async () => {
    const { result } = renderHook(() => useLiveConnection("ws://localhost:8765"));
    await vi.advanceTimersByTimeAsync(10);
    const ws = MockWebSocket.instances[0];

    act(() => {
      ws.simulateMessage({
        type: "bundle_loaded",
        bundle: {
          ...SAMPLE_INIT,
          era_reflections: {},
        },
      });
    });

    expect(result.current.bundle?.world_state.name).toBe("TestWorld");
    expect(result.current.error).toBeNull();
  });

  it("rejects malformed live bundle payloads without poisoning app state", async () => {
    const { result } = renderHook(() => useLiveConnection("ws://localhost:8765"));
    await vi.advanceTimersByTimeAsync(10);
    const ws = MockWebSocket.instances[0];

    act(() => ws.simulateMessage(SAMPLE_INIT));
    act(() => {
      ws.simulateMessage({
        type: "bundle_loaded",
        bundle: {
          manifest_version: 1,
          layers: [],
        },
      });
    });

    expect(result.current.bundle?.world_state.name).toBe("TestWorld");
    expect(result.current.error).toContain("Bundle v2 manifest");
  });
});

const SAMPLE_LOBBY_INIT = {
  type: "init",
  state: "lobby",
  scenarios: [
    {
      file: "test.yaml",
      name: "Test Scenario",
      description: "A test",
      world_name: "TestWorld",
      civs: [{ name: "TestCiv", values: ["Honor"] }],
      regions: [{ name: "TestRegion", terrain: "plains", x: null, y: null }],
    },
  ],
  models: ["test-model"],
  defaults: { turns: 50, civs: 4, regions: 8, seed: null },
};

describe("lobby state", () => {
  it("sets serverState to lobby on lobby init", async () => {
    const { result } = renderHook(() => useLiveConnection("ws://localhost:8765"));
    await vi.advanceTimersByTimeAsync(10);
    const ws = MockWebSocket.instances[0];

    act(() => ws.simulateMessage(SAMPLE_LOBBY_INIT));

    expect(result.current.serverState).toBe("lobby");
    expect(result.current.lobbyInit).not.toBeNull();
    expect(result.current.lobbyInit?.scenarios.length).toBe(1);
    expect(result.current.bundle).toBeNull();
  });

  it("treats init without state field as running (backward compat)", async () => {
    const { result } = renderHook(() => useLiveConnection("ws://localhost:8765"));
    await vi.advanceTimersByTimeAsync(10);
    const ws = MockWebSocket.instances[0];

    act(() => ws.simulateMessage(SAMPLE_INIT));

    expect(result.current.serverState).toBe("running");
    expect(result.current.bundle).not.toBeNull();
  });

  it("sendStart transitions to starting and sends start command", async () => {
    const { result } = renderHook(() => useLiveConnection("ws://localhost:8765"));
    await vi.advanceTimersByTimeAsync(10);
    const ws = MockWebSocket.instances[0];
    act(() => ws.simulateMessage(SAMPLE_LOBBY_INIT));

    act(() => {
      result.current.sendStart({
        scenario: "test.yaml",
        turns: 50,
        seed: 42,
        civs: 4,
        regions: 8,
        sim_model: "test-model",
        narrative_model: "test-model",
        narrator: "local",
        resume_state: null,
      });
    });

    expect(result.current.serverState).toBe("starting");
    expect(ws.sent.length).toBe(1);
    const sent = JSON.parse(ws.sent[0]);
    expect(sent.type).toBe("start");
    expect(sent.scenario).toBe("test.yaml");
  });

  it("reverts to lobby on error during starting", async () => {
    const { result } = renderHook(() => useLiveConnection("ws://localhost:8765"));
    await vi.advanceTimersByTimeAsync(10);
    const ws = MockWebSocket.instances[0];
    act(() => ws.simulateMessage(SAMPLE_LOBBY_INIT));

    act(() => {
      result.current.sendStart({
        scenario: "bad.yaml", turns: 50, seed: 42, civs: 4, regions: 8,
        sim_model: "m", narrative_model: "m", narrator: "local", resume_state: null,
      });
    });
    expect(result.current.serverState).toBe("starting");

    act(() => ws.simulateMessage({ type: "error", message: "Scenario not found" }));
    expect(result.current.serverState).toBe("lobby");
    expect(result.current.error).toBe("Scenario not found");
  });

  it("full retry: starting → error → lobby → retry → starting → running", async () => {
    const { result } = renderHook(() => useLiveConnection("ws://localhost:8765"));
    await vi.advanceTimersByTimeAsync(10);
    const ws = MockWebSocket.instances[0];
    act(() => ws.simulateMessage(SAMPLE_LOBBY_INIT));

    // First attempt fails
    act(() => {
      result.current.sendStart({
        scenario: "bad.yaml", turns: 50, seed: 42, civs: 4, regions: 8,
        sim_model: "m", narrative_model: "m", narrator: "local", resume_state: null,
      });
    });
    expect(result.current.serverState).toBe("starting");

    act(() => ws.simulateMessage({ type: "error", message: "Not found" }));
    expect(result.current.serverState).toBe("lobby");

    // Second attempt succeeds
    act(() => {
      result.current.sendStart({
        scenario: "test.yaml", turns: 50, seed: 42, civs: 4, regions: 8,
        sim_model: "m", narrative_model: "m", narrator: "local", resume_state: null,
      });
    });
    expect(result.current.serverState).toBe("starting");
    expect(ws.sent.length).toBe(2);

    act(() => ws.simulateMessage({ ...SAMPLE_INIT, state: "running" }));
    expect(result.current.serverState).toBe("running");
    expect(result.current.bundle).not.toBeNull();
    expect(result.current.error).toBeNull();
  });

  it("handles server-sent starting state during world gen", async () => {
    const { result } = renderHook(() => useLiveConnection("ws://localhost:8765"));
    await vi.advanceTimersByTimeAsync(10);
    const ws = MockWebSocket.instances[0];

    act(() => ws.simulateMessage({ type: "init", state: "starting" }));
    expect(result.current.serverState).toBe("starting");
  });
});
