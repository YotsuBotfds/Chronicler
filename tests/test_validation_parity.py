"""Parity pins for the two validation orchestration and CLI surfaces.

``chronicler.validate`` and ``chronicler.validation_io`` each expose
``run_oracles`` and ``main``. They are distinct compatibility surfaces
(``docs/integration/validation-split.md``): ``validate`` dispatches through
its ``ORACLE_RUNNERS`` registry, ``validation_io`` through its module-level
``run_*`` functions, each resolves its collaborators in its own module, and
their ``--require-causal-oracles`` help texts differ. These tests pin both
surfaces' current output byte for byte on small deterministic synthetic
batches, the import surface, and which monkeypatch targets reach which
surface, so the validation split can be refactored against them.

The goldens in ``tests/fixtures/validation_parity/goldens.json`` were
generated from ``fb25429`` before the split. Paths and input-file digests
are replaced by stable labels (``_Normalizer``) so the goldens do not
depend on the temporary directory, the path separator or the byte layout
of a pyarrow version; every other byte is compared exactly, except that
argparse help and usage text is compared with runs of whitespace collapsed
(its wrapping depends on the terminal width and the Python version).
"""
from __future__ import annotations

import argparse
import importlib
import json
import random
from pathlib import Path

import pyarrow as pa
import pyarrow.ipc as ipc
import pytest

from chronicler import validate, validation_io, validation_oracles
from chronicler.artifact_io import strict_json_dumps
from chronicler.batch_manifest import file_sha256

SURFACES = ("chronicler.validate", "chronicler.validation_io")
GOLDENS_PATH = Path(__file__).parent / "fixtures" / "validation_parity" / "goldens.json"
GOLDENS = json.loads(GOLDENS_PATH.read_text(encoding="utf-8"))

CIVS = ("Aram", "Belos", "Cyra")
REGIONS = ("Ash", "Brine", "Cedar", "Dune")
TURNS = 160
SNAPSHOT_TURNS = (100, 110, 120, 130)
AGENTS = 32
NEEDS_FIELDS = ("satisfaction", "safety", "autonomy", "social", "spiritual", "material", "purpose",
                "boldness", "ambition", "loyalty_trait")


# ---------------------------------------------------------------------------
# Deterministic synthetic batches
# ---------------------------------------------------------------------------

def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # No newlines: the bytes (and their digests) are the same on every platform.
    path.write_bytes(json.dumps(payload, sort_keys=True).encode("utf-8"))


