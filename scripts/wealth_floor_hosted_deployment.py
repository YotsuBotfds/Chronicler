"""Small deployment precondition for the sealed direct hosted-VM jobs.

No environment or proc information is read until the explicit function call.
This is VM-context evidence, not an attestation about invisible provider layers.
"""
from __future__ import annotations

import errno
import os
from pathlib import Path
import re


REFUSAL_CODES = frozenset((
    "runner_flags", "pid1_comm_unavailable", "pid1_comm_invalid", "pid1_comm_changed",
    "self_namespace_unavailable", "self_namespace_invalid", "self_namespace_changed",
    "pid1_namespace_unavailable", "pid1_namespace_invalid", "pid1_namespace_changed",
    "namespace_mismatch",
))


class DeploymentRefused(ValueError):
    def __init__(self, code):
        if code not in REFUSAL_CODES:
            raise ValueError("unregistered deployment refusal code")
        self.code = code
        super().__init__(code)


def _require(condition, code):
    if not condition:
        raise DeploymentRefused(code)


def _read_text(path):
    with Path(path).open("r", encoding="ascii") as stream:
        return stream.read(129)


def _comm(read_text):
    try:
        value = read_text("/proc/1/comm")
    except (OSError, UnicodeError) as exc:
        raise DeploymentRefused("pid1_comm_unavailable") from exc
    _require(type(value) is str and value.isascii() and len(value) <= 128 and value.strip() == "systemd",
             "pid1_comm_invalid")
    return value


def _namespace(read_link, path, role, *, allow_eacces=False):
    try:
        value = read_link(path)
    except OSError as exc:
        if allow_eacces and type(exc.errno) is int and exc.errno == errno.EACCES:
            return None, errno.EACCES
        raise DeploymentRefused(role + "_namespace_unavailable") from exc
    except UnicodeError as exc:
        raise DeploymentRefused(role + "_namespace_unavailable") from exc
    _require(type(value) is str and value.isascii() and len(value) <= 128
             and re.fullmatch(r"cgroup:\[[1-9][0-9]{0,19}\]", value), role + "_namespace_invalid")
    return value, None


def hosted_vm_precondition(*, environ=None, read_text=None, read_link=None):
    env = os.environ if environ is None else environ
    read_text = _read_text if read_text is None else read_text
    read_link = os.readlink if read_link is None else read_link
    _require(env.get("GITHUB_ACTIONS") == "true" and env.get("RUNNER_ENVIRONMENT") == "github-hosted",
             "runner_flags")
    comm = _comm(read_text)
    own, _ = _namespace(read_link, "/proc/self/ns/cgroup", "self")
    init, init_errno = _namespace(read_link, "/proc/1/ns/cgroup", "pid1", allow_eacces=True)
    if init_errno is None:
        _require(own == init, "namespace_mismatch")
    comm_after = _comm(read_text)
    _require(comm_after == comm, "pid1_comm_changed")
    own_after, _ = _namespace(read_link, "/proc/self/ns/cgroup", "self")
    _require(own_after == own, "self_namespace_changed")
    init_after, errno_after = _namespace(read_link, "/proc/1/ns/cgroup", "pid1", allow_eacces=True)
    _require((init_after, errno_after) == (init, init_errno), "pid1_namespace_changed")
    _require(env.get("GITHUB_ACTIONS") == "true" and env.get("RUNNER_ENVIRONMENT") == "github-hosted",
             "runner_flags")
    verified = init_errno is None
    evidence_scope = ("VM-context evidence with readable matching cgroup namespaces" if verified else
        "VM-context evidence with PID1 cgroup namespace unreadable: EACCES13 twice; namespace equality unverified")
    return dict(precondition_version=2, github_actions="true", runner_environment="github-hosted", pid1_comm="systemd",
                self_cgroup_namespace=own, pid1_cgroup_namespace=init,
                pid1_cgroup_namespace_errno=init_errno,
                namespace_equal=True if verified else None, namespace_equality_verified=verified,
                namespace_equality_status="verified_equal" if verified else "unverified_permission_denied",
                observations=dict(pid1_comm=[comm, comm_after], self_cgroup_namespace=[own, own_after],
                    pid1_cgroup_namespace=[init, init_after], pid1_cgroup_namespace_errno=[init_errno, errno_after]),
                required_job_context="Sealed direct ubuntu-24.04 job, with no configured job container",
                evidence_scope=evidence_scope,
                admission_scope="Deployment context only; no memory admission or world grant",
                scope="VM-context evidence; not proof against namespace-invisible provider ancestors")
