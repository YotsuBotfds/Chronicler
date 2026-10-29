"""Explicit bounded study journals; imports no World, observer or native runtime."""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path

SEEDS = tuple(range(2000, 2008))
ROLES = ("parent", "active", "pause_new_trials")
SELECTED = tuple((region, recipe) for region in range(8) for recipe in ("irrigation", "masonry"))
ROW_BYTES, ENVELOPE_BYTES, END = 65536, 4096, 180
KERNEL_NUMBERS = ("before", "cap", "shortfall", "disruption", "ordinary_growth", "total_growth",
                  "forgetting", "inflow", "pre_clip", "clipped", "rounded")
KERNEL_FIELDS = ("before", "cap", "prerequisites_met", "population", "shortfall", "disruption",
                 "effort_supplied", "allowance_used", "ordinary_growth", "paid_growth_rhs", "total_growth",
                 "forgetting", "inflow", "pre_clip", "clipped", "rounded", "kept")
REASONS = {"not_ready", "attempt_incomplete", "frame_contract", "phase_unobserved", "retention_limit",
           "capture_failed", "stale_request", "closed"}


class TraceContractError(ValueError):
    pass


def require(ok, message):
    if not ok:
        raise TraceContractError(message)


def encoded(value):
    return json.dumps(value, ensure_ascii=True, allow_nan=False, separators=(",", ":")).encode()


def uint(value, maximum=2**32 - 1):
    require(type(value) is int and 0 <= value <= maximum, "invalid typed integer")
    return value


def number(value):
    require(type(value) in (int, float) and math.isfinite(value), "invalid typed finite number")
    return value


def boolean(value):
    require(type(value) is bool, "invalid typed boolean")
    return value


def copy_frame(frame, source, attempt):
    """Copy only bounded public scalar fields, preserving their exact types."""
    require(frame.status in ("captured", "unavailable"), "invalid frame status")
    uint(frame.attempt)
    require(frame.source_turn is None or type(frame.source_turn) is int, "invalid frame source")
    if frame.source_turn is not None:
        uint(frame.source_turn)
    require(type(frame.rows) is tuple and len(frame.rows) <= 16, "frame row bound")
    if frame.status == "unavailable":
        require(frame.reason in REASONS and frame.scope in ("turn", "phase", "not_started"), "invalid unavailable frame")
        require(not frame.rows and type(frame.encoded_row_bytes) is int and frame.encoded_row_bytes == 0,
                "unavailable frame carries rows")
        return dict(status="unavailable", reason=frame.reason, source_turn=frame.source_turn,
                    attempt=frame.attempt, scope=frame.scope, rows=[], encoded_row_bytes=0)
    require(frame.reason is None and frame.scope == "turn" and frame.source_turn == source,
            "captured frame clock/scope differs")
    require(frame.attempt == attempt, "captured frame attempt differs")
    rows, payment_count = [], 0
    for row in frame.rows:
        require(type(row.recipe) is str, "invalid recipe type")
        require((row.region, row.recipe) in SELECTED, "unselected row")
        uint(row.region, 7)
        present, current = boolean(row.allowance_present), boolean(row.allocations_observed)
        allowance = None if row.allowance is None else number(row.allowance)
        require(not present or allowance is not None, "present allowance is absent")
        require(type(row.payments) is tuple and len(row.payments) <= 40, "payment bound")
        payments = []
        for payment in row.payments:
            seat = uint(payment.seat)
            share, confidence = number(payment.share), number(payment.confidence)
            require(0 <= share <= 1 and 0 <= confidence <= 1, "payment fractions")
            paid, group = uint(payment.bookkeeping_paid, 1), uint(payment.allocation_group_paid, 40)
            require(type(payment.event_id) is str and len(payment.event_id) <= 128, "allocation event bound")
            payments.append(dict(seat=seat, share=share, confidence=confidence, bookkeeping_paid=paid,
                                 allocation_group_paid=group, event_id=payment.event_id))
        payment_count += len(payments)
        require(payment_count <= 40 and (not payments or current), "allocation observation bound/clock")
        kernel = None
        if row.kernel is not None:
            kernel = {field: getattr(row.kernel, field) for field in KERNEL_FIELDS}
            for field in KERNEL_NUMBERS:
                number(kernel[field])
            for field in ("allowance_used", "paid_growth_rhs"):
                if kernel[field] is not None:
                    number(kernel[field])
            uint(kernel["population"])
            for field in ("prerequisites_met", "effort_supplied", "kept"):
                boolean(kernel[field])
        final_present = boolean(row.final_present)
        final_value = None if row.final_value is None else number(row.final_value)
        require(final_present == (final_value is not None), "final presence differs")
        rows.append(dict(region=row.region, recipe=row.recipe, allowance=allowance,
                         allowance_present=present, allocations_observed=current, payments=payments,
                         kernel=kernel, final_present=final_present, final_value=final_value))
    require([(row["region"], row["recipe"]) for row in rows] == list(SELECTED), "selected grid/order differs")
    size = len(encoded(rows))
    require(type(frame.encoded_row_bytes) is int and size == frame.encoded_row_bytes <= ROW_BYTES,
            "observer byte count differs")
    return dict(status="captured", reason=None, source_turn=source, attempt=frame.attempt,
                scope="turn", rows=rows, encoded_row_bytes=size)


