"""SwitchStateMixin and the shared switch helpers (CON-2) against verbatim
copies of the hand-written code they replace."""
from __future__ import annotations

from fractions import Fraction
import pickle
import sys
import types
from types import SimpleNamespace
from typing import ClassVar

from pydantic import BaseModel, Field, PrivateAttr
import pytest

from chronicler import switch_state
from chronicler.apprenticeship_state import _Record
from chronicler.scientific_research_state import LazyResearchModel
from chronicler.switch_state import SwitchStateMixin, bump_counter

COUNTERS = ("a", "b")

# ---------------------------------------------------------------------------
# _bump: verbatim copies of every variant (spec section 2), module named
# ---------------------------------------------------------------------------


def _plain(state, name, amount=1):                     # adaptive_livelihoods, workshop_payroll
    state.counters[name] = state.counters.get(name, 0) + amount


def _round4(state, key, n=1):                          # agent_movements, cities, guilds, nomads, scholarship
    state.counters[key] = round(state.counters.get(key, 0) + n, 4)


def _strict(state, key, amount=1):                     # apprenticeship, learning_cohorts, movement_branches, operating_wear
    if key not in COUNTERS:
        raise KeyError(key)
    state.counters[key] = state.counters.get(key, 0) + amount


def _strict_message(state, key, amount=1):             # attribution_records (and recovery_crews, ...)
    if key not in COUNTERS:
        raise KeyError(f"undeclared attribution-records counter {key!r}")
    state.counters[key] = state.counters.get(key, 0) + amount


def _bare_counters(counters, key, amount):             # clearing_protection, commons_rules
    counters[key] = counters.get(key, 0) + amount


def _counts(state, key, n=1):                          # diplomacy
    state.counts[key] = state.counts.get(key, 0) + n


def _strict_round6(state, key, amount=1):              # epidemic_care
    if key not in COUNTERS:
        raise KeyError(f"undeclared epidemic care counter {key!r}")
    state.counters[key] = round(state.counters.get(key, 0) + amount, 6)


def _float_zero(state, key, value):                    # grain_reserves
    state.counters[key] = state.counters.get(key, 0.0) + value


def _strict_int(state, key, amount=1):                 # guild_leagues, household_retail, reform_services, relocation_costs, remittances
    if key not in COUNTERS:
        raise KeyError(key)
    state.counters[key] = state.counters.get(key, 0) + int(amount)


def _round6(state, key, amount=1):                     # household_access, local_budgets
    state.counters[key] = round(state.counters.get(key, 0) + amount, 6)


def _maritime(state, key, amount=1):                   # maritime
    value = state.counters.get(key, 0) + amount
    state.counters[key] = round(value, 4) if isinstance(value, float) else value


def _totals(state, key, value):                        # public_health
    state.totals[key] = round(state.totals.get(key, 0.0) + value, 6)


def _ritual(state, key, value=1):                      # ritual_gatherings
    state.counters[key] = round(state.counters.get(key, 0.0) + value, 9)


def _timber_orders(state, key, amount=1):              # timber_orders
    if key not in COUNTERS:
        raise KeyError(f"undeclared timber order counter {key}")
    state.counters[key] = state.counters.get(key, 0) + int(amount)


def _strict_message_int(state, key, amount=1):         # titled_trade, workshop_economics
    if key not in COUNTERS:
        raise KeyError(f"undeclared titled trade counter {key!r}")
    state.counters[key] = state.counters.get(key, 0) + int(amount)


def _veteran(state, key, amount=1):                    # veteran_reintegration
    if key not in COUNTERS:
        raise KeyError(key)
    if amount:
        state.counters[key] = state.counters.get(key, 0) + int(amount)


def _war_requisition(state, key, value=1):             # war_requisition
    if key not in COUNTERS:
        raise KeyError(key)
    state.counters[key] = state.counters.get(key, 0) + int(value)


