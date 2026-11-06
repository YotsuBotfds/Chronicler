"""Quarantine closure of migration (connected-world C1b), offline.

``--quarantine-channels trade,migration`` under ``--quarantine-mode closure``:
option validation and refusals, the default ``trade`` as the omitted option,
serialization (absent while off), the native install and receipt seam with a
fake simulator (attribution, flight drivers, malformed or missing receipts),
the snapshot's distinct states, the totals, forwarding, the manifest, the
feature catalog and resume conflicts. The real extension is exercised in
``tests/test_quarantine_migration_native.py``.
"""
from __future__ import annotations

import argparse
import json
import pickle
from pathlib import Path

import pytest

import chronicler.contact_ledger as cl
import chronicler.epidemiology as ep
import chronicler.quarantine_rules as qr
from chronicler.models import WorldState
from chronicler.world_gen import generate_world

AGENT_MODES = ("off", "demographics-only", "shadow", "hybrid")
MIGRATING = ("demographics-only", "shadow", "hybrid")


def _world(migration: bool = True) -> WorldState:
    world = generate_world(seed=42, num_regions=8, num_civs=4)
    cl.set_contact_ledger_enabled(world, True)
    ep.set_epidemiology_enabled(world, True)
    world.epidemics.quarantine_rules = qr.QuarantineRulesState(mode="closure", migration=migration)
    if migration:
        world.epidemics.quarantine_rules.totals.migrants_blocked = 0
        world.epidemics.quarantine_rules.totals.migrants_blocked_flight = 0
    return world


def _two_polities(world: WorldState) -> None:
    """Regions 0-3 ruled by civ 0, 4-6 by civ 1, region 7 by nobody."""
    a, b = world.civilizations[0], world.civilizations[1]
    a.regions = [r.name for r in world.regions[:4]]
    b.regions = [r.name for r in world.regions[4:7]]
    for civ in world.civilizations[2:]:
        civ.regions = []
    for i, region in enumerate(world.regions):
        region.controller = a.name if i < 4 else (b.name if i < 7 else None)


class FakeSim:
    """The three native methods, recording calls (no extension)."""

    def __init__(self, rows=()):
        self.calls: list = []
        self.rows = list(rows)
        self.receipt_missing = False

    def cancel_migration_closure(self):
        self.calls.append(("cancel",))
        return False

    def set_migration_closure(self, turn, region_civ, pairs):
        self.calls.append(("set", turn, list(region_civ), list(pairs)))

    def take_migration_closure_receipt(self, turn):
        self.calls.append(("take", turn))
        return None if self.receipt_missing else list(self.rows)


def _parser():
    from chronicler.main import _build_parser
    return _build_parser()


class _Accepted(Exception):
    """Configuration got past every check (to the native runtimes)."""


@pytest.fixture
def sentinel_runtimes(monkeypatch):
    from chronicler import agent_bridge, main

    def accepted(*args, **kwargs):
        raise _Accepted

    monkeypatch.setattr(agent_bridge, "AgentBridge", accepted)
    monkeypatch.setattr(main, "_create_ecology_runtime", accepted)


def _configure(tmp_path: Path, *flags: str, world: WorldState | None = None) -> tuple[WorldState, str | None]:
    """``main._configure_run`` on a new (or given) world: (world, refusal or None)."""
    from chronicler import main
    args = _parser().parse_args(["--seed", "42", "--turns", "4", "--regions", "8", "--civs", "4",
                                 "--simulate-only", "--output", str(tmp_path / "chronicle.md"), *flags])
    world = world if world is not None else generate_world(seed=42, num_regions=8, num_civs=4)
    try:
        main._configure_run(args, world, True, tmp_path / "chronicle.md")
    except _Accepted:
        return world, None
    except ValueError as exc:
        return world, str(exc)
    return world, "configuration finished without reaching the runtimes"


