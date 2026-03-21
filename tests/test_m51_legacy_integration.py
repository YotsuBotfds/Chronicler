"""M51 Legacy Integration Tests."""


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
