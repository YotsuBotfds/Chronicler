"""Hook-order harness for ``run_turn_result`` (turn-loop consolidation, CON-4).

Turns every feature gate on or off by name, replaces each feature hook
target with a stub that records ``[slot, key]`` and returns an empty result,
quiets the core phases (the ``_quiet_phases`` pattern of
``tests/test_turn_artifact_lifecycle.py``) while recording their position, and
records the accumulator flushes. The recorded sequence over two turns is the
golden ``tests/fixtures/turn_loop/hook_order.json``, captured before the hook
table existed; the hook table must reproduce it unchanged.

Gates are patched where the current code reads them (the ``_X_on`` names
bound in ``chronicler.simulation``, ``ritual_gatherings_state``, and the plain
world attributes) and, once ``chronicler.turn_hooks`` exists, in its
``GATES`` table too. Targets are patched on their defining modules, which both
the inline imports and an import-at-call registry read.

Regenerate (only when the hook order is meant to change)::

    .venv/bin/python tests/support/turn_order_trace.py --write
"""
from __future__ import annotations

import importlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests/fixtures/turn_loop/hook_order.json"
SCHEMA_VERSION = 1
TURNS = 2

# Feature name -> the gate name bound in chronicler.simulation (None: the gate
# is read elsewhere; see WORLD_GATES and ritual_gatherings).
SIM_GATES = {
    "epidemiology": "_epidemiology_on",
    "contact_ledger": "_contact_ledger_on",
    "maritime": "_maritime_on",
    "nomads": "_nomads_on",
    "cities": "_cities_on",
    "agent_movements": "_agent_movements_on",
    "guilds": "_guilds_on",
    "scholarship": "_scholarship_on",
    "grain_reserves": "_grain_reserves_on",
    "diplomacy": "_diplomacy_on",
    "techniques": "_techniques_on",
    "gp_agendas": "_gp_agendas_on",
}
# Feature name -> world attribute and its "on" value (a sentinel object for the
# ``is not None`` gates, ``True`` for the boolean attributes).
WORLD_GATES = {
    "campaigns": ("campaigns_enabled", True),
    "mutual_aid": ("mutual_aid_enabled", True),
    "finance": ("finance", "sentinel"),
    "livelihoods": ("livelihoods", "sentinel"),
    "health_care": ("health_care", "sentinel"),
}
OTHER_GATES = {
    "ritual_gatherings": ("chronicler.ritual_gatherings_state", "ritual_gatherings_on"),
}
FEATURES = tuple(SIM_GATES) + tuple(WORLD_GATES) + tuple(OTHER_GATES)

