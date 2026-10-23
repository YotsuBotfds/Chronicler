"""State/memory checkpoint cadence (--state-every), resume and interrupt checkpoints."""
from __future__ import annotations

import argparse
import json
import shutil
import signal
from pathlib import Path

import pytest

import chronicler.main as main_mod
from chronicler.main import DEFAULT_STATE_EVERY, _build_parser, execute_run
from chronicler.memory import MemoryStream
from chronicler.models import WorldState


@pytest.fixture(autouse=True)
def _pure_python_lane(monkeypatch):
    # Fixed lane even where the optional Rust extension exists.
    monkeypatch.setattr("chronicler.main._create_ecology_runtime", lambda world: None)
    monkeypatch.setattr("chronicler.main._create_politics_runtime", lambda world: None)


def _args(folder: Path, turns: int, *, state_every=None, resume=None, reflection_interval=4):
    args = argparse.Namespace(
        seed=42, turns=turns, civs=3, regions=6,
        output=str(folder / "chronicle.md"), state=str(folder / "state.json"),
        resume=str(resume) if resume else None, reflection_interval=reflection_interval,
        llm_actions=False, scenario=None, simulate_only=True, agents="off",
    )
    if state_every is not None:
        args.state_every = state_every
    return args


def _run(folder: Path, turns: int, on_turn=None, **kwargs):
    folder.mkdir(parents=True, exist_ok=True)
    return execute_run(_args(folder, turns, **kwargs), on_turn=on_turn)


def _on_disk_after(folder: Path, turn: int, copy_to: Path):
    """on_turn hook copying the run's files as they stand after ``turn``.

    Turn N+1's callback runs before that turn writes anything, so the files
    on disk are exactly what the run left after turn N.
    """
    def hook(snapshot, text, events, named):
        if snapshot.turn == turn + 1:
            shutil.copytree(folder, copy_to)
    return hook


def _resume(source: Path, folder: Path, turns: int, **kwargs):
    """Resume like the CLI: world from state.json, memories from memories_*.json."""
    if folder != source:
        shutil.copytree(source, folder)
    world = WorldState.load(folder / "state.json")
    memories = {}
    for mem_file in folder.glob("memories_*.json"):
        stream = MemoryStream.load(mem_file)
        memories[stream.civilization_name] = stream
    for name in ("chronicle.md", "chronicle_bundle.json"):
        (folder / name).unlink(missing_ok=True)
    return execute_run(_args(folder, turns, **kwargs), world=world, memories=memories)


def _artifacts(folder: Path) -> dict[str, bytes]:
    out = {}
    for path in sorted(folder.iterdir()):
        if not path.is_file():
            continue
        data = path.read_bytes()
        if path.name == "chronicle_bundle.json":
            bundle = json.loads(data)
            bundle["metadata"].pop("generated_at")
            data = json.dumps(bundle).encode()
        out[path.name] = data
    return out


def test_parser_state_every_option():
    parser = _build_parser()
    assert parser.parse_args([]).state_every is None
    assert parser.parse_args(["--state-every", "1"]).state_every == 1
    assert parser.parse_args(["--state-every", "25"]).state_every == 25
    for bad in ("0", "-3", "x"):
        with pytest.raises(SystemExit):
            parser.parse_args(["--state-every", bad])
    assert main_mod._resolve_state_every(argparse.Namespace()) == DEFAULT_STATE_EVERY
    for bad in (0, -1, True, "5", 2.0):
        with pytest.raises(ValueError):
            main_mod._resolve_state_every(argparse.Namespace(state_every=bad))


