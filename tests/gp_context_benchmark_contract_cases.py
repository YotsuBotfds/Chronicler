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


# Observed native a840 functional428 raw tuple, not a current compiled0dca observation.
# original.zip SHA3b8c6237...; observation.json SHA cab3285f...; source/schema equality
# audit and exact complete-schema pins are recorded in SCHEMA_AUDIT.json.
_SCHEMA_FIXTURE_B85 = b'ABzY8000000t1~|ZExH*68?Vw;_@j0_Ji%DId@wJ$T@BAa80kUgZp9_0$1YhGL}S@qP*TL{NL}H8Iq#3n_O`SlB{MZzRc@0L*1P(UR34!tbG0E?EAl!mzQt8JAbiw@qVLQe`}hdR^GZpXKlS?+VA*vFjc?&k1l^4USGUhIK45p4TSTz?-tgXjcJP`dTAaDwO*Unc%uXT62r@K=#(GFf>ztTs?(@7Ez@I2zgFcqP{<FauCr&g(b<xf>APB$y1~v1Ke&7ev(|-v1Y@Li&Nh}7DDZ3JbU(6IwyxSpkd>O1p|K-HcD*mWQ^t?va;UMis*6We54t!@bIus&Ut?U1yU?}K>ukfy(aB5|XQlN<;`vD2X>4sfZmQ9Zb$by&;rCsT+TC#Z!{vQq_jYilE}*%S>`|h35O>Zot=DZoD*Db$UaWMf_62Fvx|1_+l+R2g5KB9>eoi!fQR|H=_lePJT@}4rYrh}Q%ftq=I-}|txwqvBVrQK3!x3E#-nO=xPu&f!v%MavPS=H3Zlg&P@r<u8_>jcwA$Zdy^NRu^*2=ck37rsYZC!)aP6(d3Qvvn+)^BwW0j-7#`$&wZahKUKdhLBJo|62Ve5kRHC#c?;uIRQZ9GRwNQl)zzTz@ur5*B8>jkS<?ZT)nz67sXfAGscx&c`owt-4-U^F66x<}8`>xAz$xmeNjFU}`zI-n!AL9>gOG1vPAKH)`R{y>NqDWJlq}W^CH!F*AC`{%f<s*(NOIoOvXjZ=uOF=L&H+oMCGleI!;@<E3n*n8whXFB%5>MA}@!92aY+HA_C|mIl0AJWrzf4gbFN@ScOv`R((!3%C<vUAr7E7tod4n|1@Gb*iNE(SXi&ltO50^w?WdFQLc9jy#cn!J^4zN?4f?RP`AVyNwRbnZvf;*}B$_rGwQFVk;cl4qgYV2N4qm$+Pc}0AJsa)V<L)O!y9qOz8Nb-J{Mqklq)F9CC7!ahCt?=)WJs5b_q)TRyn_Vu@f2kh;s<M7Nc0ObKrXorFRsl<=-$3Ru;%Z_z5y7wIZLEyw?K5-@0XlD~ueWUi4GqK)JTR*7x@7(}>fP`*&3K3m#U_6i)j@Ve>hFr>q4x*Rwsj+RRcCk|A;M!ws!EJ_$@6V~&^8u|1D*;^v66+)TAtR>lRV=J>Z$tEZq48RJdVM`z)2A5j}Sv5E(Y;HmmOE|?5OOaJ%a;!`Fy&6aqNhg_!;l0ho;aC(q<%%7Nc}j*5bagzsR9^L%vD<3IL`0cB8$qrBXad90#R~t_rVZK*zB3g^vQ!!?W_)bLdcD@H+pi7ihrT2I!D{bli^L>#8^o85xG3+OXbm>h%cB?!5>Gkwq_)oKM?OU{`Y^dQL<)FBW{qQO^{_NxkW-IN6ghWBwgz$Fz{VrT@={`WJdrmWkx1`t`Oq2IBOmB{ctLF_kHa~UaIqc_+bZ&4#Lz8<izrEq2tE>TAZtH+TGwW?^}!Qjj%)RfPdOoEmQO6@9^hv1Yvc#n)tmcB?T4<b_la6Mwf0ArEapuSL5ECE27x2=+rkaCoCtCClvz1l8Gxo@<BWb(Z7GAFB}PI5cqI?r68syOA`H6+P?1=2aldGXCXJM|Ag0OowlPrEe)*dM*to{Vpg-+y0{KuzimWjmbx<1t3o@0(amE?&^zs+oYGB)|v&F~YqgUsPTM`cdzQ4Ly{LWtEuU;>HdV=Dw-Yi~m?I000z=)BsvarSERwINzMZ&uq*escGhMZ}mIcTP5h#g{<9Q2ZA!8`Qdt9K;q=LJ_Wk|siUV1Qj9ES7YVI<H+Guwe#u2$VHUwwKfkET@8BDCFOt<1=O2{y;DE0r2s7A?QZ~QRWmxlHS$?5uhCeHL4s=vN;Zg(;7!pA-$+LS)joy%nC{)QbX8-Dyn=NkyxCXWX5#*v!>kwqx2+`Z;nBXh5>(b2+rc!=xI>tY~QmXq<u2IhdrJk%WzIrr(QV4c$R2)T75N~s_>?K2=RSJTp4#v6jVkugb!4hs@nn_RC+aRmLEpS2O=Co+Smi$Y{ENCP!;e)PC&RPqaF!6I!Z_|IUROTA*mFIe#mB%DN4)H84}uf@qk9Fwg~t|QmT5IJg<?<q0?fuFHplTxw`r8K9Na%-uhsRh}J=cBCK^z3$mKfwm3Dmnhg&W8O&$gQljI4t|(F?LHjMvu*ETh{&23^Zm4u@*JiW)Ngl8H>A-2L(hzzj`7h-%rx}k1;DKaV{O_>^urA>;V+F<{LPwy-<6uEUAFv6e0z<;Scy7e>p-huDnu4PFBB6l?G^Ft3L^~e#Ye~33t~8!g@sypNWSpH7dQkyOQDPh^6KRZaK>$E@u8b8X8Rsq$BMB<XJ2hM}EZ`a<`=PCz3fzqfAWj~oO@J+<>^3d+qb7wz4ZUNEoQ4GE><+OmUpeq9)u@0i0%fYV*%WC@5pQ!85wI1fOjXS(=2S@$^~HLC0MLXXosk6Z*ERA|LDI+EyNX3MnefDbzB3Q`+Ys^oh$zRJQ$sB?k}C~F<|h@0e%h*mfd<lP`2bH}$08|!RjQ^izUgLrO;A*=pl*ueY#*kpBho#I7c(QC@fqnN<+jvz6N|BcVaOOr!+|@r;oVA$M#Mm8YMJn6HW~pZHiI0{1I(Pjob#7vJB=k}fSW0zOzD&J5U<=K_fm5tfbnN3FcDWf4rI$4di)fg4q5dXD^RKBQT%jVD*LD9O?<j0#Q5Y7@qE(FnOC$(@1}~Y_tdCWHKEVY47wG{FCZLB9b2)n?Z{wBc@{(L^hr12eIgzJ<BfE6?_RPg;_s^;F7E-U2%(3%9M7SwPp^K$^GlWhz~r?>mIac$2}X7XBpH97153u=7r>LBxX`%zZgDN;$JN`#N5=10f0LC{O99)DXFfuFoYo_^0%}+WVSK>vmH<!LAGX%_o%PbBpj3I(sEMa3q!At)AK}pNs2(F+@>Gy`XM=c#-cn6%fMKXYd;3Px9`z`*v`3F2?Qs>^!FP2m<U<)&P+<~^k6mh(vM&YXz|4Ah8Yta?ETDH^Fy_yhQXS2_j9WzfUaZbjL4Mo_Kz(Loq(40%hR#`IplAt4lb+;l57DLICEWl-H3Bk_;%tYsH||AZ?vQr^zNkGXPlPs!5gC(olk>u=-nOmOkUT*3eE^O*3)!fP$t$Nzs{~RFO3HbxI^;bHu(karduyaTTp&Ogvd3r<zlZ0DgfyUcA4-vxsVOs!l41BTju;U3OkH#Qo(@8#^|U8wS&YL+cyMYFj+fK<Yvi8VY)K2V>=2p-{L(lFzy1jEDhj77I0-K+Ms8R9<`J7A7q#u<h_wcW7S#fqnbc!9Q=Wb@eztVRb+CGb3Ch8fA(UEd7&F~i&Y>{9X^o#s&F>61Dv&hc=$)V|U2@Av1Q(D*fbW%gG<`JN8Lux@=q?=Lk3^Ws{5iiD7{k6a*U!!<KG~tyWCEd#{YQM3GS;+PnpmvGskUEJenw0jLTz$-K)E#m#OM4_WWxX?bc|~^W+P&xTD7k2POA7*{F0`sYwnZ;d-yYhvyR?ucnl|=aTsJ296eMjTvL**af>164DAVCS{xu+^7+R|`M?B`>$L8MMNqqle-AB+s2YYCo&~Yot>3=+;o|Im!J!IkalJ+ai`}Q{je%||<yexmg)}%UM460WbR79;YvebD@IGT8WH$uC5KoNm6Zsi`QrzaMH+I->sFV8(Q4Xs5oX`aKU^wkEJOHvdZeZzZlWqf;03cH!PGQ}Tstau#>ftQpUY2f`me=%e2!l0s^w=#;yp6yV5+4xpA_{tbH}3uao+Qms)3#ka{_R#(cK0jO4gpJ7BOv%54rf~N6GS4&YRV%+r1(>5>NL3hl$&onjwn{cIxhYp(EdK4gmH&%yYCG`M!`*3**I)nIWHyT%EZgdxB%Z(5mstCfD&Q87aGA%R~@ETXWR(SZVc&pybA>W`Xk`_XS(3zuCsJNXX{oY;#$T-<S2~$5JlSi>}}zOy`SXC+9z326<oN@#61x>-_=QojE&DvAc;4JE<240-6~5EHB?!FrXDvkOEtI*Y4A2Oqlhw-JCVU7e|#B-qtJ9i7ZMJ_MB9g;u`>W{!F#yzt~l(;MQkE-r3s%lJ|prph+!o+#>wv6j1If;2%JbXL~AWzs#;N>pT~z59C@nUNJ*j9H5JmZ;{)9w<;LM{{xrQ({?o?9pd*<4ulRk#_0G#rBEJu$NE8$|%2cQ)J|uaept$W&v?08qo{&ax?9wM4Jue<wyJMdY%Kle;7EOm!lO1QRSD`t*CO9>tvR)zZ`DjFW<L0!iI~-{ha#j~;<Qh>?qy8Aahqhs^m9R%fdCE^o1f(Yv$E{;KOkb4?6+zzd6#0A;a+))zPUp=zX>M*+#;y*bZTg)Ue1#u5{4nHI!`F;=HehPSiFw+b#~fa6E#P>cE)`e%{Pf=(7Y;7FiQg7sgKN?$(0v#MH{A!*+wNCDA4RPGP${KrTuBRZMLc$4)8|3)z6-G_{JI(V`;>!j>2#swb#^B&rBQZw$UYEZpM&Z(w+>+c8*V6so9S?OuV9U;4$Zcqt#W^50@Zrq`iL*4MV&k|WQ_DUad~GbQsk8R_4D-JdBn3km@0hicY3T_P>#+uSs}U(y)H35zAEvYdi0rm)rK$ZVk#fPR|KXF7b_Dg-#JR66vl5L-174wkA?Aq>j9Bl&Y5<_^PK*2r_s$SeWO5o`)nC1rsw>#8hRF;RQVTwHT5cEkKIx8tclGX`b}1mtRQGTS91JZfUhkHB#kKVk}ld_aoZ{yZ8`>4t>VsKa?+xqY20|v$DfA9PtO?kedLeD{z><^KHN}BRuJGAFC8X#m*cl_Y&PT9Id~dxgw5q*`~)pPr19gnR1w5{LmwDD)2{hG$ad2B`h*7=&>y%+6W^7uFzNXt9$)_SggKF!ewI$xE2_8Gbk!1@P}B(uxAv>>)eW+lp|bjYARHRiKLqD=zDRez&lyrj$+NZGQ@@V1_mMP>2kW7(!|+foJ}>^-w=keB^}MKmxp;nY|Cj#){;f*7W-0&x'

