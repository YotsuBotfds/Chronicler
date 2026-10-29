"""NONDEFAULT external-binding prospective cases; UNRUN, invented metadata only.

No filesystem, host, clock, process, network, environment or native observation.
Successful fake joins never authenticate an external grant or activate anything.
"""
from copy import deepcopy
import json

import pytest
import current6a2_timing_binding as B


def invented_values():
    policy = deepcopy(B.STATIC_POLICY)
    roots = {name: "/invented/" + name for name in policy["root_fields"]}
    run = dict(run_id=123, job_id=456, attempt=1, nonce="1" * 64)
    source = "a" * 40
    common = dict(control_source=source, producer_source=policy["producer_source"], **run)
    environment = dict(common, kind="ROOT_ADMITTED_CURRENT6A2_ENVIRONMENT_V1",
        source_root=roots["producer_root"], native_prefix=roots["native_prefix"],
        manifests={name: {"bytes": 1, "sha256": "2" * 64} for name in policy["environment_manifest_fields"]},
        admission_source_review_sha256="3" * 64)
    original = policy["original_artifact"]
    admitted = dict(common, kind="ROOT_ADMITTED_CURRENT6A2_TIMING_INPUT",
        source_root=roots["producer_root"], native_prefix=roots["native_prefix"],
        qualified_CI_run=original["run_id"], qualified_CI_attempt=1, artifact_id=original["artifact_id"],
        archive=deepcopy(original["archive"]), build_reference=deepcopy(original["build_reference"]),
        wheel=deepcopy(original["wheel"]), native=deepcopy(original["native"]),
        builder_source_digest=policy["builder_source_digest"], official_origin_expiry_reauthenticated=True,
        installed_native_file=roots["native_prefix"]+"/lib/native.so",
        wheel_file=roots["input_root"]+"/exact.whl", expires_at="2030-01-02T00:00:00Z")
    clock = dict(common, kind="ROOT_ADMITTED_ACTUAL_JOB_DEADLINE", approval="invented-clock-review",
        job_deadline_monotonic=2000.0, monotonic_observed=900.0, publication_reserve_seconds=105)
    return {"policy":policy,"roots":roots,"run":run,"source":source,"environment":environment,
            "input":admitted,"job_clock":clock,
            "registration":{"producer_source":policy["producer_source"],
                "execution_approval":None,"job_clock_admission_approval":None,
                "runtime_input_admission_sha256":None,"job_clock_admission_sha256":None,
                "approved_fake_test_receipt_sha256":None}}


def seal_invented(values, *, grant_change=None, envelope_change=None,
                  authority_change=None, observed_change=None, keep_input_environment_pin=False):
    """Recompute invented byte pins, so semantic mutations are not masked by stale hashes."""
    v=deepcopy(values)
    raw={name:B.canonical(v[name]) for name in ("policy","environment","job_clock")}
    if not keep_input_environment_pin:
        v["input"]["environment_receipt"]=B.pin(raw["environment"])
    raw["input"]=B.canonical(v["input"])
    v["registration"].setdefault("runtime_binding_policy",{
        "path":"docs/experiments/current6a2-timing-binding-policy.json",**B.pin(raw["policy"])})
    raw["registration"]=B.canonical(v["registration"])
    static={"control_source":v["source"],"registration":B.pin(raw["registration"]),"policy":B.pin(raw["policy"])}
    receipts={name:B.pin(raw[name]) for name in ("input","environment","job_clock")}
    grant={"kind":"ROOT_AUTHORIZED_CURRENT6A2_RUNTIME_GRANT_V1","protocol":B.STATIC_POLICY["protocol"],
        "static":deepcopy(static),"roots":deepcopy(v["roots"]),"run":deepcopy(v["run"]),
        "receipts":deepcopy(receipts),"execution_approval":"invented-execution-review",
        "job_clock_admission_approval":"invented-clock-review",
        "baseline_fake_qualification":deepcopy(B.STATIC_POLICY["baseline_fake_qualification"]),
        "binding_fake_qualification":{"bytes":99,"sha256":"4444444444444444444444444444444444444444444444444444444444444444"}}
    if grant_change:
        grant_change(grant)
    raw["grant"]=B.canonical(grant)
    envelope={"kind":"OWNED_CURRENT6A2_RUNTIME_BINDING_V1","protocol":B.STATIC_POLICY["protocol"],
        "static":deepcopy(static),"roots":deepcopy(v["roots"]),"run":deepcopy(v["run"]),
        "grant":B.pin(raw["grant"]),"receipts":deepcopy(receipts)}
    if envelope_change:
        envelope_change(envelope)
    raw["envelope"]=B.canonical(envelope)
    authority={"kind":"AUTHENTICATED_CURRENT6A2_LAUNCHER_REFERENCE_V1","grant":B.pin(raw["grant"]),
        "static":deepcopy(static),"roots":deepcopy(v["roots"]),"run":deepcopy(v["run"])}
    observed={"static":deepcopy(static),"roots":deepcopy(v["roots"]),"run":deepcopy(v["run"]),
        "execution_approval":"invented-execution-review","job_clock_admission_approval":"invented-clock-review",
        "envelope":B.pin(raw["envelope"]),"now_monotonic":1000.0}
    if authority_change:
        authority_change(authority)
    if observed_change:
        observed_change(observed)
    return raw,B.canonical(authority),B.canonical(observed)


