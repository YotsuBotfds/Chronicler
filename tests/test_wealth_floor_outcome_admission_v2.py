"""Pure V2 authority contracts; synthetic packets never authorize real work."""
from copy import deepcopy
from dataclasses import FrozenInstanceError
import hashlib
from types import MappingProxyType, SimpleNamespace

import pytest
from scripts import wealth_floor_outcome_admission_v2 as V
from scripts import wealth_floor_production_primer as M
from scripts import wealth_floor_outcome_checkpoints as K


PROOF_KEYS = {"baseline_audit", "native", "wheel", "build_context", "checkpoint", "determinism"}


def _checkpoint_report():
    worlds=[]
    for plan in M.plans():
        rows=[]
        for turn in plan["checkpoint_turns"]:
            rows.append(dict(turn=turn,path=f"checkpoints/{plan['worldgen']}/straight/checkpoint_turn_{turn}.ckpt",
                bytes=100,sha256="c"*64,identity_matches=True,
                header=dict(exact=True,seed=42,turn=turn,identity=dict(native=dict(sha256=V.P.REVIEWED_BUILD["candidate_native_sha256"])),
                    run_config=dict(agent_mode="hybrid"),sections=[dict(name="python"),dict(name="native.agent.0")]),
                comparison=dict(status="PASS",expected_files=2,actual_files=2,keys_sha256="d"*64,
                    expected_outputs_sha256="e"*64,actual_outputs_sha256="e"*64,mismatches=[])))
        worlds.append(dict(plan=plan,checkpoints=rows))
    return dict(runtime=dict(python="3.13.17",logical_cpu_count=2,affinity=[0,1],caps={k:"1" for k in M.THREAD_KEYS}),
        source_sha=V.B.CANDIDATE_SOURCE,native_sha256=V.P.REVIEWED_BUILD["candidate_native_sha256"],worlds=worlds,executions=15,physics_ticks=2297)


def _worker_checkpoint(worldgen,seed):
    return dict(seed=seed,turn=101,path=f"raw/oracle_subset/batch_42/seed_{seed}/checkpoint_turn_101.ckpt",bytes=100,
        sha256="a"*64,strict_current_identity_matches=True,header=dict(format="chronicler-run-checkpoint",version=1,exact=True,
            seed=seed,turn=101,num_turns=125,start_turn=0,lineage=[],
            identity=dict(source=dict(git_sha=V.B.CANDIDATE_SOURCE,package_digest=K.PACKAGE),native=dict(sha256=V.P.REVIEWED_BUILD["candidate_native_sha256"]),
                environment=dict(python="3.13.17",implementation="CPython",affinity_cpu_count=2,thread_env=dict(K.THREADS))),
            world=dict(regions=32 if worldgen=="procedural" else 8,civilizations=10 if worldgen=="procedural" else 4),
            run_config=dict(agent_mode="hybrid",validation_sidecar=True,lineage=[],resume_info=None),
            sections=[dict(name="python"),dict(name="native.agent.0")] ))


def _hash(value):
    return hashlib.sha256(V.B.canonical_bytes(value)).hexdigest()


def _pin_prerequisite(monkeypatch, packet, *, proofs=True):
    if proofs:
        monkeypatch.setattr(V, "REVIEWED_PREREQUISITES", MappingProxyType({
            key: _hash(value) for key, value in packet["proofs"].items()
        }))
    monkeypatch.setattr(V, "ROOT_PREREQUISITE_PACKET_SHA256", _hash(packet))


def _pin_workers(monkeypatch, packet):
    monkeypatch.setattr(V, "REVIEWED_WORKER_SMOKES", MappingProxyType({
        key: _hash(value) for key, value in packet["worlds"].items()
    }))
    monkeypatch.setattr(V, "ROOT_WORKER_SMOKE_PACKET_SHA256", _hash(packet))


@pytest.fixture
def closed_registry(monkeypatch):
    monkeypatch.setattr(V,"REVIEWED_PREREQUISITES",MappingProxyType({key:None for key in PROOF_KEYS}))
    monkeypatch.setattr(V,"ROOT_PREREQUISITE_PACKET_SHA256",None)
    monkeypatch.setattr(V,"ROOT_WORKER_SMOKE_PACKET_SHA256",None)
    monkeypatch.setattr(V,"REVIEWED_PRIMER",MappingProxyType({key:None for key in V.PRIMER_KEYS}))
    monkeypatch.setattr(V,"REVIEWED_WORKER_SMOKES",MappingProxyType({key:None for key in V.WORKER_KEYS}))


