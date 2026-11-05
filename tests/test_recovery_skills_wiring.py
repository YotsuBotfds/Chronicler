"""RS0 groundwork of the recovery-skills phase, without the native extension.

Five livelihoods switches registered with inert stub modules, their CLI and
manifest wiring, prerequisites, persisted state, the cross-lane API stubs
and the guarded seams in :mod:`chronicler.workshops`. Nothing here runs a
mechanism: RS0 only guarantees that the switches exist, stay default-off and
leave every other result unchanged.
"""
from __future__ import annotations

import json
import pickle
from types import SimpleNamespace

import pyarrow as pa
import pytest

from chronicler import apprenticeship as A
from chronicler import clearing_protection as CP
from chronicler import remittances as RM
from chronicler import repair_projects as RP
from chronicler import veteran_reintegration as VR
from chronicler import workshops as W
from chronicler.batch_manifest import SIMULATION_ARG_KEYS, simulation_config
from chronicler.cities_state import City, CityState
from chronicler.expansion_features import (
    expansion_arguments, expansion_feature_flags, expansion_snapshot_fields,
)
from chronicler.livelihoods import (
    LIVELIHOODS_ARG_KEYS, LIVELIHOODS_CHOICES, configure_livelihoods, livelihoods_arguments,
    livelihoods_feature_flags, livelihoods_snapshot_fields,
)
from chronicler.livelihoods_state import LIVELIHOODS_SWITCHES, LivelihoodsState
from chronicler.main import _build_parser
from chronicler.veteran_reintegration_state import OUTCOMES
from chronicler.workshops_state import WorkshopState
from chronicler.world_gen import generate_world

RS = ("apprenticeship", "repair_projects", "veteran_reintegration", "remittances", "clearing_protection")
#: Packages whose lane replaced the inert RS0 stub (their own tests cover them).
IMPLEMENTED = {"clearing_protection", "remittances", "veteran_reintegration", "apprenticeship"}
MODE_KEYS = {"apprenticeship": "apprenticeship_mode", "repair_projects": "repair_mode",
             "veteran_reintegration": "veteran_mode", "remittances": "remittance_mode",
             "clearing_protection": "clearing_protection_mode"}
MODES = {"apprenticeship_mode": ("train", "no_qualification"), "repair_mode": ("repair", "cost_only"),
         "veteran_mode": ("priority", "record_only"), "remittance_mode": ("send", "record_only"),
         "clearing_protection_mode": ("enforced", "cost_only")}
MODULES = {"apprenticeship": A, "repair_projects": RP, "veteran_reintegration": VR,
           "remittances": RM, "clearing_protection": CP}
#: Switches that leave workshop operation untouched while nobody qualifies
#: (apprenticeship adds operating wear and upkeep time: tests/test_apprenticeship.py).
STUBS = tuple(name for name in RS if name != "apprenticeship")
#: Flags that satisfy every RS prerequisite on a world with cities.
ALL_ON = ["--workshops", "--apprenticeship", "--repair-projects", "--veteran-reintegration",
          "--remittances", "--clearing-protection"]


@pytest.fixture
def world():
    w = generate_world(seed=42, num_regions=6, num_civs=2)
    w.cities = CityState()
    w.agent_mode = "hybrid"
    return w


def parse(*argv):
    return _build_parser().parse_args(list(argv))


# --- Registry, CLI and manifest ---------------------------------------------


def test_switches_are_appended_in_order_with_their_choices():
    assert LIVELIHOODS_SWITCHES[-5:] == RS
    assert LIVELIHOODS_SWITCHES[:9] == ("workshops", "food_allocation", "timber_stock", "grain_convoys",
                                        "commons_rules", "learning_cohorts", "workshop_payroll",
                                        "relocation_costs", "local_budgets")
    assert {k: LIVELIHOODS_CHOICES[k] for k in MODES} == MODES
    assert list(LIVELIHOODS_CHOICES)[-5:] == list(MODES)
    tail = tuple(k for name in RS for k in (name, MODE_KEYS[name]))
    assert LIVELIHOODS_ARG_KEYS[-10:] == tail
    assert set(LIVELIHOODS_ARG_KEYS) <= set(SIMULATION_ARG_KEYS)
    # Each switch has its module, state field and protocol functions.
    for name, module in MODULES.items():
        assert name in LivelihoodsState.model_fields
        for fn in (f"set_{name}_enabled", f"{name}_active", "snapshot_summary"):
            assert callable(getattr(module, fn)), (name, fn)
        if name in IMPLEMENTED:
            continue
        # RS0 registers no phase hook: nothing runs during a turn yet.
        for hook in ("prepare_phase2", "finish_phase2", "rollback_phase2", "before_agent_tick",
                     "after_agent_tick", "phase10_before_reserves", "phase10"):
            assert not hasattr(module, hook), (name, hook)


