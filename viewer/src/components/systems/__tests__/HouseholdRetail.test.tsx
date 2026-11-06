import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import type { Bundle } from "../../../types";
import { HouseholdRetail } from "../HouseholdRetail";
import { LivelihoodsPanel } from "../LivelihoodsPanel";
import {
  blanked, pilotClosed, record, refundAndOfferShort, regionCount, snapOf, type Run,
} from "../../../lib/__tests__/householdRetailFixture";
afterEach(cleanup);

const NAMES = ["Oldmere", "Ashford Vale", "Bram Fen", "Highwood", "Kestrel Moor", "Saltreach", "Thornby", "Wyrmgate"];
function props(x: unknown, regions = 8, turn?: number) {
  const names = Array.from({ length: regions }, (_, i) => ({ name: NAMES[i] ?? `Region ${i}` }));
  return { bundle: { world_state: { regions: names, civilizations: [] } } as unknown as Bundle,
    snapshot: snapOf(x, turn), currentTurn: turn ?? 1, onSelectRegion: vi.fn() };
}
const natural = (run: Run) => props(record(run), regionCount(run));
const table = (name: string) => within(screen.getByRole("table", { name }));
const rowOf = (name: string, label: string | RegExp) => table(name).getByRole("row", { name: typeof label === "string" ? new RegExp(`^${label}`) : label });
const note = (text: RegExp) => screen.getByText(text, { selector: "p" });

