"""Unrun pure/fake contracts for the separate inactive current6a2 diagnostic.

These fixtures never construct a genuine profiler, World, checkpoint or native
runtime. The source-stage runner must separately admit this exact selection.
"""
from __future__ import annotations

import builtins
import copy
import gc
import hashlib
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import weakref

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
import current6a2_timing_records as records
import current6a2_timing_diagnostic as core


@pytest.fixture(autouse=True)
def no_product_or_real_profiler_import(monkeypatch):
    original = builtins.__import__
    def guarded(name, *args, **kwargs):
        if name in ("cProfile", "_lsprof", "numpy", "pyarrow", "arro3") or name == "chronicler" or name.startswith(("chronicler.", "chronicler_agents")):
            raise AssertionError("pure test attempted a product/native/profiler import")
        return original(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", guarded)


class FakeClock:
    def __init__(self):
        self.cpu_value = 0.0
        self.wall_value = 0.0
        self.events = []

    def cpu(self):
        self.events.append(("cpu", self.cpu_value))
        return self.cpu_value

    def wall(self):
        self.events.append(("wall", self.wall_value))
        return self.wall_value

    def advance(self, cpu=1.0, wall=2.0):
        self.cpu_value += cpu
        self.wall_value += wall


class FakeProfile:
    def __init__(self, clock, options, *, enable_cost=(0.0, 0.0), disable_cost=(0.0, 0.0)):
        self.clock = clock
        self.options = options
        self.enable_cost = enable_cost
        self.disable_cost = disable_cost
        self.enabled = False
        self.enable_calls = 0
        self.disable_calls = 0
        self.create_stats_calls = 0
        self.stats = {}

    def enable(self):
        self.clock.events.append(("enable", self.enable_calls))
        self.enable_calls += 1
        self.enabled = True
        self.clock.advance(*self.enable_cost)

    def disable(self):
        self.clock.events.append(("disable", self.disable_calls))
        self.disable_calls += 1
        self.enabled = False
        self.clock.advance(*self.disable_cost)

    def create_stats(self):
        self.create_stats_calls += 1


class FakeFactory:
    def __init__(self, clock, **costs):
        self.clock = clock
        self.costs = costs
        self.created = []

    def __call__(self, **options):
        profile = FakeProfile(self.clock, options, **self.costs)
        self.created.append(profile)
        return profile


class TurnOnly:
    def __init__(self, turn):
        self.turn = turn

    def __getattr__(self, name):
        raise AssertionError("boundary read more than the completed turn integer: " + name)


def make_boundary(profiled=False, **costs):
    clock = FakeClock()
    factory = FakeFactory(clock, **costs)
    cpu, wall = clock.cpu, clock.wall
    boundary = core.DiagnosticBoundary(profiled, cpu=cpu, wall=wall, factory=factory)
    return boundary, clock, factory, cpu


def feed(boundary, clock, first=1, last=97):
    for turn in range(first, last + 1):
        clock.advance()
        assert boundary.turn_end(TurnOnly(turn)) is False


def fake_identity():
    """Invented metadata only; no runtime, RNG or compiled class was inspected."""
    return {"producer_source": "6a2a7b84b7d6ea10bfa4f6574e1f5dc793c092e8",
            "source_digest": "513b1087cfb977306df70075118b78c082644f2bade337c68934d08b6b318a53",
            "native_sha256": "1ec3282dd43bc1ecfa2459960f19047aec5d8744406b5655aef44202585eaf72",
            "native_bytes": 13765672,
            "compiled_classes": ["AgentSimulator", "EcologySimulator", "PoliticsSimulator"],
            "runtime_flags": {"safe_path": True, "no_user_site": True, "ignore_environment": False,
                "isolated": False, "hash_randomization": False, "logical_CPUs": 1, "affinity_CPUs": 1,
                "RSS_unit": "LinuxKiB", "python": "3.13.17 (synthetic pure fixture)"},
            "actual_schema_tuples": None, "installed_new_API_execution": None,
            "initial_rng_input_sha256": "0" * 64}


def run_fake(summary_path, *, index=0, fail_after=None, returned_turns=97):
    request = core.schedule()[index]
    boundary, clock, factory, _cpu = make_boundary(request["role"] == "profiled")
    failure = RuntimeError("arbitrary secret exception body must not enter metadata")
    def execute(_args, *, turn_boundary):
        turn_boundary.bind(lambda _path: (_ for _ in ()).throw(AssertionError("save invoked")), {})
        if fail_after == 0:
            raise failure
        for turn in range(1, 98):
            clock.advance()
            turn_boundary.turn_end(TurnOnly(turn))
            if turn == fail_after:
                raise failure
        return SimpleNamespace(total_turns=returned_turns)
    call = lambda: core.record_call(execute, object(), boundary, request, summary_path,
                                    fake_identity(), cpu=clock.cpu,
                                    wall=clock.wall, peak=lambda: 123456)
    return call, boundary, clock, factory, failure


def valid_summary(index=0):
    return {"kind": "TIMING_ONLY_ROLE_SUMMARY", "protocol": records.PROTOCOL,
            "request": core.schedule()[index], "identity": fake_identity(),
            "execute_run_returned": True, "role_complete": True,
            "completed_world_turn_boundaries": 97,
            "closed_windows": [dict(start=a, end=b, cpu_seconds=8.0, wall_seconds=16.0)
                               for a, b in core.WINDOWS],
            "execute_run_clock": {"cpu_seconds": 97.0, "wall_seconds": 194.0},
            "process_lifetime_peak_RSS_bytes": 123456,
            "RSS_scope": "Linux process-lifetime high-water, including imports/setup/exports",
            "profiled": core.schedule()[index]["role"] == "profiled",
            "bare_CLI_baseline": False, "failure_code": None,
            "unknown": dict(records.UNKNOWN)}


def test_literal_six_role_seed_horizon_order_and_windows():
    rows = core.schedule()
    assert [(x["index"], x["case"], x["regions"], x["aggregate_target_request"], x["role"])
            for x in rows] == [
        (0, "small", 12, 2000, "plain"), (1, "small", 12, 2000, "profiled"),
        (2, "agents", 12, 20000, "profiled"), (3, "agents", 12, 20000, "plain"),
        (4, "regions", 48, 20000, "plain"), (5, "regions", 48, 20000, "profiled")]
    assert all(x["seed"] == 42 and x["civilizations"] == 4 and x["requested_turns"] == 97 for x in rows)
    assert core.WINDOWS == ((8, 16), (88, 96))
    assert sum(x["requested_turns"] for x in rows) == 582
    assert core.schedule() is not rows


@pytest.mark.parametrize("field,value", [
    ("index", False), ("seed", 43), ("regions", 13), ("aggregate_target_request", 1999),
    ("requested_turns", 96), ("civilizations", 5), ("role", "phase"), ("case", "replacement")])
def test_changed_or_bool_role_is_rejected(field, value):
    request = core.schedule()[0]
    request[field] = value
    with pytest.raises(records.Refused):
        core.validate_request(request)


@pytest.mark.parametrize("profiled", [False, True])
def test_both_roles_construct_two_disabled_profiles_with_bound_CPU_timer(profiled):
    boundary, _clock, factory, cpu = make_boundary(profiled)
    assert len(factory.created) == 2
    assert all(profile.options == {"timer": cpu, "subcalls": True, "builtins": True}
               and not profile.enabled for profile in factory.created)
    assert boundary.last == 0 and boundary.active is None and boundary.live_record() is None


def test_profile_control_costs_stay_in_observed_windows_without_correction():
    profiled, clock, factory, _cpu = make_boundary(True, enable_cost=(2.0, 4.0), disable_cost=(3.0, 5.0))
    profiled.bind(lambda _path: None, {})
    feed(profiled, clock)
    assert profiled.complete()
    assert profiled.windows == [dict(start=8, end=16, cpu_seconds=13.0, wall_seconds=25.0),
                                dict(start=88, end=96, cpu_seconds=13.0, wall_seconds=25.0)]
    assert all(profile.enable_calls == 1 and profile.disable_calls == 1 for profile in factory.created)
    plain, clock, factory, _cpu = make_boundary(False, enable_cost=(2.0, 4.0), disable_cost=(3.0, 5.0))
    plain.bind(lambda _path: None, {})
    feed(plain, clock)
    assert plain.windows == [dict(start=8, end=16, cpu_seconds=8.0, wall_seconds=16.0),
                             dict(start=88, end=96, cpu_seconds=8.0, wall_seconds=16.0)]
    assert all(profile.enable_calls == profile.disable_calls == 0 for profile in factory.created)


def test_end_window_disable_precedes_clock_close_and_later_work_cannot_change_it():
    boundary, clock, _factory, _cpu = make_boundary(True)
    boundary.bind(lambda _path: None, {})
    feed(boundary, clock, last=15)
    before = len(clock.events)
    clock.advance()
    boundary.turn_end(TurnOnly(16))
    assert [event[0] for event in clock.events[before:]] == ["disable", "cpu", "wall"]
    closed = copy.deepcopy(boundary.windows)
    clock.advance(100000.0, 200000.0)
    assert boundary.windows == closed


def test_bind_does_not_retain_or_invoke_save_config_or_world():
    boundary, clock, _factory, _cpu = make_boundary()
    class Save:
        def __call__(self, _path):
            raise AssertionError("save invoked")
    class Payload:
        pass
    save, payload = Save(), Payload()
    saved_ref, payload_ref = weakref.ref(save), weakref.ref(payload)
    configuration = {"private": payload}
    boundary.bind(save, configuration)
    world = TurnOnly(1)
    world_ref = weakref.ref(world)
    boundary.turn_end(world)
    del save, payload, configuration, world
    gc.collect()
    assert saved_ref() is payload_ref() is world_ref() is None
    assert not any(key in vars(boundary) for key in ("save", "world", "config", "run_config"))


@pytest.mark.parametrize("turns", [[0], [2], [1, 1], [True], [98]])
def test_missing_duplicate_stale_bool_or_out_of_horizon_boundaries_refuse(turns):
    boundary, _clock, _factory, _cpu = make_boundary()
    boundary.bind(lambda _path: None, {})
    with pytest.raises(records.Refused):
        for turn in turns:
            boundary.turn_end(TurnOnly(turn))


def test_boundary_requires_bind_once_and_all_97_witnesses():
    boundary, clock, _factory, _cpu = make_boundary()
    with pytest.raises(records.Refused):
        boundary.turn_end(TurnOnly(1))
    boundary.bind(lambda _path: None, {})
    with pytest.raises(records.Refused):
        boundary.bind(lambda _path: None, {})
    feed(boundary, clock, last=96)
    assert not boundary.complete()
    feed(boundary, clock, first=97)
    assert boundary.complete()


def test_scaling_keeps_existing_rounding_and_targets_are_not_native_counts():
    world = SimpleNamespace(regions=[SimpleNamespace(population=1, carrying_capacity=x) for x in (2, 4, 6)],
                            civilizations=[object(), object()])
    synchronized = []
    result = core.scale_world(world, 2000, lambda civ, actual: synchronized.append((civ, actual)))
    assert [x.population for x in world.regions] == [667, 667, 667]
    assert [x.carrying_capacity for x in world.regions] == [1333, 2667, 4000]
    assert result["requested_target"] == 2000 and result["start_Python_region_population"] == 2001
    assert result["actual_native_population"] is None
    assert synchronized == [(civ, world) for civ in world.civilizations]


def test_zero_population_is_not_silently_replaced_and_u16_refusal_stops_before_sync():
    world = SimpleNamespace(regions=[SimpleNamespace(population=0, carrying_capacity=1)], civilizations=[])
    value = core.scale_world(world, 2000, lambda *_: None)
    assert world.regions[0].population == 0 and value["start_Python_region_population"] == 0
    world = SimpleNamespace(regions=[SimpleNamespace(population=1, carrying_capacity=100)], civilizations=[object()])
    with pytest.raises(records.Refused, match="u16"):
        core.scale_world(world, 2000, lambda *_: (_ for _ in ()).throw(AssertionError("sync after refusal")))


def test_successful_fake_run_retains_separate_clock_lifetime_peak_and_unknown_native_counts(tmp_path):
    call, _boundary, _clock, factory, _failure = run_fake(tmp_path / "summary.json")
    result = call()
    assert result == records.read_json(tmp_path / "summary.json")
    assert result["execute_run_clock"] == {"cpu_seconds": 97.0, "wall_seconds": 194.0}
    assert result["process_lifetime_peak_RSS_bytes"] == 123456
    assert result["RSS_scope"].startswith("Linux process-lifetime high-water")
    assert result["completed_world_turn_boundaries"] == 97 and result["role_complete"] is True
    assert result["bare_CLI_baseline"] is False and all(value is None for value in result["unknown"].values())
    assert all(not profile.enabled and profile.create_stats_calls == 0 for profile in factory.created)


@pytest.mark.parametrize("fail_after,observed,closed_count", [(0, None, 0), (15, 15, 0), (16, 16, 1), (96, 96, 2)])
def test_exception_retains_only_actual_closed_windows_and_identical_failure(tmp_path, fail_after, observed, closed_count):
    path = tmp_path / "summary.json"
    call, _boundary, _clock, _factory, failure = run_fake(path, fail_after=fail_after)
    with pytest.raises(RuntimeError) as caught:
        call()
    assert caught.value is failure
    value = records.read_json(path)
    assert value["role_complete"] is False and value["execute_run_returned"] is False
    assert value["completed_world_turn_boundaries"] == observed
    assert len(value["closed_windows"]) == closed_count
    assert value["failure_code"] == "EXECUTE_RAISED"
    assert b"secret" not in path.read_bytes()
    assert value["unknown"]["actual_native_ticks"] is None


def test_wrong_return_count_does_not_invent_complete_role(tmp_path):
    call, *_rest = run_fake(tmp_path / "summary.json", returned_turns=96)
    with pytest.raises(records.Refused):
        call()
    value = records.read_json(tmp_path / "summary.json")
    assert value["execute_run_returned"] and value["completed_world_turn_boundaries"] == 97
    assert value["role_complete"] is False and value["failure_code"] == "INCOMPLETE_BOUNDARIES"


@pytest.mark.parametrize("unavailable", ["cpu", "wall", "peak"])
def test_failed_endpoint_or_RSS_read_stops_profiles_and_retains_unknown_negative_measurement(tmp_path, unavailable):
    boundary, clock, factory, _cpu = make_boundary(True)
    reads = {"cpu": 0, "wall": 0}
    def endpoint(name):
        def read():
            reads[name] += 1
            if name == unavailable and reads[name] == 2:
                raise RuntimeError("fake endpoint failure")
            return getattr(clock, name)()
        return read
    def peak():
        if unavailable == "peak":
            raise RuntimeError("fake RSS read failure")
        return 123456
    def execute(_args, *, turn_boundary):
        turn_boundary.bind(lambda _path: None, {})
        feed(turn_boundary, clock, last=97 if unavailable == "peak" else 10)
        return SimpleNamespace(total_turns=97 if unavailable == "peak" else 10)
    path = tmp_path / "summary.json"
    with pytest.raises(Exception):
        core.record_call(execute, object(), boundary, core.schedule()[1], path, fake_identity(),
                         cpu=endpoint("cpu"), wall=endpoint("wall"), peak=peak)
    value = records.read_json(path)
    assert all(not profile.enabled and profile.disable_calls >= 1 for profile in factory.created)
    assert value["role_complete"] is False and value["failure_code"] is not None
    if unavailable == "peak":
        assert value["execute_run_returned"] and value["completed_world_turn_boundaries"] == 97
        assert value["process_lifetime_peak_RSS_bytes"] is None
    else:
        assert value["execute_run_clock"][unavailable + "_seconds"] is None
    assert all(item is None for item in value["unknown"].values())


def test_later_detail_or_hash_failure_does_not_erase_immutable_summary(tmp_path):
    path = tmp_path / "summary.json"
    call, boundary, _clock, _factory, _failure = run_fake(path, index=1)
    call()
    before = path.read_bytes()
    boundary.profiles[0].stats = {("x", line, "f"): (1, 1, 0.0, 0.0, {}) for line in range(20001)}
    with pytest.raises(records.Refused, match="row cap"):
        core.profile_detail(boundary)
    ordinary = tmp_path / "ordinary"
    ordinary.mkdir()
    (ordinary / "body").write_bytes(b"overflow")
    with pytest.raises(records.Refused):
        records.inventory(ordinary, maximum_bytes=1)
    assert path.read_bytes() == before


def profile_fixture(source_root):
    bridge = str(source_root / "src/chronicler/agent_bridge.py")
    sync = (bridge, 1511, "_process_tick_results")
    promotion = (bridge, 2019, "_process_promotions")
    helper = (bridge, 297, "_get_agent_memory_records")
    needs = ("~", 0, "<method 'get_agent_needs' of 'builtins.AgentSimulator' objects>")
    relationships = ("~", 0, "<method 'get_agent_relationships' of 'builtins.AgentSimulator' objects>")
    memories = ("~", 0, "<method 'get_agent_memories' of 'builtins.AgentSimulator' objects>")
    stats = {helper: (12, 12, 0.4, 10.5, {sync: (10, 10, 0.3, 1.5), promotion: (2, 2, 0.1, 9.0)}),
             needs: (10, 10, 0.5, 0.5, {sync: (10, 10, 0.5, 0.5)}),
             relationships: (10, 10, 0.25, 0.25, {sync: (10, 10, 0.25, 0.25)}),
             memories: (12, 12, 1.0, 1.0, {helper: (12, 12, 1.0, 1.0)})}
    boundary, _clock, _factory, _cpu = make_boundary(True)
    for profile in boundary.profiles:
        profile.stats = copy.deepcopy(stats)
    windows = [dict(start=a, end=b, cpu_seconds=10.0, wall_seconds=20.0) for a, b in core.WINDOWS]
    return boundary, windows, (sync, promotion, helper, needs, relationships, memories)


def test_profile_retains_memory_helper_callers_and_does_not_double_count_nested_cost(tmp_path):
    boundary, windows, keys = profile_fixture(tmp_path)
    detail = core.profile_detail(boundary)
    helper_edges = [row for row in detail["selected_caller_edges"] if row["callee"]["function"] == "_get_agent_memory_records"]
    assert {row["caller"]["function"] for row in helper_edges} == {"_process_tick_results", "_process_promotions"}
    values = core.sync_opportunity(detail, windows, tmp_path)
    assert all(row["complete_selected_caller_coverage"] for row in values)
    assert all(row["inclusive_sync_opportunity_cpu_seconds"] == 2.25 for row in values)
    assert all(row["observed_profiled_window_CPU_fraction"] == 0.225 for row in values)
    assert all("not removable CPU" in row["interpretation"] for row in values)
    assert detail["timer"] == "time.process_time floating CPU seconds"
    assert detail["timer_event_overhead_measured"] is False and detail["native_internal_attribution"] is None


def test_unknown_native_label_or_missing_caller_is_unknown_instead_of_zero(tmp_path):
    boundary, windows, keys = profile_fixture(tmp_path)
    for profile in boundary.profiles:
        del profile.stats[keys[3]]
        profile.stats[("~", 0, "<method 'get_agent_needs' of 'OtherSimulator' objects>")] = (10, 10, 1.0, 1.0, {})
    values = core.sync_opportunity(core.profile_detail(boundary), windows, tmp_path)
    assert all(not row["complete_selected_caller_coverage"] for row in values)
    assert all(row["inclusive_sync_opportunity_cpu_seconds"] is None and row["observed_profiled_window_CPU_fraction"] is None for row in values)


def test_wrong_caller_source_and_overlapping_impossible_budget_cannot_claim_coverage(tmp_path):
    boundary, windows, keys = profile_fixture(tmp_path)
    detail = core.profile_detail(boundary)
    for edge in detail["selected_caller_edges"]:
        if edge["callee"]["function"] == "_get_agent_memory_records" and edge["caller"]["function"] == "_process_tick_results":
            edge["caller"]["filename"] = str(tmp_path / "foreign/agent_bridge.py")
    assert all(row["observed_profiled_window_CPU_fraction"] is None for row in core.sync_opportunity(detail, windows, tmp_path))
    boundary, windows, keys = profile_fixture(tmp_path)
    for profile in boundary.profiles:
        profile.stats[keys[2]] = (12, 12, 0.1, 20.0, {keys[0]: (12, 12, 0.1, 20.0)})
    assert all(row["observed_profiled_window_CPU_fraction"] is None for row in core.sync_opportunity(core.profile_detail(boundary), windows, tmp_path))


@pytest.mark.parametrize("bad", [(True, 1, 0.0, 0.0), (2, 1, 0.0, 0.0),
                                 (1, 1, -1.0, 1.0), (1, 1, float("nan"), 1.0),
                                 (1, 1, 0.0, float("inf"))])
def test_profile_counter_type_time_and_order_refusals(bad):
    with pytest.raises(records.Refused):
        core._profile_counters(bad)


def test_profile_row_edge_and_UTF8_caps_refuse_complete_table_claim(tmp_path):
    boundary, _windows, keys = profile_fixture(tmp_path)
    boundary.profiles[0].stats = {("x", line, "f"): (1, 1, 0.0, 0.0, {}) for line in range(20001)}
    with pytest.raises(records.Refused, match="row cap"):
        core.profile_detail(boundary)
    boundary, _windows, keys = profile_fixture(tmp_path)
    boundary.profiles[0].stats = {keys[2]: (1, 1, 0.0, 0.0,
        {("x", line, "caller"): (1, 1, 0.0, 0.0) for line in range(40001)})}
    with pytest.raises(records.Refused, match="edge cap"):
        core.profile_detail(boundary)
    with pytest.raises(records.Refused, match="UTF8"):
        core._function_key(("é" * 1025, 1, "f"))


def test_null_runtime_and_job_clock_approvals_refuse_before_import_or_input_read(monkeypatch):
    def forbidden(*_args, **_kwargs):
        raise AssertionError("source/runtime read before approval")
    monkeypatch.setattr(core, "verify_producer", forbidden)
    monkeypatch.setattr(core, "EXECUTION_APPROVAL", None)
    monkeypatch.setattr(core, "JOB_CLOCK_ADMISSION_APPROVAL", None)
    with pytest.raises(records.Refused, match="execution approval is NULL"):
        core.import_runtime(None, None, {})
    with pytest.raises(records.Refused, match="execution approval is NULL"):
        core.run_role({}, source_root=None, prefix=None, expected_hashes={}, ordinary=None, role_root=None, shared_rng={})
    monkeypatch.setattr(core, "EXECUTION_APPROVAL", "fake-source-only-starting-value")
    with pytest.raises(records.Refused, match="job-clock"):
        core.import_runtime(None, None, {})


@pytest.mark.parametrize("raw", [b'{"x":1,"x":2}', b'{"x":NaN}', b'{"x":Infinity}',
                                 b'{"x":-Infinity}', b'{"x":1e999}', b'[]', b'\xff'])
def test_strict_JSON_rejects_duplicate_nonfinite_nonobject_or_nonUTF8(raw):
    with pytest.raises(records.Refused):
        records.strict_json(raw)


def test_JSON_byte_limit_and_immutable_atomic_write(tmp_path):
    path = tmp_path / "record.json"
    value = {"ordinary": "unchanged"}
    with pytest.raises(records.Refused, match="serialized"):
        records.write_new(path, value, limit=2)
    assert not path.exists()
    pin = records.write_new(path, value)
    before = path.read_bytes()
    assert pin == {"bytes": len(before), "sha256": hashlib.sha256(before).hexdigest()}
    with pytest.raises(FileExistsError):
        records.write_new(path, {"replacement": True})
    assert path.read_bytes() == before and path.with_name(path.name + ".writing").exists()


@pytest.mark.parametrize("field,value", [("seed", 43), ("requested_turns", 96), ("index", True)])
def test_summary_rejects_unregistered_request_even_when_other_fields_look_complete(field, value):
    summary = valid_summary()
    summary["request"][field] = value
    with pytest.raises(records.Refused):
        records.validate_summary(summary)


@pytest.mark.parametrize("change", ["extra", "missing"])
def test_summary_requires_closed_fifteen_field_shape(change):
    summary = valid_summary()
    if change == "extra":
        summary["accepted_profile"] = True
    else:
        del summary["RSS_scope"]
    with pytest.raises(records.Refused, match="closed role summary fields"):
        records.validate_summary(summary)


@pytest.mark.parametrize("field,value", [
    ("producer_source", "3fbaa7bdde7d297bb4a51b4d6c6432ab10fee822"),
    ("source_digest", "0" * 64), ("native_sha256", "0" * 64), ("native_bytes", True),
    ("compiled_classes", ["EcologySimulator", "AgentSimulator", "PoliticsSimulator"]),
    ("actual_schema_tuples", {}), ("installed_new_API_execution", True),
    ("initial_rng_input_sha256", "not-a-digest")])
def test_summary_rejects_wrong_or_promoted_current6a2_identity(field, value):
    summary = valid_summary()
    summary["identity"][field] = value
    with pytest.raises(records.Refused):
        records.validate_summary(summary)


@pytest.mark.parametrize("field,value", [
    ("safe_path", False), ("no_user_site", False), ("ignore_environment", True),
    ("isolated", True), ("hash_randomization", True), ("logical_CPUs", 2),
    ("affinity_CPUs", 2), ("RSS_unit", "portable bytes")])
def test_summary_rejects_unadmitted_runtime_flag_or_RSS_unit(field, value):
    summary = valid_summary()
    summary["identity"]["runtime_flags"][field] = value
    with pytest.raises(records.Refused):
        records.validate_summary(summary)


@pytest.mark.parametrize("name", sorted(records.UNKNOWN))
def test_no_unknown_gate_can_be_promoted_by_metadata(name):
    summary = valid_summary()
    summary["unknown"][name] = True
    with pytest.raises(records.Refused, match="promoted"):
        records.validate_summary(summary)


@pytest.mark.parametrize("change", ["missing_boundary", "not_returned", "wrong_window", "duplicate_window", "RSS_phase_label"])
def test_summary_cannot_invent_completion_or_relabel_lifetime_RSS(change):
    summary = valid_summary()
    if change == "missing_boundary": summary["completed_world_turn_boundaries"] = None
    elif change == "not_returned": summary["execute_run_returned"] = False
    elif change == "wrong_window": summary["closed_windows"][0]["end"] = 15
    elif change == "duplicate_window": summary["closed_windows"][1] = dict(summary["closed_windows"][0])
    else: summary["RSS_scope"] = "per-phase allocation peak"
    with pytest.raises(records.Refused):
        records.validate_summary(summary)


def test_hashing_is_streaming_and_exact_byte_comparison_keeps_timestamp_mismatch(tmp_path, monkeypatch):
    left, right = tmp_path / "left", tmp_path / "right"
    left.mkdir(); right.mkdir()
    (left / "chronicle_bundle.json").write_bytes(b'{"metadata":{"generated_at":"first"}}')
    (right / "chronicle_bundle.json").write_bytes(b'{"metadata":{"generated_at":"later"}}')
    monkeypatch.setattr(Path, "read_bytes", lambda *_: (_ for _ in ()).throw(AssertionError("whole-file read")))
    a, b = records.inventory(left), records.inventory(right)
    result = records.compare_inventories(a, b)
    assert result["exact_file_set_and_bytes_equal"] is False
    assert result["difference_paths"] == ["chronicle_bundle.json"]
    assert result["normalization"] is None and result["body_decoding"] is False
    assert result["unknown"]["semantic_output_equal"] is None


def test_hashing_refuses_same_size_mutation_and_inventory_name_race(tmp_path):
    path = tmp_path / "body"
    path.write_bytes(b"aaaa")
    mutated = False
    def mutate():
        nonlocal mutated
        if not mutated:
            path.write_bytes(b"bbbb")
            mutated = True
    with pytest.raises(records.Refused, match="changed"):
        records.hash_regular(path, 4, guard=mutate)
    root = tmp_path / "root"
    root.mkdir(); (root / "first").write_bytes(b"a")
    calls = 0
    def insert_name():
        nonlocal calls
        calls += 1
        if calls == 3:
            (root / "late").write_bytes(b"b")
    with pytest.raises(records.Refused, match="directory changed"):
        records.inventory(root, guard=insert_name)


@pytest.mark.parametrize("kind", ["file_symlink", "ancestor_symlink", "hardlink", "fifo", "backslash", "invalid_UTF8"])
def test_inventory_rejects_links_aliases_special_and_unsafe_names(tmp_path, kind):
    root = tmp_path / "root"
    root.mkdir()
    body = root / "body"
    body.write_bytes(b"a")
    if kind == "file_symlink": (root / "link").symlink_to(body)
    elif kind == "ancestor_symlink":
        alias = tmp_path / "alias"; alias.symlink_to(root, target_is_directory=True)
        with pytest.raises(records.Refused): records.hash_regular(alias / "body", 1)
        return
    elif kind == "hardlink": os.link(body, root / "alias")
    elif kind == "fifo":
        if not hasattr(os, "mkfifo"): pytest.skip("POSIX fixture unavailable")
        os.mkfifo(root / "pipe")
    elif kind == "backslash": (root / "bad\\name").write_bytes(b"x")
    else:
        descriptor = os.open(os.fsencode(root) + b"/bad\xff", os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(descriptor)
    with pytest.raises(records.Refused):
        records.inventory(root)


def test_inventory_byte_file_entry_and_depth_caps_are_independent(tmp_path, monkeypatch):
    root = tmp_path / "root"
    root.mkdir(); (root / "a").write_bytes(b"abc"); (root / "b").write_bytes(b"def")
    with pytest.raises(records.Refused): records.inventory(root, maximum_bytes=5)
    with pytest.raises(records.Refused): records.inventory(root, maximum_files=1)
    monkeypatch.setattr(records, "MAX_ENTRIES", 1)
    with pytest.raises(records.Refused, match="entry cap"): records.inventory(root)
    monkeypatch.setattr(records, "MAX_ENTRIES", 10000)
    nested = root / "c" / "d"; nested.mkdir(parents=True)
    monkeypatch.setattr(records, "MAX_DEPTH", 1)
    with pytest.raises(records.Refused, match="depth cap"): records.inventory(root)


def test_comparison_uses_existing_maps_without_reading_or_promoting_parity(tmp_path, monkeypatch):
    roots = [tmp_path / name for name in ("first", "same", "different-name")]
    for root, filename in zip(roots, ("a", "a", "b")):
        root.mkdir(); (root / filename).write_bytes(b"x")
    a, same, different = [records.inventory(root) for root in roots]
    monkeypatch.setattr(records, "hash_regular", lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("second hash")))
    result = records.compare_inventories(a, same)
    assert result["exact_file_set_and_bytes_equal"] and result["difference_paths"] == []
    assert all(value is None for value in result["unknown"].values())
    result = records.compare_inventories(a, different)
    assert result["difference_paths"] == ["a", "b"]


def test_post_rename_stat_scan_preserves_identity_without_second_body_hash(tmp_path, monkeypatch):
    original = tmp_path / "ordinary"
    original.mkdir(); (original / "state.json").write_bytes(b"opaque ordinary bytes")
    hashed = records.inventory(original)
    archived = tmp_path / "archived"
    original.rename(archived)
    monkeypatch.setattr(records, "hash_regular", lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("second body hash")))
    observed = records.stat_inventory(archived)
    assert not original.exists()
    assert observed["identities"] == hashed["identities"]
    assert observed["root_identity"] == hashed["root_identity"]
    assert observed["bytes"] == hashed["bytes"] and observed["count"] == hashed["count"]


