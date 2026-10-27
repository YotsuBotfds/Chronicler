"""Native checks of the production ledger (real extension).

docs/integration/production-ledger.md: hybrid turns balance the resource
ledger (CHRONICLER_CHECK_RESOURCES=1), the validation sidecar writes it, it
changes nothing, the economy reports every slot's output, the tick's ledger
columns are consumed once, and the tuning keys restore the earlier rules.
"""
from __future__ import annotations

import json

import pyarrow as pa
import pytest

from chronicler.agent_bridge import build_region_batch
from chronicler.columnar import pylist
from chronicler.economy import build_economy_region_input_batch
from chronicler.models import EMPTY_SLOT, Region, ResourceType, WorldState
from chronicler.production_ledger import (
    LEDGER_FILENAME, RESOURCE_CHECK_ENV, STOCK_FISH, STOCK_RESERVE, read_ledger, summarize_ledger,
)

pytestmark = pytest.mark.native


def _native():
    ca = pytest.importorskip("chronicler_agents")
    if not isinstance(getattr(ca, "AgentSimulator", None), type):
        pytest.skip("requires the chronicler_agents Rust extension")
    if not callable(getattr(ca.AgentSimulator, "set_extraction_config", None)):
        pytest.skip("requires an extension built with the production ledger")
    return ca


def _run(tmp_path, *argv) -> dict:
    """A CLI run (``main()``'s default resolution, then ``execute_run``)."""
    from pathlib import Path
    from chronicler.main import DEFAULT_CONFIG, _build_parser, execute_run
    from chronicler.tuning import load_tuning
    tmp_path.mkdir(parents=True, exist_ok=True)
    args = _build_parser().parse_args([
        *argv, "--simulate-only", "--output", str(tmp_path / "chronicle.md"),
        "--state", str(tmp_path / "state.json"),
    ])
    for key, default in (("civs", "num_civs"), ("regions", "num_regions"),
                         ("reflection_interval", "reflection_interval")):
        if getattr(args, key) is None:
            setattr(args, key, DEFAULT_CONFIG[default])
    args.tuning_overrides = load_tuning(Path(args.tuning)) if args.tuning else {}
    execute_run(args)
    bundle = json.loads((tmp_path / "chronicle_bundle.json").read_text())
    bundle.get("metadata", {}).pop("generated_at", None)
    return bundle


@pytest.mark.parametrize("argv", [
    ("--seed", "42", "--turns", "40"),
    ("--seed", "7", "--turns", "40"),
    ("--seed", "11", "--turns", "30", "--worldgen", "procedural", "--regions", "16", "--civs", "5"),
    # Turn 27, region 3 (64 people on land for 63): the overpopulation soil loss
    # took the mines' target crew from 16 to 15, and the charge recomputed it
    # (16/15 of the rule) until the 2026-10-27 ordering correction.
    ("--seed", "64", "--turns", "28", "--worldgen", "procedural", "--regions", "32", "--civs", "10"),
])
def test_hybrid_turns_balance_the_resource_ledger(tmp_path, monkeypatch, argv):
    _native()
    monkeypatch.setenv(RESOURCE_CHECK_ENV, "1")
    _run(tmp_path, *argv, "--agents", "hybrid")


def test_the_sidecar_writes_a_ledger_that_reconciles(tmp_path):
    _native()
    _run(tmp_path, "--seed", "43", "--turns", "40", "--agents", "hybrid", "--validation-sidecar")
    rows = read_ledger(tmp_path / LEDGER_FILENAME)
    n = len(rows["turn"])
    assert n > 0 and sorted(set(rows["turn"])) == list(range(40))
    assert all(rows["realized"]), "every hybrid turn has an economy tick"
    kinds = set(rows["stock_kind"])
    assert {STOCK_RESERVE, STOCK_FISH} <= kinds
    for i in range(n):
        if rows["stock_kind"][i]:
            assert rows["stock_after"][i] == pytest.approx(
                rows["stock_before"][i] - rows["depletion"][i] + rows["recovery"][i], abs=1e-6)
        if rows["stock_kind"][i] == STOCK_FISH:
            assert rows["lost"][i] == pytest.approx(0.0, abs=1e-12)   # the landed-catch rule
            assert rows["depletion"][i] <= rows["reserved_before"][i] + 1e-9
        if rows["stock_kind"][i] == STOCK_RESERVE and rows["output"][i] == 0.0:
            assert rows["depletion"][i] == 0.0                         # no ore, no draw
    summary = summarize_ledger(rows)
    assert summary["mineral_realized_share"] == 1.0
    assert summary["overextraction_pressure_max"] < 1.0


def test_the_ledger_changes_nothing(tmp_path, monkeypatch):
    _native()
    monkeypatch.delenv(RESOURCE_CHECK_ENV, raising=False)
    plain = _run(tmp_path / "plain", "--seed", "44", "--turns", "30", "--agents", "hybrid")
    monkeypatch.setenv(RESOURCE_CHECK_ENV, "1")
    ledgered = _run(tmp_path / "ledger", "--seed", "44", "--turns", "30", "--agents", "hybrid",
                    "--validation-sidecar")
    assert (tmp_path / "ledger" / LEDGER_FILENAME).is_file()
    assert json.dumps(plain, sort_keys=True) == json.dumps(ledgered, sort_keys=True)


