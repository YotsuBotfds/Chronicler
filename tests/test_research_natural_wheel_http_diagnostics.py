"""Synthetic HTTP failures only; no network, credentials, installs or worlds."""
import io
import json
from pathlib import Path
import urllib.error
import urllib.request

import pytest

from test_research_natural_wheel import fixture_archive, helper

SECRET = "diagnostic-secret-never-retained"
SIGNED_AZURE = "https://registered.blob.core.windows.net/fixed?sig=" + SECRET


class UnreadErrorBody(io.BytesIO):
    def read(self, *args):
        pytest.fail("HTTP error body must never be read")


def denied(url, status):
    return urllib.error.HTTPError(url, status, "private message " + SECRET,
        {"Authorization": "Bearer " + SECRET, "X-Private": SECRET}, UnreadErrorBody(SECRET.encode()))


class Response(io.BytesIO):
    headers = {}
    def __init__(self, body, url):
        super().__init__(body)
        self.url = url
    def geturl(self): return self.url
    def getcode(self): return 200


def metadata(h, expected=None):
    a = (expected or h.selected())["artifact"]
    return dict(id=a["id"], name=a["name"], size_in_bytes=a["bytes"], digest="sha256:" + a["sha256"],
                expired=False, workflow_run=dict(id=a["run_id"], head_sha=a["control_sha"]))


@pytest.mark.parametrize("status", [401, 403, 404])
@pytest.mark.parametrize("provider", ["github_api", "azure_blob"])
def test_http_failure_keeps_only_stage_numeric_status_and_provider(helper, status, provider):
    trace = []
    url = helper.endpoint() if provider == "github_api" else SIGNED_AZURE
    error = denied(url, status)
    class Opener:
        def open(self, request, timeout): raise error
    with pytest.raises(helper.FetchFailure) as caught:
        helper.fetch_bytes(Opener(), helper.endpoint() + "/zip", SECRET, 4096,
                           helper.time.monotonic() + 1, trace=trace, stage="zip_get")
    expected = dict(stage="azure_redirect" if provider == "azure_blob" else "zip_get",
                    http_status=status, provider_kind=provider)
    assert caught.value.record == expected and trace == [expected]
    assert error.fp.closed
    text = str(caught.value) + repr(caught.value) + json.dumps(trace)
    assert SECRET not in text and "https://" not in text and "Authorization" not in text


@pytest.mark.parametrize("status", [401, 403, 404])
@pytest.mark.parametrize("diagnostic", [False, True])
def test_metadata_denial_stops_without_zip_or_alternate_route_and_retains_safe_failure(helper, tmp_path, monkeypatch, capsys, status, diagnostic):
    requests = []
    class Opener:
        def open(self, request, timeout):
            requests.append(request.full_url)
            raise denied(request.full_url, status)
    monkeypatch.setenv("GH_TOKEN", SECRET)
    monkeypatch.setattr(helper, "checked_source", lambda *a: {"explicit": "test-fixture"})
    monkeypatch.setattr(helper.urllib.request, "build_opener", lambda *a: Opener())
    root = tmp_path / "out"
    args = ["--source-root", str(tmp_path / "source"), "--output-root", str(root)]
    assert helper.main(args + (["--diagnostic"] if diagnostic else [])) == 1
    assert requests == [helper.endpoint()]
    path = root / ("diagnostics.json" if diagnostic else "failure.json")
    result = helper.C.read(path)
    assert result["failure"] == dict(stage="metadata_get", http_status=status, provider_kind="github_api")
    assert result["metadata_contract_verified"] is result["archive_verified"] is False
    assert {p.name for p in root.iterdir()} == {path.name}
    output = path.read_text() + capsys.readouterr().err
    assert SECRET not in output and "https://" not in output and "Authorization" not in output


