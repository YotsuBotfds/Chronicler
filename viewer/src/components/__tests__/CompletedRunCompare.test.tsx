/// <reference types="node" />
import { createHash, webcrypto } from "node:crypto";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { CompletedRunCompare } from "../CompletedRunCompare";
import { BatchCompare } from "../BatchCompare";
import { comparisonBundle } from "../../__fixtures__/completedRunHistory";
import manifest from "../../__fixtures__/bundle_v2/small/manifest.json";
import type { BatchReport } from "../../types";

// The data/clock/gap contracts are tested in the library suite. Avoid jsdom layout warnings.
vi.mock("recharts", () => ({
  ResponsiveContainer: () => <div data-testid="trajectory-chart" />,
  CartesianGrid: () => null, Legend: () => null, Line: () => null, LineChart: () => null,
  Tooltip: () => null, XAxis: () => null, YAxis: () => null, AreaChart: () => null, Area: () => null,
}));

beforeEach(() => vi.stubGlobal("crypto", webcrypto));
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

function upload(side: "left" | "right", name: string, data: unknown) {
  const text = typeof data === "string" ? data : JSON.stringify(data);
  const file = new File([text], name, { type: "application/json" });
  fireEvent.change(screen.getByLabelText(`Load ${side} run`), { target: { files: [file] } });
  return text;
}

it("keeps the initial bundle, loads the other side through the shared decoder and displays both byte identities", async () => {
  render(<CompletedRunCompare initialBundle={comparisonBundle([1, 2])} initialIdentity={{ name: "right.json", byteLength: 17, sha256: "b".repeat(64) }} />);
  const raw = upload("left", "left.json", comparisonBundle([1, 2]));
  const hash = createHash("sha256").update(raw).digest("hex");
  expect(await screen.findByText(hash)).toBeInTheDocument();
  expect(screen.getByText("b".repeat(64))).toBeInTheDocument();
  const table = screen.getByRole("table", { name: "Run metrics at snapshot 2" });
  expect(within(table).getByRole("row", { name: /Landholding population 100 100 0/ })).toBeInTheDocument();
  expect(screen.getByText(/Equal seeds do not establish a controlled experiment/)).toBeInTheDocument();
  expect(within(screen.getByRole("region", { name: "Left run" })).getAllByText("Not recorded").length).toBeGreaterThan(0);
});

it("shows null tails and preserves both loaded runs across unsupported, malformed, and repeated type-error loads", async () => {
  render(<CompletedRunCompare initialBundle={comparisonBundle([1, 2])} />);
  upload("left", "left.json", comparisonBundle([1, 3]));
  await screen.findByRole("table");
  fireEvent.change(screen.getByLabelText("Comparison snapshot"), { target: { value: "3" } });
  expect(screen.getByRole("row", { name: /Landholding population 100 Not recorded Not recorded/ })).toBeInTheDocument();
  upload("left", "manifest.json", manifest);
  expect(await screen.findByRole("alert")).toHaveTextContent("not active");
  expect(screen.getByText("left.json")).toBeInTheDocument();
  upload("right", "bad.json", "{broken");
  await waitFor(() => expect(screen.getAllByRole("alert")).toHaveLength(2));
  expect(screen.getByText("Current viewer bundle")).toBeInTheDocument();
  for (let i = 0; i < 2; i++) {
    const file = new File(["{}"], "read-error.json");
    vi.spyOn(file, "arrayBuffer").mockRejectedValue(new TypeError("Fixture read failure"));
    fireEvent.change(screen.getByLabelText("Load right run"), { target: { files: [file] } });
    await waitFor(() => expect(screen.getAllByRole("alert")[1]).toHaveTextContent("Fixture read failure"));
  }
  expect(screen.getByRole("table", { name: "Run metrics at snapshot 3" })).toBeInTheDocument();
});

it("ignores stale uploads on the same side without canceling the other input", async () => {
  render(<CompletedRunCompare initialBundle={comparisonBundle()} />);
  let release!: (bytes: ArrayBuffer) => void;
  const pending = new File(["{}"], "old.json");
  vi.spyOn(pending, "arrayBuffer").mockReturnValue(new Promise((resolve) => { release = resolve; }));
  fireEvent.change(screen.getByLabelText("Load left run"), { target: { files: [pending] } });
  upload("left", "new.json", comparisonBundle());
  await screen.findByText("new.json");
  release(new TextEncoder().encode(JSON.stringify(comparisonBundle([1]))).buffer);
  await waitFor(() => expect(screen.queryByText("Reading run…")).not.toBeInTheDocument());
  expect(screen.queryByText("old.json")).not.toBeInTheDocument();
  expect(screen.getByText("Current viewer bundle")).toBeInTheDocument();
});

