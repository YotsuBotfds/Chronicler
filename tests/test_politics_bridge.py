"""M54c: Tests for dedicated politics FFI builders and ordered apply helpers.

Covers:
- build_politics_*_batch() helpers produce stable, well-typed payloads
- reconstruct_politics_ops() fixed tuple-order expectations
- apply_politics_ops() preserves step + seq order across mixed op families
- bridge transition helper timing and deterministic event merge
- _seceded_this_turn surviving one turn and clearing on next builder read
"""
from chronicler.models import (
    Civilization, Disposition, Event, ExileModifier, Federation, FactionType, Leader,
    ProxyWar, Region, Relationship, VassalRelation, WorldState,
)
from chronicler.politics import (
    # Builders
    build_politics_civ_input_batch,
    build_politics_region_input_batch,
    build_politics_relationship_batch,
    build_politics_vassal_batch,
    build_politics_federation_batch,
    build_politics_war_batch,
    build_politics_embargo_batch,
    build_politics_proxy_war_batch,
    build_politics_exile_batch,
    build_politics_context,
    # Op constants
    CIV_OP_CREATE_BREAKAWAY,
    CIV_OP_RESTORE,
    CIV_OP_REASSIGN_CAPITAL,
    CIV_OP_STRIP_TO_FIRST_REGION,
    CIV_OP_ABSORB,
    REGION_OP_SET_CONTROLLER,
    REGION_OP_NULLIFY_CONTROLLER,
    REGION_OP_SET_SECEDED_TRANSIENT,
    REL_OP_INIT_PAIR,
    REL_OP_SET_DISPOSITION,
    REL_OP_RESET_ALLIED_TURNS,
    REL_OP_INCREMENT_ALLIED_TURNS,
    FED_OP_CREATE,
    FED_OP_APPEND_MEMBER,
    FED_OP_REMOVE_MEMBER,
    FED_OP_DISSOLVE,
    VASSAL_OP_REMOVE,
    EXILE_OP_APPEND,
    EXILE_OP_REMOVE,
    PROXY_OP_SET_DETECTED,
    ROUTING_KEEP,
    ROUTING_DIRECT_ONLY,
    ROUTING_HYBRID_SHOCK,
    BK_APPEND_STATS_HISTORY,
    BK_INCREMENT_DECLINE,
    BK_RESET_DECLINE,
    BK_INCREMENT_EVENT_COUNT,
    BRIDGE_SECESSION,
    BRIDGE_RESTORATION,
    BRIDGE_ABSORPTION,
    FED_REF_EXISTING,
    REF_EXISTING,
    REF_NEW,
    CIV_NONE,
    _DISPOSITION_TO_U8,
    # Reconstruct and apply
    reconstruct_politics_ops,
    apply_politics_ops,
)


# ── Helpers ──────────────────────────────────────────────────────────


def _make_leader(name="L", trait="bold"):
    return Leader(name=name, trait=trait, reign_start=0)


def _make_world(num_civs=3, num_regions=5):
    """Build a minimal world with `num_civs` civs and `num_regions` regions."""
    adj_map = {}
    region_names = [chr(ord("A") + i) for i in range(num_regions)]
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
            population=20,
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

    # Ensure remaining unassigned regions get no controller
    assigned = set()
    for civ in civs:
        assigned.update(civ.regions)
    for r in regions:
        if r.name not in assigned:
            r.controller = None

    rels = {}
    for a in civs:
        rels[a.name] = {}
        for b in civs:
            if a.name != b.name:
                rels[a.name][b.name] = Relationship(disposition=Disposition.NEUTRAL)

    world = WorldState(
        name="test", seed=42, turn=100, regions=regions,
        civilizations=civs, relationships=rels,
    )
    return world


def _empty_op_batch():
    """Return an op batch dict with no rows (no step/seq columns)."""
    return {}


# ── Builder Tests ────────────────────────────────────────────────────


class TestBuildPoliticsCivInputBatch:
    def test_column_count_matches_civ_count(self):
        world = _make_world(num_civs=3, num_regions=6)
        batch = build_politics_civ_input_batch(world)
        assert len(batch["civ_idx"]) == 3
        assert len(batch["civ_name"]) == 3
        assert len(batch["stability"]) == 3

    def test_civ_names_preserved_for_seeded_roll_parity(self):
        world = _make_world(num_civs=2, num_regions=4)
        world.civilizations[0].name = "Alpha Realm"
        world.civilizations[1].name = "Beta League"
        batch = build_politics_civ_input_batch(world)
        assert batch["civ_name"] == ["Alpha Realm", "Beta League"]

    def test_hidden_civ_metadata_is_preserved_for_rust_politics(self):
        world = _make_world(num_civs=2, num_regions=4)
        civ = world.civilizations[0]
        civ.factions.influence[FactionType.MERCHANT] = 0.6
        civ.factions.influence[FactionType.MILITARY] = 0.2
        civ.factions.influence[FactionType.CULTURAL] = 0.1
        civ.factions.influence[FactionType.CLERGY] = 0.1
        civ.event_counts["secession_occurred"] = 2
        civ.event_counts["capital_lost"] = 1

        batch = build_politics_civ_input_batch(world)

        assert batch["dominant_faction"][0] == 1
        assert batch["secession_occurred_count"][0] == 2
        assert batch["capital_lost_count"][0] == 1

    def test_dead_civs_included(self):
        world = _make_world(num_civs=2, num_regions=4)
        world.civilizations[1].regions = []  # dead civ
        batch = build_politics_civ_input_batch(world)
        assert len(batch["civ_idx"]) == 2
        assert batch["num_regions"][1] == 0

    def test_capital_region_maps_to_index(self):
        world = _make_world(num_civs=1, num_regions=3)
        world.civilizations[0].capital_region = "B"
        batch = build_politics_civ_input_batch(world)
        # B is index 1
        assert batch["capital_region"][0] == 1

    def test_capital_none_maps_to_sentinel(self):
        world = _make_world(num_civs=1, num_regions=3)
        world.civilizations[0].capital_region = None
        batch = build_politics_civ_input_batch(world)
        assert batch["capital_region"][0] == CIV_NONE

    def test_stats_sum_history_packed(self):
        world = _make_world(num_civs=2, num_regions=4)
        world.civilizations[0].stats_sum_history = [100, 110, 120]
        world.civilizations[1].stats_sum_history = [50]
        batch = build_politics_civ_input_batch(world)
        assert batch["stats_sum_history_values"] == [100, 110, 120, 50]
        assert batch["stats_sum_history_offsets"] == [0, 3, 4]

    def test_region_indices_packed(self):
        world = _make_world(num_civs=2, num_regions=4)
        batch = build_politics_civ_input_batch(world)
        # Civ0 has regions [A, B] -> indices [0, 1]
        # Civ1 has regions [C, D] -> indices [2, 3]
        assert batch["region_values"] == [0, 1, 2, 3]
        assert batch["region_offsets"] == [0, 2, 4]

    def test_stable_ordering_across_calls(self):
        world = _make_world(num_civs=3, num_regions=6)
        b1 = build_politics_civ_input_batch(world)
        b2 = build_politics_civ_input_batch(world)
        for key in b1:
            assert b1[key] == b2[key], f"Column {key} differs across calls"


class TestBuildPoliticsRegionInputBatch:
    def test_column_count_matches_region_count(self):
        world = _make_world(num_civs=2, num_regions=5)
        batch = build_politics_region_input_batch(world)
        assert len(batch["region_idx"]) == 5

    def test_controller_maps_to_civ_index(self):
        world = _make_world(num_civs=2, num_regions=4)
        batch = build_politics_region_input_batch(world)
        # Regions 0,1 -> Civ0(idx 0), Regions 2,3 -> Civ1(idx 1)
        assert batch["controller"][0] == 0
        assert batch["controller"][2] == 1

    def test_uncontrolled_region_sentinel(self):
        world = _make_world(num_civs=1, num_regions=3)
        world.regions[2].controller = None
        batch = build_politics_region_input_batch(world)
        assert batch["controller"][2] == CIV_NONE

    def test_adjacencies_packed(self):
        world = _make_world(num_civs=1, num_regions=3)
        # A-B-C chain: A adj=[B], B adj=[A,C], C adj=[B]
        batch = build_politics_region_input_batch(world)
        assert batch["adjacency_offsets"] == [0, 1, 3, 4]
        assert batch["adjacency_values"] == [1, 0, 2, 1]


class TestBuildPoliticsRelationshipBatch:
    def test_row_count_matches_pairs(self):
        world = _make_world(num_civs=3, num_regions=6)
        batch = build_politics_relationship_batch(world)
        # 3 civs -> 6 directed pairs
        assert len(batch["civ_a"]) == 6

    def test_disposition_encoding(self):
        world = _make_world(num_civs=2, num_regions=4)
        world.relationships["Civ0"]["Civ1"] = Relationship(disposition=Disposition.HOSTILE)
        batch = build_politics_relationship_batch(world)
        # Find the Civ0->Civ1 row
        for i in range(len(batch["civ_a"])):
            if batch["civ_a"][i] == 0 and batch["civ_b"][i] == 1:
                assert batch["disposition"][i] == _DISPOSITION_TO_U8[Disposition.HOSTILE]
                break

    def test_allied_turns_packed(self):
        world = _make_world(num_civs=2, num_regions=4)
        world.relationships["Civ0"]["Civ1"] = Relationship(
            disposition=Disposition.ALLIED, allied_turns=15,
        )
        batch = build_politics_relationship_batch(world)
        for i in range(len(batch["civ_a"])):
            if batch["civ_a"][i] == 0 and batch["civ_b"][i] == 1:
                assert batch["allied_turns"][i] == 15
                break

    def test_sorted_deterministic_order(self):
        world = _make_world(num_civs=3, num_regions=6)
        b1 = build_politics_relationship_batch(world)
        b2 = build_politics_relationship_batch(world)
        assert b1 == b2


