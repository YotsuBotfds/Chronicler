"""Synthetic wrapper layouts only; no dependency import/metadata proof."""
from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
import sys
import types

import pytest


ROOT = Path(__file__).resolve().parents[1]


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


codec = sys.modules.get("forkserver_template_codec") or _load("forkserver_template_codec", ROOT / "scripts/forkserver_template_codec.py")
lazy = _load("forkserver_lazy_metadata", ROOT / "scripts/forkserver_lazy_metadata.py")


@pytest.fixture
def wrappers(tmp_path, monkeypatch):
    calls = []

    class MockCoreSchema:
        __slots__ = ("_error_message", "_code", "_attempt_rebuild", "_built_memo")

        def __len__(self):
            calls.append("mapping length")
            raise AssertionError("mapping rebuilt")

        def __iter__(self):
            calls.append("mapping iteration")
            raise AssertionError("mapping rebuilt")

        def __getitem__(self, key):
            calls.append("mapping item")
            raise AssertionError("mapping rebuilt")

        def rebuild(self):
            calls.append("mapping rebuild")
            raise AssertionError("mapping rebuilt")

    class MockValSer:
        __slots__ = ("_error_message", "_code", "_val_or_ser", "_attempt_rebuild")

        def __getattribute__(self, name):
            calls.append("attribute " + name)
            raise AssertionError("lazy attribute rebuilt")

    class LazyClassAttribute:
        @property
        def value(self):
            calls.append("cached property")
            raise AssertionError("cache computed")

        def __get__(self, instance, owner):
            calls.append("descriptor access")
            raise AssertionError("descriptor computed")

    classes = {"MockCoreSchema": MockCoreSchema, "MockValSer": MockValSer, "LazyClassAttribute": LazyClassAttribute}
    modules = {}
    hashes = {}
    for index, name in enumerate(lazy._SOURCES):
        path = tmp_path / f"fixture-dependency-{index}.py"
        path.write_text(f"# pinned synthetic unit-test module {name}\n")
        module = types.ModuleType(name)
        module.__file__ = str(path)
        modules[name] = module
        hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()
        monkeypatch.setitem(sys.modules, name, module)
    for name, cls in classes.items():
        module_name = lazy._LAYOUTS[name][0]
        cls.__module__ = module_name
        cls.__qualname__ = name
        setattr(modules[module_name], name, cls)
    monkeypatch.setattr(lazy, "_SOURCES", hashes)
    bindings = lazy.bind_modules(modules)

    def callback():
        calls.append("callback")
        raise AssertionError("rebuild callback invoked")

    core, val, attr = MockCoreSchema(), MockValSer(), LazyClassAttribute()
    for obj in (core, val):
        object.__setattr__(obj, "_error_message", "not yet defined")
        object.__setattr__(obj, "_code", "class-not-fully-defined")
        object.__setattr__(obj, "_attempt_rebuild", callback)
    object.__setattr__(core, "_built_memo", None)
    object.__setattr__(val, "_val_or_ser", object)
    attr.name, attr.get_value = "__signature__", callback
    return types.SimpleNamespace(classes=classes, modules=modules, bindings=bindings,
                                 core=core, val=val, attr=attr, calls=calls)


def test_mock_owned_cells_preserve_original_references_without_running_lazy_methods(wrappers):
    for obj, expected in ((wrappers.core, ("_error_message", "_code", "_attempt_rebuild", "_built_memo")),
                          (wrappers.val, ("_error_message", "_code", "_val_or_ser", "_attempt_rebuild"))):
        view = lazy.storage_view(obj, wrappers.bindings)
        assert view.original is obj and view.cls is type(obj)
        assert tuple(name for name, _ in view.cells) == expected
        for name, value in view.cells:
            assert value is object.__getattribute__(obj, name)
    assert wrappers.calls == []


def test_mock_memo_none_and_live_aliases_are_not_normalized_or_copied(wrappers):
    assert dict(lazy.storage_view(wrappers.core, wrappers.bindings).cells)["_built_memo"] is None
    shared = {"alias": []}
    object.__setattr__(wrappers.core, "_built_memo", shared)
    object.__setattr__(wrappers.val, "_attempt_rebuild", shared)
    one = dict(lazy.storage_view(wrappers.core, wrappers.bindings).cells)
    two = dict(lazy.storage_view(wrappers.val, wrappers.bindings).cells)
    assert one["_built_memo"] is two["_attempt_rebuild"] is shared
    assert wrappers.calls == []


