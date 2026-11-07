"""A4 titled trade on the real compiled extension (template seed 1).

Development world only (template seed 1, household retail in every region,
titled trade, the A1 ledger): merchants first buy owners' surplus food at
turn 51; shipments travel one to three hops, carriers released in transit
(snapshots 55, 56 and 61: occupation changes and a migration) return their
shipments to the origin at once (review M3), a holder dies in transit
(snapshot 60: cargo escheated where it stood), and deliveries become
holders' retail claims that households buy. Every pairwise payment is checked against the live pool, a
repeated key is refused unchanged, carriers are never planned on native trips
(titled trade raises otherwise) and exact resumes inside live shipments equal
the straight run.
"""
from __future__ import annotations

import sys

import pytest

pytest.importorskip("chronicler_agents")
pytestmark = pytest.mark.native

BASE = ["--agents", "hybrid", "--simulate-only", "--grain-reserves", "--public-grain-shipments", "--food-allocation",
        "--household-retail", "--household-retail-boundary", "all", "--titled-trade", "--wealth-accounting"]
CARGO_PURCHASE = 8


def _cli(monkeypatch, folder, *argv):
    import chronicler.main as main_mod
    monkeypatch.setattr(sys, "argv", ["chronicler", *argv, "--output", str(folder / "chronicle.md"),
                                      "--state", str(folder / "state.json")])
    main_mod.main()


class _CheckedSim:
    """Delegates to the native simulator; checks every pairwise payment
    against the live pool (the payer loses exactly what the payees gain, no
    payer row limited, a refused credit never leaves the payer) and that a
    repeated key is refused unchanged."""

    def __init__(self, sim, seen):
        self._sim, self._seen = sim, seen

    def __getattr__(self, name):
        return getattr(self._sim, name)

    def _wealth(self):
        snap = self._sim.get_snapshot()
        return dict(zip(snap.column("id").to_pylist(), snap.column("wealth").to_pylist(), strict=True))

    def settle_pairs(self, turn, purpose, batch, rows):
        assert purpose == CARGO_PURCHASE
        before = self._wealth()
        out = self._sim.settle_pairs(turn, purpose, batch, rows)
        after = self._wealth()
        payer = rows[0][0]
        assert all(r[0] == payer for r in rows)
        for (gp, ge, requested, sent, credited, refunded, status), (p, e, amount) in zip(out, rows, strict=True):
            assert (gp, ge, requested) == (p, e, amount) and sent == amount and status in (0, 1)
            assert credited + refunded == sent and before[ge] * 1000 >= 0
            assert after[ge] - before[ge] == pytest.approx(credited / 1000, abs=2e-5)
            self._seen["rows"] += 1
            self._seen["paid"] += credited
        total = sum(r[4] for r in out)
        assert before[payer] - after[payer] == pytest.approx(total / 1000, abs=2e-5)
        with pytest.raises(ValueError, match="already applied"):
            self._sim.settle_pairs(turn, purpose, batch, rows)
        assert self._wealth() == after
        self._seen["bills"] += 1
        return out


