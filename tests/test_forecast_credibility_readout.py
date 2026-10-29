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


# Acceptance corrections below are appended to the preserved 73 reader cases.
# All reports/containers remain invented fixtures; no product code is invoked.
def _report_views(bundle, state, report_id="harvest:0:0:0"):
    sections = [snapshot["harvest_forecasts"] for snapshot in bundle["history"]]
    sections.append(state["harvest_forecasts"])
    return [row for section in sections for field in ("reports", "outcomes")
            for row in section[field] if row["id"] == report_id]


@pytest.mark.parametrize("field", ["brier", "observed_ratio", "outcome_shortfall"])
@pytest.mark.parametrize("omitted", [False, True])
def test_resolved_withheld_score_field_cannot_be_null_or_omitted(field, omitted):
    bundle, state = _trace(second=False, withheld=True)
    for row in _report_views(bundle, state):
        if row["status"] == "resolved":
            if omitted:
                row.pop(field)
            else:
                row[field] = None
    with pytest.raises(R.Refused, match="TRACE_SCORE_FIELDS|TRACE_GLOBAL_SCORE"):
        R.forecast_trace(bundle, state, withheld=True)


def test_resolved_withheld_cannot_drop_all_score_fields_to_avoid_denominator():
    bundle, state = _trace(second=False, withheld=True)
    for row in _report_views(bundle, state):
        if row["status"] == "resolved":
            row.update(brier=None, observed_ratio=None, outcome_shortfall=None)
    with pytest.raises(R.Refused, match="TRACE_GLOBAL_SCORE"):
        R.forecast_trace(bundle, state, withheld=True)


@pytest.mark.parametrize("field,value", [
    ("evaluation_count", 2), ("brier", float("nan")), ("brier", float("inf")),
    ("brier", -0.1), ("brier", 0.123), ("observed_ratio", float("inf")),
    ("observed_ratio", 0.25), ("outcome_shortfall", None), ("outcome_shortfall", 0),
])
def test_resolved_score_requires_complete_finite_source_arithmetic(field, value):
    bundle, state = _trace(second=False, withheld=True)
    for row in _report_views(bundle, state):
        if row["status"] == "resolved":
            row[field] = value
    with pytest.raises(R.Refused, match="TRACE_GLOBAL_SCORE"):
        R.forecast_trace(bundle, state, withheld=True)


@pytest.mark.parametrize("field,value", [
    ("evaluation_count", 3), ("brier", 0.0), ("observed_ratio", 0.0), ("outcome_shortfall", False),
])
def test_unscored_requires_incomplete_count_and_null_score_fields(field, value):
    bundle, state = _trace(second=False, withheld=True, missing_first=True)
    for row in _report_views(bundle, state):
        if row["status"] == "unscored":
            row[field] = value
    with pytest.raises(R.Refused, match="TRACE_UNSCORED_COMPLETE_WINDOW|TRACE_NONRESOLVED_SCORE"):
        R.forecast_trace(bundle, state, withheld=True)


def _cancelled_trace():
    bundle, state = _trace(second=False, withheld=True)
    # A declared copied fixture owner change at source turn9 precedes expiry.
    # Cancellation runs before this turn's observation, preserving count/sum.
    terminal = copy.deepcopy(bundle["history"][8]["harvest_forecasts"]["reports"][0])
    terminal.update(status="cancelled", resolved_turn=9)
    for snapshot in bundle["history"][9:]:
        snapshot["harvest_forecasts"].update(reports=[], outcomes=[copy.deepcopy(terminal)])
        snapshot["region_control"]["R0"] = "C1"
    for event in bundle["events_timeline"]:
        if event["event_id"] == "closure0":
            event["turn"] = 9
    state["civilizations"].append({"name": "C1"})
    state["regions"][0]["controller"] = "C1"
    state["harvest_forecasts"].update(reports=[], outcomes=[copy.deepcopy(terminal)], observers=[])
    return bundle, state


def test_cancelled_report_keeps_null_scores_and_original_evaluation_record():
    bundle, state = _cancelled_trace()
    result = R.forecast_trace(bundle, state, withheld=True)
    assert result["cancelled_reports"] == 1
    assert result["denominators"]["scored_reports"] == 0
    assert result["report_chains"][0]["brier"] is None


