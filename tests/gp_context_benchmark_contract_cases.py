"""Explicit pure GP benchmark contracts; no compiled API attestation or process."""
from copy import deepcopy
import json
from pathlib import Path
import struct
import sys
from types import SimpleNamespace
import zipfile

import pytest
from pydantic import BaseModel
import yaml

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
import benchmark_gp_context_sync as m


@pytest.fixture
def context(monkeypatch):
    for key,value in dict(GITHUB_SHA="c"*40,GITHUB_REF=m.RUN_REF,GITHUB_RUN_ATTEMPT="1",
        GITHUB_RUN_ID="123",GITHUB_JOB="gp-fullsync-pure-contract").items():
        monkeypatch.setenv(key,value)
    monkeypatch.delenv("GITHUB_OUTPUT",raising=False)


def test_registered_matrix_and_counterbalanced_fresh_worker_dose():
    cases=m.conditions();jobs=m.schedule()
    assert len(cases)==69 and len(jobs)==414 and m.CALLS==256 and m.WARMUPS==2
    assert sum(c["requests"]==0 for c in cases)==3
    assert sum(c["layout"]=="all-missing" for c in cases)==6
    assert sum(c["layout"]=="post1-spread" for c in cases)==6
    first=[]
    for i in range(0,414,2):
        a,b=jobs[i:i+2]
        assert (a["case"],a["trial"])==(b["case"],b["trial"])
        assert a["ordinal"]==i and b["ordinal"]==i+1
        assert {a["arm"],b["arm"]}=={"scalar","candidate"}
        assert a["arm"]==("scalar" if (a["case"]+a["trial"])%2==0 else "candidate")
        first.append(a["arm"])
    assert first.count("scalar")==104 and first.count("candidate")==103
    assert len(jobs)*m.CALLS==105984
    assert len(m.encode(m.plan()))<=m.PLAN_CAP


