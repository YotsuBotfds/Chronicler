"""Integrated bounded-load and default dispatch checks, no new runtime wiring."""
from dataclasses import replace
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from chronicler import experiment_sessions as es
from chronicler import session_operations as operations
from chronicler import experiment_receipt_inspector as inspector
from test_session_read_bounds import TrackedHandle

ROOT=Path(__file__).resolve().parents[1]
class DefaultBoundaries(unittest.TestCase):
    def test_B_D_use_the_actual_integrated_bounded_public_session_loader(self):
        self.assertIs(operations.es,es);self.assertIs(inspector.es,es)
        self.assertEqual(Path(es.__file__).resolve(),(ROOT/'src/chronicler/experiment_sessions.py').resolve())
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'large.json';path.write_bytes(b' '*513);policy=replace(es.documented_transport_policy(),max_bytes=512);import builtins;original=builtins.open;requests=[]
            def opened(p,mode='r',*a,**kw):
                handle=original(p,mode,*a,**kw)
                return TrackedHandle(handle,requests) if type(p) is int and mode=='rb' else handle
            with mock.patch.object(builtins,'open',opened),mock.patch.object(Path,'read_bytes',side_effect=AssertionError('unbounded reader reached')),mock.patch.object(es,'decode_envelope_text',side_effect=AssertionError('decode reached')):
                with self.assertRaises(es.TransportDomainError):operations.apply_operation(path,transport=policy,submission=b'{}')
                with self.assertRaises(es.TransportDomainError):inspector.inspect_receipts(path,enabled=True,transport=policy,turn=1)
            self.assertEqual([size for _,size in requests],[513,513])
    def test_new_operator_scripts_ignore_optional_inputs_while_off_at_both_hashseeds(self):
        arguments={'session_operation.py':['apply','--path','/not-read/session','--transport','/not-read/transport','--submission','/not-read/submission'],
                   'experiment_receipts.py':['--path','/not-read/session','--transport','/not-read/transport','--turn','invalid','--format','invalid']}
        with tempfile.TemporaryDirectory() as directory:
            for script,args in arguments.items():
                outputs=[]
                for seed in ('0','42'):
                    run=subprocess.run([sys.executable,'-B',str(ROOT/'scripts'/script),*args],cwd=directory,env=dict(os.environ,PYTHONHASHSEED=seed),capture_output=True,timeout=20)
                    self.assertEqual(run.returncode,0,run.stderr.decode());payload=json.loads(run.stdout)
                    self.assertFalse(payload['reads_files']);self.assertFalse(payload['writes_files']);self.assertFalse(payload['calls_kernels']);outputs.append((run.stdout,run.stderr))
                self.assertEqual(outputs[0],outputs[1])
                self.assertEqual(list(Path(directory).iterdir()),[])
    def test_imports_do_not_activate_native_world_provider_or_rng(self):
        code="import random,sys; before=random.getstate(); from chronicler import session_operations,experiment_receipt_inspector; assert random.getstate()==before; assert not any(n in sys.modules for n in ('chronicler_agents','chronicler.main','chronicler.simulation')); print('bounded operator imports only')"
        with tempfile.TemporaryDirectory() as directory:
            run=subprocess.run([sys.executable,'-B','-c',code],cwd=directory,capture_output=True,timeout=20)
            self.assertEqual(run.returncode,0,run.stderr.decode());self.assertEqual(list(Path(directory).iterdir()),[])

if __name__=='__main__':unittest.main()
