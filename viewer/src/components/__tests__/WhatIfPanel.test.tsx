/// <reference types="node" />
import { webcrypto } from "node:crypto";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { WhatIfPanel } from "../WhatIfPanel";
import { InterventionPanel } from "../InterventionPanel";
import { createWhatIfRecipe, type WhatIfControls } from "../../lib/whatIf";
import type { PauseContext } from "../../types";
import { recipeManifest, whatIfManifest, whatIfPair } from "../../__fixtures__/whatIf";
import { comparisonBundle } from "../../__fixtures__/completedRunHistory";
const context: PauseContext = { turn: 2, reason: "interval", civs: ["A", "B"],
  valid_commands: ["what_if_prepare", "checkpoint", "continue", "set", "fork", "quit"], injectable_events: ["famine"], settable_stats: ["stability"] };
const controls = (): WhatIfControls => ({ status: null, connected: true, prepare: vi.fn(), preparePolicy: vi.fn(), run: vi.fn(), cancel: vi.fn() });
beforeEach(() => vi.stubGlobal("crypto", webcrypto));
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });
it("prepares only the named global binary policy, previews scope and preserves no-op controls", () => {
  const bundle = comparisonBundle();
  (bundle.world_state as unknown as Record<string, unknown>).agent_mode = "hybrid";
  (bundle.world_state as unknown as Record<string, unknown>).grain_reserves = { granaries: [] };
  const c = { ...controls(), bundle };
  render(<WhatIfPanel context={context} controls={c} onCompare={vi.fn()} />);
  fireEvent.change(screen.getByLabelText("What-if control"), { target: { value: "granary_shortfall_priority" } });
  expect(screen.getByText(/World scope: every existing public granary/)).toBeVisible();
  expect(screen.queryByLabelText("What-if civilization")).toBeNull();
  fireEvent.change(screen.getByLabelText("What-if granary priority"), { target: { value: "0" } });
  expect(screen.getByText(/no-op control/)).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "Prepare comparison" }));
  expect(c.preparePolicy).toHaveBeenCalledWith(0, 5);
  expect(c.prepare).not.toHaveBeenCalled();
  expect(c.run).not.toHaveBeenCalled();
});
it("keeps unsupported policy selection disabled without enabling a host feature", () => {
  render(<WhatIfPanel context={context} controls={controls()} onCompare={vi.fn()} />);
  expect(screen.getByRole("option", { name: "Global granary procurement priority" })).toBeDisabled();
  expect(screen.getByText(/requires hybrid mode and already-enabled public granaries/)).toBeVisible();
});
it("validates bounded inputs and labels an intervention before allowing execution", () => {
  const c = controls();
  const { rerender } = render(<WhatIfPanel context={context} controls={c} onCompare={vi.fn()} />);
  expect(screen.queryByRole("button", { name: "Run both continuations" })).not.toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("What-if horizon"), { target: { value: "21" } });
  expect(screen.getByRole("button", { name: "Prepare comparison" })).toBeDisabled();
  fireEvent.change(screen.getByLabelText("What-if horizon"), { target: { value: "3" } });
  fireEvent.click(screen.getByRole("button", { name: "Prepare comparison" }));
  expect(c.prepare).toHaveBeenCalledWith("A", 50, 3);
  rerender(<WhatIfPanel context={context} controls={{ ...c, status: { request_id: "fixture-pair", state: "prepared", manifest: whatIfManifest } }} onCompare={vi.fn()} />);
  expect(screen.getByLabelText("Prepared what-if")).toHaveTextContent("60 → 80");
  expect(screen.getByLabelText("Prepared what-if")).toHaveTextContent("starting at turn 2");
  fireEvent.click(screen.getByRole("button", { name: "Run both continuations" }));
  expect(c.run).toHaveBeenCalledOnce();
});
it("locks original mutations and continue during a pair, but allows cancel and quit", () => {
  const c = controls(), send = vi.fn();
  render(<InterventionPanel pauseContext={context} sendCommand={send} onSaveCheckpoint={vi.fn()}
    whatIf={{ ...c, status: { request_id: "fixture-pair", state: "running", manifest: whatIfManifest } }} onCompareWhatIf={vi.fn()} />);
  for (const name of ["Continue", "Fork", "Save checkpoint", "Set", "Inject"]) expect(screen.getByRole("button", { name })).toBeDisabled();
  fireEvent.click(screen.getByRole("button", { name: "Cancel comparison" }));
  expect(c.cancel).toHaveBeenCalledOnce();
  fireEvent.click(screen.getByRole("button", { name: "Quit" }));
  expect(send).toHaveBeenCalledWith({ type: "quit" });
});
it("preserves failed-run explanation and exposes completed results through existing comparison", () => {
  const c = controls(), compare = vi.fn();
  const { rerender } = render(<WhatIfPanel context={context} controls={{ ...c, status: { request_id: "fixture-pair", state: "error", message: "Checkpoint source incompatible" } }} onCompare={compare} />);
  expect(screen.getByRole("alert")).toHaveTextContent("Checkpoint source incompatible");
  rerender(<WhatIfPanel context={context} controls={{ ...c, status: { request_id: "fixture-pair", state: "completed", manifest: whatIfManifest, pair: whatIfPair } }} onCompare={compare} />);
  fireEvent.click(screen.getByRole("button", { name: "Compare what-if results" }));
  expect(compare).toHaveBeenCalledWith(whatIfPair);
});

