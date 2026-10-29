"""Tiny, pure contracts for the pending full-output byte-audit frontend.

No real ZIP, artifact, credential, socket, process or native package is used.
These fixtures exercise contracts only and cannot qualify an actual study.
"""
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import urllib.error
import urllib.request

import pytest

import wealth_floor_full_archive_audit as W


H = "a" * 64
EXPIRY = "2026-11-28T10:46:48Z"
ERRORS = (W.Refused, W.A.AdmissionError)


def pin(world="template", family="raw", artifact_id=101, *, data=b"abc", **changes):
    row = dict(worldgen=world, family=family, artifact_id=artifact_id,
        name=f"wealth-outcome-full-{world}-{family}-{W.PRODUCER_RUN}-1",
        size=len(data), sha256=hashlib.sha256(data).hexdigest(), expires_at=EXPIRY)
    row.update(changes)
    return W.InputPin(**row)


def pins(*optional):
    rows = [pin(world, family, 100 + index)
        for index, (world, family) in enumerate((
            (world, family) for world in ("template", "procedural")
            for family in ("light", "raw", "contracts")))]
    rows.extend(pin(world, family, 200 + index)
        for index, (world, family) in enumerate(optional))
    return tuple(rows)


def member(data=b"x"):
    return dict(bytes=len(data), sha256=hashlib.sha256(data).hexdigest())


def inventory(files=None):
    files = {"payload/file.bin": member()} if files is None else files
    return dict(complete=True, files=files, file_count=len(files),
        total_bytes=sum(row["bytes"] for row in files.values()))


def authorities(inv=None):
    inv = inventory() if inv is None else inv
    return {"result.json": b"{}", "provenance.json": b"{}", "raw-inventory.json": W.A.json_bytes(inv)}


class Budget:
    def __init__(self):
        self.calls = 0

    def check(self):
        self.calls += 1


class Response:
    def __init__(self, data=b"abc", *, headers=None, url=None, status=200):
        self.data, self.headers, self.url = data, ({} if headers is None else headers), url
        self.status, self.offset, self.reads, self.closed = status, 0, [], False

    def read1(self, count):
        self.reads.append(count)
        raw = self.data[self.offset:self.offset + count]
        self.offset += len(raw)
        return raw

    def getcode(self):
        return self.status

    def geturl(self):
        return self.url

    def close(self):
        self.closed = True

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


@pytest.mark.parametrize("value", [None, True, "2026-11-28", "2026-11-28T10:46:48+00:00",
    "2026-11-28T10:46:48.000Z", "2026-11-28T10:46:48z", "2026-02-30T10:46:48Z",
    "2026-11-28T10:46:60Z", "2026-1-28T10:46:48Z", "2026-11-28T10:46:48Z\n"])
def test_strict_expiry_rejects_noncanonical_or_invalid_utc(value):
    with pytest.raises(W.Refused):
        W.strict_utc(value)


def test_strict_expiry_and_input_are_typed_immutable_facts():
    assert W.strict_utc(EXPIRY) == datetime(2026, 11, 28, 10, 46, 48, tzinfo=timezone.utc)
    item = pin()
    with pytest.raises((AttributeError, TypeError)):
        item.artifact_id = 300
    assert item.sha256 == hashlib.sha256(b"abc").hexdigest()


@pytest.mark.parametrize("changes", [dict(worldgen="unknown"), dict(family="other"),
    dict(worldgen=[]), dict(family={}),
    dict(artifact_id=True), dict(artifact_id=0), dict(name="moving-name"),
    dict(size=True), dict(size=0), dict(size=W.A.MAX_COMPRESSED_BYTES + 1),
    dict(sha256="A" * 64), dict(sha256="a" * 63), dict(expires_at="2026-11-28")])
def test_input_pin_refuses_drift_and_untyped_bounds(changes):
    with pytest.raises(W.Refused):
        pin(**changes)


def test_closed_outputs_accept_six_base_or_all_ten_registered_families():
    base = W.closed_inputs(pins())
    assert len(base) == 6
    all_rows = pins(("template", "failure-metadata"), ("template", "failed-checkpoints"),
        ("procedural", "failure-metadata"), ("procedural", "failed-checkpoints"))
    assert len(W.closed_inputs(all_rows)) == 10
    with pytest.raises(TypeError):
        base[("template", "raw")] = pin()


