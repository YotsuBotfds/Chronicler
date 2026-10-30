"""Pure state/fake-bridge policy contracts; no World or native construction."""
from copy import deepcopy
import json
import pickle
import random
from types import SimpleNamespace
import unittest

from pydantic import ValidationError
from chronicler.health_care import (
    DEFAULT_ENABLED_FOR_NEW_WORLDS, health_care_active, health_care_on,
    get_health_care_policy, prepare_health_care, set_health_care_policy,
    validate_health_care,
)
from chronicler.health_care_state import HealthCareState, InjuryEpisode


def episode(agent_id=7):
    return InjuryEpisode(agent_id=agent_id, onset_turn=-1, remaining=2., origin_region=0)


def world(state, *, mode="hybrid"):
    return SimpleNamespace(
        health_care=state, agent_mode=mode, turn=3,
        war_state=SimpleNamespace(armies=[SimpleNamespace(roster=[(9, None), (2, None)]),
                                        SimpleNamespace(roster=[(9, None), (4, None)])]),
        cities=SimpleNamespace(cities=[SimpleNamespace(settlement_id=21),
                                      SimpleNamespace(settlement_id=11),
                                      SimpleNamespace(settlement_id=21)]),
    )


class LegacySim:
    """The old native signature deliberately accepts exactly five arguments."""
    def __init__(self):
        self.calls = []
        self.rows = []

    def prepare_health_work(self, ids, excluded, urban, impairment, care):
        self.calls.append((ids, excluded, urban, impairment, care))
        return self.rows


