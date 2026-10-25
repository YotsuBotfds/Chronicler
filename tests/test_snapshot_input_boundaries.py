"""Shared descriptor-reader controls over the accepted tiny captured fixtures."""
import ast
import errno
import hashlib
import io
import json
import os
from pathlib import Path
import runpy
import stat
import subprocess
import sys
from contextlib import redirect_stderr, redirect_stdout

import pyarrow as pa
import pytest

from chronicler import campaign_logistics as cl
from chronicler import experiment_sessions as es
from chronicler import snapshot_campaign_sessions as bridge
from test_campaign_snapshot_adapter import snapshot, side_document, view, write_snapshot
from test_snapshot_campaign_sessions import (
    files, prepare, test_bounded_handle_read_ignores_metadata_and_rejects_before_arrow as original_read_gate,
)
from test_snapshot_session_provenance import tick
from test_session_read_bounds import TrackedHandle
from reference_baselines import baseline_root, baseline_source

ROOT = Path(__file__).resolve().parents[1]
PARENT = "26e1869da6c963108f0eb09dae1455245c030bc9"
BASELINE = baseline_root(PARENT)
CREATOR = "snapshot_campaign_session.py"
VERIFIER = "verify_snapshot_session.py"
POSITIONS = [("creator", "transport"), ("creator", "side_inputs"), ("creator", "snapshot"),
             ("verifier", "transport"), ("verifier", "side_inputs"), ("verifier", "snapshot"),
             ("verifier", "path")]


def forbidden(*args, **kwargs):
    raise AssertionError("forbidden parsing/admission/commit after refused input")


def stream_record(raw):
    return dict(hex=raw.hex(), sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw))


def file_map(directory):
    result = {}
    for path in sorted(directory.iterdir()):
        meta = path.lstat()
        entry = dict(mode=stat.S_IMODE(meta.st_mode), mtime_ns=meta.st_mtime_ns)
        if stat.S_ISREG(meta.st_mode):
            entry.update(kind="regular", **stream_record(path.read_bytes()))
        elif stat.S_ISFIFO(meta.st_mode):
            entry.update(kind="fifo")
        elif stat.S_ISLNK(meta.st_mode):
            entry.update(kind="symlink", target=os.readlink(path))
        else:
            entry.update(kind="other")
        result[path.name] = entry
    return result


def arguments(args):
    result = ["--enable"]
    for name in ("snapshot", "side_inputs", "transport", "path", "max_snapshot_bytes"):
        result.extend(["--" + name.replace("_", "-"), str(args[name])])
    return result