# (old function, target attribute or None for a bare dict, bump_counter options)
VARIANTS = {
    "plain": (_plain, "counters", {}),
    "round4": (_round4, "counters", {"ndigits": 4}),
    "strict": (_strict, "counters", {"allowed": COUNTERS}),
    "strict_message": (_strict_message, "counters",
                       {"allowed": COUNTERS, "message": "undeclared attribution-records counter {key!r}"}),
    "bare_counters": (_bare_counters, None, {}),
    "counts": (_counts, "counts", {}),
    "strict_round6": (_strict_round6, "counters",
                      {"allowed": COUNTERS, "message": "undeclared epidemic care counter {key!r}", "ndigits": 6}),
    "float_zero": (_float_zero, "counters", {"zero": 0.0}),
    "strict_int": (_strict_int, "counters", {"allowed": COUNTERS, "coerce": int}),
    "round6": (_round6, "counters", {"ndigits": 6}),
    "maritime": (_maritime, "counters", {"ndigits": 4, "float_only_round": True}),
    "totals": (_totals, "totals", {"zero": 0.0, "ndigits": 6}),
    "ritual": (_ritual, "counters", {"zero": 0.0, "ndigits": 9}),
    "timber_orders": (_timber_orders, "counters",
                      {"allowed": COUNTERS, "message": "undeclared timber order counter {key}", "coerce": int}),
    "strict_message_int": (_strict_message_int, "counters",
                           {"allowed": COUNTERS, "message": "undeclared titled trade counter {key!r}",
                            "coerce": int}),
    "veteran": (_veteran, "counters", {"allowed": COUNTERS, "skip_zero": True, "coerce": int}),
    "war_requisition": (_war_requisition, "counters", {"allowed": COUNTERS, "coerce": int}),
}

OPS = [("b", Fraction(1, 3)),   # a non-float sum: only maritime leaves it unrounded
       ("a", 1), ("a", 0), ("b", 2.5), ("a", 0.1), ("a", 0.2), ("b", -2.5), ("zzz", 1), ("b", 1e-7),
       ("a", True), ("b", 0.0), ("a", 3.7), ("b", None), ("a", -1), ("zzz", 0), ("b", 1 / 3), ("a", 10**20)]
STARTS = [dict, lambda: {"a": 0, "b": 0.0}, lambda: {"b": 1.23456789}]


def _view(counters):
    return [(k, type(v).__name__, repr(v)) for k, v in counters.items()]


def _apply(fn, *args):
    try:
        fn(*args)
    except Exception as exc:  # the same failure, type and text, is the contract
        return type(exc).__name__, str(exc)
    return None


@pytest.mark.parametrize("start", STARTS, ids=["empty", "prefilled", "float"])
@pytest.mark.parametrize("name", list(VARIANTS))
def test_bump_counter_reproduces_each_variant(name, start):
    old, attr, options = VARIANTS[name]
    old_state = SimpleNamespace(**{attr or "counters": start()})
    new_counters = start()
    for key, amount in OPS:
        if attr is None:
            old_error = _apply(old, old_state.counters, key, amount)
        else:
            old_error = _apply(old, old_state, key, amount)
        new_error = _apply(lambda: bump_counter(new_counters, key, amount, **options))
        assert new_error == old_error, (key, amount)
        assert _view(new_counters) == _view(getattr(old_state, attr or "counters")), (key, amount)


@pytest.mark.parametrize("name", [n for n, v in VARIANTS.items() if v[1] == "counters"])
def test_mixin_bump_uses_class_options(name):
    old, _attr, options = VARIANTS[name]

    class Probe(SwitchStateMixin, BaseModel):
        _BUMP: ClassVar = options
        counters: dict = Field(default_factory=dict)

    state, twin = Probe(), SimpleNamespace(counters={})
    for key, amount in OPS:
        assert _apply(state.bump, key, amount) == _apply(old, twin, key, amount)
        assert _view(state.counters) == _view(twin.counters)


def test_bump_counter_defaults_and_unknown_key_message():
    counters = {}
    bump_counter(counters, "x")
    assert counters == {"x": 1}
    with pytest.raises(KeyError) as info:
        bump_counter(counters, "y", allowed=("x",), message="undeclared counter {key!r}")
    assert info.value.args == ("undeclared counter 'y'",)
    assert counters == {"x": 1}


# ---------------------------------------------------------------------------
# lane_active, health_holders, sub_state_getter
# ---------------------------------------------------------------------------

def _old_lane_active(world, name: str) -> bool:        # recovery_crews.py, workshops.py, ...
    from importlib import import_module
    if getattr(getattr(world, "livelihoods", None), name, None) is None:
        return False
    return bool(getattr(import_module("chronicler." + name), f"{name}_active")(world))


