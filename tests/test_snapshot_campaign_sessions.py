"""Bounded offline controls using the existing schema, roster and topology."""
import ast
from dataclasses import FrozenInstanceError, replace
import hashlib
import io
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys

import pyarrow as pa
import pytest

from chronicler import campaign_logistics as cl
from chronicler import experiment_sessions as es
from chronicler import snapshot_campaign_sessions as bridge
from chronicler.campaign_snapshot_adapter import CampaignSnapshotError, parse_side_inputs, plan_document
from test_campaign_snapshot_adapter import side_document, snapshot, view, write_snapshot

ROOT = Path(__file__).resolve().parents[1]
DRIVER = ROOT / "scripts/snapshot_campaign_session.py"
CLI = runpy.run_path(str(DRIVER))


def prepare(**changes):
    args = dict(agent_rows=view(), side_inputs=parse_side_inputs(side_document()),
                transport=es.documented_transport_policy())
    args.update(changes)
    return bridge.prepare_snapshot_session(**args)


def files(directory):
    source = write_snapshot(directory)
    side = directory / "side.json"
    side.write_text(json.dumps(side_document()), encoding="utf-8")
    transport = directory / "transport.json"
    transport.write_text(json.dumps(es.documented_transport_policy().as_payload()), encoding="utf-8")
    return dict(enabled=True, snapshot=source, side_inputs=side, transport=transport,
                path=directory / "session.json", max_snapshot_bytes=source.stat().st_size)


def forbidden(*args, **kwargs):
    raise AssertionError("forbidden read, kernel call or persistence")


def test_public_admission_and_full_portable_envelope_are_equal_and_immutable():
    prepared = prepare()
    p = prepared.plan
    direct = cl.admit(policy=p.policy, topology=p.topology, campaign_id=p.campaign_id,
                      turn=p.admission_turn, staging=p.staging, target=p.target,
                      soldiers=p.soldiers, stocks=p.stocks)
    assert cl.canonical_bytes(direct) == cl.canonical_bytes(prepared.session.session)
    assert prepared.session.session == p.session
    assert prepared.session.history == () and direct.cursor.receipts == ()
    assert prepared.envelope.generation == 1 and prepared.envelope.turn == 7
    assert es.decode_envelope(prepared.envelope) == prepared.session
    with pytest.raises(FrozenInstanceError):
        prepared.session = None
    assert set(prepared.envelope.as_payload()) == set(es.encode_session(
        prepared.session, transport=es.documented_transport_policy(), generation=1).as_payload())


def test_complete_session_mismatch_rejected_before_envelope_or_write(monkeypatch):
    other = prepare(side_inputs=parse_side_inputs(side_document(campaign_id="different"))).session
    monkeypatch.setattr(bridge, "create_campaign_session", lambda **kwargs: other)
    monkeypatch.setattr(bridge, "encode_session", forbidden)
    with pytest.raises(es.IntegrityError, match="complete snapshot admission"):
        prepare()


@pytest.mark.parametrize("field,value", [("side_inputs", {}), ("transport", {}),
                                          ("side_inputs", replace(parse_side_inputs(side_document()), contract="foreign")),
                                          ("transport", replace(es.documented_transport_policy(), max_bytes=True))])
def test_exact_public_input_records_and_transport_validation_before_kernel(monkeypatch, field, value):
    monkeypatch.setattr(bridge, "admit_snapshot_plan", forbidden)
    with pytest.raises((CampaignSnapshotError, es.SessionError)):
        prepare(**{field: value})


@pytest.mark.parametrize("transport", [replace(es.documented_transport_policy(), max_bytes=100),
                                        replace(es.documented_transport_policy(), max_records=1),
                                        replace(es.documented_transport_policy(), max_int_bits=2)])
def test_prepared_admission_must_fit_every_transport_domain(transport):
    with pytest.raises(es.TransportDomainError):
        prepare(transport=transport)


@pytest.mark.parametrize("bound", [None, True, False, 0, -1, 1.0, "4096", 67_108_865])
def test_snapshot_bound_requires_explicit_exact_supported_int_before_reads(monkeypatch, bound):
    monkeypatch.setattr(Path, "open", forbidden)
    with pytest.raises(CampaignSnapshotError):
        bridge.read_snapshot(Path("absent"), max_snapshot_bytes=bound)


