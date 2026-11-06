"""Workshop operating wear (PL2, ``--operating-wear``) without the native extension.

The native stand-in of ``tests/test_apprenticeship.py`` drives the real L1
workshop, RS1 and operating-wear code through the livelihoods hooks. Covers the
reference arm ``W_wear`` (``--workshops --operating-wear``) against ``W_operate``
(``--workshops``), RS1 implying the same wear, the records, the registry and
prerequisites, round trips and the feature-off identity.
"""
from __future__ import annotations

import json
import pickle
from types import SimpleNamespace

import pytest
from test_apprenticeship import SETTLEMENT, SITE_REGION, FakeSim, _qualify, _turn
from test_apprenticeship import _world as _rs1_world

from chronicler import apprenticeship as A
from chronicler import livelihoods as L
from chronicler import operating_wear as OW
from chronicler import workshops as W
from chronicler.batch_manifest import SIMULATION_ARG_KEYS
from chronicler.cities_state import City, CityState
from chronicler.feature_catalog import REQUIREMENTS
from chronicler.livelihoods_state import LIVELIHOODS_SWITCHES, LivelihoodsState
from chronicler.operating_wear_state import COUNTERS
from chronicler.workshops_state import WorkshopState


def _world(wear=True, rank=1, treasury=10_000):
    civs = [SimpleNamespace(name=f"Civ{i}", treasury=treasury) for i in range(2)]
    world = SimpleNamespace(
        turn=1, agent_mode="hybrid", civilizations=civs,
        regions=[SimpleNamespace(name=f"R{i}", controller="Civ0", stockpile=SimpleNamespace(goods={"crafts": 0.0}))
                 for i in range(4)],
        cities=CityState(cities=[City(settlement_id=SETTLEMENT, region=SITE_REGION, name="C1", founded_turn=0,
                                      founder=0, rank=rank, size=10.0)]),
        livelihoods=LivelihoodsState(), war_state=SimpleNamespace(armies=[]), scholarship=None)
    world.livelihoods.workshops = WorkshopState(mode="operate")
    if wear:
        OW.set_operating_wear_enabled(world, True)
    return world


def _site(world):
    return world.livelihoods.workshops.sites[0]


