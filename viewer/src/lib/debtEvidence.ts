import { amount as finite } from "./recordGuards";
import type { Bundle, Event, FinanceCivSnapshot } from "../types";
import { eventKey, eventKeyCount } from "./bundleIndex";

export interface DebtEvidenceRow {
  turn: number;
  sourceTurn: number | null;
  status: "recorded" | "missing" | "absent" | "ambiguous";
  explanation: string;
  sourceRef: string;
  values: Record<"debt" | "foreignDebt" | "borrowed" | "service" | "interestPaid" | "principalPaid" | "shortfall" | "arrears" | "defaults" | "writtenOff", number | null>;
  principalSources: string[];
  writtenOffSource: string | null;
}
export interface DebtClaimEvidence {
  label: string;
  kind: "domestic" | "foreign";
  principal: number;
  rate: number | null;
  sourceRef: string;
  rateSourceRef: string | null;
}
export interface DebtEventEvidence {
  event: Event;
  turn: number;
  role: "borrower" | "named creditor" | "fiscal subject";
  borrower: string | null;
  sourceRef: string;
  canInspect: boolean;
}
export interface DebtEvidenceReading {
  name: string;
  civilizationIndex: number | null;
  through: number;
  from: number;
  status: string;
  rows: DebtEvidenceRow[];
  selected: DebtEvidenceRow | null;
  claims: DebtClaimEvidence[];
  events: DebtEventEvidence[];
  coverage: string[];
}
const turn = (value: unknown): value is number => finite(value) && Number.isInteger(value);
const pointer = (value: string) => value.replace(/~/g, "~0").replace(/\//g, "~1");
const val = (value: unknown) => finite(value) ? value : null;
const empty = (): DebtEvidenceRow["values"] => ({ debt: null, foreignDebt: null, borrowed: null, service: null,
  interestPaid: null, principalPaid: null, shortfall: null, arrears: null, defaults: null, writtenOff: null });
const CREDIT_EVENTS = new Set(["loan_taken", "state_default", "debt_written_off"]);

/** Recorded fiscal cash flows are not a whole-turn principal stock reconciliation. */
export function readDebtEvidence(bundle: Bundle, through: number, civilizationIndex: number | null, window = 20): DebtEvidenceReading {
  const length = turn(window) ? Math.max(1, Math.min(100, window)) : 20;
  const result: DebtEvidenceReading = { name: "Civilization not selected", civilizationIndex, through,
    from: turn(through) ? Math.max(0, through - length + 1) : 0, status: "Choose a civilization to inspect its recorded fiscal flows.",
    rows: [], selected: null, claims: [], events: [], coverage: [] };
  if (!turn(through) || civilizationIndex === null || !turn(civilizationIndex) || !bundle.world_state.civilizations[civilizationIndex]) return result;
  const name = bundle.world_state.civilizations[civilizationIndex].name;
  result.name = `Civilization ${civilizationIndex} (name not recorded)`;
  if (bundle.world_state.civilizations.filter((civ) => civ.name === name).length !== 1) {
    result.status = "Repeated civilization name: name-keyed finance cannot identify this array record. No liability or creditor role is assigned.";
    return result;
  }
  const historicalName = bundle.history.some((row) => turn(row.turn) && row.turn <= through && (Object.hasOwn(row.civ_stats, name) || Object.hasOwn(row.finance?.civs ?? {}, name)))
    || bundle.events_timeline.some((event) => turn(event.turn) && event.turn + 1 <= through && (CREDIT_EVENTS.has(event.event_type) || event.event_type === "fiscal_strain") && event.actors.includes(name));
  if (!historicalName) { result.status = "No dated civilization name or finance evidence through the selected turn. Final-world fields do not fill this gap."; return result; }
  result.name = name;
  const prefix = bundle.history.map((snapshot, index) => ({ snapshot, index })).filter(({ snapshot }) => turn(snapshot.turn) && snapshot.turn <= through);
  let exact: { row: FinanceCivSnapshot; index: number } | null = null;
  for (let at = result.from; at <= through; at++) {
    const matches = prefix.filter(({ snapshot }) => snapshot.turn === at);
    const reading: DebtEvidenceRow = { turn: at, sourceTurn: at > 0 ? at - 1 : null, status: "missing", explanation: "Snapshot not recorded; no flow is carried forward.",
      sourceRef: "/history", values: empty(), principalSources: [], writtenOffSource: null };
    const found = matches[0];
    if (found) reading.sourceRef = `/history/${found.index}/finance`;
    if (matches.length > 1) { reading.status = "ambiguous"; reading.explanation = "Duplicate snapshot turn; fiscal observations are ambiguous."; }
    else if (found?.snapshot.finance) {
      const row = found.snapshot.finance.civs[name];
      if (!row) { reading.status = "absent"; reading.explanation = "Borrower absent from finance snapshot; pruned, fallen or unrecorded is not zero debt or zero payments."; }
      else {
        reading.status = "recorded";
        reading.explanation = at === 0 ? "Opening boundary recorded; a completed fiscal tick is not established." : "Boundary debt and the completed fiscal tick's recorded payments; units are nominal treasury units.";
        reading.sourceRef += `/civs/${pointer(name)}`;
        reading.values = { debt: val(row.debt), foreignDebt: val(row.foreign_debt), borrowed: at > 0 ? val(row.borrowed) : null,
          service: at > 0 ? val(row.debt_service) : null, interestPaid: at > 0 ? val(row.interest) : null, principalPaid: null,
          shortfall: at > 0 ? val(row.shortfall) : null, arrears: val(row.arrears_turns), defaults: val(row.defaults), writtenOff: null };
        const { service, interestPaid } = reading.values;
        if (service !== null && interestPaid !== null && service >= interestPaid) {
          reading.values.principalPaid = service - interestPaid;
          reading.principalSources = [`${reading.sourceRef}/debt_service`, `${reading.sourceRef}/interest`];
        } else if (service !== null && interestPaid !== null) reading.explanation += " Paid interest exceeds service: principal paid is unknown for this inconsistent row.";
        const held = found.snapshot.finance.domestic_credit?.holders?.[name];
        reading.values.writtenOff = val(held?.written_off);
        if (reading.values.writtenOff !== null) reading.writtenOffSource = `/history/${found.index}/finance/domestic_credit/holders/${pointer(name)}/written_off`;
        if (at === through) exact = { row, index: found.index };
      }
    } else if (found) reading.explanation = "Finance subsystem not recorded in this snapshot; flows and balances are unknown.";
    result.rows.push(reading);
  }
  result.selected = result.rows.at(-1) ?? null;
  result.status = result.selected?.explanation ?? result.status;
  if (exact) {
    const snapshot = bundle.history[exact.index];
    const credit = snapshot.finance?.domestic_credit;
    const held = credit?.holders?.[name];
    const source = `/history/${exact.index}/finance/domestic_credit/holders/${pointer(name)}`;
    for (const [key, label] of [["merchants", "Merchants in"], ["cities", "City"], ["guilds", "Guild"]] as const) {
      for (const [holder, principal] of Object.entries(held?.[key] ?? {})) if (finite(principal)) result.claims.push({
        label: `${label} ${holder}`, kind: "domestic", principal, rate: val(held?.rate), sourceRef: `${source}/${key}/${pointer(holder)}`,
        rateSourceRef: val(held?.rate) === null ? null : `${source}/rate`,
      });
    }
    for (const [lender, entry] of Object.entries(held?.foreign ?? {})) if (Array.isArray(entry) && finite(entry[0])) result.claims.push({
      label: lender, kind: "foreign", principal: entry[0], rate: val(entry[1]), sourceRef: `${source}/foreign/${pointer(lender)}/0`,
      rateSourceRef: val(entry[1]) === null ? null : `${source}/foreign/${pointer(lender)}/1`,
    });
  }
  bundle.events_timeline.forEach((event, index) => {
    const visible = event.turn + 1;
    if (!turn(event.turn) || visible < result.from || visible > through || (!CREDIT_EVENTS.has(event.event_type) && event.event_type !== "fiscal_strain")) return;
    const first = event.actors[0];
    const fiscal = event.event_type === "fiscal_strain";
    const role = first === name ? fiscal ? "fiscal subject" : "borrower" : !fiscal && event.actors.slice(1).includes(name) ? "named creditor" : null;
    if (!role) return;
    result.events.push({ event, turn: visible, role, borrower: fiscal ? null : first ?? null,
      sourceRef: `/events_timeline/${index}`, canInspect: eventKeyCount(bundle.events_timeline, eventKey(event)) === 1 });
  });
  result.events.sort((a, b) => a.turn - b.turn);
  result.coverage = [
    `Snapshot window ${result.from}–${through}; ${result.rows.filter((row) => row.status === "recorded").length} recorded fiscal boundaries of ${result.rows.length}. Gaps are unknown, never zero or interpolated.`,
    "All amounts are nominal treasury units, not grain, real purchasing power or personal wealth. Debt is outstanding principal and already includes its foreign subset; the two are not added.",
    "Snapshot T records completed tick T−1. Borrowed, debt service and paid interest refer to the fiscal tick; later-phase loans can change boundary debt outside recorded fiscal borrowing.",
    "Principal paid = recorded debt service − recorded PAID interest, including prepayments. It is never inferred from debt changes, new loans or write-offs. Unknown or inconsistent components leave principal unknown.",
    "Shortfall combines unpaid upkeep and unpaid debt service; it is not an isolated interest or principal arrears amount. Arrears are running turns; defaults and written-off amounts are cumulative, not this tick's flows.",
    "Named lender claims are explicit selected-boundary observations only; a rate describes a claim's boundary terms, not paid interest received. Borrower payments are not allocated to lenders from boundary shares. Missing or unnamed allocations remain unknown.",
    "Write-off amounts are shown only when explicitly exported per borrower. Omitted historical fields are unknown. Global finance totals and prose event amounts are not allocated to this civilization.",
    "Credit event actors follow the backend contract: first actor borrower, later named actors creditors; fiscal strain identifies its subject. Events are dated context, not a complete loan/payment ledger or proof of a metric's cause.",
    "Merchant mobility and public-granary purchase receipts record different domains; they do not establish debt payment receipts. Final world balances and future records are excluded.",
  ];
  return result;
}
