"""Generic metadata graph tests; no dependency adapters, preloader or forks."""
from __future__ import annotations

import functools
from collections import deque
import importlib.util
import json
import marshal
from pathlib import Path
import struct
import sys
import types
import warnings

import pytest


PATH = Path(__file__).resolve().parents[1] / "scripts" / "forkserver_template_codec.py"
SPEC = importlib.util.spec_from_file_location("forkserver_template_codec", PATH)
codec = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = codec
SPEC.loader.exec_module(codec)


def encode(value, **kwargs):
    return codec.Encoder(**kwargs).encode({"root": value})


def test_primitives_preserve_types_float_bits_signed_zero_and_nonfinite_payloads():
    assert encode(True) != encode(1) != encode(1.0)
    assert encode(0.0) != encode(-0.0)
    nan1 = struct.unpack("!d", bytes.fromhex("7ff8000000000001"))[0]
    nan2 = struct.unpack("!d", bytes.fromhex("7ff8000000000002"))[0]
    assert encode(nan1) != encode(nan2)
    assert encode(b"data") != encode("data")
    assert encode([None, Ellipsis, NotImplemented, float("inf")])
    json.loads(encode(float("nan")))


def test_aliases_cycles_container_type_and_dictionary_order_are_observed():
    shared = []
    assert encode([shared, shared]) != encode([[], []])
    shared.append(shared)
    assert encode(shared) == encode(shared)
    assert encode([1, 2]) != encode((1, 2))
    assert encode({"one": 1, "two": 2}) != encode({"two": 2, "one": 1})


def test_unknown_objects_refuse_without_repr_pickle_property_or_attribute_hooks():
    calls = []

    class Poison:
        def __repr__(self):
            calls.append("repr")
            raise AssertionError("repr was invoked")

        def __reduce__(self):
            calls.append("pickle")
            raise AssertionError("pickle was invoked")

        def __getattribute__(self, name):
            calls.append(name)
            raise AssertionError("attribute hook was invoked")

    with pytest.raises(codec.FingerprintError, match="unsupported"):
        encode(Poison())
    assert calls == []


def test_generic_mapping_proxy_is_refused_without_calling_the_wrapped_mapping():
    calls = []

    class Mapping:
        def __getitem__(self, key):
            calls.append("getitem")
            raise AssertionError("wrapped mapping was invoked")

        def __iter__(self):
            calls.append("iter")
            raise AssertionError("wrapped mapping was invoked")

        def __len__(self):
            calls.append("len")
            raise AssertionError("wrapped mapping was invoked")

        def items(self):
            calls.append("items")
            raise AssertionError("wrapped mapping was invoked")

    with pytest.raises(codec.FingerprintError, match="unsupported"):
        encode(types.MappingProxyType(Mapping()))
    assert calls == []


def test_type_dispatch_does_not_invoke_custom_metaclass_equality_or_hashing():
    calls = []

    class Meta(type):
        def __eq__(self, other):
            calls.append("equality")
            raise AssertionError("metaclass equality was invoked")

        def __hash__(self):
            calls.append("hash")
            raise AssertionError("metaclass hashing was invoked")

    class Stored(metaclass=Meta):
        pass

    rule = codec.StorageRule(Stored, dict_storage=True)
    assert encode(Stored(), rules=(rule,))
    assert calls == []


def test_explicit_storage_rule_reads_slots_and_dict_using_only_builtin_descriptors():
    calls = []

    class Stored:
        __slots__ = ("slot", "empty", "__dict__")

        def __getattribute__(self, name):
            calls.append(name)
            raise AssertionError("user attribute hook was invoked")

    obj = Stored()
    object.__setattr__(obj, "slot", {"nested": [1]})
    object.__setattr__(obj, "extra", [2])
    rule = codec.StorageRule(Stored, dict_storage=True, slots=("slot", "empty"))
    before = encode(obj, rules=(rule,))
    object.__getattribute__(obj, "slot")["nested"].append(3)
    changed_slot = encode(obj, rules=(rule,))
    assert before != changed_slot
    object.__getattribute__(obj, "extra").append(4)
    assert encode(obj, rules=(rule,)) != changed_slot
    object.__setattr__(obj, "empty", None)
    assert encode(obj, rules=(rule,)) != changed_slot
    assert calls == []


def test_property_masquerading_as_storage_is_refused_without_invoking_it():
    calls = []

    class Poison:
        __slots__ = ()

        @property
        def __dict__(self):
            calls.append("property")
            return {}

    rule = codec.StorageRule(Poison, dict_storage=True)
    with pytest.raises(codec.FingerprintError, match="verified builtin descriptor"):
        encode(Poison(), rules=(rule,))
    assert calls == []


