"""Exact run checkpoints: the resume envelope.

A checkpoint written at the end of turn k holds everything a run carries
into turn k+1, so a run resumed from it writes the same bundle, state,
memories and sidecars, byte for byte, as the run that never stopped:

* the Python object graph in one pickle: the world with its private
  caches, accumulators and pending signals, the agent bridge, the economy
  tracker, memory streams, and the run's own accumulators (history,
  chronicle entries, era reflections, its first turn, seed and length);
* each native simulator's own state, written by Rust
  (``AgentSimulator.checkpoint_state()`` etc.; ``chronicler-agents/src/persist.rs``):
  the agent pool, regions, registries, trips, ledgers and queues, never
  reconstructed from Python.

File layout::

    MAGIC (20 bytes) | header length (u32 LE) | header (JSON) | sections

The header records the format version, the turn, the source and native
build identity, the interpreter and thread environment, the feature
switches and the SHA-256 of every section. Loading refuses a different
format version, a corrupt section, and by default any difference in build
identity; ``allow_mismatch`` continues anyway and labels the run as not
identical to an uninterrupted one.

Checkpoints are trusted local files, like the rest of a run directory. The
loader still restricts what the pickle may construct (Chronicler classes,
a few standard containers and NumPy arrays) and verifies every digest.
"""
from __future__ import annotations

import copyreg
import hashlib
import io
import json
import os
import pickle
import platform
import struct
import sys
import time
import zlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

FORMAT = "chronicler-run-checkpoint"
FORMAT_VERSION = 1
MAGIC = b"\x89CHRONICLER-CKPT\r\n\x1a\n"
PICKLE_PROTOCOL = 5
ZLIB_LEVEL = 1
DEFAULT_FILENAME = "checkpoint.ckpt"

_NATIVE_KINDS = {
    "AgentSimulator": "agent",
    "EcologySimulator": "ecology",
    "PoliticsSimulator": "politics",
}


class CheckpointError(ValueError):
    """A checkpoint that cannot be read or continued."""


class CheckpointIncompatible(CheckpointError):
    """A checkpoint written by another build or environment."""

    def __init__(self, path: Path, mismatches: list[str]):
        self.mismatches = mismatches
        lines = "\n  ".join(mismatches)
        super().__init__(
            f"checkpoint {path} was written by an incompatible build or environment:\n  {lines}\n"
            "An exact resume needs the same source, native extension, interpreter, packages and "
            "thread settings. Pass --resume-allow-mismatch to continue anyway; the run is then "
            "labelled as not identical to an uninterrupted run."
        )


@dataclass
class RunState:
    """Everything ``execute_run`` carries from one turn into the next."""

    world: Any
    memories: dict
    history: list
    chronicle_entries: list
    era_reflections: dict
    pending_injections: list
    start_turn: int
    seed: int
    num_turns: int
    agent_bridge: Any = None
    ecology_runtime: Any = None
    politics_runtime: Any = None
    economy_tracker: Any = None
    scenario_config: Any = None
    run_config: dict = field(default_factory=dict)
    # Identity-keyed markers re-bound to the restored objects on load.
    markers: dict = field(default_factory=dict)
    # A live session's presentation state: what a newly connecting viewer is
    # sent (chronicler.live_checkpoints.LiveView.record); None for other runs.
    live: dict | None = None


@dataclass
class LoadedCheckpoint:
    header: dict
    state: RunState
    mismatches: list[str]
    seconds: float
    timings: dict[str, float] = field(default_factory=dict)

    @property
    def exact(self) -> bool:
        """Resuming continues exactly the saved run, which itself never took
        a resume that was not exact."""
        return bool(self.header.get("exact", False)) and not self.mismatches


@dataclass
class WriteReport:
    path: Path
    bytes: int
    raw_bytes: int
    sections: dict[str, int]
    seconds: float
    timings: dict[str, float] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------

_SOURCE_IDENTITY: dict | None = None
_NATIVE_IDENTITY: dict | None = None


def _source_identity() -> dict:
    global _SOURCE_IDENTITY
    if _SOURCE_IDENTITY is None:
        from chronicler.batch_manifest import source_identity
        ident = source_identity()
        _SOURCE_IDENTITY = {
            "package_digest": ident["package_digest"],
            "git_sha": ident["git_sha"],
        }
    return _SOURCE_IDENTITY


