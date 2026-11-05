"""Wiring and phase hooks for the livelihoods/commons sprint (default off).

Independent switches share one persisted container,
``WorldState.livelihoods`` (:mod:`chronicler.livelihoods_state`):

* ``--workshops`` (L1): staffed public workshops in selected cities;
* ``--food-allocation`` (L2): explicit allocation of regional food to people;
* ``--timber-stock`` (L3): a renewable harvestable timber stock;
* ``--grain-convoys`` (L4): multi-leg public grain convoys under risk;
* ``--commons-rules`` (L8): a paid, enforced harvest rule on the timber stock;
* ``--learning-cohorts`` (L5): named learners attending delivered academy teaching.

This module owns only CLI forwarding, validation of prerequisites and the
fan-out of phase hooks to each package's module ``chronicler.<switch>``.
State, decisions and accounting belong to those modules. An omitted switch
keeps the saved state; a world that never enabled one has no container, no
snapshot key, no checkpoint flag and no manifest entry, so feature-off runs
keep their exact serialized output.

Package module protocol (each function optional unless noted):

``set_<name>_enabled(world, value, *, args, agent_mode)`` (required),
``<name>_active(world)`` (required), ``snapshot_summary(world)`` (required),
``prepare_phase2(world, region_input, agent_bridge, snapshot, acc)`` returning
the region batch, ``finish_phase2(world, economy_result, agent_bridge, acc)``,
``rollback_phase2(world)``, ``before_agent_tick(world, agent_bridge,
economy_result)``, ``after_agent_tick(world, agent_bridge)``,
``phase10_before_reserves(world, acc, economy_result, agent_bridge)`` and
``phase10(world, acc, economy_result, agent_bridge)``; event-returning hooks
return a list.
"""
from __future__ import annotations

import argparse
from importlib import import_module
from typing import Any

from chronicler.livelihoods_state import LIVELIHOODS_SWITCHES, LivelihoodsState

#: Non-boolean options, with their choices (first: the default when enabled).
LIVELIHOODS_CHOICES: dict[str, tuple[str, ...]] = {
    "workshop_mode": ("operate", "observe", "cost_only"),
    "food_allocation_regime": ("floor_means", "equal", "targeted_relief"),
    "convoy_route_policy": ("adaptive", "cheapest", "safest"),
    "commons_rule_mode": ("enforced", "cost_only"),
    "learning_cohort_mode": ("learn", "no_learning"),
}
#: All parser destinations owned here (``batch_manifest.SIMULATION_ARG_KEYS``).
LIVELIHOODS_ARG_KEYS: tuple[str, ...] = (
    "workshops", "workshop_mode", "food_allocation", "food_allocation_regime",
    "timber_stock", "grain_convoys", "convoy_route_policy", "commons_rules", "commons_rule_mode",
    "learning_cohorts", "learning_cohort_mode",
)
_AGENT_ECONOMY = ("hybrid", "shadow", "demographics-only")

