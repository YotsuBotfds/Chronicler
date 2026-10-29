"""Pure synthetic/API-control contracts; no compiled module, World or physics."""
from __future__ import annotations
from contextlib import nullcontext
from copy import deepcopy
from datetime import datetime, timezone
import ast
import importlib.util
import io
import json
from pathlib import Path
import stat
import sys
from types import SimpleNamespace
import urllib.error
import zipfile

import pytest
SPEC = importlib.util.spec_from_file_location("care_api_proof_under_test", Path(__file__).resolve().parents[1]/"scripts/retained_kin_care_native_api_proof.py")
P = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = P
SPEC.loader.exec_module(P)

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT/"tests/fixtures/retained_kin_care"
NOW = datetime(2026, 10, 29, tzinfo=timezone.utc)


def official():
    return json.loads((FIXTURES/"source23d_origin.json").read_bytes())


def test_pending_refuses_before_environment_path_helper_or_native(monkeypatch):
    monkeypatch.setattr(P, "REVIEWED_ACTIVATION", None)
    class Forbidden:
        def __getitem__(self, key):
            raise AssertionError("environment accessed before pending refusal")
    monkeypatch.setattr(P, "os", SimpleNamespace(environ=Forbidden()))
    monkeypatch.setattr(P, "load_helpers", lambda *_: pytest.fail("helper loaded"))
    with pytest.raises(P.Refused, match="activation_pending"):
        P.execute("unused", "unused")
    with pytest.raises(P.Refused, match="activation_pending"):
        P.probe("unused", "unused", "unused")


def test_registered_factory_uses_explicit_qualified_producer_and_reference(monkeypatch):
    monkeypatch.setattr(P, "REVIEWED_ACTIVATION", "a"*64)
    monkeypatch.setattr(P, "expiry_check", lambda: None)
    value = P.registration()
    assert value == dict(root="a"*64, producer_root="d22bc652060dba7f5b29e511ce813f1948f2880c4f02ad1917f69eab997b86fa",
                        reference_root="530e1f31f61f7c59b3b96f5663c5a4d691d8aaabccdd4c858f630fe419f014d7")


def test_actual_retained_official_projection_is_accepted_without_io():
    assert P.validate_metadata(official(), NOW) == official()


@pytest.mark.parametrize("role,key,bad", [
    ("run", "id", True), ("run", "run_attempt", 2), ("run", "head_sha", "f"*40),
    ("run", "head_branch", "main"), ("run", "path", ".github/workflows/other.yml"),
    ("run", "status", "in_progress"), ("run", "conclusion", "failure"),
    ("job", "id", P.PRODUCER_JOB+1), ("job", "run_id", True), ("job", "run_attempt", 2),
    ("job", "head_sha", "f"*40), ("job", "head_branch", "main"), ("job", "name", "Other job"), ("job", "status", "queued"),
    ("job", "conclusion", "failure"), ("artifact", "id", True), ("artifact", "name", "other"),
    ("artifact", "size_in_bytes", P.ARTIFACT_BYTES+1), ("artifact", "digest", "sha256:"+"f"*64),
    ("artifact", "expired", True), ("artifact", "expires_at", "2026-12-31T00:00:00Z"),
    ("artifact", "workflow_run", {"id": P.PRODUCER_RUN, "head_sha": "f"*40, "head_branch": P.PRODUCER_BRANCH}),
])
def test_every_producer_origin_dimension_refuses(role, key, bad):
    rows = official(); rows[role][key] = bad
    with pytest.raises(P.Refused):
        P.validate_metadata(rows, NOW)


@pytest.mark.parametrize("value", ["2026-11-12", "2026-11-12T16:11:27+00:00", "2026-99-12T16:11:27Z", True, None])
def test_strict_expiry_format(value):
    with pytest.raises(P.Refused):
        P.timestamp(value)


def test_expiry_at_boundary_refuses():
    with pytest.raises(P.Refused, match="input_expired"):
        P.validate_metadata(official(), P.timestamp(P.ARTIFACT_EXPIRY))


@pytest.mark.parametrize("raw", [b'{"a":1,"a":2}', b'{"a":NaN}', b'{"a":Infinity}', b'{"a":1e999}'])
def test_duplicate_and_nonfinite_json_refused(raw):
    with pytest.raises(P.Refused):
        P.strict_json(raw)


