import pytest
from chronicler.models import (
    InfrastructureType, Infrastructure, PendingBuild, Region,
    Civilization, Leader, WorldState, Relationship,
)


class TestInfrastructureModels:
    def test_infrastructure_type_enum(self):
        assert InfrastructureType.ROADS == "roads"
        assert InfrastructureType.FORTIFICATIONS == "fortifications"
        assert InfrastructureType.IRRIGATION == "irrigation"
        assert InfrastructureType.PORTS == "ports"
        assert InfrastructureType.MINES == "mines"

    def test_infrastructure_creation(self):
        infra = Infrastructure(
            type=InfrastructureType.ROADS,
            builder_civ="Rome", built_turn=10,
        )
        assert infra.active is True
        assert infra.builder_civ == "Rome"

    def test_pending_build(self):
        pb = PendingBuild(
            type=InfrastructureType.FORTIFICATIONS,
            builder_civ="Rome", started_turn=5, turns_remaining=3,
        )
        assert pb.turns_remaining == 3

    def test_region_has_infrastructure_fields(self):
        r = Region(
            name="Test", terrain="plains", carrying_capacity=80,
            resources="fertile",
            infrastructure=[
                Infrastructure(type=InfrastructureType.ROADS,
                              builder_civ="Rome", built_turn=10),
            ],
            pending_build=PendingBuild(
                type=InfrastructureType.IRRIGATION,
                builder_civ="Rome", started_turn=15, turns_remaining=1,
            ),
        )
        assert len(r.infrastructure) == 1
        assert r.pending_build is not None
        assert r.pending_build.turns_remaining == 1

    def test_region_default_no_infrastructure(self):
        r = Region(name="T", terrain="plains", carrying_capacity=80,
                   resources="fertile")
        assert r.infrastructure == []
        assert r.pending_build is None


def _make_civ(name, treasury=100, stability=50, regions=None, trait="bold"):
    leader = Leader(name=f"L-{name}", trait=trait, reign_start=0)
    return Civilization(
        name=name, population=50, military=30, economy=40,
        culture=30, stability=stability, treasury=treasury,
        leader=leader, regions=regions or [],
    )


def _make_world(regions, civs):
    return WorldState(name="Test", seed=42, regions=regions, civilizations=civs)


class TestInfrastructureCosts:
    def test_build_costs(self):
        from chronicler.infrastructure import BUILD_SPECS
        assert BUILD_SPECS[InfrastructureType.ROADS].cost == 10
        assert BUILD_SPECS[InfrastructureType.ROADS].turns == 2
        assert BUILD_SPECS[InfrastructureType.FORTIFICATIONS].cost == 15
        assert BUILD_SPECS[InfrastructureType.FORTIFICATIONS].turns == 3
        assert BUILD_SPECS[InfrastructureType.IRRIGATION].cost == 12
        assert BUILD_SPECS[InfrastructureType.IRRIGATION].turns == 2
        assert BUILD_SPECS[InfrastructureType.PORTS].cost == 15
        assert BUILD_SPECS[InfrastructureType.PORTS].turns == 3
        assert BUILD_SPECS[InfrastructureType.MINES].cost == 10
        assert BUILD_SPECS[InfrastructureType.MINES].turns == 2


class TestValidBuildTypes:
    def test_desert_excludes_irrigation(self):
        from chronicler.infrastructure import valid_build_types
        r = Region(name="D", terrain="desert", carrying_capacity=30,
                   resources="mineral")
        types = valid_build_types(r)
        assert InfrastructureType.IRRIGATION not in types

    def test_coast_allows_ports(self):
        from chronicler.infrastructure import valid_build_types
        r = Region(name="S", terrain="coast", carrying_capacity=70,
                   resources="maritime")
        types = valid_build_types(r)
        assert InfrastructureType.PORTS in types

    def test_non_coast_excludes_ports(self):
        from chronicler.infrastructure import valid_build_types
        r = Region(name="F", terrain="plains", carrying_capacity=80,
                   resources="fertile")
        types = valid_build_types(r)
        assert InfrastructureType.PORTS not in types

    def test_no_duplicate_types(self):
        from chronicler.infrastructure import valid_build_types
        r = Region(name="F", terrain="plains", carrying_capacity=80,
                   resources="fertile",
                   infrastructure=[
                       Infrastructure(type=InfrastructureType.ROADS,
                                     builder_civ="X", built_turn=1),
                   ])
        types = valid_build_types(r)
        assert InfrastructureType.ROADS not in types

    def test_pending_build_blocks_all(self):
        from chronicler.infrastructure import valid_build_types
        r = Region(name="F", terrain="plains", carrying_capacity=80,
                   resources="fertile",
                   pending_build=PendingBuild(
                       type=InfrastructureType.ROADS,
                       builder_civ="X", started_turn=1, turns_remaining=1,
                   ))
        types = valid_build_types(r)
        assert types == []

    def test_foreign_temple_remains_buildable_for_replacement(self):
        from chronicler.infrastructure import valid_build_types

        region = Region(
            name="F", terrain="plains", carrying_capacity=80, resources="fertile",
            controller="Rome",
            infrastructure=[
                Infrastructure(
                    type=InfrastructureType.TEMPLES,
                    builder_civ="Other",
                    built_turn=1,
                    faith_id=2,
                ),
            ],
        )
        civ = _make_civ("Rome", regions=["F"])
        civ.civ_majority_faith = 1
        world = _make_world([region], [civ])

        types = valid_build_types(region, civ=civ, world=world)

        assert InfrastructureType.TEMPLES in types