def _write_arrow(path: Path, columns: dict, types: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    table = pa.table({name: pa.array(values, types[name]) for name, values in columns.items()})
    with ipc.new_file(path, table.schema) as writer:
        writer.write_table(table)


def _bundle(seed: int, *, turns: int = TURNS, procedural: bool = False, history: bool = True) -> dict:
    rng = random.Random(seed)
    population = {civ: 60 + 15 * index for index, civ in enumerate(CIVS)}
    treasury = {civ: 40 + 5 * index for index, civ in enumerate(CIVS)}
    snapshots = []
    for turn in range(turns + 1 if history else 0):
        civ_stats = {}
        for index, civ in enumerate(CIVS):
            # The last civ collapses around turn 90 and partly recovers.
            if index == len(CIVS) - 1 and 88 <= turn <= 96:
                population[civ] = max(1, int(population[civ] * 0.8))
            else:
                population[civ] = max(1, population[civ] + rng.randint(-3, 4))
            treasury[civ] = treasury[civ] + rng.randint(-4, 5)
            civ_stats[civ] = {
                "population": population[civ],
                "treasury": treasury[civ],
                "stability": rng.randint(20, 90),
                "regions": list(REGIONS[index:index + 1 + (turn > 80 and index == 0)]),
                "prestige": turn // (5 + index) + rng.randint(0, 2),
                "gini": round(0.3 + rng.random() * 0.3, 3),
                "alive": True,
            }
        snapshots.append({"turn": turn, "civ_stats": civ_stats})
    world = {
        "turn": turns,
        "agent_mode": "hybrid",
        "regions": [{"name": name, "population": 20 + 3 * index} for index, name in enumerate(REGIONS)],
        "artifacts": [
            {"artifact_type": kind, "status": status, "mule_origin": index % 5 == 0}
            for index, (kind, status) in enumerate(
                (("relic", "active"), ("monument", "lost"), ("treatise", "active"), ("epic", "destroyed"),
                 ("artwork", "active"), ("relic", "active"), ("monument", "active"), ("treatise", "lost"),
                 ("relic", "active"), ("epic", "active"), ("artwork", "active"), ("relic", "active")))
        ],
    }
    if procedural:
        world["geography"] = {"generator": "procedural"}
    events = [
        {"turn": 89, "event_type": "famine", "actors": [CIVS[-1]]},
        {"turn": 91, "event_type": "plague", "civs": [CIVS[-1]]},
        {"turn": 120, "event_type": "war_declared", "actors": [CIVS[0], CIVS[1]]},
        {"turn": 130, "event_type": "festival", "actors": [CIVS[1]]},
    ]
    return {
        "metadata": {"seed": seed, "total_turns": turns, "bundle_version": 4,
                     "generated_at": "2026-11-04T00:00:00Z"},
        "world_state": world,
        "history": snapshots,
        "events_timeline": events,
        "named_events": [],
        "chronicle_entries": [],
        "era_reflections": {},
    }


def _agent_event_rows(seed: int, turns: int = TURNS) -> list[tuple[int, int, str]]:
    rng = random.Random(seed * 7 + 1)
    rows = []
    dead: set[int] = set()
    for turn in range(turns):
        for agent in range(AGENTS):
            if agent in dead:
                continue
            draw = rng.random()
            if draw < 0.05:
                rows.append((turn, agent, "migration"))
            elif draw < 0.065:
                rows.append((turn, agent, "rebellion"))
            elif draw < 0.095:
                rows.append((turn, agent, "occupation_switch"))
            elif draw < 0.1 and turn > 105 and agent % 7 == 3:
                rows.append((turn, agent, "death"))
                dead.add(agent)
            elif draw < 0.104:
                rows.append((turn, agent, "birth"))
    return rows


def _event_table(rows) -> tuple[dict, dict]:
    columns = {"turn": [row[0] for row in rows], "agent_id": [row[1] for row in rows],
               "event_type": [row[2] for row in rows]}
    return columns, {"turn": pa.uint32(), "agent_id": pa.uint32(), "event_type": pa.string()}


def _write_sidecars(seed_dir: Path, seed: int) -> None:
    rng = random.Random(seed * 13 + 5)
    _write_arrow(seed_dir / "agent_events.arrow", *_event_table(_agent_event_rows(seed)))
    needs = {"turn": [], "agent_id": [], "region": [], "civ_affinity": [], "occupation": []}
    needs.update({name: [] for name in NEEDS_FIELDS})
    rel = {"turn": [], "agent_id": [], "target_id": [], "bond_type": [], "sentiment": []}
    mem = {"turn": [], "agent_id": [], "event_type": [], "memory_turn": [], "valence_sign": []}
    for turn in SNAPSHOT_TURNS:
        for agent in range(AGENTS):
            needs["turn"].append(turn)
            needs["agent_id"].append(agent)
            needs["region"].append(agent % len(REGIONS))
            needs["civ_affinity"].append(agent % len(CIVS))
            needs["occupation"].append((agent + turn // 10) % 5)
            for name in NEEDS_FIELDS:
                needs[name].append(round(rng.random(), 3))
            # Dense ties within a region group, sparse ones across groups;
            # every ninth agent has no group ties (a non-member to pair with).
            for target in range(agent + 1, AGENTS):
                same_group = (agent % len(REGIONS) == target % len(REGIONS)
                              and agent % 9 != 8 and target % 9 != 8)
                if same_group or rng.random() < 0.08:
                    bond = (6, 4, 5, 2, 1)[(agent + target) % 5] if same_group else 7
                    for name, value in zip(rel, (turn, agent, target, bond, rng.randint(-20, 90))):
                        rel[name].append(value)
            # Region-mates share one memory; loners hold their own.
            memory = (agent % len(REGIONS), turn - 5, 1) if agent % 9 != 8 else (7, turn - 3 - agent % 4, -1)
            for name, value in zip(mem, (turn, agent, *memory)):
                mem[name].append(value)
    float_type = pa.float64()
    _write_arrow(seed_dir / "validation_needs.arrow", needs,
                 {**{name: pa.uint32() for name in ("turn", "agent_id")},
                  **{name: pa.uint16() for name in ("region", "civ_affinity", "occupation")},
                  **{name: float_type for name in NEEDS_FIELDS}})
    _write_arrow(seed_dir / "validation_relationships.arrow", rel,
                 {"turn": pa.uint32(), "agent_id": pa.uint32(), "target_id": pa.uint32(),
                  "bond_type": pa.uint8(), "sentiment": pa.int8()})
    _write_arrow(seed_dir / "validation_memory_signatures.arrow", mem,
                 {"turn": pa.uint32(), "agent_id": pa.uint32(), "event_type": pa.uint8(),
                  "memory_turn": pa.uint32(), "valence_sign": pa.int8()})
    aggregates = {}
    for turn in range(100, TURNS + 1, 10):
        aggregates[str(turn)] = {
            f"civ_{index}": {
                "satisfaction_mean": round(0.42 + rng.random() * 0.2, 4),
                "satisfaction_std": round(0.1 + rng.random() * 0.1, 4),
                "agent_count": 6 + index + turn // 40,
                "occupation_counts": {str(occupation): 1 + (occupation + index) % 3 for occupation in range(5)},
                "gini": round(0.3 + rng.random() * 0.3, 4),
            }
            for index in range(len(CIVS))
        }
    _write_json(seed_dir / "validation_summary.json", {"agent_aggregates_by_turn": aggregates})


def _seed_files(seed_dir: Path, root: Path) -> dict:
    return {path.relative_to(root).as_posix(): file_sha256(path)
            for path in sorted(seed_dir.iterdir()) if path.is_file()}


def _write_manifest(root: Path, runs: list[dict], seeds: list[int], turns: int) -> None:
    _write_json(root / "batch_manifest.json", {
        "kind": "chronicler-batch", "schema_version": 1, "status": "complete", "seeds": seeds,
        "turns": turns, "simulation": {"turns": turns, "agents": "hybrid"}, "runs": runs})


def _rich_batch(root: Path, seeds=(42, 43, 44)) -> Path:
    """Three seeds with every sidecar the oracles read and a verified manifest."""
    runs = []
    for seed in seeds:
        seed_dir = root / f"seed_{seed}"
        _write_json(seed_dir / "chronicle_bundle.json", _bundle(seed))
        _write_sidecars(seed_dir, seed)
        runs.append({"seed": seed, "dir": seed_dir.name, "bundle": f"{seed_dir.name}/chronicle_bundle.json",
                     "total_turns": TURNS, "files": _seed_files(seed_dir, root)})
    _write_manifest(root, runs, list(seeds), TURNS)
    return root


def _determinism_batch(root: Path) -> Path:
    """Seeds 7, 7, 8, 8: the 7 pair differs only in ``generated_at``, the 8 pair in a stat."""
    runs = []
    for index, seed in enumerate((7, 7, 8, 8)):
        bundle = _bundle(seed, turns=20)
        bundle["metadata"]["generated_at"] = f"2026-11-04T00:00:0{index}Z"
        if index == 3:
            bundle["history"][5]["civ_stats"][CIVS[0]]["treasury"] += 1
        run_dir = root / f"run_{index}"
        _write_json(run_dir / "chronicle_bundle.json", bundle)
        runs.append({"seed": seed, "dir": run_dir.name, "bundle": f"{run_dir.name}/chronicle_bundle.json",
                     "total_turns": 20, "files": _seed_files(run_dir, root)})
    _write_manifest(root, runs, [7, 7, 8, 8], 20)
    return root


def _legacy_procedural_batch(root: Path) -> Path:
    """No manifest; one procedural world with events only and one bare template bundle."""
    seed_dir = root / "seed_5"
    _write_json(seed_dir / "chronicle_bundle.json", _bundle(5, procedural=True))
    _write_arrow(seed_dir / "agent_events.arrow", *_event_table(_agent_event_rows(5)))
    _write_json(root / "seed_6" / "chronicle_bundle.json", _bundle(6, turns=40, history=False))
    return root


def _broken_batch(root: Path) -> Path:
    """A needs table without its personality columns: the needs and cohort oracles raise."""
    _rich_batch(root, seeds=(11,))
    seed_dir = root / "seed_11"
    table = ipc.open_file(seed_dir / "validation_needs.arrow").read_all()
    table = table.drop_columns(["boldness", "ambition", "loyalty_trait"])
    with ipc.new_file(seed_dir / "validation_needs.arrow", table.schema) as writer:
        writer.write_table(table)
    manifest = json.loads((root / "batch_manifest.json").read_text(encoding="utf-8"))
    manifest["runs"][0]["files"] = _seed_files(seed_dir, root)
    _write_json(root / "batch_manifest.json", manifest)
    return root


def _nonfinite_batch(root: Path) -> Path:
    """A summary whose satisfaction is NaN: the report cannot be written as strict JSON."""
    _rich_batch(root, seeds=(12,))
    seed_dir = root / "seed_12"
    summary = json.loads((seed_dir / "validation_summary.json").read_text(encoding="utf-8"))
    for civs in summary["agent_aggregates_by_turn"].values():
        civs["civ_0"]["satisfaction_mean"] = float("nan")
    (seed_dir / "validation_summary.json").write_bytes(json.dumps(summary, sort_keys=True).encode("utf-8"))
    manifest = json.loads((root / "batch_manifest.json").read_text(encoding="utf-8"))
    manifest["runs"][0]["files"] = _seed_files(seed_dir, root)
    _write_json(root / "batch_manifest.json", manifest)
    return root


def _ablation_arms(batch: Path, arms_root: Path, *, design: int, arms=("needs", "kin_roots")) -> Path:
    """Arms forked at turn 100 for every seed of ``batch``, sharing the plain prefix."""
    from chronicler.ablation_arms import ABLATION_MANIFEST_FILENAME, ABLATION_MANIFEST_KIND

    plain = json.loads((batch / "batch_manifest.json").read_text(encoding="utf-8"))
    forks = []
    for arm_index, arm in enumerate(arms):
        for run in plain["runs"]:
            seed = run["seed"]
            fork = arms_root / arm / run["dir"] / "fork_100"
            prefix = [row for row in _agent_event_rows(seed) if row[0] <= 100]
            rng = random.Random(seed * 31 + arm_index)
            tail = [(turn, agent, kind) for turn in range(101, 121) for agent in range(AGENTS)
                    for kind in ("migration", "rebellion", "occupation_switch")
                    if rng.random() < (0.01 if arm_index == 0 else 0.02)]
            _write_arrow(fork / "agent_events.arrow", *_event_table(prefix + tail))
            _write_json(fork / "fork.json", {"decision_ablation": {"name": arm, "start_turn": 101, "forked_at": 101}})
            forks.append({"arm": arm, "seed": seed, "fork_turn": 100, "dir": f"{arm}/{run['dir']}/fork_100",
                          "files": {name: file_sha256(fork / name) for name in ("agent_events.arrow", "fork.json")}})
    manifest = {"kind": ABLATION_MANIFEST_KIND, "schema_version": design, "status": "complete",
                "plain_manifest_sha256": file_sha256(batch / "batch_manifest.json"),
                "arms": list(arms), "window_turns": 20, "fork_turns": [100], "seeds": plain["seeds"],
                "forks": forks}
    if design >= 2:
        manifest["design"] = design
    _write_json(arms_root / ABLATION_MANIFEST_FILENAME, manifest)
    return arms_root


def _build_workspace(root: Path) -> tuple[dict, "_Normalizer"]:
    rich = _rich_batch(root / "rich")
    inputs = {
        "rich": rich,
        "determinism": _determinism_batch(root / "determinism"),
        "legacy": _legacy_procedural_batch(root / "legacy"),
        "broken": _broken_batch(root / "broken"),
        "nonfinite": _nonfinite_batch(root / "nonfinite"),
        "arms_design1": _ablation_arms(rich, root / "arms_design1", design=1),
        "arms_design2": _ablation_arms(rich, root / "arms_design2", design=2, arms=("needs", "kin_roots", "placebo")),
        "missing": root / "missing",
    }
    return inputs, _Normalizer(root)


@pytest.fixture(scope="module")
def workspace(tmp_path_factory):
    """Every synthetic input under one root, plus the normalizer for it.

    The validators only read their inputs, so one workspace serves every test.
    """
    return _build_workspace(tmp_path_factory.mktemp("validation_parity") / "ws")


class _Normalizer:
    """Replace the workspace's paths and its files' digests by stable labels."""

    def __init__(self, root: Path):
        self.replacements: list[tuple[str, str]] = []
        paths = [root, *sorted(root.rglob("*"))]
        for path in paths:
            label = "<WS>" + ("/" + path.relative_to(root).as_posix() if path != root else "")
            self.replacements.append((json.dumps(str(path))[1:-1], label))
            self.replacements.append((str(path), label))
            if path.is_file():
                self.replacements.append((file_sha256(path), f"<sha256:{label[5:]}>"))
        # Longest first, so a parent never replaces part of a child's path.
        self.replacements.sort(key=lambda item: len(item[0]), reverse=True)

    def __call__(self, text: str) -> str:
        for old, new in self.replacements:
            text = text.replace(old, new)
        return text


def _golden_text(section: str, case: str) -> str:
    """A pinned report as the validator writes it (the fixture keeps it as a
    JSON object for review; the generator checked the round trip is exact)."""
    return strict_json_dumps(GOLDENS[section][case])


def _collapse(text: str) -> str:
    return " ".join(text.split())


def _prog() -> str:
    """The program name argparse derives in this process (Python-version dependent)."""
    return argparse.ArgumentParser().prog




# ---------------------------------------------------------------------------
# run_oracles and main(argv): every scenario through both surfaces
# ---------------------------------------------------------------------------

# name: (batch, oracles, run_oracles options). Each also runs as a CLI
# (``_argv``) whose stdout must be the same report text.
RUN_CASES = {
    "rich_all": ("rich", ["all"], {}),
    "rich_all_full_design2_causal": (
        "rich", ["all"], {"profile": "full", "ablation_dir": "arms_design2", "require_causal": True}),
    "rich_needs_cohort_design1": ("rich", ["needs", "cohort"], {"profile": "subset", "ablation_dir": "arms_design1"}),
    "rich_subset_no_causal": ("rich", ["community", "era", "arcs"], {"profile": "subset", "require_causal": False}),
    "rich_empty_selection": ("rich", [], {}),
    "determinism_all": ("determinism", ["all"], {}),
    "determinism_only": ("determinism", ["determinism"], {"profile": "determinism-off"}),
    "legacy_all": ("legacy", ["all"], {"legacy_batch": True, "profile": "subset"}),
    "broken_error_result": ("broken", ["needs", "artifacts"], {}),
}

# run_oracles raises ValidationRequestError; the CLI writes an error report and exits 1.
REQUEST_ERROR_CASES = {
    "unknown_oracle": ("rich", ["all", "bogus"], {}),
    "all_with_explicit": ("rich", ["all", "needs"], {}),
    "missing_batch": ("missing", ["needs"], {}),
    "manifest_required": ("legacy", ["artifacts"], {}),
    "ablation_dir_missing": ("rich", ["needs"], {"ablation_dir": "missing"}),
}

# argparse's own output and exits, compared with whitespace collapsed.
ARGPARSE_CASES = {
    "help": ["--help"],
    "no_arguments": [],
    "bad_profile": ["--batch-dir", "batch", "--profile", "zzz-not-a-profile"],
}


def _resolve(inputs: dict, batch: str, options: dict) -> tuple[Path, dict]:
    options = dict(options)
    if "ablation_dir" in options:
        options["ablation_dir"] = inputs[options["ablation_dir"]]
    return inputs[batch], options


def _argv(inputs: dict, batch: str, oracles: list[str], options: dict) -> list[str]:
    argv = ["--batch-dir", str(inputs[batch])]
    if oracles != ["all"]:
        argv += ["--oracles", *oracles]
    if options.get("profile") is not None:
        argv += ["--profile", options["profile"]]
    if options.get("legacy_batch"):
        argv.append("--legacy-batch")
    if "ablation_dir" in options:
        argv += ["--ablation-dir", str(inputs[options["ablation_dir"]])]
    if options.get("require_causal") is not None:
        argv.append("--require-causal-oracles" if options["require_causal"] else "--no-require-causal-oracles")
    return argv


def _run(surface: str, inputs: dict, case: tuple, **extra) -> dict:
    batch, oracles, options = case
    batch_dir, resolved = _resolve(inputs, batch, options)
    return importlib.import_module(surface).run_oracles(batch_dir, list(oracles), **resolved, **extra)


def _run_main(surface: str, argv: list[str], capsys) -> tuple[int, str, str]:
    capsys.readouterr()
    try:
        status = importlib.import_module(surface).main(argv)
    except SystemExit as exc:  # argparse's own exits
        status = exc.code
    captured = capsys.readouterr()
    return status, captured.out, captured.err


@pytest.fixture
def stable_argparse(monkeypatch):
    monkeypatch.setenv("COLUMNS", "80")
    monkeypatch.setenv("NO_COLOR", "1")
    for name in ("FORCE_COLOR", "PYTHON_COLORS"):
        monkeypatch.delenv(name, raising=False)


@pytest.mark.parametrize("surface", SURFACES)
@pytest.mark.parametrize("case", sorted(RUN_CASES))
def test_run_oracles_reports_are_pinned(workspace, surface, case):
    inputs, normalize = workspace
    report = _run(surface, inputs, RUN_CASES[case])
    # The JSON text is what the CLI writes; its key order is part of the bytes.
    assert normalize(strict_json_dumps(report)) == _golden_text("run_oracles", case)


@pytest.mark.parametrize("surface", SURFACES)
@pytest.mark.parametrize("case", sorted(set(RUN_CASES) - {"rich_empty_selection"}))
def test_cli_writes_the_same_report_with_a_pinned_exit_status(workspace, capsys, surface, case):
    inputs, normalize = workspace
    status, out, err = _run_main(surface, _argv(inputs, *RUN_CASES[case]), capsys)
    assert (status, normalize(out), err) == (GOLDENS["cli_status"][case], _golden_text("run_oracles", case), "")


@pytest.mark.parametrize("surface", SURFACES)
@pytest.mark.parametrize("case", sorted(REQUEST_ERROR_CASES))
def test_request_errors_are_pinned(workspace, capsys, surface, case):
    inputs, normalize = workspace
    with pytest.raises(validation_io.ValidationRequestError) as raised:
        _run(surface, inputs, REQUEST_ERROR_CASES[case])
    assert type(raised.value) is validation_io.ValidationRequestError
    assert normalize(str(raised.value)) == GOLDENS["request_errors"][case]
    status, out, err = _run_main(surface, _argv(inputs, *REQUEST_ERROR_CASES[case]), capsys)
    assert (status, normalize(out), err) == (1, _golden_text("cli_error_reports", case), "")


@pytest.mark.parametrize("surface", SURFACES)
def test_a_nonfinite_report_is_returned_but_not_written(workspace, capsys, surface):
    inputs, normalize = workspace
    case = ("nonfinite", ["regression"], {})
    report = _run(surface, inputs, case)
    mean = report["results"]["regression"]["satisfaction_mean"]
    assert mean != mean  # NaN
    status, out, err = _run_main(surface, _argv(inputs, *case), capsys)
    assert (status, normalize(out), err) == (1, _golden_text("cli_error_reports", "nonfinite_report"), "")


@pytest.mark.parametrize("surface", SURFACES)
@pytest.mark.parametrize("case", sorted(ARGPARSE_CASES))
def test_argparse_output_is_pinned(stable_argparse, capsys, surface, case):
    status, out, err = _run_main(surface, ARGPARSE_CASES[case], capsys)
    out, err = (_collapse(text.replace(_prog(), "<prog>")) for text in (out, err))
    assert {"status": status, "stdout": out, "stderr": err} == GOLDENS["argparse"][case][surface]


def test_the_surfaces_differ_only_in_the_causal_flag_help(stable_argparse, capsys):
    """The documented mismatch (needs/cohort methods 8/5 against 7/4) stays each surface's own text."""
    help_text = {surface: _collapse(_run_main(surface, ["--help"], capsys)[1]) for surface in SURFACES}
    assert "(needs method 8, cohort method 5)" in help_text["chronicler.validate"]
    assert "(needs method 7, cohort method 4)" in help_text["chronicler.validation_io"]
    assert (help_text["chronicler.validate"].replace("method 8, cohort method 5", "*")
            == help_text["chronicler.validation_io"].replace("method 7, cohort method 4", "*"))
    for case in set(ARGPARSE_CASES) - {"help"}:
        assert (GOLDENS["argparse"][case]["chronicler.validate"]
                == GOLDENS["argparse"][case]["chronicler.validation_io"]), case


# ---------------------------------------------------------------------------
# Import surface
# ---------------------------------------------------------------------------

def _canonical(value):
    """A JSON form of a constant that does not depend on set iteration order."""
    if isinstance(value, (set, frozenset)):
        return {type(value).__name__: sorted(_canonical(item) for item in value)}
    if isinstance(value, tuple):
        return {"tuple": [_canonical(item) for item in value]}
    if isinstance(value, dict):
        return {"dict": [[_canonical(key), _canonical(item)] for key, item in value.items()]}
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    raise TypeError(f"no canonical form for {type(value).__name__}")


def _namespace(module) -> dict[str, str]:
    """Every non-module attribute of ``module`` and its kind."""
    import types

    names = {}
    for name, value in vars(module).items():
        if name.startswith("__") or isinstance(value, types.ModuleType):
            continue
        names[name] = "class" if isinstance(value, type) else "callable" if callable(value) else "value"
    return names


@pytest.mark.parametrize("module", [validation_io, validation_oracles, validate], ids=lambda m: m.__name__)
def test_all_lists_are_pinned_and_resolve(module):
    assert module.__all__ == GOLDENS["imports"]["__all__"][module.__name__]
    assert all(hasattr(module, name) for name in module.__all__)


def test_every_validation_io_name_stays_importable_with_its_kind():
    """Every name ``validation_io`` binds today (other than imported modules)
    stays importable from it, as the same kind of object."""
    current = _namespace(validation_io)
    pinned = GOLDENS["imports"]["validation_io_names"]
    assert {name: current.get(name) for name in pinned} == pinned


def test_validation_io_constants_keep_their_values():
    constants = GOLDENS["imports"]["validation_io_constants"]
    assert {name: _canonical(getattr(validation_io, name)) for name in constants} == constants


def test_reexports_are_the_same_objects():
    # Each surface binds its own entry points to its registry or module and
    # its help text. (The report helpers may be shared objects: what callers
    # rely on is that each main reads them from its own module, pinned by
    # test_cli_collaborators_resolve_in_their_own_surface.)
    own = {"run_oracles", "main", "_normalize_requested_oracles"}
    for name in validation_oracles.__all__:
        assert getattr(validation_oracles, name) is getattr(validation_io, name), name
    for name in set(validation_io.__all__) - own:
        assert getattr(validate, name) is getattr(validation_io, name), name
    for name in ("ABLATION_DIR_FLAG", "LEGACY_BATCH_FLAG", "MANIFEST_FILENAME", "_load_arms", "ablation_methods",
                 "check_batch_manifest", "summarize_world_shapes", "_prepare_batch_admission",
                 "causal_oracles_required", "CAUSAL_ORACLES_FLAG", "PROFILE_CHOICES", "strict_json_dumps",
                 "ArtifactIOError"):
        assert getattr(validate, name) is getattr(validation_io, name), name
    from chronicler import validation_gate
    assert validation_io.causal_oracles_required is validation_gate.causal_oracles_required
    for name in own:
        assert getattr(validate, name) is not getattr(validation_io, name), name


def test_the_validate_registry_holds_the_validation_io_runners():
    assert validate.ORACLE_RUNNERS == {
        "determinism": validation_io.run_determinism_gate, "community": validation_io.run_community_oracle,
        "needs": validation_io.run_needs_oracle, "era": validation_io.run_era_oracle,
        "cohort": validation_io.run_cohort_oracle, "artifacts": validation_io.run_artifact_oracle,
        "arcs": validation_io.run_arc_oracle, "regression": validation_io.run_regression_summary,
    }
    assert list(validate.ORACLE_RUNNERS) == ["determinism", "community", "needs", "era", "cohort", "artifacts",
                                             "arcs", "regression"]
    assert validate.SEED_RUN_ORACLES == validation_io.SEED_RUN_ORACLE_NAMES == set(validate.ORACLE_RUNNERS) - {
        "determinism"}
    assert validation_io.ORACLE_RUNNER_NAMES == set(validate.ORACLE_RUNNERS)


# ---------------------------------------------------------------------------
# Monkeypatch targets: which patch reaches which surface
# ---------------------------------------------------------------------------

def _counting(monkeypatch, module, name: str) -> list:
    original = getattr(module, name)
    calls = []

    def wrapper(*args, **kwargs):
        calls.append(args)
        return original(*args, **kwargs)

    monkeypatch.setattr(module, name, wrapper)
    return calls


# helper patched on validation_io: (batch, oracles, calls the patched helper sees)
IO_HELPER_PATCHES = {
    "_load_bundle": ("determinism", ["determinism"], 8),
    "_read_arrow_columns": ("rich", ["arcs"], 9),
    "_has_pyarrow": ("rich", ["regression"], 13),
    "_world_shape": ("rich", ["arcs"], 3),
    "_build_turn_rows": ("rich", ["arcs"], 9),
    "_filter_events_window": ("rich", ["cohort"], 12),
    "compute_cohort_distinctiveness": ("rich", ["cohort"], 24),
}


@pytest.mark.parametrize("surface", SURFACES)
@pytest.mark.parametrize("helper", sorted(IO_HELPER_PATCHES))
def test_helpers_patched_on_validation_io_reach_both_surfaces(workspace, monkeypatch, surface, helper):
    inputs, normalize = workspace
    batch, oracles, expected_calls = IO_HELPER_PATCHES[helper]
    unpatched = normalize(strict_json_dumps(_run(surface, inputs, (batch, oracles, {}))))
    calls = _counting(monkeypatch, validation_io, helper)
    report = _run(surface, inputs, (batch, oracles, {}))
    assert len(calls) == expected_calls
    assert normalize(strict_json_dumps(report)) == unpatched


@pytest.mark.parametrize("surface", SURFACES)
def test_missing_pyarrow_patched_on_validation_io_reaches_both_clis(workspace, monkeypatch, capsys, surface):
    inputs, normalize = workspace
    monkeypatch.setattr(validation_io, "_has_pyarrow", lambda: False)
    status, out, err = _run_main(surface, _argv(inputs, "rich", ["regression"], {}), capsys)
    assert (status, err) == (1, "")
    assert json.loads(out)["reason"] == "regression oracle requires pyarrow"


ORCHESTRATION_NAMES = ("load_seed_runs", "_prepare_batch_admission", "_load_arms", "ablation_methods",
                       "summarize_world_shapes", "causal_oracles_required", "_normalize_requested_oracles")


@pytest.mark.parametrize("surface", SURFACES)
@pytest.mark.parametrize("name", ORCHESTRATION_NAMES)
def test_orchestration_collaborators_resolve_in_their_own_surface(workspace, monkeypatch, surface, name):
    inputs, normalize = workspace
    case = ("rich", ["needs"], {"ablation_dir": "arms_design2"})
    other = SURFACES[1 - SURFACES.index(surface)]
    expected_other = normalize(strict_json_dumps(_run(other, inputs, case)))

    def sentinel(*args, **kwargs):
        raise validation_io.ValidationRequestError(f"sentinel {name}")

    monkeypatch.setattr(importlib.import_module(surface), name, sentinel)
    with pytest.raises(validation_io.ValidationRequestError, match=f"^sentinel {name}$"):
        _run(surface, inputs, case)
    assert normalize(strict_json_dumps(_run(other, inputs, case))) == expected_other


ORACLE_FUNCTIONS = {
    "determinism": "run_determinism_gate", "community": "run_community_oracle", "needs": "run_needs_oracle",
    "era": "run_era_oracle", "cohort": "run_cohort_oracle", "artifacts": "run_artifact_oracle",
    "arcs": "run_arc_oracle", "regression": "run_regression_summary",
}


def _fake_runner(oracle: str, seen: list):
    def fake(*args, **kwargs):
        seen.append((args, kwargs))
        return {"status": "PASS", "fake": oracle}
    return fake


# (oracle, run_oracles options, method version the registry's original
# function re-enters itself with through validation_io's module attribute).
# Community method 2 re-scores method 1, needs methods 7 and 8 method 6 and
# cohort methods 4 and 5 method 3, each by calling the module-level name;
# cohort method 6 (the current one without design-1 arms) does not.
DISPATCH_CASES = {
    "determinism": ("determinism", {}, None),
    "community": ("community", {}, 1),
    "needs": ("needs", {}, 6),
    "era": ("era", {}, None),
    "cohort": ("cohort", {}, None),
    "cohort_design1": ("cohort", {"ablation_dir": "arms_design1"}, 3),
    "artifacts": ("artifacts", {}, None),
    "arcs": ("arcs", {}, None),
    "regression": ("regression", {}, None),
}


@pytest.mark.parametrize("name", sorted(DISPATCH_CASES))
def test_validation_io_dispatches_through_its_module_functions(workspace, monkeypatch, name):
    inputs, normalize = workspace
    oracle, options, reentry = DISPATCH_CASES[name]
    case = ("determinism" if oracle == "determinism" else "rich", [oracle], options)
    expected_validate = normalize(strict_json_dumps(_run("chronicler.validate", inputs, case)))
    seen = []
    monkeypatch.setattr(validation_io, ORACLE_FUNCTIONS[oracle], _fake_runner(oracle, seen))
    assert _run("chronicler.validation_io", inputs, case)["results"][oracle] == {"status": "PASS", "fake": oracle}
    (args, kwargs), = seen
    if oracle == "determinism":
        # Always the admission-sharing call, even for a replacement function.
        assert args == (inputs["determinism"],) and set(kwargs) == {"_admission"}
    else:
        assert len(args) == 1 and [run["seed"] for run in args[0]] == [42, 43, 44]
    seen.clear()
    report = _run("chronicler.validate", inputs, case)
    if reentry is None:
        # The validate registry captured the functions at import: the patch does not reach it.
        assert normalize(strict_json_dumps(report)) == expected_validate
        assert seen == []
    else:
        # The registry's original function re-enters through the patched module attribute.
        assert normalize(strict_json_dumps(report)) != expected_validate
        assert [call[1]["method_version"] for call in seen] == [reentry]


@pytest.mark.parametrize("oracle", sorted(ORACLE_FUNCTIONS))
def test_validate_dispatches_through_its_registry(workspace, monkeypatch, oracle):
    inputs, normalize = workspace
    case = ("determinism" if oracle == "determinism" else "rich", [oracle], {})
    expected_io = normalize(strict_json_dumps(_run("chronicler.validation_io", inputs, case)))
    expected_validate = normalize(strict_json_dumps(_run("chronicler.validate", inputs, case)))
    # A module attribute of validate is not the registry.
    if oracle != "determinism":
        monkeypatch.setattr(validate, ORACLE_FUNCTIONS[oracle], _fake_runner(oracle, []))
        assert normalize(strict_json_dumps(_run("chronicler.validate", inputs, case))) == expected_validate
    seen = []
    monkeypatch.setitem(validate.ORACLE_RUNNERS, oracle, _fake_runner(oracle, seen))
    report = _run("chronicler.validate", inputs, case)
    assert report["results"][oracle] == {"status": "PASS", "fake": oracle}
    assert report["batch_manifest"]["status"] == "verified"
    (args, kwargs), = seen
    if oracle == "determinism":
        # A replacement determinism runner keeps the standalone signature.
        assert (args, kwargs) == ((inputs["determinism"],), {})
    elif oracle == "needs":
        assert set(kwargs) == {"profile", "ablation", "placebo", "require_causal", "method_version"}
    elif oracle == "cohort":
        assert set(kwargs) == {"ablation", "placebo", "community", "require_causal", "method_version"}
    else:
        assert kwargs == {}
    assert normalize(strict_json_dumps(_run("chronicler.validation_io", inputs, case))) == expected_io


def test_patching_validate_run_determinism_gate_selects_the_standalone_call(workspace, monkeypatch):
    """The registry entry is compared with validate's module attribute: when
    they differ, the registry's runner is called without the admission, after
    the admission has observed every bundle (more bundle reads)."""
    inputs, normalize = workspace
    case = ("determinism", ["determinism"], {})
    expected = normalize(strict_json_dumps(_run("chronicler.validate", inputs, case)))
    reads = _counting(monkeypatch, validation_io, "_load_bundle")
    _run("chronicler.validate", inputs, case)
    assert len(reads) == 8
    reads.clear()
    monkeypatch.setattr(validate, "run_determinism_gate", _fake_runner("determinism", []))
    report = _run("chronicler.validate", inputs, case)
    assert normalize(strict_json_dumps(report)) == expected
    assert len(reads) == 12


def test_the_validate_registry_can_gain_and_lose_oracles(workspace, monkeypatch):
    inputs, normalize = workspace
    seen = []
    monkeypatch.setitem(validate.ORACLE_RUNNERS, "custom", _fake_runner("custom", seen))
    report = validate.run_oracles(inputs["rich"], ["custom"])
    assert report["oracles"] == ["custom"] and report["results"] == {"custom": {"status": "PASS", "fake": "custom"}}
    assert [run["seed"] for run in seen[0][0][0]] == [42, 43, 44]
    assert "custom" in validate.run_oracles(inputs["rich"], ["all"])["oracles"]
    with pytest.raises(validation_io.ValidationRequestError, match="unknown_oracles: custom"):
        validation_io.run_oracles(inputs["rich"], ["custom"])
    monkeypatch.delitem(validate.ORACLE_RUNNERS, "custom")
    monkeypatch.delitem(validate.ORACLE_RUNNERS, "era")
    assert "era" not in validate.run_oracles(inputs["rich"], ["all"])["oracles"]
    with pytest.raises(validation_io.ValidationRequestError, match="unknown_oracles: era"):
        validate.run_oracles(inputs["rich"], ["era"])
    assert "era" in validation_io.run_oracles(inputs["rich"], ["all"])["oracles"]


CLI_NAMES = ("run_oracles", "_dump_report", "_error_report", "_serialization_error_report")


@pytest.mark.parametrize("surface", SURFACES)
@pytest.mark.parametrize("name", CLI_NAMES)
def test_cli_collaborators_resolve_in_their_own_surface(workspace, monkeypatch, capsys, surface, name):
    inputs, normalize = workspace
    case = {"run_oracles": ("rich", ["arcs"], {}), "_dump_report": ("rich", ["arcs"], {}),
            "_error_report": ("rich", ["bogus"], {}),
            "_serialization_error_report": ("nonfinite", ["regression"], {})}[name]
    argv = _argv(inputs, *case)
    other = SURFACES[1 - SURFACES.index(surface)]
    expected = {module: _run_main(module, argv, capsys) for module in SURFACES}
    calls = _counting(monkeypatch, importlib.import_module(surface), name)
    assert _run_main(surface, argv, capsys) == expected[surface]
    assert len(calls) == 1
    calls.clear()
    assert _run_main(other, argv, capsys) == expected[other]
    assert calls == []
