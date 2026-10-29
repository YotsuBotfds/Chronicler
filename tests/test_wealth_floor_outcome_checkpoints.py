"""Tiny synthetic checkpoint-envelope contracts; no state section is decoded."""
from contextlib import contextmanager
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import stat
import struct

import pytest

from scripts import wealth_floor_outcome_checkpoints as K


def config(worldgen="template", profile="subset"):
    procedural = worldgen == "procedural"
    turns = 125 if profile == "subset" else (300 if procedural else 500)
    return dict(worldgen=worldgen, profile=profile, turns=turns,
        seed_count=2 if profile == "subset" else (100 if procedural else 200),
        seed_start=42, regions=32 if procedural else 8, civs=10 if procedural else 4,
        parallel=2, checkpoint_turns=[t + 1 for t in range(100, turns - 20, 20 if procedural else 100)])


def header(cfg=None, seed=42, turn=101):
    cfg = config() if cfg is None else cfg
    return dict(format="chronicler-run-checkpoint", version=1, exact=True,
        seed=seed, turn=turn, num_turns=cfg["turns"], start_turn=0, lineage=[],
        identity=dict(source=dict(git_sha=K.B.CANDIDATE_SOURCE, package_digest=K.PACKAGE),
            native=dict(sha256=K.P.REVIEWED_BUILD["candidate_native_sha256"],
                state_layouts=dict(agent="v1:dcf0c34097c88451")),
            environment=dict(python=K.B.PYTHON_VERSION, implementation="CPython",
                affinity_cpu_count=2, thread_env=dict(K.THREADS))),
        world=dict(regions=cfg["regions"], civilizations=cfg["civs"]),
        run_config=dict(agent_mode="hybrid", validation_sidecar=True, lineage=[], resume_info=None),
        sections=[dict(name="python", offset=0, length=7),
            dict(name="native.agent.0", offset=7, length=8)])


def envelope(value=None, body=b"FAKEPY!FAKENAT!"):
    """The bytes deliberately are neither pickle nor compressed native state."""
    value = header() if value is None else value
    raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return K.MAGIC + struct.pack("<I", len(raw)) + raw + body


def write_checkpoint(root, cfg=None, seed=42, turn=101, value=None):
    cfg = config() if cfg is None else cfg
    profile = "oracle_subset" if cfg["profile"] == "subset" else "full_gate"
    path = root / "raw" / profile / "batch_42" / f"seed_{seed}" / f"checkpoint_turn_{turn}.ckpt"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(envelope(header(cfg, seed, turn) if value is None else value))
    return path


def prepare(root, cfg=None):
    cfg = config() if cfg is None else cfg
    paths = [write_checkpoint(root, cfg, seed, turn)
        for seed in range(42, 42 + cfg["seed_count"]) for turn in cfg["checkpoint_turns"]]
    return cfg, paths, paths[0].parent.parent


def strict_compare(actual, expected, native_required):
    assert native_required is True
    return [] if actual == expected else ["synthetic identity mismatch"]


def capture(root, cfg=None):
    cfg, paths, batch = prepare(root, cfg)
    index, seal = K.capture(root, batch, cfg, header(cfg)["identity"], strict_compare)
    return cfg, paths, batch, index, seal


@pytest.mark.parametrize("worldgen,profile,count", [
    ("template", "subset", 2), ("procedural", "subset", 2),
    ("template", "full", 800), ("procedural", "full", 900),
])
def test_fixed_production_boundaries_are_registered_without_creating_worlds(worldgen, profile, count):
    cfg = config(worldgen, profile)
    assert K.expected_turns(cfg) == cfg["checkpoint_turns"]
    assert cfg["seed_count"] * len(K.expected_turns(cfg)) == count


@pytest.mark.parametrize("key,value", [
    ("worldgen", "unknown"), ("profile", "other"), ("seed_start", 7),
    ("seed_count", 3), ("seed_count", True), ("seed_count", 10**15),
    ("turns", 126), ("parallel", 1), ("regions", 32), ("civs", 10),
    ("checkpoint_turns", [100]), ("checkpoint_turns", (101,)),
])
def test_wrong_coverage_is_refused_before_path_expansion(key, value):
    cfg = config(); cfg[key] = value
    with pytest.raises(K.P.ProofRefused):
        K.expected_turns(cfg)


