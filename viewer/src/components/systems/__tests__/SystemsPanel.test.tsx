import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import systemsFixture from "../../../__fixtures__/systems_bundle.json";
import sampleFixture from "../../../__fixtures__/sample_bundle.json";
import citiesFixture from "../../../__fixtures__/cities_bundle.json";
import type { Bundle, TurnSnapshot } from "../../../types";
import type { SystemPanelProps } from "../../../lib/systems";
import { AgendasPanel } from "../AgendasPanel";
import { CitiesPanel } from "../CitiesPanel";
import { ContactPanel } from "../ContactPanel";
import { DiplomacyPanel } from "../DiplomacyPanel";
import { EpidemicsPanel } from "../EpidemicsPanel";
import { FinancePanel } from "../FinancePanel";
import { FoodPanel } from "../FoodPanel";
import { GovernancePanel } from "../GovernancePanel";
import { MaritimePanel } from "../MaritimePanel";
import { NomadsPanel } from "../NomadsPanel";
import { RegionSystemsDetail } from "../RegionSystemsDetail";
import { SystemsPanel } from "../SystemsPanel";
import { WarsPanel } from "../WarsPanel";
import { famineSpans, foodCrisisSpans } from "../../../lib/food";
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
    expect(screen.getByLabelText("Regions short of food and regions in famine")).toBeInTheDocument();
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
    const snapshot = labelled.history.find((entry) => spans.some((span) => span.kind === "dearth"
      && span.start <= entry.turn && (span.end === null || span.end > entry.turn)))!;
    render(<FoodPanel {...props(labelled, snapshot)} />);
    expect(screen.getByText("Regions in dearth")).toBeInTheDocument();
    const hungry = screen.getByRole("table", { name: `Hungry regions at turn ${snapshot.turn}` });
    expect(within(hungry).getAllByText(/^Dearth since T/).length).toBeGreaterThan(0);
    expect(screen.getAllByText("dearth").length).toBeGreaterThan(0);
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
    render(<CitiesPanel {...props(cities, citiesAt(150))} />);
    const table = screen.getByRole("table", { name: "Cities at turn 150" });
    fireEvent.click(within(table).getByRole("button", { name: "Verdant Plains Settlement 2" }));
    const history = screen.getByRole("region", { name: "History of Verdant Plains Settlement 2" });
    expect(within(history).getByText(/fell at turn 165 \(abandoned\)/)).toBeInTheDocument();
    // Its famine is a recorded moment; the fall (turn 165) is not shown at turn 150.
    const moments = within(history).getByRole("list", { name: "Recorded moments of Verdant Plains Settlement 2" });
    expect(within(moments).getByText(/Famine/)).toBeInTheDocument();
    expect(within(moments).queryByText(/is abandoned/)).not.toBeInTheDocument();
  });

  it("shows the wares each city made, and a dash in bundles from before crafts", () => {
    const snapshot = citiesAt(150);
    const withWares: TurnSnapshot = {
      ...snapshot,
      cities: {
        ...snapshot.cities!,
        cities: snapshot.cities!.cities.map((row, i) => (i === 0 ? { ...row, crafts: 1.25 } : row)),
      },
    };
    render(<CitiesPanel {...props(cities, withWares)} />);
    const table = screen.getByRole("table", { name: "Cities at turn 150" });
    expect(within(table).getByRole("columnheader", { name: "Wares" })).toBeInTheDocument();
    const rows = within(table).getAllByRole("row").slice(1);
    expect(within(rows[0]).getByText("1.3")).toBeInTheDocument();
    expect(within(rows[1]).getAllByText("-").length).toBeGreaterThan(0);
  });

  it("says so before the first city and is a tab only when the run records cities", () => {
    render(<CitiesPanel {...props(cities, citiesAt(5))} />);
    expect(screen.getByText("No city stands at turn 5.")).toBeInTheDocument();
    cleanup();
    render(<SystemsPanel {...props(cities, CITIES_LAST)} surface="overview" />);
    expect(screen.getAllByRole("tab").map((tab) => tab.textContent)).toEqual(["Cities"]);
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
    const hungry = fixture.history.flatMap((entry) => spans
      .filter((span) => span.start <= entry.turn && (span.end === null || span.end > entry.turn))
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
