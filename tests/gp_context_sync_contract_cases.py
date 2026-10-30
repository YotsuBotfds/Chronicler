"""Pure contracts for the used private prototype; no Native import or factory."""
from __future__ import annotations

import builtins
from importlib.machinery import ExtensionFileLoader, ModuleSpec
import importlib.util
from pathlib import Path
import struct
import sys
from types import ModuleType, SimpleNamespace

import pytest
from pydantic import BaseModel

from chronicler import agent_bridge as bridge
from chronicler import _gp_context_sync as sync
from chronicler.models import Civilization, GreatPerson, Leader, WorldState


def person(aid=7):
    return GreatPerson(name="P", role="merchant", trait="bold", civilization="C",
                       origin_civilization="C", born_turn=0, agent_id=aid)


def model_world(people):
    civ = Civilization(name="C", population=1, military=1, economy=1, culture=1,
                       stability=50, leader=Leader(name="L", trait="bold", reign_start=0))
    world = WorldState(name="GP admission", seed=42, civilizations=[civ])
    civ.great_persons = people
    return world


def bits(value):
    if type(value) is float:
        return ("float", struct.pack("!d", value).hex())
    if type(value) is dict:
        return [(bits(k), bits(v)) for k, v in value.items()]
    if type(value) in (tuple, list):
        return [bits(v) for v in value]
    return value


class ProbePerson:
    def __init__(self, name, aid, trace, active=True):
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "trace", trace)
        object.__setattr__(self, "active", active)
        object.__setattr__(self, "agent_id", aid)
        object.__setattr__(self, "memories", ["old"])
        object.__setattr__(self, "needs", {"old": -0.0})
        object.__setattr__(self, "agent_bonds", ["old"])

    def __setattr__(self, name, value):
        self.trace.append(("set", self.name, name, bits(value)))
        object.__setattr__(self, name, value)


class ForeignSim:
    def __init__(self, trace, failure=None):
        self.trace, self.failure = trace, failure

    def __getattribute__(self, name):
        if name.startswith("get_agent_"):
            object.__getattribute__(self, "trace").append(("lookup", name))
            if name == "get_agent_context_batch":
                raise AssertionError("foreign batch getter was probed")
        return object.__getattribute__(self, name)

    def read(self, side, aid):
        self.trace.append(("call", side, aid))
        if self.failure == (side, aid):
            raise ValueError("original getter boundary")

    def get_agent_memories(self, aid):
        self.read("memories", aid)
        return [(4, 2, 8, -7, 99), (9, 1, 1, -12, 7, True)]

    def get_agent_needs(self, aid):
        self.read("needs", aid)
        return (0.0, -0.0, 0.25, 0.5, 0.75, 1.0)

    def get_agent_relationships(self, aid):
        self.read("bonds", aid)
        return [(7, -9, 6, 12)]


def fallback_run(function, failure=None, *, exact_bridge=False):
    trace = []
    sim = ForeignSim(trace, failure)
    if exact_bridge:
        instance = bridge.AgentBridge.__new__(bridge.AgentBridge)
        instance._sim = sim
    else:
        instance = SimpleNamespace(_sim=sim)
    people = [ProbePerson("A", 1, trace), ProbePerson("skip", 8, trace, False),
              ProbePerson("none", None, trace), ProbePerson("B", 2, trace)]
    class World:
        @property
        def civilizations(self):
            trace.append(("world", "civilizations"))
            return [SimpleNamespace(great_persons=people)]
    error = None
    try:
        result = function(instance, World())
    except ValueError as exc:
        error, result = str(exc), None
    state = [bits((gp.memories, gp.needs, gp.agent_bonds)) for gp in people]
    return trace, state, error, result


@pytest.mark.parametrize("failure", [None, ("memories", 1), ("needs", 1),
                                    ("bonds", 1), ("memories", 2), ("needs", 2), ("bonds", 2)])
@pytest.mark.parametrize("exact_bridge", [False, True])
def test_foreign_fallback_preserves_every_getter_assignment_and_partial_failure(failure, exact_bridge):
    expected = fallback_run(sync._sync_scalar_reference, failure, exact_bridge=exact_bridge)
    actual = fallback_run(sync._sync_batch_prototype, failure, exact_bridge=exact_bridge)
    assert actual == expected
    assert actual[0][0] == ("world", "civilizations")
    assert all("get_agent_context_batch" not in str(row) for row in actual[0])


def test_fallback_keeps_per_occurrence_current_bridge_helper_lookup(monkeypatch):
    seen = []
    def second(sim, aid):
        seen.append(("second", aid))
        return []
    def first(sim, aid):
        seen.append(("first", aid))
        monkeypatch.setattr(bridge, "_get_agent_memory_records", second)
        return []
    monkeypatch.setattr(bridge, "_get_agent_memory_records", first)
    assert sync._sync_scalar_reference.__globals__ is vars(bridge)
    fallback_run(sync._sync_batch_prototype)
    assert seen == [("first", 1), ("second", 2)]


