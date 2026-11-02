"""Pure validation and pair lifecycle contracts (no native or child processes)."""
import copy
import hashlib
import json
from pathlib import Path
import queue
import struct
import threading
import zlib
from types import SimpleNamespace

import pytest

import chronicler.run_checkpoint as rc
import chronicler.what_if as wi
from chronicler.live import LiveServer, make_live_pause

IDENTITY = {"source": {"package_digest": "source", "git_sha": "sha"},
            "native": {"status": "absent", "state_layouts": {}},
            "environment": {"implementation": "CPython", "python": "3.13", "machine": "x86_64",
                            "packages": {}, "thread_env": {"PYTHONHASHSEED": "0", "OMP_NUM_THREADS": "1"}}}


def write_envelope(path, *, exact=True, identity=None):
    raw = b"owned checkpoint payload"
    body = zlib.compress(raw)
    header = {"format": rc.FORMAT, "version": rc.FORMAT_VERSION, "exact": exact,
              "turn": 2, "seed": 42, "identity": identity or copy.deepcopy(IDENTITY),
              "run_config": {"simulation_args": {"agents": "off"}, "output_args": {"simulate_only": True}},
              "sections": [{"name": "python", "offset": 0, "length": len(body), "raw_length": len(raw),
                            "sha256": hashlib.sha256(body).hexdigest()}]}
    encoded = json.dumps(header).encode()
    path.write_bytes(rc.MAGIC + struct.pack("<I", len(encoded)) + encoded + body)


@pytest.fixture
def pair(tmp_path, monkeypatch):
    monkeypatch.setattr(wi, "require_hash_seed", lambda: None)
    monkeypatch.setattr(wi, "fresh_identity", lambda: copy.deepcopy(IDENTITY))
    monkeypatch.setattr(rc, "runtime_identity", lambda: copy.deepcopy(IDENTITY))
    writes = []
    def save(path):
        writes.append(path)
        write_envelope(path)
    pairs = wi.WhatIfPairs(tmp_path, queue.Queue(), SimpleNamespace(save_private=save))
    pairs.writes = writes
    return pairs


@pytest.fixture
def world():
    return SimpleNamespace(turn=2, seed=42, civilizations=[SimpleNamespace(name="King's Realm", regions=["R"], stability=60)])


def request(**extra):
    return {"type": "what_if_prepare", "request_id": "pair_1", "civ": "King's Realm", "value": 70, "turns": 2, **extra}


@pytest.mark.parametrize("extra", [{"value": True}, {"value": "50"}, {"value": 0}, {"value": 101},
                                   {"turns": False}, {"turns": 21}, {"turns": 0}, {"civ": "missing"},
                                   {"civ": "King\nRealm"}, {"path": "/tmp/a"}, {"request_id": "../bad"}])
def test_narrow_control_rejection(world, extra):
    with pytest.raises(wi.WhatIfError):
        wi.validate_request(request(**extra), world)


def test_dead_civ_refused(world):
    world.civilizations[0].regions = []
    with pytest.raises(wi.WhatIfError, match="living"):
        wi.validate_request(request(), world)


@pytest.mark.parametrize("kind", ["state", "corrupt", "nonexact", "incompatible", "turn", "seed"])
def test_checkpoint_refusals(pair, tmp_path, kind):
    path = tmp_path / "test.ckpt"
    identity = copy.deepcopy(IDENTITY)
    if kind == "incompatible":
        identity["source"]["package_digest"] = "other"
    write_envelope(path, exact=kind != "nonexact", identity=identity)
    if kind == "state":
        path.write_text('{"turn":2}')
    elif kind == "corrupt":
        path.write_bytes(path.read_bytes()[:-1] + b"!")
    with pytest.raises((wi.WhatIfError, rc.CheckpointError)):
        wi.verified_header(path, turn=3 if kind == "turn" else 2, seed=9 if kind == "seed" else 42)


def test_changed_running_source_refused(pair, tmp_path, monkeypatch):
    path = tmp_path / "test.ckpt"
    write_envelope(path)
    current = copy.deepcopy(IDENTITY)
    current["environment"]["thread_env"]["OMP_NUM_THREADS"] = "2"
    monkeypatch.setattr(wi, "fresh_identity", lambda: current)
    with pytest.raises(wi.WhatIfError, match="compatibility"):
        wi.verified_header(path)


def test_prepare_is_durable_but_never_executes_and_duplicate_runs_only_two(pair, world, monkeypatch):
    calls = []
    def child(job, arm):
        assert json.loads((job.directory / "manifest.json").read_text())["state"] == "running"
        calls.append(arm)
        return {"bundle": {}, "identity": {}}
    monkeypatch.setattr(pair, "_child", child)
    first = pair.prepare(request(), world)
    assert first["state"] == "prepared" and calls == []
    assert pair.prepare(request(), world) == first
    assert len(pair.writes) == 1
    job = pair.jobs["pair_1"]
    assert json.loads((job.directory / "manifest.json").read_text())["semantics"] == "exact_checkpoint_pair"
    with pytest.raises(wi.WhatIfError, match="different"):
        pair.prepare(request(value=71), world)
    pair.run("pair_1")
    pair.run("pair_1")
    job.thread.join(3)
    pair.run("pair_1")
    assert calls == ["baseline", "intervention"]
    assert job.state == "complete" and not pair.busy