@pytest.mark.parametrize("p,layout",[(0,"empty"),(1,"spread"),(2,"half-missing"),(50,"prefix"),(50,"all-missing")])
def test_queries_use_actual_snapshot_ids_and_declared_absence(p,layout):
    ids=[1000+7*i for i in range(512)]
    rows=m.query_rows(ids,[i//64 for i in range(512)],dict(requests=p,layout=layout))
    assert len(rows)==p
    for i,row in enumerate(rows):
        absent=layout=="all-missing" or layout=="half-missing" and i%2==1
        if absent:
            assert row["id"]==2**32-1-i and row["position"] is None and row["id"] not in ids
        else:
            assert row["id"]==ids[row["position"]] and row["id"]!=row["position"]+1
    if p==1:assert rows[0]["position"]==256


@pytest.mark.parametrize("ids",[[True,2],[0,2],[1,1],[1,2**32]])
def test_snapshot_bool_zero_duplicate_and_overflow_are_not_coerced(ids):
    with pytest.raises(ValueError,match="snapshot_identity"):
        m.query_rows(ids,[0,1],dict(requests=1,layout="spread"))


def test_missing_id_collision_is_refused_without_replacement_search():
    with pytest.raises(ValueError,match="missing_id_collision"):
        m.query_rows([1,2**32-2],[0,1],dict(requests=2,layout="half-missing"))


class Frame:
    def __init__(self,columns):self.columns=columns;self.num_rows=len(next(iter(columns.values())))
    def column(self,name):return SimpleNamespace(to_pylist=lambda:list(self.columns[name]))


class FakePA:
    @staticmethod
    def array(values,type=None):return list(values)
    @staticmethod
    def record_batch(value):return value if isinstance(value,Frame) else Frame(value)
    uint8=uint16=uint32=int8=float32=bool_=staticmethod(lambda:"explicit-fake-type")


class Model:
    def __init__(self,**values):
        self.__dict__.update(values)
        self.great_persons=[];self.utility_overrides={}


def fake_api(trace):
    class Sim:
        def __init__(self,n):
            self.ids=[1000+3*i for i in range(n)];self.civs=[i//(n//8) for i in range(n)]
        def get_snapshot(self):return Frame(dict(id=self.ids,civ_affinity=self.civs))
        def tick(self,turn,signals):
            trace.append(("tick",turn,signals))
            self.ids=self.ids[1:]+[900001];self.civs=self.civs[1:]+[7]
            return Frame(dict(event=[]))
        def apply_relationship_ops(self,batch):trace.append(("relationships",batch))
        def get_region_populations(self):return Frame(dict(alive_count=[self.civs.count(i) for i in range(8)]))
    class Bridge:
        def __init__(self,world,**kwargs):
            trace.append(("public_bridge_constructor",world,kwargs))
            self._sim=Sim(sum(r.population for r in world.regions))
    return dict(WorldState=Model,Civilization=Model,Leader=Model,Region=Model,GreatPerson=Model,
        AgentBridge=Bridge,pa=FakePA)


@pytest.mark.parametrize("layout,p,ticks",[("empty",0,0),("half-missing",2,0),("post1-spread",10,1)])
def test_public_fixture_recipe_excludes_controls_and_uses_survivors(layout,p,ticks):
    trace=[];bridge,world,info=m.fixture(dict(initial_agents=512,requests=p,layout=layout),fake_api(trace))
    constructor=trace[0]
    assert constructor[0]=="public_bridge_constructor" and constructor[1] is world
    assert constructor[2]==dict(mode="hybrid",agent_scale_mode="exact",validation_sidecar=False,relationship_stats=False)
    assert len(world.regions)==len(world.civilizations)==8
    assert [r.population for r in world.regions]==[64]*8
    assert info["alive"]==512 and sum(info["per_region"])==512
    assert len(info["controls"])==20 and len(info["rows"])==p
    assert sum(g.active for g in info["controls"])==10
    assert sum(g.agent_id is None for g in info["controls"])==10
    assert [g for c in world.civilizations for g in c.great_persons if g.active and g.agent_id is not None]==[g for g,_ in info["rows"]]
    assert sum(row[0]=="tick" for row in trace)==ticks
    if ticks:
        tick=next(row for row in trace if row[0]=="tick")
        assert tick[1]==1 and tick[2].column("civ_id").to_pylist()==list(range(8))
        assert tick[2].column("faction_cultural").to_pylist()==[.34]*8
        ops=next(row[1] for row in trace if row[0]=="relationships")
        assert ops.num_rows==8*p and ops.column("op_type").to_pylist()==[0]*(8*p)
        assert ops.column("bond_type").to_pylist()==[6]*(8*p)
        assert all(row["id"] in bridge._sim.ids for _,row in info["rows"])
        assert 1000 not in bridge._sim.ids
    else:assert not any(row[0]=="relationships" for row in trace)


class ProofModel(BaseModel):
    payload:list


@pytest.mark.parametrize("change",["negative_zero","private","extra","fields_set","alias","order"])
def test_complete_GP_proof_detects_bits_private_fields_and_container_aliases(change):
    shared=[];gp=ProofModel(payload=[0.0,shared,shared,{"a":1,"b":2}])
    world=SimpleNamespace(civilizations=[SimpleNamespace(great_persons=[gp])])
    before=m.digest(m.full_gp_state(world,BaseModel))
    if change=="negative_zero":gp.payload[0]=-0.0
    elif change=="private":object.__setattr__(gp,"__pydantic_private__",{"hidden":1})
    elif change=="extra":object.__setattr__(gp,"__pydantic_extra__",{"hidden":1})
    elif change=="fields_set":gp.__pydantic_fields_set__.add("another")
    elif change=="alias":gp.payload[2]=[]
    else:gp.payload[3]={"b":2,"a":1}
    assert m.digest(m.full_gp_state(world,BaseModel))!=before


def test_payload_proof_keeps_signed_zero_NaN_payload_and_legacy_bits():
    nan1=struct.unpack("!d",bytes.fromhex("7ff8000000000001"))[0]
    nan2=struct.unpack("!d",bytes.fromhex("7ff8000000000002"))[0]
    def raw(value,legacy):return [(7,[(1,2,3,-4,5,legacy)],(value,)*6,[(9,-2,6,3)])]
    assert m.payload_digest(raw(0.0,False))!=m.payload_digest(raw(-0.0,False))
    assert m.payload_digest(raw(nan1,False))!=m.payload_digest(raw(nan2,False))
    assert m.payload_digest(raw(nan1,False))!=m.payload_digest(raw(nan1,True))


def test_rng_proof_uses_Gaussian_cache_bits_without_NumPy_import():
    array=SimpleNamespace(dtype=SimpleNamespace(str="<u4"),shape=(2,),strides=(4,),tobytes=lambda order:b"fixed")
    def state(cache):
        random=SimpleNamespace(getstate=lambda:(3,(1,2),cache))
        np=SimpleNamespace(random=SimpleNamespace(get_state=lambda:("MT19937",array,2,1,cache)))
        return m.digest(m.rng_state(random,np))
    assert state(0.0)!=state(-0.0)


def test_passive_profile_is_restored_after_action_exception():
    previous=sys.getprofile()
    assert previous is None, "registered ordinary-guard process must be unprofiled"
    def action():raise RuntimeError("first action fault")
    with pytest.raises(RuntimeError,match="first action fault"):
        m.observe_calls(object(),action)
    assert sys.getprofile() is previous


def test_full_sync_clock_preserves_all256_calls_and_zero_CPU():
    calls=[]
    sample=m.timed_sync(lambda:calls.append(None),wall=iter([100,500]).__next__,cpu=iter([10,10]).__next__)
    assert len(calls)==256 and sample["completed_calls"]==256
    assert sample["wall_start_ns"]==100 and sample["wall_end_ns"]==500 and sample["wall_ns"]==400
    assert sample["CPU_ns"]==0 and sample["error"] is None


def test_first_sync_exception_keeps_partial_call_count_and_raw_endpoints():
    calls=[]
    def action():
        calls.append(1)
        if len(calls)==3:raise MemoryError("allocation before candidate updates")
    sample=m.timed_sync(action,wall=iter([10,20]).__next__,cpu=iter([2,7]).__next__)
    assert len(calls)==3 and sample["completed_calls"]==2
    assert sample["error"]["type"]=="MemoryError" and sample["CPU_ns"]==5


def worker_rows(job):
    spec=m.conditions()[job["case"]];p=spec["requests"];n=spec["initial_agents"]
    source=m.query_rows([1+3*i for i in range(n)],[i//(n//8) for i in range(n)],spec)
    missing=[row["position"] is None for row in source]
    end=dict(kind="worker_end",ids=[r["id"] for r in source],positions=[r["position"] for r in source],
        precursors=[r["precursor"] for r in source],alive=n,per_region=[n//8]*8,
        setup_ticks=int(spec["layout"]=="post1-spread"),payload="a"*64,
        memories=[0]*p,legacy=[0]*p,bonds=[None if x else 0 for x in missing],needs=p-sum(missing),
        initial_gp="b"*64,warm_gp="c"*64,final_gp="c"*64,control_gp="b"*64,native_before="d"*64,native_after="d"*64,
        rng_before="e"*64,rng_after="e"*64,schema=[1,"f"*64,"a"*64],
        diagnostic_counts=[p,p,p,0] if job["arm"]=="scalar" else [0,0,0,int(p>0)])
    return [dict(kind="worker_start",**job,pid=123),dict(kind="timing",wall_start_ns=10,
        CPU_start_ns=4,CPU_end_ns=4,wall_end_ns=20,wall_ns=10,CPU_ns=0,completed_calls=256,error=None),end]


@pytest.mark.parametrize("fault",["bool_id","missing_position","negative_count","legacy_count","too_many_bonds",
    "wrong_population","negative_region","needs_count","native_mutation","wrong_dose","clock_join","wrong_PID"])
def test_worker_protocol_rejects_real_identity_dose_and_payload_corruption(fault):
    job=dict(ordinal=36,case=6,trial=0,arm="scalar");rows=worker_rows(job)
    if fault=="bool_id":rows[2]["ids"][0]=True
    elif fault=="missing_position":rows[2]["positions"][1]=511
    elif fault=="negative_count":rows[2]["memories"][0]=-1
    elif fault=="legacy_count":rows[2]["legacy"][0]=1
    elif fault=="too_many_bonds":rows[2]["bonds"][0]=9
    elif fault=="wrong_population":rows[2]["alive"]+=1
    elif fault=="negative_region":rows[2]["per_region"][0]=-1
    elif fault=="needs_count":rows[2]["needs"]=2
    elif fault=="native_mutation":rows[2]["native_after"]="f"*64
    elif fault=="wrong_dose":rows[1]["completed_calls"]=255
    elif fault=="clock_join":rows[1]["wall_ns"]=9
    else:rows[0]["pid"]=124
    with pytest.raises(ValueError):m.parse_fragment(b"".join(m.encode(r) for r in rows),job,123)


@pytest.mark.parametrize("key",["payload","initial_gp","warm_gp","final_gp","control_gp","native_before","rng_before","schema"])
def test_pair_requires_full_GP_CP_RNG_and_payload_parity(key):
    a=dict(ordinal=0,case=0,trial=0,arm="scalar");b=dict(ordinal=1,case=0,trial=0,arm="candidate")
    left=m.parse_fragment(b"".join(m.encode(r) for r in worker_rows(a)),a,123)
    right=m.parse_fragment(b"".join(m.encode(r) for r in worker_rows(b)),b,123)
    m.join_pair(left,right)
    right["proof"][key]=[2,"different"] if key=="schema" else "0"*64
    with pytest.raises(ValueError,match="full_GP_payload_CP_RNG_pair"):m.join_pair(left,right)


def test_actualP50_records_fit_registered_joint_fragment_and_journal_bounds():
    jobs=[j for j in m.schedule() if m.conditions()[j["case"]]["requests"]==50]
    for job in jobs:
        rows=worker_rows(job)
        assert len(m.encode(rows[0]))<=256 and len(m.encode(rows[1]))<=512 and len(m.encode(rows[2]))<=2816
        assert sum(len(m.encode(r)) for r in rows)<=4096
    assert 414*(128+256+512+2816)<=m.JOURNAL_CAP
    assert sum([64,64,1536,128,16,8,4,16])*1024<m.BODY


def test_wall_regressions_and_zero_CPU_are_retained_without_adoption_threshold():
    records=[]
    for trial in range(3):
        for arm,wall in (("scalar",100),("candidate",200)):
            records.append(dict(case=0,trial=trial,arm=arm,timing=dict(wall_ns=wall,CPU_ns=0)))
    result=m.summaries(records)[0]
    assert result["status"]=="complete" and result["scalar_over_candidate"]==.5
    assert result["paired_wall_ratios"]==[.5]*3 and result["CPU_ratios"] is None
    records[0]["timing"]["wall_ns"]=0
    refused=m.summaries(records)[0]
    assert refused["status"]=="numerical_refused" and "scalar_over_candidate" not in refused


def test_full_worker_CPU_reservation_is_required_before_launch():
    assert m.paired.credit_admits(488000000)
    assert not m.paired.credit_admits(488000001)
    assert not m.paired.credit_admits(True)


@pytest.mark.parametrize("unknown",[False,True])
def test_postterminal_group_closure_excludes_only_stable_parent_members(unknown):
    clock=[0.0];members={1:11,2:22,3:33};kills=[]
    def kill(pid,stamp):
        kills.append((pid,stamp))
        if not unknown:members.pop(pid)
    def pause(seconds):clock[0]+=seconds
    result=m.settle_worker(5,2,{1:11},members=lambda group:dict(members),kill=kill,
        now=lambda:clock[0],pause=pause)
    assert (3,33) in kills and all(pid!=1 for pid,_ in kills)
    assert result["proven"] is (not unknown)


def test_reused_parent_PID_identity_is_not_exempted():
    members={1:99,2:22};killed=[]
    def kill(pid,stamp):killed.append((pid,stamp));members.pop(pid)
    clock=[0.0]
    result=m.settle_worker(5,2,{1:11},members=lambda group:dict(members),kill=kill,
        now=lambda:clock[0],pause=lambda delay:clock.__setitem__(0,clock[0]+delay))
    assert result["proven"] and killed==[(1,99)]


@pytest.mark.parametrize("raises",[True,False])
def test_partial_backend_failure_preserves_intent_unknown_exit_and_no_child_read(tmp_path,monkeypatch,context,raises):
    evidence=tmp_path/"evidence";evidence.mkdir();output=evidence/"comparison"
    job=m.schedule()[0];monkeypatch.setattr(m,"schedule",lambda:[job])
    original_stat,original_read=Path.stat,Path.read_bytes
    unsafe=[False]
    def guarded_stat(path,*args,**kwargs):
        if unsafe[0] and path.name=="active.jsonl":raise AssertionError("unsafe active stat")
        return original_stat(path,*args,**kwargs)
    def guarded_read(path,*args,**kwargs):
        if unsafe[0] and path.name=="active.jsonl":raise AssertionError("unsafe active read")
        return original_read(path,*args,**kwargs)
    monkeypatch.setattr(Path,"stat",guarded_stat);monkeypatch.setattr(Path,"read_bytes",guarded_read)
    class Backend:
        def run(self,job,build,fragment):
            fragment.write_bytes(b"partial\n");unsafe[0]=True
            if raises:raise OSError("after partial writer")
            return dict(cpu_us=3,quiescent=False,returncode=-9,pid=123,maximum_RSS_kib=1)
        def close(self):pass
        def total_cpu_us(self):return 3
    result=m.run_schedule({},output,Backend(),wall=lambda:0,cpu=lambda:0,admission=lambda p:None)
    assert not result["child_namespaces_quiescent"] and result["status"]=="failed"
    assert result["workers"][0]["status"]==("FAILED_UNKNOWN_EXIT" if raises else "FAILED")
    if not raises:assert result["workers"][0]["exit"]==-9
    assert result["completed_workers"]==result["retained_timing_rows"]==0
    assert json.loads((output/"journal.jsonl").read_text().splitlines()[0])["kind"]=="launch_intent"
    assert (output/"result.json").exists()


def test_owner_unknown_custody_never_reads_or_archives_active_file(tmp_path,monkeypatch,context):
    root=tmp_path/"evidence";comparison=root/"comparison";comparison.mkdir(parents=True)
    (root/"plan.json").write_bytes(b"{}\n")
    (comparison/"result.json").write_text(json.dumps(dict(child_namespaces_quiescent=False,status="failed",
        completed_workers=0,retained_timing_rows=0)))
    (comparison/"active.jsonl").write_bytes(b"possibly active bytes")
    original=Path.read_bytes
    def checked(path):
        if path.name=="active.jsonl":raise AssertionError("unsafe read")
        return original(path)
    monkeypatch.setattr(Path,"read_bytes",checked)
    result=m.owner(root,tmp_path/"no_wheel",-9)
    assert result["child_custody"]=="UNKNOWN" and result["unknown_active_reserved_bytes"]==4096
    assert result["wheels_allowed"] is False
    with zipfile.ZipFile(tmp_path/"gp-fullsync-compact.zip") as z:
        assert "comparison/active.jsonl" not in z.namelist() and "owner.json" in z.namelist()


def test_host_observations_have_explicit_thresholds_and_scope(tmp_path):
    row=m.host_admission(tmp_path,available=1920*1024**2,free=3*1024**3)
    assert "not aggregate/cgroup" in row["scope"]
    with pytest.raises(ValueError):m.host_admission(tmp_path,available=1920*1024**2-1,free=3*1024**3)


def test_disabled_mode_creates_nothing_and_does_not_look_up_Native(capsys,monkeypatch):
    monkeypatch.setattr(m,"current_source",lambda:pytest.fail("disabled identity call"))
    monkeypatch.setattr(m.paired.b,"compiled_module",lambda:pytest.fail("Native discovery"))
    assert m.main([])==0 and json.loads(capsys.readouterr().out)["status"]=="disabled"


def test_optin_workflow_selectors_preserve_standard_and_semantic_gate_separation():
    workflow=yaml.load((ROOT/".github/workflows/gp-context-benchmark.yml").read_text(),Loader=yaml.BaseLoader)
    assert workflow["on"]["push"]["branches"]==[m.RUN_REF.removeprefix("refs/heads/")]
    assert workflow["permissions"]=={"contents":"read"}
    job=workflow["jobs"]["gp-fullsync"]
    assert job["timeout-minutes"]=="120" and m.RUN_REF in job["if"]
    steps=job["steps"]
    run="\n".join(s.get("run","") for s in steps)
    assert "--signal=KILL 600s" in run and "--cpu=540:540" in run and "--as=2147483648:2147483648" in run
    assert "--execute" in run and "--owner" in run and "maturin build --release --locked" in run
    assert all("continue-on-error" not in s for s in steps)
    standard=yaml.load((ROOT/".github/workflows/tests.yml").read_text(),Loader=yaml.BaseLoader)
    assert "lead/gp-fullsync-tests-20261030" in standard["on"]["push"]["branches"]
    assert m.RUN_REF.removeprefix("refs/heads/") not in standard["on"]["push"]["branches"]
    semantic=yaml.load((ROOT/".github/workflows/workflow-semantics.yml").read_text(),Loader=yaml.BaseLoader)
    assert "lead/gp-fullsync-semantics-20261030" in semantic["on"]["push"]["branches"]
    assert "lead/gp-fullsync-semantics-20261030" in semantic["jobs"]["actionlint"]["if"]
