import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import type { Bundle } from "../../../types";
import { LivelihoodsPanel } from "../LivelihoodsPanel";
import { RecoveryChain } from "../RecoveryChain";
import { chainBundle, snapshotOf, without } from "../../../lib/__tests__/recoveryChainFixture";
afterEach(cleanup);

function props(bundle: Bundle, turn: number, extra: Record<string, unknown> = {}) {
  return { bundle, snapshot: snapshotOf(bundle, turn), currentTurn: turn, onSeek: vi.fn(), onSelectEvent: vi.fn(),
    onSelectRegion: vi.fn(), onSelectCivilization: vi.fn(), ...extra };
}
const nowTable = (region: string, turn: number) => within(screen.getByRole("table", { name: `Recovery chain in ${region} at snapshot ${turn}` }));
/** The current-snapshot table's cells of one link: [what, joined by, tradeoff]. */
function link(region: string, turn: number, title: string): string[] {
  const row = nowTable(region, turn).getByRole("rowheader", { name: title }).closest("tr")!;
  return within(row).getAllByRole("cell").map((c) => c.textContent ?? "");
}
/** A paragraph by its whole text (it can hold a button). */
const paragraph = (pattern: RegExp) => screen.getByText((_, el) => el?.tagName === "P" && pattern.test(el.textContent ?? ""));
const turnTable = (region: string) => within(screen.getByRole("table", { name: `Recovery chain in ${region} over snapshots` }));

