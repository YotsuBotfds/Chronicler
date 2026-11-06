"""The feature options a live viewer may request, with their dependencies.

One catalog, served to the viewer in the lobby ``init`` message
(``feature_catalog``), drives the Batch Lab and live new-world setup and the
server's own validation of their ``features`` objects, so the two cannot
drift. It lists:

* every livelihoods switch and its mode, generated from the registry
  (``livelihoods_state.LIVELIHOODS_SWITCHES``, ``livelihoods.LIVELIHOODS_ARG_KEYS``
  and ``LIVELIHOODS_CHOICES``; the parser's help is ``livelihoods._HELP``); a
  choice key belongs to the switch declared before it;
* the expansion prerequisites those switches depend on (``PREREQUISITES``).

Each entry's key is the CLI parser destination; flag, help text and choices
are read from the CLI parser itself. Nothing here is on by default: an absent
key is not forwarded, and the run then uses its CLI default (the first choice
of a mode once its switch is on).

``REQUIREMENTS`` declares what each switch needs. The run's own checks
(``livelihoods._check_prerequisites`` and ``main._configure_run``) stay
authoritative; ``tests/test_feature_catalog.py`` checks that the two agree on
the real configuration path, so a new switch without declared requirements
fails there.

Requirement conditions (JSON objects, each with a human ``reason``):

* ``{"agents": [modes]}``: the run's ``--agents`` mode is one of these;
* ``{"feature": key}``: that boolean feature is on;
* ``{"choice": key, "values": [...]}``: that choice (its first choice when
  unset) is one of these values;
* ``{"setting": name}``: a server setting this surface cannot change is true
  (``SETTINGS``; each surface reports its values);
* ``{"any": [conditions]}``: at least one condition holds.
"""
from __future__ import annotations

import copy
from functools import lru_cache
from typing import Any, Mapping

from chronicler.livelihoods import LIVELIHOODS_ARG_KEYS, LIVELIHOODS_CHOICES
from chronicler.livelihoods_state import LIVELIHOODS_SWITCHES

CATALOG_SCHEMA_VERSION = 1
LIVELIHOODS_GROUP = "Livelihoods"
PREREQUISITES_GROUP = "Prerequisites"
#: ``--agents`` modes, in the CLI's order of increasing agent detail.
AGENT_MODES: tuple[str, ...] = ("off", "demographics-only", "shadow", "hybrid")
_AGENT_ECONOMY: tuple[str, ...] = ("hybrid", "shadow", "demographics-only")

#: Expansion prerequisites of the livelihoods switches, in display order,
#: each with its choice options (parser destinations).
PREREQUISITES: dict[str, tuple[str, ...]] = {
    "grain_reserves": (),
    "public_grain_shipments": (),
    "grain_storage": ("grain_storage_policy",),
    "scholarship": (),
    "academy_services": (),
}

#: Server settings a request cannot change: what each means when true.
SETTINGS: dict[str, str] = {
    "cities": "cities (on by default for new worlds; off with --no-cities)",
    "techniques": "techniques (on by default for new worlds; off with --no-techniques)",
    "no_household_mobility_liquid_requirement": (
        "no household-mobility liquid requirement (--household-mobility-liquid-requirement unset or 0)"),
    "procedural_world": (
        "a procedural world (template worlds have no elevation); a live start cannot guarantee one, "
        "a Batch Lab world is procedural above 12 regions"),
}


def _agents(*modes: str) -> dict:
    return {"agents": list(modes)}


def _feature(key: str) -> dict:
    return {"feature": key}


def _choice(key: str, *values: str) -> dict:
    return {"choice": key, "values": list(values)}


def _setting(name: str) -> dict:
    return {"setting": name}


def _any(*conditions: dict) -> dict:
    return {"any": list(conditions)}


_HYBRID = _agents("hybrid")
_ECONOMY = _agents(*_AGENT_ECONOMY)

