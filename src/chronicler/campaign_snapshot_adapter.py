"""Default-off campaign admission adapter: captured snapshot -> reviewed M60a plan.

Read-only input plumbing for the detached M60a campaign kernel. The adapter
borrows one Phase-10-entry ``AgentRows`` view, demands only the four native
identity columns ``id``/``region``/``civ_affinity``/``occupation``, and hands
explicit side inputs plus explicit stable region bindings to the reviewed
public ``chronicler.campaign_logistics.admit`` seam. It plans admission only:
no tick is built, no turn advances, no draw is supplied or consumed.

Boundaries, all deliberate:

* ``chronicler.bridge_contract.validate_snapshot_schema`` is called here, and
  only here, as the opt-in exact ratchet for this boundary. Validator behavior
  is unchanged, and no ordinary consumer, view or capture path calls it.
* The snapshot has no carried rations, campaign morale, unmet needs, supply
  stocks, packet-derived information quality or eight-slot memomes. Kits,
  campaign morale and local sandbox stocks are mandatory explicit side inputs.
  Nothing is inferred from loyalty/satisfaction, float stockpiles or threat
  intensity, and no real enlistment, stock debit or treasury charge happens.
* Native occupation code 1 is the soldier role
  (``chronicler-agents/src/agent.rs:7-13``; ``models.py:675``).
* Region identifiers arrive only through explicit immutable
  ``RegionBinding(region_id, name, neighbors)`` records. Names are labels only:
  adjacency is rebuilt from the bindings, never from trade routes, sea routes,
  k-nearest fills, display-name hashes or list order.
* Provenance hashes the four demanded columns in stable-id row order, so Arrow
  row order is not part of the recorded identity while any real change to a
  demanded value is. Undemanded fields are outside that identity.
* No production hook, feature flag, shared CLI registration, world mutation,
  native query, RNG use or Python integer-limit change is introduced.
* The returned plan holds copied immutable records plus the public kernel
  ``Session``. No borrowed Arrow table, ``AgentRows`` view, world or native
  object escapes in the plan, and this module keeps no decode cache.
"""
from __future__ import annotations

from collections.abc import Mapping as MappingABC
from dataclasses import dataclass, fields, is_dataclass, replace
import hashlib
import json
import re
from typing import Any

import pyarrow as pa

from chronicler.bridge_contract import SNAPSHOT_SCHEMA, validate_snapshot_schema
from chronicler.campaign_logistics import (
    Policy, Region, Session, Soldier, Stock, Topology, admit,
)
from chronicler.turn_artifacts import AgentRows, Stamp

CONTRACT = "chronicler-campaign-snapshot-adapter-v1"
ADAPTER = "campaign-snapshot-adapter-v1"
STAGE = "phase10_entry"
SOLDIER_OCCUPATION = 1
MORALE_LIMIT = 1000
DEMANDED_COLUMNS = ("id", "region", "civ_affinity", "occupation")
SIDE_ID_KEY = re.compile(r"(0|[1-9][0-9]*)")


class CampaignSnapshotError(ValueError):
    """Rejected snapshot-to-plan input. No repair, default or inference."""


def _require(condition: Any, message: str) -> None:
    if not condition:
        raise CampaignSnapshotError(message)


def _nonnegative_int(value: Any) -> bool:
    """Exact integer domain: ``bool`` is not an integer here."""
    return type(value) is int and value >= 0


def _native_limit(name: str) -> int:
    """Upper bound of one demanded native column, straight from the contract."""
    kind = SNAPSHOT_SCHEMA.field(name).type
    if not pa.types.is_unsigned_integer(kind):
        raise CampaignSnapshotError(
            f"demanded snapshot column {name!r} must stay an unsigned native integer"
        )
    return 2 ** kind.bit_width - 1


COLUMN_LIMITS = {name: _native_limit(name) for name in DEMANDED_COLUMNS}
# Derived from SNAPSHOT_SCHEMA, so a reviewed native type change moves these
# bounds with it. If a demanded column ever stops being an unsigned integer,
# this module refuses to import rather than inventing a bound.


