"""Tiny metadata/fake contracts only: never construct a real World/runtime."""
import dataclasses
import importlib.util
from pathlib import Path
import random
from types import SimpleNamespace

import pytest


SPEC = importlib.util.spec_from_file_location(
    "passive090_test_source", Path(__file__).parents[1] / "scripts/current090_passive_profile.py")
P = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(P)


class Profile:
    def __init__(self, **kwargs):
        self.enabled = False
        self.trace = []
        self.stats = {("source.py", 7, "phase"): (1, 1, 0.1, 0.2, {})}

    def enable(self):
        assert not self.enabled
        self.enabled = True
        self.trace.append("on")

    def disable(self):
        self.enabled = False
        self.trace.append("off")

    def create_stats(self):
        assert not self.enabled


class Clock:
    def __init__(self): self.value = 0
    def __call__(self): self.value += 0.25; return self.value


def boundary(profiled):
    result = P.Boundary(profiled, clock_cpu=Clock(), clock_wall=Clock(), factory=Profile)
    result.bind(lambda path: path, {})
    return result


def toy_world(turn=0):
    return SimpleNamespace(turn=turn, regions=[SimpleNamespace(population=3)],
                           civilizations=["civ"], events_timeline=[], named_events=[])


def test_closed_schedule_cost_and_orders():
    rows = P.schedule()
    assert len(rows) == 6 and sum(row["turns"] for row in rows) == 582
    assert [(r["case"], r["role"]) for r in rows] == [
        ("small", "plain"), ("small", "profiled"), ("agents", "profiled"),
        ("agents", "plain"), ("regions", "plain"), ("regions", "profiled")]
    assert sum(16 for row in rows if row["role"] == "profiled") == 48
    for row in rows: P.validate_request(row)


@pytest.mark.parametrize("field,value", [("turns", 96), ("seed", 7), ("target", 1000),
                                        ("civs", True), ("role", "timed"), ("extra", 1)])
def test_unregistered_role_refuses(field, value):
    row = dict(P.schedule()[0]); row[field] = value
    with pytest.raises(P.Refused): P.validate_request(row)


@pytest.mark.parametrize("profiled", [False, True])
def test_exact_full_tail_windows_with_no_replay(profiled):
    b = boundary(profiled)
    w = toy_world()
    for turn in range(1, 98):
        w.turn = turn
        assert b.turn_end(w) is False
        assert [p.enabled for p in b.profiles] == [profiled and 8 <= turn < 16,
                                                   profiled and 88 <= turn < 96]
    result = b.finish()
    assert result["turns_observed"] == 97
    assert [(r["start"], r["end"]) for r in result["windows"]] == [(8, 16), (88, 96)]
    assert [r["turn"] for r in result["context"]] == [8, 16, 88, 96, 97]
    assert all(r["aggregate_region_population"] == 3 for r in result["context"])
    assert all(r["cpu_seconds"] > 0 and r["wall_seconds"] > 0 for r in result["windows"])
    assert result["profiled_ticks"] == (16 if profiled else 0)
    assert len(b.rows()) == (2 if profiled else 0)


def test_failed_boundary_stops_without_false_completion():
    b = boundary(True)
    for turn in range(1, 10): b.turn_end(toy_world(turn))
    assert b.profiles[0].enabled
    b.stop()
    assert not any(p.enabled for p in b.profiles)
    with pytest.raises(P.Refused, match="incomplete"): b.finish()
    assert b.last == 9
    with pytest.raises(P.Refused, match="sequence"): b.turn_end(toy_world(9))


def test_bind_once_and_profile_caps():
    b = boundary(True)
    with pytest.raises(P.Refused, match="bind once"): b.bind(lambda p: p, {})
    b.profiles[0].stats = {("x" * 2049, 1, "f"): (1, 1, 1., 1., {})}
    with pytest.raises(P.Refused, match="label cap"): b.rows()