#: Declared requirements of every boolean feature (a mode requires its switch).
REQUIREMENTS: dict[str, tuple[dict, ...]] = {
    "grain_reserves": (_ECONOMY,),
    "public_grain_shipments": (_feature("grain_reserves"), _ECONOMY),
    "grain_storage": (_HYBRID, _feature("grain_reserves")),
    "scholarship": (),
    "academy_services": (_HYBRID, _feature("scholarship"), _setting("techniques")),
    "workshops": (_HYBRID, _setting("cities")),
    "food_allocation": (_HYBRID,),
    "timber_stock": (_ECONOMY,),
    "grain_convoys": (_feature("public_grain_shipments"),),
    "commons_rules": (_feature("timber_stock"),),
    "learning_cohorts": (_HYBRID, _feature("academy_services")),
    "workshop_payroll": (_HYBRID, _feature("workshops"), _choice("workshop_mode", "operate")),
    "relocation_costs": (_HYBRID, _setting("no_household_mobility_liquid_requirement")),
    "local_budgets": (_HYBRID, _feature("grain_reserves")),
    "apprenticeship": (_HYBRID, _feature("workshops"), _choice("workshop_mode", "operate")),
    "repair_projects": (_HYBRID, _any(_feature("workshops"), _feature("grain_storage"))),
    "veteran_reintegration": (_HYBRID, _any(_feature("workshops"), _feature("apprenticeship"),
                                            _feature("repair_projects"))),
    "remittances": (_HYBRID,),
    "clearing_protection": (),
    "operating_wear": (_HYBRID, _feature("workshops"), _choice("workshop_mode", "operate")),
    "timber_supply": (_HYBRID, _feature("repair_projects"), _feature("timber_stock")),
    "recovery_crews": (_HYBRID, _feature("repair_projects")),
    "maintenance_obligation": (_feature("local_budgets"), _feature("repair_projects")),
    "household_retail": (_HYBRID, _feature("food_allocation")),
    "watershed": (_setting("procedural_world"),),
}


def _flag(key: str) -> str:
    return "--" + key.replace("_", "-")


def _label(key: str) -> str:
    return key.replace("_", " ").capitalize()


def _join(words: list[str]) -> str:
    return words[0] if len(words) == 1 else ", ".join(words[:-1]) + " or " + words[-1]


def _describe(condition: Mapping[str, Any]) -> str:
    if "agents" in condition:
        return "--agents " + _join(list(condition["agents"]))
    if "feature" in condition:
        return _flag(condition["feature"])
    if "choice" in condition:
        return f"{_flag(condition['choice'])} {_join(list(condition['values']))}"
    if "setting" in condition:
        return SETTINGS[condition["setting"]]
    return "one of: " + "; ".join(_describe(part) for part in condition["any"])


def _with_reasons(condition: Mapping[str, Any]) -> dict:
    result = dict(condition)
    if "any" in result:
        result["any"] = [_with_reasons(part) for part in result["any"]]
    result["reason"] = "requires " + _describe(condition)
    return result


def _parser_actions() -> dict[str, Any]:
    from chronicler.main import _build_parser
    return {action.dest: action for action in _build_parser()._actions}


def _entry(key: str, actions: Mapping[str, Any], *, group: str, experimental: bool,
           parent: str | None) -> dict:
    action = actions[key]
    choices = list(action.choices) if action.choices is not None else None
    if parent is None:
        requires = [_with_reasons(c) for c in REQUIREMENTS.get(key, ())]
    else:
        requires = [_with_reasons(_feature(parent))]
    return {
        "key": key,
        "flag": action.option_strings[0],
        "label": _label(key),
        "help": action.help or "",
        "kind": "choice" if choices is not None else "bool",
        "choices": choices,
        "default": None,
        "parent": parent,
        "requires": requires,
        "group": group,
        "experimental": experimental,
    }