@pytest.fixture
def registered(monkeypatch,closed_registry):
    """Synthetic reviewed content, with real fixed source/native identities.

    Only the content-context digest is fixture-registered in the paired-build
    pins. No compiler, artifact transport, publication or scientific proof runs.
    """
    context = dict(unknown=[], rustc="fixture rust", cargo="fixture cargo",
        maturin="fixture maturin", uv="fixture uv", target="fixture target",
        flags={key: None for key in ("RUSTFLAGS", "CARGO_ENCODED_RUSTFLAGS", "RUSTDOCFLAGS", "CARGO_BUILD_TARGET")},
        linker=dict(version="fixture linker", executable_sha256="1" * 64))
    build = dict(V.P.REVIEWED_BUILD)
    build["context_sha256"] = _hash(context)
    monkeypatch.setattr(V.P, "REVIEWED_BUILD", MappingProxyType(build))
    bridge = dict(mode="common_context_exact_rebuild",
        baseline_source=V.B.BASELINE_SOURCE, baseline_crate=V.B.BASELINE_CRATE,
        candidate_source=V.B.CANDIDATE_SOURCE, candidate_crate=V.B.CANDIDATE_CRATE,
        context=context, baseline_context_sha256=_hash(context), candidate_context_sha256=_hash(context),
        rebuilt_baseline_native_sha256=V.B.OLD_NATIVE,
        candidate_native_sha256=build["candidate_native_sha256"])
    proofs = {key: dict(fixture_only=key, status="synthetic_root_review") for key in PROOF_KEYS}
    proofs["build_context"] = bridge
    publication = dict(control_sha="c" * 40, run_id=701, job_id=702, attempt=1,
        artifact_id=703, artifact_bytes=4096, artifact_sha256="d" * 64,
        artifact_expires_at="2099-11-28T00:00:00Z", completion_sha256="e" * 64, proof_sha256="f" * 64)
    checkpoint=_checkpoint_report()
    mechanics=dict(kind="wealth-floor-production-runtime-primer",status="proof_complete_pending_job",executions_registered=19,physics_ticks_registered=3097,
        producer=dict(control_sha=publication["control_sha"],run_id=str(publication["run_id"]),run_attempt="1",job_key="primer"),checkpoint=checkpoint)
    for worldgen in ("template","procedural"):
        mechanics[worldgen]=dict(status="PASS",independent_runs=2,physics_ticks=400,execution_scope=M.REPEAT_EXECUTION_SCOPE,
            explicit_parallel=2,runtime=deepcopy(checkpoint["runtime"]))
    publication["proof_sha256"]=_hash(mechanics)
    proofs["checkpoint"]=deepcopy(mechanics);proofs["determinism"]=deepcopy(mechanics)
    proofs["native"]=dict(native_sha256=build["candidate_native_sha256"],python="3.13.17",compiled_extension=True,
        real_exported_classes=True,native_pools_created=0,schemas={name:dict(version=1,fingerprint="1"*16,schema_sha256="2"*64)
        for name in ("AgentSimulator","EcologySimulator","PoliticsSimulator")})
    proofs["wheel"]=dict(filename=V.B.WHEEL_NAME,bytes=4096,sha256=build["candidate_wheel_sha256"],
        native_member=V.B.NATIVE_MEMBER,native_bytes=8192,native_sha256=build["candidate_native_sha256"])
    packet = dict(schema_version=2, kind="wealth-floor-outcome-prerequisites-v2",
        baseline_source=V.B.BASELINE_SOURCE, baseline_crate=V.B.BASELINE_CRATE,
        candidate_source=V.B.CANDIDATE_SOURCE, candidate_crate=V.B.CANDIDATE_CRATE,
        build_registration=dict(V.P.registration()), proofs=proofs,root_reviews=dict(V.ROOT_REVIEWS),
        primer=dict(publication=publication, executions=19, physics_ticks=3097, own_checkpoints=13,
            actual_affinity_cpu_count=2, logical_cpu_count=2, caps={key: "1" for key in M.THREAD_KEYS},
            serial_repeat_scope="serial_a_b_subprocesses_not_concurrent_worker_coverage", publication_complete=True))
    monkeypatch.setattr(V, "REVIEWED_PRIMER", MappingProxyType(publication))
    _pin_prerequisite(monkeypatch, packet)
    worlds = {}
    for index, worldgen in enumerate(("template", "procedural")):
        worlds[worldgen] = dict(worldgen=worldgen, status="schema_complete", publication_complete=True,
            producer_conclusion="success", source_sha=V.B.CANDIDATE_SOURCE,
            native_sha256=build["candidate_native_sha256"], worker_path="unchanged_source503_subset_batch_pool2",
            parents=2, forks=4, executions=6, physics_ticks=334, turns=125, parallel=2,
            actual_affinity_cpu_count=2, logical_cpu_count=2, caps={key: "1" for key in M.THREAD_KEYS},
            scientific_gate_pass=False, scientific_exit_code=2,
            producer=dict(control_sha="a" * 40, run_id=801, job_id=802 + index, attempt=1, job_key="smoke"),
            worker_observation_scope="source_launched_pool2_and_real_worker_written_checkpoint_contexts_no_pid_or_overlap_sampling",
            checkpoint_index_sha256="2"*64,checkpoint_retirement_sha256="3"*64,checkpoint_retirement_complete=True,
            candidate_checkpoints=[_worker_checkpoint(worldgen,seed) for seed in (42,43)])
    workers = dict(schema_version=2, kind="wealth-floor-real-batch-worker-smokes-v2",
        candidate_source=V.B.CANDIDATE_SOURCE, candidate_native_sha256=build["candidate_native_sha256"], worlds=worlds)
    return SimpleNamespace(packet=packet, workers=workers, publication=publication)


