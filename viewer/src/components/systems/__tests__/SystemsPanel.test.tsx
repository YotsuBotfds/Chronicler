import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import systemsFixture from "../../../__fixtures__/systems_bundle.json";
import sampleFixture from "../../../__fixtures__/sample_bundle.json";
import type { Bundle, TurnSnapshot } from "../../../types";
import type { SystemKey, SystemPanelProps } from "../../../lib/systems";
import { DiplomacyPanel } from "../DiplomacyPanel";
import { EpidemicsPanel } from "../EpidemicsPanel";
import { FinancePanel } from "../FinancePanel";
import { MaritimePanel } from "../MaritimePanel";
import { RegionSystemsDetail } from "../RegionSystemsDetail";
import { SystemsPanel } from "../SystemsPanel";
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

function without(bundle: Bundle, ...keys: SystemKey[]): Bundle {
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
    render(<DiplomacyPanel {...props(fixture, at(25))} />);
    const subjects = screen.getByRole("table", { name: "Subjects at turn 25" });
    expect(within(subjects).getByText("client")).toBeInTheDocument();
    expect(within(subjects).getByText("League of Fewen")).toBeInTheDocument();
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
    const p = props();
    render(<MaritimePanel {...p} />);
    expect(screen.getAllByRole("img", { name: /^the Morendor Bight: / }).length).toBe(1);
    const zones = screen.getByRole("table", { name: "Sea zones at turn 120" });
    expect(within(zones).getAllByRole("row")).toHaveLength(1 + LAST.maritime!.zones.length);
    const fleets = screen.getByRole("table", { name: "Fleets at turn 120" });
    expect(within(fleets).getAllByRole("row")).toHaveLength(1 + LAST.maritime!.fleets.length);
    const blockades = screen.getByRole("table", { name: "Blockades at turn 120" });
    expect(within(blockades).getAllByRole("row")).toHaveLength(1 + LAST.maritime!.blockades.length);
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

describe("SystemsPanel", () => {
  it("offers one tab per recorded system and switches between them", () => {
    render(<SystemsPanel {...props()} surface="overview" />);
    const tabs = screen.getAllByRole("tab").map((tab) => tab.textContent);
    expect(tabs).toEqual(["Epidemics", "Finance", "Diplomacy", "Techniques", "Maritime"]);
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
    const partial = without(fixture, "finance", "maritime");
    render(<SystemsPanel {...props(partial, partial.history[partial.history.length - 1])} surface="trade" />);
    expect(screen.getAllByRole("tab").map((tab) => tab.textContent)).toEqual(["Epidemics", "Diplomacy", "Techniques"]);
    expect(screen.getByRole("tab", { name: "Epidemics" })).toHaveAttribute("aria-selected", "true");
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
    expect(within(techniques).getByText("96%")).toBeInTheDocument();
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

  it("renders nothing when the snapshot carries neither system", () => {
    const { container } = render(<RegionSystemsDetail snapshot={sample.history[0]} region={sample.world_state.regions[0].name} />);
    expect(container).toBeEmptyDOMElement();
  });
});
