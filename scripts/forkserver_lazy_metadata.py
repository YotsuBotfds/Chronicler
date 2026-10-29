"""Source-pinned views of three lazy Pydantic metadata storage layouts.

No Pydantic imports or lazy/schema calls; no mock/compiled codec admission.
Views retain live original references; they are not historical witnesses until
a separately qualified caller encodes them synchronously with alias tracking.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import sys
import types

from forkserver_template_codec import FingerprintError, StorageRule, _class_dict, _class_name, _is_class


_SOURCES = {
    "pydantic._internal._mock_val_ser": "56a6ec20e81e9e841088cf8db05325f6e63b8ad8094ae3cda5754a698ec0d293",
    "pydantic._internal._utils": "23de5935186553e9bc579a6a0594ab3f6b0c20d63e8b0e5a6dc3d451185a0678",
}
_LAYOUTS = {
    "MockCoreSchema": ("pydantic._internal._mock_val_ser", ("_error_message", "_code", "_attempt_rebuild", "_built_memo")),
    "MockValSer": ("pydantic._internal._mock_val_ser", ("_error_message", "_code", "_val_or_ser", "_attempt_rebuild")),
    "LazyClassAttribute": ("pydantic._internal._utils", None),
}


@dataclass(frozen=True, slots=True)
class _Binding:
    kind: str
    module: types.ModuleType
    cls: type
    path: str


@dataclass(frozen=True, slots=True)
class StorageView:
    """Owned-cell references only; does not certify inherited/compiled state."""

    kind: str
    original: object
    cls: type
    cells: tuple[tuple[str, object], ...]


def _namespace(module):
    if type(module) is not types.ModuleType:
        raise FingerprintError("dependency binding requires an exact module")
    namespace = types.ModuleType.__getattribute__(module, "__dict__")
    if len(namespace) > 20000 or any(type(key) is not str or len(key) > 4096 for key in namespace):
        raise FingerprintError("dependency module namespace is invalid")
    return namespace


def _source(module, expected_name):
    namespace = _namespace(module)
    if (type(sys.modules) is not dict or len(sys.modules) > 20000
            or any(type(name) is not str for name in sys.modules)):
        raise FingerprintError("loaded module registry is invalid")
    if sys.modules.get(expected_name) is not module:
        raise FingerprintError("dependency binding is not the actually loaded module")
    if type(namespace.get("__name__")) is not str or namespace["__name__"] != expected_name:
        raise FingerprintError("dependency module name differs")
    filename = namespace.get("__file__")
    if type(filename) is not str or not filename or len(filename) > 4096:
        raise FingerprintError("dependency source path is invalid")
    path = Path(filename)
    if path.suffix != ".py" or path.is_symlink() or not path.is_file():
        raise FingerprintError("dependency source must be a regular Python file")
    with path.open("rb") as stream:
        raw = stream.read(2 * 1024 * 1024 + 1)
    if len(raw) > 2 * 1024 * 1024 or hashlib.sha256(raw).hexdigest() != _SOURCES[expected_name]:
        raise FingerprintError("dependency source hash differs from reviewed layout")
    return namespace, filename


def _owned_descriptor(cls, name, expected_type):
    namespace = _class_dict(cls)
    descriptor = namespace.get(name)
    if (type(descriptor) is not expected_type
            or type(object.__getattribute__(descriptor, "__name__")) is not str
            or object.__getattribute__(descriptor, "__name__") != name
            or object.__getattribute__(descriptor, "__objclass__") is not cls):
        raise FingerprintError("dependency storage descriptor is replaced or foreign")
    return descriptor


def _check_binding(binding):
    if type(binding) is not _Binding or type(binding.kind) is not str or binding.kind not in _LAYOUTS:
        raise FingerprintError("unknown lazy dependency binding")
    module_name, slots = _LAYOUTS[binding.kind]
    namespace, filename = _source(binding.module, module_name)
    if filename != binding.path or namespace.get(binding.kind) is not binding.cls or not _is_class(binding.cls):
        raise FingerprintError("dependency class/source binding changed")
    identity = _class_name(binding.cls)
    if identity[:2] != [module_name, binding.kind]:
        raise FingerprintError("dependency class identity differs")
    class_namespace = _class_dict(binding.cls)
    if slots is None:
        if "__slots__" in class_namespace:
            raise FingerprintError("lazy descriptor acquired an unreviewed slot layout")
        _owned_descriptor(binding.cls, "__dict__", types.GetSetDescriptorType)
    else:
        declared = class_namespace.get("__slots__")
        if (type(declared) is not tuple or len(declared) != len(slots)
                or any(type(name) is not str for name in declared) or declared != slots):
            raise FingerprintError("mock metadata slot declaration differs")
        member_names = {name for name, value in class_namespace.items() if type(value) is types.MemberDescriptorType}
        if member_names != set(slots):
            raise FingerprintError("mock metadata member-cell coverage differs")
        for name in slots:
            _owned_descriptor(binding.cls, name, types.MemberDescriptorType)
    return slots


def bind_modules(modules: dict[str, types.ModuleType]) -> tuple[_Binding, ...]:
    """Bind only already-loaded exact modules; import/build nothing."""
    if (type(modules) is not dict or len(modules) != len(_SOURCES)
            or any(type(name) is not str for name in modules) or set(modules) != set(_SOURCES)):
        raise FingerprintError("exact reviewed dependency module set is required")
    bindings = []
    for kind, (module_name, _) in _LAYOUTS.items():
        module = modules[module_name]
        namespace, filename = _source(module, module_name)
        cls = namespace.get(kind)
        if not _is_class(cls):
            raise FingerprintError("dependency type is unavailable")
        binding = _Binding(kind, module, cls, filename)
        _check_binding(binding)
        bindings.append(binding)
    return tuple(bindings)


def _complete_bindings(bindings):
    if (type(bindings) is not tuple or len(bindings) != len(_LAYOUTS)
            or any(type(binding) is not _Binding for binding in bindings)
            or any(type(binding.kind) is not str for binding in bindings)
            or {binding.kind for binding in bindings} != set(_LAYOUTS)):
        raise FingerprintError("complete reviewed dependency bindings are required")
    return bindings


def storage_view(value, bindings: tuple[_Binding, ...]) -> StorageView:
    """Read declared own cells without touching a lazy mapping or descriptor."""
    bindings = _complete_bindings(bindings)
    selected = [binding for binding in bindings if type(value) is binding.cls]
    if len(selected) != 1:
        raise FingerprintError("unsupported lazy/compiled dependency type")
    binding = selected[0]
    slots = _check_binding(binding)
    if slots is None:
        descriptor = _owned_descriptor(binding.cls, "__dict__", types.GetSetDescriptorType)
        namespace = types.GetSetDescriptorType.__get__(descriptor, value, binding.cls)
        if (type(namespace) is not dict or len(namespace) > 20000
                or any(type(name) is not str or len(name) > 4096 for name in namespace)):
            raise FingerprintError("lazy descriptor dictionary is invalid")
        cells = (("__dict__", namespace),)
    else:
        cells = []
        for name in slots:
            descriptor = _owned_descriptor(binding.cls, name, types.MemberDescriptorType)
            try:
                item = types.MemberDescriptorType.__get__(descriptor, value, binding.cls)
            except AttributeError as exc:
                raise FingerprintError("mock metadata has an uninitialized cell") from exc
            cells.append((name, item))
        cells = tuple(cells)
    _check_binding(binding)
    return StorageView(binding.kind, value, binding.cls, cells)


def lazy_attribute_rule(bindings: tuple[_Binding, ...]) -> StorageRule:
    """One layout only; pair with class roots in a future guard, not standalone."""
    bindings = _complete_bindings(bindings)
    selected = [binding for binding in bindings if binding.kind == "LazyClassAttribute"]
    if len(selected) != 1:
        raise FingerprintError("one lazy descriptor binding is required")
    binding = selected[0]
    _check_binding(binding)
    return StorageRule(binding.cls, dict_storage=True)


def dependency_class_roots(bindings: tuple[_Binding, ...]) -> dict:
    """Include wrapper method bindings; file hashes do not expose monkeypatches.

    These are shallow projections retaining original nested references, to be
    encoded immediately by the caller. Unsupported contents still refuse.
    """
    bindings = _complete_bindings(bindings)
    roots = {}
    total = 0
    for binding in bindings:
        _check_binding(binding)
        namespace = _class_dict(binding.cls)
        total += len(namespace)
        if total > 20000:
            raise FingerprintError("dependency class projection limit exceeded")
        roots[binding.kind] = dict(namespace)
    return roots