@pytest.mark.parametrize("stage", ["smoke", "full"])
def test_null_source_registration_refuses_before_packet_processing(monkeypatch, stage,closed_registry):
    assert set(V.REVIEWED_PREREQUISITES) == PROOF_KEYS
    assert all(value is None for value in V.REVIEWED_PREREQUISITES.values())
    assert all(value is None for value in V.REVIEWED_PRIMER.values())
    assert all(value is None for value in V.REVIEWED_WORKER_SMOKES.values())
    assert V.ROOT_PREREQUISITE_PACKET_SHA256 is V.ROOT_WORKER_SMOKE_PACKET_SHA256 is None

    def forbidden(*_args, **_kwargs):
        pytest.fail("unreviewed registration interpreted packet content")

    monkeypatch.setattr(V.B, "canonical_bytes", forbidden)
    monkeypatch.setattr(V, "validate_prerequisite_packet", forbidden)
    with pytest.raises(V.P.ProofRefused, match="remain NULL"):
        V.admit_plan(object(), stage, object())


def test_smoke_gate_needs_prerequisites_but_no_worker_claim(registered):
    plan = V.admit_plan(registered.packet, "smoke")
    assert plan.stage == "smoke" and plan.worker_smoke_packet is None
    assert plan.prerequisite_packet == V.B.canonical_bytes(registered.packet)
    assert V.recheck_plan(plan).prerequisite_packet == plan.prerequisite_packet
    with pytest.raises(FrozenInstanceError):
        plan.stage = "full"
    with pytest.raises(V.P.ProofRefused, match="full cohort refused"):
        V.admit_plan(registered.packet, "full")
    with pytest.raises(V.P.ProofRefused, match="smoke phase"):
        V.admit_plan(registered.packet, "smoke", registered.workers)


@pytest.mark.parametrize("gate_pass", [False, True])
def test_full_gate_preserves_scientific_decision_as_schema_coverage(registered, monkeypatch, gate_pass):
    for row in registered.workers["worlds"].values():
        row["scientific_gate_pass"] = gate_pass
        row["scientific_exit_code"] = 0 if gate_pass else 2
    _pin_workers(monkeypatch, registered.workers)
    plan = V.admit_plan(registered.packet, "full", registered.workers)
    admitted = V.P.parse(plan.worker_smoke_packet)
    assert set(admitted["worlds"]) == {"template", "procedural"}
    assert all(row["scientific_gate_pass"] is gate_pass and row["scientific_exit_code"] == (0 if gate_pass else 2)
               for row in admitted["worlds"].values())
    assert V.recheck_plan(plan) == plan


def test_proof_object_digests_are_separate_from_native_wheel_context_fingerprints(registered):
    proofs=registered.packet["proofs"]
    assert V.REVIEWED_PREREQUISITES["native"]==_hash(proofs["native"])!=proofs["native"]["native_sha256"]
    assert V.REVIEWED_PREREQUISITES["wheel"]==_hash(proofs["wheel"])!=proofs["wheel"]["sha256"]
    assert V.REVIEWED_PREREQUISITES["build_context"]==_hash(proofs["build_context"])!=proofs["build_context"]["candidate_context_sha256"]