def test_inspect_hashes_every_byte_and_never_decodes_state(tmp_path, monkeypatch):
    path = write_checkpoint(tmp_path)
    raw = path.read_bytes(); reads = []
    original = K.P.regular

    @contextmanager
    def recorded(root, name):
        with original(root, name) as (stream, info):
            class Reader:
                def read(self, size):
                    reads.append(size)
                    return stream.read(size)
            yield Reader(), info

    monkeypatch.setattr(K.P, "regular", recorded)
    row = K.inspect(tmp_path, path.relative_to(tmp_path).as_posix())
    assert row["bytes"] == len(raw) and row["sha256"] == hashlib.sha256(raw).hexdigest()
    assert row["header"] == header() and row["file_identity"] == K.identity(path.stat())
    assert reads and set(reads) == {1024 * 1024}


@pytest.mark.parametrize("case", ["empty", "magic", "short", "oversized_header", "truncated_header",
    "duplicate_key", "nonfinite", "section_offset", "section_length", "trailing_bytes"])
def test_malformed_envelopes_are_refused_without_section_decoding(tmp_path, case):
    raw = envelope()
    if case == "empty": raw = b""
    elif case == "magic": raw = b"wrong" + raw
    elif case == "short": raw = K.MAGIC + b"\x01"
    elif case == "oversized_header": raw = K.MAGIC + struct.pack("<I", 65537) + b"{}"
    elif case == "truncated_header": raw = K.MAGIC + struct.pack("<I", 1024) + b"{}"
    elif case in ("duplicate_key", "nonfinite"):
        bad = b'{"sections":[],"x":1,"x":2}' if case == "duplicate_key" else b'{"sections":[],"x":NaN}'
        raw = K.MAGIC + struct.pack("<I", len(bad)) + bad
    elif case == "section_offset":
        value = header(); value["sections"][1]["offset"] = 8; raw = envelope(value)
    elif case == "section_length":
        value = header(); value["sections"][0]["length"] = True; raw = envelope(value)
    elif case == "trailing_bytes": raw += b"extra"
    path = tmp_path / "fixture.ckpt"; path.write_bytes(raw)
    with pytest.raises(K.P.ProofRefused):
        K.inspect(tmp_path, path.name)
    assert path.read_bytes() == raw


def test_checkpoint_member_limit_is_checked_before_streaming(tmp_path, monkeypatch):
    path = write_checkpoint(tmp_path)
    monkeypatch.setattr(K, "MAX_CHECKPOINT", path.stat().st_size - 1)
    with pytest.raises(K.P.ProofRefused, match="cap"):
        K.inspect(tmp_path, path.relative_to(tmp_path).as_posix(), lambda: pytest.fail("streamed before cap"))


@pytest.mark.parametrize("case", ["old_source", "wrong_package", "old_native", "python", "implementation",
    "affinity", "affinity_bool", "thread_cap", "missing_cap", "hash_seed", "world", "mode", "sidecar",
    "version_bool", "seed", "turn", "horizon", "start", "sections", "header_lineage", "run_lineage", "resume"])
def test_checkpoint_header_requires_actual_fresh_candidate_context(case):
    h = header(); identity = h["identity"]; env = identity["environment"]; run = h["run_config"]
    if case == "old_source": identity["source"]["git_sha"] = K.B.BASELINE_SOURCE
    elif case == "wrong_package": identity["source"]["package_digest"] = "0" * 64
    elif case == "old_native": identity["native"]["sha256"] = K.B.OLD_NATIVE
    elif case == "python": env["python"] = "3.13.5"
    elif case == "implementation": env["implementation"] = "other"
    elif case == "affinity": env["affinity_cpu_count"] = 4
    elif case == "affinity_bool": env["affinity_cpu_count"] = True
    elif case == "thread_cap": env["thread_env"]["VECLIB_MAXIMUM_THREADS"] = "2"
    elif case == "missing_cap": env["thread_env"].pop("RAYON_NUM_THREADS")
    elif case == "hash_seed": env["thread_env"]["PYTHONHASHSEED"] = "1"
    elif case == "world": h["world"]["regions"] = 32
    elif case == "mode": run["agent_mode"] = "off"
    elif case == "sidecar": run["validation_sidecar"] = False
    elif case == "version_bool": h["version"] = True
    elif case == "seed": h["seed"] = 43
    elif case == "turn": h["turn"] = 100
    elif case == "horizon": h["num_turns"] = 126
    elif case == "start": h["start_turn"] = 1
    elif case == "sections": h["sections"] = h["sections"][:1]
    elif case == "header_lineage": h["lineage"] = [{"turn": 1}]
    elif case == "run_lineage": run["lineage"] = [{"turn": 1}]
    elif case == "resume": run["resume_info"] = {"exact": True}
    with pytest.raises(K.P.ProofRefused):
        K.validate_header(h, config(), 42, 101)


