"""Pure injected observations; no local proc/resource/affinity probe."""
from contextlib import nullcontext
import hashlib
import io
import json
from pathlib import Path

import pytest
from scripts import wealth_floor_deployment_diagnostic as D


def fixture(*, environment=None, comm="systemd\n", own="cgroup:[1]", init="cgroup:[1]", changed=None, error=None):
    limits=D.Limits(clock=lambda:0.0);counts={}
    rows={"/proc/1/comm":comm,"/proc/self/ns/cgroup":own,"/proc/1/ns/cgroup":init}
    def read(path):
        counts[path]=counts.get(path,0)+1
        if error and path==error[0] and counts[path]==error[1]:raise OSError(error[2],"secret-error-text")
        value=changed[1] if changed and path==changed[0] and counts[path]>1 else rows[path]
        if path=="/proc/1/comm":limits.charge(len(value.encode('utf-8')))
        return value
    memory={"/proc/self/cgroup":"0::/\n","/proc/self/mountinfo":"41 20 0:30 / /sys/fs/cgroup rw - cgroup2 cgroup rw\n",
            "/proc/meminfo":"MemAvailable: 3000 kB\n","/sys/fs/cgroup/cgroup.controllers":"cpu memory\n",
            "/sys/fs/cgroup/cgroup.subtree_control":"memory\n","/sys/fs/cgroup/memory.max":"max\n",
            "/sys/fs/cgroup/memory.current":"100\n"}
    def meta(path):
        if path not in memory:raise FileNotFoundError(path)
        limits.charge(len(memory[path]));return memory[path]
    result=D.collect(environ={"GITHUB_ACTIONS":"true","RUNNER_ENVIRONMENT":"github-hosted"} if environment is None else environment,
        limits=limits,read_comm=read,read_link=read,memory_reader=meta)
    return result,limits


def test_default_is_inert_without_environment_or_proc_reads(monkeypatch,capsys):
    def forbidden(*a,**k):pytest.fail("inert diagnostic observed host")
    monkeypatch.setattr(D,"collect",forbidden);monkeypatch.setattr(D,"pin_one_cpu",forbidden)
    assert D.main([])==0
    assert json.loads(capsys.readouterr().out)==dict(status="inactive",diagnostic_only=True)


@pytest.mark.parametrize("kwargs,predicate", [
    ({"environment":{}},"runner_context"),({"error":("/proc/1/comm",1,13)},"initial_read_unavailable"),
    ({"comm":"init\n"},"pid1_systemd"),({"own":"net:[1]"},"namespace_format"),
    ({"init":"cgroup:[2]"},"namespace_match"),({"error":("/proc/self/ns/cgroup",2,5)},"reread_unavailable"),
    ({"changed":("/proc/1/comm","tini\n")},"evidence_stability"),
    ({"changed":("/proc/self/ns/cgroup","x"*129)},"evidence_stability"),({},"none_observed")])
def test_each_frozen_predicate_has_a_fixed_enum(kwargs,predicate):
    result,_=fixture(**kwargs)
    assert result["first_failed_predicate"]==predicate
    assert result["admission_granted"] is False and result["candidate_worlds_enabled"] is False


@pytest.mark.parametrize("comm,wanted",[("systemd\n","systemd"),("init\n","init"),("tini\n","tini"),
    ("bash\n","bash"),("python\n","python"),("python3.13\n","python"),("secret-name\n","other")])
def test_pid1_is_classified_without_arbitrary_text(comm,wanted):
    result,_=fixture(comm=comm)
    assert result["pid1_class"]==wanted
    assert b"secret-name" not in D.encoded(result)


@pytest.mark.parametrize("own",["x"*129,"cgroup:[0]","cgroup:[1]\n","secret-link", "net:[1]"])
def test_bad_namespace_is_never_dumped(own):
    result,_=fixture(own=own)
    assert not result["namespaces"]["self_format_valid"]
    assert result["namespaces"]["equal"] is None
    assert result["first_failed_predicate"]=="namespace_format"
    assert own.encode() not in D.encoded(result)


def test_errno_and_flags_are_sanitized():
    result,_=fixture(environment={"GITHUB_ACTIONS":"secret-token","RUNNER_ENVIRONMENT":"secret-host"},error=("/proc/1/ns/cgroup",1,13))
    assert result["flags"]==dict(github_actions="other",runner_environment="other")
    assert result["fields"]["pid1_namespace"]["initial_error"]==dict(category="os_error",errno=13)
    raw=D.encoded(result)
    assert b"secret" not in raw and len(raw)<=D.MAX_METADATA