@pytest.mark.parametrize("field,value", [
    ("brier", 0.0), ("observed_ratio", 0.0), ("outcome_shortfall", False), ("resolved_turn", 12),
    ("evaluation_count", 1), ("evaluation_sum", 0.5),
])
def test_cancelled_score_and_pre_observation_closure_contract_is_required(field, value):
    bundle, state = _cancelled_trace()
    for row in _report_views(bundle, state):
        if row["status"] == "cancelled":
            row[field] = value
    with pytest.raises(R.Refused, match="TRACE_NONRESOLVED_SCORE|TRACE_TERMINAL_VIEW_DATE|TRACE_EXPIRY_CLOSURE|TRACE_TERMINAL_TRANSITION"):
        R.forecast_trace(bundle, state, withheld=True)


@pytest.mark.parametrize("gap", ["active_once", "active_forever", "terminal_once", "terminal_forever"])
def test_every_issued_id_persists_through_each_later_snapshot(gap):
    bundle, state = _trace(second=False, withheld=True)
    if gap == "active_once":
        affected = [bundle["history"][7]]  # returns in the next snapshot
    elif gap == "active_forever":
        affected = bundle["history"][6:]
    elif gap == "terminal_once":
        affected = [bundle["history"][14]]  # returns as an outcome next turn
    else:
        affected = bundle["history"][13:]
    for snapshot in affected:
        snapshot["harvest_forecasts"].update(reports=[], outcomes=[])
    if gap.endswith("forever"):
        state["harvest_forecasts"].update(reports=[], outcomes=[], observers=[])
    with pytest.raises(R.Refused, match="TRACE_REPORT_LIFECYCLE_COVERAGE"):
        R.forecast_trace(bundle, state, withheld=True)


@pytest.mark.parametrize("defect", ["active_twice", "outcome_twice", "both_collections", "terminal_in_active", "active_in_outcomes"])
def test_each_id_has_exactly_one_correct_active_or_terminal_collection(defect):
    bundle, state = _trace(second=False, withheld=True)
    if defect == "active_twice":
        section = bundle["history"][6]["harvest_forecasts"]
        section["reports"].append(copy.deepcopy(section["reports"][0]))
    elif defect == "outcome_twice":
        section = bundle["history"][12]["harvest_forecasts"]
        section["outcomes"].append(copy.deepcopy(section["outcomes"][0]))
    elif defect == "both_collections":
        section = bundle["history"][6]["harvest_forecasts"]
        section["outcomes"].append(copy.deepcopy(section["reports"][0]))
    elif defect == "terminal_in_active":
        section = bundle["history"][12]["harvest_forecasts"]
        section["reports"], section["outcomes"] = section["outcomes"], []
    else:
        section = bundle["history"][6]["harvest_forecasts"]
        section["outcomes"], section["reports"] = section["reports"], []
    with pytest.raises(R.Refused, match="TRACE_REPORT_ID|TRACE_REPORT_COLLECTION"):
        R.forecast_trace(bundle, state, withheld=True)


@pytest.mark.parametrize("defect", ["expired_active", "early_closure", "late_declared_closure"])
def test_expiry_closes_on_first_source_turn_after_window(defect):
    bundle, state = _trace(second=False, withheld=True)
    if defect == "expired_active":
        for snapshot in bundle["history"][12:]:
            section = snapshot["harvest_forecasts"]
            row = section["outcomes"].pop()
            row.update(status="withheld", resolved_turn=None, brier=None, observed_ratio=None, outcome_shortfall=None)
            section["reports"] = [row]
        state["harvest_forecasts"].update(reports=copy.deepcopy(bundle["history"][-1]["harvest_forecasts"]["reports"]), outcomes=[])
    elif defect == "early_closure":
        terminal = copy.deepcopy(bundle["history"][12]["harvest_forecasts"]["outcomes"][0])
        terminal["resolved_turn"] = 11
        bundle["history"][11]["harvest_forecasts"].update(reports=[], outcomes=[terminal])
    else:
        for row in _report_views(bundle, state):
            if row["status"] == "resolved":
                row["resolved_turn"] = 13
    with pytest.raises(R.Refused, match="TRACE_EXPIRED_ACTIVE_REPORT|TRACE_EXPIRY_CLOSURE|TRACE_TERMINAL_VIEW_DATE"):
        R.forecast_trace(bundle, state, withheld=True)


