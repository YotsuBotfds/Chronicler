"""Bounded source/synthetic contracts; no native, World, network or real child."""
import ast
from copy import deepcopy
from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock
import zipfile

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("cbf_byte_contracts",ROOT/"scripts/cbf_090_default_artifact_reader.py")
Q=importlib.util.module_from_spec(spec);sys.modules[spec.name]=Q;spec.loader.exec_module(Q)
PUBLICATION=json.loads((ROOT/"tests/fixtures/cbf_090_default_artifact_publication.json").read_bytes())
NOW=datetime(2026,10,29,tzinfo=timezone.utc)


def probe(U,arm):
    prefix="/historical/tmp/cbf-090-default-env";source="/historical/work/"+arm;B=U.B;w=B.WHEELS[arm]
    runtime=dict(python="3.13.17",version="3.13.17 (synthetic)",implementation="CPython",platform="synthetic host",machine="x86_64",
        executable="/historical/python/bin/python3.13",prefix=prefix,affinity=[0],cpu_count=1,process_cpu_count=1,optimize=0,no_user_site=1,
        dont_write_bytecode=True,thread_env={**B.H.CAPS,"PYTHONHASHSEED":"0","OPENBLAS_THREAD_TIMEOUT":"16"},packages={n:"synthetic1" for n in B.A.PACKAGE_NAMES})
    env={k:runtime[k] for k in ("python","implementation","platform","machine","cpu_count","process_cpu_count","packages")}
    env.update(executable=prefix+"/bin/python",affinity_cpu_count=1,thread_env={k:v for k,v in runtime["thread_env"].items() if k!="CARGO_BUILD_JOBS"})
    native=prefix+"/lib/python3.13/site-packages/"+B.A.NATIVE_MEMBER
    return dict(source=dict(git_sha=B.SOURCES[arm],git_ref=None,package_dir=source+"/src/chronicler",package_digest="d"*64),
        native=dict(status="found",source="imported",module_file=native,bytes=w.native_size,sha256=w.native_sha256),schemas=deepcopy(B.EXPECTED_SCHEMAS),
        source_file=source+"/src/chronicler/__init__.py",native_file=native,environment=env,affinity=[0],prefix=prefix,runtime=runtime)


def result(U):
    B=U.B;p=probe(U,"candidate")
    rows=B.case_rows()
    for row in rows:row.update(status="complete",audit_sha256="a"*64)
    return dict(schema_version=1,qualified=True,status="exports_complete_pending_completed_job",sources=dict(B.SOURCES),crates=dict(B.CRATES),
        producer=dict(control_sha=Q.PRODUCER,run_id=str(Q.RUN),run_attempt="1",job_key="cbf-090-default-identity-v2",event="push",
            branch="lead/cloud-cbf-090-default-identity-v2-20261029",workflow_ref=B.A.REPOSITORY+"/.github/workflows/cbf-090-default-identity-v2.yml@refs/heads/lead/cloud-cbf-090-default-identity-v2-20261029"),
        cases=rows,expected_schemas=deepcopy(B.EXPECTED_SCHEMAS),actual_observations={a:{k:probe(U,a)[k] for k in ("schemas","native","source")} for a in B.SOURCES},
        CI_qualification=dict(B.CI_QUALIFICATION),native_sha256_by_arm={a:w.native_sha256 for a,w in B.WHEELS.items()},
        wheel_sha256_by_arm={a:w.sha256 for a,w in B.WHEELS.items()},normalization="metadata.generated_at only; original .log/run_manifest exclusions",
        limitations=["Exact CBF-to-090 default exports only; no checkpoint/RNG/science/performance/adoption grant",
            "Requires separate completed-job/publication and independent artifact qualification","Standard CI did not measure schemas; actual fresh fields stay null until real probes"],
        installer=dict(uv=dict(path="/historical/python/bin/uv",bytes=7,sha256="1"*64),bootstrap_python="/historical/python/bin/python"),
        installed_native_path=p["native_file"],installed_native_arm="candidate",runtime=p["runtime"],inventory_sha256=Q.INVENTORY_SHA,elapsed_wall_seconds=222.0)


