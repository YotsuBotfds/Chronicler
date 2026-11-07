import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen, within } from "@testing-library/react";
import type { Bundle, TurnSnapshot } from "../../../types";
import { EpidemicCare } from "../EpidemicCare";
import FIXTURE from "../../../__fixtures__/epidemicCare.json";

afterEach(cleanup);

const clone = <T,>(x: T): T => JSON.parse(JSON.stringify(x)) as T;
const snap = (turn: number, care?: unknown) =>
  ({ turn, livelihoods: care === undefined ? { schema_version: 1 } : { schema_version: 1, epidemic_care: care } }) as unknown as TurnSnapshot;
const bundle = (history: TurnSnapshot[]) => ({
  history,
  world_state: { regions: FIXTURE.regions.map((name) => ({ name })), civilizations: FIXTURE.civilizations.map((name) => ({ name })) },
}) as unknown as Bundle;
const T = FIXTURE.recorded.turn;

describe("EpidemicCare", () => {
  it("renders nothing in a run without the switch", () => {
    const b = bundle([snap(1), snap(2)]);
    const { container } = render(<EpidemicCare bundle={b} snapshot={b.history[1]} currentTurn={2} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("shows carers, capacity, coverage, the fatality factor and wages per region", () => {
    const s = snap(T, clone(FIXTURE.recorded.record));
    render(<EpidemicCare bundle={bundle([s])} snapshot={s} currentTurn={T} />);
    const section = screen.getByRole("region", { name: `Epidemic care at turn ${T}` });
    expect(within(section).getByText("Care (lowers case fatality)")).toBeInTheDocument();
    const table = within(section).getByRole("table", { name: `Epidemic care by region at turn ${T}` });
    const rows = within(table).getAllByRole("row");
    expect(rows.length).toBeGreaterThan(2);
    expect(within(table).getAllByText("0.700").length).toBeGreaterThan(0);          // 1 - 0.3 x full coverage
    expect(within(table).getAllByText("need covered").length).toBeGreaterThan(0);
  });

  it("names an absent snapshot, a malformed record and an unobserved turn, never zero", () => {
    const good = snap(T, clone(FIXTURE.recorded.record));
    const b = bundle([good, snap(T + 1)]);
    const { unmount } = render(<EpidemicCare bundle={b} snapshot={b.history[1]} currentTurn={T + 1} />);
    expect(screen.getByText(/has no record; unknown, not zero/)).toBeInTheDocument();
    unmount();
    const bad = snap(T, { ...clone(FIXTURE.recorded.record), source_turn: 0 });
    const r2 = render(<EpidemicCare bundle={b} snapshot={bad} currentTurn={T} />);
    expect(screen.getByRole("alert")).toHaveTextContent(/rejected as malformed/);
    r2.unmount();
    const unobserved = snap(T, { ...clone(FIXTURE.recorded.record), tick: null });
    render(<EpidemicCare bundle={b} snapshot={unobserved} currentTurn={T} />);
    const tile = screen.getByText("Regions covered at the tick").parentElement!;
    expect(within(tile).getByText("not observed")).toBeInTheDocument();
  });

  it("shows a recorded zero as zero with its meaning", () => {
    const z = snap(FIXTURE.recorded_zero.turn, clone(FIXTURE.recorded_zero.record));
    const b = bundle([snap(T, clone(FIXTURE.recorded.record)), z]);
    render(<EpidemicCare bundle={b} snapshot={z} currentTurn={z.turn} />);
    expect(screen.getByText(/nothing happened this turn \(no care capacity reached/)).toBeInTheDocument();
    const tile = screen.getByText("Carers named").parentElement!;
    expect(within(tile).getByText("0")).toBeInTheDocument();
    expect(screen.queryByRole("table")).toBeNull();
  });

  it("labels cost only and shows the factor it did not apply", () => {
    const record = clone(FIXTURE.recorded.record) as Record<string, unknown>;
    record.mode = "cost_only";
    const tick = record.tick as { applied: Record<string, unknown>[] };
    for (const row of tick.applied) {
      row.care_factor = 1;
      row.combined_factor = row.techniques_factor ?? 1;
    }
    const s = snap(T, record);
    render(<EpidemicCare bundle={bundle([s])} snapshot={s} currentTurn={T} />);
    expect(screen.getByText("Cost only (no effect on fatality)")).toBeInTheDocument();
    expect(screen.getByText("Factor (not applied)")).toBeInTheDocument();
  });
});

describe("EpidemicCare payment refusal", () => {
  it("names a bill refused at payment instead of showing wages", () => {
    const record = clone(FIXTURE.recorded.record) as { frame: Record<string, unknown>[] };
    const staffed = record.frame.find((row) => (row.carers as unknown[]).length > 0)!;
    staffed.paid = false;
    staffed.unpaid_reason = "payer_short";
    const s = snap(T, record);
    render(<EpidemicCare bundle={bundle([s])} snapshot={s} currentTurn={T} />);
    expect(screen.getByText("unpaid (payer short)")).toBeInTheDocument();
  });
});
