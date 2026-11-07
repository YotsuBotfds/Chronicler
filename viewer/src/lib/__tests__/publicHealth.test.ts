import { describe, expect, it } from "vitest";
import type { Bundle, TurnSnapshot } from "../../types";
import { publicHealthAt, readPublicHealth } from "../publicHealth";

const valid = () => ({ schema_version: 1, source_turn: 4, enabled: true, mode: "active", policy: "evidence",
  report_delay: 0, report_turn: 4, environment_turn: 4, supply_turn: 4, supplies: [], decisions: [], totals: {},
  environment: [{ region: 0, source_turn: 3, residence_observed: false, sanitation_observed: true,
    displaced_share: 0, water_service: 0, crowding_factor: 1, flux_factor: 1 }] });
const snapshot = (raw: unknown = valid()) => ({ turn: 5, livelihoods: { schema_version: 1, public_health: raw } }) as unknown as TurnSnapshot;
const bundle = (history: TurnSnapshot[]) => ({ history, world_state: { regions: [{ name: "A" }, { name: "B" }], civilizations: [{ name: "C" }, { name: "D" }] } }) as unknown as Bundle;

describe("public health strict reading", () => {
  it("accepts dated zeros and separates absent, off and unobserved", () => {
    const s = snapshot();
    expect(publicHealthAt(s, 2, 2)).not.toBeNull();
    expect(readPublicHealth(bundle([s]), s).state).toBe("recorded_zero");
    const absent = { turn: 6 } as TurnSnapshot;
    expect(readPublicHealth(bundle([s, absent]), absent).state).toBe("absent");
    expect(readPublicHealth(bundle([absent]), absent).state).toBe("disabled");
    const raw = valid();
    Object.assign(raw, { report_turn: null, environment_turn: null, supply_turn: null, environment: [] });
    const u = snapshot(raw);
    expect(readPublicHealth(bundle([u]), u).state).toBe("unobserved");
  });
  it.each(["source_turn", "report_turn", "environment_turn", "supply_turn"])("rejects misdated %s", key => {
    expect(publicHealthAt(snapshot({ ...valid(), [key]: 99 }), 2, 2)).toBeNull();
  });
  it("refuses malformed supply and environment rather than displaying invented zero", () => {
    const s = snapshot({ ...valid(), supplies: [{ turn: 4, civ: 0, region: 0, source: 1, seller: 1,
      need_milli: 100, food_milli: 200, charged_milli: 1000, internal_milli: 0, patients: 1,
      price_milli: 1000, reason: "supplied" }] });
    expect(readPublicHealth(bundle([s]), s).state).toBe("malformed");
    const env = valid().environment[0];
    expect(publicHealthAt(snapshot({ ...valid(), environment: [{ ...env, source_turn: 4 }] }), 2, 2)).toBeNull();
    expect(publicHealthAt(snapshot({ ...valid(), environment: [{ ...env, displaced_share: 2 }] }), 2, 2)).toBeNull();
  });
});
