"""Fixed, read-only comparison of the four registered cloud full-gate cohorts.

Run this file from the control checkout with --candidate-source naming the
separate detached d028 checkout. No simulation, native loading or oracle scoring
runs here. Original reports and gate decisions are never rewritten.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys

BASELINE = "2f9d618b70f3304c02dcaeef12996b4a99e074c0"
CANDIDATE = "d0281e5f57c508f27cea1676f36e0e6ed1225c9d"
CRATE_TREE = "a4703ef4e9a21b5dbb194d318536a46e6ca8b71c"
FROZEN_FILES = {
    "src/chronicler/validation_compare.py": "cc45f89f9d64cd5dd1714cadf5b598f6c206105998583435f95c3873ea9f4a92",
    "src/chronicler/validation_gate.py": "d213cf625291998a7fb56fd4ee7ebe08ee4714b02effefc7310e263748d9b4d1",
    "src/chronicler/artifact_io.py": "885eb95fb93187d11f2210f726df8ba58a9db13c10f305efac2e92a55f93ab4f",
    "src/chronicler/__init__.py": "9832de075b76097aafbf424ddd6ca6d7fbae24ed8fc9e271e7820b357b49e6fd"
}
MAX_FILE_BYTES = 32 * 1024 * 1024
MAX_ROOT_BYTES = 128 * 1024 * 1024
MAX_FILES = 64
MAX_RAW_ENTRIES = 100000
CLASSES = ("AgentSimulator", "EcologySimulator", "PoliticsSimulator")
ENV_KEYS = ("python", "implementation", "machine", "thread_env", "packages", "affinity_cpu_count")
SIMULATION_ARGUMENTS = ["worldgen","regions","civs","scenario","turns","reflection_interval","agents","agent_scale_mode","decision_ablation","ablation_start_turn","mutual_aid","fisheries","campaigns","governance","contact_ledger","epidemiology","finance","diplomacy","techniques","maritime","gp_agendas","nomads","cities","agent_movements","guilds","historiography","languages","scholarship","grain_reserves","community_anchoring","capacity_aware_refugees","health_care","harvest_forecasts","ritual_gatherings","scientific_claims","transaction_receipts","domestic_credit","tuning","preset","aggression_bias","tech_diffusion_rate","resource_abundance","trade_friction","severity_multiplier","cultural_drift_speed","religion_intensity","secession_likelihood"]
REPORT_FILES = (
    "validate_report_full.json", "gate_decision_full.json", "gate_summary_full.md",
    "run_manifest.json", "batch_manifest.json", "ablation_manifest.json",
)
INDEXED_FILES = frozenset(
    ("provenance.json", "raw-inventory.json", "build-manifest.json")
    + tuple("report/" + name for name in REPORT_FILES)
)
ALL_FILES = INDEXED_FILES | {"result.json", "artifact-index.json"}
ROLES = ("template-baseline", "template-candidate", "procedural-baseline", "procedural-candidate")
FEATURE_ARGUMENTS = (
    "campaigns", "governance", "contact_ledger", "finance", "fisheries", "mutual_aid",
    "epidemiology", "diplomacy", "techniques", "maritime", "gp_agendas",
    "nomads", "cities", "agent_movements", "guilds", "scholarship",
    "grain_reserves", "community_anchoring", "capacity_aware_refugees",
    "domestic_credit", "historiography", "languages", "fishery_aid",
    "health_care", "harvest_forecasts", "ritual_gatherings", "scientific_claims",
    "transaction_receipts",
)


class ComparisonInputError(ValueError):
    """An incomplete, inconsistent or aliased input cannot qualify."""


def _fail(message):
    raise ComparisonInputError(message)


def _encoded(value):
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")


def _eq(actual, expected, label):
    if _encoded(actual) != _encoded(expected):
        _fail(label + " differs from the registered value")


def _hash(value, label):
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        _fail(label + " must be a lowercase SHA-256")
    return value


def _int(value, label, *, minimum=0):
    if type(value) is not int or value < minimum:
        _fail(label + " must be an integer >= " + str(minimum))
    return value


def _schema(value, kind):
    if not isinstance(value, dict):
        _fail(kind + " must be an object")
    _eq(value.get("schema_version"), 1, kind + " schema")
    _eq(value.get("kind"), kind, kind + " kind")


def _relative(name):
    if not isinstance(name, str) or not name or "\\" in name:
        _fail("invalid artifact path")
    pure = PurePosixPath(name)
    if pure.is_absolute() or pure.as_posix() != name or any(p in ("", ".", "..") for p in pure.parts):
        _fail("escaping or noncanonical artifact path")
    if ":" in pure.parts[0]:
        _fail("invalid artifact path drive")
    return name


def _absolute(path):
    path = Path(os.path.abspath(path))
    if path.resolve() != path:
        _fail("symlink path aliases are not accepted: " + str(path))
    return path


def _under(path, root):
    return path == root or root in path.parents


def _identity(st):
    return (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns)


def _read(path, *, limit=MAX_FILE_BYTES):
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode):
        _fail("not a regular artifact: " + str(path))
    if before.st_size > limit:
        _fail("artifact exceeds byte bound: " + str(path))
    with path.open("rb") as stream:
        if _identity(os.fstat(stream.fileno())) != _identity(before):
            _fail("artifact changed before reading")
        raw = stream.read(limit + 1)
        after = os.fstat(stream.fileno())
    if len(raw) > limit or len(raw) != before.st_size or _identity(after) != _identity(before):
        _fail("artifact changed or grew while reading")
    if _identity(path.lstat()) != _identity(before):
        _fail("artifact path changed while reading")
    return raw, _identity(before)


def _json(raw, label):
    def pairs(items):
        out = {}
        for key, value in items:
            if key in out:
                _fail("duplicate JSON key in " + label)
            out[key] = value
        return out

    def finite(value):
        number = float(value)
        if not math.isfinite(number):
            _fail("non-finite JSON number in " + label)
        return number

    def constant(value):
        _fail("non-finite JSON constant in " + label)

    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=pairs,
                          parse_constant=constant, parse_float=finite)
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ComparisonInputError("invalid JSON: " + label) from exc


def _inventory(root, inodes):
    if not root.is_dir():
        _fail("artifact root must be a directory")
    files = {}
    total = 0
    pending = [root]
    entries = 0
    while pending:
        directory = pending.pop()
        for path in sorted(directory.iterdir()):
            entries += 1
            if entries > MAX_FILES + 1:
                _fail("artifact entry bound exceeded")
            st = path.lstat()
            if stat.S_ISDIR(st.st_mode):
                if path != root / "report":
                    _fail("unexpected artifact directory")
                pending.append(path)
                continue
            name = _relative(path.relative_to(root).as_posix())
            if name not in ALL_FILES:
                _fail("unexpected artifact file: " + name)
            if st.st_size > MAX_ROOT_BYTES - total or len(files) >= MAX_FILES:
                _fail("artifact root byte/file bound exceeded before reading")
            raw, ident = _read(path)
            inode = ident[:2]
            if inode in inodes:
                _fail("hard-linked or repeated artifact inputs")
            inodes.add(inode)
            total += len(raw)
            if len(files) >= MAX_FILES or total > MAX_ROOT_BYTES:
                _fail("artifact root byte/file bound exceeded")
            files[name] = {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
                           "identity": ident}
    _eq(sorted(files), sorted(ALL_FILES), "complete artifact file set")
    return files


def _check_index_records(records, label, *, bound=MAX_FILES):
    if not isinstance(records, dict) or len(records) > bound:
        _fail(label + " has invalid file bounds")
    for name, record in records.items():
        _relative(name)
        if not isinstance(record, dict) or set(record) != {"bytes", "sha256"}:
            _fail(label + " has a malformed file record")
        _int(record["bytes"], label + " byte count")
        _hash(record["sha256"], label + " file hash")


def expected_cohort(worldgen):
    procedural = worldgen == "procedural"
    forks = list(range(100, 261, 20)) if procedural else [100, 200, 300, 400]
    return {
        "profile": "full", "worldgen": worldgen, "seed_start": 42,
        "seed_count": 100 if procedural else 200, "turns": 300 if procedural else 500,
        "regions": 32 if procedural else 8, "civs": 10 if procedural else 4,
        "parallel": 2, "cpus": 2, "threads": 1,
        "arms": ["needs", "kin_roots"], "fork_turns": forks,
        "checkpoint_turns": [t + 1 for t in forks],
        "fork_count": (100 if procedural else 200) * len(forks) * 2,
        "window_turns": 20, "require_strict_regression": True,
        "causal_oracles_required": False,
    }


def registered_simulation(expected):
    # main.py resolves these defaults before batch_manifest.simulation_config.
    # The complete key set is frozen from d028; missing or extra keys refuse.
    result = {key: None for key in SIMULATION_ARGUMENTS}
    result.update(turns=expected["turns"], agents="hybrid", reflection_interval=10,
                  regions=expected["regions"], civs=expected["civs"],
                  worldgen="procedural" if expected["worldgen"] == "procedural" else None,
                  tuning_overrides={})
    return result


def _env_signature(environment):
    if not isinstance(environment, dict) or any(k not in environment for k in ENV_KEYS):
        _fail("runtime environment is incomplete")
    for key in ("python", "implementation", "machine"):
        if not isinstance(environment[key], str) or not environment[key]:
            _fail("runtime environment has an invalid " + key)
    if not isinstance(environment["packages"], dict) or not environment["packages"]:
        _fail("runtime package versions are missing")
    _eq(sorted(environment["packages"]), sorted(("numpy", "scipy", "pyarrow", "pydantic", "arro3-core", "chronicler-agents")),
        "runtime package identity set")
    if any(not isinstance(v, str) or not v for v in environment["packages"].values()):
        _fail("runtime package version is unavailable")
    _eq(environment["affinity_cpu_count"], 2, "runtime CPU affinity count")
    threads = environment["thread_env"]
    if not isinstance(threads, dict):
        _fail("thread environment is missing")
    for key in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "BLIS_NUM_THREADS",
                "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS", "GOTO_NUM_THREADS", "RAYON_NUM_THREADS"):
        _eq(threads.get(key), "1", key)
    _eq(threads.get("PYTHONHASHSEED"), "0", "PYTHONHASHSEED")
    _eq(threads.get("PYTHON_CPU_COUNT"), "2", "PYTHON_CPU_COUNT")
    return {key: environment[key] for key in ENV_KEYS}


def _schemas(schemas):
    if not isinstance(schemas, dict) or set(schemas) != set(CLASSES):
        _fail("all three compiled state schemas must be recorded")
    for name, value in schemas.items():
        if not isinstance(value, dict) or set(value) != {"version", "fingerprint", "schema_sha256"}:
            _fail("invalid compiled schema record")
        _int(value["version"], name + " schema version")
        if not isinstance(value["fingerprint"], str) or not value["fingerprint"]:
            _fail("missing compiled state fingerprint")
        _hash(value["schema_sha256"], name + " raw schema hash")


def _builder(build, build_hash, run_id, attempt):
    _schema(build, "chronicler-cloud-full-gate-build")
    for key, expected in (
        ("qualified", True), ("baseline_sha", BASELINE), ("candidate_sha", CANDIDATE),
        ("github_run_id", run_id), ("github_run_attempt", attempt), ("crate_tree", CRATE_TREE),
    ):
        _eq(build.get(key), expected, "builder " + key)
    if not isinstance(build.get("control_sha"), str) or re.fullmatch(r"[0-9a-f]{40}", build["control_sha"]) is None:
        _fail("builder control SHA is missing")
    for key in ("lock_sha256", "pyproject_sha256", "source_snapshot_before_sha256", "source_snapshot_after_sha256"):
        _hash(build.get(key), "builder " + key)
    _eq(build["source_snapshot_before_sha256"], build["source_snapshot_after_sha256"],
        "builder source stability")
    if not isinstance(build.get("python_version"), str) or re.fullmatch(r"3\.13\.[0-9]+", build["python_version"]) is None:
        _fail("builder must record its actual Python 3.13 patch")
    _eq(build.get("budget_seconds"), 80 * 60, "builder resource budget")
    elapsed = build.get("elapsed_wall_seconds")
    if (type(elapsed) not in (int, float) or not math.isfinite(elapsed)
            or not 0 <= elapsed <= 80 * 60):
        _fail("builder resource budget was not met")
    for key in ("error", "final_identity_error", "light_error"):
        if key in build:
            _fail("builder retained an execution/finalization error")
    native, wheel = build.get("native"), build.get("wheel")
    if not isinstance(native, dict) or not isinstance(wheel, dict):
        _fail("builder native/wheel identity is missing")
    _hash(native.get("sha256"), "compiled extension")
    _schemas(native.get("schemas"))
    _hash(wheel.get("sha256"), "wheel")
    _int(wheel.get("bytes"), "wheel bytes", minimum=1)
    _eq(wheel.get("native_sha256"), native["sha256"], "wheel native member")
    if not isinstance(wheel.get("filename"), str) or Path(wheel["filename"]).name != wheel["filename"] or not wheel["filename"].endswith(".whl"):
        _fail("invalid wheel filename")
    _relative(wheel.get("native_member"))
    env = _env_signature(build.get("environment"))
    _eq(env["python"], build["python_version"], "builder interpreter patch")
    return {"build_manifest_sha256": build_hash, "wheel_sha256": wheel["sha256"],
            "native_sha256": native["sha256"], "schemas": native["schemas"],
            "environment": env, "control_sha": build["control_sha"]}


def _manifest_checks(batch, ablation, report, run, expected, source, digest, native_sha):
    _schema(batch, "chronicler-batch")
    _eq(batch.get("status"), "complete", "parent manifest completion")
    seeds = list(range(42, 42 + expected["seed_count"]))
    _eq(batch.get("seeds"), seeds, "parent seeds")
    _eq(batch.get("turns"), expected["turns"], "parent horizon")
    _eq(batch.get("parallel_requested"), 2, "parent worker count")
    _eq(batch.get("source", {}).get("git_sha"), source, "parent source")
    _hash(batch.get("source", {}).get("package_digest"), "parent package digest")
    _eq(batch.get("native", {}).get("status"), "found", "parent native status")
    _eq(batch.get("native", {}).get("sha256"), native_sha, "parent native bytes")
    simulation = batch.get("simulation")
    if not isinstance(simulation, dict):
        _fail("simulation configuration is missing")
    _eq(simulation.get("agents"), "hybrid", "agent mode")
    _eq(simulation.get("turns"), expected["turns"], "simulation horizon")
    _eq(simulation, registered_simulation(expected), "complete registered simulation configuration")
    if simulation.get("scenario") is not None or simulation.get("decision_ablation") is not None:
        _fail("unexpected scenario or parent ablation")
    for name in FEATURE_ARGUMENTS:
        if simulation.get(name) is not None:
            _fail("unexpected explicit feature argument: " + name)
    for name in ("agent_scale_mode", "decision_ablation", "ablation_start_turn",
                 "tuning", "preset", "aggression_bias", "tech_diffusion_rate", "resource_abundance",
                 "trade_friction", "severity_multiplier", "cultural_drift_speed",
                 "religion_intensity", "secession_likelihood"):
        if simulation.get(name) is not None:
            _fail("unexpected requested simulation override: " + name)
    _eq(simulation.get("tuning_overrides"), {}, "default tuning overrides")
    if expected["worldgen"] == "procedural":
        for key in ("worldgen", "regions", "civs"):
            _eq(simulation.get(key), expected[key], "procedural simulation " + key)
    elif simulation.get("worldgen") not in (None, "template") or simulation.get("regions") not in (None, 8) or simulation.get("civs") not in (None, 4):
        _fail("unexpected template world configuration")
    parents = batch.get("runs")
    if not isinstance(parents, list) or len(parents) != len(seeds):
        _fail("incomplete parent records")
    for row, seed in zip(parents, seeds):
        if not isinstance(row, dict):
            _fail("invalid parent record")
        _eq(row.get("seed"), seed, "parent record seed")
        _eq(row.get("total_turns"), expected["turns"], "parent final turn")
        _eq(row.get("dir"), "seed_" + str(seed), "parent directory")
        _eq(row.get("bundle"), row["dir"] + "/chronicle_bundle.json", "parent bundle")
        files = row.get("files")
        required = {row["dir"] + "/" + name for name in (
            "chronicle_bundle.json", "agent_events.arrow", "validation_needs.arrow",
            "validation_relationships.arrow", "validation_memory_signatures.arrow",
            "validation_summary.json", "validation_community_summary.json")}
        if not isinstance(files, dict) or not required.issubset(files):
            _fail("parent validation hashes are missing")
        for name, value in files.items():
            _relative(name)
            if not name.startswith(row["dir"] + "/"):
                _fail("parent hash escapes its own directory")
            _hash(value, "parent validation input")
    _eq(report.get("profile"), "full", "report profile")
    _eq(report.get("causal_oracles_required"), False, "original causal policy")
    cohort = report.get("batch_manifest")
    if not isinstance(cohort, dict):
        _fail("verified report cohort is missing")
    for key, value in (
        ("status", "verified"), ("manifest_sha256", digest["report/batch_manifest.json"]["sha256"]),
        ("seeds", seeds), ("turns", expected["turns"]), ("simulation", simulation),
        ("source", {"git_sha": source, "package_digest": batch["source"]["package_digest"]}),
        ("native_sha256", native_sha), ("python", batch["environment"]["python"]),
        ("platform", batch["environment"]["platform"]), ("thread_env", batch["environment"]["thread_env"]),
    ):
        _eq(cohort.get(key), value, "verified report " + key)
    _eq(ablation.get("schema_version"), 2, "ablation schema")
    _eq(ablation.get("kind"), "chronicler-ablation-arms", "ablation kind")
    for key, value in (
        ("design", 2), ("status", "complete"), ("arms", expected["arms"]),
        ("seeds", seeds), ("fork_turns", expected["fork_turns"]),
        ("window_turns", 20), ("fork_count", expected["fork_count"]),
        ("plain_manifest_sha256", digest["report/batch_manifest.json"]["sha256"]),
    ):
        _eq(ablation.get(key), value, "ablation " + key)
    _eq(ablation.get("fork_rule"), {
        "first": 100, "every": 20 if expected["worldgen"] == "procedural" else 100,
        "worldgen": expected["worldgen"], "plain_total_turns": expected["turns"],
    }, "registered ablation fork rule")
    if ablation.get("failures"):
        _fail("ablation execution failures remain")
    for key in ("git_sha", "package_digest"):
        _eq(ablation.get("source", {}).get(key), batch["source"][key], "ablation source " + key)
    _eq(ablation.get("native", {}).get("sha256"), native_sha, "ablation native bytes")
    forks = ablation.get("forks")
    if not isinstance(forks, list) or len(forks) != expected["fork_count"]:
        _fail("incomplete fork records")
    expected_keys = {(seed, turn, arm) for seed in seeds for turn in expected["fork_turns"] for arm in expected["arms"]}
    seen, directories = set(), set()
    for row in forks:
        if not isinstance(row, dict):
            _fail("invalid fork record")
        key = (row.get("seed"), row.get("fork_turn"), row.get("arm"))
        if key not in expected_keys or key in seen:
            _fail("missing, duplicate or unexpected fork identity")
        seen.add(key)
        seed, turn, arm = key
        _eq(row.get("total_turns"), turn + 22, "fork final turn")
        _eq(row.get("run_dir"), "seed_" + str(seed), "fork parent directory")
        _eq(row.get("decision_ablation"), {"name": arm, "start_turn": turn + 1, "forked_at": turn + 1},
            "fork intervention")
        directory = _relative(row.get("dir"))
        _eq(directory, arm + "/seed_" + str(seed) + "/fork_" + str(turn), "registered fork directory")
        if directory in directories:
            _fail("duplicate fork output directory")
        directories.add(directory)
        files = row.get("files")
        if not isinstance(files, dict) or set(files) != {"agent_events.arrow", "fork.json"}:
            _fail("fork validation hashes are missing")
        for value in files.values():
            _hash(value, "fork validation input")
    summary = report.get("ablation_arms")
    if not isinstance(summary, dict):
        _fail("verified ablation report summary is missing")
    for key, value in (
        ("status", "verified"), ("manifest_sha256", digest["report/ablation_manifest.json"]["sha256"]),
        ("design", 2), ("arms", expected["arms"]), ("fork_turns", expected["fork_turns"]),
        ("window_turns", 20), ("forks", expected["fork_count"]), ("native_sha256", native_sha),
    ):
        _eq(summary.get(key), value, "verified ablation " + key)
    _eq(summary.get("history_identity"),
        "every fork's agent events equal the plain run's up to the fork turn",
        "ablation common-history verification")
    for name in FEATURE_ARGUMENTS:
        if name in run and run[name] is not None:
            _fail("unexpected requested run feature: " + name)
        if name in run:
            _eq(run[name], simulation.get(name), "run/batch requested feature " + name)
    for key, value in (
        ("profile", "full"), ("worldgen", expected["worldgen"]), ("seed_start", 42),
        ("seeds", expected["seed_count"]), ("turns", expected["turns"]), ("parallel", 2),
        ("ablation_oracles", True), ("ablation_arms", expected["arms"]),
        ("ablation_fork_turns", expected["fork_turns"]), ("ablation_forks", expected["fork_count"]),
        ("causal_oracles_required", False), ("require_strict_regression", True),
        ("batch_manifest_status", "verified"), ("exploratory_comparison", False),
    ):
        _eq(run.get(key), value, "original run manifest " + key)
    if run.get("baseline_report_path") is not None or run.get("comparison_path") is not None:
        _fail("cohort unexpectedly performed its own comparison")
    for oracle, version in (("community", 2), ("needs", 8), ("cohort", 6)):
        item = report.get("results", {}).get(oracle)
        if not isinstance(item, dict):
            _fail("required oracle result is missing")
        _eq(item.get("method_version"), version, oracle + " method")
    for name in ("needs", "cohort"):
        component = report["results"][name].get("ablation")
        if not isinstance(component, dict) or component.get("status") not in ("PASS", "FAIL"):
            _fail(name + " causal component was not measured")
        _eq(component.get("fork_design"), 2, name + " causal fork design")
    return simulation


def load_cohort(root, role, files, anchor, run_id, attempt):
    def get(name):
        raw, identity = _read(root / name)
        if hashlib.sha256(raw).hexdigest() != files[name]["sha256"] or identity != files[name]["identity"]:
            _fail("input changed after inventory")
        return _json(raw, name)
    index = get("artifact-index.json")
    _schema(index, "chronicler-cloud-full-gate-light-index")
    _eq(index.get("complete"), True, "light index completion")
    _eq(index.get("missing"), [], "missing light inputs")
    records = index.get("files")
    _check_index_records(records, "light index")
    _eq(sorted(records), sorted(INDEXED_FILES), "indexed light file set")
    for name, record in records.items():
        _eq(record, {k: files[name][k] for k in ("bytes", "sha256")}, "light indexed file " + name)
    _eq(index.get("file_count"), len(records), "light index file count")
    _eq(index.get("total_bytes"), sum(row["bytes"] for row in records.values()), "light index bytes")
    result, provenance, build = get("result.json"), get("provenance.json"), get("build-manifest.json")
    _schema(result, "chronicler-cloud-full-gate-cohort")
    _schema(provenance, "chronicler-cloud-full-gate-provenance")
    worldgen, arm = role.split("-")
    source = BASELINE if arm == "baseline" else CANDIDATE
    expected = expected_cohort(worldgen)
    _eq(result.get("expected"), expected, "registered cohort")
    for value in (result, provenance):
        for key, wanted in (("arm", arm), ("worldgen", worldgen), ("source_sha", source),
                            ("identities_stable", True)):
            _eq(value.get(key), wanted, "cohort " + key)
    _eq(result.get("execution_complete"), True, "cohort execution completion")
    for key in ("error", "final_identity_error", "light_error"):
        if key in result:
            _fail("cohort retained an execution/finalization error: " + key)
    _eq(result.get("stage"), "full", "full cohort stage")
    _eq(provenance.get("stage"), "full", "full provenance stage")
    _eq(result.get("qualified"), result.get("gate_pass"), "full cohort qualification state")
    _eq(result.get("budget_seconds"), 330 * 60, "full cohort resource budget")
    elapsed = result.get("elapsed_wall_seconds")
    if (type(elapsed) not in (int, float) or not math.isfinite(elapsed)
            or not 0 <= elapsed <= 330 * 60):
        _fail("full cohort resource budget was not met")
    _eq(provenance.get("github_run_id"), run_id, "cohort GitHub run")
    _eq(provenance.get("github_run_attempt"), attempt, "cohort GitHub attempt")
    _eq(files["build-manifest.json"]["sha256"], anchor, "externally anchored build manifest")
    builder = _builder(build, anchor, run_id, attempt)
    for value in (result, provenance):
        for key in ("build_manifest_sha256", "wheel_sha256", "native_sha256"):
            _eq(value.get(key), builder[key], "cohort " + key)
    _eq(provenance.get("control_sha"), builder["control_sha"], "cohort control source")
    _eq(result.get("provenance_sha256"), files["provenance.json"]["sha256"], "provenance hash")
    _eq(result.get("raw_inventory_sha256"), files["raw-inventory.json"]["sha256"], "raw inventory hash")
    _eq(result.get("light_index_sha256"), files["artifact-index.json"]["sha256"], "light index hash")
    for key in ("source_snapshot_before_sha256", "source_snapshot_after_sha256"):
        _hash(provenance.get(key), "cohort " + key)
    _eq(provenance["source_snapshot_before_sha256"], provenance["source_snapshot_after_sha256"],
        "cohort source snapshot stability")
    batch = get("report/batch_manifest.json")
    for phase in ("before", "after"):
        probe = provenance.get(phase)
        if not isinstance(probe, dict):
            _fail("runtime " + phase + " probe is missing")
        _eq(_env_signature(probe.get("environment")), builder["environment"], "runtime environment")
        native = probe.get("native")
        if not isinstance(native, dict):
            _fail("actual native probe is missing")
        _eq(native.get("sha256"), builder["native_sha256"], "actual compiled extension")
        _eq(native.get("schemas"), builder["schemas"], "actual compiled schemas")
        for key in ("git_sha", "package_digest"):
            _eq(probe.get("source", {}).get(key), batch.get("source", {}).get(key), "actual source " + key)
    _eq(_env_signature(batch.get("environment")), builder["environment"], "batch runtime environment")
    for phase in ("before", "after"):
        probe = provenance[phase]
        affinity = probe.get("affinity")
        if (not isinstance(affinity, list) or len(affinity) != 2
                or any(type(cpu) is not int or cpu < 0 for cpu in affinity)
                or len(set(affinity)) != 2):
            _fail("actual two-CPU affinity mask is missing")
        for name in ("prefix", "source_file"):
            if not isinstance(probe.get(name), str) or not probe[name]:
                _fail("actual interpreter/source path is missing")
    for name in ("affinity", "prefix", "source_file"):
        _eq(provenance["before"][name], provenance["after"][name], "within-cohort actual " + name)
    raw = get("raw-inventory.json")
    _schema(raw, "chronicler-cloud-full-gate-raw-inventory")
    _eq(raw.get("complete"), True, "raw inventory completion")
    _eq(raw.get("scope"),
        "worker payload before derived light copies; excludes final receipts and inventory",
        "raw inventory scope")
    _check_index_records(raw.get("files"), "raw inventory", bound=MAX_RAW_ENTRIES)
    _eq(raw.get("file_count"), len(raw["files"]), "raw inventory file count")
    _eq(raw.get("total_bytes"), sum(v["bytes"] for v in raw["files"].values()), "raw inventory byte count")
    for phase in ("before", "after"):
        name = "source-snapshot-" + phase + ".json"
        record = raw["files"].get(name)
        if not isinstance(record, dict) or record.get("bytes", 0) <= 0:
            _fail("raw source snapshot attestation is missing")
        _eq(record["sha256"], provenance["source_snapshot_" + phase + "_sha256"],
            "raw source snapshot hash")
    for name in REPORT_FILES:
        original = ("raw/full_gate/ablation_42/" if name == "ablation_manifest.json" else "raw/full_gate/batch_42/") + name
        _eq(raw["files"].get(original), records["report/" + name], "unaltered original " + name)
    # Every parent/fork validation hash must link to the copied raw inventory.
    # These remain controller attestations, not a local re-read of raw Arrow data.
    def raw_link(name, digest):
        record = raw["files"].get(name)
        if not isinstance(record, dict) or record.get("bytes", 0) <= 0:
            _fail("raw validation input is missing: " + name)
        _eq(record["sha256"], digest, "raw validation input hash " + name)
    parents_for_links = batch.get("runs")
    if not isinstance(parents_for_links, list):
        _fail("parent validation records are missing")
    for parent in parents_for_links:
        if not isinstance(parent, dict) or not isinstance(parent.get("files"), dict):
            _fail("parent validation records are malformed")
        for name, digest in parent["files"].items():
            raw_link("raw/full_gate/batch_42/" + _relative(name), digest)
    ablation_for_links = get("report/ablation_manifest.json")
    forks_for_links = ablation_for_links.get("forks")
    if not isinstance(forks_for_links, list):
        _fail("fork validation records are missing")
    for fork in forks_for_links:
        if not isinstance(fork, dict) or not isinstance(fork.get("files"), dict):
            _fail("fork validation records are malformed")
        directory = _relative(fork.get("dir"))
        for name, digest in fork["files"].items():
            raw_link("raw/full_gate/ablation_42/" + directory + "/" + _relative(name), digest)
    report, decision = get("report/validate_report_full.json"), get("report/gate_decision_full.json")
    run, ablation = get("report/run_manifest.json"), get("report/ablation_manifest.json")
    simulation = _manifest_checks(batch, ablation, report, run, expected, source, files, builder["native_sha256"])
    if type(decision.get("ok")) is not bool:
        _fail("original gate decision is malformed")
    _eq(decision.get("require_strict_regression"), True, "original strict gate policy")
    _eq(decision.get("causal_oracles_required"), False, "original causal gate policy")
    _eq(result.get("gate_pass"), decision["ok"], "original gate outcome")
    _eq(result.get("gate_exit_code"), 0 if decision["ok"] else 2, "original gate exit code")
    _eq(run.get("gate_status"), "PASS" if decision["ok"] else "FAIL", "original run gate status")
    _eq(run.get("gate_exit_code"), result["gate_exit_code"], "original run gate exit code")
    return {"report": report, "original_decision": decision, "simulation": simulation,
            "builder": builder, "result": result, "provenance": provenance}


def frozen_modules(candidate_source):
    root = _absolute(candidate_source)
    head, _ = _read(root / ".git" / "HEAD", limit=256)
    _eq(head.decode("ascii").strip(), CANDIDATE, "detached candidate checkout")
    for name, wanted in FROZEN_FILES.items():
        raw, _ = _read(root / name)
        _eq(hashlib.sha256(raw).hexdigest(), wanted, "frozen reader file " + name)
    src = root / "src"
    sys.path.insert(0, str(src))
    modules = {}
    for name in ("artifact_io", "validation_gate", "validation_compare"):
        module = importlib.import_module("chronicler." + name)
        if Path(module.__file__).resolve() != src / "chronicler" / (name + ".py"):
            _fail("comparison module was imported from another checkout")
        modules[name] = module
    package = importlib.import_module("chronicler")
    if Path(package.__file__).resolve() != src / "chronicler" / "__init__.py":
        _fail("comparison package was imported from another checkout")
    return modules


def analyze(cohorts, modules):
    comparator = modules["validation_compare"]
    gate = modules["validation_gate"]
    original, causal, comparisons = {}, {}, {}
    before = {role: _encoded(item["report"]) for role, item in cohorts.items()}
    for role, item in cohorts.items():
        report, saved = item["report"], item["original_decision"]
        policy = gate.adjudicate_validation_report("full", report, require_strict_regression=True,
                                                   require_causal_oracles=False)
        rebuilt = gate.build_gate_decision_payload(
            policy, report, report_path=Path(saved["report_path"]) if saved.get("report_path") else None)
        _eq(rebuilt, saved, "unaltered original strict decision")
        original[role] = saved
        required = gate.adjudicate_validation_report("full", report, require_strict_regression=True,
                                                     require_causal_oracles=True)
        causal[role] = gate.build_gate_decision_payload(required, report)
    for worldgen in ("template", "procedural"):
        left, right = cohorts[worldgen + "-baseline"], cohorts[worldgen + "-candidate"]
        comparison = comparator.compare_validation_reports(
            "full", left["report"], right["report"], require_strict_regression=True,
            fail_on_regression=True, exploratory=False)
        comparisons[worldgen] = comparison
    for role, item in cohorts.items():
        _eq(_encoded(item["report"]).hex(), before[role].hex(), "unchanged report input")
    issues = []
    for worldgen, result in comparisons.items():
        if result["exit_code"] or result["status"] != "NO_REGRESSION":
            issues.append(worldgen + ": required regression")
        if result.get("exploratory") or not result.get("cohort", {}).get("comparable"):
            issues.append(worldgen + ": incomparable cohort")
        if result.get("cohort", {}).get("unverified"):
            issues.append(worldgen + ": unverified cohort fields")
        if result.get("rebaseline_required") or result.get("oracle_method_changes"):
            issues.append(worldgen + ": oracle method change")
    if not all(value["ok"] for value in original.values()):
        issues.append("one or more original strict gates failed")
    return {
        "schema_version": 1, "kind": "chronicler-cloud-full-gate-comparison",
        "execution_complete": True, "qualification_pass": not issues,
        "unqualified_reasons": issues, "original_decisions": original,
        "causal_required_decisions": causal,
        "causal_required_all_pass": all(value["ok"] for value in causal.values()),
        "comparisons": comparisons,
        "causal_scope": "Separate adjudication of the same saved reports; no simulation or oracle rerun.",
        "raw_scope": "Original raw-file hashes are copied controller attestations; this reader verifies downloaded lightweight bytes only.",
    }


def _recheck(roots, inventories):
    for role, root in roots.items():
        current = _inventory(root, set())
        _eq(current, inventories[role], "unchanged input artifacts")


def run(roots, output, *, anchor, run_id, attempt, control_sha, modules, candidate_source):
    _hash(anchor, "external build manifest anchor")
    if not isinstance(control_sha, str) or re.fullmatch(r"[0-9a-f]{40}", control_sha) is None:
        _fail("external control SHA is missing")
    if not isinstance(run_id, str) or not run_id.isdigit() or not isinstance(attempt, str) or not attempt.isdigit():
        _fail("GitHub run identity must be decimal strings")
    _eq(sorted(roots), sorted(ROLES), "four fixed cohort roles")
    roots = {role: _absolute(path) for role, path in roots.items()}
    output, candidate_source = _absolute(output), _absolute(candidate_source)
    if output.exists() or output.is_symlink():
        _fail("output must be a new exclusive directory")
    for i, root in enumerate(roots.values()):
        if _under(output, root) or _under(root, output) or _under(output, candidate_source):
            _fail("output must be outside all inputs and frozen source")
        for other in list(roots.values())[i + 1:]:
            if _under(root, other) or _under(other, root):
                _fail("artifact input roots overlap")
    inodes = set()
    inventories = {role: _inventory(root, inodes) for role, root in roots.items()}
    cohorts = {role: load_cohort(root, role, inventories[role], anchor, run_id, attempt)
               for role, root in roots.items()}
    signatures = [item["builder"] for item in cohorts.values()]
    _eq(signatures[0]["control_sha"], control_sha, "externally pinned control source")
    for signature in signatures[1:]:
        _eq(signature, signatures[0], "shared builder/runtime identity")
    # Compare all unchanged non-world physics settings across profiles too.
    normalized = [{key: value for key, value in item["simulation"].items()
                   if key not in ("worldgen", "regions", "civs", "turns")}
                  for item in cohorts.values()]
    keys = set().union(*(item.keys() for item in normalized))
    for signature in normalized[1:]:
        for key in keys:
            _eq(signature.get(key), normalized[0].get(key), "cross-profile simulation " + key)
    result = analyze(cohorts, modules)
    result.update(
        baseline_source=BASELINE, candidate_source=CANDIDATE,
        github_run_id=run_id, github_run_attempt=attempt, control_sha=control_sha,
        build_manifest_sha256=anchor,
        reader={"python": sys.version, "executable": sys.executable,
                "candidate_source_path": str(candidate_source), "frozen_file_sha256": FROZEN_FILES,
                "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},
        inputs={role: {name: {key: item[key] for key in ("bytes", "sha256")}
                       for name, item in inventory.items()}
                for role, inventory in inventories.items()},
    )
    summary = (
        "# Fixed cloud full-gate comparison\n\n"
        + "Original strict qualification: **" + ("PASS" if result["qualification_pass"] else "FAIL") + "**.\n\n"
        + "Template comparison: " + result["comparisons"]["template"]["status"] + ".\n\n"
        + "Procedural comparison: " + result["comparisons"]["procedural"]["status"] + ".\n\n"
        + "Causal-required same-report adjudication: **"
        + ("PASS" if result["causal_required_all_pass"] else "FAIL") + "**.\n\n"
        + "NO_REGRESSION alone does not establish that either original gate passed. "
        + "Causal adjudication retains each original report and changes no historical oracle result.\n"
    )
    payloads = {"comparison.json": _encoded(result), "summary.md": summary.encode("utf-8")}
    for role, decision in result["causal_required_decisions"].items():
        payloads["causal-required-" + role + ".json"] = _encoded(decision)
    for worldgen, comparison in result["comparisons"].items():
        payloads["comparison-" + worldgen + ".json"] = _encoded(comparison)
        payloads["comparison-" + worldgen + ".md"] = modules["validation_compare"].format_comparison_markdown(comparison).encode("utf-8")
    if any(len(raw) > MAX_FILE_BYTES for raw in payloads.values()) or sum(map(len, payloads.values())) > MAX_ROOT_BYTES:
        _fail("derived output byte bound exceeded")
    _recheck(roots, inventories)
    output.mkdir(parents=False, exist_ok=False)
    for name, raw in payloads.items():
        with (output / name).open("xb") as stream:
            stream.write(raw)
    _recheck(roots, inventories)
    receipt = {"schema_version": 1, "kind": "chronicler-cloud-full-gate-comparison-receipt",
               "execution_complete": True, "qualification_pass": result["qualification_pass"],
               "files": {name: {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
                         for name, raw in payloads.items()}}
    with (output / "receipt.json").open("xb") as stream:
        stream.write(_encoded(receipt))
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for role in ROLES:
        parser.add_argument("--" + role, type=Path, required=True)
    parser.add_argument("--candidate-source", type=Path, required=True)
    parser.add_argument("--build-manifest-sha256", required=True)
    parser.add_argument("--control-sha", required=True)
    parser.add_argument("--github-run-id", required=True)
    parser.add_argument("--github-run-attempt", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        modules = frozen_modules(args.candidate_source)
        result = run({role: getattr(args, role.replace("-", "_")) for role in ROLES}, args.output,
                     anchor=args.build_manifest_sha256, run_id=args.github_run_id,
                     attempt=args.github_run_attempt, control_sha=args.control_sha,
                     modules=modules, candidate_source=args.candidate_source)
    except (ComparisonInputError, OSError, ValueError, TypeError, KeyError, AttributeError, OverflowError, RecursionError) as exc:
        sys.stderr.write("Full-gate comparison refused: " + str(exc) + "\n")
        return 1
    return 0 if result["qualification_pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
