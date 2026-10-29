"""Pure synthetic saved-artifact counterexamples; no product/native imports.

These fixtures are invented JSON/native-prefix containers. Passing them does
not qualify a World, real report exposure, native schema observation or CP load.
"""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import stat
from types import SimpleNamespace
import zlib

import pytest


@pytest.fixture
def tmp_path(tmp_path_factory, request):
    """Retained regular-only fixture namespace; avoid pytest current symlinks."""
    name = "forecast-" + hashlib.sha256(request.node.nodeid.encode()).hexdigest()
    return tmp_path_factory.mktemp(name, numbered=False)


_PATH = Path(__file__).resolve().parents[1] / "scripts/forecast_credibility_readout.py"
_SPEC = importlib.util.spec_from_file_location("_forecast_readout_test_subject", _PATH)
R = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(R)


def _write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, separators=(",", ":"), allow_nan=False))


def _fingerprint(text):
    value = 0xcbf29ce484222325
    for byte in text.encode():
        value = ((value ^ byte) * 0x100000001b3) & 0xffffffffffffffff
    return f"{value:016x}"


def _schemas():
    return {name: [1, _fingerprint(name + "{fake:u8,}"), name + "{fake:u8,}"] for name in R.KINDS}


def _native(kind, payload=b"invented-payload", fingerprint=None):
    name, number = next((name, number) for name, (key, number) in R.KINDS.items() if key == kind)
    fingerprint = _schemas()[name][1] if fingerprint is None else fingerprint
    return b"CHRNSTAT" + struct.pack("<IBQ", 1, number, int(fingerprint, 16)) + payload


def _checkpoint(path, *, header=None, sections=None):
    sections = [("python", b"invented-not-a-pickle"), *[("native." + key + ".0", _native(key))
        for key in ("agent", "ecology", "politics")]] if sections is None else sections
    descriptors, packed, offset = [], [], 0
    for name, body in sections:
        encoded = zlib.compress(body)
        descriptors.append({"name": name, "codec": "pickle5+zlib" if name == "python" else "native+zlib",
            "offset": offset, "length": len(encoded), "raw_length": len(body),
            "sha256": hashlib.sha256(encoded).hexdigest()})
        packed.append(encoded)
        offset += len(encoded)
    header = {"format": "chronicler-run-checkpoint", "version": 1, **(header or {}), "sections": descriptors}
    raw = json.dumps(header, separators=(",", ":")).encode()
    path.write_bytes(R.MAGIC + struct.pack("<I", len(raw)) + raw + b"".join(packed))
    return header


def _rewrite_checkpoint(path, mutate_header=None, mutate_body=None):
    raw = path.read_bytes()
    at = len(R.MAGIC)
    length = struct.unpack("<I", raw[at:at + 4])[0]
    header = json.loads(raw[at + 4:at + 4 + length])
    body = raw[at + 4 + length:]
    if mutate_header:
        mutate_header(header)
    if mutate_body:
        body = mutate_body(body)
    encoded = json.dumps(header, separators=(",", ":")).encode()
    path.write_bytes(R.MAGIC + struct.pack("<I", len(encoded)) + encoded + body)


def _bundle():
    return {"metadata": {"bundle_version": 6, "generated_at": "2026-10-29T00:00:00+00:00", "seed": 42,
            "total_turns": 26}, "history": [{"turn": turn} for turn in range(1, 27)],
            "world_state": {"turn": 26}, "events_timeline": [], "named_events": []}


def _ordinary(folder, *, bundle=None):
    folder.mkdir(parents=True, exist_ok=True)
    _write(folder / "state.json", {"turn": 26})
    _write(folder / "chronicle_bundle.json", _bundle() if bundle is None else bundle)
    (folder / "chronicle.md").write_text("invented ordinary output\n")
    return R.inventory(folder)


def _compare(left, right, **kwargs):
    return R.compare_roles(left, right, R.inventory(left), R.inventory(right), **kwargs)


