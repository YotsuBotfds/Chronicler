"""Bundle version 6: the history is written as changes between snapshots.

Most of a history snapshot repeats the one before it: the civ rows, the
pairwise tables and the per-system summaries change in a few fields a turn.
A version-6 ``chronicle_bundle.json`` stays plain JSON with two changes:

* ``history_delta`` replaces ``history``. Its first item is the first
  snapshot; each later item is a patch against the snapshot before it.
* ``world_state.events_timeline`` and ``world_state.named_events`` are
  ``null`` when they equal the top-level ``events_timeline`` and
  ``named_events`` (the simulation writes the same lists to both).

:func:`decode_bundle` rebuilds the bundle as version 5 laid it out: the same
values, number types and key order, with ``metadata.bundle_version`` 6.
Bundles of earlier versions (and decoded ones) are returned as they are.

A patch turns a value ``a`` (the previous snapshot's) into ``b``:

* An object patch against an object lists only the keys whose values
  changed or are new, each holding a patch against the old value (a new key
  holds its value). ``"~d"`` lists removed keys. Kept keys keep their order and
  new keys follow; ``"~o"`` gives the full key order when that differs.
* A list patch against a list is ``{"~l": [[index, patch], ...]}`` for the
  changed items, with ``"~t"`` (items appended) or ``"~n"`` (the new, shorter
  length). A list that is cheaper to write whole is written whole.
* ``{"~r": value}`` stands for ``value`` itself; it is written where a
  literal object would read as a patch (a list replaced by an object).
* Anything else is the new value.

Data keys never start with ``~`` in these fields; the encoder checks, and a
history that holds one of the reserved keys is written whole as ``history``.

Decoding checks every patch against that format and raises
:class:`BundleDecodeError` (a ``ValueError``) naming the snapshot and the
problem, rather than failing inside a patch or returning a wrong history.
"""
from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

BUNDLE_VERSION = 6
HISTORY_DELTA_KEY = "history_delta"
#: ``world_state`` fields that repeat a top-level field of the same name.
SHARED_WORLD_FIELDS = ("events_timeline", "named_events")

_DEL = "~d"
_ORDER = "~o"
_REPLACE = "~r"
_LIST = "~l"
_TAIL = "~t"
_LEN = "~n"
RESERVED_KEYS = frozenset({_DEL, _ORDER, _REPLACE, _LIST, _TAIL, _LEN})


class _ReservedKey(Exception):
    pass


class BundleDecodeError(ValueError):
    """A version-6 bundle whose ``history_delta`` does not follow the patch format."""


def _dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def same(a: Any, b: Any) -> bool:
    """JSON equality that keeps number types, key order and the sign of zero."""
    if a is b:
        return True
    kind = type(a)
    if kind is not type(b):
        return False
    if kind is dict:
        if len(a) != len(b):
            return False
        for (ka, va), (kb, vb) in zip(a.items(), b.items()):
            if ka != kb or not same(va, vb):
                return False
        return True
    if kind is list:
        return len(a) == len(b) and all(same(x, y) for x, y in zip(a, b))
    if kind is float:
        if a != b:
            return a != a and b != b  # NaN
        return a != 0.0 or str(a) == str(b)
    return a == b


def _check_keys(value: Any) -> None:
    """Raise when a literal holds a reserved key at any depth."""
    if type(value) is dict:
        for key, item in value.items():
            if key in RESERVED_KEYS:
                raise _ReservedKey(key)
            _check_keys(item)
    elif type(value) is list:
        for item in value:
            _check_keys(item)


def _literal(value: Any) -> Any:
    _check_keys(value)
    return value


def _key(key: Any) -> str:
    """A dict key as JSON writes it (the decoder sees only strings)."""
    if isinstance(key, str):
        return key
    return next(iter(json.loads(_dumps({key: 0}))))


def _diff(a: Any, b: Any) -> Any:
    """The patch turning ``a`` into ``b``."""
    if type(a) is dict and type(b) is dict:
        return _diff_dict(a, b)
    if type(a) is list and type(b) is list:
        return _diff_list(a, b)
    if type(a) is list and type(b) is dict:
        return {_REPLACE: _literal(b)}
    return _literal(b)