@pytest.mark.parametrize("selection", ["list", "missing", "duplicate", "duplicate-id", "missing-base", "extra"])
def test_closed_outputs_reject_aliases_missing_world_families_and_extra_rows(selection):
    rows = pins()
    if selection == "list":
        rows = list(rows)
    elif selection == "missing":
        rows = rows[:-1]
    elif selection == "duplicate":
        rows = rows + (rows[0],)
    elif selection == "duplicate-id":
        rows = rows[:-1] + (replace(rows[-1], artifact_id=rows[0].artifact_id),)
    elif selection == "missing-base":
        rows = rows[:-1] + (pin("template", "failure-metadata", 900),)
    else:
        rows = rows + rows
    with pytest.raises(W.Refused):
        W.closed_inputs(rows)


def test_staging_admission_accounts_for_all_staging_output_floor_and_reserve(monkeypatch):
    monkeypatch.setattr(W, "DISK_ADMISSION", 12)
    monkeypatch.setattr(W, "RAM_ADMISSION", 2)
    monkeypatch.setattr(W, "DISK_FLOOR", 3)
    monkeypatch.setattr(W, "RESERVE", 8)
    monkeypatch.setattr(W, "MAX_OUTPUT", 20)
    monkeypatch.setattr(W, "MAX_STAGED", 30)
    args = dict(available_disk=51, available_ram=2, staged_bytes=30, output_bytes=10)
    assert W.staging_admission(**args) == dict(staged_bytes=30, output_bytes=10,
        disk_floor_bytes=3, reserve_bytes=8, ram_admission_bytes=2)
    with pytest.raises(W.Refused):
        W.staging_admission(**dict(args, available_disk=50))
    with pytest.raises(W.Refused):
        W.staging_admission(**dict(args, staged_bytes=31, available_disk=52))
    for changes in (dict(available_ram=1), dict(available_disk=11), dict(staged_bytes=0),
        dict(output_bytes=0), dict(output_bytes=21), dict(staged_bytes=True), dict(output_bytes=-1)):
        with pytest.raises(W.Refused):
            W.staging_admission(**dict(args, **changes))


def test_explicit_members_accepts_empty_files_but_never_empty_archives():
    expected = W.explicit_members({"dir/empty.bin": member(b"")})
    assert expected["dir/empty.bin"].size == 0
    with pytest.raises(TypeError):
        expected["other"] = W.A.FilePin(0, H)
    with pytest.raises(W.Refused):
        W.explicit_members({})


@pytest.mark.parametrize("rows", [
    {"../escape": member()}, {"/absolute": member()}, {"a\\b": member()},
    {"a": member(), "a/child": member()}, {"a": {"bytes": True, "sha256": H}},
    {"a": {"bytes": -1, "sha256": H}}, {"a": {"bytes": 1, "sha256": H, "extra": 1}},
    {"a": {"bytes": 1, "sha256": "invalid"}},
])
def test_explicit_members_refuses_unsafe_aliases_and_untyped_rows(rows):
    with pytest.raises(ERRORS):
        W.explicit_members(rows)


def test_explicit_member_count_and_whole_expansion_are_checked_before_kernel(monkeypatch):
    monkeypatch.setattr(W.A, "MAX_ENTRIES", 2)
    monkeypatch.setattr(W.A, "MAX_PAYLOAD_BYTES", 4)
    assert len(W.explicit_members({"a": member(b"aa"), "b": member(b"bb")})) == 2
    for rows in ({"a": member(), "b": member(), "c": member()},
        {"a": member(b"aaa"), "b": member(b"bb")}):
        with pytest.raises(W.Refused):
            W.explicit_members(rows)


def test_normal_raw_closure_adds_all_three_authorities_and_all_light_copies():
    auth, light = authorities(), {"nested/report.json": member(b"report"), "index.json": member(b"index")}
    expected = W.normal_raw_members(inventory(), auth, light)
    assert set(expected) == {"payload/file.bin", *auth, "light/nested/report.json", "light/index.json"}
    for name, raw in auth.items():
        assert expected[name] == W.A.FilePin(len(raw), hashlib.sha256(raw).hexdigest())
    assert expected["light/nested/report.json"].sha256 == light["nested/report.json"]["sha256"]


