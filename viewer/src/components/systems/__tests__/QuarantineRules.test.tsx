import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen, within } from "@testing-library/react";
import { QuarantineRules } from "../QuarantineRules";
import { AGGREGATE_CLOSURE_RECORD, quarantineRecord } from "../../../__fixtures__/quarantineRules";

afterEach(cleanup);

const section = () => screen.getByRole("region", { name: "Quarantine rule at turn 8" });

describe("QuarantineRules", () => {
  it("names an unknown turn, never a rule", () => {
    render(<QuarantineRules epidemics={undefined} at={8} />);
    expect(within(section()).getByText(/Unknown: there is no epidemiology record/)).toBeInTheDocument();
    expect(within(section()).queryByText(/Legacy multiplier|Closure/)).toBeNull();
  });

  it("labels the legacy multiplier separately from a closure", () => {
    render(<QuarantineRules epidemics={{ active: [], quarantine: ["Kethani Empire"] }} at={8} />);
    expect(within(section()).getByText("Legacy multiplier")).toBeInTheDocument();
    expect(within(section()).getByText(/no route or journey is closed/)).toBeInTheDocument();
    expect(within(section()).queryByText("Closure (trade closed)")).toBeNull();
  });

  it("reports a malformed record without showing its values", () => {
    render(<QuarantineRules epidemics={{ quarantine_rules: quarantineRecord({ mode: 7 }) }} at={8} />);
    expect(within(section()).getByRole("alert")).toHaveTextContent("malformed (unknown mode 7)");
    expect(within(section()).queryByText("Merchant edges cut")).toBeNull();
  });

  it("shows a closure's receipt, closures and exemptions", () => {
    render(<QuarantineRules epidemics={{ quarantine_rules: quarantineRecord() }} at={8} />);
    const s = section();
    expect(within(s).getByText("Closure (trade closed)")).toBeInTheDocument();
    expect(within(s).getByText("Receipt of simulation turn 5.")).toBeInTheDocument();
    const table = within(s).getByRole("table", { name: "Quarantine closures at turn 8" });
    expect(within(table).getAllByRole("row")).toHaveLength(4);
    expect(within(table).getAllByText("Selurian Republic").length).toBeGreaterThan(0);
    expect(within(s).getByText(/relief grain shipments and convoys/)).toBeInTheDocument();
    const tile = within(s).getByText("Merchant edges cut").parentElement!;
    expect(within(tile).getByText("4")).toBeInTheDocument();
  });

  it("names the aggregate run's missing merchant graph as not applicable", () => {
    render(<QuarantineRules epidemics={{ quarantine_rules: AGGREGATE_CLOSURE_RECORD }} at={8} />);
    expect(within(section()).getByText("not applicable")).toBeInTheDocument();
    expect(within(section()).getByText("no agent merchant graph this turn")).toBeInTheDocument();
  });

  it("keeps a recorded zero, a value not recorded and an unrestricted mode distinct", () => {
    const receipt = quarantineRecord().receipt as Record<string, unknown>;
    const { unmount } = render(<QuarantineRules epidemics={{ quarantine_rules: quarantineRecord({
      closures: [], receipt: { ...receipt, decided: [], merchant_edges_removed: null, leaked_deliveries: null },
      totals: { ...(quarantineRecord().totals as object), closed_pair_turns: 0 } }) }} at={8} />);
    let s = section();
    expect(within(within(s).getByText("Open closures").parentElement!).getByText("0")).toBeInTheDocument();
    expect(within(s).getByText("not applicable")).toBeInTheDocument();
    expect(within(s).getByText("not recorded")).toBeInTheDocument();
    expect(within(s).getByText(/no closure \(recorded zero\)/)).toBeInTheDocument();
    unmount();
    render(<QuarantineRules epidemics={{ quarantine_rules: quarantineRecord({ mode: "cost_only", closures: [] }) }} at={8} />);
    s = section();
    expect(within(s).getByText("Cost only (nothing closed)")).toBeInTheDocument();
    expect(within(s).getAllByText("none (not restricted)").length).toBe(4);
  });
});
