"""Tiny existing M68a table oracles and report/CLI boundaries, entirely local."""
import ast
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack, redirect_stderr, redirect_stdout
from dataclasses import FrozenInstanceError, asdict, fields, replace
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

from chronicler import experiment_sessions as es
from chronicler import memome_experiment as mm
from chronicler import memome_candidate_preview as preview
from chronicler.memome_candidate_preview import (
    Alternative, CONTRACT, PreviewError, PreviewReport, preview_candidates, preview_json, preview_text,
)

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT/'src/chronicler/memome_candidate_preview.py'
DRIVER = ROOT/'scripts/memome_candidate_preview.py'
# Read only the existing explicit table; no demonstration is run.
DEMO = runpy.run_path(str(ROOT/'scripts/memome_demo.py'))


def opening(turn=0):
    people, batches = DEMO['unit_tables']()
    session = es.create_memome_session(policy=DEMO['illustrative_policy'](),
                                      genesis_turn=0, participants=people)
    for batch in batches[:turn]:
        session = es.apply_memome_batch(session, batch).session
    return session


def choices(turn=1):
    batch = mm.Batch(turn, (mm.Proposal('choice', 'basic-1', 1, 3, 199),))
    return (Alternative('candidate 3', batch), Alternative('candidate 0',
        replace(batch, proposals=(replace(batch.proposals[0], candidate=0),))))


def call(opening_session=None, alternatives=None, **kwargs):
    options = dict(enabled=True, session=opening() if opening_session is None else opening_session,
                   alternatives=choices() if alternatives is None else alternatives,
                   max_alternatives=2, transport=es.documented_transport_policy())
    options.update(kwargs)
    return preview_candidates(**options)


