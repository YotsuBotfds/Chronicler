import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import systemsFixture from "../../../__fixtures__/systems_bundle.json";
import sampleFixture from "../../../__fixtures__/sample_bundle.json";
import citiesFixture from "../../../__fixtures__/cities_bundle.json";
import movementsFixture from "../../../__fixtures__/movements_bundle.json";
import learningFixture from "../../../__fixtures__/learning_bundle.json";
import faithsFixture from "../../../__fixtures__/faiths_bundle.json";
import faithsLegacyFixture from "../../../__fixtures__/faiths_legacy_bundle.json";
import debtFixture from "../../../__fixtures__/debt_holders_bundle.json";
import type { Bundle, TurnSnapshot } from "../../../types";
import type { SystemPanelProps } from "../../../lib/systems";
import { AgendasPanel } from "../AgendasPanel";
import { CitiesPanel } from "../CitiesPanel";
import { ContactPanel } from "../ContactPanel";
import { DiplomacyPanel } from "../DiplomacyPanel";
import { EpidemicsPanel } from "../EpidemicsPanel";
import { FaithsPanel } from "../FaithsPanel";
import { FinancePanel } from "../FinancePanel";
import { FoodPanel } from "../FoodPanel";
import { GovernancePanel } from "../GovernancePanel";
import { LearningPanel } from "../LearningPanel";
import { MaritimePanel } from "../MaritimePanel";
import { MovementsPanel } from "../MovementsPanel";
import { NomadsPanel } from "../NomadsPanel";
import { RegionSystemsDetail } from "../RegionSystemsDetail";
import { SystemsPanel } from "../SystemsPanel";
import { WarsPanel } from "../WarsPanel";
import { crisesAtSnapshot, famineSpans, foodCrisisSpans } from "../../../lib/food";
import { cityRecord, cityRecordAt } from "../../../lib/cities";
import { movementRecord } from "../../../lib/movements";
import { TechniquesPanel } from "../TechniquesPanel";

afterEach(cleanup);

/** The real-shaped fixture: a trimmed procedural 48-region run with every system on. */
const fixture = systemsFixture as unknown as Bundle;
const sample = sampleFixture as unknown as Bundle;
const LAST = fixture.history[fixture.history.length - 1];

function props(bundle: Bundle = fixture, snapshot: TurnSnapshot | null = LAST): SystemPanelProps {
  return {
    bundle,
    snapshot,
    currentTurn: snapshot?.turn ?? 1,
    onSeek: vi.fn(),
    onSelectEvent: vi.fn(),
    onSelectRegion: vi.fn(),
    onSelectCivilization: vi.fn(),
  };
}

function without(bundle: Bundle, ...keys: Array<keyof TurnSnapshot>): Bundle {
  return {
    ...bundle,
    history: bundle.history.map((snapshot) => {
      const copy: TurnSnapshot = { ...snapshot };
      for (const key of keys) {
        delete copy[key];
      }
      return copy;
    }),
  };
}

function at(turn: number): TurnSnapshot {
  const snapshot = fixture.history.find((entry) => entry.turn === turn);
  if (!snapshot) {
    throw new Error(`fixture has no turn ${turn}`);
  }
  return snapshot;
}

describe("EpidemicsPanel", () => {
  it("renders outbreaks by region and pathogen, the scrubbed turn's table and quarantines", () => {
    const p = props();
    render(<EpidemicsPanel {...p} />);
    const strip = screen.getByRole("group", { name: "Outbreaks by region and pathogen over time" });
    expect(within(strip).getByText("Bredoham Wetlands · Marsh fever")).toBeInTheDocument();
    const table = screen.getByRole("table", { name: "Outbreaks at turn 120" });
    expect(within(table).getAllByRole("row")).toHaveLength(1 + LAST.epidemics!.active.length);
    expect(within(table).getByText("Marsh fever")).toBeInTheDocument();
    expect(within(screen.getByLabelText("Quarantines at turn 120")).getByText("Glewahami Confederacy")).toBeInTheDocument();
    fireEvent.click(within(table).getByRole("button", { name: "Dililene Coast" }));
    expect(p.onSelectRegion).toHaveBeenCalledWith("Dililene Coast");
    const events = screen.getByRole("list", { name: "Epidemic events" });
    fireEvent.click(within(events).getAllByRole("listitem")[0]);
    expect(p.onSelectEvent).toHaveBeenCalledTimes(1);
  });

  it("says so when the scrubbed snapshot has no outbreak", () => {
    render(<EpidemicsPanel {...props(fixture, at(1))} />);
    expect(screen.getByText("No reportable outbreak at turn 1.")).toBeInTheDocument();
  });
});

describe("FinancePanel", () => {
  it("renders the per-civ ledger at the scrubbed turn and filters loans, defaults and debasements", () => {
    const p = props();
    render(<FinancePanel {...p} />);
    const table = screen.getByRole("table", { name: "Public finance at turn 120" });
    expect(within(table).getAllByRole("row")).toHaveLength(1 + Object.keys(LAST.finance!.civs).length);
    expect(screen.getByLabelText("Debt, in turns of smoothed revenue")).toBeInTheDocument();
    expect(screen.getByLabelText("Price index (1.0 at the start)")).toBeInTheDocument();
    const list = () => screen.getByRole("list", { name: "Finance events" });
    const all = within(list()).getAllByRole("listitem").length;
    fireEvent.click(screen.getByRole("button", { name: "Defaults" }));
    const defaults = within(list()).getAllByRole("listitem");
    expect(defaults.length).toBeLessThan(all);
    for (const row of defaults) {
      expect(row).toHaveTextContent(/state default|debt written off/);
    }
    fireEvent.click(screen.getByRole("button", { name: "Debasements" }));
    expect(within(list()).getAllByRole("listitem")[0]).toHaveTextContent("debasement");
  });

  it("shows a finance-only run's debt as the abstract domestic class and one foreign total", () => {
    render(<FinancePanel {...props()} />);
    expect(screen.getByText(/This snapshot records finance totals only/)).toBeInTheDocument();
    const bars = screen.getByRole("list", { name: "Debt by holder at turn 120" });
    const owing = Object.entries(LAST.finance!.civs).filter(([, row]) => row.debt > 0);
    expect(within(bars).getAllByRole("listitem")).toHaveLength(owing.length);
    const [civ, row] = owing[0];
    fireEvent.click(within(bars).getByRole("button", { name: new RegExp(civ) }));
    const table = screen.getByRole("table", { name: `Holders of the debt of ${civ} at turn 120` });
    expect(within(table).queryByRole("columnheader", { name: "Rate" })).toBeNull();
    const domestic = within(table).getByRole("rowheader", { name: /Domestic creditors/ }).closest("tr")!;
    expect(domestic).toHaveTextContent(String(row.debt - row.foreign_debt));
    expect(screen.queryByLabelText(`Foreign debt of ${civ} by lender`)).toBeNull();
  });
});

