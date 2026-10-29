#!/usr/bin/env python3
"""Inactive contracts for a source-pinned, paired native build.

This contract module executes no compiler, native import, source import, or
world. The separate dormant controller supplies the reviewed execution boundary.
Compiler traces are consumed in memory; only bounded compiler/linker records
survive, never an environment dump or arbitrary child-process arguments.
"""
from __future__ import annotations

import argparse
import ast
from copy import deepcopy
from dataclasses import dataclass, field
import hashlib
import io
import json
import math
from pathlib import PurePosixPath
import re
import stat
from types import MappingProxyType
import zipfile

BASELINE_SOURCE = "d0281e5f57c508f27cea1676f36e0e6ed1225c9d"
BASELINE_CRATE = "a4703ef4e9a21b5dbb194d318536a46e6ca8b71c"
CANDIDATE_SOURCE = "503070175e3e78d9014add158ead8f16ce940843"
CANDIDATE_CRATE = "93b32cd9b02eccf4900b33cdaeece08262be2330"
OLD_NATIVE = "06db5e19bdda13d7a536b236d677348f5ea7cb5adad2929962f0485192f9b4d6"
OLD_BUILD_MANIFEST = "013a57c5e59993587acd65eb33c6ff1d16984796de11dbec81df686eb33210d3"
LOCK_SHA256 = "986547c01fd1dcd9bf598404124fde4ddc1e3d67db9a1d595a5304f18dacee10"
PYPROJECT_SHA256 = "d14f5588112927a0d8d889c30f04af90e81bc2cf4096b9ed91d8a51d83a2ac32"
RUSTC_COMMIT = "58cf8f9c35b355199727627d07ae34a4e2846d67"
PYTHON_VERSION = "3.13.17"
TARGET = "x86_64-unknown-linux-gnu"
CLASS_NAMES = ("AgentSimulator", "EcologySimulator", "PoliticsSimulator")
NATIVE_MEMBER = "chronicler_agents/chronicler_agents.cpython-313-x86_64-linux-gnu.so"
WHEEL_NAME = "chronicler_agents-0.1.0-cp313-cp313-manylinux_2_34_x86_64.whl"
SOURCES = MappingProxyType({
    "baseline": (BASELINE_SOURCE, BASELINE_CRATE),
    "candidate": (CANDIDATE_SOURCE, CANDIDATE_CRATE),
})
OLD_SCHEMAS = MappingProxyType({
    "AgentSimulator": (1, "dcf0c34097c88451", "0b792f3ec33ac68605caf7b6d66fa7462c919b52e6f489f0e3dd7fa42f9fba3b"),
    "EcologySimulator": (1, "4ab7f8c199b5e5f8", "bf7daf59c53773518770b90f5a5dee5b71e63d2a62d2af6c756922a07a503aff"),
    "PoliticsSimulator": (1, "b1a710f3450f5015", "48e27b42f817e0057ad5f15bf2c2e8d8cca072314a9ca666753f2c9341c47395"),
})
REGRESSIONS = (
    "behavior::tests::household_migration_poor_balances_cannot_amplify_positive_utility",
    "behavior::tests::household_migration_without_additional_wealth_keeps_raw_utility",
    "behavior::tests::household_migration_ordinary_and_threshold_balances_keep_original_bits",
    "behavior::tests::household_migration_credit_debit_can_reach_the_low_balance_case",
)

