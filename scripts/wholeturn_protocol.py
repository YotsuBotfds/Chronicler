"""Closed registration and records for a detached matched whole-turn experiment.

Importing this module performs no admission, collection, runtime or network work.
The candidate and root decision are source-owned, deliberately deferred values.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import struct

PROTOCOL = "matched-wholeturn-staging-v1"
BASELINE = "82902b85a94ebb008168cb06195b031c6ee1eb92"
BASE_NATIVE = "a840fd12462deedf92b256878d474404eeac892d"
RUN_REF = "refs/heads/lead/wholeturn-staging-run-20261030"
REGISTRATION = "docs/experiments/matched-wholeturn-staging-v1.json"
MIB = 1024**2
GIB = 1024**3


class Refused(ValueError):
    pass


def require(condition, reason):
    if not condition:
        raise Refused(reason)


def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)+"\n").encode()


def strict_json(body):
    def pairs(rows):
        result = {}
        for key, value in rows:
            require(key not in result, "duplicate JSON field")
            result[key] = value
        return result
    def constant(_):
        raise Refused("nonfinite JSON constant")
    return json.loads(body, object_pairs_hook=pairs, parse_constant=constant)


def pin(path, maximum=16*MIB):
    path = Path(path)
    before = path.lstat()
    require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1
            and 0 <= before.st_size <= maximum, "bounded unique regular file")
    digest = hashlib.sha256()
    count = 0
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(MIB), b""):
            count += len(block)
            require(count <= maximum, "file grew beyond bound")
            digest.update(block)
    after = path.lstat()
    identity = lambda s: (s.st_mode, s.st_dev, s.st_ino, s.st_nlink, s.st_size,
                          s.st_mtime_ns, s.st_ctime_ns)
    require(identity(before) == identity(after) and count == before.st_size,
            "file changed while hashing")
    return {"bytes": count, "sha256": digest.hexdigest()}


def read_json(path, maximum=MIB):
    before = pin(path, maximum)
    body = Path(path).read_bytes()
    require(before == {"bytes": len(body), "sha256": hashlib.sha256(body).hexdigest()},
            "JSON changed before read")
    return strict_json(body)


def write_new(path, value, maximum=MIB):
    body = value if type(value) is bytes else canonical(value)
    require(len(body) <= maximum, "record byte limit")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(body)
        stream.flush()
        os.fsync(stream.fileno())
    path.chmod(0o444)
    return {"bytes": len(body), "sha256": hashlib.sha256(body).hexdigest()}


def hex_value(value, width):
    return type(value) is str and re.fullmatch("[0-9a-f]{"+str(width)+"}", value) is not None


def validate_registration(value, *, ready=True):
    require(type(value) is dict and set(value) == {"activation", "baseline", "candidate", "fixed_counts", "fixtures",
            "global_rng_seed", "horizon", "kind", "limits", "proof", "protocol", "qualification", "root_decision", "run_ref", "windows"}
            and value.get("protocol") == PROTOCOL and value.get("kind") == "SOURCE_ONLY_MATCHED_WHOLETURN_REGISTRATION"
            and value.get("qualification") == {"performance": None, "runtime": None, "scientific": None},
            "registered protocol")
    require(value.get("baseline") == {"source_commit": BASELINE, "native_tree": BASE_NATIVE},
            "fixed baseline")
    candidate = value.get("candidate")
    require(type(candidate) is dict and set(candidate) == {"source_commit", "native_tree"},
            "closed candidate fields")
    require(all(v is None or hex_value(v, 40) for v in candidate.values()),
            "candidate must be exact SHA or deferred")
    require(value.get("run_ref") == RUN_REF and value.get("horizon") == 200
            and type(value["horizon"]) is int and value.get("global_rng_seed") == 0
            and type(value["global_rng_seed"]) is int,
            "fixed runtime registration")
    require(value.get("windows") == [[8, 16], [188, 196]], "fixed windows")
    require(value.get("fixtures") == [
        {"family": "template", "worldgen": "template", "regions": 8, "civilizations": 4},
        {"family": "procedural", "worldgen": "procedural", "regions": 32, "civilizations": 10},
    ], "fixed normal world matrix")
    require(value.get("fixed_counts") == {"pairs": 6, "roles": 12, "requested_World_turns": 2400},
            "fixed schedule counts")
    limits = value.get("limits", {})
    expected = {
        "job_wall_seconds": 7200, "build_wall_seconds_each": 900,
        "owner_wall_seconds": 4200, "owner_CPU_seconds": 3300,
        "role_wall_seconds": 300, "role_CPU_seconds": 240,
        "role_AS_bytes": 4*GIB, "role_observed_RSS_bytes": 2*GIB,
        "comparison_wall_seconds": 60, "comparison_CPU_seconds": 40,
        "final_wall_reserve_seconds": 150, "final_CPU_reserve_seconds": 100,
        "publication_wall_seconds": 660, "entry_disk_bytes": 12*GIB,
        "entry_available_RAM_bytes": 4*GIB, "running_disk_floor_bytes": 3*GIB,
        "running_RAM_floor_bytes": GIB, "role_output_bytes": 512*MIB,
        "metadata_reserve_bytes": 64*MIB, "aggregate_output_bytes": 12*512*MIB+64*MIB,
        "regular_files": 5000, "inventory_depth": 64, "visited_entries": 10000,
        "ordinary_hash_bytes": 6*GIB, "joint_role_log_bytes": 2*MIB,
        "profile_function_rows_per_window": 20000, "profile_label_UTF8_bytes": 2048,
        "profile_caller_edges_per_window": 40000,
        "compact_ZIP_bytes": MIB, "compact_expanded_bytes": MIB,
        "metadata_cell_bytes": 512*1024,
    }
    require(limits == expected and all(type(v) is int for v in limits.values()),
            "unchanged registered budgets")
    require(value.get("proof") == {"cross_source_restore": False, "decoded_state_visit_limit": 5_000_000,
            "live_unsupported_types": "refuse", "ordinary_comparator": "cities_identity.compare(inert=False,normalize=None) +turn_speed_identity._raw_bundle_problems",
            "required_live_capture": True, "source_provenance": "check each expected own identity, never blanket-ignore identity",
            "war_roster_projection_only": True}
            and type(value["proof"]["decoded_state_visit_limit"]) is int
            and all(type(value["proof"][key]) is bool for key in
                    ("cross_source_restore", "required_live_capture", "war_roster_projection_only")),
            "strict live and decoded proof required")
    if ready:
        require(all(hex_value(v, 40) for v in candidate.values()),
                "candidate source/native pins DEFERRED")
        require(candidate["source_commit"] != BASELINE, "distinct candidate source")
        decision = value.get("root_decision")
        require(type(decision) is dict and set(decision) == {
            "kind", "protocol", "candidate_source", "candidate_native_tree",
            "source_review_sha256", "live_proof_review_sha256", "approval_id"},
            "exact source-owned root decision DEFERRED")
        require(decision["kind"] == "ROOT_REVIEWED_WHOLETURN_CANDIDATE"
                and decision["protocol"] == PROTOCOL
                and decision["candidate_source"] == candidate["source_commit"]
                and decision["candidate_native_tree"] == candidate["native_tree"]
                and hex_value(decision["source_review_sha256"], 64)
                and hex_value(decision["live_proof_review_sha256"], 64)
                and type(decision["approval_id"]) is str
                and 0 < len(decision["approval_id"]) <= 128 and "\x00" not in decision["approval_id"],
                "root decision does not join candidate/proof")
    return value


def load_registration(controller_root, *, ready=True):
    return validate_registration(read_json(Path(controller_root)/REGISTRATION), ready=ready)


def schedule(registration):
    validate_registration(registration, ready=False)
    result = []
    for fixture in registration["fixtures"]:
        orders = [(42, False, ("baseline", "candidate")),
                  (43, False, ("candidate", "baseline")),
                  (42, True, (("baseline", "candidate") if fixture["regions"] == 8
                              else ("candidate", "baseline")))]
        for seed, profiled, arms in orders:
            pair = fixture["family"]+"-"+("profiled" if profiled else "plain")+"-"+str(seed)
            for arm in arms:
                result.append(dict(fixture, index=len(result), pair=pair, arm=arm,
                                   seed=seed, turns=200, profiled=profiled,
                                   source_commit=registration[arm]["source_commit"],
                                   native_tree=registration[arm]["native_tree"]))
    return result


def interval(raw):
    require(type(raw) is dict and set(raw) == {"CPU_start_ns", "CPU_end_ns", "wall_start_ns", "wall_end_ns"},
            "closed raw clock endpoints")
    valid = all(type(v) is int and 0 <= v < 2**63 for v in raw.values())
    cpu = raw["CPU_end_ns"]-raw["CPU_start_ns"] if valid else None
    wall = raw["wall_end_ns"]-raw["wall_start_ns"] if valid else None
    return {"raw": raw, "CPU_ns": cpu, "wall_ns": wall,
            "numerically_valid": valid and cpu > 0 and wall > 0}


def sample_ns(clock):
    """Retain malformed/failing endpoints as JSON-safe data before refusal."""
    try:
        value = clock()
    except Exception as exc:
        return {"clock_error": type(exc).__name__}
    if type(value) in (int, bool) or value is None:
        return value
    if type(value) is float:
        return {"invalid_clock_type": "float64", "bits": struct.pack("!d", value).hex()}
    return {"invalid_clock_type": type(value).__name__}


def ratio(baseline, candidate):
    if not baseline["numerically_valid"] or not candidate["numerically_valid"]:
        return {"CPU_candidate_over_baseline": None, "wall_candidate_over_baseline": None,
                "status": "NUMERICAL_REFUSAL"}
    return {"CPU_candidate_over_baseline": candidate["CPU_ns"]/baseline["CPU_ns"],
            "wall_candidate_over_baseline": candidate["wall_ns"]/baseline["wall_ns"],
            "status": "COMPLETE_RATIO_REGRESSIONS_RETAINED"}


def budget_room(registration, *, elapsed_wall, consumed_CPU, roles_left, comparisons_left):
    limits = registration["limits"]
    require(all(type(v) is int and v >= 0 for v in (roles_left, comparisons_left)), "remaining counts")
    wall = roles_left*limits["role_wall_seconds"]+comparisons_left*limits["comparison_wall_seconds"]+limits["final_wall_reserve_seconds"]
    cpu = roles_left*limits["role_CPU_seconds"]+comparisons_left*limits["comparison_CPU_seconds"]+limits["final_CPU_reserve_seconds"]
    require(elapsed_wall+wall <= limits["owner_wall_seconds"]
            and consumed_CPU+cpu <= limits["owner_CPU_seconds"], "insufficient reserved finalization/role room")
    return {"remaining_wall_reserved": wall, "remaining_CPU_reserved": cpu}
