"""Strict JSON and atomic file helpers for validation artifacts."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


class ArtifactIOError(ValueError):
    """Raised when artifact JSON or file IO fails safely."""


def _reject_constant(value: str) -> None:
    raise ArtifactIOError(f"non-finite JSON constant: {value}")


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ArtifactIOError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def strict_json_loads(text: str, *, label: str = "JSON") -> Any:
    """Load JSON while rejecting NaN/Infinity and duplicate object keys."""
    try:
        return json.loads(
            text,
            parse_constant=_reject_constant,
            object_pairs_hook=_reject_duplicate_keys,
        )
    except ArtifactIOError:
        raise
    except json.JSONDecodeError as exc:
        raise ArtifactIOError(f"invalid {label}: {exc}") from exc


def _child_path(path: str, key: str) -> str:
    if path == "<root>":
        return key
    return f"{path}.{key}"


def _validate_json_value(value: Any, *, path: str = "<root>") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if not isinstance(key, str):
                raise ArtifactIOError(f"JSON object keys must be strings at {path}: {key!r}")
            _validate_json_value(child, path=_child_path(path, key))
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            _validate_json_value(child, path=f"{path}[{index}]")


def strict_json_dumps(
    payload: Any,
    *,
    indent: int | None = 2,
    ensure_ascii: bool = True,
    trailing_newline: bool = True,
) -> str:
    """Serialize JSON fully, rejecting ambiguous keys and NaN/Infinity before writes."""
    _validate_json_value(payload)
    try:
        text = json.dumps(payload, indent=indent, ensure_ascii=ensure_ascii, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ArtifactIOError(f"could not serialize JSON: {exc}") from exc
    if trailing_newline:
        text += "\n"
    return text


def atomic_write_text(path: Path, content: str, *, encoding: str = "utf-8") -> None:
    """Atomically replace ``path`` with ``content`` using a same-directory temp file."""
    path = Path(path)
    temp_path: Path | None = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            "w",
            encoding=encoding,
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temp_file:
            temp_path = Path(temp_file.name)
            temp_file.write(content)
            temp_file.flush()
            os.fsync(temp_file.fileno())
        os.replace(temp_path, path)
        temp_path = None
    except OSError as exc:
        raise ArtifactIOError(f"could not write artifact {path}: {exc}") from exc
    finally:
        if temp_path is not None:
            try:
                temp_path.unlink()
            except FileNotFoundError:
                pass
            except OSError:
                pass


def atomic_write_json(
    path: Path,
    payload: Any,
    *,
    indent: int | None = 2,
    ensure_ascii: bool = True,
    trailing_newline: bool = True,
) -> None:
    """Serialize JSON strictly, then atomically replace ``path``."""
    text = strict_json_dumps(
        payload,
        indent=indent,
        ensure_ascii=ensure_ascii,
        trailing_newline=trailing_newline,
    )
    atomic_write_text(path, text)


__all__ = [
    "ArtifactIOError",
    "atomic_write_json",
    "atomic_write_text",
    "strict_json_dumps",
    "strict_json_loads",
]
