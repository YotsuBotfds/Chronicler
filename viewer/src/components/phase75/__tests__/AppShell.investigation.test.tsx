import { afterEach, beforeAll, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { regionalFixture } from "../../../__fixtures__/regionalPopulation";
import { AppShell } from "../AppShell";
import { preloadPanels } from "../lazyPanels";
import { INVESTIGATION_BOOKMARKS_KEY } from "../../../lib/investigationBookmarks";
beforeAll(() => preloadPanels());
afterEach(() => { cleanup(); localStorage.clear(); });
const hash = "a".repeat(64);
function mount() {
  const onSeek = vi.fn(); const bundle = regionalFixture();
  const props = { surface: "overview" as const, onSurfaceChange: vi.fn(), bundle, artifactIdentity: { name: "world.json", byteLength: 123, sha256: hash },
    bundleLoading: false, error: null, isLive: false, connected: false, serverState: "completed" as const,
    currentTurn: 3, playing: false, speed: 1, onSeek, onPlay: vi.fn(), onPause: vi.fn(), onSetSpeed: vi.fn(),
    lobbyInit: null, starting: false, onOpenBundleFile: vi.fn() };
  return { ...render(<AppShell {...props} />), onSeek };
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