it("imports a recipe into the form without sending commands, then verifies preparation before explicit Run", async () => {
  const manifest = recipeManifest(), recipe = await createWhatIfRecipe(manifest);
  const bundle = comparisonBundle();
  (bundle.world_state as unknown as Record<string, unknown>).agent_mode = "hybrid";
  const c = { ...controls(), bundle };
  const { rerender } = render(<WhatIfPanel context={context} controls={c} onCompare={vi.fn()} />);
  const file = new File([JSON.stringify(recipe)], "plan.json");
  fireEvent.change(screen.getByLabelText("Import what-if recipe"), { target: { files: [file] } });
  expect(await screen.findByText(/Recipe loaded into the preparation form/)).toBeVisible();
  expect(screen.getByLabelText("What-if stability")).toHaveValue(80);
  expect(screen.getByLabelText("What-if horizon")).toHaveValue(3);
  expect(c.prepare).not.toHaveBeenCalled();
  expect(c.run).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Prepare comparison" }));
  expect(c.prepare).toHaveBeenCalledExactlyOnceWith("A", 80, 3);
  rerender(<WhatIfPanel context={context} controls={{ ...c, status: { request_id: "fixture-pair", state: "prepared", manifest } }} onCompare={vi.fn()} />);
  await waitFor(() => expect(screen.getByRole("button", { name: "Run both continuations" })).toBeEnabled());
  expect(c.run).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Run both continuations" }));
  expect(c.run).toHaveBeenCalledOnce();
});

it("refuses a mismatched checkpoint identity and offers cancellation instead of silently running", async () => {
  const manifest = recipeManifest(), recipe = await createWhatIfRecipe(manifest);
  recipe.source.checkpoint.sha256 = "e".repeat(64);
  const bundle = comparisonBundle();
  (bundle.world_state as unknown as Record<string, unknown>).agent_mode = "hybrid";
  const c = { ...controls(), bundle };
  const { rerender } = render(<WhatIfPanel context={context} controls={c} onCompare={vi.fn()} />);
  fireEvent.change(screen.getByLabelText("Import what-if recipe"), { target: { files: [new File([JSON.stringify(recipe)], "mismatch.json")] } });
  await screen.findByText(/Recipe loaded into the preparation form/);
  fireEvent.click(screen.getByRole("button", { name: "Prepare comparison" }));
  rerender(<WhatIfPanel context={context} controls={{ ...c, status: { request_id: "fixture-pair", state: "prepared", manifest } }} onCompare={vi.fn()} />);
  expect(await screen.findByRole("alert")).toHaveTextContent("identity differs");
  expect(screen.getByRole("button", { name: "Run both continuations" })).toBeDisabled();
  expect(c.run).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Cancel comparison" }));
  expect(c.cancel).toHaveBeenCalledOnce();
});

