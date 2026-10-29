#!/usr/bin/env python3
"""Source-registered, zero-agent native API proof. No World, tick or restore.

Importing this file performs no host, credential, process or native observation.
Actual execution remains refused until a separate root-reviewed registration.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import importlib.machinery
import importlib.metadata
import io
import json
import math
import os
from pathlib import Path, PurePosixPath
import platform
import re
import resource
import shutil
import signal
import stat
import sys
import sysconfig
import time
import types
import urllib.error
import urllib.parse
import urllib.request
import zipfile

MIB, GIB = 1024**2, 1024**3
REPOSITORY = "YotsuBotfds/Chronicler"
PRODUCER_SOURCE = "23d4d24659cfda848d5bda034760ab9d1e8b57fe"
PRODUCER_BRANCH = "lead/retained-kin-care-ci-registration-review-20261029"
PRODUCER_RUN, PRODUCER_ATTEMPT, PRODUCER_JOB = 40908555947, 1, 123569924790
ARTIFACT_ID, ARTIFACT_BYTES = 12913615333, 3863158
ARTIFACT_NAME = "native-shard-build-40908555947-1"
ARTIFACT_SHA = "c9ee12a1521555d3a5cf0213ae43e45db5c2f288aa4bf4b474960a475b8b81e8"
ARTIFACT_EXPIRY = "2026-11-12T16:11:27Z"
WHEEL_SHA = "823cf2c55eefd2d7142b3e6985b39b8fc40e06c50a3dedb46d7d75594a20c96c"
NATIVE_SHA = "4028687923e9996fe4c52540ca7d2421fa1a175bd7167be19f2b005b12c9f54f"
BUILD_JSON_SHA = "126655b24447e805cc2d98ab7eade402c512f00950f8c873e96405ffeea52a41"
WHEEL_NAME = "chronicler_agents-0.1.0-cp313-cp313-manylinux_2_34_x86_64.whl"
WHEEL_BYTES, NATIVE_BYTES = 3927909, 13723592
NATIVE_MEMBER = "chronicler_agents/chronicler_agents.cpython-313-x86_64-linux-gnu.so"
PRODUCER_ROOT = "d22bc652060dba7f5b29e511ce813f1948f2880c4f02ad1917f69eab997b86fa"
REFERENCE_ROOT = "530e1f31f61f7c59b3b96f5663c5a4d691d8aaabccdd4c858f630fe419f014d7"
REFERENCE_ARTIFACT = 12904625572
REFERENCE_ZIP_SHA = "9030d854bb8fc4f678f6ba821c6f8e8c087903e35f1fa185fb1b6011ebb6cec0"
REFERENCE_MEMBER = "derived-metadata/probes/candidate-hybrid_s42-before.json"
SCHEMAS = {
    "AgentSimulator": (1, "dcf0c34097c88451", "0b792f3ec33ac68605caf7b6d66fa7462c919b52e6f489f0e3dd7fa42f9fba3b"),
    "EcologySimulator": (1, "4ab7f8c199b5e5f8", "bf7daf59c53773518770b90f5a5dee5b71e63d2a62d2af6c756922a07a503aff"),
    "PoliticsSimulator": (1, "b1a710f3450f5015", "48e27b42f817e0057ad5f15bf2c2e8d8cca072314a9ca666753f2c9341c47395"),
}
HELPERS = {
    "wealth_floor_native_build_bridge.py": "cb87ff673817fc655beb39cce88c39295cfa87dcd787e108e2cbf85026965373",
    "wealth_floor_build_resources.py": "44f1e1d23598283f0fa7b0580477e026bd3d13d515ec84202dab108cfb2db5b2",
    "wealth_floor_hosted_deployment.py": "d52b3c2b9269eb67ef154006fe06429645f79052d3dbcd4b28e6b1479f39bfb8",
    "wealth_floor_native_build_controller.py": "60bb77212757f632d8d80ed226f94e6ef9864134c4453b5affeb51dc059b9dd1",
    "default_output_identity_qualification.py": "e4ca3f0c3732e4b5536a88a6284ab44b173e2165fafb59586be02fbd1d015932",
}
REVIEWED_ACTIVATION = None
ACTIVE_BRANCH = "lead/cloud-retained-kin-care-native-api-proof-20261029"
ACTIVE_PATH = ".github/workflows/retained-kin-care-native-api-proof.yml"
TEMPLATE = "docs/workflows/retained-kin-care-native-api-proof.yml"
SCRIPT = Path(__file__).resolve()
WALL_SECONDS, TRANSFER_SECONDS, PROBE_SECONDS, PROBE_CPU_SECONDS = 600, 120, 110, 60
MAX_JSON, MAX_FILES, MAX_OUTPUT = 2*MIB, 32, 2*MIB
THREAD_KEYS = ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "BLIS_NUM_THREADS",
               "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS", "GOTO_NUM_THREADS", "RAYON_NUM_THREADS", "CARGO_BUILD_JOBS")
CAPS = {key: "1" for key in THREAD_KEYS}
CAPS.update(PYTHONHASHSEED="0", PYTHON_CPU_COUNT="1", PYTHONDONTWRITEBYTECODE="1", PYTHONNOUSERSITE="1",
            OPENBLAS_THREAD_TIMEOUT="16", PYTHONUNBUFFERED="1", UV_PYTHON_DOWNLOADS="never", UV_NO_BUILD="1")
SCOPE = "Empty native API/schema/transient lifecycle only; no patient/donor efficacy, World, physics, restore, RNG identity or performance qualification."


class Refused(ValueError):
    pass


def require(condition, code):
    if not condition:
        raise Refused(code)


def canonical(value):
    return (json.dumps(value, sort_keys=True, allow_nan=False, separators=(",", ":"))+"\n").encode()


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def strict_json(raw):
    require(type(raw) is bytes and len(raw) <= MAX_JSON, "json_size")
    def pairs(rows):
        value = {}
        for key, item in rows:
            require(key not in value, "json_duplicate_key")
            value[key] = item
        return value
    def finite(token):
        raise Refused("json_nonfinite")
    def number(token):
        value = float(token)
        require(math.isfinite(value), "json_nonfinite")
        return value
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=finite, parse_float=number)


def timestamp(value):
    require(type(value) is str and re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", value), "expiry_format")
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        raise Refused("expiry_value") from None


def expiry_check(now=None):
    now = datetime.now(timezone.utc) if now is None else now
    require(now.tzinfo is not None and now < timestamp(ARTIFACT_EXPIRY), "input_expired")


def registration():
    require(type(REVIEWED_ACTIVATION) is str and re.fullmatch(r"[0-9a-f]{64}", REVIEWED_ACTIVATION), "activation_pending")
    require(type(PRODUCER_JOB) is int and PRODUCER_JOB > 0 and type(ARTIFACT_ID) is int and ARTIFACT_ID > 0, "producer_pending")
    expiry_check()
    return dict(root=REVIEWED_ACTIVATION, producer_root=PRODUCER_ROOT, reference_root=REFERENCE_ROOT)


def validate_metadata(rows, now=None):
    require(type(rows) is dict and set(rows) == {"run", "job", "artifact"}, "metadata_keys")
    run, job, artifact = (rows[key] for key in ("run", "job", "artifact"))
    require(all(type(row) is dict for row in (run, job, artifact)), "metadata_types")
    require(type(run.get("id")) is int and run["id"] == PRODUCER_RUN and type(run.get("run_attempt")) is int
            and run["run_attempt"] == PRODUCER_ATTEMPT and run.get("head_sha") == PRODUCER_SOURCE
            and run.get("head_branch") == PRODUCER_BRANCH and run.get("path") == ".github/workflows/tests.yml"
            and run.get("status") == "completed" and run.get("conclusion") == "success", "producer_run")
    require(type(job.get("id")) is int and job["id"] == PRODUCER_JOB and type(job.get("run_id")) is int
            and job["run_id"] == PRODUCER_RUN and type(job.get("run_attempt")) is int and job["run_attempt"] == PRODUCER_ATTEMPT
            and job.get("head_sha") == PRODUCER_SOURCE and job.get("head_branch") == PRODUCER_BRANCH and job.get("name") == "Build one current-source native wheel"
            and job.get("status") == "completed" and job.get("conclusion") == "success", "producer_job")
    require(type(artifact.get("id")) is int and artifact["id"] == ARTIFACT_ID and artifact.get("name") == ARTIFACT_NAME
            and type(artifact.get("size_in_bytes")) is int and artifact["size_in_bytes"] == ARTIFACT_BYTES
            and artifact.get("digest") == "sha256:"+ARTIFACT_SHA and artifact.get("expired") is False
            and artifact.get("expires_at") == ARTIFACT_EXPIRY, "producer_artifact")
    workflow = artifact.get("workflow_run")
    require(type(workflow) is dict and type(workflow.get("id")) is int and workflow["id"] == PRODUCER_RUN
            and workflow.get("head_sha") == PRODUCER_SOURCE and workflow.get("head_branch") == PRODUCER_BRANCH,
            "artifact_workflow")
    expiry_check(now)
    return rows


def child_environment(task, selected_python, inherited):
    # Preserve the session's proxy/CA trust without copying Python/loader/token overrides.
    keys = ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY", "http_proxy", "https_proxy", "all_proxy", "no_proxy",
            "SSL_CERT_FILE", "SSL_CERT_DIR", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE", "PIP_CERT", "UV_NATIVE_TLS")
    env = {key: inherited[key] for key in keys if key in inherited}
    env.update(CAPS, PATH=str(Path(selected_python).parent)+":/usr/bin:/bin", HOME=str(task/"home"),
               TMPDIR=str(task/"tmp"), UV_CACHE_DIR=str(task/"cache"), UV_PROJECT_ENVIRONMENT=str(task/"environment"))
    return env


def runtime_contract(observed):
    require(type(observed) is dict and observed.get("python") == "3.13.17"
            and observed.get("safe_path") is True and type(observed.get("no_user_site")) is int and observed["no_user_site"] == 1
            and observed.get("dont_write_bytecode") is True and type(observed.get("hash_randomization")) is int and observed["hash_randomization"] == 0
            and type(observed.get("cpu_count")) is int and observed["cpu_count"] == 1
            and type(observed.get("process_cpu_count")) is int and observed["process_cpu_count"] == 1
            and type(observed.get("affinity")) is list and len(observed["affinity"]) == 1
            and type(observed["affinity"][0]) is int
            and observed.get("thread_env") == {key: "1" for key in THREAD_KEYS}, "runtime_contract")
    return observed


def schema_summaries(package, native):
    result = {}
    for name, expected in SCHEMAS.items():
        cls = getattr(package, name, None)
        require(isinstance(cls, type) and cls is getattr(native, name, None), "compiled_class_identity")
        value = cls.checkpoint_schema()
        require(type(value) is tuple and len(value) == 3, "schema_tuple")
        version, fingerprint, descriptor = value
        require(type(version) is int and type(fingerprint) is str and re.fullmatch(r"[0-9a-f]{16}", fingerprint)
                and type(descriptor) is str and 0 < len(descriptor.encode("utf-8")) <= 64*1024, "schema_types")
        summary = (version, fingerprint, digest(descriptor.encode("utf-8")))
        require(summary == expected, "schema_reference_mismatch")
        result[name] = dict(version=version, fingerprint=fingerprint, schema_sha256=summary[2])
    return result


def exercise_empty_api(sim):
    require(sim.get_snapshot().num_rows == 0, "nonempty_fixture")
    baseline = sim.checkpoint_state()
    require(type(baseline) is bytes and 0 < len(baseline) <= MIB, "native_state_bound")
    observations = []
    def unchanged(label):
        current = sim.checkpoint_state()
        require(type(current) is bytes and current == baseline, "persistent_state_changed")
        observations.append(dict(label=label, bytes=len(current), sha256=digest(current), equals_baseline=True))
    require(sim.prepare_health_work([], [], [], .5, .2) == [], "legacy_five_args")
    unchanged("legacy_prepared")
    try:
        sim.prepare_health_work([], [], [], .5, .2, care_policy="kin")
    except ValueError:
        invalid = True
    else:
        raise Refused("invalid_policy_not_rejected")
    unchanged("invalid_policy_rejected")
    zero = ([], [], [(0, 0.0, 0.0, 0)])
    require(sim.finish_health_work(0, 0.0) == zero, "empty_prepared_marker_lost")
    unchanged("legacy_finished")
    require(sim.finish_health_work(0, 0.0) == ([], [], []), "legacy_consumed_twice")
    require(sim.prepare_health_work([], [], [], .5, .2, care_policy="retained_kin") == [], "retained_keyword")
    unchanged("retained_prepared")
    require(sim.finish_health_work(0, 0.0) == zero, "retained_zero_cost_row")
    unchanged("retained_finished")
    require(sim.finish_health_work(0, 0.0) == ([], [], []), "retained_consumed_twice")
    unchanged("retained_finished_again")
    return dict(instances=1, agents=0, World_instances=0, ticks=0, restores=0, invalid_policy_rejected=invalid,
                legacy_five_positional=True, new_keyword=True, empty_prepared_marker_retained=True,
                zero_cost_region_row=[0, 0.0, 0.0, 0], native_state_observations=observations,
                nonempty_care_qualified=False, scope=SCOPE)


def validate_observation(value):
    require(type(value) is dict and value.get("kind") == "retained-kin-care-empty-api-observation-v1"
            and value.get("native_sha256") == NATIVE_SHA and value.get("compiled_extension") is True
            and value.get("real_exported_classes") is True and value.get("source_imports") == [], "probe_identity")
    runtime_contract(value.get("runtime"))
    expected = {name: dict(version=row[0], fingerprint=row[1], schema_sha256=row[2]) for name,row in SCHEMAS.items()}
    require(value.get("schemas") == expected, "probe_schemas")
    api = value.get("api")
    require(type(api) is dict and type(api.get("instances")) is int and api["instances"] == 1
            and all(type(api.get(key)) is int and api[key] == 0 for key in ("agents", "World_instances", "ticks", "restores"))
            and all(api.get(key) is True for key in ("invalid_policy_rejected", "legacy_five_positional", "new_keyword", "empty_prepared_marker_retained"))
            and api.get("nonempty_care_qualified") is False, "probe_empty_scope")
    rows = api.get("native_state_observations")
    require(type(rows) is list and len(rows) == 6 and [row.get("label") for row in rows] ==
            ["legacy_prepared", "invalid_policy_rejected", "legacy_finished", "retained_prepared", "retained_finished", "retained_finished_again"], "probe_state_rows")
    require(all(type(row.get("bytes")) is int and 0 < row["bytes"] <= MIB and row.get("equals_baseline") is True
                and type(row.get("sha256")) is str and re.fullmatch(r"[0-9a-f]{64}", row["sha256"]) for row in rows)
            and len({(row["bytes"],row["sha256"]) for row in rows}) == 1, "probe_persistent_bytes")
    return value


def probe(environment, out, marker):
    registration()
    validate_marker(marker, environment, out)
    # No -I/-E: PYTHONHASHSEED=0 must be effective at process startup.
    resource.setrlimit(resource.RLIMIT_AS, (2*GIB, 2*GIB))
    resource.setrlimit(resource.RLIMIT_CPU, (PROBE_CPU_SECONDS, PROBE_CPU_SECONDS))
    signal.alarm(PROBE_SECONDS)
    started, cpu = time.monotonic(), time.process_time()
    observed = runtime_contract(dict(python=platform.python_version(), safe_path=sys.flags.safe_path,
        no_user_site=sys.flags.no_user_site, dont_write_bytecode=sys.dont_write_bytecode,
        hash_randomization=sys.flags.hash_randomization, cpu_count=os.cpu_count(), process_cpu_count=os.process_cpu_count(),
        affinity=sorted(os.sched_getaffinity(0)), thread_env={key: os.environ.get(key) for key in THREAD_KEYS}))
    prefix = Path(environment).resolve()
    require(Path(sys.prefix).resolve() == prefix, "probe_environment")
    native_path = Path(sysconfig.get_paths()["platlib"])/NATIVE_MEMBER
    require(native_path.is_relative_to(prefix) and native_path.is_file() and not native_path.is_symlink()
            and native_path.stat().st_size == NATIVE_BYTES and digest(native_path.read_bytes()) == NATIVE_SHA, "installed_native_before_import")
    import chronicler_agents as package
    import chronicler_agents.chronicler_agents as native
    require(isinstance(native.__loader__, importlib.machinery.ExtensionFileLoader)
            and Path(native.__file__).resolve() == native_path.resolve(), "compiled_extension_origin")
    before = schema_summaries(package, native)
    outcome = exercise_empty_api(package.AgentSimulator(num_regions=1, seed=42))
    require(schema_summaries(package, native) == before, "schema_changed")
    require(not any(name == "chronicler" or name.startswith("chronicler.") for name in sys.modules), "producer_source_import")
    require(digest(native_path.read_bytes()) == NATIVE_SHA, "installed_native_after_probe")
    report = dict(kind="retained-kin-care-empty-api-observation-v1", native_sha256=NATIVE_SHA,
                  compiled_extension=True, real_exported_classes=True,
                  runtime=observed, schemas=before, api=outcome,
                  packages={d.metadata["Name"]: d.version for d in importlib.metadata.distributions() if d.metadata["Name"]},
                  probe_wall_before_output_seconds=time.monotonic()-started,
                  probe_self_cpu_before_output_seconds=time.process_time()-cpu, source_imports=[])
    validate_observation(report)
    atomic_json(out, report)
    require(time.monotonic()-started < PROBE_SECONDS, "probe_final_deadline")
    signal.alarm(0)


def validate_marker(marker, environment, out):
    path = Path(marker)
    require(path.is_file() and not path.is_symlink() and path.stat().st_nlink == 1, "owned_marker_path")
    value = strict_json(path.read_bytes())
    require(type(value) is dict and set(value) == {"parent_pid", "parent_birth", "source_sha256", "activation", "environment", "output", "wheel", "native"}, "owned_marker_shape")
    require(type(value["parent_pid"]) is int and value["parent_pid"] == os.getppid()
            and type(value["parent_birth"]) is int and value["parent_birth"] > 0, "owned_marker_parent")
    with Path(f"/proc/{os.getppid()}/stat").open("rb") as stream:
        raw = stream.read(4097)
    require(len(raw) <= 4096, "owned_parent_stat_bound")
    fields = raw.decode("ascii").rsplit(")", 1)[1].split()
    require(int(fields[19]) == value["parent_birth"] and value["source_sha256"] == digest(SCRIPT.read_bytes())
            and value["activation"] == REVIEWED_ACTIVATION and value["wheel"] == WHEEL_SHA and value["native"] == NATIVE_SHA
            and value["environment"] == str(Path(environment).resolve()) and value["output"] == str(Path(out).resolve()), "owned_marker_binding")


def zip_entries(archive, *, members, expanded, member_bytes):
    infos = archive.infolist()
    require(0 < len(infos) <= members and len({i.filename for i in infos}) == len(infos), "zip_member_count")
    total = 0
    for info in infos:
        path = PurePosixPath(info.filename)
        require(path.as_posix() == info.filename and not path.is_absolute() and ".." not in path.parts
                and "\\" not in info.filename and not info.is_dir(), "zip_path")
        mode = info.external_attr >> 16
        require(stat.S_IFMT(mode) in (0, stat.S_IFREG) and not (info.flag_bits & 1)
                and info.compress_type in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED), "zip_mode")
        require(0 <= info.file_size <= member_bytes, "zip_member_size")
        total += info.file_size
    require(total <= expanded, "zip_expanded")
    return infos


def inspect_artifact(raw):
    require(type(raw) is bytes and len(raw) == ARTIFACT_BYTES and len(raw) <= 8*MIB and digest(raw) == ARTIFACT_SHA,
            "artifact_whole_hash")
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        infos = zip_entries(archive, members=32, expanded=64*MIB, member_bytes=16*MIB)
        names = {i.filename for i in infos}
        require("ci-native-wheel/build.json" in names and len(names) == 2, "artifact_closure")
        build_raw = archive.read("ci-native-wheel/build.json")
        require(digest(build_raw) == BUILD_JSON_SHA, "build_json_hash")
        build = strict_json(build_raw)
        require(build.get("kind") == "native-shard-current-build-v1" and build.get("producer_job_key") == "python-native-build", "build_kind")
        identity = build["identity"]
        require(identity.get("source_commit") == PRODUCER_SOURCE and type(identity.get("run_id")) is int
                and identity["run_id"] == PRODUCER_RUN and type(identity.get("attempt")) is int
                and identity["attempt"] == PRODUCER_ATTEMPT and identity.get("classes") == list(SCHEMAS), "build_identity")
        receipt = identity["wheel"]
        wheel = receipt["wheel"]
        name = wheel["filename"]
        require(type(name) is str and name == WHEEL_NAME, "wheel_filename")
        archive_name = "chronicler-agents/target/wheels/"+name
        require(names == {"ci-native-wheel/build.json", archive_name}, "artifact_exact_members")
        data = archive.read(archive_name)
        require(len(data) == WHEEL_BYTES and 0 < len(data) <= 16*MIB and digest(data) == WHEEL_SHA and wheel.get("sha256") == WHEEL_SHA
                and wheel.get("bytes") == len(data) and wheel.get("native_member") == NATIVE_MEMBER
                and receipt.get("source_commit") == PRODUCER_SOURCE and receipt.get("schema_version") == 1, "wheel_hash")
        with zipfile.ZipFile(io.BytesIO(data)) as inner:
            entries = zip_entries(inner, members=64, expanded=64*MIB, member_bytes=32*MIB)
            require(NATIVE_MEMBER in {i.filename for i in entries}, "wheel_native_member")
            for entry in entries:
                body = inner.read(entry)  # CRC for every bounded wheel member, before install.
                if entry.filename == NATIVE_MEMBER:
                    installed = receipt["installed_native"]
                    require(len(body) == NATIVE_BYTES and digest(body) == NATIVE_SHA and installed.get("sha256") == NATIVE_SHA
                            and installed.get("wheel_member_sha256") == NATIVE_SHA and installed.get("bytes") == len(body), "wheel_native_hash")
    return name, data, build


@contextmanager
def network_deadline(deadline):
    # Used only while no owned child is active; never interrupts session cleanup.
    remaining = deadline-time.monotonic()
    require(remaining > 0 and signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0), "network_alarm_unavailable")
    previous = signal.getsignal(signal.SIGALRM)
    def expired(_number, _frame):
        raise Refused("network_wall_deadline")
    signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, remaining)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)
    require(time.monotonic() < deadline, "network_wall_deadline")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class Transport:
    def __init__(self, token, check, deadline):
        require(type(token) is str and token and "\n" not in token and "\r" not in token, "credential_unavailable")
        self.token, self.check, self.deadline = token, check, deadline
        self.opener = urllib.request.build_opener(NoRedirect())

    def api(self, endpoint):
        allowed = {f"actions/runs/{PRODUCER_RUN}", f"actions/jobs/{PRODUCER_JOB}", f"actions/artifacts/{ARTIFACT_ID}"}
        require(endpoint in allowed, "metadata_endpoint")
        self.check()
        request = urllib.request.Request(f"https://api.github.com/repos/{REPOSITORY}/{endpoint}",
            headers={"Authorization": "Bearer "+self.token, "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"})
        with network_deadline(min(self.deadline, time.monotonic()+30)):
            with self.opener.open(request, timeout=30) as response:
                require(response.status == 200, "metadata_status")
                raw = response.read(MAX_JSON+1)
        self.check()
        return strict_json(raw)

    def metadata(self):
        rows = dict(run=self.api(f"actions/runs/{PRODUCER_RUN}"), job=self.api(f"actions/jobs/{PRODUCER_JOB}"),
                    artifact=self.api(f"actions/artifacts/{ARTIFACT_ID}"))
        return validate_metadata(rows)

    def download(self):
        self.check()
        with network_deadline(min(self.deadline, time.monotonic()+TRANSFER_SECONDS)):
            return self._download()

    def _download(self):
        self.check()
        request = urllib.request.Request(f"https://api.github.com/repos/{REPOSITORY}/actions/artifacts/{ARTIFACT_ID}/zip",
            headers={"Authorization": "Bearer "+self.token, "Accept": "application/vnd.github+json"})
        try:
            response = self.opener.open(request, timeout=30)
        except urllib.error.HTTPError as exc:
            require(exc.code == 302, "artifact_redirect_status")
            location = exc.headers.get("Location", "")
            exc.close()
        else:
            response.close()
            raise Refused("artifact_redirect_missing")
        target = urllib.parse.urlsplit(location)
        require(target.scheme == "https" and target.username is None and target.password is None and target.port in (None, 443)
                and target.hostname is not None and (target.hostname.endswith(".blob.core.windows.net")
                or target.hostname.endswith(".actions.githubusercontent.com")), "artifact_redirect_host")
        started, chunks, total = time.monotonic(), [], 0
        # No Authorization header is forwarded to storage; NoRedirect rejects a second hop.
        with self.opener.open(urllib.request.Request(location), timeout=30) as response:
            require(response.status == 200, "artifact_storage_status")
            while True:
                self.check()
                require(time.monotonic()-started < TRANSFER_SECONDS, "artifact_transfer_deadline")
                block = response.read(MIB)
                if not block:
                    break
                total += len(block)
                require(total <= ARTIFACT_BYTES and total <= 8*MIB, "artifact_transfer_size")
                chunks.append(block)
        raw = b"".join(chunks)
        require(len(raw) == ARTIFACT_BYTES and digest(raw) == ARTIFACT_SHA, "artifact_transfer_hash")
        self.check()
        return raw


def atomic_json(path, value):
    raw = canonical(value)
    require(len(raw) <= MAX_JSON, "output_json_size")
    path = Path(path)
    temporary = path.with_name(path.name+".tmp")
    try:
        with temporary.open("xb") as stream:
            stream.write(raw); stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def stage_owned(owned, output, *, require_complete):
    """C60 intake stays8MiB/log; published logs are <=1MiB and complete-or-negative.

    Excess originals remain VM-local; omissions are explicit, never a complete proof.
    """
    omitted = []
    candidates = [owned/"progress.jsonl", *sorted((owned/"logs").glob("*.log"))]
    total = sum(p.stat().st_size for p in output.rglob("*") if p.is_file())
    reserve = 64*1024
    for path in candidates:
        if not path.exists():
            continue
        require(path.is_file() and not path.is_symlink() and path.stat().st_nlink == 1, "owned_evidence_type")
        relative = path.relative_to(owned)
        size = path.stat().st_size
        target = output/relative
        if target.exists():
            require(target.read_bytes() == path.read_bytes(), "owned_copy_changed")
            continue
        require(size <= 8*MIB, "owned_evidence_intake_bound")
        if (relative.parts[0] == "logs" and size > MIB) or total+size > MAX_OUTPUT-reserve:
            with path.open("rb") as stream:
                sha = hashlib.file_digest(stream, "sha256").hexdigest()
            omitted.append(dict(path=relative.as_posix(), bytes=size, sha256=sha, reason="published_capacity"))
            continue
        target.parent.mkdir(exist_ok=True)
        with path.open("rb") as src, target.open("xb") as dst:
            shutil.copyfileobj(src, dst, MIB); dst.flush(); os.fsync(dst.fileno())
        total += size
    if omitted:
        atomic_json(output/"omissions.json", dict(complete=False, omitted=omitted, original_location="Reader VM only; not cross-examination preservation", scope="Published capacity refusal"))
    require(not omitted or not require_complete, "complete_logs_do_not_fit")
    return omitted


def bound_negative(output):
    # Keep a finite negative artifact even after aggregate output refusal.
    total, kept, omitted = 0, 0, []
    for path in sorted(output.rglob("*")):
        if not path.is_file() or path.name in ("result.json", "completion.json", "negative-omissions.json"):
            continue
        size = path.stat().st_size
        require(not path.is_symlink() and size <= MAX_JSON, "negative_metadata_file")
        if total+size > MAX_OUTPUT-64*1024 or kept >= MAX_FILES-3:
            with path.open("rb") as stream:
                sha = hashlib.file_digest(stream, "sha256").hexdigest()
            omitted.append(dict(path=path.relative_to(output).as_posix(), bytes=size, sha256=sha, reason="negative_output_capacity"))
            destination = output.parent/"unpublished-negative"/path.relative_to(output)
            destination.parent.mkdir(parents=True, exist_ok=True)
            os.replace(path, destination)
        else:
            total += size; kept += 1
    if omitted:
        atomic_json(output/"negative-omissions.json", dict(complete=False, omitted=omitted, original_location="VM only; not published"))


def invalidate(output, code):
    (output/"completion.json").unlink(missing_ok=True)
    atomic_json(output/"result.json", dict(kind="retained-kin-care-api-result-v1", complete=False,
        status="INCOMPLETE", safe_failure=code, scope=SCOPE))


def publish(output, report, check, clocks):
    try:
        check()
        files, total = {}, 0
        for path in sorted(output.rglob("*")):
            require(not path.is_symlink(), "output_symlink")
            if path.is_dir():
                continue
            require(path.is_file() and stat.S_ISREG(path.stat().st_mode) and path.stat().st_nlink == 1, "output_file")
            if path.name in ("result.json", "completion.json"):
                continue
            raw = path.read_bytes(); total += len(raw)
            require(len(files) < MAX_FILES and total <= MAX_OUTPUT, "output_inventory_bound")
            files[path.relative_to(output).as_posix()] = dict(bytes=len(raw), sha256=digest(raw))
        desired = dict(report, complete=False, status="PROVISIONAL_UNTIL_COMPLETION", files=files,
                       measured_after_payload_hashing_before_result=clocks(), scope=SCOPE)
        atomic_json(output/"result.json", desired)
        check()
        result = (output/"result.json").read_bytes()
        seal = dict(kind="retained-kin-care-api-completion-v1", complete=True, result_sha256=digest(result),
                    result_bytes=len(result), measured_before_seal=clocks(),
                    scope="Requires completed successful proof job, exact artifact closure and postcommit check; "+SCOPE)
        require(total+len(result)+len(canonical(seal)) <= MAX_OUTPUT and len(files)+2 <= MAX_FILES, "final_output_bound")
        atomic_json(output/"completion.json", seal)
        check()
        return seal
    except BaseException:
        invalidate(output, "publication_incomplete")
        raise


def load_helpers(control):
    raw = {}
    for filename, expected in HELPERS.items():
        path = control/"scripts"/filename
        require(path.is_file() and not path.is_symlink(), "helper_path")
        raw[filename] = path.read_bytes()
        require(digest(raw[filename]) == expected, "helper_source")
    for filename in list(HELPERS)[:-1]:
        name = filename[:-3]
        module = types.ModuleType(name); module.__file__ = str(control/"scripts"/filename)
        sys.modules[name] = module
        exec(compile(raw[filename], module.__file__, "exec"), module.__dict__)
    return sys.modules["wealth_floor_native_build_controller"]


def execute(control, selected_python):
    registration()  # Before token, filesystem, host, process, allocation or network.
    started, cpu = time.monotonic(), time.process_time()
    child_start = resource.getrusage(resource.RUSAGE_CHILDREN)
    deadline = started+WALL_SECONDS
    control = Path(control).resolve()
    task = Path(os.environ["RUNNER_TEMP"])/"retained-kin-care-native-api-proof"
    require(not task.exists(), "output_already_exists")
    task.mkdir(mode=0o700); output = task/"metadata"; output.mkdir(mode=0o700)
    for name in ("logs",):
        (output/name).mkdir()
    invalidate(output, "not_complete")
    owned = task/"owned"; (owned/"logs").mkdir(parents=True)
    C = supervisor = None
    report = dict(kind="retained-kin-care-api-result-v1", producer_source=PRODUCER_SOURCE,
                  producer_root=PRODUCER_ROOT, reference_root=REFERENCE_ROOT, activation_root=REVIEWED_ACTIVATION)
    try:
        C = load_helpers(control)
        report["deployment"] = C.hosted_vm_precondition()
        observed = C.memory_admission()
        require(shutil.disk_usage(task).free >= 12*GIB and observed["available_bytes"] >= 2*GIB, "initial_resources")
        report["initial_memory"] = observed
        require(platform.python_version() == "3.13.17", "controller_python")
        os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
        legacy = C.legacy_helpers(control)
        source = os.environ["GITHUB_SHA"]
        env = child_environment(task, selected_python, os.environ)
        for name in ("home", "tmp", "cache"):
            (task/name).mkdir()
        with C.Cancellation() as cancellation:
            with C.SubreaperLease() as lease:
                supervisor = C.make_supervisor(legacy, owned, deadline, lease, cancellation)
                before = C.source_snapshot(legacy, control, source, deadline)
                atomic_json(output/"source-before.json", before)
                def check():
                    supervisor.check(final=True)
                    require(not C.direct_children(), "network_with_children")
                    require(time.monotonic() < deadline-25, "controller_cleanup_reserve")
                    expiry_check()
                client = Transport(os.environ.get("GH_TOKEN"), check, deadline-25)
                atomic_json(output/"origin-before.json", client.metadata())
                wheel_name, wheel_data, build = inspect_artifact(client.download())
                atomic_json(output/"origin-after-transfer.json", client.metadata())
                atomic_json(output/"producer-build.json", build)
                wheel = task/wheel_name
                with wheel.open("xb") as stream:
                    stream.write(wheel_data); stream.flush(); os.fsync(stream.fileno())
                del wheel_data
                tool = task/"tooling"
                flags = ["-P", "-s", "-B", "-X", "cpu_count=1"]
                supervisor.command("create-tooling", [selected_python, *flags, "-m", "venv", str(tool)], env, control)
                supervisor.command("install-uv", [str(tool/"bin/python"), *flags, "-m", "pip", "install", "--only-binary=:all:", "uv==0.13.6"], env, control)
                uv = str(tool/"bin/uv")
                supervisor.command("install-locked-dependencies", [uv, "sync", "--frozen", "--no-install-project", "--python", selected_python], env, control)
                python = str(task/"environment/bin/python")
                supervisor.command("install-verified-wheel", [uv, "pip", "install", "--python", python, "--no-deps", str(wheel)], env, control)
                marker = task/"owned-probe.json"
                owner = legacy.process_stat(os.getpid())
                require(owner is not None, "owned_parent_identity")
                atomic_json(marker, dict(parent_pid=os.getpid(), parent_birth=owner["birth"], source_sha256=digest(SCRIPT.read_bytes()),
                    activation=REVIEWED_ACTIVATION, environment=str((task/"environment").resolve()), output=str((output/"probe.json").resolve()), wheel=WHEEL_SHA, native=NATIVE_SHA))
                supervisor.command("empty-native-api", [python, *flags, str(SCRIPT), "--probe", "--environment", str(task/"environment"), "--out", str(output/"probe.json"), "--marker", str(marker)], env, task)
                observation = validate_observation(strict_json((output/"probe.json").read_bytes()))
                atomic_json(output/"origin-final.json", client.metadata())
                after = C.source_snapshot(legacy, control, source, deadline)
                require(before == after, "source_changed")
                atomic_json(output/"source-after.json", after)
                require(C.sha(wheel) == WHEEL_SHA and supervisor.cleanup_complete, "final_wheel_or_cleanup")
            require(not C.direct_children(), "late_children")
            cancellation.check()
            # Retain complete deployment observations, never only their truthiness.
            report.update(source=source, input_artifact=ARTIFACT_ID, native_sha256=NATIVE_SHA, wheel_sha256=WHEEL_SHA,
                          api_observation_sha256=C.sha(output/"probe.json"), cleanup_complete=True)
            def final_check():
                cancellation.check(); expiry_check()
                require(time.monotonic() < deadline, "final_deadline")
                require(not C.direct_children(), "late_children")
                require(shutil.disk_usage(task).free >= 3*GIB and C.memory_admission()["available_bytes"] >= GIB, "final_resources")
                require(C.source_snapshot(legacy, control, source, deadline) == before, "final_source_changed")
                for name, expected in HELPERS.items():
                    require(C.sha(control/"scripts"/name) == expected, "final_helper_changed")
            def clocks():
                children = resource.getrusage(resource.RUSAGE_CHILDREN)
                return dict(controller_wall_seconds=time.monotonic()-started,
                            controller_self_cpu_seconds=time.process_time()-cpu,
                            waited_children_cpu_seconds=children.ru_utime+children.ru_stime-child_start.ru_utime-child_start.ru_stime,
                            clock_scope="self and waited children only; sampled before completion serialization; postcommit deadline/source/expiry checks mandatory")
            stage_owned(owned, output, require_complete=True)
            publish(output, report, final_check, clocks)
            final_check()
        return 0
    except BaseException as exc:
        code = "deployment_"+exc.code if C and isinstance(exc, C.DeploymentRefused) else type(exc).__name__
        # Fixed class name only; no token, URL, arbitrary exception text or traceback.
        invalidate(output, code)
        try:
            stage_owned(owned, output, require_complete=False)
            bound_negative(output)
        except BaseException:
            # Primary negative receipt remains mandatory even if evidence retention refuses.
            invalidate(output, "failure_retention_incomplete")
        return 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--probe", action="store_true")
    parser.add_argument("--control", type=Path, default=SCRIPT.parent.parent)
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--environment", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--marker", type=Path)
    args = parser.parse_args(argv)
    require(args.execute != args.probe, "one_mode_required")
    if args.probe:
        require(args.environment is not None and args.out is not None and args.marker is not None, "probe_arguments")
        probe(args.environment, args.out, args.marker)
        return 0
    return execute(args.control, args.python)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Refused:
        print('{"complete":false,"status":"REFUSED"}')
        raise SystemExit(1)
