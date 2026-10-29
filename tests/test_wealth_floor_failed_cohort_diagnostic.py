"""Pure incomplete-cohort forensic contracts; no real archive/network/World."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import stat
import zipfile

import pytest

import wealth_floor_failed_cohort_diagnostic as S


NOW = datetime(2026, 10, 29, 12, 0, tzinfo=timezone.utc)
SOURCE = "a" * 40


def publications():
    raw = json.loads((Path(__file__).parents[1] / S.PUBLICATION_FILE).read_bytes())
    return raw["artifacts"]


def origin():
    run = dict(id=S.W.PRODUCER_RUN, run_attempt=1, head_sha=S.W.PRODUCER_SOURCE,
        event="push", head_branch="lead/cloud-wealth-floor-outcome-cohort-20261029",
        path=".github/workflows/wealth-floor-outcome-cohort.yml", status="completed",
        conclusion="failure", repository=dict(id=S.REPOSITORY_ID))
    jobs = dict(total_count=2, jobs=[dict(id=job, run_id=S.W.PRODUCER_RUN, run_attempt=1,
        head_sha=S.W.PRODUCER_SOURCE, name=f"cohort ({world})", status="completed", conclusion="failure")
        for world, job in S.W.PRODUCER_JOBS.items()])
    pins = publications()
    return run, jobs, dict(total_count=10, artifacts=deepcopy(pins)), pins


def test_closed_original_ten_outputs_include_bodies_only_as_metadata():
    args = origin(); result = S.validate_origin(*args, now=NOW)
    assert result["run_id"] == 40860233409 and len(result["artifact_ids"]) == 10
    assert result["effective_earliest_expires_at"] == S.ORIGINAL_CUTOFF
    assert result["original_retention_extended"] is False
    raws = []
    for world in ("template", "procedural"):
        p = next(x for x in args[3] if f"-{world}-raw-" in x["name"])
        raws.append(S.W.InputPin(world, "raw", p["id"], p["name"], p["size_in_bytes"], p["digest"][7:], p["expires_at"]))
    client = S.DiagnosticClient("synthetic", tuple(raws), S.A.Budget())
    assert sum(p.size for p in raws) == S.EXPECTED_STAGED <= S.W.MAX_STAGED
    assert len(client.zip_endpoints) == 2
    assert all("12894081792" not in value and "12892774650" not in value for value in client.zip_endpoints)


@pytest.mark.parametrize("case", ["source", "attempt", "conclusion", "path", "branch", "job-missing",
    "job-attempt", "job-conclusion", "job-name", "artifact-missing", "artifact-duplicate", "artifact-expired",
    "artifact-origin", "artifact-bytes", "artifact-digest", "artifact-expiry", "retention"])
def test_original_origin_refuses_drift_and_lost_retention(case):
    run, jobs, artifacts, pins = origin(); now = NOW
    if case == "source": run["head_sha"] = SOURCE
    elif case == "attempt": run["run_attempt"] = 2
    elif case == "conclusion": run["conclusion"] = "success"
    elif case == "path": run["path"] = ".github/workflows/other.yml"
    elif case == "branch": run["head_branch"] = "main"
    elif case == "job-missing": jobs["jobs"].pop()
    elif case == "job-attempt": jobs["jobs"][0]["run_attempt"] = 2
    elif case == "job-conclusion": jobs["jobs"][0]["conclusion"] = "success"
    elif case == "job-name": jobs["jobs"][0]["name"] = "cohort (unknown)"
    elif case == "artifact-missing": artifacts["artifacts"].pop()
    elif case == "artifact-duplicate": artifacts["artifacts"][0] = deepcopy(artifacts["artifacts"][1])
    elif case == "artifact-expired": artifacts["artifacts"][0]["expired"] = True
    elif case == "artifact-origin": artifacts["artifacts"][0]["workflow_run"]["head_sha"] = SOURCE
    elif case == "artifact-bytes": artifacts["artifacts"][0]["size_in_bytes"] += 1
    elif case == "artifact-digest": artifacts["artifacts"][0]["digest"] = "sha256:" + "a" * 64
    elif case == "artifact-expiry": artifacts["artifacts"][0]["expires_at"] = "2026-11-29T11:31:00Z"
    else: now = datetime(2026, 11, 28, 1, 15, 25, tzinfo=timezone.utc)
    with pytest.raises(S.A.AdmissionError): S.validate_origin(run, jobs, artifacts, pins, now=now)


def zip_bytes(*, extra=None, log=b"Traceback (most recent call last):\nProofRefused: candidate checkpoint world/runtime shape\n"):
    files = {"result.json": b'{"execution_complete":false,"qualified":false}',
        "logs/original-runner.log": log,
        "candidate-checkpoint-capture.jsonl": b'{"path":"cp","seed":42,"turn":101,"bytes":12,"sha256":"abc","strict_current_identity_matches":true}\n',
        "raw/full_gate/batch_42/batch_manifest.json": b'{"status":"complete","seeds":[42],"turns":500,"parallel_requested":2,"runs":[{"seed":42,"dir":"seed_42","total_turns":500}]}'}
    files.update(extra or {})
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', compression=zipfile.ZIP_STORED) as z:
        for name, raw in files.items(): z.writestr(name, raw)
    return buf.getvalue()


def archive_pin(raw):
    return S.W.InputPin("template", "raw", 101,
        f"wealth-outcome-full-template-raw-{S.W.PRODUCER_RUN}-1", len(raw),
        hashlib.sha256(raw).hexdigest(), "2026-11-28T11:32:04Z")


def test_selected_reader_has_exact_exception_and_no_payload_crc_claim(tmp_path, monkeypatch):
    raw = zip_bytes(extra={"opaque/world_payload.bin": b"opaque-world-state-not-decoded"})
    path = tmp_path / 'original.zip'; path.write_bytes(raw); tails = []
    opened = []; original = zipfile.ZipFile.open
    def observed(self, name, *args, **kwargs):
        opened.append(name.filename if isinstance(name, zipfile.ZipInfo) else name)
        return original(self, name, *args, **kwargs)
    monkeypatch.setattr(zipfile.ZipFile, 'open', observed)
    result = S.inspect_archive(path, archive_pin(raw), S.A.Budget(), emit_tail=tails.append)
    assert "opaque/world_payload.bin" not in opened
    assert result["whole_index_files"] == 5 and len(result["selected"]) == 4
    assert result["complete_member_CRC_or_payload_audit"] is False
    assert result["scientific_qualification"] is result["checkpoint_body_decode"] is False
    log = result["observations"]["logs/original-runner.log"]
    assert log["exception_lines"] == ["ProofRefused: candidate checkpoint world/runtime shape"]
    assert b"candidate checkpoint world/runtime shape" in tails[0]
    batch = result["observations"]["raw/full_gate/batch_42/batch_manifest.json"]
    assert batch["status"] == "complete" and batch["run_count"] == 1
    assert batch["declared_runs"] == [dict(seed=42, dir='seed_42', total_turns=500)]


def test_whole_zip_hash_refuses_before_index_allocation(tmp_path, monkeypatch):
    raw = zip_bytes(); path = tmp_path / 'original.zip'; path.write_bytes(raw + b'x')
    monkeypatch.setattr(S.zipfile, 'ZipFile', lambda *_: pytest.fail('ZipFile allocated before whole identity'))
    with pytest.raises(S.A.AdmissionError): S.inspect_archive(path, archive_pin(raw), S.A.Budget(), emit_tail=lambda _: None)


@pytest.mark.parametrize("extra", [{"raw/full_gate/batch_42/seed_42/checkpoint_turn_101.ckpt": b"not-decoded"},
    {"progress-segments/segment-099.jsonl": b'{}\n'}, {"prefix": b"x", "prefix/child": b"x"}])
def test_index_refuses_cp_bodies_unregistered_segments_and_prefix_aliases(tmp_path, extra):
    raw = zip_bytes(extra=extra); path = tmp_path / 'original.zip'; path.write_bytes(raw)
    with pytest.raises(S.A.AdmissionError): S.inspect_archive(path, archive_pin(raw), S.A.Budget(), emit_tail=lambda _: None)


def test_whole_expanded_cap_precedes_member_reads(tmp_path, monkeypatch):
    raw = zip_bytes(); path = tmp_path / 'original.zip'; path.write_bytes(raw)
    monkeypatch.setattr(S.A, 'MAX_PAYLOAD_BYTES', 1)
    monkeypatch.setattr(zipfile.ZipFile, 'open', lambda *_a, **_k: pytest.fail('body opened before expanded admission'))
    with pytest.raises(S.A.AdmissionError): S.inspect_archive(path, archive_pin(raw), S.A.Budget(), emit_tail=lambda _: None)


def test_selected_crc_failure_is_not_promoted(tmp_path):
    raw = zip_bytes(); changed = bytearray(raw)
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        info = z.getinfo('logs/original-runner.log')
        offset = info.header_offset + 30 + len(info.filename.encode()) + len(info.extra)
    changed[offset] ^= 1
    raw = bytes(changed); path = tmp_path / 'corrupt-selected.zip'; path.write_bytes(raw)
    with pytest.raises(zipfile.BadZipFile):
        S.inspect_archive(path, archive_pin(raw), S.A.Budget(), emit_tail=lambda _: pytest.fail('corrupt log emitted'))


def test_selected_journal_requires_newlines_and_strict_objects():
    with pytest.raises(S.A.AdmissionError): S.summarize('progress.jsonl', b'{"event":"x"}', S.A.Budget())
    with pytest.raises(S.A.AdmissionError): S.summarize('progress.jsonl', b'{"event":"x","event":"y"}\n', S.A.Budget())
    value, tail = S.summarize('progress.jsonl', b'{"event":"command_failed","label":"original-runner"}\n', S.A.Budget())
    assert value['row_count'] == 1 and value['event_counts'] == {'command_failed': 1} and tail is None


def test_selected_log_refuses_credentials_before_tail_retention():
    with pytest.raises(S.A.AdmissionError): S.summarize('logs/original-runner.log', b'Authorization: Bearer synthetic\n', S.A.Budget())


def test_failure_cleanup_invalidates_completion_preserving_original_payload(tmp_path):
    root = tmp_path / 'out'; folder = root / 'diagnostic'; folder.mkdir(parents=True)
    (folder / 'completion.json').write_bytes(b'{"diagnostic_complete":true}')
    (folder / 'original-tail.log').write_bytes(b'original source exception\n')
    digest = S.retain_failure(root, ValueError('arbitrary exception text must not be copied'))
    assert not (folder / 'completion.json').exists()
    raw = (folder / 'failure.json').read_bytes(); value = json.loads(raw)
    assert hashlib.sha256(raw).hexdigest() == digest and value['diagnostic_complete'] is False
    assert value['scientific_qualification'] is value['worlds_admitted'] is False
    assert b'arbitrary exception' not in raw
    assert (folder / 'original-tail.log').read_bytes() == b'original source exception\n'
    with pytest.raises(S.A.AdmissionError): S.retain_failure(root, RuntimeError())
    assert (folder / 'failure.json').read_bytes() == raw


def test_failure_cleanup_refuses_parent_symlink(tmp_path):
    victim = tmp_path / 'victim'; victim.mkdir(); (victim / 'completion.json').write_bytes(b'original')
    root = tmp_path / 'out'; root.mkdir(); (root / 'diagnostic').symlink_to(victim, target_is_directory=True)
    with pytest.raises(S.A.AdmissionError): S.retain_failure(root, ValueError())
    assert (victim / 'completion.json').read_bytes() == b'original' and not (victim / 'failure.json').exists()


def test_output_cap_prevents_partial_file_and_keeps_previous_payload(tmp_path, monkeypatch):
    output = S.Outputs(tmp_path); monkeypatch.setattr(S, 'MAX_OUTPUT', 8)
    output.save('one.log', b'12345678', S.A.Budget(), raw=True)
    with pytest.raises(S.A.AdmissionError): output.save('two.log', b'x', S.A.Budget(), raw=True)
    assert not (tmp_path / 'two.log').exists() and (tmp_path / 'one.log').read_bytes() == b'12345678'


def test_pending_gate_precedes_credentials_paths_resources_and_limits(monkeypatch):
    monkeypatch.setattr(S, 'REVIEWED_DIAGNOSTIC_ACTIVATION', None)
    def forbidden(*_a, **_k): pytest.fail('pending source touched host/input work')
    monkeypatch.setattr(S.resource, 'setrlimit', forbidden)
    monkeypatch.setattr(S.D, 'hosted_vm_precondition', forbidden)
    monkeypatch.setattr(S.A, '_resources', forbidden)
    monkeypatch.setattr(S, 'Path', forbidden)
    monkeypatch.setattr(S, 'DiagnosticClient', forbidden)
    for call in (S.registration, S.execute, S.main):
        with pytest.raises(S.A.AdmissionError): call()


@pytest.mark.parametrize('case', ['exact', 'changed-active', 'changed-template'])
def test_exact_active_workflow_source_binding(case):
    raw = (Path(__file__).parents[1] / S.TEMPLATE_FILE).read_bytes()
    if case == 'exact': assert S.workflow_contract(raw, raw) is True
    elif case == 'changed-active':
        with pytest.raises(S.A.AdmissionError): S.workflow_contract(raw, raw + b'\n')
    else:
        with pytest.raises(S.A.AdmissionError): S.workflow_contract(raw + b'\n', raw + b'\n')


def test_fixed_refusal_codes_survive_early_failure_without_arbitrary_text():
    assert S.safe_failure(S.W.Refused('http_refused')) == dict(error_type='Refused', reader_refusal_code='http_refused')
    assert S.safe_failure(S.JobRefused('private text', reason='deadline_exceeded')) == dict(error_type='JobRefused', controller_refusal_code='deadline_exceeded')
    class Unknown(ValueError): code = 'private response body'; reason = 'private response body'
    assert S.safe_failure(Unknown('private response body')) == dict(error_type='Unknown')
    class Deployment(ValueError): code = next(iter(S.D.REFUSAL_CODES))
    assert S.safe_failure(Deployment()) == dict(error_type='Deployment', deployment_refusal_code=Deployment.code)