@lru_cache(maxsize=1)
def _features() -> tuple[dict, ...]:
    actions = _parser_actions()
    entries: list[dict] = []
    for key, options in PREREQUISITES.items():
        entries.append(_entry(key, actions, group=PREREQUISITES_GROUP, experimental=False, parent=None))
        for option in options:
            entries.append(_entry(option, actions, group=PREREQUISITES_GROUP, experimental=False, parent=key))
    parent = None
    for key in LIVELIHOODS_ARG_KEYS:
        is_switch = key in LIVELIHOODS_SWITCHES
        if is_switch:
            parent = key
        elif key not in LIVELIHOODS_CHOICES or parent is None:
            raise ValueError(f"livelihoods key {key!r} is neither a switch nor a mode of one")
        entry = _entry(key, actions, group=LIVELIHOODS_GROUP, experimental=True,
                       parent=None if is_switch else parent)
        if not is_switch and entry["choices"] != list(LIVELIHOODS_CHOICES[key]):
            raise ValueError(f"{key} parser choices differ from LIVELIHOODS_CHOICES")
        entries.append(entry)
    return tuple(entries)


def feature_entries() -> list[dict]:
    """The catalog's entries (copies), prerequisites first, then livelihoods."""
    return copy.deepcopy(list(_features()))


def catalog_keys() -> tuple[str, ...]:
    return tuple(entry["key"] for entry in _features())


def _by_key() -> dict[str, dict]:
    return {entry["key"]: entry for entry in _features()}


def _cities_default() -> bool:
    from chronicler.cities import DEFAULT_ENABLED_FOR_NEW_WORLDS
    return bool(DEFAULT_ENABLED_FOR_NEW_WORLDS)


def _techniques_default() -> bool:
    from chronicler.techniques import DEFAULT_ENABLED_FOR_NEW_WORLDS
    return bool(DEFAULT_ENABLED_FOR_NEW_WORLDS)


def live_surface(args: Any = None) -> dict:
    """What a lobby ``start`` inherits from the server's command line: the
    agent mode, explicit values of catalog keys and the settings."""
    agents = getattr(args, "agents", "off") if args is not None else "off"
    values = {key: getattr(args, key) for key in catalog_keys()
              if args is not None and getattr(args, key, None) is not None}
    cities = getattr(args, "cities", None)
    techniques = getattr(args, "techniques", None)
    mobility = getattr(args, "household_mobility_liquid_requirement", None) or 0
    return {
        "agents": agents,
        "agent_modes": [agents],
        "values": values,
        "settings": {
            "cities": _cities_default() if cities is None else bool(cities),
            "techniques": _techniques_default() if techniques is None else bool(techniques),
            "no_household_mobility_liquid_requirement": not mobility > 0,
            # The client's start message chooses the world, so the server's
            # surface cannot promise a procedural one.
            "procedural_world": False,
        },
        "new_worlds_only": True,
    }


def _batch_value(name: str, client_defaults: Mapping[str, Any], config: Mapping[str, Any] | None):
    # The same lookup as LiveServer's batch worker.
    if config is not None:
        return config.get(name, client_defaults.get(name))
    return client_defaults.get(name)


def batch_surface(client_defaults: Mapping[str, Any], config: Mapping[str, Any] | None = None) -> dict:
    """What Batch Lab runs inherit: the agent mode (the config's, or the
    server's), the server's expansion prerequisites and the settings (batch
    runs are new worlds and are not given --cities or a mobility requirement)."""
    from chronicler.expansion_features import EXPANSION_PREREQUISITES
    keys = set(catalog_keys())
    values = {}
    for name in EXPANSION_PREREQUISITES:
        value = _batch_value(name, client_defaults, config)
        if name in keys and value is not None:
            values[name] = value
    techniques = _batch_value("techniques", client_defaults, config)
    agents = client_defaults.get("agents", "off")
    # Batch Lab runs pass no --worldgen: ``auto`` is procedural above 12 regions.
    from chronicler.world_gen import resolve_worldgen
    regions = _batch_value("regions", client_defaults, config) or 8
    return {
        "agents": config.get("agents", agents) if config is not None else agents,
        "agent_modes": list(AGENT_MODES),
        "values": values,
        "settings": {
            "cities": _cities_default(),
            "techniques": _techniques_default() if techniques is None else bool(techniques),
            "no_household_mobility_liquid_requirement": True,
            "procedural_world": isinstance(regions, int) and regions > 0
            and resolve_worldgen(None, regions) == "procedural",
        },
        "new_worlds_only": True,
    }


