"""Tiny source-only contracts; no real archive, checkpoint or World fixtures."""
from __future__ import annotations

import ast
import hashlib
import importlib.util
import io
import json
import pickle
from pathlib import Path
import stat
import struct
import sys

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


@pytest.fixture
def reader(monkeypatch):
    monkeypatch.syspath_prepend(str(SCRIPTS))
    name = "_four_header_contract_reader"
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / "wealth_floor_checkpoint_header_diagnostic.py")
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, module)
    spec.loader.exec_module(module)
    return module


class Budget:
    def __init__(self):
        self.checks = 0
    def check(self):
        self.checks += 1


class TinySparse:
    """Virtual high offsets; patches and every read remain below 1 MiB."""
    def __init__(self, size, patches):
        assert sum(len(raw) for _, raw in patches) < 1024**2
        self.size, self.patches, self.pos = size, patches, 0
        self.max_read = 0
    def seek(self, position):
        assert 0 <= position <= self.size
        self.pos = position
    def read(self, count):
        assert 0 <= count < 1024**2
        self.max_read = max(self.max_read, count)
        end = min(self.size, self.pos + count)
        data = bytearray(end - self.pos)
        for offset, raw in self.patches:
            left, right = max(self.pos, offset), min(end, offset + len(raw))
            if left < right:
                data[left - self.pos:right - self.pos] = raw[left - offset:right - offset]
        self.pos = end
        return bytes(data)


def central(name="raw/one.ckpt", *, size=7, local=0, flags=0, method=0, disk=0, mode=stat.S_IFREG, extra=b""):
    raw = name.encode("utf-8")
    return struct.pack("<4s6H3L5H2L", b"PK\x01\x02", 45, 45, flags, method, 0, 0,
        0, size, size, len(raw), len(extra), 0, disk, 0, mode << 16, local) + raw + extra


def footer_stream(records, *, zip64=False, count=None, central_offset=None):
    cd = b"".join(records)
    count = len(records) if count is None else count
    offset = central_offset if central_offset is not None else (4_500_000_000 if zip64 else 4_000_000_000)
    if zip64:
        record = struct.pack("<4sQ2H2L4Q", b"PK\x06\x06", 44, 45, 45, 0, 0, count, count, len(cd), offset)
        locator = struct.pack("<4sLQL", b"PK\x06\x07", 0, offset + len(cd), 1)
        end = struct.pack("<4s4H2LH", b"PK\x05\x06", 0, 0, 65535, 65535, 0xffffffff, 0xffffffff, 0)
        tail = cd + record + locator + end
    else:
        tail = cd + struct.pack("<4s4H2LH", b"PK\x05\x06", 0, 0, count, count, len(cd), offset, 0)
    return TinySparse(offset + len(tail), [(offset, tail)])


def header():
    return {
        "format": "chronicler-run-checkpoint", "version": 1, "exact": True,
        "seed": 48, "turn": 201, "start_turn": 0, "num_turns": 500,
        "world": {"regions": 8, "civilizations": 4},
        "run_config": {"agent_mode": "hybrid", "validation_sidecar": True},
        "identity": {}, "lineage": [],
        "sections": [
            {"name": "python", "codec": "opaque", "offset": 0, "length": 1, "raw_length": 99, "sha256": "0" * 64},
            {"name": "native.agent.0", "codec": "opaque", "offset": 1, "length": 2, "raw_length": 999, "sha256": "1" * 64},
        ],
    }


def prefix(reader, value=None, *, raw=None):
    value = header() if value is None else value
    raw = json.dumps(value, separators=(",", ":")).encode() if raw is None else raw
    return reader.MAGIC + struct.pack("<I", len(raw)) + raw


def pins(reader):
    return tuple(reader.HeaderArchivePin(w, artifact, f"wealth-outcome-full-{w}-failed-checkpoints-40860233409-1", size, "0" * 64, "2026-11-28T11:31:19Z")
        for w, artifact, size in [("template", 12892774650, 1265097885), ("procedural", 12894081792, 4192776011)])