@pytest.mark.parametrize("kind", ["leaf_symlink", "parent_symlink", "hardlink"])
def test_inspect_refuses_linked_originals(tmp_path, kind):
    path = write_checkpoint(tmp_path); relative = path.relative_to(tmp_path).as_posix()
    if kind == "leaf_symlink":
        moved = path.with_name("moved"); path.rename(moved); path.symlink_to(moved)
    elif kind == "parent_symlink":
        moved = path.parent.with_name("moved"); path.parent.rename(moved); path.parent.symlink_to(moved, target_is_directory=True)
    else:
        os.link(path, path.with_name("alias"))
    with pytest.raises((OSError, K.P.ProofRefused)):
        K.inspect(tmp_path, relative)


def test_capture_publishes_durable_complete_index_before_return(tmp_path, monkeypatch):
    cfg, paths, batch = prepare(tmp_path); events = []
    fsync, replace = K.os.fsync, K.os.replace

    def sync(fd):
        events.append("dir_sync" if stat.S_ISDIR(os.fstat(fd).st_mode) else "file_sync")
        return fsync(fd)

    def publish(before, after):
        events.append("replace_index" if Path(after).name == "candidate-checkpoint-index.json" else "replace")
        return replace(before, after)

    monkeypatch.setattr(K.os, "fsync", sync); monkeypatch.setattr(K.os, "replace", publish)
    calls = []
    def compare(actual, expected, native):
        calls.append((deepcopy(actual), deepcopy(expected), native))
        return strict_compare(actual, expected, native)
    index, seal = K.capture(tmp_path, batch, cfg, header()["identity"], compare)
    raw = (tmp_path / "candidate-checkpoint-index.json").read_bytes()
    assert seal == hashlib.sha256(raw).hexdigest() and K.P.parse(raw) == index
    assert index["capture_complete"] is True and index["checkpoint_count"] == 2
    assert [r["seed"] for r in index["checkpoints"]] == [42, 43]
    assert all(c[2] is True for c in calls) and len(calls) == 2
    assert events.index("file_sync") < events.index("replace_index") < events.index("dir_sync")
    assert all(path.exists() for path in paths)


def test_capture_partial_failure_keeps_completed_journal_and_every_body(tmp_path):
    cfg, paths, batch = prepare(tmp_path)
    h = header(cfg, 43); h["lineage"] = [{"turn": 1}]; paths[1].write_bytes(envelope(h))
    with pytest.raises(K.P.ProofRefused, match="lineage"):
        K.capture(tmp_path, batch, cfg, header()["identity"], strict_compare)
    rows = [K.P.parse(line) for line in (tmp_path / "candidate-checkpoint-capture.jsonl").read_bytes().splitlines()]
    assert len(rows) == 1 and rows[0]["seed"] == 42
    assert not (tmp_path / "candidate-checkpoint-index.json").exists()
    assert all(path.exists() for path in paths)


def test_strict_current_layout_mismatch_cannot_be_relabelled_as_captured(tmp_path):
    cfg, paths, batch = prepare(tmp_path)
    identity = header()["identity"]; identity["native"]["state_layouts"]["agent"] = "different"
    with pytest.raises(K.P.ProofRefused, match="strict current"):
        K.capture(tmp_path, batch, cfg, identity, strict_compare)
    assert not (tmp_path / "candidate-checkpoint-index.json").exists() and all(p.exists() for p in paths)


def test_capture_refuses_nonproduction_batch_path(tmp_path):
    cfg, paths, batch = prepare(tmp_path)
    with pytest.raises(K.P.ProofRefused, match="batch path"):
        K.capture(tmp_path, batch.parent, cfg, header()["identity"], strict_compare)
    assert all(p.exists() for p in paths)


