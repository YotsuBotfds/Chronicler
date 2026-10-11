"""Consumer I/O delegations, opened-version races and exact accepted-Q comparisons."""
from contextlib import ExitStack
from dataclasses import replace
import builtins
import hashlib
import json
import os
from pathlib import Path
import runpy
import stat
import subprocess
import sys
import tempfile
import traceback
import unittest
from unittest import mock
import pytest
from chronicler import experiment_sessions as es
import test_campaign_order_preview as p
import test_experiment_receipt_inspector as d
import test_operator_submission_workflow as r
from reference_baselines import baseline_root

ROOT=Path(__file__).resolve().parents[1]
BASELINE=Path(os.environ.get('PD_BASELINE',baseline_root('26e1869da6c963108f0eb09dae1455245c030bc9')))
OWNED=['scripts/campaign_order_preview.py','scripts/experiment_receipts.py',
       'tests/test_campaign_order_preview.py','tests/test_experiment_receipt_inspector.py',
       'tests/test_pd_input_boundaries.py','docs/experiments/campaign-order-preview.md','docs/experiments/receipt-inspection.md']
RECORDS={name:[] for name in ('pd-intake-evidence.json','pd-command-comparison.json','pd-negative-controls.json')}


def inventory(folder):
    result=r.inventory(folder)
    for path in folder.iterdir():
        if path.is_symlink():result[path.name].update(kind='symlink',link_target=os.readlink(path))
    return result


def persist(name,row):
    RECORDS[name].append(row)
    folder=Path(os.environ.get('PD_EVIDENCE_DIR',os.environ.get('TMPDIR',tempfile.gettempdir())))
    folder.mkdir(parents=True,exist_ok=True)
    (folder/name).write_text(json.dumps({'source_sha256':{s:r.digest((ROOT/s).read_bytes()) for s in OWNED},
                                        'records':RECORDS[name]},sort_keys=True,indent=2)+'\n')


def arguments(consumer,folder):
    args=['--enable','--path',str(folder/'session.json'),'--transport',str(folder/'transport.json')]
    return args+(['--alternatives',str(folder/'alternatives.json'),'--max-alternatives','2'] if consumer=='P' else ['--turn','1'])


def script(consumer,root=ROOT):
    return root/('scripts/campaign_order_preview.py' if consumer=='P' else 'scripts/experiment_receipts.py')


def forbidden(*args,**kwargs):raise AssertionError('forbidden downstream work or write')


def worker(consumer,folder,stage,exchange,record_path):
    driver=runpy.run_path(str(script(consumer))); path=folder/(stage+'.json')
    original_open=os.open; original_load=es.load_session; original_reader=es.read_regular_file_bytes
    opens=[];loads=[];reads=[];substituted=[];handles=[];original_handle=builtins.open
    def opened(target,*args,**kwargs):
        selected=Path(target)==path
        if selected:opens.append(str(target))
        if selected and exchange=='before':
            path.rename(folder/(stage+'.displaced'));os.mkfifo(path);substituted.append(inventory(folder))
        descriptor=original_open(target,*args,**kwargs)
        if selected and exchange=='after':
            path.rename(folder/(stage+'.displaced'));os.replace(folder/'replacement.json',path)
            substituted.append(inventory(folder))
        return descriptor
    def loaded(*args,**kwargs):
        loads.append(str(args[0]));return original_load(*args,**kwargs)
    def reader(target,**kwargs):
        reads.append({'path':str(target),**kwargs});return original_reader(target,**kwargs)
    def handle(descriptor,*args,**kwargs):
        result=original_handle(descriptor,*args,**kwargs);handles.append(result);return result
    with ExitStack() as stack:
        stack.enter_context(mock.patch.object(os,'open',opened))
        stack.enter_context(mock.patch.object(builtins,'open',handle))
        stack.enter_context(mock.patch.object(es,'load_session',loaded))
        stack.enter_context(mock.patch.object(es,'read_regular_file_bytes',reader))
        for name in ('commit_session','_exclusive_lock'):stack.enter_context(mock.patch.object(es,name,forbidden))
        # Refusal gates permit earlier successful intake but forbid later stages.
        if exchange!='after' or (folder/'old-malformed').exists():
            if consumer=='P':
                stack.enter_context(mock.patch.dict(driver['main'].__globals__,{'preview_orders':forbidden}))
                if stage=='transport':
                    if not (folder/'old-malformed').exists():stack.enter_context(mock.patch.object(es,'transport_policy_from_text',forbidden))
                    stack.enter_context(mock.patch.object(es,'load_session',forbidden))
                elif stage=='alternatives':
                    if not (folder/'old-malformed').exists():stack.enter_context(mock.patch.object(es,'submission_from_bytes',forbidden))
                    stack.enter_context(mock.patch.object(es,'load_session',forbidden))
            else:
                stack.enter_context(mock.patch.dict(driver['main'].__globals__,{'inspect_receipts':forbidden}))
                if not (folder/'old-malformed').exists():stack.enter_context(mock.patch.object(es,'transport_policy_from_text',forbidden))
                stack.enter_context(mock.patch.object(es,'load_session',forbidden))
        status=driver['main'](arguments(consumer,folder))
    record={'stage':stage,'exchange':exchange,'opens':opens,'load_calls':loads,'reader_calls':reads,
            'substitution_files':substituted,'post_files':inventory(folder),
            'all_opened_handles_closed':all(h.closed for h in handles)}
    record_path.write_text(json.dumps(record,sort_keys=True))
    return status


class BoundaryTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        self.folder=Path(temporary.name);self.transport=es.documented_transport_policy()
        self.session=p.opening()
        es.commit_session(self.folder/'session.json',self.session,transport=self.transport,
                          expected_generation=None,expected_digest=None)
        (self.folder/'transport.json').write_bytes(r.encoded(self.transport.as_payload()))
        (self.folder/'alternatives.json').write_bytes(p.document(p.choices(self.session)))

    def child(self,consumer,stage,exchange):
        with tempfile.TemporaryDirectory() as record_folder:
            record_path=Path(record_folder)/'record.json';before=inventory(self.folder)
            argv=[sys.executable,'-B',str(Path(__file__)), '--worker',consumer,str(self.folder),stage,exchange,str(record_path)]
            child=subprocess.run(argv,capture_output=True,timeout=4)
            self.assertTrue(record_path.exists(),child.stderr)
            detail=json.loads(record_path.read_bytes());after=inventory(self.folder)
            self.assertTrue(detail['all_opened_handles_closed'])
            row={'consumer':consumer,'stage':stage,'exchange':exchange,'argv':argv,'stdin_hex':None,
                 'exit_code':child.returncode,'stdout_hex':child.stdout.hex(),'stderr_hex':child.stderr.hex(),
                 'stdout_sha256':r.digest(child.stdout),'stderr_sha256':r.digest(child.stderr),
                 'before_files':before,'post_files':after,'detail':detail}
            persist('pd-intake-evidence.json',row)
            return child,detail,before,after

    def test_real_FIFO_initial_and_every_deterministic_preopen_exchange(self):
        for consumer,stage in [('P','transport'),('P','alternatives'),('P','session'),('D','transport')]:
            for exchange in ('initial','before'):
                with self.subTest(consumer=consumer,stage=stage,exchange=exchange):
                    path=self.folder/(stage+'.json');raw=path.read_bytes()
                    if exchange=='initial':path.unlink();os.mkfifo(path)
                    child,detail,before,after=self.child(consumer,stage,exchange)
                    self.assertEqual((child.returncode,child.stdout),(3,b''));error=json.loads(child.stderr)
                    self.assertIn(error['error'],('PreviewError','SessionError'))
                    self.assertEqual(after,detail['substitution_files'][0] if exchange=='before' else before)
                    expected_loads=1 if consumer=='P' and stage=='session' and exchange=='before' else 0
                    self.assertEqual(len(detail['load_calls']),expected_loads)
                    self.assertEqual(len(detail['opens']),1 if exchange=='before' or consumer=='D' else 0)
                    if exchange=='before':
                        expected=dict(before);expected[stage+'.displaced']=expected.pop(stage+'.json')
                        self.assertEqual({k:v for k,v in after.items() if k!=stage+'.json'},expected)
                        self.assertEqual(after[stage+'.json']['kind'],'fifo')
                    path.unlink()
                    displaced=self.folder/(stage+'.displaced')
                    if displaced.exists():displaced.rename(path)
                    else:path.write_bytes(raw)

    def test_after_descriptor_open_observes_old_input_and_single_loaded_version(self):
        for consumer,stage in [('P','transport'),('P','alternatives'),('P','session'),('D','transport')]:
            with self.subTest(consumer=consumer,stage=stage):
                path=self.folder/(stage+'.json');old=path.read_bytes()
                if stage=='session':
                    newer=es.apply_campaign_tick(self.session,p.choices(self.session)[0].tick).session
                    es.commit_session(self.folder/'replacement.json',newer,transport=self.transport,
                                      expected_generation=None,expected_digest=None)
                else:(self.folder/'replacement.json').write_bytes(b'not JSON')
                child,detail,before,after=self.child(consumer,stage,'after')
                self.assertEqual((child.returncode,child.stderr),(0,b''))
                self.assertEqual(after,detail['substitution_files'][0]);self.assertEqual(len(detail['opens']),1)
                self.assertEqual(len(detail['load_calls']),1)
                report=json.loads(child.stdout)
                if consumer=='P':
                    self.assertEqual(report['cli_observation']['file_digest'],r.digest(old if stage=='session' else self.folder.joinpath('session.json').read_bytes()))
                    self.assertEqual(report['base_turn'],1)
                    self.assertEqual(report['alternatives'],p.call(self.session).as_payload()['alternatives'])
                else:self.assertEqual(report['file_digest'],after['session.json']['sha256'])
                path.unlink();(self.folder/(stage+'.displaced')).rename(path)
                (self.folder/'replacement.json').unlink(missing_ok=True)

    def test_distinct_initial_link_policy_and_input_errors_and_off(self):
        driver_p=p.cli_module();driver_d=runpy.run_path(str(script('D')))
        link=self.folder/'link.json';link.symlink_to(self.folder/'transport.json')
        before=inventory(self.folder)
        pa=arguments('P',self.folder);pa[pa.index('--transport')+1]=str(link)
        da=arguments('D',self.folder);da[da.index('--transport')+1]=str(link)
        self.assertEqual(r.captured_main(driver_p.__dict__,pa)[0],3)
        self.assertEqual(r.captured_main(driver_d,da)[0],0)
        self.assertEqual(inventory(self.folder),before)
        for consumer in ('P','D'):
            driver=driver_p.__dict__ if consumer=='P' else driver_d
            for stage in (('transport','alternatives','session') if consumer=='P' else ('transport',)):
                for kind in ('missing','directory','read-error'):
                    with self.subTest(consumer=consumer,stage=stage,kind=kind):
                        path=self.folder/(stage+'.json');old=path.read_bytes();path.unlink()
                        if kind=='directory':path.mkdir()
                        elif kind=='read-error':path.write_bytes(old)
                        before=inventory(self.folder);actual_open=os.open
                        def failure(target,*args,**kwargs):
                            if Path(target)==path:raise PermissionError('test-owned opened input refusal')
                            return actual_open(target,*args,**kwargs)
                        with ExitStack() as stack:
                            stack.enter_context(mock.patch.object(es,'commit_session',forbidden))
                            stack.enter_context(mock.patch.object(es,'_exclusive_lock',forbidden))
                            if kind=='read-error':stack.enter_context(mock.patch.object(os,'open',failure))
                            result=r.captured_main(driver,arguments(consumer,self.folder))
                        self.assertEqual((result[0],result[1]),(3,b''));self.assertEqual(inventory(self.folder),before)
                        persist('pd-intake-evidence.json',{'consumer':consumer,'stage':stage,'case':kind,
                            'exit_code':result[0],'stdout_hex':result[1].hex(),'stderr_hex':result[2].hex(),
                            'stdout_sha256':r.digest(result[1]),'stderr_sha256':r.digest(result[2]),'before_files':before,'post_files':inventory(self.folder)})
                        if kind=='directory':path.rmdir()
                        elif path.exists():path.unlink()
                        path.write_bytes(old)
            fifo=self.folder/'off.fifo';os.mkfifo(fifo)
            poisoned=arguments(consumer,self.folder)[1:];poisoned[poisoned.index('--transport')+1]=str(fifo)
            before=inventory(self.folder)
            with mock.patch.object(es,'read_regular_file_bytes',forbidden),mock.patch.object(es,'load_session',forbidden),mock.patch.object(es,'transport_policy_from_text',forbidden):
                self.assertEqual(r.captured_main(driver,poisoned),r.captured_main(driver,[]))
            self.assertEqual(inventory(self.folder),before);fifo.unlink()

    def test_malformed_old_opened_bytes_refuse_even_when_path_now_valid(self):
        for consumer,stage in [('P','transport'),('P','alternatives'),('D','transport')]:
            with self.subTest(consumer=consumer,stage=stage):
                path=self.folder/(stage+'.json');raw=path.read_bytes();path.write_bytes(b'\xff')
                (self.folder/'replacement.json').write_bytes(raw);(self.folder/'old-malformed').write_bytes(b'')
                child,detail,before,after=self.child(consumer,stage,'after')
                self.assertEqual((child.returncode,child.stdout),(3,b''))
                self.assertEqual(json.loads(child.stderr)['error'],'SessionError' if stage=='alternatives' else 'UnicodeDecodeError')
                if stage=='alternatives':self.assertEqual(json.loads(child.stderr)['detail'],'the alternatives is not valid UTF-8')
                self.assertEqual(len(detail['opens']),1);self.assertEqual(len(detail['load_calls']),0)
                self.assertEqual(after,detail['substitution_files'][0])
                path.unlink();(self.folder/(stage+'.displaced')).unlink();path.write_bytes(raw)
                (self.folder/'old-malformed').unlink()

    def test_caps_growth_actual_descriptor_closure_and_unsupported_no_fallback(self):
        pp=p.cli_module();dd=runpy.run_path(str(script('D')))
        for consumer,limit in [('P',64),('D',4096)]:
            path=self.folder/'transport.json';old=path.read_bytes()
            for case in ('exact','plus-one','growth','read-error','unsupported'):
                with self.subTest(consumer=consumer,case=case):
                    if case=='exact':
                        raw=old+b' '*(limit-len(old)) if consumer=='D' else b'x'*limit
                    elif case=='plus-one':raw=b'x'*(limit+1)
                    else:raw=b'{}'
                    path.write_bytes(raw);before=inventory(self.folder);handles=[];requests=[];actual_open=builtins.open
                    actual_stat = Path.stat
                    def no_size_stat(target, *, follow_symlinks=True):
                        # P explicitly rejects links using lstat. Python 3.13
                        # routes lstat through stat(follow_symlinks=False).
                        if follow_symlinks is False:
                            return actual_stat(target, follow_symlinks=False)
                        return forbidden(target)
                    class Handle:
                        def __init__(inner,descriptor,*args,**kwargs):
                            inner.real=actual_open(descriptor,*args,**kwargs);handles.append(inner.real)
                        def __enter__(inner):return inner
                        def __exit__(inner,*args):inner.real.close()
                        def fileno(inner):return inner.real.fileno()
                        def read(inner,size):
                            requests.append(size)
                            if case=='growth':
                                with path.open('ab') as writer:writer.write(b'x'*(limit+1))
                            if case=='read-error':raise OSError('test-owned descriptor read failure')
                            return inner.real.read(size)
                    with ExitStack() as stack:
                        stack.enter_context(mock.patch.object(builtins,'open',Handle))
                        stack.enter_context(mock.patch.object(Path,'stat',no_size_stat))
                        if case!='exact':stack.enter_context(mock.patch.object(es,'transport_policy_from_text',forbidden))
                        if case=='unsupported':
                            stack.enter_context(mock.patch.dict(os.__dict__))
                            del os.__dict__['O_NONBLOCK']
                            stack.enter_context(mock.patch.object(os,'open',forbidden))
                        if case=='exact':
                            value=pp._read(path,limit) if consumer=='P' else dd['_transport'](path)
                            self.assertEqual(value,raw if consumer=='P' else self.transport)
                        else:
                            kind=es.UnsupportedPlatformError if case=='unsupported' else OSError if case=='read-error' else es.TransportDomainError
                            with self.assertRaises(kind) as caught:
                                pp._read(path,limit) if consumer=='P' else dd['_transport'](path)
                    self.assertEqual(requests,[] if case=='unsupported' else [limit+1])
                    self.assertTrue(all(h.closed for h in handles));after=inventory(self.folder)
                    if case!='growth':self.assertEqual(after,before)
                    else:
                        changed=dict(after);changed['transport.json']=before['transport.json'];self.assertEqual(changed,before)
                    persist('pd-intake-evidence.json',{'consumer':consumer,'stage':'transport' if consumer=='D' else 'bounded-input',
                        'case':case,'limit':limit,'requests':requests,'all_handles_closed':all(h.closed for h in handles),
                        'error_type':None if case=='exact' else type(caught.exception).__name__,
                        'error_detail':None if case=='exact' else str(caught.exception),'before_files':before,'post_files':after})
                    path.write_bytes(old)
        # Real alternatives at their exact caller cap decode normally; max+1 refuses before that parser.
        raw=(self.folder/'alternatives.json').read_bytes();policy=replace(self.transport,max_bytes=len(raw))
        self.assertEqual(pp._read(self.folder/'alternatives.json',policy.max_bytes),raw)
        self.assertEqual(len(pp._alternatives(raw,policy,2)),2)


