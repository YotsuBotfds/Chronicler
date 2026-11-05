import { describe, expect, it } from "vitest";
import type { TurnSnapshot } from "../../types";
import { bindingLabel, commonsRulesAt } from "../commonsRules";
import { receipt, record } from "./commonsRulesFixture";

const at = (commons: unknown, turn = 5, schema = 1) =>
  commonsRulesAt({ turn, livelihoods: { schema_version: schema, commons_rules: commons } } as unknown as TurnSnapshot, 2);

describe("commonsRulesAt", () => {
  it("accepts a dated, consistent record", () => {
    const good = record();
    expect(at(good)).toBe(good);
    expect(bindingLabel(good.receipts![0])).toBe("Yes");
  });

  it("keeps an unobserved turn unknown rather than empty", () => {
    const unobserved = record({ observed: false, receipts: null, decisions: null });
    expect(at(unobserved)?.observed).toBe(false);
    expect(at({ ...unobserved, receipts: [] })).toBeNull();
    expect(at({ ...record(), decisions: null })).toBeNull();
  });

  it("reads the cost-only ablation's would-be withholding", () => {
    const ablation = record({ mode: "cost_only", receipts: [receipt({ binding: null, extraction: 4, excess: 4, grievance_added: 0 })] });
    expect(at(ablation)?.mode).toBe("cost_only");
    expect(bindingLabel(ablation.receipts![0])).toBe("Would withhold 4");
    expect(at({ ...ablation, receipts: [receipt({ binding: null, extraction: 4, excess: 4 })] })).toBeNull();
    expect(at({ ...ablation, receipts: [receipt({ binding: false, extraction: 4, excess: 4, grievance_added: 0 })] })).toBeNull();
  });

  it("reads partial coverage and open access", () => {
    const partial = receipt({ paid: 1, coverage: 0.5, limit: 4.75, extraction: 4.75 });
    expect(at(record({ receipts: [partial] }))).not.toBeNull();
    const open = receipt({ paid: 0, coverage: 0, limit: 9.5, applied: false, extraction: 3, binding: false, grievance_added: 0 });
    expect(bindingLabel(open)).toBe("Not tightened");
    expect(at(record({ receipts: [open] }))).not.toBeNull();
    const share = receipt({ institution_share: 0.5, bill: 1, paid: 1, coverage: 1 });
    expect(at(record({ receipts: [share] }))).not.toBeNull();
  });

  it("rejects absent, future, foreign and inconsistent data", () => {
    const good = record();
    expect(commonsRulesAt(null, 2)).toBeNull();
    expect(commonsRulesAt({ turn: 5 } as TurnSnapshot, 2)).toBeNull();
    expect(at(good, 5, 2)).toBeNull();
    expect(at(good, 6)).toBeNull();
    for (const bad of [undefined, { ...good, schema_version: 2 }, { ...good, units: { timber: "wood", money: "treasury" } },
      { ...good, mode: "strict" }, { ...good, source_turn: 5 }, { ...good, parameters: { ...good.parameters, admin_cost: -1 } },
      { ...good, counters: { paid: Number.NaN } }, { ...good, rules: [good.rules[0], good.rules[0]] },
      { ...good, rules: [{ ...good.rules[0], adopted_turn: 5 }] },
      { ...good, receipts: [receipt(), receipt()] }, { ...good, receipts: [receipt({ region_id: 2 })] },
      { ...good, receipts: [receipt({ observation: { turn: 4, stock: 1, capacity: 1, extraction: 0, water_gate_open: true } })] },
      { ...good, receipts: [receipt({ coverage: 0.5 })] }, { ...good, receipts: [receipt({ paid: 3, bill: 3, required: 2 })] },
      { ...good, receipts: [receipt({ quota: 1 })] }, { ...good, receipts: [receipt({ extraction: 1 })] },
      { ...good, receipts: [receipt({ limit: 10 })] }, { ...good, receipts: [receipt({ applied: false })] },
      { ...good, receipts: [receipt({ excess: 1 })] }, { ...good, receipts: [receipt({ binding: null })] },
      { ...good, receipts: [receipt({ city: null })] }, { ...good, receipts: [receipt({ neighbour_open_extraction: 2 })] },
      { ...good, receipts: [receipt({ craft_output: Number.POSITIVE_INFINITY })] },
      { ...good, decisions: [{ ...good.decisions![0], turn: 3 }] }, { ...good, decisions: [{ ...good.decisions![0], kind: "seized" }] }]) {
      expect(at(bad)).toBeNull();
    }
  });
});
