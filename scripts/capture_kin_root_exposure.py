"""Opt-in, one-turn acquisition from a current exact first-fork checkpoint.

Default invocation imports no simulation modules and executes no simulation.
The ordinary resume's exports still require external whole-worker admission;
the bounds below cover admitted input and this driver's own artifacts only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import stat
from types import SimpleNamespace

FORK_TURN = 100
SOURCE_TURN = 101
PARENT_HORIZON = 500
SEED = 42
MAX_CHECKPOINT_BYTES = 64 * 1024 * 1024
MAX_CHECKPOINT_RAW_BYTES = 128 * 1024 * 1024
MAX_SIDECAR_ROWS = 262144
MAX_FORK_ROWS = 65536
MAX_FRAME_BYTES = 32 * 1024 * 1024 + 65536
MAX_COHORT_BYTES = 1024 * 1024
MAX_REPORT_BYTES = 65536
MIN_TMP_FREE = 3 * 1024 * 1024 * 1024
_PROJECTIONS = (
    ("relationship_columns", "_relationship_rows", ("turn", "agent_id", "target_id", "bond_type", "sentiment")),
    ("memory_columns", "_memory_rows", ("turn", "agent_id", "event_type", "memory_turn", "valence_sign")),
    ("needs_columns", "_needs_rows", ("turn", "agent_id", "region")),
)


def _require(condition, reason):
    if not condition:
        raise ValueError(reason)


def _pin(path, limit):
    info = path.lstat()
    _require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_size <= limit,
             "checkpoint_file_limit")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return {"bytes": info.st_size, "sha256": digest.hexdigest()}


def _write(path, payload, limit):
    body = (json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()
    _require(len(body) <= limit, "driver_artifact_limit")
    with path.open("xb") as output:
        output.write(body)
    return {"file": path.name, "bytes": len(body), "sha256": hashlib.sha256(body).hexdigest()}


def _header(header):
    _require(header["turn"] == SOURCE_TURN and header["seed"] == SEED
             and header["num_turns"] == PARENT_HORIZON and header["exact"] is True,
             "first_fork_checkpoint")
    world = header["world"]
    _require(world["regions"] == 8 and world["civilizations"] == 4
             and world["geography"] is False, "template_checkpoint")
    sections = header["sections"]
    _require(type(sections) is list and 1 <= len(sections) <= 16, "checkpoint_sections")
    _require(all(type(row["raw_length"]) is int and row["raw_length"] >= 0 for row in sections)
             and sum(row["raw_length"] for row in sections) <= MAX_CHECKPOINT_RAW_BYTES,
             "checkpoint_raw_limit")


def _cohort(sidecar, oracle_snapshot):
    """Project real checkpoint-carried sidecar values for existing method 2."""
    buffers = [getattr(sidecar, name, None) for _, name, _ in _PROJECTIONS]
    _require(all(type(rows) is list for rows in buffers)
             and sum(map(len, buffers)) <= MAX_SIDECAR_ROWS, "checkpoint_sidecar_limit")
    run = {}
    fork_rows = 0
    for (name, _, fields), rows in zip(_PROJECTIONS, buffers):
        columns = {field: [] for field in fields}
        for row in rows:
            _require(type(row) is dict and type(row.get("turn")) is int, "sidecar_row")
            if row["turn"] != FORK_TURN:
                continue
            fork_rows += 1
            _require(fork_rows <= MAX_FORK_ROWS, "fork_sidecar_limit")
            for field in fields:
                value = row[field]
                _require(type(value) is int, "sidecar_value")
                columns[field].append(value)
        run[name] = columns
    alive_ids = run["needs_columns"]["agent_id"]
    _require(alive_ids and len(set(alive_ids)) == len(alive_ids)
             and all(0 <= value < 2**32 for value in alive_ids), "fork_alive_ids")
    snapshot = oracle_snapshot(run, FORK_TURN)
    _require(snapshot is not None, "fork_membership_unavailable")
    alive = set(alive_ids)
    members = set()
    for group in snapshot["communities"]:
        _require(all(type(value) is int and 0 <= value < 2**32 for value in group), "community_ids")
        members.update(group)
    members &= alive
    ids = sorted(members)
    _require(len(ids) <= MAX_FORK_ROWS, "member_selection_limit")
    return {"kind": "CHECKPOINT_FORK_COHORT", "fork_turn": FORK_TURN,
        "cohort_method_version": 6, "community_method_version": 2,
        "source": "strict checkpoint-carried SidecarWriter rows at fork turn",
        "member_ids": ids, "members_at_fork": len(ids), "alive_at_fork": len(alive),
        "nonmembers_at_fork": len(alive) - len(ids), "projected_rows": fork_rows,
        "nonmember_decision_rows_captured": False}


def _load_runtime():
    # These imports occur only after explicit opt-in, never at module import.
    from chronicler import main, run_checkpoint
    from chronicler.decision_delivery import DecisionDeliveryObserver
    from chronicler.kin_root_exposure import summarize_kin_root_exposure
    from chronicler.validation_communities import oracle1_snapshot

    return SimpleNamespace(read_header=run_checkpoint.read_header,
        load=run_checkpoint.read_checkpoint, parser=main._build_parser,
        adopt=main._adopt_checkpoint_args, execute=main.execute_run,
        retarget=run_checkpoint.retarget_outputs,
        attach=DecisionDeliveryObserver.attach, snapshot=oracle1_snapshot,
        summarize=summarize_kin_root_exposure)


def acquire(checkpoint, output, runtime):
    """One normal resumed turn. Injected dependencies permit pure fake tests."""
    checkpoint, output = Path(checkpoint), Path(output)
    _require(checkpoint.is_absolute() and output.is_absolute(), "absolute_paths")
    _require(shutil.disk_usage("/tmp").free >= MIN_TMP_FREE, "tmp_disk_floor")
    output.mkdir(exist_ok=False)
    receipt = {"kind": "KIN_ROOT_FIRST_FORK_ACQUISITION", "status": "failed",
        "source_turn": SOURCE_TURN, "parent_horizon": PARENT_HORIZON,
        "execution_attestation": None, "twenty_turn_effect_estimate": None,
        "scope": "Current checkpoint member-selected first-decision capture; no historical membership recovery or temporal efficacy claim.",
        "ordinary_resume_exports_hard_budgeted": False}
    observer = bridge = None
    returned = retargeted = False
    try:
        before = _pin(checkpoint, MAX_CHECKPOINT_BYTES)
        receipt["checkpoint"] = before
        header, _ = runtime.read_header(checkpoint)
        _header(header)
        receipt["checkpoint_context"] = _write(output / "checkpoint-context.json",
            {key: header[key] for key in ("turn", "seed", "num_turns", "world", "identity", "run_config")},
            MAX_REPORT_BYTES)
        loaded = runtime.load(checkpoint, allow_mismatch=False)
        _require(loaded.exact and not loaded.mismatches and loaded.header == header, "strict_checkpoint")
        state = loaded.state
        _require(state.seed == SEED and state.num_turns == PARENT_HORIZON
                 and state.world.turn == SOURCE_TURN and state.world.seed == SEED
                 and len(state.world.regions) == 8 and len(state.world.civilizations) == 4,
                 "loaded_first_fork")
        config = state.run_config
        _require(config == header["run_config"], "checkpoint_config_join")
        _require(config.get("agent_mode") == "hybrid" and config.get("validation_sidecar") is True
                 and config.get("decision_ablation") is None, "plain_hybrid_checkpoint")
        saved_output = config.get("output_args", {})
        _require(saved_output.get("simulate_only") is True and saved_output.get("narrator") == "local",
                 "local_simulation_checkpoint")
        bridge = state.agent_bridge
        _require(bridge is not None, "checkpoint_bridge_missing")
        cohort = _cohort(getattr(bridge, "_sidecar", None), runtime.snapshot)
        cohort["checkpoint"] = before
        receipt["cohort"] = _write(output / "cohort.json", cohort, MAX_COHORT_BYTES)
        parser = runtime.parser()
        args = parser.parse_args(["--resume", str(checkpoint), "--turns", str(PARENT_HORIZON),
            "--simulate-only", "--state-every", str(PARENT_HORIZON),
            "--output", str(output / "run/chronicle.md"), "--state", str(output / "run/state.json")])
        _require(not runtime.adopt(parser, args, loaded) and args.turns == PARENT_HORIZON,
                 "checkpoint_args_conflict")
        # A failure must never flush restored sidecars back into the parent.
        runtime.retarget(state, output / "run", None)
        retargeted = True
        observer = runtime.attach(bridge, selected_agent_ids=cohort["member_ids"],
            max_agent_rows=4096, max_candidate_rows=16384, max_move_rows=16384,
            max_retained_bytes=8 * 1024 * 1024)
        attempts = 0

        def on_turn(*_):
            nonlocal attempts
            attempts += 1
            _require(attempts == 1, "unexpected_extra_turn")
            readout = observer.read_latest(expected_source_turn=SOURCE_TURN)
            receipt["readout"] = {"status": readout.status, "reason": readout.reason,
                "source_turn": readout.source_turn, "native_event_count": readout.native_event_count,
                "applied_event_links_checked": readout.applied_event_links_checked}
            if readout.status != "captured":
                headers = {name: value.to_pylist() for name in ("decision_header", "move_header")
                    if (value := getattr(readout, name, None)) is not None}
                if headers:
                    receipt["unavailable_headers"] = _write(output / "unavailable-headers.json", headers,
                        MAX_REPORT_BYTES)
            _require(readout.status == "captured" and readout.source_turn == SOURCE_TURN,
                     "capture_unavailable")
            wire = {"decision_header": readout.decision_header.to_pylist()[0],
                "decision_rows": readout.decisions.to_pylist(), "candidate_rows": readout.candidates.to_pylist(),
                "move_header": readout.move_header.to_pylist()[0], "move_rows": readout.moves.to_pylist()}
            receipt["wire"] = _write(output / "wire.json", wire, MAX_FRAME_BYTES)
            report = runtime.summarize(**wire)
            receipt["exposure"] = _write(output / "exposure.json", report, MAX_REPORT_BYTES)
            receipt["capture_status"] = report["status"]

        _require(_pin(checkpoint, MAX_CHECKPOINT_BYTES) == before, "checkpoint_changed")
        _require(shutil.disk_usage("/tmp").free >= MIN_TMP_FREE, "tmp_disk_floor")
        runtime.execute(args, checkpoint_resume=loaded, on_turn=on_turn, quit_check=lambda: True)
        returned = True
        _require(attempts == 1 and state.world.turn == SOURCE_TURN + 1, "one_turn_required")
        _require(_pin(checkpoint, MAX_CHECKPOINT_BYTES) == before, "checkpoint_changed")
        _require(shutil.disk_usage("/tmp").free >= MIN_TMP_FREE, "tmp_disk_floor")
        receipt["status"] = "captured"
    except Exception as exc:
        receipt["error"] = {"type": type(exc).__name__, "message": str(exc)[:512]}
    finally:
        errors = []
        if observer is not None:
            try:
                closed = observer.close()
                if closed.reason == "disable_failed":
                    errors.append("observer_disable_failed")
            except Exception as exc:
                errors.append(type(exc).__name__ + ": " + str(exc)[:256])
        if bridge is not None and retargeted and not returned:
            try:
                bridge.close()
            except Exception as exc:
                errors.append(type(exc).__name__ + ": " + str(exc)[:256])
        if errors:
            receipt["status"], receipt["cleanup_errors"] = "failed", errors
        _write(output / "receipt.json", receipt, MAX_REPORT_BYTES)
    return receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--enable-acquisition", action="store_true")
    parser.add_argument("--checkpoint", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    if not args.enable_acquisition:
        print('{"kind":"KIN_ROOT_FIRST_FORK_ACQUISITION","status":"disabled"}')
        return 0
    if args.checkpoint is None or args.output is None:
        parser.error("enabled acquisition requires --checkpoint and a fresh absolute --output")
    result = acquire(args.checkpoint, args.output, _load_runtime())
    print(json.dumps({"status": result["status"], "source_turn": SOURCE_TURN}, sort_keys=True))
    return 0 if result["status"] == "captured" else 2


if __name__ == "__main__":
    raise SystemExit(main())
