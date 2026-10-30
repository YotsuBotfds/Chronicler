"""Explicit ordinary-guard contracts. All carriers/native bytes are pure fakes."""
from collections import deque
from copy import deepcopy
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import wholeturn_state_proof as old
from wholeturn_live_proof import LiveFingerprint
import wholeturn_cache_identity as cache
import wholeturn_cache_protocol as p
import wholeturn_cache_worker as worker
import wholeturn_cache_pilot as owner


class Carrier:
    __module__ = "chronicler.fake"


class Bridge(Carrier):
    __module__ = "chronicler.fake"


class NativeBytes:
    """Explicit stand-in; no compiled-origin or real Native claim."""
    def checkpoint_state(self):
        return b"fake-native-persistent-bytes"


def state(form="window", *, cache_state="DICT"):
    root, world, bridge = Carrier(), Carrier(), Bridge()
    sim = NativeBytes()
    events = [{"text": "a", "weight": -0.0}]
    named = {7: {"name": "n"}}
    stats = {"counts": [1, 2], "weight": -0.0}
    bridge._sim = sim
    bridge._event_window = deque([events], maxlen=8)
    bridge._window_stats_cache = {}
    bridge._named_actor_memo = None
    if form == "window":
        bridge._window_stats_cache[id(events)] = (events, 1, stats)
    elif form == "region":
        bridge._named_actor_memo = {(id(events), id(named)): (events, named, stats)}
    elif form == "lists":
        lists = (events, events)
        bridge._named_actor_memo = {("lists", tuple(id(x) for x in lists), id(named)): (lists, named, stats)}
    else:
        raise AssertionError("fake fixture form")
    if cache_state == "ABSENT":
        del bridge._window_stats_cache
    elif cache_state == "NONE":
        bridge._window_stats_cache = None
    elif cache_state == "EMPTY":
        bridge._window_stats_cache = {}
    world.regions = list(range(8))
    world._war_roster_sim = id(sim)
    root.world, root.agent_bridge = world, bridge
    root.memories, root.markers = {}, {"war_roster_bound": True}
    return root


def fingerprint(root):
    raw = cache.ObservedLiveFingerprint(root, (NativeBytes,))
    raw_result = raw.result()
    binding = cache.CacheBindings(raw, Bridge)
    bound = cache.ObservedLiveFingerprint(root, (NativeBytes,), bindings=binding)
    result = bound.result()
    witness = binding.witness(bound)
    fields = cache.merge_field_segments(raw, bound)
    return raw, raw_result, bound, result, witness, fields


@pytest.mark.parametrize("form", ["window", "region", "lists"])
def test_distinct_real_ids_equal_bound_graphs_and_keep_raw_evidence(form):
    left, right = state(form), state(form)
    a, b = fingerprint(left), fingerprint(right)
    assert a[1]["sha256"] != b[1]["sha256"]
    assert a[3] == b[3]
    assert a[4]["entries"][0]["raw_key"] != b[4]["entries"][0]["raw_key"]
    assert a[4]["entries"][0]["event_refs"] == b[4]["entries"][0]["event_refs"]


@pytest.mark.parametrize("form", ["window", "region", "lists"])
def test_raw_observer_matches_unchanged_legacy_bytes_and_all_counters(form):
    root = state(form)
    legacy = LiveFingerprint(root, (NativeBytes,), None).result()
    a = fingerprint(root)
    assert a[1] == legacy
    assert {k: v for k, v in a[1].items() if k != "sha256"} == {k: v for k, v in a[3].items() if k != "sha256"}
    assert a[0].hash.digest() == bytes.fromhex(legacy["sha256"])