describe("FinancePanel debt holders (--domestic-credit)", () => {
  /** Trimmed from a real --domestic-credit run: procedural 32 x 10, seed 42, 120 hybrid turns. */
  const debt = debtFixture as unknown as Bundle;
  const turn54 = debt.history.find((entry) => entry.turn === 54)!;

  it("names who holds a realm's debt at the scrubbed turn and opens lenders and regions", () => {
    const p = props(debt, turn54);
    render(<FinancePanel {...p} />);
    const bars = screen.getByRole("list", { name: "Debt by holder at turn 54" });
    const owing = Object.values(turn54.finance!.civs).filter((row) => row.debt > 0);
    expect(within(bars).getAllByRole("listitem")).toHaveLength(owing.length);
    expect(within(bars).getByRole("img", { name: /^Khidutain Clans owes 231: merchants 21 .*foreign lenders 180/ }))
      .toBeInTheDocument();
    fireEvent.click(within(bars).getByRole("button", { name: /Khidutain Clans/ }));
    const section = screen.getByRole("region", { name: "Creditors of Khidutain Clans" });
    const table = within(section).getByRole("table", { name: "Holders of the debt of Khidutain Clans at turn 54" });
    expect(within(table).getByRole("columnheader", { name: "Interest" })).toBeInTheDocument();
    const sylenen = within(table).getByRole("button", { name: "Sylenen Kingdom" }).closest("tr")!;
    expect(sylenen).toHaveTextContent("133");
    expect(sylenen).toHaveTextContent("8.4%");
    expect(sylenen).toHaveTextContent((133 * 0.0841).toFixed(1));
    fireEvent.click(within(table).getByRole("button", { name: "Sylenen Kingdom" }));
    expect(p.onSelectCivilization).toHaveBeenCalledWith("Sylenen Kingdom");
    fireEvent.click(within(table).getByRole("button", { name: "Suqikan Expanse" }));
    expect(p.onSelectRegion).toHaveBeenCalledWith("Suqikan Expanse");
    expect(within(table).getByText("Brohamoor Bog Settlement 1")).toBeInTheDocument();
    expect(within(table).getByText("the Merchant Guild of Brohamoor Bog Settlement 1")).toBeInTheDocument();
    expect(within(section).getByText("Interest due")).toBeInTheDocument();
    expect(within(section).getByLabelText("Debt of Khidutain Clans by holder")).toBeInTheDocument();
    expect(within(section).getByLabelText("Foreign debt of Khidutain Clans by lender")).toBeInTheDocument();
    expect(within(section).getByRole("group", { name: "Arrears, defaults and write-offs of Khidutain Clans over time" }))
      .toBeInTheDocument();
  });

  it.each(["kinds", "totals"] as const)("uses the scrubbed snapshot's %s detail in a mixed-version history", (level) => {
    const older: TurnSnapshot = {
      ...turn54,
      finance: { ...turn54.finance!, domestic_credit: { ...turn54.finance!.domestic_credit! } },
    };
    if (level === "kinds") {
      delete older.finance!.domestic_credit!.holders;
    } else {
      delete older.finance!.domestic_credit;
    }
    const mixed: Bundle = {
      ...debt,
      history: debt.history.map((snapshot) => snapshot.turn === older.turn ? older : snapshot),
    };
    const p = { ...props(mixed, older), selectedCivilization: "Khidutain Clans" };
    const shown = render(<FinancePanel {...p} />);
    const section = screen.getByRole("region", { name: "Creditors of Khidutain Clans" });
    const table = within(section).getByRole("table", { name: "Holders of the debt of Khidutain Clans at turn 54" });
    expect(older.finance!.civs["Khidutain Clans"].foreign_debt).toBeGreaterThan(0);
    expect(within(section).getByText("one total")).toBeInTheDocument();
    expect(within(section).getByText("This snapshot does not name individual lenders.")).toBeInTheDocument();
    expect(within(section).queryByText("no foreign lender")).toBeNull();
    expect(within(table).queryByRole("columnheader", { name: "Rate" })).toBeNull();
    expect(within(table).queryByRole("columnheader", { name: "Interest" })).toBeNull();
    expect(within(section).queryAllByText("Written off").some((label) => label.closest(".systems-tile"))).toBe(false);
    expect(screen.getByText(level === "kinds"
      ? /This snapshot records domestic claims by kind of lender only/
      : /This snapshot records finance totals only/)).toBeInTheDocument();
    // Later observations still belong on the timeline; they do not supply
    // lender detail to an earlier snapshot.
    expect(within(section).getByLabelText("Foreign debt of Khidutain Clans by lender")).toBeInTheDocument();

    const newer = debt.history.find((snapshot) => snapshot.turn === 55)!;
    shown.rerender(<FinancePanel {...p} snapshot={newer} currentTurn={newer.turn} />);
    const newerSection = screen.getByRole("region", { name: "Creditors of Khidutain Clans" });
    const newerTable = within(newerSection).getByRole("table", { name: "Holders of the debt of Khidutain Clans at turn 55" });
    expect(within(newerTable).getByRole("columnheader", { name: "Rate" })).toBeInTheDocument();
    expect(within(newerSection).getByText(/lending civilization/)).toBeInTheDocument();
    expect(within(newerSection).getAllByText("Written off").some((label) => label.closest(".systems-tile"))).toBe(true);
  });

  it("shows a fallen borrower's write-off event with an unknown amount", () => {
    const next = debt.history.find((snapshot) => snapshot.turn === 55)!;
    const finance = { ...next.finance!, civs: { ...next.finance!.civs } };
    delete finance.civs["Khidutain Clans"];
    const fallen = { ...next, finance };
    const event = {
      turn: 54, event_type: "debt_written_off", actors: ["Khidutain Clans", "Sylenen Kingdom"],
      description: "With Khidutain Clans gone, its debt to Sylenen Kingdom is lost.",
      consequences: [], importance: 3, event_id: "synthetic:fallen-borrower",
    };
    const projected: Bundle = { ...debt, history: [turn54, fallen], events_timeline: [event] };
    const p = { ...props(projected, fallen), selectedCivilization: "Khidutain Clans" };
    render(<FinancePanel {...p} />);
    const section = screen.getByRole("region", { name: "Creditors of Khidutain Clans" });
    expect(within(section).getByText("Khidutain Clans has no holder record at turn 55.")).toBeInTheDocument();
    expect(within(section).queryByText("Khidutain Clans owes nothing at turn 55.")).toBeNull();
    const losses = within(section).getByRole("table", { name: "Defaults and write-offs of Khidutain Clans" });
    const row = within(losses).getAllByRole("row")[1];
    expect(within(row).getAllByRole("cell").map((cell) => cell.textContent)).toEqual(["54", "-", event.description]);
    expect(within(section).getByTitle("Khidutain Clans: write-off event recorded by turn 55 (amount not recorded)"))
      .toBeInTheDocument();
    fireEvent.click(within(row).getByRole("button", { name: event.description }));
    expect(p.onSelectEvent).toHaveBeenCalledWith(event);
  });

  it("lists a borrower's defaults and write-offs with their events, and follows the shell's selection", () => {
    const last = debt.history[debt.history.length - 1];
    const p = { ...props(debt, last), selectedCivilization: "Khidutain Clans" };
    render(<FinancePanel {...p} />);
    const losses = screen.getByRole("table", { name: "Defaults and write-offs of Khidutain Clans" });
    const rows = within(losses).getAllByRole("row").slice(1);
    // Listed at the turn of their events (the snapshot after records them).
    expect(rows.map((row) => within(row).getAllByRole("cell")[0].textContent)).toEqual(["64", "54"]);
    expect(rows[0]).toHaveTextContent("131");
    fireEvent.click(within(rows[1]).getByRole("button", { name: /defaults on its debts, repudiating 124/ }));
    expect(p.onSelectEvent).toHaveBeenCalledWith(expect.objectContaining({ event_type: "state_default", turn: 54 }));
    const credit = screen.getByRole("list", { name: "Credit events of Khidutain Clans" });
    expect(within(credit).getAllByRole("listitem").length).toBeGreaterThan(2);
    fireEvent.change(screen.getByRole("combobox", { name: "Borrower" }), { target: { value: "Saqeduni Empire" } });
    expect(screen.getByRole("region", { name: "Creditors of Saqeduni Empire" })).toBeInTheDocument();
  });
});

