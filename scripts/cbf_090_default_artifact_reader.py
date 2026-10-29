#!/usr/bin/env python3
"""Dormant original-byte audit of one completed CBF-to-090 export producer.

No command generates/restores a World, installs a retained native wheel or
decodes Arrow/checkpoint state. Transfer/audit requires a separate activation.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import importlib.util
import io
import json
import math
import os
from pathlib import Path
import platform
import re
import shutil
import stat
import subprocess
import sys
import time
from types import MappingProxyType, ModuleType, SimpleNamespace
import zipfile

SCRIPT, GIB = Path(__file__).resolve(), 1024**3
ROOT = SCRIPT.parents[1]
PRODUCER = "c7727863fad70b1a6365f3174a30f04f68a451a4"
RUN, JOB, ARTIFACT = 40875019978, 123451508654, 12896929475
ARCHIVE_BYTES = 70712129
ARCHIVE_SHA = "0b333468326a7383a9ab607557e109c698377506ae8496d0a61c8dbc85692cd4"
INVENTORY_SHA = "c6a5051b71503c1795af0614aec915a9f840719e57aa65b1c4b5807fa160722b"
EXPIRY = "2026-11-28T12:43:08Z"
BRANCH = "lead/cloud-cbf-090-default-artifact-audit-20261029"
WORKFLOW = ".github/workflows/cbf-090-default-artifact-audit.yml"
TEMPLATE = "docs/experiments/cbf-090-default-artifact-reader-workflow.yml"
JOB_KEY = "cbf-090-default-artifact-audit"
TEMPLATE_SHA = "db4a5e7af53ca793fa229a148a4a73f2f2dda0dd020f86cb3de1be9332fd872c"
SECONDS, CLEANUP_RESERVE = 600, 20
PINS = MappingProxyType({
    "native_default_output_artifact_reader.py": (45345,"e1bb40b6306984de70cafd3e66174480ab2870bb979a613756220c69ba855577"),
    "cbf_090_default_identity.py": (27584,"7aa758a678022ca89699c6077606554d76b9c7d969072b241c90fafc4bc56c48"),
    "native_default_output_identity_qualification.py": (41999,"fe7129a6c3d9386cc5aed7e4a6430509d552e4e87101510b02ddb016ef7f38d1"),
    "arc_output_identity_qualification.py": (34186,"0d3a2c5db023a47a82307d3a9b789eebd979915e52be66e7208f0c93a94540f5"),
    "completed_export_study_reader.py": (27953,"ab0168bed9d97f4b9d96a7eec5d792e934214bf50858ce69644267039b19bc31"),
    "default_output_identity_reader.py": (27754,"2bacde640402ce64ac52e284f3eb63d3462e1b00ec299ae8a21e1b6f065c649c"),
    "export_study_git.py": (20231,"80434ebb0d455ce3f2d329efd5878c2ae28dd9fca652581e9210d242ae2c53fc"),
})


class Refusal(RuntimeError):
    pass


def require(value, message):
    if not value: raise Refusal(message)


def pin(raw):
    return {"bytes":len(raw),"sha256":hashlib.sha256(raw).hexdigest()}


def same(a,b):
    if type(a) is not type(b): return False
    if isinstance(a,dict): return set(a)==set(b) and all(same(a[k],b[k]) for k in a)
    if isinstance(a,list): return len(a)==len(b) and all(same(x,y) for x,y in zip(a,b))
    return a==b


def closed(value, keys, message):
    require(type(value) is dict and set(value)==set(keys),message)


def compile_source(raw,path,name):
    module=ModuleType(name);module.__file__=str(path);sys.modules[name]=module
    exec(compile(raw,str(path),"exec"),module.__dict__)
    return module


def authenticate(directory=SCRIPT.parent):
    raw={}
    for name,(size,digest) in PINS.items():
        path=directory/name
        require(not path.is_symlink() and path.is_file() and path.stat().st_size==size,"utility file differs: "+name)
        raw[name]=path.read_bytes()
        require(pin(raw[name])=={"bytes":size,"sha256":digest},"utility bytes differ: "+name)
    return raw  # All seven authenticated before any module/cache execution.


@dataclass(frozen=True)
class ArmUtilities:
    WHEELS: object
    WHEEL_NAME: str
    NATIVE_MEMBER: str
    PYTHON: str
    H: object
    validate_wheel: object


@dataclass(frozen=True)
class Utilities:
    R: object
    B: object
    C: object
    arms: ArmUtilities


def load_modules(root, raw):
    require(set(raw)==set(PINS) and all(pin(raw[n])=={"bytes":size,"sha256":digest} for n,(size,digest) in PINS.items()),"unauthenticated utility buffers")
    view=root/"authenticated-utilities";scripts=view/"scripts"
    require(not view.exists(),"fresh utility view required")
    require(shutil.disk_usage(root).free>=3*GIB+sum(map(len,raw.values()))+16*1024**2,"utility-copy reserve refused")
    scripts.mkdir(parents=True)
    for name,value in raw.items():
        with (scripts/name).open("xb") as stream: stream.write(value)
        (scripts/name).chmod(0o444)
    scripts.chmod(0o555);view.chmod(0o555)
    verify_utility_view(root,raw)
    R=compile_source(raw["native_default_output_artifact_reader.py"],scripts/"native_default_output_artifact_reader.py","_cbf_audit_R")
    B=compile_source(raw["cbf_090_default_identity.py"],scripts/"cbf_090_default_identity.py","_cbf_audit_B")
    # This generic loader authenticates and copies the unchanged three kernels;
    # it never calls bind_study or changes any historical registration/global.
    C=R.load_kernels(root/"derived-kernels",create=True)
    verify_kernel_view(root,raw)
    A=B.A
    return Utilities(R,B,C,ArmUtilities(B.WHEELS,A.WHEEL_NAME,A.NATIVE_MEMBER,A.PYTHON,B.H,A.validate_wheel))


def verify_utility_view(root,raw):
    view=root/"authenticated-utilities";scripts=view/"scripts"
    require(not view.is_symlink() and not scripts.is_symlink() and stat.S_IMODE(view.stat().st_mode)==0o555
        and stat.S_IMODE(scripts.stat().st_mode)==0o555 and {p.name for p in view.iterdir()}=={"scripts"}
        and {p.name for p in scripts.iterdir()}==set(raw),"private utility/cache membership or mode differs")
    for name,value in raw.items():
        path=scripts/name
        require(not path.is_symlink() and path.is_file() and stat.S_IMODE(path.stat().st_mode)==0o444
            and path.read_bytes()==value,"private authenticated utility changed")


def verify_kernel_view(root,raw):
    directory=root/"derived-kernels";names={"completed_export_study_reader.py","default_output_identity_reader.py","export_study_git.py"}
    require(not directory.is_symlink() and stat.S_IMODE(directory.stat().st_mode)==0o555
        and {p.name for p in directory.iterdir()}==names,"private kernel/cache membership differs")
    for name in names:
        path=directory/name
        require(not path.is_symlink() and path.is_file() and stat.S_IMODE(path.stat().st_mode)==0o444
            and path.read_bytes()==raw[name],"private kernel changed")


def artifact_pin(U):
    return U.B.A.ArtifactPin(ARTIFACT,RUN,JOB,PRODUCER,"cbf-090-default-identity-v2-40875019978-1",
        ARCHIVE_BYTES,ARCHIVE_SHA,EXPIRY,".github/workflows/cbf-090-default-identity-v2.yml")


def validate_metadata(U,value,now=None):
    closed(value,("run","job","jobs","artifacts"),"metadata roles differ")
    run,job,jobs,artifacts=(value[k] for k in ("run","job","jobs","artifacts"))
    require(type(artifacts.get("total_count")) is int and artifacts["total_count"]==1
        and len(artifacts.get("artifacts",[]))==1 and type(jobs.get("total_count")) is int
        and jobs["total_count"]==1 and len(jobs.get("jobs",[]))==1,"complete job/artifact sets differ")
    U.B.A.validate_publication(artifact_pin(U),run,job,artifacts["artifacts"][0],now or datetime.now(timezone.utc))
    require(run["repository"]["full_name"]==U.B.A.REPOSITORY and run["head_repository"]["full_name"]==U.B.A.REPOSITORY
        and type(run["head_repository"]["id"]) is int and run["head_repository"]["id"]==U.B.A.REPOSITORY_ID,"producer repository origins differ")
    require(run["event"]=="push" and run["head_branch"]=="lead/cloud-cbf-090-default-identity-v2-20261029"
        and job["name"]=="cbf-090-default-identity-v2" and same(jobs["jobs"][0],job),"producer branch/job differs")
    expected=((1,"Set up job"),(2,"Select fresh external environment path"),(3,"Check out reviewed controls"),
        (4,"Check out exact CBF source"),(5,"Check out exact qualified 090 source"),(6,"Set up exact Python runtime"),
        (7,"Check unchanged original pure contracts"),(8,"Check closed CBF to 090 pure contracts"),
        (9,"Describe inactive registration"),(10,"Execute after separate source and activation review"),
        (11,"Retain complete positive or negative evidence"),(19,"Post Set up exact Python runtime"),
        (20,"Post Check out exact qualified 090 source"),(21,"Post Check out exact CBF source"),
        (22,"Post Check out reviewed controls"),(23,"Complete job"))
    require(all(type(s["number"]) is int for s in job["steps"]) and [(s["number"],s["name"]) for s in job["steps"]]==list(expected)
        and all(s["status"]=="completed" and s["conclusion"]=="success" for s in job["steps"]),"producer stages incomplete")
    return artifacts["artifacts"][0]


def validate_result(U,value,inventory_sha):
    B=U.B
    keys="schema_version qualified status sources crates producer cases expected_schemas actual_observations CI_qualification native_sha256_by_arm wheel_sha256_by_arm normalization limitations installer installed_native_path installed_native_arm runtime inventory_sha256 elapsed_wall_seconds".split()
    closed(value,keys,"actual producer result schema differs")
    require(type(value["schema_version"]) is int and value["schema_version"]==1 and value["qualified"] is True
        and value["status"]=="exports_complete_pending_completed_job" and value["inventory_sha256"]==inventory_sha==INVENTORY_SHA,
        "producer result incomplete or inventory pointer differs")
    require(same(value["sources"],dict(B.SOURCES)) and same(value["crates"],dict(B.CRATES))
        and same(value["expected_schemas"],B.EXPECTED_SCHEMAS) and same(value["CI_qualification"],dict(B.CI_QUALIFICATION)),"producer registration differs")
    producer=dict(control_sha=PRODUCER,run_id=str(RUN),run_attempt="1",job_key="cbf-090-default-identity-v2",event="push",
        branch="lead/cloud-cbf-090-default-identity-v2-20261029",workflow_ref=B.A.REPOSITORY+"/.github/workflows/cbf-090-default-identity-v2.yml@refs/heads/lead/cloud-cbf-090-default-identity-v2-20261029")
    require(value["producer"]==producer and value["normalization"]=="metadata.generated_at only; original .log/run_manifest exclusions"
        and value["installed_native_arm"]=="candidate","producer context or comparator rules differ")
    require(value["limitations"]==["Exact CBF-to-090 default exports only; no checkpoint/RNG/science/performance/adoption grant",
        "Requires separate completed-job/publication and independent artifact qualification",
        "Standard CI did not measure schemas; actual fresh fields stay null until real probes"],"producer scope differs")
    require(value["native_sha256_by_arm"]=={a:w.native_sha256 for a,w in B.WHEELS.items()}
        and value["wheel_sha256_by_arm"]=={a:w.sha256 for a,w in B.WHEELS.items()},"per-arm identities differ")
    require(type(value["elapsed_wall_seconds"]) in (int,float) and math.isfinite(value["elapsed_wall_seconds"])
        and 0<value["elapsed_wall_seconds"]<=4800,"producer clock differs")
    B.require_complete(value["cases"])
    for row in value["cases"]: closed(row,("arm","case","status","audit_sha256"),"case row schema differs")
    closed(value["actual_observations"],B.SOURCES,"last actual observation roles differ")
    require(all(type(v) is dict for v in value["actual_observations"].values()),"actual observations missing")
    return value["cases"]


def validate_probe(U,value,arm,package_digest,runtime=None):
    B,R=U.B,U.R;wheel=B.WHEELS[arm]
    closed(value,"source native schemas source_file native_file environment affinity prefix runtime".split(),"probe fields differ")
    source,native,actual,env=(value[k] for k in ("source","native","runtime","environment"))
    closed(source,("git_sha","git_ref","package_dir","package_digest"),"probe source fields differ")
    closed(native,("status","source","module_file","bytes","sha256"),"probe native fields differ")
    package=R.historical(source["package_dir"]);prefix=R.historical(value["prefix"]);native_path=R.historical(value["native_file"])
    require(source["git_sha"]==B.SOURCES[arm] and source["package_digest"]==package_digest and source["git_ref"] is None
        and package.parts[-2:]==("src","chronicler") and package.parents[1].name==arm
        and R.historical(value["source_file"])==package/"__init__.py","historical own-source import differs")
    require(native["status"]=="found" and native["source"]=="imported" and native["module_file"]==value["native_file"]
        and native_path.is_relative_to(prefix) and native_path.name==Path(B.A.NATIVE_MEMBER).name
        and type(native["bytes"]) is int and native["bytes"]==wheel.native_size and native["sha256"]==wheel.native_sha256
        and same(value["schemas"],B.EXPECTED_SCHEMAS),"actual retained compiled/schema observation differs")
    closed(actual,"python version implementation platform machine executable prefix affinity cpu_count process_cpu_count optimize no_user_site dont_write_bytecode thread_env packages".split(),"runtime seal fields differ")
    require(actual["python"]==B.A.PYTHON and actual["implementation"]=="CPython" and actual["version"].startswith(B.A.PYTHON+" ")
        and actual["machine"]=="x86_64" and actual["prefix"]==str(prefix) and same(actual["affinity"],value["affinity"])
        and type(actual["affinity"]) is list and len(actual["affinity"])==1 and type(actual["affinity"][0]) is int
        and actual["affinity"][0]>=0,"actual retained runtime/affinity differs")
    for key,n in (("cpu_count",1),("process_cpu_count",1),("optimize",0),("no_user_site",1)):
        require(type(actual[key]) is int and actual[key]==n,"runtime typed policy differs: "+key)
    require(actual["dont_write_bytecode"] is True and actual["thread_env"]=={**B.H.CAPS,"PYTHONHASHSEED":"0","OPENBLAS_THREAD_TIMEOUT":"16"}
        and set(actual["packages"])==set(B.A.PACKAGE_NAMES) and all(type(v) is str and v for v in actual["packages"].values()),"runtime packages/caps differ")
    R.historical(actual["executable"])
    expected={k:actual[k] for k in ("python","implementation","platform","machine","cpu_count","process_cpu_count","packages")}
    expected.update(executable=env.get("executable"),affinity_cpu_count=1,thread_env={k:v for k,v in actual["thread_env"].items() if k!="CARGO_BUILD_JOBS"})
    require(same(env,expected) and R.historical(env["executable"]).is_relative_to(prefix)
        and R.historical(env["executable"]).name in ("python","python3","python3.13"),"duplicated environment differs")
    require(runtime is None or same(actual,runtime),"cross-probe/arm runtime differs")
    return actual


def verify_sources(U,metadata,repo,root):
    B,C=U.B,U.C;freeze=C.core.read_json(metadata/"freeze.json");before=freeze["sources"]
    require(before==C.core.read_json(metadata/"sources-after.json") and set(before)=={"baseline","candidate","control"},"original source standing differs")
    verified={}
    for role,sha in {**B.SOURCES,"control":PRODUCER}.items():
        require(before[role]["sha"]==sha,"wrong source role")
        verified[role]=C.git_source.verify_snapshot(repo,before[role])
        if role in B.CRATES: require(verified[role]["crate_tree"]==B.CRATES[role],"arm crate differs")
    require(freeze["utilities"]==json.loads(json.dumps(dict(B.KERNELS))) and freeze["adapter_sha256"]==PINS["cbf_090_default_identity.py"][1]
        and freeze["matrix"]==json.loads(json.dumps(B.H.CASES)) and freeze["thread_caps"]==B.H.CAPS,"producer freeze differs")
    require(type(freeze["affinity"]) is list and len(freeze["affinity"])==1 and type(freeze["affinity"][0]) is int
        and freeze["affinity"][0]>=0,"producer freeze affinity differs")
    for name in ("cbf_090_default_identity.py","arc_output_identity_qualification.py","native_default_output_identity_qualification.py"):
        require(verified["control"]["files"]["scripts/"+name]["sha256"]==PINS[name][1],"actual producer utility differs")
    for name in B.SHARED_FILES:
        require(verified["baseline"]["files"][name]==verified["candidate"]["files"][name],"shared source input differs")
    require(C.git_source.package_digest(verified["baseline"])==C.git_source.package_digest(verified["candidate"]),"package digests differ")
    selected=[n for n in verified["candidate"]["files"] if n.startswith("src/chronicler/") and n.endswith(".py")]+["scripts/turn_speed_identity.py","scripts/cities_identity.py"]
    C.admission(root,sum(verified["candidate"]["files"][n]["bytes"] for n in selected))
    view=root/"derived-candidate";view_map=C.git_source.materialize_python_view(repo,B.SOURCES["candidate"],view,["scripts/turn_speed_identity.py","scripts/cities_identity.py"])
    descriptor=verified["baseline"]["files"]["scripts/turn_speed_identity.py"]
    C.admission(root,descriptor["bytes"]);C.write_git_file(repo,B.SOURCES["baseline"],"scripts/turn_speed_identity.py",root/"baseline-driver.py",descriptor)
    B.H.require_matrix(root/"baseline-driver.py");B.H.require_matrix(view/"scripts/turn_speed_identity.py")
    return freeze,verified,view,view_map


def verify_inputs(U,archive,files,inventory,admission):
    B,C=U.B,U.C;closed(admission,("publications","arms","members"),"input admission fields differ")
    require(set(admission["publications"])==set(B.ARTIFACTS) and set(admission["members"])==set(B.ARTIFACTS)
        and set(admission["arms"])==set(B.SOURCES),"four input roles differ")
    observed={}
    for role,p in B.ARTIFACTS.items():
        require(B.A.utc(p.expiry)>datetime.now(timezone.utc),"original nested-input expiry reached")
        raw=C.read_member(archive,files,"inputs/"+str(p.artifact_id)+".zip")
        require(pin(raw)=={"bytes":p.size,"sha256":p.sha256},"nested original ZIP differs")
        B.bounded_zip(io.BytesIO(raw));arm=role.split("-",1)[0]
        selected={"ci-native-wheel/manifest.json",B.WHEELS[arm].member} if role.endswith("-wheel") else {"native-identity.json"}
        observed[role]=B.A.inspect_zip(io.BytesIO(raw),selected)
        require(same(observed[role][0],admission["members"][role]),"nested complete member map differs")
        pub=admission["publications"][role];closed(pub,("before","after"),"CI publication phases differ")
        for phase in pub.values():
            value=phase["observed"]
            require(same(B.validate_publication(p,*(value[k] for k in ("run","job","artifact")),datetime.now(timezone.utc)),phase),"CI publication graph differs")
        require(same(pub["before"]["identity"],pub["after"]["identity"]),"CI identity changed")
    for arm,w in B.WHEELS.items():
        value=B.validate_ci_arm(arm,*observed[arm+"-wheel"],*observed[arm+"-preflight"])
        wheel=observed[arm+"-wheel"][1][w.member];B.bounded_zip(io.BytesIO(wheel))
        value["wheel_members"]=B.A.validate_wheel(wheel,w)
        require(same(value,admission["arms"][arm]),"actual per-arm input graph differs")
    require({n for n in inventory if n.startswith("inputs/")}=={"inputs/"+str(p.artifact_id)+".zip" for p in B.ARTIFACTS.values()},"input ZIP set differs")
    return {role:{"bytes":p.size,"sha256":p.sha256,"expiry":p.expiry} for role,p in B.ARTIFACTS.items()}


def verify_probes(U,metadata,inventory,result,verified,freeze):
    B,C=U.B,U.C;names=set();runtime=None;last={}
    for arm in B.SOURCES:
        digest=C.git_source.package_digest(verified[arm])
        for case in B.H.CASES:
            pair=[]
            for stage in ("before","after"):
                name=f"probes/{arm}-{case}-{stage}.json";names.add(name);value=C.core.read_json(metadata/name)
                runtime=validate_probe(U,value,arm,digest,runtime)
                require(same(value["affinity"],freeze["affinity"]),"probe/freeze affinity differs");pair.append(value)
            require(same(*pair),"before/after actual probe differs")
            name=f"probes/{arm}-{case}-which.txt";names.add(name)
            which="chronicler "+pair[0]["source_file"]+"\nnative "+pair[0]["native_file"]+" "+B.WHEELS[arm].native_sha256+"\n"
            require(U.R.bounded(metadata/name).decode()==which,"retained driver differs");last[arm]=pair[1]
        require(same(result["actual_observations"][arm],{k:last[arm][k] for k in ("schemas","native","source")}),"last actual observation differs")
    require({n for n in inventory if n.startswith("probes/")}==names and same(result["runtime"],runtime)
        and result["installed_native_path"]==last["candidate"]["native_file"],"complete probe/runtime graph differs")
    roots={arm:U.R.historical(v["source"]["package_dir"]).parents[1] for arm,v in last.items()}
    require(roots["baseline"].parent==roots["candidate"].parent,"historical source workspace differs")
    return runtime,last,roots


def verify_progress(U,metadata,result,roots,runtime):
    B,C=U.B,U.C;raw=U.R.bounded(metadata/"progress.jsonl")
    rows=[C.core.strict_json(line) for line in raw.splitlines() if line]
    starts=[r for r in rows if r["event"]=="child_start"]
    expected=["install-exact-uv","uv-version","locked-input-check","fresh-locked-environment","fresh-environment-probe"]
    for arm in B.SOURCES:
        expected.append("install-"+arm)
        for case in B.H.CASES:
            expected += [f"probe-{arm}-{case}-before",f"world-{arm}-{case}",f"probe-{arm}-{case}-after",f"audit-{arm}-{case}"]
    expected.append("compare")
    require([r["label"] for r in starts]==expected,"all80 owned child starts/order differ")
    pending=None;cleaned=False;completed=[]
    for r in rows:
        require(type(r.get("at")) in (int,float) and math.isfinite(r["at"]),"invalid progress clock")
        if r["event"]=="child_start":
            require(pending is None,"overlapping original owned children");pending=r["label"];cleaned=False
        elif r["event"]=="child_cleanup":
            require(not cleaned and r["label"]==pending and r["complete"] is True and r["cleanup_error"] is None,"owned cleanup not complete");cleaned=True
        elif r["event"]=="child_exit":
            require(cleaned and r["label"]==pending and type(r["returncode"]) is int and r["returncode"]==0,"owned exit differs")
            completed.append(pending);pending=None
        elif r["event"]=="resources":
            require(type(r["disk_free"]) is int and type(r["ram_available"]) is int,"untyped resource observation")
            disk,ram=(12,2) if r["phase"]=="initial" else ((6,2) if r["phase"] in ("environment-prepared","inputs-prepared","prepared-baseline","prepared-candidate") else (3,1))
            B.H.admit(r,disk,ram)
        else: require(r["event"] in ("resource_visibility","case_complete"),"unexpected original progress event")
    require(pending is None and completed==expected,"owned child completion ledger differs")
    resources=[r for r in rows if r["event"]=="resources"]
    required={"initial","environment-prepared","inputs-prepared","prepared-baseline","prepared-candidate"}|{p+":before" for p in expected}
    allowed=required|{"input-transfer"}|{p+":running" for p in expected}
    require(all(r["phase"] in allowed for r in resources) and all(sum(r["phase"]==p for r in resources)==1 for p in required)
        and any(r["phase"]=="input-transfer" for r in resources),"original resource admission ledger incomplete")
    done=[r for r in rows if r["event"]=="case_complete"]
    require([(r["arm"],r["case"],r["audit_sha256"]) for r in done]==[(r["arm"],r["case"],r["audit_sha256"]) for r in result["cases"]],"case-complete ledger differs")
    evidence=U.R.historical(starts[0]["cwd"]);prefix=U.R.historical(runtime["prefix"]);py=str(prefix/"bin/python")
    control=roots["baseline"].parent/"control";installer=result["installer"]["uv"]["path"]
    boot=result["installer"]["bootstrap_python"]
    setup={"install-exact-uv":[boot,"-m","pip","install","--disable-pip-version-check","--no-cache-dir","--only-binary=:all:","uv==0.13.6"],
        "uv-version":[installer,"--version"],"locked-input-check":[installer,"lock","--project",str(roots["candidate"]),"--check"],
        "fresh-locked-environment":[installer,"sync","--project",str(roots["candidate"]),"--frozen","--no-dev","--no-install-project","--no-build","--python",boot],
        "fresh-environment-probe":[py,"-I","-B","-c",B.A.ENVIRONMENT_PROBE]}
    for row in starts:
        command=row["command"];require(type(command) is list and command and all(type(x) is str for x in command),"original child argv differs")
        U.R.historical(row["cwd"]);U.R.historical(command[0])
        label=row["label"];cwd=evidence
        if label in setup: expected_command=setup[label]
        elif label.startswith("install-"):
            arm=label.removeprefix("install-");expected_command=B.A.install_command(py,evidence/"wheels"/arm/B.A.WHEEL_NAME,installer)
        elif label=="compare": expected_command=[py,str(roots["candidate"]/"scripts/turn_speed_identity.py"),"compare",str(evidence/"raw/baseline"),str(evidence/"raw/candidate")]
        else:
            family,arm,tail=label.split("-",2);cwd=evidence/"raw"/arm
            if family=="probe":
                case,stage=tail.rsplit("-",1)
                expected_command=[py,str(control/"scripts/cbf_090_default_identity.py"),"probe","--arm",arm,"--source-root",str(roots[arm]),"--expected-sha",B.SOURCES[arm],"--venv",str(prefix),"--out",str(evidence/"probes"/f"{arm}-{case}-{stage}.json")]
            elif family=="world": expected_command=[py,str(roots[arm]/"scripts/turn_speed_identity.py"),"run",str(cwd),"--source-root",str(roots[arm]),"--case",tail]
            else: expected_command=[py,str(control/"scripts/arc_output_identity_qualification.py"),"inspect","--case-root",str(cwd/tail),"--case",tail,"--out",str(evidence/"audits"/f"{arm}-{tail}.json")]
        require(command==expected_command and row["cwd"]==str(cwd),"original exact child argv/cwd differs: "+label)
    return {"owned_children":len(completed),"complete_exits":len(completed),"resource_rows":sum(r["event"]=="resources" for r in rows)}


def open_archive(U,path):
    before=path.stat()
    require(not path.is_symlink() and stat.S_ISREG(before.st_mode)
        and U.C.core.digest(path,ARCHIVE_BYTES)=={"bytes":ARCHIVE_BYTES,"sha256":ARCHIVE_SHA},"original archive differs before ZIP parsing")
    with path.open("rb") as stream: U.B.bounded_zip(stream)
    return zipfile.ZipFile(path),before


def verify_case_pair(U,archive,files,inventory,rows,view,view_map,root,case,deadline,supervisors):
    B,C,R=U.B,U.C,U.R
    require(time.monotonic()<deadline-CLEANUP_RESERVE,"reader cleanup reserve reached")
    selected=[n for n in files if any(n.startswith(f"raw/{a}/{case}/") for a in B.SOURCES) or n in (f"audits/baseline-{case}.json",f"audits/candidate-{case}.json")]
    scratch=root/"derived-case-scratch";budget=C.copy_members(archive,files,selected,scratch,inventory)
    marker={"kind":"cbf-090-derived-case","case":case,"archive_sha256":ARCHIVE_SHA};R.write(scratch/".derived-reader-scratch.json",marker)
    subset={n:inventory[n] for n in selected}
    helper=SimpleNamespace(CASES=MappingProxyType({case:B.H.CASES[case]}),COMMON=B.H.COMMON,SIDECARS=B.H.SIDECARS,require_stamp=B.H.require_stamp,case_contract=B.H.case_contract)
    counts,summary=C.core.verify_cases(scratch,subset,[r for r in rows if r["case"]==case],helper,view)
    comparison=R.compare_supervised(C,U.arms,scratch,view,counts,root,case,deadline,supervisors)
    require(C.core.payload_inventory(view)==view_map,"candidate view changed")
    R.retire_case(C,scratch,subset,marker)
    return {"case":case,"admission":budget,**comparison},counts,summary


def inspect_archive(U,root,context,report,supervisors):
    B,C,R=U.B,U.C,U.R;deadline=context["deadline"]
    require(platform.python_version()==B.A.PYTHON and platform.python_implementation()=="CPython" and platform.machine()=="x86_64"
        and sys.flags.optimize==0 and sys.flags.no_user_site==1 and sys.dont_write_bytecode
        and str(Path(sys.prefix).resolve())==context["prefix"] and len(os.sched_getaffinity(0))==1,"reader runtime differs")
    require(importlib.util.find_spec("chronicler_agents") is None and importlib.util.find_spec("chronicler") is None,"reader has installed simulation package")
    for name in ("chronicler-agents","chronicler"):
        try: importlib.metadata.distribution(name)
        except importlib.metadata.PackageNotFoundError: pass
        else: raise Refusal("reader has installed simulation distribution")
    require(all(os.environ.get(k)==v for k,v in B.H.CAPS.items()) and os.environ.get("PYTHONHASHSEED")=="0"
        and os.environ.get("OPENBLAS_THREAD_TIMEOUT")=="16","reader caps differ")
    guard=R.NativeGuard();sys.meta_path.insert(0,guard)
    validate_metadata(U,C.core.read_json(root/"metadata-after.json"))
    archive_path=root/"inputs/original.zip";archive,before=open_archive(U,archive_path)
    with archive:
        report["phase"]="complete-inventory"
        files,inventory,inventory_sha=R.complete_inventory(C,archive)
        require(inventory_sha==INVENTORY_SHA,"registered inventory seal differs")
        R.write(root/"verified-payload.json",inventory)
        names=[n for n in files if n in {"inventory.json","result.json","freeze.json","sources-after.json","input-admission.json",
            "environment-preparation.json","progress.jsonl","logs/uv-version.log","logs/fresh-environment-probe.log"} or n.startswith(("probes/","audits/"))]
        metadata=root/"derived-metadata";C.copy_members(archive,files,names,metadata,inventory)
        value=C.core.read_json(metadata/"result.json");rows=validate_result(U,value,inventory_sha)
        report["phase"]="sources";freeze,verified,view,view_map=verify_sources(U,metadata,ROOT,root)
        report["phase"]="native-inputs"
        native=R.verify_native(C,U.arms,archive,files,inventory)
        inputs=verify_inputs(U,archive,files,inventory,C.core.read_json(metadata/"input-admission.json"))
        report["phase"]="retained-probes";runtime,last,roots=verify_probes(U,metadata,inventory,value,verified,freeze)
        R.verify_installer(C,U.arms,metadata,value,runtime);owned=verify_progress(U,metadata,value,roots,runtime)
        for arm,v in last.items():
            require(C.read_member(archive,files,f"raw/{arm}/which.txt").decode()=="chronicler "+v["source_file"]+"\nnative "+v["native_file"]+" "+B.WHEELS[arm].native_sha256+"\n","final driver pointer differs")
        C.raw_sets(inventory,B.H.CASES);comparisons=[];counts={};summaries=[]
        for case in B.H.CASES:
            report["phase"]="case-"+case
            comparison,case_counts,summary=verify_case_pair(U,archive,files,inventory,rows,view,view_map,root,case,deadline,supervisors)
            counts.update(case_counts);summaries+=summary;comparisons.append(comparison);R.write(root/(case+"-result.json"),comparison)
        require(len(comparisons)==9 and set(counts)==set(B.H.CASES),"nine case comparisons incomplete")
        report["phase"]="final-graph";original=C.core.parse_comparison(C.read_member(archive,files,"logs/compare.log",C.core.COMPARE_LIMIT).decode(),counts)
        for v in verified.values(): C.git_source.verify_snapshot(ROOT,v)
        baseline=R.verify_baseline_driver(C,root,verified["baseline"]["files"]["scripts/turn_speed_identity.py"])
        require(C.core.payload_inventory(view)==view_map and C.core.payload_inventory(metadata)=={n:inventory[n] for n in names},"derived source/metadata changed")
        require(C.core.digest(archive_path,ARCHIVE_BYTES)=={"bytes":ARCHIVE_BYTES,"sha256":ARCHIVE_SHA}
            and (archive_path.stat().st_ino,archive_path.stat().st_size,archive_path.stat().st_mtime_ns)==(before.st_ino,before.st_size,before.st_mtime_ns),"original archive changed")
        require(not any(n=="chronicler_agents" or n.startswith("chronicler_agents.") for n in sys.modules),"reader loaded simulation native runtime")
        require(time.monotonic()<=deadline,"qualification deadline exceeded")
        report.update(qualified=True,phase="complete",inventory_sha256=inventory_sha,payload_files=len(inventory),total_expansion_bytes=sum(v["bytes"] for v in inventory.values()),
            comparisons=comparisons,original_comparison=original,cases=summaries,original_runtime=runtime,owned_child_ledger=owned,
            native_links=native,input_links=inputs,derived_baseline_driver=baseline,inspector_native_import_attempts=guard.attempts,
            source_snapshots={k:{"sha":v["sha"],"crate_tree":v["crate_tree"],"files":len(v["files"])} for k,v in verified.items()},
            reader_runtime={"python":platform.python_version(),"version":sys.version,"executable":sys.executable,"prefix":sys.prefix,
                "affinity":sorted(os.sched_getaffinity(0)),"thread_env":{k:os.environ.get(k) for k in (*B.H.CAPS,"PYTHONHASHSEED","OPENBLAS_THREAD_TIMEOUT")},
                "packages":{n:importlib.metadata.version(n) for n in ("numpy","scipy","pyarrow","pydantic","arro3-core")}},
            reader_native_package_present=False,reader_native_distribution_present=False,
            arrow_scope="Opaque bytes only; no Arrow decode",installer_scope="Original executable SHA is observed, not independently retained")


def reader_registration(env):
    require(env.get("GITHUB_ACTIONS")=="true" and env.get("GITHUB_REPOSITORY")=="YotsuBotfds/Chronicler"
        and env.get("GITHUB_EVENT_NAME")=="push" and env.get("GITHUB_REF")=="refs/heads/"+BRANCH
        and env.get("GITHUB_WORKFLOW_REF")=="YotsuBotfds/Chronicler/"+WORKFLOW+"@refs/heads/"+BRANCH
        and env.get("GITHUB_JOB")==JOB_KEY and env.get("GITHUB_RUN_ATTEMPT")=="1"
        and re.fullmatch("[0-9a-f]{40}",env.get("GITHUB_SHA","")) is not None
        and re.fullmatch("[1-9][0-9]*",env.get("GITHUB_RUN_ID","")) is not None,"closed first-attempt audit push required")
    return env["GITHUB_SHA"]


def workflow_contract(root,*,active_required=True):
    template,active=root/TEMPLATE,root/WORKFLOW
    require(not template.is_symlink() and pin(template.read_bytes())["sha256"]==TEMPLATE_SHA,"reader template changed")
    if active_required or active.exists() or active.is_symlink():
        require(not active.is_symlink() and active.read_bytes()==template.read_bytes(),"active reader workflow differs")


def own_source(U,expected):
    C=U.C
    current=subprocess.check_output(["git","-c","core.fsmonitor=false","-C",str(ROOT),"rev-parse","HEAD"],timeout=10,text=True).strip()
    status=subprocess.check_output(["git","-c","core.fsmonitor=false","-C",str(ROOT),"status","--porcelain=v1","--untracked-files=all"],timeout=10)
    require(current==expected and not status,"actual reader source is not clean/exact")
    snapshot=C.git_source.snapshot(ROOT,expected)
    selected={}
    for name in selected_source_names():
        row=snapshot["files"][name]
        path=ROOT/name
        require(not path.is_symlink() and path.is_file() and stat.S_IMODE(path.stat().st_mode)==row["mode"]
            and C.core.digest(path,row["bytes"])=={k:row[k] for k in ("bytes","sha256")},"reader source bytes/modes differ")
        selected[name]=row
    return {"sha":expected,"committed_snapshot":snapshot,"selected_files":selected,
        "scope":"Complete committed Git objects; only selected sparse physical source bytes/modes verified, no full reconstructed worktree claim"}


def selected_source_names():
    return tuple("scripts/"+n for n in PINS)+("scripts/cbf_090_default_artifact_reader.py",
        "tests/test_cbf_090_default_artifact_reader.py","tests/fixtures/cbf_090_default_artifact_publication.json",
        "tests/fixtures/cbf_090_default_identity_inputs.json","AGENTS.md","pyproject.toml","uv.lock",
        "docs/CONTINUATION.md","docs/DEVELOPMENT.md","docs/integration/cbf-090-default-artifact-reader-2026-10-29.md",TEMPLATE,WORKFLOW)


def fetch_metadata(U,transport):
    p=artifact_pin(U);value=transport.metadata(p)["observed"]
    for key,suffix in (("jobs",f"/actions/runs/{RUN}/jobs?per_page=100"),("artifacts",f"/actions/runs/{RUN}/artifacts?per_page=100")):
        with transport.api(suffix) as stream: raw=stream.read(U.B.A.METADATA_LIMIT+1)
        require(len(raw)<=U.B.A.METADATA_LIMIT,"metadata response bound exceeded");value[key]=U.C.core.strict_json(raw)
    value.pop("artifact");validate_metadata(U,value)
    return value


def finalize(U,root,report,started,deadline,quiescent):
    def unexpired():
        return all(U.B.A.utc(v)>datetime.now(timezone.utc) for v in (EXPIRY,*(p.expiry for p in U.B.ARTIFACTS.values())))
    if not unexpired(): report.update(qualified=False,publication_error="original input expiry reached")
    code=U.R.finalize(U.C,root,report,started,deadline,quiescent)
    if not unexpired():
        report.update(qualified=False,publication_error="original input expiry reached during finalization")
        U.R.write(root/"publication/reader-result.json",report)
        return 1
    return code


def negative_publication(root,report,started):
    """Available before authenticated helpers, resource admission or children."""
    report.update(qualified=False,reader_seconds=time.monotonic()-started)
    publication=root/"publication";publication.mkdir(exist_ok=True)
    temporary=publication/"reader-result.json.tmp"
    with temporary.open("w",encoding="utf-8") as stream:
        json.dump(report,stream,indent=2,sort_keys=True,allow_nan=False);stream.write("\n")
        stream.flush();os.fsync(stream.fileno())
    os.replace(temporary,publication/"reader-result.json")


def audit(args):
    require(args.execute is True,"inactive: explicit --execute required")
    source=reader_registration(os.environ);started=time.monotonic();deadline=started+SECONDS
    root=Path(args.evidence).resolve();prefix=Path(args.python).absolute().parent.parent.resolve()
    require(not root.exists() and not root.is_relative_to(ROOT) and not prefix.is_relative_to(ROOT),"fresh external paths required")
    require(not [k for k in os.environ if k.startswith("GIT_") and k!="GIT_PAGER"],"ambient Git override refused")
    root.mkdir(parents=True);(root/"logs").mkdir();(root/"inputs").mkdir()
    report={"qualified":False,"producer":PRODUCER,"run":RUN,"job":JOB,"artifact":ARTIFACT,"reader_source":source,
        "original_archive":{"id":ARTIFACT,"bytes":ARCHIVE_BYTES,"sha256":ARCHIVE_SHA,"expiry":EXPIRY},
        "reader_producer":{"control_sha":source,"run_id":os.environ["GITHUB_RUN_ID"],"run_attempt":"1","job_key":JOB_KEY,
            "event":"push","branch":BRANCH,"workflow_ref":os.environ["GITHUB_WORKFLOW_REF"]},
        "scope":"CBF-to-090 original default exports only; no World/checkpoint/RNG/science/performance/adoption grant"}
    negative_publication(root,report,started)
    U=None;supervisor=None;before=None;stage="authenticate"
    try:
        raw=authenticate();boot=compile_source(raw["arc_output_identity_qualification.py"],SCRIPT.with_name("arc_output_identity_qualification.py"),"_cbf_audit_boot_H")
        supervisor=boot.Supervisor(root,deadline);allowed=os.sched_getaffinity(0);os.sched_setaffinity(0,{min(allowed)})
        env=dict(os.environ,**boot.CAPS,PYTHONHASHSEED="0",PYTHONDONTWRITEBYTECODE="1",PYTHONNOUSERSITE="1",PYTHONOPTIMIZE="0",OPENBLAS_THREAD_TIMEOUT="16")
        for k in tuple(env):
            if k in ("GITHUB_TOKEN","GH_TOKEN","PYTHONPATH","PYTHONHOME","VIRTUAL_ENV") or k.startswith(("PIP_","UV_")):env.pop(k)
        env["PIP_CONFIG_FILE"]=os.devnull
        stage="initial"
        supervisor.admission("initial",12,2);U=load_modules(root,raw);B,C,R=U.B,U.C,U.R
        require(platform.python_version()==B.A.PYTHON and platform.python_implementation()=="CPython"
            and sys.flags.optimize==0 and sys.flags.no_user_site==1 and sys.dont_write_bytecode,"bootstrap reader runtime differs")
        stage="source-object-hydration"
        current=subprocess.check_output(["git","-C",str(ROOT),"rev-parse","HEAD"],timeout=10,text=True).strip();require(current==source,"wrong actual reader HEAD")
        for role,sha in {"reader":source,**B.SOURCES,"producer":PRODUCER}.items():
            supervisor.command("hydrate-"+role,["git","-c","core.fsmonitor=false","-c","gc.auto=0","-c","maintenance.auto=false","fetch","--no-tags","--refetch","--no-filter","--depth=1","origin",sha],env,ROOT)
        before=own_source(U,source)
        R.write(root/"reader-source-before.json",before)
        workflow_contract(ROOT)
        for n in ("uv.lock","pyproject.toml"):
            require((ROOT/n).read_bytes()==C.git_source.read_blob(ROOT,B.SOURCES["candidate"],n),"reader dependency input differs")
        stage="fresh-environment";report["reader_preparation"]=B.A.prepare_environment(root,{"candidate":ROOT},args.python,prefix,env,supervisor)
        stage="original-transfer";transport=B.A.Transport(os.environ.get("GITHUB_TOKEN"),supervisor,deadline)
        metadata0=fetch_metadata(U,transport);R.write(root/"metadata-before.json",metadata0)
        transport.download(artifact_pin(U),root/"inputs/original.zip")
        metadata1=fetch_metadata(U,transport);R.write(root/"metadata-after.json",metadata1)
        require(metadata0==metadata1,"official publication changed during transfer")
        metadata_pins={name:C.core.digest(root/name) for name in ("metadata-before.json","metadata-after.json")}
        context={"source":source,"prefix":str(prefix),"started":started,"deadline":deadline,"metadata_pins":metadata_pins};R.write(root/"context.json",context)
        stage="inspection";supervisor.command("original-byte-inspection",[args.python,"-B",str(SCRIPT),"inspect","--evidence",str(root)],env,root)
        inspected=C.core.read_json(root/"inspection.json");require(inspected.get("qualified") is True,"independent original-byte inspector refused")
        report.update(inspected)
        stage="final-graph";after=own_source(U,source)
        require(supervisor.cleanup_complete and same(after,before),"reader source/cleanup changed")
        R.write(root/"reader-source-after.json",after)
        report["reader_source_snapshots"]={phase:C.core.digest(root/("reader-source-"+phase+".json")) for phase in ("before","after")}
        final_transport=B.A.Transport(os.environ.get("GITHUB_TOKEN"),supervisor,deadline)
        require(fetch_metadata(U,final_transport)==metadata1,"official publication changed during audit")
        require(C.core.digest(root/"inputs/original.zip",ARCHIVE_BYTES)=={"bytes":ARCHIVE_BYTES,"sha256":ARCHIVE_SHA},"final original archive differs")
        uv=report["reader_preparation"]["uv"]
        require(C.core.digest(uv["path"],uv["bytes"])=={k:uv[k] for k in ("bytes","sha256")},"fresh reader installer changed")
        require(authenticate()==raw,"reader utility sources changed")
        verify_utility_view(root,raw);verify_kernel_view(root,raw)
        require(C.core.read_json(root/"context.json")==context and all(C.core.digest(root/n)==v for n,v in metadata_pins.items()),"carried clock/metadata changed")
        require(all(B.A.utc(p.expiry)>datetime.now(timezone.utc) for p in B.ARTIFACTS.values()),"nested input expiry reached")
        require(time.monotonic()<=deadline,"qualification deadline exceeded")
    except BaseException as error:
        report.update(qualified=False,error_stage=stage,error=type(error).__name__,error_message=re.sub(r"https?://\S+","[URL]",str(error))[:2048])
    finally:
        if U is not None:
            return finalize(U,root,report,started,deadline,supervisor.cleanup_complete)
        negative_publication(root,report,started)
    return 1


def inspect(args):
    root=Path(args.evidence).resolve();raw=authenticate()
    # Reopen only the exact already-created read-only view; never reuse modules.
    view=root/"authenticated-utilities/scripts";verify_utility_view(root,raw)
    R=compile_source(raw["native_default_output_artifact_reader.py"],view/"native_default_output_artifact_reader.py","_cbf_inspect_R")
    B=compile_source(raw["cbf_090_default_identity.py"],view/"cbf_090_default_identity.py","_cbf_inspect_B")
    C=R.load_kernels(root/"derived-kernels");verify_kernel_view(root,raw)
    U=Utilities(R,B,C,ArmUtilities(B.WHEELS,B.A.WHEEL_NAME,B.A.NATIVE_MEMBER,B.A.PYTHON,B.H,B.A.validate_wheel))
    context=C.core.read_json(root/"context.json");report={"qualified":False};supervisors=[]
    require(context["source"]==reader_registration(os.environ) and type(context["started"]) in (int,float)
        and math.isfinite(context["started"]) and context["deadline"]==context["started"]+SECONDS
        and time.monotonic()<context["deadline"] and all(C.core.digest(root/n)==v for n,v in context["metadata_pins"].items()),"carried deadline/source/metadata differs")
    try: inspect_archive(U,root,context,report,supervisors)
    except BaseException as error:
        details=R.error_record(error,B.A,C,report.get("phase","inspection"))
        if isinstance(error,Refusal): details["error_message"]=re.sub(r"https?://\S+","[URL]",str(error))[:2048]
        report.update(qualified=False,**details)
    require(all(s.cleanup_complete for s in supervisors),"inspector comparator cleanup unverified")
    verify_utility_view(root,raw);verify_kernel_view(root,raw)
    R.write(root/"inspection.json",report)
    return 0 if report["qualified"] else 1


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__.split("\n\n")[0]);sub=parser.add_subparsers(dest="command")
    sub.add_parser("describe")
    p=sub.add_parser("audit");p.add_argument("--execute",action="store_true");p.add_argument("--python",required=True);p.add_argument("--evidence",required=True)
    p=sub.add_parser("inspect");p.add_argument("--evidence",required=True)
    args=parser.parse_args(argv)
    if args.command=="audit":return audit(args)
    if args.command=="inspect":return inspect(args)
    print(json.dumps({"status":"inactive","producer":PRODUCER,"artifact":ARTIFACT,"bytes":ARCHIVE_BYTES,"sha256":ARCHIVE_SHA,
        "inventory_sha256":INVENTORY_SHA,"worlds_created":0,"original_byte_audit_performed":False}))
    return 0


if __name__=="__main__":raise SystemExit(main())
