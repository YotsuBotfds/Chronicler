"""New-world switch defaults: one registry for the CLI, live, catalog and batch paths.

``SWITCHES`` lists the persisted world switches whose value a *new* world
takes from its module's default constant (``DEFAULT_ENABLED_FOR_NEW_WORLDS``,
or ``CAMPAIGNS_DEFAULT_FOR_NEW_WORLDS`` for campaigns), in the order
``main._configure_run`` applies them. The 17 default-on rows are the
production core (DEC-2, docs/superpowers/progress/streamline-and-deepen-decisions.md);
the default-off rows are experimental and stay off. Each row's ``status``
records its qualification evidence and open calibration as the project
docs state them; it is documentation only and never read by the run.

``main._configure_run`` applies the registry in slices between its own
validation blocks (the explicit-on ``ValueError`` checks stay there), and
``live._live_world`` applies all of it to a new lobby world. Batch runs go
through ``main._configure_run``. ``feature_catalog`` reads ``default``.

Defaults are read lazily from their modules, so a module constant stays the
one place a default is decided (and tests may patch it).
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import Any, Iterable

DEFAULT_ATTR = "DEFAULT_ENABLED_FOR_NEW_WORLDS"


@dataclass(frozen=True)
class SwitchDefault:
    """One new-world switch.

    ``name`` is the parser destination (and catalog key). The value is
    applied by ``module.setter(world, value)``; a row without a setter
    assigns ``world.<world_attr>`` directly. ``enabled`` names the module's
    reader (``None``: ``bool(world.<world_attr>)``). ``requires`` names
    switches that must be on for this one to take effect when its value
    comes from the default (and always on live worlds); the CLI refuses an
    explicit on without them in ``main``. ``new_world_kwarg`` passes
    ``new_world=fresh_world`` to the setter (fisheries calibration).
    ``live_exempt`` rows are not applied to live worlds (governance, until
    COR-2).
    """

    name: str
    module: str
    setter: str | None
    enabled: str | None
    status: str
    world_attr: str | None = None
    default_attr: str = DEFAULT_ATTR
    requires: tuple[str, ...] = ()
    new_world_kwarg: bool = False
    live_exempt: bool = False


SWITCHES: tuple[SwitchDefault, ...] = (
    SwitchDefault(
        "campaigns", "chronicler.war.params", None, None, world_attr="campaigns_enabled",
        default_attr="CAMPAIGNS_DEFAULT_FOR_NEW_WORLDS",
        status="on since M60 (docs/war/campaigns-battles-occupation.md); battle and logistics "
               "parameters are illustrative, not fitted against the 200-seed gate"),
    SwitchDefault(
        "mutual_aid", "chronicler.mutual_aid", None, None, world_attr="mutual_aid_enabled",
        status="promoted on living-world validation "
               "(docs/integration/fisheries-mutual-aid-promotion.md); almost never fires; "
               "dormant with --agents off"),
    SwitchDefault(
        "fisheries", "chronicler.experimental.fisheries", "set_fisheries_enabled", "fishery_enabled",
        new_world_kwarg=True,
        status="promoted with a living-world calibration "
               "(docs/integration/fisheries-mutual-aid-promotion.md); NEW_WORLD_REFERENCE_WORKERS "
               "is [CALIBRATE]; the regression civ_survival band needs recalibration"),
    SwitchDefault(
        "governance", "chronicler.governance_runtime", "set_governance_enabled", "governance_enabled",
        live_exempt=True,
        status="subset gate, no regression (docs/governance/runtime-integration.md); calibration "
               "is a first pass; new live worlds exempt until COR-2"),
    SwitchDefault(
        "contact_ledger", "chronicler.contact_ledger", "set_contact_ledger_enabled", "ledger_enabled",
        status="on (docs/integration/contact-ledger.md); parameters illustrative, not fitted "
               "against the 200-seed gate"),
    SwitchDefault(
        "epidemiology", "chronicler.epidemiology", "set_epidemiology_enabled", "epidemiology_enabled",
        requires=("contact_ledger",),
        status="all-on full gate (docs/integration/wave3-defaults.md, epidemiology.md)"),
    SwitchDefault(
        "finance", "chronicler.finance", "set_finance_enabled", "finance_enabled",
        status="all-on full gate (docs/integration/wave3-defaults.md, money-credit.md)"),
    SwitchDefault(
        "diplomacy", "chronicler.diplomacy", "set_diplomacy_enabled", "diplomacy_enabled",
        status="all-on full gate (docs/integration/wave3-defaults.md, diplomacy.md)"),
    SwitchDefault(
        "techniques", "chronicler.techniques", "set_techniques_enabled", "techniques_enabled",
        status="full gate (docs/integration/techniques-default.md)"),
    SwitchDefault(
        "maritime", "chronicler.maritime", "set_maritime_enabled", "maritime_enabled",
        status="Wave 8 full gate (docs/integration/defaults-wave8.md, maritime.md)"),
    SwitchDefault(
        "gp_agendas", "chronicler.gp_agendas", "set_gp_agendas_enabled", "gp_agendas_enabled",
        status="Wave 8 full gate (docs/integration/defaults-wave8.md, great-person-agendas.md)"),
    SwitchDefault(
        "nomads", "chronicler.nomads", "set_nomads_enabled", "nomads_enabled",
        status="Wave 8 full gate (docs/integration/defaults-wave8.md, nomads.md)"),
    SwitchDefault(
        "cities", "chronicler.cities", "set_cities_enabled", "cities_enabled",
        status="city-markets full gate (docs/integration/cities.md, city-markets.md)"),
    SwitchDefault(
        "agent_movements", "chronicler.agent_movements", "set_agent_movements_enabled",
        "agent_movements_enabled",
        status="full gate, no regression (docs/integration/agent-movements.md)"),
    SwitchDefault(
        "guilds", "chronicler.guilds", "set_guilds_enabled", "guilds_enabled",
        status="full gate, no regression (docs/integration/guilds.md)"),
    SwitchDefault(
        "scholarship", "chronicler.scholarship", "set_scholarship_enabled", "scholarship_enabled",
        status="experimental, default off (docs/integration/scholarship.md)"),
    SwitchDefault(
        "grain_reserves", "chronicler.grain_reserves", "set_grain_reserves_enabled",
        "grain_reserves_enabled",
        status="experimental, default off (docs/integration/grain-reserves.md)"),
    SwitchDefault(
        "community_anchoring", "chronicler.community_anchoring", "set_community_anchoring_enabled",
        "community_anchoring_enabled",
        status="experimental, default off (docs/integration/community-anchoring.md)"),
    SwitchDefault(
        "domestic_credit", "chronicler.domestic_credit", "set_domestic_credit_enabled",
        "domestic_credit_enabled", requires=("finance",),
        status="experimental, default off (docs/integration/domestic-credit.md)"),
    SwitchDefault(
        "historiography", "chronicler.historiography", "set_historiography_enabled", "historiography_on",
        status="observational; outcome-neutral by identity (docs/integration/historiography.md)"),
    SwitchDefault(
        "languages", "chronicler.languages", "set_languages_enabled", "languages_on",
        status="observational; outcome-neutral by identity (docs/integration/languages.md)"),
)

_BY_NAME = {entry.name: entry for entry in SWITCHES}


def entry(name: str) -> SwitchDefault:
    return _BY_NAME[name]


def default(name: str) -> bool:
    """The new-world default of switch ``name``, read from its module."""
    row = _BY_NAME[name]
    return bool(getattr(importlib.import_module(row.module), row.default_attr))


def is_enabled(world: Any, name: str) -> bool:
    row = _BY_NAME[name]
    if row.enabled is None:
        return bool(getattr(world, row.world_attr))
    return bool(getattr(importlib.import_module(row.module), row.enabled)(world))


def switch_state(world: Any) -> dict[str, bool]:
    """Every registry switch's state on ``world`` (name -> on)."""
    return {row.name: is_enabled(world, row.name) for row in SWITCHES}