def test_parser_defaults_are_absent_and_explicit_values_are_forwarded():
    default = parse()
    keys = [k for name in RS for k in (name, MODE_KEYS[name])]
    assert all(getattr(default, key) is None for key in keys)
    assert not set(keys) & set(simulation_config(default))
    assert livelihoods_arguments(default) == []
    args = parse("--apprenticeship", "--apprenticeship-mode", "no_qualification", "--no-repair-projects",
                 "--veteran-reintegration", "--veteran-mode", "record_only", "--remittances",
                 "--remittance-mode=record_only", "--clearing-protection", "--clearing-protection-mode",
                 "cost_only", "--repair-mode", "cost_only")
    assert (args.apprenticeship, args.apprenticeship_mode, args.repair_projects, args.repair_mode) == \
        (True, "no_qualification", False, "cost_only")
    assert (args.veteran_reintegration, args.veteran_mode, args.remittances, args.remittance_mode) == \
        (True, "record_only", True, "record_only")
    assert (args.clearing_protection, args.clearing_protection_mode) == (True, "cost_only")
    config = simulation_config(args)
    assert {k: config[k] for k in keys} == {k: getattr(args, k) for k in keys}
    forwarded = livelihoods_arguments(args)
    assert forwarded == ["--apprenticeship", "--apprenticeship-mode=no_qualification", "--no-repair-projects",
                         "--repair-mode=cost_only", "--veteran-reintegration", "--veteran-mode=record_only",
                         "--remittances", "--remittance-mode=record_only", "--clearing-protection",
                         "--clearing-protection-mode=cost_only"]
    assert set(forwarded) <= set(expansion_arguments(args))
    # Child runs parse the forwarded flags back to the same values.
    again = parse(*forwarded)
    assert all(getattr(again, k) == getattr(args, k) for k in keys)
    with pytest.raises(SystemExit):
        parse("--repair-mode", "fix")
    with pytest.raises(ValueError, match="remittance_mode"):
        livelihoods_arguments(SimpleNamespace(remittance_mode="sometimes"))


def test_a_never_enabled_world_has_no_container_flag_or_snapshot_key(world):
    before = world.model_dump_json()
    args = parse("--no-apprenticeship", "--no-repair-projects", "--no-veteran-reintegration",
                 "--no-remittances", "--no-clearing-protection", "--apprenticeship-mode", "train")
    configure_livelihoods(world, args, agent_mode="hybrid")
    assert world.livelihoods is None and world.model_dump_json() == before
    assert not set(RS) & set(expansion_feature_flags(world))
    assert "livelihoods" not in expansion_snapshot_fields(world)
    assert "livelihoods" not in json.loads(world.model_dump_json())
    # A world with only older switches gains no RS key either.
    configure_livelihoods(world, parse("--workshops"), agent_mode="hybrid")
    dumped = json.loads(world.model_dump_json())["livelihoods"]
    assert set(dumped) == {"schema_version", "workshops"}
    assert set(livelihoods_feature_flags(world)) == {"workshops"}
    assert set(livelihoods_snapshot_fields(world)["livelihoods"]) == {"schema_version", "workshops"}


# --- Prerequisites ------------------------------------------------------------