def test_lazy_dict_rule_observes_absent_and_present_cache_without_accessing_property(wrappers):
    view = lazy.storage_view(wrappers.attr, wrappers.bindings)
    namespace = object.__getattribute__(wrappers.attr, "__dict__")
    assert view.cells == (("__dict__", namespace),)
    assert "value" not in namespace
    rule = lazy.lazy_attribute_rule(wrappers.bindings)
    before = codec.Encoder((rule,)).encode({"lazy": wrappers.attr})
    namespace["value"] = {"already_cached": [1]}
    after = codec.Encoder((rule,)).encode({"lazy": wrappers.attr})
    assert before != after
    assert view.cells[0][1] is namespace  # A live view, not a historical witness.
    assert wrappers.calls == []


def test_dependency_method_binding_changes_are_visible_even_when_source_file_is_unchanged(wrappers):
    roots = lazy.dependency_class_roots(wrappers.bindings)
    before = codec.Encoder().encode(roots)
    wrappers.classes["MockCoreSchema"].rebuild = lambda self: None
    changed = lazy.dependency_class_roots(wrappers.bindings)
    assert codec.Encoder().encode(changed) != before
    assert wrappers.calls == []


@pytest.mark.parametrize("changed", ["source", "file", "class", "loaded-module"])
def test_dependency_source_class_and_actual_loaded_binding_are_rechecked(wrappers, monkeypatch, tmp_path, changed):
    module = wrappers.modules["pydantic._internal._mock_val_ser"]
    if changed == "source":
        Path(module.__file__).write_text("# changed after binding\n")
    elif changed == "file":
        other = tmp_path / "other.py"
        other.write_bytes(Path(module.__file__).read_bytes())
        module.__file__ = str(other)
    elif changed == "class":
        module.MockCoreSchema = type("Other", (), {})
    else:
        monkeypatch.setitem(sys.modules, module.__name__, types.ModuleType(module.__name__))
    with pytest.raises(codec.FingerprintError):
        lazy.storage_view(wrappers.core, wrappers.bindings)
    assert wrappers.calls == []


@pytest.mark.parametrize("changed", ["deleted", "remapped", "uninitialized", "declaration"])
def test_original_mock_descriptors_and_complete_initialized_slots_are_required(wrappers, changed):
    cls = type(wrappers.core)
    if changed == "deleted":
        del cls._built_memo
    elif changed == "remapped":
        cls._built_memo = cls._code
    elif changed == "uninitialized":
        object.__delattr__(wrappers.core, "_built_memo")
    else:
        cls.__slots__ = ("_error_message", "_code", "_attempt_rebuild")
    with pytest.raises(codec.FingerprintError):
        lazy.storage_view(wrappers.core, wrappers.bindings)
    assert wrappers.calls == []


def test_subclasses_and_compiled_like_objects_remain_unsupported(wrappers):
    class Child(type(wrappers.core)):
        pass

    class CompiledLike:
        def __repr__(self):
            raise AssertionError("compiled repr invoked")

    for obj in (Child(), CompiledLike(), object()):
        with pytest.raises(codec.FingerprintError, match="unsupported lazy/compiled"):
            lazy.storage_view(obj, wrappers.bindings)
    with pytest.raises(codec.FingerprintError, match="unsupported"):
        codec.Encoder().encode({"mock": wrappers.core})
    assert wrappers.calls == []


def test_partial_duplicate_or_wrong_module_bindings_never_look_complete(wrappers):
    with pytest.raises(codec.FingerprintError, match="module set"):
        lazy.bind_modules({})
    with pytest.raises(codec.FingerprintError, match="complete"):
        lazy.storage_view(wrappers.core, wrappers.bindings[:1])
    duplicate = (wrappers.bindings[0],) * 3
    with pytest.raises(codec.FingerprintError, match="complete"):
        lazy.lazy_attribute_rule(duplicate)
    assert wrappers.calls == []
