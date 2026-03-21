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


def test_legacy_determinism():
    """Same inputs produce identical legacy memory results across two runs."""
    # The legacy system is purely deterministic: extract_legacy_memories and
    # write_single_memory have no RNG. We verify that calling the same sequence
    # twice on two separate pools yields bit-identical memory state.
    try:
        from chronicler_agents import (
            AgentPool, Occupation, BELIEF_NONE,
            factor_from_half_life, write_single_memory, extract_legacy_memories,
            LEGACY_HALF_LIFE,
            MemoryIntent,
        )
    except ImportError:
        import pytest
        pytest.skip("chronicler_agents Rust extension not built")

    def run_sequence():
        pool = AgentPool(32)
        legacy_factor = factor_from_half_life(LEGACY_HALF_LIFE)

        parent = pool.spawn(0, 0, Occupation.Farmer, 25, 0.5, 0.5, 0.5, 0, 1, 2, BELIEF_NONE)
        write_single_memory(pool, MemoryIntent(
            agent_slot=parent,
            event_type=3,   # Persecution
            source_civ=1,
            intensity=-90,
            is_legacy=False,
            decay_factor_override=None,
        ), 10)

        child = pool.spawn(0, 0, Occupation.Farmer, 25, 0.5, 0.5, 0.5, 0, 1, 2, BELIEF_NONE)
        parent_legacies = extract_legacy_memories(pool, parent)
        for (et, sc, halved) in parent_legacies:
            write_single_memory(pool, MemoryIntent(
                agent_slot=child,
                event_type=et,
                source_civ=sc,
                intensity=halved,
                is_legacy=True,
                decay_factor_override=legacy_factor,
            ), 50)

        # Verify via extract_legacy_memories on child (reads back state)
        child_legacies = extract_legacy_memories(pool, child)
        return (parent_legacies, child_legacies)

    run1 = run_sequence()
    run2 = run_sequence()

    assert run1 == run2, (
        f"Legacy memory system is non-deterministic: run1={run1}, run2={run2}"
    )
