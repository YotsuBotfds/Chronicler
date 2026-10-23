"""M48 deferred backlog: agent promotion writes a Promotion memory.

Rust ``get_promotions()`` queues the memory and the next ``tick()`` writes it,
stamped with the promotion turn, so the same-turn Mule roll in
``AgentBridge._process_promotions`` still reads only pre-promotion memories.
"""
import pytest

pytest.importorskip("chronicler_agents")

from chronicler.action_engine import ActionEngine  # noqa: E402
from chronicler.agent_bridge import AgentBridge, _get_agent_memory_records  # noqa: E402
from chronicler.simulation import run_turn  # noqa: E402
from chronicler.world_gen import generate_world  # noqa: E402

PROMOTION = 7


def _turn(world, bridge, i):
    engine = ActionEngine(world)
    run_turn(
        world,
        action_selector=lambda c, w, _e=engine: _e.select_action(c, seed=w.seed),
        narrator=lambda w, e: "",
        seed=world.seed + i,
        agent_bridge=bridge,
    )


def test_promoted_agent_gets_promotion_memory_on_next_tick():
    world = generate_world(seed=11, num_regions=8, num_civs=4)
    world.agent_mode = "hybrid"
    bridge = AgentBridge(world, mode="hybrid")

    seen: set[int] = set()
    for i in range(40):
        _turn(world, bridge, i)
        promotion_turn = world.turn - 1
        new_ids = sorted(set(bridge.gp_by_agent_id) - seen)
        seen.update(new_ids)
        if not new_ids:
            continue
        # Same turn: the promotion has been processed but not yet written.
        for agent_id in new_ids:
            assert all(m.event_type != PROMOTION
                       for m in _get_agent_memory_records(bridge._sim, agent_id))
        _turn(world, bridge, i + 1)
        survivors = [a for a in new_ids if _get_agent_memory_records(bridge._sim, a)]
        if not survivors:
            seen.update(bridge.gp_by_agent_id)
            continue
        for agent_id in survivors:
            promo = [m for m in _get_agent_memory_records(bridge._sim, agent_id)
                     if m.event_type == PROMOTION]
            assert len(promo) == 1, agent_id
            assert promo[0].turn == promotion_turn
            assert promo[0].intensity > 0
        return
    pytest.fail("no agent promotion observed within 40 hybrid turns")
