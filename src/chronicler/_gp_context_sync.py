"""Private GP-sync prototype; normal AgentBridge routing does not import this.

The explicit candidate accepts only owned compiled getters and stock models.
Its exact scalar fallback uses the bridge module's original globals, including
per-occurrence helper lookups. No Native import, World schema or stored cache.
Batch allocation errors occur before GP updates, unlike scalar partial progress;
the prototype is not universally equivalent under resource exhaustion.
"""
from __future__ import annotations

from importlib.machinery import EXTENSION_SUFFIXES, ExtensionFileLoader, ModuleSpec
import sys
from types import BuiltinFunctionType, FunctionType, MethodDescriptorType, ModuleType

from pydantic import BaseModel
import pydantic.main as _pydantic_main
from pydantic.main import _SIMPLE_SETATTR_HANDLERS

from chronicler import agent_bridge as _bridge
from chronicler import models as _models


def _raw_class_member(cls, name):
    """Resolve a relevant guard/field owner without descriptor invocation."""
    for owner in type.__getattribute__(cls, "__mro__"):
        fields = type.__getattribute__(owner, "__dict__")
        if name in fields:
            return owner, fields[name]
    return None, None


_MAX_REQUESTS = 50
_CONTEXT_NODES = 512
_CONTEXT_DEPTH = 16
_METHODS = ("get_agent_context_batch", "get_agent_memories",
            "get_agent_needs", "get_agent_relationships")
_STOCK_BRIDGE = vars(_bridge).get("AgentBridge")
_STOCK_MEMORY = vars(_bridge).get("_get_agent_memory_records")
_STOCK_DECODE = vars(_bridge).get("_decode_agent_memory_row")
_STOCK_RECORD = vars(_bridge).get("AgentMemoryRecord")
_MODEL_SETATTR = _raw_class_member(BaseModel, "__setattr__")[1]
_MODEL_GETATTR = _raw_class_member(BaseModel, "__getattr__")[1]
_MODEL_FIELD_HANDLER = (dict.get(_SIMPLE_SETATTR_HANDLERS, "model_field")
                        if type(_SIMPLE_SETATTR_HANDLERS) is dict
                        and all(type(key) is str for key in _SIMPLE_SETATTR_HANDLERS) else None)


def _bridge_function(function, name, qualified=None):
    return (type(function) is FunctionType and function.__globals__ is vars(_bridge)
            and type(function.__module__) is str
            and type(function.__qualname__) is str
            and function.__module__ == _bridge.__name__
            and function.__qualname__ == (name if qualified is None else qualified)
            and function.__code__.co_name == name
            and function.__code__.co_filename == _bridge.__file__)


def _model_runtime_stock():
    if (vars(_pydantic_main).get("_SIMPLE_SETATTR_HANDLERS") is not _SIMPLE_SETATTR_HANDLERS
            or type(_SIMPLE_SETATTR_HANDLERS) is not dict
            or any(type(key) is not str for key in _SIMPLE_SETATTR_HANDLERS)):
        return False
    for function, name, qualified in (
        (_MODEL_SETATTR, "__setattr__", "BaseModel.__setattr__"),
        (_MODEL_GETATTR, "__getattr__", "BaseModel.__getattr__"),
        (_MODEL_FIELD_HANDLER, "_model_field_setattr_handler", "_model_field_setattr_handler"),
    ):
        if (type(function) is not FunctionType or function.__globals__ is not vars(_pydantic_main)
                or type(function.__module__) is not str or type(function.__qualname__) is not str
                or function.__module__ != _pydantic_main.__name__ or function.__qualname__ != qualified
                or function.__code__.co_name != name or function.__code__.co_filename != _pydantic_main.__file__):
            return False
    return (_raw_class_member(BaseModel, "__setattr__")[1] is _MODEL_SETATTR
            and _raw_class_member(BaseModel, "__getattr__")[1] is _MODEL_GETATTR
            and _SIMPLE_SETATTR_HANDLERS.get("model_field") is _MODEL_FIELD_HANDLER)