@pytest.mark.parametrize("exposure,expected", [
    ("zero", "OBSERVED_RECORDED_JOIN"), ("all_positive", "UNOBSERVED"), ("no_actions", "UNOBSERVED"),
])
def test_no_purchase_coverage_needs_an_actual_validated_zero_purchase_warning(exposure, expected):
    bundle, state = _trace(action=exposure != "no_actions")
    if exposure == "zero":
        row = bundle["history"][18]["harvest_forecasts"]["preparedness"][0]
        row.update(bought_during_warning=0.0, paid_during_warning=0)
        bundle["history"][18]["grain_reserves"]["flows"] = []
        bundle["events_timeline"] = [event for event in bundle["events_timeline"] if event["event_id"] != "payment"]
    result = R.forecast_trace(bundle, state)
    assert result["no_purchase_coverage"] == expected
    assert result["denominators"]["actions"] == (0 if exposure == "no_actions" else 1)


def test_zero_purchase_warning_is_observed_alongside_positive_warning_action():
    bundle, state = _trace()
    action = copy.deepcopy(bundle["history"][18]["harvest_forecasts"]["preparedness"][0])
    action.update(bought_during_warning=0.0, paid_during_warning=0)
    bundle["history"][19]["harvest_forecasts"]["preparedness"] = [action]
    bundle["history"][19]["grain_reserves"].update(granaries=[{"region": 0, "owner": 0, "target": 3.5}], flows=[])
    result = R.forecast_trace(bundle, state)
    assert result["no_purchase_coverage"] == "OBSERVED_RECORDED_JOIN"
    assert result["denominators"]["actions"] == 2
    assert result["recorded_warning_purchases"] == 0.25


def test_file_pin_accepts_only_atime_metadata_advancing_during_full_read(tmp_path, monkeypatch):
    path = tmp_path / "stable-body"
    body = b"complete-stable-body" * 37
    path.write_bytes(body)
    actual_stat, actual_fstat = Path.stat, R.os.fstat
    calls = []
    def atime_view(info):
        # Same complete stable fields/type at each observation. Only synthetic
        # atime advances; the old whole-stat comparison would reject this.
        calls.append(len(calls) + 1)
        values = {field: getattr(info, field) for field in ("st_dev", "st_ino", "st_mode", "st_nlink",
            "st_size", "st_mtime_ns", "st_ctime_ns")}
        values.update(st_atime=100.0 + len(calls), st_atime_ns=100_000_000_000 + len(calls))
        return SimpleNamespace(**values)
    def fake_stat(selected, *args, **kwargs):
        value = actual_stat(selected, *args, **kwargs)
        return atime_view(value) if selected == path else value
    with monkeypatch.context() as patch:
        patch.setattr(Path, "stat", fake_stat)
        patch.setattr(R.os, "fstat", lambda descriptor: atime_view(actual_fstat(descriptor)))
        result = R._file_pin(path, 4096)
    assert len(calls) == 4
    assert result == {"bytes": len(body), "sha256": hashlib.sha256(body).hexdigest()}
    assert path.read_bytes() == body and path.stat().st_nlink == 1