def test_checkpoint_cadence(tmp_path, monkeypatch):
    checkpoints, memory_turns, final_saves = [], [], []
    real_checkpoint = main_mod._write_state_checkpoint
    real_save_memories = main_mod._save_memory_streams
    real_world_save = WorldState.save

    def checkpoint(world, path):
        checkpoints.append(world.turn)
        real_checkpoint(world, path)

    def save_memories(memories, output_dir, reflection_counts=None):
        memory_turns.append(current["world"].turn)
        real_save_memories(memories, output_dir, reflection_counts)

    def world_save(self, path):
        final_saves.append(self.turn)
        real_world_save(self, path)

    current = {}
    real_run_turn = main_mod.run_turn_result

    def run_turn(world, **kwargs):
        current["world"] = world
        return real_run_turn(world, **kwargs)

    monkeypatch.setattr(main_mod, "_write_state_checkpoint", checkpoint)
    monkeypatch.setattr(main_mod, "_save_memory_streams", save_memories)
    monkeypatch.setattr(WorldState, "save", world_save)
    monkeypatch.setattr(main_mod, "run_turn_result", run_turn)

    _run(tmp_path / "every3", 8, state_every=3)
    assert checkpoints == [3, 6]          # the final turn uses the final save
    assert memory_turns == [3, 6, 8]
    assert final_saves == [8]

    checkpoints.clear(); memory_turns.clear(); final_saves.clear()
    _run(tmp_path / "every1", 4, state_every=1)
    assert checkpoints == [1, 2, 3]
    assert memory_turns == [1, 2, 3, 4]
    assert final_saves == [4]

    checkpoints.clear(); memory_turns.clear(); final_saves.clear()
    _run(tmp_path / "default", 21)
    assert checkpoints == [10, 20]
    assert memory_turns == [10, 20, 21]

    # Interactive/live callbacks may end a run: those turns still save.
    checkpoints.clear(); memory_turns.clear(); final_saves.clear()
    folder = tmp_path / "paused"
    folder.mkdir()
    execute_run(_args(folder, 7, state_every=5), pause_every=2,
                on_pause=lambda world, memories, pending: True)
    assert checkpoints == [2, 4, 5, 6]
    assert memory_turns == [2, 4, 5, 6, 7]
    checkpoints.clear(); memory_turns.clear(); final_saves.clear()
    folder = tmp_path / "quit"
    folder.mkdir()
    execute_run(_args(folder, 6, state_every=50), quit_check=lambda: current["world"].turn == 4)
    assert checkpoints == []
    assert memory_turns == [1, 2, 3, 4]
    assert final_saves == [4]


def test_completed_run_artifacts_identical_for_any_cadence(tmp_path):
    _run(tmp_path / "k1", 13, state_every=1)
    reference = _artifacts(tmp_path / "k1")
    assert {"state.json", "chronicle.md", "chronicle_bundle.json"} <= set(reference)
    assert any(name.startswith("memories_") for name in reference)
    for k in (3, 10, 40):
        _run(tmp_path / f"k{k}", 13, state_every=k)
        assert _artifacts(tmp_path / f"k{k}") == reference, k


def test_early_quit_artifacts_identical_for_any_cadence(tmp_path):
    def run(folder, k):
        folder.mkdir()
        execute_run(_args(folder, 12, state_every=k), pause_every=4,
                    on_pause=lambda world, memories, pending: world.turn < 8)
        return _artifacts(folder)

    assert run(tmp_path / "k1", 1) == run(tmp_path / "k5", 5)


def test_intermediate_checkpoint_matches_every_turn_writer_and_resumes_identically(tmp_path):
    """The turn-8 checkpoint equals what the historical every-turn writer left
    on disk after turn 8 (8 is a reflection turn here), and resumes identically."""
    every_turn, sparse = tmp_path / "k1", tmp_path / "k4"
    _run(every_turn, 14, state_every=1, on_turn=_on_disk_after(every_turn, 8, tmp_path / "k1_t8"))
    _run(sparse, 14, state_every=4, on_turn=_on_disk_after(sparse, 8, tmp_path / "k4_t8"))
    assert _artifacts(every_turn) == _artifacts(sparse)

    reference = WorldState.load(tmp_path / "k1_t8" / "state.json")
    checkpoint = WorldState.load(tmp_path / "k4_t8" / "state.json")
    assert checkpoint.turn == 8
    assert checkpoint.model_dump_json(indent=2) == reference.model_dump_json(indent=2)
    memory_files = sorted(p.name for p in (tmp_path / "k1_t8").glob("memories_*.json"))
    assert memory_files
    for name in memory_files:
        assert (tmp_path / "k4_t8" / name).read_bytes() == (tmp_path / "k1_t8" / name).read_bytes()

    _resume(tmp_path / "k1_t8", tmp_path / "resumed_k1", 14)
    _resume(tmp_path / "k4_t8", tmp_path / "resumed_k4", 14)
    assert _artifacts(tmp_path / "resumed_k4") == _artifacts(tmp_path / "resumed_k1")


