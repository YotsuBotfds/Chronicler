"""Bounded observer checks for recorded institutional science receipts.

The host supplies the expansion audit's shared row/event/as-of bounds. This
module imports no simulation runtime and never reconstructs missing archives.
"""
from __future__ import annotations

from collections import Counter
import math
from typing import Mapping

SYSTEM = "scientific_claims"
LEGACY_RULE = "current-context-v1"
PUBLICATION_RULES = (LEGACY_RULE, "funded-context-v2")
EVENT_KINDS = frozenset(("scientific_claim_proposed", "scientific_trial_funded",
    "scientific_trial_completed", "scientific_trial_cancelled", "scientific_trial_failed",
    "scientific_evidence_received", "scientific_adoption_allocated"))
COUNTERS = ("seats", "claims", "trials", "completed", "cancelled", "failed",
    "trial_spent", "effort_spent", "evidence_receipts", "expired_messages", "withheld_results")


def integer(value):
    return value if type(value) is int else None


def number(value):
    try:
        return value if type(value) in (int, float) and math.isfinite(value) else None
    except OverflowError:
        return None


def observed_defaults():
    return {"recorded_turns": 0, "unique_proposition_ids": 0,
        "funding_events": 0, "evidence_receipt_events": 0,
        "receipt_events_with_forwarded_cause": 0, "resolved_trial_receipts": 0,
        "completed_trial_receipts": 0, "cancelled_trial_receipts": 0, "failed_trial_receipts": 0,
        "resolved_replication_receipts": 0, "costs_attached_to_resolved_trials": 0,
        "allocation_rows": 0, "paid_seat_allocations": 0, "allocation_funds": 0,
        "reported_allocation_events": 0, "current_policy_belief_rows": 0,
        "belief_rows_with_declared_groups": 0, "unique_declared_dependence_groups": 0,
        "latest_cumulative_counters": None, "latest_counter_source_turn": None,
        "within_span_counter_increments": {key: 0 for key in COUNTERS},
        "publication_rules_observed": [], "resolved_trial_details": [], "belief_details": []}