def test_closed_invented_bundle_is_detached_metadata_and_never_authentication():
    values=invented_values()
    raw,authority,observed=seal_invented(values)
    result=B.validate_bundle(raw,authority,observed)
    before=deepcopy(result)
    values["run"]["run_id"]=999
    assert result==before and result["run"]["run_id"]==123
    assert result["external_authentication_qualification"] is None
    assert result["environment_body_qualification"] is None
    assert result["quota_enforcement"] is result["ordinary_original_custody"] is None


@pytest.mark.parametrize("name",["registration","policy","grant","envelope","input","environment","job_clock"])
@pytest.mark.parametrize("change",["missing","extra","noncanonical"])
def test_document_namespace_and_exact_bytes_are_closed(name,change):
    raw,authority,observed=seal_invented(invented_values())
    if change=="missing":
        del raw[name]
    elif change=="extra":
        raw[name+"-replacement"]=raw[name]
    else:
        raw[name]=b" "+raw[name]
    with pytest.raises(B.Refused):
        B.validate_bundle(raw,authority,observed)


@pytest.mark.parametrize("receipt",["input","environment","job_clock"])
@pytest.mark.parametrize("field,value",[
    ("producer_source","bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"),("control_source","bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"),
    ("run_id",124),("job_id",457),("attempt",2),("nonce","5555555555555555555555555555555555555555555555555555555555555555"),
])
def test_each_receipt_must_join_same_exact_producer_control_job_attempt_nonce(receipt,field,value):
    values=invented_values()
    values[receipt][field]=value
    with pytest.raises(B.Refused):
        B.validate_bundle(*seal_invented(values))


@pytest.mark.parametrize("field,value",[
    ("qualified_CI_run",40939929536),("qualified_CI_attempt",True),("artifact_id",12925919180),
    ("builder_source_digest","0000000000000000000000000000000000000000000000000000000000000000"),("official_origin_expiry_reauthenticated",False),
    ("installed_native_file","/outside/native.so"),("wheel_file","/outside/wheel.whl"),
    ("expires_at","2030-01-02"),("source_root","/invented/wrong-source"),
    ("native_prefix","/invented/wrong-prefix"),
])
def test_input_cannot_borrow_other_provenance_or_arbitrary_physical_paths(field,value):
    values=invented_values()
    values["input"][field]=value
    with pytest.raises(B.Refused):
        B.validate_bundle(*seal_invented(values))


