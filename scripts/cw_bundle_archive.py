#!/usr/bin/env python3
"""Create a lossless optional gzip copy of an existing saved bundle.

No simulation, narration or source deletion. The normal JSON export remains
unchanged. Existing output files are refused rather than overwritten.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from chronicler.bundle_codec import archive_bundle


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path, help="Existing uncompressed saved JSON bundle")
    parser.add_argument("--output", required=True, type=Path, help="New gzip archive, conventionally FILE.json.gz")
    parser.add_argument("--level", type=int, choices=range(1, 10), default=1,
                        help="gzip level; 1 is the measured fast storage/transport default")
    args = parser.parse_args(argv)
    try:
        receipt = archive_bundle(args.source, args.output, compresslevel=args.level)
    except (OSError, ValueError) as exc:
        parser.exit(2, f"{parser.prog}: {exc}\n")
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
