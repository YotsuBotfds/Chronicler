"""Household food retail (L6b, option R) on the real compiled extension.

Drives the native FFI contract directly on a small constructed world (a
template development world, seed 7): the PL4-python package does not exist
yet, so the test plays its part with plain arithmetic. It checks that title,
sale, payment, ration and income replacement each move exactly once and
close, and that without the retail inputs every existing output keeps its
bits.
"""
import importlib
import math
import struct

import pytest

pytest.importorskip("chronicler_agents")
pytestmark = pytest.mark.native

pa = pytest.importorskip("pyarrow")

FOOD = ("grain", "fish", "salt", "botanicals", "exotic")
RETAIL_INPUTS = ("retail_title_share", *(f"retail_owned_{g}" for g in FOOD))
RETAIL_OUTPUTS = (*(f"retail_{k}_{g}" for k in ("titled", "owned_close", "owned_decay", "owned_overflow")
                    for g in FOOD), "commons_consumed", "commons_sufficiency")
LEDGER = ("opening", "produced", "transport_net", "craft_input", "clamp_correction", "pre_consumption",
          "consumed", "storage_loss", "cap_overflow", "closing")
WEALTH_DECAY = 0.02          # crate::agent::WEALTH_DECAY
MILLI_PER_RATION = 500       # 1000 milli-food = one food unit = two rations


def _live(seed=7, turns=2):
    from chronicler.action_engine import ActionEngine
    from chronicler.agent_bridge import AgentBridge
    from chronicler.simulation import run_turn
    from chronicler.world_gen import generate_world
    world = generate_world(seed=seed, num_regions=8, num_civs=4)
    world.agent_mode = "hybrid"
    bridge = AgentBridge(world, mode="hybrid")
    engine = ActionEngine(world)
    for _ in range(turns):
        run_turn(world, lambda c, w: engine.select_action(c, seed=w.seed), lambda w, e: "",
                 seed=world.seed, agent_bridge=bridge)
    return world, bridge._sim


def _economy_inputs(world):
    from chronicler.economy import build_economy_region_input_batch, build_economy_trade_route_batch
    return build_economy_region_input_batch(world), build_economy_trade_route_batch(world, active_trade_routes=[])


def _with(batch, columns, dtype=None):
    arrays, names = list(batch.columns), list(batch.schema.names)
    for name, values in columns.items():
        arrays.append(pa.array(values, type=dtype or pa.float32()))
        names.append(name)
    return pa.RecordBatch.from_arrays(arrays, names=names)


def _bits(column):
    return [("f", struct.pack("<d", v)) if isinstance(v, float) else ("v", v) for v in column.to_pylist()]


def _same_columns(a, b, names):
    return all(_bits(a.column(n)) == _bits(b.column(n)) for n in names)


def _empty_food_stock(batch, region):
    """Constructed stress (labelled): no commons food on hand in `region`."""
    for g in FOOD:
        index = batch.schema.get_field_index(f"stockpile_{g}")
        values = batch.column(index).to_pylist()
        values[region] = 0.0
        batch = batch.set_column(index, f"stockpile_{g}", pa.array(values, type=pa.float32()))
    return batch


def _pilot_columns(n, region, theta, owned):
    cols = {"retail_title_share": [theta if i == region else None for i in range(n)]}
    for g in FOOD:
        cols[f"retail_owned_{g}"] = [owned.get(g, 0.0) if i == region else None for i in range(n)]
    return cols


def _value(batch, name, row):
    return batch.column(name).to_pylist()[row]


def test_the_extension_is_compiled_and_has_the_retail_methods():
    compiled = importlib.import_module("chronicler_agents.chronicler_agents")
    assert compiled.__file__.endswith((".so", ".pyd"))
    from chronicler_agents import AgentSimulator
    for name in ("set_household_retail", "cancel_household_retail", "take_household_retail_frame",
                 "install_retail_income", "cancel_retail_income", "take_retail_income_receipt"):
        assert callable(getattr(AgentSimulator, name)), name
    purposes = AgentSimulator.wealth_transfer_purposes()
    assert purposes[:5] == ["workshop_wage", "relocation_fare", "apprentice_stipend", "repair_wage", "remittance"]
    assert purposes[5:] == ["food_purchase", "food_procurement"]


