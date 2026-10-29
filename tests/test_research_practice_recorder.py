"""Bounded metadata fixtures only; no World, native runtime or physics calls."""
from dataclasses import asdict, replace
import hashlib
import json
import math
import random
from types import SimpleNamespace as NS

import numpy as np
import pytest

from chronicler import practice_growth as P
from scripts import research_practice_recorder as R


def frame(source=60, attempt=1, *, paid=False, kernels=True):
    rows = []
    for region in range(8):
        for recipe in ("irrigation", "masonry"):
            share = 1/3 if recipe == "irrigation" else 2/3
            payments = ()
            if paid and region == 0:
                payments = (P.PaymentObservation(7, share, share,
                            1 if recipe == "irrigation" else 0, 1, ""),)
            allowance = .01 * share if payments else 0.
            kernel = P.KernelObservation(
                before=.5, cap=1., prerequisites_met=True, population=60, shortfall=0., disruption=1.,
                effort_supplied=True, allowance_used=allowance, ordinary_growth=0.,
                paid_growth_rhs=allowance * .25, total_growth=allowance * .25, forgetting=-0., inflow=0.,
                pre_clip=.5 + allowance * .25, clipped=.5 + allowance * .25,
                rounded=round(.5 + allowance * .25, 6), kept=True) if kernels else None
            rows.append(P.PracticeGrowthRow(region, recipe, allowance, bool(payments), True,
                payments, kernel, kernels, math.nextafter(.7, 1.) if kernels else None))
    rows = tuple(rows)
    size = len(json.dumps([asdict(row) for row in rows], separators=(",", ":"), allow_nan=False).encode())
    return P.PracticeGrowthReadout("captured", None, source, attempt, "turn", rows, size)


def changed_row(value, **changes):
    return replace(value, rows=(replace(value.rows[0], **changes),) + value.rows[1:])


def unavailable(source=None, attempt=0, reason="not_ready"):
    return P.PracticeGrowthReadout("unavailable", reason, source, attempt, "turn")


def read_journal(folder, report):
    data = (folder / report["journal"]["path"]).read_bytes()
    assert len(data) == report["journal"]["bytes"]
    assert hashlib.sha256(data).hexdigest() == report["journal"]["sha256"]
    lines = data.splitlines(keepends=True)
    assert len(lines) == report["recorded_frames"] == len(report["entries"])
    for line, entry in zip(lines, report["entries"]):
        assert data[entry["offset"]:entry["offset"] + entry["bytes"]] == line
        assert hashlib.sha256(line).hexdigest() == entry["sha256"]
    return [json.loads(line) for line in lines]


def test_public_dataclass_schema_exact_float_bits_and_separate_commit():
    value = frame(paid=True)
    copied = R.copy_frame(value, 60, 1)
    assert copied["encoded_row_bytes"] == value.encoded_row_bytes
    decoded = json.loads(R.encoded(copied))
    original, saved = value.rows[0], decoded["rows"][0]
    assert saved["kernel"]["forgetting"].hex() == (-0.).hex()
    assert saved["final_value"].hex() == original.final_value.hex()
    assert saved["final_value"] != saved["kernel"]["rounded"]
    assert type(saved["kernel"]["population"]) is int
    assert type(saved["kernel"]["prerequisites_met"]) is bool


def test_actual_payment_rows_not_event_ids_define_one_group_debit():
    copied = R.copy_frame(frame(paid=True), 60, 1)
    cost = R.accounting(copied, 4, 5)
    assert cost["status"] == "matched" and cost["delta"] == 1
    assert cost["groups"] == [dict(seat=7, region=0, group_paid=1, bookkeeping_paid=1)]
    masonry = copied["rows"][1]
    assert masonry["allowance"] > 0 and masonry["payments"][0]["bookkeeping_paid"] == 0
    assert all(not p["event_id"] for row in copied["rows"] for p in row["payments"])