def consumer_child(mode, position, exchange, directory):
    """Instrument the real CLI in a bounded child; no writer unblocks a FIFO."""
    directory = Path(directory)
    args = files(directory)
    if mode == "verifier":
        es.commit_session(args["path"], prepare().session, transport=es.documented_transport_policy(),
                          expected_generation=None, expected_digest=None)
    setup = file_map(directory)
    target = args[position]
    driver = runpy.run_path(str(ROOT / "scripts" / (CREATOR if mode == "creator" else VERIFIER)))
    globals_ = driver["main"].__globals__
    events, read_calls, admissions, descriptors, exchanges = [], [], [], [], []
    for name in ("transport_policy_from_text", "submission_from_bytes", "read_snapshot",
                 "prepare_snapshot_session", "decode_envelope_text", "decode_envelope"):
        if name in globals_:
            original = globals_[name]
            def tracked(*values, _name=name, _original=original, **keywords):
                events.append(_name)
                return _original(*values, **keywords)
            globals_[name] = tracked
    globals_["commit_session"] = forbidden
    if position == "transport":
        globals_["transport_policy_from_text"] = forbidden
    elif position == "side_inputs":
        globals_["submission_from_bytes"] = forbidden
    elif position == "snapshot":
        pa.ipc.open_file = forbidden
        globals_["prepare_snapshot_session"] = forbidden
    else:
        globals_["decode_envelope_text"] = globals_["decode_envelope"] = forbidden
    admitted = cl.admit
    def tracked_admit(*values, **keywords):
        admissions.append("admit")
        return admitted(*values, **keywords)
    cl.admit = tracked_admit
    cl.advance = forbidden
    reader = bridge.read_regular_file_bytes
    def tracked_reader(path, **keywords):
        read_calls.append(dict(path=str(path), **keywords))
        return reader(path, **keywords)
    bridge.read_regular_file_bytes = tracked_reader
    opened = os.open
    def controlled_open(path, *values, **keywords):
        if exchange and Path(path) == target and not exchanges:
            prior = file_map(directory)[target.name]
            target.unlink()
            os.mkfifo(target)
            exchanges.append(dict(before=prior, after=file_map(directory)[target.name]))
        descriptor = opened(path, *values, **keywords)
        descriptors.append(descriptor)
        return descriptor
    os.open = controlled_open
    if not exchange:
        target.unlink()
        os.mkfifo(target)
    before = file_map(directory)
    stdout, stderr = io.StringIO(), io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        exit_code = driver["main"](arguments(args))
    after = file_map(directory)
    assert exit_code == 3 and stdout.getvalue() == ""
    error = json.loads(stderr.getvalue())
    assert error["error"] == "SessionError" and "regular file" in error["detail"]
    expected = dict(before)
    if exchange:
        assert len(exchanges) == 1
        expected[target.name] = exchanges[0]["after"]
    assert after == expected
    assert read_calls[-1]["path"] == str(target)
    expected_reads = {"transport": 1, "side_inputs": 2, "snapshot": 3, "path": 4}[position]
    assert len(read_calls) == expected_reads
    if position == "path":
        assert admissions  # supplied preparation precedes the saved-session read
    else:
        assert admissions == []
    for descriptor in descriptors:
        try:
            os.fstat(descriptor)
        except OSError as exc:
            assert exc.errno == errno.EBADF
        else:
            raise AssertionError("reader descriptor escaped")
    if mode == "creator":
        assert not args["path"].exists() and ".session.json.lock" not in after
    else:
        assert after[".session.json.lock"] == before[".session.json.lock"]
    receipt = dict(schema="av-consumer-refusal-v1", mode=mode, position=position,
        exchange=exchange, cli_argv=arguments(args), cli_exit=exit_code,
        cli_stdout=stream_record(stdout.getvalue().encode()), cli_stderr=stream_record(stderr.getvalue().encode()),
        error=error, setup_files=setup, before_files=before, post_files=after,
        fixture_exchanges=exchanges, events=events, read_calls=read_calls,
        admission_calls=len(admissions), descriptors_closed=True,
        no_writer=True, saved_session_decode_replay_calls=0)
    print(json.dumps(receipt, sort_keys=True))
    return 0


@pytest.mark.parametrize("mode,position", POSITIONS)
@pytest.mark.parametrize("exchange", [False, True])
def test_seven_actual_consumer_positions_initial_fifo_and_preopen_exchange(tmp_path, mode, position, exchange):
    directory = tmp_path / "inputs"
    directory.mkdir()
    command = [sys.executable, "-B", str(Path(__file__).resolve()), "--consumer",
               mode, position, str(int(exchange)), str(directory)]
    process = subprocess.run(command, cwd=ROOT, capture_output=True, timeout=8)
    assert process.returncode == 0, process.stdout + process.stderr
    receipt = json.loads(process.stdout)
    assert receipt["cli_exit"] == 3 and receipt["cli_stdout"]["hex"] == ""
    receipt.update(child_command=command, child_exit=process.returncode,
                   child_stdout=stream_record(process.stdout), child_stderr=stream_record(process.stderr), timeout_seconds=8)
    (tmp_path / "consumer-refusal.json").write_text(json.dumps(receipt, indent=2))


@pytest.mark.parametrize("limit", [True, False, 0, -1, 1.0, "10", es.MAX_TRANSPORT_BYTES + 1])
def test_direct_helper_limit_domain_refuses_before_open(tmp_path, monkeypatch, limit):
    opened = []
    def never_open(*args, **kwargs):
        opened.append(repr(args))
        forbidden()
    monkeypatch.setattr(os, "open", never_open)
    with pytest.raises(es.SessionError) as raised:
        bridge.read_bounded_bytes(Path("unused"), limit=limit, label="snapshot")
    assert opened == []
    (tmp_path / "direct-helper-domain.json").write_text(json.dumps(dict(
        schema="av-direct-helper-domain-v1", case="invalid-limit", supplied=repr(limit),
        error=dict(type=type(raised.value).__name__, detail=str(raised.value)),
        open_calls=opened, before_open_refusal=True)))


