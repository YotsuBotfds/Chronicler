"""Closed source-only jobs for the two-winter forecast development study.

This module imports no project/native code and performs no I/O at import.
World construction and exact restoration belong solely to stock runner/CLI.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import PurePosixPath
import re

SEED = 42
HORIZON = 26
REGIONS = 8
CIVS = 4
BASELINE = "94b308e65bf3c7febc41f09b73004b1db2056a1d"
BASELINE_PACKAGE = "1235282cff8707015ffa90e94018fe4e2dafdb4eaf818db28420e09fbed5a9c0"
NATIVE_TREE = "04866c3962ec9d5c77477fc727107a553fc1d6df"
NATIVE_SHA256 = "38dddb970b7e832ccaacced1a51df860cb7d7bbd73c137a3936ecd91a65d56a5"
WHEEL_SHA256 = "55a5ac747716b7554b74cd4e761bce2f8b3cdc691a9303b113d07161895cebeb"
KINDS = ("AgentSimulator", "EcologySimulator", "PoliticsSimulator")
CAPS = {key: "1" for key in ("BLIS_NUM_THREADS", "CARGO_BUILD_JOBS", "GOTO_NUM_THREADS", "MKL_NUM_THREADS",
        "NUMEXPR_NUM_THREADS", "OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "PYTHON_CPU_COUNT",
        "RAYON_NUM_THREADS", "RUST_TEST_THREADS", "VECLIB_MAXIMUM_THREADS")}
CAPS.update(PYTHONHASHSEED="0", OPENBLAS_THREAD_TIMEOUT="16")
LIMITS = {
    "owner_wall_seconds": 2400, "owner_cpu_seconds": 1800,
    "final_wall_reserve": 150, "final_cpu_reserve": 100,
    "role_wall_seconds": 150, "role_cpu_seconds": 100,
    "bootstrap_wall_seconds": 90, "bootstrap_cpu_seconds": 60,
    "address_space_bytes": 4 * 1024**3, "observed_rss_bytes": 2 * 1024**3,
    "entry_disk_bytes": 12 * 1024**3, "entry_ram_bytes": 4 * 1024**3,
    "run_disk_bytes": 3 * 1024**3, "run_ram_bytes": 1024**3,
    "role_output_bytes": 128 * 1024**2, "role_output_files": 256,
    "log_acceptance_bytes": 2 * 1024**2,
    "max_total_bytes": 2 * 1024**3, "max_files": 4096,
    "publication_bytes": 16 * 1024**2, "publication_files": 128,
    "max_member_bytes": 128 * 1024**2, "max_header_bytes": 1024**2,
    "max_native_raw_bytes": 256 * 1024**2, "max_native_total_bytes": 1024**3,
    "max_json_nodes": 2_000_000, "max_depth": 160,
}


class Refused(ValueError):
    pass


def require(condition, reason):
    if not condition:
        raise Refused(reason)


def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()


def strict_json(raw):
    def pairs(rows):
        result = {}
        for key, value in rows:
            require(key not in result, "duplicate JSON key")
            result[key] = value
        return result
    def nonfinite(_value):
        raise Refused("nonfinite JSON constant")
    value = json.loads(raw, object_pairs_hook=pairs, parse_constant=nonfinite)
    # Reject finite-looking exponents that Python's float parser overflows.
    import math
    pending, nodes = [(value, 0)], 0
    while pending:
        item, depth = pending.pop(); nodes += 1
        require(nodes <= LIMITS["max_json_nodes"] and depth <= LIMITS["max_depth"], "JSON shape cap")
        if type(item) is float: require(math.isfinite(item), "nonfinite JSON value")
        elif type(item) is dict: pending.extend((child, depth + 1) for child in item.values())
        elif type(item) is list: pending.extend((child, depth + 1) for child in item)
    return value


def _sha(value, size=64):
    return type(value) is str and re.fullmatch("[0-9a-f]{" + str(size) + "}", value) is not None


def validate_binding(binding):
    """Only a later exact reviewed CI-qualified source can bind activation."""
    require(type(binding) is dict and set(binding) == {"candidate", "baseline", "native", "candidate_ci"},
            "closed study source binding")
    candidate, baseline, native, ci = (binding[key] for key in ("candidate", "baseline", "native", "candidate_ci"))
    require(type(candidate) is dict and set(candidate) == {"source", "package_digest", "runner_sha256", "pyproject_sha256", "lock_sha256"}
            and _sha(candidate["source"], 40)
            and all(_sha(candidate[key]) for key in candidate if key != "source"), "candidate binding remains unqualified")
    require(type(baseline) is dict and set(baseline) == {"source", "package_digest", "pyproject_sha256", "lock_sha256"}
            and baseline["source"] == BASELINE and baseline["package_digest"] == BASELINE_PACKAGE
            and all(_sha(baseline[key]) for key in ("pyproject_sha256", "lock_sha256")), "baseline source binding")
    require(type(native) is dict and set(native) == {"crate", "sha256", "bytes", "wheel_sha256", "wheel_bytes", "producer"}
            and native["crate"] == NATIVE_TREE and native["sha256"] == NATIVE_SHA256 and native["wheel_sha256"] == WHEEL_SHA256
            and type(native["bytes"]) is int and native["bytes"] == 13737112
            and type(native["wheel_bytes"]) is int and native["wheel_bytes"] == 3932436,
            "native producer/consumer binding")
    require(native["producer"] == {"artifact_id": 12919445395, "expiry": "2026-11-12T17:29:24Z",
            "job_id": 123615034004, "name": "native-shard-build-40921328325-1", "run_id": 40921328325,
            "sha256": "7cd1db77f6f8f7006e7dfb2f521c28fa7f564b1ea2c97b764aa6cabb0d38d728", "size": 3868647,
            "source": "3a2a671477be849dd1b26c000d501304b8c684e9", "workflow": ".github/workflows/tests.yml"},
            "exact separately produced native wheel origin")
    require(all(type(native["producer"][key]) is int for key in ("artifact_id", "job_id", "run_id", "size")),
            "strict native producer integer fields")
    require(type(ci) is dict and set(ci) == {"source", "run_id", "attempt", "conclusion", "root_receipt_sha256", "independent_receipt_sha256"}
            and ci["source"] == candidate["source"] and type(ci["run_id"]) is int and ci["run_id"] > 0
            and type(ci["attempt"]) is int and ci["attempt"] == 1 and ci["conclusion"] == "success"
            and _sha(ci["root_receipt_sha256"]) and _sha(ci["independent_receipt_sha256"]),
            "exact candidate full CI remains unqualified")
    return deepcopy(binding)


def validate_jobs(jobs):
    require(type(jobs) is list and len(jobs) == 14, "fixed role count")
    expected = [
        ("legacy-default", "baseline", "plain", 0, [], None, "omitted"),
        ("candidate-default", "candidate", "plain", 0, [], None, "omitted"),
        ("candidate-off", "candidate", "plain", 0, [], None, "off"),
        ("legacy-fixed", "baseline", "plain", 0, [], None, "fixed"),
        ("candidate-fixed", "candidate", "plain", 0, [], None, "fixed"),
        ("local-parent", "candidate", "plain", 0, [4], None, "local"),
        ("local-normal", "candidate", "fork", 4, [], "local-parent", "local"),
        ("local-withheld", "candidate", "fork", 4, [], "local-parent", "withheld"),
        ("local-reference", "candidate", "plain", 0, [26], None, "local"),
        ("exact-4", "candidate", "exact", 4, [6, 8, 10, 13, 26], "local-parent", "inherit"),
        ("exact-6", "candidate", "exact", 6, [26], "exact-4", "inherit"),
        ("exact-8", "candidate", "exact", 8, [26], "exact-4", "inherit"),
        ("exact-10", "candidate", "exact", 10, [26], "exact-4", "inherit"),
        ("exact-13", "candidate", "exact", 13, [26], "exact-4", "inherit"),
    ]
    fields = {"name", "source_alias", "kind", "start_turn", "checkpoint_turns", "parent", "mode"}
    for row, values in zip(jobs, expected):
        require(type(row) is dict and set(row) == fields, "closed literal job fields")
        require(tuple(row[key] for key in ("name", "source_alias", "kind", "start_turn", "checkpoint_turns", "parent", "mode")) == values,
                "fixed literal job order and values")
        require(type(row["start_turn"]) is int and all(type(t) is int for t in row["checkpoint_turns"]), "strict job turn types")
    require(sum(HORIZON - row["start_turn"] for row in jobs) == 315, "fixed executed turn accounting")
    return deepcopy(jobs)


def registration(binding, jobs):
    binding, jobs = validate_binding(binding), validate_jobs(jobs)
    roles = []
    for row in jobs:
        source = binding[row["source_alias"]]
        roles.append({"name": row["name"], "directory": "roles/" + row["name"] + "/ordinary",
                      "source": source["source"], "package_digest": source["package_digest"],
                      "native_sha256": binding["native"]["sha256"], "start_turn": row["start_turn"],
                      "turns": HORIZON, "kind": row["kind"], "checkpoint_turns": row["checkpoint_turns"]})
    comparisons = []
    for left, right in (("legacy-default", "candidate-default"), ("candidate-default", "candidate-off"),
                        ("legacy-fixed", "candidate-fixed"), ("local-parent", "local-reference")):
        comparisons.append({"name": left + "-to-" + right, "left": left, "right": right,
                            "split_turn": None, "compare_bundle": True, "state_only": False})
    comparisons.append({"name": "local-noop-state", "left": "local-parent", "right": "local-normal",
                        "split_turn": 4, "compare_bundle": False, "state_only": True})
    for split in (4, 6, 8, 10, 13):
        comparisons.append({"name": "exact-" + str(split), "left": "local-reference", "right": "exact-" + str(split),
                            "split_turn": split, "compare_bundle": True, "state_only": False})
    checkpoints = [{"name": "native-final-" + str(split), "left_role": "local-reference", "left_path": "checkpoint_turn_26.ckpt",
                    "right_role": "exact-" + str(split), "right_path": "checkpoint_turn_26.ckpt", "turn": HORIZON,
                    "expected_header": {"seed": SEED, "num_turns": HORIZON}} for split in (4, 6, 8, 10, 13)]
    return {"schema_version": 1, "study": "forecast-local-credibility-h26", "seed": SEED, "horizon": HORIZON,
            "regions": REGIONS, "civilizations": CIVS, "binding": binding, "roles": roles,
            "comparisons": comparisons, "checkpoint_comparisons": checkpoints,
            "budgets": dict(LIMITS), "unsupported": {"full_graph_equivalence": None, "global_rng_equivalence": None,
            "raw_economy_contact_candidate_evidence": None, "efficacy": None, "performance": None, "adoption": None}}


def simulation_job(spec, *, root, sources, registration_path, registration_sha256, parent_sha256=None):
    """Materialize the frozen normal-runner/CLI arguments; no filesystem reads."""
    require(type(root) is str and root.startswith("/") and str(PurePosixPath(root)) == root
            and ".." not in PurePosixPath(root).parts and _sha(registration_sha256), "canonical job input")
    require(type(spec) is dict and any(canonical(spec) == canonical(row) for row in validate_jobs(deepcopy(JOBS))), "exact registered job")
    require(type(sources) is dict and set(sources) == {"baseline", "candidate"}
            and all(str(value).startswith("/") for value in sources.values())
            and type(registration_path) is str and registration_path.startswith("/"), "registered source and protocol paths")
    ordinary = root + "/roles/" + spec["name"] + "/ordinary"
    argv = ["--seed", "42", "--turns", "26", "--simulate-only", "--agents", "hybrid", "--regions", "8", "--civs", "4",
            "--worldgen", "template", "--validation-sidecar", "--output", ordinary + "/chronicle.md", "--state", ordinary + "/state.json"]
    if spec["mode"] in ("fixed", "local", "withheld"):
        argv.extend(["--harvest-forecasts", "--grain-reserves", "--contact-ledger"])
    elif spec["mode"] == "off": argv.append("--no-harvest-forecasts")
    if spec["parent"] is not None:
        parent = root + "/roles/" + spec["parent"] + "/ordinary/checkpoint_turn_" + str(spec["start_turn"]) + ".ckpt"
        argv.extend(["--resume", parent])
    else: parent = None
    if spec["checkpoint_turns"]: argv.extend(["--checkpoint-turns", ",".join(map(str, spec["checkpoint_turns"]))])
    request = None
    if spec["mode"] in ("local", "withheld"):
        controls = {"preparation_policy": "local_credibility"}
        arm = "parent"
        if spec["kind"] == "fork":
            arm = "normal" if spec["mode"] == "local" else "withheld"
            controls["policy"] = "normal" if arm == "normal" else "withhold"
        request = {"schema_version": 1, "experiment": "forecast-local-credibility-h26", "cohort": "development",
                   "feature": "harvest_forecasts", "arm": arm, "controls": controls,
                   "fork": spec["kind"] == "fork", "registration": {"path": registration_path, "sha256": registration_sha256}}
        if parent is not None:
            require(_sha(parent_sha256), "actual parent checkpoint digest required")
            request["parent_checkpoint"] = {"path": parent, "sha256": parent_sha256}
    return {"source_root": str(sources[spec["source_alias"]]), "simulation_args": argv, "request": request,
            "entrypoint": "normal_runner_job" if request is not None else "stock_cli", "role": spec["name"]}


# Literal copy also appears in docs/experiments/forecast-credibility-jobs.json.
# The owner requires exact equality before materializing any command.
JOBS = [
    {"name":"legacy-default","source_alias":"baseline","kind":"plain","start_turn":0,"checkpoint_turns":[],"parent":None,"mode":"omitted"},
    {"name":"candidate-default","source_alias":"candidate","kind":"plain","start_turn":0,"checkpoint_turns":[],"parent":None,"mode":"omitted"},
    {"name":"candidate-off","source_alias":"candidate","kind":"plain","start_turn":0,"checkpoint_turns":[],"parent":None,"mode":"off"},
    {"name":"legacy-fixed","source_alias":"baseline","kind":"plain","start_turn":0,"checkpoint_turns":[],"parent":None,"mode":"fixed"},
    {"name":"candidate-fixed","source_alias":"candidate","kind":"plain","start_turn":0,"checkpoint_turns":[],"parent":None,"mode":"fixed"},
    {"name":"local-parent","source_alias":"candidate","kind":"plain","start_turn":0,"checkpoint_turns":[4],"parent":None,"mode":"local"},
    {"name":"local-normal","source_alias":"candidate","kind":"fork","start_turn":4,"checkpoint_turns":[],"parent":"local-parent","mode":"local"},
    {"name":"local-withheld","source_alias":"candidate","kind":"fork","start_turn":4,"checkpoint_turns":[],"parent":"local-parent","mode":"withheld"},
    {"name":"local-reference","source_alias":"candidate","kind":"plain","start_turn":0,"checkpoint_turns":[26],"parent":None,"mode":"local"},
    {"name":"exact-4","source_alias":"candidate","kind":"exact","start_turn":4,"checkpoint_turns":[6,8,10,13,26],"parent":"local-parent","mode":"inherit"},
    {"name":"exact-6","source_alias":"candidate","kind":"exact","start_turn":6,"checkpoint_turns":[26],"parent":"exact-4","mode":"inherit"},
    {"name":"exact-8","source_alias":"candidate","kind":"exact","start_turn":8,"checkpoint_turns":[26],"parent":"exact-4","mode":"inherit"},
    {"name":"exact-10","source_alias":"candidate","kind":"exact","start_turn":10,"checkpoint_turns":[26],"parent":"exact-4","mode":"inherit"},
    {"name":"exact-13","source_alias":"candidate","kind":"exact","start_turn":13,"checkpoint_turns":[26],"parent":"exact-4","mode":"inherit"},
]
