"""Bounded stdlib contracts: no real artifact, native package or world needed."""
from copy import deepcopy
from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
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
import warnings
import zipfile

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/native_default_output_identity_qualification.py"
spec = importlib.util.spec_from_file_location("native_default_qualification_contracts", SCRIPT)
A = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = A
spec.loader.exec_module(A)
NOW = datetime(2026, 10, 29, tzinfo=timezone.utc)


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def archive_bytes(rows):
    stream = io.BytesIO()
    with warnings.catch_warnings(), zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_STORED) as archive:
        warnings.simplefilter("ignore", UserWarning)
        for name, data in rows:
            archive.writestr(name, data)
    return stream.getvalue()


def publication(pin):
    run = dict(id=pin.run_id, head_sha=pin.source, run_attempt=1, status="completed", conclusion="success",
               path=pin.workflow, repository={"id": A.REPOSITORY_ID})
    job = dict(id=pin.job_id, run_id=pin.run_id, run_attempt=1, head_sha=pin.source, status="completed", conclusion="success")
    artifact = dict(id=pin.artifact_id, name=pin.name, size_in_bytes=pin.size, digest="sha256:" + pin.sha256,
        expired=False, expires_at=pin.expiry, workflow_run=dict(id=pin.run_id, head_sha=pin.source,
            repository_id=A.REPOSITORY_ID, head_repository_id=A.REPOSITORY_ID))
    return run, job, artifact


def producer_env():
    return dict(GITHUB_ACTIONS="true",GITHUB_REPOSITORY=A.REPOSITORY,GITHUB_EVENT_NAME="push",
        GITHUB_REF="refs/heads/"+A.ACTIVE_BRANCH,GITHUB_WORKFLOW_REF=A.REPOSITORY+"/"+A.WORKFLOW_PATH+
        "@refs/heads/"+A.ACTIVE_BRANCH,GITHUB_JOB=A.JOB_KEY,GITHUB_RUN_ATTEMPT="1",GITHUB_RUN_ID="42",GITHUB_SHA="1"*40)


def probe_value(arm, source, prefix):
    wheel = A.WHEELS[arm]
    runtime = dict(python=A.PYTHON, version=A.PYTHON + " (synthetic stdlib contract)", implementation="CPython",
        platform="synthetic common platform", machine="x86_64", executable=str(prefix / "bin/python"), prefix=str(prefix),
        affinity=[4], cpu_count=1, process_cpu_count=1, optimize=0, no_user_site=1, dont_write_bytecode=True,
        thread_env={**A.H.CAPS, "PYTHONHASHSEED": "0", "OPENBLAS_THREAD_TIMEOUT": "16"},
        packages={name: "1.0" for name in A.PACKAGE_NAMES})
    return dict(source={"git_sha": A.SOURCES[arm], "package_dir": str(source / "src/chronicler"), "package_digest": arm},
        source_file=str(source / "src/chronicler/__init__.py"), prefix=str(prefix), native_file=str(prefix / "lib/native.so"),
        native={"sha256": wheel.native_sha256, "bytes": wheel.native_size}, schemas=deepcopy(A.SCHEMAS), affinity=[4], runtime=runtime)


