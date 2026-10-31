"""Exact run checkpoints (chronicler.run_checkpoint): resume identity,
envelope integrity, build refusal and its override, CLI and legacy labels.

Pure-Python lane: the native ecology/politics runtimes are held off, so a
checkpoint carries no native section here (tests/test_run_checkpoint_native.py
covers the agent modes).
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import pickle
import sys
from pathlib import Path

import pytest

import chronicler.main as main_mod
import chronicler.run_checkpoint as rc
from chronicler.bundle_codec import load_bundle
from chronicler.main import execute_run
from chronicler.models import WorldState


@pytest.fixture(autouse=True)
def _pure_python_lane(monkeypatch):
    monkeypatch.setattr("chronicler.main._create_ecology_runtime", lambda world: None)
    monkeypatch.setattr("chronicler.main._create_politics_runtime", lambda world: None)


def _args(folder: Path, turns: int, **extra) -> argparse.Namespace:
    args = argparse.Namespace(
        seed=42, turns=turns, civs=3, regions=6,
        output=str(folder / "chronicle.md"), state=str(folder / "state.json"),
        resume=None, reflection_interval=4, llm_actions=False, scenario=None,
        simulate_only=True, agents="off", tuning_overrides={},
    )
    for key, value in extra.items():
        setattr(args, key, value)
    return args


def _content(path: Path) -> bytes:
    if path.name == "chronicle_bundle.json":
        data = load_bundle(path)
        data["metadata"].pop("generated_at", None)
        return json.dumps(data, sort_keys=True).encode()
    return path.read_bytes()


def _outputs(folder: Path) -> dict[str, bytes]:
    return {p.relative_to(folder).as_posix(): _content(p) for p in sorted(folder.rglob("*"))
            if p.is_file() and p.suffix != ".ckpt"}


def _straight(tmp_path: Path, turns: int = 12, every: int = 4) -> Path:
    folder = tmp_path / "straight"
    execute_run(_args(folder, turns, checkpoint_every=every,
                      checkpoint=str(folder / "ckpt" / "turn_{turn:03d}.ckpt")))
    return folder


def test_checkpointing_changes_no_output(tmp_path):
    plain = tmp_path / "plain"
    execute_run(_args(plain, 12))
    straight = _straight(tmp_path)
    # Every 4th turn, the final turn included (it can be extended).
    assert sorted(p.name for p in (straight / "ckpt").iterdir()) == [
        "turn_004.ckpt", "turn_008.ckpt", "turn_012.ckpt"]
    assert _outputs(plain) == _outputs(straight)


@pytest.mark.parametrize("k", [4, 8])
def test_resume_writes_what_the_uninterrupted_run_writes(tmp_path, k):
    straight = _straight(tmp_path)
    resumed = tmp_path / f"resumed_{k}"
    loaded = rc.read_checkpoint(straight / "ckpt" / f"turn_{k:03d}.ckpt")
    assert loaded.exact and loaded.mismatches == []
    assert loaded.state.world.turn == k and loaded.state.start_turn == 0
    result = execute_run(_args(resumed, 12), checkpoint_resume=loaded)
    assert result.total_turns == 12  # counts cover the whole run, not the resumed part
    assert _outputs(resumed) == _outputs(straight)


def test_resume_keeps_the_saved_run_configuration(tmp_path):
    # The caller's namespace says another seed and reflection interval; the
    # checkpoint's own (42, 4) decide.
    straight = _straight(tmp_path)
    resumed = tmp_path / "resumed"
    execute_run(_args(resumed, 12, seed=7, reflection_interval=10),
                checkpoint_resume=rc.read_checkpoint(straight / "ckpt" / "turn_004.ckpt"))
    assert _outputs(resumed) == _outputs(straight)


def test_args_resume_detects_a_checkpoint(tmp_path):
    straight = _straight(tmp_path)
    resumed = tmp_path / "resumed"
    execute_run(_args(resumed, 12, resume=str(straight / "ckpt" / "turn_008.ckpt")))
    assert _outputs(resumed) == _outputs(straight)


def test_a_resumed_run_checkpoints_the_same_run(tmp_path):
    """Resume 4 -> checkpoint 8 -> resume 8: still the uninterrupted run."""
    straight = _straight(tmp_path)
    first = tmp_path / "first"
    execute_run(_args(first, 12, resume=str(straight / "ckpt" / "turn_004.ckpt"),
                      checkpoint_every=4, checkpoint=str(first / "again_{turn}.ckpt")))
    second = tmp_path / "second"
    loaded = rc.read_checkpoint(first / "again_8.ckpt")
    assert loaded.header["lineage"] == [{"resumed_at": 4, "kind": "checkpoint", "exact": True}]
    execute_run(_args(second, 12), checkpoint_resume=loaded)
    assert _outputs(second) == _outputs(straight)


def test_focus_applied_deltas_survive_where_a_raw_save_loses_them(tmp_path, make_world):
    """The PR #51 gap: a raw save drops ``_focus_applied_deltas``."""
    from chronicler.tech_focus import TechFocus, apply_focus_effects, remove_focus_effects

    world = make_world(num_civs=1)
    civ = world.civilizations[0]
    civ.military = 99
    apply_focus_effects(civ, TechFocus.METALLURGY)
    assert civ.military == 100 and civ._focus_applied_deltas == {"metallurgy": {"military": 1}}

    rc.save_world(tmp_path / "w.ckpt", world)
    exact = rc.load_world(tmp_path / "w.ckpt").civilizations[0]
    remove_focus_effects(exact, TechFocus.METALLURGY)
    assert exact.military == 99

    world.save(tmp_path / "w.json")
    raw = WorldState.load(tmp_path / "w.json").civilizations[0]
    remove_focus_effects(raw, TechFocus.METALLURGY)
    assert raw.military == 85  # the full modifier comes off: the legacy gap


