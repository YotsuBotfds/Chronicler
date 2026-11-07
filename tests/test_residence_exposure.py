"""Motive-free residential observations and guarded public-health exposure.

Constructed trajectories use the existing X1 post-tick fixture. They do not
assert a reason for a move or relabel every migrant as forcibly displaced.
"""
from __future__ import annotations

import copy
import pickle
from types import SimpleNamespace

import pytest

from chronicler import public_health as PH, residence_ledger as RL
from chronicler.public_health_state import PublicHealthState
from chronicler.residence_ledger_state import ResidenceLedgerState
from tests.test_residence_ledger import FakeSim, _world, step

ARRIVALS = "recent_residence_arrivals"
UNKNOWN = "recent_residence_arrivals_unknown_reason"


def _start(*, people=1):
    world, sim = _world(), FakeSim()
    for aid in range(1, people + 1):
        sim.add(aid, 0)
    step(world, sim)
    return world, sim


def _state(world):
    return world.livelihoods.residence_ledger


def _region(frame, rid):
    return next(r for r in frame["regions"] if r["region"] == rid)


def _environment(world, crowding="density_only"):
    # Install only the consumer state: no extra package or invented payer is
    # needed to ask the production environment reader for the prior X1 frame.
    object.__setattr__(world.livelihoods, "public_health", PublicHealthState(crowding=crowding))
    return PH.environment_factors(world)


def _physical(frame):
    # Sparse X1 region rows may exist solely for legacy motive/anchor metadata.
    # Missing physical zero rows and explicit physical zero rows are equivalent.
    return [(r["region"], r["residents"], r[ARRIVALS]) for r in frame["regions"]
            if r["residents"] or r[ARRIVALS]]


def _remove_arrival_group(frame):
    frame.pop("arrival_diagnostics", None)
    for values in [frame["totals"], *frame["regions"]]:
        values.pop(ARRIVALS, None)
        values.pop(UNKNOWN, None)


@pytest.mark.parametrize("known", ["material_need", "battle_memory", "wage"])
def test_identical_physical_trajectories_have_equal_density_exposure_regardless_of_reason(known):
    a, sa = _start()
    b, sb = _start()
    for frm, to in [(0, 1), (1, 2), (2, 0)]:
        fa = step(a, sa, moves=[(1, frm, to, known)])
        fb = step(b, sb, moves=[(1, frm, to, None)])
        assert sa.people == sb.people
        assert _physical(fa) == _physical(fb)
        assert fa["totals"][ARRIVALS] == fb["totals"][ARRIVALS] == 1
        assert fa["totals"][UNKNOWN] == 0
        assert fb["totals"][UNKNOWN] == 1
        ea, eb = _environment(a), _environment(b)
        assert [r["crowding_factor"] for r in ea] == [1.0] * len(a.regions)
        assert [r["crowding_factor"] for r in eb] == [1.0] * len(b.regions)
        assert [r["recent_arrival_share"] for r in ea] == [r["recent_arrival_share"] for r in eb]


def test_legacy_label_coupling_remains_an_explicit_reproduction_control_only():
    known, sk = _start()
    unknown, su = _start()
    step(known, sk, moves=[(1, 0, 1, "material_need")])
    step(unknown, su, moves=[(1, 0, 1, None)])
    assert sk.people == su.people
    assert _environment(known, "legacy_displacement")[1]["crowding_factor"] == 1.25
    assert _environment(unknown, "legacy_displacement")[1]["crowding_factor"] == 1.0
    # This equality is the regression that failed on main2726. Motive unknown
    # does not physically erase a person from the destination.
    assert _environment(known)[1]["crowding_factor"] == _environment(unknown)[1]["crowding_factor"] == 1.0


def test_multiple_same_turn_moves_and_return_count_the_living_person_once_at_final_residence():
    world, sim = _start()
    frame = step(world, sim, moves=[(1, 0, 1, None), (1, 1, 0, None), (1, 0, 2, None)])
    assert frame["totals"]["moves"] == 3
    assert frame["totals"][ARRIVALS] == frame["totals"][UNKNOWN] == 1
    assert _region(frame, 2)[ARRIVALS] == 1
    assert sum(r[ARRIVALS] for r in frame["regions"]) == 1
    frame = step(world, sim, moves=[(1, 2, 0, None)])
    assert frame["totals"][ARRIVALS] == _region(frame, 0)[ARRIVALS] == 1


