import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import served from "../../__fixtures__/featureCatalog.json";
import type { FeatureSelection } from "../../types";
import { FeatureOptions } from "../FeatureOptions";

afterEach(cleanup);

function catalogWith(change: (raw: Record<string, any>) => void = () => {}) { // eslint-disable-line @typescript-eslint/no-explicit-any
  const raw = structuredClone(served);
  change(raw);
  return raw;
}

function Harness({ catalog, surface = "live", onChange = () => {}, unavailable = null }: {
  catalog: unknown; surface?: "live" | "batch"; onChange?: (selection: FeatureSelection) => void;
  unavailable?: string | null;
}) {
  const [selection, setSelection] = useState<FeatureSelection>({});
  const [agents, setAgents] = useState<string | null>(null);
  return (
    <FeatureOptions
      catalog={catalog}
      surface={surface}
      selection={selection}
      onSelectionChange={(next) => { setSelection(next); onChange(next); }}
      agents={agents}
      onAgentsChange={setAgents}
      unavailable={unavailable}
    />
  );
}

function open() {
  fireEvent.click(screen.getByRole("button", { name: /Experimental features \(off by default\)/ }));
}

const box = (name: RegExp) => screen.getByRole("checkbox", { name }) as HTMLInputElement;

function description(element: HTMLElement): string {
  return element.getAttribute("aria-describedby")!.split(" ")
    .map((id) => document.getElementById(id)!.textContent).join(" ");
}

