#!/usr/bin/env python3
"""Golden pickles of the switch-state classes (CON-2).

``dump DIR``
    For every pydantic class from a ``chronicler.*_state`` module that is a
    field of ``WorldState`` or ``LivelihoodsState`` (and every nested class of
    such a module reached from them whose own bases define
    ``__setstate__``/``__getstate__``), write pickles made with the exact
    checkpoint pickler (``run_checkpoint._Pickler``) and one JSON record:

    - ``populated``: defaults (required fields synthesized from their
      annotations) plus two counter writes by direct dict assignment;
    - ``transient``: the same with every private attribute holding a marker
      (shows what ``__getstate__`` clears or refuses);
    - ``old``: the populated state with every non-required field and every
      private attribute removed, as a pickle written before they existed;
    - ``partial``: the last non-required field removed and an empty private
      dict.

    The record holds ``model_json_schema()``'s digest, each pickle's digest,
    what loading it with the checkpoint unpickler yields (``__dict__`` keys,
    fields set, ``model_dump()``, ``__pydantic_private__``) and the digest of
    re-pickling the loaded object. ``_index.json`` holds the class list and
    ``WorldState.model_json_schema()``'s digest (as ``checkpoint_replay``).

``check DIR``
    Rebuild and re-pickle every class and load every stored pickle with the
    current source; any difference from the stored records fails (exit 1).

Both run under ``PYTHONHASHSEED=0`` (re-executing if needed): a pickled set's
item order follows string hashes. ``check(directory, bytes_exact=False)``
(the test) compares bytes only for pickles without set items.
"""
from __future__ import annotations

import argparse
import collections.abc
import copyreg
import enum
import hashlib
import io
import json
import math
import os
from pathlib import Path
import pickletools
import re
import sys
import types
import typing
import warnings

INDEX = "_index.json"
VARIANTS = ("populated", "transient", "old", "partial")
COUNTER_FIELDS = ("counters", "totals", "counts")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------------------
# Classes
# ---------------------------------------------------------------------------

def _is_state_module(cls) -> bool:
    return re.fullmatch(r"chronicler\.\w+_state", cls.__module__) is not None


def _models_in(annotation, out: list) -> list:
    from pydantic import BaseModel
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        if annotation not in out:
            out.append(annotation)
        return out
    for arg in typing.get_args(annotation):
        _models_in(arg, out)
    return out


def _has_hooks(cls) -> bool:
    from pydantic import BaseModel
    return any(name in base.__dict__
               for base in cls.__mro__ if base not in (BaseModel, object)
               for name in ("__setstate__", "__getstate__"))


def state_classes() -> list[type]:
    from chronicler.livelihoods_state import LivelihoodsState
    from chronicler.models import WorldState
    roots: list[type] = []
    for owner in (WorldState, LivelihoodsState):
        for field in owner.model_fields.values():
            for cls in _models_in(field.annotation, []):
                if _is_state_module(cls) and cls not in roots:
                    roots.append(cls)
    out, queue, seen = list(roots), list(roots), set(roots)
    while queue:
        cls = queue.pop(0)
        for field in cls.model_fields.values():
            for sub in _models_in(field.annotation, []):
                if sub in seen or not _is_state_module(sub):
                    continue
                seen.add(sub)
                queue.append(sub)
                if _has_hooks(sub):
                    out.append(sub)
    return out


def class_key(cls) -> str:
    return f"{cls.__module__.removeprefix('chronicler.')}.{cls.__qualname__}"


# ---------------------------------------------------------------------------
# Instances
# ---------------------------------------------------------------------------

class Unbuildable(Exception):
    pass


def _synth(annotation):
    from pydantic import BaseModel
    origin, args = typing.get_origin(annotation), typing.get_args(annotation)
    if annotation is None or annotation is type(None):
        return None
    if origin is typing.Annotated:
        return _synth(args[0])
    if origin in (typing.Union, types.UnionType):
        return None if type(None) in args else _synth(args[0])
    if origin is typing.Literal:
        return args[0]
    if origin in (list, collections.abc.Sequence, collections.abc.MutableSequence):
        return []
    if origin is tuple:
        if len(args) == 2 and args[1] is Ellipsis:
            return ()
        return tuple(_synth(arg) for arg in args)
    if origin in (dict, collections.abc.Mapping, collections.abc.MutableMapping):
        return {}
    if origin in (set, frozenset):
        return origin()
    if isinstance(annotation, type):
        if issubclass(annotation, BaseModel):
            return build(annotation, populate=False)
        if issubclass(annotation, enum.Enum):
            return next(iter(annotation))
        for kind, value in ((bool, False), (int, 1), (float, 0.5), (str, "probe"), (bytes, b"")):
            if annotation is kind:
                return value
        if annotation in (list, dict, set, frozenset, tuple):
            return annotation()
    if annotation is typing.Any or annotation is object:
        return None
    raise Unbuildable(f"cannot synthesize {annotation!r}")


