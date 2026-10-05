"""Multi-edge private qualification with independent accounting and real ABI cargo."""
import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("long_cargo", Path(__file__).resolve().parents[1] / "scripts/mutual_aid_long_cargo.py")
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)


def test_multiple_donors_competing_recipients_caps_and_exhaustion():
    result = fixture.run_policy()
    rows = result["history"]
    # Independent hand-calculated first dispatch: three donors share capacities,
    # First reaches its 2.5 delivery cap and Second receives the remaining budget.
    expected = [("A", "First", 1., .95), ("B", "First", 1.55, 1.55),
                ("B", "Second", .95, .95), ("C", "Second", 2.5, 2.375)]
    actual = [(t["donor"], t["recipient"], sum(t["sent"].values()), sum(t["received"].values())) for t in rows[0]["transfers"]]
    for a, e in zip(actual, expected, strict=True):
        assert a[:2] == e[:2]
        assert a[2:] == pytest.approx(e[2:])
    assert rows[2]["after"] == {"A": {"grain": 24., "salt": 0.}, "B": {"grain": 0., "salt": 23.},
                                "C": {"grain": 20., "salt": 0.}, "First": {"grain": 1.45, "salt": 3.55},
                                "Second": {"grain": 6.15, "salt": .95}}
    assert all(not r["transfers"] for r in rows[3:])
    assert rows[-1]["treasury"] > 0  # exhaustion is food reserve, not funding.
    assert fixture.run_policy(reverse=True)["history"] == rows


def test_simultaneous_requests_share_a_finite_treasury():
    result = fixture.run_policy(treasury=1)
    first = result["history"][0]
    assert [(t["donor"], t["recipient"]) for t in first["transfers"]] == [("A", "First")]
    assert first["treasury"] == 0
    assert all(not r["transfers"] for r in result["history"][1:])


def test_multi_edge_disabled_policy_is_exact_noop():
    for row in fixture.run_policy(enabled=False)["history"]:
        assert row["before"] == row["after"]
        assert not row["transfers"]
        assert row["treasury"] == 100


@pytest.mark.native
@pytest.mark.parametrize("hops,seed", [(3, 42), (4, 42), (5, 42), (5, 77)])
def test_long_cargo_independent_per_good_conservation_and_once_only_settlement(hops, seed):
    pytest.importorskip("chronicler_agents")
    result = fixture.run_native(hops=hops, seed=seed)
    rows = result["history"]
    assert sum(sum(r["cargo"].values()) > 0 for r in rows) >= hops - 1
    assert any(r["trip_stats"]["completed_trips"] > 0 and r["trip_stats"]["avg_trip_duration"] >= hops for r in rows)
    assert any(r["knowledge_stats"]["merchant_plans_bootstrap"] + r["knowledge_stats"]["merchant_plans_packet_driven"] > 0 for r in rows[1:])
    assert {t["donor"] for r in rows for t in r["aid"]["transfers"]} == {"A", "B"}
    assert any({t["recipient"] for t in r["aid"]["transfers"]} == {"First", "Second"} for r in rows)
    assert any(r["economy_replay_ledger"] is not None for r in rows)
    assert sum(r["oracle_ledger"]["transit_loss"]["grain"] for r in rows) > 0
    assert all(r["oracle_ledger"]["transit_loss"]["salt"] == 0 for r in rows)
    assert rows[-1]["cargo"] == pytest.approx({"grain": 0., "salt": 0.}, abs=fixture.TOL)
    assert all(c["reserved"] == c["pending_departure"] == 0 for c in rows[-1]["after_economy_commitments"])
    assert all(not r["aid"]["transfers"] for r in rows[-5:])


@pytest.mark.native
@pytest.mark.parametrize("disruption", ["cancel", "return"])
def test_real_loading_invalidation_and_inflight_return(disruption):
    pytest.importorskip("chronicler_agents")
    rows = fixture.run_native(disruption=disruption)["history"]
    if disruption == "cancel":
        assert sum(c["reserved"] for c in rows[1]["commitments"]) > 0
        assert sum(rows[2]["oracle_ledger"]["departures"].values()) == 0
        assert sum(rows[2]["oracle_ledger"]["returns"].values()) == 0
    else:
        assert rows[2]["trip_stats"]["unwind_count"] > 0
        assert sum(rows[3]["oracle_ledger"]["returns"].values()) > 0
    assert rows[-1]["cargo"] == pytest.approx({"grain": 0., "salt": 0.}, abs=fixture.TOL)


@pytest.mark.native
def test_long_cargo_disabled_native_path_retains_exact_stock_and_treasury_noop():
    pytest.importorskip("chronicler_agents")
    rows = fixture.run_native(enabled=False)["history"]
    assert any(sum(r["cargo"].values()) > 0 for r in rows)
    for r in rows:
        assert r["aid"]["before"] == r["aid"]["after"]
        assert not r["aid"]["transfers"]
        assert r["aid"]["treasury"] == 100


@pytest.mark.native
def test_catastrophe_death_releases_real_cargo_before_slot_reuse():
    pytest.importorskip("chronicler_agents")
    rows = fixture.run_native(disruption="death")["history"]
    assert sum(rows[2]["cargo"].values()) > 0
    assert rows[2]["trip_stats"]["active_trips"] == 0
    assert sum(rows[3]["oracle_ledger"]["returns"].values()) > 0
    assert rows[3]["cargo"] == pytest.approx({"grain": 0., "salt": 0.}, abs=fixture.TOL)
    assert all(sum(r["oracle_ledger"]["returns"].values()) == 0 for r in rows[4:])
