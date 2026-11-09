"""Bounded live exact-checkpoint pairs; never accepts paths or executable controls.

Preparation runs at the original simulation's pause boundary. Execution uses
ordinary interactive exact-resume CLI processes, with one fixed intervention.
The private files, including failed and cancelled arms, are retained as evidence.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import queue
import re
import shlex
import signal
import stat
import subprocess
import sys
import threading
import time
import uuid
import zlib
from dataclasses import dataclass, field
from typing import Any

from chronicler.artifact_io import atomic_write_text
from chronicler.bundle_codec import decode_bundle, dumps_bundle
from chronicler.pause_policy import CONTROL, STAT, TARGET, policy_value, validate_policy_command
from chronicler.pause_transport import (CONTROL as TRANSPORT_CONTROL, TARGET as TRANSPORT_TARGET,
    STAT as TRANSPORT_STAT, encode as encode_transport, decode as decode_transport, preview as preview_transport)

from chronicler.pause_academy import (CONTROL as ACADEMY_CONTROL, TARGET as ACADEMY_TARGET,
    STAT as ACADEMY_STAT, validate_command as validate_academy_command, preview as preview_academy)

MAX_JOBS = 8
MAX_BUNDLE_BYTES = 16 * 1024 * 1024
MAX_CHECKPOINT_BYTES = 128 * 1024 * 1024
MAX_RAW_CHECKPOINT_BYTES = 512 * 1024 * 1024
MAX_OUTPUT_BYTES = 192 * 1024 * 1024
MAX_LOG_BYTES = 2 * 1024 * 1024
ARM_TIMEOUT_SECONDS = 120
LIMITS = [
    "One paired trajectory at one seed; not a population causal estimate.",
    "Only stability can be set; 1–20 additional turns, simulation only.",
    "Bundle metadata.what_if is an intentional export change before hashing.",
]
_REQUEST_ID = re.compile(r"[A-Za-z0-9_-]{1,80}\Z")


class WhatIfError(ValueError):
    pass


def _output_size(directory: Path, *, allow_vanished: bool = False) -> int:
    """Observe regular outputs; a running atomic writer may rename a temp.

    This is a changing observation while the child runs, followed by a strict
    scan after it exits. Only an enumerated file disappearing is tolerated;
    permission, traversal and other I/O failures remain errors.
    """
    def walk_error(error: OSError) -> None:
        raise error

    total = 0
    for parent, _, names in os.walk(directory, onerror=walk_error):
        for name in names:
            try:
                info = (Path(parent) / name).stat()
            except FileNotFoundError:
                if allow_vanished:
                    continue
                raise
            if stat.S_ISREG(info.st_mode):
                total += info.st_size
    return total


def _check_output_limits(directory: Path, log_path: Path, arm: str, *, running: bool = False) -> None:
    if (log_path.stat().st_size > MAX_LOG_BYTES or
            _output_size(directory, allow_vanished=running) > MAX_OUTPUT_BYTES):
        raise WhatIfError(f"{arm} exceeded its output limit")


def _request_fields(msg: dict) -> tuple[str, str, str, int, int]:
    request_id = msg.get("request_id")
    if not isinstance(request_id, str) or not _REQUEST_ID.fullmatch(request_id):
        raise WhatIfError("request_id must contain 1–80 letters, digits, underscores or hyphens")
    if msg.get("control") == ACADEMY_CONTROL:
        if msg.get("type") != "what_if_prepare" or set(msg) != {"type", "request_id", "control", "region_id", "fallen_seat_id", "turns"}:
            raise WhatIfError("Invalid academy restoration request fields")
        rid, seat, turns = msg.get("region_id"), msg.get("fallen_seat_id"), msg.get("turns")
        if type(rid) is not int or rid < 0 or type(seat) is not int or seat < 0:
            raise WhatIfError("Invalid academy region or fallen seat ID")
        if type(turns) is not int or not 1 <= turns <= 20:
            raise WhatIfError("Horizon must be an integer from 1 to 20 additional turns")
        return request_id, ACADEMY_TARGET, ACADEMY_STAT, seat, turns
    if msg.get("control") == TRANSPORT_CONTROL:
        if msg.get("type") != "what_if_prepare" or set(msg) != {"type", "request_id", "control", "region_id", "duration", "turns"}:
            raise WhatIfError("Invalid regional transport request fields")
        turns = msg.get("turns")
        if type(turns) is not int or not 1 <= turns <= 20:
            raise WhatIfError("Horizon must be an integer from 1 to 20 additional turns")
        try:
            value = encode_transport(msg.get("region_id"), msg.get("duration"))
        except ValueError as exc:
            raise WhatIfError(str(exc)) from exc
        return request_id, TRANSPORT_TARGET, TRANSPORT_STAT, value, turns
    policy = "control" in msg
    allowed = {"type", "request_id", "value", "turns", "control" if policy else "civ"}
    if set(msg) - allowed or (policy and msg.get("control") != CONTROL):
        raise WhatIfError("Only the declared stability or granary shortfall policy control is supported")
    value, turns = msg.get("value"), msg.get("turns")
    if policy:
        if type(value) is not int or value not in (0, 1):
            raise WhatIfError("Granary shortfall priority must be integer 0 or 1")
        name, stat = TARGET, STAT
    else:
        if type(value) is not int or not 1 <= value <= 100:
            raise WhatIfError("Stability must be an integer from 1 to 100")
        name, stat = msg.get("civ"), "stability"
    if type(turns) is not int or not 1 <= turns <= 20:
        raise WhatIfError("Horizon must be an integer from 1 to 20 additional turns")
    if not isinstance(name, str) or any(c in name for c in "\n\r\x00"):
        raise WhatIfError("Invalid civilization name")
    return request_id, name, stat, value, turns


def validate_request(msg: dict, world: Any) -> tuple[str, str, int, int, int]:
    request_id, name, stat, value, turns = _request_fields(msg)
    if stat == ACADEMY_STAT:
        try:
            receipt = preview_academy(world, name, stat, value)
            if receipt.request.region_id != msg["region_id"]:
                raise ValueError("Fallen academy does not belong to the requested region")
            if not receipt.changed:
                raise ValueError("Academy is already restored at this boundary")
        except ValueError as exc:
            raise WhatIfError(str(exc)) from exc
        return request_id, name, value, turns, value
    if stat == TRANSPORT_STAT:
        try:
            receipt = preview_transport(world, name, stat, value)
        except ValueError as exc:
            raise WhatIfError(str(exc)) from exc
        return request_id, name, value, turns, receipt.prior_counter
    if stat == STAT:
        try:
            before = policy_value(world)
        except ValueError as exc:
            raise WhatIfError(str(exc)) from exc
        return request_id, name, value, turns, before
    civs = [c for c in world.civilizations if c.name == name and c.regions]
    if len(civs) != 1:
        raise WhatIfError("Choose one living civilization in the currently paused world")
    return request_id, name, value, turns, civs[0].stability


def intervention_command(intervention: dict) -> dict:
    """Compile only declared controls; metadata such as scope is never a command."""
    command = {key: intervention.get(key) for key in ("command", "civ", "stat", "value")}
    if command["command"] != "set":
        raise WhatIfError("Unsupported intervention command")
    if command["stat"] == ACADEMY_STAT:
        try:
            validate_academy_command(command["civ"], command["stat"], command["value"])
            if (type(intervention.get("fallen_seat_id")) is not int or
                    intervention["fallen_seat_id"] != command["value"] or
                    type(intervention.get("region_id")) is not int or intervention["region_id"] < 0):
                raise ValueError("Academy manifest does not match its command")
        except ValueError as exc:
            raise WhatIfError(str(exc)) from exc
    elif command["stat"] == TRANSPORT_STAT:
        try:
            decoded = decode_transport(command["civ"], command["stat"], command["value"])
            if (intervention.get("region_id") != decoded.region_id or
                    intervention.get("duration") != decoded.duration or
                    type(intervention.get("region_id")) is not int or
                    type(intervention.get("duration")) is not int):
                raise ValueError("Transport manifest does not match its command")
        except ValueError as exc:
            raise WhatIfError(str(exc)) from exc
    elif command["stat"] == STAT:
        try:
            validate_policy_command(command["civ"], command["stat"], command["value"])
        except ValueError as exc:
            raise WhatIfError(str(exc)) from exc
    elif (command["stat"] != "stability" or not isinstance(command["civ"], str)
          or any(c in command["civ"] for c in "\n\r\x00")
          or type(command["value"]) is not int or not 1 <= command["value"] <= 100):
        raise WhatIfError("Unsupported intervention control")
    return command



def validate_academy_checkpoint(path: Path, intervention: dict) -> None:
    """Bind the public manifest to the exact restored child source state."""
    from chronicler.run_checkpoint import read_checkpoint
    loaded = read_checkpoint(path)
    if not loaded.exact:
        raise WhatIfError("Academy restoration requires an exact checkpoint")
    world, bridge = loaded.state.world, loaded.state.agent_bridge
    try:
        receipt = preview_academy(world, ACADEMY_TARGET, ACADEMY_STAT, intervention["fallen_seat_id"])
        req = receipt.request
        seat = world.scholarship.seats[req.fallen_seat_id]
        expected = {"region_id": req.region_id, "region_name": world.regions[req.region_id].name,
            "fallen_seat_id": req.fallen_seat_id, "fallen_seat_name": seat.name,
            "fallen_founder": req.fallen_founder, "fallen_founded_turn": req.fallen_founded_turn,
            "fallen_turn": req.fallen_turn, "current_lord": req.current_lord,
            "current_lord_name": world.civilizations[req.current_lord].name,
            "fee": receipt.fee, "treasury_before": receipt.treasury_before,
            "treasury_after": receipt.treasury_after}
        if not receipt.changed or any(intervention.get(k) != v for k, v in expected.items()):
            raise WhatIfError("Academy manifest differs from its saved checkpoint")
    except ValueError as exc:
        raise WhatIfError(str(exc)) from exc
    finally:
        if bridge is not None:
            bridge.close()


def require_hash_seed() -> None:
    # Checking only os.environ is insufficient: changing it after startup does
    # not change the current interpreter's hash secret.
    if os.environ.get("PYTHONHASHSEED") != "0" or sys.flags.hash_randomization != 0:
        raise WhatIfError("Exact what-if pairs require starting the live server with PYTHONHASHSEED=0")
    if os.name != "posix":
        raise WhatIfError("Exact what-if process-group cleanup currently requires POSIX")


def fresh_identity() -> dict:
    """Read package, extension bytes and environment again, bypassing caches."""
    from chronicler.batch_manifest import source_identity, native_identity, environment_identity
    from chronicler.run_checkpoint import runtime_identity
    source, native, env = source_identity(), native_identity(), environment_identity()
    old = runtime_identity()
    native_out = {"status": native["status"], "state_layouts": old["native"].get("state_layouts", {})}
    if native["status"] == "found":
        native_out.update(sha256=native["sha256"], bytes=native["bytes"])
    return {"source": {k: source[k] for k in ("git_sha", "package_digest")},
            "native": native_out,
            "environment": {k: env[k] for k in ("python", "implementation", "machine",
                                                  "affinity_cpu_count", "thread_env", "packages")}}


def verified_header(path: Path, *, turn: int | None = None, seed: int | None = None) -> dict:
    """Verify all section digests and compatibility without restoring objects."""
    from chronicler.run_checkpoint import read_header, _compare_identity, runtime_identity
    if not path.is_file() or path.is_symlink() or path.stat().st_size > MAX_CHECKPOINT_BYTES:
        raise WhatIfError("Checkpoint is missing, not regular or exceeds the size limit")
    header, body = read_header(path)
    if header.get("exact") is not True or header.get("run_config", {}).get("resume_info"):
        raise WhatIfError("What-if requires an exact checkpoint; approximate resumes are refused")
    sections = header.get("sections", [])
    if not sections or sum(s.get("name") == "python" for s in sections) != 1:
        raise WhatIfError("Checkpoint must contain exactly one Python state section")
    if sum(s.get("raw_length", -1) for s in sections) > MAX_RAW_CHECKPOINT_BYTES:
        raise WhatIfError("Checkpoint decompressed state exceeds its size limit")
    for section in sections:
        data = body[section["offset"]:section["offset"] + section["length"]]
        if hashlib.sha256(data).hexdigest() != section["sha256"]:
            raise WhatIfError("Checkpoint section is corrupt (SHA-256 differs)")
        raw_length = section.get("raw_length")
        if type(raw_length) is not int or not 0 <= raw_length <= MAX_RAW_CHECKPOINT_BYTES:
            raise WhatIfError("Checkpoint section has an invalid raw length")
        try:
            decoder = zlib.decompressobj()
            raw = decoder.decompress(data, raw_length + 1)
            if len(raw) != raw_length or not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:
                raise WhatIfError("Checkpoint section is corrupt (compressed length differs)")
        except zlib.error as exc:
            raise WhatIfError("Checkpoint section is corrupt (invalid compression)") from exc
    current = fresh_identity()
    native = any(s["name"].startswith("native.") for s in sections)
    mismatches = _compare_identity(header["identity"], current, native)
    # A running interpreter may have cached identity before source/env changes.
    mismatches += _compare_identity(runtime_identity(), current, native)
    if mismatches:
        raise WhatIfError("Exact checkpoint compatibility refusal: " + "; ".join(mismatches))
    if turn is not None and header.get("turn") != turn:
        raise WhatIfError("Checkpoint turn differs from the currently paused world")
    if seed is not None and header.get("seed") != seed:
        raise WhatIfError("Checkpoint seed differs from the currently paused world")
    return header


def artifact_identity(path: Path) -> dict:
    data = path.read_bytes()
    return {"name": path.name, "byteLength": len(data), "sha256": hashlib.sha256(data).hexdigest()}


@dataclass
class Job:
    directory: Path
    manifest: dict
    state: str = "prepared"
    arm: str | None = None
    message: str | None = None
    result: dict | None = None
    cancel: threading.Event = field(default_factory=threading.Event)
    thread: threading.Thread | None = None
    process: subprocess.Popen | None = None


class WhatIfPairs:
    """One active pair and bounded retained request IDs per live session."""

    def __init__(self, output_dir: Path, status_queue: queue.Queue, checkpoints: Any):
        self.output_dir = Path(output_dir)
        self.status_queue = status_queue
        self.checkpoints = checkpoints
        self.jobs: dict[str, Job] = {}
        self._lock = threading.RLock()
        self._closed = False
        self._attempts = 0

    @property
    def busy(self) -> bool:
        with self._lock:
            return any(j.state in {"prepared", "running"} for j in self.jobs.values())

    def _status(self, job: Job) -> dict:
        msg = {"type": "what_if_status", "request_id": job.manifest["request_id"],
               "state": job.state, "manifest": copy.deepcopy(job.manifest)}
        if job.arm:
            msg["arm"] = job.arm
        if job.message:
            msg["message"] = job.message
        self.status_queue.put(msg)
        return msg

    def _persist(self, job: Job) -> None:
        atomic_write_text(job.directory / "manifest.json", json.dumps(
            {**job.manifest, "state": job.state, "arm": job.arm, "message": job.message},
            indent=2, ensure_ascii=False))

    def prepare(self, msg: dict, world: Any) -> dict:
        with self._lock:
            request_id = msg.get("request_id")
            if not isinstance(request_id, str):
                raise WhatIfError("request_id must be a string")
            existing = self.jobs.get(request_id)
            if existing:
                m = existing.manifest
                _, name, stat, value, turns = _request_fields(msg)
                if ((name, stat, value, turns) !=
                        (m["intervention"]["civ"], m["intervention"]["stat"],
                         m["intervention"]["value"], m["turns"])):
                    raise WhatIfError("This request_id already describes a different pair")
                if stat == ACADEMY_STAT and msg["region_id"] != m["intervention"]["region_id"]:
                    raise WhatIfError("This request_id already describes a different pair")
                return self._status(existing)
            request_id, civ, value, turns, before = validate_request(msg, world)
            if self._closed or self.busy:
                raise WhatIfError("Cancel or finish the current pair before preparing another")
            if self._attempts >= MAX_JOBS:
                raise WhatIfError("This session has reached its eight retained what-if requests")
            require_hash_seed()
            root = self.output_dir.resolve()
            # A resumed live session can pause before ordinary output creates
            # its directory. Preparation owns a private checkpoint immediately.
            root.mkdir(mode=0o700, parents=True, exist_ok=True)
            parent = root / "what_if"
            parent.mkdir(mode=0o700, exist_ok=True)
            if parent.is_symlink() or not parent.resolve().is_relative_to(root):
                raise WhatIfError("Private what-if output directory leads outside the live output")
            directory = parent / uuid.uuid4().hex
            self._attempts += 1  # Failed preparations also retain bounded private evidence.
            directory.mkdir(mode=0o700)
            checkpoint = directory / "common.ckpt"
            # Only the simulation thread owns this binding. No client path.
            self.checkpoints.save_private(checkpoint)
            header = verified_header(checkpoint, turn=world.turn, seed=world.seed)
            config = header.get("run_config", {})
            if config.get("output_args", {}).get("simulate_only") is not True:
                raise WhatIfError("Start this live run with --simulate-only before preparing exact what-if pairs")
            is_academy = msg.get("control") == ACADEMY_CONTROL
            is_transport = msg.get("control") == TRANSPORT_CONTROL
            is_policy = msg.get("control") == CONTROL
            if (is_transport or is_academy) and config.get("simulation_args", {}).get("agents") != "hybrid":
                raise WhatIfError("Transport disruption requires an exact hybrid checkpoint")
            stat = ACADEMY_STAT if is_academy else TRANSPORT_STAT if is_transport else STAT if is_policy else "stability"
            intervention = {"command": "set", "civ": civ, "stat": stat,
                            "before": before, "value": value}
            limits = list(LIMITS)
            if is_policy:
                intervention["scope"] = "world"
                limits[1] = "Global granary procurement priority only; 1–20 additional turns, simulation only."
            if is_transport:
                receipt = preview_transport(world, civ, stat, value)
                intervention.update(scope="region", region_id=receipt.region_id,
                    region_name=world.regions[receipt.region_id].name,
                    duration=receipt.requested_duration, prior_counter=receipt.prior_counter,
                    effective_counter=receipt.effective_counter,
                    effective_through_turn=receipt.effective_through_turn)
                limits[1] = "One regional transport disruption; 1–20 additional turns, simulation only."
            if is_academy:
                receipt = preview_academy(world, civ, stat, value)
                req = receipt.request
                if not receipt.changed or req.region_id != msg["region_id"]:
                    raise WhatIfError("Academy restoration is no longer eligible")
                old = world.scholarship.seats[req.fallen_seat_id]
                intervention.update(scope="academy", region_id=req.region_id,
                    region_name=world.regions[req.region_id].name, fallen_seat_id=req.fallen_seat_id,
                    fallen_seat_name=old.name, fallen_founder=req.fallen_founder,
                    fallen_founded_turn=req.fallen_founded_turn, fallen_turn=req.fallen_turn,
                    current_lord=req.current_lord, current_lord_name=world.civilizations[req.current_lord].name,
                    fee=receipt.fee, treasury_before=receipt.treasury_before, treasury_after=receipt.treasury_after)
                limits[1] = "One eligible paid academy restoration; 1–20 additional turns, simulation only."
                validate_academy_checkpoint(checkpoint, intervention)
            manifest = {"schema_version": 4 if is_academy else 3 if is_transport else 2 if is_policy else 1, "request_id": request_id,
                        "source": {"checkpoint": artifact_identity(checkpoint), "header": header,
                                   "current_identity": fresh_identity()},
                        "mode": config.get("simulation_args", {}).get("agents", "off"),
                        "seed": header["seed"], "start_turn": world.turn,
                        "end_turn": world.turn + turns, "turns": turns,
                        "intervention": intervention,
                        "semantics": "exact_checkpoint_pair", "limits": limits,
                        "bounds": {"arm_seconds": ARM_TIMEOUT_SECONDS, "bundle_bytes": MAX_BUNDLE_BYTES}}
            job = Job(directory, manifest)
            self._persist(job)  # Durable plan precedes status and every launch.
            self.jobs[request_id] = job
            return self._status(job)

    def run(self, request_id: str) -> None:
        with self._lock:
            job = self.jobs.get(request_id)
            if job is None:
                raise WhatIfError("Prepare this request before running it")
            if job.state != "prepared":
                self._status(job)
                if job.result is not None:
                    self.status_queue.put(copy.deepcopy(job.result))
                return
            if self._closed:
                raise WhatIfError("The live session has closed")
            job.state = "running"
            self._persist(job)
            job.thread = threading.Thread(target=self._execute, args=(job,), daemon=True,
                                          name="chronicler-what-if")
            job.thread.start()

    def cancel(self, request_id: str) -> None:
        with self._lock:
            job = self.jobs.get(request_id)
            if job is None:
                raise WhatIfError("Unknown what-if request")
            if job.state not in {"prepared", "running"}:
                self._status(job)
                return
            job.cancel.set()
            thread = job.thread
            if thread is None:
                job.state, job.message = "cancelled", "Cancelled before execution; private files retained"
                self._persist(job)
                self._status(job)
        if thread is not None:
            thread.join(timeout=5)
            if thread.is_alive():
                raise WhatIfError("What-if worker did not acknowledge cancellation")

    def close(self) -> None:
        with self._lock:
            self._closed = True
            ids = [key for key, job in self.jobs.items() if job.state in {"prepared", "running"}]
        for request_id in ids:
            self.cancel(request_id)

    @staticmethod
    def _kill_group(process: subprocess.Popen) -> None:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait(timeout=3)

    def _child(self, job: Job, arm: str) -> dict:
        m, checkpoint = job.manifest, job.directory / "common.ckpt"
        require_hash_seed()
        verified_header(checkpoint, turn=m["start_turn"], seed=m["seed"])
        if artifact_identity(checkpoint) != m["source"]["checkpoint"]:
            raise WhatIfError("Common checkpoint changed after preparation")
        if job.cancel.is_set():
            raise InterruptedError("Cancelled")
        directory = job.directory / arm
        directory.mkdir()
        end = m["end_turn"]
        command = [sys.executable, "-m", "chronicler.main", "--interactive", "--resume", str(checkpoint),
                   "--simulate-only", "--turns", str(end), "--pause-every", str(end + 1),
                   "--output", str(directory / "chronicle.md"), "--state", str(directory / "state.json"),
                   "--checkpoint-every", "1", "--checkpoint", str(directory / "final.ckpt")]
        script = "continue\n"
        if arm == "intervention":
            intervention = intervention_command(m["intervention"])
            if m["schema_version"] == 4:
                if intervention["civ"] != ACADEMY_TARGET or intervention["stat"] != ACADEMY_STAT:
                    raise WhatIfError("Academy manifest requires the restoration command")
                validate_academy_checkpoint(checkpoint, m["intervention"])
            if m["schema_version"] == 3 and (intervention["civ"] != TRANSPORT_TARGET or
                                               intervention["stat"] != TRANSPORT_STAT):
                raise WhatIfError("Transport manifest requires the regional transport command")
            script = f"set {shlex.quote(intervention['civ'])} {intervention['stat']} {intervention['value']}\n" + script
        env = os.environ.copy()  # Same seed/thread env/config, no override flags.
        env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1]) + os.pathsep + env.get("PYTHONPATH", "")
        log_path = directory / "process.log"
        with log_path.open("xb") as log:
            process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=log, stderr=subprocess.STDOUT,
                                       env=env, start_new_session=True)
            with self._lock:
                job.process = process
            started = time.monotonic()
            try:
                process.stdin.write(script.encode())
                process.stdin.close()
                while process.poll() is None:
                    if job.cancel.wait(0.05):
                        raise InterruptedError("Cancelled")
                    if time.monotonic() - started > ARM_TIMEOUT_SECONDS:
                        raise WhatIfError(f"{arm} exceeded its {ARM_TIMEOUT_SECONDS}s time limit")
                    _check_output_limits(directory, log_path, arm, running=True)
                if job.cancel.is_set():
                    raise InterruptedError("Cancelled")
                if process.returncode != 0:
                    raise WhatIfError(f"{arm} CLI failed (exit {process.returncode}); private process.log retained")
            finally:
                self._kill_group(process)
                with self._lock:
                    job.process = None
        final = verified_header(directory / "final.ckpt", turn=end, seed=m["seed"])
        _check_output_limits(directory, log_path, arm)
        expected = list(m["source"]["header"].get("run_config", {}).get("interventions", []))
        if arm == "intervention":
            expected.append({"turn": m["start_turn"], **intervention_command(m["intervention"])})
        if final.get("run_config", {}).get("interventions", []) != expected:
            raise WhatIfError(f"{arm} intervention record differs from the declared control")
        bundle_path = directory / "chronicle_bundle.json"
        if not bundle_path.is_file() or bundle_path.stat().st_size > MAX_BUNDLE_BYTES:
            raise WhatIfError(f"{arm} bundle is missing or exceeds 16 MiB")
        bundle = decode_bundle(json.loads(bundle_path.read_text(encoding="utf-8")))
        if len(json.dumps(bundle, ensure_ascii=False).encode("utf-8")) > MAX_BUNDLE_BYTES:
            raise WhatIfError(f"{arm} decoded bundle exceeds 16 MiB")
        if (bundle.get("metadata", {}).get("total_turns") != end or
                bundle.get("world_state", {}).get("turn") != end or
                bundle.get("metadata", {}).get("seed") != m["seed"] or
                bundle.get("world_state", {}).get("seed") != m["seed"]):
            raise WhatIfError(f"{arm} bundle did not finish the declared horizon")
        tag = {k: copy.deepcopy(m[k]) for k in ("schema_version", "request_id", "source", "mode", "seed",
                                               "start_turn", "end_turn", "turns", "intervention", "semantics", "limits", "bounds")}
        tag["arm"] = arm
        bundle["metadata"]["what_if"] = tag
        encoded = dumps_bundle(bundle)
        if len(encoded.encode("utf-8")) > MAX_BUNDLE_BYTES:
            raise WhatIfError(f"{arm} tagged bundle exceeds 16 MiB")
        atomic_write_text(bundle_path, encoded)
        return {"bundle": bundle, "identity": artifact_identity(bundle_path)}

    def _execute(self, job: Job) -> None:
        try:
            results = {}
            for arm in ("baseline", "intervention"):
                with self._lock:
                    if job.cancel.is_set():
                        raise InterruptedError("Cancelled")
                    job.arm = arm
                    self._persist(job)
                    self._status(job)
                results[arm] = self._child(job, arm)
            with self._lock:
                if job.cancel.is_set():
                    raise InterruptedError("Cancelled")
                job.state, job.arm = "complete", None
                job.manifest["artifacts"] = {
                    arm: {"path": f"{arm}/chronicle_bundle.json", "identity": result["identity"]}
                    for arm, result in results.items()}
                job.result = {"type": "what_if_result", "request_id": job.manifest["request_id"],
                              "manifest": copy.deepcopy(job.manifest), **results}
                self._persist(job)
                self._status(job)
                self.status_queue.put(copy.deepcopy(job.result))
        except Exception as exc:
            with self._lock:
                job.state = "cancelled" if job.cancel.is_set() or isinstance(exc, InterruptedError) else "error"
                job.message = f"{exc}; private files retained"
                self._persist(job)
                self._status(job)