def test_private_world_state_round_trips(tmp_path, make_world):
    world = make_world(num_civs=2)
    world._treasury_tax_carry = {"a": 0.25}
    world._prev_priest_counts = {1: 3}
    world._persecuted_regions = {"r1"}
    rc.save_world(tmp_path / "w.ckpt", world)
    back = rc.load_world(tmp_path / "w.ckpt")
    assert back._treasury_tax_carry == {"a": 0.25}
    assert back._prev_priest_counts == {1: 3}
    assert back._persecuted_regions == {"r1"}
    assert back.model_dump_json() == world.model_dump_json()


def test_a_pure_python_checkpoint_has_no_native_section(tmp_path):
    straight = _straight(tmp_path)
    header = rc.describe(straight / "ckpt" / "turn_004.ckpt")
    assert [s["name"] for s in header["sections"]] == ["python"]
    assert header["format"] == rc.FORMAT and header["version"] == rc.FORMAT_VERSION
    assert header["turn"] == 4 and header["seed"] == 42 and header["num_turns"] == 12
    assert header["flags"]["scholarship"] is False  # dormant: off and absent
    assert header["exact"] is True and header["lineage"] == []
    assert header["identity"]["source"]["package_digest"]
    assert header["run_config"]["agent_mode"] == "off"


def test_corrupt_truncated_and_foreign_files_are_refused(tmp_path):
    path = _straight(tmp_path) / "ckpt" / "turn_004.ckpt"
    data = path.read_bytes()
    bad = tmp_path / "bad.ckpt"
    bad.write_bytes(data[:-1] + bytes([data[-1] ^ 1]))
    with pytest.raises(rc.CheckpointError, match="corrupt"):
        rc.read_checkpoint(bad)
    bad.write_bytes(data[:-7])
    with pytest.raises(rc.CheckpointError, match="truncated"):
        rc.read_checkpoint(bad)
    bad.write_bytes(b"{}")
    assert not rc.is_checkpoint(bad)
    with pytest.raises(rc.CheckpointError, match="not an exact run checkpoint"):
        rc.read_checkpoint(bad)
    header, _ = rc.read_header(path)
    header["version"] = rc.FORMAT_VERSION + 1
    raw = json.dumps(header).encode()
    body = data[len(rc.MAGIC) + 4 + int.from_bytes(data[len(rc.MAGIC):len(rc.MAGIC) + 4], "little"):]
    bad.write_bytes(rc.MAGIC + len(raw).to_bytes(4, "little") + raw + body)
    with pytest.raises(rc.CheckpointError, match="format version"):
        rc.read_checkpoint(bad)