@pytest.mark.parametrize("change", [
    lambda f: replace(f, source_turn=59),
    lambda f: replace(f, attempt=7),
    lambda f: replace(f, scope="phase"),
    lambda f: replace(f, reason="unexpected"),
    lambda f: replace(f, encoded_row_bytes=True),
    lambda f: replace(f, rows=list(f.rows)),
    lambda f: replace(f, rows=(f.rows[0],) * 16),
    lambda f: changed_row(f, region=True),
    lambda f: changed_row(f, recipe="other"),
    lambda f: changed_row(f, allowance_present=True, allowance=None),
    lambda f: changed_row(f, final_present=True, final_value=None),
    lambda f: changed_row(f, kernel=replace(f.rows[0].kernel, before=float("nan"))),
    lambda f: changed_row(f, kernel=replace(f.rows[0].kernel, population=True)),
    lambda f: changed_row(f, payments=(P.PaymentObservation(7, .5, .5, True, 1, ""),)),
    lambda f: changed_row(f, payments=(P.PaymentObservation(7, .5, .5, 1, 1, "x" * 129),)),
    lambda f: changed_row(f, payments=(P.PaymentObservation(7, .5, .5, 1, 1, ""),) * 41),
])
def test_bad_capture_is_retained_as_unavailable_not_a_zero(tmp_path, change):
    recorder = R.PracticeRecorder(tmp_path, seed=2000, role="active", initial_effort_spent=0)
    try:
        record = recorder.append(change(frame()), source_turn=60, effort_spent=0)
        assert record["frame"]["status"] == "unavailable"
        assert record["frame"]["reason"] == "recorder_contract" and record["frame"]["rows"] == []
        report = recorder.finish()
        assert report["recorded_unavailable_slots"] == 16 and report["unrecorded_slots"] == 119 * 16
        assert not report["usable_trace"] and not report["complete_grid"]
        assert read_journal(tmp_path, report) == [record]
    finally:
        recorder.close()


def test_accounting_mismatch_keeps_valid_raw_kernel_and_payment_rows(tmp_path):
    recorder = R.PracticeRecorder(tmp_path, seed=2001, role="active", initial_effort_spent=0)
    try:
        record = recorder.append(frame(paid=True), source_turn=60, effort_spent=0)
        assert record["frame"]["status"] == "captured" and len(record["frame"]["rows"]) == 16
        assert record["accounting"]["status"] == "mismatch"
        assert record["frame"]["rows"][0]["kernel"]["paid_growth_rhs"] > 0
        report = recorder.finish()
        assert report["accounting_mismatches"] == 1 and not report["usable_trace"]
        assert read_journal(tmp_path, report)[0] == record
    finally:
        recorder.close()


@pytest.mark.parametrize("reason", ["not_ready", "retention_limit", "stale_request", "closed"])
def test_unavailable_frame_preserves_unknown_source_and_actual_cost_counter(tmp_path, reason):
    recorder = R.PracticeRecorder(tmp_path, seed=2002, role="active", initial_effort_spent=4)
    try:
        record = recorder.append(unavailable(reason=reason), source_turn=60, effort_spent=5)
        assert record["frame"]["source_turn"] is None and record["frame"]["reason"] == reason
        assert record["accounting"] == dict(status="unavailable", before=4, after=5, delta=1, groups=None)
        assert record["frame"]["rows"] == []
    finally:
        recorder.close()


def test_unknown_initial_counter_is_not_invented_as_zero(tmp_path):
    recorder = R.PracticeRecorder(tmp_path, seed=2003, role="parent")
    try:
        record = recorder.append(frame(0, 1, paid=True), source_turn=0, effort_spent=9)
        assert record["accounting"]["status"] == "baseline_unobserved"
        assert record["accounting"]["before"] is record["accounting"]["delta"] is None
        assert record["accounting"]["groups"][0]["group_paid"] == 1
    finally:
        recorder.close()


def test_complete_grid_with_zero_exposure_keeps_all_sixteen_rows(tmp_path):
    recorder = R.PracticeRecorder(tmp_path, seed=2004, role="active", initial_effort_spent=0)
    for source in range(60, 180):
        record = recorder.append(frame(source, source - 59, kernels=False), source_turn=source, effort_spent=0)
        assert record["accounting"]["delta"] == 0 and record["frame"]["rows"][0]["kernel"] is None
    report = recorder.finish()
    assert report["complete_grid"] and report["usable_trace"] and report["captured_slots"] == 120 * 16
    assert report["recorded_unavailable_slots"] == report["unrecorded_slots"] == 0
    assert len(read_journal(tmp_path, report)) == 120
    assert (tmp_path / "practice-trace.jsonl").stat().st_size < 512 * 1024
    before = (tmp_path / "practice-trace-index.json").read_bytes()
    with pytest.raises(R.TraceContractError):
        recorder.finish()
    assert (tmp_path / "practice-trace-index.json").read_bytes() == before


