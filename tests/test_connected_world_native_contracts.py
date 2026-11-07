"""Connected World transient native contracts; real extension, no paid APIs."""
from __future__ import annotations

import sys
import pytest

pytest.importorskip("chronicler_agents")
pytestmark = pytest.mark.native


def test_native_wealth_stages_close_through_births_deaths_and_migration(tmp_path, monkeypatch):
    import chronicler.main as main
    from chronicler.bundle_codec import load_bundle
    monkeypatch.setattr(sys, "argv", ["chronicler", "--agents", "hybrid", "--simulate-only",
        "--seed", "7", "--turns", "35", "--wealth-accounting",
        "--output", str(tmp_path / "chronicle.md")])
    main.main()
    bundle = load_bundle(tmp_path / "chronicle_bundle.json")
    frames = [s["livelihoods"]["wealth_accounting"]["frame"] for s in bundle["history"]]
    assert sum(f["world"]["births"] for f in frames) > 0
    assert sum(f["world"]["deaths"] for f in frames) > 0
    assert sum(f["world"]["moved"] for f in frames) > 0
    for frame in frames:
        native = frame["native"]
        assert native["source_turn"] == frame["turn"]
        assert native["totals"]["decay"] <= 0
        # No typed package is enabled: every world balance change must be
        # explained by copied physical native stages, including inheritance.
        assert frame["world"]["typed_net_milli"] == 0
        assert frame["world"]["delta"] == pytest.approx(native["modeled_net"], abs=1e-8)


def test_transient_apis_refuse_invalid_rows_without_arming():
    from chronicler_agents import AgentSimulator
    sim = AgentSimulator(2, 7)
    with pytest.raises(ValueError, match="invalid adaptive"):
        sim.set_adaptive_migration(1, [(1, 0, float("nan"))])
    with pytest.raises(ValueError, match="invalid adaptive"):
        sim.set_adaptive_migration(1, [(1, 0, 0.31)])
    with pytest.raises(ValueError, match="invalid adaptive"):
        sim.set_adaptive_migration(1, [(1, 0, 0.1), (1, 0, 0.2)])
    assert sim.cancel_adaptive_migration() is False
    with pytest.raises(ValueError, match="invalid enlisted"):
        sim.set_enlisted_service(1, [(1, 1.1)])
    assert sim.cancel_enlisted_service() is False
    sim.set_wealth_observation(1)
    with pytest.raises(ValueError, match="not completed"):
        sim.take_wealth_observation()
    with pytest.raises(ValueError, match="already pending"):
        sim.set_wealth_observation(1)
    assert sim.cancel_wealth_observation() is True
    assert sim.take_wealth_observation() is None
    assert sim.wealth_transfer_purposes()[10] == "restitution"


def test_movement_branch_input_requires_exact_prior_date_and_is_atomic():
    from chronicler_agents import AgentSimulator
    sim = AgentSimulator(2, 7)
    with pytest.raises(ValueError, match="T-1"):
        sim.set_movement_branches(1, 1, [1], [1])
    with pytest.raises(ValueError, match="invalid"):
        sim.set_movement_branches(0, 1, [1], [])
    with pytest.raises(ValueError, match="duplicate"):
        sim.set_movement_branches(0, 1, [1,1], [1,1])
    sim.set_movement_branches(0, 1, [1], [1])
    with pytest.raises(ValueError, match="already pending"):
        sim.set_movement_branches(0, 1, [2], [1])


def test_information_gate_inputs_are_atomic_and_cancelled_by_owner():
    from chronicler_agents import AgentSimulator
    sim = AgentSimulator(2, 7)
    with pytest.raises(ValueError, match="out of range"):
        sim.set_adaptive_information(1, [(1, 2)])
    assert sim.cancel_adaptive_information() is False
    assert sim.set_adaptive_information(1, [(1, 0)]) == []  # no living person yet
    with pytest.raises(ValueError, match="already pending"):
        sim.set_adaptive_information(1, [])
    assert sim.cancel_adaptive_information() is True
    assert sim.usable_trade_destinations([3, 1, 3], 1) == [(1, []), (3, [])]
    sim.set_movement_branches(0, 1, [1], [1])
    with pytest.raises(ValueError, match="another turn"):
        sim.cancel_movement_branches(2)
    assert sim.cancel_movement_branches(1) is True
    assert sim.cancel_movement_branches(1) is False


