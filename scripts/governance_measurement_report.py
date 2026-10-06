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
frozen opening the example handed to the harness through a private harness view
in a copy of this invocation's experiment-function globals. The real harness
module and the original example-function globals are never modified.
Trusted source is loaded in a fresh unattached module namespace without changing
sys.argv or installing a temporary sys.modules entry. Ordinary imports performed
by the trusted example retain their normal Python behaviour.
No kernel behaviour changes and no example source is modified. The measurement
itself (``chronicler.governance_measurements.measure_governance_result``) never
calls ``run_kernel_frame``, reads an observation or a draw, or consumes an RNG.

All output is synthetic-fixture measurement. It is not calibration, not a
scientific result, not M67 qualification and not Phase 9 authorization.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from types import FunctionType, ModuleType, SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from chronicler import governance_kernel_harness as harness  # noqa: E402
from chronicler import governance_measurements as gm  # noqa: E402

EXAMPLE_PATH = REPO_ROOT / "examples" / "governance_four_kernel.py"


def _load_trusted_source(filename: str) -> dict:
    """Execute trusted Python source without runpy's process-global bookkeeping.

    This is neither code containment nor general runpy API compatibility. Bytes
    are compiled directly to preserve Python source encoding declarations and
    filename-bearing exceptions. The module is never registered in sys.modules.
    """
    namespace = vars(ModuleType("<run_path>"))
    namespace.update(__file__=filename, __cached__=None, __loader__=None,
                     __package__="", __spec__=None)
    code = compile(Path(filename).read_bytes(), filename, "exec")
    exec(code, namespace)
    return namespace


# Historical test injection seam: the accepted tests replace this object's
# run_path operation (or the object itself). This private object is not Python's
# runpy module, and its default implementation never calls that module.
runpy = SimpleNamespace(run_path=_load_trusted_source)


def run_example(example_path: Path = EXAMPLE_PATH) -> tuple[harness.HarnessCarry,
                                                          harness.HarnessResult]:
    """Run the exact existing example; return its opening carry and result.

    The existing example source is unmodified. Only its experiment function's
    direct module-global harness references use this invocation's recording
    view. Helper/closure imports are not intercepted; arbitrary alternate
    examples using those patterns are outside this adapter's contract.
    The trusted-source loader changes neither argv nor temporary module slots;
    example code itself is not contained and may perform ordinary global imports.
    """
    if not example_path.is_file():
        raise SystemExit(f"missing example: {example_path.name}")
    namespace = runpy.run_path(str(example_path))
    experiment = namespace.get("experiment")
    if not callable(experiment):
        raise SystemExit("example does not expose an experiment() callable")
    if not isinstance(experiment, FunctionType):
        raise SystemExit("example experiment must be a Python function")
    openings: list[harness.HarnessCarry] = []
    original = harness.run_kernel_frame

    def recording(*args, **kwargs):
        openings.append(kwargs["opening"])
        return original(*args, **kwargs)

    view = SimpleNamespace(**{**vars(harness), "run_kernel_frame": recording})
    bindings = {name: view if value is harness else value
                for name, value in experiment.__globals__.items()}
    isolated = FunctionType(experiment.__code__, bindings, experiment.__name__,
                            experiment.__defaults__, experiment.__closure__)
    isolated.__kwdefaults__ = experiment.__kwdefaults__
    result = isolated()
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
