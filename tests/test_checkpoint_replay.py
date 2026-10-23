"""Continuation contracts: actual turn execution, strict loads, and CLI failures."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from chronicler import checkpoint_replay as replay
from chronicler.models import ResourceType, WorldState
from chronicler.tech_focus import TechFocus, apply_focus_effects, remove_focus_effects
from chronicler.world_gen import generate_world


@pytest.mark.parametrize("seed,split", [(1, 0), (42, 13), (73, 39)])
def test_uninterrupted_matches_every_resumed_turn(seed, split, tmp_path):
    world = generate_world(seed=seed, num_civs=4, num_regions=8)
    original = world.model_dump()
    report = replay.validate_replay(world, turns=40, split=split, checkpoint_path=tmp_path / "checkpoint.json")
    assert report["status"] == "PASS"
    assert report["compared_resumed_turns"] == 40 - split
    assert [row["turn"] for row in report["turn_digests"]] == list(range(split, 41))
    assert all(row["uninterrupted"] == row["resumed"] for row in report["turn_digests"])
    assert world.model_dump() == original
    assert world.turn == 0


def test_real_pending_stockpile_boundary_rejects_api_and_cli(tmp_path, capsys):
    # The reviewed mercenary correction and the 2026-10 extinction fix
    # (decaying event hazards) change this trace. At turn 14 an expansion into
    # an empty region requests bootstrap on the next turn. The request is
    # transient and intentionally outside the envelope contract.
    world = generate_world(seed=42, num_civs=4, num_regions=8)
    original = world.model_dump()
    with pytest.raises(replay.CheckpointError, match="completed stockpile bootstrap"):
        replay.validate_replay(world, turns=30, split=14, checkpoint_path=tmp_path / "api.json")
    assert world.model_dump() == original
    assert not (tmp_path / "api.json").exists()
    output = tmp_path / "cli"
    assert replay.main([
        "--seed", "42", "--turns", "30", "--split", "14", "--output-dir", str(output),
    ]) == 2
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "ERROR"
    assert report["reason"] == "checkpoint requires a completed stockpile bootstrap"
    assert json.loads((output / "report.json").read_text()) == report
    assert not (output / "checkpoint.json").exists()


def test_focus_sidecar_preserves_capped_bonus_removal(make_world, tmp_path):
    world = make_world()
    civ = world.civilizations[0]
    civ.military = 99
    apply_focus_effects(civ, TechFocus.METALLURGY)
    assert civ._focus_applied_deltas == {"metallurgy": {"military": 1}}

    # Reproduce the existing raw save/load gap without changing that format.
    world.save(tmp_path / "raw.json")
    raw = WorldState.load(tmp_path / "raw.json")
    remove_focus_effects(raw.civilizations[0], TechFocus.METALLURGY)
    assert raw.civilizations[0].military == 85

    replay.save_checkpoint(world, tmp_path / "checkpoint.json")
    resumed = replay.load_checkpoint(tmp_path / "checkpoint.json")
    remove_focus_effects(civ, TechFocus.METALLURGY)
    remove_focus_effects(resumed.civilizations[0], TechFocus.METALLURGY)
    assert civ.military == resumed.civilizations[0].military == 99
    assert replay._comparison_state(world) == replay._comparison_state(resumed)


def test_focused_world_continues_through_real_turns(make_world, tmp_path):
    world = make_world()
    world.civilizations[0].military = 99
    apply_focus_effects(world.civilizations[0], TechFocus.METALLURGY)
    report = replay.validate_replay(world, turns=20, split=0, checkpoint_path=tmp_path / "checkpoint.json")
    assert report["status"] == "PASS"
    assert report["compared_resumed_turns"] == 20


def test_enum_resource_keys_do_not_create_false_divergence(make_world, tmp_path):
    world = make_world()
    world.regions[0].resource_suspensions[ResourceType.GRAIN] = 4
    report = replay.validate_replay(world, turns=4, split=0, checkpoint_path=tmp_path / "checkpoint.json")
    assert report["status"] == "PASS"
    resumed = replay.load_checkpoint(tmp_path / "checkpoint.json")
    assert resumed.regions[0].resource_suspensions == {0: 4}


def test_replay_uses_absolute_seed_schedule_for_nonzero_start(make_world, tmp_path):
    world = make_world()
    world.turn = 17
    report = replay.validate_replay(world, turns=6, split=2, checkpoint_path=tmp_path / "checkpoint.json")
    assert report["status"] == "PASS"
    assert report["start_turn"] == 17
    assert report["checkpoint_turn"] == 19
    assert report["target_turn"] == 23


def test_first_divergence_is_reported_and_stops(make_world, tmp_path, monkeypatch):
    actual_load = replay.load_checkpoint

    def damaged_load(*args, **kwargs):
        restored = actual_load(*args, **kwargs)
        restored.civilizations[0].treasury += 1
        return restored

    monkeypatch.setattr(replay, "load_checkpoint", damaged_load)
    report = replay.validate_replay(make_world(), turns=8, split=2, checkpoint_path=tmp_path / "checkpoint.json")
    assert report["status"] == "FAIL"
    assert report["first_divergent_turn"] == 2
    assert report["difference_path"] == "checkpoint.world.civilizations[0].treasury"
    assert report["compared_resumed_turns"] == 0


def test_first_post_resume_divergence_and_cli_fail_exit(make_world, tmp_path, monkeypatch, capsys):
    actual_advance = replay._advance
    calls = 0

    def perturbed_advance(world):
        nonlocal calls
        actual_advance(world)
        calls += 1
        if calls == 2:  # First resumed turn, after first uninterrupted turn.
            world.civilizations[0].treasury += 1

    source = tmp_path / "input.json"
    make_world().save(source)
    monkeypatch.setattr(replay, "_advance", perturbed_advance)
    code = replay.main([
        "--state", str(source), "--turns", "4", "--split", "0",
        "--output-dir", str(tmp_path / "output"),
    ])
    assert code == 1
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "FAIL"
    assert report["first_divergent_turn"] == 1
    assert report["compared_resumed_turns"] == 1
    assert calls == 2


@pytest.mark.parametrize("mode", ["hybrid", "shadow", "demographics-only", "typo"])
def test_rejects_agent_modes_before_writing(mode, make_world, tmp_path):
    world = make_world()
    world.agent_mode = mode
    path = tmp_path / "checkpoint.json"
    with pytest.raises(replay.CheckpointError, match="unsupported agent mode"):
        replay.save_checkpoint(world, path)
    assert not path.exists()


@pytest.mark.parametrize("runtime", ["native", "native-off", "hybrid", "python-off-v2"])
def test_rejects_unsupported_runtime(runtime, make_world, tmp_path):
    with pytest.raises(replay.CheckpointError, match="unsupported runtime"):
        replay.validate_replay(make_world(), turns=2, split=0, checkpoint_path=tmp_path / "cp.json", runtime=runtime)
    assert not (tmp_path / "cp.json").exists()


@pytest.mark.parametrize("attribute", ["_agent_bridge", "_agent_snapshot", "_named_agents", "_economy_result", "_treasury_tax_carry"])
def test_rejects_residual_native_state(attribute, make_world, tmp_path):
    world = make_world()
    setattr(world, attribute, object())
    with pytest.raises(replay.CheckpointError, match="agent|native"):
        replay.save_checkpoint(world, tmp_path / "cp.json")


def test_rejects_missing_focus_deltas(make_world, tmp_path):
    world = make_world()
    apply_focus_effects(world.civilizations[0], TechFocus.METALLURGY)
    raw = WorldState.model_validate_json(world.model_dump_json())
    with pytest.raises(replay.CheckpointError, match="lacks applied deltas"):
        replay.save_checkpoint(raw, tmp_path / "cp.json")


@pytest.mark.parametrize("mutation,error", [
    (lambda p: p.update(version=99), "format/version"),
    (lambda p: p.update(version=True), "invalid checkpoint"),
    (lambda p: p.update(format="bundle"), "format/version"),
    (lambda p: p.update(runtime="native"), "runtime"),
    (lambda p: p.update(schema_sha256="changed"), "schema mismatch"),
    (lambda p: p["runtime_identity"].update(python="0.0.0"), "runtime mismatch"),
    (lambda p: p["runtime_identity"].update(source_sha256="changed"), "runtime mismatch"),
    (lambda p: p["world"].update(seed=999), "world digest mismatch"),
    (lambda p: p.update(focus_deltas=[{}]), "focus deltas digest mismatch"),
    (lambda p: p.update(extra="ignored?"), "invalid checkpoint"),
])
def test_checkpoint_contract_rejects_mutation(mutation, error, make_world, tmp_path):
    path = tmp_path / "cp.json"
    replay.save_checkpoint(make_world(), path)
    payload = json.loads(path.read_text())
    mutation(payload)
    path.write_text(json.dumps(payload))
    with pytest.raises(replay.CheckpointError, match=error):
        replay.load_checkpoint(path)


@pytest.mark.parametrize("nested", [False, True])
def test_unknown_world_fields_not_silently_dropped(nested, make_world, tmp_path):
    path = tmp_path / "cp.json"
    replay.save_checkpoint(make_world(), path)
    payload = json.loads(path.read_text())
    target = payload["world"]["regions"][0] if nested else payload["world"]
    target["future_field"] = 42
    payload["world_sha256"] = replay._digest(payload["world"])
    path.write_text(json.dumps(payload))
    with pytest.raises(replay.CheckpointError, match="unrecognized persisted field"):
        replay.load_checkpoint(path)


def test_invalid_sidecar_count_and_stat_names(make_world, tmp_path):
    path = tmp_path / "cp.json"
    replay.save_checkpoint(make_world(), path)
    payload = json.loads(path.read_text())
    payload["focus_deltas"] = [{}]
    payload["focus_deltas_sha256"] = replay._digest(payload["focus_deltas"])
    path.write_text(json.dumps(payload))
    with pytest.raises(replay.CheckpointError, match="civilization count mismatch"):
        replay.load_checkpoint(path)
    payload["focus_deltas"] = [{"metallurgy": {"treasury": 1}}, None]
    payload["focus_deltas_sha256"] = replay._digest(payload["focus_deltas"])
    path.write_text(json.dumps(payload))
    with pytest.raises(replay.CheckpointError, match="invalid tracked tech focus"):
        replay.load_checkpoint(path)


@pytest.mark.parametrize("value", [True, 1.5, "1"])
def test_sidecar_deltas_require_strict_integers(value, make_world, tmp_path):
    path = tmp_path / "cp.json"
    replay.save_checkpoint(make_world(), path)
    payload = json.loads(path.read_text())
    payload["focus_deltas"] = [{"metallurgy": {"military": value}}, None]
    payload["focus_deltas_sha256"] = replay._digest(payload["focus_deltas"])
    path.write_text(json.dumps(payload))
    with pytest.raises(replay.CheckpointError, match="invalid checkpoint"):
        replay.load_checkpoint(path)


def test_nested_world_types_and_semantic_duplicate_keys_fail_closed(make_world, tmp_path):
    path = tmp_path / "cp.json"
    replay.save_checkpoint(make_world(), path)
    original = path.read_text()
    payload = json.loads(original)
    payload["world"]["civilizations"][0]["treasury"] = "123"
    payload["world_sha256"] = replay._digest(payload["world"])
    path.write_text(json.dumps(payload))
    with pytest.raises(replay.CheckpointError, match="invalid checkpoint"):
        replay.load_checkpoint(path)
    payload = json.loads(original)
    payload["world"]["regions"][0]["resource_suspensions"] = {"0": 2, "ResourceType.GRAIN": 4}
    payload["world_sha256"] = replay._digest(payload["world"])
    path.write_text(json.dumps(payload))
    with pytest.raises(replay.CheckpointError, match="ambiguous normalized dictionary keys"):
        replay.load_checkpoint(path)


@pytest.mark.parametrize("signal", ["shocks", "faction", "bootstrap", "artifact"])
def test_pending_turn_signals_rejected(signal, make_world, tmp_path):
    world = make_world()
    if signal == "shocks":
        world.pending_shocks.append(object())
    elif signal == "faction":
        world.civilizations[0].factions.pending_faction_shift = "military"
    elif signal == "bootstrap":
        world.regions[0]._stockpile_bootstrap_pending = True
    else:
        world._artifact_intents.append(object())
    with pytest.raises(replay.CheckpointError, match="completed"):
        replay.save_checkpoint(world, tmp_path / "cp.json")


@pytest.mark.parametrize("text", ['{"version":1,"version":2}', '{"bad":NaN}', '{"bad":Infinity}', '{'])
def test_rejects_ambiguous_or_invalid_json(text, tmp_path):
    path = tmp_path / "cp.json"
    path.write_text(text)
    with pytest.raises(replay.CheckpointError, match="invalid checkpoint"):
        replay.load_checkpoint(path)


def test_invalid_utf8_is_structured_error(tmp_path, capsys):
    path = tmp_path / "invalid.json"
    path.write_bytes(b"\xff\xfe")
    with pytest.raises(replay.CheckpointError, match="invalid checkpoint"):
        replay.load_checkpoint(path)
    assert replay.main(["--state", str(path), "--output-dir", str(tmp_path / "out")]) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "ERROR"
    assert path.read_bytes() == b"\xff\xfe"


def test_nonfinite_save_preserves_existing_checkpoint(make_world, tmp_path):
    path = tmp_path / "cp.json"
    replay.save_checkpoint(make_world(), path)
    original = path.read_bytes()
    world = make_world()
    world.regions[0].ecology.soil = float("nan")
    with pytest.raises(replay.ArtifactIOError, match="serialize"):
        replay.save_checkpoint(world, path)
    assert path.read_bytes() == original


@pytest.mark.parametrize("turns,split", [(0, 0), (4, 4), (4, -1), (4, 5), (True, 0)])
def test_invalid_validation_window(turns, split, make_world, tmp_path):
    with pytest.raises(replay.CheckpointError, match="at least one resumed turn"):
        replay.validate_replay(make_world(), turns=turns, split=split, checkpoint_path=tmp_path / "cp.json")


def test_cli_unsupported_modes_return_structured_error(tmp_path, capsys):
    assert replay.main(["--agents", "hybrid", "--output-dir", str(tmp_path)]) == 2
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "ERROR"
    assert "native state/RNG" in report["reason"]
    assert not (tmp_path / "checkpoint.json").exists()


@pytest.mark.parametrize("name", ["checkpoint.json", "report.json"])
def test_cli_does_not_overwrite_source(name, make_world, tmp_path, capsys):
    source = tmp_path / name
    make_world().save(source)
    original = source.read_bytes()
    assert replay.main(["--state", str(source), "--output-dir", str(tmp_path)]) == 2
    assert source.read_bytes() == original
    assert "overwrite" in json.loads(capsys.readouterr().out)["reason"]


@pytest.mark.parametrize("name", ["checkpoint.json", "report.json"])
def test_cli_preserves_preexisting_evidence(name, tmp_path, capsys):
    path = tmp_path / name
    path.write_bytes(b"existing evidence")
    assert replay.main(["--output-dir", str(tmp_path)]) == 2
    assert path.read_bytes() == b"existing evidence"
    assert "already exist" in json.loads(capsys.readouterr().out)["reason"]


@pytest.mark.parametrize("bad_flags", [["--agents", "hybrid"], ["--runtime", "native"], ["--civs", "0"]])
@pytest.mark.parametrize("input_alias", [False, True])
def test_cli_error_preflight_preserves_evidence_and_source(bad_flags, input_alias, make_world, tmp_path, capsys):
    path = tmp_path / "report.json"
    make_world().save(path)
    original = path.read_bytes()
    argv = bad_flags + ["--output-dir", str(tmp_path)]
    if input_alias:
        argv += ["--state", str(path)]
    assert replay.main(argv) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "ERROR"
    assert path.read_bytes() == original


def test_real_cli_and_cross_process_resume_with_different_hashseeds(tmp_path):
    root = Path(__file__).resolve().parents[1]
    environment = dict(os.environ, PYTHONPATH=str(root / "src"), PYTHONHASHSEED="11")
    result = subprocess.run([
        sys.executable, "-m", "chronicler.checkpoint_replay", "--seed", "42",
        "--turns", "30", "--split", "13", "--output-dir", str(tmp_path),
    ], env=environment, cwd=root, text=True, capture_output=True, check=True)
    report = json.loads(result.stdout)
    assert report["status"] == "PASS"
    script = """
import json,sys
from pathlib import Path
from chronicler.checkpoint_replay import load_checkpoint,_advance,_digest,_comparison_state
w=load_checkpoint(Path(sys.argv[1]))
while w.turn < 30: _advance(w)
print(json.dumps({'turn':w.turn,'digest':_digest(_comparison_state(w))}))
"""
    environment["PYTHONHASHSEED"] = "97"
    resumed = subprocess.run([
        sys.executable, "-c", script, str(tmp_path / "checkpoint.json"),
    ], env=environment, cwd=root, text=True, capture_output=True, check=True)
    assert json.loads(resumed.stdout) == {"turn": 30, "digest": report["turn_digests"][-1]["uninterrupted"]}