@pytest.mark.parametrize("body",["archive","build_reference","wheel","native"])
@pytest.mark.parametrize("change",["other_hash","float_bytes","extra"])
def test_original_archive_build_wheel_native_pins_have_exact_closed_types(body,change):
    values=invented_values()
    value=values["input"][body]
    if change=="other_hash":
        value["sha256"]="0000000000000000000000000000000000000000000000000000000000000000"
    elif change=="float_bytes":
        value["bytes"]=float(value["bytes"])
    else:
        value["borrowed"]=True
    with pytest.raises(B.Refused):
        B.validate_bundle(*seal_invented(values))


@pytest.mark.parametrize("receipt",["input","environment","job_clock"])
@pytest.mark.parametrize("change",["missing","extra"])
def test_receipt_fields_cannot_expand_or_disappear(receipt,change):
    values=invented_values()
    if change=="missing":
        del values[receipt]["kind"]
    else:
        values[receipt]["ignore_unknown"]=True
    with pytest.raises(B.Refused):
        B.validate_bundle(*seal_invented(values))


@pytest.mark.parametrize("field,value",[
    ("publication_reserve_seconds",106),("publication_reserve_seconds",105.0),
    ("job_deadline_monotonic",1000.0),("job_deadline_monotonic",4000.0),
    ("monotonic_observed",1001.0),("monotonic_observed",True),
    ("approval","invented-other-clock-review"),
])
def test_clock_cannot_rebind_review_or_borrow_time_or_use_boolean_domain(field,value):
    values=invented_values()
    values["job_clock"][field]=value
    with pytest.raises(B.Refused):
        B.validate_bundle(*seal_invented(values))


@pytest.mark.parametrize("change",["missing_manifest","extra_manifest","bad_pin","wrong_source","wrong_prefix","bad_review"])
def test_environment_receipt_closes_required_body_references_without_attesting_them(change):
    values=invented_values()
    environment=values["environment"]
    if change=="missing_manifest":
        del environment["manifests"]["startup"]
    elif change=="extra_manifest":
        environment["manifests"]["ignored"]={"bytes":1,"sha256":"1111111111111111111111111111111111111111111111111111111111111111"}
    elif change=="bad_pin":
        environment["manifests"]["startup"]["bytes"]=True
    elif change=="wrong_source":
        environment["source_root"]="/other/source"
    elif change=="wrong_prefix":
        environment["native_prefix"]="/other/prefix"
    else:
        environment["admission_source_review_sha256"]="unknown"
    with pytest.raises(B.Refused):
        B.validate_bundle(*seal_invented(values))


@pytest.mark.parametrize("change",["source","registration","policy","roots","run","nonce","approval","baseline_fake","missing_fake","extra"])
def test_authenticated_grant_must_match_current_static_identity_roots_and_job(change):
    def mutate(grant):
        if change=="source": grant["static"]["control_source"]="bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
        elif change in ("registration","policy"): grant["static"][change]["sha256"]="0000000000000000000000000000000000000000000000000000000000000000"
        elif change=="roots": grant["roots"]["producer_root"]="/other/source"
        elif change=="run": grant["run"]["run_id"]=124
        elif change=="nonce": grant["run"]["nonce"]="0000000000000000000000000000000000000000000000000000000000000000"
        elif change=="approval": grant["execution_approval"]="other"
        elif change=="baseline_fake": grant["baseline_fake_qualification"]["sha256"]="0000000000000000000000000000000000000000000000000000000000000000"
        elif change=="missing_fake": del grant["binding_fake_qualification"]
        else: grant["override_root"]=True
    with pytest.raises(B.Refused):
        B.validate_bundle(*seal_invented(invented_values(),grant_change=mutate))


@pytest.mark.parametrize("change",["grant","input","environment","job_clock","static","root","extra"])
def test_envelope_is_one_closed_join_and_cannot_quietly_rebind_receipts(change):
    def mutate(envelope):
        if change=="grant": envelope["grant"]["sha256"]="0000000000000000000000000000000000000000000000000000000000000000"
        elif change in ("input","environment","job_clock"): envelope["receipts"][change]["sha256"]="0000000000000000000000000000000000000000000000000000000000000000"
        elif change=="static": envelope["static"]["control_source"]="bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
        elif change=="root": envelope["roots"]["admission_root"]="/other/admission"
        else: envelope["retry"]=2
    with pytest.raises(B.Refused):
        B.validate_bundle(*seal_invented(invented_values(),envelope_change=mutate))


