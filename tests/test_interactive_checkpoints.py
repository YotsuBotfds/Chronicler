"""Exact checkpoints of interactive sessions (chronicler.interactive).

A command typed at a pause that changes the run (``inject``, ``set``) is
recorded in the checkpoint of its turn, which is written again after the
pause; a session resumed from any of its checkpoints (``--interactive
--resume``) writes what the uninterrupted session writes, the commands of
later pauses typed again. ``fork`` changes nothing and says its state file
is not exact.

Offline lane: the terminal is scripted (``input``) and the native
ecology/politics runtimes are held off. Native agent modes are in
``tests/test_interactive_checkpoints_native.py``; the CLI with a real
terminal pipe in ``scripts/checkpoint_identity.py`` (``interactive_*``).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pytest

import chronicler.interactive as interactive
import chronicler.run_checkpoint as rc
from chronicler.live_checkpoints import PauseInterventions
from tests.live_session_harness import outputs

TURNS = 12
PAUSE_EVERY = 4


@pytest.fixture(autouse=True)
def _pure_python_lane(monkeypatch):
    monkeypatch.setattr("chronicler.main._create_ecology_runtime", lambda world: None)
    monkeypatch.setattr("chronicler.main._create_politics_runtime", lambda world: None)


class Terminal:
    """A scripted terminal: ``at_pause[turn]`` lists the lines typed at that
    pause, ``at_resume`` those at a resumed session's first pause; each pause
    then gets ``continue`` (unless its lines quit)."""

    def __init__(self, monkeypatch, at_pause: dict | None = None,
                 at_resume: list | None = None) -> None:
        self.pauses: list[tuple[int, str]] = []
        self._lines: list[str] = []
        original = interactive.interactive_pause

        def pause(world, memories, pending, *args, **kwargs):
            reason = kwargs.get("reason", "pause_interval")
            self.pauses.append((world.turn, reason))
            typed = at_resume if reason == "resumed" else (at_pause or {}).get(world.turn)
            self._lines = [*(typed or []), "continue"]
            return original(world, memories, pending, *args, **kwargs)

        monkeypatch.setattr(interactive, "interactive_pause", pause)
        monkeypatch.setattr("builtins.input", lambda prompt="": self._lines.pop(0))


def _args(folder: Path, **extra) -> argparse.Namespace:
    args = argparse.Namespace(
        seed=42, turns=TURNS, civs=3, regions=6, worldgen=None,
        output=str(folder / "chronicle.md"), state=str(folder / "state.json"),
        resume=None, reflection_interval=4, llm_actions=False, scenario=None,
        simulate_only=True, agents="off", narrator="local", interactive=True,
        pause_every=PAUSE_EVERY,
    )
    for key, value in extra.items():
        setattr(args, key, value)
    return args


def _first_civ() -> str:
    from chronicler.world_gen import generate_world
    return generate_world(seed=42, num_regions=6, num_civs=3).civilizations[0].name


def _ckpt(folder: Path, turn: int) -> Path:
    return folder / "ckpt" / f"turn_{turn:04d}.ckpt"


def _session(monkeypatch, folder: Path, *, at_pause=None, at_resume=None, **extra):
    terminal = Terminal(monkeypatch, at_pause=at_pause, at_resume=at_resume)
    return interactive.run_interactive(_args(folder, **extra)), terminal


def _straight(monkeypatch, tmp_path: Path, at_pause=None, **extra):
    folder = tmp_path / "straight"
    _session(monkeypatch, folder, at_pause=at_pause, checkpoint_every=1,
             checkpoint=str(folder / "ckpt" / "turn_{turn:04d}.ckpt"), **extra)
    return folder


def _resume(monkeypatch, path: Path, folder: Path, *, at_pause=None, at_resume=None, **extra):
    """``--interactive --resume path``, as the CLI adopts the checkpoint."""
    loaded = rc.read_checkpoint(path)
    terminal = Terminal(monkeypatch, at_pause=at_pause, at_resume=at_resume)
    args = _args(folder, resume=str(path), **extra)
    return interactive.run_interactive(args, exact_resume=loaded), terminal


def _commands(civ: str) -> dict[int, list[str]]:
    return {4: [f'set "{civ}" military 90', f'inject plague "{civ}"'],
            8: [f'set "{civ}" treasury 300']}


def test_commands_are_kept_and_every_checkpoint_resumes_exactly(tmp_path, monkeypatch):
    civ = _first_civ()
    script = _commands(civ)
    _session(monkeypatch, tmp_path / "plain", at_pause=script)
    folder = _straight(monkeypatch, tmp_path, at_pause=script)
    _session(monkeypatch, tmp_path / "untouched")
    assert outputs(tmp_path / "plain") == outputs(folder)
    assert outputs(tmp_path / "untouched") != outputs(folder)  # the commands change the run

    # The turn-4 checkpoint was written again after the pause: it holds the
    # stat and the queued injection and records both; earlier checkpoints do
    # not, later ones carry them.
    first = [{"turn": 4, "command": "set", "civ": civ, "stat": "military", "value": 90},
             {"turn": 4, "command": "inject", "event_type": "plague", "civ": civ}]
    assert rc.describe(_ckpt(folder, 4))["run_config"]["interventions"] == first
    assert "interventions" not in rc.describe(_ckpt(folder, 3))["run_config"]
    assert rc.describe(_ckpt(folder, 8))["run_config"]["interventions"] == [
        *first, {"turn": 8, "command": "set", "civ": civ, "stat": "treasury", "value": 300}]
    loaded = rc.read_checkpoint(_ckpt(folder, 4))
    assert next(c for c in loaded.state.world.civilizations if c.name == civ).military == 90
    assert loaded.state.pending_injections == [("plague", civ)]
    assert loaded.exact and loaded.state.live is None

    for k in (1, 3, 4, 5, 8, 11):
        resumed = tmp_path / f"resume_{k}"
        later = {turn: lines for turn, lines in script.items() if turn > k}
        result, terminal = _resume(monkeypatch, _ckpt(folder, k), resumed, at_pause=later)
        assert result.total_turns == TURNS
        assert terminal.pauses[0] == (k, "resumed")
        assert [t for t, _ in terminal.pauses[1:]] == [t for t in (4, 8, 12) if t > k]
        assert outputs(resumed) == outputs(folder), k


def test_a_single_run_resume_after_the_commands_is_exact(tmp_path, monkeypatch):
    """The rewritten checkpoint resumes as a plain ``--resume`` too."""
    from chronicler.main import execute_run
    civ = _first_civ()
    folder = _straight(monkeypatch, tmp_path, at_pause={4: _commands(civ)[4]})
    for k in (4, 9):
        resumed = tmp_path / f"single_{k}"
        args = _args(resumed, resume=str(_ckpt(folder, k)), interactive=False, pause_every=None)
        execute_run(args)
        assert outputs(resumed) == outputs(folder), k


def test_the_checkpoint_turns_are_written_again_too(tmp_path, monkeypatch):
    civ = _first_civ()
    script = {4: _commands(civ)[4]}
    _session(monkeypatch, tmp_path / "plain", at_pause=script)
    folder = tmp_path / "turns"
    _session(monkeypatch, folder, at_pause=script, checkpoint_turns=frozenset({4}))
    path = folder / "checkpoint_turn_4.ckpt"
    assert len(rc.describe(path)["run_config"]["interventions"]) == 2
    resumed = tmp_path / "resume"
    _resume(monkeypatch, path, resumed)
    assert outputs(resumed) == outputs(tmp_path / "plain")


def test_quit_at_the_resumed_pause_writes_nothing(tmp_path, monkeypatch):
    folder = _straight(monkeypatch, tmp_path)
    resumed = tmp_path / "quit"
    result, terminal = _resume(monkeypatch, _ckpt(folder, 5), resumed, at_resume=["quit"])
    assert result is None and terminal.pauses == [(5, "resumed")]
    assert not resumed.exists() or not any(resumed.iterdir())


def test_commands_at_the_resumed_pause_continue_the_loaded_run(tmp_path, monkeypatch):
    """A command typed at the resumed pause is applied to the checkpoint's
    run and recorded at its turn: the session equals one that paused there."""
    civ = _first_civ()
    typed = [f'set "{civ}" stability 15', f'inject drought "{civ}"']
    folder = _straight(monkeypatch, tmp_path)
    resumed = tmp_path / "resume"
    _resume(monkeypatch, _ckpt(folder, 2), resumed, at_resume=typed, checkpoint_every=1,
            checkpoint=str(resumed / "ckpt" / "turn_{turn:04d}.ckpt"))
    assert rc.describe(_ckpt(resumed, 3))["run_config"]["interventions"] == [
        {"turn": 2, "command": "set", "civ": civ, "stat": "stability", "value": 15},
        {"turn": 2, "command": "inject", "event_type": "drought", "civ": civ}]
    # An uninterrupted session pausing at turn 2 with the same commands.
    _session(monkeypatch, tmp_path / "paused_at_2", at_pause={2: typed}, pause_every=2)
    assert outputs(resumed) == outputs(tmp_path / "paused_at_2")


def test_fork_changes_nothing_and_is_labelled_not_exact(tmp_path, monkeypatch, capsys):
    _session(monkeypatch, tmp_path / "plain")
    folder = tmp_path / "forked"
    _session(monkeypatch, folder, at_pause={4: ["fork"]})
    assert "not an exact checkpoint" in capsys.readouterr().out
    forked = outputs(folder)
    assert {name for name in forked if name.startswith("fork_save_t4/")}
    assert {n: c for n, c in forked.items() if not n.startswith("fork_save_t4/")} == \
        outputs(tmp_path / "plain")


def test_pause_interventions_record_and_reset():
    world = argparse.Namespace(turn=6)
    boundary = PauseInterventions()
    boundary.note_intervention(world, {"command": "set"})  # unbound: only the flag
    assert boundary.live_record() is None
    assert boundary.turn_end(world) is True and boundary.turn_end(world) is False
    config: dict = {}
    boundary.bind(None, config)
    boundary.note_intervention(world, {"command": "inject", "event_type": "plague", "civ": "A"})
    assert config["interventions"] == [{"turn": 6, "command": "inject", "event_type": "plague",
                                        "civ": "A"}]
    assert boundary.turn_end(world) is True


def test_the_cli_resumes_only_exact_checkpoints_interactively(tmp_path, monkeypatch, capsys):
    import chronicler.main as main_mod
    from chronicler.main import execute_run

    single = tmp_path / "single"
    execute_run(_args(single, turns=6, interactive=False, pause_every=None, checkpoint_every=3,
                      checkpoint=str(single / "turn_{turn}.ckpt")))
    calls = []
    monkeypatch.setattr(interactive, "run_interactive",
                        lambda args, exact_resume=None, **kw: calls.append((args, exact_resume)))
    base = ["chronicler", "--interactive", "--simulate-only",
            "--output", str(tmp_path / "again" / "chronicle.md")]
    monkeypatch.setattr(sys, "argv", [*base, "--resume", str(single / "state.json")])
    with pytest.raises(SystemExit) as refused:
        main_mod.main()
    assert refused.value.code == 2 and "is not one" in capsys.readouterr().err
    monkeypatch.setattr(sys, "argv", [*base, "--resume", str(single / "turn_3.ckpt"),
                                      "--pause-every", "2"])
    main_mod.main()
    (args, loaded), = calls
    assert loaded.state.world.turn == 3 and args.seed == 42 and args.turns == 6
    assert (args.regions, args.civs, args.pause_every) == (6, 3, 2)
    monkeypatch.setattr(sys, "argv", [*base, "--resume", str(single / "turn_3.ckpt"),
                                      "--agents", "hybrid"])
    with pytest.raises(SystemExit):
        main_mod.main()
    assert "conflicts with the checkpoint" in capsys.readouterr().err
    # Still exclusive with the other modes.
    monkeypatch.setattr(sys, "argv", [*base, "--live", "--resume", str(single / "turn_3.ckpt")])
    with pytest.raises(SystemExit):
        main_mod.main()
    assert "mutually exclusive" in capsys.readouterr().err