def test_sanitized_environment_keeps_trust_but_drops_python_loader_and_token(tmp_path):
    inherited = dict(PYTHONPATH="untrusted", PYTHONHOME="untrusted", LD_LIBRARY_PATH="untrusted", LD_PRELOAD="untrusted",
        GH_TOKEN="fixture-never-propagate", PYTHONHASHSEED="random", OMP_NUM_THREADS="99", HTTPS_PROXY="fixture-proxy",
        SSL_CERT_FILE="fixture-ca", PATH="untrusted", HOME="untrusted")
    env = P.child_environment(tmp_path, "/selected/bin/python", inherited)
    assert all(key not in env for key in ("PYTHONPATH", "PYTHONHOME", "LD_LIBRARY_PATH", "LD_PRELOAD", "GH_TOKEN"))
    assert env["HTTPS_PROXY"] == "fixture-proxy" and env["SSL_CERT_FILE"] == "fixture-ca"
    assert env["PYTHONHASHSEED"] == "0" and env["PYTHON_CPU_COUNT"] == "1"
    assert env["PATH"] == "/selected/bin:/usr/bin:/bin"
    assert all(env[key] == "1" for key in P.THREAD_KEYS)


def runtime():
    return dict(python="3.13.17", safe_path=True, no_user_site=1, dont_write_bytecode=True, hash_randomization=0,
        cpu_count=1, process_cpu_count=1, affinity=[9], thread_env={key: "1" for key in P.THREAD_KEYS})


def test_sanitized_runtime_is_a_real_observation_contract():
    assert P.runtime_contract(runtime()) == runtime()


@pytest.mark.parametrize("key,bad", [("safe_path", False), ("no_user_site", 0), ("no_user_site", True),
    ("dont_write_bytecode", False), ("hash_randomization", 1), ("hash_randomization", False),
    ("cpu_count", 2), ("cpu_count", True), ("process_cpu_count", 2), ("affinity", [0, 1]), ("affinity", [True])])
def test_actual_startup_flags_and_cpu_observations_must_match(key, bad):
    value = runtime(); value[key] = bad
    with pytest.raises(P.Refused, match="runtime_contract"):
        P.runtime_contract(value)


@pytest.mark.parametrize("key", P.THREAD_KEYS)
def test_each_numerical_cap_is_checked(key):
    value = runtime(); value["thread_env"][key] = "2"
    with pytest.raises(P.Refused):
        P.runtime_contract(value)


def test_measured_reference_is_digest_based_and_matches_closed_source():
    value = json.loads((FIXTURES/"schema_reference_191.json").read_bytes())
    assert value["raw_descriptor_text_present"] is False
    assert value["root_sha256"] == P.REFERENCE_ROOT
    assert value["artifact_id"] == P.REFERENCE_ARTIFACT and value["artifact_sha256"] == P.REFERENCE_ZIP_SHA
    assert value["member"] == P.REFERENCE_MEMBER
    assert {name: (row["version"], row["fingerprint"], row["schema_sha256"]) for name,row in value["schemas"].items()} == P.SCHEMAS


def fake_classes(monkeypatch):
    schemas = {name: (1, f"{i:016x}", P.digest((name+" synthetic descriptor").encode()))
               for i,name in enumerate(P.SCHEMAS)}
    monkeypatch.setattr(P, "SCHEMAS", schemas)
    package = SimpleNamespace()
    for name,(version,fingerprint,_) in schemas.items():
        value=(version,fingerprint,name+" synthetic descriptor")
        setattr(package, name, type(name, (), {"checkpoint_schema": staticmethod(lambda value=value: value)}))
    return package


def test_schema_tuple_uses_all_three_real_export_object_links_in_fixture(monkeypatch):
    package = fake_classes(monkeypatch)
    assert list(P.schema_summaries(package, package)) == list(P.SCHEMAS)
    wrong = SimpleNamespace(**vars(package)); wrong.AgentSimulator = type("standin", (), {})
    with pytest.raises(P.Refused, match="compiled_class_identity"):
        P.schema_summaries(package, wrong)


@pytest.mark.parametrize("value", [[1, "0"*16, "descriptor"], (True, "0"*16, "descriptor"),
    (1, "bad", "descriptor"), (1, "0"*16, b"descriptor"), (1, "0"*16, ""), (1, "0"*16, "wrong")])
