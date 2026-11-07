"""The CW4 screen (quarantine rules, slice C1) and the CW4b screen (its migration
channel, slice C1b): arms, activation and extractors.

Offline: constructed bundles only (no simulation, no child process); the
extractors were also cross-checked on development-world bundles (the
preregistration page names the checks). Oracle chunk ``connected-world-c``.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def CW():
    sys.path.insert(0, str(ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location("cw_screens_under_test", ROOT / "scripts" / "connected_world_screens.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


REGIONS = ["A1", "A2", "B1", "C1"]


def _snap(turn, *, quarantine=(), active=(), deaths=0, total=0, control=None, civs=None, rules=None,
          fa_regions=None, counts=(100, 100, 100, 50)):
    control = control or {"A1": "A", "A2": "A", "B1": "B", "C1": "C"}
    civs = civs or {c: {"population": 100, "treasury": 50, "stability": 40} for c in "ABC"}
    epi = {"active": list(active), "deaths": deaths, "deaths_by_pathogen": {}, "deaths_total": total,
           "quarantine": list(quarantine), "strains": {}}
    if rules is not None:
        epi["quarantine_rules"] = rules
    snap = {"turn": turn, "epidemics": epi, "region_control": control, "civ_stats": civs,
            "regional_population": {"schema_version": 1, "source_turn": turn - 1, "counts": list(counts)}}
    if fa_regions is not None:
        snap["food_accounting"] = {"schema_version": 1, "source_turn": turn - 1, "regions": fa_regions}
    return snap


def _rules(mode, turn, *, closures=(), totals=None):
    base = {"receipts": turn, "closed_pair_turns": 0, "closures_opened": 0, "closures_lapsed": 0,
            "enforcement_paid": 0, "route_turns_removed": 0, "forgone_income": 0, "merchant_edges_removed": 0,
            "leaked_deliveries": 0, "leaked_quantity": 0.0}
    return {"schema_version": 1, "mode": mode, "closures": list(closures), "receipt": {"turn": turn - 1},
            "totals": {**base, **(totals or {})}}


def _arrival(turn, target_civ, source_civ, region="A1"):
    actors = [c for c in dict.fromkeys((target_civ, source_civ)) if c]
    return {"turn": turn, "event_type": "epidemic_arrival", "actors": actors, "region": region}


def _bundle(snaps, events=(), stats_len=None):
    n = len(snaps) if stats_len is None else stats_len
    return {"world_state": {"regions": [{"name": r} for r in REGIONS]}, "history": snaps,
            "events_timeline": list(events),
            "metadata": {"merchant_trip_stats": [{"disruption_replans": 1, "unwind_count": 2,
                                                  "stalled_trip_count": 0}] * n}}


def test_the_screen_declares_four_arms_on_one_control_chain_and_two_primaries(CW):
    screen = CW.SCREENS["CW4"]
    assert screen.ready and screen.root == "QL"
    assert {arm: control for arm, (_f, control) in screen.arms.items()} == {
        "QL": None, "Q0": "QL", "QC": "Q0", "QR": "QC"}
    assert screen.arms["QR"][0] == ("--quarantine-mode", "closure") and screen.arms["QL"][0] == ()
    # Amendment 1: whole-run, world-level primaries (no conditioning on an arm's own closures).
    assert [o.id for o in screen.primaries()] == ["cw4_world_arrivals", "cw4_world_death_rate"]
    assert all((o.arm, o.control) == ("QR", "QC") for o in screen.primaries())
    assert screen.held == {"template": tuple(range(761, 767)), "procedural": tuple(range(861, 867))}
    assert screen.pilot == {"template": (5,), "procedural": (19,)}
    assert screen.base == ("--turns", "200", "--agents", "hybrid", "--simulate-only")
    from screen_runner import check_screen
    assert check_screen(screen) == []


def test_windows_cover_the_closing_turns_and_the_following_k(CW):
    # Snapshot s records world turn s - 1: civ A closes at world turns 2 and 3.
    snaps = [_snap(s, quarantine=["A"] if s in (3, 4) else []) for s in range(1, 21)]
    closing, windows, problems = CW.cw4_windows(_bundle(snaps))
    assert problems == [] and closing == {"A": {2, 3}}
    assert windows["A"] == set(range(3, 3 + 1 + CW.CW4_K + 1))      # 3 .. 14 (from 2+1 to 3+1+K)
    short = [_snap(s, quarantine=["A"] if s == 4 else []) for s in range(1, 8)]
    assert CW.cw4_windows(_bundle(short))[1]["A"] == {4, 5, 6}       # cut at the last world turn


def test_arrivals_count_only_cross_polity_arrivals_into_window_civs(CW):
    snaps = [_snap(s, quarantine=["A"] if s == 3 else []) for s in range(1, 21)]
    events = [_arrival(3, "A", "B"),            # in the window (w=2 -> 3..13)
              _arrival(13, "A", "C"),           # last window turn
              _arrival(14, "A", "B"),           # after the window
              _arrival(2, "A", "B"),            # the closing turn itself: before the closure acts
              _arrival(5, "A", "A"),            # same polity
              _arrival(6, "A", None),           # an uncontrolled source
              _arrival(7, "B", "A")]            # into a civ that did not close
    m, problems = CW.cw4_extract(_bundle(snaps, events), ())
    assert problems == []
    assert m["arrivals"] == 2 and m["window_civ_turns"] == CW.CW4_K + 1
    assert m["arrivals_per_100_window_civ_turns"] == pytest.approx(200 / (CW.CW4_K + 1))
    # The primary counts every cross-polity arrival of the run, whoever closed.
    assert m["arrivals_world"] == 5 and m["region_turns"] == 20 * 4
    assert m["arrivals_world_per_1000_region_turns"] == pytest.approx(5 * 1000 / 80)


def test_deaths_per_person_turn_of_closing_civs_and_the_world(CW):
    snaps = []
    for s in range(1, 11):
        active = [{"region": "A1", "deaths": 3}, {"region": "B1", "deaths": 5}] if s == 5 else []
        snaps.append(_snap(s, quarantine=["A"] if s == 3 else [], active=active, deaths=10 if s == 5 else 0,
                           total=10 if s >= 5 else 0))
    m, problems = CW.cw4_extract(_bundle(snaps), ())
    assert problems == []
    # A's window: world turns 3..9 (7 turns of 100 people); its deaths: 3 at world turn 4.
    assert m["person_turns_closing"] == 700 and m["deaths_closing"] == 3
    assert m["deaths_per_1000_pt_closing"] == pytest.approx(3 * 1000 / 700)
    assert m["world_epidemic_deaths"] == 10 and m["reported_death_share"] == pytest.approx(0.8)
    # The primary counts ALL epidemic deaths (epidemics.deaths, reported or not) per
    # person-turn of every region (regional_population.counts: 350 a turn).
    assert m["world_person_turns"] == 10 * 350
    assert m["world_deaths_per_1000_pt"] == pytest.approx(10 * 1000 / (10 * 350))
    assert m["merchant_replans"] == 10 and m["merchant_unwinds"] == 20


def test_food_transport_sums_the_closing_civs_regions_in_their_windows(CW):
    fa = [{"region_id": 0, "native": {"transport_net": 2.0}}, {"region_id": 1, "native": {"transport_net": -0.5}},
          {"region_id": 2, "native": {"transport_net": 7.0}}]
    snaps = [_snap(s, quarantine=["A"] if s == 3 else [], fa_regions=fa) for s in range(1, 6)]
    m, _ = CW.cw4_extract(_bundle(snaps), ())
    assert m["food_net_transport_closing"] == pytest.approx(1.5 * 2)   # world turns 3, 4 (the run ends at 4)
    none = [_snap(s, fa_regions=fa) for s in range(1, 6)]
    assert CW.cw4_extract(_bundle(none), ())[0]["food_net_transport_closing"] == 0.0


def test_rules_measures_are_recorded_under_new_modes_and_never_zero_in_legacy(CW):
    closures = [{"id": 1, "civ": "A", "target": "B", "opened_turn": 2, "last_renewed_turn": 2, "cause": ""}]
    snaps = [_snap(s, quarantine=["A"] if s == 3 else [],
                   rules=_rules("closure", s, closures=closures if s == 3 else [],
                                totals={"closures_opened": 1, "forgone_income": 8, "leaked_deliveries": 1}))
             for s in range(1, 6)]
    m, problems = CW.cw4_extract(_bundle(snaps), ("--quarantine-mode", "closure"))
    assert problems == []
    assert (m["closures_opened"], m["forgone_income"], m["leaked_deliveries"]) == (1, 8, 1)
    assert m["partner_civs"] == 1 and m["partner_population_end"] == 100
    cost = [_snap(s, rules=_rules("cost_only", s)) for s in range(1, 4)]
    assert CW.cw4_extract(_bundle(cost), ("--quarantine-mode", "cost_only"))[0]["leaked_deliveries"] is None
    legacy, problems = CW.cw4_extract(_bundle([_snap(s) for s in range(1, 4)]), ())
    assert problems == [] and legacy["forgone_income"] is None and legacy["partner_civs"] is None
    # A rules record where none belongs, or missing where one does, is a missing outcome.
    assert CW.cw4_extract(_bundle(snaps), ())[1]
    assert CW.cw4_extract(_bundle([_snap(s) for s in range(1, 4)]), ("--quarantine-mode", "none"))[1]
    wrong = [_snap(s, rules=_rules("none", s)) for s in range(1, 4)]
    assert any("mode differs" in p for p in CW.cw4_extract(_bundle(wrong), ("--quarantine-mode", "closure"))[1])


def test_missing_records_are_problems_never_zero(CW):
    bad_sum = [_snap(1, deaths=4, total=4), _snap(2, deaths=1, total=6)]
    assert any("deaths_total" in p for p in CW.cw4_extract(_bundle(bad_sum), ())[1])
    misdated = [_snap(s) for s in range(1, 3)]
    misdated[1]["regional_population"]["source_turn"] = 7
    assert any("regional_population" in p for p in CW.cw4_extract(_bundle(misdated), ())[1])
    snaps = [_snap(s) for s in range(1, 4)]
    del snaps[1]["epidemics"]["quarantine"]
    assert any("epidemics.quarantine" in p for p in CW.cw4_extract(_bundle(snaps), ())[1])
    no_stats = _bundle([_snap(s) for s in range(1, 4)])
    no_stats["metadata"] = {}
    assert any("merchant_trip_stats" in p for p in CW.cw4_extract(no_stats, ())[1])
    del snaps[0]["region_control"]
    assert any("region_control" in p for p in CW.cw4_extract(_bundle(snaps), ())[1])


def test_activation_per_arm(CW):
    opened = [_snap(s, rules=_rules("closure", s, totals={"closures_opened": 3})) for s in range(1, 3)]
    assert CW.cw4_activation(_bundle(opened), ("--quarantine-mode", "closure"))[0] is True
    quiet = [_snap(s, rules=_rules("cost_only", s)) for s in range(1, 3)]
    assert CW.cw4_activation(_bundle(quiet), ("--quarantine-mode", "cost_only"))[0] is False
    assert CW.cw4_activation(_bundle([_snap(1)]), ("--quarantine-mode", "closure"))[0] is None
    sick = [_snap(1, active=[{"region": "A1", "deaths": 0}]), _snap(2)]
    assert CW.cw4_activation(_bundle(sick), ("--quarantine-mode", "none"))[0] is True
    assert CW.cw4_activation(_bundle([_snap(1)]), ("--quarantine-mode", "none"))[0] is False


# --- CW4b: the migration channel (slice C1b) -------------------------------------------

QRM = ("--quarantine-mode", "closure", "--quarantine-channels", "trade,migration")
MIG_TOTALS = {"migrants_blocked": 0, "migrants_blocked_flight": 0, "migrants_blocked_hunger": 0,
              "migrants_refusal_spells": 0}


def _mig_rules(turn, blocked, *, cumulative, totals=None, channels=("trade", "migration")):
    rules = _rules("closure", turn, totals={"closures_opened": 1, **MIG_TOTALS, **(totals or {}),
                                             "migrants_blocked": cumulative})
    rules["channels"] = list(channels)
    rules["receipt"].update(migrants_blocked=blocked, migration_refusals=None if blocked is None else (
        [{"closure": 1, "from": "A1", "to": "B1", "driver": "famine_memory", "persons": blocked}] if blocked else []))
    return rules


def _mig_bundle(per_turn, **kwargs):
    snaps, total = [], 0
    for s, blocked in enumerate(per_turn, start=1):
        total += blocked or 0
        snaps.append(_snap(s, rules=_mig_rules(s, blocked, cumulative=total, **kwargs)))
    return _bundle(snaps)


def test_cw4b_declares_three_arms_on_one_chain_and_qrm_minus_qc_primaries(CW):
    screen = CW.SCREENS["CW4b"]
    assert screen.ready and screen.root == "QC"
    assert {arm: control for arm, (_f, control) in screen.arms.items()} == {"QC": None, "QR": "QC", "QRM": "QR"}
    assert screen.arms["QRM"][0] == QRM and screen.arms["QR"][0] == ("--quarantine-mode", "closure")
    assert [o.id for o in screen.primaries()] == ["cw4b_world_arrivals", "cw4b_world_death_rate"]
    assert all((o.arm, o.control) == ("QRM", "QC") for o in screen.primaries())
    by_id = {o.id: o for o in screen.outcomes}
    assert (by_id["cw4b_mig_world_arrivals"].arm, by_id["cw4b_mig_world_arrivals"].control) == ("QRM", "QR")
    assert by_id["cw4b_refusals"].control is None
    assert screen.held == {"template": tuple(range(3101, 3107)), "procedural": tuple(range(3201, 3207))}
    assert screen.pilot == {"template": (5,), "procedural": (19,)}
    assert screen.base == ("--turns", "200", "--agents", "hybrid", "--simulate-only")
    from screen_runner import check_screen
    assert check_screen(screen) == []


def test_cw4b_reads_the_refusal_totals_and_checks_them_against_the_receipts(CW):
    bundle = _mig_bundle([0, 3, 0, 2], totals={"migrants_blocked_flight": 4, "migrants_blocked_hunger": 1,
                                               "migrants_refusal_spells": 4})
    m, problems = CW.cw4b_extract(bundle, QRM)
    assert problems == []
    assert (m["migrants_blocked"], m["migrants_blocked_flight"], m["migrants_blocked_hunger"],
            m["migrants_refusal_spells"], m["turns_with_refusals"]) == (5, 4, 1, 4, 2)
    # Totals that disagree with the receipts, an unobserved receipt or a missing total are refused.
    bad = _mig_bundle([0, 3, 0, 2])
    bad["history"][-1]["epidemics"]["quarantine_rules"]["totals"]["migrants_blocked"] = 9
    assert any("sum to 5" in p for p in CW.cw4b_extract(bad, QRM)[1])
    assert any("not observed" in p for p in CW.cw4b_extract(_mig_bundle([0, None, 1]), QRM)[1])
    gone = _mig_bundle([1, 1])
    del gone["history"][-1]["epidemics"]["quarantine_rules"]["totals"]["migrants_refusal_spells"]
    assert any("lack migrants_refusal_spells" in p for p in CW.cw4b_extract(gone, QRM)[1])
    rows = _mig_bundle([2])
    rows["history"][0]["epidemics"]["quarantine_rules"]["receipt"]["migration_refusals"][0]["persons"] = 1
    assert any("refusal rows differ" in p for p in CW.cw4b_extract(rows, QRM)[1])


def test_cw4b_channels_must_match_the_arm_and_migration_values_are_never_zero_elsewhere(CW):
    trade = [_snap(s, rules={**_rules("closure", s), "channels": ["trade"]}) for s in range(1, 4)]
    m, problems = CW.cw4b_extract(_bundle(trade), ("--quarantine-mode", "closure"))
    assert problems == [] and m["migrants_blocked"] is None and m["migrants_refusal_spells"] is None
    cost = [_snap(s, rules={**_rules("cost_only", s), "channels": []}) for s in range(1, 4)]
    assert CW.cw4b_extract(_bundle(cost), ("--quarantine-mode", "cost_only"))[1] == []
    # The migration channel's record in the trade arm, or a trade record in QRM, is a missing outcome.
    assert any("channels differ" in p for p in CW.cw4b_extract(_mig_bundle([1]), ("--quarantine-mode", "closure"))[1])
    assert any("channels differ" in p for p in CW.cw4b_extract(_bundle(trade), QRM)[1])
    leaky = [_snap(s, rules={**_rules("closure", s, totals=MIG_TOTALS), "channels": ["trade"]}) for s in range(1, 3)]
    assert any("without the migration channel" in p
               for p in CW.cw4b_extract(_bundle(leaky), ("--quarantine-mode", "closure"))[1])


def test_cw4b_activation(CW):
    assert CW.cw4b_activation(_mig_bundle([0, 2]), QRM)[0] is True
    assert CW.cw4b_activation(_mig_bundle([0, 0]), QRM)[0] is False        # closed, but nobody refused
    no_total = _mig_bundle([1])
    del no_total["history"][-1]["epidemics"]["quarantine_rules"]["totals"]["migrants_blocked"]
    assert CW.cw4b_activation(no_total, QRM)[0] is None
    trade = [_snap(s, rules={**_rules("closure", s, totals={"closures_opened": 2}), "channels": ["trade"]})
             for s in range(1, 3)]
    assert CW.cw4b_activation(_bundle(trade), ("--quarantine-mode", "closure")) == (True, "2 closures opened (closure)")
    assert CW.cw4b_activation(_bundle([_snap(1)]), QRM)[0] is None
