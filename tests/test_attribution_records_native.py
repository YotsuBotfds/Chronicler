"""D2 attribution records on the real compiled extension (hybrid runs).

Development worlds only: procedural 32x10 seed 13 (60 turns; with campaigns:
battles, attrition, natural deaths of enlisted soldiers, sieges, occupations,
annexations, granary seizures and a peace treaty with reparations, measured on
this source) and template seed 42 with every livelihoods payer on (retail in
every region). Nothing is mocked.
"""
from __future__ import annotations

import json
import sys

import pytest

pytest.importorskip("chronicler_agents")
pytestmark = pytest.mark.native

HYBRID = ["--agents", "hybrid", "--simulate-only"]
WAR_WORLD = ["--seed", "13", "--turns", "60", "--worldgen", "procedural", "--regions", "32", "--civs", "10",
             "--grain-reserves"]
ALL = ["--grain-reserves", "--public-grain-shipments", "--grain-storage", "--scholarship", "--academy-services",
       "--workshops", "--food-allocation", "--timber-stock", "--grain-convoys", "--commons-rules",
       "--learning-cohorts", "--workshop-payroll", "--relocation-costs", "--local-budgets", "--apprenticeship",
       "--repair-projects", "--veteran-reintegration", "--remittances", "--clearing-protection",
       "--operating-wear", "--timber-supply", "--recovery-crews", "--maintenance-obligation",
       "--household-retail", "--household-retail-boundary=all"]
RECORDS = ["--attribution-records"]


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
    """Remove only the records: every ``attribution_records`` key, and a
    ``livelihoods`` container that held nothing else."""
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            if key == "attribution_records":
                continue
            item = _strip(item)
            if key == "livelihoods" and isinstance(item, dict) and set(item) <= {"schema_version"} \
                    and "attribution_records" in value[key]:
                continue
            out[key] = item
        return out
    if isinstance(value, list):
        return [_strip(item) for item in value]
    return value


def _frames(bundle):
    from chronicler.attribution_records import record_status
    out = []
    for snap in bundle["history"]:
        status, frame = record_status(snap)
        assert status in ("recorded", "recorded_zero"), (snap.get("turn"), status)
        out.append(frame)
    return out


@pytest.mark.parametrize("case", ["war_world", "all_switches"])
def test_observer_identity_full_world_dump(tmp_path, monkeypatch, case):
    argv = (HYBRID + WAR_WORLD) if case == "war_world" else (HYBRID + ["--seed", "42", "--turns", "40"] + ALL)
    _cli(monkeypatch, tmp_path / "off", *argv)
    _cli(monkeypatch, tmp_path / "on", *argv, *RECORDS)
    off, on = _bundle(tmp_path / "off"), _bundle(tmp_path / "on")
    assert len(_frames(on)) == len(on["history"])
    assert "attribution_records" in on["world_state"]["livelihoods"]
    assert _strip(on["history"]) == off["history"]
    assert _strip(on["world_state"]) == off["world_state"]
    assert _strip(on) == off
    states = [json.loads((tmp_path / side / "state.json").read_text()) for side in ("off", "on")]
    assert _strip(states[1]) == states[0]
    assert (tmp_path / "off" / "chronicle.md").read_bytes() == (tmp_path / "on" / "chronicle.md").read_bytes()


def test_a_natural_war_run_is_attributed_and_closes(tmp_path, monkeypatch):
    _cli(monkeypatch, tmp_path, *HYBRID, *WAR_WORLD, *RECORDS)
    bundle = _bundle(tmp_path)
    frames = _frames(bundle)
    regions = len(bundle["world_state"]["regions"])
    by_cause: dict[str, int] = {}
    seizures = 0
    for frame in frames:
        casualties = frame["casualties"]
        assert casualties["unresolved"] == 0, frame["turn"]
        for row in casualties["rows"]:
            by_cause[row["cause"]] = by_cause.get(row["cause"], 0) + row["deaths"]
            assert row["victim"] is not None and row["war"], (frame["turn"], row)
            if row["class"] == "combat":
                assert row["actor"] is not None and row["actor"] != row["victim"], (frame["turn"], row)
            else:
                assert row["actor"] is None
        assert all(a["closes"] is not False for a in casualties["armies"]), (frame["turn"], casualties["armies"])
        granary = frame["granary"]
        assert granary["active"] and granary["unattributed"] == 0, frame["turn"]
        for s in granary["seizures"]:
            assert s["actor"] is not None and s["victim"] is not None and 0 <= s["region"] < regions
            assert s["actor"] != s["victim"] and s["grain"] > 0
        seizures += len(granary["seizures"])
        for pair in frame["burdens"]["pairs"]:
            if pair["kind"] in ("occupation_plunder", "occupation_requisition", "food_requisition",
                                "granary_seizure", "conquest_stock_loss"):
                assert not pair["internal"], (frame["turn"], pair)
    # This world and source: combat, attrition and natural deaths all occur.
    assert by_cause.get("battle", 0) > 0 and by_cause.get("attrition", 0) > 0 and by_cause.get("natural", 0) > 0
    assert seizures > 0
    record = bundle["history"][-1]["livelihoods"]["attribution_records"]
    assert record["counters"].get("army_closures_failed", 0) == 0
    assert record["counters"]["army_closures_checked"] > 0
    assert record["lifetime"]["deaths_natural"] == by_cause["natural"]


def test_retail_war_losses_are_all_attributed_on_the_all_switch_world(tmp_path, monkeypatch):
    _cli(monkeypatch, tmp_path, *HYBRID, "--seed", "42", "--turns", "40", *ALL, *RECORDS)
    for frame in _frames(_bundle(tmp_path)):
        assert frame["burdens"]["retail_unattributed"] == 0, frame["turn"]
        assert frame["granary"]["unattributed"] == 0, frame["turn"]
