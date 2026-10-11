"""Complete recorded-input controls using accepted detached unit tables only."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError, replace
import base64
import builtins
import hashlib
import json
import os
from pathlib import Path
import random
import runpy
import subprocess
import sys

import pytest

from chronicler import campaign_logistics as cl
from chronicler import experiment_sessions as es
from chronicler import memome_experiment as mm
from chronicler import session_comparison as comparison
from chronicler import session_operations as operations
from test_experiment_sessions import (
    campaign_session, campaign_trace, campaign_tick, canonical, memome_batches,
    memome_session, memome_trace, plain, reseal,
)
from test_memome_experiment import person, policy as memome_policy, proposal
from test_session_read_bounds import TrackedHandle, exact_limit_file

ROOT = Path(__file__).resolve().parents[1]
DRIVER = ROOT / "scripts/compare_experiment_sessions.py"
CLI = runpy.run_path(str(DRIVER))


def forbidden(*args, **kwargs):
    raise AssertionError("forbidden reader/kernel/fixture/writer/lock/operation work")


def saved(directory, name, session, transport=None):
    path = directory / name
    policy = transport or es.documented_transport_policy()
    result = es.commit_session(path, session, transport=policy,
                               expected_generation=None, expected_digest=None)
    return path, result


def check(left, right, transport=None):
    return comparison.compare_sessions(left, right, enabled=True,
        transport=transport or es.documented_transport_policy())


def inventory(directory):
    return {p.name: (p.read_bytes(), p.stat().st_mtime_ns)
            for p in directory.iterdir() if p.is_file()}


def conflict_campaigns():
    ready = campaign_trace(range(1, 2))[0]
    march = campaign_tick(ready, 2)
    hold = replace(march, orders=(cl.Order("hold-2", 2, "hold"),))
    return (es.apply_campaign_tick(ready, march).session,
            es.apply_campaign_tick(ready, hold).session)


@pytest.mark.parametrize("swapped", [False, True])
def test_campaign_two_vs_four_full_replay_prefix_and_inverse(tmp_path, monkeypatch, swapped):
    two, four = campaign_trace(range(1, 3))[0], campaign_trace(range(1, 5))[0]
    left, _ = saved(tmp_path, "two.json", two)
    right, _ = saved(tmp_path, "four.json", four)
    before = inventory(tmp_path)
    original = es.load_session
    loads, advances = [], []
    public_advance = cl.advance
    def loaded(path, **kwargs):
        value = original(path, **kwargs)
        loads.append((path, value.session))
        return value
    def advanced(*args, **kwargs):
        advances.append(kwargs["tick"].turn)
        return public_advance(*args, **kwargs)
    monkeypatch.setattr(es, "load_session", loaded)
    monkeypatch.setattr(cl, "advance", advanced)
    if swapped:
        left, right = right, left
    report = check(left, right)
    assert report.relationship == ("right_history_prefix" if swapped else "left_history_prefix")
    assert report.shared_committed_turn_count == 2 and report.last_shared_committed_turn == 2
    assert report.first_conflicting_turn is None
    assert (report.left.latest_turn, report.right.latest_turn) == ((4, 2) if swapped else (2, 4))
    assert [path for path, _ in loads] == [left, right]
    assert loads[0][1] == (four if swapped else two) and loads[1][1] == (two if swapped else four)
    assert advances == ([1, 2, 3, 4, 1, 2] if swapped else [1, 2, 1, 2, 3, 4])
    assert inventory(tmp_path) == before


def test_march_hold_conflict_retains_complete_tick_and_stops_at_first(tmp_path):
    march, hold = conflict_campaigns()
    left, _ = saved(tmp_path, "march.json", march)
    right, _ = saved(tmp_path, "hold.json", hold)
    report = check(left, right)
    assert report.relationship == "conflicting_history"
    assert (report.shared_committed_turn_count, report.last_shared_committed_turn,
            report.first_conflicting_turn) == (1, 1, 2)
    document = comparison.comparison_document(report)
    assert document["left_conflicting_submission"] == plain(march.history[1])
    assert document["right_conflicting_submission"] == plain(hold.history[1])
    assert document["left_conflicting_submission"]["orders"][0]["kind"] == "march"
    assert document["right_conflicting_submission"]["orders"][0]["kind"] == "hold"
    assert document["left_conflicting_submission"]["draws"] == [
        {"agent_id": 101, "value": 9999}, {"agent_id": 202, "value": 9999}]
    # Later equal-looking order records cannot hide the earliest conflict.
    suffix = replace(campaign_tick(march, 3), orders=())
    march = es.apply_campaign_tick(march, suffix).session
    hold = es.apply_campaign_tick(hold, suffix).session
    newer_left, _ = saved(tmp_path, "march-three.json", march)
    newer_right, _ = saved(tmp_path, "hold-three.json", hold)
    assert check(newer_left, newer_right).first_conflicting_turn == 2


def test_identical_history_resaved_at_new_generation_is_same_recorded_experiment(tmp_path):
    session = campaign_trace(range(1, 3))[0]
    left, first = saved(tmp_path, "one.json", session)
    right, second = saved(tmp_path, "two.json", session)
    later = es.commit_session(right, session, transport=es.documented_transport_policy(),
        expected_generation=second.generation, expected_digest=second.digest)
    report = check(left, right)
    assert report.relationship == "same_recorded_experiment"
    assert report.shared_committed_turn_count == 2
    assert report.generation_equal is False and report.file_digest_equal is False
    assert (report.left.generation, report.right.generation) == (first.generation, later.generation)
    assert report.left.session_digest == report.right.session_digest


@pytest.mark.parametrize("kernel", ["campaign", "memome"])
def test_equal_genesis_without_committed_history_is_zero_shared_not_receipt(tmp_path, kernel):
    session = campaign_session() if kernel == "campaign" else memome_session()
    left, _ = saved(tmp_path, "left.json", session)
    right, _ = saved(tmp_path, "right.json", session)
    report = check(left, right)
    assert report.relationship == "same_recorded_experiment"
    assert report.shared_committed_turn_count == 0
    assert report.last_shared_committed_turn is report.first_conflicting_turn is None


def test_memome_existing_one_vs_three_prefix(tmp_path):
    left, _ = saved(tmp_path, "one.json", memome_session(memome_batches()[:1]))
    right, _ = saved(tmp_path, "three.json", memome_trace()[0])
    report = check(left, right)
    assert report.relationship == "left_history_prefix"
    assert (report.shared_committed_turn_count, report.last_shared_committed_turn) == (1, 1)
    assert (report.left.latest_turn, report.right.latest_turn) == (1, 3)


def test_memome_rejected_proposals_same_participants_still_conflict_then_empty_prefix(tmp_path):
    genesis = es.create_memome_session(policy=memome_policy(), genesis_turn=0,
        participants=(person("a"), person("b", 1)))
    batch_a = mm.Batch(1, (proposal("reject-a", draw=500),))
    batch_b = mm.Batch(1, (proposal("reject-b", draw=999),))
    first = es.apply_memome_batch(genesis, batch_a).session
    second = es.apply_memome_batch(genesis, batch_b).session
    assert first.ledger.participants == second.ledger.participants == genesis.ledger.participants
    assert first.ledger.history[0].receipts[0].reason == "probability_rejected"
    assert second.ledger.history[0].receipts[0].reason == "probability_rejected"
    left, _ = saved(tmp_path, "rejected-a.json", first)
    right, _ = saved(tmp_path, "rejected-b.json", second)
    report = check(left, right)
    assert report.relationship == "conflicting_history"
    assert (report.shared_committed_turn_count, report.last_shared_committed_turn,
            report.first_conflicting_turn) == (0, None, 1)
    assert report.left_conflicting_submission == first.batches[0]
    assert report.right_conflicting_submission == second.batches[0]
    empty = es.apply_memome_batch(first, mm.Batch(2, ())).session
    third, _ = saved(tmp_path, "empty.json", empty)
    assert empty.ledger.participants == first.ledger.participants
    prefix = check(left, third)
    assert prefix.relationship == "left_history_prefix" and prefix.shared_committed_turn_count == 1
    assert check(third, third).shared_committed_turn_count == 2
    # An empty batch versus rejected proposals is a full submission conflict.
    rejected_two = es.apply_memome_batch(first, mm.Batch(2, (proposal("reject-2", draw=999),))).session
    fourth, _ = saved(tmp_path, "rejected-two.json", rejected_two)
    differing = check(third, fourth)
    assert differing.first_conflicting_turn == 2
    assert comparison.comparison_document(differing)["left_conflicting_submission"] == {"turn": 2, "proposals": []}


def test_memome_public_proposal_permutations_canonicalize_without_false_conflict(tmp_path):
    batch = memome_batches()[0]
    first = memome_session([batch])
    second = memome_session([replace(batch, proposals=batch.proposals[::-1])])
    assert first == second and first.batches[0] == second.batches[0]
    left, _ = saved(tmp_path, "left.json", first)
    right, _ = saved(tmp_path, "right.json", second)
    assert check(left, right).relationship == "same_recorded_experiment"


@pytest.mark.parametrize("dimension", ["policy", "topology", "admission"])
def test_complete_campaign_recorded_genesis_not_ids_or_normalized_state(tmp_path, dimension):
    first = campaign_session()
    policy, topology, admission = first.policy, first.topology, first.admission
    if dimension == "policy":
        policy = replace(policy, hunger_stress=policy.hunger_stress + 1)
    elif dimension == "topology":
        topology = replace(topology, regions=(cl.Region(0, (1, 2)), cl.Region(1, (0, 2)), cl.Region(2, (0, 1))))
    else:
        admission = replace(admission, soldiers=admission.soldiers[::-1])
    second = es.create_campaign_session(policy=policy, topology=topology,
        campaign_id=admission.campaign_id, turn=admission.turn, staging=admission.staging,
        target=admission.target, soldiers=admission.soldiers, stocks=admission.stocks)
    assert first.policy.version == second.policy.version
    assert first.topology.version == second.topology.version
    if dimension == "admission":
        assert first.session == second.session  # exact same latest cursor; admission order retained
    left, _ = saved(tmp_path, "left.json", first)
    right, _ = saved(tmp_path, "right.json", second)
    report = check(left, right)
    assert report.relationship == "different_recorded_genesis"
    assert report.differing_genesis_dimensions == (dimension,)
    assert report.shared_committed_turn_count is report.last_shared_committed_turn is None
    assert report.first_conflicting_turn is None


@pytest.mark.parametrize("dimension", ["policy", "genesis_turn", "genesis"])
def test_complete_memome_genesis_dimensions(tmp_path, dimension):
    first = memome_session()
    policy, turn, people = first.policy, first.genesis_turn, first.genesis
    if dimension == "policy":
        policy = replace(policy, draw_scale=policy.draw_scale + 1)
    elif dimension == "genesis_turn":
        turn = 1
    else:
        people = (replace(people[0], prestige=people[0].prestige + 1), *people[1:])
    second = es.create_memome_session(policy=policy, genesis_turn=turn, participants=people)
    left, _ = saved(tmp_path, "left.json", first)
    right, _ = saved(tmp_path, "right.json", second)
    report = check(left, right)
    assert report.relationship == "different_recorded_genesis"
    assert report.differing_genesis_dimensions == (dimension,)


def test_different_kernel_has_no_shared_history_or_first_conflict_claim(tmp_path):
    left, _ = saved(tmp_path, "campaign.json", campaign_trace(range(1, 3))[0])
    right, _ = saved(tmp_path, "memome.json", memome_trace()[0])
    report = check(left, right)
    assert report.relationship == "different_kernel"
    assert report.differing_genesis_dimensions == ()
    assert report.shared_committed_turn_count is report.last_shared_committed_turn is report.first_conflicting_turn is None


@pytest.mark.parametrize("side", ["left", "right"])
@pytest.mark.parametrize("kind", ["history", "receipt", "digest"])
def test_corrupt_side_public_replay_refuses_entire_comparison(tmp_path, side, kind):
    session = campaign_trace(range(1, 5))[0]
    left, _ = saved(tmp_path, "left.json", session)
    right, _ = saved(tmp_path, "right.json", session)
    target = left if side == "left" else right
    transport = es.documented_transport_policy()
    envelope = es.load_session(target, transport=transport).envelope
    if kind == "history":
        history = json.loads(envelope.history)
        history[-1]["credits"][0]["rations"] += 1
        envelope = reseal(envelope, history=canonical(history))
    elif kind == "receipt":
        latest = json.loads(envelope.latest)
        latest["cursor"]["receipts"][-1]["members"][0]["morale_after"] += 1
        envelope = reseal(envelope, latest=canonical(latest))
    else:
        envelope = replace(envelope, session_digest="0" * 64)
    target.write_bytes(es.encode_envelope_text(envelope, transport))
    es.decode_envelope_text(target.read_bytes(), transport)
    before = inventory(tmp_path)
    with pytest.raises(es.IntegrityError):
        check(left, right)
    assert inventory(tmp_path) == before


def test_mismatched_policy_and_scalar_alias_refuse_before_comparison(tmp_path):
    left, _ = saved(tmp_path, "left.json", campaign_session())
    policy = replace(es.documented_transport_policy(), max_history=20)
    right, _ = saved(tmp_path, "right.json", campaign_session(), policy)
    with pytest.raises(es.ContractError, match="transport policy differs"):
        check(left, right)
    right.write_bytes(left.read_bytes())
    document = json.loads(right.read_bytes())
    document["generation"] = True
    right.write_text(json.dumps(document))
    with pytest.raises(es.SessionError, match="exact integer"):
        check(left, right)


@pytest.mark.parametrize("enabled", [None, 0, 1, "false"])
def test_exact_enable_type_is_required_before_poison_inputs(enabled):
    with pytest.raises(es.SessionError, match="exact boolean"):
        comparison.compare_sessions(enabled=enabled)


@pytest.mark.parametrize("value", [None, {}, replace(es.documented_transport_policy(), max_bytes=True)])
def test_explicit_exact_transport_validates_before_load(monkeypatch, value):
    monkeypatch.setattr(es, "load_session", forbidden)
    with pytest.raises(es.SessionError):
        comparison.compare_sessions("left", "right", enabled=True, transport=value)


def test_immutable_report_fresh_documents_observed_identity_and_literal_paths(tmp_path, monkeypatch):
    first, second = conflict_campaigns()
    left, _ = saved(tmp_path, "left.json", first)
    right, _ = saved(tmp_path, "right.json", second)
    literal_left = str(tmp_path) + "/./left.json"
    report = check(literal_left, right)
    assert report.left.path == literal_left and report.right.path == str(right)
    with pytest.raises(FrozenInstanceError):
        report.relationship = "same_recorded_experiment"
    with pytest.raises(FrozenInstanceError):
        report.left.generation = 99
    document = comparison.comparison_document(report)
    document["left"]["generation"] = 99
    document["left_conflicting_submission"]["orders"].clear()
    fresh = comparison.comparison_document(report)
    assert fresh["left"]["generation"] == 1 and fresh["left_conflicting_submission"]["orders"]
    for path, observation in ((left, report.left), (right, report.right)):
        loaded = es.load_session(path, transport=es.documented_transport_policy())
        assert observation.file_digest == hashlib.sha256(path.read_bytes()).hexdigest() == loaded.digest
        for name in ("kernel", "kernel_contract", "session_digest", "genesis_digest",
                     "history_digest", "latest_digest", "source_head", "source_tree"):
            assert getattr(observation, name) == getattr(loaded.envelope, name)
    before = inventory(tmp_path)
    for name in ("commit_session", "_exclusive_lock", "_replace_durably"):
        monkeypatch.setattr(es, name, forbidden)
    monkeypatch.setattr(operations, "apply_operation", forbidden)
    monkeypatch.setattr(operations, "reconcile_operation", forbidden)
    assert check(left, right).relationship == "conflicting_history"
    assert inventory(tmp_path) == before
    assert "chronological file lineage" in comparison.comparison_text(report)


def test_same_path_two_observations_survive_replacement_between_public_loads(tmp_path, monkeypatch):
    short, long = campaign_trace(range(1, 3))[0], campaign_trace(range(1, 5))[0]
    path, original_commit = saved(tmp_path, "same.json", short)
    replacement, newer_commit = saved(tmp_path, "replacement.json", long)
    newer = replacement.read_bytes()
    old = path.read_bytes()
    original_load = es.load_session
    loaded_versions = []
    def observed(target, **kwargs):
        loaded = original_load(target, **kwargs)
        loaded_versions.append(loaded)
        if len(loaded_versions) == 1:
            os.replace(replacement, path)
        return loaded
    monkeypatch.setattr(es, "load_session", observed)
    report = check(path, path)
    assert len(loaded_versions) == 2
    assert report.relationship == "left_history_prefix" and report.shared_committed_turn_count == 2
    assert report.left.path == report.right.path == str(path)
    assert report.left.file_digest == hashlib.sha256(old).hexdigest() == original_commit.digest
    assert report.right.file_digest == hashlib.sha256(newer).hexdigest() == newer_commit.digest
    assert (report.left.latest_turn, report.right.latest_turn) == (2, 4)
    assert path.read_bytes() == newer


def test_public_loader_growth_refusal_and_symlink_descriptor_semantics_reach_comparison(tmp_path, monkeypatch):
    transport, raw, _ = exact_limit_file(memome_session())
    left, right = tmp_path / "left.json", tmp_path / "right.json"
    left.write_bytes(raw)
    right.write_bytes(raw)
    link = tmp_path / "linked.json"
    link.symlink_to(left)
    assert check(link, right, transport).relationship == "same_recorded_experiment"
    original_open = builtins.open
    requests, handles = [], []
    def grow():
        with left.open("ab") as writer:
            writer.write(b"x")
    def opened(descriptor, mode="r", *args, **kwargs):
        handle = original_open(descriptor, mode, *args, **kwargs)
        if type(descriptor) is int and mode == "rb":
            handles.append(handle)
            return TrackedHandle(handle, requests, grow)
        return handle
    monkeypatch.setattr(builtins, "open", opened)
    monkeypatch.setattr(es, "decode_envelope_text", forbidden)
    with pytest.raises(es.TransportDomainError):
        check(left, right, transport)
    assert [size for _, size in requests] == [transport.max_bytes + 1]
    assert all(handle.closed for handle in handles)


@pytest.mark.parametrize("arguments", [[], ["--left"], ["--format", "bad"], ["--unknown"], ["--enable=false"]])
def test_off_poison_does_not_inspect_inputs_or_parse_optional_syntax(monkeypatch, capsys, arguments):
    class Poison:
        __bool__ = __str__ = __repr__ = __fspath__ = forbidden
    before_rng = random.getstate()
    monkeypatch.setattr(es, "load_session", forbidden)
    monkeypatch.setattr(es, "transport_policy_from_payload", forbidden)
    monkeypatch.setattr(es, "read_regular_file_bytes", forbidden)
    monkeypatch.setattr(cl, "admit", forbidden)
    monkeypatch.setattr(cl, "advance", forbidden)
    monkeypatch.setattr(mm, "advance", forbidden)
    monkeypatch.setattr(CLI["InputParser"], "parse_args", forbidden)
    poison = Poison()
    report = comparison.compare_sessions(poison, poison, transport=poison)
    assert report == comparison.SessionComparison(False)
    with pytest.raises(FrozenInstanceError):
        report.enabled = True
    assert CLI["main"](arguments) == 0
    output = capsys.readouterr()
    assert json.loads(output.out) == comparison.comparison_document(report) and not output.err
    assert random.getstate() == before_rng


@pytest.mark.parametrize("arguments", [["--enable"], ["--enable", "--left"],
    ["--enable", "--unknown"], ["--enable", "--format", "bad"]])
def test_enabled_syntax_and_missing_input_json_exit3_before_reader(monkeypatch, capsys, arguments):
    monkeypatch.setattr(es, "read_regular_file_bytes", forbidden)
    assert CLI["main"](arguments) == 3
    output = capsys.readouterr()
    assert not output.out and json.loads(output.err)["error"] == "SessionError"


def test_help_before_missing_optional_value(monkeypatch, capsys):
    monkeypatch.setattr(es, "read_regular_file_bytes", forbidden)
    with pytest.raises(SystemExit) as exc:
        CLI["main"](["--enable", "--left", "--help"])
    assert exc.value.code == 0 and "usage:" in capsys.readouterr().out


def test_fresh_import_has_no_input_kernel_rng_or_fixture_work():
    probe = r'''
import builtins, io, importlib, importlib.util, random, sys
from contextlib import redirect_stdout
from pathlib import Path
from chronicler import experiment_sessions as es
from chronicler import campaign_logistics as cl
from chronicler import memome_experiment as mm
def forbidden(*args, **kwargs):
    raise AssertionError("forbidden work")
before = random.getstate()
builtins.open = Path.open = forbidden
es.load_session = es.read_regular_file_bytes = es.decode_envelope = es.commit_session = forbidden
cl.admit = cl.advance = mm.advance = forbidden
sys.stderr.write("boundary-start\n")
module = importlib.import_module("chronicler.session_comparison")
spec = importlib.util.spec_from_file_location("session_compare_cli", "scripts/compare_experiment_sessions.py")
driver = importlib.util.module_from_spec(spec)
spec.loader.exec_module(driver)
output = io.StringIO()
with redirect_stdout(output):
    assert driver.main(["--left", "--format", "bad"]) == 0
assert random.getstate() == before
for name in ("chronicler.main", "chronicler.models", "chronicler.agent_bridge", "chronicler.world_gen",
             "chronicler.snapshot_campaign_sessions", "campaign_logistics_demo", "memome_demo"):
    assert name not in sys.modules, name
sys.stderr.write("boundary-end\n")
'''
    process = subprocess.run([sys.executable, "-B", "-c", probe], cwd=ROOT,
        env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"), capture_output=True, text=True, timeout=30)
    assert process.returncode == 0, process.stdout + process.stderr
    assert process.stdout == "" and process.stderr == "boundary-start\nboundary-end\n"


def test_render_extreme_integer_fails_before_positive_stdout_without_global_changes(tmp_path, monkeypatch, capsys):
    left, _ = saved(tmp_path, "left.json", campaign_session())
    right, _ = saved(tmp_path, "right.json", campaign_session())
    transport = tmp_path / "transport.json"
    transport.write_text(json.dumps(es.documented_transport_policy().as_payload()))
    before = sys.get_int_max_str_digits()
    if before == 0:
        pytest.skip("runtime integer rendering has no digit cap")
    ordinary = comparison.comparison_document
    def extreme(report):
        document = ordinary(report)
        document["left"]["generation"] = 10 ** (before + 1)
        return document
    monkeypatch.setattr(comparison, "comparison_document", extreme)
    assert CLI["main"](["--enable", "--left", str(left), "--right", str(right),
                        "--transport", str(transport)]) == 3
    output = capsys.readouterr()
    assert not output.out and json.loads(output.err)["error"] == "ValueError"
    assert sys.get_int_max_str_digits() == before


def test_actual_cli_receipts_stable_seeds_concurrency_conflict_and_nonmutation(tmp_path):
    left, _ = saved(tmp_path, "two.json", campaign_trace(range(1, 3))[0])
    right, _ = saved(tmp_path, "four.json", campaign_trace(range(1, 5))[0])
    transport = tmp_path / "transport.json"
    transport.write_text(json.dumps(es.documented_transport_policy().as_payload()))
    receipts = []
    def arguments(a=left, b=right, output_format="json"):
        return ["--enable", "--left", str(a), "--right", str(b), "--transport", str(transport), "--format", output_format]
    def invoke(label, args, seed="0"):
        command = [sys.executable, "-B", str(DRIVER), *args]
        before = inventory(tmp_path)
        process = subprocess.run(command, cwd=ROOT, env=dict(os.environ, PYTHONHASHSEED=seed),
                                 capture_output=True, timeout=30)
        after = inventory(tmp_path)
        assert after == before
        receipts.append(dict(label=label, command=command, hash_seed=seed, exit=process.returncode,
            stdout=process.stdout.decode(), stderr=process.stderr.decode(),
            post_command_files={name: dict(bytes_base64=base64.b64encode(data).decode(),
                sha256=hashlib.sha256(data).hexdigest(), mtime_ns=mtime)
                for name, (data, mtime) in after.items()}))
        return process
    seeded = [invoke("prefix-seed" + seed, arguments(), seed) for seed in ("0", "42", "101")]
    assert all(p.returncode == 0 and p.stdout == seeded[0].stdout and p.stderr == seeded[0].stderr for p in seeded)
    with ThreadPoolExecutor(max_workers=2) as pool:
        parallel = list(pool.map(lambda n: invoke("concurrent" + str(n), arguments()), range(2)))
    assert all(p.returncode == 0 and p.stdout == seeded[0].stdout and p.stderr == seeded[0].stderr for p in parallel)
    inverse = invoke("inverse-prefix", arguments(right, left))
    assert inverse.returncode == 0 and json.loads(inverse.stdout)["relationship"] == "right_history_prefix"
    text = invoke("prefix-text", arguments(output_format="text"))
    assert text.returncode == 0 and b"left_history_prefix" in text.stdout
    march, hold = conflict_campaigns()
    a, _ = saved(tmp_path, "march.json", march)
    b, _ = saved(tmp_path, "hold.json", hold)
    conflict = invoke("march-hold-conflict", arguments(a, b))
    assert conflict.returncode == 0 and json.loads(conflict.stdout)["first_conflicting_turn"] == 2
    same = invoke("same-history", arguments(left, left))
    assert same.returncode == 0 and json.loads(same.stdout)["relationship"] == "same_recorded_experiment"
    memome, _ = saved(tmp_path, "memome.json", memome_trace()[0])
    different = invoke("different-kernel", arguments(left, memome))
    assert different.returncode == 0 and json.loads(different.stdout)["relationship"] == "different_kernel"
    changed = campaign_session()
    admission = changed.admission
    reordered = es.create_campaign_session(policy=changed.policy, topology=changed.topology,
        campaign_id=admission.campaign_id, turn=admission.turn, staging=admission.staging,
        target=admission.target, soldiers=admission.soldiers[::-1], stocks=admission.stocks)
    genesis_a, _ = saved(tmp_path, "genesis-a.json", changed)
    genesis_b, _ = saved(tmp_path, "genesis-b.json", reordered)
    genesis_result = invoke("different-recorded-genesis", arguments(genesis_a, genesis_b))
    assert genesis_result.returncode == 0
    assert json.loads(genesis_result.stdout)["differing_genesis_dimensions"] == ["admission"]
    copied, commit = saved(tmp_path, "resaved.json", campaign_trace(range(1, 3))[0])
    es.commit_session(copied, campaign_trace(range(1, 3))[0], transport=es.documented_transport_policy(),
        expected_generation=commit.generation, expected_digest=commit.digest)
    resaved = invoke("same-history-different-generation", arguments(left, copied))
    resaved_report = json.loads(resaved.stdout)
    assert resaved.returncode == 0 and resaved_report["relationship"] == "same_recorded_experiment"
    assert resaved_report["generation_equal"] is False and resaved_report["file_digest_equal"] is False
    memome_one, _ = saved(tmp_path, "memome-one.json", memome_session(memome_batches()[:1]))
    memome_prefix = invoke("memome-prefix", arguments(memome_one, memome))
    assert memome_prefix.returncode == 0 and json.loads(memome_prefix.stdout)["shared_committed_turn_count"] == 1
    original = b.read_bytes()
    envelope = es.load_session(b, transport=es.documented_transport_policy()).envelope
    latest = json.loads(envelope.latest)
    latest["state"]["consumed_food"] += 1
    b.write_bytes(es.encode_envelope_text(reseal(envelope, latest=canonical(latest)), es.documented_transport_policy()))
    corrupt = invoke("resealed-corruption", arguments(a, b))
    assert corrupt.returncode == 3 and not corrupt.stdout and json.loads(corrupt.stderr)["error"] == "IntegrityError"
    b.write_bytes(original)
    for label, args in [("missing-side", arguments(a, tmp_path / "absent.json")),
        ("syntax-unknown", ["--enable", "--unknown"]), ("syntax-missing", ["--enable", "--left"])]:
        failure = invoke(label, args)
        assert failure.returncode == 3 and not failure.stdout
    for label, args in [("off-missing-optional", ["--left"]), ("off-invalid-optional", ["--format", "bad"])]:
        off = invoke(label, args)
        assert off.returncode == 0 and json.loads(off.stdout)["enabled"] is False
    help_ = invoke("help-missing-optional", ["--enable", "--left", "--help"])
    assert help_.returncode == 0 and b"usage:" in help_.stdout
    (tmp_path / "cli-evidence.json").write_text(json.dumps(receipts, indent=2))


@pytest.mark.parametrize("which", ["session", "transport"])
def test_fifo_inputs_refused_by_public_reader_in_bounded_cli_children(tmp_path, which):
    left, _ = saved(tmp_path, "left.json", campaign_session())
    right, _ = saved(tmp_path, "right.json", campaign_session())
    transport = tmp_path / "transport.json"
    transport.write_text(json.dumps(es.documented_transport_policy().as_payload()))
    target = right if which == "session" else transport
    target.unlink()
    os.mkfifo(target)
    process = subprocess.run([sys.executable, "-B", str(DRIVER), "--enable", "--left", str(left),
        "--right", str(right), "--transport", str(transport)], capture_output=True, timeout=3)
    assert process.returncode == 3 and not process.stdout
    assert "regular file" in json.loads(process.stderr)["detail"]


@pytest.mark.parametrize("kind", ["oversize", "duplicate", "unknown", "scalar_alias"])
def test_cli_public_transport_bootstrap_bounds_and_strict_parser_before_session_load(tmp_path, monkeypatch, capsys, kind):
    path = tmp_path / "transport.json"
    policy = es.documented_transport_policy().as_payload()
    if kind == "oversize":
        path.write_bytes(b"x" * 4097)
        monkeypatch.setattr(es, "transport_policy_from_text", forbidden)
    elif kind == "duplicate":
        path.write_text(json.dumps(policy)[:-1] + ',"max_bytes":1}')
    elif kind == "unknown":
        path.write_text(json.dumps(policy | {"unknown": 1}))
    else:
        path.write_text(json.dumps(policy | {"max_bytes": True}))
    monkeypatch.setattr(es, "load_session", forbidden)
    assert CLI["main"](["--enable", "--left", "unused-left", "--right", "unused-right",
                        "--transport", str(path)]) == 3
    output = capsys.readouterr()
    assert not output.out and json.loads(output.err)["error"] in ("SessionError", "TransportDomainError")
