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
