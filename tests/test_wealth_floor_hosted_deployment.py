"""Fixture-only deployment precondition; never probes the actual host."""
import errno
import importlib.util
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "wealth_floor_hosted_deployment", Path(__file__).parents[1] / "scripts/wealth_floor_hosted_deployment.py")
deployment = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(deployment)


def observe(*, environment=None, comm="systemd\n", own="cgroup:[4026531835]", init="cgroup:[4026531835]",
            reread=None):
    counts = {}
    values = {"/proc/1/comm": comm, "/proc/self/ns/cgroup": own, "/proc/1/ns/cgroup": init}
    def read(path):
        counts[path] = counts.get(path, 0) + 1
        value = (reread or {}).get(path, values[path]) if counts[path] > 1 else values[path]
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
    assert result["namespace_equal"] is True and result["namespace_equality_verified"] is True
    assert result["namespace_equality_status"] == "verified_equal"
    assert result["observations"]["pid1_cgroup_namespace_errno"] == [None, None]
    assert "not proof" in result["scope"] and "no configured job container" in result["required_job_context"]


def test_exact_repeated_eacces_retains_unknown_equality_and_explicit_scope():
    result = observe(init=PermissionError(errno.EACCES, "private error text never recorded"))
    assert result["precondition_version"] == 2
    assert result["pid1_cgroup_namespace"] is None and result["pid1_cgroup_namespace_errno"] == 13
    assert result["namespace_equal"] is None and result["namespace_equality_verified"] is False
    assert result["namespace_equality_status"] == "unverified_permission_denied"
    assert result["observations"] == dict(pid1_comm=["systemd\n", "systemd\n"],
        self_cgroup_namespace=["cgroup:[4026531835]", "cgroup:[4026531835]"],
        pid1_cgroup_namespace=[None, None], pid1_cgroup_namespace_errno=[13, 13])
    assert "namespace equality unverified" in result["evidence_scope"]
    assert "no memory admission or world grant" in result["admission_scope"]
    assert "not proof" in result["scope"] and "private" not in repr(result)


@pytest.mark.parametrize("environment", [{}, {"GITHUB_ACTIONS": "true"},
    {"GITHUB_ACTIONS": "true", "RUNNER_ENVIRONMENT": "self-hosted"},
    {"GITHUB_ACTIONS": "false", "RUNNER_ENVIRONMENT": "github-hosted"},
    {"GITHUB_ACTIONS": True, "RUNNER_ENVIRONMENT": "github-hosted"}])
def test_wrong_runner_context_refuses_before_proc_read(environment):
    def forbidden(_path): pytest.fail("wrong deployment must refuse before proc reads")
    with pytest.raises(deployment.DeploymentRefused) as caught:
        deployment.hosted_vm_precondition(environ=environment, read_text=forbidden, read_link=forbidden)
    assert caught.value.code == "runner_flags"


@pytest.mark.parametrize("kwargs, code", [
    ({"comm": "tini\n"}, "pid1_comm_invalid"),
    ({"comm": "x" * 129}, "pid1_comm_invalid"),
    ({"comm": "systém-d\n"}, "pid1_comm_invalid"),
    ({"own": "cgroup:[12]", "init": "cgroup:[13]"}, "namespace_mismatch"),
    ({"own": "cgroup:[0]"}, "self_namespace_invalid"),
    ({"own": "net:[12]"}, "self_namespace_invalid"),
    ({"own": "cgroup:[1]\n"}, "self_namespace_invalid"),
    ({"init": "x" * 129}, "pid1_namespace_invalid"),
    ({"comm": FileNotFoundError()}, "pid1_comm_unavailable"),
    ({"init": PermissionError()}, "pid1_namespace_unavailable"),
    ({"reread": {"/proc/1/comm": " systemd\n"}}, "pid1_comm_changed"),
    ({"reread": {"/proc/self/ns/cgroup": "cgroup:[13]"}}, "self_namespace_changed"),
    ({"reread": {"/proc/1/ns/cgroup": "cgroup:[13]"}}, "pid1_namespace_changed"),
])
def test_missing_unsupported_or_mutating_namespace_refuses_with_registered_code(kwargs, code):
    with pytest.raises(deployment.DeploymentRefused) as caught: observe(**kwargs)
    assert caught.value.code == code and str(caught.value) == code
    assert code in deployment.REFUSAL_CODES


@pytest.mark.parametrize("error", [PermissionError(), PermissionError(errno.EPERM, "private"),
    FileNotFoundError(errno.ENOENT, "private"), OSError(errno.EIO, "private"),
    UnicodeError("private")])
@pytest.mark.parametrize("second", [False, True])
def test_only_actual_errno13_is_accepted_on_each_pid1_read(error, second):
    kwargs = dict(init=PermissionError(errno.EACCES, "private"), reread={"/proc/1/ns/cgroup": error}) if second else dict(init=error)
    with pytest.raises(deployment.DeploymentRefused) as caught: observe(**kwargs)
    assert caught.value.code == "pid1_namespace_unavailable"
    assert "private" not in str(caught.value)


@pytest.mark.parametrize("kwargs, code", [
    ({"reread": {"/proc/1/ns/cgroup": "cgroup:[4026531835]"}}, "pid1_namespace_changed"),
    ({"reread": {"/proc/1/ns/cgroup": "invalid"}}, "pid1_namespace_invalid"),
    ({"comm": "tini\n"}, "pid1_comm_invalid"),
    ({"own": "invalid"}, "self_namespace_invalid"),
    ({"own": PermissionError(errno.EACCES, "private")}, "self_namespace_unavailable"),
    ({"reread": {"/proc/1/comm": FileNotFoundError()}}, "pid1_comm_unavailable"),
    ({"reread": {"/proc/1/comm": " systemd\n"}}, "pid1_comm_changed"),
    ({"reread": {"/proc/self/ns/cgroup": "cgroup:[13]"}}, "self_namespace_changed"),
    ({"reread": {"/proc/self/ns/cgroup": "invalid"}}, "self_namespace_invalid"),
    ({"reread": {"/proc/self/ns/cgroup": OSError(errno.EIO, "private")}}, "self_namespace_unavailable"),
])
def test_denied_pid1_namespace_never_bypasses_other_evidence(kwargs, code):
    with pytest.raises(deployment.DeploymentRefused) as caught:
        observe(init=PermissionError(errno.EACCES, "private"), **kwargs)
    assert caught.value.code == code


def test_readable_initial_namespace_cannot_become_denied():
    with pytest.raises(deployment.DeploymentRefused) as caught:
        observe(reread={"/proc/1/ns/cgroup": PermissionError(errno.EACCES, "private")})
    assert caught.value.code == "pid1_namespace_changed"


def test_runner_flags_must_remain_registered_through_the_observation():
    environment = {"GITHUB_ACTIONS": "true", "RUNNER_ENVIRONMENT": "github-hosted"}
    def comm(_path):
        environment["RUNNER_ENVIRONMENT"] = "self-hosted"
        return "systemd\n"
    with pytest.raises(deployment.DeploymentRefused) as caught:
        deployment.hosted_vm_precondition(environ=environment, read_text=comm, read_link=lambda _path: "cgroup:[12]")
    assert caught.value.code == "runner_flags"


def test_refusal_code_registry_does_not_accept_arbitrary_exception_text():
    assert type(deployment.REFUSAL_CODES) is frozenset
    with pytest.raises(ValueError, match="unregistered deployment refusal code"):
        deployment.DeploymentRefused("private dynamic exception message")
