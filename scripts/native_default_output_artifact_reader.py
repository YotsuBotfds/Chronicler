#!/usr/bin/env python3
"""Closed read-only audit of the completed C76/95 exported-output artifact."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.abc
import importlib.metadata
import importlib.util
import io
import json
import math
import os
from pathlib import Path, PurePosixPath
import platform
import re
import shutil
import stat
import subprocess
import sys
import time
from types import ModuleType, SimpleNamespace
import zipfile

SCRIPT = Path(__file__).resolve()
ROOT = SCRIPT.parents[1]
GIB = 1024**3
SECONDS, CLEANUP_RESERVE = 600, 20
ACTIVE_BRANCH = "lead/cloud-native-default-output-artifact-audit-v2-20261029"
WORKFLOW_PATH = ".github/workflows/native-default-output-artifact-audit-v2.yml"
TEMPLATE_PATH = "docs/experiments/native-default-output-artifact-reader-v2-workflow.yml"
WORKFLOW_SHA = "8593cb38b3d990b70057b54c59afa4c9fc950d0c36d319d67112ab4bb2320826"
JOB_KEY = "native-default-output-artifact-audit-v2"
REPO = "YotsuBotfds/Chronicler"
CONTROL = "74b2904dfc4acceb6c5c03a57aa8c2b6406ce4a6"
RUN, JOB, ARTIFACT, ARCHIVE_BYTES = 40834257046, 123315234223, 12880510564, 75556121
ARCHIVE_SHA = "4afbb62db5d63165a42c5aa11e5740a665a514016eb9a5a339bb97ad48553fc3"
EXPIRY = "2026-11-28T07:19:53Z"
PRODUCER_SHA = "fe7129a6c3d9386cc5aed7e4a6430509d552e4e87101510b02ddb016ef7f38d1"
HELPER_SHA = "0d3a2c5db023a47a82307d3a9b789eebd979915e52be66e7208f0c93a94540f5"
KERNELS = {
    "completed_export_study_reader.py": (27953, "ab0168bed9d97f4b9d96a7eec5d792e934214bf50858ce69644267039b19bc31"),
    "default_output_identity_reader.py": (27754, "2bacde640402ce64ac52e284f3eb63d3462e1b00ec299ae8a21e1b6f065c649c"),
    "export_study_git.py": (20231, "80434ebb0d455ce3f2d329efd5878c2ae28dd9fca652581e9210d242ae2c53fc"),
}
NORMALIZATION = "metadata.generated_at only; original .log/run_manifest exclusions"
PUBLICATION_LIMIT = 32 * 1024**2


class NativeGuard(importlib.abc.MetaPathFinder):
    def __init__(self):self.attempts=[]
    def find_spec(self,fullname,path=None,target=None):
        if fullname=="chronicler_agents" or fullname.startswith("chronicler_agents."):
            self.attempts.append(fullname)
            raise ImportError("native runtime unavailable in read-only inspector")


class Refusal(RuntimeError):
    pass


def require(value, message):
    if not value:
        raise Refusal(message)


def exact(value, expected):
    return type(value) is type(expected) and value == expected


def error_record(error,A,C,stage):
    known=(Refusal,A.Refusal)
    if C is not None:known+=(C.core.Refusal,C.git_source.SnapshotError)
    detail=str(error) if isinstance(error,known) else type(error).__name__
    detail=re.sub(r"https?://\S+","[URL]",detail)
    detail=detail.encode("utf-8")[:2048].decode("utf-8","ignore")
    return {"error":type(error).__name__,"error_stage":stage,"error_message":detail}


def pin(raw):
    return {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def bounded(path, limit=32*1024**2):
    require(not path.is_symlink() and path.is_file(), "regular input required")
    with path.open("rb") as stream:
        raw = stream.read(limit+1)
    require(len(raw) <= limit, "input byte bound exceeded")
    return raw


def write(path, value):
    temporary = path.with_name(path.name+".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
    os.replace(temporary, path)


def compile_module(raw, path, name):
    module = ModuleType(name)
    module.__file__ = str(path)
    sys.modules[name] = module
    exec(compile(raw, str(path), "exec"), module.__dict__)
    return module


def producer():
    path = ROOT/"scripts/native_default_output_identity_qualification.py"
    raw = bounded(path, 64*1024)
    require(pin(raw)["sha256"] == PRODUCER_SHA
        and pin(bounded(path.with_name("arc_output_identity_qualification.py"), 64*1024))["sha256"] == HELPER_SHA,
        "qualified producer utility bytes differ")
    return compile_module(raw, path, "_closed_native_artifact_producer")


def kernel_bytes():
    result = {}
    for name, (size, digest) in KERNELS.items():
        raw = bounded(ROOT/"scripts"/name, size)
        require(pin(raw) == {"bytes": size, "sha256": digest}, "qualified kernel bytes differ")
        result[name] = raw
    return result


def load_kernels(directory, *, create=False):
    raw = kernel_bytes()  # Authenticate ALL three before executing any one.
    if create:
        require(shutil.disk_usage(directory.parent).free >= 3*GIB+sum(map(len, raw.values()))+16*1024**2,
                "kernel-copy reserve refused")
        directory.mkdir(mode=0o700)
        for name, value in raw.items():
            with (directory/name).open("xb") as stream: stream.write(value)
            (directory/name).chmod(0o444)
        directory.chmod(0o555)
    require(not directory.is_symlink() and stat.S_IMODE(directory.stat().st_mode) == 0o555,
            "private kernel directory differs")
    require({p.name for p in directory.iterdir()} == set(raw), "unexpected private kernel/cache entry")
    for name, value in raw.items():
        require(bounded(directory/name, len(value)) == value
            and stat.S_IMODE((directory/name).stat().st_mode) == 0o444, "private kernel changed")
    # Internal source loaders reopen only this fresh immutable no-bytecode view.
    result = compile_module(raw["completed_export_study_reader.py"],
        directory/"completed_export_study_reader.py", "_closed_native_artifact_kernels")
    require(Path(result.core.__file__).parent == directory and Path(result.git_source.__file__).parent == directory,
            "kernel imports escaped authenticated view")
    return result


def registration(env):
    require(env.get("GITHUB_ACTIONS") == "true" and env.get("GITHUB_REPOSITORY") == REPO
        and env.get("GITHUB_EVENT_NAME") == "push" and env.get("GITHUB_REF") == "refs/heads/"+ACTIVE_BRANCH
        and env.get("GITHUB_WORKFLOW_REF") == REPO+"/"+WORKFLOW_PATH+"@refs/heads/"+ACTIVE_BRANCH
        and env.get("GITHUB_JOB") == JOB_KEY and env.get("GITHUB_RUN_ATTEMPT") == "1"
        and type(env.get("GITHUB_RUN_ID")) is str and type(env.get("GITHUB_SHA")) is str
        and re.fullmatch("[1-9][0-9]*", env.get("GITHUB_RUN_ID", ""))
        and re.fullmatch("[0-9a-f]{40}", env.get("GITHUB_SHA", "")), "closed first-attempt audit producer required")
    return {key: env[key] for key in ("GITHUB_SHA", "GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT", "GITHUB_JOB")}


def validate_metadata(value, now=None):
    require(type(value) is dict and set(value) == {"run", "jobs", "artifacts"}, "official metadata role set differs")
    run, jobs, artifacts = (value[k] for k in ("run", "jobs", "artifacts"))
    require(exact(run.get("id"), RUN) and exact(run.get("run_attempt"), 1) and run.get("head_sha") == CONTROL
        and run.get("head_branch") == "lead/cloud-native-default-output-identity-20261029"
        and run.get("event") == "push" and run.get("path") == ".github/workflows/native-default-output-identity.yml"
        and run.get("status") == "completed" and run.get("conclusion") == "success"
        and exact(run.get("repository", {}).get("id"), 1187468861)
        and run["repository"].get("full_name") == REPO, "completed parity run differs")
    require(exact(jobs.get("total_count"), 1) and type(jobs.get("jobs")) is list and len(jobs["jobs"]) == 1,
            "complete parity job set differs")
    job = jobs["jobs"][0]
    require(exact(job.get("id"), JOB) and exact(job.get("run_id"), RUN) and exact(job.get("run_attempt"), 1)
        and job.get("head_sha") == CONTROL and job.get("name") == "native-default-output-identity"
        and job.get("status") == "completed" and job.get("conclusion") == "success", "completed parity job differs")
    require(type(job.get("steps")) is list and all(type(s) is dict and type(s.get("number")) is int
        and s.get("status") == "completed" and s.get("conclusion") == "success" for s in job["steps"]), "parity steps incomplete")
    steps={s["number"]:s for s in job["steps"]}
    require(len(steps)==len(job["steps"]) and all(steps.get(n,{}).get("name")==name for n,name in {
        7:"Check unchanged original pure contracts",8:"Check new pure adapter contracts",
        10:"Execute only after separate source and activation review",11:"Retain complete positive or negative evidence"}.items()),
        "parity preflight/controller/publication steps differ")
    require(exact(artifacts.get("total_count"), 1) and type(artifacts.get("artifacts")) is list
        and len(artifacts["artifacts"]) == 1, "complete parity artifact set differs")
    artifact = artifacts["artifacts"][0]; origin = artifact.get("workflow_run", {})
    require(exact(artifact.get("id"), ARTIFACT) and artifact.get("name") == f"native-default-output-identity-{RUN}-1"
        and exact(artifact.get("size_in_bytes"), ARCHIVE_BYTES) and artifact.get("digest") == "sha256:"+ARCHIVE_SHA
        and artifact.get("expired") is False and artifact.get("expires_at") == EXPIRY
        and exact(origin.get("id"), RUN) and origin.get("head_sha") == CONTROL
        and exact(origin.get("repository_id"), 1187468861) and exact(origin.get("head_repository_id"), 1187468861),
        "parity artifact content/origin differs")
    require(datetime.fromisoformat(EXPIRY.replace("Z", "+00:00")) > (now or datetime.now(timezone.utc)), "parity artifact expired")
    return {"source": CONTROL, "run": RUN, "job": JOB, "attempt": 1, "artifact": ARTIFACT,
            "bytes": ARCHIVE_BYTES, "sha256": ARCHIVE_SHA, "expiry": EXPIRY}


def validate_result(value, cases, inventory_sha, A):
    require(type(value) is dict and set(value)=={"qualified","status","baseline","candidate","control","producer","cases",
        "normalization","native_sha256_by_arm","wheel_sha256_by_arm","limitations","installer","installed_native_path",
        "installed_native_arm","runtime","package_digests","inventory_sha256","elapsed_wall_seconds"},"actual result schema differs")
    require(value.get("qualified") is True and value.get("status") == "exports_complete_pending_completed_job"
        and value.get("control") == CONTROL and value.get("baseline") == A.SOURCES["baseline"]
        and value.get("candidate") == A.SOURCES["candidate"] and value.get("normalization") == NORMALIZATION
        and value.get("inventory_sha256") == inventory_sha, "actual per-arm result identity differs")
    require(not any(k in value for k in ("error", "final_identity_error", "inventory_error")), "producer retained an error")
    expected_producer = {"control_sha": CONTROL, "run_id": str(RUN), "run_attempt": "1", "job_key": "native-default-output-identity",
        "workflow_ref": REPO+"/.github/workflows/native-default-output-identity.yml@refs/heads/lead/cloud-native-default-output-identity-20261029",
        "event": "push", "branch": "lead/cloud-native-default-output-identity-20261029"}
    require(value.get("producer") == expected_producer and value.get("native_sha256_by_arm") ==
        {arm: w.native_sha256 for arm,w in A.WHEELS.items()} and value.get("wheel_sha256_by_arm") ==
        {arm: w.sha256 for arm,w in A.WHEELS.items()}, "producer/per-arm native maps differ")
    rows = value.get("cases")
    require(type(rows) is list and all(type(r) is dict and set(r)=={"arm","case","status","audit_sha256"} for r in rows)
        and [(r.get("arm"),r.get("case")) for r in rows] ==
        [(arm,case) for arm in ("baseline","candidate") for case in cases], "ordered complete matrix differs")
    require(all(r.get("status") == "complete" and type(r.get("audit_sha256")) is str
        and re.fullmatch("[0-9a-f]{64}",r["audit_sha256"]) for r in rows), "incomplete case/audit")
    require(value.get("installed_native_arm") == "candidate", "last installed arm differs")
    require(type(value["elapsed_wall_seconds"]) in (int,float) and math.isfinite(value["elapsed_wall_seconds"])
        and 0<=value["elapsed_wall_seconds"]<=4800,"original controller elapsed differs")
    return rows


def historical(value):
    require(type(value) is str and value.startswith("/") and "\\" not in value and "\0" not in value
        and PurePosixPath(value).as_posix() == value and all(p not in ("", ".", "..") for p in value.split("/")[1:]),
        "noncanonical historical provenance path")
    return PurePosixPath(value)


def open_archive(C,path):
    require(not path.is_symlink() and stat.S_ISREG(path.stat().st_mode),"original archive must be regular")
    require(C.core.digest(path,ARCHIVE_BYTES)=={"bytes":ARCHIVE_BYTES,"sha256":ARCHIVE_SHA},
            "outer archive differs before ZIP allocation")
    return zipfile.ZipFile(path)


def complete_inventory(C,archive):
    files=C.members(archive)
    inventory_sha=pin(C.read_member(archive,files,"inventory.json"))["sha256"]
    inventory=C.stream_inventory(archive,files,SimpleNamespace(inventory_sha=inventory_sha))
    return files,inventory,inventory_sha


def validate_probe(value, arm, A, package_digest, common_runtime=None):
    source, native, runtime, env = (value[k] for k in ("source","native","runtime","environment"))
    package = historical(source["package_dir"]); source_file = historical(value["source_file"])
    prefix = historical(value["prefix"]); native_file = historical(value["native_file"])
    require(source_file == package/"__init__.py" and package.parts[-3:] == (arm,"src","chronicler")
        and source["git_sha"] == A.SOURCES[arm] and source["package_digest"] == package_digest,
        "own historical source provenance differs")
    require(prefix.name=="native-default-identity-env" and native_file.is_relative_to(prefix) and native_file.name == Path(A.NATIVE_MEMBER).name
        and native.get("status") == "found" and native.get("source") == "imported"
        and native.get("module_file") == value["native_file"] and exact(native.get("bytes"),A.WHEELS[arm].native_size)
        and native.get("sha256") == A.WHEELS[arm].native_sha256 and value["schemas"] == A.SCHEMAS,
        "per-arm imported native descriptor differs")
    require(runtime.get("python") == A.PYTHON and runtime.get("implementation") == "CPython"
        and type(runtime.get("version")) is str and runtime["version"].startswith(A.PYTHON+" ")
        and runtime.get("machine") == "x86_64" and runtime.get("prefix") == str(prefix)
        and type(runtime.get("affinity")) is list and len(runtime["affinity"]) == 1
        and type(runtime["affinity"][0]) is int and runtime["affinity"][0] >= 0
        and value["affinity"] == runtime["affinity"] and exact(runtime.get("cpu_count"),1)
        and exact(runtime.get("process_cpu_count"),1) and exact(runtime.get("optimize"),0)
        and exact(runtime.get("no_user_site"),1) and runtime.get("dont_write_bytecode") is True,
        "original actual runtime policy differs")
    historical(runtime["executable"])
    require(runtime["thread_env"] == {**A.H.CAPS,"PYTHONHASHSEED":"0","OPENBLAS_THREAD_TIMEOUT":"16"}
        and type(runtime["packages"]) is dict and set(runtime["packages"]) == set(A.PACKAGE_NAMES)
        and all(type(v) is str and bool(v) for v in runtime["packages"].values()), "original runtime package/cap graph differs")
    for key in ("python","implementation","platform","machine","cpu_count","process_cpu_count","packages"):
        require(type(env.get(key)) is type(runtime[key]) and env[key] == runtime[key], "duplicated environment/runtime field differs")
    require(env.get("executable") == str(prefix/"bin/python") and exact(env.get("affinity_cpu_count"),1)
        and env.get("thread_env") == {k:v for k,v in runtime["thread_env"].items() if k != "CARGO_BUILD_JOBS"},
        "duplicated environment provenance/caps differ")
    require(common_runtime is None or runtime == common_runtime, "cross-arm/case actual runtime differs")
    return runtime


def verify_inputs(C, A, archive, files, inventory, admission):
    selected = {"old":set(A.OLD_SEALS)|{A.WHEELS["baseline"].member},
        "new":{"ci-native-wheel/manifest.json",A.WHEELS["candidate"].member},"new-preflight":{"native-identity.json"}}
    contents, publications = {}, {}
    require(set(admission) == {"publications","old_role","new_manifest","members","wheel_members"}, "input admission schema differs")
    for role, registered in A.ARTIFACTS.items():
        name = f"inputs/{registered.artifact_id}.zip"
        require(inventory.get(name) == {"bytes":registered.size,"sha256":registered.sha256}, "retained input seal differs")
        raw = C.read_member(archive,files,name)
        require(pin(raw) == inventory[name], "retained input bytes differ")
        contents[role] = A.inspect_zip(io.BytesIO(raw),selected[role])
        rows = admission["publications"][role]
        require(set(rows) == {"before","after"}, "input observation roles differ")
        for stage in ("before","after"):
            observed = rows[stage]["observed"]
            check = A.validate_publication(registered,observed["run"],observed["job"],observed["artifact"],datetime.now(timezone.utc))
            require(rows[stage] == check, "retained input publication graph differs")
        require(rows["before"]["identity"] == rows["after"]["identity"], "input publication changed")
        publications[role] = rows
    expected = {"publications":publications,"old_role":A.validate_old(*contents["old"]),
        "new_manifest":A.validate_new(*contents["new"],*contents["new-preflight"]),
        "members":{role:value[0] for role,value in contents.items()},"wheel_members":{}}
    for arm,w in A.WHEELS.items():
        expected["wheel_members"][arm] = A.validate_wheel(contents[w.artifact][1][w.member],w)
    require(admission == expected, "complete retained input admission graph differs")
    require({n for n in inventory if n.startswith("inputs/")} == {f"inputs/{p.artifact_id}.zip" for p in A.ARTIFACTS.values()},
            "retained input set differs")
    return expected


def verify_native(C,A,archive,files,inventory):
    expected_wheels, expected_native, result = set(),set(),{}
    for arm,w in A.WHEELS.items():
        wheel = f"wheels/{arm}/{A.WHEEL_NAME}"; native = f"native/{arm}/{Path(A.NATIVE_MEMBER).name}"
        expected_wheels.add(wheel);expected_native.add(native)
        require(inventory.get(wheel) == {"bytes":w.size,"sha256":w.sha256}
            and inventory.get(native) == {"bytes":w.native_size,"sha256":w.native_sha256}, "retained arm-native links differ")
        members = A.validate_wheel(C.read_member(archive,files,wheel),w)
        require(members[A.NATIVE_MEMBER] == inventory[native], "actual wheel/copy bytes differ")
        result[arm] = {"wheel":inventory[wheel],"native":inventory[native]}
    require({n for n in inventory if n.startswith("wheels/")} == expected_wheels
        and {n for n in inventory if n.startswith("native/")} == expected_native, "two-arm wheel/native set differs")
    return result


def verify_sources(C,A,metadata,repo,output):
    freeze = C.core.read_json(metadata/"freeze.json"); before = freeze["sources"]
    require(before == C.core.read_json(metadata/"sources-after.json") and set(before) == {"baseline","candidate","control"},
            "producer before/after source roles differ")
    verified = {}
    for role,sha in {**A.SOURCES,"control":CONTROL}.items():
        require(before[role]["sha"] == sha,"producer source role differs")
        verified[role] = C.git_source.verify_snapshot(repo,before[role])
        require(verified[role]["crate_tree"] == (A.CRATES[role] if role in A.CRATES else A.CRATES["baseline"]),
                "per-role crate tree differs")
    require(freeze.get("helper_sha256") == HELPER_SHA and freeze.get("adapter_sha256") == PRODUCER_SHA,
            "new producer/helper freeze differs")
    for path,sha in (("scripts/arc_output_identity_qualification.py",HELPER_SHA),
                     ("scripts/native_default_output_identity_qualification.py",PRODUCER_SHA)):
        require(verified["control"]["files"][path]["sha256"] == sha,"frozen producer code differs")
    require(freeze["matrix"] == json.loads(json.dumps(A.H.CASES)) and freeze["thread_caps"] == A.H.CAPS
        and type(freeze["affinity"]) is list and len(freeze["affinity"]) == 1
        and type(freeze["affinity"][0]) is int,"producer matrix/caps/affinity differs")
    for path in ("uv.lock","pyproject.toml","scripts/turn_speed_identity.py","scripts/cities_identity.py","src/chronicler/bundle_codec.py"):
        require(verified["baseline"]["files"][path]["sha256"] == verified["candidate"]["files"][path]["sha256"],
                "frozen shared comparison input differs")
    selected = [n for n in verified["candidate"]["files"] if n.startswith("src/chronicler/") and n.endswith(".py")]
    selected += ["scripts/turn_speed_identity.py","scripts/cities_identity.py"]
    C.admission(output,sum(verified["candidate"]["files"][n]["bytes"] for n in selected))
    view = output/"derived-candidate"
    view_map = C.git_source.materialize_python_view(repo,A.SOURCES["candidate"],view,
        ["scripts/turn_speed_identity.py","scripts/cities_identity.py"])
    baseline = output/"baseline-driver.py"
    C.admission(output,verified["baseline"]["files"]["scripts/turn_speed_identity.py"]["bytes"])
    C.write_git_file(repo,A.SOURCES["baseline"],"scripts/turn_speed_identity.py",baseline,
        verified["baseline"]["files"]["scripts/turn_speed_identity.py"])
    A.H.require_matrix(baseline);A.H.require_matrix(view/"scripts/turn_speed_identity.py")
    return freeze,verified,view,view_map


def verify_probes(C,A,metadata,inventory,result,verified,freeze):
    expected, runtime, identities = set(),None,{}
    for arm in A.SOURCES:
        digest = C.git_source.package_digest(verified[arm])
        require(result["package_digests"][arm] == digest,"actual package digest differs from full Git snapshot")
        for case in A.H.CASES:
            pair = []
            for stage in ("before","after"):
                name = f"probes/{arm}-{case}-{stage}.json";expected.add(name)
                row = C.core.read_json(metadata/name)
                runtime = validate_probe(row,arm,A,digest,runtime)
                require(row["affinity"] == freeze["affinity"],"probe/freeze affinity differs")
                pair.append(row)
            require(pair[0] == pair[1],"before/after probe changed")
            name=f"probes/{arm}-{case}-which.txt";expected.add(name)
            which="chronicler "+pair[0]["source_file"]+"\nnative "+pair[0]["native_file"]+" "+A.WHEELS[arm].native_sha256+"\n"
            require(bounded(metadata/name).decode() == which,"retained driver provenance differs")
            identities[arm]=pair[0]
    require({n for n in inventory if n.startswith("probes/")} == expected,"complete probe set differs")
    require(result["runtime"] == runtime and result["installed_native_path"] == identities["candidate"]["native_file"],
            "result runtime/last-native graph differs")
    roots={arm:historical(v["source"]["package_dir"]).parents[1] for arm,v in identities.items()}
    require(roots["baseline"].parent == roots["candidate"].parent,"historical source workspace differs")
    return runtime,identities


def verify_installer(C,A,metadata,result,runtime):
    value=C.core.read_json(metadata/"environment-preparation.json")
    require(value == result["installer"] and set(value) == {"uv","version","environment","bootstrap_python","bootstrap_version"},
            "installer/result graph differs")
    uv=value["uv"];historical(uv["path"]);bootstrap=historical(value["bootstrap_python"])
    require(set(uv) == {"path","bytes","sha256"} and type(uv["bytes"]) is int and uv["bytes"]>0
        and re.fullmatch("[0-9a-f]{64}",uv["sha256"]) and re.fullmatch(r"uv 0\.13\.6(?: \([^\r\n]*\))?",value["version"]),
        "observed installer descriptor differs")
    require(value["environment"] == {"python":A.PYTHON,"prefix":runtime["prefix"],"project_or_native_installed":False}
        and value["bootstrap_version"] == runtime["version"] and historical(runtime["executable"]).parent==bootstrap.parent
        and bootstrap.name in {"python","python3","python3.13"}
        and historical(runtime["executable"]).name in {"python","python3","python3.13"},"fresh prefix/bootstrap observation differs")
    require(C.core.strict_json(bounded(metadata/"logs/fresh-environment-probe.log",4096)) == value["environment"]
        and bounded(metadata/"logs/uv-version.log",4096).decode().strip() == value["version"],"installer logs differ")
    return value


def compare_supervised(C,A,scratch,view,counts,root,case,deadline,supervisors):
    require(set(counts) == {case} and counts[case]>0,"empty or different comparison")
    env={k:os.environ[k] for k in ("PATH","SYSTEMROOT","LANG","LC_ALL","LD_LIBRARY_PATH") if k in os.environ}
    env.update(A.H.CAPS,PYTHONPATH=str(view/"src"),PYTHONDONTWRITEBYTECODE="1",PYTHONNOUSERSITE="1",PYTHONHASHSEED="0",PYTHONOPTIMIZE="0")
    command=[sys.executable,str(view/"scripts/turn_speed_identity.py"),"compare",str(scratch/"raw/baseline"),str(scratch/"raw/candidate")]
    label=case+"-compare";log=root/"logs"/(label+".log")
    require(not log.exists() and not log.is_symlink(),"comparison log already exists")
    supervisor=A.H.Supervisor(root,min(deadline-CLEANUP_RESERVE,time.monotonic()+180))
    supervisors.append(supervisor)
    supervisor.command(label,command,env,root)
    require(supervisor.cleanup_complete,"comparator writers not quiescent")
    text=bounded(log,C.core.COMPARE_LIMIT).decode()
    return {"command":command,**C.core.parse_comparison(text,counts)}


def retire_case(C,scratch,expected,marker):
    require(C.core.read_json(scratch/".derived-reader-scratch.json") == marker,"scratch ownership marker differs")
    require({n:r for n,r in C.core.payload_inventory(scratch).items() if n!=".derived-reader-scratch.json"} == expected,
            "copied case changed before retirement")
    shutil.rmtree(scratch)


def verify_baseline_driver(C,root,descriptor):
    observed=C.core.digest(root/"baseline-driver.py",descriptor["bytes"])
    require(observed=={key:descriptor[key] for key in ("bytes","sha256")},"derived baseline driver changed")
    return observed


def inspect(C,A,context,root,report,supervisors):
    deadline=context["deadline"]
    require(platform.python_version()==A.PYTHON and platform.python_implementation()=="CPython" and platform.machine()=="x86_64"
        and sys.flags.optimize == 0 and sys.flags.no_user_site == 1 and sys.dont_write_bytecode
        and Path(sys.prefix).resolve() == Path(context["prefix"]) and len(os.sched_getaffinity(0)) == 1,
        "actual reader interpreter/prefix/affinity differs")
    require(importlib.util.find_spec("chronicler_agents") is None and importlib.util.find_spec("chronicler") is None,
            "fresh reader has installed project/native package")
    for name in ("chronicler-agents","chronicler"):
        try: importlib.metadata.distribution(name)
        except importlib.metadata.PackageNotFoundError: pass
        else: raise Refusal("fresh reader has installed project/native distribution")
    require(all(os.environ.get(k)==v for k,v in A.H.CAPS.items()),"actual reader caps differ")
    native_guard=NativeGuard();sys.meta_path.insert(0,native_guard)
    archive_path=root/"inputs/original.zip"; metadata=C.core.read_json(root/"metadata-after.json")
    validate_metadata(metadata)
    initial_stat=archive_path.stat()
    with open_archive(C,archive_path) as archive:
        report["phase"]="inventory";files,inventory,inventory_sha=complete_inventory(C,archive)
        write(root/"verified-payload.json",inventory)
        names=[n for n in files if n in {"inventory.json","result.json","freeze.json","sources-after.json","input-admission.json","environment-preparation.json",
            "logs/uv-version.log","logs/fresh-environment-probe.log"} or n.startswith(("probes/","audits/"))]
        derived=root/"derived-metadata";C.copy_members(archive,files,names,derived,inventory)
        result=C.core.read_json(derived/"result.json");rows=validate_result(result,A.H.CASES,inventory_sha,A)
        report["phase"]="sources";freeze,verified,view,view_map=verify_sources(C,A,derived,ROOT,root)
        report["phase"]="native-inputs";native=verify_native(C,A,archive,files,inventory)
        inputs=verify_inputs(C,A,archive,files,inventory,C.core.read_json(derived/"input-admission.json"))
        write(root/"native-links.json",native);write(root/"input-validation.json",inputs)
        runtime,identities=verify_probes(C,A,derived,inventory,result,verified,freeze)
        verify_installer(C,A,derived,result,runtime)
        for arm,identity in identities.items():
            require(C.read_member(archive,files,f"raw/{arm}/which.txt").decode()==
                "chronicler "+identity["source_file"]+"\nnative "+identity["native_file"]+" "+A.WHEELS[arm].native_sha256+"\n",
                "final arm-root driver provenance differs")
        C.raw_sets(inventory,A.H.CASES)
        comparisons,counts,summaries=[],{},[]
        for case in A.H.CASES:
            report["phase"]="case-"+case
            require(time.monotonic()<deadline-CLEANUP_RESERVE,"reader cleanup reserve reached")
            selected=[n for n in files if any(n.startswith(f"raw/{arm}/{case}/") for arm in A.SOURCES)
                or n in (f"audits/baseline-{case}.json",f"audits/candidate-{case}.json")]
            scratch=root/"derived-case-scratch";budget=C.copy_members(archive,files,selected,scratch,inventory)
            marker={"kind":"derived-native-export-reader-case","case":case,"archive_sha256":ARCHIVE_SHA}
            write(scratch/".derived-reader-scratch.json",marker)
            selected_inventory={n:inventory[n] for n in selected}
            helper=SimpleNamespace(CASES={case:A.H.CASES[case]},COMMON=A.H.COMMON,SIDECARS=A.H.SIDECARS,
                require_stamp=A.H.require_stamp,case_contract=A.H.case_contract)
            case_counts,case_summary=C.core.verify_cases(scratch,selected_inventory,[r for r in rows if r["case"]==case],helper,view)
            comparison=compare_supervised(C,A,scratch,view,case_counts,root,case,deadline,supervisors)
            require(C.core.payload_inventory(view)==view_map,"frozen comparison source changed")
            retire_case(C,scratch,selected_inventory,marker)
            comparisons.append({"case":case,"admission":budget,**comparison});counts.update(case_counts);summaries+=case_summary
            write(root/(case+"-result.json"),comparisons[-1])
        require(len(comparisons)==9 and set(counts)==set(A.H.CASES),"nine comparisons incomplete")
        original=C.core.parse_comparison(C.read_member(archive,files,"logs/compare.log",C.core.COMPARE_LIMIT).decode(),counts)
        for value in verified.values():C.git_source.verify_snapshot(ROOT,value)
        baseline_driver=verify_baseline_driver(C,root,verified["baseline"]["files"]["scripts/turn_speed_identity.py"])
        require(C.core.payload_inventory(view)==view_map and C.core.payload_inventory(derived)=={n:inventory[n] for n in names},"derived source/metadata changed")
        require(C.core.digest(archive_path,ARCHIVE_BYTES)=={"bytes":ARCHIVE_BYTES,"sha256":ARCHIVE_SHA}
            and (archive_path.stat().st_ino,archive_path.stat().st_size,archive_path.stat().st_mtime_ns)==
            (initial_stat.st_ino,initial_stat.st_size,initial_stat.st_mtime_ns),"original archive changed")
        require(not any(n=="chronicler_agents" or n.startswith("chronicler_agents.") for n in sys.modules),"reader loaded native runtime")
        require(time.monotonic()<=deadline,"qualification deadline exceeded")
        report.update(qualified=True,phase="complete",inventory_sha256=inventory_sha,payload_files=len(inventory),
            total_expansion_bytes=sum(r["bytes"] for r in inventory.values()),comparison=comparisons,cases=summaries,
            original_comparison=original,source_snapshots={k:{"sha":v["sha"],"crate_tree":v["crate_tree"],"files":len(v["files"])} for k,v in verified.items()},
            native_links=native,original_runtime=runtime,inventory_seal="Registered complete outer SHA seals inventory; result pointer and every payload member independently recomputed.",
            inspector_native_import_attempts=native_guard.attempts,
            reader_packages={n:importlib.metadata.version(n) for n in ("numpy","scipy","pyarrow","pydantic","arro3-core")},
            reader_native_package_present=False,reader_native_distribution_present=False,
            derived_baseline_driver=baseline_driver,
            reader_thread_env={k:os.environ.get(k) for k in (*A.H.CAPS,"PYTHONHASHSEED","OPENBLAS_THREAD_TIMEOUT")},
            arrow_scope="Opaque payload bytes hashed/compared; no Arrow decoding.",installer_scope="Original installer checksum is an observation; its executable was not retained for independent rehash.")


def finalize(C,root,report,started,deadline,quiescent):
    desired=report.get("qualified") is True;report["qualified"]=False
    publication=root/"publication";publication.mkdir(exist_ok=True)
    report["reader_seconds"]=time.monotonic()-started
    write(publication/"reader-result.json",report)
    try:
        require(quiescent,"writer quiescence unverified; authority inventory withheld")
        selected=[p for p in root.iterdir() if p.is_file() and p.name != "reader-result.json"]
        selected += list((root/"logs").glob("*.log"))
        if (root/"derived-metadata").exists():selected+=list((root/"derived-metadata").rglob("*"))
        selected=[p for p in selected if p.is_file()]
        require(sum(p.stat().st_size for p in selected)<=PUBLICATION_LIMIT,"light publication bound exceeded")
        C.admission(root,sum(p.stat().st_size for p in selected))
        for path in selected:
            relative=path.relative_to(root);target=publication/relative
            target.parent.mkdir(parents=True,exist_ok=True)
            with path.open("rb") as source,target.open("xb") as dest:shutil.copyfileobj(source,dest,64*1024)
            require(C.core.digest(target)==C.core.digest(path),"authority copy differs")
        inventory=C.core.payload_inventory(publication);inventory.pop("reader-result.json")
        write(publication/"inventory.json",inventory)
        report["publication_inventory_sha256"]=C.core.digest(publication/"inventory.json")["sha256"]
        require(time.monotonic()<=deadline,"late reader finalization")
        report["qualified"]=desired
    except BaseException as error:
        report.update(qualified=False,publication_error=type(error).__name__)
    report["reader_seconds"]=time.monotonic()-started
    write(publication/"reader-result.json",report)
    ended=time.monotonic()
    if ended>deadline:
        report.update(qualified=False,reader_seconds=ended-started,publication_error="qualification deadline exceeded after terminal write")
        write(publication/"reader-result.json",report)
    return 0 if report["qualified"] else 1


def api_metadata(A,transport):
    result={}
    for role,suffix in (("run",f"/actions/runs/{RUN}"),("jobs",f"/actions/runs/{RUN}/jobs?filter=all&per_page=100"),
                        ("artifacts",f"/actions/runs/{RUN}/artifacts?per_page=100")):
        with transport.api(suffix) as stream:raw=stream.read(A.METADATA_LIMIT+1)
        require(len(raw)<=A.METADATA_LIMIT,"official metadata bound exceeded")
        result[role]=A.H.strict_json(raw)
    validate_metadata(result)
    return result


def own_source(C,expected):
    actual=subprocess.check_output(["git","-c","core.fsmonitor=false","-C",str(ROOT),"rev-parse","HEAD"],timeout=10,text=True).strip()
    require(actual==expected and not subprocess.check_output(["git","-c","core.fsmonitor=false","-C",str(ROOT),"status","--porcelain=v1","--untracked-files=all"],timeout=10),"reader source must be exact committed clean source")
    names=["scripts/"+n for n in KERNELS]+["scripts/native_default_output_identity_qualification.py","scripts/arc_output_identity_qualification.py",
        "scripts/native_default_output_artifact_reader.py","tests/test_native_default_output_artifact_reader.py","AGENTS.md","pyproject.toml","uv.lock",TEMPLATE_PATH]
    observed={}
    for name in names:
        raw=C.git_source.read_blob(ROOT,expected,name)
        require(bounded(ROOT/name)==raw,"actual sparse reader source differs from Git blob")
        observed[name]=pin(raw)
    active=C.git_source.read_blob(ROOT,expected,WORKFLOW_PATH)
    require(pin(active)["sha256"]==WORKFLOW_SHA and active==bounded(ROOT/TEMPLATE_PATH),"active workflow differs from reviewed template")
    return {"sha":expected,"selected_files":observed,"active_workflow":pin(active),"scope":"Actual selected sparse source bytes linked to committed blobs; no full reconstructed worktree claim."}


def hydrate_and_verify_source(C,A,expected,supervisor,env,stage):
    # Sparse checkout uses a partial clone. The immutable backend deliberately
    # forbids lazy fetch, so prime every complete object set explicitly first.
    stage["name"]="source-head"
    current=subprocess.check_output(["git","-c","core.fsmonitor=false","-C",str(ROOT),"rev-parse","HEAD"],timeout=10,text=True).strip()
    require(current==expected,"actual current control revision differs")
    stage["name"]="source-object-hydration"
    for role,sha in {"reader":current,**A.SOURCES,"producer":CONTROL}.items():
        supervisor.command("hydrate-"+role,["git","-c","core.fsmonitor=false","-c","gc.auto=0","-c","maintenance.auto=false",
            "fetch","--no-tags","--refetch","--no-filter","--depth=1","origin",sha],env,ROOT)
    stage["name"]="source-authentication"
    return own_source(C,current)


def final_sources(C,context,root,before):
    require(own_source(C,context["source"])==before,"reader source changed during inspection")
    for name,(_,sha) in KERNELS.items():
        require(C.core.digest(root/"derived-kernels"/name)["sha256"]==sha,"kernel changed after inspection")
    require(all(C.core.digest(root/name)==value for name,value in context["metadata_pins"].items()),"official metadata changed during inspection")


def entry_inspect(args):
    registration(os.environ);A=producer();root=args.context.parent
    raw=bounded(args.context);require(pin(raw)["sha256"]==args.context_sha,"carried context changed")
    context=A.H.strict_json(raw)
    require(context["source"]==os.environ["GITHUB_SHA"] and type(context["started"]) is float
        and type(context["deadline"]) is float and math.isfinite(context["started"]) and math.isfinite(context["deadline"])
        and context["deadline"]==context["started"]+SECONDS,"shared qualification clock differs")
    C=load_kernels(root/"derived-kernels")
    report={"qualified":False,"phase":"admission","original_run":RUN,"original_artifact":ARTIFACT,"original_control":CONTROL,
        "baseline":A.SOURCES["baseline"],"candidate":A.SOURCES["candidate"],"reader_source":context["source"],
        "reader_python":sys.version,"reader_affinity":sorted(os.sched_getaffinity(0)),"limits":context["limits"],
        "started_monotonic":context["started"],"qualification_deadline_monotonic":context["deadline"],
        "context_sha256":args.context_sha,
        "scope":"Completed exports only; zero new worlds/pools; no checkpoint/RNG-state, science, speed or adoption claim."}
    supervisors=[]
    try:
        before=own_source(C,context["source"]);require(before==C.core.read_json(root/"reader-source.json"),"reader source changed across prefix entry")
        require(validate_metadata(C.core.read_json(root/"metadata-before.json"))==validate_metadata(C.core.read_json(root/"metadata-after.json")),"publication identity changed")
        inspect(C,A,context,root,report,supervisors)
        final_sources(C,context,root,before)
    except BaseException as error:
        report.update(qualified=False,**error_record(error,A,C,report["phase"]))
    return finalize(C,root,report,context["started"],context["deadline"],all(s.cleanup_complete for s in supervisors))


def audit(args):
    require(args.execute is True,"inactive: explicit --execute required")
    registered=registration(os.environ);A=producer()
    require(not [k for k in os.environ if k.startswith("GIT_") and k!="GIT_PAGER"],"ambient Git override refused")
    require(ROOT==Path(os.environ["GITHUB_WORKSPACE"]).resolve()/"control","closed sparse control root required")
    temporary=Path(os.environ["RUNNER_TEMP"]).resolve();root=args.evidence.resolve();prefix=args.prefix.resolve()
    require(root==temporary/"native-default-artifact-audit" and prefix==temporary/"native-default-artifact-reader-env"
        and not root.exists() and not prefix.exists(),"fresh registered external paths required")
    root.mkdir();(root/"logs").mkdir();(root/"inputs").mkdir();(root/"publication").mkdir()
    started=time.monotonic();deadline=started+SECONDS
    write(root/"publication/reader-result.json",{"qualified":False,"phase":"bootstrap","original_run":RUN})
    supervisor=A.H.Supervisor(root,deadline-CLEANUP_RESERVE);C=None;stage={"name":"initial-resource-admission"}
    try:
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))});supervisor.admission("audit-initial",12,2)
        stage["name"]="kernel-authentication"
        C=load_kernels(root/"derived-kernels",create=True)
        env={k:v for k,v in os.environ.items() if k not in {"GITHUB_TOKEN","GH_TOKEN","PYTHONPATH","PYTHONHOME","VIRTUAL_ENV"}
             and not k.startswith(("UV_","PIP_"))}
        env.update(A.H.CAPS,PYTHONDONTWRITEBYTECODE="1",PYTHONNOUSERSITE="1",PYTHONOPTIMIZE="0",PYTHONHASHSEED="0",OPENBLAS_THREAD_TIMEOUT="16",PIP_CONFIG_FILE=os.devnull)
        source=hydrate_and_verify_source(C,A,registered["GITHUB_SHA"],supervisor,env,stage)
        write(root/"reader-source.json",source)
        stage["name"]="dependency-preparation"
        preparation=A.prepare_environment(root,{"candidate":ROOT,"control":ROOT},str(prefix/"bin/python"),prefix,env,supervisor)
        write(root/"reader-preparation.json",preparation)
        transport=A.Transport(os.environ.get("GITHUB_TOKEN"),supervisor,deadline-CLEANUP_RESERVE)
        stage["name"]="producer-metadata-before"
        before=api_metadata(A,transport);write(root/"metadata-before.json",before)
        artifact_pin=A.ArtifactPin(ARTIFACT,RUN,JOB,CONTROL,f"native-default-output-identity-{RUN}-1",ARCHIVE_BYTES,ARCHIVE_SHA,EXPIRY,
            ".github/workflows/native-default-output-identity.yml")
        stage["name"]="artifact-transfer"
        transport.download(artifact_pin,root/"inputs/original.zip")
        stage["name"]="producer-metadata-after"
        after=api_metadata(A,transport);write(root/"metadata-after.json",after)
        require(validate_metadata(before)==validate_metadata(after),"producer publication changed during transfer")
        require(supervisor.cleanup_complete and not supervisor.children,"bootstrap writers remain before prefix exec")
        context={"source":registered["GITHUB_SHA"],"started":started,"deadline":deadline,"prefix":str(prefix),
            "metadata_pins":{name:C.core.digest(root/name) for name in ("metadata-before.json","metadata-after.json")},
            "limits":{"qualification_seconds":SECONDS,"cleanup_reserve":CLEANUP_RESERVE,"outer_seconds":610,"outer_kill_grace":5,
                "effective_latest_audit_utc":min(p.expiry for p in A.ARTIFACTS.values()),
                "max_entries":2048,"max_member_json":32*1024**2,"max_expansion":512*1024**2,"disk_floor":3*GIB,"copy_reserve":16*1024**2}}
        write(root/"context.json",context)
        stage["name"]="prefix-entry"
        # Replace the bootstrap owner: no nested inspect session or reset clock.
        os.execve(str(prefix/"bin/python"),[str(prefix/"bin/python"),"-B",str(SCRIPT),"inspect","--context",str(root/"context.json"),
            "--context-sha",pin(bounded(root/"context.json"))["sha256"]],env)
    except BaseException as error:
        report={"qualified":False,"phase":"bootstrap","reader_source":registered["GITHUB_SHA"],**error_record(error,A,C,stage["name"])}
        if C is not None:return finalize(C,root,report,started,deadline,supervisor.cleanup_complete)
        report["reader_seconds"]=time.monotonic()-started;write(root/"publication/reader-result.json",report);return 1


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);commands=parser.add_subparsers(dest="command")
    commands.add_parser("describe")
    p=commands.add_parser("audit");p.add_argument("--execute",action="store_true")
    p.add_argument("--evidence",type=Path,required=True);p.add_argument("--prefix",type=Path,required=True)
    p=commands.add_parser("inspect");p.add_argument("--context",type=Path,required=True);p.add_argument("--context-sha",required=True)
    args=parser.parse_args(argv)
    if args.command=="audit":return audit(args)
    if args.command=="inspect":return entry_inspect(args)
    print(json.dumps({"status":"inactive","artifact":ARTIFACT,"new_worlds":0,"comparisons_registered":9,
        "scope":"Source-only closed registration; no transfer, setup or audit executed."}));return 0


if __name__=="__main__":raise SystemExit(main())
