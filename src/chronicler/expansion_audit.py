"""Read-only cross-examination of dated optional-system bundle receipts.

Arithmetic consistency is not independent proof of attendance, care efficacy,
forecast skill or social benefit. No final-world state fills historical gaps.
"""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict, dataclass
import hashlib
import json
import math
from pathlib import Path
import sys
from typing import Any, Mapping

from chronicler.bundle_codec import decode_bundle
from chronicler.historical_context import AsOf, Phase

SYSTEMS = ("health_care", "harvest_forecasts", "ritual_gatherings")
HEALTH_METRICS = ("episodes", "new_injuries", "recoveries", "impaired_work", "care_work",
                  "care_recipients", "recovery_progress", "cared_recovery_progress")
ACTUAL_FORECAST = ("observed_ratio", "outcome_shortfall", "brier")
INTERPRETATION = (
    "This audits recorded arithmetic, chronology and mechanism receipts, not scientific efficacy. "
    "Work-time inputs are not measured lost grain, clinical cures or avoided deaths; forecast "
    "estimates are claims, purchases during warnings are not attributable excess spending, "
    "and friendship attempts are not verified new bonds. Missing history remains unknown."
)


class AuditError(ValueError):
    pass


@dataclass(frozen=True)
class Limits:
    max_snapshots: int = 10000
    max_rows: int = 200000
    max_events: int = 100000
    max_findings: int = 200
    max_details: int = 100
    max_text_chars: int = 500
    max_file_bytes: int = 128 * 1024 * 1024

    def __post_init__(self):
        caps = {"max_snapshots": 100000, "max_rows": 2000000, "max_events": 2000000,
                "max_findings": 10000, "max_details": 10000, "max_text_chars": 10000,
                "max_file_bytes": 512 * 1024 * 1024}
        for key, value in asdict(self).items():
            if type(value) is not int or not 1 <= value <= caps[key]:
                raise AuditError(f"{key} must be an integer in 1..{caps[key]}")


def _int(value):
    return value if type(value) is int else None


def _num(value):
    try:
        return value if type(value) in (int, float) and math.isfinite(value) else None
    except OverflowError:
        return None


def _close(a, b):
    return math.isclose(a, b, rel_tol=1e-8, abs_tol=1e-7)


def _spans(turns):
    out = []
    for turn in sorted(set(turns)):
        if out and turn == out[-1][1] + 1:
            out[-1][1] = turn
        else:
            out.append([turn, turn])
    return out


def _unknown_spans(spans, end):
    out, start = [], 0
    for a, b in spans:
        if a > start:
            out.append([start, a - 1])
        start = max(start, b + 1)
    if start <= end:
        out.append([start, end])
    return out


