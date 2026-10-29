#!/usr/bin/env python3
"""Detached source503 stages, deferring only existing checkpoint deletion.

The original scientific module/file/globals are never modified. Its exact parser
and summary expressions and its parent/arm/validator functions remain unchanged.
No default command or unregistered phase imports scientific code or runs worlds.
"""
from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import math
import re
from pathlib import Path
import sys
import time

SCRIPT=Path(__file__).resolve()
sys.path.insert(0,str(SCRIPT.parent))
import wealth_floor_candidate_proof as P
import wealth_floor_outcome_admission_v2 as V
import wealth_floor_outcome_checkpoints as K

B=P.B
require,exact=P.require,P.exact
RUNNER_SHA256=P.KERNELS["scripts/m53b_run_validation.py"]
PARSER_AST_SHA256="5e55da822720339cc5721347ab5a80e18bb8cce83638536bbdbf5b9814ef14e2"
SUMMARY_AST_SHA256="e7496199a4afb3e6d6b25e71f58317f025fdf68ad318a711fc84723604517f92"


def source_fragments(raw):
    """Select unchanged source statements; no original globals are replaced."""
    require(hashlib.sha256(raw).hexdigest()==RUNNER_SHA256,"source503 runner differs")
    tree=ast.parse(raw);mains=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=="main"]
    require(len(mains)==1,"one original parser/main required")
    body=mains[0].body
    cwd=[i for i,n in enumerate(body) if isinstance(n,ast.Assign) and len(n.targets)==1
        and isinstance(n.targets[0],ast.Name) and n.targets[0].id=="cwd"]
    summaries=[n.value for n in body if isinstance(n,ast.Assign) and len(n.targets)==1
        and isinstance(n.targets[0],ast.Name) and n.targets[0].id=="summary"]
    require(len(cwd)==len(summaries)==1 and isinstance(summaries[0],ast.Dict),"fixed parser/summary boundaries required")
    prefix=ast.Module(body=body[:cwd[0]],type_ignores=[])
    require(hashlib.sha256(ast.dump(prefix,include_attributes=False,show_empty=True).encode()).hexdigest()==PARSER_AST_SHA256
        and hashlib.sha256(ast.dump(summaries[0],include_attributes=False,show_empty=True).encode()).hexdigest()==SUMMARY_AST_SHA256,
        "original parser/preflight/summary AST differs")
    require(not any(isinstance(n,ast.Call) and isinstance(n.func,ast.Name)
        and n.func.id in ("run_subset","run_full","run_arms","run_determinism","validate_batch") for n in ast.walk(prefix)),"parser prefix must contain no scientific stage")
    return prefix,ast.Expression(body=summaries[0])


def parse_original(runner,raw):
    prefix,_=source_fragments(raw);namespace=dict(vars(runner))
    exec(compile(prefix,str(Path(runner.__file__))+":original-parser","exec"),namespace)
    return namespace["args"]


def original_summary(runner,raw,**values):
    _,expression=source_fragments(raw);namespace=dict(vars(runner));namespace.update(values)
    return eval(compile(expression,str(Path(runner.__file__))+":original-summary","eval"),namespace)


def execution_marker(value,registered,stage,worldgen,branch,*,now):
    require(type(value) is dict and value.get("stage")==stage and value.get("worldgen")==worldgen
        and value.get("source_sha")==B.CANDIDATE_SOURCE and value.get("registration_sha256")==B.digest(registered)
        and value.get("prerequisite_packet_sha256")==V.ROOT_PREREQUISITE_PACKET_SHA256,"owned parent admission marker differs")
    producer=value.get("producer",{})
    require(producer.get("ref")=="refs/heads/"+branch and producer.get("job_key")==("smoke" if stage=="smoke" else "cohort")
        and producer.get("attempt")=="1" and type(producer.get("run_id")) is str and re.fullmatch("[1-9][0-9]*",producer["run_id"])
        and type(value.get("control_sha")) is str and re.fullmatch("[0-9a-f]{40}",value["control_sha"]),"owned registered producer marker required")
    observed=value.get("admitted_monotonic")
    require(type(observed) in (int,float) and math.isfinite(observed) and 0<=now-observed<=P.STAGING_WALL_SECONDS,"fresh owned parent admission required")
    return True


