"""Opt-in continuation validation for Python off-mode, without narrative clients.

This is separate from production resume: native runtimes and agent pools are
unsupported. Compare persisted simulation state, including the full event log
and explicitly saved focus deltas, at every completed turn; narration/memory/
viewer history are outside this scope.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
from enum import Enum
from importlib.metadata import version
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, StrictInt, TypeAdapter, ValidationError

from chronicler.action_engine import ActionEngine
from chronicler.artifact_io import (
    ArtifactIOError, atomic_write_json, strict_json_dumps, strict_json_loads,
)
from chronicler.batch_manifest import package_digest
from chronicler.models import WorldState
from chronicler.simulation import run_turn
from chronicler.tech_focus import FOCUS_EFFECTS, TechFocus

FORMAT = "chronicler-python-off-checkpoint"
VERSION = 1
RUNTIME = "python-off-v1"
_FOCUS_ADAPTER = TypeAdapter(list[dict[str, dict[str, StrictInt]] | None])


class CheckpointError(ValueError):
    """The checkpoint is invalid or cannot continue in this runtime."""


class _Envelope(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    format: str
    version: StrictInt
    runtime: str
    schema_sha256: str
    runtime_identity: dict[str, str]
    world_sha256: str
    world: dict[str, Any]
    focus_deltas: list[dict[str, dict[str, StrictInt]] | None]
    focus_deltas_sha256: str


def _canonical(value: Any) -> Any:
    """Use enum values and numeric dictionary keys, preserving sequence order."""
    if isinstance(value, Enum):
        return _canonical(value.value)
    if isinstance(value, dict):
        result = {}
        for key, child in value.items():
            key = _canonical(key)
            if isinstance(key, int) and not isinstance(key, bool):
                key = str(key)
            if not isinstance(key, str) or key in result:
                raise CheckpointError("ambiguous or unsupported state dictionary key")
            result[key] = _canonical(child)
        return result
    if isinstance(value, (list, tuple)):
        return [_canonical(child) for child in value]
    return value


def _encoded(value: Any) -> bytes:
    # Validate finiteness and dictionary keys before canonical sorted encoding.
    strict_json_dumps(value)
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_encoded(value)).hexdigest()


def _state(world: WorldState) -> dict[str, Any]:
    return _canonical(world.model_dump(mode="python"))


def _focus_deltas(world: WorldState) -> list[dict[str, dict[str, int]] | None]:
    try:
        return _FOCUS_ADAPTER.validate_python(
            [getattr(civ, "_focus_applied_deltas", None) for civ in world.civilizations], strict=True,
        )
    except ValidationError as exc:
        raise CheckpointError(f"invalid tracked tech focus deltas: {exc}") from exc


def _validate_focus_deltas(deltas: list[dict[str, dict[str, int]] | None]) -> None:
    for tracked in deltas:
        for focus, applied in (tracked or {}).items():
            try:
                effects = FOCUS_EFFECTS[TechFocus(focus)].stat_modifiers
            except (ValueError, KeyError) as exc:
                raise CheckpointError("unsupported tracked tech focus") from exc
            if applied.keys() != effects.keys() or any(type(delta) is not int for delta in applied.values()):
                raise CheckpointError("invalid tracked tech focus deltas")


def _comparison_state(world: WorldState) -> dict[str, Any]:
    return {"world": _state(world), "focus_deltas": _focus_deltas(world)}


def _reject_unknown_fields(payload: Any, parsed: Any, path: str = "world") -> None:
    """Reject silently discarded fields, including nested models, on Pydantic 2.x."""
    if isinstance(parsed, BaseModel) and isinstance(payload, dict):
        fields = type(parsed).model_fields
        for key, child in payload.items():
            if key not in fields or fields[key].exclude:
                raise CheckpointError(f"unrecognized persisted field: {path}.{key}")
            _reject_unknown_fields(child, getattr(parsed, key), f"{path}.{key}")
    elif isinstance(parsed, list) and isinstance(payload, list):
        for index, (child, value) in enumerate(zip(payload, parsed)):
            _reject_unknown_fields(child, value, f"{path}[{index}]")
    elif isinstance(parsed, dict) and isinstance(payload, dict):
        if len(payload) != len(parsed):
            raise CheckpointError(f"ambiguous normalized dictionary keys: {path}")
        # Pydantic may normalize int/enum keys; insertion order remains stable.
        for (key, child), value in zip(payload.items(), parsed.values()):
            _reject_unknown_fields(child, value, f"{path}.{key}")


def _schema_digest() -> str:
    return _digest(WorldState.model_json_schema())


def _runtime_identity() -> dict[str, str]:
    return {
        "python": platform.python_version(),
        "implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "source_sha256": package_digest(Path(__file__).parent),
        **{name: version(name) for name in (
            "pydantic", "numpy", "scipy", "pyarrow", "arro3-core", "pyyaml",
        )},
    }


def _require_supported(world: WorldState, runtime: str) -> None:
    if runtime != RUNTIME:
        raise CheckpointError(f"unsupported runtime {runtime!r}; only {RUNTIME} is validated")
    # Support is determined independently of the retired snapshot/name aliases.
    # Typed turn handoffs do not checkpoint native pools, RNG or bridge carry.
    if world.agent_mode not in (None, "off"):
        raise CheckpointError(
            f"unsupported agent mode {world.agent_mode!r}; native agent state/RNG is not checkpointed"
        )
    if getattr(world, "_agent_bridge", None) is not None:
        raise CheckpointError("native agent bridge cannot be checkpointed")
    if getattr(world, "_economy_result", None) is not None:
        raise CheckpointError("agent-backed economy state cannot be checkpointed")
    # Fail closed for old/staged callers still carrying the compatibility aliases.
    if any(getattr(world, name, None) is not None for name in ("_agent_snapshot", "_named_agents")):
        raise CheckpointError("agent snapshot/registry cannot be checkpointed")
    if world.pending_shocks or world._artifact_intents or world._artifact_lifecycle_intents:
        raise CheckpointError("checkpoint requires a completed turn with no pending simulation signals")
    if any(civ.factions.pending_faction_shift for civ in world.civilizations):
        raise CheckpointError("checkpoint requires a completed turn with no pending faction shift")
    if any(region.stockpile_bootstrap_pending for region in world.regions):
        raise CheckpointError("checkpoint requires a completed stockpile bootstrap")
    if getattr(world, "_treasury_tax_carry", None):
        raise CheckpointError("agent-backed treasury carry cannot be checkpointed")
    if type(world.turn) is not int or world.turn < 0:
        raise CheckpointError("checkpoint turn must be a non-negative integer")
    deltas = _focus_deltas(world)
    _validate_focus_deltas(deltas)
    for civ, tracked in zip(world.civilizations, deltas):
        if civ.active_focus and (tracked is None or civ.active_focus not in tracked):
            raise CheckpointError(
                "active tech focus lacks applied deltas; raw WorldState snapshots do not preserve them"
            )


def save_checkpoint(world: WorldState, path: Path, *, runtime: str = RUNTIME) -> None:
    """Save an envelope at a completed Python-only run_turn boundary.

    Callers must use no agent bridge, ecology runtime, politics runtime, pending
    injections, or external state. The validator below owns this execution path.
    Existing WorldState.save/load and production defaults remain unchanged.
    """
    _require_supported(world, runtime)
    _encoded(_state(world))  # Reject non-finite values before Pydantic can emit null.
    # Keep the existing WorldState JSON representation and its load semantics.
    payload = strict_json_loads(world.model_dump_json())
    deltas = _focus_deltas(world)
    atomic_write_json(path, {
        "format": FORMAT, "version": VERSION, "runtime": runtime,
        "schema_sha256": _schema_digest(), "runtime_identity": _runtime_identity(),
        "world_sha256": _digest(payload), "world": payload,
        "focus_deltas": deltas, "focus_deltas_sha256": _digest(deltas),
    })


def load_checkpoint(path: Path, *, runtime: str = RUNTIME) -> WorldState:
    """Fail closed on unsupported format, schema, runtime, or damaged payload."""
    try:
        envelope = _Envelope.model_validate(strict_json_loads(path.read_text(encoding="utf-8")))
        if envelope.format != FORMAT or envelope.version != VERSION:
            raise CheckpointError("unsupported checkpoint format/version")
        if envelope.runtime != runtime or runtime != RUNTIME:
            raise CheckpointError("unsupported checkpoint runtime; native continuation is unavailable")
        if envelope.schema_sha256 != _schema_digest():
            raise CheckpointError("checkpoint WorldState schema mismatch")
        if envelope.runtime_identity != _runtime_identity():
            raise CheckpointError("checkpoint source/Python/dependency runtime mismatch")
        if envelope.world_sha256 != _digest(envelope.world):
            raise CheckpointError("checkpoint world digest mismatch")
        if envelope.focus_deltas_sha256 != _digest(envelope.focus_deltas):
            raise CheckpointError("checkpoint focus deltas digest mismatch")
        world = WorldState.model_validate_json(strict_json_dumps(envelope.world), strict=True)
        _reject_unknown_fields(envelope.world, world)
        if len(envelope.focus_deltas) != len(world.civilizations):
            raise CheckpointError("checkpoint focus deltas/civilization count mismatch")
        _validate_focus_deltas(envelope.focus_deltas)
        for civ, tracked in zip(world.civilizations, envelope.focus_deltas):
            if tracked is not None:
                civ._focus_applied_deltas = tracked
        _require_supported(world, runtime)
        _encoded(_state(world))
        return world
    except (ArtifactIOError, ValidationError, OSError, UnicodeError) as exc:
        raise CheckpointError(f"invalid checkpoint: {exc}") from exc


def _advance(world: WorldState) -> None:
    engine = ActionEngine(world)
    run_turn(
        world,
        action_selector=lambda civ, current: engine.select_action(civ, seed=current.seed),
        narrator=lambda *_: "",
        seed=world.seed + world.turn,
    )


def _first_difference(left: Any, right: Any, path: str = "checkpoint") -> str | None:
    if isinstance(left, dict) and isinstance(right, dict):
        for key in sorted(left.keys() | right.keys()):
            child = f"{path}.{key}"
            if key not in left or key not in right:
                return child
            found = _first_difference(left[key], right[key], child)
            if found:
                return found
    elif isinstance(left, list) and isinstance(right, list):
        if len(left) != len(right):
            return f"{path}.length"
        for index, (a, b) in enumerate(zip(left, right)):
            found = _first_difference(a, b, f"{path}[{index}]")
            if found:
                return found
    elif type(left) is not type(right) or left != right:
        return path
    return None


def validate_replay(
    world: WorldState, *, turns: int, split: int, checkpoint_path: Path,
    runtime: str = RUNTIME,
) -> dict[str, Any]:
    """Validate additional turns; require at least one turn after the checkpoint.

    The input world is untouched. A PASS describes this precise tested trace,
    not universal continuation support. Stop at the first persisted difference.
    """
    _require_supported(world, runtime)
    if type(turns) is not int or type(split) is not int or not 0 <= split < turns:
        raise CheckpointError("require integer 0 <= split < turns (at least one resumed turn)")
    reference = world.model_copy(deep=True)
    _encoded(_state(reference))
    for _ in range(split):
        _advance(reference)
    save_checkpoint(reference, checkpoint_path, runtime=runtime)
    resumed = load_checkpoint(checkpoint_path, runtime=runtime)
    report: dict[str, Any] = {
        "report_version": VERSION, "status": "PASS", "runtime": runtime,
        "schema_sha256": _schema_digest(), "runtime_identity": _runtime_identity(),
        "seed": world.seed, "start_turn": world.turn, "checkpoint_turn": reference.turn,
        "target_turn": world.turn + turns, "compared_resumed_turns": 0,
        "scope": "persisted WorldState/events and focus deltas; Python off-mode; no narration/memory/history",
        "turn_digests": [],
    }
    for step in range(turns - split + 1):
        left, right = _comparison_state(reference), _comparison_state(resumed)
        left_digest, right_digest = _digest(left), _digest(right)
        difference = _first_difference(left, right)
        report["turn_digests"].append({
            "turn": reference.turn, "uninterrupted": left_digest, "resumed": right_digest,
        })
        if difference:
            report.update(status="FAIL", first_divergent_turn=reference.turn, difference_path=difference)
            break
        if step == turns - split:
            break
        _advance(reference)
        _advance(resumed)
        report["compared_resumed_turns"] += 1
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, help="Existing raw WorldState snapshot (read-only)")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--civs", type=int, default=4)
    parser.add_argument("--regions", type=int, default=8)
    parser.add_argument("--worldgen", choices=("auto", "template", "procedural"), default=None)
    parser.add_argument("--turns", type=int, default=50, help="Additional turns to validate")
    parser.add_argument("--split", type=int, default=12, help="Additional turns before checkpoint")
    parser.add_argument("--agents", default="off", help="Only off is supported")
    parser.add_argument("--runtime", default=RUNTIME, help=f"Only {RUNTIME} is supported")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    write_report = False
    try:
        if args.state and args.state.resolve() in {
            (args.output_dir / name).resolve() for name in ("checkpoint.json", "report.json")
        }:
            raise CheckpointError("output would overwrite the input state")
        if any(
            (args.output_dir / name).exists() or (args.output_dir / name).is_symlink()
            for name in ("checkpoint.json", "report.json")
        ):
            raise CheckpointError("output artifacts already exist; choose a fresh output directory")
        write_report = True
        if args.agents != "off" or args.runtime != RUNTIME:
            raise CheckpointError("only --agents=off --runtime=python-off-v1 is supported; native state/RNG is absent")
        if args.civs < 1 or args.regions < 1:
            raise CheckpointError("civs and regions must be positive integers")
        if args.state:
            payload = strict_json_loads(args.state.read_text(encoding="utf-8"))
            world = WorldState.model_validate_json(strict_json_dumps(payload), strict=True)
            _reject_unknown_fields(payload, world)
        else:
            from chronicler.world_gen import generate_world
            world = generate_world(seed=args.seed, num_civs=args.civs, num_regions=args.regions,
                                   worldgen=args.worldgen)
        report = validate_replay(
            world, turns=args.turns, split=args.split,
            checkpoint_path=args.output_dir / "checkpoint.json", runtime=args.runtime,
        )
    except (CheckpointError, ArtifactIOError, ValidationError, OSError, UnicodeError) as exc:
        report = {"report_version": VERSION, "status": "ERROR", "reason": str(exc)}
    try:
        if not write_report:
            print(strict_json_dumps(report), end="")
            return 2
        atomic_write_json(args.output_dir / "report.json", report)
    except ArtifactIOError as exc:
        print(strict_json_dumps({"status": "ERROR", "reason": str(exc)}), end="")
        return 2
    print(strict_json_dumps(report), end="")
    return {"PASS": 0, "FAIL": 1, "ERROR": 2}[report["status"]]


if __name__ == "__main__":
    raise SystemExit(main())