MIB = 1024**2
MAX_WHEEL_BYTES = 16 * MIB
MAX_NATIVE_BYTES = 32 * MIB
MAX_WHEEL_EXPANSION = 64 * MIB
MAX_TRACE_BYTES = 64 * MIB
MAX_TRACE_LINE = 256 * 1024
MAX_TRACE_RECORDS = 10000
MAX_ARG_BYTES = 128 * 1024
MAX_ARGC = 4096
MAX_PENDING_EXECS = 2048
REQUIRED_FLAGS = frozenset(("RUSTFLAGS", "CARGO_ENCODED_RUSTFLAGS", "RUSTDOCFLAGS", "CARGO_BUILD_TARGET"))
OPTIONAL_FLAGS = frozenset((
    "RUSTC_WRAPPER", "RUSTC_WORKSPACE_WRAPPER", "RUSTC", "RUSTDOC", "PYO3_PYTHON",
    "CARGO_TARGET_DIR", "CARGO_BUILD_JOBS", "CARGO_INCREMENTAL", "CC", "CXX", "AR",
    "CFLAGS", "CXXFLAGS", "CPPFLAGS", "LDFLAGS", "LD_LIBRARY_PATH", "LD_PRELOAD",
    "CARGO_TARGET_X86_64_UNKNOWN_LINUX_GNU_LINKER",
    "CARGO_TARGET_X86_64_UNKNOWN_LINUX_GNU_RUSTFLAGS",
    "CARGO_HOME", "RUSTUP_HOME", "RUSTUP_TOOLCHAIN", "CARGO_TERM_COLOR",
    "HOME", "PATH",
))
CONTEXT_FIELDS = frozenset((
    "unknown", "rustc", "cargo", "maturin", "uv", "python", "target", "flags", "linker",
    "executables", "host", "release_profile", "features", "lock_sha256", "pyproject_sha256",
    "manifest_path", "target_path", "staging_wheel_path", "build_argv",
    "cargo_config",
))
WORKFLOW_INVARIANTS = "2ef17e8d86ed16d146beeeb2ffedcaf8308da1e3daad8d9fbc0eddd97f48f487"
ACTIVE_BRANCH = "lead/cloud-wealth-floor-native-build-bridge-2-20261029"
WORKFLOW_PATH = ".github/workflows/wealth-floor-native-build-bridge.yml"