@pytest.mark.parametrize("change", ["stats", "events", "cached_length", "order", "alias", "signed_zero"])
def test_payload_bits_lengths_entry_order_and_alias_changes_stay_visible(change):
    left, right = state(), state()
    bridge = right.agent_bridge
    key, value = next(iter(bridge._window_stats_cache.items()))
    if change == "stats": value[2]["counts"][0] += 1
    elif change == "events": value[0].append({"text": "b"})
    elif change == "cached_length": bridge._window_stats_cache[key] = (value[0], 999, value[2])
    elif change == "signed_zero": value[2]["weight"] = 0.0
    elif change == "alias": value[2]["counts"] = value[0]
    else:
        other = [{"text": "b"}]
        left.agent_bridge._window_stats_cache[id(other)] = (other, 1, {"k": 2})
        bridge._window_stats_cache = {id(other): (other, 1, {"k": 2}), key: value}
    assert fingerprint(left)[3]["sha256"] != fingerprint(right)[3]["sha256"]


def test_unrelated_integer_equal_to_address_keeps_original_integer_encoding():
    left, right = state(), state()
    left.world.unrelated = next(iter(left.agent_bridge._window_stats_cache))
    right.world.unrelated = next(iter(right.agent_bridge._window_stats_cache))
    assert fingerprint(left)[3]["sha256"] != fingerprint(right)[3]["sha256"]


def test_absent_none_and_empty_cache_are_distinct():
    values = [fingerprint(state(cache_state=kind)) for kind in ("ABSENT", "NONE", "EMPTY")]
    assert len({row[3]["sha256"] for row in values}) == 3
    assert [v[4]["states"]["_window_stats_cache"] for v in values] == ["ABSENT", "NONE", "DICT"]


def test_stale_cached_length_and_off_window_retention_are_observed_not_repaired():
    root = state()
    bridge = root.agent_bridge
    key, value = next(iter(bridge._window_stats_cache.items()))
    bridge._window_stats_cache[key] = (value[0], 42, value[2])
    bridge._event_window.clear()
    entry = fingerprint(root)[4]["entries"][0]
    assert entry["cached_length"] == 42 and entry["event_counts"] == [1]
    assert entry["window_memberships"] == [[]]
    assert bridge._window_stats_cache[key][1] == 42


@pytest.mark.parametrize("kind", ["bool", "wrong_id", "equal_other_list", "bad_value", "bad_length", "foreign_mapping"])
def test_invalid_window_bindings_refuse_without_rewriting_state(kind):
    root = state()
    bridge = root.agent_bridge
    key, value = next(iter(bridge._window_stats_cache.items()))
    if kind == "bool": bridge._window_stats_cache = {True: value}
    elif kind == "wrong_id": bridge._window_stats_cache = {key + 1: value}
    elif kind == "equal_other_list": bridge._window_stats_cache[key] = (list(value[0]), 1, value[2])
    elif kind == "bad_value": bridge._window_stats_cache[key] = list(value)
    elif kind == "bad_length": bridge._window_stats_cache[key] = (value[0], True, value[2])
    else:
        class Foreign(dict): pass
        bridge._window_stats_cache = Foreign(bridge._window_stats_cache)
    original = bridge._window_stats_cache
    with pytest.raises(old.Refused): fingerprint(root)
    assert bridge._window_stats_cache is original


@pytest.mark.parametrize("form", ["region", "lists"])
def test_invalid_nested_memo_ids_refuse(form):
    root = state(form)
    memo = root.agent_bridge._named_actor_memo
    key, value = next(iter(memo.items()))
    bad = (key[0] + 1, key[1]) if form == "region" else ("lists", (key[1][0] + 1, key[1][1]), key[2])
    root.agent_bridge._named_actor_memo = {bad: value}
    with pytest.raises(old.Refused, match="identity binding"): fingerprint(root)


def test_orphan_index_referent_refuses():
    root = state()
    raw = cache.ObservedLiveFingerprint(root, (NativeBytes,))
    raw.result()
    events = next(iter(root.agent_bridge._window_stats_cache.values()))[0]
    del raw.memo[id(events)]
    with pytest.raises(old.Refused, match="orphan"): cache.CacheBindings(raw, Bridge)


def test_foreign_bridge_class_refuses():
    raw = cache.ObservedLiveFingerprint(state(), (NativeBytes,))
    raw.result()
    with pytest.raises(old.Refused, match="bridge class"): cache.CacheBindings(raw, Carrier)


