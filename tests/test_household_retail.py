"""L6b household food retail: offline contract (no native extension).

A stand-in native implements the PL4 FFI contract
(``docs/superpowers/roadmaps/productive-recovery-phase.md`` section 2) with
simple Python rules: the economy's Phase 2 retail columns (title share,
owned stock, commons-only draw-down, decay and storage cap over both
pools), the phase 0.7 provisioning (free share, own food, purchases at the
installed price, sellers pro rata, payments with a ceiling refund), the
income replacement receipt and the wealth transfer. Its provisioning rules
are a simplification of the native ones (no households, no means test); the
real-native path is ``test_household_retail_native.py``. Every world here is
the template seed 42 with constructed people.
"""
from __future__ import annotations

import copy
import json
import math
import pickle
from collections import Counter

import numpy as np
import pyarrow as pa
import pytest

from chronicler import household_retail as HR
from chronicler import livelihoods as LV
from chronicler.economy import STORAGE_DECAY, EconomyResult, build_economy_region_input_batch
from chronicler.ffi_constants import BOND_MARRIAGE
from chronicler.grain_reserves_state import BOUGHT
from chronicler.household_retail_state import (
    COUNTERS, MAX_CLAIMS, MODES, RETAIL_GOODS, HouseholdRetailState, RetailRegion,
)
from chronicler.livelihoods import configure_livelihoods, livelihoods_snapshot_fields
from chronicler.main import _build_parser
from chronicler.world_gen import generate_world

# Template seed 42: capitals Verdant Plains (2, Thornwall), Ashara Desert (3,
# Selurian), Amber Valley (5, Kethani), Obsidian Shore (7, Ashkari); Thornwood
# (4) is Thornwall's other region, Frostholm Tundra (0) Kethani's.
FROST, VERDANT, ASHARA, THORNWOOD, AMBER, OBSIDIAN = 0, 2, 3, 4, 5, 7
MAX_WEALTH = 100.0
FARM_INCOME = 0.25
f32 = np.float32


class Column:
    def __init__(self, values):
        self.values = values

    def to_pylist(self):
        return list(self.values)


class Snapshot:
    def __init__(self, rows, names):
        self.rows, self.names = rows, names

    def column(self, name):
        return Column([r[name] for r in self.rows])


L2_COLUMNS = ["region", "scarce", "phase2_alive", "alive", "households", "rations_available",
              "relief_available", "allocated", "unallocated", "relief_to_targeted", "shortfall",
              "below_floor", "fully_fed", "people_poorer_half", "shortfall_poorer_half",
              "people_richer_half", "shortfall_richer_half", "children", "shortfall_children"]


def _split(total, weights):
    """The stand-in's own largest remainder (ties to the smaller key)."""
    items = [(k, w) for k, w in sorted(weights.items()) if w > 0]
    whole = sum(w for _, w in items)
    if not total or not whole:
        return {}
    out, order = {}, []
    for k, w in items:
        q, r = divmod(total * w, whole)
        out[k] = q
        order.append((-r, k))
    for _, k in sorted(order)[:total - sum(out.values())]:
        out[k] += 1
    return {k: v for k, v in out.items() if v}