describe("recovery chain view (natural records, template seed 23)", () => {
  it("shows the chain of the busiest region at the scrubbed snapshot, each link with how it is joined and its tradeoff", () => {
    render(<RecoveryChain {...props(chainBundle(), 28)} />);
    expect(screen.getByRole("heading", { name: "Recovery chain · snapshot 28" })).toBeInTheDocument();
    expect(screen.getByLabelText("Region")).toHaveValue("7");
    expect(screen.getByText(/^On in this run: Repair projects \(RS2\), Timber supply \(PL1\)/)).toHaveTextContent("Nothing in the chain is off.");
    const [store, storeJoin] = link("Sapphire Coast", 28, "Timber store to repair");
    expect(store).toMatch(/15\.17 at the start, 0 delivered, 4 held for repairs/);
    expect(store).toMatch(/Only project #0 held timber in the region this turn.*still join it by region/);
    expect(storeJoin).toMatch(/^Region only: the store is per region/);
    const [wages, wagesJoin, wagesTrade] = link("Sapphire Coast", 28, "Wages paid (PL3, RS2, PL1)");
    expect(wages).toMatch(/Granary crew of project #0 \(3, 13, 15, 20\): paid 8 coins/);
    expect(wages).toMatch(/Total paid in the region: 8 coins\./);
    expect(wagesJoin).toMatch(/^Stable id: /);
    expect(wagesTrade).toBe("farm labour taken by granary crews: 4 farmer-turns");
    const [granary, granaryJoin] = link("Sapphire Coast", 28, "Granary condition");
    expect(granary).toBe("Condition 0.822 (capacity 80); project #0 92.7% done; this turn 0.732 → 0.822.");
    expect(granaryJoin).toMatch(/^Stable id: a granary project's asset/);
    const [, expJoin] = link("Sapphire Coast", 28, "Woodcutting expedition (PL1)");
    expect(expJoin).toMatch(/^Region only: PL1 plans one timber need per region/);
    const [retail, retailJoin, retailTrade] = link("Sapphire Coast", 28, "Food purchases (PL4)");
    expect(retail).toMatch(/Pilot region since turn 14 .*75 people \(24 children\) in 39 households provisioned; 18 households paid 6\.179 coins/);
    expect(retailJoin).toMatch(/^Region only: .*not who paid/);
    expect(retailTrade).toBe("nobody priced out");
    expect(paragraph(/^Sapphire Coast over snapshots 13-29: repair projects stalled on 4 project-snapshots \(4 for want of timber\); 2 expeditions from the region \(#0, #1\), 15\.17 timber delivered home/)).toBeInTheDocument();
  });

  it("shows the woodcutting crew's farm labour away and the person sample by id after their wages", () => {
    render(<RecoveryChain {...props(chainBundle(), 22)} />);
    const [exp, , trade] = link("Sapphire Coast", 22, "Woodcutting expedition (PL1)");
    expect(exp).toMatch(/Expedition #1 to Mistwood \(2 hops, launched turn 19; crew 2, 3, 13, 14 of 4 launched\): crew of 4 outbound/);
    expect(trade).toBe("farm labour away: 2.8 farmer-turns (food sufficiency 1.034)");
    const [retail] = link("Sapphire Coast", 22, "Food purchases (PL4)");
    expect(retail).toMatch(/By id \(ration and status only, not who paid\): 2 fed at 0\.998 of 1; 3 fed/);
    expect(retail).toMatch(/20 \(household of 13\) fed at 1 of 1/);
  });

  it("follows the region picker, and draws the forest drawn down as a tradeoff", () => {
    render(<RecoveryChain {...props(chainBundle(), 28)} />);
    fireEvent.change(screen.getByLabelText("Region"), { target: { value: "1" } });
    const [forest, join, trade] = link("Iron Peaks", 28, "Forest stock (L3)");
    expect(forest).toMatch(/^Expedition #2 cut 0\.23 at Thornwood, slot 0: stock 322 → 321\.4 of 322\. L3 account: opening 370\.5, cleared 48\.5, extraction 0\.66/);
    expect(join).toMatch(/^Stable id: the expedition's receipt names the forest region and slot/);
    expect(trade).toBe("forest at 99.8% of capacity, drawn down 0.638");
    expect(screen.queryByRole("table", { name: /Sapphire Coast/ })).toBeNull();
    const strip = screen.getByRole("group", { name: "Recovery chain in Iron Peaks over snapshots" });
    expect(within(strip).getByRole("img", { name: "Forest stock (L3): forest stock drawn down, snapshots 28-29" })).toBeInTheDocument();
  });

  it("gives the strip a text form: a turn table with a seek button per snapshot", () => {
    const p = props(chainBundle(), 28);
    render(<RecoveryChain {...p} />);
    const strip = screen.getByRole("group", { name: "Recovery chain in Sapphire Coast over snapshots" });
    // The fixture's history has gaps (13-15, 20-23, 26-29): a run never spans a missing snapshot.
    expect(within(strip).getByRole("img", { name: "Repair need (RS2): recorded, snapshots 13-14; stalled, snapshot 15; "
      + "recorded, snapshot 20; stalled, snapshots 21-23; recorded, snapshots 26-29" })).toBeInTheDocument();
    expect(within(strip).getByRole("img", { name: "Timber store to repair: recorded, snapshots 27-29" })).toBeInTheDocument();
    const rows = turnTable("Sapphire Coast").getAllByRole("row");
    expect(rows).toHaveLength(12);                                  // header and 11 snapshots
    const current = rows.find((r) => r.getAttribute("aria-current") === "true")!;
    expect(within(current).getByRole("button", { name: "Seek to snapshot 28" })).toBeInTheDocument();
    const r15 = rows.find((r) => within(r).queryByRole("button", { name: "Seek to snapshot 15" }))!;
    expect(r15).toHaveTextContent("#0 granary: stalled: no free timber");
    expect(r15).toHaveTextContent("2 coins (woodcutters of expedition #0 2)");
    expect(r15).toHaveTextContent("farm labour away: 4 farmer-turns (food sufficiency 0.934)");
    fireEvent.click(within(r15).getByRole("button", { name: "Seek to snapshot 15" }));
    expect(p.onSeek).toHaveBeenCalledWith(15);
  });

  it("hides snapshots where nothing in the chain was recorded unless every snapshot is asked for", () => {
    render(<RecoveryChain {...props(chainBundle(), 28)} />);
    fireEvent.change(screen.getByLabelText("Region"), { target: { value: "0" } });
    const listed = turnTable("Ashara Desert").getAllByRole("row").length - 1;
    expect(listed).toBeLessThan(11);
    expect(screen.getByText(new RegExp(`^${listed} of 11 snapshots are listed`))).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText("Show every snapshot"));
    expect(turnTable("Ashara Desert").getAllByRole("row")).toHaveLength(12);
    expect(screen.getByText("All 11 snapshots are listed.")).toBeInTheDocument();
  });
});

describe("off, unknown and zero in the view", () => {
  it("says off for a package switched off for the run, and leaves its column out of the turn table", () => {
    render(<RecoveryChain {...props(chainBundle(without("remittances")), 28)} />);
    expect(link("Sapphire Coast", 28, "Remittances in (RS4)")[0]).toBe("Off: Remittances (RS4) is off in this run (--remittances not recorded).");
    expect(screen.getByText(/^On in this run: /)).toHaveTextContent("Off: Remittances (RS4) (--remittances).");
    expect(turnTable("Sapphire Coast").queryByRole("columnheader", { name: "Remittances in (RS4)" })).toBeNull();
    expect(screen.getByText(/Links off in this run are left out: Remittances in \(RS4\)\./)).toBeInTheDocument();
  });

  it("says unknown, not zero, for a missing record or a null frame, and never totals it as zero", () => {
    const bundle = chainBundle((s) => {
      if (s.turn === 28) {
        delete s.livelihoods.remittances;
        Object.assign(s.livelihoods.recovery_crews, { receipts: null, ledger: null });
      }
    });
    render(<RecoveryChain {...props(bundle, 28)} />);
    expect(link("Sapphire Coast", 28, "Remittances in (RS4)")[0]).toBe("Unknown, not zero: no Remittances (RS4) record at this snapshot.");
    const [wages] = link("Sapphire Coast", 28, "Wages paid (PL3, RS2, PL1)");
    expect(wages).toMatch(/^PL3 granary crews: Unknown, not zero: no repair Phase 2 was settled/);
    expect(wages).toMatch(/The region's total is unknown: a source is not known\.$/);
    expect(wages).not.toMatch(/Total paid/);
    const r28 = turnTable("Sapphire Coast").getAllByRole("row").find((r) => r.getAttribute("aria-current") === "true")!;
    expect(r28).toHaveTextContent(/^28.*unknown \(PL3 granary crews: unknown\)/);
    expect(screen.getByText(/Totals count known snapshots only; unknown at: Wages paid \(PL3, RS2, PL1\) 1, Remittances in \(RS4\) 1\./)).toBeInTheDocument();
  });

  it("says nothing happened as nothing, not unknown", () => {
    render(<RecoveryChain {...props(chainBundle(), 13)} />);
    expect(link("Sapphire Coast", 13, "Food purchases (PL4)")[0]).toBe("Not a pilot region this turn (boundary paid work).");
    expect(link("Sapphire Coast", 13, "Remittances in (RS4)")[0]).toBe("Nothing came in this turn.");
    expect(link("Sapphire Coast", 13, "Forest stock (L3)")[0]).toBe("No expedition from the region was cutting.");
    expect(link("Sapphire Coast", 13, "Wages paid (PL3, RS2, PL1)")[0]).toMatch(/PL3 granary crews: none in the region\..*Total paid in the region: 0 coins\./);
  });

  it("says a refused record was rejected as malformed", () => {
    render(<RecoveryChain {...props(chainBundle((s) => { if (s.turn === 28) s.livelihoods.timber_supply.source_turn = 30; }), 28)} />);
    expect(link("Sapphire Coast", 28, "Woodcutting expedition (PL1)")[0])
      .toBe("Unknown, rejected as malformed: the Timber supply (PL1) record was rejected: misdated observation.");
    expect(link("Sapphire Coast", 28, "Timber store to repair")[0]).toMatch(/^Unknown, rejected as malformed/);
  });
});

describe("a run with only some of the switches (constructed from the natural records)", () => {
  it("repair projects and crews only: the timber, retail and remittance links say off", () => {
    render(<RecoveryChain {...props(chainBundle(without("timber_supply", "timber_stock", "household_retail", "remittances", "food_allocation")), 28)} />);
    expect(link("Sapphire Coast", 28, "Woodcutting expedition (PL1)")[0]).toBe("Off: Timber supply (PL1) is off in this run (--timber-supply not recorded).");
    expect(link("Sapphire Coast", 28, "Food purchases (PL4)")[0]).toMatch(/^Off: Household retail \(PL4\) is off/);
    expect(link("Sapphire Coast", 28, "Wages paid (PL3, RS2, PL1)")[0]).toMatch(/paid 8 coins\..*PL1 woodcutters: off\. Total paid in the region: 8 coins\./);
    const headers = turnTable("Sapphire Coast").getAllByRole("columnheader").map((h) => h.textContent);
    expect(headers).toEqual(["Snapshot", "Repair need (RS2)", "Granary condition", "Wages paid (PL3, RS2, PL1)", "Tradeoffs"]);
    expect(paragraph(/^Sapphire Coast over snapshots 13-29: repair projects stalled.*PL1 woodcutters off\)/)).toBeInTheDocument();
  });

  it("household retail alone: the view mounts with every repair link off", () => {
    render(<RecoveryChain {...props(chainBundle(without("repair_projects", "timber_supply", "timber_stock", "recovery_crews", "grain_storage", "remittances")), 22)} />);
    expect(link("Sapphire Coast", 22, "Repair need (RS2)")[0]).toMatch(/^Off: Repair projects \(RS2\) is off/);
    expect(link("Sapphire Coast", 22, "Granary condition")[0]).toMatch(/^Off: Granary storage is off/);
    expect(link("Sapphire Coast", 22, "Food purchases (PL4)")[0]).toMatch(/50 people .*None of the 24 people sampled here was paid earlier/);
    expect(screen.getByText(/no wages recorded \(every wage source is off\)/)).toBeInTheDocument();
  });
});

describe("mounting on the Livelihoods tab", () => {
  it("mounts once the run records a chain package, beside the package panels, and not otherwise", () => {
    const bundle = chainBundle();
    const { unmount } = render(<LivelihoodsPanel {...props(bundle, 28)} />);
    expect(screen.getByRole("heading", { name: "Recovery chain · snapshot 28" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Repair projects · snapshot 28" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Household retail · snapshot 28" })).toBeInTheDocument();
    unmount();
    const none = chainBundle(without("repair_projects", "timber_supply", "recovery_crews", "household_retail"));
    render(<LivelihoodsPanel {...props(none, 28)} />);
    expect(screen.queryByRole("heading", { name: /^Recovery chain/ })).toBeNull();
    expect(screen.getByRole("heading", { name: "Food allocation · snapshot 28" })).toBeInTheDocument();
  });

  it("follows the shell's selected region until a region is picked", () => {
    const { rerender } = render(<RecoveryChain {...props(chainBundle(), 28, { selectedRegion: "Iron Peaks" })} />);
    expect(screen.getByLabelText("Region")).toHaveValue("1");
    fireEvent.change(screen.getByLabelText("Region"), { target: { value: "7" } });
    rerender(<RecoveryChain {...props(chainBundle(), 28, { selectedRegion: "Iron Peaks" })} />);
    expect(screen.getByLabelText("Region")).toHaveValue("7");
  });
});
