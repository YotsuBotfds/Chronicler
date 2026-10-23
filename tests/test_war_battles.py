"""M60b battles and sieges: power model, determinism, casualties, retreat, sieges."""
from __future__ import annotations

import pytest

from chronicler.models import GreatPerson, Infrastructure, InfrastructureType, TechEra
from chronicler.war import params as P
from chronicler.war.battles import (
    Side, defense_multiplier, fight, garrison_size, quality, siege_required, siege_turn,
)
from chronicler.war.common import build_context
from war_fixtures import place_army, start_war, war_world


def test_quality_rises_with_era_morale_supply_and_command():
    world = war_world()
    civ = world.civ_map["A"]
    base = quality(civ, 600)
    assert quality(civ, 900) > base > quality(civ, 300)
    assert quality(civ, 600, fed=False) < base
    assert quality(civ, 600, general_trait="bold", attacking=True) > quality(civ, 600, general_trait="cautious", attacking=True) > base
    civ.tech_era = TechEra.MEDIEVAL
    assert quality(civ, 600) > base
    civ.traditions.append("martial")
    assert quality(civ, 600) > quality(civ.model_copy(update={"traditions": []}), 600)


def test_defense_multiplier_terrain_river_fortification_home():
    world = war_world()
    plains, mountains = world.region_map["Dun"], world.region_map["Crag"]
    assert defense_multiplier(world, mountains, "B") > defense_multiplier(world, plains, "B")
    assert defense_multiplier(world, plains, "B") > defense_multiplier(world, plains, "A")  # home ground
    base = defense_multiplier(world, plains, "B")
    plains.river_mask = 1
    assert defense_multiplier(world, plains, "B") == pytest.approx(base + P.RIVER_DEFENSE)
    plains.infrastructure.append(Infrastructure(type=InfrastructureType.FORTIFICATIONS, builder_civ="B",
                                                built_turn=0, active=True))
    forted = defense_multiplier(world, plains, "B")
    assert forted > base + P.RIVER_DEFENSE
    world.civ_map["B"].tech_era = TechEra.MEDIEVAL  # era doubles fortifications
    assert defense_multiplier(world, plains, "B") > forted
    assert defense_multiplier(world, plains, "B", fort_weight=0.5) < defense_multiplier(world, plains, "B")


def _duel(seed: int, a_soldiers: int, b_soldiers: int, region: str = "Brook"):
    world = war_world(seed=seed)
    ctx, war = start_war(world)
    a = place_army(world, "A", region, a_soldiers, war.war_key)
    b = place_army(world, "B", region, b_soldiers, war.war_key)
    winner = fight(ctx, war, world.region_map[region], Side(world.civ_map["B"], [b]),
                   Side(world.civ_map["A"], [a]), kind="field")
    return world, ctx, war, a, b, winner


def test_battle_is_deterministic_for_same_seed_and_state():
    w1, _, _, a1, b1, win1 = _duel(11, 30, 30)
    w2, _, _, a2, b2, win2 = _duel(11, 30, 30)
    assert win1 == win2
    assert w1.war_state.battles == w2.war_state.battles
    assert (a1.soldiers, b1.soldiers, a1.region, b1.region) == (a2.soldiers, b2.soldiers, a2.region, b2.region)
    outcomes = {(_duel(s, 30, 30)[5]) for s in range(30)}
    assert len(outcomes) > 1  # the seeded noise genuinely matters near parity


def test_overwhelming_force_wins_and_loser_retreats_or_breaks():
    world, ctx, war, a, b, winner = _duel(3, 10, 60)  # B (60) attacks A (10) in Brook
    assert winner == "B"
    record = world.war_state.battles[-1]
    assert record.winner == "B" and record.kind == "field" and record.region == "Brook"
    assert record.defender_losses > 0
    assert record.defender_losses / 10 > record.attacker_losses / 60
    assert a not in world.war_state.armies or a.region != "Brook"
    assert war.battles == 1 and war.battle_points < 0  # defender-side (B) victory
    event = [e for e in ctx.events if e.event_type == "war"][-1]
    assert event.actors == ["B", "A"] and "attacker_wins" in event.description
    assert any(ne.event_type == "battle" for ne in world.named_events)
    assert world.civ_map["A"].war_weariness > 0 and world.civ_map["B"].war_weariness > 0
    assert ctx.military_loss.get("A", 0) > 0


def test_casualties_conserve_population_accounting():
    world, ctx, war, a, b, winner = _duel(5, 40, 40)
    record = world.war_state.battles[-1]
    assert a.casualties + b.casualties == record.attacker_losses + record.defender_losses
    pop = sum(r.population for r in world.regions)
    assert pop == 2 * 60 + 3 * 40 - record.attacker_losses - record.defender_losses


def test_general_command_shifts_outcomes():
    wins_with, wins_without = 0, 0
    for seed in range(40):
        for with_general in (True, False):
            world = war_world(seed=seed)
            ctx, war = start_war(world)
            if with_general:
                world.civ_map["A"].great_persons.append(GreatPerson(
                    name="Varro", role="general", trait="bold", civilization="A",
                    origin_civilization="A", born_turn=0))
            a = place_army(world, "A", "Crag", 30, war.war_key, general="Varro" if with_general else None)
            b = place_army(world, "B", "Crag", 30, war.war_key)
            winner = fight(ctx, war, world.region_map["Crag"], Side(world.civ_map["A"], [a]),
                           Side(world.civ_map["B"], [b]), kind="field")
            if winner == "A":
                if with_general:
                    wins_with += 1
                else:
                    wins_without += 1
    assert wins_with > wins_without


def test_garrison_and_siege_requirements():
    world = war_world()
    dun, edge = world.region_map["Dun"], world.region_map["Edge"]
    owner = world.civ_map["B"]
    assert garrison_size(world, edge, owner) >= P.MIN_GARRISON
    plain = siege_required(world, edge, owner, 1.0)
    capital = siege_required(world, dun, owner, 1.0)
    assert capital == plain + 1
    dun.infrastructure.append(Infrastructure(type=InfrastructureType.FORTIFICATIONS, builder_civ="B",
                                             built_turn=0, active=True))
    assert siege_required(world, dun, owner, 1.0) >= capital + 2
    assert siege_required(world, dun, owner, 3.0) == siege_required(world, dun, owner, 1.0) - 1


def test_siege_starves_city_then_assault_takes_it():
    world = war_world()
    ctx, war = start_war(world)
    army = place_army(world, "A", "Dun", 60, war.war_key)
    dun = world.region_map["Dun"]
    pop0 = dun.population
    fell = False
    for turn in range(10):
        world.turn = turn
        if siege_turn(ctx, war, dun, [army], world.civ_map["A"], world.civ_map["B"]):
            fell = True
            break
    assert fell
    assert army.phase == "sieging"
    assert dun.population < pop0
    assert any(e.event_type == "siege_begun" for e in ctx.events)
    assert any(b.kind == "assault" and b.winner == "A" for b in world.war_state.battles)
    assert war.battle_points > 0


def test_destroyed_army_disbands_and_yields_hostage():
    world, ctx, war, a, b, winner = _duel(2, 3, 80)
    assert a not in world.war_state.armies
    assert any(e.event_type == "army_destroyed" for e in ctx.events)
    assert any(gp.is_hostage for gp in world.civ_map["B"].great_persons)