@pytest.mark.parametrize("provider", ["github_api", "azure_blob"])
def test_metadata_is_verified_before_single_zip_denial(helper, tmp_path, monkeypatch, provider):
    requests = []
    class Opener:
        def open(self, request, timeout):
            requests.append(request.full_url)
            if len(requests) == 1:
                return Response(helper.C.encoded(metadata(helper)), request.full_url)
            raise denied(request.full_url if provider == "github_api" else SIGNED_AZURE, 403)
    monkeypatch.setenv("GH_TOKEN", SECRET)
    monkeypatch.setattr(helper, "checked_source", lambda *a: {"explicit": "test-fixture"})
    monkeypatch.setattr(helper.urllib.request, "build_opener", lambda *a: Opener())
    root = tmp_path / "out"
    assert helper.main(["--diagnostic", "--source-root", str(tmp_path / "source"), "--output-root", str(root)]) == 1
    assert requests == [helper.endpoint(), helper.endpoint() + "/zip"]
    result = helper.C.read(root / "diagnostics.json")
    assert result["metadata_contract_verified"] is True and result["archive_verified"] is False
    assert result["failure"] == dict(stage="azure_redirect" if provider == "azure_blob" else "zip_get",
                                      http_status=403, provider_kind=provider)
    assert SECRET not in (root / "diagnostics.json").read_text()


def test_wrong_metadata_stops_before_any_zip_request(helper, tmp_path, monkeypatch):
    calls = []
    bad = metadata(helper)
    bad["id"] += 1
    class Opener:
        def open(self, request, timeout):
            calls.append(request.full_url)
            return Response(helper.C.encoded(bad), request.full_url)
    monkeypatch.setenv("GH_TOKEN", SECRET)
    monkeypatch.setattr(helper, "checked_source", lambda *a: {})
    monkeypatch.setattr(helper.urllib.request, "build_opener", lambda *a: Opener())
    root = tmp_path / "out"
    assert helper.main(["--diagnostic", "--source-root", str(tmp_path / "source"), "--output-root", str(root)]) == 1
    assert calls == [helper.endpoint()]
    assert helper.C.read(root / "diagnostics.json")["failure"]["stage"] == "metadata_contract"


def test_redirect_never_forwards_authorization_cookie_or_proxy_credentials(helper):
    trace = []
    request = urllib.request.Request(helper.endpoint() + "/zip", headers={"Authorization": "Bearer " + SECRET,
        "Proxy-Authorization": SECRET, "Cookie": SECRET, "Accept": "application/vnd.github+json"})
    redirected = helper.OfficialRedirect(trace).redirect_request(request, None, 302, SECRET, {"private": SECRET}, SIGNED_AZURE)
    assert all(key.lower() not in ("authorization", "proxy-authorization", "cookie") for key, _ in redirected.header_items())
    assert trace == [dict(stage="zip_get", http_status=302, provider_kind="github_api"),
                     dict(stage="azure_redirect", http_status=None, provider_kind="azure_blob")]
    assert SECRET not in json.dumps(trace)


def test_cross_origin_redirect_rebuilds_headers_and_derives_destination_host(helper):
    from types import SimpleNamespace
    # Exercise urllib's real header preparation, which adds Host as an
    # unredirected header. Calling redirect_request on an unprepared Request
    # would miss the production failure even if authorization was stripped.
    handler = urllib.request.HTTPHandler()
    handler.parent = SimpleNamespace(addheaders=[])
    request = urllib.request.Request(helper.endpoint() + "/zip", headers={
        "Authorization": "Bearer " + SECRET, "Proxy-Authorization": SECRET, "Cookie": SECRET,
        "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28", "X-Origin-Only": SECRET})
    handler.do_request_(request)
    assert request.get_header("Host") == "api.github.com"
    redirected = helper.OfficialRedirect().redirect_request(request, None, 302, SECRET, {},
        "https://unit.blob.core.windows.net/fixed")
    assert {key.lower() for key, _ in redirected.header_items()} <= {"user-agent"}
    handler.do_request_(redirected)
    assert redirected.get_header("Host") == "unit.blob.core.windows.net"
    assert {key.lower() for key, _ in redirected.header_items()} <= {"host", "user-agent"}
    assert SECRET not in str(redirected.header_items())