def resolve(row: SwitchDefault, args: Any, fresh_world: bool, *, live: bool = False) -> Any:
    """The value of ``row`` before its prerequisites: the explicit argument
    (coerced to ``bool`` on live worlds), else the default on a new world;
    ``None`` leaves the world's own setting."""
    value = getattr(args, row.name, None)
    if value is None:
        return default(row.name) if fresh_world else None
    return bool(value) if live else value


def _apply(world: Any, row: SwitchDefault, value: Any, fresh_world: bool) -> None:
    if row.setter is None:
        setattr(world, row.world_attr, value)
        return
    setter = getattr(importlib.import_module(row.module), row.setter)
    if row.new_world_kwarg:
        setter(world, value, new_world=fresh_world)
    else:
        setter(world, value)


def apply_switches(world: Any, args: Any, *, fresh_world: bool,
                   names: Iterable[str] | None = None, live: bool = False) -> None:
    """Apply the registry's switches (all, or ``names`` in registry order) to
    ``world``: an explicit argument wins, a new world takes the default and a
    supplied or resumed world keeps its own setting. A value taken from the
    default is on only while each ``requires`` switch is on; ``live`` applies
    that to explicit values too and skips ``live_exempt`` rows."""
    wanted = None if names is None else set(names)
    if wanted is not None and not wanted <= _BY_NAME.keys():
        raise KeyError(f"unknown switches: {sorted(wanted - _BY_NAME.keys())}")
    for row in SWITCHES:
        if wanted is not None and row.name not in wanted:
            continue
        if live and row.live_exempt:
            continue
        explicit = getattr(args, row.name, None) is not None
        value = resolve(row, args, fresh_world, live=live)
        if value is None:
            continue
        if row.requires and (live or not explicit):
            value = value and all(is_enabled(world, req) for req in row.requires)
        _apply(world, row, value, fresh_world)


__all__ = [
    "DEFAULT_ATTR", "SWITCHES", "SwitchDefault", "apply_switches", "default", "entry",
    "is_enabled", "resolve", "switch_state",
]