def _counter_values(annotation) -> tuple[type, ...]:
    args = typing.get_args(annotation)
    if typing.get_origin(annotation) in (typing.Union, types.UnionType):
        for arg in args:
            if typing.get_origin(arg) is dict:
                return _counter_values(arg)
        return (int, float)
    key = args[0] if args else str
    value = args[1] if len(args) > 1 else typing.Any
    kinds = [kind for kind in (int, float) if kind in (typing.get_args(value) or (value,))]
    return (key, *(kinds or (int, float)))


def _populate(obj) -> None:
    fields = type(obj).model_fields
    for name in COUNTER_FIELDS:
        counters = obj.__dict__.get(name) if name in fields else None
        if not isinstance(counters, dict):
            continue
        key_type, *kinds = _counter_values(fields[name].annotation)
        first, second = kinds[0], kinds[-1]
        probe = (lambda n: 900000 + n) if key_type is int else (lambda n: f"switch_state_probe_{n}")
        if counters:
            k0 = next(iter(counters))
            counters[k0] = counters[k0] + first(1)
        else:
            counters[probe(1)] = first(1)
        counters[probe(2)] = second(2) if second is int else 2.5


def build(cls, *, populate: bool = True):
    values = {}
    for name, field in cls.model_fields.items():
        if field.is_required():
            values[field.alias or name] = _synth(field.annotation)
    try:
        obj = cls(**values)
    except Exception as exc:  # a validator refused the synthesized values
        raise Unbuildable(f"{type(exc).__name__}: {exc}") from exc
    if populate:
        _populate(obj)
    return obj


def _private_names(cls) -> list[str]:
    return list(getattr(cls, "__private_attributes__", {}) or {})


def _stub_state(obj, variant: str) -> dict:
    cls = type(obj)
    optional = [name for name, field in cls.model_fields.items() if not field.is_required()]
    if variant == "old":
        drop, private = set(optional), None
    else:
        present = [name for name in obj.__dict__ if name in optional]
        drop = {present[-1]} if present else set()
        private = {} if _private_names(cls) else None
    return {
        "__dict__": {k: v for k, v in obj.__dict__.items() if k not in drop},
        "__pydantic_extra__": obj.__pydantic_extra__,
        "__pydantic_fields_set__": set(obj.__pydantic_fields_set__) - drop,
        "__pydantic_private__": private,
    }


def variant_bytes(cls) -> dict[str, bytes | str]:
    """Pickle bytes (or the refusal) of every variant applicable to ``cls``."""
    out: dict[str, bytes | str] = {}
    out["populated"] = _dumps(build(cls))
    names = _private_names(cls)
    if names:
        obj = build(cls)
        for name in names:
            obj.__pydantic_private__[name] = f"probe:{name}"
        try:
            out["transient"] = _dumps(obj)
        except Exception as exc:
            out["transient"] = f"{type(exc).__name__}: {exc}"
    obj = build(cls)
    out["old"] = _dumps(obj, state=_stub_state(obj, "old"))
    partial = _stub_state(obj, "partial")
    if partial["__pydantic_private__"] is not None or len(partial["__dict__"]) < len(obj.__dict__):
        out["partial"] = _dumps(obj, state=partial)
    return out


# ---------------------------------------------------------------------------
# Pickling
# ---------------------------------------------------------------------------

def _pickler_class():
    from chronicler.run_checkpoint import _Pickler

    class Pickler(_Pickler):
        """The checkpoint pickler; ``target`` pickles with a given state."""

        target = None
        target_state = None

        def reducer_override(self, obj):
            if obj is self.target:
                # Exactly object.__reduce_ex__'s shape, with another state.
                return copyreg.__newobj__, (type(obj),), self.target_state, None, None
            return NotImplemented

    return Pickler