class FakeSim:
    """People, spouses, L2's install, and the retail contract's methods."""

    def __init__(self):
        self.people: dict[int, dict] = {}
        self.spouse: dict[int, int] = {}
        self.calls: list = []
        self.pending_l2 = self.l2_frame = None
        self.pending_retail = self.retail_frame = None
        self.pending_income = self.income_receipt = None
        self.keys: set = set()
        self.die_before: set[int] = set()
        self.die_after: set[int] = set()
        self.moves: dict[int, int] = {}
        self.skip_retail = False

    def add(self, aid, region, *, occupation=0, age=30, wealth=5.0, settlement=0, parents=(0, 0)):
        self.people[aid] = {"id": aid, "region": region, "origin_region": region, "occupation": occupation,
                            "age": age, "settlement_id": settlement, "parent_id_0": parents[0],
                            "parent_id_1": parents[1], "wealth": wealth, "displacement_turn": 0}

    def marry(self, a, b):
        self.spouse[a], self.spouse[b] = b, a

    def kill(self, aid):
        self.people.pop(aid, None)

    # --- reads ---------------------------------------------------------------
    def get_snapshot(self):
        names = ["id", "region", "origin_region", "occupation", "age", "settlement_id",
                 "parent_id_0", "parent_id_1", "wealth", "displacement_turn"]
        return Snapshot([dict(self.people[i]) for i in sorted(self.people)], names)

    def get_agent_relationships(self, aid):
        self.calls.append(("get_agent_relationships", aid))
        if aid not in self.people:
            return None
        s = self.spouse.get(aid)
        return [(s, 60, BOND_MARRIAGE, 0)] if s is not None and s in self.people else []

    # --- L2 ------------------------------------------------------------------
    def set_food_allocation(self, turn, regime, floor, share, pre, counts):
        self.calls.append(("set_food_allocation", turn))
        assert self.pending_l2 is None
        self.pending_l2 = (turn, regime, list(pre), list(counts))

    def cancel_food_allocation(self):
        had, self.pending_l2 = self.pending_l2 is not None, None
        return had

    def take_food_allocation_frame(self):
        frame, self.l2_frame = self.l2_frame, None
        return frame

    # --- retail (the FFI contract) ------------------------------------------
    def set_household_retail(self, source_turn, mode, regions, claims):
        self.calls.append(("set_household_retail", source_turn, mode, list(regions), list(claims)))
        if self.pending_retail is not None:
            raise ValueError("a household retail install is pending")
        if mode not in (0, 1, 2) or len({r[0] for r in regions}) != len(regions):
            raise ValueError("invalid retail regions")
        if len({(o, r) for o, r, _ in claims}) != len(claims) or any(m < 0 for _, _, m in claims):
            raise ValueError("invalid retail claims")
        if any(price < 0 or not math.isfinite(free) or free < 0 for _, price, free in regions):
            raise ValueError("invalid retail region row")
        self.pending_retail = (source_turn, mode, list(regions), list(claims))

    def cancel_household_retail(self):
        self.calls.append(("cancel_household_retail",))
        had, self.pending_retail = self.pending_retail is not None, None
        return had

    def take_household_retail_frame(self):
        self.calls.append(("take_household_retail_frame",))
        frame, self.retail_frame = self.retail_frame, None
        return frame

    def install_retail_income(self, turn, regions):
        self.calls.append(("install_retail_income", turn, list(regions)))
        if self.pending_income is not None:
            raise ValueError("a retail income install is pending")
        self.pending_income = (turn, set(regions))

    def cancel_retail_income(self):
        self.calls.append(("cancel_retail_income",))
        had, self.pending_income = self.pending_income is not None, None
        return had

    def take_retail_income_receipt(self):
        self.calls.append(("take_retail_income_receipt",))
        receipt, self.income_receipt = self.income_receipt, None
        return receipt

    def transfer_wealth(self, turn, purpose, batch, rows):
        self.calls.append(("transfer_wealth", turn, purpose, batch, list(rows)))
        if any(p == purpose and b == batch and t >= turn for t, p, b in self.keys):
            raise ValueError("wealth transfer already applied for this turn, purpose and batch")
        assert len({r[0] for r in rows}) == len(rows)
        self.keys.add((turn, purpose, batch))
        out = []
        for aid, amount in rows:
            p = self.people.get(aid)
            if p is None:
                out.append((aid, amount, 0, amount, 2))
                continue
            applied = min(amount, math.floor((MAX_WEALTH - p["wealth"]) * 1000))
            p["wealth"] += applied / 1000
            out.append((aid, amount, applied, amount - applied, 0 if applied == amount else 1))
        return out

    # --- the tick ------------------------------------------------------------
    def tick(self, world, **_kwargs):
        turn = world.turn
        income, self.pending_income = self.pending_income, None
        replaced = []
        for aid in sorted(self.people):
            p = self.people[aid]
            if p["occupation"] != 0:
                continue
            if income is not None and income[0] == turn and p["region"] in income[1]:
                replaced.append((aid, float(f32(FARM_INCOME))))
                continue
            p["wealth"] = min(MAX_WEALTH, p["wealth"] + FARM_INCOME)
        if income is not None:
            self.income_receipt = (turn, replaced)
        for aid in sorted(self.die_before):
            self.kill(aid)
        l2, self.pending_l2 = self.pending_l2, None
        retail, self.pending_retail = self.pending_retail, None
        if self.skip_retail:
            # A tick that never takes the retail installs.
            self.pending_retail, self.pending_income, self.income_receipt = retail, income, None
            retail = None
        pilots = {r[0] for r in retail[2]} if retail is not None else set()
        if l2 is not None:
            self.l2_frame = self._l2(turn, l2, pilots)
        if retail is not None:
            self.retail_frame = self._retail(retail)
        for aid in sorted(self.die_after):
            self.kill(aid)
        for aid, to in sorted(self.moves.items()):
            self.people[aid]["region"] = to
        self.die_before, self.die_after, self.moves = set(), set(), {}
        return []

    def _l2(self, turn, install, pilots):
        _turn, regime, pre, counts = install
        alive = Counter(p["region"] for p in self.people.values())
        rows = []
        for rid, (s, n2) in enumerate(zip(pre, counts)):
            n = alive[rid]
            available = (0.0 if math.isnan(s) else s) * n2
            allocated = min(available, float(n), (0.0 if math.isnan(s) else s) * n)
            row = dict.fromkeys(L2_COLUMNS, 0.0)
            row.update(region=rid, scarce=1.0 if s < 1 else 0.0, phase2_alive=n2, alive=n, households=n,
                       rations_available=available, allocated=allocated, unallocated=available - allocated)
            if rid in pilots:
                # Retail took this region over: an L2 row that would not close.
                row.update(scarce=1.0, allocated=0.0, unallocated=0.0, rations_available=7.0)
            rows.append([row[c] for c in L2_COLUMNS])
        return (turn, regime, L2_COLUMNS, rows, [], 0)

    def _retail(self, install):
        turn, mode, regions, claims = install
        remaining = {(o, r): m for o, r, m in claims}
        used = {key: [0, 0] for key in remaining}
        money: dict[int, list[int]] = {}
        rows, sample = [], []
        for rid, price, free in regions:
            persons = sorted(a for a, p in self.people.items() if p["region"] == rid)
            n = len(persons)
            share = min(1.0, free / n) if n else 0.0
            ration = {a: share for a in persons}
            status = dict.fromkeys(persons, 0)
            offered = sum(m for (o, r), m in remaining.items() if r == rid)
            own = sold = paid_r = credited_r = refunded_r = 0
            for a in persons:                                  # own food first
                key = (a, rid)
                if remaining.get(key, 0) > 0:
                    eat = min(math.floor((1 - ration[a]) * 500 + 1e-9), remaining[key])
                    remaining[key] -= eat
                    used[key][0] += eat
                    ration[a] += eat / 500
                    own += eat
            for a in persons:                                  # then purchases
                want = math.floor((1 - ration[a]) * 500 + 1e-9)
                if want <= 0:
                    continue
                # A dead owner's claim is withheld whole (native contract), never sold.
                offer = {o: m for (o, r), m in remaining.items()
                         if r == rid and m > 0 and o != a and o in self.people}
                avail = sum(offer.values())
                wealth = math.floor(self.people[a]["wealth"] * 1000)
                afford = want if price == 0 else wealth * 500 // price
                buy = min(want, afford, avail)
                if buy < want:
                    status[a] = 1 if afford < min(want, avail) else 2
                if buy <= 0:
                    continue
                split = _split(buy, offer)
                cost = buy * price // 500
                for o, v in split.items():
                    remaining[(o, rid)] -= v
                    used[(o, rid)][1] += v
                self.people[a]["wealth"] -= cost / 1000
                money.setdefault(a, [0, 0, 0])[0] += cost
                for o, c in _split(cost, split).items():
                    seller = self.people.get(o)
                    credit = min(c, math.floor((MAX_WEALTH - seller["wealth"]) * 1000)) if seller else 0
                    if seller:
                        seller["wealth"] += credit / 1000
                    self.people[a]["wealth"] += (c - credit) / 1000
                    money.setdefault(o, [0, 0, 0])[1] += credit
                    money[a][2] += c - credit
                    credited_r += credit
                    refunded_r += c - credit
                paid_r += cost
                ration[a] += buy / 500
                sold += buy
            row = {"region": rid, "price_milli": price, "free_rations": free, "free_given": share * n,
                   "free_unallocated": free - share * n, "offered_milli": offered, "own_eaten_milli": own,
                   "sold_milli": sold, "unsold_milli": offered - own - sold, "paid_milli": paid_r,
                   "credited_milli": credited_r, "refunded_milli": refunded_r,
                   "rations": sum(ration.values()), "persons": n,
                   "priced_out_persons": sum(1 for s in status.values() if s == 1),
                   "offer_short_persons": sum(1 for s in status.values() if s == 2)}
            rows.append([float(row[c]) for c in HR.FRAME_COLUMNS])
            sample.extend((a, rid, a, float(f32(ration[a])), float(f32(share)), status[a]) for a in persons)
        claim_rows = [(o, r, e, s) for (o, r), (e, s) in sorted(used.items(), key=lambda kv: (kv[0][1], kv[0][0]))
                      if e or s]
        money_rows = [(a, *v) for a, v in sorted(money.items()) if any(v)]
        return (turn, list(HR.FRAME_COLUMNS), rows, claim_rows, money_rows, sample, 0)


class FakeBridge:
    def __init__(self, sim):
        self._sim = sim


