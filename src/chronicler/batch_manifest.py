"""Batch run manifests: what a batch directory is supposed to hold.

``chronicler.batch.run_batch`` writes ``batch_manifest.json`` into a fresh
batch directory before the first run (status ``running``) and rewrites it
after the last (``complete``, or ``cancelled``). It records the expected
seeds and turns, the requested simulation configuration, the source and
native-extension identity, the interpreter, platform and thread environment,
and per run its directory, its final turn and the SHA-256 of every file the
validator reads. ``chronicler.validate`` refuses a batch directory whose
bundles do not match its manifest (``verify_batch_manifest``), so a reused
or partly overwritten directory cannot pass for a clean cohort.

Nothing here runs a child process or imports the native extension: the
source revision is read from the Git files, the extension is found on the
import path and hashed.
"""
from __future__ import annotations

import hashlib
import importlib.machinery
import os
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from chronicler.artifact_io import ArtifactIOError, atomic_write_json, strict_json_loads

MANIFEST_FILENAME = "batch_manifest.json"
MANIFEST_KIND = "chronicler-batch"
MANIFEST_SCHEMA_VERSION = 1
BUNDLE_FILENAME = "chronicle_bundle.json"

# Files of a seed directory that ``chronicler.validate`` reads, and the
# legacy JSON sidecar directory. Other outputs (state.json, memory streams,
# chronicle text) are not hashed and may be pruned after a batch.
VALIDATION_INPUT_FILES = (
    BUNDLE_FILENAME,
    "agent_events.arrow",
    "validation_needs.arrow",
    "validation_relationships.arrow",
    "validation_memory_signatures.arrow",
    "validation_summary.json",
    "validation_community_summary.json",
)
VALIDATION_INPUT_DIRS = ("validation_summary",)

# CLI arguments (``chronicler.main`` parser destinations) by what they
# change. Simulation arguments change what is simulated and must match for
# two batches to be the same cohort; output arguments change what is
# written; the rest change neither (paths, clients, modes, base seed and
# count, which the manifest records as its seeds). Every parser destination
# is in exactly one group (tests/test_batch_manifest.py).
WORLD_ARG_KEYS = ("worldgen", "regions", "civs", "scenario")
SIMULATION_ARG_KEYS = WORLD_ARG_KEYS + (
    "turns",
    "reflection_interval",
    "agents",
    "agent_scale_mode",
    "decision_ablation",
    "ablation_start_turn",
    "mutual_aid",
    "fisheries",
    "campaigns",
    "governance",
    "contact_ledger",
    "epidemiology",
    "finance",
    "diplomacy",
    "techniques",
    "maritime",
    "gp_agendas",
    "nomads",
    "cities",
    "agent_movements",
    "guilds",
    "historiography",
    "languages",
    "scholarship",
    "grain_reserves",
    "tuning",
    "preset",
    "aggression_bias",
    "tech_diffusion_rate",
    "resource_abundance",
    "trade_friction",
    "severity_multiplier",
    "cultural_drift_speed",
    "religion_intensity",
    "secession_likelihood",
)
OUTPUT_ARG_KEYS = ("simulate_only", "narrator", "validation_sidecar", "relationship_stats", "state_every")
NON_SIMULATION_ARG_KEYS = (
    "seed", "seed_range", "batch", "parallel", "output", "state", "resume", "checkpoint_every",
    "checkpoint", "checkpoint_turns", "resume_allow_mismatch", "local_url", "sim_model",
    "narrative_model", "llm_actions", "fork", "interactive", "pause_every", "live", "live_port", "live_origin",
    "analyze",
    "compare", "checkpoints", "narrate", "budget", "narrate_output", "citations",
)

# Thread and hash-seed environment: OpenBLAS sums above 10,000 values
# depend on its thread count (docs/performance/turn-speed-2026-10.md).
THREAD_ENV_VARS = (
    "OMP_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "OPENBLAS_THREAD_TIMEOUT",
    "MKL_NUM_THREADS",
    "BLIS_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS",
    "NUMEXPR_NUM_THREADS",
    "GOTO_NUM_THREADS",
    "RAYON_NUM_THREADS",
    "PYTHON_CPU_COUNT",
    "PYTHONHASHSEED",
)
IDENTITY_PACKAGES = ("numpy", "scipy", "pyarrow", "pydantic", "arro3-core", "chronicler-agents")