it("copies a concise summary with inputs, settings, coverage and limits and offers local downloads", async () => {
  const writeText = vi.fn().mockResolvedValue(undefined);
  Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText } });
  const create = vi.fn().mockReturnValue("blob:fixture");
  const revoke = vi.fn();
  Object.defineProperty(URL, "createObjectURL", { configurable: true, value: create });
  Object.defineProperty(URL, "revokeObjectURL", { configurable: true, value: revoke });
  const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
  render(<CompletedRunCompare initialBundle={comparisonBundle()} />);
  upload("left", "left.json", comparisonBundle());
  await screen.findByRole("table");
  fireEvent.click(screen.getByRole("button", { name: "Copy Markdown" }));
  await waitFor(() => expect(writeText).toHaveBeenCalled());
  expect(writeText.mock.calls[0][0]).toContain("SHA-256 (original bytes)");
  expect(writeText.mock.calls[0][0]).toContain("Recorded settings");
  expect(writeText.mock.calls[0][0]).toContain("Recorded snapshots left / right");
  expect(writeText.mock.calls[0][0]).toContain("not a population-weighted measure");
  fireEvent.click(screen.getByRole("button", { name: "Download JSON" }));
  fireEvent.click(screen.getByRole("button", { name: "Download Markdown" }));
  expect(create).toHaveBeenCalledTimes(2); expect(click).toHaveBeenCalledTimes(2);
});

it("retains the completed-run inputs when switching to existing batch reports and back", async () => {
  render(<BatchCompare initialBundle={comparisonBundle()} />);
  upload("left", "left.json", comparisonBundle());
  await screen.findByRole("table");
  fireEvent.click(screen.getByRole("button", { name: "Batch reports" }));
  expect(screen.getByText("Baseline")).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "Completed runs" }));
  expect(screen.getByText("left.json")).toBeVisible();
  expect(screen.getByRole("table")).toBeVisible();
});

it("keeps the existing batch report mode and rejects a bundle dropped into it without replacing a report", async () => {
  const report = { metadata: { runs: 1, turns_per_run: 3, seed_range: [42, 42], timestamp: "2026-11-01" },
    stability: { percentiles_by_turn: {} }, event_firing_rates: {}, anomalies: [] } as unknown as BatchReport;
  render(<BatchCompare initialRight={report} />);
  expect(screen.getByRole("button", { name: "Batch reports" })).toHaveAttribute("aria-pressed", "true");
  expect(screen.getByText("Seeds: 42-42")).toBeVisible();
  const file = new File([JSON.stringify(comparisonBundle())], "bundle.json", { type: "application/json" });
  fireEvent.drop(screen.getByText("Drop batch_report.json or click to load"), { dataTransfer: { files: [file] } });
  expect(await screen.findByRole("alert")).toHaveTextContent("choose Completed runs");
  expect(screen.getByText("Seeds: 42-42")).toBeVisible();
});

it("loads a completed bundle by drop and reports clipboard failure without losing the summary", async () => {
  Object.defineProperty(navigator, "clipboard", { configurable: true,
    value: { writeText: vi.fn().mockRejectedValue(new Error("Clipboard denied")) } });
  render(<CompletedRunCompare initialBundle={comparisonBundle()} />);
  const file = new File([JSON.stringify(comparisonBundle())], "dropped.json", { type: "application/json" });
  fireEvent.drop(screen.getByRole("region", { name: "Left run" }), { dataTransfer: { files: [file] } });
  await screen.findByText("dropped.json");
  fireEvent.click(screen.getByRole("button", { name: "Copy Markdown" }));
  expect(await screen.findByText("Copy is unavailable here. Download the summary instead.")).toBeVisible();
  expect(screen.getByRole("button", { name: "Download JSON" })).toBeEnabled();
  expect(screen.getByRole("table")).toBeVisible();
});

it("opens an exact pair through the existing comparison and shares its full provenance until a side is replaced", async () => {
  const { whatIfPair } = await import("../../__fixtures__/whatIf");
  const writeText = vi.fn().mockResolvedValue(undefined);
  Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText } });
  render(<CompletedRunCompare initialPair={whatIfPair} />);
  expect(screen.getByLabelText("What-if provenance")).toHaveTextContent("60 → 80");
  fireEvent.click(screen.getByRole("button", { name: "Copy Markdown" }));
  await waitFor(() => expect(writeText).toHaveBeenCalledOnce());
  expect(writeText.mock.calls[0][0]).toContain('"semantics": "exact_checkpoint_pair"');
  upload("left", "replacement.json", comparisonBundle());
  await screen.findByText("replacement.json");
  expect(screen.queryByLabelText("What-if provenance")).not.toBeInTheDocument();
});