def old_seal_model(origin="d0281e5f57c508f27cea1676f36e0e6ed1225c9d"):
    """Tiny provenance graph, with injected test seals rather than real bytes."""
    names=[role+"/source-"+when+".json" for role in ("baseline","candidate") for when in ("before","after")]
    names += ["source-control-before.json","source-control-after.json"]
    names += ["wheels/"+role+"/"+A.WHEEL_NAME for role in ("baseline","candidate")]
    names += ["fixture-"+str(i) for i in range(58)]
    raw_pins={name:A.pin_bytes(b"x") for name in names}
    w=A.WHEELS["baseline"]
    raw_pins[w.member]={"bytes":w.size,"sha256":w.sha256}
    baseline_wheel=dict(filename=A.WHEEL_NAME,bytes=w.size,sha256=w.sha256,native_member=A.NATIVE_MEMBER,
                        native_bytes=w.native_size,native_sha256=w.native_sha256)
    phases={role:dict(build_complete=True,cleanup_complete=True,source_clean=True,
        source_before_sha256=raw_pins[role+"/source-before.json"]["sha256"],
        source_after_sha256=raw_pins[role+"/source-after.json"]["sha256"],
        wheel=baseline_wheel if role=="baseline" else dict(filename=A.WHEEL_NAME,**raw_pins["wheels/candidate/"+A.WHEEL_NAME]))
        for role in ("baseline","candidate")}
    phases["baseline"]["probe"]=dict(schemas=deepcopy(A.SCHEMAS),compiled_extension=True,real_exported_classes=True,
        native_pools_created=0,source_imports=[],native_sha256=w.native_sha256,python=A.PYTHON)
    manifest=dict(baseline_source=origin,baseline_crate=A.CRATES["baseline"],rebuilt_baseline_native_sha256=w.native_sha256,
        historical_reuse_eligible=True,candidate_worlds_admitted=False,phases=phases,
        producer=dict(control_sha=A.ARTIFACTS["old"].source,job_key="paired-native-build",run_attempt="1",
                      run_id=str(A.ARTIFACTS["old"].run_id)))
    payloads={"build-manifest.json":encoded(manifest),"raw-inventory.json":encoded(dict(file_count=66,files=raw_pins,
        total_bytes=sum(row["bytes"] for row in raw_pins.values())))}
    pins=dict(raw_pins)
    pins.update({name:A.pin_bytes(data) for name,data in payloads.items()})
    light={name:raw_pins[name] for name in names[:14]}
    light["build-manifest.json"]=pins["build-manifest.json"]
    payloads["light/index.json"]=encoded(dict(files=light))
    pins["light/index.json"]=A.pin_bytes(payloads["light/index.json"])
    pins.update({"light/"+name:pin for name,pin in light.items()})
    completion=dict(publication_complete=True,files={name:pins[name] for name in
        ("build-manifest.json","raw-inventory.json","light/index.json")})
    payloads["completion.json"]=encoded(completion); pins["completion.json"]=A.pin_bytes(payloads["completion.json"])
    seals={name:pins[name]["sha256"] for name in A.OLD_SEALS}
    return pins,payloads,seals


