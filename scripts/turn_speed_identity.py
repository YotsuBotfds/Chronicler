#!/usr/bin/env python3
"""Byte-identity runs for performance work.

``run OUT_DIR [--case NAME ...] [--source-root SRC] [--native-root DIR] [--cli-arg ARG ...]``
    Run the case matrix below as CLI subprocesses (``PYTHONHASHSEED=0``,
    ``RAYON_NUM_THREADS=1``), one at a time, each into ``OUT_DIR/<case>``.
    ``--source-root`` puts another checkout's ``src`` first on
    ``PYTHONPATH`` and ``--native-root`` a saved ``chronicler_agents``
    package, which is how a base tree is run. ``--cli-arg`` adds a CLI
    argument to every case (a feature switch such as ``--no-scholarship``).

``compare BASE_DIR NEW_DIR [--faith-ids]``
    Every file of every case byte for byte (``chronicle_bundle.json``
    decoded, without ``metadata.generated_at``), as
    ``scripts/cities_identity.py compare``; each bundle's raw bytes are
    also compared with only the ``generated_at`` value blanked.

    ``--faith-ids`` compares a run with permanent faith ids
    (docs/integration/permanent-faiths.md) against one without: the new
    run's faith table is dropped and every field that newly carries a
    permanent id is projected back to the native slot that faith held,
    using the new run's own table (``FaithProjection``); state files are
    then compared decoded and the raw-bytes check is skipped. Each case
    prints the fields it changed and how many values.

``digest OUT_DIR GOLDEN.json [--build-receipt PATH] [--note TEXT]``
    Per case, the SHA-256 of every compared file's content (as ``compare``;
    a batch manifest without its clock, machine and commit fields), plus
    the runtime: ``compat`` (Python minor version, platform, Rust channel)
    and ``provenance`` (full versions, native SHA-256 and the native source
    digest from the build receipt).

``check OUT_DIR GOLDEN.json [--lane python|native] [--build-receipt PATH]``
    The identity gate against a committed golden
    (``tests/fixtures/identity/``): (1) provenance, the loaded extension is
    the receipt's and the receipt's native source is this checkout's; (2)
    ``compat`` equals the golden's; (3) output digests only. The native
    SHA-256 is never an equality condition: a rebuilt extension with
    identical outputs passes and prints ``native rebuilt: OLD -> NEW``.

``receipt PATH [--extension SO] [--wheel WHL]``
    The build receipt: extension and wheel SHA-256, native source digest
    (the build inputs in ``NATIVE_SOURCE_FILES``: Cargo files, ``build.rs``,
    the crate's ``pyproject.toml``, Cargo/rustup configuration when present,
    and ``src``), its inventory version and ``rustc --version``.

``GATE_PYTHON`` and ``GATE_NATIVE`` name the ``g_*`` cases of each lane;
``run`` without ``--case`` runs the original speed matrix only.

Scaled cases multiply region capacities and starting populations before
the first turn, as ``scripts/agent_scale_benchmark.py`` does.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import subprocess
import sys
import time

REPO_ROOT = Path(__file__).resolve().parents[1]

# name -> (CLI arguments, starting-agent target or 0)
CASES: dict[str, tuple[list[str], int]] = {
    "off_s42": (["--seed", "42", "--turns", "300", "--agents", "off"], 0),
    "off_s7": (["--seed", "7", "--turns", "300", "--agents", "off"], 0),
    "hybrid_s42": (["--seed", "42", "--turns", "200", "--agents", "hybrid",
                    "--validation-sidecar"], 0),
    "hybrid_s7": (["--seed", "7", "--turns", "200", "--agents", "hybrid",
                   "--validation-sidecar"], 0),
    "hybrid_s1234": (["--seed", "1234", "--turns", "200", "--agents", "hybrid"], 0),
    "proc48_hybrid_s42": (["--seed", "42", "--turns", "150", "--regions", "48", "--civs", "10",
                           "--agents", "hybrid", "--validation-sidecar"], 0),
    "proc48_off_s7": (["--seed", "7", "--turns", "200", "--regions", "48", "--civs", "10",
                       "--agents", "off"], 0),
    "scaled22k_s42": (["--seed", "42", "--turns", "30", "--regions", "12", "--civs", "4",
                       "--agents", "hybrid", "--validation-sidecar"], 18800),
    "scaled52k_s7": (["--seed", "7", "--turns", "20", "--regions", "12", "--civs", "4",
                      "--agents", "hybrid"], 43700),
    # Identity gate (``digest``/``check`` against tests/fixtures/identity/):
    # default switches on the off and hybrid paths plus the default-off
    # systems the source-witness pins used to guard.
    "g_off_s42": (["--seed", "42", "--turns", "120", "--agents", "off"], 0),
    "g_off_proc_s7": (["--seed", "7", "--turns", "100", "--regions", "48", "--civs", "10",
                       "--agents", "off"], 0),
    "g_hybrid_s42": (["--seed", "42", "--turns", "100", "--agents", "hybrid",
                      "--validation-sidecar"], 0),
    "g_grain_s7": (["--seed", "7", "--turns", "120", "--agents", "hybrid", "--grain-reserves",
                    "--grain-storage", "--grain-storage-policy", "maintain",
                    "--grain-storage-work-budget", "1", "--public-grain-shipments",
                    "--harvest-forecasts", "--transaction-receipts"], 0),
    "g_learning_s42": (["--seed", "42", "--turns", "120", "--regions", "24", "--civs", "6",
                        "--agents", "hybrid", "--scholarship", "--academy-services"], 0),
    "g_mobility_s1234": (["--seed", "1234", "--turns", "100", "--agents", "hybrid",
                          "--household-mobility-liquid-requirement", "25",
                          "--community-anchoring", "--capacity-aware-refugees"], 0),
    "g_scaled_s42": (["--seed", "42", "--turns", "30", "--regions", "12", "--civs", "4",
                      "--agents", "hybrid", "--validation-sidecar"], 18800),
    "g_batch_off": (["--batch", "3", "--seed", "100", "--turns", "40", "--agents", "off"], 0),
}
# The base-vs-new matrix ``run`` uses when no ``--case`` is given.
SPEED_CASES = tuple(name for name in CASES if not name.startswith("g_"))
# Identity-gate lanes: without the native extension, and with it (the off
# case again, where ``--agents off`` uses the native ecology simulator).
GATE_PYTHON = ("g_off_s42", "g_off_proc_s7", "g_batch_off")
GATE_NATIVE = ("g_hybrid_s42", "g_grain_s7", "g_learning_s42", "g_mobility_s1234",
               "g_scaled_s42", "g_off_s42")

_SCALED_RUNNER = r"""
import sys
import chronicler.main as cm
from chronicler.utils import sync_civ_population
target = int(sys.argv[1])
original = cm.generate_world
def scaled(*a, **k):
    world = original(*a, **k)
    mult = target / max(1, sum(r.population for r in world.regions))
    for region in world.regions:
        region.carrying_capacity = max(1, round(region.carrying_capacity * mult))
        region.population = round(region.population * mult)
    for civ in world.civilizations:
        sync_civ_population(civ, world)
    return world