class Harness:
    """One constructed world, run through the real livelihoods hooks."""

    def __init__(self, *flags, l2=True, retail=True):
        self.world = generate_world(seed=42)
        self.world.agent_mode = "hybrid"
        self.world.turn = 10
        for region in self.world.regions:
            region.stockpile.goods = {}
        argv = (["--food-allocation", "--food-allocation-regime", "equal"] if l2 else []) + \
               (["--household-retail", *flags] if retail else [])
        configure_livelihoods(self.world, _build_parser().parse_args(argv), agent_mode="hybrid")
        self.sim = FakeSim()
        self.bridge = FakeBridge(self.sim)
        self.region_inputs = []
        self.results = []

    @property
    def state(self) -> HouseholdRetailState:
        return self.world.livelihoods.household_retail

    def economy(self, region_input, production, imports=None):
        """Native Phase 2 under the contract: owned in availability and price,
        commons-only draw-down, decay and the storage cap on both pools."""
        world = self.world
        cols = {n: region_input.column(n).to_pylist() for n in region_input.schema.names}
        retail = "retail_title_share" in cols
        alive = Counter(p["region"] for p in self.sim.people.values())
        res = EconomyResult()
        for rid, region in enumerate(world.regions):
            prod = [float((production or {}).get(rid, {}).get(g, 0.0)) for g in RETAIL_GOODS]
            imp = [float((imports or {}).get(rid, {}).get(g, 0.0)) for g in RETAIL_GOODS]
            commons = [float(cols[f"stockpile_{g}"][rid]) for g in RETAIL_GOODS]
            theta = cols["retail_title_share"][rid] if retail else None
            owned = [float(cols[f"retail_owned_{g}"][rid]) for g in RETAIL_GOODS] if retail else [0.0] * 5
            titled = [float(f32(theta * p)) if theta is not None else 0.0 for p in prod]
            owned = [o + t for o, t in zip(owned, titled)]
            commons = [c + p - t + i for c, p, t, i in zip(commons, prod, titled, imp)]
            demand = 0.5 * alive[rid]
            total = sum(commons) + sum(owned)
            ctotal = sum(commons)
            draw = min(ctotal, demand)
            commons = [c - draw * c / ctotal for c in commons] if ctotal > 0 else commons
            rates = [STORAGE_DECAY[g] for g in RETAIL_GOODS]
            cdec = [c * r for c, r in zip(commons, rates)]
            odec = [float(f32(o * r)) for o, r in zip(owned, rates)]
            commons = [c - d for c, d in zip(commons, cdec)]
            owned = [o - d for o, d in zip(owned, odec)]
            cap = 2.5 * region.population
            oover = []
            for g in range(5):
                both = commons[g] + owned[g]
                over = max(0.0, both - cap)
                share_o = over * owned[g] / both if both > 0 else 0.0
                commons[g] -= over - share_o
                oover.append(float(f32(share_o)))
                owned[g] -= share_o
            for g, name in enumerate(RETAIL_GOODS):
                if commons[g] or name in region.stockpile.goods:
                    region.stockpile.goods[name] = float(f32(max(0.0, commons[g])))
            name = region.name
            res.food_sufficiency[name] = float(f32(1.0 if demand <= 0 else min(2.0, total / demand)))
            res.market_demand[name] = (demand, 0.0, 0.0, 0.0)
            res.market_supply[name] = (total, 0.0, 0.0, 0.0)
            res.market_prices[name] = {"food": float(f32(demand / max(total, 0.1)))}
            res.slot_output[name] = (prod[0], 0.0, 0.0)
            res.forage_output[name] = 0.0
            if region.resource_types[0] != 0:                  # grain grown in slot 0 or foraged
                res.slot_output[name] = (0.0, 0.0, 0.0)
                res.forage_output[name] = prod[0]
            if retail:
                row = {}
                for g, good in enumerate(RETAIL_GOODS):
                    row[f"retail_titled_{good}"] = titled[g]
                    row[f"retail_owned_close_{good}"] = float(f32(owned[g]))
                    row[f"retail_owned_decay_{good}"] = odec[g]
                    row[f"retail_owned_overflow_{good}"] = oover[g]
                row["commons_consumed"] = float(f32(draw))
                row["commons_sufficiency"] = float(f32(1.0 if demand <= 0 else min(2.0, ctotal / demand)))
                res.household_retail[rid] = row
        return res

    def turn(self, production=None, *, imports=None, between=None, granaries=None):
        world, bridge = self.world, self.bridge
        snapshot = self.sim.get_snapshot()
        region_input = build_economy_region_input_batch(world)
        region_input = LV.prepare_phase2(world, region_input, bridge, snapshot)
        self.region_inputs.append(region_input)
        res = self.economy(region_input, production, imports)
        self.results.append(res)
        LV.finish_phase2(world, res, bridge)
        from chronicler.grain_reserves import grain_reserves_active, open_granaries
        if grain_reserves_active(world):
            open_granaries(world, res, bridge)          # public release, as Phase 2 does
        if between is not None:
            between()
        tick = LV.wrap_agent_tick(world, bridge, self.sim.tick, res)
        tick(world)
        LV.phase10_before_reserves(world, economy_result=res, agent_bridge=bridge)
        if granaries is not None:
            granaries(res)
        LV.phase10(world, economy_result=res, agent_bridge=bridge)
        world.turn += 1
        return res

    def summary(self):
        return livelihoods_snapshot_fields(self.world)["livelihoods"]["household_retail"]

    def frame(self, rid):
        return next(f for f in self.state.frame if f.region == rid)


def _people(h, rid, ids, **kw):
    for aid in ids:
        h.sim.add(aid, rid, **kw)


def _calls(sim, *names):
    return [c for c in sim.calls if c[0] in names]


def _claims_total(state):
    return sum(sum(r.claims.values()) for r in state.regions)


# --- registry, switch and feature off ------------------------------------------

def test_switch_registry_cli_and_prerequisites():
    from chronicler.batch_manifest import SIMULATION_ARG_KEYS, simulation_config
    from chronicler.feature_catalog import REQUIREMENTS
    from chronicler.livelihoods_state import LIVELIHOODS_SWITCHES
    assert LIVELIHOODS_SWITCHES[-1] == "household_retail"
    assert LIVELIHOODS_SWITCHES.index("food_allocation") < LIVELIHOODS_SWITCHES.index("household_retail")
    assert LV.LIVELIHOODS_ARG_KEYS[-3:] == ("household_retail", "household_retail_mode", "household_retail_boundary")
    assert LV.LIVELIHOODS_CHOICES["household_retail_mode"] == MODES
    assert LV.LIVELIHOODS_CHOICES["household_retail_boundary"] == ("market", "paid_work", "all")
    assert {"household_retail", "household_retail_mode", "household_retail_boundary"} <= set(SIMULATION_ARG_KEYS)
    assert REQUIREMENTS["household_retail"] == ({"agents": ["hybrid"]}, {"feature": "food_allocation"})
    parse = _build_parser().parse_args
    default = parse([])
    assert not {"household_retail", "household_retail_mode", "household_retail_boundary"} & set(simulation_config(default))
    args = parse(["--household-retail", "--household-retail-mode", "no_relief", "--household-retail-boundary", "all"])
    assert LV.livelihoods_arguments(args)[-3:] == ["--household-retail", "--household-retail-mode=no_relief",
                                                   "--household-retail-boundary=all"]
    world = generate_world(seed=42)
    with pytest.raises(ValueError, match="food-allocation"):
        configure_livelihoods(world, parse(["--household-retail"]), agent_mode="hybrid")
    with pytest.raises(ValueError, match="hybrid"):
        configure_livelihoods(world, parse(["--household-retail", "--food-allocation"]), agent_mode="shadow")
    assert world.livelihoods is None
    configure_livelihoods(world, parse(["--food-allocation", "--household-retail", "--household-retail-boundary",
                                        "paid_work"]), agent_mode="hybrid")
    state = world.livelihoods.household_retail
    assert (state.enabled, state.mode, state.boundary) == (True, "retail", "paid_work")
    # A saved switch keeps its options unless given (a mode without its
    # switch is ignored, the recorded limit); a conflicting resume is named.
    configure_livelihoods(world, parse(["--household-retail-mode", "free_exchange"]), agent_mode="hybrid")
    assert (state.mode, state.boundary) == ("retail", "paid_work")
    configure_livelihoods(world, parse(["--household-retail", "--household-retail-mode", "free_exchange"]),
                          agent_mode="hybrid")
    assert (state.mode, state.boundary) == ("free_exchange", "paid_work")
    conflicts = LV.livelihoods_resume_conflicts(world, parse(["--household-retail-boundary", "all"]), {})
    assert conflicts == ["--household-retail-boundary 'all' conflicts with the checkpoint (saved: 'paid_work')"]
    assert LV.livelihoods_feature_flags(world)["household_retail"] is False   # world.agent_mode is None


def test_feature_off_has_no_state_no_columns_and_no_snapshot_key():
    h = Harness(retail=False)
    _people(h, VERDANT, range(1, 5))
    h.turn({VERDANT: {"grain": 4.0}})
    assert h.world.livelihoods.household_retail is None
    assert "household_retail" not in json.loads(h.world.model_dump_json())["livelihoods"]
    assert not [n for n in h.region_inputs[0].schema.names if n.startswith("retail_")]
    assert "household_retail" not in livelihoods_snapshot_fields(h.world)["livelihoods"]
    assert not _calls(h.sim, *HR.NATIVE_METHODS, "transfer_wealth")


# --- title ------------------------------------------------------------------------

