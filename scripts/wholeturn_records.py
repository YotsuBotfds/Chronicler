"""Bounded data-only packaging. Raw bodies remain a separate hosted artifact.

This does not import a producer, decode checkpoints, extract files or turn an
exit code into a scientific/performance qualification.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import os
from pathlib import Path, PurePosixPath
import stat
import zipfile

import wholeturn_protocol as p


def optional_json(path, maximum=512*1024):
    path = Path(path)
    return p.read_json(path, maximum) if path.exists() else None


def build_projection(path):
    value = optional_json(path)
    if value is None:
        return {"status": "NOT_RECORDED"}
    fields = ("kind", "protocol", "arm", "source_commit", "native_tree", "controller_commit", "github",
              "driver_pins", "registration", "wheel_receipt", "schemas", "python", "package_digest",
              "python_binary", "distributions", "uv_lock", "cargo_lock", "cargo_manifest", "toolchain", "build_flags")
    return {"original": p.pin(path, 512*1024), "data": {k: value[k] for k in fields},
            "sealed_source": {"count": value["sealed_source"]["count"], "digest": value["sealed_source"]["digest"]}}


def profile_projection(path):
    path = Path(path)
    if not path.exists():
        return None
    windows = p.read_json(path, 32*p.MIB)
    result = {"original": p.pin(path, 32*p.MIB), "windows": []}
    for window in windows:
        rows = window["rows"]
        top = sorted(rows, key=lambda r: (-r["self_CPU_seconds"], r["filename"], r["line"], r["function"]))[:10]
        result["windows"].append({"window": window["window"], "function_rows": len(rows),
            "caller_edges": len(window["caller_edges"]), "display_top10_self_CPU": top,
            "coverage": window["coverage"], "display_is_complete_table": False})
    return result


def selected_records(controller_root, root, actual_step_outcome, step_outcomes=None):
    root = Path(root)
    reg = p.load_registration(controller_root, ready=False)
    admission = optional_json(root/"admission.json")
    owner = optional_json(root/"raw/owner.json", 2*p.MIB)
    preflight = optional_json(root/"metadata/execute-preflight-failure.json", 65536)
    child_bodies_allowed = (owner is not None and owner.get("raw_custody_proven") is True
                            and owner.get("raw_upload_allowed") is True)
    summary = {"kind": "MATCHED_WHOLETURN_COMPACT", "protocol": p.PROTOCOL,
        "registration": reg, "registration_pin": p.pin(Path(controller_root)/p.REGISTRATION),
        "actual_step_outcome": actual_step_outcome,
        "hosted_step_outcomes": step_outcomes,
        "status": owner["status"] if owner is not None else "NO_COMPLETE_OWNER_RECORD",
        "admission": admission,
        "owner": None if owner is None else {k: v for k, v in owner.items()
            if k not in ("roles", "comparisons", "final_raw_inventory", "final_retained_inventory")},
        "owner_original": p.pin(root/"raw/owner.json", 2*p.MIB) if owner is not None else None,
        "preflight_failure": preflight,
        "preflight_failure_original": p.pin(root/"metadata/execute-preflight-failure.json", 65536) if preflight is not None else None,
        "comparison_outcomes": owner["comparisons"] if owner is not None else [],
        "child_body_reads_allowed": child_bodies_allowed,
        "raw_upload_allowed": child_bodies_allowed,
        "custody_scope": "Parent owner/builds/launch intents only until observed quiescence and bounded final inventory; intents prove no process start.",
        "raw_inventory": None if owner is None else {k: v for k, v in owner.get("final_raw_inventory", {}).items() if k != "files"},
        "raw_inventory_digest": hashlib.sha256(p.canonical(owner.get("final_raw_inventory"))).hexdigest() if owner else None,
        "builds": {arm: build_projection(root/"metadata"/arm/"build.json") for arm in ("baseline", "candidate")},
        "performance_qualification": None, "scientific_qualification": None,
        "scope": "Saved selected producer data; full raw journals/checkpoints/ordinary output/profile tables remain remote. No replay/raw rehash claim."}
    roles = []
    for request in p.schedule(reg):
        path = root/"raw/roles"/str(request["index"])
        outcome = owner["roles"][request["index"]] if owner is not None else {"request": request, "status": "NOT_RECORDED"}
        value = optional_json(path/"result.json") if child_bodies_allowed else None
        row = {"request": request, "owner_outcome": outcome, "role_data": value,
               "role_original": p.pin(path/"result.json", 512*1024) if value is not None else None,
               "profile_display": profile_projection(path/"profile-functions.json") if child_bodies_allowed else None,
               "parent_launch_intent": optional_json(path/"launch-intent.json",65536)}
        journal = path/"timing.jsonl"
        if child_bodies_allowed and journal.exists():
            original = p.pin(journal, 65536)
            body = journal.read_bytes()
            p.require(original == {"bytes": len(body), "sha256": hashlib.sha256(body).hexdigest()}, "whole role clock journal changed")
            # Keep original literal bytes as a UTF-8 JSON string; no resampling.
            row["timing_journal"] = body.decode("utf-8", "strict")
            row["timing_journal_original"] = original
        roles.append(row)
    pairs = []
    for pair in dict.fromkeys(q["pair"] for q in p.schedule(reg)):
        path = root/"raw/comparisons"/pair/"result.json"
        value = optional_json(path, p.MIB) if child_bodies_allowed else None
        pairs.append({"pair": pair, "data": value,
                      "original": p.pin(path, p.MIB) if value is not None else None,
                      "parent_launch_intent": optional_json(path.parent/"launch-intent.json",65536)})
    return {"summary.json": p.canonical(summary), "roles.json": p.canonical(roles), "pairs.json": p.canonical(pairs)}


def pack(records, output):
    p.require(set(records) == {"summary.json", "roles.json", "pairs.json"}
              and all(type(body) is bytes for body in records.values()), "closed compact bodies")
    manifest = {"kind": "MATCHED_WHOLETURN_COMPACT_MANIFEST", "protocol": p.PROTOCOL,
        "members": {name: {"bytes": len(body), "sha256": hashlib.sha256(body).hexdigest()}
                    for name, body in sorted(records.items())},
        "scientific_qualification": None, "performance_qualification": None}
    records = {**records, "manifest.json": p.canonical(manifest)}
    p.require(sum(map(len, records.values())) <= p.MIB, "compact expanded body refusal")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, body in sorted(records.items()):
            info = zipfile.ZipInfo(name, (2026, 10, 30, 0, 0, 0))
            info.compress_type, info.external_attr = zipfile.ZIP_DEFLATED, (stat.S_IFREG|0o444)<<16
            archive.writestr(info, body)
    return p.write_new(output, buffer.getvalue(), p.MIB)


def inspect_original(path):
    """Read one saved original in RAM; no extraction or scientific execution."""
    original = p.pin(path, p.MIB)
    body = Path(path).read_bytes()
    p.require(original == {"bytes": len(body), "sha256": hashlib.sha256(body).hexdigest()}, "original changed")
    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        rows = archive.infolist()
        p.require(len(rows) == 4 and {r.filename for r in rows} ==
                  {"summary.json", "roles.json", "pairs.json", "manifest.json"}, "closed unique member census")
        p.require(sum(r.file_size for r in rows) <= p.MIB, "expanded byte bound")
        records = {}
        for row in rows:
            p.require(row.orig_filename == row.filename and PurePosixPath(row.filename).name == row.filename and "\x00" not in row.filename
                      and not row.is_dir() and not row.flag_bits & 1
                      and stat.S_ISREG(row.external_attr>>16) and row.compress_type == zipfile.ZIP_DEFLATED,
                      "regular bounded compact member")
            records[row.filename] = archive.read(row)
    manifest = p.strict_json(records["manifest.json"])
    expected = {name: {"bytes": len(value), "sha256": hashlib.sha256(value).hexdigest()}
                for name, value in records.items() if name != "manifest.json"}
    p.require(manifest["kind"] == "MATCHED_WHOLETURN_COMPACT_MANIFEST"
              and manifest["protocol"] == p.PROTOCOL and manifest["members"] == expected,
              "complete selected manifest joins")
    return {"original": original, "data": {name: p.strict_json(value) for name, value in records.items()},
            "scope": "ZIP/hash/selected-data structural inspection only; official run/source/spec joins still required."}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("pack", "inspect"))
    parser.add_argument("--controller-root", type=Path)
    parser.add_argument("--root", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--actual-step-outcome", default="unknown")
    parser.add_argument("--step-outcomes-json")
    args = parser.parse_args(argv)
    if args.command == "inspect":
        print(p.canonical(inspect_original(args.output)).decode(), end="")
    else:
        p.require(args.actual_step_outcome in ("success", "failure", "cancelled", "skipped", "unknown"), "literal hosted step outcome")
        steps = p.strict_json(args.step_outcomes_json) if args.step_outcomes_json else None
        if steps is not None:
            p.require(type(steps) is dict and set(steps) == {"admission", "environments", "baseline", "candidate", "owner"}
                      and all(value in ("success", "failure", "cancelled", "skipped") for value in steps.values()), "closed actual hosted step outcomes")
        selected = selected_records(args.controller_root, args.root, args.actual_step_outcome, steps)
        allowed = p.strict_json(selected["summary.json"])["raw_upload_allowed"]
        result = pack(selected,args.output)
        if os.environ.get("GITHUB_OUTPUT"):
            with Path(os.environ["GITHUB_OUTPUT"]).open("a") as stream:
                stream.write("raw_upload_allowed="+("true" if allowed else "false")+"\n")
        print(p.canonical(result).decode(), end="")


if __name__ == "__main__":
    raise SystemExit(main())
