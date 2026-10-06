"""Read-only historical gates over existing detached unit-table fixtures."""
from dataclasses import FrozenInstanceError, replace
import hashlib
import io
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys

import pytest

from chronicler import campaign_logistics as cl
from chronicler import experiment_receipt_inspector as inspector
from chronicler import experiment_sessions as es
from chronicler import memome_experiment as mm
from test_experiment_sessions import (
    campaign_session, campaign_tick, campaign_trace, memome_trace,
    plain, reseal, canonical,
)
from test_memome_experiment import policy as memome_policy, person, proposal

ROOT = Path(__file__).resolve().parents[1]
DRIVER = ROOT / "scripts/experiment_receipts.py"
CLI = runpy.run_path(str(DRIVER))


def saved(directory, kernel="m60a"):
    session = campaign_trace()[0] if kernel == "m60a" else memome_trace()[0]
    path = directory / f"{kernel}.json"
    policy = es.documented_transport_policy()
    es.commit_session(path, session, transport=policy, expected_generation=None, expected_digest=None)
    return path, session, policy


def inspect(path, policy, **selection):
    return inspector.inspect_receipts(path, enabled=True, transport=policy, **selection)


def forbidden(*args, **kwargs):
    raise AssertionError("forbidden IO, kernel execution or write")


