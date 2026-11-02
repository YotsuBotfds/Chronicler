import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { LiveInspectionControls } from "../LiveInspectionControls";

describe("LiveInspectionControls", () => {
  it("offers an explicit inspection lock while following", () => {
    const onLock = vi.fn();
    const onReturnToLive = vi.fn();
    render(<LiveInspectionControls
      followMode inspectionLocked={false} newTurns={0} latestTurn={100}
      onLock={onLock} onReturnToLive={onReturnToLive}
    />);
    expect(screen.getByRole("status")).toHaveTextContent("Following live");
    fireEvent.click(screen.getByRole("button", { name: "Inspect this turn" }));
    expect(onLock).toHaveBeenCalledOnce();
    expect(onReturnToLive).not.toHaveBeenCalled();
  });

  it("shows arrivals and returns only after an explicit click", () => {
    const onReturnToLive = vi.fn();
    const props = {
      followMode: false, inspectionLocked: true, newTurns: 0, latestTurn: 100,
      onLock: vi.fn(), onReturnToLive,
    };
    const { rerender } = render(<LiveInspectionControls {...props} />);
    expect(screen.getByRole("status")).toHaveTextContent("Inspecting history");
    expect(screen.getByRole("status")).toHaveTextContent("Latest available: turn 100");
    expect(screen.getByRole("button", { name: "Return to live" })).toBeVisible();
    expect(screen.queryByText(/new turns available/)).toBeNull();

    rerender(<LiveInspectionControls {...props} newTurns={5} latestTurn={105} />);
    expect(screen.getByRole("status")).toHaveTextContent("5 new turns available");
    expect(screen.getByRole("status")).toHaveTextContent("Latest available: turn 105");
    expect(onReturnToLive).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Return to live" }));
    expect(onReturnToLive).toHaveBeenCalledOnce();
  });

  it("labels a single arrival and does not claim to follow while disconnected", () => {
    const props = {
      followMode: false, inspectionLocked: true, newTurns: 1, latestTurn: 101,
      onLock: vi.fn(), onReturnToLive: vi.fn(),
    };
    const { rerender } = render(<LiveInspectionControls {...props} />);
    expect(screen.getByRole("status")).toHaveTextContent("1 new turn available");
    rerender(<LiveInspectionControls {...props} inspectionLocked={false} newTurns={0} />);
    expect(screen.getByRole("status")).toHaveTextContent("Live follow ready");
    expect(screen.queryByText("Following live")).toBeNull();
  });
});
