import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { InterventionPanel } from "../InterventionPanel";
import type { PauseContext } from "../../types";

const mockContext: PauseContext = {
  turn: 20,
  reason: "era_boundary",
  valid_commands: ["continue", "inject", "set", "fork", "quit"],
  injectable_events: ["plague", "famine", "migration"],
  settable_stats: ["population", "military", "economy"],
  civs: ["Civ Alpha", "Civ Beta"],
};

describe("InterventionPanel", () => {
  it("renders when visible", () => {
    const sendCommand = vi.fn();
    render(<InterventionPanel pauseContext={mockContext} sendCommand={sendCommand} />);
    expect(screen.getByText(/paused at turn 20/i)).toBeDefined();
  });

  it("stages inject command in pending queue on Inject click", () => {
    const sendCommand = vi.fn();
    render(<InterventionPanel pauseContext={mockContext} sendCommand={sendCommand} />);

    fireEvent.change(screen.getByLabelText(/event type/i), { target: { value: "plague" } });
    fireEvent.change(screen.getByLabelText(/target civ/i), { target: { value: "Civ Alpha" } });
    fireEvent.click(screen.getByText(/inject/i));

    // Should appear in pending list, not sent yet
    expect(screen.getByText(/plague/)).toBeDefined();
    expect(sendCommand).not.toHaveBeenCalled();
  });

  it("sends set command immediately", () => {
    const sendCommand = vi.fn();
    render(<InterventionPanel pauseContext={mockContext} sendCommand={sendCommand} />);

    fireEvent.change(screen.getByLabelText(/stat civ/i), { target: { value: "Civ Beta" } });
    fireEvent.change(screen.getByLabelText(/stat name/i), { target: { value: "military" } });
    fireEvent.change(screen.getByLabelText(/stat value/i), { target: { value: "9" } });
    fireEvent.click(screen.getByText(/^set$/i));

    expect(sendCommand).toHaveBeenCalledWith({ type: "set", civ: "Civ Beta", stat: "military", value: 9 });
  });

  it("removes staged inject from pending queue", () => {
    const sendCommand = vi.fn();
    render(<InterventionPanel pauseContext={mockContext} sendCommand={sendCommand} />);

    fireEvent.change(screen.getByLabelText(/event type/i), { target: { value: "plague" } });
    fireEvent.change(screen.getByLabelText(/target civ/i), { target: { value: "Civ Alpha" } });
    fireEvent.click(screen.getByText(/inject/i));

    const removeBtn = screen.getByLabelText(/remove/i);
    fireEvent.click(removeBtn);
    expect(screen.queryByText(/plague.*Civ Alpha/)).toBeNull();
  });

  it("sends staged commands then continue on Continue click", () => {
    const sendCommand = vi.fn();
    render(<InterventionPanel pauseContext={mockContext} sendCommand={sendCommand} />);

    // Stage an inject
    fireEvent.change(screen.getByLabelText(/event type/i), { target: { value: "plague" } });
    fireEvent.change(screen.getByLabelText(/target civ/i), { target: { value: "Civ Alpha" } });
    fireEvent.click(screen.getByText(/inject/i));

    // Click continue — should send staged inject, then continue
    fireEvent.click(screen.getByText(/continue/i));
    expect(sendCommand).toHaveBeenCalledTimes(2);
    expect(sendCommand).toHaveBeenNthCalledWith(1, { type: "inject", event_type: "plague", civ: "Civ Alpha" });
    expect(sendCommand).toHaveBeenNthCalledWith(2, { type: "continue" });
  });

  it("sends fork command immediately", () => {
    const sendCommand = vi.fn();
    render(<InterventionPanel pauseContext={mockContext} sendCommand={sendCommand} />);

    fireEvent.click(screen.getByText(/fork/i));
    expect(sendCommand).toHaveBeenCalledWith({ type: "fork" });
  });

  it("sends quit command immediately", () => {
    const sendCommand = vi.fn();
    render(<InterventionPanel pauseContext={mockContext} sendCommand={sendCommand} />);

    fireEvent.click(screen.getByText(/quit/i));
    expect(sendCommand).toHaveBeenCalledWith({ type: "quit" });
  });
});
