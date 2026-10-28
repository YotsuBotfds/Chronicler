"""Shared entrypoint wiring for the bounded October expansion experiments.

State and runtime decisions belong to each system. This module owns only
CLI/config forwarding and optional observation fields, keeping single, live,
batch and qualification runs on the same switches. Omitted flags preserve
saved state; disabled worlds do not import experimental runtimes.
"""
from __future__ import annotations

import argparse
from importlib import import_module
from typing import Any

EXPANSION_FEATURES = ("health_care", "harvest_forecasts", "ritual_gatherings",
                      "scientific_claims", "transaction_receipts")
EXPANSION_PREREQUISITES = ("grain_reserves", "contact_ledger", "scholarship", "techniques")
EXPANSION_SWITCHES = EXPANSION_FEATURES + ("scientific_research_agendas",)

_HELP = {
    "scientific_research_agendas": (
        "Finite recurring paid academy research with retained topics and evidence; "
        "requires --scientific-claims, --scholarship and --techniques (default off; "
        "--no-scientific-research-agendas pauses new funding while retaining knowledge)"
    ),
    "transaction_receipts": (
        "Record bounded cargo movement receipts with observed voyage identities "
        "and explicit regional-stock or virtual basis; requires an agent-backed "
        "economy (default off; saved state dormant without an agent pool)"
    ),
    "scientific_claims": (
        "Academy-funded contextual trials, dated evidence and paid adoption effort; "
        "requires --scholarship and --techniques (default off; saved state "
        "dormant without prerequisites)"
    ),
    "health_care": (
        "Temporary occupational injuries and household care: lost work and "
        "care time constrain farming and work income; requires --agents hybrid "
        "(default off; saved state dormant in other modes)"
    ),
    "harvest_forecasts": (
        "Fallible delayed harvest reports can raise paid public-granary "
        "preparation targets; requires --grain-reserves, --contact-ledger and "
        "an agent-backed economy (default off; saved state dormant without prerequisites)"
    ),
    "ritual_gatherings": (
        "Recurring harvest gatherings spend real food and funds, with bounded "
        "attendance, contact and relationships; requires --agents hybrid "
        "(default off; saved state dormant in other modes)"
    ),
}


def add_expansion_arguments(parser: argparse.ArgumentParser, *, forwarding: bool = False) -> None:
    for name in EXPANSION_SWITCHES:
        flag = "--" + name.replace("_", "-")
        parser.add_argument(
            flag, action=argparse.BooleanOptionalAction, default=None,
            help=(f"Forward {flag}/{flag.replace('--', '--no-', 1)} to every run. "
                  if forwarding else "") + _HELP[name],
        )


def expansion_arguments(args: Any) -> list[str]:
    """Forward explicit requests, including explicit disables, to child runs."""
    flags = []
    for name in EXPANSION_SWITCHES:
        value = getattr(args, name, None)
        if value is not None:
            if not isinstance(value, bool):
                raise ValueError(f"{name} must be a boolean or None")
            flags.append("--" + ("" if value else "no-") + name.replace("_", "-"))
    return flags


def configure_expansion_features(world: Any, args: Any, *, agent_mode: str) -> None:
    """Apply explicit switches after existing prerequisites are configured.

    Invalid explicit opt-ins fail. A loaded enabled system with an omitted
    switch keeps its state and can remain dormant. Normalize the effective
    mode only for worlds using these new systems: older feature-off world
    serialization and runtime paths stay unchanged.
    """
    values = {name: getattr(args, name, None) for name in EXPANSION_FEATURES}
    research = getattr(args, "scientific_research_agendas", None)
    if research is not None and type(research) is not bool:
        raise ValueError("scientific_research_agendas must be a boolean or None")
    if research is True and (values["scientific_claims"] is False or (
            values["scientific_claims"] is not True and getattr(world, "scientific_claims", None) is None)):
        raise ValueError("--scientific-research-agendas requires --scientific-claims")
    for name, value in values.items():
        if value is not None and not isinstance(value, bool):
            raise ValueError(f"{name} must be a boolean or None")
        if value is True and name in ("health_care", "ritual_gatherings") and agent_mode != "hybrid":
            raise ValueError(f"--{name.replace('_', '-')} requires --agents hybrid")
    if values["transaction_receipts"] is True and agent_mode not in ("hybrid", "shadow", "demographics-only"):
        raise ValueError("--transaction-receipts requires an agent-backed economy")
    if values["scientific_claims"] is True:
        from chronicler.scholarship import scholarship_enabled
        from chronicler.techniques import techniques_enabled
        if not scholarship_enabled(world) or not techniques_enabled(world):
            raise ValueError("--scientific-claims requires --scholarship and --techniques")
    if values["harvest_forecasts"] is True:
        from chronicler.contact_ledger import ledger_enabled
        from chronicler.grain_reserves import grain_reserves_enabled
        if agent_mode not in ("hybrid", "shadow", "demographics-only"):
            raise ValueError("--harvest-forecasts requires an agent-backed goods economy")
        if not grain_reserves_enabled(world):
            raise ValueError("--harvest-forecasts requires --grain-reserves")
        if not ledger_enabled(world):
            raise ValueError("--harvest-forecasts requires --contact-ledger")
    if any(getattr(world, name, None) is not None or values[name] is True
           for name in EXPANSION_FEATURES):
        world.agent_mode = agent_mode
    for name, value in values.items():
        if value is not None:
            if value is False and getattr(world, name, None) is None:
                continue
            module = import_module("chronicler." + name)
            getattr(module, f"set_{name}_enabled")(world, value)
    if research is not None:
        from chronicler.scientific_research import set_research_agendas_enabled
        set_research_agendas_enabled(world, research)


def expansion_feature_flags(world: Any) -> dict[str, bool]:
    flags = {name: getattr(world, name, None) is not None for name in EXPANSION_FEATURES}
    state = getattr(world, "scientific_claims", None)
    plan = state.research_agendas if state is not None else None
    if plan is not None:
        flags["scientific_research_agendas"] = plan.enabled
    return flags


def expansion_snapshot_fields(world: Any) -> dict:
    """Include each active system's copied historical record, never final state."""
    fields = {}
    for name in EXPANSION_FEATURES:
        if getattr(world, name, None) is None:
            continue
        module = import_module("chronicler." + name)
        if getattr(module, f"{name}_active")(world):
            fields[name] = module.snapshot_summary(world)
    return fields