def test_shared_key_tuple_retains_global_alias_and_reference_ordinals():
    left, right = state("region"), state("region")
    for root in (left, right):
        key = next(iter(root.agent_bridge._named_actor_memo))
        root.world.key_alias = key
    a, b = fingerprint(left), fingerprint(right)
    assert a[3] == b[3]
    assert a[2].memo[id(left.world.key_alias)] == a[4]["entries"][0]["key_ref_ordinal"]
    right.world.key_alias = tuple(list(right.world.key_alias))
    assert fingerprint(right)[3]["sha256"] != a[3]["sha256"]


def test_conflicting_shared_key_container_descriptor_refuses():
    root = state("region")
    raw = cache.ObservedLiveFingerprint(root, (NativeBytes,)); raw.result()
    binding = cache.CacheBindings(raw, Bridge)
    key = next(iter(root.agent_bridge._named_actor_memo))
    with pytest.raises(old.Refused, match="conflicting"):
        binding._tuple(key, {0: 999, 1: 998})


def test_cache_dictionary_alias_is_ambiguous_and_refuses():
    root = state()
    root.agent_bridge._named_actor_memo = root.agent_bridge._window_stats_cache
    with pytest.raises(old.Refused, match="aliased cache"): fingerprint(root)


def test_global_field_segment_retains_prior_alias_instead_of_rerooting():
    root = state()
    shared = [1, 2]
    root.world.first = shared
    root.agent_bridge.later = shared
    result = fingerprint(root)
    rows = {r["path"]: r for r in result[5]}
    first = rows["World.public.first"]["validated_bound"]
    later = rows["AgentBridge.__dict__.later"]["validated_bound"]
    assert first["sha256"] != later["sha256"] and first["tokens"] > later["tokens"]
    assert cache.SEGMENT_SCOPE == "SAME_GLOBAL_EMITTED_TOKEN_SEGMENT_WITH_REFERENCE_ORDINALS"


@pytest.mark.parametrize("cap", ["records", "field_bytes", "binding_bytes"])
def test_diagnostic_caps_refuse_instead_of_sampling(cap, monkeypatch):
    monkeypatch.setattr(cache, {"records": "FIELD_RECORDS", "field_bytes": "FIELD_BYTES", "binding_bytes": "BINDING_BYTES"}[cap], 1)
    with pytest.raises(old.Refused): fingerprint(state())


def test_first_field_difference_reports_order_and_count_without_normalization():
    a = fingerprint(state())[5]
    b = deepcopy(a); b[0]["path"] += "changed"
    assert cache.first_field_difference(a, b)["kind"] == "FIELD_OWNERSHIP_OR_ORDER_DIFFERS"
    assert cache.first_field_difference(a, a[:-1])["kind"] == "FIELD_RECORD_COUNT_DIFFERS"


def fake_capture(monkeypatch, *, mutate=False, fail_write=False):
    root = state()
    counts = {"save": 0, "write": 0, "load": 0}
    rng = {"python": [3, [0] * 624 + [0], None], "numpy": ["MT19937", [0] * 624, 0, 0, 0.0]}
    monkeypatch.setattr(old, "capture_rng", lambda np: deepcopy(rng))
    monkeypatch.setattr(old, "native_region_counts", lambda sim, regions: {"fake": True})
    def write(path, current):
        counts["write"] += 1
        if fail_write: raise OSError("fake first write failure")
        if mutate: next(iter(current.agent_bridge._window_stats_cache.values()))[2]["counts"].append(9)
    def load(path, allow_mismatch):
        counts["load"] += 1
        return SimpleNamespace(exact=True, state=root, header={"sections": [{"name": "native.AgentSimulator"}]})
    rc = SimpleNamespace(write_checkpoint=write, read_checkpoint=load, _markers=lambda state: {"war_roster_bound": True})
    def save(path):
        counts["save"] += 1
        rc.write_checkpoint(path, root)
        return path
    ticks = iter(range(1, 1000))
    return root, counts, rng, rc, save, write, lambda: next(ticks)