class BatchDestinationError(ValueError):
    """A batch would write into a directory that already holds files."""


class BatchManifestError(ValueError):
    """A batch directory does not match its manifest, or has none."""


def check_batch_destination(batch_dir: Path) -> None:
    """Refuse a ``batch_dir`` that already holds anything (``BatchDestinationError``).

    Validation reads every bundle below a batch directory, so a second batch
    into the same directory would mix its runs with the first one's.
    """
    batch_dir = Path(batch_dir)
    if batch_dir.exists():
        if not batch_dir.is_dir():
            raise BatchDestinationError(f"batch destination {batch_dir} exists and is not a directory")
        entries = sorted(path.name for path in batch_dir.iterdir())
        if entries:
            shown = ", ".join(entries[:5]) + (", ..." if len(entries) > 5 else "")
            raise BatchDestinationError(
                f"batch directory {batch_dir} is not empty ({len(entries)} entries: {shown}); "
                "a batch writes into a new or empty directory, so that validation reads only its runs. "
                "Remove it or choose another --output."
            )


def prepare_batch_dir(batch_dir: Path) -> None:
    """Create ``batch_dir`` and claim it, refusing one that already holds
    anything (``check_batch_destination``). The claim is an exclusively
    created, empty ``batch_manifest.json``, so of two batches started into
    the same directory at once only one proceeds; the batch then writes the
    manifest over it."""
    check_batch_destination(batch_dir)
    Path(batch_dir).mkdir(parents=True, exist_ok=True)
    try:
        os.close(os.open(Path(batch_dir) / MANIFEST_FILENAME, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644))
    except FileExistsError as exc:
        raise BatchDestinationError(f"batch directory {batch_dir} was claimed by another batch") from exc


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _json_value(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in sorted(value.items(), key=lambda kv: str(kv[0]))}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return str(value)


def simulation_config(args: Any, tuning_overrides: dict | None = None) -> dict[str, Any]:
    """The requested simulation configuration of a run namespace: each
    ``SIMULATION_ARG_KEYS`` value as given (None: the CLI default) and the
    tuning overrides in effect."""
    config = {key: _json_value(getattr(args, key, None)) for key in SIMULATION_ARG_KEYS}
    overrides = tuning_overrides if tuning_overrides is not None else getattr(args, "tuning_overrides", None)
    config["tuning_overrides"] = _json_value(overrides or {})
    return config


def output_config(args: Any) -> dict[str, Any]:
    return {key: _json_value(getattr(args, key, None)) for key in OUTPUT_ARG_KEYS}


def _package_dir() -> Path:
    return Path(__file__).resolve().parent


def _git_dir(start: Path) -> Path | None:
    for parent in (start, *start.parents):
        dotgit = parent / ".git"
        try:
            if dotgit.is_dir():
                return dotgit
            if dotgit.is_file():
                text = dotgit.read_text(encoding="utf-8").strip()
                if text.startswith("gitdir:"):
                    target = Path(text[len("gitdir:"):].strip())
                    return target if target.is_absolute() else (parent / target).resolve()
                return None
        except OSError:
            return None
    return None


def _is_sha(text: str) -> bool:
    return len(text) in (40, 64) and all(char in "0123456789abcdef" for char in text)


def _resolve_git_head(git_dir: Path) -> tuple[str | None, str | None]:
    head = (git_dir / "HEAD").read_text(encoding="utf-8").strip()
    if not head.startswith("ref:"):
        return (head if _is_sha(head) else None), None
    ref = head[len("ref:"):].strip()
    common = git_dir
    commondir = git_dir / "commondir"
    if commondir.is_file():
        common = (git_dir / commondir.read_text(encoding="utf-8").strip()).resolve()
    for base in (git_dir, common):
        loose = base / ref
        if loose.is_file():
            sha = loose.read_text(encoding="utf-8").strip()
            return (sha if _is_sha(sha) else None), ref
    packed = common / "packed-refs"
    if packed.is_file():
        for line in packed.read_text(encoding="utf-8").splitlines():
            if not line or line.startswith(("#", "^")):
                continue
            sha, _, name = line.partition(" ")
            if name.strip() == ref and _is_sha(sha):
                return sha, ref
    return None, ref