class PolicySim:
    def __init__(self):
        self.calls = []
        self.rows = []

    def prepare_health_work(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return self.rows


class ForbiddenBridge:
    @property
    def _sim(self):
        raise AssertionError("inactive or invalid state reached bridge")


class HealthCarePolicyTests(unittest.TestCase):
    def test_legacy_json_omits_default_even_when_explicit(self):
        expected = dict(episodes=[], injury_rate=.01, impairment=.5, care_fraction=.2,
                        recovery_work=2., care_enabled=True, last_tick_turn=-1, summary={})
        for state in (HealthCareState(), HealthCareState(care_policy="spouse")):
            with self.subTest(explicit="care_policy" in state.model_fields_set):
                self.assertEqual(state.model_dump(), expected)
                self.assertEqual(json.loads(state.model_dump_json()), expected)
                self.assertEqual(state.care_policy, "spouse")

    def test_declared_default_metadata_is_not_a_legacy_pickle_identity_claim(self):
        state = HealthCareState()
        self.assertEqual(state.__dict__["care_policy"], "spouse")
        self.assertEqual(state.__getstate__()["__dict__"]["care_policy"], "spouse")
        self.assertNotIn("care_policy", state.model_dump())

    def test_opt_in_survives_json_copy_and_owned_model_pickle(self):
        state = HealthCareState(episodes=[episode()], care_policy="retained_kin")
        expected = state.model_dump()
        self.assertEqual(expected["care_policy"], "retained_kin")
        for loaded in (HealthCareState.model_validate_json(state.model_dump_json()),
                       state.model_copy(deep=True), pickle.loads(pickle.dumps(state))):
            with self.subTest(kind=type(loaded).__name__):
                self.assertEqual(loaded.model_dump(), expected)
                sim = PolicySim()
                prepare_health_care(world(loaded), SimpleNamespace(_sim=sim))
                self.assertEqual(sim.calls[0][1], {"care_policy": "retained_kin"})

    def test_actual_missing_field_pickle_uses_legacy_five_argument_route(self):
        for enabled in (True, False):
            with self.subTest(care_enabled=enabled):
                state = HealthCareState(episodes=[episode()], care_enabled=enabled)
                state.__dict__.pop("care_policy")
                state.__pydantic_fields_set__.discard("care_policy")
                self.assertNotIn("care_policy", state.__getstate__()["__dict__"])
                loaded = pickle.loads(pickle.dumps(state))
                self.assertNotIn("care_policy", loaded.__dict__)
                self.assertEqual(get_health_care_policy(loaded), "spouse")
                sim = LegacySim()
                prepare_health_care(world(loaded), SimpleNamespace(_sim=sim))
                self.assertEqual(sim.calls, [([7], [2, 4, 9], [11, 21], .5, .2 if enabled else 0.)])
                self.assertIs(loaded._prepared, sim.rows)

    def test_constructed_default_uses_legacy_five_argument_route(self):
        state = HealthCareState.model_construct(episodes=[episode()])
        self.assertEqual(state.care_policy, "spouse")
        sim = LegacySim()
        prepare_health_care(world(state), SimpleNamespace(_sim=sim))
        self.assertEqual(sim.calls, [([7], [2, 4, 9], [11, 21], .5, .2)])

    def test_default_and_explicit_spouse_keep_old_input_order_and_return(self):
        for explicit in (False, True):
            with self.subTest(explicit=explicit):
                kwargs = {"care_policy": "spouse"} if explicit else {}
                state = HealthCareState(episodes=[episode(19), episode(7)], **kwargs)
                sim = LegacySim()
                prepare_health_care(world(state), SimpleNamespace(_sim=sim))
                self.assertEqual(sim.calls, [([19, 7], [2, 4, 9], [11, 21], .5, .2)])
                self.assertIs(state._prepared, sim.rows)

    def test_only_explicit_retained_kin_supplies_policy_keyword(self):
        state = HealthCareState(episodes=[episode(19), episode(7)], care_policy="retained_kin")
        sim = PolicySim()
        prepare_health_care(world(state), SimpleNamespace(_sim=sim))
        self.assertEqual(sim.calls, [(([19, 7], [2, 4, 9], [11, 21], .5, .2),
                                     {"care_policy": "retained_kin"})])
        self.assertIs(state._prepared, sim.rows)

    def test_explicit_retained_policy_never_falls_back_to_an_old_native_route(self):
        state = HealthCareState(episodes=[episode()], care_policy="retained_kin")
        sim = LegacySim()
        with self.assertRaisesRegex(TypeError, "care_policy"):
            prepare_health_care(world(state), SimpleNamespace(_sim=sim))
        self.assertEqual(sim.calls, [])
        self.assertIsNone(state._prepared)

    def test_care_false_keeps_zero_fraction_and_explicit_policy_route(self):
        for policy in ("spouse", "retained_kin"):
            with self.subTest(policy=policy):
                state = HealthCareState(episodes=[episode()], care_enabled=False, care_policy=policy)
                sim = PolicySim()
                prepare_health_care(world(state), SimpleNamespace(_sim=sim))
                self.assertEqual(sim.calls[0][0], ([7], [2, 4, 9], [11, 21], .5, 0.))
                self.assertEqual(sim.calls[0][1], {} if policy == "spouse" else {"care_policy": "retained_kin"})

    def test_literal_rejects_invalid_policy_at_model_admission(self):
        for value in (None, "", "kin", "parent", "Spouse", False, 1, []):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                HealthCareState(care_policy=value)

    def test_invalid_constructed_mutated_or_pickled_policy_refuses_before_bridge(self):
        for value in (None, "kin", False, 1, []):
            for route in ("construct", "mutate", "pickle"):
                with self.subTest(value=value, route=route):
                    if route == "construct":
                        state = HealthCareState.model_construct(care_policy=value)
                    else:
                        state = HealthCareState()
                        state.care_policy = value
                        if route == "pickle":
                            state = pickle.loads(pickle.dumps(state))
                    with self.assertRaisesRegex(ValueError, "care_policy"):
                        prepare_health_care(world(state), ForbiddenBridge())

    def test_duplicate_episodes_still_refuse_before_bridge_for_both_policies(self):
        for policy in ("spouse", "retained_kin"):
            with self.subTest(policy=policy):
                state = HealthCareState(episodes=[episode(), episode()], care_policy=policy)
                with self.assertRaisesRegex(ValueError, "duplicate"):
                    prepare_health_care(world(state), ForbiddenBridge())

    def test_absent_disabled_and_nonhybrid_states_do_not_reach_bridge(self):
        self.assertIs(DEFAULT_ENABLED_FOR_NEW_WORLDS, False)
        for w in (SimpleNamespace(agent_mode="hybrid"), world(None),
                  world(HealthCareState(care_policy="retained_kin"), mode="off"),
                  world(HealthCareState(care_policy="retained_kin"), mode=None)):
            with self.subTest(mode=getattr(w, "agent_mode", None)):
                before = deepcopy(w.__dict__)
                self.assertFalse(health_care_active(w))
                self.assertIsNone(prepare_health_care(w, ForbiddenBridge()))
                self.assertEqual(w.__dict__, before)
        self.assertFalse(health_care_on(SimpleNamespace()))

    def test_turn_and_missing_native_failures_remain_explicit(self):
        state = HealthCareState(last_tick_turn=3, care_policy="retained_kin")
        with self.assertRaisesRegex(ValueError, "already completed"):
            prepare_health_care(world(state), ForbiddenBridge())
        state.last_tick_turn = -1
        with self.assertRaisesRegex(RuntimeError, "fresh native"):
            prepare_health_care(world(state), SimpleNamespace(_sim=object()))

    def test_preparation_preserves_python_rng_episodes_and_summary(self):
        for policy in ("spouse", "retained_kin"):
            for enabled in (True, False):
                with self.subTest(policy=policy, care_enabled=enabled):
                    state = HealthCareState(episodes=[episode(19), episode(7)],
                                            summary={"source_turn": 1},
                                            care_policy=policy, care_enabled=enabled)
                    before = deepcopy(state.model_dump())
                    rng = random.getstate()
                    prepare_health_care(world(state), SimpleNamespace(_sim=PolicySim()))
                    self.assertEqual(random.getstate(), rng)
                    self.assertEqual(state.model_dump(), before)

    def test_setter_changes_only_policy_and_allows_explicit_reversion(self):
        state = HealthCareState(episodes=[episode()], summary={"source_turn": 1})
        w = world(state)
        episodes, patient, summary = state.episodes, state.episodes[0], state.summary
        before = state.model_dump()
        for policy in ("retained_kin", "spouse"):
            with self.subTest(policy=policy):
                set_health_care_policy(w, policy)
                self.assertEqual(get_health_care_policy(state), policy)
                self.assertIs(w.health_care, state)
                self.assertIs(state.episodes, episodes)
                self.assertIs(state.episodes[0], patient)
                self.assertIs(state.summary, summary)
                self.assertIsNone(state._prepared)
                self.assertEqual({k: v for k, v in state.model_dump().items() if k != "care_policy"}, before)
        sim = LegacySim()
        prepare_health_care(w, SimpleNamespace(_sim=sim))
        self.assertEqual(len(sim.calls), 1)
        self.assertEqual(len(sim.calls[0]), 5)

    def test_setter_requires_enabled_state_and_never_enables_it(self):
        for w in (SimpleNamespace(), SimpleNamespace(health_care=None)):
            with self.subTest(has_field=hasattr(w, "health_care")):
                before = deepcopy(w.__dict__)
                with self.assertRaisesRegex(ValueError, "already-enabled"):
                    set_health_care_policy(w, "retained_kin")
                self.assertEqual(w.__dict__, before)

    def test_setter_rejects_invalid_policy_without_any_mutation(self):
        for value in (None, "", "kin", "parent", False, 1, []):
            with self.subTest(value=value):
                state = HealthCareState(episodes=[episode()])
                before = pickle.dumps(state)
                with self.assertRaises(ValueError):
                    set_health_care_policy(world(state), value)
                self.assertEqual(pickle.dumps(state), before)

    def test_setter_validates_complete_candidate_before_mutation(self):
        for fault in ("duplicate", "episode_remaining", "impairment", "care_enabled"):
            with self.subTest(fault=fault):
                state = HealthCareState(episodes=[episode()])
                if fault == "duplicate":
                    state.episodes.append(episode())
                elif fault == "episode_remaining":
                    state.episodes[0].remaining = -1.
                elif fault == "impairment":
                    state.impairment = 2.
                else:
                    state.care_enabled = "false"
                before = pickle.dumps(state)
                with self.assertRaises(ValueError):
                    set_health_care_policy(world(state), "retained_kin")
                self.assertEqual(pickle.dumps(state), before)

    def test_setter_refuses_changes_with_prepared_work_and_preserves_noop(self):
        for policy, other in (("spouse", "retained_kin"), ("retained_kin", "spouse")):
            with self.subTest(policy=policy):
                state = HealthCareState(episodes=[episode()], care_policy=policy)
                state._prepared = [(7, 0, 9, .2)]
                prepared = state._prepared
                before = pickle.dumps(state)
                with self.assertRaisesRegex(ValueError, "prepared"):
                    set_health_care_policy(world(state), other)
                self.assertEqual(pickle.dumps(state), before)
                self.assertIs(state._prepared, prepared)
                set_health_care_policy(world(state), policy)
                self.assertEqual(pickle.dumps(state), before)
                self.assertIs(state._prepared, prepared)

    def test_setter_preserves_absent_legacy_field_on_noop_then_selects_policy(self):
        state = HealthCareState(episodes=[episode()])
        state.__dict__.pop("care_policy")
        state.__pydantic_fields_set__.discard("care_policy")
        state = pickle.loads(pickle.dumps(state))
        before = pickle.dumps(state)
        set_health_care_policy(world(state), "spouse")
        self.assertNotIn("care_policy", state.__dict__)
        self.assertEqual(pickle.dumps(state), before)
        set_health_care_policy(world(state), "retained_kin")
        self.assertEqual(get_health_care_policy(state), "retained_kin")


if __name__ == "__main__":
    unittest.main()


# CAREOBS1 SOURCE-ONLY CODEC CONTRACTS — 2026-10-29.
# Synthetic primitive fixtures below are not native observations or World proof.
import ast as _care_codec_ast
from dataclasses import fields as _care_codec_fields, replace as _care_codec_replace
import hashlib as _care_codec_hashlib
from pathlib import Path as _care_codec_Path
import struct as _care_codec_struct

import pytest as _care_codec_pytest
from chronicler import health_care_observation_codec as _care_codec


def _care_codec_b32(value):
    return _care_codec_struct.unpack("<I", _care_codec_struct.pack("<f", value))[0]


def _care_codec_b64(value):
    return _care_codec_struct.unpack("<Q", _care_codec_struct.pack("<d", value))[0]


def _care_codec_expected(*, regions=8, ordinal=0, start=20, policy=0):
    return _care_codec.FrameExpected(bytes(range(32)), start, start + ordinal,
                                     start + ordinal + 1, ordinal, policy, regions)


def _care_codec_controls(turn=20, *, policy=0):
    return _care_codec.ControlsBits(_care_codec_b64(.25), _care_codec_b64(.5),
        _care_codec_b64(.2), _care_codec_b64(2.5), True, True, True, policy, turn)


def _care_codec_joins(expected, *, initial_episodes=(), post_episodes=()):
    initial = _care_codec.SnapshotBits(
        _care_codec_controls(expected.entry_turn - 1, policy=expected.policy), initial_episodes)
    snapshot = _care_codec.SnapshotBits(
        _care_codec_controls(expected.entry_turn, policy=expected.policy), post_episodes)
    summary = _care_codec.NumericSummaryBits(expected.entry_turn, 0, len(post_episodes),
        0, 0, 0, 0, 0, 0, 0)
    regions = tuple(_care_codec.RegionalSummaryBits(r, 0, 0, 0, 0, 0, 0, 0, 0)
                    for r in range(expected.regions))
    return initial, _care_codec.PostJoinBits(snapshot, summary, regions)


def _care_codec_slot(agent_id, *, age=30, region=0, settlement=0, occupation=0,
                     trip=0, rel_count=0, marriage=0, kin=0, targets=(), alive=True):
    return (agent_id, age, region, settlement, occupation, trip, rel_count,
            marriage, kin, targets, alive)


def _care_codec_ref(ids, raw):
    if raw == 0:
        return _care_codec_struct.pack("<H", 0)
    try:
        slot = ids.index(raw)
    except ValueError:
        return _care_codec_struct.pack("<HI", 65535, raw)
    return _care_codec_struct.pack("<H", slot + 1)


def _care_codec_prefix(*, expected=None, slots=(), patients=(), excluded=(), urban=(),
                       workers=(), assignments=(), prep_regions=None,
                       economy_inputs=None, economy_outputs=None, losses_length=0,
                       scoped=(), wealth_capacity=None, coverage=None, finish_slots=None,
                       alive=(), injuries=(), stats=None, failure=0, raw_body=None):
    """Independent explicit struct layout; never invokes the production encoder."""
    expected = expected or _care_codec_expected()
    r = expected.regions
    n = len(slots)
    ids = tuple(slot[0] for slot in slots)
    finish_slots = slots if finish_slots is None else finish_slots
    wealth_capacity = n if wealth_capacity is None else wealth_capacity
    prep_regions = ((0, 0, 0, 0),) * r if prep_regions is None else prep_regions
    economy_inputs = ((0, _care_codec_b32(1.), _care_codec_b32(1.), 0),) * r if economy_inputs is None else economy_inputs
    economy_outputs = tuple((i, (0, 0, 0), 0, 0) for i in range(r)) if economy_outputs is None else economy_outputs
    stats = tuple((i, 0, 0, 0) for i in range(r)) if stats is None else stats
    k = sum((slot[7] | slot[8]).bit_count() for slot in slots)
    counts = (n, r, len(patients), len(excluded), len(urban), len(workers),
              len(assignments), losses_length, len(scoped), len(economy_outputs),
              len(alive), len(injuries), len(stats), 0, 0, k)
    body = bytearray()
    offsets = {}
    def add(name, value):
        offsets[name] = 256 + len(body)
        body.extend(value)
    def refs(name, values):
        positions = []
        for value in values:
            positions.append(256 + len(body))
            body.extend(_care_codec_ref(ids, value))
        offsets[name] = tuple(positions)
    add("constants", _care_codec_struct.pack("<II", _care_codec_b32(.5), _care_codec_b32(.2)))
    refs("patients", patients)
    refs("excluded", excluded)
    add("urban", b"".join(_care_codec_struct.pack("<H", x) for x in urban))
    for name, index, fmt in (("ids", 0, "I"), ("ages", 1, "H"), ("regions", 2, "H"),
            ("settlements", 3, "H"), ("occupations", 4, "B"), ("trips", 5, "B"),
            ("rel_count", 6, "B"), ("marriage", 7, "B"), ("kin", 8, "B")):
        add(name, b"".join(_care_codec_struct.pack("<" + fmt, slot[index]) for slot in slots))
    bitmap = bytearray((n + 7) // 8)
    for i, slot in enumerate(slots):
        bitmap[i // 8] |= int(slot[10]) << (i % 8)
    add("prep_alive", bytes(bitmap))
    refs("targets", tuple(target for slot in slots for target in slot[9]))
    positions = []
    for slot, available in workers:
        positions.append(256 + len(body))
        body.extend(_care_codec_struct.pack("<HI", slot, available))
    offsets["workers"] = tuple(positions)
    positions = []
    for patient, region, giver, care in assignments:
        positions.append(256 + len(body))
        body.extend(_care_codec_ref(ids, patient))
        body.extend(_care_codec_struct.pack("<H", region))
        body.extend(_care_codec_ref(ids, giver))
        body.extend(_care_codec_struct.pack("<I", care))
    offsets["assignments"] = tuple(positions)
    add("prep_regions", b"".join(_care_codec_struct.pack("<IQQI", *row) for row in prep_regions))
    positions = []
    for row in economy_inputs:
        positions.append(256 + len(body)); body.extend(_care_codec_struct.pack("<IIIB", *row))
    offsets["economy_inputs"] = tuple(positions)
    positions = []
    for region, outputs, forage, worked in economy_outputs:
        positions.append(256 + len(body)); body.extend(_care_codec_struct.pack("<HIIIIB", region, *outputs, forage, worked))
    offsets["economy_outputs"] = tuple(positions)
    present = sum(row[0] < wealth_capacity for row in scoped)
    coverage = (wealth_capacity, wealth_capacity, present, wealth_capacity - present) if coverage is None else coverage
    add("coverage", _care_codec_struct.pack("<HHHH", *coverage))
    positions = []
    for slot, consumed, loss, current, region, occupation, flags, reason, mask, numbers in scoped:
        positions.append(256 + len(body)); body.extend(_care_codec_struct.pack("<H", slot))
        body.extend(_care_codec_ref(ids, consumed))
        body.extend(_care_codec_struct.pack("<IIHBBBB6I", loss, current, region,
                                           occupation, flags, reason, mask, *numbers))
    offsets["scoped"] = tuple(positions)
    add("wealth_regions", bytes(12 * r))
    add("finish_metadata", _care_codec_struct.pack("<IIH", expected.entry_turn, _care_codec_b32(.25), len(finish_slots)))
    add("finish_ids", b"".join(_care_codec_struct.pack("<I", slot[0]) for slot in finish_slots))
    add("finish_regions", b"".join(_care_codec_struct.pack("<H", slot[2]) for slot in finish_slots))
    bitmap = bytearray((len(finish_slots) + 7) // 8)
    for i, slot in enumerate(finish_slots):
        bitmap[i // 8] |= int(slot[10]) << (i % 8)
    add("finish_alive", bytes(bitmap))
    positions = []
    for agent_id, region in alive:
        positions.append(256 + len(body)); body.extend(_care_codec_ref(ids, agent_id)); body.extend(_care_codec_struct.pack("<H", region))
    offsets["alive"] = tuple(positions)
    positions = []
    for agent_id, work_region, region in injuries:
        positions.append(256 + len(body)); body.extend(_care_codec_ref(ids, agent_id)); body.extend(_care_codec_struct.pack("<HH", work_region, region))
    offsets["injuries"] = tuple(positions)
    add("finish_stats", b"".join(_care_codec_struct.pack("<HQQI", *row) for row in stats))
    if raw_body is not None:
        body = bytearray(raw_body)
    header = bytearray(256)
    _care_codec_struct.pack_into("<8sHHIII BBH", header, 0, b"CAREOBS1", 1, 256,
        4 if failure else 0, expected.entry_turn, 256 + len(body), 15, expected.policy, failure)
    _care_codec_struct.pack_into("<16I", header, 28, *counts)
    header[92:124] = expected.manifest_sha256
    header[196:200] = b"\x01\x01\x01\x01"
    _care_codec_struct.pack_into("<I", header, 200, expected.ordinal)
    return bytes(header + body), offsets


def _care_codec_change(data, offset, fmt, *values, final=False):
    changed = bytearray(data)
    _care_codec_struct.pack_into("<" + fmt, changed, offset, *values)
    _care_codec_struct.pack_into("<I", changed, 20, len(changed))
    if final:
        changed[156:188] = _care_codec_hashlib.sha256(changed[256:]).digest()
    return bytes(changed)


def _care_codec_finalize(prefix=None, *, expected=None, initial=None, post=None, previous=None):
    expected = expected or _care_codec_expected()
    if prefix is None:
        prefix, _ = _care_codec_prefix(expected=expected)
    default_initial, default_post = _care_codec_joins(expected)
    if initial is None and expected.ordinal == 0:
        initial = default_initial
    if post is None:
        post = default_post
    result = _care_codec.finalize_care_frame(prefix, expected=expected, initial=initial,
                                           post=post, previous=previous)
    assert type(result) is bytes
    return result


def _care_codec_fault(data, expected, code=None):
    view = _care_codec.decode_care_frame(data, expected=expected)
    assert isinstance(view, _care_codec.CareFaultView)
    if code is not None:
        assert _care_codec_struct.unpack_from("<H", data, 26)[0] == code
    assert _care_codec_struct.unpack_from("<I", data, 20)[0] == len(data)
    assert data[156:188] == _care_codec_hashlib.sha256(data[256:]).digest()
    assert _care_codec_struct.unpack_from("<I", data, 12)[0] == 4
    return view


def test_care_codec_empty_first_frame_matches_closed_1550_byte_layout():
    expected = _care_codec_expected()
    prefix, offsets = _care_codec_prefix(expected=expected)
    assert len(prefix) == 1002
    final = _care_codec_finalize(prefix, expected=expected)
    assert len(final) == 1550
    view = _care_codec.decode_care_frame(final, expected=expected)
    assert type(view) is _care_codec.CareFrameView and view.structural_complete
    assert view.data is final
    assert view.header.counts == (0, 8, 0, 0, 0, 0, 0, 0, 0, 8, 0, 0, 8, 0, 0, 0)
    assert (view.header.flags, view.header.stage, view.header.calls) == (3, 63, (1, 1, 1, 1))
    assert offsets["finish_stats"] + 22 * 8 == len(prefix)
    assert final[len(prefix):len(prefix) + 44] == _care_codec_struct.pack("<4Q4Bq",
        _care_codec_b64(.25), _care_codec_b64(.5), _care_codec_b64(.2),
        _care_codec_b64(2.5), 1, 1, 1, 0, 19)
    assert final[156:188] == _care_codec_hashlib.sha256(final[256:]).digest()
    assert view.frame_sha256 == _care_codec_hashlib.sha256(final).digest()
    assert not hasattr(view, "mechanics_verified")


def test_care_codec_native_prefix_is_only_admitted_by_immutable_finalization():
    expected = _care_codec_expected()
    prefix, _ = _care_codec_prefix(expected=expected)
    initial, post = _care_codec_joins(expected)
    before = (prefix, initial, post, random.getstate())
    with _care_codec_pytest.raises(_care_codec.CareFrameError):
        _care_codec.decode_care_frame(prefix, expected=expected)
    first = _care_codec.finalize_care_frame(prefix, expected=expected, initial=initial, post=post)
    second = _care_codec.finalize_care_frame(prefix, expected=expected, initial=initial, post=post)
    assert type(first) is bytes and first == second
    assert (prefix, initial, post, random.getstate()) == before
    view = _care_codec.decode_care_frame(first, expected=expected)
    assert view.data == first
    with _care_codec_pytest.raises(AttributeError):
        view.data = b"forged"
    with _care_codec_pytest.raises(AttributeError):
        post.summary.episodes = 9000


def test_care_codec_native_float_bits_keep_signed_zero_infinities_and_nan_payloads():
    expected = _care_codec_expected(regions=1)
    numbers = (0x7fc00011, 0x80000000, 0x7fc00022, 0x7f800000, 0xff800000, 0)
    scoped = ((0, 7, 0x7fc01234, 7, 0, 0, 7, 0, 63, numbers),)
    prefix, _ = _care_codec_prefix(expected=expected, slots=(_care_codec_slot(7),),
        workers=((0, 0x80000000),), losses_length=1, scoped=scoped,
        prep_regions=((0x80000000, 0x7ff8000000000011, 0x8000000000000000, 0),),
        economy_inputs=((0, 0x80000000, 0x80000000, 0),),
        economy_outputs=((0, (0x80000000, 0x7fc04321, 0x7f800000), 0xff800000, 1),),
        stats=((0, 0x7ff8000000000022, 0x7ff0000000000000, 0),))
    view = _care_codec.decode_care_frame(_care_codec_finalize(prefix, expected=expected), expected=expected)
    assert view.native.workers == ((0, 0x80000000),)
    assert view.native.preparation_regions == ((0x80000000, 0x7ff8000000000011, 0x8000000000000000, 0),)
    assert view.native.economy_outputs == ((0, (0x80000000, 0x7fc04321, 0x7f800000), 0xff800000, True),)
    assert view.native.scoped[0].loss_b32 == 0x7fc01234
    assert view.native.scoped[0].numbers == numbers
    assert view.native.regional_results[0][1:3] == (0x7ff8000000000022, 0x7ff0000000000000)


def test_care_codec_idrefs_are_canonical_raw_ids_independent_of_dead_duplicates():
    expected = _care_codec_expected(regions=1)
    slots = (_care_codec_slot(0), _care_codec_slot(7, alive=False),
             _care_codec_slot(7), _care_codec_slot(99))
    prefix, offsets = _care_codec_prefix(expected=expected, slots=slots, patients=(0, 7, 404))
    episodes = tuple(_care_codec.EpisodeBits(x, -1, _care_codec_b64(2.), 0) for x in (0, 7, 404))
    initial, post = _care_codec_joins(expected, initial_episodes=episodes)
    final = _care_codec_finalize(prefix, expected=expected, initial=initial, post=post)
    view = _care_codec.decode_care_frame(final, expected=expected)
    assert view.native.inputs == (0, 7, 404)
    assert prefix[offsets["patients"][1]:offsets["patients"][1] + 2] == b"\x02\x00"
    bad = ((_care_codec_change(prefix, offsets["patients"][0], "H", 1)),
           (_care_codec_change(prefix, offsets["patients"][1], "H", 3)),
           (_care_codec_change(prefix, offsets["patients"][1], "H", 5)),
           (_care_codec_change(prefix, offsets["patients"][2] + 2, "I", 0)),
           (_care_codec_change(prefix, offsets["patients"][2] + 2, "I", 7)))
    for changed in bad:
        _care_codec_fault(_care_codec_finalize(changed, expected=expected, initial=initial, post=post), expected)


def test_care_codec_ordered_inputs_workers_and_assignments_are_never_deduplicated():
    expected = _care_codec_expected(regions=1)
    ids = (20, 10, 20, 404)
    episodes = tuple(_care_codec.EpisodeBits(x, -1, _care_codec_b64(2.), 0) for x in ids)
    initial, post = _care_codec_joins(expected, initial_episodes=episodes)
    assignments = ((20, 0, 10, _care_codec_b32(.2)), (10, 0, 0, 0))
    prefix, offsets = _care_codec_prefix(expected=expected,
        slots=(_care_codec_slot(10), _care_codec_slot(20)), patients=ids,
        excluded=(404, 10, 404), urban=(0, 12, 12),
        workers=((1, _care_codec_b32(.75)), (0, 0x80000000)), assignments=assignments)
    view = _care_codec.decode_care_frame(
        _care_codec_finalize(prefix, expected=expected, initial=initial, post=post), expected=expected)
    assert view.native.inputs == ids and view.initial.episodes == episodes
    assert view.native.excluded == (404, 10, 404) and view.native.urban == (0, 12, 12)
    assert view.native.workers == ((1, _care_codec_b32(.75)), (0, 0x80000000))
    assert view.native.assignments == assignments
    changed = _care_codec_change(prefix, offsets["workers"][0], "H", 2)
    _care_codec_fault(_care_codec_finalize(changed, expected=expected, initial=initial, post=post), expected)


def test_care_codec_relationship_masks_retain_zero_self_absent_and_duplicate_positions():
    expected = _care_codec_expected(regions=1)
    slots = (_care_codec_slot(1, rel_count=8, marriage=1, kin=14, targets=(0, 1, 404, 404)),
             _care_codec_slot(2, alive=False))
    prefix, offsets = _care_codec_prefix(expected=expected, slots=slots)
    view = _care_codec.decode_care_frame(_care_codec_finalize(prefix, expected=expected), expected=expected)
    assert view.native.rel_counts == (8, 0)
    assert view.native.marriage_masks == (1, 0) and view.native.kin_masks == (14, 0)
    assert view.native.targets == (0, 1, 404, 404)
    mutations = ((offsets["rel_count"], "B", 9),
                 (offsets["rel_count"], "B", 3),
                 (offsets["marriage"], "B", 3), (28 + 15 * 4, "I", 5))
    for offset, fmt, value in mutations:
        changed = _care_codec_change(prefix, offset, fmt, value)
        _care_codec_fault(_care_codec_finalize(changed, expected=expected), expected)


def test_care_codec_public_join_records_exclude_display_and_inferred_genealogy_fields():
    names = {field.name for record in (_care_codec.ControlsBits, _care_codec.EpisodeBits,
        _care_codec.SnapshotBits, _care_codec.NumericSummaryBits, _care_codec.RegionalSummaryBits,
        _care_codec.PostJoinBits, _care_codec.FrameExpected) for field in _care_codec_fields(record)}
    assert not names.intersection({"name", "civ", "civ_name", "units", "parents", "household", "sentiment"})
    assert {field.name for field in _care_codec_fields(_care_codec.EpisodeBits)} == {
        "agent_id", "onset_turn", "remaining_b64", "origin_region"}
    expected = _care_codec_expected(regions=1)
    prefix, _ = _care_codec_prefix(expected=expected, slots=(_care_codec_slot(7, rel_count=3),))
    view = _care_codec.decode_care_frame(_care_codec_finalize(prefix, expected=expected), expected=expected)
    assert view.native.rel_counts == (3,) and view.native.targets == ()
    assert view.native.marriage_masks == view.native.kin_masks == (0,)


def test_care_codec_sparse_consumed_loss_elides_only_exact_id_zero_positive_zero():
    expected = _care_codec_expected(regions=1)
    slots = tuple(_care_codec_slot(x) for x in (1, 2, 3, 4))
    scoped = ((0, 1, 0, 1, 0, 0, 7, 1, 63, (0,) * 6),
              (1, 0, 0x80000000, 2, 0, 0, 7, 2, 63, (0,) * 6),
              (2, 3, 0x7fc01234, 3, 0, 0, 7, 0, 63, (0,) * 6))
    prefix, offsets = _care_codec_prefix(expected=expected, slots=slots, losses_length=4, scoped=scoped)
    view = _care_codec.decode_care_frame(_care_codec_finalize(prefix, expected=expected), expected=expected)
    assert view.header.counts[7:9] == (4, 3)
    assert tuple((r.slot, r.consumed_id, r.loss_b32) for r in view.native.scoped) == (
        (0, 1, 0), (1, 0, 0x80000000), (2, 3, 0x7fc01234))
    reconstructed = {r.slot: (r.consumed_id, r.loss_b32) for r in view.native.scoped}
    assert tuple(reconstructed.get(i, (0, 0)) for i in range(4))[-1] == (0, 0)
    for index in (0, 1):
        changed = _care_codec_change(prefix, offsets["scoped"][index], "H", 4)
        _care_codec_fault(_care_codec_finalize(changed, expected=expected), expected)
    changed = _care_codec_change(prefix, offsets["scoped"][1], "H", 0)
    _care_codec_fault(_care_codec_finalize(changed, expected=expected), expected)
    changed = _care_codec_change(prefix, offsets["scoped"][1] + 4, "I", 0)
    _care_codec_fault(_care_codec_finalize(changed, expected=expected), expected)


def test_care_codec_scope_reason_priority_flags_and_unavailable_numeric_bits_are_checked():
    expected = _care_codec_expected(regions=1)
    slots = tuple(_care_codec_slot(x) for x in range(1, 7))
    zero = (0,) * 6
    retained = (0x7fc01234, 0, 0, 0, 0, 0x7fc01234)
    scoped = ((0, 1, _care_codec_b32(.5), 1, 0, 0, 7, 0, 63, zero),
        (1, 2, 0x80000000, 2, 0, 0, 7, 1, 63, zero),
        (2, 999, _care_codec_b32(.5), 3, 0, 0, 7, 2, 63, zero),
        (3, 999, _care_codec_b32(.5), 4, 0, 1, 7, 3, 63, zero),
        (4, 999, 0, 5, 0, 1, 5, 4, 33, retained),
        (5, 999, 0, 6, 99, 1, 3, 5, 33, retained),
        (6, 999, 0x7fc04321, 0, 0, 0, 0, 6, 0, zero))
    prefix, offsets = _care_codec_prefix(expected=expected, slots=slots, losses_length=7, scoped=scoped)
    view = _care_codec.decode_care_frame(_care_codec_finalize(prefix, expected=expected), expected=expected)
    assert tuple(r.reason for r in view.native.scoped) == (0, 1, 2, 3, 4, 5, 6)
    assert tuple(r.numeric_mask for r in view.native.scoped) == (63, 63, 63, 63, 33, 33, 0)
    assert view.native.scoped[4].numbers == retained
    # Literal consumed IDs add four bytes before the current facts in rows2..6.
    mutations = ((offsets["scoped"][0] + 16, "B", 1),
                 (offsets["scoped"][4] + 21, "B", 63),
                 (offsets["scoped"][4] + 26, "I", 1),
                 (offsets["scoped"][6] + 12, "I", 1))
    for offset, fmt, value in mutations:
        _care_codec_fault(_care_codec_finalize(_care_codec_change(prefix, offset, fmt, value), expected=expected), expected)


def test_care_codec_coverage_counts_existing_scope_separately_from_no_slot_rows():
    expected = _care_codec_expected(regions=1)
    scoped = ((0, 1, _care_codec_b32(.5), 1, 0, 0, 7, 0, 63, (0,) * 6),
              (2, 999, _care_codec_b32(.5), 0, 0, 0, 0, 6, 0, (0,) * 6))
    prefix, offsets = _care_codec_prefix(expected=expected,
        slots=(_care_codec_slot(1), _care_codec_slot(2)), losses_length=3, scoped=scoped)
    view = _care_codec.decode_care_frame(_care_codec_finalize(prefix, expected=expected), expected=expected)
    assert view.header.counts[8] == 2 and view.native.wealth_coverage == (2, 2, 1, 1)
    assert view.native.scoped[0].numbers == (0,) * 6
    for values in ((2, 1, 1, 1), (2, 2, 2, 0), (2, 2, 0, 2)):
        changed = _care_codec_change(prefix, offsets["coverage"], "4H", *values)
        _care_codec_fault(_care_codec_finalize(changed, expected=expected), expected)


def test_care_codec_economy_rows_keep_raw_order_and_bitwise_false_branch_equality():
    expected = _care_codec_expected(regions=2)
    inputs = ((0, 0x80000000, 0x80000000, 0), (3, _care_codec_b32(1.), _care_codec_b32(.5), 1))
    outputs = ((1, (1, 2, 3), 4, 1), (0, (5, 6, 7), 8, 0))
    prefix, offsets = _care_codec_prefix(expected=expected, economy_inputs=inputs, economy_outputs=outputs)
    view = _care_codec.decode_care_frame(_care_codec_finalize(prefix, expected=expected), expected=expected)
    assert view.native.economy_inputs == ((0, 0x80000000, 0x80000000, False), (3, _care_codec_b32(1.), _care_codec_b32(.5), True))
    assert tuple(row[0] for row in view.native.economy_outputs) == (1, 0)
    assert tuple(row[1] for row in view.native.economy_outputs) == ((1, 2, 3), (5, 6, 7))
    changed = _care_codec_change(prefix, offsets["economy_inputs"][0] + 8, "I", 0)
    _care_codec_fault(_care_codec_finalize(changed, expected=expected), expected, 5)
    changed = _care_codec_change(prefix, offsets["economy_outputs"][0] + 18, "B", 2)
    _care_codec_fault(_care_codec_finalize(changed, expected=expected), expected)


def test_care_codec_full_finish_columns_allow_capacity_changes_and_last_live_lookup():
    expected = _care_codec_expected(regions=2)
    slots = (_care_codec_slot(0), _care_codec_slot(7))
    finish = (_care_codec_slot(0, alive=False), _care_codec_slot(7, alive=False),
        _care_codec_slot(7, region=1), _care_codec_slot(99, region=65535), _care_codec_slot(0))
    episodes = tuple(_care_codec.EpisodeBits(x, -1, _care_codec_b64(2.), 0) for x in (7, 0))
    initial, post = _care_codec_joins(expected, initial_episodes=episodes)
    post = _care_codec_replace(post, summary=_care_codec_replace(post.summary, new_injuries=1))
    prefix, _ = _care_codec_prefix(expected=expected, slots=slots, patients=(7, 0),
        finish_slots=finish, alive=((7, 1), (0, 0)), injuries=((7, 0, 1),))
    view = _care_codec.decode_care_frame(
        _care_codec_finalize(prefix, expected=expected, initial=initial, post=post), expected=expected)
    assert view.native.ids == (0, 7)
    assert view.native.finish_ids == (0, 7, 7, 99, 0)
    assert view.native.finish_regions == (0, 0, 1, 65535, 0)
    assert view.native.finish_alive == (False, False, True, True, True)
    live = {agent_id: slot for slot, agent_id in enumerate(view.native.finish_ids) if view.native.finish_alive[slot]}
    assert live[7] == 2 and live[0] == 4
    assert view.native.alive_results == ((7, 1), (0, 0))
    assert view.native.injuries == ((7, 0, 1),)
    assert view.native.regional_results == ((0, 0, 0, 0), (1, 0, 0, 0))


def test_care_codec_python_episode_and_numeric_metric_mapping_is_exact():
    expected = _care_codec_expected(regions=1)
    episodes = (_care_codec.EpisodeBits(404, -(1 << 63), 0x8000000000000000, 65535),
                _care_codec.EpisodeBits(7, -1, 0x7ff8000000000022, 0))
    initial, post = _care_codec_joins(expected, initial_episodes=episodes, post_episodes=episodes[::-1])
    summary = _care_codec.NumericSummaryBits(20, 11, 2, 0, 13, 14,
        0x8000000000000000, 0x7ff8000000000011, 0x7ff0000000000000, 0x7ff8000000000022)
    regional = _care_codec.RegionalSummaryBits(0, 21, 22, 23, 24, 31, 32, 33, 34)
    post = _care_codec_replace(post, summary=summary, regions=(regional,))
    prefix, _ = _care_codec_prefix(expected=expected, slots=(_care_codec_slot(7),), patients=(404, 7))
    final = _care_codec_finalize(prefix, expected=expected, initial=initial, post=post)
    view = _care_codec.decode_care_frame(final, expected=expected)
    assert view.initial == initial and view.post == post
    assert view.post.snapshot.episodes == episodes[::-1]
    assert view.post.summary == summary and view.post.regions == (regional,)
    assert final[-110:-50] == _care_codec_struct.pack("<qI4I4Q", 20, 11, 2, 0, 13, 14,
        0x8000000000000000, 0x7ff8000000000011, 0x7ff0000000000000, 0x7ff8000000000022)
    assert final[-50:] == _care_codec_struct.pack("<H4I4Q", 0, 21, 22, 23, 24, 31, 32, 33, 34)


def _care_codec_assert_refusal(prefix, expected, initial, post, *, previous=None):
    try:
        result = _care_codec.finalize_care_frame(prefix, expected=expected, initial=initial,
                                               post=post, previous=previous)
    except _care_codec.CareFrameError as error:
        assert type(error.code) is int and 1 <= error.code <= 11
        assert len(str(error)) < 128
        return
    assert type(result) is bytes and 256 <= len(result) <= 131072
    assert _care_codec_struct.unpack_from("<I", result, 12)[0] == 4
    assert 1 <= _care_codec_struct.unpack_from("<H", result, 26)[0] <= 11
    assert result[156:188] == _care_codec_hashlib.sha256(result[256:]).digest()


def test_care_codec_predecessors_are_redecoded_from_bound_bytes_across_multiple_turns():
    episode_bits = (_care_codec.EpisodeBits(7, -1, _care_codec_b64(2.), 0),)
    previous = None
    views = []
    for ordinal in range(3):
        expected = _care_codec_expected(regions=1, ordinal=ordinal)
        prefix, _ = _care_codec_prefix(expected=expected, slots=(_care_codec_slot(7),), patients=(7,))
        initial, post = _care_codec_joins(expected, initial_episodes=episode_bits, post_episodes=episode_bits)
        result = _care_codec.finalize_care_frame(prefix, expected=expected,
            initial=initial if ordinal == 0 else None, post=post, previous=previous)
        view = _care_codec.decode_care_frame(result, expected=expected, previous=previous)
        assert type(view) is _care_codec.CareFrameView
        assert view.header.predecessor_sha256 == (bytes(32) if previous is None else previous.frame_sha256)
        assert view.header.flags == (3 if ordinal == 0 else 1)
        assert view.header.stage == (63 if ordinal == 0 else 31)
        assert view.header.counts[14] == (1 if ordinal == 0 else 0)
        views.append(view)
        previous = view
    expected = _care_codec_expected(regions=1, ordinal=3)
    prefix, _ = _care_codec_prefix(expected=expected, slots=(_care_codec_slot(7),), patients=(7,))
    initial, post = _care_codec_joins(expected, initial_episodes=episode_bits, post_episodes=episode_bits)
    good = _care_codec.finalize_care_frame(prefix, expected=expected, initial=None, post=post, previous=previous)
    forged_episodes = (_care_codec_replace(episode_bits[0], agent_id=404),)
    forged_post = _care_codec_replace(previous.post,
        snapshot=_care_codec_replace(previous.post.snapshot, episodes=forged_episodes))
    for forged in (_care_codec_replace(previous, post=forged_post),
                   _care_codec_replace(previous, frame_sha256=b"x" * 32),
                   _care_codec_replace(previous, native=_care_codec_replace(previous.native, inputs=(404,))),
                   _care_codec_replace(previous, header=_care_codec_replace(previous.header, source_turn=9000)),
                   _care_codec_replace(previous, previous=_care_codec_replace(views[1], post=forged_post))):
        assert _care_codec.finalize_care_frame(prefix, expected=expected, initial=None,
                                              post=post, previous=forged) == good
    bad_prefix, _ = _care_codec_prefix(expected=expected, slots=(_care_codec_slot(7),), patients=(404,))
    _care_codec_assert_refusal(bad_prefix, expected, None, post,
        previous=_care_codec_replace(previous, post=forged_post))
    _care_codec_assert_refusal(prefix, expected, None, post, previous=None)
    _care_codec_assert_refusal(prefix, expected, initial, post, previous=previous)
    _care_codec_assert_refusal(prefix, expected, None, post,
                              previous=_care_codec_replace(previous, previous=None))
    first_expected = _care_codec_expected(regions=1)
    first_prefix, _ = _care_codec_prefix(expected=first_expected)
    _, first_post = _care_codec_joins(first_expected)
    _care_codec_fault(_care_codec.finalize_care_frame(first_prefix, expected=first_expected,
        initial=None, post=first_post), first_expected, 11)
    failed = _care_codec_fault(_care_codec.finalize_care_frame(None, expected=first_expected,
        initial=None, post=None), first_expected, 7)
    _care_codec_assert_refusal(prefix, expected, None, post, previous=failed)
    changed_bytes = bytearray(previous.data)
    changed_bytes[256] ^= 1  # stale body hash must not borrow cached validation
    invalid_control = _care_codec_change(previous.data, 256, "I", _care_codec_b32(.75), final=True)
    for changed in (bytes(changed_bytes), invalid_control):
        _care_codec_assert_refusal(prefix, expected, None, post,
                                  previous=_care_codec_replace(previous, data=changed))
    # All32 source ordinals are accepted from revalidated bytes/ancestry; the
    # same small primitive fixture carries its actual preceding post input.
    bounded_previous = None
    for ordinal in range(32):
        bounded_expected = _care_codec_expected(regions=1, ordinal=ordinal)
        bounded_prefix, _ = _care_codec_prefix(expected=bounded_expected,
            slots=(_care_codec_slot(7),), patients=(7,))
        bounded_initial, bounded_post = _care_codec_joins(bounded_expected,
            initial_episodes=episode_bits, post_episodes=episode_bits)
        bounded_bytes = _care_codec.finalize_care_frame(bounded_prefix, expected=bounded_expected,
            initial=bounded_initial if ordinal == 0 else None,
            post=bounded_post, previous=bounded_previous)
        bounded_previous = _care_codec.decode_care_frame(bounded_bytes,
            expected=bounded_expected, previous=bounded_previous)
        assert type(bounded_previous) is _care_codec.CareFrameView
        assert bounded_previous.header.ordinal == ordinal
    assert bounded_previous.header.ordinal == 31
    outside = _care_codec_expected(regions=1, ordinal=32)
    with _care_codec_pytest.raises(_care_codec.CareFrameError) as refused:
        _care_codec.finalize_care_frame(bounded_prefix, expected=outside,
            initial=None, post=bounded_post, previous=bounded_previous)
    assert refused.value.code == 8


def test_care_codec_manifest_policy_regions_and_all_turn_bindings_refuse_mismatches():
    expected = _care_codec_expected(regions=1)
    prefix, offsets = _care_codec_prefix(expected=expected)
    initial, post = _care_codec_joins(expected)
    for wrong in (_care_codec_replace(expected, manifest_sha256=b"z" * 32),
                  _care_codec_replace(expected, policy=1),
                  _care_codec_replace(expected, regions=2),
                  _care_codec_replace(expected, ordinal=32),
                  _care_codec_replace(expected, entry_turn=21, exit_turn=22),
                  _care_codec_replace(expected, exit_turn=20),
                  _care_codec_replace(expected, entry_turn=(1 << 32) - 1, exit_turn=1 << 32)):
        _care_codec_assert_refusal(prefix, wrong, initial, post)
    for changed in (_care_codec_change(prefix, 16, "I", 21),
                    _care_codec_change(prefix, offsets["finish_metadata"], "I", 21),
                    _care_codec_change(prefix, 200, "I", 1)):
        _care_codec_assert_refusal(changed, expected, initial, post)
    for changed_post in (_care_codec_replace(post, summary=_care_codec_replace(post.summary, source_turn=21)),
            _care_codec_replace(post, snapshot=_care_codec_replace(post.snapshot,
                controls=_care_codec_replace(post.snapshot.controls, last_tick_turn=19))),
            _care_codec_replace(post, snapshot=_care_codec_replace(post.snapshot,
                controls=_care_codec_replace(post.snapshot.controls, care_fraction_b64=_care_codec_b64(.3))))):
        _care_codec_assert_refusal(prefix, expected, initial, changed_post)
    for controls in (_care_codec_replace(initial.controls, care_enabled=False),
                     _care_codec_replace(initial.controls, injury_rate_b64=0x7ff8000000000011),
                     _care_codec_replace(initial.controls, impairment_b64=0x7ff0000000000000),
                     _care_codec_replace(initial.controls, care_enabled=False, care_fraction_b64=0x7ff8000000000022),
                     _care_codec_replace(initial.controls, recovery_work_b64=0x7ff8000000000033),
                     _care_codec_replace(initial.controls, injury_rate_b64=_care_codec_b64(.5))):
        changed_initial = _care_codec_replace(initial, controls=controls)
        changed_post = _care_codec_replace(post,
            snapshot=_care_codec_replace(post.snapshot,
                controls=_care_codec_replace(controls, last_tick_turn=20)))
        _care_codec_assert_refusal(prefix, expected, changed_initial, changed_post)


def test_care_codec_final_header_hash_padding_counts_and_truncation_checks_are_strict():
    expected = _care_codec_expected(regions=1)
    prefix, offsets = _care_codec_prefix(expected=expected, slots=(_care_codec_slot(7),))
    final = _care_codec_finalize(prefix, expected=expected)
    mutations = ((0, "B", 0), (8, "H", 2), (10, "H", 255), (12, "I", 64),
        (12, "I", 5), (24, "B", 15), (26, "H", 1), (196, "B", 2),
        (204, "B", 1), (28, "I", 4097), (28 + 15 * 4, "I", 32769),
        (20, "I", len(final) + 1), (offsets["prep_alive"], "B", 129),
        (offsets["finish_alive"], "B", 129))
    for offset, fmt, value in mutations:
        changed = bytearray(final)
        _care_codec_struct.pack_into("<" + fmt, changed, offset, value)
        if offset >= 256:
            changed[156:188] = _care_codec_hashlib.sha256(changed[256:]).digest()
        with _care_codec_pytest.raises(_care_codec.CareFrameError):
            _care_codec.decode_care_frame(bytes(changed), expected=expected)
    for changed in (final[:-1], final[:255], final[:156] + bytes(32) + final[188:],
                    _care_codec_change(final, len(final) - 1, "B", final[-1] ^ 1)):
        with _care_codec_pytest.raises(_care_codec.CareFrameError):
            _care_codec.decode_care_frame(changed, expected=expected)
    trailing = bytearray(final + b"\0")
    _care_codec_struct.pack_into("<I", trailing, 20, len(trailing))
    trailing[156:188] = _care_codec_hashlib.sha256(trailing[256:]).digest()
    with _care_codec_pytest.raises(_care_codec.CareFrameError):
        _care_codec.decode_care_frame(bytes(trailing), expected=expected)


def test_care_codec_exact_joined_byte_cap_accepts_and_next_encoded_unit_refuses():
    expected = _care_codec_expected()
    slots = tuple(_care_codec_slot(i + 1) for i in range(1024))
    excluded = tuple(2_000_000 + i for i in range(1576))
    episodes = tuple(_care_codec.EpisodeBits(1_000_000 + i, -1, _care_codec_b64(2.), 0)
                     for i in range(4096))
    initial, post = _care_codec_joins(expected, post_episodes=episodes)
    prefix, _ = _care_codec_prefix(expected=expected, slots=slots, excluded=excluded, urban=(0,))
    final = _care_codec_finalize(prefix, expected=expected, initial=initial, post=post)
    assert len(final) == 131072
    assert _care_codec.decode_care_frame(final, expected=expected).structural_complete
    too_big, _ = _care_codec_prefix(expected=expected, slots=slots, excluded=excluded, urban=(0, 0))
    refused = _care_codec_finalize(too_big, expected=expected, initial=initial, post=post)
    _care_codec_fault(refused, expected, 3)
    assert len(refused) == len(too_big) < 131072
    with _care_codec_pytest.raises(_care_codec.CareFrameError):
        _care_codec.decode_care_frame(final + b"\0", expected=expected)


def test_care_codec_primitive_domains_and_tuple_bounds_refuse_without_iteration_or_narrowing():
    expected = _care_codec_expected(regions=1)
    prefix, _ = _care_codec_prefix(expected=expected)
    initial, post = _care_codec_joins(expected)
    for wrong in (_care_codec_replace(initial.controls, enabled=1),
                  _care_codec_replace(initial.controls, policy=True),
                  _care_codec_replace(initial.controls, injury_rate_b64=True),
                  _care_codec_replace(initial.controls, care_fraction_b64=1 << 64),
                  _care_codec_replace(initial.controls, last_tick_turn=-(1 << 63) - 1)):
        _care_codec_assert_refusal(prefix, expected, _care_codec_replace(initial, controls=wrong), post)
    base = _care_codec.EpisodeBits(7, -1, _care_codec_b64(2.), 0)
    for wrong in (_care_codec_replace(base, agent_id=-1), _care_codec_replace(base, agent_id=1 << 32),
                  _care_codec_replace(base, agent_id=True), _care_codec_replace(base, onset_turn=1 << 63),
                  _care_codec_replace(base, remaining_b64=1 << 64), _care_codec_replace(base, origin_region=1 << 16)):
        bad_initial = _care_codec_replace(initial, episodes=(wrong,))
        _care_codec_assert_refusal(prefix, expected, bad_initial, post)
    visited = []
    def forbidden_generator():
        visited.append("iterated")
        yield base
    generator = forbidden_generator()
    for episodes in ([base], generator, (base,) * 4097):
        _care_codec_assert_refusal(prefix, expected, _care_codec_replace(initial, episodes=episodes), post)
    assert visited == []
    generator.close()
    _care_codec_assert_refusal(prefix, expected, initial, _care_codec_replace(post, regions=list(post.regions)))
    for index in range(16):
        if index == 15:
            value = 32769
        else:
            value = 4097
        _care_codec_assert_refusal(_care_codec_change(prefix, 28 + 4 * index, "I", value), expected, initial, post)


def test_care_codec_native_aborted_body_stays_opaque_and_preserves_first_fault_and_turns(monkeypatch):
    expected = _care_codec_expected(regions=1)
    prefix, _ = _care_codec_prefix(expected=expected, failure=2,
                                    raw_body=b"\xff\x00opaque\x80not regular sections")
    prefix = _care_codec_change(prefix, 16, "I", 21)
    prefix = _care_codec_change(prefix, 28, "I", (1 << 32) - 1)
    def no_regular_decode(*args, **kwargs):
        raise AssertionError("an opaque fault body reached regular native decoding")
    monkeypatch.setattr(_care_codec, "_native", no_regular_decode)
    result = _care_codec.finalize_care_frame(prefix, expected=expected, initial=None, post=None)
    view = _care_codec_fault(result, expected, 2)
    assert not view.structural_complete
    assert bytes(view.opaque_body) == prefix[256:]
    assert view.header.source_turn == 21 and view.header.entry_turn == 20 and view.header.exit_turn == 21
    assert view.header.counts[0] == (1 << 32) - 1
    assert view.frame_sha256 == _care_codec_hashlib.sha256(result).digest()
    assert not hasattr(view, "native")
    with _care_codec_pytest.raises(TypeError):
        view.opaque_body[0] = 0


def test_care_codec_memory_error_is_missing_evidence_and_never_mutates_input_records(monkeypatch):
    expected = _care_codec_expected(regions=1)
    prefix, _ = _care_codec_prefix(expected=expected)
    initial, post = _care_codec_joins(expected)
    before = (prefix, initial, post, random.getstate())
    original = _care_codec._candidate_header
    def allocation_failure(*args, **kwargs):
        raise MemoryError
    monkeypatch.setattr(_care_codec, "_candidate_header", allocation_failure)
    assert _care_codec.finalize_care_frame(prefix, expected=expected, initial=initial, post=post) is None
    monkeypatch.setattr(_care_codec, "_candidate_header", original)
    monkeypatch.setattr(_care_codec, "_append_snapshot", allocation_failure)
    assert _care_codec.finalize_care_frame(prefix, expected=expected, initial=initial, post=post) is None
    assert (prefix, initial, post, random.getstate()) == before


def test_care_codec_stdlib_only_source_and_sentinel_objects_forbid_external_runtime_work():
    source = _care_codec_Path(_care_codec.__file__).read_text(encoding="utf-8")
    tree = _care_codec_ast.parse(source)
    imports = {node.module.split(".")[0] for node in _care_codec_ast.walk(tree)
               if isinstance(node, _care_codec_ast.ImportFrom)}
    imports.update(alias.name.split(".")[0] for node in _care_codec_ast.walk(tree)
                   if isinstance(node, _care_codec_ast.Import) for alias in node.names)
    assert imports <= {"__future__", "bisect", "dataclasses", "hashlib", "struct", "enum"}
    calls = {node.func.id for node in _care_codec_ast.walk(tree)
             if isinstance(node, _care_codec_ast.Call) and isinstance(node.func, _care_codec_ast.Name)}
    assert not calls.intersection({"open", "eval", "exec", "__import__", "World", "WorldState", "AgentSimulator", "run_turn_result"})
    class Forbidden:
        def __getattribute__(self, name):
            raise AssertionError("foreign runtime object was inspected")
    expected = _care_codec_expected(regions=1)
    prefix, _ = _care_codec_prefix(expected=expected)
    initial, post = _care_codec_joins(expected)
    rng = random.getstate()
    _care_codec_assert_refusal(prefix, expected, Forbidden(), post)
    _care_codec_assert_refusal(prefix, expected, initial, Forbidden())
    _care_codec_assert_refusal(Forbidden(), expected, initial, post)
    assert random.getstate() == rng
    assert "mechanics" in _care_codec.__doc__ and "qualification" in _care_codec.__doc__


def test_care_codec_source_binding_preserves_reviewed_native_and_python_phase_witnesses():
    # Strict current whole-file witnesses include b32's unrelated context-reader
    # early exit. Care bodies remain exact829; mechanics.SOURCE_BINDINGS keeps
    # its historical native09ec witness. These pins claim no native qualification.
    root = _care_codec_Path(__file__).resolve().parents[1]
    pins = {
        "chronicler-agents/src/health_care.rs": "d853edb7b7d4b584e22aa919dde02696580ffaa5b10f49127007102cc7aabac7",
        "chronicler-agents/src/health_care_observation.rs": "9c617fa6a252db0d2367053c466ee77560727af90825c16cab4b58b2e6791ed9",
        "chronicler-agents/src/pool.rs": "91ef1ae2eb802b75759ef1e018d930113179b767d34183d8fa637191a8b2fa1e",
        "chronicler-agents/src/tick.rs": "b2614e33e7feedab6726aa0b51f3285032873f8db4c7909e5b8821a0c83274fb",
        "chronicler-agents/src/ffi/mod.rs": "42513302f4d089fb0b769b480e5c685804cc738a50bf01b645763f192ad21677",
        "src/chronicler/health_care.py": "fc96d7c2f859865fc95023201c4c5c436cde0b8b39f53def02beb6f8557cd8ff",
        "src/chronicler/health_care_state.py": "43ea4162dd65e2a59fde602be5b670b3d4699dfe2bb4580f8402d88760a04ec8",
        "src/chronicler/agent_bridge.py": "0ad61ddadf43e1a52b55559a9708e4a5d7b90350f7a6979c192534a9d3f32e18",
        "src/chronicler/simulation.py": "99745a54e243f817930b8ab53d7b0521a63a9ea90b5be3521fa273668dd83a40",
        "src/chronicler/main.py": "0e62573977eab538606ad3be0025e371206067b347917816fb199318016c05ec",
    }
    for path, digest in pins.items():
        assert _care_codec_hashlib.sha256((root / path).read_bytes()).hexdigest() == digest
    native = (root / "chronicler-agents/src/health_care_observation.rs").read_text(encoding="utf-8")
    pool = (root / "chronicler-agents/src/pool.rs").read_text(encoding="utf-8")
    assert "health_work_loss /* CAREOBS_TRANSIENT_BEGIN */, health_care_observation" in pool
    assert "health_care_observation: None" in pool
    assert "saved_bytes(&self)" in native and "sort_unstable" in native
    assert "CAREOBS1" in _care_codec.__doc__
    # These static bytes bind source witnesses only; no actual native schema,
    # copy truthfulness, World result, physics/RNG replay or efficacy is proved.


# INDEPENDENT MECHANICS SOURCE CONTRACTS — invented primitive facts, UNRUN.
import sys as _care_mech_sys
from chronicler import health_care_observation_mechanics as _care_mech


def _care_mech_context(expected):
    return _care_mech.MechanicsContext(expected.manifest_sha256,
        "CPython" if _care_mech_sys.implementation.name == "cpython" else _care_mech_sys.implementation.name,
        tuple(_care_mech_sys.version_info[:3]), _care_mech_sys.version,
        (_care_mech_sys.float_info.radix, _care_mech_sys.float_info.mant_dig,
         _care_mech_sys.float_info.max_exp, _care_mech_sys.float_info.min_exp))


def _care_mech_view(*, expected=None, initial=None, post=None, **facts):
    """Structural fixture only; full-pipeline cases spell source-compatible facts."""
    expected = expected or _care_codec_expected(regions=1)
    if initial is None or post is None:
        episodes = tuple(_care_codec.EpisodeBits(aid, -1, _care_codec_b64(2.), 0)
                         for aid in facts.get("patients", ()))
        default_initial, default_post = _care_codec_joins(expected, initial_episodes=episodes)
        if initial is None:
            initial = default_initial
        if post is None:
            post = _care_codec_replace(default_post, summary=_care_codec_replace(
                default_post.summary, new_injuries=len(facts.get("injuries", ()))))
    prefix, _ = _care_codec_prefix(expected=expected, **facts)
    data = _care_codec.finalize_care_frame(prefix, expected=expected, initial=initial, post=post)
    return _care_codec.decode_care_frame(data, expected=expected)


def _care_mech_prepared(*, patients=(), workers=(), rows=(), health_loss=(), regions=((0, 0, 0, 0),)):
    return _care_mech._Prepared(patients, workers, rows, health_loss, regions)


def _care_mech_scope(slot=0, *, consumed=1, loss=0, current=1, region=0,
                     occupation=0, flags=7, reason=1, mask=63, numbers=(0,) * 6):
    return _care_codec.ScopedBits(slot, consumed, loss, current, region,
                                occupation, flags, reason, mask, numbers)


def _care_mech_assert_pipeline(data, expected, *, previous=None):
    context = _care_mech_context(expected)
    report = _care_mech.verify_care_mechanics(data, expected=expected,
                                            previous=previous, context=context)
    assert type(report) is _care_mech.CareMechanicsReport
    components = dict(report.components)
    assert all(components[name] is True for name in _care_mech.COMPONENTS[:-1])
    if (_care_mech_sys.implementation.name == "cpython"
            and tuple(_care_mech_sys.version_info[:3]) == (3, 13, 17)
            and _care_mech_sys.float_info.rounds == 1
            and context.producer_float_info == (2, 53, 1024, -1021)):
        assert report.verdict == "DETERMINISTIC_MATCH"
        assert components["floating_totals"] is True
    else:
        assert report.verdict == "PARTIAL"
        assert components["floating_totals"] is None
        assert report.unavailable == ("unqualified_CPython_sum",)
    assert all(value is None for _, value in report.claims)
    return report


def test_care_mechanics_ieee32_add_sub_literal_ties_zeros_and_subnormals():
    assert _care_mech._add32(0x3f800000, 0x33800000) == 0x3f800000
    assert _care_mech._add32(0x3f800001, 0x33800000) == 0x3f800002
    assert _care_mech._add32(0x3f800000, 0xbf800000) == 0
    assert _care_mech._add32(0x80000000, 0x80000000) == 0x80000000
    assert _care_mech._sub32(0x80000000, 0) == 0x80000000
    assert _care_mech._sub32(0x00800000, 1) == 0x007fffff
    assert _care_mech._add32(1, 1) == 2


def test_care_mechanics_ieee32_mul_literal_rounding_and_finite_overflow():
    assert _care_mech._mul32(0x3fc00000, 0x3f000000) == 0x3f400000
    assert _care_mech._mul32(1, 0x3f000000) == 0
    assert _care_mech._mul32(3, 0x3f000000) == 2
    assert _care_mech._mul32(0x80000000, 0xbf800000) == 0
    with _care_codec_pytest.raises(_care_mech.UnsupportedArithmetic, match="nonfinite_result"):
        _care_mech._mul32(0x7f7fffff, 0x40000000)


def test_care_mechanics_ieee32_division_and_u32_cast_are_single_rounding():
    assert _care_mech._div32(0x3f800000, 0x40400000) == 0x3eaaaaab
    assert _care_mech._div32(0x40000000, 0x40400000) == 0x3f2aaaab
    assert _care_mech._div32(0x00800000, 0x40000000) == 0x00400000
    assert _care_mech._uint_to32(16777217) == 0x4b800000
    assert _care_mech._uint_to32(16777219) == 0x4b800002
    assert _care_mech._uint_to32(4294967295) == 0x4f800000
    with _care_codec_pytest.raises(_care_mech.UnsupportedArithmetic, match="zero_divisor"):
        _care_mech._div32(0x3f800000, 0x80000000)
    for invalid in (True, -1, 1 << 32):
        with _care_codec_pytest.raises(ValueError):
            _care_mech._uint_to32(invalid)


def test_care_mechanics_ieee64_widening_recovery_operations_and_min_ties():
    assert _care_mech._widen32(0x3e4ccccd) == 0x3fc99999a0000000
    assert _care_mech._widen32(1) == 0x36a0000000000000
    assert _care_mech._widen32(0x80000000) == 0x8000000000000000
    assert _care_mech._mul64(0x4014000000000000, 0x3fc99999a0000000) == 0x3ff0000004000000
    assert _care_mech._add64(0x3ff0000000000000, 0x3fe0000000000000) == 0x3ff8000000000000
    assert _care_mech._sub64(0x4004000000000000, 0x3ff8000000000000) == 0x3ff0000000000000
    assert _care_mech._min64(0x8000000000000000, 0) == 0x8000000000000000
    assert _care_mech._min64(0, 0x8000000000000000) == 0


def test_care_mechanics_typed_constants_and_source_operator_rounding_are_explicit():
    assert (_care_mech.BASE32, _care_mech.DECAY32, _care_mech.MAX32) == (0x3e99999a, 0x3ca3d70a, 0x42c80000)
    assert _care_mech._sub32(0x3f800000, 0x3ca3d70a) == 0x3f7ae148
    assert _care_mech._mul32(0x3e99999a, 0x3f7ae148) == 0x3e96872c
    tree = _care_codec_ast.parse(_care_codec_Path(_care_mech.__file__).read_text())
    wealth = next(node for node in tree.body if isinstance(node, _care_codec_ast.FunctionDef) and node.name == "_check_wealth")
    called = [node.func.id for node in _care_codec_ast.walk(wealth)
              if isinstance(node, _care_codec_ast.Call) and isinstance(node.func, _care_codec_ast.Name)]
    assert {"_add32", "_sub32", "_mul32", "_clamp32"} <= set(called)
    assert not {"sum", "fsum", "fma"}.intersection(called)


def test_care_mechanics_nonfinite_copy_only_facts_do_not_authorize_arithmetic():
    native = _care_mech_view().native
    nan = 0x7fc01234
    dead = _care_mech_scope(flags=5, reason=4, mask=33,
                            numbers=(nan, 0, 0, 0, 0, nan))
    _care_mech._check_wealth(_care_codec_replace(native, scoped=(dead,)))
    assert not _care_mech._positive(nan, 32)
    assert _care_mech._positive(0x7f800000, 32)
    for operation in (_care_mech._add32, _care_mech._mul32, _care_mech._div32):
        with _care_codec_pytest.raises(_care_mech.UnsupportedArithmetic, match="nonfinite_operand"):
            operation(nan, 0x3f800000)


def test_care_mechanics_distinct_zero_bits_and_ambiguous_rust_ties_are_not_tolerances():
    assert _care_mech._compare(0, 0x80000000, 32) == 0
    assert _care_mech._max32_zero(0) == 0
    assert _care_mech._max32_zero(0x80000001) == 0
    assert _care_mech._clamp32(0x43160000) == 0x42c80000
    assert _care_mech._clamp32(0xbf800000) == 0
    for operation in (_care_mech._max32_zero, _care_mech._clamp32):
        with _care_codec_pytest.raises(_care_mech.UnsupportedArithmetic, match="ambiguous_rust_zero_tie"):
            operation(0x80000000)


def test_care_mechanics_actual_cpython_sum_qualification_is_never_faked_or_skipped():
    expected = _care_codec_expected(regions=1)
    context = _care_mech_context(expected)
    values = (0x4341c37937e08000, 0x3ff0000000000000, 0xc341c37937e08000)
    assert _care_mech._add64(_care_mech._add64(values[0], values[1]), values[2]) == 0
    if (_care_mech_sys.implementation.name == "cpython"
            and tuple(_care_mech_sys.version_info[:3]) == (3, 13, 17)
            and context.producer_float_info == (2, 53, 1024, -1021)
            and _care_mech_sys.float_info.rounds == 1):
        assert _care_mech._builtin_sum64(values, context) == 0x3ff0000000000000
    else:
        with _care_codec_pytest.raises(_care_mech.UnsupportedArithmetic, match="unqualified_CPython_sum"):
            _care_mech._builtin_sum64(values, context)
    unavailable = _care_codec_replace(context, producer_float_info=None)
    with _care_codec_pytest.raises(_care_mech.UnsupportedArithmetic, match="unqualified_CPython_sum"):
        _care_mech._builtin_sum64(values, unavailable)


def test_care_mechanics_global_last_alive_lookup_preserves_zero_dead_duplicates_and_sparse_ids():
    expected = _care_codec_expected(regions=2)
    slots = (_care_codec_slot(0), _care_codec_slot(7, alive=False),
             _care_codec_slot(7, age=19, region=1), _care_codec_slot(0xfffffffe))
    native = _care_mech_view(expected=expected, slots=slots, patients=(7, 0, 0xfffffffe)).native
    derived = _care_mech._derive_preparation(native, 0, "release")
    assert derived.patients == (0, 7, 0xfffffffe)
    assert derived.rows == ((0, 0, 0, 0), (7, 1, 0, 0), (0xfffffffe, 0, 0, 0))
    assert tuple(row[:3] for row in derived.workers) == ((0, 0, 0), (3, 0xfffffffe, 0))
    assert derived.regions == ((0x3f800000, 0x3ff0000000000000, 0, 0), (0, 0, 0, 0))


def test_care_mechanics_raw_input_order_differs_from_native_sorted_unique_iteration():
    native = _care_mech_view(slots=(_care_codec_slot(9), _care_codec_slot(3, settlement=12),
        _care_codec_slot(17)), patients=(9, 3, 9, 404), excluded=(17, 17), urban=(0, 12, 12)).native
    derived = _care_mech._derive_preparation(native, 0, "release")
    assert native.inputs == (9, 3, 9, 404)
    assert derived.patients == (3, 9)
    assert derived.rows == ((3, 0, 0, 0), (9, 0, 0, 0))
    assert derived.workers == ((0, 9, 0, 0x3f000000),)
    expected = _care_codec_expected(regions=1)
    view = _care_mech_view(expected=expected, patients=(404, 404))
    report = _care_mech.verify_care_mechanics(view.data, expected=expected, context=_care_mech_context(expected))
    assert report.verdict == "MISMATCH" and report.failure_section == "duplicate_incoming_episode"


def test_care_mechanics_eligibility_checks_adult_farmer_idle_excluded_urban_and_region_boundaries():
    slots = (_care_codec_slot(1, age=19), _care_codec_slot(2, age=20),
        _care_codec_slot(3, occupation=1), _care_codec_slot(4, trip=1),
        _care_codec_slot(5), _care_codec_slot(6, settlement=12),
        _care_codec_slot(7, region=65535), _care_codec_slot(8, alive=False),
        _care_codec_slot(9, trip=2), _care_codec_slot(10, trip=3))
    native = _care_mech_view(slots=slots, excluded=(5,), urban=(0, 12)).native
    derived = _care_mech._derive_preparation(native, 0, "release")
    assert derived.workers == ((1, 2, 0, 0x3f800000),)
    assert derived.rows == derived.health_loss == ()


def test_care_mechanics_complete_spouse_pass_reserves_scarce_donor_before_earlier_kin():
    slots = (_care_codec_slot(1, rel_count=1, kin=1, targets=(3,)),
             _care_codec_slot(2, rel_count=1, marriage=1, targets=(3,)),
             _care_codec_slot(3, rel_count=1, kin=1, targets=(1,)))
    native = _care_mech_view(slots=slots, patients=(1, 2)).native
    derived = _care_mech._derive_preparation(native, 1, "release")
    assert derived.rows == ((1, 0, 0, 0), (2, 0, 3, 0x3e4ccccd))
    assert derived.health_loss == ((1, 0x3f000000), (2, 0x3f000000), (3, 0x3e4ccccd))
    assert derived.regions[0][2:] == (0x3fc99999a0000000, 1)


def test_care_mechanics_raw_zero_spouse_deduction_and_release_first_marriage_sentinel_are_exact():
    slots = (_care_codec_slot(0),
        _care_codec_slot(1, rel_count=2, marriage=1, kin=2, targets=(0, 3)),
        _care_codec_slot(3, rel_count=1, kin=1, targets=(1,)))
    native = _care_mech_view(slots=slots, patients=(1,)).native
    spouse = _care_mech._derive_preparation(native, 0, "release")
    assert spouse.rows == ((1, 0, 0, 0),)
    assert spouse.health_loss == ((0, 0x3e4ccccd), (1, 0x3f000000), (0, 0))
    assert spouse.regions[0][2:] == (0x3fc99999a0000000, 1)
    kin = _care_mech._derive_preparation(native, 1, "release")
    assert kin.rows == ((1, 0, 3, 0x3e4ccccd),)
    assert kin.regions[0][2:] == (0x3fd99999a0000000, 2)
    native = _care_mech_view(slots=(_care_codec_slot(1, rel_count=2, marriage=3, targets=(0, 3)),
                                   _care_codec_slot(3)), patients=(1,)).native
    assert _care_mech._derive_preparation(native, 0, "release").rows == ((1, 0, 0, 0),)
    with _care_codec_pytest.raises(_care_mech._Mismatch, match="mechanics mismatch"):
        _care_mech._derive_preparation(native, 0, "debug")
    with _care_codec_pytest.raises(_care_mech.UnsupportedArithmetic, match="unqualified_Marriage_profile"):
        _care_mech._derive_preparation(native, 0, "unknown")


def test_care_mechanics_kin_patient_lookup_uses_last_eligible_worker_and_keeps_original_row_region():
    slots = (_care_codec_slot(7, rel_count=1, kin=1, targets=(9,)),
        _care_codec_slot(9, rel_count=1, kin=1, targets=(7,)), _care_codec_slot(7, age=19, region=1))
    native = _care_mech_view(expected=_care_codec_expected(regions=2), slots=slots, patients=(7,)).native
    derived = _care_mech._derive_preparation(native, 1, "release")
    assert derived.rows == ((7, 1, 9, 0x3e4ccccd),)
    assert derived.regions == ((0, 0, 0, 0), (0x3e4ccccd, 0, 0x3fc99999a0000000, 1))
    assert derived.health_loss == ((0, 0), (9, 0x3e4ccccd), (0, 0))


def test_care_mechanics_reciprocal_kin_is_raw_sorted_unique_with_zero_self_dead_and_absent_targets():
    slots = (_care_codec_slot(0, rel_count=7, kin=127, targets=(0, 404, 9, 7, 7, 3, 5)),
        _care_codec_slot(3), _care_codec_slot(5, rel_count=1, kin=1, targets=(0,)),
        _care_codec_slot(7, rel_count=1, kin=1, targets=(0,)), _care_codec_slot(9, alive=False))
    native = _care_mech_view(slots=slots, patients=(0,)).native
    derived = _care_mech._derive_preparation(native, 1, "release")
    assert derived.rows == ((0, 0, 5, 0x3e4ccccd),)
    assert derived.health_loss[2] == (5, 0x3e4ccccd)
    assert derived.health_loss[3] == (0, 0)


def test_care_mechanics_physical_loss_sum_then_kin_append_has_source_specific_rounding():
    slots = (_care_codec_slot(1, rel_count=1, kin=1, targets=(2,)),
        _care_codec_slot(2, rel_count=1, kin=1, targets=(1,)), _care_codec_slot(3),
        _care_codec_slot(4, rel_count=1, marriage=1, targets=(3,)))
    native = _care_mech_view(slots=slots, patients=(1, 4)).native
    derived = _care_mech._derive_preparation(native, 1, "release")
    assert derived.rows == ((1, 0, 2, 0x3e4ccccd), (4, 0, 3, 0x3e4ccccd))
    assert derived.regions[0][0] == 0x3fb33334
    final_slot_fold = _care_mech._add32(_care_mech._add32(_care_mech._add32(
        0x3f000000, 0x3e4ccccd), 0x3e4ccccd), 0x3f000000)
    assert final_slot_fold == 0x3fb33333


def test_care_mechanics_kin_assigned_duplicate_workers_update_each_own_loss_slot():
    slots = (_care_codec_slot(1, rel_count=1, kin=1, targets=(9,)), _care_codec_slot(9),
             _care_codec_slot(9, rel_count=1, kin=1, targets=(1,)))
    native = _care_mech_view(slots=slots, patients=(1,)).native
    derived = _care_mech._derive_preparation(native, 1, "release")
    assert derived.workers == ((0, 1, 0, 0x3f000000), (1, 9, 0, 0x3f800000), (2, 9, 0, 0x3f4ccccd))
    assert derived.health_loss == ((1, 0x3f000000), (0, 0), (9, 0x3e4ccccd))


def test_care_mechanics_consumed_vector_length_and_nondefaults_survive_missing_or_reused_slots():
    native = _care_mech_view(slots=(_care_codec_slot(0),), patients=(0,), losses_length=1).native
    zero = _care_codec_replace(native, impairment_b32=0, care_fraction_b32=0)
    prepared = _care_mech._derive_preparation(zero, 0, "release")
    assert prepared.health_loss == ((0, 0),)
    header = _care_mech_view(losses_length=1).header
    _care_mech._check_consumed(zero, header, prepared)
    with _care_codec_pytest.raises(_care_mech._Mismatch):
        _care_mech._check_consumed(zero, _care_mech_view().header, prepared)
    prepared = _care_mech_prepared(health_loss=((1, 0x3f000000),))
    vanished = _care_mech_scope(consumed=1, loss=0x3f000000, current=0, flags=0, reason=6, mask=0)
    reused = _care_mech_scope(consumed=1, loss=0x3f000000, current=999, reason=2)
    for row in (vanished, reused):
        _care_mech._check_consumed(_care_codec_replace(zero, scoped=(row,)), header, prepared)


def test_care_mechanics_labor_witnesses_use_u32_cast_and_separate_mul_sub_max_div():
    native = _care_mech_view().native
    prepared = _care_mech_prepared(regions=((0x3f000000, 0, 0, 0),))
    observed = _care_codec_replace(native, economy_inputs=((3, 0x3f800000, 0x3f555555, True),))
    _care_mech._check_labor(observed, prepared)
    negative = _care_codec_replace(native, economy_inputs=((1, 0x3e800000, 0, True),))
    _care_mech._check_labor(negative, prepared)
    for wrong in (((3, 0x3f800000, 0x3f400000, True),), ((3, 0x3f800000, 0x3f800000, False),)):
        with _care_codec_pytest.raises(_care_mech._Mismatch):
            _care_mech._check_labor(_care_codec_replace(native, economy_inputs=wrong), prepared)


def test_care_mechanics_worked_predicate_keeps_raw_output_order_and_last_region_update():
    native = _care_mech_view().native
    outputs = ((0, (0x7f800000, 0, 0), 0, True),
               (0, (0x7fc01234, 0x80000000, 0xff800000), 0, False))
    assert _care_mech._check_worked(_care_codec_replace(native, economy_outputs=outputs)) == (False,)
    wrong = (outputs[0], (0, outputs[1][1], 0, True))
    with _care_codec_pytest.raises(_care_mech._Mismatch):
        _care_mech._check_worked(_care_codec_replace(native, economy_outputs=wrong))


def test_care_mechanics_scope_reason_guards_preserve_dead_invalid_stale_and_nonfarmer_values():
    native = _care_codec_replace(_care_mech_view().native,
        wealth_regions=((0x3f800000, 0x3f800000, 0x3f800000),))
    base = (0, 0x3e99999a, 0x3e99999a, 0x3e99999a, 0x3e96872c, 0x3e96872c)
    charged = (0, 0x3e99999a, 0x3e19999a, 0x3e19999a, 0x3e16872c, 0x3e16872c)
    soldier = (0, 0x3f000000, 0x3f000000, 0x3f000000, 0x3efae148, 0x3efae148)
    rows = (_care_mech_scope(loss=0x3f000000, reason=0, numbers=charged),
        _care_mech_scope(1, loss=0x80000000, numbers=base),
        _care_mech_scope(2, loss=0x3f000000, current=2, reason=2, numbers=base),
        _care_mech_scope(3, loss=0x3f000000, occupation=1, reason=3, numbers=soldier),
        _care_mech_scope(4, flags=5, reason=4, mask=33, numbers=(0x7fc01234, 0, 0, 0, 0, 0x7fc01234)),
        _care_mech_scope(5, region=99, flags=3, reason=5, mask=33, numbers=(0x80000000, 0, 0, 0, 0, 0x80000000)),
        _care_mech_scope(6, current=0, flags=0, reason=6, mask=0))
    assert tuple(row.reason for row in rows) == (0, 1, 2, 3, 4, 5, 6)
    _care_mech._check_wealth(_care_codec_replace(native, scoped=rows))


def test_care_mechanics_farmer_operands_and_productivity_branch_differ_from_nonfarmer_origin():
    native = _care_mech_view().native
    row = _care_mech_scope(numbers=(0, 0x3e99999a, 0x3e99999a, 0x3e99999a, 0x3e96872c, 0x3e96872c))
    _care_mech._check_wealth(_care_codec_replace(native, scoped=(row,),
        wealth_regions=((0x3f800000, 0x3f800000, 0x3f800000),)))
    doubled = _care_codec_replace(row, numbers=(0, 0x3f19999a, 0x3f19999a, 0x3f19999a, 0x3f16872c, 0x3f16872c))
    _care_mech._check_wealth(_care_codec_replace(native, scoped=(doubled,),
        wealth_regions=((0x3f800000, 0x3f800000, 0x40000000),)))
    with _care_codec_pytest.raises(_care_mech._Mismatch):
        _care_mech._check_wealth(_care_codec_replace(native, scoped=(row,),
            wealth_regions=((0x3f800000, 0x3f800000, 0x40000000),)))


def test_care_mechanics_wealth_charge_is_one_actual_operation_chain_and_zero_money_is_valid():
    native = _care_codec_replace(_care_mech_view().native,
        wealth_regions=((0x3f800000, 0x3f800000, 0x3f800000),))
    numbers = (0, 0x3e99999a, 0x3e19999a, 0x3e19999a, 0x3e16872c, 0x3e16872c)
    row = _care_mech_scope(loss=0x3f000000, reason=0, numbers=numbers)
    _care_mech._check_wealth(_care_codec_replace(native, scoped=(row,)))
    for index in (2, 3, 4, 5):
        changed = list(numbers); changed[index] = 0
        with _care_codec_pytest.raises(_care_mech._Mismatch):
            _care_mech._check_wealth(_care_codec_replace(native,
                scoped=(_care_codec_replace(row, numbers=tuple(changed)),)))
    zero = _care_codec_replace(row, numbers=(0,) * 6)
    _care_mech._check_wealth(_care_codec_replace(native, scoped=(zero,),
        wealth_regions=((0, 0x3f800000, 0x3f800000),)))


def test_care_mechanics_finish_last_live_capacity_and_shortcircuit_bounds_are_explicit():
    expected = _care_codec_expected(regions=2)
    native = _care_mech_view(expected=expected, slots=(_care_codec_slot(0), _care_codec_slot(7)),
        patients=(0, 7), finish_slots=(_care_codec_slot(0, alive=False), _care_codec_slot(7, alive=False),
            _care_codec_slot(7, region=1), _care_codec_slot(0)), alive=((0, 0), (7, 1))).native
    prepared = _care_mech_prepared(patients=(0, 7), regions=((0, 0, 0, 0), (0, 0, 0, 0)))
    _care_mech._check_finish(native, prepared)
    worker = _care_mech_prepared(workers=((9, 77, 0, 0x3f800000),), regions=((0, 0, 0, 0), (0, 0, 0, 0)))
    _care_mech._check_injuries(native, worker, (False, False))
    with _care_codec_pytest.raises(_care_mech._Mismatch) as raised:
        _care_mech._check_injuries(native, worker, (True, False))
    assert raised.value.section == "finish_slot_out_of_bounds"


def test_care_mechanics_injury_rows_require_sorted_possible_worker_multiset_without_draw_completeness():
    native = _care_mech_view(slots=(_care_codec_slot(9), _care_codec_slot(9)),
        injuries=((9, 0, 0), (9, 0, 0))).native
    workers = ((0, 9, 0, 0x3f800000), (1, 9, 0, 0x3f800000))
    prepared = _care_mech_prepared(workers=workers)
    _care_mech._check_injuries(native, prepared, (True,))
    _care_mech._check_injuries(_care_codec_replace(native, injuries=()), prepared, (True,))
    with _care_codec_pytest.raises(_care_mech._Mismatch):
        _care_mech._check_injuries(_care_codec_replace(native, injuries=((9, 0, 0),) * 3), prepared, (True,))
    tiny = _care_codec_replace(native, rate_b32=1, injuries=((9, 0, 0),))
    half = _care_mech_prepared(workers=((0, 9, 0, 0x3f000000),))
    with _care_codec_pytest.raises(_care_mech._Mismatch):
        _care_mech._check_injuries(tiny, half, (True,))


def test_care_mechanics_python_transition_reconciles_censor_short_recovery_and_new_onset():
    expected = _care_codec_expected(regions=2)
    episodes = (_care_codec.EpisodeBits(7, -1, 0x3fe0000000000000, 0),
                _care_codec.EpisodeBits(404, -2, 0x4000000000000000, 0))
    initial, post = _care_codec_joins(expected, initial_episodes=episodes)
    post = _care_codec_replace(post, summary=_care_codec_replace(post.summary, new_injuries=1))
    view = _care_mech_view(expected=expected, initial=initial, post=post,
        slots=(_care_codec_slot(7), _care_codec_slot(9, region=1)), patients=(7, 404),
        assignments=((7, 0, 0, 0),), alive=((7, 1),), injuries=((9, 0, 1),))
    kept, regions, censored = _care_mech._derive_python(view)
    assert kept == (_care_codec.EpisodeBits(9, 20, 0x4004000000000000, 0),)
    assert censored == 1
    assert regions == (_care_codec.RegionalSummaryBits(0, 0, 1, 1, 0, 0, 0, 0x3fe0000000000000, 0),
                       _care_codec.RegionalSummaryBits(1, 1, 0, 0, 0, 0, 0, 0, 0))


def test_care_mechanics_python_summary_duplicate_sort_last_current_region_and_full_pipeline():
    expected = _care_codec_expected(regions=2)
    view = _care_mech_view(expected=expected, slots=(_care_codec_slot(9),),
        injuries=((9, 0, 0), (9, 1, 1)))
    kept, regions, censored = _care_mech._derive_python(view)
    assert kept == (_care_codec.EpisodeBits(9, 20, 0x4004000000000000, 0),
                    _care_codec.EpisodeBits(9, 20, 0x4004000000000000, 1))
    assert regions[0].new_injuries == regions[1].new_injuries == 1
    assert regions[0].episodes == 0 and regions[1].episodes == 2 and censored == 0
    expected = _care_codec_expected(regions=1)
    episode = _care_codec.EpisodeBits(7, -1, 0x3fe0000000000000, 0)
    initial, post = _care_codec_joins(expected, initial_episodes=(episode,))
    post = _care_codec_replace(post,
        summary=_care_codec.NumericSummaryBits(20, 0, 0, 0, 1, 0, 0, 0, 0x3fe0000000000000, 0),
        regions=(_care_codec.RegionalSummaryBits(0, 0, 0, 1, 0, 0, 0, 0x3fe0000000000000, 0),))
    recovered = _care_mech_view(expected=expected, initial=initial, post=post,
        slots=(_care_codec_slot(7, age=19),), patients=(7,), assignments=((7, 0, 0, 0),),
        alive=((7, 65535),), finish_slots=(_care_codec_slot(7, age=19, region=65535),))
    _care_mech_assert_pipeline(recovered.data, expected)
    wrong_post = _care_codec_replace(post, summary=_care_codec_replace(post.summary, recoveries=2))
    wrong = _care_mech_view(expected=expected, initial=initial, post=wrong_post,
        slots=(_care_codec_slot(7, age=19),), patients=(7,), assignments=((7, 0, 0, 0),),
        alive=((7, 65535),), finish_slots=(_care_codec_slot(7, age=19, region=65535),))
    report = _care_mech.verify_care_mechanics(wrong.data, expected=expected, context=_care_mech_context(expected))
    assert report.verdict == "MISMATCH" and report.failure_section == "summary_integer_totals"


def test_care_mechanics_bound_bytes_context_report_and_purity_refuse_forged_authority(monkeypatch):
    expected = _care_codec_expected(regions=1)
    view = _care_mech_view(expected=expected)
    before = random.getstate()
    report = _care_mech_assert_pipeline(view.data, expected)
    assert random.getstate() == before
    assert report.frame_sha256 == _care_codec_hashlib.sha256(view.data).digest()
    assert report.source_bindings == _care_mech.SOURCE_BINDINGS
    assert all(value is None for _, value in report.claims)
    assert dict(report.claims)["native_injury_draws"] is None
    assert dict(report.claims)["source_copy_truth"] is None
    with _care_codec_pytest.raises(AttributeError):
        report.verdict = "forged"
    for context in (_care_codec_replace(_care_mech_context(expected), manifest_sha256=b"x" * 32),
                    _care_codec_replace(_care_mech_context(expected), source_bindings=()),
                    _care_codec_replace(_care_mech_context(expected), native_profile="unbounded")):
        refused = _care_mech.verify_care_mechanics(view.data, expected=expected, context=context)
        assert refused.verdict == "INCOMPLETE" and refused.unavailable == ("invalid_source_context",)
    malformed = _care_mech.verify_care_mechanics(bytearray(view.data), expected=expected,
                                               context=_care_mech_context(expected))
    assert malformed.verdict == "INCOMPLETE"
    later_expected = _care_codec_expected(regions=1, ordinal=1)
    later_prefix, _ = _care_codec_prefix(expected=later_expected)
    _, later_post = _care_codec_joins(later_expected)
    later_data = _care_codec.finalize_care_frame(later_prefix, expected=later_expected,
        initial=None, post=later_post, previous=view)
    later_report = _care_mech_assert_pipeline(later_data, later_expected, previous=view)
    forged = _care_codec_replace(view,
        native=_care_codec_replace(view.native, inputs=(404,)),
        post=_care_codec_replace(view.post, summary=_care_codec_replace(view.post.summary, recoveries=999)),
        frame_sha256=b"x" * 32)
    assert _care_mech_assert_pipeline(later_data, later_expected, previous=forged) == later_report
    bad_previous = bytearray(view.data); bad_previous[256] ^= 1
    broken = _care_mech.verify_care_mechanics(later_data, expected=later_expected,
        previous=_care_codec_replace(view, data=bytes(bad_previous)), context=_care_mech_context(later_expected))
    assert broken.verdict == "INCOMPLETE" and broken.unavailable == ("malformed_frame",)
    too_large = view.data + bytes(131073 - len(view.data))
    assert _care_mech.verify_care_mechanics(too_large, expected=expected,
        context=_care_mech_context(expected)).verdict == "INCOMPLETE"
    assert _care_mech.INTEGER_BITS == 8192
    with _care_codec_pytest.raises(_care_mech.UnsupportedArithmetic, match="internal_integer_bound"):
        _care_mech._bounded(1 << 8192)
    bindings = dict(_care_mech.SOURCE_BINDINGS)
    assert bindings["codec"] == _care_codec_hashlib.sha256(
        _care_codec_Path(_care_codec.__file__).read_bytes()).hexdigest()
    witness = {"section": report.failure_section, "index": report.failure_index,
               "frame_sha256": report.frame_sha256.hex()}
    assert len(json.dumps(witness, separators=(",", ":")).encode()) <= 512
    source = _care_codec_Path(_care_mech.__file__).read_text()
    tree = _care_codec_ast.parse(source)
    names = {node.func.id for node in _care_codec_ast.walk(tree)
             if isinstance(node, _care_codec_ast.Call) and isinstance(node.func, _care_codec_ast.Name)}
    assert not names.intersection({"open", "eval", "exec", "__import__", "World", "AgentSimulator", "run_turn_result"})
    def allocation_failure(*args, **kwargs):
        raise MemoryError
    monkeypatch.setattr(_care_mech.codec, "decode_care_frame", allocation_failure)
    assert _care_mech.verify_care_mechanics(view.data, expected=expected,
                                          context=_care_mech_context(expected)) is None