def test_capture_one_save_load_old_and_bound_invariance_and_raw_subphase_endpoints(monkeypatch):
    root, counts, rng, rc, save, original, clock = fake_capture(monkeypatch)
    progress = {}
    outcome = cache.capture_terminal(save, "fake.ckpt", rc, (NativeBytes,), None, expected_rng=rng,
        bridge_class=Bridge, progress=progress, cpu=clock, wall=clock)
    assert counts == {"save": 1, "write": 1, "load": 1} and rc.write_checkpoint is original
    assert outcome["old_raw_live"]["sha256"] != outcome["live"]["sha256"]
    assert outcome["extra_physics_runs"] == 0 and progress["own_old_raw_write_invariance"]
    assert list(progress["subphases"]) == ["old_live_before", "bound_live_before", "checkpoint_write", "old_live_after", "bound_live_after", "checkpoint_load", "decoded_fingerprint"]
    assert all(r["status"] == "COMPLETE" and r["clock"]["numerically_valid"] for r in progress["subphases"].values())


@pytest.mark.parametrize("failure", ["write", "mutate"])
def test_first_capture_failure_keeps_old_hash_progress_and_no_replay(failure, monkeypatch):
    root, counts, rng, rc, save, original, clock = fake_capture(monkeypatch, mutate=failure == "mutate", fail_write=failure == "write")
    progress = {}
    with pytest.raises((old.Refused, OSError)):
        cache.capture_terminal(save, "fake.ckpt", rc, (NativeBytes,), None, expected_rng=rng,
            bridge_class=Bridge, progress=progress, cpu=clock, wall=clock)
    assert "old_before" in progress and "bound_before" in progress and progress["failure"]
    assert counts == {"save": 1, "write": 1, "load": 0} and rc.write_checkpoint is original
    assert progress["extra_physics_runs"] == 0
    if failure == "write": assert progress["subphases"]["checkpoint_write"]["status"] == "FAILED"


def test_unready_registration_blocks_collection_and_fixed_pilot_is_two_roles(monkeypatch, tmp_path):
    reg = p.read_json(ROOT / p.REGISTRATION)
    p.validate_registration(reg)
    reg = {**reg, "root_decision": None}
    assert reg["root_decision"] is None
    controller = tmp_path / "unready-controller"
    p.write_new(controller / p.REGISTRATION, reg)
    q = p.schedule(reg)
    assert [(r["regions"], r["civilizations"], r["seed"], r["turns"], r["profiled"], r["arm"]) for r in q] == [(8, 4, 42, 200, False, "baseline"), (8, 4, 42, 200, False, "candidate")]
    assert sum(r["turns"] for r in q) == 400
    monkeypatch.setattr(owner.build, "github_context", lambda *_: pytest.fail("UNREADY reached Git/context"))
    monkeypatch.setattr(owner, "official_metadata", lambda *_: pytest.fail("UNREADY reached HTTP"))
    with pytest.raises(p.Refused, match="DEFERRED"): owner.admission(controller, tmp_path / "runtime")
    assert not (tmp_path / "runtime").exists()


def test_bound_graph_mismatch_retains_locator_and_old_hash_diagnostics():
    a, b = fingerprint(state()), fingerprint(state())
    def proof(row):
        return {"encoding": cache.ENCODING, "old_raw_live": row[1], "live": row[3], "decoded": {"sha256": "a" * 64}, "coverage": {"closed": True}, "SAME_GLOBAL_field_token_segments": row[5]}
    assert worker.proof_differences(proof(a), proof(b)) == []
    changed = state(); changed.world.other = 99
    c = proof(fingerprint(changed))
    failures = worker.proof_differences(proof(a), c)
    assert failures[0]["component"] == "live"
    assert failures[-1]["first_recorded_field_segment_difference"] is not None


