"""Detached contracts for the inactive natural-research continuation study.

This module imports no simulation or native runtime. Reading an artifact never
loads a checkpoint's Python pickle or creates a native pool.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import struct
import subprocess
import zlib
import research_practice_runtime_policy as P

SOURCE = "cbf6e368ebd218c1f54179bee4accffc1ab2a4c0"
NATIVE = "3ee06a53b3c16dcba01bc53c8fe1dd97e530754a61d65fe2c1396b158b48e6d0"
SEEDS = tuple(range(2000, 2008))
ROLES = ("parent", "active", "pause_new_trials")
FORK, END = 60, 180
EXPERIMENT = "natural-finite-research-practice-observation-20261029"
CONTROLS = dict(withhold_information=False, transmission_enabled=True,
                uninformative_tests=False, publication_rule="funded-context-v2")
REGISTRATION = "docs/experiments/natural-practice-observer-registration-2026-10-29.md"
CONTROL_FILES = ("scripts/research_practice_contract.py", "scripts/run_research_practice_continuation.py",
                 "scripts/read_research_practice_continuation.py", "scripts/research_practice_runtime_policy.py",
                 "scripts/research_practice_recorder.py", "scripts/research_practice_adapter.py",
                 "scripts/research_practice_resources.py", "scripts/research_practice_trace_reader.py", REGISTRATION)
THREADS = ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "BLIS_NUM_THREADS",
           "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS", "GOTO_NUM_THREADS", "RAYON_NUM_THREADS")
MAX_METADATA = 64 * 1024**2
MAX_FILES, MAX_BYTES = 5000, 2 * 1024**3
AGGREGATE_CPU, WORKER_CPU, AGGREGATE_WALL, WORKER_WALL = 900, 90, 1800, 900
MAGIC = b"\x89CHRONICLER-CKPT\r\n\x1a\n"


class ContractError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise ContractError(message)


def selected_policy(frozen):
    try:
        selected = frozen["runtime_policy"]
        require(same(selected, P.policy(selected["name"])), "frozen runtime policy differs from closed registration")
        P.validate_runtime(selected["name"], frozen["runtime"], same)
        return selected
    except (KeyError, TypeError, ValueError) as exc:
        raise ContractError("invalid frozen runtime policy: " + str(exc)) from exc


def control_files(policy_name=P.DEFAULT_POLICY):
    P.policy(policy_name)
    return CONTROL_FILES + ("scripts/fetch_research_practice_wheel.py",)


def sha(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode()


def digest(value):
    return hashlib.sha256(encoded(value)).hexdigest()


def checkpoint_projection(value):
    """The checkpoint writer sorts every JSON mapping; no data comparator waiver."""
    return loads(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False))


def nonnegative(value, name, *, integer=False):
    require(type(value) is int if integer else type(value) in (int, float), name + " is not a typed number")
    require(math.isfinite(value) and value >= 0, name + " is negative or nonfinite")
    return value


def closed(value, fields, name):
    require(type(value) is dict and set(value) == set(fields), name + " fields differ")


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(encoded(value))


def read(path, maximum=MAX_METADATA):
    path = Path(path)
    require(path.is_file() and not path.is_symlink(), "metadata is not a regular non-link file")
    with path.open("rb") as stream:
        raw = stream.read(maximum + 1)
    require(len(raw) <= maximum, "metadata exceeds its registered read bound")
    return loads(raw)


def loads(raw):
    def pairs(rows):
        out = {}
        for key, value in rows:
            require(key not in out, "duplicate JSON key")
            out[key] = value
        return out
    def number(text):
        value = float(text)
        require(math.isfinite(value), "nonfinite JSON number")
        return value
    def constant(text):
        raise ContractError("nonfinite JSON literal")
    return json.loads(raw, object_pairs_hook=pairs, parse_float=number, parse_constant=constant)


def same(a, b):
    if type(a) is not type(b):
        return False
    if type(a) is dict:
        return list(a) == list(b) and all(same(a[k], b[k]) for k in a)
    if type(a) is list:
        return len(a) == len(b) and all(same(x, y) for x, y in zip(a, b))
    if type(a) is float:
        return math.isfinite(a) and math.isfinite(b) and a == b and (a != 0 or str(a) == str(b))
    return a == b


def differences(a, b, path="$"):
    if same(a, b):
        return []
    if type(a) is dict and type(b) is dict:
        rows = [] if list(a) == list(b) else [dict(path=path + ".<key-order>", left=list(a), right=list(b))]
        for key in sorted(a.keys() | b.keys()):
            rows += ([dict(path=path + "." + key, left_present=key in a, right_present=key in b,
                           left=a.get(key), right=b.get(key))] if key not in a or key not in b
                     else differences(a[key], b[key], path + "." + key))
        return rows
    if type(a) is list and type(b) is list:
        return [row for i in range(max(len(a), len(b))) for row in
                ([dict(path=path + f"[{i}]", left_present=i < len(a), right_present=i < len(b),
                       left=a[i] if i < len(a) else None, right=b[i] if i < len(b) else None)]
                 if i >= len(a) or i >= len(b) else differences(a[i], b[i], path + f"[{i}]"))]
    return [dict(path=path, left=a, right=b)]


def relative(value):
    require(isinstance(value, str) and "\\" not in value and "\x00" not in value, "invalid artifact path")
    path = PurePosixPath(value)
    require(not path.is_absolute() and value == path.as_posix() and not any(x in (".", "..") for x in path.parts),
            "artifact path aliases or escapes")
    return value


def inventory(root, *, omit=()):
    root = Path(root)
    rows, total = {}, 0
    for path in sorted(root.rglob("*")):
        require(not path.is_symlink(), "artifact inventory encountered a link")
        if path.is_dir():
            continue
        require(path.is_file(), "artifact inventory encountered a special file")
        name = relative(path.relative_to(root).as_posix())
        if name in omit:
            continue
        size = path.stat().st_size
        total += size
        require(len(rows) < MAX_FILES and total <= MAX_BYTES, "artifact inventory exceeds registered bounds")
        rows[name] = dict(bytes=size, sha256=sha(path))
    return rows


def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args], stderr=subprocess.PIPE, timeout=10)


def source_snapshot(root, expected=None):
    root = Path(root).resolve()
    head = git(root, "rev-parse", "HEAD").decode().strip()
    require(expected is None or head == expected, "source revision differs from prospective registration")
    require(not git(root, "status", "--porcelain"), "source/control checkout is dirty")
    files = {}
    for entry in git(root, "ls-files", "--stage", "-z").split(b"\0"):
        if not entry:
            continue
        meta, name = entry.split(b"\t", 1)
        mode, blob, stage = meta.decode().split()
        name = relative(name.decode())
        require(stage == "0" and mode in ("100644", "100755"), "unmerged/submodule/link source entry")
        path = root / name
        require(path.is_file() and not path.is_symlink(), "tracked source is not a regular file")
        files[name] = dict(mode=mode, bytes=path.stat().st_size, sha256=sha(path))
    return dict(root=str(root), git_sha=head, files=files, files_sha256=digest(files))


def checkpoint_sections(path):
    """Verify the whole envelope's sections without unpickling or importing native."""
    path = Path(path)
    require(path.stat().st_size <= MAX_METADATA, "checkpoint exceeds bounded observer input")
    raw = path.read_bytes()
    require(raw.startswith(MAGIC) and len(raw) > len(MAGIC) + 4, "invalid checkpoint magic/header")
    size = struct.unpack("<I", raw[len(MAGIC):len(MAGIC) + 4])[0]
    start = len(MAGIC) + 4
    require(0 < size <= MAX_METADATA and start + size <= len(raw), "checkpoint header length differs")
    header = loads(raw[start:start + size])
    require(header.get("format") == "chronicler-run-checkpoint" and type(header.get("version")) is int
            and header["version"] == 1, "checkpoint format differs")
    body, offset, records = raw[start + size:], 0, {}
    for section in header["sections"]:
        name = section["name"]
        require(type(name) is str and (name == "python" or name.startswith("native.")),
                "unsupported checkpoint section name")
        require(all(type(section.get(k)) is int and section[k] >= 0 for k in ("offset", "length", "raw_length"))
                and 0 < section["length"] <= MAX_METADATA and section["raw_length"] <= MAX_METADATA,
                "checkpoint section lengths are not bounded integers")
        require(name not in records and section["offset"] == offset, "checkpoint section aliases/offset differs")
        packed = body[offset:offset + section["length"]]
        offset += section["length"]
        require(hashlib.sha256(packed).hexdigest() == section["sha256"], "checkpoint packed section hash differs")
        dec = zlib.decompressobj()
        value = dec.decompress(packed, MAX_METADATA + 1)
        require(len(value) <= MAX_METADATA and dec.eof and not dec.unused_data and not dec.unconsumed_tail,
                "checkpoint decompression exceeds bounds or has trailing data")
        require(len(value) == section["raw_length"], "checkpoint raw section length differs")
        records[name] = dict(bytes=len(value), sha256=hashlib.sha256(value).hexdigest(),
                             packed_sha256=section["sha256"])
    require(offset == len(body) and "python" in records, "checkpoint payload set is incomplete")
    return header, records


