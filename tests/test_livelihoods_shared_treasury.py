"""One ruler treasury, many claimants: adversarial checks across sprint lanes (offline).

Review R2 (2026-11-05), derived from the stated contracts rather than the
authors' examples:

* L9 (``docs/integration/local-budgets.md``, Limits): "L7 assisted
  relocation ... Its ceiling (``relocation_costs.ASSIST_SHARE`` of the
  treasury) is reserved as an obligation before any envelope ..., so the two
  never claim the same coins." A reservation only keeps the two apart if the
  assistance actually installed next turn stays within it.
* L7 (``docs/integration/relocation-costs.md``): assistance is charged once,
  in Phase 10, only for applied assisted moves; a failed tick charges nothing.
* The Phase 10 order is relocation charge, then the granary pass: the relief
  envelope is capped by the treasury left above the floor after the charge.

The fake native gate and wealth transfer are the L7 offline suite's
(``tests/test_relocation_costs.py``), which follow ``relocation.rs`` and
``wealth_transfer.rs``. The real-native closure checks are in
``tests/test_livelihoods_closure_native.py``.
"""
from __future__ import annotations

import math

import chronicler.grain_reserves as G
from chronicler import local_budgets as LB
from chronicler import relocation_costs as R
from chronicler.accumulator import StatAccumulator
from chronicler.finance import _projections
from chronicler.livelihoods import configure_livelihoods
from chronicler.local_budgets_state import Commitment
from chronicler.main import _build_parser
from chronicler.world_gen import generate_world
from tests.test_relocation_costs import Economy, FakeBridge, FakeSim

HOST = 1                     # civ 1 rules regions 2 and 3: the destination ruler
SHORT = 750                  # each adult holds 750 milli: a family of three is 1500 short


def _world(treasury=200, *, budgets=True):
    world = generate_world(seed=42, num_regions=4, num_civs=2)
    world.agent_mode = "hybrid"
    for i, r in enumerate(world.regions):
        r.controller = world.civilizations[0 if i < 2 else 1].name
    for civ in world.civilizations:
        civ.treasury = treasury
    G.set_grain_reserves_enabled(world, True)
    G._ensure(world)
    flags = ["--relocation-costs", "--relocation-mode", "assisted"] + (["--local-budgets"] if budgets else [])
    configure_livelihoods(world, _build_parser().parse_args(flags), agent_mode="hybrid")
    return world


def _families(n, adult=SHORT):
    """``n`` short families of three (two adults, one child), region 0 -> 2."""
    wealth, households = {}, []
    for k in range(n):
        a, b, c = 100 + 3 * k, 101 + 3 * k, 102 + 3 * k
        wealth.update({a: adult, b: adult, c: 0})
        households.append(([a, b, c], [a, b], 0, 2))
    return wealth, households


def _decide(world):
    """Phase 10 of turn T: L9 settles and decides turn T+1 (no economy this turn)."""
    LB.phase10(world, acc=None, economy_result=None, agent_bridge=None)
    return next(d for d in world.livelihoods.local_budgets.decisions if d.civ == HOST)


def _next_turn_relocation(world, households, wealth, *, acc=None):
    """Turn T+1: the gate installs the assistance budgets, the tick moves the
    families, Phase 10 charges the destination ruler."""
    world.turn += 1
    sim = FakeSim(wealth)
    bridge = FakeBridge(sim)
    R.before_agent_tick(world, bridge, Economy(world))
    installed = list(sim.policy["budgets"])
    sim.tick(households)
    R.after_agent_tick(world, bridge)
    R.phase10_before_reserves(world, acc, None, bridge)
    return installed, world.livelihoods.relocation_costs