def _old_health_holders(world) -> set[int]:            # recovery_crews.py, apprenticeship.py
    health = getattr(world, "health_care", None)
    rows = getattr(health, "_prepared", None) if health is not None else None
    out: set[int] = set()
    for aid, _region, giver, care in rows or ():
        out.add(int(aid))
        if int(giver) and float(care) > 0:
            out.add(int(giver))
    return out


@pytest.fixture
def fake_lane(monkeypatch):
    calls = []
    module = types.ModuleType("chronicler.switch_state_fake_lane")

    def switch_state_fake_lane_active(world):
        calls.append(world)
        return world.answer

    module.switch_state_fake_lane_active = switch_state_fake_lane_active
    monkeypatch.setitem(sys.modules, module.__name__, module)
    return calls


@pytest.mark.parametrize("world", [
    SimpleNamespace(),
    SimpleNamespace(livelihoods=None),
    SimpleNamespace(livelihoods=SimpleNamespace()),
    SimpleNamespace(livelihoods=SimpleNamespace(switch_state_fake_lane=None)),
    SimpleNamespace(livelihoods=SimpleNamespace(switch_state_fake_lane=object()), answer=1),
    SimpleNamespace(livelihoods=SimpleNamespace(switch_state_fake_lane=object()), answer=0),
    SimpleNamespace(livelihoods=SimpleNamespace(switch_state_fake_lane=object()), answer=[]),
    SimpleNamespace(livelihoods=SimpleNamespace(switch_state_fake_lane=object()), answer="yes"),
], ids=["no-container", "none-container", "absent", "none", "true", "zero", "empty", "truthy"])
def test_lane_active_truth_table(world, fake_lane):
    new = switch_state.lane_active(world, "switch_state_fake_lane")
    called = len(fake_lane)
    old = _old_lane_active(world, "switch_state_fake_lane")
    assert type(new) is bool and new == old
    assert called == len(fake_lane) - called  # each consulted the module equally (or not at all)


def test_lane_active_does_not_import_an_absent_lane(monkeypatch):
    def refuse(name):
        raise AssertionError(f"imported {name}")
    monkeypatch.setattr(switch_state, "import_module", refuse)
    world = SimpleNamespace(livelihoods=SimpleNamespace(workshops=None))
    assert switch_state.lane_active(world, "workshops") is False


@pytest.mark.parametrize("rows", [None, [], [(1, 0, 0, 1.0), (2, 0, 3, 0.0), (4, 1, 5, 0.5), ("6", 0, "7", "2")]])
def test_health_holders_matches_old(rows):
    for world in (SimpleNamespace(), SimpleNamespace(health_care=None),
                  SimpleNamespace(health_care=SimpleNamespace(_prepared=rows))):
        assert switch_state.health_holders(world) == _old_health_holders(world)


def test_sub_state_getter_matches_both_old_spellings():
    get = switch_state.sub_state_getter("workshops")

    def old_short(world):                              # workshops.py
        return getattr(world.livelihoods, "workshops", None)

    def old_long(world):                               # adaptive_livelihoods.py
        return getattr(getattr(world, "livelihoods", None), "workshops", None)

    sentinel = object()
    for world in (SimpleNamespace(livelihoods=SimpleNamespace(workshops=sentinel)),
                  SimpleNamespace(livelihoods=SimpleNamespace()),
                  SimpleNamespace(livelihoods=SimpleNamespace(workshops=None))):
        assert get(world) is old_short(world) is old_long(world)
    assert get(SimpleNamespace()) is old_long(SimpleNamespace()) is None


# ---------------------------------------------------------------------------
# Mixin pickle hooks against hand-written twins
# ---------------------------------------------------------------------------

class _Turn:
    pass


_ABSENT = object()


def _fields():
    return {
        "__annotations__": {"schema_version": int, "enabled": bool, "rows": list, "counters": dict},
        "schema_version": 1, "enabled": True,
        "rows": Field(default_factory=list), "counters": Field(default_factory=dict),
    }