def test_stat_scan_cannot_hide_a_mutated_archived_body(tmp_path):
    root = tmp_path / "ordinary"
    root.mkdir(); (root / "state.json").write_bytes(b"initial")
    hashed = records.inventory(root)
    (root / "state.json").write_bytes(b"changed and longer")
    observed = records.stat_inventory(root)
    assert observed["identities"] != hashed["identities"]
    assert observed["bytes"] != hashed["bytes"]


def test_metadata_publication_retains_detail_refusal_reason_and_never_reads_ordinary_body(tmp_path):
    source, output = tmp_path / "source", tmp_path / "published"
    role = source / "roles" / "0"
    role.mkdir(parents=True)
    records.write_new(role / "summary.json", valid_summary())
    records.write_new(role / "detail-status.json", {"available": False, "reason": "PROFILE_DETAIL_REFUSED"})
    ordinary = role / "ordinary"
    ordinary.mkdir(); (ordinary / "state.json").write_bytes(b"not JSON or a checkpoint decoder input\0")
    result = records.publish_metadata(source, output)
    assert "roles/0/detail-status.json" in result["present"]
    assert records.read_json(output / "roles/0/detail-status.json")["reason"] == "PROFILE_DETAIL_REFUSED"
    assert not (output / "roles/0/ordinary").exists()
    assert result["metadata_only"] and result["original_body_retention"] is None
    assert all(value is None for value in result["unknown"].values())


