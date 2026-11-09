"""Default-off wiring of the livelihoods sprint switches (no runtime behavior)."""
import json
import pickle

import pytest

from chronicler.batch_manifest import SIMULATION_ARG_KEYS, simulation_config
from chronicler.expansion_features import (
    expansion_arguments, expansion_feature_flags, expansion_snapshot_fields,
)
from chronicler.livelihoods import (
    LIVELIHOODS_ARG_KEYS, configure_livelihoods, livelihoods_arguments,
)
from chronicler.livelihoods_state import LIVELIHOODS_SWITCHES, LivelihoodsState
from chronicler.main import _build_parser
from chronicler.world_gen import generate_world


@pytest.fixture
def world():
    return generate_world(seed=42, num_regions=6, num_civs=2)


def test_parser_defaults_are_absent_and_flags_parse():
    parser = _build_parser()
    default = parser.parse_args([])
    assert all(getattr(default, key) is None for key in LIVELIHOODS_ARG_KEYS)
    assert set(LIVELIHOODS_ARG_KEYS) <= set(SIMULATION_ARG_KEYS)
    assert not set(LIVELIHOODS_ARG_KEYS) & set(simulation_config(default))
    args = parser.parse_args(["--workshops", "--workshop-mode", "observe", "--no-timber-stock",
                              "--food-allocation-regime", "equal"])
    assert (args.workshops, args.workshop_mode, args.timber_stock) == (True, "observe", False)
    config = simulation_config(args)
    assert config["workshops"] is True and config["workshop_mode"] == "observe"
    assert config["timber_stock"] is False and config["food_allocation_regime"] == "equal"
    forwarded = expansion_arguments(args)
    assert {"--workshops", "--workshop-mode=observe", "--no-timber-stock",
            "--food-allocation-regime=equal"} <= set(forwarded)
    assert livelihoods_arguments(default) == []


def test_never_enabled_world_has_no_container_flags_or_snapshot(world):
    args = _build_parser().parse_args(["--no-workshops", "--no-grain-convoys"])
    before = world.model_dump_json()
    configure_livelihoods(world, args, agent_mode="hybrid")
    assert world.livelihoods is None and world.model_dump_json() == before
    assert not set(LIVELIHOODS_SWITCHES) & set(expansion_feature_flags(world))
    assert "livelihoods" not in expansion_snapshot_fields(world)
    assert "livelihoods" not in json.loads(world.model_dump_json())


def test_prerequisites_are_enforced(world):
    parse = _build_parser().parse_args
    with pytest.raises(ValueError, match="hybrid"):
        configure_livelihoods(world, parse(["--food-allocation"]), agent_mode="off")
    with pytest.raises(ValueError, match="agent-backed"):
        configure_livelihoods(world, parse(["--timber-stock"]), agent_mode="off")
    with pytest.raises(ValueError, match="public-grain-shipments"):
        configure_livelihoods(world, parse(["--grain-convoys"]), agent_mode="hybrid")
    assert world.livelihoods is None


def test_container_pickle_backfills_missing_switches():
    state = LivelihoodsState()
    raw = state.__getstate__()
    for name in LIVELIHOODS_SWITCHES:
        raw["__dict__"].pop(name, None)
    back = LivelihoodsState.__new__(LivelihoodsState)
    back.__setstate__(raw)
    assert all(getattr(back, name) is None for name in LIVELIHOODS_SWITCHES)
    assert pickle.loads(pickle.dumps(back)).model_dump_json() == state.model_dump_json()


def test_screen_runner_counts_only_real_livelihoods_switches():
    """Lead review 2026-11-05: the sprint-2 screen runner keyed L7 as
    'relocation' while its snapshot key is 'relocation_costs', so its outcomes
    would have been silently dropped. Every counted package must be a switch."""
    import importlib.util
    from pathlib import Path
    from chronicler.livelihoods_state import LIVELIHOODS_SWITCHES
    path = Path(__file__).resolve().parents[1] / "scripts" / "livelihoods_screens.py"
    spec = importlib.util.spec_from_file_location("livelihoods_screens_under_test", path)
    screens = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(screens)
    assert set(screens.COUNTED) <= set(LIVELIHOODS_SWITCHES)
    assert set(screens.FUNNEL_KEYS) == set(screens.COUNTED)
    screens.check_counted()
    for name, (flags, control, _tuning) in screens.ARMS2.items():
        assert control is None or control in screens.ARMS2, name