describe("DiplomacyPanel", () => {
  it("renders active treaties, the vassal ladder and the trust and grievance matrices", () => {
    const p = props();
    render(<DiplomacyPanel {...p} />);
    const treaties = screen.getByRole("table", { name: "Active treaties at turn 120" });
    expect(within(treaties).getAllByRole("row")).toHaveLength(1 + LAST.diplomacy!.treaties.length);
    const ladder = screen.getByRole("group", { name: "Overlord and subject stages over time" });
    expect(within(ladder).getByText("Doguri Republic → League of Fewen")).toBeInTheDocument();
    const trust = screen.getByRole("table", { name: /^Trust of each row civilization/ });
    const [holder, row] = Object.entries(LAST.diplomacy!.pairs!)[0];
    const [target, [value]] = Object.entries(row)[0];
    expect(within(trust).getByTitle(new RegExp(`^${holder} toward ${target}: trust ${value.toFixed(1)}`))).toBeInTheDocument();
    expect(screen.getByRole("table", { name: /^Total grievance of each row civilization/ })).toBeInTheDocument();
    expect(screen.queryByText(/exports only the five largest grievances/)).not.toBeInTheDocument();
  });

  it("shows the subject and its ladder stage at a turn that has one", () => {
    render(<DiplomacyPanel {...props(fixture, at(91))} />);
    const subjects = screen.getByRole("table", { name: "Subjects at turn 91" });
    expect(within(subjects).getByText("vassal")).toBeInTheDocument();
    expect(within(subjects).getByText("Hiholdi Kingdom")).toBeInTheDocument();
  });

  it("falls back to the five largest grievances on bundles without the pair matrix", () => {
    const older = { ...LAST, diplomacy: { ...LAST.diplomacy!, pairs: undefined } };
    render(<DiplomacyPanel {...props(fixture, older)} />);
    expect(screen.getByText(/exports only the five largest grievances/)).toBeInTheDocument();
  });
});

describe("TechniquesPanel", () => {
  it("renders known techniques, the era timeline, regional practice and diffusion events", () => {
    const p = props();
    render(<TechniquesPanel {...p} />);
    expect(screen.getByLabelText("Techniques known (of 30)")).toBeInTheDocument();
    const eras = screen.getByRole("group", { name: "Era of each civilization over time" });
    expect(within(eras).getAllByText("Thyrodori Confederacy").length).toBeGreaterThan(0);
    const table = screen.getByRole("table", { name: "Techniques per civilization at turn 120" });
    expect(within(table).getAllByRole("row")).toHaveLength(1 + Object.keys(LAST.techniques!.known).length);
    expect(screen.getByRole("table", { name: "Regional practice at turn 120" })).toBeInTheDocument();
    expect(within(screen.getByRole("list", { name: "Technique events" })).getAllByRole("listitem").length).toBeGreaterThan(0);
  });

  it("says when a bundle does not export regional practice", () => {
    const older = { ...LAST, techniques: { ...LAST.techniques!, regions: undefined } };
    render(<TechniquesPanel {...props(fixture, older)} />);
    expect(screen.getByText("Regional practice is not exported in this bundle.")).toBeInTheDocument();
  });
});

describe("MaritimePanel", () => {
  it("renders sea-zone control, zones with their ports, fleets and blockades", () => {
    const blockaded = at(101);
    const p = props(fixture, blockaded);
    render(<MaritimePanel {...p} />);
    expect(screen.getAllByRole("img", { name: /^the Morendor Bight: / }).length).toBe(1);
    const zones = screen.getByRole("table", { name: "Sea zones at turn 101" });
    expect(within(zones).getAllByRole("row")).toHaveLength(1 + blockaded.maritime!.zones.length);
    const fleets = screen.getByRole("table", { name: "Fleets at turn 101" });
    expect(within(fleets).getAllByRole("row")).toHaveLength(1 + blockaded.maritime!.fleets.length);
    const blockades = screen.getByRole("table", { name: "Blockades at turn 101" });
    expect(within(blockades).getAllByRole("row")).toHaveLength(1 + blockaded.maritime!.blockades.length);
    const port = fixture.world_state.regions[fixture.world_state.maritime!.zones![0].ports![0]].name;
    fireEvent.click(within(zones).getAllByRole("button", { name: port })[0]);
    expect(p.onSelectRegion).toHaveBeenCalledWith(port);
  });

  it("explains an idle layer on a world without sea zones", () => {
    const sealess = {
      ...fixture,
      history: fixture.history.map((snapshot) => ({
        ...snapshot,
        maritime: { ...snapshot.maritime!, zones: [], fleets: [], blockades: [] },
      })),
    };
    render(<MaritimePanel {...props(sealess, sealess.history[sealess.history.length - 1])} />);
    expect(screen.getByText(/this world has no sea zones/)).toBeInTheDocument();
  });
});

describe("WarsPanel", () => {
  it("renders wars over time, the scrubbed turn's wars and armies, and the battles so far", () => {
    const snapshot = at(101);
    const p = props(fixture, snapshot);
    render(<WarsPanel {...p} />);
    expect(within(screen.getByRole("group", { name: "Wars over time" })).getAllByRole("img").length).toBeGreaterThan(0);
    const wars = screen.getByRole("table", { name: "Wars at turn 101" });
    expect(within(wars).getAllByRole("row")).toHaveLength(1 + snapshot.campaign!.wars.length);
    const armies = screen.getByRole("table", { name: "Armies at turn 101" });
    expect(within(armies).getAllByRole("row")).toHaveLength(1 + snapshot.campaign!.armies.length);
    const army = snapshot.campaign!.armies[0];
    fireEvent.click(within(armies).getAllByRole("button", { name: army.region })[0]);
    expect(p.onSelectRegion).toHaveBeenCalledWith(army.region);
    expect(screen.getByRole("table", { name: "Battles up to turn 101" })).toBeInTheDocument();
    expect(within(screen.getByRole("list", { name: "War events" })).getAllByRole("listitem").length).toBeGreaterThan(0);
  });

  it("lists occupations at a turn that has one", () => {
    render(<WarsPanel {...props(fixture, at(11))} />);
    expect(screen.getByRole("table", { name: "Occupations at turn 11" })).toBeInTheDocument();
  });
});