def raw_schema_fixture():
    import base64
    import gzip
    return json.loads(gzip.decompress(base64.b85decode(_SCHEMA_FIXTURE_B85)))

def fixture_packages_digest():
    return m.digest({"fixture-only-dist":"1"})


def parse_rows(data,job,pid):
    return m.parse_fragment(data,job,pid,m.schema_reference(raw_schema_fixture()),fixture_packages_digest())


def worker_rows(job):
    spec=m.conditions()[job["case"]];p=spec["requests"];n=spec["initial_agents"]
    source=m.query_rows([1+3*i for i in range(n)],[i//(n//8) for i in range(n)],spec)
    missing=[row["position"] is None for row in source]
    end=dict(kind="worker_end",ids=[r["id"] for r in source],positions=[r["position"] for r in source],
        precursors=[r["precursor"] for r in source],alive=n,per_region=[n//8]*8,
        setup_ticks=int(spec["layout"]=="post1-spread"),payload="a"*64,
        memories=[0]*p,legacy=[0]*p,bonds=[None if x else 0 for x in missing],needs=p-sum(missing),
        initial_gp="b"*64,warm_gp="c"*64,final_gp="c"*64,control_gp="b"*64,native_before="d"*64,native_after="d"*64,
        rng_before="e"*64,rng_after="e"*64,schema=m.schema_reference(raw_schema_fixture()),
        diagnostic_counts=[p,p,p,0] if job["arm"]=="scalar" else [0,0,0,int(p>0)])
    return [dict(kind="worker_start",**job,pid=123,packages_sha256=fixture_packages_digest()),dict(kind="timing",wall_start_ns=10,
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
    with pytest.raises(ValueError):parse_rows(b"".join(m.encode(r) for r in rows),job,123)


@pytest.mark.parametrize("key",["payload","initial_gp","warm_gp","final_gp","control_gp","native_before","rng_before","schema"])
def test_pair_requires_full_GP_CP_RNG_and_payload_parity(key):
    a=dict(ordinal=0,case=0,trial=0,arm="scalar");b=dict(ordinal=1,case=0,trial=0,arm="candidate")
    left=parse_rows(b"".join(m.encode(r) for r in worker_rows(a)),a,123)
    right=parse_rows(b"".join(m.encode(r) for r in worker_rows(b)),b,123)
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


def test_full_observed_schema_stays_in_build_and_P50_wires_remain_bounded():
    raw=raw_schema_fixture();ref=m.schema_reference(raw)
    assert raw[0]==1 and raw[1]=="dcf0c34097c88451" and len(raw[2].encode())==10828
    assert ref==dict(version=1,fingerprint=raw[1],schema_bytes=10828,
        schema_sha256="0b792f3ec33ac68605caf7b6d66fa7462c919b52e6f489f0e3dd7fa42f9fba3b")
    assert len(m.encode(dict(agent_schema=raw,agent_schema_reference=ref,
        packages={"fixture-only-dist":"1"},packages_sha256=fixture_packages_digest())))<m.BUILD_CAP
    for job in m.schedule():
        if m.conditions()[job["case"]]["requests"]!=50:continue
        rows=worker_rows(job)
        assert len(m.encode(rows[0]))<=256 and len(m.encode(rows[2]))<=2816
        oversized=deepcopy(rows[2]);oversized["schema"]=raw
        assert len(m.encode(oversized))>2816  # The old64/64 fake hid this real shape.


@pytest.mark.parametrize("change",["64hex","wrong16hex","bool_version","changed_schema"])
def test_schema_reference_checks_the_real_tuple_and_full_string(change):
    raw=raw_schema_fixture()
    if change=="64hex":raw[1]="a"*64
    elif change=="wrong16hex":raw[1]="0"*16
    elif change=="bool_version":raw[0]=True
    else:raw[2]+="changed"
    with pytest.raises(ValueError):m.schema_reference(raw)


def test_worker_schema_and_package_refs_must_join_exact_build_identity():
    job=m.schedule()[0];data=b"".join(m.encode(r) for r in worker_rows(job))
    expected=m.schema_reference(raw_schema_fixture())
    changed=dict(expected,schema_bytes=expected["schema_bytes"]+1)
    with pytest.raises(ValueError,match="checkpoint_schema_build_join"):
        m.parse_fragment(data,job,123,changed,fixture_packages_digest())
    with pytest.raises(ValueError,match="worker_identity"):
        m.parse_fragment(data,job,123,expected,"0"*64)


@pytest.mark.parametrize("names",[("Some.Package","some_package"),("MY-package","my_package")])
def test_distribution_canonical_duplicates_refuse_even_equal_versions(names):
    items=[SimpleNamespace(metadata={"Name":name},version="1") for name in names]
    with pytest.raises(ValueError,match="ambiguous_package_name"):m.package_versions(items)


def test_observed_package_version_mismatch_refuses_before_measurement():
    actual=m.package_versions([SimpleNamespace(metadata={"Name":"Some_Package"},version="2")])
    assert actual=={"some-package":"2"}
    with pytest.raises(ValueError,match="installed_package_version_mismatch"):
        m.check_packages(actual,{"some-package":"1"},m.digest({"some-package":"1"}))


def write_final_custody(root,proven=True):
    row=dict(kind="GP_FULLSYNC_PARENT_CUSTODY",github={k:__import__("os").environ.get(k) for k in m.GITHUB},
        parent_pid=123,last_attempted_ordinal=0,proven=proven)
    (root/"comparison/custody.json").write_bytes(m.encode(row))


@pytest.mark.parametrize("raw",[b"",b"{",b'{"status":',b"[]",b"null",b"{}",
    b'{"status":"complete"}',b'{"x":1,"x":2}',b'{"x":NaN}',
    b'{"kind":"GP_FULLSYNC_RESULT","planned_workers":414,"method":"named-gp-fullsync-v1-69x3x2-256","actual_source":"cccccccccccccccccccccccccccccccccccccccc","status":"failed","child_namespaces_quiescent":true,"completed_workers":0,"retained_timing_rows":0,"case_summaries":[{"nested":{"value":1e999}}]}',
    b'{"kind":"GP_FULLSYNC_RESULT","planned_workers":414,"method":"named-gp-fullsync-v1-69x3x2-256","actual_source":"cccccccccccccccccccccccccccccccccccccccc","status":"failed","child_namespaces_quiescent":true,"completed_workers":0,"retained_timing_rows":0,"case_summaries":[{"nested":{"value":-1e999}}]}'])
def test_partial_parent_results_keep_bounded_refusal_without_synthetic_rows(tmp_path,monkeypatch,context,raw):
    root=tmp_path/"evidence";(root/"comparison").mkdir(parents=True)
    write_final_custody(root)
    (root/"comparison/result.json").write_bytes(raw)
    (root/"comparison/active.jsonl").write_bytes(b"must never enter failed recovery")
    original=Path.read_bytes
    def guarded(path):
        if path.name=="active.jsonl":raise AssertionError("invalid parent result allowed child read")
        return original(path)
    monkeypatch.setattr(Path,"read_bytes",guarded)
    value=m.owner(root,tmp_path/"no_wheel",-9)
    assert value["child_custody"]=="PROVEN" and value["child_data_allowed"] is False
    assert value["recovery_problem"] and value["comparison_status"]=="UNKNOWN"
    assert value["completed_workers"] is value["durable_timing_rows"] is None
    assert value["parent_result_record"]==dict(bytes=len(raw),sha256=m.sha(raw))
    with zipfile.ZipFile(tmp_path/"gp-fullsync-compact.zip") as z:
        assert z.read("comparison/result.json")==raw
        assert "comparison/active.jsonl" not in z.namelist()
        assert json.loads(z.read("owner.json"))["actual_comparison_exit"]==-9


def test_unknown_custody_does_not_even_read_a_parent_result(tmp_path,monkeypatch,context):
    root=tmp_path/"evidence";(root/"comparison").mkdir(parents=True)
    write_final_custody(root,False)
    (root/"comparison/result.json").write_bytes(b"partial parent")
    original=Path.read_bytes
    def guarded(path):
        if path.name in ("result.json","active.jsonl"):raise AssertionError("read before custody proof")
        return original(path)
    monkeypatch.setattr(Path,"read_bytes",guarded)
    value=m.owner(root,tmp_path/"no_wheel",-9)
    assert value["child_custody"]=="UNKNOWN" and value["completed_workers"] is None
    assert value["unknown_result_reserved_bytes"]==m.RESULT_CAP
    with zipfile.ZipFile(tmp_path/"gp-fullsync-compact.zip") as z:
        assert "comparison/result.json" not in z.namelist()


def test_valid_failed_parent_keeps_known_counts_and_closed_failure_fragment(tmp_path,context):
    root=tmp_path/"evidence";(root/"comparison").mkdir(parents=True)
    write_final_custody(root)
    result=dict(kind="GP_FULLSYNC_RESULT",planned_workers=414,
        method=m.METHOD,actual_source="c"*40,status="failed",child_namespaces_quiescent=True,
        completed_workers=0,retained_timing_rows=0)
    (root/"comparison/result.json").write_bytes(m.encode(result))
    (root/"comparison/active.jsonl").write_bytes(b"closed worker failure\n")
    value=m.owner(root,tmp_path/"no_wheel",2)
    assert value["recovery_problem"] is None and value["comparison_status"]=="failed"
    assert value["completed_workers"]==value["durable_timing_rows"]==0
    assert value["actual_comparison_exit"]==2 and value["child_data_allowed"]
    with zipfile.ZipFile(tmp_path/"gp-fullsync-compact.zip") as z:
        assert z.read("comparison/active.jsonl")==b"closed worker failure\n"


def test_parent_record_reader_enforces_a_small_explicit_bound(tmp_path):
    path=tmp_path/"record.json";path.write_bytes(b"x"*17)
    value,pin,error=m.read_parent_record(path,16)
    assert value is None and pin=={} and error


def test_missing_custody_field_refuses_before_parent_result_read(tmp_path,monkeypatch,context):
    root=tmp_path/"evidence";(root/"comparison").mkdir(parents=True)
    write_final_custody(root)
    path=root/"comparison/custody.json";row=json.loads(path.read_bytes())
    del row["last_attempted_ordinal"];path.write_bytes(m.encode(row))
    original=Path.read_bytes
    def guarded(path):
        if path.name in ("result.json","active.jsonl"):raise AssertionError("read without complete custody")
        return original(path)
    monkeypatch.setattr(Path,"read_bytes",guarded)
    value=m.owner(root,tmp_path/"no_wheel",-9)
    assert value["child_custody"]=="UNKNOWN" and value["recovery_problem"]
    assert value["completed_workers"] is None


def test_safe_refusal_packet_upload_does_not_convert_failed_owner_to_success():
    workflow=yaml.load((ROOT/".github/workflows/gp-context-benchmark.yml").read_text(),Loader=yaml.BaseLoader)
    steps=workflow["jobs"]["gp-fullsync"]["steps"]
    compact=next(s for s in steps if s["name"]=="Publish the single bounded compact packet")
    refusal=next(s for s in steps if s["name"]=="Preserve bounded parent refusal only")
    assert compact["if"]=="always() && steps.owner.outputs.compact_allowed == 'true'"
    assert refusal["if"]=="always() && steps.owner.outputs.compact_allowed != 'true'"
    assert all("continue-on-error" not in s for s in steps)


# Untimed fixture setup reuse only; all earlier contracts remain byte-exact.
def _snapshot_observer_api(trace, snapshots, column_reads):
    api = fake_api(trace)
    original_bridge = api["AgentBridge"]
    class Bridge(original_bridge):
        def __init__(self, world, **kwargs):
            super().__init__(world, **kwargs)
            sim = self._sim
            def snapshot():
                ordinal = len(snapshots)
                columns = dict(id=list(sim.ids), civ_affinity=list(sim.civs))
                snapshots.append(columns)
                trace.append(("snapshot", ordinal))
                class Snapshot(Frame):
                    def column(self, name):
                        def to_pylist():
                            column_reads.append((ordinal, name))
                            return list(columns[name])
                        return SimpleNamespace(to_pylist=to_pylist)
                return Snapshot(columns)
            sim.get_snapshot = snapshot
    api["AgentBridge"] = Bridge
    return api


@pytest.mark.parametrize("layout,p", [("empty", 0), ("prefix", 10), ("half-missing", 2)])
def test_no_tick_fixture_reuses_one_snapshot_and_each_decoded_column(layout, p):
    trace, snapshots, reads = [], [], []
    spec = dict(initial_agents=512, requests=p, layout=layout)
    bridge, world, info = m.fixture(spec, _snapshot_observer_api(trace, snapshots, reads))
    assert len(snapshots) == 1
    assert reads == [(0, "id"), (0, "civ_affinity")]
    assert [row[0] for row in trace] == ["public_bridge_constructor", "snapshot"]
    expected = m.query_rows(snapshots[0]["id"], snapshots[0]["civ_affinity"], spec)
    expected = [row for civ in range(8) for row in expected if row["civ"] == civ]
    assert [row for _, row in info["rows"]] == expected
    assert [gp.agent_id for gp, _ in info["rows"]] == [row["id"] for row in expected]
    assert info["setup_ticks"] == 0 and info["alive"] == len(bridge._sim.ids) == 512
    assert len(info["controls"]) == 20 and len(world.civilizations) == 8


def test_post_tick_fixture_reloads_changed_ids_affinities_and_preserves_query_order():
    trace, snapshots, reads = [], [], []
    spec = dict(initial_agents=512, requests=10, layout="post1-spread")
    bridge, world, info = m.fixture(spec, _snapshot_observer_api(trace, snapshots, reads))
    assert len(snapshots) == 2
    assert reads == [(0, "id"), (0, "civ_affinity"), (1, "id"), (1, "civ_affinity")]
    assert [row[0] for row in trace] == [
        "public_bridge_constructor", "snapshot", "tick", "snapshot", "relationships"]
    assert snapshots[0]["id"][0] == 1000 and snapshots[1]["id"][-1] == 900001
    assert snapshots[0]["id"] != snapshots[1]["id"]
    assert snapshots[0]["civ_affinity"] != snapshots[1]["civ_affinity"]
    expected = m.query_rows(snapshots[1]["id"], snapshots[1]["civ_affinity"], spec)
    grouped = [row for civ in range(8) for row in expected if row["civ"] == civ]
    assert [row for _, row in info["rows"]] == grouped
    assert 900001 in [gp.agent_id for gp, _ in info["rows"]]
    ops = next(row[1] for row in trace if row[0] == "relationships")
    assert ops.column("agent_a").to_pylist() == [row["id"] for row in expected for _ in range(8)]
    assert ops.column("agent_b").to_pylist() == [
        snapshots[1]["id"][(row["precursor"] + k) % 512]
        for row in expected for k in range(1, 9)]
    assert info["setup_ticks"] == 1 and info["alive"] == 512


@pytest.mark.parametrize("layout", ["all-missing", "half-missing"])
def test_missing_queries_reuse_the_validated_id_set_and_still_refuse_collisions(monkeypatch, layout):
    ids = [1000 + 3*i for i in range(512)]
    civs = [i//64 for i in range(512)]
    built, checked = [], []
    class WitnessSet(set):
        def __contains__(self, value):
            checked.append(value)
            return super().__contains__(value)
    def build(values):
        built.append(tuple(values))
        return WitnessSet(values)
    monkeypatch.setattr(m, "set", build, raising=False)
    spec = dict(requests=2, layout=layout)
    rows = m.query_rows(ids, civs, spec)
    absent = [row["id"] for row in rows if row["position"] is None]
    assert built == [tuple(ids)] and checked == absent
    collision = 2**32 - (1 if layout == "all-missing" else 2)
    changed = ids.copy()
    changed[-1] = collision
    with pytest.raises(ValueError, match="missing_id_collision"):
        m.query_rows(changed, civs, spec)
    assert built == [tuple(ids), tuple(changed)]
    assert checked[-1] == collision
