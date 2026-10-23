"""Default-off CLI for one explicit session operation or read-only reconciliation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from chronicler import experiment_sessions as es
from chronicler import session_operations as operations


def _emit(payload: dict, *, error: bool = False) -> None:
    stream = sys.stderr if error else sys.stdout
    stream.write(json.dumps(payload, sort_keys=True, separators=(",", ":"),
                            allow_nan=False) + "\n")


def _read_bounded(path: str, limit: int, label: str) -> bytes:
    return es.read_regular_file_bytes(path, max_bytes=limit, label=label)


def _transport(path: str) -> es.TransportPolicy:
    data = _read_bounded(path, 4096, "transport policy")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise es.SessionError("transport policy is not valid UTF-8") from error
    return es.transport_policy_from_text(text)


def _expectation(text: str, transport: es.TransportPolicy) -> operations.ReconcileExpectation:
    payload = es.submission_from_bytes(text.encode("utf-8"), transport=transport,
                                       label="reconcile expectation")
    return operations.expectation_from_payload(payload)


def _publish(receipt, *, error: bool = False) -> int:
    """Delivery failure never reclassifies a completed operation as a rejection."""
    try:
        _emit(receipt.as_payload(), error=error)
    except OSError as output_error:
        if not error:
            try:
                _emit({"contract": operations.CONTRACT, "status": "output_delivery_failed",
                       "operation_receipt": receipt.as_payload(),
                       "error": {"error_type": type(output_error).__name__, "detail": str(output_error)},
                       "note": "output failure does not undo the operation or authorize a retry"},
                      error=True)
            except OSError:
                pass  # Both output channels are unavailable; never submit again.
        return 3
    return 3 if error else 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--enable", action="store_true")
    commands = parser.add_subparsers(dest="command", required=True)
    apply = commands.add_parser("apply", help="submit once; never retry a conflict")
    apply.add_argument("--path", required=True)
    apply.add_argument("--transport", required=True)
    apply.add_argument("--submission", required=True)
    apply.add_argument("--precondition", help="require the exact reviewed-base declaration")
    reconcile = commands.add_parser("reconcile", help="observe without writing")
    reconcile.add_argument("--path", required=True)
    reconcile.add_argument("--transport", required=True)
    reconcile.add_argument("--expectation-json", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments in (["-h"], ["--help"]):
        _parser().print_help()
        return 0
    if "--enable" not in arguments:
        _emit({"contract": operations.CONTRACT, "status": "disabled",
               "reads_files": False, "writes_files": False, "calls_kernels": False})
        return 0
    args = _parser().parse_args(arguments)
    try:
        transport = _transport(args.transport)
        if args.command == "apply":
            submission = _read_bounded(args.submission, transport.max_bytes, "submission")
            if args.precondition is None:
                receipt = operations.apply_operation(args.path, transport=transport,
                                                      submission=submission)
            else:
                precondition = operations.apply_precondition_from_bytes(
                    _read_bounded(args.precondition, transport.max_bytes, "apply precondition"),
                    transport=transport)
                receipt = operations.apply_operation(args.path, transport=transport,
                                                      submission=submission, precondition=precondition)
        else:
            receipt = operations.reconcile_operation(
                args.path, transport=transport,
                expectation=_expectation(args.expectation_json, transport))
    except Exception as error:
        receipt = getattr(error, "operation_receipt", None)
        if receipt is None:
            receipt = operations.OperationReceipt(
                "rejected", args.path, None, None, None,
                operations.ErrorInfo(type(error).__name__, str(error)))
        return _publish(receipt, error=True)
    return _publish(receipt, error=receipt.status == "unreadable_or_invalid")


if __name__ == "__main__":
    raise SystemExit(main())