def _dumps(obj, *, state=None) -> bytes:
    buf = io.BytesIO()
    pickler = _pickler_class()(buf)
    if state is not None:
        pickler.target, pickler.target_state = obj, state
    pickler.dump(obj)
    return buf.getvalue()


def _loads(data: bytes):
    from chronicler.run_checkpoint import _Unpickler
    return _Unpickler(io.BytesIO(data)).load()


def hash_order_free(data: bytes) -> bool:
    """No set or frozenset items: the bytes do not depend on the hash seed."""
    return not any(op.name in ("ADDITEMS", "FROZENSET") for op, _arg, _pos in pickletools.genops(data))


# ---------------------------------------------------------------------------
# Records
# ---------------------------------------------------------------------------

def canon(value):
    """JSON form that keeps int/float, tuple/list, key order and set content."""
    from pydantic import BaseModel
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else {"__float__": repr(value)}
    if isinstance(value, (list, tuple)):
        items = [canon(v) for v in value]
        return items if isinstance(value, list) else {"__tuple__": items}
    if isinstance(value, (set, frozenset)):
        return {"__set__": sorted((canon(v) for v in value), key=lambda v: json.dumps(v, sort_keys=True))}
    if isinstance(value, dict):
        if all(isinstance(k, str) and not k.startswith("__") for k in value):
            return {k: canon(v) for k, v in value.items()}
        return {"__map__": [[canon(k), canon(v)] for k, v in value.items()]}
    if isinstance(value, BaseModel):
        return {"__model__": class_key(type(value)), "dump": _dump(value)}
    if isinstance(value, enum.Enum):
        return {"__enum__": f"{type(value).__qualname__}.{value.name}"}
    if isinstance(value, bytes):
        return {"__bytes__": value.hex()}
    return {"__object__": f"{type(value).__module__}.{type(value).__qualname__}"}


def _error(exc: BaseException) -> dict:
    return {"error": f"{type(exc).__name__}: {exc}"}


def _dump(obj):
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        try:
            dump = canon(obj.model_dump())
        except Exception as exc:
            dump = _error(exc)
    if caught:
        return {"dump": dump, "warnings": [str(w.message) for w in caught]}
    return dump


def describe(obj) -> dict:
    try:
        private = canon(object.__getattribute__(obj, "__pydantic_private__"))
    except AttributeError:
        private = "<absent>"
    return {
        "type": class_key(type(obj)),
        "dict_keys": list(obj.__dict__),
        "fields_set": sorted(obj.__pydantic_fields_set__),
        "extra": canon(obj.__pydantic_extra__),
        "private": private,
        "dump": _dump(obj),
    }


def _schema_digest(cls) -> str | dict:
    from chronicler.checkpoint_replay import _digest
    try:
        return _digest(cls.model_json_schema())
    except Exception as exc:
        return _error(exc)


def _loaded(data: bytes) -> dict:
    try:
        obj = _loads(data)
    except Exception as exc:
        return {"load": _error(exc)}
    record = {"loaded": describe(obj)}
    try:
        again = _dumps(obj)
    except Exception as exc:
        record["repickle"] = _error(exc)
    else:
        record["repickle_sha256"] = _sha(again)
        record["repickle_hash_order_free"] = hash_order_free(again)
    return record


def class_record(cls, blobs: dict[str, bytes | str]) -> dict:
    record = {"class": class_key(cls), "schema_sha256": _schema_digest(cls), "variants": {}}
    for variant, blob in blobs.items():
        if isinstance(blob, str):
            record["variants"][variant] = {"pickle_error": blob}
            continue
        record["variants"][variant] = {
            "pickle": f"{class_key(cls)}.{variant}.pkl",
            "sha256": _sha(blob),
            "hash_order_free": hash_order_free(blob),
            **_loaded(blob),
        }
    return record


def _versions() -> dict:
    import pydantic
    return {"python": ".".join(map(str, sys.version_info[:2])), "pydantic": pydantic.VERSION}


def _world_schema() -> str:
    from chronicler.checkpoint_replay import _schema_digest as world_schema_digest
    return world_schema_digest()