def test_assisted_relocation_spends_only_what_the_local_budget_reserved():
    """The treasury grows between L9's decision (Phase 10 of T) and the gate
    (T+1, before the tick), e.g. from Phase 10 income still queued at the
    decision or Phase 1-9 revenue. The reservation was ASSIST_SHARE of the
    treasury at the decision; the gate must not install, and Phase 10 must not
    charge, more than that."""
    world = _world(treasury=200)
    decision = _decide(world)
    reserved = decision.obligations                      # no academies: all of it is L7's
    assert reserved == math.floor(R.ASSIST_SHARE * 200) == 10
    world.civilizations[HOST].treasury = 1000            # revenue arrives before the next gate
    wealth, households = _families(8)                    # 8 x 1500 milli of assistance wanted
    installed, state = _next_turn_relocation(world, households, wealth)
    assert installed[HOST] <= reserved * 1000, (installed[HOST], reserved)
    charged = sum(a.charged_coins for a in state.assistance if a.civ == HOST)
    assert 0 < charged <= reserved, (charged, reserved)
    assert world.civilizations[HOST].treasury == 1000 - charged


def test_without_local_budgets_the_assistance_ceiling_is_unchanged():
    world = _world(treasury=200, budgets=False)
    world.civilizations[HOST].treasury = 1000
    wealth, households = _families(8)
    installed, state = _next_turn_relocation(world, households, wealth)
    assert installed[HOST] == math.floor(R.ASSIST_SHARE * 1000) * 1000
    assert sum(a.charged_coins for a in state.assistance) == 12          # 8 x 1500 milli


def test_relocation_charge_comes_first_and_relief_takes_only_the_rest_above_the_floor():
    """Phase 10 of T+1: relocation is charged through the accumulator before
    the granary pass; the relief envelope is then capped by the projected
    treasury above the floor, so the two never overdraw the treasury together
    even when the treasury fell after the decision."""
    world = _world(treasury=100)
    decision = _decide(world)
    budget = decision.budget
    assert budget == math.floor(LB.ENVELOPE_SHARE * (100 - LB.FLOOR - decision.obligations))
    state = world.livelihoods.local_budgets
    state.open.append(Commitment(cid=state.next_cid, civ=HOST, service="relief", pid=0,
                                 decided_turn=world.turn, for_turn=world.turn + 1, recipients=[2],
                                 claims=[f"procurement:{HOST}"], amount=budget, unit="grain", expected=1.0))
    world.civilizations[HOST].treasury = 30              # Phase 1-9 spending after the decision
    acc = StatAccumulator()
    wealth, households = _families(2, adult=1000)       # each family is 1000 short
    _installed, reloc = _next_turn_relocation(world, households, wealth, acc=acc)
    charged = sum(a.charged_coins for a in reloc.assistance if a.civ == HOST)
    assert charged == 1                                  # 5% of 30: one coin of assistance
    assert world.civilizations[HOST].treasury == 30      # queued as keep, not yet applied
    projected = _projections(world, acc)
    assert projected[HOST] == 30 - charged
    cap = LB.procurement_budget(world, [0, 0], projected)[HOST]
    assert cap == min(budget, projected[HOST] - LB.FLOOR)
    assert charged + cap <= 30 - LB.FLOOR


def test_a_failed_tick_charges_no_fare_and_no_assistance_and_settlement_is_once():
    world = _world(treasury=200, budgets=False)
    wealth, households = _families(2)
    sim = FakeSim(wealth)
    bridge = FakeBridge(sim)
    R.before_agent_tick(world, bridge, Economy(world))
    # The native tick raises: no after-tick hook, so nothing is settled.
    assert R.phase10_before_reserves(world, None, None, bridge) == []
    state = world.livelihoods.relocation_costs
    assert world.civilizations[HOST].treasury == 200 and sim.wealth == wealth
    assert state.assistance == [] and not state.counters.get("assistance_charged_milli")
    assert state.last_assistance_turn is None and state.last_settled_turn is None
    # A completed turn settles its assistance exactly once.
    world.turn += 1
    sim = FakeSim(wealth)
    bridge = FakeBridge(sim)
    R.before_agent_tick(world, bridge, Economy(world))
    sim.tick(households)
    R.after_agent_tick(world, bridge)
    R.phase10_before_reserves(world, None, None, bridge)
    after = world.civilizations[HOST].treasury
    assert after == 200 - 3                              # 2 x 1500 milli
    assert R.phase10_before_reserves(world, None, None, bridge) == []
    assert world.civilizations[HOST].treasury == after
    assert state.counters["assistance_charged_milli"] == 3000