describe("FoodPanel", () => {
  it("renders famines by region, hungry regions with food over need, and relief", () => {
    const snapshot = fixture.history.find((entry) => (entry.food?.aid.length ?? 0) > 0)!;
    const p = props(fixture, snapshot);
    render(<FoodPanel {...p} />);
    expect(screen.getByLabelText("Regions short of food, in dearth and in famine")).toBeInTheDocument();
    const strip = screen.getByRole("group", { name: "Famines by region over time" });
    expect(within(strip).getByText("Bredoham Wetlands")).toBeInTheDocument();
    const hungry = screen.getByRole("table", { name: `Hungry regions at turn ${snapshot.turn}` });
    expect(within(hungry).getByText("Food ÷ need")).toBeInTheDocument();
    expect(within(screen.getByLabelText(`Relief convoys at turn ${snapshot.turn}`)).getAllByText(/→/).length)
      .toBe(snapshot.food!.aid.length);
    fireEvent.click(within(strip).getByRole("button", { name: "Bredoham Wetlands" }));
    expect(p.onSelectRegion).toHaveBeenCalledWith("Bredoham Wetlands");
  });

  it("separates dearth from famine when the bundle labels its reports", () => {
    // Relabel every onset a dearth: its episode is a dearth until a later report says famine.
    const labelled = {
      ...fixture,
      events_timeline: fixture.events_timeline.map((event) => (
        event.event_type === "famine" && event.episode === "onset" ? { ...event, event_type: "dearth" } : event)),
    };
    const spans = foodCrisisSpans(labelled.events_timeline);
    const snapshot = labelled.history.find((entry) => crisesAtSnapshot(spans, entry.turn)
      .some((span) => span.kind === "dearth"))!;
    render(<FoodPanel {...props(labelled, snapshot)} />);
    expect(screen.getByText("Regions in dearth")).toBeInTheDocument();
    const hungry = screen.getByRole("table", { name: `Hungry regions at turn ${snapshot.turn}` });
    expect(within(hungry).getAllByText(/^Dearth since T/).length).toBeGreaterThan(0);
    expect(screen.getAllByText("dearth").length).toBeGreaterThan(0);
  });

  it("lists hungry regions by their food, shortest first, and regions not observed last", () => {
    const snapshot = fixture.history.find((entry) => (entry.food?.sufficiency ?? []).filter((v) => v != null && v < 1).length >= 2)!;
    const names = fixture.world_state.regions.map((region) => region.name);
    const short = names.filter((_, index) => (snapshot.food!.sufficiency[index] ?? 2) < 1);
    const unobserved = names.find((_, index) => snapshot.food!.sufficiency[index] == null)!;
    const dearth = { turn: snapshot.turn - 1, event_type: "dearth", region: unobserved, episode: "onset" as const,
      actors: [], description: "", consequences: [], importance: 4 };
    const bundle = { ...fixture, events_timeline: [...fixture.events_timeline, dearth] };
    render(<FoodPanel {...props(bundle, snapshot)} />);
    const table = screen.getByRole("table", { name: `Hungry regions at turn ${snapshot.turn}` });
    const rows = within(table).getAllByRole("row").slice(1).map((row) => row.textContent ?? "");
    expect(rows[0]).not.toContain("Not observed");
    expect(rows.findIndex((row) => row.startsWith(unobserved))).toBeGreaterThan(
      Math.max(...short.slice(0, 2).map((name) => rows.findIndex((row) => row.startsWith(name)))));
  });

  it("counts famines only when the bundle has no food field", () => {
    const older = without(fixture, "food");
    render(<FoodPanel {...props(older, older.history[older.history.length - 1])} />);
    expect(screen.getByText(/does not export regional food sufficiency/)).toBeInTheDocument();
    expect(screen.queryByText("Food ÷ need")).not.toBeInTheDocument();
  });
});

describe("NomadsPanel", () => {
  it("renders ways of life, herds and the nomad counters", () => {
    const p = props();
    render(<NomadsPanel {...p} />);
    const strip = screen.getByRole("group", { name: "Subsistence mode of each civilization over time" });
    expect(within(strip).getByText("Hiholdi Kingdom")).toBeInTheDocument();
    expect(screen.getByLabelText("Herd head on each civilization's land")).toBeInTheDocument();
    expect(within(screen.getByLabelText("Nomad totals by turn 120")).getByText("Raids")).toBeInTheDocument();
    fireEvent.click(within(strip).getByRole("button", { name: "Hiholdi Kingdom" }));
    expect(p.onSelectCivilization).toHaveBeenCalledWith("Hiholdi Kingdom");
  });
});

describe("AgendasPanel", () => {
  it("phrases open vows with their targets resolved and lists agenda events", () => {
    const p = props();
    render(<AgendasPanel {...p} />);
    const table = screen.getByRole("table", { name: "Open agendas at turn 120" });
    expect(within(table).getAllByRole("row")).toHaveLength(1 + LAST.gp_agendas!.open.length);
    expect(within(table).getByText("discover bronze working")).toBeInTheDocument();
    const civ = fixture.world_state.civilizations[2].name;
    expect(within(table).getByText(`keep the trade road to ${civ} open`)).toBeInTheDocument();
    expect(screen.getByLabelText("Agendas so far (running totals)")).toBeInTheDocument();
    expect(within(screen.getByRole("list", { name: "Agenda events" })).getAllByRole("listitem").length).toBeGreaterThan(0);
  });
});

describe("GovernancePanel", () => {
  it("renders forms of government, political stress and each realm at the turn", () => {
    const p = props();
    render(<GovernancePanel {...p} />);
    const strip = screen.getByRole("group", { name: "Form of government of each civilization over time" });
    expect(within(strip).getAllByRole("img").length).toBeGreaterThan(0);
    expect(screen.getByLabelText("Political stress index (higher is closer to unrest)")).toBeInTheDocument();
    const table = screen.getByRole("table", { name: "Governance at turn 120" });
    const living = Object.values(LAST.civ_stats).filter((row) => row.governance && row.alive !== false).length;
    expect(within(table).getAllByRole("row")).toHaveLength(1 + living);
    expect(within(table).getByText("merchant republic")).toBeInTheDocument();
  });
});

describe("ContactPanel", () => {
  it("renders contact over time and the largest trade partnerships with their dependence", () => {
    render(<ContactPanel {...props()} />);
    const table = screen.getByRole("table", { name: "Trade partnerships at turn 120" });
    expect(within(table).getAllByRole("row")).toHaveLength(1 + LAST.contact!.top_trade_pairs.length);
    const top = LAST.contact!.top_trade_pairs[0];
    expect(within(table).getAllByText(`${(top.dependence_ab * 100).toFixed(0)}%`).length).toBeGreaterThan(0);
    expect(screen.getByLabelText("Pairs of living civilizations in contact, and trading")).toBeInTheDocument();
  });
});