@pytest.mark.parametrize("fault",["native_identity","native_available_only","native_instance_created","schema_missing","schema_version_alias",
    "wheel_identity","wheel_foreign_native","wheel_member","wheel_size_alias","root_review"])
def test_typed_native_wheel_and_root_proofs_refuse_semantic_misregistration(registered,monkeypatch,fault):
    packet=deepcopy(registered.packet)
    if fault=="native_identity":packet["proofs"]["native"]["native_sha256"]="3"*64
    elif fault=="native_available_only":packet["proofs"]["native"]["real_exported_classes"]=False
    elif fault=="native_instance_created":packet["proofs"]["native"]["native_pools_created"]=1
    elif fault=="schema_missing":packet["proofs"]["native"]["schemas"].pop("EcologySimulator")
    elif fault=="schema_version_alias":packet["proofs"]["native"]["schemas"]["AgentSimulator"]["version"]=True
    elif fault=="wheel_identity":packet["proofs"]["wheel"]["sha256"]="3"*64
    elif fault=="wheel_foreign_native":packet["proofs"]["wheel"]["native_sha256"]=V.B.OLD_NATIVE
    elif fault=="wheel_member":packet["proofs"]["wheel"]["native_member"]="other.so"
    elif fault=="wheel_size_alias":packet["proofs"]["wheel"]["bytes"]=True
    else:packet["root_reviews"]["primer"]="3"*64
    _pin_prerequisite(monkeypatch,packet)
    with pytest.raises(V.P.ProofRefused):V.admit_plan(packet,"smoke")


@pytest.mark.parametrize("fault",["missing","seed","source","native","affinity","caps","lineage","retirement","scope","index_digest"])
def test_actual_worker_cp_context_is_required_before_full_admission(registered,monkeypatch,fault):
    packet=deepcopy(registered.workers);row=packet["worlds"]["template"]
    cp=row["candidate_checkpoints"][0]
    if fault=="missing":row["candidate_checkpoints"].pop()
    elif fault=="seed":cp["seed"]=43
    elif fault=="source":cp["header"]["identity"]["source"]["git_sha"]="0"*40
    elif fault=="native":cp["header"]["identity"]["native"]["sha256"]=V.B.OLD_NATIVE
    elif fault=="affinity":cp["header"]["identity"]["environment"]["affinity_cpu_count"]=4
    elif fault=="caps":cp["header"]["identity"]["environment"]["thread_env"]["VECLIB_MAXIMUM_THREADS"]="2"
    elif fault=="lineage":cp["header"]["lineage"]=[dict(resumed_at=6)]
    elif fault=="retirement":row["checkpoint_retirement_complete"]=False
    elif fault=="scope":row["worker_observation_scope"]="independently_sampled_two_worker_overlap"
    else:row["checkpoint_index_sha256"]=None
    _pin_workers(monkeypatch,packet)
    with pytest.raises(V.P.ProofRefused):V.admit_plan(registered.packet,"full",packet)


@pytest.mark.parametrize("stage", [None, "", "all", "FULL", 2, True])
def test_phase_is_closed(registered, stage):
    with pytest.raises(V.P.ProofRefused, match="closed outcome phase"):
        V.admit_plan(registered.packet, stage)


@pytest.mark.parametrize("key", sorted(PROOF_KEYS))
def test_each_of_six_reviewed_proof_digests_is_required(registered, monkeypatch, key):
    pins = dict(V.REVIEWED_PREREQUISITES)
    pins[key] = None
    monkeypatch.setattr(V, "REVIEWED_PREREQUISITES", MappingProxyType(pins))
    with pytest.raises(V.P.ProofRefused, match="remain NULL"):
        V.admit_plan(registered.packet, "smoke")


@pytest.mark.parametrize("scope", ["REVIEWED_PREREQUISITES", "REVIEWED_PRIMER", "REVIEWED_WORKER_SMOKES"])
@pytest.mark.parametrize("fault", ["missing", "extra"])
def test_source_registry_keys_are_closed_before_content(registered, monkeypatch, scope, fault):
    _pin_workers(monkeypatch, registered.workers)
    pins = dict(getattr(V, scope))
    if fault == "missing":
        del pins[sorted(pins)[0]]
    else:
        pins["unregistered_extra"] = "7" * 64
    monkeypatch.setattr(V, scope, MappingProxyType(pins))

    def forbidden(*_args, **_kwargs):
        pytest.fail("malformed source registration interpreted packet")

    monkeypatch.setattr(V.B, "canonical_bytes", forbidden)
    stage = "full" if scope == "REVIEWED_WORKER_SMOKES" else "smoke"
    with pytest.raises(V.P.ProofRefused):
        V.admit_plan(registered.packet, stage, registered.workers if stage == "full" else None)


