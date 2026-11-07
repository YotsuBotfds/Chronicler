import { expect, it } from "vitest";
import type { TurnSnapshot } from "../../types";
import { movementBranchesAt, movementBranchesOn } from "../movementBranches";

import { branchRecord } from "./movementBranchesFixture";
const snapshot = (record: unknown, turn = 5) => ({ turn, livelihoods: { movement_branches: record } }) as unknown as TurnSnapshot;

it("distinguishes absent, unobserved, recorded zero and a paid dated branch", () => {
  expect(movementBranchesAt(snapshot(null), 2, 2).status).toBe("absent");
  expect(movementBranchesOn([snapshot(branchRecord())])).toBe(true);
  expect(movementBranchesAt(snapshot({ ...branchRecord(), frame: null }), 2, 2).status).toBe("unobserved");
  expect(movementBranchesAt(snapshot({ ...branchRecord(), frame: { turn: 4, new_identities_refused: 0, rows: [] } }), 2, 2).status).toBe("recorded_zero");
  expect(movementBranchesAt(snapshot(branchRecord()), 2, 2).status).toBe("recorded");
});

it("refuses misdated, duplicate, unpaid-permission and inconsistent-money records", () => {
  const paid = branchRecord();
  for (const bad of [
    { ...paid, source_turn: 5 }, { ...paid, mode: "cost_only" },
    { ...paid, frame: { ...paid.frame, rows: [{ ...paid.frame.rows[0], payers: [1, 1, 2] }] } },
    { ...paid, frame: { ...paid.frame, rows: [{ ...paid.frame.rows[0], dues_milli: 31 }] } },
    { ...paid, frame: { ...paid.frame, rows: [{ ...paid.frame.rows[0], regions: [9] }] } },
    { ...paid, frame: { ...paid.frame, rows: [paid.frame.rows[0], paid.frame.rows[0]] } },
  ]) expect(movementBranchesAt(snapshot(bad), 2, 2).status).toBe("malformed");
});