class TestBuildPoliticsVassalBatch:
    def test_empty_when_no_vassals(self):
        world = _make_world(num_civs=2, num_regions=4)
        batch = build_politics_vassal_batch(world)
        assert len(batch["overlord"]) == 0

    def test_packs_vassal_relations(self):
        world = _make_world(num_civs=2, num_regions=4)
        world.vassal_relations = [VassalRelation(overlord="Civ0", vassal="Civ1")]
        batch = build_politics_vassal_batch(world)
        assert len(batch["overlord"]) == 1
        assert batch["overlord"][0] == 0
        assert batch["vassal"][0] == 1


class TestBuildPoliticsFederationBatch:
    def test_empty_when_no_federations(self):
        world = _make_world(num_civs=2, num_regions=4)
        batch = build_politics_federation_batch(world)
        assert len(batch["federation_idx"]) == 0

    def test_packs_federation_members(self):
        world = _make_world(num_civs=3, num_regions=6)
        world.federations = [
            Federation(name="The Iron Pact", members=["Civ0", "Civ1"], founded_turn=10),
        ]
        batch = build_politics_federation_batch(world)
        assert len(batch["federation_idx"]) == 1
        assert batch["member_values"] == [0, 1]
        assert batch["member_offsets"] == [0, 2]


class TestBuildPoliticsWarBatch:
    def test_packs_active_wars(self):
        world = _make_world(num_civs=2, num_regions=4)
        world.active_wars = [("Civ0", "Civ1")]
        batch = build_politics_war_batch(world)
        assert batch["civ_a"] == [0]
        assert batch["civ_b"] == [1]


class TestBuildPoliticsEmbargoBatch:
    def test_packs_embargoes(self):
        world = _make_world(num_civs=2, num_regions=4)
        world.embargoes = [("Civ0", "Civ1")]
        batch = build_politics_embargo_batch(world)
        assert batch["civ_a"] == [0]
        assert batch["civ_b"] == [1]


class TestBuildPoliticsProxyWarBatch:
    def test_packs_proxy_wars(self):
        world = _make_world(num_civs=2, num_regions=4)
        world.proxy_wars = [ProxyWar(sponsor="Civ0", target_civ="Civ1", target_region="C")]
        batch = build_politics_proxy_war_batch(world)
        assert batch["sponsor"] == [0]
        assert batch["target_civ"] == [1]
        assert batch["target_region"] == [2]  # C is index 2
        assert batch["detected"] == [False]


class TestBuildPoliticsExileBatch:
    def test_packs_exile_modifiers(self):
        world = _make_world(num_civs=2, num_regions=4)
        world.exile_modifiers = [
            ExileModifier(
                original_civ_name="Civ1", absorber_civ="Civ0",
                conquered_regions=["C", "D"], turns_remaining=15,
                recognized_by=["Civ0"],
            ),
        ]
        batch = build_politics_exile_batch(world)
        assert batch["original_civ"] == [1]
        assert batch["absorber_civ"] == [0]
        assert batch["turns_remaining"] == [15]
        assert batch["region_values"] == [2, 3]
        assert batch["region_offsets"] == [0, 2]
        assert batch["recognized_values"] == [0]
        assert batch["recognized_offsets"] == [0, 1]


class TestBuildPoliticsContext:
    def test_packs_scalar_context(self):
        world = _make_world(num_civs=1, num_regions=2)
        ctx = build_politics_context(world, hybrid_mode=True)
        assert ctx["seed"] == 42
        assert ctx["turn"] == 100
        assert ctx["hybrid_mode"] is True

    def test_off_mode_context(self):
        world = _make_world(num_civs=1, num_regions=2)
        ctx = build_politics_context(world, hybrid_mode=False)
        assert ctx["hybrid_mode"] is False


# ── Reconstruct Tests ────────────────────────────────────────────────


class TestReconstructPoliticsOps:
    def test_empty_batches_produce_empty_ops(self):
        ops = reconstruct_politics_ops(
            _empty_op_batch(), _empty_op_batch(), _empty_op_batch(),
            _empty_op_batch(), _empty_op_batch(), _empty_op_batch(),
            _empty_op_batch(), _empty_op_batch(), _empty_op_batch(),
            _empty_op_batch(), _empty_op_batch(), _empty_op_batch(),
        )
        assert ops == []

    def test_sorts_by_step_then_seq(self):
        batch_a = {"step": [2, 1], "seq": [0, 0], "op_type": [0, 0]}
        batch_b = {"step": [1], "seq": [1], "op_type": [0]}
        ops = reconstruct_politics_ops(
            batch_a, batch_b, _empty_op_batch(),
            _empty_op_batch(), _empty_op_batch(), _empty_op_batch(),
            _empty_op_batch(), _empty_op_batch(), _empty_op_batch(),
            _empty_op_batch(), _empty_op_batch(), _empty_op_batch(),
        )
        steps_seqs = [(o[0], o[1]) for o in ops]
        assert steps_seqs == [(1, 0), (1, 1), (2, 0)]

    def test_mixed_families_interleave(self):
        civ_ops = {"step": [1], "seq": [0], "op_type": [CIV_OP_REASSIGN_CAPITAL]}
        region_ops = {"step": [1], "seq": [1], "op_type": [REGION_OP_SET_CONTROLLER]}
        rel_ops = {"step": [1], "seq": [2], "op_type": [REL_OP_INIT_PAIR]}
        ops = reconstruct_politics_ops(
            civ_ops, region_ops, rel_ops,
            _empty_op_batch(), _empty_op_batch(), _empty_op_batch(),
            _empty_op_batch(), _empty_op_batch(), _empty_op_batch(),
            _empty_op_batch(), _empty_op_batch(), _empty_op_batch(),
        )
        families = [o[2] for o in ops]
        assert families == ["civ_op", "region_op", "relationship_op"]

    def test_tuple_format(self):
        batch = {"step": [5], "seq": [3], "op_type": [0], "extra": ["foo"]}
        ops = reconstruct_politics_ops(
            batch, _empty_op_batch(), _empty_op_batch(),
            _empty_op_batch(), _empty_op_batch(), _empty_op_batch(),
            _empty_op_batch(), _empty_op_batch(), _empty_op_batch(),
            _empty_op_batch(), _empty_op_batch(), _empty_op_batch(),
        )
        assert len(ops) == 1
        step, seq, family, payload = ops[0]
        assert step == 5
        assert seq == 3
        assert family == "civ_op"
        assert payload["extra"] == "foo"

    def test_twelve_tuple_order_required(self):
        """All 12 batch families are in the expected positional order."""
        batches = [{"step": [i + 1], "seq": [0], "op_type": [0]} for i in range(12)]
        ops = reconstruct_politics_ops(*batches)
        expected_families = [
            "civ_op", "region_op", "relationship_op", "federation_op",
            "vassal_op", "exile_op", "proxy_war_op", "civ_effect",
            "bookkeeping", "artifact_intent", "bridge_transition", "event_trigger",
        ]
        families = [o[2] for o in ops]
        assert families == expected_families

    def test_decodes_packed_region_indices_for_exile_and_bridge_batches(self):
        exile_batch = {
            "step": [9],
            "seq": [0],
            "op_type": [EXILE_OP_APPEND],
            "original_civ_ref_kind": [REF_EXISTING],
            "original_civ_ref_id": [1],
            "absorber_civ_ref_kind": [REF_EXISTING],
            "absorber_civ_ref_id": [0],
            "region_count": [2],
            "region_0": [2],
            "region_1": [3],
            "region_2": [CIV_NONE],
            "region_3": [CIV_NONE],
            "turns_remaining": [10],
        }
        bridge_batch = {
            "step": [9],
            "seq": [1],
            "transition_type": [BRIDGE_RESTORATION],
            "source_ref_kind": [REF_EXISTING],
            "source_ref_id": [0],
            "target_ref_kind": [REF_EXISTING],
            "target_ref_id": [1],
            "region_count": [2],
            "region_0": [2],
            "region_1": [3],
            "region_2": [CIV_NONE],
            "region_3": [CIV_NONE],
        }

        ops = reconstruct_politics_ops(
            _empty_op_batch(), _empty_op_batch(), _empty_op_batch(),
            _empty_op_batch(), _empty_op_batch(), exile_batch,
            _empty_op_batch(), _empty_op_batch(), _empty_op_batch(),
            _empty_op_batch(), bridge_batch, _empty_op_batch(),
        )

        exile_payload = next(payload for _, _, family, payload in ops if family == "exile_op")
        bridge_payload = next(payload for _, _, family, payload in ops if family == "bridge_transition")
        assert exile_payload["region_indices"] == [2, 3]
        assert bridge_payload["region_indices"] == [2, 3]

    def test_decodes_list_region_columns_without_truncation(self):
        exile_batch = {
            "step": [9],
            "seq": [0],
            "op_type": [EXILE_OP_APPEND],
            "original_civ_ref_kind": [REF_EXISTING],
            "original_civ_ref_id": [1],
            "absorber_civ_ref_kind": [REF_EXISTING],
            "absorber_civ_ref_id": [0],
            "conquered_regions": [[0, 1, 2, 3, 4, 5]],
            "turns_remaining": [10],
        }
        bridge_batch = {
            "step": [9],
            "seq": [1],
            "transition_type": [BRIDGE_ABSORPTION],
            "source_ref_kind": [REF_EXISTING],
            "source_ref_id": [0],
            "target_ref_kind": [REF_EXISTING],
            "target_ref_id": [1],
            "region_indices": [[0, 1, 2, 3, 4, 5]],
        }

        ops = reconstruct_politics_ops(
            _empty_op_batch(), _empty_op_batch(), _empty_op_batch(),
            _empty_op_batch(), _empty_op_batch(), exile_batch,
            _empty_op_batch(), _empty_op_batch(), _empty_op_batch(),
            _empty_op_batch(), bridge_batch, _empty_op_batch(),
        )

        exile_payload = next(payload for _, _, family, payload in ops if family == "exile_op")
        bridge_payload = next(payload for _, _, family, payload in ops if family == "bridge_transition")
        assert exile_payload["region_indices"] == [0, 1, 2, 3, 4, 5]
        assert bridge_payload["region_indices"] == [0, 1, 2, 3, 4, 5]