def test_schema_tuple_types_version_and_descriptor_hash_cannot_be_substituted(monkeypatch, value):
    package = fake_classes(monkeypatch)
    package.AgentSimulator.checkpoint_schema = staticmethod(lambda: value)
    with pytest.raises(P.Refused):
        P.schema_summaries(package, package)


class EmptyFixture:
    def __init__(self, *, discard_invalid=False, change_bytes=False, rows=0):
        self.prepared = False; self.discard_invalid = discard_invalid; self.change_bytes = change_bytes
        self.rows = rows; self.calls = []
    def get_snapshot(self): return SimpleNamespace(num_rows=self.rows)
    def checkpoint_state(self): return b"mutated" if self.change_bytes and self.prepared else b"persistent-fixture"
    def prepare_health_work(self, *args, care_policy="spouse"):
        self.calls.append((args, care_policy))
        assert args == ([], [], [], .5, .2)
        if care_policy == "kin":
            if self.discard_invalid: self.prepared = False
            raise ValueError("fixture-invalid")
        self.prepared = True; return []
    def finish_health_work(self, turn, rate):
        assert (turn, rate) == (0, 0.0)
        if not self.prepared: return ([], [], [])
        self.prepared = False
        return ([], [], [(0, 0.0, 0.0, 0)])


def test_empty_fixture_exercises_actual_five_positional_and_keyword_paths():
    sim = EmptyFixture(); got = P.exercise_empty_api(sim)
    assert [call[1] for call in sim.calls] == ["spouse", "kin", "retained_kin"]
    assert got["instances"] == 1 and got["agents"] == got["ticks"] == got["World_instances"] == got["restores"] == 0
    assert got["invalid_policy_rejected"] and got["empty_prepared_marker_retained"]
    assert got["nonempty_care_qualified"] is False and len(got["native_state_observations"]) == 6
    assert all(row["equals_baseline"] for row in got["native_state_observations"])
    assert all("body" not in row for row in got["native_state_observations"])


@pytest.mark.parametrize("kwargs,code", [({"discard_invalid":True}, "empty_prepared_marker_lost"),
    ({"change_bytes":True}, "persistent_state_changed"), ({"rows":1}, "nonempty_fixture")])
def test_empty_probe_cannot_succeed_after_mutation_or_population(kwargs, code):
    with pytest.raises(P.Refused, match=code):
        P.exercise_empty_api(EmptyFixture(**kwargs))


def zip_bytes(rows):
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for name, body, mode in rows:
            info=zipfile.ZipInfo(name); info.external_attr=(mode << 16); info.compress_type=zipfile.ZIP_DEFLATED
            z.writestr(info, body)
    return out.getvalue()


@pytest.mark.parametrize("name,mode", [("../x", stat.S_IFREG|0o600), ("/x", stat.S_IFREG|0o600),
    ("a\\x", stat.S_IFREG|0o600), ("a//x", stat.S_IFREG|0o600), ("link", stat.S_IFLNK|0o777)])
def test_zip_paths_and_nonregular_modes_refused(name, mode):
    with zipfile.ZipFile(io.BytesIO(zip_bytes([(name,b"x",mode)]))) as z:
        with pytest.raises(P.Refused):
            P.zip_entries(z, members=3, expanded=10, member_bytes=10)


