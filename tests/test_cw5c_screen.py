"""The CW5c screen (bounded epidemic care capacity, slice C2): arms, activation
and the extractor.

Offline: constructed bundles only (no simulation, no child process); the
extractor was also validated on the timing pilot's bundles (the
preregistration page names the checks). Oracle chunk ``connected-world-c2``.
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


def _applied(region, coverage, deaths, cases, factor=None):
    f = 1 - 0.3 * coverage if factor is None else factor
    return {"region": region, "source_turn": 0, "patients": 5.0, "infectious": 5.0, "coverage": coverage,
            "care_factor": f, "would_be": 1 - 0.3 * coverage, "techniques_factor": None, "combined_factor": f,
            "floored": False, "deaths": deaths, "cases": cases, "infectious_after": 1.0}


def _receipt(region, carers=1, *, farm=1.0, paid=500, due=500, withheld=0.3):
    return {"turn": 0, "region": region, "civ": 0, "commitment": 1, "envelope": 1, "infectious": 5.0, "need": 1.0,
            "eligible": 3, "carers": [{"agent_id": 10 + i, "origin": "rural_farmer", "share": farm / max(1, carers),
                                       "wage_due_milli": due // max(1, carers), "wage_paid_milli": paid // max(1, carers),
                                       "wage_residual_milli": 0, "income_withheld": withheld / max(1, carers)}
                                      for i in range(carers)],
            "care_time": farm, "patients": 5.0 * farm, "wages_due_milli": due, "wages_paid_milli": paid,
            "wage_residual_milli": 0, "farm_time_removed": farm, "limit": "need_met", "paid": True}


def _care(turn, mode="care", applied=(), frame=(), ledger=(), counters=None, tick=True):
    return {"schema_version": 1, "stage": "C2", "mode": mode, "source_turn": turn - 1,
            "tick": {"turn": turn - 1, "applied": list(applied), "refused": []} if tick else None,
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


def test_three_arms_on_one_chain_and_three_care_primaries(CW):
    screen = CW.SCREENS["CW5c"]
    assert screen.ready and screen.root == "E0" and screen.control_activation
    assert {arm: control for arm, (_f, control) in screen.arms.items()} == {"E0": None, "EC": "E0", "EF": "EC"}
    assert screen.arms["EC"][0] == ("--epidemic-care", "--epidemic-care-mode", "cost_only")
    assert screen.arms["EF"][0] == ("--epidemic-care",)
    assert screen.base == ("--turns", "200", "--agents", "hybrid", "--simulate-only", "--grain-reserves",
                           "--local-budgets")
    assert [o.id for o in screen.primaries()] == ["cw5c_covered_cfr", "cw5c_world_death_rate", "cw5c_covered_death_rate"]
    assert all((o.arm, o.control) == ("EF", "EC") for o in screen.primaries())
    assert screen.held == {"template": tuple(range(3301, 3307)), "procedural": tuple(range(3401, 3407))}
    assert screen.pilot == {"template": (5,), "procedural": (19,)}
    from screen_runner import check_screen, check_seeds, load_registry
    assert check_screen(screen) == []
    problems, _notes = check_seeds(screen, load_registry(), reuse="recorded")
    assert problems == []


def test_covered_region_turns_pool_deaths_over_new_infections_and_person_turns(CW):
    counters = {"carer_turns": 2, "farm_time_removed": 2.0}
    snaps = [
        _snap(1, care=_care(1, frame=[_receipt(0)]), awards=[("epidemic_care", 1), ("relief", 3)]),
        _snap(2, active=[_outbreak("A1", 1, 10.0)], deaths=1, total=1,
              care=_care(2, applied=[_applied(0, 1.0, 1, 10.0), _applied(1, 0.0, 0, 0.0)], frame=[_receipt(0)],
                         counters=counters)),
    ]
    m, problems = CW.cw5c_extract(_bundle(snaps), ("--epidemic-care",))
    assert problems == []
    assert m["covered_region_turns"] == 1 and m["applied_region_turns"] == 2
    assert m["covered_cfr"] == pytest.approx(0.1)
    assert m["covered_person_turns"] == 100 and m["covered_deaths_per_1000_pt"] == pytest.approx(10.0)
    assert m["world_deaths_per_1000_pt"] == pytest.approx(1000 * 1 / 500)
    assert m["carers_named"] == 2 and m["farm_time_removed"] == 2.0 and m["wages_paid"] == 1.0
    assert m["l9_care_coins"] == 1 and m["l9_other_coins"] == 3 and m["l9_relief_coins"] == 3
    assert m["mean_coverage"] == 0.5


def test_continuing_outbreak_region_turns_are_defined_in_every_arm(CW):
    snaps = [_snap(1, active=[_outbreak("A1", 0, 4.0)]),
             _snap(2, active=[_outbreak("A1", 2, 8.0), _outbreak("B1", 1, 3.0)], deaths=3, total=3),
             _snap(3, active=[_outbreak("B1", 1, 2.0)], deaths=1, total=4)]
    m, problems = CW.cw5c_extract(_bundle(snaps), ())
    assert problems == []
    assert m["reported_region_turns"] == 4 and m["itt_region_turns"] == 2
    assert m["itt_cfr"] == pytest.approx((2 + 1) / (8 + 2))
    assert all(m[k] is None for k in ("covered_cfr", "carers_named", "farm_time_removed"))   # not recorded, never 0


def test_hunger_stability_and_unrest_measures(CW):
    snaps = [_snap(1, fa=[1.2, 0.9, 0.5]), _snap(2, fa=[1.0, 0.59, 0.61])]
    snaps[0]["cities"] = {"cities": [{"id": 1, "unrest": 0.2}, {"id": 2, "unrest": 0.4}]}
    snaps[1]["cities"] = {"cities": [{"id": 1, "unrest": 0.6}]}
    m, problems = CW.cw5c_extract(_bundle(snaps), ())
    assert problems == []
    assert m["dearth_region_turns"] == 4 and m["famine_region_turns"] == 2
    assert m["stability_mean"] == pytest.approx(50.0)
    assert m["city_unrest_mean"] == pytest.approx(0.4)
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
    snaps = [_snap(1, care=_care(1, frame=[_receipt(0)], counters={"carer_turns": 5}))]
    _m, problems = CW.cw5c_extract(_bundle(snaps), ("--epidemic-care",))
    assert any("care counter carer_turns is 5" in p for p in problems)
    bad = _snap(1)
    del bad["regional_population"]
    _m, problems = CW.cw5c_extract(_bundle([bad]), ())
    assert any("regional_population" in p for p in problems)


def test_activation_per_arm(CW):
    quiet = _bundle([_snap(1)])
    assert CW.cw5c_activation(quiet, ())[0] is False
    sick = _bundle([_snap(1, active=[_outbreak("A1", 0, 3.0)])])
    assert CW.cw5c_activation(sick, ())[0] is True
    covered = _bundle([_snap(1, care=_care(1, applied=[_applied(0, 0.5, 0, 2.0)], frame=[_receipt(0)]))])
    ok, text = CW.cw5c_activation(covered, ("--epidemic-care",))
    assert ok is True and "1 covered region-turns" in text
    idle = _bundle([_snap(1, care=_care(1, applied=[_applied(0, 0.0, 0, 0.0)]))])
    assert CW.cw5c_activation(idle, ("--epidemic-care", "--epidemic-care-mode", "cost_only"))[0] is False
    assert CW.cw5c_activation(_bundle([_snap(1)]), ("--epidemic-care",))[0] is None