_HELP = {
    "workshops": (
        "Staffed public workshops: up to four selected cities employ named adult "
        "urban farmers' already-diverted time; with --workshop-mode operate the "
        "controller's treasury pays construction and upkeep as a public cost (no "
        "wages) and the crew's work replaces the region's craft ceiling; requires "
        "--agents hybrid and cities (default off)"
    ),
    "workshop_mode": "operate (default): treasury-funded crews replace the craft ceiling; observe: crews and native craft inputs only; cost_only: the ablation that builds and pays but keeps the legacy ceiling",
    "food_allocation": (
        "Allocate each region's available food to its people and derived households "
        "under an explicit rule; individual hunger, needs and mortality read the "
        "person's own allocation; requires --agents hybrid (default off)"
    ),
    "food_allocation_regime": (
        "floor_means (default): an equal subsistence floor, the scarce remainder by "
        "household means; equal: equal per person (reproduces the regional signal); "
        "targeted_relief: equal market food, public granary release to the worst off"
    ),
    "timber_stock": (
        "Renewable harvestable timber stock: realized timber extraction debits it, "
        "regrowth takes turns under forest cover and water, harvest cannot exceed it; "
        "requires an agent-backed economy (default off)"
    ),
    "grain_convoys": (
        "Multi-leg public grain convoys: paid foreign purchases travel leg by leg, "
        "can be delayed, rerouted, turned back, captured or lost; requires "
        "--public-grain-shipments (default off)"
    ),
    "convoy_route_policy": "adaptive (default), cheapest or safest route choice at dispatch",
    "commons_rules": (
        "Commons rules on the timber stock: a region's controller may adopt a harvest "
        "quota with a rest period on a depleted, harvested stand, paying wardens from its "
        "treasury; partial payment leaves part of the stand open access; requires "
        "--timber-stock (default off)"
    ),
    "commons_rule_mode": "enforced (default): the rule lowers the harvest cap; cost_only: the ablation that adopts and pays identically but applies no cap",
    "learning_cohorts": (
        "Named learners at academies: finite cohorts of present adults attend actual "
        "delivered academy teaching, give up part of their ordinary income, and on "
        "completion gain skill in their trade; requires --agents hybrid and "
        "--academy-services (default off)"
    ),
    "learning_cohort_mode": "learn (default): completion raises the learner's trade skill; no_learning: the cost-retaining control (same attendance, cost and supplies, no skill gain)",
}


def add_livelihoods_arguments(parser: argparse.ArgumentParser, *, forwarding: bool = False) -> None:
    for name in LIVELIHOODS_ARG_KEYS:
        flag = "--" + name.replace("_", "-")
        prefix = f"Forward {flag} to every run. " if forwarding else ""
        if name in LIVELIHOODS_CHOICES:
            parser.add_argument(flag, choices=LIVELIHOODS_CHOICES[name], default=None,
                                help=prefix + _HELP[name])
        else:
            parser.add_argument(flag, action=argparse.BooleanOptionalAction, default=None,
                                help=prefix + _HELP[name])


def livelihoods_arguments(args: Any) -> list[str]:
    """Forward explicit requests, including explicit disables, to child runs."""
    flags = []
    for name in LIVELIHOODS_ARG_KEYS:
        value = getattr(args, name, None)
        if value is None:
            continue
        flag = name.replace("_", "-")
        if name in LIVELIHOODS_CHOICES:
            if value not in LIVELIHOODS_CHOICES[name]:
                raise ValueError(f"{name} must be one of {LIVELIHOODS_CHOICES[name]}")
            flags.append(f"--{flag}={value}")
        elif isinstance(value, bool):
            flags.append("--" + ("" if value else "no-") + flag)
        else:
            raise ValueError(f"{name} must be a boolean or None")
    return flags


def livelihoods_state(world: Any) -> LivelihoodsState | None:
    state = getattr(world, "livelihoods", None)
    if state is not None and not isinstance(state, LivelihoodsState):
        raise TypeError("world.livelihoods must be LivelihoodsState or None")
    return state


def _module(name: str):
    return import_module("chronicler." + name)


def _check_prerequisites(world: Any, values: dict, agent_mode: str) -> None:
    if values["workshops"] is True:
        if agent_mode != "hybrid":
            raise ValueError("--workshops requires --agents hybrid")
        if getattr(world, "cities", None) is None:
            raise ValueError("--workshops requires cities")
    if values["food_allocation"] is True and agent_mode != "hybrid":
        raise ValueError("--food-allocation requires --agents hybrid")
    if values["timber_stock"] is True and agent_mode not in _AGENT_ECONOMY:
        raise ValueError("--timber-stock requires an agent-backed economy")
    if values["grain_convoys"] is True:
        reserves = getattr(world, "grain_reserves", None)
        if reserves is None or getattr(reserves, "shipments", None) is None:
            raise ValueError("--grain-convoys requires --public-grain-shipments")
    if values["commons_rules"] is True:
        saved = getattr(livelihoods_state(world), "timber_stock", None)
        if values["timber_stock"] is False or (values["timber_stock"] is None
                                               and not getattr(saved, "enabled", False)):
            raise ValueError("--commons-rules requires --timber-stock")
    if values["learning_cohorts"] is True:
        if agent_mode != "hybrid":
            raise ValueError("--learning-cohorts requires --agents hybrid")
        services = getattr(getattr(world, "scholarship", None), "learning_services", None)
        if services is None or not getattr(services, "enabled", True):
            raise ValueError("--learning-cohorts requires --academy-services")


