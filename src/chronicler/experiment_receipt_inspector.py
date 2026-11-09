"""Deprecated path; the module lives in chronicler_lab.experiment_receipt_inspector. Removed in PR 7."""
import sys
from chronicler_lab import experiment_receipt_inspector as _m
sys.modules[__name__] = _m
