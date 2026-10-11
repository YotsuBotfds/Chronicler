"""Controlled tests over the accepted tiny fixture; no production campaigns."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError, replace
from fractions import Fraction
import ast
import importlib.util
import json
import os
from pathlib import Path
import random
import subprocess
import sys
from threading import Barrier

import pytest

from chronicler import governance_capture as gc
from chronicler import governance_sequence as gs
from chronicler import governance_measurements as gm
from chronicler import governance_kernel_harness as h
from chronicler import governance_capital as c
from chronicler import institutions as i
from chronicler import elite_metrics as e
from chronicler import ruler_ambitions as a

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/governance_sequence_report.py"
ORIGIN = gm.MeasurementOrigin.SYNTHETIC_FOUR_KERNEL_HARNESS
IDENTITY = gm.SourceIdentity("1" * 40, "2" * 40, "explicit sequence test")
ENABLED = ["--enabled", "--fixture", "existing-two-turn", "--origin", ORIGIN.value,
           "--revision", IDENTITY.revision, "--tree", IDENTITY.tree,
           "--source-label", IDENTITY.label, "--max-frames", "2"]


def load(path=SCRIPT):
    spec = importlib.util.spec_from_file_location("unattached_sequence_test_driver", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fixture():
    return load().capture_fixture(origin=ORIGIN, source_identity=IDENTITY)


def run(opening, frame, policy, identity=IDENTITY):
    return gc.capture_frame(enabled=True, opening=opening, frame=frame, policy=policy,
                           origin=ORIGIN, source_identity=identity)


def inspect(items, cap=2):
    return gs.inspect_sequence(enabled=True, captures=items, max_frames=cap)


def assert_valid_then_rejected(items, message):
    before = tuple(h.carry_to_json(item.opening) for item in items)
    for item in items:
        gc.validate_capture(item)
    with pytest.raises(ValueError, match=message):
        inspect(items)
    assert before == tuple(h.carry_to_json(item.opening) for item in items)


def test_existing_fixture_exact_oracle_and_owner_bytes():
    items = fixture()
    result = inspect(items)
    document = gs.sequence_document(result)
    assert items[1].opening == h.carry_from_json(h.carry_to_json(items[0].result.carry))
    assert [(row.source_turn, row.effective_turn) for row in result.rows] == [(0, 1), (1, 2)]
    assert [row.net_capital_changes[0].as_fraction() for row in result.rows] == [Fraction(0), Fraction(-3, 10)]
    assert result.frame_count == 2 and result.adjacent_link_count == 1 and result.full_policy_equal is True
    assert document["first_source_turn"] == 0 and document["last_effective_turn"] == 2
    assert document["declared_source_identity"]["label"] == IDENTITY.label
    for index, (item, row) in enumerate(zip(items, document["rows"], strict=True)):
        assert row["ownership_epoch"] == item.frame.ownership_epoch == row["source_turn"]
        assert row["raw_measurement_json"] == gm.measurement_json(item.measurement)
        assert len(row["unavailable"]) == 20
        assert all(metric["value"] is None and metric["reason"] for metric in row["unavailable"])
        civ = row["civilizations"][0]
        assert civ["opening_capital"]["exact_balance"]["fraction"] == [3, 10]
        assert civ["published_capital"]["exact_balance"]["fraction"] == ([3, 10] if index == 0 else [0, 1])
        assert civ["derived_net_capital_change"]["fraction"] == ([0, 1] if index == 0 else [-3, 10])
        owned = json.loads(gm.measurement_json(item.measurement))
        assert row["metrics"] == [m for m in owned["metrics"] if m["key"] in gs.SUMMARY_METRICS]
        assert civ["spent_capital"] == owned["civilizations"][0]["spend_total"]
        assert civ["accrual"] == owned["civilizations"][0]["accrual"]
    final = items[-1].result.carry.civilizations[0]
    assert final.governance.effective_turn == 2
    assert final.governance.exact_political_capital == Fraction(0)
    assert final.governance.ruler_legitimacy == .6 and len(final.contributions) == 1
    assert "source_turn=1 -> effective_turn=2" in gs.render_report(result)
    assert gs.sequence_json(result) == gs.sequence_json(result)
    with pytest.raises(FrozenInstanceError):
        result.rows = ()
    with pytest.raises(FrozenInstanceError):
        result.rows[0].measurement = None
    document["rows"].clear()
    assert result.frame_count == 2


def test_disabled_before_optional_inputs_and_any_validation(monkeypatch):
    class Poison:
        def __getattribute__(self, name):
            raise AssertionError("poison read")
        def __iter__(self):
            raise AssertionError("poison consumed")
    def fail(*args, **kwargs):
        raise AssertionError("disabled optional work")
    monkeypatch.setattr(gc, "validate_capture", fail)
    monkeypatch.setattr(gm, "measure_governance_result", fail)
    monkeypatch.setattr(h, "run_kernel_frame", fail)
    assert gs.inspect_sequence(captures=Poison(), max_frames=Poison()) == gs.inspect_sequence()
    assert gs.inspect_sequence().status == "disabled_no_evidence"


@pytest.mark.parametrize("enabled", [0, 1, None, "true", ()])
def test_exact_boolean(enabled):
    with pytest.raises(ValueError, match="boolean"):
        gs.inspect_sequence(enabled=enabled)


@pytest.mark.parametrize("cap", [None, False, True, 0, -1, 1., "2"])
def test_exact_positive_bound(cap):
    with pytest.raises(ValueError, match="positive integer"):
        gs.inspect_sequence(enabled=True, captures=(), max_frames=cap)


def test_exact_tuple_no_lazy_consumption_and_cap_before_any_element(monkeypatch):
    def poison():
        raise AssertionError("generator consumed")
        yield
    class TupleSubclass(tuple):
        pass
    for container in ([], poison(), TupleSubclass()):
        with pytest.raises(ValueError, match="exact immutable tuple"):
            inspect(container)
    def fail(*args, **kwargs):
        raise AssertionError("element validation preceded bound")
    monkeypatch.setattr(gc, "validate_capture", fail)
    with pytest.raises(ValueError, match="count exceeds"):
        inspect((object(), object()), cap=1)


def test_empty_single_exact_cap_and_disabled_member():
    empty = inspect((), cap=1)
    document = gs.sequence_document(empty)
    assert empty.enabled and empty.status == "no_evidence" and empty.frame_count == 0
    assert document["full_policy_equal"] is None
    for key in ("declared_source_identity", "declared_origin", "identity_registry", "policy_id", "first_source_turn", "last_effective_turn"):
        assert document[key] is None
    first, second = fixture()
    singleton = inspect((second,), cap=1)
    assert singleton.adjacent_link_count == 0 and singleton.frame_count == 1
    assert singleton.rows[0].source_turn == 1
    assert inspect((first, second), cap=2).frame_count == 2
    off = gc.capture_frame(opening=second.opening)
    gc.validate_capture(off)
    with pytest.raises(ValueError, match="enabled captures"):
        inspect((first, off))
    for bad in (object(), replace(first, contract="unsupported")):
        with pytest.raises(ValueError):
            inspect((bad,))


def test_public_c_validator_runs_without_kernel_and_refuses_stale_cache(monkeypatch):
    items = fixture()
    observed = []
    original = gc.validate_capture
    def validate(item):
        observed.append(item)
        original(item)
    def forbidden(*args, **kwargs):
        raise AssertionError("inspection executed kernel")
    monkeypatch.setattr(gc, "validate_capture", validate)
    monkeypatch.setattr(h, "run_kernel_frame", forbidden)
    assert inspect(items).frame_count == 2 and observed == list(items)
    with pytest.raises(ValueError, match="cached measurement"):
        inspect((replace(items[0], measurement=items[1].measurement), items[1]))


def test_order_duplicates_reverse_gap_and_nonzero_start():
    first, second = fixture()
    for items in ((first, first), (second, first), (second, second)):
        assert_valid_then_rejected(items, "consecutive")
    civ = first.opening.civilizations[0]
    fork_opening = replace(first.opening, civilizations=(replace(civ,
        governance=c.GovernanceState(0, .5, .4, Fraction(2, 5))),))
    fork = run(fork_opening, first.frame, first.policy)
    assert fork != first and fork.frame.source_turn == first.frame.source_turn
    assert_valid_then_rejected((first, fork), "consecutive")
    civ = second.opening.civilizations[0]
    shifted = replace(civ, institutions=replace(civ.institutions, effective_turn=2),
        governance=replace(civ.governance, effective_turn=2),
        ratchet=replace(civ.ratchet, snapshot_turn=1))
    opening = h.HarnessCarry(2, 1, (0,), (shifted,))
    obs = second.frame.civilizations[0]
    frame = replace(second.frame, source_turn=2, ownership_epoch=2,
        civilizations=(replace(obs, ambition_snapshot=replace(obs.ambition_snapshot, turn=2)),))
    later = run(opening, frame, second.policy)
    gc.validate_capture(later)
    assert_valid_then_rejected((first, later), "consecutive")
    assert inspect((later,), cap=1).rows[0].source_turn == 2
    with pytest.raises(ValueError, match="watermark"):
        replace(second.opening, last_committed_turn=-1)


@pytest.mark.parametrize("field", ["institutions", "capital", "ratchet", "reign", "archives", "contributions", "pending", "evidence_log", "evidence_cursor"])
def test_complete_carry_mismatch_with_same_epoch_and_ids_is_individually_c_valid(field):
    first, second = fixture()
    civ = second.opening.civilizations[0]
    if field == "institutions":
        inst = i.InstitutionState(i.InstitutionType.CONSCRIPTION, 0, .5, 8., i.Faction.MERCHANT)
        changed = replace(civ, institutions=replace(civ.institutions, institutions=(inst,)))
    elif field == "capital":
        changed = replace(civ, governance=c.GovernanceState(1, .6, .4, Fraction(2, 5)))
    elif field == "ratchet":
        changed = replace(civ, ratchet=replace(civ.ratchet, conspicuous_consumption_index=.1))
    elif field == "reign":
        changed = replace(civ, reign=replace(civ.reign, ruler_event_tags=("new_ruler", "extra")))
    elif field == "archives":
        archived = replace(civ.reign, ruler_id="archived-test-reign")
        changed = replace(civ, archives=(h.ReignArchive(archived, ()),))
    elif field == "contributions":
        goal = replace(civ.reign.ambitions[0], completed=True)
        reign = replace(civ.reign, ambitions=(goal,))
        key = a.AmbitionContributionKey("0", reign.ruler_id, 0, 0, goal.ambition_type)
        changed = replace(civ, reign=reign, contributions=(h.Contribution(key, .1),))
    elif field == "pending":
        event = a.EvidenceEvent(0, 1, "0", "test-evidence")
        changed = replace(civ, evidence_cursor=1, evidence_log=(event,), pending_events=(event,))
    elif field == "evidence_log":
        event = a.EvidenceEvent(0, 0, "0", "test-evidence")
        changed = replace(civ, evidence_log=(event,))
    else:
        changed = replace(civ, evidence_cursor=1)
    opening = replace(second.opening, civilizations=(changed,))
    frame = second.frame
    if field in ("pending", "evidence_cursor"):
        obs = frame.civilizations[0]
        frame = replace(frame, civilizations=(replace(obs,
            ambition_snapshot=replace(obs.ambition_snapshot, event_cursor=1)),))
    altered = run(opening, frame, second.policy)
    assert altered.opening.effective_turn == second.opening.effective_turn
    assert altered.opening.identity_registry == second.opening.identity_registry
    assert_valid_then_rejected((first, altered), "complete adjacent carry")


@pytest.mark.parametrize("field", ["costs", "calibration", "coefficients", "conventions", "funding", "accession", "limit"])
def test_full_policy_equality_despite_same_id_and_individual_c_validity(field):
    first, second = fixture()
    policy = first.policy
    alternatives = dict(costs=replace(policy, spend_costs=c.SpendCosts(.05, .2, .15)),
        calibration=replace(policy, elite_calibration=replace(policy.elite_calibration, ratchet_up_rate=.2)),
        coefficients=replace(policy, institutions=replace(policy.institutions, legitimacy_erosion_rate=.2)),
        conventions=replace(policy, elite_conventions=replace(policy.elite_conventions, position_rounding=e.PositionRounding.CEIL)),
        funding=replace(policy, funding=i.FundingPolicy.EXTERNAL_AGGREGATE_RECORD),
        accession=replace(policy, capital_on_accession="reset_zero"),
        limit=replace(policy, capital_limit=Fraction(11)))
    changed = alternatives[field]
    # C checks retained correspondence, not causal proof of this declaration.
    altered = replace(second, policy=changed)
    assert altered.policy.policy_id == first.policy.policy_id and altered.policy != first.policy
    assert_valid_then_rejected((first, altered), "complete sequence policy")


@pytest.mark.parametrize("field", ["revision", "tree", "label"])
def test_full_source_declaration_equality(field):
    first, second = fixture()
    identity = replace(IDENTITY, **{field: "3" * 40 if field != "label" else "other declared source"})
    altered = run(second.opening, second.frame, second.policy, identity)
    assert_valid_then_rejected((first, altered), "declared sequence source")


def test_only_one_origin_is_supported_and_invalid_origin_is_c_rejection():
    assert len(tuple(gm.MeasurementOrigin)) == 1
    first, second = fixture()
    invalid = replace(second, origin="invented-origin")
    with pytest.raises(ValueError, match="MeasurementOrigin"):
        gc.validate_capture(invalid)
    with pytest.raises(ValueError, match="MeasurementOrigin"):
        inspect((first, invalid))


def test_individually_c_valid_different_registry_rejected():
    first, second = fixture()
    civ = second.opening.civilizations[0]
    other = replace(civ, civ_id=7, reign=replace(civ.reign, civ_id="7"))
    opening = h.HarnessCarry(1, 0, (7,), (other,))
    obs = second.frame.civilizations[0]
    frame = replace(second.frame, civilizations=(replace(obs, civ_id=7,
        ambition_snapshot=replace(obs.ambition_snapshot, civ_id="7")),))
    altered = run(opening, frame, second.policy)
    assert_valid_then_rejected((first, altered), "identity registry")


def test_exact_subfloat_net_and_accession_opening_are_not_spend():
    first, second = fixture()
    residual = Fraction(1, 10**40)
    balance = Fraction(3, 10) + residual
    civ = first.opening.civilizations[0]
    opening = replace(first.opening, civilizations=(replace(civ,
        governance=c.GovernanceState(0, .5, float(balance), balance)),))
    one = run(opening, first.frame, first.policy)
    two = run(one.result.carry, second.frame, second.policy)
    assert two.result.carry.civilizations[0].governance.exact_political_capital == residual
    data = json.loads(gs.sequence_json(inspect((two,), cap=1)))
    row = data["rows"][0]["civilizations"][0]
    assert row["published_capital"]["exact_balance"]["fraction"] == [1, 10**40]
    assert row["derived_net_capital_change"]["fraction"] == [-3, 10]
    # With reset accession the late-phase opening differs from the original wallet.
    reset_policy = replace(first.policy, capital_on_accession="reset_zero")
    reset = run(first.opening, first.frame, reset_policy)
    row = gs.sequence_document(inspect((reset,), cap=1))["rows"][0]["civilizations"][0]
    assert row["opening_capital"]["exact_balance"]["fraction"] == [3, 10]
    assert row["accrual"]["opening_capital"]["fraction"] == [0, 1]
    assert row["accrual"]["accession_pool_applied"] is True
    assert row["derived_net_capital_change"]["fraction"] == [-3, 10]


def test_subfloat_residual_in_derived_net_survives():
    first, _ = fixture()
    residual = Fraction(1, 10**40)
    balance = Fraction(3, 10) + residual
    policy = replace(first.policy, capital_on_accession="reset_zero")
    civ = first.opening.civilizations[0]
    opening = replace(first.opening, civilizations=(replace(civ,
        governance=c.GovernanceState(0, .5, float(balance), balance)),))
    item = run(opening, first.frame, policy)
    gc.validate_capture(item)
    sequence = inspect((item,), cap=1)
    net = sequence.rows[0].net_capital_changes[0]
    assert net.as_fraction() == -balance
    assert net.as_fraction() != Fraction(-3, 10)
    data = json.loads(gs.sequence_json(sequence))
    assert data["rows"][0]["civilizations"][0]["derived_net_capital_change"]["fraction"] == [net.numerator, net.denominator]


def test_existing_repeal_metric_used_once_and_empty_registry_stays_unavailable():
    first, second = fixture()
    civ = second.opening.civilizations[0]
    inst = i.InstitutionState(i.InstitutionType.HOLY_INQUISITION, 0, .5, 2., i.Faction.MERCHANT)
    opening = replace(second.opening, civilizations=(replace(civ,
        institutions=i.InstitutionSnapshot(1, (inst,)),
        governance=c.GovernanceState(1, .6, .5, Fraction(1, 2))),))
    obs = second.frame.civilizations[0]
    frame = replace(second.frame, civilizations=(replace(obs, factions=i.FactionWeights(.1, .6, .2, .1)),))
    forced = run(opening, frame, second.policy)
    assert forced.result.receipts[0].institutions.repeal_outcomes
    assert any(event.event_type == "institution_repealed" for event in forced.result.receipts[0].institutions.events)
    data = gs.sequence_document(inspect((forced,), cap=1))["rows"][0]
    assert next(m for m in data["metrics"] if m["key"] == "repeal_count")["value"] == 1
    assert next(m for m in data["metrics"] if m["key"] == "forced_repeal_count")["value"] == 1
    empty = run(h.HarnessCarry(0, -1, (), ()), replace(first.frame, civilizations=()), first.policy)
    gc.validate_capture(empty)
    row = gs.sequence_document(inspect((empty,), cap=1))["rows"][0]
    assert row["civilizations"] == []
    assert row["unavailable"] and all(m["value"] is None and m["reason"] for m in row["unavailable"])


def test_driver_exactly_two_kernel_calls_and_inspection_none(monkeypatch, capsys):
    driver = load()
    original = h.run_kernel_frame
    calls = []
    def counted(**kwargs):
        calls.append(kwargs)
        return original(**kwargs)
    monkeypatch.setattr(h, "run_kernel_frame", counted)
    argv_before = list(sys.argv)
    slots_before = dict(sys.modules)
    assert driver.main([*ENABLED, "--json"]) == 0
    assert len(calls) == 2
    assert sys.argv == argv_before
    assert dict(sys.modules) == slots_before
    assert json.loads(capsys.readouterr().out)["frame_count"] == 2


INVALID_OPTIONAL = [["--origin", "invalid"], ["--fixture", "/nonexistent.py"],
                    ["--max-frames", "invalid"], ["--max-frames", "0"],
                    ["--revision", "/invalid/path"], ["--tree", "invalid"],
                    ["--source-label", "  "], ["--origin"]]


@pytest.mark.parametrize("args", INVALID_OPTIONAL)
def test_cli_disabled_before_all_optional_validation(monkeypatch, capsys, args):
    driver = load()
    def forbidden(*args, **kwargs):
        raise AssertionError("off called optional validator/fixture")
    monkeypatch.setattr(driver, "build_parser", forbidden)
    monkeypatch.setattr(driver, "capture_fixture", forbidden)
    assert driver.main([]) == 0
    baseline = capsys.readouterr().out
    assert driver.main(args) == 0
    output = capsys.readouterr()
    assert output.out == baseline and not output.err


@pytest.mark.parametrize("args", INVALID_OPTIONAL)
def test_enabled_invalid_options_no_fixture_or_output(monkeypatch, capsys, args):
    driver = load()
    def forbidden(*args, **kwargs):
        raise AssertionError("invalid input executed fixture")
    monkeypatch.setattr(driver, "capture_fixture", forbidden)
    with pytest.raises(SystemExit) as error:
        driver.main([*ENABLED, *args])
    assert error.value.code == 2
    output = capsys.readouterr()
    assert not output.out and output.err


@pytest.mark.parametrize("help_flag", ["-h", "--help"])
@pytest.mark.parametrize("enabled", [False, True])
def test_explicit_help_ignores_optional_invalid_values(capsys, monkeypatch, help_flag, enabled):
    driver = load()
    def forbidden(*args, **kwargs):
        raise AssertionError("help fixture")
    monkeypatch.setattr(driver, "capture_fixture", forbidden)
    with pytest.raises(SystemExit) as error:
        driver.main((["--enabled"] if enabled else []) + ["--origin", "invalid", help_flag])
    assert error.value.code == 0
    assert "--max-frames" in capsys.readouterr().out


@pytest.mark.parametrize("json_output", [False, True])
def test_render_failure_emits_no_success_prefix(monkeypatch, capsys, json_output):
    driver = load()
    items = fixture()
    monkeypatch.setattr(driver, "capture_fixture", lambda **kwargs: items)
    original_limit = sys.get_int_max_str_digits()
    def fail(*args, **kwargs):
        raise ValueError("injected owner render failure")
    monkeypatch.setattr(gm, "measurement_json" if json_output else "render_report", fail)
    with pytest.raises(SystemExit) as error:
        driver.main([*ENABLED, *(["--json"] if json_output else [])])
    assert error.value.code == 2 and not capsys.readouterr().out
    assert sys.get_int_max_str_digits() == original_limit


def test_huge_public_integer_explicit_encoding_failure_no_global_limit_change(monkeypatch, capsys):
    first, second = fixture()
    digits = sys.get_int_max_str_digits()
    assert digits > 0
    balance = Fraction(1, 10**(digits + 1))
    civ = first.opening.civilizations[0]
    opening = replace(first.opening, civilizations=(replace(civ,
        governance=c.GovernanceState(0, .5, float(balance), balance)),))
    item = run(opening, first.frame, first.policy)
    gc.validate_capture(item)
    receipt = inspect((item,), cap=1)
    for renderer in (gs.sequence_json, gs.render_report):
        with pytest.raises(ValueError, match="digit"):
            renderer(receipt)
    driver = load()
    monkeypatch.setattr(driver, "capture_fixture", lambda **kwargs: (item,))
    with pytest.raises(SystemExit) as error:
        driver.main([*ENABLED, "--json"])
    assert error.value.code == 2 and not capsys.readouterr().out
    assert sys.get_int_max_str_digits() == digits


@pytest.mark.parametrize("fail_one", [False, True])
def test_concurrent_independent_inspections_equal_serial_and_preserve_globals(monkeypatch, fail_one):
    items = fixture()
    other_identity = replace(IDENTITY, label="another caller")
    other = tuple(replace(item, source_identity=other_identity,
        measurement=replace(item.measurement, source_identity=other_identity)) for item in items)
    serial = [inspect(items), inspect(other)]
    before = (list(sys.argv), dict(sys.modules), random.getstate(), h.run_kernel_frame,
              tuple(h.carry_to_json(item.opening) for item in items + other))
    barrier = Barrier(2, timeout=10)
    original = gc.validate_capture
    def interleaved(item):
        if item.frame.source_turn == 0:
            barrier.wait()
            if fail_one and item.source_identity == IDENTITY:
                raise ValueError("one caller failure")
        original(item)
    monkeypatch.setattr(gc, "validate_capture", interleaved)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(inspect, group) for group in (items, other)]
        if fail_one:
            with pytest.raises(ValueError, match="one caller"):
                futures[0].result(timeout=15)
        else:
            assert futures[0].result(timeout=15) == serial[0]
        assert futures[1].result(timeout=15) == serial[1]
    assert before == (list(sys.argv), dict(sys.modules), random.getstate(), h.run_kernel_frame,
                      tuple(h.carry_to_json(item.opening) for item in items + other))


def process(args=(), seed="0", code=None):
    env = dict(os.environ, PYTHONHASHSEED=seed, PYTHONPATH=str(ROOT / "src"))
    command = [sys.executable, "-B", "-c", code] if code else [sys.executable, "-B", str(SCRIPT), *args]
    return subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True, timeout=30)


@pytest.mark.parametrize("args", [[], [*ENABLED, "--json"], ENABLED])
def test_fresh_seed_0_42_101_outputs_match(args):
    results = [process(args, seed) for seed in ("0", "42", "101")]
    assert all(result.returncode == 0 and not result.stderr for result in results), [r.stderr for r in results]
    assert len({result.stdout for result in results}) == 1


def test_source_import_surface_exact_and_production_has_no_consumers():
    source = ROOT / "src/chronicler/governance_sequence.py"
    imports = [node.module for node in ast.walk(ast.parse(source.read_text())) if isinstance(node, ast.ImportFrom)]
    assert imports == ["__future__", "dataclasses", None, None]
    for path in (ROOT / "src").rglob("*.py"):
        if path != source:
            assert "governance_sequence" not in path.read_text(), path
    code = '''import importlib.util, sys
from pathlib import Path
import chronicler.governance_sequence as gs
expected={"governance_sequence","governance_capture","governance_measurements","governance_kernel_harness","institutions","elite_metrics","governance_capital","ruler_ambitions"}
assert {n.removeprefix("chronicler.") for n in sys.modules if n.startswith("chronicler.")} == expected
for name in expected:
    assert Path(sys.modules["chronicler."+name].__file__).resolve() == Path("src/chronicler",name+".py").resolve()
assert not any(n in sys.modules for n in ("chronicler_agents","numpy","random"))
assert gs.inspect_sequence().status == "disabled_no_evidence"
spec=importlib.util.spec_from_file_location("off_driver","scripts/governance_sequence_report.py")
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
def fail(*args,**kwargs): raise AssertionError("off fixture import")
m.capture_fixture=fail
assert m.main(["--fixture","invalid","--origin","invalid","--max-frames","invalid"]) == 0
assert not any(n in sys.modules for n in ("explicit_sequence_capture_fixture","explicit_capture_fixture_policy"))
'''
    for seed in ("0", "42", "101"):
        result = process(seed=seed, code=code)
        assert result.returncode == 0, result.stderr


def test_fresh_concurrency_is_pure_and_seed_stable():
    code = '''import importlib.util, random, sys
from concurrent.futures import ThreadPoolExecutor
from chronicler import governance_sequence as gs, governance_measurements as gm, governance_kernel_harness as h
spec=importlib.util.spec_from_file_location("fresh_private_driver","scripts/governance_sequence_report.py")
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
identity=gm.SourceIdentity("1"*40,"2"*40,"fresh independent inspection")
items=m.capture_fixture(origin=gm.MeasurementOrigin.SYNTHETIC_FOUR_KERNEL_HARNESS,source_identity=identity)
kernel=h.run_kernel_frame
def forbidden(*args,**kwargs): raise AssertionError("inspection kernel execution")
h.run_kernel_frame=forbidden
before=(list(sys.argv),dict(sys.modules),random.getstate())
def inspect(): return gs.sequence_json(gs.inspect_sequence(enabled=True,captures=items,max_frames=2))
try:
    serial=inspect()
    with ThreadPoolExecutor(max_workers=2) as pool:
        outputs=list(pool.map(lambda _: inspect(),range(2)))
    assert outputs == [serial,serial]
    assert h.run_kernel_frame is forbidden
    assert before == (list(sys.argv),dict(sys.modules),random.getstate())
    print(serial,end="")
finally:
    h.run_kernel_frame=kernel
'''
    outputs = [process(seed=seed, code=code) for seed in ("0", "42", "101")]
    assert all(result.returncode == 0 and not result.stderr for result in outputs), [r.stderr for r in outputs]
    assert len({result.stdout for result in outputs}) == 1


def test_driver_missing_required_inputs_and_no_fixture_without_opt_in():
    result = process(["--enabled"])
    assert result.returncode == 2 and not result.stdout and "requires fixture" in result.stderr
    off = process()
    invalid = process(["--origin", "invalid", "--max-frames", "bad", "--fixture", "/no/path"])
    assert (invalid.returncode, invalid.stdout, invalid.stderr) == (off.returncode, off.stdout, off.stderr)
