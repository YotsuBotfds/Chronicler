"""Read-only snapshot-to-campaign admission seam. No worlds, RNG or native calls.

Real Arrow tables carry the 24-field native schema (``movement_id`` appended
last by the agent movements) and the existing
three-region adjacency from ``chronicler-agents/tests/test_behavior.rs:63-65``.
Soldier/civ selection, kits, morale and stocks are explicit caller data, and
the reviewed ``chronicler.campaign_logistics.admit`` seam stays the only place a
campaign state is created.
"""

from __future__ import annotations

from collections.abc import Mapping
import ast
from dataclasses import FrozenInstanceError, fields, is_dataclass, replace
import gc
import hashlib
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
import weakref

import pyarrow as pa
import pytest

from chronicler.bridge_contract import SNAPSHOT_FIELD_NAMES, SNAPSHOT_SCHEMA
from chronicler.campaign_logistics import (
    ORDERING, Policy, Region, Session, Soldier, Stock, Topology, admit, canonical_bytes,
)
from chronicler.campaign_snapshot_adapter import (
    ADAPTER, CONTRACT, DEMANDED_COLUMNS, MORALE_LIMIT, SOLDIER_OCCUPATION,
    AdmissionPlan, CampaignSnapshotError, RegionBinding, SourceIdentity,
    admit_snapshot_plan, parse_side_inputs, plan_bytes, plan_document,
)
from chronicler.turn_artifacts import AgentRows, Stamp, TurnObservation

# Reused existing snapshot-contract test doubles and helpers.
from test_turn_artifact_views import CountingBatch, rows_for

STAGE = "phase10_entry"

ROOT = Path(__file__).resolve().parents[1]
DRIVER = ROOT / "scripts" / "campaign_snapshot_plan.py"
DEMO = runpy.run_path(str(DRIVER))

FARMER, MERCHANT = 0, 2
SOLDIER = SOLDIER_OCCUPATION

# The existing reviewed demo's illustrative policy, reused unchanged as caller data.
DEMO_POLICY = Policy("m60a-demo-illustrative-v1", ration_demand=1, carried_limit=8,
                     distance_stress=10, unreachable_stress=100, hunger_stress=120,
                     needs_stress=100, information_stress=80, morale_recovery=20,
                     desertion_threshold=200, desertion_chance=5000,
                     movement_min_morale=100, require_full_rations=True)
assert DEMO_POLICY == Policy("m60a-demo-illustrative-v1", 1, 8, 10, 100, 120, 100, 80, 20,
                             200, 5000, 100, True)


# Existing three-region adjacency, id-stable bindings only. Region 0 connects to
# 1 and 2; 1 and 2 connect only to 0 (test_behavior.rs:63-65).
BINDINGS = (
    RegionBinding(0, "r0", ("r1", "r2")),
    RegionBinding(1, "r1", ("r0",)),
    RegionBinding(2, "r2", ("r0",)),
)
TOPOLOGY_VERSION = "existing-three-region-v1"
# Every roster id a negative case may select, so plan_for can supply valid side
# values without indexing a table that lacks the id. Negative tests pass their
# own kits/morale when they want a specific one.
DEFAULT_SIDE_VALUES = (7, 8, 9, 10, 11, 99)


def rows(*, ids, regions, civs, occupations, extra=None):
    """One real Arrow record batch over the 24-field native schema.

    ``extra`` fills only fields outside the four demanded columns, so an
    ordinary table stays a plausible native capture.
    """
    assert len(SNAPSHOT_FIELD_NAMES) == 24
    assert not set(extra or {}) & set(DEMANDED_COLUMNS)
    count = len(ids)
    data = {
        "id": pa.array(ids, type=pa.uint32()),
        "region": pa.array(regions, type=pa.uint16()),
        "civ_affinity": pa.array(civs, type=pa.uint8()),
        "occupation": pa.array(occupations, type=pa.uint8()),
    }
    for field in SNAPSHOT_SCHEMA:
        if field.name not in data:
            filler = extra or {}
            data[field.name] = pa.array([filler.get(field.name, 0)] * count, type=field.type)
    return pa.record_batch([data[name] for name in SNAPSHOT_FIELD_NAMES],
                           schema=SNAPSHOT_SCHEMA)


def snapshot():
    # Agent 7: civ 1 soldier in region 0. Agent 8: civ 1 soldier in region 1.
    # Agent 9: civ 0 farmer. Agent 10: civ 1 merchant. Agent 11: civ 2 soldier.
    return rows(ids=[7, 8, 9, 10, 11], regions=[0, 1, 2, 0, 1],
                civs=[1, 1, 0, 1, 2], occupations=[SOLDIER, SOLDIER, FARMER, MERCHANT, SOLDIER])


def view(batch=None, turn=7):
    return AgentRows(Stamp(turn, "phase10_entry"), batch if batch is not None else snapshot())


def forced_stamp(source_turn, stage):
    """A Stamp built past its own stage check, to reach the adapter's re-check."""
    stamp = Stamp.__new__(Stamp)
    object.__setattr__(stamp, "source_turn", source_turn)
    object.__setattr__(stamp, "stage", stage)
    return stamp


def write_snapshot(directory, batch=None):
    """Write one explicit Arrow IPC snapshot file holding a single record batch."""
    path = directory / "snapshot.arrow"
    with pa.OSFile(str(path), "wb") as sink:
        with pa.ipc.new_file(sink, SNAPSHOT_SCHEMA) as writer:
            writer.write_batch(batch if batch is not None else snapshot())
    return path


def plan_for(rows_view=None, **overrides):
    """Default valid call; kits/morale follow the selected roster unless given.

    Omitting them here keeps each test focused on the argument it varies; the
    adapter itself always requires them explicitly. Side values are valid for
    every known roster id, so a negative case reaches the adapter's own check
    instead of tripping over this helper's fixture.
    """
    selected = overrides.get("selected_ids", (7, 8))
    parameters = dict(
        agent_rows=rows_view if rows_view is not None else view(),
        expected_source_turn=7, civ_id=1, selected_ids=selected,
        region_bindings=BINDINGS, topology_version=TOPOLOGY_VERSION,
        policy=DEMO_POLICY, campaign_id="snapshot-plan", staging=1, target=2,
        kits={agent: 8 for agent in selected},
        morale={agent: 800 for agent in selected},
        stocks={0: 0, 1: 0, 2: 4},
    )
    # Extra keys for unknown ids are harmless: the adapter rejects them on its own
    # coverage check, so a negative case still reaches the adapter, not this helper.
    parameters.update(overrides)
    return admit_snapshot_plan(**parameters)


# ---------------------------------------------------------------- complete plan

def test_plan_admits_through_the_public_kernel_seam_and_is_complete():
    plan = plan_for()
    roster = (Soldier(7, 0, 8, 800), Soldier(8, 1, 8, 800))
    direct = admit(policy=DEMO_POLICY,
                   topology=Topology(TOPOLOGY_VERSION, (Region(0, (1, 2)), Region(1, (0,)),
                                                        Region(2, (0,)))),
                   campaign_id="snapshot-plan", turn=7, staging=1, target=2, soldiers=roster,
                   stocks=(Stock(0, 0), Stock(1, 0), Stock(2, 4)))
    assert plan.session == direct
    assert plan.soldiers == roster
    assert plan.stocks == (Stock(0, 0), Stock(1, 0), Stock(2, 4))
    assert plan.kits == ((7, 8), (8, 8))
    assert plan.morale == ((7, 800), (8, 800))
    assert plan.selected_ids == (7, 8)
    assert plan.admission_turn == 7 and plan.staging == 1 and plan.target == 2
    assert plan.civ_id == 1 and plan.campaign_id == "snapshot-plan"
    assert plan.region_bindings == BINDINGS
    assert plan.topology == Topology(TOPOLOGY_VERSION, (Region(0, (1, 2)), Region(1, (0,)),
                                                        Region(2, (0,))))
    assert plan.policy == DEMO_POLICY and plan.session.cursor.receipts == ()
    assert plan.initial_state_digest == plan.session.cursor.initial_state_digest
    document = plan_document(plan)
    assert document["plan_digest"] == plan.plan_digest
    assert document["admission"]["phase"] == "rally"
    assert document["admission"]["cursor_receipts"] == 0
    assert document["source"]["columns"] == list(DEMANDED_COLUMNS)
    assert document["inputs"]["kits"] == [[7, 8], [8, 8]]
    assert document["inputs"]["region_bindings"] == [
        {"name": "r0", "neighbors": ["r1", "r2"], "region_id": 0},
        {"name": "r1", "neighbors": ["r0"], "region_id": 1},
        {"name": "r2", "neighbors": ["r0"], "region_id": 2}]
    assert document["inputs"]["policy"] == plain_json(DEMO_POLICY)
    assert document["inputs"]["selected_ids"] == [7, 8]
    assert document["admission"]["soldiers"] == [
        {"agent_id": 7, "morale": 800, "rations": 8, "region": 0, "role": "soldier",
         "status": "active"},
        {"agent_id": 8, "morale": 800, "rations": 8, "region": 1, "role": "soldier",
         "status": "active"}]
    assert document["admission"]["topology_regions"] == [[0, [1, 2]], [1, [0]], [2, [0]]]
    assert document["admission"]["policy_digest"] == plan.session.state.policy_digest
    assert document["admission"]["topology_digest"] == plan.session.state.topology_digest
    # The admitted state carries the reviewed kernel's own contract, not this lane's.
    assert document["admission"]["contract"] == "chronicler-m60a-detached-v1"
    assert document["contract"] == CONTRACT
    assert json.loads(plan_bytes(plan).decode()) == document


