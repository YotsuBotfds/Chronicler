"""Bounded harvest/rest ledger and Python persistence fixture."""
import importlib.util
from pathlib import Path

import pytest


@pytest.fixture(scope="module")
def validation_module():
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("fishery_recovery_validation", root / "scripts/validate_fishery_recovery.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def recovery_run(validation_module):
    source = Path(__file__).resolve().parents[1] / "src"
    return validation_module.run_fixture(source, enabled=True)


def test_harvest_rest_resource_and_actual_goods_accounting(recovery_run):
    assert all(recovery_run["checks"].values())
    harvest, rest = recovery_run["trace"][:20], recovery_run["trace"][20:]
    assert harvest[-1]["stock_after"] < harvest[0]["stock_before"]
    assert all(row["stock_after"] > row["stock_before"] for row in rest)
    assert all(row["catch_worker_units"] == 0 and row["actual_food_production"] == 0 for row in rest)
    assert any(row["catch_worker_units"] > 0 for row in harvest)
    assert any(row["actual_food_production"] > 0 for row in harvest)
    assert all(row["actual_food_production"] <= row["previous_catch_credit"] + 1e-9
               for row in recovery_run["trace"])
    assert recovery_run["summary"]["max_combined_balance_residual"] < 1e-9


def test_famine_and_stockpile_sufficiency_remain_distinct(recovery_run):
    summary = recovery_run["summary"]
    assert summary["famine_event_turns"]
    assert summary["yield_famine_turns"]
    assert all(turn in summary["yield_famine_turns"] for turn in summary["famine_event_turns"])
    assert len(summary["famine_event_turns"]) < len(summary["yield_famine_turns"])
    assert set(range(20, 40)) <= set(summary["stockpile_shortage_without_yield_famine_turns"])


def test_python_saved_stock_ratio_budget_and_goods_resume_across_rest_boundary(validation_module, recovery_run):
    source = Path(__file__).resolve().parents[1] / "src"
    resumed = validation_module.run_fixture(source, enabled=True, resume_at=20)
    assert resumed["persistence"] == {"resumed_at": 20, "roundtrip_verified": True}
    assert resumed["trace"] == recovery_run["trace"]
    assert resumed["summary"] == recovery_run["summary"]


def test_saved_disabled_memory_is_ignored_then_removed_slot_resets(tmp_path):
    from chronicler.experimental.fisheries import apply_fishery_feedback, catch_budget
    from chronicler.ecology import goods_per_worker
    from chronicler.models import Region, ResourceType, WorldState

    world = WorldState(name="Reset fixture", seed=42, regions=[Region(
        name="Coast", terrain="coast", carrying_capacity=1000, population=100,
        resources="maritime", resource_types=[3, 255, 255], resource_base_yields=[1, 0, 0],
        fishery_stocks=[.2, 1, 1], fishery_yield_ratios=[.3, 1, 1],
        fishery_catch_budgets=[40, None, None],
    )])
    path = tmp_path / "disabled.json"
    world.save(path)
    loaded = WorldState.load(path)
    assert loaded.model_dump() == world.model_dump()
    before = loaded.model_dump()
    yields = {"Coast": [1, 0, 0]}
    apply_fishery_feedback(loaded, yields)
    assert loaded.model_dump() == before
    assert catch_budget(loaded, loaded.regions[0]) is None
    loaded.fishery_experiment.enabled = True
    # The saved catch credit, in goods units.
    assert catch_budget(loaded, loaded.regions[0]) == pytest.approx(goods_per_worker(ResourceType.FISH, 40))
    loaded.regions[0].resource_types[0] = 0
    apply_fishery_feedback(loaded, yields)
    assert loaded.regions[0].fishery_stocks == [1, 1, 1]
    assert loaded.regions[0].fishery_yield_ratios == [1, 1, 1]
    assert loaded.regions[0].fishery_catch_budgets == [None, None, None]