class ScientificReceiptsAudit:
    def __init__(self, host):
        self.a = host
        self.out = host.observed[SYSTEM]
        self.claims, self.trials, self.groups = {}, set(), set()
        self.all_claim_ids = set()
        self.previous = None
        self.last_source, self.span_start = None, None
        self.events_by_turn = None
        self.detail_omissions = Counter()

    def finding(self, code, source, detail, rid=None, severity="error"):
        self.a.finding(SYSTEM, code, source, detail, rid, severity)

    def check(self, key, good):
        self.a.check(SYSTEM + "." + key, "verified" if good else "failed")

    def dependency(self, child, parent, source, rid):
        if child is None or parent is None:
            self.a.check(SYSTEM + ".recorded_dependencies", "unavailable")
            return
        candidates = [row for row in self.a.events.get(child, [])
                      if integer(row.get("turn")) is not None and row["turn"] <= source]
        causes = candidates[0].get("causes") if len(candidates) == 1 else None
        if not isinstance(causes, list):
            self.a.check(SYSTEM + ".recorded_dependencies", "unavailable")
        else:
            if len(causes) > 100:
                self.a.truncated.add("max_event_causes")
            good = parent in causes[:100]
            self.check("recorded_dependencies", good)
            if not good:
                self.finding("missing_recorded_dependency", source,
                             "A dated trial event omits its recorded proposal/funding dependency.", rid)

    def detail(self, table, row):
        if len(self.out[table]) < self.a.limits.max_details:
            self.out[table].append(row)
        else:
            self.detail_omissions[table] += 1

    def quantities(self, row, fields, source, rid=None, *, whole=False):
        good = self.a.quantities(row, fields, SYSTEM, source, rid)
        if whole:
            for field in fields:
                value = number(row.get(field))
                if value is not None and value % 1:
                    self.finding("fractional_science_count", source,
                                 f"{field} must be a whole count or treasury payment.", rid)
                    good = False
        return good

    def _events(self, source):
        if self.events_by_turn is None:
            self.events_by_turn = {}
            for rows in self.a.events.values():
                for event in rows:
                    turn = integer(event.get("turn"))
                    if turn is not None and event.get("event_type") in EVENT_KINDS:
                        self.events_by_turn.setdefault(turn, []).append(event)
        if not self.a.event_complete:
            self.out["funding_events"] = self.out["evidence_receipt_events"] = None
            self.out["receipt_events_with_forwarded_cause"] = None
            self.a.check(SYSTEM + ".timeline_mechanisms", "unavailable")
            return None
        events = self.events_by_turn.get(source, [])
        unique = {}
        for event in events:
            unique.setdefault(event["event_id"], event)
        for event in unique.values():
            kind = event["event_type"]
            if kind == "scientific_trial_funded":
                self.out["funding_events"] += 1
            elif kind == "scientific_evidence_received":
                self.out["evidence_receipt_events"] += 1
                causes = event.get("causes")
                if isinstance(causes, list):
                    if len(causes) > 100:
                        self.a.truncated.add("max_event_causes")
                    forwarded = any(isinstance(cause, str) and any(
                        e.get("event_type") == kind and integer(e.get("turn")) is not None
                        and e["turn"] <= source for e in self.a.events.get(cause, []))
                        for cause in causes[:100])
                    self.out["receipt_events_with_forwarded_cause"] += int(forwarded)
        return Counter(event["event_type"] for event in unique.values())

    def process(self, state, source, snapshot):
        if self.last_source is None or self.last_source + 1 != source:
            # Summaries do not carry cohort identity. Across an unrecorded gap
            # neither unchanged identity nor a fresh cohort can be proved.
            self.claims.clear()
            self.trials.clear()
            self.previous = None
            self.span_start = source
        self.last_source = source
        self.out["recorded_turns"] += 1
        tables = {}
        complete = True
        for name in ("propositions", "trials_resolved", "beliefs", "allocations"):
            tables[name], valid = self.a.rows(state.get(name), SYSTEM, source, name)
            complete &= valid
        valid_counts = self.quantities(state, (*COUNTERS, "pending_messages"), source, whole=True)
        if valid_counts:
            if (state["seats"] > 20 or state["claims"] > 20 or state["trials"] > 40
                    or state["evidence_receipts"] > 800 or state["pending_messages"] > 1200):
                self.finding("science_capacity_exceeded", source, "Counts exceed the bounded science state contract.")
            if state["completed"] + state["cancelled"] + state["failed"] > state["trials"]:
                self.finding("resolved_counts_exceed_trials", source, "Resolved status totals exceed funded trials.")
            good = state["trial_spent"] == 2 * state["trials"]
            self.check("fixed_trial_cost", good)
            if not good:
                self.finding("trial_cost_total_mismatch", source, "Recorded trial expense differs from two treasury units per funded trial.")
        controls = state.get("controls")
        if (not isinstance(controls, Mapping) or set(controls) != {
                "withhold_information", "transmission_enabled", "uninformative_tests"}
                or any(type(v) is not bool for v in controls.values())):
            self.finding("invalid_science_controls", source, "Recorded information controls must be three explicit booleans.")
            controls = {}
        rule = state.get("publication_rule", LEGACY_RULE)
        if rule not in PUBLICATION_RULES:
            self.finding("unknown_publication_rule", source, "Publication rule is unknown; no rule semantics inferred.")
        elif rule not in self.out["publication_rules_observed"]:
            self.out["publication_rules_observed"].append(rule)

        chronology_ok = True
        claims_here = {}
        for row in tables["propositions"]:
            proposed = integer(row.get("proposed_turn"))
            if proposed is None or not 0 <= proposed <= source:
                self.finding("future_or_undated_proposition", source, "Unavailable actual proposition evidence is withheld.")
                chronology_ok = False
                continue
            cid = integer(row.get("id"))
            if cid is None or cid < 0 or cid in claims_here:
                self.finding("invalid_or_duplicate_claim_id", source, "Propositions need unique nonnegative cohort-local IDs.")
                continue
            claims_here[cid] = row
            identity = (row.get("recipe"), row.get("origin_seat"), proposed, row.get("context"), row.get("threshold"), row.get("event_id"))
            if cid in self.claims and self.claims[cid] != identity:
                self.finding("changed_proposition_identity", source, "An existing proposition changed its immutable recorded identity.", cid)
            self.claims.setdefault(cid, identity)
            self.all_claim_ids.add(cid)
            self.a.event_ref(row.get("event_id"), "scientific_claim_proposed", proposed, SYSTEM, source, cid)
            threshold = number(row.get("threshold"))
            if threshold is None or threshold < 0:
                self.finding("invalid_claim_threshold", source, "Proposition threshold must be finite and nonnegative.", cid)
        self.out["unique_proposition_ids"] = len(self.all_claim_ids)
        if complete and chronology_ok and valid_counts and state["claims"] != len(claims_here):
            self.finding("proposition_count_mismatch", source, "Cumulative claim count disagrees with the complete dated proposition table.")
        statuses = Counter()
        for row in tables["trials_resolved"]:
            funded, planned, resolved = (integer(row.get(k)) for k in ("funded_turn", "completion_turn", "resolved_turn"))
            if funded is None or resolved is None or not 0 <= funded <= resolved <= source:
                self.finding("future_or_undated_trial", source, "Unavailable actual trial evidence is withheld; planned completion alone is not resolution.")
                chronology_ok = False
                continue
            if resolved != source:
                self.finding("replayed_trial_resolution", source, "Resolved trial rows belong only to their actual resolution turn.")
                continue
            tid, cid = integer(row.get("id")), integer(row.get("claim"))
            if tid is None or tid < 0 or tid in self.trials:
                self.finding("invalid_or_duplicate_trial_id", source, "A cohort-local resolved trial ID repeats or is invalid.")
                continue
            status = row.get("status")
            if status not in ("completed", "cancelled", "failed"):
                self.finding("invalid_resolved_trial_status", source, "A resolution receipt needs a terminal trial status.", tid)
                continue
            inputs = row.get("inputs")
            if status == "completed" and isinstance(inputs, Mapping):
                measured = integer(inputs.get("turn"))
                if measured is None or not 0 <= measured <= source:
                    self.finding("future_or_undated_measurement_inputs", source,
                                 "Unavailable actual measurement inputs and their result identities are withheld.")
                    chronology_ok = False
                    continue
            if planned is None or planned < funded or (status == "completed" and resolved < planned):
                self.finding("inverted_trial_dates", source, "Trial planning/funding/resolution dates disagree.", tid)
            claim = claims_here.get(cid)
            if claim is None:
                self.finding("unknown_science_claim", source, "Resolved trial has no available dated proposition; its body is withheld.")
                chronology_ok = False
                continue
            self.trials.add(tid)
            if claim is not None and funded < claim["proposed_turn"]:
                self.finding("funding_before_proposal", source, "Trial funding precedes the recorded proposition.", tid)
            funded_ref = self.a.event_ref(row.get("funded_event_id"), "scientific_trial_funded", funded, SYSTEM, source, tid)
            resolved_ref = self.a.event_ref(row.get("event_id"), "scientific_trial_" + status, resolved, SYSTEM, source, tid)
            proposal_ref = self.a.event_ref(claim.get("event_id"), "scientific_claim_proposed", claim["proposed_turn"], SYSTEM, source, cid)
            self.dependency(funded_ref, proposal_ref, source, tid)
            self.dependency(resolved_ref, funded_ref, source, tid)
            cost_ok = self.quantities(row, ("cost",), source, tid, whole=True)
            if cost_ok and row["cost"] != 2:
                self.finding("trial_payment_mismatch", source, "Recorded paid trial cost differs from the fixed two-unit contract.", tid)
            cost = row["cost"] if cost_ok else 0
            statuses[status] += 1
            self.out["resolved_trial_receipts"] += 1
            self.out[status + "_trial_receipts"] += 1
            self.out["costs_attached_to_resolved_trials"] += cost
            parent = integer(row.get("parent"))
            self.out["resolved_replication_receipts"] += int(parent is not None and parent >= 0)
            if status == "completed":
                good_outputs = self.quantities(row, ("control_output", "treatment_output", "observed_control", "observed_treatment"), source, tid)
                informative = row.get("informative")
                if type(informative) is not bool or (good_outputs and informative != (row["control_output"] > 0 and row["observed_control"] > 0)):
                    self.finding("informative_flag_mismatch", source, "Informative status disagrees with positive physical/comparator observations.", tid)
                threshold = number(claim.get("threshold")) if claim is not None else None
                if good_outputs and informative is True and threshold is not None:
                    supports = (row["observed_treatment"] - row["observed_control"]) / row["observed_control"] >= threshold
                    good = type(row.get("supports")) is bool and row["supports"] == supports
                    self.check("support_arithmetic", good)
                    if not good:
                        self.finding("support_arithmetic_mismatch", source, "Recorded support differs from the noisy observed comparison and threshold.", tid)
                elif informative is False and row.get("supports") is not None:
                    self.finding("support_without_information", source, "Uninformative physical observations must not carry a support verdict.", tid)
                if isinstance(inputs, Mapping):
                    if inputs.get("turn") != funded or (claim is not None and inputs.get("context") != claim.get("context")):
                        self.finding("funded_context_mismatch", source, "Archived measurement inputs disagree with funding date or proposition context.", tid)
                else:
                    self.a.check(SYSTEM + ".funded_context", "unavailable")
                group = row.get("dependence_group")
                if isinstance(group, str) and group:
                    self.groups.add(group)
                else:
                    self.finding("missing_dependence_group", source, "Completed trial lacks its declared dependence group.", tid, "warning")
            self.detail("resolved_trial_details", {"id": tid, "recorded_span_start": self.span_start,
                "claim": cid, "seat": integer(row.get("seat")),
                "payer": integer(row.get("payer")), "funded_turn": funded, "planned_completion_turn": planned,
                "resolved_turn": resolved, "status": status, "cost": cost if cost_ok else None,
                "parent": parent, "funded_event_id": self.a.label(row.get("funded_event_id", "")),
                "resolved_event_id": self.a.label(row.get("event_id", "")),
                "source_data": self.a.label(row.get("source_data", "")),
                "declared_dependence_group": self.a.label(row.get("dependence_group", ""))})
        self.out["unique_declared_dependence_groups"] = len(self.groups)

        seen_beliefs = set()
        for row in tables["beliefs"]:
            date = integer(row.get("last_evidence_turn"))
            if (row.get("last_evidence_turn") is not None and (date is None or not 0 <= date <= source)):
                self.finding("future_or_undated_belief_evidence", source, "Unavailable actual belief evidence is withheld.")
                chronology_ok = False
                continue
            key = (integer(row.get("seat")), integer(row.get("claim")))
            if None in key or min(key) < 0 or key in seen_beliefs:
                self.finding("invalid_or_duplicate_belief", source, "Current belief rows need unique seat/claim IDs.")
                continue
            seen_beliefs.add(key)
            if key[1] not in claims_here:
                self.finding("unknown_science_claim", source, "Belief has no available dated proposition; its body is withheld.")
                chronology_ok = False
                continue
            confidence, groups = number(row.get("confidence")), integer(row.get("independent_groups"))
            if confidence is None or not 0 <= confidence <= 1 or groups is None or not 0 <= groups <= 40:
                self.finding("invalid_science_belief", source, "Confidence/group counts are outside their recorded bounds.")
                continue
            if groups == 0 and not math.isclose(confidence, .5, abs_tol=1e-12):
                self.finding("neutral_prior_mismatch", source, "Zero policy-visible groups must retain the one-half prior.")
            if date is not None:
                self.a.event_ref(row.get("last_evidence_event_id"), "scientific_evidence_received", date, SYSTEM, source, key)
            elif row.get("last_evidence_event_id") or groups:
                self.finding("missing_belief_evidence_date", source, "Policy-visible evidence requires an actual receipt date.")
            self.out["current_policy_belief_rows"] += 1
            self.out["belief_rows_with_declared_groups"] += int(groups > 0)
            self.detail("belief_details", {"source_turn": source, "seat": key[0], "claim": key[1],
                "seat_name": self.a.label(row.get("seat_name", "")),
                "region": integer(row.get("region")), "region_name": self.a.label(row.get("region_name", "")),
                "owner": integer(row.get("owner")), "owner_name": self.a.label(row.get("owner_name", "")),
                "confidence": confidence, "declared_policy_groups": groups, "last_used_receipt_turn": date})

        payments, shares, seen_allocations, report_events = {}, {}, set(), set()
        for row in tables["allocations"]:
            key = (integer(row.get("seat")), row.get("recipe"))
            if key[0] is None or key[0] < 0 or not isinstance(key[1], str) or key in seen_allocations:
                self.finding("invalid_or_duplicate_allocation", source, "Paid allocation rows need unique seat/recipe IDs within their turn.")
                continue
            seen_allocations.add(key)
            if key[1] not in {claim.get("recipe") for claim in claims_here.values() if isinstance(claim.get("recipe"), str)}:
                self.finding("unknown_science_claim", source, "Allocation has no available dated proposition recipe; its body is withheld.")
                chronology_ok = False
                continue
            if not self.quantities(row, ("share", "confidence", "paid"), source, key):
                continue
            if row["share"] > 1 or row["confidence"] > 1 or row["paid"] not in (0, 1):
                self.finding("invalid_allocation_bounds", source, "Shares/confidence must be probabilities and row payment zero or one.")
            seat = key[0]
            shares[seat] = shares.get(seat, 0) + row["share"]
            payments[seat] = payments.get(seat, 0) + row["paid"]
            self.out["allocation_rows"] += 1
            self.out["allocation_funds"] += row["paid"]
            if row.get("event_id"):
                ref = self.a.event_ref(row["event_id"], "scientific_adoption_allocated", source, SYSTEM, source, key)
                if ref is not None:
                    report_events.add(ref)
        for seat in shares:
            good = math.isclose(shares[seat], 1, rel_tol=1e-8, abs_tol=1e-7) and payments[seat] == 1
            self.check("paid_allocation_split", good)
            if not good:
                self.finding("allocation_split_or_payment_mismatch", source, "Each allocated seat must spend one treasury unit once and split shares to one.", seat)
        self.out["paid_seat_allocations"] += sum(value == 1 for value in payments.values())
        self.out["reported_allocation_events"] += len(report_events)
        events = self._events(source)
        clean = {key: state[key] for key in COUNTERS} if valid_counts and chronology_ok else None
        previous = self.previous
        if clean is not None:
            self.out["latest_cumulative_counters"] = clean
            self.out["latest_counter_source_turn"] = source
            if previous is not None and previous[0] + 1 == source:
                deltas = {key: clean[key] - previous[1][key] for key in COUNTERS}
                for key, value in deltas.items():
                    self.check("counter_monotonicity", value >= 0)
                    if value < 0:
                        self.finding("science_counter_regression", source, f"Cumulative {key} fell inside a continuous recorded span.")
                    self.out["within_span_counter_increments"][key] += value
                if complete:
                    expected = {"completed": statuses["completed"], "cancelled": statuses["cancelled"],
                                "failed": statuses["failed"], "effort_spent": sum(payments.values())}
                    if events is not None:
                        expected.update(trials=events["scientific_trial_funded"],
                                        evidence_receipts=events["scientific_evidence_received"])
                    for key, value in expected.items():
                        good = deltas[key] == value
                        self.check("counter_receipt_totals", good)
                        if not good:
                            self.finding("science_counter_receipt_mismatch", source, f"Cumulative {key} increment differs from this turn's recorded receipts/events.")
                    if controls.get("withhold_information") and deltas["evidence_receipts"]:
                        self.finding("receipt_under_withholding", source, "New evidence receipts were recorded while information was withheld.")
            self.previous = (source, clean)
        else:
            self.previous = None

