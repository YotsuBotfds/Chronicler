import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import systemsFixture from "../../../__fixtures__/systems_bundle.json";
import type { Bundle } from "../../../types";
import { accountsForEvent } from "../../../lib/historiography";
import { sampleField } from "../../../__fixtures__/historiographyField";
import { AppShell } from "../AppShell";
import { preloadPanels } from "../lazyPanels";
import { InWorldAccounts } from "../InWorldAccounts";

// Lazy panels render without a fallback once their chunks are loaded (lazyPanels.tsx).
beforeAll(() => preloadPanels());
afterEach(cleanup);

describe("InWorldAccounts", () => {
  it("renders told, lost, silent and plain accounts with their biases", () => {
    render(<InWorldAccounts accounts={accountsForEvent(sampleField(), "4:war:1")} />);
    const section = screen.getByLabelText("In-world accounts");
    expect(section).toHaveTextContent("4 chroniclers");
    expect(section).toHaveTextContent("contested (lost, magnitude, ruler, silence)");
    expect(section).toHaveTextContent("The Ashkari chronicles (inflate, praise)");
    expect(section).toHaveTextContent("In the glorious reign of Chancellor Zhara");
    expect(section).toHaveTextContent("lost: their archive was sacked (turn 10)");
    expect(section).toHaveTextContent("The temple scribes of the Faith of Ashkari pass over it in silence.");
    expect(section).toHaveTextContent("The Thornwall chronicles tell it as it happened.");
  });

  it("renders nothing without accounts", () => {
    const { container } = render(<InWorldAccounts accounts={null} />);
    expect(container).toBeEmptyDOMElement();
  });
});

function renderShell(bundle: Bundle, currentTurn: number) {
  render(
    <AppShell
      surface="overview"
      onSurfaceChange={vi.fn()}
      bundle={bundle}
      bundleLoading={false}
      error={null}
      isLive={false}
      connected={false}
      serverState="completed"
      currentTurn={currentTurn}
      playing={false}
      speed={1}
      onSeek={vi.fn()}
      onPlay={vi.fn()}
      onPause={vi.fn()}
      onSetSpeed={vi.fn()}
      lobbyInit={null}
      starting={false}
      onOpenBundleFile={vi.fn()}
    />,
  );
}

describe("AppShell event inspector", () => {
  const systems = systemsFixture as unknown as Bundle;
  const visible = systems.events_timeline
    .filter((event) => event.turn <= 120)
    .sort((a, b) => b.turn - a.turn)
    .slice(0, 24);
  const target = visible.find((event) => event.event_id)!;

  function pin() {
    fireEvent.click(screen.getByRole("button", { name: "Event Log" }));
    const rows = document.querySelectorAll(".phase75-event-row");
    const row = [...rows].find((el) => el.textContent?.includes(target.description))!;
    fireEvent.click(row);
    return document.querySelector(".phase75-right-rail") as HTMLElement;
  }

  it("shows the in-world accounts of a pinned event", () => {
    expect(target).toBeDefined();
    renderShell({ ...systems, historiography: sampleField(target.event_id) }, 120);
    const inspector = pin();
    const section = within(inspector).getByLabelText("In-world accounts");
    expect(section).toHaveTextContent("the Ashkari host won the day");
  });

  it("adds nothing for a bundle without the field", () => {
    renderShell(systems, 120);
    const inspector = pin();
    expect(within(inspector).getByText(target.event_type)).toBeInTheDocument();
    expect(within(inspector).queryByLabelText("In-world accounts")).not.toBeInTheDocument();
  });
});
