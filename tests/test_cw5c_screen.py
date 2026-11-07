"""The CW5c screen (bounded epidemic care capacity, slice C2): arms, activation,
the extractor, the paired intention-to-treat reading and the report.

Offline: constructed bundles only (no simulation, no child process); the
extractor was also validated on the timing pilot's and development worlds'
bundles (the preregistration page names the checks). Oracle chunk
``connected-world-c2``.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
REGIONS = ["A1", "A2", "B1"]


@pytest.fixture(scope="module")
def CW():
    sys.path.insert(0, str(ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location("cw5c_screens_under_test", ROOT / "scripts" / "connected_world_screens.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _applied(region, coverage, deaths, infectious_after, factor=None, tech=None):
    f = 1 - 0.3 * coverage if factor is None else factor
    combined = max(0.5, (tech or 1.0) * f) if f != 1.0 else (tech or 1.0)
    return {"region": region, "source_turn": 0, "patients": 5.0, "infectious": 5.0, "coverage": coverage,
            "care_factor": f, "would_be": 1 - 0.3 * coverage, "techniques_factor": tech, "combined_factor": combined,
            "floored": False, "deaths": deaths, "cases": 1.0, "infectious_after": infectious_after}


def _receipt(region, carers=1, *, farm=1.0, paid=500, due=500, withheld=0.3, unpaid=None):
    return {"turn": 0, "region": region, "civ": 0, "commitment": 1, "envelope": 1, "infectious": 5.0, "need": 1.0,
            "eligible": 3, "carers": [{"agent_id": 10 + i, "origin": "rural_farmer", "share": farm / max(1, carers),
                                       "wage_due_milli": due // max(1, carers), "wage_paid_milli": paid // max(1, carers),
                                       "wage_residual_milli": 0, "income_withheld": withheld / max(1, carers)}
                                      for i in range(carers)],
            "care_time": farm, "patients": 5.0 * farm, "wages_due_milli": due, "wages_paid_milli": paid,
            "wage_residual_milli": 0, "farm_time_removed": farm, "limit": "need_met", "paid": unpaid is None,
            "unpaid_reason": unpaid}


def _care(turn, mode="care", applied=(), frame=(), ledger=(), counters=None, regions=(), tick=True):
    return {"schema_version": 1, "stage": "C2", "mode": mode, "source_turn": turn - 1,
            "tick": {"turn": turn - 1, "applied": list(applied), "refused": [],
                     "regions": [{"region": j, "deaths": d, "infectious_pt": i, "cases": 1.0} for j, d, i in regions]}
            if tick else None,
            "frame": list(frame), "ledger": list(ledger), "capacity": [], "counters": counters or {},
            "parameters": {}}


def _snap(turn, *, active=(), deaths=0, total=0, counts=(100, 100, 50), care=None, awards=(), fa=None):
    epi = {"active": list(active), "deaths": deaths, "deaths_total": total, "quarantine": [], "strains": {}}
    proposals = [{"pid": i, "service": service} for i, (service, _amount) in enumerate(awards)]
    budget = {"schema_version": 1, "stage": "L9", "mode": "bargained", "source_turn": turn - 1,
              "decisions": [{"civ": 0, "proposals": proposals,
                             "awards": [{"pid": i, "amount": amount} for i, (_s, amount) in enumerate(awards)]}],
              "counters": {}}
    snap = {"turn": turn, "epidemics": epi,
            "civ_stats": {"A": {"population": 100, "treasury": 50, "stability": 40},
                          "B": {"population": 50, "treasury": 20, "stability": 60}},
            "regional_population": {"schema_version": 1, "source_turn": turn - 1, "counts": list(counts)},
            "livelihoods": {"schema_version": 1, "local_budgets": budget}}
    if care is not None:
        snap["livelihoods"]["epidemic_care"] = care
    if fa is not None:
        snap["food_accounting"] = {"schema_version": 1, "source_turn": turn - 1,
                                   "regions": [{"region_id": i, "sufficiency_after_relief": s} for i, s in enumerate(fa)]}
    return snap


def _bundle(snaps):
    return {"world_state": {"regions": [{"name": r} for r in REGIONS]}, "history": snaps, "events_timeline": [],
            "metadata": {}}


def _outbreak(region, deaths, cases):
    return {"region": region, "pathogen": "pox", "prevalence": 0.05, "immune": 0.1, "cases": cases, "deaths": deaths,
            "virgin": False}


def _counters(**kw):
    return {"covered_region_turns": 0, "carer_turns": 0, "farm_time_removed": 0.0, "wages_paid_milli": 0,
            "unpaid_bills": 0, "envelope_coins": 0, **kw}


def _two_turns(mode="care", d0=2, d1=1):
    """Turn 0: carers named in A1 (1 coin). Turn 1: the capacity covers A1 (coverage 1)
    and B1 is infected but not covered."""
    counters = _counters(covered_region_turns=1, carer_turns=2, farm_time_removed=2.0, wages_paid_milli=1000,
                         envelope_coins=2)
    return [
        _snap(1, care=_care(1, mode, frame=[_receipt(0)], regions=[(0, 0, 4.0)],
                            ledger=[{"turn": 0, "civ": 0, "envelope_coins": 1, "status": "paid"}]),
              awards=[("epidemic_care", 1), ("relief", 3)]),
        _snap(2, active=[_outbreak("A1", d0, 10.0)], deaths=d0 + d1, total=d0 + d1,
              care=_care(2, mode, applied=[_applied(0, 1.0, d0, 20.0, factor=None if mode == "care" else 1.0),
                                           _applied(1, 0.0, 0, 0.0)],
                         frame=[_receipt(0)], regions=[(0, d0, 20.0), (2, d1, 10.0)], counters=counters,
                         ledger=[{"turn": 1, "civ": 0, "envelope_coins": 1, "status": "paid"}])),
    ]


def test_three_arms_on_one_chain_and_three_unconditioned_or_control_cell_primaries(CW):
    screen = CW.SCREENS["CW5c"]
    assert screen.ready and screen.root == "E0" and screen.control_activation and screen.report is not None
    assert {arm: control for arm, (_f, control) in screen.arms.items()} == {"E0": None, "EC": "E0", "EF": "EC"}
    assert screen.arms["EC"][0] == ("--epidemic-care", "--epidemic-care-mode", "cost_only")
    assert screen.arms["EF"][0] == ("--epidemic-care",)
    assert [o.id for o in screen.primaries()] == ["cw5c_world_death_rate", "cw5c_itt_cfr", "cw5c_world_dpi"]
    assert all((o.arm, o.control) == ("EF", "EC") for o in screen.primaries())
    itt = next(o for o in screen.outcomes if o.id == "cw5c_itt_cfr")
    assert itt.pair is CW.cw5c_itt_pair
    assert screen.held == {"template": tuple(range(3301, 3307)), "procedural": tuple(range(3401, 3407))}
    from screen_runner import check_screen, check_seeds, load_registry
    assert check_screen(screen) == []
    problems, _notes = check_seeds(screen, load_registry(), reuse="recorded")
    assert problems == []


def test_cells_world_fatality_mechanism_and_reach(CW):
    m, problems = CW.cw5c_extract(_bundle(_two_turns()), ("--epidemic-care",))
    assert problems == []
    assert m["cells"] == [[0, 0, 0, 4.0], [1, 0, 2, 20.0], [1, 2, 1, 10.0]]
    assert m["covered_cells"] == [[1, 0]] and m["covered_region_turns"] == 1
    assert m["world_infectious_pt"] == 34.0 and m["world_deaths_per_ipt"] == pytest.approx(3 / 34)
    assert m["covered_dpi"] == pytest.approx(2 / 20) and m["covered_death_share"] == pytest.approx(2 / 3)
    assert m["mean_relative_factor"] == pytest.approx(0.7) and m["mean_coverage"] == 0.5
    assert m["l9_care_coins"] == 1 and m["l9_other_coins"] == 3
    assert m["envelope_coins_executed"] == 2 and m["wages_paid"] == 1.0 and m["care_coins_unspent"] == 1.0
    assert m["carers_named"] == 2 and m["farm_time_removed"] == 2.0 and m["unpaid_bills"] == 0


def test_the_itt_primary_reads_both_arms_at_the_controls_covered_cells(CW):
    ec, _ = CW.cw5c_extract(_bundle(_two_turns("cost_only", d0=4, d1=1)), ("--epidemic-care", "--epidemic-care-mode",
                                                                          "cost_only"))
    ef, _ = CW.cw5c_extract(_bundle(_two_turns("care", d0=2, d1=3)), ("--epidemic-care",))
    ef["covered_cells"] = [[1, 2]]           # EF's own coverage differs: it must not matter
    arm, control = CW.cw5c_itt_pair({"m": ef}, {"m": ec})
    assert control == pytest.approx(4 / 20) and arm == pytest.approx(2 / 20)     # cell (1, 0) in both
    # A cell the arm never infected counts zero of both deaths and infectious person-turns.
    ec["covered_cells"] = [[1, 0], [1, 1]]
    assert CW.cw5c_itt_pair({"m": ef}, {"m": ec})[0] == pytest.approx(2 / 20)
    assert CW.cw5c_itt_pair({"m": {}}, {"m": ec}) == (None, pytest.approx(4 / 20))
    # The runner subtracts the pair, and refuses a paired reading without a control.
    import screen_runner as SR
    rows = [{"arm": "EF", "stratum": "t", "seed": 1, "rc": 0, "m": ef, "activation": {"activated": True}},
            {"arm": "EC", "stratum": "t", "seed": 1, "rc": 0, "m": ec, "activation": {"activated": True}}]
    _cells, values = SR.paired_values(rows, CW.SCREENS["CW5c"], "EF", "EC", lambda r: None, "t", [1],
                                      pair=CW.cw5c_itt_pair)
    assert values == [pytest.approx(2 / 20 - 4 / 20)]
    bad = SR.Screen(name="X", title="x", preregistration=None, base=(), arms={"A": ((), None)}, root="A", pilot={},
                    held={}, outcomes=(SR.Outcome("p", "p", "A", None, lambda r: None, pair=CW.cw5c_itt_pair),))
    assert any("paired reading needs a control" in p for p in SR.check_preregistration(bad, held=False))


def test_continuing_outbreak_region_turns_are_defined_in_every_arm(CW):
    snaps = [_snap(1, active=[_outbreak("A1", 0, 4.0)]),
             _snap(2, active=[_outbreak("A1", 2, 8.0), _outbreak("B1", 1, 3.0)], deaths=3, total=3),
             _snap(3, active=[_outbreak("B1", 1, 2.0)], deaths=1, total=4)]
    m, problems = CW.cw5c_extract(_bundle(snaps), ())
    assert problems == []
    assert m["reported_region_turns"] == 4 and m["continuing_region_turns"] == 2
    assert m["continuing_deaths_per_case"] == pytest.approx((2 + 1) / (8 + 2))
    assert all(m[k] is None for k in ("world_deaths_per_ipt", "cells", "covered_cells", "carers_named"))


def test_hunger_stability_and_unrest_measures(CW):
    snaps = [_snap(1, fa=[1.2, 0.9, 0.5]), _snap(2, fa=[1.0, 0.59, 0.61])]
    snaps[0]["cities"] = {"cities": [{"id": 1, "unrest": 0.2}, {"id": 2, "unrest": 0.4}]}
    snaps[1]["cities"] = {"cities": [{"id": 1, "unrest": 0.6}]}
    m, problems = CW.cw5c_extract(_bundle(snaps), ())
    assert problems == []
    assert m["dearth_region_turns"] == 4 and m["famine_region_turns"] == 2
    assert m["stability_mean"] == pytest.approx(50.0) and m["city_unrest_mean"] == pytest.approx(0.4)
    m, _ = CW.cw5c_extract(_bundle([_snap(1)]), ())
    assert m["city_unrest_mean"] is None              # no city recorded: unknown, not zero


def test_missing_or_inconsistent_records_are_problems_never_zeros(CW):
    snaps = [_snap(1, care=_care(1, frame=[_receipt(0)], tick=False))]
    _m, problems = CW.cw5c_extract(_bundle(snaps), ("--epidemic-care",))
    assert any("not observed" in p for p in problems)
    snaps = [_snap(1, care=_care(1, mode="cost_only"))]
    _m, problems = CW.cw5c_extract(_bundle(snaps), ("--epidemic-care",))
    assert any("mode 'cost_only'" in p for p in problems)
    snaps = [_snap(1, care=_care(1))]
    _m, problems = CW.cw5c_extract(_bundle(snaps), ())
    assert "an epidemic care record in an arm without care" in problems
    for key, value in (("covered_region_turns", 5), ("wages_paid_milli", 999), ("envelope_coins", 7)):
        snaps = _two_turns()
        snaps[-1]["livelihoods"]["epidemic_care"]["counters"][key] = value
        _m, problems = CW.cw5c_extract(_bundle(snaps), ("--epidemic-care",))
        assert any(f"care counter {key} is {value}" in p for p in problems), key
    snaps = _two_turns()
    snaps[-1]["epidemics"]["deaths"] = 9
    _m, problems = CW.cw5c_extract(_bundle(snaps), ("--epidemic-care",))
    assert any("differ from epidemics.deaths" in p for p in problems)
    bad = _snap(1)
    del bad["regional_population"]
    _m, problems = CW.cw5c_extract(_bundle([bad]), ())
    assert any("regional_population" in p for p in problems)


def test_activation_per_arm(CW):
    assert CW.cw5c_activation(_bundle([_snap(1)]), ())[0] is False
    assert CW.cw5c_activation(_bundle([_snap(1, active=[_outbreak("A1", 0, 3.0)])]), ())[0] is True
    ok, text = CW.cw5c_activation(_bundle(_two_turns()), ("--epidemic-care",))
    assert ok is True and "1 covered region-turns" in text
    idle = _bundle([_snap(1, care=_care(1, applied=[_applied(0, 0.0, 0, 0.0)]))])
    assert CW.cw5c_activation(idle, ("--epidemic-care", "--epidemic-care-mode", "cost_only"))[0] is False
    assert CW.cw5c_activation(_bundle([_snap(1)]), ("--epidemic-care",))[0] is None


def test_the_report_shows_the_mechanism_check_and_reach(CW):
    ec, _ = CW.cw5c_extract(_bundle(_two_turns("cost_only", d0=4, d1=1)), ("--epidemic-care", "--epidemic-care-mode",
                                                                          "cost_only"))
    ef, _ = CW.cw5c_extract(_bundle(_two_turns("care", d0=2, d1=1)), ("--epidemic-care",))
    rows = [{"arm": "EC", "stratum": "t", "seed": 1, "rc": 0, "m": ec}, {"arm": "EF", "stratum": "t", "seed": 1, "rc": 0, "m": ef}]
    text = "\n".join(CW._cw5c_report(rows, {"t": [1]}))
    assert "mechanism check" in text and "reach and attenuation" in text
    assert "| t1 | 0.2 | 0.1 | 0.5 | 0.7 | 0 | 0.5 |" in text
    assert "| t1 | 0.8 | 0.7 | -0.240 |" in text
