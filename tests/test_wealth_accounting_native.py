"""A1 observation-only wealth ledger on the real compiled extension.

Development worlds only. Template seed 7 (8 regions x 4 civs) with every
livelihoods payer on (the catalog's all-on set, retail in every region) plus
``--finance --domestic-credit``: PL3 granary crews from turn 26, RS1 attached
apprentices and PL1 expeditions from about turn 60, PL3 workshop crews beside
granary crews at turns 75 and 78, retail settlement every turn and a live
expedition at turn 67 (measured on this source). Template seed 23 for the
unpaid PL3 control; procedural 32x10 seed 31 for the resource checks. Native
decisions, deaths, trips, prices and transfers are not mocked; the one
constructed step is named where it occurs (a transfer injected between Phase 10
and the next Phase 2).
"""
from __future__ import annotations

import json
import sys

import pytest

pytest.importorskip("chronicler_agents")
pytestmark = pytest.mark.native

HYBRID = ["--agents", "hybrid", "--simulate-only"]
ALL = ["--grain-reserves", "--public-grain-shipments", "--grain-storage", "--scholarship", "--academy-services",
       "--workshops", "--food-allocation", "--timber-stock", "--grain-convoys", "--commons-rules",
       "--learning-cohorts", "--workshop-payroll", "--relocation-costs", "--local-budgets", "--apprenticeship",
       "--repair-projects", "--veteran-reintegration", "--remittances", "--clearing-protection",
       "--operating-wear", "--timber-supply", "--recovery-crews", "--maintenance-obligation",
       "--household-retail", "--household-retail-boundary=all", "--finance", "--domestic-credit"]
LEDGER = ["--wealth-accounting"]
PROCEDURAL = ["--worldgen", "procedural", "--regions", "32", "--civs", "10"]


def _cli(monkeypatch, folder, *argv):
    import chronicler.main as main_mod
    monkeypatch.setattr(sys, "argv", ["chronicler", *argv, "--output", str(folder / "chronicle.md"),
                                      "--state", str(folder / "state.json")])
    main_mod.main()


def _bundle(folder):
    from chronicler.bundle_codec import load_bundle
    bundle = load_bundle(folder / "chronicle_bundle.json")
    bundle["metadata"].pop("generated_at", None)
    return bundle


def _strip(value):
    """Remove only the ledger: every ``wealth_accounting`` key, and a
    ``livelihoods`` container that held nothing else."""
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            if key == "wealth_accounting":
                continue
            item = _strip(item)
            if key == "livelihoods" and isinstance(item, dict) and set(item) <= {"schema_version"} \
                    and "wealth_accounting" in value[key]:
                continue
            out[key] = item
        return out
    if isinstance(value, list):
        return [_strip(item) for item in value]
    return value


def _frames(bundle):
    from chronicler.wealth_accounting import record_status
    out = []
    for snap in bundle["history"]:
        status, frame = record_status(snap)
        assert status == "observed", (snap.get("turn"), status)
        out.append(frame)
    return out


def _turn(world, bridge):
    from chronicler.action_engine import ActionEngine
    from chronicler.simulation import run_turn_result
    engine = ActionEngine(world)
    run_turn_result(world, lambda c, w: engine.select_action(c, seed=w.seed), lambda w, e: "",
                    seed=world.seed + world.turn, agent_bridge=bridge)
    return world.livelihoods.wealth_accounting.frame


@pytest.mark.parametrize("case", ["all_switches", "ledger_alone"])
def test_observer_identity_full_world_dump(tmp_path, monkeypatch, case):
    """Every output except the ledger's record equals the switch off: the
    history, the bundle's final world and state.json, compared whole."""
    turns = 40 if case == "all_switches" else 25
    flags = ["--seed", "7", "--turns", str(turns), *HYBRID, *ALL] if case == "all_switches" else \
        ["--seed", "3", "--turns", str(turns), *HYBRID]
    _cli(monkeypatch, tmp_path / "off", *flags)
    _cli(monkeypatch, tmp_path / "on", *flags, *LEDGER)
    off, on = _bundle(tmp_path / "off"), _bundle(tmp_path / "on")
    assert len(_frames(on)) == len(on["history"]) == turns
    assert "wealth_accounting" in on["world_state"]["livelihoods"]
    assert _strip(on["history"]) == off["history"]
    assert _strip(on["world_state"]) == off["world_state"]
    assert _strip(on) == off
    states = [json.loads((tmp_path / side / "state.json").read_text(encoding="utf-8")) for side in ("off", "on")]
    assert _strip(states[1]) == states[0]
    assert (tmp_path / "off" / "chronicle.md").read_bytes() == (tmp_path / "on" / "chronicle.md").read_bytes()