def test_another_build_is_refused_and_the_override_labels_the_run(tmp_path, monkeypatch):
    straight = _straight(tmp_path)
    path = straight / "ckpt" / "turn_008.ckpt"
    real = rc.runtime_identity()
    other = json.loads(json.dumps(real))
    other["source"]["package_digest"] = "0" * 64
    monkeypatch.setattr(rc, "runtime_identity", lambda: other)
    with pytest.raises(rc.CheckpointIncompatible) as info:
        rc.read_checkpoint(path)
    assert "source package digest" in str(info.value) and "--resume-allow-mismatch" in str(info.value)
    loaded = rc.read_checkpoint(path, allow_mismatch=True)
    assert not loaded.exact and len(loaded.mismatches) == 1
    resumed = tmp_path / "resumed"
    execute_run(_args(resumed, 12), checkpoint_resume=loaded)
    meta = load_bundle(resumed / "chronicle_bundle.json")["metadata"]
    assert meta["resume"]["kind"] == "checkpoint" and meta["resume"]["exact"] is False
    assert meta["resume"]["turn"] == 8 and "source package digest" in meta["resume"]["mismatches"][0]
    # Apart from that label the run is the same (the source did not really change).
    out, ref = _outputs(resumed), _outputs(straight)
    assert out.keys() == ref.keys()
    assert [name for name in out if out[name] != ref[name]] == ["chronicle_bundle.json"]


def test_thread_settings_are_part_of_the_identity():
    saved = rc.runtime_identity()
    current = json.loads(json.dumps(saved))
    current["environment"]["thread_env"]["OPENBLAS_NUM_THREADS"] = "7"
    assert any("thread_env" in m for m in rc._compare_identity(saved, current, False))


@pytest.mark.parametrize(("checkpoint_seed", "resume_seed"), [("0", "42"), (None, "0")])
def test_hash_seed_is_compared_through_thread_environment(checkpoint_seed, resume_seed):
    saved = json.loads(json.dumps(rc.runtime_identity()))
    current = json.loads(json.dumps(saved))
    saved["environment"]["thread_env"]["PYTHONHASHSEED"] = checkpoint_seed
    current["environment"]["thread_env"]["PYTHONHASHSEED"] = resume_seed

    mismatches = rc._compare_identity(saved, current, False)

    assert any("thread_env PYTHONHASHSEED" in mismatch for mismatch in mismatches)


def test_hash_seed_receipt_field_mirrors_the_compared_environment_value():
    environment = rc.runtime_identity()["environment"]

    assert environment["hash_seed"] == environment["thread_env"].get("PYTHONHASHSEED")


def test_the_loader_constructs_only_allowed_globals():
    with pytest.raises(rc.CheckpointError, match="may not construct"):
        rc._Unpickler(io.BytesIO(pickle.dumps(os.system))).load()
    with pytest.raises(rc.CheckpointError, match="may not construct"):
        # A Chronicler function that is not a slot reducer.
        rc._Unpickler(io.BytesIO(pickle.dumps(main_mod.execute_run))).load()
    assert rc._Unpickler(io.BytesIO(pickle.dumps({1, 2}))).load() == {1, 2}


def test_checkpoint_path_template():
    assert rc.checkpoint_path("out/c.ckpt", 7) == Path("out/c.ckpt")
    assert rc.checkpoint_path("out/t{turn:04d}.ckpt", 7) == Path("out/t0007.ckpt")


def test_shadow_logger_rewrites_its_logged_turns(tmp_path):
    pa = pytest.importorskip("pyarrow")
    from chronicler.shadow import ShadowLogger

    class _Civ:
        population, military, economy, culture, stability = 10, 2, 3, 4, 5

    class _World:
        civilizations = [_Civ(), _Civ()]

    aggs = pa.record_batch({name: pa.array([0, 1], type=pa.uint32()) for name in
                            ("civ_id", "population", "military", "economy", "culture", "stability")})
    original = ShadowLogger(tmp_path / "a" / "shadow.arrow")
    for turn in (1, 2, 3):
        original.log_turn(turn, aggs, _World())
    restored = pickle.loads(pickle.dumps(original))
    original.close()
    restored.retarget(tmp_path / "b" / "shadow.arrow")
    restored.log_turn(4, aggs, _World())
    restored.close()
    original_more = ShadowLogger(tmp_path / "c" / "shadow.arrow")
    for turn in (1, 2, 3, 4):
        original_more.log_turn(turn, aggs, _World())
    original_more.close()
    assert (tmp_path / "b" / "shadow.arrow").read_bytes() == (tmp_path / "c" / "shadow.arrow").read_bytes()


