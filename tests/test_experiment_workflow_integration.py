"""Explicit tiny operator workflows; producer dry-run evidence, not adoption."""
from dataclasses import asdict,replace
import hashlib
import json
import os
from pathlib import Path
import runpy
import shutil
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
from chronicler import experiment_receipt_inspector as inspector

ROOT=Path(__file__).resolve().parents[1]
CAMPAIGN=runpy.run_path(str(ROOT/'scripts/campaign_logistics_demo.py'))
MEMOME=runpy.run_path(str(ROOT/'scripts/memome_demo.py'))

def encoded(value):return json.dumps(value,sort_keys=True,separators=(',',':')).encode()
def session_fixture(kernel):
    if kernel=='m60a':
        policy,topology=CAMPAIGN['illustrative_policy'](),CAMPAIGN['fixture_topology']()
        initial=CAMPAIGN['fixture_session'](policy,topology).state
        return es.create_campaign_session(policy=policy,topology=topology,campaign_id=initial.campaign_id,turn=0,staging=initial.staging,target=initial.target,soldiers=initial.soldiers,stocks=initial.stocks)
    people,_=MEMOME['unit_tables']()
    return es.create_memome_session(policy=MEMOME['illustrative_policy'](),genesis_turn=0,participants=people)

def uncertain_worker():
    transport=es.transport_policy_from_text(Path('transport.json').read_text())
    original=es.os.fsync
    def fsync(fd):
        if stat.S_ISDIR(os.fstat(fd).st_mode):raise OSError('test-owned post-replace directory fsync failure')
        return original(fd)
    with mock.patch.object(es.os,'fsync',fsync):
        try:operations.apply_operation('campaign.json',transport=transport,submission=Path('turn1.json').read_bytes())
        except es.DurabilityUncertain as error:print(json.dumps(error.operation_receipt.as_payload(),sort_keys=True))
        else:raise AssertionError('expected injected uncertain return')