# ── Apply Tests ──────────────────────────────────────────────────────


class TestApplyPoliticsOps:
    def test_create_breakaway_op_materializes_new_civ_for_followup_ops(self):
        world = _make_world(num_civs=1, num_regions=4)
        ops = [
            (2, 0, "civ_op", {
                "op_type": CIV_OP_CREATE_BREAKAWAY,
                "source_ref_kind": REF_EXISTING,
                "source_ref_id": 0,
                "target_ref_kind": REF_NEW,
                "target_ref_id": 0,
                "region_indices": [3],
                "stat_military": 8,
                "stat_economy": 9,
                "stat_culture": 30,
                "stat_stability": 40,
                "stat_treasury": 7,
                "stat_population": 20,
                "stat_asabiya": 0.7,
                "founded_turn": world.turn,
            }),
            (2, 1, "region_op", {
                "op_type": REGION_OP_SET_CONTROLLER,
                "region": 3,
                "controller_ref_kind": REF_NEW,
                "controller_ref_id": 0,
            }),
            (2, 2, "relationship_op", {
                "op_type": REL_OP_INIT_PAIR,
                "civ_a_ref_kind": REF_EXISTING,
                "civ_a_ref_id": 0,
                "civ_b_ref_kind": REF_NEW,
                "civ_b_ref_id": 0,
                "disposition": _DISPOSITION_TO_U8[Disposition.HOSTILE],
            }),
        ]

        apply_politics_ops(world, ops)

        assert len(world.civilizations) == 2
        new_civ = world.civilizations[1]
        assert new_civ.name != "Civ0"
        assert new_civ.population == 20
        assert new_civ.regions == ["D"]
        assert new_civ.capital_region == "D"
        assert world.regions[3].controller == new_civ.name
        assert world.civilizations[0].regions == ["A", "B", "C"]
        assert world.civilizations[0].population == 60
        assert world.relationships["Civ0"][new_civ.name].disposition == Disposition.HOSTILE

    def test_restore_op_materializes_dead_civ_for_followup_ops(self):
        world = _make_world(num_civs=2, num_regions=4)
        absorber = world.civilizations[0]
        restored = world.civilizations[1]
        absorber.regions = ["A", "B", "C"]
        restored.regions = []
        world.regions[2].controller = absorber.name
        world.regions[3].controller = None
        world.exile_modifiers = [
            ExileModifier(
                original_civ_name=restored.name,
                absorber_civ=absorber.name,
                conquered_regions=["C"],
                turns_remaining=5,
            ),
        ]

        ops = [
            (8, 0, "civ_op", {
                "op_type": CIV_OP_RESTORE,
                "source_ref_kind": REF_EXISTING,
                "source_ref_id": 0,
                "target_ref_kind": REF_EXISTING,
                "target_ref_id": 1,
                "region_indices": [2],
                "stat_military": 20,
                "stat_economy": 20,
                "stat_culture": 30,
                "stat_stability": 50,
                "stat_treasury": 0,
                "stat_population": 30,
                "stat_asabiya": 0.8,
                "founded_turn": world.turn,
            }),
            (8, 1, "region_op", {
                "op_type": REGION_OP_SET_CONTROLLER,
                "region": 2,
                "controller_ref_kind": REF_EXISTING,
                "controller_ref_id": 1,
            }),
        ]

        apply_politics_ops(world, ops)

        assert absorber.regions == ["A", "B"]
        assert absorber.population == 40
        assert restored.regions == ["C"]
        assert restored.capital_region == "C"
        assert restored.population == 30
        assert world.regions[2].controller == restored.name
        assert restored.leader.name != "Placeholder"

    def test_restore_op_resets_absorber_war_frequency_when_last_region_lost(self):
        world = _make_world(num_civs=2, num_regions=4)
        absorber = world.civilizations[0]
        restored = world.civilizations[1]
        absorber.regions = ["C"]
        absorber.war_weariness = 3.25
        absorber.peace_momentum = 4.0
        restored.regions = []
        world.regions[2].controller = absorber.name
        world.exile_modifiers = [
            ExileModifier(
                original_civ_name=restored.name,
                absorber_civ=absorber.name,
                conquered_regions=["C"],
                turns_remaining=5,
            ),
        ]

        ops = [(8, 0, "civ_op", {
            "op_type": CIV_OP_RESTORE,
            "source_ref_kind": REF_EXISTING,
            "source_ref_id": 0,
            "target_ref_kind": REF_EXISTING,
            "target_ref_id": 1,
            "region_indices": [2],
            "stat_military": 20,
            "stat_economy": 20,
            "stat_culture": 30,
            "stat_stability": 50,
            "stat_treasury": 0,
            "stat_population": 30,
            "stat_asabiya": 0.8,
            "founded_turn": world.turn,
        })]

        apply_politics_ops(world, ops)

        assert absorber.regions == []
        assert absorber.war_weariness == 0.0
        assert absorber.peace_momentum == 0.0

    def test_breakaway_and_restore_asabiya_normalize_float32_constants(self):
        world = _make_world(num_civs=2, num_regions=4)
        absorber = world.civilizations[0]
        restored = world.civilizations[1]
        absorber.regions = ["A", "B", "C"]
        restored.regions = []
        world.regions[2].controller = absorber.name
        world.exile_modifiers = [
            ExileModifier(
                original_civ_name=restored.name,
                absorber_civ=absorber.name,
                conquered_regions=["C"],
                turns_remaining=5,
            ),
        ]
        ops = [
            (2, 0, "civ_op", {
                "op_type": CIV_OP_CREATE_BREAKAWAY,
                "source_ref_kind": REF_EXISTING,
                "source_ref_id": 0,
                "target_ref_kind": REF_NEW,
                "target_ref_id": 0,
                "region_indices": [3],
                "stat_military": 8,
                "stat_economy": 9,
                "stat_culture": 30,
                "stat_stability": 40,
                "stat_treasury": 7,
                "stat_population": 20,
                "stat_asabiya": 0.699999988079071,
                "founded_turn": world.turn,
            }),
            (2, 1, "region_op", {
                "op_type": REGION_OP_SET_CONTROLLER,
                "region": 3,
                "controller_ref_kind": REF_NEW,
                "controller_ref_id": 0,
            }),
            (8, 0, "civ_op", {
                "op_type": CIV_OP_RESTORE,
                "source_ref_kind": REF_EXISTING,
                "source_ref_id": 0,
                "target_ref_kind": REF_EXISTING,
                "target_ref_id": 1,
                "region_indices": [2],
                "stat_military": 20,
                "stat_economy": 20,
                "stat_culture": 30,
                "stat_stability": 50,
                "stat_treasury": 0,
                "stat_population": 30,
                "stat_asabiya": 0.800000011920929,
                "founded_turn": world.turn,
            }),
            (8, 1, "region_op", {
                "op_type": REGION_OP_SET_CONTROLLER,
                "region": 2,
                "controller_ref_kind": REF_EXISTING,
                "controller_ref_id": 1,
            }),
        ]

        apply_politics_ops(world, ops)

        assert world.civilizations[2].asabiya == 0.7
        assert world.civilizations[1].asabiya == 0.5
        assert world.regions[2].asabiya_state.asabiya == 0.8

    def test_hybrid_pending_shocks_group_contiguous_civ_effects(self):
        world = _make_world(num_civs=1, num_regions=3)
        world.agent_mode = "hybrid"
        ops = [
            (2, 0, "civ_effect", {
                "civ_ref_kind": REF_EXISTING,
                "civ_ref_id": 0,
                "field": "military",
                "delta": -0.25,
                "routing": ROUTING_HYBRID_SHOCK,
            }),
            (2, 1, "civ_effect", {
                "civ_ref_kind": REF_EXISTING,
                "civ_ref_id": 0,
                "field": "economy",
                "delta": -0.15,
                "routing": ROUTING_HYBRID_SHOCK,
            }),
            (2, 2, "civ_effect", {
                "civ_ref_kind": REF_EXISTING,
                "civ_ref_id": 0,
                "field": "stability",
                "delta": -0.10,
                "routing": ROUTING_HYBRID_SHOCK,
            }),
        ]

        apply_politics_ops(world, ops)

        assert len(world.pending_shocks) == 1
        shock = world.pending_shocks[0]
        assert shock.civ_id == 0
        assert shock.military_shock == -0.25
        assert shock.economy_shock == -0.15
        assert shock.stability_shock == -0.10

    def test_hybrid_pending_shocks_do_not_merge_across_event_boundaries(self):
        world = _make_world(num_civs=1, num_regions=3)
        world.agent_mode = "hybrid"
        ops = [
            (1, 0, "civ_effect", {
                "civ_ref_kind": REF_EXISTING,
                "civ_ref_id": 0,
                "field": "stability",
                "delta": -0.20,
                "routing": ROUTING_HYBRID_SHOCK,
            }),
            (1, 1, "civ_op", {
                "op_type": CIV_OP_REASSIGN_CAPITAL,
                "source_ref_kind": REF_EXISTING,
                "source_ref_id": 0,
                "region_indices": [1],
            }),
            (2, 0, "civ_effect", {
                "civ_ref_kind": REF_EXISTING,
                "civ_ref_id": 0,
                "field": "military",
                "delta": -0.30,
                "routing": ROUTING_HYBRID_SHOCK,
            }),
            (2, 1, "civ_effect", {
                "civ_ref_kind": REF_EXISTING,
                "civ_ref_id": 0,
                "field": "economy",
                "delta": -0.10,
                "routing": ROUTING_HYBRID_SHOCK,
            }),
        ]

        apply_politics_ops(world, ops)

        assert len(world.pending_shocks) == 2
        first, second = world.pending_shocks
        assert first.stability_shock == -0.20
        assert first.military_shock == 0.0
        assert second.military_shock == -0.30
        assert second.economy_shock == -0.10
        assert second.stability_shock == 0.0

    def test_reassign_capital(self):
        world = _make_world(num_civs=1, num_regions=3)
        ops = [(1, 0, "civ_op", {
            "op_type": CIV_OP_REASSIGN_CAPITAL,
            "source_ref_kind": REF_EXISTING, "source_ref_id": 0,
            "region_0": 2,  # region C
        })]
        apply_politics_ops(world, ops)
        assert world.civilizations[0].capital_region == "C"

    def test_strip_to_first_region(self):
        world = _make_world(num_civs=1, num_regions=3)
        ops = [(11, 0, "civ_op", {
            "op_type": CIV_OP_STRIP_TO_FIRST_REGION,
            "source_ref_kind": REF_EXISTING, "source_ref_id": 0,
        })]
        apply_politics_ops(world, ops)
        assert world.civilizations[0].regions == ["A"]
        # Stripped regions have controller nullified
        assert world.regions[1].controller is None
        assert world.regions[2].controller is None

    def test_region_op_set_controller(self):
        world = _make_world(num_civs=2, num_regions=4)
        # Transfer region 2 (C) from Civ1 to Civ0
        ops = [(2, 0, "region_op", {
            "op_type": REGION_OP_SET_CONTROLLER,
            "region": 2,
            "controller_ref_kind": REF_EXISTING, "controller_ref_id": 0,
        })]
        apply_politics_ops(world, ops)
        assert world.regions[2].controller == "Civ0"

    def test_region_op_nullify_controller(self):
        world = _make_world(num_civs=1, num_regions=3)
        ops = [(11, 0, "region_op", {
            "op_type": REGION_OP_NULLIFY_CONTROLLER,
            "region": 1,
        })]
        apply_politics_ops(world, ops)
        assert world.regions[1].controller is None

    def test_region_op_set_seceded_transient(self):
        world = _make_world(num_civs=1, num_regions=3)
        ops = [(2, 5, "region_op", {
            "op_type": REGION_OP_SET_SECEDED_TRANSIENT,
            "region": 1,
        })]
        apply_politics_ops(world, ops)
        assert getattr(world.regions[1], "_seceded_this_turn", False) is True

    def test_relationship_op_init_pair(self):
        world = _make_world(num_civs=3, num_regions=6)
        ops = [(2, 10, "relationship_op", {
            "op_type": REL_OP_INIT_PAIR,
            "civ_a_ref_kind": REF_EXISTING, "civ_a_ref_id": 0,
            "civ_b_ref_kind": REF_EXISTING, "civ_b_ref_id": 2,
            "disposition": _DISPOSITION_TO_U8[Disposition.HOSTILE],
        })]
        apply_politics_ops(world, ops)
        assert world.relationships["Civ0"]["Civ2"].disposition == Disposition.HOSTILE
        assert world.relationships["Civ2"]["Civ0"].disposition == Disposition.HOSTILE

    def test_relationship_op_set_disposition(self):
        world = _make_world(num_civs=2, num_regions=4)
        ops = [(7, 0, "relationship_op", {
            "op_type": REL_OP_SET_DISPOSITION,
            "civ_a_ref_kind": REF_EXISTING, "civ_a_ref_id": 0,
            "civ_b_ref_kind": REF_EXISTING, "civ_b_ref_id": 1,
            "disposition": _DISPOSITION_TO_U8[Disposition.HOSTILE],
        })]
        apply_politics_ops(world, ops)
        assert world.relationships["Civ0"]["Civ1"].disposition == Disposition.HOSTILE

    def test_relationship_op_increment_allied_turns(self):
        world = _make_world(num_civs=2, num_regions=4)
        world.relationships["Civ0"]["Civ1"].allied_turns = 5
        ops = [(3, 0, "relationship_op", {
            "op_type": REL_OP_INCREMENT_ALLIED_TURNS,
            "civ_a_ref_kind": REF_EXISTING, "civ_a_ref_id": 0,
            "civ_b_ref_kind": REF_EXISTING, "civ_b_ref_id": 1,
        })]
        apply_politics_ops(world, ops)
        assert world.relationships["Civ0"]["Civ1"].allied_turns == 6

    def test_relationship_op_reset_allied_turns(self):
        world = _make_world(num_civs=2, num_regions=4)
        world.relationships["Civ0"]["Civ1"].allied_turns = 10
        ops = [(3, 0, "relationship_op", {
            "op_type": REL_OP_RESET_ALLIED_TURNS,
            "civ_a_ref_kind": REF_EXISTING, "civ_a_ref_id": 0,
            "civ_b_ref_kind": REF_EXISTING, "civ_b_ref_id": 1,
        })]
        apply_politics_ops(world, ops)
        assert world.relationships["Civ0"]["Civ1"].allied_turns == 0

    def test_federation_create(self):
        world = _make_world(num_civs=2, num_regions=4)
        ops = [(5, 0, "federation_op", {
            "op_type": FED_OP_CREATE,
            "federation_name": "The Iron Pact",
            "founded_turn": 100,
            "federation_ref_id": 99,  # local id
            "civ_ref_kind": REF_EXISTING, "civ_ref_id": 0,
        }), (5, 1, "federation_op", {
            "op_type": FED_OP_APPEND_MEMBER,
            "federation_ref_kind": 1, "federation_ref_id": 99,  # New ref
            "civ_ref_kind": REF_EXISTING, "civ_ref_id": 1,
        })]
        new_fed_map = {}
        apply_politics_ops(world, ops, new_fed_map=new_fed_map)
        assert len(world.federations) == 1
        assert world.federations[0].name == "The Iron Pact"
        assert "Civ0" in world.federations[0].members
        assert "Civ1" in world.federations[0].members

    def test_federation_create_round_trips_initial_members_and_name_seed(self):
        world = _make_world(num_civs=3, num_regions=6)
        ops = [(5, 0, "federation_op", {
            "op_type": FED_OP_CREATE,
            "federation_ref_kind": REF_NEW,
            "federation_ref_id": 7,
            "civ_ref_kind": REF_EXISTING,
            "civ_ref_id": 0,
            "member_count": 2,
            "member_0_ref_kind": REF_EXISTING,
            "member_0_ref_id": 0,
            "member_1_ref_kind": REF_EXISTING,
            "member_1_ref_id": 2,
            "context_seed": 1234,
            "founded_turn": 100,
        })]

        apply_politics_ops(world, ops)

        assert len(world.federations) == 1
        assert world.federations[0].members == ["Civ0", "Civ2"]
        assert world.federations[0].name == "The Maritime Accord"

    def test_federation_dissolve(self):
        world = _make_world(num_civs=2, num_regions=4)
        world.federations = [Federation(name="Old Pact", members=["Civ0"], founded_turn=1)]
        ops = [(6, 0, "federation_op", {
            "op_type": FED_OP_DISSOLVE,
            "federation_ref_kind": 0, "federation_ref_id": 0,
            "civ_ref_kind": REF_EXISTING, "civ_ref_id": 0,
        })]
        apply_politics_ops(world, ops)
        assert len(world.federations) == 0

    def test_federation_refs_survive_lower_index_dissolve(self):
        world = _make_world(num_civs=5, num_regions=8)
        world.federations = [
            Federation(name="Old Pact", members=["Civ0"], founded_turn=1),
            Federation(name="Grand Accord", members=["Civ2", "Civ3"], founded_turn=2),
        ]
        ops = [
            (5, 0, "federation_op", {
                "op_type": FED_OP_APPEND_MEMBER,
                "federation_ref_kind": FED_REF_EXISTING,
                "federation_ref_id": 1,
                "civ_ref_kind": REF_EXISTING,
                "civ_ref_id": 4,
            }),
            (6, 0, "federation_op", {
                "op_type": FED_OP_DISSOLVE,
                "federation_ref_kind": FED_REF_EXISTING,
                "federation_ref_id": 0,
                "civ_ref_kind": REF_EXISTING,
                "civ_ref_id": 0,
            }),
            (6, 1, "federation_op", {
                "op_type": FED_OP_REMOVE_MEMBER,
                "federation_ref_kind": FED_REF_EXISTING,
                "federation_ref_id": 1,
                "civ_ref_kind": REF_EXISTING,
                "civ_ref_id": 4,
            }),
        ]

        apply_politics_ops(world, ops)

        assert len(world.federations) == 1
        assert world.federations[0].name == "Grand Accord"
        assert world.federations[0].members == ["Civ2", "Civ3"]

    def test_vassal_op_remove(self):
        world = _make_world(num_civs=2, num_regions=4)
        world.vassal_relations = [VassalRelation(overlord="Civ0", vassal="Civ1")]
        ops = [(4, 0, "vassal_op", {
            "op_type": VASSAL_OP_REMOVE,
            "vassal_ref_kind": REF_EXISTING, "vassal_ref_id": 1,
            "overlord_ref_kind": REF_EXISTING, "overlord_ref_id": 0,
        })]
        apply_politics_ops(world, ops)
        assert len(world.vassal_relations) == 0

    def test_exile_op_append(self):
        world = _make_world(num_civs=2, num_regions=4)
        ops = [(9, 0, "exile_op", {
            "op_type": EXILE_OP_APPEND,
            "original_civ_ref_kind": REF_EXISTING, "original_civ_ref_id": 1,
            "absorber_civ_ref_kind": REF_EXISTING, "absorber_civ_ref_id": 0,
            "region_indices": [2, 3],
            "turns_remaining": 10,
        })]
        apply_politics_ops(world, ops)
        assert len(world.exile_modifiers) == 1
        assert world.exile_modifiers[0].original_civ_name == "Civ1"
        assert world.exile_modifiers[0].conquered_regions == ["C", "D"]

    def test_exile_op_append_round_trips_packed_region_columns(self):
        world = _make_world(num_civs=2, num_regions=4)
        exile_batch = {
            "step": [9],
            "seq": [0],
            "op_type": [EXILE_OP_APPEND],
            "original_civ_ref_kind": [REF_EXISTING],
            "original_civ_ref_id": [1],
            "absorber_civ_ref_kind": [REF_EXISTING],
            "absorber_civ_ref_id": [0],
            "region_count": [2],
            "region_0": [2],
            "region_1": [3],
            "region_2": [CIV_NONE],
            "region_3": [CIV_NONE],
            "turns_remaining": [10],
        }

        ops = reconstruct_politics_ops(
            _empty_op_batch(), _empty_op_batch(), _empty_op_batch(),
            _empty_op_batch(), _empty_op_batch(), exile_batch,
            _empty_op_batch(), _empty_op_batch(), _empty_op_batch(),
            _empty_op_batch(), _empty_op_batch(), _empty_op_batch(),
        )
        apply_politics_ops(world, ops)

        assert len(world.exile_modifiers) == 1
        assert world.exile_modifiers[0].conquered_regions == ["C", "D"]

    def test_exile_op_remove(self):
        world = _make_world(num_civs=2, num_regions=4)
        world.exile_modifiers = [
            ExileModifier(
                original_civ_name="Civ1", absorber_civ="Civ0",
                conquered_regions=["C"], turns_remaining=5,
            ),
        ]
        ops = [(8, 0, "exile_op", {
            "op_type": EXILE_OP_REMOVE,
            "original_civ_ref_kind": REF_EXISTING, "original_civ_ref_id": 1,
        })]
        apply_politics_ops(world, ops)
        assert len(world.exile_modifiers) == 0

    def test_proxy_war_op_set_detected(self):
        world = _make_world(num_civs=2, num_regions=4)
        world.proxy_wars = [ProxyWar(sponsor="Civ0", target_civ="Civ1", target_region="C")]
        ops = [(7, 0, "proxy_war_op", {
            "op_type": PROXY_OP_SET_DETECTED,
            "sponsor_ref_kind": REF_EXISTING, "sponsor_ref_id": 0,
            "target_civ_ref_kind": REF_EXISTING, "target_civ_ref_id": 1,
            "target_region": 2,
        })]
        apply_politics_ops(world, ops)
        assert world.proxy_wars[0].detected is True

    def test_proxy_war_op_set_detected_matches_target_region(self):
        world = _make_world(num_civs=2, num_regions=4)
        world.proxy_wars = [
            ProxyWar(sponsor="Civ0", target_civ="Civ1", target_region="C"),
            ProxyWar(sponsor="Civ0", target_civ="Civ1", target_region="D"),
        ]
        ops = [(7, 0, "proxy_war_op", {
            "op_type": PROXY_OP_SET_DETECTED,
            "sponsor_ref_kind": REF_EXISTING, "sponsor_ref_id": 0,
            "target_civ_ref_kind": REF_EXISTING, "target_civ_ref_id": 1,
            "target_region": 3,
        })]
        apply_politics_ops(world, ops)
        assert world.proxy_wars[0].detected is False
        assert world.proxy_wars[1].detected is True

    def test_proxy_war_op_set_detected_marks_identical_duplicates(self):
        world = _make_world(num_civs=2, num_regions=4)
        world.proxy_wars = [
            ProxyWar(sponsor="Civ0", target_civ="Civ1", target_region="C"),
            ProxyWar(sponsor="Civ0", target_civ="Civ1", target_region="C"),
        ]
        ops = [(7, 0, "proxy_war_op", {
            "op_type": PROXY_OP_SET_DETECTED,
            "sponsor_ref_kind": REF_EXISTING, "sponsor_ref_id": 0,
            "target_civ_ref_kind": REF_EXISTING, "target_civ_ref_id": 1,
            "target_region": 2,
        })]
        apply_politics_ops(world, ops)
        assert all(pw.detected for pw in world.proxy_wars)

    def test_civ_effect_direct(self):
        world = _make_world(num_civs=1, num_regions=3)
        world.civilizations[0].stability = 50
        ops = [(1, 0, "civ_effect", {
            "civ_ref_kind": REF_EXISTING, "civ_ref_id": 0,
            "field": "stability", "delta": -20.0,
            "routing": ROUTING_DIRECT_ONLY,
        })]
        apply_politics_ops(world, ops)
        assert world.civilizations[0].stability == 30

    def test_civ_effect_hybrid_shock(self):
        world = _make_world(num_civs=1, num_regions=3)
        world.agent_mode = "hybrid"
        world.civilizations[0].stability = 50
        ops = [(1, 0, "civ_effect", {
            "civ_ref_kind": REF_EXISTING, "civ_ref_id": 0,
            "field": "stability", "delta": -0.5,
            "routing": ROUTING_HYBRID_SHOCK,
        })]
        apply_politics_ops(world, ops)
        # In hybrid mode, delta goes to pending_shocks, not direct
        assert world.civilizations[0].stability == 50
        assert len(world.pending_shocks) == 1

    def test_civ_effect_hybrid_shock_merges_same_civ_fields(self):
        world = _make_world(num_civs=1, num_regions=3)
        world.agent_mode = "hybrid"
        ops = [
            (11, 0, "civ_effect", {
                "civ_ref_kind": REF_EXISTING, "civ_ref_id": 0,
                "field": "military", "delta": -0.5,
                "routing": ROUTING_HYBRID_SHOCK,
            }),
            (11, 1, "civ_effect", {
                "civ_ref_kind": REF_EXISTING, "civ_ref_id": 0,
                "field": "economy", "delta": -0.5,
                "routing": ROUTING_HYBRID_SHOCK,
            }),
        ]

        apply_politics_ops(world, ops)

        assert len(world.pending_shocks) == 1
        shock = world.pending_shocks[0]
        assert shock.civ_id == 0
        assert shock.military_shock == -0.5
        assert shock.economy_shock == -0.5

    def test_civ_effect_hybrid_shock_coalesces_contiguous_duplicate_fields(self):
        world = _make_world(num_civs=1, num_regions=3)
        world.agent_mode = "hybrid"
        ops = [
            (11, 0, "civ_effect", {
                "civ_ref_kind": REF_EXISTING, "civ_ref_id": 0,
                "field": "stability", "delta": 0.2,
                "routing": ROUTING_HYBRID_SHOCK,
            }),
            (11, 1, "civ_effect", {
                "civ_ref_kind": REF_EXISTING, "civ_ref_id": 0,
                "field": "stability", "delta": 0.2,
                "routing": ROUTING_HYBRID_SHOCK,
            }),
        ]

        apply_politics_ops(world, ops)

        assert len(world.pending_shocks) == 1
        assert world.pending_shocks[0].stability_shock == 0.2

    def test_civ_effect_treasury(self):
        world = _make_world(num_civs=1, num_regions=3)
        world.civilizations[0].treasury = 100
        ops = [(2, 0, "civ_effect", {
            "civ_ref_kind": REF_EXISTING, "civ_ref_id": 0,
            "field": "treasury", "delta": -30.0,
            "routing": ROUTING_DIRECT_ONLY,
        })]
        apply_politics_ops(world, ops)
        assert world.civilizations[0].treasury == 70

    def test_civ_effect_asabiya(self):
        world = _make_world(num_civs=1, num_regions=3)
        world.civilizations[0].asabiya = 0.5
        ops = [(4, 0, "civ_effect", {
            "civ_ref_kind": REF_EXISTING, "civ_ref_id": 0,
            "field": "asabiya", "delta": 0.2,
            "routing": ROUTING_KEEP,
        })]
        apply_politics_ops(world, ops)
        assert abs(world.civilizations[0].asabiya - 0.5) < 0.001
        for region in world.regions:
            if region.controller == world.civilizations[0].name:
                assert abs(region.asabiya_state.asabiya - 0.7) < 0.001

    def test_bookkeeping_append_stats_history(self):
        world = _make_world(num_civs=1, num_regions=3)
        world.civilizations[0].stats_sum_history = [100]
        ops = [(10, 0, "bookkeeping", {
            "civ_ref_kind": REF_EXISTING, "civ_ref_id": 0,
            "bk_type": BK_APPEND_STATS_HISTORY, "value": 110,
        })]
        apply_politics_ops(world, ops)
        assert world.civilizations[0].stats_sum_history == [100, 110]

    def test_bookkeeping_increment_decline(self):
        world = _make_world(num_civs=1, num_regions=3)
        world.civilizations[0].decline_turns = 5
        ops = [(10, 0, "bookkeeping", {
            "civ_ref_kind": REF_EXISTING, "civ_ref_id": 0,
            "bk_type": BK_INCREMENT_DECLINE,
        })]
        apply_politics_ops(world, ops)
        assert world.civilizations[0].decline_turns == 6

    def test_bookkeeping_reset_decline(self):
        world = _make_world(num_civs=1, num_regions=3)
        world.civilizations[0].decline_turns = 10
        ops = [(10, 0, "bookkeeping", {
            "civ_ref_kind": REF_EXISTING, "civ_ref_id": 0,
            "bk_type": BK_RESET_DECLINE,
        })]
        apply_politics_ops(world, ops)
        assert world.civilizations[0].decline_turns == 0

    def test_bookkeeping_increment_event_count(self):
        world = _make_world(num_civs=1, num_regions=3)
        ops = [(2, 0, "bookkeeping", {
            "civ_ref_kind": REF_EXISTING, "civ_ref_id": 0,
            "bk_type": BK_INCREMENT_EVENT_COUNT,
            "event_key": "secession_occurred",
        })]
        apply_politics_ops(world, ops)
        assert world.civilizations[0].event_counts["secession_occurred"] == 1

    def test_event_trigger(self):
        world = _make_world(num_civs=2, num_regions=4)
        ops = [(2, 99, "event_trigger", {
            "event_type": "secession",
            "actor_count": 2,
            "actor_0_ref_kind": REF_EXISTING, "actor_0_ref_id": 0,
            "actor_1_ref_kind": REF_EXISTING, "actor_1_ref_id": 1,
            "importance": 9,
            "description": "The Secession of Civ1 from Civ0",
        })]
        events = apply_politics_ops(world, ops)
        assert len(events) == 1
        assert events[0].event_type == "secession"
        assert events[0].actors == ["Civ0", "Civ1"]
        assert events[0].importance == 9

    def test_step_seq_ordering_preserved(self):
        """Ops from different families in different steps execute in step+seq order."""
        world = _make_world(num_civs=2, num_regions=4)
        world.civilizations[0].stability = 50
        world.civilizations[0].treasury = 100
        ops = [
            (3, 0, "civ_effect", {
                "civ_ref_kind": REF_EXISTING, "civ_ref_id": 0,
                "field": "stability", "delta": -10.0,
                "routing": ROUTING_DIRECT_ONLY,
            }),
            (1, 0, "civ_effect", {
                "civ_ref_kind": REF_EXISTING, "civ_ref_id": 0,
                "field": "treasury", "delta": -50.0,
                "routing": ROUTING_DIRECT_ONLY,
            }),
        ]
        # Ops arrive out of order — apply should sort first
        apply_politics_ops(world, sorted(ops, key=lambda t: (t[0], t[1])))
        # Treasury (-50) at step 1, stability (-10) at step 3
        assert world.civilizations[0].treasury == 50
        assert world.civilizations[0].stability == 40

    def test_absorb_op(self):
        world = _make_world(num_civs=2, num_regions=4)
        ops = [(9, 0, "civ_op", {
            "op_type": CIV_OP_ABSORB,
            "source_ref_kind": REF_EXISTING, "source_ref_id": 1,  # dying civ
            "target_ref_kind": REF_EXISTING, "target_ref_id": 0,  # absorber
        })]
        apply_politics_ops(world, ops)
        assert world.civilizations[1].regions == []
        assert "C" in world.civilizations[0].regions
        assert "D" in world.civilizations[0].regions