class BridgeRefused(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise BridgeRefused(message)


def hash_shape(value):
    return type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def canonical_bytes(value):
    return (json.dumps(value, sort_keys=True, allow_nan=False, separators=(",", ":")) + "\n").encode()


def digest(value):
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def absolute_path(value):
    require(type(value) is str and value and "\0" not in value and "\\" not in value, "unsafe absolute path")
    path = PurePosixPath(value)
    require(path.is_absolute() and path.as_posix() == value and ".." not in path.parts, "unsafe absolute path")
    return value


@dataclass(frozen=True)
class Policy:
    """Provisional wall/resource ceilings, including teardown and receipt work.

    CPU clocks are descriptive; this protocol makes no aggregate CPU-budget
    admission claim. The controller deadline and separate job timeout bound work.
    """

    wall_seconds: float = 1800.0
    cleanup_wall_reserve: float = 25.0
    admission_disk_bytes: int = 12 * 1024**3
    admission_ram_bytes: int = 2 * 1024**3
    running_disk_bytes: int = 3 * 1024**3
    running_ram_bytes: int = 1024**3

    def __post_init__(self):
        for value in (self.wall_seconds, self.cleanup_wall_reserve):
            require(type(value) in (int, float) and math.isfinite(value) and value > 0, "invalid build budget")
        require(self.wall_seconds <= 1800, "build budget exceeds registration")
        require(self.cleanup_wall_reserve >= 25 and self.cleanup_wall_reserve < self.wall_seconds,
                "budget reserve exceeds ceiling")
        require(type(self.admission_disk_bytes) is int and self.admission_disk_bytes >= 12 * 1024**3,
                "build admission disk floor lowered")
        require(type(self.admission_ram_bytes) is int and self.admission_ram_bytes >= 2 * 1024**3,
                "build admission RAM floor lowered")
        require(type(self.running_disk_bytes) is int and self.running_disk_bytes >= 3 * 1024**3,
                "running disk floor lowered")
        require(type(self.running_ram_bytes) is int and self.running_ram_bytes >= 1024**3,
                "running RAM floor lowered")


_TOOL = re.compile(r"(?:rustc|cargo|cc|gcc(?:-\d+)?|g\+\+(?:-\d+)?|clang(?:\+\+)?(?:-\d+)?|"
                   r"collect2|cc1|cc1plus|lto1|lto-wrapper|ld(?:\.lld|\.bfd|\.gold)?|rust-lld|lld|ar|ranlib|as|"
                   r"x86_64-linux-gnu-(?:gcc|g\+\+|ld(?:\.lld|\.bfd|\.gold)?|ar|ranlib|as)(?:-\d+)?)\Z")
LINKER_NAMES = frozenset(("ld", "ld.bfd", "ld.gold", "ld.lld", "rust-lld", "lld",
    "x86_64-linux-gnu-ld", "x86_64-linux-gnu-ld.bfd", "x86_64-linux-gnu-ld.gold", "x86_64-linux-gnu-ld.lld"))
_CREDENTIAL = re.compile(r"(?i)(?:authorization\s*[:=]|bearer\s+|--(?:token|password|secret|credential)(?:=|\Z)|"
                         r"(?:[?&]|\b)(?:access_token|api_key|password|secret|signature|sig)=|[a-z]+://[^/\s]*@)")
_START = re.compile(r"^\s*(?:\[pid\s+(\d+)\]\s+|(\d+)\s+)?(?:\d+\.\d+\s+)?(execve(?:at)?)\(")
_RESUMED = re.compile(r"^\s*(?:\[pid\s+(\d+)\]\s+|(\d+)\s+)?(?:\d+\.\d+\s+)?<\.\.\. execve(?:at)? resumed>(.*)$")
_CALL = re.compile(r'^execve\(("(?:[^"\\]|\\.)*"),\s*(\[.*\]),\s*'
                   r'(?:0x[0-9a-f]+|NULL)\s*(?:/\*\s*\d+\s+vars\s*\*/)?\s*\)\s*=\s*(-?\d+)(?:\s+[^\n]*)?$')


def _literal(value):
    try:
        return ast.literal_eval(value)
    except (ValueError, SyntaxError, MemoryError, RecursionError) as exc:
        raise BridgeRefused("truncated or invalid execve arguments") from exc


def parse_execve(call):
    """Return a sanitized selected-tool record, or None for ignored/failed calls.

    No raw line, ignored process arguments or environment values are returned.
    This parser accepts the non-verbose pointer/count environment format only.
    """
    require(type(call) is str and len(call.encode()) <= MAX_TRACE_LINE, "execve line byte bound exceeded")
    require(not call.startswith("execveat("), "unresolved execveat executable")
    match = _CALL.fullmatch(call)
    require(match is not None, "truncated, verbose-environment or unknown execve format")
    if int(match[3]) != 0:
        return None
    executable, argv = _literal(match[1]), _literal(match[2])
    require(type(executable) is str and type(argv) is list and all(type(x) is str for x in argv), "invalid execve values")
    if not _TOOL.fullmatch(PurePosixPath(executable).name):
        return None
    absolute_path(executable)
    require(0 < len(argv) <= MAX_ARGC and sum(len(x.encode()) for x in argv) <= MAX_ARG_BYTES, "compiler argv byte/count cap")
    require(not any(_CREDENTIAL.search(x) for x in (executable, *argv)), "potential credential-bearing compiler argv refused")
    require(not any(x.startswith("@") or ",@" in x or "link-arg=@" in x for x in argv), "unresolved compiler/linker response file")
    require(not any("\0" in x for x in argv), "NUL in compiler argv")
    return dict(executable=executable, argv=argv)


@dataclass
class TraceAccumulator:
    """Bounded streaming strace consumer; raw input is never retained."""

    records: list = field(default_factory=list)
    unknown: set = field(default_factory=set)
    pending: dict = field(default_factory=dict)
    observed_bytes: int = 0
    retained_bytes: int = 0
    ignored_calls: int = 0

    def feed(self, raw):
        require(type(raw) is bytes, "trace input must be bytes")
        self.observed_bytes += len(raw)
        require(len(raw) <= MAX_TRACE_LINE and self.observed_bytes <= MAX_TRACE_BYTES, "trace byte cap exceeded")
        try:
            line = raw.decode("ascii").rstrip("\n")
        except UnicodeDecodeError:
            self.unknown.add("non_ascii_trace")
            return
        resumed = _RESUMED.fullmatch(line)
        if resumed:
            pid = resumed[1] or resumed[2]
            if pid not in self.pending:
                self.unknown.add("unmatched_resumed_execve")
                return
            line = self.pending.pop(pid) + resumed[3]
            require(len(line.encode()) <= MAX_TRACE_LINE, "resumed execve line cap exceeded")
        else:
            start = _START.match(line)
            if not start:
                # strace exit/signal lines contain no arguments and add no tool evidence.
                if "execve" in line:
                    self.unknown.add("unknown_execve_format")
                return
            pid = start[1] or start[2]
            line = line[start.start(3):]
            if line.endswith("<unfinished ...>"):
                require(pid is not None and pid not in self.pending and len(self.pending) < MAX_PENDING_EXECS,
                        "unfinished execve ownership/count invalid")
                self.pending[pid] = line[:-len("<unfinished ...>")]
                return
        try:
            record = parse_execve(line)
        except BridgeRefused as exc:
            # Reasons are fixed strings; the rejected raw argv cannot leak here.
            self.unknown.add(str(exc))
            return
        if record is None:
            self.ignored_calls += 1
            return
        encoded = canonical_bytes(record)
        require(len(self.records) < MAX_TRACE_RECORDS and self.retained_bytes + len(encoded) <= MAX_TRACE_BYTES,
                "retained compiler trace cap exceeded")
        self.records.append(record)
        self.retained_bytes += len(encoded)

    def finish(self):
        unknown = set(self.unknown)
        if self.pending:
            unknown.add("unfinished_execve_at_eof")
        tools = {PurePosixPath(row["executable"]).name for row in self.records}
        if "rustc" not in tools:
            unknown.add("no_observed_rustc")
        if not tools & LINKER_NAMES:
            unknown.add("no_observed_actual_linker")
        return dict(records=list(self.records), unknown=sorted(unknown), observed_bytes=self.observed_bytes,
            retained_bytes=self.retained_bytes, ignored_calls=self.ignored_calls,
            scope="selected compiler/linker successful execve argv only; no environments or ignored child argv")


def schemas_equal_registered(schemas):
    require(type(schemas) is dict and set(schemas) == set(CLASS_NAMES), "all three compiled-class schemas required")
    for name, expected in OLD_SCHEMAS.items():
        row = schemas[name]
        require(type(row) is dict and set(row) == {"version", "fingerprint", "schema_sha256"}, "schema fields differ")
        require(type(row["version"]) is int and (row["version"], row["fingerprint"], row["schema_sha256"]) == expected,
                "compiled checkpoint schema differs")


def inspect_wheel(raw, filename):
    """Bounded byte inspection only; never extract or import its native module."""
    require(type(raw) is bytes and 0 < len(raw) <= MAX_WHEEL_BYTES and filename == WHEEL_NAME, "wheel size/name differs")
    # The controlled wheels are small, non-ZIP64 archives. Admit the directory
    # before ZipFile constructs Python objects from it.
    end = raw.rfind(b"PK\x05\x06", max(0, len(raw) - 65557))
    require(end >= 0 and end + 22 <= len(raw), "wheel EOCD missing")
    import struct
    e = struct.unpack("<4s4H2LH", raw[end:end + 22])
    require(e[1] == e[2] == 0 and e[3] == e[4] and 0 < e[4] <= 128
            and 0 < e[5] <= MIB and e[6] + e[5] == end and end + 22 + e[7] == len(raw), "wheel directory bound differs")
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            infos = archive.infolist()
            names = [row.filename for row in infos]
            require(len(infos) == e[4] and len(set(names)) == len(names), "wheel member aliases/count differ")
            require(sum(row.file_size for row in infos) <= MAX_WHEEL_EXPANSION, "wheel expansion cap")
            for row in infos:
                require(row.orig_filename == row.filename and row.filename and "\\" not in row.filename and "\0" not in row.filename,
                        "unsafe wheel member")
                normalized = row.filename[:-1] if row.is_dir() else row.filename
                require(normalized not in ("", "."), "unsafe wheel member")
                p = PurePosixPath(normalized)
                require(not p.is_absolute() and p.as_posix() == normalized and ".." not in p.parts
                        and ":" not in p.parts[0] and row.flag_bits & 1 == 0 and row.compress_type in (0, 8), "unsafe wheel member")
                mode = stat.S_IFMT(row.external_attr >> 16)
                require(mode in ((0, stat.S_IFDIR) if row.is_dir() else (0, stat.S_IFREG))
                        and 0 <= row.file_size <= MAX_NATIVE_BYTES and (not row.is_dir() or row.file_size == 0),
                        "wheel member type/expansion differs")
            native = [row for row in infos if row.filename.endswith(".so")]
            require(len(native) == 1 and native[0].filename == NATIVE_MEMBER and 0 < native[0].file_size <= MAX_NATIVE_BYTES,
                    "wheel compiled-member set differs")
            digest_native = hashlib.sha256()
            received = 0
            with archive.open(native[0]) as stream:
                while block := stream.read(min(MIB, native[0].file_size - received + 1)):
                    received += len(block)
                    require(received <= native[0].file_size, "native member exceeds indexed size")
                    digest_native.update(block)
            require(received == native[0].file_size, "native member truncated")
    except (zipfile.BadZipFile, RuntimeError, EOFError) as exc:
        raise BridgeRefused("wheel archive invalid") from exc
    return dict(filename=filename, bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest(), native_member=NATIVE_MEMBER,
        native_bytes=received, native_sha256=digest_native.hexdigest())


def validate_context(context):
    require(type(context) is dict and set(context) == CONTEXT_FIELDS, "common build context fields differ")
    require(type(context["unknown"]) is list and all(type(x) is str for x in context["unknown"]), "context unknowns invalid")
    require(context["unknown"] == [], "effective build context incomplete")
    require(type(context["rustc"]) is str and context["rustc"].startswith("rustc 1.99.1 ") and RUSTC_COMMIT in context["rustc"]
            and "LLVM version: 23.1.1" in context["rustc"], "rustc version/commit differs")
    require(type(context["cargo"]) is str and context["cargo"].strip() == "cargo 1.99.1 (5f94df478 2026-08-27)", "cargo version differs")
    require(context["maturin"] == "maturin 1.15.0" and context["uv"] == "uv 0.13.6 (x86_64-unknown-linux-gnu)"
            and context["python"] == PYTHON_VERSION and context["target"] == TARGET, "build tool/runtime version differs")
    flags = context["flags"]
    require(type(flags) is dict and set(flags) == REQUIRED_FLAGS | OPTIONAL_FLAGS
            and all(value is None or type(value) is str for value in flags.values()), "build flag states incomplete")
    require(all(flags.get(key) in (None, "") for key in ("RUSTFLAGS", "CARGO_ENCODED_RUSTFLAGS", "RUSTDOCFLAGS",
        "RUSTC_WRAPPER", "RUSTC_WORKSPACE_WRAPPER", "CARGO_BUILD_TARGET", "LD_PRELOAD")), "unregistered effective flag or wrapper")
    require(flags.get("CARGO_BUILD_JOBS") == "1" and flags.get("CARGO_INCREMENTAL") == "0", "Cargo limits differ")
    for key in ("HOME", "CARGO_HOME", "RUSTUP_HOME", "PYO3_PYTHON"):
        if flags.get(key) is not None:
            absolute_path(flags[key])
    linker = context["linker"]
    require(type(linker) is dict and set(linker) == {"path", "version", "executable_sha256"}
            and type(linker["version"]) is str and linker["version"] and hash_shape(linker["executable_sha256"]), "linker identity incomplete")
    absolute_path(linker["path"])
    executables = context["executables"]
    require(type(executables) is list and 0 < len(executables) <= 64, "compiler/linker executable set incomplete")
    seen = set()
    for row in executables:
        require(type(row) is dict and set(row) == {"path", "sha256", "version"} and hash_shape(row["sha256"])
                and type(row["version"]) is str and row["version"], "compiler/linker executable identity incomplete")
        absolute_path(row["path"])
        require(row["path"] not in seen, "duplicate executable identity")
        seen.add(row["path"])
    require(any(row["path"] == linker["path"] and row["sha256"] == linker["executable_sha256"] for row in executables),
            "linker not in observed executable identities")
    require({"rustc", "cargo"} <= {PurePosixPath(row["path"]).name for row in executables}, "compiler/Cargo executable identity absent")
    host = context["host"]
    require(type(host) is dict and set(host) == {"system", "machine", "platform", "image_os", "image_version"}
            and host["system"] == "Linux" and host["machine"] == "x86_64" and type(host["platform"]) is str and host["platform"]
            and all(value is None or type(value) is str for value in host.values()), "current host identity incomplete")
    profile = context["release_profile"]
    require(type(profile) is dict and {key: type(value) for key, value in profile.items()} ==
            {"codegen-units": int, "lto": bool, "opt-level": int}
            and profile == {"codegen-units": 1, "lto": True, "opt-level": 3}
            and context["features"] == ["pyo3/extension-module"], "native profile/features differ")
    require(context["lock_sha256"] == LOCK_SHA256 and context["pyproject_sha256"] == PYPROJECT_SHA256, "locked build inputs differ")
    for key in ("manifest_path", "target_path", "staging_wheel_path"):
        absolute_path(context[key])
    require(context["manifest_path"].endswith("/candidate/chronicler-agents/Cargo.toml"), "common producer path differs")
    require(context["build_argv"] == ["-m", "maturin", "build", "--release", "--locked", "--manifest-path",
        context["manifest_path"], "--out", context["staging_wheel_path"]], "maturin command differs")
    require(flags.get("CARGO_TARGET_DIR") == context["target_path"], "actual Cargo target path differs")
    config = context["cargo_config"]
    require(type(config) is dict and set(config) == {"checked_absent_paths", "scope"}
            and type(config["checked_absent_paths"]) is list and 0 < len(config["checked_absent_paths"]) <= 128
            and config["scope"] == "Cargo home and command/manifest ancestors; config files absent",
            "Cargo configuration visibility incomplete")
    for name in config["checked_absent_paths"]:
        absolute_path(name)
    return digest(context)


def validate_phase(phase, role):
    require(role in SOURCES and type(phase) is dict, "unknown build phase")
    source, crate = SOURCES[role]
    require(phase.get("source_sha") == source and phase.get("crate_tree") == crate and phase.get("source_clean") is True,
            "source/crate/standing differs")
    require(hash_shape(phase.get("source_before_sha256")) and phase["source_before_sha256"] == phase.get("source_after_sha256"),
            "source changed during build phase")
    require(phase.get("build_complete") is True and phase.get("cleanup_complete") is True, "phase execution incomplete")
    wheel, probe = phase.get("wheel"), phase.get("probe")
    require(type(wheel) is dict and wheel.get("filename") == WHEEL_NAME and hash_shape(wheel.get("sha256"))
            and hash_shape(wheel.get("native_sha256")) and wheel.get("native_member") == NATIVE_MEMBER,
            "wheel identity incomplete")
    require(type(probe) is dict and probe.get("compiled_extension") is True and probe.get("real_exported_classes") is True
            and probe.get("native_sha256") == wheel["native_sha256"] and probe.get("python") == PYTHON_VERSION
            and probe.get("source_imports") == [] and probe.get("native_pools_created") == 0,
            "actual isolated native API probe incomplete")
    require(type(probe.get("native_pools_created")) is int, "invalid native API pool count")
    schemas_equal_registered(probe.get("schemas"))
    absolute_path(probe.get("native_path"))
    absolute_path(probe.get("environment_root"))
    require(PurePosixPath(probe["native_path"]).is_relative_to(probe["environment_root"]), "native origin outside isolated environment")
    require(probe["native_path"].endswith("/" + NATIVE_MEMBER), "native compiled origin member differs")
    if role == "candidate":
        require(phase.get("regressions") == {name: "PASS" for name in REGRESSIONS}, "four genuine native regressions required")
    return validate_context(phase.get("context"))


def classify_pair(baseline, candidate, final_budget):
    """A positive local result remains pending a completed producer attestation."""
    baseline_context = validate_phase(baseline, "baseline")
    candidate_context = validate_phase(candidate, "candidate")
    require(baseline_context == candidate_context, "source phases used different effective contexts")
    require(type(final_budget) is dict and final_budget.get("final_observation") is True
            and final_budget.get("cleanup_complete") is True and final_budget.get("live_processes") == 0,
            "closed whole-build accounting required")
    require(type(final_budget.get("live_processes")) is int, "invalid final process count")
    require(type(final_budget.get("wall_seconds")) in (int, float) and math.isfinite(final_budget["wall_seconds"])
            and 0 <= final_budget["wall_seconds"] <= 1800 and final_budget.get("wall_limit_seconds") == 1800,
            "final controller wall budget exceeded")
    require(all(type(final_budget.get(key)) in (int, float) and math.isfinite(final_budget[key]) and final_budget[key] >= 0
                for key in ("controller_measured_cpu_seconds", "waited_children_cpu_seconds")), "invalid measured child/self CPU")
    require(candidate["wheel"]["native_sha256"] != baseline["wheel"]["native_sha256"], "candidate native is not distinct")
    require(candidate["wheel"]["sha256"] != baseline["wheel"]["sha256"], "candidate wheel is not distinct")
    old_env = PurePosixPath(baseline["probe"]["environment_root"])
    new_env = PurePosixPath(candidate["probe"]["environment_root"])
    require(not old_env.is_relative_to(new_env) and not new_env.is_relative_to(old_env), "native probe environments are not independent")
    old_reproduced = baseline["wheel"]["native_sha256"] == OLD_NATIVE
    return dict(schema_version=1, kind="wealth-floor-native-build-bridge", status="build_complete_pending_job",
        mode="common_context_exact_rebuild", classification="historical_reuse_eligible" if old_reproduced else "fresh_baseline_required",
        historical_reuse_eligible=old_reproduced, baseline_source=BASELINE_SOURCE, baseline_crate=BASELINE_CRATE,
        candidate_source=CANDIDATE_SOURCE, candidate_crate=CANDIDATE_CRATE,
        old_build_manifest_sha256=OLD_BUILD_MANIFEST, rebuilt_baseline_native_sha256=baseline["wheel"]["native_sha256"],
        candidate_native_sha256=candidate["wheel"]["native_sha256"], baseline_context_sha256=baseline_context,
        candidate_context_sha256=candidate_context, context=baseline["context"], measured=final_budget,
        candidate_worlds_admitted=False, original_context_unknown=["inherited effective flags", "target overrides", "linker/full argv", "Ubuntu image"],
        qualification="Pending exact receipt digest, completed successful producer job and artifact publication. No world grant.")


def workflow_contract(workflow):
    """Recognize only the dormant template or its exact future push activation.

    Defining both states now avoids an obsolete preparation-only assertion at
    activation. Every command, source, environment, budget and retention setting
    remains sealed after removing only the trigger/display name and job guard.
    """
    require(type(workflow) is dict and not ("on" in workflow and True in workflow), "ambiguous workflow trigger")
    value = deepcopy(workflow)
    value.pop("name", None)
    trigger = value.pop("on") if "on" in value else value.pop(True, None)
    jobs = value.get("jobs", {})
    require(type(jobs) is dict and set(jobs) == {"paired-native-build"}, "workflow job set differs")
    guard = jobs["paired-native-build"].pop("if", None)
    if trigger == {"workflow_dispatch": {}}:
        require(guard == "${{ false }}", "prepared build job must be disabled")
        state = "prepared"
    else:
        require(trigger == {"push": {"branches": [ACTIVE_BRANCH], "paths": [WORKFLOW_PATH]}}, "unregistered build trigger")
        require(guard == "${{ github.event_name == 'push' && github.ref == 'refs/heads/" + ACTIVE_BRANCH + "' }}",
                "unregistered active build guard")
        state = "activated"
    require(digest(value) == WORKFLOW_INVARIANTS, "reviewed workflow body differs")
    return state


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("describe", "build"), nargs="?", default="describe")
    args = parser.parse_args(argv)
    if args.command == "build":
        # The contract library never starts execution. The separate controller
        # and any future workflow activation retain their own reviewed boundary.
        raise BridgeRefused("contract library executes no builds; use only the separately reviewed dormant controller")
    print(json.dumps(dict(kind="inactive-wealth-floor-native-build-bridge", source_pair=dict(SOURCES),
        candidate_worlds_admitted=False, controller="wealth_floor_native_build_controller.py", library_executes_builds=False), sort_keys=True))
    return 0


if __name__ == "__main__":
    main()
