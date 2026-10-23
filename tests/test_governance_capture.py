"""Bounded explicit synthetic capture gates; no runtime or provider execution."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError, replace
from fractions import Fraction
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
from threading import Barrier

import pytest

from chronicler import governance_capture as gc
from chronicler import governance_kernel_harness as h
from chronicler import governance_measurements as gm
from chronicler import governance_capital as c

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/governance_capture_report.py"
IDENTITY = gm.SourceIdentity("1" * 40, "2" * 40, "explicit test caller")
ORIGIN = gm.MeasurementOrigin.SYNTHETIC_FOUR_KERNEL_HARNESS


def driver():
    spec = importlib.util.spec_from_file_location("capture_driver_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run(opening, frame, policy, identity=IDENTITY):
    return gc.capture_frame(enabled=True, opening=opening, frame=frame,
        policy=policy, origin=ORIGIN, source_identity=identity)


def test_fixture_matches_direct_public_run_measure_and_existing_example():
    script = driver()
    opening, frames, policy = script.existing_fixture()
    captured = script.capture_fixture(origin=ORIGIN, source_identity=IDENTITY)
    assert captured[0].opening == opening
    for item, frame in zip(captured, frames):
        direct = h.run_kernel_frame(enabled=True, opening=item.opening,
                                    observations=frame, policy=policy)
        measured = gm.measure_governance_result(opening=item.opening, result=direct,
            origin=ORIGIN, source_identity=IDENTITY)
        assert item.result == direct
        assert item.measurement == measured
        assert item.policy == policy
        assert item.frame == frame
        gc.validate_capture(item)
        assert item.source_identity is IDENTITY
        assert item.origin is ORIGIN
        assert item.status == "captured"
        assert item.measurement.source_turn == frame.source_turn
        assert item.measurement.effective_turn == frame.source_turn + 1
        assert item.measurement.opening_last_committed_turn == frame.source_turn - 1
    assert captured[1].opening == captured[0].result.carry
    spec = importlib.util.spec_from_file_location("accepted_example_test", ROOT / "examples/governance_four_kernel.py")
    example = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(example)
    assert captured[1].result == example.experiment()
    assert captured[1].result.receipts[0].spending.state.exact_political_capital == Fraction(0)
    with pytest.raises(FrozenInstanceError):
        captured[0].opening = captured[1].opening


def test_sub_float_residual_and_exact_opening_survive_both_frames():
    opening, frames, policy = driver().existing_fixture()
    residual = Fraction(1, 10**40)
    balance = Fraction(3, 10) + residual
    civ = opening.civilizations[0]
    opening = replace(opening, civilizations=(replace(civ,
        governance=c.GovernanceState(0, .5, float(balance), balance)),))
    first = run(opening, frames[0], policy)
    second = run(first.result.carry, frames[1], policy)
    assert first.opening is opening
    assert second.opening is first.result.carry
    for item in (first, second):
        measurement = item.measurement.civilizations[0]
        assert measurement.opening_capital.exact_balance.as_fraction() == item.opening.civilizations[0].governance.exact_political_capital
        encoded = json.loads(gm.measurement_json(item.measurement))
        assert encoded["civilizations"][0]["opening_capital"]["exact_balance"]["fraction"] == [
            measurement.opening_capital.exact_balance.numerator, measurement.opening_capital.exact_balance.denominator]
    assert second.result.receipts[0].spending.state.exact_political_capital == residual


@pytest.mark.parametrize("explicit", [False, True])
def test_disabled_returns_identical_opening_and_consumes_nothing(monkeypatch, explicit):
    opening, _, _ = driver().existing_fixture()
    class Unreadable:
        def __getattribute__(self, name):
            raise AssertionError("disabled input was read")
    poison = Unreadable()
    def fail(*args, **kwargs):
        raise AssertionError("disabled call executed")
    monkeypatch.setattr(gm, "measure_governance_result", fail)
    original = h.run_kernel_frame
    class NoExecutionHarness:
        HarnessCarry = h.HarnessCarry
        def __getattr__(self, name):
            raise AssertionError("disabled call accessed harness execution")
    # Substitute only the capture module's local dependency reference. The
    # actual shared public harness function is never changed, even by this gate.
    monkeypatch.setattr(gc, "harness", NoExecutionHarness())
    item = gc.capture_frame(opening=opening, frame=poison, policy=poison,
                            origin=poison, source_identity=poison,
                            **({"enabled": False} if explicit else {}))
    assert item.opening is opening
    assert not item.enabled and item.status == "disabled_no_measurement"
    assert (item.result, item.measurement, item.policy, item.origin, item.source_identity, item.frame) == (None,) * 6
    assert h.run_kernel_frame is original
    gc.validate_capture(item)


@pytest.mark.parametrize("variant", ["costs", "calibration", "limit"])
def test_equal_policy_ids_retain_distinct_full_policies_across_contiguous_carries(variant):
    opening, frames, policy = driver().existing_fixture()
    alternatives = dict(costs=replace(policy, spend_costs=c.SpendCosts(.05, .2, .15)),
        calibration=replace(policy, elite_calibration=replace(policy.elite_calibration,
            ratchet_up_rate=.2)), limit=replace(policy, capital_limit=Fraction(11)))
    changed = alternatives[variant]
    first = run(opening, frames[0], policy)
    second = run(first.result.carry, frames[1], changed)
    assert first.policy is policy and second.policy is changed
    assert first.frame is frames[0] and second.frame is frames[1]
    assert first.result.carry == second.opening
    assert first.policy.policy_id == second.policy.policy_id
    assert first.policy != second.policy
    # A sequence consumer's fixed-policy requirement must use this full equality.
    assert not all(item.policy == first.policy for item in (first, second))
    gc.validate_capture(first)
    gc.validate_capture(second)


def test_cached_measurement_revalidation_is_pure_and_rejects_mismatched_cache(monkeypatch):
    opening, frames, policy = driver().existing_fixture()
    first = run(opening, frames[0], policy)
    second = run(first.result.carry, frames[1], policy)
    class PureOnlyHarness:
        HarnessCarry = h.HarnessCarry
        HarnessResult = h.HarnessResult
        HarnessPolicy = h.HarnessPolicy
        SyntheticFrame = h.SyntheticFrame
        def __getattr__(self, name):
            raise AssertionError("validation accessed a kernel execution API")
    monkeypatch.setattr(gc, "harness", PureOnlyHarness())
    gc.validate_capture(first)
    with pytest.raises(ValueError, match="cached measurement"):
        gc.validate_capture(replace(first, measurement=second.measurement))
    with pytest.raises(ValueError, match="cached measurement"):
        gc.validate_capture(replace(first, measurement=replace(first.measurement,
            source_identity=gm.SourceIdentity("3" * 40, "4" * 40, "wrong cached identity"))))


@pytest.mark.parametrize("changes", [dict(source_turn=1), dict(ownership_epoch=1),
    dict(source_turn=False), dict(ownership_epoch=False), dict(origin="production")])
def test_retained_frame_epoch_and_origin_revalidation(changes):
    opening, frames, policy = driver().existing_fixture()
    item = run(opening, frames[0], policy)
    with pytest.raises(ValueError, match="frame origin/epochs|invalid type"):
        gc.validate_capture(replace(item, frame=replace(item.frame, **changes)))


@pytest.mark.parametrize("missing", ["frame", "policy", "origin", "source_identity"])
def test_enabled_requires_all_explicit_inputs(missing):
    opening, frames, policy = driver().existing_fixture()
    kwargs = dict(opening=opening, frame=frames[0], policy=policy, origin=ORIGIN,
                  source_identity=IDENTITY, enabled=True)
    del kwargs[missing]
    with pytest.raises(ValueError):
        gc.capture_frame(**kwargs)


@pytest.mark.parametrize("enabled", [1, 0, None, "true"])
def test_opt_in_is_an_exact_boolean(enabled):
    opening, _, _ = driver().existing_fixture()
    with pytest.raises(ValueError, match="boolean"):
        gc.capture_frame(opening=opening, enabled=enabled)


@pytest.mark.parametrize("change", ["source", "ownership", "duplicate", "missing", "origin"])
def test_harness_refusals_publish_nothing_and_leave_inputs_unchanged(change):
    opening, frames, policy = driver().existing_fixture()
    frame = frames[0]
    changes = dict(source=dict(source_turn=1), ownership=dict(ownership_epoch=1),
        duplicate=dict(civilizations=frame.civilizations * 2), missing=dict(civilizations=()),
        origin=dict(origin="production"))
    bad = replace(frame, **changes[change])
    before = h.carry_to_json(opening)
    with pytest.raises(ValueError):
        run(opening, bad, policy)
    assert h.carry_to_json(opening) == before
    assert frame == frames[0]


def test_measurement_failure_after_pure_result_publishes_nothing(monkeypatch):
    opening, frames, policy = driver().existing_fixture()
    inputs = (opening, frames, policy)
    before = h.carry_to_json(opening)
    observed = []
    def fail(**kwargs):
        assert kwargs["opening"] is opening
        observed.append(kwargs["result"])
        raise ValueError("injected measurement failure")
    monkeypatch.setattr(gm, "measure_governance_result", fail)
    with pytest.raises(ValueError, match="measurement failure"):
        run(opening, frames[0], policy)
    assert len(observed) == 1 and observed[0].carry.effective_turn == 1
    assert (opening, frames, policy) == inputs
    assert h.carry_to_json(opening) == before


@pytest.mark.parametrize("damage", ["disabled", "duplicate", "missing", "policy", "spend"])
def test_measurement_refusals_escape_without_successful_capture(monkeypatch, damage):
    script = driver()
    opening, frames, policy = script.existing_fixture()
    first = run(opening, frames[0], policy)
    opening = first.result.carry
    original = gm.measure_governance_result
    def broken(**kwargs):
        result = kwargs["result"]
        if damage == "disabled":
            result = replace(result, policy_id=None)
        elif damage == "duplicate":
            result = replace(result, receipts=result.receipts * 2)
        elif damage == "missing":
            result = replace(result, receipts=())
        elif damage == "policy":
            result = replace(result, policy_id="unreviewed")
        else:
            receipt = result.receipts[0]
            decisions = receipt.spending.decisions
            bad = replace(decisions[0], exact_capital_after=Fraction(1, 7))
            receipt = replace(receipt, spending=replace(receipt.spending, decisions=(bad,) + decisions[1:]))
            result = replace(result, receipts=(receipt,))
        return original(**dict(kwargs, result=result))
    monkeypatch.setattr(gm, "measure_governance_result", broken)
    before = h.carry_to_json(opening)
    with pytest.raises(ValueError):
        run(opening, frames[1], policy)
    assert h.carry_to_json(opening) == before


@pytest.mark.parametrize("fail_one", [False, True])
def test_genuine_interleaving_keeps_each_callers_result_and_harness_identity(monkeypatch, fail_one):
    opening, frames, policy = driver().existing_fixture()
    other_civ = replace(opening.civilizations[0], civ_id=7,
        governance=c.GovernanceState(0, .5, .8, Fraction(4, 5)))
    other_opening = h.HarnessCarry(0, -1, (7,), (other_civ,))
    obs = frames[0].civilizations[0]
    other_frame = replace(frames[0], civilizations=(replace(obs, civ_id=7,
        ambition_snapshot=replace(obs.ambition_snapshot, civ_id="7", ruler_id="other-reign")),))
    other_identity = gm.SourceIdentity("3" * 40, "4" * 40, "other caller")
    cases = [(opening, frames[0], policy, IDENTITY), (other_opening, other_frame, policy, other_identity)]
    serial = [run(*case) for case in cases]
    original_harness = h.run_kernel_frame
    original_measurement = gm.measure_governance_result
    barrier = Barrier(2, timeout=10)
    def interleaved(**kwargs):
        assert h.run_kernel_frame is original_harness
        barrier.wait()
        if fail_one and kwargs["source_identity"] is IDENTITY:
            raise ValueError("one caller failed")
        result = original_measurement(**kwargs)
        assert h.run_kernel_frame is original_harness
        return result
    monkeypatch.setattr(gm, "measure_governance_result", interleaved)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(run, *case) for case in cases]
        if fail_one:
            with pytest.raises(ValueError, match="one caller failed"):
                futures[0].result(timeout=15)
        else:
            assert futures[0].result(timeout=15) == serial[0]
        assert futures[1].result(timeout=15) == serial[1]
    assert h.run_kernel_frame is original_harness
    assert serial[0].opening is opening and serial[1].opening is other_opening


def test_unavailable_catalogue_and_derived_accession_signal_stay_exact():
    captures = driver().capture_fixture(origin=ORIGIN, source_identity=IDENTITY)
    for item in captures:
        assert item.measurement.unavailable
        for metric in item.measurement.unavailable:
            assert metric.value is None and metric.reason
        assert {m.key for m in item.measurement.unavailable} >= {
            "enact_rate", "repeal_rate", "institution_tenure", "psi",
            "institutional_regime_classification", "scale_qualification"}
        accrual = item.result.receipts[0].accrual
        expected = accrual.exact_opening_political_capital != item.result.receipts[0].spending.state.exact_political_capital
        assert item.measurement.civilizations[0].accrual.accession_pool_applied is expected


def process(args, seed="0", code=None):
    env = dict(os.environ, PYTHONHASHSEED=seed, PYTHONPATH=str(ROOT / "src"))
    command = [sys.executable, "-B", "-c", code] if code else [sys.executable, "-B", str(SCRIPT), *args]
    return subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True, timeout=30)


ENABLED_ARGS = ["--enabled", "--fixture", "existing-two-turn", "--origin", ORIGIN.value,
                "--revision", IDENTITY.revision, "--tree", IDENTITY.tree, "--source-label", IDENTITY.label]


def test_disabled_driver_ignores_supplied_provenance_and_imports_no_fixture(monkeypatch, capsys):
    script = driver()
    def fail(*args, **kwargs):
        raise AssertionError("fixture executed")
    monkeypatch.setattr(script, "existing_fixture", fail)
    assert script.main(["--revision", "/nonexistent/input", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["status"] == "disabled_no_measurement" and data["captures"] == []
    assert data["unavailable"] == [dict(key=o.key, reason=o.reason) for o in gm.m67_measurement_obligation_catalogue()]
    code = 'import runpy,sys; runpy.run_path("scripts/governance_capture_report.py",run_name="__main__")'
    assert process([], code=code).returncode == 0


def test_enabled_driver_requires_explicit_inputs_before_fixture_import():
    result = process(["--enabled"])
    assert result.returncode == 2 and not result.stdout
    assert "requires fixture" in result.stderr
    result = process([*ENABLED_ARGS, "--revision", "invalid"])
    assert result.returncode == 2 and not result.stdout


INVALID_OPTIONAL_ARGS = [
    ["--origin", "invalid-declared-origin"],
    ["--fixture", "invalid-fixture"],
    ["--revision", "invalid-revision"],
    ["--tree", "invalid-tree"],
    ["--source-label", "  "],
    ["--origin", "invalid-declared-origin", "--fixture", "invalid-fixture",
     "--revision", "invalid", "--tree", "invalid"],
    ["--origin"],
]


@pytest.mark.parametrize("args", INVALID_OPTIONAL_ARGS)
def test_disabled_dispatch_precedes_all_optional_validation(monkeypatch, capsys, args):
    script = driver()
    def fail(*args, **kwargs):
        raise AssertionError("disabled dispatch parsed optional values or executed fixture")
    monkeypatch.setattr(script, "existing_fixture", fail)
    monkeypatch.setattr(script, "capture_fixture", fail)
    monkeypatch.setattr(script, "build_parser", fail)
    assert script.main([]) == 0
    expected = capsys.readouterr().out
    assert script.main(args) == 0
    output = capsys.readouterr()
    assert output.out == expected and not output.err
    assert json.loads(output.out)["status"] == "disabled_no_measurement"


@pytest.mark.parametrize("args", INVALID_OPTIONAL_ARGS)
def test_enabled_dispatch_still_rejects_invalid_optional_values(monkeypatch, capsys, args):
    script = driver()
    def fail(*args, **kwargs):
        raise AssertionError("invalid enabled input reached fixture execution")
    monkeypatch.setattr(script, "existing_fixture", fail)
    monkeypatch.setattr(script, "capture_fixture", fail)
    with pytest.raises(SystemExit) as error:
        script.main([*ENABLED_ARGS, *args])
    assert error.value.code == 2
    output = capsys.readouterr()
    assert not output.out and output.err


@pytest.mark.parametrize("help_flag", ["-h", "--help"])
@pytest.mark.parametrize("enabled", [False, True])
def test_explicit_help_keeps_full_help_without_optional_validation(monkeypatch, capsys, help_flag, enabled):
    script = driver()
    def fail(*args, **kwargs):
        raise AssertionError("help executed fixture")
    monkeypatch.setattr(script, "capture_fixture", fail)
    args = ["--origin", "invalid-origin", "--fixture", "invalid-fixture", help_flag]
    if enabled:
        args.insert(0, "--enabled")
    with pytest.raises(SystemExit) as error:
        script.main(args)
    assert error.value.code == 0
    output = capsys.readouterr()
    assert "usage:" in output.out and "--fixture" in output.out and "--source-label" in output.out
    assert "disabled_no_measurement" not in output.out and not output.err


def test_invalid_disabled_cli_receipt_matches_no_arguments_in_fresh_processes():
    outputs = [process(args, seed) for seed in ("0", "42")
               for args in ([], INVALID_OPTIONAL_ARGS[5])]
    assert all(result.returncode == 0 and not result.stderr for result in outputs)
    assert all(result.stdout == outputs[0].stdout for result in outputs)


@pytest.mark.parametrize("args", [[], ENABLED_ARGS, [*ENABLED_ARGS, "--json"]])
def test_driver_bytes_match_fresh_hash_seeds(args):
    outputs = [process(args, seed) for seed in ("0", "42")]
    assert all(result.returncode == 0 and not result.stderr for result in outputs)
    assert outputs[0].stdout == outputs[1].stdout


def test_fresh_serial_and_concurrent_outputs_match_and_imports_stay_detached():
    code = '''import importlib.util, sys
from concurrent.futures import ThreadPoolExecutor
from chronicler import governance_capture as gc
from chronicler import governance_kernel_harness as h
from chronicler import governance_measurements as gm
spec=importlib.util.spec_from_file_location("driver", "scripts/governance_capture_report.py")
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
identity=gm.SourceIdentity("1"*40,"2"*40,"fresh process")
original=h.run_kernel_frame
assert "explicit_capture_fixture_policy" not in sys.modules
assert not any(name in sys.modules for name in ("chronicler.simulation","chronicler.models","chronicler.analytics","chronicler_agents","random","numpy"))
def run():
    return m.capture_fixture(origin=gm.MeasurementOrigin.SYNTHETIC_FOUR_KERNEL_HARNESS,source_identity=identity)
serial=run()
with ThreadPoolExecutor(max_workers=2) as pool:
    concurrent=list(pool.map(lambda _: run(), range(2)))
assert h.run_kernel_frame is original
assert all(m.capture_json(items)==m.capture_json(serial) for items in concurrent)
print(m.capture_json(serial),end="")
'''
    results = [process([], seed, code) for seed in ("0", "42")]
    assert all(result.returncode == 0 for result in results), [r.stderr for r in results]
    assert results[0].stdout == results[1].stdout