describe("SystemsPanel", () => {
  it("offers one tab per recorded system and switches between them", () => {
    render(<SystemsPanel {...props()} surface="overview" />);
    const tabs = screen.getAllByRole("tab").map((tab) => tab.textContent);
    expect(tabs).toEqual([
      "Epidemics", "Food", "Wars", "Finance", "Diplomacy", "Techniques", "Maritime", "Nomads", "Agendas",
      "Governance", "Contact",
    ]);
    expect(screen.getByRole("tab", { name: "Epidemics" })).toHaveAttribute("aria-selected", "true");
    fireEvent.click(screen.getByRole("tab", { name: "Maritime" }));
    expect(screen.getByRole("table", { name: "Sea zones at turn 120" })).toBeInTheDocument();
  });

  it("opens on the system that fits the surface", () => {
    render(<SystemsPanel {...props()} surface="trade" />);
    expect(screen.getByRole("tab", { name: "Finance" })).toHaveAttribute("aria-selected", "true");
  });

  it("renders nothing for a bundle without any system", () => {
    const { container } = render(<SystemsPanel {...props(sample, sample.history[0])} surface="overview" />);
    expect(container).toBeEmptyDOMElement();
  });

  it("drops the tab of a system the bundle does not carry", () => {
    const partial = without(fixture, "finance", "maritime", "contact", "campaign", "nomads", "gp_agendas", "food");
    render(<SystemsPanel {...props(partial, partial.history[partial.history.length - 1])} surface="trade" />);
    // Food stays: the timeline still records famines by region.
    expect(screen.getAllByRole("tab").map((tab) => tab.textContent))
      .toEqual(["Epidemics", "Food", "Diplomacy", "Techniques", "Governance"]);
    expect(screen.getByRole("tab", { name: "Epidemics" })).toHaveAttribute("aria-selected", "true");
  });

  it("opens the war tab on the campaign surface", () => {
    render(<SystemsPanel {...props()} surface="campaign" />);
    expect(screen.getByRole("tab", { name: "Wars" })).toHaveAttribute("aria-selected", "true");
  });
});

/**
 * A trimmed template run with --cities (seed 70, 250 hybrid turns): every
 * snapshot's `cities` field, the city events and `world_state.cities`.
 */
const cities = citiesFixture as unknown as Bundle;
const CITIES_LAST = cities.history[cities.history.length - 1];

function citiesAt(turn: number): TurnSnapshot {
  const snapshot = cities.history.find((entry) => entry.turn === turn);
  if (!snapshot) {
    throw new Error(`cities fixture has no turn ${turn}`);
  }
  return snapshot;
}

describe("CitiesPanel", () => {
  it("renders the cities over time, the scrubbed turn's table and the first city's history", () => {
    const p = props(cities, CITIES_LAST);
    render(<CitiesPanel {...p} />);
    const strip = screen.getByRole("group", { name: "Rank of each city over time" });
    expect(within(strip).getByText("Verdant Plains Settlement 2")).toBeInTheDocument();
    const table = screen.getByRole("table", { name: "Cities at turn 250" });
    expect(within(table).getAllByRole("row")).toHaveLength(1 + CITIES_LAST.cities!.cities.length);
    expect(within(table).getAllByText("self-government")).toHaveLength(2);
    fireEvent.click(within(table).getAllByRole("button", { name: "Kethani Empire" })[0]);
    expect(p.onSelectCivilization).toHaveBeenCalledWith("Kethani Empire");
    fireEvent.click(within(table).getByRole("button", { name: "Sunfire Steppe" }));
    expect(p.onSelectRegion).toHaveBeenCalledWith("Sunfire Steppe");
    // The first living city is followed: its purse, unrest and recorded moments.
    const history = screen.getByRole("region", { name: "History of Sunfire Steppe Settlement 1" });
    expect(within(history).getByLabelText("Civic purse of Sunfire Steppe Settlement 1")).toBeInTheDocument();
    const moments = within(history).getByRole("list", { name: "Recorded moments of Sunfire Steppe Settlement 1" });
    expect(within(moments).getByText(/has grown into a great city/)).toBeInTheDocument();
    fireEvent.click(within(moments).getAllByRole("listitem")[0]);
    expect(p.onSelectEvent).toHaveBeenCalledTimes(1);
  });

  it("follows the city chosen in the table, including one that fell", () => {
    const view = render(<CitiesPanel {...props(cities, citiesAt(150))} />);
    const table = screen.getByRole("table", { name: "Cities at turn 150" });
    fireEvent.click(within(table).getByRole("button", { name: "Verdant Plains Settlement 2" }));
    const history = screen.getByRole("region", { name: "History of Verdant Plains Settlement 2" });
    // Its record as known at turn 150: founded at 120, its peak so far; the
    // fall (turn 165) is neither in the note nor among the moments yet.
    expect(within(history).getByText(/founded turn 120; peak by turn 150 town/)).toBeInTheDocument();
    expect(within(history).queryByText(/fell at turn 165/)).not.toBeInTheDocument();
    const moments = within(history).getByRole("list", { name: "Recorded moments of Verdant Plains Settlement 2" });
    expect(within(moments).getByText(/Famine/)).toBeInTheDocument();
    expect(within(moments).queryByText(/is abandoned/)).not.toBeInTheDocument();
    // From turn 165 the fall is recorded.
    view.rerender(<CitiesPanel {...props(cities, citiesAt(170))} />);
    const later = screen.getByRole("region", { name: "History of Verdant Plains Settlement 2" });
    expect(within(later).getByText(/fell at turn 165 \(abandoned\)/)).toBeInTheDocument();
  });

  it("states a later city's founding is not recorded yet, and takes no later city as the default focus", () => {
    const record = cityRecord(cities, 5)!;
    const before = citiesAt(record.founded_turn - 1);
    // A city chosen at a later turn stays selected while scrubbing back.
    const view = render(<CitiesPanel {...props(cities, citiesAt(150))} />);
    fireEvent.click(within(screen.getByRole("table", { name: "Cities at turn 150" }))
      .getByRole("button", { name: "Verdant Plains Settlement 2" }));
    view.rerender(<CitiesPanel {...props(cities, before)} />);
    const history = screen.getByRole("region", { name: "History of Verdant Plains Settlement 2" });
    expect(within(history).getByText(`Not yet founded at turn ${before.turn}.`)).toBeInTheDocument();
    expect(within(history).queryByText(/peak/)).not.toBeInTheDocument();
    expect(cityRecordAt(cities, 5, before.turn)).toBeNull();
    expect(cityRecordAt(cities, 5, 150)).toMatchObject({ fell: false, peakRank: 1 });
    expect(cityRecordAt(cities, 5, 165)?.fell).toBe(true);
    // The default focus at a turn with no living city is a city known by then, never a later one.
    view.unmount();
    const first = cities.history.find((snapshot) => (snapshot.cities?.cities.length ?? 0) > 0)!;
    const empty = cities.history.filter((snapshot) => snapshot.turn < first.turn).at(-1);
    if (empty) {
      render(<CitiesPanel {...props(cities, empty)} />);
      expect(screen.queryByRole("region", { name: /History of/ })).not.toBeInTheDocument();
    }
  });

  it("shows the wares each city made, and a dash in bundles from before crafts", () => {
    const snapshot = citiesAt(150);
    const withWares: TurnSnapshot = {
      ...snapshot,
      cities: {
        ...snapshot.cities!,
        cities: snapshot.cities!.cities.map((row, i) => (i === 0 ? { ...row, crafts: 1.25 }
          : i === 2 ? { ...row, crafts: 0.03 } : row)),
      },
    };
    render(<CitiesPanel {...props(cities, withWares)} />);
    const table = screen.getByRole("table", { name: "Cities at turn 150" });
    expect(within(table).getByRole("columnheader", { name: "Wares" })).toBeInTheDocument();
    const rows = within(table).getAllByRole("row").slice(1);
    expect(within(rows[0]).getByText("1.25")).toBeInTheDocument();
    // A fraction of a unit is still wares made, not "0.0".
    expect(within(rows[2]).getByText("0.03")).toBeInTheDocument();
    expect(within(rows[1]).getAllByText("-").length).toBeGreaterThan(0);
  });

  it("shows a guild column and the guilds table only in runs with guilds", () => {
    const snapshot = citiesAt(150);
    const [first, second] = snapshot.cities!.cities;
    // Synthetic guild rows on the cities fixture (the shape guilds.snapshot_summary writes).
    const withGuilds: TurnSnapshot = {
      ...snapshot,
      guilds: {
        guilds: [
          { id: 0, name: `the Weavers' Guild of ${first.name}`, city: first.id, region: first.region,
            kind: "craft", masters: 6.2, wealth: 4.5, monopoly: true, say: true, charter: 3 },
          { id: 2, name: `the Merchant Guild of ${second.name}`, city: second.id, region: second.region,
            kind: "merchant", masters: 4.1, wealth: 1.0, monopoly: false, say: false, levy: true, movement: 7 },
        ],
        dissolved: 1,
        burghers: { "Kethani Empire": 0.14 },
        counters: { founded: 3, privileges: 2, levies: 1, threats: 2, movements: 1, charters: 1 },
      },
    };
    render(<CitiesPanel {...props(cities, withGuilds)} />);
    const table = screen.getByRole("table", { name: "Cities at turn 150" });
    expect(within(table).getByRole("columnheader", { name: "Guild" })).toBeInTheDocument();
    const rows = within(table).getAllByRole("row").slice(1);
    expect(within(rows[0]).getByText("craft: monopoly, say in dues, guild charter")).toBeInTheDocument();
    expect(within(rows[1]).getByText("merchant: levied")).toBeInTheDocument();
    const guilds = screen.getByRole("table", { name: "Guilds at turn 150" });
    expect(within(guilds).getAllByRole("row")).toHaveLength(3);
    expect(within(guilds).getByText("rising for its privileges")).toBeInTheDocument();
    fireEvent.click(within(guilds).getByRole("button", { name: second.name }));
    expect(screen.getByRole("region", { name: `History of ${second.name}` })).toBeInTheDocument();
    expect(screen.getByLabelText("Guild totals by turn 150")).toHaveTextContent("Guild charters1");
    cleanup();
    render(<CitiesPanel {...props(cities, snapshot)} />);
    expect(within(screen.getByRole("table", { name: "Cities at turn 150" }))
      .queryByRole("columnheader", { name: "Guild" })).not.toBeInTheDocument();
    expect(screen.queryByRole("table", { name: "Guilds at turn 150" })).not.toBeInTheDocument();
  });

  it("says so before the first city and is a tab only when the run records cities", () => {
    render(<CitiesPanel {...props(cities, citiesAt(5))} />);
    expect(screen.getByText("No city stands at turn 5.")).toBeInTheDocument();
    cleanup();
    render(<SystemsPanel {...props(cities, CITIES_LAST)} surface="overview" />);
    expect(screen.getAllByRole("tab").map((tab) => tab.textContent)).toEqual(["Cities"]);
  });
});

