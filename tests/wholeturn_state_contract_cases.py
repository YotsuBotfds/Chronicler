"""Strict graph and terminal-capture fakes; no Native/World/Arrow import."""
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
import wholeturn_state_proof as proof
import wholeturn_live_proof as live


class Native:
    def __init__(self): self.data=b"persistent"
    def checkpoint_state(self): return self.data
    def get_region_populations(self):
        class Batch:
            num_rows=8; num_columns=2; schema=SimpleNamespace(names=["region_id","alive_count"])
            def column(self,name):
                return SimpleNamespace(null_count=0,to_pylist=lambda:list(range(8)) if name=="region_id" else [1]*8)
        return Batch()


@dataclass
class World:
    regions:list=field(default_factory=lambda:list(range(8)))
    cache:object=field(default_factory=list)


@dataclass
class Bridge:
    _sim:object
    _private_cache:object=field(default_factory=list)


@dataclass
class State:
    world:object
    agent_bridge:object
    memories:dict=field(default_factory=dict)
    markers:dict=field(default_factory=lambda:{"war_roster_bound":True})


def state():
    value=State(World(),Bridge(Native()))
    value.world._war_roster_sim=id(value.agent_bridge._sim)
    return value


def fingerprint(value): return proof.StateFingerprint(value,(Native,)).result()


def test_roster_projection_requires_the_actual_association():
    value=state()
    before=fingerprint(value)
    replacement=Native()
    value.agent_bridge._sim=replacement
    value.world._war_roster_sim=id(replacement)
    assert fingerprint(value) == before
    value.world._war_roster_sim=0
    with pytest.raises(proof.Refused,match="association"):
        fingerprint(value)


@pytest.mark.parametrize("mutation", ["native","private","negative_zero","alias","order"])
def test_full_graph_detects_real_persistent_private_bit_alias_and_order_changes(mutation):
    value=state()
    shared=[]
    value.world.cache=[0.0,shared,shared,{"a":1,"b":2}]
    before=fingerprint(value)
    if mutation=="native": value.agent_bridge._sim.data=b"different"
    elif mutation=="private": value.agent_bridge._private_cache.append("changed")
    elif mutation=="negative_zero": value.world.cache[0]=-0.0
    elif mutation=="alias": value.world.cache[2]=[]
    else: value.world.cache[3]={"b":2,"a":1}
    assert fingerprint(value)["sha256"] != before["sha256"]


def test_cycles_are_supported_without_addresses_in_digest():
    a,b=state(),state()
    a.world.cache.append(a.world.cache)
    b.world.cache.append(b.world.cache)
    assert fingerprint(a) == fingerprint(b)


@pytest.mark.parametrize("unsupported", [datetime(2026,10,30),complex(1,2),range(3),slice(1,2)])
def test_loader_permitted_but_unproved_types_refuse(unsupported):
    value=state(); value.world.cache=unsupported
    with pytest.raises(proof.Refused,match="unsupported state type"):
        fingerprint(value)


def test_memory_encoder_rows_require_original_objects_and_scalar_identity():
    @dataclass
    class Entry:
        turn:int; text:str; importance:float; entry_type:str
    @dataclass
    class Memory:
        entries:list; reflections:list; _encoded:dict
    value=state()
    entry=Entry(1000,"a long memory body",0.125,"memory")
    value.memories["civ"]=Memory([entry],[],{"entries":[(entry,entry.turn,entry.text,entry.importance,entry.entry_type)]})
    assert fingerprint(value)["memory_cache_rows"] == {"civ":{"entries":1}}
    value.memories["civ"]._encoded["entries"][0]=(deepcopy(entry),entry.turn,entry.text,entry.importance,entry.entry_type)
    with pytest.raises(proof.Refused,match="encoder identity"):
        fingerprint(value)


def test_terminal_capture_observes_live_cache_separately_from_reduced_graph(monkeypatch,tmp_path):
    value=state(); value.markers={}; value.agent_bridge._private_cache=["live-only"]
    decoded=state()
    original_calls=[]
    def original(path,observed): original_calls.append(observed); return path
    rc=SimpleNamespace(write_checkpoint=original,_markers=lambda s:{"war_roster_bound":True},
        read_checkpoint=lambda path,allow_mismatch:SimpleNamespace(exact=True,state=decoded,
          header={"sections":[{"name":"native.agents"}]}))
    monkeypatch.setattr(proof,"capture_rng",lambda np:{"unchanged":True})
    monkeypatch.setattr(proof,"same_rng",lambda a,b:a==b)
    result=live.capture_terminal(lambda path:rc.write_checkpoint(path,value),tmp_path/"state.ckpt",rc,(Native,),None)
    assert len(original_calls)==1 and rc.write_checkpoint is original
    assert result["live"]["sha256"] != result["decoded"]["sha256"]
    assert result["live_equals_decoded_claim"] is False and result["extra_physics_runs"] == 0
    assert result["actual_final_native"]["in_domain_alive_count"] == 8
    assert result["coverage"]["internal_C_Arrow_storage_aliases"] == "UNOBSERVED"


def test_live_writer_mutation_refuses_and_restores_original_binding(monkeypatch,tmp_path):
    value=state()
    def original(path,observed): observed.agent_bridge._private_cache.append("mutation"); return path
    rc=SimpleNamespace(write_checkpoint=original,_markers=lambda s:{"war_roster_bound":True})
    monkeypatch.setattr(proof,"capture_rng",lambda np:{})
    with pytest.raises(proof.Refused,match="mutated live"):
        live.capture_terminal(lambda path:rc.write_checkpoint(path,value),tmp_path/"state.ckpt",rc,(Native,),None)
    assert rc.write_checkpoint is original


def test_python_counterfeit_raw_arrow_class_cannot_admit_by_names():
    class Counterfeit:
        __module__="arro3.core._core"
        __arrow_c_array__=object.__getattribute__
        column=object.__getattribute__
    Counterfeit.__name__="RecordBatch"
    fake_pa=SimpleNamespace(RecordBatch=type("DifferentExactClass",(),{}))
    assert not live.trusted_raw_batch(Counterfeit(),fake_pa,type("DifferentArro3Class",(),{}))