cm.generate_world = scaled
sys.argv = ["chronicler"] + sys.argv[2:]
cm.main()
"""


def _env(source_root: Path | None, native_root: Path | None) -> dict:
    env = dict(os.environ)
    env["PYTHONHASHSEED"] = "0"
    env["RAYON_NUM_THREADS"] = "1"
    env["CHRONICLER_QUIET"] = "1"
    paths = []
    if native_root:
        paths.append(str(native_root.resolve()))
    if source_root:
        paths.append(str((source_root / "src").resolve()))
    if paths:
        env["PYTHONPATH"] = os.pathsep.join(paths)
    else:
        env.pop("PYTHONPATH", None)
    return env


_WHICH = (
    "import platform, sys\n"
    "print('python', platform.python_version(), sys.platform + '-' + platform.machine())\n"
    "import hashlib, chronicler, chronicler_agents.chronicler_agents as m\n"
    "print('chronicler', chronicler.__file__)\n"
    "print('native', m.__file__, hashlib.sha256(open(m.__file__, 'rb').read()).hexdigest())\n"
)


def run(out: Path, cases: list[str], source_root: Path | None, native_root: Path | None,
        extra: list[str] | None = None) -> int:
    env = _env(source_root, native_root)
    # Record which source tree and native build the runs used.
    if source_root and not (source_root / "src" / "chronicler" / "__init__.py").is_file():
        # The checkout root is wanted (``src`` is appended); a wrong path would
        # silently fall back to whatever ``chronicler`` the interpreter installs.
        raise SystemExit(f"--source-root {source_root} has no src/chronicler: pass the checkout root")
    which = subprocess.run([sys.executable, "-c", _WHICH], env=env, cwd=str(out),
                           capture_output=True, text=True)
    (out / "which.txt").write_text(which.stdout + which.stderr)
    print(which.stdout.strip(), flush=True)
    imported = next((line.split(" ", 1)[1] for line in which.stdout.splitlines() if line.startswith("chronicler ")),
                    None)
    if source_root and (imported is None or not Path(imported).resolve().is_relative_to(
            (source_root / "src").resolve())):
        raise SystemExit(f"runs would import chronicler from {imported}, not from {source_root / 'src'}")
    status = 0
    for name in cases:
        cli, target = CASES[name]
        case_dir = out / name
        case_dir.mkdir(parents=True, exist_ok=True)
        cli = cli + list(extra or []) + ["--simulate-only", "--output", str(case_dir / "chronicle.md"),
                     "--state", str(case_dir / "state.json")]
        if target:
            cmd = [sys.executable, "-c", _SCALED_RUNNER, str(target), *cli]
        else:
            cmd = [sys.executable, "-m", "chronicler.main", *cli]
        t0 = time.monotonic()
        with open(out / f"{name}.log", "w") as log:
            proc = subprocess.run(cmd, env=env, stdout=log, stderr=subprocess.STDOUT,
                                  cwd=str(out))
        print(f"{name}: exit {proc.returncode} in {time.monotonic() - t0:.0f} s", flush=True)
        status |= proc.returncode != 0
    return int(status)


_GENERATED_AT = re.compile(rb'"generated_at": ?"[^"]*"')


def _raw_bundle_problems(base: Path, new: Path) -> list[str]:
    """Raw bytes of every bundle, with only the wall-clock stamp blanked."""
    problems = []
    for a in sorted(base.rglob("chronicle_bundle.json")):
        b = new / a.relative_to(base)
        if not b.exists():
            continue
        if _GENERATED_AT.sub(b"", a.read_bytes()) != _GENERATED_AT.sub(b"", b.read_bytes()):
            problems.append(f"raw bytes differ: {a.relative_to(base)}")
    return problems


_TEMPLE_TEXT = re.compile(r"^Temple of faith (\d+) ")
_TEMPLE_ID = re.compile(r"temple:(\d+)")


class FaithProjection:
    """A run's permanent faith ids projected back to native slots.

    Built from the run's own ``faiths`` table (index = permanent id, ``slot``
    the slot it held), it rewrites, in a decoded file of that run, exactly
    the fields that carry a permanent id since docs/integration/permanent-faiths.md
    and drops the table: movements (``faith``, ``schism_from``,
    ``schism_to``, a schism's ``successor``), tolerations (``faith``, in the
    world state and the history's reform rows), conversion objectives
    (``conversion_faith_id``), seats (``faith``), ``Temple of faith <id>``
    descriptions, temple chronicler ids (``temple:<id>``) and ``faith``, and
    the faith words' ``ref``. ``counts`` holds the values changed per field.
    """

    def __init__(self, table: list[dict]):
        self.slot = {k: rec["slot"] for k, rec in enumerate(table)}
        self.released = sum(1 for rec in table if rec.get("released_turn") is not None)
        self.size = len(table)
        from collections import Counter
        self.counts: Counter = Counter()

    def _map(self, value, field: str):
        if isinstance(value, int) and not isinstance(value, bool) and value in self.slot \
                and self.slot[value] != value:
            self.counts[field] += 1
            return self.slot[value]
        return value

    def _put(self, obj, key: str, field: str) -> None:
        if isinstance(obj, dict) and key in obj:
            obj[key] = self._map(obj[key], field)

    def _text(self, desc, field: str):
        if not isinstance(desc, str):
            return desc
        m = _TEMPLE_TEXT.match(desc)
        if m is None:
            return desc
        new = self._map(int(m.group(1)), field)
        return desc if new == int(m.group(1)) else f"Temple of faith {new} " + desc[m.end():]

    def _ids(self, value, field: str):
        """Temple chronicler ids anywhere in a value (strings and dict keys)."""
        if isinstance(value, str):
            def sub(m):
                return f"temple:{self._map(int(m.group(1)), field)}"
            return _TEMPLE_ID.sub(sub, value)
        if isinstance(value, list):
            return [self._ids(v, field) for v in value]
        if isinstance(value, dict):
            out = {self._ids(k, field): self._ids(v, field) for k, v in value.items()}
            if out.get("kind") == "temple" and "faith" in out:
                out["faith"] = self._map(out["faith"], "historiography.faith")
            return out
        return value

    def _world(self, ws: dict, where: str) -> None:
        if ws.pop("faiths", None) is not None:
            self.counts[f"{where}.faiths (table dropped)"] += 1
        am = ws.get("agent_movements") or {}
        for m in am.get("movements") or []:
            self._put(m, "faith", "movements.faith")
            self._put(m, "schism_from", "movements.schism_from")
            self._put(m, "schism_to", "movements.schism_to")
            if m.get("end") == 4:  # agent_movements_state.SCHISM
                self._put(m, "successor", "movements.successor")
        for r in am.get("reforms") or []:
            if r.get("kind") == 2:  # TOLERATION
                self._put(r, "faith", "reforms.faith")
        for rec in ((ws.get("gp_agendas") or {}).get("records") or {}).values():
            self._put(rec.get("agenda"), "conversion_faith_id", "gp_agendas.conversion_faith_id")
        for civ in ws.get("civilizations") or []:
            for a in (civ.get("governance") or {}).get("ambitions") or []:
                self._put(a, "conversion_faith_id", "governance.conversion_faith_id")
        for seat in (ws.get("scholarship") or {}).get("seats") or []:
            self._put(seat, "faith", "scholarship.faith")
        for ev in ws.get("events_timeline") or []:
            ev["description"] = self._text(ev.get("description"), "events.temple_description")

    def _words(self, rows, columns) -> None:
        ki, ri = columns.index("kind"), columns.index("ref")
        for row in rows:
            if row[ki] == "faith":
                row[ri] = self._map(row[ri], "languages.words.ref")

    def __call__(self, name: str, data: dict) -> None:
        if name == "chronicle_bundle.json":
            self._world(data["world_state"], "world_state")
            for snap in data.get("history") or []:
                for row in (snap.get("agent_movements") or {}).get("reforms") or []:
                    self._put(row, "faith", "history.reforms.faith")
            for ev in data.get("events_timeline") or []:
                ev["description"] = self._text(ev.get("description"), "events.temple_description")
            if isinstance(data.get("historiography"), dict):
                data["historiography"] = self._ids(data["historiography"], "historiography.temple_id")
            langs = data.get("languages")
            if isinstance(langs, dict):
                self._words(langs.get("words") or [], list(langs.get("word_columns") or []))
                for f in langs.get("faiths") or []:
                    self._put(f, "faith", "languages.faiths")
        elif name.endswith(".historiography.json"):
            data.update(self._ids(data, "historiography.temple_id"))
        elif name.endswith(".languages.json"):
            st = data.get("state") if isinstance(data.get("state"), dict) else data
            for w in st.get("words") or []:
                if w.get("kind") == "faith":
                    self._put(w, "ref", "languages.words.ref")
            if isinstance(st.get("faiths"), dict):
                st["faiths"] = {str(self._map(int(k), "languages.faiths")): v
                                for k, v in st["faiths"].items()}
        elif name.startswith("state") and name.endswith(".json"):
            self._world(data, "state")


def _differing_parts(base_file: Path, new_file: Path, projection: FaithProjection | None) -> list[str]:
    """The top-level keys (and ``world_state`` keys) in which two decoded
    JSON files differ, the new one projected."""
    import json
    from chronicler.bundle_codec import load_bundle

    def load(path: Path):
        if path.name == "chronicle_bundle.json":
            data = load_bundle(path)
            data.get("metadata", {}).pop("generated_at", None)
        else:
            data = json.loads(path.read_text(encoding="utf-8"))
        return data

    a, b = load(base_file), load(new_file)
    if projection is not None:
        projection(new_file.name, b)
    parts = []
    for key in sorted(set(a) | set(b)):
        if a.get(key) == b.get(key):
            continue
        if key in ("world_state", "state") and isinstance(a.get(key), dict) and isinstance(b.get(key), dict):
            sub = sorted(k for k in set(a[key]) | set(b[key]) if a[key].get(k) != b[key].get(k))
            parts.extend(f"{key}.{k}" for k in sub)
        else:
            parts.append(key)
    return parts


def _faith_projection(case_dir: Path) -> FaithProjection | None:
    """The projection of a case's run, from its state's faith table."""
    import json
    state = case_dir / "state.json"
    if not state.exists():
        return None
    table = json.loads(state.read_text(encoding="utf-8")).get("faiths") or []
    return FaithProjection(table)


def compare(base: Path, new: Path, faith_ids: bool = False) -> int:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    from cities_identity import compare as compare_dirs

    total_checked = 0
    total_problems = 0
    cases = sorted(p.name for p in base.iterdir() if p.is_dir())
    for name in cases:
        projection = _faith_projection(new / name) if faith_ids else None
        checked, problems = compare_dirs(base / name, new / name, normalize=projection)
        if not faith_ids:
            problems += _raw_bundle_problems(base / name, new / name)
        total_checked += checked
        total_problems += len(problems)
        print(f"{name}: {checked} files, {len(problems)} differences")
        if projection is not None:
            print(f"  faith table: {projection.size} faiths, {projection.released} released; "
                  f"projected: {dict(sorted(projection.counts.items())) or 'nothing'}")
        for line in problems:
            print(f"  {line}")
            if faith_ids and line.startswith("differs: ") and line.endswith(")"):
                rel = line[len("differs: "):].rsplit(" (", 1)[0]
                if rel.endswith(".json"):
                    parts = _differing_parts(base / name / rel, new / name / rel,
                                             _faith_projection(new / name))
                    print(f"    in: {', '.join(parts) or '(key order only)'}")
    print(f"{len(cases)} cases, {total_checked} files compared, {total_problems} differences")
    return 0 if total_checked and not total_problems else 1


# --- identity gate: digest / check against committed goldens -----------------------

# Fields of a batch manifest that describe the machine, the clock or the
# commit rather than the runs (``chronicler.batch_manifest``).
_BATCH_MANIFEST_VOLATILE = ("created_at", "completed_at", "environment", "source", "native")
# The native build inputs a receipt's ``source_digest`` covers: the crate's
# manifest and lockfile, its build script (it selects the ``chronicler_avx512``
# cfg of the spatial kernel), its maturin configuration (``pyproject.toml``:
# the extension features) and its ``src`` tree, plus Cargo and rustup
# configuration in the checkout when present (an optional file that appears
# changes the digest because its path is listed).
NATIVE_SOURCE_FILES = ("chronicler-agents/Cargo.toml", "chronicler-agents/Cargo.lock",
                       "chronicler-agents/build.rs", "chronicler-agents/pyproject.toml")
NATIVE_OPTIONAL_FILES = tuple(f"{base}{name}" for base in ("", "chronicler-agents/") for name in (
    ".cargo/config", ".cargo/config.toml", "rust-toolchain", "rust-toolchain.toml"))
NATIVE_SOURCE_DIR = "chronicler-agents/src"
# Version of that inventory, recorded in each receipt. Version 1 (no
# ``source_inventory`` key) hashed the manifest, lockfile and ``src`` only, so
# its digests cannot show a stale build script or packaging change: ``check``
# refuses such a receipt and asks for a new one. Goldens keep their recorded
# digest as provenance only; it is never compared.
NATIVE_SOURCE_INVENTORY = 2
INCOMPATIBLE = "incompatible runtime: re-capture the goldens in a reviewed PR"


def _sha256_bytes(data: bytes) -> str:
    import hashlib
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(Path(path).read_bytes())


def _cities_identity():
    if str(REPO_ROOT / "scripts") not in sys.path:
        sys.path.insert(0, str(REPO_ROOT / "scripts"))
    import cities_identity
    return cities_identity


def _batch_manifest_content(path: Path) -> bytes:
    """A batch manifest without its machine, clock and commit fields; paths
    under its directory and the digests of its files become labels (the
    approach of ``tests/test_validation_parity.py::_Normalizer``)."""
    import json
    root = path.parent
    data = json.loads(path.read_text(encoding="utf-8"))
    for key in _BATCH_MANIFEST_VOLATILE:
        data.pop(key, None)
    text = json.dumps(data, sort_keys=True)
    replacements = []
    for item in [root, *sorted(root.rglob("*"))]:
        label = "<WS>" + ("/" + item.relative_to(root).as_posix() if item != root else "")
        replacements.append((json.dumps(str(item))[1:-1], label))
        if item.is_file() and item != path:
            replacements.append((_sha256_file(item), f"<sha256:{label[5:]}>"))
    replacements.sort(key=lambda pair: len(pair[0]), reverse=True)
    for old, new in replacements:
        text = text.replace(old, new)
    return text.encode("utf-8")


def output_digests(case_dir: Path) -> dict[str, str]:
    """``relpath -> sha256`` of every compared file of one case directory:
    the content ``compare`` compares (``cities_identity._content``: bundles
    decoded, ``metadata.generated_at`` dropped), skipping ``.log`` files and
    ``run_manifest.json``; a batch manifest is projected first."""
    ci = _cities_identity()
    digests = {}
    for path in sorted(p for p in case_dir.rglob("*") if p.is_file()):
        if path.name in ci.IGNORED_NAMES or path.suffix == ".log":
            continue
        if path.name == "batch_manifest.json":
            content = _batch_manifest_content(path)
        else:
            content = ci._content(path, False)
        digests[path.relative_to(case_dir).as_posix()] = _sha256_bytes(content)
    return digests


def native_source_digest(root: Path) -> str:
    """SHA-256 over the native build inputs of a checkout (``NATIVE_SOURCE_FILES``,
    the ``NATIVE_OPTIONAL_FILES`` present and the ``src`` tree): each file's
    relative path and content digest, in that order."""
    root = Path(root)
    rels = list(NATIVE_SOURCE_FILES) + [rel for rel in NATIVE_OPTIONAL_FILES if (root / rel).is_file()]
    rels += sorted(
        p.relative_to(root).as_posix() for p in (root / NATIVE_SOURCE_DIR).rglob("*") if p.is_file())
    lines = []
    for rel in rels:
        path = root / rel
        if not path.is_file():
            raise FileNotFoundError(f"native source file missing: {path}")
        lines.append(f"{rel}\0{_sha256_file(path)}\n")
    return _sha256_bytes("".join(lines).encode("utf-8"))


def _rust_channel(rustc: str | None) -> str | None:
    if not rustc:
        return None
    version = rustc.split()[1] if len(rustc.split()) > 1 else rustc
    for channel in ("nightly", "beta"):
        if channel in version:
            return channel
    return "stable"


def loaded_runtime(out: Path) -> dict:
    """What the runs in ``out`` loaded, from the ``which.txt`` that ``run``
    writes: Python version and platform, and the native extension's path and
    SHA-256 (``None`` when the extension was absent)."""
    import platform as _platform
    info = {"python_full": _platform.python_version(),
            "platform": f"{sys.platform}-{_platform.machine()}",
            "native_path": None, "native_sha256": None}
    which = Path(out) / "which.txt"
    for line in (which.read_text(encoding="utf-8").splitlines() if which.exists() else []):
        parts = line.split()
        if parts[:1] == ["python"] and len(parts) == 3:
            info["python_full"], info["platform"] = parts[1], parts[2]
        elif parts[:1] == ["native"] and len(parts) >= 3:
            info["native_path"], info["native_sha256"] = " ".join(parts[1:-1]), parts[-1]
    return info


def environment(out: Path, receipt: dict | None) -> dict:
    runtime = loaded_runtime(out)
    native = runtime["native_sha256"]
    rustc = (receipt or {}).get("rustc") if native else None
    python_minor = ".".join(runtime["python_full"].split(".")[:2])
    return {
        "compat": {"python_minor": python_minor, "platform": runtime["platform"],
                   "rust_channel": _rust_channel(rustc)},
        "provenance": {"python_full": runtime["python_full"], "rustc": rustc,
                       "native_sha256": native,
                       "native_source_digest": (receipt or {}).get("source_digest") if native else None,
                       "native_source_inventory": (receipt or {}).get("source_inventory") if native else None},
    }


def digest_tree(out: Path, receipt: dict | None = None) -> dict:
    out = Path(out)
    cases = {p.name: output_digests(p) for p in sorted(out.iterdir()) if p.is_dir()}
    return {"environment": environment(out, receipt), "cases": cases}


def _load_json(path: Path | None) -> dict | None:
    import json
    return None if path is None else json.loads(Path(path).read_text(encoding="utf-8"))


def digest(out: Path, golden: Path, receipt_path: Path | None = None, note: str | None = None) -> int:
    import json
    data = digest_tree(out, _load_json(receipt_path))
    if note:
        data["environment"]["provenance"]["note"] = note
    Path(golden).write_text(json.dumps(data, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    files = sum(len(v) for v in data["cases"].values())
    print(f"{len(data['cases'])} cases, {files} files digested -> {golden}")
    return 0


def provenance_problems(out: Path, lane: str, receipt: dict | None, source_root: Path) -> list[str]:
    """The build must belong to the source under test (step 1 of ``check``)."""
    runtime = loaded_runtime(out)
    loaded = runtime["native_sha256"]
    if lane == "python":
        return [] if loaded is None else [f"provenance: python lane loaded a native extension ({loaded})"]
    if loaded is None:
        return ["provenance: native lane runs did not load chronicler_agents (see which.txt)"]
    if receipt is None:
        return ["provenance: native lane needs --build-receipt"]
    problems = []
    if receipt.get("extension_sha256") != loaded:
        problems.append(f"provenance: loaded extension {loaded} is not the receipt's "
                        f"{receipt.get('extension_sha256')}")
    inventory = receipt.get("source_inventory", 1)
    if inventory != NATIVE_SOURCE_INVENTORY:
        problems.append(f"provenance: receipt digests native source inventory {inventory}, "
                        f"this checker uses {NATIVE_SOURCE_INVENTORY} (build script and packaging "
                        f"included): take a new receipt from the build")
        return problems
    candidate = native_source_digest(source_root)
    if receipt.get("source_digest") != candidate:
        problems.append(f"provenance: receipt built from native source {receipt.get('source_digest')}, "
                        f"checkout has {candidate}")
    return problems


def identity_problems(golden_cases: dict, run_cases: dict) -> tuple[int, list[str]]:
    checked, problems = 0, []
    for case in sorted(set(golden_cases) | set(run_cases)):
        if case not in run_cases:
            problems.append(f"only in golden: {case}")
            continue
        if case not in golden_cases:
            problems.append(f"only in run: {case}")
            continue
        want, got = golden_cases[case], run_cases[case]
        for rel in sorted(set(want) ^ set(got)):
            problems.append(f"only in {'golden' if rel in want else 'run'}: {case}/{rel}")
        for rel in sorted(set(want) & set(got)):
            checked += 1
            if want[rel] != got[rel]:
                problems.append(f"differs: {case}/{rel} ({want[rel][:12]} != {got[rel][:12]})")
    return checked, problems


def check(out: Path, golden_path: Path, lane: str = "python", receipt_path: Path | None = None,
          source_root: Path | None = None) -> int:
    """Provenance, then compatibility, then output identity. The native
    SHA-256 is provenance only: a rebuilt extension with identical outputs passes."""
    golden = _load_json(golden_path)
    receipt = _load_json(receipt_path)
    problems = provenance_problems(out, lane, receipt, Path(source_root or REPO_ROOT))
    if problems:
        for line in problems:
            print(line)
        print("refused: the build does not belong to the source under test")
        return 1
    candidate = digest_tree(out, receipt)
    want_env, got_env = golden["environment"], candidate["environment"]
    if want_env["compat"] != got_env["compat"]:
        print(f"{INCOMPATIBLE} (golden {want_env['compat']}, run {got_env['compat']})")
        return 1
    old_native = want_env["provenance"].get("native_sha256")
    new_native = got_env["provenance"].get("native_sha256")
    if old_native and new_native and old_native != new_native:
        print(f"native rebuilt: {old_native} -> {new_native}")
    checked, problems = identity_problems(golden["cases"], candidate["cases"])
    for line in problems:
        print(f"  {line}")
    print(f"{len(golden['cases'])} golden cases, {checked} files checked, {len(problems)} differences")
    return 0 if checked and not problems else 1


def write_receipt(path: Path, extension: Path, source_root: Path, wheel: Path | None = None,
                  rustc: str | None = None) -> dict:
    """The native build receipt ``check --build-receipt`` reads."""
    import json
    receipt = {"extension": str(extension), "extension_sha256": _sha256_file(extension),
               "wheel": None if wheel is None else Path(wheel).name,
               "wheel_sha256": None if wheel is None else _sha256_file(wheel),
               "source_digest": native_source_digest(source_root),
               "source_inventory": NATIVE_SOURCE_INVENTORY, "rustc": rustc}
    Path(path).write_text(json.dumps(receipt, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return receipt


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("out", type=Path)
    r.add_argument("--case", action="append", choices=sorted(CASES))
    r.add_argument("--source-root", type=Path)
    r.add_argument("--native-root", type=Path)
    r.add_argument("--cli-arg", action="append", default=[],
                   help="extra CLI argument for every case (repeatable)")
    c = sub.add_parser("compare")
    c.add_argument("base", type=Path)
    c.add_argument("new", type=Path)
    c.add_argument("--faith-ids", action="store_true",
                   help="project the new run's permanent faith ids back to slots (see above)")
    d = sub.add_parser("digest")
    d.add_argument("out", type=Path)
    d.add_argument("golden", type=Path)
    d.add_argument("--build-receipt", type=Path)
    d.add_argument("--note", help="free text kept in the golden's provenance (where it was captured)")
    k = sub.add_parser("check")
    k.add_argument("out", type=Path)
    k.add_argument("golden", type=Path)
    k.add_argument("--lane", choices=("python", "native"), default="python")
    k.add_argument("--build-receipt", type=Path)
    k.add_argument("--source-root", type=Path,
                   help="checkout whose native source the receipt must match (default: this one)")
    b = sub.add_parser("receipt")
    b.add_argument("path", type=Path)
    b.add_argument("--extension", type=Path,
                   help="installed extension file (default: the one this interpreter imports)")
    b.add_argument("--wheel", type=Path)
    b.add_argument("--source-root", type=Path, default=REPO_ROOT)
    a = p.parse_args(argv)
    if a.cmd == "run":
        a.out.mkdir(parents=True, exist_ok=True)
        return run(a.out.resolve(), a.case or list(SPEED_CASES), a.source_root, a.native_root, a.cli_arg)
    if a.cmd == "digest":
        return digest(a.out, a.golden, a.build_receipt, a.note)
    if a.cmd == "check":
        return check(a.out, a.golden, a.lane, a.build_receipt, a.source_root)
    if a.cmd == "receipt":
        extension = a.extension
        if extension is None:
            import importlib
            extension = Path(importlib.import_module("chronicler_agents.chronicler_agents").__file__)
        rustc = subprocess.run(["rustc", "--version"], capture_output=True, text=True).stdout.strip() or None
        receipt = write_receipt(a.path, extension, a.source_root, a.wheel, rustc)
        print(f"extension {receipt['extension_sha256']}, native source {receipt['source_digest']}, {rustc}")
        return 0
    return compare(a.base, a.new, faith_ids=a.faith_ids)


if __name__ == "__main__":
    sys.exit(main())