it("rejects incompatible live recipes without replacing the current preparation form", async () => {
  const recipe = await createWhatIfRecipe(recipeManifest());
  recipe.source.seed = 7;
  const bundle = comparisonBundle();
  (bundle.world_state as unknown as Record<string, unknown>).agent_mode = "hybrid";
  const c = { ...controls(), bundle };
  render(<WhatIfPanel context={context} controls={c} onCompare={vi.fn()} />);
  fireEvent.change(screen.getByLabelText("Import what-if recipe"), { target: { files: [new File([JSON.stringify(recipe)], "other-world.json")] } });
  expect(await screen.findByRole("alert")).toHaveTextContent("seed, mode or starting turn differs");
  expect(screen.getByLabelText("What-if stability")).toHaveValue(50);
  expect(c.prepare).not.toHaveBeenCalled();
});

it("imports a global policy recipe and requires an explicit preparation without a civilization argument", async () => {
  const manifest = { ...recipeManifest(), schema_version: 2 as const,
    intervention: { command: "set" as const, civ: "@world" as const, stat: "grain_reserves.shortfall_priority" as const,
      scope: "world" as const, before: 0 as const, value: 1 as const } };
  const recipe = await createWhatIfRecipe(manifest);
  const bundle = comparisonBundle();
  const world = bundle.world_state as unknown as Record<string, unknown>;
  world.agent_mode = "hybrid"; world.grain_reserves = { granaries: [] };
  const c = { ...controls(), bundle };
  render(<WhatIfPanel context={context} controls={c} onCompare={vi.fn()} />);
  fireEvent.change(screen.getByLabelText("Import what-if recipe"), { target: { files: [new File([JSON.stringify(recipe)], "policy.json")] } });
  await screen.findByText(/Recipe loaded into the preparation form/);
  expect(screen.getByLabelText("What-if control")).toHaveValue("granary_shortfall_priority");
  expect(screen.getByLabelText("What-if granary priority")).toHaveValue("1");
  expect(c.preparePolicy).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Prepare comparison" }));
  expect(c.preparePolicy).toHaveBeenCalledExactlyOnceWith(1, 3);
  expect(c.prepare).not.toHaveBeenCalled();
  expect(c.run).not.toHaveBeenCalled();
});

it("downloads a versioned recipe with reference output identities and no raw source headers", async () => {
  const manifest = recipeManifest();
  const pair = { ...whatIfPair, manifest };
  const makeUrl = vi.fn<(blob: Blob) => string>(() => "blob:recipe");
  Object.defineProperty(URL, "createObjectURL", { configurable: true, writable: true, value: makeUrl });
  Object.defineProperty(URL, "revokeObjectURL", { configurable: true, writable: true, value: vi.fn() });
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
  render(<WhatIfPanel context={context} controls={{ ...controls(), status: {
    request_id: "fixture-pair", state: "completed", manifest, pair,
  } }} onCompare={vi.fn()} />);
  fireEvent.click(screen.getByRole("button", { name: "Download recipe" }));
  await waitFor(() => expect(makeUrl).toHaveBeenCalledOnce());
  const text = await new Promise<string>((resolve) => {
    const reader = new FileReader(); reader.onload = () => resolve(String(reader.result)); reader.readAsText(makeUrl.mock.calls[0][0]);
  });
  const recipe = JSON.parse(text);
  expect(recipe.kind).toBe("chronicler-what-if-recipe");
  expect(recipe.version).toBe(1);
  expect(recipe.outputs.baseline.sha256).toBe("a".repeat(64));
  expect(text).not.toContain("PRIVATE_TOKEN");
  expect(text).not.toContain("/private/");
});