def _twins(old_methods, options, privates):
    """(hand-written class, mixin class) with the same fields and privates."""
    ns_old = {**_fields(), **{name: PrivateAttr(**spec) for name, spec in privates.items()}, **old_methods}
    ns_new = {**_fields(), **{name: PrivateAttr(**spec) for name, spec in privates.items()},
              **{k: v for k, v in options.items()}}
    ns_new["__annotations__"] = {**ns_new["__annotations__"], **{k: ClassVar for k in options}}
    old = type("Probe", (BaseModel,), {"__module__": __name__, **ns_old})
    new = type("Probe", (SwitchStateMixin, BaseModel), {"__module__": __name__, **ns_new})
    return old, new


def _getstate_turn(self):                              # recovery_crews_state.py
    state = super(type(self), self).__getstate__()
    private = state.get("__pydantic_private__")
    if private and private.get("_turn") is not None:
        state = {**state, "__pydantic_private__": {**private, "_turn": None}}
    return state


def _setstate_fill_all_turn(self, state):              # recovery_crews_state.py
    super(type(self), self).__setstate__(state)
    for name, field in type(self).model_fields.items():
        if name not in self.__dict__:
            self.__dict__[name] = field.get_default(call_default_factory=True)
    if getattr(self, "__pydantic_private__", None) is None:
        object.__setattr__(self, "__pydantic_private__", {"_turn": None})
    else:
        self.__pydantic_private__.setdefault("_turn", None)


def _getstate_two(self):                               # infrastructure_condition_state.py
    state = super(type(self), self).__getstate__()
    private = state.get("__pydantic_private__")
    if private and (private.get("_turn") is not None or private.get("_labour") is not None):
        state = {**state, "__pydantic_private__": {**private, "_turn": None, "_labour": None}}
    return state


def _setstate_names_two(self, state):                  # livelihoods_state.py (named field list)
    super(type(self), self).__setstate__(state)
    self.__dict__.setdefault("rows", [])
    self.__dict__.setdefault("counters", {})
    private = getattr(self, "__pydantic_private__", None)
    if private is None:
        object.__setattr__(self, "__pydantic_private__", {"_turn": None, "_labour": None})
    else:
        private.setdefault("_turn", None)
        private.setdefault("_labour", None)


def _setstate_private_only(self, state):               # commons_rules_state.py
    super(type(self), self).__setstate__(state)
    private = getattr(self, "__pydantic_private__", None)
    if private is None:
        object.__setattr__(self, "__pydantic_private__", {"_turn": None})
    else:
        private.setdefault("_turn", None)


def _setstate_fill_all(self, state):                   # apprenticeship_state.py, war_requisition_state.py
    super(type(self), self).__setstate__(state)
    for name, field in type(self).model_fields.items():
        if name not in self.__dict__:
            self.__dict__[name] = field.get_default(call_default_factory=True)


def _setstate_factory_privates(self, state):           # veteran_reintegration_state.py
    super(type(self), self).__setstate__(state)
    for name, field in type(self).model_fields.items():
        if name not in self.__dict__:
            self.__dict__[name] = field.get_default(call_default_factory=True)
    private = getattr(self, "__pydantic_private__", None)
    if private is None:
        private = {}
        object.__setattr__(self, "__pydantic_private__", private)
    private.setdefault("_captures", [])
    private.setdefault("_turn", None)


FORMS = {
    "fill-all+turn": ({"__getstate__": _getstate_turn, "__setstate__": _setstate_fill_all_turn},
                      {"_FILL_DEFAULTS": True, "_FILL_PRIVATE": True, "_TRANSIENT": ("_turn",)},
                      {"_turn": {"default": None}}),
    "names+two": ({"__getstate__": _getstate_two, "__setstate__": _setstate_names_two},
                  {"_FILL_DEFAULTS": ("rows", "counters"), "_FILL_PRIVATE": ("_turn", "_labour"),
                   "_TRANSIENT": ("_turn", "_labour")},
                  {"_turn": {"default": None}, "_labour": {"default": None}, "_keep": {"default": 7}}),
    "private-only": ({"__getstate__": _getstate_turn, "__setstate__": _setstate_private_only},
                     {"_FILL_PRIVATE": ("_turn",), "_TRANSIENT": ("_turn",)},
                     {"_turn": {"default": None}}),
    "fill-all": ({"__setstate__": _setstate_fill_all}, {"_FILL_DEFAULTS": True}, {}),
    "factory-privates": ({"__setstate__": _setstate_factory_privates},
                         {"_FILL_DEFAULTS": True, "_FILL_PRIVATE": True},
                         {"_captures": {"default_factory": list}, "_turn": {"default": None}}),
    "none": ({}, {}, {"_turn": {"default": None}}),
}


