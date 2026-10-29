"""Bounded scalar journal verification; no project/native imports or unpickling."""
from __future__ import annotations

import hashlib
from pathlib import Path
from types import SimpleNamespace as NS

import research_practice_contract as C
import research_practice_recorder as R

WITNESS_ROWS = 32
TRACE_FILES = {"practice-counter-baseline.json", "practice-trace-index.json", "practice-trace.jsonl"}


def copied_frame(value, source, attempt):
    C.closed(value, {"status", "reason", "source_turn", "attempt", "scope", "rows", "encoded_row_bytes"}, "practice frame")
    C.require(type(value["rows"]) is list and len(value["rows"]) <= 16, "practice row bound")
    if value["reason"] == "recorder_contract":
        expected = dict(status="unavailable", reason="recorder_contract", source_turn=None, attempt=None,
                        scope="turn", rows=[], encoded_row_bytes=0)
        C.require(C.same(value, expected), "recorder refusal frame differs")
        return expected
    rows = []
    for row in value["rows"]:
        C.closed(row, {"region", "recipe", "allowance", "allowance_present", "allocations_observed",
                       "payments", "kernel", "final_present", "final_value"}, "practice row")
        C.require(type(row["payments"]) is list and len(row["payments"]) <= 40, "practice payment bound")
        payments = []
        for payment in row["payments"]:
            C.closed(payment, {"seat", "share", "confidence", "bookkeeping_paid", "allocation_group_paid", "event_id"}, "practice payment")
            payments.append(NS(**payment))
        kernel = row["kernel"]
        if kernel is not None:
            C.closed(kernel, R.KERNEL_FIELDS, "practice kernel")
            kernel = NS(**kernel)
        rows.append(NS(**{**row, "payments": tuple(payments), "kernel": kernel}))
    copied = R.copy_frame(NS(**{**value, "rows": tuple(rows)}), source, attempt)
    C.require(copied["attempt"] == attempt, "practice handle attempt differs")
    C.require(C.same(copied, value), "practice scalar projection differs")
    return copied


def records(folder, seed, role, index, baseline):
    """Yield one <=69,632-byte frame at a time; verify complete indexed bytes."""
    start = 0 if role == "parent" else C.FORK
    path = Path(folder) / "practice-trace.jsonl"
    journal = index["journal"]
    C.closed(journal, {"path", "bytes", "sha256"}, "practice journal")
    C.require(journal["path"] == path.name and path.is_file() and not path.is_symlink(), "practice journal path differs")
    C.nonnegative(journal["bytes"], "practice journal bytes", integer=True)
    C.require(journal["bytes"] == path.stat().st_size <= (C.END - start) * (R.ROW_BYTES + R.ENVELOPE_BYTES), "practice journal size bound")
    entries = index["entries"]
    C.require(type(entries) is list and len(entries) == C.END - start, "practice index coverage differs")
    offset, previous, digest = 0, baseline["initial_effort_spent"], hashlib.sha256()
    with path.open("rb") as stream:
        for source, entry in zip(range(start, C.END), entries):
            C.closed(entry, {"source_turn", "offset", "bytes", "sha256", "status", "reason", "accounting_status"}, "practice entry")
            raw = stream.readline(R.ROW_BYTES + R.ENVELOPE_BYTES + 1)
            C.require(0 < len(raw) <= R.ROW_BYTES + R.ENVELOPE_BYTES and raw.endswith(b"\n"), "practice frame byte bound/truncation")
            record = C.loads(raw)
            C.closed(record, {"schema_version", "seed", "role", "expected_source_turn", "selected_slots", "frame", "accounting"}, "practice record")
            for key, expected in dict(schema_version=1, seed=seed, role=role, expected_source_turn=source, selected_slots=16).items():
                C.require(C.same(record[key], expected), "practice record clock/identity differs")
            frame = copied_frame(record["frame"], source, source - start + 1)
            costs = record["accounting"]
            C.require(type(costs) is dict and "after" in costs, "practice accounting shape")
            actual = R.uint(costs["after"])
            try:
                expected = R.accounting(frame, previous, actual)
            except Exception:
                expected = dict(status="mismatch", before=previous, after=actual, delta=actual - previous, groups=None)
            C.require(C.same(costs, expected), "practice accounting projection differs")
            expected_entry = dict(source_turn=source, offset=offset, bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest(),
                status=frame["status"], reason=frame["reason"], accounting_status=costs["status"])
            C.require(C.same(entry, expected_entry) and R.encoded(record) + b"\n" == raw, "practice index or canonical bytes differ")
            previous, offset = actual, offset + len(raw)
            digest.update(raw)
            yield record
        C.require(stream.read(1) == b"", "practice journal has trailing frames")
    C.require(offset == journal["bytes"] and digest.hexdigest() == journal["sha256"], "practice journal digest differs")