def test_pair_failure_writes_structured_diagnostic_before_ordinary_comparison(monkeypatch, tmp_path):
    reg = p.read_json(ROOT / p.REGISTRATION)
    requests = p.schedule(reg)
    context = {"GITHUB_SHA": "1" * 40}
    rows = []
    for request in requests:
        root = state()
        if request["arm"] == "candidate": root.world.changed_payload = 7
        view = fingerprint(root)
        identity = {"source": {"git_sha": request["source_commit"]}, "environment": {}, "native": {"state_layouts": {}}}
        rows.append({"request": request, "run_complete": True, "proof_complete": True,
            "status": "COMPLETE_ROLE_PENDING_PAIR_COMPARISON", "github": context,
            "controller_commit": context["GITHUB_SHA"], "runtime_identity": identity,
            "checkpoint_identity": identity, "run_config": {}, "effective_flags": {},
            "initial_rng": {}, "final_rng": {},
            "proof": {"encoding": cache.ENCODING, "old_raw_live": view[1], "live": view[3],
                "decoded": {"same": True}, "coverage": {"same": True}, "SAME_GLOBAL_field_token_segments": view[5]}})
    values = {"build": {"measured_root": str(tmp_path)}, "left": rows[0], "right": rows[1]}
    monkeypatch.setattr(p, "load_registration", lambda _: reg)
    monkeypatch.setattr(worker.build, "github_context", lambda _: context)
    monkeypatch.setattr(worker.build, "recheck_build", lambda _: None)
    monkeypatch.setattr(p, "read_json", lambda path, *args: values[str(path)])
    monkeypatch.setattr(worker.proof, "same_rng", lambda a, b: True)
    monkeypatch.setitem(sys.modules, "cities_identity", SimpleNamespace(compare=lambda *_: pytest.fail("mismatch reached ordinary")))
    monkeypatch.setitem(sys.modules, "turn_speed_identity", SimpleNamespace(_raw_bundle_problems=lambda *_: pytest.fail("mismatch reached raw comparison")))
    output = tmp_path / "pair.json"
    assert worker.compare_roles(ROOT, "build", "left", "right", "ordinary-a", "ordinary-b", output) == 2
    value = p.strict_json(output.read_bytes())
    assert value["status"] == "REFUSED_NO_QUALIFICATION" and value["ordinary_comparison_reached"] is False
    assert value["proof_differences"][0]["component"] == "live"
    assert value["proof_differences"][-1]["first_recorded_field_segment_difference"]
    assert value["old_raw_live"] == [r["proof"]["old_raw_live"] for r in rows]


@pytest.mark.parametrize("mode", ["success_late_change", "write_failure_late_change", "write_failure_late_error"])
def test_final_rng_is_required_only_without_an_earlier_failure(mode, monkeypatch):
    failed_write = mode != "success_late_change"
    root, counts, rng, rc, save, original, clock = fake_capture(monkeypatch, fail_write=failed_write)
    calls = []
    late_index = 2 if failed_write else 3
    def observe(np):
        calls.append(len(calls) + 1)
        value = deepcopy(rng)
        if len(calls) == late_index:
            if mode == "write_failure_late_error":
                raise RuntimeError("fake late RNG observation")
            value["numpy"][4] = -0.0
        return value
    monkeypatch.setattr(old, "capture_rng", observe)
    progress = {}
    expected_error = OSError if failed_write else old.Refused
    with pytest.raises(expected_error) as error:
        cache.capture_terminal(save, "fake.ckpt", rc, (NativeBytes,), None, expected_rng=rng,
            bridge_class=Bridge, progress=progress, cpu=clock, wall=clock)
    assert counts == {"save": 1, "write": 1, "load": 0 if failed_write else 1}
    assert rc.write_checkpoint is original and len(calls) == late_index
    assert progress["extra_physics_runs"] == 0
    if failed_write:
        assert str(error.value) == "fake first write failure"
        assert progress["failure"] == {"type": "OSError", "message": "fake first write failure"}
    else:
        assert str(error.value) == "final proof RNG observation differs"
        assert progress["global_RNG_read_invariance"] is True
        assert "failure" not in progress
    if mode == "write_failure_late_error":
        assert progress["final_RNG_observation_error"] == {"type": "RuntimeError", "message": "fake late RNG observation"}
        assert "final_RNG_read_invariance" not in progress
    else:
        assert progress["final_RNG_read_invariance"] is False
        assert "final_RNG_observation_error" not in progress
