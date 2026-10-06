"""B intake wiring and the published preview-to-saved-receipt walkthrough, offline."""
from contextlib import ExitStack, redirect_stderr, redirect_stdout
from dataclasses import replace
import builtins
import hashlib
import io
import json
import os
from pathlib import Path
import random
import re
import runpy
import shlex
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from chronicler import campaign_logistics as cl
from chronicler import experiment_sessions as es
from chronicler import memome_experiment as mm
from chronicler import session_operations as operations
import test_session_operations as existing

ROOT = Path(__file__).resolve().parents[1]
DRIVER = ROOT / 'scripts/session_operation.py'
DOC = ROOT / 'docs/experiments/session-operations.md'
INTAKE_RECORDS = []


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':')).encode()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def inventory(folder):
    result = {}
    for path in sorted(folder.iterdir()):
        meta = path.lstat()
        row = {'mode': meta.st_mode, 'mtime_ns': meta.st_mtime_ns,
               'kind': 'regular' if stat.S_ISREG(meta.st_mode) else
                       'fifo' if stat.S_ISFIFO(meta.st_mode) else 'directory'}
        if stat.S_ISREG(meta.st_mode):
            raw = path.read_bytes()
            row.update(bytes_hex=raw.hex(), sha256=digest(raw))
        result[path.name] = row
    return result


def persist(name, value):
    folder = Path(os.environ.get('R007_EVIDENCE_DIR', os.environ.get('TMPDIR', tempfile.gettempdir())))
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name).write_text(json.dumps(value, sort_keys=True, indent=2) + '\n')


def forbid_work(stack, *, policy=False):
    for module, names in ((operations, ('apply_operation', 'reconcile_operation')),
                          (es, ('load_session', 'commit_session', '_exclusive_lock',
                                'submission_from_bytes', 'memome_batch_from_payload')),
                          (mm, ('advance',)), (cl, ('advance',))):
        for name in names:
            stack.enter_context(mock.patch.object(module, name, side_effect=AssertionError(
                'intake refusal must not call ' + name)))
    if policy:
        stack.enter_context(mock.patch.object(es, 'transport_policy_from_text',
                                              side_effect=AssertionError('policy must not decode')))


def captured_main(driver, arguments):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        status = driver['main'](arguments)
    return status, out.getvalue().encode(), err.getvalue().encode()


def intake_arguments(folder, command, stage):
    arguments = ['--enable', command, '--path', str(folder / 'session.json'),
                 '--transport', str(folder / 'transport.json')]
    return arguments + (['--submission', str(folder / 'submission.json')] if command == 'apply'
                        else ['--expectation-json', '{}'])


def intake_child(folder, command, stage, swap):
    """The actual CLI routing, with deterministic pre-open substitution and no writer."""
    driver = runpy.run_path(str(DRIVER))
    path = folder / ('transport.json' if stage == 'transport' else 'submission.json')
    original = os.open
    substituted = False

    def opened(target, *args, **kwargs):
        nonlocal substituted
        if swap and Path(target) == path:
            if substituted:
                raise AssertionError('input must never reopen')
            substituted = True
            path.rename(path.with_suffix('.displaced'))
            os.mkfifo(path)
        return original(target, *args, **kwargs)

    with ExitStack() as stack:
        forbid_work(stack, policy=stage == 'transport')
        stack.enter_context(mock.patch.object(os, 'open', opened))
        return driver['main'](intake_arguments(folder, command, stage))


class OperatorIntakeTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.folder = Path(temporary.name)
        self.target = self.folder / 'session.json'
        self.transport = es.documented_transport_policy()
        self.session = existing.fixture_session('m68a')
        es.commit_session(self.target, self.session, transport=self.transport,
                          expected_generation=None, expected_digest=None)
        (self.folder / 'transport.json').write_bytes(encoded(self.transport.as_payload()))
        (self.folder / 'submission.json').write_bytes(existing.submission(existing.first_input(self.session)))
        self.driver = runpy.run_path(str(DRIVER))

    def record(self, case, arguments, result, before, after):
        status, out, err = result
        INTAKE_RECORDS.append({'case': case, 'argv': arguments, 'exit_code': status,
                               'stdout': out.decode(), 'stderr': err.decode(),
                               'stdout_hex': out.hex(), 'stderr_hex': err.hex(),
                               'stdout_sha256': digest(out), 'stderr_sha256': digest(err),
                               'before_files': before, 'after_files': after})
        persist('intake-evidence.json', INTAKE_RECORDS)

    def rejected(self, result, kind):
        status, out, err = result
        self.assertEqual((status, out), (3, b''))
        payload = json.loads(err)
        self.assertEqual(payload['status'], 'rejected')
        self.assertEqual(payload['error']['error_type'], kind)
        self.assertIsNone(payload['base'])
        self.assertIsNone(payload['intended'])
        self.assertIsNone(payload['expectation'])
        return payload

    def test_consumer_delegates_exact_public_reader_parameters(self):
        with mock.patch.object(es, 'read_regular_file_bytes', return_value=b'{}') as reader:
            self.assertEqual(self.driver['_read_bounded']('input.json', 64, 'submission'), b'{}')
        reader.assert_called_once_with('input.json', max_bytes=64, label='submission')
        self.assertIs(self.driver['_read_bounded'].__globals__['es'].read_regular_file_bytes,
                      es.read_regular_file_bytes)

    def test_fifo_transport_submission_and_reconcile_and_preopen_replacements_refuse(self):
        for command, stage in (('apply', 'transport'), ('apply', 'submission'), ('reconcile', 'transport')):
            for swap in (False, True):
                with self.subTest(command=command, stage=stage, swap=swap):
                    path = self.folder / (stage + '.json')
                    displaced = path.with_suffix('.displaced')
                    displaced.unlink(missing_ok=True)
                    path.unlink(missing_ok=True)
                    original = encoded(self.transport.as_payload()) if stage == 'transport' else existing.submission(
                        existing.first_input(self.session))
                    if swap:
                        path.write_bytes(original)
                    else:
                        os.mkfifo(path)
                    before = inventory(self.folder)
                    argv = [sys.executable, '-B', str(Path(__file__).resolve()), '--intake-child',
                            str(self.folder), command, stage, str(int(swap))]
                    child = subprocess.run(argv, capture_output=True, timeout=3)
                    result = child.returncode, child.stdout, child.stderr
                    self.rejected(result, 'SessionError')
                    after = inventory(self.folder)
                    self.record(f'{command}-{stage}-fifo-swap{int(swap)}', argv, result, before, after)
                    self.assertEqual(after['session.json'], before['session.json'])
                    self.assertEqual(after['.session.json.lock'], before['.session.json.lock'])
                    if swap:
                        expected = dict(before)
                        expected.pop(path.name)
                        expected[displaced.name] = before[path.name]
                        self.assertEqual({k: v for k, v in after.items() if k != path.name}, expected)
                        self.assertEqual(after[path.name]['kind'], 'fifo')
                        self.assertEqual(displaced.read_bytes(), original)
                    else:
                        self.assertEqual(after, before)
                    # Restore explicit regular inputs for the next independent case.
                    path.unlink()
                    if swap:
                        displaced.rename(path)
                    else:
                        path.write_bytes(original)

    def test_actual_growth_and_stale_metadata_request_exact_caps_before_work(self):
        for stage, limit in (('transport', 4096), ('submission', 64)):
            for grow in (False, True):
                with self.subTest(stage=stage, grow=grow):
                    path = self.folder / (stage + '.json')
                    if stage == 'submission':
                        (self.folder / 'transport.json').write_bytes(encoded(replace(
                            self.transport, max_bytes=64).as_payload()))
                    path.write_bytes(b'{}' if grow else b'x' * (limit + 1))
                    before = inventory(self.folder)
                    original_open = builtins.open
                    requests, handles = [], []

                    class Tracked:
                        def __init__(inner, descriptor, mode, *args, **kwargs):
                            inner.handle = original_open(descriptor, mode, *args, **kwargs)
                            handles.append(inner.handle)
                            info = os.fstat(descriptor)
                            inner.selected = (info.st_dev, info.st_ino) == (path.stat().st_dev, path.stat().st_ino)

                        def __enter__(inner): return inner
                        def __exit__(inner, *args): return inner.handle.__exit__(*args)
                        def fileno(inner): return inner.handle.fileno()
                        def read(inner, size):
                            if inner.selected:
                                requests.append(size)
                                if grow:
                                    with path.open('ab') as writer:
                                        writer.write(b'x' * (limit + 1))
                            return inner.handle.read(size)

                    # Pathname size is deliberately stale, while inode identity stays real.
                    real_stat = Path.stat
                    stale = path.stat()
                    values = list(stale); values[6] = 2
                    false_size = os.stat_result(values)
                    def misleading(target, *args, **kwargs):
                        return false_size if target == path else real_stat(target, *args, **kwargs)

                    with ExitStack() as stack:
                        forbid_work(stack, policy=stage == 'transport')
                        stack.enter_context(mock.patch.object(Path, 'stat', misleading))
                        stack.enter_context(mock.patch.object(builtins, 'open', side_effect=Tracked))
                        result = captured_main(self.driver, intake_arguments(self.folder, 'apply', stage))
                    self.rejected(result, 'TransportDomainError')
                    after = inventory(self.folder)
                    self.record(f'{stage}-limit{limit}-growth{int(grow)}', intake_arguments(
                        self.folder, 'apply', stage), result, before, after)
                    self.assertEqual(requests, [limit + 1])
                    self.assertTrue(all(handle.closed for handle in handles))
                    self.assertEqual(after['session.json'], before['session.json'])
                    self.assertEqual(after['.session.json.lock'], before['.session.json.lock'])
                    self.assertEqual(set(after), set(before))
                    self.assertEqual({k: v for k, v in after.items() if k != path.name},
                                     {k: v for k, v in before.items() if k != path.name})
                    if grow:
                        self.assertEqual(path.read_bytes(), b'{}' + b'x' * (limit + 1))
                    else:
                        self.assertEqual(after, before)

    def test_missing_directory_and_read_errors_preserve_saved_files_and_close(self):
        for stage in ('transport', 'submission'):
            for failure in ('missing', 'directory', 'read'):
                with self.subTest(stage=stage, failure=failure):
                    (self.folder / 'transport.json').write_bytes(encoded(self.transport.as_payload()))
                    (self.folder / 'submission.json').write_bytes(b'{}')
                    path = self.folder / (stage + '.json')
                    if failure != 'read':
                        path.unlink()
                        if failure == 'directory': path.mkdir()
                    before = inventory(self.folder)
                    handles = []
                    original = builtins.open
                    error = OSError('injected ordinary input read failure')
                    selected_identity = None if failure != 'read' else (path.stat().st_dev, path.stat().st_ino)
                    class Tracked:
                        def __init__(inner, descriptor, mode, *args, **kwargs):
                            inner.handle = original(descriptor, mode, *args, **kwargs)
                            handles.append(inner.handle)
                            info = os.fstat(descriptor)
                            inner.selected = (info.st_dev, info.st_ino) == selected_identity
                        def __enter__(inner): return inner
                        def __exit__(inner, *args): return inner.handle.__exit__(*args)
                        def fileno(inner): return inner.handle.fileno()
                        def read(inner, size):
                            if inner.selected: raise error
                            return inner.handle.read(size)
                    with ExitStack() as stack:
                        forbid_work(stack, policy=stage == 'transport')
                        stack.enter_context(mock.patch.object(builtins, 'open', side_effect=Tracked))
                        result = captured_main(self.driver, intake_arguments(self.folder, 'apply', stage))
                    self.rejected(result, {'missing': 'FileNotFoundError', 'directory': 'IsADirectoryError',
                                           'read': 'OSError'}[failure])
                    after = inventory(self.folder)
                    self.record(f'{stage}-{failure}', intake_arguments(self.folder, 'apply', stage), result, before, after)
                    self.assertEqual(after, before)
                    self.assertTrue(all(handle.closed for handle in handles))
                    if failure == 'directory': path.rmdir()
                    elif failure == 'read':
                        with mock.patch.object(builtins, 'open', side_effect=Tracked):
                            with self.assertRaises(OSError) as caught:
                                self.driver['_read_bounded'](str(path), 4096, stage)
                        self.assertIs(caught.exception, error)
                        self.assertTrue(all(handle.closed for handle in handles))

    def test_postopen_submission_replacement_uses_one_opened_version_without_retry(self):
        path = self.folder / 'submission.json'
        path.write_bytes(b'{')
        newer = self.folder / 'replacement.json'
        newer.write_bytes(existing.submission(existing.first_input(self.session)))
        before = inventory(self.folder)
        original = os.open
        calls = []
        def opened(target, *args, **kwargs):
            descriptor = original(target, *args, **kwargs)
            if Path(target) == path:
                calls.append(str(target))
                path.rename(self.folder / 'submission.displaced')
                newer.rename(path)
            return descriptor
        with ExitStack() as stack:
            stack.enter_context(mock.patch.object(os, 'open', opened))
            loader = stack.enter_context(mock.patch.object(es, 'load_session', wraps=es.load_session))
            for module, names in ((es, ('commit_session', '_exclusive_lock')), (mm, ('advance',)), (cl, ('advance',))):
                for name in names:
                    stack.enter_context(mock.patch.object(module, name, side_effect=AssertionError('no mutation')))
            result = captured_main(self.driver, intake_arguments(self.folder, 'apply', 'submission'))
        self.assertEqual((result[0], result[1]), (3, b''))
        payload = json.loads(result[2])
        self.assertEqual((payload['status'], payload['error']['error_type']), ('rejected', 'SessionError'))
        self.assertIsNotNone(payload['base'])
        self.assertIsNone(payload['intended'])
        self.assertEqual(calls, [str(path)])
        self.assertEqual(loader.call_count, 1)
        after = inventory(self.folder)
        self.record('postopen-malformed-observed-submission', intake_arguments(self.folder, 'apply', 'submission'),
                    result, before, after)
        self.assertEqual(after['session.json'], before['session.json'])
        self.assertEqual(after['.session.json.lock'], before['.session.json.lock'])
        expected = dict(before)
        expected['submission.displaced'] = expected.pop('submission.json')
        expected['submission.json'] = expected.pop('replacement.json')
        self.assertEqual(after, expected)

    def test_off_help_and_enabled_syntax_do_no_optional_work_or_global_mutation(self):
        fifo = self.folder / 'optional.fifo'; os.mkfifo(fifo)
        before = inventory(self.folder)
        globals_before = list(sys.argv), dict(os.environ), random.getstate()
        missing_args = ['apply', '--path', 'missing', '--transport', str(fifo), '--submission', 'missing']
        fifo_args = ['apply', '--path', str(self.target), '--transport', 'missing', '--submission', str(fifo)]
        with ExitStack() as stack:
            forbid_work(stack)
            stack.enter_context(mock.patch.object(es, 'read_regular_file_bytes', side_effect=AssertionError('no read')))
            stack.enter_context(mock.patch.object(os, 'open', side_effect=AssertionError('no open')))
            stack.enter_context(mock.patch.object(Path, 'open', side_effect=AssertionError('no open')))
            empty = captured_main(self.driver, [])
            missing = captured_main(self.driver, missing_args)
            fifo_off = captured_main(self.driver, fifo_args)
            help_result = captured_main(self.driver, ['--help'])
            out, err = io.StringIO(), io.StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                with self.assertRaises(SystemExit) as caught:
                    self.driver['main'](['--enable', 'apply', '--path', str(self.target),
                                          '--transport', str(fifo)])
        self.assertEqual(empty, missing)
        self.assertEqual(empty, fifo_off)
        self.assertEqual(empty[0], 0)
        self.assertEqual((help_result[0], help_result[2]), (0, b''))
        self.assertIn(b'usage:', help_result[1])
        self.assertEqual(caught.exception.code, 2)
        self.assertEqual(out.getvalue(), '')
        self.assertIn('usage:', err.getvalue())
        self.assertEqual((list(sys.argv), dict(os.environ), random.getstate()), globals_before)
        after = inventory(self.folder)
        self.assertEqual(after, before)
        for name, arguments, result in [('off-empty', [], empty), ('off-missing', missing_args, missing),
                                        ('off-fifo', fifo_args, fifo_off), ('help', ['--help'], help_result),
                                        ('syntax', ['--enable', 'apply', '--path', str(self.target),
                                                     '--transport', str(fifo)], (2, out.getvalue().encode(), err.getvalue().encode()))]:
            self.record(name, arguments, result, before, after)

    def test_original_bounded_request_gate_rejects_unbounded_reader_negative_control(self):
        actual_run_path = runpy.run_path
        unbounded_requests = []
        def loaded(path, *args, **kwargs):
            driver = actual_run_path(path, *args, **kwargs)
            if Path(path) == existing.DRIVER:
                def unbounded(target, limit, label):
                    unbounded_requests.append(str(target))
                    raw = Path(target).read_bytes()
                    if len(raw) > limit:
                        raise es.TransportDomainError('same cap refusal after an unbounded read')
                    return raw
                driver['_read_bounded'] = unbounded
            return driver
        case = existing.SessionOperationCliTests(
            'test_cli_file_read_request_uses_limit_plus_one_without_metadata_trust')
        result = unittest.TestResult()
        with mock.patch.object(existing.runpy, 'run_path', side_effect=loaded):
            case.run(result)
        self.assertEqual(result.testsRun, 1)
        self.assertEqual(len(result.errors), 0)
        self.assertEqual(len(result.failures), 1)
        self.assertTrue(unbounded_requests)
        self.assertIn('[] != [65]', result.failures[0][1])
        persist('negative-control.json', {'negative_control': 'Path.read_bytes followed by correct oversize rejection',
                                         'unbounded_calls': unbounded_requests,
                                         'tests_run': result.testsRun, 'failures': [text for _, text in result.failures],
                                         'errors': [text for _, text in result.errors],
                                         'unchanged_request_gate_detected_unbounded_read': True})


