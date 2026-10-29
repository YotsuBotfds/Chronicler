"""Pure byte/HTTP contracts: no network, install, native import or study world."""
from copy import deepcopy
import importlib.util
import hashlib
import io
import json
from pathlib import Path
import stat
import urllib.request
import zipfile

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def helper(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location("research_wheel_test", ROOT / "scripts/fetch_research_natural_wheel.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def zipped(rows):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, value, mode in rows:
            info = zipfile.ZipInfo(name)
            info.external_attr = mode << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, value)
    return stream.getvalue()


def fixture_archive(h, *, wheel_rows=None, manifest_change=None):
    expected = h.selected()
    a = expected["artifact"]
    native = b"opaque synthetic compiled bytes; never loaded"
    wheel_rows = wheel_rows or [(a["native_member"], native, stat.S_IFREG | 0o755),
        ("chronicler_agents/__init__.py", b"raise AssertionError('must never execute')", stat.S_IFREG | 0o644)]
    wheel = zipped(wheel_rows)
    a.update(wheel_bytes=len(wheel), wheel_sha256=h.record(wheel)["sha256"], native_bytes=len(native), native_sha256=h.record(native)["sha256"])
    manifest = dict(schema_version=1, kind="chronicler-cloud-full-gate-build", qualified=True,
        control_sha=a["control_sha"], github_run_id=str(a["run_id"]), github_run_attempt="1",
        crate_tree=a["crate_tree"], pyproject_sha256=a["pyproject_sha256"], lock_sha256=a["lock_sha256"],
        python_version=a["python_version"], native=dict(schemas=deepcopy(expected["schemas"]), sha256=a["native_sha256"]),
        wheel=dict(bytes=a["wheel_bytes"], filename=Path(a["wheel_path"]).name, native_member=a["native_member"],
            native_sha256=a["native_sha256"], sha256=a["wheel_sha256"]))
    if manifest_change:
        manifest_change(manifest)
    manifest_raw = (json.dumps(manifest, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()
    a.update(manifest_bytes=len(manifest_raw), manifest_sha256=h.record(manifest_raw)["sha256"])
    raw = zipped([("build-manifest.json", manifest_raw, stat.S_IFREG | 0o644), (a["wheel_path"], wheel, stat.S_IFREG | 0o644)])
    a.update(bytes=len(raw), sha256=h.record(raw)["sha256"])
    return raw, expected


def test_verified_archive_does_not_execute_python_or_native_members(helper):
    raw, expected = fixture_archive(helper)
    manifest, wheel = helper.verify_archive(raw, expected)
    assert manifest and wheel


@pytest.mark.parametrize("field", ["id", "name", "size_in_bytes", "digest", "expired", "run", "head"])
def test_official_metadata_binding_is_required_before_download(helper, field):
    a = helper.selected()["artifact"]
    metadata = dict(id=a["id"], name=a["name"], size_in_bytes=a["bytes"], digest="sha256:" + a["sha256"],
        expired=False, workflow_run=dict(id=a["run_id"], head_sha=a["control_sha"]))
    helper.metadata_contract(metadata, a)
    if field == "run":
        metadata["workflow_run"]["id"] += 1
    elif field == "head":
        metadata["workflow_run"]["head_sha"] = "different"
    elif field == "expired":
        metadata[field] = 0  # Numeric alias for false is not accepted.
    else:
        metadata[field] = "different"
    with pytest.raises(helper.C.ContractError):
        helper.metadata_contract(metadata, a)


@pytest.mark.parametrize("fault", ["parent", "absolute", "symlink", "duplicate", "extra_native", "native_bytes"])
def test_nested_wheel_rejects_unsafe_members_even_when_outer_hashes_match(helper, fault):
    a = helper.selected()["artifact"]
    row = (a["native_member"], b"opaque synthetic compiled bytes; never loaded", stat.S_IFREG | 0o755)
    rows = [row]
    if fault == "parent":
        rows.append(("../escape", b"x", stat.S_IFREG | 0o644))
    elif fault == "absolute":
        rows.append(("/escape", b"x", stat.S_IFREG | 0o644))
    elif fault == "symlink":
        rows.append(("alias", b"target", stat.S_IFLNK | 0o777))
    elif fault == "duplicate":
        rows.append(row)
    elif fault == "extra_native":
        rows.append(("extra.so", b"x", stat.S_IFREG | 0o644))
    else:
        rows = [(a["native_member"], b"changed", stat.S_IFREG | 0o755)]
    with pytest.warns(UserWarning) if fault == "duplicate" else __import__("contextlib").nullcontext():
        raw, expected = fixture_archive(helper, wheel_rows=rows)
    with pytest.raises(helper.C.ContractError):
        helper.verify_archive(raw, expected)


@pytest.mark.parametrize("fault", ["qualified", "source", "lock", "schema", "wheel"])
def test_manifest_provenance_and_schema_checked_after_byte_hashes(helper, fault):
    def change(manifest):
        if fault == "qualified":
            manifest["qualified"] = 1
        elif fault == "source":
            manifest["crate_tree"] = "different"
        elif fault == "lock":
            manifest["lock_sha256"] = "different"
        elif fault == "schema":
            manifest["native"]["schemas"]["AgentSimulator"]["version"] = True
        else:
            manifest["wheel"]["native_member"] = "different.so"
    raw, expected = fixture_archive(helper, manifest_change=change)
    with pytest.raises(helper.C.ContractError):
        helper.verify_archive(raw, expected)


def test_archive_member_count_and_expansion_bounds(helper, monkeypatch):
    raw, expected = fixture_archive(helper)
    monkeypatch.setattr(helper, "MAX_WHEEL_MEMBERS", 1)
    with pytest.raises(helper.C.ContractError, match="count"):
        helper.verify_archive(raw, expected)
    monkeypatch.setattr(helper, "MAX_WHEEL_MEMBERS", 32)
    monkeypatch.setattr(helper, "MAX_WHEEL_EXPANDED", 4)
    with pytest.raises(helper.C.ContractError, match="expansion"):
        helper.verify_archive(raw, expected)


def test_redirect_strips_credentials_and_only_accepts_official_blob_destination(helper):
    request = urllib.request.Request("https://api.github.com/repos/YotsuBotfds/Chronicler/actions/artifacts/12861488234/zip",
        headers={"Authorization": "Bearer never-forward", "Cookie": "never-forward", "User-Agent": "test"})
    redirect = helper.OfficialRedirect()
    safe = redirect.redirect_request(request, None, 302, "", {}, "https://official.blob.core.windows.net/payload?sig=redacted")
    assert not safe.has_header("Authorization") and not safe.has_header("Cookie")
    for url in ("http://official.blob.core.windows.net/x", "https://blob.core.windows.net.evil/x", "https://user@official.blob.core.windows.net/x"):
        with pytest.raises(helper.C.ContractError):
            redirect.redirect_request(request, None, 302, "", {}, url)


def test_streaming_reader_rejects_oversized_body_without_retaining_more_than_bound(helper):
    class Response(io.BytesIO):
        headers = {}
    class Opener:
        def open(self, request, timeout):
            assert request.get_header("Authorization") == "Bearer synthetic"
            return Response(b"too large")
    with pytest.raises(helper.C.ContractError, match="exceeds bound"):
        helper.fetch_bytes(Opener(), "https://api.github.com/fixed", "synthetic", 3, helper.time.monotonic() + 1)


def test_retained_receipt_rehashes_exact_payload_set(helper, tmp_path, monkeypatch):
    raw, expected = fixture_archive(helper)
    manifest, wheel = helper.verify_archive(raw, expected)
    (tmp_path / "official-artifact.zip").write_bytes(raw)
    (tmp_path / "build-manifest.json").write_bytes(manifest)
    (tmp_path / Path(expected["artifact"]["wheel_path"]).name).write_bytes(wheel)
    producer = {"root": "synthetic"}
    monkeypatch.setattr(helper, "selected", lambda: expected)
    monkeypatch.setattr(helper, "checked_source", lambda *a: producer)
    helper.C.write(tmp_path / "verification.json", dict(schema_version=1, kind="natural-research-wheel-verification", verified=True,
        runtime_policy=helper.CLOUD_POLICY, artifact=expected["artifact"], schemas=expected["schemas"], producer=producer,
        files=helper.payloads(tmp_path, expected["artifact"]), native_imported=False, wheel_installed=False))
    assert helper.verify_receipt(tmp_path / "verification.json", "synthetic")["verified"] is True
    (tmp_path / "extra").write_bytes(b"not registered")
    with pytest.raises(helper.C.ContractError, match="file set"):
        helper.verify_receipt(tmp_path / "verification.json", "synthetic")


ACTIVATION_BRANCH = "lead/cloud-natural-research-20261029"
WORKFLOW_PATH = ".github/workflows/research-natural-continuation.yml"
PREPARATION_SHA = "7dad47540f24c842633cc2762fa6fd7a9c493556"
# The complete reviewed workflow, excluding only its names, trigger and job
# guard. Exact command bodies, CPU settings, budgets, sources, policies and
# artifact retention are sealed; activation cannot introduce other changes.
REVIEWED_WORKFLOW_INVARIANTS = "5457d30bd36b88adc2766ebedc85a360f72bb8efa17fda7387de3a20aa3b25cf"


def assert_registered_workflow(workflow, activation_registration):
    trigger_keys = [key for key in workflow if key == "on" or key is True]
    assert len(trigger_keys) == 1, "one closed workflow trigger required"
    trigger = workflow[trigger_keys[0]]
    job = workflow["jobs"]["registered-continuation"]
    if trigger == {"workflow_dispatch": None}:
        assert workflow["name"] == "Inactive natural research continuation", "prepared workflow name differs"
        assert job["name"] == "Inactive fixed eight-seed research contrast", "prepared job name differs"
        assert job["if"] == "${{ github.event_name == 'workflow_dispatch' && false }}", "prepared guard must remain false"
    else:
        assert trigger == {"push": {"branches": [ACTIVATION_BRANCH], "paths": [WORKFLOW_PATH]}}, "activation trigger differs"
        assert workflow["name"] == "Registered natural research continuation", "activation workflow name differs"
        assert job["name"] == "Fixed eight-seed research contrast", "activation job name differs"
        assert job["if"] == "${{ github.event_name == 'push' && github.ref == 'refs/heads/lead/cloud-natural-research-20261029' }}", "activation guard differs"
        required = ("# Single prospective natural research continuation attempt", ACTIVATION_BRANCH, PREPARATION_SHA,
            "f60eb23d9d8ef9b6e8afda9eb87f974690686e2a5835c794a6ac3975cfb09a57",
            "f9a6a1e6bdf963426c63a46ba2c74e7fe310098b58875067d921c4bcd14cc89b")
        assert all(value in activation_registration for value in required), "activation registration missing or differs"
    invariant = deepcopy(workflow)
    for key in ("name", "on", True):
        invariant.pop(key, None)
    for key in ("name", "if"):
        invariant["jobs"]["registered-continuation"].pop(key)
    digest = hashlib.sha256(json.dumps(invariant, sort_keys=True, allow_nan=False, separators=(",", ":")).encode()).hexdigest()
    assert digest == REVIEWED_WORKFLOW_INVARIANTS, "reviewed scientific/runtime workflow commands or budgets differ"


def workflow_and_registration():
    import yaml
    workflow = yaml.safe_load((ROOT / WORKFLOW_PATH).read_text())
    path = ROOT / "docs/experiments/scientific-research-natural-activation-2026-10-29.md"
    return workflow, path.read_text() if path.exists() else ""


def test_current_workflow_is_one_of_the_two_closed_registered_states():
    workflow, registration = workflow_and_registration()
    assert_registered_workflow(workflow, registration)


def configured_workflow(state):
    workflow, registration = workflow_and_registration()
    for key in ("on", True):
        workflow.pop(key, None)
    job = workflow["jobs"]["registered-continuation"]
    if state == "prepared":
        workflow.update(name="Inactive natural research continuation", on={"workflow_dispatch": None})
        job.update(name="Inactive fixed eight-seed research contrast",
                   **{"if": "${{ github.event_name == 'workflow_dispatch' && false }}"})
    else:
        workflow.update(name="Registered natural research continuation",
                        on={"push": {"branches": [ACTIVATION_BRANCH], "paths": [WORKFLOW_PATH]}})
        job.update(name="Fixed eight-seed research contrast",
                   **{"if": "${{ github.event_name == 'push' && github.ref == 'refs/heads/lead/cloud-natural-research-20261029' }}"})
    return workflow, registration


@pytest.mark.parametrize("state", ["prepared", "activated"])
def test_both_closed_workflow_states_preserve_all_reviewed_commands(state):
    workflow, registration = configured_workflow(state)
    assert_registered_workflow(workflow, registration)


@pytest.mark.parametrize("fault", ["branch", "path", "dispatch", "false_guard", "arbitrary_guard", "policy", "seed", "budget", "cpu", "source", "unverified_install", "registration"])
def test_active_workflow_refuses_any_unregistered_activation_or_scientific_change(fault):
    workflow, registration = configured_workflow("activated")
    trigger = workflow.get("on", workflow.get(True))["push"]
    job = workflow["jobs"]["registered-continuation"]
    if fault == "branch": trigger["branches"].append("main")
    elif fault == "path": trigger["paths"] = ["**"]
    elif fault == "dispatch": workflow.get("on", workflow.get(True))["workflow_dispatch"] = None
    elif fault == "false_guard": job["if"] = "${{ false }}"
    elif fault == "arbitrary_guard": job["if"] = "${{ github.event_name == 'push' }}"
    elif fault == "budget": job["timeout-minutes"] = 61
    elif fault == "cpu": workflow["env"]["PYTHON_CPU_COUNT"] = "2"
    elif fault == "source":
        next(step for step in job["steps"] if step["name"] == "Check out the exact qualified producer separately")["with"]["ref"] = "main"
    elif fault == "registration": registration = ""
    else:
        name = "Install only the verified wheel without dependency changes" if fault == "unverified_install" else "Run the unchanged fixed cohort under its original resource admission"
        step = next(step for step in job["steps"] if step["name"] == name)
        if fault == "policy": step["run"] = step["run"].replace("cloud-fullgate-06db", "local-fb20")
        elif fault == "seed": step["run"] += " --seed 2008\n"
        else: step["run"] = step["run"].replace("--no-deps", "")
    with pytest.raises(AssertionError):
        assert_registered_workflow(workflow, registration)