def test_largest_remainder_ties_go_to_the_smaller_id_and_debits_stay_within_claims():
    assert HR.largest_remainder(10, [(5, 1), (3, 1), (9, 1)]) == {3: 4, 5: 3, 9: 3}
    assert HR.largest_remainder(7, [(1, 2), (2, 1)]) == {1: 5, 2: 2}
    assert HR.largest_remainder(0, [(1, 1)]) == {} and HR.largest_remainder(5, [(1, 0)]) == {}
    claims = {4: 1, 7: 999, 11: 3}
    for total in range(0, 1004):
        split = HR._pro_rata(total, claims)
        assert sum(split.values()) == total and all(split.get(k, 0) <= v for k, v in claims.items())
    with pytest.raises(HR.RetailAccountingError):
        HR._pro_rata(1004, claims)
    assert HR._draw([10, 0, 5, 0, 0], 7) == [5, 0, 2, 0, 0]


def test_title_by_food_work_weights_and_largest_remainder():
    from chronicler.cities_state import City, CityState
    h = Harness()
    h.world.cities = CityState(cities=[City(settlement_id=9, region=VERDANT, name="Verd", rank=1, founded_turn=0,
                                            founder=2)])
    _people(h, VERDANT, (1, 2, 3))                        # rural farmers
    h.sim.add(4, VERDANT, settlement=9)                    # a town farmer: u = 0.8
    h.sim.add(5, VERDANT, occupation=1)                    # a soldier: no title
    h.sim.add(6, VERDANT, age=8)                           # a child farmer holds his own title
    # A health plan: 2 impaired (eligible patient), 3 his carer.
    from types import SimpleNamespace
    h.world.health_care = SimpleNamespace(_prepared=[(2, VERDANT, 3, 0.25)], impairment=0.5)
    import chronicler.health_care as health
    original = health.health_care_active
    health.health_care_active = lambda world: True
    try:
        weights = HR.title_weights(h.world, h.sim.get_snapshot(), [VERDANT])
    finally:
        health.health_care_active = original
    assert weights == {VERDANT: [(1, 1_000_000), (2, 500_000), (3, 750_000), (4, 800_000), (6, 1_000_000)]}
    h.world.health_care = None
    # Salt does not decay, so the claims right after Phase 2 are the title itself:
    # 0.9 x 10.0 = 9000 milli over weights 1, 1, 1, 0.8, 1 (ties to the smaller id),
    # and 0.9 x 0.7 = 630 milli of fish after its decay, pro rata.
    seen = {}
    res = h.turn({VERDANT: {"salt": 10.0}}, between=lambda: seen.update(h.state.region(VERDANT).claims))
    assert res.household_retail[VERDANT]["retail_titled_salt"] == float(f32(9.0))
    assert seen == HR.largest_remainder(9000, [(1, 10), (2, 10), (3, 10), (4, 8), (6, 10)])
    assert seen == {1: 1875, 2: 1875, 3: 1875, 4: 1500, 6: 1875}
    assert h.frame(VERDANT).flows["titled"] == 9000 and h.state.counters["titled_milli"] == 9000
    assert 5 not in seen and 6 in seen                     # the soldier owns nothing; the child his share
    seen.clear()
    h2 = Harness()
    for aid in (3, 1, 2):
        h2.sim.add(aid, VERDANT)
    h2.turn({VERDANT: {"salt": 0.001}}, between=lambda: seen.update(h2.state.region(VERDANT).claims))
    assert seen == {1: 1}                                  # 0.9 milli rounds to 1; the tie goes to id 1


def test_opening_stock_and_imports_stay_commons_and_only_new_harvest_is_titled():
    h = Harness()
    h.world.regions[VERDANT].stockpile.goods = {"grain": 25.0}
    _people(h, VERDANT, (1, 2))
    h.turn({VERDANT: {"grain": 2.0}}, imports={VERDANT: {"grain": 3.0, "fish": 1.0}})
    first = h.region_inputs[0]
    assert first.column("retail_owned_grain").to_pylist()[VERDANT] == 0.0        # nothing owned at opening
    assert first.column("stockpile_grain").to_pylist()[VERDANT] == 25.0           # the opening stock is commons
    assert first.column("retail_title_share").to_pylist()[VERDANT] == pytest.approx(0.9)
    assert first.column("retail_title_share").to_pylist()[THORNWOOD] is None      # not a pilot region
    frame = h.frame(VERDANT)
    assert frame.flows["titled"] == 1800                                         # 0.9 x 2 grain; imports untitled
    assert h.state.region(VERDANT).reason == "capital"
    assert [r.region for r in h.state.regions] == [VERDANT, ASHARA, AMBER, OBSIDIAN]


def test_claims_close_per_owner_and_region_over_turns_and_refuse_corruption():
    h = Harness()
    _people(h, VERDANT, (1, 2, 3), wealth=20.0)
    _people(h, VERDANT, (10, 11), occupation=2, wealth=20.0)          # non-farm buyers
    for _ in range(4):
        h.turn({VERDANT: {"grain": 3.0, "salt": 0.5}})
        reg = h.state.region(VERDANT)
        frame = h.frame(VERDANT)
        signed = sum(HR.FLOW_SIGNS[k] * v for k, v in frame.flows.items())
        assert frame.open_milli + signed == frame.close_milli == sum(reg.goods) == sum(reg.claims.values())
        native = frame.provisioning
        assert native["own_eaten_milli"] + native["sold_milli"] == native["offered_milli"] - native["unsold_milli"]
    money = h.state.money
    assert money["paid_milli"] == money["credited_milli"] + money["refunded_milli"] > 0
    assert h.state.counters["sold_milli"] > 0 and h.state.counters["own_eaten_milli"] > 0
    # Every flow kind moved claims and goods together; a corrupted book raises.
    book = HR._Book(entry=reg, open_goods=list(reg.goods), open_claims=dict(reg.claims))
    HR.check_region(reg, book)
    HR.check_owner(reg, book)
    reg.claims[1] = reg.claims.get(1, 0) + 1
    with pytest.raises(HR.RetailAccountingError):
        HR.check_region(reg, book)
    with pytest.raises(HR.RetailAccountingError):
        HR.check_owner(reg, book)


# --- provisioning, payments and income --------------------------------------------

def test_installs_carry_prices_free_rations_and_claims_and_settle_exactly_once():
    h = Harness()
    _people(h, VERDANT, (1, 2), wealth=10.0)
    h.sim.add(3, VERDANT, occupation=2, wealth=10.0)
    h.turn({VERDANT: {"grain": 3.0}})
    h.turn({VERDANT: {"grain": 3.0}})
    (_, turn, mode, regions, claims) = _calls(h.sim, "set_household_retail")[-1]
    res = h.results[-1]
    row = next(r for r in regions if r[0] == VERDANT)
    p = res.market_prices["Verdant Plains"]["food"]
    assert row[1] == math.floor(min(3.0, max(0.5, p)) * 0.5 * 1000)
    assert row[2] == pytest.approx(res.household_retail[VERDANT]["commons_consumed"] / 0.5)
    assert mode == 0 and turn == 11 and all(r == VERDANT for _, r, _ in claims if r == VERDANT)
    assert _calls(h.sim, "install_retail_income")[-1][2] == [VERDANT, ASHARA, AMBER, OBSIDIAN]
    assert h.state.income["rows"] == 2 and h.state.income["replaced"] == pytest.approx(0.5)
    assert h.state.last_settled_turn == 11 and h.state.counters["turns_settled"] == 2


def test_l2_seam_leaves_pilot_regions_to_retail():
    # The stand-in L2 row of a pilot region does not close; L2 must not check it.
    h = Harness()
    _people(h, VERDANT, (1, 2))
    _people(h, THORNWOOD, (5, 6))
    h.turn({VERDANT: {"grain": 0.2}})
    l2 = h.world.livelihoods.food_allocation
    assert VERDANT not in {r["region"] for r in l2.regions}
    assert HR.provisioned_regions(h.world) == set()          # nothing after the tick