def test_failed_baseline_stops_remaining_arm(pair, world, monkeypatch):
    calls = []
    def child(job, arm):
        calls.append(arm)
        raise wi.WhatIfError("baseline failed")
    monkeypatch.setattr(pair, "_child", child)
    pair.prepare(request(), world)
    pair.run("pair_1")
    job = pair.jobs["pair_1"]
    job.thread.join(3)
    assert calls == ["baseline"] and job.state == "error"
    assert job.directory.is_dir()


def test_cancel_prepared_and_running_joins_worker(pair, world, monkeypatch):
    pair.prepare(request(), world)
    pair.cancel("pair_1")
    pair.run("pair_1")
    assert pair.jobs["pair_1"].state == "cancelled"
    entered = threading.Event()
    def child(job, arm):
        entered.set()
        assert job.cancel.wait(2)
        raise InterruptedError("cancelled")
    monkeypatch.setattr(pair, "_child", child)
    pair.prepare(request(request_id="pair_2"), world)
    pair.run("pair_2")
    assert entered.wait(2)
    pair.cancel("pair_2")
    job = pair.jobs["pair_2"]
    assert job.state == "cancelled" and not job.thread.is_alive()
    assert json.loads((job.directory / "manifest.json").read_text())["state"] == "cancelled"


def test_pause_blocks_mutations_and_quit_closes_prepared(pair, world):
    commands, statuses = queue.Queue(), pair.status_queue
    pair.prepare(request(), world)
    for cmd in ({"type": "continue"}, {"type": "set", "civ": "King's Realm", "stat": "stability", "value": 1},
                {"type": "inject", "civ": "King's Realm", "event_type": "plague"}, {"type": "fork"}, {"type": "quit"}):
        commands.put(cmd)
    assert make_live_pause(commands, statuses, what_if=pair)(world, {}, []) is False
    assert world.civilizations[0].stability == 60
    assert pair.jobs["pair_1"].state == "cancelled"
    assert sum(m["type"] == "error" for m in list(statuses.queue)) == 4


def test_shutdown_cancels_and_no_request_can_restart(pair, world):
    pair.prepare(request(), world)
    server = LiveServer()
    server.what_if = pair
    server.stop()
    assert pair.jobs["pair_1"].state == "cancelled"
    with pytest.raises(wi.WhatIfError):
        pair.prepare(request(request_id="other"), world)


def test_one_active_and_retained_job_bound(pair, world, monkeypatch):
    monkeypatch.setattr(wi, "MAX_JOBS", 2)
    pair.prepare(request(), world)
    with pytest.raises(wi.WhatIfError, match="current pair"):
        pair.prepare(request(request_id="second"), world)
    pair.cancel("pair_1")
    pair.prepare(request(request_id="second"), world)
    pair.cancel("second")
    with pytest.raises(wi.WhatIfError, match="retained"):
        pair.prepare(request(request_id="third"), world)


def test_duplicate_preparation_replays_even_after_original_world_changes(pair, world):
    pair.prepare(request(), world)
    pair.cancel("pair_1")
    world.turn = 50
    world.civilizations[0].regions = []
    assert pair.prepare(request(), world)["state"] == "cancelled"
    assert len(pair.writes) == 1


def test_unknown_run_and_cancel_refused(pair):
    with pytest.raises(wi.WhatIfError, match="Prepare"):
        pair.run("unknown")
    with pytest.raises(wi.WhatIfError, match="Unknown"):
        pair.cancel("unknown")


def test_hash_seed_checks_actual_interpreter_flags(monkeypatch):
    monkeypatch.setenv("PYTHONHASHSEED", "0")
    monkeypatch.setattr(wi.sys, "flags", SimpleNamespace(hash_randomization=1))
    with pytest.raises(wi.WhatIfError, match="PYTHONHASHSEED=0"):
        wi.require_hash_seed()


def test_quoted_civilization_is_one_interactive_command():
    import shlex
    from chronicler.interactive import parse_command
    name = "King's Realm; $(anything) \"quoted\""
    assert parse_command(f"set {shlex.quote(name)} stability 75") == ("set", (name, "stability", 75))


def test_server_retains_latest_result_for_reconnect():
    server = LiveServer()
    status = {"type": "what_if_status", "request_id": "one", "state": "complete", "manifest": {}}
    result = {"type": "what_if_result", "request_id": "one"}
    server._record_status(status)
    server._record_status(result)
    assert server._last_what_if_status == status and server._last_what_if_result == result
    server._record_status({"type": "what_if_status", "request_id": "bad", "state": "error"})
    assert server._last_what_if_status == status and server._last_what_if_result == result
    server._record_status({"type": "what_if_status", "request_id": "two", "state": "prepared", "manifest": {}})
    assert server._last_what_if_result is None