def _cli_args(folder: Path, turns: int, **extra) -> argparse.Namespace:
    args = argparse.Namespace(
        seed=7, turns=turns, civs=4, regions=8, output=str(folder / "chronicle.md"),
        state=str(folder / "state.json"), resume=None, reflection_interval=10, llm_actions=False,
        scenario=None, pause_every=None, simulate_only=True, agents="off", tuning_overrides={},
    )
    for key, value in extra.items():
        setattr(args, key, value)
    return args


@pytest.fixture
def pure_python_runtimes(monkeypatch):
    monkeypatch.setattr("chronicler.main._create_ecology_runtime", lambda world: None)
    monkeypatch.setattr("chronicler.main._create_politics_runtime", lambda world: None)


# --- options and refusals -------------------------------------------------------------------

@pytest.mark.parametrize("mode", [None, "legacy", "none", "cost_only"])
def test_migration_channel_requires_the_closure_mode(tmp_path, sentinel_runtimes, mode):
    flags = ["--agents", "hybrid", "--quarantine-channels", "trade,migration"]
    if mode is not None:
        flags += ["--quarantine-mode", mode]
    _, refusal = _configure(tmp_path, *flags)
    assert refusal == "--quarantine-channels trade,migration requires --quarantine-mode closure"


@pytest.mark.parametrize("agents", AGENT_MODES)
def test_migration_channel_requires_an_agent_mode_with_native_migration(tmp_path, sentinel_runtimes, agents):
    world, refusal = _configure(tmp_path, "--agents", agents, "--quarantine-mode", "closure",
                                "--quarantine-channels", "trade,migration")
    if agents == "off":
        assert refusal.startswith("--quarantine-channels trade,migration requires an agent mode")
        assert "--agents off" in refusal
    else:
        assert refusal is None
        rules = world.epidemics.quarantine_rules
        assert rules.mode == "closure" and rules.migration is True
        assert qr.channels_of(rules) == ["trade", "migration"]
        assert (rules.totals.migrants_blocked, rules.totals.migrants_blocked_flight) == (0, 0)


@pytest.mark.parametrize("mode", [None, "legacy", "none", "cost_only", "closure"])
@pytest.mark.parametrize("agents", AGENT_MODES)
def test_explicit_trade_is_the_omitted_option(tmp_path, sentinel_runtimes, mode, agents):
    flags = ["--agents", agents] + (["--quarantine-mode", mode] if mode else [])
    omitted, refusal_omitted = _configure(tmp_path / "o", *flags)
    given, refusal_given = _configure(tmp_path / "g", *flags, "--quarantine-channels", "trade")
    assert refusal_omitted is None and refusal_given is None
    assert given.model_dump_json() == omitted.model_dump_json()
    assert not qr.migration_closure_on(given)


def test_explicit_trade_needs_neither_epidemiology_nor_the_ledger(tmp_path, sentinel_runtimes):
    for setting in ("--no-epidemiology", "--no-contact-ledger"):
        assert _configure(tmp_path, "--agents", "hybrid", setting, "--quarantine-channels", "trade")[1] is None


def test_an_aggregate_run_with_explicit_trade_writes_the_omitted_options_world(tmp_path, pure_python_runtimes):
    from chronicler.main import execute_run
    execute_run(_cli_args(tmp_path / "omitted", 8, quarantine_mode="closure"))
    execute_run(_cli_args(tmp_path / "trade", 8, quarantine_mode="closure", quarantine_channels="trade"))
    assert (tmp_path / "omitted/state.json").read_bytes() == (tmp_path / "trade/state.json").read_bytes()
    saved = json.loads((tmp_path / "trade/state.json").read_text())["epidemics"]["quarantine_rules"]
    assert "migration" not in saved and "migrants_blocked" not in saved["totals"]


# --- persisted state -------------------------------------------------------------------------

