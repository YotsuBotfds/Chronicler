"""Quarantine closure of migration (connected-world C1b) with the real extension.

The FFI install, validation and receipt lifecycle; a hybrid run in which no
agent migration crosses a pair closed for its tick while the trade-only arm's
migrants do; every agent mode with native migration observes a receipt each
tick; and an exact hybrid resume during an active migration closure. Run
against a freshly built extension.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

import chronicler.contact_ledger as cl
import chronicler.epidemiology as ep
import chronicler.quarantine_rules as qr

pytestmark = pytest.mark.native

_REAL_INSTALL = qr.install_migration_closure
_REAL_UPDATE = cl.update_contact_ledger


def _native():
    native = pytest.importorskip("chronicler_agents")
    sim = getattr(native, "AgentSimulator", None)
    if not isinstance(sim, type) or not hasattr(sim, "set_migration_closure") \
            or not hasattr(sim, "checkpoint_state"):
        pytest.skip("requires a fresh chronicler_agents build (migration closure and exact checkpoints)")
    return native


def _world(seed: int = 7, mode: str = "closure", migration: bool = True, agents: str = "hybrid"):
    from chronicler.world_gen import generate_world
    world = generate_world(seed=seed, num_regions=8, num_civs=4)
    world.campaigns_enabled = True
    world.agent_mode = agents
    cl.set_contact_ledger_enabled(world, True)
    ep.set_epidemiology_enabled(world, True)
    rules = world.epidemics.quarantine_rules = qr.QuarantineRulesState(mode=mode, migration=migration)
    if migration:
        rules.totals.migrants_blocked = rules.totals.migrants_blocked_flight = 0
    return world


# --- the FFI seam ----------------------------------------------------------------------------

def test_ffi_validates_installs_and_takes_the_receipt_once():
    _native()
    from chronicler.agent_bridge import AgentBridge, build_signals
    world = _world(migration=False)
    bridge = AgentBridge(world, mode="hybrid")
    sim = bridge._sim
    n = len(world.regions)
    with pytest.raises(ValueError, match="match the region count"):
        sim.set_migration_closure(world.turn, [0] * (n - 1), [(0, 1)])
    with pytest.raises(ValueError, match="two distinct civilizations"):
        sim.set_migration_closure(world.turn, [0] * n, [(2, 2)])
    assert sim.cancel_migration_closure() is False
    sim.set_migration_closure(world.turn + 5, [0] * n, [(0, 1)])
    with pytest.raises(ValueError, match="already pending"):
        sim.set_migration_closure(world.turn + 5, [0] * n, [])
    bridge.sync_regions(world)
    with pytest.raises(ValueError, match="migration closure must be installed for this tick"):
        sim.tick(world.turn, build_signals(world))
    assert sim.cancel_migration_closure() is True
    sim.set_migration_closure(world.turn, [0] * n, [(1, 0)])
    sim.tick(world.turn, build_signals(world))
    assert sim.take_migration_closure_receipt(world.turn + 1) is None
    assert sim.take_migration_closure_receipt(world.turn) == []    # one polity everywhere: nothing refused
    assert sim.take_migration_closure_receipt(world.turn) is None   # taken once
    sim.tick(world.turn + 1, build_signals(world))                   # no closure: nothing pending
    assert sim.take_migration_closure_receipt(world.turn + 1) is None


# --- a hybrid run: no crossing of a pair closed for its tick ---------------------------------

def _hybrid_run(migration: bool, turns: int, monkeypatch, agents: str = "hybrid"):
    from chronicler.action_engine import ActionEngine
    from chronicler.agent_bridge import AgentBridge
    from chronicler.history_index import history_index
    from chronicler.simulation import run_turn

    world = _world(migration=migration, agents=agents)
    bridge = AgentBridge(world, mode=agents)
    tokens: dict[int, tuple] = {}
    moves: dict[int, list[tuple[int, int, str | None, str | None]]] = {}
    receipts: dict[int, qr.QuarantineReceipt] = {}

    def install(w, sim):
        token = _REAL_INSTALL(w, sim)
        if token is not None:
            tokens[w.turn] = token
        return token

    def update(w):
        # The turn's agent migrations, with controllers read at the end of the turn.
        moves[w.turn] = [(e.region, e.target_region) for e in history_index(w).agent_migrations_for_turn(w, w.turn)]
        _REAL_UPDATE(w)

    monkeypatch.setattr(qr, "install_migration_closure", install)
    monkeypatch.setattr(cl, "update_contact_ledger", update)
    for _ in range(turns):
        engine = ActionEngine(world)
        run_turn(world, lambda c, w, e=engine: e.select_action(c, seed=w.seed), lambda w, ev: "",
                 seed=world.seed + world.turn, agent_bridge=bridge)
        receipt = world.epidemics.quarantine_rules.receipt
        receipts[receipt.turn] = receipt.model_copy(deep=True)
    return world, tokens, moves, receipts


def _closed_crossings(world, receipt, moves) -> int:
    """Moves between the two polities (controllers now) of a pair closed this turn."""
    civs = world.civilizations
    pairs = {tuple(sorted((civs[a].name, civs[b].name))) for a, b in receipt.decided}
    count = 0
    for src, dst in moves:
        ca, cb = world.regions[src].controller, world.regions[dst].controller
        if ca and cb and ca != cb and tuple(sorted((ca, cb))) in pairs:
            count += 1
    return count


def test_hybrid_migration_closure_refuses_every_crossing_of_a_pair_closed_for_its_tick(monkeypatch):
    _native()
    turns = 24
    closed, tokens, moves, receipts = _hybrid_run(True, turns, monkeypatch)
    trade, trade_tokens, trade_moves, trade_receipts = _hybrid_run(False, turns, monkeypatch)
    assert trade_tokens == {}                                     # trade only: nothing installed
    assert len(tokens) == turns                                   # installed every tick
    first = min(t for t, r in receipts.items() if r.decided)
    for t in range(1, first):
        assert moves[t] == trade_moves[t]                        # identical until the first closure
    refused = crossed = 0
    for t, receipt in receipts.items():
        assert receipt.migrants_blocked is not None              # observed every tick
        _, region_civ, by_pair = tokens[t]
        open_pairs = {(min(a, b), max(a, b)) for a, b in by_pair}
        for src, dst in moves[t]:
            a, b = region_civ[src], region_civ[dst]
            assert a == b or 255 in (a, b) or (min(a, b), max(a, b)) not in open_pairs, (t, src, dst)
        refused += qr.blocked_counts(receipt.migrants_blocked)[0]
        assert {row[0] for row in receipt.migrants_blocked} <= set(by_pair.values())
        crossed += _closed_crossings(trade, trade_receipts[t], trade_moves[t])
        assert trade_receipts[t].migrants_blocked is None
    print(f"refused {refused}, trade-only crossings of closed pairs {crossed}, first closure {first}")
    assert refused > 0 and crossed > 0, (refused, crossed)
    totals = closed.epidemics.quarantine_rules.totals
    assert totals.migrants_blocked + qr.blocked_counts(closed.epidemics.quarantine_rules.receipt.migrants_blocked)[0] \
        == refused
    assert trade.epidemics.quarantine_rules.totals.migrants_blocked is None


@pytest.mark.parametrize("agents", ["shadow", "demographics-only"])
def test_every_agent_mode_with_native_migration_observes_each_tick(monkeypatch, agents):
    _native()
    world, tokens, _, receipts = _hybrid_run(True, 8, monkeypatch, agents=agents)
    assert len(tokens) == 8 and all(r.migrants_blocked is not None for r in receipts.values())


# --- exact hybrid resume during an active migration closure ----------------------------------

def _args(folder: Path, turns: int, **extra) -> argparse.Namespace:
    args = argparse.Namespace(
        seed=7, turns=turns, civs=4, regions=8, output=str(folder / "chronicle.md"),
        state=str(folder / "state.json"), resume=None, reflection_interval=10, llm_actions=False,
        scenario=None, simulate_only=True, agents="hybrid", tuning_overrides={},
    )
    for key, value in extra.items():
        setattr(args, key, value)
    return args


def _outputs(folder: Path, after: int = -1) -> dict[str, bytes]:
    from chronicler.bundle_codec import load_bundle
    out = {}
    for path in sorted(folder.rglob("*")):
        if not path.is_file() or path.suffix == ".ckpt":
            continue
        stem = path.stem
        if "_turn_" in stem and int(stem.rsplit("_", 1)[1]) <= after:
            continue
        if path.name == "chronicle_bundle.json":
            data = load_bundle(path)
            data["metadata"].pop("generated_at", None)
            out[path.name] = json.dumps(data, sort_keys=True).encode()
        else:
            out[path.relative_to(folder).as_posix()] = path.read_bytes()
    return out


def test_exact_hybrid_resume_during_an_active_migration_closure(tmp_path):
    _native()
    import chronicler.run_checkpoint as rc
    from chronicler.main import execute_run

    straight = tmp_path / "straight"
    execute_run(_args(straight, 14, quarantine_mode="closure", quarantine_channels="trade,migration",
                      checkpoint_every=2, checkpoint=str(straight / "c{turn}.ckpt")))
    chosen = []
    for k in range(2, 14, 2):
        loaded = rc.read_checkpoint(straight / f"c{k}.ckpt")
        assert loaded.state.run_config["simulation_args"]["quarantine_channels"] == "trade,migration"
        rules = loaded.state.world.epidemics.quarantine_rules
        if rules.closures and rules.receipt.migrants_blocked:
            chosen.append(k)
    assert chosen, "no checkpoint inside an active closure that refused migrants"
    for k in chosen[:2]:
        resumed = tmp_path / f"resumed_{k}"
        execute_run(_args(resumed, 14), checkpoint_resume=rc.read_checkpoint(straight / f"c{k}.ckpt"))
        expected, got = _outputs(straight, after=k), _outputs(resumed)
        assert got.keys() == expected.keys()
        assert [name for name in got if got[name] != expected[name]] == []
    state = json.loads((straight / "state.json").read_text())["epidemics"]["quarantine_rules"]
    assert state["migration"] is True and state["totals"]["migrants_blocked"] > 0