def test_scaling_is_old_rounding_and_sync_after_all_regions():
    w = SimpleNamespace(regions=[SimpleNamespace(population=3, carrying_capacity=10),
                                  SimpleNamespace(population=5, carrying_capacity=20)],
                        civilizations=["a", "b"])
    calls = []
    out = P.scale_world(w, 2000, lambda civ, world: calls.append((civ, [r.population for r in world.regions])))
    assert out["base_population"] == 8 and out["multiplier"] == 250.
    assert out["region_population"] == [750, 1250] and out["region_capacity"] == [2500, 5000]
    assert calls == [("a", [750, 1250]), ("b", [750, 1250])]


def test_u16_refusal_precedes_any_civ_sync():
    w = SimpleNamespace(regions=[SimpleNamespace(population=1, carrying_capacity=100)], civilizations=["a"])
    with pytest.raises(P.Refused, match="u16"):
        P.scale_world(w, 2000, lambda *args: pytest.fail("must not reach physics/setup sync"))


def valid_rng():
    p = random.getstate()
    return {"python": [p[0], list(p[1]), p[2]],
            "numpy": ["MT19937", list(range(624)), 624, 0, 0.]}


@pytest.mark.parametrize("fault", ["kind", "word", "cursor", "gaussian", "boolword", "extra"])
def test_rng_metadata_refuses_malformed_actual_state(fault):
    r = valid_rng()
    if fault == "kind": r["numpy"][0] = "seed42"
    if fault == "word": r["numpy"][1].pop()
    if fault == "cursor": r["python"][1][-1] = 625
    if fault == "gaussian": r["python"][2] = float("nan")
    if fault == "boolword": r["numpy"][1][0] = True
    if fault == "extra": r["seed"] = 42
    with pytest.raises(P.Refused): P.validate_rng(r)


def test_rng_accepts_actual_snapshot_not_a_seed():
    r = valid_rng(); P.validate_rng(r)
    assert len(r["python"][1]) == 625 and len(r["numpy"][1]) == 624


def test_both_global_streams_replay_actual_shared_checkpoint_and_preserve_caller():
    class Words:
        def __init__(self, rows): self.rows = list(rows)
        def tolist(self): return list(self.rows)

    class NumpyMetadata:
        uint32 = "synthetic uint32"
        def __init__(self):
            self.state = ("MT19937", Words(range(624)), 624, 0, 0.)
            self.random = self
        def array(self, rows, dtype): assert dtype == self.uint32; return Words(rows)
        def get_state(self): return self.state
        def set_state(self, value): self.state = value

    saved = random.getstate()
    try:
        np = NumpyMetadata()
        shared = P.capture_rng(np)
        first = [random.random() for _ in range(4)]
        np.state = ("MT19937", Words([1] * 624), 7, 1, 1.)
        P.restore_rng(shared, np)
        assert P.capture_rng(np) == shared
        assert first == [random.random() for _ in range(4)]
    finally:
        random.setstate(saved)


def test_profile_output_refuses_missing_files_or_raw_bundle_difference():
    proof = {key: "same" for key in ("logical_output", "initial_rng", "final_rng", "state", "run_result", "identity")}
    proof.update(initial_rng=valid_rng(), final_rng=valid_rng())
    for count, problems, raw in ((0, [], []), (1, ["missing"], []), (1, [], ["raw differs"])):
        with pytest.raises(P.Refused, match="ordinary"):
            P.profile_equivalent(proof, dict(proof), lambda a, b: (count, list(problems)),
                                 lambda a, b: list(raw), Path("a"), Path("b"))


class NativeBytes:
    def __init__(self): self.data = b"native RNG slots queues trips"
    def checkpoint_state(self): return self.data


class ToyModel:
    model_fields = {"turn": None}
    def __init__(self):
        self.turn = 97
        self.__pydantic_private__ = {}
        self.__pydantic_extra__ = None
        self.__pydantic_fields_set__ = {"turn"}


