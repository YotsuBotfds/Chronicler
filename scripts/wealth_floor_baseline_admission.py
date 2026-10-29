"""Inactive, stdlib-only admission of retained wealth-floor baseline evidence.

No network, subprocess, source/payload import, extraction or scientific scoring.
An audit receipt requires a completed producer attestation; it grants no worlds.
"""
from __future__ import annotations

from dataclasses import dataclass
from contextlib import contextmanager
from collections.abc import Mapping
from datetime import datetime, timezone
import hashlib
import json
import math
import os
import shutil
from pathlib import Path, PurePosixPath, PureWindowsPath
import stat
import struct
import time
from types import MappingProxyType
import zipfile

OLD_RUN = 40791402289
OLD_CONTROL = "27f0f3d11a1a171e1539353eb2c3a0fb896f0939"
OLD_SOURCE = "d0281e5f57c508f27cea1676f36e0e6ed1225c9d"
OLD_CRATE = "a4703ef4e9a21b5dbb194d318536a46e6ca8b71c"
OLD_NATIVE = "06db5e19bdda13d7a536b236d677348f5ea7cb5adad2929962f0485192f9b4d6"
OLD_COMPARISON = "6343e81b4332786353c4bf83ed0c50e30db84ca10c8a428112efa5da7ba61889"
CANDIDATE_SOURCE = "503070175e3e78d9014add158ead8f16ce940843"
CANDIDATE_CRATE = "93b32cd9b02eccf4900b33cdaeece08262be2330"
BLOCK_BYTES = 1024 * 1024
MAX_CENTRAL_BYTES = 64 * BLOCK_BYTES
MAX_ENTRIES = 100000
MAX_PAYLOAD_BYTES = 6 * 1024**3
MAX_AGGREGATE_PAYLOAD = 10 * 1024**3
MAX_COMPRESSED_BYTES = 2126779694
MAX_METADATA_BYTES = 32 * BLOCK_BYTES
LIGHT_NAMES = frozenset(("artifact-index.json", "build-manifest.json", "provenance.json", "raw-inventory.json", "result.json",
    "report/ablation_manifest.json", "report/batch_manifest.json", "report/gate_decision_full.json",
    "report/gate_summary_full.md", "report/run_manifest.json", "report/validate_report_full.json"))
REVIEWED_CANDIDATE_PROOFS = MappingProxyType(dict(baseline_audit=None, native=None, wheel=None, build_context=None, checkpoint=None, determinism=None))


class AdmissionError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise AdmissionError(message)


def hash_shape(value):
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


@dataclass(frozen=True)
class FilePin:
    size: int
    sha256: str
    def __post_init__(self):
        require(type(self.size) is int and self.size >= 0 and hash_shape(self.sha256), "invalid file pin")


@dataclass(frozen=True)
class ArchivePin:
    artifact_id: int
    role: str
    size: int
    sha256: str
    expires_at: str
    def __post_init__(self):
        require(type(self.artifact_id) is int and self.artifact_id > 0, "invalid archive ID")
        require(self.role in ("template-candidate", "procedural-candidate"), "wrong historical role")
        FilePin(self.size, self.sha256)


ARCHIVES = MappingProxyType({
    "template": ArchivePin(12865287568, "template-candidate", 891194242,
        "ac1132176349bee3a82bcfffef9ee29abccf424920711ca635d07d616598e1ae", "2026-11-28T01:15:25Z"),
    "procedural": ArchivePin(12867956553, "procedural-candidate", 1235585452,
        "1ebd660a76acf26106d9205729f56aadeb59e8c5633a044faa5a5b1c32e928a8", "2026-11-28T02:13:35Z"),
})
RAW_COUNTS = MappingProxyType({"template": (55432, 4256211501), "procedural": (20332, 4896245631)})


