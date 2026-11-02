"""POSIX process/native what-if evidence; outside the guarded offline lane."""
import copy
import hashlib
import json
import io
import os
from pathlib import Path
import pickle
import queue
import random
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
def test_real_native_pair_preserves_original_and_unchanged_arm(tmp_path, changed):
    if os.environ.get("PYTHONHASHSEED") != "0" or sys.flags.hash_randomization:
        pytest.skip("launch PYTHONHASHSEED=0 for exact parent/children")
    native = pytest.importorskip("chronicler_agents")
    assert isinstance(native.AgentSimulator, type)
    import chronicler.main as main
    from chronicler.bundle_codec import load_bundle
    from chronicler.run_checkpoint import read_header
    args = main._build_parser().parse_args([
        "--seed", "42", "--turns", "4", "--regions", "4", "--civs", "2", "--agents", "hybrid",
        "--simulate-only", "--output", str(tmp_path / "original" / "chronicle.md"),
        "--state", str(tmp_path / "original" / "state.json"),
    ])
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
        # Serialize the real original graph/private RNG before any preparation.
        before = world_bytes(world)
        py_rng, np_rng = random.getstate(), pickle.dumps(np.random.get_state())
        civ = next(c for c in world.civilizations if c.regions)
        msg = {"type": "what_if_prepare", "request_id": "native_pair", "civ": civ.name,
               "value": (1 if civ.stability != 1 else 100) if changed else civ.stability, "turns": 2}  # unchanged intervention checks determinism
        pair.prepare(msg, world)
        job = pair.jobs["native_pair"]
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
        if not changed:
            assert baseline == intervention
        else:
            assert baseline != intervention
        recorded["baseline"] = baseline
        return True
    try:
        main.execute_run(args, on_pause=pause, pause_every=2, turn_boundary=checkpoints)
    finally:
        pair.close()
    # Original live graph continued unchanged and matches the resumed baseline.
    original = load_bundle(output_dir / "chronicle_bundle.json")
    original["metadata"].pop("generated_at", None)
    assert original == recorded["baseline"]
