"""Tiny stdlib contracts; never a real archive, audit, native import or world."""
import ast
from copy import deepcopy
from datetime import datetime,timezone
import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import shutil
import stat
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest import mock
import zipfile

PATH=Path(__file__).resolve().parents[1]/"scripts/native_default_output_artifact_reader.py"
spec=importlib.util.spec_from_file_location("native_artifact_reader_contracts",PATH)
R=importlib.util.module_from_spec(spec);sys.modules[spec.name]=R;spec.loader.exec_module(R)


def encoded(value):return json.dumps(value,sort_keys=True).encode()


def zip_bytes(rows):
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,"w",compression=zipfile.ZIP_STORED) as archive:
        for name,raw in rows:archive.writestr(name,raw)
    return stream.getvalue()


def metadata():
    names={7:"Check unchanged original pure contracts",8:"Check new pure adapter contracts",
        10:"Execute only after separate source and activation review",11:"Retain complete positive or negative evidence"}
    job=dict(id=R.JOB,run_id=R.RUN,run_attempt=1,head_sha=R.CONTROL,name="native-default-output-identity",
        status="completed",conclusion="success",steps=[dict(number=n,name=name,status="completed",conclusion="success") for n,name in names.items()])
    artifact=dict(id=R.ARTIFACT,name=f"native-default-output-identity-{R.RUN}-1",size_in_bytes=R.ARCHIVE_BYTES,
        digest="sha256:"+R.ARCHIVE_SHA,expired=False,expires_at=R.EXPIRY,
        workflow_run=dict(id=R.RUN,head_sha=R.CONTROL,repository_id=1187468861,head_repository_id=1187468861))
    run=dict(id=R.RUN,run_attempt=1,head_sha=R.CONTROL,head_branch="lead/cloud-native-default-output-identity-20261029",
        event="push",path=".github/workflows/native-default-output-identity.yml",status="completed",conclusion="success",
        repository=dict(id=1187468861,full_name=R.REPO))
    return dict(run=run,jobs=dict(total_count=1,jobs=[job]),artifacts=dict(total_count=1,artifacts=[artifact]))


def runtime(A):
    return dict(python=A.PYTHON,version=A.PYTHON+" synthetic",implementation="CPython",platform="synthetic Linux",
        machine="x86_64",executable="/old/python/bin/python3.13",prefix="/old/temp/native-default-identity-env",affinity=[0],
        cpu_count=1,process_cpu_count=1,optimize=0,no_user_site=1,dont_write_bytecode=True,
        thread_env={**A.H.CAPS,"PYTHONHASHSEED":"0","OPENBLAS_THREAD_TIMEOUT":"16"},packages={n:"1.0" for n in A.PACKAGE_NAMES})


def probe(A,arm):
    rt=runtime(A);prefix=rt["prefix"];package="/old/work/"+arm+"/src/chronicler";native=prefix+"/lib/"+Path(A.NATIVE_MEMBER).name
    env={k:deepcopy(rt[k]) for k in ("python","implementation","platform","machine","cpu_count","process_cpu_count","packages")}
    env.update(executable=prefix+"/bin/python",affinity_cpu_count=1,thread_env={k:v for k,v in rt["thread_env"].items() if k!="CARGO_BUILD_JOBS"})
    return dict(source=dict(git_sha=A.SOURCES[arm],git_ref=None,package_dir=package,package_digest="1"*64),
        source_file=package+"/__init__.py",prefix=prefix,native_file=native,
        native=dict(status="found",source="imported",module_file=native,bytes=A.WHEELS[arm].native_size,sha256=A.WHEELS[arm].native_sha256),
        schemas=deepcopy(A.SCHEMAS),runtime=rt,environment=env,affinity=[0])