def test_no_hidden_writer_between_turns_and_an_injected_transfer_is_detected(tmp_path, monkeypatch):
    """Over 31 turns with every payer on, each opening equals the previous
    closing bit for bit (f32 wealth and region of every id). Constructed: a
    keyed transfer of 5.0 between Phase 10 and the next Phase 2 is found."""
    import pyarrow as pa
    from chronicler.run_checkpoint import read_checkpoint
    straight = tmp_path / "straight"
    _cli(monkeypatch, straight, "--seed", "7", "--turns", "31", *HYBRID, *ALL, *LEDGER, "--checkpoint-turns", "30")
    frames = _frames(_bundle(straight))
    assert frames[0]["continuity"]["status"] == "unchecked" and frames[0]["continuity"]["reason"] == "first_turn"
    assert all(f["continuity"]["status"] == "exact" for f in frames[1:])
    ckpt = straight / "checkpoint_turn_30.ckpt"
    control = read_checkpoint(ckpt).state
    assert _turn(control.world, control.agent_bridge)["continuity"]["status"] == "exact"
    control.agent_bridge.close()
    arm = read_checkpoint(ckpt).state
    sim = arm.agent_bridge._sim
    people = pa.record_batch(sim.get_snapshot()).to_pylist()
    target = min(people, key=lambda p: (p["wealth"], p["id"]))
    ((aid, requested, applied, _residual, status),) = sim.transfer_wealth(arm.world.turn, 3, 99, [(target["id"], 5000)])
    assert (aid, requested, applied, status) == (target["id"], 5000, 5000, 0)
    frame = _turn(arm.world, arm.agent_bridge)
    c = frame["continuity"]
    assert c["status"] == "broken" and c["wealth_changed"] and not c["region_changed"]
    assert c["difference"] == pytest.approx(5.0, abs=1e-4) and c["agents_difference"] == 0
    assert c["regions"] == [[target["region"], pytest.approx(5.0, abs=1e-4), 0]]
    ledger = arm.world.livelihoods.wealth_accounting
    assert ledger.counters["continuity_broken"] == 1 and ledger.log[-1].kind == "continuity_broken"
    arm.agent_bridge.close()


