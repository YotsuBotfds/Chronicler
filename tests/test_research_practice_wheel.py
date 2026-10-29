"""Tiny ZIP/HTTP-preparation fixtures, without requests, installs or imports."""
from copy import deepcopy
import hashlib
import importlib
import io
import json
from pathlib import Path
import urllib.error
import urllib.request
import zipfile

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def helper(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    return importlib.import_module("fetch_research_practice_wheel")


def zipped(rows):
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, raw in rows:
            archive.writestr(name, raw)
    return out.getvalue()


def archive_fixture(helper, *, classes=None, native_bad=False):
    selected = helper.selected()
    a = selected["artifact"]
    native = b"scalar fixture: never a compiled module"
    wheel = zipped([(a["native_member"], b"different" if native_bad else native),
                    ("chronicler_agents/__init__.py", b"# never imported\n")])
    a.update(wheel_bytes=len(wheel), wheel_sha256=hashlib.sha256(wheel).hexdigest(),
             native_bytes=len(native), native_sha256=hashlib.sha256(native).hexdigest())
    manifest = dict(schema_version=1, source_commit=a["control_sha"],
        wheel=dict(filename=Path(a["wheel_path"]).name, bytes=len(wheel), sha256=a["wheel_sha256"], native_member=a["native_member"]),
        installed_native=dict(filename=Path(a["native_member"]).name, bytes=len(native), sha256=a["native_sha256"], wheel_member_sha256=a["native_sha256"]),
        scope="Completed CI build identity only; no reproducibility, performance or scientific qualification",
        python="3.13.17 (fixture)", classes=classes if classes is not None else ["AgentSimulator", "EcologySimulator", "PoliticsSimulator"])
    manifest_raw = json.dumps(manifest, indent=2).encode()
    a.update(manifest_bytes=len(manifest_raw), manifest_sha256=hashlib.sha256(manifest_raw).hexdigest())
    raw = zipped([(a["manifest_path"], manifest_raw), (a["wheel_path"], wheel)])
    a.update(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
    return raw, selected, manifest_raw, wheel


def test_tiny_nested_exact_bytes_verify_without_native_loading(helper):
    raw, selected, manifest, wheel = archive_fixture(helper)
    assert helper.verify_archive(raw, selected) == (manifest, wheel)
    assert helper.selected()["artifact"]["bytes"] == 3850581


@pytest.mark.parametrize("fault", ["wrong_classes", "native_bytes", "zip_digest", "manifest_digest", "wheel_digest"])
def test_nested_archive_refuses_each_independent_identity_fault(helper, fault):
    raw, selected, _, _ = archive_fixture(helper,
        classes=["AgentSimulator"] if fault == "wrong_classes" else None, native_bad=fault == "native_bytes")
    if fault.endswith("digest"):
        key = {"zip_digest": "sha256", "manifest_digest": "manifest_sha256", "wheel_digest": "wheel_sha256"}[fault]
        selected["artifact"][key] = "0"*64
    with pytest.raises(ValueError):
        helper.verify_archive(raw, selected)


def test_real_urllib_header_preparation_derives_destination_host_and_drops_origin_headers(helper):
    request = urllib.request.Request(helper.endpoint()+"/zip", headers={
        "Authorization": "Bearer fixture-secret", "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28", "User-Agent": helper.USER_AGENT})
    # No opener/open/network: exercise actual urllib's automatic Host handling.
    handler = urllib.request.HTTPHandler()
    handler.add_parent(urllib.request.OpenerDirector())
    request = handler.do_request_(request)
    assert request.get_header("Host") == "api.github.com"
    target = "https://unit.blob.core.windows.net/fixture?sig=fixture-secret"
    redirected = helper.OfficialRedirect().redirect_request(request, None, 302, "", {}, target)
    redirected = handler.do_request_(redirected)
    assert redirected.get_header("Host") == "unit.blob.core.windows.net"
    headers = {key.lower(): value for key, value in redirected.header_items()}
    assert "authorization" not in headers and "accept" not in headers and "x-github-api-version" not in headers
    assert headers["user-agent"] == helper.USER_AGENT


@pytest.mark.parametrize("status", [401, 403, 404, 400])
def test_failed_http_retains_only_stage_status_provider_without_reading_body(helper, status):
    class Body(io.BytesIO):
        def read(self, *args):
            raise AssertionError("denied body must never be read")
    body = Body(b"fixture-secret")
    error = urllib.error.HTTPError("https://unit.blob.core.windows.net/secret?sig=fixture-secret",
                                  status, "fixture-secret", {"secret": "fixture-secret"}, body)
    class Opener:
        def open(self, *args, **kwargs):
            raise error
    with pytest.raises(helper.FetchFailure) as caught:
        helper.fetch_bytes(Opener(), helper.endpoint()+"/zip", "fixture-secret", 1024, float("inf"))
    assert caught.value.record == dict(stage="azure_redirect", http_status=status, provider_kind="azure_blob")
    assert "fixture-secret" not in str(caught.value) and "http" not in str(caught.value).replace("http_status", "")
    assert body.closed


def test_fixed_transport_refuses_arbitrary_api_endpoint_before_open(helper):
    class Opener:
        def open(self, *args, **kwargs):
            raise AssertionError("unregistered endpoint must never be requested")
    with pytest.raises(ValueError, match="unregistered artifact endpoint"):
        helper.fetch_bytes(Opener(), "https://api.github.com/arbitrary", "fixture", 1, float("inf"))
