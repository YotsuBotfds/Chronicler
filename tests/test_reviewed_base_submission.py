"""Exact reviewed observations, real saved receipts and two independent race controls."""
from contextlib import ExitStack
from dataclasses import FrozenInstanceError, asdict, replace
import builtins
import json
import os
from pathlib import Path
import re
import runpy
import selectors
import shlex
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from chronicler import campaign_logistics as cl
from chronicler import experiment_sessions as es
from chronicler import session_operations as operations
import test_session_operations as existing
import test_operator_submission_workflow as r
import test_campaign_order_preview as p
import test_memome_candidate_preview as m

ROOT = Path(__file__).resolve().parents[1]
DRIVER = ROOT / 'scripts/session_operation.py'
DOC = ROOT / 'docs/experiments/session-operations.md'
RECORDS = {'q-observation-evidence.json': [], 'q-race-evidence.json': [],
           'q-negative-controls.json': [], 'q-command-evidence.json': []}
OWNED = ['src/chronicler/session_operations.py', 'scripts/session_operation.py',
         'tests/test_reviewed_base_submission.py', 'docs/experiments/session-operations.md']


def save(name, row):
    RECORDS[name].append(row)
    folder = Path(os.environ.get('Q009_EVIDENCE_DIR', os.environ.get('TMPDIR', tempfile.gettempdir())))
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name).write_text(json.dumps({'source_sha256': {s: r.digest((ROOT/s).read_bytes()) for s in OWNED},
                                         'records': RECORDS[name]}, sort_keys=True, indent=2) + '\n')


def attempt(path, transport, body, guard=None):
    try:
        return operations.apply_operation(path, transport=transport, submission=body, precondition=guard)
    except (ValueError, OSError) as error:
        return error.operation_receipt


def declaration(report, transport, kernel):
    observed = report['cli_observation']
    return operations.ApplyPrecondition(observed['path'], transport, kernel, es.KERNEL_CONTRACTS[kernel],
        operations.SessionIdentity(observed['generation'], observed['file_digest'],
                                   report['base_session_digest'], observed['turn']))


def preview(folder, kernel, turn=None):
    transport = es.documented_transport_policy()
    loaded = es.load_session(folder/'session.json', transport=transport)
    alternatives = p.choices(loaded.session) if kernel == 'm60a' else m.choices(loaded.turn + 1 if turn is None else turn)
    if kernel == 'm68a' and loaded.turn > 0:
        alternatives=tuple(replace(a,batch=replace(a.batch,proposals=tuple(
            replace(proposal,proposal_id=f'choice-{loaded.turn+1}') for proposal in a.batch.proposals))) for a in alternatives)
    (folder/'choices.json').write_bytes(p.document(alternatives) if kernel == 'm60a' else m.document(alternatives))
    argv = [sys.executable, '-B', str(ROOT / ('scripts/campaign_order_preview.py' if kernel == 'm60a'
                                             else 'scripts/memome_candidate_preview.py')),
            '--enable', '--path', str(folder/'session.json'), '--transport', str(folder/'transport.json'),
            '--alternatives', str(folder/'choices.json'), '--max-alternatives', '2', '--format', 'json']
    before = r.inventory(folder)
    child = subprocess.run(argv, capture_output=True, timeout=10)
    if child.returncode != 0 or child.stderr:
        raise AssertionError((child.returncode, child.stderr))
    after = r.inventory(folder)
    if after != before: raise AssertionError('preview changed input files')
    report = json.loads(child.stdout)
    save('q-command-evidence.json', command_row(argv, child, before, after, case='actual-'+kernel+'-preview'))
    return declaration(report, transport, kernel), report, alternatives


def command_row(argv, child, before, after, **extra):
    return dict(argv=argv, exit_code=child.returncode, stdout=child.stdout.decode(), stderr=child.stderr.decode(),
                stdout_hex=child.stdout.hex(), stderr_hex=child.stderr.hex(),
                stdout_sha256=r.digest(child.stdout), stderr_sha256=r.digest(child.stderr),
                before_files=before, post_files=after, **extra)


def forbid_after_load(stack):
    for module, names in ((es, ('submission_from_bytes', 'apply_campaign_tick', 'apply_memome_batch',
                               'encode_session', 'encode_envelope_text', 'commit_session', '_exclusive_lock')),
                          (operations, ('_require_derivation',))):
        for name in names:
            stack.enter_context(mock.patch.object(module, name, side_effect=AssertionError('forbidden after mismatch: '+name)))


def checked_stale(case, path, transport, body, guard, before, *, preflight=False):
    actual_load = es.load_session
    calls = []
    with ExitStack() as stack:
        def observed(*args, **kwargs):
            loaded = actual_load(*args, **kwargs)
            calls.append(existing.identity(loaded).as_payload())
            forbid_after_load(stack)
            return loaded
        stack.enter_context(mock.patch.object(es, 'load_session', observed))
        receipt = attempt(path, transport, body, guard)
    case.assertEqual(len(calls), 1)
    case.assertEqual(receipt.status, 'stale_conflict')
    case.assertEqual(receipt.base.as_payload(), calls[0])
    case.assertIsNone(receipt.intended)
    case.assertEqual(receipt.error.error_type, 'StaleGenerationError')
    case.assertEqual(r.inventory(path.parent), before)
    save('q-observation-evidence.json', {'case': 'stale-before-semantic-work', 'supplied': guard.as_payload(),
        'observed': calls[0], 'receipt': receipt.as_payload(), 'before_files': before,
        'post_files': r.inventory(path.parent), 'load_calls': len(calls)})
    return receipt


