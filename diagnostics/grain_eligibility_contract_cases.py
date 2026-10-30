"""Opt-in pure contracts: explicitly selected, outside the default tests tree.

No Native, product module, World, simulator, artifact endpoint, or installation is
used. Runtime qualification is separate; these source cases are initially UNRUN.
"""
from __future__ import annotations
import ast
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import threading
import types
import zipfile

import pytest

from grain_eligibility_driver import (
    Refused, canonical, strict_json, safe_zip, verify_archive, verify_build,
    verify_wheel, installed_payload, package_map, source_identity, stream_command,
    tree_charge, write_once, sha, WHEEL_MEMBER, WHEEL_NAME,
)
from grain_eligibility_trace import (
    FOOTER_RESERVE, TraceBuffer, PassiveTrace, primitive_copy, source_points,
    Refused as TraceRefused,
)

ROOT = Path(__file__).resolve().parents[1]

def zip_bytes(files, names=None, compression=zipfile.ZIP_DEFLATED):
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", compression=compression) as z:
        for name, body in (files.items() if names is None else names):
            z.writestr(name, body)
    return out.getvalue()

def read_protocol():
    return strict_json((ROOT / "diagnostics/grain_eligibility_protocol.json").read_bytes())

@pytest.mark.parametrize("raw", [b'{"a":1,"a":2}', b'{"x":NaN}', b'{"x":Infinity}', b'{"x":-Infinity}'])
def test_json_refuses_ambiguous_or_nonfinite_input(raw):
    with pytest.raises((ValueError, Refused)):
        strict_json(raw)

def test_json_keeps_false_zero_and_empty_distinct():
    assert strict_json(b'{"a":false,"b":0,"c":""}') == {"a": False, "b": 0, "c": ""}
    assert canonical({"x": False}) != canonical({"x": 0})

@pytest.mark.parametrize("name", ["../a", "/a", "a/../b", "a//b", "a\\b", "a/./b", "C:a", "a/"])
def test_zip_rejects_noncanonical_names(name):
    raw = zip_bytes({name: b"x"})
    with pytest.raises(Refused):
        safe_zip(raw, expanded_cap=4, member_cap=4, max_members=4)

def test_zip_refuses_duplicate_entries():
    raw = zip_bytes({}, names=[("a", b"1"), ("a", b"2")])
    with pytest.raises(Refused):
        safe_zip(raw, expanded_cap=8, member_cap=4, max_members=4)

def test_zip_refuses_symlink_before_read():
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        info = zipfile.ZipInfo("link")
        info.create_system = 3
        info.external_attr = (0o120777 << 16)
        z.writestr(info, b"target")
    with pytest.raises(Refused):
        safe_zip(out.getvalue(), expanded_cap=64, member_cap=64, max_members=4)

@pytest.mark.parametrize("change", ["member", "expanded", "count", "namespace"])
def test_zip_bounds_and_closed_inventory(change):
    raw = zip_bytes({"a": b"1234", "b": b"5"})
    options = {"expanded_cap": 10, "member_cap": 10, "max_members": 4}
    if change == "member":
        options["member_cap"] = 3
    if change == "expanded":
        options["expanded_cap"] = 4
    if change == "count":
        options["max_members"] = 1
    if change == "namespace":
        options["expected_names"] = {"a", "c"}
    with pytest.raises(Refused):
        safe_zip(raw, **options)

def test_zip_crc_failure_is_not_accepted():
    raw = bytearray(zip_bytes({"a": b"HELLO"}, compression=zipfile.ZIP_STORED))
    offset = raw.index(b"HELLO")
    raw[offset] ^= 1
    with pytest.raises(zipfile.BadZipFile):
        safe_zip(bytes(raw), expanded_cap=10, member_cap=10, max_members=2)

def test_zip_valid_closed_payload_is_exact():
    raw = zip_bytes({"a": b"\0x", "b": b""})
    assert safe_zip(raw, expanded_cap=2, member_cap=2, max_members=2,
                    expected_names={"a", "b"}) == {"a": b"\0x", "b": b""}

def test_outer_pin_failure_precedes_zip_parse():
    protocol = read_protocol()
    with pytest.raises(Refused, match="outer"):
        verify_archive(b"not a zip", protocol)