class OriginalGateNegativeControls(unittest.TestCase):
    def test_independent_unbounded_substitutes_fail_both_original_request_gates(self):
        real_factory=p.cli_module
        def unbounded(target,limit):
            raw=Path(target).read_bytes()
            if len(raw)>limit:raise es.TransportDomainError('correct refusal after unbounded read')
            return raw
        def factory():
            driver=real_factory();driver._read=unbounded;return driver
        result=unittest.TestResult()
        with mock.patch.object(p,'cli_module',factory):p.CliTests('test_bounded_reads_at_most_limit_plus_one').run(result)
        self.assertEqual((result.testsRun,len(result.failures),len(result.errors)),(1,1,0))
        self.assertIn('[] != [4097, 8388609]',result.failures[0][1])
        persist('pd-negative-controls.json',{'consumer':'P','only_consumer_reader_replaced':True,
            'eventual_oversize_refusal_retained':True,'original_test':'test_bounded_reads_at_most_limit_plus_one',
            'failures':[text for _,text in result.failures],'errors':[]})
        with tempfile.TemporaryDirectory() as temporary:
            def transport(target):
                raw=Path(target).read_bytes()
                if len(raw)>4096:raise es.TransportDomainError('correct refusal after unbounded read')
                return es.transport_policy_from_text(raw.decode())
            with pytest.MonkeyPatch.context() as monkeypatch:
                monkeypatch.setitem(d.CLI,'_transport',transport)
                with self.assertRaises(AssertionError) as caught:
                    d.test_policy_actual_handle_read_is_bounded_before_decode_without_stat(monkeypatch,Path(temporary))
            persist('pd-negative-controls.json',{'consumer':'D','only_consumer_reader_replaced':True,
                'eventual_oversize_refusal_retained':True,
                'original_test':'test_policy_actual_handle_read_is_bounded_before_decode_without_stat',
                'failure_type':type(caught.exception).__name__,'failure_detail':str(caught.exception)})