def _trace(*, first_probability=0.8, first_ratios=(1.0, 1.0, 1.0), second=True, withheld=False,
           missing_first=False, action=True):
    history, events, latest, memories = [], [], [], []
    definitions = [(0, first_probability, first_ratios)]
    if second:
        definitions.append((1, 0.9, (0.5, 0.5, 0.5)))
    for year, probability, ratios in definitions:
        issue, delivery, closure = year * 12 + 5, year * 12 + 6, year * 12 + 12
        events.append({"event_id": f"issue{year}", "event_type": "harvest_forecast_issued", "turn": issue,
                       "region": "R0", "actors": ["C0"], "causes": []})
        if not withheld:
            events.append({"event_id": f"delivery{year}", "event_type": "harvest_forecast_delivered", "turn": delivery,
                           "region": "R0", "actors": ["C0"], "causes": [f"issue{year}"]})
        events.append({"event_id": f"closure{year}", "event_type": "harvest_forecast_resolved", "turn": closure,
                       "region": "R0", "actors": ["C0"], "causes": [f"issue{year}"] + ([] if withheld else [f"delivery{year}"])})
    for turn in range(26):
        reports, outcomes, preparation = [], [], []
        grain = {"source_turn": turn, "granaries": [], "flows": []}
        for year, probability, ratios in definitions:
            issue, delivery, end, closure = year * 12 + 5, year * 12 + 6, year * 12 + 11, year * 12 + 12
            if turn < issue:
                continue
            observations = [[year * 12 + 9 + offset, ratio] for offset, ratio in enumerate(ratios)
                if year * 12 + 9 + offset <= turn and not (missing_first and year == 0 and offset == 1)]
            total = 0.0
            for _, value in observations:
                total += value
            count = len(observations)
            status = "pending" if turn < delivery else "withheld" if withheld else "delivered"
            if turn >= closure:
                status = "resolved" if count == 3 else "unscored"
            row = {"id": f"harvest:{year}:0:0", "source_region": 0, "source_region_name": "R0",
                "recipient_region": 0, "recipient_region_name": "R0", "owner": 0, "owner_name": "C0",
                "issued_turn": issue, "delivery_turn": delivery, "expires_turn": end,
                "target_start": year * 12 + 9, "target_end": end, "probability": probability,
                "confidence": 0.75, "predicted_ratio": 0.4, "status": status,
                "delivered_turn": delivery if turn >= delivery and not withheld else None,
                "resolved_turn": closure if turn >= closure else None,
                "evaluation_count": count, "evaluation_sum": total, "issued_event_id": f"issue{year}",
                "delivered_event_id": f"delivery{year}" if turn >= delivery and not withheld else "",
                "observed_ratio": total / 3 if status == "resolved" else None,
                "outcome_shortfall": total / 3 < 0.6 if status == "resolved" else None,
                "brier": (probability - float(total / 3 < 0.6)) ** 2 if status == "resolved" else None}
            if observations and not withheld:
                row["credibility_observations"] = observations
            (outcomes if turn >= closure else reports).append(row)
        if turn == 18 and second and action and not withheld:
            prior = next(row for row in outcomes if row["id"] == "harvest:0:0:0")
            eligible = [] if prior["status"] != "resolved" else [prior]
            discount = (2.0 + sum(1.0 - row["brier"] for row in eligible)) / (2.0 + len(eligible))
            preparation.append({"region": 0, "region_name": "R0", "owner": 0, "owner_name": "C0",
                "forecast_id": "harvest:1:0:0", "preparation_policy": "local_credibility",
                "credibility_evidence_ids": [row["id"] for row in eligible], "credibility_discount": discount,
                "base_target": 3.0, "extra_target": 0.5, "bought_during_warning": 0.25, "paid_during_warning": 2})
            grain["granaries"] = [{"region": 0, "owner": 0, "target": 3.5}]
            grain["flows"] = [{"region": 0, "buyer": 0, "kind": "bought", "amount": 0.25, "cost": 2}]
            events.append({"event_id": "payment", "event_type": "harvest_preparedness", "turn": turn,
                "region": "R0", "actors": ["C0"], "causes": ["delivery1"]})
        history.append({"turn": turn + 1, "region_control": {"R0": "C0"}, "grain_reserves": grain,
            "harvest_forecasts": {"source_turn": turn, "reports": reports, "outcomes": outcomes,
                                  "preparedness": preparation}})
        latest = reports + outcomes
    for row in latest:
        if row["status"] == "resolved" and not withheld:
            evidence = {key: row[key] for key in ("issued_event_id", "delivered_event_id", "source_region",
                "recipient_region", "owner", "owner_name", "issued_turn", "delivered_turn", "resolved_turn",
                "probability", "observed_ratio", "outcome_shortfall", "brier")}
            evidence.update(report_id=row["id"], observations=row["credibility_observations"])
            memories.append(evidence)
    section = history[-1]["harvest_forecasts"]
    state = {"turn": 26, "regions": [{"name": "R" + str(i)} for i in range(8)], "civilizations": [{"name": "C0"}],
        "harvest_forecasts": {"preparation_policy": "local_credibility", "policy": "withhold" if withheld else "normal",
            "reports": copy.deepcopy(section["reports"]), "outcomes": copy.deepcopy(section["outcomes"]),
            "observers": [{"region": 0, "credibility_memory": memories}]}}
    bundle = _bundle()
    bundle.update(history=history, events_timeline=events)
    return bundle, state


