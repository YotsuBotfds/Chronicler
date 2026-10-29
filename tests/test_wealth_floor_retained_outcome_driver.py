"""Original source fragments / fixed orchestration, with no scientific stages.

The tiny fake stages never create a world or checkpoint. Real checkpoint metadata
safety is separately covered by test_wealth_floor_outcome_checkpoints.py.
"""
import ast
import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest
from scripts import wealth_floor_retained_outcome_driver as D
from scripts import wealth_floor_outcome_qualification as O
from scripts import m53b_run_validation as CONTROL

ROOT=Path(__file__).resolve().parents[1]
FIXTURE=ROOT/"tests/fixtures/wealth_floor/source503_m53b_run_validation.py.txt"
RAW=FIXTURE.read_bytes()


def parser_runner():
    # Existing control differs from503 only by a summary-only forwarding fix.
    # The tested parser executes the exact pinned503 source fragment, not main.
    return SimpleNamespace(**vars(CONTROL))


def original_call(name):
    tree=ast.parse(RAW)
    if name=="run_ablation_arms":
        scope=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=="run_arms")
    else:
        scope=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=="main")
    return next(n for n in ast.walk(scope) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id==name)


def driver_call(name):
    tree=ast.parse(Path(D.__file__).read_bytes())
    scope=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=="run_stages")
    return next(n for n in ast.walk(scope) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr==name)


def test_fixture_is_exact_source503_and_fragments_are_original_nodes():
    assert hashlib.sha256(RAW).hexdigest()==D.RUNNER_SHA256=="42030add6479c784546261b341686a11b481ab1b0c125bfe4ca0b6925739198a"
    prefix,summary=D.source_fragments(RAW)
    assert hashlib.sha256(ast.dump(prefix,include_attributes=False,show_empty=True).encode()).hexdigest()==D.PARSER_AST_SHA256
    assert hashlib.sha256(ast.dump(summary.body,include_attributes=False,show_empty=True).encode()).hexdigest()==D.SUMMARY_AST_SHA256
    before=ast.dump(ast.parse(RAW),include_attributes=True)
    D.source_fragments(RAW)
    assert ast.dump(ast.parse(RAW),include_attributes=True)==before


@pytest.mark.parametrize("what",["comment","parser","summary"])
def test_unregistered_source_or_fragment_edit_is_refused(monkeypatch,what):
    changed=RAW+b"\n# unreviewed source\n" if what=="comment" else RAW.replace(
        b'"--seed-start", type=int, default=42',b'"--seed-start", type=int, default=43') if what=="parser" else RAW.replace(
        b'"gate_status": "PASS" if',b'"gate_status": "UPDATED" if')
    assert changed!=RAW
    if what!="comment":monkeypatch.setattr(D,"RUNNER_SHA256",hashlib.sha256(changed).hexdigest())
    with pytest.raises(D.P.ProofRefused):D.source_fragments(changed)


@pytest.mark.parametrize("name",["run_subset","run_full","validate_batch"])
def test_original_parent_and_validator_argument_asts_are_unchanged(name):
    old,new=original_call(name),driver_call(name)
    assert [ast.dump(a,include_attributes=False) for a in old.args]==[ast.dump(a,include_attributes=False) for a in new.args]
    assert {k.arg:ast.dump(k.value,include_attributes=False) for k in old.keywords}=={
        k.arg:ast.dump(k.value,include_attributes=False) for k in new.keywords}


def test_arm_call_only_adds_existing_delete_checkpoints_false():
    old,new=original_call("run_ablation_arms"),driver_call("run_ablation_arms")
    assert [ast.dump(a,include_attributes=False) for a in old.args]==[ast.dump(a,include_attributes=False) for a in new.args]
    before={k.arg:ast.dump(k.value,include_attributes=False) for k in old.keywords}
    after={k.arg:ast.dump(k.value,include_attributes=False) for k in new.keywords}
    assert after.pop("delete_checkpoints")==ast.dump(ast.Constant(False),include_attributes=False)
    assert after==before


@pytest.mark.parametrize("worldgen,stage",[(w,s) for w in ("template","procedural") for s in ("smoke","full")])
def test_exact_original_parser_defaults_and_fixed_vectors(monkeypatch,tmp_path,worldgen,stage):
    helpers=O.scientific_helpers(ROOT)
    command=O.runner_command("PY",Path("SOURCE"),worldgen,tmp_path/"raw",stage,helpers)
    monkeypatch.setattr(sys,"argv",["detached-driver",*command[2:]])
    runner=parser_runner();before=dict(vars(CONTROL))
    args=D.parse_original(runner,RAW);expected=helpers.expected(worldgen,stage)
    assert vars(CONTROL)==before
    assert args.profile==expected["profile"] and args.worldgen==worldgen and args.parallel==2
    assert args.seeds==expected["seed_count"] and args.turns==expected["turns"] and args.seed_start==42
    assert args.require_strict_regression is expected["require_strict_regression"]
    assert args.baseline_report is None and not args.fail_on_regression and not args.exploratory_comparison
    assert runner.ablation_arms_for(args)==["needs","kin_roots"] and runner.ablation_enabled(args)