def test_new_volume_policy_is_separate_from_old_admission(reader):
    before = (reader.W.MAX_STAGED, reader.A.MAX_COMPRESSED_BYTES)
    result = reader.stage_admission({"disk_free_bytes": 12 * 1024**3, "ram_available_bytes": 2 * 1024**3}, pins(reader))
    assert result["compressed_bytes"] == 5457873896
    assert result["compressed_bytes"] + result["output_bytes"] + result["reserve_bytes"] == 5474651112 < 5500000000
    assert before == (2133433148, 2126779694) == (reader.W.MAX_STAGED, reader.A.MAX_COMPRESSED_BYTES)
    assert all(type(p) is reader.HeaderArchivePin and type(p) is not reader.W.InputPin for p in pins(reader))


@pytest.mark.parametrize("resources", [
    {"disk_free_bytes": 12 * 1024**3 - 1, "ram_available_bytes": 2 * 1024**3},
    {"disk_free_bytes": 12 * 1024**3, "ram_available_bytes": 2 * 1024**3 - 1},
    {"disk_free_bytes": True, "ram_available_bytes": 2 * 1024**3},
])
def test_new_volume_admission_refuses_deficits_and_bool(reader, resources):
    with pytest.raises(reader.A.AdmissionError):
        reader.stage_admission(resources, pins(reader))


@pytest.mark.parametrize("zip64", [False, True])
def test_high_offset_index_uses_only_tiny_fake_stream(reader, zip64):
    stream = footer_stream([central()], zip64=zip64)
    assert reader.header_index_preflight(stream, stream.size, {"raw/one.ckpt": 7}, Budget()) == ("raw/one.ckpt",)
    assert stream.max_read <= 65557 and sum(len(v) for _, v in stream.patches) < 1024


def test_zip64_central_offset_scalar_is_explicit(reader):
    extra = struct.pack("<HHQ", 1, 8, 4_400_000_000)
    stream = footer_stream([central(local=0xffffffff, extra=extra)], zip64=True)
    assert reader.header_index_preflight(stream, stream.size, {"raw/one.ckpt": 7}, Budget()) == ("raw/one.ckpt",)
    assert reader.zip64_values(extra, 7, 7, 0xffffffff, 0) == (7, 7, 4_400_000_000, 0)


@pytest.mark.parametrize("records,expected", [
    ([central(), central()], {"raw/one.ckpt": 7}),
    ([central("../one.ckpt")], {"raw/one.ckpt": 7}),
    ([central(size=8)], {"raw/one.ckpt": 7}),
    ([central(flags=1)], {"raw/one.ckpt": 7}),
    ([central(method=99)], {"raw/one.ckpt": 7}),
    ([central(disk=1)], {"raw/one.ckpt": 7}),
    ([central(mode=stat.S_IFLNK)], {"raw/one.ckpt": 7}),
    ([central()], {"raw/one.ckpt": 7, "missing.ckpt": 3}),
])
def test_index_refuses_alias_name_size_flag_type_and_missing_member(reader, records, expected):
    stream = footer_stream(records)
    with pytest.raises(reader.A.AdmissionError):
        reader.header_index_preflight(stream, stream.size, expected, Budget())


@pytest.mark.parametrize("extra", [b"\x01", struct.pack("<HH", 1, 8) + b"short", struct.pack("<HHQHHQ", 1, 8, 7, 1, 8, 8)])
def test_zip64_extra_refuses_truncation_and_duplicate(reader, extra):
    with pytest.raises(reader.A.AdmissionError):
        reader.zip64_values(extra, 0xffffffff, 7, 0, 0)


def test_index_refuses_truncated_footer_and_declared_count(reader):
    stream = footer_stream([central()], count=2)
    with pytest.raises(reader.A.AdmissionError):
        reader.header_index_preflight(stream, stream.size, {"raw/one.ckpt": 7}, Budget())
    with pytest.raises(reader.A.AdmissionError):
        reader.header_index_preflight(io.BytesIO(b"PK\x05\x06"), 4, {"raw/one.ckpt": 7}, Budget())
    with pytest.raises(reader.A.AdmissionError):
        reader.read_at(io.BytesIO(b"short"), 0, 10, 10, Budget())