@pytest.mark.parametrize("raw", [b'{"x":1,"x":2}', b'{"x":NaN}', b'{"x":1e999}'])
def test_json_refuses_duplicate_nonfinite_and_overflow(raw):
    with pytest.raises(R.Refused):
        R._json(raw, R.MAXIMA)


def test_json_tree_bound_is_closed():
    bounds = {**R.MAXIMA, "max_json_nodes": 2}
    with pytest.raises(R.Refused, match="JSON_TREE_BOUND"):
        R._json(b'[1,2]', bounds)


@pytest.mark.parametrize("bad", ["../x", "/x", "a//b", "a/./b", "a\\b"])
def test_unsafe_names_refused(bad):
    with pytest.raises(R.Refused):
        R._name(bad)


def test_inventory_requires_original_regular_unaliased_body(tmp_path, monkeypatch):
    original = tmp_path / "body"
    original.write_bytes(b"original")
    actual_lstat = Path.lstat
    def fake_lstat(path, *args, **kwargs):
        if path == original:
            return SimpleNamespace(st_mode=stat.S_IFLNK | 0o777)
        return actual_lstat(path, *args, **kwargs)
    with monkeypatch.context() as patch:
        patch.setattr(Path, "lstat", fake_lstat)
        with pytest.raises(R.Refused, match="INVENTORY_LINK"):
            R.inventory(tmp_path)
    assert original.is_file() and not original.is_symlink() and original.read_bytes() == b"original"


def test_inventory_refuses_hardlink_even_when_hash_matches(tmp_path, monkeypatch):
    original = tmp_path / "body"
    original.write_bytes(b"original")
    actual_stat = Path.stat
    def fake_stat(path, *args, **kwargs):
        info = actual_stat(path, *args, **kwargs)
        if path == original:
            return SimpleNamespace(st_mode=info.st_mode, st_nlink=2, st_size=info.st_size)
        return info
    with monkeypatch.context() as patch:
        patch.setattr(Path, "stat", fake_stat)
        with pytest.raises(R.Refused, match="FILE_BOUND"):
            R.inventory(tmp_path)
    assert original.stat().st_nlink == 1 and original.read_bytes() == b"original"


def test_inventory_total_bound_preserves_overflow_body(tmp_path):
    (tmp_path / "body").write_bytes(b"retained")
    with pytest.raises(R.Refused, match="INVENTORY_BYTES"):
        R.inventory(tmp_path, {**R.MAXIMA, "max_total_bytes": 3})
    assert (tmp_path / "body").read_bytes() == b"retained"


def test_complete_native_sections_hashed_without_unpickling(tmp_path):
    path = tmp_path / "fixture.ckpt"
    _checkpoint(path)
    result = R.checkpoint_summary(tmp_path, path.name)
    assert [row["name"] for row in result["native_sections"]] == ["native.agent.0", "native.ecology.0", "native.politics.0"]
    assert result["native_sections"][0]["sha256"] == hashlib.sha256(_native("agent")).hexdigest()
    assert result["python_unpickled"] is result["python_raw_length_verified"] is False
    assert result["native_sections"][2]["original_native_prefix"]["kind"] == 3