def _canonical(payload: Any) -> bytes:
    """Canonical JSON for adapter records only; the kernel owns its own encoder."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _digest(payload: Any) -> str:
    return hashlib.sha256(_canonical(payload)).hexdigest()


@dataclass(frozen=True, slots=True)
class RegionBinding:
    """One explicit stable region identifier, its label and its labeled neighbors.

    ``neighbors`` uses the names-based shape of ``models.Region.adjacencies``
    (``models.py:296-310``) but every edge must name another bound region. The
    identifier travels with the record, so reordering a caller's list can never
    remap a region id, name or edge.
    """

    region_id: int
    name: str
    neighbors: tuple[str, ...]

    def __post_init__(self) -> None:
        _require(_nonnegative_int(self.region_id),
                 "region binding id must be a nonnegative exact integer")
        _require(type(self.name) is str and bool(self.name.strip()),
                 "region binding name must be a nonempty string")
        _require(type(self.neighbors) is tuple,
                 "region binding neighbors must be an immutable tuple of names")
        for neighbor in self.neighbors:
            _require(type(neighbor) is str and bool(neighbor.strip()),
                     "region binding neighbor must be a nonempty string")
        _require(len(set(self.neighbors)) == len(self.neighbors),
                 f"duplicate neighbor in region binding {self.region_id}")
        _require(self.name not in self.neighbors,
                 f"region binding {self.region_id} cannot neighbor itself")


@dataclass(frozen=True, slots=True)
class SourceIdentity:
    """Content identity of exactly what this adapter read, and nothing more."""

    contract: str
    adapter: str
    source_turn: int
    stage: str
    row_count: int
    columns: tuple[str, ...]
    column_digests: tuple[tuple[str, str], ...]
    content_digest: str


@dataclass(frozen=True, slots=True)
class AdmissionPlan:
    """Frozen read-only plan: copied inputs, provenance and the public admission."""

    contract: str
    adapter: str
    source: SourceIdentity
    campaign_id: str
    civ_id: int
    admission_turn: int
    staging: int
    target: int
    selected_ids: tuple[int, ...]
    region_bindings: tuple[RegionBinding, ...]
    region_binding_digest: str
    policy: Policy
    topology: Topology
    soldiers: tuple[Soldier, ...]
    kits: tuple[tuple[int, int], ...]
    morale: tuple[tuple[int, int], ...]
    stocks: tuple[Stock, ...]
    session: Session
    initial_state_digest: str
    plan_digest: str


SIDE_KEYS = frozenset({
    "contract", "source_turn", "civ_id", "selected_ids", "campaign_id",
    "topology_version", "staging", "target", "policy", "region_bindings",
    "kits", "morale", "stocks",
})
BINDING_KEYS = frozenset({"region_id", "name", "neighbors"})
POLICY_KEYS = frozenset(field.name for field in fields(Policy))
# Side-document parsing must know the reviewed Policy shape explicitly: adding a
# kernel field or kind requires an intentional update here. Parsing classifies
# JSON kinds and exact integers only; every numeric range stays the public
# kernel's business, so the JSON path admits exactly what the typed path does.
POLICY_INT_KEYS = frozenset({
    "ration_demand", "carried_limit", "distance_stress", "unreachable_stress",
    "hunger_stress", "needs_stress", "information_stress", "morale_recovery",
    "desertion_threshold", "desertion_chance", "movement_min_morale",
})
POLICY_BOOL_KEYS = frozenset({"require_full_rations"})
POLICY_TEXT_KEYS = frozenset({"version", "rally_rule", "termination_rule"})
POLICY_TUPLE_KEYS = frozenset({"ordering"})
_require(POLICY_KEYS == POLICY_INT_KEYS | POLICY_BOOL_KEYS | POLICY_TEXT_KEYS | POLICY_TUPLE_KEYS,
         "side-document Policy key sets are stale for the reviewed kernel Policy")


@dataclass(frozen=True, slots=True)
class SideInputs:
    """Parsed explicit side document: typed, immutable and exact-key checked."""

    contract: str
    source_turn: int
    civ_id: int
    selected_ids: tuple[int, ...]
    campaign_id: str
    topology_version: str
    staging: int
    target: int
    policy: Policy
    region_bindings: tuple[RegionBinding, ...]
    kits: tuple[tuple[int, int], ...]
    morale: tuple[tuple[int, int], ...]
    stocks: tuple[tuple[int, int], ...]


def _side_object(value: Any, keys: frozenset[str], label: str) -> dict:
    """Require exactly these keys: unknown and missing keys are both rejected."""
    _require(type(value) is dict, f"{label}: expected a JSON object")
    _require(set(value) == keys,
             f"{label}: expected exactly the keys {sorted(keys)}, got {sorted(value)}")
    return value


def _side_int(value: Any, label: str, *, maximum: int | None = None) -> int:
    _require(_nonnegative_int(value),
             f"{label}: expected a nonnegative exact integer, got {value!r}")
    if maximum is not None:
        _require(value <= maximum, f"{label}: {value} exceeds {maximum}")
    return value


def _side_text(value: Any, label: str) -> str:
    _require(type(value) is str and bool(value.strip()),
             f"{label}: expected a nonempty string")
    return value


def _side_pairs(value: Any, label: str) -> tuple[tuple[int, int], ...]:
    """Copy a canonical decimal-keyed integer mapping into sorted pairs.

    Keys must be canonical decimal text, so ``"7"`` and ``"07"`` cannot both
    name agent 7. A strict JSON reader already refuses duplicate object keys.
    """
    _require(type(value) is dict, f"{label}: expected a JSON object keyed by ids")
    pairs = []
    for key, amount in value.items():
        _require(type(key) is str and SIDE_ID_KEY.fullmatch(key) is not None,
                 f"{label}: {key!r} is not a canonical nonnegative integer id")
        _side_int(amount, f"{label}[{key}]")
        pairs.append((int(key), amount))
    _require(len({pair[0] for pair in pairs}) == len(pairs), f"{label}: duplicate id")
    return tuple(sorted(pairs))


def _side_policy(value: Any) -> Policy:
    """Classify a JSON policy object by kind; leave every range to the kernel.

    Numeric fields must be exact nonnegative JSON integers and nothing more. The
    reviewed public ``Policy``/``admit`` domains are deliberately not restated
    here, so a JSON policy is admissible exactly when the equivalent typed
    policy is.
    """
    payload = _side_object(value, POLICY_KEYS, "policy")
    values: dict[str, Any] = {}
    for key in sorted(POLICY_KEYS):
        item = payload[key]
        if key in POLICY_BOOL_KEYS:
            _require(type(item) is bool, f"policy.{key}: expected a boolean")
            values[key] = item
        elif key in POLICY_TUPLE_KEYS:
            _require(type(item) is list and all(type(entry) is str for entry in item),
                     f"policy.{key}: expected a list of strings")
            values[key] = tuple(item)
        elif key in POLICY_TEXT_KEYS:
            values[key] = _side_text(item, f"policy.{key}")
        else:
            _require(key in POLICY_INT_KEYS, f"policy.{key}: unclassified reviewed field")
            values[key] = _side_int(item, f"policy.{key}")
    return Policy(**values)


def _side_binding(value: Any, label: str) -> RegionBinding:
    payload = _side_object(value, BINDING_KEYS, label)
    _require(type(payload["neighbors"]) is list,
             f"{label}.neighbors: expected a list of region names")
    for name in payload["neighbors"]:
        _side_text(name, f"{label}.neighbors")
    return RegionBinding(
        _side_int(payload["region_id"], f"{label}.region_id", maximum=COLUMN_LIMITS["region"]),
        _side_text(payload["name"], f"{label}.name"),
        tuple(payload["neighbors"]),
    )


def parse_side_inputs(payload: Any) -> SideInputs:
    """Parse one explicit side document. Unknown or missing keys are rejected.

    This performs shape and exact-integer-domain checks only. Roster coverage,
    region bindings, adjacency reciprocity and kernel validity stay with
    ``admit_snapshot_plan``.
    """
    document = _side_object(payload, SIDE_KEYS, "side inputs")
    _require(document["contract"] == CONTRACT,
             f"side inputs: expected contract {CONTRACT!r}")
    selected = document["selected_ids"]
    _require(type(selected) is list and bool(selected),
             "selected_ids: expected a nonempty list of stable agent ids")
    selected_ids = tuple(_side_int(agent, "selected_ids", maximum=COLUMN_LIMITS["id"])
                         for agent in selected)
    _require(len(set(selected_ids)) == len(selected_ids), "selected_ids: duplicate agent id")
    bindings = document["region_bindings"]
    _require(type(bindings) is list and bool(bindings),
             "region_bindings: expected a nonempty list of region bindings")
    return SideInputs(
        CONTRACT,
        _side_int(document["source_turn"], "source_turn"),
        _side_int(document["civ_id"], "civ_id", maximum=COLUMN_LIMITS["civ_affinity"]),
        selected_ids,
        _side_text(document["campaign_id"], "campaign_id"),
        _side_text(document["topology_version"], "topology_version"),
        _side_int(document["staging"], "staging", maximum=COLUMN_LIMITS["region"]),
        _side_int(document["target"], "target", maximum=COLUMN_LIMITS["region"]),
        _side_policy(document["policy"]),
        tuple(_side_binding(entry, f"region_bindings[{index}]")
              for index, entry in enumerate(bindings)),
        _side_pairs(document["kits"], "kits"),
        _side_pairs(document["morale"], "morale"),
        _side_pairs(document["stocks"], "stocks"),
    )


def _side_values(values: Any, expected: tuple[int, ...], label: str, subject: str,
                 coverage: str, *, maximum: int | None = None) -> tuple[tuple[int, int], ...]:
    """Copy caller-supplied integer side inputs with exact key coverage.

    Accepts a mapping or an immutable ``(id, value)`` pair sequence. Either way
    the result is a fresh sorted tuple, so the caller's container cannot change
    the plan afterwards, and neither container is retained.
    """
    if isinstance(values, MappingABC):
        items = list(values.items())
    else:
        _require(type(values) is tuple, f"{label}: expected an explicit mapping or tuple of pairs")
        items = []
        for pair in values:
            _require(type(pair) is tuple and len(pair) == 2, f"{label}: expected (id, value) pairs")
            items.append(pair)
    copied: dict[int, int] = {}
    for key, value in items:
        _require(_nonnegative_int(key) and key in expected,
                 f"{label}: {key!r} is not a known {subject}")
        _require(type(value) is int and value >= 0,
                 f"{label}: {subject} {key} needs a nonnegative exact integer, got {value!r}")
        if maximum is not None:
            _require(value <= maximum, f"{label}: {subject} {key} exceeds {maximum}")
        _require(key not in copied, f"{label}: duplicate {subject} {key}")
        copied[key] = value
    missing = sorted(set(expected) - set(copied))
    _require(not missing, f"{label}: missing explicit values for {coverage} {missing}")
    return tuple(sorted(copied.items()))


def _bindings(region_bindings: Any, topology_version: Any) -> tuple[
        tuple[RegionBinding, ...], Topology, tuple[int, ...]]:
    """Canonical bindings, the rebuilt topology and its ordered region ids.

    The kernel requires known, reciprocal, non-self edges; this rebuilds them
    from the supplied bindings so a rejected edge is reported against the
    binding that declared it, before any campaign state exists.
    """
    _require(type(topology_version) is str and bool(topology_version.strip()),
             "explicit topology version string required")
    _require(type(region_bindings) is tuple and bool(region_bindings),
             "explicit nonempty tuple of RegionBinding records required")
    for binding in region_bindings:
        _require(type(binding) is RegionBinding, "explicit RegionBinding records required")
        _require(binding.region_id <= COLUMN_LIMITS["region"],
                 f"region binding {binding.region_id} is outside the native region domain")
    ids = tuple(binding.region_id for binding in region_bindings)
    names = tuple(binding.name for binding in region_bindings)
    _require(len(set(ids)) == len(ids), "duplicate region binding id")
    _require(len(set(names)) == len(names), "duplicate region binding name")
    by_name = dict(zip(names, ids))
    edges: dict[int, tuple[int, ...]] = {}
    for binding in region_bindings:
        neighbors = []
        for neighbor in binding.neighbors:
            _require(neighbor in by_name,
                     f"region {binding.region_id} neighbors unknown region {neighbor!r}")
            neighbors.append(by_name[neighbor])
        edges[binding.region_id] = tuple(sorted(neighbors))
    for region_id, neighbors in edges.items():
        for neighbor in neighbors:
            _require(neighbor in edges and region_id in edges[neighbor],
                     f"region adjacency {region_id}<->{neighbor} must be reciprocal")
    # Copies, canonicalized by id then by name: caller order cannot survive here.
    canonical = tuple(sorted((RegionBinding(binding.region_id, binding.name,
                                            tuple(sorted(binding.neighbors)))
                              for binding in region_bindings),
                             key=lambda binding: (binding.region_id, binding.name)))
    region_ids = tuple(sorted(edges))
    topology = Topology(topology_version,
                        tuple(Region(region_id, edges[region_id]) for region_id in region_ids))
    return canonical, topology, region_ids


def _source_identity(source_turn: int, row_count: int,
                     columns: dict[str, tuple]) -> SourceIdentity:
    """Identity of the demanded columns, canonicalized into stable-id row order.

    Agent ids are the stable identity, so Arrow row order is not part of what
    was read: the same captured identities in a different row order describe the
    same observation. Undemanded fields sit outside this identity by design, so
    this is an identity of what this boundary read, not of the whole snapshot.
    """
    order = sorted(range(row_count), key=lambda index: columns["id"][index])
    digests = tuple((name, _digest([columns[name][index] for index in order]))
                    for name in DEMANDED_COLUMNS)
    content = _digest({"adapter": ADAPTER, "contract": CONTRACT, "source_turn": source_turn,
                       "stage": STAGE, "row_count": row_count,
                       "column_digests": [list(pair) for pair in digests]})
    return SourceIdentity(CONTRACT, ADAPTER, source_turn, STAGE, row_count,
                          DEMANDED_COLUMNS, digests, content)


def admit_snapshot_plan(*, agent_rows: AgentRows, expected_source_turn: int, civ_id: int,
                        selected_ids: tuple[int, ...],
                        region_bindings: tuple[RegionBinding, ...], topology_version: str,
                        policy: Policy, campaign_id: str, staging: int, target: int,
                        kits: Any, morale: Any, stocks: Any) -> AdmissionPlan:
    """Plan one M60a admission from a borrowed snapshot observation.

    The caller keeps every authority: the ``AgentRows`` view is only read, the
    native snapshot is never fetched here, and the public kernel ``admit`` seam
    is the only place a campaign state is created. The admission turn is the
    observation's own source turn N; no N+1 completed-turn label is invented,
    because this adapter never completes a turn.

    Kits, campaign morale and sandbox stocks are mandatory explicit inputs with
    exact coverage of the selected roster and of every bound region. Omitted
    values are rejected, never defaulted, converted or inferred, and no adapter
    ceiling is placed on a stock or on a policy field: the reviewed kernel owns
    those domains.
    """
    _require(isinstance(agent_rows, AgentRows), "borrowed AgentRows view required")
    _require(_nonnegative_int(expected_source_turn), "expected source turn must be a nonnegative integer")
    stamp = agent_rows.stamp
    _require(isinstance(stamp, Stamp), "borrowed AgentRows must carry a Stamp")
    _require(stamp.stage == STAGE, f"snapshot observation stage must be {STAGE!r}")
    # Stamp validates the stage but not the turn, so check the turn's exact
    # integer domain here: equality alone would accept True, 1.0 or an int
    # subclass, and provenance would then silently record the expected integer.
    _require(_nonnegative_int(stamp.source_turn),
             f"snapshot source turn {stamp.source_turn!r} is not a nonnegative exact integer")
    _require(stamp.source_turn == expected_source_turn,
             f"snapshot source turn {stamp.source_turn} does not match expected source turn "
             f"{expected_source_turn}")
    _require(type(policy) is Policy, "explicit campaign Policy required")
    _require(_nonnegative_int(civ_id) and civ_id <= COLUMN_LIMITS["civ_affinity"],
             "explicit civ id must be a nonnegative native civ affinity")
    _require(type(campaign_id) is str and bool(campaign_id.strip()),
             "explicit campaign id string required")
    for label, region_id in (("staging", staging), ("target", target)):
        _require(_nonnegative_int(region_id) and region_id <= COLUMN_LIMITS["region"],
                 f"{label} must be a nonnegative native region id")

    # Opt-in exact ratchet for this boundary only, before any value is decoded.
    # This is the single new caller; the validator itself is unchanged.
    validate_snapshot_schema(agent_rows.batch.schema)

    # Defensive copy: the returned plan never aliases the caller's policy record.
    policy_copy = replace(policy)
    canonical_bindings, topology, region_ids = _bindings(region_bindings, topology_version)
    bound = set(region_ids)
    _require(staging in bound, f"staging region {staging} is not bound")
    _require(target in bound, f"target region {target} is not bound")

    # Borrowed decode: read-only, one decode per demanded column, nothing else.
    columns = {name: agent_rows.ints(name) for name in DEMANDED_COLUMNS}
    lengths = {name: len(columns[name]) for name in DEMANDED_COLUMNS}
    _require(len(set(lengths.values())) == 1, f"snapshot columns are misaligned: {lengths}")
    row_count = lengths["id"]
    reported = getattr(agent_rows.batch, "num_rows", None)
    if type(reported) is int:
        _require(reported == row_count,
                 f"decoded {row_count} rows but the borrowed batch reports {reported}")
    for name in DEMANDED_COLUMNS:
        limit = COLUMN_LIMITS[name]
        for index, value in enumerate(columns[name]):
            _require(type(value) is int,
                     f"snapshot column {name!r} row {index} is null or not an exact integer")
            _require(0 <= value <= limit,
                     f"snapshot column {name!r} row {index} is outside the native domain")

    identifiers = columns["id"]
    _require(len(set(identifiers)) == row_count, "snapshot agent ids must be unique")
    _require(type(selected_ids) is tuple and bool(selected_ids),
             "explicit nonempty tuple of stable soldier ids required")
    for agent in selected_ids:
        _require(_nonnegative_int(agent) and agent <= COLUMN_LIMITS["id"],
                 f"selected agent id {agent!r} is outside the native id domain")
    _require(len(set(selected_ids)) == len(selected_ids), "selected soldier ids must be unique")
    index_of = {value: index for index, value in enumerate(identifiers)}
    for agent in selected_ids:
        _require(agent in index_of, f"selected soldier id {agent} is absent from the snapshot")

    # Only selected rows are interpreted; unselected rows are this boundary's
    # business solely through the shared snapshot-id uniqueness check above.
    regions, civs, occupations = columns["region"], columns["civ_affinity"], columns["occupation"]
    for agent in selected_ids:
        index = index_of[agent]
        _require(regions[index] in bound,
                 f"selected soldier {agent} stands in unbound region {regions[index]}")
        _require(occupations[index] == SOLDIER_OCCUPATION,
                 f"selected agent {agent} has occupation {occupations[index]}, not a native soldier")
        _require(civs[index] == civ_id,
                 f"selected agent {agent} has civ affinity {civs[index]}, not {civ_id}")

    roster = tuple(sorted(selected_ids))
    kit_pairs = _side_values(kits, roster, "kits", "soldier id", "selected soldier ids",
                             maximum=policy_copy.carried_limit)
    morale_pairs = _side_values(morale, roster, "morale", "soldier id", "selected soldier ids",
                                maximum=MORALE_LIMIT)
    stock_pairs = _side_values(stocks, region_ids, "stocks", "region id", "bound regions")
    kits_by_id = dict(kit_pairs)
    morale_by_id = dict(morale_pairs)
    stocks_by_region = dict(stock_pairs)

    soldiers = tuple(Soldier(agent, regions[index_of[agent]], kits_by_id[agent], morale_by_id[agent])
                     for agent in roster)
    stock_records = tuple(Stock(region, stocks_by_region[region]) for region in region_ids)

    session = admit(policy=policy_copy, topology=topology, campaign_id=campaign_id,
                    turn=expected_source_turn, staging=staging, target=target,
                    soldiers=soldiers, stocks=stock_records)
    bindings_digest = _digest([{"region_id": binding.region_id, "name": binding.name,
                                "neighbors": list(binding.neighbors)}
                               for binding in canonical_bindings])
    source = _source_identity(expected_source_turn, row_count, columns)
    plan = AdmissionPlan(CONTRACT, ADAPTER, source, campaign_id, civ_id, expected_source_turn,
                         staging, target, roster, canonical_bindings,
                         bindings_digest, policy_copy, topology, session.state.soldiers,
                         kit_pairs, morale_pairs, session.state.stocks, session,
                         session.cursor.initial_state_digest, "")
    # The digest covers the canonical plan body, so it is filled in from that body.
    return replace(plan, plan_digest=_digest(_plan_body(plan)))


def _plain(value: Any) -> Any:
    """Recursively plain-JSON view of a frozen record.

    Tuple-valued fields become JSON arrays, so ``plan_document(plan)`` equals
    ``json.loads(plan_bytes(plan))``. Policy objects are not mutated: this reads
    them and rebuilds equivalent plain containers.
    """
    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: _plain(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    if isinstance(value, MappingABC):
        return {str(key): _plain(item) for key, item in value.items()}
    return value


def _plan_body(plan: AdmissionPlan) -> dict[str, Any]:
    """Canonical plan content, excluding the plan digest itself.

    Three explicit groups, never mixed: what was read (``source``), what the
    caller supplied and the adapter copied (``inputs``), and what the reviewed
    kernel admitted from those inputs (``admission``).
    """
    state = plan.session.state
    return {
        "adapter": plan.adapter,
        "contract": plan.contract,
        "source": {
            "adapter": plan.source.adapter,
            "columns": list(plan.source.columns),
            "column_digests": [list(pair) for pair in plan.source.column_digests],
            "content_digest": plan.source.content_digest,
            "contract": plan.source.contract,
            "row_count": plan.source.row_count,
            "source_turn": plan.source.source_turn,
            "stage": plan.source.stage,
        },
        "inputs": {
            "admission_turn": plan.admission_turn,
            "campaign_id": plan.campaign_id,
            "civ_id": plan.civ_id,
            "kits": [list(pair) for pair in plan.kits],
            "morale": [list(pair) for pair in plan.morale],
            "policy": _plain(plan.policy),
            "region_binding_digest": plan.region_binding_digest,
            "region_bindings": [{"name": binding.name, "neighbors": list(binding.neighbors),
                                 "region_id": binding.region_id}
                                for binding in plan.region_bindings],
            "selected_ids": list(plan.selected_ids),
            "staging": plan.staging,
            "stocks": [[stock.region, stock.rations] for stock in plan.stocks],
            "target": plan.target,
        },
        "admission": {
            "admission_turn": state.admission_turn,
            "campaign_id": state.campaign_id,
            "contract": state.contract,
            "cursor_receipts": len(plan.session.cursor.receipts),
            "initial_food": state.initial_food,
            "initial_state_digest": plan.initial_state_digest,
            "original_ids": list(state.original_ids),
            "phase": state.phase,
            "policy_digest": state.policy_digest,
            "policy_id": state.policy_id,
            "soldiers": [_plain(soldier) for soldier in state.soldiers],
            "stocks": [[stock.region, stock.rations] for stock in state.stocks],
            "topology_digest": state.topology_digest,
            "topology_id": state.topology_id,
            "topology_regions": [[region.region_id, list(region.neighbors)]
                                 for region in plan.topology.regions],
            "turn": state.turn,
        },
    }


def plan_document(plan: AdmissionPlan) -> dict[str, Any]:
    """Deterministic plain-data view of a plan; safe to serialize or hash."""
    return {**_plan_body(plan), "plan_digest": plan.plan_digest}


def plan_bytes(plan: AdmissionPlan) -> bytes:
    """Canonical plan bytes; identical across processes for identical inputs.

    These bytes include the ``plan_digest`` key, so hashing them does not
    reproduce that digest. The digest covers the canonical plan body only:
    ``sha256`` over the same canonical encoding with ``plan_digest`` removed.
    """
    return _canonical(plan_document(plan))