def checkpoint_build_identity(header, frozen):
    """Match the source-owned checkpoint projection to the observed freeze."""
    runtime = frozen["runtime"]
    source = {key: runtime["source"][key] for key in ("package_digest", "git_sha")}
    native = {key: runtime["native"][key] for key in ("status", "sha256", "bytes")}
    native["state_layouts"] = {kind: "v" + str(runtime["available_compiled_classes"][name]["version"]) + ":" +
        runtime["available_compiled_classes"][name]["fingerprint"] for name, kind in
        (("AgentSimulator", "agent"), ("EcologySimulator", "ecology"), ("PoliticsSimulator", "politics"))}
    env = {key: runtime["environment"][key] for key in
           ("python", "implementation", "machine", "affinity_cpu_count", "thread_env", "packages")}
    env["hash_seed"] = runtime["environment"]["thread_env"]["PYTHONHASHSEED"]
    require(same(header["identity"], checkpoint_projection(dict(source=source, native=native, environment=env))),
            "checkpoint source/native/environment projection differs from frozen runtime")


def validate_rng_json(value):
    """Validate lossless legacy RNG encodings without importing NumPy/native."""
    require(type(value) is dict and set(value) == {"python", "numpy"}, "RNG sidecar fields differ")
    p, n = value["python"], value["numpy"]
    require(type(p) is list and len(p) == 3 and p[0] == 3 and type(p[0]) is int
            and type(p[1]) is list and len(p[1]) == 625
            and all(type(v) is int and 0 <= v <= 2**32 - 1 for v in p[1][:-1])
            and type(p[1][-1]) is int and 0 <= p[1][-1] <= 624
            and (p[2] is None or type(p[2]) is float and math.isfinite(p[2])), "Python RNG state malformed")
    require(type(n) is list and len(n) == 5 and n[0] == "MT19937" and type(n[1]) is list and len(n[1]) == 624
            and all(type(v) is int and 0 <= v <= 2**32 - 1 for v in n[1])
            and type(n[2]) is int and 0 <= n[2] <= 624 and type(n[3]) is int and n[3] in (0, 1)
            and type(n[4]) is float and math.isfinite(n[4]), "NumPy legacy RNG state malformed")


