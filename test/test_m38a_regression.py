"""M38a Tier 2 regression: Decision 9 baseline.
Verifies 3→4 faction renormalization preserves relative proportions."""
import pytest
from chronicler.models import FactionType, FactionState
from chronicler.factions import normalize_influence, FACTION_FLOOR


def test_decision9_faction_ratios_preserved():
    """With clergy at floor and no events, 3-faction ratios within ±2%."""
    baseline = {FactionType.MILITARY: 0.40, FactionType.MERCHANT: 0.35, FactionType.CULTURAL: 0.25}
    baseline_total = sum(baseline.values())
    baseline_ratios = {ft: v / baseline_total for ft, v in baseline.items()}

    fs = FactionState()
    fs.influence = {
        FactionType.MILITARY: 0.40,
        FactionType.MERCHANT: 0.35,
        FactionType.CULTURAL: 0.25,
        FactionType.CLERGY: FACTION_FLOOR,
    }
    normalize_influence(fs)

    non_clergy_total = sum(v for ft, v in fs.influence.items() if ft != FactionType.CLERGY)
    for ft in [FactionType.MILITARY, FactionType.MERCHANT, FactionType.CULTURAL]:
        actual_ratio = fs.influence[ft] / non_clergy_total
        expected_ratio = baseline_ratios[ft]
        assert abs(actual_ratio - expected_ratio) < 0.02, \
            f"{ft}: ratio {actual_ratio:.3f} vs baseline {expected_ratio:.3f} exceeds ±2%"


def test_decision9_clergy_at_floor():
    """Clergy at floor (0.08) stays at floor after normalization."""
    fs = FactionState()
    fs.influence = {
        FactionType.MILITARY: 0.40,
        FactionType.MERCHANT: 0.35,
        FactionType.CULTURAL: 0.25,
        FactionType.CLERGY: FACTION_FLOOR,
    }
    normalize_influence(fs)
    assert abs(fs.influence[FactionType.CLERGY] - FACTION_FLOOR) < 0.01
