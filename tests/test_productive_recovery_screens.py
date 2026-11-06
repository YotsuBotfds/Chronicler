"""PL6a: the checkpoint-1 screen runner, its validated extractor and its cohorts.

Offline: constructed bundles (not simulation runs) and the real parser and
prerequisite checks. Nothing here runs the simulation or a held seed.
"""
from __future__ import annotations

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
    spec = importlib.util.spec_from_file_location("productive_recovery_screens_under_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# --- Constructed bundles ------------------------------------------------------------

TURNS = 3
GRANARY = [0.5, 0.6, 0.7]          # condition of the one granary with capacity, per turn
SITE = [0.9, 0.8, 0.7]             # condition of the one built workshop site, per turn
DEMAND = [[10.0, 4.0], [10.0, 4.0], [10.0, 4.0]]
SUFFICIENCY = [[0.5, 1.0], [1.2, 0.25], [0.8, 2.0]]   # after relief, per turn and region


def _rec(mode, counters, turn, **extra):
    rec = {"schema_version": 1, "source_turn": turn - 1, "counters": counters, **extra}
    if mode is not None:
        rec["mode"] = mode
    return rec


def _records(S, arm, turn, *, drop=None, rename=None):
    """Package records of one snapshot for ``arm`` (``drop``: a package left out;
    ``rename``: (package, counter) recorded under an undeclared name)."""
    expected = S.expected_packages(S.ARMS[arm][0])
    liv = {"schema_version": 1}
    for name, mode in expected.items():
        if name == drop:
            continue
        counters = {}
        extra = {}
        if name == "workshops":
            counters = {}
            extra = {"sites": [{"site": 0, "status": "open", "asset": "open", "condition": SITE[turn - 1]},
                               {"site": 1, "status": "open", "asset": "building", "condition": 1.0}],
                     "receipts": [{"allocated": 1.0, "realized": 1.0, "region_craft_output": 2.0,
                                   "paid": {"repair": 20} if turn == 2 else {"upkeep": 3},
                                   "craft_ceiling": 2.0, "asset": "open"}]}
        elif name == "timber_stock":
            extra = {"totals": {"extraction": 1.5, "regrowth": 0.5, "cleared": 0.0, "overdraft": 0.0,
                                "capped_slots": 0, "stock": 50.0, "capacity": 100.0}}
        elif name == "timber_supply":
            counters = {"launched": 2, "ended": 2, "cut": 6.0, "delivered": 5.0, "lost": 0.05,
                        "abandoned_cargo": 0.95, "away_delivered": 3.0, "wages_milli": 4500,
                        "ended_wages_milli": 4000, "ended_person_turns": 8, "ended_away": 3.0}
            extra = {"receipts": [
                {"turn": turn - 1, "home": 1, "stage": "cutting" if turn == 2 else "outbound",
                 "away_delivered": 1.0 if turn != 3 else 0.0,
                 "stock_after": 60.0 if turn == 2 else None, "capacity": 100.0 if turn == 2 else None}]}
        elif name == "repair_projects":
            counters = {"stalled_no_timber": 7, "wages_milli": 1500, "timber_used": 4.0}
        elif name == "recovery_crews":
            counters = {"granary_wages_milli": 2000 if mode == "paid" else 0, "veterans_placed": 0}
        elif name == "local_budgets":
            extra = {"decisions": [{"proposals": [{"pid": 0, "service": "workshop"}, {"pid": 1, "service": "repairs"},
                                                  {"pid": 2, "service": "granary_maintain"}],
                                    "awards": [{"pid": 0, "amount": 3}, {"pid": 1, "amount": 2},
                                               {"pid": 2, "amount": 1}]}]}
        elif name == "maintenance_obligation":
            counters = {"reserved_coins": 9, "used_coins": 7 if mode == "reserve" else 0,
                        "returned_coins": 2 if mode == "reserve" else 9}
        elif name == "apprenticeship":
            counters = {"operating_site_turns": 10, "covered_site_turns": 4 if mode == "train" else 2}
        elif name == "veteran_reintegration":
            counters = {"placements": 3 if mode == "priority" else 1, "people_placed": 2}
        elif name == "operating_wear":
            counters = {"turns": turn, "wear": 0.02 * turn}
        if rename and rename[0] == name:
            counters[rename[1]] = 1
        liv[name] = _rec(mode, counters, turn, **extra)
    return liv


def _bundle(S, arm, *, drop=None, rename=None, food_gap_at=None):
    hist = []
    for turn in range(1, TURNS + 1):
        regions = [{"region_id": i, "native": {"demand": DEMAND[turn - 1][i]},
                    "sufficiency_after_relief": SUFFICIENCY[turn - 1][i]} for i in range(2)]
        if food_gap_at == turn:
            regions[1]["sufficiency_after_relief"] = None
        hist.append({
            "turn": turn,
            "civ_stats": {"A": {"population": 10 + turn, "treasury": 5.0}},
            "grain_reserves": {"storage": {"assets": [{"capacity": 10.0, "condition": GRANARY[turn - 1]},
                                                      {"capacity": 0.0, "condition": 0.2}]}},
            "food_accounting": {"source_turn": turn - 1, "regions": regions},
            "livelihoods": _records(S, arm, turn, drop=drop, rename=rename),
        })
    world = {"regions": [{"stockpile": {"goods": {"timber": 1.0}}, "ecology": {"forest_cover": 0.3}}
                         for _ in range(2)],
             "grain_reserves": {"storage": {"assets": [{"capacity": 10.0, "condition": GRANARY[-1]}]}},
             "livelihoods": {"workshops": {"sites": [{"status": "open", "asset": "open", "condition": SITE[-1]}]}}}
    return {"history": hist, "world_state": world}


@pytest.fixture
def short(S, monkeypatch):
    monkeypatch.setattr(S, "TURNS", TURNS)
    return S


def _extract(S, bundle, arm):
    return S.extract(bundle, S.ARMS[arm][0], S.declared_counters(), S.declared_services())


# --- Arms, flags and controls -------------------------------------------------------

def test_base_and_arms_are_the_preregistered_ones(S):
    assert S.BASE == ["--turns", "200", "--agents", "hybrid", "--simulate-only", "--grain-reserves",
                      "--public-grain-shipments", "--scholarship", "--techniques", "--academy-services",
                      "--grain-storage", "--workshops"]
    assert S.PROCEDURAL == ["--worldgen", "procedural", "--regions", "32", "--civs", "10"]
    rp = ["--operating-wear", "--repair-projects", "--timber-stock"]
    ch = rp + ["--timber-supply", "--recovery-crews", "--veteran-reintegration"]
    assert S.ARMS == {
        "W": ([], None),
        "W_wear": (["--operating-wear"], "W"),
        "TR2": (["--apprenticeship"], "NQ2"),
        "NQ2": (["--apprenticeship", "--apprenticeship-mode", "no_qualification"], "W_wear"),
        "RP": (rp, "W_wear"),
        "TS": (rp + ["--timber-supply"], "TS_cost"),
        "TS_cost": (rp + ["--timber-supply", "--timber-supply-mode", "cost_only"], "RP"),
        "RC": (rp + ["--recovery-crews"], "RC_unpaid"),
        "RC_unpaid": (rp + ["--recovery-crews", "--recovery-crew-mode", "unpaid"], "RP"),
        "L9": (rp + ["--local-budgets"], "RP"),
        "MO": (rp + ["--local-budgets", "--maintenance-obligation"], "MO_ro"),
        "MO_ro": (rp + ["--local-budgets", "--maintenance-obligation", "--maintenance-obligation-mode",
                        "reserve_only"], "L9"),
        "CH": (ch, "CH_rec"),
        "CH_rec": (ch + ["--veteran-mode", "record_only"], "RP"),
    }


def test_every_arm_parses_and_passes_the_livelihoods_prerequisites(S):
    from chronicler.main import _build_parser
    parser = _build_parser()
    for arm, (flags, _control) in S.ARMS.items():
        parser.parse_args(["--seed", "5", *S.BASE, *flags])
        parser.parse_args(["--seed", "19", *S.BASE, *S.PROCEDURAL, *flags])
    S.check_arm_flags()       # configure_livelihoods on a hybrid world: modes as expected
    assert S.expected_packages(S.ARMS["W"][0]) == {"workshops": "operate"}
    assert S.expected_packages(S.ARMS["NQ2"][0]) == {"workshops": "operate", "apprenticeship": "no_qualification"}
    assert S.expected_packages(S.ARMS["MO_ro"][0]) == {
        "workshops": "operate", "operating_wear": None, "repair_projects": "repair", "timber_stock": None,
        "local_budgets": "bargained", "maintenance_obligation": "reserve_only"}
    assert S.expected_packages(S.ARMS["CH_rec"][0])["veteran_reintegration"] == "record_only"
    assert S.expected_packages(S.ARMS["TS_cost"][0])["timber_supply"] == "cost_only"
    assert S.expected_packages(S.ARMS["RC_unpaid"][0])["recovery_crews"] == "unpaid"


def test_a_prerequisite_failure_is_named(S, monkeypatch):
    monkeypatch.setitem(S.ARMS, "TS", (["--timber-supply"], "TS_cost"))       # no RS2, no L3
    with pytest.raises(SystemExit, match="arm TS: --timber-supply requires"):
        S.check_arm_flags()


def test_each_control_exists_and_leads_to_the_root(S, monkeypatch):
    for arm, (_flags, control) in S.ARMS.items():
        assert control is None or control in S.ARMS, arm
    S.check_extractor()
    monkeypatch.setitem(S.ARMS, "TS", (S.ARMS["TS"][0], "TS_none"))
    with pytest.raises(SystemExit, match="arm TS: unknown control TS_none"):
        S.check_extractor()


def test_a_cycle_of_controls_is_refused(S, monkeypatch):
    monkeypatch.setitem(S.ARMS, "RP", (S.ARMS["RP"][0], "TS"))
    with pytest.raises(SystemExit, match="do not lead to the root W"):
        S.check_extractor()


# --- Seeds --------------------------------------------------------------------------

def test_seed_cohorts_are_disjoint_from_every_earlier_and_reserved_cohort(S):
    S.check_seeds()
    assert S.PILOT == {"template": (5,), "procedural": (19,)}
    assert set(S.HELD["template"]) == set(range(701, 707))
    assert set(S.HELD["procedural"]) == set(range(801, 807))
    earlier_t = {2, *range(101, 107), *range(301, 307), *range(501, 507)}
    earlier_p = {*range(201, 207), *range(401, 407), *range(601, 607)}
    reserved_t = {*range(711, 717), *range(721, 727)}
    reserved_p = {*range(811, 817), *range(821, 827)}
    for cohort in (S.PILOT, S.HELD):
        assert not set(cohort["template"]) & (earlier_t | reserved_t)
        assert not set(cohort["procedural"]) & (earlier_p | reserved_p)
    assert not set(S.PILOT["template"]) & set(S.HELD["template"])
    assert not set(S.PILOT["procedural"]) & set(S.HELD["procedural"])
    assert S.NEVER_RUN["template"] == earlier_t and S.NEVER_RUN["procedural"] == earlier_p
    assert S.RESERVED["template"] == reserved_t and S.RESERVED["procedural"] == reserved_p


def test_an_overlapping_seed_is_refused(S, monkeypatch):
    monkeypatch.setitem(S.HELD, "template", (501, 702))
    with pytest.raises(SystemExit, match=r"template held seeds \[501\] are in the earlier cohorts"):
        S.check_seeds()
    monkeypatch.setitem(S.HELD, "template", tuple(range(701, 707)))
    monkeypatch.setitem(S.PILOT, "procedural", (811,))
    with pytest.raises(SystemExit, match=r"procedural pilot seeds \[811\] are in the reserved cohorts"):
        S.check_seeds()


def test_jobs_cover_exactly_the_cohort(S):
    jobs = S.jobs_for("pilot", "all", list(S.ARMS))
    assert len(jobs) == 28
    assert {(j[1], j[2]) for j in jobs} == {("t", 5), ("p", 19)}
    assert all(j[3] == S.PROCEDURAL for j in jobs if j[1] == "p") and all(j[3] == [] for j in jobs if j[1] == "t")
    held = S.jobs_for("held", "template", ["W"])
    assert [j[2] for j in held] == list(range(701, 707)) and [j[4] for j in held] == [True] + [False] * 5


def test_a_held_run_is_refused_until_the_preregistration_is_frozen(S, tmp_path, monkeypatch):
    draft = tmp_path / "prereg.md"
    draft.write_text("# x\n\nStatus: **DRAFT, not frozen**.\n")
    assert not S.preregistration_frozen(draft)
    draft.write_text("# x\n\nStatus: **FROZEN** on 2026-11-07 at abc.\n")
    assert S.preregistration_frozen(draft)
    assert not S.preregistration_frozen(S.PREREGISTRATION)     # the committed draft
    called = []
    monkeypatch.setattr(S, "simulate", lambda cmd: called.append(cmd))
    with pytest.raises(SystemExit, match="held run refused"):
        S.main(["run", str(tmp_path / "out"), "--cohort", "held", "--arms", "W"])
    assert called == [] and not (tmp_path / "out").exists()


# --- Extractor validation -------------------------------------------------------------

def test_the_extractor_validates_against_the_source(S, monkeypatch):
    S.check_extractor()
    declared = S.declared_counters()
    for name, keys in S.OUTCOMES.items():
        assert set(keys) <= declared[name], name
    assert {"workshop", "granary_maintain", "granary_expand", "relief", "repairs"} <= S.declared_services()
    monkeypatch.setitem(S.OUTCOMES, "timber_supply", ("cut", "timber_delivered"))
    with pytest.raises(SystemExit, match="timber_supply.timber_delivered is not a declared counter"):
        S.check_extractor()


def test_an_undeclared_comparison_is_refused(S, monkeypatch):
    monkeypatch.setattr(S, "PAIRED", [*S.PAIRED, ("x", "TS", "W", lambda r: 0)])
    with pytest.raises(SystemExit, match="TS - W is not a declared comparison"):
        S.check_extractor()


def test_a_wrong_default_mode_is_refused(S, monkeypatch):
    monkeypatch.setitem(S.PACKAGES, "--timber-supply", ("timber_supply", "--timber-supply-mode", "cost_only"))
    with pytest.raises(SystemExit, match="--timber-supply-mode: default 'cost_only'"):
        S.check_extractor()


# --- Extraction of constructed bundles ------------------------------------------------

def test_a_constructed_timber_supply_bundle_extracts(short):
    S = short
    out, problems = _extract(S, _bundle(S, "TS"), "TS")
    assert problems == []
    assert out["packages"]["timber_supply"] == "supply"
    assert out["granary"]["run_mean"] == pytest.approx(0.6) and out["granary"]["end"] == pytest.approx(0.7)
    assert out["workshop"]["run_mean"] == pytest.approx(0.8) and out["workshop"]["end"] == pytest.approx(0.7)
    assert out["lump_repairs"] == 1
    # Shortfall after relief = demand x max(0, 1 - sufficiency), summed per region.
    assert out["food"]["region_shortfall"] == pytest.approx([5.0 + 0.0 + 2.0, 0.0 + 3.0 + 0.0])
    assert out["food"]["region_demand"] == pytest.approx([30.0, 12.0])
    ts = out["ts"]
    assert ts["homes"] == [1] and ts["region_away"] == pytest.approx([0.0, 2.0])
    # Away on turns 1 and 2 (source turns 0 and 1): region 1's shortfall 0 + 3 of demand 8.
    assert (ts["away_cells"], ts["away_shortfall"], ts["away_demand"], ts["away_below_one"]) == (2, 3.0, 8.0, 1)
    assert ts["away_shortfall_share"] == pytest.approx(3 / 8)
    assert ts["min_stock_share"] == pytest.approx(0.6)
    assert ts["wages_per_ended"] == pytest.approx(2.0) and ts["person_turns_per_ended"] == pytest.approx(4.0)
    pk = out["pk"]
    assert pk["timber_supply"]["delivered"] == 5.0 and pk["timber_supply"]["recalls"] == 0   # never incremented
    assert pk["repair_projects"]["stalled_no_timber"] == 7
    assert "l9" not in out and "recovery_crews" not in pk


def test_a_constructed_budget_bundle_reads_awards_by_service(short):
    S = short
    out, problems = _extract(S, _bundle(S, "MO_ro"), "MO_ro")
    assert problems == []
    assert out["l9"]["awards"] == {"workshop": 9, "repairs": 6, "granary_maintain": 3}
    assert (out["l9"]["other"], out["l9"]["workshop"], out["l9"]["granary"], out["l9"]["relief"]) == (12, 9, 3, 0)
    assert out["pk"]["maintenance_obligation"]["returned_coins"] == 9
    assert "ts" not in out


def test_the_metrics_row_carries_the_shared_metrics(short, tmp_path):
    S = short
    path = tmp_path / "chronicle_bundle.json"
    path.write_text(json.dumps(_bundle(S, "CH")))
    row = S.metrics_row(path, S.ARMS["CH"][0])
    assert "rc" not in row
    assert row["population"] == 13 and row["timber"]["extraction"] == pytest.approx(4.5)
    assert row["workshops"]["operating"] == 3
    assert S._wages(row) == pytest.approx((1500 + 2000 + 4500) / 1000)
    assert row["pk"]["veteran_reintegration"]["placements"] == 3


def test_structural_zero_only_for_a_package_the_arm_leaves_off(short):
    S = short
    rp, _ = _extract(S, _bundle(S, "RP"), "RP")
    assert S._z(rp, "timber_supply", "delivered") == 0.0           # off: verified absent
    assert S._wages(rp) == pytest.approx(1.5)                        # RS2 workshop wages only
    assert S._c(rp, "timber_supply", "delivered") is None
    assert S._z({}, "timber_supply", "delivered") is None            # failed row: unknown


@pytest.mark.parametrize("label, kwargs, arm, match", [
    ("missing package", {"drop": "timber_supply"}, "TS", "packages .* recorded, expected exactly"),
    ("renamed counter", {"rename": ("timber_supply", "timber_delivered")}, "TS", "undeclared counters"),
    ("missing food", {"food_gap_at": 2}, "TS", "food accounting missing or incomplete at turns \\[2\\]"),
])
def test_a_missing_or_malformed_outcome_is_named(short, label, kwargs, arm, match):
    S = short
    _out, problems = _extract(S, _bundle(S, arm, **kwargs), arm)
    assert any(re.search(match, p) for p in problems), (label, problems)


def test_other_malformed_records_are_named(short):
    S = short
    cases = {}
    b = _bundle(S, "TS_cost")
    b["history"][-1]["livelihoods"]["timber_supply"]["mode"] = "supply"
    cases["wrong mode"] = (b, "TS_cost", "timber_supply: mode 'supply', expected 'cost_only'")
    b = _bundle(S, "TS")
    b["history"][-1]["livelihoods"]["repair_projects"]["source_turn"] = 1
    cases["stale record"] = (b, "TS", "repair_projects: source_turn 1 is not the completed turn")
    b = _bundle(S, "W")
    b["history"][-1]["livelihoods"]["timber_supply"] = _rec("supply", {}, TURNS)
    cases["leaked package"] = (b, "W", "expected exactly")
    b = _bundle(S, "TS")
    b["history"][1]["livelihoods"]["timber_supply"]["receipts"] = None
    cases["unknown receipts"] = (b, "TS", "timber_supply: receipts missing at turns \\[2\\]")
    b = _bundle(S, "L9")
    b["history"][0]["livelihoods"]["local_budgets"]["decisions"][0]["proposals"][0]["service"] = "bribes"
    cases["unknown service"] = (b, "L9", "names no declared service")
    b = _bundle(S, "W")
    del b["history"][1]["grain_reserves"]
    cases["no granaries"] = (b, "W", "granary storage missing at turns \\[2\\]")
    b = _bundle(S, "W")
    b["history"] = b["history"][:2]
    cases["short run"] = (b, "W", "snapshots are not turns 1..3")
    b = _bundle(S, "W_wear")
    b["history"][-1]["livelihoods"]["operating_wear"]["counters"]["wear"] = float("nan")
    cases["NaN counter"] = (b, "W_wear", "non-numeric counters")
    for label, (bundle, arm, match) in cases.items():
        _out, problems = _extract(S, bundle, arm)
        assert any(re.search(match, p) for p in problems), (label, problems)


def test_an_unknown_measure_is_none_not_zero(short):
    S = short
    b = _bundle(S, "TS")
    for snap in b["history"]:
        snap["livelihoods"]["timber_supply"]["receipts"] = []
        snap["livelihoods"]["timber_supply"]["counters"]["ended"] = 0
        snap["grain_reserves"]["storage"]["assets"] = [{"capacity": 0.0, "condition": 0.2}]
    out, problems = _extract(S, b, "TS")
    assert problems == []
    assert out["granary"]["run_mean"] is None
    assert out["ts"]["min_stock_share"] is None and out["ts"]["wages_per_ended"] is None
    assert out["ts"]["away_shortfall_share"] is None and out["ts"]["homes"] == []


# --- Running: a missing outcome exits with code 3 -------------------------------------

def _fake_simulate(S, *, drop=None):
    def simulate(cmd):
        out = Path(cmd[cmd.index("--output") + 1]).parent
        start = 5 + len(S.BASE)
        assert cmd[5:start] == S.BASE
        if cmd[start:start + len(S.PROCEDURAL)] == S.PROCEDURAL:
            start += len(S.PROCEDURAL)
        flags = cmd[start:cmd.index("--output")]
        (arm,) = [a for a, (f, _c) in S.ARMS.items() if f == flags]
        (out / "chronicle_bundle.json").write_text(json.dumps(_bundle(S, arm, drop=drop)))
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
    code = S.main(["run", str(out), "--cohort", "pilot", "--arms", "TS,RP", "--seeds", "template", "--jobs", "1"])
    assert code == 3
    rows = [json.loads(line) for line in (out / "metrics.jsonl").read_text().splitlines()]
    by = {r["arm"]: r for r in rows}
    assert by["TS"]["rc"] == 3 and "timber_supply" in by["TS"]["error"]
    assert by["RP"]["rc"] == 0
    assert "FAILED run TS t5 (rc 3)" in capsys.readouterr().out
    assert not (out / "runs" / "TS-t5").exists()                     # raw output deleted
    assert "cohort pilot" in (out / "source.txt").read_text()
    # The completeness check fails with code 3 too, and the report names the run.
    assert S.main(["check", "--metrics", str(out / "metrics.jsonl"), "--cohort", "pilot"]) == 3
    assert S.exit_code(rows) == 3
    report = "\n".join(S.report_lines(rows))
    assert "FAILED TS t5 (rc 3)" in report and "INCOMPLETE TS p19: not run" in report


def test_a_complete_pilot_extracts_and_reports(short, tmp_path, monkeypatch, capsys):
    S = short
    monkeypatch.setattr(S.LS, "source_identity", _stub_identity)
    monkeypatch.setattr(S, "simulate", _fake_simulate(S))
    out = tmp_path / "out"
    assert S.main(["run", str(out), "--cohort", "pilot", "--jobs", "2"]) == 0
    rows = [json.loads(line) for line in (out / "metrics.jsonl").read_text().splitlines()]
    assert len(rows) == 28 and all(r["rc"] == 0 for r in rows)
    assert S.check_metrics(rows, "pilot") == []
    assert S.main(["check", "--metrics", str(out / "metrics.jsonl"), "--cohort", "pilot"]) == 0
    assert S.check_metrics(rows, "held")                              # a pilot is not the held cohort
    capsys.readouterr()
    assert S.main(["report", str(out / "metrics.jsonl")]) == 0
    text = capsys.readouterr().out
    assert "Projected held run time from this pilot" in text
    assert "[primary] TS granary mean condition, run mean (TS - TS_cost)" in text
    # Food over the sending regions (region 1 in both arms): equal constructed worlds, so 0.
    S.annotate_pairs(rows)
    by = {(r["arm"], r["stratum"]): r for r in rows}
    assert by[("TS", "t")]["pair"]["TS|TS_cost"] == pytest.approx(3.0)
    assert by[("TS_cost", "t")]["pair"]["TS|TS_cost"] == pytest.approx(3.0)
    assert by[("RP", "t")]["pair"]["TS_cost|RP"] == pytest.approx(3.0)
    assert by[("RP", "t")]["pair"]["TS|RP"] == pytest.approx(3.0)