@pytest.mark.parametrize("change", ["turn", "repeat_settle", "repeat_title", "partial"])
def test_stale_repeated_and_wrong_turn_receipts_are_refused(change):
    h = Harness()
    _people(h, VERDANT, (1, 2))
    h.turn({VERDANT: {"grain": 3.0}})
    if change == "turn":
        original = h.sim._retail

        def stale(install):
            frame = original(install)
            return (frame[0] - 1, *frame[1:])
        h.sim._retail = stale
        with pytest.raises(RuntimeError, match="another turn"):
            h.turn({VERDANT: {"grain": 3.0}})
    elif change == "repeat_settle":
        h.state.last_settled_turn = h.world.turn
        with pytest.raises(RuntimeError, match="already settled"):
            h.turn({VERDANT: {"grain": 3.0}})
    elif change == "repeat_title":
        snapshot = h.sim.get_snapshot()
        batch = LV.prepare_phase2(h.world, build_economy_region_input_batch(h.world), h.bridge, snapshot)
        res = h.economy(batch, {VERDANT: {"grain": 3.0}})
        LV.finish_phase2(h.world, res, h.bridge)
        with pytest.raises(RuntimeError, match="already titled"):
            LV.finish_phase2(h.world, res, h.bridge)
    else:
        h.sim.take_retail_income_receipt = lambda: None
        with pytest.raises(RuntimeError, match="taken together"):
            h.turn({VERDANT: {"grain": 3.0}})


def test_a_frame_that_does_not_close_is_refused():
    h = Harness()
    _people(h, VERDANT, (1, 2), wealth=10.0)
    h.sim.add(3, VERDANT, occupation=2, wealth=10.0)
    h.turn({VERDANT: {"grain": 3.0}})
    original = h.sim._retail

    def broken(install):
        frame = list(original(install))
        frame[2] = [list(row) for row in frame[2]]
        frame[2][0][HR.FRAME_COLUMNS.index("unsold_milli")] += 1
        return tuple(frame)
    h.sim._retail = broken
    with pytest.raises(HR.RetailAccountingError, match="offered - unsold"):
        h.turn({VERDANT: {"grain": 3.0}})


def test_an_untaken_install_is_cancelled_and_a_failed_tick_rolls_back():
    h = Harness()
    _people(h, VERDANT, (1, 2))
    h.sim.skip_retail = True
    h.turn({VERDANT: {"grain": 3.0}})
    assert h.state.counters["turns_not_taken"] == 1
    assert h.sim.pending_retail is None and h.sim.pending_income is None
    h.sim.skip_retail = False

    def explode(world, **kw):
        raise RuntimeError("tick failed")
    h.sim.tick = explode
    with pytest.raises(RuntimeError, match="tick failed"):
        h.turn({VERDANT: {"grain": 3.0}})
    assert ("cancel_household_retail",) in h.sim.calls and ("cancel_retail_income",) in h.sim.calls
    assert h.sim.pending_retail is None and h.sim.pending_income is None


# --- lifecycles ---------------------------------------------------------------------

def _owners(h, rid):
    return dict(h.state.region(rid).claims)


def test_death_passes_the_claim_to_the_spouse_then_children_then_commons():
    h = Harness()
    _people(h, VERDANT, (1, 2, 3, 4), wealth=0.0)
    h.sim.add(20, VERDANT, occupation=2, age=40, wealth=0.0)            # spouse of 1 (not a farmer)
    h.sim.marry(1, 20)
    h.sim.add(30, VERDANT, occupation=2, age=10, parents=(2, 0))         # 2's children: 30 here,
    h.sim.add(31, VERDANT, occupation=2, age=12, parents=(0, 2))         # 31 here,
    h.sim.add(32, THORNWOOD, occupation=2, age=12, parents=(2, 0))       # 32 elsewhere (not an heir)
    h.turn({VERDANT: {"grain": 20.0}})
    before = _owners(h, VERDANT)
    commons_before = h.world.regions[VERDANT].stockpile.goods.get("grain", 0.0)
    h.sim.die_after = {1, 2, 3}
    h.turn()
    after = _owners(h, VERDANT)
    assert 1 not in after and 2 not in after and 3 not in after
    reg_frame = h.frame(VERDANT)
    log = [r for r in h.state.log if r.kind in ("inherited", "escheat")]
    spouse = [r for r in log if r.owner == 1]
    assert [(r.other, r.note) for r in spouse] == [(20, "spouse")]
    assert after[20] == spouse[0].milli > 0 and 20 not in before          # the whole claim, after the tick
    kids = [r for r in log if r.owner == 2]
    assert sorted(r.other for r in kids) == [30, 31] and abs(kids[0].milli - kids[1].milli) <= 1
    assert kids[0].other == 30 and kids[0].milli >= kids[1].milli         # the extra milli to the smaller id
    (escheat,) = [r for r in log if r.owner == 3]
    assert escheat.kind == "escheat" and escheat.milli > 0
    assert reg_frame.commons["escheat"] == escheat.milli
    assert h.world.regions[VERDANT].stockpile.goods["grain"] > commons_before
    assert reg_frame.flows["inherited_in"] == reg_frame.flows["inherited_out"]
    assert sum(after.values()) == sum(h.state.region(VERDANT).goods)


def test_an_owner_dead_before_provisioning_keeps_the_claim_whole_for_the_heir():
    h = Harness()
    _people(h, VERDANT, (1, 2), wealth=0.0)
    h.sim.add(5, VERDANT, occupation=2, wealth=30.0)
    h.sim.marry(1, 5)
    h.turn({VERDANT: {"grain": 4.0}})
    h.sim.die_before = {1}
    h.turn()
    # The claim installed for the tick is neither sold (the spouse could pay)
    # nor eaten: the spouse inherits all of it.
    installed = {(o, r): m for o, r, m in _calls(h.sim, "set_household_retail")[-1][4]}
    log = [r for r in h.state.log if r.kind == "inherited" and r.owner == 1]
    assert log and log[0].other == 5 and log[0].milli == installed[(1, VERDANT)] > 0
    assert _owners(h, VERDANT)[5] == installed[(1, VERDANT)]
    assert 1 not in _owners(h, VERDANT)


def test_migration_keeps_the_claim_in_the_origin_and_split_or_rejoin_create_nothing():
    h = Harness()
    _people(h, VERDANT, (1, 2), wealth=0.0)
    _people(h, THORNWOOD, (7,), occupation=2, wealth=0.0)
    h.turn({VERDANT: {"grain": 4.0}})
    h.sim.moves = {1: THORNWOOD}
    h.turn()
    assert h.sim.people[1]["region"] == THORNWOOD and 1 in _owners(h, VERDANT)
    assert THORNWOOD not in [r.region for r in h.state.regions]
    # Absent, the migrant cannot eat it, only sell it (nobody here can pay):
    # the claim installed in the origin comes back untouched.
    h.turn()
    installed = {(o, r): m for o, r, m in _calls(h.sim, "set_household_retail")[-1][4]}
    assert installed[(1, VERDANT)] == _owners(h, VERDANT)[1] > 0
    # Marriage and its end merge and split households: claims stay personal and
    # every turn's books close per owner (nothing is created or lost).
    for change in (lambda: h.sim.marry(1, 2), h.sim.spouse.clear):
        change()
        before = _claims_total(h.state)
        h.turn()
        frame = h.frame(VERDANT)
        assert frame.open_milli == before and "titled" not in frame.flows
        assert frame.close_milli == _claims_total(h.state) == before - sum(
            v for k, v in frame.flows.items() if k in ("own_eaten", "sold", "decay", "overflow"))


