"""Default-off illustrative memome candidate preview; stdout only, no saves."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from chronicler import experiment_sessions as es
from chronicler.memome_candidate_preview import (
    Alternative, CONTRACT, PreviewError, PreviewReport, preview_candidates, preview_json, preview_text,
)


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise PreviewError(message)


def _alternatives(data: bytes, transport: es.TransportPolicy, maximum: int) -> tuple:
    if type(maximum) is not int or maximum <= 0:
        raise PreviewError("max_alternatives must be an exact positive integer")
    payload = es.submission_from_bytes(data, transport=transport, label="alternatives")
    if type(payload) is not dict or set(payload) != {"contract", "alternatives"}:
        raise PreviewError("alternatives document fields must be exactly contract and alternatives")
    if type(payload["contract"]) is not str or payload["contract"] != CONTRACT:
        raise PreviewError("unsupported alternatives contract")
    records = payload["alternatives"]
    if type(records) is not list or not 1 <= len(records) <= maximum:
        raise PreviewError("alternative count must be between 1 and max_alternatives")
    result = []
    for index, record in enumerate(records):
        if type(record) is not dict or set(record) != {"label", "batch"}:
            raise PreviewError(f"alternative {index}: fields must be exactly label and batch")
        try:
            batch = es.memome_batch_from_payload(record["batch"], transport=transport)
        except ValueError as exc:
            raise PreviewError(f"alternative {record['label']!r}: {exc}") from exc
        result.append(Alternative(record["label"], batch))
    return tuple(result)


def main(argv=None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    help_requested = any(flag in arguments for flag in ("-h", "--help"))
    if "--enable" not in arguments and not help_requested:
        sys.stdout.write(preview_json(PreviewReport()))
        return 0
    parser = _Parser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--enable", action="store_true")
    parser.add_argument("--path", type=Path)
    parser.add_argument("--transport", type=Path)
    parser.add_argument("--alternatives", type=Path)
    parser.add_argument("--max-alternatives", type=int)
    parser.add_argument("--format", choices=("json", "text"), default="json")
    if help_requested:
        parser.print_help()
        return 0
    try:
        args = parser.parse_args(arguments)
        if any(value is None for value in (args.path, args.transport, args.alternatives, args.max_alternatives)):
            raise PreviewError("--enable requires --path, --transport, --alternatives and --max-alternatives")
        if args.max_alternatives <= 0:
            raise PreviewError("max_alternatives must be an exact positive integer")
        raw_transport = es.read_regular_file_bytes(args.transport, max_bytes=4096, label="transport policy")
        transport = es.transport_policy_from_text(raw_transport.decode("utf-8"))
        raw_choices = es.read_regular_file_bytes(args.alternatives, max_bytes=transport.max_bytes,
                                                 label="alternatives")
        alternatives = _alternatives(raw_choices, transport, args.max_alternatives)
        loaded = es.load_session(args.path, transport=transport)
        report = preview_candidates(enabled=True, session=loaded.session, alternatives=alternatives,
                                    max_alternatives=args.max_alternatives, transport=transport)
        observation = {"path": loaded.path, "generation": loaded.generation,
                       "turn": loaded.turn, "file_digest": loaded.digest,
                       "scope": "one verified read; currentness and durability are not asserted",
                       "submission_token": False}
        if args.format == "json":
            payload = report.as_payload()
            payload["cli_observation"] = observation
            output = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"
        else:
            output = preview_text(report) + "CLI observation: " + json.dumps(
                observation, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"
        sys.stdout.write(output)
    except (ValueError, OSError, TypeError) as exc:
        sys.stderr.write(json.dumps({"error": type(exc).__name__, "detail": str(exc)},
                                    sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n")
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