@pytest.mark.parametrize("change",["grant","source","root","job","attempt"])
def test_already_authenticated_reference_still_must_join_actual_context(change):
    def mutate(authority):
        if change=="grant": authority["grant"]["sha256"]="0000000000000000000000000000000000000000000000000000000000000000"
        elif change=="source": authority["static"]["control_source"]="bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
        elif change=="root": authority["roots"]["input_root"]="/other/input"
        elif change=="job": authority["run"]["job_id"]=999
        else: authority["run"]["attempt"]=2
    with pytest.raises(B.Refused):
        B.validate_bundle(*seal_invented(invented_values(),authority_change=mutate))


@pytest.mark.parametrize("change",["alias","nested","relative","traversal","double_slash"])
def test_even_joined_root_claims_must_be_canonical_and_disjoint(change):
    values=invented_values()
    if change=="alias": values["roots"]["input_root"]=values["roots"]["native_prefix"]
    elif change=="nested": values["roots"]["input_root"]=values["roots"]["native_prefix"]+"/nested"
    elif change=="relative": values["roots"]["input_root"]="relative"
    elif change=="traversal": values["roots"]["input_root"]="/root/../input"
    else: values["roots"]["input_root"]="//ambiguous/input"
    with pytest.raises(B.Refused):
        B.validate_bundle(*seal_invented(values))


@pytest.mark.parametrize("change",["runtime_hash","clock_hash","policy_path","policy_float","policy_changed"])
def test_static_registration_is_not_edited_to_guess_future_runtime_hashes(change):
    values=invented_values()
    if change=="runtime_hash": values["registration"]["runtime_input_admission_sha256"]="0000000000000000000000000000000000000000000000000000000000000000"
    elif change=="clock_hash": values["registration"]["job_clock_admission_sha256"]="0000000000000000000000000000000000000000000000000000000000000000"
    elif change in ("policy_path","policy_float"):
        values["registration"]["runtime_binding_policy"]={
            "path":"/arbitrary/policy" if change=="policy_path" else "docs/experiments/current6a2-timing-binding-policy.json",
            **B.pin(B.canonical(values["policy"]))}
        if change=="policy_float":
            values["registration"]["runtime_binding_policy"]["bytes"]=float(values["registration"]["runtime_binding_policy"]["bytes"])
    else: values["policy"]["publication_reserve_seconds"]=106
    with pytest.raises(B.Refused):
        B.validate_bundle(*seal_invented(values))


def test_forwarding_uses_the_same_explicit_envelope_grant_and_receipt_paths_for_every_child():
    paths={name:"/invented/admission/"+leaf for name,leaf in B.STATIC_POLICY["external_leaf_names"].items()}
    paths["output"]="/invented/output"
    pins={name:{"bytes":1,"sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"} for name in ("grant","envelope")}
    wanted=B.forwarded_arguments(paths,pins,"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb")
    for _role in ("bootstrap","role","hash","compare"):
        assert B.forwarded_arguments(paths,pins,"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb")==wanted
    assert wanted.count("--runtime-binding")==wanted.count("--root-grant")==1
    assert wanted[wanted.index("--environment-admission")+1]==paths["environment"]


def test_actual_grant_authenticator_is_source_held_even_with_caller_supplied_matching_labels(monkeypatch):
    import current6a2_timing_owner as owner
    def forbidden(*_args,**_kwargs):
        raise AssertionError("external I/O before authenticating launcher")
    monkeypatch.setattr(owner.records,"read_json",forbidden)
    monkeypatch.setattr(owner.records,"hash_regular",forbidden)
    with pytest.raises(owner.records.Refused,match="trusted launcher admission remains HELD"):
        owner.authenticate_root_grant({"grant_sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","kind":"ROOT_AUTHORIZED_CURRENT6A2_RUNTIME_GRANT_V1"},{})
