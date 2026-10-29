"""Prospective explicit outcome authority, separate from frozen inactive A9de.

Six prerequisite objects and the actual primer are registered for smoke only.
Worker/full packet slots remain NULL. A separate reviewed activation is still
required; source registration alone launches nothing. This
module performs pure content admission; it probes no host and launches nothing.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import sys
from types import MappingProxyType

sys.path.insert(0,str(Path(__file__).resolve().parent))
import wealth_floor_baseline_admission as A
import wealth_floor_candidate_proof as P
import wealth_floor_production_primer as M
import wealth_floor_outcome_checkpoints as K

B = P.B
require, exact = P.require, P.exact
REVIEWED_PREREQUISITES = MappingProxyType({'baseline_audit': '0520cfae02607dcf3153ab721b274e16a5e8d7fd94a5d0da09c3ffd3610791ca', 'build_context': '80eee397c86daf6452abf495db9f8414e45b6fcfc6f376ab13b5dfe694ac7000', 'checkpoint': 'f7dc1cbdfc26356dd3fef4832ab61b9dd8c865478d259695908de63b9333494e', 'determinism': 'f7dc1cbdfc26356dd3fef4832ab61b9dd8c865478d259695908de63b9333494e', 'native': 'b7318023fe7856ca8ef29cf3969e2e5db3ad6c856053fc5263796710620519e1', 'wheel': 'e0fe8cc107fdf501261c02763884ec047b3624be98ac60dab19cd83c5cc44e8e'})
PREREQUISITE_KEYS = frozenset(("baseline_audit","native","wheel","build_context","checkpoint","determinism"))
WORKER_KEYS = frozenset(("template","procedural"))
PRIMER_KEYS = frozenset(("control_sha","run_id","job_id","attempt","artifact_id","artifact_bytes",
    "artifact_sha256","artifact_expires_at","completion_sha256","proof_sha256"))
ROOT_PREREQUISITE_PACKET_SHA256 = '2e80a6cef44b166c27053954ea078668b9ce5fb4a4e1472e3e88f0e77c275999'
ROOT_WORKER_SMOKE_PACKET_SHA256 = None
REVIEWED_PRIMER = MappingProxyType({'artifact_bytes': 142839893, 'artifact_expires_at': '2026-11-28T06:32:03Z', 'artifact_id': 12878510742, 'artifact_sha256': '2507464994956018fabb37fc89c001d08c13882375e1a47e0e5f81d576b5ed74', 'attempt': 1, 'completion_sha256': '22ab852023addacc8007819d111b8f4a73aeae5bb8a0e54023ba9f62345836f6', 'control_sha': '4ed374ce7f0a8efdc99d1e9392a5b41d3fa65a38', 'job_id': 123299181396, 'proof_sha256': 'f7dc1cbdfc26356dd3fef4832ab61b9dd8c865478d259695908de63b9333494e', 'run_id': 40829185023})
REVIEWED_WORKER_SMOKES = MappingProxyType(dict(template=None, procedural=None))
_SEAL = object()
ROOT_REVIEWS = MappingProxyType(dict(build="72e545308da0cf24d23113e350adf388f75de230ba296453a87eb7b6ba8920a6",
    bootstrap="208b35e77f662d182984cc772ab6281fbe906d950e9a6a6858246716c2d37196",
    primer="c39522453f8b36b4bed5f34dfda38fbf7997952b909c7ff0270dbffa016c0208",
    baseline_audit="8aef28bfd40a95165518e4572ba7045878d8f0abf18b22b31f2ac24c891a2a29"))


@dataclass(frozen=True)
class AdmittedOutcomePlan:
    stage: str
    prerequisite_packet: bytes
    worker_smoke_packet: bytes | None
    registration_bytes: bytes
    _seal: object


def registration(stage):
    require(stage in ("smoke", "full"), "closed outcome phase required")
    require(set(REVIEWED_PREREQUISITES)==PREREQUISITE_KEYS and set(REVIEWED_WORKER_SMOKES)==WORKER_KEYS
        and set(REVIEWED_PRIMER)==PRIMER_KEYS,"closed prerequisite/worker/primer registration key sets required")
    require(all(B.hash_shape(v) for v in REVIEWED_PREREQUISITES.values())
        and B.hash_shape(ROOT_PREREQUISITE_PACKET_SHA256), "V2 six prerequisite/root packet pins remain NULL; no outcome worlds admitted")
    require(all(v is not None for v in REVIEWED_PRIMER.values()), "reviewed late-primer producer remains pending")
    for key in ("run_id", "job_id", "attempt", "artifact_id", "artifact_bytes"):
        require(type(REVIEWED_PRIMER[key]) is int and REVIEWED_PRIMER[key] > 0, "primer producer numeric identity")
    require(REVIEWED_PRIMER["attempt"] == 1 and type(REVIEWED_PRIMER["control_sha"]) is str
        and len(REVIEWED_PRIMER["control_sha"]) == 40 and all(c in "0123456789abcdef" for c in REVIEWED_PRIMER["control_sha"]), "primer source/attempt identity")
    for key in ("artifact_sha256", "completion_sha256", "proof_sha256"):
        require(B.hash_shape(REVIEWED_PRIMER[key]), "primer publication digest")
    P.expiry(REVIEWED_PRIMER["artifact_expires_at"])
    if stage == "full":
        require(B.hash_shape(ROOT_WORKER_SMOKE_PACKET_SHA256) and all(B.hash_shape(v) for v in REVIEWED_WORKER_SMOKES.values()),
            "two real batch-worker smoke producers/coverage remain unreviewed; full cohort refused")
    return dict(schema_version=2, stage=stage, prerequisite_sha256=dict(REVIEWED_PREREQUISITES),
        prerequisite_packet_sha256=ROOT_PREREQUISITE_PACKET_SHA256, primer=dict(REVIEWED_PRIMER),
        worker_smoke_packet_sha256=ROOT_WORKER_SMOKE_PACKET_SHA256 if stage == "full" else None,
        worker_smoke_sha256=dict(REVIEWED_WORKER_SMOKES) if stage == "full" else None)


def validate_prerequisite_packet(packet):
    require(type(packet) is dict and set(packet) == {"schema_version", "kind", "baseline_source", "baseline_crate",
        "candidate_source", "candidate_crate", "build_registration", "proofs", "primer", "root_reviews"}, "closed V2 prerequisite packet")
    require(type(packet["schema_version"]) is int and packet["schema_version"] == 2
        and packet["kind"] == "wealth-floor-outcome-prerequisites-v2", "V2 prerequisite packet schema")
    for key, value in dict(baseline_source=B.BASELINE_SOURCE, baseline_crate=B.BASELINE_CRATE,
        candidate_source=B.CANDIDATE_SOURCE, candidate_crate=B.CANDIDATE_CRATE).items():
        require(packet[key] == value, "fixed outcome source pair differs")
    require(exact(packet["build_registration"], dict(P.registration())), "real paired build registration differs")
    require(exact(packet["root_reviews"],dict(ROOT_REVIEWS)),"qualified root prerequisite reviews differ; no activation grant inferred")
    proofs = packet["proofs"]
    require(type(proofs) is dict and set(proofs) == set(REVIEWED_PREREQUISITES)
        and all(type(value) is dict for value in proofs.values()), "six exact prerequisite proof objects required")
    require(all(hashlib.sha256(A.json_bytes(proofs[key])).hexdigest() == digest for key,digest in REVIEWED_PREREQUISITES.items()), "root-sealed prerequisite proof digest differs")
    native=proofs["native"]
    require(set(native)=={"native_sha256","python","compiled_extension","real_exported_classes","native_pools_created","schemas"}
        and native["native_sha256"]==P.REVIEWED_BUILD["candidate_native_sha256"] and native["python"]==B.PYTHON_VERSION
        and native["compiled_extension"] is True and native["real_exported_classes"] is True
        and type(native["native_pools_created"]) is int and native["native_pools_created"]==0,"typed actual compiled-native proof required")
    require(type(native["schemas"]) is dict and set(native["schemas"])=={"AgentSimulator","EcologySimulator","PoliticsSimulator"},"three real compiled class schemas required")
    for schema in native["schemas"].values():
        require(type(schema) is dict and set(schema)=={"version","fingerprint","schema_sha256"}
            and type(schema["version"]) is int and schema["version"]==1 and type(schema["fingerprint"]) is str
            and len(schema["fingerprint"])==16 and all(c in "0123456789abcdef" for c in schema["fingerprint"])
            and B.hash_shape(schema["schema_sha256"]),"typed compiled checkpoint schema required")
    wheel=proofs["wheel"]
    require(set(wheel)=={"filename","bytes","sha256","native_member","native_bytes","native_sha256"}
        and wheel["filename"]==B.WHEEL_NAME and wheel["sha256"]==P.REVIEWED_BUILD["candidate_wheel_sha256"]
        and wheel["native_member"]==B.NATIVE_MEMBER and wheel["native_sha256"]==native["native_sha256"]
        and type(wheel["bytes"]) is int and 0<wheel["bytes"]<=B.MAX_WHEEL_BYTES
        and type(wheel["native_bytes"]) is int and 0<wheel["native_bytes"]<=64*B.MIB,"typed whole-wheel/native proof required")
    A.validate_build_bridge(proofs["build_context"])
    context=proofs["build_context"]
    require(context["candidate_native_sha256"] == P.REVIEWED_BUILD["candidate_native_sha256"]
        and context["baseline_context_sha256"] == context["candidate_context_sha256"] == P.REVIEWED_BUILD["context_sha256"],
        "qualified candidate native/common build context differs")
    primer = packet["primer"]
    require(type(primer) is dict and set(primer) == {"publication", "executions", "physics_ticks", "own_checkpoints",
        "actual_affinity_cpu_count", "logical_cpu_count", "caps", "serial_repeat_scope", "publication_complete"}, "closed late-primer scope")
    require(exact(primer["publication"], dict(REVIEWED_PRIMER)) and primer["publication_complete"] is True
        and primer["serial_repeat_scope"] == "serial_a_b_subprocesses_not_concurrent_worker_coverage", "reviewed completed primer binding")
    for key,value in dict(executions=19,physics_ticks=3097,own_checkpoints=13,actual_affinity_cpu_count=2,logical_cpu_count=2).items():
        require(type(primer[key]) is int and primer[key] == value, "fixed late-primer/runtime scope differs")
    require(exact(primer["caps"], {key:"1" for key in M.THREAD_KEYS}), "late-primer caps1 required")
    for key in ("checkpoint","determinism"):
        mechanical=proofs[key]
        require(B.digest(mechanical)==REVIEWED_PRIMER["proof_sha256"]
            and mechanical.get("kind")=="wealth-floor-production-runtime-primer" and mechanical.get("status")=="proof_complete_pending_job"
            and exact(mechanical.get("producer"),dict(control_sha=REVIEWED_PRIMER["control_sha"],run_id=str(REVIEWED_PRIMER["run_id"]),run_attempt="1",job_key="primer"))
            and mechanical.get("executions_registered")==19 and mechanical.get("physics_ticks_registered")==3097,"typed original mechanical proof/producer required")
        M.validate_checkpoint_report(mechanical.get("checkpoint"))
        for worldgen in ("template","procedural"):
            result=mechanical.get(worldgen,{})
            require(result.get("status")=="PASS" and result.get("independent_runs")==2 and result.get("physics_ticks")==400
                and result.get("execution_scope")==M.REPEAT_EXECUTION_SCOPE and result.get("explicit_parallel")==2,"original serial repeated-seed scope required")
            M.validate_runtime(result.get("runtime"))
    return True


def validate_worker_smoke_packet(packet):
    require(type(packet) is dict and set(packet) == {"schema_version", "kind", "candidate_source", "candidate_native_sha256", "worlds"}
        and type(packet["schema_version"]) is int and packet["schema_version"] == 2
        and packet["kind"] == "wealth-floor-real-batch-worker-smokes-v2"
        and packet["candidate_source"] == B.CANDIDATE_SOURCE
        and packet["candidate_native_sha256"] == P.REVIEWED_BUILD["candidate_native_sha256"], "closed real-worker smoke packet")
    worlds=packet["worlds"]
    require(type(worlds) is dict and set(worlds) == {"template","procedural"}, "both original worker schema smokes required")
    for worldgen,row in worlds.items():
        require(type(row) is dict and B.digest(row) == REVIEWED_WORKER_SMOKES[worldgen], "root-sealed worker-smoke proof differs")
        require(row.get("worldgen") == worldgen and row.get("status") == "schema_complete"
            and row.get("publication_complete") is True and row.get("producer_conclusion") == "success"
            and row.get("source_sha") == B.CANDIDATE_SOURCE and row.get("native_sha256") == packet["candidate_native_sha256"]
            and row.get("worker_path") == "unchanged_source503_subset_batch_pool2", "completed actual worker-path proof required")
        producer=row.get("producer")
        require(type(producer) is dict and set(producer)=={"control_sha","run_id","job_id","attempt","job_key"}
            and type(producer["control_sha"]) is str and len(producer["control_sha"])==40
            and all(c in "0123456789abcdef" for c in producer["control_sha"])
            and all(type(producer[k]) is int and producer[k]>0 for k in ("run_id","job_id","attempt"))
            and producer["attempt"]==1 and producer["job_key"]=="smoke","root-sealed worker-smoke producer identity required")
        require(exact(row.get("caps"),{key:"1" for key in M.THREAD_KEYS}),"worker-smoke numerical caps1 required")
        for key,value in dict(parents=2,forks=4,executions=6,physics_ticks=334,turns=125,parallel=2,actual_affinity_cpu_count=2,logical_cpu_count=2).items():
            require(type(row.get(key)) is int and row[key] == value, "original worker-smoke coverage differs")
        require(type(row.get("scientific_gate_pass")) is bool and type(row.get("scientific_exit_code")) is int
            and row["scientific_exit_code"] == (0 if row["scientific_gate_pass"] else 2), "preserved smoke scientific decision required")
        require(row.get("worker_observation_scope")=="source_launched_pool2_and_real_worker_written_checkpoint_contexts_no_pid_or_overlap_sampling"
            and B.hash_shape(row.get("checkpoint_index_sha256")) and B.hash_shape(row.get("checkpoint_retirement_sha256"))
            and row.get("checkpoint_retirement_complete") is True,"actual checkpoint evidence before retirement required")
        checkpoints=row.get("candidate_checkpoints")
        require(type(checkpoints) is list and len(checkpoints)==2,"both actual per-seed worker checkpoints required")
        for checkpoint,seed in zip(checkpoints,(42,43)):
            require(type(checkpoint) is dict and checkpoint.get("seed")==seed and checkpoint.get("turn")==101
                and checkpoint.get("path")==f"raw/oracle_subset/batch_42/seed_{seed}/checkpoint_turn_101.ckpt"
                and type(checkpoint.get("bytes")) is int and 0<checkpoint["bytes"]<=K.MAX_CHECKPOINT
                and B.hash_shape(checkpoint.get("sha256")) and checkpoint.get("strict_current_identity_matches") is True,"actual candidate-owned worker checkpoint row required")
            K.validate_header(checkpoint.get("header"),dict(turns=125,regions=32 if worldgen=="procedural" else 8,civs=10 if worldgen=="procedural" else 4),seed,101)
    return True


def admit_plan(prerequisite_packet, stage, worker_smoke_packet=None):
    registered=registration(stage)  # Before interpreting any untrusted packet.
    raw=B.canonical_bytes(prerequisite_packet)
    require(hashlib.sha256(raw).hexdigest() == ROOT_PREREQUISITE_PACKET_SHA256, "root prerequisite packet differs")
    validate_prerequisite_packet(prerequisite_packet)
    smoke_raw=None
    if stage == "full":
        smoke_raw=B.canonical_bytes(worker_smoke_packet)
        require(hashlib.sha256(smoke_raw).hexdigest() == ROOT_WORKER_SMOKE_PACKET_SHA256, "root actual-worker packet differs")
        validate_worker_smoke_packet(worker_smoke_packet)
    else:
        require(worker_smoke_packet is None, "smoke phase never asserts full-phase worker admission")
    return AdmittedOutcomePlan(stage,raw,smoke_raw,B.canonical_bytes(registered),_SEAL)


def recheck_plan(plan):
    require(type(plan) is AdmittedOutcomePlan and plan._seal is _SEAL, "factory-admitted V2 outcome plan required")
    require(plan.registration_bytes == B.canonical_bytes(registration(plan.stage)), "V2 source registration changed")
    return admit_plan(P.parse(plan.prerequisite_packet),plan.stage,
        P.parse(plan.worker_smoke_packet) if plan.worker_smoke_packet is not None else None)