@pytest.mark.parametrize("driver", [None, "material_need", "wage"])
def test_window_ages_out_after_twenty_calendar_turns_even_when_legacy_home_differs(driver):
    world, sim = _start()
    step(world, sim, moves=[(1, 0, 1, driver)])  # move at T2
    while world.turn <= 21:
        frame = step(world, sim)
    assert frame["turn"] == 21 and frame["totals"][ARRIVALS] == 1
    assert frame["arrival_diagnostics"]["window_turns"] == 20
    assert frame["arrival_diagnostics"]["complete"] is True
    assert _environment(world)[1]["recent_arrival_share"] == 1.0
    frame = step(world, sim)  # T22 − T2 ==20: outside [T−19,T]
    assert frame["totals"][ARRIVALS] == 0
    assert _environment(world)[1]["recent_arrival_share"] == 0.0


def test_first_seen_and_newborn_rows_are_not_invented_arrivals():
    world, sim = _start()
    sim.add(2, 2, origin=2, age=0)
    frame = step(world, sim)
    assert frame["totals"][ARRIVALS] == 0
    assert all(row.move_turn is None for row in _state(world).rows.values())
    assert frame["arrival_diagnostics"]["coverage_complete"] is True
    assert frame["arrival_diagnostics"]["window_complete"] is False
    assert all(r["recent_arrival_share"] is None for r in _environment(world))


def test_observation_window_completes_on_twentieth_write_not_twenty_first():
    world, sim = _start()
    while world.turn <= 19:
        frame = step(world, sim)
    assert frame["arrival_diagnostics"]["window_complete"] is False
    assert all(r["recent_arrival_share"] is None for r in _environment(world))
    frame = step(world, sim)
    assert frame["turn"] == 20
    diagnostic = frame["arrival_diagnostics"]
    assert diagnostic["window_turns"] == 20
    assert diagnostic["coverage_complete"] is diagnostic["window_complete"] is diagnostic["complete"] is True
    assert _environment(world)[0]["recent_arrival_share"] == 0.0


def test_death_and_a_new_stable_identity_cannot_inherit_a_recent_move():
    world, sim = _start()
    step(world, sim, moves=[(1, 0, 1, None)])
    sim.add(99, 1, age=0)
    frame = step(world, sim, deaths=[1])
    assert 1 not in _state(world).rows and 99 in _state(world).rows
    assert _state(world).rows[99].move_turn is None
    assert frame["totals"][ARRIVALS] == 0


def test_household_relationship_changes_do_not_duplicate_or_create_arrivals():
    from chronicler.ffi_constants import BOND_MARRIAGE
    world, sim = _start(people=3)
    sim.bonds = [(1, 2, BOND_MARRIAGE)]
    sim.people[3].update(age=8, parent_id_0=1, parent_id_1=2)
    frame = step(world, sim, moves=[(aid, 0, 1, None) for aid in (1, 2, 3)])
    assert _region(frame, 1)[ARRIVALS] == frame["totals"][ARRIVALS] == 3
    sim.bonds = []
    sim.people[3].update(parent_id_0=2, parent_id_1=0)
    frame = step(world, sim)
    assert frame["totals"]["moves"] == 0
    assert _region(frame, 1)[ARRIVALS] == frame["totals"][ARRIVALS] == 3


def test_ordinary_trip_is_not_a_residence_move_but_actual_unwind_relocation_is():
    world, sim = _start()
    sim.trips = {1}
    sim.people[1]["region"] = 2
    frame = step(world, sim)
    assert _state(world).rows[1].res == 0
    assert frame["totals"][ARRIVALS] == 0
    assert _state(world).rows[1].move_turn is None
    sim.trips.clear()  # the native trip unwound and left this person in2
    frame = step(world, sim)
    assert frame["totals"]["trip_relocations"] == 1
    assert frame["totals"]["moves"] == 0
    assert frame["totals"][ARRIVALS] == frame["totals"][UNKNOWN] == 1
    assert _region(frame, 2)[ARRIVALS] == 1


def test_recent_residential_arrival_clock_is_not_refreshed_by_an_ordinary_trip():
    world, sim = _start()
    step(world, sim, moves=[(1, 0, 1, None)])
    move_turn = _state(world).rows[1].move_turn
    sim.trips = {1}
    sim.people[1]["region"] = 2
    frame = step(world, sim)
    assert _state(world).rows[1].res == 1
    assert _state(world).rows[1].move_turn == move_turn
    assert _region(frame, 1)[ARRIVALS] == 1  # residence, not instantaneous physical presence
    assert _region(frame, 1)["in_transit"] == 1


def test_row_cap_and_deferred_residences_make_population_share_unknown(monkeypatch):
    monkeypatch.setattr(RL, "MAX_ROWS", 1)
    world, sim = _start(people=2)
    while world.turn <= 20:
        frame = step(world, sim)
    assert frame["arrival_diagnostics"]["window_complete"] is False
    assert frame["arrival_diagnostics"]["coverage_complete"] is False
    assert frame["arrival_diagnostics"]["complete"] is False
    assert all(r["recent_arrival_share"] is None for r in _environment(world))
    assert all(r["arrival_diagnostics_complete"] is False for r in _environment(world))