@pytest.mark.parametrize("key", sorted(PROOF_KEYS))
def test_changed_proof_fails_even_with_new_packet_hash(registered, monkeypatch, key):
    packet = deepcopy(registered.packet)
    packet["proofs"][key]["unreviewed_change"] = True
    _pin_prerequisite(monkeypatch, packet, proofs=False)
    with pytest.raises(V.P.ProofRefused, match="proof digest differs"):
        V.admit_plan(packet, "smoke")


@pytest.mark.parametrize("key,value", [
    ("schema_version", True), ("schema_version", 1), ("kind", "legacy"),
    ("baseline_source", "0" * 40), ("baseline_crate", "0" * 40),
    ("candidate_source", "0" * 40), ("candidate_crate", "0" * 40),
    ("build_registration", {}), ("proofs", {}),
])
def test_closed_packet_sources_and_build_binding(registered, monkeypatch, key, value):
    packet = deepcopy(registered.packet)
    packet[key] = value
    _pin_prerequisite(monkeypatch, packet, proofs=False)
    with pytest.raises(V.P.ProofRefused):
        V.admit_plan(packet, "smoke")


@pytest.mark.parametrize("key,value", [
    ("executions", 18), ("executions", True), ("physics_ticks", 3096),
    ("own_checkpoints", 12), ("actual_affinity_cpu_count", 4),
    ("logical_cpu_count", 4), ("publication_complete", False),
    ("serial_repeat_scope", "two concurrent workers proven"), ("caps", {}),
])
def test_late_primer_has_exact_coverage_and_serial_scope(registered, monkeypatch, key, value):
    packet = deepcopy(registered.packet)
    packet["primer"][key] = value
    _pin_prerequisite(monkeypatch, packet)
    with pytest.raises(V.P.ProofRefused):
        V.admit_plan(packet, "smoke")


@pytest.mark.parametrize("cap", M.THREAD_KEYS)
def test_each_primer_thread_cap_is_one(registered, monkeypatch, cap):
    packet = deepcopy(registered.packet)
    packet["primer"]["caps"][cap] = "2"
    _pin_prerequisite(monkeypatch, packet)
    with pytest.raises(V.P.ProofRefused, match="caps1"):
        V.admit_plan(packet, "smoke")


@pytest.mark.parametrize("key,value", [("run_id", True), ("job_id", 0), ("attempt", 2),
    ("artifact_id", -1), ("artifact_bytes", 0), ("control_sha", "C" * 40),
    ("artifact_sha256", "0" * 63), ("proof_sha256", None),
    ("artifact_expires_at", "not-a-date")])
def test_primer_producer_registration_is_typed_and_exact(registered, monkeypatch, key, value):
    changed = dict(V.REVIEWED_PRIMER)
    changed[key] = value
    monkeypatch.setattr(V, "REVIEWED_PRIMER", MappingProxyType(changed))
    with pytest.raises(V.P.ProofRefused):
        V.admit_plan(registered.packet, "smoke")


@pytest.mark.parametrize("fault", ["candidate_native", "build_context", "unknown_flags"])
def test_build_proof_must_match_registered_native_and_context(registered, monkeypatch, fault):
    packet = deepcopy(registered.packet)
    proof = packet["proofs"]["build_context"]
    if fault == "candidate_native":
        proof["candidate_native_sha256"] = "3" * 64
    elif fault == "build_context":
        proof["context"]["rustc"] = "different recorded compiler"
        proof["baseline_context_sha256"] = proof["candidate_context_sha256"] = _hash(proof["context"])
    else:
        proof["context"]["unknown"] = ["RUSTFLAGS"]
        proof["baseline_context_sha256"] = proof["candidate_context_sha256"] = _hash(proof["context"])
    _pin_prerequisite(monkeypatch, packet)
    with pytest.raises((V.P.ProofRefused, V.A.AdmissionError)):
        V.admit_plan(packet, "smoke")


