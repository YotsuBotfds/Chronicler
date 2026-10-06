"""Bounded offline composition gates, including real cooperating contenders."""

from contextlib import ExitStack, redirect_stdout, redirect_stderr
from dataclasses import FrozenInstanceError, asdict, replace
import hashlib
import io
import json
import os
from pathlib import Path
import runpy
import selectors
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

from chronicler import experiment_sessions as es
from chronicler import memome_experiment as mm
from chronicler import session_operations as operations


ROOT = Path(__file__).resolve().parents[1]
DRIVER = ROOT / "scripts" / "session_operation.py"
CAMPAIGN = runpy.run_path(str(ROOT / "scripts" / "campaign_logistics_demo.py"))
MEMOME = runpy.run_path(str(ROOT / "scripts" / "memome_demo.py"))


def json_bytes(payload):
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def submission(record):
    return json_bytes(asdict(record))


def fixture_session(kernel):
    if kernel == "m60a":
        policy, topology = CAMPAIGN["illustrative_policy"](), CAMPAIGN["fixture_topology"]()
        state = CAMPAIGN["fixture_session"](policy, topology).state
        return es.create_campaign_session(
            policy=policy, topology=topology, campaign_id=state.campaign_id,
            turn=state.admission_turn, staging=state.staging, target=state.target,
            soldiers=state.soldiers, stocks=state.stocks)
    people, _ = MEMOME["unit_tables"]()
    return es.create_memome_session(policy=MEMOME["illustrative_policy"](),
                                     genesis_turn=0, participants=people)


def first_input(session):
    if type(session) is es.CampaignSession:
        return CAMPAIGN["fixture_tick"](session.session, 1)
    return MEMOME["unit_tables"]()[1][0]


def advance(session, record):
    if type(session) is es.CampaignSession:
        return es.apply_campaign_tick(session, record).session
    return es.apply_memome_batch(session, record).session


def identity(loaded):
    return operations.SessionIdentity(loaded.generation, loaded.digest,
                                       loaded.envelope.session_digest, loaded.turn)


def contender(path, transport_path, submission_path):
    """Child-local instrumentation pauses after the real public load returns."""
    transport = es.transport_policy_from_text(Path(transport_path).read_text())
    body = Path(submission_path).read_bytes()
    original_load = es.load_session

    def barrier_load(*args, **kwargs):
        loaded = original_load(*args, **kwargs)
        print(json.dumps({"ready": identity(loaded).as_payload()}), flush=True)
        if sys.stdin.readline() != "release\n":
            raise RuntimeError("test-owned contender barrier was not released")
        return loaded

    with mock.patch.object(es, "load_session", barrier_load):
        try:
            receipt = operations.apply_operation(path, transport=transport, submission=body)
        except (ValueError, OSError) as error:
            receipt = error.operation_receipt
    print(json.dumps(receipt.as_payload(), sort_keys=True), flush=True)


def unlock_failure(path, transport_path, submission_path):
    """The real unlock happens, then fails; the existing finally must still close."""
    transport = es.transport_policy_from_text(Path(transport_path).read_text())
    original = es.fcntl.flock
    lock_descriptors = []

    def fail_after_unlock(descriptor, operation):
        result = original(descriptor, operation)
        if operation == es.fcntl.LOCK_EX:
            lock_descriptors.append(descriptor)
        if operation == es.fcntl.LOCK_UN:
            raise OSError("injected postpublication unlock failure")
        return result

    with mock.patch.object(es.fcntl, "flock", fail_after_unlock):
        try:
            operations.apply_operation(path, transport=transport,
                                        submission=Path(submission_path).read_bytes())
        except es.CommittedCleanupError as error:
            receipt = error.operation_receipt
            assert error.__cause__ is error.cleanup_error
            assert isinstance(error.cleanup_error, OSError)
            assert str(error.cleanup_error) == "injected postpublication unlock failure"
            loaded = es.load_session(path, transport=transport)
            assert error.result.generation == loaded.generation
            assert error.result.digest == loaded.digest
            assert error.result.envelope.session_digest == loaded.envelope.session_digest
            assert error.result.turn == loaded.turn
        else:
            raise AssertionError("postpublication unlock failure did not surface")
    for descriptor in lock_descriptors:
        try:
            os.fstat(descriptor)
        except OSError:
            pass
        else:
            raise AssertionError("test-owned writer descriptor was not closed")
    print(json.dumps(receipt.as_payload(), sort_keys=True), flush=True)