@pytest.mark.parametrize("kind", ["incomplete", "count", "bytes", "authority-missing", "authority-extra",
    "authority-type", "empty-light", "root-collision", "light-collision", "parent-collision"])
def test_normal_raw_closure_refuses_drift_collision_or_incomplete_authority(kind):
    inv, auth, light = inventory(), authorities(), {"report.json": member()}
    if kind == "incomplete": inv["complete"] = False
    elif kind == "count": inv["file_count"] += 1
    elif kind == "bytes": inv["total_bytes"] += 1
    elif kind == "authority-missing": del auth["result.json"]
    elif kind == "authority-extra": auth["extra.json"] = b"{}"
    elif kind == "authority-type": auth["result.json"] = "{}"
    elif kind == "empty-light": light = {}
    else:
        path = {"root-collision": "result.json", "light-collision": "light/report.json",
            "parent-collision": "light"}[kind]
        inv = inventory({path: member()})
        auth = authorities(inv)
    with pytest.raises(ERRORS):
        W.normal_raw_members(inv, auth, light)


def test_whole_raw_limit_includes_late_authorities_and_duplicate_light(monkeypatch):
    inv, auth = inventory(), authorities()
    monkeypatch.setattr(W.A, "MAX_PAYLOAD_BYTES", 1 + sum(len(raw) for raw in auth.values()) + 1)
    assert sum(p.size for p in W.explicit_members(inv["files"]).values()) == 1
    with pytest.raises(W.Refused):
        W.normal_raw_members(inv, auth, {"report.json": member(b"xx")})


def test_normal_raw_closure_authenticates_the_same_inventory_used_for_expected_rows():
    inv = inventory()
    auth = authorities(inventory({"different-payload.bin": member()}))
    with pytest.raises(W.Refused):
        W.normal_raw_members(inv, auth, {"report.json": member()})


def test_metadata_admission_uses_only_exact_allowlist_and_total_retained_bound(monkeypatch):
    monkeypatch.setattr(W.A, "MAX_METADATA_BYTES", 4)
    monkeypatch.setattr(W, "MAX_METADATA", 6)
    expected = W.explicit_members({"report.json": member(b"abc"),
        "index.json": member(b"xy"), "original-body.json": member(b"opaque-body")})
    names = frozenset(("report.json", "index.json"))
    assert W.metadata_admission(expected, names, retained_bytes=1) == 6
    with pytest.raises(W.Refused):
        W.metadata_admission(expected, names, retained_bytes=2)
    with pytest.raises(W.Refused):
        W.metadata_admission(expected, frozenset(("original-body.json",)))
    for names, retained in ((set(("report.json",)), 0), (frozenset(), 0),
        (frozenset(("missing.json",)), 0), (frozenset(("report.json",)), True)):
        with pytest.raises(W.Refused):
            W.metadata_admission(expected, names, retained_bytes=retained)


def test_audit_delegates_exact_checked_closure_to_unchanged_kernel(monkeypatch):
    old_archives, old_proofs = W.A.ARCHIVES, W.A.REVIEWED_CANDIDATE_PROOFS
    old_limits = {key: getattr(W.A, key) for key in ("MAX_ENTRIES", "MAX_PAYLOAD_BYTES",
        "MAX_AGGREGATE_PAYLOAD", "MAX_COMPRESSED_BYTES", "MAX_CENTRAL_BYTES")}
    calls = []
    def kernel(path, expected, selected, budget):
        calls.append((path, expected, selected, budget))
        return {"pending": True}
    monkeypatch.setattr(W.A, "audit_archive", kernel)
    selected, budget = pin(), object()
    assert W.audit_archive("synthetic-only", {"payload/a": W.A.FilePin(1, H)}, selected, budget) == {"pending": True}
    path, expected, actual_pin, actual_budget = calls.pop()
    assert path == "synthetic-only" and actual_pin is selected and actual_budget is budget
    assert expected == {"payload/a": W.A.FilePin(1, H)}
    assert W.A.ARCHIVES is old_archives and W.A.REVIEWED_CANDIDATE_PROOFS is old_proofs
    assert {key: getattr(W.A, key) for key in old_limits} == old_limits
    with pytest.raises(W.Refused):
        W.audit_archive("never-open", {"a": W.A.FilePin(1, H), "a/b": W.A.FilePin(1, H)}, selected, budget)
    assert not calls