@pytest.mark.parametrize("worldgen", ["template", "procedural"])
@pytest.mark.parametrize("key,value", [
    ("worldgen", "other"), ("source_sha", "0" * 40), ("native_sha256", "0" * 64),
    ("status", "PASS"), ("publication_complete", False), ("producer_conclusion", "failure"),
    ("worker_path", "serial_a_b_subprocesses"), ("parents", 1), ("forks", 3),
    ("executions", 5), ("physics_ticks", 333), ("turns", 124), ("parallel", True),
    ("actual_affinity_cpu_count", 4), ("logical_cpu_count", 4), ("caps", {}),
    ("scientific_gate_pass", 0), ("scientific_gate_pass", True), ("scientific_exit_code", 0),
    ("producer", {}),
])
def test_full_gate_requires_each_real_worker_smoke_scope(registered, monkeypatch, worldgen, key, value):
    packet = deepcopy(registered.workers)
    packet["worlds"][worldgen][key] = value
    _pin_workers(monkeypatch, packet)
    with pytest.raises(V.P.ProofRefused):
        V.admit_plan(registered.packet, "full", packet)


@pytest.mark.parametrize("worldgen", ["template", "procedural"])
def test_one_world_or_serial_repeat_cannot_supply_worker_coverage(registered, monkeypatch, worldgen):
    packet = deepcopy(registered.workers)
    del packet["worlds"][worldgen]
    # Keep both source-reviewed row pins while changing only the packet hash.
    _pin_workers(monkeypatch, registered.workers)
    monkeypatch.setattr(V, "ROOT_WORKER_SMOKE_PACKET_SHA256", _hash(packet))
    with pytest.raises(V.P.ProofRefused, match="both original worker"):
        V.admit_plan(registered.packet, "full", packet)


@pytest.mark.parametrize("key,value", [("control_sha", "A" * 40), ("run_id", True),
    ("job_id", 0), ("attempt", 2), ("job_key", "full")])
def test_worker_producer_is_explicit_and_typed(registered, monkeypatch, key, value):
    packet = deepcopy(registered.workers)
    packet["worlds"]["template"]["producer"][key] = value
    _pin_workers(monkeypatch, packet)
    with pytest.raises(V.P.ProofRefused):
        V.admit_plan(registered.packet, "full", packet)


@pytest.mark.parametrize("cap", M.THREAD_KEYS)
def test_each_worker_thread_cap_is_one(registered, monkeypatch, cap):
    packet = deepcopy(registered.workers)
    packet["worlds"]["procedural"]["caps"][cap] = "2"
    _pin_workers(monkeypatch, packet)
    with pytest.raises(V.P.ProofRefused, match="caps1"):
        V.admit_plan(registered.packet, "full", packet)


def test_factory_seals_and_input_snapshot_prevent_forgery_and_mutation(registered):
    plan = V.admit_plan(registered.packet, "smoke")
    registered.packet["primer"]["physics_ticks"] = 1
    assert V.recheck_plan(plan).prerequisite_packet == plan.prerequisite_packet
    forged = V.AdmittedOutcomePlan(plan.stage, plan.prerequisite_packet, None, plan.registration_bytes, object())
    with pytest.raises(V.P.ProofRefused, match="factory-admitted"):
        V.recheck_plan(forged)


@pytest.mark.parametrize("scope", ["prerequisite", "primer", "root_packet", "worker", "worker_packet"])
def test_recheck_refuses_any_registration_drift(registered, monkeypatch, scope):
    _pin_workers(monkeypatch, registered.workers)
    plan = V.admit_plan(registered.packet, "full", registered.workers)
    if scope == "prerequisite":
        pins = dict(V.REVIEWED_PREREQUISITES); pins["native"] = "7" * 64
        monkeypatch.setattr(V, "REVIEWED_PREREQUISITES", MappingProxyType(pins))
    elif scope == "primer":
        pins = dict(V.REVIEWED_PRIMER); pins["job_id"] += 1
        monkeypatch.setattr(V, "REVIEWED_PRIMER", MappingProxyType(pins))
    elif scope == "root_packet":
        monkeypatch.setattr(V, "ROOT_PREREQUISITE_PACKET_SHA256", "7" * 64)
    elif scope == "worker":
        pins = dict(V.REVIEWED_WORKER_SMOKES); pins["template"] = "7" * 64
        monkeypatch.setattr(V, "REVIEWED_WORKER_SMOKES", MappingProxyType(pins))
    else:
        monkeypatch.setattr(V, "ROOT_WORKER_SMOKE_PACKET_SHA256", "7" * 64)
    with pytest.raises(V.P.ProofRefused, match="registration changed"):
        V.recheck_plan(plan)
