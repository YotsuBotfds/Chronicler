"""Tests for the tuning override system."""
import warnings
from collections import UserDict
from pathlib import Path
from types import SimpleNamespace

import pytest

from chronicler.tuning import (
    _flatten, load_tuning, get_override, get_multiplier, K_DROUGHT_STABILITY,
)


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


def test_tuning_lookups_follow_plain_dict_mutations(make_world):
    world = make_world(num_civs=2)
    key = "multiplier.test"
    assert get_override(world, key, 10.0) == 10.0
    assert get_multiplier(world, key) == 1.0

    world.tuning_overrides[key] = 2.5
    assert get_override(world, key, 10.0) == 2.5
    assert get_multiplier(world, key) == 2.5

    world.tuning_overrides[key] = 3.5
    assert get_override(world, key, 10.0) == 3.5
    assert get_multiplier(world, key) == 3.5


def test_tuning_lookups_keep_dict_subclass_get_dispatch():
    calls = []

    class CustomDict(dict):
        def get(self, key, default=None):
            calls.append((key, default))
            return 7.5

    world = SimpleNamespace(tuning_overrides=CustomDict())
    assert get_override(world, "key", 10.0) == 7.5
    assert get_multiplier(world, "key") == 7.5
    assert calls == [("key", 10.0), ("key", 1.0)]


def test_tuning_lookups_keep_custom_mapping_and_nonmapping_fallback():
    calls = []

    class CustomMapping(UserDict):
        def get(self, key, default=None):
            calls.append((key, default))
            return super().get(key, default)

    world = SimpleNamespace(tuning_overrides=CustomMapping({"key": 4.5}))
    assert get_override(world, "key", 10.0) == 4.5
    assert get_multiplier(world, "key") == 4.5
    assert calls == [("key", 10.0), ("key", 1.0)]

    class GetOnly:
        def get(self, *_args):
            raise AssertionError("nonmapping get should not be called")

    world.tuning_overrides = GetOnly()
    assert get_override(world, "key", 10.0) == 10.0
    assert get_multiplier(world, "key") == 1.0


def test_tuning_lookups_read_dynamic_overrides_on_each_call():
    class DynamicWorld:
        def __init__(self):
            self.values = iter(({"key": 2.0}, {"key": 3.0}))

        @property
        def tuning_overrides(self):
            return next(self.values)

    world = DynamicWorld()
    assert get_override(world, "key", 10.0) == 2.0
    assert get_multiplier(world, "key") == 3.0


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


# --- M47: Multiplier validation ---

def test_load_tuning_rejects_zero_multiplier(tmp_path):
    p = tmp_path / "bad.yaml"
    p.write_text("multiplier:\n  severity: 0.0\n")
    with pytest.raises(ValueError, match="must be > 0"):
        load_tuning(p)


def test_load_tuning_rejects_negative_multiplier(tmp_path):
    p = tmp_path / "bad.yaml"
    p.write_text("multiplier:\n  aggression_bias: -1.0\n")
    with pytest.raises(ValueError, match="must be > 0"):
        load_tuning(p)


def test_load_tuning_accepts_positive_multiplier(tmp_path):
    p = tmp_path / "ok.yaml"
    p.write_text("multiplier:\n  severity: 1.5\n")
    result = load_tuning(p)
    assert result["multiplier.severity"] == 1.5


# --- M47: Consumer wiring ---

def test_severity_composition_cap():
    """Severity multiplier composed with tuning override capped at 2.0."""
    from chronicler.emergence import get_severity_multiplier
    from unittest.mock import MagicMock
    civ = MagicMock()
    civ.civ_stress = 20  # base = 1.0 + (20/20)*0.5 = 1.5
    world = MagicMock()
    world.tuning_overrides = {"multiplier.severity": 1.8}  # composed = 1.5 * 1.8 = 2.7 → cap 2.0
    assert get_severity_multiplier(civ, world) == 2.0


def test_severity_no_world_returns_base():
    """Without world param, returns uncapped base severity."""
    from chronicler.emergence import get_severity_multiplier
    from unittest.mock import MagicMock
    civ = MagicMock()
    civ.civ_stress = 20
    assert get_severity_multiplier(civ) == pytest.approx(1.5)


def test_trade_friction_scales_transport_cost():
    """friction_multiplier parameter scales compute_transport_cost output."""
    from chronicler.economy import compute_transport_cost
    cost_default = compute_transport_cost(
        "plains", "plains", is_river=False, is_coastal=False, is_winter=False,
    )
    cost_high = compute_transport_cost(
        "plains", "plains", is_river=False, is_coastal=False, is_winter=False,
        friction_multiplier=2.0,
    )
    assert cost_high == pytest.approx(cost_default * 2.0)
