"""Fresh joint flag qualification using real native cargo and complete turns."""
import pytest

from scripts.qualify_third_wave import run_case
from scripts.third_wave_controls import strip_dormant_fields


@pytest.mark.native
@pytest.mark.parametrize("fishery,aid", [(False, False), (True, False), (False, True), (True, True)])
@pytest.mark.parametrize("seed,hops", [(42, 3), (77, 5)])
def test_joint_full_turn_accounting_and_determinism(fishery, aid, seed, hops):
    pytest.importorskip("chronicler_agents")
    first = run_case(fishery, aid, seed, hops)
    second = run_case(fishery, aid, seed, hops)
    assert first == second  # all parsed values, full world + native snapshot hashes
    rows = first["history"]
    assert any(r["trip_stats"]["total_in_transit_qty"] > 0 for r in rows)
    assert any(r["trip_stats"]["completed_trips"] > 0 and r["trip_stats"]["avg_trip_duration"] >= hops for r in rows)
    assert rows[-1]["trip_stats"]["total_in_transit_qty"] == 0
    assert sum(r["economy"]["oracle_ledger"]["transit_loss"].get("grain", 0.) for r in rows) > 0
    assert all(r["economy"]["oracle_ledger"]["transit_loss"].get("salt", 0.) == 0 for r in rows)
    if aid:
        # Which adjacent donor sends is emergent (donor stocks net of merchant
        # cargo commitments). Since the 2026-10 food-balance corrections A's
        # free surplus alone covers both recipients in some of these runs;
        # multi-donor sharing is pinned deterministically by
        # test_mutual_aid_long_cargo.py::test_multiple_donors_competing_recipients_caps_and_exhaustion.
        donors = {t["donor"] for r in rows for t in r["transfers"]}
        assert "A" in donors and donors <= {"A", "B"}
        assert {t["recipient"] for r in rows for t in r["transfers"]} == {"First", "Second"}
        assert sum(sum(r["aid_treasury_debits"]) for r in rows) > 0
    else:
        assert all(not r["transfers"] and not r["aid_treasury_debits"] for r in rows)
    if fishery:
        assert any(r["fishery"]["harvest"] > 0 for r in rows[:16])
        assert any(r["fishery"]["yield_per_worker"] < r["fishery"]["potential"] for r in rows[:16])
        assert all(r["fishery"]["harvest"] == 0 and r["fishery"]["stock"] > r["fishery"]["before"] for r in rows[16:])
        assert any(r["economy"]["food_sufficiency"]["A"] < 1 and not r["fishery"]["yield_famine_predicate"] for r in rows)


@pytest.mark.native
@pytest.mark.parametrize("disruption", ["cancel", "return", "death"])
def test_joint_real_cargo_cleanup_through_full_turn(disruption):
    pytest.importorskip("chronicler_agents")
    rows = run_case(True, True, disruption=disruption)["history"]
    assert rows[-1]["trip_stats"]["total_in_transit_qty"] == 0
    if disruption == "cancel":
        assert sum(rows[2]["economy"]["oracle_ledger"]["departures"].values()) == 0
        assert sum(rows[2]["economy"]["oracle_ledger"]["returns"].values()) == 0
    else:
        assert sum(rows[3]["economy"]["oracle_ledger"]["returns"].values()) > 0
    if disruption == "death":
        assert rows[2]["trip_stats"]["active_trips"] == 0
        assert all(sum(row["economy"]["oracle_ledger"]["returns"].values()) == 0 for row in rows[4:])


def test_dormancy_projection_rejects_changed_metadata():
    from chronicler.models import WorldState
    data = WorldState(name="Dormancy", seed=42).model_dump(mode="json")
    data["fishery_experiment"]["enabled"] = True
    with pytest.raises(AssertionError):
        strip_dormant_fields(data)