def _diff_dict(a: dict, b: dict) -> dict:
    patch: dict[str, Any] = {}
    for key, value in b.items():
        if key in RESERVED_KEYS:
            raise _ReservedKey(key)
        if key in a:
            old = a[key]
            if not same(old, value):
                patch[key] = _diff(old, value)
        else:
            patch[key] = _literal(value)
    if len(a) != len(b) or list(a) != list(b):
        deleted = [_key(key) for key in a if key not in b]
        if deleted:
            patch[_DEL] = deleted
        order = [key for key in a if key in b] + [key for key in b if key not in a]
        if order != list(b):
            patch[_ORDER] = [_key(key) for key in b]
    return patch


def _diff_list(a: list, b: list) -> Any:
    shared = min(len(a), len(b))
    changes = [[i, _diff(a[i], b[i])] for i in range(shared) if not same(a[i], b[i])]
    patch: dict[str, Any] = {_LIST: changes}
    if len(b) > shared:
        patch[_TAIL] = _literal(b[shared:])
    elif len(a) > shared:
        patch[_LEN] = len(b)
    if len(_dumps(patch)) < len(_dumps(b)):
        return patch
    return _literal(b)


def _is_int(value: Any) -> bool:
    return type(value) is int


def _apply(a: Any, patch: Any) -> Any:
    if type(patch) is dict:
        if _REPLACE in patch:
            if len(patch) != 1:
                raise BundleDecodeError(f"'{_REPLACE}' patch with other keys: {sorted(patch)}")
            return patch[_REPLACE]
        if type(a) is dict:
            return _apply_dict(a, patch)
        if type(a) is list:
            return _apply_list(a, patch)
        reserved = sorted(key for key in patch if key in RESERVED_KEYS)
        if reserved:
            raise BundleDecodeError(f"patch {reserved} against a {type(a).__name__}")
    return patch


def _apply_dict(a: dict, patch: dict) -> dict:
    unexpected = sorted(key for key in patch if key in RESERVED_KEYS and key not in (_DEL, _ORDER))
    if unexpected:
        raise BundleDecodeError(f"object patch holds list keys {unexpected}")
    deleted = patch.get(_DEL)
    if deleted is not None and (type(deleted) is not list
                                or any(type(k) is not str or k not in a for k in deleted)):
        raise BundleDecodeError(f"'{_DEL}' must list existing keys, got {deleted!r}")
    removed = set(deleted) if deleted else ()
    out: dict[str, Any] = {}
    for key, value in a.items():
        if key in removed:
            continue
        out[key] = _apply(value, patch[key]) if key in patch else value
    for key, value in patch.items():
        if key not in a and key not in RESERVED_KEYS:
            out[key] = value
    order = patch.get(_ORDER)
    if order is not None:
        if (type(order) is not list or len(order) != len(out)
                or any(type(k) is not str for k in order) or set(order) != set(out)):
            raise BundleDecodeError(f"'{_ORDER}' must list the object's keys once each, got {order!r}")
        out = {key: out[key] for key in order}
    return out


def _apply_list(a: list, patch: dict) -> list:
    unexpected = sorted(key for key in patch if key not in (_LIST, _TAIL, _LEN))
    if unexpected or _LIST not in patch:
        raise BundleDecodeError(f"list patch needs '{_LIST}' and only list keys, got {sorted(patch)}")
    out = list(a)
    length = patch.get(_LEN)
    if length is not None:
        if not _is_int(length) or not 0 <= length <= len(out):
            raise BundleDecodeError(f"'{_LEN}' must be a length up to {len(out)}, got {length!r}")
        del out[length:]
    changes = patch[_LIST]
    if type(changes) is not list:
        raise BundleDecodeError(f"'{_LIST}' must be a list, got {type(changes).__name__}")
    for change in changes:
        if type(change) is not list or len(change) != 2 or not _is_int(change[0]) \
                or not 0 <= change[0] < len(out):
            raise BundleDecodeError(f"'{_LIST}' item must be [index < {len(out)}, patch], got {change!r}")
        index, item = change
        out[index] = _apply(out[index], item)
    tail = patch.get(_TAIL)
    if tail is not None and type(tail) is not list:
        raise BundleDecodeError(f"'{_TAIL}' must be a list, got {type(tail).__name__}")
    if tail:
        out.extend(tail)
    return out