def pause_archive(before, after):
    """Validate archive retention, not equality of legitimate pending work."""
    a, b = before["research_agendas"], after["research_agendas"]
    require(a["enabled"] is True and b["enabled"] is False and b["policy_changed_turn"] == FORK, "pause policy differs")
    for key in ("schema_version", "rule", "enabled_turn", "host_seal", "next_open_turn", "origin_cursor"):
        require(same(a[key], b[key]), "pause changed retained lineage: " + key)
    require(same(b["academy_births"][:len(a["academy_births"])], a["academy_births"]), "academy birth prefix changed")
    require(after["seat_ids"][:len(before["seat_ids"])] == before["seat_ids"], "enrolled seat prefix changed")
    require(same(before["claims"], after["claims"]), "pause created/replaced canonical topics")
    require(len(a["cycles"]) == len(b["cycles"]), "pause opened an agenda")
    for old, new in zip(a["cycles"], b["cycles"]):
        if old["closed_turn"] is not None:
            require(same(old, new), "closed agenda changed")
        else:
            for key in ("id", "legacy_adopted", "opening_roster_complete", "opened_turn", "origin_seat",
                        "participants", "claims", "trials", "announcement_event_id"):
                require(same(old[key], new[key]), "paused agenda lineage changed")
            require(new["closed_turn"] == FORK and new["close_reason"] == "research_paused", "pause closure missing")
    require(len(before["trials"]) == len(after["trials"]) and before["trial_spent"] == after["trial_spent"], "pause funded new work")
    terminal = {"status", "resolved_turn", "observed_control", "observed_treatment", "informative", "supports", "reason", "event_id"}
    for old, new in zip(before["trials"], after["trials"]):
        require(new["funded_turn"] < FORK, "pause funded a trial at/after boundary")
        keys = old.keys() if old["status"] != "running" else old.keys() - terminal
        require(same({k: old[k] for k in keys}, {k: new[k] for k in keys}), "retained trial admission changed")
    for key in ("proposals", "receipts"):
        require(same(before[key], after[key][:len(before[key])]), "retained receipt prefix changed")
    return dict(no_new_trial_funding=True, archive_prefix_preserved=True,
                trial_spent_delta=after["trial_spent"] - before["trial_spent"],
                effort_spent_delta=after["effort_spent"] - before["effort_spent"])


