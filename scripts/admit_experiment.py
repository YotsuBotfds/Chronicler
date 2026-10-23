#!/usr/bin/env python3
"""Repository entrypoint for the standalone experiment admission CLI."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from chronicler.evidence_admission import main

if __name__ == '__main__':
    sys.exit(main())
