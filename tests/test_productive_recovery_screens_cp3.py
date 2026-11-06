"""PL6d: the checkpoint-3 (integrated chain) screens, their extractor and cohorts.

Offline: constructed bundles (not simulation runs) and the real parser and
prerequisite checks. Nothing here runs the simulation or a held seed.
"""
from __future__ import annotations

import copy
import importlib.util
import json
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def S():
    path = ROOT / "scripts" / "productive_recovery_screens.py"
    spec = importlib.util.spec_from_file_location("productive_recovery_screens_cp3_under_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# --- Constructed bundles ------------------------------------------------------------

TURNS = 3
N = 3                                                            # regions
DEMAND = [10.0, 4.0, 5.0]                                        # per region, every turn
SUFFICIENCY = [[0.5, 1.0, 0.8], [1.2, 0.25, 0.9], [0.8, 2.0, 0.7]]   # after relief, per turn and region
NATIVE_COUNT = [12, 5, 6]                                        # Phase-2 alive per region (every turn)
L2_SHORT = [2.5, 1.5, 0.5]                                       # L2's shortfall in a scarce region-turn
PRICED = [2.0, 1.0, 4.0]                                         # priced-out persons per pilot region-turn
#: Pilot region-turns under paid_work: region -> turns. CH_unpaid has a pilot region
#: (2) that CH lacks, and lacks one (1) that CH has.
PILOTS = {"C0": {0: (1, 2, 3)}, "CH": {0: (1, 2, 3), 1: (2, 3)}, "CH_unpaid": {0: (1, 2, 3), 2: (3,)},
          "CH_cut": {0: (1, 2, 3), 1: (2, 3)}, "CH_free": {0: (1, 2, 3), 1: (2, 3)}, "CH_L2": {}}
#: Granary condition per turn (CH_cut repairs less).
GRANARY = {"CH_cut": [0.4, 0.5, 0.6]}
GRANARY_DEFAULT = [0.5, 0.6, 0.7]
#: The woodcutting home region per arm (CH_cut's crews come from another region).
HOME = {"CH_cut": 2}


def _provisioning(mode, rid):
    priced = 0.0 if mode == "free_exchange" else PRICED[rid]
    paid = 0.0 if mode == "free_exchange" else 1000.0
    return {"region": float(rid), "mode": 0.0, "persons": 10.0, "children": 4.0, "rations": 9.0,
            "fed_fair": 8.0, "deficit": 0.6, "priced_out_households": 1.0 if priced else 0.0,
            "priced_out_persons": priced, "priced_out_children": priced / 2, "priced_out_deficit": priced / 4,
            "offer_short_persons": 0.0, "offer_short_children": 0.0, "offer_short_deficit": 0.0,
            "withheld_dead_persons": 0.0, "withheld_dead_children": 0.0, "withheld_dead_deficit": 0.0,
            "free_given": 2.0, "own_eaten_milli": 3000.0, "sold_milli": 1500.0, "paid_milli": paid,
            "credited_milli": paid, "refunded_milli": 0.0}


def _l2_row(rid, turn):
    s = SUFFICIENCY[turn - 1][rid]
    short = L2_SHORT[rid]
    return {"region": rid, "scarce": 1, "phase2_alive": NATIVE_COUNT[rid], "alive": NATIVE_COUNT[rid],
            "households": 3, "sufficiency": s, "rations_available": 4.0, "relief_available": 0.0,
            "allocated": NATIVE_COUNT[rid] - short, "unallocated": 0.0, "relief_to_targeted": 0.0,
            "shortfall": short, "below_floor": 1, "fully_fed": 1, "min_ration": 0.2, "max_ration": 1.0,
            "people_poorer_half": 2, "shortfall_poorer_half": short / 2, "people_richer_half": 2,
            "shortfall_richer_half": short / 2, "children": 1, "shortfall_children": 0.1}


def _counters(name, mode):
    if name == "repair_projects":
        return {"stalled_no_timber": 9 if mode == "cut" else 7, "wages_milli": 1500, "timber_used": 4.0,
                "income_replaced": 0.2}
    if name == "timber_supply":
        cut = mode == "cost_only"
        return {"launched": 2, "ended": 2, "cut": 0.0 if cut else 6.0, "delivered": 0.0 if cut else 5.0,
                "lost": 0.0 if cut else 0.05, "away_delivered": 2.0, "wages_milli": 4500,
                "ended_wages_milli": 4000, "ended_person_turns": 8, "ended_away": 3.0, "income_withheld": 0.4}
    if name == "recovery_crews":
        paid = mode == "paid"
        return {"granary_wages_milli": 2000 if paid else 0, "granary_sunk_milli": 0 if paid else 2000,
                "granary_coin_cost_milli": 2000, "income_replaced": 0.3}
    if name == "remittances":
        return {"credited_milli": 800, "fee_milli": 150, "turns": 3}
    return {}


def _bundle(S, arm, *, drop=None, rename=None, leak=False):
    """A three-turn, three-region bundle for ``arm`` (``drop``: a package left out of
    every snapshot; ``rename``: (package, counter) recorded under an undeclared name;
    ``leak``: a retail record in an arm without retail)."""
    cp = S.CP3
    flags = cp.ARMS[arm][0]
    expected = S.expected_packages(flags, cp)
    options = S.expected_options(flags, cp)
    mode = expected.get("household_retail")
    provisioned = mode in S.PROVISIONED_MODES
    pilots = PILOTS[arm] if mode else {}
    granary = GRANARY.get(arm, GRANARY_DEFAULT)
    home = HOME.get(arm, 1)
    sums = dict.fromkeys(S.CHECKED_SUMS, 0.0)
    cells = 0
    hist = []
    for turn in range(1, TURNS + 1):
        here = [rid for rid, turns in sorted(pilots.items()) if turn in turns]
        food = [{"region_id": i, "model_population": 10, "native_count": NATIVE_COUNT[i],
                 "native": {"demand": DEMAND[i], "transport_net": 0.5, "sufficiency": SUFFICIENCY[turn - 1][i]},
                 "sufficiency_after_relief": SUFFICIENCY[turn - 1][i]} for i in range(N)]
        scarce = [i for i in range(N) if SUFFICIENCY[turn - 1][i] < 1.0 and not (provisioned and i in here)]
        liv = {"schema_version": 1}
        for name, pmode in expected.items():
            rec = {"schema_version": 1, "source_turn": turn - 1,
                   "counters": _counters(name, "cut" if arm == "CH_cut" and name == "repair_projects" else pmode)}
            if name == "food_allocation":
                rec.update(regime=pmode, stage="L2", totals={}, regions=[_l2_row(i, turn) for i in scarce],
                           sample=[])
            elif pmode is not None:
                rec["mode"] = pmode
            if name == "workshops":
                rec.update(sites=[{"site": 0, "status": "open", "asset": "open", "condition": 0.9 - 0.1 * turn},
                                  {"site": 1, "status": "open", "asset": "building", "condition": 1.0}],
                           receipts=[{"allocated": 1.0, "realized": 1.0, "region_craft_output": 2.0,
                                      "paid": {"upkeep": 3}, "craft_ceiling": 2.0, "asset": "open"}])
            elif name == "timber_stock":
                rec["totals"] = {"extraction": 1.5, "regrowth": 0.5, "cleared": 0.0, "overdraft": 0.0,
                                 "capped_slots": 0, "stock": 50.0, "capacity": 100.0}
            elif name == "timber_supply":
                stage = ("outbound", "cutting", "returning")[turn - 1]
                rec["receipts"] = [{"turn": turn - 1, "eid": 0, "home": home, "stage": stage,
                                    "away_delivered": 1.0 if turn < 3 else 0.0,
                                    "stock_after": (60.0 if pmode == "supply" else 90.0) if turn == 2 else None,
                                    "capacity": 100.0 if turn == 2 else None}]
            elif name == "household_retail":
                frames = []
                for rid in here:
                    prov = _provisioning(mode, rid) if provisioned else None
                    if prov:
                        for k in S.CHECKED_SUMS:
                            sums[k] += prov[k]
                    frames.append({"region": rid, "opened_turn": 0, "open_milli": 0, "close_milli": 0,
                                   "goods_close": [0] * 5, "owners": 3, "flows": {}, "commons": {},
                                   "price_milli": 250, "free_rations": 2.0, "phase2": None, "provisioning": prov,
                                   "would_be": None, "income_replaced": 0.5 if mode == "retail" else None,
                                   "income_rows": 3, "merchant_food_departing": 0.5,
                                   "owned_food_unloadable_milli": 2000})
                cells += len(here)
                counters = {"turns_settled": turn, "pilot_region_turns": cells,
                            **{k: int(v) for k, v in sums.items() if v}}
                if mode == "retail":
                    counters["procurement_credited_milli"] = 500
                rec.update(boundary=options["household_retail"]["boundary"], regions=frames, money={}, income={},
                           sample=[], counters=counters,
                           income_replaced_total=0.5 * cells if mode == "retail" else 0.0)
            if rename and rename[0] == name:
                rec["counters"] = {**rec["counters"], rename[1]: 1}
            liv[name] = rec
        if leak:
            liv["household_retail"] = {"schema_version": 1, "mode": "retail", "boundary": "paid_work",
                                       "source_turn": turn - 1, "regions": [], "counters": {}}
        if drop:
            liv.pop(drop, None)
        hist.append({"turn": turn,
                     "civ_stats": {"A": {"population": 10 + turn, "treasury": 5.0, "gini": 0.3},
                                   "B": {"population": 0, "treasury": 0.0, "gini": 0.0}},
                     "grain_reserves": {"storage": {"assets": [{"capacity": 10.0, "condition": granary[turn - 1]},
                                                               {"capacity": 0.0, "condition": 0.2}]}},
                     "food_accounting": {"source_turn": turn - 1, "regions": food},
                     "livelihoods": liv})
    world = {"regions": [{"stockpile": {"goods": {"timber": 1.0}}} for _ in range(N)],
             "grain_reserves": {"storage": {"assets": [{"capacity": 10.0, "condition": granary[-1]}]}},
             "livelihoods": {"workshops": {"sites": [{"status": "open", "asset": "open", "condition": 0.6}]}}}
    return {"history": hist, "world_state": world, "metadata": {"generated_at": f"{arm}-now"}}


@pytest.fixture
def short(S, monkeypatch):
    monkeypatch.setattr(S.CP3, "TURNS", TURNS)
    return S


def _extract(S, bundle, arm):
    return S.extract_cp3(bundle, S.CP3.ARMS[arm][0], S.declared_counters_cp3())


# --- Arms, flags and controls -------------------------------------------------------

def test_base_and_arms_are_the_preregistered_ones(S):
    base = ["--turns", "200", "--agents", "hybrid", "--simulate-only", "--grain-reserves", "--public-grain-shipments",
            "--scholarship", "--techniques", "--academy-services", "--grain-storage", "--food-allocation",
            "--workshops", "--operating-wear", "--repair-projects", "--timber-stock"]
    retail = ["--household-retail", "--household-retail-boundary", "paid_work"]
    chain = ["--timber-supply", "--recovery-crews", "--remittances"]
    assert S.CP3.BASE == base and S.CP3.RETAIL == retail and S.CP3.CHAIN == chain
    assert S.CP3.PROCEDURAL == ["--worldgen", "procedural", "--regions", "32", "--civs", "10"]
    assert S.CP3.ARMS == {
        "C0": (retail, None),
        "CH": (retail + chain, "CH_unpaid"),
        "CH_unpaid": (retail + ["--timber-supply", "--recovery-crews", "--recovery-crew-mode", "unpaid",
                                "--remittances"], "C0"),
        "CH_cut": (retail + ["--timber-supply", "--timber-supply-mode", "cost_only", "--recovery-crews",
                             "--remittances"], "CH"),
        "CH_free": (retail + ["--household-retail-mode", "free_exchange"] + chain, "CH"),
        "CH_L2": (chain, "CH"),
    }
    # C0's whole command line is the preregistered base.
    assert [*S.CP3.BASE, *S.CP3.ARMS["C0"][0]] == base + retail
    assert S.CP3.PREREGISTRATION.name == "productive-recovery-screens-cp3.md"
    assert (S.CP3.CHECKPOINT, S.CP3.ROOT, S.CP3.TURNS, S.CP3.IDENTITY) == (3, "C0", 200, None)
    assert S.CHECKPOINTS == {1: S.CP1, 2: S.CP2, 3: S.CP3}
    # Checkpoints 1 and 2 keep their own arms and bases.
    assert len(S.ARMS) == 14 and len(S.CP2.ARMS) == 8 and "--household-retail" not in S.CP2.BASE


def test_every_arm_parses_and_passes_the_livelihoods_prerequisites(S):
    from chronicler.main import _build_parser
    parser = _build_parser()
    for arm, (flags, _control) in S.CP3.ARMS.items():
        parser.parse_args(["--seed", "5", *S.CP3.BASE, *flags])
        parser.parse_args(["--seed", "19", *S.CP3.BASE, *S.CP3.PROCEDURAL, *flags])
    S.check_arm_flags(S.CP3)      # configure_livelihoods on a hybrid world: modes and boundary as expected
    packages = lambda arm: S.expected_packages(S.CP3.ARMS[arm][0], S.CP3)     # noqa: E731
    options = lambda arm: S.expected_options(S.CP3.ARMS[arm][0], S.CP3)       # noqa: E731
    reference = {"food_allocation": "floor_means", "workshops": "operate", "operating_wear": None,
                 "repair_projects": "repair", "timber_stock": None}
    chain = {"timber_supply": "supply", "recovery_crews": "paid", "remittances": "send"}
    assert packages("C0") == {**reference, "household_retail": "retail"}
    assert packages("CH") == {**reference, "household_retail": "retail", **chain}
    assert packages("CH_unpaid") == {**reference, "household_retail": "retail", **chain, "recovery_crews": "unpaid"}
    assert packages("CH_cut") == {**reference, "household_retail": "retail", **chain, "timber_supply": "cost_only"}
    assert packages("CH_free") == {**reference, "household_retail": "free_exchange", **chain}
    assert packages("CH_L2") == {**reference, **chain}
    for arm in ("C0", "CH", "CH_unpaid", "CH_cut", "CH_free"):
        assert options(arm) == {"household_retail": {"boundary": "paid_work"}}, arm
    assert options("CH_L2") == {}


def test_a_prerequisite_failure_is_named(S, monkeypatch):
    monkeypatch.setattr(S.CP3, "BASE", [f for f in S.CP3.BASE if f != "--food-allocation"])
    with pytest.raises(SystemExit, match="arm C0: --household-retail requires --agents hybrid and --food-allocation"):
        S.check_arm_flags(S.CP3)
    monkeypatch.setattr(S.CP3, "BASE", [f for f in S.CP3.BASE if f != "--timber-stock"] + ["--food-allocation"])
    with pytest.raises(SystemExit, match="arm CH: --timber-supply requires"):
        S.check_arm_flags(S.CP3)


def test_each_control_exists_and_leads_to_the_root(S, monkeypatch):
    for arm, (_flags, control) in S.CP3.ARMS.items():
        assert control is None or control in S.CP3.ARMS, arm
    S.check_extractor(S.CP3)
    monkeypatch.setitem(S.CP3.ARMS, "CH", (S.CP3.ARMS["CH"][0], "CH_none"))
    with pytest.raises(SystemExit, match="arm CH: unknown control CH_none"):
        S.check_extractor(S.CP3)


def test_a_cycle_of_controls_is_refused(S, monkeypatch):
    monkeypatch.setitem(S.CP3.ARMS, "CH_unpaid", (S.CP3.ARMS["CH_unpaid"][0], "CH"))
    with pytest.raises(SystemExit, match="do not lead to the root C0"):
        S.check_extractor(S.CP3)


# --- Seeds --------------------------------------------------------------------------

def test_seed_cohorts_are_disjoint_from_every_other_cohort(S):
    S.check_seeds(S.CP3)
    assert S.CP3.PILOT == {"template": (5,), "procedural": (19,)}
    assert S.CP3.HELD == {"template": tuple(range(721, 727)), "procedural": tuple(range(821, 827))}
    earlier_t = {2, *range(101, 107), *range(301, 307), *range(501, 507)}
    earlier_p = {*range(201, 207), *range(401, 407), *range(601, 607)}
    cp1_t, cp1_p = set(range(701, 707)), set(range(801, 807))
    cp2_t, cp2_p = set(range(711, 717)), set(range(811, 817))
    dev_t, dev_p = {1, 3, 7, 9, 11, 23, 42}, {7, 11, 13, 17, 21, 31, 302, 303}
    for cohort in (S.CP3.PILOT, S.CP3.HELD):
        assert not set(cohort["template"]) & (earlier_t | cp1_t | cp2_t | dev_t | {12, 13, 14})
        assert not set(cohort["procedural"]) & (earlier_p | cp1_p | cp2_p | dev_p)
    assert not set(S.CP3.PILOT["template"]) & set(S.CP3.HELD["template"])
    assert not set(S.CP3.PILOT["procedural"]) & set(S.CP3.HELD["procedural"])
    assert S.CP3.NEVER_RUN["template"] == earlier_t | cp1_t | cp2_t
    assert S.CP3.NEVER_RUN["procedural"] == earlier_p | cp1_p | cp2_p
    assert S.CP3.RESERVED == {"template": frozenset(), "procedural": frozenset()}
    assert S.CP3.PRIOR_HELD == (S.HELD, S.CP2.HELD)            # checkpoints 1 and 2's held cohorts
    assert S.CP3.DEVELOPMENT == {"template": frozenset(dev_t), "procedural": frozenset(dev_p)}
    # Checkpoint 3's held cohort is the cohort checkpoints 1 and 2 reserved.
    assert set(S.CP3.HELD["template"]) <= S.CP2.RESERVED["template"] <= S.RESERVED["template"]
    assert set(S.CP3.HELD["procedural"]) <= S.CP2.RESERVED["procedural"] <= S.RESERVED["procedural"]


def test_an_overlapping_or_unlisted_seed_is_refused(S, monkeypatch):
    monkeypatch.setitem(S.CP3.HELD, "template", (713, 722))
    with pytest.raises(SystemExit, match=r"template held seeds \[713\] are in the earlier cohorts"):
        S.check_seeds(S.CP3)
    monkeypatch.setitem(S.CP3.HELD, "template", (703, 722))
    with pytest.raises(SystemExit, match=r"template held seeds \[703\] are in the earlier cohorts"):
        S.check_seeds(S.CP3)
    monkeypatch.setitem(S.CP3.HELD, "template", tuple(range(721, 727)))
    monkeypatch.setitem(S.CP3.PILOT, "procedural", (21,))
    with pytest.raises(SystemExit, match=r"procedural pilot seeds \[21\] are in the development worlds"):
        S.check_seeds(S.CP3)
    monkeypatch.setitem(S.CP3.PILOT, "procedural", (19,))
    monkeypatch.setitem(S.CP3.NEVER_RUN, "procedural", S.CP3.NEVER_RUN["procedural"] - {815})
    with pytest.raises(SystemExit, match=r"procedural: earlier checkpoint's held seeds \[815\] not in NEVER_RUN"):
        S.check_seeds(S.CP3)


def test_jobs_cover_exactly_the_cohort(S):
    jobs = S.jobs_for("pilot", "all", list(S.CP3.ARMS), S.CP3)
    assert len(jobs) == 12
    assert {(j[1], j[2]) for j in jobs} == {("t", 5), ("p", 19)}
    assert all(j[3] == S.CP3.PROCEDURAL for j in jobs if j[1] == "p") and all(j[3] == [] for j in jobs if j[1] == "t")
    held = S.jobs_for("held", "all", list(S.CP3.ARMS), S.CP3)
    assert len(held) == 72
    assert sorted({j[2] for j in held if j[1] == "t"}) == list(range(721, 727))
    assert sorted({j[2] for j in held if j[1] == "p"}) == list(range(821, 827))


def test_the_committed_preregistration_is_frozen(S):
    # The lead froze checkpoint 3's preregistration before the held run.
    assert S.preregistration_frozen(S.CP3.PREREGISTRATION)
    status = next(line for line in S.CP3.PREREGISTRATION.read_text().splitlines() if line.startswith("Status:"))
    assert "FROZEN" in status and "DRAFT" not in status


def test_a_held_run_is_refused_while_its_preregistration_is_a_draft(S, tmp_path, monkeypatch):
    # The refusal reads checkpoint 3's own file; a draft refuses.
    draft = tmp_path / "draft.md"
    draft.write_text("# x\n\nStatus: **DRAFT** (not frozen).\n")
    assert not S.preregistration_frozen(draft)
    real = S.preregistration_frozen
    seen = []
    monkeypatch.setattr(S, "preregistration_frozen", lambda path: seen.append(path) or real(draft))
    called = []
    monkeypatch.setattr(S, "simulate", lambda cmd: called.append(cmd))
    with pytest.raises(SystemExit, match="held run refused: docs/superpowers/progress/"
                                         "productive-recovery-screens-cp3.md is not marked FROZEN"):
        S.main(["run", str(tmp_path / "out"), "--checkpoint", "3", "--cohort", "held", "--arms", "C0"])
    assert seen == [S.CP3.PREREGISTRATION] and called == [] and not (tmp_path / "out").exists()


# --- Extractor validation -------------------------------------------------------------

def test_the_extractor_validates_against_the_source(S, monkeypatch):
    S.check_extractor(S.CP3)
    declared = S.declared_counters_cp3()
    for name, keys in S.CP3.OUTCOMES.items():
        assert set(keys) <= declared[name], name
    assert set(S.CP3.REGION_RETAIL) <= set(S.RETAIL_SUMS)
    monkeypatch.setitem(S.CP3.OUTCOMES, "remittances", ("credited_milli", "remitted_milli"))
    with pytest.raises(SystemExit, match="remittances.remitted_milli is not a declared counter"):
        S.check_extractor(S.CP3)


@pytest.mark.parametrize("name, value, match", [
    ("OPTIONS", {}, "household_retail has a registered choice the screen does not check: household_retail_boundary"),
    ("MODE_KEYS", {}, "food_allocation: its mode is recorded as 'regime', the screen reads 'mode'"),
    ("REGION_RETAIL", ("persons", "priced_out_people"), "per-region retail column priced_out_people is not in"),
])
def test_an_unchecked_choice_or_column_is_refused(S, monkeypatch, name, value, match):
    monkeypatch.setattr(S.CP3, name, value)
    with pytest.raises(SystemExit, match=match):
        S.check_extractor(S.CP3)


def test_a_mode_option_the_screen_does_not_check_is_refused(S, monkeypatch):
    monkeypatch.setitem(S.CP3.PACKAGES, "--recovery-crews", ("recovery_crews", None, None))
    with pytest.raises(SystemExit, match="recovery_crews has a registered choice the screen does not check: "
                                         "recovery_crew_mode"):
        S.check_extractor(S.CP3)
    monkeypatch.setitem(S.CP3.PACKAGES, "--recovery-crews", ("recovery_crews", "--recovery-crew-mode", "unpaid"))
    with pytest.raises(SystemExit, match="--recovery-crew-mode: default 'unpaid'"):
        S.check_extractor(S.CP3)


def test_a_record_field_the_source_does_not_declare_is_refused(S, monkeypatch):
    monkeypatch.setitem(S.FIELDS_READ_CP3, ("timber_supply_state", "ExpeditionReceipt"), {"home", "distance"})
    with pytest.raises(SystemExit, match="ExpeditionReceipt.distance is not a field"):
        S.check_extractor(S.CP3)
    monkeypatch.setitem(S.FIELDS_READ_CP3, ("timber_supply_state", "ExpeditionReceipt"), {"home"})
    monkeypatch.setitem(S.FIELDS_READ_CP3, ("food_accounting", "RegionFood"), {"region_id", "shortfall"})
    with pytest.raises(SystemExit, match="RegionFood.shortfall is not a field"):
        S.check_extractor(S.CP3)
    monkeypatch.setitem(S.FIELDS_READ_CP3, ("food_accounting", "RegionFood"), {"region_id"})
    monkeypatch.setitem(S.VALUES_READ_CP3, ("timber_supply_state", "STAGES"), {"felling"})
    with pytest.raises(SystemExit, match="timber_supply_state.STAGES does not declare 'felling'"):
        S.check_extractor(S.CP3)


def test_an_undeclared_comparison_is_refused(S, monkeypatch):
    monkeypatch.setattr(S.CP3, "PAIRED", [*S.CP3.PAIRED, ("x", "CH_free", "C0", lambda r: 0)])
    with pytest.raises(SystemExit, match="CH_free - C0 is not a declared comparison"):
        S.check_extractor(S.CP3)


def test_the_primaries_and_comparisons_are_the_preregistered_ones(S):
    primaries = [label for label, *_ in S.CP3.PAIRED if label.startswith("[primary]")]
    assert primaries == ["[primary] CH priced-out person-turns per pilot person-turn in the pilot regions of "
                         "either arm (CH - CH_unpaid)",
                         "[primary] CH granary mean condition, run mean (CH - CH_cut)"]
    pairs = {(a, c) for _l, a, c, _f in S.CP3.PAIRED if c}
    assert pairs == {("CH", "CH_unpaid"), ("CH", "CH_cut"), ("CH", "CH_free"), ("CH", "CH_L2"), ("CH", "C0")}
    alone = {a for _l, a, c, _f in S.CP3.PAIRED if c is None}
    assert alone == set(S.CP3.ARMS)                              # pilot coverage of every arm
    assert S.CP3.REGION_SETS == (("CH", "CH_unpaid"), ("CH", "CH_free"), ("CH", "CH_L2"), ("CH", "C0"))
    assert S.CP3.HOME_SET == ("CH", "CH_cut")


# --- Extraction of constructed bundles ------------------------------------------------

def test_a_constructed_chain_bundle_extracts(short):
    S = short
    out, problems = _extract(S, _bundle(S, "CH"), "CH")
    assert problems == []
    assert out["packages"]["remittances"] == "send" and out["packages"]["household_retail"] == "retail"
    totals = out["region_totals"]
    assert totals["pilot_turns"] == [3, 2, 0] and out["retail"]["pilot_region_turns"] == 5
    # Per-region retail sums over the arm's own pilot region-turns.
    assert totals["retail_priced_out_persons"] == pytest.approx([6.0, 2.0, 0.0])
    assert totals["retail_priced_out_children"] == pytest.approx([3.0, 1.0, 0.0])
    assert totals["retail_persons"] == pytest.approx([30.0, 20.0, 0.0])
    # Ration shortfall: retail rows in pilot region-turns, L2's scarce rows elsewhere.
    assert totals["ration_short"] == pytest.approx([3.0, 2.0, 1.5])
    assert totals["food_gap"] == pytest.approx([7.0, 3.0, 3.0])
    assert out["granary"]["run_mean"] == pytest.approx(0.6) and out["granary"]["end"] == pytest.approx(0.7)
    assert out["workshop"]["run_mean"] == pytest.approx(0.7) and out["lump_repairs"] == 0
    ts = out["ts"]
    assert ts["homes"] == [1] and ts["min_stock_share"] == pytest.approx(0.6)
    # Away on source turns 0 and 1 in region 1: shortfall 0 + 3 of demand 8.
    assert (ts["away_cells"], ts["away_shortfall"], ts["away_demand"]) == (2, 3.0, 8.0)
    assert out["income_replaced"] == pytest.approx(2.5)
    assert "digest" not in out                                     # no identity control in checkpoint 3
    assert out["pk"]["remittances"]["credited_milli"] == 800 and out["pk"]["remittances"]["rows_absent"] == 0
    assert S._wages(out) == pytest.approx((1500 + 2000 + 4500) / 1000)
    assert S._money_cp3(out) == pytest.approx(8.0 + 0.8 + 0.5 - 2.5)


def test_the_controls_extract_with_structural_zeros(short):
    S = short
    l2, problems = _extract(S, _bundle(S, "CH_L2"), "CH_L2")
    assert problems == []
    assert "household_retail" not in l2["packages"] and l2["income_replaced"] == 0.0
    assert l2["region_totals"]["pilot_turns"] == [0, 0, 0] and l2["retail"]["pilot_region_turns"] == 0
    assert l2["region_totals"]["retail_priced_out_persons"] == [0.0, 0.0, 0.0]
    assert S._money_cp3(l2) == pytest.approx(8.0 + 0.8)             # no procurement, nothing replaced
    c0, problems = _extract(S, _bundle(S, "C0"), "C0")
    assert problems == []
    assert "ts" not in c0 and S._z(c0, "timber_supply", "delivered") == 0.0
    assert S._wages(c0) == pytest.approx(1.5) and S._money_cp3(c0) == pytest.approx(1.5 + 0.5 - 1.5)
    free, problems = _extract(S, _bundle(S, "CH_free"), "CH_free")
    assert problems == [] and free["retail"]["priced_out_persons"] == 0 and free["income_replaced"] == 0.0
    cut, problems = _extract(S, _bundle(S, "CH_cut"), "CH_cut")
    assert problems == [] and cut["ts"]["homes"] == [2] and cut["ts"]["min_stock_share"] == pytest.approx(0.9)
    assert cut["granary"]["run_mean"] == pytest.approx(0.5)


@pytest.mark.parametrize("label, arm, kwargs, match", [
    ("missing package", "CH", {"drop": "remittances"}, "packages .* recorded, expected exactly"),
    ("leaked retail", "CH_L2", {"leak": True},
     "household_retail: recorded at turns \\[1, 2, 3\\] in an arm without it"),
    ("renamed counter", "CH", {"rename": ("remittances", "remitted_milli")},
     "remittances: undeclared counters \\['remitted_milli'\\]"),
    ("no L2 frame", "CH", {"drop": "food_allocation"}, "food_allocation: frame missing or malformed"),
])
def test_a_missing_or_malformed_outcome_is_named(short, label, arm, kwargs, match):
    S = short
    _out, problems = _extract(S, _bundle(S, arm, **kwargs), arm)
    assert any(re.search(match, p) for p in problems), (label, problems)


def test_other_malformed_records_are_named(short, tmp_path):
    S = short
    cases = {}
    b = _bundle(S, "CH")
    b["history"][-1]["livelihoods"]["household_retail"]["boundary"] = "market"
    cases["wrong boundary"] = (b, "CH", "household_retail: boundary 'market', expected 'paid_work'")
    b = _bundle(S, "CH_unpaid")
    b["history"][-1]["livelihoods"]["recovery_crews"]["mode"] = "paid"
    cases["wrong crew mode"] = (b, "CH_unpaid", "recovery_crews: mode 'paid', expected 'unpaid'")
    b = _bundle(S, "CH")
    b["history"][-1]["livelihoods"]["remittances"]["source_turn"] = 0
    cases["stale remittances"] = (b, "CH", "remittances: source_turn 0 is not the completed turn")
    b = _bundle(S, "CH")
    b["history"][1]["livelihoods"]["timber_supply"]["receipts"] = None
    cases["no woodcutting receipts"] = (b, "CH", "timber_supply: receipts missing at turns \\[2\\]")
    b = _bundle(S, "CH")
    b["history"][0]["grain_reserves"] = {}
    cases["no granaries"] = (b, "CH", "granary storage missing at turns \\[1\\]")
    b = _bundle(S, "CH")
    b["history"][2]["livelihoods"]["workshops"]["receipts"] = None
    cases["no workshop receipts"] = (b, "CH", "workshop sites or receipts missing at turns \\[3\\]")
    b = _bundle(S, "CH")
    b["history"][1]["livelihoods"]["household_retail"]["regions"][1]["provisioning"]["priced_out_persons"] = 0.0
    cases["frames disagree with counters"] = (b, "CH", "frames sum priced_out_persons to 7.0, the counter has 8")
    b = _bundle(S, "CH")
    b["history"][1]["livelihoods"]["household_retail"]["regions"] = None
    cases["unobserved retail frame"] = (b, "CH", "household_retail: frame missing or malformed at turns \\[2\\]")
    b = _bundle(S, "CH")
    b["history"][0]["food_accounting"]["regions"][2]["sufficiency_after_relief"] = None
    cases["missing food row"] = (b, "CH", "food accounting missing or incomplete at turns \\[1\\]")
    b = _bundle(S, "CH")
    b["history"][-1]["livelihoods"]["recovery_crews"]["counters"]["granary_wages_milli"] = float("nan")
    cases["NaN counter"] = (b, "CH", "recovery_crews: non-numeric counters")
    b = _bundle(S, "C0")
    b["history"] = b["history"][:2]
    cases["short run"] = (b, "C0", "snapshots are not turns 1..3")
    for label, (bundle, arm, match) in cases.items():
        _out, problems = _extract(S, bundle, arm)
        assert any(re.search(match, p) for p in problems), (label, problems)
    # A snapshot without L3 totals would read as no extraction: it is named.
    b = _bundle(S, "CH")
    b["history"][1]["livelihoods"]["timber_stock"].pop("totals")
    _out, problems = _extract(S, b, "CH")
    assert "timber_stock: totals missing at turns [2]" in problems
    # Through the metrics row too, with the shared metrics' own check when no snapshot
    # holds an L3 record at all.
    path = tmp_path / "chronicle_bundle.json"
    path.write_text(json.dumps(b))
    row = S.metrics_row_cp3(path, S.CP3.ARMS["CH"][0])
    assert row["rc"] == 3 and "timber_stock: totals missing at turns [2]" in row["error"]
    b = _bundle(S, "CH", drop="timber_stock")
    path.write_text(json.dumps(b))
    row = S.metrics_row_cp3(path, S.CP3.ARMS["CH"][0])
    assert row["rc"] == 3 and "timber_stock: no totals in any snapshot" in row["error"]


# --- Running: a missing outcome exits with code 3 -------------------------------------

def _arm_of(S, cmd):
    """The arm whose flags a runner command carries (after the shared and world flags)."""
    start = 5 + len(S.CP3.BASE)
    assert cmd[5:start] == S.CP3.BASE
    if cmd[start:start + len(S.CP3.PROCEDURAL)] == S.CP3.PROCEDURAL:
        start += len(S.CP3.PROCEDURAL)
    flags = cmd[start:cmd.index("--output")]
    (arm,) = [a for a, (f, _c) in S.CP3.ARMS.items() if f == flags]
    return arm


def _fake_simulate(S, *, drop=None):
    def simulate(cmd):
        arm = _arm_of(S, cmd)
        out = Path(cmd[cmd.index("--output") + 1]).parent
        bundle = _bundle(S, arm, drop=drop if arm == "CH" else None)
        (out / "chronicle_bundle.json").write_text(json.dumps(bundle))
        return subprocess.CompletedProcess(cmd, 0, "", "")
    return simulate


def _stub_identity(out):
    (out / "source.txt").write_text("source test\n")
    return "source test\n"


def test_a_missing_outcome_exits_with_code_3_and_names_the_run(short, tmp_path, monkeypatch, capsys):
    S = short
    monkeypatch.setattr(S.LS, "source_identity", _stub_identity)
    monkeypatch.setattr(S, "simulate", _fake_simulate(S, drop="timber_supply"))
    out = tmp_path / "out"
    code = S.main(["run", str(out), "--checkpoint", "3", "--cohort", "pilot", "--arms", "CH,C0",
                   "--seeds", "template", "--jobs", "1"])
    assert code == 3
    rows = [json.loads(line) for line in (out / "metrics.jsonl").read_text().splitlines()]
    by = {r["arm"]: r for r in rows}
    assert by["CH"]["rc"] == 3 and "timber_supply" in by["CH"]["error"] and by["C0"]["rc"] == 0
    assert all(r["checkpoint"] == 3 for r in rows)
    assert "FAILED run CH t5 (rc 3)" in capsys.readouterr().out
    assert not (out / "runs" / "CH-t5").exists()                   # raw output deleted
    assert "checkpoint 3; cohort pilot" in (out / "source.txt").read_text()
    assert S.main(["check", "--checkpoint", "3", "--metrics", str(out / "metrics.jsonl"), "--cohort", "pilot"]) == 3
    report = "\n".join(S.report_lines(rows, S.CP3))
    assert "FAILED CH t5 (rc 3)" in report and "INCOMPLETE CH p19: not run" in report


def test_a_complete_pilot_extracts_and_reports(short, tmp_path, monkeypatch, capsys):
    S = short
    monkeypatch.setattr(S.LS, "source_identity", _stub_identity)
    monkeypatch.setattr(S, "simulate", _fake_simulate(S))
    out = tmp_path / "out"
    assert S.main(["run", str(out), "--checkpoint", "3", "--cohort", "pilot", "--jobs", "2"]) == 0
    rows = [json.loads(line) for line in (out / "metrics.jsonl").read_text().splitlines()]
    assert len(rows) == 12 and all(r["rc"] == 0 for r in rows)
    assert S.check_metrics(rows, "pilot", S.CP3) == []
    assert S.main(["check", "--checkpoint", "3", "--metrics", str(out / "metrics.jsonl"), "--cohort", "pilot"]) == 0
    assert S.check_metrics(rows, "held", S.CP3)                     # a pilot is not the held cohort
    capsys.readouterr()
    assert S.main(["report", str(out / "metrics.jsonl"), "--checkpoint", "3"]) == 0
    text = capsys.readouterr().out
    assert "Projected held run time from this pilot" in text and "for 72 runs" in text
    assert ("[primary] CH priced-out person-turns per pilot person-turn in the pilot regions of either arm "
            "(CH - CH_unpaid)") in text
    assert "[primary] CH granary mean condition, run mean (CH - CH_cut)" in text
    S.annotate_pairs_cp3(rows)
    by = {(r["arm"], r["stratum"]): r for r in rows}
    paired = {label: f for label, _a, _c, f in S.CP3.PAIRED}

    def diff(label, arm, control):
        f = paired[label]
        return f(by[(arm, "t")]) - f(by[(control, "t")])

    # CH - CH_unpaid over the pilot regions of either arm ({0, 1, 2}): CH priced out
    # 3 x 2 + 2 x 1 = 8, CH_unpaid 3 x 2 + 1 x 4 = 10 (its region 2 is in the set).
    ch, unpaid = by[("CH", "t")]["pair"]["CH|CH_unpaid"], by[("CH_unpaid", "t")]["pair"]["CH|CH_unpaid"]
    assert ch["regions"] == unpaid["regions"] == 3
    assert (ch["priced_out_persons"], unpaid["priced_out_persons"]) == (8.0, 10.0)
    assert diff("CH priced-out person-turns in the pilot regions of either arm (CH - CH_unpaid)",
                "CH", "CH_unpaid") == -2.0
    assert diff("[primary] CH priced-out person-turns per pilot person-turn in the pilot regions of either arm "
                "(CH - CH_unpaid)", "CH", "CH_unpaid") == pytest.approx(8 / 50 - 10 / 40)
    # Only region 0 is a pilot region in both arms: 6 priced out in each.
    assert (ch["both_regions"], ch["both_priced_out_persons"], unpaid["both_priced_out_persons"]) == (1, 6.0, 6.0)
    assert (ch["pilot_region_turns"], unpaid["pilot_region_turns"]) == (5.0, 4.0)
    assert ch["coverage"] == pytest.approx(5 / 9) and unpaid["coverage"] == pytest.approx(4 / 9)
    assert ch["priced_out_rate"] == pytest.approx(8 / 50) and unpaid["priced_out_rate"] == pytest.approx(10 / 40)
    # Ration shortfall over the set: CH 3 + 2 + 1.5; CH_unpaid 3 + 1.5 + (0.5 + 0.5 + 1).
    assert (ch["ration_short"], unpaid["ration_short"]) == (pytest.approx(6.5), pytest.approx(6.5))
    assert diff("CH granary-crew wages paid to named members, coins (CH - CH_unpaid)", "CH", "CH_unpaid") == 2.0
    assert diff("CH money credited to households (gross): named wages + remittances credited + procurement - "
                "income replaced by retail, coins (CH - CH_unpaid)", "CH", "CH_unpaid") == \
        pytest.approx((8.0 + 1.3 - 2.5) - (6.0 + 1.3 - 2.0))
    # The crews' withheld ordinary income and the senders' net debit, read beside it
    # (each package's own counter; structural zero in C0, which has none of them).
    own = {"CH ordinary income withheld for RS2 workshop crews' paid shares, coins (CH - CH_unpaid)": 0.2,
           "CH ordinary income withheld for PL1 woodcutters' paid shares, coins (CH - CH_unpaid)": 0.4,
           "CH ordinary income withheld for PL3 crews' paid shares (granary and workshop), coins (CH - CH_unpaid)":
               0.3,
           "CH remittance senders' net debit: credited + courier fee, coins (CH - CH_unpaid)": 0.95}
    for label, value in own.items():
        assert paired[label](by[("CH", "t")]) == pytest.approx(value), label
    for label in list(own)[1:]:
        assert paired[label](by[("C0", "t")]) == 0.0, label
    # CH - CH_cut: granary run mean 0.6 - 0.5; the woodcutting home regions of either
    # arm are {1, 2}: food shortfall 3 + 3 in both.
    assert diff("[primary] CH granary mean condition, run mean (CH - CH_cut)", "CH", "CH_cut") == pytest.approx(0.1)
    assert by[("CH", "t")]["pair"]["CH|CH_cut|homes"] == pytest.approx(6.0)
    assert by[("CH_cut", "t")]["pair"]["CH|CH_cut|homes"] == pytest.approx(6.0)
    assert diff("CH RS2 no_timber stalled project-turns (CH - CH_cut)", "CH", "CH_cut") == -2
    assert diff("CH timber delivered (CH - CH_cut)", "CH", "CH_cut") == 5.0
    # CH - CH_free: free_exchange prices nobody out.
    assert diff("CH priced-out person-turns in the pilot regions of either arm (CH - CH_free)", "CH", "CH_free") == 8.0
    # CH - CH_L2: the set is CH's own pilot regions ({0, 1}); L2's rows cover them.
    l2 = by[("CH_L2", "t")]["pair"]["CH|CH_L2"]
    assert l2["regions"] == 2 and l2["ration_short"] == pytest.approx(2.5 * 2 + 1.5)
    assert by[("CH", "t")]["pair"]["CH|CH_L2"]["ration_short"] == pytest.approx(5.0)
    assert l2["both_priced_out_persons"] is None                   # no region is a pilot region in both
    # CH - C0 over {0, 1}.
    assert diff("CH priced-out person-turns in the pilot regions of either arm (CH - C0)", "CH", "C0") == 2.0
    # Every set's size and both-arms size are reported, and both arms' coverage of the
    # CH - CH_free and CH - C0 sets (C0's set is {0, 1}, pilot in both arms: region 0).
    ch_row = by[("CH", "t")]
    assert paired["CH regions in the CH|CH_unpaid set (CH; the pilot regions of either arm)"](ch_row) == 3
    assert paired["CH regions pilot in both arms (CH; CH|CH_unpaid set)"](ch_row) == 1
    assert paired["CH regions in the CH|CH_L2 set (CH; the pilot regions of either arm)"](ch_row) == 2
    assert paired["CH regions pilot in both arms (CH; CH|CH_L2 set)"](ch_row) == 0
    c0_set = ch_row["pair"]["CH|C0"]
    assert paired["CH regions in the CH|C0 set (CH; the pilot regions of either arm)"](ch_row) == c0_set["regions"]
    assert paired["CH share of the set's region-turns that were pilot turns (CH; CH|C0 set)"](ch_row) == \
        pytest.approx(c0_set["coverage"])
    assert paired["C0 share of the set's region-turns that were pilot turns (C0; CH|C0 set)"](by[("C0", "t")]) == \
        pytest.approx(3 / (c0_set["regions"] * 3))
    assert paired["CH_free share of the set's region-turns that were pilot turns (CH_free; CH|CH_free set)"](
        by[("CH_free", "t")]) == pytest.approx(by[("CH_free", "t")]["pair"]["CH|CH_free"]["coverage"])
    assert paired["C0 pilot region-turns (C0)"](by[("C0", "t")]) == 3
    assert paired["CH_unpaid pilot regions (CH_unpaid)"](by[("CH_unpaid", "t")]) == 2
    assert paired["CH_L2 pilot region-turns (CH_L2)"](by[("CH_L2", "t")]) == 0


def test_a_failed_control_leaves_its_pair_unknown(short, tmp_path, monkeypatch):
    S = short
    monkeypatch.setattr(S.LS, "source_identity", _stub_identity)
    monkeypatch.setattr(S, "simulate", _fake_simulate(S))
    out = tmp_path / "out"
    assert S.main(["run", str(out), "--checkpoint", "3", "--cohort", "pilot", "--arms", "CH,CH_unpaid",
                   "--seeds", "template", "--jobs", "1"]) == 0
    rows = [json.loads(line) for line in (out / "metrics.jsonl").read_text().splitlines()]
    for r in rows:
        if r["arm"] == "CH_unpaid":
            r["rc"], r["error"] = 3, "constructed failure"
    S.annotate_pairs_cp3(rows)
    by = {r["arm"]: r for r in rows}
    assert by["CH"]["pair"]["CH|CH_unpaid"] is None
    text = "\n".join(S.report_lines(rows, S.CP3))
    for label in ("[primary] CH priced-out person-turns per pilot person-turn in the pilot regions of either arm "
                  "(CH - CH_unpaid)", "CH priced-out person-turns in the pilot regions of either arm (CH - CH_unpaid)"):
        assert f"| {label} | t | 5: failed" in text


def test_a_resume_before_the_first_row_checks_the_recorded_checkpoint_and_cohort(short, tmp_path, monkeypatch):
    """A run killed before its first row leaves source.txt and an empty metrics.jsonl;
    the resume must still refuse another checkpoint or cohort (the run header)."""
    S = short
    monkeypatch.setattr(S.LS, "source_identity", _stub_identity)
    monkeypatch.setattr(S, "simulate", _fake_simulate(S))
    out = tmp_path / "out"
    assert S.main(["run", str(out), "--checkpoint", "3", "--cohort", "pilot", "--arms", "C0",
                   "--seeds", "template"]) == 0
    (out / "metrics.jsonl").write_text("")                         # killed before any row
    assert S.recorded_run((out / "source.txt").read_text()) == (3, "pilot")
    with pytest.raises(SystemExit, match="started as checkpoint 3, cohort pilot, not checkpoint 1, cohort pilot"):
        S.main(["run", str(out), "--cohort", "pilot", "--arms", "W", "--seeds", "template", "--resume"])
    assert (out / "metrics.jsonl").read_text() == ""                 # nothing was run
    (out / "source.txt").write_text("source test\n")
    with pytest.raises(SystemExit, match="records no run header"):
        S.main(["run", str(out), "--checkpoint", "3", "--cohort", "pilot", "--arms", "C0", "--seeds", "template",
                "--resume"])
    # Checkpoint 1's header has no checkpoint prefix; the same rule reads it.
    assert S.recorded_run("source x\ncohort held; seeds all; arms W; jobs 3; rows already written 0\n") == (1, "held")
    assert S.recorded_run("source x\ncheckpoint 2; resumed held; seeds all\n") is None


def test_rows_of_another_checkpoint_are_refused(short, tmp_path, monkeypatch):
    S = short
    monkeypatch.setattr(S.LS, "source_identity", _stub_identity)
    monkeypatch.setattr(S, "simulate", _fake_simulate(S))
    out = tmp_path / "out"
    assert S.main(["run", str(out), "--checkpoint", "3", "--cohort", "pilot", "--arms", "C0",
                   "--seeds", "template"]) == 0
    metrics = out / "metrics.jsonl"
    with pytest.raises(SystemExit, match="holds rows of another checkpoint than 2"):
        S.main(["report", str(metrics), "--checkpoint", "2"])
    rows = [json.loads(line) for line in metrics.read_text().splitlines()]
    assert any("row of checkpoint 3" in p for p in S.check_metrics(rows, "pilot", S.CP2))
    with pytest.raises(SystemExit, match="started as checkpoint 3, cohort pilot, not checkpoint 2"):
        S.main(["run", str(out), "--checkpoint", "2", "--cohort", "pilot", "--arms", "L2", "--seeds", "template",
                "--resume"])
    # The rows are checked too: a directory whose header was rewritten still refuses them.
    source = out / "source.txt"
    source.write_text(source.read_text().replace("checkpoint 3; cohort pilot", "checkpoint 2; cohort pilot"))
    with pytest.raises(SystemExit, match="holds a row of checkpoint 3, not 2"):
        S.main(["run", str(out), "--checkpoint", "2", "--cohort", "pilot", "--arms", "L2", "--seeds", "template",
                "--resume"])
    # A checkpoint-2 row is refused by a checkpoint-3 report.
    cp2 = dict(copy.deepcopy(rows[0]), arm="L2", checkpoint=2)
    metrics.write_text(json.dumps(cp2) + "\n")
    with pytest.raises(SystemExit, match="holds rows of another checkpoint than 3"):
        S.main(["report", str(metrics), "--checkpoint", "3"])