class ToyBridge:
    __module__ = "chronicler.test_passive_metadata"
    def __init__(self): self._sim = NativeBytes(); self.output = Path("/same/run")


@dataclasses.dataclass
class Entry:
    turn: int = 97
    text: str = "retained"
    importance: int = 5
    entry_type: str = "event"


class ToyMemory:
    __module__ = "chronicler.test_passive_metadata"
    def __init__(self):
        e = Entry()
        self.entries, self.reflections = [e], []
        self._encoded = {"entries": [(e, e.turn, e.text, e.importance, e.entry_type, "actual JSON")]}


@dataclasses.dataclass
class ToyState:
    world: object
    agent_bridge: object
    memories: dict
    markers: dict
    run_config: dict
    history: list


def state():
    w, b = ToyModel(), ToyBridge()
    w.__pydantic_private__["_war_roster_sim"] = id(b._sim)
    w.__pydantic_private__["_agent_bridge"] = b
    return ToyState(w, b, {"civ": ToyMemory()}, {"war_roster_bound": True},
                    {"output": "/same/run", "feature": False}, [{"turn": 97}])


def fingerprint(s): return P.StateFingerprint(s, (NativeBytes,)).result()


def test_detached_marker_token_preserves_original_and_native_graph():
    a, b = state(), state()
    ai, bi = a.world.__pydantic_private__["_war_roster_sim"], b.world.__pydantic_private__["_war_roster_sim"]
    assert ai != bi and fingerprint(a) == fingerprint(b)
    assert a.world.__pydantic_private__["_war_roster_sim"] == ai
    assert b.world.__pydantic_private__["_war_roster_sim"] == bi
    assert a.markers == b.markers == {"war_roster_bound": True}


@pytest.mark.parametrize("fault", ["false", "integer", "unknown", "duplicate", "unrelated"])
def test_unknown_or_unbound_marker_refuses(fault):
    s = state()
    if fault == "false": s.markers["war_roster_bound"] = False
    if fault == "integer": s.markers["war_roster_bound"] = 1
    if fault == "unknown": s.markers["another"] = True
    if fault == "duplicate": s.world._war_roster_sim = id(s.agent_bridge._sim)
    if fault == "unrelated": s.world.__pydantic_private__["_war_roster_sim"] += 1
    with pytest.raises(P.Refused): fingerprint(s)


@pytest.mark.parametrize("fault", ["native", "private", "extra", "config", "path", "history",
                                        "cache_text", "signedzero", "alias", "dynamic"])
def test_every_carried_native_private_cache_and_path_change_matters(fault):
    a, b = state(), state()
    if fault == "native": b.agent_bridge._sim.data += b"changed"
    if fault == "private": b.world.__pydantic_private__["pending"] = [1]
    if fault == "extra": b.world.__pydantic_extra__ = {"x": 1}
    if fault == "config": b.run_config["feature"] = True
    if fault == "path": b.agent_bridge.output = Path("/other/run")
    if fault == "history": b.history[0]["turn"] = 96
    if fault == "cache_text":
        row = b.memories["civ"]._encoded["entries"][0]
        b.memories["civ"]._encoded["entries"][0] = (*row[:-1], "changed JSON")
    if fault == "signedzero": a.run_config["zero"] = 0.; b.run_config["zero"] = -0.
    if fault == "alias":
        x = []; a.history = [x, x]; b.history = [[], []]
    if fault == "dynamic": b.extra = ["must be retained"]
    assert fingerprint(a) != fingerprint(b)


def test_cycle_is_retained_and_nested_boundaries_are_unambiguous():
    a, b = state(), state()
    x = []; x.append(x); a.extra = x
    y = []; y.append(y); b.extra = y
    assert fingerprint(a) == fingerprint(b)
    a.extra = [[], [1], 2]; b.extra = [[], [1, 2]]
    assert fingerprint(a) != fingerprint(b)


