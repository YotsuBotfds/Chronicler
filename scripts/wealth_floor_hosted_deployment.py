"""Small deployment precondition for the sealed direct hosted-VM jobs.

No environment or proc information is read until the explicit function call.
This is VM-context evidence, not an attestation about invisible provider layers.
"""
from __future__ import annotations

import os
from pathlib import Path
import re


class DeploymentRefused(ValueError):
    pass


def _require(condition, message):
    if not condition:
        raise DeploymentRefused(message)


def _read_text(path):
    with Path(path).open("r", encoding="ascii") as stream:
        return stream.read(129)


def hosted_vm_precondition(*, environ=None, read_text=None, read_link=None):
    env = os.environ if environ is None else environ
    read_text = _read_text if read_text is None else read_text
    read_link = os.readlink if read_link is None else read_link
    _require(env.get("GITHUB_ACTIONS") == "true" and env.get("RUNNER_ENVIRONMENT") == "github-hosted",
             "direct hosted GitHub runner required")
    try:
        comm = read_text("/proc/1/comm")
        own = read_link("/proc/self/ns/cgroup")
        init = read_link("/proc/1/ns/cgroup")
        _require(type(comm) is str and comm.isascii() and len(comm) <= 128 and comm.strip() == "systemd",
                 "hosted VM PID1 systemd evidence required")
        _require(all(type(value) is str and value.isascii() and len(value) <= 128
                     and re.fullmatch(r"cgroup:\[[1-9][0-9]{0,19}\]", value) for value in (own, init)),
                 "cgroup namespace identity unsupported")
        _require(own == init, "process cgroup namespace differs from VM PID1")
        _require(read_text("/proc/1/comm") == comm
                 and read_link("/proc/self/ns/cgroup") == own
                 and read_link("/proc/1/ns/cgroup") == init,
                 "hosted VM namespace evidence changed during observation")
    except (OSError, UnicodeError) as exc:
        raise DeploymentRefused("hosted VM deployment evidence unavailable") from exc
    return dict(github_actions="true", runner_environment="github-hosted", pid1_comm="systemd",
                self_cgroup_namespace=own, pid1_cgroup_namespace=init,
                required_job_context="Sealed direct ubuntu-24.04 job, with no configured job container",
                scope="VM-context evidence; not proof against namespace-invisible provider ancestors")