/**
 * A trimmed template run with --agent-movements (500 hybrid turns, every
 * fifth snapshot and the last): `agent_movements` per snapshot, the movement
 * and reform events with the events they cite, `world_state.agent_movements`.
 */
const movements = movementsFixture as unknown as Bundle;
const MOVEMENTS_LAST = movements.history[movements.history.length - 1];

describe("MovementsPanel", () => {
  const busiest = movements.history.reduce((best, snapshot) =>
    (snapshot.agent_movements!.living.length > best.agent_movements!.living.length ? snapshot : best));

  it("renders the movements over time and the scrubbed turn's table", () => {
    const p = props(movements, busiest);
    render(<MovementsPanel {...p} />);
    expect(screen.getByRole("group", { name: "Stage of each movement over time" })).toBeInTheDocument();
    expect(screen.getByLabelText("Living movements by creed")).toBeInTheDocument();
    // The creed chart says which line is which.
    const legends = screen.getAllByLabelText("Legend").map((legend) => legend.textContent);
    expect(legends).toContain("commonslibertysect");  // no guild creed: the fixture records no guilds
    const living = busiest.agent_movements!.living;
    const table = screen.getByRole("table", { name: `Movements at turn ${busiest.turn}` });
    expect(within(table).getAllByRole("row")).toHaveLength(1 + living.length);
    const target = movements.world_state.civilizations[living[0].target].name;
    fireEvent.click(within(table).getAllByRole("button", { name: target })[0]);
    expect(p.onSelectCivilization).toHaveBeenCalledWith(target);
    // The first living movement is followed: its members and recorded moments.
    const history = screen.getByRole("region", { name: `History of ${living[0].name}` });
    expect(within(history).getByLabelText(`Members of ${living[0].name}`)).toBeInTheDocument();
    const moments = within(history).getByRole("list", { name: `Recorded moments of ${living[0].name}` });
    expect(within(moments).getAllByRole("listitem").length).toBeGreaterThan(0);
  });

  it("lists the lasting reforms in force and follows the movement that won one", () => {
    const snapshot = movements.history.find((entry) => (entry.agent_movements!.reforms ?? []).length > 0)!;
    const p = props(movements, snapshot);
    render(<MovementsPanel {...p} />);
    const reforms = snapshot.agent_movements!.reforms!;
    const table = screen.getByRole("table", { name: `Lasting reforms at turn ${snapshot.turn}` });
    expect(within(table).getAllByRole("row")).toHaveLength(1 + reforms.length);
    const winner = movements.world_state.agent_movements!.movements![reforms[0].movement].name;
    fireEvent.click(within(table).getByRole("button", { name: winner }));
    expect(screen.getByRole("region", { name: `History of ${winner}` })).toBeInTheDocument();
    const totals = screen.getByLabelText(`Movement totals by turn ${snapshot.turn}`);
    expect(within(totals).getByText("Lasting reforms enacted")).toBeInTheDocument();
  });

  it("follows a movement as known at the scrubbed turn, and takes no later one as the default focus", () => {
    // Before the first movement nothing is followed (main dae4ba5 followed the
    // run's first movement, with its whole record).
    const firstTurn = movements.history.find((snapshot) => snapshot.agent_movements!.living.length > 0)!.turn;
    const before = movements.history.filter((snapshot) => snapshot.turn < firstTurn).at(-1)!;
    const view = render(<MovementsPanel {...props(movements, before)} />);
    expect(screen.queryByRole("region", { name: /History of/ })).not.toBeInTheDocument();
    expect(document.body.textContent).not.toContain("Whole record");
    view.unmount();

    // A movement that ended: at a turn while it lived, its note has no end and its totals so far.
    const records = movements.world_state.agent_movements!.movements!;
    const id = records.findIndex((record) => record.ended_turn != null
      && movements.history.some((snapshot) => snapshot.turn < record.ended_turn!
        && snapshot.agent_movements!.living.some((row) => row.id === records.indexOf(record))));
    const record = movementRecord(movements, id)!;
    const living = movements.history.filter((snapshot) => snapshot.turn < record.ended_turn!
      && snapshot.agent_movements!.living.some((row) => row.id === id)).at(-1)!;
    const shown = render(<MovementsPanel {...props(movements, living)} />);
    fireEvent.click(within(screen.getByRole("table", { name: `Movements at turn ${living.turn}` }))
      .getByRole("button", { name: record.name }));
    const note = within(screen.getByRole("region", { name: `History of ${record.name}` }))
      .getByText(/founded turn/).textContent ?? "";
    expect(note).toContain(`By turn ${living.turn}: peak`);
    expect(note).not.toContain(`at turn ${record.ended_turn}`);
    shown.rerender(<MovementsPanel {...props(movements, MOVEMENTS_LAST)} />);
    const after = within(screen.getByRole("region", { name: `History of ${record.name}` }))
      .getByText(/founded turn/).textContent ?? "";
    expect(after).toContain(`at turn ${record.ended_turn}`);
  });

  it("says so before the first movement and is a tab only when the run records movements", () => {
    const quiet = movements.history.find((snapshot) => snapshot.agent_movements!.living.length === 0)!;
    render(<MovementsPanel {...props(movements, quiet)} />);
    expect(screen.getByText(`No movement is living at turn ${quiet.turn}.`)).toBeInTheDocument();
    cleanup();
    render(<SystemsPanel {...props(movements, MOVEMENTS_LAST)} surface="overview" />);
    // The run's registry records schisms (an older bundle's faiths, rebuilt: lib/faiths).
    expect(screen.getAllByRole("tab").map((tab) => tab.textContent)).toEqual(["Movements", "Faiths"]);
    cleanup();
    render(<MovementsPanel {...props(fixture, LAST)} />);
    expect(screen.getByText(`No movement record at turn ${LAST.turn}.`)).toBeInTheDocument();
  });
});

