"""Compatibility for callers importing historical module attributes directly."""

import ast
import importlib
import os
from pathlib import Path
import random
import subprocess
import sys
from dataclasses import dataclass, field as dataclass_field

import pytest

from chronicler.leaders import _pick_regnal_name as leaders_pick_regnal_name
from chronicler.memory import field as memory_field
from chronicler.models import Civilization, Leader, WorldState, field as models_field
from chronicler.world_gen import _pick_regnal_name as world_gen_pick_regnal_name


def test_module_import_aliases_remain_callable():
    assert memory_field is dataclass_field
    assert models_field is dataclass_field
    assert world_gen_pick_regnal_name is leaders_pick_regnal_name

    @dataclass
    class CallerRecord:
        memories: list[str] = memory_field(default_factory=list)
        counts: dict[str, int] = models_field(default_factory=dict)

    record = CallerRecord()
    assert record.memories == []
    assert record.counts == {}

    civ = Civilization(
        name="Test Realm",
        leader=Leader(name="Founder", trait="bold", reign_start=0),
        leader_name_pool=["Arin"],
    )
    world = WorldState(name="Import compatibility", seed=1, civilizations=[civ])
    _, throne_name, ordinal = world_gen_pick_regnal_name(civ, world, random.Random(1))
    assert (throne_name, ordinal) == ("Arin", 0)
    assert civ.regnal_name_counts["Arin"] == 1


# Detached harness modules relocated (or to be relocated) to ``chronicler_lab``
# (DEC-6: validation_compare and community_admissibility stay in chronicler).
LAB_MODULES = (
    "experiment_sessions", "memome_experiment", "session_operations", "session_comparison",
    "experiment_receipt_inspector", "memome_candidate_preview", "campaign_order_preview",
    "campaign_snapshot_adapter", "snapshot_campaign_sessions",
    "governance_measurements", "governance_capture", "governance_sequence",
    "expansion_audit", "expansion_compare", "scientific_research_audit",
    "scientific_receipts_audit", "history_forensics", "evidence_admission",
    "health_care_observation_codec", "health_care_observation_mechanics",
    "health_care_capture", "artifact_budget",
    "practice_growth", "decision_delivery", "kin_root_exposure", "shadow_oracle",
    "checkpoint_replay",
)
LAB_CLI_MODULES = ("expansion_audit", "expansion_compare", "history_forensics",
                   "evidence_admission", "checkpoint_replay")
# Loaded through ``import_module("chronicler." + name)`` string building.
DYNAMIC_PRODUCTION_MODULES = ("learning_cohorts", "remittances", "timber_orders", "wealth_accounting")
PRODUCTION_ROOTS = ("main", "live", "validate", "narration_audit")
REPO = Path(__file__).resolve().parents[1]
PRODUCTION = REPO / "src" / "chronicler"
LAB = REPO / "src" / "chronicler_lab"


def _shims():
    return tuple(line.strip() for line in (LAB / "SHIMS").read_text().splitlines() if line.strip())


def _production_files():
    excluded = set(_shims()) | set(LAB_MODULES)
    return [path for path in sorted(PRODUCTION.rglob("*.py"))
            if not (path.parent == PRODUCTION and path.stem in excluded)]


def test_lab_module_lists_are_consistent():
    assert len(LAB_MODULES) == len(set(LAB_MODULES)) == 27
    assert set(LAB_CLI_MODULES) <= set(LAB_MODULES)
    assert set(_shims()) <= set(LAB_MODULES)
    for name in LAB_MODULES:
        assert (PRODUCTION / f"{name}.py").is_file() or (LAB / f"{name}.py").is_file(), name
    for name in _shims():
        assert (LAB / f"{name}.py").is_file(), name