def progress(U,r):
    B=U.B;prefix=Path(r["runtime"]["prefix"]);py=str(prefix/"bin/python");root=Path("/historical/tmp/evidence")
    roots={a:Path("/historical/work")/a for a in B.SOURCES};control=Path("/historical/work/control");uv=r["installer"]["uv"]["path"];boot=r["installer"]["bootstrap_python"]
    rows=[dict(at=0,event='resources',phase='initial',disk_free=12*Q.GIB,ram_available=2*Q.GIB)]
    def child(label,command,cwd=root):
        rows.extend([dict(at=0,event='resources',phase=label+':before',disk_free=12*Q.GIB,ram_available=2*Q.GIB),dict(at=1,event="child_start",label=label,command=command,cwd=str(cwd)),
            dict(at=2,event="child_cleanup",label=label,complete=True,cleanup_error=None),dict(at=3,event="child_exit",label=label,returncode=0)])
    child("install-exact-uv",[boot,"-m","pip","install","--disable-pip-version-check","--no-cache-dir","--only-binary=:all:","uv==0.13.6"])
    child("uv-version",[uv,"--version"]);child("locked-input-check",[uv,"lock","--project",str(roots["candidate"]),"--check"])
    child("fresh-locked-environment",[uv,"sync","--project",str(roots["candidate"]),"--frozen","--no-dev","--no-install-project","--no-build","--python",boot])
    child("fresh-environment-probe",[py,"-I","-B","-c",B.A.ENVIRONMENT_PROBE])
    for arm in B.SOURCES:
        child("install-"+arm,B.A.install_command(py,root/"wheels"/arm/B.A.WHEEL_NAME,uv))
        for case in B.H.CASES:
            cwd=root/"raw"/arm
            def p(stage):child(f"probe-{arm}-{case}-{stage}",[py,str(control/"scripts/cbf_090_default_identity.py"),"probe","--arm",arm,"--source-root",str(roots[arm]),"--expected-sha",B.SOURCES[arm],"--venv",str(prefix),"--out",str(root/"probes"/f"{arm}-{case}-{stage}.json")],cwd)
            p("before");child(f"world-{arm}-{case}",[py,str(roots[arm]/"scripts/turn_speed_identity.py"),"run",str(cwd),"--source-root",str(roots[arm]),"--case",case],cwd);p("after")
            child(f"audit-{arm}-{case}",[py,str(control/"scripts/arc_output_identity_qualification.py"),"inspect","--case-root",str(cwd/case),"--case",case,"--out",str(root/"audits"/f"{arm}-{case}.json")],cwd)
            rows.append(dict(at=4,event="case_complete",arm=arm,case=case,audit_sha256="a"*64))
    child("compare",[py,str(roots["candidate"]/"scripts/turn_speed_identity.py"),"compare",str(root/"raw/baseline"),str(root/"raw/candidate")])
    rows += [dict(at=5,event='resources',phase=p,disk_free=12*Q.GIB,ram_available=2*Q.GIB) for p in ('environment-prepared','inputs-prepared','prepared-baseline','prepared-candidate','input-transfer')]
    return rows,roots