@pytest.mark.parametrize("label", [None, True, 1, "", " \t\n", b"snapshot"])
def test_direct_helper_label_domain_refuses_before_open(tmp_path, monkeypatch, label):
    opened = []
    def never_open(*args, **kwargs):
        opened.append(repr(args))
        forbidden()
    monkeypatch.setattr(os, "open", never_open)
    with pytest.raises(es.SessionError, match="file label") as raised:
        bridge.read_bounded_bytes(Path("unused"), limit=10, label=label)
    assert opened == []
    (tmp_path / "direct-helper-domain.json").write_text(json.dumps(dict(
        schema="av-direct-helper-domain-v1", case="invalid-label", supplied=repr(label),
        error=dict(type=type(raised.value).__name__, detail=str(raised.value)),
        open_calls=opened, before_open_refusal=True)))


@pytest.mark.parametrize("path", [b"unused", 1])
def test_prior_path_coercion_does_not_broaden_bytes_or_int_paths(monkeypatch, path):
    monkeypatch.setattr(os, "open", forbidden)
    with pytest.raises(TypeError):
        bridge.read_bounded_bytes(path, limit=10, label="snapshot")


def test_delegation_is_exact_public_reader_with_original_positive_validation_and_64mib_request(tmp_path, monkeypatch):
    assert bridge.read_regular_file_bytes is es.read_regular_file_bytes
    assert bridge.MAX_SNAPSHOT_BYTES == es.MAX_TRANSPORT_BYTES == 67_108_864
    path = tmp_path / "tiny"
    path.write_bytes(b"tiny")
    original = open
    requests, handles = [], []
    def opened(descriptor, *args, **kwargs):
        handle = original(descriptor, *args, **kwargs)
        handles.append(handle)
        return TrackedHandle(handle, requests)
    monkeypatch.setattr(es, "open", opened, raising=False)
    assert bridge.read_bounded_bytes(path, limit=bridge.MAX_SNAPSHOT_BYTES, label="snapshot") == b"tiny"
    assert [size for _, size in requests] == [67_108_865]
    assert all(handle.closed for handle in handles)
    (tmp_path / "direct-helper-domain.json").write_text(json.dumps(dict(
        schema="av-direct-helper-domain-v1", case="exact-64MiB-tiny-file",
        supported_limit=bridge.MAX_SNAPSHOT_BYTES, shared_limit=es.MAX_TRANSPORT_BYTES,
        actual_read_requests=[size for _, size in requests], observed_bytes=stream_record(b"tiny"),
        fixture=file_map(tmp_path), all_handles_closed=True, public_reader_identity=True)))


@pytest.mark.parametrize("limit", [10, 4096])
def test_exact_length_and_one_excess_byte_never_parse_rejected_bytes(tmp_path, monkeypatch, limit):
    path = tmp_path / "source"
    path.write_bytes(b"x" * limit)
    assert bridge.read_bounded_bytes(path, limit=limit, label="source") == b"x" * limit
    path.write_bytes(b"x" * (limit + 1))
    monkeypatch.setattr(pa.ipc, "open_file", forbidden)
    with pytest.raises(es.TransportDomainError):
        bridge.read_bounded_bytes(path, limit=limit, label="source")
    if limit == 10:
        with pytest.raises(es.TransportDomainError):
            bridge.read_snapshot(path, max_snapshot_bytes=limit)


def test_original_11_byte_request_assertion_rejects_unbounded_negative_control(tmp_path, monkeypatch):
    requests, rejections = [], []
    def unbounded(path, *, max_bytes, label):
        descriptor = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
        with es.open(descriptor, "rb", closefd=True) as source:
            requests.append(-1)
            data = source.read()  # deliberately broken test-local reader
        if len(data) > max_bytes:
            error = es.TransportDomainError("eventual rejection does not rescue an unbounded read")
            rejections.append(dict(type=type(error).__name__, detail=str(error)))
            raise error
        return data
    monkeypatch.setattr(bridge, "read_regular_file_bytes", unbounded)
    with pytest.raises(AssertionError) as raised:
        original_read_gate(monkeypatch, tmp_path)
    assert requests == [-1] and len(rejections) == 1
    (tmp_path / "negative-control.json").write_text(json.dumps(dict(
        schema="av-unbounded-negative-control-v1", scope="test-local bridge public-reader alias only; production reader/source unchanged",
        actual_read_requests=requests, expected_preserved_oracle=[11], eventual_size_rejections=rejections,
        caught_assertion=dict(type=type(raised.value).__name__, detail=str(raised.value)),
        preserved_assertion_detected_unbounded_read=True, fixture=file_map(tmp_path))))