# (slot, key, "module:attr", returns). ``returns`` is "empty" ([]), "none",
# "dict" ({}), or "arg<N>" (the N-th positional argument, for wrappers that
# hand their input on). Slots are harness labels for the turn position (close
# to the spec section 3 slots, but not required to equal the hook table's slot
# names); the ``p2.economy``, ``p4`` and ``p9.wrap`` rows stay inline in the
# hook table and are recorded so the sequence anchors every hook.
TARGETS = (
    ("p1.environment", "epidemiology", "chronicler.epidemiology:tick_epidemics", "empty"),
    ("p1.off_observers", "contact_ledger", "chronicler.contact_ledger:observe_phase2", "none"),
    ("p1.off_observers", "maritime", "chronicler.maritime:observe_phase2", "none"),
    ("p2.economy", "mutual_aid.commitments", "chronicler.mutual_aid:read_stockpile_commitments", "dict"),
    ("p2.economy", "mutual_aid.dispatch", "chronicler.mutual_aid:dispatch_mutual_aid", "empty"),
    ("p2.economy", "cities.columns", "chronicler.cities:with_economy_columns", "arg1"),
    ("p2.economy", "maritime.filter", "chronicler.maritime:filter_boundary_batch", "arg1"),
    ("p2.economy", "health_care.prepare", "chronicler.health_care:prepare_health_care", "none"),
    ("p2.economy", "livelihoods.prepare", "chronicler.livelihoods:prepare_phase2", "arg1"),
    ("p2.economy", "livelihoods.finish", "chronicler.livelihoods:finish_phase2", "empty"),
    ("p2.economy", "grain_reserves.open", "chronicler.grain_reserves:open_granaries", "empty"),
    ("p2.observers", "mutual_aid.observe", "chronicler.mutual_aid:observe_mutual_aid", "none"),
    ("p2.dues", "cities.dues", "chronicler.cities:pay_dues", "none"),
    ("p3b.finance", "finance", "chronicler.finance:tick_finance", "empty"),
    ("p4", "techniques", "chronicler.techniques:tick_techniques", "empty"),
    ("p5.after_action", "maritime", "chronicler.maritime:tick_maritime", "empty"),
    ("p5.after_action", "nomads", "chronicler.nomads:tick_nomads", "empty"),
    ("p5.after_action", "campaigns", "chronicler.war.runtime:tick_campaigns", "empty"),
    ("p9.before_ecology", "livelihoods", "chronicler.livelihoods:before_ecology", "none"),
    ("p9.after_ecology", "livelihoods", "chronicler.livelihoods:after_ecology", "empty"),
    ("p9.wrap", "livelihoods", "chronicler.livelihoods:wrap_agent_tick", "arg2"),
    ("p9.after_tick", "health_care", "chronicler.health_care:finish_health_care", "empty"),
    ("p9.after_tick", "campaigns.rosters", "chronicler.war.armies:reconcile_rosters", "none"),
    ("p10.after_politics", "diplomacy", "chronicler.diplomacy:tick_diplomacy", "empty"),
    ("p10.after_politics", "gp_agendas", "chronicler.gp_agendas:tick_gp_agendas", "empty"),
    ("p10.after_politics", "cities", "chronicler.cities:tick_cities", "empty"),
    ("p10.after_politics", "agent_movements", "chronicler.agent_movements:tick_agent_movements", "empty"),
    ("p10.after_politics", "guilds", "chronicler.guilds:tick_guilds", "empty"),
    ("p10.after_politics", "scholarship", "chronicler.scholarship:tick_scholarship", "empty"),
    ("p10.pre_flush", "livelihoods.before_reserves", "chronicler.livelihoods:phase10_before_reserves", "empty"),
    ("p10.pre_flush", "grain_reserves", "chronicler.grain_reserves:tick_grain_reserves", "empty"),
    ("p10.pre_flush", "livelihoods.p10", "chronicler.livelihoods:phase10", "empty"),
    ("p10.pre_flush", "ritual_gatherings", "chronicler.ritual_gatherings:tick_ritual_gatherings", "empty"),
    ("post.close", "campaigns.sync", "chronicler.war.runtime:end_of_turn_sync", "none"),
    ("post.close", "maritime.sea_trade", "chronicler.maritime:observe_agent_sea_trade", "none"),
    ("post.close", "contact_ledger", "chronicler.contact_ledger:update_contact_ledger", "none"),
    ("post.close", "finance.money", "chronicler.finance:update_money", "none"),
)
# Core phases quieted on the simulation namespace (recorded as ["core", name]).
CORE_SIM = ("phase_environment", "apply_automatic_effects", "phase_production", "phase_technology",
            "phase_action", "phase_cultural_milestones", "phase_random_events",
            "phase_leader_dynamics", "run_settlement_tick", "phase_consequences")
CORE_MODULES = (
    ("chronicler.emergence", "check_black_swans", "empty"),
    ("chronicler.emergence", "check_environmental_events", "empty"),
    ("chronicler.emergence", "check_tech_regression", "empty"),
    ("chronicler.emergence", "compute_all_stress", "none"),
    ("chronicler.ecology", "tick_ecology", "empty"),
    ("chronicler.artifacts", "tick_artifacts", "empty"),
    ("chronicler.economy", "settle_pending_stockpile_bootstraps", "none"),
)