class Budget:
    def __init__(self, cpu_limit=900, wall_limit=1800, *, wall_clock=time.monotonic, cpu_clock=time.process_time):
        require(type(cpu_limit) in (int, float) and 0 < cpu_limit <= 900, "invalid CPU budget")
        require(type(wall_limit) in (int, float) and 0 < wall_limit <= 1800, "invalid wall budget")
        self.cpu_limit, self.wall_limit = cpu_limit, wall_limit
        self.wall_clock, self.cpu_clock = wall_clock, cpu_clock
        self.start_wall, self.start_cpu = wall_clock(), cpu_clock()
        self.floor_probe, self.next_floor, self.resources = None, 0.0, None
    def check(self):
        wall, cpu = self.wall_clock() - self.start_wall, self.cpu_clock() - self.start_cpu
        if self.floor_probe is not None and wall >= self.next_floor:
            self.next_floor = wall + 0.5
            self.resources = self.floor_probe()
            wall, cpu = self.wall_clock() - self.start_wall, self.cpu_clock() - self.start_cpu
        require(all(math.isfinite(t) and t >= 0 for t in (wall, cpu)), "invalid elapsed clock")
        require(wall <= self.wall_limit and cpu <= self.cpu_limit, "audit CPU/wall budget exceeded")
        return dict(wall_seconds=wall, cpu_seconds=cpu)


def _resources(path, *, admission=False):
    disk = shutil.disk_usage(path).free
    require(disk >= (12 if admission else 3) * 1024**3, "disk admission/floor unmet")
    with open("/proc/meminfo", encoding="ascii") as stream:
        rows = stream.read(65537)
    require(len(rows) <= 65536, "memory metadata exceeds bound")
    memory = next((int(line.split()[1]) * 1024 for line in rows.splitlines() if line.startswith("MemAvailable:")), 0)
    cap, current = Path("/sys/fs/cgroup/memory.max"), Path("/sys/fs/cgroup/memory.current")
    if cap.exists() and current.exists():
        with cap.open("rb") as f: limit = f.read(129)
        with current.open("rb") as f: used = f.read(129)
        require(len(limit) <= 128 and len(used) <= 128, "cgroup metadata exceeds bound")
        if limit.strip() != b"max": memory = min(memory, max(0, int(limit) - int(used)))
    require(memory >= (2 if admission else 1) * 1024**3, "RAM admission/floor unmet")
    return dict(disk_free_bytes=disk, ram_available_bytes=memory)


def canonical_name(name, *, directory=False):
    require(isinstance(name, str) and name and "\0" not in name and "\\" not in name, "unsafe ZIP name")
    value = name[:-1] if directory and name.endswith("/") else name
    p = PurePosixPath(value)
    require(value not in ("", ".") and not p.is_absolute() and not PureWindowsPath(value).drive
            and p.as_posix() == value and all(x not in (".", "..") for x in p.parts), "unsafe ZIP name")
    return value


def json_bytes(value):
    return (json.dumps(value, sort_keys=True, allow_nan=False, separators=(",", ":")) + "\n").encode()


def parse_json(raw, budget):
    budget.check()
    require(len(raw) <= MAX_METADATA_BYTES, "metadata byte bound exceeded")
    def pairs(rows):
        result = {}
        for key, value in rows:
            require(key not in result, "duplicate JSON key")
            result[key] = value
        return result
    def finite(text):
        value = float(text); require(math.isfinite(value), "nonfinite JSON number"); return value
    def constant(_text):
        raise AdmissionError("nonfinite JSON constant")
    try:
        value = json.loads(raw, object_pairs_hook=pairs, parse_float=finite, parse_constant=constant)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AdmissionError("invalid JSON") from exc
    budget.check()
    require(isinstance(value, dict), "metadata object required")
    return value


def identity(st):
    return st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns


def _flags(directory=False):
    require(hasattr(os, "O_NOFOLLOW") and hasattr(os, "O_NONBLOCK") and hasattr(os, "O_DIRECTORY"), "safe POSIX file opens required")
    return os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | getattr(os, "O_CLOEXEC", 0) | (os.O_DIRECTORY if directory else 0)


