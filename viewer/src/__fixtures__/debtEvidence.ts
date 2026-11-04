/** Constructed fiscal records, not a simulation trajectory or reconciliation. */
import { comparisonBundle } from "./completedRunHistory";
import type { Event, FinanceCivSnapshot } from "../types";

export function debtEvidenceFixture() {
  const bundle = comparisonBundle([1, 3, 6, 10]);
  bundle.world_state.civilizations[0].treasury = 99999999;
  const base = bundle.history[0].finance!.civs.A;
  const finance = (debt: number, foreign_debt: number, debt_service: number, interest: number, borrowed: number): FinanceCivSnapshot =>
    ({ ...base, debt, foreign_debt, debt_service, interest, borrowed, shortfall: 3, arrears_turns: 2, defaults: 1 });
  bundle.history[0].finance!.civs = { A: finance(100, 30, 12, 4, 7), B: finance(0, 0, 0, 0, 0) };
  bundle.history[1].finance!.civs = { A: finance(250, 50, 20, 5, 90), B: finance(0, 0, 0, 0, 0) };
  bundle.history[1].finance!.totals = { issued_domestic: 99999, written_off: 88888, repaid_principal: 77777 };
  bundle.history[1].finance!.domestic_credit = { claims: { city: 20 }, civs: { A: { city: 20 } }, lenders: 2,
    merchant_due: 0, grievance: {}, holders: { A: { cities: { "Harbor Council": 20 }, rate: .04, foreign: { B: [50, .06] }, written_off: 11 } } };
  delete bundle.history[2].finance!.civs.A;
  bundle.history[3].finance!.civs.A = finance(99999999, 55555555, 5000, 2000, 10000);
  const event = (turn: number, event_type: string, actors: string[], event_id: string, description: string): Event => ({
    turn, event_type, actors, event_id, description, importance: 5, consequences: [],
  });
  bundle.events_timeline = [event(0, "loan_taken", ["A", "B"], "loan-0", "A borrows from B."),
    event(2, "state_default", ["A", "B"], "default-2", "A defaults; B is named as a creditor."),
    event(2, "fiscal_strain", ["A"], "strain-2", "A is under fiscal strain."),
    event(5, "debt_written_off", ["A"], "loss-5", "A's obligations are written off after its fall."),
    event(9, "loan_taken", ["A", "B"], "future-secret-event", "FUTURE_SECRET_CREDIT_EVENT")];
  return bundle;
}