def test_prerequisites_refuse_before_any_change(world):
    cases = [
        (["--apprenticeship"], "hybrid", "operate mode"),
        (["--workshops", "--workshop-mode", "observe", "--apprenticeship"], "hybrid", "operate mode"),
        (["--repair-projects"], "hybrid", "grain-storage"),
        (["--veteran-reintegration"], "hybrid", "one of --workshops"),
        (["--remittances"], "shadow", "--remittances requires --agents hybrid"),
    ]
    for argv, mode, match in cases:
        with pytest.raises(ValueError, match=match):
            configure_livelihoods(world, parse(*argv), agent_mode=mode)
        assert world.livelihoods is None, argv
    # With saved workshops in operate mode, a non-hybrid run still refuses each.
    configure_livelihoods(world, parse("--workshops"), agent_mode="hybrid")
    saved = world.model_dump_json()
    for flag, match in (("--apprenticeship", "operate mode"), ("--repair-projects", "--repair-projects requires"),
                        ("--veteran-reintegration", "--veteran-reintegration requires")):
        for mode in ("off", "shadow", "demographics-only"):
            with pytest.raises(ValueError, match=match):
                configure_livelihoods(world, parse(flag), agent_mode=mode)
    assert world.model_dump_json() == saved
    # Repair projects accept workshops in any mode (observe builds nothing to repair).
    costed = generate_world(seed=4, num_regions=6, num_civs=2)
    costed.cities = CityState()
    configure_livelihoods(costed, parse("--workshops", "--workshop-mode", "cost_only", "--repair-projects"),
                          agent_mode="hybrid")
    assert costed.livelihoods.repair_projects.enabled
    # Clearing protection has no prerequisite: any agent mode, no cities.
    bare = generate_world(seed=3, num_regions=4, num_civs=2)
    configure_livelihoods(bare, parse("--clearing-protection"), agent_mode="off")
    assert bare.livelihoods.clearing_protection.enabled
    assert CP.clearing_protection_active(bare)


def test_prerequisites_read_saved_state_when_a_switch_is_omitted(world):
    configure_livelihoods(world, parse("--workshops"), agent_mode="hybrid")
    # Saved workshops in operate mode satisfy apprenticeship, repair and veterans.
    configure_livelihoods(world, parse("--apprenticeship"), agent_mode="hybrid")
    configure_livelihoods(world, parse("--repair-projects"), agent_mode="hybrid")
    configure_livelihoods(world, parse("--veteran-reintegration"), agent_mode="hybrid")
    # An explicit disable, or another saved mode, does not.
    for argv in (["--no-workshops", "--apprenticeship"], ["--workshop-mode", "cost_only", "--apprenticeship"]):
        with pytest.raises(ValueError, match="operate mode"):
            configure_livelihoods(world, parse(*argv), agent_mode="hybrid")
    with pytest.raises(ValueError, match="--workshops or --grain-storage"):
        configure_livelihoods(world, parse("--no-workshops", "--repair-projects"), agent_mode="hybrid")
    assert world.livelihoods.workshops.enabled and world.livelihoods.workshops.mode == "operate"
    # Veterans need one consumer: a saved apprenticeship or repair switch is enough.
    other = generate_world(seed=5, num_regions=6, num_civs=2)
    other.cities = CityState()
    configure_livelihoods(other, parse("--workshops", "--repair-projects"), agent_mode="hybrid")
    configure_livelihoods(other, parse("--no-workshops"), agent_mode="hybrid")
    configure_livelihoods(other, parse("--veteran-reintegration"), agent_mode="hybrid")
    configure_livelihoods(other, parse("--no-repair-projects"), agent_mode="hybrid")
    with pytest.raises(ValueError, match="one of --workshops"):
        configure_livelihoods(other, parse("--no-veteran-reintegration", "--veteran-reintegration"),
                              agent_mode="hybrid")


def test_repair_projects_accept_grain_storage_without_workshops():
    from chronicler.grain_reserves import set_grain_reserves_enabled
    from chronicler.grain_storage import enable_storage
    w = generate_world(seed=42, num_regions=3, num_civs=2)
    w.agent_mode = "hybrid"
    set_grain_reserves_enabled(w, True)
    with pytest.raises(ValueError, match="grain-storage"):
        configure_livelihoods(w, parse("--repair-projects"), agent_mode="hybrid")
    enable_storage(w)
    configure_livelihoods(w, parse("--repair-projects", "--repair-mode", "cost_only"), agent_mode="hybrid")
    assert w.livelihoods.repair_projects.mode == "cost_only" and RP.repair_projects_active(w)
    # Grain storage alone does not satisfy veteran reintegration's consumers.
    configure_livelihoods(w, parse("--veteran-reintegration"), agent_mode="hybrid")
    assert VR.veteran_reintegration_active(w)