def _snapshot(obj):
    try:
        private = object.__getattribute__(obj, "__pydantic_private__")
    except AttributeError:
        private = "<absent>"
    return (list(obj.__dict__.items()), sorted(obj.__pydantic_fields_set__), obj.__pydantic_extra__,
            None if private is None else private if private == "<absent>" else list(private.items()))


def _states(cls):
    full = cls(enabled=False)
    full.counters["a"] = 2
    base = full.__getstate__()
    out = {"full": base}
    for drop in ("counters", "rows", "enabled"):
        out[f"no-{drop}"] = {**base, "__dict__": {k: v for k, v in base["__dict__"].items() if k != drop},
                             "__pydantic_fields_set__": base["__pydantic_fields_set__"] - {drop}}
    out["private-none"] = {**base, "__pydantic_private__": None}
    out["private-empty"] = {**base, "__pydantic_private__": {}}
    out["private-partial"] = {**base, "__pydantic_private__": {
        k: v for k, v in list((base["__pydantic_private__"] or {}).items())[1:]}}
    out["old"] = {"__dict__": {}, "__pydantic_extra__": None, "__pydantic_fields_set__": set(),
                  "__pydantic_private__": None}
    return out


def _restore(cls, state):
    obj = cls.__new__(cls)
    obj.__setstate__({k: (dict(v) if isinstance(v, dict) else v) for k, v in state.items()})
    return obj


@pytest.mark.parametrize("form", list(FORMS))
def test_mixin_setstate_matches_hand_written_forms(form):
    old, new = _twins(*FORMS[form])
    for label, state in _states(old).items():
        assert _snapshot(_restore(new, state)) == _snapshot(_restore(old, state)), label


@pytest.mark.parametrize("form", list(FORMS))
def test_mixin_getstate_matches_hand_written_forms(form):
    old, new = _twins(*FORMS[form])
    marker = _Turn()
    for values in ({}, {"_turn": marker}, {"_labour": marker}, {"_turn": marker, "_labour": marker},
                   {"_keep": marker}, {"_turn": _ABSENT}, {"_turn": _ABSENT, "_labour": marker}):
        a, b = old(), new()
        for obj in (a, b):
            for name, value in values.items():
                if name in (obj.__pydantic_private__ or ()):
                    if value is _ABSENT:     # restored from an old pickle without a private fill
                        del obj.__pydantic_private__[name]
                    else:
                        obj.__pydantic_private__[name] = value
        before = b.__pydantic_private__ and list(b.__pydantic_private__.items())
        sa, sb = a.__getstate__(), b.__getstate__()
        assert list(sb) == list(sa)
        for key in sa:
            got, want = sb[key], sa[key]
            assert (list(got.items()) if isinstance(got, dict) else got) == \
                   (list(want.items()) if isinstance(want, dict) else want), (values, key)
        assert (b.__pydantic_private__ and list(b.__pydantic_private__.items())) == before  # live object untouched


def _round_trip(obj, monkeypatch):
    """pickle.dumps/loads of a test-local class, published under a module name."""
    cls = type(obj)
    name = f"_Pickled_{id(cls)}"
    cls.__qualname__ = name                            # a test-local class
    monkeypatch.setattr(sys.modules[__name__], name, cls, raising=False)
    return pickle.loads(pickle.dumps(obj))


@pytest.mark.parametrize("form", list(FORMS))
def test_mixin_pickle_round_trip(form, monkeypatch):
    _old, new = _twins(*FORMS[form])
    obj = new(rows=[1])
    obj.counters["a"] = 1.5
    has_turn = "_turn" in (obj.__pydantic_private__ or ())
    if has_turn:
        obj._turn = _Turn() if FORMS[form][1].get("_TRANSIENT") else None
    again = _round_trip(obj, monkeypatch)
    assert again.model_dump() == obj.model_dump()
    assert again.__pydantic_fields_set__ == obj.__pydantic_fields_set__
    if has_turn and FORMS[form][1].get("_TRANSIENT"):
        assert again._turn is None and isinstance(obj._turn, _Turn)


