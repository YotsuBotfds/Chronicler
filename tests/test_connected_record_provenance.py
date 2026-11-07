"""Exact opt-in record citations, using saved natural PL3 and constructed variants."""
import copy
import json
from pathlib import Path
import pytest
from chronicler.narration_provenance import livelihood_fact_id, resolve_record_pointer, parse_citations
from chronicler.narration_audit import BundleRecords, audit_bundle

@pytest.fixture
def bundle():
    natural = json.loads((Path(__file__).parents[1] / "viewer/src/__fixtures__/recovery_chain_natural_records.json").read_text())
    return {"history": natural["snapshots"], "world_state": {}, "chronicle_entries": []}

def test_natural_receipt_has_exact_value_pointer_and_completed_date(bundle):
    snapshot = next(s for s in bundle["history"] if s["turn"] == 28)
    fid = livelihood_fact_id(28, "recovery_crews", "receipts", 0, "members", 0, "wage_milli")
    record = resolve_record_pointer(bundle, fid)
    assert record is not None and record.source_turn == 27
    assert record.value == snapshot["livelihoods"]["recovery_crews"]["receipts"][0]["members"][0]["wage_milli"]
    value = bundle
    for token in record.pointer.lstrip("/").split("/"):
        value = value[int(token)] if isinstance(value, list) else value[token]
    assert value == record.value
    assert BundleRecords(bundle).resolve(fid, {}) == (True, 27)
    clean, spans = parse_citations(f"The saved wage was {record.value} milli-coins [{fid}].")
    assert clean.endswith("milli-coins.") and spans[0][2] == [fid]

@pytest.mark.parametrize("fid", ["s28.lh.recovery_crews.receipts.999.members.0", "s28.lh.fake.records.0", "s28.lh.recovery_crews.missing", "s28.lh", "s28.lh.recovery_crews.receipts.-1", "s28.lh.recovery_crews.receipts.00"])
def test_invented_rows_never_pass_as_existing_snapshot_facts(bundle, fid):
    assert resolve_record_pointer(bundle, fid) is None
    assert BundleRecords(bundle).resolve(fid, {}) == (False, None)

@pytest.mark.parametrize("change", ["date", "version", "duplicate", "missing"])
def test_package_source_and_unique_snapshot_are_required(bundle, change):
    snapshot = next(s for s in bundle["history"] if s["turn"] == 28)
    if change == "date": snapshot["livelihoods"]["recovery_crews"]["source_turn"] = 28
    if change == "version": snapshot["livelihoods"]["schema_version"] = 99
    if change == "duplicate": bundle["history"].append(copy.deepcopy(snapshot))
    if change == "missing": del snapshot["livelihoods"]
    assert resolve_record_pointer(bundle, livelihood_fact_id(28, "recovery_crews", "receipts", 0)) is None

def test_audit_finds_exact_false_citation_and_preserves_historical_snapshot_ids(bundle):
    records = BundleRecords(bundle)
    assert records.resolve("s28.old_unknown_kind.c0", {}) == (True, 27)
    fid = livelihood_fact_id(28, "recovery_crews", "receipts", 999)
    bundle["chronicle_entries"] = [{"narrative": "A receipt exists.", "provenance": {"v": 1, "narrator": "mechanical", "as_of": 27, "facts": [fid], "names": [], "spans": [[0,17,[fid]]]}}]
    assert "unresolved_fact" in {f.kind for f in audit_bundle(bundle).flags}

def test_exact_citations_keep_future_and_date_mismatch_checks(bundle):
    fid = livelihood_fact_id(28, "recovery_crews", "receipts", 0)
    bundle["chronicle_entries"] = [{"narrative": "A receipt exists.", "provenance": {"v": 1, "narrator": "mechanical", "as_of": 25, "facts": [[fid,28]], "names": [], "spans": [[0,17,[fid]]]}}]
    assert {"date_mismatch", "future_supplied", "future_citation"} <= {f.kind for f in audit_bundle(bundle).flags}

