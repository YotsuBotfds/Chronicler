import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import fixture from "../../../__fixtures__/sample_bundle.json";
import type { Bundle } from "../../../types";
import { SavedWorldDetails } from "../SavedWorldDetails";
import { savedWorldSummary } from "../../../lib/savedWorldSummary";

afterEach(cleanup);

it("keeps file details available and reports actual snapshot range independently of the final state", () => {
  const bundle = structuredClone(fixture) as unknown as Bundle;
  bundle.history = [bundle.history[3], bundle.history[7]];
  bundle.world_state.turn = 50;
  render(<SavedWorldDetails bundle={bundle} identity={{ name: "world.json", byteLength: 321, sha256: "abc123" }} />);
  expect(screen.getByText("Recorded turns").nextElementSibling?.textContent).toBe("4–8 (2 snapshots)");
  expect(screen.getByText("Saved final turn").nextElementSibling?.textContent).toBe("50");
  expect(screen.getByText("world.json")).toBeInTheDocument();
  expect(screen.getByText(/SHA-256 abc123/)).toBeInTheDocument();
  expect(screen.getByText(/final state does not establish earlier observations/)).toBeInTheDocument();
});

it("leaves absent mode and history unknown and separates enabled saved systems from historical observations", () => {
  const bundle = structuredClone(fixture) as unknown as Bundle;
  const world = bundle.world_state as unknown as Record<string, unknown>;
  delete world.agent_mode;
  world.grain_reserves = { granaries: [] };
  bundle.history = [];
  expect(savedWorldSummary(bundle)).toMatchObject({ first: null, last: null, mode: "Unknown — not recorded",
    enabled: expect.arrayContaining(["Public granaries"]), recorded: [] });
  render(<SavedWorldDetails bundle={bundle} />);
  expect(screen.getByText("No recorded snapshots")).toBeInTheDocument();
  expect(screen.getByText("No system history recorded")).toBeInTheDocument();
});