class ReviewedFixture(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.folder = Path(temporary.name); self.path = self.folder/'session.json'
        self.transport = es.documented_transport_policy()
        self.session = m.opening()
        es.commit_session(self.path, self.session, transport=self.transport,
                          expected_generation=None, expected_digest=None)
        (self.folder/'transport.json').write_bytes(r.encoded(self.transport.as_payload()))
        self.guard, self.report, self.alternatives = preview(self.folder, 'm68a')
        self.body = existing.submission(self.alternatives[0].batch)


class ReviewedBaseTests(ReviewedFixture):
    def test_frozen_closed_parser_and_native_validation_before_io(self):
        self.assertEqual(operations.apply_precondition_from_bytes(r.encoded(self.guard.as_payload()),
                          transport=self.transport), self.guard)
        with self.assertRaises(FrozenInstanceError): self.guard.target = 'other'
        payload = self.guard.as_payload()
        invalid = [r.encoded(dict(payload, extra=1)), r.encoded({k:v for k,v in payload.items() if k!='base'}),
                   r.encoded(dict(payload, contract='other')), b'{"contract":"x","contract":"y"}', b'\xff',
                   r.encoded(dict(payload, base=dict(payload['base'], generation=True))),
                   r.encoded(dict(payload, base=dict(payload['base'], generation=1.0))),
                   r.encoded(dict(payload, base=dict(payload['base'], file_digest='A'*64))),
                   r.encoded(dict(payload, base=dict(payload['base'], session_digest='a'*63))),
                   r.encoded(dict(payload, base=dict(payload['base'], extra=0))),
                   r.encoded(dict(payload, base={k:v for k,v in payload['base'].items() if k!='turn'}))]
        for raw in invalid:
            with self.subTest(raw=raw):
                with mock.patch.object(es, 'load_session', side_effect=AssertionError('no IO')):
                    with self.assertRaises((ValueError, OSError)) as caught:
                        operations.apply_precondition_from_bytes(raw, transport=self.transport)
                save('q-observation-evidence.json',{'case':'strict-precondition-parser-refusal',
                    'declaration_bytes_hex':raw.hex(),'error_type':type(caught.exception).__name__,
                    'error_detail':str(caught.exception),'before_files':r.inventory(self.folder),'post_files':r.inventory(self.folder)})
        class Derived(operations.ApplyPrecondition): pass
        class Identity(operations.SessionIdentity): pass
        class Policy(es.TransportPolicy): pass
        class Target(str): pass
        bad = [object(), Derived(self.guard.target,self.transport,'m68a',self.guard.kernel_contract,self.guard.base),
               replace(self.guard, target=''), replace(self.guard, target=Target(self.guard.target)),
               replace(self.guard, target=str(self.folder/'alias.json')),
               replace(self.guard, transport=replace(self.transport,max_bytes=self.transport.max_bytes-1)),
               replace(self.guard, transport=Policy(**asdict(self.transport))),
               replace(self.guard, base=Identity(**asdict(self.guard.base))),
               replace(self.guard, base=replace(self.guard.base,generation=True)),
               replace(self.guard, base=replace(self.guard.base,turn=-1)),
               replace(self.guard, kernel_contract='other'), replace(self.guard, kernel=True)]
        before=r.inventory(self.folder)
        for guard in bad:
            with self.subTest(guard=guard):
                with ExitStack() as stack:
                    stack.enter_context(mock.patch.object(es,'load_session',side_effect=AssertionError('no IO')))
                    forbid_after_load(stack)
                    receipt=attempt(self.path,self.transport,b'invalid submission',guard)
                self.assertEqual(receipt.status,'rejected'); self.assertIsNone(receipt.base); self.assertIsNone(receipt.intended)
                self.assertEqual(r.inventory(self.folder),before)
                save('q-observation-evidence.json', {'case':'malformed-or-binding-before-IO',
                    'supplied_repr':repr(guard),'receipt':receipt.as_payload(),'before_files':before,'post_files':r.inventory(self.folder)})

    def test_each_valid_identity_or_kernel_mismatch_and_equal_payload_reformat(self):
        mutations=[replace(self.guard,base=replace(self.guard.base,**{field:value})) for field,value in
                   [('generation',2),('turn',1),('file_digest','0'*64),('session_digest','0'*64)]]
        mutations.append(replace(self.guard,kernel='m60a',kernel_contract=es.KERNEL_CONTRACTS['m60a']))
        for guard in mutations:
            with self.subTest(guard=guard):
                checked_stale(self,self.path,self.transport,b'not JSON',guard,r.inventory(self.folder))
        raw=self.path.read_bytes(); payload=json.loads(raw)
        self.path.write_text(json.dumps(payload,indent=2)+'\n')
        self.assertEqual(json.loads(self.path.read_bytes()),payload)
        self.assertNotEqual(r.digest(self.path.read_bytes()),r.digest(raw))
        checked_stale(self,self.path,self.transport,self.body,self.guard,r.inventory(self.folder))
        alias=self.folder/'alias.json'; alias.write_bytes(self.path.read_bytes())
        before=r.inventory(self.folder)
        with mock.patch.object(es,'load_session',side_effect=AssertionError('alias binding before IO')):
            receipt=attempt(alias,self.transport,self.body,self.guard)
        self.assertEqual(receipt.status,'rejected'); self.assertIsNone(receipt.base)
        self.assertEqual(r.inventory(self.folder),before)

    def test_advanced_writer_refuses_identical_replay_and_different_next_batch(self):
        committed=attempt(self.path,self.transport,self.body)
        self.assertEqual(committed.status,'committed_durable')
        for body in (self.body, existing.submission(m.choices(2)[1].batch), b'not JSON'):
            checked_stale(self,self.path,self.transport,body,self.guard,r.inventory(self.folder))

    def test_matching_fresh_replay_and_replacement_after_read_has_no_head_lease(self):
        self.assertEqual(attempt(self.path,self.transport,self.body,self.guard).status,'committed_durable')
        fresh,_,next_alternatives=preview(self.folder,'m68a')
        before=r.inventory(self.folder)
        with mock.patch.object(es,'commit_session',side_effect=AssertionError('replay must not commit')):
            receipt=attempt(self.path,self.transport,self.body,fresh)
        self.assertEqual(receipt.status,'replay_no_write'); self.assertIsNone(receipt.intended)
        self.assertEqual(r.inventory(self.folder),before)
        actual_load=es.load_session; writer_map=[]; calls=[]
        def replacement(*args,**kwargs):
            loaded=actual_load(*args,**kwargs); calls.append(loaded)
            writer=operations.apply_operation(self.path,transport=self.transport,
                                               submission=existing.submission(next_alternatives[1].batch))
            self.assertEqual(writer.status,'committed_durable')
            writer_map.append(r.inventory(self.folder)); return loaded
        # Writer uses the real loader, not the barrier recursively.
        def once(*args,**kwargs):
            with mock.patch.object(es,'load_session',actual_load): return replacement(*args,**kwargs)
        with mock.patch.object(es,'load_session',once):
            receipt=attempt(self.path,self.transport,self.body,fresh)
        self.assertEqual(len(calls),1); self.assertEqual(receipt.status,'replay_no_write')
        self.assertEqual(receipt.base,fresh.base); self.assertIsNone(receipt.intended)
        self.assertEqual(r.inventory(self.folder),writer_map[0])
        self.assertEqual(actual_load(self.path,transport=self.transport).generation,3)
        save('q-observation-evidence.json',{'case':'replay-after-observed-read-replacement',
            'supplied':fresh.as_payload(),'receipt':receipt.as_payload(),'before_files':before,'post_files':writer_map[0],
            'currentness_reserved':False})

    def test_observation_guard_only_bypass_fails_unchanged_stale_gate(self):
        self.assertEqual(attempt(self.path,self.transport,self.body).status,'committed_durable')
        before=r.inventory(self.folder)
        def gate():
            receipt=attempt(self.path,self.transport,self.body,self.guard)
            self.assertEqual(receipt.status,'stale_conflict')
            return receipt
        gate()
        with mock.patch.object(operations,'_require_reviewed_base',return_value=None):
            with self.assertRaises(AssertionError) as caught: gate()
            receipt=attempt(self.path,self.transport,self.body,self.guard)
        self.assertEqual(receipt.status,'replay_no_write'); self.assertEqual(r.inventory(self.folder),before)
        save('q-negative-controls.json',{'control':'only-observation-guard-bypassed','detected_failure':str(caught.exception),
            'supplied':self.guard.as_payload(),'receipt':receipt.as_payload(),
            'CAS_unchanged':True,'before_files':before,'post_files':r.inventory(self.folder)})

    def test_no_option_and_none_legacy_bytes_and_cli_keyword_shape(self):
        alias=self.folder/'legacy.json'; alias.write_bytes(self.path.read_bytes())
        left=operations.apply_operation(self.path,transport=self.transport,submission=self.body)
        right=operations.apply_operation(alias,transport=self.transport,submission=self.body,precondition=None)
        self.assertEqual(self.path.read_bytes(),alias.read_bytes())
        self.assertEqual(left.base,right.base); self.assertEqual(left.intended,right.intended)
        self.assertEqual(left.status,right.status)
        (self.folder/'submission.json').write_bytes(self.body)
        driver=runpy.run_path(str(DRIVER)); argv=['--enable','apply','--path',str(self.path),
            '--transport',str(self.folder/'transport.json'),'--submission',str(self.folder/'submission.json')]
        with mock.patch.object(operations,'apply_operation',return_value=left) as called:
            self.assertEqual(r.captured_main(driver,argv)[0],0)
        self.assertEqual(set(called.call_args.kwargs),{'transport','submission'})


class BothKernelPreviewApplyTests(unittest.TestCase):
    def test_real_preview_guard_full_saved_receipts_and_hand_oracles(self):
        for kernel in ('m60a','m68a'):
            with self.subTest(kernel=kernel), tempfile.TemporaryDirectory() as temporary:
                folder=Path(temporary); target=folder/'session.json'; transport=es.documented_transport_policy()
                session=p.opening() if kernel=='m60a' else m.opening()
                es.commit_session(target,session,transport=transport,expected_generation=None,expected_digest=None)
                (folder/'transport.json').write_bytes(r.encoded(transport.as_payload()))
                guard,report,alternatives=preview(folder,kernel)
                selected=report['alternatives'][0]
                body=existing.submission(alternatives[0].tick if kernel=='m60a' else alternatives[0].batch)
                before=r.inventory(folder); real_commit=es.commit_session
                with mock.patch.object(es,'commit_session',wraps=real_commit) as commit:
                    receipt=operations.apply_operation(target,transport=transport,submission=body,precondition=guard)
                commit.assert_called_once()
                self.assertEqual(commit.call_args.kwargs['expected_generation'],guard.base.generation)
                self.assertEqual(commit.call_args.kwargs['expected_digest'],guard.base.file_digest)
                loaded=es.load_session(target,transport=transport)
                self.assertEqual(receipt.status,'committed_durable'); self.assertEqual(receipt.base,guard.base)
                self.assertEqual(receipt.intended,existing.identity(loaded)); self.assertEqual(loaded.digest,r.digest(target.read_bytes()))
                argv=[sys.executable,'-B',str(ROOT/'scripts/experiment_receipts.py'),'--enable','--path',str(target),
                      '--transport',str(folder/'transport.json'),'--turn',str(loaded.turn)]
                before_inspect=r.inventory(folder); command=subprocess.run(argv,capture_output=True,timeout=10)
                self.assertEqual((command.returncode,command.stderr),(0,b'')); self.assertEqual(r.inventory(folder),before_inspect)
                inspection=json.loads(command.stdout); row=inspection['turns'][0]
                self.assertTrue(row['available']); self.assertEqual(inspection['file_digest'],loaded.digest)
                if kernel=='m68a':
                    expected={'proposal_id':'choice','recipient':'basic-1','slot':1,'previous':1,'candidate':3,'draw':199,
                              'candidate_weight':1,'electorate_weight':3,'threshold':200,'reason':'accepted'}
                    self.assertEqual(selected['receipts'],[{'receipt':expected,'previous_slot_value':1,'resulting_slot_value':3}])
                    self.assertEqual(row['memome']['batch'],selected['admitted_batch'])
                    self.assertEqual(row['memome']['receipts'],[expected])
                    self.assertEqual(row['memome']['participants_after'],json.loads(r.encoded([asdict(person) for person in loaded.session.ledger.participants])))
                    self.assertEqual(next(person for person in row['memome']['participants_after'] if person['agent_id']=='basic-1')['slots'][1],3)
                else:
                    raw=selected['receipt']; self.assertEqual(row['campaign']['receipt'],raw)
                    self.assertEqual(raw['phase_after'],'marching')
                    self.assertEqual([x['region_after'] for x in raw['members']],[0,0])
                    self.assertEqual([x['ration_after'] for x in raw['members']],[6,6])
                    self.assertEqual([x['consumed'] for x in raw['members']],[1,1])
                    self.assertEqual([x['distance_stress'] for x in raw['members']],[0,0])
                    self.assertEqual([x['morale_after'] for x in raw['members']],[840,810])
                    self.assertEqual(raw['food'],dict(initial=20,credits=0,local=4,carried=12,consumed=4,deserted=0))
                    self.assertEqual([(s.region,s.rations,s.morale) for s in loaded.session.session.state.soldiers],[(0,6,840),(0,6,810)])
                save('q-observation-evidence.json',{'case':'both-kernel-hand-oracle','kernel':kernel,'supplied':guard.as_payload(),
                    'preview':report,'receipt':receipt.as_payload(),'inspection':inspection,'before_files':before,'post_files':r.inventory(folder)})
                save('q-command-evidence.json',command_row(argv,command,before_inspect,r.inventory(folder),case='actual-'+kernel+'-inspect'))


def intake_child(folder, swap):
    driver=runpy.run_path(str(DRIVER)); path=folder/'precondition.json'; original_open=os.open
    def opened(target,*args,**kwargs):
        if swap and Path(target)==path:
            path.rename(folder/'precondition.displaced'); os.mkfifo(path)
        return original_open(target,*args,**kwargs)
    with ExitStack() as stack:
        stack.enter_context(mock.patch.object(operations,'apply_operation',side_effect=AssertionError('no operation')))
        stack.enter_context(mock.patch.object(os,'open',opened))
        return driver['main'](['--enable','apply','--path',str(folder/'session.json'),
             '--transport',str(folder/'transport.json'),'--submission',str(folder/'submission.json'),
             '--precondition',str(path)])


class PreconditionIntakeTests(ReviewedFixture):
    def test_optional_fifo_replacement_missing_directory_read_error_and_oversize(self):
        driver=runpy.run_path(str(DRIVER)); path=self.folder/'precondition.json'
        (self.folder/'submission.json').write_bytes(self.body)
        argv=['--enable','apply','--path',str(self.path),'--transport',str(self.folder/'transport.json'),
              '--submission',str(self.folder/'submission.json'),'--precondition',str(path)]
        for kind in ('fifo','fifo-replacement','missing','directory','read-error','oversize','utf8'):
            with self.subTest(kind=kind):
                if path.exists():
                    if path.is_dir(): path.rmdir()
                    else: path.unlink()
                (self.folder/'precondition.displaced').unlink(missing_ok=True)
                policy=replace(self.transport,max_bytes=64) if kind=='oversize' else self.transport
                (self.folder/'transport.json').write_bytes(r.encoded(policy.as_payload()))
                (self.folder/'submission.json').write_bytes(b'{}' if kind=='oversize' else self.body)
                if kind=='fifo': os.mkfifo(path)
                elif kind=='directory': path.mkdir()
                elif kind not in ('missing',): path.write_bytes(
                    b'x'*(policy.max_bytes+1) if kind=='oversize' else b'\xff' if kind=='utf8'
                    else r.encoded(self.guard.as_payload()))
                before=r.inventory(self.folder); requests=[]; handles=[]
                actual_read=es.read_regular_file_bytes
                def reader(target,**kwargs):
                    requests.append([str(target),kwargs['max_bytes'],kwargs['label']]); return actual_read(target,**kwargs)
                with ExitStack() as stack:
                    stack.enter_context(mock.patch.object(operations,'apply_operation',side_effect=AssertionError('no operation')))
                    stack.enter_context(mock.patch.object(es,'read_regular_file_bytes',reader))
                    if kind in ('fifo','fifo-replacement'):
                        child_argv=[sys.executable,'-B',str(Path(__file__)), '--intake',str(self.folder),str(int(kind=='fifo-replacement'))]
                        child=subprocess.run(child_argv,capture_output=True,timeout=3)
                        result=child.returncode,child.stdout,child.stderr; actual_argv=child_argv
                    else:
                        actual_argv=argv
                        if kind=='read-error':
                            real_open=os.open
                            def failed(target,*args,**kwargs):
                                if Path(target)==path: raise PermissionError('test-owned precondition open refusal')
                                return real_open(target,*args,**kwargs)
                            stack.enter_context(mock.patch.object(os,'open',failed))
                        result=r.captured_main(driver,argv)
                status,out,err=result; self.assertEqual((status,out),(3,b'')); receipt=json.loads(err)
                self.assertEqual(receipt['status'],'rejected'); self.assertIsNone(receipt['base']); self.assertIsNone(receipt['intended'])
                after=r.inventory(self.folder)
                if kind=='fifo-replacement':
                    self.assertEqual(after['session.json'],before['session.json'])
                    self.assertEqual(after['.session.json.lock'],before['.session.json.lock'])
                    expected=dict(before); expected['precondition.displaced']=expected.pop('precondition.json')
                    self.assertEqual({k:v for k,v in after.items() if k!='precondition.json'},expected)
                    self.assertEqual(after['precondition.json']['kind'],'fifo')
                else: self.assertEqual(after,before)
                if requests:
                    self.assertEqual(requests,[[str(self.folder/'transport.json'),4096,'transport policy'],
                        [str(self.folder/'submission.json'),policy.max_bytes,'submission'],
                        [str(path),policy.max_bytes,'apply precondition']])
                save('q-observation-evidence.json',{'case':'intake-'+kind,'argv':actual_argv,'exit_code':status,
                    'stdout_hex':out.hex(),'stderr_hex':err.hex(),'stdout_sha256':r.digest(out),'stderr_sha256':r.digest(err),
                    'before_files':before,'post_files':after,'requests':requests,'receipt':receipt})

    def test_actual_precondition_descriptor_growth_caps_and_closes(self):
        driver=runpy.run_path(str(DRIVER)); path=self.folder/'precondition.json'; path.write_bytes(b'{}')
        (self.folder/'submission.json').write_bytes(self.body)
        limit=64; policy=replace(self.transport,max_bytes=limit)
        # Small valid raw input ensures the new boundary, not submission cap, is tested.
        (self.folder/'submission.json').write_bytes(b'{}')
        (self.folder/'transport.json').write_bytes(r.encoded(policy.as_payload()))
        raw_open=builtins.open; requests=[]; handles=[]
        selected_inode=path.stat().st_ino
        class Tracked:
            def __init__(inner,descriptor,mode,*args,**kwargs):
                inner.handle=raw_open(descriptor,mode,*args,**kwargs); handles.append(inner.handle)
                inner.selected=os.fstat(descriptor).st_ino==selected_inode
            def __enter__(inner): return inner
            def __exit__(inner,*args): return inner.handle.__exit__(*args)
            def fileno(inner): return inner.handle.fileno()
            def read(inner,size):
                if inner.selected:
                    requests.append(size)
                    with path.open('ab') as writer: writer.write(b'x'*(limit+1))
                return inner.handle.read(size)
        before=r.inventory(self.folder)
        with mock.patch.object(builtins,'open',Tracked), mock.patch.object(operations,'apply_operation',side_effect=AssertionError('no operation')):
            result=r.captured_main(driver,['--enable','apply','--path',str(self.path),
                '--transport',str(self.folder/'transport.json'),'--submission',str(self.folder/'submission.json'),
                '--precondition',str(path)])
        self.assertEqual(requests,[65]); self.assertTrue(handles); self.assertTrue(all(h.closed for h in handles))
        self.assertEqual(result[0],3); self.assertEqual(json.loads(result[2])['error']['error_type'],'TransportDomainError')
        after=r.inventory(self.folder); self.assertEqual(after['session.json'],before['session.json'])
        self.assertEqual(after['.session.json.lock'],before['.session.json.lock'])
        save('q-observation-evidence.json',{'case':'descriptor-growth-cap-close','requests':requests,
            'all_handles_closed':all(h.closed for h in handles),'before_files':before,'post_files':after,
            'exit_code':result[0],'stdout_hex':result[1].hex(),'stderr_hex':result[2].hex()})

    def test_intake_order_decode_before_operation_off_help_and_syntax(self):
        driver=runpy.run_path(str(DRIVER)); path=self.folder/'precondition.json'
        path.write_bytes(r.encoded(self.guard.as_payload())); (self.folder/'submission.json').write_bytes(self.body)
        argv=['--enable','apply','--path',str(self.path),'--transport',str(self.folder/'transport.json'),
              '--submission',str(self.folder/'submission.json'),'--precondition',str(path)]
        events=[]; real_reader=es.read_regular_file_bytes; real_parser=operations.apply_precondition_from_bytes
        def reader(target,**kwargs): events.append(kwargs['label']); return real_reader(target,**kwargs)
        def parser(raw,**kwargs): events.append('strict-decode'); return real_parser(raw,**kwargs)
        observed=es.load_session(self.path,transport=self.transport)
        receipt=operations.OperationReceipt('replay_no_write',str(self.path),'m68a',existing.identity(observed),None,
            transport=self.transport,kernel_contract=es.KERNEL_CONTRACTS['m68a'])
        def operation(*args,**kwargs):
            events.append('operation'); self.assertEqual(kwargs['precondition'],self.guard); return receipt
        before=r.inventory(self.folder)
        with mock.patch.object(es,'read_regular_file_bytes',reader), mock.patch.object(operations,'apply_precondition_from_bytes',parser), mock.patch.object(operations,'apply_operation',operation):
            self.assertEqual(r.captured_main(driver,argv)[0],0)
        self.assertEqual(events,['transport policy','submission','apply precondition','strict-decode','operation'])
        path.unlink(); os.mkfifo(path)
        with mock.patch.object(es,'read_regular_file_bytes',side_effect=AssertionError('off no read')):
            empty=r.captured_main(driver,[]); off=r.captured_main(driver,argv[1:])
            self.assertEqual(empty,off)
            top=r.captured_main(driver,['--help']); self.assertNotIn(b'--precondition',top[1])
            import io
            from contextlib import redirect_stdout, redirect_stderr
            out,err=io.StringIO(),io.StringIO()
            with redirect_stdout(out),redirect_stderr(err):
                with self.assertRaises(SystemExit) as caught: driver['main'](['--enable','apply','--help'])
            self.assertEqual(caught.exception.code,0); self.assertIn('--precondition',out.getvalue())
            with redirect_stdout(out),redirect_stderr(err):
                with self.assertRaises(SystemExit) as caught: driver['main'](argv[:-1])
            self.assertEqual(caught.exception.code,2)
        self.assertEqual(r.inventory(self.folder)['session.json'],before['session.json'])
        save('q-observation-evidence.json',{'case':'intake-order-and-off-syntax','events':events,
            'off_stdout_hex':off[1].hex(),'top_help_stdout_hex':top[1].hex(),'apply_help_stdout':out.getvalue(),
            'syntax_stderr':err.getvalue(),'before_files':before,'post_files':r.inventory(self.folder)})



def contender(folder, body_file, bypass):
    transport=es.transport_policy_from_text((folder/'transport.json').read_text())
    guard=operations.apply_precondition_from_bytes((folder/'precondition.json').read_bytes(),transport=transport)
    original_load=es.load_session; original_commit=es.commit_session; commits=[]
    def load(*args,**kwargs):
        loaded=original_load(*args,**kwargs)
        print(json.dumps({'ready':existing.identity(loaded).as_payload()}),flush=True)
        if sys.stdin.readline()!='release\n': raise RuntimeError('unreleased test-owned barrier')
        return loaded
    def commit(*args,**kwargs):
        commits.append({'expected_generation':kwargs['expected_generation'],'expected_digest':kwargs['expected_digest']})
        return original_commit(*args,**kwargs)
    with ExitStack() as stack:
        stack.enter_context(mock.patch.object(es,'load_session',load))
        stack.enter_context(mock.patch.object(es,'commit_session',commit))
        if bypass: stack.enter_context(mock.patch.object(es,'_require_expected',return_value=None))
        receipt=attempt(folder/'session.json',transport,(folder/body_file).read_bytes(),guard)
    print(json.dumps({'receipt':receipt.as_payload(),'commits':commits},sort_keys=True),flush=True)


def start_child(case, folder, body_file, bypass=False):
    argv=[sys.executable,'-B',str(Path(__file__)), '--contender',str(folder),body_file,str(int(bypass))]
    child=subprocess.Popen(argv,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    case.addCleanup(lambda: terminate(child))
    with selectors.DefaultSelector() as selector:
        selector.register(child.stdout,selectors.EVENT_READ)
        case.assertTrue(selector.select(timeout=10),'child never reached real loaded barrier')
        ready=child.stdout.readline()
    case.assertIn('ready',json.loads(ready))
    return child,argv,ready


def terminate(child):
    if child.poll() is None: child.kill(); child.communicate(timeout=3)
    for stream in (child.stdin,child.stdout,child.stderr):
        if stream and not stream.closed: stream.close()


def finish_child(case, child, argv, ready):
    out,err=child.communicate(b'release\n',timeout=10)
    case.assertEqual((child.returncode,err),(0,b''))
    row={'argv':argv,'stdin_hex':b'release\n'.hex(),'exit_code':child.returncode,
         'stdout_hex':(ready+out).hex(),'stderr_hex':err.hex(),
         'stdout_sha256':r.digest(ready+out),'stderr_sha256':r.digest(err),
         'ready':json.loads(ready),'result':json.loads(out)}
    return row


class RealGuardedRaceTests(unittest.TestCase):
    def setup_files(self,folder):
        transport=es.documented_transport_policy()
        es.commit_session(folder/'session.json',m.opening(),transport=transport,expected_generation=None,expected_digest=None)
        (folder/'transport.json').write_bytes(r.encoded(transport.as_payload()))
        guard,_,alts=preview(folder,'m68a'); (folder/'precondition.json').write_bytes(r.encoded(guard.as_payload()))
        for index,alt in enumerate(alts): (folder/f'body{index}.json').write_bytes(existing.submission(alt.batch))
        return transport,guard

    def postload_gate(self,folder,bypass=False):
        transport,guard=self.setup_files(folder); initial=r.inventory(folder)
        child,argv,ready=start_child(self,folder,'body1.json',bypass)
        self.assertEqual(json.loads(ready)['ready'],guard.base.as_payload())
        writer=operations.apply_operation(folder/'session.json',transport=transport,submission=(folder/'body0.json').read_bytes())
        self.assertEqual(writer.status,'committed_durable'); before_release=r.inventory(folder)
        row=finish_child(self,child,argv,ready); after=r.inventory(folder); receipt=row['result']['receipt']
        self.assertEqual(row['result']['commits'],[{'expected_generation':guard.base.generation,'expected_digest':guard.base.file_digest}])
        self.assertEqual(receipt['base'],guard.base.as_payload()); self.assertIsNotNone(receipt['intended'])
        evidence={'case':'postload-contender','bypass_only_CAS':bypass,'supplied':guard.as_payload(),'child':row,
            'writer_receipt':writer.as_payload(),'initial_files':initial,'before_release_files':before_release,'post_files':after}
        save('q-race-evidence.json',evidence)
        return receipt,before_release,after,evidence

    def assert_postload_refusal(self,receipt,before,after):
        self.assertEqual(receipt['status'],'stale_conflict')
        self.assertEqual(after,before)

    def test_real_postload_writer_final_CAS_and_independent_CAS_only_negative_control(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder=Path(temporary); normal=folder/'normal'; normal.mkdir(); bypass=folder/'bypass'; bypass.mkdir()
            receipt,before,after,_=self.postload_gate(normal)
            self.assert_postload_refusal(receipt,before,after)
            receipt,before,after,evidence=self.postload_gate(bypass,True)
            with self.assertRaises(AssertionError) as caught: self.assert_postload_refusal(receipt,before,after)
            self.assertEqual(receipt['status'],'committed_durable')
            self.assertNotEqual(after['session.json']['sha256'],before['session.json']['sha256'])
            save('q-negative-controls.json',{'control':'only-final-CAS-comparison-bypassed',
                'comparison_seam':'experiment_sessions._require_expected','expected_generation_retained':1,
                'observation_guard_unchanged':True,'real_lock_write_commit_retained':True,
                'detected_failure':str(caught.exception),'evidence':evidence})

    def test_two_guarded_real_contenders_one_winner_unspecified(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder=Path(temporary); transport,guard=self.setup_files(folder); before=r.inventory(folder)
            children=[start_child(self,folder,f'body{i}.json') for i in range(2)]
            for child,_,_ in children: child.stdin.write(b'release\n'); child.stdin.flush()
            records=[]
            for child,argv,ready in children:
                # Both releases are already delivered; do not issue a second release.
                out,err=child.communicate(timeout=10)
                self.assertEqual((child.returncode,err),(0,b''))
                records.append({'argv':argv,'stdin_hex':b'release\n'.hex(),'exit_code':child.returncode,
                    'stdout_hex':(ready+out).hex(),'stderr_hex':err.hex(),'stdout_sha256':r.digest(ready+out),
                    'stderr_sha256':r.digest(err),'ready':json.loads(ready),'result':json.loads(out)})
            statuses=[x['result']['receipt']['status'] for x in records]
            self.assertCountEqual(statuses,['committed_durable','stale_conflict'])
            winner=next(x for x in records if x['result']['receipt']['status']=='committed_durable')
            loaded=es.load_session(folder/'session.json',transport=transport)
            self.assertEqual(existing.identity(loaded).as_payload(),winner['result']['receipt']['intended'])
            self.assertEqual((loaded.generation,loaded.turn,len(loaded.session.batches)),(2,1,1))
            for record in records:
                self.assertEqual(record['ready']['ready'],guard.base.as_payload())
                self.assertEqual(record['result']['commits'],[{'expected_generation':1,'expected_digest':guard.base.file_digest}])
            chosen=3 if 'body0.json' in winner['argv'] else 0
            self.assertEqual(loaded.session.batches[0].proposals[0].candidate,chosen)
            self.assertEqual(next(x for x in loaded.session.ledger.participants if x.agent_id=='basic-1').slots[1],3 if chosen==3 else 1)
            save('q-race-evidence.json',{'case':'two-guarded-contenders','supplied':guard.as_payload(),'children':records,
                'winner_not_predetermined':True,'before_files':before,'post_files':r.inventory(folder)})


class PublishedGuardedWorkflowTests(unittest.TestCase):
    def test_published_extension_exact_commands_and_full_bytes_at_seeds_0_42(self):
        text=DOC.read_text()
        prior=re.findall(r'<!-- r007-step: ([a-z-]+) -->\n```sh\n(.*?)\n```',text,re.S)
        steps=[(name,block) for name,block in prior if name in ('prepare','create','copy-opening','select')]
        guarded=re.findall(r'<!-- q009-step: ([a-z-]+) -->\n```sh\n(.*?)\n```',text,re.S)
        self.assertEqual([name for name,_ in guarded],['preview','precondition','apply','inspect','stale-replay'])
        steps+=guarded; records=[]
        with tempfile.TemporaryDirectory() as temporary:
            for seed in ('0','42'):
                folder=Path(temporary)/('seed-'+seed); folder.mkdir()
                env=dict(os.environ,PYTHONHASHSEED=seed,PYTHON=sys.executable,CHECKOUT=str(ROOT),PYTHONDONTWRITEBYTECODE='1')
                for name,block in steps:
                    before=r.inventory(folder); lines=block.splitlines(); stdin=None; redirected=None
                    if " <<'PY'" in lines[0]:
                        stdin=('\n'.join(lines[1:-1])+'\n').encode(); head=lines[0].split(" <<'PY'")[0]
                    else: head=block
                    argv=[word.replace('$PYTHON',sys.executable).replace('$CHECKOUT',str(ROOT)) for word in shlex.split(head)]
                    if '>' in argv:
                        index=argv.index('>'); redirected=argv[index+1]; argv=argv[:index]
                        # Run the actual published shell redirect; retain both shell streams and delivered program stdout.
                        child=subprocess.run(['/bin/sh','-eu','-c',block],cwd=folder,env=env,capture_output=True,timeout=15)
                    else:
                        child=subprocess.run(argv,cwd=folder,env=env,input=stdin,capture_output=True,timeout=15)
                    after=r.inventory(folder); expected=3 if name=='stale-replay' else 0
                    self.assertEqual(child.returncode,expected,child.stderr)
                    if expected==0: self.assertEqual(child.stderr,b'')
                    else: self.assertEqual(child.stdout,b'')
                    row=command_row(argv,child,before,after,seed=seed,step=name,published_block=block,
                                    stdin_hex=None if stdin is None else stdin.hex(),stdout_redirect=redirected,
                                    execution_argv=['/bin/sh','-eu','-c',block] if redirected else argv)
                    if redirected: row['redirected_stdout_hex']=(folder/redirected).read_bytes().hex()
                    records.append(row)
                    if name=='preview':
                        report=json.loads((folder/'reviewed-preview.json').read_bytes())
                        self.assertEqual(report['cli_observation']['file_digest'],before['memome.json']['sha256'])
                        self.assertFalse(report['cli_observation']['submission_token'])
                        self.assertEqual(after['memome.json'],before['memome.json'])
                    if name=='precondition':
                        supplied=json.loads((folder/'precondition.json').read_bytes())
                        self.assertEqual(supplied,declaration(report,es.documented_transport_policy(),'m68a').as_payload())
                        self.assertEqual(after['memome.json'],before['memome.json'])
                    if name=='apply':
                        applied=json.loads(child.stdout)
                        self.assertEqual(applied['status'],'committed_durable'); self.assertEqual(applied['base'],supplied['base'])
                        self.assertEqual(applied['intended']['file_digest'],after['memome.json']['sha256'])
                        self.assertEqual((applied['intended']['generation'],applied['intended']['turn']),(2,1))
                    if name=='inspect':
                        self.assertEqual(after,before)
                        inspection=json.loads(child.stdout)
                        expected_receipt={'proposal_id':'choice','recipient':'basic-1','slot':1,'previous':1,'candidate':3,'draw':199,
                            'candidate_weight':1,'electorate_weight':3,'threshold':200,'reason':'accepted'}
                        row=inspection['turns'][0]['memome']
                        self.assertEqual(row['receipts'],[expected_receipt])
                        self.assertEqual(row['batch'],next(a['batch'] for a in json.loads((folder/'choices.json').read_bytes())['alternatives'] if a['label']=='candidate 3'))
                        loaded=es.load_session(folder/'memome.json',transport=es.documented_transport_policy())
                        self.assertEqual(row['participants_after'],json.loads(r.encoded([asdict(person) for person in loaded.session.ledger.participants])))
                        self.assertEqual(existing.identity(loaded).as_payload(),applied['intended'])
                    if name=='stale-replay':
                        self.assertEqual(after,before); refused=json.loads(child.stderr)
                        self.assertEqual(refused['status'],'stale_conflict'); self.assertEqual(refused['base'],applied['intended'])
                        self.assertIsNone(refused['intended'])
                        self.assertNotEqual(refused['base'],supplied['base'])
                        save('q-observation-evidence.json',{'case':'published-stale-replay','seed':seed,'supplied':supplied,
                            'observed':refused['base'],'receipt':refused,'before_files':before,'post_files':after})
        first=records[:len(steps)]; second=records[len(steps):]
        for left,right in zip(first,second):
            self.assertEqual((left['argv'],left['stdin_hex'],left['exit_code'],left['stdout_hex'],left['stderr_hex']),
                             (right['argv'],right['stdin_hex'],right['exit_code'],right['stdout_hex'],right['stderr_hex']))
            self.assertEqual({k:(v.get('bytes_hex'),v.get('sha256'),v['kind']) for k,v in left['post_files'].items()},
                             {k:(v.get('bytes_hex'),v.get('sha256'),v['kind']) for k,v in right['post_files'].items()})
        for row in records: save('q-command-evidence.json',row)


if __name__=='__main__':
    if len(sys.argv)>1 and sys.argv[1]=='--intake':
        raise SystemExit(intake_child(Path(sys.argv[2]),bool(int(sys.argv[3]))))
    if len(sys.argv)>1 and sys.argv[1]=='--contender':
        contender(Path(sys.argv[2]),sys.argv[3],bool(int(sys.argv[4]))); raise SystemExit(0)
    unittest.main()