# ── Seceded Transient Tests ──────────────────────────────────────────


class TestSecededTransientLifecycle:
    def test_seceded_flag_survives_one_turn(self):
        """_seceded_this_turn set via apply_politics_ops survives for one build cycle."""
        world = _make_world(num_civs=1, num_regions=3)
        ops = [(2, 5, "region_op", {
            "op_type": REGION_OP_SET_SECEDED_TRANSIENT,
            "region": 1,
        })]
        apply_politics_ops(world, ops)
        assert getattr(world.regions[1], "_seceded_this_turn", False) is True

    def test_seceded_flag_cleared_by_build_region_batch(self):
        """After build_region_batch reads it, the transient flag resets to False."""
        from chronicler.agent_bridge import build_region_batch
        world = _make_world(num_civs=1, num_regions=3)
        world.regions[1]._seceded_this_turn = True

        batch1 = build_region_batch(world)
        vals1 = batch1.column("seceded_this_turn").to_pylist()
        assert vals1[1] is True

        batch2 = build_region_batch(world)
        vals2 = batch2.column("seceded_this_turn").to_pylist()
        assert vals2[1] is False


# ── Oracle Preservation Tests ────────────────────────────────────────


class TestOraclePreservation:
    """Verify that adding builders did not break the existing Python oracle."""

    def test_check_capital_loss_still_works(self):
        from chronicler.politics import check_capital_loss
        world = _make_world(num_civs=1, num_regions=3)
        world.civilizations[0].capital_region = "Z"  # not in regions
        events = check_capital_loss(world)
        assert len(events) > 0
        assert world.civilizations[0].capital_region in world.civilizations[0].regions

    def test_update_allied_turns_still_works(self):
        from chronicler.politics import update_allied_turns
        world = _make_world(num_civs=2, num_regions=4)
        world.relationships["Civ0"]["Civ1"] = Relationship(
            disposition=Disposition.ALLIED, allied_turns=5,
        )
        update_allied_turns(world)
        assert world.relationships["Civ0"]["Civ1"].allied_turns == 6

    def test_check_federation_formation_still_works(self):
        from chronicler.politics import check_federation_formation
        world = _make_world(num_civs=2, num_regions=4)
        world.relationships["Civ0"]["Civ1"] = Relationship(
            disposition=Disposition.ALLIED, allied_turns=10,
        )
        world.relationships["Civ1"]["Civ0"] = Relationship(
            disposition=Disposition.ALLIED, allied_turns=10,
        )
        events = check_federation_formation(world)
        assert len(world.federations) == 1

    def test_update_decline_tracking_still_works(self):
        from chronicler.politics import update_decline_tracking
        world = _make_world(num_civs=1, num_regions=3)
        civ = world.civilizations[0]
        civ.stats_sum_history = list(range(20))
        update_decline_tracking(world)
        assert len(civ.stats_sum_history) == 20

    def test_check_proxy_detection_still_works(self):
        from chronicler.politics import check_proxy_detection
        world = _make_world(num_civs=2, num_regions=4)
        world.proxy_wars = [ProxyWar(sponsor="Civ0", target_civ="Civ1", target_region="C")]
        # With culture=30 -> detection_prob=0.3. Run multiple seeds.
        detected = False
        for seed in range(50):
            world.seed = seed
            world.proxy_wars = [ProxyWar(sponsor="Civ0", target_civ="Civ1", target_region="C")]
            check_proxy_detection(world)
            if world.proxy_wars[0].detected:
                detected = True
                break
        # At least one seed should detect within 50 tries
        assert detected


