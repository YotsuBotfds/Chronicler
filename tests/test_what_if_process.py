"""POSIX process/native what-if evidence; outside the guarded offline lane."""
import copy
import hashlib
import importlib.machinery
import json
import io
import os
from pathlib import Path
import pickle
import queue
import random
import signal
import subprocess
import sys
import threading
import time

import numpy as np
import pytest

from chronicler.live_checkpoints import LiveCheckpoints, LiveView
from chronicler.what_if import WhatIfPairs, WhatIfError
import chronicler.what_if as wi

pytestmark = pytest.mark.skipif(os.name != "posix", reason="POSIX process groups required")


def wait_file(path):
    deadline = time.monotonic() + 4
    while not path.exists():
        if time.monotonic() > deadline:
            raise AssertionError("child did not start")
        time.sleep(0.02)


@pytest.mark.parametrize("action", ["cancel", "shutdown", "timeout"])
def test_cancel_kills_owned_cli_group_including_descendant(tmp_path, monkeypatch, action):
    """Run actual child+grandchild processes behind the exact CLI boundary."""
    from types import SimpleNamespace
    from tests.test_what_if import IDENTITY, write_envelope, request
    import chronicler.run_checkpoint as rc
    monkeypatch.setattr(wi, "require_hash_seed", lambda: None)
    monkeypatch.setattr(wi, "fresh_identity", lambda: copy.deepcopy(IDENTITY))
    monkeypatch.setattr(rc, "runtime_identity", lambda: copy.deepcopy(IDENTITY))
    pair = WhatIfPairs(tmp_path, queue.Queue(), SimpleNamespace(save_private=write_envelope))
    world = SimpleNamespace(turn=2, seed=42, civilizations=[SimpleNamespace(name="King's Realm", regions=["R"], stability=60)])
    pair.prepare(request(), world)
    real_popen = subprocess.Popen
    processes = []
    pid_path = tmp_path / "grandchild.pid"
    # The child waits for its grandchild; both are in the owned new session.
    script = ("import subprocess,sys,pathlib; "
              "p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)']); "
              f"pathlib.Path({str(pid_path)!r}).write_text(str(p.pid)); p.wait()")
    def popen(command, **kwargs):
        assert command[1:5] == ["-m", "chronicler.main", "--interactive", "--resume"]
        assert "--resume-allow-mismatch" not in command
        p = real_popen([sys.executable, "-c", script], **kwargs)
        processes.append(p)
        return p
    monkeypatch.setattr(wi.subprocess, "Popen", popen)
    if action == "timeout":
        monkeypatch.setattr(wi, "ARM_TIMEOUT_SECONDS", 1)
    pair.run("pair_1")
    wait_file(pid_path)
    grandchild = int(pid_path.read_text())
    start = time.monotonic()
    if action == "timeout":
        pair.jobs["pair_1"].thread.join(4)
    elif action == "shutdown":
        from chronicler.live import LiveServer
        server = LiveServer()
        server.what_if = pair
        server.stop()
    else:
        pair.cancel("pair_1")
    assert time.monotonic() - start < 5
    assert len(processes) == 1 and processes[0].poll() is not None
    assert pair.jobs["pair_1"].state == ("error" if action == "timeout" else "cancelled")
    assert not pair.jobs["pair_1"].thread.is_alive()
    # Linux can retain the killed orphan briefly as a zombie until init reaps.
    stat = Path(f"/proc/{grandchild}/stat")
    assert not stat.exists() or stat.read_text().split()[2] == "Z"