@pytest.mark.parametrize("position", ["first", "middle", "last"])
def test_native_comparison_hash_covers_entire_payload(tmp_path, position):
    payload = bytearray(b"a" * 1000)
    baseline = _native("agent", bytes(payload))
    at = {"first": 0, "middle": 500, "last": 999}[position]
    payload[at] = ord("b")
    _checkpoint(tmp_path / "left.ckpt", sections=[("python", b"opaque"), ("native.agent.0", baseline)])
    _checkpoint(tmp_path / "right.ckpt", sections=[("python", b"opaque"), ("native.agent.0", _native("agent", bytes(payload)))])
    a = R.checkpoint_summary(tmp_path, "left.ckpt")["native_sections"][0]
    b = R.checkpoint_summary(tmp_path, "right.ckpt")["native_sections"][0]
    assert a["bytes"] == b["bytes"] and a["sha256"] != b["sha256"]


@pytest.mark.parametrize("defect", ["digest", "offset", "raw_length", "codec", "duplicate", "sequence", "trailing", "truncated"])
def test_checkpoint_refuses_corrupt_original_containers(tmp_path, defect):
    path = tmp_path / "fixture.ckpt"
    _checkpoint(path)
    if defect == "trailing":
        path.write_bytes(path.read_bytes() + b"tail")
    elif defect == "truncated":
        path.write_bytes(path.read_bytes()[:-1])
    else:
        def mutate(header):
            row = header["sections"][1]
            if defect == "digest": row["sha256"] = "0" * 64
            elif defect == "offset": row["offset"] += 1
            elif defect == "raw_length": row["raw_length"] -= 1
            elif defect == "codec": row["codec"] = "pickle5+zlib"
            elif defect == "duplicate": row["name"] = "python"
            elif defect == "sequence": row["name"] = "native.agent.1"
        _rewrite_checkpoint(path, mutate_header=mutate)
    with pytest.raises(R.Refused):
        R.checkpoint_summary(tmp_path, path.name)


def test_checkpoint_refuses_concatenated_zlib_stream(tmp_path):
    path = tmp_path / "fixture.ckpt"
    header = _checkpoint(path, sections=[("python", b"opaque"), ("native.agent.0", _native("agent"))])
    raw = path.read_bytes()
    packed = zlib.compress(_native("agent")) + zlib.compress(b"concealed")
    def mutate(value):
        value["sections"][1]["length"] = len(packed)
        value["sections"][1]["sha256"] = hashlib.sha256(packed).hexdigest()
    python_size = header["sections"][0]["length"]
    _rewrite_checkpoint(path, mutate_header=mutate, mutate_body=lambda body: body[:python_size] + packed)
    with pytest.raises(R.Refused, match="CP_NATIVE_STREAM_BOUND"):
        R.checkpoint_summary(tmp_path, path.name)


@pytest.mark.parametrize("defect", ["magic", "kind", "version"])
def test_checkpoint_refuses_native_prefix_mislabel(tmp_path, defect):
    native = bytearray(_native("agent"))
    native[{"magic": 0, "version": 8, "kind": 12}[defect]] ^= 1
    _checkpoint(tmp_path / "fixture.ckpt", sections=[("python", b"opaque"), ("native.agent.0", bytes(native))])
    with pytest.raises(R.Refused):
        R.checkpoint_summary(tmp_path, "fixture.ckpt")


def test_python_declared_raw_length_is_not_claimed_independently_verified(tmp_path):
    path = tmp_path / "fixture.ckpt"
    _checkpoint(path)
    _rewrite_checkpoint(path, mutate_header=lambda h: h["sections"][0].update(raw_length=900))
    result = R.checkpoint_summary(tmp_path, path.name)
    assert result["python_raw_length_verified"] is False


@pytest.mark.parametrize("defect", ["missing_kind", "fingerprint", "bool_version", "descriptor"])
def test_full_schema_tuple_metadata_is_checked_without_native_import(defect):
    schemas = _schemas()
    if defect == "missing_kind": del schemas["EcologySimulator"]
    elif defect == "fingerprint": schemas["AgentSimulator"][1] = "0" * 16
    elif defect == "bool_version": schemas["AgentSimulator"][0] = True
    elif defect == "descriptor": schemas["AgentSimulator"][2] += "changed"
    with pytest.raises(R.Refused):
        R.schema_layouts(schemas)


