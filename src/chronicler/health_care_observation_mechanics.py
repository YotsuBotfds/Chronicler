"""Deprecated path; the module lives in chronicler_lab.health_care_observation_mechanics. Removed in PR 7."""
import sys
from chronicler_lab import health_care_observation_mechanics as _m
sys.modules[__name__] = _m
