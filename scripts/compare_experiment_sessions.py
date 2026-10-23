"""Default-off comparison of two publicly verified saved experiment histories."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from chronicler import experiment_sessions as es
from chronicler.session_comparison import (
    compare_sessions, comparison_json, comparison_text,
)


class InputParser(argparse.ArgumentParser):
    def error(self, message):
        raise es.SessionError(message)


def main(argv=None) -> int:
    raw = list(sys.argv[1:] if argv is None else argv)
    parser = InputParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--enable", action="store_true")
    for name in ("left", "right", "transport"):
        parser.add_argument("--" + name)
    parser.add_argument("--format", choices=("json", "text"), default="json")
    if "--help" in raw or "-h" in raw:
        parser.parse_args(["--help"])
    try:
        if "--enable" not in raw:
            output = comparison_json(compare_sessions())
        else:
            args = parser.parse_args(raw)
            if any(value is None for value in (args.left, args.right, args.transport)):
                raise es.SessionError("--enable requires --left, --right and --transport")
            transport = es.transport_policy_from_text(es.read_regular_file_bytes(
                args.transport, max_bytes=4096, label="transport policy").decode("utf-8"))
            report = compare_sessions(args.left, args.right, enabled=True, transport=transport)
            output = comparison_json(report) if args.format == "json" else comparison_text(report)
    except (ValueError, OSError, TypeError) as exc:
        error = json.dumps({"error": type(exc).__name__, "detail": str(exc)},
                           sort_keys=True, separators=(",", ":")) + "\n"
        sys.stderr.write(error)
        return 3
    sys.stdout.write(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
