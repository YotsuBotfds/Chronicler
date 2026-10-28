import { describe, expect, it } from "vitest";
import { buildEventFeed, eventProvenance } from "../../components/phase75/appShellHelpers";
import { eventSnapshotTurn, observationEventKnown } from "../observedSystems";

const kinds = ["occupational_injury", "harvest_forecast_issued", "harvest_forecast_delivered",
  "harvest_forecast_resolved", "harvest_preparedness", "harvest_gathering_held", "harvest_gathering_cancelled",
  "scientific_claim_proposed", "scientific_trial_funded", "scientific_trial_completed", "scientific_trial_cancelled",
  "scientific_trial_failed", "scientific_evidence_received", "scientific_adoption_allocated",
  "scientific_research_agenda_opened", "scientific_research_agenda_closed", "scientific_research_capacity_blocked"];
const event = (event_type: string, turn: number, id: string, actors = ["Old realm"], causes: string[] = []) =>
  ({ event_type, turn, event_id: id, actors, causes });

describe("completed-turn observation event clocks", () => {
  it.each(kinds)("dates %s to its containing snapshot", (kind) => {
    const receipt = event(kind, 6, "receipt");
    expect(observationEventKnown(receipt, 5)).toBe(false);
    expect(observationEventKnown(receipt, 6)).toBe(true);
    expect(eventSnapshotTurn(receipt)).toBe(7);
    expect(buildEventFeed([receipt], 6, null)).toEqual([]);
    expect(buildEventFeed([receipt], 7, null)).toEqual([receipt]);
  });

  it("keeps legacy dates and fills the feed with known rows after excluding future receipts", () => {
    const future = Array.from({ length: 30 }, (_, n) => event("harvest_forecast_issued", 6, `future:${n}`));
    const known = Array.from({ length: 30 }, (_, n) => event("war", 6, `known:${n}`, ["Other realm"]));
    expect(observationEventKnown(known[0], 5)).toBe(true);
    expect(eventSnapshotTurn(known[0])).toBe(6);
    expect(buildEventFeed([...future, ...known], 6, null)).toEqual(known.slice(0, 24));
    // Unknown focused events must not meet the eight-row focus threshold.
    expect(buildEventFeed([...future, ...known], 6, "Old realm")).toEqual(known.slice(0, 24));
  });

  it("uses the selected snapshot's source even when currentTurn lies in a history gap", () => {
    const receipt = event("harvest_preparedness", 6, "receipt");
    const legacy = event("trade", 8, "legacy");
    expect(buildEventFeed([receipt, legacy], 9, null, 5)).toEqual([legacy]);
    expect(buildEventFeed([receipt, legacy], 9, null, 6)).toEqual([legacy, receipt]);
  });

  it("cuts off future actual provenance and hides a pinned receipt before its source tick", () => {
    const cause = event("harvest_forecast_delivered", 6, "cause");
    const selected = event("harvest_preparedness", 6, "selected", ["Old realm"], ["cause"]);
    const future = event("harvest_forecast_resolved", 7, "future", ["Old realm"], ["selected"]);
    const legacy = event("trade", 7, "legacy", ["Old realm"], ["selected"]);
    const events = [cause, selected, future, legacy];
    expect(eventProvenance(events, selected, 6)).toEqual({ causes: [], effects: [] });
    expect(eventProvenance(events, selected, 7)).toEqual({ causes: [cause], effects: [legacy] });
    expect(eventProvenance(events, selected, 8)).toEqual({ causes: [cause], effects: [future, legacy] });
    expect(eventProvenance(events, selected)).toEqual({ causes: [cause], effects: [future, legacy] });
  });
});