class WorkflowCase(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.work=Path(temp.name)
        self.transport=es.documented_transport_policy();self.transport_file=self.work/'transport.json'
        self.transport_file.write_bytes(encoded(self.transport.as_payload()))
    def cli(self,script,*args,exit_code=0):
        command=[sys.executable,'-B',str(ROOT/'scripts'/script),*args]
        # Equal pre-command bytes in a fresh directory test both hash seeds,
        # without turning a second apply into a replay of the first mutation.
        with tempfile.TemporaryDirectory() as directory:
            clone=Path(directory)
            for path in self.work.iterdir():shutil.copy2(path,clone/path.name)
            run=subprocess.run(command,cwd=self.work,env=dict(os.environ,PYTHONHASHSEED='0'),capture_output=True,timeout=20)
            repeated=subprocess.run(command,cwd=clone,env=dict(os.environ,PYTHONHASHSEED='42'),capture_output=True,timeout=20)
            self.assertEqual((run.returncode,run.stdout,run.stderr),(repeated.returncode,repeated.stdout,repeated.stderr))
            def file_bytes(directory):
                paths=list(directory.iterdir())
                self.assertTrue(all(path.is_file() for path in paths))
                return {path.name:path.read_bytes() for path in paths}
            final_bytes=file_bytes(self.work)
            self.assertEqual(final_bytes,file_bytes(clone))
            final_digests={name:hashlib.sha256(raw).hexdigest() for name,raw in sorted(final_bytes.items())}
        print(json.dumps({'script':script,'arguments':args,'seed0_seed42_equal':True,'exit_code':run.returncode,
                          'stdout_sha256':hashlib.sha256(run.stdout).hexdigest(),'stderr_sha256':hashlib.sha256(run.stderr).hexdigest(),
                          'resulting_file_bytes_seed0_seed42_equal':True,'resulting_files_sha256':final_digests},sort_keys=True))
        self.assertEqual(run.returncode,exit_code,run.stderr.decode(errors='replace'))
        payload=json.loads((run.stdout if exit_code==0 else run.stderr).decode())
        if '--path' in args and args[args.index('--path')+1] in final_bytes:
            name=args[args.index('--path')+1]
            loaded=es.load_session(self.work/name,transport=self.transport)
            self.assertEqual(loaded.digest,final_digests[name])
            identity=(payload.get('intended') or payload.get('current') or payload.get('base'))
            if identity is not None:
                self.assertEqual((identity['generation'],identity['turn'],identity['file_digest'],identity['session_digest']),
                                 (loaded.generation,loaded.turn,loaded.digest,loaded.envelope.session_digest))
            if 'file_digest' in payload:self.assertEqual(payload['file_digest'],loaded.digest)
            if 'digest' in payload:self.assertEqual(payload['digest'],loaded.digest)
        return payload
    def create(self,kernel,name):
        self.cli('experiment_session.py','create','--kernel',kernel,'--path',name,'--transport','transport.json','--demo')
        loaded=es.load_session(self.work/name,transport=self.transport)
        self.assertEqual((loaded.generation,loaded.turn),(1,0));return loaded
    def submit(self,name,record,filename,exit_code=0):
        (self.work/filename).write_bytes(encoded(asdict(record)))
        return self.cli('session_operation.py','--enable','apply','--path',name,'--transport','transport.json','--submission',filename,exit_code=exit_code)
    def inspect(self,name,turn):
        return self.cli('experiment_receipts.py','--enable','--path',name,'--transport','transport.json','--turn',str(turn))
    def test_campaign_stop_resume_replenish_close_terminal_and_historical_replay(self):
        loaded=self.create('m60a','campaign.json');expected=session_fixture('m60a');ticks={}
        oracle={1:('ready',2),2:('marching',4),3:('arrived',6),4:('arrived',8),5:('returning',10),6:('closed',12),7:('closed',12)}
        for turn in range(1,8):
            # Public reload is the restart boundary before every explicit tick.
            loaded=es.load_session(self.work/'campaign.json',transport=self.transport)
            tick=CAMPAIGN['fixture_tick'](loaded.session.session,turn);ticks[turn]=tick
            result=self.submit('campaign.json',tick,f'campaign-turn-{turn}.json')
            self.assertEqual(result['status'],'committed_durable')
            expected=es.apply_campaign_tick(expected,tick).session
            loaded=es.load_session(self.work/'campaign.json',transport=self.transport)
            self.assertEqual((loaded.generation,loaded.turn),(turn+1,turn))
            state=loaded.session.session.state
            self.assertEqual((state.phase,state.consumed_food),oracle[turn])
            if turn==2:self.assertEqual((loaded.generation,loaded.turn),(3,2))
            if turn==4:
                self.assertEqual((state.credited_food,dict((s.region,s.rations) for s in state.stocks)[2]),(2,2))
                self.assertEqual(tuple(s.rations for s in state.soldiers),(6,6))
                row=self.inspect('campaign.json',4)['turns'][0]['campaign']['receipt']
                self.assertEqual([r['granted'] for r in row['replenishments']],[2,2])
        self.assertEqual(cl.canonical_bytes(loaded.session.session),cl.canonical_bytes(expected.session))
        self.assertEqual(loaded.session.history,expected.history)
        state=loaded.session.session.state
        self.assertEqual((state.initial_food,state.credited_food,state.consumed_food,state.deserted_food),(20,2,12,0))
        self.assertEqual(dict((s.region,s.rations) for s in state.stocks),{0:0,1:8,2:2})
        self.assertEqual(tuple(s.rations for s in state.soldiers),(0,0))
        raw=(self.work/'campaign.json').read_bytes()
        for turn in (1,4):
            report=self.inspect('campaign.json',turn)
            self.assertEqual((report['generation'],report['latest_turn']),(8,7))
            self.assertEqual(report['file_digest'],hashlib.sha256(raw).hexdigest())
            self.assertEqual(report['turns'][0]['campaign']['receipt'],json.loads(cl.canonical_bytes(expected.session.cursor.receipts[turn-1])))
        replay=self.submit('campaign.json',ticks[4],'campaign-turn-4.json')
        self.assertEqual(replay['status'],'replay_no_write');self.assertEqual(replay['base']['generation'],8)
        self.assertIsNone(replay['intended']);self.assertEqual((self.work/'campaign.json').read_bytes(),raw)
        conflict=replace(ticks[4],credits=(replace(ticks[4].credits[0],rations=3),))
        rejected=self.submit('campaign.json',conflict,'campaign-conflict.json',exit_code=3)
        self.assertEqual(rejected['status'],'rejected');self.assertEqual((self.work/'campaign.json').read_bytes(),raw)
    def test_memome_reopened_latest_history_is_not_rolled_back_by_noncanonical_replay(self):
        self.create('m68a','memome.json');expected=session_fixture('m68a');_,batches=MEMOME['unit_tables']()
        for batch in batches:
            self.assertEqual(self.submit('memome.json',batch,f'batch-{batch.turn}.json')['status'],'committed_durable')
            expected=es.apply_memome_batch(expected,batch).session
            reopened=es.load_session(self.work/'memome.json',transport=self.transport)
            self.assertEqual((reopened.generation,reopened.turn),(batch.turn+1,batch.turn))
        loaded=es.load_session(self.work/'memome.json',transport=self.transport)
        self.assertEqual(mm.checkpoint_json(loaded.session.ledger,loaded.session.policy),mm.checkpoint_json(expected.ledger,expected.policy))
        raw=(self.work/'memome.json').read_bytes();report=self.inspect('memome.json',1)
        self.assertEqual((report['generation'],report['latest_turn']),(4,3))
        receipts={r['proposal_id']:r for r in report['turns'][0]['memome']['receipts']}
        self.assertEqual(tuple(receipts['minority'][k] for k in ['candidate_weight','electorate_weight','threshold','draw','reason']),(1,3,200,199,'accepted'))
        self.assertEqual(tuple(receipts['prestige'][k] for k in ['candidate_weight','electorate_weight','threshold','draw','reason']),(5,6,961,960,'accepted'))
        self.assertEqual(receipts['incompatible']['reason'],'incompatible')
        self.assertEqual(self.inspect('memome.json',3)['turns'][0]['memome']['receipts'][0]['reason'],'absent_candidate')
        self.assertIn('unavailable',report['turns'][0]['memome']['individual_electorate_votes'])
        replay=self.submit('memome.json',batches[0],'batch-1.json');self.assertEqual(replay['status'],'replay_no_write')
        self.assertEqual((replay['base']['generation'],replay['base']['turn']),(4,3));self.assertEqual((self.work/'memome.json').read_bytes(),raw)
        altered=replace(batches[0],proposals=(replace(batches[0].proposals[0],draw=198),)+batches[0].proposals[1:])
        self.assertEqual(self.submit('memome.json',altered,'batch-conflict.json',exit_code=3)['status'],'rejected')
        self.assertEqual((self.work/'memome.json').read_bytes(),raw)
        for turn in (0,4):self.assertFalse(self.inspect('memome.json',turn)['turns'][0]['available'])
        self.assertEqual(es.load_session(self.work/'memome.json',transport=self.transport).session,loaded.session)
    def test_uncertain_child_publication_visible_inspection_and_reconciliation_never_retry(self):
        initial=self.create('m60a','campaign.json');tick=CAMPAIGN['fixture_tick'](initial.session.session,1)
        (self.work/'turn1.json').write_bytes(encoded(asdict(tick)))
        run=subprocess.run([sys.executable,'-B',str(Path(__file__)),'--uncertain-worker'],cwd=self.work,capture_output=True,timeout=20)
        self.assertEqual(run.returncode,0,run.stderr.decode());receipt=json.loads(run.stdout)
        self.assertEqual(receipt['status'],'durability_uncertain');raw=(self.work/'campaign.json').read_bytes()
        report=self.inspect('campaign.json',1);self.assertEqual((report['generation'],report['latest_turn']),(2,1))
        self.assertEqual(report['file_digest'],receipt['intended']['file_digest'])
        observation=self.cli('session_operation.py','--enable','reconcile','--path','campaign.json','--transport','transport.json','--expectation-json',json.dumps(receipt['expectation']))
        self.assertEqual(observation['status'],'intended_visible_durability_unknown');self.assertFalse(observation['writes'])
        self.assertEqual((self.work/'campaign.json').read_bytes(),raw)
        wrong=dict(receipt['expectation'],target='different.json')
        rejected=self.cli('session_operation.py','--enable','reconcile','--path','campaign.json','--transport','transport.json','--expectation-json',json.dumps(wrong),exit_code=3)
        self.assertEqual(rejected['status'],'rejected');self.assertEqual((self.work/'campaign.json').read_bytes(),raw)

if __name__=='__main__':
    if sys.argv[1:]==['--uncertain-worker']:uncertain_worker()
    else:unittest.main()
