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

  it("resyncs staged controls when pause context changes", () => {
    const sendCommand = vi.fn();
    const { rerender } = render(
      <InterventionPanel pauseContext={mockContext} sendCommand={sendCommand} />,
    );

    fireEvent.change(screen.getByLabelText(/event type/i), { target: { value: "migration" } });
    fireEvent.change(screen.getByLabelText(/target civ/i), { target: { value: "Civ Beta" } });
    fireEvent.click(screen.getByText(/inject/i));

    const updatedContext: PauseContext = {
      ...mockContext,
      turn: 25,
      injectable_events: ["famine"],
      civs: ["Civ Gamma"],
      settable_stats: ["stability"],
    };

    rerender(<InterventionPanel pauseContext={updatedContext} sendCommand={sendCommand} />);

    expect(screen.getByText(/paused at turn 25/i)).toBeDefined();
    expect(screen.getByLabelText(/event type/i)).toHaveValue("famine");
    expect(screen.getByLabelText(/target civ/i)).toHaveValue("Civ Gamma");
    expect(screen.getByLabelText(/stat civ/i)).toHaveValue("Civ Gamma");
    expect(screen.getByLabelText(/stat name/i)).toHaveValue("stability");
    expect(screen.queryByText(/pending actions/i)).toBeNull();
  });

  describe("Save checkpoint", () => {
    const checkpointContext: PauseContext = {
      ...mockContext,
      valid_commands: [...mockContext.valid_commands, "checkpoint"],
    };

    it("is offered only when the server lists checkpoint", () => {
      const onSave = vi.fn();
      const { rerender } = render(
        <InterventionPanel pauseContext={mockContext} sendCommand={vi.fn()} onSaveCheckpoint={onSave} />,
      );
      expect(screen.queryByRole("button", { name: /save checkpoint/i })).toBeNull();
      rerender(
        <InterventionPanel pauseContext={checkpointContext} sendCommand={vi.fn()} onSaveCheckpoint={onSave} />,
      );
      fireEvent.click(screen.getByRole("button", { name: /save checkpoint/i }));
      expect(onSave).toHaveBeenCalledTimes(1);
    });

    it("shows the saved file, or the server's refusal", () => {
      const { rerender } = render(
        <InterventionPanel
          pauseContext={checkpointContext}
          sendCommand={vi.fn()}
          onSaveCheckpoint={vi.fn()}
          checkpointStatus={{ state: "saving" }}
        />,
      );
      expect(screen.getByText(/saving checkpoint/i)).toBeDefined();
      expect(screen.getByRole("button", { name: /save checkpoint/i })).toBeDisabled();
      rerender(
        <InterventionPanel
          pauseContext={checkpointContext}
          sendCommand={vi.fn()}
          onSaveCheckpoint={vi.fn()}
          checkpointStatus={{
            state: "saved",
            turn: 20,
            path: "output/live_checkpoints/turn_0020.ckpt",
            resumeHint: "--live --resume output/live_checkpoints/turn_0020.ckpt",
          }}
        />,
      );
      expect(screen.getByText(/checkpoint saved at turn 20/i)).toBeDefined();
      expect(screen.getByText("output/live_checkpoints/turn_0020.ckpt")).toBeDefined();
      expect(screen.getByText(/--live --resume/)).toBeDefined();
      expect(screen.getByRole("button", { name: /save checkpoint/i })).toBeEnabled();
      rerender(
        <InterventionPanel
          pauseContext={checkpointContext}
          sendCommand={vi.fn()}
          onSaveCheckpoint={vi.fn()}
          checkpointStatus={{ state: "error", message: "Checkpoint not written: disk full" }}
        />,
      );
      expect(screen.getByText(/disk full/)).toBeDefined();
    });
  });
});