def test_typed_flows_close_per_purpose_and_every_paid_work_row_is_attributed(tmp_path, monkeypatch):
    """80 turns, every payer on, ``CHRONICLER_CHECK_RESOURCES=1``: each frame's
    package closures hold, every paid-work receipt row has exactly one
    installing package, PL3's granary + workshop crews equal PL3's own withheld
    total (RL7) every turn, and the ledger's lifetime channel totals equal the
    packages' own lifetime counters."""
    monkeypatch.setenv("CHRONICLER_CHECK_RESOURCES", "1")
    _cli(monkeypatch, tmp_path, "--seed", "7", "--turns", "80", *HYBRID, *ALL, *LEDGER)
    bundle = _bundle(tmp_path)
    frames = _frames(bundle)
    seen = {"both_crews": 0, "apprentices": 0, "woodcut": 0, "granary": 0, "credit": 0, "purchases": 0}
    for f in frames:
        assert f["typed_complete"], f["turn"]
        failed = [c for c in f["closures"] if not c["closes"]]
        assert not failed, (f["turn"], failed)
        assert f["turn"] == 0 or f["continuity"]["status"] == "exact", (f["turn"], f["continuity"])
        wh = f["withheld"]
        assert wh["unattributed_rows"] == 0 and wh["conflicts"] == 0, (f["turn"], wh)
        assert all(p["matches"] in (True, None) for p in wh["packages"]), (f["turn"], wh["packages"])
        split = wh["recovery_crews"]
        assert split["closes"] and split["rows_dropped"] == 0, (f["turn"], split)
        assert sum(p["rows"] for p in wh["packages"]) == wh["rows"]
        seen["both_crews"] += split["granary"] > 0 and split["workshop"] > 0
        rows = {p["package"]: p["rows"] for p in wh["packages"]}
        seen["apprentices"] += rows["apprenticeship"] > 0
        typed = {r["channel"]: r for r in f["typed"]}
        seen["woodcut"] += typed["woodcut_wage"]["in_milli"] > 0
        seen["granary"] += typed["granary_crew_wage"]["in_milli"] > 0
        seen["credit"] += typed["domestic_credit"]["in_milli"] > 0 or typed["domestic_credit"]["out_milli"] > 0
        seen["purchases"] += typed["food_purchase"]["in_milli"] > 0
        w = f["world"]
        assert w["unplaced_agents"] == 0
        assert w["native_model"] == pytest.approx(w["delta"] - w["typed_net_milli"] / 1000, abs=1e-9)
        assert sum(r["native_model"] for r in f["regions"]) == pytest.approx(
            w["native_model"] + (w["unlocated_in_milli"] - w["unlocated_out_milli"]) / 1000, abs=1e-6)
    assert all(seen.values()), seen
    last = bundle["history"][-1]["livelihoods"]
    life = last["wealth_accounting"]["lifetime"]
    counters = {name: last[name]["counters"] for name in ("repair_projects", "recovery_crews", "timber_supply",
                                                          "remittances", "relocation_costs", "household_retail",
                                                          "workshop_payroll", "apprenticeship")}
    assert life["repair_wage_in_milli"] == counters["repair_projects"].get("wages_milli", 0)
    assert life["granary_crew_wage_in_milli"] == counters["recovery_crews"]["granary_wages_milli"] > 0
    assert life["woodcut_wage_in_milli"] == counters["timber_supply"]["wages_milli"] > 0
    assert life["remittance_in_milli"] == counters["remittances"]["credited_milli"] > 0
    assert life["remittance_out_milli"] == counters["remittances"]["credited_milli"] + counters["remittances"]["fee_milli"]
    assert life["relocation_fare_out_milli"] == counters["relocation_costs"]["fare_debited_milli"] > 0
    assert life["food_purchase_in_milli"] == counters["household_retail"]["credited_milli"] > 0
    assert life["food_procurement_in_milli"] == counters["household_retail"].get("procurement_credited_milli", 0)
    assert life["workshop_wage_in_milli"] == counters["workshop_payroll"].get("wages_paid", 0)
    assert life["apprentice_stipend_in_milli"] == counters["apprenticeship"].get("stipends_paid", 0)
    credit = bundle["world_state"]["domestic_credit"]
    assert life["domestic_credit_in_milli"] - life["domestic_credit_out_milli"] == pytest.approx(
        credit["merchant_applied"] * 1000, abs=1e-3)
    pl3 = counters["recovery_crews"]["income_replaced"]
    assert life["withheld_recovery_crews_granary"] + life["withheld_recovery_crews_workshop"] == pytest.approx(pl3)
    assert life["withheld_recovery_crews_workshop"] > 0 and life["withheld_recovery_crews_granary"] > 0
    assert life["withheld_unattributed"] == 0


def test_the_unpaid_crew_control_sinks_the_granary_coins(tmp_path, monkeypatch):
    _cli(monkeypatch, tmp_path, "--seed", "23", "--turns", "60", *HYBRID, *ALL, "--recovery-crew-mode", "unpaid",
         *LEDGER)
    frames = _frames(_bundle(tmp_path))
    coins = 0
    for f in frames:
        assert all(c["closes"] for c in f["closures"]), f["turn"]
        assert next(r for r in f["typed"] if r["channel"] == "granary_crew_wage")["in_milli"] == 0
        unpaid = [c for c in f["closures"] if c["check"] == "granary coins = wages + sunk (unpaid)"]
        assert len(unpaid) == 1
        coins += unpaid[0]["lhs"]
        assert f["treasury"]["to_households_milli"]["granary_crew_wage"] == 0
    assert coins > 0


def test_exact_resume_inside_a_live_expedition_and_a_retail_settlement(tmp_path, monkeypatch):
    straight = tmp_path / "straight"
    _cli(monkeypatch, straight, "--seed", "7", "--turns", "72", *HYBRID, *ALL, *LEDGER, "--checkpoint-turns", "68")
    ckpt = straight / "checkpoint_turn_68.ckpt"
    resumed = tmp_path / "resumed"
    _cli(monkeypatch, resumed, "--resume", str(ckpt))
    a, b = _bundle(straight), _bundle(resumed)
    at = a["history"][67]["livelihoods"]
    assert at["timber_supply"]["expeditions"], "a live expedition at the checkpoint"
    assert (at["household_retail"]["money"] or {}).get("paid_milli", 0) > 0, "a retail settlement turn"
    assert at["wealth_accounting"]["frame"]["turn"] == 67
    assert a["history"] == b["history"] and a["world_state"] == b["world_state"]
    assert (straight / "state.json").read_bytes() == (resumed / "state.json").read_bytes()
    after = [s["livelihoods"]["wealth_accounting"]["frame"] for s in b["history"][68:]]
    assert all(f["continuity"]["status"] == "exact" for f in after)


