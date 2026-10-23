"""Default-off continuous inspection of the accepted two-turn synthetic fixture.

Only --enabled --fixture existing-two-turn executes the two fixture kernels.
The sequence inspector executes none. Reports go only to stdout.
"""
from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if __name__ == "__main__":
    sys.path.insert(0, str(REPO_ROOT / "src"))

from chronicler import governance_measurements as gm
from chronicler import governance_sequence as sequence


def capture_fixture(*, origin, source_identity):
    """Load only the trusted local accepted C script, without registering it.

    No runpy, legacy wrapper, argv patch, module-slot patch or user Python path.
    C owns fixture construction and its exact carry codec restart boundary.
    """
    spec = importlib.util.spec_from_file_location(
        "explicit_sequence_capture_fixture", REPO_ROOT / "scripts" / "governance_capture_report.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.capture_fixture(origin=origin, source_identity=source_identity)


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--enabled", action="store_true")
    parser.add_argument("--fixture", choices=("existing-two-turn",))
    parser.add_argument("--origin", choices=tuple(origin.value for origin in gm.MeasurementOrigin))
    parser.add_argument("--revision")
    parser.add_argument("--tree")
    parser.add_argument("--source-label")
    parser.add_argument("--max-frames", type=int)
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv=None):
    raw = list(sys.argv[1:] if argv is None else argv)
    dispatch = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    dispatch.add_argument("--enabled", action="store_true")
    dispatch.add_argument("-h", "--help", action="store_true")
    activation, _ = dispatch.parse_known_args(raw)
    if activation.help:
        build_parser().parse_args(["--help"])
    if not activation.enabled:
        text = sequence.sequence_json(sequence.inspect_sequence())
        sys.stdout.write(text)
        return 0
    parser = build_parser()
    args = parser.parse_args(raw)
    if not all((args.fixture, args.origin, args.revision, args.tree, args.source_label)) or args.max_frames is None:
        parser.error("enabled sequence requires fixture, origin, revision, tree, source-label and max-frames")
    try:
        identity = gm.SourceIdentity(args.revision, args.tree, args.source_label)
        # This one supported fixture has exactly two frames. Reject its cap
        # before fixture work, then the inspector independently checks the tuple.
        if args.max_frames < 2:
            raise ValueError("existing-two-turn requires max-frames >= 2")
        captures = capture_fixture(origin=gm.MeasurementOrigin(args.origin), source_identity=identity)
        receipt = sequence.inspect_sequence(enabled=True, captures=captures, max_frames=args.max_frames)
        text = sequence.sequence_json(receipt) if args.json else sequence.render_report(receipt)
    except ValueError as error:
        parser.error(str(error))
    sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
