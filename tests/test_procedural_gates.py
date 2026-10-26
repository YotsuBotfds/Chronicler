"""Procedural gate profile: runner world arguments, world shapes in reports,
the artifact oracle per starting civ, and the comparator's world check
(docs/integration/procedural-gates.md)."""
from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path

import pytest

from chronicler.validation_gate import ValidationGateInputError

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "m53b_run_validation.py"


def _load_runner():
    spec = importlib.util.spec_from_file_location("m53b_run_validation", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _ns(**kwargs):
    base = {"profile": "full", "seeds": None, "turns": None, "worldgen": "template",
            "regions": None, "civs": None}
    base.update(kwargs)
    return argparse.Namespace(**base)


def test_procedural_profile_defaults_and_world_size():
    runner = _load_runner()
    subset = runner.apply_profile_defaults(_ns(profile="subset", worldgen="procedural"))
    full = runner.apply_profile_defaults(_ns(profile="full", worldgen="procedural"))
    assert (subset.seeds, subset.turns) == (20, 200)
    assert (full.seeds, full.turns) == (100, 300)
    assert (full.regions, full.civs) == (32, 10)
    sized = runner.apply_profile_defaults(_ns(worldgen="procedural", regions=48, civs=12, seeds=3, turns=7))
    assert (sized.seeds, sized.turns, sized.regions, sized.civs) == (3, 7, 48, 12)
    assert runner._world_args(full) == ["--worldgen", "procedural", "--regions", "32", "--civs", "10"]


def test_template_profile_is_unchanged():
    runner = _load_runner()
    full = runner.apply_profile_defaults(_ns(profile="full"))
    assert (full.seeds, full.turns) == (200, 500)
    assert (full.regions, full.civs) == (None, None)
    assert runner._world_args(full) == []
    # Namespaces built before the world option existed still work.
    legacy = runner.apply_profile_defaults(argparse.Namespace(profile="subset", seeds=None, turns=None))
    assert (legacy.seeds, legacy.turns) == (20, 200)
    assert runner._world_args(legacy) == []


@pytest.mark.parametrize("runner_fn", ["run_subset", "run_full"])
def test_procedural_runs_forward_the_world(monkeypatch, tmp_path, runner_fn):
    runner = _load_runner()
    commands: list[list[str]] = []
    monkeypatch.setattr(runner, "_run", lambda cmd, cwd, env: commands.append(cmd))
    args = runner.apply_profile_defaults(_ns(profile="full", worldgen="procedural", seed_start=42, parallel=3,
                                             output_root=tmp_path))
    getattr(runner, runner_fn)(args, tmp_path, {})
    cmd = commands[0]
    at = cmd.index("--worldgen")
    assert cmd[at:at + 6] == ["--worldgen", "procedural", "--regions", "32", "--civs", "10"]
    assert cmd[cmd.index("--seed-range") + 1] == "42-141"
    assert cmd[cmd.index("--turns") + 1] == "300"


def test_runner_rejects_world_size_for_template(monkeypatch):
    runner = _load_runner()
    monkeypatch.setattr(runner.sys, "argv", ["m53b_run_validation.py", "--profile", "subset", "--regions", "24"])
    with pytest.raises(SystemExit) as exc:
        runner.main()
    assert exc.value.code == 2


def _bundle(civs: int, regions: int, procedural: bool, artifacts: int = 0, turns: int = 100) -> dict:
    world = {
        "regions": [{} for _ in range(regions)],
        "artifacts": [{"artifact_type": ("relic", "artwork")[i % 2], "status": "active"} for i in range(artifacts)],
    }
    if procedural:
        world["geography"] = {"generator": "procedural"}
    return {
        "world_state": world,
        "history": [{"civ_stats": {f"civ{i}": {"regions": ["r"]} for i in range(civs)}}],
        "metadata": {"total_turns": turns},
    }


def test_world_shape_and_summary():
    from chronicler.validation_io import _world_shape, summarize_world_shapes

    template = _world_shape(_bundle(4, 8, procedural=False))
    procedural = _world_shape(_bundle(10, 32, procedural=True))
    assert template == {"generator": "template", "regions": 8, "civs": 4}
    assert procedural == {"generator": "procedural", "regions": 32, "civs": 10}
    assert summarize_world_shapes([{"world": template}] * 3) is None
    assert summarize_world_shapes([{"world": procedural}] * 2) == [
        {"generator": "procedural", "regions": 32, "civs": 10, "seeds": 2}
    ]


def test_artifact_creation_rate_is_per_starting_civ():
    from chronicler.validation_io import check_artifact_lifecycle, run_artifact_oracle

    # 40 artifacts in 100 turns: 10 per civ per 100 turns with 4 civs, 4 with 10.
    template = [_bundle(4, 8, procedural=False, artifacts=40)]
    procedural = [_bundle(10, 32, procedural=True, artifacts=40)]
    legacy = check_artifact_lifecycle(template)
    assert legacy["creation_rate_per_civ_per_100"] == 10.0
    assert check_artifact_lifecycle(template, starting_civs=[4]) == legacy
    assert check_artifact_lifecycle(procedural, starting_civs=[10])["creation_rate_per_civ_per_100"] == 4.0
    runs = [{"bundle": procedural[0], "world": {"generator": "procedural", "regions": 32, "civs": 10}}]
    assert run_artifact_oracle(runs)["creation_rate_per_civ_per_100"] == 4.0
    # A seed run without a recorded world counts the template world's 4 civs.
    assert run_artifact_oracle([{"bundle": procedural[0]}])["creation_rate_per_civ_per_100"] == 10.0
    with pytest.raises(ValueError):
        check_artifact_lifecycle(procedural, starting_civs=[10, 4])


def _report(worlds=None) -> dict:
    report = {"results": {name: {"status": "PASS"} for name in
                          ("community", "needs", "cohort", "era", "artifacts", "arcs", "regression")}}
    if worlds is not None:
        report["worlds"] = worlds
    return report


def test_comparator_rejects_reports_of_different_worlds():
    from chronicler.validation_compare import compare_validation_reports

    procedural = [{"generator": "procedural", "regions": 32, "civs": 10, "seeds": 20}]
    same_shape = [{"generator": "procedural", "regions": 32, "civs": 10, "seeds": 100}]
    compare_validation_reports("subset", _report(), _report())
    compare_validation_reports("subset", _report(procedural), _report(same_shape))
    with pytest.raises(ValidationGateInputError, match="different worlds"):
        compare_validation_reports("subset", _report(), _report(procedural))
    with pytest.raises(ValidationGateInputError, match="different worlds"):
        compare_validation_reports(
            "subset", _report(procedural),
            _report([{"generator": "procedural", "regions": 48, "civs": 12, "seeds": 20}]),
        )