def test_information_tick_date_is_checked_before_mutation():
    import pyarrow as pa
    from chronicler_agents import AgentSimulator
    sim = AgentSimulator(2, 7)
    sim.set_adaptive_information(1, [])
    with pytest.raises(ValueError, match="adaptive information must be installed for this tick"):
        sim.tick(2, pa.record_batch({"unused": [0]}))
    assert sim.cancel_adaptive_information() is True


def test_legacy_attribution_observer_refuses_active_adaptive_inputs_in_both_orders():
    from chronicler_agents import AgentSimulator
    sim = AgentSimulator(2, 7)
    sim.configure_decision_delivery(True)
    with pytest.raises(ValueError, match="legacy decision observer"):
        sim.set_adaptive_migration(1, [(1, 0, 0.1)])
    with pytest.raises(ValueError, match="legacy decision observer"):
        sim.set_adaptive_information(1, [])
    assert sim.cancel_adaptive_migration() is False
    assert sim.cancel_adaptive_information() is False
    sim.configure_decision_delivery(False)
    sim.set_adaptive_migration(1, [(1, 0, 0.1)])
    with pytest.raises(ValueError, match="active adaptive inputs"):
        sim.configure_decision_delivery(True)
    with pytest.raises(ValueError, match="driver budget"):
        sim.get_migration_driver_stats()
    assert sim.cancel_adaptive_migration() is True
    # The record_only input has no behavioral effect or attribution gap.
    sim.set_adaptive_migration(1, [])
    sim.configure_decision_delivery(True)
    assert isinstance(sim.get_migration_driver_stats(), dict)


def test_native_wealth_observer_exact_resume_at_active_lifecycle_turns(tmp_path):
    from chronicler.main import execute_run
    from chronicler.run_checkpoint import read_checkpoint
    from test_run_checkpoint_native import _args, _outputs
    straight = tmp_path / "straight"
    execute_run(_args(straight, 35, "hybrid", seed=7, wealth_accounting=True,
        wealth_accounting_mode="strict", checkpoint_every=7, checkpoint=str(straight / "c{turn}.ckpt")))
    for turn in (14, 28):
        saved = read_checkpoint(straight / f"c{turn}.ckpt")
        assert saved.state.world.livelihoods.wealth_accounting._turn is None
        assert saved.state.agent_bridge._sim.take_wealth_observation() is None
        resumed = tmp_path / f"resume_{turn}"
        execute_run(_args(resumed, 35, "off"), checkpoint_resume=saved)
        assert _outputs(resumed) == _outputs(straight)


def _service_sim():
    """Constructed native census fork, separate from natural campaign evidence."""
    import pyarrow as pa
    from chronicler.agent_bridge import AgentBridge
    from chronicler.world_gen import generate_world
    world = generate_world(seed=7)
    world.agent_mode = "hybrid"
    bridge = AgentBridge(world, mode="hybrid")
    from chronicler.agent_bridge import build_region_batch
    # Constructed positive model income, independent of dormant template slot0.
    region_batch = build_region_batch(world)
    index = region_batch.schema.get_field_index("resource_yield_0")
    region_batch = region_batch.set_column(index, "resource_yield_0", pa.array([1.0] * len(world.regions), type=pa.float32()))
    bridge._sim.set_region_state(region_batch)
    rows = pa.record_batch(bridge._sim.get_snapshot()).to_pylist()
    farmers = [r for r in rows if r["region"] == 0 and r["occupation"] == 0 and r["age"] >= 20]
    assert len(farmers) >= 3
    return world, bridge, rows, farmers[0]["id"], farmers[1]["id"]