def encode_history(snapshots: Iterable[Any]) -> list[Any] | None:
    """The ``history_delta`` of a serialized history, or None when a snapshot
    holds a reserved key (the history is then written whole)."""
    out: list[Any] = []
    prev: Any = None
    try:
        for index, snapshot in enumerate(snapshots):
            # Two equal snapshot dicts give the empty patch.
            out.append(_literal(snapshot) if index == 0 else _diff(prev, snapshot))
            prev = snapshot
    except _ReservedKey:
        return None
    return out


def decode_history(encoded: list[Any]) -> list[Any]:
    """The serialized history of a ``history_delta``.

    Each snapshot is an independent JSON tree, as ``json.loads`` of a
    version-5 bundle gives. Raises :class:`BundleDecodeError` for a patch
    that does not follow the format.
    """
    if type(encoded) is not list:
        raise BundleDecodeError(f"{HISTORY_DELTA_KEY} must be a list, got {type(encoded).__name__}")
    shared: list[Any] = []
    prev: Any = None
    for index, item in enumerate(encoded):
        try:
            prev = item if index == 0 else _apply(prev, item)
        except BundleDecodeError as exc:
            raise BundleDecodeError(f"{HISTORY_DELTA_KEY}[{index}]: {exc}") from None
        if type(prev) is not dict:
            raise BundleDecodeError(
                f"{HISTORY_DELTA_KEY}[{index}]: a snapshot must be an object, got {type(prev).__name__}")
        shared.append(prev)
    # Consecutive snapshots share their unchanged values; copy them apart so a
    # reader that edits one snapshot does not edit its neighbours.
    return json.loads(_dumps(shared))


def is_encoded(bundle: Any) -> bool:
    """Whether a bundle dict is in the version-6 file layout."""
    if not isinstance(bundle, Mapping):
        return False
    if HISTORY_DELTA_KEY in bundle:
        return True
    world = bundle.get("world_state")
    return isinstance(world, Mapping) and any(
        key in world and world[key] is None and key in bundle for key in SHARED_WORLD_FIELDS
    )


def encode_bundle(bundle: Mapping[str, Any]) -> dict[str, Any]:
    """The version-6 file layout of an assembled (decoded) bundle.

    Returns a shallow copy; the input is not changed. Values are shared with
    the input, so write the result before editing the input.
    """
    out: dict[str, Any] = {}
    for key, value in bundle.items():
        if key == "history" and isinstance(value, list):
            encoded = encode_history(value)
            if encoded is not None:
                out[HISTORY_DELTA_KEY] = encoded
                continue
        if key == "world_state" and isinstance(value, Mapping):
            world = dict(value)
            for field in SHARED_WORLD_FIELDS:
                if field in world and field in bundle and world[field] is not None \
                        and same(world[field], bundle[field]):
                    world[field] = None
            value = world
        out[key] = value
    return out


def decode_bundle(bundle: Any) -> Any:
    """A version-6 file layout back as an assembled bundle (version-5 layout).

    Bundles that are not encoded (earlier versions, or already decoded) and
    anything that is not a bundle are returned as they are. Otherwise a new
    dict is returned; ``metadata`` keeps the bundle version. A malformed
    ``history_delta`` raises :class:`BundleDecodeError`.
    """
    if not is_encoded(bundle):
        return bundle
    out: dict[str, Any] = {}
    for key, value in bundle.items():
        if key == HISTORY_DELTA_KEY:
            out["history"] = decode_history(value)
        elif key == "world_state" and isinstance(value, Mapping):
            world = dict(value)
            for field in SHARED_WORLD_FIELDS:
                if field in world and world[field] is None and field in bundle:
                    world[field] = json.loads(_dumps(bundle[field]))
            out[key] = world
        else:
            out[key] = value
    return out


def load_bundle(path: str | Path) -> Any:
    """Read a ``chronicle_bundle.json`` of any version, decoded."""
    return decode_bundle(json.loads(Path(path).read_text(encoding="utf-8")))


def dumps_bundle(bundle: Mapping[str, Any]) -> str:
    """The text :func:`chronicler.bundle.write_bundle` writes for a bundle."""
    return _dumps(encode_bundle(bundle))