def tiny_inputs(U):
    """Explicit synthetic capability; never changes a producer/module registry."""
    A=U.B.A;wheels={};archives={};pins={};members={};contents={};publications={};role_by_id={}
    def zipped(rows):
        stream=io.BytesIO()
        with zipfile.ZipFile(stream,'w') as z:
            for name,value in rows.items():z.writestr(name,value)
        return stream.getvalue()
    saved=json.loads((ROOT/'tests/fixtures/cbf_090_default_identity_inputs.json').read_bytes())['arms']
    def ci(arm,wp,wd,pp,pd):
        return dict(manifest=json.loads(wd['ci-native-wheel/manifest.json']),preflight=json.loads(pd['native-identity.json']),historical_paths_only=True,actual_fresh_schema_observation=None)
    for arm in U.B.SOURCES:
        payload=('synthetic-native-'+arm).encode();wh=zipped({A.NATIVE_MEMBER:payload});member='chronicler-agents/target/wheels/'+A.WHEEL_NAME
        wheels[arm]=A.WheelPin(arm+'-wheel',member,len(wh),Q.pin(wh)['sha256'],len(payload),Q.pin(payload)['sha256'])
        for kind,rows in [('wheel',{'ci-native-wheel/manifest.json':json.dumps({'synthetic':arm}).encode(),member:wh}),('preflight',{'native-identity.json':json.dumps({'synthetic':arm}).encode(),'native.xml':b'synthetic XML'})]:
            role=arm+'-'+kind;raw=zipped(rows);number=100+len(pins);old=U.B.ARTIFACTS[role]
            p=A.ArtifactPin(number,old.run_id,old.job_id,old.source,'synthetic-'+role,len(raw),Q.pin(raw)['sha256'],'2099-11-12T00:00:00Z',old.workflow)
            pins[role]=p;role_by_id[number]=role;archives['inputs/'+str(number)+'.zip']=raw
            selected=set(rows)-{'native.xml'};contents[role]=A.inspect_zip(io.BytesIO(raw),selected);members[role]=contents[role][0]
            artifact=deepcopy(saved[arm][kind]['artifact']);artifact.update(id=number,name=p.name,size_in_bytes=p.size,digest='sha256:'+p.sha256,expires_at=p.expiry)
            value=U.B.validate_publication(p,saved[arm]['run'],saved[arm]['job'],artifact,NOW);publications[role]={'before':value,'after':deepcopy(value)}
    arms={}
    for arm,w in wheels.items():
        arms[arm]=ci(arm,*contents[arm+'-wheel'],*contents[arm+'-preflight'])
        arms[arm]['wheel_members']=A.validate_wheel(contents[arm+'-wheel'][1][w.member],w)
    B=SimpleNamespace(A=A,SOURCES=U.B.SOURCES,ARTIFACTS=pins,WHEELS=wheels,bounded_zip=U.B.bounded_zip,validate_ci_arm=ci,validate_publication=U.B.validate_publication)
    C=SimpleNamespace(read_member=lambda archive,files,name:archives[name])
    admission=dict(publications=publications,arms=arms,members=members)
    return SimpleNamespace(B=B,C=C),archives,{n:Q.pin(v) for n,v in archives.items()},admission


class Contracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary=tempfile.TemporaryDirectory();cls.cache=Path(cls.temporary.name)
        cls.raw=Q.authenticate(ROOT/"scripts");cls.U=Q.load_modules(cls.cache,cls.raw)
    @classmethod
    def tearDownClass(cls):cls.temporary.cleanup()

    def test_actual_saved_completed_publication_and_expiry(self):
        self.assertEqual(Q.validate_metadata(self.U,deepcopy(PUBLICATION),NOW)["id"],Q.ARTIFACT)
        with self.assertRaises((RuntimeError,ValueError)):
            Q.validate_metadata(self.U,deepcopy(PUBLICATION),self.U.B.A.utc(Q.EXPIRY))

    def test_wrong_original_producer_or_closed_stage_refuses(self):
        for role,key,value in [("run","head_sha","0"*40),("run","run_attempt",2),("job","id",123366280070),("job","name","native-default-output-artifact-audit"),
                               ("artifacts","total_count",True),("jobs","total_count",2)]:
            with self.subTest(role=role,key=key):
                v=deepcopy(PUBLICATION);v[role][key]=value
                with self.assertRaises((RuntimeError,ValueError)):Q.validate_metadata(self.U,v,NOW)
        v=deepcopy(PUBLICATION);v["job"]["steps"][9]["conclusion"]="failure"
        with self.assertRaises((RuntimeError,ValueError)):Q.validate_metadata(self.U,v,NOW)
        v=deepcopy(PUBLICATION);v['jobs']['jobs'][0]['run_attempt']=True
        with self.assertRaises((RuntimeError,ValueError)):Q.validate_metadata(self.U,v,NOW)

    def test_actual_producer_result_field_shape_is_source_derived(self):
        v=result(self.U);self.assertEqual(len(Q.validate_result(self.U,v,Q.INVENTORY_SHA)),18)
        tree=ast.parse((ROOT/"scripts/cbf_090_default_identity.py").read_bytes())
        execute=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=="execute")
        initial=next(n.value for n in ast.walk(execute) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=="report" for t in n.targets))
        keys={ast.literal_eval(k) for k in initial.keys}
        self.assertEqual(set(v),keys|{"installer","installed_native_path","installed_native_arm","runtime","inventory_sha256","elapsed_wall_seconds"})
        self.assertEqual(ast.literal_eval(initial.values[[ast.literal_eval(k) for k in initial.keys].index("limitations")]),v["limitations"])

    def test_result_refuses_old_schema_missing_observations_and_boolean_versions(self):
        for key,value in [("baseline",self.U.B.SOURCES["baseline"]),("inventory_sha256","0"*64),("schema_version",True),
                          ("qualified",False),("actual_observations",{"baseline":None,"candidate":None}),("elapsed_wall_seconds",True)]:
            with self.subTest(key=key):
                v=result(self.U);v[key]=value
                with self.assertRaises((RuntimeError,ValueError)):Q.validate_result(self.U,v,Q.INVENTORY_SHA)
        v=result(self.U);v["cases"].reverse()
        with self.assertRaises((RuntimeError,ValueError)):Q.validate_result(self.U,v,Q.INVENTORY_SHA)

    def test_historical_probes_need_no_local_producer_files(self):
        runtime=None
        for arm in self.U.B.SOURCES:
            v=probe(self.U,arm);runtime=Q.validate_probe(self.U,v,arm,"d"*64,runtime)
        self.assertEqual(runtime["prefix"],"/historical/tmp/cbf-090-default-env")

    def test_probe_native_schema_path_and_duplicate_environment_faults(self):
        for section,key,value in [("source","package_digest","0"*64),("native","source","import_path"),("native","sha256","0"*64),
            ("runtime","cpu_count",True),("runtime","optimize",1),("runtime","prefix","/different/prefix"),
            ("environment","affinity_cpu_count",2),("environment","executable","/outside/python")]:
            with self.subTest(section=section,key=key):
                v=probe(self.U,"candidate");v[section][key]=value
                with self.assertRaises((RuntimeError,ValueError)):Q.validate_probe(self.U,v,"candidate","d"*64)
        v=probe(self.U,"candidate");v["schemas"]["AgentSimulator"]["version"]=True
        with self.assertRaises((RuntimeError,ValueError)):Q.validate_probe(self.U,v,"candidate","d"*64)
        v=probe(self.U,"candidate");v['affinity']=[False]
        with self.assertRaises((RuntimeError,ValueError)):Q.validate_probe(self.U,v,"candidate","d"*64)

    def test_last_probe_graph_36_beforeafter_and_driver_records(self):
        B=self.U.B;v=result(self.U);inventory={};rows={}
        for arm in B.SOURCES:
            for case in B.H.CASES:
                p=probe(self.U,arm)
                for stage in ("before","after"):
                    n=f"probes/{arm}-{case}-{stage}.json";inventory[n]={};rows[n]=p
                n=f"probes/{arm}-{case}-which.txt";inventory[n]={};rows[n]="chronicler "+p["source_file"]+"\nnative "+p["native_file"]+" "+B.WHEELS[arm].native_sha256+"\n"
        fake=SimpleNamespace(**self.U.__dict__)
        fake.C=SimpleNamespace(core=SimpleNamespace(read_json=lambda path:rows[str(path).removeprefix('/meta/')]),git_source=SimpleNamespace(package_digest=lambda snapshot:"d"*64))
        fake.R=SimpleNamespace(historical=self.U.R.historical,bounded=lambda path:rows[str(path).removeprefix('/meta/')].encode())
        Q.verify_probes(fake,Path('/meta'),inventory,v,{a:{} for a in B.SOURCES},{'affinity':[0]})
        v['actual_observations']['candidate']['native']['sha256']='0'*64
        with self.assertRaises((RuntimeError,ValueError)):Q.verify_probes(fake,Path('/meta'),inventory,v,{a:{} for a in B.SOURCES},{'affinity':[0]})

    def test_all_seven_authenticate_before_module_execution(self):
        bad=dict(self.raw);bad['cbf_090_default_identity.py']=b'no execution'
        with tempfile.TemporaryDirectory() as t,mock.patch.object(Q,'compile_source',side_effect=AssertionError('unauthenticated exec')):
            with self.assertRaises(RuntimeError):Q.load_modules(Path(t),bad)
            self.assertEqual(list(Path(t).iterdir()),[])

    def test_immutable_capability_and_original_registries_unchanged(self):
        with self.assertRaises(FrozenInstanceError):self.U.arms.PYTHON='other'
        self.assertEqual(self.U.R.CONTROL,'74b2904dfc4acceb6c5c03a57aa8c2b6406ce4a6')
        self.assertEqual(self.U.B.A.SOURCES['baseline'],'c76efe8552b4c6c288ebb1f813e2c0a58e5957b1')
        tree=ast.parse((ROOT/'scripts/default_output_identity_reader.py').read_bytes())
        expected=ast.literal_eval(next(n.value for n in tree.body if isinstance(n,ast.Assign)
            and any(isinstance(t,ast.Name) and t.id=='BASELINE' for t in n.targets)))
        self.assertEqual(self.U.C.core.BASELINE,expected)

    def test_private_view_rejects_cache_and_symlink_alias(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);view=root/'authenticated-utilities';s=view/'scripts';s.mkdir(parents=True);p=s/'one.py';p.write_bytes(b'x');p.chmod(0o444);s.chmod(0o555);view.chmod(0o555)
            Q.verify_utility_view(root,{'one.py':b'x'})
            s.chmod(0o755);(s/'__pycache__').mkdir();s.chmod(0o555)
            with self.assertRaises(RuntimeError):Q.verify_utility_view(root,{'one.py':b'x'})

    def test_wrong_archive_refuses_before_zip_allocation(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'tiny';p.write_bytes(b'not the registered original')
            with mock.patch.object(Q.zipfile,'ZipFile',side_effect=AssertionError('must not allocate')):
                with self.assertRaises(RuntimeError):Q.open_archive(self.U,p)

    def test_four_input_complete_hash_member_publication_and_arm_graph(self):
        U,archives,inventory,admission=tiny_inputs(self.U)
        self.assertEqual(set(Q.verify_inputs(U,None,{},inventory,admission)),set(self.U.B.ARTIFACTS))
        for fault in ('member','publication','arm','extra','crossarm'):
            with self.subTest(fault=fault):
                changed=deepcopy(admission);inv=dict(inventory);original=dict(archives)
                if fault=='member':changed['members']['candidate-wheel'].pop(next(iter(changed['members']['candidate-wheel'])))
                elif fault=='publication':changed['publications']['candidate-preflight']['before']['identity']['source']='wrong'
                elif fault=='arm':changed['arms']['candidate']['wheel_members'][U.B.A.NATIVE_MEMBER]['sha256']='0'*64
                elif fault=='extra':inv['inputs/unregistered.zip']=Q.pin(b'x')
                else:archives['inputs/102.zip']=archives['inputs/100.zip']
                with self.assertRaises((RuntimeError,ValueError)):Q.verify_inputs(U,None,{},inv,changed)
                archives.clear();archives.update(original)

    def test_exact_80_child_cleanup_and_argv_ledger(self):
        r=result(self.U);rows,roots=progress(self.U,r)
        with tempfile.TemporaryDirectory() as t:
            p=Path(t);(p/'progress.jsonl').write_text(''.join(json.dumps(v)+'\n' for v in rows))
            self.assertEqual(Q.verify_progress(self.U,p,r,roots,r['runtime'])['owned_children'],80)

    def test_cleanup_missing_exit_failure_extra_world_and_wrong_args_refuse(self):
        r=result(self.U);rows,roots=progress(self.U,r)
        for fault in ('missing_cleanup','bad_exit','extra_child','wrong_world_argv','no_reinstall'):
            with self.subTest(fault=fault),tempfile.TemporaryDirectory() as t:
                changed=deepcopy(rows)
                if fault=='missing_cleanup':changed.remove(next(v for v in changed if v['event']=='child_cleanup'))
                elif fault=='bad_exit':next(v for v in changed if v['event']=='child_exit')['returncode']=True
                elif fault=='extra_child':changed.append(dict(at=5,event='child_start',label='world-extra',command=['/x'],cwd='/x'))
                elif fault=='wrong_world_argv':next(v for v in changed if v['event']=='child_start' and v['label'].startswith('world-'))['command'][1]='/wrong/driver.py'
                else:next(v for v in changed if v['event']=='child_start' and v['label']=='install-baseline')['command'].remove('--reinstall')
                p=Path(t);(p/'progress.jsonl').write_text(''.join(json.dumps(v)+'\n' for v in changed))
                with self.assertRaises((RuntimeError,ValueError)):Q.verify_progress(self.U,p,r,roots,r['runtime'])

    def test_case_comparator_exception_and_copy_mutation_prevent_retirement(self):
        for fault in ('compare','mutation'):
            with self.subTest(fault=fault),tempfile.TemporaryDirectory() as t:
                root=Path(t);view=root/'candidate';view.mkdir();(view/'source.py').write_bytes(b'x');view_map=self.U.C.core.payload_inventory(view)
                case='off_s42';name='raw/baseline/off_s42/state.json';inventory={name:Q.pin(b'x')}
                def copy(archive,files,names,destination,all_pins):
                    (destination/'raw/baseline/off_s42').mkdir(parents=True);(destination/name).write_bytes(b'x');return {}
                C=SimpleNamespace(copy_members=copy,core=SimpleNamespace(verify_cases=lambda *args:({case:1},[]),payload_inventory=self.U.C.core.payload_inventory))
                def compare(*args):
                    if fault=='compare':raise RuntimeError('injected comparator')
                    (root/'derived-case-scratch'/name).write_bytes(b'changed');return {}
                R=SimpleNamespace(write=self.U.R.write,compare_supervised=compare,retire_case=lambda c,s,e,m:self.U.R.retire_case(self.U.C,s,e,m))
                U=SimpleNamespace(B=self.U.B,C=C,R=R,arms=self.U.arms)
                with self.assertRaises((RuntimeError,ValueError)):
                    Q.verify_case_pair(U,None,{name:None},inventory,[],view,view_map,root,case,Q.time.monotonic()+60,[])
                self.assertTrue((root/'derived-case-scratch').exists())

    def test_baseline_driver_final_rehash_refuses_mutation(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);p=root/'baseline-driver.py';p.write_bytes(b'first');descriptor=Q.pin(p.read_bytes())
            self.U.R.verify_baseline_driver(self.U.C,root,descriptor);p.write_bytes(b'other')
            with self.assertRaises((RuntimeError,ValueError)):self.U.R.verify_baseline_driver(self.U.C,root,descriptor)

    def test_600_second_negative_first_finalizer_demotes_late_terminal_write(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);(root/'logs').mkdir();report={'qualified':True};clock=[100.];states=[];original=self.U.R.write
            def write(path,value):
                original(path,value)
                if Path(path).name=='reader-result.json':
                    states.append(value['qualified'])
                    if value['qualified']:clock[0]=701.
            with mock.patch.object(self.U.R.time,'monotonic',side_effect=lambda:clock[0]),mock.patch.object(self.U.R,'write',side_effect=write):
                self.assertEqual(self.U.R.finalize(self.U.C,root,report,100.,700.,True),1)
            self.assertEqual(states,[False,True,False]);self.assertFalse(json.loads((root/'publication/reader-result.json').read_bytes())['qualified'])

    def test_expiry_crossing_during_finalization_cannot_grant(self):
        clock=[datetime(2026,11,12,8,33,40,tzinfo=timezone.utc)]
        def finish(C,root,report,*args):
            (root/'publication').mkdir();self.U.R.write(root/'publication/reader-result.json',report)
            clock[0]=datetime(2026,11,12,8,33,41,tzinfo=timezone.utc);return 0
        with tempfile.TemporaryDirectory() as t,mock.patch.object(Q,'datetime') as dt,mock.patch.object(self.U.R,'finalize',side_effect=finish):
            dt.now.side_effect=lambda zone:clock[0];report={'qualified':True}
            self.assertEqual(Q.finalize(self.U,Path(t),report,0,600,True),1);self.assertFalse(report['qualified'])

    def test_closed_authority_and_explicit_execution_before_any_setup(self):
        with self.assertRaises(RuntimeError):Q.audit(SimpleNamespace(execute=False))
        with self.assertRaises(RuntimeError):Q.reader_registration({'GITHUB_EVENT_NAME':'workflow_dispatch'})

    def test_bootstrap_refusals_publish_negative_before_any_setup(self):
        for fault in ('authentication','initial_resources'):
            with self.subTest(fault=fault),tempfile.TemporaryDirectory() as t:
                root=Path(t)/'evidence';calls=[]
                class Supervisor:
                    cleanup_complete=True
                    def __init__(self,*args):calls.append('supervisor')
                    def admission(self,*args):
                        calls.append(('admission',args))
                        raise RuntimeError('injected admission refusal')
                boot=SimpleNamespace(Supervisor=Supervisor,CAPS={})
                auth=mock.Mock(side_effect=RuntimeError('injected authentication refusal')) if fault=='authentication' else mock.Mock(return_value={'arc_output_identity_qualification.py':b'synthetic'})
                with mock.patch.object(Q,'reader_registration',return_value='a'*40),mock.patch.dict(Q.os.environ,{'GITHUB_RUN_ID':'1','GITHUB_WORKFLOW_REF':'synthetic'},clear=True), \
                     mock.patch.object(Q,'authenticate',auth),mock.patch.object(Q,'compile_source',return_value=boot), \
                     mock.patch.object(Q.os,'sched_getaffinity',return_value={4}),mock.patch.object(Q.os,'sched_setaffinity'), \
                     mock.patch.object(Q,'load_modules',side_effect=AssertionError('no setup before admission')) as load:
                    self.assertEqual(Q.audit(SimpleNamespace(execute=True,evidence=str(root),python=str(Path(t)/'prefix/bin/python'))),1)
                load.assert_not_called();saved=json.loads((root/'publication/reader-result.json').read_bytes())
                self.assertIs(saved['qualified'],False);self.assertEqual(saved['error_stage'],'authenticate' if fault=='authentication' else 'initial')
                self.assertEqual(saved['error'],'RuntimeError');self.assertGreaterEqual(saved['reader_seconds'],0)
                self.assertEqual(calls,[] if fault=='authentication' else ['supervisor',('admission',('initial',12,2))])

    def test_own_source_keeps_full_git_snapshot_and_checks_only_selected_sparse_bytes(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);path=root/'selected.py';path.write_bytes(b'selected');path.chmod(0o644)
            row={**Q.pin(path.read_bytes()),'mode':0o644};snapshot={'files':{'selected.py':row,'unselected.py':dict(row)}}
            U=SimpleNamespace(C=SimpleNamespace(git_source=SimpleNamespace(snapshot=lambda *a:deepcopy(snapshot)),core=self.U.C.core))
            with mock.patch.object(Q,'ROOT',root),mock.patch.object(Q,'selected_source_names',return_value=('selected.py',)), \
                 mock.patch.object(Q.subprocess,'check_output',side_effect=['a'*40,b'','a'*40,b'']):
                observed=Q.own_source(U,'a'*40)
                self.assertEqual(observed['committed_snapshot'],snapshot);self.assertEqual(observed['selected_files'],{'selected.py':row})
                self.assertFalse((root/'unselected.py').exists());path.write_bytes(b'mutation')
                with self.assertRaises(RuntimeError):Q.own_source(U,'a'*40)

    def test_sparse_workflow_selects_exact_physical_source_contract(self):
        text=(ROOT/Q.TEMPLATE).read_text();block=text.split('          sparse-checkout: |\n',1)[1].split('      - name:',1)[0]
        names=tuple(line.strip().removeprefix('/') for line in block.splitlines() if line.strip())
        self.assertEqual(len(names),len(set(names)))
        self.assertEqual(set(line.strip().removeprefix('/') for line in block.splitlines() if line.strip()),set(Q.selected_source_names()))
        self.assertIn('          sparse-checkout-cone-mode: false',text)

    def test_dormant_template_pins_verified_actions_and_original_bounds(self):
        text=(ROOT/Q.TEMPLATE).read_text();self.assertEqual(Q.pin(text.encode())['sha256'],Q.TEMPLATE_SHA)
        self.assertIn('actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02',text)
        self.assertIn('timeout --kill-after=5s 610s',text);self.assertIn(Q.BRANCH,text)
        Q.workflow_contract(ROOT,active_required=False)
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);template=root/Q.TEMPLATE;template.parent.mkdir(parents=True);template.write_bytes((ROOT/Q.TEMPLATE).read_bytes())
            active=root/Q.WORKFLOW;active.parent.mkdir(parents=True);active.write_bytes(template.read_bytes());Q.workflow_contract(root)
            active.write_bytes(template.read_bytes()+b'\n# changed\n')
            with self.assertRaises(RuntimeError):Q.workflow_contract(root)

    def test_describe_does_not_load_helpers_or_transfer(self):
        with mock.patch.object(Q,'authenticate',side_effect=AssertionError('no helper activation')),contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(Q.main(['describe']),0)
        self.assertFalse(json.loads(output.getvalue())['original_byte_audit_performed'])


if __name__=='__main__':unittest.main()