def test_bounded_handle_read_ignores_metadata_and_rejects_before_arrow(monkeypatch, tmp_path):
    reads = []
    class Tracked:
        def __init__(self, handle):
            self.handle = handle
        def __enter__(self):
            self.handle.__enter__()
            return self
        def __exit__(self, *args):
            return self.handle.__exit__(*args)
        def fileno(self):
            return self.handle.fileno()
        @property
        def closed(self):
            return self.handle.closed
        def read(self, size=-1):
            reads.append(size)
            return self.handle.read(size)
    path = tmp_path / "misleading"
    path.write_bytes(b"x" * 11)
    stream = None
    def opened(descriptor, *args, **kwargs):
        nonlocal stream
        stream = Tracked(open(descriptor, *args, **kwargs))
        return stream
    # Restore shared filesystem APIs before pytest formats a possible failure.
    with monkeypatch.context() as monkeypatch:
        monkeypatch.setattr(es, "open", opened, raising=False)
        monkeypatch.setattr(Path, "stat", forbidden)
        monkeypatch.setattr(pa.ipc, "open_file", forbidden)
        with pytest.raises(es.TransportDomainError):
            bridge.read_snapshot(path, max_snapshot_bytes=10)
    assert reads == [11] and stream.closed


def test_exact_snapshot_limit_and_batch_survives_closed_deleted_source(tmp_path):
    path = write_snapshot(tmp_path)
    batch = bridge.read_snapshot(path, max_snapshot_bytes=path.stat().st_size)
    assert batch.equals(snapshot())
    path.unlink()
    assert prepare(agent_rows=view(batch)).plan.session == prepare().plan.session


@pytest.mark.parametrize("count", [0, 2])
def test_exactly_one_ipc_batch_required(tmp_path, count):
    path = tmp_path / "snapshot.arrow"
    with pa.OSFile(str(path), "wb") as sink:
        with pa.ipc.new_file(sink, snapshot().schema) as writer:
            for _ in range(count):
                writer.write_batch(snapshot())
    with pytest.raises(CampaignSnapshotError, match="exactly one"):
        bridge.read_snapshot(path, max_snapshot_bytes=path.stat().st_size)


def test_disabled_paths_and_no_args_open_nothing_and_call_no_kernel(monkeypatch, capsys):
    for name in ("read_snapshot", "read_bounded_bytes", "prepare_snapshot_session", "commit_session"):
        monkeypatch.setitem(CLI["run"].__globals__, name, forbidden)
    monkeypatch.setattr(Path, "open", forbidden)
    assert CLI["main"]([]) == 0
    empty = capsys.readouterr()
    assert CLI["main"](["--snapshot", "missing", "--side-inputs", "missing",
                          "--transport", "missing", "--path", "missing"]) == 0
    supplied = capsys.readouterr()
    assert empty.out == supplied.out and not empty.err and not supplied.err
    assert json.loads(empty.out) == CLI["disabled_receipt"]()


@pytest.mark.parametrize("field", ["snapshot", "side_inputs", "transport", "path", "max_snapshot_bytes"])
def test_enabled_missing_inputs_open_nothing(monkeypatch, field):
    args = dict(enabled=True, snapshot=Path("x"), side_inputs=Path("x"),
                transport=Path("x"), path=Path("x"), max_snapshot_bytes=4096)
    args[field] = None
    monkeypatch.setattr(Path, "open", forbidden)
    with pytest.raises(CampaignSnapshotError):
        CLI["run"](**args)


@pytest.mark.parametrize("malformed", [b'{"contract":1,"contract":2}', b'{"source_turn":NaN}',
                                        b'{"source_turn":1.0}', b'{"source_turn":Infinity}'])
def test_strict_side_submission_rejected_before_destination_or_lock(tmp_path, malformed):
    args = files(tmp_path)
    args["side_inputs"].write_bytes(malformed)
    with pytest.raises(es.SessionError):
        CLI["run"](**args)
    assert not args["path"].exists() and not list(tmp_path.glob(".*.lock"))


@pytest.mark.parametrize("change", [dict(source_turn=True), dict(selected_ids=[7, 99]),
                                    dict(kits={"7": True, "8": 8}), dict(civ_id=2)])
