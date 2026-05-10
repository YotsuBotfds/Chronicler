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


def test_culture_import_does_not_require_agent_bridge_or_native_extension(monkeypatch):
    import sys

    sys.modules.pop("chronicler.culture", None)
    sys.modules.pop("chronicler.agent_bridge", None)
    for module_name in list(sys.modules):
        if module_name == "chronicler_agents" or module_name.startswith("chronicler_agents."):
            monkeypatch.delitem(sys.modules, module_name, raising=False)

    import chronicler.culture  # noqa: F401

    assert "chronicler.agent_bridge" not in sys.modules
    assert "chronicler_agents" not in sys.modules
    assert "chronicler_agents.chronicler_agents" not in sys.modules
