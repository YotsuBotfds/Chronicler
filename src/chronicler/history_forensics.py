"""Deprecated path; the module lives in chronicler_lab.history_forensics. Removed in PR 7."""
import sys
from chronicler_lab import history_forensics as _m
if __name__ == "__main__":
    raise SystemExit(_m.main())
sys.modules[__name__] = _m
