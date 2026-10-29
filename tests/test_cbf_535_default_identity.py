"""Tiny stdlib contracts: saved metadata and mocked children, never real worlds."""
from copy import deepcopy
from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock
import zipfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("cbf_535_contracts", ROOT/"scripts/cbf_535_default_identity.py")
B = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = B
spec.loader.exec_module(B)
SAVED = json.loads((ROOT/"tests/fixtures/cbf_535_default_identity_inputs.json").read_bytes())["arms"]
NOW = datetime(2026, 10, 29, tzinfo=timezone.utc)


def encoded(value):
    return json.dumps(value, sort_keys=True).encode()


def producer_env():
    return dict(GITHUB_ACTIONS="true", GITHUB_REPOSITORY=B.A.REPOSITORY, GITHUB_EVENT_NAME="push",
        GITHUB_REF="refs/heads/"+B.ACTIVE_BRANCH, GITHUB_WORKFLOW_REF=B.A.REPOSITORY+"/"+B.WORKFLOW_PATH+
        "@refs/heads/"+B.ACTIVE_BRANCH, GITHUB_JOB=B.JOB_KEY, GITHUB_RUN_ATTEMPT="1", GITHUB_RUN_ID="42", GITHUB_SHA="1"*40)


def ci_values(arm):
    saved, wheel = SAVED[arm], B.WHEELS[arm]
    payload = {"ci-native-wheel/manifest.json": encoded(saved["wheel"]["member"])}
    pins = {"ci-native-wheel/manifest.json": B.A.pin_bytes(payload["ci-native-wheel/manifest.json"]),
            wheel.member: {"bytes": wheel.size, "sha256": wheel.sha256}}
    pre = {"native-identity.json": encoded(saved["preflight"]["member"])}
    pre_pins = {"native-identity.json": B.A.pin_bytes(pre["native-identity.json"]),
                "native.xml": B.A.pin_bytes(b"synthetic nonempty XML placeholder")}
    return pins, payload, pre_pins, pre


def probe_value(arm, source, prefix, digest="d"*64):
    wheel = B.WHEELS[arm]
    runtime = dict(python=B.A.PYTHON, version=B.A.PYTHON+" (synthetic contract)", implementation="CPython",
        platform="synthetic same host", machine="x86_64", executable=str(prefix/"bin/python"), prefix=str(prefix),
        affinity=[4], cpu_count=1, process_cpu_count=1, optimize=0, no_user_site=1, dont_write_bytecode=True,
        thread_env={**B.H.CAPS, "PYTHONHASHSEED": "0", "OPENBLAS_THREAD_TIMEOUT": "16"},
        packages={name: "synthetic1" for name in B.A.PACKAGE_NAMES})
    environment = {k: runtime[k] for k in ("python", "implementation", "executable", "platform", "machine", "cpu_count", "process_cpu_count", "packages")}
    environment.update(affinity_cpu_count=1, thread_env={k:v for k,v in runtime["thread_env"].items() if k != "CARGO_BUILD_JOBS"})
    native_path = str(prefix/"lib/chronicler_agents/native.so")
    return dict(source={"git_sha": B.SOURCES[arm], "git_ref": None, "package_dir": str(source/"src/chronicler"), "package_digest": digest},
        source_file=str(source/"src/chronicler/__init__.py"), prefix=str(prefix), native_file=native_path,
        native=dict(status="found", source="imported", module_file=native_path, bytes=wheel.native_size, sha256=wheel.native_sha256),
        schemas=deepcopy(B.EXPECTED_SCHEMAS), affinity=[4], runtime=runtime, environment=environment)


