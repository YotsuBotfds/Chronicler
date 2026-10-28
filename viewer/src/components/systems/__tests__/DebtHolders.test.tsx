import { afterEach, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import fixture from "../../../__fixtures__/debt_holders_bundle.json";
import type { Bundle } from "../../../types";
import { DebtHolders } from "../DebtHolders";

afterEach(cleanup);
it("distinguishes the missing historical finance record from observed zero debt", () => {
  const bundle = fixture as unknown as Bundle;
  render(<DebtHolders bundle={bundle} snapshot={null} currentTurn={0}
    civs={bundle.world_state.civilizations.map((civ) => civ.name)} onSeek={vi.fn()}
    onSelectEvent={vi.fn()} onSelectRegion={vi.fn()} onSelectCivilization={vi.fn()} />);
  expect(screen.getByText("No finance record at turn 0.")).toBeInTheDocument();
  expect(screen.queryByText(/No civilization owes anything/)).not.toBeInTheDocument();
});