class TestHandleBuild:
    def test_build_creates_pending(self):
        from chronicler.infrastructure import handle_build
        r = Region(name="A", terrain="plains", carrying_capacity=80,
                   resources="fertile", controller="Rome")
        civ = _make_civ("Rome", treasury=50, regions=["A"])
        world = _make_world([r], [civ])
        event = handle_build(civ, world)
        assert r.pending_build is not None
        assert r.pending_build.builder_civ == "Rome"
        assert civ.treasury < 50

    def test_build_deducts_cost(self):
        from chronicler.infrastructure import handle_build, BUILD_SPECS
        r = Region(name="A", terrain="plains", carrying_capacity=80,
                   resources="fertile", controller="Rome")
        civ = _make_civ("Rome", treasury=100, regions=["A"])
        world = _make_world([r], [civ])
        handle_build(civ, world)
        selected_type = r.pending_build.type
        expected_cost = BUILD_SPECS[selected_type].cost
        assert civ.treasury == 100 - expected_cost

    def test_build_aggressive_prefers_fortifications(self):
        from chronicler.infrastructure import handle_build
        r = Region(name="A", terrain="plains", carrying_capacity=80,
                   resources="fertile", controller="Rome")
        civ = _make_civ("Rome", treasury=100, regions=["A"], trait="aggressive")
        world = _make_world([r], [civ])
        handle_build(civ, world)
        assert r.pending_build.type == InfrastructureType.FORTIFICATIONS

    def test_build_no_valid_regions_returns_none(self):
        from chronicler.infrastructure import handle_build
        r = Region(name="A", terrain="plains", carrying_capacity=80,
                   resources="fertile", controller="Rome",
                   pending_build=PendingBuild(
                       type=InfrastructureType.ROADS,
                       builder_civ="Rome", started_turn=1, turns_remaining=1))
        civ = _make_civ("Rome", treasury=100, regions=["A"])
        world = _make_world([r], [civ])
        event = handle_build(civ, world)
        assert event is None

    def test_build_uses_temple_tuning_overrides(self):
        from chronicler.infrastructure import handle_build
        from chronicler.tuning import K_TEMPLE_BUILD_COST, K_TEMPLE_BUILD_TURNS

        region = Region(
            name="A", terrain="coast", carrying_capacity=80, resources="fertile", controller="Rome",
            infrastructure=[
                Infrastructure(type=InfrastructureType.ROADS, builder_civ="Rome", built_turn=1),
                Infrastructure(type=InfrastructureType.FORTIFICATIONS, builder_civ="Rome", built_turn=1),
                Infrastructure(type=InfrastructureType.IRRIGATION, builder_civ="Rome", built_turn=1),
                Infrastructure(type=InfrastructureType.PORTS, builder_civ="Rome", built_turn=1),
                Infrastructure(type=InfrastructureType.MINES, builder_civ="Rome", built_turn=1),
            ],
        )
        civ = _make_civ("Rome", treasury=50, regions=["A"])
        civ.civ_majority_faith = 1
        world = _make_world([region], [civ])
        world.tuning_overrides[K_TEMPLE_BUILD_COST] = 7
        world.tuning_overrides[K_TEMPLE_BUILD_TURNS] = 5

        handle_build(civ, world)

        assert region.pending_build.type == InfrastructureType.TEMPLES
        assert region.pending_build.turns_remaining == 5
        assert civ.treasury == 43

    def test_build_replaces_foreign_temple(self):
        from chronicler.infrastructure import handle_build

        region = Region(
            name="A", terrain="coast", carrying_capacity=80, resources="fertile", controller="Rome",
            infrastructure=[
                Infrastructure(type=InfrastructureType.ROADS, builder_civ="Rome", built_turn=1),
                Infrastructure(type=InfrastructureType.FORTIFICATIONS, builder_civ="Rome", built_turn=1),
                Infrastructure(type=InfrastructureType.IRRIGATION, builder_civ="Rome", built_turn=1),
                Infrastructure(type=InfrastructureType.PORTS, builder_civ="Rome", built_turn=1),
                Infrastructure(type=InfrastructureType.MINES, builder_civ="Rome", built_turn=1),
                Infrastructure(type=InfrastructureType.TEMPLES, builder_civ="Other", built_turn=1, faith_id=2),
            ],
        )
        civ = _make_civ("Rome", treasury=50, regions=["A"])
        civ.civ_majority_faith = 1
        world = _make_world([region], [civ])

        handle_build(civ, world)

        assert region.pending_build.type == InfrastructureType.TEMPLES
        assert region.infrastructure[-1].active is False


