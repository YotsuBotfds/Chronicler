"""Completion options must agree with CLI feature ownership before mutation."""
from __future__ import annotations

import pytest

from chronicler import livelihoods as LV, main
from chronicler.adaptive_livelihoods_state import AdaptiveLivelihoodsState
from chronicler.food_allocation_state import FoodAllocationState
from chronicler.health_care_state import HealthCareState
from chronicler.household_retail_state import HouseholdRetailState
from chronicler.livelihoods_state import LivelihoodsState
from chronicler.residence_ledger_state import ResidenceLedgerState
from chronicler.war_consequences_state import WarConsequencesState
from chronicler.war_requisition_state import WarRequisitionState
from chronicler.wealth_accounting_state import WealthAccountingState
from chronicler.world_gen import generate_world
from test_feature_catalog import sentinel_runtimes  # noqa: F401


OPTIONS = (
    ("war_requisition_mode", "cost_only"),
    ("war_consequences_mode", "record_only"),
    ("adaptive_livelihoods_mode", "record_only"),
    ("adaptive_livelihoods_rules", "1"),
    ("wealth_accounting_mode", "strict"),
)


def _args(key, value, *flags):
    return main._build_parser().parse_args(["--agents", "hybrid", "--simulate-only",
                                           "--" + key.replace("_", "-"), value, *flags])


def _saved_world():
    world = generate_world(seed=7)
    world.agent_mode = "hybrid"
    world.campaigns_enabled = True
    world.health_care = HealthCareState()
    world.livelihoods = LivelihoodsState(
        food_allocation=FoodAllocationState(), household_retail=HouseholdRetailState(rules_version=2),
        residence_ledger=ResidenceLedgerState(), war_requisition=WarRequisitionState(),
        war_consequences=WarConsequencesState(), adaptive_livelihoods=AdaptiveLivelihoodsState(),
        wealth_accounting=WealthAccountingState())
    return world


@pytest.mark.parametrize("key,value", OPTIONS)
def test_real_cli_startup_refuses_orphan_completion_option(tmp_path, sentinel_runtimes, key, value):
    world = generate_world(seed=7)
    with pytest.raises(ValueError, match="requires --"):
        main._configure_run(_args(key, value), world, True, tmp_path / "chronicle.md")
    assert world.livelihoods is None


@pytest.mark.parametrize("key,value", OPTIONS)
def test_explicit_disable_with_option_refuses_without_changing_saved_state(key, value):
    world = _saved_world()
    name, _field = LV._CHOICE_FIELDS[key]
    before = world.model_dump_json()
    with pytest.raises(ValueError, match="requires --"):
        LV.configure_livelihoods(world, _args(key, value, "--no-" + name.replace("_", "-")), agent_mode="hybrid")
    assert world.model_dump_json() == before


@pytest.mark.parametrize("key,_value", OPTIONS)
def test_matching_saved_option_is_accepted_without_explicit_enable_or_mutation(key, _value):
    world = _saved_world()
    name, field = LV._CHOICE_FIELDS[key]
    value = getattr(getattr(world.livelihoods, name), field)
    before = world.model_dump_json()
    LV.configure_livelihoods(world, _args(key, value), agent_mode="hybrid")
    assert world.model_dump_json() == before


@pytest.mark.parametrize("explicit_enable", [False, True])
@pytest.mark.parametrize("key,value", OPTIONS)
def test_conflicting_saved_option_refuses_before_any_setter(key, value, explicit_enable):
    world = _saved_world()
    name, field = LV._CHOICE_FIELDS[key]
    assert value != getattr(getattr(world.livelihoods, name), field)
    flags = ["--" + name.replace("_", "-")] if explicit_enable else []
    before = world.model_dump_json()
    with pytest.raises(ValueError, match="conflicts with the saved world"):
        LV.configure_livelihoods(world, _args(key, value, *flags), agent_mode="hybrid")
    assert world.model_dump_json() == before


@pytest.mark.parametrize("key,value", OPTIONS)
def test_new_requested_switch_receives_its_explicit_option(key, value):
    world = _saved_world()
    name, field = LV._CHOICE_FIELDS[key]
    setattr(world.livelihoods, name, None)
    LV.configure_livelihoods(world, _args(key, value, "--" + name.replace("_", "-")), agent_mode="hybrid")
    state = getattr(world.livelihoods, name)
    assert state.enabled and getattr(state, field) == value