def test_admission_matches_public_kernel_with_large_sandbox_stock():
    # Sandbox stocks are caller data, so a large value must survive the whole
    # seam: the adapter copies it, the kernel admits it, the plan reports it.
    stocks = {0: 2 ** 120, 1: 0, 2: 4}
    admitted = plan_for(stocks=stocks)
    direct = admit(policy=DEMO_POLICY,
                   topology=Topology(TOPOLOGY_VERSION, (Region(0, (1, 2)), Region(1, (0,)),
                                                        Region(2, (0,)))),
                   campaign_id="snapshot-plan", turn=7, staging=1, target=2,
                   soldiers=(Soldier(7, 0, 8, 800), Soldier(8, 1, 8, 800)),
                   stocks=tuple(Stock(region, rations) for region, rations in stocks.items()))
    assert admitted.session == direct
    assert admitted.stocks[0] == Stock(0, 2 ** 120)
    assert plan_document(admitted)["inputs"]["stocks"][0] == [0, 2 ** 120]
    assert plan_document(admitted)["admission"]["initial_food"] == 2 ** 120 + 20


def test_plan_digest_covers_the_canonical_body_and_provenance():
    plan = plan_for()
    assert plan.plan_digest == plan_for().plan_digest
    changed = (plan_for(kits={7: 8, 8: 7}), plan_for(morale={7: 800, 8: 780}),
               plan_for(stocks={0: 1, 1: 0, 2: 4}),
               plan_for(civ_id=1, selected_ids=(7,)),
               plan_for(campaign_id="other"), plan_for(view(turn=8), expected_source_turn=8),
               plan_for(staging=0, target=2),
               plan_for(topology_version="other-three-region-v1"),
               plan_for(policy=replace(DEMO_POLICY, version="other-v1")))
    assert all(other.plan_digest != plan.plan_digest for other in changed)
    # Selection and binding order are canonicalized, not hashed as given.
    assert plan_for(civ_id=1, selected_ids=(8, 7)).plan_digest == plan.plan_digest
    # The digest is exactly sha256 over the canonical body, and excludes itself,
    # so a caller can verify it from the emitted document alone.
    body = {key: value for key, value in plan_document(plan).items() if key != "plan_digest"}
    assert plan.plan_digest == hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    assert hashlib.sha256(plan_bytes(plan)).hexdigest() != plan.plan_digest


def test_plan_document_equals_the_emitted_json_value():
    # plan_document is the plain-data view of the emitted bytes, so a caller can
    # compare or store either without a conversion step.
    plan = plan_for()
    document = plan_document(plan)
    assert json.loads(plan_bytes(plan)) == document
    # Tuple-valued record fields appear as JSON arrays, not as tuples.
    assert document["inputs"]["policy"]["ordering"] == list(ORDERING)
    assert isinstance(document["inputs"]["policy"]["ordering"], list)
    assert all(type(value) is str for value in document["inputs"]["policy"]["ordering"])
    assert isinstance(document["inputs"]["selected_ids"], list)
    # The plan's own records stay tuples; only the document view is plain.
    assert isinstance(plan.policy.ordering, tuple)
    for policy_change in ({}, {"carried_limit": 20000}, {"ration_demand": 3, "carried_limit": 12}):
        other = plan_for(policy=replace(DEMO_POLICY, **policy_change))
        assert json.loads(plan_bytes(other)) == plan_document(other)


def test_plan_is_frozen_immutable_and_copies_its_inputs():
    plan = plan_for()
    with pytest.raises(FrozenInstanceError):
        plan.selected_ids = (8,)
    with pytest.raises(FrozenInstanceError):
        plan.session.state.turn = 99
    with pytest.raises(TypeError):
        plan.kits[0][1] = 1
    assert isinstance(plan, AdmissionPlan)
    document = plan_document(plan)
    assert plan_bytes(plan) == json.dumps(document, sort_keys=True,
                                          separators=(",", ":")).encode()
    # The record set is exactly the reviewed kernel plus this lane's own records.
    assert {field.name for field in fields(AdmissionPlan)} == set(AdmissionPlan.__slots__)
    # The plan holds its own policy copy, not the caller's record.
    assert plan.policy == DEMO_POLICY and plan.policy is not DEMO_POLICY
    # The admitted soldiers are the kernel's own records, not rebuilt copies.
    assert all(isinstance(soldier, Soldier) for soldier in plan.soldiers)
    assert all(isinstance(stock, Stock) for stock in plan.stocks)
    assert isinstance(plan.policy, Policy) and isinstance(plan.topology, Topology)


# ------------------------------------------------------------------- selection

def test_selection_takes_only_explicit_soldier_ids_of_the_explicit_civ():
    plan = plan_for()
    assert plan.selected_ids == (7, 8)
    single = plan_for(selected_ids=(8,))
    assert single.selected_ids == (8,) and single.soldiers == (Soldier(8, 1, 8, 800),)
    assert single.kits == ((8, 8),) and single.morale == ((8, 800),)
    assert single.session.state.original_ids == (8,)
    # Agent 9 is a farmer and 10 a merchant, so neither can be enlisted as a soldier.
    for selected, message in (((9,), "not a native soldier"), ((10,), "not a native soldier")):
        with pytest.raises(CampaignSnapshotError, match=message):
            plan_for(selected_ids=selected)
    # Agent 11 is a soldier, but of another civ.
    with pytest.raises(CampaignSnapshotError, match="civ affinity"):
        plan_for(selected_ids=(11,))
    with pytest.raises(CampaignSnapshotError, match="civ affinity"):
        plan_for(civ_id=2, selected_ids=(7,))
    assert plan_for(civ_id=2, selected_ids=(11,)).soldiers == (Soldier(11, 1, 8, 800),)


def test_duplicate_and_missing_ids_are_rejected():
    with pytest.raises(CampaignSnapshotError, match="absent"):
        plan_for(selected_ids=(7, 99))
    with pytest.raises(CampaignSnapshotError, match="must be unique"):
        plan_for(selected_ids=(7, 7))
    duplicated = rows(ids=[7, 7], regions=[0, 0], civs=[1, 1], occupations=[SOLDIER, SOLDIER])
    with pytest.raises(CampaignSnapshotError, match="ids must be unique"):
        plan_for(view(duplicated), selected_ids=(7,), kits={7: 8}, morale={7: 800})
    with pytest.raises(CampaignSnapshotError, match="nonempty"):
        plan_for(selected_ids=())
    with pytest.raises(CampaignSnapshotError, match="native id domain"):
        plan_for(selected_ids=(2 ** 32,))
    with pytest.raises(CampaignSnapshotError, match="nonempty tuple"):
        plan_for(selected_ids=[7])
    # A selected id present once but not as a soldier is a role rejection, not an
    # absence: the row was found and read.
    with pytest.raises(CampaignSnapshotError, match="not a native soldier"):
        plan_for(selected_ids=(9,))
    # A selected region that is not bound is rejected for the selected row only.
    with pytest.raises(CampaignSnapshotError, match="unbound region"):
        plan_for(view(rows(ids=[7], regions=[9], civs=[1], occupations=[SOLDIER])),
                  selected_ids=(7,), kits={7: 8}, morale={7: 800})