describe("household retail panel", () => {
  it("dates the turn, names the mode and boundary, and puts the people at risk first", () => {
    const p = natural("nr7");
    const { container } = render(<HouseholdRetail {...p} />);
    expect(screen.getByRole("heading", { name: "Household retail · snapshot 10" })).toBeInTheDocument();
    const notes = [...container.querySelectorAll("p.systems-note")].map((n) => n.textContent ?? "");
    expect(notes[0]).toMatch(/^Simulation turn 9\. No-relief control \(what relief protects\): the whole harvest is titled/);
    expect(notes[1]).toMatch(/^Mode: no_relief \(what relief protects\)\. Pilot boundary: market: each ruling civilization's capital region/);
    expect(notes[1]).toMatch(/θ = 1: 0% of each pilot harvest stays commons/);
    // Children first, then persons and households, each cause with its deficit.
    expect(notes[2]).toBe("141 people (34 children) were provisioned in 4 pilot regions. Below their fair share: priced out, "
      + "4 children among 16 people in 14 households (deficit 8.7 rations). Nobody was short of the offer or short of a claim "
      + "withheld for heirs.");
    const risk = "People below their fair share at snapshot 10";
    // Only the causes someone was short of get a column.
    expect(table(risk).getAllByRole("columnheader").map((h) => h.textContent)).toEqual(["Region (fair share)", "Priced out"]);
    expect(screen.getByRole("table", { name: risk }).querySelector("caption")?.textContent).toBe("Children · persons · households "
      + "below their fair share (deficit in rations), by cause: Priced out (cash ran out).");
    expect(rowOf(risk, "Saltreach")).toHaveTextContent(/^Saltreach \(1\)1 · 8 · 7 \(5\.404\)$/);
    expect(rowOf(risk, "Bram Fen")).toHaveTextContent("2 · 2 · 2 (0.343)");
    // Every risk row comes before the food and money tables in the section.
    const tables = [...container.querySelectorAll("table")].map((t) => t.getAttribute("aria-label"));
    expect(tables.slice(0, 2)).toEqual([risk, "Sampled people below their fair share at snapshot 10"]);
    expect(table("Sampled people below their fair share at snapshot 10").getAllByRole("row")).toHaveLength(17);
    fireEvent.click(within(rowOf(risk, "Saltreach")).getByRole("button", { name: "Saltreach" }));
    expect(p.onSelectRegion).toHaveBeenCalledWith("Saltreach");
  });

  it("shows own food, the title and its commons share, decay, overflow and inheritance", () => {
    render(<HouseholdRetail {...natural("t7")} />);
    const food = "Owned food at snapshot 81";
    // Oldmere: 13.464 carried in, most of it lost to the storage cap at opening; one claim inherited.
    expect(rowOf(food, "Oldmere")).toHaveTextContent("13.464 → 0.213 (1)1.574 (≈0.175)1.293 · 0.068 · 0.2133.89 of 4.1060.404 · 13.060 · 0none0.213");
    expect(rowOf(food, "Ashford Vale")).toHaveTextContent("21.98 (≈2.442)16.757 · 5.889 · 10.894");
    expect(note(/^141 people \(30 children\) were provisioned in 6 pilot regions\. Below their fair share: withheld for heirs, 0 children among 9 people/))
      .toBeInTheDocument();
    expect(rowOf("People below their fair share at snapshot 81", "Oldmere")).toHaveTextContent(/^Oldmere \(0\.382\)0 · 9 · 7 \(0\.26\)$/);
    expect(table("Sampled people below their fair share at snapshot 81").getAllByRole("row")[1])
      .toHaveTextContent("45 (45), Oldmerewithheld (dead owner's claim)0.368 of 0.382");
    expect(note(/117 more were not sampled\. The region counts above are complete\./)).toBeInTheDocument();
    expect(note(/^Records this turn: inherited 2\.$/)).toBeInTheDocument();
  });

  it("shows price, payments, income replaced and the merchant bound, labelled as a bound", () => {
    render(<HouseholdRetail {...natural("t7")} />);
    const money = "Food money at snapshot 81";
    expect(table(money).getAllByRole("columnheader").map((h) => h.textContent)).toEqual(["Region", "Price a ration",
      "Paid · credited · refunded", "Income replaced (farmers)", "Merchants: commons out · owned left (bound)"]);
    expect(rowOf(money, "Ashford Vale")).toHaveTextContent("Ashford Vale0.3614.258 · 4.258 · 04.105 (27 farmers)0 · at most 10.894");
    expect(rowOf(money, "Bram Fen")).toHaveTextContent("none (no farmer rows)");
    expect(note(/that owned food is an upper bound on the departures foregone, not a measured loss/)).toBeInTheDocument();
    const lifetime = "Household retail to snapshot 81";
    expect(rowOf(lifetime, "Paid · credited · refunded")).toHaveTextContent("1,083.841 · 1,083.841 · 0");
    expect(rowOf(lifetime, "Granary purchases")).toHaveTextContent("5 · 0 · 0");
    expect(rowOf(lifetime, "Farm income replaced")).toHaveTextContent("1,162.11 (6,451)");
  });

  it("shows refunds and offer shortfalls (constructed records that close)", () => {
    render(<HouseholdRetail {...props(refundAndOfferShort())} />);
    expect(rowOf("Food money at snapshot 81", "Kestrel Moor")).toHaveTextContent("1.603 · 1.5 · 0.103");
    const risk = "People below their fair share at snapshot 81";
    expect(table(risk).getAllByRole("columnheader").map((h) => h.textContent)).toEqual(["Region (fair share)", "Offer short", "Withheld for heirs"]);
    expect(rowOf(risk, "Wyrmgate")).toHaveTextContent(/^Wyrmgate \(1\)1 · 3 · 2 \(0\.4\)none$/);
    expect(rowOf(risk, "Oldmere")).toHaveTextContent(/^Oldmere \(0\.382\)none0 · 9 · 7 \(0\.26\)$/);
    expect(note(/offer short, 1 child among 3 people in 2 households \(deficit 0\.4 rations\); withheld for heirs/)).toBeInTheDocument();
  });

  it("shows a pilot closure and a conquest loss, dated, without inventing the closed region's provisioning", () => {
    render(<HouseholdRetail {...props(pilotClosed())} />);
    const food = "Owned food at snapshot 81";
    expect(rowOf(food, "Kestrel Moor")).toHaveTextContent("Kestrel Moor (left the pilot)0.5 → 0 (0)");
    expect(rowOf(food, "Kestrel Moor")).toHaveTextContent("not provisionednot provisioned");
    expect(rowOf(food, "Kestrel Moor")).toHaveTextContent("left the pilot 0.5");
    expect(rowOf("Food money at snapshot 81", "Kestrel Moor")).toHaveTextContent("not installednot provisionednot replaced (not provisioned)Unknown");
    expect(note(/^Not provisioned by retail this turn .*: Kestrel Moor\.$/)).toBeInTheDocument();
    expect(note(/turn 80 Kestrel Moor pilot closed 0\.5 \(no controller\)/)).toBeInTheDocument();
    cleanup();
    render(<HouseholdRetail {...natural("p13")} />);
    expect(rowOf("Owned food at snapshot 6", "Region 21")).toHaveTextContent("0 · 64.64no heir 5.594");
    expect(rowOf("Owned food at snapshot 6", "Region 24")).toHaveTextContent("Region 24 (joined this turn)0 → 6.147 (24)");
    expect(note(/^Records this turn: pilot opened 1, war loss 1, escheat 4\.$/)).toBeInTheDocument();
  });

  it("labels the controls plainly: free exchange charges nothing, record-only applies nothing", () => {
    render(<HouseholdRetail {...natural("fx7")} />);
    expect(note(/^Simulation turn 31\. Free-exchange control \(ownership without cash\)/)).toBeInTheDocument();
    expect(note(/^Mode: free_exchange \(ownership without cash\)\./)).toBeInTheDocument();
    expect(rowOf("Food money at snapshot 32", "Oldmere")).toHaveTextContent("not charged0 · 0 · 0kept (not replaced)");
    expect(note(/^Granaries bought 5\.586 of owners' grain in 1 purchases; in this control nobody was paid \(1 stays/)).toBeInTheDocument();
    expect(note(/Everyone reached their fair share\.$/)).toBeInTheDocument();
    expect(screen.queryByRole("table", { name: /People below their fair share/ })).toBeNull();
    cleanup();
    render(<HouseholdRetail {...natural("ro7")} />);
    expect(note(/^Simulation turn 59\. Record-only control \(identity control, nothing applied\)/)).toBeInTheDocument();
    expect(note(/^Mode: record_only \(identity control, nothing applied\)\./)).toBeInTheDocument();
    expect(rowOf("Would-be retail at snapshot 60", "Ashford Vale")).toHaveTextContent("Ashford Vale14.00730 of 3000.8030");
    expect(screen.queryByRole("table", { name: /Owned food at/ })).toBeNull();
    expect(screen.queryByRole("table", { name: /Food money at/ })).toBeNull();
    cleanup();
    render(<HouseholdRetail {...natural("pw7")} />);
    expect(note(/Pilot boundary: paid_work: regions where paid work has been done \(an open workshop firm, a paid repair or granary crew/))
      .toBeInTheDocument();
    cleanup();
    render(<HouseholdRetail {...natural("all11")} />);
    expect(note(/Pilot boundary: all: every controlled region/)).toBeInTheDocument();
    expect(rowOf("People below their fair share at snapshot 9", "Highwood")).toHaveTextContent("5 · 19 · 14 (11.145)");
  });

  it("keeps an unrecorded frame unknown, says when no region is in the pilot, and refuses malformed records", () => {
    const { container } = render(<HouseholdRetail {...props(blanked("t7"))} />);
    expect(screen.getByRole("heading", { name: "Household retail · snapshot 81" })).toBeInTheDocument();
    expect(note(/^The retail frame of simulation turn 80 was not recorded: .* unknown, not zero\.$/)).toBeInTheDocument();
    const tables = [...container.querySelectorAll("table")].map((t) => t.getAttribute("aria-label"));
    expect(tables).toEqual(["Household retail to snapshot 81"]);                // lifetime only, no this-turn table
    expect(container.textContent).not.toMatch(/Everyone reached|were provisioned/);
    cleanup();
    render(<HouseholdRetail {...natural("pw7early")} />);
    expect(note(/^No region is in the pilot at simulation turn 9\.$/)).toBeInTheDocument();
    cleanup();
    const bad = record("t7");
    bad.regions[1].flows.sold += 1;
    const view = render(<HouseholdRetail {...props(bad)} />);
    expect(screen.getByRole("heading", { name: "Household retail" })).toBeInTheDocument();
    expect(note(/^The household retail record at snapshot 81 was rejected as malformed: the owned food does not close/)).toBeInTheDocument();
    expect(view.container.querySelectorAll("table")).toHaveLength(0);
    cleanup();
    render(<HouseholdRetail {...props(record("t7"), 8, 80)} />);
    expect(note(/rejected as malformed: misdated observation\.$/)).toBeInTheDocument();
    cleanup();
    render(<HouseholdRetail {...props(null)} />);
    expect(note(/^Household retail is not observed at snapshot 1\.$/)).toBeInTheDocument();
  });

  it("is mounted on the Livelihoods tab beside food allocation, only when recorded", () => {
    const p = props(record("t7"));
    const panel = (snapshot: unknown) => <LivelihoodsPanel {...p} snapshot={snapshot as never} onSeek={vi.fn()}
      onSelectEvent={vi.fn()} onSelectCivilization={vi.fn()} />;
    render(panel(p.snapshot));
    expect(screen.getByRole("heading", { name: "Household retail · snapshot 81" })).toBeInTheDocument();
    expect(screen.queryByText(/names no package this viewer reads/)).toBeNull();
    cleanup();
    render(panel({ turn: 81, livelihoods: { schema_version: 1, food_allocation: null } }));
    expect(screen.queryByRole("heading", { name: /Household retail/ })).toBeNull();
    expect(screen.getByText(/names no package this viewer reads/)).toBeInTheDocument();
  });
});
