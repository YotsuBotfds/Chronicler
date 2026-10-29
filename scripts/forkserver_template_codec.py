"""Strict same-template metadata encoding; no simulation imports or repr fallback.

This is a foundation for a future preloader, not an activated fork guard.
Callers must explicitly register exact storage types. Unsupported values refuse.
Class identities refer to one process and its unchanged fork descendants; this
is not a cross-source or independent-interpreter equivalence codec.
"""
from __future__ import annotations

from dataclasses import dataclass
import functools
import json
import re
import struct
import types


_MODULE_NAME = re.compile(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*\Z", re.ASCII)


class FingerprintError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class StorageRule:
    cls: type
    dict_storage: bool = False
    slots: tuple[str, ...] = ()
    tuple_contents: bool = False

    def __post_init__(self):
        if not _is_class(self.cls):
            raise FingerprintError("storage rule requires an exact class")
        if type(self.dict_storage) is not bool or type(self.tuple_contents) is not bool:
            raise FingerprintError("storage flags must be boolean")
        if (type(self.slots) is not tuple or len(self.slots) > 128
                or any(type(name) is not str or not name or len(name) > 256
                       or name in {"__dict__", "__weakref__"} for name in self.slots)
                or len(set(self.slots)) != len(self.slots)):
            raise FingerprintError("storage slots must be unique explicit names")
        if not (self.dict_storage or self.slots or self.tuple_contents):
            raise FingerprintError("empty storage rule cannot hide unknown object state")


def _class_dict(cls):
    namespace = types.GetSetDescriptorType.__get__(type.__dict__["__dict__"], cls, type(cls))
    # type() can accept non-string keys in its input dictionary. Check the
    # proven class view before any string lookup could invoke such a key's eq.
    if len(namespace) > 20000 or any(type(key) is not str or len(key) > 4096 for key in namespace):
        raise FingerprintError("class namespace names/count are invalid")
    return namespace


def _class_mro(cls):
    mro = types.GetSetDescriptorType.__get__(type.__dict__["__mro__"], cls, type(cls))
    if len(mro) > 64:
        raise FingerprintError("class MRO length limit exceeded")
    return mro


def _is_class(value):
    return any(base is type for base in _class_mro(type(value)))


def _one_of(cls, candidates):
    return any(cls is candidate for candidate in candidates)


def _class_name(cls):
    # Invoke only the known builtin type descriptor, bypassing metaclass hooks.
    _class_dict(cls)
    module = types.GetSetDescriptorType.__get__(type.__dict__["__module__"], cls, type(cls))
    name = types.GetSetDescriptorType.__get__(type.__dict__["__qualname__"], cls, type(cls))
    if type(module) is not str or type(name) is not str or len(module) > 4096 or len(name) > 4096:
        raise FingerprintError("class identity has invalid metadata")
    return [module, name, hex(id(cls))]


def _storage_descriptor(cls, name, descriptor_type):
    for base in _class_mro(cls):
        namespace = _class_dict(base)
        if name in namespace:
            descriptor = namespace[name]
            if type(descriptor) is not descriptor_type:
                raise FingerprintError("storage attribute is not a verified builtin descriptor")
            return descriptor
    raise FingerprintError("declared storage descriptor is missing")


def _validate_rule_layout(rule):
    slots = set()
    has_dict = False
    mro = _class_mro(rule.cls)
    if any(entry is base for entry in mro for base in (list, dict, set, frozenset, bytes, str, int, float)):
        raise FingerprintError("unmodelled builtin subtype storage requires a dedicated codec")
    for base in mro:
        namespace = _class_dict(base)
        declared = namespace.get("__slots__", ())
        if type(declared) is str:
            declared = (declared,)
        if type(declared) is not tuple and type(declared) is not list:
            raise FingerprintError("slot declarations require a reviewed literal layout")
        if len(declared) > 128 or any(type(name) is not str or len(name) > 256 for name in declared):
            raise FingerprintError("slot declarations exceed literal layout bounds")
        base_name = types.GetSetDescriptorType.__get__(type.__dict__["__name__"], base, type(base))
        if type(base_name) is not str or len(base_name) > 4096:
            raise FingerprintError("class storage name requires a bounded exact string")
        expected_members = set()
        for name in declared:
            if name in {"__dict__", "__weakref__"}:
                continue
            if name.startswith("__") and not name.endswith("__"):
                name = "_" + base_name.lstrip("_") + name
            expected_members.add(name)
        actual_members = set()
        for name, descriptor in namespace.items():
            if type(descriptor) is types.MemberDescriptorType:
                if (object.__getattribute__(descriptor, "__name__") != name
                        or object.__getattribute__(descriptor, "__objclass__") is not base):
                    raise FingerprintError("remapped or foreign slot descriptor is not admitted")
                actual_members.add(name)
                if name in slots:
                    raise FingerprintError("shadowed slot storage requires a dedicated adapter")
                slots.add(name)
        if actual_members != expected_members:
            raise FingerprintError("declared slot cells must retain every original descriptor")
        if "__dict__" in namespace:
            _storage_descriptor(rule.cls, "__dict__", types.GetSetDescriptorType)
            has_dict = True
    non_object_bases = [base for base in mro if base is not rule.cls and base is not object]
    if non_object_bases and not (rule.tuple_contents and len(non_object_bases) == 1 and non_object_bases[0] is tuple):
        raise FingerprintError("inherited storage base requires a dedicated reviewed adapter")
    if (slots != set(rule.slots) or has_dict != rule.dict_storage
            or any(base is tuple for base in mro) != rule.tuple_contents):
        raise FingerprintError("storage rule must cover the complete declared layout")


class Encoder:
    """Encode bounded primitive graphs and explicit type storage without hooks."""

    def __init__(self, rules=(), *, max_nodes=100000, max_depth=80,
                 max_container=20000, max_scalar_bytes=1024 * 1024, max_bytes=8 * 1024 * 1024):
        self.rules = {}
        if type(rules) is not tuple or len(rules) > 512:
            raise FingerprintError("storage rules require a bounded tuple")
        for rule in rules:
            if type(rule) is not StorageRule or id(rule.cls) in self.rules:
                raise FingerprintError("storage rules must have unique exact classes")
            _validate_rule_layout(rule)
            self.rules[id(rule.cls)] = rule
        limits = (max_nodes, max_depth, max_container, max_scalar_bytes, max_bytes)
        if any(type(value) is not int or value <= 0 for value in limits):
            raise FingerprintError("codec limits must be positive integers")
        self.max_nodes, self.max_depth, self.max_container, self.max_scalar_bytes, self.max_bytes = limits
        self._used = False
        self._seen = {}
        self._nodes = []
        self._reserved = 0

    def _charge(self, count):
        self._reserved += count
        if self._reserved > self.max_bytes:
            raise FingerprintError("metadata byte reservation limit exceeded")

    def _string(self, value):
        if len(value) > self.max_scalar_bytes:
            raise FingerprintError("metadata scalar byte limit exceeded")
        raw = value.encode("utf-8")
        if len(raw) > self.max_scalar_bytes:
            raise FingerprintError("metadata scalar byte limit exceeded")
        self._charge(len(raw) + 64)
        return value

    def _items(self, value, depth):
        if len(value) > self.max_container:
            raise FingerprintError("metadata container limit exceeded")
        return [self._value(item, depth + 1) for item in value]

    def _class_token(self, cls):
        return [self._string(part) for part in _class_name(cls)]

    def _value(self, value, depth):
        if depth > self.max_depth:
            raise FingerprintError("metadata depth limit exceeded")
        cls = type(value)
        if value is None:
            self._charge(16)
            return ["none"]
        if cls is bool:
            self._charge(16)
            return ["bool", value]
        if cls is int:
            if value.bit_length() > 16384:
                raise FingerprintError("metadata integer limit exceeded")
            return ["int", self._string(str(value))]
        if cls is float:
            self._charge(48)
            return ["float64", struct.pack("!d", value).hex()]
        if cls is str:
            return ["str", self._string(value)]
        if cls is bytes:
            if len(value) > self.max_scalar_bytes:
                raise FingerprintError("metadata scalar byte limit exceeded")
            self._charge(2 * len(value) + 64)
            return ["bytes", value.hex()]
        if value is Ellipsis or value is NotImplemented:
            self._charge(32)
            return ["singleton", "ellipsis" if value is Ellipsis else "not-implemented"]
        if _is_class(value):
            self._charge(192)
            return ["class", self._class_token(value)]
        if cls is types.ModuleType:
            namespace = types.ModuleType.__getattribute__(value, "__dict__")
            if len(namespace) > 20000 or any(type(key) is not str or len(key) > 4096 for key in namespace):
                raise FingerprintError("module namespace names/count are invalid")
            if type(namespace.get("__name__")) is not str:
                raise FingerprintError("module identity has a non-string name")
            return ["module", self._string(namespace["__name__"]), hex(id(value))]

        identity = id(value)
        if identity in self._seen:
            self._charge(24)
            return ["ref", self._seen[identity]]
        if len(self._nodes) >= self.max_nodes:
            raise FingerprintError("metadata node limit exceeded")
        index = len(self._nodes)
        self._seen[identity] = index
        self._nodes.append(None)
        self._charge(96)
        node = ["type", self._class_token(cls)]

        if cls is dict:
            if len(value) > self.max_container:
                raise FingerprintError("metadata container limit exceeded")
            node += [[self._value(key, depth + 1), self._value(item, depth + 1)] for key, item in value.items()]
        elif _one_of(cls, (list, tuple, set, frozenset)):
            # Same-template order is retained even for sets: no normalization.
            node += self._items(value, depth)
        elif cls is types.FunctionType:
            node += [self._value(value.__code__, depth + 1)]
            for name in ("__defaults__", "__kwdefaults__", "__annotations__", "__dict__"):
                node.append([name, self._value(object.__getattribute__(value, name), depth + 1)])
            cells = []
            for cell in value.__closure__ or ():
                try:
                    contents = cell.cell_contents
                except ValueError:
                    cells.append(["empty-cell"])
                else:
                    cells.append(self._value(contents, depth + 1))
            node.append(["closure", cells])
        elif cls is types.MethodType:
            node += [self._value(value.__func__, depth + 1), self._value(value.__self__, depth + 1)]
        elif cls is types.BuiltinFunctionType:
            node += [self._value(object.__getattribute__(value, name), depth + 1)
                     for name in ("__module__", "__name__", "__self__")]
        elif _one_of(cls, (types.WrapperDescriptorType, types.MethodDescriptorType,
                          types.GetSetDescriptorType, types.MemberDescriptorType)):
            node += [self._value(object.__getattribute__(value, name), depth + 1)
                     for name in ("__objclass__", "__name__")]
        elif _one_of(cls, (classmethod, staticmethod)):
            node += [self._value(object.__getattribute__(value, "__func__"), depth + 1),
                     self._value(object.__getattribute__(value, "__dict__"), depth + 1)]
        elif cls is property:
            node += [self._value(object.__getattribute__(value, name), depth + 1) for name in ("fget", "fset", "fdel", "__doc__")]
        elif cls is functools.partial:
            node += [self._value(object.__getattribute__(value, name), depth + 1) for name in ("func", "args", "keywords", "__dict__")]
        elif cls is types.CodeType:
            # Do not marshal first: a large co_consts value can allocate an
            # unbounded serialized blob before a later size check. Known code
            # fields enter the same bounded primitive graph as every value.
            if types.CodeType.__sizeof__(value) > self.max_scalar_bytes + 4096:
                raise FingerprintError("code object storage exceeds scalar byte limit")
            for name in ("co_argcount", "co_posonlyargcount", "co_kwonlyargcount",
                         "co_nlocals", "co_stacksize", "co_flags", "co_code", "co_consts",
                         "co_names", "co_varnames", "co_filename", "co_name", "co_qualname",
                         "co_firstlineno", "co_linetable", "co_exceptiontable", "co_freevars", "co_cellvars"):
                node.append([name, self._value(object.__getattribute__(value, name), depth + 1)])
        elif id(cls) in self.rules:
            rule = self.rules[id(cls)]
            if rule.dict_storage:
                descriptor = _storage_descriptor(cls, "__dict__", types.GetSetDescriptorType)
                namespace = types.GetSetDescriptorType.__get__(descriptor, value, cls)
                if type(namespace) is not dict:
                    raise FingerprintError("object dictionary storage is not a plain dictionary")
                node.append(["dict", self._value(namespace, depth + 1)])
            for name in rule.slots:
                descriptor = _storage_descriptor(cls, name, types.MemberDescriptorType)
                try:
                    item = types.MemberDescriptorType.__get__(descriptor, value, cls)
                except AttributeError:
                    encoded = ["uninitialized-slot"]
                else:
                    encoded = self._value(item, depth + 1)
                node.append([self._string(name), encoded])
            if rule.tuple_contents:
                if not any(base is tuple for base in _class_mro(cls)):
                    raise FingerprintError("tuple storage rule does not describe a tuple subtype")
                if tuple.__len__(value) > self.max_container:
                    raise FingerprintError("metadata container limit exceeded")
                node.append(["tuple", self._items(tuple.__getitem__(value, slice(None)), depth)])
        else:
            raise FingerprintError("unsupported metadata storage type: " + ".".join(_class_name(cls)[:2]))
        self._nodes[index] = node
        return ["ref", index]

    def encode(self, roots: dict) -> bytes:
        if self._used:
            raise FingerprintError("a codec instance is single-use")
        self._used = True
        if type(roots) is not dict or any(type(name) is not str for name in roots):
            raise FingerprintError("metadata roots must be a named plain dictionary")
        root = self._value(roots, 0)
        raw = json.dumps({"kind": "same-template-metadata-v1", "root": root, "nodes": self._nodes},
                         ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
        if len(raw) > self.max_bytes:
            raise FingerprintError("encoded metadata byte limit exceeded")
        return raw


def module_roots(modules: dict[str, types.ModuleType]) -> dict:
    """Capture registered namespaces and locally declared class dictionaries."""
    if type(modules) is not dict or not modules:
        raise FingerprintError("registered modules must be a nonempty dictionary")
    if (len(modules) > 64 or any(type(name) is not str or len(name) > 256
                               or _MODULE_NAME.fullmatch(name) is None for name in modules)):
        raise FingerprintError("module registry names/count are invalid")
    roots = {}
    projected_bindings = 0
    for name, module in sorted(modules.items()):
        if type(name) is not str or type(module) is not types.ModuleType:
            raise FingerprintError("registered modules require exact module objects")
        namespace = types.ModuleType.__getattribute__(module, "__dict__")
        if len(namespace) > 20000 or any(type(key) is not str or len(key) > 4096 for key in namespace):
            raise FingerprintError("module namespace names/count are invalid")
        if type(namespace.get("__name__")) is not str or namespace["__name__"] != name:
            raise FingerprintError("module registry name differs from actual namespace")
        projected_bindings += len(namespace)
        if projected_bindings > 20000:
            raise FingerprintError("module/class projection binding limit exceeded")
        roots[name] = {key: value for key, value in namespace.items() if key != "__builtins__"}
        for key, value in sorted(namespace.items()):
            if _is_class(value) and _class_name(value)[0] == name:
                # Only this builtin type descriptor establishes that the
                # proxy wraps a real class dict. Generic mapping proxies may
                # wrap arbitrary Python mappings and are refused by Encoder.
                class_namespace = _class_dict(value)
                projected_bindings += len(class_namespace)
                if projected_bindings > 20000:
                    raise FingerprintError("module/class projection binding limit exceeded")
                roots[name + "::" + key] = dict(class_namespace)
    return roots
