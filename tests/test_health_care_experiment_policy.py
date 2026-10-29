"""Pure experiment-policy receipts with owned models and metadata-only stubs."""
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
import pickle
import random
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest import mock

from chronicler import health_care
from chronicler.expansion_experiment import (
    CONTROL_FIELDS, allowed_control_fields, apply_expansion_experiment,
    controls_for_state,
)
from chronicler.health_care_state import HealthCareState, InjuryEpisode


LEGACY_FIELDS = ("care_enabled", "injury_rate", "impairment", "care_fraction", "recovery_work")
LEGACY_VALUES = dict(care_enabled=True, injury_rate=.02, impairment=.4,
                     care_fraction=.25, recovery_work=3.)
RECEIPT_FIELDS = (
    "schema_version", "experiment", "cohort", "feature", "arm", "intervention_fork",
    "applied_before_turn", "seed", "controls_before", "controls_after",
    "parent_checkpoint", "registration", "source", "native", "previous_experiment",
)
SOURCE = dict(git_sha="c" * 40, git_ref=None, package_dir="/synthetic/source",
              package_digest="d" * 64)
NATIVE = {"status": "absent"}
PARENT_PATH = "/__health_policy_metadata__/parent.ckpt"
REGISTRATION_PATH = "/__health_policy_metadata__/registration.json"
PARENT_SHA = "a" * 64
REGISTRATION_SHA = "b" * 64


def state(*, policy="spouse", missing_policy=False):
    value = HealthCareState(
        episodes=[InjuryEpisode(agent_id=7, onset_turn=31, remaining=3., origin_region=0)],
        last_tick_turn=36, summary={"source_turn": 36, "care_work": .25},
        care_policy=policy, **LEGACY_VALUES,
    )
    if missing_policy:
        value.__dict__.pop("care_policy")
        value.__pydantic_fields_set__.discard("care_policy")
        value = pickle.loads(pickle.dumps(value))
        assert "care_policy" not in value.__dict__
    return value


def world(value):
    return SimpleNamespace(health_care=value, turn=37, seed=42)


def request(controls=None, **extra):
    value = dict(schema_version=1, experiment="care-policy-probe", cohort="development",
                 feature="health_care", arm="control", controls={} if controls is None else controls,
                 fork=False)
    value.update(extra)
    return value


@contextmanager
def metadata(*, header_changes=None, source=None):
    """Expose only the four metadata helpers used by the experiment seam."""
    batch = ModuleType("chronicler.batch_manifest")
    batch.source_identity = mock.Mock(return_value=deepcopy(SOURCE if source is None else source))
    batch.native_identity = mock.Mock(return_value=deepcopy(NATIVE))
    hashes = {PARENT_PATH: PARENT_SHA, REGISTRATION_PATH: REGISTRATION_SHA}

    def digest(path):
        # A new unexpected path is a test failure, never a filesystem fallback.
        return hashes[str(path)]

    batch.file_sha256 = mock.Mock(side_effect=digest)
    checkpoint = ModuleType("chronicler.run_checkpoint")
    header = dict(turn=37, seed=42, exact=True,
                  identity={"source": deepcopy(SOURCE), "native": deepcopy(NATIVE)},
                  flags={"health_care": True})
    header.update(header_changes or {})
    checkpoint.read_header = mock.Mock(return_value=(header, b"opaque-unread-body"))
    with mock.patch.dict(sys.modules, {batch.__name__: batch, checkpoint.__name__: checkpoint}), \
            mock.patch.object(sys.modules["chronicler"], "batch_manifest", batch, create=True), \
            mock.patch.object(sys.modules["chronicler"], "run_checkpoint", checkpoint, create=True):
        yield SimpleNamespace(batch=batch, checkpoint=checkpoint, header=header)


