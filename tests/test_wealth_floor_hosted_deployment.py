"""Fixture-only deployment precondition; never probes the actual host."""
import importlib.util
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "wealth_floor_hosted_deployment", Path(__file__).parents[1] / "scripts/wealth_floor_hosted_deployment.py")
deployment = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(deployment)


def observe(*, environment=None, comm="systemd\n", own="cgroup:[4026531835]", init="cgroup:[4026531835]",
            changing=None):
    counts = {}
    values = {"/proc/1/comm": comm, "/proc/self/ns/cgroup": own, "/proc/1/ns/cgroup": init}
    def read(path):
        counts[path] = counts.get(path, 0) + 1
        if path == changing and counts[path] > 1:
            return "changed"
        value = values[path]
        if isinstance(value, Exception):
            raise value
        return value
    return deployment.hosted_vm_precondition(
        environ={"GITHUB_ACTIONS": "true", "RUNNER_ENVIRONMENT": "github-hosted"} if environment is None else environment,
        read_text=read, read_link=read)


def test_matching_hosted_vm_namespace_has_explicit_visibility_limit():
    result = observe()
    assert result["runner_environment"] == "github-hosted"
    assert result["self_cgroup_namespace"] == result["pid1_cgroup_namespace"]
    assert "not proof" in result["scope"] and "no configured job container" in result["required_job_context"]


@pytest.mark.parametrize("environment", [{}, {"GITHUB_ACTIONS": "true"},
    {"GITHUB_ACTIONS": "true", "RUNNER_ENVIRONMENT": "self-hosted"},
    {"GITHUB_ACTIONS": "false", "RUNNER_ENVIRONMENT": "github-hosted"}])
def test_wrong_runner_context_refuses_before_proc_read(environment):
    def forbidden(_path): pytest.fail("wrong deployment must refuse before proc reads")
    with pytest.raises(deployment.DeploymentRefused):
        deployment.hosted_vm_precondition(environ=environment, read_text=forbidden, read_link=forbidden)


@pytest.mark.parametrize("kwargs", [
    {"comm": "tini\n"}, {"comm": "x" * 129}, {"comm": "systém-d\n"},
    {"own": "cgroup:[12]", "init": "cgroup:[13]"}, {"own": "cgroup:[0]"},
    {"own": "net:[12]"}, {"own": "cgroup:[1]\n"}, {"init": "x" * 129},
    {"comm": FileNotFoundError()}, {"init": PermissionError()},
    {"changing": "/proc/1/comm"}, {"changing": "/proc/self/ns/cgroup"}, {"changing": "/proc/1/ns/cgroup"},
])
def test_missing_unsupported_or_mutating_namespace_refuses(kwargs):
    with pytest.raises(deployment.DeploymentRefused): observe(**kwargs)