def _native_identity() -> dict:
    """The extension file's digest and each simulator's state layout."""
    global _NATIVE_IDENTITY
    if _NATIVE_IDENTITY is None:
        from chronicler.batch_manifest import native_identity
        ident = native_identity()
        out: dict[str, Any] = {"status": ident.get("status")}
        if ident.get("status") == "found":
            out["sha256"] = ident["sha256"]
            out["bytes"] = ident["bytes"]
        layouts = {}
        try:
            import chronicler_agents as native
        except ImportError:
            native = None
        for cls_name, kind in _NATIVE_KINDS.items():
            cls = getattr(native, cls_name, None) if native is not None else None
            schema = getattr(cls, "checkpoint_schema", None) if isinstance(cls, type) else None
            if schema is not None:
                version, fingerprint, _ = schema()
                layouts[kind] = f"v{version}:{fingerprint}"
        out["state_layouts"] = layouts
        _NATIVE_IDENTITY = out
    return _NATIVE_IDENTITY


_ENVIRONMENT_IDENTITY: dict | None = None


def _environment_identity() -> dict:
    """Interpreter, packages and thread settings, read once per process."""
    global _ENVIRONMENT_IDENTITY
    if _ENVIRONMENT_IDENTITY is not None:
        return _ENVIRONMENT_IDENTITY
    from chronicler.batch_manifest import environment_identity
    env = environment_identity()
    _ENVIRONMENT_IDENTITY = {
        "python": env["python"],
        "implementation": env["implementation"],
        "machine": env["machine"],
        "affinity_cpu_count": env["affinity_cpu_count"],
        "thread_env": env["thread_env"],
        "packages": env["packages"],
        "hash_seed": os.environ.get("PYTHONHASHSEED"),
    }
    return _ENVIRONMENT_IDENTITY


def runtime_identity() -> dict:
    return {
        "source": _source_identity(),
        "native": _native_identity(),
        "environment": _environment_identity(),
    }


def _compare_identity(saved: dict, current: dict, uses_native: bool) -> list[str]:
    """Differences that can change what the run computes next."""
    out: list[str] = []

    def diff(label: str, a: Any, b: Any) -> None:
        if a == b:
            return
        if isinstance(a, dict) and isinstance(b, dict):
            for key in sorted(set(a) | set(b)):
                if a.get(key) != b.get(key):
                    out.append(f"{label} {key}: checkpoint {a.get(key)!r}, this run {b.get(key)!r}")
            return
        out.append(f"{label}: checkpoint {a!r}, this run {b!r}")

    diff("source package digest", saved["source"]["package_digest"],
         current["source"]["package_digest"])
    s_nat, c_nat = saved["native"], current["native"]
    # The extension decides which runtimes a turn uses (off mode included),
    # so its bytes must match; the state layouts matter where native state
    # is carried.
    diff("native extension", s_nat.get("sha256"), c_nat.get("sha256"))
    if uses_native:
        diff("native state layouts", s_nat.get("state_layouts"), c_nat.get("state_layouts"))
    s_env, c_env = saved["environment"], current["environment"]
    for key in ("implementation", "python", "machine", "packages", "thread_env"):
        diff(f"environment {key}", s_env.get(key), c_env.get(key))
    threads = s_env.get("thread_env") or {}
    if not threads.get("OPENBLAS_NUM_THREADS") and not threads.get("OMP_NUM_THREADS"):
        # OpenBLAS sizes its pool by the CPUs when no thread count is set.
        diff("environment affinity_cpu_count (no OpenBLAS thread count set)",
             s_env.get("affinity_cpu_count"), c_env.get("affinity_cpu_count"))
    return out


# ---------------------------------------------------------------------------
# Feature switches and run configuration
# ---------------------------------------------------------------------------