def test_side_selection_failures_preserve_existing_destination_and_create_no_lock(tmp_path, change):
    args = files(tmp_path)
    args["path"].write_bytes(b"existing unrelated destination")
    args["side_inputs"].write_text(json.dumps(side_document(**change)), encoding="utf-8")
    with pytest.raises((CampaignSnapshotError, ValueError)):
        CLI["run"](**args)
    assert args["path"].read_bytes() == b"existing unrelated destination"
    assert not list(tmp_path.glob(".*.lock"))


def test_schema_and_epoch_failures_precede_persistence(tmp_path):
    with pytest.raises(ValueError):
        prepare(agent_rows=view(turn=8))
    args = files(tmp_path)
    batch = snapshot().remove_column(0)
    with pa.OSFile(str(args["snapshot"]), "wb") as sink:
        with pa.ipc.new_file(sink, batch.schema) as writer:
            writer.write_batch(batch)
    args["max_snapshot_bytes"] = args["snapshot"].stat().st_size
    with pytest.raises(KeyError):
        CLI["run"](**args)
    assert not args["path"].exists() and not list(tmp_path.glob(".*.lock"))


@pytest.mark.parametrize("which", ["transport", "side_inputs", "snapshot"])
def test_file_bound_failures_precede_destination_creation(tmp_path, which):
    args = files(tmp_path)
    limit = 4096 if which == "transport" else es.documented_transport_policy().max_bytes
    if which == "snapshot":
        args["max_snapshot_bytes"] -= 1
    else:
        args[which].write_bytes(b" " * (limit + 1))
    with pytest.raises(es.TransportDomainError):
        CLI["run"](**args)
    assert not args["path"].exists() and not list(tmp_path.glob(".*.lock"))


def test_receipt_truth_existing_file_protection_and_portable_resume_replay(tmp_path):
    args = files(tmp_path)
    receipt = CLI["run"](**args)
    policy = es.documented_transport_policy()
    loaded = es.load_session(args["path"], transport=policy)
    assert receipt["plan"] == plan_document(prepare().plan)
    assert receipt["file_digest"] == hashlib.sha256(args["path"].read_bytes()).hexdigest()
    assert receipt["session_digest"] == loaded.envelope.session_digest
    assert receipt["plan_provenance_persisted"] is False
    assert "plan" not in json.loads(args["path"].read_bytes())
    assert loaded.session == prepare().session and loaded.turn == 7
    previous = args["path"].read_bytes(), args["path"].stat().st_mtime_ns
    with pytest.raises(es.StaleGenerationError):
        CLI["run"](**args)
    assert (args["path"].read_bytes(), args["path"].stat().st_mtime_ns) == previous
    ticks = [cl.Tick(turn, (), (), (cl.Condition(7, 0, 1000), cl.Condition(8, 0, 1000)),
                     (cl.Draw(7, 9999), cl.Draw(8, 9999)), (1,)) for turn in (8, 9)]
    uninterrupted = loaded.session
    resumed = loaded
    for tick in ticks:
        uninterrupted = es.apply_campaign_tick(uninterrupted, tick).session
        result = es.apply_campaign_tick(resumed.session, tick)
        es.commit_session(args["path"], result.session, transport=policy,
                          expected_generation=resumed.generation, expected_digest=resumed.digest)
        resumed = es.load_session(args["path"], transport=policy)
    assert resumed.session == uninterrupted
    replay = es.apply_campaign_tick(resumed.session, ticks[-1])
    assert not replay.changed and replay.replayed and replay.session == resumed.session
    assert set(p.name for p in tmp_path.iterdir()) == {
        "snapshot.arrow", "side.json", "transport.json", "session.json", ".session.json.lock"}


def test_cli_error_json_preserves_durability_uncertain_taxonomy(tmp_path, monkeypatch, capsys):
    args = files(tmp_path)
    def uncertain(*args, **kwargs):
        raise es.DurabilityUncertain("read the file back and reconcile it")
    monkeypatch.setitem(CLI["run"].__globals__, "commit_session", uncertain)
    argv = ["--enable"]
    for flag in ("snapshot", "side_inputs", "transport", "path", "max_snapshot_bytes"):
        argv.extend(["--" + flag.replace("_", "-"), str(args[flag])])
    assert CLI["main"](argv) == 3
    captured = capsys.readouterr()
    assert not captured.out
    assert json.loads(captured.err) == {
        "error": "DurabilityUncertain", "detail": "read the file back and reconcile it"}