def test_economy_retail_columns_title_and_close_and_absent_inputs_keep_every_bit():
    world, sim = _live()
    batch, routes = _economy_inputs(world)
    n = batch.num_rows
    sim.tick_economy(batch, routes, 0, False, 1.0)        # drain this turn's merchant deliveries
    base = sim.tick_economy(batch, routes, 0, False, 1.0)
    again = sim.tick_economy(batch, routes, 0, False, 1.0)
    for x, y in zip(base, again, strict=True):
        assert _same_columns(x, y, x.schema.names)
    base_names = base[0].schema.names
    assert not set(RETAIL_OUTPUTS) & set(base_names)
    # Present but all null (no pilot region): every existing output keeps its
    # bits in all five batches; the retail columns are appended, all null.
    nulls = sim.tick_economy(_with(batch, {c: [None] * n for c in RETAIL_INPUTS}), routes, 0, False, 1.0)
    assert nulls[0].schema.names == [*base_names, *RETAIL_OUTPUTS]
    assert all(v is None for c in RETAIL_OUTPUTS for v in nulls[0].column(c).to_pylist())
    for x, y in zip(base, nulls, strict=True):
        assert _same_columns(x, y, x.schema.names)
    # One pilot region: the most productive one.
    produced = base[0].column("food_produced").to_pylist()
    r = max(range(n), key=lambda i: produced[i])
    assert produced[r] > 0
    owned = {"grain": 3.0, "fish": 0.25}
    out = sim.tick_economy(_with(batch, _pilot_columns(n, r, 0.9, owned)), routes, 0, False, 1.0)[0]
    titled = sum(_value(out, f"retail_titled_{g}", r) for g in FOOD)
    assert titled == pytest.approx(0.9 * produced[r], rel=1e-5)
    for g in FOOD:
        close = (owned.get(g, 0.0) + _value(out, f"retail_titled_{g}", r) - _value(out, f"retail_owned_decay_{g}", r)
                 - _value(out, f"retail_owned_overflow_{g}", r))
        assert _value(out, f"retail_owned_close_{g}", r) == pytest.approx(close, abs=1e-5)
    ledger = {k: _value(out, f"food_{k}", r) for k in LEDGER}
    terms = [ledger["opening"], ledger["produced"], ledger["transport_net"], -ledger["craft_input"],
             ledger["clamp_correction"], -ledger["consumed"], -ledger["storage_loss"], -ledger["cap_overflow"]]
    assert ledger["closing"] == pytest.approx(math.fsum(terms), abs=1e-5 * max(1.0, sum(map(abs, terms))))
    commons_open = sum(_value(batch, f"stockpile_{g}", r) for g in FOOD)
    assert ledger["opening"] == pytest.approx(commons_open + sum(owned.values()), abs=1e-5)
    commons_close = sum(_value(out, f"stockpile_{g}", r) for g in FOOD)
    owned_close = sum(_value(out, f"retail_owned_close_{g}", r) for g in FOOD)
    assert ledger["closing"] == pytest.approx(commons_close + owned_close, abs=1e-4)
    assert _value(out, "commons_consumed", r) == ledger["consumed"]
    # Owned food is supply and availability: the carried stock after its
    # opening decay and cap (this turn's title is not in Phase A's supply).
    carried = sum(_value(out, f"retail_owned_close_{g}", r) - _value(out, f"retail_titled_{g}", r) for g in FOOD)
    assert carried == pytest.approx(sum(owned.values()) - sum(
        _value(out, f"retail_owned_decay_{g}", r) + _value(out, f"retail_owned_overflow_{g}", r) for g in FOOD), abs=1e-5)
    assert 0 < carried < sum(owned.values())
    assert _value(out, "market_supply_food", r) == pytest.approx(
        _value(base[0], "market_supply_food", r) + carried, abs=1e-4)
    assert _value(out, "food_sufficiency", r) >= _value(base[0], "food_sufficiency", r)
    assert all(v is None for i, v in enumerate(out.column("retail_titled_grain").to_pylist()) if i != r)
    others = [name for name in base_names if name.startswith(("stockpile_", "food_"))]
    for i in range(n):
        if i != r:
            assert all(_bits(out.column(c))[i] == _bits(base[0].column(c))[i] for c in others)
    # Refusals, each before any change.
    bad = [
        _with(batch, {"retail_title_share": [None] * n}),
        _with(batch, {c: [None] * n for c in RETAIL_INPUTS[:-1]}),
        _with(batch, {c: [None] * n for c in RETAIL_INPUTS}, dtype=pa.float64()),
        _with(batch, {**{c: [None] * n for c in RETAIL_INPUTS}, "retail_owned_grain": [1.0] * n}),
        _with(batch, _pilot_columns(n, r, 1.5, {})),
        _with(batch, _pilot_columns(n, r, 0.9, {"fish": -1.0})),
        _with(batch, {**_pilot_columns(n, r, 0.9, {}), "retail_owned_salt": [None] * n}),
    ]
    for b in bad:
        with pytest.raises(ValueError):
            sim.tick_economy(b, routes, 0, False, 1.0)
    sim.set_hybrid_economy_mode(False)
    with pytest.raises(ValueError, match="hybrid economy"):
        sim.tick_economy(_with(batch, _pilot_columns(n, r, 0.9, {})), routes, 0, False, 1.0)
    sim.set_hybrid_economy_mode(True)
    after = sim.tick_economy(batch, routes, 0, False, 1.0)
    for x, y in zip(base, after, strict=True):
        assert _same_columns(x, y, x.schema.names)


