"""Post-hoc observations do not mutate state or manufacture activation."""
import copy
import runpy
from pathlib import Path

collect = runpy.run_path(str(Path(__file__).parents[1]/"scripts/connected_world_examples.py"))["collect_examples"]

def test_examples_preserve_source_and_audit_each_actual_pointer():
    package={"schema_version":1,"stage":"A4-3","source_turn":2,"closed":[
        {"id":1,"holder":7,"outcome":"delivered","delivered_milli":990,"lost_milli":10,"credited_milli":1100,"refunded_milli":900},
        {"id":2,"holder":8,"outcome":"route_lost","delivered_milli":0,"lost_milli":0,"purchase_milli":500,"deposited_milli":1000,"refunded_milli":2000}]}
    bundle={"history":[{"turn":3,"livelihoods":{"schema_version":1,"timber_orders":package}}],"world_state":{},"chronicle_entries":[]}
    before=copy.deepcopy(bundle);report=collect(bundle,{"snapshots":{"3":{"timber_orders":"observed"}}})
    assert bundle==before
    for category in ("adaptation","failure","mixed"):
        row=report["examples"]["timber_orders:"+category]
        assert row["found"] and row["source_turn"]==2 and row["pointer"].startswith("/history/0/livelihoods/timber_orders/closed/")
    assert report["examples"]["war_requisition:adaptation"]["found"] is False
    assert report["story_audit"]["flags"]==[]

def test_constructed_input_stays_labelled_and_misdated_records_are_not_cited():
    marker={"from":"abc","edits":["constructed"]}
    bundle={"metadata":{"constructed":marker},"world_state":{},"history":[{"turn":3,"livelihoods":{"schema_version":1,"timber_orders":{"schema_version":1,"source_turn":3,"closed":[{"outcome":"route_lost"}]}}}]}
    report=collect(bundle)
    assert report["constructed"]==marker
    assert all(not row["found"] for row in report["examples"].values())
    assert report["story_audit"]["flags"]==[]


def test_natural_examples_require_observed_strict_reader_receipt():
    bundle={"history":[{"turn":3,"livelihoods":{"schema_version":1,"timber_orders":{"schema_version":1,"source_turn":2,"closed":[{"outcome":"route_lost"}]}}}],"world_state":{}}
    for receipt in (None,{"snapshots":{"3":{"timber_orders":"malformed"}}},{"snapshots":{"3":{"timber_orders":"unobserved"}}}):
        report=collect(bundle,receipt)
        assert not report["examples"]["timber_orders:failure"]["found"]
        assert report["skipped_validation"]
        assert report["story_audit"]["totals"]["entries"]==0