@contextmanager
def _directory(path, budget):
    parts = Path(path).absolute().parts
    require(len(parts) <= 128 and all(x not in ("..", ".") for x in parts), "unsafe directory path")
    fd = os.open(parts[0], _flags(True))
    try:
        for part in parts[1:]:
            budget.check(); child = os.open(part, _flags(True), dir_fd=fd); os.close(fd); fd = child
        require(stat.S_ISDIR(os.fstat(fd).st_mode), "directory required")
        yield fd
    except OSError as exc:
        raise AdmissionError("unsafe or replaced directory") from exc
    finally: os.close(fd)


@contextmanager
def _regular(path, budget):
    path = Path(path); budget.check()
    with _directory(path.parent, budget) as parent:
        before = os.stat(path.name, dir_fd=parent, follow_symlinks=False)
        require(stat.S_ISREG(before.st_mode), "regular file required")
        try: fd = os.open(path.name, _flags(), dir_fd=parent)
        except OSError as exc: raise AdmissionError("unsafe file open") from exc
        with os.fdopen(fd, "rb") as stream:
            require(stat.S_ISREG(os.fstat(fd).st_mode) and identity(os.fstat(fd)) == identity(before), "file replaced before read")
            yield stream, before
            require(identity(os.fstat(fd)) == identity(before), "file changed during read")
            require(identity(os.stat(path.name, dir_fd=parent, follow_symlinks=False)) == identity(before), "file replaced after read")
        budget.check()


def bounded_read(path, limit, budget):
    with _regular(path, budget) as (stream, before):
        require(before.st_size <= limit, "metadata byte bound exceeded")
        raw = stream.read(limit + 1)
        require(len(raw) == before.st_size, "file changed while reading")
    budget.check(); return raw


def closed_light_inventory(root, budget):
    """Visit only the finite registered trie; never descend into extra trees."""
    trie = {}
    for name in LIGHT_NAMES:
        parts = name.split("/"); current = trie
        for part in parts[:-1]: current = current.setdefault(part, {})
        current[parts[-1]] = None
    found = set()
    with _directory(root, budget) as fd:
        def visit(directory, node, prefix):
            seen = set()
            with os.scandir(directory) as entries:
                for entry in entries:
                    budget.check()
                    require(entry.name in node and entry.name not in seen, "unexpected light entry")
                    seen.add(entry.name)
                    before = entry.stat(follow_symlinks=False)
                    relative = prefix + entry.name
                    if node[entry.name] is None:
                        require(stat.S_ISREG(before.st_mode), "light file is not regular")
                        found.add(relative)
                    else:
                        require(stat.S_ISDIR(before.st_mode), "light directory is unsafe")
                        child = os.open(entry.name, _flags(True), dir_fd=directory)
                        try:
                            require(identity(os.fstat(child)) == identity(before), "light directory replaced")
                            visit(child, node[entry.name], relative + "/")
                        finally: os.close(child)
            require(seen == node.keys(), "incomplete light directory")
        visit(fd, trie, "")
    return frozenset(found)


def read_original_comparison(path, budget=None):
    budget = budget or Budget()
    raw = bounded_read(path, MAX_METADATA_BYTES, budget)
    require(hashlib.sha256(raw).hexdigest() == OLD_COMPARISON, "original reader receipt digest differs")
    result = parse_json(raw, budget)
    require(result.get("control_sha") == OLD_CONTROL and result.get("github_run_id") == str(OLD_RUN)
            and result.get("github_run_attempt") == "1", "original reader origin differs")
    require(result.get("pipeline_qualified") is True and result.get("scientific_comparison_pass") is True,
            "original reader not complete/qualified")
    return result


