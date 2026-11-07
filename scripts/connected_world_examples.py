#!/usr/bin/env python3
"""Find dated adaptation, failure and mixed observations in an existing bundle.

PYTHONPATH=src python scripts/connected_world_examples.py BUNDLE --output report.json

Post hoc, read only, no narration/model call and no held-seed execution. Each
found example supplies an exact record citation, actual JSON pointer, stable
identity where recorded and a mechanically composed observation. The first
matching row in saved snapshot order is retained; unactivated categories are
explicit nulls, never replaced by constructed evidence. Labels describe the
selection rule, not an efficacy finding. A constructed input remains labelled.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
from chronicler.bundle_codec import load_bundle
from chronicler.narration_provenance import livelihood_fact_id, resolve_record_pointer
from chronicler.narration_audit import audit_bundle

# package, path to rows, category, selection rule, fields preserved in prose
RULES = (
 ("timber_orders",("closed",),"adaptation","delivered timber is positive",lambda r:r.get("outcome")=="delivered" and r.get("delivered_milli",0)>0,("id","holder","outcome","delivered_milli","credited_milli")),
 ("timber_orders",("closed",),"failure","terminal order did not deliver",lambda r:r.get("outcome")!="delivered",("id","holder","outcome","purchase_milli","lost_milli","deposited_milli","refunded_milli")),
 ("timber_orders",("closed",),"mixed","positive delivery with physical loss or unused escrow",lambda r:r.get("delivered_milli",0)>0 and (r.get("lost_milli",0)>0 or r.get("refunded_milli",0)>0),("id","holder","delivered_milli","lost_milli","credited_milli","refunded_milli")),
 ("war_requisition",("frame","events"),"adaptation","food reaches named carried ration allocations",lambda r:sum(a["rations"] for a in r.get("allocations",[]))>0,("kind","region","owner","shipment","removed_milli","allocations","destroyed_milli")),
 ("war_requisition",("frame","events"),"failure","army ration adequacy is below one",lambda r:r.get("kind")=="consumption" and r.get("adequacy",1)<1,("kind","army","consumed_rations","demanded_rations","adequacy")),
 ("war_requisition",("frame","events"),"mixed","some removed food is carried and some destroyed",lambda r:sum(a["rations"] for a in r.get("allocations",[]))>0 and r.get("destroyed_milli",0)>0,("kind","region","allocations","destroyed_milli","removed_milli")),
 ("adaptive_livelihoods",("frame","offers"),"adaptation","a new offer is declined after personal experience",lambda r:r.get("would_decline") is True and r.get("accepted") is False,("id","kind","would_decline","accepted")),
 ("adaptive_livelihoods",("frame","refusals"),"failure","native migration was refused by its recorded gate",lambda r:True,("id","origin","region","gate")),
 ("adaptive_livelihoods",("frame","work"),"mixed","positive actual payment with unknown net utility or withheld income",lambda r:(r.get("paid_milli") or 0)>0 and (r.get("net_milli") is None or (r.get("withheld_milli") or 0)>0),("id","kind","paid_milli","withheld_milli","title_forgone_milli","net_milli","progress","source")),
 ("war_consequences",("frame","events"),"adaptation","an evacuation or return is recorded (safety not established)",lambda r:r.get("kind") in ("evacuated","returned"),("id","kind","region","destination","home","cause")),
 ("war_consequences",("frame","events"),"failure","a selected combat victim receives a wound record",lambda r:r.get("kind")=="wounded",("id","kind","region","army","cause")),
 ("war_consequences",("frame","separation","separated"),"mixed","a family relation persists while its members are separated",lambda r:True,("a","b","relation","cause")),
 ("public_health",("decisions",),"adaptation","delivered evidence selects a closure (effectiveness not established)",lambda r:r.get("close") is True,("civ","target","report_ids","expected_loss_units","cost_units","close")),
 ("public_health",("supplies",),"failure","patient supply falls short of physical need",lambda r:r.get("food_milli",0)<r.get("need_milli",0),("region","need_milli","food_milli","reason")),
 ("public_health",("supplies",),"mixed","positive patient supplies leave unmet physical need",lambda r:0<r.get("food_milli",0)<r.get("need_milli",0),("region","need_milli","food_milli","charged_milli","internal_milli","reason")),
 ("infrastructure_condition",("receipts",),"adaptation","repair credits positive condition work",lambda r:r.get("credited",0)>0,("wid","aid","region","kind","delivered","credited","condition_before","condition_after")),
 ("infrastructure_condition",("receipts",),"failure","repair stalls",lambda r:r.get("status")=="stalled",("wid","aid","region","kind","reasons","requested","delivered")),
 ("infrastructure_condition",("receipts",),"mixed","positive work remains limited by recorded reasons",lambda r:r.get("delivered",0)>0 and bool(r.get("reasons")),("wid","aid","region","kind","reasons","requested","delivered","credited")),
 ("reform_services",("frame","purchases"),"adaptation","relief purchases physical food from owners",lambda r:r.get("food_milli",0)>0,("region","civ","food_milli","rations","credited_milli","sellers")),
 ("reform_services",("frame","deliveries"),"failure","relief delivery is unobserved or upper bound is zero",lambda r:r.get("observed") is False or r.get("delivered_at_most")==0,("region","bought_turn","observed","delivered_at_least","delivered_at_most")),
 ("reform_services",("frame","deliveries"),"mixed","regional delivery has a positive upper bound and no lower bound",lambda r:r.get("observed") is True and r.get("delivered_at_least") is None and (r.get("delivered_at_most") or 0)>0,("region","bought_turn","delivered_at_least","delivered_at_most","priced_out_persons")),
 ("guild_leagues",("frame","payouts"),"adaptation","a city's purse receives a positive recorded claim payment",lambda r:r.get("paid_milli",0)>0,("league","city","kind","loss_milli","paid_milli","event_id")),
 ("guild_leagues",("frame","payouts"),"failure","a positive recorded claim receives no payment",lambda r:r.get("loss_milli",0)>0 and r.get("paid_milli")==0,("league","city","kind","loss_milli","paid_milli","event_id")),
 ("guild_leagues",("frame","payouts"),"mixed","claim paid only in part",lambda r:0<r.get("paid_milli",0)<r.get("loss_milli",0),("league","city","kind","loss_milli","paid_milli","event_id")),
)

def collect_examples(bundle: dict) -> dict:
    """Return independent story entries and explicit empty categories, without mutation."""
    examples = {f"{package}:{category}": {"found":False,"selection_rule":rule} for package,_path,category,rule,_predicate,_fields in RULES}
    errors=[]; entries=[]
    for snapshot in bundle.get("history") or []:
        turn=snapshot.get("turn"); lh=snapshot.get("livelihoods") or {}
        if not isinstance(lh,dict) or lh.get("schema_version")!=1: continue
        for package,path,category,rule,predicate,fields in RULES:
            key=f"{package}:{category}"
            if examples[key]["found"]: continue
            record=lh.get(package)
            if not isinstance(record,dict) or record.get("source_turn")!=turn-1: continue
            rows=record
            for field in path: rows=rows.get(field) if isinstance(rows,dict) else None
            if not isinstance(rows,list): continue
            for i,row in enumerate(rows):
                if not isinstance(row,dict): continue
                try: selected=predicate(row)
                except (TypeError,KeyError,ValueError) as exc:
                    errors.append({"snapshot":turn,"package":package,"reason":str(exc)}); continue
                if not selected: continue
                fid=livelihood_fact_id(turn,package,*path,i); resolved=resolve_record_pointer(bundle,fid)
                if resolved is None:
                    errors.append({"snapshot":turn,"package":package,"reason":"selected row failed exact citation resolution"}); continue
                values={field:row.get(field) for field in fields}
                # One recorded observation per sentence, no causal connectors.
                text=f"At snapshot {turn}, {package.replace('_',' ')} recorded {json.dumps(values,sort_keys=True,separators=(',',':'))}."
                prov={"v":1,"narrator":"mechanical","as_of":turn-1,"facts":[fid],"names":[],"spans":[[0,len(text),[fid]]]}
                entry={"narrative":text,"provenance":prov}
                entries.append(entry)
                individual=any(field in values for field in ("holder","owner","id","a","army"))
                examples[key]={"found":True,"selection_rule":rule,"snapshot":turn,"source_turn":resolved.source_turn,"join":"id" if individual else "region_or_institution_context","fact_id":fid,"pointer":resolved.pointer,"values":values,"story_entry":entry}
                break
    # Audit a derived object, never mutate or narrate the simulation bundle.
    story_bundle={**bundle,"chronicle_entries":entries}
    audit=audit_bundle(story_bundle)
    return {"constructed":(bundle.get("metadata") or {}).get("constructed"),"selection":"first matching saved row per declared rule; labels are observations, not efficacy or qualification","examples":examples,"schema_errors":errors,"story_audit":audit.to_dict()}

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("bundle",type=Path);parser.add_argument("--output",type=Path)
    args=parser.parse_args();data=args.bundle.read_bytes();bundle=load_bundle(args.bundle);report=collect_examples(bundle)
    report={"bundle":str(args.bundle.resolve()),"bundle_sha256":hashlib.sha256(data).hexdigest(),**report}
    encoded=json.dumps(report,indent=2,sort_keys=True)+"\n"
    if args.output: args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(encoded)
    else: print(encoded,end="")
    return bool(report["schema_errors"] or report["story_audit"]["flags"])
if __name__=="__main__":raise SystemExit(main())