def _probe_schema(mixin: bool):
    class Probe(*((SwitchStateMixin,) if mixin else ()), BaseModel):
        """A switch state."""
        _FILL_DEFAULTS: ClassVar = True
        enabled: bool = True
        mode: str = "a"
        counters: dict[str, float] = Field(default_factory=dict)
        _turn: object | None = PrivateAttr(default=None)
    return Probe


def test_mixin_adds_no_field_private_or_schema():
    plain, mixed = _probe_schema(False), _probe_schema(True)
    assert mixed.model_json_schema() == plain.model_json_schema()
    assert list(mixed.model_fields) == list(plain.model_fields)
    assert list(mixed.__private_attributes__) == list(plain.__private_attributes__) == ["_turn"]
    assert mixed.__qualname__ == plain.__qualname__ and mixed.__module__ == plain.__module__
    assert pickle.dumps(mixed().__getstate__()) == pickle.dumps(plain().__getstate__())


def test_mixin_options_are_class_variables_and_validated():
    class Unannotated(SwitchStateMixin, BaseModel):
        _FILL_DEFAULTS = True
        _TRANSIENT = ("_turn",)
        _turn: object = PrivateAttr(default=None)
    assert list(Unannotated.__private_attributes__) == ["_turn"]
    assert Unannotated._FILL_DEFAULTS is True

    with pytest.raises(TypeError, match="unknown"):
        class BadFill(SwitchStateMixin, BaseModel):
            _FILL_DEFAULTS: ClassVar = ("missing",)
    with pytest.raises(TypeError, match="unknown"):
        class BadTransient(SwitchStateMixin, BaseModel):
            _TRANSIENT: ClassVar = ("_missing",)
    with pytest.raises(TypeError, match="unknown"):
        class BadBump(SwitchStateMixin, BaseModel):
            _BUMP: ClassVar = {"label": "x"}
    with pytest.raises(TypeError, match="unknown"):
        class BadPrivate(SwitchStateMixin, BaseModel):
            _FILL_PRIVATE: ClassVar = ("_missing",)


def test_mixin_over_record_base_keeps_its_restore(monkeypatch):
    class Rec(SwitchStateMixin, _Record):
        _TRANSIENT: ClassVar = ("_turn",)
        a: int = 1
        b: list = Field(default_factory=list)
        _turn: object = PrivateAttr(default=None)

    obj = Rec(a=2)
    obj._turn = _Turn()
    again = _round_trip(obj, monkeypatch)
    assert again.a == 2 and again._turn is None
    old = Rec.__new__(Rec)
    old.__setstate__({"__dict__": {"a": 3}, "__pydantic_extra__": None,
                      "__pydantic_fields_set__": {"a"}, "__pydantic_private__": None})
    assert list(old.__dict__.items()) == [("a", 3), ("b", [])]   # _Record's own fill ran


def test_mixin_over_lazy_research_model_keeps_lazy_payload(monkeypatch):
    def make(mixin):
        class Lazy(*((SwitchStateMixin,) if mixin else ()), LazyResearchModel):
            lazy_name = "probe_identity"
            lazy_backing = "_probe_identity"
            lazy_payload = int
            counters: dict[str, float] = Field(default_factory=dict)
            last_turn: int | None = None

            if not mixin:
                def __setstate__(self, state):
                    super().__setstate__(state)
                    self.__dict__.setdefault("last_turn", None)
            else:
                _FILL_DEFAULTS: ClassVar = ("last_turn",)
        return Lazy

    plain, mixed = make(False), make(True)
    assert mixed.model_json_schema() == plain.model_json_schema()
    for cls in (plain, mixed):
        obj = cls.model_validate({"probe_identity": 3, "counters": {"a": 1.0}})
        again = _round_trip(obj, monkeypatch)
        assert again.model_dump() == {"counters": {"a": 1.0}, "last_turn": None, "probe_identity": 3}
        stale = cls.__new__(cls)
        stale.__setstate__({"__dict__": {"counters": {}, "_probe_identity": 4}, "__pydantic_extra__": None,
                            "__pydantic_fields_set__": set(), "__pydantic_private__": None})
        assert list(stale.__dict__) == ["counters", "_probe_identity", "last_turn"]
        assert stale.model_dump()["probe_identity"] == 4
