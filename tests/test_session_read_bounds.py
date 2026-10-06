"""Offline file-bound gates using the existing detached demo tables only."""

from contextlib import ExitStack
from dataclasses import replace
import hashlib
import os
from pathlib import Path
import runpy
import tempfile
import unittest
from unittest import mock

from chronicler import experiment_sessions as es


ROOT = Path(__file__).resolve().parents[1]
CAMPAIGN = runpy.run_path(str(ROOT / "scripts" / "campaign_logistics_demo.py"))
MEMOME = runpy.run_path(str(ROOT / "scripts" / "memome_demo.py"))


def fixture_session(kernel):
    if kernel == "m60a":
        policy = CAMPAIGN["illustrative_policy"]()
        topology = CAMPAIGN["fixture_topology"]()
        state = CAMPAIGN["fixture_session"](policy, topology).state
        return es.create_campaign_session(
            policy=policy, topology=topology, campaign_id=state.campaign_id,
            turn=state.admission_turn, staging=state.staging, target=state.target,
            soldiers=state.soldiers, stocks=state.stocks)
    people, _ = MEMOME["unit_tables"]()
    return es.create_memome_session(
        policy=MEMOME["illustrative_policy"](), genesis_turn=0, participants=people)


def exact_limit_file(session):
    """Find a policy whose canonical envelope occupies its complete byte budget."""
    policy = replace(es.documented_transport_policy(), max_bytes=65536)
    for _ in range(8):
        envelope = es.encode_session(session, transport=policy, generation=1)
        raw = es.encode_envelope_text(envelope, policy)
        if len(raw) == policy.max_bytes:
            return policy, raw, envelope
        policy = replace(policy, max_bytes=len(raw))
    raise AssertionError("fixture envelope byte budget did not stabilize")


class TrackedHandle:
    """Wrap an actual opened file, recording requests without replacing its data."""

    def __init__(self, handle, requests, before_read=None):
        self.handle = handle
        self.requests = requests
        self.before_read = before_read

    def __enter__(self):
        self.handle.__enter__()
        return self

    def __exit__(self, *args):
        return self.handle.__exit__(*args)

    def read(self, size=-1):
        self.requests.append((self.handle.fileno(), size))
        if self.before_read is not None:
            self.before_read()
        return self.handle.read(size)


class SessionReadBoundsTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.workdir = Path(temporary.name)
        self.target = self.workdir / "session.json"
        self.session = fixture_session("m68a")

    def invoke(self, operation, policy, raw, *, generation=1, digest=None):
        if operation == "load":
            return es.load_session(self.target, transport=policy)
        return es.commit_session(
            self.target, self.session, transport=policy,
            expected_generation=generation,
            expected_digest=hashlib.sha256(raw).hexdigest() if digest is None else digest)

    def track_open(self, requests, handles, before_read=None):
        original = Path.open

        def opened(path, mode="r", *args, **kwargs):
            handle = original(path, mode, *args, **kwargs)
            if path == self.target and mode == "rb":
                handles.append(handle)
                return TrackedHandle(handle, requests, before_read)
            return handle

        return mock.patch.object(Path, "open", opened)

    def forbid_decode(self, stack):
        for name in ("decode_envelope_text", "_strict_loads", "decode_envelope"):
            stack.enter_context(mock.patch.object(
                es, name, side_effect=AssertionError(f"unexpected decoder: {name}")))

    def test_exact_limit_preserves_canonical_bytes_and_digests_for_both_kernels(self):
        for kernel in ("m60a", "m68a"):
            with self.subTest(kernel=kernel):
                session = fixture_session(kernel)
                policy, raw, envelope = exact_limit_file(session)
                self.target.write_bytes(raw)
                before = sorted(self.workdir.iterdir())
                requests, handles = [], []
                with self.track_open(requests, handles), mock.patch.object(
                        Path, "read_bytes", side_effect=AssertionError("unbounded read")):
                    loaded = es.load_session(self.target, transport=policy)
                self.assertEqual([size for _, size in requests], [policy.max_bytes + 1])
                self.assertTrue(all(handle.closed for handle in handles))
                self.assertEqual(loaded.session, session)
                self.assertEqual(loaded.envelope, envelope)
                self.assertEqual(loaded.digest, hashlib.sha256(raw).hexdigest())
                self.assertEqual(es.session_digest(loaded.session, policy),
                                 envelope.session_digest)
                self.assertEqual(es.encode_envelope_text(loaded.envelope, policy), raw)
                self.assertEqual(self.target.read_bytes(), raw)
                self.assertEqual(sorted(self.workdir.iterdir()), before)

    def test_one_excess_byte_is_refused_before_decoding_on_both_paths(self):
        policy = replace(es.documented_transport_policy(), max_bytes=64)
        # An over-wide decimal literal must never get as far as JSON parsing.
        raw = b'{"generation":' + b"9" * (policy.max_bytes + 1 - 14)
        self.assertEqual(len(raw), policy.max_bytes + 1)
        for operation in ("load", "commit"):
            with self.subTest(operation=operation):
                self.target.write_bytes(raw)
                requests, handles = [], []
                with ExitStack() as stack:
                    self.forbid_decode(stack)
                    stack.enter_context(self.track_open(requests, handles))
                    stack.enter_context(mock.patch.object(
                        Path, "read_bytes", side_effect=AssertionError("unbounded read")))
                    with self.assertRaisesRegex(es.TransportDomainError, "64-byte"):
                        self.invoke(operation, policy, raw)
                self.assertEqual([size for _, size in requests], [65])
                self.assertTrue(all(handle.closed for handle in handles))
                self.assertEqual(self.target.read_bytes(), raw)
                expected_names = [self.target.name]
                if operation == "commit":
                    expected_names.append(".session.json.lock")
                self.assertEqual(sorted(p.name for p in self.workdir.iterdir()),
                                 sorted(expected_names))

    def test_misleading_small_metadata_cannot_admit_an_oversized_real_file(self):
        policy = replace(es.documented_transport_policy(), max_bytes=64)
        raw = b"x" * 1024
        original_stat = os.stat

        def lying_stat(path, *args, **kwargs):
            result = original_stat(path, *args, **kwargs)
            if Path(path) == self.target:
                values = list(result)
                values[6] = 0
                return os.stat_result(values)
            return result

        for operation in ("load", "commit"):
            with self.subTest(operation=operation):
                self.target.write_bytes(raw)
                requests, handles = [], []
                with ExitStack() as stack:
                    self.forbid_decode(stack)
                    stack.enter_context(mock.patch.object(os, "stat", lying_stat))
                    stack.enter_context(self.track_open(requests, handles))
                    with self.assertRaises(es.TransportDomainError):
                        self.invoke(operation, policy, raw)
                self.assertEqual([size for _, size in requests], [65])
                self.assertTrue(all(handle.closed for handle in handles))
                self.assertEqual(self.target.read_bytes(), raw)

    def test_growth_after_open_is_detected_from_the_actual_handle(self):
        policy, raw, _ = exact_limit_file(self.session)
        original_open = Path.open

        def grow():
            with original_open(self.target, "ab") as writer:
                writer.write(b"x")

        for operation in ("load", "commit"):
            with self.subTest(operation=operation):
                self.target.write_bytes(raw)
                requests, handles = [], []
                with ExitStack() as stack:
                    self.forbid_decode(stack)
                    stack.enter_context(self.track_open(requests, handles, grow))
                    with self.assertRaises(es.TransportDomainError):
                        self.invoke(operation, policy, raw)
                self.assertEqual([size for _, size in requests], [policy.max_bytes + 1])
                self.assertTrue(all(handle.closed for handle in handles))
                # Only the simulated external growth changed the file.
                self.assertEqual(self.target.read_bytes(), raw + b"x")
                self.assertEqual(list(self.workdir.glob(".*.tmp")), [])

    def test_oversized_commit_refuses_before_digest_encode_or_temporary_write(self):
        policy = replace(es.documented_transport_policy(), max_bytes=64)
        raw = b"x" * 65
        self.target.write_bytes(raw)
        lock_events = []
        original_flock = es.fcntl.flock

        def tracked_flock(descriptor, operation):
            lock_events.append(operation)
            return original_flock(descriptor, operation)

        with ExitStack() as stack:
            self.forbid_decode(stack)
            stack.enter_context(mock.patch.object(es.fcntl, "flock", tracked_flock))
            for name in ("_digest_bytes", "encode_session", "_create_temp_file",
                         "_replace_durably"):
                stack.enter_context(mock.patch.object(
                    es, name, side_effect=AssertionError(f"unexpected commit step: {name}")))
            with self.assertRaises(es.TransportDomainError):
                self.invoke("commit", policy, raw, digest="0" * 64)
        self.assertEqual(lock_events, [es.fcntl.LOCK_EX, es.fcntl.LOCK_UN])
        self.assertEqual(self.target.read_bytes(), raw)
        self.assertEqual(sorted(p.name for p in self.workdir.iterdir()),
                         [".session.json.lock", "session.json"])

    def test_valid_existing_destination_uses_bounded_read_and_commits_next_generation(self):
        policy, raw, _ = exact_limit_file(self.session)
        self.target.write_bytes(raw)
        requests, handles = [], []
        with self.track_open(requests, handles), mock.patch.object(
                Path, "read_bytes", side_effect=AssertionError("unbounded read")):
            result = self.invoke("commit", policy, raw)
        expected = es.encode_session(self.session, transport=policy, generation=2)
        expected_bytes = es.encode_envelope_text(expected, policy)
        self.assertEqual([size for _, size in requests], [policy.max_bytes + 1])
        self.assertTrue(all(handle.closed for handle in handles))
        self.assertEqual(result.generation, 2)
        self.assertEqual(result.envelope, expected)
        self.assertEqual(result.digest, hashlib.sha256(expected_bytes).hexdigest())
        self.assertEqual(self.target.read_bytes(), expected_bytes)
        self.assertEqual(es.load_session(self.target, transport=policy).session, self.session)

    def test_in_limit_digest_and_generation_mismatches_remain_stale(self):
        policy, raw, _ = exact_limit_file(self.session)
        self.target.write_bytes(raw)
        for generation, digest in ((1, "0" * 64), (2, hashlib.sha256(raw).hexdigest())):
            with self.subTest(generation=generation, digest=digest):
                with mock.patch.object(es, "encode_session", side_effect=AssertionError(
                        "checkpoint validation must follow expected-generation")):
                    with self.assertRaises(es.StaleGenerationError):
                        self.invoke("commit", policy, raw, generation=generation, digest=digest)
                self.assertEqual(self.target.read_bytes(), raw)
                self.assertEqual(list(self.workdir.glob(".*.tmp")), [])

    def test_malformed_in_limit_files_keep_normal_decoder_errors(self):
        policy = replace(es.documented_transport_policy(), max_bytes=64)
        for raw, message in ((b"\xff", "not valid UTF-8"), (b"{", "not valid JSON"),
                             (b"{}", "envelope fields")):
            for operation in ("load", "commit"):
                with self.subTest(raw=raw, operation=operation):
                    self.target.write_bytes(raw)
                    with self.assertRaisesRegex(es.SessionError, message) as raised:
                        self.invoke(operation, policy, raw)
                    self.assertNotIsInstance(raised.exception, es.TransportDomainError)
                    self.assertEqual(self.target.read_bytes(), raw)
                    self.assertEqual(list(self.workdir.glob(".*.tmp")), [])

    def test_invalid_policy_is_rejected_before_file_io_or_lock(self):
        self.target.write_bytes(b"anything")
        for operation in ("load", "commit"):
            with self.subTest(operation=operation):
                with mock.patch.object(Path, "open", side_effect=AssertionError(
                        "file must not open")), mock.patch.object(
                        es, "_exclusive_lock", side_effect=AssertionError("lock must not open")):
                    with self.assertRaises(es.SessionError) as raised:
                        self.invoke(operation, replace(es.documented_transport_policy(),
                                                       max_bytes=True), b"anything")
                self.assertNotIsInstance(raised.exception, es.TransportDomainError)
                self.assertEqual(sorted(p.name for p in self.workdir.iterdir()),
                                 ["session.json"])

    def test_path_and_open_errors_are_not_reclassified_as_bound_excess(self):
        policy = es.documented_transport_policy()
        with self.assertRaises(FileNotFoundError):
            es.load_session(self.target, transport=policy)
        with self.assertRaises(IsADirectoryError):
            es.load_session(self.workdir, transport=policy)
        self.target.write_bytes(b"{}")
        for operation in ("load", "commit"):
            with self.subTest(operation=operation):
                error = PermissionError("injected ordinary open failure")
                with mock.patch.object(Path, "open", side_effect=error):
                    with self.assertRaises(PermissionError) as raised:
                        self.invoke(operation, policy, b"{}")
                self.assertIs(raised.exception, error)
                self.assertEqual(self.target.read_bytes(), b"{}")

    def test_read_io_errors_propagate_unchanged_and_close_the_handle(self):
        policy, raw, _ = exact_limit_file(self.session)
        for operation in ("load", "commit"):
            with self.subTest(operation=operation):
                self.target.write_bytes(raw)
                error = OSError("injected ordinary read failure")
                handles, requests = [], []

                def fail_read():
                    raise error

                with self.track_open(requests, handles, fail_read):
                    with self.assertRaises(OSError) as raised:
                        self.invoke(operation, policy, raw)
                self.assertIs(raised.exception, error)
                self.assertTrue(all(handle.closed for handle in handles))
                self.assertEqual(self.target.read_bytes(), raw)


if __name__ == "__main__":
    unittest.main()
