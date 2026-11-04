import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { webcrypto } from "node:crypto";
import { CompletedRunCompare } from "../CompletedRunCompare";
import { AcademyRunComparison } from "../AcademyRunComparison";
import { clearComparisonGallery, gallerySnapshot, GALLERY_LIMIT, keepComparison } from "../../lib/comparisonGallery";
import { comparisonBundle } from "../../__fixtures__/completedRunHistory";
import { whatIfPair } from "../../__fixtures__/whatIf";
import type { Bundle, SeatRecord } from "../../types";
import type { LearningServicesSnapshot } from "../../learningServicesTypes";

vi.mock("recharts", () => ({ ResponsiveContainer: () => null, CartesianGrid: () => null,
  Legend: () => null, Line: () => null, LineChart: () => null, Tooltip: () => null, XAxis: () => null, YAxis: () => null }));
beforeEach(() => { clearComparisonGallery(); vi.stubGlobal("crypto", webcrypto); });
afterEach(() => { cleanup(); clearComparisonGallery(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });
const run = (bundle: Bundle) => ({ bundle, identity: null, label: "Constructed test fixture" });
it("keeps a real supplied pair and reopens its snapshot and provenance after replacing an input", async () => {
  render(<CompletedRunCompare initialPair={whatIfPair} />);
  fireEvent.change(screen.getByLabelText("Comparison snapshot"), { target: { value: "2" } });
  fireEvent.change(screen.getByLabelText("Gallery case label"), { target: { value: "Receiving service interruption" } });
  fireEvent.click(screen.getByRole("button", { name: "Keep this comparison" }));
  const card = screen.getByRole("article", { name: /Gallery case/ });
  expect(card).toHaveTextContent("Receiving service interruption");
  expect(card).toHaveTextContent("Starting snapshot precedes the intervention");
  const file = new File([JSON.stringify(comparisonBundle())], "replacement.json");
  fireEvent.change(screen.getByLabelText("Load left run"), { target: { files: [file] } });
  await screen.findByText("replacement.json");
  expect(screen.queryByLabelText("What-if provenance")).not.toBeInTheDocument();
  fireEvent.click(within(card).getByRole("button", { name: /Open case/ }));
  expect(screen.getByLabelText("What-if provenance")).toHaveTextContent("60 → 80");
  expect(screen.getByLabelText("Comparison snapshot")).toHaveValue("2");
  expect(screen.queryByText("replacement.json")).not.toBeInTheDocument();
});
it("retains session cases across modal unmount and makes incomplete data explicit", () => {
  const a = run(comparisonBundle([1, 3])), b = run(comparisonBundle([1, 2]));
  keepComparison(a, b, 3, null);
  const view = render(<CompletedRunCompare />);
  const card = screen.getByRole("article", { name: /Gallery case/ });
  expect(card).toHaveTextContent("Left 100 · Right Not recorded · Δ Not recorded");
  expect(card).toHaveTextContent("right Not recorded");
  view.unmount();
  render(<CompletedRunCompare />);
  fireEvent.click(screen.getByRole("button", { name: /Open case/ }));
  expect(screen.getByRole("table", { name: "Run metrics at snapshot 3" })).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: /Remove case/ }));
  expect(screen.queryByRole("article", { name: /Gallery case/ })).not.toBeInTheDocument();
  expect(screen.getByRole("table", { name: "Run metrics at snapshot 3" })).toBeInTheDocument();
});
it("bounds retained inputs without silently evicting cases or duplicating an identical snapshot", () => {
  const a = run(comparisonBundle()), b = run(comparisonBundle());
  expect(keepComparison(a, b, 1, null)).toContain("kept");
  expect(keepComparison(a, b, 1, null)).toContain("already");
  for (let i = 1; i < GALLERY_LIMIT; i++) keepComparison(run(comparisonBundle()), b, 1, null);
  const first = gallerySnapshot()[0];
  expect(keepComparison(run(comparisonBundle()), b, 1, null)).toContain("full");
  expect(gallerySnapshot()).toHaveLength(GALLERY_LIMIT);
  expect(gallerySnapshot()[0]).toBe(first);
});
it("invalidates an outstanding file read when a gallery case is reopened", async () => {
  keepComparison(whatIfPair.baseline, whatIfPair.intervention, 2, whatIfPair);
  render(<CompletedRunCompare initialPair={whatIfPair} />);
  let release!: (bytes: ArrayBuffer) => void;
  const pending = new File(["{}"], "late.json");
  vi.spyOn(pending, "arrayBuffer").mockReturnValue(new Promise((resolve) => { release = resolve; }));
  fireEvent.change(screen.getByLabelText("Load left run"), { target: { files: [pending] } });
  fireEvent.click(screen.getByRole("button", { name: /Open case/ }));
  release(new TextEncoder().encode(JSON.stringify(comparisonBundle())).buffer);
  await waitFor(() => expect(screen.queryByText("Reading run…")).not.toBeInTheDocument());
  expect(screen.queryByText("late.json")).not.toBeInTheDocument();
  expect(screen.getByLabelText("What-if provenance")).toBeInTheDocument();
});
/** Constructed contract data; these tests are not simulation evidence. */
function serviceBundle() {
  const bundle = comparisonBundle([5]);
  const id = { seat_id: 0, region: 0, founder: 0, founded_turn: 1, seat_name: "Test academy" };
  const seat = { region: 0, kind: 0, name: id.seat_name, founded_turn: 1, founder: 0,
    level: 1, peak_level: 1, peak_scholars: 1, fallen_turn: null, fall_cause: -1, refuge: -1, history: [] } as SeatRecord;
  bundle.world_state.scholarship = { seats: [seat] };
  const frame: LearningServicesSnapshot = { schema_version: 1, captured_turn: 5, enabled: true, active: true,
    inventories: [], supply_losses: [], totals: {},
    procurement_receipts: [{ ...id, lord: 0, source_turn: 4, upkeep_source_turn: 4, upkeep_due: 0,
      upkeep_amount_paid: 0, upkeep_satisfied: true, scholar_upper_bound: 3, learner_upper_bound: 16, craft_price: 1,
      market_stock: 0, market_commitments: 0, budget_before: 10, held_before: 0, purchased: 0, paid: 0,
      held_after: 0, shortfalls: ["market_stock"] }],
    teaching_receipts: [{ ...id, lord: 0, source_turn: 4, available_turn: 5, learner_upper_bound: 16,
      scholar_upper_bound: 3, upkeep_source_turn: 3, upkeep_lord: 0, upkeep_due: 0, upkeep_amount_paid: 0,
      upkeep_satisfied: true, upkeep_applies: true, held_before: 0, work_requested: 0,
      work_available: null, work_reserved: null, work_delivered: null, learners_delivered: null,
      crafts_used: null, held_after: 0, native_dropped: null }] };
  bundle.history[0].scholarship = { seats: [], fallen: 0, counters: {}, learning_services: frame };
  return { bundle, frame };
}
it("shows zero purchases and requests separately from unobserved native delivery", () => {
  const { bundle } = serviceBundle();
  render(<AcademyRunComparison left={run(bundle)} right={run(comparisonBundle([5]))} turn={5} />);
  const table = screen.getByRole("region", { name: "Academy supplies and service comparison" });
  expect(table).toHaveTextContent("Crafts bought: 0 · Treasury paid: 0");
  expect(table).toHaveTextContent("Requested: 0 · Delivered: Not observed scholar-days");
  expect(table).toHaveTextContent("Potential learners (upper bound): 16");
  expect(table).toHaveTextContent("market stock");
  expect(table).toHaveTextContent("No validated academy receipts at this exact snapshot");
});
it("excludes future/malformed or ambiguous receipts while labeling retained inactive dates", () => {
  const { bundle, frame } = serviceBundle();
  frame.teaching_receipts![0].source_turn = 5;
  const view = render(<AcademyRunComparison left={run(bundle)} right={run(comparisonBundle([5]))} turn={5} />);
  expect(screen.getByText(/Work source tick: Not observed/)).toBeInTheDocument();
  frame.active = false;
  Object.assign(frame.teaching_receipts![0], { source_turn: 3, available_turn: 4 });
  view.rerender(<AcademyRunComparison left={run(bundle)} right={run(comparisonBundle([5]))} turn={5} />);
  expect(screen.getByText(/Service paused or unavailable; retained receipts keep their source dates/)).toBeInTheDocument();
  expect(screen.getByText(/Work source tick: 3/)).toBeInTheDocument();
  bundle.history.push(structuredClone(bundle.history[0]));
  view.rerender(<AcademyRunComparison left={run(bundle)} right={run(comparisonBundle([5]))} turn={5} />);
  expect(screen.queryByRole("region", { name: "Academy supplies and service comparison" })).not.toBeInTheDocument();
});