def test_foreign_dynamic_ids_keep_original_read_and_call_order():
    def run(function):
        log = []
        class GP:
            active = True
            def __init__(self):
                self.next = 0
            @property
            def agent_id(self):
                self.next += 1
                log.append(("id", self.next))
                return self.next
        gp = GP()
        world = SimpleNamespace(civilizations=[SimpleNamespace(great_persons=[gp])])
        function(SimpleNamespace(_sim=ForeignSim(log)), world)
        return log, bits((gp.memories, gp.needs, gp.agent_bonds))
    expected = run(sync._sync_scalar_reference)
    assert run(sync._sync_batch_prototype) == expected
    assert [x for x in expected[0] if x[0] == "id"] == [("id", 1), ("id", 2), ("id", 3), ("id", 4)]
    assert [x for x in expected[0] if x[0] == "call"] == [("call", "memories", 2), ("call", "needs", 3), ("call", "bonds", 4)]


@pytest.mark.parametrize("aid", [True, -1, 2**32, 1.5])
def test_invalid_later_id_fallback_does_not_preempt_earlier_updates(aid):
    trace = []
    first, invalid = ProbePerson("first", 1, trace), ProbePerson("invalid", aid, trace)
    class Sim(ForeignSim):
        def get_agent_memories(self, value):
            if type(value) is not int or not 0 <= value < 2**32:
                raise OverflowError("original ID refusal")
            return super().get_agent_memories(value)
    world = SimpleNamespace(civilizations=[SimpleNamespace(great_persons=[first, invalid])])
    with pytest.raises(OverflowError, match="original ID refusal"):
        sync._sync_batch_prototype(SimpleNamespace(_sim=Sim(trace)), world)
    assert first.memories[0]["is_legacy"] is False and first.needs["material"] == -0.0
    assert first.agent_bonds == [{"target_id": 7, "sentiment": -9, "bond_type": 6, "formed_turn": 12}]
    assert invalid.memories == ["old"]


def test_python_and_borrowed_C_descriptor_native_spoofs_are_not_called(monkeypatch):
    class AgentSimulator:
        __slots__ = ()
        get_agent_context_batch = dict.get
        get_agent_memories = dict.get
        get_agent_needs = dict.get
        get_agent_relationships = dict.get
    name = "chronicler_agents.chronicler_agents"
    module, package = ModuleType(name), ModuleType("chronicler_agents")
    loader = ExtensionFileLoader(name, "/tmp/gp-fake.cpython-313-x86_64-linux-gnu.so")
    module.__loader__, module.__file__ = loader, loader.path
    module.__spec__ = ModuleSpec(name, loader, origin=loader.path)
    module.AgentSimulator = package.AgentSimulator = AgentSimulator
    monkeypatch.setitem(sys.modules, name, module)
    monkeypatch.setitem(sys.modules, "chronicler_agents", package)
    assert sync._native_batch_getter(AgentSimulator()) is None


@pytest.mark.parametrize("edit", ["handler", "field", "config"])
def test_stock_model_metadata_refuses_foreign_callbacks_without_invoking_them(monkeypatch, edit):
    gp = person()
    class Bomb:
        def __bool__(self):
            raise AssertionError("foreign truth test")
        def __eq__(self, other):
            raise AssertionError("foreign equality")
    if edit == "handler":
        handlers = dict(GreatPerson.__pydantic_setattr_handlers__)
        handlers["memories"] = Bomb()
        monkeypatch.setattr(GreatPerson, "__pydantic_setattr_handlers__", handlers)
        assert not sync._gp_assignment_stock()
    elif edit == "field":
        monkeypatch.setattr(GreatPerson, "memories", property(lambda self: pytest.fail("field getter")), raising=False)
        assert not sync._gp_assignment_stock()
    else:
        monkeypatch.setattr(GreatPerson, "model_config", dict(GreatPerson.model_config, frozen=Bomb()))
        assert not sync._stock_model(gp, GreatPerson)


@pytest.mark.parametrize("target", ["memory", "model"])
def test_pre_import_python_patches_are_not_captured_as_stock(monkeypatch, target):
    if target == "memory":
        def replacement(sim, aid):
            return []
        monkeypatch.setattr(bridge, "_get_agent_memory_records", replacement)
    else:
        original = BaseModel.__setattr__
        def replacement(self, name, value):
            return original(self, name, value)
        monkeypatch.setattr(BaseModel, "__setattr__", replacement)
    spec = importlib.util.spec_from_file_location("_gp_preimport_patch_probe", Path(sync.__file__))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if target == "memory":
        assert not module._bridge_function(module._STOCK_MEMORY, "_get_agent_memory_records")
    else:
        assert not module._model_runtime_stock()


@pytest.mark.parametrize("kind", ["cycle", "depth", "nodes", "foreign"])
def test_overwritten_context_validation_is_bounded_and_never_calls_foreign_protocols(kind):
    if kind == "cycle":
        value = []
        value.append(value)
    elif kind == "depth":
        value = []
        for _ in range(20):
            value = [value]
    elif kind == "nodes":
        value = list(range(600))
    else:
        class Foreign:
            def __iter__(self):
                pytest.fail("foreign iterator")
            def __bool__(self):
                pytest.fail("foreign truth")
        value = Foreign()
    assert not sync._plain_context(value, [512], set())
    shared = [1, -0.0, float("nan")]
    assert sync._plain_context([shared, shared], [512], set())


