#!/usr/bin/env python3
"""Generate a sample chronicle_bundle.json for the viewer test fixtures.

Run: python scripts/generate_viewer_fixture.py
Output: viewer/src/__fixtures__/sample_bundle.json
"""
import argparse
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from chronicler.bundle_codec import load_bundle
from chronicler.main import execute_run


def main():
    tmp_dir = Path("output/_fixture_gen")
    tmp_dir.mkdir(parents=True, exist_ok=True)

    args = argparse.Namespace(
        seed=42, turns=10, civs=4, regions=8,
        output=str(tmp_dir / "chronicle.md"),
        state=str(tmp_dir / "state.json"),
        resume=None, reflection_interval=10,
        llm_actions=False, scenario=None, pause_every=None,
    )
    execute_run(args)

    src = tmp_dir / "chronicle_bundle.json"
    dst = Path("viewer/src/__fixtures__/sample_bundle.json")
    dst.parent.mkdir(parents=True, exist_ok=True)
    # The viewer's tests import the fixture as a bundle, so write it decoded
    # (the version-5 layout; the bundle file itself is version 6).
    dst.write_text(json.dumps(load_bundle(src), ensure_ascii=False, separators=(",", ":")),
                   encoding="utf-8")
    print(f"Fixture written to {dst} ({dst.stat().st_size} bytes)")

    shutil.rmtree(tmp_dir)


if __name__ == "__main__":
    main()