@pytest.fixture
def stages(monkeypatch,tmp_path):
    calls=[];helper=O.scientific_helpers(ROOT);config=helper.expected("template","smoke")
    command=O.runner_command("PY",Path("SOURCE"),"template",tmp_path/"raw","smoke",helper)
    monkeypatch.setattr(sys,"argv",["driver",*command[2:]])
    runner=parser_runner();args=D.parse_original(runner,RAW)
    batch=tmp_path/"raw/oracle_subset/batch_42"
    def parent(*values):calls.append(("parent",values));return batch
    def arms(*values,**kw):
        calls.append(("arms",values,kw));return dict(status="complete",fork_count=4,seconds=1.0,fork_turns=[100])
    def validate(*values,**kw):
        calls.append(("validate",values,kw));return dict(report_path=batch/"validate_report_subset.json",decision_path=batch/"gate_decision_subset.json",
            summary_path=batch/"gate_summary_subset.md",decision=dict(ok=False,exit_code=2),comparison=None,batch_manifest_status="verified")
    runner.run_subset=parent;runner.run_ablation_arms=arms;runner.validate_batch=validate
    runner.atomic_write_json=lambda path,value:calls.append(("write_summary",path,value))
    runner._format_gate_failure=lambda _value:"fixture scientific FAIL, not an actual gate"
    monkeypatch.setattr(D.K,"capture",lambda *a,**k:(calls.append(("capture",a,k)) or ({"fixture_only":True},"a"*64)))
    monkeypatch.setattr(D.K,"retire",lambda *a,**k:calls.append(("retire",a,k)))
    return SimpleNamespace(calls=calls,runner=runner,args=args,config=config,root=tmp_path)


def run(stages):
    return D.run_stages(stages.args,stages.runner,RAW,stages.config,stages.root,
        current_identity={"fixture_only":True},compare_identity=lambda *_:[],clock=lambda:1.0)


def test_capture_precedes_forks_and_retirement_precedes_original_validation_even_scientific_fail(stages):
    assert run(stages)==2
    assert [c[0] for c in stages.calls]==["parent","capture","arms","retire","validate","write_summary"]
    arm=next(c for c in stages.calls if c[0]=="arms")
    assert arm[2]["delete_checkpoints"] is False and arm[2]["parallel"]==2 and arm[2]["arms"]==["needs","kin_roots"]
    summary=stages.calls[-1][2]
    assert summary["gate_status"]=="FAIL" and summary["gate_exit_code"]==2
    assert summary["causal_oracles_required"] is False and summary["exploratory_comparison"] is False
    assert summary["ablation_forks"]==4 and summary["ablation_fork_turns"]==[100]


@pytest.mark.parametrize("failure",["capture","arms","retire"])
def test_phase_failure_prevents_later_science_or_retirement(monkeypatch,stages,failure):
    def refused(*_a,**_k):
        stages.calls.append((failure,));raise D.P.ProofRefused("synthetic phase refusal")
    if failure=="capture":monkeypatch.setattr(D.K,"capture",refused)
    elif failure=="retire":monkeypatch.setattr(D.K,"retire",refused)
    else:stages.runner.run_ablation_arms=refused
    with pytest.raises(D.P.ProofRefused):run(stages)
    names=[c[0] for c in stages.calls]
    assert "validate" not in names and "write_summary" not in names
    if failure=="capture":assert "arms" not in names and "retire" not in names
    if failure=="arms":assert "retire" not in names


def test_default_and_null_registration_cannot_import_scientific_runner(monkeypatch,capsys):
    monkeypatch.setattr(D.V,"REVIEWED_PREREQUISITES",{key:None for key in D.V.PREREQUISITE_KEYS})
    monkeypatch.setattr(D.V,"REVIEWED_PRIMER",{key:None for key in D.V.PRIMER_KEYS})
    monkeypatch.setattr(D.V,"REVIEWED_WORKER_SMOKES",{key:None for key in D.V.WORKER_KEYS})
    monkeypatch.setattr(D.V,"ROOT_PREREQUISITE_PACKET_SHA256",None)
    monkeypatch.setattr(D.V,"ROOT_WORKER_SMOKE_PACKET_SHA256",None)
    monkeypatch.setattr(sys,"argv",["driver"])
    assert D.main()==0 and json.loads(capsys.readouterr().out)["status"]=="inactive_source_only"
    monkeypatch.setattr(sys,"argv",["driver","--profile","subset","--worldgen","template","--output-root","unused"])
    def forbidden(*_a,**_k):pytest.fail("source/path read before phase admission")
    monkeypatch.setattr(D.P,"read_bytes",forbidden);monkeypatch.setattr(D.P,"read_json",forbidden)
    with pytest.raises(D.P.ProofRefused,match="remain NULL"):D.main()


@pytest.mark.parametrize("fault",[None,"stage","world","registration","producer","attempt","old","future","control"])
def test_owned_parent_marker_content_contract(monkeypatch,fault):
    registered=dict(fixture_only=True,stage="smoke")
    monkeypatch.setattr(D.V,"ROOT_PREREQUISITE_PACKET_SHA256","a"*64)
    value=dict(stage="smoke",worldgen="template",source_sha=D.B.CANDIDATE_SOURCE,control_sha="b"*40,
        registration_sha256=D.B.digest(registered),prerequisite_packet_sha256="a"*64,admitted_monotonic=99.0,
        producer=dict(ref="refs/heads/"+O.SMOKE_BRANCH,job_key="smoke",run_id="12",attempt="1"))
    if fault=="stage":value["stage"]="full"
    elif fault=="world":value["worldgen"]="procedural"
    elif fault=="registration":value["registration_sha256"]="0"*64
    elif fault=="producer":value["producer"]["ref"]="refs/heads/main"
    elif fault=="attempt":value["producer"]["attempt"]="2"
    elif fault=="old":value["admitted_monotonic"]=1.0
    elif fault=="future":value["admitted_monotonic"]=301.0
    elif fault=="control":value["control_sha"]="invalid"
    if fault is None:
        assert D.execution_marker(value,registered,"smoke","template",O.SMOKE_BRANCH,now=101.0)
    else:
        with pytest.raises(D.P.ProofRefused):D.execution_marker(value,registered,"smoke","template",O.SMOKE_BRANCH,now=300.0)