class TestTickInfrastructure:
    def test_pending_build_advances(self):
        from chronicler.infrastructure import tick_infrastructure
        r = Region(name="A", terrain="plains", carrying_capacity=80,
                   resources="fertile",
                   pending_build=PendingBuild(
                       type=InfrastructureType.ROADS,
                       builder_civ="Rome", started_turn=1, turns_remaining=2,
                   ))
        world = _make_world([r], [])
        tick_infrastructure(world)
        assert r.pending_build.turns_remaining == 1

    def test_pending_build_completes(self):
        from chronicler.infrastructure import tick_infrastructure
        r = Region(name="A", terrain="plains", carrying_capacity=80,
                   resources="fertile",
                   pending_build=PendingBuild(
                       type=InfrastructureType.ROADS,
                       builder_civ="Rome", started_turn=1, turns_remaining=1,
                   ))
        world = _make_world([r], [])
        events = tick_infrastructure(world)
        assert r.pending_build is None
        assert len(r.infrastructure) == 1
        assert r.infrastructure[0].type == InfrastructureType.ROADS
        assert len(events) == 1
        assert events[0].event_type == "infrastructure_completed"

    # Mine soil degradation tests moved to test_ecology.py (TestTickSoil)


class TestScorchedEarth:
    def test_low_stability_scorches(self):
        from chronicler.infrastructure import scorched_earth_check
        civ = _make_civ("Rome", stability=10)
        r = Region(name="A", terrain="plains", carrying_capacity=80,
                   resources="fertile",
                   infrastructure=[
                       Infrastructure(type=InfrastructureType.ROADS,
                                     builder_civ="Rome", built_turn=1),
                       Infrastructure(type=InfrastructureType.IRRIGATION,
                                     builder_civ="Rome", built_turn=5),
                   ])
        world = _make_world([r], [civ])
        events = scorched_earth_check(world, civ, r, seed=42)
        assert all(not i.active for i in r.infrastructure)
        assert len(events) == 1

    def test_high_stability_no_scorch(self):
        from chronicler.infrastructure import scorched_earth_check
        civ = _make_civ("Rome", stability=100)
        r = Region(name="A", terrain="plains", carrying_capacity=80,
                   resources="fertile",
                   infrastructure=[
                       Infrastructure(type=InfrastructureType.ROADS,
                                     builder_civ="Rome", built_turn=1),
                   ])
        world = _make_world([r], [civ])
        events = scorched_earth_check(world, civ, r, seed=42)
        assert all(i.active for i in r.infrastructure)
        assert len(events) == 0

    def test_no_infrastructure_no_event(self):
        from chronicler.infrastructure import scorched_earth_check
        civ = _make_civ("Rome", stability=1)
        r = Region(name="A", terrain="plains", carrying_capacity=80,
                   resources="fertile")
        world = _make_world([r], [civ])
        events = scorched_earth_check(world, civ, r, seed=42)
        assert len(events) == 0

    def test_scorched_earth_clears_pending_build(self):
        from chronicler.infrastructure import scorched_earth_check

        civ = _make_civ("Rome", stability=10)
        r = Region(
            name="A", terrain="plains", carrying_capacity=80, resources="fertile",
            infrastructure=[
                Infrastructure(type=InfrastructureType.ROADS, builder_civ="Rome", built_turn=1),
            ],
            pending_build=PendingBuild(
                type=InfrastructureType.MINES,
                builder_civ="Rome",
                started_turn=1,
                turns_remaining=2,
            ),
        )
        world = _make_world([r], [civ])

        events = scorched_earth_check(world, civ, r, seed=42)

        assert len(events) == 1
        assert r.pending_build is None
