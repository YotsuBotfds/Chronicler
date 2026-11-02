import { afterEach, beforeAll, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { regionalFixture } from "../../../__fixtures__/regionalPopulation";
import { AppShell } from "../AppShell";
import { preloadPanels } from "../lazyPanels";
import { INVESTIGATION_BOOKMARKS_KEY } from "../../../lib/investigationBookmarks";
import type { ComponentProps } from "react";
beforeAll(() => preloadPanels());
afterEach(() => { cleanup(); localStorage.clear(); });
const hash = "a".repeat(64);
function mount(extra: Partial<ComponentProps<typeof AppShell>> = {}) {
  const onSeek = vi.fn(); const bundle = regionalFixture();
  const props = { surface: "overview" as const, onSurfaceChange: vi.fn(), bundle, artifactIdentity: { name: "world.json", byteLength: 123, sha256: hash },
    bundleLoading: false, error: null, isLive: false, connected: false, serverState: "completed" as const,
    currentTurn: 3, playing: false, speed: 1, onSeek, onPlay: vi.fn(), onPause: vi.fn(), onSetSpeed: vi.fn(),
    lobbyInit: null, starting: false, onOpenBundleFile: vi.fn(), ...extra };
  return { ...render(<AppShell {...props} />), onSeek, props };
}
it("keeps map, region history and turn comparison synchronized without resetting the metric, window or selected turn", async () => {
  const { onSeek } = mount();
  fireEvent.click(screen.getByRole("button", { name: "Inspect region A" }));
  fireEvent.click(within(screen.getByRole("region", { name: "Selected region investigation" })).getByRole("button", { name: "Inspect history: A" }));
  const region = await screen.findByRole("combobox", { name: "Region" });
  const metric = screen.getByRole("combobox", { name: "Metric" }) as HTMLSelectElement;
  const chosen = metric.options[metric.options.length - 1].value;
  fireEvent.change(metric, { target: { value: chosen } });
  fireEvent.change(screen.getByLabelText("From turn", { exact: true }), { target: { value: "2" } });
  fireEvent.click(screen.getByRole("button", { name: "Inspect region B" }));
  expect(region).toHaveValue("B"); expect(metric).toHaveValue(chosen);
  expect(screen.getByLabelText("From turn", { exact: true })).toHaveValue(2);
  fireEvent.change(region, { target: { value: "A" } });
  expect(screen.getByRole("region", { name: "Selected region investigation" })).toHaveTextContent("Region identity 0");
  expect(screen.getByRole("combobox", { name: "Compare civilization or region" })).toHaveValue(JSON.stringify(["region", "A"]));
  expect(onSeek).not.toHaveBeenCalled();
});
it("lets a paused world be inspected without commands or lost intervention drafts, and reopens controls at a new pause", async () => {
  const send = vi.fn();
  const context = { turn: 3, reason: "interval", civs: ["A", "B"], valid_commands: ["continue", "inject", "set", "quit"],
    injectable_events: ["plague"], settable_stats: ["stability"] };
  const { props, rerender, onSeek } = mount({ isLive: true, connected: true, serverState: "running", livePaused: true,
    livePauseContext: context, liveSendCommand: send });
  let dialog = await screen.findByRole("dialog", { name: "Paused simulation at turn 3" });
  fireEvent.change(within(dialog).getByRole("spinbutton"), { target: { value: "77" } });
  fireEvent.click(within(dialog).getByRole("button", { name: "Inject" }));
  fireEvent.click(within(dialog).getByRole("button", { name: "Inspect world while paused" }));
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  fireEvent.change(screen.getByRole("combobox", { name: "Inspect a region" }), { target: { value: "B" } });
  expect(screen.getByRole("region", { name: "Selected region investigation" })).toHaveTextContent("Region identity 1");
  fireEvent.click(screen.getByRole("button", { name: "Return to run controls" }));
  dialog = screen.getByRole("dialog", { name: "Paused simulation at turn 3" });
  expect(within(dialog).getByRole("spinbutton")).toHaveValue(77);
  expect(within(dialog).getByText(/plague.*A/)).toBeInTheDocument();
  expect(send).not.toHaveBeenCalled(); expect(onSeek).not.toHaveBeenCalled();
  fireEvent.click(within(dialog).getByRole("button", { name: "Inspect world while paused" }));
  rerender(<AppShell {...props} livePauseContext={{ ...context, turn: 4 }} />);
  expect(screen.getByRole("dialog", { name: "Paused simulation at turn 4" })).toBeInTheDocument();
});
it("restores only an available entity and exact turn from a matching file, and leaves a forged target alone", async () => {
  localStorage.setItem(INVESTIGATION_BOOKMARKS_KEY, JSON.stringify({ version: 1, bookmarks: [
    { world: { sha256: hash, filename: "world.json" }, target: { kind: "region", index: 1, name: "B" }, turn: 2, panel: "history" },
    { world: { sha256: hash, filename: "world.json" }, target: { kind: "region", index: 42, name: "A" }, turn: 1, panel: "history" },
  ] }));
  const { onSeek } = mount();
  fireEvent.click(screen.getByText("Bookmarks and investigation export"));
  const bookmarks = await screen.findByRole("region", { name: "Investigation bookmarks" });
  fireEvent.click(within(bookmarks).getByRole("button", { name: "Restore bookmark: A, turn 1, history" }));
  expect(within(bookmarks).getByRole("status")).toHaveTextContent("identity is unavailable or ambiguous");
  expect(onSeek).not.toHaveBeenCalled();
  fireEvent.click(within(bookmarks).getByRole("button", { name: "Restore bookmark: B, turn 2, history" }));
  expect(onSeek).toHaveBeenLastCalledWith(2);
  expect(await screen.findByRole("combobox", { name: "Region" })).toHaveValue("B");
});
