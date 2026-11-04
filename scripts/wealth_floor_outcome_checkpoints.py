"""Bounded real checkpoint evidence before the original successful retirement.

Metadata only: no checkpoint section decompression, unpickling, native import or
world execution. The detached scientific driver supplies current identity and
the unchanged source503 strict identity comparator after admission.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import stat
import struct
import sys

sys.path.insert(0,str(Path(__file__).resolve().parent))
import wealth_floor_candidate_proof as P

B,C=P.B,P.C
require,exact=P.require,P.exact
MAGIC=b"\x89CHRONICLER-CKPT\r\n\x1a\n"
MAX_CHECKPOINT=64*B.MIB
MAX_HEADER=65536
MAX_INDEX=32*B.MIB
MAX_CHECKPOINTS=1000
MAX_FAILED_BODY_BYTES=6*1024**3
PACKAGE="49d78e877f981c4af2440e9dadbde7dd211e2fff0d2f1be68e7a4e5c10310e0a"
THREADS={k:"1" for k in ("BLIS_NUM_THREADS","GOTO_NUM_THREADS","MKL_NUM_THREADS","NUMEXPR_NUM_THREADS",
    "OMP_NUM_THREADS","OPENBLAS_NUM_THREADS","RAYON_NUM_THREADS","VECLIB_MAXIMUM_THREADS")}
THREADS.update(OPENBLAS_THREAD_TIMEOUT="16",PYTHONHASHSEED="0",PYTHON_CPU_COUNT="2")


def identity(info):
    return [info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns,info.st_ctime_ns]


def expected_turns(config):
    """Check fixed counts before expanding a possibly malformed configuration."""
    require(type(config) is dict and config.get("worldgen") in ("template","procedural")
        and config.get("profile") in ("subset","full"),"fixed checkpoint profile/world required")
    procedural=config["worldgen"]=="procedural";smoke=config["profile"]=="subset"
    turns,count=(125,2) if smoke else ((300,100) if procedural else (500,200))
    checkpoints=[t+1 for t in range(100,turns-20,20 if procedural else 100)]
    for key,value in dict(turns=turns,seed_count=count,seed_start=42,regions=32 if procedural else 8,civs=10 if procedural else 4,parallel=2).items():
        require(type(config.get(key)) is int and config[key]==value,"fixed checkpoint coverage differs")
    require(type(config.get("checkpoint_turns")) is list and config["checkpoint_turns"]==checkpoints
        and count*len(checkpoints)<=MAX_CHECKPOINTS,"fixed checkpoint count/turns differ")
    return checkpoints


def inspect(root,name,check=lambda:None):
    """Wholefile hash plus bounded real header, never decoding state sections."""
    digest=hashlib.sha256();prefix=bytearray();count=0
    with P.regular(root,name) as (stream,info):
        require(0<info.st_size<=MAX_CHECKPOINT,"checkpoint evidence member cap")
        while block:=stream.read(B.MIB):
            check();count+=len(block);require(count<=info.st_size,"checkpoint grew during hash")
            digest.update(block)
            if len(prefix)<MAX_HEADER+len(MAGIC)+4:
                prefix.extend(block[:MAX_HEADER+len(MAGIC)+4-len(prefix)])
        require(count==info.st_size,"checkpoint hash EOF")
    require(prefix.startswith(MAGIC) and len(prefix)>=len(MAGIC)+4,"checkpoint magic")
    start=len(MAGIC)+4;size=struct.unpack('<I',prefix[len(MAGIC):start])[0]
    require(size<=MAX_HEADER and start+size<=len(prefix),"bounded checkpoint header")
    header=P.parse(bytes(prefix[start:start+size]));offset=0
    require(type(header) is dict and type(header.get("sections")) is list,"checkpoint sections")
    for section in header["sections"]:
        require(type(section) is dict and type(section.get("offset")) is int and section["offset"]==offset
            and type(section.get("length")) is int and section["length"]>=0,"checkpoint section extent")
        offset+=section["length"]
    require(start+size+offset==count,"whole checkpoint extent")
    return dict(path=P.safe_name(name),bytes=count,sha256=digest.hexdigest(),header=header,file_identity=identity(info))


def validate_header(header,config,seed,turn):
    require(header.get("format")=="chronicler-run-checkpoint" and type(header.get("version")) is int
        and header["version"]==1 and header.get("exact") is True,"exact checkpoint format")
    for key,value in dict(seed=seed,turn=turn,num_turns=config["turns"],start_turn=0).items():
        require(type(header.get(key)) is int and header[key]==value,"candidate checkpoint seed/horizon")
    require(header.get("identity",{}).get("source")==dict(git_sha=B.CANDIDATE_SOURCE,package_digest=PACKAGE)
        and header["identity"].get("native",{}).get("sha256")==P.REVIEWED_BUILD["candidate_native_sha256"],"candidate-owned checkpoint identity")
    env=header["identity"].get("environment",{})
    require(env.get("python")==B.PYTHON_VERSION and env.get("implementation")=="CPython"
        and type(env.get("affinity_cpu_count")) is int and env["affinity_cpu_count"]==2
        and exact(env.get("thread_env"),THREADS),"actual worker-written checkpoint runtime context")
    world=header.get("world",{});run=header.get("run_config",{})
    require(world.get("regions")==config["regions"] and world.get("civilizations")==config["civs"]
        and run.get("agent_mode")=="hybrid" and run.get("validation_sidecar") is True
        and [s.get("name") for s in header["sections"]]==["python","native.agent.0"],"candidate checkpoint world/runtime shape")
    require(header.get("lineage")==[] and run.get("lineage")==[] and run.get("resume_info") is None,"fresh parent checkpoint lineage required")
    return True


def durable_json(path,value):
    """Persist evidence before any body is eligible for retirement."""
    raw=B.canonical_bytes(value);require(len(raw)<=MAX_INDEX,"combined checkpoint index cap")
    path=Path(path);temporary=path.with_name(path.name+".pending")
    with temporary.open('xb') as stream:
        stream.write(raw);stream.flush();os.fsync(stream.fileno())
    os.replace(temporary,path)
    fd=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(fd)
    finally:os.close(fd)
    return hashlib.sha256(raw).hexdigest()


def capture(root,batch,config,current_identity,compare_identity,check=lambda:None):
    root,batch=Path(root),Path(batch)
    require(batch.is_relative_to(root),"checkpoint batch outside evidence root")
    turns=expected_turns(config)
    batch_relative=batch.relative_to(root).as_posix()
    require(batch_relative==("raw/oracle_subset/batch_42" if config["profile"]=="subset" else "raw/full_gate/batch_42"),"fixed checkpoint batch path required")
    expected=[(seed,turn) for seed in range(42,42+config["seed_count"]) for turn in turns]
    require(0<len(expected)<=MAX_CHECKPOINTS,"fixed checkpoint evidence count bound")
    index=dict(schema_version=1,kind="wealth-floor-real-parent-checkpoint-index",capture_complete=False,
        config=config,batch_relative=batch_relative,checkpoint_count=len(expected),checkpoints=[],scope="Actual worker-written headers/wholefile hashes before forks; no native/Python state decode or independently sampled worker PID/overlap.")
    partial=root/"candidate-checkpoint-capture.jsonl";total=0
    with partial.open('xb') as journal:
        for seed,turn in expected:
            check();name=(batch/f"seed_{seed}"/f"checkpoint_turn_{turn}.ckpt").relative_to(root).as_posix()
            row=inspect(root,name,check);validate_header(row["header"],config,seed,turn)
            require(compare_identity(row["header"]["identity"],current_identity,True)==[],"strict current candidate checkpoint identity mismatch")
            row.update(seed=seed,turn=turn,strict_current_identity_matches=True)
            encoded=B.canonical_bytes(row);total+=len(encoded)
            require(total<=MAX_INDEX-65536,"combined checkpoint capture metadata cap")
            journal.write(encoded);journal.flush();index["checkpoints"].append(row)
        os.fsync(journal.fileno())
    index["capture_complete"]=True
    seal=durable_json(root/"candidate-checkpoint-index.json",index)
    return index,seal


def unlink_original(root,name,expected_identity):
    parts=Path(P.safe_name(name)).parts
    flags=os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW
    directory=os.open(root,flags);opened=[directory]
    try:
        for part in parts[:-1]:
            directory=os.open(part,flags,dir_fd=directory);opened.append(directory)
        info=os.stat(parts[-1],dir_fd=directory,follow_symlinks=False)
        require(stat.S_ISREG(info.st_mode) and info.st_nlink==1 and identity(info)==expected_identity,"checkpoint path changed before unlink")
        os.unlink(parts[-1],dir_fd=directory)
    finally:
        for fd in reversed(opened):os.close(fd)


def retire(root,index,index_sha256,check=lambda:None):
    """Recheck every complete body before the first original cleanup unlink."""
    root=Path(root);raw=P.read_bytes(root,"candidate-checkpoint-index.json",MAX_INDEX,check)
    require(hashlib.sha256(raw).hexdigest()==index_sha256 and exact(P.parse(raw),index)
        and index["capture_complete"] is True,"durable captured checkpoint index changed")
    turns=expected_turns(index["config"])
    batch_relative="raw/oracle_subset/batch_42" if index["config"]["profile"]=="subset" else "raw/full_gate/batch_42"
    expected=[(seed,turn) for seed in range(42,42+index["config"]["seed_count"]) for turn in turns]
    require(type(index.get("schema_version")) is int and index["schema_version"]==1 and index.get("kind")=="wealth-floor-real-parent-checkpoint-index"
        and index.get("batch_relative")==batch_relative and type(index.get("checkpoints")) is list
        and len(index["checkpoints"])==index.get("checkpoint_count")==len(expected),"fixed complete checkpoint index required")
    verified=[]
    for row,(seed,turn) in zip(index["checkpoints"],expected):
        require(row.get("path")==f"{batch_relative}/seed_{seed}/checkpoint_turn_{turn}.ckpt" and row.get("seed")==seed
            and row.get("turn")==turn and row.get("strict_current_identity_matches") is True,"fixed captured checkpoint row required")
        actual=inspect(root,row["path"],check)
        require(all(exact(actual[k],row[k]) for k in ("path","bytes","sha256","header","file_identity")),"checkpoint changed before retirement")
        validate_header(actual["header"],index["config"],seed,turn)
        verified.append(actual)
    status=dict(schema_version=1,kind="wealth-floor-checkpoint-retirement",checkpoint_index_sha256=index_sha256,
        all_files_rechecked=True,retirement_complete=False,retired=[],expected_count=len(verified),
        incomplete_retired_list_may_be_nonexhaustive=True)
    durable_json(root/"checkpoint-retirement.json",status)
    with (root/"checkpoint-retirement.jsonl").open('xb') as journal:
        try:
            for row in verified:
                check()
                journal.write(B.canonical_bytes(dict(event="unlink_intent",path=row["path"])));journal.flush()
                unlink_original(root,row["path"],row["file_identity"]);status["retired"].append(row["path"])
                journal.write(B.canonical_bytes(dict(event="unlink_complete",path=row["path"])));journal.flush()
            os.fsync(journal.fileno())
        except BaseException as exc:
            status["error_type"]=type(exc).__name__
            durable_json(root/"checkpoint-retirement.json",status)
            raise
    status["retirement_complete"]=True
    status["incomplete_retired_list_may_be_nonexhaustive"]=False
    durable_json(root/"checkpoint-retirement.json",status)
    return status


def failure_body_selection(root,batch,config,*,clock,seconds=2):
    """Select original remaining failed CPs for a separate bounded artifact.

    No bodies are copied/read/deleted. This failure-only diagnostic budget never
    grants positive completion or more scientific work. Actual publication stays
    pending the uploader; omissions are explicitly unavailable for cross-exam.
    """
    require(type(seconds) in (int,float) and 0<seconds<=2,"failure-only selection wall bound")
    root,batch=Path(root),Path(batch);require(batch.is_relative_to(root),"failed checkpoint batch outside evidence")
    turns=expected_turns(config)
    start=clock();selected=[];omitted=[];missing=[];total=0;prefix_exhausted=False
    names=sorted((batch/f"seed_{seed}"/f"checkpoint_turn_{turn}.ckpt").relative_to(root).as_posix()
        for seed in range(42,42+config["seed_count"]) for turn in turns)
    require(len(names)<=MAX_CHECKPOINTS,"failed checkpoint count bound")
    for name in names:
        if clock()-start>seconds:
            omitted.append(dict(path=name,reason="failure_selection_deadline",bytes=None));continue
        try:
            with P.regular(root,name) as (_stream,info):size=info.st_size
        except FileNotFoundError:
            missing.append(name);continue
        except (OSError,P.ProofRefused):
            omitted.append(dict(path=name,reason="not_verified_regular_original",bytes=None));continue
        if prefix_exhausted or size>MAX_CHECKPOINT or total+size>MAX_FAILED_BODY_BYTES:
            prefix_exhausted=True
            omitted.append(dict(path=name,reason="failure_artifact_size_prefix_bound",bytes=size));continue
        total+=size;selected.append(dict(path=name,bytes=size,source_path=str(root/name),current_body_sha256=None))
    value=dict(schema_version=1,kind="wealth-floor-failed-checkpoint-body-selection",failed_producer=True,
        selection_complete_for_remaining_verified_files=not omitted,publication_complete=None,
        publication_status="pending_failure_only_uploader_and_official_artifact_verification",
        selected=selected,selected_bytes=total,omitted=omitted,missing_or_already_retired=missing,
        limits=dict(expanded_bytes=MAX_FAILED_BODY_BYTES,files=MAX_CHECKPOINTS,member_bytes=MAX_CHECKPOINT,selection_wall_seconds=seconds),
        scope="Original remaining CP bodies only; no body copy or deletion. Deterministic lexical prefix. Omitted/missing bodies are not claimed preserved by VM lifetime; partial publication stays explicit. Scientific oracle FAIL after complete mechanics uses normal captured-and-retired policy.")
    durable_json(root/"failed-checkpoint-body-selection.json",value)
    return value