@pytest.mark.parametrize("args", [(0,"recovery_crews"), (True,"recovery_crews"), (28,"with.dot"), (28,"recovery_crews",-1), (28,"recovery_crews",True)])
def test_builder_refuses_ambiguous_pointer_tokens(args):
    with pytest.raises(ValueError): livelihood_fact_id(*args)

@pytest.mark.parametrize("join", ["region", "inferred"])
def test_regional_or_inferred_cooccurrence_cannot_be_told_as_a_cause(bundle, join):
    a = livelihood_fact_id(28,"recovery_crews","receipts",0,"members",0)
    b = livelihood_fact_id(28,"repair_projects","projects",0)
    text = "The crew was paid because the project existed."
    bundle["chronicle_entries"] = [{"narrative":text,"provenance":{"v":1,"narrator":"mechanical","as_of":27,"facts":[a,b],"names":[],"spans":[[0,len(text),[a,b]]],"record_links":[{"from":a,"to":b,"join":join}]}}]
    assert "unsupported_record_cause" in {f.kind for f in audit_bundle(bundle).flags}

def test_declared_id_cause_requires_reviewed_equal_person_namespace(bundle):
    snap = next(s for s in bundle["history"] if s["turn"] == 28)
    member = snap["livelihoods"]["recovery_crews"]["receipts"][0]["members"][0]
    person = member["agent_id"]
    snap["livelihoods"]["adaptive_livelihoods"] = {"schema_version":1,"source_turn":27,"frame":{"work":[{"id":person}]}}
    a=livelihood_fact_id(28,"recovery_crews","receipts",0,"members",0)
    b=livelihood_fact_id(28,"adaptive_livelihoods","frame","work",0)
    text = "These rows name the same person, so participation can be joined."
    prov = {"v":1,"narrator":"mechanical","as_of":27,"facts":[a,b],"names":[],"spans":[[0,len(text),[a,b]]],"record_links":[{"from":a,"to":b,"join":"id","left_key":"agent_id","right_key":"id","value":person}]}
    bundle["chronicle_entries"] = [{"narrative":text,"provenance":prov}]
    assert audit_bundle(bundle).flags == []
    prov["record_links"][0]["value"] = 999
    assert "unsupported_record_cause" in {f.kind for f in audit_bundle(bundle).flags}


def test_nested_observation_keeps_its_earlier_completed_source_date(bundle):
    s=next(s for s in bundle["history"] if s["turn"]==28)
    s["livelihoods"]["constructed_contract"]={"schema_version":1,"source_turn":27,"frame":{"source_turn":26,"rows":[{"id":13}]}}
    fid=livelihood_fact_id(28,"constructed_contract","frame","rows",0)
    assert resolve_record_pointer(bundle,fid).source_turn==26
    assert BundleRecords(bundle).resolve(fid,{})==(True,26)
    text="The earlier observation names person13."
    bundle["chronicle_entries"]=[{"narrative":text,"provenance":{"v":1,"narrator":"mechanical","as_of":27,"facts":[[fid,26]],"names":[],"spans":[[0,len(text),[fid]]]}}]
    assert audit_bundle(bundle).flags==[]
    bundle["chronicle_entries"][0]["provenance"]["facts"]=[fid]
    assert "date_mismatch" in {f.kind for f in audit_bundle(bundle).flags}


@pytest.mark.parametrize("source",[True,28,-1,"26",None])
def test_future_or_unknown_nested_source_is_not_relabelled_with_snapshot_date(bundle,source):
    s=next(s for s in bundle["history"] if s["turn"]==28)
    s["livelihoods"]["constructed_contract"]={"schema_version":1,"source_turn":27,"frame":{"source_turn":source,"rows":[{"id":13}]}}
    assert resolve_record_pointer(bundle,livelihood_fact_id(28,"constructed_contract","frame","rows",0)) is None


