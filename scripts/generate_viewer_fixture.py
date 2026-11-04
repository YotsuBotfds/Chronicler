#!/usr/bin/env python3
"""Generate the viewer's sample bundle fixture from a fresh 10-turn run.

    python scripts/generate_viewer_fixture.py --out PATH
    python scripts/generate_viewer_fixture.py --write

Runs ``chronicler.main.execute_run`` (seed 42, 10 turns, 4 civs, 8 regions:
the arguments of ``tests/test_bundle.py``'s fixture contract test) in a
temporary directory and writes the decoded bundle (the version-5 layout; the
run's bundle file is version 6) as compact JSON. ``--out`` writes PATH;
``--write`` replaces the checked-in
``viewer/src/__fixtures__/sample_bundle.json``. Without either it writes
nothing. ``metadata.generated_at`` is the time of the run, so two runs
differ only in that field.

The checked-in fixture predates this writer (indented, generated
2026-04-01, no ``bundle_version``) and does not reproduce: ``--write``
rewrites the whole file. Review the diff and run the viewer tests before
committing one.
"""
import argparse
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "viewer" / "src" / "__fixtures__" / "sample_bundle.json"


def generate(dst: Path) -> None:
    sys.path.insert(0, str(ROOT / "src"))
    from chronicler.bundle_codec import load_bundle
    from chronicler.main import execute_run

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        args = argparse.Namespace(
            seed=42, turns=10, civs=4, regions=8,
            output=str(tmp_dir / "chronicle.md"),
            state=str(tmp_dir / "state.json"),
            resume=None, reflection_interval=10,
            llm_actions=False, scenario=None, pause_every=None,
        )
        execute_run(args)
        bundle = load_bundle(tmp_dir / "chronicle_bundle.json")

    dst.parent.mkdir(parents=True, exist_ok=True)
    # The viewer's tests import the fixture as a bundle, so write it decoded
    # (the version-5 layout; the bundle file itself is version 6).
    dst.write_text(json.dumps(bundle, ensure_ascii=False, separators=(",", ":")),
                   encoding="utf-8")
    print(f"Fixture written to {dst} ({dst.stat().st_size} bytes)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--out", type=Path, help="write the fixture to this path")
    target.add_argument("--write", action="store_true",
                        help=f"replace the checked-in {FIXTURE.relative_to(ROOT).as_posix()}")
    args = parser.parse_args(argv)
    generate(FIXTURE if args.write else args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
