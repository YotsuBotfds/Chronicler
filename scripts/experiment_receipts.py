"""Default-off historical receipt inspection; stdout only, no session writes."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from chronicler import experiment_sessions as es
from chronicler.experiment_receipt_inspector import (
    disabled_receipt, inspect_receipts, inspection_json, inspection_text,
)


def _transport(path: Path) -> es.TransportPolicy:
    data = es.read_regular_file_bytes(path, max_bytes=4096, label="transport policy")
    return es.transport_policy_from_text(data.decode("utf-8"))


def main(argv=None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if "--enable" not in arguments and not any(flag in arguments for flag in ("-h", "--help")):
        sys.stdout.write(json.dumps(disabled_receipt(), sort_keys=True, separators=(",", ":")) + "\n")
        return 0
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--enable", action="store_true")
    parser.add_argument("--path", type=Path)
    parser.add_argument("--transport", type=Path)
    parser.add_argument("--turn", type=int)
    parser.add_argument("--start-turn", type=int)
    parser.add_argument("--end-turn", type=int)
    parser.add_argument("--max-turns", type=int)
    parser.add_argument("--format", choices=("json", "text"), default="json")
    args = parser.parse_args(arguments)
    try:
        if args.path is None or args.transport is None:
            raise es.SessionError("--enable requires --path and --transport")
        inspection = inspect_receipts(
            args.path, enabled=True, transport=_transport(args.transport),
            turn=args.turn, start_turn=args.start_turn, end_turn=args.end_turn,
            max_turns=args.max_turns)
        sys.stdout.write(inspection_json(inspection) if args.format == "json"
                         else inspection_text(inspection))
    except (ValueError, OSError) as exc:
        sys.stderr.write(json.dumps({"error": type(exc).__name__, "detail": str(exc)},
                                    sort_keys=True, separators=(",", ":")) + "\n")
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