def fake_artifact(monkeypatch):
    native = b"SYNTHETIC NOT AN EXTENSION"
    wheel = zip_bytes([(P.NATIVE_MEMBER,native,stat.S_IFREG|0o644), ("chronicler_agents/__init__.py",b"synthetic",stat.S_IFREG|0o644)])
    monkeypatch.setattr(P,"NATIVE_SHA",P.digest(native));monkeypatch.setattr(P,"NATIVE_BYTES",len(native))
    monkeypatch.setattr(P,"WHEEL_SHA",P.digest(wheel));monkeypatch.setattr(P,"WHEEL_BYTES",len(wheel))
    build = dict(kind="native-shard-current-build-v1", producer_job_key="python-native-build", identity=dict(
        source_commit=P.PRODUCER_SOURCE, run_id=P.PRODUCER_RUN, attempt=P.PRODUCER_ATTEMPT, classes=list(P.SCHEMAS),
        wheel=dict(schema_version=1, source_commit=P.PRODUCER_SOURCE,
        wheel=dict(filename=P.WHEEL_NAME,bytes=len(wheel),sha256=P.WHEEL_SHA,native_member=P.NATIVE_MEMBER),
        installed_native=dict(bytes=len(native),sha256=P.NATIVE_SHA,wheel_member_sha256=P.NATIVE_SHA))))
    raw_build = P.canonical(build);monkeypatch.setattr(P,"BUILD_JSON_SHA",P.digest(raw_build))
    archive = zip_bytes([("ci-native-wheel/build.json",raw_build,stat.S_IFREG|0o644),
        ("chronicler-agents/target/wheels/"+P.WHEEL_NAME,wheel,stat.S_IFREG|0o644)])
    monkeypatch.setattr(P,"ARTIFACT_BYTES",len(archive));monkeypatch.setattr(P,"ARTIFACT_SHA",P.digest(archive))
    return archive,wheel,build


def test_tiny_artifact_full_crc_hash_closure_without_any_import(monkeypatch):
    raw,wheel,build = fake_artifact(monkeypatch)
    name,data,got = P.inspect_artifact(raw)
    assert name == P.WHEEL_NAME and data == wheel and got == build
    with pytest.raises(P.Refused,match="artifact_whole_hash"):
        P.inspect_artifact(raw+b"unexpected")


@pytest.mark.parametrize("field", ["WHEEL_SHA","NATIVE_SHA","BUILD_JSON_SHA"])
def test_each_pinned_whole_or_member_identity_refuses(monkeypatch, field):
    raw,_,_ = fake_artifact(monkeypatch);monkeypatch.setattr(P,field,"f"*64)
    with pytest.raises(P.Refused): P.inspect_artifact(raw)


def test_member_and_expansion_caps_precede_payload_reads():
    raw = zip_bytes([("a",b"xx",stat.S_IFREG|0o644), ("b",b"xx",stat.S_IFREG|0o644)])
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        for limits in [dict(members=1,expanded=10,member_bytes=10), dict(members=3,expanded=3,member_bytes=10), dict(members=3,expanded=10,member_bytes=1)]:
            with pytest.raises(P.Refused): P.zip_entries(z,**limits)


def test_transport_has_only_three_closed_metadata_endpoints(monkeypatch):
    monkeypatch.setattr(P.urllib.request,"build_opener",lambda *_: SimpleNamespace())
    transport=P.Transport("synthetic-credential",lambda:None,9999999999)
    with pytest.raises(P.Refused,match="metadata_endpoint"):
        transport.api("actions/runs/latest")


class Response:
    status = 200
    def __init__(self, raw):self.raw=io.BytesIO(raw)
    def read(self,n):return self.raw.read(n)
    def close(self):pass
    def __enter__(self):return self
    def __exit__(self,*args):pass


def test_storage_redirect_does_not_receive_api_authorization(monkeypatch):
    raw,_,_ = fake_artifact(monkeypatch);requests=[]
    class Opener:
        def open(self,request,timeout):
            requests.append(request)
            if len(requests)==1:
                raise urllib.error.HTTPError(request.full_url,302,"fixture",{"Location":"https://fixture.blob.core.windows.net/closed?synthetic=1"},None)
            return Response(raw)
    monkeypatch.setattr(P.urllib.request,"build_opener",lambda *_:Opener())
    monkeypatch.setattr(P,"network_deadline",lambda *_:nullcontext())
    transport=P.Transport("synthetic-credential",lambda:None,9999999999)
    assert transport.download()==raw
    assert requests[0].get_header("Authorization")=="Bearer synthetic-credential"
    assert requests[1].get_header("Authorization") is None


@pytest.mark.parametrize("location", ["http://fixture.blob.core.windows.net/a", "https://attacker.invalid/a", "https://user:pass@fixture.blob.core.windows.net/a"])
def test_changed_signed_storage_hosts_are_refused_before_storage_read(monkeypatch,location):
    class Opener:
        def open(self,request,timeout):
            raise urllib.error.HTTPError(request.full_url,302,"fixture",{"Location":location},None)
    monkeypatch.setattr(P.urllib.request,"build_opener",lambda *_:Opener())
    monkeypatch.setattr(P,"network_deadline",lambda *_:nullcontext())
    with pytest.raises(P.Refused,match="artifact_redirect_host"):
        P.Transport("synthetic",lambda:None,9999999999).download()


