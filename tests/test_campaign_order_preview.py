"""Offline contract gates; tiny existing three-region table, no new sampling."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack, redirect_stderr, redirect_stdout
from dataclasses import FrozenInstanceError, replace
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import random
import runpy
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from chronicler import campaign_logistics as cl
from chronicler import experiment_sessions as es
from chronicler.campaign_order_preview import (
    Alternative, CONTRACT, PreviewError, PreviewReport, preview_json, preview_orders, preview_text,
)

ROOT = Path(__file__).resolve().parents[1]
DRIVER = ROOT / "scripts/campaign_order_preview.py"
MODULE = ROOT / "src/chronicler/campaign_order_preview.py"
DEMO = runpy.run_path(str(ROOT / "scripts/campaign_logistics_demo.py"))


def opening(turn=1):
    policy, topology = DEMO["illustrative_policy"](), DEMO["fixture_topology"]()
    admitted = DEMO["fixture_session"](policy, topology).state
    session = es.create_campaign_session(policy=policy, topology=topology,
        campaign_id=admitted.campaign_id, turn=0, staging=1, target=2,
        soldiers=admitted.soldiers, stocks=admitted.stocks)
    for current in range(1, turn + 1):
        session = es.apply_campaign_tick(session, DEMO["fixture_tick"](session.session, current)).session
    return session


def choices(session):
    tick = DEMO["fixture_tick"](session.session, session.session.state.turn + 1)
    return (Alternative("march", replace(tick, orders=(cl.Order("choice", tick.turn, "march"),))),
            Alternative("hold", replace(tick, orders=(cl.Order("choice", tick.turn, "hold"),))))


def call(opening_session, alternatives=None, **kwargs):
    options = dict(enabled=True, session=opening_session,
                   alternatives=choices(opening_session) if alternatives is None else alternatives,
                   max_alternatives=2, transport=es.documented_transport_policy())
    options.update(kwargs)
    return preview_orders(**options)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def document(alternatives):
    return cl.canonical_bytes({"contract": CONTRACT, "alternatives": [
        {"label": a.label, "tick": json.loads(cl.canonical_bytes(a.tick))} for a in alternatives]})


def cli_module():
    spec = importlib.util.spec_from_file_location("preview_test_driver", DRIVER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PreviewTests(unittest.TestCase):
    def test_hand_ready_march_hold_complete_public_oracle(self):
        session = opening()
        self.assertEqual(session.session.state.phase, "ready")
        self.assertEqual([(s.region, s.rations, s.morale) for s in session.session.state.soldiers],
                         [(1, 7, 820), (1, 7, 790)])
        before = cl.canonical_bytes(session)
        report = call(session)
        self.assertEqual(report.base_session_digest, es.session_digest(session, es.documented_transport_policy()))
        for row, alternative, phase, region in zip(report.alternatives, choices(session),
                                                 ("marching", "ready"), (0, 1)):
            receipt = json.loads(row.receipt_json)
            direct = es.apply_campaign_tick(session, alternative.tick).receipts[0]
            self.assertEqual(row.receipt_json.encode(), cl.canonical_bytes(direct))
            self.assertEqual(receipt["phase_after"], phase)
            self.assertEqual([m["region_after"] for m in receipt["members"]], [region, region])
            self.assertEqual([m["ration_after"] for m in receipt["members"]], [6, 6])
            self.assertEqual([m["consumed"] for m in receipt["members"]], [1, 1])
            self.assertEqual([m["distance_stress"] for m in receipt["members"]], [0, 0])
            self.assertEqual([m["morale_after"] for m in receipt["members"]], [840, 810])
            self.assertEqual(receipt["food"], dict(initial=20, credits=0, local=4,
                carried=12, consumed=4, deserted=0))
            self.assertEqual(20, 4 + 12 + 4)
            summary = json.loads(row.summary_json)
            self.assertEqual(summary["food"], receipt["food"])
            self.assertEqual(summary["members"][0]["reasons"], receipt["members"][0]["reasons"])
        self.assertEqual(cl.canonical_bytes(session), before)

    def test_arrived_replenish_return_small_fixed_table(self):
        session = opening(3)
        tick = DEMO["fixture_tick"](session.session, 4)
        alternatives = (Alternative("hold/replenish", tick),
                        Alternative("return", replace(tick, orders=(cl.Order("return-choice", 4, "return"),))))
        report = call(session, alternatives)
        self.assertEqual(session.session.state.phase, "arrived")
        expected = (("arrived", 2, [2, 2], 2, 12), ("returning", 0, [], 6, 8))
        for row, alternative, (phase, region, grants, local, carried) in zip(report.alternatives, alternatives, expected):
            receipt = json.loads(row.receipt_json)
            self.assertEqual(row.receipt_json.encode(), cl.canonical_bytes(es.apply_campaign_tick(session, alternative.tick).receipts[0]))
            self.assertEqual(receipt["phase_after"], phase)
            self.assertEqual([m["region_after"] for m in receipt["members"]], [region, region])
            self.assertEqual([g["granted"] for g in receipt["replenishments"]], grants)
            self.assertEqual([m["morale_after"] for m in receipt["members"]], [810, 780])
            self.assertEqual(receipt["food"], dict(initial=20, credits=2, local=local,
                                                 carried=carried, consumed=8, deserted=0))
            self.assertEqual(22, local + carried + 8)
        grants = json.loads(report.alternatives[0].receipt_json)["replenishments"]
        self.assertEqual([(g["agent_id"], g["region"], g["stock_before"], g["stock_after"], g["reason"]) for g in grants],
                         [(101, 2, 6, 4, "replenished"), (202, 2, 4, 2, "replenished")])
        self.assertEqual(json.loads(report.alternatives[1].receipt_json)["stocks_before"],
                         json.loads(report.alternatives[0].receipt_json)["stocks_before"])

    def test_reverse_and_concurrent_equal_serial_no_global_change(self):
        session, alternatives = opening(), choices(opening())
        state = cl.canonical_bytes(session), es.session_digest(session, es.documented_transport_policy())
        serial = call(session, alternatives)
        reversed_report = call(session, tuple(reversed(alternatives)))
        self.assertEqual(tuple(reversed(serial.alternatives)), reversed_report.alternatives)
        argv, modules, rng = tuple(sys.argv), set(sys.modules), random.getstate()
        with mock.patch.object(es, "commit_session", side_effect=AssertionError("persistence")):
            with ThreadPoolExecutor(max_workers=2) as executor:
                reports = list(executor.map(lambda _: call(session, alternatives), range(2)))
        self.assertEqual(reports, [serial, serial])
        self.assertEqual(tuple(sys.argv), argv)
        self.assertEqual(set(sys.modules), modules)
        self.assertEqual(random.getstate(), rng)
        self.assertEqual((cl.canonical_bytes(session), es.session_digest(session, es.documented_transport_policy())), state)

    def test_immutable_report_and_detached_payload(self):
        report = call(opening())
        with self.assertRaises(FrozenInstanceError):
            report.base_turn = 9
        with self.assertRaises(FrozenInstanceError):
            report.alternatives[0].label = "new"
        payload = report.as_payload()
        payload["alternatives"][0]["receipt"]["members"].clear()
        self.assertEqual(len(report.as_payload()["alternatives"][0]["receipt"]["members"]), 2)
        self.assertNotIn("generation", payload)
        self.assertNotIn("session", payload)
        self.assertFalse(payload["committed"])

    def test_exact_enable_and_off_poison(self):
        class Poison:
            def __getattribute__(self, name):
                raise AssertionError("inspected poison")
            def __iter__(self):
                raise AssertionError("consumed poison")
        for enabled in (0, 1, None, "true"):
            with self.assertRaises(PreviewError):
                preview_orders(enabled=enabled)
        with mock.patch.object(es, "encode_session", side_effect=AssertionError("encode")), \
             mock.patch.object(es, "apply_campaign_tick", side_effect=AssertionError("apply")), \
             mock.patch.object(es, "load_session", side_effect=AssertionError("load")):
            self.assertEqual(preview_orders(session=Poison(), alternatives=Poison(),
                max_alternatives=Poison(), transport=Poison()), PreviewReport())

    def test_containers_bounds_labels_and_count_before_elements(self):
        session = opening()
        for kwargs in ({"alternatives": list(choices(session))}, {"alternatives": iter(choices(session))},
                       {"alternatives": ()}, {"alternatives": (object(), object(), object())},
                       {"max_alternatives": True}, {"max_alternatives": 0},
                       {"max_alternatives": 2.0}, {"session": object()}, {"transport": None}):
            # subTest parameters are plain values: pytest-xdist serializes them.
            with self.subTest(kwargs=repr(kwargs)), self.assertRaises(ValueError):
                call(session, **kwargs)
        for label in ("", " ", "x" * 129, None, 4):
            with self.subTest(label=label), self.assertRaises(PreviewError):
                call(session, (Alternative(label, choices(session)[0].tick),))
        with self.assertRaisesRegex(PreviewError, "duplicate label"):
            call(session, (choices(session)[0], choices(session)[0]))
        with self.assertRaisesRegex(PreviewError, "alternative count"), \
             mock.patch.object(es, "encode_session", side_effect=AssertionError("too early")):
            call(session, (object(), object(), object()))

    def test_bad_turns_and_invalid_later_alternative_atomic(self):
        session, alternatives = opening(), choices(opening())
        before = cl.canonical_bytes(session)
        before_digest = es.session_digest(session, es.documented_transport_policy())
        bad_ticks = (replace(alternatives[1].tick, turn=1), replace(alternatives[1].tick, turn=3),
                     replace(alternatives[1].tick, turn=True), replace(alternatives[1].tick, draws=()),
                     replace(alternatives[1].tick, conditions=()),
                     replace(alternatives[1].tick, orders=(cl.Order("bad", 2, "teleport"),)),
                     replace(alternatives[1].tick, orders=[cl.Order("bad", 2, "hold")]),
                     object())
        for tick in bad_ticks:
            with self.subTest(tick=repr(tick)), self.assertRaisesRegex(PreviewError, "alternative 'bad'"):
                call(session, (alternatives[0], Alternative("bad", tick)))
            self.assertEqual(cl.canonical_bytes(session), before)
            self.assertEqual(es.session_digest(session, es.documented_transport_policy()), before_digest)

    def test_every_non_order_field_must_agree(self):
        session, alternatives = opening(), choices(opening())
        tick = alternatives[1].tick
        changed = (replace(tick, credits=(cl.Credit("different", 2, 1, 1),)),
                   replace(tick, supply_sources=(0,)),
                   replace(tick, draws=(cl.Draw(101, 9998), cl.Draw(202, 9999))),
                   replace(tick, conditions=(cl.Condition(101, 1, 1000), cl.Condition(202, 0, 1000))))
        before = cl.canonical_bytes(session)
        for tick in changed:
            with self.subTest(tick=tick), self.assertRaisesRegex(PreviewError, "alternative 'different'.*only in orders"):
                call(session, (alternatives[0], Alternative("different", tick)))
            self.assertEqual(cl.canonical_bytes(session), before)

    def test_equivalent_permutations_canonicalize(self):
        session = opening(3)
        tick = DEMO["fixture_tick"](session.session, 4)
        permuted = replace(tick, orders=tuple(reversed(tick.orders)),
            conditions=tuple(reversed(tick.conditions)), draws=tuple(reversed(tick.draws)))
        first, second = call(session, (Alternative("first", tick), Alternative("second", permuted))).alternatives
        self.assertEqual(first.receipt_json, second.receipt_json)
        self.assertEqual(first.summary_json, second.summary_json)

    def test_committed_id_rejected_separate_choice_id_allowed(self):
        session = opening(3)
        tick = DEMO["fixture_tick"](session.session, 4)
        with self.assertRaisesRegex(PreviewError, "already committed"):
            call(session, (Alternative("bad", replace(tick, orders=(cl.Order("march-2", 4, "hold"),))),))
        self.assertEqual(len(call(opening()).alternatives), 2)

    def test_transport_input_and_derived_domain_and_full_history(self):
        session = opening()
        policy = es.documented_transport_policy()
        for transport in (replace(policy, max_bytes=1), replace(policy, max_records=1),
                          replace(policy, max_int_bits=1), replace(policy, max_bytes=True)):
            with self.subTest(transport=transport), self.assertRaises(ValueError):
                call(session, transport=transport)
        with self.assertRaisesRegex(PreviewError, "alternative 'march'.*history"):
            call(session, transport=replace(policy, max_history=1))
        tampered = replace(session, session=replace(session.session,
            state=replace(session.session.state, consumed_food=999)))
        with self.assertRaises(ValueError):
            call(tampered)
        # Bound the entire alternatives submission even if individual ticks fit.
        alternatives = tuple(Alternative(f"label-{i}", choices(session)[0].tick) for i in range(40))
        encoded_session = es.encode_envelope_text(es.encode_session(session, transport=policy, generation=1), policy)
        smaller = replace(policy, max_bytes=len(encoded_session) + 1)
        self.assertGreater(len(document(alternatives)), smaller.max_bytes)
        with self.assertRaisesRegex(ValueError, "alternatives.*byte"):
            call(session, alternatives, max_alternatives=40, transport=smaller)

    def test_terminal_noop_is_new_turn(self):
        session = opening(7)
        tick = DEMO["fixture_tick"](session.session, 8)
        row = call(session, (Alternative("terminal", tick),)).alternatives[0]
        self.assertEqual(row.proposed_turn, 8)
        self.assertIn("terminal_noop", json.loads(row.receipt_json)["reasons"])

    def test_enabled_forbids_persistence_and_lock_creation(self):
        session = opening()
        with ExitStack() as stack:
            for target, name in ((es, "commit_session"), (os, "open"), (os, "replace"),
                                 (os, "unlink"), (Path, "open"), (random, "random")):
                stack.enter_context(mock.patch.object(target, name, side_effect=AssertionError(name)))
            call(session)

    def test_import_and_off_forbid_input_kernel_fixture_and_rng_work(self):
        driver = cli_module()
        with ExitStack() as stack:
            for target, name in ((es, "encode_session"), (es, "apply_campaign_tick"),
                                 (es, "load_session"), (es, "commit_session"), (cl, "advance"),
                                 (cl, "admit"), (Path, "open"), (runpy, "run_path"),
                                 (random, "random"), (random, "seed")):
                stack.enter_context(mock.patch.object(target, name, side_effect=AssertionError(name)))
            spec = importlib.util.spec_from_file_location("chronicler.preview_import_control", MODULE)
            module = importlib.util.module_from_spec(spec)
            stack.enter_context(mock.patch.dict(sys.modules, {spec.name: module}))
            spec.loader.exec_module(module)
            self.assertFalse(module.preview_orders().enabled)
            out = io.StringIO()
            with redirect_stdout(out):
                self.assertEqual(driver.main(["--path", "/nonexistent", "--max-alternatives", "poison", "--format", "wrong", "--unknown"]), 0)
            self.assertEqual(out.getvalue(), preview_json(PreviewReport()))


class CliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.session = opening()
        self.transport = es.documented_transport_policy()
        self.path = self.directory / "campaign.json"
        self.policy = self.directory / "transport.json"
        self.alternatives = self.directory / "alternatives.json"
        # The accepted writer prepares the fixture before preview controls.
        initial = es.commit_session(self.path, opening(0), transport=self.transport,
                                    expected_generation=None, expected_digest=None)
        self.committed = es.commit_session(self.path, self.session, transport=self.transport,
                                           expected_generation=initial.generation, expected_digest=initial.digest)
        self.policy.write_bytes(cl.canonical_bytes(self.transport))
        self.alternatives.write_bytes(document(choices(self.session)))
        self.arguments = ["--enable", "--path", str(self.path), "--transport", str(self.policy),
                          "--alternatives", str(self.alternatives), "--max-alternatives", "2"]

    def inventory(self):
        return {p.name: (p.stat().st_mode, p.read_bytes()) for p in self.directory.iterdir()}

    def process(self, arguments=None, seed=None):
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        if seed is not None:
            env["PYTHONHASHSEED"] = str(seed)
        return subprocess.run([sys.executable, "-B", str(DRIVER),
            *(self.arguments if arguments is None else arguments)], env=env,
            capture_output=True, timeout=30)

    def test_real_cli_observed_bytes_complete_report_and_nonmutation(self):
        before = self.inventory()
        result = self.process()
        self.assertEqual((result.returncode, result.stderr), (0, b""))
        payload = json.loads(result.stdout)
        observed = payload.pop("cli_observation")
        self.assertEqual(observed["file_digest"], digest(before[self.path.name][1]))
        self.assertEqual((observed["generation"], observed["turn"]), (2, 1))
        self.assertFalse(observed["submission_token"])
        self.assertEqual(payload, call(self.session).as_payload())
        self.assertEqual(self.inventory(), before)

    def test_actual_hashseed_0_42_101_stdout_stderr_exit_and_postbytes(self):
        before = self.inventory()
        results = [self.process(seed=seed) for seed in (0, 42, 101)]
        self.assertEqual([(r.returncode, r.stdout, r.stderr) for r in results],
                         [(0, results[0].stdout, b"")] * 3)
        self.assertEqual(self.inventory(), before)
        self.alternatives.write_bytes(b'{"contract":true,"alternatives":[]}')
        before = self.inventory()
        failures = [self.process(seed=seed) for seed in (0, 42, 101)]
        self.assertEqual([(r.returncode, r.stdout, r.stderr) for r in failures],
                         [(3, b"", failures[0].stderr)] * 3)
        self.assertEqual(self.inventory(), before)

    def test_invalid_cli_complete_output_atomic_and_nonmutation(self):
        valid = json.loads(self.alternatives.read_bytes())
        bad_documents = [b'{"contract":1,"contract":2,"alternatives":[]}',
                         b'{"contract":NaN,"alternatives":[]}',
                         b'{"contract":1.1,"alternatives":[]}',
                         b'{"contract":"wrong","alternatives":[]}',
                         cl.canonical_bytes({**valid, "extra": 1})]
        bad = json.loads(self.alternatives.read_bytes())
        bad["alternatives"][1]["tick"]["draws"] = []
        bad_documents.append(cl.canonical_bytes(bad))
        bad = json.loads(self.alternatives.read_bytes())
        bad["alternatives"][1]["tick"]["turn"] = True
        bad_documents.append(cl.canonical_bytes(bad))
        for data in bad_documents:
            with self.subTest(data=data):
                self.alternatives.write_bytes(data)
                before = self.inventory()
                result = self.process()
                self.assertEqual((result.returncode, result.stdout), (3, b""))
                self.assertIn(b"error", result.stderr)
                self.assertEqual(self.inventory(), before)

    def test_cli_count_precedes_record_decode(self):
        driver = cli_module()
        data = cl.canonical_bytes({"contract": CONTRACT, "alternatives": [None, None, None]})
        with mock.patch.object(es, "campaign_tick_from_payload", side_effect=AssertionError("decode")), \
             self.assertRaisesRegex(PreviewError, "alternative count"):
            driver._alternatives(data, self.transport, 2)

    def test_bounded_reads_at_most_limit_plus_one(self):
        driver = cli_module()
        requests = []
        import builtins
        original = builtins.open
        class Handle:
            def __init__(self, handle): self.handle = handle
            def __enter__(self): return self
            def __exit__(self, *args): self.handle.close()
            def fileno(self): return self.handle.fileno()
            def read(self, size):
                requests.append(size)
                return self.handle.read(size)
        def tracked(descriptor, *args, **kwargs): return Handle(original(descriptor, *args, **kwargs))
        with mock.patch.object(builtins, "open", tracked):
            driver._read(self.policy, 4096)
            driver._read(self.alternatives, self.transport.max_bytes)
        self.assertEqual(requests, [4097, self.transport.max_bytes + 1])
        self.policy.write_bytes(b" " * 4097)
        before = self.inventory()
        result = self.process()
        self.assertEqual((result.returncode, result.stdout), (3, b""))
        self.assertEqual(self.inventory(), before)
        self.policy.write_bytes(cl.canonical_bytes(self.transport))
        self.alternatives.write_bytes(b" " * (self.transport.max_bytes + 1))
        result = self.process()
        self.assertEqual((result.returncode, result.stdout), (3, b""))

    def test_regular_file_only_no_directory_links_or_fifo(self):
        directory = self.directory / "not-file"
        directory.mkdir()
        link = self.directory / "link"
        link.symlink_to(self.alternatives)
        fifo = self.directory / "fifo"
        os.mkfifo(fifo)
        for path in (directory, link, fifo):
            for flag in ("--path", "--transport", "--alternatives"):
                args = self.arguments.copy()
                args[args.index(flag) + 1] = str(path)
                with self.subTest(path=path.name, flag=flag):
                    result = self.process(args)
                    self.assertEqual((result.returncode, result.stdout), (3, b""))
                    self.assertIn(b"regular", result.stderr)

    def test_replacement_after_one_verified_read_rows_use_observation(self):
        replacement = self.directory / "replacement.json"
        newer = es.apply_campaign_tick(self.session, choices(self.session)[0].tick).session
        es.commit_session(replacement, newer, transport=self.transport,
                          expected_generation=None, expected_digest=None)
        original_bytes = self.path.read_bytes()
        replacement_bytes = replacement.read_bytes()
        driver = cli_module()
        public_load = es.load_session
        loads, opens = [], []
        original_open = os.open
        def tracked_open(path, *args, **kwargs):
            if Path(path) == self.path: opens.append(path)
            return original_open(path, *args, **kwargs)
        def load_then_replace(path, **kwargs):
            loaded = public_load(path, **kwargs)
            loads.append(loaded)
            # Prepared through the existing public writer; no replacement writer.
            os.replace(replacement, self.path)
            return loaded
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(es, "load_session", load_then_replace), \
             mock.patch.object(os, "open", tracked_open), redirect_stdout(out), redirect_stderr(err):
            self.assertEqual(driver.main(self.arguments), 0)
        self.assertEqual((len(loads), len(opens), err.getvalue()), (1, 1, ""))
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["cli_observation"]["file_digest"], digest(original_bytes))
        self.assertEqual(payload["cli_observation"]["generation"], 2)
        self.assertEqual(payload["base_turn"], 1)
        self.assertNotEqual(digest(self.path.read_bytes()), digest(original_bytes))
        self.assertEqual(self.path.read_bytes(), replacement_bytes)
        self.assertEqual(payload["alternatives"], call(self.session).as_payload()["alternatives"])
        self.assertIn("currentness", payload["cli_observation"]["scope"])
        self.assertFalse(payload["cli_observation"]["submission_token"])

    def test_text_help_and_off_actual_cli(self):
        before = self.inventory()
        result = self.process(self.arguments + ["--format", "text"])
        self.assertEqual((result.returncode, result.stderr), (0, b""))
        self.assertIn(b"CLI observation:", result.stdout)
        self.assertIn(b"Receipt:", result.stdout)
        help_result = self.process(["--path", "/nonexistent", "--max-alternatives", "bad", "--help"])
        self.assertEqual((help_result.returncode, help_result.stderr), (0, b""))
        self.assertIn(b"--enable", help_result.stdout)
        disabled = self.process(["--path", "/nonexistent", "--format", "bad", "--max-alternatives", "bad"])
        self.assertEqual((disabled.returncode, disabled.stderr, disabled.stdout),
                         (0, b"", preview_json(PreviewReport()).encode()))
        self.assertEqual(self.inventory(), before)

    def test_enable_missing_values_and_memome_rejected(self):
        for args in (["--enable"], self.arguments[:-2], self.arguments + ["--max-alternatives", "0"]):
            result = self.process(args)
            self.assertEqual((result.returncode, result.stdout), (3, b""))
        table = runpy.run_path(str(ROOT / "scripts/memome_demo.py"))
        people, _ = table["unit_tables"]()
        memome = es.create_memome_session(policy=table["illustrative_policy"](),
                                         genesis_turn=0, participants=people)
        self.path.write_bytes(es.encode_envelope_text(es.encode_session(
            memome, transport=self.transport, generation=7), self.transport))
        before = self.inventory()
        result = self.process()
        self.assertEqual((result.returncode, result.stdout), (3, b""))
        self.assertIn(b"CampaignSession", result.stderr)
        self.assertEqual(self.inventory(), before)
        # Exact CampaignSession check applies independently of foreign content.
        with self.assertRaisesRegex(PreviewError, "CampaignSession"):
            preview_orders(enabled=True, session=object(), alternatives=(),
                           max_alternatives=1, transport=self.transport)


if __name__ == "__main__":
    unittest.main()