def test_real_shared_memory_algorithm_runs_only_over_injected_metadata():
    result,_=fixture()
    memory=result["memory"]
    assert memory["status"]=="observed_only" and memory["available_bytes"]==3000*1024
    assert memory["visible_ancestor_count"]==1 and "no admission grant" in memory["scope"]
    assert b"/sys/fs/cgroup" not in D.encoded(result)


def test_every_file_read_is_bounded_and_aggregate_metadata_cannot_grow():
    sizes=[]
    class Stream(io.BytesIO):
        def read(self,size=-1):sizes.append(size);return super().read(size)
    limits=D.Limits(clock=lambda:0.0)
    with pytest.raises(D.DiagnosticRefused,match="metadata_bound"):
        D.bounded_file("fixture",limits,opener=lambda *a:Stream(b"a"*(D.MAX_METADATA+1)))
    assert limits.bytes==D.MAX_METADATA and max(sizes)<=129 and min(sizes)>0


def test_pid1_sentinel_refuses_shape_without_dumping_text():
    limits=D.Limits(clock=lambda:0.0)
    text=D.bounded_file("fixture",limits,once=True,opener=lambda *a:io.BytesIO(b"x"*200))
    assert len(text)==129 and limits.bytes==129 and D.comm_class(text)=="other"


def test_memory_budget_failure_keeps_deployment_facts_without_grant():
    limits=D.Limits(clock=lambda:0.0)
    def metadata(_path):raise D.DiagnosticRefused("metadata_bound")
    result=D.collect(environ={"GITHUB_ACTIONS":"true","RUNNER_ENVIRONMENT":"github-hosted"},limits=limits,
        read_comm=lambda path:"systemd\n",read_link=lambda path:"cgroup:[1]",memory_reader=metadata)
    assert result["first_failed_predicate"]=="none_observed"
    assert result["memory"]==dict(status="unavailable",category="metadata_bound",errno=None)
    assert not result["admission_granted"]


def test_deadline_refuses_and_one_cpu_policy_is_injected():
    clock=[0.0];limits=D.Limits(clock=lambda:clock[0]);clock[0]=31
    with pytest.raises(D.DiagnosticRefused,match="deadline"):limits.check()
    current=[{2,4}];calls=[]
    def set_cpu(pid,cpus):calls.append((pid,cpus));current[0]=cpus
    result=D.pin_one_cpu(get_affinity=lambda pid:current[0],set_affinity=set_cpu)
    assert calls==[(0,{2})] and result["process_affinity_count"]==1


def test_explicit_cli_uses_injected_observer_only_and_exclusive_output(monkeypatch,tmp_path,capsys):
    monkeypatch.setattr(D,"hard_deadline",lambda:nullcontext())
    monkeypatch.setattr(D,"pin_one_cpu",lambda:dict(process_affinity_count=1))
    monkeypatch.setattr(D,"collect",lambda **k:dict(status="observation_only",admission_granted=False))
    output=tmp_path/"result.json"
    assert D.main(["--observe","--output",str(output)])==0
    assert json.loads(output.read_text())["admission_granted"] is False
    assert D.main(["--observe","--output",str(output)])==1
    assert "Traceback" not in capsys.readouterr().err


def test_helpers_and_dormant_known_active_body_are_unchanged(tmp_path):
    root=Path(__file__).parents[1]
    assert hashlib.sha256((root/"scripts/wealth_floor_build_resources.py").read_bytes()).hexdigest()==D.RESOURCE_SOURCE
    assert hashlib.sha256((root/"scripts/wealth_floor_hosted_deployment.py").read_bytes()).hexdigest()==D.DEPLOYMENT_SOURCE
    raw=(root/"docs/experiments/wealth-floor-deployment-diagnostic.yml.inactive").read_bytes()
    active=root/D.WORKFLOW_PATH
    if active.exists():assert active.read_bytes()==raw
    known=tmp_path/"known-active.yml";known.write_bytes(raw)
    assert known.read_bytes()==raw
    text=raw.decode()
    assert "branches: ["+D.ACTIVATION_BRANCH+"]" in text and "paths: ["+D.WORKFLOW_PATH+"]" in text
    assert "GH_TOKEN" not in text and "timeout-minutes: 5" in text