@pytest.mark.parametrize("which", ["missing", "directory", "device", "read_error"])
def test_missing_nonregular_and_read_errors_preserve_domains_and_close_descriptors(tmp_path, monkeypatch, which):
    target = tmp_path / "input"
    if which == "missing":
        with pytest.raises(FileNotFoundError):
            bridge.read_bounded_bytes(target, limit=10, label="source")
        return
    target.write_bytes(b"tiny")
    if which == "directory":
        target.unlink()
        target.mkdir()
    elif which == "device":
        target = Path("/dev/null")
    original = open
    actual_open = os.open
    handles, requests, descriptors = [], [], []
    def opened_descriptor(*args, **kwargs):
        descriptor = actual_open(*args, **kwargs)
        descriptors.append(descriptor)
        return descriptor
    monkeypatch.setattr(os, "open", opened_descriptor)
    error = OSError("controlled descriptor read error")
    def fail():
        raise error
    def opened(descriptor, *args, **kwargs):
        handle = original(descriptor, *args, **kwargs)
        handles.append(handle)
        return TrackedHandle(handle, requests, fail if which == "read_error" else None)
    monkeypatch.setattr(es, "open", opened, raising=False)
    expected = IsADirectoryError if which == "directory" else es.SessionError if which == "device" else OSError
    with pytest.raises(expected) as raised:
        bridge.read_bounded_bytes(target, limit=10, label="source")
    if which == "read_error":
        assert raised.value is error
    assert descriptors and all(handle.closed for handle in handles)
    for descriptor in descriptors:
        with pytest.raises(OSError) as closed:
            os.fstat(descriptor)
        assert closed.value.errno == errno.EBADF


def test_symlink_positive_control_and_opened_descriptor_survives_replaced_path(tmp_path, monkeypatch):
    path = tmp_path / "source"
    path.write_bytes(b"old observed")
    link = tmp_path / "link"
    link.symlink_to(path)
    assert bridge.read_bounded_bytes(link, limit=32, label="source") == b"old observed"
    replacement = tmp_path / "replacement"
    replacement.write_bytes(b"new version")
    opened = os.open
    reads = []
    def replaced(target, *args, **kwargs):
        descriptor = opened(target, *args, **kwargs)
        reads.append(str(target))
        if Path(target) == path:
            os.replace(replacement, path)
        return descriptor
    monkeypatch.setattr(os, "open", replaced)
    assert bridge.read_bounded_bytes(path, limit=32, label="source") == b"old observed"
    assert reads == [str(path)] and path.read_bytes() == b"new version"


def test_arrow_reader_types_buffers_and_lifetime_have_one_source_open(tmp_path, monkeypatch):
    path = write_snapshot(tmp_path)
    original = os.open
    opened = []
    def tracked(target, *args, **kwargs):
        opened.append(str(target))
        return original(target, *args, **kwargs)
    monkeypatch.setattr(os, "open", tracked)
    copied = bridge.read_snapshot(path, max_snapshot_bytes=path.stat().st_size)
    assert opened == [str(path)]
    assert copied.schema.equals(snapshot().schema, check_metadata=True)
    assert copied.equals(snapshot())
    for actual, expected in zip(copied.columns, snapshot().columns):
        assert actual.type == expected.type
        assert actual.null_count == expected.null_count
        assert [None if buffer is None else buffer.to_pybytes() for buffer in actual.buffers()] == [
            None if buffer is None else buffer.to_pybytes() for buffer in expected.buffers()]
    path.unlink()
    assert copied.equals(snapshot()) and prepare(agent_rows=view(copied)).session == prepare().session


def test_verifier_session_digest_binds_one_descriptor_after_path_replacement(tmp_path, monkeypatch):
    args = files(tmp_path)
    policy = es.documented_transport_policy()
    es.commit_session(args["path"], prepare().session, transport=policy,
                      expected_generation=None, expected_digest=None)
    old = args["path"].read_bytes()
    next_session = es.apply_campaign_tick(prepare().session, tick(8)).session
    replacement = tmp_path / "replacement.json"
    newer = es.encode_envelope_text(es.encode_session(next_session, transport=policy, generation=2), policy)
    replacement.write_bytes(newer)
    original = os.open
    observed = []
    def replaced(path, *values, **keywords):
        descriptor = original(path, *values, **keywords)
        if Path(path) == args["path"]:
            observed.append(descriptor)
            os.replace(replacement, path)
        return descriptor
    monkeypatch.setattr(os, "open", replaced)
    driver = runpy.run_path(str(ROOT / "scripts" / VERIFIER))
    report = driver["run"](**args)
    assert len(observed) == 1 and args["path"].read_bytes() == newer
    assert report["observed_session"]["file_digest"] == hashlib.sha256(old).hexdigest()
    assert report["observed_session"]["generation"] == 1
    assert report["observed_session"]["latest_turn"] == 7
    assert report["session_changed"] is report["committed"] is False