def test_actual_redirect_handler_closes_without_draining_body(helper):
    from types import SimpleNamespace
    trace, followed = [], []
    request = urllib.request.Request(helper.endpoint() + "/zip", headers={"Authorization": "Bearer " + SECRET})
    request.timeout = 15
    handler = helper.OfficialRedirect(trace)
    handler.parent = SimpleNamespace(open=lambda request, timeout: followed.append(request) or "response")
    body = UnreadErrorBody(SECRET.encode())
    assert handler.http_error_302(request, body, 302, SECRET, {"Location": SIGNED_AZURE}) == "response"
    assert body.closed and len(followed) == 1
    assert followed[0].get_header("Authorization") is None
    assert SECRET not in json.dumps(trace)


def test_redirect_denial_closes_without_read_or_alternate_request(helper):
    from types import SimpleNamespace
    request = urllib.request.Request(helper.endpoint() + "/zip")
    request.timeout = 15
    handler = helper.OfficialRedirect([])
    handler.parent = SimpleNamespace(open=lambda *a, **k: pytest.fail("unregistered redirect must stop"))
    body = UnreadErrorBody(SECRET.encode())
    with pytest.raises(helper.FetchFailure) as error:
        handler.http_error_302(request, body, 302, SECRET, {"Location": "https://alternate.example/?secret=" + SECRET})
    assert body.closed and error.value.record == dict(stage="redirect_validation", http_status=302, provider_kind="unregistered")
    assert SECRET not in str(error.value)


def test_unregistered_endpoint_is_rejected_before_authentication_is_sent(helper):
    class Opener:
        def open(self, *a, **k): pytest.fail("no alternate endpoint may receive authorization")
    with pytest.raises(helper.C.ContractError, match="unregistered artifact endpoint"):
        helper.fetch_bytes(Opener(), "https://api.github.com/repos/alternate/artifacts/other", SECRET,
                           4096, helper.time.monotonic() + 1)


def test_expired_deadline_stops_before_a_request_is_sent(helper):
    class Opener:
        def open(self, *a, **k): pytest.fail("expired diagnostic cannot send a request")
    with pytest.raises(helper.C.ContractError, match="wall budget"):
        helper.fetch_bytes(Opener(), helper.endpoint(), SECRET, 4096, helper.time.monotonic() - 1)


def test_absolute_timeout_is_sanitized_and_restores_timer_ownership(helper, tmp_path, monkeypatch):
    original = helper.signal.getsignal(helper.signal.SIGALRM)
    calls = []
    class Opener:
        def open(self, request, timeout):
            calls.append(request.full_url)
            handler = helper.signal.getsignal(helper.signal.SIGALRM)
            handler(helper.signal.SIGALRM, None)
    monkeypatch.setenv("GH_TOKEN", SECRET)
    monkeypatch.setattr(helper, "checked_source", lambda *a: {})
    monkeypatch.setattr(helper.urllib.request, "build_opener", lambda *a: Opener())
    root = tmp_path / "out"
    assert helper.main(["--diagnostic", "--source-root", str(tmp_path / "source"), "--output-root", str(root)]) == 1
    assert calls == [helper.endpoint()]
    assert helper.C.read(root / "diagnostics.json")["failure"] == dict(
        stage="metadata_get", http_status=None, provider_kind="local_verifier")
    assert helper.signal.getitimer(helper.signal.ITIMER_REAL) == (0.0, 0.0)
    assert helper.signal.getsignal(helper.signal.SIGALRM) is original