def test_c2_capacity_input_does_not_backdate_current_mortality_or_refusal(bundle):
    s=next(s for s in bundle["history"] if s["turn"]==28)
    s["livelihoods"]["epidemic_care"]={"schema_version":1,"source_turn":27,"tick":{"turn":27,"applied":[{"source_turn":26,"patients":2.0,"infectious":4.0,"deaths":1}],"refused":[{"source_turn":30,"reason":"future"}]}}
    prefix=(28,"epidemic_care","tick","applied",0)
    for leaf in [(),("deaths",),("infectious",)]:
        assert resolve_record_pointer(bundle,livelihood_fact_id(*prefix,*leaf)).source_turn==27
    for leaf in ["patients","source_turn"]:
        assert resolve_record_pointer(bundle,livelihood_fact_id(*prefix,leaf)).source_turn==26
    refused=livelihood_fact_id(28,"epidemic_care","tick","refused",0)
    assert resolve_record_pointer(bundle,refused).source_turn==27
    fid=livelihood_fact_id(*prefix,"deaths");text="The current regional tick recorded one death."
    bundle["chronicle_entries"]=[{"narrative":text,"provenance":{"v":1,"narrator":"mechanical","as_of":26,"facts":[[fid,26]],"names":[],"spans":[[0,len(text),[fid]]]}}]
    assert {"date_mismatch","future_citation"}<={f.kind for f in audit_bundle(bundle).flags}


def test_c4_prior_exposure_inputs_are_distinct_from_current_policy_application(bundle):
    s=next(s for s in bundle["history"] if s["turn"]==28)
    s["livelihoods"]["public_health"]={"schema_version":1,"source_turn":27,"environment":[{"source_turn":26,"displaced_share":.2,"water_service":.5,"crowding_factor":1.05,"flux_factor":.9}]}
    prefix=(28,"public_health","environment",0)
    for leaf in [(),("flux_factor",)]:
        assert resolve_record_pointer(bundle,livelihood_fact_id(*prefix,*leaf)).source_turn==27
    for leaf in ["source_turn","displaced_share","water_service","crowding_factor"]:
        assert resolve_record_pointer(bundle,livelihood_fact_id(*prefix,leaf)).source_turn==26


@pytest.mark.parametrize("left_package,left_path,left_key,right_package,right_path,right_key",[
    ("workshop_economics",["receipts",0],"owner","epidemic_care",["frame",0,"carers",0],"agent_id"),
    ("repair_projects",["projects",0],"pid","timber_supply",["expeditions",0],"eid"),
    ("constructed_contract",["left"],"agent_id","constructed_contract",["right"],"holder"),
])
def test_equal_scalars_from_incompatible_or_unreviewed_identity_namespaces_do_not_authorize_cause(bundle,left_package,left_path,left_key,right_package,right_path,right_key):
    snap=next(s for s in bundle["history"] if s["turn"]==28)
    def install(package,path,key):
        root=snap["livelihoods"].setdefault(package,{"schema_version":1,"source_turn":27})
        value=root
        for i,part in enumerate(path):
            following=path[i+1] if i+1<len(path) else None
            if isinstance(part,int):
                while len(value)<=part:value.append({})
                value=value[part]
            else:value=value.setdefault(part,[] if isinstance(following,int) else {})
        value[key]=1
    install(left_package,left_path,left_key);install(right_package,right_path,right_key)
    a=livelihood_fact_id(28,left_package,*left_path);b=livelihood_fact_id(28,right_package,*right_path)
    text="The equal integers caused this result, so these people were linked."
    bundle["chronicle_entries"]=[{"narrative":text,"provenance":{"v":1,"narrator":"mechanical","as_of":27,"facts":[a,b],"names":[],"spans":[[0,len(text),[a,b]]],"record_links":[{"from":a,"to":b,"join":"id","left_key":left_key,"right_key":right_key,"value":1}]}}]
    assert "unsupported_record_cause" in {f.kind for f in audit_bundle(bundle).flags}