def test_encoded_entry_identity_is_not_replaced_by_equal_content():
    s = state(); row = s.memories["civ"]._encoded["entries"][0]
    s.memories["civ"]._encoded["entries"][0] = (Entry(), *row[1:])
    with pytest.raises(P.Refused, match="encoder identity"): fingerprint(s)


def test_unsupported_state_has_no_repr_or_id_fallback():
    s = state(); s.extra = object()
    with pytest.raises(P.Refused, match="unsupported"): fingerprint(s)


def test_ordered_dict_content_and_unordered_set_are_distinguished():
    a, b = state(), state()
    a.extra = {("b", 2), ("a", 1)}; b.extra = {("a", 1), ("b", 2)}
    assert fingerprint(a) == fingerprint(b)
    a.extra = {"a": 1, "b": 2}; b.extra = {"b": 2, "a": 1}
    assert fingerprint(a) != fingerprint(b)


def test_old_comparator_is_called_without_new_exclusions_or_normalizer():
    calls = []
    def compare(a, b): calls.append((a, b)); return 4, []
    def raw(a, b): calls.append(("raw", a, b)); return []
    proof = {key: "same" for key in ("logical_output", "initial_rng", "final_rng", "state", "run_result", "identity")}
    proof.update(initial_rng=valid_rng(), final_rng=valid_rng())
    out = P.profile_equivalent(proof, dict(proof), compare, raw, Path("a"), Path("b"))
    assert out == {"checked_files": 4, "differences": 0, "instrumentation_equal": True}
    assert calls == [(Path("a"), Path("b")), ("raw", Path("a"), Path("b"))]
    bad = dict(proof); bad["state"] = "changed"
    with pytest.raises(P.Refused, match="state"):
        P.profile_equivalent(proof, bad, compare, raw, Path("a"), Path("b"))


def test_null_approval_refuses_before_any_project_native_or_path_access():
    assert P.EXECUTION_APPROVAL is None
    with pytest.raises(P.Refused, match="not approved"):
        P.run_role({}, ordinary=None, checkpoint=None, shared_rng=None, admission=None)


def test_result_keeps_every_field_and_literal_logical_path_json_safe():
    @dataclasses.dataclass
    class ResultMetadata:
        output_dir: Path
        total_turns: int
        actions: dict
    result = ResultMetadata(Path("/same/absolute/run"), 97, {"develop": 8})
    assert P.result_record(result) == {"output_dir": "/same/absolute/run", "total_turns": 97,
                                       "actions": {"develop": 8}}
    P.canonical_bytes(P.result_record(result))
    with pytest.raises(P.Refused, match="path type"):
        P.result_record(ResultMetadata("/same/absolute/run", 97, {}))


def test_no_native_observer_calls_between_physics_turns_in_either_role():
    calls = []
    def forbidden():
        calls.append("unexpected native read")
        pytest.fail("no observer native call between physics turns")
    for profiled in (False, True):
        b = boundary(profiled)
        world = toy_world()
        world.regions = [SimpleNamespace(population=3) for _ in range(12)]
        world._agent_bridge = SimpleNamespace(_sim=SimpleNamespace(get_region_populations=forbidden))
        # A leftover callable must not be consulted either.
        b.population_reader = lambda value: forbidden()
        for turn in range(1, 98):
            world.turn = turn
            b.turn_end(world)
        summary = b.finish()
        assert [row["turn"] for row in summary["context"]] == [8, 16, 88, 96, 97]
        assert all(row["aggregate_region_population"] == 36 for row in summary["context"])
        assert all("actual_native" not in row for row in summary["context"])
    assert calls == []