def test_zero_row_snapshot_has_no_admissible_roster():
    # A real Arrow table: a valid 24-field schema with zero rows.
    empty = rows(ids=[], regions=[], civs=[], occupations=[])
    assert empty.num_rows == 0
    with pytest.raises(CampaignSnapshotError, match="absent"):
        plan_for(view(empty), selected_ids=(7,))
    with pytest.raises(CampaignSnapshotError, match="nonempty"):
        plan_for(view(empty), selected_ids=())
    # Even with an empty roster the bounds check and ratchet run first.
    with pytest.raises(CampaignSnapshotError, match="civ id"):
        plan_for(view(empty), selected_ids=(), civ_id=-1)


# ----------------------------------------------------------------- schema gate

# The last field (``movement_id``) is the one a capture written before agent
# movements lacks; that layout stays valid (test_bridge_contract).
@pytest.mark.parametrize("name", SNAPSHOT_FIELD_NAMES[:-1])
def test_exact_snapshot_schema_ratchet_rejects_a_missing_field(name):
    # Zero rows and a missing field: the reviewed ratchet rejects the schema
    # itself, so a partial capture can never be planned from.
    schema = pa.schema([field for field in SNAPSHOT_SCHEMA if field.name != name])
    batch = pa.record_batch([pa.array([], type=field.type) for field in schema], schema=schema)
    with pytest.raises(KeyError, match=name):
        plan_for(view(batch))


class SchemaBatch:
    """Batch double exposing a malformed schema and refusing every value read.

    The ratchet runs before any decode, so these cases need no Arrow arrays:
    a column access here would itself fail the test.
    """

    def __init__(self, schema, num_rows=5):
        self.schema, self.num_rows = schema, num_rows
        self.accesses = []

    def column(self, name):
        self.accesses.append(name)
        raise AssertionError(f"value decoded before the schema ratchet rejected: {name}")


@pytest.mark.parametrize("schema, error, message", [
    (SNAPSHOT_SCHEMA.append(pa.field("future_field", pa.uint8())), ValueError, "unexpected"),
    (pa.schema(list(SNAPSHOT_SCHEMA)[::-1]), ValueError, "order"),
    (SNAPSHOT_SCHEMA.set(3, SNAPSHOT_SCHEMA.field("civ_affinity").with_nullable(True)),
     ValueError, "non-nullable"),
    (SNAPSHOT_SCHEMA.set(4, pa.field("occupation", pa.int64(), nullable=False)),
     TypeError, "occupation"),
    (SNAPSHOT_SCHEMA.set(0, pa.field("id", pa.int64(), nullable=False)), TypeError, "id"),
    (SNAPSHOT_SCHEMA.set(1, pa.field("region", pa.uint8(), nullable=False)), TypeError, "region"),
    (SNAPSHOT_SCHEMA.set(3, pa.field("civ_affinity", pa.uint16(), nullable=False)),
     TypeError, "civ_affinity"),
    (SNAPSHOT_SCHEMA.append(SNAPSHOT_SCHEMA.field("id")), ValueError, "duplicate"),
])
def test_exact_schema_ratchet_rejects_malformed_snapshots(schema, error, message):
    batch = SchemaBatch(schema)
    with pytest.raises(error, match=message):
        plan_for(view(batch))
    assert batch.accesses == []


class DecodedBatch:
    """Schema-real batch double yielding arbitrary Python values on demand.

    Real Arrow arrays cannot hold nulls or floats in a non-nullable integer
    column, so the uncoerced ``to_pylist`` decode is the only honest place to
    exercise the adapter's value-domain checks.
    """

    def __init__(self, batch, values):
        self.batch, self.schema, self.num_rows = batch, batch.schema, batch.num_rows
        self.values = values

    def column(self, name):
        owner = self

        class Column:
            def to_pylist(self):
                return list(owner.values[name])

        return Column()


@pytest.mark.parametrize("column, value, message", [
    ("id", None, "null or not an exact integer"),
    ("id", 1.0, "null or not an exact integer"),
    ("occupation", True, "null or not an exact integer"),
    ("civ_affinity", "1", "null or not an exact integer"),
    ("region", -1, "native domain"),
    ("region", 2 ** 16, "native domain"),
    ("occupation", 2 ** 8, "native domain"),
    ("id", 2 ** 32, "native domain"),
])
def test_null_and_wrong_typed_identity_values_are_rejected(column, value, message):
    base = {"id": [7], "region": [0], "civ_affinity": [1], "occupation": [SOLDIER]}
    probe = DecodedBatch(rows(ids=[7], regions=[0], civs=[1], occupations=[SOLDIER]),
                         dict(base, **{column: [value]}))
    with pytest.raises(CampaignSnapshotError, match=message):
        plan_for(view(probe), selected_ids=(7,), kits={7: 8}, morale={7: 800})


def test_misaligned_or_misreported_row_counts_are_rejected():
    batch = rows(ids=[7, 8], regions=[0, 1], civs=[1, 1], occupations=[SOLDIER, SOLDIER])
    aligned = {"id": [7, 8], "region": [0, 1], "civ_affinity": [1, 1],
               "occupation": [SOLDIER, SOLDIER]}
    ragged = DecodedBatch(batch, dict(aligned, region=[0]))
    with pytest.raises(CampaignSnapshotError, match="misaligned"):
        plan_for(view(ragged), selected_ids=(7,), kits={7: 8}, morale={7: 800})
    lying = DecodedBatch(batch, aligned)
    lying.num_rows = 3
    with pytest.raises(CampaignSnapshotError, match="reports 3"):
        plan_for(view(lying), selected_ids=(7,), kits={7: 8}, morale={7: 800})


@pytest.mark.parametrize("field, value, message", [
    ("region", 9, "unbound region"),
    ("occupation", FARMER, "not a native soldier"),
    ("civ_affinity", 3, "civ affinity"),
])
def test_illegal_row_domain_role_and_region_are_rejected(field, value, message):
    data = {"id": 7, "region": 0, "civ_affinity": 1, "occupation": SOLDIER}
    data[field] = value
    batch = rows(ids=[data["id"]], regions=[data["region"]], civs=[data["civ_affinity"]],
                 occupations=[data["occupation"]])
    with pytest.raises(CampaignSnapshotError, match=message):
        plan_for(view(batch), selected_ids=(7,), kits={7: 8}, morale={7: 800})


def test_unselected_illegal_rows_are_never_read_or_validated():
    # Agent 99 is a non-soldier of another civ in an unbound region: unselected
    # rows are not this boundary's business.
    batch = rows(ids=[7, 99], regions=[0, 40000], civs=[1, 4],
                 occupations=[SOLDIER, FARMER])
    plan = plan_for(view(batch), selected_ids=(7,), kits={7: 8}, morale={7: 800})
    assert plan.soldiers == (Soldier(7, 0, 8, 800),)
    assert plan.source.row_count == 2


# ------------------------------------------------------------ provenance/epoch

def test_source_turn_must_match_the_explicit_expectation():
    with pytest.raises(CampaignSnapshotError, match="does not match"):
        plan_for(view(turn=7), expected_source_turn=8)
    with pytest.raises(CampaignSnapshotError, match="does not match"):
        plan_for(view(turn=7), expected_source_turn=6)
    # N versus N+1: a N+1 completed-turn label is not a source turn here.
    observation = TurnObservation(7, 8, view())
    assert observation.completed_turn == 8
    with pytest.raises(CampaignSnapshotError, match="does not match"):
        plan_for(agent_rows=observation.phase10_agents, expected_source_turn=8)
    plan = plan_for(agent_rows=observation.phase10_agents, expected_source_turn=7)
    assert plan.source.source_turn == 7 and plan.admission_turn == 7
    with pytest.raises(ValueError):
        TurnObservation(7, 7, view())