@pytest.mark.parametrize("changed", [False, True])
def test_real_native_pair_preserves_original_and_unchanged_arm(tmp_path, changed, *, policy_case=None):
    native = pytest.importorskip("chronicler_agents")
    import chronicler_agents.chronicler_agents as compiled
    assert any(compiled.__file__.endswith(suffix) for suffix in importlib.machinery.EXTENSION_SUFFIXES)
    assert all(isinstance(getattr(native, name, None), type)
               and getattr(native, name) is getattr(compiled, name)
               for name in ("AgentSimulator", "EcologySimulator", "PoliticsSimulator"))
    if os.environ.get("PYTHONHASHSEED") != "0" or sys.flags.hash_randomization:
        _run_hash_zero_native_fixture(tmp_path, changed, policy_case)
        return
    import chronicler.main as main
    from chronicler.bundle_codec import load_bundle
    from chronicler.run_checkpoint import read_header
    command = [
        "--seed", "42", "--turns", "4", "--regions", "4", "--civs", "2", "--agents", "hybrid",
        "--simulate-only", "--output", str(tmp_path / "original" / "chronicle.md"),
        "--state", str(tmp_path / "original" / "state.json"),
    ]
    if policy_case is not None:
        command.append("--grain-reserves")
    args = main._build_parser().parse_args(command)
    output_dir = Path(args.output).parent
    output_dir.mkdir()
    checkpoints = LiveCheckpoints(output_dir, queue.Queue(), LiveView(), lambda: 0, 2)
    pair = WhatIfPairs(output_dir, checkpoints.status_queue, checkpoints)
    recorded = {}
    def world_bytes(world):
        from chronicler.run_checkpoint import _Pickler
        buf = io.BytesIO()
        writer = _Pickler(buf)
        writer.dump(world)
        return buf.getvalue(), writer.natives
    def pause(world, memories, pending):
        if world.turn != 2:
            return True
        if policy_case in ("disable", "noop-enabled"):
            # Both arms and the original receive this explicitly declared
            # common input before saving. No arm enables the host system.
            from chronicler.pause_policy import STAT
            world.tuning_overrides[STAT] = 1.
        # Serialize the real original graph/private RNG before any preparation.
        before = world_bytes(world)
        py_rng, np_rng = random.getstate(), pickle.dumps(np.random.get_state())
        civ = next(c for c in world.civilizations if c.regions)
        msg = {"type": "what_if_prepare", "request_id": "native_pair", "civ": civ.name,
               "value": (1 if civ.stability != 1 else 100) if changed else civ.stability, "turns": 2}  # unchanged intervention checks determinism
        if policy_case is not None:
            msg = {"type": "what_if_prepare", "request_id": "native_pair",
                   "control": "granary_shortfall_priority", "turns": 2,
                   "value": int(policy_case in ("enable", "noop-enabled"))}
        pair.prepare(msg, world)
        job = pair.jobs["native_pair"]
        if policy_case is not None:
            assert job.manifest["schema_version"] == 2
            assert job.manifest["intervention"]["scope"] == "world"
        common_bytes = (job.directory / "common.ckpt").read_bytes()
        header, _ = read_header(job.directory / "common.ckpt")
        assert any(s["name"].startswith("native.") for s in header["sections"])
        pair.run("native_pair")
        job.thread.join(35)
        assert not job.thread.is_alive(), "pair exceeded bounded small test wait"
        assert job.state == "complete", job.message
        assert (job.directory / "common.ckpt").read_bytes() == common_bytes
        assert world_bytes(world) == before
        assert random.getstate() == py_rng and pickle.dumps(np.random.get_state()) == np_rng
        # A second exact save witnesses unchanged native simulator bytes too.
        checkpoints.save_private(job.directory / "after.ckpt")
        after_header, after_body = read_header(job.directory / "after.ckpt")
        from chronicler.run_checkpoint import _section
        before_header, before_body = read_header(job.directory / "common.ckpt")
        assert after_header["run_config"] == before_header["run_config"]
        for section in before_header["sections"]:
            if section["name"].startswith("native."):
                assert _section(job.directory / "common.ckpt", before_header, before_body, section["name"]) == \
                    _section(job.directory / "after.ckpt", after_header, after_body, section["name"])
        baseline = copy.deepcopy(job.result["baseline"]["bundle"])
        intervention = copy.deepcopy(job.result["intervention"]["bundle"])
        for arm, bundle in (("baseline", baseline), ("intervention", intervention)):
            path = job.directory / arm / "chronicle_bundle.json"
            assert bundle["metadata"].pop("what_if")["arm"] == arm
            assert hashlib.sha256(path.read_bytes()).hexdigest() == job.result[arm]["identity"]["sha256"]
            assert load_bundle(path)["metadata"]["what_if"]["semantics"] == "exact_checkpoint_pair"
            bundle["metadata"].pop("generated_at", None)
        same = not changed if policy_case is None else policy_case.startswith("noop")
        if same:
            assert baseline == intervention
        else:
            assert baseline != intervention
        recorded["baseline"] = baseline
        if policy_case is not None:
            from chronicler.run_checkpoint import read_checkpoint
            from chronicler.pause_policy import STAT, policy_value
            final_states = {}
            for arm in ("baseline", "intervention"):
                final_path = job.directory / arm / "final.ckpt"
                final = read_checkpoint(final_path)
                wanted = int(policy_case in ("disable", "noop-enabled")) if arm == "baseline" else msg["value"]
                assert policy_value(final.state.world) == wanted
                expected = header.get("run_config", {}).get("interventions", [])
                if arm == "intervention":
                    expected = expected + [{"turn": 2, "command": "set", "civ": "@world", "stat": STAT, "value": msg["value"]}]
                assert final.state.run_config.get("interventions", []) == expected
                if policy_case == "noop-default":
                    assert STAT not in final.state.world.tuning_overrides
                final_states[arm] = final
                recorded.setdefault("policy_checkpoints", []).append((arm, final_path, wanted))
            if same:
                assert final_states["baseline"].state.world.model_dump() == final_states["intervention"].state.world.model_dump()
                for section in final_states["baseline"].header["sections"]:
                    if section["name"].startswith("native."):
                        h1, b1 = read_header(job.directory / "baseline" / "final.ckpt")
                        h2, b2 = read_header(job.directory / "intervention" / "final.ckpt")
                        assert _section(job.directory / "baseline" / "final.ckpt", h1, b1, section["name"]) == \
                            _section(job.directory / "intervention" / "final.ckpt", h2, b2, section["name"])
        return True
    try:
        main.execute_run(args, on_pause=pause, pause_every=2, turn_boundary=checkpoints)
    finally:
        pair.close()
    # Original live graph continued unchanged and matches the resumed baseline.
    original = load_bundle(output_dir / "chronicle_bundle.json")
    original["metadata"].pop("generated_at", None)
    assert original == recorded["baseline"]
    if policy_case is not None:
        _assert_policy_checkpoint_continuations(tmp_path, recorded["policy_checkpoints"])


