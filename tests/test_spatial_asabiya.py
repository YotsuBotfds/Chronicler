"""Tests for M55b spatial asabiya."""
import pytest
from chronicler.models import Region, RegionAsabiya, Civilization, CivSnapshot, Leader, TechEra


def test_region_asabiya_defaults():
    ra = RegionAsabiya()
    assert ra.asabiya == 0.5
    assert ra.frontier_fraction == 0.0
    assert ra.different_civ_count == 0
    assert ra.uncontrolled_count == 0


def test_region_has_asabiya_state():
    r = Region(name="Test", terrain="plains", carrying_capacity=60, resources="fertile")
    assert r.asabiya_state.asabiya == 0.5
    assert r.asabiya_state.frontier_fraction == 0.0


def test_civilization_has_asabiya_variance():
    civ = Civilization(
        name="Test", population=50, military=30, economy=40, culture=30,
        stability=50, tech_era=TechEra.IRON, treasury=50,
        leader=Leader(name="L", trait="cautious", reign_start=0),
    )
    assert civ.asabiya_variance == 0.0


def test_civ_snapshot_asabiya_variance_default():
    snap = CivSnapshot(
        population=50, military=30, economy=40, culture=30, stability=50,
        treasury=50, asabiya=0.5, tech_era=TechEra.IRON, trait="cautious",
        regions=["r1"], leader_name="L", alive=True,
    )
    assert snap.asabiya_variance == 0.0
