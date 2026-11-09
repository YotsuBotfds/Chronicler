import { describe, expect, it } from "vitest";
import fixture from "../../__fixtures__/transport_bundle.json";
import { parseBundle } from "../bundleFile";
import { parseLiveInit, parseLiveTurn } from "../liveMessages";
import type { Bundle } from "../../types";

const bundle = parseBundle(JSON.stringify(fixture)).bundle as Bundle;
const row = bundle.history[0] as unknown as Record<string, unknown>;
const validTurn = { ...row, type: "turn", chronicle_text: "", events: [], named_events: [] };
const validInit = {
  type: "init", state: "running", world_state: bundle.world_state, history: bundle.history,
  metadata: bundle.metadata, speed: 1,
};

describe("parseLiveTurn", () => {
  it("accepts a turn message built from the transport fixture", () => {
    expect(row.turn).toBeGreaterThanOrEqual(1);
    const parsed = parseLiveTurn(validTurn);
    expect(parsed).toEqual({ ok: true, value: validTurn });
  });

  it("accepts a turn without the optional event arrays", () => {
    const rest: Record<string, unknown> = { ...validTurn };
    delete rest.events;
    delete rest.named_events;
    expect(parseLiveTurn(rest).ok).toBe(true);
  });

  const rejected: [string, unknown][] = [
    ["null", null],
    ["a string", "turn"],
    ["an array", [validTurn]],
    ["missing turn", { ...validTurn, turn: undefined }],
    ["NaN turn", { ...validTurn, turn: Number.NaN }],
    ["negative turn", { ...validTurn, turn: -1 }],
    ["zero turn", { ...validTurn, turn: 0 }],
    ["float turn", { ...validTurn, turn: 1.5 }],
    ["string turn", { ...validTurn, turn: "1" }],
    ["civ_stats array", { ...validTurn, civ_stats: [] }],
    ["missing region_control", { ...validTurn, region_control: undefined }],
    ["relationships null", { ...validTurn, relationships: null }],
    ["events string", { ...validTurn, events: "war" }],
    ["named_events object", { ...validTurn, named_events: {} }],
  ];
  it.each(rejected)("rejects %s", (_label, msg) => {
    const parsed = parseLiveTurn(msg);
    expect(parsed.ok).toBe(false);
    if (!parsed.ok) expect(parsed.reason).toMatch(/turn message/);
  });
});

describe("parseLiveInit", () => {
  it("accepts a running init built from the transport fixture", () => {
    expect(parseLiveInit(validInit)).toEqual({ ok: true, value: validInit });
  });

  it("accepts a running init with an empty history", () => {
    expect(parseLiveInit({ ...validInit, history: [] }).ok).toBe(true);
  });

  const world = bundle.world_state as unknown as Record<string, unknown>;
  const rejected: [string, unknown][] = [
    ["null", null],
    ["an array", [validInit]],
    ["missing world_state", { ...validInit, world_state: undefined }],
    ["world_state without regions", { ...validInit, world_state: { ...world, regions: undefined } }],
    ["world_state without civilizations", { ...validInit, world_state: { ...world, civilizations: {} } }],
    ["missing history", { ...validInit, history: undefined }],
    ["history object", { ...validInit, history: {} }],
    ["history row not a record", { ...validInit, history: [row, 3] }],
    ["history row without turn", { ...validInit, history: [{ ...row, turn: undefined }] }],
    ["history row with NaN turn", { ...validInit, history: [{ ...row, turn: Number.NaN }] }],
    ["metadata array", { ...validInit, metadata: [] }],
    ["missing metadata", { ...validInit, metadata: undefined }],
  ];
  it.each(rejected)("rejects %s", (_label, msg) => {
    const parsed = parseLiveInit(msg);
    expect(parsed.ok).toBe(false);
    if (!parsed.ok) expect(parsed.reason).toMatch(/init message/);
  });
});