@pytest.mark.parametrize("fault", [None, "row_count", "columns", "order", "bool", "null", "negative"])
def test_native_region_count_reader_bounds_and_retains_extinction(fault):
    class Column:
        null_count = 0
        def __init__(self, values): self.values = values
        def to_pylist(self): return self.values
    columns = {"region_id": Column(list(range(12))), "alive_count": Column([0] * 12)}
    batch = SimpleNamespace(num_rows=12, num_columns=2, schema=SimpleNamespace(names=["region_id", "alive_count"]),
                            column=lambda name: columns[name])
    calls = []
    sim = SimpleNamespace(get_region_populations=lambda: calls.append("read") or batch)
    if fault == "row_count": batch.num_rows = 1000000
    if fault == "columns": batch.schema.names.reverse()
    if fault == "order": columns["region_id"].values.reverse()
    if fault == "bool": columns["alive_count"].values[0] = True
    if fault == "null": columns["alive_count"].null_count = 1
    if fault == "negative": columns["alive_count"].values[0] = -1
    if fault is None:
        assert P.native_region_counts(sim, 12) == {"region_ids": list(range(12)), "alive_counts": [0] * 12,
                                                  "in_domain_alive_count": 0}
    else:
        with pytest.raises(P.Refused): P.native_region_counts(sim, 12)
    assert calls == ["read"]


def test_window_clocks_exclude_costly_python_context_in_both_roles():
    class AdvancingClock:
        value = 0.
        def __call__(self): return self.value
    results = []
    for profiled in (False, True):
        cpu, wall = AdvancingClock(), AdvancingClock()
        b = P.Boundary(profiled, clock_cpu=cpu, clock_wall=wall, factory=Profile)
        calls, world = [], toy_world()
        class CostlyRegion:
            @property
            def population(self):
                assert not any(p.enabled for p in b.profiles)
                calls.append(world.turn)
                cpu.value += 100.
                wall.value += 200.
                return 9
        world.regions = [CostlyRegion()]
        b.bind(lambda path: path, {})
        for turn in range(1, 98):
            cpu.value += 1.
            wall.value += 2.
            world.turn = turn
            b.turn_end(world)
        summary = b.finish()
        assert calls == [8, 16, 88, 96, 97]
        times = [(row["cpu_seconds"], row["wall_seconds"]) for row in summary["windows"]]
        assert times == [(8., 16.), (8., 16.)]
        results.append(times)
    assert results[0] == results[1]


def test_mutable_bytearray_aliases_are_part_of_carried_graph():
    a, b = state(), state()
    buf = bytearray(b"shared")
    a.extra = [buf, buf]
    b.extra = [bytearray(b"shared"), bytearray(b"shared")]
    assert fingerprint(a) != fingerprint(b)


@pytest.mark.parametrize("stream,index", [("python", 2), ("numpy", 4)])
def test_signed_zero_gaussian_cache_is_not_equal_or_normalized(stream, index):
    left, right = valid_rng(), valid_rng()
    left[stream][index], right[stream][index] = -0., 0.
    assert not P.same_rng(left, right)
    proof = {key: "same" for key in ("logical_output", "state", "run_result", "identity")}
    a = dict(proof, initial_rng=left, final_rng=left)
    b = dict(proof, initial_rng=right, final_rng=right)
    with pytest.raises(P.Refused, match="initial_rng"):
        P.profile_equivalent(a, b, lambda *args: (1, []), lambda *args: [], Path("a"), Path("b"))


def test_marker_refuses_an_unadmitted_supported_dataclass_simulator():
    @dataclasses.dataclass
    class OtherSimulator:
        payload: bytes = b"not the selected compiled class"
    s = state(); s.agent_bridge._sim = OtherSimulator()
    s.world.__pydantic_private__["_war_roster_sim"] = id(s.agent_bridge._sim)
    with pytest.raises(P.Refused, match="admitted AgentSimulator"): fingerprint(s)