describe("FeatureOptions", () => {
  it("renders nothing for an older server that sends no catalog", () => {
    const { container } = render(<Harness catalog={undefined} />);
    expect(container.innerHTML).toBe("");
  });

  it("shows a notice instead of options when the catalog is malformed", () => {
    render(<Harness catalog={catalogWith((raw) => { raw.schema_version = 9; })} />);
    expect(screen.getByRole("status").textContent).toMatch(/cannot read \(unsupported feature_catalog schema_version 9\)/);
    expect(screen.queryByRole("button", { name: /Experimental features/ })).toBeNull();
    expect(screen.queryAllByRole("checkbox")).toHaveLength(0);
  });

  it("is collapsed with nothing selected until opened", () => {
    render(<Harness catalog={served} />);
    const toggle = screen.getByRole("button", { name: /Experimental features/ });
    expect(toggle.getAttribute("aria-expanded")).toBe("false");
    expect(screen.queryAllByRole("checkbox")).toHaveLength(0);
    open();
    expect(toggle.getAttribute("aria-expanded")).toBe("true");
    expect(screen.getByRole("group", { name: "Livelihoods" })).toBeTruthy();
    expect(screen.getByRole("group", { name: "Prerequisites" })).toBeTruthy();
    for (const checkbox of screen.getAllByRole("checkbox")) expect((checkbox as HTMLInputElement).checked).toBe(false);
    expect(screen.getByText("Selected: none.")).toBeTruthy();
  });

  it("disables what the server's agent mode cannot run, with the reason", () => {
    render(<Harness catalog={catalogWith((raw) => {
      raw.surfaces.live.agents = "off";
      raw.surfaces.live.agent_modes = ["off"];
    })} />);
    open();
    const workshops = box(/^Workshops --workshops$/);
    expect(workshops.disabled).toBe(true);
    expect(description(workshops)).toMatch(/Unavailable: requires --agents hybrid \(this server runs --agents off\)/);
    expect(box(/^Scholarship --scholarship$/).disabled).toBe(false);
    expect(screen.getByText(/Agent mode: --agents off \(set when the server was started\)/)).toBeTruthy();
  });

  it("enables a switch once its prerequisite is on and drops it when the prerequisite goes", () => {
    const onChange = vi.fn();
    render(<Harness catalog={served} onChange={onChange} />);
    open();
    expect(box(/^Local budgets/).disabled).toBe(true);
    expect(description(box(/^Local budgets/))).toMatch(/Unavailable: requires --grain-reserves\./);
    fireEvent.click(box(/^Grain reserves/));
    expect(box(/^Local budgets/).disabled).toBe(false);
    fireEvent.click(box(/^Local budgets/));
    expect(onChange).toHaveBeenLastCalledWith({ grain_reserves: true, local_budgets: true });
    expect(screen.getByText("--grain-reserves --local-budgets")).toBeTruthy();
    expect(screen.getByRole("button", { name: /2 selected/ })).toBeTruthy();
    fireEvent.click(box(/^Grain reserves/));
    expect(onChange).toHaveBeenLastCalledWith({});
    expect(box(/^Local budgets/).checked).toBe(false);
    expect(box(/^Local budgets/).disabled).toBe(true);
  });

  it("shows a switch's mode only while it is on and sends only a non-default mode", () => {
    const onChange = vi.fn();
    render(<Harness catalog={served} onChange={onChange} />);
    open();
    expect(screen.queryByRole("combobox", { name: /Workshop mode/ })).toBeNull();
    fireEvent.click(box(/^Workshops/));
    const mode = screen.getByRole("combobox", { name: /Workshop mode/ }) as HTMLSelectElement;
    expect(mode.value).toBe("operate");
    expect([...mode.options].map((option) => option.textContent)).toEqual(["operate (default)", "observe", "cost_only"]);
    expect(onChange).toHaveBeenLastCalledWith({ workshops: true });
    fireEvent.change(mode, { target: { value: "observe" } });
    expect(onChange).toHaveBeenLastCalledWith({ workshops: true, workshop_mode: "observe" });
    // Payroll needs the operate mode.
    expect(box(/^Workshop payroll/).disabled).toBe(true);
    fireEvent.change(mode, { target: { value: "operate" } });
    expect(onChange).toHaveBeenLastCalledWith({ workshops: true });
    fireEvent.click(box(/^Workshop payroll/));
    fireEvent.change(screen.getByRole("combobox", { name: /Workshop mode/ }), { target: { value: "cost_only" } });
    expect(onChange).toHaveBeenLastCalledWith({ workshops: true, workshop_mode: "cost_only" });
    fireEvent.click(box(/^Workshops/));
    expect(onChange).toHaveBeenLastCalledWith({});
    expect(screen.queryByRole("combobox", { name: /Workshop mode/ })).toBeNull();
  });

  it("lets Batch Lab choose the runs' agent mode and re-checks requirements", () => {
    render(<Harness surface="batch" catalog={catalogWith((raw) => { raw.surfaces.batch.agents = "off"; })} />);
    open();
    expect(box(/^Workshops/).disabled).toBe(true);
    expect(description(box(/^Workshops/))).toMatch(/requires --agents hybrid \(these runs use --agents off\)/);
    const agents = screen.getByRole("combobox", { name: /Agent mode for these runs/ });
    fireEvent.change(agents, { target: { value: "hybrid" } });
    expect(box(/^Workshops/).disabled).toBe(false);
    fireEvent.click(box(/^Workshops/));
    expect(box(/^Workshops/).checked).toBe(true);
    fireEvent.change(agents, { target: { value: "" } });
    expect(box(/^Workshops/).checked).toBe(false);
  });

  it("shows what the server's command line already sets", () => {
    render(<Harness catalog={catalogWith((raw) => { raw.surfaces.live.values = { grain_reserves: true }; })} />);
    open();
    expect(box(/^Grain reserves/).checked).toBe(true);
    expect(screen.getByText(/Already on the server's command line/)).toBeTruthy();
    expect(box(/^Local budgets/).disabled).toBe(false);
  });

  it("offers the productive-recovery switches off, each disabled until its prerequisites are met", () => {
    const onChange = vi.fn();
    render(<Harness catalog={served} onChange={onChange} />);
    open();
    const wear = box(/^Operating wear --operating-wear$/);
    const timber = box(/^Timber supply --timber-supply$/);
    const crews = box(/^Recovery crews --recovery-crews$/);
    const obligation = box(/^Maintenance obligation --maintenance-obligation$/);
    for (const control of [wear, timber, crews, obligation]) {
      expect(control.checked).toBe(false);
      expect(control.disabled).toBe(true);
    }
    for (const mode of [/Timber supply mode/, /Recovery crew mode/, /Maintenance obligation mode/]) {
      expect(screen.queryByRole("combobox", { name: mode })).toBeNull();
    }
    expect(description(wear)).toMatch(/Unavailable: requires --workshops\.$/);   // an unset mode is its default, operate
    expect(description(timber)).toMatch(/Unavailable: requires --repair-projects; requires --timber-stock\./);
    expect(description(crews)).toMatch(/Unavailable: requires --repair-projects\./);
    expect(description(obligation)).toMatch(/Unavailable: requires --local-budgets; requires --repair-projects\./);

    fireEvent.click(box(/^Workshops --workshops$/));
    expect(wear.disabled).toBe(false);
    fireEvent.click(box(/^Repair projects --repair-projects$/));
    expect(crews.disabled).toBe(false);
    expect(timber.disabled).toBe(true);                                   // still needs the timber stock
    expect(description(timber)).toMatch(/Unavailable: requires --timber-stock\./);
    fireEvent.click(box(/^Timber stock --timber-stock$/));
    expect(timber.disabled).toBe(false);
    expect(obligation.disabled).toBe(true);
    fireEvent.click(box(/^Grain reserves --grain-reserves$/));
    fireEvent.click(box(/^Local budgets --local-budgets$/));
    expect(obligation.disabled).toBe(false);
    for (const control of [wear, timber, crews, obligation]) fireEvent.click(control);
    const modes: Array<[RegExp, string[]]> = [[/Timber supply mode/, ["supply (default)", "cost_only"]],
      [/Recovery crew mode/, ["paid (default)", "unpaid"]], [/Maintenance obligation mode/, ["reserve (default)", "reserve_only"]]];
    for (const [name, options] of modes) {
      const select = screen.getByRole("combobox", { name }) as HTMLSelectElement;
      expect([...select.options].map((option) => option.textContent)).toEqual(options);
      fireEvent.change(select, { target: { value: options[1] } });
    }
    expect(onChange).toHaveBeenLastCalledWith({ workshops: true, repair_projects: true, timber_stock: true,
      grain_reserves: true, local_budgets: true, operating_wear: true, timber_supply: true, recovery_crews: true,
      maintenance_obligation: true, timber_supply_mode: "cost_only", recovery_crew_mode: "unpaid",
      maintenance_obligation_mode: "reserve_only" });
    expect(screen.getByText(/--timber-supply-mode=cost_only/)).toBeTruthy();

    // Dropping a prerequisite drops what depends on it, and its mode.
    fireEvent.click(box(/^Timber stock --timber-stock$/));
    expect(timber.checked).toBe(false);
    expect(screen.queryByRole("combobox", { name: /Timber supply mode/ })).toBeNull();
    fireEvent.click(box(/^Grain reserves --grain-reserves$/));
    expect(obligation.checked).toBe(false);
    fireEvent.click(box(/^Repair projects --repair-projects$/));
    expect(crews.checked).toBe(false);
    expect(wear.checked).toBe(true);
    fireEvent.click(box(/^Workshops --workshops$/));
    expect(onChange).toHaveBeenLastCalledWith({});
  });

  it("offers household retail off, disabled until food allocation, with its mode and boundary (PL5b)", () => {
    const onChange = vi.fn();
    render(<Harness catalog={served} onChange={onChange} />);
    open();
    const retail = box(/^Household retail --household-retail$/);
    expect(retail.checked).toBe(false);
    expect(retail.disabled).toBe(true);
    expect(description(retail)).toMatch(/Unavailable: requires --food-allocation\.$/);
    for (const name of [/Household retail mode/, /Household retail boundary/]) expect(screen.queryByRole("combobox", { name })).toBeNull();
    fireEvent.click(box(/^Food allocation --food-allocation$/));
    expect(retail.disabled).toBe(false);
    fireEvent.click(retail);
    const mode = screen.getByRole("combobox", { name: /Household retail mode --household-retail-mode/ }) as HTMLSelectElement;
    const boundary = screen.getByRole("combobox", { name: /Household retail boundary --household-retail-boundary/ }) as HTMLSelectElement;
    expect([...mode.options].map((o) => o.textContent)).toEqual(["retail (default)", "no_relief", "free_exchange", "record_only"]);
    expect([...boundary.options].map((o) => o.textContent)).toEqual(["market (default)", "paid_work", "all"]);
    expect(onChange).toHaveBeenLastCalledWith({ food_allocation: true, household_retail: true });
    fireEvent.change(mode, { target: { value: "record_only" } });
    fireEvent.change(boundary, { target: { value: "paid_work" } });
    expect(onChange).toHaveBeenLastCalledWith({ food_allocation: true, household_retail: true,
      household_retail_mode: "record_only", household_retail_boundary: "paid_work" });
    expect(screen.getByText(/--household-retail-mode=record_only/)).toBeTruthy();
    // Dropping food allocation drops the switch and both options.
    fireEvent.click(box(/^Food allocation --food-allocation$/));
    expect(retail.checked).toBe(false);
    expect(screen.queryByRole("combobox", { name: /Household retail mode/ })).toBeNull();
    expect(onChange).toHaveBeenLastCalledWith({});
  });

  it("offers RS1's rules version under apprenticeship, version 2 by default, sent only when changed", () => {
    const onChange = vi.fn();
    render(<Harness catalog={served} onChange={onChange} />);
    open();
    expect(screen.queryByRole("combobox", { name: /Apprenticeship rules/ })).toBeNull();
    fireEvent.click(box(/^Workshops --workshops$/));
    fireEvent.click(box(/^Apprenticeship --apprenticeship$/));
    const rules = screen.getByRole("combobox", { name: /Apprenticeship rules --apprenticeship-rules/ }) as HTMLSelectElement;
    expect([...rules.options].map((option) => option.textContent)).toEqual(["2 (default)", "1"]);
    expect(onChange).toHaveBeenLastCalledWith({ workshops: true, apprenticeship: true });
    fireEvent.change(rules, { target: { value: "1" } });
    expect(onChange).toHaveBeenLastCalledWith({ workshops: true, apprenticeship: true, apprenticeship_rules: "1" });
    expect(screen.getByText(/--apprenticeship-rules=1/)).toBeTruthy();
    fireEvent.click(box(/^Workshops --workshops$/));
    expect(onChange).toHaveBeenLastCalledWith({});
    expect(screen.queryByRole("combobox", { name: /Apprenticeship rules/ })).toBeNull();
  });

  it("disables everything with the reason when requests are unavailable", () => {
    render(<Harness catalog={served} unavailable="Feature options apply to new worlds only." />);
    open();
    expect(screen.getByRole("note").textContent).toBe("Feature options apply to new worlds only.");
    for (const checkbox of screen.getAllByRole("checkbox")) expect((checkbox as HTMLInputElement).disabled).toBe(true);
  });
});