def _native_batch_getter(sim):
    """Static ownership first; never look up a getter on a foreign instance."""
    native = sys.modules.get("chronicler_agents.chronicler_agents")
    package = sys.modules.get("chronicler_agents")
    if type(native) is not ModuleType or type(package) is not ModuleType:
        return None
    fields = vars(native)
    cls = fields.get("AgentSimulator")
    if type(cls) is not type or type(sim) is not cls or vars(package).get("AgentSimulator") is not cls:
        return None
    spec = fields.get("__spec__")
    if type(spec) is not ModuleSpec:
        return None
    loader = spec.loader
    if (type(loader) is not ExtensionFileLoader or fields.get("__loader__") is not loader
            or type(spec.name) is not str or type(loader.name) is not str
            or type(fields.get("__file__")) is not str
            or spec.name != "chronicler_agents.chronicler_agents"
            or loader.name != spec.name or fields.get("__file__") != spec.origin
            or type(spec.origin) is not str or not spec.origin.endswith(tuple(EXTENSION_SUFFIXES))):
        return None
    if (type.__getattribute__(cls, "__dictoffset__") != 0
            or _raw_class_member(cls, "__getattribute__")[1] is not object.__getattribute__):
        return None
    owned = type.__getattribute__(cls, "__dict__")
    methods = []
    for name in _METHODS:
        descriptor = owned.get(name)
        if (type(descriptor) is not MethodDescriptorType or descriptor.__objclass__ is not cls
                or descriptor.__name__ != name):
            return None
        getter = descriptor.__get__(sim, cls)
        if (type(getter) is not BuiltinFunctionType or getter.__self__ is not sim
                or getter.__name__ != name or getter != descriptor.__get__(sim, cls)):
            return None
        methods.append(getter)
    return methods[0]


def _stock_model(value, cls):
    if type(value) is not cls or type(cls) is not type(BaseModel):
        return False
    module = _raw_class_member(cls, "__module__")[1]
    if (type(module) is not str or module != "chronicler.models"
            or _raw_class_member(cls, "__getattribute__")[1] is not object.__getattribute__
            or _raw_class_member(cls, "__setattr__")[1] is not _MODEL_SETATTR
            or _raw_class_member(cls, "__getattr__")[1] is not _MODEL_GETATTR):
        return False
    config = _raw_class_member(cls, "model_config")[1]
    return (type(config) is dict and all(type(key) is str for key in config)
            and (config.get("frozen") is None or config.get("frozen") is False)
            and (config.get("validate_assignment") is None or config.get("validate_assignment") is False)
            and type(object.__getattribute__(value, "__dict__")) is dict
            and type(object.__getattribute__(value, "__pydantic_fields_set__")) is set)


def _plain_context(value, remaining, active, depth=0):
    remaining[0] -= 1
    if remaining[0] < 0 or depth > _CONTEXT_DEPTH:
        return False
    kind = type(value)
    if value is None or kind in (bool, int, float, str, bytes):
        return True
    if kind not in (list, tuple, dict):
        return False
    token = id(value)
    if token in active:
        return False
    active.add(token)
    try:
        if kind is dict:
            return all(_plain_context(k, remaining, active, depth + 1)
                       and _plain_context(v, remaining, active, depth + 1) for k, v in value.items())
        return all(_plain_context(v, remaining, active, depth + 1) for v in value)
    finally:
        active.remove(token)


def _gp_assignment_stock():
    gp_class = vars(_models).get("GreatPerson")
    if type(gp_class) is not type(BaseModel):
        return False
    handlers = _raw_class_member(gp_class, "__pydantic_setattr_handlers__")[1]
    if type(handlers) is not dict or any(type(key) is not str for key in handlers):
        return False
    for name in ("memories", "needs", "agent_bonds"):
        handler = handlers.get(name)
        if _raw_class_member(gp_class, name)[0] is not None or handler is not None and handler is not _MODEL_FIELD_HANDLER:
            return False
    return True