def test_wheel_pin_failure_precedes_zip_parse():
    with pytest.raises(Refused, match="whole"):
        verify_wheel(b"not a zip", read_protocol())

def test_old_build_whole_identity_cannot_be_rewritten():
    protocol = read_protocol()
    identity = protocol["historical"]["identity"]
    manifest = strict_json((ROOT / "scripts/testing/native_shards_manifest.json").read_bytes())
    build = {"kind": "native-shard-current-build-v1", "producer_job_key": "python-native-build",
             "manifest_digest": sha(canonical(manifest)), "identity": identity}
    assert verify_build(build, protocol) == identity
    changed = strict_json(canonical(build))
    changed["identity"]["source_commit"] = "a" * 40
    with pytest.raises(Refused):
        verify_build(changed, protocol)

def test_unready_protocol_refuses_before_git_or_original_request(monkeypatch):
    import grain_eligibility_driver as driver
    protocol = read_protocol()
    protocol["state"], protocol["activation_allowed"] = "UNREADY", False
    monkeypatch.chdir(ROOT)
    def forbidden(*args, **kwargs):
        raise AssertionError("must not reach Git/network/process")
    monkeypatch.setattr(driver, "git", forbidden)
    monkeypatch.setattr(driver.subprocess, "Popen", forbidden)
    with pytest.raises(Refused, match="UNREADY"):
        source_identity(protocol)

def test_write_once_preserves_first_bytes_and_cap(tmp_path):
    path = tmp_path / "first"
    write_once(path, b"first", 5)
    with pytest.raises(FileExistsError):
        write_once(path, b"retry", 5)
    assert path.read_bytes() == b"first"
    with pytest.raises(Refused):
        write_once(tmp_path / "over", b"123456", 5)
    assert not (tmp_path / "over").exists()

def test_no_follow_charge_refuses_symlinks(tmp_path):
    (tmp_path / "a").write_bytes(b"x")
    assert tree_charge(tmp_path) >= 1
    (tmp_path / "link").symlink_to(tmp_path / "a")
    with pytest.raises(Refused):
        tree_charge(tmp_path)

def test_package_namespace_duplicate_is_refused(monkeypatch):
    import grain_eligibility_driver as driver
    values = [types.SimpleNamespace(metadata={"Name": "X_Y"}, version="1"),
              types.SimpleNamespace(metadata={"Name": "x-y"}, version="1")]
    monkeypatch.setattr(driver.metadata, "distributions", lambda: values)
    with pytest.raises(Refused):
        package_map()

def test_installed_package_rejects_extra_or_changed_payload_before_import(tmp_path, monkeypatch):
    import grain_eligibility_driver as driver
    package = tmp_path / "chronicler_agents"
    package.mkdir()
    (package / "__init__.py").write_bytes(b"# old\n")
    payload = {"chronicler_agents/__init__.py": b"# old\n"}
    monkeypatch.setattr(driver.sysconfig, "get_paths", lambda: {"platlib": str(tmp_path)})
    def forbidden(*args, **kwargs):
        raise AssertionError("spec/import must follow all file checks")
    monkeypatch.setattr(driver.util, "find_spec", forbidden)
    (package / "extra.py").write_bytes(b"bad")
    with pytest.raises(Refused, match="namespace"):
        installed_payload(payload)
    (package / "extra.py").unlink()
    (package / "__init__.py").write_bytes(b"# new\n")
    with pytest.raises(Refused, match="payload"):
        installed_payload(payload)

def test_primitive_snapshot_never_calls_repr_property_or_iterator():
    class Hostile:
        def __repr__(self):
            raise AssertionError("repr")
        @property
        def target(self):
            raise AssertionError("getter")
        def __iter__(self):
            raise AssertionError("iterator")
    assert primitive_copy(Hostile()) == {"opaque": True}
    assert primitive_copy([False, 0, {"x": .5}]) == [False, 0, {"ordered_items": [["x", .5]]}]

@pytest.mark.parametrize("value", [float("nan"), float("inf"), 2**129, "x" * 257, [0] * 65])
def test_primitive_bounds_fail_closed(value):
    with pytest.raises(TraceRefused):
        primitive_copy(value)

