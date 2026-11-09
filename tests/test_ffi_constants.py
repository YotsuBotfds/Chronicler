"""Regression tests for shared Python/Rust FFI constants."""

import re

import pytest

from tests import rust_source_constants as rsc


def test_ffi_constants_match_rust_discriminants_and_legacy_aliases():
    from chronicler.ffi_constants import TERRAIN_MAP, VALUE_EMPTY, VALUE_TO_ID

    assert TERRAIN_MAP == {
        "plains": 0,
        "mountains": 1,
        "coast": 2,
        "forest": 3,
        "desert": 4,
        "tundra": 5,
        "river": 0,
        "hills": 0,
        "steppe": 6,
        "jungle": 7,
        "marsh": 8,
    }
    assert VALUE_TO_ID == {
        "Freedom": 0,
        "Order": 1,
        "Tradition": 2,
        "Knowledge": 3,
        "Honor": 4,
        "Cunning": 5,
    }
    assert VALUE_EMPTY == 0xFF


def test_culture_import_does_not_require_agent_bridge_or_native_extension():
    import importlib
    import sys
    import chronicler

    def isolated_module(name):
        return name in {"chronicler.culture", "chronicler.agent_bridge"} or (
            name == "chronicler_agents" or name.startswith("chronicler_agents.")
        )

    original_modules = {name: module for name, module in sys.modules.items() if isolated_module(name)}
    missing = object()
    original_attributes = {name: getattr(chronicler, name, missing) for name in ("culture", "agent_bridge")}
    try:
        for name in original_modules:
            sys.modules.pop(name)
        for name in original_attributes:
            chronicler.__dict__.pop(name, None)

        importlib.import_module("chronicler.culture")

        assert "chronicler.agent_bridge" not in sys.modules
        assert "chronicler_agents" not in sys.modules
        assert "chronicler_agents.chronicler_agents" not in sys.modules
    finally:
        # Other collected tests may retain AgentBridge class references. Restore
        # both import caches exactly so their real checkpoints remain picklable.
        for name in list(sys.modules):
            if isolated_module(name):
                sys.modules.pop(name)
        sys.modules.update(original_modules)
        for name, value in original_attributes.items():
            if value is missing:
                chronicler.__dict__.pop(name, None)
            else:
                setattr(chronicler, name, value)


# ---------------------------------------------------------------------------
# CON-5: parity rows for the Python <-> Rust constant mirrors. Each row reads
# the Rust source text (no native extension needed) through
# ``tests/rust_source_constants.py``.
# ---------------------------------------------------------------------------

_LEGACY_TERRAIN_ALIASES = frozenset({"river", "hills"})