def dump(directory: Path) -> int:
    directory.mkdir(parents=True, exist_ok=True)
    for stale in [*directory.glob("*.pkl"), *directory.glob("*.json")]:
        stale.unlink()
    classes, skipped = [], {}
    for cls in state_classes():
        try:
            blobs = variant_bytes(cls)
        except Unbuildable as exc:
            skipped[class_key(cls)] = str(exc)
            continue
        classes.append(class_key(cls))
        for variant, blob in blobs.items():
            if isinstance(blob, bytes):
                (directory / f"{class_key(cls)}.{variant}.pkl").write_bytes(blob)
        _write_json(directory / f"{class_key(cls)}.json", class_record(cls, blobs))
    _write_json(directory / INDEX, {"world_schema_sha256": _world_schema(), "versions": _versions(),
                                    "classes": classes, "skipped": skipped})
    print(f"wrote {len(classes)} classes to {directory} ({len(skipped)} skipped)")
    return 0


def _write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


def check(directory: Path, *, bytes_exact: bool = True) -> list[str]:
    """Differences between the stored corpus and the current source."""
    problems: list[str] = []
    index = json.loads((directory / INDEX).read_text(encoding="utf-8"))
    if _world_schema() != index["world_schema_sha256"]:
        problems.append("WorldState.model_json_schema() digest changed")
    by_key = {class_key(cls): cls for cls in state_classes()}
    expected = list(index["classes"]) + list(index["skipped"])
    if sorted(by_key) != sorted(expected):
        problems.append(f"class list changed: added {sorted(set(by_key) - set(expected))}, "
                        f"removed {sorted(set(expected) - set(by_key))}")
    for key in index["classes"]:
        cls = by_key.get(key)
        if cls is None:
            continue
        stored = json.loads((directory / f"{key}.json").read_text(encoding="utf-8"))
        try:
            blobs = variant_bytes(cls)
        except Unbuildable as exc:
            problems.append(f"{key}: no longer buildable: {exc}")
            continue
        if _schema_digest(cls) != stored["schema_sha256"]:
            problems.append(f"{key}: model_json_schema() digest changed")
        if sorted(blobs) != sorted(stored["variants"]):
            problems.append(f"{key}: variants {sorted(blobs)} != stored {sorted(stored['variants'])}")
        for variant, want in stored["variants"].items():
            label = f"{key} [{variant}]"
            blob = blobs.get(variant)
            if "pickle_error" in want:
                if blob != want["pickle_error"]:
                    problems.append(f"{label}: pickling no longer refuses with {want['pickle_error']!r}")
                continue
            data = (directory / want["pickle"]).read_bytes()
            if _sha(data) != want["sha256"]:
                problems.append(f"{label}: stored pickle does not match its record")
                continue
            exact = bytes_exact or want["hash_order_free"]
            if not isinstance(blob, bytes):
                problems.append(f"{label}: pickling now fails: {blob}")
            elif exact and blob != data:
                problems.append(f"{label}: pickling the rebuilt object gives other bytes")
            got = _loaded(data)
            if got.get("load") != want.get("load"):
                problems.append(f"{label}: loading differs: {got.get('load')} != {want.get('load')}")
            if got.get("loaded") != want.get("loaded"):
                problems.append(f"{label}: the loaded object differs")
            if got.get("repickle") != want.get("repickle"):
                problems.append(f"{label}: re-pickling differs: {got.get('repickle')} != {want.get('repickle')}")
            if bytes_exact or want.get("repickle_hash_order_free", False):
                if got.get("repickle_sha256") != want.get("repickle_sha256"):
                    problems.append(f"{label}: re-pickled bytes differ")
    return problems


def _require_seed_zero() -> None:
    if os.environ.get("PYTHONHASHSEED") != "0":
        env = {**os.environ, "PYTHONHASHSEED": "0"}
        os.execve(sys.executable, [sys.executable, *sys.argv], env)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("dump", "check"):
        sub.add_parser(name).add_argument("directory", type=Path)
    args = parser.parse_args(argv)
    _require_seed_zero()
    if args.command == "dump":
        return dump(args.directory)
    problems = check(args.directory)
    for problem in problems:
        print(problem)
    index = json.loads((args.directory / INDEX).read_text(encoding="utf-8"))
    if index["versions"] != _versions():
        print(f"note: corpus written with {index['versions']}, checked with {_versions()}")
    print(f"{'FAIL' if problems else 'PASS'}: {len(index['classes'])} classes, {len(problems)} differences")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
