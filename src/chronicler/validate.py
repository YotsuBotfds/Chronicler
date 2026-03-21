"""M53b: Validation oracle runner.

Usage: python -m chronicler.validate --batch-dir <path> --oracles all
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path

SCRUB_KEYS = {"generated_at"}

def scrubbed_equal(a: dict, b: dict) -> bool:
    """Compare two bundles ignoring transient metadata fields."""
    def _scrub(d):
        if isinstance(d, dict):
            return {k: _scrub(v) for k, v in d.items() if k not in SCRUB_KEYS}
        if isinstance(d, list):
            return [_scrub(x) for x in d]
        return d
    return _scrub(a) == _scrub(b)

def run_determinism_gate(batch_dir: Path) -> dict:
    """Run determinism smoke gate: 2 identical seeds must produce scrubbed-equal output."""
    # Implementation: load two bundles with same seed, compare
    pass

def run_oracles(batch_dir: Path, oracles: list[str]) -> dict:
    """Run specified oracles and return structured report."""
    results = {}
    if "all" in oracles or "determinism" in oracles:
        results["determinism"] = run_determinism_gate(batch_dir)
    return results

def main():
    parser = argparse.ArgumentParser(description="M53b validation oracle runner")
    parser.add_argument("--batch-dir", required=True, type=Path)
    parser.add_argument("--oracles", nargs="+", default=["all"])
    args = parser.parse_args()
    report = run_oracles(args.batch_dir, args.oracles)
    json.dump(report, sys.stdout, indent=2)

if __name__ == "__main__":
    main()