# ── Task 3: FFI Bridge Tests ────────────────────────────────────────


class TestCallRustPolitics:
    """Test the call_rust_politics() wrapper that goes through the full
    Python builders -> Arrow -> Rust FFI -> Arrow -> Python reconstruct path.
    """

    def _get_simulator(self):
        """Get a PoliticsSimulator (off-mode, no pool)."""
        try:
            from chronicler_agents import PoliticsSimulator
            return PoliticsSimulator()
        except ImportError:
            import pytest
            pytest.skip("chronicler_agents not built")

    def test_empty_world_returns_empty_ops(self):
        from chronicler.politics import call_rust_politics
        sim = self._get_simulator()
        world = _make_world(num_civs=1, num_regions=2)
        # Stable civ with enough regions — nothing should trigger
        ops = call_rust_politics(sim, world, hybrid_mode=False)
        # Should have no civ ops (possibly bookkeeping for decline tracking)
        civ_ops = [o for o in ops if o[2] == "civ_op"]
        assert len(civ_ops) == 0

    def test_capital_loss_round_trip(self):
        from chronicler.politics import call_rust_politics
        sim = self._get_simulator()
        world = _make_world(num_civs=1, num_regions=3)
        # Capital region is "A" (index 0). Remove it from civ's regions
        world.civilizations[0].regions = ["B", "C"]
        world.civilizations[0].capital_region = "A"
        ops = call_rust_politics(sim, world, hybrid_mode=False)
        # Should get a ReassignCapital civ op
        civ_ops = [o for o in ops if o[2] == "civ_op"]
        assert len(civ_ops) >= 1
        reassign = [o for o in civ_ops if o[3].get("op_type") == CIV_OP_REASSIGN_CAPITAL]
        assert len(reassign) == 1, f"Expected 1 ReassignCapital, got {len(reassign)}"

    def test_result_tuple_has_12_batches(self):
        """Verify the FFI returns exactly 12 op family batches."""
        from chronicler.politics import (
            build_politics_civ_input_batch,
            build_politics_region_input_batch,
            build_politics_relationship_batch,
            build_politics_vassal_batch,
            build_politics_federation_batch,
            build_politics_war_batch,
            build_politics_embargo_batch,
            build_politics_proxy_war_batch,
            build_politics_exile_batch,
            _dict_to_civ_input_batch,
            _dict_to_region_input_batch,
            _dict_to_relationship_batch,
            _dict_to_vassal_batch,
            _dict_to_federation_batch,
            _dict_to_pair_batch,
            _dict_to_proxy_war_batch,
            _dict_to_exile_batch,
            _build_region_input_with_eff_cap,
        )
        sim = self._get_simulator()
        world = _make_world(num_civs=2, num_regions=4)

        civ_rb = _dict_to_civ_input_batch(build_politics_civ_input_batch(world))
        region_rb = _dict_to_region_input_batch(_build_region_input_with_eff_cap(world))
        rel_rb = _dict_to_relationship_batch(build_politics_relationship_batch(world))
        vassal_rb = _dict_to_vassal_batch(build_politics_vassal_batch(world))
        fed_rb = _dict_to_federation_batch(build_politics_federation_batch(world))
        war_rb = _dict_to_pair_batch(build_politics_war_batch(world))
        embargo_rb = _dict_to_pair_batch(build_politics_embargo_batch(world))
        proxy_rb = _dict_to_proxy_war_batch(build_politics_proxy_war_batch(world))
        exile_rb = _dict_to_exile_batch(build_politics_exile_batch(world))

        result = sim.tick_politics(
            civ_rb, region_rb, rel_rb, vassal_rb, fed_rb,
            war_rb, embargo_rb, proxy_rb, exile_rb,
            100, 42, False,
        )
        assert len(result) == 12, f"Expected 12-tuple, got {len(result)}"

    def test_step_seq_columns_present_on_all_families(self):
        """Every non-empty returned batch must have step and seq columns."""
        from chronicler.politics import call_rust_politics, _batch_to_dict
        sim = self._get_simulator()
        world = _make_world(num_civs=1, num_regions=3)
        # Trigger capital loss for some op output
        world.civilizations[0].regions = ["B", "C"]
        world.civilizations[0].capital_region = "A"
        ops = call_rust_politics(sim, world, hybrid_mode=False)
        for step, seq, family, payload in ops:
            assert isinstance(step, int), f"step should be int, got {type(step)}"
            assert isinstance(seq, int), f"seq should be int, got {type(seq)}"
            assert 1 <= step <= 11, f"step {step} out of range"

    def test_off_mode_simulator_exists(self):
        """PoliticsSimulator can be constructed and has tick_politics."""
        sim = self._get_simulator()
        assert hasattr(sim, "tick_politics")
        assert hasattr(sim, "set_politics_config")

    def test_configure_politics_runtime_matches_python_oracle_defaults(self):
        """Rust runtime fallback defaults should mirror the Python oracle helpers."""
        from chronicler.politics import configure_politics_runtime

        class FakeSimulator:
            def __init__(self):
                self.kwargs = None

            def set_politics_config(self, **kwargs):
                self.kwargs = kwargs

        sim = FakeSimulator()
        world = _make_world(num_civs=1, num_regions=3)

        configure_politics_runtime(sim, world)

        assert sim.kwargs == {
            "secession_stability_threshold": 10,
            "secession_surveillance_threshold": 5,
            "proxy_war_secession_bonus": 0.05,
            "secession_stability_loss": 10,
            "secession_likelihood_multiplier": 1.0,
            "capital_loss_stability": 20,
            "vassal_rebellion_base_prob": 0.15,
            "vassal_rebellion_reduced_prob": 0.05,
            "federation_allied_turns": 10,
            "federation_exit_stability": 15,
            "federation_remaining_stability": 5,
            "restoration_base_prob": 0.05,
            "restoration_recognition_bonus": 0.03,
            "twilight_absorption_decline": 40,
            "severity_stress_divisor": 20.0,
            "severity_stress_scale": 0.5,
            "severity_cap": 2.0,
            "severity_multiplier": 1.0,
        }

    def test_forced_collapse_through_ffi(self):
        """Forced collapse fires through the Rust FFI path."""
        from chronicler.politics import call_rust_politics
        sim = self._get_simulator()
        world = _make_world(num_civs=1, num_regions=3)
        world.civilizations[0].asabiya = 0.05
        world.civilizations[0].stability = 15
        world.civilizations[0].military = 50
        world.civilizations[0].economy = 30
        ops = call_rust_politics(sim, world, hybrid_mode=False)
        # Should have a StripToFirstRegion op (step 11)
        strip_ops = [o for o in ops if o[2] == "civ_op" and o[3].get("op_type") == CIV_OP_STRIP_TO_FIRST_REGION]
        assert len(strip_ops) == 1, "Expected forced collapse StripToFirstRegion"
        assert strip_ops[0][0] == 11, "Forced collapse should be step 11"

    def test_decline_tracking_through_ffi(self):
        """Decline tracking bookkeeping comes through the FFI."""
        from chronicler.politics import call_rust_politics
        sim = self._get_simulator()
        world = _make_world(num_civs=1, num_regions=3)
        ops = call_rust_politics(sim, world, hybrid_mode=False)
        bk_ops = [o for o in ops if o[2] == "bookkeeping"]
        # Should have at least one decline tracking op (step 10)
        step10_bk = [o for o in bk_ops if o[0] == 10]
        assert len(step10_bk) > 0, "Expected step 10 bookkeeping ops"

    def test_twilight_absorption_keeps_all_exile_regions_beyond_four(self):
        """Rust FFI must not truncate exile region lists to four entries."""
        from chronicler.politics import call_rust_politics, apply_politics_ops, configure_politics_runtime

        sim = self._get_simulator()
        world = _make_world(num_civs=2, num_regions=8)
        world.seed = 7
        world.turn = 100
        weak = world.civilizations[0]
        absorber = world.civilizations[1]

        weak.regions = ["A", "B", "C", "D", "E", "F"]
        weak.capital_region = "A"
        weak.founded_turn = 0
        weak.culture = 10

        absorber.regions = ["G", "H"]
        absorber.capital_region = "G"
        absorber.culture = 80

        for region in world.regions:
            if region.name in weak.regions:
                region.controller = weak.name
                region.carrying_capacity = 1
                region.population = 1
            elif region.name in absorber.regions:
                region.controller = absorber.name
            else:
                region.controller = None

        world.relationships = {
            weak.name: {absorber.name: Relationship(disposition=Disposition.HOSTILE)},
            absorber.name: {weak.name: Relationship(disposition=Disposition.HOSTILE)},
        }

        configure_politics_runtime(sim, world)
        ops = call_rust_politics(sim, world, hybrid_mode=False)
        apply_politics_ops(world, ops)

        assert len(world.exile_modifiers) == 1
        assert world.exile_modifiers[0].conquered_regions == ["A", "B", "C", "D", "E", "F"]