def setup_output(tmp_path):
    out=tmp_path/"metadata";out.mkdir();P.invalidate(out,"not_complete");(out/"probe.json").write_bytes(b'{}\n');return out


def test_complete_publication_hashes_original_payload_and_requires_seal(tmp_path):
    out=setup_output(tmp_path)
    seal=P.publish(out,dict(cleanup_complete=True),lambda:None,lambda:dict(wall=1))
    result=P.strict_json((out/"result.json").read_bytes())
    assert result["complete"] is False and result["status"]=="PROVISIONAL_UNTIL_COMPLETION"
    assert seal["complete"] and seal["result_sha256"]==P.digest((out/"result.json").read_bytes())
    assert result["files"]=={"probe.json":{"bytes":3,"sha256":P.digest(b'{}\n')}}


@pytest.mark.parametrize("failure_call", [1,2,3])
def test_before_result_or_after_seal_fault_always_removes_positive(tmp_path,failure_call):
    out=setup_output(tmp_path);calls=[]
    def check():
        calls.append(1)
        if len(calls)==failure_call:raise P.Refused("synthetic_expiry_or_final_source_fault")
    with pytest.raises(P.Refused):P.publish(out,dict(cleanup_complete=True),check,lambda:{})
    assert not (out/"completion.json").exists()
    assert P.strict_json((out/"result.json").read_bytes())["complete"] is False
    assert (out/"probe.json").read_bytes()==b'{}\n'


def test_owned_complete_logs_copy_exactly_and_capacity_failure_is_explicit(tmp_path,monkeypatch):
    out=setup_output(tmp_path);owned=tmp_path/"owned";(owned/"logs").mkdir(parents=True)
    (owned/"progress.jsonl").write_bytes(b'{"event":"child_cleanup"}\n');(owned/"logs/a.log").write_bytes(b"complete\n")
    assert P.stage_owned(owned,out,require_complete=True)==[]
    assert (out/"progress.jsonl").read_bytes()==(owned/"progress.jsonl").read_bytes()
    assert P.stage_owned(owned,out,require_complete=True)==[]
    monkeypatch.setattr(P,"MIB",128)
    (owned/"logs/b.log").write_bytes(b"x"*129)
    with pytest.raises(P.Refused,match="complete_logs_do_not_fit"):
        P.stage_owned(owned,out,require_complete=True)
    omissions=P.strict_json((out/"omissions.json").read_bytes())
    assert omissions["complete"] is False and omissions["omitted"][0]["bytes"]==129
    assert (owned/"logs/b.log").exists() and not (out/"logs/b.log").exists()


def test_negative_total_capacity_retains_explicit_omissions(tmp_path,monkeypatch):
    out=setup_output(tmp_path);(out/"a.json").write_bytes(b"a"*40);(out/"b.json").write_bytes(b"b"*40)
    monkeypatch.setattr(P,"MAX_OUTPUT",64*1024+64)
    P.bound_negative(out)
    got=P.strict_json((out/"negative-omissions.json").read_bytes())
    assert got["complete"] is False and got["omitted"]
    assert P.strict_json((out/"result.json").read_bytes())["complete"] is False
    assert sum(p.stat().st_size for p in out.rglob("*") if p.is_file())<=P.MAX_OUTPUT


def test_source_probe_order_and_unchanged_helper_pins():
    tree=ast.parse((ROOT/"scripts/retained_kin_care_native_api_proof.py").read_text())
    probe=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=="probe")
    calls=[n for n in ast.walk(probe) if isinstance(n,ast.Call)]
    source=ast.get_source_segment((ROOT/"scripts/retained_kin_care_native_api_proof.py").read_text(),probe)
    assert source.index("registration()")<source.index("resource.setrlimit")<source.index("import chronicler_agents")
    assert source.index('"installed_native_before_import"')<source.index("import chronicler_agents")
    assert ".tick(" not in source and "from_checkpoint_state" not in source
    assert P.HELPERS["wealth_floor_build_resources.py"]=="44f1e1d23598283f0fa7b0580477e026bd3d13d515ec84202dab108cfb2db5b2"
    for name,expected in P.HELPERS.items():assert P.digest((ROOT/"scripts"/name).read_bytes())==expected