def validate_origin(result, worldgen):
    wanted = dict(arm="candidate", source_sha=OLD_SOURCE, control_sha=OLD_CONTROL, native_sha256=OLD_NATIVE,
                  github_run_id=str(OLD_RUN), github_run_attempt="1", execution_complete=True,
                  identities_stable=True, qualified=True, gate_pass=True, stage="full", worldgen=worldgen)
    require(worldgen in ARCHIVES, "unknown world generator")
    require(all(type(result.get(k)) is type(v) and result[k] == v for k, v in wanted.items()), "historical origin/role/native differs")


def utc(value):
    try:
        t = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError) as exc:
        raise AdmissionError("invalid UTC time") from exc
    require(t.tzinfo is not None and t.utcoffset().total_seconds() == 0, "UTC timestamp required")
    return t


def validate_publication(metadata, pin, now):
    worldgen = pin.role.split("-")[0]
    wanted = dict(id=pin.artifact_id, name=f"full-gates-raw-candidate-{worldgen}-{OLD_RUN}-1",
                  size_in_bytes=pin.size, digest="sha256:" + pin.sha256, expired=False, expires_at=pin.expires_at)
    require(all(type(metadata.get(k)) is type(v) and metadata[k] == v for k, v in wanted.items()), "archive publication differs")
    origin = metadata.get("workflow_run", {})
    require(type(origin.get("id")) is int and origin["id"] == OLD_RUN and origin.get("head_sha") == OLD_CONTROL,
            "archive workflow origin differs")
    require(isinstance(now, datetime) and now.tzinfo is not None and utc(pin.expires_at) > now, "archive expired")


def build_expected_members(light_blobs, budget=None):
    budget = budget or Budget()
    require(set(light_blobs) == LIGHT_NAMES, "incomplete light file set")
    require(sum(map(len, light_blobs.values())) <= 128 * BLOCK_BYTES, "light package too large")
    inventory = parse_json(light_blobs["raw-inventory.json"], budget)
    files = inventory.get("files")
    require(inventory.get("complete") is True and isinstance(files, dict) and files, "raw inventory incomplete")
    require(type(inventory.get("file_count")) is int and inventory["file_count"] == len(files) <= MAX_ENTRIES, "raw inventory count differs")
    expected = {}
    for name, row in files.items():
        budget.check(); canonical_name(name)
        require(isinstance(row, dict), "invalid raw file record")
        expected[name] = FilePin(row.get("bytes"), row.get("sha256"))
    require(type(inventory.get("total_bytes")) is int and inventory["total_bytes"] == sum(p.size for p in expected.values()), "raw inventory byte total differs")
    extras = {name: light_blobs[name] for name in ("result.json", "provenance.json", "raw-inventory.json")}
    extras.update({"light/" + name: raw for name, raw in light_blobs.items()})
    require(not expected.keys() & extras.keys(), "raw inventory shadows derived receipts")
    expected.update({name: FilePin(len(raw), hashlib.sha256(raw).hexdigest()) for name, raw in extras.items()})
    for name in expected:
        require(not any(str(parent) in expected for parent in PurePosixPath(name).parents if str(parent) != "."), "file/directory prefix conflict")
    budget.check(); return MappingProxyType(expected)


def _read_at(stream, offset, count, size, budget):
    require(0 <= offset <= size and 0 <= count <= BLOCK_BYTES and offset + count <= size, "truncated ZIP index")
    budget.check(); stream.seek(offset); raw = stream.read(count); budget.check()
    require(len(raw) == count, "truncated ZIP index"); return raw