def test_provenance_identity_scopes_only_the_demanded_columns():
    plan = plan_for()
    assert plan.source.contract == CONTRACT and plan.source.adapter == ADAPTER
    assert plan.source.stage == STAGE and plan.source.row_count == 5
    assert plan.source.columns == DEMANDED_COLUMNS
    assert [name for name, _ in plan.source.column_digests] == list(DEMANDED_COLUMNS)
    assert all(len(digest) == 64 for _, digest in plan.source.column_digests)
    assert len(plan.source.content_digest) == 64
    # Undemanded native fields cannot change the recorded source identity: the
    # snapshot carries no ration, morale, needs, stock, quality or memome column.
    other = rows(ids=[7, 8, 9, 10, 11], regions=[0, 1, 2, 0, 1],
                 civs=[1, 1, 0, 1, 2], occupations=[SOLDIER, SOLDIER, FARMER, MERCHANT, SOLDIER],
                 extra={"wealth": 4.5, "belief": 3, "loyalty": 0.25, "satisfaction": 0.5})
    assert plan_for(view(other)).source == plan.source
    assert not {"rations", "morale", "unmet_needs", "information_quality", "stock",
                "stockpile", "memome"} & set(SNAPSHOT_FIELD_NAMES)
    # Arrow row order is not part of what was read: stable ids are.
    reordered = rows(ids=[11, 9, 8, 10, 7], regions=[1, 2, 1, 0, 0],
                     civs=[2, 0, 1, 1, 1],
                     occupations=[SOLDIER, FARMER, SOLDIER, MERCHANT, SOLDIER])
    assert plan_for(view(reordered)).source == plan.source
    assert plan_for(view(reordered)).plan_digest == plan.plan_digest
    # A real content change in a demanded column does change the identity.
    moved = rows(ids=[7, 8, 9, 10, 11], regions=[0, 2, 2, 0, 1],
                 civs=[1, 1, 0, 1, 2], occupations=[SOLDIER, SOLDIER, FARMER, MERCHANT, SOLDIER])
    assert plan_for(view(moved)).source != plan.source


def test_content_identity_covers_the_whole_demanded_table_not_just_the_roster():
    # The identity covers all rows of the four demanded columns, including the
    # unselected ones, so a change to an unselected row is still visible.
    base = rows(ids=[7, 8, 9], regions=[0, 1, 2], civs=[1, 1, 1],
                occupations=[SOLDIER, SOLDIER, FARMER])
    original = plan_for(view(base))
    moved_unselected = plan_for(view(rows(ids=[7, 8, 9], regions=[0, 1, 0], civs=[1, 1, 1],
                                          occupations=[SOLDIER, SOLDIER, FARMER])))
    assert original.soldiers == moved_unselected.soldiers
    assert original.session == moved_unselected.session
    assert original.source.content_digest != moved_unselected.source.content_digest
    # Semantic bound-region/role/civ checks cover the selected roster only.
    unbound_unselected = plan_for(view(rows(ids=[7, 8, 9], regions=[0, 1, 40000],
                                           civs=[1, 1, 1],
                                           occupations=[SOLDIER, SOLDIER, FARMER])))
    assert unbound_unselected.soldiers == original.soldiers


# ---------------------------------------------------------- region stability

def test_binding_and_neighbor_order_cannot_remap_region_ids():
    assert plan_for().region_bindings == BINDINGS
    reordered = plan_for(region_bindings=tuple(reversed(BINDINGS)))
    assert reordered.region_bindings == BINDINGS
    assert reordered.plan_digest == plan_for().plan_digest
    neighbor_swap = plan_for(region_bindings=(
        RegionBinding(0, "r0", ("r2", "r1")), RegionBinding(1, "r1", ("r0",)),
        RegionBinding(2, "r2", ("r0",))))
    assert neighbor_swap.plan_digest == plan_for().plan_digest
    assert neighbor_swap.topology.regions == plan_for().topology.regions
    # Names are labels only: they appear in the plan but never remap region ids,
    # so relabelling changes the recorded bindings and nothing else.
    relabelled = plan_for(region_bindings=(
        RegionBinding(0, "r0", ("r2", "r1")), RegionBinding(1, "r2", ("r0",)),
        RegionBinding(2, "r1", ("r0",))))
    assert relabelled.plan_digest != plan_for().plan_digest
    assert relabelled.topology == plan_for().topology
    assert relabelled.soldiers == plan_for().soldiers
    assert relabelled.source == plan_for().source
    assert relabelled.region_binding_digest != plan_for().region_binding_digest
    # The kernel records the topology version, so it travels with the graph.
    assert relabelled.session.state.topology_id == TOPOLOGY_VERSION


def test_region_binding_records_reject_malformed_construction():
    # A binding that cannot describe a stable region never becomes a record.
    for arguments, message in (
        (((0, "r0", ["r1"]),), "immutable tuple"),
        (((0, "r0", ("r0",)),), "cannot neighbor itself"),
        (((0, "r0", ("r1", "r1")),), "duplicate neighbor"),
        (((0, "", ()),), "nonempty string"),
        (((0, "r0", ("",)),), "nonempty string"),
        (((-1, "r0", ()),), "nonnegative"),
        (((0, 3, ()),), "nonempty string"),
        (((0, "r0", 7),), "immutable tuple"),
    ):
        with pytest.raises(CampaignSnapshotError, match=message):
            RegionBinding(*arguments[0])


def test_bindings_reject_unknown_asymmetric_and_malformed_graph_references():
    # An unknown neighbor name is an unknown reference, not an asymmetry: the
    # name cannot resolve to a bound region at all.
    with pytest.raises(CampaignSnapshotError, match="unknown region 'absent'"):
        plan_for(region_bindings=(RegionBinding(0, "r0", ("absent",)),))
    with pytest.raises(CampaignSnapshotError, match="unknown region 'absent'"):
        plan_for(region_bindings=(RegionBinding(0, "r0", ("absent",)),
                                  RegionBinding(1, "r1", ("r0",)),
                                  RegionBinding(2, "r2", ("r0",))))
    # A real one-way edge is the reciprocity failure.
    for bindings in (
        (RegionBinding(0, "r0", ("r1",)), RegionBinding(1, "r1", ())),
        (RegionBinding(0, "r0", ("r1", "r2")), RegionBinding(1, "r1", ("r0",)),
         RegionBinding(2, "r2", ())),
        (RegionBinding(0, "r0", ("r1",)), RegionBinding(1, "r1", ("r0",)),
         RegionBinding(2, "r2", ("r0",))),
    ):
        with pytest.raises(CampaignSnapshotError, match="reciprocal"):
            plan_for(region_bindings=bindings)
    # An isolated region is legal: the kernel permits a disconnected graph, and
    # an unreachable objective is a reason-coded stall, not a rejection.
    isolated = plan_for(region_bindings=(RegionBinding(0, "r0", ("r1",)),
                                        RegionBinding(1, "r1", ("r0",)),
                                        RegionBinding(2, "r2", ())))
    assert isolated.topology.regions == (Region(0, (1,)), Region(1, (0,)), Region(2, ()))
    with pytest.raises(CampaignSnapshotError, match="native region domain"):
        plan_for(region_bindings=(RegionBinding(70000, "rX", ()),))
    with pytest.raises(CampaignSnapshotError, match="duplicate region binding id"):
        plan_for(region_bindings=(RegionBinding(0, "a", ()), RegionBinding(0, "b", ())))
    with pytest.raises(CampaignSnapshotError, match="duplicate region binding name"):
        plan_for(region_bindings=(RegionBinding(0, "a", ()), RegionBinding(1, "a", ())))
    with pytest.raises(CampaignSnapshotError, match="nonempty tuple"):
        plan_for(region_bindings=())
    with pytest.raises(CampaignSnapshotError, match="RegionBinding"):
        plan_for(region_bindings=(("r0", 0, ("r1",)),))
    with pytest.raises(CampaignSnapshotError, match="RegionBinding"):
        plan_for(region_bindings=[RegionBinding(0, "r0", ())])
    with pytest.raises(CampaignSnapshotError, match="staging region"):
        plan_for(staging=9)
    with pytest.raises(CampaignSnapshotError, match="target region"):
        plan_for(target=9)
    with pytest.raises(CampaignSnapshotError, match="topology version"):
        plan_for(topology_version=" ")


def test_adjacency_comes_from_bindings_not_trade_routes_or_display_hashes():
    plan = plan_for()
    assert plan.topology == Topology(TOPOLOGY_VERSION, (Region(0, (1, 2)), Region(1, (0,)),
                                                        Region(2, (0,))))
    # A chain with no direct edge between staging and target still admits: only the
    # supplied bindings define the graph, and no arbitrary distance cap appears.
    chain = plan_for(region_bindings=(RegionBinding(0, "r0", ("r1",)),
                                      RegionBinding(1, "r1", ("r0", "r2")),
                                      RegionBinding(2, "r2", ("r1",))))
    assert chain.topology.regions == (Region(0, (1,)), Region(1, (0, 2)), Region(2, (1,)))
    assert chain.selected_ids == (7, 8)
    assert chain.soldiers == (Soldier(7, 0, 8, 800), Soldier(8, 1, 8, 800))
    # A name that merely looks like an id changes nothing about region identity.
    numeric_names = plan_for(region_bindings=(
        RegionBinding(0, "0", ("1", "2")), RegionBinding(1, "1", ("0",)),
        RegionBinding(2, "2", ("0",))))
    assert numeric_names.topology == plan_for().topology