def test_conquest_destroys_the_conquest_share_of_owned_stock():
    h = Harness()
    _people(h, VERDANT, (1, 2), wealth=0.0)
    h.turn({VERDANT: {"grain": 8.0}})
    goods = []

    def conquer():
        goods.extend(h.state.region(VERDANT).goods)          # after this turn's decay
        h.world.regions[VERDANT].controller = "Kethani Empire"
    h.turn(between=conquer)
    frame = h.frame(VERDANT)
    expect = sum(v - math.floor(v * 0.5) for v in goods)
    assert frame.flows["war_loss"] == expect
    assert [r for r in h.state.log if r.kind == "war_loss"][0].note == "Thornwall Confederacy -> Kethani Empire"
    assert VERDANT in [r.region for r in h.state.regions]                      # sticky


def test_pilot_closure_returns_holdings_to_the_commons_before_the_economy_reads_them():
    h = Harness()
    _people(h, VERDANT, (1, 2), wealth=0.0)
    h.turn({VERDANT: {"grain": 8.0}})
    owned = list(h.state.region(VERDANT).goods)
    commons = h.world.regions[VERDANT].stockpile.goods.get("grain", 0.0)
    h.world.regions[VERDANT].controller = None
    h.turn()
    assert VERDANT not in [r.region for r in h.state.regions]
    batch = h.region_inputs[-1]
    assert batch.column("stockpile_grain").to_pylist()[VERDANT] == pytest.approx(commons + owned[0] / 1000, abs=1e-4)
    frame = h.frame(VERDANT)
    assert frame.commons["pilot_closed"] == sum(owned) and frame.close_milli == 0
    assert [r.kind for r in h.state.log][-1] == "pilot_closed"


def test_pool_reset_closes_every_claim_to_the_commons_dated():
    h = Harness()
    _people(h, VERDANT, (1, 2), wealth=0.0)
    h.turn({VERDANT: {"grain": 8.0}})
    owned = sum(h.state.region(VERDANT).goods)
    h.world.livelihoods._pool_sim = None          # the next hook binds a rebuilt pool
    h.sim = FakeSim()
    _people(h, VERDANT, (1, 2), wealth=0.0)
    h.bridge = FakeBridge(h.sim)
    h.turn()
    assert all(not r.claims for r in h.state.regions)
    assert h.frame(VERDANT).commons["pool_reset"] == owned
    rec = [r for r in h.state.log if r.kind == "pool_reset" and r.region == VERDANT][0]
    assert rec.turn == 11 and rec.milli == owned and h.state.counters["pool_resets"] == 1
    assert h.region_inputs[-1].column("stockpile_grain").to_pylist()[VERDANT] > 0


def test_the_claims_cap_refuses_new_owners_and_their_share_stays_commons(monkeypatch):
    monkeypatch.setattr(HR, "MAX_CLAIMS", 2)
    h = Harness()
    _people(h, VERDANT, (1, 2, 3), wealth=0.0)
    h.turn({VERDANT: {"grain": 3.0}})
    assert set(_owners(h, VERDANT)) <= {1, 2}
    frame = h.frame(VERDANT)
    assert frame.commons["claims_refused"] > 0 and h.state.counters["claims_refused"] == 1


# --- procurement -------------------------------------------------------------------

def _granary_world(h, monkeypatch, target=30.0):
    import chronicler.grain_reserves as G
    G.set_grain_reserves_enabled(h.world, True)
    G._ensure(h.world)
    for civ in h.world.civilizations:
        civ.treasury = 200
    from chronicler.models import Disposition
    for row in h.world.relationships.values():
        for rel in row.values():
            rel.disposition = Disposition.NEUTRAL
    granary = h.world.grain_reserves.granaries[VERDANT]
    granary.owner = 2
    granary.target, granary.observed = target, 50
    monkeypatch.setattr(G, "_observe", lambda *a: None)
    monkeypatch.setenv("CHRONICLER_CHECK_RESOURCES", "1")
    return G, granary


def _surplus_market(h):
    """Three owners and twenty penniless neighbours: owners keep a large unsold surplus."""
    _people(h, VERDANT, (1, 2, 3), wealth=0.0)
    _people(h, VERDANT, range(40, 60), occupation=2, wealth=0.0)
    h.world.regions[VERDANT].population = 60


def test_procurement_buys_owners_grain_first_and_credits_them_once(monkeypatch):
    h = Harness()
    _surplus_market(h)
    G, granary = _granary_world(h, monkeypatch)
    h.turn({VERDANT: {"grain": 150.0}})             # owners hold most of the market's grain
    owned_before = h.state.region(VERDANT).goods[0]
    commons_before = h.world.regions[VERDANT].stockpile.goods.get("grain", 0.0)
    wealth_before = {a: h.sim.people[a]["wealth"] for a in (1, 2, 3)}
    treasury = h.world.civilizations[2].treasury

    def buy(res):
        G.tick_grain_reserves(h.world, None, res, None)
    h.turn({}, granaries=buy)
    bought = [f for f in h.world.grain_reserves.flows if f.kind == BOUGHT and f.source == VERDANT]
    assert bought and h.world.civilizations[2].treasury == treasury - sum(f.cost for f in bought)
    frame = h.frame(VERDANT)
    procured = frame.flows["procured"]
    assert procured > 0 and h.state.money["procurement_flows"] == len(bought)
    owed = sum(math.floor(f.cost * 1000 * min(1.0, (procured / 1000) / f.sent)) for f in bought)
    assert h.state.money["procurement_owed_milli"] == owed == h.state.money["procurement_credited_milli"]
    (call,) = _calls(h.sim, "transfer_wealth")
    assert call[2:4] == (HR.PURPOSE_FOOD_PROCUREMENT, 0)
    assert sum(v for _, v in call[4]) == owed
    # Nobody here can pay for food and farm income is replaced: the owners'
    # only gain is the procurement credit, pro rata to the grain each gave.
    assert h.state.money["paid_milli"] == 0 and h.state.money["procurement_residual_milli"] == 0
    gained = {a: round((h.sim.people[a]["wealth"] - wealth_before[a]) * 1000) for a in (1, 2, 3)}
    assert dict(call[4]) == gained and sum(gained.values()) == owed
    assert max(gained.values()) - min(gained.values()) <= 1
    # Owners first: the market's commons sold nothing (all of it came from owners).
    assert procured == sum(math.ceil(f.sent * 1000 - 1e-6) for f in bought)
    assert h.world.regions[VERDANT].stockpile.goods.get("grain", 0.0) <= commons_before
    assert owned_before > 0
    # Paid once: the transfer key refuses a repeat, Python refuses first.
    h.state.last_procured_turn = h.world.turn
    t = HR._turn(h.state, h.world)
    t.procured.append(HR._Procured(flow_index=0, region=VERDANT, taken=0.1, milli=100, owners={1: 100}))
    with pytest.raises(RuntimeError, match="already credited"):
        LV.phase10(h.world, economy_result=h.results[-1], agent_bridge=h.bridge)


def test_the_resource_ledger_market_term_counts_owned_grain_sold(monkeypatch):
    h = Harness()
    _surplus_market(h)
    G, _ = _granary_world(h, monkeypatch)
    h.turn({VERDANT: {"grain": 150.0}})
    # Without the seam's term the market would seem to lose less than it sold.
    monkeypatch.setattr(HR, "owned_grain_sold", lambda world: {})
    with pytest.raises(AssertionError, match="resource ledger does not balance"):
        h.turn({}, granaries=lambda res: G.tick_grain_reserves(h.world, None, res, None))