def test_original_function_and_assertion_asts_preserved_outside_owned_hook():
    def baseline(name):
        return baseline_source(PARENT, name)
    name = "src/chronicler/snapshot_campaign_sessions.py"
    old, new = ast.parse(baseline(name)), ast.parse((ROOT / name).read_text())
    old_functions = {node.name: node for node in old.body if isinstance(node, ast.FunctionDef)}
    new_functions = {node.name: node for node in new.body if isinstance(node, ast.FunctionDef)}
    assert old_functions.keys() == new_functions.keys()
    for key in old_functions:
        if key != "read_bounded_bytes":
            assert ast.dump(old_functions[key]) == ast.dump(new_functions[key])
    assert ast.dump(old_functions["read_bounded_bytes"].args) == ast.dump(new_functions["read_bounded_bytes"].args)
    assert ast.dump(old_functions["read_bounded_bytes"].body[1]) == ast.dump(new_functions["read_bounded_bytes"].body[1])
    name = "tests/test_snapshot_campaign_sessions.py"
    old, new = ast.parse(baseline(name)), ast.parse((ROOT / name).read_text())
    old_functions = {node.name: node for node in old.body if isinstance(node, ast.FunctionDef)}
    new_functions = {node.name: node for node in new.body if isinstance(node, ast.FunctionDef)}
    assert old_functions.keys() == new_functions.keys()
    for key in old_functions:
        a, b = old_functions[key], new_functions[key]
        if key != "test_bounded_handle_read_ignores_metadata_and_rejects_before_arrow":
            assert ast.dump(a) == ast.dump(b)
        else:
            assert [ast.dump(node) for node in ast.walk(a) if isinstance(node, ast.Assert)] == [
                ast.dump(node) for node in ast.walk(b) if isinstance(node, ast.Assert)]
            for attribute in ("stat", "open_file"):
                old_hooks = [ast.dump(node) for node in ast.walk(a) if isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute) and node.func.attr == "setattr"
                    and any(isinstance(arg, ast.Constant) and arg.value == attribute for arg in node.args)]
                new_hooks = [ast.dump(node) for node in ast.walk(b) if isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute) and node.func.attr == "setattr"
                    and any(isinstance(arg, ast.Constant) and arg.value == attribute for arg in node.args)]
                assert old_hooks == new_hooks and old_hooks