# ------------------------------------------------------------- explicit inputs

def test_snapshot_source_turn_must_be_an_exact_nonnegative_integer():
    class TurnChild(int):
        """An int subclass compares equal to its value but is not an exact int."""

    # Stamp validates the stage but not the turn, so equality alone would let a
    # lossy turn value match an exact expectation and be recorded as if exact.
    for turn in (True, 1.0, TurnChild(7), -1, "7"):
        with pytest.raises(CampaignSnapshotError, match="nonnegative exact integer"):
            plan_for(AgentRows(Stamp(turn, STAGE), snapshot()), expected_source_turn=7)
    # The expectation itself has the same domain.
    for expected in (True, 7.0, -1, "7"):
        with pytest.raises(CampaignSnapshotError, match="expected source turn"):
            plan_for(expected_source_turn=expected)
    # Exact agreement still admits, and N is still not N+1.
    assert plan_for(view(turn=7), expected_source_turn=7).source.source_turn == 7
    with pytest.raises(CampaignSnapshotError, match="does not match"):
        plan_for(view(turn=7), expected_source_turn=8)


def test_side_inputs_are_mandatory_exact_and_never_inferred():
    # No side input is optional, and none is filled from the snapshot instead.
    for field in ("kits", "morale", "stocks"):
        with pytest.raises(CampaignSnapshotError, match=f"{field}: missing"):
            plan_for(**{field: {}})
    with pytest.raises(CampaignSnapshotError, match="missing"):
        plan_for(kits={7: 8})
    with pytest.raises(CampaignSnapshotError, match="missing"):
        plan_for(morale={8: 800})
    with pytest.raises(CampaignSnapshotError, match="missing"):
        plan_for(stocks={0: 0, 1: 0})
    with pytest.raises(CampaignSnapshotError, match="not a known soldier id"):
        plan_for(selected_ids=(7,), kits={7: 8, 99: 1})
    with pytest.raises(CampaignSnapshotError, match="not a known region id"):
        plan_for(stocks={0: 0, 1: 0, 2: 4, 9: 1})
    # Kits are bounded by the caller's own policy carried limit.
    for kits, message in (({7: 9, 8: 8}, "exceeds 8"),
                          ({7: -1, 8: 8}, "nonnegative exact integer"),
                          ({7: 1.5, 8: 8}, "nonnegative exact integer"),
                          ({7: True, 8: 8}, "nonnegative exact integer"),
                          ({7: None, 8: 8}, "nonnegative exact integer"),
                          ((7, 8), r"expected \(id, value\) pairs"),
                          (7, "expected an explicit mapping or tuple of pairs")):
        with pytest.raises(CampaignSnapshotError, match=message):
            plan_for(kits=kits)
    with pytest.raises(CampaignSnapshotError, match=f"exceeds {MORALE_LIMIT}"):
        plan_for(morale={7: MORALE_LIMIT + 1, 8: 800})
    # A pair sequence is explicit too, and its duplicates are still duplicates.
    with pytest.raises(CampaignSnapshotError, match="duplicate soldier id"):
        plan_for(kits=((7, 8), (7, 8), (8, 8)))
    # Float stockpiles are never silently converted to rations.
    with pytest.raises(CampaignSnapshotError, match="nonnegative exact integer"):
        plan_for(stocks={0: 0.0, 1: 0, 2: 4})
    with pytest.raises(CampaignSnapshotError, match="nonnegative exact integer"):
        plan_for(stocks={0: -1, 1: 0, 2: 4})


def test_side_input_mappings_are_copied_so_later_mutation_cannot_change_a_plan():
    kits, morale, stocks = {7: 8, 8: 8}, {7: 800, 8: 790}, {0: 0, 1: 0, 2: 4}
    plan = plan_for(kits=kits, morale=morale, stocks=stocks)
    saved = plan_bytes(plan)
    kits[7], morale[8], stocks[2] = 0, 0, 99
    assert plan_bytes(plan) == saved
    assert plan.kits == ((7, 8), (8, 8)) and plan.morale == ((7, 800), (8, 790))
    assert plan.stocks == (Stock(0, 0), Stock(1, 0), Stock(2, 4))
    # Immutable pair sequences are accepted without a mutable mapping.
    assert plan_for(kits=((7, 8), (8, 8)), morale=((7, 800), (8, 790)),
                    stocks=((0, 0), (1, 0), (2, 4))).plan_digest == plan.plan_digest


def test_adapter_configuration_is_validated_before_admission():
    for change, message in (({"policy": None}, "Policy required"),
                            ({"policy": "illustrative"}, "Policy required"),
                            ({"civ_id": -1}, "civ id"),
                            ({"civ_id": 2 ** 8}, "civ id"),
                            ({"campaign_id": ""}, "campaign id"),
                            ({"campaign_id": 7}, "campaign id"),
                            ({"topology_version": ""}, "topology version"),
                            ({"topology_version": 3}, "topology version"),
                            ({"expected_source_turn": -1}, "expected source turn"),
                            ({"expected_source_turn": 7.0}, "expected source turn"),
                            ({"staging": -1}, "staging")):
        with pytest.raises(CampaignSnapshotError, match=message):
            plan_for(**change)
    with pytest.raises(CampaignSnapshotError, match="AgentRows"):
        plan_for(agent_rows=None)
    with pytest.raises(CampaignSnapshotError, match="AgentRows"):
        plan_for(agent_rows=object())
    with pytest.raises(CampaignSnapshotError, match="AgentRows"):
        plan_for(agent_rows=snapshot())
    with pytest.raises(ValueError, match="phase10_entry"):
        Stamp(7, "latest")
    # Stamp's own constructor refuses other stages, so reaching the adapter's
    # stage re-check needs a stamp forced past that constructor.
    with pytest.raises(CampaignSnapshotError, match="phase10_entry"):
        plan_for(agent_rows=AgentRows(forced_stamp(7, "later"), snapshot()))
    with pytest.raises(CampaignSnapshotError, match="must carry a Stamp"):
        plan_for(agent_rows=AgentRows(object(), snapshot()))


def test_kernel_policy_and_objective_rules_still_apply():
    strict = replace(DEMO_POLICY, ordering=("move", "consume"))
    with pytest.raises(ValueError, match="unsupported policy lifecycle/order"):
        plan_for(policy=strict)
    for change in ({"staging": 2, "target": 2}, {"staging": 1, "target": 1},
                   {"policy": replace(DEMO_POLICY, require_full_rations=1)},
                   {"policy": replace(DEMO_POLICY, ration_demand=0)}):
        with pytest.raises(ValueError):
            plan_for(**change)


def test_carried_limit_above_one_thousand_is_admitted_not_rejected():
    # The public kernel owns this domain: a large carried limit is a success case,
    # and no adapter-side ceiling stands between the caller and the kernel.
    plan = plan_for(policy=replace(DEMO_POLICY, carried_limit=20000))
    assert plan.policy.carried_limit == 20000
    large_kit = plan_for(policy=replace(DEMO_POLICY, carried_limit=20000), kits={7: 9000, 8: 9000})
    assert tuple(soldier.rations for soldier in large_kit.soldiers) == (9000, 9000)
    # A kit beyond the policy's own limit is still the kernel's rejection.
    with pytest.raises(CampaignSnapshotError, match="exceeds 20000"):
        plan_for(policy=replace(DEMO_POLICY, carried_limit=20000), kits={7: 20001, 8: 8})


# ---------------------------------------------------------------- no retention

def test_source_objects_are_unchanged_and_nothing_borrowed_is_retained():
    batch = snapshot()
    before = batch.to_pydict()
    borrowed = view(batch)
    stamp_before = (borrowed.stamp.source_turn, borrowed.stamp.stage)
    rows_before = borrowed.ints("id")
    admitted = plan_for(borrowed)
    assert batch.to_pydict() == before
    assert (borrowed.stamp.source_turn, borrowed.stamp.stage) == stamp_before
    assert borrowed.batch is batch and borrowed.ints("id") == rows_before
    saved = plan_bytes(admitted)
    assert json.loads(saved.decode())["plan_digest"] == admitted.plan_digest
    assert saved == plan_bytes(plan_for())
    # The plan stays alive and usable while the caller's view and batch are
    # released: the plan holds neither, so both weakrefs clear.
    view_reference, batch_reference = weakref.ref(borrowed), weakref.ref(batch)
    del borrowed, batch
    gc.collect()
    assert view_reference() is None and batch_reference() is None
    assert plan_bytes(admitted) == saved