def test_primitive_copy_does_not_alias_producer_data():
    original = {0: [1., 2.]}
    copied = primitive_copy(original)
    original[0].append(3.)
    assert copied == {"ordered_items": [[0, [1., 2.]]]}

def test_trace_cap_retains_closure_and_is_incomplete():
    trace = TraceBuffer({"protocol": "synthetic"}, limit=FOOTER_RESERVE + 1000)
    for i in range(200):
        trace.append({"i": i, "text": "x" * 100})
    body, complete = trace.finish({"hooks_restored": True, "active_frames": 0, "calls": 1})
    records = [json.loads(x) for x in body.splitlines()]
    assert len(body) <= FOOTER_RESERVE + 1000
    assert complete is False and records[-1]["truncated"] is True
    assert records[-1]["dropped_records"] > 0 and records[-1]["kind"] == "CLOSURE"

def test_observer_error_does_not_throw_into_producer_or_call_repr():
    trace = TraceBuffer({})
    class Hostile:
        def __repr__(self):
            raise AssertionError("repr")
    trace.append({"opaque": Hostile()})
    trace.append({"later": "not recorded after error"})
    body, complete = trace.finish({"hooks_restored": True, "active_frames": 0, "calls": 1})
    assert not complete
    assert json.loads(body.splitlines()[-1])["observer_errors"] == ["TypeError"]

@pytest.mark.parametrize("closure", [
    {"hooks_restored": False, "active_frames": 0, "calls": 1},
    {"hooks_restored": True, "active_frames": 1, "calls": 1},
    {"hooks_restored": True, "active_frames": 0, "calls": 0},
])
def test_trace_incomplete_cleanup_or_zero_calls_is_not_complete(closure):
    assert TraceBuffer({}).finish(closure)[1] is False

def test_production_ast_point_schema_is_exact_without_product_import():
    protocol = read_protocol()
    source = (ROOT / "src/chronicler/grain_reserves.py").read_text()
    points = source_points(source)
    assert points == protocol["tick"]["schema"]
    names = {p["point"]: p for p in points["points"].values()}
    assert names["INTEGER_COST"]["line"] == 577
    assert "cost" not in names["BUDGET_DEFICIT"]["fields"]
    assert "event" not in names["INTEGER_COST"]["fields"]
    assert names["DISPATCH_RETURN"]["line"] == 588
    assert protocol["filters"] == {"buyer": 2, "destinations": [2, 4], "sources": [0, 2, 3, 4, 7]}

def test_point_schema_rejects_ambiguous_production_anchor():
    source = (ROOT / "src/chronicler/grain_reserves.py").read_text()
    changed = source.replace("if cost < 1:", "if cost < 2:")
    with pytest.raises(TraceRefused):
        source_points(changed)

def test_trace_bound_compares_actual_code_to_pinned_source(tmp_path):
    protocol = read_protocol()
    production = ROOT / "src/chronicler/grain_reserves.py"
    trace = PassiveTrace(production, protocol["tick"]["source_sha256"], protocol["tick"]["schema"],
                         tmp_path / "trace", protocol["filters"], {})
    source = production.read_text()
    code = compile(source, str(production.resolve()), "exec", dont_inherit=True, optimize=0)
    target = [x for x in code.co_consts if type(x) is types.CodeType and x.co_name == "tick_grain_reserves"][0]
    assert trace.expected_code == target
    with pytest.raises(TraceRefused, match="pinned production"):
        PassiveTrace(production, "0" * 64, protocol["tick"]["schema"],
                     tmp_path / "other", protocol["filters"], {})

def test_recorded_branch_successor_and_cost_presence_are_point_specific():
    trace = PassiveTrace.__new__(PassiveTrace)
    trace.buffer = TraceBuffer({})
    state = {"pending": {"kind": "POINT", "point": "INTEGER_COST", "source_line": 577,
                         "locals": {"cost": {"present": True, "value": 0}}}}
    trace._flush(state, "line", 578)
    assert state["pending"] is None
    row = json.loads(trace.buffer.records[-1])
    assert row["following_line"] == 578 and row["locals"]["cost"]["value"] == 0

def test_callback_error_is_swallowed_and_original_function_continues():
    trace = PassiveTrace.__new__(PassiveTrace)
    trace.frames, trace.buffer, trace.schema = {}, TraceBuffer({}), {"points": {}}
    continued = []
    def producer():
        trace._local(sys._getframe(), "line", None)
        continued.append("original return")
        return 23
    assert producer() == 23 and continued == ["original return"]
    assert trace.buffer.errors == ["UNREGISTERED_TARGET_FRAME"]