@pytest.mark.parametrize("kind", ["compression", "raw_length"])
def test_corrupt_compression_refused_even_with_valid_section_hash(pair, tmp_path, monkeypatch, kind):
    path = tmp_path / "corrupt.ckpt"
    write_envelope(path)
    header, body = rc.read_header(path)
    if kind == "compression":
        body = b"not zlib data"
    else:
        header["sections"][0]["raw_length"] += 1
    header["sections"][0].update(length=len(body), sha256=hashlib.sha256(body).hexdigest())
    encoded = json.dumps(header).encode()
    path.write_bytes(rc.MAGIC + struct.pack("<I", len(encoded)) + encoded + body)
    with pytest.raises(wi.WhatIfError, match="corrupt"):
        wi.verified_header(path)


def test_failed_preparations_are_also_bounded_and_preserved(pair, world, monkeypatch):
    monkeypatch.setattr(wi, "MAX_JOBS", 1)
    monkeypatch.setattr(wi, "verified_header", lambda *a, **kw: (_ for _ in ()).throw(wi.WhatIfError("corrupt")))
    with pytest.raises(wi.WhatIfError, match="corrupt"):
        pair.prepare(request(), world)
    assert len(pair.writes) == 1 and pair.writes[0].exists()
    with pytest.raises(wi.WhatIfError, match="retained"):
        pair.prepare(request(request_id="other"), world)
    assert len(pair.writes) == 1


@pytest.mark.parametrize("running", [True, False])
def test_output_scan_atomic_rename_between_enumeration_and_stat(tmp_path, monkeypatch, running):
    directory = tmp_path / "arm"
    directory.mkdir()
    destination = directory / "state.json"
    destination.write_bytes(b"old")
    temporary = directory / ".state.json.123.tmp"
    temporary.write_bytes(b"completed replacement")
    log = directory / "process.log"
    log.write_bytes(b"")
    real_stat = Path.stat
    renamed = False

    def stat_after_atomic_replace(path, *args, **kwargs):
        nonlocal renamed
        if path == temporary and not renamed:
            # The observer already has this directory entry; the actual atomic
            # writer removes it immediately before its metadata is requested.
            temporary.replace(destination)
            renamed = True
        return real_stat(path, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", stat_after_atomic_replace)
    if running:
        wi._check_output_limits(directory, log, "baseline", running=True)
    else:
        with pytest.raises(FileNotFoundError):
            wi._check_output_limits(directory, log, "baseline")
    assert renamed and not temporary.exists()
    assert destination.read_bytes() == b"completed replacement"
    # Once the child exits, the destination is measured exactly; a vanished
    # temp never excuses an oversized completed artifact.
    assert wi._output_size(directory) == len(b"completed replacement")
    monkeypatch.setattr(wi, "MAX_OUTPUT_BYTES", len(b"completed replacement") - 1)
    with pytest.raises(wi.WhatIfError, match="output limit"):
        wi._check_output_limits(directory, log, "baseline")


@pytest.mark.parametrize("running", [True, False])
@pytest.mark.parametrize("limit", ["log", "total"])
def test_output_caps_still_refuse_running_and_completed_outputs(tmp_path, monkeypatch, running, limit):
    log = tmp_path / "process.log"
    log.write_bytes(b"1234" if limit == "log" else b"")
    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / "state.json").write_bytes(b"12345")
    monkeypatch.setattr(wi, "MAX_LOG_BYTES", 3 if limit == "log" else 100)
    monkeypatch.setattr(wi, "MAX_OUTPUT_BYTES", 100 if limit == "log" else 4)
    with pytest.raises(wi.WhatIfError, match="output limit"):
        wi._check_output_limits(tmp_path, log, "intervention", running=running)


@pytest.mark.parametrize("running", [True, False])
@pytest.mark.parametrize("error", [PermissionError("denied"), OSError("device I/O failure")])
def test_output_file_stat_errors_are_not_missing_outputs(tmp_path, monkeypatch, running, error):
    log = tmp_path / "process.log"
    log.write_bytes(b"")
    output = tmp_path / "state.json"
    output.write_bytes(b"data")
    real_stat = Path.stat

    def refuse_stat(path, *args, **kwargs):
        if path == output:
            raise error
        return real_stat(path, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", refuse_stat)
    with pytest.raises(type(error)) as caught:
        wi._check_output_limits(tmp_path, log, "baseline", running=running)
    assert caught.value is error


@pytest.mark.parametrize("running", [True, False])
def test_output_directory_permission_errors_are_not_silently_skipped(tmp_path, monkeypatch, running):
    log = tmp_path / "process.log"
    log.write_bytes(b"")
    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / "state.json").write_bytes(b"data")
    real_scandir = wi.os.scandir

    def refuse_directory(path):
        if Path(path) == nested:
            raise PermissionError("cannot scan output directory")
        return real_scandir(path)

    monkeypatch.setattr(wi.os, "scandir", refuse_directory)
    with pytest.raises(PermissionError, match="cannot scan"):
        wi._check_output_limits(tmp_path, log, "baseline", running=running)