def test_production_never_imports_chronicler_lab():
    forbidden = set(_shims()) | set(LAB_MODULES)
    forbidden |= {f"chronicler.{name}" for name in tuple(forbidden)}
    forbidden |= {f"chronicler_lab.{name}" for name in LAB_MODULES}
    hits = []
    for path in _production_files():
        where = path.relative_to(REPO).as_posix()
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"), filename=where)):
            if isinstance(node, ast.Import):
                hits += [(where, node.lineno, a.name) for a in node.names
                         if a.name == "chronicler_lab" or a.name.startswith("chronicler_lab.")]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                if node.module == "chronicler_lab" or node.module.startswith("chronicler_lab."):
                    hits.append((where, node.lineno, node.module))
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                if node.value in forbidden or node.value == "chronicler_lab":
                    hits.append((where, node.lineno, node.value))
    assert hits == []


def _module_dependencies(path, package_dir, names):
    """Module names under ``chronicler`` (or ``chronicler_lab``) one file reaches."""
    in_subpackage = path.parent != package_dir
    out = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            for alias in node.names:
                parts = alias.name.split(".")
                if parts[0] in ("chronicler", "chronicler_lab") and len(parts) > 1:
                    out.add(parts[1])
        elif isinstance(node, ast.ImportFrom):
            # Absolute; level 1 in a top-level module or level 2 in a subpackage means chronicler.
            parent_level = 2 if in_subpackage else 1
            if node.level == 0 and node.module:
                parts = node.module.split(".")
                if parts[0] in ("chronicler", "chronicler_lab"):
                    out |= {parts[1]} if len(parts) > 1 else {a.name for a in node.names}
            elif node.level == parent_level:
                out |= {node.module.split(".")[0]} if node.module else {a.name for a in node.names}
        elif isinstance(node, ast.Call):
            func = node.func
            called = getattr(func, "attr", getattr(func, "id", ""))
            if called in ("import_module", "__import__") and node.args:
                first = node.args[0]
                if isinstance(first, ast.Constant) and isinstance(first.value, str):
                    parts = first.value.split(".")
                    if parts[0] in ("chronicler", "chronicler_lab") and len(parts) > 1:
                        out.add(parts[1])
                else:
                    out |= set(DYNAMIC_PRODUCTION_MODULES)
    return out & names


def test_lab_modules_not_reachable_from_roots():
    modules = {path.stem for path in PRODUCTION.glob("*.py")} | {path.stem for path in LAB.glob("*.py")}
    subpackages = {path.name for path in PRODUCTION.iterdir()
                   if path.is_dir() and (path / "__init__.py").exists()}
    names = (modules | subpackages) - {"__init__"}
    graph = {}
    for path in PRODUCTION.glob("*.py"):
        graph[path.stem] = _module_dependencies(path, PRODUCTION, names)
    for path in LAB.glob("*.py"):
        graph.setdefault(path.stem, set()).update(_module_dependencies(path, LAB, names))
    for name in subpackages:
        graph[name] = set().union(*(_module_dependencies(path, PRODUCTION, names)
                                    for path in (PRODUCTION / name).rglob("*.py")))
    seen, stack = set(), list(PRODUCTION_ROOTS)
    while stack:
        name = stack.pop()
        if name not in seen:
            seen.add(name)
            stack += graph.get(name, ())
    assert set(PRODUCTION_ROOTS) <= seen
    assert set(DYNAMIC_PRODUCTION_MODULES) <= seen
    assert sorted(seen & set(LAB_MODULES)) == []


def test_shims_are_identity_aliases():
    for name in _shims():
        assert importlib.import_module("chronicler." + name) is importlib.import_module("chronicler_lab." + name)


@pytest.mark.real_process
@pytest.mark.skipif("python_oracle_guard" in sys.modules,
                    reason="starts child processes; the offline oracle lane forbids them")
def test_cli_shims_run_as_module():
    environment = dict(os.environ, PYTHONPATH=str(REPO / "src"))
    for name in sorted(set(_shims()) & set(LAB_CLI_MODULES)):
        outputs = [subprocess.run([sys.executable, "-m", f"{package}.{name}", "--help"], cwd=REPO,
                                  env=environment, text=True, capture_output=True, check=True).stdout
                   for package in ("chronicler", "chronicler_lab")]
        assert outputs[0] == outputs[1], name