def configure_livelihoods(world: Any, args: Any, *, agent_mode: str) -> None:
    """Apply explicit switches after prerequisites (expansion features) are set."""
    values = {name: getattr(args, name, None) for name in LIVELIHOODS_SWITCHES}
    for name, value in values.items():
        if value is not None and not isinstance(value, bool):
            raise ValueError(f"{name} must be a boolean or None")
    for name, choices in LIVELIHOODS_CHOICES.items():
        value = getattr(args, name, None)
        if value is not None and value not in choices:
            raise ValueError(f"{name} must be one of {choices}")
    _check_prerequisites(world, values, agent_mode)
    state = livelihoods_state(world)
    for name, value in values.items():
        if value is None:
            continue
        if value is False and (state is None or getattr(state, name) is None):
            continue
        if state is None:
            state = world.livelihoods = LivelihoodsState()
        getattr(_module(name), f"set_{name}_enabled")(world, value, args=args, agent_mode=agent_mode)


def _present(world: Any):
    state = livelihoods_state(world)
    if state is None:
        return
    for name in LIVELIHOODS_SWITCHES:
        if getattr(state, name) is not None:
            yield name, _module(name)


def livelihoods_feature_flags(world: Any) -> dict[str, bool]:
    """Checkpoint header flags, only for switches this world ever enabled."""
    return {name: bool(getattr(module, f"{name}_active")(world)) for name, module in _present(world)}


def livelihoods_snapshot_fields(world: Any) -> dict:
    """Copied completed-turn observations of active packages; never final state."""
    parts = {name: module.snapshot_summary(world) for name, module in _present(world)
             if getattr(module, f"{name}_active")(world)}
    if not parts:
        return {}
    return {"livelihoods": {"schema_version": 1, **parts}}


def _hooks(world: Any, hook: str):
    for name, module in _present(world):
        fn = getattr(module, hook, None)
        if fn is not None and getattr(module, f"{name}_active")(world):
            yield fn


def prepare_phase2(world, region_input, agent_bridge, snapshot, *, acc=None):
    """Before the native economy tick: may replace columns; charges nothing."""
    for fn in _hooks(world, "prepare_phase2"):
        region_input = fn(world, region_input, agent_bridge, snapshot, acc)
    return region_input


def finish_phase2(world, economy_result, agent_bridge, *, acc=None) -> list:
    """After a successful native economy tick and storage settlement."""
    events: list = []
    for fn in _hooks(world, "finish_phase2"):
        events.extend(fn(world, economy_result, agent_bridge, acc) or [])
    return events


def rollback_phase2(world) -> None:
    """Release anything a failed Phase 2 left pending; never a native rollback."""
    for name, module in _present(world):
        fn = getattr(module, "rollback_phase2", None)
        if fn is not None:
            fn(world)


def wrap_agent_tick(world, agent_bridge, tick_agents, economy_result):
    """Wrap the native agent tick with the active packages' before/after hooks."""
    before = list(_hooks(world, "before_agent_tick"))
    after = list(_hooks(world, "after_agent_tick"))
    if (not before and not after) or tick_agents is None:
        return tick_agents

    def _tick(*args, **kwargs):
        for fn in before:
            fn(world, agent_bridge, economy_result)
        events = tick_agents(*args, **kwargs)
        for fn in after:
            events = list(events or []) + list(fn(world, agent_bridge) or [])
        return events

    return _tick


def phase10_before_reserves(world, *, acc=None, economy_result=None, agent_bridge=None) -> list:
    events: list = []
    for fn in _hooks(world, "phase10_before_reserves"):
        events.extend(fn(world, acc, economy_result, agent_bridge) or [])
    return events


def phase10(world, *, acc=None, economy_result=None, agent_bridge=None) -> list:
    events: list = []
    for fn in _hooks(world, "phase10"):
        events.extend(fn(world, acc, economy_result, agent_bridge) or [])
    return events
