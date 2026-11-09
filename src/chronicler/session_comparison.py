"""Deprecated path; the module lives in chronicler_lab.session_comparison. Removed in PR 7."""
import sys
from chronicler_lab import session_comparison as _m
sys.modules[__name__] = _m