class _Audit:
    def __init__(self, bundle, point, limits, truncated):
        self.bundle, self.point, self.limits = bundle, point, limits
        self.truncated = set(truncated)
        self.findings, self.counts, self.checks = [], Counter(), {}
        self.rows_used = 0
        self.coverage = {s: {"turns": [], "missing_snapshots": 0, "invalid_snapshots": 0} for s in SYSTEMS}
        self.previous = {}
        self.events = {}
        self.related = {}
        self.event_complete = True
        self.observed = {"health_care": {"recorded_turns": 0, "episode_turns": 0.0,
            "new_injuries": 0.0, "episode_retirements": 0.0, "censored_episodes": None,
            "impaired_worker_turns": 0.0, "care_worker_turns": 0.0},
            "harvest_forecasts": {"unique_report_ids": 0, "delivered_report_ids": 0,
                "closed_report_ids": 0, "scored_report_ids": 0, "preparation_receipts": 0, "grain_bought_during_warnings": 0.0,
                "paid_preparation_receipts": 0, "funds_paid_during_warnings": 0.0, "report_chains": []},
            "ritual_gatherings": {"occurrences": 0, "held": 0, "cancelled": 0, "selected_attendances": 0,
                "food": 0.0, "funds": 0.0, "contact_units": 0.0, "bond_attempts": 0,
                "arrival_receipts": 0, "held_with_contact": 0, "held_with_bond_attempts": 0,
                "cancellation_reasons": {}, "occurrence_details": []}}
        self.reports, self.occurrences, self.preparations = {}, set(), set()

    def label(self, value):
        text = str(value)
        if len(text) > self.limits.max_text_chars:
            self.truncated.add("max_text_chars")
            return text[:self.limits.max_text_chars] + "…"
        return text

    def finding(self, system, code, turn, detail, record_id=None, severity="error", evidence=None):
        self.counts[severity] += 1
        if len(self.findings) >= self.limits.max_findings:
            self.truncated.add("max_findings")
            return
        self.findings.append({"system": system, "code": code, "source_turn": turn,
                              "record_id": self.label(record_id) if record_id is not None else None,
                              "severity": severity, "detail": detail, "evidence": evidence or {}})

    def check(self, key, verdict):
        self.checks.setdefault(key, {"verified": 0, "failed": 0, "unavailable": 0})[verdict] += 1

    def rows(self, values, system, turn, table):
        if values is None:
            self.check(f"{system}.{table}_recorded", "unavailable")
            return [], False
        if not isinstance(values, list):
            self.finding(system, "malformed_table", turn, f"{table} must be a list.")
            return [], False
        room = max(0, self.limits.max_rows - self.rows_used)
        if len(values) > room:
            self.truncated.add("max_rows")
        selected = values[:room]
        self.rows_used += len(selected)
        rows = []
        for row in selected:
            if not isinstance(row, Mapping):
                self.finding(system, "malformed_receipt", turn, f"{table} contains a non-object receipt.")
            else:
                rows.append(row)
        return rows, len(values) <= room and len(rows) == len(values)

    def quantities(self, row, keys, system, turn, rid=None, required=True):
        valid = True
        for key in keys:
            number = _num(row.get(key))
            if number is None:
                if required or key in row:
                    self.finding(system, "invalid_quantity", turn, f"{key} is missing or non-finite/nonnumeric.", rid)
                    valid = False
            elif number < 0:
                self.finding(system, "negative_quantity", turn, f"{key} is negative.", rid,
                             evidence={key: number})
                valid = False
            elif key in ("episodes", "new_injuries", "recoveries", "care_recipients", "censored_episodes",
                         "evaluation_count", "bond_ops") and number % 1 != 0:
                self.finding(system, "fractional_count", turn, f"{key} must be a whole count.", rid)
                valid = False
        return valid

    def event_ref(self, ref, expected_kind, expected_turn, system, source, rid):
        key = f"{system}.event_links"
        if not isinstance(ref, str) or not ref:
            self.check(key, "unavailable")
            return None
        rows = self.events.get(ref, [])
        if not rows:
            self.check(key, "unavailable")
            if self.event_complete:
                self.finding(system, "dangling_event_id", source, "A recorded event ID has no timeline record.", rid, "warning")
            return None
        if len(rows) != 1:
            self.check(key, "failed")
            self.finding(system, "ambiguous_event_id", source, "The timeline repeats a referenced stable event ID.", rid)
            return None
        event = rows[0]
        turn = _int(event.get("turn"))
        if turn is None or turn > source:
            self.check(key, "failed")
            self.finding(system, "future_or_undated_event_reference", source,
                         "A receipt cites actual event evidence unavailable at its date; event body withheld.", rid)
            return None
        good = event.get("event_type") == expected_kind and turn == expected_turn
        self.check(key, "verified" if good else "failed")
        if not good:
            self.finding(system, "event_link_mismatch", source, "Referenced event kind/date disagrees with the receipt.", rid)
        return self.label(ref) if good else None

    def counters(self, system, state, source, deltas=None, complete=True):
        counters = state.get("counters")
        if not isinstance(counters, Mapping):
            self.check(f"{system}.counters", "unavailable")
            self.previous.pop(system, None)
            return
        clean = {}
        from itertools import islice
        if len(counters) > 100:
            self.truncated.add("max_counter_keys")
        for key in sorted(islice(counters, 100), key=str):
            value = _num(counters[key])
            if value is None or value < 0:
                self.finding(system, "invalid_cumulative_counter", source, f"Counter {self.label(key)} is negative or non-finite.")
            else:
                clean[key] = value
        prev = self.previous.get(system)
        if prev is not None and prev[0] + 1 == source:
            for key in sorted(clean.keys() & prev[1].keys()):
                delta = clean[key] - prev[1][key]
                good = delta >= -1e-7
                self.check(f"{system}.counter_monotonicity", "verified" if good else "failed")
                if not good:
                    self.finding(system, "counter_regression", source,
                                 f"Cumulative {self.label(key)} fell within a continuously recorded span.")
                if complete and deltas is not None and key in deltas:
                    good = _close(delta, deltas[key])
                    self.check(f"{system}.counter_receipt_totals", "verified" if good else "failed")
                    if not good:
                        self.finding(system, "counter_receipt_mismatch", source,
                                     f"Cumulative {self.label(key)} increment disagrees with this turn's receipts.")
        self.previous[system] = (source, clean)

    def health(self, state, source, snapshot):
        system = "health_care"
        rows, complete = self.rows(state.get("regions"), system, source, "regions")
        if state.get("units") != "worker-turns":
            self.finding(system, "unknown_work_units", source, "Work totals have unknown units; no work-time interpretation supplied.", severity="warning")
        metrics = HEALTH_METRICS + (("censored_episodes",) if "censored_episodes" in state else ())
        self.quantities(state, metrics, system, source)
        sums = {k: 0.0 for k in metrics}
        seen, valid = set(), complete
        for row in rows:
            region = _int(row.get("region"))
            if region is None or region < 0 or region in seen:
                self.finding(system, "invalid_or_duplicate_region", source, "Regional work summaries need unique nonnegative region IDs.")
                valid = False
            seen.add(region)
            ok = self.quantities(row, metrics, system, source, region)
            valid &= ok
            if ok:
                for key in metrics:
                    sums[key] += row[key]
                if row.get("cared_recovery_progress", 0) > row.get("recovery_progress", 0) + 1e-7:
                    self.finding(system, "care_progress_exceeds_total", source, "Cared recovery-work progress exceeds all recorded recovery-work progress.", region)
        for key in metrics:
            actual = _num(state.get(key))
            verdict = ("verified" if _close(sums[key], actual) else "failed") if valid and actual is not None else "unavailable"
            self.check("health_care.regional_totals", verdict)
            if verdict == "failed":
                self.finding(system, "regional_total_mismatch", source, f"Regional {key} does not sum to its recorded total.")
        # Never count repeated active episodes as distinct patients.
        out = self.observed[system]
        out["recorded_turns"] += 1
        for dest, key in (("episode_turns", "episodes"), ("new_injuries", "new_injuries"),
                          ("episode_retirements", "recoveries"), ("censored_episodes", "censored_episodes"),
                          ("impaired_worker_turns", "impaired_work"), ("care_worker_turns", "care_work")):
            value = _num(state.get(key))
            if value is not None and value >= 0:
                out[dest] = (out[dest] or 0) + value

    def gathering(self, state, source, snapshot):
        system = "ritual_gatherings"
        rows, complete = self.rows(state.get("outcomes"), system, source, "outcomes")
        attended_this_turn = set()
        totals = dict.fromkeys(("scheduled", "held", "cancelled", "attendees", "food", "funds", "contact_units", "bond_ops"), 0.0)
        for row in rows:
            gid, turn, region = row.get("gathering_id"), _int(row.get("turn")), _int(row.get("region"))
            if turn is None or turn > source:
                self.finding(system, "future_or_undated_gathering", source,
                             "An actual occurrence is dated after this snapshot or has no date; receipt withheld.")
                complete = False
                continue
            if not isinstance(gid, str) or region is None or region < 0 or gid != f"harvest:{region}":
                self.finding(system, "invalid_gathering_identity", source, "Gathering ID must identify its recorded region.")
                complete = False
                continue
            key = (gid, turn)
            if turn != source or key in self.occurrences:
                self.finding(system, "replayed_gathering_receipt", source,
                             "A previous/duplicate occurrence was replayed as a new turn receipt.", gid)
                complete = False
                continue
            self.occurrences.add(key)
            status = row.get("status")
            quantities = self.quantities(row, ("food", "funds", "contact_units", "bond_ops"), system, source, gid)
            ids = row.get("attendee_ids")
            if not isinstance(ids, list):
                self.finding(system, "missing_attendance", source, "Attendance IDs are unavailable.", gid)
                ids = []
                quantities = False
            eligible_ids = ids[:33]
            if (len(ids) > 32 or any(type(a) is not int or not 0 <= a <= 0xFFFFFFFF for a in eligible_ids)
                    or len(set(map(str, eligible_ids))) != len(eligible_ids)):
                self.finding(system, "invalid_attendance", source, "Attendance exceeds 32 or repeats/invalidates stable IDs.", gid)
                quantities = False
            if quantities:
                if attended_this_turn.intersection(eligible_ids):
                    self.finding(system, "attendee_multiple_regions", source,
                                 "A selected ID appears in multiple simultaneous local gatherings.", gid)
                attended_this_turn.update(eligible_ids)
            arrivals = row.get("arrivals")
            good_arrivals = set()
            arrival_details = []
            if not isinstance(arrivals, list):
                self.check("ritual_gatherings.arrival_membership", "unavailable")
                arrivals = []
            else:
                if len(arrivals) > 32:
                    self.finding(system, "arrival_cap", source, "Arrival receipts exceed selected attendance capacity.", gid)
                for pair in arrivals[:33]:
                    good = (isinstance(pair, (tuple, list)) and len(pair) == 2
                            and type(pair[0]) is int and pair[0] in eligible_ids
                            and type(pair[1]) is int and pair[1] >= 0 and pair[1] != region
                            and pair[0] not in good_arrivals)
                    self.check("ritual_gatherings.arrival_membership", "verified" if good else "failed")
                    if good:
                        good_arrivals.add(pair[0])
                        arrival_details.append({"agent_id": pair[0], "source_region": pair[1]})
                    else:
                        self.finding(system, "invalid_arrival_receipt", source, "Arrival must uniquely identify a selected attendee and another source region.", gid)
            if quantities:
                if status == "cancelled":
                    if ids or arrivals or any(row[k] != 0 for k in ("food", "funds", "contact_units", "bond_ops")):
                        self.finding(system, "improper_cancellation", source, "Cancellation records attendance, expense, contact or a bond attempt.", gid)
                elif status == "held":
                    if _int(row.get("host")) is None or row["host"] < 0:
                        self.finding(system, "held_without_host", source, "A held occurrence has no recorded host civilization ID.", gid)
                    if not ids or row["food"] <= 0 or row["funds"] <= 0:
                        self.finding(system, "cost_or_attendance_missing", source, "A held gathering needs attendance and real positive food/fund costs.", gid)
                    if not _close(row["food"], 0.05 * len(ids)) or row["funds"] != 1 + math.ceil(len(ids) / 16):
                        self.finding(system, "hosting_cost_mismatch", source, "Recorded costs disagree with the first-slice hosting contract.", gid)
                else:
                    self.finding(system, "unknown_gathering_status", source, "Occurrence status is neither held nor cancelled.", gid)
                if row["bond_ops"] > min(8, len(ids) // 2) or row["contact_units"] > min(8, len(good_arrivals)):
                    self.finding(system, "bounded_effect_exceeded", source, "Bond/contact attempts exceed attendance/verified-arrival bounds.", gid)
                for before, after, amount in (("grain_before", "grain_after", "food"), ("funds_before", "funds_after", "funds")):
                    a, b = _num(row.get(before)), _num(row.get(after))
                    if a is None or b is None:
                        self.check("ritual_gatherings.expense_balances", "unavailable")
                    else:
                        good = a >= 0 and b >= 0 and _close(a - b, row[amount])
                        self.check("ritual_gatherings.expense_balances", "verified" if good else "failed")
                        if not good:
                            self.finding(system, "expense_balance_mismatch", source,
                                         f"{before} minus {after} does not equal recorded {amount}.", gid,
                                         evidence={before: a, after: b, amount: row[amount]})
                totals["scheduled"] += 1
                totals[status] = totals.get(status, 0) + 1
                totals["attendees"] += len(ids)
                for key in ("food", "funds", "contact_units", "bond_ops"):
                    totals[key] += row[key]
                out = self.observed[system]
                out["occurrences"] += 1
                if status in ("held", "cancelled"):
                    out[status] += 1
                if status == "held":
                    out["held_with_contact"] += int(row["contact_units"] > 0)
                    out["held_with_bond_attempts"] += int(row["bond_ops"] > 0)
                elif status == "cancelled":
                    reason = row.get("reason")
                    if reason not in ("occupied", "shortage", "food", "funds", "no_host", "no_attendees", "unmeasured_food"):
                        reason = "other_or_unknown"
                    out["cancellation_reasons"][reason] = out["cancellation_reasons"].get(reason, 0) + 1
                out["selected_attendances"] += len(ids)
                out["arrival_receipts"] += len(good_arrivals)
                for dest, key in (("food", "food"), ("funds", "funds"), ("contact_units", "contact_units"), ("bond_attempts", "bond_ops")):
                    out[dest] += row[key]
                if len(out["occurrence_details"]) < self.limits.max_details:
                    out["occurrence_details"].append({"gathering_id": self.label(gid), "turn": turn,
                        "region": region, "region_name": self.label(row.get("region_name", "unknown")),
                        "host_name": self.label(row["host_name"]) if row.get("host_name") else None,
                        "host": row.get("host") if _int(row.get("host")) is not None else None,
                        "faith": row.get("faith") if _int(row.get("faith")) is not None else None,
                        "faith_name": self.label(row["faith_name"]) if row.get("faith_name") else None,
                        "attendee_ids": list(eligible_ids), "arrival_membership_receipts": arrival_details,
                        "status": status, "attendance_count": len(ids),
                        **{k: row[k] for k in ("food", "funds", "contact_units", "bond_ops")}})
        schedules, _ = self.rows(state.get("schedules"), system, source, "schedules")
        schedule_ids = set()
        for row in schedules:
            gid = row.get("gathering_id")
            if not isinstance(gid, str):
                self.finding(system, "invalid_schedule_identity", source, "A schedule lacks a string identity.")
                continue
            if gid in schedule_ids:
                self.finding(system, "duplicate_schedule", source, "A regional schedule is repeated.", row.get("gathering_id"))
            schedule_ids.add(gid)
            if _int(row.get("last_turn")) is not None and row["last_turn"] > source:
                self.finding(system, "future_schedule_outcome", source, "A schedule records a future actual last occurrence; body withheld.")
        contact = snapshot.get("contact")
        inflow = contact.get("inflow") if isinstance(contact, Mapping) else None
        pilgrims = inflow.get("pilgrims") if isinstance(inflow, Mapping) else None
        if complete and _num(pilgrims) is not None:
            good = totals["contact_units"] <= pilgrims + 1e-7
            self.check("ritual_gatherings.contact_inflow", "verified" if good else "failed")
            if not good:
                self.finding(system, "contact_inflow_mismatch", source, "Gathering contact exceeds all recorded pilgrimage-channel inflow.")
        else:
            self.check("ritual_gatherings.contact_inflow", "unavailable")
        self.counters(system, state, source, totals, complete)

    def forecasts(self, state, source, snapshot):
        system = "harvest_forecasts"
        reports, a = self.rows(state.get("reports"), system, source, "reports")
        outcomes, b = self.rows(state.get("outcomes"), system, source, "outcomes")
        seen, current = set(), {}
        for row in reports + outcomes:
            issued, rid = _int(row.get("issued_turn")), row.get("id")
            if issued is None or issued > source:
                self.finding(system, "future_or_undated_report", source, "Report issuance is unavailable at this snapshot; body and identity withheld.")
                continue
            if not isinstance(rid, str) or not rid:
                self.finding(system, "missing_report_id", source, "A report lacks a stable ID.")
                continue
            if rid in seen:
                self.finding(system, "duplicate_report_receipt", source, "The same report appears more than once within one snapshot.", rid)
                continue
            seen.add(rid)
            if not self.quantities(row, ("probability", "confidence", "predicted_ratio", "evaluation_sum", "evaluation_count"), system, source, rid):
                continue
            if row["probability"] > 1 or row["confidence"] > 1:
                self.finding(system, "invalid_forecast_probability", source, "Probability/confidence exceeds one.", rid)
            target_start, target_end = _int(row.get("target_start")), _int(row.get("target_end"))
            if (target_start is None or target_end is None or target_start > target_end
                    or _int(row.get("delivery_turn")) is None or row["delivery_turn"] < issued
                    or _int(row.get("expires_turn")) is None or row["expires_turn"] < target_end):
                self.finding(system, "invalid_forecast_plan", source, "Planned delivery/target/expiry dates are missing or inverted.", rid)
            delivery, resolved = _int(row.get("delivered_turn")), _int(row.get("resolved_turn"))
            status = row.get("status")
            if delivery is not None and (delivery > source or delivery < issued):
                self.finding(system, "future_or_inverted_delivery", source, "Actual delivery is future-dated or precedes issuance; evidence withheld.", rid)
                delivery = None
            if resolved is not None and (resolved > source or resolved < issued):
                self.finding(system, "future_or_inverted_resolution", source, "Actual resolution is future-dated or precedes issuance; outcome evidence withheld.", rid)
                resolved = None
            if row["evaluation_count"] > 0 and (target_start is None or source < target_start):
                self.finding(system, "future_evaluation_evidence", source, "Actual target-period observations appear before the target interval; evidence withheld.", rid)
            actual = any(row.get(k) is not None for k in ACTUAL_FORECAST)
            scored = (resolved is not None and status == "resolved" and target_end is not None and target_end <= source)
            if actual and not scored:
                self.finding(system, "premature_outcome_evidence", source, "Scored outcome fields lack a completed, dated resolution; values withheld.", rid)
            identity = tuple(row.get(k) for k in ("issued_turn", "source_region", "recipient_region", "owner", "probability", "confidence", "target_start", "target_end"))
            previous = self.reports.get(rid)
            if previous is not None and previous["identity"] != identity:
                self.finding(system, "report_identity_changed", source, "A stable report ID changed its issuing identity, estimate or target interval.", rid)
            chain = previous or {"identity": identity, "id": self.label(rid), "issued_turn": issued,
                "source_region_name": self.label(row.get("source_region_name", "unknown")),
                "recipient_region_name": self.label(row.get("recipient_region_name", "unknown")),
                "owner_name": self.label(row.get("owner_name", "unknown")), "issued_event_id": None,
                "delivered_turn": None, "delivered_event_id": None, "resolved_turn": None,
                "resolution_event_ids": [], "preparation_event_ids": [], "preparation_receipts": 0, "grain_bought": 0.0,
                "funds_paid": 0.0, "brier": None}
            chain["issued_event_id"] = self.event_ref(row.get("issued_event_id"), "harvest_forecast_issued", issued, system, source, rid)
            if delivery is not None:
                chain["delivered_turn"] = delivery
                chain["delivered_event_id"] = self.event_ref(row.get("delivered_event_id"), "harvest_forecast_delivered", delivery, system, source, rid)
            elif status == "delivered":
                self.finding(system, "delivery_without_actual_date", source, "Delivered status has no valid actual delivery date.", rid)
            if resolved is not None:
                chain["resolved_turn"] = resolved
                # Runtime resolutions cite issue/delivery IDs but have no
                # resolved_event_id field; match only exact recorded dependencies.
                chain["resolution_event_ids"] = self.related_events("harvest_forecast_resolved", resolved, row)
                self.check("harvest_forecasts.resolution_event_links", "verified" if chain["resolution_event_ids"] else "unavailable")
            if scored:
                self.quantities(row, ("observed_ratio", "brier"), system, source, rid)
                values = (row.get("probability"), row.get("outcome_shortfall"), row.get("brier"))
                if type(values[1]) is bool and _num(values[2]) is not None and values[2] >= 0:
                    good = _close((values[0] - int(values[1])) ** 2, values[2])
                    self.check("harvest_forecasts.brier_arithmetic", "verified" if good else "failed")
                    if not good:
                        self.finding(system, "brier_mismatch", source, "Brier score disagrees with the report's recorded probability/outcome.", rid)
                    chain["brier"] = values[2]
                else:
                    self.finding(system, "invalid_scored_outcome", source, "A resolved report lacks a finite score and boolean outcome.", rid)
                if row["evaluation_count"] > 0 and _num(row.get("observed_ratio")) is not None:
                    good = _close(row["evaluation_sum"] / row["evaluation_count"], row["observed_ratio"])
                    self.check("harvest_forecasts.observed_ratio_arithmetic", "verified" if good else "failed")
                    if not good:
                        self.finding(system, "observed_ratio_mismatch", source, "Resolved production/demand ratio disagrees with its recorded observations.", rid)
                    good = row.get("outcome_shortfall") is (row["observed_ratio"] < 0.6)
                    self.check("harvest_forecasts.shortfall_definition", "verified" if good else "failed")
                    if not good:
                        self.finding(system, "shortfall_definition_mismatch", source,
                                     "Recorded shortfall boolean disagrees with the first-slice production/demand threshold 0.6.", rid)
            self.reports[rid] = chain
            current[rid] = (row, delivery)
        preparations, complete = self.rows(state.get("preparedness"), system, source, "preparedness")
        paid, bought = 0.0, 0.0
        for row in preparations:
            rid = row.get("forecast_id")
            if any(key in row and (_int(row[key]) is None or row[key] != source)
                   for key in ("turn", "source_turn", "paid_turn")):
                self.finding(system, "preparation_date_mismatch", source,
                             "An actual preparation receipt has a different/future date; quantities withheld.")
                complete = False
                continue
            if not isinstance(rid, str) or _int(row.get("region")) is None:
                self.finding(system, "invalid_preparation_identity", source, "Preparation needs its report ID and region ID.")
                complete = False
                continue
            key = (source, rid, row.get("region"))
            if key in self.preparations:
                self.finding(system, "duplicate_preparation_receipt", source, "A preparation receipt is repeated within its actual turn.", rid)
                complete = False
                continue
            self.preparations.add(key)
            if not self.quantities(row, ("base_target", "extra_target", "bought_during_warning", "paid_during_warning"), system, source, rid):
                continue
            report, delivered = current.get(rid, (None, None))
            if report is None or delivered is None or report.get("status") != "delivered":
                self.finding(system, "preparation_without_delivered_report", source, "Preparation has no valid currently delivered report; quantities withheld.", rid)
                continue
            if (_int(report.get("expires_turn")) is None or source > report["expires_turn"]
                    or row.get("region") != report.get("recipient_region") or row.get("owner") != report.get("owner")):
                self.finding(system, "preparation_identity_or_expiry", source, "Paid preparation disagrees with report recipient/owner or expiry.", rid)
                continue
            chain = self.reports[rid]
            chain["preparation_receipts"] += 1
            chain["grain_bought"] += row["bought_during_warning"]
            chain["funds_paid"] += row["paid_during_warning"]
            bought += row["bought_during_warning"]
            paid += row["paid_during_warning"]
            self.observed[system]["preparation_receipts"] += 1
            self.verify_purchases(row, source, snapshot)
            if row["paid_during_warning"] > 0:
                self.observed[system]["paid_preparation_receipts"] += 1
                links = self.related_events("harvest_preparedness", source, report)
                chain["preparation_event_ids"] = sorted(set(chain["preparation_event_ids"] + links))
                self.check("harvest_forecasts.preparation_event_links", "verified" if links else "unavailable")
        out = self.observed[system]
        out["grain_bought_during_warnings"] += bought
        out["funds_paid_during_warnings"] += paid
        self.counters(system, state, source, {"bought_during_warning": bought, "paid_during_warning": paid}, complete and a and b)

    def related_events(self, kind, turn, report):
        links = []
        required = report.get("delivered_event_id") if kind == "harvest_preparedness" else report.get("issued_event_id")
        if not required:
            return links
        return [self.label(eid) for eid in sorted(self.related.get(
            (kind, turn, report.get("recipient_region_name"), required), []))]

    def verify_purchases(self, row, source, snapshot):
        state = snapshot.get("grain_reserves")
        key = "harvest_forecasts.granary_purchase_totals"
        if not isinstance(state, Mapping) or state.get("source_turn") != source:
            self.check(key, "unavailable")
            return
        flows, complete = self.rows(state.get("flows"), "harvest_forecasts", source, "granary_flows")
        flows = [f for f in flows if f.get("kind") == "bought" and f.get("region") == row.get("region")]
        if not complete or any(_num(f.get(k)) is None or f[k] < 0 for f in flows for k in ("amount", "cost")):
            self.check(key, "unavailable")
            return
        good = (_close(sum(f["amount"] for f in flows), row["bought_during_warning"])
                and _close(sum(f["cost"] for f in flows), row["paid_during_warning"]))
        self.check(key, "verified" if good else "failed")
        if not good:
            self.finding("harvest_forecasts", "purchase_flow_mismatch", source,
                         "Warning-period purchases disagree with the same turn's actual granary purchase flows.", row.get("forecast_id"))


def audit_bundle(bundle: Mapping[str, Any], *, as_of: AsOf | None = None, limits: Limits | None = None) -> dict:
    """Audit a bounded history prefix without changing the input or running simulation."""
    limits = limits or Limits()
    if not isinstance(bundle, Mapping):
        raise AuditError("the bundle must be a JSON object")
    truncated = set()
    # Bound delta expansion before the shared decoder reconstructs every row.
    if isinstance(bundle.get("history_delta"), list) and len(bundle["history_delta"]) > limits.max_snapshots:
        bundle = {**bundle, "history_delta": bundle["history_delta"][:limits.max_snapshots]}
        truncated.add("max_snapshots")
    decoded = decode_bundle(bundle)
    history = decoded.get("history", [])
    if not isinstance(history, list):
        raise AuditError("history must be a list of snapshots")
    world, metadata = decoded.get("world_state"), decoded.get("metadata")
    declared = _int(world.get("turn")) if isinstance(world, Mapping) else None
    if declared is None and isinstance(metadata, Mapping):
        declared = _int(metadata.get("total_turns"))
    if as_of is None:
        horizon = declared - 1 if declared is not None else max(
            (_int(s.get("turn")) - 1 for s in history if isinstance(s, Mapping) and _int(s.get("turn")) is not None), default=-1)
        as_of = AsOf.after(horizon)
    if (not isinstance(as_of, AsOf) or type(as_of.turn) is not int
            or not isinstance(as_of.phase, Phase) or as_of.completed < -1):
        raise AuditError("as_of must identify a turn at or after the initial boundary")
    audit = _Audit(decoded, as_of, limits, truncated)
    timeline = decoded.get("events_timeline", decoded.get("events", []))
    if timeline is None:
        timeline = []
    if not isinstance(timeline, list):
        raise AuditError("events_timeline must be a list when present")
    audit.event_complete = ("events_timeline" in decoded or "events" in decoded) and len(timeline) <= limits.max_events
    if len(timeline) > limits.max_events:
        audit.truncated.add("max_events")
    for event in timeline[:limits.max_events]:
        if isinstance(event, Mapping) and isinstance(event.get("event_id"), str) and event["event_id"]:
            audit.events.setdefault(event["event_id"], []).append(event)
    for eid, events in audit.events.items():
        if len(events) != 1:
            visible = [e for e in events if _int(e.get("turn")) is not None and e["turn"] <= as_of.completed
                       and e.get("event_type") in ("harvest_forecast_issued", "harvest_forecast_delivered",
                            "harvest_preparedness", "harvest_forecast_resolved", "occupational_injury",
                            "harvest_gathering_held", "harvest_gathering_cancelled")]
            if visible:
                audit.finding("events", "duplicate_event_id", min(e["turn"] for e in visible),
                              "Relevant timeline events repeat a stable event ID.", eid)
            continue
        event = events[0]
        if event.get("event_type") not in ("harvest_preparedness", "harvest_forecast_resolved"):
            continue
        causes = event.get("causes")
        if not isinstance(causes, list):
            continue
        if len(causes) > 100:
            audit.truncated.add("max_event_causes")
        for cause in causes[:100]:
            if isinstance(cause, str) and isinstance(event.get("region"), str) and _int(event.get("turn")) is not None:
                audit.related.setdefault((event["event_type"], event["turn"], event["region"], cause), []).append(eid)
    grouped = {}
    if len(history) > limits.max_snapshots:
        audit.truncated.add("max_snapshots")
    for snapshot in history[:limits.max_snapshots]:
        if not isinstance(snapshot, Mapping) or _int(snapshot.get("turn")) is None:
            audit.finding("history", "undated_snapshot", None, "A historical snapshot has no integer turn.")
            continue
        if snapshot["turn"] - 1 <= as_of.completed:
            grouped.setdefault(snapshot["turn"], []).append(snapshot)
    inspected = []
    for turn, copies in sorted(grouped.items()):
        if audit.rows_used >= limits.max_rows:
            audit.truncated.add("max_rows")
            break
        snapshot = copies[0]
        if len(copies) > 1:
            same = all(snapshot == other for other in copies[1:])
            audit.finding("history", "duplicate_snapshot" if same else "conflicting_snapshot", turn - 1,
                          "Repeated snapshot receipts are counted once." if same else "Conflicting snapshots at one date are withheld.",
                          severity="warning" if same else "error")
            if not same:
                audit.previous.clear()
                continue
        source = turn - 1
        inspected.append(source)
        for system in SYSTEMS:
            state = snapshot.get(system)
            coverage = audit.coverage[system]
            if state is None or state == {}:
                coverage["missing_snapshots"] += 1
                audit.previous.pop(system, None)
                continue
            if not isinstance(state, Mapping) or _int(state.get("source_turn")) != source:
                coverage["invalid_snapshots"] += 1
                audit.previous.pop(system, None)
                audit.finding(system, "section_source_mismatch", source, "Section does not identify this snapshot's completed turn; its body is withheld.")
                continue
            coverage["turns"].append(source)
            {"health_care": audit.health, "harvest_forecasts": audit.forecasts,
             "ritual_gatherings": audit.gathering}[system](state, source, snapshot)
    for system, coverage in audit.coverage.items():
        turns = coverage.pop("turns")
        spans = _spans(turns)
        unknown = _unknown_spans(spans, as_of.completed)
        coverage.update({"recorded_snapshots": len(turns), "completed_turn_spans": spans,
                         "unknown_completed_turn_spans": unknown, "unknown_span_intervals": len(unknown)})
    forecasts = audit.observed["harvest_forecasts"]
    chains = sorted(audit.reports.values(), key=lambda r: (r["issued_turn"], r["id"]))
    forecasts["unique_report_ids"] = len(chains)
    forecasts["delivered_report_ids"] = sum(r["delivered_turn"] is not None for r in chains)
    forecasts["closed_report_ids"] = sum(r["resolved_turn"] is not None for r in chains)
    forecasts["scored_report_ids"] = sum(r["brier"] is not None for r in chains)
    forecasts["report_chains"] = [{k: v for k, v in row.items() if k != "identity"} for row in chains[:limits.max_details]]
    details_omitted = max(0, len(chains) - limits.max_details)
    occurrence_omitted = max(0, audit.observed["ritual_gatherings"]["occurrences"] - limits.max_details)
    observed_any = any(c["recorded_snapshots"] for c in audit.coverage.values())
    observations = []
    gathers, work = audit.observed["ritual_gatherings"], audit.observed["health_care"]
    if gathers["occurrences"] and not gathers["held"]:
        observations.append("Every inspected gathering occurrence was cancelled; the attendance/contact/bond pathway was not exercised by these receipts.")
    if gathers["held"] and not gathers["held_with_contact"]:
        observations.append("Held gatherings produced no positive recorded arrival-based gathering contact in the inspected coverage.")
    if forecasts["unique_report_ids"] and not forecasts["scored_report_ids"]:
        observations.append("Reports were recorded but none has a dated scored outcome in this view; forecast scoring cannot yet be examined.")
    if forecasts["delivered_report_ids"] and not forecasts["paid_preparation_receipts"]:
        observations.append("Delivered reports have no positive recorded warning-period payment in the inspected coverage; delivery alone does not establish material preparation.")
    if work["impaired_worker_turns"] > 0 and work["care_worker_turns"] == 0:
        observations.append("Work impairment was recorded with zero recorded caregiver work allocation in the inspected coverage.")

    def finite(value):
        if isinstance(value, dict):
            return {k: finite(v) for k, v in value.items()}
        if isinstance(value, list):
            return [finite(v) for v in value]
        if type(value) is float and not math.isfinite(value):
            audit.finding("report", "aggregate_overflow", None, "A sum of individually finite quantities overflowed; aggregate withheld.")
            return None
        return value

    observed = finite(audit.observed)
    status = ("issues_found" if audit.counts["error"] else "partial" if audit.truncated else
              "no_violations_in_recorded_coverage" if observed_any else "no_recorded_expansion_history")
    return {"schema_version": 1, "status": status, "scan_complete": not audit.truncated,
        "interpretation": INTERPRETATION, "as_of": {"turn": as_of.turn, "phase": as_of.phase.value,
        "completed_turn": as_of.completed}, "coverage": {"inspected_snapshot_spans": _spans(inspected),
        "inspected_snapshots": len(inspected), "systems": audit.coverage},
        "verified_checks": dict(sorted(audit.checks.items())), "observed_mechanisms": observed,
        "descriptive_observations": observations,
        "findings": audit.findings, "finding_counts": {"error": audit.counts["error"], "warning": audit.counts["warning"]},
        "unobservable": ["Missing or rejected historical sections cannot establish that a feature was off or had zero effect.",
            "Summaries cannot identify unique patients, clinical recovery, deaths or the causes of episode censoring.",
            "A bundle alone cannot independently establish native attendance location/age/occupation, merchant commitments, friendship success or pandemic imports.",
            "Equal purchase quantities on different turns are not duplicate purchases; granary-flow reconciliation is observational, not attributable excess spending.",
            "Without a recorded event ID, matching prose or chronology does not prove a forecast dependency."],
        "requires_interventions": ["Care efficacy or avoided deaths", "Forecast skill versus seasonal baselines and withheld/shuffled reports",
            "Additional spending or reduced shortage attributable to a warning", "Gathering benefits versus cost-only, no-contact and no-bond controls"],
        "contracts_checked": {"version": "first_slice_2026_10", "gathering_max_attendance": 32,
            "gathering_max_bond_attempts": 8, "gathering_max_contact_units": 8,
            "grain_per_attendee": 0.05, "funds": "1 + ceil(attendees / 16)", "production_shortfall_ratio": 0.6},
        "limits": asdict(limits), "truncated_by": sorted(audit.truncated),
        "details_omitted": {"report_chains": details_omitted, "gathering_occurrences": occurrence_omitted}}


def audit_path(path: str | Path, *, as_of: AsOf | None = None, limits: Limits | None = None) -> dict:
    limits = limits or Limits()
    path = Path(path)
    with path.open("rb") as stream:
        raw = stream.read(limits.max_file_bytes + 1)
    if len(raw) > limits.max_file_bytes:
        raise AuditError("source exceeds max_file_bytes; no partial-byte identity or audit produced")
    report = audit_bundle(json.loads(raw), as_of=as_of, limits=limits)
    report["source"] = {"name": path.name, "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}
    return report


def _md(value):
    text = str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    for char in ("\\", "`", "*", "_", "{", "}", "[", "]", "(", ")", "#", "+", "-", "!", "|"):
        text = text.replace(char, "\\" + char)
    return " ".join(text.split())


def render_markdown(report: Mapping[str, Any]) -> str:
    lines = ["# System expansion audit", "", report["interpretation"], "",
             f"Status: **{_md(report['status'])}**; as of completed turn {report['as_of']['completed_turn']}."]
    if source := report.get("source"):
        lines += [f"Source: {_md(source['name'])}; SHA-256 `{source['sha256']}`; {source['bytes']} bytes."]
    lines += ["", "## Dated coverage", "", "| System | Recorded snapshots | Completed-turn spans | Missing / invalid |",
              "| --- | ---: | --- | ---: |"]
    for system, row in report["coverage"]["systems"].items():
        lines.append(f"| {_md(system)} | {row['recorded_snapshots']} | {_md(row['completed_turn_spans'])} | {row['missing_snapshots']} / {row['invalid_snapshots']} |")
    lines += ["", "## Arithmetic and chronology checks", "", "| Check | Verified | Failed | Unavailable |", "| --- | ---: | ---: | ---: |"]
    for key, row in report["verified_checks"].items():
        lines.append(f"| {_md(key)} | {row['verified']} | {row['failed']} | {row['unavailable']} |")
    lines += ["", "## Observed mechanisms", ""]
    for system, values in report["observed_mechanisms"].items():
        lines.append(f"- **{_md(system)}**: " + "; ".join(f"{_md(k)}: {_md(v)}" for k, v in values.items() if not isinstance(v, list)) + ".")
    lines += ["", *[f"- {_md(value)}" for value in report["descriptive_observations"]]]
    lines += ["", "### Forecast cross-examination", ""]
    for row in report["observed_mechanisms"]["harvest_forecasts"]["report_chains"]:
        lines += [f"- {_md(row['id'])}: {_md(row['source_region_name'])} → {_md(row['recipient_region_name'])}, "
                  f"owner {_md(row['owner_name'])}; issued {row['issued_turn']} ({_md(row['issued_event_id'])}); "
                  f"delivered {_md(row['delivered_turn'])} ({_md(row['delivered_event_id'])}); "
                  f"{row['preparation_receipts']} preparation receipts, {row['grain_bought']} grain / {row['funds_paid']} funds; "
                  f"purchase IDs {_md(row['preparation_event_ids'])}; "
                  f"resolved {_md(row['resolved_turn'])}, IDs {_md(row['resolution_event_ids'])}, score {_md(row['brier'])}."]
    lines += ["", "### Gathering receipts", ""]
    for row in report["observed_mechanisms"]["ritual_gatherings"]["occurrence_details"]:
        lines += [f"- {_md(row['gathering_id'])}, turn {row['turn']}, {_md(row['region_name'])}, host {_md(row['host_name'])}: "
                  f"{_md(row['status'])}; {row['attendance_count']} selected attendees, {row['food']} food / {row['funds']} funds; "
                  f"{row['bond_ops']} bond attempts / {row['contact_units']} additional contact units."]
    lines += ["", "## Findings", ""]
    lines += [f"- **{_md(f['severity'])} / {_md(f['code'])}**, {_md(f['system'])}, "
              f"turn {_md(f['source_turn'])}, ID {_md(f['record_id'])}: {_md(f['detail'])}"
              + (f" Evidence: {_md(f['evidence'])}." if f.get("evidence") else "") for f in report["findings"]]
    if not report["findings"]:
        lines += ["No violations found in the inspected recorded coverage; this is not efficacy qualification."]
    for title, key in (("Unobservable from these records", "unobservable"), ("Scientific claims requiring interventions", "requires_interventions")):
        lines += ["", f"## {title}", "", *[f"- {_md(value)}" for value in report[key]]]
    lines += ["", "## Bounds", "", "- Scan complete: " + str(report["scan_complete"]) + ".",
              "- Truncated by: " + (", ".join(report["truncated_by"]) or "none") + ".",
              "- Detail rows omitted: " + _md(report["details_omitted"]) + "."]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("bundle", type=Path)
    parser.add_argument("--as-of", type=int, help="Turn boundary (default: declared last completed turn)")
    parser.add_argument("--phase", choices=("start", "end"), default="end")
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    parser.add_argument("--json", type=Path)
    parser.add_argument("--markdown", type=Path)
    for key, default in asdict(Limits()).items():
        parser.add_argument("--" + key.replace("_", "-"), type=int, default=default)
    args = parser.parse_args(argv)
    if args.as_of is None and args.phase != "end":
        parser.error("--phase start requires --as-of")
    try:
        outputs = [p for p in (args.json, args.markdown) if p is not None]
        for destination in outputs:
            if destination.resolve() == args.bundle.resolve() or (destination.exists() and destination.samefile(args.bundle)):
                raise AuditError("a report output must not overwrite the source bundle")
        if len(outputs) == 2 and (outputs[0].resolve() == outputs[1].resolve()
                or (outputs[0].exists() and outputs[1].exists() and outputs[0].samefile(outputs[1]))):
            raise AuditError("JSON and Markdown outputs must be different files")
        limits = Limits(**{key: getattr(args, key) for key in asdict(Limits())})
        point = AsOf(args.as_of, Phase(args.phase)) if args.as_of is not None else None
        report = audit_path(args.bundle, as_of=point, limits=limits)
        js = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        md = render_markdown(report)
        for path, content in ((args.json, js), (args.markdown, md)):
            if path is not None:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
        print(js if args.format == "json" else md, end="")
        return 1 if report["finding_counts"]["error"] else 3 if report["status"] in ("partial", "no_recorded_expansion_history") else 0
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(f"system-expansion-audit: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