def test_stream_controller_bounds_first_bytes_and_never_retries(tmp_path):
    command = [sys.executable, "-c", "import sys;sys.stdout.buffer.write(b'x'*10000)"]
    result, streams = stream_command(command, dict(os.environ), (128, 128), 5, cwd=tmp_path)
    assert result["refusal"] == "STDOUT_CAP"
    assert len(streams[0]) == 129 and result["streams"][0]["bytes"] > 128
    assert len(streams[1]) <= 129

def test_stream_controller_retains_nonzero_first_exit(tmp_path):
    result, streams = stream_command([sys.executable, "-c", "print('first');raise SystemExit(7)"],
                                    dict(os.environ), (128, 128), 5, cwd=tmp_path)
    assert result["exit_code"] == 7 and result["refusal"] is None and streams[0] == b"first\n"

def test_current_future_and_existing_python_threads_restore_none(tmp_path):
    # Pure Python threads only. Does not execute the production tick or Native.
    assert sys.version_info[:2] >= (3, 13), "contract requires actual settrace_all_threads API"
    import grain_eligibility_trace as module
    trace = PassiveTrace.__new__(PassiveTrace)
    trace.buffer, trace.frames, trace.calls = TraceBuffer({}), {}, 1
    trace.source_path = tmp_path / "unchanged.py"
    trace.source_path.write_bytes(b"# unchanged\n")
    trace.source_sha256 = sha(trace.source_path.read_bytes())
    trace.output_path = tmp_path / "trace.jsonl"
    trace.installed, trace.closed, trace.hooks_restored = False, False, False
    trace.restoration_error, trace.bound_code = None, None
    visited = {}
    lock = threading.Lock()
    def hook(frame, event, arg):
        # Exact synthetic name only; no product is imported or invoked.
        if frame.f_code.co_name == "observed":
            with lock:
                visited[frame.f_locals["label"]] = threading.get_ident()
        return None
    trace._global = hook
    ready, enter, end = threading.Event(), threading.Event(), threading.Event()
    def observed(label):
        return 7
    def existing():
        ready.set()
        enter.wait()
        observed("existing")
        end.set()
    old = threading.Thread(target=existing)
    old.start()
    ready.wait(2)
    trace.install()
    try:
        observed("current")
        enter.set()
        assert end.wait(2)
        old.join(2)
        fresh = threading.Thread(target=observed, args=("future",))
        fresh.start()
        fresh.join(2)
        assert set(visited) == {"current", "existing", "future"}
        assert visited["current"] == threading.get_ident() and visited["existing"] != visited["current"]
    finally:
        enter.set()
        old.join(2)
        trace.close()
    assert sys.gettrace() is None and threading.gettrace() is None
    assert trace.hooks_restored and trace.complete


# Corrective B1/B2/B3 decisions; original complete FIRST49 module above is exact.
# Injected faults below are decision contracts, not an OS-containment claim.

def _reserved_endpoint():
    return {"exit_code": 0, "waited": True, "group_quiescent": True,
            "custody": {"proven": True}, "refusal": None,
            "streams_complete": True, "endpoint_durable": True}

