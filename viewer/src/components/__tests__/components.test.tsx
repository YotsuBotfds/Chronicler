import { describe, it, expect, beforeAll } from "vitest";
import { render, screen } from "@testing-library/react";
import sampleBundle from "../../__fixtures__/sample_bundle.json";
import type { Bundle } from "../../types";

// jsdom does not implement scrollIntoView
beforeAll(() => {
  Element.prototype.scrollIntoView = () => {};
});
import { Header } from "../Header";
import { FactionDashboard } from "../FactionDashboard";
import { EventLog } from "../EventLog";
import { ChroniclePanel } from "../ChroniclePanel";
import { StatGraphs } from "../StatGraphs";
import { TimelineScrubber } from "../TimelineScrubber";
import { TerritoryMap } from "../TerritoryMap";

const bundle = sampleBundle as unknown as Bundle;

describe("Header", () => {
  it("renders world name", () => {
    render(
      <Header
        worldName={bundle.world_state.name}
        metadata={bundle.metadata}
        currentTurn={1}
        darkMode={true}
        onToggleDarkMode={() => {}}
      />,
    );
    expect(screen.getByText(bundle.world_state.name)).toBeInTheDocument();
  });
});

describe("FactionDashboard", () => {
  it("renders correct number of faction cards", () => {
    const { container } = render(
      <FactionDashboard
        civilizations={bundle.world_state.civilizations}
        history={bundle.history}
        currentTurn={1}
      />,
    );
    const cards = container.querySelectorAll(".rounded.border");
    expect(cards.length).toBe(bundle.world_state.civilizations.length);
  });
});

describe("EventLog", () => {
  it("renders events table", () => {
    render(
      <EventLog events={bundle.events_timeline} onJumpToTurn={() => {}} />,
    );
    expect(screen.getByText("Turn")).toBeInTheDocument();
    expect(screen.getByText("Type")).toBeInTheDocument();
  });
});

describe("ChroniclePanel", () => {
  it("renders without crashing", () => {
    const { container } = render(
      <ChroniclePanel
        chronicleEntries={bundle.chronicle_entries}
        eraReflections={bundle.era_reflections}
        currentTurn={1}
        maxTurn={bundle.metadata.total_turns}
      />,
    );
    expect(container.firstChild).toBeTruthy();
  });
});

describe("StatGraphs", () => {
  it("renders stat selector", () => {
    render(
      <StatGraphs
        civilizations={bundle.world_state.civilizations}
        history={bundle.history}
        namedEvents={bundle.named_events}
        currentTurn={1}
      />,
    );
    expect(screen.getByText("Asabiya")).toBeInTheDocument();
  });
});

describe("TimelineScrubber", () => {
  it("renders play button and speed selector", () => {
    render(
      <TimelineScrubber
        currentTurn={1}
        maxTurn={bundle.metadata.total_turns}
        playing={false}
        speed={1}
        history={bundle.history}
        namedEvents={bundle.named_events}
        onSeek={() => {}}
        onPlay={() => {}}
        onPause={() => {}}
        onSetSpeed={() => {}}
      />,
    );
    expect(screen.getByText(">")).toBeInTheDocument();
    expect(screen.getByText("1x")).toBeInTheDocument();
  });
});

describe("TerritoryMap", () => {
  it("renders correct number of region nodes", () => {
    const { container } = render(
      <TerritoryMap
        regions={bundle.world_state.regions}
        history={bundle.history}
        currentTurn={1}
        showRelationships={false}
        onToggleRelationships={() => {}}
      />,
    );
    const circles = container.querySelectorAll("circle");
    expect(circles.length).toBe(bundle.world_state.regions.length);
  });
});
