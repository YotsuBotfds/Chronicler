"""Deprecated path; the module lives in chronicler_lab.memome_experiment. Removed in PR 7."""
import sys
from chronicler_lab import memome_experiment as _m
sys.modules[__name__] = _m
