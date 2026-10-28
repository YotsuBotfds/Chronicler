"""Saved community counters diagnose capacity without changing an oracle."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json

import pytest

from chronicler import community_admissibility as ca
from chronicler.validation_communities import community_method_2_result


def _report(total=3, eligible=1, above=3):
    spec = {
        "status": "FAIL",
        "communities": total,
        "region_share": {
            "communities_above": above,
            "communities_in_regions_of_at_least": {
                "population": 100,
                "communities": eligible,
            },
        },
    }
    return {
        "results": {
            "community": community_method_2_result({"status": "PASS"}, spec),
        },
    }


def test_decomposes_saved_counters_without_changing_report_or_verdict():
    report = _report()
    before = deepcopy(report)
    result = ca.diagnose_report(report)
    assert report == before
    assert result["status"] == "assessed"
    assert result["original_community_status"] == "PASS"
    assert result["original_spec_status"] == "FAIL"
    assert result["minimum_region_population"] == 100
    assert result["observations"] == 3
    assert result["structurally_forced_region_share_failures"] == 2
    assert result["minimum_size_capacity_eligible_observations"] == 1
    assert result["region_share_failures_among_capacity_eligible_observations"] == 1
    assert result["observations_within_region_share_bound"] == 0
    assert result["global_community_count_band"] == [3.0, 15.0]


def test_capacity_does_not_imply_region_share_pass():
    result = ca.diagnose_report(_report(total=3, eligible=3, above=2))
    assert result["structurally_forced_region_share_failures"] == 0
    assert result["region_share_failures_among_capacity_eligible_observations"] == 2
    assert result["observations_within_region_share_bound"] == 1


def test_empty_exposure_never_becomes_a_pass():
    result = ca.diagnose_report(_report(total=0, eligible=0, above=0))
    assert result["status"] == "no_observations"
    assert result["fraction_structurally_forced_failures"] is None
    assert result["structural_constraint_observed"] is None


@pytest.mark.parametrize("report", [
    {},
    {"results": {}},
    {"results": {"community": {"status": "PASS"}}},
    {"results": {"community": {"method_version": 3}}},
    {"results": {"community": {
        "method_version": 2, "status": "PASS", "spec": {"status": "SKIP"},
    }}},
])
def test_missing_legacy_future_or_skipped_evidence_is_unavailable(report):
    assert ca.diagnose_report(report)["status"] == "unavailable"


@pytest.mark.parametrize("version", [True, 2.0, "2", -1])
def test_version_aliases_are_rejected(version):
    report = _report()
    report["results"]["community"]["method_version"] = version
    with pytest.raises(ValueError):
        ca.diagnose_report(report)


@pytest.mark.parametrize("field,value", [
    ("communities", True),
    ("communities", 3.0),
    ("communities", -1),
    ("communities_above", True),
    ("communities_above", 4),
    ("eligible", 4),
    ("eligible", "1"),
    ("population", 99),
])
def test_invalid_or_inconsistent_counters_fail_closed(field, value):
    report = _report()
    spec = report["results"]["community"]["spec"]
    if field == "communities":
        spec[field] = value
    elif field == "communities_above":
        spec["region_share"][field] = value
    else:
        key = "communities" if field == "eligible" else field
        spec["region_share"]["communities_in_regions_of_at_least"][key] = value
    with pytest.raises(ValueError):
        ca.diagnose_report(report)


def test_report_cannot_claim_fewer_failures_than_mathematically_forced():
    with pytest.raises(ValueError, match="structurally forced"):
        ca.diagnose_report(_report(total=3, eligible=0, above=2))


@pytest.mark.parametrize("report", [
    [],
    {"results": None},
    {"results": {"community": []}},
    {"results": {"community": {"method_version": 2, "status": "PASS", "spec": {}}}},
])
def test_malformed_known_structure_is_not_missing_evidence(report):
    with pytest.raises(ValueError):
        ca.diagnose_report(report)


def test_spec_pass_cannot_contradict_recorded_share_failures():
    report = _report()
    report["results"]["community"]["spec"]["status"] = "PASS"
    with pytest.raises(ValueError, match="contradicts"):
        ca.diagnose_report(report)


def test_cli_binds_output_to_exact_input_and_never_rewrites_it(tmp_path, capsys):
    path = tmp_path / "report.json"
    raw = json.dumps(_report()).encode()
    path.write_bytes(raw)
    assert ca.main([str(path)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["input_report_sha256"] == hashlib.sha256(raw).hexdigest()
    assert result["input_bytes"] == len(raw)
    assert path.read_bytes() == raw
    assert set(tmp_path.iterdir()) == {path}


@pytest.mark.parametrize("raw", [
    b'{"results": {}, "results": {}}',
    b'{"results": NaN}',
    b'{"results": 1e9999}',
])
def test_cli_rejects_ambiguous_json(tmp_path, raw):
    path = tmp_path / "report.json"
    path.write_bytes(raw)
    with pytest.raises(SystemExit) as error:
        ca.main([str(path)])
    assert error.value.code == 2
    assert path.read_bytes() == raw


def test_reader_enforces_bound_before_reading(tmp_path, monkeypatch):
    monkeypatch.setattr(ca, "MAX_REPORT_BYTES", 16)
    path = tmp_path / "report.json"
    path.write_bytes(b"x" * 17)
    with pytest.raises(ValueError, match="byte limit"):
        ca._read_regular_report(path)


def test_reader_refuses_directory(tmp_path):
    with pytest.raises((ValueError, OSError)):
        ca._read_regular_report(tmp_path)
