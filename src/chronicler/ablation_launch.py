"""Pure contracts for a prospective, explicitly selected ablation launcher.

There is deliberately no executor here. The models-only forkserver has not
been qualified against this producer. Admission always refuses it before the
ordinary launcher claims output paths; there is no fresh-process fallback.
This module must remain stdlib-only and must not preload simulation models.
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import islice
import os
import re
import signal
import sys


MAX_BATCH_JOBS = 8
MAX_ARGV_ITEMS = 256
MAX_ARGV_BYTES = 128 * 1024
MAX_ARGUMENT_BYTES = 16 * 1024
_JOB_ID = re.compile(r"[A-Za-z0-9_.-]{1,128}\Z")
_STATUSES = frozenset({"succeeded", "failed", "cancelled", "unattempted"})


class BackendUnavailableError(RuntimeError):
    """The requested backend has no source-qualified runtime implementation."""


def refuse_unqualified_backend(backend, *, arms, parallel, lean_output, window) -> None:
    """Check the narrow proposal, then refuse without importing runtime code.

    Host checks are preliminary eligibility, not an identity or safety proof
    for a requested interpreter, checkpoint, native binary or model preload.
    """
    if type(backend) is not str or backend != "models-forkserver":
        raise ValueError(f"unknown ablation launch backend {backend!r}")
    if type(parallel) is not int or parallel != 1:
        raise ValueError("models-forkserver requires exactly one worker")
    if lean_output is not True:
        raise ValueError("models-forkserver requires lean ablation output")
    if type(window) is not int or window != 20:
        raise ValueError("models-forkserver requires the 20-turn measured window")
    arms = tuple(islice(arms, 3))
    if (not arms or len(arms) > 2 or any(type(arm) is not str for arm in arms)
            or len(set(arms)) != len(arms) or not set(arms) <= {"needs", "kin_roots"}):
        raise ValueError("models-forkserver supports unique needs/kin_roots arms only")
    if (sys.platform != "linux" or sys.implementation.name != "cpython"
            or sys.version_info[:2] != (3, 13)
            or not all(callable(getattr(os, name, None)) for name in ("pidfd_open", "wait4"))
            or not callable(getattr(signal, "pidfd_send_signal", None))):
        raise ValueError("models-forkserver requires Linux CPython 3.13 with pidfd/wait4")
    raise BackendUnavailableError(
        "models-forkserver is unavailable: current-source preload, ownership, "
        "checkpoint and continuation qualification is pending"
    )


def _job_id(value) -> None:
    if type(value) is not str or _JOB_ID.fullmatch(value) is None:
        raise ValueError("job_id must be a bounded opaque identifier")


def _closed_object(payload, fields: set[str]) -> None:
    if type(payload) is not dict or set(payload) != fields:
        raise ValueError("launch payload has missing or unknown fields")


@dataclass(frozen=True, slots=True)
class LaunchJob:
    """Opaque immutable argv, never a loaded world/checkpoint/native object."""

    job_id: str
    argv: tuple[str, ...]

    def __post_init__(self) -> None:
        _job_id(self.job_id)
        if type(self.argv) is not tuple or not 1 <= len(self.argv) <= MAX_ARGV_ITEMS:
            raise ValueError("job argv must be a nonempty bounded tuple")
        total = 0
        for argument in self.argv:
            if type(argument) is not str or "\0" in argument:
                raise ValueError("job argv must contain NUL-free strings")
            if len(argument) > MAX_ARGUMENT_BYTES:
                raise ValueError("job argument exceeds byte limit")
            size = len(argument.encode("utf-8"))
            if size > MAX_ARGUMENT_BYTES:
                raise ValueError("job argument exceeds byte limit")
            total += size + 1
        if not self.argv[0] or total > MAX_ARGV_BYTES:
            raise ValueError("job argv exceeds byte limit or has no executable")

    def payload(self) -> dict:
        return {"job_id": self.job_id, "argv": list(self.argv)}

    @classmethod
    def from_payload(cls, payload) -> LaunchJob:
        _closed_object(payload, {"job_id", "argv"})
        argv = payload["argv"]
        if type(argv) is not list or not 1 <= len(argv) <= MAX_ARGV_ITEMS:
            raise ValueError("job argv must be a nonempty bounded list")
        return cls(payload["job_id"], tuple(argv))


@dataclass(frozen=True, slots=True)
class LaunchOutcome:
    """Terminal execution status; success requires verified writer absence."""

    job_id: str
    status: str
    returncode: int | None
    cleanup_confirmed: bool

    def __post_init__(self) -> None:
        _job_id(self.job_id)
        if type(self.status) is not str or self.status not in _STATUSES:
            raise ValueError("unknown terminal launch status")
        if self.returncode is not None and type(self.returncode) is not int:
            raise ValueError("returncode must be an integer or null")
        if type(self.cleanup_confirmed) is not bool:
            raise ValueError("cleanup confirmation must be boolean")
        if self.status == "succeeded" and (self.returncode != 0 or not self.cleanup_confirmed):
            raise ValueError("success requires exit zero and confirmed owned cleanup")
        if self.status == "unattempted" and (self.returncode is not None or not self.cleanup_confirmed):
            raise ValueError("an unattempted job has no returncode or owned writers")

    def payload(self) -> dict:
        return {"job_id": self.job_id, "status": self.status,
                "returncode": self.returncode, "cleanup_confirmed": self.cleanup_confirmed}

    @classmethod
    def from_payload(cls, payload) -> LaunchOutcome:
        _closed_object(payload, {"job_id", "status", "returncode", "cleanup_confirmed"})
        return cls(**payload)


def ordered_outcomes(jobs: tuple[LaunchJob, ...], outcomes: tuple[LaunchOutcome, ...]) -> tuple[LaunchOutcome, ...]:
    """Require one terminal result per submitted job, then restore input order."""
    if type(jobs) is not tuple or not 1 <= len(jobs) <= MAX_BATCH_JOBS:
        raise ValueError("a launch batch requires one to eight jobs")
    if any(type(job) is not LaunchJob for job in jobs):
        raise ValueError("a launch batch requires immutable jobs")
    ids = tuple(job.job_id for job in jobs)
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate submitted job_id")
    if (type(outcomes) is not tuple or len(outcomes) != len(jobs)
            or any(type(result) is not LaunchOutcome for result in outcomes)):
        raise ValueError("complete terminal result coverage is required")
    by_id = {result.job_id: result for result in outcomes}
    if len(by_id) != len(outcomes) or set(by_id) != set(ids):
        raise ValueError("terminal results must cover submitted job_ids exactly once")
    return tuple(by_id[job_id] for job_id in ids)


def batch_succeeded(jobs: tuple[LaunchJob, ...], outcomes: tuple[LaunchOutcome, ...]) -> bool:
    """Incomplete coverage raises; failed/cancelled/unattempted stays failure."""
    return all(result.status == "succeeded" for result in ordered_outcomes(jobs, outcomes))