ALL = FEATURES
# Combination name -> features switched on (spec section 7 / plan CON-4a).
COMBINATIONS = {
    "none": (),
    "all": ALL,
    "phase10_institutions": ("cities", "guilds", "scholarship", "diplomacy", "gp_agendas",
                             "agent_movements"),
    "food_and_ritual": ("livelihoods", "grain_reserves", "ritual_gatherings"),
    "state_and_war": ("finance", "maritime", "nomads", "campaigns", "contact_ledger",
                      "epidemiology"),
}
# Recorded runs: (combination, agent mode). "off" runs without a bridge; the
# agent modes use the fake bridge below.
RUNS = tuple((name, mode) for name in COMBINATIONS for mode in ("off", "hybrid")) + (
    ("all", "shadow"),
)
PHASE10_ORDER = (
    "diplomacy", "gp_agendas", "cities", "agent_movements", "guilds", "scholarship",
    "livelihoods.before_reserves", "grain_reserves", "livelihoods.p10", "ritual_gatherings",
)


def _returns(kind: str, args: tuple):
    if kind == "empty":
        return []
    if kind == "none":
        return None
    if kind == "dict":
        return {}
    if kind.startswith("arg"):
        return args[int(kind[3:])]
    raise ValueError(kind)


# Targets called from two places: (positional-argument count from which the
# call is the second site, its slot). The contact ledger reads the goods
# routes without a bridge in Phase 1 and the merchant deliveries with one
# inside the economy transaction.
SECOND_SITE = {"chronicler.contact_ledger:observe_phase2": (3, "p2.economy")}


def _stub(log: list, slot: str, key: str, kind: str, target: str | None = None):
    second = SECOND_SITE.get(target)

    def stub(*args, **kwargs):
        label = second[1] if second is not None and len(args) >= second[0] else slot
        log.append([label, key])
        return _returns(kind, args)
    return stub


def make_world(mode: str):
    """The conftest ``make_world()`` world (two one-region civilizations)."""
    from chronicler.models import Civilization, Leader, Region, Relationship, TechEra, WorldState
    names = ["Civ0", "Civ1"]
    regions = [Region(name=f"{n}_region", terrain="plains", carrying_capacity=60,
                      resources="fertile", controller=n) for n in names]
    civs = [Civilization(name=n, population=50, military=30, economy=40, culture=30, stability=50,
                         tech_era=TechEra.IRON, treasury=50,
                         leader=Leader(name=f"Leader of {n}", trait="cautious", reign_start=0),
                         regions=[f"{n}_region"], asabiya=0.5) for n in names]
    rels = {a: {b: Relationship() for b in names if b != a} for a in names}
    world = WorldState(name="TestWorld", seed=42, turn=0, regions=regions, civilizations=civs,
                       relationships=rels)
    if mode != "off":
        world.agent_mode = mode
    return world


def make_bridge(world, log: list):
    """A fake agent bridge (``test_turn_artifact_lifecycle`` ``Bridge``) that
    owns relationship formation, as every real ``AgentBridge`` does."""
    import pyarrow as pa
    from chronicler.demand_signals import DemandSignalManager

    def batch():
        return pa.record_batch({"region": [0], "x": [0.1], "y": [0.2]})

    class Native:
        def tick_economy(self, *args):
            return ()

        def get_snapshot(self):
            return batch()

    class Bridge:
        _sim = Native()
        _demand_manager = DemandSignalManager()
        named_agents: dict = {}
        dynasty_registry = None
        rust_owns_formation = True
        economy_simulator = None

        @property
        def ecology_simulator(self):
            return self._sim

        def get_snapshot(self):
            return batch()

        def set_economy_result(self, result):
            pass

        def sync_regions(self, w):
            pass

        def tick_agents(self, w, **kwargs):
            log.append(["core", "tick_agents"])
            return []

        def read_social_edges(self):
            return []

    return Bridge()


