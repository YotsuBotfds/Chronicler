"""Standalone operator CLI for durable detached experiment sessions.

Default invocation performs no file read, no file write and no kernel call: it
prints the closed command surface and a documented transport policy. Explicit
subcommands use only the public ``chronicler.experiment_sessions`` API and the
two reviewed detached kernels. Nothing here starts a simulation, draws an RNG,
generates a world, or touches production state, bundles or the CLI registry.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import runpy
import sys

# Supports direct invocation without installing or importing the production CLI.
if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from chronicler import experiment_sessions as es  # noqa: E402


COMMANDS = ("create", "apply", "inspect", "verify")
_EXIT_OK = 0
_EXIT_ERROR = 3

_DEMO_SCRIPTS = {"m60a": "campaign_logistics_demo.py", "m68a": "memome_demo.py"}


def _emit(payload: dict) -> None:
    sys.stdout.write(json.dumps(payload, sort_keys=True, separators=(",", ":"),
                                allow_nan=False) + "\n")


def _read_bounded(path: str, limit: int, label: str) -> bytes:
    """Read one regular descriptor within the byte cap before parsing."""
    return es.read_regular_file_bytes(path, max_bytes=limit, label=label)


def _transport(path: str) -> es.TransportPolicy:
    """An explicit versioned transport policy is required before any IO."""
    data = _read_bounded(path, 4096, "transport policy")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise es.SessionError("transport policy is not valid UTF-8") from exc
    return es.transport_policy_from_text(text)


def _submission(path: str, transport: es.TransportPolicy, label: str) -> dict:
    """One bounded strict decoder for every explicit caller document."""
    payload = es.submission_from_bytes(_read_bounded(path, transport.max_bytes, label),
                                       transport=transport, label=label)
    if type(payload) is not dict:
        raise es.SessionError(f"the {label} must be a JSON object")
    return payload


def _demo_tables(kernel: str) -> dict:
    """Load the existing hand-calculated demo tables without running the demo."""
    script = Path(__file__).resolve().parent / _DEMO_SCRIPTS[kernel]
    return runpy.run_path(str(script))


def _demo_campaign_session() -> es.CampaignSession:
    tables = _demo_tables("m60a")
    policy, topology = tables["illustrative_policy"](), tables["fixture_topology"]()
    admitted = tables["fixture_session"](policy, topology).state
    return es.create_campaign_session(
        policy=policy, topology=topology, campaign_id=admitted.campaign_id,
        turn=admitted.admission_turn, staging=admitted.staging, target=admitted.target,
        soldiers=admitted.soldiers, stocks=admitted.stocks)


def _demo_memome_session() -> es.MemomeSession:
    tables = _demo_tables("m68a")
    policy, (people, _batches) = tables["illustrative_policy"](), tables["unit_tables"]()
    return es.create_memome_session(policy=policy, genesis_turn=0, participants=people)


def _create(args: argparse.Namespace) -> dict:
    transport = _transport(args.transport)
    if bool(args.demo) == (args.admission is not None):
        raise es.SessionError("exactly one of --demo or --admission is required")
    if args.demo:
        session = (_demo_campaign_session() if args.kernel == "m60a"
                   else _demo_memome_session())
    else:
        payload = _submission(args.admission, transport, "admission")
        session = (es.campaign_session_from_payload(payload, transport=transport)
                   if args.kernel == "m60a"
                   else es.memome_session_from_payload(payload, transport=transport))
    result = es.commit_session(args.path, session, transport=transport,
                               expected_generation=None, expected_digest=None)
    return {"command": "create", "kernel": args.kernel, "path": result.path,
            "generation": result.generation, "turn": result.turn, "digest": result.digest,
            "session_digest": result.envelope.session_digest,
            "transport": result.envelope.transport.as_payload()}


def _apply(args: argparse.Namespace) -> dict:
    transport = _transport(args.transport)
    loaded = es.load_session(args.path, transport=transport)
    payload = _submission(args.batch, transport, "batch")
    if type(loaded.session) is es.CampaignSession:
        applied = es.apply_campaign_tick(loaded.session,
                                         es.campaign_tick_from_payload(payload,
                                                                      transport=transport))
    elif type(loaded.session) is es.MemomeSession:
        applied = es.apply_memome_batch(loaded.session,
                                        es.memome_batch_from_payload(payload,
                                                                      transport=transport))
    else:
        raise es.SessionError("the loaded session uses an unsupported kernel")
    report = {"command": "apply", "kernel": loaded.envelope.kernel, "turn": applied.turn,
              "changed": applied.changed, "replayed": applied.replayed,
              "receipt_count": len(applied.receipts),
              "previous_generation": loaded.generation}
    if not applied.changed:
        report.update({"committed": False, "generation": loaded.generation,
                       "digest": loaded.digest,
                       "note": "identical replay wrote nothing"})
        return report
    result = es.commit_session(args.path, applied.session, transport=transport,
                               expected_generation=loaded.generation,
                               expected_digest=loaded.digest)
    report.update({"committed": True, "generation": result.generation,
                   "digest": result.digest,
                   "session_digest": result.envelope.session_digest})
    return report


def _inspect(args: argparse.Namespace) -> dict:
    transport = _transport(args.transport)
    report = es.session_report(es.load_session(args.path, transport=transport))
    report.update({"command": "inspect", "path": args.path, "writes": False})
    return report


def _verify(args: argparse.Namespace) -> dict:
    transport = _transport(args.transport)
    loaded = es.load_session(args.path, transport=transport)
    return {"command": "verify", "path": loaded.path, "verified": True, "writes": False,
            "kernel": loaded.envelope.kernel, "generation": loaded.generation,
            "turn": loaded.turn, "digest": loaded.digest,
            "session_digest": loaded.envelope.session_digest,
            "transport": loaded.envelope.transport.as_payload(),
            "commit_order": list(es.SESSION_COMMIT_ORDER)}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Durable local sessions for the reviewed detached experiments.",
        epilog="Running this script with no subcommand is a no-op.")
    subparsers = parser.add_subparsers(dest="command")

    create = subparsers.add_parser("create", help="create one session from explicit inputs")
    create.add_argument("--kernel", required=True, choices=sorted(es.KERNEL_CONTRACTS))
    create.add_argument("--path", required=True)
    create.add_argument("--transport", required=True)
    create.add_argument("--demo", action="store_true",
                        help="use the existing hand-calculated demo inputs")
    create.add_argument("--admission", help="caller-supplied typed admission JSON")

    apply_parser = subparsers.add_parser("apply", help="apply exactly one explicit batch")
    apply_parser.add_argument("--path", required=True)
    apply_parser.add_argument("--transport", required=True)
    apply_parser.add_argument("--batch", required=True)

    inspect = subparsers.add_parser("inspect", help="inspect the latest state and receipts")
    inspect.add_argument("--path", required=True)
    inspect.add_argument("--transport", required=True)

    verify = subparsers.add_parser("verify", help="verify and resume one session file")
    verify.add_argument("--path", required=True)
    verify.add_argument("--transport", required=True)
    return parser


def _default_output() -> dict:
    return {
        "contract": es.CONTRACT,
        "envelope_version": es.ENVELOPE_VERSION,
        "commands": list(COMMANDS),
        "default_invocation": "no-op",
        "reads_files": False,
        "writes_files": False,
        "calls_kernels": False,
        "source_head": es.BASELINE_SOURCE_HEAD,
        "source_tree": es.BASELINE_SOURCE_TREE,
        "kernel_contracts": dict(es.KERNEL_CONTRACTS),
        "documented_transport_policy": es.documented_transport_policy().as_payload(),
        "commit_order": list(es.SESSION_COMMIT_ORDER),
        "limits": {
            "one_writer": True,
            "local_posix_filesystem_only": True,
            "production_state": "never read or written",
            "kernel_arithmetic": "unchanged",
            "milestones": "none; this is operator tooling only",
        },
    }


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if not arguments:
        _emit(_default_output())
        return _EXIT_OK
    if arguments[0] in ("-h", "--help"):
        _parser().print_help()
        return _EXIT_OK
    if arguments[0] not in COMMANDS:
        _emit(_default_output())
        return _EXIT_OK
    args = _parser().parse_args(arguments)
    handlers = {"create": _create, "apply": _apply, "inspect": _inspect, "verify": _verify}
    try:
        _emit(handlers[args.command](args))
    except es.CommittedCleanupError as exc:
        result = exc.result
        _emit({"command": args.command, "committed": True, "status": "committed_durable",
               "path": result.path, "generation": result.generation, "turn": result.turn,
               "digest": result.digest, "session_digest": result.envelope.session_digest})
        sys.stderr.write(json.dumps(
            {"error": type(exc).__name__, "detail": str(exc),
             "cleanup_error": type(exc.cleanup_error).__name__,
             "cleanup_detail": str(exc.cleanup_error)},
            sort_keys=True, separators=(",", ":")) + "\n")
        return _EXIT_ERROR
    except es.SessionError as exc:
        # Includes TransportDomainError, ContractError and the persistence tree.
        sys.stderr.write(json.dumps({"error": type(exc).__name__, "detail": str(exc)},
                                    sort_keys=True, separators=(",", ":")) + "\n")
        return _EXIT_ERROR
    except (ValueError, OSError) as exc:
        # Session errors and the kernels' own ValueError rejections are reported
        # identically; nothing is retried and nothing is written here.
        sys.stderr.write(json.dumps({"error": type(exc).__name__, "detail": str(exc)},
                                    sort_keys=True, separators=(",", ":")) + "\n")
        return _EXIT_ERROR
    return _EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())