def run_stages(args,runner,raw,config,root,*,current_identity,compare_identity,check=lambda:None,clock=time.monotonic):
    """Only the original deletion is deferred around real metadata capture."""
    cwd=Path.cwd();env=runner._build_env();timings={}
    check();started=clock()
    batch_dir=runner.run_subset(args,cwd,env) if args.profile=="subset" else runner.run_full(args,cwd,env)
    timings["batch_seconds"]=round(clock()-started,1)
    check();started=clock()
    index,seal=K.capture(root,batch_dir,config,current_identity,compare_identity,check)
    timings["checkpoint_capture_seconds"]=round(clock()-started,1)
    arms=runner.ablation_arms_for(args);out=runner._ablation_dir_for(batch_dir)
    require(arms==config["arms"] and runner.ablation_enabled(args),"original registered arms required")
    print(f"> ablation arms {','.join(arms)} into {out}")
    check();started=clock()
    manifest=runner.run_ablation_arms(batch_dir,out,arms=arms,total_turns=args.turns,
        parallel=max(1,int(args.parallel or 1)),env=env,cwd=cwd,delete_checkpoints=False)
    timings["ablation_seconds"]=round(clock()-started,1)
    require(manifest.get("status")=="complete" and manifest.get("fork_count")==config["fork_count"],"all original arm forks must finish before retirement")
    arms_result={"dir":out,"arms":arms,"forks":manifest.get("fork_count"),"seconds":manifest.get("seconds"),"fork_turns":manifest.get("fork_turns")}
    check();started=clock()
    K.retire(root,index,seal,check)
    timings["checkpoint_recheck_retirement_seconds"]=round(clock()-started,1)
    check();started=clock()
    validation_result=runner.validate_batch(batch_dir,f"validate_report_{args.profile}.json",cwd,env,args.profile,
        require_strict_regression=args.require_strict_regression,baseline_report=args.baseline_report,
        fail_on_regression=args.fail_on_regression,exploratory_comparison=args.exploratory_comparison,
        ablation_dir=arms_result["dir"] if arms_result is not None else None,require_causal_oracles=args.require_causal_oracles)
    timings["validation_seconds"]=round(clock()-started,1)
    summary=original_summary(runner,raw,args=args,batch_dir=batch_dir,validation_result=validation_result,
        comparison=validation_result.get("comparison"),arms_result=arms_result,timings=timings,env=env)
    runner.atomic_write_json(batch_dir/"run_manifest.json",summary)
    print(runner.strict_json_dumps(summary),end="")
    if not validation_result["decision"]["ok"]:
        print(runner._format_gate_failure(validation_result["decision"]),file=sys.stderr)
        return validation_result["decision"]["exit_code"]
    comparison=validation_result.get("comparison")
    return comparison["exit_code"] if comparison is not None else 0


def main():
    argv=sys.argv[1:]
    if not argv:
        print(json.dumps(dict(status="inactive_source_only",worlds_admitted=False)));return 0
    require(argv.count("--profile")==argv.count("--worldgen")==argv.count("--output-root")==1,"fixed original runner argument vector required")
    profile=argv[argv.index("--profile")+1];worldgen=argv[argv.index("--worldgen")+1]
    require(profile in ("subset","full") and worldgen in ("template","procedural"),"fixed original outcome profile required")
    stage="smoke" if profile=="subset" else "full"
    V.registration(stage)  # Before source/path access, project import or worlds.
    control=SCRIPT.parents[1]
    import wealth_floor_outcome_qualification as O
    plan=V.admit_plan(P.read_json(control,O.PREREQUISITE_PATH),stage,
        P.read_json(control,O.WORKER_PACKET_PATH) if stage=="full" else None)
    source=Path.cwd().resolve();runner_raw=P.read_bytes(source,"scripts/m53b_run_validation.py")
    require(hashlib.sha256(runner_raw).hexdigest()==RUNNER_SHA256,"exact source503 scientific runner required")
    helpers=O.scientific_helpers(control)
    output=Path(argv[argv.index("--output-root")+1])
    require(output.is_absolute() and output.resolve()==output,"canonical owned output path required")
    marker=P.read_json(output.parent,"execution-admission.json")
    execution_marker(marker,P.parse(plan.registration_bytes),stage,worldgen,O.SMOKE_BRANCH if stage=="smoke" else O.ACTIVE_BRANCH,now=time.monotonic())
    require(argv==O.runner_command(sys.executable,source,worldgen,output,stage,helpers)[2:],"parent/arm/validator settings differ from original fixed command")
    O.source_bindings(control)
    sys.path.insert(0,str(source/"src"))
    spec=importlib.util.spec_from_file_location("registered_source503_outcome_runner",source/"scripts/m53b_run_validation.py")
    runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)
    args=parse_original(runner,runner_raw);config=helpers.expected(worldgen,stage)
    root=Path(args.output_root).parent
    deadline=P.read_json(root,"execution-deadline.json")
    require(type(deadline.get("work_deadline_monotonic")) in (int,float)
        and math.isfinite(deadline["work_deadline_monotonic"]) and deadline["work_deadline_monotonic"]>0,"owned controller work deadline required")
    check=lambda:require(time.monotonic()<=deadline["work_deadline_monotonic"],"owned outcome work deadline exceeded")
    import chronicler.run_checkpoint as rc
    V.recheck_plan(plan);check()
    import wealth_floor_production_primer as M
    M.observe_runtime()
    current=rc.runtime_identity()
    require(current["source"]==dict(git_sha=B.CANDIDATE_SOURCE,package_digest=K.PACKAGE)
        and current["native"].get("sha256")==P.REVIEWED_BUILD["candidate_native_sha256"],"current candidate source/native differs before any parent world")
    return run_stages(args,runner,runner_raw,config,root,current_identity=current,compare_identity=rc._compare_identity,check=check)


if __name__=="__main__":
    raise SystemExit(main())