def _snapshot(sim):
    snap = sim.get_snapshot()
    cols = {c: snap.column(c).to_pylist() for c in ("id", "region", "occupation", "age", "wealth",
                                                    "parent_id_0", "parent_id_1")}
    return [dict(zip(cols, row, strict=True)) for row in zip(*cols.values(), strict=True)]


def _largest_remainder(total, keys):
    base, left = divmod(total, len(keys))
    return {k: base + (1 if i < left else 0) for i, k in enumerate(sorted(keys))}


def test_title_sale_payment_ration_and_income_move_exactly_once_and_close():
    from chronicler.agent_bridge import build_region_batch, build_signals
    from chronicler.ffi_constants import BOND_TYPES
    (wa, sa), (wb, sb) = _live(), _live()          # retail and control: the same deterministic world
    people = _snapshot(sa)
    assert people == _snapshot(sb)
    turn, n = wa.turn, len(wa.regions)
    farmers = {}
    for p in people:
        if p["occupation"] == 0:
            farmers.setdefault(p["region"], []).append(p["id"])
    r = max(farmers, key=lambda k: len(farmers[k]))
    assert len(farmers[r]) >= 3
    # Phase 2: the pilot split on the retail sim, the plain economy on the
    # control. The pilot region starts with no commons on hand (constructed
    # stress), so its free pool is the untitled tenth of the harvest.
    batch, routes = _economy_inputs(wa)
    batch = _empty_food_stock(batch, r)
    economy = sa.tick_economy(_with(batch, _pilot_columns(n, r, 0.9, {})), routes, 0, False, 1.0)[0]
    control_batch, control_routes = _economy_inputs(wb)
    sb.tick_economy(_empty_food_stock(control_batch, r), control_routes, 0, False, 1.0)
    titled = sum(_value(economy, f"retail_titled_{g}", r) for g in FOOD)
    assert titled > 0
    owned_milli = math.floor(sum(_value(economy, f"retail_owned_close_{g}", r) for g in FOOD) * 1000)
    # Python's part, played here: title split equally over the region's
    # farmers, plus a claim of an owner who lives elsewhere (only for sale).
    claims = _largest_remainder(owned_milli, farmers[r])
    absent = next(p["id"] for p in people if p["region"] != r and p["age"] >= 20)
    rows = [(owner, r, milli) for owner, milli in sorted(claims.items())] + [(absent, r, 400)]
    price_food = _value(economy, "market_price_food", r)
    price = math.floor(min(max(price_food, 0.5), 3.0) * 0.5 * 1000)
    free = _value(economy, "commons_consumed", r) / 0.5
    # A short region, the same in both runs; L2 equal on both.
    for world, sim in ((wa, sa), (wb, sb)):
        region_batch = build_region_batch(world)
        fs = region_batch.column("food_sufficiency").to_pylist()
        fs[r] = 0.7
        index = region_batch.schema.get_field_index("food_sufficiency")
        sim.set_region_state(region_batch.set_column(index, "food_sufficiency", pa.array(fs, type=pa.float32())))
        counts = [sum(1 for p in people if p["region"] == i) for i in range(n)]
        sim.set_food_allocation(turn, 0, 0.5, 0.5, [float("nan")] * n, counts)
    # Installs: validation refuses bad ones and leaves nothing pending.
    for regions, claim_rows, mode in [([(r, price, free)], rows, 3), ([(n, price, free)], [], 0),
                                      ([(r, price, free), (r, price, free)], [], 0), ([(r, -1, free)], [], 0),
                                      ([(r, price, float("nan"))], [], 0), ([(r, price, free)], [(absent, (r + 1) % n, 5)], 0),
                                      ([(r, price, free)], rows + rows[:1], 0), ([(r, price, free)], [(absent, r, -5)], 0)]:
        with pytest.raises(ValueError):
            sa.set_household_retail(turn, mode, regions, claim_rows)
    assert sa.cancel_household_retail() is False
    for bad in ([n], [r, r]):
        with pytest.raises(ValueError):
            sa.install_retail_income(turn, bad)
    assert sa.cancel_retail_income() is False
    # The tick refuses an install for another turn, unchanged, then runs.
    sa.set_household_retail(turn + 1, 0, [(r, price, free)], rows)
    with pytest.raises(ValueError, match="installed for this tick"):
        sa.tick(turn, build_signals(wa))
    assert sa.cancel_household_retail() is True
    sa.set_household_retail(turn, 0, [(r, price, free)], rows)
    with pytest.raises(ValueError, match="already pending"):
        sa.set_household_retail(turn, 0, [(r, price, free)], rows)
    sa.install_retail_income(turn, [r])
    with pytest.raises(ValueError, match="already pending"):
        sa.install_retail_income(turn, [r])
    spouse = {}
    for p in people:
        for target, _sentiment, bond, _formed in sa.get_agent_relationships(p["id"]) or []:
            if bond == BOND_TYPES["marriage"]:
                spouse[p["id"]] = target
    events_a = sa.tick(turn, build_signals(wa))
    events_b = sb.tick(turn, build_signals(wb))
    # Exactly once: each receipt is taken once; the control has none.
    frame = sa.take_household_retail_frame()
    assert frame is not None and sa.take_household_retail_frame() is None
    receipt = sa.take_retail_income_receipt()
    assert receipt is not None and sa.take_retail_income_receipt() is None
    assert sb.take_household_retail_frame() is None and sb.take_retail_income_receipt() is None
    source, columns, region_rows, claim_rows, money, sample, dropped = frame
    assert source == turn and len(region_rows) == 1
    row = dict(zip(columns, region_rows[0], strict=True))
    # The columns PL4-python requires (household_retail.FRAME_COLUMNS) are all present.
    assert {"region", "price_milli", "free_rations", "free_given", "free_unallocated", "offered_milli",
            "own_eaten_milli", "sold_milli", "unsold_milli", "paid_milli", "credited_milli", "refunded_milli",
            "rations", "persons", "priced_out_persons", "offer_short_persons"} <= set(columns)
    assert (row["region"], row["mode"], row["price_milli"], row["milli_food_per_ration"]) == (r, 0, price, MILLI_PER_RATION)
    assert row["free_given"] + row["free_unallocated"] == pytest.approx(free, abs=1e-9)
    # Food: the claims close and every ration is free plus own plus bought.
    assert row["offered_milli"] == owned_milli + 400
    eaten = sum(c[2] for c in claim_rows)
    sold = sum(c[3] for c in claim_rows)
    assert row["own_eaten_milli"] == eaten == row["own_eaten_fair_milli"] + row["own_eaten_open_milli"]
    assert row["sold_milli"] == sold == row["sold_fair_milli"] + row["sold_open_milli"]
    assert eaten + sold + row["unsold_milli"] == row["offered_milli"]
    assert row["rations"] == pytest.approx(row["free_given"] + (eaten + sold) / MILLI_PER_RATION, abs=1e-6)
    assert sold > 0 and row["paid_milli"] > 0
    assert {(c[0], c[1]) for c in claim_rows} == {(o, rr) for o, rr, _ in rows}
    assert next(c for c in claim_rows if c[0] == absent)[2] == 0          # an absent owner only sells
    assert len(sample) + dropped == row["persons"]
    assert all(0.0 <= s[3] <= 1.0 and s[1] == r and s[5] in (0, 1, 2) for s in sample)
    assert sum(1 for s in sample if s[5] == 0) == row["fed_fair"]
    # Money: debits equal credits plus refunds exactly; nobody below zero.
    assert row["paid_milli"] == row["credited_milli"] + row["refunded_milli"]
    assert sum(m[1] for m in money) == row["paid_milli"] == sum(m[2] + m[3] for m in money)
    # Income replacement: one row per farmer of the pilot region alive at 0.5.
    assert receipt[0] == turn
    replaced = dict(receipt[1])
    assert set(replaced) <= set(farmers[r]) and len(replaced) == len(receipt[1])
    assert sum(replaced.values()) > 0
    # Per person, against the control run: wealth differs by exactly the
    # money settled and the farm income replaced, for everyone not touched by
    # an inheritance this tick (deaths may differ between the runs).
    dead = set()
    for events in (events_a, events_b):
        kinds, ids = events.column("event_type").to_pylist(), events.column("agent_id").to_pylist()
        dead |= {i for k, i in zip(kinds, ids, strict=True) if k == 0}
    by_id = {p["id"]: p for p in people}
    heirs = {i for i, p in by_id.items() if p["parent_id_0"] in dead or p["parent_id_1"] in dead
             or spouse.get(i) in dead}
    after_a = {p["id"]: p["wealth"] for p in _snapshot(sa)}
    after_b = {p["id"]: p["wealth"] for p in _snapshot(sb)}
    net = {m[0]: (m[2] + m[3] - m[1]) / 1000 for m in money}
    compared = 0
    for i in by_id:
        if i in dead or i in heirs or i not in after_a or i not in after_b:
            continue
        expected = net.get(i, 0.0) - replaced.get(i, 0.0) * (1.0 - WEALTH_DECAY)
        tolerance = 2e-5 + 2e-6 * abs(after_b[i])
        assert after_a[i] - after_b[i] == pytest.approx(expected, abs=tolerance), i
        assert after_a[i] >= 0.0
        compared += 1
    assert compared >= 0.8 * len(people)
    assert all(i in after_a or i in dead for i in net)
    # The purchase key is consumed; the next tick runs neither step.
    with pytest.raises(ValueError, match="already applied"):
        sa.transfer_wealth(turn, 5, 0, [(absent, 1)])
    sa.set_food_allocation(turn + 1, 0, 0.5, 0.5, [float("nan")] * n,
                           [sum(1 for p in _snapshot(sa) if p["region"] == i) for i in range(n)])
    sa.tick(turn + 1, build_signals(wa))
    assert sa.take_household_retail_frame() is None and sa.take_retail_income_receipt() is None
    assert sa.take_food_allocation_frame() is not None