def feature_flags(world: Any) -> dict[str, bool]:
    """The world's simulation switches, keyed by CLI destination."""
    from chronicler.agent_movements import agent_movements_enabled
    from chronicler.cities import cities_enabled
    from chronicler.contact_ledger import ledger_enabled
    from chronicler.diplomacy import diplomacy_enabled
    from chronicler.epidemiology import epidemiology_enabled
    from chronicler.experimental.fisheries import fishery_enabled
    from chronicler.finance import finance_enabled
    from chronicler.governance_runtime import governance_enabled
    from chronicler.gp_agendas import gp_agendas_enabled
    from chronicler.guilds import guilds_enabled
    from chronicler.maritime import maritime_enabled
    from chronicler.nomads import nomads_enabled
    from chronicler.scholarship import scholarship_enabled
    from chronicler.grain_reserves import grain_reserves_enabled
    from chronicler.community_anchoring import community_anchoring_enabled
    from chronicler.domestic_credit_state import domestic_credit_on
    from chronicler.techniques import techniques_enabled

    return {
        "campaigns": bool(world.campaigns_enabled),
        "mutual_aid": bool(world.mutual_aid_enabled),
        "fisheries": bool(fishery_enabled(world)),
        "governance": bool(governance_enabled(world)),
        "contact_ledger": bool(ledger_enabled(world)),
        "epidemiology": bool(epidemiology_enabled(world)),
        "finance": bool(finance_enabled(world)),
        "diplomacy": bool(diplomacy_enabled(world)),
        "techniques": bool(techniques_enabled(world)),
        "maritime": bool(maritime_enabled(world)),
        "gp_agendas": bool(gp_agendas_enabled(world)),
        "nomads": bool(nomads_enabled(world)),
        "cities": bool(cities_enabled(world)),
        "agent_movements": bool(agent_movements_enabled(world)),
        "guilds": bool(guilds_enabled(world)),
        "scholarship": bool(scholarship_enabled(world)),
        "grain_reserves": bool(grain_reserves_enabled(world)),
        "community_anchoring": bool(community_anchoring_enabled(world)),
        "domestic_credit": bool(domestic_credit_on(world)),
        # The observational layers are read without importing them (they are
        # imported only by the modules that run or narrate them).
        "historiography": getattr(world, "_historiography", None) is not None,
        "languages": getattr(world, "_languages", None) is not None,
    }


# ---------------------------------------------------------------------------
# Pickling
# ---------------------------------------------------------------------------

_LOAD_NATIVES: dict[str, Any] | None = None


def _native_ref(key: str) -> Any:
    """Pickle stand-in for a native simulator; resolved by the loader."""
    if _LOAD_NATIVES is None or key not in _LOAD_NATIVES:
        raise CheckpointError(f"checkpoint references native state {key!r} it does not carry")
    return _LOAD_NATIVES[key]


_AGENT_EVENT_FIELDS: Any = None


def _reduce_agent_event(event: Any) -> tuple:
    """``(AgentEventRecord, positional fields)``: rebuilt by its constructor."""
    global _AGENT_EVENT_FIELDS
    if _AGENT_EVENT_FIELDS is None:
        import dataclasses
        import operator
        _AGENT_EVENT_FIELDS = operator.attrgetter(
            *(f.name for f in dataclasses.fields(type(event))))
    return (type(event), _AGENT_EVENT_FIELDS(event))


class _Pickler(pickle.Pickler):
    """Pickles the run with each native simulator as its Rust state blob."""

    def __init__(self, file: io.BytesIO):
        super().__init__(file, protocol=PICKLE_PROTOCOL)
        self.natives: dict[str, bytes] = {}
        self.native_seconds = 0.0
        table = copyreg.dispatch_table.copy()
        try:
            import chronicler_agents as native
        except ImportError:
            native = None
        if native is not None:
            for cls_name, kind in _NATIVE_KINDS.items():
                cls = getattr(native, cls_name, None)
                if isinstance(cls, type):
                    table[cls] = self._reducer(kind)
        # Agent event records are the run's most numerous objects (every
        # birth, death and migration): pickled as their positional fields,
        # half the bytes of the default slots state and twice as fast to load.
        from chronicler.models import AgentEventRecord
        table[AgentEventRecord] = _reduce_agent_event
        self.dispatch_table = table

    def _reducer(self, kind: str):
        def reduce(obj: Any):
            save = getattr(obj, "checkpoint_state", None)
            if save is None:
                raise CheckpointError(
                    f"the installed chronicler_agents {type(obj).__name__} predates exact "
                    "checkpoints; rebuild the extension"
                )
            key = f"{kind}.{sum(1 for k in self.natives if k.startswith(kind + '.'))}"
            t0 = time.perf_counter()
            self.natives[key] = bytes(save())
            self.native_seconds += time.perf_counter() - t0
            return (_native_ref, (key,))
        return reduce