def _mock_command(monkeypatch, *, fail_started=False, members=None):
    import grain_eligibility_session as owned
    events = []
    class Pipe:
        def __init__(self, number):
            self.number, self.closed = number, False
        def fileno(self):
            return self.number
        def close(self):
            self.closed = True
    class Process:
        pid = 12345
        stdout, stderr = Pipe(10), Pipe(11)
        def poll(self):
            raise AssertionError("must never reap via poll")
        def wait(self):
            events.append("wait")
            return 0
    class Selector:
        def __init__(self):
            self.keys = {}
        def register(self, pipe, mask, data):
            self.keys[pipe] = types.SimpleNamespace(fileobj=pipe, data=data)
        def unregister(self, pipe):
            del self.keys[pipe]
        def get_map(self):
            return self.keys
        def select(self, timeout):
            return [(key, 1) for key in list(self.keys.values())]
        def close(self):
            events.append("selector-close")
    monkeypatch.setattr(owned.selectors, "DefaultSelector", Selector)
    monkeypatch.setattr(owned.os, "set_blocking", lambda *args: None)
    monkeypatch.setattr(owned.os, "read", lambda *args: b"")
    monkeypatch.setattr(owned, "durable_directory", lambda path: events.append("mkdir"))
    def writer(path, body, cap):
        name = Path(path).name
        events.append(name)
        if fail_started and name == "launch-started.json":
            raise KeyboardInterrupt()
    def launch(*args, **kwargs):
        events.append("launch")
        assert kwargs["start_new_session"] is True
        return Process()
    states = iter(members or [[], []])
    clock = [0.]
    def member_probe(group, leader):
        events.append("probe")
        return {"group": next(states, []), "other_session_groups": []}
    def settle(pid):
        return owned.settle_reserved_group(pid, terminal=lambda pid: True,
            members=member_probe, kill=lambda *args: events.append("kill"),
            now=lambda: clock[0], pause=lambda n: clock.__setitem__(0, clock[0] + n))
    return owned, events, writer, launch, settle

def test_closed_pipes_live_descendant_settles_before_sole_reap(monkeypatch, tmp_path):
    owned, events, writer, launch, settle = _mock_command(monkeypatch, members=[[999], []])
    result, _ = owned.run_owned(["synthetic"], {}, (128, 128), 5, cwd=tmp_path,
        control=tmp_path / "control", stage="mock", launch=launch, terminal=lambda pid: True,
        settle=settle, writer=writer)
    assert events.index("launch-intent.json") < events.index("launch")
    assert events.index("kill") < events.index("wait") < events.index("endpoint.json")
    assert events.count("wait") == 1 and result["group_quiescent"] is True
    assert result["refusal"] == "OWNED_SESSION_REQUIRED_CLEANUP"

def test_clean_held_leader_has_no_cleanup_signal_or_post_reap_probe(monkeypatch, tmp_path):
    owned, events, writer, launch, settle = _mock_command(monkeypatch)
    result, _ = owned.run_owned(["synthetic"], {}, (128, 128), 5, cwd=tmp_path,
        control=tmp_path / "control", stage="mock", launch=launch, terminal=lambda pid: True,
        settle=settle, writer=writer)
    assert owned.clean_command(result)
    assert "kill" not in events and events.count("wait") == 1
    assert "probe" not in events[events.index("wait") + 1:]

def test_baseexception_after_launch_always_closes_before_endpoint(monkeypatch, tmp_path):
    owned, events, writer, launch, settle = _mock_command(monkeypatch, fail_started=True)
    result, _ = owned.run_owned(["synthetic"], {}, (128, 128), 5, cwd=tmp_path,
        control=tmp_path / "control", stage="mock", launch=launch, terminal=lambda pid: True,
        settle=settle, writer=writer)
    assert events.index("launch") < events.index("wait") < events.index("endpoint.json")
    assert result["first_failure"]["type"] == "KeyboardInterrupt"
    assert result["refusal"] == "COMMAND_OBSERVER_ERROR"

def test_durable_intent_failure_blocks_launch(monkeypatch, tmp_path):
    owned, events, _, launch, settle = _mock_command(monkeypatch)
    def failing(path, body, cap):
        events.append(Path(path).name)
        raise OSError("synthetic intent fsync failure")
    with pytest.raises(OSError):
        owned.run_owned(["synthetic"], {}, (128, 128), 5, cwd=tmp_path,
            control=tmp_path / "control", stage="mock", launch=launch,
            terminal=lambda pid: True, settle=settle, writer=failing)
    assert "launch" not in events and "wait" not in events

def test_lost_reservation_never_signals_a_reused_group():
    import grain_eligibility_session as owned
    actions = []
    def lost(pid):
        raise ChildProcessError()
    result = owned.settle_reserved_group(123, terminal=lost,
        members=lambda *args: actions.append("probe"), kill=lambda *args: actions.append("kill"))
    assert result["proven"] is False and actions == []
    assert result["error_type"] == "ChildProcessError"

def test_failed_member_probe_keeps_custody_unknown():
    import grain_eligibility_session as owned
    def denied(*args):
        raise PermissionError()
    actions = []
    result = owned.settle_reserved_group(123, terminal=lambda pid: True,
        members=denied, kill=lambda *args: actions.append("kill"))
    assert result["proven"] is False and actions == ["kill"]

