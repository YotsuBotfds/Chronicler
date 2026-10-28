"""Conservative automatic process budgets; explicit worker counts stay explicit.

CPU visibility/affinity can exceed a container's quota. Read the conventional
Linux cgroup v2/v1 mounts when available, including a process's ancestors;
unavailable platform probes simply leave the other limits in force.
"""
from __future__ import annotations

import os
from pathlib import Path, PurePosixPath

_CGROUP_ROOT = Path("/sys/fs/cgroup")
_PROCESS_CGROUP = Path("/proc/self/cgroup")


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="ascii").strip()
    except (OSError, UnicodeError):
        return ""


def _quota_cpus(quota: str, period: str) -> int | None:
    try:
        q, p = int(quota), int(period)
    except ValueError:
        return None
    # v2 "max" (not an integer), v1 -1 and invalid limits are unbounded.
    return max(1, q // p) if q > 0 and p > 0 else None


def _cgroup_limits() -> list[int]:
    # Common v1 mount names; v2 is mounted directly at /sys/fs/cgroup.
    roots = (_CGROUP_ROOT / "cpu", _CGROUP_ROOT / "cpu,cpuacct")
    locations = {(_CGROUP_ROOT, 2), *((root, 1) for root in roots)}
    for line in _read(_PROCESS_CGROUP).splitlines():
        parts = line.split(":", 2)
        if len(parts) != 3:
            continue
        hierarchy, controllers, name = parts
        relative = PurePosixPath(name)
        if not relative.is_absolute() or ".." in relative.parts:
            continue
        mounts = ((_CGROUP_ROOT, 2),) if hierarchy == "0" and not controllers else (
            tuple((root, 1) for root in roots) if "cpu" in controllers.split(",") else ())
        for root, version in mounts:
            directory = root.joinpath(*relative.parts[1:])
            while True:
                locations.add((directory, version))
                if directory == root:
                    break
                directory = directory.parent
    limits = []
    for directory, version in locations:
        if version == 2:
            fields = _read(directory / "cpu.max").split()
            value = _quota_cpus(*fields) if len(fields) == 2 else None
        else:
            value = _quota_cpus(_read(directory / "cpu.cfs_quota_us"),
                                _read(directory / "cpu.cfs_period_us"))
        if value is not None:
            limits.append(value)
    return limits


def automatic_workers() -> int:
    """Visible CPUs limited by affinity and cgroup quota, minus one CPU
    when more than one is available. Fractional quotas round down, with at
    least one worker even below one CPU. No thread/environment settings change.
    """
    limits = _cgroup_limits()
    for counter in (os.cpu_count, getattr(os, "process_cpu_count", lambda: None)):
        try:
            count = counter()
        except (OSError, NotImplementedError):
            continue
        if isinstance(count, int) and count > 0:
            limits.append(count)
    try:
        affinity = len(os.sched_getaffinity(0))
        if affinity > 0:
            limits.append(affinity)
    except (AttributeError, OSError, NotImplementedError):
        pass
    available = min(limits) if limits else 1
    return max(1, available - 1)
