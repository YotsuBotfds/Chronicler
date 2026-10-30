"""Pure benchmark contracts: fake APIs and clocks, never native/World/timing."""
import ast
from copy import deepcopy
from importlib.util import module_from_spec, spec_from_file_location
import io
import json
from pathlib import Path
import struct

import pytest
import yaml

_source = Path(__file__).resolve().parents[1]/"scripts/benchmark_named_context.py"
_spec = spec_from_file_location("named_context_benchmark_contract_source", _source)
bench = module_from_spec(_spec)
_spec.loader.exec_module(bench)


class FakeSimulator:
    def __init__(self, ids, bond_slots=0):
        self.ids = set(ids)
        self.bond_slots = bond_slots
        self.calls = []

    def get_agent_memories(self, agent):
        self.calls.append(("memories", agent))
        return []

    def get_agent_needs(self, agent):
        self.calls.append(("needs", agent))
        return (0., -.0, .25, .5, .75, 1.) if agent in self.ids else None

    def get_agent_relationships(self, agent):
        self.calls.append(("bonds", agent))
        return [(100+i, 50, 6, 0) for i in range(self.bond_slots)] if agent in self.ids else None

    def get_agent_context_batch(self, ids):
        self.calls.append(("batch", tuple(ids)))
        # Payloads are synthetic, independently allocated for every input row.
        return [(agent, [], (0., -.0, .25, .5, .75, 1.) if agent in self.ids else None,
                 [(100+i, 50, 6, 0) for i in range(self.bond_slots)] if agent in self.ids else None)
                for agent in ids]


class Clock:
    def __init__(self, step=100):
        self.value, self.step = 0, step

    def __call__(self):
        self.value += self.step
        return self.value


def build_file(tmp_path, monkeypatch):
    source = "a"*40
    monkeypatch.setenv("GITHUB_SHA", source)
    path = tmp_path/"build.json"
    value = dict(kind="OWN_FRESH_CONTEXT_WHEEL_BUILD", method=bench.METHOD,
        source_commit=source, source_tree="b"*40, native_tree=bench.NATIVE_TREE,
        benchmark_script=bench.file_pin(Path(bench.__file__), bench.MAX_BUILD))
    path.write_text(json.dumps(value))
    return path, value


def small_plan(monkeypatch):
    rows = [dict(case=0, slots=8, requests=1, layout="prefix", bond_slots=0),
            dict(case=1, slots=8, requests=2, layout="missing", bond_slots=0)]
    monkeypatch.setattr(bench, "conditions", lambda: deepcopy(rows))
    monkeypatch.setattr(bench, "RECORDS", 4)
    monkeypatch.setattr(bench, "PAIRS", 2)
    monkeypatch.setattr(bench, "WARMUP_RECORDS", 2)
    return rows