def test_plan_never_carries_arrow_world_or_native_objects():
    batch = snapshot()
    plan = plan_for(view(batch))
    escaped = []

    def walk(value, seen):
        if isinstance(value, (str, bytes, int, float, bool, type(None))):
            return
        if id(value) in seen:
            return
        seen.add(id(value))
        if isinstance(value, (pa.RecordBatch, pa.Table, pa.ChunkedArray, pa.Array,
                              AgentRows, Stamp, pa.DataType, pa.Schema)):
            escaped.append(value)
            return
        if isinstance(value, dict):
            for key, item in value.items():
                walk(key, seen)
                walk(item, seen)
        elif isinstance(value, (list, tuple)):
            for item in value:
                walk(item, seen)
        elif hasattr(value, "__dict__") or hasattr(value, "__slots__"):
            for name in getattr(value, "__slots__", ()) or ():
                walk(getattr(value, name, None), seen)
            for name in getattr(value, "__dataclass_fields__", {}):
                walk(getattr(value, name, None), seen)

    walk(plan, set())
    walk(plan_document(plan), set())
    walk(plan.source.column_digests, set())
    assert not escaped
    # Every plan field holds only this lane's records or reviewed kernel records.
    allowed = (str, int, SourceIdentity, RegionBinding, Policy, Topology, Soldier, Stock,
               Session, tuple)
    assert all(isinstance(getattr(plan, field.name), allowed) for field in fields(plan))


def test_demanded_columns_are_decoded_at_most_once_and_nothing_else_is_read():
    probe = CountingBatch(snapshot())
    plan = plan_for(view(probe))
    assert probe.calls == {name: 1 for name in DEMANDED_COLUMNS}
    assert set(probe.accesses) == set(DEMANDED_COLUMNS)
    assert plan.soldiers == (Soldier(7, 0, 8, 800), Soldier(8, 1, 8, 800))
    # Rejections read no more than they need, and never a fifth column. Bounds,
    # epoch and binding checks precede the decode; roster checks follow it.
    for overrides, expected in (({"selected_ids": (9,)}, set(DEMANDED_COLUMNS)),
                                ({"selected_ids": ()}, set(DEMANDED_COLUMNS)),
                                ({"kits": {}}, set(DEMANDED_COLUMNS)),
                                ({"region_bindings": ()}, set()),
                                ({"civ_id": -1}, set()),
                                ({"expected_source_turn": 6}, set())):
        probe = CountingBatch(snapshot())
        with pytest.raises(ValueError):
            plan_for(view(probe), **overrides)
        assert set(probe.accesses) == expected


# -------------------------------------------------------------- side document

def plain_json(value):
    """Recursively plain-JSON view of a frozen record, as a side document needs."""
    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: plain_json(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, (list, tuple)):
        return [plain_json(item) for item in value]
    if isinstance(value, Mapping):
        return {str(key): plain_json(item) for key, item in value.items()}
    return value


def side_document(**overrides):
    document = {
        "contract": CONTRACT, "source_turn": 7, "civ_id": 1, "selected_ids": [8, 7],
        "campaign_id": "snapshot-plan", "topology_version": TOPOLOGY_VERSION,
        "staging": 1, "target": 2,
        "policy": {
            "version": "m60a-demo-illustrative-v1", "ration_demand": 1, "carried_limit": 8,
            "distance_stress": 10, "unreachable_stress": 100, "hunger_stress": 120,
            "needs_stress": 100, "information_stress": 80, "morale_recovery": 20,
            "desertion_threshold": 200, "desertion_chance": 5000,
            "movement_min_morale": 100, "require_full_rations": True,
            "ordering": list(ORDERING),
            "rally_rule": "all-survivors-next-turn",
            "termination_rule": "all-returned-or-deserted",
        },
        "region_bindings": [
            {"region_id": 2, "name": "r2", "neighbors": ["r0"]},
            {"region_id": 0, "name": "r0", "neighbors": ["r1", "r2"]},
            {"region_id": 1, "name": "r1", "neighbors": ["r0"]},
        ],
        "kits": {"8": 8, "7": 8},
        "morale": {"7": 800, "8": 800},
        "stocks": {"2": 4, "1": 0, "0": 0},
    }
    document.update(overrides)
    return document


def test_side_document_parses_to_the_same_plan_as_direct_arguments():
    side = parse_side_inputs(side_document())
    assert side.contract == CONTRACT and side.source_turn == 7
    assert side.selected_ids == (8, 7)
    # The parser preserves the document's own order; canonical order is the
    # adapter's job, and it happens in the returned plan, not in SideInputs.
    assert side.region_bindings == (RegionBinding(2, "r2", ("r0",)),
                                    RegionBinding(0, "r0", ("r1", "r2")),
                                    RegionBinding(1, "r1", ("r0",)))
    assert side.policy == DEMO_POLICY
    assert side.kits == ((7, 8), (8, 8)) and side.morale == ((7, 800), (8, 800))
    assert side.stocks == ((0, 0), (1, 0), (2, 4))
    driven = admit_snapshot_plan(
        agent_rows=view(), expected_source_turn=side.source_turn, civ_id=side.civ_id,
        selected_ids=side.selected_ids, region_bindings=side.region_bindings,
        topology_version=side.topology_version, policy=side.policy,
        campaign_id=side.campaign_id, staging=side.staging, target=side.target,
        kits=dict(side.kits), morale=dict(side.morale), stocks=dict(side.stocks))
    assert driven.plan_digest == plan_for().plan_digest
    # Canonical plan order is by region id, regardless of the supplied order.
    assert driven.region_bindings == BINDINGS
    assert driven.selected_ids == (7, 8)
    # The parsed record is frozen; callers cannot retarget a planned civ.
    with pytest.raises(FrozenInstanceError):
        side.civ_id = 2


@pytest.mark.parametrize("change, message", [
    ({"contract": "other"}, "expected contract"),
    ({"selected_ids": []}, "nonempty list"),
    ({"selected_ids": [7, 7]}, "duplicate agent id"),
    ({"selected_ids": ["7"]}, "nonnegative exact integer"),
    ({"selected_ids": [7.0]}, "nonnegative exact integer"),
    ({"selected_ids": [True]}, "nonnegative exact integer"),
    ({"source_turn": -1}, "nonnegative exact integer"),
    ({"civ_id": 256}, "exceeds 255"),
    ({"campaign_id": ""}, "nonempty string"),
    ({"staging": "1"}, "nonnegative exact integer"),
    ({"kits": {"07": 8, "8": 8}}, "canonical"),
    ({"kits": {"7": 1.5, "8": 8}}, "nonnegative exact integer"),
    ({"kits": {"7": -1, "8": 8}}, "nonnegative"),
    ({"kits": {"7": True, "8": 8}}, "nonnegative exact integer"),
    ({"kits": []}, "JSON object keyed by ids"),
    ({"stocks": []}, "JSON object keyed by ids"),
    ({"kits": {"7": 8, "8": 8}, "morale": []}, "JSON object keyed by ids"),
    ({"selected_ids": (7, 8)}, "expected a nonempty list"),
    ({"selected_ids": {7, 8}}, "expected a nonempty list"),
    ({"selected_ids": [2 ** 32]}, "exceeds 4294967295"),
    ({"source_turn": 1.0}, "nonnegative exact integer"),
    ({"civ_id": True}, "nonnegative exact integer"),
    ({"topology_version": 7}, "nonempty string"),
    ({"region_bindings": [{"region_id": 0, "name": "r0", "neighbors": ["r0"]}]},
     "cannot neighbor itself"),
    ({"region_bindings": []}, "nonempty list"),
    ({"region_bindings": [{"region_id": 0, "name": "r0"}]}, "expected exactly the keys"),
    ({"region_bindings": [{"region_id": 0, "name": "r0", "neighbors": "r1"}]}, "list of region names"),
    ({"region_bindings": [{"region_id": 0, "name": "r0", "neighbors": [1]}]}, "nonempty string"),
    ({"policy": {"version": "v"}}, "expected exactly the keys"),
    ({"policy": None}, "expected a JSON object"),
    ({"unexpected_key": 1}, "expected exactly the keys"),
])
def test_side_document_is_strict_about_shape_and_exact_integer_domains(change, message):
    with pytest.raises(CampaignSnapshotError, match=message):
        parse_side_inputs(side_document(**change))