def accounting(frame, previous, actual):
    """Account payments from rows, without treating event IDs as a census."""
    actual = uint(actual)
    require(previous is None or actual >= previous, "effort counter decreased")
    delta = None if previous is None else actual - previous
    if frame["status"] != "captured":
        return dict(status="unavailable", before=previous, after=actual, delta=delta, groups=None)
    groups, seen = {}, set()
    for row in frame["rows"]:
        for payment in row["payments"]:
            key, recipe_key = (payment["seat"], row["region"]), (payment["seat"], row["region"], row["recipe"])
            require(recipe_key not in seen, "duplicate recipe payment")
            seen.add(recipe_key)
            group = groups.setdefault(key, dict(seat=key[0], region=key[1], group_paid=payment["allocation_group_paid"],
                                               bookkeeping_paid=0))
            require(group["group_paid"] == payment["allocation_group_paid"], "group cost disagrees")
            group["bookkeeping_paid"] += payment["bookkeeping_paid"]
    require(len(groups) <= 20, "group bound")
    require(all(g["group_paid"] == g["bookkeeping_paid"] for g in groups.values()), "group debit duplicated")
    total = sum(g["group_paid"] for g in groups.values())
    require(delta is None or total == delta, "payment rows differ from effort counter")
    return dict(status="baseline_unobserved" if delta is None else "matched", before=previous, after=actual,
                delta=delta, groups=list(groups.values()))


class PracticeRecorder:
    """One explicit per-role journal; no automatic run, callback or replay."""
    def __init__(self, folder, *, seed, role, initial_effort_spent=None):
        require(type(seed) is int and seed in SEEDS and type(role) is str and role in ROLES, "unregistered seed/role")
        folder = Path(folder)
        require(folder.is_dir() and not folder.is_symlink(), "journal folder is not a real directory")
        self.folder, self.seed, self.role = folder.resolve(), seed, role
        self.start = 0 if role == "parent" else 60
        self.next, self.previous = self.start, None if initial_effort_spent is None else uint(initial_effort_spent)
        self.initial = self.previous
        self.partial, self.final = self.folder / "practice-trace.jsonl.partial", self.folder / "practice-trace.jsonl"
        self.index_path = self.folder / "practice-trace-index.json"
        require(not any(path.exists() or path.is_symlink() for path in (self.final, self.index_path)),
                "journal already exists")
        self.stream = self.partial.open("xb")
        self.hash, self.offset, self.entries, self.closed, self.failed = hashlib.sha256(), 0, [], False, False

    def append(self, frame, *, source_turn, effort_spent):
        require(not self.closed and not self.failed and self.next == source_turn < END, "journal clock/ownership")
        uint(source_turn)
        actual = uint(effort_spent)
        # An invalid capture remains an unavailable slot; it never replays physics.
        try:
            copied = copy_frame(frame, source_turn, source_turn - self.start + 1)
        except Exception:
            copied = dict(status="unavailable", reason="recorder_contract", source_turn=None, attempt=None,
                          scope="turn", rows=[], encoded_row_bytes=0)
        try:
            costs = accounting(copied, self.previous, actual)
        except Exception:
            # Preserve valid raw kernel/payment rows even when their reconciliation fails.
            costs = dict(status="mismatch", before=self.previous, after=actual,
                         delta=None if self.previous is None else actual - self.previous, groups=None)
        record = dict(schema_version=1, seed=self.seed, role=self.role, expected_source_turn=source_turn,
                      selected_slots=16, frame=copied, accounting=costs)
        raw = encoded(record) + b"\n"
        require(len(raw) <= ROW_BYTES + ENVELOPE_BYTES, "journal frame ceiling")
        require(self.offset + len(raw) <= (END - self.start) * (ROW_BYTES + ENVELOPE_BYTES), "journal ceiling")
        try:
            require(self.stream.write(raw) == len(raw), "short journal write")
            self.stream.flush()
        except BaseException:
            self.failed = True
            raise
        self.entries.append(dict(source_turn=source_turn, offset=self.offset, bytes=len(raw),
                                 sha256=hashlib.sha256(raw).hexdigest(), status=copied["status"], reason=copied["reason"],
                                 accounting_status=costs["status"]))
        self.hash.update(raw)
        self.offset, self.next, self.previous = self.offset + len(raw), self.next + 1, actual
        return record

    def finish(self):
        require(not self.closed and not self.failed, "journal cannot publish")
        try:
            self.stream.flush()
            os.fsync(self.stream.fileno())
        finally:
            self.stream.close()
            self.closed = True
        complete = self.next == END
        captured = sum(entry["status"] == "captured" for entry in self.entries)
        mismatches = sum(entry["accounting_status"] == "mismatch" for entry in self.entries)
        if complete:
            require(not self.final.exists() and not self.final.is_symlink(), "journal target appeared")
            self.partial.rename(self.final)
        journal = self.final if complete else self.partial
        report = dict(schema_version=1, seed=self.seed, role=self.role, source_start=self.start, source_end=END - 1,
                      selected_pairs=SELECTED, expected_frames=END - self.start, recorded_frames=len(self.entries),
                      expected_slots=(END - self.start) * 16, captured_slots=captured * 16,
                      recorded_unavailable_slots=(len(self.entries) - captured) * 16,
                      unrecorded_slots=(END - self.start - len(self.entries)) * 16, complete_grid=complete,
                      initial_effort_spent=self.initial, accounting_mismatches=mismatches,
                      usable_trace=complete and captured == END - self.start and not mismatches,
                      usable_trace_scope="complete validated frames; kernels may legitimately be uncomputed",
                      qualification_scope="journal bytes only; worker/execution seals remain required",
                      journal=dict(path=journal.name, bytes=self.offset, sha256=self.hash.hexdigest()), entries=self.entries)
        raw = encoded(report) + b"\n"
        require(len(raw) <= 1024**2, "journal index ceiling")
        partial = self.index_path.with_suffix(".json.partial")
        with partial.open("xb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        require(not self.index_path.exists() and not self.index_path.is_symlink(), "index target appeared")
        partial.rename(self.index_path)
        return report

    def close(self):
        if not self.closed:
            self.stream.close()
            self.closed = True