def test_durable_index_cap_refuses_before_creating_pending_file(tmp_path, monkeypatch):
    monkeypatch.setattr(K, "MAX_INDEX", 16)
    with pytest.raises(K.P.ProofRefused, match="index cap"):
        K.durable_json(tmp_path / "index.json", {"large": "x" * 32})
    assert list(tmp_path.iterdir()) == []


def test_successful_retirement_rechecks_all_before_any_unlink(tmp_path, monkeypatch):
    cfg, paths, batch, index, seal = capture(tmp_path); events = []
    inspect, unlink = K.inspect, K.unlink_original
    def checked(root, name, check):
        events.append(("checked", name)); return inspect(root, name, check)
    def removed(root, name, identity):
        assert len([x for x in events if x[0] == "checked"]) == 2
        assert json.loads((tmp_path / "checkpoint-retirement.json").read_text())["all_files_rechecked"] is True
        events.append(("unlink", name)); return unlink(root, name, identity)
    monkeypatch.setattr(K, "inspect", checked); monkeypatch.setattr(K, "unlink_original", removed)
    status = K.retire(tmp_path, index, seal)
    assert status["retirement_complete"] is True and status["retired"] == [r["path"] for r in index["checkpoints"]]
    assert status["incomplete_retired_list_may_be_nonexhaustive"] is False
    assert all(not path.exists() for path in paths)
    assert [kind for kind, _ in events] == ["checked", "checked", "unlink", "unlink"]


@pytest.mark.parametrize("case", ["body_mutation", "truncated", "missing", "new_inode"])
def test_second_checkpoint_failure_prevents_the_first_unlink(tmp_path, case):
    cfg, paths, batch, index, seal = capture(tmp_path)
    second = paths[1]
    if case == "body_mutation":
        raw = second.read_bytes(); second.write_bytes(raw[:-1] + bytes([raw[-1] ^ 1]))
    elif case == "truncated": second.write_bytes(second.read_bytes()[:-1])
    elif case == "missing": second.unlink()
    else:
        raw = second.read_bytes(); moved = second.with_name("replacement"); moved.write_bytes(raw); os.replace(moved, second)
    with pytest.raises((OSError, K.P.ProofRefused)):
        K.retire(tmp_path, index, seal)
    assert paths[0].exists() and not (tmp_path / "checkpoint-retirement.jsonl").exists()


def test_changed_durable_index_cannot_authorize_any_retirement(tmp_path):
    cfg, paths, batch, index, seal = capture(tmp_path)
    with (tmp_path / "candidate-checkpoint-index.json").open("ab") as stream: stream.write(b"\n")
    with pytest.raises(K.P.ProofRefused, match="index changed"):
        K.retire(tmp_path, index, seal)
    assert all(p.exists() for p in paths)


@pytest.mark.parametrize("case", ["omitted", "duplicate", "foreign_path", "batch"])
def test_even_resealed_incomplete_or_foreign_index_cannot_delete(tmp_path, case):
    cfg, paths, batch, index, seal = capture(tmp_path)
    if case == "omitted": index["checkpoints"].pop(); index["checkpoint_count"] = 1
    elif case == "duplicate": index["checkpoints"][1] = deepcopy(index["checkpoints"][0])
    elif case == "foreign_path": index["checkpoints"][1]["path"] = "unrelated.ckpt"
    else: index["batch_relative"] = "raw/full_gate/batch_42"
    seal = K.durable_json(tmp_path / "candidate-checkpoint-index.json", index)
    with pytest.raises(K.P.ProofRefused):
        K.retire(tmp_path, index, seal)
    assert all(p.exists() for p in paths)


def test_parent_symlink_swap_after_verification_cannot_delete_original(tmp_path, monkeypatch):
    cfg, paths, batch, index, seal = capture(tmp_path)
    original = K.unlink_original; moved = tmp_path / "moved-original-seed"
    def swapped(root, name, identity):
        parent = paths[0].parent
        parent.rename(moved); parent.symlink_to(moved, target_is_directory=True)
        return original(root, name, identity)
    monkeypatch.setattr(K, "unlink_original", swapped)
    with pytest.raises((OSError, K.P.ProofRefused)):
        K.retire(tmp_path, index, seal)
    assert (moved / paths[0].name).exists() and paths[1].exists()
    status = json.loads((tmp_path / "checkpoint-retirement.json").read_text())
    assert status["retirement_complete"] is False and status["retired"] == []