def test_side_document_top_level_is_an_exact_object():
    for payload, message in ((None, "expected a JSON object"), ([], "expected a JSON object"),
                             (side_document() | {"extra": 1}, "expected exactly the keys")):
        with pytest.raises(CampaignSnapshotError, match=message):
            parse_side_inputs(payload)


def test_side_document_policy_kinds_are_checked_and_ranges_stay_the_kernels():
    def policy_with(**change):
        document = side_document()
        document["policy"] = dict(document["policy"], **change)
        return document

    # JSON kinds are the parser's job: exact integers, a real boolean, a list
    # of strings for ordering, nonempty text elsewhere.
    for change, message in (({"ration_demand": 1.0}, "nonnegative exact integer"),
                            ({"carried_limit": True}, "nonnegative exact integer"),
                            ({"hunger_stress": -1}, "nonnegative"),
                            ({"require_full_rations": 1}, "expected a boolean"),
                            ({"ordering": "orders"}, "list of strings"),
                            ({"ordering": [7]}, "list of strings"),
                            ({"rally_rule": ""}, "nonempty string"),
                            ({"version": " "}, "nonempty string")):
        with pytest.raises((CampaignSnapshotError, ValueError), match=message):
            parse_side_inputs(policy_with(**change))
    # Numeric ranges are the public kernel's, so parsing succeeds and admission
    # is where the reviewed rule applies.
    for change, message in (({"desertion_chance": 10001}, "invalid desertion chance"),
                            ({"hunger_stress": 1001}, "invalid hunger_stress"),
                            ({"desertion_threshold": 1001}, "invalid desertion_threshold"),
                            ({"ordering": list(ORDERING) + ["extra"]},
                             "unsupported policy lifecycle/order"),
                            ({"ordering": ["orders"]}, "unsupported policy lifecycle/order"),
                            ({"rally_rule": "same-turn"}, "unsupported policy lifecycle/order"),
                            ({"termination_rule": "combat"},
                             "unsupported policy lifecycle/order")):
        with pytest.raises((CampaignSnapshotError, ValueError), match=message):
            side = parse_side_inputs(policy_with(**change))
            plan_for(policy=side.policy)
    for change in ({"ration_demand": 0}, {"movement_min_morale": -1},
                   {"movement_min_morale": 1001}):
        with pytest.raises(ValueError):
            side = parse_side_inputs(policy_with(**change))
            plan_for(policy=side.policy)


def test_side_policy_json_admits_exactly_what_the_typed_policy_admits():
    # The parser restates no kernel range, so typed and JSON agree at the edges
    # of the public domain, including a large carried limit.
    for change in ({}, {"carried_limit": 20000}, {"ration_demand": 3, "carried_limit": 12},
                   {"desertion_chance": 10000}, {"hunger_stress": 0}):
        policy = replace(DEMO_POLICY, **change)
        typed = plan_for(policy=policy)
        parsed = parse_side_inputs(side_document(policy=plain_json(policy)))
        assert parsed.policy == policy
        driven = plan_for(policy=parsed.policy)
        assert plan_bytes(driven) == plan_bytes(typed)
        assert driven.policy.carried_limit == policy.carried_limit


# --------------------------------------------------------------------- the CLI

def test_disabled_cli_opens_no_file_and_calls_no_kernel(monkeypatch):
    receipt = DEMO["disabled_receipt"]()
    assert receipt == {"contract": CONTRACT, "enabled": False,
                       "reason": "explicit --enable with --snapshot and --side-inputs required",
                       "snapshot_read": False, "side_inputs_read": False,
                       "kernel_admit_calls": 0, "turns_advanced": 0}
    calls = []

    def forbidden(*arguments, **keywords):
        calls.append((arguments, keywords))
        raise AssertionError("disabled driver touched a file or the kernel")

    # Patch the real module globals run() resolves, not runpy's returned mapping.
    monkeypatch.setitem(DEMO["run"].__globals__, "read_snapshot", forbidden)
    monkeypatch.setitem(DEMO["run"].__globals__, "strict_json_loads", forbidden)
    monkeypatch.setitem(DEMO["run"].__globals__, "admit_snapshot_plan", forbidden)
    assert DEMO["run"](enabled=False, snapshot=None, side_inputs=None) == receipt
    # Disabled runs stay inert even when both paths are supplied.
    inert = DEMO["run"](enabled=False, snapshot=Path("/nonexistent/absent.arrow"),
                        side_inputs=Path("/nonexistent/absent.json"))
    assert inert == receipt and not inert["snapshot_read"] and not inert["side_inputs_read"]
    assert calls == []


def test_driver_has_no_native_query_or_simulation_advance_in_executable_code():
    # Executable code only: the module docstring legitimately explains what the
    # driver never does.
    tree = ast.parse(DRIVER.read_text(encoding="utf-8"))
    imported = {alias.name.split(".")[0] for node in ast.walk(tree)
                if isinstance(node, (ast.Import, ast.ImportFrom))
                for alias in node.names}
    assert not imported & {"chronicler_agents", "chronicler", "numpy", "random"}
    calls = {node.func.attr for node in ast.walk(tree)
             if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)}
    assert not calls & {"get_snapshot", "run_turn", "tick", "advance"}
    # Only the adapter, the reviewed views and the strict JSON reader are imported.
    modules = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
    assert modules == {"chronicler.artifact_io", "chronicler.campaign_snapshot_adapter",
                       "chronicler.turn_artifacts", "__future__", "pathlib"}


def test_driver_side_inputs_use_a_strict_json_reader(tmp_path, capsys):
    # Duplicate JSON keys and non-finite constants are refused before parsing.
    for text, message in (('{"contract": "a", "contract": "b"}', "duplicate JSON key"),
                          ('{"kits": NaN}', "non-finite"),
                          ('{"kits": Infinity}', "non-finite"),
                          ("{not json}", "invalid side inputs")):
        path = tmp_path / "strict.json"
        path.write_text(text, encoding="utf-8")
        with pytest.raises(ValueError, match=message):
            DEMO["strict_json_loads"](path.read_text(encoding="utf-8"), label="side inputs")
    # Through the driver, the same refusal is reported, not raised.
    path = tmp_path / "duplicate.json"
    path.write_text('{"contract": "a", "contract": "b"}', encoding="utf-8")
    assert DEMO["main"](["--enable", "--snapshot", str(write_snapshot(tmp_path)),
                        "--side-inputs", str(path)]) == 2
    assert "duplicate JSON key" in capsys.readouterr().err


def test_disabled_invocation_reads_no_paths_in_a_fresh_process(tmp_path):
    missing = tmp_path / "absent.arrow"
    document = tmp_path / "absent.json"
    for arguments in ([], ["--snapshot", str(missing)], ["--side-inputs", str(document)],
                      ["--snapshot", str(missing), "--side-inputs", str(document)]):
        output = subprocess.run(
            [sys.executable, str(DRIVER), *arguments], check=True,
            capture_output=True, text=True,
            env=dict(os.environ, PYTHONPATH=str(ROOT / "src")))
        assert json.loads(output.stdout) == DEMO["disabled_receipt"]()
    # Neither path was created or read.
    assert not missing.exists() and not document.exists()


def test_enabled_driver_reads_explicit_files_and_stays_read_only(tmp_path):
    snapshot_path = write_snapshot(tmp_path)
    side_path = tmp_path / "side.json"
    side_path.write_text(json.dumps(side_document()), encoding="utf-8")
    document = DEMO["run"](enabled=True, snapshot=snapshot_path, side_inputs=side_path)
    assert document["plan_digest"] == plan_for().plan_digest
    assert document["admission"]["cursor_receipts"] == 0
    assert document["admission"]["original_ids"] == [7, 8]
    # Re-running is byte-identical; the snapshot file itself is unchanged.
    assert DEMO["run"](enabled=True, snapshot=snapshot_path,
                       side_inputs=side_path) == document
    assert DEMO["read_snapshot"](snapshot_path).num_rows == 5
    assert DEMO["read_snapshot"](snapshot_path).schema == SNAPSHOT_SCHEMA
    # The driver's batch is self-contained: it outlives the file it came from.
    owned = DEMO["read_snapshot"](snapshot_path)
    snapshot_path.unlink()
    assert owned.to_pydict() == snapshot().to_pydict()