def test_schema_layout_reference_uses_saved_full_descriptor():
    schemas = _schemas()
    assert R.schema_layouts(schemas)["agent"] == "v1:" + schemas["AgentSimulator"][1]


def test_bundle_decode_preserves_complete_history_key_order_and_zero_sign():
    encoded = _bundle()
    encoded.pop("history")
    encoded["history_delta"] = [{"turn": 1, "data": {"b": -0.0, "a": [1, 2]}}]
    encoded["history_delta"].extend({"turn": turn} for turn in range(2, 27))
    encoded["world_state"].update(events_timeline=None, named_events=None)
    decoded = R.decode_bundle(encoded, R.MAXIMA)
    assert len(decoded["history"]) == 26
    assert list(decoded["history"][-1]["data"]) == ["b", "a"]
    assert struct.pack(">d", decoded["history"][-1]["data"]["b"]) == struct.pack(">d", -0.0)
    assert decoded["world_state"]["events_timeline"] == []
    decoded["history"][0]["data"]["a"].append(3)
    assert decoded["history"][1]["data"]["a"] == [1, 2]


@pytest.mark.parametrize("defect", ["short", "duplicate_turn", "bad_patch", "ambiguous"])
def test_bundle_refuses_missing_or_malformed_historical_coverage(defect):
    bundle = _bundle()
    if defect == "short": bundle["history"].pop()
    elif defect == "duplicate_turn": bundle["history"][-1]["turn"] = 25
    elif defect == "bad_patch":
        bundle.pop("history")
        bundle["history_delta"] = [{"turn": 1}, {"~l": []}]
    elif defect == "ambiguous": bundle["history_delta"] = []
    with pytest.raises(R.Refused):
        R.decode_bundle(bundle, R.MAXIMA)


def test_only_generated_at_is_normalized(tmp_path):
    left, right = tmp_path / "left", tmp_path / "right"
    _ordinary(left)
    changed = _bundle()
    changed["metadata"]["generated_at"] = "2026-10-29T01:00:00+00:00"
    _ordinary(right, bundle=changed)
    assert _compare(left, right)["equal"] is True
    changed["metadata"]["source"] = "different-provenance"
    _write(right / "chronicle_bundle.json", changed)
    assert _compare(left, right)["equal"] is False


@pytest.mark.parametrize("value", [0.0, 1, {"a": 1, "b": 2}])
def test_bundle_comparison_preserves_float_type_sign_and_key_order(tmp_path, value):
    left, right = tmp_path / "left", tmp_path / "right"
    a, b = _bundle(), _bundle()
    original = -0.0 if type(value) is float else 1.0 if type(value) is int else {"b": 2, "a": 1}
    a["history"][0]["witness"], b["history"][0]["witness"] = original, value
    _ordinary(left, bundle=a)
    _ordinary(right, bundle=b)
    assert _compare(left, right)["equal"] is False


def test_cp10_missing_source_turn10_sidecar_is_negative(tmp_path):
    left, right = tmp_path / "left", tmp_path / "right"
    _ordinary(left)
    _ordinary(right)
    _write(left / "validation_summary/economy_turn_010.json", {"source_turn": 10})
    result = _compare(left, right, split_turn=10)
    assert result["equal"] is False
    assert result["allowed_pre_split_source_clock_json_omissions"] == []


def test_only_registered_pre_split_source_clock_sidecar_can_be_absent(tmp_path):
    left, right = tmp_path / "left", tmp_path / "right"
    _ordinary(left)
    _ordinary(right)
    _write(left / "validation_summary/economy_turn_009.json", {"source_turn": 9})
    result = _compare(left, right, split_turn=10)
    assert result["equal"] is True
    assert result["allowed_pre_split_source_clock_json_omissions"] == ["validation_summary/economy_turn_009.json"]


def test_retained_columnar_prefix_never_suffix_filtered(tmp_path):
    left, right = tmp_path / "left", tmp_path / "right"
    _ordinary(left)
    _ordinary(right)
    (left / "validation_reserve_ledger.arrow").write_bytes(b"complete-prefix-and-suffix")
    (right / "validation_reserve_ledger.arrow").write_bytes(b"suffix")
    assert _compare(left, right, split_turn=10)["equal"] is False