def _saved_checkpoint(world, flags):
    """A loaded checkpoint as ``_adopt_checkpoint_args`` reads it."""
    from types import SimpleNamespace
    simulation_args = simulation_config(_build_parser().parse_args(flags))
    return SimpleNamespace(state=SimpleNamespace(world=world, seed=42, num_turns=8,
                                                 run_config={"simulation_args": simulation_args}))


def _world_with_workshops_and_fares(world):
    # A realistic saved workshops world has cities (``--workshops requires
    # cities``); FIX-7 checks the saved switches' prerequisites on resume.
    from chronicler.cities_state import CityState
    from chronicler.relocation_costs_state import RelocationCostsState
    from chronicler.workshops_state import WorkshopState
    world.cities = CityState()
    world.livelihoods = LivelihoodsState()
    world.livelihoods.workshops = WorkshopState(mode="operate")
    world.livelihoods.relocation_costs = RelocationCostsState(mode="paid")
    return world


def test_exact_resume_refuses_livelihoods_options_the_checkpoint_never_recorded(world):
    """Review R3 2026-11-05. ``simulation_config`` omits livelihoods options
    that were never given, so ``_adopt_checkpoint_args`` never compared them:
    ``--resume CKPT --workshops`` (or ``--relocation-mode assisted``) exited 0
    and silently continued without the request. An exact resume refuses any
    option given with a value other than the checkpoint's
    (docs/integration/checkpoint-continuation.md, section 1)."""
    from chronicler.main import _adopt_checkpoint_args
    parser = _build_parser()
    world.turn = 2
    off = _saved_checkpoint(world, [])
    before = world.model_dump_json()
    # Requests that agree with the retained state stay accepted.
    assert _adopt_checkpoint_args(parser, parser.parse_args(["--no-workshops", "--no-timber-stock"]), off) == []
    for flags in (["--workshops"], ["--timber-stock"], ["--local-budgets"], ["--grain-convoys"],
                  ["--workshop-mode", "cost_only"], ["--relocation-mode", "assisted"]):
        conflicts = _adopt_checkpoint_args(parser, parser.parse_args(flags), off)
        assert len(conflicts) == 1 and "conflicts with the checkpoint" in conflicts[0], flags
    assert world.livelihoods is None and world.model_dump_json() == before

    on = _saved_checkpoint(_world_with_workshops_and_fares(world), ["--workshops", "--relocation-costs"])
    before = world.model_dump_json()
    for flags in ([], ["--workshops"], ["--workshop-mode", "operate"], ["--relocation-mode", "paid"],
                  ["--no-food-allocation"]):
        args = parser.parse_args(flags)
        assert _adopt_checkpoint_args(parser, args, on) == [], flags
        # An omitted switch takes the checkpoint's value.
        assert args.workshops is True and args.relocation_costs is True
    for flags in (["--no-workshops"], ["--no-relocation-costs"], ["--workshop-mode", "cost_only"],
                  ["--relocation-mode", "liquidity_only"], ["--food-allocation"]):
        conflicts = _adopt_checkpoint_args(parser, parser.parse_args(flags), on)
        assert len(conflicts) == 1 and "conflicts with the checkpoint" in conflicts[0], flags
    assert world.model_dump_json() == before


