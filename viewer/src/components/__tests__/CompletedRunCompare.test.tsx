/// <reference types="node" />
import { createHash, webcrypto } from "node:crypto";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { CompletedRunCompare } from "../CompletedRunCompare";
import { BatchCompare } from "../BatchCompare";
import { comparisonBundle } from "../../__fixtures__/completedRunHistory";
import manifest from "../../__fixtures__/bundle_v2/small/manifest.json";
import type { BatchReport } from "../../types";
import { recipeManifest, whatIfPair } from "../../__fixtures__/whatIf";

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
  await screen.findByRole("table", { name: /Run metrics at snapshot/ });
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
  await screen.findByRole("table", { name: /Run metrics at snapshot/ });
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
  await screen.findByRole("table", { name: /Run metrics at snapshot/ });
  fireEvent.click(screen.getByRole("button", { name: "Batch reports" }));
  expect(screen.getByText("Baseline")).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "Completed runs" }));
  expect(screen.getByText("left.json")).toBeVisible();
  expect(screen.getByRole("table", { name: /Run metrics at snapshot/ })).toBeVisible();
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
  expect(screen.getByRole("table", { name: /Run metrics at snapshot/ })).toBeVisible();
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

it("exports only portable provenance/settings and labels a global policy pair without claiming stability", async () => {
  const manifest = { ...recipeManifest(), schema_version: 2 as const,
    intervention: { command: "set" as const, civ: "@world" as const, stat: "grain_reserves.shortfall_priority" as const,
      scope: "world" as const, before: 0 as const, value: 1 as const } };
  const pair = { ...whatIfPair, manifest,
    baseline: { ...whatIfPair.baseline, bundle: comparisonBundle(), label: "Unchanged continuation" },
    intervention: { ...whatIfPair.intervention, bundle: comparisonBundle(), label: "Global granary priority intervention" } };
  for (const [arm, run] of [["baseline", pair.baseline], ["intervention", pair.intervention]] as const) {
    (run.bundle.metadata as unknown as Record<string, unknown>).what_if = { ...manifest, arm };
  }
  const writeText = vi.fn().mockResolvedValue(undefined);
  Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText } });
  const makeUrl = vi.fn<(blob: Blob) => string>(() => "blob:portable-summary");
  Object.defineProperty(URL, "createObjectURL", { configurable: true, writable: true, value: makeUrl });
  Object.defineProperty(URL, "revokeObjectURL", { configurable: true, writable: true, value: vi.fn() });
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
  render(<CompletedRunCompare initialPair={pair} />);
  const scrollRegion = screen.getByRole("region", { name: "Scrollable run metrics" });
  scrollRegion.focus();
  expect(scrollRegion).toHaveFocus();
  expect(screen.getByLabelText("What-if provenance")).toHaveTextContent("World granary priority");
  expect(screen.getByLabelText("What-if provenance")).not.toHaveTextContent("stability");
  fireEvent.click(screen.getByRole("button", { name: "Copy Markdown" }));
  await waitFor(() => expect(writeText).toHaveBeenCalledOnce());
  const markdown = writeText.mock.calls[0][0] as string;
  expect(markdown).toContain('"schema_version": 2');
  expect(markdown).toContain("grain_reserves.shortfall_priority");
  expect(markdown).not.toContain("PRIVATE_TOKEN");
  expect(markdown).not.toContain("/private/");
  fireEvent.click(screen.getByRole("button", { name: "Download JSON" }));
  const blob = makeUrl.mock.calls[0][0] as unknown as Blob;
  const json = await new Promise<string>((resolve) => {
    const reader = new FileReader(); reader.onload = () => resolve(String(reader.result)); reader.readAsText(blob);
  });
  expect(json).not.toContain("PRIVATE_TOKEN");
  expect(json).not.toContain("/private/");
  expect(JSON.parse(json).what_if.intervention.scope).toBe("world");
  expect(JSON.parse(json).inputs.left.settings.configuration.scenario).toBe("world.yaml");
  expect(screen.getByLabelText("What-if provenance")).toBeVisible();
});

it("exports readable regional transport provenance without the encoded backend command", async () => {
  const manifest = { ...recipeManifest(), schema_version: 3 as const,
    intervention: { command: "set" as const, civ: "@transport" as const, stat: "lab.transport_disruption" as const,
      before: 0, value: 12, scope: "region" as const, region_id: 1, region_name: "B", duration: 2,
      prior_counter: 0, effective_counter: 3, effective_through_turn: 3 } };
  const pair = { ...whatIfPair, manifest, baseline: { ...whatIfPair.baseline, bundle: comparisonBundle() },
    intervention: { ...whatIfPair.intervention, bundle: comparisonBundle() } };
  for (const [arm, run] of [["baseline", pair.baseline], ["intervention", pair.intervention]] as const)
    (run.bundle.metadata as unknown as Record<string, unknown>).what_if = { ...manifest, arm };
  const writeText = vi.fn().mockResolvedValue(undefined);
  Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText } });
  const makeUrl = vi.fn<(blob: Blob) => string>(() => "blob:transport-summary");
  Object.defineProperty(URL, "createObjectURL", { configurable: true, writable: true, value: makeUrl });
  Object.defineProperty(URL, "revokeObjectURL", { configurable: true, writable: true, value: vi.fn() });
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
  render(<CompletedRunCompare initialPair={pair} />);
  expect(screen.getByLabelText("What-if provenance")).toHaveTextContent("B (#1), 2 turns");
  fireEvent.click(screen.getByRole("button", { name: "Copy Markdown" }));
  await waitFor(() => expect(writeText).toHaveBeenCalledOnce());
  const markdown = writeText.mock.calls[0][0] as string;
  expect(markdown).toContain('"region_id": 1');
  expect(markdown).not.toContain('"value": 12');
  expect(markdown).not.toContain("lab.transport_disruption");
  expect(markdown).not.toContain("PRIVATE_TOKEN");
  fireEvent.click(screen.getByRole("button", { name: "Download JSON" }));
  const json = await new Promise<string>((resolve) => { const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result)); reader.readAsText(makeUrl.mock.calls[0][0]); });
  expect(JSON.parse(json).what_if.intervention).toMatchObject({ region_id: 1, duration: 2, effective_counter: 3 });
  expect(json).not.toContain('"value": 12'); expect(json).not.toContain("lab.transport_disruption");
});