def test_empty_natural_exposure_stays_explicitly_unobserved():
    bundle, state = _trace(second=False, action=False)
    for snapshot in bundle["history"]:
        snapshot["harvest_forecasts"].update(reports=[], outcomes=[])
    bundle["events_timeline"] = []
    state["harvest_forecasts"].update(reports=[], outcomes=[], observers=[])
    result = R.forecast_trace(bundle, state)
    assert result["denominators"]["unique_reports"] == 0
    assert result["learning_use_coverage"] == result["false_alarm_coverage"] == "UNOBSERVED"
    assert result["raw_production_demand_recomputation"] is None


def test_false_alarm_result_to_later_warning_uses_exact_earlier_ids():
    bundle, state = _trace()
    result = R.forecast_trace(bundle, state)
    assert result["denominators"]["unique_reports"] == 2
    assert result["denominators"]["false_alarms"] == 1
    assert result["preparation_actions"][0]["evidence_ids"] == ["harvest:0:0:0"]
    assert result["preparation_actions"][0]["payment_event_ids"] == ["payment"]
    assert result["recorded_warning_payments"] == 2
    assert len(result["report_chains"][0]["float_witnesses"]["brier"]["binary64_hex"]) == 16


def test_missed_warning_can_become_local_memory_without_warning_action():
    bundle, state = _trace(first_probability=0.3, first_ratios=(0.1, 0.2, 0.3), second=False)
    result = R.forecast_trace(bundle, state)
    assert result["denominators"]["missed_warnings"] == 1
    assert result["denominators"]["local_memory_results"] == 1
    assert result["denominators"]["actions"] == 0


def test_incomplete_raw_window_is_unscored_and_not_local_knowledge():
    bundle, state = _trace(second=False, missing_first=True)
    result = R.forecast_trace(bundle, state)
    assert result["incomplete_window_reports"] == 1
    assert result["denominators"]["local_memory_results"] == 0


def test_withheld_global_score_is_not_local_exposure():
    bundle, state = _trace(withheld=True)
    result = R.forecast_trace(bundle, state, withheld=True)
    assert result["denominators"]["scored_reports"] == result["withheld_report_exposure"] == 2
    assert result["denominators"]["delivered_reports"] == result["denominators"]["local_memory_results"] == 0
    assert result["preparation_actions"] == []


@pytest.mark.parametrize("defect", ["future_observation", "rewritten_probability", "missing_delivery_event",
    "missing_resolution_event", "wrong_owner", "wrong_evidence", "future_evidence", "wrong_discount",
    "wrong_target", "negative_payment", "wrong_buyer", "missing_payment_event", "repeated_report"])
def test_mechanical_report_receipt_corruption_is_refused(defect):
    bundle, state = _trace()
    if defect == "future_observation":
        bundle["history"][9]["harvest_forecasts"]["reports"][0]["credibility_observations"][0][0] = 11
    elif defect == "rewritten_probability":
        bundle["history"][7]["harvest_forecasts"]["reports"][0]["probability"] = 0.1
    elif defect == "missing_delivery_event": bundle["events_timeline"] = [e for e in bundle["events_timeline"] if e["event_id"] != "delivery0"]
    elif defect == "missing_resolution_event": bundle["events_timeline"] = [e for e in bundle["events_timeline"] if e["event_id"] != "closure0"]
    elif defect == "wrong_owner": state["harvest_forecasts"]["observers"][0]["credibility_memory"][0]["owner_name"] = "C1"
    elif defect == "future_evidence": state["harvest_forecasts"]["observers"][0]["credibility_memory"][0]["resolved_turn"] = 20
    elif defect == "wrong_evidence": bundle["history"][18]["harvest_forecasts"]["preparedness"][0]["credibility_evidence_ids"] = []
    elif defect == "wrong_discount": bundle["history"][18]["harvest_forecasts"]["preparedness"][0]["credibility_discount"] = 1.0
    elif defect == "wrong_target": bundle["history"][18]["grain_reserves"]["granaries"][0]["target"] = 4.0
    elif defect == "negative_payment": bundle["history"][18]["harvest_forecasts"]["preparedness"][0]["paid_during_warning"] = -1
    elif defect == "wrong_buyer": bundle["history"][18]["grain_reserves"]["flows"][0]["buyer"] = 1
    elif defect == "missing_payment_event": bundle["events_timeline"] = [e for e in bundle["events_timeline"] if e["event_id"] != "payment"]
    elif defect == "repeated_report": bundle["history"][5]["harvest_forecasts"]["reports"] *= 2
    with pytest.raises(R.Refused):
        R.forecast_trace(bundle, state)