def _snake(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


def test_terrain_enum_matches_terrain_map_without_legacy_aliases():
    from chronicler.ffi_constants import TERRAIN_MAP

    rust = {name.lower(): value for name, value in rsc.enum("region.rs", "Terrain").items()}
    python = {name: value for name, value in TERRAIN_MAP.items() if name not in _LEGACY_TERRAIN_ALIASES}
    assert rust == python


def test_bond_type_enum_and_positive_valence_match_ffi_constants():
    from chronicler.ffi_constants import BOND_TYPES, POSITIVE_VALENCE_BONDS

    rust = {_snake(name): value for name, value in rsc.enum("relationships.rs", "BondType").items()}
    assert rust["exile_bond"] == BOND_TYPES["exile_bond"]
    assert rust == BOND_TYPES

    src = rsc.read_source("relationships.rs")
    m = re.search(r"fn is_positive_valence\([^)]*\)\s*->\s*bool\s*\{\s*matches!\(\s*\w+\s*,\s*([0-9|\s]+)\)", src)
    assert m, "is_positive_valence not found in relationships.rs"
    arms = {int(arm) for arm in m.group(1).split("|")}
    assert arms == set(POSITIVE_VALENCE_BONDS)


def test_cultural_value_empty_matches_value_empty():
    from chronicler.ffi_constants import VALUE_EMPTY

    assert rsc.const("agent.rs", "CULTURAL_VALUE_EMPTY") == VALUE_EMPTY


def test_terrain_caps_and_floors_match_python_ecology():
    from chronicler import ecology
    from chronicler.ffi_constants import TERRAIN_MAP

    caps = rsc.array("ecology.rs", "TERRAIN_CAPS")
    by_id = {value: name for name, value in TERRAIN_MAP.items() if name not in _LEGACY_TERRAIN_ALIASES}
    assert len(caps) == len(by_id)
    for terrain_id, row in enumerate(caps):
        expected = ecology.TERRAIN_ECOLOGY_CAPS[by_id[terrain_id]]
        assert row == [expected["soil"], expected["water"], expected["forest_cover"]], by_id[terrain_id]

    floors = rsc.array("ecology.rs", "TERRAIN_FLOORS")
    assert floors == [ecology._FLOOR_SOIL, ecology._FLOOR_WATER, ecology._FLOOR_FOREST]


def test_season_and_climate_tables_match_resources():
    from chronicler import resources

    assert rsc.array("ecology.rs", "SEASON_MOD") == resources.SEASON_MOD
    assert rsc.array("ecology.rs", "CLIMATE_CLASS_MOD") == resources.CLIMATE_CLASS_MOD


def _movement_pairs() -> dict:
    """Every movements.rs constant with a Python mirror (Rust name -> Python value).

    A Rust constant is checked once it is listed here; the end and reform ids
    and the recruitment/lapse tuning have no Rust or no Python counterpart.
    """
    from chronicler import agent_movements as am
    from chronicler import agent_movements_state as st
    from chronicler import guilds

    return {
        "CREED_COMMONS": st.COMMONS,
        "CREED_LIBERTY": st.LIBERTY,
        "CREED_SECT": st.SECT,
        "CREED_GUILD": st.GUILD,
        "CREED_COUNT": st.NEED_CREEDS,
        "STAGE_GATHERING": st.GATHERING,
        "STAGE_PRESSING": st.PRESSING,
        "STAGE_SUPPRESSED": st.SUPPRESSED,
        "STAGE_RISING": st.RISING,
        "STAGE_SATISFIED": st.SATISFIED,
        "NO_REGION": am.NO_REGION,
        "NO_FAITH": am.NO_FAITH,
        "NO_RELIEF": am.NO_RELIEF,
        "ADULT_AGE": am.ADULT_AGE,
        "RELIEF_TURNS": am.RELIEF_TURNS,
        "GUILD_SAT": guilds.MOVEMENT_SATISFACTION,
    }


def _check_movement_constants() -> None:
    for rust_name, python_value in _movement_pairs().items():
        rust_value = rsc.const("movements.rs", rust_name)
        if isinstance(rust_value, float):
            assert rust_value == pytest.approx(python_value), rust_name
        else:
            assert rust_value == python_value, rust_name


def test_movement_constants_match_python_mirrors():
    _check_movement_constants()


def test_movement_parity_row_fails_on_a_changed_rust_constant(monkeypatch):
    original = rsc.read_source

    def mutated(path):
        text = original(path)
        if str(path) == "movements.rs":
            changed = text.replace("pub const RELIEF_TURNS: u16 = 20;", "pub const RELIEF_TURNS: u16 = 21;")
            assert changed != text, "RELIEF_TURNS declaration not found for the mutation check"
            return changed
        return text

    monkeypatch.setattr(rsc, "read_source", mutated)
    with pytest.raises(AssertionError, match="RELIEF_TURNS"):
        _check_movement_constants()


def test_reader_names_a_missing_constant():
    with pytest.raises(AssertionError, match="NOT_A_CONSTANT not found in movements.rs"):
        rsc.const("movements.rs", "NOT_A_CONSTANT")


def test_reader_evaluates_only_whitelisted_arithmetic():
    assert rsc.evaluate("5.0 * 0.5") == 2.5
    assert rsc.evaluate("u16::MAX") == 0xFFFF
    assert rsc.evaluate("0.1_f32") == pytest.approx(0.1)
    with pytest.raises(ValueError):
        rsc.evaluate("2 ** 3")
    with pytest.raises(ValueError):
        rsc.evaluate("FOO")


def test_schism_secession_modifier_matches_religion():
    from chronicler import religion

    assert rsc.const("politics.rs", "SCHISM_SECESSION_MODIFIER") == religion.SCHISM_SECESSION_MODIFIER


def test_tithe_and_supply_floor_constants_match_python():
    from chronicler import economy, factions, grain_reserves

    assert rsc.const("economy.rs", "TITHE_RATE") == pytest.approx(factions.TITHE_RATE)
    # Python keeps the gate as a local in compute_economy until CON-5b hoists it.
    assert rsc.const("economy.rs", "TITHE_FOOD_GATE") == 0.5
    supply_floor = rsc.const("economy.rs", "SUPPLY_FLOOR")
    assert supply_floor == economy._SUPPLY_FLOOR == grain_reserves.PRICE_SUPPLY_FLOOR
    assert (
        rsc.const("merchant.rs", "FOOD_PRICE_SUFFICIENCY_FLOOR")
        == rsc.const("merchant.rs", "PRICE_SUPPLY_FLOOR")
        == supply_floor
        == 0.1
    )


def test_economy_config_defaults_match_the_values_python_pushes():
    from chronicler.agent_bridge import configure_economy_runtime
    from chronicler.models import WorldState

    class RecordingSimulator:
        def __init__(self):
            self.calls = []

        def set_economy_config(self, **kwargs):
            self.calls.append(kwargs)

    stub = RecordingSimulator()
    world = WorldState(name="parity", seed=0)
    assert not world.tuning_overrides
    configure_economy_runtime(stub, world)

    assert len(stub.calls) == 1
    pushed = stub.calls[0]
    rust = rsc.default_fields("economy.rs", "impl Default for EconomyConfig")
    assert set(pushed) == set(rust)
    for field, rust_value in rust.items():
        assert pushed[field] == pytest.approx(rust_value), field


def test_native_purposes_match_wealth_transfer():
    from chronicler import money

    assert rsc.array("wealth_transfer.rs", "PURPOSES") == list(money.NATIVE_PURPOSES)