@pytest.mark.parametrize("defect", ["identity", "mtime", "content"])
def test_file_pin_still_rejects_actual_identity_mtime_or_content_mutation(tmp_path, monkeypatch, defect):
    path = tmp_path / "changing-body"
    body = b"original-retained-content"
    path.write_bytes(body)
    (tmp_path / "before-retained").write_bytes(body)
    actual_open = Path.open
    before = path.stat()
    mutated = []
    def change():
        mutated.append(True)
        if defect == "identity":
            replacement = tmp_path / "replacement"
            replacement.write_bytes(body)
            path.rename(tmp_path / "original-inode-retained")
            replacement.rename(path)
        elif defect == "mtime":
            R.os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns + 1_000_000_000))
        else:
            with actual_open(path, "r+b") as changed:
                changed.write(b"X")
            # Even restoring the original mtime cannot hide content/ctime drift.
            R.os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
    class MutatingRead:
        def __init__(self, stream):
            self.stream = stream
        def __enter__(self):
            self.stream.__enter__()
            return self
        def __exit__(self, *args):
            return self.stream.__exit__(*args)
        def fileno(self):
            return self.stream.fileno()
        def read(self, size):
            block = self.stream.read(size)
            if block and not mutated:
                change()
            return block
    def fake_open(selected, mode="r", *args, **kwargs):
        stream = actual_open(selected, mode, *args, **kwargs)
        return MutatingRead(stream) if selected == path and mode == "rb" else stream
    with monkeypatch.context() as patch:
        patch.setattr(Path, "open", fake_open)
        with pytest.raises(R.Refused, match="FILE_CHANGED"):
            R._file_pin(path, 4096)
    assert mutated == [True]
    assert (tmp_path / "before-retained").read_bytes() == body
    assert path.is_file() and path.stat().st_nlink == 1


# Source-only issue-event/catalog acceptance cases appended after all 183
# previously selected test bodies (120 reader + 63 study cases).
def _remove_report_everywhere(bundle, state, report_id):
    for snapshot in bundle["history"]:
        section = snapshot["harvest_forecasts"]
        for field in ("reports", "outcomes"):
            section[field] = [row for row in section[field] if row["id"] != report_id]
    for field in ("reports", "outcomes"):
        state["harvest_forecasts"][field] = [row for row in state["harvest_forecasts"][field] if row["id"] != report_id]
    for observer in state["harvest_forecasts"]["observers"]:
        observer["credibility_memory"] = [row for row in observer["credibility_memory"] if row["report_id"] != report_id]


def test_retained_issue_event_cannot_lose_every_snapshot_and_final_report_view():
    bundle, state = _trace(second=False, withheld=True)
    _remove_report_everywhere(bundle, state, "harvest:0:0:0")
    # Keep only the actual issue event to isolate reverse catalog completeness.
    bundle["events_timeline"] = [event for event in bundle["events_timeline"] if event["event_id"] == "issue0"]
    with pytest.raises(R.Refused, match="TRACE_ISSUE_EVENT_CATALOG"):
        R.forecast_trace(bundle, state, withheld=True)


@pytest.mark.parametrize("year", [0, 1])
@pytest.mark.parametrize("first_status", ["pending", "delivered", "terminal"])
def test_missing_initial_report_view_cannot_be_replaced_by_a_later_first_view(year, first_status):
    bundle, state = _trace(action=False)
    identifier, issue = f"harvest:{year}:0:0", year * 12 + 5
    first_turn = year * 12 + 12 if first_status == "terminal" else issue + 1
    initial = copy.deepcopy(next(row for row in bundle["history"][issue]["harvest_forecasts"]["reports"]
                                 if row["id"] == identifier))
    for snapshot in bundle["history"][issue:first_turn]:
        for field in ("reports", "outcomes"):
            snapshot["harvest_forecasts"][field] = [row for row in snapshot["harvest_forecasts"][field]
                                                   if row["id"] != identifier]
    if first_status == "pending":
        section = bundle["history"][first_turn]["harvest_forecasts"]
        section["reports"] = [initial if row["id"] == identifier else row for row in section["reports"]]
    with pytest.raises(R.Refused, match="TRACE_FIRST_REPORT_VIEW"):
        R.forecast_trace(bundle, state)


@pytest.mark.parametrize("defect", ["extra_event", "orphan_second_issue", "missing_issue_event"])
def test_issue_event_catalog_cardinality_is_closed_in_both_directions(defect):
    bundle, state = _trace(withheld=True)
    if defect == "extra_event":
        extra = copy.deepcopy(next(event for event in bundle["events_timeline"] if event["event_id"] == "issue0"))
        extra["event_id"] = "extra-unmatched-issue"
        bundle["events_timeline"].append(extra)
    elif defect == "orphan_second_issue":
        _remove_report_everywhere(bundle, state, "harvest:1:0:0")
        bundle["events_timeline"] = [event for event in bundle["events_timeline"] if event["event_id"] != "closure1"]
    else:
        bundle["events_timeline"] = [event for event in bundle["events_timeline"] if event["event_id"] != "issue0"]
    with pytest.raises(R.Refused, match="TRACE_ISSUE_EVENT_CATALOG"):
        R.forecast_trace(bundle, state, withheld=True)