/**
 * Procedural seed 42, 200 hybrid turns, every tenth snapshot: four sects took
 * the native slots of vanished faiths. `faiths` has the permanent faith table
 * (docs/integration/permanent-faiths.md); `faithsLegacy` is the same run
 * written before it, whose records name faiths by slot.
 */
const faiths = faithsFixture as unknown as Bundle;
const faithsLegacy = faithsLegacyFixture as unknown as Bundle;
const FAITHS_LAST = faiths.history[faiths.history.length - 1];

describe("FaithsPanel", () => {
  it("lists each church once by name and founding turn, two that shared a slot apart", () => {
    const p = props(faiths, FAITHS_LAST);
    render(<FaithsPanel {...p} />);
    const table = screen.getByRole("table", { name: `Faiths by turn ${FAITHS_LAST.turn}` });
    expect(within(table).getAllByRole("row")).toHaveLength(1 + faiths.world_state.faiths!.length);
    const vanished = within(table).getByRole("button", { name: "Faith of Duglutoni Principality (Reformed)" })
      .closest("tr")!;
    expect(vanished).toHaveTextContent("10 (shared)");
    expect(vanished).toHaveTextContent(
      "vanished; slot 10 passed to the Faith of Lisolenen League (Reformed) (founded turn 37) at turn 37");
    const sect = within(table).getByRole("button", { name: "Faith of Lisolenen League (Reformed)" }).closest("tr")!;
    expect(sect).toHaveTextContent("holds slot 10");
    expect(sect).toHaveTextContent("sect of the Seekers of Pondor Strand");
    expect(sect).toHaveTextContent("Faith of Lisolenen League (founded turn 0)");
    fireEvent.click(within(table).getByRole("button", { name: "Faith of Lisolenen League (Reformed)" }));
    const history = screen.getByRole("region", {
      name: "History of the Faith of Lisolenen League (Reformed) (founded turn 37)" });
    expect(within(history).getByText(/also named: Faith of Duglutoni Principality \(Reformed\)/)).toBeInTheDocument();
    const moments = within(history).getByRole("list", {
      name: "Recorded moments of the Faith of Lisolenen League (Reformed) (founded turn 37)" });
    expect(within(moments).getAllByRole("listitem").length).toBeGreaterThan(0);
    fireEvent.click(within(table).getByRole("button", { name: "Faith of Khorain Kingdom" }));
    expect(p.onSelectCivilization).not.toHaveBeenCalled();
    fireEvent.click(within(table).getAllByRole("button", { name: "Khorain Kingdom" })[0]);
    expect(p.onSelectCivilization).toHaveBeenCalledWith("Khorain Kingdom");
  });

  it("shows the faiths as known at the scrubbed turn", () => {
    const early = faiths.history.find((snapshot) => snapshot.turn === 31)!;
    render(<FaithsPanel {...props(faiths, early)} />);
    const table = screen.getByRole("table", { name: "Faiths by turn 31" });
    expect(within(table).getAllByRole("row")).toHaveLength(1 + 16);
    expect(within(table).queryByText(/vanished/)).not.toBeInTheDocument();
    expect(within(table).queryByText(/\(shared\)/)).not.toBeInTheDocument();
  });

  it("rebuilds an older bundle's churches and says so", () => {
    render(<FaithsPanel {...props(faithsLegacy, faithsLegacy.history[faithsLegacy.history.length - 1])} />);
    expect(screen.getByText(/predates permanent faith ids/)).toBeInTheDocument();
    const table = screen.getByRole("table", { name: `Faiths by turn ${FAITHS_LAST.turn}` });
    expect(within(table).getAllByRole("row")).toHaveLength(1 + 20);
    expect(within(table).getByRole("button", { name: "Faith of Duglutoni Principality (Reformed)" }).closest("tr")!)
      .toHaveTextContent("vanished; slot 10 passed to the Faith of Lisolenen League (Reformed) (founded turn 37)");
  });

  it("is a tab beside the movements", () => {
    render(<SystemsPanel {...props(faiths, FAITHS_LAST)} surface="overview" />);
    expect(screen.getAllByRole("tab").map((tab) => tab.textContent)).toEqual(["Movements", "Faiths"]);
  });

  it("names a sect's church and the church it became by permanent identity", () => {
    const records = faiths.world_state.agent_movements!.movements!;
    const id = records.findIndex((record) => record.name === "the Seekers of Pondor Strand");
    render(<MovementsPanel {...props(faiths, FAITHS_LAST)} />);
    fireEvent.click(screen.getByRole("button", { name: `${records[id].name} (sect)` }));
    const history = screen.getByRole("region", { name: `History of ${records[id].name}` });
    expect(within(history).getByText(/A sect movement of the Faith of Lisolenen League \(founded turn 0\)/))
      .toBeInTheDocument();
    expect(within(history).getByText(
      /becoming the church of the Faith of Lisolenen League \(Reformed\) \(founded turn 37\)/)).toBeInTheDocument();
  });
});

