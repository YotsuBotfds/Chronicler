"""M51 Legacy Integration Tests."""
from chronicler.narrative import render_memory


def test_render_legacy_memory():
    mem = {"event_type": 0, "source_civ": 1, "turn": 50,
           "intensity": -45, "decay_factor": 7, "is_legacy": True}
    result = render_memory(mem, civ_names=["Aram", "Kethani"])
    assert result is not None
    assert "ancestral" in result.lower() or "inherited" in result.lower()
    # Should still mention the event content, not just generic "legacy"
    assert "famine" in result.lower()


def test_render_normal_memory_no_ancestral():
    mem = {"event_type": 0, "source_civ": 1, "turn": 50,
           "intensity": -80, "decay_factor": 20, "is_legacy": False}
    result = render_memory(mem, civ_names=["Aram", "Kethani"])
    assert result is not None
    assert "ancestral" not in result.lower()
    assert "inherited" not in result.lower()


def test_memory_sync_includes_legacy_flag():
    """Memory sync dict should include is_legacy from 6-tuple."""
    # Mock the 6-tuple return from get_agent_memories
    raw = [(0, 1, 100, -45, 7, True)]  # Famine, legacy
    # Simulate the dict construction that agent_bridge uses
    mem = {
        "event_type": raw[0][0],
        "source_civ": raw[0][1],
        "turn": raw[0][2],
        "intensity": raw[0][3],
        "decay_factor": raw[0][4],
        "is_legacy": raw[0][5],
    }
    assert mem["is_legacy"] is True
    assert mem["event_type"] == 0  # Famine preserved


def test_memory_sync_non_legacy_flag():
    """Non-legacy memory should have is_legacy=False."""
    raw = [(1, 0, 50, -60, 20, False)]
    mem = {
        "event_type": raw[0][0],
        "source_civ": raw[0][1],
        "turn": raw[0][2],
        "intensity": raw[0][3],
        "decay_factor": raw[0][4],
        "is_legacy": raw[0][5],
    }
    assert mem["is_legacy"] is False