def exposure(science, history):
    """Source-dated stages; no end-turn belief substituted for paid-row confidence."""
    for name in ("trial_spent", "effort_spent"):
        nonnegative(science[name], name)
    for trial in science["trials"]:
        nonnegative(trial["cost"], "trial cost")
        nonnegative(trial["funded_turn"], "funded turn", integer=True)
    require(science["trial_spent"] == sum(t["cost"] for t in science["trials"]), "trial expense accounting differs")
    new = [t for t in science["trials"] if t["funded_turn"] >= FORK]
    old = [t for t in science["trials"] if t["funded_turn"] < FORK]
    trials = {t["id"]: t for t in science["trials"]}
    proposals = [p for p in science["proposals"] if p["received_turn"] >= FORK]
    receipts = [r for r in science["receipts"] if r["received_turn"] >= FORK]
    allocations, observed_sources, paid_sources = [], [], []
    for snapshot in history:
        section = snapshot.get("scientific_claims")
        source = snapshot["turn"] - 1
        if source < FORK:
            continue
        require(type(section) is dict, "post-boundary science observation unavailable")
        require(type(section["source_turn"]) is int and section["source_turn"] == source, "science snapshot clock differs")
        observed_sources.append(source)
        for row in section.get("allocations", []):
            nonnegative(row["paid"], "paid adoption cost")
            nonnegative(row["confidence"], "paid adoption confidence")
            nonnegative(row["share"], "paid adoption share")
            require(row["confidence"] <= 1 and row["share"] <= 1, "paid confidence/share exceeds one")
            paid_sources.append(source)
            prior = [r for r in science["receipts"] if r["seat"] == row["seat"] and r["received_turn"] < source
                     and trials[r["trial"]]["claim"] == row["claim_id"]]
            allocations.append(dict(source_turn=source, **row,
                prior_new_trial_receipts=sum(trials[r["trial"]]["funded_turn"] >= FORK for r in prior),
                receipt_scope="received strictly before payment source; same-source receipt not attributed"))
    plan = science["research_agendas"]
    return dict(new_agendas=sum(c["opened_turn"] is not None and c["opened_turn"] >= FORK for c in plan["cycles"]),
        new_trials=len(new), new_trial_cost=sum(t["cost"] for t in new),
        new_trial_statuses=dict(Counter(t["status"] for t in new)),
        new_trial_rows=new, running_new_trials_at_horizon=sum(t["status"] == "running" for t in new),
        pre_funded_post_boundary_resolutions=sum(t["resolved_turn"] is not None and t["resolved_turn"] >= FORK for t in old),
        pre_funded_post_boundary_terminal_rows=[t for t in old if t["resolved_turn"] is not None and t["resolved_turn"] >= FORK],
        new_trial_funding_turns=[t["funded_turn"] for t in new],
        new_trial_resolution_turns=[t["resolved_turn"] for t in new],
        proposals_received=len(proposals), outcome_receipts_received=len(receipts),
        post_boundary_proposals=proposals, post_boundary_outcome_receipts=receipts,
        outcome_receipts_from_new_trials=sum(trials[r["trial"]]["funded_turn"] >= FORK for r in receipts),
        paid_adoption_rows=allocations, paid_adoption_cost=sum(row["paid"] for row in allocations),
        trial_spent_total=science["trial_spent"], effort_spent_total=science["effort_spent"],
        topics_total=len(science["claims"]), cycles_total=len(plan["cycles"]),
        canonical_topics=science["claims"], retained_agendas=plan["cycles"],
        final_capacity_block=dict(reason=plan["blocked_reason"], source_turn=plan["blocked_turn"]),
        payment_phase_coverage=dict(observed_source_turns=observed_sources,
            paid_source_turns=sorted(set(paid_sources)), paid_seasons=sorted({(s % 12) // 3 for s in paid_sources}),
            calendar="source turn modulo12 /3, source-owned get_season_id", phase="phase4 before same-source phase10 receipts"),
        paid_use_season_scope="fixed six-turn cadence samples two of four seasons; missing use is not efficacy null",
        interpretation="descriptive stages; seeds/turns/institutions are not certified independent units")