@pytest.mark.parametrize("passed,conclusion,label", [
    (True, "success", "positive_claim_pending_evidence"),
    (False, "failure", "negative_science_claim_pending_evidence"),
])
def test_consistent_scientific_claims_still_remain_pending_evidence(passed, conclusion, label):
    report = dict(execution_complete=True, identities_stable=True, gate_pass=passed,
        gate_exit_code=0 if passed else 2, qualified=passed)
    assert W.outcome_consistency(report, conclusion) == label
    assert "pending_evidence" in label


@pytest.mark.parametrize("change", [dict(gate_exit_code=1), dict(gate_exit_code=True),
    dict(gate_pass=1), dict(qualified=False), dict(qualified="true")])
def test_complete_claims_refuse_wrong_exit_or_qualified_types(change):
    report = dict(execution_complete=True, identities_stable=True, gate_pass=True,
        gate_exit_code=0, qualified=True)
    with pytest.raises(W.Refused):
        W.outcome_consistency(dict(report, **change), "success")


@pytest.mark.parametrize("conclusion", ["success", "cancelled", "timed_out"])
def test_negative_science_claim_requires_exact_failure_conclusion(conclusion):
    with pytest.raises(W.Refused):
        W.outcome_consistency(dict(execution_complete=True, identities_stable=True,
            gate_pass=False, gate_exit_code=2, qualified=False), conclusion)


def test_incomplete_claim_never_gains_qualification():
    assert W.outcome_consistency({"execution_complete": False, "qualified": False}, "timed_out") == "incomplete_claim_no_qualification"
    with pytest.raises(W.Refused):
        W.outcome_consistency({"execution_complete": False, "qualified": True}, "failure")


def test_redirect_strips_authorization_and_all_inherited_headers():
    selected = W.endpoint(pin()) + "/zip"
    handler = W.ClosedRedirect(selected, frozenset((selected,)))
    request = urllib.request.Request(selected, headers={"Authorization": "Bearer synthetic-secret",
        "Accept": "application/private", "X-Private": "sensitive"})
    redirected = handler.redirect_request(request, None, 302, "", {}, "https://store.blob.core.windows.net/file?sig=synthetic")
    assert redirected.full_url.startswith("https://store.blob.core.windows.net/")
    assert dict(redirected.header_items()) == {"User-agent": W.USER_AGENT}
    assert handler.followed is True
    with pytest.raises(W.Refused):
        handler.redirect_request(request, None, 302, "", {}, redirected.full_url)


@pytest.mark.parametrize("url", ["http://store.blob.core.windows.net/x", "https://example.com/x",
    "https://store.blob.core.windows.net.attacker.test/x", "https://u:p@store.blob.core.windows.net/x",
    "https://store.blob.core.windows.net:444/x", "https://store.blob.core.windows.net/x#fragment"])
def test_redirect_refuses_nonclosed_storage_origins(url):
    selected = W.endpoint(pin()) + "/zip"
    handler = W.ClosedRedirect(selected, frozenset((selected,)))
    with pytest.raises(W.Refused):
        handler.redirect_request(urllib.request.Request(selected), None, 302, "", {}, url)


@pytest.mark.parametrize("code,selected_allowed,request_alias", [(301, True, False), (307, True, False),
    (302, False, False), (302, True, True)])
def test_redirect_refuses_status_selection_or_request_aliases(code, selected_allowed, request_alias):
    selected = W.endpoint(pin()) + "/zip"
    handler = W.ClosedRedirect(selected, frozenset((selected,)) if selected_allowed else frozenset())
    request = urllib.request.Request(selected + ("?alias=1" if request_alias else ""))
    with pytest.raises(W.Refused):
        handler.redirect_request(request, None, code, "", {}, "https://store.blob.core.windows.net/x")


def test_redirect_handler_closes_response_when_location_refused():
    selected = W.endpoint(pin()) + "/zip"
    request = urllib.request.Request(selected)
    response = Response()
    handler = W.ClosedRedirect(selected, frozenset((selected,)))
    with pytest.raises(W.Refused):
        handler.http_error_302(request, response, 302, "", {"Location": "bad location"})
    assert response.closed


