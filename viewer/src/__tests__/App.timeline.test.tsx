import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { Bundle } from "../types";
import fixture from "../__fixtures__/region_inspection_bundle.json";

const state = vi.hoisted(() => ({ staticBundle: null as Bundle | null, liveBundle: null as Bundle | null }));
vi.mock("../hooks/useBundle", () => ({ useBundle: () => ({ bundle: state.staticBundle,
  error: null, loading: false, artifactIdentity: null, loadFromFile: vi.fn() }) }));
vi.mock("../hooks/useLiveConnection", () => ({ useLiveConnection: () => ({ bundle: state.liveBundle,
  error: null, connected: true, serverState: "running", batch: { batchState: "idle" } }) }));
vi.mock("../components/phase75/AppShell", () => ({ AppShell: ({ currentTurn, onSeek }: {
  currentTurn: number; onSeek: (turn: number) => void;
}) => <><output aria-label="Current turn">{currentTurn}</output>
  <button onClick={() => onSeek(5)}>Seek exported endpoint</button>
  <button onClick={() => onSeek(3)}>Seek received endpoint</button></> }));
import App from "../App";

beforeEach(() => {
  window.history.replaceState({}, "", "/");
  state.staticBundle = structuredClone(fixture) as unknown as Bundle;
  state.liveBundle = null;
});
afterEach(() => { cleanup(); window.history.replaceState({}, "", "/"); });

it("navigates a static sparse artifact to its exported endpoint, not its sample count", () => {
  render(<App />);
  fireEvent.click(screen.getByRole("button", { name: "Seek exported endpoint" }));
  expect(screen.getByLabelText("Current turn")).toHaveTextContent("5");
});

it("keeps streaming navigation and follow mode bounded by actually received snapshots", () => {
  window.history.replaceState({}, "", "/?ws=ws://localhost/test");
  state.liveBundle = structuredClone(fixture) as unknown as Bundle;
  state.liveBundle.metadata.total_turns = 100;
  state.liveBundle.history = state.liveBundle.history.slice(0, 2); // only turns 1 and 3 received
  const { rerender } = render(<App />);
  expect(screen.getByLabelText("Current turn")).toHaveTextContent("3");
  fireEvent.click(screen.getByRole("button", { name: "Seek exported endpoint" }));
  expect(screen.getByLabelText("Current turn")).toHaveTextContent("3");
  fireEvent.click(screen.getByRole("button", { name: "Seek received endpoint" }));
  state.liveBundle = { ...state.liveBundle, history: [...state.liveBundle.history, fixture.history[2]] } as Bundle;
  rerender(<App />);
  expect(screen.getByLabelText("Current turn")).toHaveTextContent("5");
});