class _SessionCase(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.workdir = Path(temporary.name)
        self.target = self.workdir / "session.json"
        self.transport = es.documented_transport_policy()

    def create(self, session, transport=None):
        return es.commit_session(self.target, session, transport=transport or self.transport,
                                  expected_generation=None, expected_digest=None)

    def apply(self, record, transport=None):
        return operations.apply_operation(self.target, transport=transport or self.transport,
                                            submission=submission(record))

    def reconcile(self, receipt):
        return operations.reconcile_operation(self.target, transport=self.transport,
                                                expectation=receipt.expectation)


class SessionOperationsTests(_SessionCase):
    def test_public_kernel_results_exact_next_file_identities_and_single_commit(self):
        for kernel in ("m60a", "m68a"):
            with self.subTest(kernel=kernel):
                self.target.unlink(missing_ok=True)
                initial = fixture_session(kernel)
                self.create(initial)
                before = es.load_session(self.target, transport=self.transport)
                record = first_input(initial)
                expected = advance(initial, record)
                envelope = es.encode_session(expected, transport=self.transport, generation=2)
                expected_bytes = es.encode_envelope_text(envelope, self.transport)
                with mock.patch.object(es, "commit_session", wraps=es.commit_session) as commit:
                    receipt = self.apply(record)
                self.assertEqual(commit.call_count, 1)
                self.assertEqual(commit.call_args.kwargs["expected_generation"], 1)
                self.assertEqual(commit.call_args.kwargs["expected_digest"], before.digest)
                self.assertEqual(receipt.status, "committed_durable")
                self.assertEqual(receipt.base, identity(before))
                self.assertEqual(receipt.intended, operations.SessionIdentity(
                    2, hashlib.sha256(expected_bytes).hexdigest(), envelope.session_digest, 1))
                self.assertNotEqual(receipt.intended.file_digest, receipt.intended.session_digest)
                self.assertEqual(self.target.read_bytes(), expected_bytes)
                loaded = es.load_session(self.target, transport=self.transport)
                self.assertEqual(loaded.session, expected)
                self.assertEqual(operations.identity_from_payload(
                    receipt.intended.as_payload()), receipt.intended)
                with self.assertRaises(FrozenInstanceError):
                    receipt.status = "wrong"
                with self.assertRaises(FrozenInstanceError):
                    receipt.intended.turn = 99

    def test_replay_does_not_commit_touch_bytes_or_increment_generation(self):
        for kernel in ("m60a", "m68a"):
            with self.subTest(kernel=kernel):
                self.target.unlink(missing_ok=True)
                initial = fixture_session(kernel)
                record = first_input(initial)
                self.create(advance(initial, record))
                before = self.target.read_bytes(), self.target.stat().st_mtime_ns
                with mock.patch.object(es, "commit_session", side_effect=AssertionError(
                        "replay must not commit")):
                    receipt = self.apply(record)
                self.assertEqual(receipt.status, "replay_no_write")
                self.assertIsNone(receipt.intended)
                self.assertEqual(receipt.base.generation, 1)
                self.assertEqual((self.target.read_bytes(), self.target.stat().st_mtime_ns), before)

    def test_original_order_late_memome_replay_preserves_latest_ledger_and_generation(self):
        session = fixture_session("m68a")
        batches = MEMOME["unit_tables"]()[1]
        for batch in batches:
            session = advance(session, batch)
        self.assertNotEqual(session.batches[0].proposals, batches[0].proposals)
        self.create(session)
        before = self.target.read_bytes(), self.target.stat().st_mtime_ns
        with mock.patch.object(es, "commit_session", side_effect=AssertionError("no write")):
            receipt = self.apply(batches[0])
        self.assertEqual((receipt.status, receipt.base.generation, receipt.base.turn),
                         ("replay_no_write", 1, 3))
        self.assertEqual((self.target.read_bytes(), self.target.stat().st_mtime_ns), before)
        self.assertEqual(es.load_session(self.target, transport=self.transport).session, session)
        contradictory = replace(batches[0], proposals=(replace(batches[0].proposals[0], draw=1),))
        with self.assertRaises(ValueError) as caught:
            self.apply(contradictory)
        self.assertEqual(caught.exception.operation_receipt.status, "rejected")
        self.assertEqual(caught.exception.operation_receipt.base.turn, 3)
        self.assertIsNone(caught.exception.operation_receipt.intended)
        self.assertEqual((self.target.read_bytes(), self.target.stat().st_mtime_ns), before)

    def test_stale_type_and_intended_identities_survive_without_any_retry(self):
        session = fixture_session("m68a")
        self.create(session)
        error = es.StaleGenerationError("injected competing commit")
        before = self.target.read_bytes()
        with mock.patch.object(es, "commit_session", side_effect=error) as commit:
            with self.assertRaises(es.StaleGenerationError) as caught:
                self.apply(first_input(session))
        self.assertIs(caught.exception, error)
        self.assertEqual(commit.call_count, 1)
        receipt = error.operation_receipt
        self.assertEqual(receipt.status, "stale_conflict")
        self.assertEqual((receipt.base.generation, receipt.intended.generation), (1, 2))
        self.assertEqual(receipt.error.error_type, "StaleGenerationError")
        self.assertEqual(self.target.read_bytes(), before)

    def test_file_fsync_and_replace_refusals_preserve_base_and_temporary_cleanup(self):
        session = fixture_session("m68a")
        self.create(session)
        before = self.target.read_bytes()
        original_fsync = os.fsync

        def fail_file_fsync(descriptor):
            if stat.S_ISREG(os.fstat(descriptor).st_mode):
                raise OSError("injected file fsync failure")
            return original_fsync(descriptor)

        patchers = (mock.patch.object(es.os, "fsync", fail_file_fsync),
                    mock.patch.object(es.os, "replace", side_effect=OSError("injected replace failure")))
        for patcher in patchers:
            with self.subTest(patcher=patcher):
                with patcher, self.assertRaises(es.PersistenceError) as caught:
                    self.apply(first_input(session))
                self.assertNotIsInstance(caught.exception, es.DurabilityUncertain)
                receipt = caught.exception.operation_receipt
                self.assertEqual(receipt.status, "rejected")
                self.assertEqual(receipt.error.error_type, "PersistenceError")
                self.assertEqual(self.target.read_bytes(), before)
                self.assertEqual(list(self.workdir.glob(".*.tmp")), [])
                reconciliation = self.reconcile(receipt)
                self.assertEqual(reconciliation.status, "base_visible")
                self.assertEqual(reconciliation.current, receipt.base)

    def test_directory_fsync_failure_keeps_intended_visible_but_durability_unknown(self):
        session = fixture_session("m68a")
        self.create(session)
        original_fsync = os.fsync

        def fail_directory_fsync(descriptor):
            if stat.S_ISDIR(os.fstat(descriptor).st_mode):
                raise OSError("injected directory fsync failure")
            return original_fsync(descriptor)

        with mock.patch.object(es.os, "fsync", fail_directory_fsync), self.assertRaises(
                es.DurabilityUncertain) as caught:
            self.apply(first_input(session))
        receipt = caught.exception.operation_receipt
        self.assertEqual(receipt.status, "durability_uncertain")
        self.assertEqual(receipt.error.error_type, "DurabilityUncertain")
        self.assertEqual(hashlib.sha256(self.target.read_bytes()).hexdigest(),
                         receipt.intended.file_digest)
        before = self.target.read_bytes(), self.target.stat().st_mtime_ns
        with mock.patch.object(es, "commit_session", side_effect=AssertionError("reconcile cannot write")):
            observed = self.reconcile(receipt)
        self.assertEqual(observed.status, "intended_visible_durability_unknown")
        self.assertEqual(observed.current, receipt.intended)
        self.assertFalse(observed.as_payload()["writes"])
        self.assertEqual((self.target.read_bytes(), self.target.stat().st_mtime_ns), before)
        self.assertEqual(list(self.workdir.glob(".*.tmp")), [])

    def test_reconcile_different_valid_file_never_grants_overwrite_or_retry(self):
        session = fixture_session("m68a")
        self.create(session)
        receipt = self.apply(first_input(session))
        next_batch = MEMOME["unit_tables"]()[1][1]
        self.apply(next_batch)
        before = self.target.read_bytes(), self.target.stat().st_mtime_ns
        with mock.patch.object(es, "commit_session", side_effect=AssertionError("no write")):
            observed = self.reconcile(receipt)
        self.assertEqual(observed.status, "different_valid_file")
        self.assertEqual(observed.current.generation, 3)
        self.assertEqual((self.target.read_bytes(), self.target.stat().st_mtime_ns), before)

    def test_reconcile_missing_invalid_and_unreadable_have_explicit_typed_observations(self):
        session = fixture_session("m68a")
        self.create(session)
        receipt = self.apply(first_input(session))
        for malformed in (b"{", b"\xff"):
            with self.subTest(malformed=malformed):
                self.target.write_bytes(malformed)
                observed = self.reconcile(receipt)
                self.assertEqual(observed.status, "unreadable_or_invalid")
                self.assertFalse(observed.missing)
                self.assertEqual(observed.error.error_type, "SessionError")
                self.assertEqual(self.target.read_bytes(), malformed)
        self.target.unlink()
        observed = self.reconcile(receipt)
        self.assertEqual(observed.status, "unreadable_or_invalid")
        self.assertTrue(observed.missing)
        self.assertEqual(observed.error.error_type, "FileNotFoundError")
        self.assertIsNone(observed.current)
        with mock.patch.object(es, "load_session", side_effect=PermissionError("denied")):
            observed = self.reconcile(receipt)
        self.assertFalse(observed.missing)
        self.assertEqual(observed.error.error_type, "PermissionError")

    def test_identity_comparison_uses_all_fields_and_rejects_malformed_declarations(self):
        session = fixture_session("m68a")
        self.create(session)
        receipt = self.apply(first_input(session))
        for changes in ({"session_digest": "0" * 64}, {"file_digest": "0" * 64}):
            with self.subTest(changes=changes):
                observed = operations.reconcile_operation(
                    self.target, transport=self.transport,
                    expectation=replace(receipt.expectation,
                                        intended=replace(receipt.intended, **changes)))
                self.assertEqual(observed.status, "different_valid_file")
        for changes in ({"generation": True}, {"turn": 1.0}, {"file_digest": "g" * 64},
                        {"session_digest": "0" * 63}, {"generation": 0}, {"turn": -1}):
            with self.subTest(invalid=changes), mock.patch.object(
                    es, "load_session", side_effect=AssertionError("reject before read")):
                with self.assertRaises(es.SessionError):
                    operations.reconcile_operation(
                        self.target, transport=self.transport,
                        expectation=replace(receipt.expectation,
                                            intended=replace(receipt.intended, **changes)))
        with self.assertRaises(es.SessionError):
            operations.identity_from_payload(dict(receipt.base.as_payload(), extra=1))

    def test_strict_submission_failures_remain_typed_and_preserve_bytes(self):
        self.create(fixture_session("m68a"))
        before = self.target.read_bytes(), self.target.stat().st_mtime_ns
        for body, error_type in ((b'{"turn":1,"turn":1,"proposals":[]}', es.TransportDomainError),
                                 (b'{"turn":1.0,"proposals":[]}', es.TransportDomainError),
                                 (b'{"turn":NaN,"proposals":[]}', es.TransportDomainError),
                                 (b'{"turn":true,"proposals":[]}', es.SessionError),
                                 (b"{}", es.SessionError), (b"\xff", es.SessionError),
                                 (b" " * (self.transport.max_bytes + 1), es.TransportDomainError)):
            with self.subTest(body=body[:40]):
                with mock.patch.object(es, "commit_session", side_effect=AssertionError("no commit")):
                    with self.assertRaises(error_type) as caught:
                        operations.apply_operation(self.target, transport=self.transport, submission=body)
                self.assertEqual(caught.exception.operation_receipt.status, "rejected")
                self.assertIsNotNone(caught.exception.operation_receipt.base)
                self.assertIsNone(caught.exception.operation_receipt.intended)
                self.assertEqual((self.target.read_bytes(), self.target.stat().st_mtime_ns), before)

    def test_derived_122_bit_receipt_fails_121_bit_domain_before_commit(self):
        policy = MEMOME["illustrative_policy"]()
        people = tuple(mm.Participant(name, "group", (1,) + (255,) * 7, 2 ** 120)
                       for name in ("a", "b"))
        session = es.create_memome_session(policy=policy, genesis_turn=0, participants=people)
        transport = replace(self.transport, max_int_bits=121)
        self.create(session, transport)
        before = self.target.read_bytes()
        batch = mm.Batch(1, (mm.Proposal("p", "a", 0, 1, 0),))
        self.assertEqual(advance(session, batch).ledger.history[0].receipts[0].electorate_weight.bit_length(), 122)
        with mock.patch.object(es, "commit_session", side_effect=AssertionError("no commit")):
            with self.assertRaises(es.TransportDomainError) as caught:
                self.apply(batch, transport)
        self.assertEqual(caught.exception.operation_receipt.status, "rejected")
        self.assertEqual(self.target.read_bytes(), before)

    def test_corrupt_and_resealed_content_fail_public_reconstruction(self):
        session = fixture_session("m60a")
        result = self.create(session)
        envelope = result.envelope
        latest = json.loads(envelope.latest)
        latest["state"]["soldiers"][0]["morale"] += 1
        altered = json_bytes(latest).decode("utf-8")
        combined = json_bytes({"genesis": envelope.genesis, "history": envelope.history,
                               "latest": altered})
        resealed = replace(envelope, latest=altered,
                           latest_digest=hashlib.sha256(altered.encode()).hexdigest(),
                           session_digest=hashlib.sha256(combined).hexdigest())
        for raw in (b"broken", es.encode_envelope_text(resealed, self.transport)):
            with self.subTest(raw=raw[:20]):
                self.target.write_bytes(raw)
                with mock.patch.object(es, "commit_session", side_effect=AssertionError("no commit")):
                    with self.assertRaises(es.SessionError) as caught:
                        self.apply(first_input(session))
                self.assertEqual(caught.exception.operation_receipt.status, "rejected")
                self.assertIsNone(caught.exception.operation_receipt.base)
                self.assertEqual(self.target.read_bytes(), raw)

    def test_unsupported_platform_preserves_type_base_and_intended_without_mutation(self):
        session = fixture_session("m68a")
        self.create(session)
        before = self.target.read_bytes()
        with mock.patch.object(es, "fcntl", None), self.assertRaises(es.UnsupportedPlatformError) as caught:
            self.apply(first_input(session))
        receipt = caught.exception.operation_receipt
        self.assertEqual(receipt.status, "rejected")
        self.assertEqual(receipt.error.error_type, "UnsupportedPlatformError")
        self.assertIsNotNone(receipt.intended)
        self.assertEqual(self.target.read_bytes(), before)

    def test_equal_bytes_at_distinct_targets_require_explicit_matching_path(self):
        session = fixture_session("m68a")
        self.create(session)
        receipt = self.apply(first_input(session))
        other = self.workdir / "other.json"
        other.write_bytes(self.target.read_bytes())
        self.assertEqual(es.load_session(other, transport=self.transport).digest,
                         receipt.intended.file_digest)
        with mock.patch.object(es, "load_session", side_effect=AssertionError("path mismatch before IO")):
            with self.assertRaises(es.SessionError):
                operations.reconcile_operation(other, transport=self.transport,
                                                expectation=receipt.expectation)
        # Only a new explicit target declaration can compare the other copy.
        observed = operations.reconcile_operation(
            other, transport=self.transport, expectation=replace(receipt.expectation, target=str(other)))
        self.assertEqual(observed.status, "intended_visible_durability_unknown")

    def test_same_payload_in_a_different_generation_never_matches_base(self):
        session = fixture_session("m68a")
        self.create(session)
        receipt = self.apply(first_input(session))
        current = es.load_session(self.target, transport=self.transport)
        es.commit_session(self.target, session, transport=self.transport,
                          expected_generation=current.generation, expected_digest=current.digest)
        observed = self.reconcile(receipt)
        self.assertEqual(observed.current.session_digest, receipt.base.session_digest)
        self.assertNotEqual(observed.current.file_digest, receipt.base.file_digest)
        self.assertEqual(observed.current.generation, 3)
        self.assertEqual(observed.status, "different_valid_file")

    def test_strict_expectation_relationships_transport_and_kernel_before_io(self):
        session = fixture_session("m68a")
        self.create(session)
        receipt = self.apply(first_input(session))
        expectation = receipt.expectation
        self.assertEqual(operations.expectation_from_payload(expectation.as_payload()), expectation)
        invalid = [replace(expectation, intended=replace(receipt.intended, generation=4)),
                   replace(expectation, intended=replace(receipt.intended, turn=4)),
                   replace(expectation, base=replace(receipt.base, generation=True)),
                   replace(expectation, base=replace(receipt.base, file_digest="A" * 64)),
                   replace(expectation, kernel="unknown"),
                   replace(expectation, kernel_contract="wrong"),
                   replace(expectation, transport=replace(self.transport, max_bytes=True)),
                   replace(expectation, target="")]
        with mock.patch.object(es, "load_session", side_effect=AssertionError("invalid expectation before IO")):
            for candidate in invalid:
                with self.subTest(candidate=candidate), self.assertRaises(es.SessionError):
                    operations.reconcile_operation(self.target, transport=self.transport, expectation=candidate)
            with self.assertRaises(es.ContractError):
                operations.reconcile_operation(
                    self.target, transport=replace(self.transport, max_bytes=self.transport.max_bytes + 1),
                    expectation=expectation)
            with self.assertRaises(es.SessionError):
                operations.expectation_from_payload(dict(expectation.as_payload(), extra=1))

    def test_candidate_from_another_loaded_genesis_is_rejected_before_commit(self):
        original = fixture_session("m60a")
        self.create(original)
        other = es.create_campaign_session(
            policy=original.policy, topology=original.topology, campaign_id="other-campaign",
            turn=original.admission.turn, staging=original.admission.staging,
            target=original.admission.target, soldiers=original.admission.soldiers,
            stocks=original.admission.stocks)
        other_target = self.workdir / "other.json"
        es.commit_session(other_target, other, transport=self.transport,
                          expected_generation=None, expected_digest=None)
        other_loaded = es.load_session(other_target, transport=self.transport)
        other_result = es.apply_campaign_tick(other_loaded.session, first_input(other))
        before = self.target.read_bytes()
        with mock.patch.object(es, "apply_campaign_tick", return_value=other_result), mock.patch.object(
                es, "commit_session", side_effect=AssertionError("candidate swap cannot commit")):
            with self.assertRaises(es.IntegrityError) as caught:
                self.apply(first_input(original))
        self.assertEqual(caught.exception.operation_receipt.status, "rejected")
        self.assertIsNone(caught.exception.operation_receipt.intended)
        self.assertEqual(self.target.read_bytes(), before)

    def test_replay_receipt_observes_base_even_if_a_later_writer_moves_current_file(self):
        initial = fixture_session("m68a")
        batches = MEMOME["unit_tables"]()[1]
        session = advance(initial, batches[0])
        self.create(session)
        loaded = es.load_session(self.target, transport=self.transport)
        original_apply = es.apply_memome_batch

        def replay_then_competing_write(observed, batch):
            result = original_apply(observed, batch)
            later = original_apply(observed, batches[1]).session
            es.commit_session(self.target, later, transport=self.transport,
                              expected_generation=loaded.generation, expected_digest=loaded.digest)
            return result

        with mock.patch.object(es, "apply_memome_batch", replay_then_competing_write):
            receipt = self.apply(batches[0])
        self.assertEqual((receipt.status, receipt.base.generation, receipt.base.turn),
                         ("replay_no_write", 1, 1))
        self.assertIsNone(receipt.intended)
        self.assertEqual(es.load_session(self.target, transport=self.transport).generation, 2)
        self.assertEqual(self.reconcile(receipt).status, "different_valid_file")

    def test_proven_postpublication_unlock_failure_is_durable_in_test_owned_process(self):
        session = fixture_session("m68a")
        self.create(session)
        transport_path = self.workdir / "transport.json"
        transport_path.write_bytes(json_bytes(self.transport.as_payload()))
        body_path = self.workdir / "batch.json"
        body_path.write_bytes(submission(first_input(session)))
        child = subprocess.run(
            [sys.executable, "-B", str(Path(__file__).resolve()), "--unlock-failure",
             str(self.target), str(transport_path), str(body_path)], capture_output=True, timeout=15)
        self.assertEqual(child.returncode, 0, child.stderr)
        payload = json.loads(child.stdout)
        self.assertEqual(payload["status"], "committed_durable")
        self.assertEqual(payload["error"]["error_type"], "CommittedCleanupError")
        self.assertIn("injected postpublication unlock failure", payload["error"]["detail"])
        expectation = operations.expectation_from_payload(payload["expectation"])
        before = self.target.read_bytes()
        observed = operations.reconcile_operation(self.target, transport=self.transport, expectation=expectation)
        self.assertEqual(observed.status, "intended_visible_durability_unknown")
        self.assertEqual(es.load_session(self.target, transport=self.transport).generation, 2)
        self.assertEqual(self.target.read_bytes(), before)
        self.assertEqual(list(self.workdir.glob(".*.tmp")), [])

    def test_ordinary_precommit_read_error_is_rejected_not_unknown(self):
        error = PermissionError("injected load denial")
        with mock.patch.object(es, "load_session", side_effect=error), mock.patch.object(
                es, "commit_session", side_effect=AssertionError("load failure cannot commit")):
            with self.assertRaises(PermissionError) as caught:
                operations.apply_operation(self.target, transport=self.transport, submission=b"{}")
        self.assertIs(caught.exception, error)
        self.assertEqual(error.operation_receipt.status, "rejected")
        self.assertIsNone(error.operation_receipt.expectation)

    def contenders(self, bodies):
        """Wait for both loaded-generation signals before releasing either process."""
        transport_path = self.workdir / "transport.json"
        transport_path.write_bytes(json_bytes(self.transport.as_payload()))
        processes = []
        ready = {}
        try:
            for index, body in enumerate(bodies):
                body_path = self.workdir / f"submission-{index}.json"
                body_path.write_bytes(body)
                process = subprocess.Popen(
                    [sys.executable, "-B", str(Path(__file__).resolve()), "--contender",
                     str(self.target), str(transport_path), str(body_path)],
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    text=True, start_new_session=True)
                processes.append(process)
            with selectors.DefaultSelector() as selector:
                for index, process in enumerate(processes):
                    selector.register(process.stdout, selectors.EVENT_READ, index)
                deadline = time.monotonic() + 15
                while len(ready) < len(processes):
                    remaining = deadline - time.monotonic()
                    self.assertGreater(remaining, 0, "contender load barrier timed out")
                    events = selector.select(remaining)
                    self.assertTrue(events, "contender load barrier timed out")
                    for key, _ in events:
                        line = key.fileobj.readline()
                        self.assertTrue(line, "contender exited before loaded barrier")
                        ready[key.data] = json.loads(line)["ready"]
                        selector.unregister(key.fileobj)
            self.assertEqual(ready[0], ready[1])
            for process in processes:
                process.stdin.write("release\n")
                process.stdin.flush()
            receipts = []
            for process in processes:
                output, errors = process.communicate(timeout=15)
                self.assertEqual(process.returncode, 0, errors)
                receipts.append(json.loads(output))
            return receipts
        finally:
            # Only the two test-owned child processes are terminated on failure.
            for process in processes:
                if process.poll() is None:
                    process.kill()
                process.communicate(timeout=5)

    def test_two_real_processes_different_valid_batches_have_one_winner_and_one_stale(self):
        session = fixture_session("m68a")
        self.create(session)
        first = first_input(session)
        alternate = replace(first, proposals=(replace(first.proposals[0], draw=200),) + first.proposals[1:])
        expected = [advance(session, batch) for batch in (first, alternate)]
        self.assertNotEqual(expected[0], expected[1])
        receipts = self.contenders([submission(first), submission(alternate)])
        self.assertEqual(sorted(receipt["status"] for receipt in receipts),
                         ["committed_durable", "stale_conflict"])
        winner = next(index for index, receipt in enumerate(receipts)
                      if receipt["status"] == "committed_durable")
        loaded = es.load_session(self.target, transport=self.transport)
        self.assertEqual((loaded.generation, loaded.turn), (2, 1))
        self.assertEqual(loaded.session, expected[winner])
        self.assertEqual(loaded.digest, receipts[winner]["intended"]["file_digest"])
        self.assertEqual(receipts[1 - winner]["error"]["error_type"], "StaleGenerationError")
        self.assertEqual(list(self.workdir.glob(".*.tmp")), [])

    def test_identical_real_contenders_stay_stale_then_explicit_fresh_replay_writes_nothing(self):
        session = fixture_session("m68a")
        self.create(session)
        record = first_input(session)
        receipts = self.contenders([submission(record), submission(record)])
        self.assertEqual(sorted(receipt["status"] for receipt in receipts),
                         ["committed_durable", "stale_conflict"])
        self.assertEqual(receipts[0]["intended"], receipts[1]["intended"])
        before = self.target.read_bytes(), self.target.stat().st_mtime_ns
        with mock.patch.object(es, "commit_session", side_effect=AssertionError("fresh replay no write")):
            replay = self.apply(record)
        self.assertEqual((replay.status, replay.base.generation, replay.base.turn),
                         ("replay_no_write", 2, 1))
        self.assertIsNone(replay.intended)
        self.assertEqual((self.target.read_bytes(), self.target.stat().st_mtime_ns), before)


class SessionOperationCliTests(_SessionCase):
    def cli(self, args, seed="0"):
        return subprocess.run([sys.executable, "-B", str(DRIVER), *args], cwd=ROOT,
                              env=dict(os.environ, PYTHONHASHSEED=seed),
                              capture_output=True, timeout=15)

    def test_disabled_even_with_supplied_nonexistent_paths_opens_nothing(self):
        driver = runpy.run_path(str(DRIVER))
        output = io.StringIO()
        with ExitStack() as stack:
            stack.enter_context(redirect_stdout(output))
            for owner, name in ((Path, "open"), (es, "load_session"),
                                (es, "commit_session"), (es, "submission_from_bytes"),
                                (es, "apply_campaign_tick"), (es, "apply_memome_batch")):
                stack.enter_context(mock.patch.object(owner, name, side_effect=AssertionError("disabled side effect")))
            self.assertEqual(driver["main"](["apply", "--path", "missing",
                                              "--transport", "missing", "--submission", "missing"]), 0)
        disabled = json.loads(output.getvalue())
        self.assertEqual(disabled["status"], "disabled")
        self.assertFalse(disabled["reads_files"])
        self.assertFalse(disabled["calls_kernels"])
        self.assertEqual(list(self.workdir.iterdir()), [])
        self.assertEqual(self.cli([]).stdout, self.cli(["apply", "--path", "missing"], "42").stdout)

    def test_enabled_cli_and_reconcile_are_deterministic_across_fresh_hash_seeds(self):
        session = fixture_session("m68a")
        self.create(session)
        base_bytes = self.target.read_bytes()
        transport_path = self.workdir / "transport.json"
        transport_path.write_bytes(json_bytes(self.transport.as_payload()))
        body_path = self.workdir / "batch.json"
        body_path.write_bytes(submission(first_input(session)))
        args = ["--enable", "apply", "--path", str(self.target), "--transport",
                str(transport_path), "--submission", str(body_path)]
        outputs = []
        for seed in ("0", "42"):
            self.target.write_bytes(base_bytes)
            result = self.cli(args, seed)
            self.assertEqual(result.returncode, 0, result.stderr)
            outputs.append(result.stdout)
        self.assertEqual(outputs[0], outputs[1])
        receipt = json.loads(outputs[0])
        self.assertEqual(receipt["status"], "committed_durable")
        reconcile_args = ["--enable", "reconcile", "--path", str(self.target),
                          "--transport", str(transport_path), "--expectation-json",
                          json.dumps(receipt["expectation"])]
        before = self.target.read_bytes(), self.target.stat().st_mtime_ns
        first = self.cli(reconcile_args)
        second = self.cli(reconcile_args, "42")
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(first.stdout, second.stdout)
        self.assertEqual(json.loads(first.stdout)["status"], "intended_visible_durability_unknown")
        self.assertEqual((self.target.read_bytes(), self.target.stat().st_mtime_ns), before)

    def test_cli_strict_failure_is_json_stderr_exit3_with_no_destination_change(self):
        session = fixture_session("m68a")
        self.create(session)
        transport_path = self.workdir / "transport.json"
        transport_path.write_bytes(json_bytes(self.transport.as_payload()))
        body_path = self.workdir / "batch.json"
        body_path.write_bytes(b'{"turn":1,"turn":1,"proposals":[]}')
        before = self.target.read_bytes()
        result = self.cli(["--enable", "apply", "--path", str(self.target),
                           "--transport", str(transport_path), "--submission", str(body_path)])
        self.assertEqual(result.returncode, 3)
        self.assertEqual(result.stdout, b"")
        receipt = json.loads(result.stderr)
        self.assertEqual(receipt["status"], "rejected")
        self.assertEqual(receipt["error"]["error_type"], "TransportDomainError")
        self.assertIsNotNone(receipt["base"])
        self.assertEqual(self.target.read_bytes(), before)

    def test_cli_file_read_request_uses_limit_plus_one_without_metadata_trust(self):
        driver = runpy.run_path(str(DRIVER))
        path = self.workdir / "input.json"
        path.write_bytes(b"x" * 65)
        original_open = Path.open
        requests = []
        handles = []

        class Tracking:
            def __enter__(self):
                self.handle = original_open(path, "rb")
                handles.append(self.handle)
                return self

            def __exit__(self, *args):
                self.handle.close()

            def read(self, size):
                requests.append(size)
                return self.handle.read(size)

        with mock.patch.object(Path, "open", return_value=Tracking()), mock.patch.object(
                Path, "stat", side_effect=AssertionError("no metadata-only bound")):
            with self.assertRaises(es.TransportDomainError):
                driver["_read_bounded"](str(path), 64, "test")
        self.assertEqual(requests, [65])
        self.assertTrue(all(handle.closed for handle in handles))

    def test_oversize_policy_and_submission_files_fail_before_decoder_or_commit(self):
        driver = runpy.run_path(str(DRIVER))
        transport_path = self.workdir / "transport.json"
        body_path = self.workdir / "submission.json"
        transport_path.write_bytes(b"x" * 4097)
        args = ["--enable", "apply", "--path", str(self.target), "--transport",
                str(transport_path), "--submission", str(body_path)]
        with redirect_stderr(io.StringIO()), mock.patch.object(
                es, "transport_policy_from_text", side_effect=AssertionError("oversize policy cannot decode")):
            self.assertEqual(driver["main"](args), 3)
        transport = replace(self.transport, max_bytes=64)
        transport_path.write_bytes(json_bytes(transport.as_payload()))
        body_path.write_bytes(b"x" * 65)
        with redirect_stderr(io.StringIO()), mock.patch.object(
                operations, "apply_operation", side_effect=AssertionError("oversize submission cannot apply")):
            self.assertEqual(driver["main"](args), 3)
        self.assertFalse(self.target.exists())
        self.assertFalse((self.workdir / ".session.json.lock").exists())

    def test_stdout_failure_after_durable_commit_never_reports_safe_rejection(self):
        driver = runpy.run_path(str(DRIVER))
        session = fixture_session("m68a")
        self.create(session)
        transport_path = self.workdir / "transport.json"
        transport_path.write_bytes(json_bytes(self.transport.as_payload()))
        body_path = self.workdir / "batch.json"
        body_path.write_bytes(submission(first_input(session)))
        args = ["--enable", "apply", "--path", str(self.target), "--transport",
                str(transport_path), "--submission", str(body_path)]

        class BrokenOutput:
            def write(self, _text):
                raise BrokenPipeError("injected output failure")

        errors = io.StringIO()
        with redirect_stdout(BrokenOutput()), redirect_stderr(errors), mock.patch.object(
                es, "commit_session", wraps=es.commit_session) as commit:
            self.assertEqual(driver["main"](args), 3)
        payload = json.loads(errors.getvalue())
        self.assertEqual(payload["status"], "output_delivery_failed")
        self.assertEqual(payload["operation_receipt"]["status"], "committed_durable")
        self.assertEqual(commit.call_count, 1)
        loaded = es.load_session(self.target, transport=self.transport)
        self.assertEqual(loaded.generation, 2)
        self.assertEqual(loaded.digest, payload["operation_receipt"]["intended"]["file_digest"])

    def test_durable_receipt_need_not_describe_current_head_when_rendered(self):
        driver = runpy.run_path(str(DRIVER))
        initial = fixture_session("m68a")
        self.create(initial)
        batches = MEMOME["unit_tables"]()[1]
        transport_path = self.workdir / "transport.json"
        transport_path.write_bytes(json_bytes(self.transport.as_payload()))
        body_path = self.workdir / "batch.json"
        body_path.write_bytes(submission(batches[0]))
        original_emit = driver["_emit"]

        def later_commit_before_render(payload, *, error=False):
            self.assertEqual(payload["status"], "committed_durable")
            operations.apply_operation(self.target, transport=self.transport, submission=submission(batches[1]))
            original_emit(payload, error=error)

        output = io.StringIO()
        with redirect_stdout(output), mock.patch.dict(driver["main"].__globals__, {"_emit": later_commit_before_render}):
            result = driver["main"](["--enable", "apply", "--path", str(self.target),
                                      "--transport", str(transport_path), "--submission", str(body_path)])
        self.assertEqual(result, 0)
        receipt = json.loads(output.getvalue())
        self.assertEqual((receipt["status"], receipt["intended"]["generation"]), ("committed_durable", 2))
        current = es.load_session(self.target, transport=self.transport)
        self.assertEqual((current.generation, current.turn), (3, 2))
        self.assertNotEqual(current.digest, receipt["intended"]["file_digest"])

    def test_import_and_disabled_driver_have_no_production_native_or_fixture_execution(self):
        code = (
            "import sys, runpy\n"
            "from pathlib import Path\n"
            "from chronicler import session_operations as operations\n"
            "from chronicler import experiment_sessions as es\n"
            "def forbidden(*args, **kwargs): raise AssertionError('unexpected runtime call')\n"
            "es.load_session = es.commit_session = es.create_campaign_session = forbidden\n"
            "es.create_memome_session = es.apply_campaign_tick = es.apply_memome_batch = forbidden\n"
            "driver = runpy.run_path(sys.argv[1])\n"
            "driver['main']([])\n"
            "assert not any(name.startswith(('chronicler_agents', 'chronicler.simulation', "
            "'chronicler.agent_bridge', 'chronicler.main', 'chronicler.models')) for name in sys.modules)\n")
        result = subprocess.run([sys.executable, "-B", "-c", code, str(DRIVER)],
                                capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"], "disabled")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--contender":
        contender(*sys.argv[2:])
    elif len(sys.argv) > 1 and sys.argv[1] == "--unlock-failure":
        unlock_failure(*sys.argv[2:])
    else:
        unittest.main()