def test_state_file_resume_keeps_omitted_switches_and_explicit_disable_only_freezes_one(world, tmp_path):
    """Review R3 adversarial: a legacy state-file resume re-applies the CLI.
    Omitted switches keep the saved sub-states byte for byte; an explicit
    ``--no-x`` disables only x (its state is kept, frozen); re-enabling resumes."""
    from chronicler.models import WorldState
    from chronicler.livelihoods import livelihoods_feature_flags
    parse = _build_parser().parse_args
    _world_with_workshops_and_fares(world)
    configure_livelihoods(world, parse(["--timber-stock"]), agent_mode="hybrid")
    saved = world.livelihoods.model_dump_json()
    path = tmp_path / "state.json"
    world.save(path)
    loaded = WorldState.load(path)
    assert loaded.livelihoods.model_dump_json() == saved
    configure_livelihoods(loaded, parse([]), agent_mode="hybrid")
    assert loaded.livelihoods.model_dump_json() == saved
    configure_livelihoods(loaded, parse(["--no-timber-stock"]), agent_mode="hybrid")
    state = loaded.livelihoods
    assert state.timber_stock.enabled is False and state.timber_stock.stocks == world.livelihoods.timber_stock.stocks
    assert state.workshops.model_dump() == world.livelihoods.workshops.model_dump()
    assert livelihoods_feature_flags(loaded)["timber_stock"] is False
    assert "timber_stock" not in expansion_snapshot_fields(loaded).get("livelihoods", {})
    configure_livelihoods(loaded, parse(["--timber-stock"]), agent_mode="hybrid")
    assert loaded.livelihoods.model_dump_json() == saved
    # Dependants of a disabled prerequisite stay dormant, never re-created.
    with pytest.raises(ValueError, match="requires --timber-stock"):
        configure_livelihoods(loaded, parse(["--no-timber-stock", "--commons-rules"]), agent_mode="hybrid")


def test_feature_off_checkpoint_of_the_baseline_loads_without_the_field(world, tmp_path):
    """Review R3 adversarial: a world pickled by main 64863f1 has no
    ``livelihoods`` entry at all. This code must load it, serialize it to the
    exact baseline bytes and add no flag, snapshot key or container until a
    switch is explicitly enabled."""
    from chronicler.run_checkpoint import load_world, read_checkpoint, save_world
    world.turn = 3
    expected = world.model_dump_json()
    del world.__dict__["livelihoods"]          # main's pickled WorldState
    assert world.model_dump_json() == expected
    path = tmp_path / "baseline.ckpt"
    save_world(path, world)
    header = read_checkpoint(path).header
    assert not set(LIVELIHOODS_SWITCHES) & set(header["flags"])
    back = load_world(path)
    assert "livelihoods" not in back.__dict__ and getattr(back, "livelihoods", None) is None
    assert back.model_dump_json() == expected and "livelihoods" not in json.loads(back.model_dump_json())
    assert not set(LIVELIHOODS_SWITCHES) & set(expansion_feature_flags(back))
    assert "livelihoods" not in expansion_snapshot_fields(back)
    configure_livelihoods(back, _build_parser().parse_args(["--no-workshops", "--no-timber-stock"]),
                          agent_mode="hybrid")
    assert getattr(back, "livelihoods", None) is None and back.model_dump_json() == expected
    configure_livelihoods(back, _build_parser().parse_args(["--timber-stock"]), agent_mode="hybrid")
    assert back.livelihoods.timber_stock.enabled is True