def test_rules_cannot_omit_slots_dictionary_or_tuple_payload():
    class Stored:
        __slots__ = ("one", "two", "__dict__")

    for rule in (codec.StorageRule(Stored, slots=("one",)),
                 codec.StorageRule(Stored, slots=("one", "two")),
                 codec.StorageRule(Stored, dict_storage=True)):
        with pytest.raises(codec.FingerprintError, match="complete declared layout"):
            codec.Encoder((rule,))

    class Sequence(tuple):
        __slots__ = ()

        def __iter__(self):
            raise AssertionError("custom iteration was invoked")

        def __len__(self):
            raise AssertionError("custom length was invoked")

    rule = codec.StorageRule(Sequence, tuple_contents=True)
    assert encode(Sequence((1, 2)), rules=(rule,)) != encode(Sequence((1, 3)), rules=(rule,))


def test_rule_for_subclass_does_not_admit_unregistered_descendant_or_hidden_builtin_storage():
    class Stored:
        pass

    class Child(Stored):
        pass

    rule = codec.StorageRule(Stored, dict_storage=True)
    with pytest.raises(codec.FingerprintError, match="unsupported"):
        encode(Child(), rules=(rule,))

    class Hidden(list):
        pass

    with pytest.raises(codec.FingerprintError, match="builtin subtype"):
        codec.Encoder((codec.StorageRule(Hidden, dict_storage=True),))


def test_shadowed_slots_and_unreviewed_c_base_payloads_cannot_be_hidden():
    class Base:
        __slots__ = ("value",)

    class Child(Base):
        __slots__ = ("value",)

    with pytest.raises(codec.FingerprintError, match="shadowed slot"):
        codec.Encoder((codec.StorageRule(Child, slots=("value",)),))
    for base in (bytearray, deque):
        class Hidden(base):
            pass
        with pytest.raises(codec.FingerprintError, match="inherited storage base"):
            codec.Encoder((codec.StorageRule(Hidden, dict_storage=True),))


def test_slot_descriptors_cannot_be_remapped_or_deleted_to_hide_existing_cells():
    class Remapped:
        __slots__ = ("one", "two")

    Remapped.one = Remapped.two
    with pytest.raises(codec.FingerprintError, match="remapped or foreign"):
        codec.Encoder((codec.StorageRule(Remapped, slots=("one", "two")),))

    class Deleted:
        __slots__ = ("one", "two")

    del Deleted.one
    with pytest.raises(codec.FingerprintError, match="retain every original descriptor"):
        codec.Encoder((codec.StorageRule(Deleted, slots=("two",)),))


def test_private_slot_names_have_explicit_descriptor_storage_without_accessing_properties():
    class Stored:
        __slots__ = ("__hidden",)

    obj = Stored()
    object.__setattr__(obj, "_Stored__hidden", [1])
    rule = codec.StorageRule(Stored, slots=("_Stored__hidden",))
    before = encode(obj, rules=(rule,))
    object.__getattribute__(obj, "_Stored__hidden").append(2)
    assert encode(obj, rules=(rule,)) != before


def test_class_name_string_subclasses_cannot_run_hooks_during_slot_mangling():
    calls = []

    class Name(str):
        def lstrip(self, *args):
            calls.append("lstrip")
            raise AssertionError("custom name method was invoked")

    class Stored:
        __slots__ = ("__hidden",)

    Stored.__name__ = Name("Stored")
    with pytest.raises(codec.FingerprintError, match="bounded exact string"):
        codec.Encoder((codec.StorageRule(Stored, slots=("_Stored__hidden",)),))
    assert calls == []


def test_function_defaults_closures_annotations_and_mutable_metadata_are_captured():
    state = [1]

    def function(value=[2]):
        return state, value

    before = encode(function)
    state.append(3)
    assert encode(function) != before
    before = encode(function)
    function.__defaults__[0].append(4)
    assert encode(function) != before
    before = encode(function)
    function.__annotations__["value"] = "changed"
    assert encode(function) != before
    before = encode(function)
    function.marker = [5]
    assert encode(function) != before


def test_descriptors_methods_partials_and_code_objects_are_supported_without_execution():
    calls = []

    def function(value=1):
        calls.append(value)

    class Stored:
        def method(self):
            calls.append("method")

    obj = Stored()
    rule = codec.StorageRule(Stored, dict_storage=True)
    values = [classmethod(function), staticmethod(function), property(function),
              functools.partial(function, 2), function.__code__, obj.method,
              object.__repr__, object.__dict__["__class__"], list.append, len]
    assert encode(values, rules=(rule,))
    assert calls == []


def test_registered_module_and_class_mutations_are_captured_without_metaclass_hooks():
    calls = []

    class Meta(type):
        def __getattribute__(self, name):
            calls.append(name)
            raise AssertionError("metaclass attribute hook was invoked")

    class Data(metaclass=Meta):
        __module__ = "template_for_test"
        mutable = {"keys": [1]}

    module = types.ModuleType("template_for_test")
    module.Data = Data
    module.constant = [2]
    modules = {module.__name__: module}
    before = codec.Encoder().encode(codec.module_roots(modules))
    codec._class_dict(Data)["mutable"]["keys"].append(3)
    assert codec.Encoder().encode(codec.module_roots(modules)) != before
    before = codec.Encoder().encode(codec.module_roots(modules))
    module.constant.append(4)
    assert codec.Encoder().encode(codec.module_roots(modules)) != before
    assert calls == []


