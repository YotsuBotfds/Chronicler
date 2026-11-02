import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { debtEvidenceFixture } from "../../__fixtures__/debtEvidence";
import { DebtEvidence } from "../DebtEvidence";

describe("debt evidence inspector", () => {
  it("shows fiscal payment scope and keeps event inspection distinct from explicit seeking", () => {
    const inspect = vi.fn(), seek = vi.fn();
    render(<DebtEvidence bundle={debtEvidenceFixture()} currentTurn={3} civilizationIndex={0} onInspectEvent={inspect} onViewRecordedTurn={seek} />);
    expect(screen.getByText(/Total debt 250; foreign subset 50/)).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Interest paid" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Inspect credit event: state_default" }));
    expect(inspect).toHaveBeenCalledWith(expect.objectContaining({ event_id: "default-2", turn: 2 }));
    expect(seek).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "View snapshot 1" }));
    expect(seek).toHaveBeenCalledWith(1);
  });

  it("supports a bounded keyboard-operable snapshot window", () => {
    render(<DebtEvidence bundle={debtEvidenceFixture()} currentTurn={25} civilizationIndex={0} />);
    const select = screen.getByRole("combobox", { name: "Debt evidence window" });
    select.focus();
    expect(select).toHaveFocus();
    fireEvent.change(select, { target: { value: "10" } });
    expect(screen.getByText(/Snapshot window 16–25/, { selector: "caption" })).toBeInTheDocument();
    const scroll = screen.getByRole("region", { name: "Scrollable fiscal payment ledger" });
    scroll.focus();
    expect(scroll).toHaveFocus();
    expect(screen.queryByText("FUTURE_SECRET_CREDIT_EVENT")).not.toBeInTheDocument();
  });

  it("drops future rows and event descriptions immediately on rewind", () => {
    const bundle = debtEvidenceFixture();
    const { rerender } = render(<DebtEvidence bundle={bundle} currentTurn={10} civilizationIndex={0} />);
    expect(screen.getByText("FUTURE_SECRET_CREDIT_EVENT")).toBeInTheDocument();
    rerender(<DebtEvidence bundle={bundle} currentTurn={3} civilizationIndex={0} />);
    expect(screen.queryByText("FUTURE_SECRET_CREDIT_EVENT")).not.toBeInTheDocument();
    expect(screen.queryByText("99,999,999")).not.toBeInTheDocument();
  });

  it("shows an unrecorded selected row as unknown, retaining independently dated loss events", () => {
    render(<DebtEvidence bundle={debtEvidenceFixture()} currentTurn={6} civilizationIndex={0} />);
    expect(screen.getByRole("status")).toHaveTextContent("Borrower absent");
    expect(screen.getByText(/Total debt Unknown; foreign subset Unknown/)).toBeInTheDocument();
    expect(screen.getByText("A's obligations are written off after its fall.")).toBeInTheDocument();
    expect(screen.getByText(/does not establish that there are no creditors/)).toBeInTheDocument();
  });

  it("renders unresolved selection and duplicate identities without a fake ledger", () => {
    const bundle = debtEvidenceFixture();
    const { rerender } = render(<DebtEvidence bundle={bundle} currentTurn={3} civilizationIndex={null} />);
    expect(screen.getByRole("status")).toHaveTextContent("Choose a civilization");
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
    bundle.world_state.civilizations.push({ ...bundle.world_state.civilizations[0] });
    rerender(<DebtEvidence bundle={bundle} currentTurn={3} civilizationIndex={0} />);
    expect(screen.getByRole("status")).toHaveTextContent("Repeated civilization name");
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });
});