def test_driver_reader_returns_a_zero_row_batch_so_admission_refuses_it(tmp_path, capsys):
    # A valid single-batch IPC file with no rows is a real capture shape: the
    # reader must hand it to the adapter, which then reports the absent roster,
    # rather than indexing an empty batch list.
    path = tmp_path / "empty.arrow"
    with pa.OSFile(str(path), "wb") as sink:
        with pa.ipc.new_file(sink, SNAPSHOT_SCHEMA) as writer:
            writer.write_batch(rows(ids=[], regions=[], civs=[], occupations=[]))
    batch = DEMO["read_snapshot"](path)
    assert batch.num_rows == 0 and batch.schema == SNAPSHOT_SCHEMA
    side_path = tmp_path / "side.json"
    side_path.write_text(json.dumps(side_document()), encoding="utf-8")
    assert DEMO["main"](["--enable", "--snapshot", str(path),
                        "--side-inputs", str(side_path)]) == 2
    captured = capsys.readouterr()
    assert captured.out == "" and "Traceback" not in captured.err
    assert "absent" in captured.err


def test_driver_reader_requires_exactly_one_record_batch(tmp_path):
    path = tmp_path / "two-batches.arrow"
    with pa.OSFile(str(path), "wb") as sink:
        with pa.ipc.new_file(sink, SNAPSHOT_SCHEMA) as writer:
            writer.write_batch(snapshot())
            writer.write_batch(snapshot())
    with pytest.raises(CampaignSnapshotError, match="exactly one Arrow IPC record batch"):
        DEMO["read_snapshot"](path)


def test_driver_reports_rejections_on_stderr_without_a_traceback(tmp_path, capsys):
    snapshot_path = write_snapshot(tmp_path)
    side_path = tmp_path / "side.json"
    side_path.write_text(json.dumps(side_document(selected_ids=[7, 99])), encoding="utf-8")
    with pytest.raises(CampaignSnapshotError, match="absent"):
        DEMO["run"](enabled=True, snapshot=snapshot_path, side_inputs=side_path)
    assert DEMO["main"]([]) == 0
    assert capsys.readouterr().out.strip() == json.dumps(DEMO["disabled_receipt"](),
                                                         sort_keys=True, separators=(",", ":"))
    assert DEMO["main"](["--enable"]) == 2
    assert capsys.readouterr().out == ""
    # An absent roster member is reported, not raised through main().
    assert DEMO["main"](["--enable", "--snapshot", str(snapshot_path),
                        "--side-inputs", str(side_path)]) == 2
    assert "CampaignSnapshotError" in capsys.readouterr().err
    # A malformed side document and an absent snapshot are reported too.
    broken = tmp_path / "broken.json"
    broken.write_text(json.dumps({"contract": CONTRACT}), encoding="utf-8")
    assert DEMO["main"](["--enable", "--snapshot", str(snapshot_path),
                        "--side-inputs", str(broken)]) == 2
    assert "expected exactly the keys" in capsys.readouterr().err
    assert DEMO["main"](["--enable", "--snapshot", str(tmp_path / "none.arrow"),
                        "--side-inputs", str(tmp_path / "none.json")]) == 2
    assert capsys.readouterr().out == ""


def test_plan_bytes_are_stable_across_fresh_processes(tmp_path):
    snapshot_path = write_snapshot(tmp_path)
    side_path = tmp_path / "side.json"
    side_path.write_text(json.dumps(side_document()), encoding="utf-8")
    arguments = [sys.executable, str(DRIVER), "--enable", "--snapshot", str(snapshot_path),
                 "--side-inputs", str(side_path)]
    outputs = [subprocess.check_output(arguments, env=dict(os.environ, PYTHONHASHSEED=seed,
                                                            PYTHONPATH=str(ROOT / "src")))
               for seed in ("0", "1", "42", "101")]
    assert all(output == outputs[0] for output in outputs)
    document = json.loads(outputs[0])
    assert document["plan_digest"] == plan_for().plan_digest
    # Fresh processes agree byte-for-byte with this process's canonical bytes.
    assert outputs[0].strip() == plan_bytes(plan_for())
    assert json.dumps(document, sort_keys=True, separators=(",", ":")).encode() == outputs[0].strip()
    # Importing the adapter and running the driver touches no production world,
    # simulation or native module, and consumes no RNG state. pyarrow legitimately
    # imports numpy transitively for allowed Arrow I/O, so that is not asserted.
    probe = '''import random, sys
FORBIDDEN = ("chronicler.models", "chronicler.simulation", "chronicler.agent_bridge",
             "chronicler.main", "chronicler.world_gen", "chronicler.economy",
             "chronicler.memome_experiment", "chronicler_agents")
before = random.getstate()
import chronicler.campaign_snapshot_adapter
assert random.getstate() == before
assert not any(k in sys.modules for k in FORBIDDEN), sorted(sys.modules)
import runpy
runpy.run_path("scripts/campaign_snapshot_plan.py", run_name="driver_probe")
assert random.getstate() == before
assert not any(k in sys.modules for k in FORBIDDEN), sorted(sys.modules)
'''
    subprocess.run([sys.executable, "-c", probe], check=True, cwd=str(ROOT),
                   env=dict(os.environ, PYTHONPATH=str(ROOT / "src")))


def test_kernel_and_existing_fixtures_are_reused_not_copied():
    module = (ROOT / "src" / "chronicler" / "campaign_snapshot_adapter.py").read_text("utf-8")
    # Only the public kernel seam is used: no private helpers, no copied algorithm.
    assert "from chronicler.campaign_logistics import" in module
    # Line-anchored, so unrelated identifiers cannot satisfy or break the check.
    for private in ("_config(", "_path(", "_validate_soldier(", "_tick_input(",
                    "_int(", "_unique(", "_records(", "deque("):
        assert f"\n    {private}" not in module and f"\ndef {private}" not in module
    assert "validate_snapshot_schema" in module
    # The only kernel names borrowed are public records plus the admit seam.
    borrowed = {alias.name for node in ast.walk(ast.parse(module))
                if isinstance(node, ast.ImportFrom) and node.module == "chronicler.campaign_logistics"
                for alias in node.names}
    assert borrowed == {"Policy", "Region", "Session", "Soldier", "Stock", "Topology", "admit"}
    # The existing reviewed demo's policy and topology are the reused fixtures.
    demo = runpy.run_path(str(ROOT / "scripts" / "campaign_logistics_demo.py"))
    assert demo["illustrative_policy"]() == DEMO_POLICY
    assert plan_for().topology == demo["fixture_topology"]()
    # This lane's roster is different from the demo's, and says so: no native
    # enlistment is claimed for agents 7 and 8.
    assert demo["fixture_session"](DEMO_POLICY, demo["fixture_topology"]()).state.soldiers != (
        plan_for().session.state.soldiers)
    assert canonical_bytes(plan_for().session.state) == canonical_bytes(
        admit(policy=DEMO_POLICY, topology=demo["fixture_topology"](), campaign_id="snapshot-plan",
              turn=7, staging=1, target=2,
              soldiers=(Soldier(7, 0, 8, 800), Soldier(8, 1, 8, 800)),
              stocks=(Stock(0, 0), Stock(1, 0), Stock(2, 4))).state)
    # This lane owns exactly four added paths and registers no production surface.
    added = {"src/chronicler/campaign_snapshot_adapter.py",
             "scripts/campaign_snapshot_plan.py",
             "tests/test_campaign_snapshot_adapter.py",
             "docs/experiments/campaign-snapshot-adapter.md"}
    assert all((ROOT / path).is_file() for path in added)
    registry = (ROOT / "src" / "chronicler" / "main.py").read_text("utf-8")
    assert "campaign_snapshot" not in registry
    # Nothing in the package imports the adapter, so no ordinary path can reach it.
    importers = [path for path in (ROOT / "src").rglob("*.py")
                 if path.name != "campaign_snapshot_adapter.py"
                 and "campaign_snapshot_adapter" in path.read_text("utf-8")]
    assert {path.relative_to(ROOT).as_posix() for path in importers} == {
        "src/chronicler/snapshot_campaign_sessions.py"}
    # Existing snapshot-contract and campaign fixtures are reused unchanged.
    assert SNAPSHOT_FIELD_NAMES == tuple(SNAPSHOT_SCHEMA.names)
    assert len(SNAPSHOT_FIELD_NAMES) == 24 and SNAPSHOT_FIELD_NAMES[0] == "id"
    assert SNAPSHOT_FIELD_NAMES[-1] == "movement_id"
    assert rows_for(snapshot()).ints("id") == (7, 8, 9, 10, 11)