def test_the_tuning_keys_restore_the_earlier_rules(tmp_path, monkeypatch):
    _native()
    tuning = tmp_path / "old.yaml"
    tuning.write_text("ecology:\n  overextraction_realized: 0\n  mine_soil_realized: 0\n"
                      "  fishery_charges_landed_catch: 0\n  yield_penalty_reaches_goods: 0\n")
    monkeypatch.setenv(RESOURCE_CHECK_ENV, "1")   # the checks follow the configured rules
    _run(tmp_path / "run", "--seed", "45", "--turns", "40", "--agents", "hybrid", "--validation-sidecar",
         "--tuning", str(tuning))
    rows = read_ledger(tmp_path / "run" / LEDGER_FILENAME)
    lost = 0.0
    for i in range(len(rows["turn"])):
        if rows["sustainable"][i] > 0:
            assert rows["take"][i] == rows["proxy_take"][i]           # population / 5
        assert rows["mine_soil"][i] == rows["proxy_mine_soil"][i]     # flat per mine
        if rows["stock_kind"][i] == STOCK_FISH:
            assert rows["depletion"][i] == pytest.approx(rows["reserved_before"][i])  # full charge
            lost += rows["lost"][i]
    assert lost > 0, "some allowance went unlanded and was charged anyway"


# --- the tick's ledger columns, turn by turn ------------------------------------------------

ORE = int(ResourceType.ORE)


def _mine_world() -> WorldState:
    from chronicler.models import Civilization, Leader
    region = Region(name="R0", terrain="mountains", carrying_capacity=60, resources="mineral",
                    population=60, controller="A")
    region.resource_types = [ORE, EMPTY_SLOT, EMPTY_SLOT]
    region.resource_base_yields = [1.0, 0.0, 0.0]
    region.resource_effective_yields = [1.0, 0.0, 0.0]
    region.resource_current_yields = [1.0, 0.0, 0.0]
    civ = Civilization(name="A", population=60, military=30, economy=40, culture=30, stability=50,
                       leader=Leader(name="Ruler", trait="cautious", reign_start=0), regions=["R0"])
    world = WorldState(name="T", seed=42, regions=[region], civilizations=[civ])
    world.agent_mode = "hybrid"
    return world


def _economy(sim, world):
    routes = pa.record_batch({
        "origin_region_id": pa.array([], type=pa.uint16()),
        "dest_region_id": pa.array([], type=pa.uint16()),
        "is_river": pa.array([], type=pa.bool_()),
    })
    out = sim.tick_economy(build_economy_region_input_batch(world), routes, 0, False, 1.0)
    batch = pa.record_batch(out[0])
    return [pylist(batch.column(f"slot_output_{s}"))[0] for s in range(3)], pylist(batch.column("forage_output"))[0]


def _ledger_columns(region_batch) -> dict:
    batch = pa.record_batch(region_batch)
    return {name: pylist(batch.column(name))[0] for name in (
        "extraction_realized", "mineral_drawn_0", "proxy_mineral_draw_0", "extraction_target_crew",
        "overextraction_take_0", "resource_reserve_0")}


def test_the_ledger_columns_are_consumed_once():
    ca = _native()
    world = _mine_world()
    sim = ca.AgentSimulator(num_regions=1, seed=42)
    sim.set_region_state(build_region_batch(world))
    outputs, forage = _economy(sim, world)
    assert outputs[0] > 0.0 and forage >= 0.0
    first = _ledger_columns(sim.tick_ecology(0, 0, [False], [False])[0])
    assert first["extraction_realized"] is True
    assert first["mineral_drawn_0"] == pytest.approx(1.0 - first["resource_reserve_0"], abs=1e-7)
    assert first["mineral_drawn_0"] == pytest.approx(
        outputs[0] / first["extraction_target_crew"] * 0.009, rel=1e-5)
    assert first["overextraction_take_0"] == pytest.approx(outputs[0] / 1.0, rel=1e-6)
    # A tick without an economy tick: the proxy, and the proxy draw is the draw.
    second = _ledger_columns(sim.tick_ecology(1, 0, [False], [False])[0])
    assert second["extraction_realized"] is False
    assert second["mineral_drawn_0"] == second["proxy_mineral_draw_0"] > 0.0
    assert second["overextraction_take_0"] == 60 // 5


def test_the_off_mode_simulator_reports_the_proxy():
    ca = _native()
    if not isinstance(getattr(ca, "EcologySimulator", None), type):
        pytest.skip("requires the EcologySimulator")
    world = _mine_world()
    world.agent_mode = "off"
    eco = ca.EcologySimulator()
    eco.set_region_state(build_region_batch(world))
    cols = _ledger_columns(eco.tick_ecology(0, 0, [False], [False])[0])
    assert cols["extraction_realized"] is False
    assert cols["mineral_drawn_0"] == cols["proxy_mineral_draw_0"] > 0.0
