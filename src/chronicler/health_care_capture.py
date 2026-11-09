"""Deprecated path; the module lives in chronicler_lab.health_care_capture. Removed in PR 7."""
import sys
from chronicler_lab import health_care_capture as _m
sys.modules[__name__] = _m