@pytest.mark.parametrize("headers", [{"Content-Length": "4"}, {"Content-Length": "-1"},
    {"Content-Length": " 3"}, {"Content-Length": "٣"}, {"Content-Length": 3},
    {"Content-Length": "9" * 21}, {"Content-Encoding": "gzip"}])
def test_transport_headers_reject_wrong_size_encoding_or_untyped_lengths(headers):
    with pytest.raises(W.Refused):
        W.check_length(headers, 3, exact=True)


def test_transport_headers_allow_absent_length_and_exact_identity():
    W.check_length({}, 3, exact=True)
    W.check_length({"Content-Length": "3", "Content-Encoding": "identity"}, 3, exact=True)
    W.check_length({"Content-Length": "2"}, 3)


def test_stream_download_checks_exact_eof_hash_and_every_bounded_read():
    response, selected, writes, budget = Response(headers={"Content-Length": "3"}), pin(), [], Budget()
    result = W.stream_download(response, selected, lambda data: writes.append(data) or len(data), budget.check)
    assert result == dict(artifact_id=selected.artifact_id, bytes=3, sha256=selected.sha256)
    assert b"".join(writes) == b"abc" and response.reads == [4, 1]
    assert budget.calls == 5


@pytest.mark.parametrize("data,sha", [(b"ab", None), (b"abcd", None), (b"abc", "b" * 64)])
def test_stream_download_refuses_early_eof_overrun_or_digest_drift(data, sha):
    response, selected = Response(data), pin(**({} if sha is None else {"sha256": sha}))
    with pytest.raises(W.Refused):
        W.stream_download(response, selected, lambda raw: len(raw), Budget().check)


def test_stream_download_refuses_partial_write_without_another_read():
    response = Response()
    with pytest.raises(W.Refused):
        W.stream_download(response, pin(), lambda raw: len(raw) - 1, Budget().check)
    assert response.reads == [4]


def test_stream_download_propagates_cancellation_before_writing():
    class Cancelled(Exception): pass
    response, writes, calls = Response(), [], []
    def check():
        calls.append(True)
        if len(calls) == 2: raise Cancelled()
    with pytest.raises(Cancelled):
        W.stream_download(response, pin(), lambda raw: writes.append(raw) or len(raw), check)
    assert writes == [] and response.reads == [4]


def test_stream_download_refuses_nonbytes_or_reader_overrun():
    class Bad(Response):
        def read1(self, count): return "abc"
    with pytest.raises(W.Refused):
        W.stream_download(Bad(), pin(), lambda raw: len(raw), Budget().check)
    class Overrun(Response):
        def read1(self, count): return b"abcde"
    with pytest.raises(W.Refused):
        W.stream_download(Overrun(), pin(), lambda raw: len(raw), Budget().check)


def client_fixture(*, status=200, final_url=None, headers=None, error=None, follow=False, data=b"abc"):
    selected_pins, captured, budget = pins(), [], Budget()
    def factory(handler):
        class Opener:
            def open(self, request, timeout):
                captured.append((request, timeout, handler))
                if error is not None: raise error
                url = request.full_url
                if follow:
                    redirected = handler.redirect_request(request, None, 302, "", {},
                        "https://store.blob.core.windows.net/file?sig=synthetic")
                    captured.append((redirected, timeout, handler))
                    url = redirected.full_url
                return Response(data, url=final_url or url, status=status, headers=headers)
        return Opener()
    client = W.ClosedClient("synthetic-secret", selected_pins, budget, opener_factory=factory)
    return client, captured, budget


def test_closed_client_uses_only_registered_metadata_and_checks_before_after():
    client, captured, budget = client_fixture()
    endpoint = W.endpoint(pins()[0])
    with client.response(endpoint) as response:
        assert response.geturl() == endpoint
    request, timeout, _ = captured[0]
    assert request.get_header("Authorization") == "Bearer synthetic-secret" and timeout == 15
    assert response.closed and budget.calls == 3
    with pytest.raises(W.Refused):
        with client.response(endpoint + "?alias=1"): pass
    assert len(captured) == 1


