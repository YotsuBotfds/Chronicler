"""Regression tests for shared Python/Rust FFI constants."""


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