/**
 * A trimmed template run with --scholarship (500 hybrid turns, every fifth
 * snapshot and the last): `scholarship` per snapshot, the seat events with
 * the events they cite, `world_state.scholarship`.
 */
const learning = learningFixture as unknown as Bundle;
const LEARNING_LAST = learning.history[learning.history.length - 1];

describe("LearningPanel", () => {
  const busiest = learning.history.reduce((best, snapshot) =>
    (snapshot.scholarship!.seats.length > best.scholarship!.seats.length ? snapshot : best));

  it("renders the seats over time, the scrubbed turn's table and the first seat's history", () => {
    const p = props(learning, busiest);
    render(<LearningPanel {...p} />);
    expect(screen.getByRole("group", { name: "Level of each seat of learning over time" })).toBeInTheDocument();
    const living = busiest.scholarship!.seats;
    const table = screen.getByRole("table", { name: `Seats of learning at turn ${busiest.turn}` });
    expect(within(table).getAllByRole("row")).toHaveLength(1 + living.length);
    expect(within(table).getAllByText(/its (ruler|temple|city)/).length).toBe(living.length);
    fireEvent.click(within(table).getAllByRole("button", { name: living[0].region! })[0]);
    expect(p.onSelectRegion).toHaveBeenCalledWith(living[0].region);
    const history = screen.getByRole("region", { name: `History of ${living[0].name}` });
    expect(within(history).getByLabelText(`Scholars of ${living[0].name}`)).toBeInTheDocument();
    const moments = within(history).getByRole("list", { name: `Recorded moments of ${living[0].name}` });
    expect(within(moments).getAllByRole("listitem").length).toBeGreaterThan(0);
    const totals = screen.getByLabelText(`Seat totals by turn ${busiest.turn}`);
    expect(within(totals).getByText("Flights to another seat")).toBeInTheDocument();
  });

  it("follows a seat chosen in the table and says where a fallen seat's scholars went", () => {
    const seats = learning.world_state.scholarship!.seats!;
    const index = seats.findIndex((seat) => seat.fallen_turn != null && seat.refuge >= 0);
    const standing = learning.history.find((snapshot) =>
      snapshot.scholarship!.seats.some((row) => row.id === index))!;
    const p = props(learning, standing);
    p.currentTurn = LEARNING_LAST.turn;
    render(<LearningPanel {...p} />);
    const table = screen.getByRole("table", { name: `Seats of learning at turn ${standing.turn}` });
    fireEvent.click(within(table).getByRole("button", { name: seats[index].name }));
    const history = screen.getByRole("region", { name: `History of ${seats[index].name}` });
    expect(within(history).getByText(new RegExp(`its scholars fled to ${seats[seats[index].refuge].name}`)))
      .toBeInTheDocument();
  });

  it("tells a seat's fall and refuge only from the turn it fell", () => {
    const seats = learning.world_state.scholarship!.seats!;
    const index = seats.findIndex((seat) => seat.fallen_turn != null && seat.refuge >= 0);
    const standing = learning.history.find((snapshot) =>
      snapshot.scholarship!.seats.some((row) => row.id === index))!;
    render(<LearningPanel {...props(learning, standing)} />);
    const table = screen.getByRole("table", { name: `Seats of learning at turn ${standing.turn}` });
    fireEvent.click(within(table).getByRole("button", { name: seats[index].name }));
    const history = screen.getByRole("region", { name: `History of ${seats[index].name}` });
    expect(within(history).getByText(new RegExp(`founded turn ${seats[index].founded_turn}`))).toBeInTheDocument();
    expect(within(history).queryByText(/fell at turn|its scholars fled to/)).toBeNull();
  });

  it("says so before the first seat and is a tab only when the run records seats", () => {
    render(<LearningPanel {...props(learning, learning.history[0])} />);
    expect(screen.getByText(`No seat of learning stands at turn ${learning.history[0].turn}.`)).toBeInTheDocument();
    cleanup();
    render(<SystemsPanel {...props(learning, LEARNING_LAST)} surface="overview" />);
    expect(screen.getAllByRole("tab").map((tab) => tab.textContent)).toEqual(["Learning"]);
    cleanup();
    render(<LearningPanel {...props(fixture, LAST)} />);
    expect(screen.getByText(`No record of seats of learning at turn ${LAST.turn}.`)).toBeInTheDocument();
  });
});

describe("RegionSystemsDetail", () => {
  it("shows a region's outbreaks, quarantine and practised techniques at the snapshot", () => {
    const region = "Dililene Coast";
    render(<RegionSystemsDetail snapshot={LAST} region={region} />);
    const epidemics = screen.getByLabelText(`Epidemics in ${region}`);
    expect(within(epidemics).getByText(/Marsh fever/)).toBeInTheDocument();
    // The controller (Thyrodori Confederacy) is not the quarantining state at turn 120.
    expect(within(epidemics).getByText("Borders open")).toBeInTheDocument();
    const techniques = screen.getByLabelText(`Techniques in ${region}`);
    expect(within(techniques).getByText("Writing")).toBeInTheDocument();
    const writing = LAST.techniques!.regions![region].writing;
    expect(within(techniques).getByText(`${(writing * 100).toFixed(0)}%`)).toBeInTheDocument();
  });

  it("names a quarantining controller and an empty region", () => {
    const snapshot = {
      ...LAST,
      region_control: { ...LAST.region_control, "Dadun Grasslands": "Glewahami Confederacy" },
      techniques: { ...LAST.techniques!, regions: {} },
    };
    render(<RegionSystemsDetail snapshot={snapshot} region="Dadun Grasslands" />);
    expect(screen.getByText("Glewahami Confederacy has closed its borders")).toBeInTheDocument();
    expect(screen.getByText("None reportable")).toBeInTheDocument();
    expect(screen.getByText("None recorded")).toBeInTheDocument();
  });

  it("shows a region's food, famine and the armies in it", () => {
    const spans = famineSpans(fixture.events_timeline);
    const names = fixture.world_state.regions.map((region) => region.name);
    const snapshot = at(101);
    const army = snapshot.campaign!.armies[0];
    render(<RegionSystemsDetail snapshot={snapshot} region={army.region} famine={spans} regionNames={names} />);
    const food = screen.getByLabelText(`Food in ${army.region}`);
    expect(within(food).getByText("Food ÷ need")).toBeInTheDocument();
    expect(within(screen.getByLabelText(`War in ${army.region}`)).getByText(army.name)).toBeInTheDocument();
    cleanup();
    const hungry = fixture.history.flatMap((entry) => crisesAtSnapshot(spans, entry.turn)
      .map((span) => ({ entry, span })))[0];
    expect(hungry).toBeDefined();
    render(<RegionSystemsDetail snapshot={hungry.entry} region={hungry.span.region} famine={spans} regionNames={names} />);
    expect(within(screen.getByLabelText(`Food in ${hungry.span.region}`)).getByText(`Since turn ${hungry.span.start}`))
      .toBeInTheDocument();
  });

  it("renders nothing when the snapshot carries neither system", () => {
    const { container } = render(<RegionSystemsDetail snapshot={sample.history[0]} region={sample.world_state.regions[0].name} />);
    expect(container).toBeEmptyDOMElement();
  });
});
