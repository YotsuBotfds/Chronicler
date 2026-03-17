"""Tests for the tuning override system."""
import warnings
from pathlib import Path

import pytest

from chronicler.tuning import _flatten, load_tuning, get_override, K_DROUGHT_STABILITY


def test_flatten_simple():
    result = _flatten({"stability": {"drain": {"drought": -10}}})
    assert result == {"stability.drain.drought": -10}


def test_flatten_mixed_depths():
    result = _flatten({"a": 1, "b": {"c": 2, "d": {"e": 3}}})
    assert result == {"a": 1, "b.c": 2, "b.d.e": 3}


def test_flatten_rejects_non_numeric_leaf():
    with pytest.raises(ValueError, match="non-numeric"):
        _flatten({"a": "string_value"})


def test_load_tuning_warns_on_unknown_keys(tmp_path):
    yaml_file = tmp_path / "tuning.yaml"
    yaml_file.write_text("bogus_key_xyz: 99\n")
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        result = load_tuning(yaml_file)
        assert any("Unknown tuning key" in str(warning.message) for warning in w)
    assert result == {"bogus_key_xyz": 99}


def test_load_tuning_accepts_known_keys(tmp_path):
    yaml_file = tmp_path / "tuning.yaml"
    yaml_file.write_text("stability:\n  drain:\n    drought_immediate: -5\n")
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        result = load_tuning(yaml_file)
        unknown_warnings = [x for x in w if "Unknown tuning key" in str(x.message)]
        assert len(unknown_warnings) == 0
    assert result[K_DROUGHT_STABILITY] == -5


def test_get_override_returns_override(make_world):
    world = make_world(num_civs=2)
    world.tuning_overrides = {"some.key": 42.0}
    assert get_override(world, "some.key", 10.0) == 42.0


def test_get_override_returns_default(make_world):
    world = make_world(num_civs=2)
    assert get_override(world, "nonexistent.key", 10.0) == 10.0


def test_m35b_disease_constants_registered():
    from chronicler.tuning import KNOWN_OVERRIDES
    assert "ecology.disease_baseline_fever" in KNOWN_OVERRIDES
    assert "ecology.disease_baseline_cholera" in KNOWN_OVERRIDES
    assert "ecology.disease_baseline_plague" in KNOWN_OVERRIDES
    assert "ecology.disease_severity_cap" in KNOWN_OVERRIDES
    assert "ecology.disease_decay_rate" in KNOWN_OVERRIDES
    assert "ecology.flare_overcrowding_threshold" in KNOWN_OVERRIDES
    assert "ecology.flare_overcrowding_spike" in KNOWN_OVERRIDES
    assert "ecology.flare_army_spike" in KNOWN_OVERRIDES
    assert "ecology.flare_water_spike" in KNOWN_OVERRIDES
    assert "ecology.flare_season_spike" in KNOWN_OVERRIDES
    assert "ecology.soil_pressure_threshold" in KNOWN_OVERRIDES
    assert "ecology.soil_pressure_streak_limit" in KNOWN_OVERRIDES
    assert "ecology.overextraction_streak_limit" in KNOWN_OVERRIDES
    assert "ecology.overextraction_yield_penalty" in KNOWN_OVERRIDES
    assert "ecology.workers_per_yield_unit" in KNOWN_OVERRIDES


def test_m35b_emergence_constants_registered():
    from chronicler.tuning import KNOWN_OVERRIDES
    assert "emergence.locust_probability" in KNOWN_OVERRIDES
    assert "emergence.flood_probability" in KNOWN_OVERRIDES
    assert "emergence.collapse_probability" in KNOWN_OVERRIDES
    assert "emergence.drought_intensification_probability" in KNOWN_OVERRIDES
    assert "emergence.collapse_mortality_spike" in KNOWN_OVERRIDES
    assert "emergence.ecological_recovery_probability" in KNOWN_OVERRIDES
    assert "emergence.ecological_recovery_fraction" in KNOWN_OVERRIDES