def _memory_record_stock():
    if type(_STOCK_RECORD) is not type:
        return False
    module = _raw_class_member(_STOCK_RECORD, "__module__")[1]
    # Exact metaclass type supplies this fixed data-descriptor metadata;
    # __qualname__ is not an ordinary entry in a Python class's own dict.
    qualified = type.__getattribute__(_STOCK_RECORD, "__qualname__")
    slots = _raw_class_member(_STOCK_RECORD, "__slots__")[1]
    return (type(module) is str and module == _bridge.__name__
            and type(qualified) is str and qualified == "AgentMemoryRecord"
            and type(slots) is tuple and all(type(name) is str for name in slots)
            and slots == ("event_type", "source_civ", "turn", "intensity", "decay_factor", "is_legacy"))


def _collect_targets(world):
    """Pure stock-model admission; no simulator lookup or field mutation."""
    world_class = vars(_models).get("WorldState")
    civ_class = vars(_models).get("Civilization")
    gp_class = vars(_models).get("GreatPerson")
    if (not _model_runtime_stock() or not _stock_model(world, world_class)
            or not _gp_assignment_stock()):
        return None
    # These are the exact scalar loop reads. Any effective class/MRO member
    # selects scalar before raw-dict collection; never evaluate its descriptor.
    for cls, names in ((world_class, ("civilizations",)), (civ_class, ("great_persons",)),
                       (gp_class, ("active", "agent_id"))):
        if type(cls) is not type(BaseModel) or any(_raw_class_member(cls, name)[0] is not None for name in names):
            return None
    civs = object.__getattribute__(world, "__dict__").get("civilizations")
    if type(civs) is not list:
        return None
    targets = []
    for civ in civs:
        if not _stock_model(civ, civ_class):
            return None
        persons = object.__getattribute__(civ, "__dict__").get("great_persons")
        if type(persons) is not list:
            return None
        for gp in persons:
            if not _stock_model(gp, gp_class):
                return None
            fields = object.__getattribute__(gp, "__dict__")
            active = fields.get("active")
            if type(active) is not bool:
                return None
            if not active:
                continue
            aid = fields.get("agent_id")
            if aid is None:
                continue
            if type(aid) is not int or not 0 <= aid < 2**32 or len(targets) == _MAX_REQUESTS:
                return None
            remaining, seen = [_CONTEXT_NODES], set()
            for name in ("memories", "needs", "agent_bonds"):
                if name not in fields or not _plain_context(fields[name], remaining, seen):
                    return None
            targets.append((gp, aid))
    return targets


def _prepare_native_sync(self, world):
    """Return the owned simulator, ordered targets and bound batch getter, or None.

    Unsupported/edited inputs choose the original loop before batch reads/writes.
    Private/extras metadata is preserved rather than projected out.
    """
    if (type(self) is not _STOCK_BRIDGE or type(_STOCK_BRIDGE) is not type
            or vars(_bridge).get("AgentBridge") is not _STOCK_BRIDGE):
        return None
    module = _raw_class_member(_STOCK_BRIDGE, "__module__")[1]
    tick_owner, tick = _raw_class_member(_STOCK_BRIDGE, "tick_agents")
    if (type(module) is not str or module != _bridge.__name__
            or _raw_class_member(_STOCK_BRIDGE, "__getattribute__")[1] is not object.__getattribute__
            or _raw_class_member(_STOCK_BRIDGE, "_sim")[0] is not None
            or tick_owner is not _STOCK_BRIDGE
            or not _bridge_function(tick, "tick_agents", "AgentBridge.tick_agents")):
        return None
    bridge_fields = object.__getattribute__(self, "__dict__")
    if type(bridge_fields) is not dict or "tick_agents" in bridge_fields:
        return None
    sim = bridge_fields.get("_sim")
    getter = _native_batch_getter(sim)
    if getter is None:
        return None
    if (vars(_bridge).get("_get_agent_memory_records") is not _STOCK_MEMORY
            or vars(_bridge).get("_decode_agent_memory_row") is not _STOCK_DECODE
            or vars(_bridge).get("AgentMemoryRecord") is not _STOCK_RECORD
            or not _bridge_function(_STOCK_MEMORY, "_get_agent_memory_records")
            or not _bridge_function(_STOCK_DECODE, "_decode_agent_memory_row")
            or not _memory_record_stock()):
        return None
    targets = _collect_targets(world)
    return None if targets is None else (sim, targets, getter)


