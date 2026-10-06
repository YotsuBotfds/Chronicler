"""Opt-in measurement report over the detached four-kernel governance harness.

This is a standalone reporting seam. It adds instrumentation, not a governance
mechanic: it never constructs a world, fixture world, seed campaign or long run,
never edits any repository file, and never touches the production runtime, shared
models, agent bridge, native pool or CLI registry.

The default is OFF. Without ``--run-example`` the script imports no example
module, runs no experiment and measures nothing: it prints the deterministic
default-off notice listing every M67 obligation that stays unavailable.

    python scripts/governance_measurement_report.py                       # default off
    python scripts/governance_measurement_report.py --run-example          # text report
    python scripts/governance_measurement_report.py --run-example --json   # JSON frame
    python scripts/governance_measurement_report.py --run-example \
        --output /tmp/governance-measurement-report.txt

``--run-example`` invokes the exact existing ``examples/governance_four_kernel.py``
experiment unchanged, then measures its already-produced result. Because that
example builds its opening carry internally, the script observes the explicit
frozen opening the example handed to the harness by wrapping ``run_kernel_frame``
in-process for the duration of the call and restoring it in a ``finally`` block.
No kernel behaviour changes and no example source is modified. The measurement
itself (``chronicler.governance_measurements.measure_governance_result``) never
calls ``run_kernel_frame``, reads an observation or a draw, or consumes an RNG.

All output is synthetic-fixture measurement. It is not calibration, not a
scientific result, not M67 qualification and not Phase 9 authorization.
"""
from __future__ import annotations

import argparse
import runpy
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from chronicler import governance_kernel_harness as harness  # noqa: E402
from chronicler import governance_measurements as gm  # noqa: E402

EXAMPLE_PATH = REPO_ROOT / "examples" / "governance_four_kernel.py"


def run_example(example_path: Path = EXAMPLE_PATH) -> tuple[harness.HarnessCarry,
                                                          harness.HarnessResult]:
    """Run the exact existing example; return its opening carry and result.

    The example is executed unmodified. ``run_kernel_frame`` is wrapped for the
    duration of the call so the opening carry it passed is observable, and the
    original entry point is always restored.
    """
    if not example_path.is_file():
        raise SystemExit(f"missing example: {example_path.name}")
    namespace = runpy.run_path(str(example_path))
    experiment = namespace.get("experiment")
    if not callable(experiment):
        raise SystemExit("example does not expose an experiment() callable")
    openings: list[harness.HarnessCarry] = []
    original = harness.run_kernel_frame

    def recording(*args, **kwargs):
        openings.append(kwargs["opening"])
        return original(*args, **kwargs)

    harness.run_kernel_frame = recording
    try:
        result = experiment()
    finally:
        harness.run_kernel_frame = original
    if not openings:
        raise SystemExit("example invoked no kernel frame")
    return openings[-1], result


def measure_example(source_identity: gm.SourceIdentity,
                    origin: gm.MeasurementOrigin,
                    example_path: Path = EXAMPLE_PATH) -> gm.GovernanceMeasurementFrame:
    """Opt in: run the existing synthetic example, then measure its result."""
    opening, result = run_example(example_path)
    return gm.measure_governance_result(opening=opening, result=result, origin=origin,
                                        source_identity=source_identity)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Report what the detached four-kernel governance harness emits. "
                    "Measurement is opt-in; the default runs nothing.")
    parser.add_argument("--run-example", action="store_true",
                        help="opt in: run examples/governance_four_kernel.py, then measure it")
    parser.add_argument("--json", action="store_true",
                        help="emit the canonical JSON measurement frame instead of the report")
    parser.add_argument("--output", type=Path, default=None,
                        help="also write the emitted text to this path")
    parser.add_argument("--origin", choices=[member.value for member in gm.MeasurementOrigin],
                        default=gm.MeasurementOrigin.SYNTHETIC_FOUR_KERNEL_HARNESS.value,
                        help="declared provenance of the measured result")
    parser.add_argument("--revision", default=gm.REVIEWED_HARNESS_SOURCE.revision,
                        help="40 hex source revision recorded in the report")
    parser.add_argument("--tree", default=gm.REVIEWED_HARNESS_SOURCE.tree,
                        help="40 hex source tree recorded in the report")
    parser.add_argument("--source-label", default=gm.REVIEWED_HARNESS_SOURCE.label,
                        help="human label describing the recorded source identity")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        identity = gm.SourceIdentity(revision=args.revision, tree=args.tree,
                                     label=args.source_label)
    except ValueError as error:
        raise SystemExit(f"invalid source identity: {error}") from error
    if not args.run_example:
        sys.stdout.write(gm.render_obligation_catalogue(identity))
        return 0
    frame = measure_example(identity, gm.MeasurementOrigin(args.origin))
    text = gm.measurement_json(frame) if args.json else gm.render_report(frame)
    if args.output is not None:
        args.output.write_text(text, encoding="utf-8")
    sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())