def _build(world, sim):
    for _ in range(W.CONSTRUCTION_COST // W.INSTALLMENT):
        _turn(world, sim)
    assert _site(world).asset == "open" and _site(world).condition == 1.0


def _args(**given):
    args = SimpleNamespace(**{key: None for key in L.LIVELIHOODS_ARG_KEYS})
    for key, value in given.items():
        setattr(args, key, value)
    return args


def test_the_switch_alone_wears_every_funded_operating_site_and_nothing_else():
    world, sim = _world(), FakeSim(range(1, 5))
    _build(world, sim)                                   # construction turns are not worn
    state = world.livelihoods.operating_wear
    assert state.counters.get("operating_site_turns", 0) == 0 and state.frame == []
    for turn in range(1, 4):
        _turn(world, sim)
        assert _site(world).condition == pytest.approx(1.0 - turn * OW.OPERATING_WEAR)
        r = state.frame[0]
        assert (r.site, r.region, r.wear, r.upkeep_offset, r.net_wear, r.qualified_on_crew, r.full_offset) == (
            0, SITE_REGION, OW.OPERATING_WEAR, 0.0, OW.OPERATING_WEAR, [], False)
        assert r.condition_after == pytest.approx(_site(world).condition) and r.turn == world.turn - 1
    # The wear is a maintenance assumption only: the crew's craft time is untouched.
    receipt = world.livelihoods.workshops.frame[0]
    assert receipt.allocated == pytest.approx(receipt.work_available)
    assert receipt.craft_ceiling == pytest.approx(W.K_RAW_PER_WORK * receipt.work_available)
    assert state.counters["wear"] == pytest.approx(3 * OW.OPERATING_WEAR) and state.counters["turns"] == 9
    assert state.counters.get("covered_site_turns", 0) == 0
    # An unfunded built site keeps L1's own wear only.
    world.civilizations[0].treasury = 0
    before = _site(world).condition
    _turn(world, sim)
    assert _site(world).condition == pytest.approx(before - W.CONDITION_WEAR) and state.frame == []
    world.civilizations[0].treasury = 10_000
    # Below the operating floor the worn site stops until the L1 lump repairs it.
    _site(world).condition = W.OPERATE_CONDITION + 0.01
    _turn(world, sim)
    assert _site(world).condition < W.OPERATE_CONDITION
    _turn(world, sim)
    assert world.livelihoods.workshops.frame[0].paid.get("repair") == W.REPAIR_COST
    assert state.counters["repairs"] == 1
    assert _site(world).condition == pytest.approx(1.0 - OW.OPERATING_WEAR)


def test_the_reference_arm_without_the_switch_does_not_wear_and_has_no_state():
    world, sim = _world(wear=False), FakeSim(range(1, 5))
    for _ in range(12):
        _turn(world, sim)
    assert world.livelihoods.operating_wear is None and _site(world).condition == 1.0
    assert "operating_wear" not in L.livelihoods_snapshot_fields(world)["livelihoods"]
    assert "operating_wear" not in L.livelihoods_feature_flags(world)


def test_apprenticeship_implies_the_wear_and_the_switch_then_only_records_it(monkeypatch):
    monkeypatch.setattr(A, "SERVICE_TURNS", 100)
    monkeypatch.setattr(A, "COMPLETION_TURNS", 4)

    def run(with_switch, rules):
        world, sim = _rs1_world(rules=rules), FakeSim(range(1, 5))
        sim.add(30, settlement=0, age=20)
        if with_switch:
            OW.set_operating_wear_enabled(world, True)
        for _ in range(W.CONSTRUCTION_COST // W.INSTALLMENT):
            _turn(world, sim)
        _qualify(world, sim, [4])
        for _ in range(5):
            _turn(world, sim)
        return world

    for rules in (1, 2):
        implied, recorded = run(False, rules), run(True, rules)
        assert implied.livelihoods.operating_wear is None
        a, b = implied.livelihoods, recorded.livelihoods
        assert a.workshops.model_dump_json() == b.workshops.model_dump_json()
        assert a.apprenticeship.model_dump_json() == b.apprenticeship.model_dump_json()
        assert _site(implied).condition < 1.0
        state = b.operating_wear
        rs1 = b.apprenticeship.frame[0]
        r = state.frame[0]
        assert (r.wear, r.upkeep_offset, r.net_wear, r.qualified_on_crew) == (
            rs1.wear, rs1.upkeep_offset, rs1.net_wear, rs1.qualified_on_crew)
        assert r.upkeep_offset > 0.0 and state.counters["covered_site_turns"] == 5
        for key in ("upkeep_offset", "wear", "operating_site_turns"):
            assert state.counters[key] == pytest.approx(b.apprenticeship.counters[key]), key
        snap = OW.snapshot_summary(recorded)
        assert snap["with_apprenticeship"] is True and snap["receipts"][0]["qualified_on_crew"] == r.qualified_on_crew
        assert 4 in r.qualified_on_crew


def test_registry_cli_prerequisites_and_conflicts():
    # Appended after the recovery-skills block (later switches append after it).
    assert LIVELIHOODS_SWITCHES.index("operating_wear") == LIVELIHOODS_SWITCHES.index("clearing_protection") + 1
    assert L.LIVELIHOODS_ARG_KEYS.index("operating_wear") == L.LIVELIHOODS_ARG_KEYS.index("clearing_protection_mode") + 1
    assert "operating_wear" in SIMULATION_ARG_KEYS and "operating_wear" not in L.LIVELIHOODS_CHOICES
    assert REQUIREMENTS["operating_wear"] == REQUIREMENTS["apprenticeship"]
    from chronicler.main import _build_parser
    assert _build_parser().parse_args([]).operating_wear is None
    assert _build_parser().parse_args(["--operating-wear"]).operating_wear is True
    assert L.livelihoods_arguments(_args(operating_wear=False)) == ["--no-operating-wear"]
    world = _world(wear=False)
    with pytest.raises(ValueError, match="--operating-wear requires --workshops in operate mode"):
        L.configure_livelihoods(world, _args(operating_wear=True), agent_mode="shadow")
    world.livelihoods.workshops.mode = "observe"
    with pytest.raises(ValueError, match="--operating-wear requires"):
        L.configure_livelihoods(world, _args(operating_wear=True), agent_mode="hybrid")
    world.livelihoods.workshops.mode = "operate"
    bare = _world(wear=False)
    bare.livelihoods = None
    with pytest.raises(ValueError, match="--operating-wear requires"):
        L.configure_livelihoods(bare, _args(operating_wear=True), agent_mode="hybrid")
    L.configure_livelihoods(world, _args(operating_wear=True), agent_mode="hybrid")
    assert OW.operating_wear_active(world) and L.livelihoods_feature_flags(world)["operating_wear"] is True
    # An exact resume cannot add (or drop) the switch silently.
    plain = _world(wear=False)
    assert L.livelihoods_resume_conflicts(plain, _args(operating_wear=True), {}) == [
        "--operating-wear True conflicts with the checkpoint (saved: False)"]
    assert L.livelihoods_resume_conflicts(world, _args(operating_wear=None), {}) == []
    # Disabled: inert, the record kept.
    L.configure_livelihoods(world, _args(operating_wear=False), agent_mode="hybrid")
    assert not OW.operating_wear_active(world) and world.livelihoods.operating_wear is not None


def test_round_trips_rollback_and_the_dated_snapshot():
    world, sim = _world(), FakeSim(range(1, 5))
    _build(world, sim)
    _turn(world, sim)
    text = world.livelihoods.model_dump_json()
    back = pickle.loads(pickle.dumps(LivelihoodsState.model_validate_json(text)))
    assert back.model_dump_json() == text and back.operating_wear._pending is None
    snap = L.livelihoods_snapshot_fields(world)["livelihoods"]["operating_wear"]
    assert (snap["schema_version"], snap["stage"], snap["source_turn"]) == (1, "PL2", world.turn - 1)
    assert snap["receipts"][0]["net_wear"] == OW.OPERATING_WEAR and set(snap["counters"]) <= set(COUNTERS)
    assert json.loads(json.dumps(snap)) == snap and snap["with_apprenticeship"] is False
    world.turn += 1
    assert OW.snapshot_summary(world)["receipts"] is None
    world.turn -= 1
    # A failed Phase 2 records nothing (the wear is applied at settlement only).
    before = world.livelihoods.operating_wear.model_dump_json()
    condition = _site(world).condition
    with pytest.raises(RuntimeError, match="economy tick failed"):
        _turn(world, sim, fail="phase2")
    assert world.livelihoods.operating_wear.model_dump_json() == before
    assert world.livelihoods.operating_wear._pending is None and _site(world).condition == condition


def test_no_operating_wear_under_apprenticeship_keeps_rs1s_wear_and_only_stops_the_records(monkeypatch):
    """Review B (doc): ``--no-operating-wear`` does not stop the wear while
    ``--apprenticeship`` is on, because RS1 implies it; the switch's record is kept
    and stops updating, and its snapshot key goes."""
    monkeypatch.setattr(A, "SERVICE_TURNS", 100)
    world, sim = _rs1_world(rules=2), FakeSim(range(1, 5))
    L.configure_livelihoods(world, _args(operating_wear=True), agent_mode="hybrid")
    for _ in range(W.CONSTRUCTION_COST // W.INSTALLMENT + 2):
        _turn(world, sim)
    state = world.livelihoods.operating_wear
    frame_turn, counted = state.frame_turn, state.counters["operating_site_turns"]
    L.configure_livelihoods(world, _args(operating_wear=False), agent_mode="hybrid")
    before = _site(world).condition
    _turn(world, sim)
    assert _site(world).condition == pytest.approx(before - OW.OPERATING_WEAR)     # RS1's own wear
    assert world.livelihoods.apprenticeship.frame[0].net_wear == OW.OPERATING_WEAR
    assert state.frame_turn == frame_turn and state.counters["operating_site_turns"] == counted
    fields = L.livelihoods_snapshot_fields(world)["livelihoods"]
    assert "operating_wear" not in fields and "apprenticeship" in fields
    assert L.livelihoods_feature_flags(world)["operating_wear"] is False