def test_free_rations_include_the_granary_release(monkeypatch):
    h = Harness()
    _people(h, VERDANT, (1, 2))
    _people(h, VERDANT, range(40, 50), occupation=2)
    G, granary = _granary_world(h, monkeypatch)
    granary.grain = 50.0
    h.turn({VERDANT: {"grain": 1.0}})
    released = sum(f.amount for f in h.world.grain_reserves.flows if f.kind == 1 and f.region == VERDANT)
    row = next(r for r in _calls(h.sim, "set_household_retail")[-1][3] if r[0] == VERDANT)
    consumed = h.results[-1].household_retail[VERDANT]["commons_consumed"]
    assert released > 0 and row[2] == pytest.approx((consumed + released) / 0.5)


def test_free_exchange_procurement_leaves_owners_unpaid(monkeypatch):
    h = Harness("--household-retail-mode", "free_exchange")
    _surplus_market(h)
    G, _ = _granary_world(h, monkeypatch)
    h.turn({VERDANT: {"grain": 150.0}})
    h.turn({}, granaries=lambda res: G.tick_grain_reserves(h.world, None, res, None))
    assert h.state.money["procurement_unpaid_milli"] > 0 and not _calls(h.sim, "transfer_wealth")
    (_, _, mode, regions, _) = _calls(h.sim, "set_household_retail")[-1]
    assert mode == 2 and all(price == 0 for _, price, _ in regions)
    assert not _calls(h.sim, "install_retail_income")


def test_foreign_purchases_take_commons_only(monkeypatch):
    h = Harness()
    _surplus_market(h)
    G, granary = _granary_world(h, monkeypatch)
    granary.target = 0.0
    foreign = h.world.grain_reserves.granaries[ASHARA]
    foreign.owner, foreign.target, foreign.observed = 3, 30.0, 50
    _people(h, ASHARA, (90, 91), occupation=2)              # the buyer's market has a demand
    h.world.regions[VERDANT].population = 200                # room for owned and imported grain
    h.turn({VERDANT: {"grain": 150.0}})
    # Imported commons beyond the market's keep: the only grain abroad may buy.
    h.turn({}, imports={VERDANT: {"grain": 120.0}},
           granaries=lambda res: G.tick_grain_reserves(h.world, None, res, None))
    flows = [f for f in h.world.grain_reserves.flows if f.kind == BOUGHT and f.source == VERDANT]
    assert flows and all(f.buyer == 3 and f.seller == 2 for f in flows)
    assert h.frame(VERDANT).flows.get("procured", 0) == 0 and not _calls(h.sim, "transfer_wealth")


# --- modes and boundaries ------------------------------------------------------------

def test_no_relief_titles_the_whole_harvest_with_native_mode_one():
    h = Harness("--household-retail-mode", "no_relief")
    _people(h, VERDANT, (1, 2))
    h.turn({VERDANT: {"grain": 2.0}})
    assert h.region_inputs[0].column("retail_title_share").to_pylist()[VERDANT] == 1.0
    assert h.frame(VERDANT).flows["titled"] == 2000
    assert _calls(h.sim, "set_household_retail")[0][2] == 1
    assert h.summary()["parameters"]["theta"] == 1.0


def test_boundaries_market_paid_work_and_all_are_sticky():
    from chronicler.workshop_payroll_state import WorkshopFirm, WorkshopPayrollState
    h = Harness("--household-retail-boundary", "paid_work")
    _people(h, VERDANT, (1,))
    h.turn({VERDANT: {"grain": 1.0}})
    assert h.state.regions == []
    assert not [n for n in h.region_inputs[-1].schema.names if n.startswith("retail_")]
    h.world.livelihoods.workshop_payroll = WorkshopPayrollState(firms=[WorkshopFirm(
        site=0, region=THORNWOOD, settlement_id=3, city_name="T", opened_turn=10)])
    h.turn()
    assert [(r.region, r.reason) for r in h.state.regions] == [(THORNWOOD, "paid_work")]
    h.world.livelihoods.workshop_payroll.firms[0].status = "closed"
    h.turn()
    assert [r.region for r in h.state.regions] == [THORNWOOD]                     # sticky
    a = Harness("--household-retail-boundary", "all")
    a.turn()
    assert [r.region for r in a.state.regions] == [r for r, reg in enumerate(a.world.regions) if reg.controller]
    m = Harness()
    m.turn()
    m.world.civilizations[2].capital_region = "Thornwood"
    m.turn()
    assert [r.region for r in m.state.regions] == [VERDANT, ASHARA, THORNWOOD, AMBER, OBSIDIAN]


def test_record_only_installs_nothing_and_its_trajectory_equals_l2_alone():
    def scripted(h):
        _people(h, VERDANT, (1, 2, 3), wealth=4.0)
        h.sim.add(9, VERDANT, occupation=2, wealth=4.0)
        _people(h, AMBER, (4, 5), wealth=1.0)
        h.sim.marry(1, 9)
        for turn in range(4):
            if turn == 2:
                h.sim.die_after = {1}
            h.turn({VERDANT: {"grain": 3.0}, AMBER: {"grain": 1.5}})

    alone, shadow = Harness(retail=False), Harness("--household-retail-mode", "record_only")
    scripted(alone)
    scripted(shadow)
    assert not _calls(shadow.sim, *HR.NATIVE_METHODS, "transfer_wealth")
    assert all(not [n for n in b.schema.names if n.startswith("retail_")] for b in shadow.region_inputs)
    dump = json.loads(shadow.world.model_dump_json())
    retail = dump["livelihoods"].pop("household_retail")
    assert dump == json.loads(alone.world.model_dump_json())
    assert shadow.sim.people == alone.sim.people
    assert all(not r["claims"] and not any(r["goods"]) for r in retail["regions"])
    would = shadow.frame(VERDANT).would_be
    assert would["titled_milli"] == 2700 and would["owners"] == 2 and would["price_milli"] > 0
    l2a = livelihoods_snapshot_fields(alone.world)["livelihoods"]["food_allocation"]
    l2b = livelihoods_snapshot_fields(shadow.world)["livelihoods"]["food_allocation"]
    assert l2a == l2b


def test_switching_off_or_to_record_only_closes_holdings_to_the_commons():
    h = Harness()
    _people(h, VERDANT, (1, 2))
    h.turn({VERDANT: {"grain": 4.0}})
    owned = list(h.state.region(VERDANT).goods)
    commons = h.world.regions[VERDANT].stockpile.goods.get("grain", 0.0)
    configure_livelihoods(h.world, _build_parser().parse_args(["--household-retail", "--household-retail-mode",
                                                               "record_only"]), agent_mode="hybrid")
    assert h.state.regions == [] and h.state.log[-1].kind == "switch_off"
    assert h.world.regions[VERDANT].stockpile.goods["grain"] == pytest.approx(commons + owned[0] / 1000)
    configure_livelihoods(h.world, _build_parser().parse_args(["--no-household-retail"]), agent_mode="hybrid")
    assert h.state.enabled is False and not HR.household_retail_active(h.world)


# --- persistence and snapshot --------------------------------------------------------

def test_exact_pickle_and_json_round_trip_mid_pilot():
    from chronicler.models import WorldState
    h = Harness()
    _people(h, VERDANT, (1, 2, 3), wealth=3.0)
    for _ in range(2):
        h.turn({VERDANT: {"grain": 3.0, "fish": 0.4}})
    state = h.state
    assert state.region(VERDANT).claims and state._turn is None
    state._turn = HR._Turn(turn=99)                     # transient: never serialized
    back = pickle.loads(pickle.dumps(h.world))
    assert back.livelihoods.household_retail._turn is None
    assert back.model_dump_json() == h.world.model_dump_json()
    state._turn = None
    assert back.livelihoods.household_retail == state
    loaded = WorldState.model_validate_json(h.world.model_dump_json())
    assert loaded.livelihoods.household_retail == state
    assert loaded.livelihoods.household_retail.region(VERDANT).claims == state.region(VERDANT).claims
    assert all(isinstance(k, int) for k in loaded.livelihoods.household_retail.region(VERDANT).claims)
    # An old pickle without the newer fields still loads.
    raw = state.__getstate__()
    raw["__dict__"] = {k: v for k, v in raw["__dict__"].items() if k in ("schema_version", "enabled", "mode")}
    old = HouseholdRetailState.__new__(HouseholdRetailState)
    old.__setstate__(raw)
    assert old.regions == [] and old.boundary == "market"
    # A resumed copy continues identically.
    twin = copy.deepcopy(h)
    LV.bind_native_pool(twin.world, twin.bridge, reset=False)   # an exact load re-binds the same pool
    h.turn({VERDANT: {"grain": 3.0}})
    twin.turn({VERDANT: {"grain": 3.0}})
    assert twin.world.model_dump_json() == h.world.model_dump_json()