def test_unexpected_success_body_is_never_retained_as_an_artifact(helper, tmp_path, monkeypatch):
    calls = []
    class Opener:
        def open(self, request, timeout):
            calls.append(request.full_url)
            return Response(helper.C.encoded(metadata(helper)) if len(calls) == 1 else SECRET.encode(), request.full_url)
    monkeypatch.setenv("GH_TOKEN", SECRET)
    monkeypatch.setattr(helper, "checked_source", lambda *a: {})
    monkeypatch.setattr(helper.urllib.request, "build_opener", lambda *a: Opener())
    root = tmp_path / "out"
    assert helper.main(["--diagnostic", "--source-root", str(tmp_path / "source"), "--output-root", str(root)]) == 1
    assert {p.name for p in root.iterdir()} == {"diagnostics.json"}
    assert SECRET not in (root / "diagnostics.json").read_text()
    assert helper.C.read(root / "diagnostics.json")["failure"]["stage"] == "archive_verify"


def test_verified_diagnostic_success_never_creates_an_installable_verification_receipt(helper, tmp_path, monkeypatch):
    raw, expected = fixture_archive(helper)
    calls = []
    class Opener:
        def open(self, request, timeout):
            calls.append(request.full_url)
            body = helper.C.encoded(metadata(helper, expected)) if len(calls) == 1 else raw
            return Response(body, request.full_url)
    monkeypatch.setenv("GH_TOKEN", SECRET)
    monkeypatch.setattr(helper, "selected", lambda: expected)
    monkeypatch.setattr(helper, "checked_source", lambda *a: {})
    monkeypatch.setattr(helper.urllib.request, "build_opener", lambda *a: Opener())
    root = tmp_path / "out"
    assert helper.main(["--diagnostic", "--source-root", str(tmp_path / "source"), "--output-root", str(root)]) == 0
    result = helper.C.read(root / "diagnostics.json")
    assert result["metadata_contract_verified"] is result["archive_verified"] is True
    assert result["native_imported"] is result["wheel_installed"] is False
    assert not (root / "verification.json").exists()
    assert calls == [helper.endpoint(), helper.endpoint() + "/zip"]


@pytest.mark.parametrize("diagnostic", [False, True])
def test_timer_disarm_failure_invalidates_positive_and_restores_ownership(helper, tmp_path, monkeypatch, capsys, diagnostic):
    raw, expected = fixture_archive(helper)
    calls = []
    class Opener:
        def open(self, request, timeout):
            calls.append(request.full_url)
            return Response(helper.C.encoded(metadata(helper, expected)) if len(calls) == 1 else raw, request.full_url)
    original_handler = helper.signal.getsignal(helper.signal.SIGALRM)
    original_timer = helper.signal.setitimer
    failed_once = False
    def timer(which, seconds):
        nonlocal failed_once
        if seconds == 0 and not failed_once:
            failed_once = True
            raise OSError("private teardown failure " + SECRET)
        return original_timer(which, seconds)
    monkeypatch.setenv("GH_TOKEN", SECRET)
    monkeypatch.setattr(helper, "selected", lambda: expected)
    monkeypatch.setattr(helper, "checked_source", lambda *a: {})
    monkeypatch.setattr(helper.urllib.request, "build_opener", lambda *a: Opener())
    monkeypatch.setattr(helper.signal, "setitimer", timer)
    root = tmp_path / "out"
    args = ["--source-root", str(tmp_path / "source"), "--output-root", str(root)]
    assert helper.main(args + (["--diagnostic"] if diagnostic else [])) == 1
    assert calls == [helper.endpoint(), helper.endpoint() + "/zip"]  # No network retry.
    assert not (root / "verification.json").exists()
    failure_path = root / ("diagnostics.json" if diagnostic else "failure.json")
    result = helper.C.read(failure_path)
    assert result["archive_verified"] is False
    assert result["failure"] == dict(stage="timer_finalization", http_status=None, provider_kind="local_verifier")
    assert (root / ("incomplete-diagnostics.json" if diagnostic else "incomplete-verification.json")).is_file()
    assert helper.signal.getitimer(helper.signal.ITIMER_REAL) == (0.0, 0.0)
    assert helper.signal.getsignal(helper.signal.SIGALRM) is original_handler
    assert SECRET not in failure_path.read_text() + capsys.readouterr().err