def test_metadata_publication_refuses_selected_symlink_and_joint_metadata_caps(tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    target = tmp_path / "outside.json"
    records.write_new(target, {"kind": "untrusted"})
    (source / "owner-summary.json").symlink_to(target)
    with pytest.raises(records.Refused):
        records.publish_metadata(source, tmp_path / "symlink-output")
    (source / "owner-summary.json").unlink()
    records.write_new(source / "owner-summary.json", {"kind": "TIMING_ONLY_OWNER_SUMMARY",
        "protocol": records.PROTOCOL, "unknown": dict(records.UNKNOWN)})
    monkeypatch.setattr(records, "METADATA_BYTES", 1)
    with pytest.raises(records.Refused, match="joint metadata reserve"):
        records.publish_metadata(source, tmp_path / "overbound-output")


def test_metadata_receiver_rejects_unregistered_ordinary_member_even_with_valid_hash(tmp_path):
    root = tmp_path / "publication"
    root.mkdir()
    pin = records.write_new(root / "ordinary-state.json", {"opaque_ordinary_state": True})
    records.write_new(root / "publication.json", {
        "kind": "TIMING_ONLY_METADATA_PUBLICATION", "protocol": records.PROTOCOL,
        "present": {"ordinary-state.json": pin}, "missing": [], "selected_bytes": pin["bytes"],
        "unknown": dict(records.UNKNOWN), "metadata_only": True,
        "owner_step_outcome": "unknown", "original_body_retention": None})
    with pytest.raises(records.Refused):
        records.read_publication(root)


def completion_source(tmp_path, mutation=None):
    """Complete invented source-owned metadata, with no actual study or archive."""
    source = tmp_path / "source"
    source.mkdir()
    summaries = [valid_summary(index) for index in range(6)]
    owner = {"kind": "TIMING_ONLY_OWNER_SUMMARY", "protocol": records.PROTOCOL,
             "producer_source": fake_identity()["producer_source"], "control_source": "a" * 40,
             "matrix_complete": True, "whole_owner_cleanup_certified": True,
             "errors": [], "completed_roles": [
                 {"index": index, "request": copy.deepcopy(summaries[index]["request"]),
                  "completed_world_turn_boundaries": 97, "actual_native_ticks": None,
                  "actual_native_population": None, "ordinary_bytes_hashed": 0}
                 for index in range(6)],
             "unknown": dict(records.UNKNOWN)}
    if mutation == "foreign_producer": owner["producer_source"] = "3fbaa7bdde7d297bb4a51b4d6c6432ab10fee822"
    elif mutation == "malformed_control": owner["control_source"] = "not-an-authenticated-control-SHA"
    elif mutation == "bool_role_index": owner["completed_roles"][0]["index"] = False
    elif mutation == "different_request": owner["completed_roles"][0]["request"]["seed"] = 43
    elif mutation == "missing_boundary": owner["completed_roles"][0]["completed_world_turn_boundaries"] = 96
    elif mutation == "native_ticks_promoted": owner["completed_roles"][0]["actual_native_ticks"] = 97
    elif mutation == "native_population_promoted": owner["completed_roles"][0]["actual_native_population"] = 2000
    elif mutation == "negative_hashed_bytes": owner["completed_roles"][0]["ordinary_bytes_hashed"] = -1
    elif mutation == "oversized_hashed_bytes": owner["completed_roles"][0]["ordinary_bytes_hashed"] = records.ROLE_BYTES + 1
    elif mutation == "different_initial_rng": summaries[5]["identity"]["initial_rng_input_sha256"] = "1" * 64
    else: assert mutation is None
    owner_pin = records.write_new(source / "owner-summary.json", owner)
    records.write_new(source / "terminal.json", {
        "kind": "TIMING_ONLY_TERMINAL", "protocol": records.PROTOCOL,
        "matrix_complete": True, "whole_owner_cleanup_certified": True,
        "owner_summary": owner_pin, "unknown": dict(records.UNKNOWN)})
    for index in range(6):
        directory = source / "roles" / str(index)
        directory.mkdir(parents=True)
        records.write_new(directory / "summary.json", summaries[index])
    return source


@pytest.mark.parametrize("outcome,completion", [("unknown", False), ("failure", False), ("success", True)])
def test_metadata_completion_claim_requires_actual_owner_success_and_stays_source_owned(tmp_path, outcome, completion):
    source, output = completion_source(tmp_path), tmp_path / "publication"
    records.publish_metadata(source, output, owner_step_outcome=outcome)
    readout = records.read_publication(output)
    assert readout["source_owned_matrix_completion_claim"] is completion
    assert readout["official_origin_or_original_archive_qualification"] is None
    assert all(value is None for value in readout["unknown"].values())


@pytest.mark.parametrize("mutation", [
    "foreign_producer", "malformed_control", "bool_role_index", "different_request",
    "missing_boundary", "native_ticks_promoted", "native_population_promoted",
    "negative_hashed_bytes", "oversized_hashed_bytes", "different_initial_rng"])
def test_receiver_rejects_malformed_owner_role_join_or_different_initial_rng(tmp_path, mutation):
    source, output = completion_source(tmp_path, mutation), tmp_path / "publication"
    records.publish_metadata(source, output, owner_step_outcome="success")
    with pytest.raises(records.Refused):
        records.read_publication(output)


def test_metadata_receiver_rejects_a_promoted_unknown_in_selected_owner_record(tmp_path):
    source, output = tmp_path / "source", tmp_path / "publication"
    source.mkdir()
    owner = {"kind": "TIMING_ONLY_OWNER_SUMMARY", "protocol": records.PROTOCOL,
             "unknown": dict(records.UNKNOWN)}
    owner["unknown"]["controlled_speedup"] = True
    records.write_new(source / "owner-summary.json", owner)
    with pytest.raises(records.Refused):
        records.publish_metadata(source, output)
    # Independently exercise receiver rejection; the rejected publisher output
    # remains preserved. This is invented canonical metadata, not an artifact.
    forged = tmp_path / "forged-publication"
    forged.mkdir()
    pin = records.write_new(forged / "owner-summary.json", owner)
    records.write_new(forged / "publication.json", {
        "kind": "TIMING_ONLY_METADATA_PUBLICATION", "protocol": records.PROTOCOL,
        "present": {"owner-summary.json": pin},
        "missing": [name for name in records.metadata_names() if name != "owner-summary.json"],
        "selected_bytes": pin["bytes"], "unknown": dict(records.UNKNOWN),
        "metadata_only": True, "owner_step_outcome": "unknown", "original_body_retention": None})
    with pytest.raises(records.Refused):
        records.read_publication(forged)


# SOURCE-ONLY APPEND FRAGMENT; NOT IMPORTED, COMPILED, COLLECTED OR EXECUTED.
# Append to tests/current6a2_timing_fake_cases.py after parent source review.
# Relies on that module's pytest, records, core, Path, SimpleNamespace, copy,
# hashlib, os, valid_summary and product/profiler import guard. No real resource,
# affinity, subprocess, cancellation, subreaper or runtime operation is used.


@pytest.fixture
def owner_fake(tmp_path, monkeypatch):
    """Exercise owner decisions with invented clocks, metadata and command results.

    The dummy executable is never invoked. Real temporary files are tiny fixture
    records, not product output. Fake approval here never activates registration.
    """
    from datetime import datetime as DateTime, timezone as TimeZone, timedelta
    import current6a2_timing_owner as owner

    control, source, prefix = [tmp_path / name for name in ("control", "producer", "prefix")]
    for directory in (control, source, prefix / "bin"):
        directory.mkdir(parents=True)
    (prefix / "bin/python").write_text("synthetic non-executable placeholder\n", encoding="ascii")
    admission, job_clock = tmp_path / "admission.json", tmp_path / "job-clock.json"
    admission.write_bytes(b"synthetic admission pin only\n")
    job_clock.write_bytes(b"synthetic job clock pin only\n")
    args = SimpleNamespace(source=source, prefix=prefix, output=tmp_path / "output",
                           admission=admission, job_clock=job_clock, control_source="a" * 40)
    h = SimpleNamespace(owner=owner, args=args, control=control, source=source, prefix=prefix,
                        wall=1000.0, cpu=100.0, events=[], commands=[], input_calls=0,
                        now=DateTime(2030, 1, 1, tzinfo=TimeZone.utc),
                        expires=DateTime(2030, 1, 2, tzinfo=TimeZone.utc),
                        control_changed=False, producer_changed=False,
                        git_changed=None, admission_changed=False, children=[],
                        compare_failure=None, hash_failure=False, lease_failure=False,
                        post_lease_child=False, after_command=lambda _label: None)
    h.expire = lambda: setattr(h, "now", h.expires + timedelta(seconds=1))
    h.real_job_deadline = owner.job_deadline
    h.real_control_snapshot = owner.control_snapshot
    h.real_git_metadata = owner.git_metadata
    h.real_child_limits = owner.child_limits
    h.real_cpu_seconds = owner.cpu_seconds
    h.original_hash = records.hash_regular
    h.original_write = records.write_new
    h.original_inventory = records.inventory
    h.original_stat = records.stat_inventory

    class FakeContext:
        def __init__(self, name): self.name = name
        def __enter__(self):
            h.events.append(("enter", self.name))
            return self
        def __exit__(self, exc_type, exc, tb):
            h.events.append(("exit", self.name, exc_type is not None))
            if self.name == "lease":
                if h.lease_failure:
                    raise records.Refused("synthetic lease exit refused")
                if h.post_lease_child:
                    h.children = [909090]
            return False

    class FakeSupervisor:
        def __init__(self):
            self.cleanup_complete = True
            self.last_stdout = b""
        def admission(self, *values): h.events.append(("admission", *values))
        def check(self, *, final=False): h.events.append(("check", final))
        def command(self, label, argv, env, cwd):
            h.commands.append({"label": label, "argv": list(argv), "env": dict(env), "cwd": cwd})
            h.events.append(("command", label))
            assert argv[:3] == ["/usr/bin/timeout", "--signal=TERM", "--kill-after=5s"]
            assert int(argv[3]) >= 1
            if label.endswith("-head"):
                self.last_stdout = ((args.control_source if "control" in label else core.SOURCE) + "\n").encode("ascii")
            elif label.endswith("-clean"):
                self.last_stdout = b""
            elif label == "bootstrap":
                records.write_new(Path(argv[argv.index("--result") + 1]), {
                    "kind": "TIMING_ONLY_INITIAL_RNG_INPUT", "protocol": records.PROTOCOL,
                    "rng": {"synthetic": True}, "unknown": dict(records.UNKNOWN)})
            elif label.startswith("role-"):
                index = int(label.split("-")[1])
                role = Path(argv[argv.index("--role-root") + 1])
                ordinary = Path(argv[argv.index("--ordinary") + 1])
                ordinary.mkdir()
                (ordinary / "opaque.bin").write_bytes(b"x")
                records.write_new(role / "summary.json", valid_summary(index))
            elif label.startswith("hash-"):
                if h.hash_failure:
                    raise records.Refused("synthetic hash child refused")
                ordinary = Path(argv[argv.index("--ordinary") + 1])
                remaining = int(argv[argv.index("--remaining-hash-bytes") + 1])
                records.write_new(Path(argv[argv.index("--result") + 1]),
                                  records.inventory(ordinary, maximum_bytes=remaining), records.DETAIL_BYTES)
            elif label.startswith("compare-"):
                if h.compare_failure:
                    if h.compare_failure == "unclean": self.cleanup_complete = False
                    if h.compare_failure == "live_child": h.children = [808080]
                    raise records.Refused("synthetic bounded comparison refused")
                records.write_new(Path(argv[argv.index("--result") + 1]), {
                    "synthetic_comparison": True, "unknown": dict(records.UNKNOWN)})
            else:
                raise AssertionError("unexpected synthetic command: " + label)
            h.after_command(label)

    h.supervisor = FakeSupervisor()
    def snapshot(_registration):
        return {"registration": {"bytes": 1, "sha256": ("1" if h.control_changed else "0") * 64},
                "files": {"synthetic-control": {"bytes": 1, "sha256": "2" * 64}}}
    def git_metadata(path, expected):
        kind = "control" if path == control else "producer"
        h.events.append(("git_metadata", kind))
        return {"HEAD": {"bytes": 41, "sha256": ("f" if h.git_changed == kind else "3") * 64},
                "synthetic_expected": expected}
    def admit(*_args):
        h.input_calls += 1
        h.events.append(("input_admission", h.input_calls))
        if h.admission_changed:
            raise records.Refused("synthetic reauthentication refused")
        records.require(h.now < h.expires, "synthetic admitted input expiry")
        return {"expires_at": h.expires.isoformat()}
    def verify(*_args):
        h.events.append(("verify_producer",))
        records.require(not h.producer_changed, "synthetic producer byte mutation")

    own = SimpleNamespace(Cancellation=lambda: FakeContext("cancellation"),
                          SubreaperLease=lambda: FakeContext("lease"),
                          make_supervisor=lambda *_a: h.supervisor,
                          direct_children=lambda: list(h.children))
    controls = {"exact_near_screen_process": own, "exact_near_screen_session": object(),
                "wealth_floor_hosted_deployment": SimpleNamespace(
                    hosted_vm_precondition=lambda: {"synthetic_host": True})}
    monkeypatch.setattr(owner, "ROOT", control)
    monkeypatch.setattr(owner, "REGISTRATION", control / "registration.json")
    monkeypatch.setattr(owner, "time", SimpleNamespace(monotonic=lambda: h.wall))
    monkeypatch.setattr(owner, "cpu_seconds", lambda: h.cpu)
    monkeypatch.setattr(owner, "datetime", SimpleNamespace(
        now=lambda _tz: h.now, fromisoformat=DateTime.fromisoformat))
    monkeypatch.setattr(owner, "os", SimpleNamespace(
        environ=dict(core.CAPS), pathsep=os.pathsep,
        sched_getaffinity=lambda _pid: {7},
        sched_setaffinity=lambda pid, cpus: h.events.append(("fake_affinity", pid, cpus)),
        rename=lambda left, right: Path(left).rename(right)))
    monkeypatch.setattr(core, "require_approval", lambda: None)
    monkeypatch.setattr(core, "verify_producer", verify)
    monkeypatch.setattr(owner, "load_registration", lambda: {"synthetic_registration": True})
    monkeypatch.setattr(owner, "input_admission", admit)
    monkeypatch.setattr(owner, "load_controls", lambda _registration: controls)
    monkeypatch.setattr(owner, "job_deadline", lambda *_a: 1000000.0)
    monkeypatch.setattr(owner, "control_snapshot", snapshot)
    monkeypatch.setattr(owner, "git_metadata", git_metadata)
    monkeypatch.setattr(owner, "producer_pins", lambda: {"synthetic": "not producer execution"})
    return h


@pytest.mark.parametrize("entry", ["job_deadline", "run_owner"])
def test_owner_null_actual_job_clock_refuses_before_receipt_or_input_reads(owner_fake, monkeypatch, entry):
    h, owner = owner_fake, owner_fake.owner
    monkeypatch.setattr(owner, "job_deadline", h.real_job_deadline)
    monkeypatch.setattr(core, "JOB_CLOCK_ADMISSION_APPROVAL", None)
    def forbidden(*_a, **_k): raise AssertionError("receipt bytes read before actual clock approval")
    monkeypatch.setattr(records, "hash_regular", forbidden)
    monkeypatch.setattr(records, "read_json", forbidden)
    with pytest.raises(records.Refused, match="actual job-clock source review is NULL"):
        if entry == "job_deadline":
            owner.job_deadline(h.args.job_clock, {}, h.args.control_source,
                               now=lambda: (_ for _ in ()).throw(AssertionError("fallback clock read")))
        else:
            owner.run_owner(h.args)
    assert h.input_calls == 0 and not h.args.output.exists()
    assert not h.commands


def test_owner_actual_deadline_room_is_required_before_input_admission(owner_fake, monkeypatch):
    h, owner = owner_fake, owner_fake.owner
    monkeypatch.setattr(owner, "job_deadline", lambda *_a: h.wall + 105 + 150)
    with pytest.raises(records.Refused, match="job room before any World"):
        owner.run_owner(h.args)
    assert h.input_calls == 0 and not h.args.output.exists() and not h.commands


@pytest.mark.parametrize("limiting_room,expected_seconds", [("wall", 17), ("CPU", 17), ("role", 300)])
def test_owner_command_budget_preserves_finalization_room_and_floors_timeout(owner_fake, limiting_room, expected_seconds):
    h, owner = owner_fake, owner_fake.owner
    def after_bootstrap(label):
        if label == "bootstrap":
            if limiting_room == "wall": h.wall = 1000 + 2400 - 150 - 17.75
            if limiting_room == "CPU": h.cpu = 100 + 1800 - 100 - 17.75
    h.after_command = after_bootstrap
    report = owner.run_owner(h.args)
    role = next(command for command in h.commands if command["label"] == "role-0")
    assert int(role["argv"][3]) == expected_seconds
    assert report["matrix_complete"] and report["whole_owner_cleanup_certified"]
    assert ("admission", "initial", 12, 4) in h.events
    assert report["actual_native_ticks"] is None and report["actual_native_population"] is None
    assert all(value is None for value in report["unknown"].values())


@pytest.mark.parametrize("limiting_room", ["wall", "CPU"])
def test_owner_refuses_subsecond_finalization_room_before_next_role(owner_fake, limiting_room):
    h, owner = owner_fake, owner_fake.owner
    def after_bootstrap(label):
        if label == "bootstrap":
            if limiting_room == "wall": h.wall = 1000 + 2400 - 150 - .5
            else: h.cpu = 100 + 1800 - 100 - .5
    h.after_command = after_bootstrap
    with pytest.raises(records.Refused, match="reserved finalization room"):
        owner.run_owner(h.args)
    assert "role-0" not in [command["label"] for command in h.commands]
    report = records.read_json(h.args.output / "owner-summary.json")
    assert report["completed_roles"] == [] and not report["matrix_complete"]
    assert report["whole_owner_cleanup_certified"] is False
    assert records.read_json(h.args.output / "terminal.json")["matrix_complete"] is False


@pytest.mark.parametrize("child_kind,cpu_cap", [("bootstrap", 240), ("role", 240), ("hash", 40), ("compare", 40)])
def test_owner_selects_child_resource_budget_before_operation_using_fake_resource(owner_fake, monkeypatch, child_kind, cpu_cap):
    h, owner = owner_fake, owner_fake.owner
    calls = []
    fake_resource = SimpleNamespace(RLIMIT_CPU="CPU", RLIMIT_AS="AS", RLIMIT_FSIZE="FSIZE",
                                    setrlimit=lambda name, values: calls.append((name, values)))
    monkeypatch.setattr(owner, "resource", fake_resource)
    class ReachedAfterLimits(Exception): pass
    def stop(): raise ReachedAfterLimits
    monkeypatch.setattr(owner, "producer_pins", stop)
    args = SimpleNamespace(source=h.source, prefix=h.prefix, admission=h.args.admission, child=child_kind)
    with pytest.raises(ReachedAfterLimits): owner.child(args)
    assert calls == [("CPU", (cpu_cap, cpu_cap)), ("AS", (4 * 1024**3, 4 * 1024**3)),
                     ("FSIZE", (512 * 1024**2, 512 * 1024**2))]
    assert h.input_calls == 1 and not h.commands


def test_owner_cpu_ledger_includes_self_and_waited_children(owner_fake, monkeypatch):
    h, owner = owner_fake, owner_fake.owner
    calls = []
    def usage(kind):
        calls.append(kind)
        return SimpleNamespace(ru_utime=2 if kind == "SELF" else 5,
                               ru_stime=3 if kind == "SELF" else 7)
    monkeypatch.setattr(owner, "resource", SimpleNamespace(
        RUSAGE_SELF="SELF", RUSAGE_CHILDREN="CHILDREN", getrusage=usage))
    # The harness patched cpu_seconds, so call the exact function bound on import.
    value = owner_fake.real_cpu_seconds()
    assert value == 17 and calls == ["SELF", "CHILDREN"]


@pytest.mark.parametrize("mutation", [None, "source", "helper", "escape"])
def test_owner_control_snapshot_binds_registration_source_and_selected_helper_without_import(owner_fake, monkeypatch, mutation):
    h, owner = owner_fake, owner_fake.owner
    pin = {"bytes": 1, "sha256": "4" * 64}
    expected = {name: dict(pin) for name in (
        "scripts/current6a2_timing_owner.py", "scripts/current6a2_timing_diagnostic.py",
        "scripts/current6a2_timing_records.py", "docs/experiments/current6a2-timing-producer-pins.json")}
    helpers = {"owned-helper.py": dict(pin)}
    if mutation == "escape": expected["../escaped.py"] = dict(pin)
    calls = []
    def fake_hash(path, limit):
        calls.append((path, limit))
        wrong_source = mutation == "source" and path == h.control / "scripts/current6a2_timing_records.py"
        wrong_helper = mutation == "helper" and path.name == "owned-helper.py"
        return {"bytes": 1, "sha256": ("5" if wrong_source or wrong_helper else "4") * 64}
    monkeypatch.setattr(records, "hash_regular", fake_hash)
    registration = {"control_file_pins": expected, "selected_control_files": helpers}
    if mutation is None:
        result = h.real_control_snapshot(registration)
        assert result["registration"] == pin and result["files"] == expected
        assert calls[-1] == (h.control / "scripts/current6a2_timing_controls/owned-helper.py", 64 * 1024)
    else:
        with pytest.raises(records.Refused): h.real_control_snapshot(registration)
    assert not h.commands


@pytest.mark.parametrize("layout", ["detached", "loose", "packed"])
def test_owner_git_metadata_retains_exact_bounded_detached_loose_or_packed_bytes(owner_fake, layout):
    h = owner_fake
    git = h.source / ".git"
    git.mkdir()
    expected = core.SOURCE
    if layout == "detached":
        (git / "HEAD").write_text(expected + "\n", encoding="ascii")
    else:
        (git / "HEAD").write_text("ref: refs/heads/diagnostic\n", encoding="ascii")
        if layout == "loose":
            (git / "refs/heads").mkdir(parents=True)
            (git / "refs/heads/diagnostic").write_text(expected + "\n", encoding="ascii")
        else:
            (git / "packed-refs").write_text("# pack-refs with: peeled\n" + expected + " refs/heads/diagnostic\n", encoding="ascii")
    result = h.real_git_metadata(h.source, expected)
    assert result["HEAD"] == records.hash_regular(git / "HEAD", 4096)
    if layout == "detached": assert set(result) == {"HEAD"}
    elif layout == "loose":
        assert result["loose_exists"] and result["loose"] == records.hash_regular(git / "refs/heads/diagnostic", 128)
    else:
        assert result["loose_exists"] is False
        assert result["packed"] == records.hash_regular(git / "packed-refs", 1024**2)
    assert not h.commands


@pytest.mark.parametrize("mutation", ["unsafe_ref", "foreign_detached", "wrong_loose", "duplicate_packed", "HEAD_changed_after_hash"])
def test_owner_git_metadata_refuses_noncanonical_foreign_or_racing_head_bytes(owner_fake, monkeypatch, mutation):
    h = owner_fake
    git = h.source / ".git"
    git.mkdir()
    head = git / "HEAD"
    head.write_text("ref: refs/heads/diagnostic\n", encoding="ascii")
    if mutation == "unsafe_ref": head.write_text("ref: refs/heads/../outside\n", encoding="ascii")
    elif mutation == "foreign_detached": head.write_text("b" * 40 + "\n", encoding="ascii")
    elif mutation == "wrong_loose":
        (git / "refs/heads").mkdir(parents=True)
        (git / "refs/heads/diagnostic").write_text("b" * 40 + "\n", encoding="ascii")
    elif mutation == "duplicate_packed":
        (git / "packed-refs").write_text((core.SOURCE + " refs/heads/diagnostic\n") * 2, encoding="ascii")
    else:
        original = records.hash_regular
        def race(path, limit, **kwargs):
            pin = original(path, limit, **kwargs)
            if path == head: head.write_text(core.SOURCE + "\n", encoding="ascii")
            return pin
        monkeypatch.setattr(records, "hash_regular", race)
    with pytest.raises(records.Refused): h.real_git_metadata(h.source, core.SOURCE)


@pytest.mark.parametrize("mutation", ["control", "producer", "Git_control", "Git_producer", "admission", "job_clock"])
def test_owner_late_source_or_admission_guard_keeps_role_summaries_and_blocks_positive_terminal(owner_fake, mutation):
    h, owner = owner_fake, owner_fake.owner
    def late_change(label):
        if label == "final-producer-clean":
            if mutation == "control": h.control_changed = True
            elif mutation == "producer": h.producer_changed = True
            elif mutation.startswith("Git_"): h.git_changed = mutation[4:]
            elif mutation == "admission": h.admission_changed = True
            else: h.args.job_clock.write_bytes(b"changed synthetic clock receipt\n")
    h.after_command = late_change
    with pytest.raises(records.Refused): owner.run_owner(h.args)
    assert all((h.args.output / "roles" / str(i) / "summary.json").exists() for i in range(6))
    assert not (h.args.output / "terminal.json").exists()
    assert records.read_json(h.args.output / "terminal-failure.json")["kind"] == "TIMING_ONLY_TERMINAL_FAILURE"
    assert ("exit", "lease", True) in h.events


def test_owner_input_expiry_during_command_retains_actual_core_summary_without_next_role(owner_fake):
    h, owner = owner_fake, owner_fake.owner
    h.after_command = lambda label: h.expire() if label == "role-0" else None
    with pytest.raises(records.Refused, match="input expired during owned operation"):
        owner.run_owner(h.args)
    summary = records.read_json(h.args.output / "roles/0/summary.json")
    assert summary["role_complete"] and summary["completed_world_turn_boundaries"] == 97
    assert not (h.args.output / "roles/1").exists()
    assert not (h.args.output / "terminal.json").exists()
    assert (h.args.output / "terminal-failure.json").exists()


@pytest.mark.parametrize("cleanup", ["clean", "unclean", "live_child"])
def test_owner_optional_comparison_failure_continues_only_after_owned_quiescence(owner_fake, cleanup):
    h, owner = owner_fake, owner_fake.owner
    h.compare_failure = cleanup
    if cleanup == "clean":
        report = owner.run_owner(h.args)
        assert report["matrix_complete"] and report["whole_owner_cleanup_certified"]
        assert report["optional_observations_unavailable"] == [
            "small:comparison", "agents:comparison", "regions:comparison"]
        status = records.read_json(h.args.output / "comparisons/small-status.json")
        assert status == {"available": False, "reason": "BOUNDED_COMPARISON_REFUSED"}
    else:
        with pytest.raises(records.Refused, match="comparison refusal requires owned quiescence"):
            owner.run_owner(h.args)
        report = records.read_json(h.args.output / "owner-summary.json")
        assert len(report["completed_roles"]) == 2 and not report["matrix_complete"]
        assert report["whole_owner_cleanup_certified"] is False
        assert not (h.args.output / "roles/2").exists()
        assert not (h.args.output / "comparisons/small-status.json").exists()
    assert all(value is None for value in report["unknown"].values())


@pytest.mark.parametrize("refusal", ["lease_exit", "post_lease_child"])
def test_owner_whole_cleanup_needs_successful_lease_exit_and_post_lease_quiescence(owner_fake, refusal):
    h, owner = owner_fake, owner_fake.owner
    h.lease_failure = refusal == "lease_exit"
    h.post_lease_child = refusal == "post_lease_child"
    with pytest.raises(records.Refused): owner.run_owner(h.args)
    report = records.read_json(h.args.output / "owner-summary.json")
    terminal = records.read_json(h.args.output / "terminal.json")
    assert len(report["completed_roles"]) == 6
    assert report["matrix_complete"] is False and report["whole_owner_cleanup_certified"] is False
    assert terminal["matrix_complete"] is False and terminal["whole_owner_cleanup_certified"] is False
    assert h.events.index(("exit", "lease", False)) < h.events.index(("exit", "cancellation", refusal == "lease_exit"))


def test_owner_post_terminal_guard_retains_original_bytes_and_adds_invalidation_sentinel(owner_fake, monkeypatch):
    h, owner = owner_fake, owner_fake.owner
    terminal_pin = {}
    def write_then_change(path, value, *args, **kwargs):
        pin = h.original_write(path, value, *args, **kwargs)
        if Path(path).name == "terminal.json":
            terminal_pin.update(pin)
            h.control_changed = True
        return pin
    monkeypatch.setattr(records, "write_new", write_then_change)
    with pytest.raises(records.Refused, match="terminal or post-terminal guard refused"):
        owner.run_owner(h.args)
    terminal = h.args.output / "terminal.json"
    assert records.hash_regular(terminal, records.SUMMARY_BYTES) == terminal_pin
    assert records.read_json(terminal)["matrix_complete"] is True
    assert (h.args.output / "terminal-failure.json").exists()
    # The later sentinel, not overwritten positive bytes, carries invalidation.
    assert records.read_json(h.args.output / "owner-summary.json")["whole_owner_cleanup_certified"] is True


def test_owner_hash_child_failure_preserves_core_role_summary_and_cannot_claim_completion(owner_fake):
    h, owner = owner_fake, owner_fake.owner
    h.hash_failure = True
    with pytest.raises(records.Refused, match="synthetic hash child refused"): owner.run_owner(h.args)
    summary = records.read_json(h.args.output / "roles/0/summary.json")
    report = records.read_json(h.args.output / "owner-summary.json")
    assert summary["role_complete"] and summary["completed_world_turn_boundaries"] == 97
    assert (h.args.output / "work/small/opaque.bin").read_bytes() == b"x"
    assert not (h.args.output / "roles/0/ordinary-inventory.json").exists()
    assert not (h.args.output / "roles/0/ordinary").exists()
    assert report["completed_roles"] == [] and report["matrix_complete"] is False
    assert report["whole_owner_cleanup_certified"] is False


def test_owner_joint_role_cap_includes_metadata_after_ordinary_hash_without_large_allocation(owner_fake, monkeypatch):
    h, owner = owner_fake, owner_fake.owner
    def charged_metadata(path, *args, **kwargs):
        value = h.original_inventory(path, *args, **kwargs)
        if Path(path) == h.args.output / "roles/0": value["bytes"] = 512 * 1024**2
        return value
    monkeypatch.setattr(records, "inventory", charged_metadata)
    with pytest.raises(records.Refused, match="joint whole role output cap"): owner.run_owner(h.args)
    assert (h.args.output / "roles/0/summary.json").exists()
    assert (h.args.output / "roles/0/ordinary-inventory.json").exists()
    assert records.read_json(h.args.output / "owner-summary.json")["completed_roles"] == []


def test_owner_joint_output_reserve_counts_metadata_inside_total_without_large_allocation(owner_fake, monkeypatch):
    h, owner = owner_fake, owner_fake.owner
    calls = []
    def charged_joint(path, *args, **kwargs):
        value = h.original_stat(path, *args, **kwargs)
        if Path(path) == h.args.output and "guard" in kwargs:
            calls.append(dict(kwargs))
            value["bytes"] = 3 * 1024**3 - 64 * 1024**2 + 1
        return value
    monkeypatch.setattr(records, "stat_inventory", charged_joint)
    with pytest.raises(records.Refused, match="joint aggregate publication reserve"): owner.run_owner(h.args)
    report = records.read_json(h.args.output / "owner-summary.json")
    assert len(report["completed_roles"]) == 1 and not report["matrix_complete"]
    assert calls[0]["maximum_bytes"] == 3 * 1024**3 - 64 * 1024**2 - 3 * 64 * 1024
    assert calls[0]["maximum_files"] == 5000 - 128 - 3


def test_owner_child_environment_forwards_only_selected_values_and_owned_paths(owner_fake):
    h, owner = owner_fake, owner_fake.owner
    owner.os.environ.update({"PATH": "/synthetic/path", "LANG": "C.UTF-8", "GITHUB_TOKEN": "invented-secret",
                             "LD_PRELOAD": "/untrusted/preload.so", "PYTHONPATH": "/untrusted/path",
                             "PYTHONSTARTUP": "/untrusted/startup.py", "AWS_SECRET_ACCESS_KEY": "invented-secret"})
    env = owner.child_environment(h.source, h.prefix)
    assert env["PATH"] == "/synthetic/path" and env["LANG"] == "C.UTF-8"
    assert env["PYTHONPATH"] == os.pathsep.join((str(h.source / "src"), str(h.control / "scripts")))
    assert env["VIRTUAL_ENV"] == str(h.prefix)
    assert env["PYTHONDONTWRITEBYTECODE"] == "1" and env["CHRONICLER_QUIET"] == "1"
    assert all(env[key] == value for key, value in core.CAPS.items())
    assert not {"GITHUB_TOKEN", "LD_PRELOAD", "PYTHONSTARTUP", "AWS_SECRET_ACCESS_KEY"} & set(env)