def preflight_zip_index(stream, size, budget):
    """Read only bounded ZIP footers/index before ZipFile allocates its index."""
    tail = _read_at(stream, max(0, size - 65557), min(size, 65557), size, budget)
    end = tail.rfind(b"PK\x05\x06")
    require(end >= 0 and end + 22 <= len(tail), "missing/truncated ZIP EOCD")
    e = struct.unpack("<4s4H2LH", tail[end:end + 22])
    require(end + 22 + e[7] == len(tail) and e[1] == e[2] == 0, "invalid/multidisk ZIP EOCD")
    end_pos = size - len(tail) + end
    entries, central_size, central_offset = e[4], e[5], e[6]
    sentinel = entries == 65535 or central_size == 0xffffffff or central_offset == 0xffffffff
    locator = _read_at(stream, end_pos - 20, 20, size, budget) if end_pos >= 20 else b""
    if locator.startswith(b"PK\x06\x07"):
        _, disk, offset, disks = struct.unpack("<4sLQL", locator)
        require(disk == 0 and disks == 1, "multidisk ZIP64")
        header = _read_at(stream, offset, 56, size, budget)
        z = struct.unpack("<4sQ2H2L4Q", header)
        require(z[0] == b"PK\x06\x06" and z[3] == 45 and 44 <= z[1] <= 4096 and offset + z[1] + 12 == end_pos - 20, "bad ZIP64 EOCD")
        require(z[4] == z[5] == 0 and z[6] == z[7], "multidisk ZIP64 count")
        entries, central_size, central_offset = z[7], z[8], z[9]
        require((e[3] == 65535 or e[3] == entries) and (e[4] == 65535 or e[4] == entries) and (e[5] == 0xffffffff or e[5] == central_size)
                and (e[6] == 0xffffffff or e[6] == central_offset), "ZIP64/EOCD mismatch")
        central_end = offset
    else:
        require(not sentinel and e[3] == entries, "missing ZIP64 locator/count mismatch")
        central_end = end_pos
    require(0 < entries <= MAX_ENTRIES and 46 * entries <= central_size <= MAX_CENTRAL_BYTES, "ZIP index count/byte cap")
    require(central_offset + central_size == central_end, "ZIP central directory span differs")
    position, count, names = central_offset, 0, []
    while position < central_end:
        h = struct.unpack("<4s6H3L5H2L", _read_at(stream, position, 46, size, budget))
        require(h[0] == b"PK\x01\x02" and h[13] == 0 and h[3] & 1 == 0 and h[4] in (0, 8), "unsupported ZIP index entry")
        length = 46 + h[10] + h[11] + h[12]
        require(h[10] > 0 and position + length <= central_end, "truncated ZIP central entry")
        raw_name = _read_at(stream, position + 46, h[10], size, budget)
        try:
            name = raw_name.decode("utf-8" if h[3] & 0x800 else "cp437")
        except UnicodeError as exc:
            raise AdmissionError("invalid ZIP filename encoding") from exc
        canonical_name(name, directory=name.endswith("/")); names.append(name)
        count += 1; require(count <= entries, "ZIP index count mismatch")
        position += length
    require(position == central_end and count == entries and len(set(names)) == count, "ZIP index count/alias mismatch")
    return tuple(names)


def _archive_hash(stream, size, budget):
    stream.seek(0); digest = hashlib.sha256(); remaining = size
    while remaining:
        budget.check(); raw = stream.read(min(BLOCK_BYTES, remaining)); budget.check()
        require(raw, "archive truncated"); digest.update(raw); remaining -= len(raw)
    require(not stream.read(1), "archive grew"); budget.check(); return digest.hexdigest()


