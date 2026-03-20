"""M49 Needs System integration tests."""
import pytest
from chronicler.narrative import render_needs, NEED_DESCRIPTIONS


class TestNeedsRendering:
    def test_all_satisfied(self):
        needs = {"safety": 0.5, "material": 0.6, "social": 0.4,
                 "spiritual": 0.5, "autonomy": 0.5, "purpose": 0.5}
        lines = render_needs(needs)
        assert len(lines) == 1  # just the summary, no LOW descriptions
        assert "LOW" not in lines[0]

    def test_one_low(self):
        needs = {"safety": 0.1, "material": 0.6, "social": 0.4,
                 "spiritual": 0.5, "autonomy": 0.5, "purpose": 0.5}
        lines = render_needs(needs)
        assert "Safety LOW (0.10)" in lines[0]
        assert "feels unsafe" in lines[1]

    def test_multiple_low(self):
        needs = {"safety": 0.1, "material": 0.6, "social": 0.1,
                 "spiritual": 0.5, "autonomy": 0.0, "purpose": 0.5}
        lines = render_needs(needs)
        assert "Safety LOW" in lines[0]
        assert "Social LOW" in lines[0]
        assert "Autonomy LOW" in lines[0]
        assert len(lines) == 4  # summary + 3 descriptions

    def test_empty_needs(self):
        assert render_needs({}) == []
        assert render_needs(None) == []

    def test_need_descriptions_complete(self):
        for name in ["safety", "material", "social", "spiritual", "autonomy", "purpose"]:
            assert name in NEED_DESCRIPTIONS

    def test_threshold_boundary(self):
        """Need at exactly threshold should be satisfied, not LOW."""
        needs = {"safety": 0.3, "material": 0.3, "social": 0.25,
                 "spiritual": 0.3, "autonomy": 0.3, "purpose": 0.35}
        lines = render_needs(needs)
        assert "LOW" not in lines[0]