def test_partial_unlink_failure_is_journalled_and_survivor_stays_original(tmp_path, monkeypatch):
    cfg, paths, batch, index, seal = capture(tmp_path)
    original = K.unlink_original; calls = []
    def fail_second(root, name, identity):
        calls.append(name)
        if len(calls) == 2: raise OSError("synthetic second unlink refusal")
        return original(root, name, identity)
    monkeypatch.setattr(K, "unlink_original", fail_second)
    with pytest.raises(OSError, match="second unlink"):
        K.retire(tmp_path, index, seal)
    status = json.loads((tmp_path / "checkpoint-retirement.json").read_text())
    assert status["retirement_complete"] is False and status["retired"] == [index["checkpoints"][0]["path"]]
    assert status["error_type"] == "OSError" and status["incomplete_retired_list_may_be_nonexhaustive"] is True
    assert not paths[0].exists() and paths[1].exists()
    events = [json.loads(line)["event"] for line in (tmp_path / "checkpoint-retirement.jsonl").read_text().splitlines()]
    assert events == ["unlink_intent", "unlink_complete", "unlink_intent"]


def test_failure_selection_keeps_originals_and_marks_publication_pending(tmp_path, monkeypatch):
    cfg, paths, batch = prepare(tmp_path); original = K.P.regular
    @contextmanager
    def no_body_read(root, name):
        with original(root, name) as (_stream, info):
            class NoRead:
                def read(self, *_args): pytest.fail("failure selection decoded/read a body")
            yield NoRead(), info
    monkeypatch.setattr(K.P, "regular", no_body_read)
    value = K.failure_body_selection(tmp_path, batch, cfg, clock=lambda: 0)
    assert value["failed_producer"] is True and value["publication_complete"] is None
    assert value["publication_status"].startswith("pending") and value["selection_complete_for_remaining_verified_files"] is True
    assert len(value["selected"]) == 2 and value["omitted"] == value["missing_or_already_retired"] == []
    assert all(r["current_body_sha256"] is None for r in value["selected"])
    assert value["selected_bytes"] == sum(p.stat().st_size for p in paths) and all(p.exists() for p in paths)


def test_failure_selection_size_prefix_is_bounded_and_omissions_explicit(tmp_path, monkeypatch):
    cfg, paths, batch = prepare(tmp_path)
    monkeypatch.setattr(K, "MAX_FAILED_BODY_BYTES", paths[0].stat().st_size)
    value = K.failure_body_selection(tmp_path, batch, cfg, clock=lambda: 0)
    assert [r["path"] for r in value["selected"]] == [paths[0].relative_to(tmp_path).as_posix()]
    assert value["selection_complete_for_remaining_verified_files"] is False
    assert value["omitted"] == [dict(path=paths[1].relative_to(tmp_path).as_posix(),
        bytes=paths[1].stat().st_size, reason="failure_artifact_size_prefix_bound")]
    assert all(p.exists() for p in paths)


def test_failure_selection_deadline_does_not_claim_unobserved_bodies_preserved(tmp_path):
    cfg, paths, batch = prepare(tmp_path); times = iter([0, 0, 3])
    value = K.failure_body_selection(tmp_path, batch, cfg, clock=lambda: next(times))
    assert len(value["selected"]) == 1 and value["selection_complete_for_remaining_verified_files"] is False
    assert value["omitted"] == [dict(path=paths[1].relative_to(tmp_path).as_posix(),
        reason="failure_selection_deadline", bytes=None)]
    assert all(p.exists() for p in paths)


def test_failure_selection_records_missing_and_refuses_links_without_following(tmp_path):
    cfg, paths, batch = prepare(tmp_path)
    paths[0].unlink(); moved = paths[1].with_name("original"); paths[1].rename(moved); paths[1].symlink_to(moved)
    value = K.failure_body_selection(tmp_path, batch, cfg, clock=lambda: 0)
    assert value["selected"] == [] and value["selected_bytes"] == 0
    assert value["missing_or_already_retired"] == [paths[0].relative_to(tmp_path).as_posix()]
    assert value["omitted"] == [dict(path=paths[1].relative_to(tmp_path).as_posix(),
        reason="not_verified_regular_original", bytes=None)]
    assert moved.exists()
