"""Pure contracts; no worlds, network, native imports or copied cohort data."""
from contextlib import nullcontext
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import struct
import sys
import zipfile

import pytest

pytestmark = pytest.mark.skipif(os.name != "posix", reason="detached admission requires safe POSIX file descriptors")


@pytest.fixture(scope="module")
def admission():
    path = Path(__file__).parents[1] / "scripts/wealth_floor_baseline_admission.py"
    spec = importlib.util.spec_from_file_location("wealth_floor_admission_contract", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class Clock:
    wall = 0.0
    cpu = 0.0
    def budget(self, module, **kwargs):
        return module.Budget(wall_clock=lambda: self.wall, cpu_clock=lambda: self.cpu, **kwargs)


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def write_zip(path, members, *, omit=(), extra=()):
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as z:
        for name, raw in members.items():
            if name not in omit: z.writestr(name, raw)
        for name, raw in extra: z.writestr(name, raw)
    return path


@pytest.fixture
def sample(admission, tmp_path):
    payload = {"raw/example.bin": b"synthetic\0\xff", "logs/example.txt": b"observed\n"}
    inv = {"complete": True, "file_count": len(payload), "total_bytes": sum(map(len, payload.values())),
           "files": {n: {"bytes": len(b), "sha256": sha(b)} for n, b in payload.items()}}
    light = {n: encoded({"label": n}) for n in admission.LIGHT_NAMES}
    light["raw-inventory.json"] = encoded(inv)
    members = dict(payload)
    members.update({n: light[n] for n in ("result.json", "provenance.json", "raw-inventory.json")})
    members.update({"light/" + n: b for n, b in light.items()})
    path = write_zip(tmp_path / "old.zip", members)
    def pin(p=path):
        raw = p.read_bytes()
        return admission.ArchivePin(9, "template-candidate", len(raw), sha(raw), "2026-11-28T01:15:25Z")
    return light, members, admission.build_expected_members(light), path, pin


def test_complete_stream_has_no_extract_or_native_decode(admission, sample, monkeypatch):
    _, members, expected, path, pin = sample
    def forbidden(*args, **kwargs): pytest.fail("payload extraction forbidden")
    monkeypatch.setattr(zipfile.ZipFile, "extract", forbidden)
    monkeypatch.setattr(zipfile.ZipFile, "extractall", forbidden)
    result = admission.audit_archive(path, expected, pin(), Clock().budget(admission))
    assert result["files"] == len(members)
    assert result["payload_bytes"] == sum(map(len, members.values()))
    assert result["archive_sha256"] == sha(path.read_bytes())
    assert not any(n == "chronicler_agents" or n.startswith("chronicler_agents.") for n in sys.modules)


@pytest.mark.parametrize("attack", ["missing", "extra", "duplicate", "traversal", "symlink"])
def test_member_set_errors_refuse(admission, sample, tmp_path, attack):
    _, members, expected, _, pin = sample
    path = tmp_path / "bad.zip"
    if attack == "missing": write_zip(path, members, omit=("raw/example.bin",))
    elif attack == "symlink":
        write_zip(path, members)
        i = zipfile.ZipInfo("link"); i.create_system = 3; i.external_attr = 0o120777 << 16
        with zipfile.ZipFile(path, "a") as z: z.writestr(i, b"raw/example.bin")
    else:
        n = {"extra": "unexpected", "duplicate": "raw/example.bin", "traversal": "../escape"}[attack]
        with pytest.warns(UserWarning) if attack == "duplicate" else nullcontext():
            write_zip(path, members, extra=((n, b"injected"),))
    with pytest.raises(admission.AdmissionError): admission.audit_archive(path, expected, pin(path), Clock().budget(admission))


def test_bounded_member_reads_and_expansion(admission, sample, monkeypatch):
    _, _, expected, path, pin = sample
    original = zipfile.ZipExtFile.read
    sizes = []
    def read(stream, size=-1):
        sizes.append(size); assert 0 < size <= admission.BLOCK_BYTES
        return original(stream, size)
    monkeypatch.setattr(zipfile.ZipExtFile, "read", read)
    admission.audit_archive(path, expected, pin(), Clock().budget(admission))
    assert sizes
    with pytest.raises(admission.AdmissionError): admission.audit_archive(path, expected, pin(), Clock().budget(admission), max_payload_bytes=1)


def test_archive_mutation_during_read_is_detected(admission, sample, monkeypatch):
    _, _, expected, path, pin = sample
    frozen = pin(); original = zipfile.ZipExtFile.read; changed = []
    def read(stream, size=-1):
        raw = original(stream, size)
        if not changed:
            with path.open("ab") as f: f.write(b"late change")
            changed.append(True)
        return raw
    monkeypatch.setattr(zipfile.ZipExtFile, "read", read)
    with pytest.raises(admission.AdmissionError): admission.audit_archive(path, expected, frozen, Clock().budget(admission))


@pytest.mark.parametrize("clock", ["wall", "cpu"])
def test_clock_limits_are_distinct(admission, clock):
    c = Clock(); budget = c.budget(admission)
    setattr(c, clock, 901 if clock == "cpu" else 1801)
    with pytest.raises(admission.AdmissionError): budget.check()


def origin(module):
    return dict(arm="candidate", source_sha=module.OLD_SOURCE, control_sha=module.OLD_CONTROL,
                native_sha256=module.OLD_NATIVE, github_run_id=str(module.OLD_RUN), github_run_attempt="1",
                execution_complete=True, identities_stable=True, qualified=True, gate_pass=True,
                stage="full", worldgen="template")


@pytest.mark.parametrize("field,value", [("arm", "baseline"), ("source_sha", "0"*40), ("native_sha256", "0"*64),
                                        ("github_run_id", "2"), ("github_run_attempt", "2"), ("execution_complete", False)])
def test_origin_is_closed(admission, field, value):
    r = origin(admission); admission.validate_origin(r, "template"); r[field] = value
    with pytest.raises(admission.AdmissionError): admission.validate_origin(r, "template")


def test_expired_or_substituted_publication_refuses(admission, sample):
    _, _, _, _, pin = sample; p = pin(); now = datetime(2026, 10, 29, tzinfo=timezone.utc)
    m = dict(id=p.artifact_id, name="full-gates-raw-candidate-template-40791402289-1", size_in_bytes=p.size,
             digest="sha256:"+p.sha256, expired=False, expires_at=p.expires_at,
             workflow_run=dict(id=admission.OLD_RUN, head_sha=admission.OLD_CONTROL))
    admission.validate_publication(m, p, now)
    with pytest.raises(admission.AdmissionError): admission.validate_publication(m, p, now+timedelta(days=40))
    m["workflow_run"]["head_sha"] = "0"*40
    with pytest.raises(admission.AdmissionError): admission.validate_publication(m, p, now)


def test_partial_old_reader_result_has_no_authority(admission, tmp_path):
    p = tmp_path / "comparison.json"; p.write_bytes(encoded({"pipeline_qualified": True}))
    with pytest.raises(admission.AdmissionError): admission.read_original_comparison(p)


def test_unknown_candidate_proofs_refuse(admission):
    with pytest.raises(admission.AdmissionError, match="unreviewed"): admission.require_candidate_world_admission({})


@pytest.mark.parametrize("field,value", [("entries", 100001), ("central_size", 64*1024**2+1)])
def test_index_admission_precedes_zipfile_allocation(admission, sample, tmp_path, monkeypatch, field, value):
    _, _, expected, path, pin = sample
    raw = bytearray(path.read_bytes()); e = len(raw)-22
    if field == "entries": struct.pack_into("<H", raw, e+10, 65535)
    else: struct.pack_into("<L", raw, e+12, value)
    bad = tmp_path / "index.zip"; bad.write_bytes(raw)
    def forbidden(*args, **kwargs): pytest.fail("unsafe central directory reached ZipFile")
    monkeypatch.setattr(zipfile, "ZipFile", forbidden)
    with pytest.raises(admission.AdmissionError): admission.audit_archive(bad, expected, pin(bad), Clock().budget(admission))


def zip64(raw, *, entries=None, bad_offset=False):
    e = struct.unpack("<4s4H2LH", raw[-22:]); position = len(raw)-22
    count = e[4] if entries is None else entries
    end64 = struct.pack("<4sQ2H2L4Q", b"PK\x06\x06", 44, 45, 45, 0, 0, count, count, e[5], e[6])
    locator = struct.pack("<4sLQL", b"PK\x06\x07", 0, len(raw)+999 if bad_offset else position, 1)
    end = struct.pack("<4s4H2LH", b"PK\x05\x06", 0, 0, 65535, 65535, 0xffffffff, 0xffffffff, 0)
    return raw[:-22] + end64 + locator + end


def test_small_valid_zip64_is_admitted(admission, sample, tmp_path):
    _, _, expected, path, pin = sample
    target = tmp_path/"zip64.zip"; target.write_bytes(zip64(path.read_bytes()))
    admission.audit_archive(target, expected, pin(target), Clock().budget(admission))


@pytest.mark.parametrize("attack", ["zip64-count", "zip64-offset", "truncated", "actual-count", "bad-header"])
def test_broken_index_is_rejected_before_zipfile(admission, sample, tmp_path, monkeypatch, attack):
    _, _, expected, path, pin = sample; raw = path.read_bytes()
    if attack == "zip64-count": raw = zip64(raw, entries=100001)
    elif attack == "zip64-offset": raw = zip64(raw, bad_offset=True)
    elif attack == "truncated": raw = raw[:-8]
    else:
        value = bytearray(raw); e = len(value)-22
        if attack == "actual-count":
            count = struct.unpack_from("<H", value, e+10)[0]+1
            struct.pack_into("<HH", value, e+8, count, count)
        else:
            offset = struct.unpack_from("<L", value, e+16)[0]; value[offset] = 0
        raw = bytes(value)
    target = tmp_path/"bad-index.zip"; target.write_bytes(raw)
    monkeypatch.setattr(zipfile, "ZipFile", lambda *_a, **_k: pytest.fail("unsafe index allocated"))
    with pytest.raises(admission.AdmissionError): admission.audit_archive(target, expected, pin(target), Clock().budget(admission))


@pytest.mark.parametrize("name", ["./alias", "/absolute", "a/../escape", "a\\alias", "C:/drive"])
def test_noncanonical_original_names_refuse(admission, sample, tmp_path, name):
    _, members, expected, _, pin = sample
    path = write_zip(tmp_path/"name.zip", members, extra=((name, b"extra"),))
    with pytest.raises(admission.AdmissionError): admission.audit_archive(path, expected, pin(path), Clock().budget(admission))


def test_embedded_nul_central_name_never_reaches_zipfile(admission, sample, tmp_path, monkeypatch):
    _, _, expected, path, pin = sample; raw = bytearray(path.read_bytes())
    central = raw.find(b"PK\x01\x02"); raw[central+46] = 0
    target = tmp_path/"nul.zip"; target.write_bytes(raw)
    monkeypatch.setattr(zipfile, "ZipFile", lambda *_a, **_k: pytest.fail("NUL normalized by ZipFile"))
    with pytest.raises(admission.AdmissionError): admission.audit_archive(target, expected, pin(target), Clock().budget(admission))


def test_prefix_file_directory_conflict_refuses(admission, sample):
    _, _, expected, path, pin = sample
    altered = dict(expected); altered["raw"] = admission.FilePin(0, sha(b""))
    with pytest.raises(admission.AdmissionError): admission.audit_archive(path, altered, pin(), Clock().budget(admission))


def test_same_physical_zip_cannot_supply_both_cohorts(admission, sample, tmp_path):
    _, _, _, path, _ = sample; alias = tmp_path/"alias.zip"; os.link(path, alias)
    with pytest.raises(admission.AdmissionError): admission.validate_archive_paths({"template":path,"procedural":alias})


def test_forged_plan_cannot_claim_completed_original_reader(admission, tmp_path):
    forged = {"template":{},"procedural":{}}
    with pytest.raises(admission.AdmissionError, match="validated baseline plan"):
        admission.audit_baseline(forged, {}, {}, tmp_path/"result.json", control_sha="1"*40,run_id=2,job_id=3)
    assert not (tmp_path/"result.json").exists()


def test_unexpected_light_tree_is_refused_without_descent(admission, tmp_path, monkeypatch):
    (tmp_path/"unexpected").mkdir(); (tmp_path/"unexpected"/"nested").mkdir()
    monkeypatch.setattr(Path,"rglob",lambda *_a,**_k: pytest.fail("unbounded traversal"))
    with pytest.raises(admission.AdmissionError,match="unexpected light entry"):
        admission.closed_light_inventory(tmp_path,Clock().budget(admission))


def test_fifo_swap_is_nonblocking_and_never_read(admission, tmp_path, monkeypatch):
    path=tmp_path/"evidence.json";path.write_bytes(b"{}");original=os.open;swapped=[]
    def opening(name,flags,*args,**kwargs):
        if name==path.name and not swapped:
            assert flags&os.O_NONBLOCK and flags&os.O_NOFOLLOW
            path.unlink();os.mkfifo(path);swapped.append(True)
        return original(name,flags,*args,**kwargs)
    monkeypatch.setattr(os,"open",opening)
    with pytest.raises(admission.AdmissionError):admission.bounded_read(path,100,Clock().budget(admission))
    assert swapped


def test_budget_expiry_during_serialization_never_writes_receipt(admission,tmp_path,monkeypatch):
    clock=Clock();budget=clock.budget(admission);original=admission.json_bytes
    def delayed(value):
        raw=original(value);clock.cpu=901;return raw
    monkeypatch.setattr(admission,"json_bytes",delayed)
    path=tmp_path/"receipt.json"
    with pytest.raises(admission.AdmissionError):admission.publish_pending_receipt({"status":"audit_complete_pending_job"},path,budget)
    assert not path.exists()


def test_late_fsync_leaves_only_non_authoritative_pending_receipt(admission,tmp_path,monkeypatch):
    clock=Clock();budget=clock.budget(admission);original=os.fsync
    def delayed(fd):original(fd);clock.wall=1801
    monkeypatch.setattr(os,"fsync",delayed);path=tmp_path/"receipt.json"
    with pytest.raises(admission.AdmissionError):admission.publish_pending_receipt({"status":"audit_complete_pending_job"},path,budget)
    receipt=json.loads(path.read_bytes());assert receipt["status"]=="audit_complete_pending_job" and "qualified" not in receipt
    digest=sha(admission.json_bytes(receipt))
    with pytest.raises(admission.AdmissionError):
        admission.validate_completed_job(receipt,{"conclusion":"failure"},receipt_sha256=digest,expected_receipt_sha256=digest,control_sha="1"*40)


def bridge(module):
    context=dict(unknown=[],rustc="1.99.1",cargo="1.99.1",maturin="1.15.0",uv="0.13.6",target="x86_64-unknown-linux-gnu",
                 flags={k:None for k in ["RUSTFLAGS","CARGO_ENCODED_RUSTFLAGS","RUSTDOCFLAGS","CARGO_BUILD_TARGET"]},
                 linker=dict(version="recorded tool",executable_sha256="1"*64))
    digest=sha(module.json_bytes(context))
    return dict(mode="common_context_exact_rebuild",baseline_source=module.OLD_SOURCE,baseline_crate=module.OLD_CRATE,
                candidate_source=module.CANDIDATE_SOURCE,candidate_crate=module.CANDIDATE_CRATE,
                context=context,baseline_context_sha256=digest,candidate_context_sha256=digest,
                rebuilt_baseline_native_sha256=module.OLD_NATIVE,candidate_native_sha256="2"*64)


def test_build_bridge_matches_original_bytes_or_requires_fresh_worlds(admission):
    proof=bridge(admission);admission.validate_build_bridge(proof)
    proof["rebuilt_baseline_native_sha256"]="0"*64
    with pytest.raises(admission.AdmissionError,match="fresh baseline worlds"):admission.validate_build_bridge(proof)


@pytest.mark.parametrize("unknown",["RUSTFLAGS","linker"])
def test_matching_compiler_versions_do_not_prove_unknown_context(admission,unknown):
    proof=bridge(admission);proof["context"]["unknown"]=[unknown]
    with pytest.raises(admission.AdmissionError):admission.validate_build_bridge(proof)


@pytest.mark.parametrize("attack",["payload-hash","crc","indexed-size"])
def test_exact_member_hash_crc_and_indexed_size(admission,sample,tmp_path,attack):
    _,members,expected,path,pin=sample
    if attack=="payload-hash":
        changed=dict(members);changed["raw/example.bin"]=b"X"*len(changed["raw/example.bin"])
        target=write_zip(tmp_path/"changed.zip",changed)
    else:
        raw=bytearray(path.read_bytes())
        if attack=="crc":raw[raw.find(b"synthetic")]=ord("X")
        else:
            central=raw.find(b"PK\x01\x02");size=struct.unpack_from("<L",raw,central+24)[0]
            struct.pack_into("<L",raw,central+24,size+1)
        target=tmp_path/"corrupt.zip";target.write_bytes(raw)
    with pytest.raises(admission.AdmissionError):admission.audit_archive(target,expected,pin(target),Clock().budget(admission))


def test_metadata_parse_charges_time_after_decode(admission,monkeypatch):
    clock=Clock();budget=clock.budget(admission);original=admission.json.loads
    def delayed(*args,**kwargs):
        value=original(*args,**kwargs);clock.wall=1801;return value
    monkeypatch.setattr(admission.json,"loads",delayed)
    with pytest.raises(admission.AdmissionError):admission.parse_json(b'{"value":1}',budget)


def test_decompression_charge_rejects_mid_member_expiry(admission,sample,monkeypatch):
    _,_,expected,path,pin=sample;clock=Clock();budget=clock.budget(admission);original=zipfile.ZipExtFile.read
    def delayed(*args,**kwargs):
        raw=original(*args,**kwargs);clock.cpu=901;return raw
    monkeypatch.setattr(zipfile.ZipExtFile,"read",delayed)
    with pytest.raises(admission.AdmissionError):admission.audit_archive(path,expected,pin(),budget)


def test_completed_job_attestation_and_exact_receipt_bytes_are_both_required(admission):
    receipt=dict(status="audit_complete_pending_job",old_run_id=admission.OLD_RUN,old_control_sha=admission.OLD_CONTROL,
                 old_source_sha=admission.OLD_SOURCE,original_comparison_sha256=admission.OLD_COMPARISON,
                 producer=dict(control_sha="1"*40,run_id=2,job_id=3))
    job=dict(id=3,run_id=2,head_sha="1"*40,status="completed",conclusion="success")
    digest=sha(admission.json_bytes(receipt))
    admission.validate_completed_job(receipt,job,receipt_sha256=digest,expected_receipt_sha256=digest,control_sha="1"*40)
    for conclusion in [None,"failure","cancelled"]:
        changed=dict(job,conclusion=conclusion)
        with pytest.raises(admission.AdmissionError):admission.validate_completed_job(receipt,changed,receipt_sha256=digest,expected_receipt_sha256=digest,control_sha="1"*40)
    receipt["producer"]["job_id"]=4
    with pytest.raises(admission.AdmissionError):admission.validate_completed_job(receipt,job,receipt_sha256=digest,expected_receipt_sha256=digest,control_sha="1"*40)


@pytest.mark.parametrize("kind",["compressed","expanded"])
def test_aggregate_storage_and_expansion_bounds_are_independent(admission,kind):
    size=admission.MAX_COMPRESSED_BYTES+1 if kind=="compressed" else 1
    payload=admission.MAX_AGGREGATE_PAYLOAD+1 if kind=="expanded" else 1
    pin=admission.ArchivePin(9,"template-candidate",size,"0"*64,"2026-11-28T01:15:25Z")
    rows={"toy":dict(pin=pin,members={"x":admission.FilePin(payload,"1"*64)})}
    with pytest.raises(admission.AdmissionError):admission.validate_aggregate_bounds(rows)
