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
