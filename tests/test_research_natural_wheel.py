"""Pure byte/HTTP contracts: no network, install, native import or study world."""
from copy import deepcopy
import importlib.util
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


def test_workflow_has_no_push_activation_and_uses_exact_source_and_verified_wheel():
    import yaml
    workflow = yaml.safe_load((ROOT / ".github/workflows/research-natural-continuation.yml").read_text())
    assert set(workflow.get("on", workflow.get(True))) == {"workflow_dispatch"}
    job = workflow["jobs"]["registered-continuation"]
    assert job["if"] == "${{ github.event_name == 'workflow_dispatch' && false }}"
    source = next(s for s in job["steps"] if s["name"] == "Check out the exact qualified producer separately")
    assert source["with"]["ref"] == "c76efe8552b4c6c288ebb1f813e2c0a58e5957b1"
    assert workflow["env"]["PYTHON_CPU_COUNT"] == "1"
    text = "\n".join(s.get("run", "") for s in job["steps"])
    assert "maturin" not in text and "cargo " not in text
    assert "--wheel-receipt" in text and "--no-deps" in text