_ALLOWED_GLOBALS = {
    "builtins": {"set", "frozenset", "list", "dict", "tuple", "int", "float", "str", "bytes",
                 "bytearray", "complex", "slice", "range", "bool", "object"},
    "collections": {"deque", "defaultdict", "OrderedDict", "Counter"},
    "copyreg": {"_reconstructor"},
    "datetime": {"datetime", "date", "time", "timedelta", "timezone"},
    "pathlib": {"Path", "PosixPath", "WindowsPath", "PurePath", "PurePosixPath", "PureWindowsPath"},
    "pathlib._local": {"Path", "PosixPath", "WindowsPath", "PurePath", "PurePosixPath",
                       "PureWindowsPath"},
    "numpy": {"ndarray", "dtype"},
    "numpy.core.multiarray": {"_reconstruct", "scalar"},
    "numpy._core.multiarray": {"_reconstruct", "scalar"},
    "numpy.core.numeric": {"_frombuffer"},
    "numpy._core.numeric": {"_frombuffer"},
}


# Chronicler functions a pickle may call: the reducers of slots that pickle
# themselves as their serialized dump (``__reduce__``).
_ALLOWED_CHRONICLER_FUNCTIONS = {
    ("chronicler.historiography", "_slot_from_dump"),
    ("chronicler.languages", "_slot_from_dump"),
}


class _Unpickler(pickle.Unpickler):
    def find_class(self, module: str, name: str) -> Any:
        if module == __name__ and name == "_native_ref":
            return _native_ref
        if name in _ALLOWED_GLOBALS.get(module, ()):
            return super().find_class(module, name)
        if (module, name) in _ALLOWED_CHRONICLER_FUNCTIONS:
            return super().find_class(module, name)
        if module == "numpy.dtypes" and name.endswith("DType"):
            return super().find_class(module, name)
        if module == "chronicler" or module.startswith("chronicler."):
            obj = super().find_class(module, name)
            if isinstance(obj, type):
                return obj
        raise CheckpointError(
            f"checkpoint references {module}.{name}, which an exact checkpoint may not construct"
        )


# ---------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------

def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _markers(state: RunState) -> dict:
    """Markers that hold a Python object identity, re-bound on load.

    ``world._war_roster_sim`` is ``id(bridge._sim)`` once the war rosters
    are bound to the pool; a restored simulator has another identity, and
    an unmatched marker would re-draft every roster."""
    world = state.world
    sim = getattr(state.agent_bridge, "_sim", None) if state.agent_bridge is not None else None
    marker = world.__dict__.get("_war_roster_sim", "unset")
    if marker == "unset" and world.__pydantic_private__:
        marker = world.__pydantic_private__.get("_war_roster_sim", "unset")
    return {"war_roster_bound": sim is not None and marker == id(sim)}


def write_checkpoint(path: Path, state: RunState, *, exact: bool = True,
                     lineage: list[dict] | None = None) -> WriteReport:
    """Write ``state`` atomically to ``path``. Reads the run only."""
    from chronicler.artifact_io import atomic_write_bytes

    t0 = time.perf_counter()
    state.markers = _markers(state)
    buf = io.BytesIO()
    pickler = _Pickler(buf)
    pickler.dump(state)
    raw = {"python": buf.getvalue()}
    t_pickle = time.perf_counter()
    for key, blob in pickler.natives.items():
        raw[f"native.{key}"] = blob
    sections = []
    payloads = []
    offset = 0
    for name, data in raw.items():
        packed = zlib.compress(data, ZLIB_LEVEL)
        sections.append({
            "name": name,
            "codec": "pickle5+zlib" if name == "python" else "native+zlib",
            "offset": offset,
            "length": len(packed),
            "raw_length": len(data),
            "sha256": _sha256(packed),
        })
        payloads.append(packed)
        offset += len(packed)
    t_compress = time.perf_counter()
    world = state.world
    header = {
        "format": FORMAT,
        "version": FORMAT_VERSION,
        "turn": world.turn,
        "seed": state.seed,
        "start_turn": state.start_turn,
        "num_turns": state.num_turns,
        "world": {
            "name": world.name,
            "regions": len(world.regions),
            "civilizations": len(world.civilizations),
            "geography": world.geography is not None,
        },
        "flags": feature_flags(world),
        "run_config": state.run_config,
        "exact": bool(exact),
        "lineage": list(lineage or []),
        "identity": runtime_identity(),
        "sections": sections,
    }
    header_bytes = json.dumps(header, sort_keys=True, separators=(",", ":"),
                              allow_nan=False).encode("utf-8")
    blob = b"".join([MAGIC, struct.pack("<I", len(header_bytes)), header_bytes, *payloads])
    t_header = time.perf_counter()
    atomic_write_bytes(Path(path), blob)
    t_end = time.perf_counter()
    return WriteReport(
        path=Path(path), bytes=len(blob), raw_bytes=sum(len(d) for d in raw.values()),
        sections={s["name"]: s["length"] for s in sections},
        seconds=t_end - t0,
        timings={"native": pickler.native_seconds,
                 "pickle": t_pickle - t0 - pickler.native_seconds,
                 "compress": t_compress - t_pickle, "header": t_header - t_compress,
                 "write": t_end - t_header},
    )