def test_closed_client_metadata_returns_strict_bounded_object():
    client, _, budget = client_fixture(data=b'{"x":1}', headers={"Content-Length": "7"})
    assert client.metadata(W.endpoint(pins()[0])) == {"x": 1}
    assert budget.calls >= 7


@pytest.mark.parametrize("headers", [{}, {"Content-Length": "9"}])
def test_closed_client_metadata_refuses_header_or_stream_overrun_before_parsing(monkeypatch, headers):
    monkeypatch.setattr(W, "MAX_API", 8)
    client, _, _ = client_fixture(data=b"123456789", headers=headers)
    with pytest.raises(W.Refused):
        client.metadata(W.endpoint(pins()[0]))


@pytest.mark.parametrize("raw", [b'{"x":1,"x":2}', b"[]", b"null", b"1", b"true",
    b'{"x":NaN}', b'{"x":Infinity}', b'{"x":1e999}', b"\xff"])
def test_closed_client_metadata_refuses_duplicate_keys_nonobjects_and_nonfinite_json(raw):
    client, _, _ = client_fixture(data=raw)
    with pytest.raises(ERRORS):
        client.metadata(W.endpoint(pins()[0]))


def test_closed_client_zip_requires_actual_single_redirect_and_strips_credentials():
    client, captured, _ = client_fixture(follow=True)
    endpoint = W.endpoint(pins()[0]) + "/zip"
    with client.response(endpoint, zip_input=True): pass
    assert len(captured) == 2
    assert captured[0][0].get_header("Authorization") == "Bearer synthetic-secret"
    assert captured[1][0].get_header("Authorization") is None
    no_redirect, _, _ = client_fixture(final_url="https://store.blob.core.windows.net/file")
    with pytest.raises(W.Refused):
        with no_redirect.response(endpoint, zip_input=True): pass


@pytest.mark.parametrize("options", [dict(status=201), dict(final_url="https://api.github.com/alias"),
    dict(headers={"Link": "next-page"})])
def test_closed_client_refuses_metadata_status_redirect_alias_or_pagination(options):
    client, _, _ = client_fixture(**options)
    with pytest.raises(W.Refused):
        with client.response(W.endpoint(pins()[0])): pass


@pytest.mark.parametrize("error,code", [(urllib.error.HTTPError("https://api.github.com/synthetic", 403, "denied", {}, None), "http_refused"),
    (urllib.error.URLError("synthetic"), "transport_failed"), (TimeoutError(), "transport_failed")])
def test_closed_client_maps_transport_failures_to_fixed_codes_without_text(error, code):
    client, _, _ = client_fixture(error=error)
    with pytest.raises(W.Refused) as caught:
        with client.response(W.endpoint(pins()[0])): pass
    assert caught.value.code == code and str(caught.value) == code
    assert "synthetic" not in str(caught.value)


@pytest.mark.parametrize("token", [None, "", "contains whitespace", "newline\n"])
def test_closed_client_refuses_untyped_or_whitespace_credentials_without_opening(token):
    def forbidden(*_): pytest.fail("opener must remain unused")
    with pytest.raises(W.Refused):
        W.ClosedClient(token, pins(), Budget(), opener_factory=forbidden)


@pytest.mark.parametrize("filled", [False, True])
def test_pending_registration_and_main_refuse_before_any_input_work(monkeypatch, filled):
    for name in ("REVIEWED_OUTPUTS", "REVIEWED_CLOSURES", "REVIEWED_OUTCOMES",
        "REVIEWED_RESOURCE_POLICY", "REVIEWED_COMPLETION"):
        monkeypatch.setattr(W, name, {} if filled else None)
    def forbidden(*_, **__): pytest.fail("pending actual frontend touched input work")
    for name in ("ClosedClient", "staging_admission", "audit_archive", "closed_inputs"):
        monkeypatch.setattr(W, name, forbidden)
    for entry in (W.registration, W.main):
        with pytest.raises(W.Refused) as caught:
            entry()
        assert caught.value.code == "pending_publication"


def test_refusal_codes_are_closed_and_never_arbitrary_exception_text():
    assert W.Refused("http_refused").code == "http_refused"
    with pytest.raises(ValueError, match="unregistered refusal code"):
        W.Refused("private failure details")