@pytest.mark.parametrize("fed", [0.0, 1.0])
@pytest.mark.parametrize("free_per_person", [0.0, 0.5])
def test_service_census_has_no_second_civilian_meal_or_purchase(fed, free_per_person):
    from chronicler.agent_bridge import build_signals
    world, bridge, people, enlisted, later_recruit = _service_sim()
    sim = bridge._sim
    # Only the frozen Phase 2 id is installed. A later recruit is deliberately
    # absent: it already contributed to this turn's civilian economy and meal.
    sim.set_enlisted_service(0, [(enlisted, fed)])
    sim.set_wealth_observation(0)
    counts = [sum(p["region"] == r and p["id"] != enlisted for p in people) for r in range(len(world.regions))]
    sim.set_food_allocation(0, 0, .5, .5, [.5] * len(counts), counts)
    sim.set_household_retail(0, 0, [(0, 100, counts[0] * free_per_person)],
                             [(enlisted, 0, 500), (later_recruit, 0, 5000)])
    sim.install_retail_income(0, [0])
    sim.tick(0, build_signals(world), 1.0)
    frame = sim.take_household_retail_frame()
    row = dict(zip(frame[1], frame[2][0], strict=True))
    assert row["phase2_alive"] == counts[0]
    assert row["persons"] == counts[0]
    assert row["free_given"] <= counts[0] * free_per_person + 1e-6
    assert enlisted not in {r[0] for r in frame[5]}
    assert later_recruit in {r[0] for r in frame[5]}
    # Existing ownership survives service: the person can sell a real title,
    # but cannot eat it again or be a civilian buyer. This is not new output.
    claim = next(r for r in frame[3] if r[0] == enlisted)
    assert claim[2] == 0
    money = next((r for r in frame[4] if r[0] == enlisted), (enlisted, 0, 0, 0))
    assert money[1] == money[3] == 0
    assert row["paid_milli"] == row["credited_milli"] + row["refunded_milli"]
    assert row["own_eaten_milli"] + row["sold_milli"] + row["unsold_milli"] == row["offered_milli"]
    totals = {}
    for _, component, amount in sim.take_wealth_observation()[1]:
        totals[component] = totals.get(component, 0.0) + amount
    assert totals["withheld_enlisted"] > 0
    income = dict(sim.take_retail_income_receipt()[1])
    assert income.get(enlisted, 0.0) == 0.0
    assert income[later_recruit] > 0
    # A successful tick consumes the transient input; no stale exclusion.
    assert sim.cancel_enlisted_service() is False
    bridge.close()


@pytest.mark.parametrize("fed", [0.0, 1.0])
def test_service_economy_consumes_only_civilians_and_health_uses_civilian_farmers(fed):
    import pyarrow as pa
    from chronicler.economy import build_economy_region_input_batch, build_economy_trade_route_batch
    world, bridge, people, enlisted, impaired = _service_sim()
    sim = bridge._sim
    sim.set_enlisted_service(0, [(enlisted, fed)])
    # The exclusion list is the Phase 2 census. Impair one remaining civilian
    # farmer by half a work turn; no spouse care is requested here.
    sim.prepare_health_work([impaired], [enlisted], [], .5, 0.0)
    batch = build_economy_region_input_batch(world)
    # Declared linear foraging fixture: one food unit per effective farmer.
    # Rich initial stock ensures civilian demand, not shortage, owns consumption.
    for name in batch.schema.names:
        values = None
        if name.startswith("resource_type_"): values = [255] * len(world.regions)
        elif name.startswith(("farm_labor_", "slot_labor_")): values = [0.0] * len(world.regions)
        elif name == "subsistence_yield": values = [1.0] * len(world.regions)
        elif name == "stockpile_grain": values = [1000.0] * len(world.regions)
        if values is not None:
            index = batch.schema.get_field_index(name)
            batch = batch.set_column(index, name, pa.array(values, type=batch.schema.field(index).type))
    routes = build_economy_trade_route_batch(world, active_trade_routes=[])
    result = pa.record_batch(sim.tick_economy(batch, routes, 0, False, 1.0)[0]).to_pylist()[0]
    residents = [p for p in people if p["region"] == 0 and p["id"] != enlisted]
    civilians = len(residents)
    farmers = sum(p["occupation"] == 0 for p in residents)
    assert result["market_demand_food"] == pytest.approx(civilians * .5)
    assert result["food_consumed"] == pytest.approx(civilians * .5)
    assert result["food_produced"] == pytest.approx(farmers - .5)
    assert result["forage_output"] == pytest.approx(farmers - .5)
    sim.finish_health_work(0, 0.0)
    assert sim.cancel_enlisted_service() is True
    bridge.close()