def checkpoint_path(template: str | Path, turn: int) -> Path:
    """``template`` with ``{turn}`` (and format specs such as ``{turn:04d}``)
    filled in; a template without it names one file, replaced each time."""
    text = str(template)
    if "{" in text:
        text = text.format(turn=turn)
    return Path(text)


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------

def is_checkpoint(path: Path) -> bool:
    try:
        with open(path, "rb") as fh:
            return fh.read(len(MAGIC)) == MAGIC
    except OSError:
        return False


def read_header(path: Path) -> tuple[dict, bytes]:
    """The verified header and the section bytes of ``path``."""
    from chronicler.artifact_io import ArtifactIOError, strict_json_loads

    path = Path(path)
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise CheckpointError(f"cannot read checkpoint {path}: {exc}") from exc
    if not data.startswith(MAGIC):
        raise CheckpointError(f"{path} is not an exact run checkpoint")
    start = len(MAGIC) + 4
    if len(data) < start:
        raise CheckpointError(f"checkpoint {path} is truncated")
    (header_len,) = struct.unpack("<I", data[len(MAGIC):start])
    if start + header_len > len(data):
        raise CheckpointError(f"checkpoint {path} is truncated")
    try:
        header = strict_json_loads(data[start:start + header_len].decode("utf-8"),
                                   label="checkpoint header")
    except (UnicodeDecodeError, ArtifactIOError) as exc:
        raise CheckpointError(f"checkpoint {path} has a corrupt header: {exc}") from exc
    if not isinstance(header, dict) or header.get("format") != FORMAT:
        raise CheckpointError(f"{path} is not a {FORMAT} file")
    if header.get("version") != FORMAT_VERSION:
        raise CheckpointError(
            f"checkpoint {path} is format version {header.get('version')!r}; this build reads "
            f"version {FORMAT_VERSION}"
        )
    body = data[start + header_len:]
    expected = 0
    for section in header.get("sections", []):
        if section.get("offset") != expected:
            raise CheckpointError(f"checkpoint {path}: section {section.get('name')!r} is misplaced")
        expected += int(section.get("length", -1))
    if expected != len(body):
        raise CheckpointError(f"checkpoint {path} is truncated or has trailing bytes")
    return header, body


def _section(path: Path, header: dict, body: bytes, name: str) -> bytes:
    for section in header["sections"]:
        if section["name"] == name:
            packed = body[section["offset"]:section["offset"] + section["length"]]
            if _sha256(packed) != section["sha256"]:
                raise CheckpointError(f"checkpoint {path}: section {name!r} is corrupt (SHA-256 differs)")
            data = zlib.decompress(packed)
            if len(data) != section["raw_length"]:
                raise CheckpointError(f"checkpoint {path}: section {name!r} has the wrong length")
            return data
    raise CheckpointError(f"checkpoint {path} has no {name!r} section")