def test_the_flag_and_totals_are_absent_while_off_and_old_states_load():
    off = _world(migration=False)
    dumped = json.loads(off.epidemics.model_dump_json())["quarantine_rules"]
    assert "migration" not in dumped and set(dumped["totals"]) == set(qr.QuarantineTotals().model_dump())
    assert "migrants_blocked" not in dumped["totals"]
    on = json.loads(_world().epidemics.model_dump_json())["quarantine_rules"]
    assert on["migration"] is True
    assert on["totals"]["migrants_blocked"] == 0 and on["totals"]["migrants_blocked_flight"] == 0
    # A C1 rules state (no field) loads as trade only.
    restored = qr.QuarantineRulesState.model_validate(dumped)
    assert restored.migration is False and restored.totals.migrants_blocked is None
    pickled = pickle.loads(pickle.dumps(off))
    assert qr.migration_closure_on(pickled) is False


def test_closures_carry_the_migration_channel_and_the_event_says_so():
    world = _world()
    _two_polities(world)
    world.epidemics.initialized_turn = world.turn
    world.epidemics.homelands = []
    world.contact_ledger.edges = []
    world.contact_ledger.invalidate()
    cl._pending(world).append((4, 3, cl.PEOPLE, 100.0))
    cl.update_contact_ledger(world)
    row = ep._row_for(world.epidemics, 4, ep.PLAGUE, world.regions[4].population)
    world.regions[4].population = world.regions[4].carrying_capacity = 300
    row.n = 300
    ep._seed(row, 30.0, cause="", virgin=True)
    world.civilizations[0].stability, world.civilizations[0].treasury = 80, 50
    events = ep.tick_epidemics(world)
    rules = world.epidemics.quarantine_rules
    assert [(c.civ, c.target, c.channels) for c in rules.closures] == [(0, 1, ["trade", "migration"])]
    text = next(e.description for e in events if e.event_type == "quarantine")
    assert "closes its borders to trade and migration with" in text


# --- the native seam (fake simulator) ---------------------------------------------------------

def _receipt_world(closures):
    world = _world()
    _two_polities(world)
    rules = world.epidemics.quarantine_rules
    rules.closures = [qr.QuarantineClosure(id=i, civ=c, target=t, opened_turn=0, last_renewed_turn=0)
                      for i, c, t in closures]
    rules.receipt = qr.QuarantineReceipt(turn=world.turn)
    return world, rules


def test_install_sends_controllers_and_canonical_pairs_after_dropping_a_stale_closure():
    world, _ = _receipt_world([(3, 1, 0), (4, 0, 1)])
    sim = FakeSim()
    token = qr.install_migration_closure(world, sim)
    assert sim.calls == [("cancel",), ("set", world.turn, [0, 0, 0, 0, 1, 1, 1, 255], [(0, 1)])]
    assert token == (world.turn, [0, 0, 0, 0, 1, 1, 1, 255], {(1, 0): 3, (0, 1): 4})


def test_install_runs_every_tick_of_the_channel_even_without_a_closure():
    world, _ = _receipt_world([])
    sim = FakeSim()
    assert qr.install_migration_closure(world, sim)[2] == {}
    assert sim.calls[-1][3] == []


@pytest.mark.parametrize("migration", [False, True])
def test_nothing_reaches_the_simulator_without_the_channel(migration):
    world, rules = _receipt_world([(1, 0, 1)])
    rules.migration = migration
    sim = FakeSim()
    token = qr.install_migration_closure(world, sim)
    qr.take_migration_receipt(world, sim, token)
    assert (token is None, sim.calls == []) == (not migration, not migration)
    from chronicler.agent_bridge import _quarantine_migration_closure, _quarantine_migration_receipt
    legacy = generate_world(seed=42, num_regions=8, num_civs=4)
    assert _quarantine_migration_closure(legacy, object()) is None
    _quarantine_migration_receipt(legacy, object(), None)   # touches nothing


def test_an_old_extension_is_refused_clearly():
    world, _ = _receipt_world([])
    with pytest.raises(RuntimeError, match="requires a fresh native build with the migration closure"):
        qr.install_migration_closure(world, object())