@pytest.mark.parametrize("text,error", [
    ('{"version":"chronicler-session-transport-v1","version":"other"}', "TransportDomainError"),
    ('{"max_bytes":NaN}', "TransportDomainError"),
    ('{"max_bytes":1.0}', "TransportDomainError"),
    (json.dumps(es.documented_transport_policy().as_payload() | {"max_bytes": True}), "SessionError"),
])
def test_strict_transport_failure_is_json_exit3_before_any_destination(tmp_path, capsys, text, error):
    args = files(tmp_path)
    args["transport"].write_text(text, encoding="utf-8")
    argv = ["--enable"]
    for flag in ("snapshot", "side_inputs", "transport", "path", "max_snapshot_bytes"):
        argv.extend(["--" + flag.replace("_", "-"), str(args[flag])])
    assert CLI["main"](argv) == 3
    captured = capsys.readouterr()
    assert not captured.out and json.loads(captured.err)["error"] == error
    assert not args["path"].exists() and not list(tmp_path.glob(".*.lock"))


def test_schema_key_error_is_reported_as_json_exit3(tmp_path, capsys):
    args = files(tmp_path)
    batch = snapshot().remove_column(0)
    with pa.OSFile(str(args["snapshot"]), "wb") as sink:
        with pa.ipc.new_file(sink, batch.schema) as writer:
            writer.write_batch(batch)
    args["max_snapshot_bytes"] = args["snapshot"].stat().st_size
    argv = ["--enable"]
    for flag in ("snapshot", "side_inputs", "transport", "path", "max_snapshot_bytes"):
        argv.extend(["--" + flag.replace("_", "-"), str(args[flag])])
    assert CLI["main"](argv) == 3
    captured = capsys.readouterr()
    assert not captured.out and json.loads(captured.err)["error"] == "KeyError"
    assert not args["path"].exists() and not list(tmp_path.glob(".*.lock"))


def test_fresh_process_seed_determinism_and_unchanged_session_cli(tmp_path):
    args = files(tmp_path)
    base = [sys.executable, str(DRIVER), "--enable"]
    for flag in ("snapshot", "side_inputs", "transport", "path", "max_snapshot_bytes"):
        base.extend(["--" + flag.replace("_", "-"), str(args[flag])])
    receipts, contents = [], []
    for seed in ("1", "77"):
        environment = dict(os.environ, PYTHONHASHSEED=seed, PYTHONDONTWRITEBYTECODE="1")
        result = subprocess.run(base, env=environment, capture_output=True, text=True, timeout=30)
        assert result.returncode == 0, result.stderr
        receipts.append(result.stdout)
        contents.append(args["path"].read_bytes())
        for command in ("inspect", "verify"):
            check = subprocess.run([sys.executable, str(ROOT / "scripts/experiment_session.py"),
                                    command, "--path", str(args["path"]),
                                    "--transport", str(args["transport"])], env=environment,
                                   capture_output=True, text=True, timeout=30)
            assert check.returncode == 0, check.stderr
            assert json.loads(check.stdout)["session_digest"] == json.loads(result.stdout)["session_digest"]
        tick = tmp_path / "tick.json"
        tick.write_text(json.dumps({"turn": 8, "orders": [], "credits": [],
                                   "conditions": [{"agent_id": agent, "unmet_needs": 0,
                                                   "information_quality": 1000} for agent in (7, 8)],
                                   "draws": [{"agent_id": agent, "value": 9999} for agent in (7, 8)],
                                   "supply_sources": [1]}), encoding="utf-8")
        apply_args = [sys.executable, str(ROOT / "scripts/experiment_session.py"), "apply",
                      "--path", str(args["path"]), "--transport", str(args["transport"]),
                      "--batch", str(tick)]
        applied = subprocess.run(apply_args, env=environment, capture_output=True,
                                 text=True, timeout=30)
        assert applied.returncode == 0, applied.stderr
        assert json.loads(applied.stdout)["committed"] is True
        before_replay = args["path"].read_bytes(), args["path"].stat().st_mtime_ns
        replay = subprocess.run(apply_args, env=environment, capture_output=True,
                                text=True, timeout=30)
        assert replay.returncode == 0, replay.stderr
        assert json.loads(replay.stdout)["committed"] is False
        assert (args["path"].read_bytes(), args["path"].stat().st_mtime_ns) == before_replay
        args["path"].unlink()
    assert receipts[0] == receipts[1] and contents[0] == contents[1]


