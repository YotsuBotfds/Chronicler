"""Deprecated path; the module lives in chronicler_lab.artifact_budget. Removed in PR 7."""
import sys
from chronicler_lab import artifact_budget as _m
sys.modules[__name__] = _m
