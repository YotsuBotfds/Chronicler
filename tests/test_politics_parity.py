"""M54c Task 5: Politics parity and determinism safety net.

Compares Rust politics output against the Python oracle on controlled fixtures.

IMPORTANT: The Rust path uses SHA-256/splitmix64 RNG, not Python's random.Random.
Exact numeric parity for probabilistic decisions is NOT achievable through the
same seed.  Instead, parity tests verify:

1. Structural parity: Same ops for deterministic scenarios (forced outcomes)
2. Apply-layer parity: Given the same ops, apply_politics_ops produces the same
   world state changes
3. Semantic parity: For forced-outcome scenarios, both paths produce the same result
4. Determinism: Repeated Rust runs with same inputs produce identical op batches
"""
import pytest

from chronicler.models import (
    Civilization, Disposition, ExileModifier, Federation, Leader,
    ProxyWar, Region, RegionEcology, Relationship, VassalRelation,
    WorldState,
)
from chronicler.politics import (
    # Python oracle functions
    check_capital_loss,
    check_secession,
    check_vassal_rebellion,
    check_federation_formation,
    check_federation_dissolution,
    check_proxy_detection,
    check_restoration,
    check_twilight_absorption,
    update_allied_turns,
    update_decline_tracking,
    # Rust bridge
    call_rust_politics,
    apply_politics_ops,
    configure_politics_runtime,
    # Op constants
    CIV_OP_CREATE_BREAKAWAY,
    CIV_OP_REASSIGN_CAPITAL,
    CIV_OP_STRIP_TO_FIRST_REGION,
    CIV_OP_ABSORB,
    REGION_OP_NULLIFY_CONTROLLER,
    REGION_OP_SET_SECEDED_TRANSIENT,
    REL_OP_INCREMENT_ALLIED_TURNS,
    REL_OP_RESET_ALLIED_TURNS,
    FED_OP_CREATE,
    FED_OP_DISSOLVE,
    VASSAL_OP_REMOVE,
    EXILE_OP_APPEND,
    PROXY_OP_SET_DETECTED,
    BK_APPEND_STATS_HISTORY,
    BK_INCREMENT_DECLINE,
    BK_RESET_DECLINE,
    ROUTING_DIRECT_ONLY,
    ROUTING_HYBRID_SHOCK,
    BRIDGE_SECESSION,
    BRIDGE_ABSORPTION,
    REF_EXISTING,
    CIV_NONE,
    # Builders
    build_politics_region_input_batch,
)
from chronicler.utils import sync_civ_population


# ── Fixtures ─────────────────────────────────────────────────────────


def _get_simulator():
    """Get a PoliticsSimulator (off-mode, no pool)."""
    try:
        from chronicler_agents import PoliticsSimulator
        return PoliticsSimulator()
    except ImportError:
        pytest.skip("chronicler_agents not built")


def _make_leader(name="L", trait="bold"):
    return Leader(name=name, trait=trait, reign_start=0)