def test_deferred_traveller_is_unknown_coverage_and_is_not_a_new_residential_arrival():
    world, sim = _world(), FakeSim()
    sim.add(1, 0)
    sim.trips.add(1)
    frame = step(world, sim)
    assert frame["totals"]["deferred"] == 1 and frame["totals"][ARRIVALS] == 0
    assert frame["arrival_diagnostics"]["coverage_complete"] is False
    sim.trips.clear()
    frame = step(world, sim)
    assert frame["totals"][ARRIVALS] == 0
    assert _state(world).rows[1].move_turn is None


def test_recovered_row_cap_does_not_turn_unobserved_prior_arrivals_into_a_known_zero(monkeypatch):
    monkeypatch.setattr(RL, "MAX_ROWS", 1)
    world, sim = _start(people=2)  # id2 is alive but its residence row is refused
    step(world, sim, moves=[(2, 0, 1, None)])  # T2: an actual move outside coverage
    step(world, sim, deaths=[1])  # T3: the formerly held row dies
    while world.turn <= 20:
        frame = step(world, sim)
    # The current population is fully observed, but its T2 movement is still
    # inside the T1..T20 window and was never observed by the ledger. A current
    # complete headcount cannot retroactively establish a complete history.
    assert frame["totals"]["observed"] == frame["totals"]["alive"] == 1
    assert frame["totals"][ARRIVALS] == 0
    assert frame["arrival_diagnostics"]["coverage_complete"] is True
    assert frame["arrival_diagnostics"]["window_complete"] is False
    assert _environment(world)[1]["recent_arrival_share"] is None
    # Full coverage began at T4: the first entirely observed20-turn window is
    # T4..T23. The earlier actual arrival has then genuinely aged out.
    while world.turn <= 23:
        frame = step(world, sim)
    assert frame["arrival_diagnostics"]["complete"] is True
    assert _environment(world)[1]["recent_arrival_share"] == 0.0


@pytest.mark.parametrize("reset", ["gap", "pool"])
def test_observation_gap_or_pool_reset_starts_a_new_incomplete_window_without_old_identity(reset):
    world, sim = _start()
    step(world, sim, moves=[(1, 0, 1, None)])
    if reset == "gap":
        world.turn += 2
    else:
        RL.on_pool_reset(world)
        sim.people.clear()
        sim.add(1, 2)  # same integer may identify a different person after a pool reset
    frame = step(world, sim)
    assert frame["totals"][ARRIVALS] == 0
    assert frame["arrival_diagnostics"]["window_complete"] is False
    assert all(row.move_turn is None for row in _state(world).rows.values())
    assert all(r["recent_arrival_share"] is None for r in _environment(world))


def test_new_density_path_still_propagates_same_turn_and_future_read_refusals():
    world, sim = _start()
    step(world, sim, moves=[(1, 0, 1, None)])
    world.turn = _state(world).frame_turn
    with pytest.raises(RL.LedgerReadRefused, match="same-turn"):
        _environment(world)
    world.turn -= 1
    with pytest.raises(RL.LedgerReadRefused, match="same-turn"):
        _environment(world)


def test_legacy_frame_has_unknown_arrival_share_and_preserves_guarded_copy_semantics():
    world, sim = _start()
    frame = step(world, sim, moves=[(1, 0, 1, None)])
    _remove_arrival_group(frame)
    rows = _environment(world)
    assert all(r["recent_arrival_share"] is None for r in rows)
    assert all(r["arrival_diagnostics_complete"] is None for r in rows)
    assert all(r["crowding_factor"] == 1.0 for r in rows)
    copied = RL.read_frame(world, consumer_turn=world.turn)
    copied["totals"]["alive"] = -1
    assert _state(world).frame["totals"]["alive"] == 1


def test_new_recent_arrival_record_is_not_zero_when_this_turn_has_no_move_or_spell():
    world, sim = _start()
    step(world, sim, moves=[(1, 0, 1, None)])
    frame = step(world, sim)
    assert frame["totals"]["moves"] == frame["totals"]["displaced"] == 0
    assert frame["totals"][ARRIVALS] == 1
    snapshot = {"livelihoods": {"residence_ledger": RL.snapshot_summary(world)}}
    status, observed = RL.record_status(snapshot)
    assert status == "recorded" and observed["totals"][ARRIVALS] == 1
    # Older snapshots carry no assertion about this diagnostic at all. Their
    # old zero-status remains compatible, while arrival information is absent.
    _remove_arrival_group(snapshot["livelihoods"]["residence_ledger"]["frame"])
    status, observed = RL.record_status(snapshot)
    assert status == "recorded_zero" and "arrival_diagnostics" not in observed
    assert ARRIVALS not in observed["totals"]


