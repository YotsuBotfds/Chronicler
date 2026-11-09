"""Deprecated path; the module lives in chronicler_lab.decision_delivery. Removed in PR 7."""
import sys
from chronicler_lab import decision_delivery as _m
sys.modules[__name__] = _m
