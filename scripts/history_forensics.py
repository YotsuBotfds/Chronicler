#!/usr/bin/env python3
"""Inspect an existing bundle; see docs/integration/history-forensics.md."""
from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from chronicler.history_forensics import main


if __name__ == "__main__":
    sys.exit(main())