@pytest.mark.parametrize("kind", ["too_many", "bool", "negative", "overflow", "GP_subclass", "list_subclass"])
def test_real_model_collection_refuses_edited_inputs_before_updates_or_callbacks(kind):
    gp = person()
    if kind == "too_many":
        people = [gp] * 51
    elif kind in ("bool", "negative", "overflow"):
        invalid = person(8)
        invalid.agent_id = {"bool": True, "negative": -1, "overflow": 2**32}[kind]
        people = [gp, invalid]
    elif kind == "GP_subclass":
        class Child(GreatPerson):
            pass
        child = Child(**gp.model_dump())
        people = [gp, child]
    else:
        class Edited(list):
            def __iter__(self):
                pytest.fail("edited iterator called by admission")
        people = Edited([gp])
    world = model_world(people)
    before = gp.__dict__.copy()
    assert sync._collect_targets(world) is None
    assert gp.__dict__ == before


def test_real_model_collection_keeps_occurrences_and_ignores_unmodified_private_metadata():
    gp, skip, none = person(7), person(8), person(None)
    skip.active = False
    shared = {"signed": -0.0}
    object.__setattr__(gp, "__pydantic_private__", {"unrelated": shared})
    object.__setattr__(gp, "__pydantic_extra__", {"unrelated": shared})
    world = model_world([gp, skip, none, gp])
    before = gp.__dict__.copy()
    targets = sync._collect_targets(world)
    assert len(targets) == 2 and targets[0][0] is gp and targets[1][0] is gp
    assert [aid for _, aid in targets] == [7, 7]
    assert gp.__dict__ == before
    assert gp.__pydantic_private__["unrelated"] is shared
    assert gp.__pydantic_extra__["unrelated"] is shared
    assert sync._collect_targets(model_world([skip, none])) == []


def test_batch_assignment_retains_legacy_fields_float_bits_and_independent_containers():
    a, b, missing, zero = [person(aid) for aid in (7, 7, 99, 0)]
    stale = {"old": -0.0}
    old_bonds = [{"old": 1}]
    missing.needs = zero.needs = stale
    missing.agent_bonds = zero.agent_bonds = old_bonds
    needs = (-0.0, float("nan"), float("inf"), float("-inf"), 0.25, 0.75)
    memories = [(4, 2, 8, -7, 99), (9, 1, 1, -12, 7, True)]
    bonds = [(11, -9, 6, 12)]
    rows = [(7, memories, needs, bonds), (7, memories, needs, bonds),
            (99, [], None, None), (0, [], needs, None)]
    assert sync._apply_rows([(a, 7), (b, 7), (missing, 99), (zero, 0)], rows) is None
    assert a.memories[0] == {"event_type": 4, "source_civ": 2, "turn": 8,
                             "intensity": -7, "decay_factor": 99, "is_legacy": False}
    assert a.memories[1]["is_legacy"] is True
    assert list(a.needs) == ["safety", "material", "social", "spiritual", "autonomy", "purpose"]
    assert [struct.pack("!d", x) for x in a.needs.values()] == [struct.pack("!d", x) for x in needs]
    assert bits(a.memories) == bits(b.memories) and bits(a.needs) == bits(b.needs)
    assert a.memories is not b.memories and a.memories[0] is not b.memories[0]
    assert a.needs is not b.needs and a.agent_bonds is not b.agent_bonds
    assert a.agent_bonds[0] is not b.agent_bonds[0]
    assert missing.memories == [] and missing.needs is stale and missing.agent_bonds is old_bonds
    assert zero.needs is not stale and zero.agent_bonds is old_bonds


@pytest.mark.parametrize("bad", ["count", "id", "memory", "needs", "bonds"])
def test_entire_batch_shape_refusal_precedes_any_GP_assignment(bad):
    a, b = person(7), person(8)
    first = (7, [], None, None)
    second = (8, [], None, None)
    rows = [first, second]
    if bad == "count":
        rows.pop()
    elif bad == "id":
        rows[1] = (9, [], None, None)
    elif bad == "memory":
        rows[1] = (8, [(1,)], None, None)
    elif bad == "needs":
        rows[1] = (8, [], (0.0,), None)
    else:
        rows[1] = (8, [], None, [(1,)])
    original = [gp.__dict__.copy() for gp in (a, b)]
    with pytest.raises(ValueError):
        sync._apply_rows([(a, 7), (b, 8)], rows)
    assert a.__dict__ == original[0] and b.__dict__ == original[1]


def test_repeated_GP_occurrences_receive_ordered_replacements():
    trace = []
    gp = ProbePerson("same", 7, trace)
    rows = [(7, [(1, 0, 1, -1, 3)], None, None),
            (7, [(2, 0, 2, -2, 4)], None, None)]
    sync._apply_rows([(gp, 7), (gp, 7)], rows)
    assert [row[2] for row in trace] == ["memories", "memories"]
    assert gp.memories[0]["event_type"] == 2
