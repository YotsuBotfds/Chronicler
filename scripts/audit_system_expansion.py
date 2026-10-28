#!/usr/bin/env python3
"""Audit an existing run without changing it; see docs/integration/expansion-audit.md."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from chronicler.expansion_audit import main


if __name__ == "__main__":
    sys.exit(main())