def _study(root):
    candidate = {"source": "a" * 40, "package_digest": "b" * 64, "runner_sha256": "c" * 64,
        "pyproject_sha256": "d" * 64, "lock_sha256": "e" * 64}
    baseline = {"source": R.BASELINE, "package_digest": R.BASELINE_PACKAGE,
        "pyproject_sha256": "d" * 64, "lock_sha256": "e" * 64}
    binding = {"candidate": candidate, "baseline": baseline,
        "candidate_ci": {"source": candidate["source"], "run_id": 1, "attempt": 1, "conclusion": "success",
            "root_receipt_sha256": "f" * 64, "independent_receipt_sha256": "1" * 64},
        "native": {"sha256": R.NATIVE_SHA256, "bytes": R.NATIVE_BYTES,
            "crate": "04866c3962ec9d5c77477fc727107a553fc1d6df"}}
    schemas = _schemas()
    layouts = R.schema_layouts(schemas)
    environment = {"python": "3.13.17", "implementation": "CPython", "machine": "x86_64",
        "affinity_cpu_count": 1, "thread_env": {"PYTHONHASHSEED": "0"}, "packages": {"fake": "1"}}
    def identity(source):
        return {"source": {"git_sha": source["source"], "package_digest": source["package_digest"]},
                "native": {"status": "found", "sha256": R.NATIVE_SHA256, "bytes": R.NATIVE_BYTES},
                "environment": copy.deepcopy(environment)}
    _write(root / "admission.json", {"actual_Worlds": 0, "schemas": schemas, "identity": identity(candidate)})
    registration = {"schema_version": 1, "seed": 42, "horizon": 26, "binding": binding,
        "bootstrap_schemas": schemas, "roles": [], "comparisons": [], "checkpoint_comparisons": []}
    records = {}
    for name in R.ROLE_NAMES:
        source = baseline if name in ("legacy-default", "legacy-fixed") else candidate
        start = int(name[6:]) if name.startswith("exact-") else 4 if name in ("local-normal", "local-withheld") else 0
        kind = "exact" if name.startswith("exact-") else "fork" if name in ("local-normal", "local-withheld") else "plain"
        role = {"name": name, "directory": "roles/" + name + "/ordinary", "source": source["source"],
                "package_digest": source["package_digest"], "native_sha256": R.NATIVE_SHA256,
                "start_turn": start, "turns": 26, "kind": kind, "checkpoint_turns": R.CHECKPOINT_TURNS[name]}
        registration["roles"].append(role)
        folder = root / role["directory"]
        folder.mkdir(parents=True)
        bundle, state = _trace(second=False, action=False, withheld=name == "local-withheld")
        for snapshot in bundle["history"]:
            snapshot["harvest_forecasts"].update(reports=[], outcomes=[])
        bundle["events_timeline"] = []
        state["harvest_forecasts"].update(reports=[], outcomes=[], observers=[])
        if kind == "fork":
            bundle["metadata"]["resume"] = {"kind": "experiment-fork", "exact": False, "turn": 4}
        _ordinary(folder, bundle=bundle)
        _write(folder / "state.json", state)
        observed = identity(source)
        for turn in role["checkpoint_turns"]:
            lineage = []
            if name.startswith("exact-"):
                lineage.append({"resumed_at": 4, "kind": "checkpoint", "exact": True})
                if name != "exact-4":
                    lineage.append({"resumed_at": start, "kind": "checkpoint", "exact": True})
            cp_identity = copy.deepcopy(observed)
            cp_identity["native"]["state_layouts"] = layouts
            cp_identity["environment"]["hash_seed"] = "0"
            _checkpoint(folder / f"checkpoint_turn_{turn}.ckpt", header={"exact": True, "seed": 42, "turn": turn,
                "num_turns": 26, "start_turn": 0, "identity": cp_identity,
                "flags": {"harvest_forecasts": True, "grain_reserves": True, "contact_ledger": True,
                    "health_care": False, "ritual_gatherings": False, "scientific_claims": False},
                "run_config": {"resume_info": None, "lineage": lineage}, "lineage": lineage})
        normal_runner = name in ("local-parent", "local-normal", "local-withheld", "local-reference")
        runner = candidate["runner_sha256"] if normal_runner else "2" * 64
        _write(folder.parent / "worker_identity.json", {"schema_version": 2, "environment_stable": True,
            "identities_stable": True, "runner_sha256": runner, "runner_sha256_after": runner,
            "before": observed, "after": observed})
        records[name] = {"status": "complete", "returncode": 0, "completed_horizon": 26,
            "start_turn": start, "observed_ticks": 26 - start, "identity": observed, "schemas": schemas,
            "worker_identity_path": f"roles/{name}/worker_identity.json", "runner_sha256": runner,
            "entrypoint": "normal_runner_job" if normal_runner else "stock_cli", "inventory": R.inventory(folder)}
    for index, (left, right, split, state_only) in enumerate(R.ORDINARY_PAIRS):
        registration["comparisons"].append({"name": f"fake-{index}", "left": left, "right": right,
            "split_turn": split, "state_only": state_only, "compare_bundle": not state_only})
    for turn in (4, 6, 8, 10, 13):
        registration["checkpoint_comparisons"].append({"name": f"fake-native-{turn}",
            "left_role": "local-reference", "left_path": "checkpoint_turn_26.ckpt",
            "right_role": "exact-" + str(turn), "right_path": "checkpoint_turn_26.ckpt", "turn": 26,
            "expected_header": {"seed": 42, "num_turns": 26}})
    return registration, records


