"""Regression tests for running pure-Python paths without the Rust extension."""

import builtins
import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest


class _BlockChroniclerAgentsImport:
    def __init__(self, monkeypatch):
        self._orig_import = builtins.__import__
        self._monkeypatch = monkeypatch

    def __enter__(self):
        for module_name in list(sys.modules):
            if module_name == "chronicler_agents" or module_name.startswith("chronicler_agents."):
                self._monkeypatch.delitem(sys.modules, module_name, raising=False)

        def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
            if name == "chronicler_agents":
                raise ImportError("blocked chronicler_agents for no-native regression test")
            return self._orig_import(name, globals, locals, fromlist, level)

        self._monkeypatch.setattr(builtins, "__import__", guarded_import)
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_agent_bridge_helpers_import_without_chronicler_agents(monkeypatch):
    sys.modules.pop("chronicler.agent_bridge", None)
    with _BlockChroniclerAgentsImport(monkeypatch):
        import chronicler.agent_bridge as agent_bridge

    assert callable(agent_bridge.build_region_postpass_patch_batch)
    assert "chronicler_agents" not in sys.modules


def test_agent_bridge_constructor_reports_missing_native_extension(monkeypatch):
    sys.modules.pop("chronicler.agent_bridge", None)

    with _BlockChroniclerAgentsImport(monkeypatch):
        from chronicler.agent_bridge import AgentBridge
        from chronicler.models import WorldState

        world = WorldState(name="T", seed=1, regions=[], civilizations=[])
        with pytest.raises(RuntimeError, match="chronicler_agents"):
            AgentBridge(world)


def test_pure_python_tests_do_not_poison_native_extension_imports(monkeypatch):
    test_path = Path(__file__).with_name("test_religion.py")
    sys.modules.pop("chronicler.religion", None)

    with _BlockChroniclerAgentsImport(monkeypatch):
        spec = importlib.util.spec_from_file_location("_chronicler_test_religion_probe", test_path)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)

    assert "chronicler_agents" not in sys.modules


def test_pure_python_test_modules_do_not_install_global_native_stubs():
    offenders = []
    allowed = {"test_native_extension_fallbacks.py", "test_agent_bridge_legacy_migration.py"}
    for test_path in Path(__file__).parent.glob("test_*.py"):
        if test_path.name in allowed:
            continue
        text = test_path.read_text(encoding="utf-8")
        if 'sys.modules["chronicler_agents"] =' in text or 'setdefault("chronicler_agents"' in text:
            offenders.append(test_path.name)

    assert offenders == []


def test_agent_bridge_constructor_rejects_fake_native_extension(monkeypatch):
    fake_module = MagicMock()
    fake_module.AgentSimulator = MagicMock()
    monkeypatch.setitem(sys.modules, "chronicler_agents", fake_module)
    sys.modules.pop("chronicler.agent_bridge", None)

    from chronicler.agent_bridge import AgentBridge
    from chronicler.models import WorldState

    world = WorldState(name="T", seed=1, regions=[], civilizations=[])
    with pytest.raises(RuntimeError, match="not a real native extension"):
        AgentBridge(world)


def test_off_mode_runtime_factories_ignore_magicmock_chronicler_agents(monkeypatch):
    monkeypatch.setitem(sys.modules, "chronicler_agents", MagicMock())

    from chronicler.main import _create_ecology_runtime, _create_politics_runtime
    from chronicler.world_gen import generate_world

    world = generate_world(seed=42, num_regions=4, num_civs=2)

    assert _create_ecology_runtime(world) is None
    assert _create_politics_runtime(world) is None