@pytest.mark.parametrize("turn", [1, 4, 7])
def test_exact_campaign_historical_receipt_and_digest_chain_equal_saved_kernel(tmp_path, turn):
    path, session, policy = saved(tmp_path)
    inspection = inspect(path, policy, turn=turn)
    document = inspector.inspection_document(inspection)
    actual = session.session.cursor.receipts[turn - 1]
    selected = document["turns"][0]
    assert selected["turn"] == turn and selected["available"] is True
    assert selected["campaign"]["receipt"] == plain(actual)
    assert "memome" not in selected
    assert selected["campaign"]["receipt_digest"] == session.session.cursor.receipt_digests[turn - 1]
    assert selected["campaign"]["receipt_digest"] == hashlib.sha256(cl.canonical_bytes(actual)).hexdigest()
    assert document["campaign_initial_state_digest"] == session.session.cursor.initial_state_digest
    assert document["file_digest"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert document["session_digest"] == es.load_session(path, transport=policy).envelope.session_digest
    text = inspector.inspection_text(inspection)
    for member in actual.members:
        derived = next(item for item in selected["campaign"]["derived_member_changes"]
                       if item["agent_id"] == member.agent_id)
        assert derived["morale_delta"] == member.morale_after - member.morale_before
        assert ",".join(member.reasons) in text
    assert actual.state_before_digest in text and actual.state_after_digest in text
    with pytest.raises(FrozenInstanceError):
        inspection.generation = 999


@pytest.mark.parametrize("turn", [1, 3])
def test_exact_memome_receipts_preserve_proposal_draw_threshold_and_weights(tmp_path, turn):
    path, session, policy = saved(tmp_path, "m68a")
    inspection = inspect(path, policy, turn=turn)
    document = inspector.inspection_document(inspection)
    tick = session.ledger.history[turn - 1]
    selected = document["turns"][0]
    assert selected["memome"]["receipts"] == plain(tick.receipts)
    assert selected["memome"]["batch"] == plain(tick.batch)
    assert selected["memome"]["participants_after"] == plain(tick.participants)
    assert "campaign" not in selected and "campaign_initial_state_digest" not in document
    assert "unavailable" in selected["memome"]["individual_electorate_votes"]
    assert "unavailable" in selected["memome"]["receipt_digest_chain"]
    text = inspector.inspection_text(inspection)
    for receipt in tick.receipts:
        assert f"{receipt.candidate_weight}\t{receipt.electorate_weight}\t{receipt.threshold}\t{receipt.reason}" in text


@pytest.mark.parametrize("kernel", ["m60a", "m68a"])
def test_required_interval_is_inclusive_ordered_and_missing_turn_never_latest_fallback(tmp_path, kernel):
    path, session, policy = saved(tmp_path, kernel)
    report = inspector.inspection_document(inspect(path, policy, start_turn=0, end_turn=3, max_turns=4))
    assert [entry["turn"] for entry in report["turns"]] == [0, 1, 2, 3]
    assert report["turns"][0] == {"turn": 0, "available": False,
                                  "reason": "unavailable: no committed receipt at this turn"}
    future = inspector.inspection_document(inspect(path, policy, turn=100))
    assert future["turns"] == [{"turn": 100, "available": False,
                                "reason": "unavailable: no committed receipt at this turn"}]
    assert future["latest_turn"] == es.session_turn(session)


@pytest.mark.parametrize("selection", [
    {}, {"turn": -1}, {"turn": True}, {"turn": 1.0}, {"turn": "1"},
    {"turn": 1, "start_turn": 1}, {"turn": 1, "max_turns": 1},
    {"start_turn": 1, "end_turn": 2}, {"start_turn": 1, "max_turns": 2},
    {"end_turn": 2, "max_turns": 2},
    {"start_turn": 3, "end_turn": 2, "max_turns": 2},
    {"start_turn": False, "end_turn": 2, "max_turns": 3},
    {"start_turn": 1, "end_turn": 2.0, "max_turns": 2},
    {"start_turn": 1, "end_turn": 2, "max_turns": True},
    {"start_turn": 1, "end_turn": 2, "max_turns": 0},
    {"start_turn": 1, "end_turn": 2, "max_turns": 1},
    {"start_turn": 1, "end_turn": 2, "max_turns": es.MAX_TRANSPORT_HISTORY + 1},
])
def test_invalid_selection_refused_before_session_read(monkeypatch, selection):
    monkeypatch.setattr(es, "load_session", forbidden)
    with pytest.raises(es.SessionError):
        inspect(Path("not-opened"), es.documented_transport_policy(), **selection)


def test_overwide_requested_turn_refused_before_read(monkeypatch):
    monkeypatch.setattr(es, "load_session", forbidden)
    with pytest.raises(es.TransportDomainError):
        inspect(Path("not-opened"), replace(es.documented_transport_policy(), max_int_bits=8), turn=256)


def test_missing_exact_transport_and_invalid_policy_refused_before_read(monkeypatch):
    monkeypatch.setattr(es, "load_session", forbidden)
    for value in (None, {}, replace(es.documented_transport_policy(), max_bytes=True)):
        with pytest.raises(es.SessionError):
            inspect(Path("not-opened"), value, turn=1)


def test_disabled_library_and_cli_with_supplied_paths_open_and_execute_nothing(monkeypatch, capsys):
    monkeypatch.setattr(Path, "open", forbidden)
    monkeypatch.setattr(es, "load_session", forbidden)
    monkeypatch.setattr(cl, "admit", forbidden)
    monkeypatch.setattr(cl, "advance", forbidden)
    monkeypatch.setattr(mm, "advance", forbidden)
    assert inspector.inspect_receipts(object(), transport=object(), turn=object()) == inspector.disabled_receipt()
    assert CLI["main"]([]) == 0
    first = capsys.readouterr()
    assert CLI["main"](["--path", "missing", "--transport", "missing", "--format", "text"]) == 0
    second = capsys.readouterr()
    assert first.out == second.out and not first.err and not second.err
    assert json.loads(first.out) == inspector.disabled_receipt()
    assert CLI["main"](["--path", "missing", "--turn", "not-an-integer", "--max-turns", "invalid"]) == 0
    assert capsys.readouterr().out == first.out


@pytest.mark.parametrize("kernel", ["m60a", "m68a"])
def test_inspection_never_commits_changes_generation_bytes_or_directory(tmp_path, monkeypatch, kernel):
    path, _, policy = saved(tmp_path, kernel)
    before = path.read_bytes(), path.stat().st_mtime_ns, sorted(item.name for item in tmp_path.iterdir())
    generation = es.load_session(path, transport=policy).generation
    monkeypatch.setattr(es, "commit_session", forbidden)
    monkeypatch.setattr(es, "apply_campaign_tick", forbidden)
    monkeypatch.setattr(es, "apply_memome_batch", forbidden)
    selected = inspect(path, policy, turn=1)
    inspector.inspection_text(selected)
    inspector.inspection_json(selected)
    assert selected.generation == generation
    assert (path.read_bytes(), path.stat().st_mtime_ns, sorted(item.name for item in tmp_path.iterdir())) == before


@pytest.mark.parametrize("kernel", ["m60a", "m68a"])
def test_resealed_tampered_receipts_still_refused_by_public_reconstruction(tmp_path, kernel):
    path, _, policy = saved(tmp_path, kernel)
    loaded = es.load_session(path, transport=policy)
    latest = json.loads(loaded.envelope.latest)
    if kernel == "m60a":
        receipt = latest["cursor"]["receipts"][0]
        receipt["members"][0]["morale_after"] += 1
        latest["cursor"]["receipt_digests"][0] = hashlib.sha256(cl.canonical_bytes(receipt)).hexdigest()
    else:
        checkpoint = json.loads(latest["checkpoint"])
        checkpoint["ledger"]["history"][0]["receipts"][0]["threshold"] += 1
        latest["checkpoint"] = canonical(checkpoint) + "\n"
    altered = reseal(loaded.envelope, latest=canonical(latest))
    path.write_bytes(es.encode_envelope_text(altered, policy))
    with pytest.raises(ValueError):
        inspect(path, policy, turn=1)


def test_malformed_and_over_byte_bound_saved_sessions_fail(tmp_path):
    path = tmp_path / "bad.json"
    path.write_bytes(b"{")
    with pytest.raises(es.SessionError):
        inspect(path, es.documented_transport_policy(), turn=1)
    path.write_bytes(b" " * 101)
    with pytest.raises(es.TransportDomainError):
        inspect(path, replace(es.documented_transport_policy(), max_bytes=100), turn=1)


def test_large_memome_weights_exact_in_json_and_text_without_float_or_digit_setting(tmp_path, monkeypatch):
    value = 2 ** 120
    people = (person("a", prestige=1), person("b", 1, prestige=value))
    session = es.create_memome_session(policy=memome_policy(), genesis_turn=0, participants=people)
    session = es.apply_memome_batch(session, mm.Batch(1, (proposal(),))).session
    policy = replace(es.documented_transport_policy(), max_int_bits=121)
    path = tmp_path / "large.json"
    es.commit_session(path, session, transport=policy, expected_generation=None, expected_digest=None)
    monkeypatch.setattr(sys, "set_int_max_str_digits", forbidden)
    selected = inspect(path, policy, turn=1)
    receipt = inspector.inspection_document(selected)["turns"][0]["memome"]["receipts"][0]
    assert receipt["candidate_weight"] == value and type(receipt["candidate_weight"]) is int
    assert receipt["electorate_weight"] == value + 1
    assert str(value) in inspector.inspection_json(selected)
    assert f"{value}\t{value + 1}" in inspector.inspection_text(selected)


@pytest.mark.parametrize("mode", ["deserted", "stall"])
def test_campaign_desertion_and_ration_stall_explain_recorded_reasons_only(tmp_path, mode):
    base = campaign_session()
    admission = base.admission
    soldiers = tuple(replace(soldier, morale=0) if mode == "deserted" else replace(soldier, rations=0)
                     for soldier in admission.soldiers)
    session = es.create_campaign_session(policy=base.policy, topology=base.topology,
                                         campaign_id=admission.campaign_id, turn=admission.turn,
                                         staging=admission.staging, target=admission.target,
                                         soldiers=soldiers, stocks=admission.stocks)
    tick = replace(campaign_tick(session, 1),
                   draws=tuple(cl.Draw(s.agent_id, 0 if mode == "deserted" else 9999) for s in soldiers))
    session = es.apply_campaign_tick(session, tick).session
    path = tmp_path / f"{mode}.json"
    policy = es.documented_transport_policy()
    es.commit_session(path, session, transport=policy, expected_generation=None, expected_digest=None)
    row = inspector.inspection_document(inspect(path, policy, turn=1))["turns"][0]["campaign"]
    if mode == "deserted":
        assert all(member["deserted"] and "deserted" in member["reasons"] for member in row["receipt"]["members"])
        assert sum(change["deserted_rations"] for change in row["derived_member_changes"]) == session.session.state.deserted_food
    else:
        assert all("ration_shortfall" in member["reasons"] and "logistics_stall" in member["reasons"]
                   and member["consumed"] == 0 for member in row["receipt"]["members"])


def test_empty_memome_batch_is_available_not_missing_and_text_cells_are_escaped(tmp_path):
    session = es.create_memome_session(policy=memome_policy(), genesis_turn=0,
                                       participants=(person("a\t\n"), person("b", 1)))
    batch = mm.Batch(1, (proposal("p\t\n", "a\t\n"),))
    session = es.apply_memome_batch(session, batch).session
    session = es.apply_memome_batch(session, mm.Batch(2, ())).session
    path = tmp_path / "empty.json"
    policy = es.documented_transport_policy()
    es.commit_session(path, session, transport=policy, expected_generation=None, expected_digest=None)
    selected = inspect(path, policy, start_turn=1, end_turn=2, max_turns=2)
    document = inspector.inspection_document(selected)
    assert document["turns"][1]["available"] is True
    assert document["turns"][1]["memome"]["receipts"] == []
    text = inspector.inspection_text(selected)
    assert "p\\t\\n" in text and "a\\t\\n" in text
    assert "available: committed batch contains no proposals" in text


def test_cli_strict_transport_errors_and_missing_inputs_are_json_exit3(tmp_path, capsys):
    transport = tmp_path / "transport.json"
    transport.write_text('{"version":1,"version":2}', encoding="utf-8")
    assert CLI["main"](["--enable", "--path", "missing", "--transport", str(transport), "--turn", "1"]) == 3
    result = capsys.readouterr()
    assert not result.out and json.loads(result.err)["error"] == "TransportDomainError"
    assert CLI["main"](["--enable"]) == 3
    assert json.loads(capsys.readouterr().err)["error"] == "SessionError"


def test_policy_actual_handle_read_is_bounded_before_decode_without_stat(monkeypatch, tmp_path):
    import builtins
    reads = []
    original = builtins.open
    (tmp_path / "misleading-size").write_bytes(b" " * 4097)
    monkeypatch.chdir(tmp_path)
    class Tracked:
        def __init__(self, descriptor, *args, **kwargs):
            self.handle = original(descriptor, *args, **kwargs)
        def __enter__(self): return self
        def __exit__(self, *args): self.handle.close()
        def fileno(self): return self.handle.fileno()
        @property
        def closed(self): return self.handle.closed
        def read(self, size=-1):
            reads.append(size)
            return self.handle.read(size)
    stream = None
    def tracked(descriptor, *args, **kwargs):
        nonlocal stream
        stream = Tracked(descriptor, *args, **kwargs)
        return stream
    monkeypatch.setattr(builtins, "open", tracked)
    monkeypatch.setattr(Path, "stat", forbidden)
    monkeypatch.setattr(es, "transport_policy_from_text", forbidden)
    with pytest.raises(es.TransportDomainError):
        CLI["_transport"](Path("misleading-size"))
    assert reads == [4097] and stream.closed


@pytest.mark.parametrize("kernel,turn", [("m60a", 1), ("m60a", 7), ("m68a", 1), ("m68a", 3)])
def test_earliest_and_latest_selection_still_validates_entire_saved_history(tmp_path, monkeypatch, kernel, turn):
    path, session, policy = saved(tmp_path, kernel)
    observed = []
    if kernel == "m60a":
        original = cl.advance
        def replay(*args, **kwargs):
            observed.append(kwargs["tick"].turn)
            return original(*args, **kwargs)
        monkeypatch.setattr(cl, "advance", replay)
        expected = [receipt.turn for receipt in session.session.cursor.receipts]
    else:
        original = mm.restore_checkpoint
        def replay(text):
            observed.extend(tick["batch"]["turn"] for tick in json.loads(text)["ledger"]["history"])
            return original(text)
        monkeypatch.setattr(mm, "restore_checkpoint", replay)
        expected = [tick.batch.turn for tick in session.ledger.history]
    result = inspect(path, policy, turn=turn)
    assert observed == expected
    assert [entry.turn for entry in result.turns] == [turn]


@pytest.mark.parametrize("kernel", ["m60a", "m68a"])
def test_fresh_process_json_text_and_default_are_hash_seed_deterministic(tmp_path, kernel):
    path, _, policy = saved(tmp_path, kernel)
    transport = tmp_path / "transport.json"
    transport.write_text(json.dumps(policy.as_payload()), encoding="utf-8")
    results = []
    for seed in ("0", "42"):
        env = dict(os.environ, PYTHONHASHSEED=seed, PYTHONDONTWRITEBYTECODE="1")
        outputs = []
        for format_name in ("json", "text"):
            result = subprocess.run([sys.executable, str(DRIVER), "--enable", "--path", str(path),
                                     "--transport", str(transport), "--start-turn", "0", "--end-turn", "3",
                                     "--max-turns", "4", "--format", format_name], env=env,
                                    capture_output=True, text=True, timeout=30)
            assert result.returncode == 0, result.stderr
            outputs.append(result.stdout)
        disabled = subprocess.run([sys.executable, str(DRIVER)], env=env,
                                  capture_output=True, text=True, timeout=30)
        assert disabled.returncode == 0 and not disabled.stderr
        results.append([*outputs, disabled.stdout])
    assert results[0] == results[1]


def test_fresh_imports_only_existing_session_and_detached_kernel_modules():
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    result = subprocess.run([sys.executable, "-c",
                             "import sys,json; import chronicler.experiment_receipt_inspector; "
                             "print(json.dumps(sorted(n for n in sys.modules if n.startswith('chronicler.'))))"],
                            env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == ["chronicler.campaign_logistics", "chronicler.experiment_receipt_inspector",
                                        "chronicler.experiment_sessions", "chronicler.memome_experiment"]