class HealthCareExperimentPolicyTests(unittest.TestCase):
    def assert_progress_preserved(self, w, original, episodes, patient, summary):
        self.assertIs(w.health_care, original)
        self.assertIs(original.episodes, episodes)
        self.assertIs(original.episodes[0], patient)
        self.assertIs(original.summary, summary)
        self.assertEqual(patient.model_dump(), dict(agent_id=7, onset_turn=31, remaining=3., origin_region=0))
        self.assertEqual(original.last_tick_turn, 36)
        self.assertEqual(original.summary, {"source_turn": 36, "care_work": .25})
        self.assertEqual((w.turn, w.seed), (37, 42))

    def test_control_registry_keeps_exact_legacy_tuples_and_key_order(self):
        expected = {
            "harvest_forecasts": ("policy",),
            "ritual_gatherings": ("contact_enabled", "bonds_enabled"),
            "health_care": LEGACY_FIELDS,
            "scientific_claims": ("withhold_information", "transmission_enabled", "uninformative_tests", "publication_rule"),
        }
        self.assertEqual(list(CONTROL_FIELDS), list(expected))
        self.assertEqual(CONTROL_FIELDS, expected)
        for feature in expected:
            with self.subTest(feature=feature):
                extra = {"care_policy"} if feature == "health_care" else (
                    {"research_enabled"} if feature == "scientific_claims" else set())
                self.assertEqual(allowed_control_fields(feature), set(expected[feature]) | extra)

    def test_omitted_policy_keeps_exact_legacy_control_and_receipt_order(self):
        for missing in (False, True):
            with self.subTest(old_pickle_field_absent=missing), metadata() as m:
                original = state(missing_policy=missing)
                w = world(original)
                config = {"expansion_experiment": {"arm": "prior", "lineage": [1, 2]}}
                before_config = deepcopy(config)
                req = request({"care_enabled": False})
                before_req = deepcopy(req)
                receipt = apply_expansion_experiment(w, config, req, resumed=False)
                after = {**LEGACY_VALUES, "care_enabled": False}
                expected = dict(
                    schema_version=1, experiment="care-policy-probe", cohort="development",
                    feature="health_care", arm="control", intervention_fork=False,
                    applied_before_turn=37, seed=42, controls_before=LEGACY_VALUES,
                    controls_after=after, parent_checkpoint=None, registration=None,
                    source=SOURCE, native=NATIVE, previous_experiment=before_config["expansion_experiment"],
                )
                self.assertEqual(receipt, expected)
                self.assertEqual(tuple(receipt), RECEIPT_FIELDS)
                self.assertEqual(tuple(receipt["controls_before"]), LEGACY_FIELDS)
                self.assertEqual(tuple(receipt["controls_after"]), LEGACY_FIELDS)
                self.assertEqual(controls_for_state("health_care", original), after)
                self.assertEqual(config, before_config)
                self.assertEqual(req, before_req)
                self.assertIsNot(receipt["previous_experiment"], config["expansion_experiment"])
                self.assertEqual("care_policy" in original.__dict__, not missing)
                m.batch.file_sha256.assert_not_called()
                m.checkpoint.read_header.assert_not_called()
                m.batch.source_identity.assert_called_once_with()
                m.batch.native_identity.assert_called_once_with()

    def test_explicit_retained_policy_appends_both_receipts_and_applies_first_once(self):
        original = state()
        w = world(original)
        writes = []
        prior_setattr = HealthCareState.__setattr__

        def record_write(target, name, value):
            if target is original:
                writes.append(name)
            return prior_setattr(target, name, value)

        with metadata(), mock.patch.object(HealthCareState, "__setattr__", record_write):
            receipt = apply_expansion_experiment(
                w, {}, request({"care_policy": "retained_kin", "care_enabled": False, "care_fraction": .3}),
                resumed=False,
            )
        self.assertEqual(receipt["controls_before"], {**LEGACY_VALUES, "care_policy": "spouse"})
        self.assertEqual(receipt["controls_after"], {**LEGACY_VALUES, "care_enabled": False,
                                                    "care_fraction": .3, "care_policy": "retained_kin"})
        self.assertEqual(tuple(receipt["controls_before"]), LEGACY_FIELDS + ("care_policy",))
        self.assertEqual(tuple(receipt["controls_after"]), LEGACY_FIELDS + ("care_policy",))
        self.assertEqual(writes, ["care_policy", *LEGACY_FIELDS])
        self.assertEqual(health_care.get_health_care_policy(original), "retained_kin")
        self.assertIs(original.care_enabled, False)

    def test_explicit_reversion_is_in_both_receipts_and_really_applied(self):
        original = state(policy="retained_kin")
        w = world(original)
        episodes, patient, summary = original.episodes, original.episodes[0], original.summary
        with metadata():
            receipt = apply_expansion_experiment(w, {}, request({"care_policy": "spouse"}), resumed=False)
        self.assertEqual(receipt["controls_before"], {**LEGACY_VALUES, "care_policy": "retained_kin"})
        self.assertEqual(receipt["controls_after"], {**LEGACY_VALUES, "care_policy": "spouse"})
        self.assertEqual(tuple(receipt["controls_before"]), LEGACY_FIELDS + ("care_policy",))
        self.assertEqual(tuple(receipt["controls_after"]), LEGACY_FIELDS + ("care_policy",))
        self.assertEqual(health_care.get_health_care_policy(original), "spouse")
        self.assertNotIn("care_policy", original.model_dump())
        self.assert_progress_preserved(w, original, episodes, patient, summary)

    def test_explicit_legacy_noop_is_recorded_even_with_absent_old_pickle_field(self):
        original = state(missing_policy=True)
        with metadata():
            receipt = apply_expansion_experiment(world(original), {}, request({"care_policy": "spouse"}), resumed=False)
        self.assertEqual(receipt["controls_before"], {**LEGACY_VALUES, "care_policy": "spouse"})
        self.assertEqual(receipt["controls_after"], {**LEGACY_VALUES, "care_policy": "spouse"})
        self.assertNotIn("care_policy", original.__dict__)
        self.assertEqual(health_care.get_health_care_policy(original), "spouse")

    def test_saved_nonlegacy_policy_is_recorded_when_request_omits_it_without_setter(self):
        original = state(policy="retained_kin")
        with metadata(), mock.patch.object(health_care, "set_health_care_policy",
                                           side_effect=AssertionError("omitted policy must not call setter")) as setter:
            receipt = apply_expansion_experiment(world(original), {}, request({"care_fraction": .4}), resumed=False)
        setter.assert_not_called()
        self.assertEqual(receipt["controls_before"], {**LEGACY_VALUES, "care_policy": "retained_kin"})
        self.assertEqual(receipt["controls_after"], {**LEGACY_VALUES, "care_fraction": .4,
                                                    "care_policy": "retained_kin"})
        self.assertEqual(health_care.get_health_care_policy(original), "retained_kin")

    def test_omitted_legacy_policy_never_calls_setter_or_writes_policy(self):
        original = state()
        writes = []
        prior_setattr = HealthCareState.__setattr__

        def record_write(target, name, value):
            if target is original:
                writes.append(name)
            return prior_setattr(target, name, value)

        with metadata(), mock.patch.object(HealthCareState, "__setattr__", record_write), \
                mock.patch.object(health_care, "set_health_care_policy",
                                  side_effect=AssertionError("legacy request must not call setter")) as setter:
            receipt = apply_expansion_experiment(world(original), {}, request(), resumed=False)
        setter.assert_not_called()
        self.assertEqual(writes, list(LEGACY_FIELDS))
        self.assertNotIn("care_policy", receipt["controls_before"])
        self.assertNotIn("care_policy", receipt["controls_after"])

    def test_invalid_policy_or_other_control_is_transactional(self):
        cases = [
            {"care_policy": "kin"}, {"care_policy": False}, {"care_policy": None},
            {"care_policy": "retained_kin", "impairment": 1.1},
            {"care_policy": "retained_kin", "care_fraction": float("inf")},
            {"care_policy": "retained_kin", "injury_rate": float("nan")},
            {"care_policy": "retained_kin", "care_enabled": 0},
            {"care_policy": "retained_kin", "recovery_work": 0},
            {"care_policy": "retained_kin", "episodes": []},
            {"care_policy": "retained_kin", "research_enabled": True},
        ]
        for controls in cases:
            with self.subTest(controls=controls), metadata() as m:
                original = state()
                before = pickle.dumps(original)
                config = {"expansion_experiment": {"arm": "prior"}}
                with self.assertRaises(ValueError):
                    apply_expansion_experiment(world(original), config, request(controls), resumed=False)
                self.assertEqual(pickle.dumps(original), before)
                self.assertEqual(config, {"expansion_experiment": {"arm": "prior"}})
                m.batch.source_identity.assert_not_called()
                m.batch.native_identity.assert_not_called()

    def test_invalid_registration_is_checked_before_any_policy_or_other_mutation(self):
        for registration, cohort in ((None, "confirmatory"), ({"path": REGISTRATION_PATH}, "development"),
                                     ({"path": REGISTRATION_PATH, "sha256": "f" * 64}, "development"),
                                     ({"path": 3, "sha256": REGISTRATION_SHA}, "development")):
            with self.subTest(registration=registration), metadata() as m:
                original = state()
                before = pickle.dumps(original)
                req = request({"care_policy": "retained_kin", "care_enabled": False},
                              registration=registration, cohort=cohort)
                with self.assertRaises(ValueError):
                    apply_expansion_experiment(world(original), {}, req, resumed=False)
                self.assertEqual(pickle.dumps(original), before)
                m.batch.source_identity.assert_not_called()
                m.batch.native_identity.assert_not_called()

    def test_valid_confirmatory_registration_is_metadata_only_and_copied(self):
        req = request({"care_policy": "retained_kin"}, cohort="confirmatory",
                      registration={"path": REGISTRATION_PATH, "sha256": REGISTRATION_SHA})
        with metadata() as m:
            receipt = apply_expansion_experiment(world(state()), {}, req, resumed=False)
            m.batch.file_sha256.assert_called_once_with(Path(REGISTRATION_PATH))
            m.checkpoint.read_header.assert_not_called()
        self.assertEqual(receipt["registration"], req["registration"])
        self.assertIsNot(receipt["registration"], req["registration"])
        self.assertNotIn("gate_status", receipt)

    def test_resume_requires_explicit_fork_and_parent_identity_transactionally(self):
        cases = [
            (False, None, {}),
            (True, None, {}),
            (True, {"path": PARENT_PATH, "sha256": "f" * 64}, {}),
            (True, {"path": PARENT_PATH, "sha256": PARENT_SHA, "extra": 1}, {}),
            (True, {"path": PARENT_PATH, "sha256": PARENT_SHA}, {"turn": 38}),
            (True, {"path": PARENT_PATH, "sha256": PARENT_SHA}, {"seed": 43}),
        ]
        for fork, parent, changed_header in cases:
            with self.subTest(fork=fork, parent=parent, header=changed_header), metadata(header_changes=changed_header) as m:
                original = state()
                before = pickle.dumps(original)
                req = request({"care_policy": "retained_kin", "care_fraction": .3},
                              fork=fork, parent_checkpoint=parent)
                with self.assertRaises(ValueError):
                    apply_expansion_experiment(world(original), {}, req, resumed=True)
                self.assertEqual(pickle.dumps(original), before)
                m.batch.source_identity.assert_not_called()
                m.batch.native_identity.assert_not_called()

    def test_fresh_request_cannot_claim_a_parent_or_resumed_fork(self):
        for extra in ({"fork": True}, {"parent_checkpoint": {"path": PARENT_PATH, "sha256": PARENT_SHA}}):
            with self.subTest(extra=extra), metadata() as m:
                original = state()
                before = pickle.dumps(original)
                with self.assertRaises(ValueError):
                    apply_expansion_experiment(world(original), {}, request({"care_policy": "retained_kin"}, **extra), resumed=False)
                self.assertEqual(pickle.dumps(original), before)
                m.checkpoint.read_header.assert_not_called()

    def test_valid_resumed_policy_change_and_reversion_preserve_progress_and_lineage(self):
        for policy, requested in (("spouse", "retained_kin"), ("retained_kin", "spouse")):
            with self.subTest(policy=policy, requested=requested), metadata() as m:
                original = state(policy=policy)
                w = world(original)
                episodes, patient, summary = original.episodes, original.episodes[0], original.summary
                config = {"expansion_experiment": {"arm": "parent", "turn": 36}}
                before_config = deepcopy(config)
                req = request({"care_policy": requested}, fork=True,
                              parent_checkpoint={"path": PARENT_PATH, "sha256": PARENT_SHA})
                receipt = apply_expansion_experiment(w, config, req, resumed=True)
                self.assertEqual(receipt["controls_before"]["care_policy"], policy)
                self.assertEqual(receipt["controls_after"]["care_policy"], requested)
                self.assertEqual(health_care.get_health_care_policy(original), requested)
                self.assertIs(receipt["intervention_fork"], True)
                self.assertEqual(receipt["parent_checkpoint"], dict(
                    path=PARENT_PATH, sha256=PARENT_SHA, turn=37, seed=42,
                    identity=m.header["identity"], flags=m.header["flags"], exact=True))
                m.batch.file_sha256.assert_called_once_with(Path(PARENT_PATH))
                m.checkpoint.read_header.assert_called_once_with(Path(PARENT_PATH))
                self.assertEqual(receipt["previous_experiment"], {"arm": "parent", "turn": 36})
                self.assertEqual(config, before_config)
                self.assert_progress_preserved(w, original, episodes, patient, summary)

    def test_prepared_policy_change_refuses_before_any_control_mutation(self):
        for policy, requested in (("spouse", "retained_kin"), ("retained_kin", "spouse")):
            with self.subTest(policy=policy), metadata():
                original = state(policy=policy)
                original._prepared = [(7, 0, 9, .25)]
                prepared = original._prepared
                before = pickle.dumps(original)
                with self.assertRaisesRegex(ValueError, "prepared"):
                    apply_expansion_experiment(world(original), {}, request(
                        {"care_policy": requested, "care_fraction": .4, "care_enabled": False}), resumed=False)
                self.assertEqual(pickle.dumps(original), before)
                self.assertIs(original._prepared, prepared)

    def test_late_invalid_receipt_metadata_is_transactional(self):
        original = state()
        before = pickle.dumps(original)
        with metadata(source={"invalid": float("nan")}):
            with self.assertRaises(ValueError):
                apply_expansion_experiment(world(original), {}, request(
                    {"care_policy": "retained_kin", "care_enabled": False}), resumed=False)
        self.assertEqual(pickle.dumps(original), before)

    def test_disabled_health_cannot_be_enabled_by_policy_request(self):
        w = world(None)
        with metadata() as m, self.assertRaisesRegex(ValueError, "enabled"):
            apply_expansion_experiment(w, {}, request({"care_policy": "retained_kin"}), resumed=False)
        self.assertIsNone(w.health_care)
        m.batch.source_identity.assert_not_called()
        m.batch.native_identity.assert_not_called()

    def test_policy_requests_do_not_draw_python_rng_or_allocate_work(self):
        cases = [("spouse", {}), ("spouse", {"care_policy": "retained_kin"}),
                 ("retained_kin", {"care_policy": "spouse"}), ("retained_kin", {})]
        for policy, controls in cases:
            with self.subTest(policy=policy, controls=controls), metadata() as m:
                original = state(policy=policy)
                rng = random.getstate()
                apply_expansion_experiment(world(original), {}, request(controls), resumed=False)
                self.assertEqual(random.getstate(), rng)
                self.assertIsNone(original._prepared)
                m.batch.native_identity.assert_called_once_with()  # A stubbed metadata record only.


if __name__ == "__main__":
    unittest.main()