class Contracts(unittest.TestCase):
    def test_exact_registered_matrix_and_immutable_arms(self):
        self.assertEqual(len(B.case_rows()), 18)
        self.assertEqual([r["arm"] for r in B.case_rows()], ["baseline"]*9+["candidate"]*9)
        self.assertEqual(2*sum(int(cli[cli.index("--turns")+1]) for cli,_ in B.H.CASES.values()), 3200)
        self.assertEqual(B.WHEELS["baseline"].sha256, "556c6677c4cb998cd6ad4b284d0f67a7e79368f86831b458c3885943de3b95ac")
        self.assertNotEqual(B.WHEELS["baseline"].sha256, B.A.WHEELS["candidate"].sha256)
        with self.assertRaises(TypeError): B.SOURCES["baseline"] = "0"*40
        with self.assertRaises(FrozenInstanceError): B.WHEELS["candidate"].size = 1

    def test_saved_official_four_publications_match_exact_pins(self):
        for role,pin in B.ARTIFACTS.items():
            with self.subTest(role=role):
                arm,kind = role.split("-",1); saved = SAVED[arm]
                result = B.validate_publication(pin, saved["run"], saved["job"], saved[kind]["artifact"], NOW)
                self.assertEqual(result["identity"]["source"], B.SOURCES[arm])

    def test_publication_wrong_authority_and_expiry_are_refused(self):
        role = "candidate-wheel"; pin = B.ARTIFACTS[role]; saved = SAVED["candidate"]
        rows = [saved["run"],saved["job"],saved["wheel"]["artifact"]]
        for index,key,value in [(0,"head_sha",B.SOURCES["baseline"]),(0,"run_attempt",2),(0,"id",True),
            (1,"id",123338805674),(1,"name","Python native"),(1,"run_attempt",True),
            (2,"digest","sha256:"+"0"*64),(2,"expires_at","2026-11-13T10:33:21Z"),(2,"expired",True)]:
            with self.subTest(index=index,key=key,value=value):
                values = deepcopy(rows); values[index][key] = value
                with self.assertRaises(B.Refusal): B.validate_publication(pin,*values,NOW)
        with self.assertRaises(B.Refusal): B.validate_publication(pin,*rows,B.A.utc(pin.expiry))

    def test_actual_build_step_numbers_names_and_success_required(self):
        saved = SAVED["baseline"]; pin = B.ARTIFACTS["baseline-wheel"]
        for key,value in [("number",16),("name","Unrelated build"),("conclusion","skipped")]:
            with self.subTest(key=key):
                job = deepcopy(saved["job"]); next(s for s in job["steps"] if s["number"] == 12)[key] = value
                with self.assertRaises(B.Refusal): B.validate_publication(pin,saved["run"],job,saved["wheel"]["artifact"],NOW)

    def test_saved_both_ci_member_schemas_and_historical_paths(self):
        for arm in B.SOURCES:
            with self.subTest(arm=arm):
                value = B.validate_ci_arm(arm,*ci_values(arm))
                self.assertTrue(value["historical_paths_only"])
                self.assertIsNone(value["actual_fresh_schema_observation"])

    def test_ci_cross_arm_and_duplicated_native_fields_refused(self):
        with self.assertRaises(B.Refusal): B.validate_ci_arm("candidate",*ci_values("baseline"))
        for section,key,value in [("installed_native","bytes",1),("installed_native","wheel_member_sha256","0"*64),
                                   ("wheel","sha256",B.WHEELS["baseline"].sha256)]:
            with self.subTest(section=section,key=key):
                pins,payload,ppins,pre = ci_values("candidate")
                manifest = json.loads(payload["ci-native-wheel/manifest.json"]); manifest[section][key] = value
                payload["ci-native-wheel/manifest.json"] = encoded(manifest)
                with self.assertRaises(B.Refusal): B.validate_ci_arm("candidate",pins,payload,ppins,pre)

    def test_ci_extra_schema_member_and_wrong_real_class_refused(self):
        for change in ("extra","class","path"):
            with self.subTest(change=change):
                pins,payload,ppins,pre = ci_values("baseline")
                value = json.loads(pre["native-identity.json"])
                if change == "extra": value["unexpected"] = True
                elif change == "class": value["classes"] = ["FakeSimulator"]
                else: value["compiled_extension"] = "relative/native.so"
                pre["native-identity.json"] = encoded(value)
                with self.assertRaises(B.Refusal): B.validate_ci_arm("baseline",pins,payload,ppins,pre)

    def test_closed_producer_refuses_event_branch_attempt_and_job(self):
        self.assertEqual(B.producer_context(producer_env())["event"],"push")
        for key,value in [("GITHUB_EVENT_NAME","workflow_dispatch"),("GITHUB_REF","refs/heads/main"),
                          ("GITHUB_RUN_ATTEMPT","2"),("GITHUB_JOB",B.A.JOB_KEY),("GITHUB_RUN_ID","0"),
                          ("GITHUB_WORKFLOW_REF",producer_env()["GITHUB_WORKFLOW_REF"]+"x")]:
            with self.subTest(key=key):
                env = producer_env(); env[key] = value
                with self.assertRaises(B.Refusal): B.producer_context(env)

    def test_workflow_dormant_or_exact_active_copy_only(self):
        B.workflow_contract(ROOT,active_required=False)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); template = root/B.TEMPLATE_PATH; template.parent.mkdir(parents=True)
            template.write_bytes((ROOT/B.TEMPLATE_PATH).read_bytes())
            active = root/B.WORKFLOW_PATH; active.parent.mkdir(parents=True)
            active.write_bytes(template.read_bytes()); B.workflow_contract(root)
            active.write_bytes(template.read_bytes()+b"\n# drift\n")
            with self.assertRaises(B.Refusal): B.workflow_contract(root)

    def test_immutable_utilities_rechecked_even_with_cached_module(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            for name in B.KERNELS: (directory/name).write_bytes((ROOT/"scripts"/name).read_bytes())
            path = directory/"arc_output_identity_qualification.py"; raw = path.read_bytes(); path.write_bytes(b"!"+raw[1:])
            with mock.patch("builtins.exec",side_effect=AssertionError("must authenticate all before exec")):
                with self.assertRaises(RuntimeError): B.load_utilities(directory)

    def test_utility_apis_do_not_call_old_pair_orchestration(self):
        import ast
        tree = ast.parse((ROOT/"scripts/cbf_535_default_identity.py").read_bytes())
        called = {n.func.attr for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute)
                  and isinstance(n.func.value,ast.Name) and n.func.value.id == "A"}
        self.assertEqual(called, {"ArtifactPin","WheelPin","validate_publication","Transport","inspect_artifact",
                                 "validate_wheel","utc","exact_int","runtime_seal","install_command","prepare_environment"})

    def test_bounded_eocd_before_zipfile_and_zip64_refused(self):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream,"w") as z: z.writestr("tiny",b"x")
        raw = stream.getvalue(); B.bounded_zip(io.BytesIO(raw))
        at = raw.rfind(b"PK\x05\x06")
        for mode in ("count","offset","zip64","tail"):
            with self.subTest(mode=mode):
                changed = bytearray(raw)
                if mode == "count": struct.pack_into("<HH",changed,at+8,65535,65535)
                elif mode == "offset": struct.pack_into("<I",changed,at+16,0xffffffff)
                elif mode == "zip64": changed[at-20:at-16] = b"PK\x06\x07"
                else: changed += b"trailing"
                with self.assertRaises(B.Refusal): B.bounded_zip(io.BytesIO(changed))

    def test_wrong_archive_digest_refused_before_parser(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary)/"tiny.zip"; path.write_bytes(b"no archive")
            with mock.patch.object(B.A,"inspect_artifact",side_effect=AssertionError("parser must not run")):
                with self.assertRaises(B.Refusal): B.inspect_input(path,B.ARTIFACTS["candidate-wheel"],())

    def test_package_digest_uses_all_python_names_and_hashes(self):
        rows = {"src/chronicler/z.py":{"sha256":"b"*64},"src/chronicler/a.py":{"sha256":"a"*64},"README.md":{"sha256":"c"*64}}
        expected = hashlib.sha256(b"a.py\0"+b"a"*64+b"\nz.py\0"+b"b"*64+b"\n").hexdigest()
        self.assertEqual(B.package_digest({"files":rows}),expected)

    def test_input_plumbing_seals_each_original_publication_before_and_after(self):
        events = []; contents = {}
        for arm in B.SOURCES:
            pins,payload,pre_pins,pre = ci_values(arm)
            payload[B.WHEELS[arm].member] = b"synthetic wheel placeholder, not a real wheel"
            contents[arm+"-wheel"] = (pins,payload); contents[arm+"-preflight"] = (pre_pins,pre)
        class FakeTransport:
            def metadata(self,pin):
                role = next(k for k,v in B.ARTIFACTS.items() if v == pin); arm,kind = role.split("-",1)
                events.append(("metadata",role)); saved = SAVED[arm]
                return B.validate_publication(pin,saved["run"],saved["job"],saved[kind]["artifact"],NOW)
            def download(self,pin,path):
                events.append(("download",pin.artifact_id)); path.write_bytes(b"synthetic archive placeholder")
        def inspect(path,pin,selected):
            role = next(k for k,v in B.ARTIFACTS.items() if v == pin)
            expected = {"ci-native-wheel/manifest.json",B.WHEELS[role.split("-",1)[0]].member} if role.endswith("-wheel") else {"native-identity.json"}
            self.assertEqual(selected,expected); events.append(("inspect",role)); return contents[role]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); (root/"inputs").mkdir()
            for arm in B.SOURCES: (root/"wheels"/arm).mkdir(parents=True)
            with mock.patch.object(B.A,"Transport",return_value=FakeTransport()),mock.patch.object(B,"inspect_input",side_effect=inspect), \
                mock.patch.object(B,"bounded_zip"),mock.patch.object(B.A,"validate_wheel",return_value={"synthetic":True}):
                paths = B.admit_inputs(root,SimpleNamespace(),100)
            self.assertEqual(list(paths),list(B.ARTIFACTS))
            for i,(role,pin) in enumerate(B.ARTIFACTS.items()):
                self.assertEqual(events[4*i:4*i+4],[("metadata",role),("download",pin.artifact_id),("inspect",role),("metadata",role)])
            value = json.loads((root/"input-admission.json").read_bytes())
            self.assertEqual(set(value["publications"]),set(B.ARTIFACTS))

    def test_actual_fresh_probe_both_arms_same_runtime(self):
        prefix = Path("/synthetic/env"); runtime = None
        for arm in B.SOURCES:
            with self.subTest(arm=arm):
                source = Path("/synthetic")/arm
                runtime = B.validate_probe(probe_value(arm,source,prefix),arm,source,prefix,"d"*64,runtime)

    def test_probe_rejects_schema_native_source_and_runtime_mismatches(self):
        source,prefix = Path("/synthetic/candidate"),Path("/synthetic/env")
        mutations = [("schemas","AgentSimulator",{}),("native","sha256",B.WHEELS["baseline"].native_sha256),
            ("native","source","import_path"),("source","git_sha",B.SOURCES["baseline"]),
            ("source","package_digest","0"*64),("runtime","optimize",1),("runtime","cpu_count",True),
            ("runtime","affinity",[0,1]),("runtime","packages",{}),("environment","affinity_cpu_count",2)]
        for section,key,value in mutations:
            with self.subTest(section=section,key=key):
                probe = probe_value("candidate",source,prefix); probe[section][key] = value
                with self.assertRaises(B.Refusal): B.validate_probe(probe,"candidate",source,prefix,"d"*64)

    def test_runtime_change_between_arms_refused(self):
        source,prefix = Path("/synthetic/candidate"),Path("/synthetic/env")
        probe = probe_value("candidate",source,prefix); previous = deepcopy(probe["runtime"]); previous["platform"] = "other host"
        with self.assertRaises(B.Refusal): B.validate_probe(probe,"candidate",source,prefix,"d"*64,previous)

    def test_all_complete_rows_and_order_required(self):
        rows = B.case_rows()
        with self.assertRaises(B.Refusal): B.require_complete(rows)
        for row in rows: row.update(status="complete",audit_sha256="a"*64)
        B.require_complete(rows)
        for changed in (rows[:-1],list(reversed(rows)),rows+[rows[0]]):
            with self.subTest(rows=len(changed)):
                with self.assertRaises(B.Refusal): B.require_complete(changed)

    def run_fake_cases(self,root,*,bad_probe=False,compare_failure=False):
        roots = {arm:root/"source"/arm for arm in B.SOURCES}; prefix = root/"prefix"
        for folder in ("wheels","native","raw","probes","audits"):
            (root/folder).mkdir()
        for arm in B.SOURCES:
            (root/"wheels"/arm).mkdir(); (root/"native"/arm).mkdir()
            (root/"wheels"/arm/B.A.WHEEL_NAME).write_bytes(b"placeholder")
        native = prefix/"lib/chronicler_agents/native.so"; native.parent.mkdir(parents=True); native.write_bytes(b"placeholder")
        installer = root/"uv"; installer.write_bytes(b"placeholder")
        snapshots = {arm:{"files":{}} for arm in B.SOURCES}; digest = B.package_digest(snapshots["baseline"])
        report = {"cases":B.case_rows(),"installer":{"uv":{"path":str(installer),"sha256":"1"*64}},
                  "actual_observations":{arm:None for arm in B.SOURCES}}
        commands = []; current = [None]; real_sha = B.H.sha
        def sha(path):
            p = Path(path)
            if p == installer: return "1"*64
            if p == native: return B.WHEELS[current[0]].native_sha256
            for arm in B.SOURCES:
                if p == root/"wheels"/arm/B.A.WHEEL_NAME: return B.WHEELS[arm].sha256
                if p.parent == root/"native"/arm: return B.WHEELS[arm].native_sha256
            return real_sha(p)
        def command(label,args,env,cwd):
            commands.append((label,args))
            if label.startswith("install-"): current[0] = label.removeprefix("install-")
            elif label.startswith("probe-"):
                arm = args[args.index("--arm")+1]; value = probe_value(arm,roots[arm],prefix,digest)
                if bad_probe: value["schemas"] = {}
                B.H.write(args[args.index("--out")+1],value)
            elif label.startswith("world-"):
                arm = current[0]; self.assertIsNotNone(report["actual_observations"][arm])
                value = probe_value(arm,roots[arm],prefix,digest)
                (Path(cwd)/args[-1]).mkdir()
                (Path(cwd)/"which.txt").write_text("chronicler "+value["source_file"]+"\nnative "+str(native)+" "+B.WHEELS[arm].native_sha256+"\n")
            elif label.startswith("audit-"): B.H.write(args[-1],{"files":{}})
            elif label == "compare" and compare_failure: raise B.Refusal("injected comparator failure")
        supervisor = SimpleNamespace(command=command,admission=mock.Mock(),event=mock.Mock(),cleanup_complete=True)
        with mock.patch.object(B.H,"sha",side_effect=sha):
            result = B.run_cases(root,roots,str(prefix/"bin/python"),prefix,{},supervisor,report,snapshots)
        return commands,report,result

    def test_original_case_order_36_probes_and_no_flag_comparator(self):
        with tempfile.TemporaryDirectory() as temporary:
            commands,report,result = self.run_fake_cases(Path(temporary))
            expected = ["world-"+r["arm"]+"-"+r["case"] for r in B.case_rows()]
            self.assertEqual([label for label,_ in commands if label.startswith("world-")],expected)
            self.assertEqual(sum(label.startswith("probe-") for label,_ in commands),36)
            self.assertEqual(sum(label.startswith("install-") for label,_ in commands),2)
            self.assertEqual(commands[-1][0],"compare")
            self.assertEqual(commands[-1][1][-3:],["compare",str(Path(temporary)/"raw/baseline"),str(Path(temporary)/"raw/candidate")])
            B.require_complete(report["cases"]); self.assertEqual(set(result),set(B.SOURCES))

    def test_bad_first_actual_schema_prevents_any_world(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(B.Refusal,"native/schema"):
                self.run_fake_cases(Path(temporary),bad_probe=True)
            self.assertFalse((Path(temporary)/"raw/baseline/off_s42").exists())

    def test_comparator_exception_is_not_a_positive_completion(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(B.Refusal,"injected comparator"):
                self.run_fake_cases(Path(temporary),compare_failure=True)

    def test_explicit_execute_required_before_any_work(self):
        with mock.patch.object(B.H,"Supervisor",side_effect=AssertionError("must not start")):
            with self.assertRaises(B.Refusal): B.execute(SimpleNamespace(execute=False))

    def test_initial_admission_and_source_validation_precede_environment(self):
        events = []; snapshot = {"crate_tree":None,"files":{n:{"bytes":1,"sha256":"1"*64} for n in B.SHARED_FILES}}
        class FakeSupervisor:
            cleanup_complete = True
            def __init__(self,root,deadline): events.append(("supervisor",deadline))
            def admission(self,phase,disk,ram): events.append((phase,disk,ram))
        def source(root,sha,deadline):
            events.append(("source",sha)); value = deepcopy(snapshot)
            value["crate_tree"] = B.CRATES.get(next((a for a,s in B.SOURCES.items() if s == sha),"control")); return value
        def preparation(*args):
            self.assertEqual(events[1],("initial",12,2)); self.assertEqual(sum(e[0] == "source" for e in events),3)
            self.assertGreater(events[0][1],B.time.monotonic()); events.append(("prepare",)); raise B.Refusal("injected preparation stop")
        with tempfile.TemporaryDirectory() as temporary:
            args = SimpleNamespace(execute=True,evidence=str(Path(temporary)/"evidence"),baseline_root=temporary+"/baseline",
                candidate_root=temporary+"/candidate",python=temporary+"/prefix/bin/python")
            with mock.patch.dict(os.environ,producer_env(),clear=True), mock.patch.object(B.H,"Supervisor",FakeSupervisor), \
                mock.patch.object(B.H,"source_snapshot",side_effect=source),mock.patch.object(B,"workflow_contract"), \
                mock.patch.object(B.H,"require_matrix"),mock.patch.object(B.os,"sched_setaffinity"), \
                mock.patch.object(B.A,"prepare_environment",side_effect=preparation),mock.patch.object(B,"final_checks"), \
                mock.patch.object(B,"finish_report"),contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(B.execute(args),1)
            self.assertEqual(events[-1],("prepare",))

    def test_quiescence_required_before_final_source_or_inventory(self):
        with mock.patch.object(B.H,"source_snapshot",side_effect=AssertionError("must wait for quiescence")):
            with self.assertRaisesRegex(B.Refusal,"cleanup"):
                B.final_checks(Path("/unused"),{}, {},{}, {},{}, {"cases":[]},SimpleNamespace(cleanup_complete=False),100)

    def test_export_mutation_and_audit_mutation_refuse_finalization(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); (root/"audits").mkdir(); (root/"raw/baseline/off_s42").mkdir(parents=True)
            audit = root/"audits/baseline-off_s42.json"; B.H.write(audit,{"files":{"state.json":{"bytes":1,"sha256":"1"*64}}})
            report = {"cases":[dict(arm="baseline",case="off_s42",status="complete",audit_sha256=B.H.sha(audit))]}
            original = B.H.sha
            def digest(path):
                for arm,wheel in B.WHEELS.items():
                    if Path(path) == root/"wheels"/arm/B.A.WHEEL_NAME: return wheel.sha256
                return original(path)
            with mock.patch.object(B.H,"sha",side_effect=digest),mock.patch.object(B.time,"monotonic",return_value=1):
                with self.assertRaisesRegex(B.Refusal,"exports/audit"):
                    B.final_checks(root,{}, {},{}, {},{},report,SimpleNamespace(cleanup_complete=True),100)
                report["cases"][0]["audit_sha256"] = "0"*64
                with self.assertRaisesRegex(B.Refusal,"exports/audit"):
                    B.final_checks(root,{}, {},{}, {},{},report,SimpleNamespace(cleanup_complete=True),100)

    def test_negative_first_inventory_and_late_terminal_write_cannot_grant(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); clock = [99]; states = []; original = B.H.write
            def write(path,value):
                original(path,value)
                if Path(path).name == "result.json":
                    states.append(value["qualified"])
                    if value["qualified"]: clock[0] = 101
            report = {"qualified":True,"status":"exports_complete_pending_completed_job"}
            with mock.patch.object(B.H,"write",side_effect=write),mock.patch.object(B.time,"monotonic",side_effect=lambda:clock[0]):
                B.finish_report(root,report,True,100)
            self.assertEqual(states,[False,True,False])
            self.assertFalse(json.loads((root/"result.json").read_bytes())["qualified"])

    def test_inventory_failure_and_live_writer_withhold_positive_receipt(self):
        for quiescent in (False,True):
            with self.subTest(quiescent=quiescent),tempfile.TemporaryDirectory() as temporary:
                report = {"qualified":True,"status":"pending"}
                with mock.patch.object(B.H,"payload_inventory",side_effect=B.Refusal("injected inventory error")):
                    B.finish_report(Path(temporary),report,quiescent,B.time.monotonic()+10)
                self.assertFalse(report["qualified"])

    def test_describe_does_not_prepare_probe_download_or_admit(self):
        with mock.patch.object(B,"execute",side_effect=AssertionError("no execution")), \
            mock.patch.object(B,"probe",side_effect=AssertionError("no probe")),contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(B.main(["describe"]),0)
        value = json.loads(output.getvalue()); self.assertEqual(value["worlds"],18)
        self.assertEqual(value["actual_observations"],{"baseline":None,"candidate":None})
        self.assertFalse(value["activation_authorized"])


if __name__ == "__main__":
    unittest.main()