def test_supported_workflow_matches_accepted_q_full_streams_and_post_bytes_at_two_seeds(tmp_path):
    directory = tmp_path / "inputs"
    directory.mkdir()
    args = files(directory)
    # The frozen baseline predates the agent-movements snapshot column: both
    # sources read the same capture in the earlier 23-field layout, which the
    # current contract still accepts.
    from chronicler.bridge_contract import LEGACY_SNAPSHOT_SCHEMA
    legacy = snapshot().select(list(LEGACY_SNAPSHOT_SCHEMA.names))
    with pa.OSFile(str(args["snapshot"]), "wb") as sink:
        with pa.ipc.new_file(sink, LEGACY_SNAPSHOT_SCHEMA) as writer:
            writer.write_batch(legacy)
    tick_path = directory / "tick.json"
    tick_path.write_text(json.dumps(dict(turn=8, orders=[], credits=[],
        conditions=[dict(agent_id=i, unmet_needs=0, information_quality=1000) for i in (7, 8)],
        draws=[dict(agent_id=i, value=9999) for i in (7, 8)], supply_sources=[1])))
    original_side = args["side_inputs"].read_bytes()
    immutable_inputs = file_map(directory)
    all_receipts = []
    expected = None
    def invoke(source, seed, label, script, argv, exit_code=0, no_write=True):
        command = [sys.executable, "-B", str(source / "scripts" / script), *argv]
        before = file_map(directory)
        environment = dict(os.environ, PYTHONHASHSEED=seed,
            PYTHONPATH=os.pathsep.join([str(source / "src"), str(source / "tests")]),
            PYTHONDONTWRITEBYTECODE="1")
        process = subprocess.run(command, cwd=source, env=environment, capture_output=True, timeout=15)
        post = file_map(directory)
        assert process.returncode == exit_code, process.stdout + process.stderr
        if no_write:
            assert before == post
        receipt = dict(schema="av-workflow-command-v1", source=str(source), seed=seed, label=label,
            command=command, exit=process.returncode, stdout=stream_record(process.stdout),
            stderr=stream_record(process.stderr), before_files=before, post_files=post,
            no_write=no_write, timeout_seconds=15)
        all_receipts.append(receipt)
        return process, receipt
    for source in (BASELINE, ROOT):
        for seed in ("0", "42"):
            args["path"].unlink(missing_ok=True)
            (directory / ".session.json.lock").unlink(missing_ok=True)
            args["side_inputs"].write_bytes(original_side)
            # Restore setup input timestamps only between workflow invocations;
            # post-command maps themselves are captured unchanged immediately.
            for name, record in immutable_inputs.items():
                os.utime(directory / name, ns=(record["mtime_ns"], record["mtime_ns"]))
            sequence = []
            created, receipt = invoke(source, seed, "create", CREATOR, arguments(args), no_write=False)
            sequence.append(receipt)
            digest = json.loads(created.stdout)["plan"]["plan_digest"]
            for verb in ("inspect", "verify"):
                _, receipt = invoke(source, seed, verb, "experiment_session.py", [verb,
                    "--path", str(args["path"]), "--transport", str(args["transport"])])
                sequence.append(receipt)
            for label, extra, expected_exit in (("genesis-equivalent", ["--expected-plan-digest", digest], 0),):
                _, receipt = invoke(source, seed, label, VERIFIER, arguments(args) + extra, expected_exit)
                sequence.append(receipt)
            applied_args = ["apply", "--path", str(args["path"]), "--transport", str(args["transport"]),
                            "--batch", str(tick_path)]
            _, receipt = invoke(source, seed, "apply", "experiment_session.py", applied_args, no_write=False)
            sequence.append(receipt)
            _, receipt = invoke(source, seed, "guarded-replay", "experiment_session.py", applied_args)
            sequence.append(receipt)
            for label, extra, expected_exit in (("advanced-equivalent", ["--expected-plan-digest", digest], 0),
                ("expected-mismatch", ["--expected-plan-digest", "0" * 64], 1),
                ("expected-absent", [], 0)):
                _, receipt = invoke(source, seed, label, VERIFIER, arguments(args) + extra, expected_exit)
                sequence.append(receipt)
            changed = side_document()
            changed["kits"]["7"] = 7
            args["side_inputs"].write_text(json.dumps(changed))
            different, receipt = invoke(source, seed, "admission-different", VERIFIER,
                arguments(args) + ["--expected-plan-digest", digest], 1)
            assert not json.loads(different.stdout)["admission_equivalent"]
            sequence.append(receipt)
            args["side_inputs"].write_bytes(original_side)
            for label, script, argv, exit_code in [
                ("creator-off", CREATOR, [], 0), ("creator-malformed-off", CREATOR, ["--max-snapshot-bytes", "bad"], 2),
                ("verifier-off", VERIFIER, ["--max-snapshot-bytes"], 0),
                ("creator-help", CREATOR, ["--help"], 0),
                ("verifier-help", VERIFIER, ["--enable", "--path", "--help"], 0),
                ("verifier-syntax", VERIFIER, ["--enable", "--unknown"], 3)]:
                _, receipt = invoke(source, seed, label, script, argv, exit_code)
                sequence.append(receipt)
            comparable = [(row["label"], row["exit"], row["stdout"], row["stderr"],
                {name: {key: value for key, value in entry.items() if key != "mtime_ns"}
                 for name, entry in row["post_files"].items()}) for row in sequence]
            # New publication times depend on each actual invocation. They are
            # retained in full; read/replay before/post timestamp equality is exact.
            if expected is None:
                expected = comparable
            else:
                assert comparable == expected
    (tmp_path / "workflow-compatibility.json").write_text(json.dumps(dict(
        schema="av-workflow-compatibility-v1", parent=PARENT, commands=all_receipts,
        full_stream_and_exit_equality=True, full_post_byte_digest_mode_equality=True,
        all_read_replay_before_post_mtime_and_inventory_equality=True,
        publication_mtimes="actual wall-clock values retained; separate creations are not claimed to have equal timestamps"), indent=2))


if __name__ == "__main__" and len(sys.argv) > 1 and sys.argv[1] == "--consumer":
    raise SystemExit(consumer_child(sys.argv[2], sys.argv[3], bool(int(sys.argv[4])), sys.argv[5]))
