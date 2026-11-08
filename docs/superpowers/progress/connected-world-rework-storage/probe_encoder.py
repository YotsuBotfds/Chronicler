#!/usr/bin/env python3
"""Reproduce the rejected scalar-only encoder shortcut on a frozen source.

This compiles both codecs in memory; it never edits the checkout or simulation.
The retained measurement used original codec SHA3b362f4e... from main2726.
"""
from __future__ import annotations

import argparse
import gc
import hashlib
import json
from pathlib import Path
import resource
import subprocess
import sys
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--source-root", type=Path, default=Path(__file__).resolve().parents[4])
    parser.add_argument("--source-ref", default="2726bf449d0e4d581a72034000ee0861a58ee439")
    args = parser.parse_args()
    source = subprocess.check_output(["git", "show", f"{args.source_ref}:src/chronicler/bundle_codec.py"],
                                     cwd=args.source_root, text=True)
    anchor = "    if type(a) is dict and type(b) is dict:\n        return _diff_dict(a, b)"
    candidate = ("    if type(b) not in (dict, list):\n        return b\n" + anchor)
    assert source.count(anchor) == 1
    old, new = {"__name__": "frozen_codec"}, {"__name__": "candidate_codec"}
    exec(compile(source, "<frozen-codec>", "exec"), old)
    exec(compile(source.replace(anchor, candidate), "<candidate-codec>", "exec"), new)
    raw = args.bundle.read_bytes()
    expected = hashlib.sha256(raw).hexdigest()
    bundle = old["load_bundle"](args.bundle)
    rows = []
    for repeat in range(3):
        pair = [("old", old), ("candidate", new)]
        if repeat % 2:
            pair.reverse()
        for name, module in pair:
            gc.collect()
            cpu, wall = time.process_time(), time.perf_counter()
            encoded = module["dumps_bundle"](bundle)
            seconds = time.process_time() - cpu
            digest = hashlib.sha256(encoded.encode()).hexdigest()
            assert digest == expected
            row = {"repeat": repeat, "implementation": name, "cpu_s": seconds,
                   "wall_s": time.perf_counter() - wall, "encoded_bytes": len(encoded.encode()),
                   "sha256": digest, "max_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
            rows.append(row)
            print(json.dumps(row), flush=True)
            del encoded
    result = {"kind": "same-input-encoder-prototype", "runtime_modified": False,
              "source_commit": args.source_ref, "source_sha256": hashlib.sha256(source.encode()).hexdigest(),
              "input": str(args.bundle), "input_sha256": expected, "python_version": sys.version,
              "candidate_change": "Return non-dict/list replacements before container dispatch; no format change.",
              "rows": rows}
    args.output.write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()