def test_feature_on_checkpoint_keeps_every_switch_when_resumed_with_flags_omitted(world, tmp_path):
    """Review R3 adversarial: the header flags, the retained sub-states and the
    adopted arguments of a features-on checkpoint resumed with no flags."""
    from chronicler.main import _adopt_checkpoint_args
    from chronicler.run_checkpoint import read_checkpoint, save_world
    parse = _build_parser().parse_args
    _world_with_workshops_and_fares(world)
    configure_livelihoods(world, parse(["--timber-stock"]), agent_mode="hybrid")
    configure_livelihoods(world, parse(["--no-relocation-costs"]), agent_mode="hybrid")
    world.turn = 4
    saved = world.livelihoods.model_dump_json()
    path = tmp_path / "on.ckpt"
    save_world(path, world)
    loaded = read_checkpoint(path)
    flags = loaded.header["flags"]
    assert flags["timber_stock"] is True and flags["relocation_costs"] is False
    assert "food_allocation" not in flags                 # never enabled: no flag
    assert loaded.state.world.livelihoods.model_dump_json() == saved
    loaded.state.run_config = {"simulation_args": simulation_config(
        parse(["--workshops", "--timber-stock", "--no-relocation-costs"]))}
    loaded.state.num_turns = 8
    args = parse([])
    assert _adopt_checkpoint_args(_build_parser(), args, loaded) == []
    assert (args.workshops, args.timber_stock, args.relocation_costs) == (True, True, False)
    assert loaded.state.world.livelihoods.model_dump_json() == saved
    for flags in (["--relocation-costs"], ["--relocation-mode", "assisted"], ["--workshop-mode", "observe"]):
        assert len(_adopt_checkpoint_args(_build_parser(), parse(flags), loaded)) == 1, flags
    assert loaded.state.world.livelihoods.model_dump_json() == saved


# --- FIX-7: saved prerequisites ---------------------------------------------
# (Lead scope ruling 2026-11-09: a mode given without its switch, and a mode
# that differs from the saved one, stay accepted; see the household-retail,
# recovery-crews and recovery-skills resume tests.)

def _saved_workshops(world, mode="operate"):
    from chronicler.cities_state import CityState
    from chronicler.workshops_state import WorkshopState
    world.cities = CityState()
    world.livelihoods = LivelihoodsState()
    world.livelihoods.workshops = WorkshopState(mode=mode)
    return world


def test_a_saved_switch_outside_its_prerequisites_is_refused_with_the_way_to_end_it(world):
    from chronicler.livelihoods import LivelihoodsRefusal
    parse = _build_parser().parse_args
    _saved_workshops(world)
    saved = world.livelihoods.model_dump_json()
    with pytest.raises(LivelihoodsRefusal) as refused:
        configure_livelihoods(world, parse([]), agent_mode="off")
    assert str(refused.value) == ("--workshops requires --agents hybrid; this world has it on: "
                                  "pass --no-workshops to end it")
    assert world.livelihoods.model_dump_json() == saved
    # The explicit request keeps its text; resuming in hybrid is accepted;
    # --no-workshops ends the saved switch outside hybrid.
    with pytest.raises(ValueError) as explicit:
        configure_livelihoods(world, parse(["--workshops"]), agent_mode="off")
    assert str(explicit.value) == "--workshops requires --agents hybrid"
    assert not isinstance(explicit.value, LivelihoodsRefusal)
    configure_livelihoods(world, parse([]), agent_mode="hybrid")
    assert world.livelihoods.model_dump_json() == saved
    configure_livelihoods(world, parse(["--no-workshops"]), agent_mode="off")
    assert world.livelihoods.workshops.enabled is False


def _differential_keys():
    """Switches whose prerequisites ``_check_prerequisites`` itself checks
    (not a module's own ``check_request``) over terms a generated world with
    cities can meet (no world setting other than cities and the mobility
    requirement, no exclusion)."""
    from chronicler import feature_catalog as fc
    module_owned = {"watershed", "infrastructure_condition", "harvest_cover", "epidemic_care",
                    "public_health", "movement_branches"}
    world_settings = {"cities", "no_household_mobility_liquid_requirement"}

    def plain(condition):
        if "setting" in condition:
            return condition["setting"] in world_settings
        if "any" in condition:
            return all(plain(part) for part in condition["any"])
        return "not" not in condition

    entries = fc._by_key()
    return [key for key in LIVELIHOODS_SWITCHES if key not in module_owned and entries[key]["requires"]
            and all(plain(condition) for condition in entries[key]["requires"])]