it("adopts a different prepared checkpoint only after an explicit new-case choice, retaining the old reference and exporting the new source", async () => {
  const manifest = recipeManifest(), recipe = await createWhatIfRecipe(manifest);
  recipe.source.checkpoint.sha256 = "e".repeat(64);
  const originalText = JSON.stringify(recipe);
  const originalFile = new File([originalText], "saved-reference.json");
  const bundle = comparisonBundle();
  (bundle.world_state as unknown as Record<string, unknown>).agent_mode = "hybrid";
  const c = { ...controls(), bundle };
  const makeUrl = vi.fn<(blob: Blob) => string>(() => "blob:new-case-recipe");
  Object.defineProperty(URL, "createObjectURL", { configurable: true, writable: true, value: makeUrl });
  Object.defineProperty(URL, "revokeObjectURL", { configurable: true, writable: true, value: vi.fn() });
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
  const { rerender } = render(<WhatIfPanel context={context} controls={c} onCompare={vi.fn()} />);
  fireEvent.change(screen.getByLabelText("Import what-if recipe"), { target: { files: [originalFile] } });
  await screen.findByText(/Recipe loaded into the preparation form/);
  fireEvent.click(screen.getByRole("button", { name: "Prepare comparison" }));
  rerender(<WhatIfPanel context={context} controls={{ ...c, status: { request_id: "fixture-pair", state: "prepared", manifest } }} onCompare={vi.fn()} />);
  const adopt = await screen.findByRole("button", { name: "Use this prepared checkpoint as a new case" });
  const sources = screen.getByLabelText("Recipe source comparison");
  expect(within(sources).getByText("e".repeat(64))).toBeVisible();
  expect(within(sources).getByText("f".repeat(64))).toBeVisible();
  expect(sources).toHaveTextContent("Source identifiers:");
  expect(screen.getByRole("button", { name: "Run both continuations" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "Cancel comparison" })).toBeEnabled();
  expect(c.prepare).toHaveBeenCalledOnce();
  expect(c.run).not.toHaveBeenCalled();
  fireEvent.click(adopt);
  expect(screen.getByText(/New case selected for this preparation/)).toHaveTextContent("original recipe is not reproduced; equivalent state is unproven");
  expect(within(screen.getByLabelText("Recipe source comparison")).getByText("e".repeat(64))).toBeVisible();
  expect(screen.getByRole("button", { name: "Run both continuations" })).toBeEnabled();
  expect(c.prepare).toHaveBeenCalledOnce();
  expect(c.run).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Download recipe" }));
  await waitFor(() => expect(makeUrl).toHaveBeenCalledOnce());
  const exportedText = await new Promise<string>((resolve) => {
    const reader = new FileReader(); reader.onload = () => resolve(String(reader.result)); reader.readAsText(makeUrl.mock.calls[0][0]);
  });
  expect(JSON.parse(exportedText).source.checkpoint.sha256).toBe("f".repeat(64));
  expect(new TextDecoder().decode(await originalFile.arrayBuffer())).toBe(originalText);
  expect(c.run).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Run both continuations" }));
  expect(c.run).toHaveBeenCalledOnce();
});

