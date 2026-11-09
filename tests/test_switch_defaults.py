"""The new-world switch defaults registry (chronicler.switch_defaults, CON-1).

One registry decides which persisted switches a new world gets: the CLI
(``main._configure_run``, which batch runs use), live lobby worlds
(``live._live_world``) and the feature catalog read it.
"""

from __future__ import annotations

import ast
import importlib
import re
from pathlib import Path

import pytest

from chronicler import switch_defaults as SD
from chronicler.main import _build_parser, _configure_run
from chronicler.world_gen import generate_world

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "chronicler"

#: The production core (DEC-2): the 17 default-on systems.
DEFAULT_ON = {
    "campaigns", "mutual_aid", "fisheries", "governance", "contact_ledger", "epidemiology",
    "finance", "diplomacy", "techniques", "maritime", "gp_agendas", "nomads", "cities",
    "agent_movements", "guilds", "historiography", "languages",
}


def _main_slices() -> list[list[str]]:
    """The ``_switches(...)`` slices of ``main._configure_run``, in source order."""
    tree = ast.parse((SRC / "main.py").read_text(encoding="utf-8"))
    fn = next(node for node in ast.walk(tree)
              if isinstance(node, ast.FunctionDef) and node.name == "_configure_run")
    calls = [node for node in ast.walk(fn)
             if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "_switches"]
    calls.sort(key=lambda node: (node.lineno, node.col_offset))
    return [[arg.value for arg in call.args] for call in calls]


def _live_world(argv=(), **params):
    from chronicler.live import _live_world as build
    args = _build_parser().parse_args(["--live", *argv])
    world, _ = build(args, {"seed": 42, "regions": 8, "civs": 4, **params})
    return world


def _cli_world(tmp_path, argv=(), fresh_world=True):
    args = _build_parser().parse_args(["--seed", "42", "--turns", "3", *argv])
    world = generate_world(seed=42, num_regions=8, num_civs=4)
    _configure_run(args, world, fresh_world, tmp_path / "out" / "chronicle.md")
    return world


def test_registry_order_is_mains_and_main_applies_every_row_once():
    names = [row.name for row in SD.SWITCHES]
    assert len(names) == len(set(names)) == 21
    applied = [name for names_ in _main_slices() for name in names_]
    assert applied == names


def test_every_default_on_module_is_in_the_registry():
    on = set()
    for path in SRC.rglob("*.py"):
        if re.search(r"^DEFAULT_ENABLED_FOR_NEW_WORLDS = True\b", path.read_text(encoding="utf-8"), re.M):
            on.add(".".join(("chronicler", *path.relative_to(SRC).with_suffix("").parts)))
    modules = {row.module for row in SD.SWITCHES}
    assert on <= modules
    assert len(on) == 16  # plus campaigns' CAMPAIGNS_DEFAULT_FOR_NEW_WORLDS
    assert {row.name for row in SD.SWITCHES if SD.default(row.name)} == DEFAULT_ON


def test_rows_resolve_and_list_their_qualification_status():
    for row in SD.SWITCHES:
        module = importlib.import_module(row.module)
        assert isinstance(getattr(module, row.default_attr), bool), row.name
        if row.setter is not None:
            assert callable(getattr(module, row.setter)), row.name
        if row.enabled is not None:
            assert callable(getattr(module, row.enabled)), row.name
        else:
            assert row.world_attr, row.name
        assert row.status.strip(), row.name
        assert all(req in {r.name for r in SD.SWITCHES} for req in row.requires)
        names = [r.name for r in SD.SWITCHES]
        assert all(names.index(req) < names.index(row.name) for req in row.requires), row.name
    assert "[CALIBRATE]" in SD.entry("fisheries").status
    # Governance is the only live exemption (until COR-2).
    assert [row.name for row in SD.SWITCHES if row.live_exempt] == ["governance"]


def test_unknown_switch_names_are_refused():
    world = generate_world(seed=1, num_regions=4, num_civs=2)
    with pytest.raises(KeyError):
        SD.apply_switches(world, _build_parser().parse_args([]), fresh_world=True, names=("no_such",))


def test_cli_and_live_new_worlds_agree_except_live_exemptions(tmp_path):
    cli = SD.switch_state(_cli_world(tmp_path))
    live = SD.switch_state(_live_world())
    exempt = {row.name for row in SD.SWITCHES if row.live_exempt}
    assert {name: on for name, on in cli.items() if name not in exempt} == \
        {name: on for name, on in live.items() if name not in exempt}
    assert cli == {row.name: row.name in DEFAULT_ON for row in SD.SWITCHES}
    # Governance stays off on new live worlds until COR-2.
    assert cli["governance"] is True and live["governance"] is False


@pytest.mark.parametrize("name", [row.name for row in SD.SWITCHES if not row.live_exempt])
def test_live_flags_override_each_default(name):
    flag = "--" + name.replace("_", "-")
    on = SD.switch_state(_live_world([flag]))
    off = SD.switch_state(_live_world(["--no-" + flag[2:]]))
    assert off[name] is False
    # A prerequisite the default leaves on keeps an explicit on in effect.
    assert on[name] is all(SD.default(req) for req in SD.entry(name).requires)


def test_prerequisites_hold_on_live_and_default_cli_worlds(tmp_path):
    live = SD.switch_state(_live_world(["--epidemiology", "--no-contact-ledger"]))
    assert live["epidemiology"] is False and live["contact_ledger"] is False
    live = SD.switch_state(_live_world(["--domestic-credit", "--no-finance"]))
    assert live["domestic_credit"] is False
    assert SD.switch_state(_live_world(["--domestic-credit"]))["domestic_credit"] is True
    # The CLI's default-on epidemiology stays off without the ledger; an
    # explicit --epidemiology without it is refused.
    assert SD.switch_state(_cli_world(tmp_path, ["--no-contact-ledger"]))["epidemiology"] is False
    with pytest.raises(ValueError, match="contact ledger"):
        _cli_world(tmp_path, ["--epidemiology", "--no-contact-ledger"])


def test_supplied_worlds_keep_their_settings(tmp_path):
    world = generate_world(seed=42, num_regions=8, num_civs=4)
    before = SD.switch_state(world)
    args = _build_parser().parse_args([])
    SD.apply_switches(world, args, fresh_world=False)
    assert SD.switch_state(world) == before
    assert SD.switch_state(_cli_world(tmp_path, fresh_world=False)) == before
    # An explicit switch still applies to a supplied world.
    assert SD.switch_state(_cli_world(tmp_path, ["--no-nomads", "--nomads"], fresh_world=False))["nomads"] is True


def test_feature_catalog_settings_follow_the_registry():
    from chronicler import feature_catalog as FC
    settings = FC.live_surface(_build_parser().parse_args(["--live"]))["settings"]
    for name in ("cities", "techniques", "agent_movements", "guilds"):
        assert settings[name] is SD.default(name)
    assert settings["epidemiology"] is (SD.default("epidemiology") and SD.default("contact_ledger"))
    batch = FC.batch_surface({"agents": "off"})["settings"]
    for name in ("cities", "techniques", "agent_movements", "guilds"):
        assert batch[name] is SD.default(name)


def test_batch_manifests_record_every_registry_switch():
    from chronicler.batch_manifest import SIMULATION_ARG_KEYS
    assert {row.name for row in SD.SWITCHES} <= set(SIMULATION_ARG_KEYS)
