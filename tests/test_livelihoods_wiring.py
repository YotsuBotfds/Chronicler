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