it("invalidates new-case adoption on another preparation and on a different manifest reference while preserving cancellation", async () => {
  const manifest = recipeManifest(), recipe = await createWhatIfRecipe(manifest);
  recipe.source.checkpoint.sha256 = "e".repeat(64);
  const bundle = comparisonBundle();
  (bundle.world_state as unknown as Record<string, unknown>).agent_mode = "hybrid";
  const c = { ...controls(), bundle };
  const { rerender } = render(<WhatIfPanel context={context} controls={c} onCompare={vi.fn()} />);
  fireEvent.change(screen.getByLabelText("Import what-if recipe"), { target: { files: [new File([JSON.stringify(recipe)], "reference.json")] } });
  await screen.findByText(/Recipe loaded into the preparation form/);
  rerender(<WhatIfPanel context={context} controls={{ ...c, status: { request_id: "fixture-pair", state: "prepared", manifest } }} onCompare={vi.fn()} />);
  fireEvent.click(await screen.findByRole("button", { name: "Use this prepared checkpoint as a new case" }));
  expect(screen.getByRole("button", { name: "Run both continuations" })).toBeEnabled();
  const otherWorld = structuredClone(bundle);
  otherWorld.metadata.seed = 7;
  rerender(<WhatIfPanel context={context} controls={{ ...c, bundle: otherWorld, status: { request_id: "fixture-pair", state: "prepared", manifest } }} onCompare={vi.fn()} />);
  expect(screen.getByRole("alert")).toHaveTextContent("seed, mode or starting turn differs");
  expect(screen.getByRole("button", { name: "Run both continuations" })).toBeDisabled();
  rerender(<WhatIfPanel context={context} controls={{ ...c, status: { request_id: "fixture-pair", state: "prepared", manifest } }} onCompare={vi.fn()} />);
  expect(screen.getByRole("button", { name: "Run both continuations" })).toBeEnabled();
  rerender(<WhatIfPanel context={context} controls={{ ...c, status: { request_id: "fixture-pair", state: "preparing", manifest } }} onCompare={vi.fn()} />);
  rerender(<WhatIfPanel context={context} controls={{ ...c, status: { request_id: "fixture-pair", state: "prepared", manifest } }} onCompare={vi.fn()} />);
  expect(screen.getByRole("button", { name: "Run both continuations" })).toBeDisabled();
  fireEvent.click(await screen.findByRole("button", { name: "Use this prepared checkpoint as a new case" }));
  expect(screen.getByRole("button", { name: "Run both continuations" })).toBeEnabled();
  const replacement = structuredClone(manifest);
  rerender(<WhatIfPanel context={context} controls={{ ...c, status: { request_id: "fixture-pair", state: "prepared", manifest: replacement } }} onCompare={vi.fn()} />);
  expect(screen.getByRole("button", { name: "Run both continuations" })).toBeDisabled();
  await screen.findByRole("button", { name: "Use this prepared checkpoint as a new case" });
  expect(screen.queryByText(/New case selected for this preparation/)).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Cancel comparison" }));
  expect(c.cancel).toHaveBeenCalledOnce();
  expect(c.run).not.toHaveBeenCalled();
});

it("does not offer new-case adoption when the prepared manifest lacks verifiable checkpoint identity", async () => {
  const recipe = await createWhatIfRecipe(recipeManifest());
  const bundle = comparisonBundle();
  (bundle.world_state as unknown as Record<string, unknown>).agent_mode = "hybrid";
  const c = { ...controls(), bundle };
  const { rerender } = render(<WhatIfPanel context={context} controls={c} onCompare={vi.fn()} />);
  fireEvent.change(screen.getByLabelText("Import what-if recipe"), { target: { files: [new File([JSON.stringify(recipe)], "reference.json")] } });
  await screen.findByText(/Recipe loaded into the preparation form/);
  rerender(<WhatIfPanel context={context} controls={{ ...c, status: { request_id: "fixture-pair", state: "prepared", manifest: whatIfManifest } }} onCompare={vi.fn()} />);
  expect(await screen.findByRole("alert")).toHaveTextContent("complete compatible exact-checkpoint manifest");
  expect(screen.queryByRole("button", { name: "Use this prepared checkpoint as a new case" })).toBeNull();
  expect(screen.getByRole("button", { name: "Run both continuations" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "Cancel comparison" })).toBeEnabled();
});
