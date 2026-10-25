import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import systemsFixture from "../../../__fixtures__/systems_bundle.json";
import type { Bundle } from "../../../types";
import { sampleLanguages } from "../../../__fixtures__/languagesField";
import { AppShell } from "../AppShell";
import { LanguagesPanel } from "../LanguagesPanel";

afterEach(cleanup);

describe("LanguagesPanel", () => {
  it("shows a selection's names, a glossary and an etymology", () => {
    render(<LanguagesPanel field={sampleLanguages()} turn={70} selected={{ kind: "region", ref: 0 }} />);
    const names = screen.getByLabelText("Names of the selection");
    expect(names).toHaveTextContent("Eskelbor Dorrathi (its own people) 'green plain' · kept from the earlier local name");
    expect(names).toHaveTextContent("Ashkelvor Kethani");
    const glossary = screen.getByLabelText("Glossary");
    expect(glossary).toHaveTextContent("Land Eskelbor Verdant Plains 'green plain'");
    fireEvent.click(within(names).getByRole("button", { name: "Eskelbor" }));
    const ety = screen.getByLabelText("Etymology");
    expect(ety).toHaveTextContent("Dorrathi kept from the earlier local name (turn 30)");
    expect(ety).toHaveTextContent("Eskelbor turn 60 (a o u > e e i when the next syllable has i)");
    expect(ety).toHaveTextContent("Kethani coined (turn 0) from ashkel 'green' + vor 'plain'");
  });

  it("switches language through the family tree", () => {
    render(<LanguagesPanel field={sampleLanguages()} turn={70} />);
    const select = screen.getByRole("combobox");
    fireEvent.change(select, { target: { value: "0" } });
    expect(screen.getByLabelText("Glossary")).toHaveTextContent("People Kethaniki Kethani Empire 'Kethani people'");
    expect(screen.getByText(/Kethaniki to its speakers/)).toBeInTheDocument();
  });

  it("renders nothing without the field", () => {
    const { container } = render(<LanguagesPanel field={undefined} turn={0} />);
    expect(container).toBeEmptyDOMElement();
  });
});

function renderShell(bundle: Bundle) {
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
      currentTurn={70}
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

describe("AppShell languages section", () => {
  const systems = systemsFixture as unknown as Bundle;

  it("adds a Languages section when the bundle carries the field", () => {
    renderShell({ ...systems, languages: sampleLanguages() });
    const inspector = document.querySelector(".phase75-right-rail") as HTMLElement;
    expect(within(inspector).getByRole("button", { name: /Languages/ })).toBeInTheDocument();
    expect(within(inspector).getByLabelText("Glossary")).toHaveTextContent("Eskelbor");
  });

  it("adds nothing for a bundle without the field", () => {
    renderShell(systems);
    const inspector = document.querySelector(".phase75-right-rail") as HTMLElement;
    expect(within(inspector).queryByLabelText("Languages")).not.toBeInTheDocument();
  });
});
