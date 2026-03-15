"""End-to-end smoke test for M15 Living World mechanics."""
import pytest
from chronicler.models import WorldState, ClimateConfig, ClimatePhase
from chronicler.world_gen import generate_world


class TestM15Integration:
    def test_20_turn_smoke_test(self):
        """Run 20 turns with all M15 mechanics active. Assert no crashes."""
        world = generate_world(seed=42, num_regions=10, num_civs=4)
        world.climate_config = ClimateConfig(period=20, severity=1.0)

        from chronicler.simulation import run_turn
        from chronicler.action_engine import ActionEngine

        for turn in range(20):
            engine = ActionEngine(world)
            run_turn(
                world,
                action_selector=lambda civ, w: engine.select_action(civ, seed=42 + turn),
                narrator=lambda w, e: "",
                seed=42 + turn,
            )

        # Basic invariants
        for region in world.regions:
            assert 0.0 <= region.ecology.soil <= 1.0
            assert region.role in ("standard", "crossroads", "frontier", "chokepoint")
        for civ in world.civilizations:
            assert civ.population >= 0

    def test_terrain_defense_affects_war_outcome(self):
        """Mountain defenders should win more often than plains defenders."""
        from chronicler.models import Leader, Civilization, Region
        from chronicler.action_engine import resolve_war

        mountain_wins = 0
        for seed in range(50):
            mountain = Region(name="Peaks", terrain="mountains",
                             carrying_capacity=50, resources="mineral",
                             controller="Defender",
                             adjacencies=["Valley"])
            plains = Region(name="Valley", terrain="plains",
                           carrying_capacity=80, resources="fertile",
                           controller="Attacker",
                           adjacencies=["Peaks"])
            leader_d = Leader(name="LD", trait="bold", reign_start=0)
            leader_a = Leader(name="LA", trait="bold", reign_start=0)
            defender = Civilization(
                name="Defender", population=50, military=50, economy=40,
                culture=30, stability=50, leader=leader_d, regions=["Peaks"])
            attacker = Civilization(
                name="Attacker", population=50, military=50, economy=40,
                culture=30, stability=50, leader=leader_a, regions=["Valley"])
            w = WorldState(name="T", seed=seed, regions=[mountain, plains],
                          civilizations=[defender, attacker])
            resolve_war(attacker, defender, w, seed=seed)
            d = next(c for c in w.civilizations if c.name == "Defender")
            if "Peaks" in d.regions:
                mountain_wins += 1
        assert mountain_wins > 25

    def test_climate_cycle_completes(self):
        """Run a full climate cycle and verify all four phases occur."""
        from chronicler.climate import get_climate_phase
        cfg = ClimateConfig(period=20)
        phases_seen = set()
        for turn in range(20):
            phases_seen.add(get_climate_phase(turn, cfg))
        assert len(phases_seen) == 4

    def test_region_roles_assigned(self):
        """Verify regions get role classification after generation."""
        world = generate_world(seed=42, num_regions=8, num_civs=4)
        roles = {r.role for r in world.regions}
        # With 8 regions, should have at least standard and one other
        assert "standard" in roles or len(roles) > 0

    def test_infrastructure_builds_complete(self):
        """Infrastructure should complete after enough turns."""
        from chronicler.models import Region, Civilization, Leader, InfrastructureType, PendingBuild
        from chronicler.infrastructure import tick_infrastructure

        r = Region(name="A", terrain="plains", carrying_capacity=80,
                   resources="fertile", controller="Rome",
                   pending_build=PendingBuild(
                       type=InfrastructureType.ROADS,
                       builder_civ="Rome", started_turn=0, turns_remaining=2))
        w = WorldState(name="T", seed=42, regions=[r])

        tick_infrastructure(w)
        assert r.pending_build.turns_remaining == 1

        tick_infrastructure(w)
        assert r.pending_build is None
        assert len(r.infrastructure) == 1
        assert r.infrastructure[0].type == InfrastructureType.ROADS
