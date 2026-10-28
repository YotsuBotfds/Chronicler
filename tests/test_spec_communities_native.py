"""The bond-type mirror (``ffi_constants.BOND_TYPES``) against the native
extension's behaviour: the kin code is the one bond type that is protected
from eviction and refused by a symmetric upsert (kin bonds form at birth),
marriage is protected and symmetric, and the mentor bond is asymmetric
(chronicler-agents/src/relationships.rs, ffi/mod.rs apply_relationship_ops).
Community method 2's kin-only exclusion reads the kin code from the mirror."""
from __future__ import annotations

import pytest

from chronicler.ffi_constants import BOND_KIN, BOND_MARRIAGE, BOND_MENTOR, BOND_TYPES

pytestmark = pytest.mark.native

UPSERT_DIRECTED, UPSERT_SYMMETRIC = 0, 1
REL_SLOTS = 8


def _simulator(agents: int):
    pa = pytest.importorskip("pyarrow")
    ca = pytest.importorskip("chronicler_agents")
    sim_class = getattr(ca, "AgentSimulator", None)
    if not isinstance(sim_class, type):
        pytest.skip("chronicler_agents is not a real native extension")
    sim = sim_class(num_regions=1, seed=7)
    sim.set_region_state(pa.record_batch({
        "region_id": pa.array([0], type=pa.uint16()),
        "terrain": pa.array([0], type=pa.uint8()),
        "carrying_capacity": pa.array([agents], type=pa.uint16()),
        "population": pa.array([agents], type=pa.uint16()),
        "soil": pa.array([0.8], type=pa.float32()),
        "water": pa.array([0.6], type=pa.float32()),
        "forest_cover": pa.array([0.3], type=pa.float32()),
    }))
    ids = sim.get_snapshot().column("id").to_pylist()
    assert len(ids) >= REL_SLOTS + 2
    return sim, ids


def _ops(rows):
    import pyarrow as pa

    return pa.record_batch({
        "op_type": pa.array([r[0] for r in rows], type=pa.uint8()),
        "agent_a": pa.array([r[1] for r in rows], type=pa.uint32()),
        "agent_b": pa.array([r[2] for r in rows], type=pa.uint32()),
        "bond_type": pa.array([r[3] for r in rows], type=pa.uint8()),
        "sentiment": pa.array([r[4] for r in rows], type=pa.int8()),
        "formed_turn": pa.array([r[5] for r in rows], type=pa.uint16()),
    })


def _native_traits(code: int) -> tuple[bool, bool]:
    """(refused by a symmetric upsert, protected from eviction) of a bond type."""
    sim, ids = _simulator(REL_SLOTS + 4)
    a, b = ids[0], ids[1]
    sim.apply_relationship_ops(_ops([(UPSERT_SYMMETRIC, a, b, code, 30, 1)]))
    refused = not any(rel[0] == b and rel[2] == code for rel in sim.get_agent_relationships(a) or ())
    sim, ids = _simulator(REL_SLOTS + 4)
    a, targets, newcomer = ids[0], ids[1:REL_SLOTS + 1], ids[REL_SLOTS + 1]
    sim.apply_relationship_ops(_ops([(UPSERT_DIRECTED, a, t, code, 10, 1) for t in targets]))
    assert len(sim.get_agent_relationships(a)) == REL_SLOTS
    friend = BOND_TYPES["friend"]
    sim.apply_relationship_ops(_ops([(UPSERT_DIRECTED, a, newcomer, friend, 100, 2)]))
    protected = not any(rel[0] == newcomer for rel in sim.get_agent_relationships(a))
    return refused, protected


def test_native_bond_codes_match_the_mirror():
    traits = {code: _native_traits(code) for code in sorted(BOND_TYPES.values())}
    assert [code for code, (refused, protected) in traits.items() if refused and protected] == [BOND_KIN]
    assert [code for code, (refused, protected) in traits.items() if protected and not refused] == [BOND_MARRIAGE]
    assert [code for code, (refused, protected) in traits.items() if refused and not protected] == [BOND_MENTOR]