def test_the_receipt_is_attributed_to_the_border_the_mover_would_enter():
    # Civ 1 closed against civ 0 (closure 3) and civ 0 against civ 1 (closure 4):
    # 0 -> 1 movers meet closure 3 (civ 1's border), 1 -> 0 movers meet closure 4.
    world, rules = _receipt_world([(3, 1, 0), (4, 0, 1)])
    rows = [(3, 4, "famine_memory", 2), (3, 4, "wage", 1), (5, 2, "opp_food", 4), (6, 1, "unattributed", 1)]
    sim = FakeSim(rows)
    qr.take_migration_receipt(world, sim, qr.install_migration_closure(world, sim))
    assert rules.receipt.migrants_blocked == [
        (3, 3, 4, "famine_memory", 2), (3, 3, 4, "wage", 1), (4, 5, 2, "opp_food", 4), (4, 6, 1, "unattributed", 1)]
    assert qr.blocked_counts(rules.receipt.migrants_blocked) == (8, 2)


def test_a_one_sided_closure_takes_both_directions():
    world, rules = _receipt_world([(9, 0, 1)])
    sim = FakeSim([(3, 4, "wage", 1), (4, 3, "battle_memory", 2)])
    qr.take_migration_receipt(world, sim, qr.install_migration_closure(world, sim))
    assert rules.receipt.migrants_blocked == [(9, 3, 4, "wage", 1), (9, 4, 3, "battle_memory", 2)]


@pytest.mark.parametrize("row, message", [
    ((0, 1, "wage", 1), "refused an open crossing"),          # inside civ 0
    ((3, 7, "wage", 1), "refused an open crossing"),          # into unclaimed land
    ((3, 99, "wage", 1), "malformed native migration closure row"),
    ((3, 4, "wage", 0), "malformed native migration closure row"),
])
def test_an_impossible_native_row_is_refused(row, message):
    world, _ = _receipt_world([(1, 0, 1)])
    sim = FakeSim([row])
    with pytest.raises(RuntimeError, match=message):
        qr.take_migration_receipt(world, sim, qr.install_migration_closure(world, sim))


def test_a_missing_receipt_is_refused_and_the_install_released():
    world, _ = _receipt_world([(1, 0, 1)])
    sim = FakeSim()
    sim.receipt_missing = True
    token = qr.install_migration_closure(world, sim)
    with pytest.raises(RuntimeError, match="receipt missing"):
        qr.take_migration_receipt(world, sim, token)
    assert sim.calls[-1] == ("cancel",)


# --- snapshot and totals ----------------------------------------------------------------------

C1_RECEIPT_KEYS = {"turn", "decided", "continued", "closed_last_tick", "opened", "renewed", "lapsed",
                   "enforcement", "phase2_observed", "routes_removed", "forgone_income",
                   "merchant_edges_removed", "leaked_deliveries", "leaked_quantity"}


def test_trade_only_snapshots_keep_c1s_shape():
    world, rules = _receipt_world([(1, 0, 1)])
    rules.migration = False
    rules.totals = qr.QuarantineTotals()
    summary = qr.snapshot_summary(world)
    assert summary["channels"] == ["trade"] and "migrants" in summary["exempt"]
    assert set(summary["receipt"]) == C1_RECEIPT_KEYS
    assert "migrants_blocked" not in summary["totals"]


