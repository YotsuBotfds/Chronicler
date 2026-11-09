"""Shared switch-state helpers: one mixin for the ``*_state.py`` pickle hooks
and the counter, lane and sub-state helpers their owner modules copy.

Behaviour-preserving by construction (CON-2): every option reproduces one of
the hand-written forms it replaces, and the defaults reproduce no hook at all.

- ``bump_counter`` encodes the ``_bump`` variants (strict or lax key check,
  ``int`` coercion, rounding, zero skip, a ``0.0`` start).
- ``SwitchStateMixin`` is a plain, field-free class listed FIRST in a model's
  bases: ``class X(SwitchStateMixin, BaseModel)``. It adds no annotation,
  field or private attribute, so ``model_json_schema()``, the pickle payload
  and the class path stay as they were. Its options are class variables
  declared ``ClassVar`` here, which pydantic carries to subclasses (an
  underscore name it did not know as a class variable would become a
  private attribute; the mixin refuses such a class).

This module imports no other chronicler module at top level.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable, Mapping
from importlib import import_module
from types import MappingProxyType
from typing import Any, ClassVar

__all__ = [
    "SwitchStateMixin",
    "bump_counter",
    "controller_index",
    "health_holders",
    "lane_active",
    "sub_state_getter",
]


def bump_counter(counters: dict, key, amount=1, *, allowed=None, message: str | None = None,
                 coerce: Callable[[Any], Any] | None = None, ndigits: int | None = None,
                 zero=0, skip_zero: bool = False, float_only_round: bool = False) -> None:
    """Add ``amount`` to ``counters[key]`` (starting from ``zero``).

    ``allowed``: the declared keys; another key raises ``KeyError`` with
    ``message.format(key=key)`` (or the bare key) before anything else.
    ``skip_zero``: a falsy amount writes nothing. ``coerce``: applied to the
    amount (``int`` for the integer counters). ``ndigits``: round the sum;
    with ``float_only_round`` only a float sum is rounded (an int stays int).
    """
    if allowed is not None and key not in allowed:
        raise KeyError(message.format(key=key) if message else key)
    if skip_zero and not amount:
        return
    if coerce is not None:
        amount = coerce(amount)
    value = counters.get(key, zero) + amount
    if ndigits is not None and (not float_only_round or isinstance(value, float)):
        value = round(value, ndigits)
    counters[key] = value


_BUMP_OPTIONS = frozenset(
    name for name, p in inspect.signature(bump_counter).parameters.items()
    if p.kind is inspect.Parameter.KEYWORD_ONLY
)


def lane_active(world, name: str) -> bool:
    """A livelihoods switch is present and active (never imports its module
    for a world that never enabled it)."""
    if getattr(getattr(world, "livelihoods", None), name, None) is None:
        return False
    return bool(getattr(import_module("chronicler." + name), f"{name}_active")(world))


def sub_state_getter(name: str) -> Callable[[Any], Any]:
    """``world.livelihoods.<name>``, or None when either is absent."""
    def _state(world):
        return getattr(getattr(world, "livelihoods", None), name, None)
    _state.__qualname__ = f"sub_state_getter({name!r})"
    return _state


def controller_index(world, rid: int) -> int:
    """The controlling civilization's index through ``world.civ_index_map``,
    -1 for no controller or an unknown name (commons_rules, clearing_protection).

    Not the scan form (``timber_orders._controller``: first civilization of
    that name): with duplicate names the map holds the last index, and its
    cache is rebuilt only when the civilization count changes.
    """
    name = world.regions[rid].controller
    if name is None:
        return -1
    return world.civ_index_map.get(name, -1)


def health_holders(world) -> set[int]:
    """Patients and carers of this turn's prepared rural health work."""
    health = getattr(world, "health_care", None)
    rows = getattr(health, "_prepared", None) if health is not None else None
    out: set[int] = set()
    for aid, _region, giver, care in rows or ():
        out.add(int(aid))
        if int(giver) and float(care) > 0:
            out.add(int(giver))
    return out


_OPTIONS = ("_FILL_DEFAULTS", "_FILL_PRIVATE", "_TRANSIENT", "_BUMP")


class SwitchStateMixin:
    """Pickle hooks and ``bump`` for a pydantic switch state.

    ``_FILL_DEFAULTS``: on unpickling, give each missing field its declared
    default (``True``: every field in declaration order; a tuple: those
    names; ``False``: none, as pydantic's own restore does).
    ``_FILL_PRIVATE``: likewise for private attributes (``True``: all, a
    tuple: those names); a missing ``__pydantic_private__`` becomes a dict
    holding exactly those names.
    ``_TRANSIENT``: private attributes pickled as None; the state is copied
    only when one of them holds a value, so the live object is never touched.
    ``_BUMP``: the keyword options of ``bump_counter`` for ``self.bump``.
    """

    __slots__ = ()

    _FILL_DEFAULTS: ClassVar[bool | tuple[str, ...]] = False
    _FILL_PRIVATE: ClassVar[bool | tuple[str, ...]] = False
    _TRANSIENT: ClassVar[tuple[str, ...]] = ()
    _BUMP: ClassVar[Mapping[str, Any]] = MappingProxyType({})

    @classmethod
    def __pydantic_init_subclass__(cls, **kwargs):
        super().__pydantic_init_subclass__(**kwargs)
        private = getattr(cls, "__private_attributes__", {})
        leaked = [name for name in _OPTIONS if name in private]
        if leaked:
            raise TypeError(f"{cls.__qualname__}: annotate {', '.join(leaked)} with ClassVar")
        fields = cls.model_fields
        for option, known in (("_FILL_DEFAULTS", fields), ("_FILL_PRIVATE", private)):
            value = getattr(cls, option)
            if not isinstance(value, bool):
                unknown = [name for name in value if name not in known]
                if unknown:
                    raise TypeError(f"{cls.__qualname__}.{option} names unknown {unknown}")
        unknown = [name for name in cls._TRANSIENT if name not in private]
        if unknown:
            raise TypeError(f"{cls.__qualname__}._TRANSIENT names unknown {unknown}")
        unknown = sorted(set(cls._BUMP) - _BUMP_OPTIONS)
        if unknown:
            raise TypeError(f"{cls.__qualname__}._BUMP has unknown options {unknown}")

    def __getstate__(self):
        state = super().__getstate__()
        names = type(self)._TRANSIENT
        if names:
            private = state.get("__pydantic_private__")
            if private and any(private.get(name) is not None for name in names):
                state = {**state, "__pydantic_private__": {**private, **dict.fromkeys(names)}}
        return state

    def __setstate__(self, state):
        super().__setstate__(state)
        cls = type(self)
        fill = cls._FILL_DEFAULTS
        if fill:
            fields = cls.model_fields
            values = self.__dict__
            for name in (fields if fill is True else fill):
                if name not in values:
                    values[name] = fields[name].get_default(call_default_factory=True)
        fill = cls._FILL_PRIVATE
        if fill:
            declared = cls.__private_attributes__
            names = tuple(declared) if fill is True else fill
            private = getattr(self, "__pydantic_private__", None)
            if private is None:
                object.__setattr__(self, "__pydantic_private__",
                                   {name: declared[name].get_default() for name in names})
            else:
                for name in names:
                    if name not in private:
                        private[name] = declared[name].get_default()

    def bump(self, key, amount=1) -> None:
        bump_counter(self.counters, key, amount, **type(self)._BUMP)