def canonical(payload):
    return json.dumps(payload, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def document(alternatives):
    return canonical({'contract': CONTRACT, 'alternatives': [
        {'label': a.label, 'batch': asdict(a.batch)} for a in alternatives]})


def identity(session):
    return (mm.checkpoint_json(session.ledger, session.policy),
            canonical(asdict(session)), es.session_digest(session, es.documented_transport_policy()))


def driver_module():
    spec = importlib.util.spec_from_file_location('memome_preview_test_driver', DRIVER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PreviewTests(unittest.TestCase):
    def assert_direct(self, session, row, batch):
        direct = mm.advance(session.ledger, batch, session.policy, enabled=True)
        self.assertEqual(row.admitted_batch, direct.ledger.history[-1].batch)
        self.assertEqual(tuple(view.receipt for view in row.receipts), direct.receipts)
        self.assertEqual([set(view.as_payload()['receipt']) for view in row.receipts],
                         [set(field.name for field in fields(mm.Receipt))] * len(direct.receipts))
        before = {p.agent_id: p for p in session.ledger.participants}
        after = {p.agent_id: p for p in direct.ledger.participants}
        for view in row.receipts:
            self.assertEqual(view.previous_slot_value, before[view.receipt.recipient].slots[view.receipt.slot])
            self.assertEqual(view.resulting_slot_value, after[view.receipt.recipient].slots[view.receipt.slot])

    def test_basic_hand_candidate_three_accepts_zero_absent_complete_receipts(self):
        session, alternatives = opening(), choices()
        before = identity(session)
        report = call(session, alternatives)
        self.assertEqual((report.base_turn, report.base_session_digest), (0, before[2]))
        self.assertEqual((report.policy_version, report.draw_scale), (mm.CONTRACT, 1000))
        for row, alternative in zip(report.alternatives, alternatives):
            self.assert_direct(session, row, alternative.batch)
        first, second = (row.receipts[0] for row in report.alternatives)
        self.assertEqual((first.receipt.candidate_weight, first.receipt.electorate_weight,
                          first.receipt.threshold, first.receipt.draw, first.receipt.reason,
                          first.previous_slot_value, first.resulting_slot_value),
                         (1, 3, 200, 199, 'accepted', 1, 3))
        self.assertEqual((second.receipt.candidate_weight, second.receipt.electorate_weight,
                          second.receipt.threshold, second.receipt.draw, second.receipt.reason,
                          second.previous_slot_value, second.resulting_slot_value),
                         (0, 3, 0, 199, 'absent_candidate', 1, 1))
        self.assertEqual(identity(session), before)

    def test_synchronous_second_vote_uses_opening_frequency_not_first_success(self):
        session = opening()
        batch = mm.Batch(1, (mm.Proposal('a-first', 'basic-1', 1, 3, 199),
                             mm.Proposal('b-second', 'basic-2', 1, 3, 200)))
        row = call(session, (Alternative('synchronous', batch),)).alternatives[0]
        self.assert_direct(session, row, batch)
        self.assertEqual([(v.receipt.candidate_weight, v.receipt.electorate_weight,
                           v.receipt.threshold, v.receipt.reason, v.resulting_slot_value) for v in row.receipts],
                         [(1, 3, 200, 'accepted', 3), (1, 3, 200, 'probability_rejected', 5)])

    def test_named_five_six_and_exact_draw_boundaries(self):
        session = opening()
        for draw, reason, value in ((960, 'accepted', 2), (961, 'probability_rejected', 5)):
            batch = mm.Batch(1, (mm.Proposal('named', 'ordinary-1', 2, 2, draw),))
            row = call(session, (Alternative('named', batch),)).alternatives[0]
            self.assert_direct(session, row, batch)
            view = row.receipts[0]
            self.assertEqual((view.receipt.candidate_weight, view.receipt.electorate_weight,
                              view.receipt.threshold, view.receipt.reason, view.resulting_slot_value),
                             (5, 6, 961, reason, value))
        for draw, reason in ((199, 'accepted'), (200, 'probability_rejected')):
            row = call(session, (Alternative('boundary', mm.Batch(1, (
                replace(choices()[0].batch.proposals[0], draw=draw),))),)).alternatives[0]
            self.assertEqual((row.receipts[0].receipt.threshold, row.receipts[0].receipt.reason), (200, reason))

    def test_reason_precedence_incompatible_unchanged_empty_electorate(self):
        session = opening()
        proposals = ((mm.Proposal('incompatible', 'basic-2', 2, 3, 0), 'incompatible', 2),
                     (mm.Proposal('same', 'basic-0', 1, 3, 999), 'unchanged', 3),
                     (mm.Proposal('empty', 'basic-1', 3, 1, 0), 'empty_electorate', 255))
        for proposal, reason, value in proposals:
            row = call(session, (Alternative(reason, mm.Batch(1, (proposal,))),)).alternatives[0]
            self.assert_direct(session, row, mm.Batch(1, (proposal,)))
            self.assertEqual((row.receipts[0].receipt.reason, row.receipts[0].resulting_slot_value), (reason, value))

    def test_explicit_empty_next_batch_is_hypothetical_new_turn(self):
        session = opening(2)
        row = call(session, (Alternative('empty', mm.Batch(3, ())),)).alternatives[0]
        self.assert_direct(session, row, mm.Batch(3, ()))
        self.assertEqual((row.proposed_turn, row.receipts, row.admitted_batch), (3, (), mm.Batch(3, ())))
        self.assertEqual(session.ledger.turn, 2)

    def test_canonical_proposal_permutations_and_reversed_alternatives(self):
        session = opening()
        batch = DEMO['unit_tables']()[1][0]
        alternative = replace(batch, proposals=tuple(reversed(batch.proposals)))
        report = call(session, (Alternative('first', batch), Alternative('second', alternative)))
        self.assertEqual(report.alternatives[0].admitted_batch, report.alternatives[1].admitted_batch)
        self.assertEqual(report.alternatives[0].receipts, report.alternatives[1].receipts)
        serial = call(session)
        self.assertEqual(call(session, tuple(reversed(choices()))).alternatives,
                         tuple(reversed(serial.alternatives)))

    def test_concurrency_identity_and_process_globals_preserved(self):
        session = opening(1)
        alternatives = choices(2)
        before = identity(session)
        serial = call(session, alternatives)
        argv, modules, path, state, limits = tuple(sys.argv), set(sys.modules), tuple(sys.path), random.getstate(), sys.get_int_max_str_digits()
        with mock.patch.object(es, 'commit_session', side_effect=AssertionError('commit')):
            with ThreadPoolExecutor(max_workers=2) as executor:
                reports = list(executor.map(lambda _: call(session, alternatives), range(2)))
        self.assertEqual(reports, [serial, serial])
        self.assertEqual(identity(session), before)
        self.assertEqual((tuple(sys.argv), set(sys.modules), tuple(sys.path), random.getstate(), sys.get_int_max_str_digits()),
                         (argv, modules, path, state, limits))

    def test_immutable_records_and_fresh_payloads(self):
        session = opening()
        report = call(session)
        for record, attribute, value in ((report, 'base_turn', 4), (report.alternatives[0], 'label', 'change'),
                                         (report.alternatives[0].receipts[0], 'resulting_slot_value', 0),
                                         (report.alternatives[0].receipts[0].receipt, 'threshold', 800)):
            with self.assertRaises(FrozenInstanceError): setattr(record, attribute, value)
        original = preview_json(report)
        payload = report.as_payload()
        payload['alternatives'][0]['receipts'][0]['receipt']['threshold'] = 800
        payload['alternatives'].clear()
        self.assertEqual(preview_json(report), original)
        self.assertEqual(preview_json(call(session)), original)
        self.assertNotIn('generation', report.as_payload())
        self.assertNotIn('checkpoint', original)
        self.assertNotIn('participants', original)
        self.assertNotIn('voter', original)
        self.assertFalse(report.as_payload()['committed'])

    def test_exact_enable_and_off_poison_without_kernel_policy_or_iteration(self):
        class Poison:
            def __getattribute__(self, name): raise AssertionError('poison inspected')
            def __iter__(self): raise AssertionError('poison consumed')
        for enabled in (1, 0, None, 'yes'):
            with self.assertRaises(PreviewError): preview_candidates(enabled=enabled)
        with ExitStack() as stack:
            for owner, name in ((mm, 'advance'), (es, 'encode_session'), (es, 'apply_memome_batch'),
                                (es, 'load_session'), (es, 'read_regular_file_bytes')):
                stack.enter_context(mock.patch.object(owner, name, side_effect=AssertionError(name)))
            self.assertEqual(preview_candidates(session=Poison(), transport=Poison(),
                alternatives=Poison(), max_alternatives=Poison()), PreviewReport())

    def test_import_off_and_enabled_persistence_rng_guards(self):
        session = opening()
        driver = driver_module()
        with ExitStack() as stack:
            for owner, name in ((es, 'commit_session'), (os, 'open'), (os, 'replace'), (os, 'unlink'),
                                (Path, 'open'), (random, 'random'), (random, 'seed')):
                stack.enter_context(mock.patch.object(owner, name, side_effect=AssertionError(name)))
            call(session)
            for owner, name in ((mm, 'advance'), (mm, 'checkpoint_json'), (es, 'encode_session'),
                                (es, 'load_session'), (es, 'read_regular_file_bytes'), (runpy, 'run_path')):
                stack.enter_context(mock.patch.object(owner, name, side_effect=AssertionError(name)))
            spec = importlib.util.spec_from_file_location('chronicler.memome_preview_import_guard', MODULE)
            module = importlib.util.module_from_spec(spec)
            stack.enter_context(mock.patch.dict(sys.modules, {spec.name: module}))
            spec.loader.exec_module(module)
            self.assertFalse(module.preview_candidates().enabled)
            out, err = io.StringIO(), io.StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                self.assertEqual(driver.main(['--path', '/nonexistent', '--max-alternatives', 'poison', '--format', 'bad']), 0)
            self.assertEqual((out.getvalue(), err.getvalue()), (preview_json(PreviewReport()), ''))

    def test_containers_labels_and_cap_before_element_or_public_validation(self):
        session = opening()
        for kwargs in ({'alternatives': list(choices())}, {'alternatives': iter(choices())},
                       {'alternatives': ()}, {'max_alternatives': True}, {'max_alternatives': 0},
                       {'max_alternatives': 2.0}, {'transport': None}, {'session': object()}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError): call(session, **kwargs)
        with (mock.patch.object(es, 'encode_session', side_effect=AssertionError('encode')),
              self.assertRaisesRegex(PreviewError, 'alternative count')):
            call(session, (object(), object(), object()))
        for label in ('', ' ', 'x'*129, None, 3):
            with self.subTest(label=label), self.assertRaises(PreviewError):
                call(session, (Alternative(label, choices()[0].batch),))
        with self.assertRaisesRegex(PreviewError, 'duplicate label'): call(session, (choices()[0], choices()[0]))
        with self.assertRaisesRegex(PreviewError, 'exact Alternative'): call(session, (object(),))

    def test_reject_recipient_slot_draw_idset_changes_without_partial_report(self):
        session = opening()
        good = choices()[0]
        proposal = good.batch.proposals[0]
        variants = (replace(proposal, recipient='basic-0', candidate=0), replace(proposal, slot=2),
                    replace(proposal, draw=200), replace(proposal, proposal_id='other'))
        before = identity(session)
        for changed in variants:
            with self.subTest(changed=changed), self.assertRaisesRegex(PreviewError, "alternative 'bad'.*only in candidate"):
                call(session, (good, Alternative('bad', mm.Batch(1, (changed,)))))
            self.assertEqual(identity(session), before)
        with self.assertRaisesRegex(PreviewError, "alternative 'bad'.*only in candidate"):
            call(session, (good, Alternative('bad', mm.Batch(1, ()))))

    def test_malformed_historical_gap_missing_values_and_duplicate_recipients(self):
        session = opening()
        good = choices()[0]
        proposal = good.batch.proposals[0]
        bad_batches = (mm.Batch(0, ()), mm.Batch(2, ()), mm.Batch(True, ()),
                       mm.Batch(1, [proposal]), mm.Batch(1, (object(),)),
                       mm.Batch(1, (replace(proposal, draw=True),)),
                       mm.Batch(1, (replace(proposal, candidate=True),)),
                       mm.Batch(1, (replace(proposal, slot=True),)),
                       mm.Batch(1, (replace(proposal, draw=-1),)),
                       mm.Batch(1, (replace(proposal, draw=1000),)),
                       mm.Batch(1, (proposal, replace(proposal, proposal_id='second'))),
                       mm.Batch(1, (proposal, proposal)), object())
        before = identity(session)
        for batch in bad_batches:
            with self.subTest(batch=batch), self.assertRaisesRegex(PreviewError, "alternative 'bad'"):
                call(session, (good, Alternative('bad', batch)))
            self.assertEqual(identity(session), before)

    def test_committed_ids_replay_history_and_campaign_refused(self):
        session = opening(2)
        before = identity(session)
        for batch in (session.batches[0], mm.Batch(3, (mm.Proposal('minority', 'basic-1', 1, 0, 199),))):
            with self.assertRaisesRegex(PreviewError, "alternative 'historical'"):
                call(session, (Alternative('historical', batch),))
            self.assertEqual(identity(session), before)
        campaign_demo = runpy.run_path(str(ROOT/'scripts/campaign_logistics_demo.py'))
        policy, topology = campaign_demo['illustrative_policy'](), campaign_demo['fixture_topology']()
        state = campaign_demo['fixture_session'](policy, topology).state
        campaign = es.create_campaign_session(policy=policy, topology=topology,
            campaign_id=state.campaign_id, turn=0, staging=state.staging, target=state.target,
            soldiers=state.soldiers, stocks=state.stocks)
        with self.assertRaisesRegex(PreviewError, 'MemomeSession'): call(campaign)

    def test_complete_opening_and_hypothetical_history_domain_validation(self):
        session = opening(1)
        tick = session.ledger.history[0]
        receipts = (replace(tick.receipts[0], threshold=tick.receipts[0].threshold+1),) + tick.receipts[1:]
        tampered = replace(session, ledger=replace(session.ledger, history=(replace(tick, receipts=receipts),)))
        with self.assertRaises(ValueError): call(tampered, choices(2))
        bounded_history = opening(3)
        for turn in (4, 5):
            bounded_history = es.apply_memome_batch(bounded_history, mm.Batch(turn, ())).session
        with self.assertRaisesRegex(PreviewError, "alternative 'candidate 3'.*history"):
            call(bounded_history, choices(6), transport=replace(es.documented_transport_policy(), max_history=5))
        for transport in (replace(es.documented_transport_policy(), max_bytes=1),
                          replace(es.documented_transport_policy(), max_records=1),
                          replace(es.documented_transport_policy(), max_int_bits=1),
                          replace(es.documented_transport_policy(), max_bytes=True)):
            with self.subTest(transport=transport), self.assertRaises(ValueError): call(transport=transport)
        opening_bytes = es.encode_envelope_text(es.encode_session(opening(), transport=es.documented_transport_policy(), generation=1), es.documented_transport_policy())
        transport = replace(es.documented_transport_policy(), max_bytes=len(opening_bytes)+1)
        many = tuple(Alternative('label-'+str(i), choices()[0].batch) for i in range(100))
        self.assertGreater(len(document(many)), transport.max_bytes)
        with self.assertRaisesRegex(ValueError, 'alternatives.*byte'):
            call(alternatives=many, max_alternatives=100, transport=transport)

    def test_exact_large_integer_weights_and_render_failure_no_limit_changes(self):
        people, _ = DEMO['unit_tables']()
        weighted = tuple(replace(p, prestige=1<<4000) if p.group=='basic' else p for p in people)
        session = es.create_memome_session(policy=DEMO['illustrative_policy'](), genesis_turn=0, participants=weighted)
        limit = sys.get_int_max_str_digits()
        report = call(session)
        receipt = report.alternatives[0].receipts[0].receipt
        self.assertEqual((receipt.candidate_weight, receipt.electorate_weight, receipt.threshold),
                         (1<<4000, 3*(1<<4000), 200))
        self.assertIs(type(json.loads(preview_json(report))['alternatives'][0]['receipts'][0]['receipt']['candidate_weight']), int)
        original_json = preview._json
        def rendering(payload):
            if type(payload) is dict and 'receipts' in payload:
                raise ValueError('injected unsupported integer rendering')
            return original_json(payload)
        before = identity(session)
        with mock.patch.object(preview, '_json', side_effect=rendering), self.assertRaisesRegex(PreviewError, "alternative 'candidate 3'.*rendering"):
            call(session)
        self.assertEqual(identity(session), before)
        self.assertEqual(sys.get_int_max_str_digits(), limit)

    def test_static_import_surface_no_private_codec_or_other_preview_dependency(self):
        for path in (MODULE, DRIVER):
            tree = ast.parse(path.read_text())
            imports = [node for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom))]
            for node in imports:
                names = ([node.module or ''] if isinstance(node, ast.ImportFrom) else [item.name for item in node.names])
                self.assertFalse(any(any(word in name for word in ('snapshot', 'campaign_order_preview', 'session_diagnostics', 'simulation')) for name in names))
                if isinstance(node, ast.ImportFrom) and (node.module or '').startswith('chronicler'):
                    self.assertFalse(any(item.name.startswith('_') for item in node.names))


class CliTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.folder = Path(temporary.name)
        self.session = opening()
        self.transport = es.documented_transport_policy()
        self.path, self.policy, self.alternatives = (self.folder/name for name in ('memome.json', 'transport.json', 'choices.json'))
        first = es.commit_session(self.path, self.session, transport=self.transport,
                                  expected_generation=None, expected_digest=None)
        es.commit_session(self.path, self.session, transport=self.transport,
                          expected_generation=first.generation, expected_digest=first.digest)
        self.policy.write_bytes(canonical(asdict(self.transport)))
        self.alternatives.write_bytes(document(choices()))
        self.arguments = ['--enable', '--path', str(self.path), '--transport', str(self.policy),
                          '--alternatives', str(self.alternatives), '--max-alternatives', '2', '--format', 'json']

    def inventory(self):
        return {p.name: (p.read_bytes(), hashlib.sha256(p.read_bytes()).hexdigest(),
                         p.stat().st_mtime_ns, p.stat().st_mode) for p in self.folder.iterdir()}

    def process(self, arguments=None, seed=0):
        env = dict(os.environ, PYTHONHASHSEED=str(seed), PYTHONDONTWRITEBYTECODE='1')
        return subprocess.run([sys.executable, '-B', str(DRIVER),
            *(self.arguments if arguments is None else arguments)], capture_output=True, env=env, timeout=15)

    def test_actual_cli_complete_observation_input_bytes_mtimes_and_inventory(self):
        before = self.inventory()
        result = self.process()
        self.assertEqual((result.returncode, result.stderr), (0, b''))
        payload = json.loads(result.stdout)
        observation = payload.pop('cli_observation')
        self.assertEqual((observation['path'], observation['generation'], observation['turn'], observation['file_digest']),
                         (str(self.path), 2, 0, before[self.path.name][1]))
        self.assertFalse(observation['submission_token'])
        self.assertEqual(payload, json.loads(preview_json(call(self.session))))
        self.assertEqual(self.inventory(), before)

    def test_actual_seed_0_42_101_all_streams_exits_and_inputs_success_failure_empty_off(self):
        valid = self.alternatives.read_bytes()
        cases = [('success', valid, self.arguments, 0),
                 ('invalid', b'{"contract":true,"alternatives":[]}', self.arguments, 3),
                 ('empty', document((Alternative('empty', mm.Batch(1, ())),)), self.arguments, 0),
                 ('off', valid, ['--path', '/nonexistent', '--max-alternatives', 'bad', '--format', 'bad'], 0)]
        for name, data, arguments, exit_code in cases:
            self.alternatives.write_bytes(data)
            before = self.inventory()
            results = [self.process(arguments, seed) for seed in (0, 42, 101)]
            with self.subTest(case=name):
                self.assertEqual([(r.returncode, r.stdout, r.stderr) for r in results],
                                 [(exit_code, results[0].stdout, results[0].stderr)] * 3)
                self.assertEqual(self.inventory(), before)
                if exit_code==3: self.assertEqual(results[0].stdout, b'')
                else: self.assertEqual(results[0].stderr, b'')

    def test_enabled_parser_errors_are_json_three_and_off_help_short_circuit(self):
        before = self.inventory()
        for arguments in (['--enable', '--max-alternatives', 'garbage'], ['--enable', '--format', 'invalid'],
                          ['--enable', '--path'], ['--enable', '--unknown'], ['--enable']):
            result = self.process(arguments)
            self.assertEqual((result.returncode, result.stdout), (3, b''))
            self.assertEqual(set(json.loads(result.stderr)), {'error', 'detail'})
            self.assertNotIn(b'usage:', result.stderr)
        result = self.process(['--max-alternatives', 'bad', '--path', '/missing', '--help'])
        self.assertEqual((result.returncode, result.stderr), (0, b''))
        self.assertIn(b'--enable', result.stdout)
        result = self.process(['--max-alternatives', 'bad', '--path', '/missing'])
        self.assertEqual((result.returncode, result.stderr, result.stdout), (0, b'', preview_json(PreviewReport()).encode()))
        self.assertEqual(self.inventory(), before)

    def test_valid_syntax_invalid_document_no_partial_stdout_or_input_mutation(self):
        valid = json.loads(self.alternatives.read_bytes())
        documents = [b'{"contract":1,"contract":2,"alternatives":[]}',
                     b'{"contract":NaN,"alternatives":[]}', b'{"contract":1.1,"alternatives":[]}',
                     canonical({**valid, 'unknown': 1}), canonical({'contract': CONTRACT, 'alternatives': {}})]
        for path, value in ((('batch', 'turn'), True), (('batch', 'turn'), 2),
                            (('batch', 'proposals'), []), (('label',), 'candidate 3')):
            bad = json.loads(self.alternatives.read_bytes())
            target = bad['alternatives'][1]
            for key in path[:-1]: target = target[key]
            target[path[-1]] = value
            documents.append(canonical(bad))
        for data in documents:
            self.alternatives.write_bytes(data)
            before = self.inventory()
            result = self.process()
            with self.subTest(data=data):
                self.assertEqual((result.returncode, result.stdout), (3, b''))
                self.assertIn('error', json.loads(result.stderr))
                self.assertEqual(self.inventory(), before)

    def test_count_before_record_decoding_and_exact_closed_records(self):
        driver = driver_module()
        with (mock.patch.object(es, 'memome_batch_from_payload', side_effect=AssertionError('decode')),
              self.assertRaisesRegex(PreviewError, 'alternative count')):
            driver._alternatives(canonical({'contract': CONTRACT, 'alternatives': [None]*3}), self.transport, 2)
        for records in ([{'label':'x', 'batch':{}, 'extra':0}], [None]):
            with self.assertRaisesRegex(PreviewError, 'exactly label and batch'):
                driver._alternatives(canonical({'contract':CONTRACT, 'alternatives':records}), self.transport, 2)

    def test_cli_uses_public_bounded_reader_for_all_three_inputs(self):
        driver = driver_module()
        read = es.read_regular_file_bytes
        calls = []
        def traced(path, **kwargs):
            calls.append((Path(path), kwargs['max_bytes']))
            return read(path, **kwargs)
        out, err = io.StringIO(), io.StringIO()
        before = self.inventory()
        with mock.patch.object(es, 'read_regular_file_bytes', side_effect=traced), redirect_stdout(out), redirect_stderr(err):
            self.assertEqual(driver.main(self.arguments), 0)
        self.assertEqual(calls, [(self.policy,4096), (self.alternatives,self.transport.max_bytes), (self.path,self.transport.max_bytes)])
        self.assertEqual(err.getvalue(), '')
        self.assertEqual(self.inventory(), before)
        self.policy.write_bytes(b' '*4097)
        before = self.inventory()
        result = self.process()
        self.assertEqual((result.returncode, result.stdout), (3,b''))
        self.assertEqual(self.inventory(), before)
        self.policy.write_bytes(canonical(asdict(self.transport)))
        self.alternatives.write_bytes(b' '*(self.transport.max_bytes+1))
        before = self.inventory()
        result = self.process()
        self.assertEqual((result.returncode, result.stdout), (3,b''))
        self.assertEqual(self.inventory(), before)

    def test_public_reader_refuses_fifo_and_directory_without_blocking(self):
        directory = self.folder/'not-file'
        directory.mkdir()
        fifo = self.folder/'fifo'
        os.mkfifo(fifo)
        for target in (directory, fifo):
            for flag in ('--path','--transport','--alternatives'):
                arguments = self.arguments.copy()
                arguments[arguments.index(flag)+1] = str(target)
                result = self.process(arguments)
                with self.subTest(target=target, flag=flag):
                    self.assertEqual((result.returncode,result.stdout),(3,b''))
                    self.assertIn('error', json.loads(result.stderr))

    def test_one_loaded_read_then_replacement_keeps_observed_base_and_complete_rows(self):
        driver = driver_module()
        replacement = self.folder/'replacement.json'
        advanced = es.apply_memome_batch(self.session, choices()[0].batch).session
        es.commit_session(replacement, advanced, transport=self.transport,
                          expected_generation=None, expected_digest=None)
        original_bytes, new_bytes = self.path.read_bytes(), replacement.read_bytes()
        actual_load, actual_read = es.load_session, es.read_regular_file_bytes
        loaded, reads = [], []
        def replace_after_load(path, **kwargs):
            observed = actual_load(path, **kwargs)
            loaded.append(observed)
            os.replace(replacement,self.path)
            return observed
        def traced(path, **kwargs):
            reads.append(Path(path))
            return actual_read(path, **kwargs)
        out,err = io.StringIO(),io.StringIO()
        with mock.patch.object(es,'load_session',side_effect=replace_after_load), mock.patch.object(es,'read_regular_file_bytes',side_effect=traced), redirect_stdout(out),redirect_stderr(err):
            self.assertEqual(driver.main(self.arguments),0)
        payload=json.loads(out.getvalue())
        self.assertEqual((len(loaded),reads.count(self.path),err.getvalue()),(1,1,''))
        self.assertEqual((payload['cli_observation']['file_digest'],payload['cli_observation']['generation'],payload['base_turn']),
                         (hashlib.sha256(original_bytes).hexdigest(),2,0))
        self.assertEqual(self.path.read_bytes(),new_bytes)
        self.assertNotEqual(hashlib.sha256(new_bytes).hexdigest(),payload['cli_observation']['file_digest'])
        self.assertEqual(payload['alternatives'],json.loads(preview_json(call(self.session)))['alternatives'])
        self.assertIn('currentness',payload['cli_observation']['scope'])
        self.assertFalse(payload['cli_observation']['submission_token'])

    def test_text_is_complete_illustrative_report_and_render_failure_atomic(self):
        result=self.process(self.arguments+['--format','text'])
        self.assertEqual((result.returncode,result.stderr),(0,b''))
        self.assertIn(b'illustrative=true',result.stdout)
        self.assertIn(b'"candidate_weight":1',result.stdout)
        self.assertIn(b'"resulting_slot_value":3',result.stdout)
        self.assertIn(b'CLI observation:',result.stdout)
        driver=driver_module()
        before=self.inventory()
        out,err=io.StringIO(),io.StringIO()
        with mock.patch.object(driver,'preview_text',side_effect=ValueError('unsupported rendering')), redirect_stdout(out),redirect_stderr(err):
            self.assertEqual(driver.main(self.arguments+['--format','text']),3)
        self.assertEqual(out.getvalue(),'')
        self.assertIn('rendering',json.loads(err.getvalue())['detail'])
        self.assertEqual(self.inventory(),before)


if __name__=='__main__': unittest.main()
