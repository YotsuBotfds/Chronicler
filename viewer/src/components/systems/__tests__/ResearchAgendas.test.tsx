import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { researchAgendaEvents, researchAgendaObservation } from "../../../__fixtures__/researchAgendaObservation";
import type { Bundle } from "../../../types";
import { ScientificClaims } from "../ScientificClaims";

afterEach(cleanup);
function props() {
  const snapshot = researchAgendaObservation();
  return { snapshot, currentTurn: 1,
    bundle: { history: [snapshot], events_timeline: structuredClone(researchAgendaEvents),
      world_state: { scientific_claims: { research_agendas: { current_cycle_id: 999 } } } } as unknown as Bundle,
    onSeek: vi.fn(), onSelectEvent: vi.fn(), onSelectRegion: vi.fn(), onSelectCivilization: vi.fn() };
}

describe("recorded finite research agenda inspector", () => {
  it("shows actual unit capacities and funding plans without inventing completed trial bodies", () => {
    const p = props(); render(<ScientificClaims {...p} />);
    const agenda = screen.getByLabelText("Finite research agendas");
    expect(agenda).toHaveTextContent("New research enabled.");
    expect(screen.getByText("2 lifetime enrolled seats")).toBeInTheDocument();
    expect(agenda).toHaveTextContent("originals through turn 11, all funding through turn 23 (inclusive)");
    expect(agenda).toHaveTextContent("no earlier than turn 25");
    expect(agenda).toHaveTextContent("not treasury payments");
    expect(agenda).toHaveTextContent("Complete historical trial and receipt contents are not inferred");
    const capacity = within(agenda).getByRole("table", { name: "Research capacity after simulation turn 0" });
    expect(within(capacity).getAllByRole("row")).toHaveLength(8);
    expect(within(capacity).getByRole("row", { name: "Paid trials 2 2 40" })).toBeInTheDocument();
    expect(screen.queryByRole("table", { name: /Scientific trial history/ })).not.toBeInTheDocument();
    expect(screen.getByText(/No dated trial resolution/)).toBeInTheDocument();
    expect(agenda).not.toHaveTextContent("999");
    const topics = screen.getByRole("table", { name: "Scientific propositions at snapshot 1" });
    expect(within(topics).getAllByText(/Metric: grain_output; comparator \/ intervention: 0 \/ 1; horizon: 1 turn/)).toHaveLength(2);
  });

  it("shows closed legacy membership as activation observations with unknown historical deadlines", () => {
    const p = props(), science = p.snapshot.scientific_claims!, plan = science.research_agendas!;
    plan.current_cycle_id = null;
    Object.assign(plan.cycles[0], { legacy_adopted: true, opening_roster_complete: false,
      opening_roster_scope: "observed_at_legacy_activation", closed_turn: 0,
      close_reason: "legacy funding closed prospectively at activation", original_deadline: null,
      funding_deadline: null, next_open_not_before: null });
    science.allocations = [{ seat: 0, region: 0, recipe: "irrigation", share: .6, confidence: .6, paid: 1 }];
    render(<ScientificClaims {...p} />);
    const ledger = screen.getByRole("table", { name: "Research cycle ledger after simulation turn 0", hidden: true });
    expect(ledger).toHaveTextContent("adopted legacy");
    expect(ledger).toHaveTextContent("Historical funding deadlines unknown");
    expect(ledger).toHaveTextContent("Historical opening roster unknown; seats observed at legacy activation");
    const allocation = screen.getByRole("table", { name: "Scientific allocations at snapshot 1" });
    expect(allocation).toHaveTextContent("Unknown at legacy activation");
    expect(allocation).toHaveTextContent("60%");
    expect(screen.getByRole("table", { name: "Scientific beliefs at snapshot 1" })).toHaveTextContent("50%");
  });

  it("distinguishes a research pause from dormancy and unfilled opportunities from paid failures", () => {
    const p = props(), plan = p.snapshot.scientific_claims!.research_agendas!;
    plan.enabled = false; plan.current_cycle_id = null;
    Object.assign(plan.cycles[0], { closed_turn: 0, close_reason: "research_paused",
      unfunded_replications: [0, 1], slot_reasons: { "replication:0": "no_eligible_received_question", "replication:1": "projected_treasury_floor" } });
    plan.capacity.trials.reserved = 0;
    render(<ScientificClaims {...p} />);
    expect(screen.getByText(/Academy science is active/)).toBeInTheDocument();
    const agenda = screen.getByLabelText("Finite research agendas");
    expect(agenda).toHaveTextContent("New research paused.");
    expect(agenda).toHaveTextContent("Already-paid trials, messages, retained evidence and ordinary paid adoption can continue");
    expect(agenda).toHaveTextContent("unpaid opportunities, not failed trials");
    expect(agenda).toHaveTextContent("No eligible academy has received this cycle's question");
  });

  it("uses actual paid canonical IDs rather than the later confidence row", () => {
    const p = props(), science = p.snapshot.scientific_claims!;
    science.allocations = [{ seat: 0, region: 0, recipe: "irrigation", share: .6, confidence: .6, paid: 1, claim_id: 0 },
      { seat: 0, region: 0, recipe: "masonry", share: .4, confidence: .4, paid: 0, claim_id: 1 }];
    render(<ScientificClaims {...p} />);
    const allocation = screen.getByRole("table", { name: "Scientific allocations at snapshot 1" });
    expect(within(allocation).getByRole("columnheader", { name: "Topic used at payment" })).toBeInTheDocument();
    expect(allocation).toHaveTextContent("60%");
    expect(screen.getByText(/Actual treasury paid this completed turn: 1\./)).toBeInTheDocument();
    expect(screen.getByText(/Later delivery or publication can change the end-turn confidence/)).toBeInTheDocument();
  });

  it("connects a known agenda announcement but hides future links even in a history gap", () => {
    const p = props(); p.currentTurn = 3;
    const view = render(<ScientificClaims {...p} />);
    fireEvent.click(screen.getByRole("button", { name: "Agenda announcement", hidden: true }));
    expect(p.onSelectEvent).toHaveBeenCalledWith(p.bundle.events_timeline[2]);
    p.bundle.events_timeline[2].turn = 1;
    view.rerender(<ScientificClaims {...p} />);
    expect(screen.queryByRole("button", { name: "Agenda announcement", hidden: true })).not.toBeInTheDocument();
    expect(screen.getByRole("list", { name: "Scientific claims events" })).not.toHaveTextContent("opens paid research agenda");
  });

  it("withholds present malformed mode including totals without displaying its body", () => {
    const p = props(); p.snapshot.scientific_claims!.research_agendas!.cycles[0].opened_turn = 4;
    p.snapshot.scientific_claims!.research_agendas!.blocked_reason = "SECRET_FUTURE";
    render(<ScientificClaims {...p} />);
    expect(screen.getByText(/Present research-agenda metadata is unsupported/)).toBeInTheDocument();
    expect(screen.queryByRole("table", { hidden: true })).not.toBeInTheDocument();
    expect(screen.queryByText("Trial spending")).not.toBeInTheDocument();
    expect(screen.queryByText(/SECRET_FUTURE/)).not.toBeInTheDocument();
  });

  it("keeps missing earlier rows unknown and preserves the agenda-absent legacy view", () => {
    const p = props();
    const view = render(<ScientificClaims {...p} snapshot={null} currentTurn={0} />);
    expect(screen.getByText(/No usable scientific-claims observation at turn 0/)).toBeInTheDocument();
    expect(screen.queryByLabelText("Finite research agendas")).not.toBeInTheDocument();
    delete p.snapshot.scientific_claims!.research_agendas;
    view.rerender(<ScientificClaims {...p} />);
    expect(screen.queryByLabelText("Finite research agendas")).not.toBeInTheDocument();
    expect(screen.getByText(/The pilot is active/)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Contextual propositions" })).toBeInTheDocument();
    expect(screen.queryByRole("columnheader", { name: "Topic used at payment" })).not.toBeInTheDocument();
  });
});
