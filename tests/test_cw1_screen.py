"""The CW1 screen (slice S1: the wage and paid_work enrollment) and the runner's two
phases: arms, derived schedules, activation, extractors and the run flow.

Offline: constructed bundles and a fake runtime (no simulation, no child process);
the real parser and feature catalog check the arm command lines. The extractors
were also checked on development-world bundles (the preregistration names the
checks). Nothing here runs a pilot, held or reserved seed. Oracle chunk
``connected-world-e``.
"""
from __future__ import annotations

import dataclasses
import hashlib
import importlib.util
import json
import sys
import threading
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def CW():
    sys.path.insert(0, str(ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location("cw1_screens_under_test", ROOT / "scripts" / "connected_world_screens.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def SR(CW):
    return CW.SR


@pytest.fixture(scope="module")
def HR(SR):
    SR._src()
    from chronicler import household_retail
    return household_retail


N_REGIONS = 4


def _cohorts(priced):
    groups = {"crew": (2, 0), "crew_children": (1, 0), "children_alone": (2, priced), "nonfarm_adults": (3, 0),
              "other": (2, 0)}
    return {"groups": {g: {"persons": p, "priced_out": po, "paid_milli": 0, "refunded_milli": 0, "credited_milli": 0,
                           "income_replaced": 0.0, "wages_milli": 0} for g, (p, po) in groups.items()},
            "credited_outside_milli": 0, "unknown": {}}


def _frame(region, priced):
    prov = {"persons": 10.0, "priced_out_persons": float(priced), "priced_out_children": 0.0, "rations": 8.0,
            "credited_milli": 500.0, "paid_milli": 500.0, "refunded_milli": 0.0}
    return {"region": region, "opened_turn": 0, "provisioning": prov, "income_replaced": 0.5, "commons": {},
            "cohorts": _cohorts(priced)}


def cw1_bundle(flags, *, turns=4, intervals=None, schedule=None, granary=1000, priced=(1, 0)):
    """A CW1-shaped bundle: retail frames for the regions inside ``intervals`` (region ->
    [[open, close]]), one ledger frame per snapshot with granary wages in region 0, a
    woodcut wage in region 2, a remittance into region 3 and an unlocated procurement
    credit, and the chain's records in the arm's modes."""
    flags = list(flags)
    boundary = flags[flags.index("--household-retail-boundary") + 1]
    paid = "unpaid" not in flags
    intervals = {0: [[0, None]], 1: [[0, None]]} if intervals is None else intervals
    hist = []
    prt = priced_total = 0
    for turn in range(1, turns + 1):
        t = turn - 1
        inside = [r for r, iv in sorted(intervals.items()) if any(a <= t and (b is None or t < b) for a, b in iv)]
        frames = [_frame(r, priced[r] if r < len(priced) else 0) for r in inside]
        prt += len(frames)
        priced_total += sum(int(f["provisioning"]["priced_out_persons"]) for f in frames)
        g = granary if paid else 0
        food = {f["region"]: 500 for f in frames}
        located = {r: food.get(r, 0) for r in range(N_REGIONS)}
        located[0] += g
        located[2] += 500
        located[3] += 300
        typed = [
            {"channel": "repair_wage", "in_milli": 0, "out_milli": 0, "unlocated_in_milli": 0, "observed": True},
            {"channel": "granary_crew_wage", "in_milli": g, "out_milli": 0, "unlocated_in_milli": 0, "observed": True},
            {"channel": "food_procurement", "in_milli": 200, "out_milli": 0, "unlocated_in_milli": 200,
             "observed": True},
            {"channel": "food_purchase", "in_milli": sum(food.values()), "out_milli": sum(food.values()),
             "unlocated_in_milli": 0, "observed": True},
            {"channel": "remittance", "in_milli": 300, "out_milli": 0, "unlocated_in_milli": 0, "observed": True},
        ]
        if "--timber-supply" in flags:
            typed.insert(2, {"channel": "woodcut_wage", "in_milli": 500, "out_milli": 0, "unlocated_in_milli": 0,
                             "observed": True})
        else:
            located[2] -= 500
        frame = {"turn": t, "typed_complete": True, "typed": typed, "closures": [],
                 "regions": [{"region": r, "typed_in_milli": v, "typed_out_milli": 0} for r, v in located.items()
                             if v],
                 "withheld": {"retail_income_replaced": 0.5 * len(frames) if frames else None}}
        hr = {"schema_version": 1, "stage": "L6b", "mode": "retail", "boundary": boundary, "rules_version": 2,
              "source_turn": t, "regions": frames, "opened_turn": {str(r): iv[0][0] for r, iv in intervals.items()},
              "intervals": {str(r): [list(i) for i in iv] for r, iv in sorted(intervals.items())},
              "counters": {"pilot_region_turns": prt, "priced_out_persons": priced_total,
                           "regions_opened": len(intervals)}, "log": []}
        if schedule is not None:
            hr["schedule"] = schedule
        lv = {"household_retail": hr,
              "wealth_accounting": {"schema_version": 1, "stage": "A1", "source_turn": t, "frame": frame,
                                    "counters": {"turns_observed": turn}},
              "recovery_crews": {"mode": "paid" if paid else "unpaid", "source_turn": t},
              "remittances": {"mode": "send", "source_turn": t}}
        if "--timber-supply" in flags:
            lv["timber_supply"] = {"mode": "supply", "source_turn": t}
        hist.append({"turn": turn, "livelihoods": lv,
                     "civ_stats": {"A": {"population": 100, "treasury": 50, "gini": 0.3}}})
    return {"metadata": {"bundle_version": 6}, "world_state": {"regions": [{"name": f"R{i}"} for i in range(N_REGIONS)]},
            "history": hist}


def _flags(CW, arm, path=None):
    flags = list(CW.SCREENS["CW1"].arms[arm][0])
    return [path if (path and f.startswith("{")) else f for f in flags]


# --- Declaration ------------------------------------------------------------------------

def test_cw1_declaration(SR, CW):
    s = CW.SCREENS["CW1"]
    assert s.ready and s.root == "B" and s.control_activation and SR.check_screen(s) == []
    assert s.held == {"template": tuple(range(731, 737)), "procedural": tuple(range(831, 837))}
    assert s.pilot == {"template": (5,), "procedural": (19,)}
    # The checkpoint-3 base, then retail rules 2 and the ledger in every arm.
    import productive_recovery_screens as PR
    assert list(s.base[:len(PR.CP3.BASE)]) == PR.CP3.BASE
    assert s.base[len(PR.CP3.BASE):] == ("--household-retail", "--household-retail-rules", "2", "--wealth-accounting")
    assert {a: c for a, (_f, c) in s.arms.items()} == {"A": "C", "B": None, "C": "B", "D": "B", "E": "F", "F": "B",
                                                        "G": "H", "H": "B", "CH_noTS": "A"}
    chain, unpaid = PR.CP3.CHAIN, ["--timber-supply", "--recovery-crews", "--recovery-crew-mode", "unpaid",
                                   "--remittances"]
    pw = ["--household-retail-boundary", "paid_work"]
    assert list(s.arms["A"][0]) == pw + chain and list(s.arms["B"][0]) == pw + unpaid
    assert list(s.arms["C"][0]) == ["--household-retail-boundary", "schedule", "--household-retail-schedule",
                                    "{S_A}", *unpaid]
    assert list(s.arms["D"][0]) == ["--household-retail-boundary", "schedule", "--household-retail-schedule",
                                    "{S_B}", *chain]
    assert list(s.arms["CH_noTS"][0]) == pw + ["--recovery-crews", "--remittances"]
    assert [(d.name, d.source, d.placeholder) for d in s.derived] == [("S_A", "A", "{S_A}"), ("S_B", "B", "{S_B}")]
    assert [o.id for o in s.primaries()] == ["cw1_p1_wage_money", "cw1_p2_enrollment_money", "cw1_p3_wage_priced_out"]
    assert [(o.arm, o.control) for o in s.primaries()] == [("A", "C"), ("C", "B"), ("A", "C")]
    inter = {o.id: o for o in s.outcomes}["cw1_interaction_money"]
    assert (inter.arm, inter.control, inter.minus) == ("A", "C", ("D", "B"))


def test_derived_declarations_are_checked(SR, CW):
    s = CW.SCREENS["CW1"]
    a, b = s.derived
    cases = [
        ((dataclasses.replace(a, source="X"), b), "source 'X' is not an arm"),
        ((dataclasses.replace(a, source="C"), b), "its source arm C uses a derived file itself"),
        ((dataclasses.replace(a, placeholder="{S_B}"), b), "derived names or placeholders repeat"),
        ((a, b, dataclasses.replace(a, name="S_C", placeholder="{S_C}")), "no arm names {S_C}"),
        ((dataclasses.replace(a, name="S A"), b), "a name of letters"),
    ]
    for derived, message in cases:
        problems = SR.check_screen(dataclasses.replace(s, derived=derived))
        assert any(message in p for p in problems), (message, problems)
    twice = dict(s.arms, C=((*s.arms["C"][0], "{S_A}"), "B"))
    assert any("names {S_A} more than once" in p for p in SR.check_derived(dataclasses.replace(s, arms=twice)))


# --- Extractor ---------------------------------------------------------------------------

def test_cw1_extract_formulas(SR, CW):
    s = CW.SCREENS["CW1"]
    paid = SR.extract_bundle(s, "A", cw1_bundle(_flags(CW, "A")), _flags(CW, "A"))
    assert "rc" not in paid, paid.get("error")
    m = paid["m"]
    # Per turn: wages 1.0 + 0.5, remittance 0.3, procurement 0.2; income replaced 2 x 0.5.
    assert m["money_world"] == pytest.approx(4 * (1.0 + 0.5 + 0.3 + 0.2 - 1.0))
    # Over the set {0, 1}: the granary wage (region 0); the woodcut wage (region 2) and the
    # remittance (region 3) are outside it, and procurement (unlocated) is left out (Amendment 1).
    assert m["region_set"] == [0, 1] and m["money_set"] == pytest.approx(4 * (1.0 - 1.0))
    assert m["procurement_world"] == pytest.approx(0.8)
    assert (m["wages_world"], m["granary_crew_wages"], m["woodcut_wages"]) == (6.0, 4.0, 2.0)
    assert m["priced_out_set"] == 4 and m["persons_set"] == 80 and m["priced_out_rate_set"] == pytest.approx(0.05)
    assert m["ration_mean_set"] == pytest.approx(0.8) and m["coverage"] == pytest.approx(0.5)
    assert m["rl5_crew_rate"] == 0.0 and m["rl5_children_alone_rate"] == pytest.approx(4 / 16)
    assert m["rl5_children_alone_priced_out"] == 4 and m["rl5_nonfarm_priced_out"] == 0
    assert m["money_unlocated"] == 0 and m["wa_unobserved_turns"] == 0
    assert paid["activation"] == {"activated": True, "evidence": "8 pilot region-turns in 2 regions; granary crew "
                                                                 "wages 4.000 (paid arm)"}
    unpaid = SR.extract_bundle(s, "B", cw1_bundle(_flags(CW, "B")), _flags(CW, "B"))
    assert unpaid["m"]["money_world"] == pytest.approx(4 * (0.5 + 0.3 + 0.2 - 1.0))
    assert unpaid["m"]["money_set"] == pytest.approx(4 * (0.0 - 1.0))
    assert unpaid["activation"]["evidence"] == "root arm"
    # Without the timber supply (CH_noTS): no woodcut wage, no timber supply record.
    nots = SR.extract_bundle(s, "CH_noTS", cw1_bundle(_flags(CW, "CH_noTS")), _flags(CW, "CH_noTS"))
    assert "rc" not in nots and nots["m"]["woodcut_wages"] == 0


def _mutated(CW, change):
    b = cw1_bundle(_flags(CW, "A"))
    snap = b["history"][2]
    lv = snap["livelihoods"]
    frame = lv["wealth_accounting"]["frame"]
    if change == "ledger frame missing":
        lv["wealth_accounting"]["frame"] = None
    elif change == "typed incomplete":
        frame["typed_complete"] = False
    elif change == "income differs":
        frame["withheld"]["retail_income_replaced"] = 2.0
    elif change == "cohorts differ":
        lv["household_retail"]["regions"][0]["cohorts"]["groups"]["other"]["priced_out"] = 3
    elif change == "located differs":
        frame["regions"][0]["typed_in_milli"] += 7
    elif change == "rules 1":
        lv["household_retail"]["rules_version"] = 1
    elif change == "turns differ":
        frame["turn"] = 99
    elif change == "no cohorts":
        lv["household_retail"]["regions"][0].pop("cohorts")
    return b


@pytest.mark.parametrize("change, message", [
    ("ledger frame missing", "ledger frame missing beside retail frames"),
    ("typed incomplete", "ledger typed flows incomplete"),
    ("income differs", "income replaced differs from the ledger's"),
    ("cohorts differ", "RL5 cohorts' priced-out persons differ"),
    ("located differs", "located inflows less retail sales differ"),
    ("rules 1", "retail not in rules 2"),
    ("turns differ", "ledger and retail frames of different turns"),
    ("no cohorts", "provisioned region without RL5 cohorts"),
])
def test_cw1_extract_refuses_inconsistent_records(SR, CW, change, message):
    row = SR.extract_bundle(CW.SCREENS["CW1"], "A", _mutated(CW, change), _flags(CW, "A"))
    assert row["rc"] == SR.RC_MISSING and message in row["error"], row.get("error")


def test_cw1_unknown_cohort_persons_are_left_out_of_rates_not_zero(SR, CW):
    b = cw1_bundle(_flags(CW, "A"))
    for g in b["history"][0]["livelihoods"]["household_retail"]["regions"][0]["cohorts"]["groups"].values():
        g["persons"] = None
    m = SR.extract_bundle(CW.SCREENS["CW1"], "A", b, _flags(CW, "A"))["m"]
    assert m["rl5_children_alone_unknown_frames"] == 1
    assert m["rl5_children_alone_rate"] == pytest.approx(3 / 14) and m["rl5_children_alone_priced_out"] == 4


@pytest.mark.parametrize("arm, granary, prt_regions, expected", [
    ("A", 1000, None, True), ("A", 0, None, False), ("E", 1000, {}, False), ("F", 1000, None, True),
])
def test_cw1_activation(SR, CW, arm, granary, prt_regions, expected):
    flags = _flags(CW, arm)
    b = cw1_bundle(flags, granary=granary, intervals=prt_regions)
    assert CW.cw1_activation(b, flags)[0] is expected
    # An unpaid arm whose records show a granary wage did not run as declared.
    if arm == "F":
        b["history"][0]["livelihoods"]["wealth_accounting"]["frame"]["typed"][1]["in_milli"] = 5
        assert CW.cw1_activation(b, flags)[0] is False


def test_cw1_schedule_is_made_and_replayed(SR, CW, HR, tmp_path):
    flags_a = _flags(CW, "A")
    intervals = {0: [[0, 2], [3, None]], 2: [[1, None]]}
    data, info = CW.cw1_schedule(cw1_bundle(flags_a, intervals=intervals), flags_a)
    assert data == b'{"0":[[0,2],[3,null]],"2":[[1,null]]}'
    assert info["canonical_sha256"] == hashlib.sha256(data).hexdigest() and info["regions"] == 2
    assert info["intervals"] == 3
    path = tmp_path / "S_A.json"
    path.write_bytes(data)
    flags_c = _flags(CW, "C", str(path))
    given = {"sha256": hashlib.sha256(data).hexdigest(), "turns": {"0": [[0, 2], [3, None]], "2": [[1, None]]}}
    exact = cw1_bundle(flags_c, intervals=intervals, schedule=given)
    row = SR.extract_bundle(CW.SCREENS["CW1"], "C", exact, flags_c)
    assert "rc" not in row, row.get("error")
    assert row["m"]["replay"]["exact"] and row["m"]["region_set"] == [0, 2] and row["activation"]["activated"]
    # A region enrolled later than scheduled (its controller missing): inexact, not activated.
    late = cw1_bundle(flags_c, intervals={0: [[0, 2], [3, None]], 2: [[2, None]]}, schedule=given)
    replay = CW.cw1_replay(late, flags_c)
    assert not replay["exact"] and replay["differ"] == [2]
    activated, text = CW.cw1_activation(late, flags_c)
    assert activated is False and "inexactly (regions [2]" in text
    # The file the run was given must be the schedule it recorded.
    path.chmod(0o644)
    path.write_bytes(b'{"0":[[0,null]]}')
    row = SR.extract_bundle(CW.SCREENS["CW1"], "C", exact, flags_c)
    assert row["rc"] == SR.RC_MISSING and "the schedule file's sha256" in row["error"]


def test_cw1_schedule_refuses_an_approximate_bundle(SR, CW):
    flags = _flags(CW, "A")
    b = cw1_bundle(flags)
    for s in b["history"]:
        s["livelihoods"]["household_retail"].pop("intervals")
    with pytest.raises(ValueError, match="approximate"):
        CW.cw1_schedule(b, flags)


# --- Runner: the two phases ----------------------------------------------------------------

IDENTITY = ("source abc", "dirty 0 tracked files")


class FakeCW1:
    """A fake simulation writing CW1-shaped bundles: a schedule arm records exactly the
    intervals of its schedule file (or ``late`` ones); ``fail`` names (arm, world) runs
    that exit 1."""

    def __init__(self, SR, CW, fail=(), late=()):
        self.SR, self.CW, self.fail, self.late = SR, CW, set(fail), set(late)
        self.calls, self.lock = [], threading.Lock()
        self.rt = SR.Runtime(simulate=self.simulate, identity=lambda screen: list(IDENTITY), clock=lambda: 0.0,
                             changed_paths=lambda old, new: [])

    def simulate(self, cmd):
        out = Path(cmd[cmd.index("--output") + 1]).parent
        arm = out.name.rsplit("-", 1)[0]
        world = out.name.rsplit("-", 1)[1]
        with self.lock:
            self.calls.append((arm, world, cmd))
        if (arm, world) in self.fail:
            return types.SimpleNamespace(returncode=1, stderr="boom")
        flags = cmd[cmd.index("--household-retail-boundary"):cmd.index("--output")]
        intervals, schedule = None, None
        if "--household-retail-schedule" in cmd:
            raw = Path(cmd[cmd.index("--household-retail-schedule") + 1]).read_bytes()
            turns = json.loads(raw)
            schedule = {"sha256": hashlib.sha256(raw).hexdigest(), "turns": turns}
            intervals = {int(k): [list(i) for i in v] for k, v in turns.items()}
            if (arm, world) in self.late:
                intervals = {r: [[iv[0][0] + 1, None]] for r, iv in intervals.items()}
        elif "unpaid" in flags:
            intervals = {0: [[1, None]]}            # B enrolls less than A
        (out / "chronicle_bundle.json").write_text(json.dumps(cw1_bundle(flags, intervals=intervals,
                                                                         schedule=schedule)))
        return types.SimpleNamespace(returncode=0, stderr="")


def _run(SR, CW, tmp_path, fake, *extra, out="out"):
    argv = [str(tmp_path / out), "--screen", "CW1", "--cohort", "dev", "--worlds", "t1,p7", "--jobs", "2", *extra]
    return SR.run_main(argv, CW.SCREENS, fake.rt)


def test_two_phases_freeze_the_schedules_before_their_users(SR, CW, tmp_path):
    fake = FakeCW1(SR, CW)
    assert _run(SR, CW, tmp_path, fake) == 0
    out = tmp_path / "out"
    order = [(arm, world) for arm, world, _c in fake.calls]
    for world in ("t1", "p7"):
        assert order.index(("A", world)) < order.index(("C", world))
        assert order.index(("B", world)) < order.index(("D", world))
    rows = {(r["arm"], f"{r['stratum']}{r['seed']}"): r for r in SR.read_rows(out / "metrics.jsonl", CW.SCREENS["CW1"])}
    assert len(rows) == 18 and all(r["rc"] == 0 for r in rows.values())
    derived = [json.loads(line) for line in (out / "derived.jsonl").read_text().splitlines()]
    assert sorted((d["name"], d["stratum"], d["seed"]) for d in derived) == [
        ("S_A", "p", 7), ("S_A", "t", 1), ("S_B", "p", 7), ("S_B", "t", 1)]
    source = (out / "source.txt").read_text()
    for d in derived:
        path = out / d["path"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == d["sha256"] and not path.stat().st_mode & 0o222
        world = f"{d['stratum']}{d['seed']}"
        user = {"S_A": "C", "S_B": "D"}[d["name"]]
        assert rows[(d["arm"], world)]["derived"][d["name"]]["sha256"] == d["sha256"]
        assert rows[(user, world)]["inputs"] == {d["name"]: {"path": d["path"], "sha256": d["sha256"]}}
        assert f"derived {d['name']} {world} (from arm {d['arm']}): sha256 {d['sha256']} {d['path']}" in source
        # C's command line names the frozen file.
        cmd = next(c for arm, w, c in fake.calls if (arm, w) == (user, world))
        assert cmd[cmd.index("--household-retail-schedule") + 1] == str(path.resolve())
    assert rows[("C", "t1")]["m"]["replay"]["exact"] and rows[("C", "t1")]["activation"]["activated"]
    text = "\n".join(SR.report_lines(list(rows.values()), CW.SCREENS["CW1"]))
    assert "## CW1 validity per world" in text and "replays S_A" in text and ": exact" in text
    assert "| cw1_p1_wage_money:" in text and "| cw1_interaction_money:" in text


def test_a_failed_source_fails_its_users_and_an_inexact_replay_is_not_activated(SR, CW, tmp_path):
    fake = FakeCW1(SR, CW, fail={("A", "t1")}, late={("D", "p7")})
    assert _run(SR, CW, tmp_path, fake) == SR.RC_FAILED
    rows = {(r["arm"], f"{r['stratum']}{r['seed']}"): r
            for r in SR.read_rows(tmp_path / "out" / "metrics.jsonl", CW.SCREENS["CW1"])}
    assert ("C", "t1") not in [(a, w) for a, w, _c in fake.calls]
    assert rows[("C", "t1")]["rc"] == SR.RC_FAILED
    assert "not run: derived S_A for t1 is unavailable (its source arm A failed" in rows[("C", "t1")]["error"]
    assert rows[("C", "p7")]["rc"] == 0
    assert rows[("D", "p7")]["activation"]["activated"] is False and not rows[("D", "p7")]["m"]["replay"]["exact"]
    text = "\n".join(SR.report_lines(list(rows.values()), CW.SCREENS["CW1"]))
    assert "INEXACT (regions [0])" in text
    # D - B leaves p7 out (not activated); A - C leaves t1 out (failed).
    cells, values = SR.paired_values(list(rows.values()), CW.SCREENS["CW1"], "D", "B", CW._m("money_set"), "p", [7])
    assert cells == ["7: not activated"] and values == []
    cells, _v = SR.paired_values(list(rows.values()), CW.SCREENS["CW1"], "A", "C", CW._m("money_set"), "t", [1])
    assert cells == ["1: failed"]


def test_a_user_arm_needs_its_source_and_resumes_on_the_recorded_schedule(SR, CW, tmp_path):
    with pytest.raises(SystemExit, match="arm C uses S_A, which arm A makes on each world: choose arm A too"):
        _run(SR, CW, tmp_path, FakeCW1(SR, CW), "--arms", "C")
    first = FakeCW1(SR, CW)
    assert _run(SR, CW, tmp_path, first, "--arms", "A,B", out="two") == 0
    again = FakeCW1(SR, CW)
    assert _run(SR, CW, tmp_path, again, "--arms", "C,D", "--resume", out="two") == 0
    assert sorted({a for a, _w, _c in again.calls}) == ["C", "D"]
    rows = SR.read_rows(tmp_path / "two" / "metrics.jsonl", CW.SCREENS["CW1"])
    assert len(rows) == 8 and all(r["rc"] == 0 for r in rows)


def test_a_changed_derived_file_is_refused_before_the_run(SR, CW, tmp_path):
    fake = FakeCW1(SR, CW)
    out = tmp_path / "o"
    s = CW.SCREENS["CW1"]
    path = SR.derived_path(out, s.derived[0], "t", 1)
    path.parent.mkdir(parents=True)
    path.write_bytes(b'{"0":[[0,null]]}')
    row = SR.run_one(s, fake.rt, out, "dev", "C", "t", 1, False, "id", None, {"S_A": "0" * 64})
    assert row["rc"] == SR.RC_FAILED and "missing or changed (recorded sha256 000000000000" in row["error"]
    assert fake.calls == []


# --- Runner: differences of differences and control activation ---------------------------

def _row(arm, value, act=True, seed=1):
    return {"arm": arm, "stratum": "t", "seed": seed, "rc": 0, "activation": {"activated": act}, "m": {"v": value}}


def test_interaction_and_control_activation(SR, CW):
    s = CW.SCREENS["CW1"]
    read = CW._m("v")
    rows = [_row("A", 10.0), _row("C", 4.0), _row("D", 7.0), _row("B", 5.0, act=None)]
    assert SR.paired_values(rows, s, "A", "C", read, "t", [1], minus=("D", "B")) == (["1: +4"], [4.0])
    # The control must have acted too (control_activation); the root never needs to.
    rows[1] = _row("C", 4.0, act=False)
    assert SR.paired_values(rows, s, "A", "C", read, "t", [1])[0] == ["1: not activated"]
    assert SR.paired_values(rows, s, "D", "B", read, "t", [1])[1] == [2.0]
    lax = dataclasses.replace(s, control_activation=False)
    assert SR.paired_values(rows, lax, "A", "C", read, "t", [1])[1] == [6.0]
    # A missing interaction term is not run, never zero.
    assert SR.paired_values(rows[:2] + rows[3:], lax, "A", "C", read, "t", [1], minus=("D", "B"))[0] == ["1: not run"]
    bad = dataclasses.replace(s, outcomes=(*s.outcomes, SR.Outcome("x", "x", "A", "C", read, minus=("D", "C"))))
    assert any("x: C is not a control of D" in p for p in SR.check_preregistration(bad, held=False))


def test_held_run_records_the_schedule_digests_in_the_ledger(SR, CW, tmp_path):
    prereg = tmp_path / "cw1.md"
    prereg.write_text("# CW1\n\nStatus: FROZEN at abc\n\nCompute ceiling: 2.0 core-hours\n\nPrimary outcomes: "
                      "cw1_p1_wage_money, cw1_p2_enrollment_money, cw1_p3_wage_priced_out\n")
    screen = dataclasses.replace(CW.SCREENS["CW1"], preregistration=prereg)
    identity = [*IDENTITY, SR.preregistration_line(screen)]
    pilot = tmp_path / "pilot"
    pilot.mkdir()
    (pilot / "source.txt").write_text("\n".join(identity) + "\nrun: screen CW1; cohort pilot; x\n")
    digest = SR.identity_digest(identity)
    (pilot / "metrics.jsonl").write_text("".join(
        json.dumps({"screen": "CW1", "cohort": "pilot", "arm": arm, "stratum": tag, "seed": seed, "rc": 0,
                    "wall_s": 1.0, "extract_s": 0.0, "identity": digest}) + "\n"
        for arm in screen.arms for tag, seed in (("t", 5), ("p", 19))))
    fake = FakeCW1(SR, CW)
    fake.rt.ledger = tmp_path / "ledger.jsonl"
    # A scratch registry as before CW1's held run was recorded (never the real file).
    reg = SR.load_registry()
    for e in reg["entries"]:
        if e.get("screen") == "CW1" and e.get("cohort") == "held":
            e["status"] = "reserved"
            e.pop("held_run", None)
    fake.rt.registry = tmp_path / "registry.json"
    fake.rt.registry.write_text(SR.dump_registry(reg))
    rc = SR.run_main([str(tmp_path / "held"), "--screen", "CW1", "--cohort", "held", "--jobs", "2", "--pilot",
                      str(pilot / "metrics.jsonl"), "--seeds", "template"], {"CW1": screen}, fake.rt)
    assert rc == 0
    entries = SR.ledger_entries(fake.rt.ledger)
    starts = [e for e in entries if "derived" not in e]
    derived = [e["derived"] for e in entries if "derived" in e]
    assert len(starts) == 1 and len(derived) == 12
    assert {(d["name"], d["seed"]) for d in derived} == {(n, s) for n in ("S_A", "S_B") for s in range(731, 737)}
    assert all(e["identity"] == starts[0]["identity"] for e in entries)
    # A recorded derived digest is not another start of the cohort.
    assert len(SR.ledger_conflicts(fake.rt.ledger, screen, "held")) == 1