def lobby_feature_catalog(args: Any = None) -> dict:
    """The ``feature_catalog`` field of the lobby ``init`` message."""
    from chronicler.expansion_features import EXPANSION_PREREQUISITES
    defaults = {"agents": getattr(args, "agents", "off") if args is not None else "off"}
    for name in EXPANSION_PREREQUISITES:
        defaults[name] = getattr(args, name, None) if args is not None else None
    return {
        "schema_version": CATALOG_SCHEMA_VERSION,
        "features": feature_entries(),
        "settings": dict(SETTINGS),
        "surfaces": {"live": live_surface(args), "batch": batch_surface(defaults)},
    }


def _satisfied(condition: Mapping[str, Any], effective: Mapping[str, Any], surface: Mapping[str, Any],
               entries: Mapping[str, dict]) -> bool:
    if "agents" in condition:
        return surface.get("agents") in condition["agents"]
    if "feature" in condition:
        return effective.get(condition["feature"]) is True
    if "choice" in condition:
        key = condition["choice"]
        value = effective.get(key)
        return (entries[key]["choices"][0] if value is None else value) in condition["values"]
    if "setting" in condition:
        return surface.get("settings", {}).get(condition["setting"]) is True
    return any(_satisfied(part, effective, surface, entries) for part in condition["any"])


def unmet_requirements(features: Mapping[str, Any], surface: Mapping[str, Any]) -> list[str]:
    """Every requirement an on feature misses, as messages (catalog order)."""
    entries = _by_key()
    effective = {**surface.get("values", {}), **features}
    problems = []
    for key, entry in entries.items():
        active = (effective.get(key) is True) if entry["kind"] == "bool" else key in features
        if not active:
            continue
        for condition in entry["requires"]:
            if not _satisfied(condition, effective, surface, entries):
                problem = f"'{key}' ({entry['flag']}) {condition['reason']}"
                if "agents" in condition:
                    problem += f" (this run uses --agents {surface.get('agents')})"
                problems.append(problem)
    return problems


def validate_features(features: Any, surface: Mapping[str, Any]) -> str | None:
    """Why a ``features`` request is refused, or None: keys must be catalog
    keys, values booleans or one of the choices, and every feature that is
    on (requested or inherited) must have its requirements met."""
    if not isinstance(features, dict):
        return "must be an object"
    entries = _by_key()
    for key, value in features.items():
        if not isinstance(key, str) or key not in entries:
            return f"unknown feature {key!r}"
        entry = entries[key]
        if entry["kind"] == "bool":
            if type(value) is not bool:
                return f"'{key}' must be a boolean"
        elif not isinstance(value, str) or value not in entry["choices"]:
            return f"'{key}' must be one of {', '.join(entry['choices'])}"
    problems = unmet_requirements(features, surface)
    return problems[0] if problems else None


def validate_batch_features(config: Mapping[str, Any], client_defaults: Mapping[str, Any]) -> str | None:
    """``validate_features`` for a ``batch_start`` config; a key may not be
    given both in ``features`` and at the top level of the config."""
    features = config.get("features")
    if features is None:
        return None
    if isinstance(features, dict):
        for key in features:
            if key in config:
                return f"'{key}' is given both in features and at the top level of the config"
    return validate_features(features, batch_surface(client_defaults, config))


def feature_cli_arguments(features: Mapping[str, Any]) -> list[str]:
    """The command-line flags that request ``features`` (catalog order)."""
    entries = _by_key()
    flags = []
    for key, entry in entries.items():
        if key not in features:
            continue
        value = features[key]
        if entry["kind"] == "bool":
            flags.append(entry["flag"] if value else "--no-" + entry["flag"][2:])
        else:
            flags.append(f"{entry['flag']}={value}")
    return flags


def apply_features(args: Any, features: Mapping[str, Any] | None) -> dict[str, Any]:
    """Set each requested feature on ``args`` as the CLI parser would; returns
    the previous values (for restoring)."""
    previous = {}
    for key, value in (features or {}).items():
        previous[key] = getattr(args, key, None)
        setattr(args, key, value)
    return previous