def test_merchants_buy_carry_and_sell_owned_food_with_exact_books(tmp_path, monkeypatch):
    from chronicler import titled_trade as TT
    from chronicler.bundle_codec import load_bundle
    from chronicler_agents import AgentSimulator
    assert AgentSimulator.wealth_transfer_purposes()[CARGO_PURCHASE] == "cargo_purchase"
    assert AgentSimulator.work_reservation_categories()[TT.CATEGORY_TRADE] == "trade"
    seen = {"bills": 0, "rows": 0, "paid": 0}
    original = TT._native
    monkeypatch.setattr(TT, "_native", lambda bridge: _CheckedSim(original(bridge), seen))
    monkeypatch.setenv("CHRONICLER_CHECK_RESOURCES", "1")
    _cli(monkeypatch, tmp_path, "--seed", "1", "--turns", "80", *BASE)
    bundle = load_bundle(tmp_path / "chronicle_bundle.json")
    paid = withheld_rows = delivered = 0
    outcomes = {}
    for snap in bundle["history"]:
        lv = snap["livelihoods"]
        tt, ledger = lv["titled_trade"], lv["wealth_accounting"]["frame"]
        assert tt["stage"] == "A4"
        frame = tt["frame"]
        if frame is not None:
            for d in frame["dispatched"]:
                paid += d["paid"]
                assert d["paid"] == sum(r[3] for r in d["seller_rows"]) or d["sellers"] > len(d["seller_rows"])
                assert d["milli"] == sum(d["cargo"]) and d["refunded"] == 0
            for row in frame["withheld"]:
                withheld_rows += 1
                assert row["share"] == 1.0 and row["deducted"] == pytest.approx(row["ordinary"])
            for e in frame["events"]:
                if e["event"] in ("delivered", "returned", "escheated", "released_returned"):
                    outcomes[e["shipment"]] = outcomes.get(e["shipment"], []) + [e["event"]]
        for ship in tt["shipments"] + tt["closed"]:
            lost = sum(ship["losses"].values())
            assert sum(ship["cargo_open"]) == (sum(ship["cargo"]) + lost + ship["delivered"] + ship["returned"]
                                               + ship["deposited"])
        if ledger is not None:
            assert all(c["closes"] for c in ledger["closures"]), ledger["closures"]
            typed = {r["channel"]: r for r in ledger["typed"]}
            assert typed["cargo_purchase"]["in_milli"] == typed["cargo_purchase"]["out_milli"]
            assert ledger["withheld"]["unattributed_rows"] == 0
        retail = lv["household_retail"]
        for f in retail["regions"] or ():
            delivered += f["flows"].get("consigned_in", 0)
    last = bundle["history"][-1]["livelihoods"]["titled_trade"]
    counters = last["counters"]
    assert counters["dispatched"] >= 5 and counters["delivered"] >= 3 and counters["escheated"] >= 1
    assert all(len(v) == 1 for v in outcomes.values())             # one declared outcome per shipment
    assert counters["paid_milli"] == paid == seen["paid"] and seen["bills"] == counters["dispatched"]
    assert counters["receipt_rows"] == withheld_rows == counters["carrier_turns"] > 0
    assert counters["consigned_milli"] == delivered > 0
    assert counters["cargo_sold_milli"] > 0 and counters["cargo_sales_credited_milli"] > 0
    life = bundle["history"][-1]["livelihoods"]["wealth_accounting"]["lifetime"]
    assert life["cargo_purchase_in_milli"] == life["cargo_purchase_out_milli"] == paid


def _resume_identical(tmp_path, monkeypatch, flags, turns, k):
    from chronicler.bundle_codec import load_bundle
    straight = tmp_path / "straight"
    _cli(monkeypatch, straight, "--seed", "1", "--turns", str(turns), *flags, "--checkpoint-turns", str(k))
    ckpt = straight / f"checkpoint_turn_{k}.ckpt"
    assert ckpt.exists()
    resumed = tmp_path / "resumed"
    _cli(monkeypatch, resumed, "--resume", str(ckpt))
    a, b = (load_bundle(p / "chronicle_bundle.json") for p in (straight, resumed))
    for bundle in (a, b):
        bundle["metadata"].pop("generated_at", None)
    assert a["history"] == b["history"] and a["world_state"] == b["world_state"]
    assert (straight / "state.json").read_bytes() == (resumed / "state.json").read_bytes()
    return a


@pytest.mark.parametrize("k, turns, expect", [
    (52, 55, "moved"),            # a shipment halfway along its two-hop route
    (55, 58, "released_returned"),  # carriers in transit switch occupation: their shipments return
    (59, 62, "escheated"),        # the holder dies in the next tick
])
def test_exact_resume_with_a_shipment_in_transit(tmp_path, monkeypatch, k, turns, expect):
    a = _resume_identical(tmp_path, monkeypatch, BASE, turns, k)
    assert a["history"][k]["livelihoods"]["titled_trade"]["shipments"]          # live at the checkpoint
    events = [e["event"] for snap in a["history"][k + 1:]
              for e in (snap["livelihoods"]["titled_trade"]["frame"] or {}).get("events", [])]
    assert expect in events