def test_sidecar_rows_pickle_as_columns_and_economy_summary_uses_this_run(tmp_path):
    from chronicler.sidecar import SidecarWriter, _columns_to_rows, _rows_to_columns

    rows = [{"turn": 1, "a": 2}, {"turn": 1, "a": 3}, {"turn": 2, "b": 0.5}, {}, {}]
    assert _columns_to_rows(_rows_to_columns(rows)) == rows
    writer = SidecarWriter(tmp_path / "one")
    writer._needs_rows.extend(rows)
    writer.write_economy_snapshot(100, {"turn": 100, "x": {"r": 1.5}})
    back = pickle.loads(pickle.dumps(writer))
    assert back._needs_rows == rows
    back._base_dir = tmp_path / "two"
    back._dir = back._base_dir / "validation_summary"
    back._dir.mkdir(parents=True)
    back.write_economy_snapshot(110, {"turn": 110, "x": {"r": 2.0}})
    # The first snapshot's file is not in the new directory; the summary
    # still holds it, as the uninterrupted writer's does.
    assert [r["turn"] for r in back._economy_rows()] == [100, 110]


def _cli(monkeypatch, argv: list[str]) -> None:
    monkeypatch.setattr(sys, "argv", ["chronicler", *argv])
    main_mod.main()


def test_cli_resume_takes_the_checkpoint_configuration(tmp_path, monkeypatch, capsys):
    straight = tmp_path / "straight"
    _cli(monkeypatch, ["--seed", "42", "--turns", "10", "--civs", "3", "--regions", "6",
                       "--agents", "off", "--simulate-only", "--reflection-interval", "4",
                       "--output", str(straight / "chronicle.md"), "--state", str(straight / "state.json"),
                       "--checkpoint-every", "5"])
    ckpt = straight / rc.DEFAULT_FILENAME
    assert rc.describe(ckpt)["turn"] == 10  # replaced each time; the last is the final turn
    rc_turn5 = tmp_path / "t5"
    _cli(monkeypatch, ["--seed", "42", "--turns", "10", "--civs", "3", "--regions", "6",
                       "--agents", "off", "--simulate-only", "--reflection-interval", "4",
                       "--output", str(rc_turn5 / "chronicle.md"), "--state", str(rc_turn5 / "state.json"),
                       "--checkpoint-every", "5", "--checkpoint", str(rc_turn5 / "c{turn}.ckpt")])
    resumed = tmp_path / "resumed"
    # No --turns, --seed or switches: all from the checkpoint.
    _cli(monkeypatch, ["--resume", str(rc_turn5 / "c5.ckpt"), "--output", str(resumed / "chronicle.md"),
                       "--state", str(resumed / "state.json")])
    assert "Resuming exactly from" in capsys.readouterr().out
    assert _outputs(resumed) == {k: v for k, v in _outputs(rc_turn5).items()}


def test_cli_refuses_options_that_differ_from_the_checkpoint(tmp_path, monkeypatch, capsys):
    folder = tmp_path / "run"
    _cli(monkeypatch, ["--seed", "42", "--turns", "6", "--civs", "3", "--regions", "6", "--agents", "off",
                       "--simulate-only", "--output", str(folder / "chronicle.md"),
                       "--state", str(folder / "state.json"), "--checkpoint-every", "3",
                       "--checkpoint", str(folder / "c{turn}.ckpt")])
    for extra in (["--seed", "7"], ["--regions", "12"], ["--scholarship"], ["--turns", "3"]):
        with pytest.raises(SystemExit) as info:
            _cli(monkeypatch, ["--resume", str(folder / "c3.ckpt"), *extra,
                               "--output", str(tmp_path / "x" / "chronicle.md")])
        assert info.value.code == 2
        assert "checkpoint" in capsys.readouterr().err


def test_cli_legacy_state_resume_is_labelled(tmp_path, monkeypatch, capsys):
    folder = tmp_path / "run"
    _cli(monkeypatch, ["--seed", "42", "--turns", "6", "--civs", "3", "--regions", "6", "--agents", "off",
                       "--simulate-only", "--output", str(folder / "chronicle.md"),
                       "--state", str(folder / "state.json")])
    _cli(monkeypatch, ["--resume", str(folder / "state.json"), "--turns", "9", "--civs", "3",
                       "--regions", "6", "--agents", "off", "--simulate-only",
                       "--output", str(folder / "chronicle.md"), "--state", str(folder / "state.json")])
    assert "legacy resume" in capsys.readouterr().err
    meta = load_bundle(folder / "chronicle_bundle.json")["metadata"]
    assert meta["resume"] == {"kind": "legacy-state", "exact": False, "turn": 6}


def test_cli_checkpoint_option_checks(monkeypatch):
    for argv in (["--checkpoint", "x.ckpt"], ["--resume-allow-mismatch"]):
        with pytest.raises(SystemExit):
            _cli(monkeypatch, argv)