class PublishedOperatorWorkflowTests(unittest.TestCase):
    def test_published_commands_full_receipts_and_actual_post_files_at_both_seeds(self):
        steps = re.findall(r'<!-- r007-step: ([a-z-]+) -->\n```sh\n(.*?)\n```', DOC.read_text(), re.S)
        self.assertEqual([name for name, _ in steps], ['prepare', 'create', 'copy-opening', 'preview', 'select',
                                                      'apply', 'inspect', 'replay', 'inspect-replay', 'compare',
                                                      'invalid-prepare', 'invalid-refusal'])
        all_records = []
        no_write = {'preview', 'inspect', 'replay', 'inspect-replay', 'compare', 'invalid-refusal'}
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            for seed in ('0', '42'):
                folder = base / ('seed-' + seed); folder.mkdir()
                env = dict(os.environ, PYTHONHASHSEED=seed, PYTHON=sys.executable, CHECKOUT=str(ROOT),
                           PYTHONDONTWRITEBYTECODE='1')
                opening = None
                payloads = {}
                for name, block in steps:
                    lines = block.splitlines()
                    stdin = None
                    if " <<'PY'" in lines[0]:
                        self.assertEqual(lines[-1], 'PY')
                        head = lines[0].split(" <<'PY'")[0]
                        stdin = ('\n'.join(lines[1:-1]) + '\n').encode()
                    else:
                        head = block
                    argv = [word.replace('$PYTHON', sys.executable).replace('$CHECKOUT', str(ROOT))
                            for word in shlex.split(head)]
                    before = inventory(folder)
                    command = subprocess.run(argv, cwd=folder, env=env, input=stdin,
                                             capture_output=True, timeout=15)
                    after = inventory(folder)
                    expected_exit = 3 if name == 'invalid-refusal' else 0
                    self.assertEqual(command.returncode, expected_exit, command.stderr)
                    if expected_exit == 0: self.assertEqual(command.stderr, b'')
                    else: self.assertEqual(command.stdout, b'')
                    if name in no_write: self.assertEqual(after, before, name)
                    record = {'seed': seed, 'step': name, 'published_block': block, 'argv': argv,
                              'stdin_hex': None if stdin is None else stdin.hex(), 'exit_code': command.returncode,
                              'stdout': command.stdout.decode(), 'stderr': command.stderr.decode(),
                              'stdout_hex': command.stdout.hex(), 'stderr_hex': command.stderr.hex(),
                              'stdout_sha256': digest(command.stdout), 'stderr_sha256': digest(command.stderr),
                              'before_files': before, 'post_files': after}
                    all_records.append(record)
                    if command.stdout: payloads[name] = json.loads(command.stdout)
                    if name == 'create':
                        loaded = es.load_session(folder / 'memome.json', transport=es.documented_transport_policy())
                        self.assertEqual((loaded.generation, loaded.turn), (1, 0))
                        self.assertEqual(len(loaded.session.ledger.participants), 5)
                        opening = (folder / 'memome.json').read_bytes()
                    if 'opening.json' in after:
                        self.assertEqual(bytes.fromhex(after['opening.json']['bytes_hex']), opening)
                    if name == 'preview':
                        preview = payloads[name]
                        self.assertEqual((preview['cli_observation']['generation'], preview['cli_observation']['turn']), (1, 0))
                        self.assertEqual(preview['cli_observation']['file_digest'], digest(opening))
                        self.assertFalse(preview['cli_observation']['submission_token'])
                        rows = {row['label']: row for row in preview['alternatives']}
                        selected = rows['candidate 3']['receipts'][0]
                        expected = {'proposal_id': 'choice', 'recipient': 'basic-1', 'slot': 1, 'previous': 1,
                                    'candidate': 3, 'draw': 199, 'candidate_weight': 1,
                                    'electorate_weight': 3, 'threshold': 200, 'reason': 'accepted'}
                        self.assertEqual(selected, {'receipt': expected, 'previous_slot_value': 1, 'resulting_slot_value': 3})
                        absent = rows['candidate 0']['receipts'][0]
                        self.assertEqual(absent, {'receipt': dict(expected, candidate=0, candidate_weight=0,
                                                               threshold=0, reason='absent_candidate'),
                                                 'previous_slot_value': 1, 'resulting_slot_value': 1})
                    if name == 'select':
                        chosen = next(row['batch'] for row in json.loads((folder / 'choices.json').read_text())['alternatives']
                                      if row['label'] == 'candidate 3')
                        self.assertEqual(json.loads((folder / 'submission.json').read_bytes()), chosen)
                    if name == 'apply':
                        receipt = payloads[name]
                        self.assertEqual(receipt['status'], 'committed_durable')
                        self.assertEqual((receipt['base']['generation'], receipt['base']['turn']), (1, 0))
                        self.assertEqual((receipt['intended']['generation'], receipt['intended']['turn']), (2, 1))
                        self.assertEqual(receipt['base']['file_digest'], digest(opening))
                        self.assertEqual(receipt['intended']['file_digest'], after['memome.json']['sha256'])
                        loaded = es.load_session(folder / 'memome.json', transport=es.documented_transport_policy())
                        self.assertEqual(loaded.digest, receipt['intended']['file_digest'])
                        self.assertEqual(loaded.envelope.session_digest, receipt['intended']['session_digest'])
                        self.assertEqual(len(loaded.session.batches), 1)
                    if name == 'inspect':
                        inspection = payloads[name]
                        row = inspection['turns'][0]
                        self.assertTrue(row['available'])
                        self.assertEqual(row['memome']['batch'], rows['candidate 3']['admitted_batch'])
                        self.assertEqual(row['memome']['receipts'], [expected])
                        people = {person['agent_id']: person for person in row['memome']['participants_after']}
                        self.assertEqual(people['basic-1']['slots'][1], 3)
                        self.assertEqual(inspection['file_digest'], after['memome.json']['sha256'])
                        self.assertEqual((inspection['generation'], inspection['latest_turn']), (2, 1))
                    if name == 'replay':
                        self.assertEqual(payloads[name]['status'], 'replay_no_write')
                        self.assertIsNone(payloads[name]['intended'])
                        self.assertEqual((payloads[name]['base']['generation'], payloads[name]['base']['turn']), (2, 1))
                        loaded = es.load_session(folder / 'memome.json', transport=es.documented_transport_policy())
                        self.assertEqual((loaded.generation, loaded.turn, len(loaded.session.batches),
                                          len(loaded.session.ledger.history)), (2, 1, 1, 1))
                    if name == 'inspect-replay': self.assertEqual(payloads[name], payloads['inspect'])
                    if name == 'compare':
                        comparison = payloads[name]
                        self.assertEqual(comparison['relationship'], 'left_history_prefix')
                        self.assertEqual(comparison['shared_committed_turn_count'], 0)
                        self.assertIsNone(comparison['last_shared_committed_turn'])
                        self.assertEqual((comparison['left']['latest_turn'], comparison['right']['latest_turn']), (0, 1))
                        self.assertEqual(comparison['left']['file_digest'], after['opening.json']['sha256'])
                        self.assertEqual(comparison['right']['file_digest'], after['memome.json']['sha256'])
                    if name == 'invalid-refusal':
                        rejection = json.loads(command.stderr)
                        self.assertEqual((rejection['status'], rejection['error']['error_type']),
                                         ('rejected', 'TransportDomainError'))
                        self.assertIsNone(rejection['base']); self.assertIsNone(rejection['intended'])
            first, second = all_records[:len(steps)], all_records[len(steps):]
            for left, right in zip(first, second):
                self.assertEqual((left['argv'], left['stdin_hex'], left['exit_code'], left['stdout_hex'], left['stderr_hex']),
                                 (right['argv'], right['stdin_hex'], right['exit_code'], right['stdout_hex'], right['stderr_hex']))
                self.assertEqual({name: (row.get('bytes_hex'), row.get('sha256'), row['kind'])
                                  for name, row in left['post_files'].items()},
                                 {name: (row.get('bytes_hex'), row.get('sha256'), row['kind'])
                                  for name, row in right['post_files'].items()})
        persist('workflow-evidence.json', {'source_sha256': {str(path.relative_to(ROOT)): digest(path.read_bytes())
                for path in [DRIVER, DOC, Path(__file__), ROOT / 'tests/test_session_operations.py']},
                'quiescent_target_assumption': True, 'preview_is_submission_token': False,
                'all_corresponding_post_file_bytes_digests_equal': True, 'records': all_records})


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--intake-child':
        raise SystemExit(intake_child(Path(sys.argv[2]), sys.argv[3], sys.argv[4], bool(int(sys.argv[5]))))
    unittest.main()