def result(A):
    return dict(qualified=True,status="exports_complete_pending_completed_job",baseline=A.SOURCES["baseline"],candidate=A.SOURCES["candidate"],
        control=R.CONTROL,producer=dict(control_sha=R.CONTROL,run_id=str(R.RUN),run_attempt="1",job_key="native-default-output-identity",
            workflow_ref=R.REPO+"/.github/workflows/native-default-output-identity.yml@refs/heads/lead/cloud-native-default-output-identity-20261029",
            event="push",branch="lead/cloud-native-default-output-identity-20261029"),
        cases=[dict(arm=arm,case=case,status="complete",audit_sha256="2"*64) for arm in A.SOURCES for case in A.H.CASES],
        normalization=R.NORMALIZATION,native_sha256_by_arm={arm:w.native_sha256 for arm,w in A.WHEELS.items()},
        wheel_sha256_by_arm={arm:w.sha256 for arm,w in A.WHEELS.items()},limitations=["synthetic"],installer={},
        installed_native_path="/old/temp/native-default-identity-env/lib/native.so",installed_native_arm="candidate",
        runtime=runtime(A),package_digests={arm:"1"*64 for arm in A.SOURCES},inventory_sha256="3"*64,elapsed_wall_seconds=257.0)


class Contracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.base=Path(cls.tmp.name)
        # Synthetic resource observation only; physical source-copy fixture <80KiB.
        with mock.patch.object(R.shutil,"disk_usage",return_value=SimpleNamespace(free=16*R.GIB)):
            cls.C=R.load_kernels(cls.base/"kernels",create=True)
        cls.A=R.producer()

    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()

    def setUp(self):
        if shutil.disk_usage(tempfile.gettempdir()).free<3*R.GIB+2*1024**2:
            self.fail("pure fixtures stopped before real floor reserve")

    def test_default_and_unapproved_audit_are_inert(self):
        with mock.patch.object(R,"producer",side_effect=AssertionError("producer import")), \
             mock.patch.object(Path,"mkdir",side_effect=AssertionError("mkdir")), contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(R.main([]),0)
            with self.assertRaisesRegex(R.Refusal,"inactive"):R.audit(SimpleNamespace(execute=False))
        self.assertEqual(json.loads(out.getvalue())["new_worlds"],0)

    def test_closed_registration_refuses_wrong_event_branch_attempt_before_io(self):
        good=dict(GITHUB_ACTIONS="true",GITHUB_REPOSITORY=R.REPO,GITHUB_EVENT_NAME="push",GITHUB_REF="refs/heads/"+R.ACTIVE_BRANCH,
            GITHUB_WORKFLOW_REF=R.REPO+"/"+R.WORKFLOW_PATH+"@refs/heads/"+R.ACTIVE_BRANCH,GITHUB_JOB=R.JOB_KEY,
            GITHUB_RUN_ATTEMPT="1",GITHUB_RUN_ID="42",GITHUB_SHA="a"*40)
        R.registration(good)
        for field,value in (("GITHUB_EVENT_NAME","workflow_dispatch"),("GITHUB_REF","refs/heads/main"),("GITHUB_RUN_ATTEMPT","2"),
            ("GITHUB_JOB","other"),("GITHUB_RUN_ID",True),("GITHUB_WORKFLOW_REF","other")):
            with self.subTest(field=field),self.assertRaises(R.Refusal):R.registration(dict(good,**{field:value}))

    def test_all_kernel_bytes_authenticate_before_import_or_destination_creation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/"scripts").mkdir()
            for name in R.KERNELS:(root/"scripts"/name).write_bytes((R.ROOT/"scripts"/name).read_bytes())
            (root/"scripts/export_study_git.py").write_bytes(b"raise AssertionError('never execute')")
            with mock.patch.object(R,"ROOT",root),mock.patch.object(R,"compile_module",side_effect=AssertionError("exec")):
                with self.assertRaises(R.Refusal):R.load_kernels(root/"derived",create=True)
            self.assertFalse((root/"derived").exists())

    def test_private_kernels_and_old_registries_remain_byte_identical(self):
        self.assertEqual(set(self.C.STUDIES),{"arc","recovered"})
        self.assertEqual(self.C.core.NATIVE_SHA,self.A.WHEELS["baseline"].native_sha256)
        self.assertNotEqual(self.C.core.CANDIDATE,self.A.SOURCES["candidate"])
        for name,(size,digest) in R.KERNELS.items():
            path=self.base/"kernels"/name
            self.assertEqual(R.pin(path.read_bytes()),dict(bytes=size,sha256=digest))
            self.assertEqual(stat.S_IMODE(path.stat().st_mode),0o444)
        self.assertEqual({p.name for p in (self.base/"kernels").iterdir()},set(R.KERNELS))

    def test_actual_metadata_schema_and_typed_completion_identity(self):
        good=metadata();now=datetime(2026,10,29,tzinfo=timezone.utc)
        self.assertEqual(R.validate_metadata(good,now)["artifact"],R.ARTIFACT)
        bads=[]
        for role,field,value in (("run","run_attempt",True),("run","head_sha","0"*40),("run","event","workflow_dispatch")):
            bad=deepcopy(good);bad[role][field]=value;bads.append(bad)
        bad=deepcopy(good);bad["jobs"]["jobs"][0]["steps"][0]["name"]="wrong";bads.append(bad)
        for field,value in (("expired",0),("size_in_bytes",True),("digest","sha256:"+"0"*64),("expires_at","2099-01-01T00:00:00Z")):
            bad=deepcopy(good);bad["artifacts"]["artifacts"][0][field]=value;bads.append(bad)
        for i,bad in enumerate(bads):
            with self.subTest(i=i),self.assertRaises(R.Refusal):R.validate_metadata(bad,now)
        with self.assertRaises(R.Refusal):R.validate_metadata(good,datetime(2099,1,1,tzinfo=timezone.utc))

    def test_per_arm_result_is_not_an_old_scalar_projection_and_order_is_exact(self):
        good=result(self.A);self.assertEqual(len(R.validate_result(good,self.A.H.CASES,"3"*64,self.A)),18)
        bads=[]
        for field,value in (("native_sha256_by_arm",{"baseline":self.A.WHEELS["baseline"].native_sha256,"candidate":self.A.WHEELS["baseline"].native_sha256}),
            ("status","complete"),("normalization",self.C.NORMALIZATION),("cases",list(reversed(good["cases"]))),("inventory_sha256","0"*64)):
            bad=deepcopy(good);bad[field]=value;bads.append(bad)
        bad=deepcopy(good);bad["native_sha256"]="0"*64;bads.append(bad)
        for i,bad in enumerate(bads):
            with self.subTest(i=i),self.assertRaises(R.Refusal):R.validate_result(bad,self.A.H.CASES,"3"*64,self.A)

    def test_historical_probe_paths_are_never_resolved_on_audit_filesystem(self):
        good=probe(self.A,"baseline")
        with mock.patch.object(Path,"resolve",side_effect=AssertionError("historical filesystem resolution")):
            R.validate_probe(good,"baseline",self.A,"1"*64)
        for value in ("/old//work","/old/../work","relative","/old/./work","/old\\work"):
            with self.subTest(value=value),self.assertRaises(R.Refusal):R.historical(value)

    def test_each_native_runtime_environment_duplicate_is_cross_linked(self):
        good=probe(self.A,"baseline");rt=R.validate_probe(good,"baseline",self.A,"1"*64)
        R.validate_probe(probe(self.A,"candidate"),"candidate",self.A,"1"*64,rt)
        changes=[("native","status","absent"),("native","source","import_path"),("native","module_file","/other.so"),
            ("native","sha256",self.A.WHEELS["candidate"].native_sha256),("environment","cpu_count",True),
            ("environment","affinity_cpu_count",2),("environment","executable","/other/python"),
            ("runtime","optimize",False),("runtime","prefix","/other/prefix"),("source","package_digest","0"*64)]
        for section,key,value in changes:
            bad=deepcopy(good);bad[section][key]=value
            with self.subTest(section=section,key=key),self.assertRaises(R.Refusal):R.validate_probe(bad,"baseline",self.A,"1"*64,rt)
        for section,key in (("environment","packages"),("environment","thread_env"),("runtime","packages")):
            bad=deepcopy(good);bad[section][key]={}
            with self.subTest(section=section,key=key),self.assertRaises(R.Refusal):R.validate_probe(bad,"baseline",self.A,"1"*64,rt)

    def test_outer_digest_is_checked_before_zip_allocation(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"wrong.zip";path.write_bytes(b"not a real registered archive")
            with mock.patch.object(R.zipfile,"ZipFile",side_effect=AssertionError("ZIP allocation")):
                with self.assertRaisesRegex(R.Refusal,"before ZIP allocation"):R.open_archive(self.C,path)

    def test_outer_sealed_inventory_streams_all_members_and_crc(self):
        payload=b"UNSELECTED-SYNTHETIC-PAYLOAD";filemap={"data":R.pin(payload)}
        raw=zip_bytes([("data",payload),("inventory.json",encoded(filemap)),("result.json",encoded({"inventory_sha256":R.pin(encoded(filemap))["sha256"]}))])
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            files,inventory,digest=R.complete_inventory(self.C,archive)
            self.assertEqual(set(files),{"data","inventory.json","result.json"})
            self.assertEqual(inventory["data"],R.pin(payload));self.assertEqual(digest,R.pin(encoded(filemap))["sha256"])
        corrupt=bytearray(raw);corrupt[raw.index(payload)]^=1
        with zipfile.ZipFile(io.BytesIO(corrupt)) as archive,self.assertRaises(zipfile.BadZipFile):R.complete_inventory(self.C,archive)

    def test_safe_outer_member_and_expansion_bounds_remain_from_immutable_kernel(self):
        for name in ("../x","x//y","/x","x\\y"):
            with self.subTest(name=name),zipfile.ZipFile(io.BytesIO(zip_bytes([(name,b"x")])) ) as archive,self.assertRaises(Exception):self.C.members(archive)
        info=zipfile.ZipInfo("link");info.external_attr=(stat.S_IFLNK|0o777)<<16
        with zipfile.ZipFile(io.BytesIO(zip_bytes([(info,b"elsewhere")])) ) as archive,self.assertRaises(Exception):self.C.members(archive)
        with mock.patch.object(self.C,"MAX_MEMBER",1),zipfile.ZipFile(io.BytesIO(zip_bytes([("x",b"xx")])) ) as archive,self.assertRaises(Exception):self.C.members(archive)

    def test_both_arm_wheel_inner_bytes_and_retained_copies_are_independent(self):
        rows=[];wheels={}
        for arm in ("baseline","candidate"):
            native=("inert-"+arm).encode();raw=zip_bytes([(self.A.NATIVE_MEMBER,native)])
            wheels[arm]=self.A.WheelPin(arm,"unused",len(raw),R.pin(raw)["sha256"],len(native),R.pin(native)["sha256"])
            rows += [(f"wheels/{arm}/{self.A.WHEEL_NAME}",raw),(f"native/{arm}/{Path(self.A.NATIVE_MEMBER).name}",native)]
        raw=zip_bytes(rows);inventory={n:R.pin(b) for n,b in rows}
        with mock.patch.object(self.A,"WHEELS",wheels),zipfile.ZipFile(io.BytesIO(raw)) as archive:
            files=self.C.members(archive);R.verify_native(self.C,self.A,archive,files,inventory)
            broken=deepcopy(inventory);broken[f"native/candidate/{Path(self.A.NATIVE_MEMBER).name}"]["sha256"]="0"*64
            with self.assertRaises(R.Refusal):R.verify_native(self.C,self.A,archive,files,broken)

    def test_input_graph_rejects_missing_schema_before_any_archive_read(self):
        with mock.patch.object(self.C,"read_member",side_effect=AssertionError("archive read")):
            with self.assertRaises(R.Refusal):R.verify_inputs(self.C,self.A,None,{}, {},{})

    def test_input_graph_recomputes_all_three_members_and_both_publication_observations(self):
        payloads={"old":[("seal",b"original-seal"),("base.whl",b"baseline-wheel")],
            "new":[("ci-native-wheel/manifest.json",b"{}"),("candidate.whl",b"candidate-wheel")],
            "new-preflight":[("native-identity.json",b"{}") ]}
        selected={"old":{"seal","base.whl"},"new":{"ci-native-wheel/manifest.json","candidate.whl"},"new-preflight":{"native-identity.json"}}
        artifacts={};contents={};rows=[];publications={}
        for index,(role,entries) in enumerate(payloads.items(),1):
            raw=zip_bytes(entries);artifacts[role]=SimpleNamespace(artifact_id=index,size=len(raw),sha256=R.pin(raw)["sha256"],role=role)
            contents[role]=self.A.inspect_zip(io.BytesIO(raw),selected[role]);rows.append((f"inputs/{index}.zip",raw))
            observation={"run":{"role":role},"job":{},"artifact":{}}
            publications[role]={stage:{"identity":{"role":role},"observed":deepcopy(observation)} for stage in ("before","after")}
        old_role={"build_source":"D028","world_source":"C76"};manifest={"source":"95"}
        def publication(pin,run,job,artifact,now):
            self.assertEqual(run["role"],pin.role)
            return {"identity":{"role":pin.role},"observed":{"run":run,"job":job,"artifact":artifact}}
        def wheel(raw,pin):return {"native":R.pin(raw)}
        proxy=SimpleNamespace(ARTIFACTS=artifacts,OLD_SEALS={"seal":"registered"},WHEELS={
            "baseline":SimpleNamespace(artifact="old",member="base.whl"),"candidate":SimpleNamespace(artifact="new",member="candidate.whl")},
            inspect_zip=self.A.inspect_zip,validate_publication=mock.Mock(side_effect=publication),
            validate_old=mock.Mock(return_value=old_role),validate_new=mock.Mock(return_value=manifest),validate_wheel=mock.Mock(side_effect=wheel))
        admission=dict(publications=publications,old_role=old_role,new_manifest=manifest,members={k:v[0] for k,v in contents.items()},
            wheel_members={"baseline":{"native":R.pin(b"baseline-wheel")},"candidate":{"native":R.pin(b"candidate-wheel")}})
        inventory={n:R.pin(raw) for n,raw in rows}
        with zipfile.ZipFile(io.BytesIO(zip_bytes(rows))) as archive:
            files=self.C.members(archive);self.assertEqual(R.verify_inputs(self.C,proxy,archive,files,inventory,admission),admission)
            self.assertEqual(proxy.validate_publication.call_count,6)
            self.assertEqual(proxy.validate_old.call_args.args,contents["old"])
            self.assertEqual(proxy.validate_new.call_args.args,(*contents["new"],*contents["new-preflight"]))
            bad=deepcopy(admission);bad["members"]["old"]["seal"]["sha256"]="0"*64
            with self.assertRaises(R.Refusal):R.verify_inputs(self.C,proxy,archive,files,inventory,bad)

    def test_installer_observation_logs_and_runtime_are_linked_without_rehash_claim(self):
        rt=runtime(self.A)
        value=dict(uv=dict(path="/old/python/bin/uv",bytes=123,sha256="4"*64),version="uv 0.13.6",
            environment=dict(python=self.A.PYTHON,prefix=rt["prefix"],project_or_native_installed=False),
            bootstrap_python="/old/python/bin/python",bootstrap_version=rt["version"])
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/"logs").mkdir()
            R.write(root/"environment-preparation.json",value)
            (root/"logs/fresh-environment-probe.log").write_bytes(encoded(value["environment"]))
            (root/"logs/uv-version.log").write_text("uv 0.13.6\n")
            R.verify_installer(self.C,self.A,root,{"installer":value},rt)
            (root/"logs/uv-version.log").write_text("uv 0.14.0\n")
            with self.assertRaises(R.Refusal):R.verify_installer(self.C,self.A,root,{"installer":value},rt)

    def test_supervised_compare_preserves_exact_cli_and_requires_owned_cleanup(self):
        for cleanup in (True,False):
            with self.subTest(cleanup=cleanup),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);(root/"logs").mkdir();calls=[];deadline=time.monotonic()+500
                class Supervisor:
                    cleanup_complete=cleanup
                    def __init__(self,where,end):calls.append((where,end))
                    def command(self,label,command,env,cwd):
                        calls.append((label,command,env,cwd));(root/"logs"/(label+".log")).write_text("off_s42: 9 files, 0 differences\n1 cases, 9 files compared, 0 differences\n")
                with mock.patch.object(self.A.H,"Supervisor",Supervisor):
                    if cleanup:result=R.compare_supervised(self.C,self.A,root/"scratch",root/"view",{"off_s42":9},root,"off_s42",deadline,[])
                    else:
                        with self.assertRaises(R.Refusal):R.compare_supervised(self.C,self.A,root/"scratch",root/"view",{"off_s42":9},root,"off_s42",deadline,[])
                command=calls[1][1]
                self.assertEqual(command,[sys.executable,str(root/"view/scripts/turn_speed_identity.py"),"compare",str(root/"scratch/raw/baseline"),str(root/"scratch/raw/candidate")])
                self.assertLessEqual(calls[0][1],deadline-R.CLEANUP_RESERVE)
                if cleanup:self.assertEqual(result["files_compared"],9)

    def test_marker_and_copy_rehash_precede_only_derived_retirement(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);marker={"kind":"derived","case":"x"};R.write(root/".derived-reader-scratch.json",marker)
            (root/"file").write_bytes(b"x");inventory={"file":R.pin(b"x")}
            with mock.patch.object(R.shutil,"rmtree") as retire:
                R.retire_case(self.C,root,inventory,marker);retire.assert_called_once_with(root)
            (root/"file").write_bytes(b"changed")
            with mock.patch.object(R.shutil,"rmtree",side_effect=AssertionError("must retain")),self.assertRaises(R.Refusal):R.retire_case(self.C,root,inventory,marker)

    def test_comparator_exception_cannot_parse_or_retire_case(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/"logs").mkdir()
            supervisor=SimpleNamespace(cleanup_complete=True,command=mock.Mock(side_effect=R.Refusal("synthetic comparator failure")))
            with mock.patch.object(self.A.H,"Supervisor",return_value=supervisor), \
                 mock.patch.object(self.C.core,"parse_comparison",side_effect=AssertionError("parse after failed child")), \
                 mock.patch.object(R.shutil,"rmtree") as retire:
                with self.assertRaisesRegex(R.Refusal,"comparator failure"):
                    R.compare_supervised(self.C,self.A,root/"scratch",root/"view",{"off_s42":9},root,"off_s42",time.monotonic()+300,[])
                    R.retire_case(self.C,root/"scratch",{}, {})
                retire.assert_not_called()

    def test_reader_finalizer_uses_real_start_and_never_4800_second_offset(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/"logs").mkdir();(root/"publication").mkdir()
            with mock.patch.object(self.C,"admission"),mock.patch.object(R.time,"monotonic",return_value=112.0):
                self.assertEqual(R.finalize(self.C,root,{"qualified":True},100.0,700.0,True),0)
            saved=json.loads((root/"publication/reader-result.json").read_text());self.assertEqual(saved["reader_seconds"],12.0)

    def test_uncertain_cleanup_or_late_finalization_stays_negative(self):
        for quiescent,now in ((False,112.0),(True,701.0)):
            with self.subTest(quiescent=quiescent),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);(root/"logs").mkdir();(root/"publication").mkdir()
                with mock.patch.object(self.C,"admission"),mock.patch.object(R.time,"monotonic",return_value=now):
                    self.assertEqual(R.finalize(self.C,root,{"qualified":True},100.0,700.0,quiescent),1)
                self.assertFalse(json.loads((root/"publication/reader-result.json").read_text())["qualified"])
                if not quiescent:self.assertFalse((root/"publication/inventory.json").exists())

    def test_late_terminal_write_is_censored_with_actual_elapsed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/"logs").mkdir();(root/"publication").mkdir();clock={"now":112.0};real_write=R.write
            def write(path,value):
                real_write(path,value)
                if value.get("qualified") is True:clock["now"]=701.0
            with mock.patch.object(self.C,"admission"),mock.patch.object(R,"write",side_effect=write), \
                 mock.patch.object(R.time,"monotonic",side_effect=lambda:clock["now"]):
                self.assertEqual(R.finalize(self.C,root,{"qualified":True},100.0,700.0,True),1)
            saved=json.loads((root/"publication/reader-result.json").read_text())
            self.assertFalse(saved["qualified"]);self.assertEqual(saved["reader_seconds"],601.0)

    def test_final_source_kernel_and_metadata_mutations_refuse(self):
        context={"source":"a"*40,"metadata_pins":{"metadata-after.json":{"bytes":1,"sha256":"1"*64}}}
        expected={"sha":"a"*40};root=Path("/synthetic")
        for fault in ("source","kernel","metadata"):
            def digest(path,*args):
                if path.name in R.KERNELS:return {"sha256":"0"*64 if fault=="kernel" else R.KERNELS[path.name][1]}
                return {"bytes":1,"sha256":"0"*64 if fault=="metadata" else "1"*64}
            with self.subTest(fault=fault),mock.patch.object(R,"own_source",return_value={} if fault=="source" else expected), \
                 mock.patch.object(self.C.core,"digest",side_effect=digest),self.assertRaises(R.Refusal):
                R.final_sources(self.C,context,root,expected)

    def test_saved_producer_source_field_shapes_match_probe_fixture(self):
        tree=ast.parse((R.ROOT/"scripts/arc_output_identity_qualification.py").read_bytes())
        function=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=="probe")
        call=next(n for n in ast.walk(function) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=="write")
        keys={ast.literal_eval(k) for k in call.args[1].keys}
        self.assertEqual(keys|{"runtime"},set(probe(self.A,"baseline")))
        tree=ast.parse((R.ROOT/"scripts/native_default_output_identity_qualification.py").read_bytes())
        function=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=="runtime_seal")
        returned=next(n for n in ast.walk(function) if isinstance(n,ast.Return))
        self.assertEqual({ast.literal_eval(k) for k in returned.value.keys},set(runtime(self.A)))
        execute=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=="execute")
        initial=next(n.value for n in ast.walk(execute) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=="report" for t in n.targets))
        keys={ast.literal_eval(k) for k in initial.keys}
        run_cases=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=="run_cases")
        for call in ast.walk(run_cases):
            if isinstance(call,ast.Call) and isinstance(call.func,ast.Attribute) and isinstance(call.func.value,ast.Name) and call.func.value.id=="report" and call.func.attr=="update":
                keys|={k.arg for k in call.keywords}
        self.assertEqual(keys|{"installer","inventory_sha256","elapsed_wall_seconds"},set(result(self.A)))

    def test_dormant_closed_workflow_has_no_outside_environment_or_download(self):
        raw=(R.ROOT/R.TEMPLATE_PATH).read_bytes();self.assertEqual(R.pin(raw)["sha256"],R.WORKFLOW_SHA)
        text=raw.decode()
        for value in (R.ACTIVE_BRANCH,R.WORKFLOW_PATH,"github.run_attempt == '1'","timeout --kill-after=5s 610s"):
            self.assertIn(value,text)
        for value in ("workflow_dispatch","pip install","uv sync","download-artifact","--faith-ids","--checkpoint"):
            self.assertNotIn(value,text)


if __name__=="__main__":unittest.main()