def _validate_rows(targets, rows):
    if type(rows) is not list or len(rows) != len(targets):
        raise ValueError("GP context batch row count/type differs from requested targets")
    for (_, aid), row in zip(targets, rows):
        if type(row) is not tuple or len(row) != 4 or type(row[0]) is not int or row[0] != aid:
            raise ValueError("GP context batch row identity/order differs")
        _, memories, needs, bonds = row
        if type(memories) is not list or len(memories) > 8:
            raise ValueError("GP context memory shape differs")
        for memory in memories:
            if (type(memory) is not tuple or len(memory) not in (5, 6)
                    or any(type(v) is not int for v in memory[:5])
                    or len(memory) == 6 and type(memory[5]) is not bool):
                raise ValueError("GP context memory row differs")
        if needs is not None and (type(needs) is not tuple or len(needs) != 6
                                  or any(type(v) is not float for v in needs)):
            raise ValueError("GP context needs shape differs")
        if bonds is not None:
            if type(bonds) is not list or len(bonds) > 8:
                raise ValueError("GP context bonds shape differs")
            if any(type(b) is not tuple or len(b) != 4 or any(type(v) is not int for v in b) for b in bonds):
                raise ValueError("GP context bond row differs")


def _apply_rows(targets, rows):
    """Validate the complete batch before the existing ordered assignments."""
    _validate_rows(targets, rows)
    for (gp, _aid), (_returned, memories, raw_needs, raw_bonds) in zip(targets, rows):
        memory_records = [_bridge._decode_agent_memory_row(row) for row in memories]
        gp.memories = [
            {"event_type": m.event_type, "source_civ": m.source_civ, "turn": m.turn,
             "intensity": m.intensity, "decay_factor": m.decay_factor, "is_legacy": m.is_legacy}
            for m in memory_records
        ]
        if raw_needs is not None:
            gp.needs = {"safety": raw_needs[0], "material": raw_needs[1],
                        "social": raw_needs[2], "spiritual": raw_needs[3],
                        "autonomy": raw_needs[4], "purpose": raw_needs[5]}
        if raw_bonds is not None:
            gp.agent_bonds = [{"target_id": b[0], "sentiment": b[1], "bond_type": b[2], "formed_turn": b[3]}
                              for b in raw_bonds]


def _sync_batch_prototype(self, world):
    """Explicit prototype only; the production hybrid loop stays unchanged."""
    prepared = _prepare_native_sync(self, world)
    if prepared is None:
        return _sync_scalar_reference(self, world)
    _sim, targets, getter = prepared
    if not targets:
        return None
    rows = getter([aid for _gp, aid in targets])
    _apply_rows(targets, rows)
    return None


def _sync_scalar_reference(self, world):
    # M48: Sync memories for active named characters
    for civ_obj in world.civilizations:
        for gp in civ_obj.great_persons:
            if gp.active and gp.agent_id is not None:
                memory_records = _get_agent_memory_records(self._sim, gp.agent_id)
                gp.memories = [
                    {
                        "event_type": m.event_type,
                        "source_civ": m.source_civ,
                        "turn": m.turn,
                        "intensity": m.intensity,
                        "decay_factor": m.decay_factor,
                        "is_legacy": m.is_legacy,
                    }
                    for m in memory_records
                ]
                # M49: Sync needs for active named characters
                raw_needs = self._sim.get_agent_needs(gp.agent_id)
                if raw_needs is not None:
                    gp.needs = {
                        "safety": raw_needs[0], "material": raw_needs[1],
                        "social": raw_needs[2], "spiritual": raw_needs[3],
                        "autonomy": raw_needs[4], "purpose": raw_needs[5],
                    }
                # M50a: relationship sync
                raw_bonds = self._sim.get_agent_relationships(gp.agent_id)
                if raw_bonds is not None:
                    gp.agent_bonds = [
                        {"target_id": b[0], "sentiment": b[1], "bond_type": b[2], "formed_turn": b[3]}
                        for b in raw_bonds
                    ]


# Keep original helper lookup timing/namespace without an extra wrapper per GP.
# This rebinds our declared code object, never evaluates producer/input source.
_sync_scalar_reference = FunctionType(
    _sync_scalar_reference.__code__, vars(_bridge), "_sync_scalar_reference",
)