def audit_archive(path, expected, pin, budget, *, max_payload_bytes=MAX_PAYLOAD_BYTES):
    path = Path(path); budget.check()
    require(0 < pin.size <= MAX_COMPRESSED_BYTES, "archive compressed byte bound")
    require(expected and len(expected) <= MAX_ENTRIES and sum(p.size for p in expected.values()) <= max_payload_bytes <= MAX_PAYLOAD_BYTES, "archive payload bound exceeded")
    for name in expected: canonical_name(name)
    prefixes = {str(p) for name in expected for p in PurePosixPath(name).parents if str(p) != "."}
    require(not expected.keys() & prefixes, "file/directory prefix conflict")
    with _regular(path, budget) as (stream, before):
        require(before.st_size == pin.size, "archive type/size differs")
        require(_archive_hash(stream, pin.size, budget) == pin.sha256, "archive digest differs")
        index_names = preflight_zip_index(stream, pin.size, budget)
        seen, total = set(), 0
        try:
            with zipfile.ZipFile(stream) as archive:
                entries = archive.infolist()
                require(len(entries) == len(index_names), "actual ZIP index count differs")
                for info, original_name in zip(entries, index_names, strict=True):
                    budget.check()
                    require(info.orig_filename == info.filename == original_name, "normalized ZIP name differs")
                    base = canonical_name(info.filename, directory=info.is_dir())
                    mode = stat.S_IFMT(info.external_attr >> 16)
                    require(info.flag_bits & 1 == 0 and info.compress_type in (0, 8), "encrypted/unsupported ZIP entry")
                    if info.is_dir():
                        require(mode in (0, stat.S_IFDIR) and base in prefixes and info.file_size == 0, "unexpected ZIP directory")
                        continue
                    require(mode in (0, stat.S_IFREG) and base in expected and base not in seen, "extra/aliased ZIP file")
                    record = expected[base]
                    require(info.file_size == record.size and info.compress_size <= pin.size, "indexed file size differs")
                    digest, received = hashlib.sha256(), 0
                    with archive.open(info) as member:
                        while True:
                            budget.check(); raw = member.read(min(BLOCK_BYTES, record.size - received + 1)); budget.check()
                            if not raw: break
                            received += len(raw); require(received <= record.size, "member expanded beyond indexed size")
                            digest.update(raw)
                    require(received == record.size and digest.hexdigest() == record.sha256, "member EOF/hash differs")
                    seen.add(base); total += received
                    require(total <= max_payload_bytes, "aggregate member bound exceeded")
        except (zipfile.BadZipFile, RuntimeError, EOFError, OSError) as exc:
            raise AdmissionError("invalid or changed archive") from exc
        require(seen == expected.keys(), "archive is incomplete")
        require(_archive_hash(stream, pin.size, budget) == pin.sha256, "archive changed during audit")
        require(identity(os.fstat(stream.fileno())) == identity(before), "archive identity changed")
    budget.check()
    return dict(files=len(seen), payload_bytes=total, archive_sha256=pin.sha256)


_PLAN_SEAL = object()


@dataclass(frozen=True, init=False)
class BaselinePlan(Mapping):
    _rows: Mapping
    _seal: object
    _budget: Budget
    def __getitem__(self, key): return self._rows[key]
    def __iter__(self): return iter(self._rows)
    def __len__(self): return len(self._rows)


def prepare_baseline_plan(comparison_path, light_roots, budget=None):
    budget = budget or Budget()
    _resources(Path(comparison_path).parent, admission=True)
    budget.floor_probe = lambda: _resources(Path(comparison_path).parent)
    budget.check(); result = read_original_comparison(comparison_path, budget)
    require(set(light_roots) == set(ARCHIVES), "both historical cohorts required")
    plan = {}
    for world, root in light_roots.items():
        sealed = result["inputs"][world + "-candidate"]
        require(set(sealed) == LIGHT_NAMES, "original reader light set differs")
        require(closed_light_inventory(root, budget) == LIGHT_NAMES, "light input set differs")
        blobs = {}
        for name, record in sealed.items():
            raw = bounded_read(Path(root) / name, MAX_METADATA_BYTES, budget)
            require(len(raw) == record["bytes"] and hashlib.sha256(raw).hexdigest() == record["sha256"], "sealed light bytes differ")
            blobs[name] = raw
        validate_origin(parse_json(blobs["result.json"], budget), world)
        members = build_expected_members(blobs, budget)
        require((len(members), sum(p.size for p in members.values())) == RAW_COUNTS[world], "raw expectations differ from registration")
        plan[world] = MappingProxyType(dict(pin=ARCHIVES[world], members=members,
            historical_role=world + "-candidate", prospective_role="baseline",
            sealed_light=MappingProxyType({n: FilePin(r["bytes"], r["sha256"]) for n, r in sealed.items()})))
    prepared = object.__new__(BaselinePlan)
    object.__setattr__(prepared, "_rows", MappingProxyType(plan))
    object.__setattr__(prepared, "_seal", _PLAN_SEAL)
    object.__setattr__(prepared, "_budget", budget)
    return prepared