def test_ctrl_c_finishes_turn_and_writes_resumable_checkpoint(tmp_path, monkeypatch):
    previous = signal.signal(signal.SIGINT, signal.default_int_handler)
    real_run_turn = main_mod.run_turn_result
    seen = []

    def run_turn(world, **kwargs):
        result = real_run_turn(world, **kwargs)
        seen.append(world.turn)
        if world.turn == 8:  # a reflection turn that is not a checkpoint turn
            signal.raise_signal(signal.SIGINT)  # deferred: the turn still completes
        return result

    monkeypatch.setattr(main_mod, "run_turn_result", run_turn)
    folder = tmp_path / "interrupted"
    folder.mkdir()
    try:
        with pytest.raises(KeyboardInterrupt):
            execute_run(_args(folder, 20, state_every=50))
        assert signal.getsignal(signal.SIGINT) is signal.default_int_handler
    finally:
        signal.signal(signal.SIGINT, previous)
    assert seen == list(range(1, 9))
    assert not (folder / "chronicle.md").exists()

    # Same files as the historical every-turn writer had on disk after turn 8.
    monkeypatch.setattr(main_mod, "run_turn_result", real_run_turn)
    reference = tmp_path / "k1"
    _run(reference, 20, state_every=1, on_turn=_on_disk_after(reference, 8, tmp_path / "k1_t8"))
    interrupted_world = WorldState.load(folder / "state.json")
    reference_world = WorldState.load(tmp_path / "k1_t8" / "state.json")
    assert interrupted_world.turn == 8
    assert interrupted_world.model_dump_json(indent=2) == reference_world.model_dump_json(indent=2)
    memory_files = sorted(p.name for p in (tmp_path / "k1_t8").glob("memories_*.json"))
    assert memory_files
    for name in memory_files:
        assert (folder / name).read_bytes() == (tmp_path / "k1_t8" / name).read_bytes()

    _resume(folder, tmp_path / "resumed_interrupt", 12)
    _resume(tmp_path / "k1_t8", tmp_path / "resumed_reference", 12)
    assert _artifacts(tmp_path / "resumed_interrupt") == _artifacts(tmp_path / "resumed_reference")


def test_sigint_deferral_is_inert_off_main_thread_or_over_custom_handlers():
    import threading

    custom = lambda signum, frame: None  # noqa: E731
    previous = signal.signal(signal.SIGINT, custom)
    try:
        with main_mod._SigintDeferral() as deferral:
            assert signal.getsignal(signal.SIGINT) is custom
        assert not deferral.requested
    finally:
        signal.signal(signal.SIGINT, previous)

    result = {}

    def worker():
        with main_mod._SigintDeferral() as deferral:
            result["installed"] = deferral._installed

    thread = threading.Thread(target=worker)
    thread.start()
    thread.join()
    assert result == {"installed": False}


def test_checkpoint_is_compact_atomic_and_loads_identically(tmp_path, sample_world):
    path = tmp_path / "state.json"
    path.write_text("stale")
    main_mod._write_state_checkpoint(sample_world, path)
    text = path.read_text(encoding="utf-8")
    assert "\n" not in text
    assert WorldState.load(path).model_dump_json(indent=2) == sample_world.model_dump_json(indent=2)
    assert not [p for p in tmp_path.iterdir() if p.name != "state.json"]  # no temp leftovers