def test_running_group_never_returns_proven_only_because_pipes_closed():
    import grain_eligibility_session as owned
    clock = [0.]
    result = owned.settle_reserved_group(123, terminal=lambda pid: False,
        members=lambda *args: {"group": [], "other_session_groups": []},
        kill=lambda *args: None, now=lambda: clock[0],
        pause=lambda value: clock.__setitem__(0, clock[0] + value))
    assert result["proven"] is False and result["leader_terminal"] is False
    assert result["kill_requested"] is True and clock[0] >= 5

def test_same_session_other_group_is_unknown_not_empty_group_proof():
    import grain_eligibility_session as owned
    clock = [0.]
    result = owned.settle_reserved_group(123, terminal=lambda pid: True,
        members=lambda *args: {"group": [], "other_session_groups": [456]},
        kill=lambda *args: None, now=lambda: clock[0],
        pause=lambda value: clock.__setitem__(0, clock[0] + value))
    assert result["proven"] is False

def test_reap_failure_keeps_primary_error_and_blocks_capture():
    import grain_eligibility_session as owned
    class Process:
        pid = 123
        def wait(self):
            raise KeyboardInterrupt()
    endpoint = {"refusal": "PRIMARY", "waited": False, "exit_code": None}
    owned.finish_child(Process(), endpoint, settle=lambda pid: {
        "proven": True, "leader_terminal": True, "kill_requested": False})
    assert endpoint["refusal"] == "PRIMARY" and endpoint["group_quiescent"] is False
    assert not owned.capture_allowed(endpoint)

@pytest.mark.parametrize("change", ["group", "wait", "exit", "bool_exit"])
def test_unknown_custody_never_even_looks_up_child_members(change):
    import grain_eligibility_session as owned
    endpoint = _reserved_endpoint()
    if change == "group":
        endpoint["group_quiescent"] = False
    elif change == "wait":
        endpoint["waited"] = False
    elif change == "exit":
        endpoint["exit_code"] = None
    else:
        endpoint["exit_code"] = True
    def forbidden(*args):
        raise AssertionError("child lookup before custody")
    bodies, errors = owned.collect_snapshot(endpoint, [("x", Path("/UNREAD"), 4)], reader=forbidden)
    assert bodies == {} and errors and not owned.capture_allowed(endpoint)

def test_live_census_requires_reservation_and_stops_on_uncertainty():
    import grain_eligibility_session as owned
    called = []
    def lost(pid):
        raise ChildProcessError()
    with pytest.raises(ChildProcessError):
        owned.monitored_census(123, lambda: called.append("census"), terminal=lost)
    assert called == []
    assert owned.monitored_census(123, lambda: "metadata-only", terminal=lambda pid: False) == "metadata-only"

def test_snapshot_missing_member_cannot_arm_upload():
    import grain_eligibility_session as owned
    events = []
    result = owned.publish_snapshot("/UNWRITTEN", _reserved_endpoint(), {"a": b"first"}, {"a", "b"},
        writer=lambda *args: events.append("write"), mkdir=lambda *args: events.append("mkdir"))
    assert result is False and events == []

def test_snapshot_writer_error_cannot_return_true():
    import grain_eligibility_session as owned
    called = []
    def fail(*args):
        called.append("partial")
        raise OSError()
    with pytest.raises(OSError):
        owned.publish_snapshot("/UNWRITTEN", _reserved_endpoint(), {"a": b"x"}, {"a"},
            writer=fail, mkdir=lambda *args: None)
    assert called == ["partial"]

def test_complete_quiescent_negative_snapshot_keeps_negative():
    import grain_eligibility_session as owned
    endpoint = _reserved_endpoint()
    endpoint["exit_code"], endpoint["refusal"] = 2, "FIRST_FAILURE"
    writes = []
    assert owned.publish_snapshot("/UNWRITTEN", endpoint, {"negative.json": b'{"pytest_exit":1}'},
        {"negative.json"}, writer=lambda p, b, cap: writes.append(b), mkdir=lambda *args: None)
    assert endpoint["refusal"] == "FIRST_FAILURE" and writes == [b'{"pytest_exit":1}']

