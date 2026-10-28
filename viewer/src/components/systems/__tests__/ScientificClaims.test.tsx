import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import observations from "../../../__fixtures__/scientific_claims_observations.json";
import type { Bundle, TurnSnapshot } from "../../../types";
import { ScientificClaims } from "../ScientificClaims";

afterEach(cleanup);
function props(turn = 13) {
  const history = structuredClone(observations.history) as unknown as TurnSnapshot[];
  return { bundle: { history, events_timeline: [], world_state: { scientific_claims: { trial_spent: 999 } } } as unknown as Bundle,
    snapshot: history.find((row) => row.turn === turn)!, currentTurn: turn,
    onSeek: vi.fn(), onSelectEvent: vi.fn(), onSelectRegion: vi.fn(), onSelectCivilization: vi.fn() };
}

describe("recorded academy claims and evidence inspector", () => {
  it("shows contextual local confidence and real paid effort without multiplying per-recipe expense", () => {
    const p = props(); render(<ScientificClaims {...p} />);
    expect(screen.getByText(/Recorded after simulation turn 12/)).toBeInTheDocument();
    expect(screen.getByText(/Actual treasury paid this completed turn: 5\./)).toBeInTheDocument();
    expect(screen.getByText(/count does not establish independent world units/)).toBeInTheDocument();
    expect(screen.getByText(/not a probability that a technique is universally true/)).toBeInTheDocument();
    expect(within(screen.getByRole("table", { name: "Scientific propositions at snapshot 13" })).getAllByText(/soil band 3, water band 2/)).toHaveLength(2);
    const beliefs = screen.getByRole("table", { name: "Scientific beliefs at snapshot 13" });
    fireEvent.click(within(beliefs).getAllByRole("button", { name: "Avalon" })[0]);
    expect(p.onSelectRegion).toHaveBeenCalledWith("Avalon");
    expect(screen.queryByText("999")).not.toBeInTheDocument();
  });

  it("keeps modelled outputs separate from measured evidence and seeks completed-trial snapshots", () => {
    const p = props(2); render(<ScientificClaims {...p} />);
    const history = screen.getByRole("table", { name: "Scientific trial history through snapshot 2" });
    fireEvent.click(within(history).getAllByRole("button", { name: "1 / 2" })[0]);
    expect(p.onSeek).toHaveBeenCalledWith(2);
    expect(within(history).getAllByText(/Modelled grain output, control \/ treatment:/)).toHaveLength(2);
    expect(within(history).getAllByText(/Measured grain output, control \/ treatment:/)).toHaveLength(2);
    expect(within(history).getAllByText(/Reported support: No/)).toHaveLength(2);
    expect(within(history).queryByText(/13 \/ 14/)).not.toBeInTheDocument();
  });

  it("distinguishes archived receipts from evidence currently used by policy", () => {
    const p = props(7);
    expect(p.snapshot.scientific_claims!.evidence_receipts).toBeGreaterThan(0);
    expect(p.snapshot.scientific_claims!.beliefs.every((row) => row.last_evidence_turn == null && row.independent_groups === 0)).toBe(true);
    render(<ScientificClaims {...p} />);
    const table = screen.getByRole("table", { name: "Scientific beliefs at snapshot 7" });
    expect(within(table).getByRole("columnheader", { name: "Last evidence used by policy" })).toBeInTheDocument();
    expect(within(table).getAllByText("None applicable")).toHaveLength(p.snapshot.scientific_claims!.beliefs.length);
    expect(screen.getByText(/Archived receipts can remain/)).toBeInTheDocument();
  });

  it("labels sham measurements and withholds future evidence including totals", () => {
    const p = props(2); p.snapshot.scientific_claims!.controls.uninformative_tests = true;
    const view = render(<ScientificClaims {...p} />);
    expect(screen.getByText(/sham measurements with no treatment information/)).toBeInTheDocument();
    p.snapshot.scientific_claims!.beliefs[0].last_evidence_turn = 13;
    view.rerender(<ScientificClaims {...p} />);
    expect(screen.getByText(/No usable scientific-claims observation/)).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
    expect(screen.queryByText("Trial spending")).not.toBeInTheDocument();
  });

  it("filters newly emitted events by source and keeps event selection connected", () => {
    const p = props(2); p.currentTurn = 4;
    const known = { turn: 1, event_type: "scientific_trial_completed", event_id: "known", actors: [],
      importance: 3, description: "A noisy trial measurement was recorded.", consequences: [] };
    const future = { ...known, turn: 2, event_id: "future", description: "A future receipt." };
    p.bundle.events_timeline = [known, future];
    render(<ScientificClaims {...p} />);
    const list = screen.getByRole("list", { name: "Scientific claims events" });
    expect(within(list).queryByText(future.description)).not.toBeInTheDocument();
    fireEvent.click(within(list).getByText(known.description));
    expect(p.onSelectEvent).toHaveBeenCalledWith(known);
  });

  it("connects recorded trial provenance but withholds a future linked event", () => {
    const p = props(2);
    const known = { turn: 1, event_type: "scientific_trial_completed", event_id: "known", actors: [],
      importance: 3, description: "Known resolution receipt.", consequences: [] };
    const future = { ...known, turn: 2, event_id: "future", description: "Unobserved funding receipt." };
    p.bundle.events_timeline = [known, future];
    p.snapshot.scientific_claims!.trials_resolved[0].event_id = known.event_id;
    p.snapshot.scientific_claims!.trials_resolved[0].funded_event_id = future.event_id;
    render(<ScientificClaims {...p} />);
    fireEvent.click(screen.getByRole("button", { name: "Resolution event" }));
    expect(p.onSelectEvent).toHaveBeenCalledWith(known);
    expect(screen.queryByRole("button", { name: "Funding event" })).not.toBeInTheDocument();
  });

  it("keeps missing earlier history unknown and omits an entirely unrecorded feature", () => {
    const p = props(1); delete p.snapshot.scientific_claims;
    const view = render(<ScientificClaims {...p} />);
    expect(screen.getByText(/unknown/)).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
    p.bundle.history = [p.snapshot]; view.rerender(<ScientificClaims {...p} />);
    expect(view.container).toBeEmptyDOMElement();
  });
});
