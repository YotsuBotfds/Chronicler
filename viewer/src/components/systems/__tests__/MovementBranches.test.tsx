import { afterEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { Bundle, TurnSnapshot } from "../../../types";
import { MovementBranches } from "../MovementBranches";
import { branchRecord } from "../../../lib/__tests__/movementBranchesFixture";

afterEach(cleanup);

it("uses historical names and distinguishes paid permission from individual effects", () => {
  const snapshot = { turn: 5, livelihoods: { movement_branches: branchRecord() } } as unknown as TurnSnapshot;
  const bundle = { history: [snapshot], world_state: { regions: [{ name: "Home field" }, { name: "Host field" }],
    civilizations: [{ name: "Future home name" }, { name: "Future host name" }] } } as unknown as Bundle;
  const select = vi.fn();
  render(<MovementBranches bundle={bundle} snapshot={snapshot} onSelectRegion={select} />);
  expect(screen.getByText("Host then / Home then")).toBeInTheDocument();
  expect(screen.queryByText(/Future host name/)).toBeNull();
  expect(screen.getByText(/No particular member's change is attributed/)).toBeInTheDocument();
  expect(screen.getByText(/0.030 from 3 people/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Host field" }));
  expect(select).toHaveBeenCalledWith("Host field");
});