@pytest.mark.parametrize("value", [0, 1, "true", None])
def test_truthy_nonboolean_publication_gate_is_refused(value):
    from grain_eligibility_driver import emit_raw_allowed
    with pytest.raises(Refused):
        emit_raw_allowed(value)

def test_durable_write_flushes_then_fsyncs_file_then_directory(tmp_path):
    import grain_eligibility_session as owned
    import stat
    events = []
    path = tmp_path / "intent.json"
    def sync(fd):
        is_dir = stat.S_ISDIR(os.fstat(fd).st_mode)
        if not is_dir:
            assert path.read_bytes() == b"first"
        events.append("dir-sync" if is_dir else "file-sync")
    def open_dir(name, flags):
        events.append("dir-open")
        assert flags & os.O_DIRECTORY and flags & os.O_NOFOLLOW
        return os.open(name, flags)
    owned.durable_bytes(path, b"first", 5, sync=sync, open_dir=open_dir)
    assert events == ["file-sync", "dir-open", "dir-sync"]
    with pytest.raises(FileExistsError):
        owned.durable_bytes(path, b"retry", 5, sync=sync, open_dir=open_dir)
    assert path.read_bytes() == b"first"

@pytest.mark.parametrize("failure", ["file", "directory"])
def test_fsync_failure_never_claims_durability(tmp_path, failure):
    import grain_eligibility_session as owned
    import stat
    visited = []
    def sync(fd):
        kind = "directory" if stat.S_ISDIR(os.fstat(fd).st_mode) else "file"
        visited.append(kind)
        if kind == failure:
            raise OSError()
    with pytest.raises(OSError):
        owned.durable_bytes(tmp_path / "intent", b"first", 5, sync=sync)
    assert visited == (["file"] if failure == "file" else ["file", "directory"])

def test_protocol_worktree_ready_flip_is_not_committed_activation():
    from grain_eligibility_driver import protocol_binding
    raw = canonical({"state": "READY", "activation_allowed": True})
    committed = canonical({"state": "UNREADY", "activation_allowed": False})
    with pytest.raises(Refused, match="committed HEAD"):
        protocol_binding(strict_json(raw), raw, committed, "100644", "a" * 40, 0o100644)

@pytest.mark.parametrize("mode,gitmode", [(0o120777, "100644"), (0o100755, "100644"), (0o100644, "100755")])
def test_protocol_mode_binding_refuses_alias_or_executable(mode, gitmode):
    from grain_eligibility_driver import protocol_binding
    raw = canonical({"state": "READY", "activation_allowed": True})
    with pytest.raises(Refused, match="protocol mode"):
        protocol_binding(strict_json(raw), raw, raw, gitmode, "a" * 40, mode)

@pytest.mark.parametrize("replacement", [0, 1])
def test_passed_protocol_object_cannot_substitute_bool_and_int(replacement):
    from grain_eligibility_driver import protocol_binding
    expected = {"state": "READY", "activation_allowed": bool(replacement)}
    raw = canonical(expected)
    changed = {**expected, "activation_allowed": replacement}
    with pytest.raises(Refused, match="strict JSON"):
        protocol_binding(changed, raw, raw, "100644", "a" * 40, 0o100644)

def test_protocol_pin_covers_complete_committed_bytes():
    from grain_eligibility_driver import protocol_binding
    protocol = {"state": "READY", "activation_allowed": True, "context": {"x": 3}}
    raw = canonical(protocol)
    pin = protocol_binding(protocol, raw, raw, "100644", "b" * 40, 0o100644)
    assert pin["bytes"] == len(raw) and pin["sha256"] == sha(raw)
    assert pin["git_blob"] == "b" * 40 and pin["mode"] == "100644"

def test_first_failure_survives_secondary_pin_errors():
    import grain_eligibility_session as owned
    endpoint = {"refusal": None}
    owned.remember_failure(endpoint, "PRIMARY", "command")
    owned.remember_failure(endpoint, "SECONDARY_PIN", "capture", OSError())
    assert endpoint["refusal"] == "PRIMARY"
    assert endpoint["first_failure"] == {"label": "PRIMARY", "stage": "command"}
    assert endpoint["secondary_failures"][0]["label"] == "SECONDARY_PIN"