@pytest.mark.parametrize("base", [dict, list, tuple, set, frozenset, P.deque, random.Random, type(Path())])
def test_stateful_unregistered_container_rng_and_path_subclasses_refuse(base):
    class Stateful(base):
        pass
    if base is random.Random: value = Stateful(1)
    elif base is type(Path()): value = Stateful("/same/path")
    else: value = Stateful()
    value.extra_flag = "would be silently lost by an isinstance-only branch"
    s = state(); s.extra = value
    with pytest.raises(P.Refused, match="subclass"): fingerprint(s)


def test_explicit_counter_extra_state_is_preserved():
    a, b = state(), state()
    a.extra = P.Counter({"x": 1}); b.extra = P.Counter({"x": 1})
    a.extra.note, b.extra.note = "one", "two"
    assert fingerprint(a) != fingerprint(b)


class ArrayMetadata:
    __module__ = "numpy.synthetic_metadata_contract"
    def __init__(self, content=b"abcd", base=None, offset=0):
        self.dtype = SimpleNamespace(hasobject=False, fields=None, subdtype=None, metadata=None,
                                     str="|u1", itemsize=1, alignment=1)
        self.flags = SimpleNamespace(c_contiguous=True, f_contiguous=True,
                                      num=1028 if base is None else 1024, owndata=base is None)
        self.shape, self.strides = (len(content),), (1,)
        self.size = self.nbytes = len(content)
        self.base, self.content = base, content
        self.__array_interface__ = {"data": (1000 + offset, False)}
    def tobytes(self, order="C"): return self.content


class ScalarMetadata:
    __module__ = "numpy.synthetic_metadata_contract"


def numpy_metadata_api():
    api = SimpleNamespace(ndarray=ArrayMetadata)
    for name in ("bool_", "int8", "int16", "int32", "int64", "uint8", "uint16", "uint32", "uint64",
                 "float16", "float32", "float64", "complex64", "complex128", "datetime64",
                 "timedelta64", "bytes_", "str_"):
        setattr(api, name, ScalarMetadata)
    def probe(buffer, dtype, count):
        assert type(buffer) is memoryview and dtype is ScalarMetadata and count == 0
        return SimpleNamespace(__array_interface__={"data": (1000, False)})
    api.frombuffer = probe
    return api


def numpy_fingerprint(s): return P.StateFingerprint(s, (NativeBytes,), numpy_metadata_api()).result()


@pytest.mark.parametrize("fault", ["stride", "writable", "offset", "base_alias"])
def test_exact_array_storage_geometry_flags_and_mutable_base_alias_matter(fault):
    a, b = state(), state()
    a.extra = ArrayMetadata(b"ab", base=ArrayMetadata(b"abcdefgh"))
    b.extra = ArrayMetadata(b"ab", base=ArrayMetadata(b"abcdefgh"))
    assert numpy_fingerprint(a) == numpy_fingerprint(b)
    if fault == "stride": b.extra.strides = (2,)
    if fault == "writable": b.extra.flags.num = 4
    if fault == "offset": b.extra.__array_interface__["data"] = (1002, False)
    if fault == "base_alias":
        shared = ArrayMetadata(b"abcdefgh")
        a.extra = [ArrayMetadata(b"ab", base=shared), ArrayMetadata(b"ab", base=shared)]
        b.extra = [ArrayMetadata(b"ab", base=ArrayMetadata(b"abcdefgh")),
                   ArrayMetadata(b"ab", base=ArrayMetadata(b"abcdefgh"))]
    assert numpy_fingerprint(a) != numpy_fingerprint(b)


@pytest.mark.parametrize("fault", ["unadmitted", "subclass", "object", "structured", "metadata",
                                        "noncontiguous_base", "outside_base"])