# --- State, modes and observation ---------------------------------------------


def test_each_stub_switch_enables_records_its_mode_and_observes_only_itself(world):
    configure_livelihoods(world, parse(*ALL_ON), agent_mode="hybrid")
    state = world.livelihoods
    for name, module in MODULES.items():
        assert getattr(module, f"{name}_active")(world), name
        if name in IMPLEMENTED:
            continue
        sub = getattr(state, name)
        assert (sub.schema_version, sub.enabled, sub.mode, sub.counters) == \
            (1, True, MODES[MODE_KEYS[name]][0], {}), name
        assert getattr(module, f"{name}_active")(world), name
        assert module.snapshot_summary(world) == {"schema_version": 1, "stage": "RS0", "enabled": True,
                                                  "mode": MODES[MODE_KEYS[name]][0], "counters": {}}
    flags = livelihoods_feature_flags(world)
    assert {k: flags[k] for k in RS} == dict.fromkeys(RS, True)
    snap = livelihoods_snapshot_fields(world)["livelihoods"]
    assert set(RS) <= set(snap) and snap["schema_version"] == 1
    # Nothing but the switch changed: no site, no worker, no money.
    assert world.livelihoods.workshops.sites == []
    assert all(c.treasury == generate_world(seed=42, num_regions=6, num_civs=2).civilizations[i].treasury
               for i, c in enumerate(world.civilizations))


def test_an_omitted_flag_keeps_saved_state_and_a_mode_alone_does_nothing(world):
    configure_livelihoods(world, parse(*ALL_ON, "--apprenticeship-mode", "no_qualification",
                                       "--remittance-mode", "record_only"), agent_mode="hybrid")
    state = world.livelihoods
    assert state.apprenticeship.mode == "no_qualification" and state.remittances.mode == "record_only"
    # Omitted switches and modes keep the saved state, as other packages do.
    configure_livelihoods(world, parse(), agent_mode="hybrid")
    assert state.apprenticeship.mode == "no_qualification" and state.apprenticeship.enabled
    # Re-enabling without a mode keeps the saved mode; a disable keeps it too.
    configure_livelihoods(world, parse("--apprenticeship", "--no-remittances"), agent_mode="hybrid")
    assert state.apprenticeship.mode == "no_qualification"
    assert not state.remittances.enabled and state.remittances.mode == "record_only"
    assert not RM.remittances_active(world)
    assert "remittances" not in livelihoods_snapshot_fields(world)["livelihoods"]
    assert livelihoods_feature_flags(world)["remittances"] is False
    # An explicit mode changes the saved one.
    configure_livelihoods(world, parse("--remittances", "--remittance-mode", "send",
                                       "--clearing-protection-mode", "cost_only"), agent_mode="hybrid")
    assert state.remittances.enabled and state.remittances.mode == "send"
    # A mode flag without its switch leaves the saved mode (the existing protocol).
    assert state.clearing_protection.mode == "enforced"
    configure_livelihoods(world, parse("--clearing-protection", "--clearing-protection-mode", "cost_only"),
                          agent_mode="hybrid")
    assert state.clearing_protection.mode == "cost_only"


def test_activity_follows_prerequisite_state_at_run_time(world):
    configure_livelihoods(world, parse(*ALL_ON), agent_mode="hybrid")
    world.agent_mode = "shadow"
    assert not any(getattr(MODULES[n], f"{n}_active")(world) for n in RS[:4])
    assert CP.clearing_protection_active(world)
    world.agent_mode = "hybrid"
    world.livelihoods.workshops.mode = "cost_only"
    # Apprenticeship needs operate mode; repair projects accept a cost_only site.
    assert not A.apprenticeship_active(world) and RP.repair_projects_active(world)
    assert VR.veteran_reintegration_active(world) and RM.remittances_active(world)


