"""Observed-byte, replay and many-to-one controls over accepted tiny fixtures."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import base64
import hashlib
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys

import pyarrow as pa
import pytest

from chronicler import campaign_logistics as cl
from chronicler import experiment_sessions as es
from chronicler import snapshot_campaign_sessions as bridge
from chronicler.campaign_snapshot_adapter import CampaignSnapshotError, parse_side_inputs, plan_bytes
from test_campaign_snapshot_adapter import snapshot, side_document, view, write_snapshot
from test_experiment_sessions import canonical, memome_session, reseal

ROOT = Path(__file__).resolve().parents[1]
DRIVER = ROOT / "scripts/verify_snapshot_session.py"
CLI = runpy.run_path(str(DRIVER))


def forbidden(*args, **kwargs):
    raise AssertionError("forbidden input, replay, preparation, kernel or write")


def prepared(document=None, batch=None):
    return bridge.prepare_snapshot_session(
        agent_rows=view(batch), side_inputs=parse_side_inputs(document or side_document()),
        transport=es.documented_transport_policy())


def tick(turn):
    return cl.Tick(turn, (), (), (cl.Condition(7, 0, 1000), cl.Condition(8, 0, 1000)),
                   (cl.Draw(7, 9999), cl.Draw(8, 9999)), (1,))


def files(directory, *, advanced=False):
    source = write_snapshot(directory)
    side = directory / "side.json"
    side.write_text(json.dumps(side_document()), encoding="utf-8")
    transport = directory / "transport.json"
    policy = es.documented_transport_policy()
    transport.write_text(json.dumps(policy.as_payload()), encoding="utf-8")
    original = prepared()
    saved = original.session
    generation = 1
    if advanced:
        for turn in (8, 9):
            saved = es.apply_campaign_tick(saved, tick(turn)).session
            generation += 1
    path = directory / "session.json"
    # Public creation establishes the regular-file workflow and existing lock.
    es.commit_session(path, saved, transport=policy, expected_generation=None,
                      expected_digest=None)
    if advanced:
        path.write_bytes(es.encode_envelope_text(es.encode_session(
            saved, transport=policy, generation=generation), policy))
    return dict(enabled=True, snapshot=source, side_inputs=side, transport=transport,
                path=path, max_snapshot_bytes=source.stat().st_size,
                expected_plan_digest=original.plan.plan_digest)


def inventory(directory):
    return {p.name: (p.read_bytes(), p.stat().st_mtime_ns)
            for p in directory.iterdir() if p.is_file()}


def argv(args, *, expected=True, output_format="json"):
    values = ["--enable"]
    for name in ("snapshot", "side_inputs", "transport", "path", "max_snapshot_bytes"):
        values.extend(["--" + name.replace("_", "-"), str(args[name])])
    if expected and args.get("expected_plan_digest") is not None:
        values.extend(["--expected-plan-digest", args["expected_plan_digest"]])
    values.extend(["--format", output_format])
    return values


def change_row(batch, index, region):
    column = batch.schema.get_field_index("region")
    values = batch.column(column).to_pylist()
    values[index] = region
    return batch.set_column(column, batch.schema.field(column), pa.array(values, type=pa.uint16()))


def renamed_document():
    document = side_document()
    for binding in document["region_bindings"]:
        if binding["name"] == "r0":
            binding["name"] = "renamed-zero"
        binding["neighbors"] = ["renamed-zero" if name == "r0" else name
                                for name in binding["neighbors"]]
    return document


@pytest.mark.parametrize("advanced", [False, True])
def test_equivalent_genesis_and_advanced_history_preserve_every_file(tmp_path, advanced):
    args = files(tmp_path, advanced=advanced)
    before = inventory(tmp_path)
    result = CLI["run"](**args)
    assert result["admission_equivalent"] is True
    assert result["comparison"] == dict(policy=True, topology=True, admission=True)
    assert result["plan_expectation"] == "match"
    assert result["original_provenance"] == "unverified"
    assert result["observed_session"]["generation"] == (3 if advanced else 1)
    assert result["observed_session"]["latest_turn"] == (9 if advanced else 7)
    assert result["observed_session"]["genesis_turn"] == 7
    assert result["observed_session"]["file_digest"] == hashlib.sha256(before["session.json"][0]).hexdigest()
    assert result["supplied_plan"]["plan_digest"] == prepared().plan.plan_digest
    assert result["supplied_plan"]["plan_digest"] != hashlib.sha256(plan_bytes(prepared().plan)).hexdigest()
    assert result["committed"] is result["session_changed"] is False
    assert inventory(tmp_path) == before


@pytest.mark.parametrize("kind", ["unselected_row", "region_label"])
def test_many_to_one_admission_cannot_recover_retained_evidence(tmp_path, kind):
    args = files(tmp_path)
    baseline = CLI["run"](**args)
    if kind == "unselected_row":
        write_snapshot(tmp_path, change_row(snapshot(), 2, 1))  # id9 stays an unselected farmer
        args["max_snapshot_bytes"] = args["snapshot"].stat().st_size
    else:
        args["side_inputs"].write_text(json.dumps(renamed_document()), encoding="utf-8")
    changed = CLI["run"](**args)
    assert changed["admission_equivalent"] is True
    assert changed["comparison"] == baseline["comparison"]
    assert changed["plan_expectation"] == "mismatch"
    assert changed["supplied_plan"]["plan_digest"] != baseline["supplied_plan"]["plan_digest"]
    dimension = "source_content_digest" if kind == "unselected_row" else "region_binding_digest"
    assert changed["supplied_plan"][dimension] != baseline["supplied_plan"][dimension]
    absent = CLI["run"](**(args | {"expected_plan_digest": None}))
    assert absent["admission_equivalent"] is True and absent["plan_expectation"] == "not_supplied"
    assert absent["original_provenance"] == changed["original_provenance"] == "unverified"


@pytest.mark.parametrize("kind,dimension", [("selected_row", "admission"),
                                           ("policy", "policy"), ("topology", "topology"),
                                           ("stock", "admission")])
def test_full_typed_genesis_comparison_even_with_matching_new_expectation(tmp_path, kind, dimension):
    args = files(tmp_path, advanced=True)
    document = side_document()
    batch = snapshot()
    if kind == "selected_row":
        batch = change_row(batch, 0, 1)
        write_snapshot(tmp_path, batch)
        args["max_snapshot_bytes"] = args["snapshot"].stat().st_size
    elif kind == "policy":
        document["policy"]["ration_demand"] = 2  # same version ID
    elif kind == "stock":
        document["stocks"]["2"] = 5
    else:
        for binding in document["region_bindings"]:
            if binding["name"] == "r1":
                binding["neighbors"].append("r2")
            if binding["name"] == "r2":
                binding["neighbors"].append("r1")
    args["side_inputs"].write_text(json.dumps(document), encoding="utf-8")
    args["expected_plan_digest"] = prepared(document, batch).plan.plan_digest
    result = CLI["run"](**args)
    assert result["admission_equivalent"] is False
    assert result["comparison"][dimension] is False
    assert result["plan_expectation"] == "match"  # expectation identifies no saved session
    assert result["observed_session"]["latest_turn"] == 9


@pytest.mark.parametrize("kind", ["history", "latest", "digest"])
def test_complete_replay_rejects_resealed_corruption_before_positive_report(tmp_path, kind, capsys):
    args = files(tmp_path, advanced=True)
    policy = es.documented_transport_policy()
    envelope = es.decode_envelope_text(args["path"].read_bytes(), policy)
    if kind == "history":
        history = json.loads(envelope.history)
        history[0]["conditions"][0]["unmet_needs"] = 1
        corrupted = reseal(envelope, history=canonical(history))
    elif kind == "latest":
        latest = json.loads(envelope.latest)
        latest["state"]["consumed_food"] += 1
        corrupted = reseal(envelope, latest=canonical(latest))
    else:
        corrupted = replace(envelope, session_digest="0" * 64)
    # Digest-consistent history/latest controls pass header decoding but fail replay.
    args["path"].write_bytes(es.encode_envelope_text(corrupted, policy))
    es.decode_envelope_text(args["path"].read_bytes(), policy)
    before = inventory(tmp_path)
    assert CLI["main"](argv(args)) == 3
    output = capsys.readouterr()
    assert not output.out and json.loads(output.err)["error"] == "IntegrityError"
    assert inventory(tmp_path) == before


def test_memome_and_different_transport_are_input_failures(tmp_path, capsys):
    args = files(tmp_path)
    policy = es.documented_transport_policy()
    args["path"].write_bytes(es.encode_envelope_text(es.encode_session(
        memome_session(), transport=policy, generation=1), policy))
    assert CLI["main"](argv(args)) == 3
    output = capsys.readouterr()
    assert not output.out and "M60a" in json.loads(output.err)["detail"]
    args["path"].write_bytes(es.encode_envelope_text(prepared().envelope, policy))
    args["transport"].write_text(json.dumps(replace(policy, max_history=policy.max_history + 1).as_payload()))
    assert CLI["main"](argv(args)) == 3
    output = capsys.readouterr()
    assert not output.out and "transport policy differs" in json.loads(output.err)["detail"]


@pytest.mark.parametrize("value", ["", "a" * 63, "A" * 64, "g" * 64, "a" * 65, True, 64])
def test_expected_digest_validation_precedes_reads(monkeypatch, value):
    monkeypatch.setitem(CLI["run"].__globals__, "read_bounded_bytes", forbidden)
    with pytest.raises(CampaignSnapshotError, match="64 lowercase"):
        CLI["run"](enabled=True, snapshot=Path("x"), side_inputs=Path("x"),
                   transport=Path("x"), path=Path("x"), max_snapshot_bytes=4096,
                   expected_plan_digest=value)


@pytest.mark.parametrize("field", ["snapshot", "side_inputs", "transport", "path", "max_snapshot_bytes"])
def test_required_inputs_before_any_read(monkeypatch, field):
    args = dict(enabled=True, snapshot=Path("x"), side_inputs=Path("x"),
                transport=Path("x"), path=Path("x"), max_snapshot_bytes=4096)
    args[field] = None
    monkeypatch.setitem(CLI["run"].__globals__, "read_bounded_bytes", forbidden)
    with pytest.raises(CampaignSnapshotError, match="requires"):
        CLI["run"](**args)


@pytest.mark.parametrize("kind", ["duplicate", "unknown", "bool", "float", "nan"])
def test_strict_side_document_rejected_before_arrow(tmp_path, monkeypatch, kind):
    args = files(tmp_path)
    document = side_document()
    if kind == "duplicate":
        text = json.dumps(document)[:-1] + ',"source_turn":7}'
    elif kind == "unknown":
        text = json.dumps(document | {"unknown": 1})
    else:
        document["source_turn"] = {"bool": True, "float": 7.0, "nan": float("nan")}[kind]
        text = json.dumps(document)
    args["side_inputs"].write_text(text)
    monkeypatch.setitem(CLI["run"].__globals__, "read_snapshot", forbidden)
    with pytest.raises((es.SessionError, CampaignSnapshotError)):
        CLI["run"](**args)


@pytest.mark.parametrize("which", ["transport", "side_inputs", "snapshot", "path"])
def test_public_byte_bounds_before_respective_parser(tmp_path, monkeypatch, which):
    args = files(tmp_path)
    if which == "snapshot":
        args["max_snapshot_bytes"] -= 1
        monkeypatch.setattr(pa.ipc, "open_file", forbidden)
    else:
        limit = 4096 if which == "transport" else es.documented_transport_policy().max_bytes
        args[which].write_bytes(b" " * (limit + 1))
        target = {"transport": "transport_policy_from_text", "side_inputs": "submission_from_bytes",
                  "path": "decode_envelope_text"}[which]
        monkeypatch.setitem(CLI["run"].__globals__, target, forbidden)
    with pytest.raises(es.TransportDomainError):
        CLI["run"](**args)


def test_schema_and_declared_epoch_checks_are_preserved(tmp_path, monkeypatch):
    args = files(tmp_path)
    malformed = snapshot().remove_column(0)
    with pa.OSFile(str(args["snapshot"]), "wb") as sink:
        with pa.ipc.new_file(sink, malformed.schema) as writer:
            writer.write_batch(malformed)
    args["max_snapshot_bytes"] = args["snapshot"].stat().st_size
    with pytest.raises(KeyError):
        CLI["run"](**args)
    write_snapshot(tmp_path)
    args["max_snapshot_bytes"] = args["snapshot"].stat().st_size
    # No Arrow epoch exists; the stamp is the caller declaration. Test the public
    # preparation boundary's rejection if the supplied stamp differs from it.
    monkeypatch.setitem(CLI["run"].__globals__, "Stamp", lambda turn, stage: view(turn=turn + 1).stamp)
    with pytest.raises(CampaignSnapshotError, match="turn"):
        CLI["run"](**args)


def test_single_session_read_report_stays_bound_to_old_bytes_after_replacement(tmp_path, monkeypatch):
    args = files(tmp_path)
    old = args["path"].read_bytes()
    advanced = es.apply_campaign_tick(prepared().session, tick(8)).session
    policy = es.documented_transport_policy()
    new = es.encode_envelope_text(es.encode_session(advanced, transport=policy, generation=2), policy)
    original_read = CLI["run"].__globals__["read_bounded_bytes"]
    observations = []
    def replacement(path, **kwargs):
        data = original_read(path, **kwargs)
        if Path(path) == args["path"]:
            observations.append(data)
            swap = tmp_path / "replacement.json"
            swap.write_bytes(new)
            os.replace(swap, path)
        return data
    monkeypatch.setitem(CLI["run"].__globals__, "read_bounded_bytes", replacement)
    result = CLI["run"](**args)
    assert observations == [old] and args["path"].read_bytes() == new
    assert result["observed_session"]["file_digest"] == hashlib.sha256(old).hexdigest()
    assert result["observed_session"]["generation"] == 1
    assert result["observed_session"]["latest_turn"] == 7
    assert "path may subsequently be replaced" in " ".join(result["limitations"])


def test_off_and_help_ignore_poison_optional_values(monkeypatch, capsys):
    globals_ = CLI["run"].__globals__
    for name in ("validate_snapshot_byte_limit", "read_bounded_bytes", "read_snapshot",
                 "prepare_snapshot_session", "decode_envelope_text", "decode_envelope"):
        monkeypatch.setitem(globals_, name, forbidden)
    class Poison:
        __bool__ = __str__ = __repr__ = __fspath__ = forbidden
    poison = Poison()
    assert CLI["run"](enabled=False, snapshot=poison, side_inputs=poison,
                      transport=poison, path=poison, max_snapshot_bytes=poison,
                      expected_plan_digest=poison) == CLI["disabled_report"]()
    assert CLI["main"](["--max-snapshot-bytes", "garbage", "--expected-plan-digest", "bad",
                         "--format", "malformed", "--path", "missing"]) == 0
    output = capsys.readouterr()
    assert json.loads(output.out) == CLI["disabled_report"]() and not output.err
    with pytest.raises(SystemExit) as exc:
        CLI["main"](["--enable", "--max-snapshot-bytes", "bad", "--help"])
    assert exc.value.code == 0


def test_fresh_import_and_disabled_cli_do_no_input_kernel_rng_or_fixture_work():
    probe = r'''
import builtins, importlib.util, io, json, random, sys
from contextlib import redirect_stdout
from pathlib import Path
import pyarrow as pa
from chronicler import campaign_logistics as kernel
from chronicler import campaign_snapshot_adapter as adapter
from chronicler import experiment_sessions as sessions
from chronicler import snapshot_campaign_sessions as bridge
def forbidden(*args, **kwargs):
    raise AssertionError("forbidden work")
before = random.getstate()
builtins.open = Path.open = forbidden
kernel.admit = kernel.advance = adapter.admit_snapshot_plan = forbidden
for name in ("create_campaign_session", "decode_envelope_text", "decode_envelope", "commit_session"):
    setattr(sessions, name, forbidden)
for name in ("read_bounded_bytes", "read_snapshot", "prepare_snapshot_session"):
    setattr(bridge, name, forbidden)
pa.ipc.open_file = forbidden
spec = importlib.util.spec_from_file_location("snapshot_check", "scripts/verify_snapshot_session.py")
module = importlib.util.module_from_spec(spec)
sys.stderr.write("boundary-start\n")
spec.loader.exec_module(module)
output = io.StringIO()
with redirect_stdout(output):
    assert module.main(["--max-snapshot-bytes", "bad", "--expected-plan-digest", "bad"]) == 0
assert json.loads(output.getvalue()) == module.disabled_report()
assert random.getstate() == before
for name in ("chronicler.main", "chronicler.models", "chronicler.agent_bridge", "chronicler.world_gen",
             "chronicler_agents", "campaign_logistics_demo", "memome_demo"):
    assert name not in sys.modules, name
sys.stderr.write("boundary-end\n")
'''
    result = subprocess.run([sys.executable, "-B", "-c", probe], cwd=ROOT,
                            env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"),
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout == ""
    assert result.stderr.partition("boundary-start\n")[2] == "boundary-end\n"


def test_actual_cli_seed_concurrency_mismatch_error_and_post_command_bytes(tmp_path):
    args = files(tmp_path, advanced=True)
    receipts = []
    def invoke(arguments, seed="0"):
        command = [sys.executable, "-B", str(DRIVER), *arguments]
        before = inventory(tmp_path)
        process = subprocess.run(command, cwd=ROOT, capture_output=True, timeout=30,
                                 env=dict(os.environ, PYTHONHASHSEED=seed, PYTHONDONTWRITEBYTECODE="1"))
        after = inventory(tmp_path)
        assert after == before
        receipt = {"command": command, "hash_seed": seed, "exit": process.returncode,
                   "stdout": process.stdout.decode(), "stderr": process.stderr.decode(),
                   "post_command_files": {
                       name: {"bytes_base64": base64.b64encode(data).decode(),
                              "sha256": hashlib.sha256(data).hexdigest(), "mtime_ns": mtime}
                       for name, (data, mtime) in after.items()}}
        receipts.append(receipt)
        return process
    serial = [invoke(argv(args), seed) for seed in ("0", "42", "101")]
    assert all(p.returncode == 0 and p.stdout == serial[0].stdout for p in serial)
    with ThreadPoolExecutor(max_workers=2) as pool:
        concurrent = list(pool.map(lambda _: invoke(argv(args)), range(2)))
    assert all(p.returncode == 0 and p.stdout == serial[0].stdout for p in concurrent)
    text = invoke(argv(args, output_format="text"))
    assert text.returncode == 0 and b"original provenance unverified" in text.stdout
    # Both accepted independent many-to-one controls get actual CLI receipts.
    for kind in ("unselected_row", "region_label"):
        write_snapshot(tmp_path, change_row(snapshot(), 2, 1) if kind == "unselected_row" else snapshot())
        args["max_snapshot_bytes"] = args["snapshot"].stat().st_size
        args["side_inputs"].write_text(json.dumps(renamed_document() if kind == "region_label" else side_document()))
        mismatch = invoke(argv(args))
        assert mismatch.returncode == 1
        report = json.loads(mismatch.stdout)
        assert report["admission_equivalent"] and report["plan_expectation"] == "mismatch"
        absent = invoke(argv(args, expected=False))
        assert absent.returncode == 0 and json.loads(absent.stdout)["plan_expectation"] == "not_supplied"
    args["expected_plan_digest"] = "bad"
    invalid = invoke(argv(args))
    assert invalid.returncode == 3 and not invalid.stdout and json.loads(invalid.stderr)["error"] == "CampaignSnapshotError"
    changed_batch = change_row(snapshot(), 0, 1)
    write_snapshot(tmp_path, changed_batch)
    args["max_snapshot_bytes"] = args["snapshot"].stat().st_size
    args["side_inputs"].write_text(json.dumps(side_document()))
    args["expected_plan_digest"] = prepared(batch=changed_batch).plan.plan_digest
    selected_mismatch = invoke(argv(args))
    selected_report = json.loads(selected_mismatch.stdout)
    assert selected_mismatch.returncode == 1
    assert not selected_report["admission_equivalent"] and selected_report["plan_expectation"] == "match"
    write_snapshot(tmp_path)
    args["max_snapshot_bytes"] = args["snapshot"].stat().st_size
    args["expected_plan_digest"] = prepared().plan.plan_digest
    policy = es.documented_transport_policy()
    original = args["path"].read_bytes()
    envelope = es.decode_envelope_text(original, policy)
    latest = json.loads(envelope.latest)
    latest["state"]["consumed_food"] += 1
    args["path"].write_bytes(es.encode_envelope_text(reseal(envelope, latest=canonical(latest)), policy))
    corrupt = invoke(argv(args))
    assert corrupt.returncode == 3 and not corrupt.stdout and json.loads(corrupt.stderr)["error"] == "IntegrityError"
    args["path"].write_bytes(es.encode_envelope_text(es.encode_session(
        memome_session(), transport=policy, generation=1), policy))
    memome = invoke(argv(args))
    assert memome.returncode == 3 and not memome.stdout
    args["path"].write_bytes(original)
    off = invoke(["--max-snapshot-bytes", "bad", "--expected-plan-digest", "bad", "--format", "bad"])
    assert off.returncode == 0 and json.loads(off.stdout) == CLI["disabled_report"]()
    help_ = invoke(["--enable", "--max-snapshot-bytes", "bad", "--help"])
    assert help_.returncode == 0 and b"usage:" in help_.stdout
    for arguments in (["--enable", "--unknown"], ["--enable", "--path"],
                      ["--enable", "--max-snapshot-bytes"]):
        failure = invoke(arguments)
        assert failure.returncode == 3 and not failure.stdout
        assert json.loads(failure.stderr)["error"] == "CampaignSnapshotError"
    for arguments in (["--path"], ["--max-snapshot-bytes"], ["--expected-plan-digest"],
                      ["--unknown", "--format"], ["--enable=false"]):
        disabled = invoke(arguments)
        assert disabled.returncode == 0 and not disabled.stderr
        assert json.loads(disabled.stdout) == CLI["disabled_report"]()
    explicit_help = invoke(["--enable", "--path", "--help"])
    assert explicit_help.returncode == 0 and b"usage:" in explicit_help.stdout
    # Receipt writing occurs only in test scratch, after all post-command checks.
    (tmp_path / "cli-evidence.json").write_text(json.dumps(receipts, indent=2))


def test_render_failure_emits_no_partial_positive_stdout(tmp_path, monkeypatch, capsys):
    args = files(tmp_path)
    def failed_render(*args):
        raise ValueError("cannot render complete result")
    monkeypatch.setitem(CLI["main"].__globals__, "render", failed_render)
    assert CLI["main"](argv(args)) == 3
    output = capsys.readouterr()
    assert not output.out and "cannot render complete result" in output.err


def test_arrow_parser_error_is_input_failure_without_partial_stdout(tmp_path, monkeypatch, capsys):
    args = files(tmp_path)
    def unsupported(*args, **kwargs):
        raise pa.ArrowNotImplementedError("unsupported supplied IPC feature")
    monkeypatch.setitem(CLI["run"].__globals__, "read_snapshot", unsupported)
    assert CLI["main"](argv(args)) == 3
    output = capsys.readouterr()
    assert not output.out and json.loads(output.err)["error"] == "ArrowNotImplementedError"


@pytest.mark.parametrize("arguments", [[], ["--snapshot"], ["--side-inputs"],
    ["--transport"], ["--path"], ["--max-snapshot-bytes"], ["--expected-plan-digest"],
    ["--format"], ["--unknown"], ["--max-snapshot-bytes", "bad", "--unknown"],
    ["--enabl"], ["--enable=false"]])
def test_exact_off_dispatch_precedes_optional_syntax_and_validation(monkeypatch, capsys, arguments):
    for name in ("validate_snapshot_byte_limit", "read_bounded_bytes", "read_snapshot",
                 "prepare_snapshot_session", "decode_envelope_text", "decode_envelope"):
        monkeypatch.setitem(CLI["run"].__globals__, name, forbidden)
    monkeypatch.setattr(Path, "open", forbidden)
    monkeypatch.setattr(CLI["InputParser"], "parse_args", forbidden)
    assert CLI["main"](arguments) == 0
    output = capsys.readouterr()
    assert not output.err and json.loads(output.out) == CLI["disabled_report"]()


@pytest.mark.parametrize("arguments", [["--enable", "--unknown"], ["--enable", "--path"],
    ["--enable", "--max-snapshot-bytes"], ["--enable", "--expected-plan-digest"],
    ["--enable", "--enabl"]])
def test_enabled_cli_syntax_error_is_exit3_before_any_optional_validator_or_read(monkeypatch, capsys, arguments):
    for name in ("validate_snapshot_byte_limit", "read_bounded_bytes", "read_snapshot",
                 "prepare_snapshot_session", "decode_envelope_text", "decode_envelope"):
        monkeypatch.setitem(CLI["run"].__globals__, name, forbidden)
    monkeypatch.setattr(Path, "open", forbidden)
    assert CLI["main"](arguments) == 3
    output = capsys.readouterr()
    assert not output.out and json.loads(output.err)["error"] == "CampaignSnapshotError"


@pytest.mark.parametrize("arguments", [["--enable", "--path", "--help"],
                                      ["--max-snapshot-bytes", "-h"]])
def test_explicit_help_precedes_optional_syntax(monkeypatch, capsys, arguments):
    monkeypatch.setattr(Path, "open", forbidden)
    with pytest.raises(SystemExit) as exc:
        CLI["main"](arguments)
    assert exc.value.code == 0
    output = capsys.readouterr()
    assert "usage:" in output.out and not output.err