def test_exact_experimental_import_contract_and_no_other_package_consumers():
    path = ROOT / "src/chronicler/snapshot_campaign_sessions.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports = [node for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
               and node.module == "chronicler.campaign_snapshot_adapter"]
    assert len(imports) == 1
    assert {alias.name for alias in imports[0].names} == {
        "CONTRACT", "AdmissionPlan", "CampaignSnapshotError", "SideInputs", "admit_snapshot_plan"}
    assert all(alias.asname is None for alias in imports[0].names)
    adapter_consumers = {candidate.relative_to(ROOT).as_posix()
                         for candidate in (ROOT / "src").rglob("*.py")
                         if candidate.name != "campaign_snapshot_adapter.py"
                         and "campaign_snapshot_adapter" in candidate.read_text(encoding="utf-8")}
    assert adapter_consumers == {"src/chronicler/snapshot_campaign_sessions.py"}
    bridge_consumers = {candidate.relative_to(ROOT).as_posix()
                        for candidate in (ROOT / "src").rglob("*.py")
                        if candidate != path
                        and "snapshot_campaign_sessions" in candidate.read_text(encoding="utf-8")}
    assert bridge_consumers == set()
    for candidate in (ROOT / "src/chronicler/main.py", ROOT / "src/chronicler/__init__.py"):
        source = candidate.read_text(encoding="utf-8")
        assert "campaign_snapshot" not in source and "snapshot_campaign" not in source


def test_fresh_import_and_disabled_calls_do_no_input_kernel_commit_fixture_or_rng_work():
    probe = r'''
import builtins, importlib.util, io, json, random, sys
from contextlib import redirect_stdout
from pathlib import Path
import pyarrow as pa
from chronicler import campaign_logistics as kernel
from chronicler import campaign_snapshot_adapter as adapter
from chronicler import experiment_sessions as sessions

def forbidden(*args, **kwargs):
    raise AssertionError("forbidden input/kernel/commit/fixture work")

before = random.getstate()
builtins.open = forbidden
Path.open = forbidden
kernel.admit = forbidden
kernel.advance = forbidden
adapter.admit_snapshot_plan = forbidden
for name in ("create_campaign_session", "encode_session", "decode_envelope", "commit_session"):
    setattr(sessions, name, forbidden)
pa.ipc.open_file = forbidden
sys.stderr.write("snapshot-boundary-start\n")
sys.stderr.flush()

import chronicler.snapshot_campaign_sessions
spec = importlib.util.spec_from_file_location("standalone_snapshot_session_driver", "scripts/snapshot_campaign_session.py")
driver = importlib.util.module_from_spec(spec)
spec.loader.exec_module(driver)

class Poison:
    def __getattribute__(self, name):
        return forbidden()
    __bool__ = __fspath__ = __str__ = __repr__ = forbidden

poison = Poison()
assert driver.run(enabled=False, snapshot=poison, side_inputs=poison,
                  transport=poison, path=poison, max_snapshot_bytes=poison) == driver.disabled_receipt()
for arguments in ([], ["--snapshot", "unread", "--side-inputs", "unread",
                       "--transport", "unread", "--path", "unread"]):
    output = io.StringIO()
    with redirect_stdout(output):
        assert driver.main(arguments) == 0
    assert json.loads(output.getvalue()) == driver.disabled_receipt()
assert random.getstate() == before
for name in ("chronicler.main", "chronicler.models", "chronicler.simulation",
             "chronicler.agent_bridge", "chronicler.world_gen", "chronicler.economy",
             "chronicler_agents", "campaign_logistics_demo", "memome_demo"):
    assert name not in sys.modules, name
sys.stderr.write("snapshot-boundary-end\n")
'''
    result = subprocess.run([sys.executable, "-c", probe], cwd=ROOT,
                            env=dict(os.environ, PYTHONPATH=str(ROOT / "src"),
                                     PYTHONDONTWRITEBYTECODE="1"),
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout == ""
    # Allowed Arrow/OpenMP bootstrap can warn before the controlled new imports.
    # The bridge/driver import and disabled operations themselves stay silent.
    prefix, marker, boundary = result.stderr.partition("snapshot-boundary-start\n")
    assert marker and boundary == "snapshot-boundary-end\n", result.stderr