def test_dormant_workflow_is_closed_and_future_copy_must_be_exact():
    text=(ROOT/P.TEMPLATE).read_text()
    assert P.ACTIVE_BRANCH in text and P.ACTIVE_PATH in text
    assert 'workflow_dispatch' not in text and 'python -P -s -B -X cpu_count=1' in text
    assert '-I ' not in text and '-E ' not in text and 'timeout-minutes: 15' in text
    active=ROOT/P.ACTIVE_PATH
    if active.exists():assert not active.is_symlink() and active.read_bytes()==(ROOT/P.TEMPLATE).read_bytes()


def test_owned_marker_binds_parent_birth_source_and_fixed_scope(tmp_path, monkeypatch):
    marker=tmp_path/"marker.json";environment=tmp_path/"environment";out=tmp_path/"probe.json";proc=tmp_path/"parent.stat"
    fields=["S","1","2","3"]+["0"]*15+["54321"]
    proc.write_text("4040 (fixture) "+" ".join(fields))
    value=dict(parent_pid=4040,parent_birth=54321,source_sha256=P.digest(P.SCRIPT.read_bytes()),activation="a"*64,
        environment=str(environment.resolve()),output=str(out.resolve()),wheel=P.WHEEL_SHA,native=P.NATIVE_SHA)
    marker.write_bytes(P.canonical(value));real_path=Path
    monkeypatch.setattr(P,"REVIEWED_ACTIVATION","a"*64)
    monkeypatch.setattr(P,"os",SimpleNamespace(getppid=lambda:4040))
    monkeypatch.setattr(P,"Path",lambda value:proc if str(value)=="/proc/4040/stat" else real_path(value))
    P.validate_marker(marker,environment,out)
    for key,bad in [("parent_pid",True),("parent_birth",54322),("activation","b"*64),("source_sha256","f"*64),
                    ("environment",str(tmp_path/"wrong")),("output",str(tmp_path/"wrong")),("wheel","f"*64),("native","f"*64)]:
        changed=dict(value,**{key:bad});marker.write_bytes(P.canonical(changed))
        with pytest.raises(P.Refused):P.validate_marker(marker,environment,out)


def test_network_deadline_is_scoped_outside_child_cleanup_and_restores_handler(monkeypatch):
    calls=[];clock=[0.0]
    class Signals:
        ITIMER_REAL=1;SIGALRM=14
        def getitimer(self,_):return (0.0,0.0)
        def getsignal(self,_):return "original"
        def signal(self,*args):calls.append(("handler",*args))
        def setitimer(self,*args):calls.append(("timer",*args))
    monkeypatch.setattr(P,"signal",Signals());monkeypatch.setattr(P,"time",SimpleNamespace(monotonic=lambda:clock[0]))
    with pytest.raises(P.Refused,match="network_wall_deadline"):
        with P.network_deadline(10):clock[0]=11
    assert calls[-2:]==[("timer",1,0),("handler",14,"original")]
    assert calls[1]==("timer",1,10.0)


def observation():
    return dict(kind="retained-kin-care-empty-api-observation-v1", native_sha256=P.NATIVE_SHA, compiled_extension=True,
        real_exported_classes=True, source_imports=[], runtime=runtime(),
        schemas={name:dict(version=row[0],fingerprint=row[1],schema_sha256=row[2]) for name,row in P.SCHEMAS.items()},
        api=P.exercise_empty_api(EmptyFixture()))


def test_parent_observation_verifier_does_not_accept_a_nonempty_or_unbound_scope():
    value=observation();assert P.validate_observation(value)==value
    for key,bad in [("instances",True),("World_instances",1),("ticks",1),("restores",1),("agents",1),("nonempty_care_qualified",True)]:
        changed=deepcopy(value);changed["api"][key]=bad
        with pytest.raises(P.Refused):P.validate_observation(changed)
    changed=deepcopy(value);changed["api"]["native_state_observations"][2]["sha256"]="f"*64
    with pytest.raises(P.Refused):P.validate_observation(changed)