def install(monkeypatch, world, features, log: list) -> None:
    """Patch gates, targets, core phases and flushes for one recorded run."""
    from chronicler import simulation as sim
    from chronicler.accumulator import StatAccumulator
    unknown = set(features) - set(FEATURES)
    if unknown:
        raise ValueError(f"unknown features {sorted(unknown)}")
    on = set(features)
    try:
        turn_hooks = importlib.import_module("chronicler.turn_hooks")
    except ModuleNotFoundError:
        turn_hooks = None
    for name in FEATURES:
        value = name in on
        gate = (lambda *a, _value=value, **kw: _value)
        if name in SIM_GATES:
            monkeypatch.setattr(sim, SIM_GATES[name], gate, raising=False)
        elif name in OTHER_GATES:
            module, attr = OTHER_GATES[name]
            monkeypatch.setattr(importlib.import_module(module), attr, gate)
        else:
            attr, on_value = WORLD_GATES[name]
            if value:
                monkeypatch.setattr(world, attr, SimpleNamespace() if on_value == "sentinel" else on_value)
            else:
                monkeypatch.setattr(world, attr, False if on_value is True else None)
        gates = getattr(turn_hooks, "GATES", None)
        if gates is not None and name in gates:
            monkeypatch.setitem(gates, name, gate)
    for slot, key, target, kind in TARGETS:
        module, attr = target.split(":")
        monkeypatch.setattr(importlib.import_module(module), attr, _stub(log, slot, key, kind, target))
    for name in CORE_SIM:
        kind = "none" if name == "phase_production" else "empty"
        monkeypatch.setattr(sim, name, _stub(log, "core", name, kind))
    for module, attr, kind in CORE_MODULES:
        monkeypatch.setattr(importlib.import_module(module), attr, _stub(log, "core", attr, kind))
    from chronicler import economy
    results = SimpleNamespace(treasury_tax={}, imports_by_region={})
    monkeypatch.setattr(economy, "build_economy_region_input_batch", lambda *a: "region_input")
    monkeypatch.setattr(economy, "build_economy_trade_route_batch", lambda *a, **kw: "route_input")
    monkeypatch.setattr(economy, "reconstruct_economy_result", lambda *a, **kw: results)
    apply, apply_keep = StatAccumulator.apply, StatAccumulator.apply_keep

    def flush_all(self, w):
        log.append(["flush", "apply"])
        return apply(self, w)

    def flush_keep(self, w):
        log.append(["flush", "apply_keep"])
        return apply_keep(self, w)

    monkeypatch.setattr(StatAccumulator, "apply", flush_all)
    monkeypatch.setattr(StatAccumulator, "apply_keep", flush_keep)


def trace(monkeypatch, combination: str, mode: str) -> list:
    """The recorded call sequence of ``TURNS`` turns (each ends with the
    narrator, recorded as ``["core", "narrator"]``)."""
    from chronicler import simulation as sim
    log: list = []
    world = make_world(mode)
    install(monkeypatch, world, COMBINATIONS[combination], log)
    bridge = None if mode == "off" else make_bridge(world, log)

    def narrator(w, events):
        log.append(["core", "narrator"])
        return ""

    for _ in range(TURNS):
        sim.run_turn_result(world, lambda *a: None, narrator, agent_bridge=bridge)
    return log


def record() -> dict:
    import pytest
    runs = {}
    for combination, mode in RUNS:
        with pytest.MonkeyPatch.context() as monkeypatch:
            runs[f"{combination}/{mode}"] = trace(monkeypatch, combination, mode)
    return {"schema_version": SCHEMA_VERSION, "turns": TURNS,
            "record": "tests/support/turn_order_trace.py",
            "combinations": {name: list(features) for name, features in COMBINATIONS.items()},
            "runs": runs}


def dumps(document: dict) -> str:
    head = {key: value for key, value in document.items() if key != "runs"}
    lines = ["{"]
    lines += [f"  {json.dumps(key)}: {json.dumps(value)}," for key, value in head.items()]
    lines.append('  "runs": {')
    names = list(document["runs"])
    for index, name in enumerate(names):
        rows = document["runs"][name]
        lines.append(f"    {json.dumps(name)}: [")
        lines.extend(f"      {json.dumps(row)}" + ("," if i < len(rows) - 1 else "")
                     for i, row in enumerate(rows))
        lines.append("    ]" + ("," if index < len(names) - 1 else ""))
    lines += ["  }", "}"]
    return "\n".join(lines) + "\n"


def load() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT / "src"))
    if sys.argv[1:] != ["--write"]:
        raise SystemExit("usage: turn_order_trace.py --write")
    FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    FIXTURE.write_text(dumps(record()), encoding="utf-8")
    print(f"wrote {FIXTURE.relative_to(ROOT)}")
