import { afterEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { WhatIfPanel } from "../WhatIfPanel";
import { InterventionPanel } from "../InterventionPanel";
import type { WhatIfControls } from "../../lib/whatIf";
import type { PauseContext } from "../../types";
import { whatIfManifest, whatIfPair } from "../../__fixtures__/whatIf";
import { comparisonBundle } from "../../__fixtures__/completedRunHistory";
const context: PauseContext = { turn: 2, reason: "interval", civs: ["A", "B"],
  valid_commands: ["what_if_prepare", "checkpoint", "continue", "set", "fork", "quit"], injectable_events: ["famine"], settable_stats: ["stability"] };
const controls = (): WhatIfControls => ({ status: null, connected: true, prepare: vi.fn(), preparePolicy: vi.fn(), run: vi.fn(), cancel: vi.fn() });
afterEach(cleanup);
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