@pytest.mark.parametrize("fault", [None,"source_after_seal","oversize_log"])
def test_fake_controller_complete_or_negative_publication_end_to_end(tmp_path,monkeypatch,fault):
    raw,_,_=fake_artifact(monkeypatch);commands=[];snapshots=[]
    # This fake controller uses a synthetic registered interpreter; no host version probe.
    monkeypatch.setattr(P,"platform",SimpleNamespace(python_version=lambda:"3.13.17"))
    monkeypatch.setattr(P,"REVIEWED_ACTIVATION","a"*64)
    real_os=P.os
    fake_os=SimpleNamespace(**vars(real_os));fake_os.environ=dict(RUNNER_TEMP=str(tmp_path),GITHUB_SHA="c"*40,GH_TOKEN="synthetic")
    fake_os.sched_getaffinity=lambda *_:{7};fake_os.sched_setaffinity=lambda *_:None;fake_os.getpid=lambda:4040
    monkeypatch.setattr(P,"os",fake_os)
    monkeypatch.setattr(P,"shutil",SimpleNamespace(disk_usage=lambda *_:SimpleNamespace(free=16*P.GIB),copyfileobj=P.shutil.copyfileobj))
    class Cancellation:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def check(self):pass
    class Lease(Cancellation):pass
    class DeploymentError(ValueError):pass
    class Supervisor:
        cleanup_complete=True
        def __init__(self,owned):self.root=owned
        def check(self,**kwargs):pass
        def command(self,label,command,env,cwd):
            commands.append((label,command,env))
            size=P.MIB+1 if fault=="oversize_log" and label=="install-locked-dependencies" else 12
            (self.root/"logs"/(label+".log")).write_bytes(b"x"*size)
            (self.root/"progress.jsonl").write_bytes(b'{"event":"child_cleanup","complete":true}\n')
            if label=="empty-native-api":
                out=Path(command[command.index("--out")+1]);P.atomic_json(out,observation())
            return b""
    def source_snapshot(*args):
        snapshots.append(1)
        if fault=="source_after_seal" and len(snapshots)==5:raise P.Refused("synthetic_late_source_change")
        return dict(source="c"*40,files={"synthetic":True})
    fakeC=SimpleNamespace(hosted_vm_precondition=lambda:dict(namespace_equal=None,namespace_equality_verified=False,scope="synthetic"),
        memory_admission=lambda:dict(available_bytes=6*P.GIB),legacy_helpers=lambda *_:SimpleNamespace(process_stat=lambda _:dict(birth=54321)),
        source_snapshot=source_snapshot,Cancellation=Cancellation,SubreaperLease=Lease,
        make_supervisor=lambda _,owned,*args:Supervisor(owned),direct_children=lambda:[],
        sha=lambda path:P.digest(Path(path).read_bytes()),DeploymentRefused=DeploymentError)
    monkeypatch.setattr(P,"load_helpers",lambda _:fakeC)
    class Transport:
        def __init__(self,*args):pass
        def metadata(self):return dict(synthetic=True)
        def download(self):return raw
    monkeypatch.setattr(P,"Transport",Transport)
    # Final helper checks read only these declared tiny fixture files.
    control=tmp_path/"control";(control/"scripts").mkdir(parents=True)
    helper=control/"scripts/helper.py";helper.write_bytes(b"fixture")
    monkeypatch.setattr(P,"HELPERS",{"helper.py":P.digest(b"fixture")})
    code=P.execute(control,"/selected/bin/python")
    out=tmp_path/"retained-kin-care-native-api-proof/metadata"
    result=P.strict_json((out/"result.json").read_bytes())
    assert len(commands)==5
    assert all("-I" not in command and "-E" not in command for _,command,_ in commands)
    assert all("GH_TOKEN" not in env for _,_,env in commands)
    probe_command=commands[-1][1];assert probe_command[1:7]==["-P","-s","-B","-X","cpu_count=1",str(P.SCRIPT)]
    assert "--frozen" in commands[2][1] and "--no-install-project" in commands[2][1]
    assert sum(p.stat().st_size for p in out.rglob("*") if p.is_file())<=P.MAX_OUTPUT
    if fault is None:
        assert code==0 and (out/"completion.json").exists() and result["complete"] is False
        assert result["deployment"]["namespace_equal"] is None
    else:
        assert code==1 and not (out/"completion.json").exists() and result["status"]=="INCOMPLETE"
        if fault=="oversize_log":assert (out/"omissions.json").exists()
