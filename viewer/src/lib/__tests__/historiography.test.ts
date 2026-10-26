import { describe, expect, it } from "vitest";
import { COLUMNS, sampleField } from "../../__fixtures__/historiographyField";
import { accountsAsOf, accountsForEvent, capitalized, decodeAccounts, lossPhrase } from "../historiography";

describe("historiography field", () => {
  it("decodes rows by their named columns", () => {
    const rows = decodeAccounts(sampleField());
    expect(rows).toHaveLength(4);
    expect(rows[0]).toMatchObject({
      id: "court:0/4:war:1", chroniclerName: "the Ashkari chronicles", stance: "victory", status: "told",
    });
    expect(rows[0].transforms.map((t) => t.kind)).toEqual(["inflate", "praise"]);
    expect(rows[1]).toMatchObject({ status: "lost", lostTurn: 10, lostCause: "sack" });
    expect(rows[2].status).toBe("silent");
  });

  it("collects an event's accounts, plain tellings and divergence", () => {
    const field = sampleField();
    const event = accountsForEvent(field, "4:war:1");
    expect(event?.accounts.map((a) => `${a.chronicler}:${a.status}`)).toEqual([
      "court:0:told", "court:1:lost", "temple:0:silent", "court:2:plain",
    ]);
    expect(event?.divergence).toEqual(["lost", "magnitude", "ruler", "silence"]);
    expect(accountsForEvent(field, "9:famine:0")?.divergence).toEqual([]);
  });

  it("is absent for bundles without the field and events without accounts", () => {
    expect(accountsForEvent(undefined, "4:war:1")).toBeNull();
    expect(accountsForEvent(sampleField(), undefined)).toBeNull();
    expect(accountsForEvent(sampleField(), "1:none:0")).toBeNull();
  });

  it("tolerates a reordered column layout", () => {
    const field = sampleField();
    const order = [...COLUMNS].reverse();
    field.account_columns = order;
    field.accounts = field.accounts.map((row) => order.map((name) => row[COLUMNS.indexOf(name)]));
    expect(decodeAccounts(field)[0].text).toContain("Chancellor Zhara");
  });

  it("phrases losses and names", () => {
    expect(lossPhrase("sack")).toBe("sacked");
    expect(lossPhrase("flight")).toBe("thinned on its scholars' flight");
    expect(lossPhrase(null)).toBe("lost");
    expect(capitalized("the Kethani chronicles")).toBe("The Kethani chronicles");
  });

  it("gives an event's accounts as known at a turn: a copy lost later still stands", () => {
    // court:1's archive is sacked at turn 10 (the field holds the final losses).
    const before = accountsForEvent(sampleField(), "4:war:1", undefined, 9)!;
    const kethani = before.accounts.find((a) => a.chronicler === "court:1")!;
    expect(kethani).toMatchObject({ status: "told", lostTurn: null, lostCause: null });
    expect(before.divergence).toEqual(["magnitude", "ruler", "silence"]);
    const after = accountsForEvent(sampleField(), "4:war:1", undefined, 10)!;
    expect(after.accounts.find((a) => a.chronicler === "court:1")).toMatchObject({ status: "lost", lostTurn: 10 });
    expect(after).toEqual(accountsForEvent(sampleField(), "4:war:1"));
    // Every copy lost at the end, one standing at the turn: lost is a divergence then.
    const all = accountsAsOf({
      accounts: before.accounts.filter((a) => a.chronicler !== "court:2").map((a) => ({
        ...a, status: "lost" as const, lostTurn: a.chronicler === "court:1" ? 10 : 20, lostCause: "sack",
      })),
      divergence: [],
    }, 15);
    expect(all.divergence).toEqual(["lost"]);
    expect(all.accounts.filter((a) => a.status === "lost").map((a) => a.chronicler)).toEqual(["court:1"]);
  });
});