def test_state_round_trips_through_json_and_pickle(world):
    configure_livelihoods(world, parse(*ALL_ON, "--veteran-mode", "record_only"), agent_mode="hybrid")
    world.livelihoods.repair_projects.counters["opened"] = 2
    text = world.model_dump_json()
    back = type(world).model_validate_json(text)
    assert back.model_dump_json() == text
    assert back.livelihoods.veteran_reintegration.mode == "record_only"
    assert back.livelihoods.repair_projects.counters == {"opened": 2}
    assert pickle.loads(pickle.dumps(world.livelihoods)).model_dump_json() == world.livelihoods.model_dump_json()
    # An older container pickled before RS0 restores with the new switches absent.
    raw = LivelihoodsState().__getstate__()
    for name in RS:
        raw["__dict__"].pop(name)
    old = LivelihoodsState.__new__(LivelihoodsState)
    old.__setstate__(raw)
    assert all(getattr(old, name) is None for name in RS)
    assert old.model_dump_json() == LivelihoodsState().model_dump_json()
    with pytest.raises(ValueError):
        type(world).model_validate_json(text.replace('"record_only"', '"sometimes"'))


# --- Cross-lane API stubs -------------------------------------------------------


def test_cross_lane_stubs_are_inert(world):
    configure_livelihoods(world, parse(*ALL_ON), agent_mode="hybrid")
    before = world.model_dump_json()
    # RS1 landed: with no qualification held its cross-lane API is still empty.
    assert A.qualified_ids(world, 0) == [] and VR.priority_ids(world, 3) == []
    assert RP.legacy_workshop_repair_allowed(world) is True
    for kind in OUTCOMES:
        assert VR.note_outcome(world, 7, kind, turn=3, detail={"site": 0}) is None
    with pytest.raises(ValueError, match="unknown veteran outcome"):
        VR.note_outcome(world, 7, "placed:army", turn=3)
    assert world.model_dump_json() == before
    assert OUTCOMES == ("placed:crew", "placed:apprentice", "placed:repair", "waiting", "remobilised",
                        "died", "migrated", "control_lost", "expired", "pool_reset")


# --- workshops.py seams -----------------------------------------------------------


def _ws_world(mode="operate", treasury=(1000,)):
    civs = [SimpleNamespace(name=f"Civ{i}", treasury=t) for i, t in enumerate(treasury)]
    world = SimpleNamespace(turn=20, civilizations=civs, agent_mode="hybrid",
                            regions=[SimpleNamespace(name=f"R{i}", controller="Civ0") for i in range(6)],
                            cities=CityState(cities=[_city(1, 2, 2), _city(2, 4, 1)]),
                            livelihoods=LivelihoodsState(), war_state=SimpleNamespace(armies=[]))
    world.livelihoods.workshops = WorkshopState(mode=mode)
    return world


def _city(sid, region, rank=1, size=10.0):
    return City(settlement_id=sid, region=region, name=f"C{sid}", founded_turn=1, founder=0, rank=rank, size=size)