def test_snapshot_summary_reports_the_completed_turn_only():
    h = Harness()
    _people(h, VERDANT, (1, 2), wealth=2.0)
    h.turn({VERDANT: {"grain": 3.0}})
    summary = h.summary()
    assert summary["stage"] == "L6b" and summary["source_turn"] == 10
    assert {r["region"] for r in summary["regions"]} == {VERDANT, ASHARA, AMBER, OBSIDIAN}
    assert set(summary["counters"]) <= set(COUNTERS)
    json.dumps(summary)
    h.world.turn += 1                                      # a turn without a frame: unknown, not zero
    stale = h.summary()
    assert stale["regions"] is None and stale["money"] is None


def test_economy_reconstruct_keeps_the_retail_columns_only_when_present():
    from chronicler.economy import reconstruct_economy_result
    world = generate_world(seed=42)
    n = len(world.regions)

    def batches(extra):
        region = {"region_id": pa.array(range(n), type=pa.uint16()),
                  **{f"stockpile_{g}": pa.array([0.0] * n, type=pa.float32()) for g in
                     ("grain", "fish", "salt", "timber", "ore", "botanicals", "precious", "exotic")},
                  **{c: pa.array([1.0] * n, type=pa.float32()) for c in
                     ("farmer_income_modifier", "food_sufficiency", "merchant_margin", "merchant_trade_income")},
                  "trade_route_count": pa.array([0] * n, type=pa.uint32()), **extra}
        civ = pa.record_batch({"civ_id": pa.array([], type=pa.uint8()), "treasury_tax": pa.array([], type=pa.float32()),
                               "tithe_base": pa.array([], type=pa.float32()),
                               "priest_tithe_share": pa.array([], type=pa.float32())})
        obs = pa.record_batch({"region_id": pa.array([], type=pa.uint16()), "import_share": pa.array([], type=pa.float32()),
                               "trade_dependent": pa.array([], type=pa.bool_())})
        up = pa.record_batch({"dest_region_id": pa.array([], type=pa.uint16()),
                              "source_ordinal": pa.array([], type=pa.uint8()),
                              "source_region_id": pa.array([], type=pa.uint16())})
        cons = pa.record_batch({k: pa.array([0.0], type=pa.float64()) for k in
                                ("production", "transit_loss", "consumption", "storage_loss", "cap_overflow",
                                 "clamp_floor_loss")})
        return pa.record_batch(region), civ, obs, up, cons

    assert reconstruct_economy_result(*batches({}), world).household_retail == {}
    extra = {"retail_titled_grain": pa.array([0.5] + [None] * (n - 1), type=pa.float32()),
             "commons_consumed": pa.array([0.25] * n, type=pa.float32())}
    got = reconstruct_economy_result(*batches(extra), world).household_retail
    assert got[0] == {"retail_titled_grain": 0.5, "commons_consumed": 0.25}
    assert got[1]["retail_titled_grain"] is None and len(got) == n


def test_a_native_economy_without_the_retail_columns_is_refused():
    h = Harness()
    _people(h, VERDANT, (1,))
    snapshot = h.sim.get_snapshot()
    batch = LV.prepare_phase2(h.world, build_economy_region_input_batch(h.world), h.bridge, snapshot)
    res = h.economy(batch, {VERDANT: {"grain": 1.0}})
    res.household_retail = {}
    with pytest.raises(RuntimeError, match="retail columns"):
        LV.finish_phase2(h.world, res, h.bridge)
    LV.rollback_phase2(h.world)
    assert h.state._turn.phase2 is None


def test_counters_are_bounded_and_the_log_rolls():
    state = HouseholdRetailState()
    for i in range(80):
        HR._log(state, HR.RetailRecord(turn=i, region=0, kind="pilot_opened"))
    assert len(state.log) == 64 and state.log_dropped == 16 and state.log[0].turn == 16
    with pytest.raises(KeyError):
        HR._bump(state, "not_a_counter")
    assert MAX_CLAIMS == 4096
    assert RetailRegion(region=0, opened_turn=0, reason="capital").goods == [0, 0, 0, 0, 0]


def test_an_heir_beyond_the_claims_cap_is_refused_and_the_share_escheats(monkeypatch):
    h = Harness()
    _people(h, VERDANT, (1, 2), wealth=0.0)
    h.sim.add(30, VERDANT, occupation=2, age=10, parents=(1, 0))
    h.sim.add(31, VERDANT, occupation=2, age=11, parents=(1, 0))
    h.turn({VERDANT: {"grain": 20.0}})
    monkeypatch.setattr(HR, "MAX_CLAIMS", 2)                      # 1 and 2 hold the only entries
    h.sim.die_after = {1}
    h.turn()
    claims = _owners(h, VERDANT)
    assert set(claims) == {2, 30}                                 # 1's entry frees one slot: 30 only
    escheat = [r for r in h.state.log if r.kind == "escheat" and r.owner == 1]
    assert escheat and escheat[0].note == "claims cap" and h.state.counters["claims_refused"] == 1
    inherited = [r for r in h.state.log if r.kind == "inherited" and r.owner == 1]
    assert [(r.other, r.note) for r in inherited] == [(30, "child")]
    assert abs(inherited[0].milli - escheat[0].milli) <= 1        # the equal shares of 30 and 31


def test_occupation_and_siege_do_not_reach_owned_stock_but_are_counted():
    h = Harness()
    _people(h, VERDANT, (1, 2), wealth=0.0)
    h.turn({VERDANT: {"grain": 8.0}})
    h.world.regions[VERDANT].occupied_by = "Kethani Empire"
    goods = sum(h.state.region(VERDANT).goods)
    h.turn()
    frame = h.frame(VERDANT)
    assert h.state.counters["requisition_exempt_region_turns"] == 1
    assert "war_loss" not in frame.flows and frame.open_milli == goods


def test_a_failing_second_install_cancels_the_first():
    h = Harness()
    _people(h, VERDANT, (1, 2))
    h.turn({VERDANT: {"grain": 3.0}})

    def refuse(turn, regions):
        raise ValueError("retail income refused")
    h.sim.install_retail_income = refuse
    with pytest.raises(ValueError, match="retail income refused"):
        h.turn({VERDANT: {"grain": 3.0}})
    assert ("cancel_household_retail",) in h.sim.calls and ("cancel_retail_income",) not in h.sim.calls
    assert h.sim.pending_retail is None


def test_paid_work_includes_regions_of_paid_repair_crews():
    from types import SimpleNamespace
    h = Harness("--household-retail-boundary", "paid_work")
    h.world.livelihoods.repair_projects = SimpleNamespace(
        enabled=True, receipts=[SimpleNamespace(region=FROST, wages_milli=250),
                                SimpleNamespace(region=AMBER, wages_milli=0)])
    assert HR._paid_work_regions(h.world) == [(FROST, "paid_work")]
    h.world.livelihoods.repair_projects = None
    h.state.boundary = "paid_work"
    assert HR._paid_work_regions(h.world) == []