@pytest.mark.parametrize("policy_case", ["enable", "disable", "noop-default", "noop-enabled"])
def test_real_native_granary_policy_pair_and_exact_continuations(tmp_path, policy_case):
    test_real_native_pair_preserves_original_and_unchanged_arm(tmp_path, True, policy_case=policy_case)


def _assert_policy_checkpoint_continuations(tmp_path, checkpoints):
    """Ordinary CLI resumes retain the saved policy, without repeating a command."""
    from chronicler.bundle_codec import load_bundle
    from chronicler.pause_policy import STAT, policy_value
    from chronicler.run_checkpoint import read_checkpoint, read_header, _section
    for arm, source, wanted in checkpoints:
        def resume(checkpoint, name, end):
            directory = tmp_path / f"{arm}-{name}"
            directory.mkdir()
            command = [sys.executable, "-m", "chronicler.main", "--resume", str(checkpoint),
                       "--simulate-only", "--turns", str(end), "--checkpoint-every", "1",
                       "--checkpoint", str(directory / "turn_{turn}.ckpt"),
                       "--output", str(directory / "chronicle.md"), "--state", str(directory / "state.json")]
            result = subprocess.run(command, capture_output=True, text=True, timeout=35)
            (directory / "process.log").write_text(result.stdout + result.stderr)
            assert result.returncode == 0, result.stdout + result.stderr
            final = read_checkpoint(directory / f"turn_{end}.ckpt")
            assert final.exact and policy_value(final.state.world) == wanted
            source_state = read_checkpoint(checkpoint)
            assert final.state.run_config.get("interventions", []) == source_state.state.run_config.get("interventions", [])
            assert (STAT in final.state.world.tuning_overrides) == (STAT in source_state.state.world.tuning_overrides)
            return directory
        straight = resume(source, "straight", 6)
        first = resume(source, "split-first", 5)
        split = resume(first / "turn_5.ckpt", "split-last", 6)
        def outputs(directory):
            bundle = load_bundle(directory / "chronicle_bundle.json")
            bundle["metadata"].pop("generated_at", None)
            return bundle, json.loads((directory / "state.json").read_text())
        assert outputs(straight) == outputs(split)
        h1, b1 = read_header(straight / "turn_6.ckpt")
        h2, b2 = read_header(split / "turn_6.ckpt")
        for section in h1["sections"]:
            if section["name"].startswith("native."):
                assert _section(straight / "turn_6.ckpt", h1, b1, section["name"]) == \
                    _section(split / "turn_6.ckpt", h2, b2, section["name"])


def _run_hash_zero_native_fixture(tmp_path, changed, policy_case=None):
    """Execute this exact fixture without inheriting pytest plugins/JUnit writers.

    A hash seed cannot be changed in a running interpreter. CI's unpinned
    pytest therefore supervises one ordinary fixed-hash Python process; it
    does not skip or replace either real native continuation assertion.
    """
    script = """
import json, runpy, signal, sys
from pathlib import Path
def terminate(signum, frame):
    raise SystemExit("hash-zero fixture terminated")
signal.signal(signal.SIGTERM, terminate)
namespace = runpy.run_path(sys.argv[1])
changed = sys.argv[3] == "True"
policy_case = None if sys.argv[4] == "None" else sys.argv[4]
namespace["test_real_native_pair_preserves_original_and_unchanged_arm"](Path(sys.argv[2]), changed, policy_case=policy_case)
print("HASH_ZERO_NATIVE_PAIR_COMPLETE " + json.dumps({"changed": changed, "hash_seed": "0", "hash_randomization": sys.flags.hash_randomization}), flush=True)
"""
    env = dict(os.environ, PYTHONHASHSEED="0")
    source = str(Path(__file__).resolve().parents[1] / "src")
    env["PYTHONPATH"] = source + os.pathsep + env.get("PYTHONPATH", "")
    process = subprocess.Popen(
        [sys.executable, "-c", script, str(Path(__file__).resolve()), str(tmp_path), str(changed), str(policy_case)],
        env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        start_new_session=True,
    )
    try:
        stdout, _ = process.communicate(timeout=110)
        assert process.returncode == 0, stdout
        receipt = next((line.removeprefix("HASH_ZERO_NATIVE_PAIR_COMPLETE ")
                        for line in stdout.splitlines() if line.startswith("HASH_ZERO_NATIVE_PAIR_COMPLETE ")), None)
        assert receipt is not None, stdout
        assert json.loads(receipt) == {"changed": changed, "hash_seed": "0", "hash_randomization": 0}, stdout
    finally:
        if process.poll() is None:
            # Unwind the same fixture's finally/pair.close first: its arm CLI
            # processes deliberately own separate process groups.
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                pass
        WhatIfPairs._kill_group(process)