class Contracts(unittest.TestCase):
    def setUp(self):
        # At most a few KiB of fixture output, with a reserve above the real floor.
        if shutil.disk_usage(tempfile.gettempdir()).free < 3 * A.GIB + 2 * 1024**2:
            self.fail("synthetic contracts stopped before the 3 GiB disk floor")

    def test_original_helper_and_historical_registries_are_unchanged(self):
        self.assertEqual(A.H.sha(A.H.SCRIPT), A.HELPER_SHA)
        self.assertEqual(set(A.H.SOURCE_PAIRS), {"arc", "recovered"})
        with tempfile.TemporaryDirectory() as tmp:
            wrong = Path(tmp) / "helper.py"
            wrong.write_bytes(b"raise AssertionError('must not execute')")
            with self.assertRaisesRegex(RuntimeError, "identity refused"):
                A.load_helper(wrong)

    def test_default_is_inert_and_run_requires_explicit_execution_before_io(self):
        out = io.StringIO()
        with mock.patch.object(A.Transport, "__init__", side_effect=AssertionError("transport")), \
             mock.patch.object(A.H.subprocess, "Popen", side_effect=AssertionError("child")), \
             mock.patch.object(Path, "mkdir", side_effect=AssertionError("mkdir")), contextlib.redirect_stdout(out):
            self.assertEqual(A.main([]), 0)
            with self.assertRaisesRegex(A.Refusal, "inactive"):
                A.execute(SimpleNamespace(execute=False))
        self.assertEqual(json.loads(out.getvalue())["status"], "inactive")

    def test_closed_identity_records_are_not_mutable_cli_parameters(self):
        with self.assertRaises(TypeError): A.SOURCES["baseline"] = "latest"
        with self.assertRaises(FrozenInstanceError): A.ARTIFACTS["old"].size = 0
        self.assertEqual(A.SOURCES["baseline"], "c76efe8552b4c6c288ebb1f813e2c0a58e5957b1")
        self.assertEqual(A.SOURCES["candidate"], "95f73a74f809d7e10f09a1241c98014864350ffb")

    def test_all_eighteen_rows_preserve_original_order_and_tick_budget(self):
        rows = A.case_rows()
        names=["off_s42","off_s7","hybrid_s42","hybrid_s7","hybrid_s1234","proc48_hybrid_s42", "proc48_off_s7","scaled22k_s42","scaled52k_s7"]
        self.assertEqual([(r["arm"], r["case"]) for r in rows],
            [(arm, name) for arm in ("baseline", "candidate") for name in names])
        self.assertEqual(len(rows), 18)
        self.assertEqual(2 * sum(int(cli[cli.index("--turns") + 1]) for cli, _ in A.H.CASES.values()), 3200)
        self.assertEqual(A.H.CASES["scaled22k_s42"][1], 18800)
        self.assertEqual(A.H.CASES["scaled52k_s7"][1], 43700)

    def test_nonempty_complete_ordered_rows_are_required(self):
        complete = [dict(row, status="complete", audit_sha256="1" * 64) for row in A.case_rows()]
        A.require_complete(complete)
        for bad in ([], complete[:-1], list(reversed(complete)), complete + complete[:1],
                    [dict(row, status="started") if i == 0 else row for i, row in enumerate(complete)]):
            with self.subTest(length=len(bad)), self.assertRaises(A.Refusal): A.require_complete(bad)

    def test_same_version_wheel_install_must_force_replacement(self):
        cmd = A.install_command("/env/bin/python", Path("/wheels/baseline/" + A.WHEEL_NAME))
        self.assertEqual(cmd, ["uv", "pip", "install", "--no-deps", "--reinstall", "--python",
                               "/env/bin/python", "/wheels/baseline/" + A.WHEEL_NAME])
        self.assertEqual(A.install_command("/env/bin/python",Path("/arm.whl"),"/selected/uv")[0],"/selected/uv")

    def test_push_producer_is_closed_before_any_io(self):
        env=producer_env()
        self.assertEqual(A.producer_context(env)["run_id"],"42")
        for field,value in (("GITHUB_EVENT_NAME","workflow_dispatch"),("GITHUB_REF","refs/heads/main"),
            ("GITHUB_WORKFLOW_REF",env["GITHUB_WORKFLOW_REF"].replace(A.WORKFLOW_PATH,"other.yml")),
            ("GITHUB_RUN_ATTEMPT","2"),("GITHUB_JOB","other"),("GITHUB_RUN_ID","0"),("GITHUB_SHA","bad")):
            with self.subTest(field=field), mock.patch.dict(A.os.environ,dict(env,**{field:value}),clear=True), \
                 mock.patch.object(Path,"mkdir",side_effect=AssertionError("mkdir")):
                with self.assertRaisesRegex(A.Refusal,"closed first-attempt"):
                    A.execute(SimpleNamespace(execute=True))

    def test_active_workflow_must_equal_exact_reviewed_template(self):
        template=(SCRIPT.parents[1]/A.TEMPLATE_PATH).read_bytes()
        self.assertEqual(hashlib.sha256(template).hexdigest(),A.WORKFLOW_SHA)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for name in (A.TEMPLATE_PATH,A.WORKFLOW_PATH):
                path=root/name; path.parent.mkdir(parents=True,exist_ok=True); path.write_bytes(template)
            A.workflow_contract(root)
            (root/A.WORKFLOW_PATH).write_bytes(template+b"# changed\n")
            with self.assertRaises(A.Refusal): A.workflow_contract(root)

    def test_environment_setup_observes_selected_uv_and_uses_one_supervisor(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp).resolve(); root=base/"evidence"; (root/"logs").mkdir(parents=True)
            prefix=base/"env"; uv=base/"hostbin/uv"; uv.parent.mkdir(); uv.write_bytes(b"inert installer")
            roots={name:base/name for name in ("baseline","candidate","control")}
            labels=[]
            class Supervisor:
                deadline=time.monotonic()+4800
                def command(self,label,command,env,cwd):
                    labels.append((label,list(command),dict(env)))
                    if label=="uv-version": (root/"logs/uv-version.log").write_text("uv 0.13.6\n")
                    if label=="fresh-locked-environment":
                        (prefix/"bin").mkdir(parents=True); (prefix/"bin/python").write_bytes(b"never executed")
                    if label=="fresh-environment-probe":
                        (root/"logs/fresh-environment-probe.log").write_bytes(encoded(dict(python=A.PYTHON,
                            prefix=str(prefix),project_or_native_installed=False)))
                def admission(self,*args): labels.append(("admission",args,{}))
            supervisor=Supervisor(); deadline=supervisor.deadline
            with mock.patch.object(A.sysconfig,"get_path",return_value=str(uv.parent)), \
                 mock.patch.object(A.platform,"python_version",return_value=A.PYTHON), \
                 mock.patch.object(A.platform,"python_implementation",return_value="CPython"):
                result=A.prepare_environment(root,roots,str(prefix/"bin/python"),prefix,{},supervisor)
            self.assertEqual([row[0] for row in labels],["install-exact-uv","uv-version","locked-input-check",
                "fresh-locked-environment","fresh-environment-probe","admission"])
            self.assertEqual(supervisor.deadline,deadline)
            self.assertIn("uv==0.13.6",labels[0][1]); self.assertEqual(labels[1][1],[str(uv),"--version"])
            self.assertIn("--no-install-project",labels[3][1]); self.assertIn("--no-build",labels[3][1])
            self.assertEqual(labels[3][2]["UV_PROJECT_ENVIRONMENT"],str(prefix))
            self.assertEqual(labels[-1][1],("environment-prepared",6,2))
            self.assertEqual(result["uv"]["sha256"],hashlib.sha256(uv.read_bytes()).hexdigest())
            with self.assertRaisesRegex(A.Refusal,"fresh external"):
                A.prepare_environment(root,roots,str(prefix/"bin/python"),prefix,{},supervisor)

    def test_wrong_observed_uv_version_stops_before_dependency_environment(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp).resolve(); (base/"logs").mkdir(); uv=base/"uv"; uv.write_bytes(b"inert")
            labels=[]
            def command(label,*args):
                labels.append(label)
                if label=="uv-version": (base/"logs/uv-version.log").write_text("uv 0.1.0\n")
            with mock.patch.object(A.sysconfig,"get_path",return_value=str(base)), \
                 mock.patch.object(A.platform,"python_version",return_value=A.PYTHON), \
                 mock.patch.object(A.platform,"python_implementation",return_value="CPython"):
                with self.assertRaisesRegex(A.Refusal,"actual uv"):
                    A.prepare_environment(base,{"candidate":base/"source"},str(base.parent/"env/bin/python"),
                        base.parent/"env",{},SimpleNamespace(command=command))
            self.assertEqual(labels,["install-exact-uv","uv-version"])

    def test_completed_producer_publication_identities_and_original_expiry(self):
        for pin in A.ARTIFACTS.values():
            with self.subTest(artifact=pin.artifact_id):
                rows = publication(pin)
                result = A.validate_publication(pin, *rows, NOW)
                self.assertEqual(result["identity"]["sha256"], pin.sha256)
                changed = deepcopy(rows); changed[0]["repository"]["description"] = "unrelated mutable metadata"
                self.assertEqual(A.validate_publication(pin, *changed, NOW)["identity"], result["identity"])
                for index, field, value in [(0,"run_attempt",True),(0,"head_sha","0"*40),(0,"conclusion","failure"),
                    (1,"id",pin.job_id+1),(1,"run_attempt",True),(1,"head_sha","0"*40),
                    (2,"digest","sha256:"+"0"*64),(2,"expired",0),(2,"expires_at","2099-01-01T00:00:00Z")]:
                    bad=deepcopy(rows); bad[index][field]=value
                    with self.subTest(field=field), self.assertRaises(A.Refusal): A.validate_publication(pin,*bad,NOW)
                with self.assertRaises(A.Refusal): A.validate_publication(pin,*rows,datetime(2099,1,1,tzinfo=timezone.utc))

    def test_wrong_outer_digest_refuses_before_zip_allocation(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"input.zip"; path.write_bytes(b"not the registered artifact")
            with mock.patch.object(A.zipfile,"ZipFile",side_effect=AssertionError("ZIP allocation")):
                with self.assertRaises(A.Refusal): A.inspect_artifact(path,A.ARTIFACTS["old"],())

    def test_storage_redirect_drops_api_authorization_and_checks_exact_stream(self):
        data=b"tiny registered synthetic stream"
        pin=A.ArtifactPin(1,2,3,"1"*40,"fixture",len(data),hashlib.sha256(data).hexdigest(),
                          "2026-11-28T00:00:00Z","fixture.yml")
        supervisor=SimpleNamespace(admission=lambda *_:None)
        transport=A.Transport("synthetic-token-never-forwarded",supervisor,time.monotonic()+10)
        requests=[]
        def open_storage(request,**kwargs):
            requests.append(request)
            return io.BytesIO(data)
        transport.opener=SimpleNamespace(open=open_storage)
        redirect=A.urllib.error.HTTPError("https://api.github.com/registered",302,"redirect",
            {"Location":"https://fixture.blob.core.windows.net/closed?sig=synthetic"},None)
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(transport,"api",side_effect=redirect):
            path=Path(tmp)/"input.zip"; transport.download(pin,path)
            self.assertEqual(path.read_bytes(),data)
        self.assertEqual(len(requests),1)
        self.assertIsNone(requests[0].get_header("Authorization"))
        bad_redirect=A.urllib.error.HTTPError("https://api.github.com/registered",302,"redirect",
            {"Location":"https://unregistered.example/closed?sig=synthetic"},None)
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(transport,"api",side_effect=bad_redirect):
            with self.assertRaises(A.Refusal): transport.download(pin,Path(tmp)/"input.zip")
        self.assertEqual(len(requests),1)

    def test_input_deadline_and_size_do_not_become_success(self):
        transport=A.Transport("synthetic-token",SimpleNamespace(admission=lambda *_:None),time.monotonic()-1)
        with self.assertRaises(A.Refusal): transport.check()
        transport.deadline=time.monotonic()+10
        pin=A.ArtifactPin(1,2,3,"1"*40,"fixture",1,hashlib.sha256(b"x").hexdigest(),"2026-11-28T00:00:00Z","fixture.yml")
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(transport,"api",return_value=io.BytesIO(b"xx")):
            with self.assertRaises(A.Refusal): transport.download(pin,Path(tmp)/"input.zip")

    def test_zip_inventory_streams_unselected_members_and_checks_crc(self):
        raw=archive_bytes([("wanted",b"keep"),("other",b"UNSELECTED-PAYLOAD")])
        pins,values=A.inspect_zip(io.BytesIO(raw),{"wanted"})
        self.assertEqual(set(pins),{"wanted","other"}); self.assertEqual(values,{"wanted":b"keep"})
        corrupt=bytearray(raw); corrupt[raw.index(b"UNSELECTED-PAYLOAD")]^=1
        with self.assertRaises(zipfile.BadZipFile): A.inspect_zip(io.BytesIO(corrupt),{"wanted"})

    def test_zip_paths_aliases_types_and_caps_refuse(self):
        for name in ("../x","/x","x//y","x/./y","x\\y","C:x"):
            with self.subTest(name=name), self.assertRaises(A.Refusal):
                A.inspect_zip(io.BytesIO(archive_bytes([(name,b"x")])))
        with self.assertRaises(A.Refusal): A.inspect_zip(io.BytesIO(archive_bytes([("x",b"a"),("x",b"b")])))
        info=zipfile.ZipInfo("link"); info.external_attr=(stat.S_IFLNK|0o777)<<16
        with self.assertRaises(A.Refusal): A.inspect_zip(io.BytesIO(archive_bytes([(info,b"elsewhere")])))
        with mock.patch.object(A,"MAX_MEMBER",3), self.assertRaises(A.Refusal):
            A.inspect_zip(io.BytesIO(archive_bytes([("x",b"four")])))
        with mock.patch.object(A,"MAX_ENTRIES",1), self.assertRaises(A.Refusal):
            A.inspect_zip(io.BytesIO(archive_bytes([("x",b"x"),("y",b"y")])))

    def test_empty_wheel_directories_validate_local_headers_and_outer_refuses_them(self):
        raw=archive_bytes([("pkg/",b""),("pkg/file",b"x")])
        pins,_=A.inspect_zip(io.BytesIO(raw),allow_directories=True)
        self.assertEqual(set(pins),{"pkg/file"})
        with self.assertRaises(A.Refusal): A.inspect_zip(io.BytesIO(raw))
        with self.assertRaises(A.Refusal): A.inspect_zip(io.BytesIO(archive_bytes([("pkg/",b"not empty")])),allow_directories=True)

    def test_wheel_arm_and_actual_inner_native_bytes_are_independent_checks(self):
        raw=archive_bytes([(A.NATIVE_MEMBER,b"synthetic native bytes"),("pkg.dist-info/METADATA",b"Version: 0.1.0")])
        pin=A.WheelPin("synthetic","wheel",len(raw),hashlib.sha256(raw).hexdigest(),
                      len(b"synthetic native bytes"),hashlib.sha256(b"synthetic native bytes").hexdigest())
        A.validate_wheel(raw,pin)
        bad=A.WheelPin(pin.artifact,pin.member,pin.size,pin.sha256,pin.native_size,"0"*64)
        with self.assertRaises(A.Refusal): A.validate_wheel(raw,bad)
        with mock.patch.object(A.zipfile,"ZipFile",side_effect=AssertionError("ZIP allocation")):
            with self.assertRaises(A.Refusal): A.validate_wheel(raw,A.WHEELS["baseline"])

    def test_sealed_inventory_checks_types_and_every_content_pin(self):
        pins={"one":A.pin_bytes(b"one"),"two":A.pin_bytes(b"two")}
        A.require_inventory(pins,deepcopy(pins))
        for bad in ({"one":dict(pins["one"],bytes=True)}, {"two":dict(pins["two"],sha256="0"*64)}, {"missing":pins["one"]}):
            with self.assertRaises(A.Refusal): A.require_inventory(pins,bad)

    def test_new_wheel_requires_separate_same_producer_installed_receipt(self):
        w=A.WHEELS["candidate"]
        manifest=dict(schema_version=1,source_commit=A.SOURCES["candidate"],wheel=dict(filename=A.WHEEL_NAME,bytes=w.size,
            sha256=w.sha256,native_member=A.NATIVE_MEMBER),installed_native=dict(filename=Path(A.NATIVE_MEMBER).name,
            bytes=w.native_size,sha256=w.native_sha256,wheel_member_sha256=w.native_sha256),python=A.PYTHON+" fixture",
            classes=["AgentSimulator","EcologySimulator","PoliticsSimulator"])
        identity=dict(source_commit=A.SOURCES["candidate"],sha256=w.native_sha256,classes=manifest["classes"],
                      python=manifest["python"],compiled_extension="/qualified/native.so")
        pins={"ci-native-wheel/manifest.json":{},w.member:{}}; pre={"native-identity.json":{},"native.xml":{}}
        A.validate_new(pins,{"ci-native-wheel/manifest.json":encoded(manifest)},pre,{"native-identity.json":encoded(identity)})
        for field,value in (("sha256","0"*64),("source_commit",A.SOURCES["baseline"]),("compiled_extension","shim.py")):
            bad=dict(identity,**{field:value})
            with self.subTest(field=field), self.assertRaises(A.Refusal):
                A.validate_new(pins,{"ci-native-wheel/manifest.json":encoded(manifest)},pre,{"native-identity.json":encoded(bad)})

    def test_probe_rejects_runtime_schema_source_or_native_mismatch(self):
        source,prefix=Path("/fixture/source"),Path("/fixture/env")
        good=probe_value("baseline",source,prefix)
        runtime=A.validate_probe(good,"baseline",source,prefix)
        other=probe_value("candidate",Path("/fixture/candidate"),prefix)
        A.validate_probe(other,"candidate",Path("/fixture/candidate"),prefix,runtime)
        for kind in ("source","native","schema","affinity","optimize","caps","package"):
            bad=deepcopy(good)
            if kind=="source": bad["source"]["git_sha"]=A.SOURCES["candidate"]
            if kind=="native": bad["native"]["sha256"]=A.WHEELS["candidate"].native_sha256
            if kind=="schema": bad["schemas"]["AgentSimulator"]["fingerprint"]="changed"
            if kind=="affinity": bad["runtime"]["affinity"]=[4,5]
            if kind=="optimize": bad["runtime"]["optimize"]=False
            if kind=="caps": bad["runtime"]["thread_env"]["RAYON_NUM_THREADS"]="2"
            if kind=="package": bad["runtime"]["packages"]["numpy"]="different"
            with self.subTest(kind=kind), self.assertRaises(A.Refusal): A.validate_probe(bad,"baseline",source,prefix,runtime)

    def test_old_build_seals_cannot_be_replaced_by_a_success_flag(self):
        with self.assertRaises(A.Refusal): A.validate_old({}, {"success":True})
        pins={name:{"sha256":value,"bytes":1} for name,value in A.OLD_SEALS.items()}
        pins.update({str(i):A.pin_bytes(b"x") for i in range(81)})
        pins["completion.json"]["sha256"]="0"*64
        with self.assertRaises(A.Refusal): A.validate_old(pins,{})

    def test_old_completion_graph_preserves_build_origin_and_rejects_relabeling(self):
        pins,payloads,seals=old_seal_model()
        with mock.patch.object(A,"OLD_SEALS",seals):
            role=A.validate_old(pins,payloads)
        self.assertEqual(role["world_source"],A.SOURCES["baseline"])
        self.assertEqual(role["build_source"],"d0281e5f57c508f27cea1676f36e0e6ed1225c9d")
        pins,payloads,seals=old_seal_model(origin=A.SOURCES["baseline"])
        with mock.patch.object(A,"OLD_SEALS",seals), self.assertRaises(A.Refusal): A.validate_old(pins,payloads)

    def test_synthetic_scheduler_runs_only_own_source_matrix_and_stops_on_failure(self):
        def perform(tmp,fail=False):
            base=Path(tmp).resolve(); root=base/"evidence"; prefix=base/"env"; roots={"baseline":base/"base","candidate":base/"new"}
            for folder in ("raw","probes","audits","native/baseline","native/candidate","wheels/baseline","wheels/candidate"):
                (root/folder).mkdir(parents=True,exist_ok=True)
            (prefix/"lib").mkdir(parents=True); (prefix/"lib/native.so").write_bytes(b"inert fixture, never imported")
            installer=base/"uv"; installer.write_bytes(b"inert installer")
            report={"qualified":False,"cases":A.case_rows(),"installer":{"uv":{"path":str(installer),
                "sha256":hashlib.sha256(installer.read_bytes()).hexdigest()}}}
            commands=[]
            class Supervisor:
                def admission(self,*args): pass
                def event(self,*args,**kwargs): pass
                def command(self,label,command,env,cwd):
                    commands.append((label,list(command),dict(env)))
                    if label.startswith("probe-"):
                        arm=command[command.index("--arm")+1]
                        Path(command[command.index("--out")+1]).write_bytes(encoded(probe_value(arm,roots[arm],prefix)))
                    elif label.startswith("world-"):
                        if fail and label=="world-baseline-hybrid_s42": raise A.Refusal("synthetic first world refusal")
                        arm="baseline" if label.startswith("world-baseline-") else "candidate"
                        name=command[-1]; (root/"raw"/arm/name).mkdir()
                        (root/"raw"/arm/"which.txt").write_text("chronicler "+str(roots[arm]/"src/chronicler/__init__.py")+
                            "\nnative "+str(prefix/"lib/native.so")+" "+A.WHEELS[arm].native_sha256+"\n")
                    elif label.startswith("audit-"):
                        Path(command[-1]).write_bytes(encoded({"files":{}}))
            real_sha=A.H.sha
            def fixture_sha(path):
                path=Path(path)
                if path.name==A.WHEEL_NAME: return A.WHEELS[path.parent.name].sha256
                if path.parent.parent==root/"native": return A.WHEELS[path.parent.name].native_sha256
                return real_sha(path)
            with mock.patch.object(A.H,"sha",side_effect=fixture_sha):
                if fail:
                    with self.assertRaisesRegex(A.Refusal,"synthetic first"):
                        A.run_cases(root,roots,str(prefix/"bin/python"),prefix,{},Supervisor(),report)
                else:
                    A.run_cases(root,roots,str(prefix/"bin/python"),prefix,{},Supervisor(),report)
            return commands,report,root,roots,prefix
        with tempfile.TemporaryDirectory() as tmp:
            commands,report,root,roots,prefix=perform(tmp)
            worlds=[row for row in commands if row[0].startswith("world-")]
            self.assertEqual([row[0] for row in worlds],["world-"+r["arm"]+"-"+r["case"] for r in A.case_rows()])
            self.assertEqual(len([row for row in commands if row[0].startswith("install-")]),2)
            for command,row in zip(worlds,A.case_rows()):
                own=roots[row["arm"]]
                self.assertEqual(command[1],[str(prefix/"bin/python"),str(own/"scripts/turn_speed_identity.py"),"run",
                    str(root/"raw"/row["arm"]),"--source-root",str(own),"--case",row["case"]])
                self.assertEqual(command[2]["PYTHONPATH"],str(own/"src"))
            self.assertEqual(commands[-1][1],[str(prefix/"bin/python"),str(roots["candidate"]/"scripts/turn_speed_identity.py"),
                "compare",str(root/"raw/baseline"),str(root/"raw/candidate")])
            A.require_complete(report["cases"])
        with tempfile.TemporaryDirectory() as tmp:
            commands,report,_,_,_=perform(tmp,fail=True)
            self.assertEqual(len([row for row in commands if row[0].startswith("world-")]),3)
            self.assertFalse(any(row[0]=="compare" or row[0]=="install-candidate" for row in commands))
            self.assertFalse(report["qualified"])

    def test_wrong_source_stops_before_input_admission_or_child(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            args=SimpleNamespace(execute=True,evidence=str(root/"evidence"),baseline_root=str(root/"base"),
                                 candidate_root=str(root/"new"),python=str(root/"env/bin/python"))
            env=producer_env()
            with mock.patch.dict(A.os.environ,env,clear=True), mock.patch.object(A.os,"sched_getaffinity",return_value={4}), \
                 mock.patch.object(A.os,"sched_setaffinity"), mock.patch.object(A.H.Supervisor,"admission"), \
                 mock.patch.object(A.H,"source_snapshot",side_effect=A.Refusal("wrong source commit")), \
                 mock.patch.object(A,"prepare_environment",side_effect=AssertionError("environment preparation")), \
                 mock.patch.object(A,"admit_inputs",side_effect=AssertionError("input admission")), \
                 mock.patch.object(A.H.Supervisor,"command",side_effect=AssertionError("child")), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(A.execute(args),1)
            result=json.loads((root/"evidence/result.json").read_text())
            self.assertFalse(result["qualified"]); self.assertIn("wrong source commit",result["error"])

    def test_initial_admission_and_source_checks_precede_budgeted_environment(self):
        for resource_refusal in (True,False):
            with self.subTest(resource_refusal=resource_refusal), tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp).resolve(); events=[]
                args=SimpleNamespace(execute=True,evidence=str(root/"evidence"),baseline_root=str(root/"base"),
                    candidate_root=str(root/"new"),python=str(root/"env/bin/python"))
                def admission(self,phase,*limits):
                    events.append((phase,limits))
                    if resource_refusal: raise A.Refusal("synthetic initial resource refusal")
                def snapshot(source,expected,deadline):
                    events.append(("source",expected))
                    return {"crate_tree":A.CRATES["baseline"] if expected==A.SOURCES["baseline"] else A.CRATES["candidate"]}
                def preparation(evidence,sources,py,prefix,env,supervisor):
                    events.append(("prepare",supervisor.deadline))
                    self.assertGreater(supervisor.deadline,time.monotonic())
                    self.assertLessEqual(supervisor.deadline,time.monotonic()+A.H.WALL_SECONDS)
                    raise A.Refusal("synthetic stop before actual preparation")
                with mock.patch.dict(A.os.environ,producer_env(),clear=True), \
                     mock.patch.object(A.os,"sched_getaffinity",return_value={4}), mock.patch.object(A.os,"sched_setaffinity"), \
                     mock.patch.object(A.H.Supervisor,"admission",new=admission), \
                     mock.patch.object(A.H,"source_snapshot",side_effect=snapshot), \
                     mock.patch.object(A,"workflow_contract"), mock.patch.object(A.H,"sha",return_value="0"*64), \
                     mock.patch.object(A.H,"require_matrix"), mock.patch.object(A,"prepare_environment",side_effect=preparation), \
                     mock.patch.object(A,"admit_inputs",side_effect=AssertionError("artifact admission")), \
                     contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(A.execute(args),1)
                self.assertEqual(events[0],("initial",(12,2)))
                prepared=[i for i,row in enumerate(events) if row[0]=="prepare"]
                self.assertEqual(len(prepared),0 if resource_refusal else 1)
                if prepared: self.assertEqual([row[0] for row in events[:prepared[0]]],["initial","source","source","source"])

    def test_terminal_inventory_error_cannot_leave_positive_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); result=dict(qualified=True,status="exports_complete_pending_completed_job")
            with mock.patch.object(A.H,"payload_inventory",side_effect=A.Refusal("synthetic inventory refusal")):
                A.finish_report(root,result,True,time.monotonic()+10)
            saved=json.loads((root/"result.json").read_text())
            self.assertIs(saved["qualified"],False); self.assertEqual(saved["status"],"refused")
            self.assertIn("inventory_error",saved)

    def test_workflow_is_a_dormant_closed_template(self):
        root=SCRIPT.parents[1]
        text=(root/"docs/experiments/native-default-output-identity-workflow.yml").read_text()
        self.assertIn("branches: ["+A.ACTIVE_BRANCH+"]",text)
        self.assertIn("paths: ["+A.WORKFLOW_PATH+"]",text)
        self.assertIn("github.event_name == 'push'",text)
        self.assertNotIn("workflow_dispatch",text)
        self.assertNotIn("pip install",text)
        self.assertNotIn("uv sync",text)
        self.assertFalse((root/".github/workflows/native-default-output-identity.yml").exists())
        for source in A.SOURCES.values(): self.assertIn("ref: "+source,text)
        for flag in ("--faith-ids","--checkpoint","--resume","maturin build","--scientific-claims"):
            self.assertNotIn(flag,text)


if __name__ == "__main__":
    unittest.main()
