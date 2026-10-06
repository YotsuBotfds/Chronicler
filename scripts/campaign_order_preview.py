"""Default-off next-turn campaign order preview; complete output on stdout only."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import stat
import sys

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from chronicler import experiment_sessions as es
from chronicler.campaign_order_preview import (
    Alternative, CONTRACT, PreviewError, PreviewReport, preview_json, preview_orders, preview_text,
)


def _regular(path: Path) -> None:
    if not stat.S_ISREG(path.lstat().st_mode):
        raise PreviewError("inputs must be explicit regular files (no links or special files)")


def _read(path: Path, limit: int) -> bytes:
    _regular(path)
    with path.open("rb") as source:
        if not stat.S_ISREG(os.fstat(source.fileno()).st_mode):
            raise PreviewError("opened input must be a regular file")
        data = source.read(limit + 1)
    if len(data) > limit:
        raise es.TransportDomainError(f"input exceeds the {limit}-byte limit")
    return data


def _alternatives(data: bytes, transport: es.TransportPolicy, maximum: int) -> tuple:
    if type(maximum) is not int or maximum <= 0:
        raise PreviewError("max_alternatives must be an exact positive integer")
    payload = es.submission_from_bytes(data, transport=transport, label="alternatives")
    if type(payload) is not dict or set(payload) != {"contract", "alternatives"}:
        raise PreviewError("alternatives document fields must be exactly contract and alternatives")
    if payload["contract"] != CONTRACT or type(payload["contract"]) is not str:
        raise PreviewError("unsupported alternatives contract")
    records = payload["alternatives"]
    if type(records) is not list or not 1 <= len(records) <= maximum:
        raise PreviewError("alternative count must be between 1 and max_alternatives")
    alternatives = []
    for index, record in enumerate(records):
        if type(record) is not dict or set(record) != {"label", "tick"}:
            raise PreviewError(f"alternative {index}: fields must be exactly label and tick")
        try:
            tick = es.campaign_tick_from_payload(record["tick"], transport=transport)
        except ValueError as exc:
            raise PreviewError(f"alternative {record['label']!r}: {exc}") from exc
        alternatives.append(Alternative(record["label"], tick))
    return tuple(alternatives)


def main(argv=None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if "--enable" not in arguments and not any(flag in arguments for flag in ("-h", "--help")):
        sys.stdout.write(preview_json(PreviewReport()))
        return 0
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--enable", action="store_true")
    parser.add_argument("--path", type=Path)
    parser.add_argument("--transport", type=Path)
    parser.add_argument("--alternatives", type=Path)
    parser.add_argument("--max-alternatives", type=int)
    parser.add_argument("--format", choices=("json", "text"), default="json")
    if any(flag in arguments for flag in ("-h", "--help")):
        # Help precedes conversion of all optional values, regardless of order.
        parser.parse_args(["--help"])
    args = parser.parse_args(arguments)
    try:
        if any(value is None for value in (args.path, args.transport, args.alternatives,
                                            args.max_alternatives)):
            raise PreviewError("--enable requires --path, --transport, --alternatives and --max-alternatives")
        if args.max_alternatives <= 0:
            raise PreviewError("max_alternatives must be an exact positive integer")
        transport = es.transport_policy_from_text(_read(args.transport, 4096).decode("utf-8"))
        alternatives = _alternatives(_read(args.alternatives, transport.max_bytes), transport,
                                     args.max_alternatives)
        # The accepted loader reads once and reports the digest of those exact
        # bytes. Preflight limits this CLI to regular-file inputs; inherited
        # loader/open races are not a special-file safety guarantee.
        _regular(args.path)
        loaded = es.load_session(args.path, transport=transport)
        report = preview_orders(enabled=True, session=loaded.session, alternatives=alternatives,
                                max_alternatives=args.max_alternatives, transport=transport)
        observation = {"path": loaded.path, "file_digest": loaded.digest,
                       "generation": loaded.generation, "turn": loaded.turn,
                       "scope": "one verified read; currentness and durability are not asserted",
                       "submission_token": False}
        if args.format == "json":
            payload = report.as_payload()
            payload["cli_observation"] = observation
            output = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"
        else:
            output = preview_text(report) + "CLI observation: " + json.dumps(
                observation, sort_keys=True, separators=(",", ":")) + "\n"
        sys.stdout.write(output)
    except (ValueError, OSError) as exc:
        sys.stderr.write(json.dumps({"error": type(exc).__name__, "detail": str(exc)},
                                    sort_keys=True, separators=(",", ":")) + "\n")
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