class AcceptedQCommandComparison(unittest.TestCase):
    def test_supported_command_outputs_and_full_postfiles_against_accepted_Q_seeds_0_42(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder=Path(temporary);transport=es.documented_transport_policy();session=p.opening()
            es.commit_session(folder/'session.json',session,transport=transport,expected_generation=None,expected_digest=None)
            (folder/'transport.json').write_bytes(r.encoded(transport.as_payload()))
            (folder/'alternatives.json').write_bytes(p.document(p.choices(session)))
            (folder/'bad-alternatives.json').write_bytes(b'{"contract":true,"alternatives":[]}')
            (folder/'bad-policy.json').write_bytes(b'{}')
            (folder/'oversize.json').write_bytes(b'x'*4097)
            (folder/'utf8.json').write_bytes(b'\xff')
            (folder/'directory').mkdir()
            results=[]
            for seed in ('0','42'):
                for consumer in ('P','D'):
                    common=['--enable','--path','session.json','--transport','transport.json']
                    selected=common+(['--alternatives','alternatives.json','--max-alternatives','2'] if consumer=='P' else ['--turn','1'])
                    cases=[('json',selected),('text',selected+['--format','text']),
                           ('off-poison',['--path','missing','--transport','missing','--format','poison','--unknown']),
                           ('help',['--help']),('syntax',selected+['--format','wrong']),('missing-required',['--enable']),
                           ('invalid-policy',selected.copy()),('utf8',selected.copy()),
                           ('oversize',selected.copy()),('directory',selected.copy())]
                    if consumer=='P':cases.append(('semantic-error',common+['--alternatives','bad-alternatives.json','--max-alternatives','2']))
                    else:cases.append(('semantic-error',common+['--turn','-1']))
                    for name,args in cases:
                        args=args.copy()
                        if name in ('invalid-policy','utf8','oversize','directory'):
                            args[args.index('--transport')+1]={'invalid-policy':'bad-policy.json','utf8':'utf8.json',
                                                            'oversize':'oversize.json','directory':'directory'}[name]
                        pair=[]
                        for label,root in [('accepted-Q',BASELINE),('PD-candidate',ROOT)]:
                            env=dict(os.environ,PYTHONHASHSEED=seed,PYTHONDONTWRITEBYTECODE='1',
                                     PYTHONPATH=os.pathsep.join([str(root/'src'),str(root/'tests')]))
                            before=inventory(folder);argv=[sys.executable,'-B',str(script(consumer,root)),*args]
                            command=subprocess.run(argv,cwd=folder,env=env,capture_output=True,timeout=10)
                            after=inventory(folder);self.assertEqual(after,before)
                            row={'source':label,'source_root':str(root),'source_parent':'26e1869da6c963108f0eb09dae1455245c030bc9',
                                 'driver_sha256':r.digest(script(consumer,root).read_bytes()),'seed':seed,'consumer':consumer,
                                 'case':name,'argv':argv,'stdin_hex':None,'exit_code':command.returncode,
                                 'stdout_hex':command.stdout.hex(),'stderr_hex':command.stderr.hex(),
                                 'stdout_sha256':r.digest(command.stdout),'stderr_sha256':r.digest(command.stderr),
                                 'before_files':before,'post_files':after}
                            pair.append(row);persist('pd-command-comparison.json',row)
                        self.assertEqual((pair[0]['exit_code'],pair[0]['stdout_hex']),(pair[1]['exit_code'],pair[1]['stdout_hex']))
                        diagnostic_change=name=='oversize' or (name=='directory' and consumer=='D')
                        if diagnostic_change:
                            old,new=(json.loads(bytes.fromhex(row['stderr_hex'])) for row in pair)
                            self.assertEqual(old['error'],new['error']);self.assertNotEqual(old['detail'],new['detail'])
                        else:self.assertEqual(pair[0]['stderr_hex'],pair[1]['stderr_hex'])
                        results.append((seed,consumer,name,pair))
            for left,right in zip(results[:len(results)//2],results[len(results)//2:]):
                self.assertEqual(left[1:3],right[1:3])
                for a,b in zip(left[3],right[3]):
                    self.assertEqual((a['exit_code'],a['stdout_hex'],a['stderr_hex'],a['post_files']),
                                     (b['exit_code'],b['stdout_hex'],b['stderr_hex'],b['post_files']))


if __name__=='__main__':
    if len(sys.argv)>1 and sys.argv[1]=='--worker':
        raise SystemExit(worker(sys.argv[2],Path(sys.argv[3]),sys.argv[4],sys.argv[5],Path(sys.argv[6])))
    unittest.main()
