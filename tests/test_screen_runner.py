"""The connected-world screen runner, its seed registry and the CW1-CW6 stubs.

Offline: constructed bundles and a fake runtime (no simulation, no child process);
the real parser and feature catalog check arm command lines. Nothing here runs a
held, pilot or reserved seed.
"""
from __future__ import annotations

import copy
import dataclasses
import hashlib
import importlib.util
import json
import tempfile
import threading
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def CW():
    path = ROOT / "scripts" / "connected_world_screens.py"
    spec = importlib.util.spec_from_file_location("connected_world_screens_under_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def SR(CW):
    return CW.SR


@pytest.fixture(scope="module")
def registry(SR):
    return SR.load_registry()


def _seeds(*items):
    out = set()
    for item in items:
        out.update(range(item[0], item[1] + 1) if isinstance(item, tuple) else {item})
    return out


# --- The seed registry ----------------------------------------------------------------

def test_registry_is_valid(SR, registry):
    assert SR.validate_registry(registry) == []
    assert registry["restricted_ranges"] == {"template": [[42, 241]], "procedural": [[42, 141]], "both": [[1000, 1999]]}
    assert set(registry["statuses"]) == set(SR.REGISTRY_STATUSES)
    for e in registry["entries"]:
        assert set(SR.ENTRY_KEYS) <= set(e) <= set(SR.ENTRY_KEYS + SR.OPTIONAL_ENTRY_KEYS)


#: Audit E section 5.3: every historical cohort, per stratum.
AUDIT_COHORTS = [
    ("template", _seeds((101, 106), (301, 306), (501, 506), (701, 706), (711, 716), (721, 726))),
    ("procedural", _seeds((201, 206), (401, 406), (601, 606), (801, 806), (811, 816), (821, 826))),
    ("template", _seeds(2, 5, (1, 3), 3, 7, 9, 11, 23, 42, 12, 13, 14)),
    ("procedural", _seeds(7, 19, 11, 13, 17, 21, 31, 302, 303)),
    ("template", _seeds(202, 303, 404, (42, 241), (62, 81), (142, 161), (42, 121), (1000, 1019))),
    ("procedural", _seeds((42, 141), (42, 61), (1000, 1019), (42, 51), (52, 71), (900, 904), (1000, 1999))),
    ("template", _seeds((282, 301), (42, 81), (900, 909), (1000, 1999), (10, 29), 42, 43, 77, 1337, 2026, 0, 101, 1234)),
    ("procedural", _seeds(42, 43, 11, 7)),
]


@pytest.mark.parametrize("stratum, seeds", AUDIT_COHORTS)
def test_registry_holds_every_audit_cohort(SR, registry, stratum, seeds):
    assert seeds <= SR.seed_sets(registry, stratum)["used"]


def test_registry_union_covers_the_audit_union(SR, registry):
    template = _seeds((0, 3), 5, 7, 9, (10, 29), (42, 241), (282, 306), 404, (501, 506), (701, 706), (711, 716),
                      (721, 726), (900, 909), (1000, 1999), 1234, 1337, 2026)
    procedural = _seeds(7, 11, 13, 17, 19, 21, 31, (42, 141), (201, 206), 302, 303, (401, 406), (601, 606),
                        (801, 806), (811, 816), (821, 826), (900, 904), (1000, 1999))
    assert template <= SR.seed_sets(registry, "template")["used"]
    assert procedural <= SR.seed_sets(registry, "procedural")["used"]
    # Held cohorts that ran are never run again; development worlds are not.
    assert _seeds((701, 706), (101, 106)) <= SR.seed_sets(registry, "template")["never_run_again"]
    assert 23 in SR.seed_sets(registry, "template")["development"]


PROGRAM = {"CW1": (731, 831), "CW2": (741, 841), "CW3": (751, 851), "CW4": (761, 861), "CW5": (771, 871),
           "CW6": (781, 881)}


@pytest.mark.parametrize("screen", sorted(PROGRAM))
def test_program_reservations(SR, registry, CW, screen):
    t0, p0 = PROGRAM[screen]
    own = [e for e in registry["entries"] if e.get("screen") == screen]
    assert {(e["stratum"], e["status"], e["cohort"], e["program"]) for e in own} == {
        ("template", "reserved", "held", "connected-world"), ("procedural", "reserved", "held", "connected-world")}
    got = {e["stratum"]: SR.expand(e["seeds"]) for e in own}
    assert got == {"template": set(range(t0, t0 + 6)), "procedural": set(range(p0, p0 + 6))}
    assert CW.SCREENS[screen].held == {"template": tuple(range(t0, t0 + 6)), "procedural": tuple(range(p0, p0 + 6))}
    for stratum, seeds in got.items():
        others = set().union(*(SR.expand(e["seeds"]) for e in registry["entries"]
                               if e["stratum"] == stratum and e not in own))
        assert not seeds & others


def test_pilot_and_reserve(SR, registry, CW):
    by = {e["id"]: e for e in registry["entries"]}
    assert SR.expand(by["cw-pilot-t"]["seeds"]) == {5} and SR.expand(by["cw-pilot-p"]["seeds"]) == {19}
    assert by["cw-pilot-t"]["cohort"] == "pilot" and by["cw-pilot-t"]["screen"] is None
    assert SR.expand(by["cw-reserve-t"]["seeds"]) == set(range(791, 797))
    assert SR.expand(by["cw-reserve-p"]["seeds"]) == set(range(891, 897))
    assert all(by[k]["status"] == "reserved" for k in ("cw-pilot-t", "cw-pilot-p", "cw-reserve-t", "cw-reserve-p"))
    assert all(s.pilot == {"template": (5,), "procedural": (19,)} for n, s in CW.SCREENS.items() if n != "DEV")


def _mutate(registry, change):
    reg = copy.deepcopy(registry)
    by = {e["id"]: e for e in reg["entries"]}
    if change == "duplicate id":
        reg["entries"].append(dict(by["ls1-held-t"]))
    elif change == "bad stratum":
        by["ls1-held-t"]["stratum"] = "both"
    elif change == "bad status":
        by["ls1-held-t"]["status"] = "used"
    elif change == "bad seeds":
        by["ls1-held-t"]["seeds"] = [[106, 101]]
    elif change == "unknown key":
        by["ls1-held-t"]["note"] = "x"
    elif change == "reservation overlaps":
        by["cw2-held-t"]["seeds"] = [[736, 741]]
    elif change == "reservation in the gate":
        by["cw1-held-t"]["seeds"] = [[231, 236]]
    elif change == "no gate entry":
        reg["entries"] = [e for e in reg["entries"] if e["id"] != "gate200-t"]
    elif change == "ranges changed":
        reg["restricted_ranges"]["template"] = [[42, 141]]
    elif change == "held reservation without screen":
        by["cw1-held-t"]["screen"] = None
    return reg


@pytest.mark.parametrize("change", ["duplicate id", "bad stratum", "bad status", "bad seeds", "unknown key",
                                    "reservation overlaps", "reservation in the gate", "no gate entry",
                                    "ranges changed", "held reservation without screen"])
def test_validate_registry_refuses(SR, registry, change):
    assert SR.validate_registry(_mutate(registry, change))


# --- check_seeds --------------------------------------------------------------------

@pytest.mark.parametrize("name", ["CW1", "CW2", "CW3", "CW4", "CW5", "CW6", "DEV"])
def test_program_cohorts_pass(SR, registry, CW, name):
    problems, notes = SR.check_seeds(CW.SCREENS[name], registry)
    assert problems == []
    # The shared pilot was also seen by old exploratory batches: a note, not a refusal.
    assert all("pilot seed" in n for n in notes)


def _screen(CW, **changes):
    return dataclasses.replace(CW.SCREENS["CW1"], **changes)


def _held(t, p=tuple(range(831, 837))):
    return {"template": tuple(t), "procedural": tuple(p)}


@pytest.mark.parametrize("changes, registry_change, message", [
    ({"held": _held(range(741, 747))}, None, "are in another cohort or use: cw2-held-t"),
    ({"held": _held(range(741, 747))}, None, "differs from its registry reservation"),
    ({"held": _held([731, 731, 732, 733, 734, 735])}, None, "listed more than once"),
    ({"held": _held(range(100, 106))}, None, "restricted gate range"),
    ({"held": _held(range(1000, 1006))}, None, "are in 1000-1999"),
    ({"held": _held([731, 732, 733, 734, 735, 23])}, None, "are development worlds"),
    ({}, "cw1 run", "were already run (reused)"),
    ({"pilot": {"template": (6,), "procedural": (19,)}}, None, "is not registered as the shared pilot"),
    ({"pilot": {"template": (791,), "procedural": (19,)}}, None, "is in a reserve cohort"),
    ({"pilot": {"template": (741,), "procedural": (19,)}}, None, "is in a held cohort"),
    ({"pilot": {"template": (7,), "procedural": (19,)}}, None, "are development worlds"),
    ({"pilot": {"template": (50,), "procedural": (19,)}}, None, "restricted gate range"),
    ({"pilot": {"template": (731,), "procedural": (19,)}}, None, "pilot and held overlap"),
])
def test_check_seeds_refuses(SR, registry, CW, changes, registry_change, message):
    reg = copy.deepcopy(registry)
    if registry_change == "cw1 run":
        next(e for e in reg["entries"] if e["id"] == "cw1-held-t")["status"] = "run"
    problems, _notes = SR.check_seeds(_screen(CW, **changes), reg)
    assert any(message in p for p in problems), problems


# --- Preregistration ----------------------------------------------------------------

def _outcome(SR, i, primary=True, arm="TS", control="W"):
    return SR.Outcome(f"o{i}", f"outcome {i}", arm, control, lambda r: 0.0, primary=primary)


@pytest.mark.parametrize("n, ok", [(0, False), (1, False), (2, True), (3, True), (4, False)])
def test_two_or_three_primaries(SR, CW, n, ok):
    outcomes = tuple(_outcome(SR, i, primary=i < n) for i in range(5))
    screen = dataclasses.replace(CW.SCREENS["DEV"], outcomes=outcomes)
    problems = SR.check_preregistration(screen, held=False)
    assert (problems == []) is ok
    if not ok:
        assert any("primary outcomes, a screen declares 2-3" in p for p in problems)


def test_outcome_comparisons_must_be_declared(SR, CW):
    screen = dataclasses.replace(CW.SCREENS["DEV"], outcomes=(
        _outcome(SR, 0), _outcome(SR, 1), _outcome(SR, 2, arm="W", control="TS"), _outcome(SR, 3, arm="X")))
    problems = SR.check_preregistration(screen, held=False)
    assert any("o2: TS is not a control of W" in p for p in problems)
    assert any("o3: unknown arm X" in p for p in problems)


PREREG = "# CW1\n\nStatus: FROZEN at abc123\n\nCompute ceiling: 1.0 core-hours\n\nPrimary outcomes: dev_population, dev_stand\n"


@pytest.mark.parametrize("text, message", [
    (None, "missing"),
    (PREREG.replace("FROZEN", "DRAFT"), "is not marked FROZEN"),
    (PREREG.replace("FROZEN at", "DRAFT, FROZEN at"), "is not marked FROZEN"),
    (PREREG.replace("Compute ceiling: 1.0 core-hours\n", ""), "Compute ceiling"),
    (PREREG + "Compute ceiling: 2 core-hours\n", "Compute ceiling"),
    (PREREG.replace("dev_population, dev_stand", "dev_population"), "differs from the screen's primaries"),
    (PREREG.replace("dev_population, dev_stand", "dev_population, dev_food"), "differs from the screen's primaries"),
])
def test_held_preregistration_is_enforced(SR, CW, tmp_path, text, message):
    path = tmp_path / "prereg.md"
    if text is not None:
        path.write_text(text)
    screen = dataclasses.replace(CW.SCREENS["DEV"], preregistration=path)
    problems = SR.check_preregistration(screen, held=True)
    assert any(message in p for p in problems), problems


def test_frozen_preregistration_reads_its_ceiling_and_primaries(SR, CW, tmp_path):
    path = tmp_path / "prereg.md"
    path.write_text(PREREG)
    screen = dataclasses.replace(CW.SCREENS["DEV"], preregistration=path)
    assert SR.check_preregistration(screen, held=True) == []
    assert SR.compute_ceiling(PREREG) == 1.0
    assert SR.declared_primaries(PREREG.replace("dev_stand", "`dev_stand`")) == ["dev_population", "dev_stand"]


# --- Constructed bundles and the harm panel ---------------------------------------------

def make_bundle(turns=3, regions=2, timber=False, retail=False, epidemics=False, migration=True, food=True,
                cut=True):
    def snap(t):
        s = {"turn": t, "civ_stats": {"A": {"population": 10 + t, "treasury": 5, "gini": 0.25},
                                      "B": {"population": 20, "treasury": 7, "gini": 0.75}}}
        if food:
            s["food_accounting"] = {"schema_version": 1, "source_turn": t - 1, "regions": [
                {"region_id": i, "native": {"demand": 10.0}, "sufficiency_after_relief": 0.5 if i == 0 else 1.2}
                for i in range(regions)]}
        if migration:
            s["migration"] = [[0, 1, 3], [1, 1, 9]]
        if epidemics:
            s["epidemics"] = {"deaths": 1, "deaths_total": t}
        liv = {}
        if timber:
            liv["timber_stock"] = {"schema_version": 1, "source_turn": t - 1, "observed": True,
                                   "totals": {"stock": 40.0, "capacity": 80.0,
                                              "extraction": 2.0 if (cut and t > 1) else 0.0}}
        if retail:
            liv["household_retail"] = {"schema_version": 1, "source_turn": t - 1, "mode": "retail", "regions": [
                {"region": 0, "provisioning": {"priced_out_persons": 2.0, "priced_out_children": 1.0}},
                {"region": 1, "provisioning": None}], "counters": {"priced_out_persons": 2.0 * t}}
        if liv:
            s["livelihoods"] = {"schema_version": 1, **liv}
        return s
    return {"metadata": {"bundle_version": 6}, "world_state": {"regions": [{"name": f"R{i}"} for i in range(regions)]},
            "history": [snap(t) for t in range(1, turns + 1)]}


def test_harm_panel_is_fixed_data(SR):
    assert [h.key for h in SR.HARM_PANEL] == [
        "population", "treasury", "food_shortfall", "priced_out_persons", "priced_out_children", "deaths_famine",
        "deaths_epidemic", "deaths_war", "out_migration", "wealth_gini", "forest_stand"]
    missing = {h.key: h.owner for h in SR.HARM_PANEL if h.extractor is None}
    assert set(missing) == {"deaths_famine", "deaths_war"} and all(missing.values())
    assert all(h.label and h.source for h in SR.HARM_PANEL)


def test_harm_extractors_on_a_constructed_bundle(SR):
    harm, problems = SR.harm_panel(make_bundle(turns=3, timber=True, retail=True, epidemics=True))
    assert problems == []
    values = {k: (v["state"], v["value"]) for k, v in harm.items()}
    assert values == {
        "population": ("recorded", 33), "treasury": ("recorded", 12), "food_shortfall": ("recorded", 15.0),
        "priced_out_persons": ("recorded", 6.0), "priced_out_children": ("recorded", 3.0),
        "deaths_famine": ("requires_slice_extractor", None), "deaths_epidemic": ("recorded", 3),
        "deaths_war": ("requires_slice_extractor", None), "out_migration": ("recorded", 9),
        "wealth_gini": ("recorded", 0.5), "forest_stand": ("recorded", 0.5)}


def test_harms_of_systems_that_are_off_are_not_recorded_never_zero(SR):
    harm, problems = SR.harm_panel(make_bundle(migration=False, food=False))
    assert problems == []
    for key in ("food_shortfall", "priced_out_persons", "priced_out_children", "deaths_epidemic", "out_migration",
                "forest_stand"):
        assert harm[key]["state"] == "not_recorded" and harm[key]["value"] is None and harm[key]["note"]
    assert SR.harm_value({"harm": harm}, "food_shortfall") is None


@pytest.mark.parametrize("damage, key", [
    ("food row", "food_shortfall"), ("food dated", "food_shortfall"), ("retail counter", "priced_out_persons"),
    ("retail frame", "priced_out_children"), ("migration", "out_migration"), ("epidemics", "deaths_epidemic"),
    ("gini", "wealth_gini"), ("population", "population"),
])
def test_malformed_harms_fail_the_run(SR, CW, damage, key):
    bundle = make_bundle(timber=True, retail=True, epidemics=True)
    last = bundle["history"][-1]
    if damage == "food row":
        del last["food_accounting"]["regions"][1]["sufficiency_after_relief"]
    elif damage == "food dated":
        last["food_accounting"]["source_turn"] = 7
    elif damage == "retail counter":
        last["livelihoods"]["household_retail"]["counters"]["priced_out_persons"] = 99.0
    elif damage == "retail frame":
        last["livelihoods"]["household_retail"]["regions"][0]["provisioning"]["priced_out_children"] = "2"
    elif damage == "migration":
        last["migration"] = [[0, 1]]
    elif damage == "epidemics":
        del last["epidemics"]["deaths_total"]
    elif damage == "gini":
        last["civ_stats"]["A"]["gini"] = None
    elif damage == "population":
        last["civ_stats"]["B"]["population"] = None
    harm, problems = SR.harm_panel(bundle)
    assert harm[key]["state"] == "malformed"
    assert any(p.startswith(f"harm {key}:") for p in problems)
    row = SR.extract_bundle(CW.SCREENS["DEV"], "TS", bundle, ["--timber-stock"])
    assert row["rc"] == 3 and f"harm {key}" in row["error"]


def test_schema_versions_read(SR):
    versions = SR.schema_versions(make_bundle(timber=True, retail=True))
    assert versions == {"bundle": 6, "livelihoods": [1], "packages": {"household_retail": [1], "timber_stock": [1]},
                        "records": {"food_accounting": [1]}}


# --- Packages and activation ---------------------------------------------------------

def test_dev_extraction_records_activation_and_packages(SR, CW):
    screen = CW.SCREENS["DEV"]
    row = SR.extract_bundle(screen, "TS", make_bundle(timber=True), ["--timber-stock"])
    assert "rc" not in row
    assert row["activation"] == {"activated": True, "evidence": "2 of 3 observed turns cut timber"}
    row = SR.extract_bundle(screen, "TS", make_bundle(timber=True, cut=False), ["--timber-stock"])
    assert row["activation"]["activated"] is False
    assert SR.extract_bundle(screen, "W", make_bundle(), [])["activation"] == {"activated": None, "evidence": "root arm"}


@pytest.mark.parametrize("arm, flags, bundle_kwargs, message", [
    ("W", [], {"timber": True}, "timber_stock: recorded at turns [1, 2, 3] in an arm without it"),
    ("TS", ["--timber-stock"], {}, "timber_stock: enabled but never recorded"),
])
def test_package_leaks_and_absences_fail(SR, CW, arm, flags, bundle_kwargs, message):
    row = SR.extract_bundle(CW.SCREENS["DEV"], arm, make_bundle(**bundle_kwargs), flags)
    assert row["rc"] == 3 and message in row["error"]


def test_package_counters_are_declared_dated_and_in_mode(SR, CW):
    retail = SR.Package("--household-retail", ("livelihoods", "household_retail"),
                        counters_module="chronicler.household_retail_state", counters=("priced_out_persons",),
                        mode_flag="--household-retail-mode", default_mode="retail")
    screen = dataclasses.replace(CW.SCREENS["DEV"], packages=(retail,))
    assert SR.check_packages_declared(screen) == []
    bundle = make_bundle(retail=True)
    pk, problems = SR.package_problems(screen, bundle, ["--household-retail"])
    assert problems == [] and pk == {"household_retail": {"priced_out_persons": 6.0}}
    _pk, problems = SR.package_problems(screen, bundle, ["--household-retail", "--household-retail-mode", "no_relief"])
    assert problems == ["household_retail: mode 'retail', expected 'no_relief' at turns [1, 2, 3]"]
    bundle["history"][-1]["livelihoods"]["household_retail"]["counters"]["invented"] = 1
    bundle["history"][0]["livelihoods"]["household_retail"]["source_turn"] = 5
    _pk, problems = SR.package_problems(screen, bundle, ["--household-retail"])
    assert any("undeclared counters ['invented']" in p for p in problems)
    assert any("misdated records at turns [1]" in p for p in problems)
    wrong = dataclasses.replace(screen, packages=(dataclasses.replace(retail, counters=("not_a_counter",)),))
    assert SR.check_packages_declared(wrong) == ["household_retail.not_a_counter is not a declared counter"]


# --- Uncertainty ---------------------------------------------------------------------

def test_sign_flip_is_exact(SR):
    flip = SR.sign_flip([2.0, -1.0, 3.0])
    assert flip == {"n": 3, "assignments": 8, "observed": 4 / 3, "min": -2.0, "max": 2.0, "at_least_as_extreme": 4}
    assert SR.sign_flip([1.0, 1.0])["at_least_as_extreme"] == 2
    six = SR.sign_flip([1.0] * 6)
    assert six["assignments"] == 64 and six["at_least_as_extreme"] == 2
    assert SR.sign_flip([]) is None and SR.sign_flip([1.0] * 17) is None


def test_describe(SR):
    assert SR.describe([1.0, -2.0, 0.0, 4.0]) == {"n": 4, "mean": 0.75, "min": -2.0, "max": 4.0, "positive": 2,
                                                  "negative": 1, "zero": 1}
    assert SR.describe([]) is None


# --- Report ----------------------------------------------------------------------------

def _row(SR, CW, arm, tag, seed, bundle, rc=0, identity="i"):
    flags = list(CW.SCREENS["DEV"].arms[arm][0])
    row = {"screen": "DEV", "cohort": "dev", "arm": arm, "stratum": tag, "seed": seed, "rc": rc, "wall_s": 1.0,
           "extract_s": 0.5, "identity": identity}
    if rc == 0:
        row.update(SR.extract_bundle(CW.SCREENS["DEV"], arm, bundle, flags))
    return row


def test_report_shows_activation_first_and_never_reads_non_activation_as_zero(SR, CW):
    rows = [_row(SR, CW, "W", "t", 1, make_bundle()), _row(SR, CW, "TS", "t", 1, make_bundle(timber=True)),
            _row(SR, CW, "W", "t", 3, make_bundle()), _row(SR, CW, "TS", "t", 3, make_bundle(timber=True, cut=False)),
            _row(SR, CW, "W", "t", 7, make_bundle()), _row(SR, CW, "TS", "t", 7, None, rc=1),
            _row(SR, CW, "W", "t", 9, make_bundle())]
    text = "\n".join(SR.report_lines(rows, CW.SCREENS["DEV"]))
    assert text.index("## Activation per world") < text.index("## Primary outcomes") < text.index("## Harm panel")
    assert "| TS | t | 1: activated; 3: not activated; 7: failed; 9: not run | 1 of 4 |" in text
    stand = next(line for line in text.splitlines() if line.startswith("| dev_stand"))
    assert "1: +0.5" in stand and "3: not activated" in stand and "7: failed" in stand and "9: not run" in stand
    assert "+0.5 [+0.5, +0.5] | 1 / 0 / 0 | n/a (no control)" in stand
    assert "- INCOMPLETE TS t9: not run" in text and "- FAILED TS t7 (rc 1)" in text
    assert "| TS - W | Deaths by war (the casualty authority) | t | requires slice extractor |" in text
    retail = next(line for line in text.splitlines() if "| TS - W | Priced-out person-turns" in line)
    assert "1: not recorded" in retail and "not_recorded (household retail is off" in retail
    assert "not a significance test" in text


def test_pilot_projection(SR, CW):
    screen = dataclasses.replace(CW.SCREENS["DEV"], held={"template": (1, 2), "procedural": (3,)})
    rows = [{"arm": arm, "stratum": tag, "rc": 0, "wall_s": w, "extract_s": 0.0}
            for arm in ("W", "TS") for tag, w in (("t", 360.0), ("p", 720.0))]
    assert SR.projected_held_core_hours(rows, screen) == pytest.approx((360 * 2 + 720) * 2 / 3600)
    assert SR.projected_held_core_hours(rows[:3], screen) is None


# --- Running with a fake runtime --------------------------------------------------------

IDENTITY = ("source abc", "dirty 0 tracked files")


class FakeRuntime:
    """Writes a constructed bundle for each command; each simulation takes ``seconds`` on
    its own thread's clock (so concurrent runs are timed alike). The ledger lives in a
    temporary directory; ``changed`` lists the paths between two revisions."""

    def __init__(self, SR, seconds=1.0, identity=IDENTITY, ledger=None, changed=(), rc=0):
        self.seconds, self.calls, self.rc, self.local = seconds, [], rc, threading.local()
        self.ledger = Path(ledger) if ledger else Path(tempfile.mkdtemp()) / "ledger.jsonl"
        self.rt = SR.Runtime(simulate=self.simulate, identity=lambda screen: list(identity), clock=self.clock,
                             ledger=self.ledger, changed_paths=lambda old, new: list(changed))

    def clock(self):
        return getattr(self.local, "now", 0.0)

    def simulate(self, cmd):
        self.calls.append(cmd)
        out = Path(cmd[cmd.index("--output") + 1]).parent
        (out / "chronicle_bundle.json").write_text(json.dumps(make_bundle(timber="--timber-stock" in cmd)))
        self.local.now = self.clock() + self.seconds
        return types.SimpleNamespace(returncode=self.rc, stderr="failed" if self.rc else "")


@pytest.mark.parametrize("cohort", ["held", "pilot"])
def test_stub_screens_are_refused(SR, CW, tmp_path, cohort):
    fake = FakeRuntime(SR)
    with pytest.raises(SystemExit, match="CW1 is not ready"):
        SR.run_main([str(tmp_path / "out"), "--screen", "CW1", "--cohort", cohort], CW.SCREENS, fake.rt)
    assert fake.calls == []


def test_dev_run_writes_identity_and_rows_and_resumes(SR, CW, tmp_path):
    out = tmp_path / "out"
    fake = FakeRuntime(SR)
    argv = [str(out), "--screen", "DEV", "--cohort", "dev", "--worlds", "t1,p7", "--turns", "5", "--jobs", "1"]
    assert SR.run_main(argv, CW.SCREENS, fake.rt) == 0
    assert len(fake.calls) == 4
    assert all(c[c.index("--turns") + 1] == "5" for c in fake.calls)
    assert sum("--worldgen" in c for c in fake.calls) == 2
    source = (out / "source.txt").read_text()
    assert source.startswith("source abc\ndirty 0 tracked files\nrun: screen DEV; cohort dev;")
    rows = SR.read_rows(out / "metrics.jsonl", CW.SCREENS["DEV"])
    digest = hashlib.sha256(b"source abc\ndirty 0 tracked files").hexdigest()
    assert {r["identity"] for r in rows} == {digest} and all(r["rc"] == 0 for r in rows)
    assert {(r["arm"], r["stratum"], r["seed"]) for r in rows} == {("W", "t", 1), ("TS", "t", 1), ("W", "p", 7),
                                                                 ("TS", "p", 7)}
    assert SR.check_metrics(rows, "dev", CW.SCREENS["DEV"], [("t", 1), ("p", 7)]) == []
    assert not (out / "runs" / "W-t1").exists()
    # Not without --resume; a resume on the same identity repeats nothing.
    with pytest.raises(SystemExit, match="pass --resume"):
        SR.run_main(argv, CW.SCREENS, FakeRuntime(SR).rt)
    again = FakeRuntime(SR)
    assert SR.run_main([*argv, "--resume"], CW.SCREENS, again.rt) == 0 and again.calls == []
    other = FakeRuntime(SR, identity=("source def", "dirty 0 tracked files"))
    with pytest.raises(SystemExit, match="resume refused: the source"):
        SR.run_main([*argv, "--resume"], CW.SCREENS, other.rt)
    source_path = out / "source.txt"
    source_path.write_text(source_path.read_text().replace("cohort dev;", "cohort pilot;"))
    with pytest.raises(SystemExit, match="resume refused: .* was started as"):
        SR.run_main([*argv, "--resume"], CW.SCREENS, FakeRuntime(SR).rt)


@pytest.mark.parametrize("argv, message", [
    (["--cohort", "dev", "--worlds", "t5"], "not a registered development world"),
    (["--cohort", "dev", "--worlds", "t731"], "not a registered development world"),
    (["--cohort", "dev"], "needs --worlds"),
    (["--cohort", "pilot"], "has no pilot cohort"),
    (["--cohort", "held", "--turns", "5"], "has no held cohort"),
])
def test_dev_screen_refusals(SR, CW, tmp_path, argv, message):
    with pytest.raises(SystemExit, match=message):
        SR.run_main([str(tmp_path / "o"), "--screen", "DEV", *argv], CW.SCREENS, FakeRuntime(SR).rt)


def _held_screen(SR, CW, tmp_path, ceiling=1.0):
    prereg = tmp_path / "prereg.md"
    prereg.write_text(PREREG.replace("1.0", str(ceiling)))
    dev = CW.SCREENS["DEV"]
    return dataclasses.replace(CW.SCREENS["CW1"], base=dev.base, arms=dev.arms, root=dev.root, packages=dev.packages,
                               outcomes=dev.outcomes, activation=dev.activation, ready=True, preregistration=prereg)


def _pilot(tmp_path, seconds, identity=IDENTITY, rows_identity=None, name="pilot"):
    """A pilot directory: source.txt with its identity lines and metrics.jsonl."""
    folder = tmp_path / name
    folder.mkdir(exist_ok=True)
    (folder / "source.txt").write_text("\n".join(identity) + "\nrun: screen CW1; cohort pilot; x\n")
    digest = rows_identity or hashlib.sha256("\n".join(identity).encode()).hexdigest()
    path = folder / "metrics.jsonl"
    path.write_text("".join(json.dumps({"screen": "CW1", "cohort": "pilot", "arm": arm, "stratum": tag, "seed": seed,
                                        "rc": 0, "wall_s": seconds, "extract_s": 0.0, "identity": digest}) + "\n"
                            for arm in ("W", "TS") for tag, seed in (("t", 5), ("p", 19))))
    return path


def test_held_run_refuses_a_projection_over_the_ceiling(SR, CW, tmp_path):
    screens = {"CW1": _held_screen(SR, CW, tmp_path, ceiling=1.0)}
    argv = [str(tmp_path / "out"), "--screen", "CW1", "--cohort", "held"]
    with pytest.raises(SystemExit, match="--pilot"):
        SR.run_main(argv, screens, FakeRuntime(SR).rt)
    # 2 arms x 12 worlds x 200 s = 1.33 core-hours; x1.5 = 2.0 > 1.0
    with pytest.raises(SystemExit, match=r"projects 1\.333 core-hours; x1\.5 = 2\.000 exceeds the ceiling"):
        SR.run_main([*argv, "--pilot", str(_pilot(tmp_path, 200.0))], screens, FakeRuntime(SR).rt)
    unfrozen = {"CW1": dataclasses.replace(screens["CW1"], preregistration=tmp_path / "absent.md")}
    with pytest.raises(SystemExit, match="preregistration .* missing"):
        SR.run_main([*argv, "--pilot", str(_pilot(tmp_path, 1.0))], unfrozen, FakeRuntime(SR).rt)


def test_held_run_stops_at_the_ceiling_and_reports_the_rest_as_not_run(SR, CW, tmp_path):
    screens = {"CW1": _held_screen(SR, CW, tmp_path, ceiling=1.0)}
    out = tmp_path / "out"
    fake = FakeRuntime(SR, seconds=600.0)       # 6 runs reach 1 core-hour
    rc = SR.run_main([str(out), "--screen", "CW1", "--cohort", "held", "--jobs", "1",
                      "--pilot", str(_pilot(tmp_path, 10.0))], screens, fake.rt)
    assert rc == SR.RC_CEILING and len(fake.calls) == 6
    assert all(int(c[c.index("--seed") + 1]) in range(831, 837) for c in fake.calls)   # procedural first
    source = (out / "source.txt").read_text()
    assert "stopped at the compute ceiling (1.0 core-hours" in source and "18 runs not started" in source
    assert "pilot " in source and "projected 0.067 core-hours" in source
    rows = SR.read_rows(out / "metrics.jsonl", screens["CW1"])
    text = "\n".join(SR.report_lines(rows, screens["CW1"]))
    assert text.count("- INCOMPLETE") == 18 and "- INCOMPLETE W t731: not run" in text
    assert sum(p.endswith(": 0 rows") for p in SR.check_metrics(rows, "held", screens["CW1"])) == 18


def test_check_metrics_names_every_gap(SR, CW):
    screen = CW.SCREENS["DEV"]
    rows = [{"screen": "DEV", "cohort": "dev", "arm": "W", "stratum": "t", "seed": 1, "rc": 0, "identity": "a"},
            {"screen": "DEV", "cohort": "dev", "arm": "W", "stratum": "t", "seed": 1, "rc": 0, "identity": "b"},
            {"screen": "DEV", "cohort": "dev", "arm": "TS", "stratum": "t", "seed": 3, "rc": 3, "identity": "a",
             "error": "missing"}]
    problems = SR.check_metrics(rows, "dev", screen, [("t", 1)])
    assert "W t1: 2 rows" in problems and "TS t1: 0 rows" in problems
    assert "rows carry more than one identity digest" in problems
    assert "TS t3: not in the cohort" in problems and any(p.startswith("TS t3: rc 3") for p in problems)


def test_identity_lines(SR, CW):
    lines = SR.identity_lines("rev", 2, "/x/src/chronicler/__init__.py", "/n.so abc", CW.SCREENS["CW1"])
    assert lines[:5] == ["source rev", "dirty 2 tracked files", "chronicler /x/src/chronicler/__init__.py",
                         "native /n.so abc", f"interpreter {SR.PY}"]
    sha = lambda p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest()  # noqa: E731
    assert lines[5:] == [f"runner {sha('scripts/screen_runner.py')} scripts/screen_runner.py",
                         f"screens {sha('scripts/connected_world_screens.py')} scripts/connected_world_screens.py",
                         f"registry {sha('scripts/seed_registry.json')} scripts/seed_registry.json"]


def test_check_command_reports_stubs_not_ready(SR, CW, capsys):
    assert CW.main(["check", "--screen", "all"]) == 2
    text = capsys.readouterr().out
    for name in ("CW1", "CW2", "CW3", "CW4", "CW5", "CW6"):
        assert f"{name}: seeds OK" in text and f"{name}: NOT READY" in text
    assert "DEV: extractor, packages, 2 arms and 3 outcomes (2 primary): OK" in text
    assert CW.main(["check", "--screen", "DEV"]) == 0
    assert CW.main(["registry"]) == 0
    assert "reserved cw1-held-t: template 731-736" in capsys.readouterr().out


def test_arm_command_lines_are_checked_by_the_parser_and_catalog(SR, CW):
    dev = CW.SCREENS["DEV"]
    assert SR.check_screen(dev) == []
    bad = dataclasses.replace(dev, arms={"W": ((), None), "TS": (("--commons-rules",), "W")})
    assert any("requires --timber-stock" in p for p in SR.check_screen(bad))
    typo = dataclasses.replace(dev, arms={"W": ((), None), "TS": (("--timber-stocks",), "W")})
    assert any("does not parse" in p for p in SR.check_screen(typo))
    orphan = dataclasses.replace(dev, arms={"W": ((), None), "TS": (("--timber-stock",), "X")})
    assert any("do not lead to the root" in p for p in SR.check_screen(orphan))


# --- Review findings (M1, m1-m5, m8, n1, n3, n7) ------------------------------------------

def _held_argv(tmp_path, out="out", jobs="1", pilot=None, extra=()):
    return [str(tmp_path / out), "--screen", "CW1", "--cohort", "held", "--jobs", jobs,
            "--pilot", str(pilot or _pilot(tmp_path, 10.0)), *extra]


def test_m1_ceiling_counts_the_runs_in_flight(SR, CW, tmp_path):
    """Runs take 100x the pilot: after the first batch of three, no run starts whose cost,
    with the runs in flight, would pass the ceiling (before, six started: 1.67 core-hours)."""
    screens = {"CW1": _held_screen(SR, CW, tmp_path, ceiling=1.0)}
    fake = FakeRuntime(SR, seconds=1000.0)
    rc = SR.run_main(_held_argv(tmp_path, jobs="3"), screens, fake.rt)
    assert rc == SR.RC_CEILING and len(fake.calls) == 3
    rows = SR.read_rows(tmp_path / "out" / "metrics.jsonl", screens["CW1"])
    assert sum(SR.run_seconds(r) for r in rows) == 3000.0 <= 3600
    source = (tmp_path / "out" / "source.txt").read_text()
    assert "stopped at the compute ceiling (1.0 core-hours): 0.833 used, 0.000 expected in flight, " \
           "the next run expected 1000.0 s; 21 runs not started" in source
    assert "expected seconds per run: max of the pilot mean per arm and stratum (TS p 10.0" in source


def test_m1_runs_that_fit_with_the_runs_in_flight_still_start(SR, CW, tmp_path):
    screens = {"CW1": _held_screen(SR, CW, tmp_path, ceiling=1.0)}
    fake = FakeRuntime(SR, seconds=100.0)            # 24 runs x 100 s = 0.67 core-hours: all fit
    assert SR.run_main(_held_argv(tmp_path, jobs="3"), screens, fake.rt) == 0 and len(fake.calls) == 24


def test_m1_held_identity_and_ledger(SR, CW, tmp_path):
    screens = {"CW1": _held_screen(SR, CW, tmp_path, ceiling=10.0)}
    fake = FakeRuntime(SR)
    assert SR.run_main(_held_argv(tmp_path), screens, fake.rt) == 0
    source = (tmp_path / "out" / "source.txt").read_text()
    prereg = screens["CW1"].preregistration
    line = f"preregistration {hashlib.sha256(prereg.read_bytes()).hexdigest()} {prereg.resolve()}"
    assert source.splitlines()[:3] == [*IDENTITY, line]                      # m4: the preregistration's hash
    rows = SR.read_rows(tmp_path / "out" / "metrics.jsonl", screens["CW1"])
    assert {r["identity"] for r in rows} == {hashlib.sha256("\n".join([*IDENTITY, line]).encode()).hexdigest()}
    held = json.loads((tmp_path / "out" / "held-run.json").read_text())
    assert held["cohort"] == "held" and held["out"] == str((tmp_path / "out").resolve())
    assert held["seeds"] == {"template": list(range(731, 737)), "procedural": list(range(831, 837))}
    assert SR.ledger_entries(fake.ledger) == [held]


def test_m1_m4_a_changed_preregistration_refuses_the_resume(SR, CW, tmp_path):
    screens = {"CW1": _held_screen(SR, CW, tmp_path, ceiling=1.0)}
    fake = FakeRuntime(SR, seconds=1000.0)
    assert SR.run_main(_held_argv(tmp_path), screens, fake.rt) == SR.RC_CEILING
    prereg = screens["CW1"].preregistration
    prereg.write_text(prereg.read_text() + "\nA definition changed after the run started.\n")
    with pytest.raises(SystemExit, match="resume refused: .*preregistration changed"):
        SR.run_main([*_held_argv(tmp_path), "--resume"], screens, FakeRuntime(SR, ledger=fake.ledger).rt)


def test_m1_a_second_held_run_is_refused_while_the_first_is_recorded(SR, CW, tmp_path, registry):
    screens = {"CW1": _held_screen(SR, CW, tmp_path, ceiling=10.0)}
    fake = FakeRuntime(SR)
    assert SR.run_main(_held_argv(tmp_path, out="held1"), screens, fake.rt) == 0
    # A fresh held run into another folder is refused on the ledger, before any run.
    again = FakeRuntime(SR, ledger=fake.ledger)
    with pytest.raises(SystemExit, match=r"a held run of CW1 was started at .* into .*held1 .*resume it there"):
        SR.run_main(_held_argv(tmp_path, out="held2"), screens, again.rt)
    assert again.calls == []
    # The recorded run itself resumes (nothing left to run); without its ledger entry it does not.
    assert SR.run_main([*_held_argv(tmp_path, out="held1"), "--resume"], screens, again.rt) == 0
    with pytest.raises(SystemExit, match="the ledger .* records no held run"):
        SR.run_main([*_held_argv(tmp_path, out="held1"), "--resume"], screens, FakeRuntime(SR).rt)
    # mark-run records it in the registry: every clone then refuses the cohort as reused.
    reg_path = tmp_path / "registry.json"
    reg_path.write_text(SR.dump_registry(registry))
    assert SR.mark_run_main([str(tmp_path / "held1"), "--screen", "CW1", "--registry", str(reg_path)], screens) == 0
    marked = SR.load_registry(reg_path)
    assert SR.validate_registry(marked) == []
    entries = [e for e in marked["entries"] if e.get("screen") == "CW1"]
    assert {e["status"] for e in entries} == {"run"}
    assert {e["held_run"]["complete"] for e in entries} == {True} and {e["held_run"]["rows"] for e in entries} == {24}
    problems, _ = SR.check_seeds(screens["CW1"], marked)
    assert any("were already run (reused)" in p for p in problems)
    with pytest.raises(SystemExit, match="mark-run refused: cw1-held-t is run"):
        SR.mark_run_main([str(tmp_path / "held1"), "--screen", "CW1", "--registry", str(reg_path)], screens)


def test_registry_file_is_its_own_dump(SR, registry):
    assert SR.dump_registry(registry) == SR.REGISTRY.read_text(encoding="utf-8")


def test_m5_reserve_cohort_for_a_named_screen(SR, CW, tmp_path, registry):
    screens = {"CW1": _held_screen(SR, CW, tmp_path, ceiling=10.0), "CW2": _held_screen(SR, CW, tmp_path, 10.0)}
    argv = [str(tmp_path / "reserve"), "--screen", "CW1", "--cohort", "reserve", "--jobs", "1",
            "--pilot", str(_pilot(tmp_path, 10.0))]
    with pytest.raises(SystemExit, match="--reason is required with --cohort reserve"):
        SR.run_main(argv, screens, FakeRuntime(SR).rt)
    with pytest.raises(SystemExit, match="--reason is required with --cohort reserve, and only there"):
        SR.run_main([*_held_argv(tmp_path), "--reason", "x"], screens, FakeRuntime(SR).rt)
    fake = FakeRuntime(SR)
    reason = "CW1's held run failed at a fixed extractor bug"
    assert SR.run_main([*argv, "--reason", reason], screens, fake.rt) == 0
    seeds = {int(c[c.index("--seed") + 1]) for c in fake.calls}
    assert seeds == set(range(791, 797)) | set(range(891, 897))
    source = (tmp_path / "reserve" / "source.txt").read_text()
    assert "run: screen CW1; cohort reserve;" in source and f"reason: {reason}" in source
    rows = SR.read_rows(tmp_path / "reserve" / "metrics.jsonl", screens["CW1"])
    assert {r["cohort"] for r in rows} == {"reserve"}
    assert SR.check_metrics(rows, "reserve", screens["CW1"], seeds=SR.cohort_seeds(screens["CW1"], "reserve")) == []
    # The reserve is used once by the whole program.
    with pytest.raises(SystemExit, match="a reserve run of CW1 was started"):
        SR.run_main([str(tmp_path / "r2"), "--screen", "CW2", "--cohort", "reserve", "--reason", "x", "--pilot",
                     str(_pilot(tmp_path, 10.0))], screens, FakeRuntime(SR, ledger=fake.ledger).rt)
    reg_path = tmp_path / "registry.json"
    reg_path.write_text(SR.dump_registry(registry))
    assert SR.mark_run_main([str(tmp_path / "reserve"), "--screen", "CW1", "--registry", str(reg_path)], screens) == 0
    marked = SR.load_registry(reg_path)
    reserve = [e for e in marked["entries"] if e.get("cohort") == "reserve"]
    assert {(e["status"], e["screen"], e["held_run"]["reason"]) for e in reserve} == {("run", "CW1", reason)}
    assert SR.validate_registry(marked) == []
    assert any("was already used (run, by CW1)" in p for p in SR.check_reserve(screens["CW2"], marked))


def test_m4_pilot_of_another_identity_is_refused(SR, CW, tmp_path):
    screens = {"CW1": _held_screen(SR, CW, tmp_path, ceiling=10.0)}
    cases = [
        (_pilot(tmp_path, 10.0, rows_identity="OTHER", name="p1"), (), "its rows carry identity"),
        (_pilot(tmp_path, 10.0, identity=("source abc", "dirty 0 tracked files", "runner 99 scripts/screen_runner.py"),
                name="p2"), (), "runner '99 scripts/screen_runner.py' differs"),
        (_pilot(tmp_path, 10.0, identity=("source abc", "dirty 3 tracked files"), name="p3"), (), "dirty"),
        (_pilot(tmp_path, 10.0, identity=("source old", "dirty 0 tracked files"), name="p4"),
         ("docs/x.md", "scripts/screen_runner.py"), "differs from abc in code: \\['scripts/screen_runner.py'\\]"),
    ]
    for pilot, changed, message in cases:
        with pytest.raises(SystemExit, match=message):
            SR.run_main(_held_argv(tmp_path, pilot=pilot), screens, FakeRuntime(SR, changed=changed).rt)
    missing = tmp_path / "p5"
    missing.mkdir()
    (missing / "metrics.jsonl").write_text(_pilot(tmp_path, 10.0, name="p6").read_text())
    with pytest.raises(SystemExit, match="source.txt is missing"):
        SR.run_main(_held_argv(tmp_path, pilot=missing / "metrics.jsonl"), screens, FakeRuntime(SR).rt)
    # A revision that differs only outside the code (the freeze commit) is accepted.
    docs_only = _pilot(tmp_path, 10.0, identity=("source old", "dirty 0 tracked files"), name="p7")
    assert SR.run_main(_held_argv(tmp_path, pilot=docs_only), screens, FakeRuntime(SR, changed=("docs/x.md",)).rt) == 0


def test_m2_harm_panel_for_every_arm(SR, CW):
    dev = CW.SCREENS["DEV"]
    screen = dataclasses.replace(dev, arms={**dev.arms, "TS2": (("--timber-stock",), "TS")},
                                 outcomes=tuple(o for o in dev.outcomes if o.control is None) + (
                                     _outcome(SR, 8, arm="TS", control="W"),))
    assert SR.harm_pairs(screen) == [("TS", "W"), ("TS2", "TS")]
    only_alone = dataclasses.replace(dev, outcomes=tuple(o for o in dev.outcomes if o.control is None))
    assert SR.harm_pairs(only_alone) == [("TS", "W")]
    rows = [_row(SR, CW, "W", "t", 1, make_bundle()), _row(SR, CW, "TS", "t", 1, make_bundle(timber=True))]
    rows.append({**_row(SR, CW, "TS", "t", 1, make_bundle(timber=True)), "arm": "TS2"})
    text = "\n".join(SR.report_lines(rows, screen))
    assert "| TS2 - TS | Population at the end (sum over civilizations) | t | 1: +0 |" in text
    assert "| TS - W | Timber stand share of capacity at the end | t | 1: not recorded |" in text


def test_m3_harms_without_an_agent_economy_are_not_recorded(SR):
    bundle = make_bundle(migration=False)
    for snap in bundle["history"]:
        for row in snap["food_accounting"]["regions"]:
            row["native"], row["sufficiency_after_relief"] = None, None
    harm, problems = SR.harm_panel(bundle)
    assert problems == []
    assert harm["wealth_gini"]["state"] == "not_recorded" and "no agent pool" in harm["wealth_gini"]["note"]
    assert harm["food_shortfall"] == {"state": "not_recorded", "value": None,
                                      "note": "no native food ledger in this run (no agent economy)"}
    partly = make_bundle()
    for row in partly["history"][0]["food_accounting"]["regions"]:
        row["native"] = None
    assert SR.harm_food_shortfall(partly)["note"] == "no native food ledger at turns [1]: the run total is unknown, not zero"
    mixed = make_bundle()
    mixed["history"][0]["food_accounting"]["regions"][0]["native"] = None
    assert SR.harm_food_shortfall(mixed)["state"] == "malformed"


@pytest.mark.parametrize("edit, state, note", [
    (lambda h: h[-1]["livelihoods"]["timber_stock"].update(observed=False, totals=None, regions=None),
     "not_recorded", "the last timber account was not observed: unknown, not zero"),
    (lambda h: h[-1]["livelihoods"].pop("timber_stock"), "not_recorded", "no timber stock record in the last snapshot"),
    (lambda h: h[0]["livelihoods"]["timber_stock"].update(observed=False, totals=None), "recorded", ""),
    (lambda h: h[-1]["livelihoods"].update(timber_stock="x"), "malformed", "not an object"),
])
def test_m3_forest_stand_reads_the_last_snapshot(SR, edit, state, note):
    bundle = make_bundle(timber=True)
    edit(bundle["history"])
    harm = SR.harm_forest_stand(bundle)
    assert harm["state"] == state and note in harm["note"]


def test_m8_records_before_the_last_snapshot_are_checked(SR, CW):
    bundle = make_bundle(timber=True)
    bundle["history"][0]["livelihoods"]["timber_stock"] = ["not", "a", "record"]
    _pk, problems = SR.package_problems(CW.SCREENS["DEV"], bundle, ["--timber-stock"])
    assert problems == ["timber_stock: records that are not objects at turns [1]"]
    retail = SR.Package("--household-retail", ("livelihoods", "household_retail"),
                        counters_module="chronicler.household_retail_state", counters=("priced_out_persons",))
    screen = dataclasses.replace(CW.SCREENS["DEV"], packages=(retail,))
    bundle = make_bundle(retail=True)
    bundle["history"][0]["livelihoods"]["household_retail"]["counters"]["priced_out_persons"] = "2"
    bundle["history"][1]["livelihoods"]["household_retail"]["counters"] = None
    _pk, problems = SR.package_problems(screen, bundle, ["--household-retail"])
    assert problems == ["household_retail: counters missing at turns [2]",
                        "household_retail: non-numeric counters ['priced_out_persons']"]


def test_n1_a_malformed_registry_is_refused_not_crashing(SR, CW, registry):
    reg = copy.deepcopy(registry)
    reg["entries"][0]["seeds"] = [[10]]
    del reg["entries"][1]["stratum"]
    problems, _notes = SR.check_seeds(CW.SCREENS["CW1"], reg)
    assert problems and all("CW1" not in p for p in problems)


def test_n7_a_failed_run_keeps_its_output(SR, CW, tmp_path):
    fake = FakeRuntime(SR, rc=1)
    argv = [str(tmp_path / "out"), "--screen", "DEV", "--cohort", "dev", "--worlds", "t1", "--jobs", "1"]
    assert SR.run_main(argv, CW.SCREENS, fake.rt) == SR.RC_FAILED
    assert (tmp_path / "out" / "runs" / "W-t1" / "chronicle_bundle.json").exists()
