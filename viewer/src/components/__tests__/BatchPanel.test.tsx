import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { BatchPanel } from "../BatchPanel";

describe("BatchPanel", () => {
  const defaultProps = {
    batchState: "idle" as const,
    report: null,
    progress: null,
    error: null,
    onStart: vi.fn(),
    onCancel: vi.fn(),
    onReset: vi.fn(),
  };

  it("renders config form in idle state", () => {
    render(<BatchPanel {...defaultProps} />);
    expect(screen.getByText("Start Seed")).toBeTruthy();
    expect(screen.getByText("Seed Count")).toBeTruthy();
    expect(screen.getByText("Turns")).toBeTruthy();
    expect(screen.getByText(/Workers/)).toBeTruthy();
    expect(screen.getByText("Simulate Only")).toBeTruthy();
    expect(screen.getByRole("button", { name: /Run Batch/i })).toBeTruthy();
  });

  it("calls onStart with config when Run Batch clicked", () => {
    const onStart = vi.fn();
    render(<BatchPanel {...defaultProps} onStart={onStart} />);

    fireEvent.click(screen.getByRole("button", { name: /Run Batch/i }));

    expect(onStart).toHaveBeenCalledTimes(1);
    const config = onStart.mock.calls[0][0];
    expect(config.seed_start).toBe(1);
    expect(config.seed_count).toBe(200);
    expect(config.turns).toBe(500);
    expect(config.simulate_only).toBe(true);
    expect(config.parallel).toBe(true);
  });

  it("passes through current setup defaults when provided", () => {
    const onStart = vi.fn();
    render(
      <BatchPanel
        {...defaultProps}
        onStart={onStart}
        runDefaults={{
          turns: 120,
          civs: 6,
          regions: 10,
          scenario: "test.yaml",
          sim_model: "sim-x",
          narrative_model: "narr-x",
          narrator: "local",
        }}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /Run Batch/i }));

    const config = onStart.mock.calls[0][0];
    expect(config.turns).toBe(120);
    expect(config.civs).toBe(6);
    expect(config.regions).toBe(10);
    expect(config.scenario).toBe("test.yaml");
    expect(config.sim_model).toBe("sim-x");
    expect(config.narrative_model).toBe("narr-x");
    expect(config.narrator).toBe("local");
  });

  it("shows progress bar when running", () => {
    render(
      <BatchPanel
        {...defaultProps}
        batchState="running"
        progress={{ completed: 50, total: 200, currentSeed: 51 }}
      />,
    );

    expect(screen.getByText("50/200")).toBeTruthy();
    expect(screen.getByText("Seed 51")).toBeTruthy();
    expect(screen.getByRole("button", { name: /Cancel Batch/i })).toBeTruthy();
  });

  it("guards zero-total progress without rendering NaN width", () => {
    const { container } = render(
      <BatchPanel
        {...defaultProps}
        batchState="running"
        progress={{ completed: 0, total: 0, currentSeed: 1 }}
      />,
    );

    expect(screen.getByText("0/0")).toBeTruthy();
    const fill = container.querySelector(".bg-green-500");
    expect(fill).not.toBeNull();
    expect(fill).toHaveStyle({ width: "0%" });
  });

  it("calls onCancel when Cancel clicked", () => {
    const onCancel = vi.fn();
    render(
      <BatchPanel
        {...defaultProps}
        batchState="running"
        progress={{ completed: 10, total: 200, currentSeed: 11 }}
        onCancel={onCancel}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /Cancel Batch/i }));
    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  it("disables inputs while running", () => {
    render(
      <BatchPanel
        {...defaultProps}
        batchState="running"
        progress={{ completed: 0, total: 200, currentSeed: 1 }}
      />,
    );

    const inputs = screen.getAllByRole("spinbutton");
    inputs.forEach((input) => {
      expect(input).toBeDisabled();
    });
  });

  it("shows error banner", () => {
    render(<BatchPanel {...defaultProps} batchState="error" error="Something broke" />);
    expect(screen.getByText("Something broke")).toBeTruthy();
  });

  it("toggles tuning overrides section", () => {
    render(<BatchPanel {...defaultProps} />);

    expect(screen.queryByText("Drought Immediate")).toBeNull();
    fireEvent.click(screen.getByText(/Tuning Overrides/));
    expect(screen.getByText("Drought Immediate")).toBeTruthy();
  });

  it("sends tuning overrides when filled in", () => {
    const onStart = vi.fn();
    render(<BatchPanel {...defaultProps} onStart={onStart} />);

    fireEvent.click(screen.getByText(/Tuning Overrides/));

    const droughtLabel = screen.getByText("Drought Immediate");
    const droughtInput = droughtLabel.closest("div")!.querySelector("input")!;
    fireEvent.change(droughtInput, { target: { value: "10" } });

    fireEvent.click(screen.getByRole("button", { name: /Run Batch/i }));

    const config = onStart.mock.calls[0][0];
    expect(config.tuning_overrides).toEqual({
      "stability.drain.drought_immediate": 10,
    });
  });
});