def audit_baseline(plan, paths, publication, output, *, control_sha, run_id, job_id, budget=None, now=None):
    """Only an informational audit; no local receipt alone authorizes worlds."""
    require(type(plan) is BaselinePlan and getattr(plan, "_seal", None) is _PLAN_SEAL, "validated baseline plan required")
    budget = budget or plan._budget
    require(budget is plan._budget, "audit budget cannot reset after plan verification")
    now = now or datetime.now(timezone.utc)
    require(set(plan) == set(paths) == set(publication) == set(ARCHIVES), "both cohorts required")
    for world, row in plan.items():
        require(row["pin"] == ARCHIVES[world] and row["historical_role"] == world + "-candidate"
                and row["prospective_role"] == "baseline" and set(row["sealed_light"]) == LIGHT_NAMES
                and (len(row["members"]), sum(p.size for p in row["members"].values())) == RAW_COUNTS[world], "baseline registration differs")
    validate_aggregate_bounds(plan)
    validate_archive_paths(paths)
    for world in plan: validate_publication(publication[world], plan[world]["pin"], now)
    reports = {w: audit_archive(paths[w], row["members"], row["pin"], budget) for w, row in plan.items()}
    budget.check()
    receipt = dict(kind="wealth-floor-baseline-audit", schema_version=1, status="audit_complete_pending_job",
        old_run_id=OLD_RUN, old_control_sha=OLD_CONTROL, old_source_sha=OLD_SOURCE,
        original_comparison_sha256=OLD_COMPARISON, producer=dict(control_sha=control_sha, run_id=run_id, job_id=job_id),
        roles={w: dict(historical_role=w + "-candidate", prospective_role="baseline",
                      original_report_sha256=plan[w]["sealed_light"]["report/validate_report_full.json"].sha256,
                      raw_inventory_sha256=plan[w]["sealed_light"]["raw-inventory.json"].sha256) for w in plan},
        archives=reports, measured=budget.check(), qualification="Requires exact receipt digest and completed producer attestation; grants no candidate worlds.")
    receipt["role_reference_sha256"] = hashlib.sha256(json_bytes(receipt["roles"])).hexdigest()
    return publish_pending_receipt(receipt, output, budget)


def validate_archive_paths(paths):
    require(set(paths) == set(ARCHIVES), "both staged archives required")
    physical = [Path(paths[w]).lstat() for w in paths]
    require(all(stat.S_ISREG(s.st_mode) for s in physical) and len({(s.st_dev, s.st_ino) for s in physical}) == len(physical), "cohort archive physical alias")


def validate_aggregate_bounds(rows):
    require(sum(x["pin"].size for x in rows.values()) <= MAX_COMPRESSED_BYTES, "aggregate compressed storage bound")
    require(sum(p.size for x in rows.values() for p in x["members"].values()) <= MAX_AGGREGATE_PAYLOAD, "aggregate expansion bound")


def publish_pending_receipt(receipt, output, budget):
    """A pending file is never authoritative; late failure requires job refusal."""
    require(receipt.get("status") == "audit_complete_pending_job" and "qualified" not in receipt, "only pending receipts may be written")
    budget.check(); raw = json_bytes(receipt); budget.check()
    digest = hashlib.sha256(raw).hexdigest(); budget.check()
    output = Path(output)
    with _directory(output.parent, budget) as parent:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_NONBLOCK | getattr(os, "O_CLOEXEC", 0)
        fd = os.open(output.name, flags, 0o600, dir_fd=parent)
        with os.fdopen(fd, "wb") as stream:
            require(stat.S_ISREG(os.fstat(stream.fileno()).st_mode), "receipt is not regular")
            stream.write(raw); stream.flush(); os.fsync(stream.fileno()); budget.check()
        os.fsync(parent); budget.check()
    return dict(receipt_sha256=digest, measured_after_fsync=budget.check(), pending_completed_job=True)