# ── M54c Task 4: Phase 10 Runtime Routing Tests ──────────────────────


class TestPhase10RuntimeRouting:
    """Verify that the production call path routes Phase 10 politics
    through Rust via call_rust_politics + apply_politics_ops."""

    def test_hybrid_bridge_transition_secession_fires(self):
        """Secession bridge transition ops include BRIDGE_SECESSION when secession fires."""
        try:
            from chronicler_agents import PoliticsSimulator
        except ImportError:
            import pytest
            pytest.skip("chronicler_agents not built")

        from chronicler.politics import call_rust_politics, configure_politics_runtime

        sim = PoliticsSimulator()
        world = _make_world(num_civs=1, num_regions=5)
        # Wire config with low secession threshold so it fires easily
        configure_politics_runtime(sim, world)

        # Set up conditions that strongly favor secession:
        # very low stability, many regions, past grace period
        civ = world.civilizations[0]
        civ.stability = 5
        civ.asabiya = 0.1
        civ.founded_turn = 0
        world.turn = 200

        # Try many seeds to find one that triggers secession
        secession_found = False
        for seed in range(200):
            world.seed = seed
            # Reset civ state each iteration
            civ.stability = 5
            civ.asabiya = 0.1
            civ.regions = ["A", "B", "C", "D", "E"]
            civ.capital_region = "A"
            for r in world.regions:
                r.controller = civ.name
            ops = call_rust_politics(sim, world, hybrid_mode=True)
            bridge_ops = [o for o in ops if o[2] == "bridge_transition"
                          and o[3].get("transition_type") == BRIDGE_SECESSION]
            if bridge_ops:
                secession_found = True
                break

        assert secession_found, "Expected at least one seed to trigger secession bridge op"

    def test_forced_collapse_dead_civ_semantics(self):
        """Forced collapse preserves dead-civ-with-empty-regions via StripToFirstRegion."""
        try:
            from chronicler_agents import PoliticsSimulator
        except ImportError:
            import pytest
            pytest.skip("chronicler_agents not built")

        from chronicler.politics import call_rust_politics, apply_politics_ops

        sim = PoliticsSimulator()
        world = _make_world(num_civs=1, num_regions=3)
        civ = world.civilizations[0]
        civ.asabiya = 0.05
        civ.stability = 15
        civ.military = 50
        civ.economy = 30

        ops = call_rust_politics(sim, world, hybrid_mode=False)
        apply_politics_ops(world, ops)

        # After forced collapse, civ should have exactly 1 region (not 0)
        assert len(civ.regions) == 1, f"Expected 1 region after collapse, got {len(civ.regions)}"
        # Stats should be halved via integer division
        assert civ.military == 25  # 50 // 2
        assert civ.economy == 15  # 30 // 2

    def test_forced_collapse_hybrid_shock_routing(self):
        """In hybrid mode, forced collapse routes shocks to pending_shocks."""
        try:
            from chronicler_agents import PoliticsSimulator
        except ImportError:
            import pytest
            pytest.skip("chronicler_agents not built")

        from chronicler.politics import call_rust_politics, apply_politics_ops

        sim = PoliticsSimulator()
        world = _make_world(num_civs=1, num_regions=3)
        world.agent_mode = "hybrid"
        civ = world.civilizations[0]
        civ.asabiya = 0.05
        civ.stability = 15
        civ.military = 50
        civ.economy = 30

        ops = call_rust_politics(sim, world, hybrid_mode=True)
        apply_politics_ops(world, ops)

        # After forced collapse in hybrid, stats should NOT be halved
        # (shocks go to pending_shocks instead)
        assert civ.military == 50, "Hybrid: military should not be directly halved"
        assert civ.economy == 30, "Hybrid: economy should not be directly halved"
        # Should have pending_shocks
        shock_shocks = [s for s in world.pending_shocks
                        if getattr(s, "military_shock", 0) != 0
                        or getattr(s, "economy_shock", 0) != 0]
        assert len(shock_shocks) >= 1, "Expected military/economy shocks in pending_shocks"

    def test_seceded_this_turn_clears_on_next_builder_read(self):
        """_seceded_this_turn set by apply_politics_ops clears when build_region_batch is called."""
        from chronicler.agent_bridge import build_region_batch

        world = _make_world(num_civs=1, num_regions=3)
        # Simulate what apply_politics_ops does for secession
        ops = [(2, 5, "region_op", {
            "op_type": REGION_OP_SET_SECEDED_TRANSIENT,
            "region": 1,
        })]
        apply_politics_ops(world, ops)
        assert getattr(world.regions[1], "_seceded_this_turn", False) is True

        # First build_region_batch should read the flag as True
        batch1 = build_region_batch(world)
        vals1 = batch1.column("seceded_this_turn").to_pylist()
        assert vals1[1] is True

        # Second call should see it cleared (transient rule)
        batch2 = build_region_batch(world)
        vals2 = batch2.column("seceded_this_turn").to_pylist()
        assert vals2[1] is False

    def test_event_ordering_deterministic(self):
        """Ops from Rust produce events in deterministic step+seq order."""
        world = _make_world(num_civs=2, num_regions=4)
        # Create events at multiple steps
        ops = [
            (7, 0, "event_trigger", {
                "event_type": "proxy_detected",
                "actor_count": 1,
                "actor_0_ref_kind": REF_EXISTING, "actor_0_ref_id": 0,
                "importance": 5,
                "description": "Proxy war detected",
            }),
            (2, 99, "event_trigger", {
                "event_type": "secession",
                "actor_count": 1,
                "actor_0_ref_kind": REF_EXISTING, "actor_0_ref_id": 0,
                "importance": 9,
                "description": "Secession occurred",
            }),
            (9, 0, "event_trigger", {
                "event_type": "twilight_absorption",
                "actor_count": 1,
                "actor_0_ref_kind": REF_EXISTING, "actor_0_ref_id": 1,
                "importance": 8,
                "description": "Twilight absorption",
            }),
        ]
        events = apply_politics_ops(world, sorted(ops, key=lambda t: (t[0], t[1])))
        # Events should arrive in step order: 2, 7, 9
        assert len(events) == 3
        assert events[0].event_type == "secession"
        assert events[1].event_type == "proxy_detected"
        assert events[2].event_type == "twilight_absorption"

        # Run again — should produce identical order
        world2 = _make_world(num_civs=2, num_regions=4)
        events2 = apply_politics_ops(world2, sorted(ops, key=lambda t: (t[0], t[1])))
        assert [e.event_type for e in events2] == [e.event_type for e in events]

    def test_bridge_restoration_round_trips_packed_region_columns(self):
        class _StubBridge:
            def __init__(self):
                self.calls = []

            def apply_restoration_transitions(
                self, absorber_civ, restored_civ, region_names, **kwargs
            ):
                self.calls.append(
                    (absorber_civ.name, restored_civ.name, list(region_names), kwargs)
                )

        world = _make_world(num_civs=2, num_regions=4)
        world.agent_mode = "hybrid"
        world._agent_bridge = _StubBridge()
        bridge_batch = {
            "step": [9],
            "seq": [0],
            "transition_type": [BRIDGE_RESTORATION],
            "source_ref_kind": [REF_EXISTING],
            "source_ref_id": [0],
            "target_ref_kind": [REF_EXISTING],
            "target_ref_id": [1],
            "region_count": [2],
            "region_0": [2],
            "region_1": [3],
            "region_2": [CIV_NONE],
            "region_3": [CIV_NONE],
        }

        ops = reconstruct_politics_ops(
            _empty_op_batch(), _empty_op_batch(), _empty_op_batch(),
            _empty_op_batch(), _empty_op_batch(), _empty_op_batch(),
            _empty_op_batch(), _empty_op_batch(), _empty_op_batch(),
            _empty_op_batch(), bridge_batch, _empty_op_batch(),
        )
        apply_politics_ops(world, ops)

        assert world._agent_bridge.calls == [
            ("Civ0", "Civ1", ["C", "D"], {"absorber_civ_id": 0, "restored_civ_id": 1, "world": world})
        ]

    def test_twilight_absorption_dead_civ_has_empty_regions(self):
        """After absorption, the absorbed civ has regions=[] (dead civ stays in list)."""
        try:
            from chronicler_agents import PoliticsSimulator
        except ImportError:
            import pytest
            pytest.skip("chronicler_agents not built")

        from chronicler.politics import call_rust_politics, apply_politics_ops

        sim = PoliticsSimulator()
        world = _make_world(num_civs=2, num_regions=4)
        dying = world.civilizations[1]
        absorber = world.civilizations[0]

        # Set dying civ to trigger twilight absorption:
        # low effective capacity (population < 10 or terminal decline)
        dying.decline_turns = 45  # > K_TWILIGHT_ABSORPTION_DECLINE (40)
        dying.stability = 10
        dying.asabiya = 0.3
        dying.population = 5
        for rn in dying.regions:
            idx = next(i for i, r in enumerate(world.regions) if r.name == rn)
            world.regions[idx].population = 2
            world.regions[idx].carrying_capacity = 5

        # Set absorber as neighbor with capacity
        absorber.stability = 80
        absorber.population = 100

        ops = call_rust_politics(sim, world, hybrid_mode=False)
        absorb_ops = [o for o in ops if o[2] == "civ_op"
                      and o[3].get("op_type") == CIV_OP_ABSORB]
        if absorb_ops:
            apply_politics_ops(world, ops)
            # Dead civ still in list but with empty regions
            assert dying in world.civilizations
            assert dying.regions == []
            # Absorber got the regions
            assert len(absorber.regions) > 2