@pytest.mark.parametrize("kwargs,value", [
    ({"max_nodes": 1}, [[]]),
    ({"max_depth": 1}, [[[]]]),
    ({"max_container": 1}, [1, 2]),
    ({"max_scalar_bytes": 2}, "abc"),
    ({"max_scalar_bytes": 4}, "\U0001f331\U0001f331"),
    ({"max_bytes": 32}, "payload"),
])
def test_resource_limits_fail_before_a_fingerprint_can_be_returned(kwargs, value):
    with pytest.raises(codec.FingerprintError, match="limit"):
        encode(value, **kwargs)


def test_encoders_are_single_use_and_rule_and_root_schemas_are_closed():
    instance = codec.Encoder()
    instance.encode({"root": 1})
    with pytest.raises(codec.FingerprintError, match="single-use"):
        instance.encode({"root": 2})
    with pytest.raises(codec.FingerprintError, match="positive integers"):
        codec.Encoder(max_depth=True)
    with pytest.raises(codec.FingerprintError, match="named plain dictionary"):
        codec.Encoder().encode({False: "not a root name"})
    with pytest.raises(codec.FingerprintError, match="empty storage rule"):
        codec.StorageRule(object)
    with pytest.raises(codec.FingerprintError, match="slots"):
        codec.StorageRule(object, slots=("same", "same"))


def test_rule_iterators_and_registry_keys_are_rejected_before_running_custom_code():
    calls = []

    def rules():
        calls.append("rule iterator")
        yield None

    with pytest.raises(codec.FingerprintError, match="bounded tuple"):
        codec.Encoder(rules())

    class Key:
        def __lt__(self, other):
            calls.append("ordering")
            raise AssertionError("registry key ordering was invoked")

    with pytest.raises(codec.FingerprintError, match="names/count"):
        codec.module_roots({Key(): types.ModuleType("unknown"), "known": types.ModuleType("known")})
    assert calls == []


def test_module_registry_cannot_overwrite_class_roots_using_separator_names():
    module = types.ModuleType("a")
    shadow = types.ModuleType("a::Data")
    with pytest.raises(codec.FingerprintError, match="names/count"):
        codec.module_roots({"a": module, "a::Data": shadow})


def test_module_namespace_key_validation_precedes_all_name_lookups():
    calls = []

    class Key:
        def __hash__(self):
            return hash("__name__")

        def __eq__(self, other):
            calls.append("equality")
            raise AssertionError("colliding key equality was invoked")

    module = types.ModuleType("safe")
    del vars(module)["__name__"]
    vars(module)[Key()] = "safe"
    with pytest.raises(codec.FingerprintError, match="namespace names/count"):
        codec.module_roots({"safe": module})
    with pytest.raises(codec.FingerprintError, match="namespace names/count"):
        encode(module)
    assert calls == []


def test_class_namespace_key_validation_precedes_builtin_metadata_lookups():
    calls = []
    armed = False

    class Key:
        def __hash__(self):
            return hash("__module__")

        def __eq__(self, other):
            if armed:
                calls.append("equality")
                raise AssertionError("class key equality was invoked")
            return False

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        bad = type("Bad", (), {Key(): 1, "__module__": "synthetic"})
    armed = True
    with pytest.raises(codec.FingerprintError, match="class namespace names/count"):
        encode(bad)
    with pytest.raises(codec.FingerprintError, match="class namespace names/count"):
        codec.Encoder((codec.StorageRule(bad, dict_storage=True),))
    assert calls == []


def test_storage_layout_mro_is_bounded_before_scanning_inherited_maps():
    base = object
    for index in range(65):
        base = type(f"Deep{index}", (base,), {})
    with pytest.raises(codec.FingerprintError, match="MRO length limit"):
        codec.Encoder((codec.StorageRule(base, dict_storage=True),))


def test_oversized_class_metadata_cannot_escape_scalar_or_byte_bounds():
    class Data:
        pass

    Data.__module__ = "x" * 4097
    with pytest.raises(codec.FingerprintError, match="class identity"):
        encode(Data)


def test_oversized_code_constant_is_bounded_without_marshalling_it(monkeypatch):
    calls = []

    def function():
        return None

    def forbidden_marshal(*args, **kwargs):
        calls.append("marshal")
        raise AssertionError("unbounded marshal was invoked")

    huge_code = function.__code__.replace(co_consts=(b"x" * (1024 * 1024 + 1),))
    monkeypatch.setattr(marshal, "dumps", forbidden_marshal)
    with pytest.raises(codec.FingerprintError, match="scalar byte limit"):
        encode(huge_code)
    assert calls == []