def test_retail_without_the_food_allocation_is_refused_by_the_tick():
    from chronicler.agent_bridge import build_signals
    world, sim = _live(turns=1)
    sim.set_household_retail(world.turn, 0, [(0, 250, 0.0)], [])
    with pytest.raises(ValueError, match="with the food allocation"):
        sim.tick(world.turn, build_signals(world))
    assert sim.cancel_household_retail() is True
    sim.install_retail_income(world.turn + 3, [0])
    with pytest.raises(ValueError, match="retail income must be installed for this tick"):
        sim.tick(world.turn, build_signals(world))
    assert sim.cancel_retail_income() is True and sim.cancel_retail_income() is False


def test_an_owner_dead_after_phase2_keeps_the_claim_whole_for_the_heirs():
    """A claim whose owner dies before phase 0.7 (a targeted death) is neither
    offered nor eaten, though buyers with cash want food: it comes back whole
    for Python's settlement to pass on, recorded as withheld."""
    from chronicler.agent_bridge import build_region_batch, build_signals
    world, sim = _live()
    people = _snapshot(sim)
    turn, n = world.turn, len(world.regions)
    by_region = {}
    for p in people:
        by_region.setdefault(p["region"], []).append(p)
    r = max(by_region, key=lambda k: len(by_region[k]))
    dead = next(p["id"] for p in by_region[r] if p["occupation"] == 0)
    seller = next(p["id"] for p in people if p["region"] != r and p["age"] >= 20)
    assert sum(1 for p in by_region[r] if p["id"] != dead and p["wealth"] > 0.5) >= 3   # buyers with cash
    region_batch = build_region_batch(world)
    fs = region_batch.column("food_sufficiency").to_pylist()
    fs[r] = 0.7
    index = region_batch.schema.get_field_index("food_sufficiency")
    sim.set_region_state(region_batch.set_column(index, "food_sufficiency", pa.array(fs, type=pa.float32())))
    sim.set_food_allocation(turn, 0, 0.5, 0.5, [float("nan")] * n,
                            [sum(1 for p in people if p["region"] == i) for i in range(n)])
    sim.set_household_retail(turn, 0, [(r, 300, 0.0)], [(dead, r, 3000), (seller, r, 500)])
    sim.queue_targeted_deaths([dead])
    events = sim.tick(turn, build_signals(world))
    assert dead in {i for k, i in zip(events.column("event_type").to_pylist(),
                                      events.column("agent_id").to_pylist(), strict=True) if k == 0}
    _source, columns, rows, claim_rows, money, _sample, _dropped = sim.take_household_retail_frame()
    row = dict(zip(columns, rows[0], strict=True))
    claims = {(c[0], c[1]): (c[2], c[3]) for c in claim_rows}
    # The living seller's 500 sells out to the hungry; the dead owner's 3000 is untouched.
    assert claims[(seller, r)] == (0, 500)
    assert claims[(dead, r)] == (0, 0)
    assert dead not in {m[0] for m in money}
    assert (row["withheld_dead_claims"], row["withheld_dead_milli"]) == (1, 3000)
    assert "refused_dead_milli" not in columns
    # PL4-python's checks hold with the withheld claim counted as unsold.
    assert row["offered_milli"] == 3500 and row["sold_milli"] == 500 and row["own_eaten_milli"] == 0
    assert row["own_eaten_milli"] + row["sold_milli"] == row["offered_milli"] - row["unsold_milli"]
    assert row["paid_milli"] == row["credited_milli"] + row["refunded_milli"] > 0
    # The hungry with cash are short because the dead owner's food was
    # withheld: classified withheld_dead (status 3), never offer_short.
    assert row["withheld_dead_persons"] > 0 and row["offer_short_persons"] == 0
    assert row["deficit"] == pytest.approx(row["priced_out_deficit"] + row["withheld_dead_deficit"])
    assert {s[5] for s in _sample} <= {0, 1, 3} and 3 in {s[5] for s in _sample}