@pytest.mark.parametrize("bad_id", [None, "", False, 0])
def test_issue_event_needs_a_nonempty_string_identity(bad_id):
    bundle, state = _trace(second=False, withheld=True)
    for event in bundle["events_timeline"]:
        if event["event_id"] == "issue0":
            event["event_id"] = bad_id
    with pytest.raises(R.Refused, match="TRACE_ISSUE_EVENT_ID"):
        R.forecast_trace(bundle, state, withheld=True)


def test_two_issue_events_cannot_share_one_event_identity():
    bundle, state = _trace(second=False, withheld=True)
    bundle["events_timeline"].append(copy.deepcopy(next(event for event in bundle["events_timeline"]
                                                      if event["event_id"] == "issue0")))
    with pytest.raises(R.Refused, match="TRACE_EVENT_ID"):
        R.forecast_trace(bundle, state, withheld=True)


def test_two_catalog_reports_cannot_share_one_issue_event():
    bundle, state = _trace(withheld=True)
    for row in _report_views(bundle, state, "harvest:1:0:0"):
        row["issued_event_id"] = "issue0"
    with pytest.raises(R.Refused, match="TRACE_ISSUE_EVENT_CATALOG"):
        R.forecast_trace(bundle, state, withheld=True)


def test_unrelated_timeline_event_is_not_a_forecast_issue_obligation():
    bundle, state = _trace(second=False, withheld=True)
    _remove_report_everywhere(bundle, state, "harvest:0:0:0")
    bundle["events_timeline"] = [{"event_id": "unrelated-event", "event_type": "unrelated_history",
                                 "turn": 5, "actors": ["C0"], "region": "R0", "causes": []}]
    result = R.forecast_trace(bundle, state, withheld=True)
    assert result["denominators"]["unique_reports"] == 0
    assert result["learning_use_coverage"] == "UNOBSERVED"


@pytest.mark.parametrize("field,value", [("evaluation_count", 1), ("evaluation_sum", 0.25)])
def test_freshly_issued_report_starts_with_zero_evaluation_count_and_sum(field, value):
    bundle, state = _trace(second=False, withheld=True)
    bundle["history"][5]["harvest_forecasts"]["reports"][0][field] = value
    with pytest.raises(R.Refused):
        R.forecast_trace(bundle, state, withheld=True)


def test_withheld_prewinter_evaluation_jump_cannot_masquerade_as_a_coherent_final_score():
    bundle, state = _trace(second=False, withheld=True)
    # All eventual arithmetic remains coherent; only the recorded chronology is
    # impossible. Source turn8 precedes the target window9/10/11.
    for snapshot in bundle["history"][8:12]:
        snapshot["harvest_forecasts"]["reports"][0].update(evaluation_count=3, evaluation_sum=3.0)
    with pytest.raises(R.Refused):
        R.forecast_trace(bundle, state, withheld=True)


def test_one_window_turn_cannot_advance_evaluation_count_twice():
    bundle, state = _trace(second=False, withheld=True)
    bundle["history"][9]["harvest_forecasts"]["reports"][0].update(evaluation_count=2, evaluation_sum=2.0)
    with pytest.raises(R.Refused):
        R.forecast_trace(bundle, state, withheld=True)


def test_prewindow_sum_drift_is_refused_even_when_count_stays_zero():
    bundle, state = _trace(second=False, withheld=True)
    bundle["history"][8]["harvest_forecasts"]["reports"][0]["evaluation_sum"] = 0.25
    with pytest.raises(R.Refused):
        R.forecast_trace(bundle, state, withheld=True)


def test_missing_ratio_turn_cannot_change_sum_without_count_increment():
    bundle, state = _trace(second=False, withheld=True, missing_first=True)
    bundle["history"][10]["harvest_forecasts"]["reports"][0]["evaluation_sum"] = 1.5
    with pytest.raises(R.Refused):
        R.forecast_trace(bundle, state, withheld=True)


