"""Snapshot accuracy reuse must follow real hostage lifecycle mutations."""
import argparse
import hashlib
from chronicler.turn_artifacts import TurnObservation, TurnResult
from pathlib import Path

from chronicler.great_persons import kill_great_person
from chronicler.intelligence import get_perceived_stat
from chronicler.main import execute_run
from chronicler.models import FactionState, FactionType, GreatPerson
from chronicler.relationships import capture_hostage, release_hostage
from scripts.benchmark_headless import FixedDateTime, rng_trace


def test_snapshot_reuse_matches_live_reads_across_capture_release_and_death(
    make_world, tmp_path, monkeypatch,
):
    initial = make_world(num_civs=3)
    initial.agent_mode = "off"
    for civ in initial.civilizations:
        civ.factions = FactionState(influence={
            FactionType.MILITARY: 0.7, FactionType.MERCHANT: 0.1,
            FactionType.CULTURAL: 0.1, FactionType.CLERGY: 0.1,
        })
    origin = initial.civilizations[0]
    origin.great_persons.append(GreatPerson(
        name="Prince", role="general", trait="bold", civilization=origin.name,
        origin_civilization=origin.name, born_turn=1,
    ))

    def tick(world, *_args, **_kwargs):
        # Snapshot construction runs immediately after this turn boundary.
        world.turn += 1
        origin, captor, other = world.civilizations
        if world.turn == 1:
            capture_hostage(origin, captor, world)
        elif world.turn == 2:
            release_hostage(captor.great_persons[0], captor, origin, world)
        elif world.turn == 3:
            capture_hostage(origin, other, world)
        elif world.turn == 4:
            kill_great_person(other.great_persons[0], other, world)
        elif world.turn == 5:
            capture_hostage(origin, captor, world)
        elif world.turn == 6:
            release_hostage(captor.great_persons[0], captor, origin, world)
        return TurnResult("", TurnObservation(world.turn - 1, world.turn, None))

    monkeypatch.setattr("chronicler.main.run_turn_result", tick)
    monkeypatch.setattr("chronicler.main._create_ecology_runtime", lambda _world: None)
    monkeypatch.setattr("chronicler.main._create_politics_runtime", lambda _world: None)
    monkeypatch.setattr("chronicler.bundle.datetime", FixedDateTime)

    def run(folder: Path, live_reads: bool):
        folder.mkdir()
        snapshots = []
        world = initial.model_copy(deep=True)
        args = argparse.Namespace(
            seed=world.seed, turns=6, civs=3, regions=3,
            output=str(folder / "chronicle.md"), state=str(folder / "state.json"),
            resume=None, reflection_interval=10, llm_actions=False,
            scenario=None, simulate_only=True, agents="off",
        )
        with monkeypatch.context() as context:
            if live_reads:
                context.setattr(
                    "chronicler.main._get_perceived_stat_with_accuracy",
                    lambda obs, target, stat, world, max_value=100, **_:
                        get_perceived_stat(obs, target, stat, world, max_value),
                )
            with rng_trace(folder / "rng.jsonl") as trace:
                execute_run(args, world=world, on_turn=lambda snapshot, *_:
                            snapshots.append(snapshot.model_dump(mode="json")))
        artifacts = {
            str(path.relative_to(folder)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in folder.rglob("*") if path.is_file() and path.name != "rng.jsonl"
        }
        return snapshots, trace, artifacts

    optimized = run(tmp_path / "optimized", False)
    reference = run(tmp_path / "reference", True)
    assert optimized == reference
    origin, captor, other = (c.name for c in initial.civilizations)
    assert [snapshot["per_pair_accuracy"][origin] for snapshot in optimized[0]] == [
        {captor: 0.3}, {}, {other: 0.3}, {}, {captor: 0.3}, {},
    ]
    for snapshot in optimized[0]:
        assert snapshot["per_pair_accuracy"][captor] == {}
        assert snapshot["per_pair_accuracy"][other] == {}