def _make_world(num_civs=3, num_regions=5, seed=42, turn=100):
    """Build a minimal world with civs controlling regions in a linear chain."""
    region_names = [chr(ord("A") + i) for i in range(num_regions)]
    adj_map = {}
    for i, rn in enumerate(region_names):
        adj = []
        if i > 0:
            adj.append(region_names[i - 1])
        if i < num_regions - 1:
            adj.append(region_names[i + 1])
        adj_map[rn] = adj

    regions = [
        Region(
            name=rn, terrain="plains", carrying_capacity=50,
            resources="fertile", adjacencies=adj_map.get(rn, []),
            population=20, controller=None,
        )
        for rn in region_names
    ]

    civs = []
    regions_per_civ = max(1, num_regions // num_civs)
    for ci in range(num_civs):
        start = ci * regions_per_civ
        end = min(start + regions_per_civ, num_regions)
        civ_regions = region_names[start:end]
        civ = Civilization(
            name=f"Civ{ci}",
            population=20 * len(civ_regions),
            military=30, economy=40, culture=30, stability=50,
            treasury=100, leader=_make_leader(f"L{ci}"),
            regions=civ_regions,
            capital_region=civ_regions[0] if civ_regions else None,
        )
        civs.append(civ)
        for rn in civ_regions:
            regions[region_names.index(rn)].controller = civ.name

    rels = {}
    for a in civs:
        rels[a.name] = {}
        for b in civs:
            if a.name != b.name:
                rels[a.name][b.name] = Relationship(disposition=Disposition.NEUTRAL)

    world = WorldState(
        name="test", seed=seed, turn=turn, regions=regions,
        civilizations=civs, relationships=rels,
    )
    return world


# ── Capital Loss Parity ──────────────────────────────────────────────


class TestCapitalLossParity:
    """Capital loss is a deterministic scenario (no RNG) — both paths must match."""

    def test_capital_reassignment_matches(self):
        """When capital is lost, both Python oracle and Rust produce the same
        new capital assignment (highest effective_capacity).

        Uses regions with distinct effective_capacity to avoid tie-breaking
        differences between Python (max picks first-in-list) and Rust
        (max picks last-in-list).
        """
        sim = _get_simulator()

        def _make_cap_loss_world():
            """World where B has low effective_cap and C has high."""
            regions = [
                Region(name="A", terrain="plains", carrying_capacity=50,
                       resources="fertile", adjacencies=["B"],
                       ecology=RegionEcology(soil=0.5, water=0.6),
                       population=10),
                Region(name="B", terrain="plains", carrying_capacity=30,
                       resources="fertile", adjacencies=["A", "C"],
                       ecology=RegionEcology(soil=0.3, water=0.6),
                       population=10),
                Region(name="C", terrain="plains", carrying_capacity=80,
                       resources="fertile", adjacencies=["B"],
                       ecology=RegionEcology(soil=0.9, water=0.6),
                       population=10),
            ]
            regions[1].controller = "Civ0"
            regions[2].controller = "Civ0"
            leader = _make_leader()
            civ = Civilization(
                name="Civ0", population=20, military=30, economy=40,
                culture=30, stability=50, treasury=100, leader=leader,
                regions=["B", "C"], capital_region="A",
            )
            return WorldState(name="test", seed=42, turn=100, regions=regions,
                              civilizations=[civ])

        world_py = _make_cap_loss_world()
        world_rust = _make_cap_loss_world()

        # Python oracle
        py_events = check_capital_loss(world_py)

        # Rust path
        configure_politics_runtime(sim, world_rust)
        ops = call_rust_politics(sim, world_rust, hybrid_mode=False)
        rust_events = apply_politics_ops(world_rust, ops)

        # Both should reassign capital to C (highest eff_cap)
        assert world_py.civilizations[0].capital_region == "C"
        assert world_rust.civilizations[0].capital_region == "C"

        # Both should produce a capital_loss event
        py_event_types = [e.event_type for e in py_events]
        rust_event_types = [e.event_type for e in rust_events]
        assert "capital_loss" in py_event_types
        assert "capital_loss" in rust_event_types

    def test_no_capital_loss_when_capital_present(self):
        """When capital is in regions, neither path produces any capital ops."""
        sim = _get_simulator()
        world_py = _make_world(num_civs=1, num_regions=3)
        world_rust = _make_world(num_civs=1, num_regions=3)

        py_events = check_capital_loss(world_py)

        configure_politics_runtime(sim, world_rust)
        ops = call_rust_politics(sim, world_rust, hybrid_mode=False)
        reassign_ops = [o for o in ops if o[2] == "civ_op"
                        and o[3].get("op_type") == CIV_OP_REASSIGN_CAPITAL]

        assert len(py_events) == 0
        assert len(reassign_ops) == 0

    def test_capital_loss_with_ecology(self):
        """Capital reassignment picks by effective_capacity, matching ecology."""
        sim = _get_simulator()

        def _make_eco_world():
            regions = [
                Region(name="A", terrain="plains", carrying_capacity=30,
                       resources="fertile", adjacencies=["B"],
                       ecology=RegionEcology(soil=0.3, water=0.6),
                       population=10),
                Region(name="B", terrain="plains", carrying_capacity=30,
                       resources="fertile", adjacencies=["A", "C"],
                       ecology=RegionEcology(soil=0.5, water=0.6),
                       population=10),
                Region(name="C", terrain="plains", carrying_capacity=80,
                       resources="fertile", adjacencies=["B"],
                       ecology=RegionEcology(soil=0.9, water=0.6),
                       population=10),
            ]
            leader = _make_leader()
            civ = Civilization(
                name="Civ0", population=20, military=30, economy=40,
                culture=30, stability=50, treasury=100, leader=leader,
                regions=["B", "C"], capital_region="A",
            )
            regions[1].controller = "Civ0"
            regions[2].controller = "Civ0"
            w = WorldState(name="test", seed=42, turn=100, regions=regions,
                           civilizations=[civ])
            return w

        world_py = _make_eco_world()
        world_rust = _make_eco_world()

        check_capital_loss(world_py)

        configure_politics_runtime(sim, world_rust)
        ops = call_rust_politics(sim, world_rust, hybrid_mode=False)
        apply_politics_ops(world_rust, ops)

        # C has much higher effective_capacity — both should pick C
        assert world_py.civilizations[0].capital_region == "C"
        assert world_rust.civilizations[0].capital_region == "C"


# ── Secession Parity (Structural) ───────────────────────────────────


class TestSecessionStructuralParity:
    """Secession is probabilistic (different RNG). We verify structural
    properties that must hold regardless of whether secession fires."""

    def test_secession_grace_period_blocks_both_paths(self):
        """Both paths skip secession during grace period."""
        sim = _get_simulator()
        world_py = _make_world(num_civs=1, num_regions=5)
        world_rust = _make_world(num_civs=1, num_regions=5)

        for w in [world_py, world_rust]:
            w.civilizations[0].stability = 0
            w.civilizations[0].founded_turn = 80  # turn 100 - 80 = 20 < 50 grace
            w.civilizations[0].regions = ["A", "B", "C", "D", "E"]
            for r in w.regions:
                r.controller = w.civilizations[0].name

        py_events = check_secession(world_py)

        configure_politics_runtime(sim, world_rust)
        ops = call_rust_politics(sim, world_rust, hybrid_mode=False)
        secession_ops = [o for o in ops if o[2] == "civ_op"]

        assert len(world_py.civilizations) == 1
        # No CreateBreakaway ops should appear
        # (ReassignCapital etc. may appear from other steps, but no secession)
        breakaway_ops = [o for o in secession_ops
                         if o[3].get("op_type") not in (CIV_OP_REASSIGN_CAPITAL,
                                                        CIV_OP_STRIP_TO_FIRST_REGION,
                                                        CIV_OP_ABSORB)]
        assert len(breakaway_ops) == 0

    def test_secession_blocked_with_too_few_regions(self):
        """Both paths skip secession with < 3 regions."""
        sim = _get_simulator()
        world_py = _make_world(num_civs=1, num_regions=2)
        world_rust = _make_world(num_civs=1, num_regions=2)

        for w in [world_py, world_rust]:
            w.civilizations[0].stability = 0
            w.civilizations[0].founded_turn = 0

        py_events = check_secession(world_py)

        configure_politics_runtime(sim, world_rust)
        ops = call_rust_politics(sim, world_rust, hybrid_mode=False)
        secession_events = [o for o in ops if o[2] == "event_trigger"
                            and o[3].get("event_type") == "secession"]

        assert len(world_py.civilizations) == 1
        assert len(secession_events) == 0

    def test_secession_above_threshold_blocked(self):
        """Both paths skip secession when stability >= threshold."""
        sim = _get_simulator()
        world_py = _make_world(num_civs=1, num_regions=5)
        world_rust = _make_world(num_civs=1, num_regions=5)

        for w in [world_py, world_rust]:
            w.civilizations[0].stability = 50  # well above default threshold
            w.civilizations[0].founded_turn = 0
            w.civilizations[0].regions = ["A", "B", "C", "D", "E"]
            for r in w.regions:
                r.controller = w.civilizations[0].name

        py_events = check_secession(world_py)

        configure_politics_runtime(sim, world_rust)
        ops = call_rust_politics(sim, world_rust, hybrid_mode=False)
        secession_events = [o for o in ops if o[2] == "event_trigger"
                            and o[3].get("event_type") == "secession"]

        assert len(world_py.civilizations) == 1
        assert len(secession_events) == 0


# ── Vassal Rebellion Parity (Structural) ─────────────────────────────


class TestVassalRebellionStructuralParity:
    """Vassal rebellion is probabilistic. We verify structural blocking
    conditions work the same on both paths."""

    def test_no_rebellion_when_overlord_strong(self):
        """Strong overlord prevents rebellion on both paths."""
        sim = _get_simulator()
        world_py = _make_world(num_civs=2, num_regions=4)
        world_rust = _make_world(num_civs=2, num_regions=4)

        for w in [world_py, world_rust]:
            w.civilizations[0].stability = 80  # strong overlord
            w.civilizations[0].treasury = 200
            w.vassal_relations = [VassalRelation(overlord="Civ0", vassal="Civ1")]

        py_events = check_vassal_rebellion(world_py)

        configure_politics_runtime(sim, world_rust)
        ops = call_rust_politics(sim, world_rust, hybrid_mode=False)
        rebellion_ops = [o for o in ops if o[2] == "vassal_op"
                         and o[3].get("op_type") == VASSAL_OP_REMOVE]

        assert len(py_events) == 0
        assert len(rebellion_ops) == 0
        assert len(world_py.vassal_relations) == 1


# ── Federation Parity ────────────────────────────────────────────────


class TestFederationParity:
    """Federation formation/dissolution is deterministic."""

    def test_federation_formation_fires_both_paths(self):
        """Allied civs at threshold form a federation on both paths."""
        sim = _get_simulator()
        world_py = _make_world(num_civs=2, num_regions=4)
        world_rust = _make_world(num_civs=2, num_regions=4)

        for w in [world_py, world_rust]:
            w.relationships["Civ0"]["Civ1"] = Relationship(
                disposition=Disposition.ALLIED, allied_turns=10,
            )
            w.relationships["Civ1"]["Civ0"] = Relationship(
                disposition=Disposition.ALLIED, allied_turns=10,
            )

        # Python oracle: run step 3 (update_allied_turns) then step 5
        update_allied_turns(world_py)
        py_events = check_federation_formation(world_py)

        # Rust path
        configure_politics_runtime(sim, world_rust)
        ops = call_rust_politics(sim, world_rust, hybrid_mode=False)
        fed_create_ops = [o for o in ops if o[2] == "federation_op"
                          and o[3].get("op_type") == FED_OP_CREATE]

        # Both should create a federation
        assert len(world_py.federations) == 1
        assert len(fed_create_ops) >= 1

    def test_federation_dissolution_fires_both_paths(self):
        """Hostile members trigger dissolution on both paths."""
        sim = _get_simulator()
        world_py = _make_world(num_civs=2, num_regions=4)
        world_rust = _make_world(num_civs=2, num_regions=4)

        for w in [world_py, world_rust]:
            w.federations = [
                Federation(name="The Iron Pact", members=["Civ0", "Civ1"],
                           founded_turn=50),
            ]
            w.relationships["Civ0"]["Civ1"] = Relationship(
                disposition=Disposition.HOSTILE,
            )
            w.relationships["Civ1"]["Civ0"] = Relationship(
                disposition=Disposition.HOSTILE,
            )

        # Python oracle
        py_events = check_federation_dissolution(world_py)

        # Rust path
        configure_politics_runtime(sim, world_rust)
        ops = call_rust_politics(sim, world_rust, hybrid_mode=False)
        fed_dissolve_ops = [o for o in ops if o[2] == "federation_op"
                            and o[3].get("op_type") == FED_OP_DISSOLVE]

        # Both should dissolve
        assert len(world_py.federations) == 0
        assert len(fed_dissolve_ops) >= 1

    def test_no_federation_when_not_at_threshold(self):
        """Below threshold, no federation on either path."""
        sim = _get_simulator()
        world_py = _make_world(num_civs=2, num_regions=4)
        world_rust = _make_world(num_civs=2, num_regions=4)

        for w in [world_py, world_rust]:
            w.relationships["Civ0"]["Civ1"] = Relationship(
                disposition=Disposition.ALLIED, allied_turns=3,  # below 10
            )
            w.relationships["Civ1"]["Civ0"] = Relationship(
                disposition=Disposition.ALLIED, allied_turns=3,
            )

        update_allied_turns(world_py)
        py_events = check_federation_formation(world_py)

        configure_politics_runtime(sim, world_rust)
        ops = call_rust_politics(sim, world_rust, hybrid_mode=False)
        fed_ops = [o for o in ops if o[2] == "federation_op"
                   and o[3].get("op_type") == FED_OP_CREATE]

        assert len(world_py.federations) == 0
        assert len(fed_ops) == 0


# ── Twilight Absorption Parity ───────────────────────────────────────


class TestTwilightAbsorptionParity:
    """Twilight absorption is deterministic (triggered by decline_turns threshold)."""

    def test_twilight_absorption_fires_both_paths(self):
        """Terminal decline civ is absorbed on both paths."""
        sim = _get_simulator()

        def _make_twilight_world():
            regions = [
                Region(name="A", terrain="plains", carrying_capacity=20,
                       resources="fertile", adjacencies=["B"], population=10,
                       controller="Civ0"),
                Region(name="B", terrain="plains", carrying_capacity=50,
                       resources="fertile", adjacencies=["A"], population=30,
                       controller="Civ1"),
            ]
            civ0 = Civilization(
                name="Civ0", population=10, military=5, economy=5,
                culture=5, stability=10, treasury=10,
                leader=_make_leader("L0"), regions=["A"],
                capital_region="A", decline_turns=45, founded_turn=0,
            )
            civ1 = Civilization(
                name="Civ1", population=30, military=30, economy=40,
                culture=60, stability=50, treasury=100,
                leader=_make_leader("L1"), regions=["B"],
                capital_region="B",
            )
            rels = {
                "Civ0": {"Civ1": Relationship(disposition=Disposition.NEUTRAL)},
                "Civ1": {"Civ0": Relationship(disposition=Disposition.NEUTRAL)},
            }
            return WorldState(name="test", seed=42, turn=100,
                              regions=regions, civilizations=[civ0, civ1],
                              relationships=rels)

        world_py = _make_twilight_world()
        world_rust = _make_twilight_world()

        # Python oracle (steps 1-8 are no-ops, then step 9)
        py_events = check_twilight_absorption(world_py)

        # Rust path
        configure_politics_runtime(sim, world_rust)
        ops = call_rust_politics(sim, world_rust, hybrid_mode=False)
        absorb_ops = [o for o in ops if o[2] == "civ_op"
                      and o[3].get("op_type") == CIV_OP_ABSORB]
        exile_append_ops = [o for o in ops if o[2] == "exile_op"
                            and o[3].get("op_type") == EXILE_OP_APPEND]
        absorption_events = [o for o in ops if o[2] == "event_trigger"
                             and o[3].get("event_type") == "twilight_absorption"]

        # Both should absorb
        assert len(py_events) > 0
        assert any(e.event_type == "twilight_absorption" for e in py_events)
        assert len(absorb_ops) >= 1

        # Dead civ should have regions=[] on Python path
        assert world_py.civilizations[0].regions == []

        # Rust should emit exile modifier append
        assert len(exile_append_ops) >= 1

        # Rust should emit twilight_absorption event
        assert len(absorption_events) >= 1

    def test_no_absorption_when_not_declining(self):
        """Healthy civ is not absorbed on either path."""
        sim = _get_simulator()
        world_py = _make_world(num_civs=2, num_regions=4)
        world_rust = _make_world(num_civs=2, num_regions=4)

        py_events = check_twilight_absorption(world_py)

        configure_politics_runtime(sim, world_rust)
        ops = call_rust_politics(sim, world_rust, hybrid_mode=False)
        absorb_ops = [o for o in ops if o[2] == "civ_op"
                      and o[3].get("op_type") == CIV_OP_ABSORB]

        assert len(py_events) == 0
        assert len(absorb_ops) == 0

    def test_absorber_not_reabsorbed_after_gaining_viable_capacity(self):
        """An absorber that becomes viable mid-step should not be absorbed again."""
        sim = _get_simulator()

        def _make_chain_world():
            regions = [
                Region(
                    name="A", terrain="plains", carrying_capacity=8,
                    resources="fertile", adjacencies=["B"], population=10,
                    controller="Civ0", ecology=RegionEcology(soil=1.0, water=0.5),
                ),
                Region(
                    name="B", terrain="plains", carrying_capacity=4,
                    resources="fertile", adjacencies=["A", "C"], population=10,
                    controller="Civ1", ecology=RegionEcology(soil=1.0, water=0.5),
                ),
                Region(
                    name="C", terrain="plains", carrying_capacity=50,
                    resources="fertile", adjacencies=["B"], population=30,
                    controller="Civ2", ecology=RegionEcology(soil=1.0, water=0.5),
                ),
            ]
            civ0 = Civilization(
                name="Civ0", population=10, military=5, economy=5,
                culture=5, stability=10, treasury=10,
                leader=_make_leader("L0"), regions=["A"],
                capital_region="A", founded_turn=0,
            )
            civ1 = Civilization(
                name="Civ1", population=10, military=10, economy=10,
                culture=20, stability=20, treasury=20,
                leader=_make_leader("L1"), regions=["B"],
                capital_region="B", founded_turn=0,
            )
            civ2 = Civilization(
                name="Civ2", population=30, military=30, economy=40,
                culture=60, stability=50, treasury=100,
                leader=_make_leader("L2"), regions=["C"],
                capital_region="C", founded_turn=0,
            )
            rels = {
                "Civ0": {
                    "Civ1": Relationship(disposition=Disposition.NEUTRAL),
                    "Civ2": Relationship(disposition=Disposition.NEUTRAL),
                },
                "Civ1": {
                    "Civ0": Relationship(disposition=Disposition.NEUTRAL),
                    "Civ2": Relationship(disposition=Disposition.NEUTRAL),
                },
                "Civ2": {
                    "Civ0": Relationship(disposition=Disposition.NEUTRAL),
                    "Civ1": Relationship(disposition=Disposition.NEUTRAL),
                },
            }
            world = WorldState(
                name="test", seed=42, turn=100,
                regions=regions, civilizations=[civ0, civ1, civ2],
                relationships=rels,
            )
            return world

        world_py = _make_chain_world()
        world_rust = _make_chain_world()

        py_events = check_twilight_absorption(world_py)

        configure_politics_runtime(sim, world_rust)
        ops = call_rust_politics(sim, world_rust, hybrid_mode=False)
        rust_events = apply_politics_ops(world_rust, ops)

        py_absorptions = [e for e in py_events if e.event_type == "twilight_absorption"]
        rust_absorptions = [e for e in rust_events if e.event_type == "twilight_absorption"]

        assert len(py_absorptions) == 1
        assert len(rust_absorptions) == 1
        assert py_absorptions[0].actors == ["Civ0", "Civ1"]
        assert rust_absorptions[0].actors == ["Civ0", "Civ1"]
        assert world_py.civilizations[1].regions == ["B", "A"]
        assert world_rust.civilizations[1].regions == ["B", "A"]
        assert world_py.civilizations[2].regions == ["C"]
        assert world_rust.civilizations[2].regions == ["C"]
        assert world_rust.regions[0].controller == "Civ1"
        assert world_rust.regions[1].controller == "Civ1"
        assert world_rust.regions[2].controller == "Civ2"


# ── Forced Collapse Parity ───────────────────────────────────────────


class TestForcedCollapseParity:
    """Forced collapse is deterministic (triggered by asabiya < 0.1 and
    stability <= 20, with > 1 region). Both paths must produce the same
    structural outcome."""

    def test_forced_collapse_fires_both_paths(self):
        """Both paths strip to first region and halve military/economy."""
        sim = _get_simulator()
        world_py = _make_world(num_civs=1, num_regions=3)
        world_rust = _make_world(num_civs=1, num_regions=3)

        for w in [world_py, world_rust]:
            civ = w.civilizations[0]
            civ.asabiya = 0.05
            civ.stability = 15
            civ.military = 51
            civ.economy = 33
            civ.regions = ["A", "B", "C"]
            for r in w.regions:
                r.controller = civ.name

        # Python oracle (inline forced collapse in phase_consequences)
        from chronicler.utils import clamp, STAT_FLOOR
        py_civ = world_py.civilizations[0]
        # Manually apply forced collapse logic matching simulation.py
        lost = py_civ.regions[1:]
        py_civ.regions = py_civ.regions[:1]
        for region in world_py.regions:
            if region.name in lost:
                region.controller = None
        py_civ.military = clamp(py_civ.military // 2, STAT_FLOOR["military"], 100)
        py_civ.economy = clamp(py_civ.economy // 2, STAT_FLOOR["economy"], 100)

        # Rust path
        configure_politics_runtime(sim, world_rust)
        ops = call_rust_politics(sim, world_rust, hybrid_mode=False)
        apply_politics_ops(world_rust, ops)

        rust_civ = world_rust.civilizations[0]

        # Both should have exactly 1 region
        assert py_civ.regions == ["A"]
        assert rust_civ.regions == ["A"]

        # Both should halve stats via integer division
        assert py_civ.military == 51 // 2  # 25
        assert py_civ.economy == 33 // 2   # 16
        assert rust_civ.military == 51 // 2
        assert rust_civ.economy == 33 // 2

        # Lost regions should have controller=None
        for r in world_rust.regions:
            if r.name in ["B", "C"]:
                assert r.controller is None

    def test_forced_collapse_hybrid_mode_emits_shocks(self):
        """In hybrid mode, forced collapse emits shocks instead of direct deltas."""
        sim = _get_simulator()
        world = _make_world(num_civs=1, num_regions=3)
        civ = world.civilizations[0]
        civ.asabiya = 0.05
        civ.stability = 15
        civ.military = 50
        civ.economy = 30
        civ.regions = ["A", "B", "C"]
        world.agent_mode = "hybrid"
        for r in world.regions:
            r.controller = civ.name

        configure_politics_runtime(sim, world)
        ops = call_rust_politics(sim, world, hybrid_mode=True)

        # Should have HybridShock routing for military/economy effects
        mil_effects = [o for o in ops if o[2] == "civ_effect"
                       and o[3].get("field") == "military"
                       and o[0] == 11]
        eco_effects = [o for o in ops if o[2] == "civ_effect"
                       and o[3].get("field") == "economy"
                       and o[0] == 11]
        assert len(mil_effects) >= 1
        assert len(eco_effects) >= 1
        assert mil_effects[0][3]["routing"] == ROUTING_HYBRID_SHOCK
        assert eco_effects[0][3]["routing"] == ROUTING_HYBRID_SHOCK

    def test_no_collapse_when_stable(self):
        """No collapse when asabiya >= 0.1 or stability > 20."""
        sim = _get_simulator()
        world = _make_world(num_civs=1, num_regions=3)
        civ = world.civilizations[0]
        civ.asabiya = 0.5
        civ.stability = 50

        configure_politics_runtime(sim, world)
        ops = call_rust_politics(sim, world, hybrid_mode=False)
        strip_ops = [o for o in ops if o[2] == "civ_op"
                     and o[3].get("op_type") == CIV_OP_STRIP_TO_FIRST_REGION]
        assert len(strip_ops) == 0


# ── Allied Turns Bookkeeping Parity ──────────────────────────────────


class TestAlliedTurnsParity:
    """Allied turns update is deterministic bookkeeping."""

    def test_allied_turns_increment_both_paths(self):
        """ALLIED pairs get incremented on both paths."""
        sim = _get_simulator()
        world_py = _make_world(num_civs=2, num_regions=4)
        world_rust = _make_world(num_civs=2, num_regions=4)

        for w in [world_py, world_rust]:
            w.relationships["Civ0"]["Civ1"] = Relationship(
                disposition=Disposition.ALLIED, allied_turns=5,
            )
            w.relationships["Civ1"]["Civ0"] = Relationship(
                disposition=Disposition.ALLIED, allied_turns=5,
            )

        # Python oracle
        update_allied_turns(world_py)

        # Rust path
        configure_politics_runtime(sim, world_rust)
        ops = call_rust_politics(sim, world_rust, hybrid_mode=False)
        inc_ops = [o for o in ops if o[2] == "relationship_op"
                   and o[3].get("op_type") == REL_OP_INCREMENT_ALLIED_TURNS]

        assert world_py.relationships["Civ0"]["Civ1"].allied_turns == 6
        assert len(inc_ops) >= 2  # both directions

    def test_hostile_resets_allied_turns(self):
        """HOSTILE pairs reset to 0 on both paths."""
        sim = _get_simulator()
        world_py = _make_world(num_civs=2, num_regions=4)
        world_rust = _make_world(num_civs=2, num_regions=4)

        for w in [world_py, world_rust]:
            w.relationships["Civ0"]["Civ1"] = Relationship(
                disposition=Disposition.HOSTILE, allied_turns=7,
            )

        update_allied_turns(world_py)

        configure_politics_runtime(sim, world_rust)
        ops = call_rust_politics(sim, world_rust, hybrid_mode=False)
        reset_ops = [o for o in ops if o[2] == "relationship_op"
                     and o[3].get("op_type") == REL_OP_RESET_ALLIED_TURNS]

        assert world_py.relationships["Civ0"]["Civ1"].allied_turns == 0
        assert len(reset_ops) >= 1


# ── Decline Tracking Parity ──────────────────────────────────────────


class TestDeclineTrackingParity:
    """Decline tracking is deterministic bookkeeping."""

    def test_decline_tracking_emits_bookkeeping_ops(self):
        """Both paths emit stats_sum_history append."""
        sim = _get_simulator()
        world_py = _make_world(num_civs=1, num_regions=3)
        world_rust = _make_world(num_civs=1, num_regions=3)

        for w in [world_py, world_rust]:
            w.civilizations[0].stats_sum_history = [200] * 19

        # Python oracle
        update_decline_tracking(world_py)

        # Rust path
        configure_politics_runtime(sim, world_rust)
        ops = call_rust_politics(sim, world_rust, hybrid_mode=False)
        bk_ops = [o for o in ops if o[2] == "bookkeeping"]
        history_ops = [o for o in bk_ops
                       if o[3].get("bk_type") == BK_APPEND_STATS_HISTORY]

        assert len(world_py.civilizations[0].stats_sum_history) == 20
        assert len(history_ops) >= 1

    def test_hybrid_secession_decline_history_uses_visible_stats(self):
        """Hybrid-mode decline bookkeeping should ignore same-turn deferred shocks."""
        sim = _get_simulator()
        world = _make_world(num_civs=1, num_regions=5)
        civ = world.civilizations[0]
        civ.stability = 5
        civ.founded_turn = 0
        civ.military = 100
        civ.economy = 100
        civ.culture = 30
        civ.treasury = 100
        civ.regions = ["A", "B", "C", "D", "E"]
        civ.capital_region = "A"
        for region in world.regions:
            region.controller = civ.name
        world.agent_mode = "hybrid"

        configure_politics_runtime(sim, world)
        expected_sum = civ.military + civ.economy + civ.culture

        found = False
        for seed in range(100):
            world.seed = seed
            ops = call_rust_politics(sim, world, hybrid_mode=True)
            if any(
                family == "civ_op" and payload.get("op_type") == CIV_OP_CREATE_BREAKAWAY
                for _, _, family, payload in ops
            ):
                apply_politics_ops(world, ops)
                assert world.civilizations[0].stats_sum_history[-1] == expected_sum
                found = True
                break

        assert found, "expected at least one hybrid secession seed in the scan"


# ── Apply Layer Parity ───────────────────────────────────────────────


class TestApplyLayerParity:
    """Verify that the apply layer produces correct world state for given ops."""

    def test_apply_strip_to_first_region_matches_manual(self):
        """apply_politics_ops with StripToFirstRegion matches the manual
        inline code from simulation.py."""
        world = _make_world(num_civs=1, num_regions=3)
        civ = world.civilizations[0]
        civ.regions = ["A", "B", "C"]
        for r in world.regions:
            r.controller = civ.name

        ops = [(11, 0, "civ_op", {
            "op_type": CIV_OP_STRIP_TO_FIRST_REGION,
            "source_ref_kind": REF_EXISTING, "source_ref_id": 0,
        })]
        apply_politics_ops(world, ops)

        assert civ.regions == ["A"]
        assert world.regions[1].controller is None
        assert world.regions[2].controller is None

    def test_apply_reassign_capital_matches_oracle(self):
        """apply_politics_ops with ReassignCapital matches oracle behavior."""
        world = _make_world(num_civs=1, num_regions=3)
        civ = world.civilizations[0]
        civ.capital_region = "Z"  # lost
        civ.regions = ["B", "C"]

        ops = [(1, 0, "civ_op", {
            "op_type": CIV_OP_REASSIGN_CAPITAL,
            "source_ref_kind": REF_EXISTING, "source_ref_id": 0,
            "region_0": 2,  # region C
        })]
        apply_politics_ops(world, ops)
        assert civ.capital_region == "C"

    def test_apply_absorb_transfers_regions(self):
        """Absorb op transfers regions and empties dying civ."""
        world = _make_world(num_civs=2, num_regions=4)
        ops = [(9, 0, "civ_op", {
            "op_type": CIV_OP_ABSORB,
            "source_ref_kind": REF_EXISTING, "source_ref_id": 1,
            "target_ref_kind": REF_EXISTING, "target_ref_id": 0,
        })]
        apply_politics_ops(world, ops)
        assert world.civilizations[1].regions == []
        assert "C" in world.civilizations[0].regions


# ── Transient Cleanup Parity ─────────────────────────────────────────


class TestTransientCleanupParity:
    """Verify _seceded_this_turn survives one turn and clears the next."""

    def test_seceded_transient_survives_one_turn(self):
        """After secession fires through Rust, _seceded_this_turn is set."""
        sim = _get_simulator()
        world = _make_world(num_civs=1, num_regions=5, seed=42)
        civ = world.civilizations[0]
        civ.stability = 0
        civ.founded_turn = 0
        civ.military = 100
        civ.economy = 100
        civ.treasury = 100
        civ.leader_name_pool = ["Name1", "Name2"]
        civ.regions = ["A", "B", "C", "D", "E"]
        for r in world.regions:
            r.controller = civ.name

        configure_politics_runtime(sim, world)

        # Try seeds to find one where secession fires
        seceded_regions = []
        for seed in range(200):
            world.seed = seed
            world.turn = seed + 60
            civ.stability = 0
            civ.regions = ["A", "B", "C", "D", "E"]
            civ.military = 100
            civ.economy = 100
            civ.treasury = 100
            for r in world.regions:
                r.controller = civ.name
                r._seceded_this_turn = False
            world.civilizations = [civ]
            world.relationships = {}

            ops = call_rust_politics(sim, world, hybrid_mode=False)
            transient_ops = [o for o in ops if o[2] == "region_op"
                             and o[3].get("op_type") == REGION_OP_SET_SECEDED_TRANSIENT]

            if transient_ops:
                apply_politics_ops(world, ops)
                for r in world.regions:
                    if getattr(r, "_seceded_this_turn", False):
                        seceded_regions.append(r.name)
                break

        if not seceded_regions:
            pytest.skip("Could not trigger secession in 200 seeds")

        # Verify the transient was set
        assert len(seceded_regions) > 0

    def test_seceded_transient_cleared_by_build_region_batch(self):
        """_seceded_this_turn clears after build_region_batch reads it."""
        from chronicler.agent_bridge import build_region_batch

        world = _make_world(num_civs=1, num_regions=3)
        world.regions[1]._seceded_this_turn = True

        # First read sees the flag
        batch1 = build_region_batch(world)
        vals1 = batch1.column("seceded_this_turn").to_pylist()
        assert vals1[1] is True

        # Second read sees it cleared
        batch2 = build_region_batch(world)
        vals2 = batch2.column("seceded_this_turn").to_pylist()
        assert vals2[1] is False


# ── Pending Shocks Semantics ─────────────────────────────────────────


class TestPendingShockSemantics:
    """Verify that political shocks in hybrid mode go to pending_shocks
    (next-turn consumption), not current-turn application."""

    def test_hybrid_shocks_append_to_pending(self):
        """Capital loss in hybrid mode appends shocks to pending_shocks."""
        sim = _get_simulator()
        world = _make_world(num_civs=1, num_regions=3)
        world.agent_mode = "hybrid"
        world.civilizations[0].regions = ["B", "C"]
        world.civilizations[0].capital_region = "A"

        configure_politics_runtime(sim, world)
        ops = call_rust_politics(sim, world, hybrid_mode=True)
        apply_politics_ops(world, ops)

        # In hybrid mode, stability shock goes to pending_shocks
        assert len(world.pending_shocks) >= 1

    def test_off_mode_no_pending_shocks(self):
        """Off-mode produces no pending_shocks."""
        sim = _get_simulator()
        world = _make_world(num_civs=1, num_regions=3)
        world.civilizations[0].regions = ["B", "C"]
        world.civilizations[0].capital_region = "A"

        configure_politics_runtime(sim, world)
        ops = call_rust_politics(sim, world, hybrid_mode=False)
        apply_politics_ops(world, ops)

        assert len(world.pending_shocks) == 0


# ── Step Ordering Parity ─────────────────────────────────────────────


class TestStepOrderingParity:
    """Verify the 11-step ordering is preserved in Rust output."""

    def test_step_ordering_monotonic(self):
        """All ops from the Rust path have non-decreasing step values."""
        sim = _get_simulator()

        for seed in range(20):
            world = _make_world(num_civs=2, num_regions=5, seed=seed)
            world.civilizations[0].stability = 10
            world.civilizations[0].founded_turn = 0
            world.civilizations[0].asabiya = 0.05

            configure_politics_runtime(sim, world)
            ops = call_rust_politics(sim, world, hybrid_mode=False)

            steps = [o[0] for o in ops]
            for i in range(len(steps) - 1):
                assert steps[i] <= steps[i + 1], (
                    f"Seed {seed}: step ordering violated: "
                    f"step {steps[i]} followed by {steps[i + 1]}"
                )

    def test_step_values_in_valid_range(self):
        """All step values are in [1, 11]."""
        sim = _get_simulator()
        world = _make_world(num_civs=1, num_regions=3)
        world.civilizations[0].asabiya = 0.05
        world.civilizations[0].stability = 15

        configure_politics_runtime(sim, world)
        ops = call_rust_politics(sim, world, hybrid_mode=False)

        for step, seq, family, payload in ops:
            assert 1 <= step <= 11, f"Step {step} out of range"


# ── Determinism ──────────────────────────────────────────────────────


class TestRustDeterminism:
    """Prove Rust produces identical results across repeated runs."""

    def test_identical_ops_across_5_runs(self):
        """Same inputs produce identical op batches across 5 Rust runs."""
        sim = _get_simulator()
        world = _make_world(num_civs=2, num_regions=5, seed=7)
        world.civilizations[0].stability = 5
        world.civilizations[0].founded_turn = 0
        world.civilizations[0].military = 100
        world.civilizations[0].economy = 100
        world.civilizations[0].treasury = 100
        world.vassal_relations = [VassalRelation(overlord="Civ0", vassal="Civ1")]
        world.relationships["Civ1"]["Civ0"] = Relationship(
            disposition=Disposition.SUSPICIOUS,
        )

        configure_politics_runtime(sim, world)

        baseline_ops = call_rust_politics(sim, world, hybrid_mode=False)

        for run in range(5):
            ops = call_rust_politics(sim, world, hybrid_mode=False)
            assert len(ops) == len(baseline_ops), (
                f"Run {run}: op count differs ({len(ops)} vs {len(baseline_ops)})"
            )
            for i, (op, baseline) in enumerate(zip(ops, baseline_ops)):
                assert op[0] == baseline[0], f"Run {run}, op {i}: step differs"
                assert op[1] == baseline[1], f"Run {run}, op {i}: seq differs"
                assert op[2] == baseline[2], f"Run {run}, op {i}: family differs"
                assert op[3] == baseline[3], f"Run {run}, op {i}: payload differs"

    def test_event_merge_order_stable(self):
        """Events come in deterministic order across repeated runs."""
        sim = _get_simulator()

        # Use a world with multiple political events active
        world = _make_world(num_civs=2, num_regions=4, seed=42)
        world.civilizations[0].stability = 5
        world.civilizations[0].asabiya = 0.05
        world.civilizations[0].founded_turn = 0

        configure_politics_runtime(sim, world)

        baseline_ops = call_rust_politics(sim, world, hybrid_mode=False)
        baseline_events = [(o[0], o[1], o[3].get("event_type"))
                           for o in baseline_ops if o[2] == "event_trigger"]

        for _ in range(5):
            ops = call_rust_politics(sim, world, hybrid_mode=False)
            events = [(o[0], o[1], o[3].get("event_type"))
                      for o in ops if o[2] == "event_trigger"]
            assert events == baseline_events

    def test_determinism_across_20_seeds(self):
        """For each of 20 seeds, repeated runs produce identical ops."""
        sim = _get_simulator()

        for seed in range(20):
            world = _make_world(num_civs=2, num_regions=4, seed=seed)
            configure_politics_runtime(sim, world)

            ops1 = call_rust_politics(sim, world, hybrid_mode=False)
            ops2 = call_rust_politics(sim, world, hybrid_mode=False)

            assert len(ops1) == len(ops2), (
                f"Seed {seed}: op count differs ({len(ops1)} vs {len(ops2)})"
            )
            for i, (o1, o2) in enumerate(zip(ops1, ops2)):
                assert o1 == o2, (
                    f"Seed {seed}, op {i}: mismatch {o1} vs {o2}"
                )

    def test_determinism_with_topology(self):
        """Complex topology (vassals, federations, proxy wars) produces
        deterministic results."""
        sim = _get_simulator()
        world = _make_world(num_civs=3, num_regions=6, seed=99)
        world.vassal_relations = [VassalRelation(overlord="Civ0", vassal="Civ1")]
        world.federations = [
            Federation(name="The Iron Pact", members=["Civ1", "Civ2"],
                       founded_turn=50),
        ]
        world.proxy_wars = [
            ProxyWar(sponsor="Civ0", target_civ="Civ2", target_region="E"),
        ]
        world.relationships["Civ1"]["Civ0"] = Relationship(
            disposition=Disposition.HOSTILE,
        )

        configure_politics_runtime(sim, world)

        baseline = call_rust_politics(sim, world, hybrid_mode=False)
        for _ in range(5):
            result = call_rust_politics(sim, world, hybrid_mode=False)
            assert len(result) == len(baseline)
            for i in range(len(result)):
                assert result[i] == baseline[i]


# ── Restoration Structural Parity ────────────────────────────────────


class TestRestorationParity:
    """Restoration is probabilistic. We verify structural blocking conditions."""

    def test_no_restoration_without_exile_modifier(self):
        """Neither path triggers restoration when no exile modifier exists."""
        sim = _get_simulator()
        world_py = _make_world(num_civs=2, num_regions=4)
        world_rust = _make_world(num_civs=2, num_regions=4)

        py_events = check_restoration(world_py)

        configure_politics_runtime(sim, world_rust)
        ops = call_rust_politics(sim, world_rust, hybrid_mode=False)
        restore_events = [o for o in ops if o[2] == "event_trigger"
                          and o[3].get("event_type") == "restoration"]

        assert len(py_events) == 0
        assert len(restore_events) == 0

    def test_no_restoration_when_absorber_strong(self):
        """Strong absorber prevents restoration on both paths."""
        sim = _get_simulator()
        world_py = _make_world(num_civs=2, num_regions=4)
        world_rust = _make_world(num_civs=2, num_regions=4)

        for w in [world_py, world_rust]:
            w.civilizations[0].stability = 80  # strong absorber
            w.exile_modifiers = [
                ExileModifier(
                    original_civ_name="Civ1", absorber_civ="Civ0",
                    conquered_regions=["C", "D"], turns_remaining=15,
                ),
            ]
            # Dead civ
            w.civilizations[1].regions = []

        py_events = check_restoration(world_py)

        configure_politics_runtime(sim, world_rust)
        ops = call_rust_politics(sim, world_rust, hybrid_mode=False)
        restore_events = [o for o in ops if o[2] == "event_trigger"
                          and o[3].get("event_type") == "restoration"]

        assert len(py_events) == 0
        assert len(restore_events) == 0


# ── Full 11-Step Integration ─────────────────────────────────────────


class TestFullPassIntegration:
    """End-to-end Rust pass through all 11 steps on a complex fixture."""

    def test_complex_fixture_no_crash(self):
        """A world with many active political features runs without error."""
        sim = _get_simulator()
        world = _make_world(num_civs=4, num_regions=8, seed=42)

        # Set up complex political state
        world.civilizations[0].stability = 5
        world.civilizations[0].founded_turn = 0
        world.civilizations[0].decline_turns = 10

        world.vassal_relations = [
            VassalRelation(overlord="Civ0", vassal="Civ1"),
        ]
        world.relationships["Civ1"]["Civ0"] = Relationship(
            disposition=Disposition.HOSTILE,
        )
        world.relationships["Civ2"]["Civ3"] = Relationship(
            disposition=Disposition.ALLIED, allied_turns=10,
        )
        world.relationships["Civ3"]["Civ2"] = Relationship(
            disposition=Disposition.ALLIED, allied_turns=10,
        )

        configure_politics_runtime(sim, world)
        ops = call_rust_politics(sim, world, hybrid_mode=False)

        # Should produce some ops without crashing
        assert isinstance(ops, list)

        # Apply should not crash
        events = apply_politics_ops(world, ops)
        assert isinstance(events, list)

    def test_all_steps_represented_with_complex_setup(self):
        """At least bookkeeping (step 10) and decline tracking appear."""
        sim = _get_simulator()
        world = _make_world(num_civs=1, num_regions=3, seed=42)
        world.civilizations[0].stats_sum_history = [100] * 5

        configure_politics_runtime(sim, world)
        ops = call_rust_politics(sim, world, hybrid_mode=False)

        steps_present = {o[0] for o in ops}
        # Step 10 (decline tracking) should always produce bookkeeping
        assert 10 in steps_present, f"Step 10 should be present; got {steps_present}"