def _differential_selections(key):
    """The smallest catalog selection with ``key`` on (livelihoods switches
    only: other prerequisites stay off), then each prerequisite dropped."""
    from chronicler import feature_catalog as fc
    entries = fc._by_key()
    selection, stack = {key: True}, [key]

    def walk(condition):
        if "feature" in condition:
            if condition["feature"] in LIVELIHOODS_SWITCHES and condition["feature"] not in selection:
                selection[condition["feature"]] = True
                stack.append(condition["feature"])
        elif "choice" in condition:
            if entries[condition["choice"]]["choices"][0] not in condition["values"]:
                selection[condition["choice"]] = condition["values"][0]
        elif "any" in condition:
            walk(next((part for part in condition["any"] if part.get("feature") in LIVELIHOODS_SWITCHES),
                      condition["any"][0]))

    while stack:
        for condition in entries[stack.pop()]["requires"]:
            walk(condition)
    yield selection
    for other in selection:
        if other != key and other in LIVELIHOODS_SWITCHES:
            yield {k: v for k, v in selection.items() if k != other and entries[k]["parent"] != other}


def _saved_sub_state(name, selection):
    """A saved enabled sub-state holding the selection's choices (else each
    choice's catalog default, the value the catalog assumes)."""
    import typing
    from chronicler import feature_catalog as fc
    from chronicler.livelihoods import _CHOICE_FIELDS
    entries = fc._by_key()
    annotation = LivelihoodsState.model_fields[name].annotation
    cls = next(arg for arg in typing.get_args(annotation) if arg is not type(None))
    fields = {}
    for key, (switch, field) in _CHOICE_FIELDS.items():
        if switch != name:
            continue
        value = selection.get(key, entries[key]["choices"][0])
        if field in cls.model_fields:
            fields[field] = value
        elif field == "rules" and "rules_version" in cls.model_fields:
            fields["rules_version"] = int(value)
    return cls.model_construct(enabled=True, **fields)


def test_saved_and_requested_switches_meet_the_catalog_requirements():
    """FIX-7 differential: for each switch with declared requirements, the
    run's check accepts the same selections whether they are requested or
    only saved, and agrees with ``feature_catalog.unmet_requirements``
    (agents off and hybrid)."""
    from chronicler import feature_catalog as fc
    from chronicler.cities_state import CityState
    from chronicler.livelihoods import _check_prerequisites
    parse = _build_parser().parse_args

    def fresh():
        world = generate_world(seed=42, num_regions=6, num_civs=2)
        world.cities = CityState()
        return world

    def verdict(world, values, args, agents):
        try:
            _check_prerequisites(world, values, agents, args)
        except ValueError as exc:
            return exc
        return None

    keys = _differential_keys()
    assert {"workshops", "food_allocation", "timber_stock", "grain_convoys", "commons_rules",
            "learning_cohorts", "workshop_payroll", "relocation_costs", "local_budgets", "apprenticeship",
            "repair_projects", "veteran_reintegration", "remittances", "recovery_crews",
            "maintenance_obligation", "operating_wear"} <= set(keys)
    problems, accepted, refused = [], 0, 0
    for key in keys:
        for selection in _differential_selections(key):
            switches = [k for k in selection if k in LIVELIHOODS_SWITCHES]
            choices = {k: v for k, v in selection.items() if k not in LIVELIHOODS_SWITCHES}
            for agents in ("off", "hybrid"):
                catalog = fc.unmet_requirements(selection, fc.live_surface(parse(["--agents", agents])))
                values = {name: (True if name in switches else None) for name in LIVELIHOODS_SWITCHES}
                requested = verdict(fresh(), values,
                                    parse(["--agents", agents, *fc.feature_cli_arguments(choices)]), agents)
                world = fresh()
                world.livelihoods = LivelihoodsState()
                for name in switches:
                    setattr(world.livelihoods, name, _saved_sub_state(name, selection))
                saved = verdict(world, dict.fromkeys(LIVELIHOODS_SWITCHES), parse(["--agents", agents]), agents)
                if not ((not catalog) == (requested is None) == (saved is None)):
                    problems.append((key, agents, selection, catalog, str(requested), str(saved)))
                accepted += saved is None
                refused += saved is not None
    assert problems == []
    assert accepted and refused