def test_nonnegative_recorded_measurement_cannot_reduce_evaluation_sum():
    bundle, state = _trace(second=False, withheld=True)
    bundle["history"][10]["harvest_forecasts"]["reports"][0]["evaluation_sum"] = 0.5
    with pytest.raises(R.Refused):
        R.forecast_trace(bundle, state, withheld=True)


def test_available_dated_observation_must_match_that_turns_ordered_sum():
    bundle, state = _trace(second=False, first_ratios=(0.1, 0.2, 0.3))
    # Future observations, complete final memory and score are untouched. The
    # already retained source-turn9 ratio is 0.1, so 0.0 += 0.1 cannot be 0.125.
    bundle["history"][9]["harvest_forecasts"]["reports"][0]["evaluation_sum"] = 0.125
    with pytest.raises(R.Refused):
        R.forecast_trace(bundle, state)


@pytest.mark.parametrize("withheld", [False, True])
def test_missing_raw_ratio_legitimately_leaves_count_and_sum_unchanged(withheld):
    bundle, state = _trace(second=False, withheld=withheld, missing_first=True)
    before = bundle["history"][9]["harvest_forecasts"]["reports"][0]
    missing = bundle["history"][10]["harvest_forecasts"]["reports"][0]
    assert (before["evaluation_count"], before["evaluation_sum"]) == (missing["evaluation_count"], missing["evaluation_sum"])
    result = R.forecast_trace(bundle, state, withheld=withheld)
    assert result["incomplete_window_reports"] == 1
    assert result["denominators"]["scored_reports"] == 0
    assert result["raw_production_demand_recomputation"] is None


@pytest.mark.parametrize("withheld", [False, True])
def test_zero_ratio_legitimately_increments_count_without_increasing_sum(withheld):
    bundle, state = _trace(second=False, withheld=withheld, first_ratios=(0.0, 1.0, 0.0))
    initial = bundle["history"][8]["harvest_forecasts"]["reports"][0]
    zero = bundle["history"][9]["harvest_forecasts"]["reports"][0]
    assert zero["evaluation_count"] == initial["evaluation_count"] + 1
    assert zero["evaluation_sum"] == initial["evaluation_sum"]
    result = R.forecast_trace(bundle, state, withheld=withheld)
    assert result["denominators"]["scored_reports"] == 1
    assert result["raw_production_demand_recomputation"] is None


def test_cancellation_transfers_two_prior_measurements_without_measuring_its_own_turn():
    bundle, state = _trace(second=False, withheld=True)
    terminal = copy.deepcopy(bundle["history"][10]["harvest_forecasts"]["reports"][0])
    terminal.update(status="cancelled", resolved_turn=11)
    assert terminal["evaluation_count"] == 2 and terminal["evaluation_sum"] == 2.0
    for snapshot in bundle["history"][11:]:
        snapshot["harvest_forecasts"].update(reports=[], outcomes=[copy.deepcopy(terminal)])
        snapshot["region_control"]["R0"] = "C1"
    next(event for event in bundle["events_timeline"] if event["event_id"] == "closure0")["turn"] = 11
    state["civilizations"].append({"name": "C1"})
    state["regions"][0]["controller"] = "C1"
    state["harvest_forecasts"].update(reports=[], outcomes=[copy.deepcopy(terminal)], observers=[])
    result = R.forecast_trace(bundle, state, withheld=True)
    assert result["cancelled_reports"] == 1 and result["denominators"]["scored_reports"] == 0


@pytest.mark.parametrize("withheld", [False, True])
def test_expiry_resolution_transfers_complete_count_and_sum_unchanged(withheld):
    bundle, state = _trace(second=False, withheld=withheld)
    last_measurement = bundle["history"][11]["harvest_forecasts"]["reports"][0]
    resolved = bundle["history"][12]["harvest_forecasts"]["outcomes"][0]
    assert (resolved["evaluation_count"], resolved["evaluation_sum"]) == (
        last_measurement["evaluation_count"], last_measurement["evaluation_sum"])
    result = R.forecast_trace(bundle, state, withheld=withheld)
    assert result["denominators"]["scored_reports"] == 1
    assert result["raw_production_demand_recomputation"] is None