def read_checkpoint(path: Path, *, allow_mismatch: bool = False) -> LoadedCheckpoint:
    """Load ``path`` for an exact resume.

    Refuses a checkpoint of another build or environment unless
    ``allow_mismatch``; the differences are returned either way."""
    global _LOAD_NATIVES
    t0 = time.perf_counter()
    path = Path(path)
    header, body = read_header(path)
    natives = [s["name"] for s in header["sections"] if s["name"].startswith("native.")]
    mismatches = _compare_identity(header["identity"], runtime_identity(), bool(natives))
    if mismatches and not allow_mismatch:
        raise CheckpointIncompatible(path, mismatches)
    t_header = time.perf_counter()
    restored: dict[str, Any] = {}
    if natives:
        try:
            import chronicler_agents as native
        except ImportError as exc:
            raise CheckpointError(
                f"checkpoint {path} carries native simulator state; the chronicler_agents "
                "extension is not installed"
            ) from exc
        classes = {kind: getattr(native, cls_name, None) for cls_name, kind in _NATIVE_KINDS.items()}
        for name in natives:
            key = name[len("native."):]
            cls = classes.get(key.split(".")[0])
            loader = getattr(cls, "from_checkpoint_state", None) if isinstance(cls, type) else None
            if loader is None:
                raise CheckpointError(
                    f"the installed chronicler_agents cannot restore {key!r}; rebuild the extension"
                )
            try:
                restored[key] = loader(_section(path, header, body, name))
            except ValueError as exc:
                raise CheckpointError(f"checkpoint {path}: cannot restore {key!r}: {exc}") from exc
    t_native = time.perf_counter()
    raw = _section(path, header, body, "python")
    _LOAD_NATIVES = restored
    try:
        state = _Unpickler(io.BytesIO(raw)).load()
    except CheckpointError:
        raise
    except Exception as exc:
        raise CheckpointError(f"checkpoint {path}: cannot restore the Python state: {exc}") from exc
    finally:
        _LOAD_NATIVES = None
    if not isinstance(state, RunState):
        raise CheckpointError(f"checkpoint {path} does not hold a run state")
    _rebind_markers(state)
    _upgrade_faiths(state)
    t_end = time.perf_counter()
    return LoadedCheckpoint(header=header, state=state, mismatches=mismatches,
                            seconds=t_end - t0,
                            timings={"read": t_header - t0, "native": t_native - t_header,
                                     "python": t_end - t_native})


def _rebind_markers(state: RunState) -> None:
    if state.markers.get("war_roster_bound") and state.agent_bridge is not None:
        state.world._war_roster_sim = id(state.agent_bridge._sim)


def _upgrade_faiths(state: RunState) -> None:
    """A checkpoint written before permanent faith ids (resumed across
    builds): rebuild the world's faith table and map the recycled-slot
    references of its records and history snapshots (chronicler.faiths). A
    checkpoint carrying the table is left exactly as written."""
    from chronicler import faiths
    world = state.world
    legacy = not world.__dict__.get("faiths")
    faiths.ensure(world)
    if legacy and faiths.table(world) is not None and faiths.needs_mapping(world.faiths):
        faiths.upgrade_snapshots(state.history, faiths.resolver(world.faiths))


def retarget_outputs(state: RunState, output_dir: Path, shadow_output: Path | None) -> None:
    """Point the restored sidecar writers at this run's output directory."""
    bridge = state.agent_bridge
    if bridge is None:
        return
    sidecar = getattr(bridge, "_sidecar", None)
    if sidecar is not None:
        sidecar._base_dir = output_dir
        sidecar._dir = output_dir / "validation_summary"
        sidecar._dir.mkdir(parents=True, exist_ok=True)
    shadow = getattr(bridge, "_shadow_logger", None)
    if shadow is not None and shadow_output is not None:
        shadow.retarget(shadow_output)


def save_world(path: Path, world: Any) -> WriteReport:
    """An exact checkpoint of a bare world, for callers that drive
    ``run_turn`` themselves: the world with every private cache,
    accumulator and pending signal (``WorldState.save`` keeps model fields
    only). No bridge, runtimes or run accumulators."""
    state = RunState(world=world, memories={}, history=[], chronicle_entries=[],
                     era_reflections={}, pending_injections=[], start_turn=world.turn,
                     seed=world.seed, num_turns=world.turn)
    return write_checkpoint(path, state)


def load_world(path: Path, *, allow_mismatch: bool = False) -> Any:
    """The world of a ``save_world`` (or any) checkpoint."""
    return read_checkpoint(path, allow_mismatch=allow_mismatch).state.world


def describe(path: Path) -> dict:
    """The header of ``path`` with section sizes, for inspection."""
    header, _ = read_header(path)
    return header


def main(argv: list[str] | None = None) -> int:
    """``python -m chronicler.run_checkpoint CHECKPOINT``: print its header."""
    import argparse

    parser = argparse.ArgumentParser(description="Inspect an exact run checkpoint.")
    parser.add_argument("checkpoint", type=Path)
    parser.add_argument("--check", action="store_true",
                        help="also compare its build identity with this environment")
    args = parser.parse_args(argv)
    try:
        header = describe(args.checkpoint)
    except CheckpointError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(header, indent=2, sort_keys=True))
    if args.check:
        natives = any(s["name"].startswith("native.") for s in header["sections"])
        mismatches = _compare_identity(header["identity"], runtime_identity(), natives)
        for line in mismatches:
            print(f"mismatch: {line}")
        print("compatible" if not mismatches else "incompatible")
        return 0 if not mismatches else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