class _Sim:
    """Records each planner call exactly as made (keyword arguments included)."""

    def __init__(self):
        self.calls, self.inputs = [], None

    def plan_workshop_crews(self, requests, enlisted, turn=None, **kwargs):
        self.calls.append((list(requests), list(enlisted), turn, dict(kwargs)))
        priority = kwargs.get("priority_ids") or []
        out = []
        for site, region, settlement, diverted, _ in requests:
            crew = [a for a in priority if a // 100 == region] + [10 + site, 20 + site]
            out.append((site, region, settlement, 3, 0, 0, 0, len(crew), crew[:2], [30, 40], 2 * diverted))
        return out

    def take_craft_inputs(self):
        out, self.inputs = self.inputs, None
        return out


def _batch(n=6):
    return pa.record_batch({"region_id": pa.array(range(n), pa.uint16()),
                            "craft_raw_demand": pa.array([1.5] * n, pa.float32())})


def _turn(world, sim, output=0.4):
    batch = W.prepare_phase2(world, _batch(len(world.regions)), SimpleNamespace(_sim=sim), None, None)
    sim.inputs = [[0.0] * 9 for _ in world.regions]
    W.finish_phase2(world, SimpleNamespace(craft_output={r.name: output for r in world.regions}),
                    SimpleNamespace(_sim=sim), None)
    world.turn += 1
    return batch


def _enable(world, *names, **modes):
    args = SimpleNamespace(**{MODE_KEYS[n]: modes.get(n) for n in names})
    for name in names:
        getattr(MODULES[name], f"set_{name}_enabled")(world, True, args=args, agent_mode="hybrid")


def _run(world, turns=9):
    sim = _Sim()
    batches = [_turn(world, sim).column("craft_raw_demand").to_pylist() for _ in range(turns)]
    return sim, batches


def _inert_rs1(monkeypatch):
    """Replace the landed RS1 hooks the workshop seams call with inert ones, so
    these RS0 seam tests keep testing only the seams (RS1 has its own tests)."""
    monkeypatch.setattr(A, "before_crews", lambda w, s, requests: None)
    monkeypatch.setattr(A, "crew_priority_ids", lambda w: [])
    monkeypatch.setattr(A, "crew_maintenance", lambda w, site, row: 0.0)
    monkeypatch.setattr(A, "operating_wear", lambda w, site: 0.0)


def test_stub_switches_leave_workshop_operation_identical():
    plain, stubbed = _ws_world(), _ws_world()
    _enable(stubbed, *STUBS)
    sim_a, batches_a = _run(plain)
    sim_b, batches_b = _run(stubbed)
    assert batches_a == batches_b and sim_a.calls == sim_b.calls
    # The planner was called exactly as before: no priority keyword at all.
    assert all(call[3] == {} for call in sim_b.calls)
    assert plain.livelihoods.workshops.model_dump_json() == stubbed.livelihoods.workshops.model_dump_json()
    assert [c.treasury for c in plain.civilizations] == [c.treasury for c in stubbed.civilizations]


def test_crew_priority_ids_are_passed_only_when_veterans_list_someone(monkeypatch):
    world = _ws_world()
    _enable(world, "veteran_reintegration")
    lists = {2: [203, 201, 203], 4: [405, 201]}
    monkeypatch.setattr(VR, "priority_ids", lambda w, region: list(lists.get(region, [])))
    sim = _Sim()
    _turn(world, sim)
    sites = world.livelihoods.workshops.sites
    assert [s.region for s in sites] == [2, 4]                  # rank 2 city first
    assert sim.calls[-1][3] == {"priority_ids": [203, 201, 405]}
    assert world.livelihoods.workshops.frame[0].crew == [203, 201]
    # An empty list for every site: the call is exactly today's.
    lists.clear()
    _turn(world, sim)
    assert sim.calls[-1][3] == {}
    # Inactive (disabled) veterans: never consulted.
    monkeypatch.setattr(VR, "priority_ids", lambda w, region: pytest.fail("consulted while inactive"))
    VR.set_veteran_reintegration_enabled(world, False, args=None)
    _turn(world, sim)
    assert sim.calls[-1][3] == {}


def test_before_crews_runs_first_only_while_apprenticeship_is_active(monkeypatch):
    world = _ws_world()
    seen = []
    sim = _Sim()
    _inert_rs1(monkeypatch)
    monkeypatch.setattr(A, "before_crews", lambda w, s, requests: seen.append((s, list(requests), len(s.calls))))
    _turn(world, sim)
    assert seen == []
    _enable(world, "apprenticeship")
    _turn(world, sim)
    assert len(seen) == 1 and seen[0][0] is sim and seen[0][2] == 1     # before this turn's planner call
    assert [r[0] for r in seen[0][1]] == [s.site for s in world.livelihoods.workshops.sites]
    world.livelihoods.workshops.mode = "cost_only"                      # apprenticeship inactive
    _turn(world, sim)
    assert len(seen) == 1


def _built_site_world():
    world = _ws_world()
    sim = _Sim()
    for _ in range(W.CONSTRUCTION_COST // W.INSTALLMENT):
        _turn(world, sim)
    return world, sim


def test_legacy_repair_gate_bills_the_lump_only_while_allowed(monkeypatch):
    world, sim = _built_site_world()
    site = world.livelihoods.workshops.sites[0]
    site.condition = 0.3
    assert "repair" in W._bill(site) and "repair" in W._bill(site, world)
    _enable(world, "repair_projects")
    assert "repair" in W._bill(site, world)                 # the RS0 stub allows it
    monkeypatch.setattr(RP, "legacy_workshop_repair_allowed", lambda w: False)
    assert W._bill(site, world) == {"upkeep": W.UPKEEP}
    assert "repair" in W._bill(site)                        # no world: today's bill
    batch = _turn(world, sim)
    receipt = world.livelihoods.workshops.frame[0]
    assert "repair" not in receipt.paid and site.condition == 0.3
    # Without the lump, a worn site stays shut until something repairs it.
    assert receipt.funded and receipt.allocated == 0.0 and receipt.craft_ceiling == 0.0
    assert batch.column("craft_raw_demand").to_pylist()[site.region] == 0.0
    assert world.livelihoods.workshops.frame[1].allocated > 0          # the healthy site operates
    # Inactive repair projects: the gate is never consulted.
    monkeypatch.setattr(RP, "legacy_workshop_repair_allowed", lambda w: pytest.fail("consulted while inactive"))
    RP.set_repair_projects_enabled(world, False, args=None)
    _turn(world, sim)
    assert world.livelihoods.workshops.frame[0].paid.get("repair") == W.REPAIR_COST and site.condition == 1.0


def test_operating_wear_touches_condition_only_when_positive(monkeypatch):
    world, sim = _built_site_world()
    sites = world.livelihoods.workshops.sites
    sites[0].condition = 0.8125
    _inert_rs1(monkeypatch)
    _enable(world, "apprenticeship")
    _turn(world, sim)
    assert sites[0].condition == 0.8125                    # stub wear 0.0: untouched
    monkeypatch.setattr(A, "operating_wear", lambda w, site: 0.25 if site.site == sites[0].site else 0.0)
    _turn(world, sim)
    assert world.livelihoods.workshops.frame[0].allocated > 0
    assert sites[0].condition == pytest.approx(0.5625) and sites[1].condition == 1.0
    monkeypatch.setattr(A, "operating_wear", lambda w, site: 0.9)
    _turn(world, sim)
    assert sites[0].condition == 0.0                       # clamped at zero
    monkeypatch.setattr(A, "operating_wear", lambda w, site: float("nan"))
    with pytest.raises(ValueError, match="operating wear"):
        _turn(world, sim)


def test_unfunded_or_non_operating_sites_never_read_operating_wear(monkeypatch):
    world, sim = _built_site_world()
    _inert_rs1(monkeypatch)
    _enable(world, "apprenticeship")
    monkeypatch.setattr(A, "operating_wear", lambda w, site: pytest.fail("read for a non-operating site"))
    world.civilizations[0].treasury = 0
    _turn(world, sim)                                      # unfunded: L1 wear only
    assert world.livelihoods.workshops.sites[0].condition == pytest.approx(1.0 - W.CONDITION_WEAR)


# --- Exact resume ---------------------------------------------------------------


def test_exact_resume_refuses_a_recovery_skills_mode_the_checkpoint_never_recorded(world):
    """Lead integration 2026-11-05 (RS1 lane report): the five RS mode options
    were missing from ``livelihoods_resume_conflicts``, so ``--resume CKPT
    --remittance-mode record_only`` would have continued silently in the saved
    mode. An exact resume refuses a mode other than the retained one."""
    from types import SimpleNamespace
    from chronicler.batch_manifest import simulation_config
    from chronicler.main import _adopt_checkpoint_args
    parser = _build_parser()
    world.turn = 2

    def saved(flags):
        return SimpleNamespace(state=SimpleNamespace(
            world=world, seed=42, num_turns=8,
            run_config={"simulation_args": simulation_config(parser.parse_args(flags))}))

    off = saved([])
    for key, (default, other) in ((MODE_KEYS[n], MODES[MODE_KEYS[n]]) for n in RS):
        flag = "--" + key.replace("_", "-")
        conflicts = _adopt_checkpoint_args(parser, parser.parse_args([flag, other]), off)
        assert len(conflicts) == 1 and flag in conflicts[0] and "conflicts with the checkpoint" in conflicts[0]
    configure_livelihoods(world, parse(*ALL_ON), agent_mode="hybrid")
    on = saved([])
    before = world.model_dump_json()
    for name in RS:
        key = MODE_KEYS[name]
        default, other = MODES[key]
        flag = "--" + key.replace("_", "-")
        assert _adopt_checkpoint_args(parser, parser.parse_args([flag, default]), on) == [], flag
        conflicts = _adopt_checkpoint_args(parser, parser.parse_args([flag, other]), on)
        assert len(conflicts) == 1 and flag in conflicts[0], flag
    assert world.model_dump_json() == before