def test_on_a_development_world_the_fair_share_is_always_on_offer(tmp_path, monkeypatch):
    """Template development seed 7, every controlled region a pilot, 30 turns
    through the real package: in every short pilot region-turn with nothing
    withheld, the free food and the owned food on offer cover the fair share
    for everyone alive, and nobody is short for want of an offer (review D's
    B1: Phase 2 counted the owned stock before its decay)."""
    from chronicler import household_retail as HR
    from chronicler.main import _build_parser, execute_run
    frames, states = [], []
    settle = HR._settle_frame

    def spy(world, state, t, installed, frame, receipt, *rest):
        frames.append((int(world.turn), frame))
        states.append(state)
        return settle(world, state, t, installed, frame, receipt, *rest)
    monkeypatch.setattr(HR, "_settle_frame", spy)
    args = _build_parser().parse_args([
        "--seed", "7", "--turns", "30", "--civs", "4", "--regions", "8", "--agents", "hybrid", "--simulate-only",
        "--food-allocation", "--household-retail", "--household-retail-boundary", "all",
        "--output", str(tmp_path / "chronicle.md"), "--state", str(tmp_path / "state.json")])
    execute_run(args)
    assert frames and states[-1].counters.get("claims_refused", 0) == 0
    tolerance = 20 / MILLI_PER_RATION        # Python's whole-milli claims against native f32 stock
    short = 0
    for turn, (_source, columns, rows, *_rest) in frames:
        for values in rows:
            row = dict(zip(columns, values, strict=True))
            if row["sufficiency"] >= 1.0 or row["persons"] == 0 or row["withheld_dead_milli"] > 0:
                continue
            short += 1
            need = row["fair_share"] * row["persons"]
            on_offer = row["free_living"] + row["offered_milli"] / row["milli_food_per_ration"]
            assert on_offer >= need - tolerance, (turn, row["region"], on_offer, need)
            assert row["offer_short_deficit"] <= tolerance, (turn, row)
            assert row["withheld_dead_persons"] == 0
    assert short >= 10, "the run must exercise short pilot regions"
