"""Bounded, stdlib-only RAM observation for the dormant native build bridge.

The cgroup paths and all counters are read only on an explicit function call.
Tests inject text fixtures; importing this module probes no runtime resources.
"""
from __future__ import annotations

from pathlib import Path, PurePosixPath
import re

MAX_FILE_BYTES = 1024 * 1024
MAX_ANCESTORS = 128
MAX_COUNTER = 2**64 - 1


class ResourceRefused(ValueError):
    pass


def _require(condition, message):
    if not condition:
        raise ResourceRefused(message)


def _default_read(path):
    with Path(path).open("r", encoding="ascii") as stream:
        return stream.read(MAX_FILE_BYTES + 1)


def _read(reader, path, *, optional=False):
    try:
        value = reader(path)
    except FileNotFoundError:
        if optional:
            return None
        raise ResourceRefused("required resource file missing") from None
    except (OSError, UnicodeError):
        raise ResourceRefused("resource file unreadable") from None
    _require(type(value) is str and value.isascii() and len(value) <= MAX_FILE_BYTES,
             "resource text shape or byte bound invalid")
    return value


def _path(value):
    _require(type(value) is str and value.startswith("/")
             and not any(c in value for c in ("\0", "\n", "\r", "\\")), "unsupported hierarchy path")
    path = PurePosixPath(value)
    _require(path.as_posix() == value and ".." not in path.parts and not value.startswith("//"),
             "noncanonical hierarchy path")
    return path


def _mount_unescape(value):
    # mountinfo escapes these four bytes, including the separator whitespace.
    escapes = {"040": " ", "011": "\t", "012": "\n", "134": "\\"}
    def decode(match):
        _require(match[1] in escapes, "unsupported mountinfo escape")
        return escapes[match[1]]
    decoded = re.sub(r"\\([0-9]{3})", decode, value)
    _require("\\" not in decoded, "unsupported mountinfo path escape")
    return decoded


def _membership(text):
    lines = text.splitlines()
    _require(len(lines) == 1 and lines[0].startswith("0::"),
             "one unified cgroup-v2 membership required")
    return _path(lines[0][3:])


def _mount(text):
    candidates = []
    for line in text.splitlines():
        fields = line.split(" - ")
        _require(len(fields) == 2, "malformed mountinfo record")
        before, after = fields[0].split(), fields[1].split()
        _require(len(before) >= 6 and len(after) >= 3, "malformed mountinfo fields")
        if after[0] == "cgroup2":
            root = _path(_mount_unescape(before[3]))
            point = _path(_mount_unescape(before[4]))
            candidates.append((root, point))
    _require(len(candidates) == 1, "one unambiguous cgroup-v2 mount required")
    root, point = candidates[0]
    _require(str(root) == "/", "bind-root or hidden-parent cgroup mount unsupported")
    return point


def _counter(text):
    value = text.strip()
    _require(re.fullmatch(r"[0-9]{1,20}", value) is not None, "invalid memory counter")
    number = int(value)
    _require(number <= MAX_COUNTER, "memory counter exceeds bound")
    return number


def _controllers(text):
    tokens = text.split()
    _require(len(tokens) == len(set(tokens)) and len(tokens) <= 64
             and all(re.fullmatch(r"[a-z][a-z0-9_]*", item) for item in tokens),
             "invalid cgroup controller evidence")
    return set(tokens)


def memory_admission(*, read_text=None):
    """Return the minimum available bytes across host and visible ancestors.

    ``read_text`` accepts an absolute path string and returns ASCII text or
    raises FileNotFoundError. Every other read failure refuses admission.
    Namespace-invisible ancestors cannot be discovered from these interfaces;
    the returned visibility notes explicitly limit this observation's scope.
    Counters are mutable observations, not reserved memory or an atomic sample.
    """
    reader = _default_read if read_text is None else read_text
    membership_text = _read(reader, "/proc/self/cgroup")
    mountinfo_text = _read(reader, "/proc/self/mountinfo")
    member = _membership(membership_text)
    mount = _mount(mountinfo_text)
    meminfo = _read(reader, "/proc/meminfo")
    available = [line for line in meminfo.splitlines() if line.startswith("MemAvailable:")]
    _require(len(available) == 1, "one host MemAvailable observation required")
    match = re.fullmatch(r"MemAvailable:\s*([0-9]{1,20})\s+kB\s*", available[0])
    _require(match is not None, "invalid host MemAvailable")
    host = _counter(match[1]) * 1024
    _require(host <= MAX_COUNTER, "host memory observation exceeds bound")

    _require(len(member.parts) <= MAX_ANCESTORS, "visible cgroup ancestor bound exceeded")
    paths = list(reversed((member, *member.parents)))
    rows, headroom = [], [host]
    parent_enabled = None
    for relative in paths:
        directory = mount / str(relative).lstrip("/")
        controllers = _controllers(_read(reader, str(directory / "cgroup.controllers")))
        enabled = _controllers(_read(reader, str(directory / "cgroup.subtree_control")))
        _require(enabled <= controllers, "enabled cgroup controllers lack availability evidence")
        maximum_text = _read(reader, str(directory / "memory.max"), optional=True)
        current_text = _read(reader, str(directory / "memory.current"), optional=True)
        _require((maximum_text is None) == (current_text is None), "partial memory controller files")
        root = str(relative) == "/"
        if maximum_text is None:
            _require(root or "memory" not in parent_enabled,
                     "enabled memory controller files missing")
            maximum = current = remaining = None
            status = "unbounded_local_root" if root else "no_local_memory_controller_inherits_visible_parents"
        else:
            _require(root or "memory" in parent_enabled,
                     "memory files contradict parent controller evidence")
            current = _counter(current_text)
            maximum = None if maximum_text.strip() == "max" else _counter(maximum_text)
            remaining = None if maximum is None else max(0, maximum - current)
            status = "unbounded_local_limit" if maximum is None else "bounded_local_limit"
            if remaining is not None:
                headroom.append(remaining)
        rows.append(dict(cgroup_path=str(relative), directory=str(directory),
                         controllers=sorted(controllers), subtree_control=sorted(enabled),
                         memory_max_bytes=maximum, memory_current_bytes=current,
                         remaining_bytes=remaining, observation=status))
        parent_enabled = enabled
    _require(_read(reader, "/proc/self/cgroup") == membership_text,
             "process cgroup membership changed during observation")
    _require(_read(reader, "/proc/self/mountinfo") == mountinfo_text,
             "cgroup mount mapping changed during observation")
    return dict(available_bytes=min(headroom), host_available_bytes=host,
                process_cgroup_path=str(member), cgroup_mount=str(mount),
                ancestor_order="visible root to process cgroup", visible_ancestors=rows,
                visibility_limits=[
                    "Includes every ancestor visible in this unified cgroup namespace; namespace-invisible ancestors are unobservable.",
                    "Non-root cgroup mount roots, multiple cgroup2 mounts and non-unified memberships are refused.",
                    "Mutable host and cgroup counters are separate observations, not an atomic sample or memory reservation.",
                ])
