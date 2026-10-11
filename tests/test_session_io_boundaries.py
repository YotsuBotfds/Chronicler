"""Descriptor races and explicit durable-publication cleanup outcomes; offline only."""
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
import builtins
import io
import json
import os
from pathlib import Path
import runpy
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from chronicler import experiment_sessions as es
from chronicler import session_operations as operations
from test_session_read_bounds import TrackedHandle, exact_limit_file, fixture_session
from test_session_operations import first_input, submission

ROOT = Path(__file__).resolve().parents[1]
DRIVER = runpy.run_path(str(ROOT / "scripts" / "experiment_session.py"))


class SessionIOBoundaryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.folder = Path(temporary.name)
        self.target = self.folder / "session.json"
        self.transport = es.documented_transport_policy()
        self.session = fixture_session("m68a")

    def commit(self):
        return es.commit_session(self.target, self.session, transport=self.transport,
                                 expected_generation=None, expected_digest=None)

    def assert_completed(self, error):
        loaded = es.load_session(self.target, transport=self.transport)
        self.assertEqual((error.result.path, error.result.generation, error.result.turn,
                          error.result.digest, error.result.envelope.session_digest),
                         (str(self.target), loaded.generation, loaded.turn, loaded.digest,
                          loaded.envelope.session_digest))
        self.assertIs(error.__cause__, error.cleanup_error)
        self.assertNotIsInstance(error, es.PersistenceError)
        self.assertIn("committed durably", str(error))
        self.assertIn("read the file back", str(error))
        self.assertIn("do not automatically retry", str(error))
        self.assertEqual(list(self.folder.glob(".*.tmp")), [])
        return loaded

    def test_cli_ignores_stale_path_size_and_refuses_oversized_bytes(self):
        self.target.write_bytes(b"{}")
        stale = self.target.stat()
        self.target.write_bytes(b"x" * 128)
        with mock.patch.object(Path, "stat", return_value=stale):
            with self.assertRaises(es.TransportDomainError):
                DRIVER["_read_bounded"](str(self.target), 16, "submission")

    def test_cli_growth_after_descriptor_type_check_uses_actual_bounded_read(self):
        self.target.write_bytes(b"{}")
        original = builtins.open
        requests, handles = [], []

        def opened(descriptor, mode, *args, **kwargs):
            handle = original(descriptor, mode, *args, **kwargs)
            if type(descriptor) is not int or mode != "rb":
                return handle
            handles.append(handle)

            def grow():
                with self.target.open("ab") as writer:
                    writer.write(b"x" * 128)

            return TrackedHandle(handle, requests, grow)

        with mock.patch.object(builtins, "open", opened), mock.patch.object(
                Path, "read_bytes", side_effect=AssertionError("unbounded read")):
            with self.assertRaises(es.TransportDomainError):
                DRIVER["_read_bounded"](str(self.target), 16, "submission")
        self.assertEqual([size for _, size in requests], [17])
        self.assertTrue(all(handle.closed for handle in handles))
        self.assertEqual(self.target.read_bytes(), b"{}" + b"x" * 128)

    def test_session_descriptor_survives_path_substitution_after_open(self):
        policy, raw, _ = exact_limit_file(self.session)
        self.target.write_bytes(raw)
        original = os.open
        displaced = self.folder / "displaced.json"

        def substituted(path, *args, **kwargs):
            descriptor = original(path, *args, **kwargs)
            if Path(path) == self.target:
                self.target.rename(displaced)
                os.mkfifo(self.target)
            return descriptor

        with mock.patch.object(os, "open", substituted):
            loaded = es.load_session(self.target, transport=policy)
        self.assertEqual(loaded.generation, 1)
        self.assertEqual(displaced.read_bytes(), raw)
        self.assertTrue(stat.S_ISFIFO(self.target.stat().st_mode))

    def test_fifo_and_regular_to_fifo_open_race_are_refused_in_bounded_children(self):
        for mode in ("session", "cli", "public"):
            for substitute in (False, True):
                with self.subTest(mode=mode, substitute=substitute):
                    self.target.unlink(missing_ok=True)
                    if substitute:
                        self.target.write_bytes(b"{}")
                    else:
                        os.mkfifo(self.target)
                    child = subprocess.run(
                        [sys.executable, "-B", str(Path(__file__).resolve()), "--fifo",
                         str(self.target), mode, str(int(substitute))],
                        capture_output=True, timeout=3)
                    self.assertEqual(child.returncode, 0, child.stderr)
                    self.assertIn(b"SessionError", child.stdout)

    def test_nonregular_device_is_refused_and_read_symlink_behavior_is_preserved(self):
        with self.assertRaisesRegex(es.SessionError, "regular file"):
            es.read_regular_file_bytes("/dev/null", max_bytes=64, label="submission")
        policy, raw, _ = exact_limit_file(self.session)
        self.target.write_bytes(raw)
        link = self.folder / "link.json"
        link.symlink_to(self.target)
        self.assertEqual(es.load_session(link, transport=policy).generation, 1)

    def test_public_reader_rejects_nonexact_limits_before_open(self):
        for value in (True, 1.0, "16", 0, -1, es.MAX_TRANSPORT_BYTES + 1):
            with self.subTest(value=value), mock.patch.object(
                    os, "open", side_effect=AssertionError("invalid limit must not open")):
                with self.assertRaises(es.SessionError):
                    es.read_regular_file_bytes(self.target, max_bytes=value, label="submission")

    def test_cli_growth_refuses_before_utf8_or_submission_decode(self):
        self.target.write_bytes(b"\xff" * 65)
        transport = replace(self.transport, max_bytes=64)
        with mock.patch.object(es, "submission_from_bytes", side_effect=AssertionError("decode")):
            with self.assertRaises(es.TransportDomainError):
                DRIVER["_submission"](str(self.target), transport, "submission")

    def test_unlock_failure_reports_completed_identity_and_original_cause(self):
        original = es.fcntl.flock
        failure = OSError("injected unlock failure")
        descriptors = []

        def failed_unlock(descriptor, operation):
            if operation == es.fcntl.LOCK_UN:
                raise failure
            descriptors.append(descriptor)
            return original(descriptor, operation)

        with mock.patch.object(es.fcntl, "flock", failed_unlock):
            with self.assertRaises(es.CommittedCleanupError) as caught:
                self.commit()
        self.assert_completed(caught.exception)
        self.assertIs(caught.exception.cleanup_error, failure)
        for descriptor in descriptors:
            with self.assertRaises(OSError):
                os.fstat(descriptor)

    def test_successful_directory_fsync_then_close_failure_is_known_durable(self):
        original = os.close
        failure = OSError("injected directory close failure")

        def failed_close(descriptor):
            directory = stat.S_ISDIR(os.fstat(descriptor).st_mode)
            original(descriptor)
            if directory:
                raise failure

        with mock.patch.object(os, "close", failed_close):
            with self.assertRaises(es.CommittedCleanupError) as caught:
                self.commit()
        self.assert_completed(caught.exception)
        self.assertIs(caught.exception.cleanup_error, failure)

    def test_writer_close_failure_after_publication_is_known_durable(self):
        original_close, original_flock = os.close, es.fcntl.flock
        locks = set()
        failure = OSError("injected writer close failure")

        def tracked_lock(descriptor, operation):
            if operation == es.fcntl.LOCK_EX:
                locks.add(descriptor)
            return original_flock(descriptor, operation)

        def failed_close(descriptor):
            original_close(descriptor)
            if descriptor in locks:
                raise failure

        with mock.patch.object(os, "close", failed_close), mock.patch.object(
                es.fcntl, "flock", tracked_lock):
            with self.assertRaises(es.CommittedCleanupError) as caught:
                self.commit()
        self.assert_completed(caught.exception)
        self.assertIs(caught.exception.cleanup_error, failure)

    def test_fsync_uncertainty_is_not_masked_by_directory_close_and_unlock_failures(self):
        original_fsync, original_close, original_flock = os.fsync, os.close, es.fcntl.flock
        failure = OSError("injected actual directory fsync failure")

        def failed_fsync(descriptor):
            if stat.S_ISDIR(os.fstat(descriptor).st_mode):
                raise failure
            return original_fsync(descriptor)

        def failed_close(descriptor):
            directory = stat.S_ISDIR(os.fstat(descriptor).st_mode)
            original_close(descriptor)
            if directory:
                raise OSError("secondary directory close")

        def failed_unlock(descriptor, operation):
            if operation == es.fcntl.LOCK_UN:
                raise OSError("secondary unlock")
            return original_flock(descriptor, operation)

        with mock.patch.object(os, "fsync", failed_fsync), mock.patch.object(
                os, "close", failed_close), mock.patch.object(es.fcntl, "flock", failed_unlock):
            with self.assertRaises(es.DurabilityUncertain) as caught:
                self.commit()
        self.assertIs(caught.exception.__cause__, failure)
        self.assertIn("secondary directory close", " ".join(failure.__notes__))
        self.assertIn("secondary unlock", " ".join(caught.exception.__notes__))
        self.assertEqual(es.load_session(self.target, transport=self.transport).generation, 1)
        self.assertFalse(hasattr(caught.exception, "result"))

    def test_prepublication_error_remains_primary_when_unlock_also_fails(self):
        original = es.fcntl.flock
        failure = es.SessionError("injected checkpoint rejection")

        def failed_unlock(descriptor, operation):
            if operation == es.fcntl.LOCK_UN:
                raise OSError("secondary unlock")
            return original(descriptor, operation)

        with mock.patch.object(es, "encode_session", side_effect=failure), mock.patch.object(
                es.fcntl, "flock", failed_unlock):
            with self.assertRaises(es.SessionError) as caught:
                self.commit()
        self.assertIs(caught.exception, failure)
        self.assertIn("secondary unlock", " ".join(failure.__notes__))
        self.assertFalse(self.target.exists())

    def test_primary_fsync_and_both_writer_cleanup_diagnostics_survive(self):
        self.commit()
        original_fsync, original_close, original_flock = os.fsync, os.close, es.fcntl.flock
        failure = OSError("primary directory fsync failure")
        locks = set()

        def failed_fsync(descriptor):
            if stat.S_ISDIR(os.fstat(descriptor).st_mode):
                raise failure
            return original_fsync(descriptor)

        def tracked_lock(descriptor, operation):
            if operation == es.fcntl.LOCK_EX:
                locks.add(descriptor)
            if operation == es.fcntl.LOCK_UN:
                raise OSError("secondary writer unlock failure")
            return original_flock(descriptor, operation)

        def failed_close(descriptor):
            original_close(descriptor)
            if descriptor in locks:
                raise OSError("secondary writer close failure")

        with mock.patch.object(os, "fsync", failed_fsync), mock.patch.object(
                os, "close", failed_close), mock.patch.object(es.fcntl, "flock", tracked_lock):
            with self.assertRaises(es.DurabilityUncertain) as caught:
                operations.apply_operation(self.target, transport=self.transport,
                                           submission=submission(first_input(self.session)))
        error = caught.exception
        self.assertIs(type(error), es.DurabilityUncertain)
        self.assertIs(error.__cause__, failure)
        self.assertIs(type(error.__cause__), OSError)
        self.assertIn("writer lock cleanup also failed", " ".join(error.__notes__))
        self.assertIn("secondary writer unlock failure", " ".join(error.__notes__))
        self.assertIn("secondary writer close failure", " ".join(error.__notes__))
        self.assertFalse(hasattr(error, "result"))
        receipt = error.operation_receipt
        self.assertEqual(receipt.status, "durability_uncertain")
        before = self.target.read_bytes()
        loaded = es.load_session(self.target, transport=self.transport)
        self.assertEqual(loaded.generation, 2)
        self.assertEqual(loaded.digest, receipt.intended.file_digest)
        reconciled = operations.reconcile_operation(
            self.target, transport=self.transport, expectation=receipt.expectation)
        self.assertEqual(reconciled.status, "intended_visible_durability_unknown")
        self.assertEqual(self.target.read_bytes(), before)
        self.assertEqual(list(self.folder.glob(".*.tmp")), [])
        for descriptor in locks:
            with self.assertRaises(OSError):
                os.fstat(descriptor)

    def test_prepublication_primary_and_both_writer_cleanup_diagnostics_survive(self):
        first = self.commit()
        before = self.target.read_bytes()
        advanced = es.apply_memome_batch(self.session, first_input(self.session)).session
        original_close, original_flock = os.close, es.fcntl.flock
        failure = es.SessionError("primary checkpoint rejection")
        original_cause = OSError("original checkpoint rejection cause")
        failure.__cause__ = original_cause
        locks = set()

        def tracked_lock(descriptor, operation):
            if operation == es.fcntl.LOCK_EX:
                locks.add(descriptor)
            if operation == es.fcntl.LOCK_UN:
                raise OSError("secondary writer unlock failure")
            return original_flock(descriptor, operation)

        def failed_close(descriptor):
            original_close(descriptor)
            if descriptor in locks:
                raise OSError("secondary writer close failure")

        with mock.patch.object(es, "encode_session", side_effect=failure), mock.patch.object(
                os, "close", failed_close), mock.patch.object(es.fcntl, "flock", tracked_lock):
            with self.assertRaises(es.SessionError) as caught:
                es.commit_session(self.target, advanced, transport=self.transport,
                                  expected_generation=first.generation, expected_digest=first.digest)
        self.assertIs(caught.exception, failure)
        self.assertIs(type(caught.exception), es.SessionError)
        self.assertIs(caught.exception.__cause__, original_cause)
        self.assertIn("writer lock cleanup also failed", " ".join(failure.__notes__))
        self.assertIn("secondary writer unlock failure", " ".join(failure.__notes__))
        self.assertIn("secondary writer close failure", " ".join(failure.__notes__))
        self.assertFalse(hasattr(failure, "result"))
        self.assertEqual(self.target.read_bytes(), before)
        self.assertEqual(es.load_session(self.target, transport=self.transport).generation, 1)
        self.assertEqual(list(self.folder.glob(".*.tmp")), [])
        for descriptor in locks:
            with self.assertRaises(OSError):
                os.fstat(descriptor)

    def test_unexpected_postpublication_exception_retains_unknown_operation_receipt(self):
        self.commit()
        original = es.commit_session
        failure = RuntimeError("unexpected failure after completed write")

        def unexpected(*args, **kwargs):
            original(*args, **kwargs)
            raise failure

        with mock.patch.object(es, "commit_session", unexpected):
            with self.assertRaises(RuntimeError) as caught:
                operations.apply_operation(self.target, transport=self.transport,
                                           submission=submission(first_input(self.session)))
        self.assertIs(caught.exception, failure)
        receipt = failure.operation_receipt
        self.assertEqual(receipt.status, "commit_outcome_unknown")
        self.assertEqual(receipt.error.error_type, "RuntimeError")
        loaded = es.load_session(self.target, transport=self.transport)
        self.assertEqual((loaded.generation, loaded.digest),
                         (receipt.intended.generation, receipt.intended.file_digest))

    def test_completed_metadata_must_match_operation_intended_identity(self):
        original = es.commit_session
        for changed_field in ("digest", "kernel_contract"):
            with self.subTest(changed_field=changed_field):
                self.target.unlink(missing_ok=True)
                self.commit()

                def wrong_metadata(*args, **kwargs):
                    result = original(*args, **kwargs)
                    if changed_field == "digest":
                        result = replace(result, digest="0" * 64)
                    else:
                        result = replace(result, envelope=replace(
                            result.envelope, kernel_contract="foreign-kernel-contract"))
                    error = OSError("injected cleanup")
                    raise es.CommittedCleanupError(result, error) from error

                with mock.patch.object(es, "commit_session", wrong_metadata):
                    with self.assertRaises(es.CommittedCleanupError) as caught:
                        operations.apply_operation(self.target, transport=self.transport,
                                                   submission=submission(first_input(self.session)))
                self.assertEqual(caught.exception.operation_receipt.status, "commit_outcome_unknown")
                self.assertIn("differs", " ".join(caught.exception.__notes__))
                self.assertEqual(es.load_session(self.target, transport=self.transport).generation, 2)
                if changed_field == "kernel_contract":
                    self.assertEqual(caught.exception.result.digest,
                                     caught.exception.operation_receipt.intended.file_digest)

    def test_cli_known_durable_cleanup_emits_identity_and_diagnostics(self):
        policy_path = self.folder / "transport.json"
        policy_path.write_text(json.dumps(self.transport.as_payload()))
        original = es.fcntl.flock

        def failed_unlock(descriptor, operation):
            if operation == es.fcntl.LOCK_UN:
                raise OSError("CLI cleanup failure")
            return original(descriptor, operation)

        output, diagnostics = io.StringIO(), io.StringIO()
        with mock.patch.object(es.fcntl, "flock", failed_unlock), redirect_stdout(
                output), redirect_stderr(diagnostics):
            status = DRIVER["main"](["create", "--kernel", "m68a", "--path", str(self.target),
                                      "--transport", str(policy_path), "--demo"])
        self.assertEqual(status, 3)
        payload, error = json.loads(output.getvalue()), json.loads(diagnostics.getvalue())
        self.assertTrue(payload["committed"])
        self.assertEqual(payload["status"], "committed_durable")
        self.assertEqual(error["error"], "CommittedCleanupError")
        self.assertEqual(error["cleanup_error"], "OSError")
        self.assertEqual(error["cleanup_detail"], "CLI cleanup failure")
        loaded = es.load_session(self.target, transport=self.transport)
        self.assertEqual((payload["generation"], payload["turn"], payload["digest"],
                          payload["session_digest"]),
                         (loaded.generation, loaded.turn, loaded.digest, loaded.envelope.session_digest))


def fifo_child(path, mode, substitute):
    original = os.open

    def opening(target, *args, **kwargs):
        if substitute and Path(target) == Path(path):
            Path(path).unlink()
            os.mkfifo(path)
        return original(target, *args, **kwargs)

    with mock.patch.object(os, "open", opening):
        try:
            if mode == "session":
                es.load_session(path, transport=es.documented_transport_policy())
            elif mode == "cli":
                DRIVER["_read_bounded"](path, 16, "submission")
            else:
                es.read_regular_file_bytes(path, max_bytes=16, label="submission")
        except es.SessionError as error:
            print(type(error).__name__)
            return 0
    return 1


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--fifo":
        raise SystemExit(fifo_child(sys.argv[2], sys.argv[3], bool(int(sys.argv[4]))))
    unittest.main()