def test_numpy_unregistered_types_dtype_or_unproved_storage_refuse(fault):
    s = state(); value = ArrayMetadata()
    if fault == "subclass":
        class Stateful(ArrayMetadata):
            __module__ = "numpy.synthetic_metadata_contract"
        value = Stateful(); value.extra = "not discarded"
    if fault == "object": value.dtype.hasobject = True
    if fault == "structured": value.dtype.fields = {"field": 1}
    if fault == "metadata": value.dtype.metadata = {"extra": 1}
    if fault == "noncontiguous_base":
        value.base = ArrayMetadata(b"abcdefgh")
        value.base.flags.c_contiguous = value.base.flags.f_contiguous = False
    if fault == "outside_base": value.base = ArrayMetadata(b"a")
    s.extra = value
    with pytest.raises(P.Refused):
        if fault == "unadmitted": fingerprint(s)
        else: numpy_fingerprint(s)


def test_memoryview_preserves_readonly_and_buffer_object_graph_without_real_numpy():
    a, b = state(), state()
    a.extra = memoryview(bytearray(b"ab"))
    b.extra = memoryview(b"ab")
    assert numpy_fingerprint(a) != numpy_fingerprint(b)


def test_dataclass_subclass_extra_slots_are_not_lost():
    @dataclasses.dataclass
    class Base:
        x: int = 1
    class Slotted(Base):
        __slots__ = ("flag",)
    a, b = state(), state()
    a.extra, b.extra = Slotted(), Slotted()
    a.extra.flag, b.extra.flag = "one", "two"
    assert fingerprint(a) != fingerprint(b)


def test_decoded_project_fields_do_not_invoke_an_omitting_reducer():
    class AlreadyDecoded:
        __module__ = "chronicler.synthetic_metadata_contract"
        def __getstate__(self): return {"x": self.x}
    a, b = state(), state()
    a.extra, b.extra = AlreadyDecoded(), AlreadyDecoded()
    a.extra.x = b.extra.x = 1
    a.extra.flag, b.extra.flag = "one", "two"
    assert fingerprint(a) != fingerprint(b)


def test_model_like_extra_slots_are_not_lost():
    class WithSlot(ToyModel):
        __slots__ = ("extra_flag",)
    a, b = state(), state()
    for target, flag in ((a, "one"), (b, "two")):
        target.world = WithSlot()
        target.world.__pydantic_private__["_war_roster_sim"] = id(target.agent_bridge._sim)
        target.world.extra_flag = flag
    assert fingerprint(a) != fingerprint(b)


def test_qualified_path_type_keeps_capabilities_with_identical_text():
    a, b = state(), state()
    a.extra = P.PosixPath("/same")
    b.extra = P.PurePosixPath("/same")
    assert str(a.extra) == str(b.extra) and fingerprint(a) != fingerprint(b)


def test_hidden_slot_storage_refuses_instead_of_skipping_the_base_value():
    class Base:
        __module__ = "chronicler.synthetic_metadata_contract"
        __slots__ = ("value",)
    class Hidden(Base):
        __module__ = "chronicler.synthetic_metadata_contract"
        __slots__ = ("value",)
    s = state(); s.extra = Hidden()
    Base.value.__set__(s.extra, "physical base slot")
    Hidden.value.__set__(s.extra, "different physical child slot")
    with pytest.raises(P.Refused, match="duplicate slot"): fingerprint(s)


def test_inherited_slot_storage_without_redeclaration_is_retained():
    class Base:
        __module__ = "chronicler.synthetic_metadata_contract"
        __slots__ = ("value",)
    class Inherited(Base):
        __module__ = "chronicler.synthetic_metadata_contract"
        __slots__ = ()
    a, b = state(), state()
    a.extra, b.extra = Inherited(), Inherited()
    a.extra.value, b.extra.value = "one", "two"
    assert fingerprint(a) != fingerprint(b)


def test_unanchored_nonowning_array_refuses_even_when_base_is_none():
    s = state(); s.extra = ArrayMetadata()
    s.extra.flags.owndata = False
    s.extra.flags.num &= ~4
    with pytest.raises(P.Refused, match="unanchored"): numpy_fingerprint(s)