def test_header_reads_only_prefix_and_never_inner_sections(reader, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("inner checkpoint state decoding is forbidden")
    monkeypatch.setattr(pickle, "loads", forbidden)
    monkeypatch.setattr(reader.zlib, "decompress", forbidden)
    raw = prefix(reader)
    result = reader.parse_checkpoint_prefix(raw, len(raw) + 3, Budget())
    assert result["header"] == header()
    assert result["inner_sections_inflated"] is False and result["inner_section_digests_verified"] is False
    assert result["header_json_bytes"] < 2048


@pytest.mark.parametrize("mutation", [
    lambda d: d.update(version=True),
    lambda d: d.update(seed=True),
    lambda d: d["world"].update(civilizations=True),
    lambda d: d.update(identity={"bad": float("inf")}),
    lambda d: d["sections"][1].update(offset=0),
    lambda d: d["sections"][1].update(length=-1),
    lambda d: d["sections"][1].update(name="python"),
    lambda d: d["sections"][1].update(sha256="unknown"),
])
def test_header_refuses_typed_nonfinite_and_packed_extent_faults(reader, mutation):
    value = header(); mutation(value); raw = prefix(reader, value)
    with pytest.raises(reader.A.AdmissionError):
        reader.parse_checkpoint_prefix(raw, len(raw) + 3, Budget())


def test_header_refuses_duplicate_json_and_oversized_or_partial_header(reader):
    raw_json = json.dumps(header(), separators=(",", ":")).encode().replace(b'"version":1', b'"version":1,"version":1')
    raw = prefix(reader, raw=raw_json)
    with pytest.raises(reader.A.AdmissionError):
        reader.parse_checkpoint_prefix(raw, len(raw) + 3, Budget())
    for raw in [reader.MAGIC + struct.pack("<I", 65537), reader.MAGIC + struct.pack("<I", 40) + b"{}"]:
        with pytest.raises(reader.A.AdmissionError):
            reader.parse_checkpoint_prefix(raw, 1000, Budget())
    raw = prefix(reader)
    with pytest.raises(reader.A.AdmissionError):
        reader.parse_checkpoint_prefix(raw, len(raw) + 4, Budget())


def test_old_shape_returns_individual_bits_without_validity_judgment(reader):
    value = header(); config = {"regions": 8, "civs": 4}
    assert reader.old_shape_observations(value, config)["old_compound_result"] is True
    value["world"]["civilizations"] = 5
    observed = reader.old_shape_observations(value, config)
    assert observed["old_K_predicate_bits"] == {"regions_equals_requested": True,
        "current_civilizations_equals_initial_requested": False, "agent_mode_hybrid": True,
        "validation_sidecar_true": True, "sections_exact_python_agent0": True}
    assert observed["old_compound_result"] is False and observed["current_world_counts"]["civilizations"] == 5
    assert "no legitimate/invalid civilization judgment" in observed["interpretation"]


def test_pending_registration_precedes_any_execute_or_client(reader, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("pending registration touched the runtime")
    monkeypatch.setattr(reader, "REVIEWED_HEADER_ACTIVATION", None)
    monkeypatch.setattr(reader, "execute", forbidden, raising=False)
    if hasattr(reader, "main"):
        with pytest.raises(reader.A.AdmissionError):
            reader.main(["--execute"])
    else:
        with pytest.raises(reader.A.AdmissionError):
            reader.registration()
    assert reader.REVIEWED_HEADER_ACTIVATION is None


def test_source_import_boundary_excludes_inner_state_loaders(reader):
    tree = ast.parse(Path(reader.__file__).read_bytes())
    imports = [n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
    imports += [a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names]
    assert not any(name == "pickle" or name.startswith(("chronicler", "chronicler_agents")) for name in imports)


def small_bundle():
    return {"member_index_pins": [{"path": "raw/one.ckpt", "bytes": 7, "sha256": None}],
        "selector_member": "failed-checkpoint-body-selection.json", "selector_file_bytes": 2,
        "selector_file_sha256": hashlib.sha256(b"{}").hexdigest(),
        "expected_index_files_from_selector": 2, "expected_expanded_bytes_from_selector": 9}


def test_expected_index_preserves_null_body_hash_and_full_selector_closure(reader):
    bundle = small_bundle()
    assert reader.expected_members(bundle) == {"raw/one.ckpt": 7, "failed-checkpoint-body-selection.json": 2}
    bundle["member_index_pins"][0]["sha256"] = "0" * 64
    with pytest.raises(reader.A.AdmissionError):
        reader.expected_members(bundle)


@pytest.mark.parametrize("mutation", [
    lambda d: d["member_index_pins"].append(dict(d["member_index_pins"][0])),
    lambda d: d["member_index_pins"][0].update(path="../escape.ckpt"),
    lambda d: d["member_index_pins"][0].update(bytes=True),
    lambda d: d.update(expected_expanded_bytes_from_selector=10),
    lambda d: d.update(expected_index_files_from_selector=3),
])
def test_expected_index_refuses_duplicate_alias_bool_and_bad_total(reader, mutation):
    value = small_bundle(); mutation(value)
    with pytest.raises(reader.A.AdmissionError):
        reader.expected_members(value)


class TinyResponse:
    def __init__(self, body, declared_length):
        self.body, self.position = body, 0
        self.headers = {"Content-Length": str(declared_length)}
        self.requests = []
    def read1(self, count):
        assert 0 < count <= 1024**2
        self.requests.append(count)
        raw = self.body[self.position:self.position + count]
        self.position += len(raw)
        return raw


def test_new_pin_stream_checks_compressed_whole_sha_and_eof(reader):
    body = b"tiny archive bytes"
    p = reader.HeaderArchivePin("template", 12892774650,
        "wealth-outcome-full-template-failed-checkpoints-40860233409-1", len(body), hashlib.sha256(body).hexdigest(), "2026-11-28T11:31:19Z")
    output = io.BytesIO(); response = TinyResponse(body, len(body))
    result = reader.stream_header_archive(response, p, output.write, Budget().check)
    assert result == {"artifact_id": p.artifact_id, "bytes": len(body), "sha256": hashlib.sha256(body).hexdigest()}
    assert output.getvalue() == body
    for actual, declared in [(body[:-1], len(body)), (body + b"!", len(body)), (b"X" * len(body), len(body))]:
        with pytest.raises(reader.A.AdmissionError):
            reader.stream_header_archive(TinyResponse(actual, declared), p, io.BytesIO().write, Budget().check)
    with pytest.raises(reader.W.Refused):
        reader.stream_header_archive(TinyResponse(body, len(body) + 1), p, io.BytesIO().write, Budget().check)


def test_client_new_volume_endpoint_set_never_enables_other_original_artifacts(reader):
    def forbidden(*args, **kwargs):
        pytest.fail("fixture client must not open transport")
    client = reader.HeaderClient("fixture-token", pins(reader), Budget(), current_run_id=123, opener_factory=forbidden)
    assert client.zip_endpoints == frozenset(reader.W.API + "/actions/artifacts/" + str(i) + "/zip" for i in (12892774650, 12894081792))
    assert reader.W.API + "/actions/artifacts/12893208388/zip" not in client.zip_endpoints
    assert len(client.metadata_endpoints) == 5


def tiny_header_bundle(reader, tmp_path, *, wrong_known_sha=False, selector_omission=False):
    import zipfile
    names = [f"raw/full_gate/batch_42/seed_48/checkpoint_turn_{turn}.ckpt" for turn in (101, 201)]
    cps = []
    for turn in (101, 201):
        value = header(); value["turn"] = turn
        value["identity"] = {"source": {"git_sha": reader.CANDIDATE, "package_digest": reader.PACKAGE},
            "native": {"sha256": reader.NATIVE}, "environment": {"python": "fixture"}}
        value["run_config"].update(lineage=[], resume_info=None)
        if turn == 201:
            value["world"]["civilizations"] = 5
        cps.append(prefix(reader, value) + b"bad")
    selected = [{"path": name, "bytes": len(body), "current_body_sha256": None} for name, body in zip(names, cps)]
    selector = json.dumps({"selected": selected, "omitted": ["fixture"] if selector_omission else [],
        "missing_or_already_retired": [], "selection_complete_for_remaining_verified_files": True}).encode()
    bundle = {"member_index_pins": [{"path": name, "bytes": len(body), "sha256": None} for name, body in zip(names, cps)],
        "selector_member": "failed-checkpoint-body-selection.json", "selector_file_bytes": len(selector),
        "selector_file_sha256": hashlib.sha256(selector).hexdigest(), "expected_index_files_from_selector": 3,
        "expected_expanded_bytes_from_selector": len(selector) + sum(map(len, cps))}
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(bundle["selector_member"], selector)
        for name, body in zip(names, cps):
            archive.writestr(name, body)
    raw = buffer.getvalue(); assert len(raw) < 8192
    path = tmp_path / "tiny-headers.zip"; path.write_bytes(raw)
    pin = reader.HeaderArchivePin("template", 12892774650,
        "wealth-outcome-full-template-failed-checkpoints-40860233409-1", len(raw), hashlib.sha256(raw).hexdigest(), "2026-11-28T11:31:19Z")
    targets = [{"path": name, "label": label, "seed": 48, "turn": turn, "file_bytes": len(body),
        "known_wholefile_sha256": (("f" * 64 if wrong_known_sha else hashlib.sha256(body).hexdigest()) if label == "last_valid" else None),
        "schedule_status": "synthetic fixture only"} for name, label, turn, body in zip(names, ("last_valid", "first_unvalidated"), (101, 201), cps)]
    return path, pin, bundle, targets, cps


def test_two_tiny_headers_keep_known_and_new_hash_roles_without_state_decode(reader, tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("inner checkpoint decode/extraction is forbidden")
    monkeypatch.setattr(pickle, "loads", forbidden)
    monkeypatch.setattr(reader.zlib, "decompress", forbidden)
    monkeypatch.setattr(reader.zipfile.ZipFile, "extract", forbidden)
    monkeypatch.setattr(reader.zipfile.ZipFile, "extractall", forbidden)
    path, pin, bundle, targets, cps = tiny_header_bundle(reader, tmp_path)
    emitted = []
    result = reader.inspect_bundle(path, pin, bundle, targets, Budget(), lambda *args: emitted.append(args))
    rows = result["selected_headers"]
    assert len(rows) == len(emitted) == 2
    assert rows[0]["compared_to_existing_sha"] is True and rows[1]["compared_to_existing_sha"] is False
    assert rows[0]["sha_origin"] == "original_partial_capture_journal_verified"
    assert rows[1]["existing_whole_sha256"] is None and rows[1]["sha_origin"] == "newly_observed_under_authenticated_zip"
    assert [row["file"]["sha256"] for row in rows] == [hashlib.sha256(body).hexdigest() for body in cps]
    assert rows[0]["observations"]["old_compound_result"] is True
    assert rows[1]["observations"]["old_compound_result"] is False
    assert rows[1]["observations"]["old_K_predicate_bits"]["current_civilizations_equals_initial_requested"] is False
    assert all(row["observations"]["identity_equal_last_valid"] is True for row in rows)
    assert all(row["checkpoint_state_decoded"] is False and row["physics_qualified"] is False for row in rows)
    assert result["full_payload_crc_or_physics_qualification"] is False and result["checkpoint_inner_sections_decoded"] is False
    for world, label, raw in emitted:
        assert world == "template" and label in ("last_valid", "first_unvalidated")
        value = json.loads(raw)
        assert value["format"] == "chronicler-run-checkpoint" and len(raw) < 2048
    assert list(tmp_path.iterdir()) == [path]


@pytest.mark.parametrize("fault", ["known_sha", "selector_omission", "whole_zip_change"])
def test_tiny_bundle_refuses_known_hash_selector_and_whole_zip_faults(reader, tmp_path, fault):
    path, pin, bundle, targets, _ = tiny_header_bundle(reader, tmp_path,
        wrong_known_sha=fault == "known_sha", selector_omission=fault == "selector_omission")
    if fault == "whole_zip_change":
        path.write_bytes(path.read_bytes() + b"!")
    emitted = []
    with pytest.raises(reader.A.AdmissionError):
        reader.inspect_bundle(path, pin, bundle, targets, Budget(), lambda *args: emitted.append(args))
    assert emitted == []


def test_actual_curated_policy_has_exact_known_and_unknown_hash_roles(reader):
    control = SCRIPTS.parent
    data = json.loads((control / reader.INPUT_FILE).read_bytes())
    public = json.loads((control / reader.OLD_PUBLICATIONS).read_bytes())
    plan = reader.build_plan(data, public)
    assert sum(p.size for p in plan["pins"]) == 5457873896
    assert [len(plan["expected"][w]) for w in ("template", "procedural")] == [801, 901]
    assert sum(sum(v.values()) for v in plan["expected"].values()) == 5501929345
    assert [[(t["seed"], t["turn"], t["known_wholefile_sha256"] is None) for t in plan["targets"][w]]
        for w in ("template", "procedural")] == [[(48, 101, False), (48, 201, True)], [(44, 141, False), (44, 161, True)]]
    assert all(t["selector_body_sha256"] is None for rows in plan["targets"].values() for t in rows)


@pytest.mark.parametrize("fault", ["candidate_role", "source_role", "job", "target", "unknown_sha"])
def test_actual_curated_policy_refuses_role_and_target_drift(reader, fault):
    control = SCRIPTS.parent
    data = json.loads((control / reader.INPUT_FILE).read_bytes())
    public = json.loads((control / reader.OLD_PUBLICATIONS).read_bytes())
    if fault == "candidate_role": data["candidate_identity_reference"]["source"] = data["original_control_source"]
    elif fault == "source_role": data["original_control_source"] = reader.CANDIDATE
    elif fault == "job": data["jobs"]["template"] += 1
    elif fault == "target": data["targets"]["template"][1]["turn"] += 1
    elif fault == "unknown_sha": data["targets"]["template"][1]["known_wholefile_sha256"] = "0" * 64
    with pytest.raises(reader.A.AdmissionError): reader.build_plan(data, public)


def producer_facts(reader):
    source = "a" * 40
    run = dict(id=123, run_attempt=1, head_sha=source, event="push", head_branch=reader.BRANCH,
        path=reader.WORKFLOW, status="in_progress", conclusion=None, repository={"id": reader.L.REPOSITORY_ID})
    jobs = dict(total_count=1, jobs=[dict(id=456, run_id=123, run_attempt=1, head_sha=source,
        name=reader.JOB_NAME, status="in_progress", conclusion=None)])
    return source, run, jobs


@pytest.mark.parametrize("fault", [None, "attempt", "source", "job_name", "job_run", "extra_job"])
def test_current_producer_is_exact_first_attempt_single_job(reader, fault):
    source, run, jobs = producer_facts(reader)
    if fault == "attempt": run["run_attempt"] = 2
    elif fault == "source": run["head_sha"] = "b" * 40
    elif fault == "job_name": jobs["jobs"][0]["name"] = "other"
    elif fault == "job_run": jobs["jobs"][0]["run_id"] = 999
    elif fault == "extra_job": jobs["total_count"] = 2; jobs["jobs"].append(dict(jobs["jobs"][0]))
    class Client:
        def metadata(self, url):
            return jobs if "/jobs?" in url else run
    if fault:
        with pytest.raises(reader.A.AdmissionError): reader.current_producer(Client(), 123, source)
    else:
        assert reader.current_producer(Client(), 123, source)["job_id"] == 456


def test_source_snapshot_requires_exact_active_copy_and_protected_helpers(reader, tmp_path, monkeypatch):
    root = tmp_path / "control"; root.mkdir()
    names = (*reader.SOURCE_PINS, "scripts/wealth_floor_checkpoint_header_diagnostic.py",
        reader.INPUT_FILE, reader.OLD_PUBLICATIONS, reader.TEMPLATE)
    for name in names:
        target = root / name; target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((SCRIPTS.parent / name).read_bytes())
    for module, name in ((reader.L, "wealth_floor_failed_cohort_diagnostic.py"),
        (reader.W, "wealth_floor_full_archive_audit.py"), (reader.A, "wealth_floor_baseline_admission.py"),
        (reader.R, "wealth_floor_build_resources.py"), (reader.D, "wealth_floor_hosted_deployment.py")):
        monkeypatch.setattr(module, "__file__", str(root / "scripts" / name))
    active = root / reader.WORKFLOW; active.parent.mkdir(parents=True)
    with pytest.raises(reader.A.AdmissionError): reader.source_snapshot(root, Budget())
    template = (root / reader.TEMPLATE).read_bytes(); active.write_bytes(template)
    result = reader.source_snapshot(root, Budget())
    assert result[reader.WORKFLOW] == result[reader.TEMPLATE]
    assert result[reader.TEMPLATE]["sha256"] == reader.TEMPLATE_SHA256
    active.write_bytes(template + b"# drift\n")
    with pytest.raises(reader.A.AdmissionError): reader.source_snapshot(root, Budget())
    active.unlink(); active.symlink_to(root / reader.TEMPLATE)
    with pytest.raises(reader.A.AdmissionError): reader.source_snapshot(root, Budget())


def test_late_failure_invalidates_completion_and_keeps_original_header_metadata(reader, tmp_path):
    root = tmp_path / "reader"; output = root / "diagnostic"; output.mkdir(parents=True)
    payload = b'{"observed":"original bounded header fixture"}\n'
    (output / "template-last_valid-header.json").write_bytes(payload)
    (output / "completion.json").write_bytes(b'{"header_observations_complete":true}\n')
    reader.L.retain_failure(root, reader.A.AdmissionError("private exception text"))
    assert not (output / "completion.json").exists()
    failed = json.loads((output / "failure.json").read_bytes())
    assert failed["diagnostic_complete"] is False and failed["scientific_qualification"] is False
    assert failed["worlds_admitted"] is False and "private exception text" not in json.dumps(failed)
    assert (output / "template-last_valid-header.json").read_bytes() == payload


def test_dormant_template_and_pending_source_are_separately_bound(reader):
    raw = (SCRIPTS.parent / reader.TEMPLATE).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == reader.TEMPLATE_SHA256
    assert reader.BRANCH.encode() in raw and reader.WORKFLOW.encode() in raw
    assert b"timeout-minutes: 60" in raw and b"if: always()" in raw
    assert b"/wealth-four-checkpoint-headers/diagnostic/" in raw
    assert b"/wealth-four-checkpoint-headers/archives/" not in raw
    # This source-freeze check is explicitly separate from fixture-owned NULL refusal.
    tree = ast.parse((SCRIPTS / "wealth_floor_checkpoint_header_diagnostic.py").read_bytes())
    registration = next(n for n in tree.body if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "REVIEWED_HEADER_ACTIVATION" for t in n.targets))
    assert isinstance(registration.value, ast.Constant)
    assert registration.value.value is None or reader.A.hash_shape(registration.value.value)
    assert all(v is None for v in reader.A.REVIEWED_CANDIDATE_PROOFS.values())
    assert all(getattr(reader.W, k) is None for k in ("REVIEWED_OUTPUTS", "REVIEWED_CLOSURES", "REVIEWED_OUTCOMES",
        "REVIEWED_RESOURCE_POLICY", "REVIEWED_COMPLETION"))