def validate_completed_job(receipt, job, *, receipt_sha256, expected_receipt_sha256, control_sha):
    require(hash_shape(receipt_sha256) and receipt_sha256 == expected_receipt_sha256, "audit receipt not externally sealed")
    require(hashlib.sha256(json_bytes(receipt)).hexdigest() == receipt_sha256, "audit receipt bytes differ")
    require(receipt.get("status") == "audit_complete_pending_job", "audit did not complete")
    require(receipt.get("old_run_id") == OLD_RUN and receipt.get("old_control_sha") == OLD_CONTROL
            and receipt.get("old_source_sha") == OLD_SOURCE and receipt.get("original_comparison_sha256") == OLD_COMPARISON,
            "audit historical origin differs")
    producer = receipt.get("producer", {})
    require(producer.get("control_sha") == control_sha and job.get("head_sha") == control_sha
            and job.get("id") == producer.get("job_id") and job.get("run_id") == producer.get("run_id")
            and job.get("status") == "completed" and job.get("conclusion") == "success", "completed successful producer attestation required")


def validate_build_bridge(proof):
    require(proof.get("baseline_source") == OLD_SOURCE and proof.get("baseline_crate") == OLD_CRATE, "baseline build source differs")
    require(proof.get("candidate_source") == CANDIDATE_SOURCE and proof.get("candidate_crate") == CANDIDATE_CRATE, "candidate build source differs")
    context = proof.get("context")
    require(isinstance(context, dict) and context.get("unknown") == []
            and all(isinstance(context.get(k), str) and context[k] for k in ("rustc", "cargo", "maturin", "uv", "target")), "effective build flags/linker remain unknown")
    flags, linker = context.get("flags"), context.get("linker")
    flag_keys = {"RUSTFLAGS", "CARGO_ENCODED_RUSTFLAGS", "RUSTDOCFLAGS", "CARGO_BUILD_TARGET"}
    require(isinstance(flags, dict) and flag_keys <= set(flags) and all(isinstance(k, str) for k in flags)
            and all(v is None or isinstance(v, str) for v in flags.values()), "effective flag states not recorded")
    require(isinstance(linker, dict) and isinstance(linker.get("version"), str) and linker["version"]
            and hash_shape(linker.get("executable_sha256")), "effective linker identity not recorded")
    require(proof.get("mode") == "common_context_exact_rebuild", "historical effective context remains unproven")
    require(proof.get("rebuilt_baseline_native_sha256") == OLD_NATIVE, "different rebuilt native requires fresh baseline worlds")
    require(hash_shape(proof.get("candidate_native_sha256")) and proof["candidate_native_sha256"] != OLD_NATIVE, "candidate binary not distinct/pinned")
    require(proof.get("baseline_context_sha256") == proof.get("candidate_context_sha256") == hashlib.sha256(json_bytes(context)).hexdigest(), "build contexts differ")


def require_candidate_world_admission(proofs):
    require(all(hash_shape(value) for value in REVIEWED_CANDIDATE_PROOFS.values()), "candidate proof pins remain unreviewed; no worlds admitted")
    require(all(hashlib.sha256(json_bytes(proofs.get(k))).hexdigest() == v for k, v in REVIEWED_CANDIDATE_PROOFS.items()), "candidate proof digest differs")


if __name__ == "__main__":
    print(json.dumps(dict(status="inactive", old_run=OLD_RUN, candidate=CANDIDATE_SOURCE,
        candidate_worlds_enabled=False, note="Library interfaces only; no active workflow, transport, build or world launcher.")))