def test_the_one_sided_transfer_refuses_the_pairwise_purposes(tmp_path, monkeypatch):
    """Review m4: cargo_purchase and cargo_sale are paid only pairwise."""
    from chronicler_agents import AgentSimulator
    sim = AgentSimulator(num_regions=1, seed=1)
    for purpose in (CARGO_PURCHASE, CARGO_PURCHASE + 1):
        with pytest.raises(ValueError, match="pairwise"):
            sim.transfer_wealth(1, purpose, 0, [(1, 10)])


@pytest.mark.parametrize("force", ["reset", "death"])
def test_a_deposit_made_while_phase_2_is_prepared_reaches_the_economy(tmp_path, monkeypatch, force):
    """Review M1 on the real extension: a forced pool reset (as a legacy
    resume rebuilds the pool) and a holder's death seen at ``reserve_first``
    deposit cargo after the region batch was built; retail patches the batch,
    so the economy starts from commons that hold the cargo."""
    import chronicler.livelihoods as LV
    import chronicler.titled_trade as TT
    from chronicler.household_retail_state import RETAIL_GOODS
    seen = {}
    real_prep, real_people = LV.prepare_phase2, TT._people

    def prep(world, region_input, agent_bridge, snapshot, *, acc=None):
        st = getattr(world.livelihoods, "titled_trade", None)
        armed = st is not None and "forced" not in seen and world.turn >= 52 and bool(st.shipments)
        if armed:
            ship = sorted(st.shipments, key=lambda s: s.id)[0]
            rid = ship.region()
            hit = [s for s in st.shipments if s.region() == rid and (force == "reset" or s.holder == ship.holder)]
            cargo = [sum(s.cargo[g] for s in hit) for g in range(len(RETAIL_GOODS))]
            before = [float(world.regions[rid].stockpile.goods.get(g, 0.0)) for g in RETAIL_GOODS]
            retail = world.livelihoods.household_retail.region(rid)
            owned = list(retail.goods) if retail is not None and force == "reset" else [0] * len(RETAIL_GOODS)
            seen["forced"] = (int(world.turn), sorted(s.id for s in hit), cargo)
            if force == "reset":
                world.livelihoods._pool_sim = -1
            else:
                monkeypatch.setattr(TT, "_people", lambda snap: {k: v for k, v in real_people(snap).items()
                                                                 if k != ship.holder})
        out = real_prep(world, region_input, agent_bridge, snapshot, acc=acc)
        if armed:
            monkeypatch.setattr(TT, "_people", real_people)
            built = [region_input.column(f"stockpile_{g}").to_pylist()[rid] for g in RETAIL_GOODS]
            got = [out.column(f"stockpile_{g}").to_pylist()[rid] for g in RETAIL_GOODS]
            now = [float(world.regions[rid].stockpile.goods.get(g, 0.0)) for g in RETAIL_GOODS]
            seen["check"] = (built, got, now, [b + (o + v) / 1000 for b, o, v in zip(before, owned, cargo)])
        return out
    monkeypatch.setattr(LV, "prepare_phase2", prep)
    monkeypatch.setenv("CHRONICLER_CHECK_RESOURCES", "1")
    _cli(monkeypatch, tmp_path, "--seed", "1", "--turns", "56", *BASE)
    turn, ids, cargo = seen["forced"]
    built, got, now, expected = seen["check"]
    assert sum(cargo) > 0 and ids
    assert got != pytest.approx(built, rel=1e-6, abs=1e-3)       # the batch was built without the cargo
    assert got == pytest.approx(now, rel=1e-6, abs=1e-3)         # and the economy reads it
    assert now == pytest.approx(expected, rel=1e-9, abs=1e-6)
    from chronicler.bundle_codec import load_bundle
    bundle = load_bundle(tmp_path / "chronicle_bundle.json")
    closed = {s["id"]: s for snap in bundle["history"] for s in snap["livelihoods"]["titled_trade"]["closed"]}
    for sid in ids:
        assert closed[sid]["outcome"] == ("pool_reset" if force == "reset" else "escheated")
        assert closed[sid]["closed_turn"] == turn and closed[sid]["deposit_reason"] in ("pool_reset", "holder_died")
    assert sum(closed[sid]["deposited"] for sid in ids) == sum(cargo)
