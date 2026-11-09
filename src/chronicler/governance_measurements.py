"""Deprecated path; the module lives in chronicler_lab.governance_measurements. Removed in PR 7."""
import sys
from chronicler_lab import governance_measurements as _m
sys.modules[__name__] = _m