def test_snapshot_keeps_not_observed_recorded_zero_and_refusals_distinct():
    world, rules = _receipt_world([(1, 0, 1)])
    summary = qr.snapshot_summary(world)
    assert summary["channels"] == ["trade", "migration"] and "migrants" not in summary["exempt"]
    receipt = summary["receipt"]
    assert set(receipt) == C1_RECEIPT_KEYS | {"migrants_blocked", "migrants_blocked_flight", "migration_refusals"}
    assert receipt["migrants_blocked"] is None and receipt["migration_refusals"] is None   # not observed
    sim = FakeSim([])
    qr.take_migration_receipt(world, sim, qr.install_migration_closure(world, sim))
    receipt = qr.snapshot_summary(world)["receipt"]
    assert (receipt["migrants_blocked"], receipt["migrants_blocked_flight"], receipt["migration_refusals"]) == (0, 0, [])
    rules.receipt = qr.QuarantineReceipt(turn=world.turn)
    sim = FakeSim([(4, 3, "persecution", 3), (5, 2, "frontier", 1)])
    qr.take_migration_receipt(world, sim, qr.install_migration_closure(world, sim))
    summary = qr.snapshot_summary(world)
    assert summary["receipt"]["migrants_blocked"] == 4 and summary["receipt"]["migrants_blocked_flight"] == 3
    assert summary["receipt"]["migration_refusals"][0] == {
        "closure": 1, "from": world.regions[4].name, "to": world.regions[3].name, "driver": "persecution",
        "persons": 3}
    assert (summary["totals"]["migrants_blocked"], summary["totals"]["migrants_blocked_flight"]) == (4, 3)


def test_totals_fold_each_receipt_once():
    totals = qr.QuarantineTotals(migrants_blocked=0, migrants_blocked_flight=0)
    for rows in ([(1, 0, 4, "famine_memory", 2)], None, [], [(1, 4, 0, "wage", 5)]):
        receipt = qr.QuarantineReceipt(turn=1, migrants_blocked=rows)
        qr._fold(totals, receipt)
    assert (totals.migrants_blocked, totals.migrants_blocked_flight, totals.receipts) == (7, 2, 4)
    plain = qr.QuarantineTotals()
    qr._fold(plain, qr.QuarantineReceipt(turn=1))
    assert plain.migrants_blocked is None


def test_flight_drivers_are_native_term_names():
    assert set(qr.FLIGHT_DRIVERS) <= {
        "low_satisfaction", "opp_satisfaction", "opp_capacity", "opp_food", "opp_river", "opp_news",
        "persecution", "famine_memory", "battle_memory", "conquest_memory", "persecution_memory",
        "safety_need", "material_need", "spiritual_need", "frontier", "wage", "chain", "urban",
        "social_need", "learning"}


def test_metrics_carry_the_migration_totals():
    world, _ = _receipt_world([(1, 0, 1)])
    sim = FakeSim([(4, 3, "famine_memory", 2)])
    qr.take_migration_receipt(world, sim, qr.install_migration_closure(world, sim))
    metrics = qr.extract_metrics([{"quarantine_rules": qr.snapshot_summary(world)}])
    assert (metrics["migrants_blocked"], metrics["migrants_blocked_flight"]) == (2, 2)


# --- forwarding, manifest, catalog -------------------------------------------------------------

def test_forwarding_and_manifest_record_explicit_channels_only():
    from chronicler.batch_manifest import simulation_config
    from chronicler.expansion_features import expansion_arguments
    parser = _parser()
    omitted = parser.parse_args(["--quarantine-mode", "closure"])
    given = parser.parse_args(["--quarantine-mode", "closure", "--quarantine-channels", "trade,migration"])
    assert "quarantine_channels" not in simulation_config(omitted)
    assert simulation_config(given)["quarantine_channels"] == "trade,migration"
    assert expansion_arguments(omitted) == ["--quarantine-mode=closure"]
    assert expansion_arguments(given) == ["--quarantine-mode=closure", "--quarantine-channels=trade,migration"]
    assert parser.parse_args(expansion_arguments(given)).quarantine_channels == "trade,migration"
    with pytest.raises(ValueError):
        qr.quarantine_arguments(argparse.Namespace(quarantine_mode=None, quarantine_channels="migration"))


@pytest.mark.parametrize("agents", AGENT_MODES)
@pytest.mark.parametrize("mode", qr.QUARANTINE_MODES)
@pytest.mark.parametrize("channels", qr.QUARANTINE_CHANNELS)
def test_catalog_and_run_agree_on_every_mode_and_channel_combination(tmp_path, sentinel_runtimes,
                                                                     agents, mode, channels):
    from chronicler import feature_catalog as fc
    selection = {"quarantine_mode": mode, "quarantine_channels": channels}
    surface = fc.live_surface(_parser().parse_args(["--agents", agents]))
    catalog = fc.validate_features(selection, surface)
    _, refusal = _configure(tmp_path, "--agents", agents, *fc.feature_cli_arguments(selection))
    assert (catalog is None) == (refusal is None), (catalog, refusal)
    assert (refusal is None) == (channels == "trade" or (mode == "closure" and agents in MIGRATING))