@pytest.mark.parametrize("boundary",["resume","pool_reset"])
def test_reused_person_integer_across_rebuild_is_not_a_stable_join(bundle,boundary):
    if boundary=="resume":bundle["metadata"]={"resume":{"exact":False,"turn":27}}
    earlier=next(s for s in bundle["history"] if s["turn"]==27)
    later=next(s for s in bundle["history"] if s["turn"]==28)
    if boundary=="pool_reset":later["livelihoods"]["residence_ledger"]={"schema_version":1,"stage":"X1","source_turn":27,"log_dropped":0,"log":[{"turn":27,"kind":"pool_reset"}]}
    person=later["livelihoods"]["recovery_crews"]["receipts"][0]["members"][0]["agent_id"]
    earlier["livelihoods"]["adaptive_livelihoods"]={"schema_version":1,"source_turn":26,"frame":{"work":[{"id":person}]}}
    a=livelihood_fact_id(27,"adaptive_livelihoods","frame","work",0);b=livelihood_fact_id(28,"recovery_crews","receipts",0,"members",0)
    text="These are the same person because the integer matches."
    bundle["chronicle_entries"]=[{"narrative":text,"provenance":{"v":1,"narrator":"mechanical","as_of":27,"facts":[[a,26],b],"names":[],"spans":[[0,len(text),[a,b]]],"record_links":[{"from":a,"to":b,"join":"id","left_key":"id","right_key":"agent_id","value":person}]}}]
    assert "unsupported_record_cause" in {f.kind for f in audit_bundle(bundle).flags}


def test_retained_cargo_holder_keeps_its_pre_rebuild_identity_segment(bundle):
    bundle["metadata"]={"resume":{"exact":False,"turn":27}}
    snap=next(s for s in bundle["history"] if s["turn"]==28)
    person=snap["livelihoods"]["recovery_crews"]["receipts"][0]["members"][0]["agent_id"]
    snap["livelihoods"]["timber_orders"]={"schema_version":1,"source_turn":27,"closed":[{"holder":person,"dispatched_turn":26}]}
    a=livelihood_fact_id(28,"timber_orders","closed",0);b=livelihood_fact_id(28,"recovery_crews","receipts",0,"members",0)
    text="The old cargo holder is this worker because their integer matches."
    bundle["chronicle_entries"]=[{"narrative":text,"provenance":{"v":1,"narrator":"mechanical","as_of":27,"facts":[a,b],"names":[],"spans":[[0,len(text),[a,b]]],"record_links":[{"from":a,"to":b,"join":"id","left_key":"holder","right_key":"agent_id","value":person}]}}]
    assert "unsupported_record_cause" in {f.kind for f in audit_bundle(bundle).flags}


@pytest.mark.parametrize('prior', [-1, 26])
def test_neutral_configured_density_is_known_now_without_inventing_prior_residence(bundle, prior):
    s = next(s for s in bundle['history'] if s['turn'] == 28)
    row = {'source_turn': prior, 'crowding_basis': 'density_only', 'crowding_source_turn': 27,
           'crowding_factor': 1.0, 'recent_arrival_share': None, 'arrival_diagnostics_complete': False}
    s['livelihoods']['public_health'] = {'schema_version': 1, 'source_turn': 27, 'environment': [row]}
    fid = livelihood_fact_id(28, 'public_health', 'environment', 0, 'crowding_factor')
    assert resolve_record_pointer(bundle, fid).source_turn == 27
    if prior >= 0:
        arrival = livelihood_fact_id(28, 'public_health', 'environment', 0, 'recent_arrival_share')
        assert resolve_record_pointer(bundle, arrival).source_turn == prior
    row['crowding_source_turn'] = 28
    assert resolve_record_pointer(bundle, fid) is None
    row['crowding_source_turn'], row['crowding_factor'] = 27, 1.25
    assert resolve_record_pointer(bundle, fid) is None
