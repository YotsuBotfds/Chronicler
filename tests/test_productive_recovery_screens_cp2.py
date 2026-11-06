"""PL6c: the checkpoint-2 (household food retail) screens, their extractor and cohorts.

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
    spec = importlib.util.spec_from_file_location("productive_recovery_screens_cp2_under_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# --- Constructed bundles ------------------------------------------------------------

TURNS = 3
DEMAND = [[10.0, 4.0], [10.0, 4.0], [10.0, 4.0]]
SUFFICIENCY = [[0.5, 1.0], [1.2, 0.25], [0.8, 2.0]]   # after relief, per turn and region
NATIVE_COUNT = [12, 5]                                # Phase-2 alive per region (every turn)
TRANSPORT = [-1.0, 0.5]                               # net food transport per region-turn
PERSONS, RATIONS = 10.0, 9.0                          # per provisioned pilot region-turn


def _pilots(arm):
    """Pilot regions of a constructed retail arm (region 0 is the capital)."""
    return [0, 1] if "_all" in arm else [0]


def _provisioning(mode, rid):
    priced = {"retail": 2.0, "no_relief": 3.0, "free_exchange": 0.0}[mode]
    paid = 0.0 if mode == "free_exchange" else 1000.0
    return {"region": float(rid), "mode": 0.0, "persons": PERSONS, "children": 4.0, "rations": RATIONS,
            "fed_fair": 8.0, "deficit": 0.6, "priced_out_households": 1.0 if priced else 0.0,
            "priced_out_persons": priced, "priced_out_children": priced / 2, "priced_out_deficit": priced / 4,
            "offer_short_persons": 0.0, "offer_short_children": 0.0, "offer_short_deficit": 0.0,
            "withheld_dead_persons": 1.0, "withheld_dead_children": 0.0, "withheld_dead_deficit": 0.1,
            "free_given": 2.0, "own_eaten_milli": 3000.0, "sold_milli": 1500.0, "paid_milli": paid,
            "credited_milli": paid, "refunded_milli": 0.0}


def _l2_row(rid, turn):
    s = SUFFICIENCY[turn - 1][rid]
    short = 2.5 if rid == 0 else 1.5
    return {"region": rid, "scarce": 1, "phase2_alive": NATIVE_COUNT[rid], "alive": NATIVE_COUNT[rid],
            "households": 3, "sufficiency": s, "rations_available": 4.0, "relief_available": 0.0,
            "allocated": NATIVE_COUNT[rid] - short, "unallocated": 0.0, "relief_to_targeted": 0.0,
            "shortfall": short, "below_floor": 1, "fully_fed": 1, "min_ration": 0.2, "max_ration": 1.0,
            "people_poorer_half": 2, "shortfall_poorer_half": 1.0, "people_richer_half": 2,
            "shortfall_richer_half": short - 1.0, "children": 1, "shortfall_children": 0.5}


def _bundle(S, arm, *, drop=None, rename=None, perturb=False):
    """A three-turn, two-region bundle for ``arm`` (``drop``: a package left out of
    every snapshot; ``rename``: a counter recorded under an undeclared name; ``perturb``:
    a different treasury, so the trajectory differs)."""
    expected = S.expected_packages(S.CP2.ARMS[arm][0], S.CP2)
    options = S.expected_options(S.CP2.ARMS[arm][0], S.CP2)
    mode = expected.get("household_retail")
    provisioned = mode in S.PROVISIONED_MODES
    pilots = _pilots(arm) if mode else []
    hist = []
    for turn in range(1, TURNS + 1):
        food = [{"region_id": i, "model_population": 10, "native_count": NATIVE_COUNT[i],
                 "native": {"demand": DEMAND[turn - 1][i], "transport_net": TRANSPORT[i],
                            "sufficiency": SUFFICIENCY[turn - 1][i]},
                 "sufficiency_after_relief": SUFFICIENCY[turn - 1][i]} for i in range(2)]
        scarce = [i for i in range(2) if SUFFICIENCY[turn - 1][i] < 1.0 and not (provisioned and i in pilots)]
        liv = {"schema_version": 1,
               "food_allocation": {"schema_version": 1, "stage": "L2", "regime": expected["food_allocation"],
                                   "source_turn": turn - 1, "totals": {},
                                   "regions": [_l2_row(i, turn) for i in scarce], "sample": [], "counters": {}}}
        if mode:
            frames = []
            for rid in pilots:
                frames.append({"region": rid, "opened_turn": 0, "open_milli": 0, "close_milli": 0,
                               "goods_close": [0] * 5, "owners": 3, "flows": {}, "commons": {},
                               "price_milli": 250, "free_rations": 2.0, "phase2": None,
                               "provisioning": _provisioning(mode, rid) if provisioned else None,
                               "would_be": None if provisioned else {"titled_milli": 900.0, "price_milli": 250.0},
                               "income_replaced": 0.5 if mode in ("retail", "no_relief") else None,
                               "income_rows": 3, "merchant_food_departing": 0.5,
                               "owned_food_unloadable_milli": 2000 if provisioned else 0})
            cells = turn * len(pilots)
            counters = {"turns_settled": turn, "pilot_region_turns": cells}
            if provisioned:
                prov = _provisioning(mode, 0)
                for k in S.CHECKED_SUMS:
                    if prov[k]:
                        counters[k] = int(prov[k] * cells)
                if mode != "free_exchange":
                    counters["procurement_credited_milli"] = 500
            if rename:
                counters[rename] = 1
            liv["household_retail"] = {
                "schema_version": 1, "stage": "L6b", "mode": mode, "boundary": options["household_retail"]["boundary"],
                "source_turn": turn - 1, "regions": frames, "money": {}, "income": {}, "sample": [],
                "counters": counters,
                "income_replaced_total": 0.5 * cells if mode in ("retail", "no_relief") else 0.0}
        if drop:
            liv.pop(drop, None)
        treasury = 5.0 + (1.0 if perturb else 0.0) + (2.0 if provisioned else 0.0)
        hist.append({"turn": turn,
                     "civ_stats": {"A": {"population": 10 + turn + (1 if provisioned else 0), "treasury": treasury,
                                         "gini": 0.3 + (0.05 if provisioned else 0.0)},
                                   "B": {"population": 0, "treasury": 0.0, "gini": 0.0}},
                     "food_accounting": {"source_turn": turn - 1, "regions": food},
                     "livelihoods": liv})
    world = {"regions": [{"stockpile": {"goods": {"grain": 1.0}}} for _ in range(2)],
             "livelihoods": {"food_allocation": {"regime": expected["food_allocation"]}}}
    if mode:
        world["livelihoods"]["household_retail"] = {"mode": mode}
    return {"history": hist, "world_state": world, "metadata": {"generated_at": f"{arm}-now"}}


@pytest.fixture
def short(S, monkeypatch):
    monkeypatch.setattr(S.CP2, "TURNS", TURNS)
    return S


def _extract(S, bundle, arm):
    return S.extract_cp2(bundle, S.CP2.ARMS[arm][0], S.declared_counters_cp2())


# --- Arms, flags and controls -------------------------------------------------------

def test_base_and_arms_are_the_preregistered_ones(S):
    assert S.CP2.BASE == ["--turns", "200", "--agents", "hybrid", "--simulate-only", "--grain-reserves",
                          "--public-grain-shipments", "--scholarship", "--techniques", "--academy-services",
                          "--grain-storage", "--food-allocation"]
    assert S.CP2.PROCEDURAL == ["--worldgen", "procedural", "--regions", "32", "--civs", "10"]
    r = ["--household-retail"]
    mode, every = ["--household-retail-mode"], ["--household-retail-boundary", "all"]
    assert S.CP2.ARMS == {
        "L2": ([], None),
        "R_rec": (r + mode + ["record_only"], "L2"),
        "R": (r, "R_free"),
        "R_free": (r + mode + ["free_exchange"], "L2"),
        "R_norelief": (r + mode + ["no_relief"], "R"),
        "R_all": (r + every, "R_all_free"),
        "R_all_free": (r + mode + ["free_exchange"] + every, "L2"),
        "R_all_norelief": (r + mode + ["no_relief"] + every, "R_all"),
    }
    assert S.CP2.PREREGISTRATION.name == "productive-recovery-screens-cp2.md"
    assert (S.CP2.CHECKPOINT, S.CP2.ROOT, S.CP2.TURNS) == (2, "L2", 200)
    # Checkpoint 1 keeps its own arms, base and preregistration.
    assert len(S.ARMS) == 14 and S.ARMS["W"] == ([], None) and "--workshops" in S.BASE
    assert S.CHECKPOINTS == {1: S.CP1, 2: S.CP2} and S.CP1.ARMS is S.ARMS


def test_every_arm_parses_and_passes_the_livelihoods_prerequisites(S):
    from chronicler.main import _build_parser
    parser = _build_parser()
    for arm, (flags, _control) in S.CP2.ARMS.items():
        parser.parse_args(["--seed", "5", *S.CP2.BASE, *flags])
        parser.parse_args(["--seed", "19", *S.CP2.BASE, *S.CP2.PROCEDURAL, *flags])
    S.check_arm_flags(S.CP2)      # configure_livelihoods on a hybrid world: modes and boundary as expected
    packages = lambda arm: S.expected_packages(S.CP2.ARMS[arm][0], S.CP2)     # noqa: E731
    options = lambda arm: S.expected_options(S.CP2.ARMS[arm][0], S.CP2)       # noqa: E731
    assert packages("L2") == {"food_allocation": "floor_means"} and options("L2") == {}
    assert packages("R") == {"food_allocation": "floor_means", "household_retail": "retail"}
    assert options("R") == {"household_retail": {"boundary": "market"}}
    assert packages("R_rec")["household_retail"] == "record_only"
    assert packages("R_free")["household_retail"] == "free_exchange"
    assert packages("R_norelief")["household_retail"] == "no_relief"
    assert packages("R_all_norelief")["household_retail"] == "no_relief"
    assert options("R_all_free") == {"household_retail": {"boundary": "all"}}


def test_a_prerequisite_failure_is_named(S, monkeypatch):
    monkeypatch.setattr(S.CP2, "BASE", [f for f in S.CP2.BASE if f != "--food-allocation"])
    with pytest.raises(SystemExit, match="arm R: --household-retail requires --agents hybrid and --food-allocation"):
        S.check_arm_flags(S.CP2)


def test_each_control_exists_and_leads_to_the_root(S, monkeypatch):
    for arm, (_flags, control) in S.CP2.ARMS.items():
        assert control is None or control in S.CP2.ARMS, arm
    S.check_extractor(S.CP2)
    monkeypatch.setitem(S.CP2.ARMS, "R", (S.CP2.ARMS["R"][0], "R_none"))
    with pytest.raises(SystemExit, match="arm R: unknown control R_none"):
        S.check_extractor(S.CP2)


def test_a_cycle_of_controls_is_refused(S, monkeypatch):
    monkeypatch.setitem(S.CP2.ARMS, "R_free", (S.CP2.ARMS["R_free"][0], "R"))
    with pytest.raises(SystemExit, match="do not lead to the root L2"):
        S.check_extractor(S.CP2)


# --- Seeds --------------------------------------------------------------------------

def test_seed_cohorts_are_disjoint_from_every_earlier_and_reserved_cohort(S):
    S.check_seeds(S.CP2)
    assert S.CP2.PILOT == {"template": (5,), "procedural": (19,)}
    assert S.CP2.HELD == {"template": tuple(range(711, 717)), "procedural": tuple(range(811, 817))}
    earlier_t = {2, *range(101, 107), *range(301, 307), *range(501, 507)}
    earlier_p = {*range(201, 207), *range(401, 407), *range(601, 607)}
    cp1_t, cp1_p = set(range(701, 707)), set(range(801, 807))
    cp3_t, cp3_p = set(range(721, 727)), set(range(821, 827))
    for cohort in (S.CP2.PILOT, S.CP2.HELD):
        assert not set(cohort["template"]) & (earlier_t | cp1_t | cp3_t)
        assert not set(cohort["procedural"]) & (earlier_p | cp1_p | cp3_p)
    assert not set(S.CP2.PILOT["template"]) & set(S.CP2.HELD["template"])
    assert not set(S.CP2.PILOT["procedural"]) & set(S.CP2.HELD["procedural"])
    assert S.CP2.NEVER_RUN["template"] == earlier_t | cp1_t
    assert S.CP2.NEVER_RUN["procedural"] == earlier_p | cp1_p
    assert S.CP2.RESERVED == {"template": cp3_t, "procedural": cp3_p}
    assert S.CP2.PRIOR_HELD == (S.HELD,)                 # checkpoint 1's own held cohort
    assert set(S.HELD["template"]) == cp1_t and set(S.HELD["procedural"]) == cp1_p


def test_an_overlapping_or_unlisted_seed_is_refused(S, monkeypatch):
    monkeypatch.setitem(S.CP2.HELD, "template", (703, 712))
    with pytest.raises(SystemExit, match=r"template held seeds \[703\] are in the earlier cohorts"):
        S.check_seeds(S.CP2)
    monkeypatch.setitem(S.CP2.HELD, "template", tuple(range(711, 717)))
    monkeypatch.setitem(S.CP2.PILOT, "procedural", (823,))
    with pytest.raises(SystemExit, match=r"procedural pilot seeds \[823\] are in the reserved cohorts"):
        S.check_seeds(S.CP2)
    monkeypatch.setitem(S.CP2.PILOT, "procedural", (19,))
    monkeypatch.setitem(S.CP2.NEVER_RUN, "procedural", S.CP2.NEVER_RUN["procedural"] - {804})
    with pytest.raises(SystemExit, match=r"procedural: earlier checkpoint's held seeds \[804\] not in NEVER_RUN"):
        S.check_seeds(S.CP2)


def test_jobs_cover_exactly_the_cohort(S):
    jobs = S.jobs_for("pilot", "all", list(S.CP2.ARMS), S.CP2)
    assert len(jobs) == 16
    assert {(j[1], j[2]) for j in jobs} == {("t", 5), ("p", 19)}
    assert all(j[3] == S.CP2.PROCEDURAL for j in jobs if j[1] == "p") and all(j[3] == [] for j in jobs if j[1] == "t")
    held = S.jobs_for("held", "procedural", ["L2"], S.CP2)
    assert [j[2] for j in held] == list(range(811, 817)) and [j[4] for j in held] == [True] + [False] * 5


def test_a_held_run_is_refused_until_its_preregistration_is_frozen(S, tmp_path, monkeypatch):
    # The committed checkpoint-2 preregistration is a draft; checkpoint 1's freeze does not count.
    assert not S.preregistration_frozen(S.CP2.PREREGISTRATION)
    assert S.preregistration_frozen(S.PREREGISTRATION)
    called = []
    monkeypatch.setattr(S, "simulate", lambda cmd: called.append(cmd))
    with pytest.raises(SystemExit, match="held run refused: docs/superpowers/progress/"
                                         "productive-recovery-screens-cp2.md is not marked FROZEN"):
        S.main(["run", str(tmp_path / "out"), "--checkpoint", "2", "--cohort", "held", "--arms", "L2"])
    assert called == [] and not (tmp_path / "out").exists()
    # The refusal reads checkpoint 2's own file, whose status line decides.
    seen = []
    monkeypatch.setattr(S, "preregistration_frozen", lambda path: seen.append(path) or False)
    with pytest.raises(SystemExit, match="held run refused"):
        S.main(["run", str(tmp_path / "out"), "--checkpoint", "2", "--cohort", "held", "--arms", "L2"])
    assert seen == [S.CP2.PREREGISTRATION] and called == []
    assert "DRAFT" in next(line for line in S.CP2.PREREGISTRATION.read_text().splitlines()
                           if line.startswith("Status:"))


# --- Extractor validation -------------------------------------------------------------

def test_the_extractor_validates_against_the_source(S, monkeypatch):
    S.check_extractor(S.CP2)
    declared = S.declared_counters_cp2()
    assert set(S.CP2.OUTCOMES["household_retail"]) <= declared["household_retail"]
    retail = S.rust_columns(S.PROVISIONING_RS, "RETAIL_REGION_COLUMNS")
    l2 = S.rust_columns(S.PROVISIONING_RS, "REGION_COLUMNS")
    assert len(retail) == 55 and set(S.RETAIL_SUMS) <= set(retail)
    assert len(l2) == 22 and set(S.L2_COLUMNS) <= set(l2)
    monkeypatch.setitem(S.CP2.OUTCOMES, "household_retail", ("sold_milli", "food_sold_milli"))
    with pytest.raises(SystemExit, match="household_retail.food_sold_milli is not a declared counter"):
        S.check_extractor(S.CP2)


@pytest.mark.parametrize("name, value, match", [
    ("RETAIL_SUMS", ("persons", "priced_out_people"), "frame column priced_out_people is not in RETAIL_REGION_COLUMNS"),
    ("L2_COLUMNS", ("region", "rations"), "frame column rations is not in REGION_COLUMNS"),
    ("FRAME_FIELDS", ("region", "merchant_departures"), "frame field merchant_departures is not a RegionFrame field"),
    ("FOOD_FIELDS", ("demand", "transport"), "food accounting field transport is not declared"),
    ("PROVISIONED_MODES", ("retail", "free_exchange"), "household retail modes are"),
])
def test_a_column_the_source_does_not_declare_is_refused(S, monkeypatch, name, value, match):
    monkeypatch.setattr(S, name, value)
    with pytest.raises(SystemExit, match=match):
        S.check_extractor(S.CP2)


def test_an_unchecked_option_or_a_wrong_default_is_refused(S, monkeypatch):
    monkeypatch.setitem(S.CP2.OPTIONS, "--household-retail", (("--household-retail-boundary", "boundary", "all"),))
    with pytest.raises(SystemExit, match="--household-retail-boundary: default 'all'"):
        S.check_extractor(S.CP2)
    monkeypatch.setitem(S.CP2.OPTIONS, "--household-retail", ())
    with pytest.raises(SystemExit, match=r"household_retail has registered choices the screen does not check: "
                                         r"\['household_retail_boundary'\]"):
        S.check_extractor(S.CP2)


def test_an_undeclared_comparison_is_refused(S, monkeypatch):
    monkeypatch.setattr(S.CP2, "PAIRED", [*S.CP2.PAIRED, ("x", "R_norelief", "L2", lambda r: 0)])
    with pytest.raises(SystemExit, match="R_norelief - L2 is not a declared comparison"):
        S.check_extractor(S.CP2)


def test_every_identity_outcome_compares_r_rec_with_l2(S):
    ident = [(label, a, c) for label, a, c, _f in S.CP2.PAIRED if label.startswith("[identity]")]
    assert len(ident) == 17 and all((a, c) == ("R_rec", "L2") for _l, a, c in ident)
    primaries = [label for label, *_ in S.CP2.PAIRED if label.startswith("[primary]")]
    assert primaries == ["[primary] R priced-out person-turns in its pilot regions (R - R_free)",
                         "[primary] R_norelief priced-out person-turns (R_norelief - R; what relief protects)"]


# --- Extraction of constructed bundles ------------------------------------------------

def test_a_constructed_retail_bundle_extracts(short):
    S = short
    out, problems = _extract(S, _bundle(S, "R"), "R")
    assert problems == []
    assert out["packages"] == {"food_allocation": "floor_means", "household_retail": "retail"}
    rt = out["retail"]
    assert rt["pilot_region_turns"] == 3 and rt["persons"] == 30 and rt["rations"] == 27
    assert (rt["priced_out_persons"], rt["priced_out_children"], rt["priced_out_deficit"]) == (6, 3, 1.5)
    assert rt["withheld_dead_persons"] == 3 and rt["offer_short_persons"] == 0
    assert rt["owned_food_unloadable"] == pytest.approx(6.0) and rt["merchant_food_departing"] == pytest.approx(1.5)
    assert out["income_replaced"] == pytest.approx(1.5)
    totals = out["region_totals"]
    assert totals["pilot_turns"] == [3, 0]
    # Food shortfall after relief = demand x max(0, 1 - sufficiency), summed per region.
    assert totals["food_gap"] == pytest.approx([5.0 + 0.0 + 2.0, 0.0 + 3.0 + 0.0])
    # Ration shortfall: the retail rows in the pilot region (persons - rations), L2's
    # scarce rows elsewhere (region 1 is scarce at turn 2 only).
    assert totals["ration_short"] == pytest.approx([3.0, 1.5])
    assert totals["phase2_alive"] == [36, 15] and totals["transport_net"] == pytest.approx([-3.0, 1.5])
    assert out["gini"] == pytest.approx(0.35)                 # alive civilizations only
    assert out["pk"]["household_retail"]["sold_milli"] == 4500
    assert out["pk"]["household_retail"]["war_loss_milli"] == 0                    # never incremented
    assert len(out["digest"]) == 64


def test_record_only_and_l2_extract_with_structural_zeros(short):
    S = short
    rec, problems = _extract(S, _bundle(S, "R_rec"), "R_rec")
    assert problems == []
    assert rec["retail"]["pilot_region_turns"] == 3 and rec["retail"]["persons"] == 0
    assert rec["retail"]["merchant_food_departing"] == pytest.approx(1.5) and rec["income_replaced"] == 0.0
    # record_only provisions nothing: L2's frame covers the pilot region.
    assert rec["region_totals"]["ration_short"] == pytest.approx([5.0, 1.5])
    l2, problems = _extract(S, _bundle(S, "L2"), "L2")
    assert problems == []
    assert l2["packages"] == {"food_allocation": "floor_means"} and l2["income_replaced"] == 0.0
    assert l2["retail"]["pilot_region_turns"] == 0 and l2["region_totals"]["pilot_turns"] == [0, 0]
    assert S._z(l2, "household_retail", "credited_milli") == 0.0
    # The trajectory digest ignores the retail record and the run's metadata.
    assert rec["digest"] == l2["digest"]
    perturbed, _ = _extract(S, _bundle(S, "R_rec", perturb=True), "R_rec")
    assert perturbed["digest"] != l2["digest"]


def test_the_all_boundary_covers_both_regions(short):
    S = short
    out, problems = _extract(S, _bundle(S, "R_all_norelief"), "R_all_norelief")
    assert problems == []
    assert out["region_totals"]["pilot_turns"] == [3, 3] and out["retail"]["priced_out_persons"] == 18


@pytest.mark.parametrize("label, kwargs, arm, match", [
    ("missing package", {"drop": "household_retail"}, "R", "packages .* recorded, expected exactly"),
    ("leaked package", {}, "L2", "expected exactly"),
    ("renamed counter", {"rename": "food_sold_milli"}, "R", "undeclared counters"),
    ("no L2 frame", {"drop": "food_allocation"}, "R_free", "food_allocation: frame missing or malformed at turns \\[1, 2, 3\\]"),
])
def test_a_missing_or_malformed_outcome_is_named(short, label, kwargs, arm, match):
    S = short
    bundle = _bundle(S, arm, **kwargs)
    if label == "leaked package":
        bundle["history"][-1]["livelihoods"]["household_retail"] = _bundle(S, "R")["history"][-1]["livelihoods"][
            "household_retail"]
    _out, problems = _extract(S, bundle, arm)
    assert any(re.search(match, p) for p in problems), (label, problems)


def test_other_malformed_records_are_named(short):
    S = short
    cases = {}
    b = _bundle(S, "R_all")
    b["history"][-1]["livelihoods"]["household_retail"]["boundary"] = "market"
    cases["wrong boundary"] = (b, "R_all", "household_retail: boundary 'market', expected 'all'")
    b = _bundle(S, "R_free")
    b["history"][-1]["livelihoods"]["household_retail"]["mode"] = "retail"
    cases["wrong mode"] = (b, "R_free", "household_retail: mode 'retail', expected 'free_exchange'")
    b = _bundle(S, "R")
    b["history"][-1]["livelihoods"]["food_allocation"]["regime"] = "equal"
    cases["wrong regime"] = (b, "R", "food_allocation: regime 'equal', expected 'floor_means'")
    b = _bundle(S, "R")
    b["history"][-1]["livelihoods"]["household_retail"]["source_turn"] = 1
    cases["stale record"] = (b, "R", "household_retail: source_turn 1 is not the completed turn")
    b = _bundle(S, "R")
    del b["history"][1]["livelihoods"]["household_retail"]["regions"][0]["provisioning"]["priced_out_children"]
    cases["missing column"] = (b, "R", "household_retail: frame missing or malformed at turns \\[2\\]")
    b = _bundle(S, "R")
    b["history"][1]["livelihoods"]["household_retail"]["regions"] = None
    cases["unobserved frame"] = (b, "R", "household_retail: frame missing or malformed at turns \\[2\\]")
    b = _bundle(S, "R")
    b["history"][1]["livelihoods"]["household_retail"]["regions"][0]["provisioning"] = None
    cases["dropped provisioning"] = (b, "R", "2 pilot region-turns in the frames, the counter has 3")
    b = _bundle(S, "R")
    b["history"][0]["livelihoods"]["household_retail"]["regions"][0]["provisioning"]["priced_out_persons"] = 0.0
    cases["frames disagree with counters"] = (b, "R", "frames sum priced_out_persons to 4.0, the counter has 6")
    b = _bundle(S, "R")
    b["history"][0]["livelihoods"]["food_allocation"]["regions"].append(_l2_row(0, 1))
    cases["region in both frames"] = (b, "R", "also in L2's frame at turns \\[1\\]")
    b = _bundle(S, "R_rec")
    b["history"][2]["livelihoods"]["household_retail"]["regions"][0]["provisioning"] = _provisioning("retail", 0)
    cases["record_only provisions"] = (b, "R_rec", "household_retail: frame missing or malformed at turns \\[3\\]")
    b = _bundle(S, "R")
    b["history"][1]["food_accounting"]["regions"][1]["native"]["transport_net"] = None
    cases["missing transport"] = (b, "R", "food accounting missing or incomplete at turns \\[2\\]")
    b = _bundle(S, "R")
    b["history"][2]["food_accounting"]["regions"][0]["native_count"] = None
    cases["missing Phase-2 count"] = (b, "R", "food accounting missing or incomplete at turns \\[3\\]")
    b = _bundle(S, "R")
    del b["history"][-1]["livelihoods"]["household_retail"]["income_replaced_total"]
    cases["no income total"] = (b, "R", "income_replaced_total missing")
    b = _bundle(S, "R")
    b["history"][-1]["civ_stats"]["A"]["gini"] = None
    cases["no Gini"] = (b, "R", "wealth Gini missing")
    b = _bundle(S, "L2")
    b["history"] = b["history"][:2]
    cases["short run"] = (b, "L2", "snapshots are not turns 1..3")
    b = _bundle(S, "R")
    b["history"][-1]["livelihoods"]["household_retail"]["counters"]["sold_milli"] = float("nan")
    cases["NaN counter"] = (b, "R", "non-numeric counters")
    for label, (bundle, arm, match) in cases.items():
        _out, problems = _extract(S, bundle, arm)
        assert any(re.search(match, p) for p in problems), (label, problems)


# --- Running: a missing outcome exits with code 3 -------------------------------------

def _arm_of(S, cmd):
    """The arm whose flags a runner command carries (after the base and world flags)."""
    start = 5 + len(S.CP2.BASE)
    assert cmd[5:start] == S.CP2.BASE
    if cmd[start:start + len(S.CP2.PROCEDURAL)] == S.CP2.PROCEDURAL:
        start += len(S.CP2.PROCEDURAL)
    flags = cmd[start:cmd.index("--output")]
    (arm,) = [a for a, (f, _c) in S.CP2.ARMS.items() if f == flags]
    return arm


def _fake_simulate(S, *, drop=None, perturb=None):
    def simulate(cmd):
        arm = _arm_of(S, cmd)
        out = Path(cmd[cmd.index("--output") + 1]).parent
        bundle = _bundle(S, arm, drop=drop if arm == "R" else None, perturb=arm == perturb)
        (out / "chronicle_bundle.json").write_text(json.dumps(bundle))
        return subprocess.CompletedProcess(cmd, 0, "", "")
    return simulate


def _stub_identity(out):
    (out / "source.txt").write_text("source test\n")
    return "source test\n"


def test_a_missing_outcome_exits_with_code_3_and_names_the_run(short, tmp_path, monkeypatch, capsys):
    S = short
    monkeypatch.setattr(S.LS, "source_identity", _stub_identity)
    monkeypatch.setattr(S, "simulate", _fake_simulate(S, drop="household_retail"))
    out = tmp_path / "out"
    code = S.main(["run", str(out), "--checkpoint", "2", "--cohort", "pilot", "--arms", "R,L2",
                   "--seeds", "template", "--jobs", "1"])
    assert code == 3
    rows = [json.loads(line) for line in (out / "metrics.jsonl").read_text().splitlines()]
    by = {r["arm"]: r for r in rows}
    assert by["R"]["rc"] == 3 and "household_retail" in by["R"]["error"] and by["L2"]["rc"] == 0
    assert all(r["checkpoint"] == 2 for r in rows)
    assert "FAILED run R t5 (rc 3)" in capsys.readouterr().out
    assert not (out / "runs" / "R-t5").exists()                     # raw output deleted
    assert "checkpoint 2; cohort pilot" in (out / "source.txt").read_text()
    assert S.main(["check", "--checkpoint", "2", "--metrics", str(out / "metrics.jsonl"), "--cohort", "pilot"]) == 3
    report = "\n".join(S.report_lines(rows, S.CP2))
    assert "FAILED R t5 (rc 3)" in report and "INCOMPLETE R p19: not run" in report


def test_a_complete_pilot_extracts_and_reports(short, tmp_path, monkeypatch, capsys):
    S = short
    monkeypatch.setattr(S.LS, "source_identity", _stub_identity)
    monkeypatch.setattr(S, "simulate", _fake_simulate(S))
    out = tmp_path / "out"
    assert S.main(["run", str(out), "--checkpoint", "2", "--cohort", "pilot", "--jobs", "2"]) == 0
    rows = [json.loads(line) for line in (out / "metrics.jsonl").read_text().splitlines()]
    assert len(rows) == 16 and all(r["rc"] == 0 for r in rows)
    assert S.check_metrics(rows, "pilot", S.CP2) == []
    assert S.main(["check", "--checkpoint", "2", "--metrics", str(out / "metrics.jsonl"), "--cohort", "pilot"]) == 0
    assert S.check_metrics(rows, "held", S.CP2)                     # a pilot is not the held cohort
    capsys.readouterr()
    assert S.main(["report", str(out / "metrics.jsonl"), "--checkpoint", "2"]) == 0
    text = capsys.readouterr().out
    assert "Projected held run time from this pilot" in text and "for 96 runs" in text
    assert "[primary] R priced-out person-turns in its pilot regions (R - R_free)" in text
    assert "All 17 identity outcomes are zero in all 2 worlds." in text
    # Paired values: R - R_free priced out 6 - 0; R_norelief - R 9 - 6.
    S.annotate_pairs_cp2(rows)
    by = {(r["arm"], r["stratum"]): r for r in rows}
    paired = {label: f for label, _a, _c, f in S.CP2.PAIRED}
    f = paired["[primary] R priced-out person-turns in its pilot regions (R - R_free)"]
    assert f(by[("R", "t")]) - f(by[("R_free", "t")]) == 6
    f = paired["[primary] R_norelief priced-out person-turns (R_norelief - R; what relief protects)"]
    assert f(by[("R_norelief", "t")]) - f(by[("R", "t")]) == 3
    # R - L2 over R's pilot region (region 0, every turn): food shortfall 7 in both
    # constructed worlds; ration shortfall 3 (retail rows) against 5 (L2's rows).
    assert by[("R", "t")]["pair"]["R|L2"]["food"] == pytest.approx(7.0)
    assert by[("L2", "t")]["pair"]["R|L2"]["food"] == pytest.approx(7.0)
    assert by[("R", "t")]["pair"]["R|L2"]["ration_short"] == pytest.approx(3.0)
    assert by[("L2", "t")]["pair"]["R|L2"]["ration_short"] == pytest.approx(5.0)
    assert by[("R", "t")]["pair"]["R|L2"]["mean_ration"] == pytest.approx(1 - 3 / 36)
    assert by[("R", "t")]["pair"]["R|L2"]["coverage"] == pytest.approx(1.0)
    # Under the all boundary both regions are in the set.
    assert by[("L2", "t")]["pair"]["R_all|L2"]["ration_short"] == pytest.approx(6.5)
    revenue = paired["R owners' sale revenue: household purchases and granary procurement credited, coins (R)"]
    assert revenue(by[("R", "t")]) == pytest.approx(3.5) and revenue(by[("L2", "t")]) == 0.0
    ratio = paired["R sale revenue / income replaced (R)"]
    assert ratio(by[("R", "t")]) == pytest.approx(3.5 / 1.5)
    assert by[("R_rec", "t")]["pair"]["R_rec|L2"]["trajectory_differs"] == 0.0


def test_a_differing_identity_arm_is_reported_as_a_failure(short, tmp_path, monkeypatch, capsys):
    S = short
    monkeypatch.setattr(S.LS, "source_identity", _stub_identity)
    monkeypatch.setattr(S, "simulate", _fake_simulate(S, perturb="R_rec"))
    out = tmp_path / "out"
    assert S.main(["run", str(out), "--checkpoint", "2", "--cohort", "pilot", "--arms", "R_rec,L2",
                   "--seeds", "template"]) == 0
    rows = [json.loads(line) for line in (out / "metrics.jsonl").read_text().splitlines()]
    text = "\n".join(S.report_lines(rows, S.CP2))
    assert "**FAILED** on 2 outcome-worlds:" in text
    assert "[identity] R_rec trajectory differs (1) or is identical (0) (R_rec - L2; must be 0) t5: +1" in text
    assert "[identity] R_rec treasury (R_rec - L2; must be 0) t5: +1" in text


def test_rows_of_another_checkpoint_are_refused(short, tmp_path, monkeypatch):
    S = short
    monkeypatch.setattr(S.LS, "source_identity", _stub_identity)
    monkeypatch.setattr(S, "simulate", _fake_simulate(S))
    out = tmp_path / "out"
    assert S.main(["run", str(out), "--checkpoint", "2", "--cohort", "pilot", "--arms", "L2",
                   "--seeds", "template"]) == 0
    metrics = out / "metrics.jsonl"
    with pytest.raises(SystemExit, match="holds rows of another checkpoint than 1"):
        S.main(["report", str(metrics)])
    rows = [json.loads(line) for line in metrics.read_text().splitlines()]
    assert any("row of checkpoint 2" in p for p in S.check_metrics(rows, "pilot"))
    with pytest.raises(SystemExit, match="holds a row of checkpoint 2, not 1"):
        S.main(["run", str(out), "--cohort", "pilot", "--arms", "W", "--seeds", "template", "--resume"])
    # A checkpoint-1 row is refused by a checkpoint-2 report.
    cp1 = dict(copy.deepcopy(rows[0]), arm="W")
    cp1.pop("checkpoint")
    metrics.write_text(json.dumps(cp1) + "\n")
    with pytest.raises(SystemExit, match="holds rows of another checkpoint than 2"):
        S.main(["report", str(metrics), "--checkpoint", "2"])
