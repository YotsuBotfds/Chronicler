#!/usr/bin/env python3
"""Serial saved-bundle archive/load measurements; no simulation or native import.

Example: PYTHONPATH=src python benchmark.py --out NEW_DIR --case NAME=FILE
Run a timing pilot first, then choose an elapsed budget for the remaining cases.
Each archive/plain-load/gzip-load measurement uses a fresh process. Raw input
files are retained unchanged; only new archives and compact receipts are written.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import resource
import subprocess
import sys
import time
import zlib


def digest(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            result.update(chunk)
    return result.hexdigest()


def rss_mib():
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return value / (1024 * 1024 if sys.platform == "darwin" else 1024)


def child(operation, source, output):
    import chronicler.bundle_codec as codec
    if operation == "archive":
        result = codec.archive_bundle(source, output)
        result["peak_rss_mib"] = rss_mib()
    else:
        start_cpu, start_wall = time.process_time(), time.perf_counter()
        bundle = codec.load_bundle(source)
        result = {"source": str(source), "load_cpu_s": time.process_time() - start_cpu,
                  "load_wall_s": time.perf_counter() - start_wall, "load_peak_rss_mib": rss_mib(),
                  "snapshots": len(bundle.get("history", [])),
                  "bundle_version": bundle.get("metadata", {}).get("bundle_version")}
        fingerprint_cpu, fingerprint_wall = time.process_time(), time.perf_counter()
        # JSON trees contain no tuple/subclass values: this canonical text keeps
        # all numeric types, key order, Unicode and the sign of floating zero.
        canonical = json.dumps(bundle, ensure_ascii=False, separators=(",", ":")).encode()
        result.update(decoded_sha256=hashlib.sha256(canonical).hexdigest(), decoded_json_bytes=len(canonical),
                      fingerprint_cpu_s=time.process_time() - fingerprint_cpu,
                      fingerprint_wall_s=time.perf_counter() - fingerprint_wall,
                      verification_peak_rss_mib=rss_mib())
    result.update(interpreter=sys.executable, python_version=sys.version,
                  codec_path=codec.__file__, codec_sha256=digest(codec.__file__),
                  native_loaded=any(name.startswith("chronicler_agents") for name in sys.modules))
    assert result["native_loaded"] is False
    print(json.dumps(result))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--case", action="append", default=[], help="NAME=source JSON file")
    parser.add_argument("--budget-seconds", type=float, default=180)
    parser.add_argument("--source-root", type=Path, default=Path(__file__).resolve().parents[4])
    parser.add_argument("--child", choices=("archive", "load"))
    parser.add_argument("--source", type=Path)
    parser.add_argument("--archive", type=Path)
    args = parser.parse_args()
    if args.child:
        child(args.child, args.source, args.archive)
        return
    if args.out is None or not args.case or args.budget_seconds <= 0:
        parser.error("--out, at least one --case and a positive budget are required")
    args.out.mkdir(parents=True, exist_ok=False)
    root = args.source_root.resolve()
    env = {**os.environ, "PYTHONPATH": str(root / "src"), "RAYON_NUM_THREADS": "1"}
    receipt = {"kind": "optional_lossless_transport_benchmark", "budget_wall_s": args.budget_seconds,
               "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip(),
               "tool_sha256": digest(__file__), "python_version": sys.version,
               "zlib_version": zlib.ZLIB_VERSION, "zlib_runtime_version": zlib.ZLIB_RUNTIME_VERSION,
               "claims": "Optional gzip representation only; no simulation, event reduction, raw-file deletion or RSS improvement claim.",
               "cases": [], "status": "running"}
    started = time.perf_counter()
    try:
        for item in args.case:
            name, raw = item.split("=", 1)
            if not name or Path(name).name != name:
                raise ValueError("case name must be a simple directory name")
            source = Path(raw).resolve()
            archive = args.out / f"{name}.json.gz"
            case = {"name": name, "source": str(source), "input_sha256": digest(source), "steps": {}}
            receipt["cases"].append(case)
            for label, operation, path in (("archive", "archive", source), ("plain_load", "load", source),
                                            ("gzip_load", "load", archive)):
                remaining = args.budget_seconds - (time.perf_counter() - started)
                if remaining <= 0:
                    raise TimeoutError("declared archive/load budget exhausted")
                command = [sys.executable, str(Path(__file__).resolve()), "--child", operation,
                           "--source", str(path), "--archive", str(archive)]
                result = subprocess.run(command, cwd=root, env=env, text=True, capture_output=True,
                                        timeout=min(180, remaining))
                (args.out / f"{name}-{label}.log").write_text(result.stdout + result.stderr)
                if result.returncode:
                    raise RuntimeError(f"{name}/{label} failed rc={result.returncode}")
                case["steps"][label] = json.loads(result.stdout)
            assert case["steps"]["archive"]["source_sha256"] == case["input_sha256"] == digest(source)
            assert case["steps"]["plain_load"]["decoded_sha256"] == case["steps"]["gzip_load"]["decoded_sha256"]
            case["same_decoded_values_types_order_signed_zero"] = True
            case["source_unchanged"] = True
            print(json.dumps({"case": name, "raw": case["steps"]["archive"]["source_bytes"],
                              "gzip": case["steps"]["archive"]["archive_bytes"], "decode_identity": True}), flush=True)
        receipt["status"] = "pass"
    except Exception as exc:
        receipt.update(status="failed", failure=f"{type(exc).__name__}: {exc}")
        raise
    finally:
        receipt["elapsed_wall_s"] = time.perf_counter() - started
        (args.out / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")


if __name__ == "__main__":
    main()