def package_digest(package_dir: Path | None = None) -> str:
    """SHA-256 over the running ``chronicler`` package's Python files
    (relative path and content hash, in path order): the source identity
    when the checkout is dirty or not a Git work tree."""
    package_dir = package_dir or _package_dir()
    digest = hashlib.sha256()
    for path in sorted(package_dir.rglob("*.py"), key=lambda p: p.relative_to(package_dir).as_posix()):
        digest.update(path.relative_to(package_dir).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(file_sha256(path).encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def source_identity() -> dict[str, Any]:
    """Git revision of the checkout holding the running package (None when
    it is not a Git work tree; uncommitted changes are not detected) and the
    package digest."""
    package_dir = _package_dir()
    sha = ref = None
    try:
        git_dir = _git_dir(package_dir)
        if git_dir is not None:
            sha, ref = _resolve_git_head(git_dir)
    except OSError:
        sha = ref = None
    return {
        "git_sha": sha,
        "git_ref": ref,
        "package_dir": str(package_dir),
        "package_digest": package_digest(package_dir),
    }


def _find_native_extension() -> Path | None:
    suffixes = importlib.machinery.EXTENSION_SUFFIXES
    for entry in sys.path:
        base = Path(entry or ".")
        package = base / "chronicler_agents"
        try:
            if package.is_dir():
                for suffix in suffixes:
                    candidate = package / f"chronicler_agents{suffix}"
                    if candidate.is_file():
                        return candidate
                return None
            for suffix in suffixes:
                candidate = base / f"chronicler_agents{suffix}"
                if candidate.is_file():
                    return candidate
        except OSError:
            continue
    return None


def native_identity() -> dict[str, Any]:
    """The ``chronicler_agents`` extension module file and its SHA-256: the
    loaded one, else the first on the import path (found without importing)."""
    module = sys.modules.get("chronicler_agents.chronicler_agents")
    path = getattr(module, "__file__", None) if module is not None else None
    source = "imported"
    if path is None:
        source = "import_path"
        path = _find_native_extension()
    if path is None:
        return {"status": "absent"}
    path = Path(path)
    try:
        return {
            "status": "found",
            "source": source,
            "module_file": str(path),
            "bytes": path.stat().st_size,
            "sha256": file_sha256(path),
        }
    except OSError as exc:
        return {"status": "unreadable", "source": source, "module_file": str(path), "reason": str(exc)}


def _package_versions() -> dict[str, str | None]:
    from importlib import metadata

    versions: dict[str, str | None] = {}
    for name in IDENTITY_PACKAGES:
        try:
            versions[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            versions[name] = None
        except Exception:  # pragma: no cover - a broken distribution record
            versions[name] = None
    return versions


def environment_identity() -> dict[str, Any]:
    """Interpreter, platform, CPUs and the thread environment. ``cpu_count``
    follows ``PYTHON_CPU_COUNT``; ``affinity_cpu_count`` is the operating
    system's, which native thread pools (OpenBLAS) size themselves by."""
    process_cpu_count = getattr(os, "process_cpu_count", None)
    sched_getaffinity = getattr(os, "sched_getaffinity", None)
    return {
        "python": platform.python_version(),
        "implementation": platform.python_implementation(),
        "executable": sys.executable,
        "platform": platform.platform(),
        "machine": platform.machine(),
        "cpu_count": os.cpu_count(),
        "process_cpu_count": process_cpu_count() if process_cpu_count else None,
        "affinity_cpu_count": len(sched_getaffinity(0)) if sched_getaffinity else None,
        "thread_env": {name: os.environ.get(name) for name in THREAD_ENV_VARS},
        "packages": _package_versions(),
    }


def new_batch_manifest(
    args: Any,
    seeds: Iterable[int],
    *,
    tuning_overrides: dict | None = None,
    run_dirs: Iterable[str] | None = None,
) -> dict[str, Any]:
    """A ``running`` manifest for a batch of ``seeds`` (run directories
    ``seed_<seed>`` unless ``run_dirs`` names them)."""
    seeds = [int(seed) for seed in seeds]
    run_dirs = list(run_dirs) if run_dirs is not None else [f"seed_{seed}" for seed in seeds]
    if len(run_dirs) != len(seeds):
        raise ValueError("run_dirs must name one directory per seed")
    turns = getattr(args, "turns", None)
    parallel = getattr(args, "parallel", None)
    return {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "kind": MANIFEST_KIND,
        "status": "running",
        "created_at": _utc_now(),
        "completed_at": None,
        "seeds": seeds,
        "turns": int(turns) if isinstance(turns, int) and not isinstance(turns, bool) else None,
        "simulation": simulation_config(args, tuning_overrides),
        "outputs": output_config(args),
        "parallel_requested": _json_value(parallel),
        "environment": environment_identity(),
        "source": source_identity(),
        "native": native_identity(),
        "runs": [
            {"seed": seed, "dir": run_dir, "bundle": f"{run_dir}/{BUNDLE_FILENAME}", "total_turns": None, "files": None}
            for seed, run_dir in zip(seeds, run_dirs)
        ],
    }


def _validation_input_paths(seed_dir: Path) -> list[Path]:
    paths = [seed_dir / name for name in VALIDATION_INPUT_FILES if (seed_dir / name).is_file()]
    for name in VALIDATION_INPUT_DIRS:
        directory = seed_dir / name
        if directory.is_dir():
            paths.extend(sorted(path for path in directory.rglob("*") if path.is_file()))
    return paths


def record_batch_run(batch_dir: Path, manifest: dict[str, Any], index: int, total_turns: int | None) -> None:
    """Record run ``index``'s final turn and its validation inputs' hashes."""
    run = manifest["runs"][index]
    seed_dir = Path(batch_dir) / run["dir"]
    run["total_turns"] = int(total_turns) if total_turns is not None else None
    run["files"] = {
        path.relative_to(batch_dir).as_posix(): file_sha256(path) for path in _validation_input_paths(seed_dir)
    }


def finish_batch_manifest(batch_dir: Path, manifest: dict[str, Any], *, cancelled: bool = False) -> Path:
    """Mark the manifest ``complete`` (every run recorded) or ``cancelled`` and write it."""
    recorded = all(run["files"] is not None for run in manifest["runs"])
    manifest["status"] = "complete" if recorded and not cancelled else "cancelled"
    manifest["completed_at"] = _utc_now()
    return write_batch_manifest(batch_dir, manifest)


def write_batch_manifest(batch_dir: Path, manifest: dict[str, Any]) -> Path:
    path = Path(batch_dir) / MANIFEST_FILENAME
    atomic_write_json(path, manifest)
    return path


def load_batch_manifest(batch_dir: Path) -> dict[str, Any] | None:
    """The manifest of a batch directory, or None when it has none."""
    path = Path(batch_dir) / MANIFEST_FILENAME
    if not path.is_file():
        return None
    try:
        text = path.read_text(encoding="utf-8")
        if not text.strip():
            raise BatchManifestError(f"batch manifest {path} is empty: the batch claimed the directory and stopped")
        manifest = strict_json_loads(text, label="batch manifest JSON")
    except (OSError, UnicodeDecodeError, ArtifactIOError) as exc:
        raise BatchManifestError(f"could not read batch manifest {path}: {exc}") from exc
    if not isinstance(manifest, dict) or manifest.get("kind") != MANIFEST_KIND:
        raise BatchManifestError(f"{path} is not a Chronicler batch manifest")
    version = manifest.get("schema_version")
    if not isinstance(version, int) or isinstance(version, bool) or version > MANIFEST_SCHEMA_VERSION:
        raise BatchManifestError(f"unsupported batch manifest schema_version {version!r} in {path}")
    return manifest


def _seed_label(run: dict[str, Any]) -> str:
    return f"seed {run.get('seed')} ({run.get('dir')})"


def verify_batch_manifest(batch_dir: Path, manifest: dict[str, Any], bundle_paths: Iterable[Path]) -> list[str]:
    """Problems that make ``batch_dir`` differ from its manifest (empty when
    it matches): an incomplete batch, bundles the manifest does not list,
    missing runs, runs shorter than the requested turns, and validation
    inputs whose bytes changed since the batch wrote them."""
    batch_dir = Path(batch_dir)
    problems: list[str] = []
    status = manifest.get("status")
    if status != "complete":
        problems.append(f"batch status is {status!r}, not 'complete'")
    runs = manifest.get("runs")
    if not isinstance(runs, list) or not runs:
        return problems + ["manifest lists no runs"]
    expected = {str(run.get("bundle")): run for run in runs if isinstance(run, dict)}
    found = {Path(path).relative_to(batch_dir).as_posix() for path in bundle_paths}
    unlisted = sorted(found - set(expected))
    if unlisted:
        shown = ", ".join(unlisted[:5]) + (", ..." if len(unlisted) > 5 else "")
        problems.append(f"{len(unlisted)} bundle(s) not in the manifest: {shown}")
    missing = [run for bundle, run in expected.items() if bundle not in found]
    if missing:
        shown = ", ".join(_seed_label(run) for run in missing[:5]) + (", ..." if len(missing) > 5 else "")
        problems.append(f"{len(missing)} run(s) of the manifest have no bundle: {shown}")
    turns = manifest.get("turns")
    short = [
        run for run in expected.values()
        if isinstance(turns, int) and isinstance(run.get("total_turns"), int) and run["total_turns"] < turns
    ]
    if short:
        shown = ", ".join(f"{_seed_label(run)} ran {run['total_turns']}" for run in short[:5])
        problems.append(f"{len(short)} run(s) shorter than the requested {turns} turns: {shown}")
    changed: list[str] = []
    for bundle, run in expected.items():
        if bundle not in found:
            continue
        files = run.get("files")
        if not isinstance(files, dict) or bundle not in files:
            changed.append(f"{bundle} (not hashed)")
            continue
        for relative, sha in files.items():
            path = batch_dir / relative
            if not path.is_file():
                changed.append(f"{relative} (missing)")
            elif file_sha256(path) != sha:
                changed.append(f"{relative} (changed)")
    if changed:
        shown = ", ".join(changed[:5]) + (", ..." if len(changed) > 5 else "")
        problems.append(f"{len(changed)} validation input(s) differ from the manifest: {shown}")
    return problems


def batch_cohort(manifest: dict[str, Any], manifest_sha256: str | None = None) -> dict[str, Any]:
    """What a validation report records of its verified batch: the cohort
    (seeds, turns, simulation configuration) and the run identity."""
    native = manifest.get("native") if isinstance(manifest.get("native"), dict) else {}
    source = manifest.get("source") if isinstance(manifest.get("source"), dict) else {}
    environment = manifest.get("environment") if isinstance(manifest.get("environment"), dict) else {}
    return {
        "status": "verified",
        "manifest_sha256": manifest_sha256,
        "seeds": manifest.get("seeds"),
        "turns": manifest.get("turns"),
        "simulation": manifest.get("simulation"),
        "source": {"git_sha": source.get("git_sha"), "package_digest": source.get("package_digest")},
        "native_sha256": native.get("sha256"),
        "python": environment.get("python"),
        "platform": environment.get("platform"),
        "thread_env": environment.get("thread_env"),
    }


__all__ = [
    "BUNDLE_FILENAME",
    "BatchDestinationError",
    "BatchManifestError",
    "MANIFEST_FILENAME",
    "MANIFEST_KIND",
    "MANIFEST_SCHEMA_VERSION",
    "NON_SIMULATION_ARG_KEYS",
    "OUTPUT_ARG_KEYS",
    "SIMULATION_ARG_KEYS",
    "THREAD_ENV_VARS",
    "VALIDATION_INPUT_DIRS",
    "VALIDATION_INPUT_FILES",
    "WORLD_ARG_KEYS",
    "batch_cohort",
    "check_batch_destination",
    "environment_identity",
    "file_sha256",
    "finish_batch_manifest",
    "load_batch_manifest",
    "native_identity",
    "new_batch_manifest",
    "package_digest",
    "prepare_batch_dir",
    "record_batch_run",
    "simulation_config",
    "source_identity",
    "verify_batch_manifest",
    "write_batch_manifest",
]