def test_parent_complete_but_unavailable_is_not_usable_and_not_unattempted(tmp_path):
    recorder = R.PracticeRecorder(tmp_path, seed=2005, role="parent")
    for source in range(180):
        recorder.append(unavailable(source, source + 1, "phase_unobserved"), source_turn=source, effort_spent=0)
    report = recorder.finish()
    assert report["complete_grid"] and not report["usable_trace"]
    assert report["recorded_unavailable_slots"] == 180 * 16 and report["unrecorded_slots"] == 0
    assert len(read_journal(tmp_path, report)) == 180


@pytest.mark.parametrize("source", [59, 61, True])
def test_clock_error_does_not_consume_a_slot(tmp_path, source):
    recorder = R.PracticeRecorder(tmp_path, seed=2006, role="pause_new_trials", initial_effort_spent=0)
    try:
        with pytest.raises(R.TraceContractError):
            recorder.append(frame(), source_turn=source, effort_spent=0)
        assert recorder.next == 60 and recorder.entries == [] and recorder.offset == 0
    finally:
        recorder.close()


@pytest.mark.parametrize("seed,role", [(1999, "parent"), (2008, "active"), (2000., "parent"),
                                      (True, "parent"), (2000, "other"), (2000, True)])
def test_only_fixed_cohort_and_roles_open_journals(tmp_path, seed, role):
    with pytest.raises(R.TraceContractError):
        R.PracticeRecorder(tmp_path, seed=seed, role=role)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("name", ["practice-trace.jsonl", "practice-trace-index.json"])
def test_existing_evidence_is_never_overwritten(tmp_path, name):
    target = tmp_path / name
    target.write_bytes(b"old evidence")
    with pytest.raises(R.TraceContractError):
        R.PracticeRecorder(tmp_path, seed=2000, role="parent")
    assert target.read_bytes() == b"old evidence"


def test_partial_write_failure_keeps_prefix_and_cannot_publish(tmp_path):
    recorder = R.PracticeRecorder(tmp_path, seed=2007, role="active", initial_effort_spent=0)
    original = recorder.stream

    def fail(raw):
        original.write(raw[:7])
        original.flush()
        raise OSError("synthetic partial write")

    recorder.stream = NS(write=fail, close=original.close)
    with pytest.raises(OSError):
        recorder.append(frame(), source_turn=60, effort_spent=0)
    assert recorder.failed and recorder.next == 60
    with pytest.raises(R.TraceContractError):
        recorder.finish()
    recorder.close()
    assert (tmp_path / "practice-trace.jsonl.partial").stat().st_size == 7
    assert not (tmp_path / "practice-trace-index.json").exists()


def test_final_fsync_failure_closes_without_a_positive_index(tmp_path, monkeypatch):
    recorder = R.PracticeRecorder(tmp_path, seed=2000, role="active", initial_effort_spent=0)
    recorder.append(frame(), source_turn=60, effort_spent=0)

    def fail(fd):
        raise OSError("synthetic fsync failure")

    monkeypatch.setattr(R, "os", NS(fsync=fail))
    with pytest.raises(OSError):
        recorder.finish()
    assert recorder.closed and not (tmp_path / "practice-trace-index.json").exists()
    assert (tmp_path / "practice-trace.jsonl.partial").is_file()


def test_observation_and_journaling_do_not_consume_caller_rng(tmp_path):
    recorder = R.PracticeRecorder(tmp_path, seed=2000, role="active", initial_effort_spent=0)
    before = random.getstate(), np.random.get_state()
    recorder.append(frame(paid=True), source_turn=60, effort_spent=1)
    recorder.finish()
    after = random.getstate(), np.random.get_state()
    assert before[0] == after[0]
    assert before[1][0] == after[1][0] and np.array_equal(before[1][1], after[1][1])
    assert before[1][2:] == after[1][2:]
