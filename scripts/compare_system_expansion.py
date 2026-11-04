#!/usr/bin/env python3
"""Compare recorded expansion studies without running simulation."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from chronicler.expansion_compare import main
if __name__ == "__main__":
    sys.exit(main())