def test_legacy_resume_switch_off_and_refusals(tmp_path, monkeypatch):
    base = ["--seed", "11", *HYBRID, "--remittances", *LEDGER]
    first = tmp_path / "first"
    _cli(monkeypatch, first, *base, "--turns", "12", "--checkpoint-turns", "10")
    saved = first / "state.json"
    # A legacy state-file resume rebuilds the pool: a dated pool-reset record,
    # the first resumed opening unchecked, the next ones exact.
    legacy = tmp_path / "legacy"
    _cli(monkeypatch, legacy, "--resume", str(saved), *base, "--turns", "15")
    frames = [s["livelihoods"]["wealth_accounting"]["frame"] for s in _bundle(legacy)["history"]
              if s["turn"] > 12]
    assert frames[0]["turn"] == 12 and frames[0]["continuity"]["reason"] == "pool_reset"
    assert all(f["continuity"]["status"] == "exact" for f in frames[1:])
    ledger = _bundle(legacy)["world_state"]["livelihoods"]["wealth_accounting"]
    resets = [r for r in ledger["log"] if r["kind"] == "pool_reset"]
    assert len(resets) == 1 and resets[0]["turn"] == 12 and resets[0]["detail"]["closing_turn"] == 11
    # Turned off on resume: the closing and frame are dropped, dated; no record follows.
    off = tmp_path / "off"
    _cli(monkeypatch, off, "--resume", str(saved), "--seed", "11", *HYBRID, "--remittances",
         "--no-wealth-accounting", "--turns", "14")
    bundle = _bundle(off)
    state = bundle["world_state"]["livelihoods"]["wealth_accounting"]
    assert state["enabled"] is False and "closing" not in state and state["frame"] is None
    assert state["log"][-1]["kind"] == "switched_off" and state["log"][-1]["turn"] == 12
    assert all("wealth_accounting" not in s["livelihoods"] for s in bundle["history"] if s["turn"] > 12)
    # Outside hybrid: a legacy resume is refused until the switch is ended,
    # and an exact resume refuses another agent mode. (``--agents off`` is the
    # parser default, which an exact resume reads as not given: it continues
    # the checkpoint's own hybrid run, and the ledger with it.)
    with pytest.raises(ValueError, match="pass --no-wealth-accounting"):
        _cli(monkeypatch, tmp_path / "refused", "--resume", str(saved), "--agents", "off", "--simulate-only",
             "--turns", "14")
    assert not (tmp_path / "refused" / "chronicle_bundle.json").exists()
    exact = str(first / "checkpoint_turn_10.ckpt")
    for mode in ("shadow", "demographics-only"):
        with pytest.raises(SystemExit):
            _cli(monkeypatch, tmp_path / f"refused_{mode}", "--resume", exact, "--agents", mode)
        assert not (tmp_path / f"refused_{mode}" / "chronicle_bundle.json").exists()
    _cli(monkeypatch, tmp_path / "default_mode", "--resume", exact, "--agents", "off")
    kept = _bundle(tmp_path / "default_mode")
    assert kept["world_state"]["agent_mode"] == "hybrid"
    assert kept["history"][-1]["livelihoods"]["wealth_accounting"]["frame"]["continuity"]["status"] == "exact"


def test_resource_checks_pass_on_an_all_switch_procedural_run(tmp_path, monkeypatch):
    monkeypatch.setenv("CHRONICLER_CHECK_RESOURCES", "1")
    _cli(monkeypatch, tmp_path, "--seed", "31", "--turns", "40", *PROCEDURAL, *HYBRID, *ALL, *LEDGER)
    frames = _frames(_bundle(tmp_path))
    assert len(frames) == 40
    for f in frames:
        assert all(c["closes"] for c in f["closures"]), f["turn"]
        assert f["turn"] == 0 or f["continuity"]["status"] == "exact"
        assert f["withheld"]["unattributed_rows"] == 0 and f["withheld"]["conflicts"] == 0
        assert f["typed_complete"]