@pytest.mark.parametrize("damage", [
    "counts_without_metadata", "metadata_without_counts", "missing_half", "negative",
    "unknown_exceeds_arrivals", "regional_arrival_sum", "regional_unknown_sum",
    "noninteger", "metadata_none", "inconsistent_complete", "wrong_window", "one_new_legacy_key",
])
def test_optional_arrival_group_is_atomic_and_malformed_values_never_become_zero(damage):
    world, sim = _start(people=3)
    step(world, sim, moves=[(1, 0, 1, None), (2, 0, 1, "material_need")])
    snapshot = {"livelihoods": {"residence_ledger": RL.snapshot_summary(world)}}
    frame = snapshot["livelihoods"]["residence_ledger"]["frame"]
    totals, destination = frame["totals"], _region(frame, 1)
    if damage == "counts_without_metadata":
        frame.pop("arrival_diagnostics")
    elif damage == "metadata_without_counts":
        for values in [totals, *frame["regions"]]:
            values.pop(ARRIVALS)
            values.pop(UNKNOWN)
    elif damage == "missing_half":
        totals.pop(UNKNOWN)
    elif damage == "negative":
        totals[ARRIVALS] = -1
    elif damage == "unknown_exceeds_arrivals":
        totals[UNKNOWN] = totals[ARRIVALS] + 1
    elif damage == "regional_arrival_sum":
        destination[ARRIVALS] = 1  # within regional bounds, but world total says2
    elif damage == "regional_unknown_sum":
        totals[UNKNOWN] = 0  # individually in bounds, but region still says1
    elif damage == "noninteger":
        destination[ARRIVALS] = True
    elif damage == "metadata_none":
        frame["arrival_diagnostics"] = None
    elif damage == "inconsistent_complete":
        assert frame["arrival_diagnostics"]["window_complete"] is False
        frame["arrival_diagnostics"]["complete"] = True
    elif damage == "wrong_window":
        frame["arrival_diagnostics"]["window_turns"] = 19
    else:
        _remove_arrival_group(frame)
        destination[ARRIVALS] = 0
    assert RL.record_status(snapshot) == ("malformed", None)


def test_pickle_resume_preserves_live_arrivals_and_selected_exposure_rule_exactly():
    world, sim = _start(people=2)
    step(world, sim, moves=[(1, 0, 1, None), (2, 0, 1, "material_need")])
    _environment(world)
    restored, restored_sim = pickle.loads(pickle.dumps((world, sim)))
    for moves, deaths in [([(1, 1, 2, None)], []), ([(1, 2, 0, None)], [2]), ([], [])]:
        a = step(world, sim, moves=moves, deaths=deaths)
        b = step(restored, restored_sim, moves=moves, deaths=deaths)
        assert a == b
        assert PH.environment_factors(world) == PH.environment_factors(restored)


def test_old_serialized_public_health_state_keeps_legacy_rule_but_new_enable_defaults_density():
    # Missing persisted fields must preserve historical enabled behavior;
    # enabling a genuinely new package deliberately chooses the corrected rule.
    old = PublicHealthState.model_validate({"enabled": True, "mode": "active"})
    assert old.crowding == "legacy_displacement"
    raw = PublicHealthState(crowding="density_only").__getstate__()
    raw["__dict__"].pop("crowding")
    restored = PublicHealthState.__new__(PublicHealthState)
    restored.__setstate__(copy.deepcopy(raw))
    assert restored.crowding == "legacy_displacement"
    world, _ = _start()
    PH.set_public_health_enabled(world, True)
    assert world.livelihoods.public_health.crowding == "density_only"


def test_explicit_legacy_selection_survives_resume_without_implicit_promotion():
    world, _ = _start()
    PH.set_public_health_enabled(world, True, args=SimpleNamespace(public_health_crowding="legacy_displacement"))
    assert world.livelihoods.public_health.crowding == "legacy_displacement"
    restored = pickle.loads(pickle.dumps(world))
    PH.set_public_health_enabled(restored, True)
    assert restored.livelihoods.public_health.crowding == "legacy_displacement"


def test_json_legacy_ledger_cannot_rebuild_person_arrival_history():
    world, sim = _start()
    step(world, sim, moves=[(1, 0, 1, None)])
    saved = _state(world).model_dump(mode="json")
    assert "rows" not in saved
    restored = ResidenceLedgerState.model_validate(saved)
    world.livelihoods.residence_ledger = restored
    RL.on_pool_reset(world)
    frame = step(world, sim)
    assert frame["totals"][ARRIVALS] == 0
    assert frame["arrival_diagnostics"]["complete"] is False
    assert all(r["recent_arrival_share"] is None for r in _environment(world))