def test_default_is_disabled_before_runtime_or_file_access(monkeypatch, capsys):
    def forbidden(*args, **kwargs):
        raise AssertionError("disabled mode attempted native or build access")
    monkeypatch.setattr(bench, "compiled_module", forbidden)
    monkeypatch.setattr(bench, "record_build", forbidden)
    monkeypatch.setattr(bench, "run_suite", forbidden)
    assert bench.main([]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "disabled"


def test_explicit_plan_only_preserves_all_conditions_without_native(tmp_path,monkeypatch):
    def forbidden(*args):raise AssertionError("plan loaded native")
    monkeypatch.setattr(bench,"compiled_module",forbidden)
    path=tmp_path/"plan.json"
    assert bench.main(["--plan-only","--output",str(path)]) == 0
    plan=json.loads(path.read_text())
    assert len(plan["conditions"]) == 21 and plan["timed_samples"] == 126


def test_fixed21_matrix_and_worst_work_are_declared_before_timing():
    rows = bench.conditions()
    assert len(rows) == 21 and [r["case"] for r in rows] == list(range(21))
    assert rows[:18] == [dict(case=i, slots=n, requests=p, layout=layout, bond_slots=0)
        for i, (n,p,layout) in enumerate((n,p,l) for n in (512,8192,65536)
            for p in (1,50) for l in ("prefix","spread","missing"))]
    assert rows[18:] == [dict(case=18+i,slots=8192,requests=p,layout="spread",bond_slots=8)
        for i,p in enumerate((1,10,50))]
    assert bench.RECORDS == 20000 and bench.PAIRS == 3 and bench.WARMUP_RECORDS == 200
    assert bench.work_bounds()["scalar_slot_visit_upper_bound"] == 84602880000
    assert bench.work_bounds()["batch_slot_visits"] == 14180966400


@pytest.mark.parametrize("layout,p,expected", [
    ("prefix", 1, [0]), ("prefix", 3, [0,1,2]),
    ("spread", 1, [4]), ("spread", 3, [0,3,7]), ("missing", 3, [None,None,None])])
def test_slot_layouts_preserve_observed_pool_order_not_sorted_ids(layout,p,expected):
    ids = [41, 7, 99, 2, 55, 9, 21, 1]
    queries, positions = bench.query_ids(ids, dict(slots=8,requests=p,layout=layout))
    assert positions == expected
    assert queries == ([2**32-1-i for i in range(p)] if layout == "missing" else [ids[i] for i in expected])
    assert ids == [41, 7, 99, 2, 55, 9, 21, 1]


def test_missing_layout_cannot_accidentally_select_a_live_id():
    with pytest.raises(ValueError,match="missing_fixture_ids_live"):
        bench.query_ids([2**32-1, 1],dict(slots=2,requests=1,layout="missing"))


def test_raw_kernels_consume_equal_records_and_keep_scalar_call_order():
    ids = [2, 1, 2, 100]
    scalar, batch = FakeSimulator([1,2],8), FakeSimulator([1,2],8)
    expected = sum(bench.consume(*r) for r in bench.scalar_rows(scalar,ids))*2
    scalar.calls.clear()
    assert bench.scalar_kernel(scalar,ids,2) == bench.batch_kernel(batch,ids,2) == expected
    assert scalar.calls == [(kind,agent) for _ in range(2) for agent in ids
        for kind in ("memories","needs","bonds")]
    assert batch.calls == [("batch",tuple(ids)),("batch",tuple(ids))]


def test_payload_fingerprint_keeps_signed_zero_and_NaN_bits():
    values = (0., -.0, .25, .5, .75, 1.)
    a = [(1,[],values,[])]
    b = [(1,[],(0.,0.,.25,.5,.75,1.),[])]
    assert bench.fingerprint(a) != bench.fingerprint(b)
    nan = struct.unpack("!d",bytes.fromhex("7ff8000000001234"))[0]
    assert bench.fingerprint([(1,[],(nan,)*6,[])]) == bench.fingerprint([(1,[],(nan,)*6,[])])


def test_sample_retains_all_four_clock_endpoints_and_helper_error():
    def broken(*args):
        raise RuntimeError("synthetic helper failure")
    row = bench.timed_sample(broken,None,[],1,Clock(100),Clock(50))
    assert row["wall_end_ns"]-row["wall_start_ns"] == row["wall_ns"] == 100
    assert row["process_CPU_end_ns"]-row["process_CPU_start_ns"] == row["process_CPU_ns"] == 50
    assert row["checksum"] is None and row["error"]["message"] == "synthetic helper failure"


def test_zero_CPU_is_retained_refused_without_ratios_or_retry(monkeypatch):
    monkeypatch.setattr(bench,"RECORDS",2)
    monkeypatch.setattr(bench,"WARMUP_RECORDS",2)
    monkeypatch.setattr(bench,"PAIRS",1)
    journal = io.BytesIO()
    result = bench.condition_result(dict(case=0,slots=8,requests=1,layout="prefix",bond_slots=0),
        FakeSimulator(range(1,9)),list(range(1,9)),journal,Clock(),Clock(0))
    rows = [json.loads(line) for line in journal.getvalue().splitlines()]
    assert len(rows) == len(result["samples"]) == 2
    assert all(r["process_CPU_ns"] == 0 and r["accepted"] is False for r in rows)
    assert result["status"] == "refused" and "wall_ratio_scalar_over_batch" not in result


def test_timed_helper_failure_is_journaled_before_abort(monkeypatch):
    monkeypatch.setattr(bench,"RECORDS",2)
    monkeypatch.setattr(bench,"WARMUP_RECORDS",1)
    monkeypatch.setattr(bench,"PAIRS",1)
    def scalar(sim,ids,repetitions):
        if repetitions == 2:raise RuntimeError("timed synthetic failure")
        return 0
    monkeypatch.setattr(bench,"scalar_kernel",scalar)
    journal=io.BytesIO()
    with pytest.raises(ValueError,match="timed_helper_failed"):
        bench.condition_result(dict(case=0,slots=8,requests=1,layout="prefix",bond_slots=0),
            FakeSimulator(range(1,9)),list(range(1,9)),journal,Clock(),Clock())
    rows=[json.loads(line) for line in journal.getvalue().splitlines()]
    assert len(rows) == 1 and rows[0]["error"]["message"] == "timed synthetic failure"
    assert rows[0]["accepted"] is False and rows[0]["checksum"] is None


def test_ordered_compiled_parity_refusal_precedes_any_clock():
    sim=FakeSimulator(range(1,9))
    get=sim.get_agent_context_batch
    sim.get_agent_context_batch=lambda ids:list(reversed(get(ids)))
    def forbidden():raise AssertionError("parity failure reached timing")
    with pytest.raises(ValueError,match="compiled_API_parity"):
        bench.condition_result(dict(case=0,slots=8,requests=2,layout="prefix",bond_slots=0),
            sim,list(range(1,9)),io.BytesIO(),forbidden,forbidden)


def test_a_batch_slowdown_is_reported_as_a_regression(monkeypatch):
    monkeypatch.setattr(bench,"RECORDS",2)
    monkeypatch.setattr(bench,"WARMUP_RECORDS",2)
    monkeypatch.setattr(bench,"PAIRS",1)
    wall = iter((0,100,200,400))
    result = bench.condition_result(dict(case=0,slots=8,requests=1,layout="prefix",bond_slots=0),
        FakeSimulator(range(1,9)),list(range(1,9)),io.BytesIO(),lambda:next(wall),Clock())
    assert result["status"] == "complete"
    assert result["wall_ratio_scalar_over_batch"] == .5
    assert result["batch_wall_change_percent"] == 100


def test_suite_keeps_every_condition_and_alternates_order_without_native(tmp_path,monkeypatch):
    small_plan(monkeypatch)
    build,_ = build_file(tmp_path,monkeypatch)
    calls=[]
    def runtime(record,wheels):
        calls.append("runtime")
        return lambda spec:(FakeSimulator(range(1,9)),list(range(1,9)))
    result=bench.run_suite(tmp_path/"results",build,tmp_path,runtime,Clock(),Clock())
    assert result["status"] == "complete" and calls == ["runtime"]
    assert len(result["conditions"]) == 2
    rows=[json.loads(line) for line in (tmp_path/"results/timings.jsonl").read_text().splitlines()]
    assert len(rows) == 8
    assert [(r["case"],r["trial"],r["helper"]) for r in rows] == [
        (0,0,"scalar"),(0,0,"batch"),(0,1,"batch"),(0,1,"scalar"),
        (1,0,"batch"),(1,0,"scalar"),(1,1,"scalar"),(1,1,"batch")]
    assert result["complete_Python_sync_measured"] is False
    assert result["external_whole_attempt_wall_CPU_RSS"] is None


@pytest.mark.parametrize("field,value",[("method","other"),("native_tree","0"*40),
    ("source_commit","0"*40),("benchmark_script",{})])
def test_wrong_build_source_refuses_before_runtime_and_keeps_plan(tmp_path,monkeypatch,field,value):
    small_plan(monkeypatch)
    build,data=build_file(tmp_path,monkeypatch)
    data[field]=value
    build.write_text(json.dumps(data))
    def forbidden(*args):
        raise AssertionError("wrong identity loaded runtime")
    result=bench.run_suite(tmp_path/"results",build,tmp_path,forbidden,Clock(),Clock())
    assert result["status"] == "failed" and len(result["conditions"]) == 2
    assert all(c["status"] == "not_run" for c in result["conditions"])
    assert (tmp_path/"results/plan.json").exists()


def test_fixture_failure_retains_failed_and_unrun_conditions(tmp_path,monkeypatch):
    small_plan(monkeypatch)
    build,_=build_file(tmp_path,monkeypatch)
    def runtime(*args):
        def broken(spec):raise RuntimeError("fixture failure")
        return broken
    result=bench.run_suite(tmp_path/"results",build,tmp_path,runtime,Clock(),Clock())
    assert result["status"] == "failed"
    assert [c["status"] for c in result["conditions"]] == ["failed","not_run"]
    assert result["conditions"][0]["error"]["message"] == "fixture failure"


def test_journal_cap_refuses_without_writing_partial_records(monkeypatch):
    monkeypatch.setattr(bench,"MAX_JOURNAL",1)
    out=io.BytesIO()
    with pytest.raises(ValueError,match="timing_journal_limit"):bench.append_sample(out,{"row":1})
    assert out.getvalue() == b""


def test_only_dedicated_run_ref_activates_the_hosted_workflow():
    root=Path(__file__).resolve().parents[1]
    value=yaml.safe_load((root/".github/workflows/named-context-benchmark.yml").read_text())
    trigger=value.get("on",value.get(True))
    assert set(trigger) == {"push","workflow_dispatch"}
    assert trigger["push"]["branches"] == ["lead/named-context-benchmark-run-20261030"]
    job=value["jobs"]["benchmark"]
    assert job["if"] == "github.ref == 'refs/heads/lead/named-context-benchmark-run-20261030'"
    steps=job["steps"]
    comparison=next(s for s in steps if s.get("id") == "comparison")["run"]
    assert "set +e" in comparison and 'context_exit=$?' in comparison and 'exit "$context_exit"' in comparison
    assert "ulimit -v 2097152" in comparison and "ulimit -t 540" in comparison
    assert "timeout --signal=KILL 600s taskset" in comparison
    build=next(s for s in steps if s["name"].startswith("Build and install"))
    assert build["timeout-minutes"] == 40 and "--release --locked" in build["run"]
    wheel=next(s for s in steps if s["name"] == "Publish the separately bounded own wheel")
    assert wheel["if"] == "always() && steps.identity.outcome == 'success'"


def owner_encoder():
    root=Path(__file__).resolve().parents[1]
    value=yaml.safe_load((root/".github/workflows/named-context-benchmark.yml").read_text())
    run=next(s for s in value["jobs"]["benchmark"]["steps"] if s.get("id") == "inventory")["run"]
    lines=run.splitlines()
    assert lines[0] == "python -B - <<'PY'" and lines[-1] == "PY"
    module=ast.parse("\n".join(lines[1:-1]))
    helper=next(n for n in module.body if isinstance(n,ast.FunctionDef) and n.name == "encode_owner")
    scope={"json":json}
    exec(compile(ast.Module(body=[helper],type_ignores=[]),"<hosted-owner-helper>","exec"),scope)
    return scope["encode_owner"]


@pytest.mark.parametrize("extra,refused",[(0,False),(1,True)])
def test_owner_counts_its_own_serialized_bytes_at_boundary(extra,refused):
    value=dict(kind="synthetic-owner",files=[],evidence_retention="within_body_cap",refusal=None)
    initial=(json.dumps(value,sort_keys=True,indent=2)+"\n").encode()
    file_bytes=2048-len(initial)+extra
    result,body=owner_encoder()(value,file_bytes,2048,1024)
    assert (result["evidence_retention"] == "refused") is refused
    assert (result["refusal"] is not None) is refused
    assert len(body) <= 1024
    if not refused:
        assert file_bytes+len(body) == 2048
    else:
        assert "including owner" in result["refusal"]
    assert value["refusal"] is None


def test_oversize_owner_inventory_retains_bounded_refusal_metadata_only():
    value=dict(kind="synthetic-owner",files=[dict(path="x"*3000,bytes=1)],
        evidence_retention="within_body_cap",refusal=None)
    result,body=owner_encoder()(value,1,4096,512)
    assert result["evidence_retention"] == "refused" and result["files"] == []
    assert "member list omitted" in result["refusal"] and len(body) <= 512