def test_fixed_fourteen_role_fake_readout_requires_originals_and_preserves_null_gates(tmp_path):
    registration, records = _study(tmp_path)
    result = R.read_study(tmp_path, registration, records)
    assert result["complete"] is True
    assert result["actual_roles"] == 14 and result["actual_physics_ticks"] == 315
    assert len(result["ordinary_comparisons"]) == 10 and len(result["native_checkpoint_comparisons"]) == 5
    assert result["retained_bootstrap_metadata"]["descriptor_fingerprints_recomputed"] is True
    assert result["bootstrap_full_descriptor_independent_verification"] is None
    assert result["full_graph_equivalence"] is result["global_rng_equivalence"] is None


@pytest.mark.parametrize("defect", ["pruned_comparison", "partial_role", "wrong_source", "unqualified_ci",
    "missing_checkpoint_body", "metadata_only_schema", "raw_native_layout", "runner_mismatch"])
def test_full_fake_study_refuses_missing_or_misbound_evidence(tmp_path, defect):
    registration, records = _study(tmp_path)
    if defect == "pruned_comparison": registration["comparisons"].pop()
    elif defect == "partial_role": records["exact-13"]["status"] = "failed"
    elif defect == "wrong_source": registration["roles"][-1]["source"] = R.BASELINE
    elif defect == "unqualified_ci": registration["binding"]["candidate_ci"]["root_receipt_sha256"] = None
    elif defect == "missing_checkpoint_body":
        (tmp_path / "roles/exact-13/ordinary/checkpoint_turn_26.ckpt").rename(tmp_path / "retained-invented-checkpoint-body.ckpt")
        records["exact-13"]["inventory"].pop("checkpoint_turn_26.ckpt")
    elif defect == "metadata_only_schema": records["exact-13"]["schemas"] = {"AgentSimulator": [1, "a", "name-only"]}
    elif defect == "runner_mismatch": records["local-parent"]["runner_sha256"] = "4" * 64
    elif defect == "raw_native_layout":
        path = tmp_path / "roles/exact-13/ordinary/checkpoint_turn_26.ckpt"
        old = R.checkpoint_summary(path.parent, path.name)["header"]
        _checkpoint(path, header={key: value for key, value in old.items() if key != "sections"}, sections=[("python", b"opaque"),
            ("native.agent.0", _native("agent", fingerprint="0" * 16)),
            ("native.ecology.0", _native("ecology")), ("native.politics.0", _native("politics"))])
        records["exact-13"]["inventory"] = R.inventory(path.parent)
    with pytest.raises(R.Refused):
        R.read_study(tmp_path, registration, records)
