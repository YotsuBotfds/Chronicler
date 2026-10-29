"""Exact small scalar journals only; no World, native runtime or physics."""
from copy import deepcopy
import hashlib
import importlib
import json
import math
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def modules(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    return tuple(importlib.import_module(name) for name in (
        "research_practice_recorder", "research_practice_contract", "research_practice_trace_reader"))


def frame(r, source, attempt, *, captured=True, changed=False, frequent=False):
    if not captured:
        return NS(status="unavailable", reason="phase_unobserved", source_turn=source,
                  attempt=attempt, scope="turn", rows=(), encoded_row_bytes=0)
    rows, raw_rows = [], []
    for region, recipe in r.SELECTED:
        payments = []
        paid = region == 0 and (source == 61 or frequent and 60 <= source < 81)
        if paid:
            share = 1/3 if recipe == "irrigation" else 2/3
            payments = [dict(seat=7, share=share, confidence=share, bookkeeping_paid=int(recipe == "irrigation"),
                             allocation_group_paid=1, event_id="")]
        kernel = None
        if region == 0:
            kernel = dict(before=.98, cap=1., prerequisites_met=True, population=60, shortfall=0., disruption=1.,
                effort_supplied=True, allowance_used=.05 if paid else 0., ordinary_growth=0.,
                paid_growth_rhs=math.nextafter(.0125, 1.) if paid else 0.,
                total_growth=.05 if paid else 0., forgetting=-0., inflow=0., pre_clip=1.03 if paid else .98,
                clipped=1. if paid else .98, rounded=1. if paid else .98, kept=True)
        row = dict(region=region, recipe=recipe, allowance=.05 if paid else 0., allowance_present=paid,
            allocations_observed=True, payments=payments, kernel=kernel,
            final_present=kernel is not None, final_value=(.97 if changed and source == 100 else .98) if kernel else None)
        raw_rows.append(row)
        rows.append(NS(**{**row, "payments": tuple(NS(**p) for p in payments),
                          "kernel": NS(**kernel) if kernel else None}))
    return NS(status="captured", reason=None, source_turn=source, attempt=attempt, scope="turn",
              rows=tuple(rows), encoded_row_bytes=len(r.encoded(raw_rows)))


def journal(modules, folder, *, role="active", captured=False, changed=False, frequent=False):
    r, c, t = modules
    folder.mkdir()
    start, actual = (0 if role == "parent" else 60), 9
    baseline = dict(schema_version=1, seed=2001, role=role, source_turn=start,
        initial_effort_spent=actual, expected_checkpoint_effort=None if role == "parent" else actual,
        clock="immediately before first actual observer/physics call")
    (folder / "practice-counter-baseline.json").write_bytes(r.encoded(baseline)+b"\n")
    recorder = r.PracticeRecorder(folder, seed=2001, role=role, initial_effort_spent=actual)
    for source in range(start, 180):
        actual += captured and (source == 61 or frequent and 60 <= source < 81)
        recorder.append(frame(r, source, source-start+1, captured=captured, changed=changed, frequent=frequent),
                        source_turn=source, effort_spent=actual)
    index = recorder.finish()
    summary = dict(index_sha256=c.sha(folder / "practice-trace-index.json"),
        baseline_sha256=c.sha(folder / "practice-counter-baseline.json"),
        **{key: index[key] for key in ("complete_grid", "usable_trace", "recorded_frames", "captured_slots",
           "recorded_unavailable_slots", "unrecorded_slots", "accounting_mismatches")})
    return summary, actual


def inspect(modules, folder, summary, actual, *, role="active"):
    return modules[2].inspect(folder, 2001, role, summary,
        checkpoint_effort=None if role == "parent" else 9, final_effort=actual)


def test_exact_payment_rhs_cap_round_and_separate_commit_from_writer(modules, tmp_path):
    folder = tmp_path / "active"
    summary, actual = journal(modules, folder, captured=True)
    result = inspect(modules, folder, summary, actual)
    assert result["usable_trace"] and result["captured_slots"] == 120*16
    assert result["initial_effort_spent"] == 9 and result["final_effort_spent"] == 10
    counts = result["counts"]
    assert counts["recipe_payment_occurrences"] == counts["payment_rows"] == 2
    assert counts["bookkeeping_paid_sum"] == counts["matched_group_debit_sum"] == 1
    assert counts["positive_allowance"] == counts["positive_paid_rhs"] == 2
    assert counts["paid_rhs_zero"] == 238 and counts["paid_rhs_unobserved"] == 0
    assert counts["kernel_computed"] == 240 and counts["kernel_uncomputed"] == 120*14
    irrigation, masonry = result["payment_witness_rows"]
    assert irrigation["source_turn"] == masonry["source_turn"] == 61
    assert masonry["row"]["payments"][0]["bookkeeping_paid"] == 0 and masonry["row"]["allowance"] > 0
    assert all(not row["row"]["payments"][0]["event_id"] for row in (irrigation, masonry))
    kernel = irrigation["row"]["kernel"]
    assert kernel["paid_growth_rhs"].hex() == math.nextafter(.0125, 1.).hex()
    assert kernel["forgetting"].hex() == (-0.).hex()
    assert kernel["pre_clip"] > kernel["cap"] and kernel["clipped"] == kernel["rounded"] == 1.
    assert irrigation["row"]["final_value"] == .98 and counts["final_differs_from_kernel_rounded"] == 2


def test_full_unavailable_grid_is_not_zero_exposure(modules, tmp_path):
    folder = tmp_path / "unavailable"
    summary, actual = journal(modules, folder)
    result = inspect(modules, folder, summary, actual)
    assert result["complete_grid"] and not result["usable_trace"]
    assert result["captured_slots"] == result["unrecorded_slots"] == 0
    assert result["recorded_unavailable_slots"] == 120*16
    assert result["unavailable_reasons"] == {"phase_unobserved": 120}
    assert result["counts"]["matched_debit_frames"] == 0
    assert result["counts"]["kernel_computed"] == result["counts"]["kernel_uncomputed"] == 0


def test_parent_active_post60_trace_equal_only_after_validated_attempt_offset(modules, tmp_path):
    a, b, different = (tmp_path / name for name in ("parent", "active", "different"))
    parent_summary, parent_actual = journal(modules, a, role="parent", captured=True)
    active_summary, active_actual = journal(modules, b, captured=True)
    other_summary, other_actual = journal(modules, different, captured=True, changed=True)
    parent = inspect(modules, a, parent_summary, parent_actual, role="parent")
    active = inspect(modules, b, active_summary, active_actual)
    other = inspect(modules, different, other_summary, other_actual)
    assert parent["post_boundary_comparable_sha256"] == active["post_boundary_comparable_sha256"]
    assert parent["post_boundary_comparable_sha256"] != other["post_boundary_comparable_sha256"]


@pytest.mark.parametrize("fault", ["wrong_index_offset", "wrong_index_type", "wrong_summary", "truncated", "trailing",
    "baseline_cp", "baseline_type", "final_counter", "attempt", "unknown_frame_field", "bool_kernel", "duplicate_key"])
def test_reader_rejects_linkage_type_or_byte_mutations(modules, tmp_path, fault):
    r, c, t = modules
    folder = tmp_path / "bad"
    summary, actual = journal(modules, folder)
    index_path, journal_path = folder / "practice-trace-index.json", folder / "practice-trace.jsonl"
    if fault.startswith("wrong_index"):
        index = c.read(index_path)
        index["entries"][0]["offset" if fault == "wrong_index_offset" else "bytes"] = 1 if fault == "wrong_index_offset" else True
        index_path.write_bytes(r.encoded(index)+b"\n")
        summary["index_sha256"] = c.sha(index_path)
    elif fault == "wrong_summary":
        summary["index_sha256"] = "0"*64
    elif fault in ("baseline_cp", "baseline_type"):
        path = folder / "practice-counter-baseline.json"
        baseline = c.read(path)
        baseline["expected_checkpoint_effort"] = 8 if fault == "baseline_cp" else True
        path.write_bytes(r.encoded(baseline)+b"\n")
        summary["baseline_sha256"] = c.sha(path)
    elif fault == "final_counter":
        actual += 1
    else:
        raw = journal_path.read_bytes()
        if fault == "truncated":
            raw = raw[:-1]
        elif fault == "trailing":
            raw += b"{}\n"
        else:
            line, rest = raw.split(b"\n", 1)
            value = c.loads(line)
            if fault == "attempt":
                value["frame"]["attempt"] = 99
            elif fault == "unknown_frame_field":
                value["frame"]["extra"] = 1
            elif fault == "bool_kernel":
                value["frame"] = vars(frame(r, 60, 1, captured=True))
                value["frame"]["rows"] = [dict(region=0, recipe="irrigation", allowance=0., allowance_present=False,
                    allocations_observed=True, payments=[], kernel={field: False for field in r.KERNEL_FIELDS}, final_present=False, final_value=None)]
            line = r.encoded(value)
            if fault == "duplicate_key":
                line = line.replace(b'"schema_version":1', b'"schema_version":1,"schema_version":1', 1)
            raw = line+b"\n"+rest
        journal_path.write_bytes(raw)
        if fault in ("attempt", "unknown_frame_field", "bool_kernel", "duplicate_key"):
            # Preserve valid byte/index links so the semantic contract, rather
            # than an earlier digest mismatch, must reject these mutations.
            index, offset = c.read(index_path), 0
            for line, entry in zip(raw.splitlines(keepends=True), index["entries"]):
                value = json.loads(line)
                entry.update(offset=offset, bytes=len(line), sha256=hashlib.sha256(line).hexdigest(),
                             status=value["frame"]["status"], reason=value["frame"]["reason"],
                             accounting_status=value["accounting"]["status"])
                offset += len(line)
            index["journal"].update(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
            index_path.write_bytes(r.encoded(index)+b"\n")
            summary["index_sha256"] = c.sha(index_path)
    with pytest.raises((ValueError, TypeError)):
        inspect(modules, folder, summary, actual)


def test_normalization_refuses_wrong_handle_attempt_even_when_unavailable(modules):
    r, _, t = modules
    value = dict(status="unavailable", reason="phase_unobserved", source_turn=60, attempt=61,
                 scope="turn", rows=[], encoded_row_bytes=0)
    with pytest.raises(ValueError, match="attempt"):
        t.copied_frame(value, 60, 1)


def test_witness_limit_is_fixed_and_full_journal_is_still_indexed(modules):
    assert modules[2].WITNESS_ROWS == 32
    assert modules[2].TRACE_FILES == {"practice-counter-baseline.json", "practice-trace-index.json", "practice-trace.jsonl"}


def test_witness_overflow_counts_omissions_but_preserves_all_payment_rows(modules, tmp_path):
    r, c, t = modules
    folder = tmp_path / "witnesses"
    summary, actual = journal(modules, folder, captured=True, frequent=True)
    result = inspect(modules, folder, summary, actual)
    assert result["counts"]["payment_rows"] == 42 and result["counts"]["matched_group_debit_sum"] == 21
    assert len(result["payment_witness_rows"]) == 32 and result["omitted_payment_witness_rows"] == 10
    index, baseline = c.read(folder / "practice-trace-index.json"), c.read(folder / "practice-counter-baseline.json")
    assert sum(bool(row["payments"]) for record in t.records(folder, 2001, "active", index, baseline)
               for row in record["frame"]["rows"]) == 42
