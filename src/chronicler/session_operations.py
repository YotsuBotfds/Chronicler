"""Deprecated path; the module lives in chronicler_lab.session_operations. Removed in PR 7."""
import sys
from chronicler_lab import session_operations as _m
sys.modules[__name__] = _m
