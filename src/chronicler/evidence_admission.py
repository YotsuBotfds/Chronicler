"""Deprecated path; the module lives in chronicler_lab.evidence_admission. Removed in PR 7."""
import sys
from chronicler_lab import evidence_admission as _m
if __name__ == "__main__":
    raise SystemExit(_m.main())
sys.modules[__name__] = _m
