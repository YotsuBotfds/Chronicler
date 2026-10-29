#!/usr/bin/env python3
"""Source-only fixed503 outcome adapter; original final A remains closed.

No default command probes a host, installs a wheel or creates a world. This
adapter keeps the qualified scientific27f functions and503 kernels unchanged.
The prospective final-admission interface is deliberately pending root review.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import platform
import resource
import re
import shutil
import sys
import time
from types import MappingProxyType

SCRIPT = Path(__file__).resolve()
sys.path.insert(0, str(SCRIPT.parent))
import wealth_floor_candidate_proof as P
import wealth_floor_production_primer as M
import wealth_floor_baseline_admission as A
import wealth_floor_outcome_admission_v2 as V
import wealth_floor_outcome_checkpoints as K

B, C = P.B, P.C
require, exact = P.require, P.exact
F_FILE = "scripts/cloud_full_gate_qualification.py"
F_SHA256 = "c85de88f9b4afd0f075d00807ec296b36544f4db4c78e30ebb61fa8751f216da"
M_SHA256 = "0a6fdefae4a88be9434c6cb131cbc0187c08f8a61e1d7f8a85829397824e5f16"
ACTIVE_BRANCH = "lead/cloud-wealth-floor-outcome-cohort-20261029"
SMOKE_BRANCH = "lead/cloud-wealth-floor-outcome-worker-smoke-20261029"
WORKFLOW_PATH = ".github/workflows/wealth-floor-outcome-cohort.yml"
SMOKE_WORKFLOW_PATH = ".github/workflows/wealth-floor-outcome-worker-smoke.yml"
TEMPLATE_PATH = "docs/experiments/wealth-floor-outcome-cohort.yml.inactive"
SMOKE_TEMPLATE_PATH = "docs/experiments/wealth-floor-outcome-worker-smoke.yml.inactive"
PREREQUISITE_PATH = "docs/integration/wealth-floor-outcome-prerequisites-reviewed.json"
WORKER_PACKET_PATH = "docs/integration/wealth-floor-outcome-worker-smokes-reviewed.json"
V_SHA256 = "f253f2defe17ae9ec23f922f049a772e82ea507c7ae1ccaf54a2f3a8a0a68590"
WORKFLOW_SHA256 = {'smoke': '0cc71984b30c9c6d5fc219b3f7d3be4dc5052e1c5ec639e44ef45a18ed2248a2', 'full': '2ffb5ab9a10adf900344c8ae961266544d0f3e6ebb4ade7540f10687d9e0bc27'}
MAX_RAW_BYTES = A.MAX_PAYLOAD_BYTES
MAX_RAW_FILES = A.MAX_ENTRIES
COHORT_WALL_SECONDS = 330 * 60
SMOKE_WALL_SECONDS = 80 * 60
JOURNAL_SEGMENT_BYTES = C.MAX_PROGRESS_BYTES
JOURNAL_MAX_SEGMENTS = 16
JOURNAL_MAX_BYTES = JOURNAL_SEGMENT_BYTES * JOURNAL_MAX_SEGMENTS
JOURNAL_MAX_ROW_BYTES = 64 * 1024


class SegmentedJournal:
    """Preserve every frozen C60 event, synchronously, without changing C60.

    The original bound event writer still creates each row. Closed segments and
    the current tail form one ordered log, with 8 MiB per file and 128 MiB total.
    Every read rechecks actual wholefile identities; a write failure latches the
    journal incomplete and cannot be promoted by later successful publication.
    """
    def __init__(self,root,writer,check):
        self.root=Path(root);self.writer=writer;self.check=check
        self.closed=[];self.tail_bytes=0;self.tail_rows=0;self.total_bytes=0
        self.tail_hash=hashlib.sha256();self.last_monotonic=None;self.failed=False;self.sealed=False
        require(not (self.root/'progress.jsonl').exists() and not (self.root/'progress-segments').exists(),"fresh segmented journal required")
        (self.root/'progress-segments').mkdir()
        self.write_index(False)

    def rows(self):
        rows=list(self.closed)
        if self.tail_bytes:
            rows.append(dict(path='progress.jsonl',bytes=self.tail_bytes,rows=self.tail_rows,sha256=self.tail_hash.hexdigest()))
        return rows

    def write_index(self,complete):
        K.durable_json(self.root/'progress-segments/index.json',dict(schema_version=1,kind='wealth-floor-complete-ordered-progress',
            journal_complete=complete and not self.failed,publication_complete=False,segment_byte_limit=JOURNAL_SEGMENT_BYTES,
            aggregate_byte_limit=JOURNAL_MAX_BYTES,segment_count_limit=JOURNAL_MAX_SEGMENTS,row_byte_limit=JOURNAL_MAX_ROW_BYTES,
            total_bytes=self.total_bytes,event_count=sum(row['rows'] for row in self.rows()),segments=self.rows(),
            scope='Every original C60 event in original order; no thinning or omitted resource/admission/ownership/cleanup rows.'))

    def checked_bytes(self,row):
        raw=P.read_bytes(self.root,row['path'],JOURNAL_SEGMENT_BYTES,self.check)
        require(len(raw)==row['bytes'] and hashlib.sha256(raw).hexdigest()==row['sha256'],"ordered journal segment missing or changed")
        return raw

    def event(self,kind,**fields):
        require(not self.failed and not self.sealed,"segmented journal already incomplete or sealed")
        try:
            require(len(B.canonical_bytes(dict(event=kind,monotonic=time.monotonic(),**fields)))<=JOURNAL_MAX_ROW_BYTES-64,"journal event row bound")
            if self.tail_bytes+JOURNAL_MAX_ROW_BYTES>JOURNAL_SEGMENT_BYTES:
                row=self.rows()[-1];self.checked_bytes(row)
                require(len(self.closed)+1<JOURNAL_MAX_SEGMENTS,"ordered journal segment count cap")
                name=f'progress-segments/segment-{len(self.closed):03d}.jsonl'
                require(not (self.root/name).exists(),"journal segment collision")
                (self.root/'progress.jsonl').rename(self.root/name)
                row['path']=name;self.closed.append(row)
                self.tail_bytes=0;self.tail_rows=0;self.tail_hash=hashlib.sha256()
                self.write_index(False)
            require(self.total_bytes+JOURNAL_MAX_ROW_BYTES<=JOURNAL_MAX_BYTES,"ordered journal aggregate cap")
            before=self.tail_bytes
            self.writer(kind,**fields)
            with P.regular(self.root,'progress.jsonl') as (stream,st):
                require(st.st_size>before and st.st_size-before<=JOURNAL_MAX_ROW_BYTES,"partial or oversized journal append")
                stream.seek(before);raw=stream.read(JOURNAL_MAX_ROW_BYTES+1)
            require(len(raw)==st.st_size-before and raw.endswith(b'\n') and raw.count(b'\n')==1,"partial journal row")
            row=P.parse(raw);stamp=row.get('monotonic')
            require(type(row) is dict and set(row)=={'event','monotonic',*fields} and row['event']==kind
                and exact({key:row[key] for key in fields},fields) and type(stamp) in (int,float) and math.isfinite(stamp)
                and (self.last_monotonic is None or stamp>=self.last_monotonic),"original journal event/order differs")
            self.tail_hash.update(raw);self.tail_bytes+=len(raw);self.tail_rows+=1;self.total_bytes+=len(raw);self.last_monotonic=stamp
        except BaseException:
            self.failed=True
            try:self.write_index(False)
            except BaseException:pass
            raise

    def events(self):
        require(not self.failed,"incomplete ordered journal refused")
        last=None
        for segment in self.rows():
            raw=self.checked_bytes(segment);lines=raw.splitlines(keepends=True)
            require(len(lines)==segment['rows'],"journal row count differs")
            for line in lines:
                self.check();require(len(line)<=JOURNAL_MAX_ROW_BYTES and line.endswith(b'\n'),"journal row framing")
                row=P.parse(line);stamp=row.get('monotonic')
                require(type(stamp) in (int,float) and math.isfinite(stamp) and (last is None or stamp>=last),"journal order changed")
                last=stamp;yield row

    def seal(self):
        try:
            require(not self.failed,"incomplete journal cannot seal")
            require(sum(1 for _ in self.events())==sum(row['rows'] for row in self.rows()),"journal event total differs")
            self.write_index(True);self.sealed=True
        except BaseException:
            self.failed=True
            try:self.write_index(False)
            except BaseException:pass
            raise


def install_outcome_journal(supervisor,root):
    journal=SegmentedJournal(root,supervisor.event,supervisor.check)
    supervisor.event=journal.event
    supervisor.outcome_journal=journal
    return supervisor


def scientific_helpers(control):
    """Import only the exact original controller, without invoking its CLI."""
    raw = P.read_bytes(control, F_FILE)
    require(hashlib.sha256(raw).hexdigest() == F_SHA256, "original scientific controller source differs")
    require(hashlib.sha256(P.read_bytes(control, C.LEGACY_FILE)).hexdigest() == C.LEGACY_SHA, "qualified legacy helper differs")
    spec = importlib.util.spec_from_file_location("wealth_fixed_scientific27f", Path(control) / F_FILE)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def work_plan(worldgen, stage, helpers):
    config = helpers.expected(worldgen, stage)
    parents = config["seed_count"]
    # Each original fork loads CP(label+1), advances21 actual ticks, measures20.
    return dict(config=config, parents=parents, forks=config["fork_count"],
        executions=parents+config["fork_count"], physics_ticks=parents*config["turns"]+21*config["fork_count"],
        wall_limit_seconds=SMOKE_WALL_SECONDS if stage == "smoke" else COHORT_WALL_SECONDS,
        entry_disk_gib=20, entry_effective_available_memory_gib=6, running_disk_floor_gib=3,
        running_memory_floor_gib=1, exact_live_tree_cpu_admission=False)


def registration(stage):
    """Must be called before paths, transport, install or scientific imports.

    V2 is the separately named authority explicitly chosen for prospective new
    activations. Original A9de/P13239 remain frozen and are never monkeypatched.
    """
    return V.registration(stage)


def runner_command(python, source, worldgen, output, stage, helpers):
    """Exact original CLI, no baseline argument, exploration or new tuning."""
    return helpers.cohort_command(str(python), Path(source), worldgen, Path(output), stage)


def command_exit(supervisor, label, command, env, cwd, root):
    """C60 returns stdout; its owned child_exit event supplies actual status."""
    supervisor.command(label, command, env, cwd, allowed_exit_codes=(0, 2))
    journal=getattr(supervisor,'outcome_journal',None)
    rows=journal.events() if journal is not None else (P.parse(line) for line in P.read_bytes(root,"progress.jsonl",C.MAX_PROGRESS_BYTES,supervisor.check).splitlines())
    exits=[];cleanups=[]
    for row in rows:
        if row.get('label')==label:
            if row.get('event')=='child_exit':exits.append(row)
            elif row.get('event')=='child_cleanup':cleanups.append(row)
    require(len(exits) == len(cleanups) == 1 and cleanups[0].get("complete") is True
        and cleanups[0].get("cleanup_error") is None and type(exits[0].get("returncode")) is int
        and exits[0]["returncode"] in (0, 2), "unique owned scientific child status required")
    return exits[0]["returncode"]


def assess_records(records, worldgen, stage, native_sha, runner_exit, helpers):
    profile = "subset" if stage == "smoke" else "full"
    assessment = helpers.validate_records(records["run_manifest.json"], records["batch_manifest.json"],
        records["ablation_manifest.json"], records["validate_report_"+profile+".json"],
        records["gate_decision_"+profile+".json"], helpers.expected(worldgen, stage), B.CANDIDATE_SOURCE, native_sha)
    require(type(runner_exit) is int and runner_exit == assessment["gate_exit_code"], "real runner and saved original gate exit disagree")
    return dict(assessment, schema_complete=True, scientific_gate_pass=assessment["gate_pass"],
        schema_smoke_complete=(stage == "smoke"), scientific_exit_code=assessment["gate_exit_code"])


def source_bindings(control):
    rows = P.source_bindings(control)
    for name, expected in ((F_FILE,F_SHA256),("scripts/wealth_floor_production_primer.py",M_SHA256),
        ("scripts/wealth_floor_outcome_admission_v2.py",V_SHA256)):
        raw=P.read_bytes(control,name);require(hashlib.sha256(raw).hexdigest()==expected,"fixed dependency differs")
        rows[name]=dict(bytes=len(raw),sha256=expected)
    raw=P.read_bytes(control,"scripts/wealth_floor_outcome_qualification.py")
    rows["scripts/wealth_floor_outcome_qualification.py"]=dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
    for name in ("scripts/wealth_floor_outcome_checkpoints.py","scripts/wealth_floor_retained_outcome_driver.py"):
        raw=P.read_bytes(control,name);rows[name]=dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
    return rows


def workflow_contract(stage,template,active=None):
    require(B.hash_shape(WORKFLOW_SHA256[stage]) and hashlib.sha256(template).hexdigest()==WORKFLOW_SHA256[stage],"reviewed phase workflow differs")
    require(active is None or active==template,"actual phase workflow must match dormant source byte-for-byte")


def verify_workflow_paths(control,stage):
    template=SMOKE_TEMPLATE_PATH if stage=="smoke" else TEMPLATE_PATH
    active=SMOKE_WORKFLOW_PATH if stage=="smoke" else WORKFLOW_PATH
    path=Path(control)/active
    actual=P.read_bytes(control,active) if path.exists() or path.is_symlink() else None
    workflow_contract(stage,P.read_bytes(control,template),actual)
    return True


def transport_plan(packet):
    producer=packet["proofs"]["baseline_audit"]["producer"]
    A.validate_producer_identity(producer["control_sha"],producer["run_id"],producer["job_id"])
    result={"build":dict(run_id=P.REVIEWED_BUILD["run_id"],artifact_id=P.REVIEWED_BUILD["artifact_id"]),
        "bootstrap":dict(run_id=M.BOOTSTRAP["run_id"],artifact_id=M.BOOTSTRAP["artifact_id"]),
        "primer":dict(run_id=V.REVIEWED_PRIMER["run_id"],artifact_id=V.REVIEWED_PRIMER["artifact_id"]),
        "historical_template":dict(artifact_id=A.ARCHIVES["template"].artifact_id),
        "historical_procedural":dict(artifact_id=A.ARCHIVES["procedural"].artifact_id),
        "baseline_audit_job":dict(job_id=producer["job_id"])}
    require(all(type(value) is int and value>0 for row in result.values() for value in row.values()),"typed fixed transport IDs required")
    return result


def validate_publications(metadata,packet,*,now):
    require(type(metadata) is dict and set(metadata)==set(transport_plan(packet)),"closed fresh publication set required")
    P.validate_publication(metadata["build"],P.registration(),now=now)
    M.validate_bootstrap_publication(metadata["bootstrap"],now=now)
    for worldgen in ("template","procedural"):
        A.validate_publication(metadata["historical_"+worldgen],A.ARCHIVES[worldgen],now)
    audit=packet["proofs"]["baseline_audit"]
    A.validate_completed_job(audit,metadata["baseline_audit_job"],receipt_sha256=V.REVIEWED_PREREQUISITES["baseline_audit"],
        expected_receipt_sha256=V.REVIEWED_PREREQUISITES["baseline_audit"],control_sha=audit["producer"]["control_sha"])
    value=metadata["primer"];pins=V.REVIEWED_PRIMER
    require(type(value) is dict and set(value)=={"run","jobs","artifact"},"closed primer metadata required")
    run,jobs,artifact=value["run"],value["jobs"],value["artifact"]
    require(run.get("id")==pins["run_id"] and type(run.get("id")) is int and run.get("head_sha")==pins["control_sha"]
        and run.get("head_branch")==M.ACTIVE_BRANCH and run.get("path")==M.WORKFLOW_PATH and run.get("run_attempt")==1
        and run.get("status")=="completed" and run.get("conclusion")=="success"
        and run.get("repository",{}).get("full_name")==P.REPOSITORY,"completed qualified primer origin required")
    require(type(jobs) is dict and type(jobs.get("jobs")) is list and len(jobs["jobs"])<=32,"bounded primer jobs")
    matched=[j for j in jobs["jobs"] if type(j.get("id")) is int and j["id"]==pins["job_id"]]
    require(len(matched)==1 and matched[0].get("run_id")==pins["run_id"] and matched[0].get("head_sha")==pins["control_sha"]
        and matched[0].get("status")=="completed" and matched[0].get("conclusion")=="success","completed qualified primer job required")
    require(type(artifact.get("id")) is int and artifact["id"]==pins["artifact_id"]
        and type(artifact.get("size_in_bytes")) is int and artifact["size_in_bytes"]==pins["artifact_bytes"]
        and artifact.get("digest")=="sha256:"+pins["artifact_sha256"] and artifact.get("expired") is False
        and artifact.get("expires_at")==pins["artifact_expires_at"]
        and artifact.get("name")==f"wealth-production-primer-raw-{pins['run_id']}-1"
        and artifact.get("workflow_run",{}).get("id")==pins["run_id"]
        and artifact.get("workflow_run",{}).get("head_sha")==pins["control_sha"],"exact primer raw publication required")
    require(now<P.expiry(pins["artifact_expires_at"]),"primer raw publication expired")
    return True


def load_plan(control,stage):
    registration(stage)
    packet=P.read_json(control,PREREQUISITE_PATH)
    return V.admit_plan(packet,stage,P.read_json(control,WORKER_PACKET_PATH) if stage=="full" else None)


def retained_command(python,source,control,worldgen,output,stage,helpers):
    command=runner_command(python,source,worldgen,output,stage,helpers)
    return [command[0],str(Path(control)/"scripts/wealth_floor_retained_outcome_driver.py"),*command[2:]]


def emit_failed_body_outputs(selection):
    output=os.environ.get("GITHUB_OUTPUT")
    if not output:return
    paths=[row["source_path"] for row in selection["selected"]]
    text="\n".join(paths)
    require(len(text.encode())<=256*1024 and all("\n" not in p and "\r" not in p for p in paths),"failure-only uploader path bound")
    with open(output,"a",encoding="utf-8") as stream:
        stream.write(f"failed_checkpoint_count={len(paths)}\nfailed_checkpoint_paths<<WEALTH_CP_PATHS\n{text}\nWEALTH_CP_PATHS\n")


def invalidate_publication(root,report,failed,stage):
    report.update(qualified=False,smoke_pass=False,error=type(failed).__name__,failure_stage=stage,publication_complete=False)
    (root/"light").mkdir(exist_ok=True)
    for path in (root/"result.json",root/"light/result.json"):C.write_json(path,report)
    C.write_json(root/"light/completion.json",dict(publication_complete=False,error=type(failed).__name__,failure_stage=stage,
        failed_checkpoint_body_publication="Separate best-effort bounded failure artifact; missing/omitted bodies are not claimed preserved."))


def establish_negative_receipts(root,desired):
    """Keep desired science flags in memory until the original finalizer."""
    (root/"light").mkdir(exist_ok=True)
    negative=dict(desired,qualified=False,smoke_pass=False,publication_complete=False)
    for path in (root/"result.json",root/"light/result.json"):C.write_json(path,negative)
    C.write_json(root/"light/completion.json",dict(publication_complete=False,status="incomplete_pending_bounded_finalization"))


def copy_required_light(root,helpers,stage,check):
    """Original F mappings/bounds, allowing already established negatives.

    F.copy_light mkdir() requires a missing directory; this narrow publication
    adapter retains negative receipts while copying the same required sources.
    F's source and all scientific functions/decisions remain unchanged.
    """
    files={};missing=[];total=0
    for relative,source in helpers.light_sources(stage).items():
        check();require(relative not in ("result.json","completion.json","artifact-index.json"),"recursive light mapping refused")
        path=root/source
        if not path.exists():missing.append(relative);continue
        raw=P.read_bytes(root,source,helpers.MAX_FILE_BYTES,check)
        require(total+len(raw)<=helpers.MAX_LIGHT_BYTES and len(files)+1<=helpers.MAX_LIGHT_FILES,"required light bounds exceeded")
        target=root/"light"/relative;target.parent.mkdir(parents=True,exist_ok=True)
        with target.open('xb') as stream:stream.write(raw)
        digest=hashlib.sha256(raw).hexdigest();require(C.sha(target)==digest,"required light copy differs")
        files[relative]=dict(bytes=len(raw),sha256=digest);total+=len(raw)
    index=dict(schema_version=1,kind=helpers.KINDS["light-index"],complete=not missing,missing=missing,file_count=len(files),total_bytes=total,files=files)
    C.write_json(root/"light/artifact-index.json",index)
    return index


def publish_light(root,desired,helpers,stage,check):
    establish_negative_receipts(root,desired)
    return extend_light(root,copy_required_light(root,helpers,stage,check),check)


def extend_light(root,index,check):
    names=("candidate-checkpoint-index.json","candidate-checkpoint-capture.jsonl","checkpoint-retirement.json",
        "checkpoint-retirement.jsonl","source-snapshot-before.json","source-snapshot-after.json","control-sources-before.json",
        "control-sources-after.json","probes/before.json","probes/after.json","runtime-before.json","runtime-after.json",
        "execution-admission.json","execution-deadline.json","failed-checkpoint-body-selection.json","worker-path-evidence.json","progress-segments/index.json")
    for name in names:
        check();path=root/name
        if not path.exists():continue
        raw=P.read_bytes(root,name,32*B.MIB,check)
        require(len(index["files"])<64 and len(raw)<=32*B.MIB,"extended light bounds")
        target=root/"light"/name;target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(raw);index["files"][name]=dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
    index.update(file_count=len(index["files"]),total_bytes=sum(v["bytes"] for v in index["files"].values()))
    require(index["total_bytes"]<=128*B.MIB,"extended light aggregate bound")
    C.write_json(root/"light/artifact-index.json",index)
    return index


def execute(args):
    registered=registration(args.stage)  # Before paths, host IO, install or worlds.
    start=time.monotonic();usage=resource.getrusage(resource.RUSAGE_CHILDREN)
    helpers=scientific_helpers(SCRIPT.parents[1]);plan_config=work_plan(args.worldgen,args.stage,helpers)
    deadline=start+plan_config["wall_limit_seconds"]
    require(sys.platform=="linux" and platform.python_version()==B.PYTHON_VERSION,"registered Linux/Python runtime")
    branch=SMOKE_BRANCH if args.stage=="smoke" else ACTIVE_BRANCH
    require(os.environ.get("GITHUB_REF")=="refs/heads/"+branch and os.environ.get("GITHUB_JOB")==("smoke" if args.stage=="smoke" else "cohort")
        and os.environ.get("GITHUB_RUN_ATTEMPT")=="1"
        and re.fullmatch("[1-9][0-9]*",os.environ.get("GITHUB_RUN_ID",""))
        and re.fullmatch("[0-9a-f]{40}",os.environ.get("GITHUB_SHA","")),"closed first-attempt outcome phase producer")
    workspace=Path(os.environ["GITHUB_WORKSPACE"]).resolve();temporary=Path(os.environ["RUNNER_TEMP"]).resolve()
    control,source,root=SCRIPT.parents[1],Path(args.source).resolve(),Path(args.output).resolve()
    require(control==workspace/"control" and source==workspace/"candidate"
        and root==temporary/f"wealth-outcome-{args.stage}-{args.worldgen}" and len(str(root))<=128,"closed bounded source/evidence paths")
    staging_observation(temporary,args.stage,args.worldgen)
    require(not root.exists(),"fresh outcome output required")
    root.mkdir();(root/"logs").mkdir();(root/"probes").mkdir()
    before=source_bindings(control);C.write_json(root/"control-sources-before.json",before)
    template=SMOKE_TEMPLATE_PATH if args.stage=="smoke" else TEMPLATE_PATH
    actual=SMOKE_WORKFLOW_PATH if args.stage=="smoke" else WORKFLOW_PATH
    workflow_contract(args.stage,P.read_bytes(control,template),P.read_bytes(control,actual))
    report=dict(schema_version=2,kind="wealth-floor-outcome-candidate-v2",stage=args.stage,arm="candidate",worldgen=args.worldgen,
        source_sha=B.CANDIDATE_SOURCE,baseline_source_sha=B.BASELINE_SOURCE,control_sha=os.environ["GITHUB_SHA"],
        github_run_id=os.environ["GITHUB_RUN_ID"],github_run_attempt="1",expected=plan_config["config"],work=plan_config,
        budget_seconds=plan_config["wall_limit_seconds"],execution_complete=False,identities_stable=False,
        gate_pass=False,gate_exit_code=None,qualified=False,smoke_pass=False,original_A_pins_remain_null=True,
        final_historical_reuse_admitted=False,pipeline_publication_pending=True)
    establish_negative_receipts(root,report)
    cancellation=C.Cancellation();cancellation.__enter__()
    supervisor=None;failed=None;stage="deployment";runner_exit=None
    try:
        report["deployment"]=P.hosted_vm_precondition()
        legacy=C.legacy_helpers(control)
        with C.SubreaperLease() as lease:
            supervisor=install_outcome_journal(C.make_supervisor(legacy,root,deadline,lease,cancellation),root)
            supervisor.admission("before_staged_input",12,2)
            available=sorted(os.sched_getaffinity(0));require(len(available)>=2,"two actual CPUs required")
            os.sched_setaffinity(0,set(available[:2]))
            stage="source_and_prerequisite_content"
            admitted=load_plan(control,args.stage);packet=P.parse(admitted.prerequisite_packet)
            metadata=P.read_json(temporary,"wealth-outcome-publication.json",supervisor.check)
            validate_publications(metadata,packet,now=datetime.now(timezone.utc))
            build=P.admit_build(temporary/"wealth-build-input",metadata["build"],now=datetime.now(timezone.utc),check=supervisor.check)
            manifest=P.parse(build.manifest_bytes);shutil.copyfile(build.root/"build-manifest.json",root/"build-manifest.json")
            original_probe=manifest["phases"]["candidate"]["probe"]
            require(exact(packet["proofs"]["native"],{key:original_probe[key] for key in
                ("native_sha256","python","compiled_extension","real_exported_classes","native_pools_created","schemas")})
                and exact(packet["proofs"]["wheel"],manifest["phases"]["candidate"]["wheel"])
                and exact(packet["proofs"]["build_context"]["context"],manifest["phases"]["candidate"]["context"]),
                "typed root proofs differ from actual inspected paired-build payload")
            initial={"source":C.source_snapshot(legacy,source,B.CANDIDATE_SOURCE,supervisor.deadline),
                "control":C.source_snapshot(legacy,control,os.environ["GITHUB_SHA"],supervisor.deadline)}
            require(initial["source"]["crate_tree"]==B.CANDIDATE_CRATE,"candidate crate differs")
            C.write_json(root/"source-snapshot-before.json",initial)
            for name,digest in P.KERNELS.items():
                require(hashlib.sha256(P.read_bytes(source,name)).hexdigest()==digest,"unchanged source503 kernels required")
            env=C.build_environment(temporary,sys.executable)
            for key in list(env):
                if key.startswith(("GITHUB_","RUNNER_","CODEX_","OIC_","UV_")) or key in ("GH_TOKEN","GITHUB_TOKEN"):env.pop(key)
            env.update(PYTHONPATH=str(source/"src"),CHRONICLER_QUIET="1",PYTEST_DISABLE_PLUGIN_AUTOLOAD="1")
            env.pop("CARGO_TARGET_DIR",None);env.pop("PYO3_PYTHON",None)
            stage="fresh_candidate_environment"
            target=temporary/f"wealth-outcome-{args.stage}-{args.worldgen}-env";require(not target.exists(),"fresh source503 runtime required")
            role_env=dict(env,UV_PROJECT_ENVIRONMENT=str(target));python=target/"bin/python"
            supervisor.command("locked-runtime",["uv","sync","--project",str(source),"--frozen","--no-dev","--no-install-project","--python",sys.executable],role_env,control)
            P.recheck_build(build,supervisor.check)
            supervisor.command("candidate-wheel-install",["uv","pip","install","--no-deps","--python",str(python),str(build.root/"wheels/candidate"/B.WHEEL_NAME)],role_env,control)
            def probe(label):
                supervisor.command("native-"+label,[str(python),"-I","-B",str(control/"scripts/wealth_floor_native_build_controller.py"),"probe","--environment-root",str(target),"--out",str(root/"probes"/(label+".json"))],role_env,control)
                value=P.read_json(root,"probes/"+label+".json",supervisor.check)
                require(value["native_sha256"]==P.REVIEWED_BUILD["candidate_native_sha256"] and value["schemas"]==manifest["phases"]["candidate"]["probe"]["schemas"]
                    and value.get("compiled_extension") is True and value.get("real_exported_classes") is True
                    and value.get("native_pools_created")==0 and value.get("source_imports")==[] and value.get("python")==B.PYTHON_VERSION,"current actual compiled API/native differs")
                supervisor.command("runtime-"+label,[str(python),"-B",str(SCRIPT),"--runtime-observation","--out",str(root/("runtime-"+label+".json"))],env,source)
                runtime=M.validate_runtime(P.read_json(root,"runtime-"+label+".json",supervisor.check))
                return value,runtime
            first,runtime_before=probe("before")
            C.write_json(root/"execution-admission.json",dict(registration=registered,prerequisite_packet_sha256=V.ROOT_PREREQUISITE_PACKET_SHA256,
                registration_sha256=B.digest(registered),source_sha=B.CANDIDATE_SOURCE,control_sha=os.environ["GITHUB_SHA"],stage=args.stage,worldgen=args.worldgen,
                admitted_monotonic=time.monotonic(),producer=dict(ref=os.environ["GITHUB_REF"],job_key=os.environ["GITHUB_JOB"],run_id=os.environ["GITHUB_RUN_ID"],attempt="1")))
            C.write_json(root/"execution-deadline.json",dict(work_deadline_monotonic=supervisor.deadline,overall_deadline_monotonic=deadline,scope="Original controller work/final wall scopes; no extra science or retry budget."))
            stage="original_science_with_deferred_cleanup"
            supervisor.admission("before_simulation",20,6)
            runner_exit=command_exit(supervisor,"original-runner",retained_command(python,source,control,args.worldgen,root/"raw",args.stage,helpers),env,source,root)
            second,runtime_after=probe("after")
            require(exact(first,second) and exact(runtime_before,runtime_after),"candidate runtime/native changed")
            stage="original_report_assessment"
            records={Path(name).name:P.read_json(root,path,supervisor.check) for name,path in helpers.report_files(args.stage).items() if name.endswith('.json')}
            assessment=assess_records(records,args.worldgen,args.stage,P.REVIEWED_BUILD["candidate_native_sha256"],runner_exit,helpers)
            retirement=P.read_json(root,"checkpoint-retirement.json",supervisor.check)
            captured=P.parse(P.read_bytes(root,"candidate-checkpoint-index.json",K.MAX_INDEX,supervisor.check))
            require(retirement["retirement_complete"] is True and len(retirement["retired"])==plan_config["config"]["seed_count"]*len(plan_config["config"]["checkpoint_turns"]),"actual captured checkpoint retirement incomplete")
            require(captured["capture_complete"] is True and exact(captured["config"],plan_config["config"])
                and retirement["checkpoint_index_sha256"]==C.sha(root/"candidate-checkpoint-index.json")
                and set(retirement["retired"])=={row["path"] for row in captured["checkpoints"]},"actual capture/retirement lineage binding differs")
            report.update(execution_complete=True,gate_pass=assessment["gate_pass"],gate_exit_code=runner_exit)
            report["checkpoint_evidence"]=dict(index_sha256=C.sha(root/"candidate-checkpoint-index.json"),retirement_sha256=C.sha(root/"checkpoint-retirement.json"),
                scope="Actual per-seed worker-written headers/native/runtime/lineage and wholefile hashes captured before forks, all bodies rechecked before retirement; source-launched Pool2, no independently sampled worker PID/task assignment/live overlap.")
            if args.stage=="smoke":
                C.write_json(root/"worker-path-evidence.json",dict(schema_version=1,kind="wealth-floor-real-worker-checkpoint-contexts",
                    worker_observation_scope="source_launched_pool2_and_real_worker_written_checkpoint_contexts_no_pid_or_overlap_sampling",
                    original_source_sha=B.CANDIDATE_SOURCE,worldgen=args.worldgen,parallel=2,batch_environment=records["batch_manifest.json"]["environment"],
                    parent_validation_hashes=[dict(seed=row["seed"],files=row["files"]) for row in records["batch_manifest.json"]["runs"]],
                    forks=records["ablation_manifest.json"]["forks"],candidate_checkpoints=captured["checkpoints"],
                    checkpoint_index_sha256=report["checkpoint_evidence"]["index_sha256"],checkpoint_retirement_sha256=report["checkpoint_evidence"]["retirement_sha256"],
                    checkpoint_retirement_complete=True,scope="Actual CP header observations and strict restores plus source-launched Pool2; no independent worker PID/assignment/live-overlap observation."))
            stage="source_input_and_cleanup"
            final={"source":C.source_snapshot(legacy,source,B.CANDIDATE_SOURCE,supervisor.deadline),
                "control":C.source_snapshot(legacy,control,os.environ["GITHUB_SHA"],supervisor.deadline)}
            require(exact(initial,final),"source bytes/modes/standing changed")
            C.write_json(root/"source-snapshot-after.json",final)
            P.recheck_build(build,supervisor.check);V.recheck_plan(admitted)
            validate_publications(metadata,packet,now=datetime.now(timezone.utc))
            report["identities_stable"]=True
            report["publication_check_scope"]="Fresh official inputs checked at staging; cached facts/expiry rechecked after work. Completed producer/output artifacts require separate final consumer origin/byte verification."
            supervisor.check(final=True)
        require(supervisor.cleanup_complete and not C.direct_children(),"owned descendants remain")
        supervisor.outcome_journal.seal()
        stage="bounded_publication"
        require(exact(before,source_bindings(control)),"loaded control bytes changed")
        C.write_json(root/"control-sources-after.json",before)
        files=P.inventory(root,max_bytes=MAX_RAW_BYTES,max_files=MAX_RAW_FILES,check=lambda:supervisor.check(final=True),
            exclude=("light","result.json","provenance.json","raw-inventory.json","completion.json"))
        require(not any(n.endswith('.ckpt') for n in files),"successful raw still contains unretired checkpoints")
        inventory=dict(schema_version=1,kind=helpers.KINDS["raw-inventory"],complete=True,file_count=len(files),total_bytes=sum(v['bytes'] for v in files.values()),files=files,
            scope="Original scientific payload plus real capture/retirement/controller metadata; successful checkpoint bodies retired only after durable evidence/all-file recheck.")
        helpers.check_manifest_hashes(root,records["batch_manifest.json"],records["ablation_manifest.json"],inventory,args.stage)
        C.write_json(root/"raw-inventory.json",inventory);report["raw_inventory_sha256"]=C.sha(root/"raw-inventory.json")
        C.write_json(root/"provenance.json",dict(schema_version=2,kind="wealth-floor-candidate-outcome-provenance-v2",source_sha=B.CANDIDATE_SOURCE,
            control_sha=os.environ["GITHUB_SHA"],paired_build_registration=dict(P.registration()),admission_registration=registered,
            before=first,after=second,runtime_before=runtime_before,runtime_after=runtime_after,checkpoint_evidence=report["checkpoint_evidence"],identities_stable=True))
        used=resource.getrusage(resource.RUSAGE_CHILDREN)
        report["measured"]=dict(wall_seconds=time.monotonic()-start,controller_cpu_seconds=time.process_time(),
            waited_children_cpu_seconds=used.ru_utime+used.ru_stime-usage.ru_utime-usage.ru_stime,
            scope="After owned cleanup and raw hashing, before light/receipt publication; no aggregate live-tree CPU or closed end-to-end upload total.")
        report.update(helpers.outcome_flags(args.stage,True,True,report["gate_pass"]))
        light=publish_light(root,report,helpers,args.stage,lambda:supervisor.check(final=True))
        require(light["complete"],"original required light set incomplete")
        report["light_index_sha256"]=C.sha(root/"light/artifact-index.json")
        helpers.finish_receipts(root,report,"result.json",deadline,start)
        require(not report.get("finalization_error"),"original final receipt publication failed")
        supervisor.check(final=True)
        C.write_json(root/"light/completion.json",dict(publication_complete=True,status="pending_completed_producer_and_artifact_verification",
            result_sha256=C.sha(root/"result.json"),light_index_sha256=report["light_index_sha256"],raw_inventory_sha256=report["raw_inventory_sha256"],final_historical_reuse_admitted=False))
        supervisor.check(final=True)
        require(exact(before,source_bindings(control)),"source drift after positive publication")
    except BaseException as exc:
        failed=exc;report.update(error=type(exc).__name__,failure_stage=stage,qualified=False,smoke_pass=False)
        from wealth_floor_hosted_deployment import REFUSAL_CODES
        if getattr(exc,"code",None) in REFUSAL_CODES:report["deployment_refusal_code"]=exc.code
    finally:
        if time.monotonic()>deadline or C.direct_children() or cancellation.cancelled:
            failed=failed or P.ProofRefused("late cleanup/deadline refusal")
        try:cancellation.__exit__(type(failed) if failed else None,failed,None)
        except BaseException as exc:failed=failed or exc
        if failed:
            report.update(qualified=False,smoke_pass=False,error=type(failed).__name__,failure_stage=stage,publication_complete=False)
            try:
                if supervisor is not None and supervisor.cleanup_complete and not C.direct_children():
                    batch=root/("raw/oracle_subset/batch_42" if args.stage=="smoke" else "raw/full_gate/batch_42")
                    selection=K.failure_body_selection(root,batch,plan_config["config"],clock=time.monotonic)
                    emit_failed_body_outputs(selection);report["failed_checkpoint_body_selection"]="failed-checkpoint-body-selection.json"
                else:
                    report["failed_checkpoint_body_publication_error"]="CleanupUnverifiedOrNoSupervisor"
            except BaseException as exc:report["failed_checkpoint_body_publication_error"]=type(exc).__name__
            invalidate_publication(root,report,failed,stage)
    if failed:return 1
    return 0 if args.stage=="smoke" or report["gate_pass"] else 2


def staging_observation(temporary,stage,worldgen,*,clock=time.monotonic):
    row=P.read_json(temporary,"wealth-outcome-preflight.json")
    require(type(row) is dict and set(row)=={"started_monotonic","stage","worldgen","control_sha","run_id","attempt"},"closed outcome staging observation")
    require(row["stage"]==stage and row["worldgen"]==worldgen and row["control_sha"]==os.environ.get("GITHUB_SHA")
        and row["run_id"]==os.environ.get("GITHUB_RUN_ID") and row["attempt"]=="1","staging producer/phase differs")
    start=row["started_monotonic"]
    require(type(start) in (int,float) and math.isfinite(start) and start>0
        and 0<=clock()-start<=P.STAGING_WALL_SECONDS,"180-second pre-transfer/staging window exceeded")
    return row


def preflight(args):
    registration(args.stage)  # All NULL gates refuse before any host/path probe.
    require(args.worldgen in ("template","procedural"),"fixed outcome world generator required")
    branch=SMOKE_BRANCH if args.stage=="smoke" else ACTIVE_BRANCH
    require(os.environ.get("GITHUB_REF")=="refs/heads/"+branch and os.environ.get("GITHUB_RUN_ATTEMPT")=="1","registered first-attempt phase branch")
    require(sys.platform=="linux" and platform.python_version()==B.PYTHON_VERSION,"registered pre-transfer interpreter")
    start=time.monotonic();temporary=Path(os.environ["RUNNER_TEMP"])
    control=SCRIPT.parents[1];plan=load_plan(control,args.stage);packet=P.parse(plan.prerequisite_packet)
    P.hosted_vm_precondition()
    from wealth_floor_build_resources import memory_admission
    require(shutil.disk_usage(temporary).free>=12*1024**3 and memory_admission()["available_bytes"]>=2*1024**3,"pre-transfer12GiB/2GiB admission")
    transport=transport_plan(packet);C.write_json(temporary/"wealth-outcome-transport-plan.json",transport)
    C.write_json(temporary/"wealth-outcome-preflight.json",dict(started_monotonic=start,stage=args.stage,worldgen=args.worldgen,
        control_sha=os.environ["GITHUB_SHA"],run_id=os.environ["GITHUB_RUN_ID"],attempt="1"))
    with open(os.environ["GITHUB_OUTPUT"],"a",encoding="ascii") as stream:
        stream.write(f"build_run_id={P.REVIEWED_BUILD['run_id']}\nbuild_artifact_id={P.REVIEWED_BUILD['artifact_id']}\n")
    return 0


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute",action="store_true")
    parser.add_argument("--registration",action="store_true")
    parser.add_argument("--validate-publication",action="store_true")
    parser.add_argument("--runtime-observation",action="store_true")
    parser.add_argument("--stage",choices=("smoke","full"),default="smoke")
    parser.add_argument("--worldgen",choices=("template","procedural"))
    for key in ("source","output","out"):parser.add_argument("--"+key)
    args=parser.parse_args(argv)
    if args.registration:
        return preflight(args)
    if args.runtime_observation:
        C.write_json(args.out,M.observe_runtime());return 0
    if args.validate_publication:
        registration(args.stage)
        temporary=Path(os.environ["RUNNER_TEMP"]);staging_observation(temporary,args.stage,args.worldgen)
        plan=load_plan(SCRIPT.parents[1],args.stage)
        validate_publications(P.read_json(temporary,"wealth-outcome-publication.json"),P.parse(plan.prerequisite_packet),now=datetime.now(timezone.utc))
        return 0
    if args.execute:
        return execute(args)
    print(json.dumps(dict(status="inactive_source_only",source=B.CANDIDATE_SOURCE,
        production_executions=3700,production_ticks=201400,separate_batch_worker_smoke_executions=12,
        separate_batch_worker_smoke_ticks=668,final_A_pins="unchanged/null",candidate_worlds_admitted=False)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