# --- resume -------------------------------------------------------------------------------------

def _ticked(migration: bool) -> WorldState:
    world = _world(migration)
    world.epidemics.last_tick_turn = 3
    return world


@pytest.mark.parametrize("saved, given, conflict", [
    (False, None, False), (False, "trade", False), (False, "trade,migration", True),
    (True, None, False), (True, "trade,migration", False), (True, "trade", True),
])
def test_a_ticked_world_keeps_its_channels(tmp_path, sentinel_runtimes, saved, given, conflict):
    flags = ["--agents", "hybrid"] + (["--quarantine-channels", given] if given else [])
    world, refusal = _configure(tmp_path, *flags, world=_ticked(saved))
    if conflict:
        assert refusal.startswith(f"--quarantine-channels {given} conflicts with the saved world")
        assert world.epidemics.quarantine_rules.migration is saved
    else:
        assert refusal is None and world.epidemics.quarantine_rules.migration is saved


def test_a_world_that_never_ticked_takes_the_requested_channels(tmp_path, sentinel_runtimes):
    world, refusal = _configure(tmp_path, "--agents", "hybrid", "--quarantine-channels", "trade",
                                world=_world(True))
    assert refusal is None and world.epidemics.quarantine_rules.migration is False
    assert world.epidemics.quarantine_rules.totals.migrants_blocked is None


def test_saved_migration_closure_refuses_an_aggregate_continuation(tmp_path, sentinel_runtimes):
    _, refusal = _configure(tmp_path, "--agents", "off", world=_ticked(True))
    assert refusal.startswith("this world's saved quarantine rules close migration")


@pytest.mark.parametrize("saved, given, conflicts", [
    (False, None, []), (False, "trade", []), (True, "trade,migration", []),
    (False, "trade,migration", ["--quarantine-channels 'trade,migration' conflicts with the checkpoint "
                                "(saved: 'trade')"]),
    (True, "trade", ["--quarantine-channels 'trade' conflicts with the checkpoint (saved: 'trade,migration')"]),
])
def test_exact_resume_conflicts_read_the_retained_world(saved, given, conflicts):
    args = argparse.Namespace(quarantine_mode=None, quarantine_channels=given)
    assert qr.quarantine_resume_conflicts(_ticked(saved), args, {}) == conflicts
    # A channel the checkpoint recorded is left to main's generic adoption.
    assert qr.quarantine_resume_conflicts(_ticked(saved), args, {"quarantine_channels": "trade"}) == []


def test_exact_aggregate_closure_checkpoint_refuses_the_migration_channel(tmp_path, pure_python_runtimes):
    import chronicler.run_checkpoint as rc
    from chronicler.main import _adopt_checkpoint_args, execute_run
    straight = tmp_path / "straight"
    execute_run(_cli_args(straight, 4, quarantine_mode="closure", checkpoint_every=2,
                          checkpoint=str(straight / "c{turn}.ckpt")))
    parser = _parser()
    path = straight / "c2.ckpt"
    assert "quarantine_channels" not in rc.read_checkpoint(path).state.run_config["simulation_args"]
    args = parser.parse_args(["--resume", str(path), "--quarantine-channels", "trade,migration"])
    assert _adopt_checkpoint_args(parser, args, rc.read_checkpoint(path)) == [
        "--quarantine-channels 'trade,migration' conflicts with the checkpoint (saved: 'trade')"]
    same = parser.parse_args(["--resume", str(path), "--quarantine-channels", "trade"])
    assert _adopt_checkpoint_args(parser, same, rc.read_checkpoint(path)) == []