def inspect(folder, seed, role, summary, *, checkpoint_effort, final_effort):
    folder = Path(folder)
    index = C.read(folder / "practice-trace-index.json", 1024**2)
    baseline = C.read(folder / "practice-counter-baseline.json", 4096)
    C.closed(baseline, {"schema_version", "seed", "role", "source_turn", "initial_effort_spent",
                        "expected_checkpoint_effort", "clock"}, "practice baseline")
    start = 0 if role == "parent" else C.FORK
    for key, expected in dict(schema_version=1, seed=seed, role=role, source_turn=start,
            expected_checkpoint_effort=checkpoint_effort,
            clock="immediately before first actual observer/physics call").items():
        C.require(C.same(baseline[key], expected), "actual practice baseline provenance differs")
    R.uint(baseline["initial_effort_spent"])
    C.require(checkpoint_effort is None or C.same(baseline["initial_effort_spent"], checkpoint_effort), "practice baseline differs from actual CP")
    C.closed(index, {"schema_version", "seed", "role", "source_start", "source_end", "selected_pairs", "expected_frames",
        "recorded_frames", "expected_slots", "captured_slots", "recorded_unavailable_slots", "unrecorded_slots",
        "complete_grid", "initial_effort_spent", "accounting_mismatches", "usable_trace", "usable_trace_scope",
        "qualification_scope", "journal", "entries"}, "practice index")
    for key, expected in dict(schema_version=1, seed=seed, role=role, source_start=start, source_end=C.END-1,
            selected_pairs=[list(pair) for pair in R.SELECTED], expected_frames=C.END-start, recorded_frames=C.END-start,
            expected_slots=(C.END-start)*16, unrecorded_slots=0, complete_grid=True,
            initial_effort_spent=baseline["initial_effort_spent"],
            usable_trace_scope="complete validated frames; kernels may legitimately be uncomputed",
            qualification_scope="journal bytes only; worker/execution seals remain required").items():
        C.require(C.same(index[key], expected), "practice index registration differs: " + key)
    counts = dict(captured_frames=0, unavailable_frames=0, accounting_mismatches=0, kernel_computed=0,
        kernel_uncomputed=0, positive_allowance=0, positive_paid_rhs=0, paid_rhs_zero=0,
        paid_rhs_unobserved=0, kernel_dropped=0,
        final_present=0, final_differs_from_kernel_rounded=0, payment_rows=0, recipe_payment_occurrences=0,
        bookkeeping_paid_sum=0, matched_group_debit_sum=0, matched_debit_frames=0)
    witnesses, reasons, post_boundary = [], {}, hashlib.sha256()
    final_counter = baseline["initial_effort_spent"]
    for record in records(folder, seed, role, index, baseline):
        frame, costs, source = record["frame"], record["accounting"], record["expected_source_turn"]
        final_counter = costs["after"]
        if source >= C.FORK:
            # Only owner-local role and already-validated handle attempt differ.
            comparable = {**record, "role": "validated_role"}
            comparable["frame"] = {**frame, "attempt": "validated_handle_attempt" if frame["attempt"] is not None else None}
            post_boundary.update(R.encoded(comparable) + b"\n")
        captured = frame["status"] == "captured"
        counts["captured_frames" if captured else "unavailable_frames"] += 1
        counts["accounting_mismatches"] += costs["status"] == "mismatch"
        if costs["status"] == "matched":
            counts["matched_group_debit_sum"] += costs["delta"]
            counts["matched_debit_frames"] += 1
        if not captured:
            reasons[frame["reason"]] = reasons.get(frame["reason"], 0) + 1
        for row in frame["rows"]:
            kernel = row["kernel"]
            counts["kernel_computed" if kernel is not None else "kernel_uncomputed"] += 1
            counts["positive_allowance"] += row["allowance"] is not None and row["allowance"] > 0
            counts["final_present"] += row["final_present"]
            if kernel is not None:
                counts["positive_paid_rhs"] += kernel["paid_growth_rhs"] is not None and kernel["paid_growth_rhs"] > 0
                counts["paid_rhs_zero"] += kernel["paid_growth_rhs"] is not None and kernel["paid_growth_rhs"] == 0
                counts["paid_rhs_unobserved"] += kernel["paid_growth_rhs"] is None
                counts["kernel_dropped"] += not kernel["kept"]
                counts["final_differs_from_kernel_rounded"] += row["final_present"] and not C.same(row["final_value"], kernel["rounded"])
            counts["recipe_payment_occurrences"] += len(row["payments"])
            counts["bookkeeping_paid_sum"] += sum(p["bookkeeping_paid"] for p in row["payments"])
            if row["payments"]:
                counts["payment_rows"] += 1
                if len(witnesses) < WITNESS_ROWS:
                    witnesses.append(dict(source_turn=source, row=row, accounting_status=costs["status"]))
    C.require(C.same(final_counter, final_effort), "practice final counter differs from ordinary final World")
    captured = counts["captured_frames"]
    for key, expected in dict(captured_slots=captured*16, recorded_unavailable_slots=counts["unavailable_frames"]*16,
            accounting_mismatches=counts["accounting_mismatches"],
            usable_trace=captured == C.END-start and not counts["accounting_mismatches"]).items():
        C.require(C.same(index[key], expected), "practice index derived coverage differs")
    expected = dict(index_sha256=C.sha(folder / "practice-trace-index.json"),
        baseline_sha256=C.sha(folder / "practice-counter-baseline.json"),
        **{key: index[key] for key in ("complete_grid", "usable_trace", "recorded_frames", "captured_slots",
           "recorded_unavailable_slots", "unrecorded_slots", "accounting_mismatches")})
    C.require(C.same(summary, expected), "worker practice summary differs from retained journal")
    return dict(index_sha256=expected["index_sha256"], baseline_sha256=expected["baseline_sha256"],
        journal=index["journal"], initial_effort_spent=baseline["initial_effort_spent"], final_effort_spent=final_counter,
        complete_grid=True, usable_trace=index["usable_trace"], expected_slots=index["expected_slots"],
        captured_slots=index["captured_slots"], recorded_unavailable_slots=index["recorded_unavailable_slots"],
        unrecorded_slots=0, counts=counts, unavailable_reasons=reasons, payment_witness_rows=witnesses,
        omitted_payment_witness_rows=counts["payment_rows"]-len(witnesses),
        witness_limit=WITNESS_ROWS, post_boundary_comparable_sha256=post_boundary.hexdigest(),
        scope="actual payments/allowances/computed kernel/final commit; no counterfactual RHS or welfare attribution")
