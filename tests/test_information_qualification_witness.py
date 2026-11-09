"""Source lineage checks, independent of candidate runtime parity."""
import hashlib
import json

import pytest

from scripts.testing.frozen_sources import frozen_text
from scripts.testing.information_qualification_witness import (
    WITNESS, WALKTHROUGH_WITNESS,
    before_forecast_walkthrough, before_information_qualification,
)


def test_information_qualification_projects_exact_reviewed_sources_and_rejects_mutations():
    witness = json.loads(WITNESS.read_text(encoding="utf-8"))
    assert witness["base"] == "03062059a2d61c911587d4e3d2ab797520fbcb74"
    assert witness["head"] == "a3faca1385d3a8d0eac0a51c0cbdd2e1f2f8ddd0"
    for path, row in witness["files"].items():
        source = frozen_text(path)
        parent = before_information_qualification(source, path)
        assert hashlib.sha256(parent.encode()).hexdigest() == row["sha256"]
        assert before_information_qualification(parent, path, allow_parent=True) == parent
        with pytest.raises(AssertionError):
            before_information_qualification(parent, path)
        for changed in (source + "\n# unrelated mutation\n", source.replace("\n", "\r\n")):
            with pytest.raises(AssertionError):
                before_information_qualification(changed, path)
        for patch in row["patches"]:
            assert source.count(patch["new"]) == 1
            for changed in (source.replace(patch["new"], patch["old"], 1),
                            source + patch["new"],
                            source.replace(patch["new"], patch["new"] + " ", 1)):
                with pytest.raises(AssertionError):
                    before_information_qualification(changed, path)
    for path, digest in witness["new_files"].items():
        source = frozen_text(path)
        historical = before_forecast_walkthrough(source, path)
        assert hashlib.sha256(historical.encode("utf-8")).hexdigest() == digest


def test_forecast_walkthrough_projection_preserves_frozen_helper_and_rejects_mutations():
    witness = json.loads(WALKTHROUGH_WITNESS.read_text(encoding="utf-8"))
    assert witness["base"] == "63581a9a1a1297396ce2227ac2683aeefd5ad8a3"
    assert witness["head"] == "448d4bcbdf4ab6ac561352c440b0c20c7dce1764"
    assert set(witness["files"]) == {
        "scripts/crisis_forecast_misleading_example.py",
        "tests/test_crisis_forecast_misleading_example.py",
    }
    historical = json.loads(WITNESS.read_text(encoding="utf-8"))
    helper = "scripts/crisis_forecast_misleading_example.py"
    assert witness["files"][helper]["sha256"] == historical["new_files"][helper]
    for path, row in witness["files"].items():
        source = frozen_text(path)
        parent = before_forecast_walkthrough(source, path)
        assert hashlib.sha256(parent.encode("utf-8")).hexdigest() == row["sha256"]
        assert before_forecast_walkthrough(parent, path, allow_parent=True) == parent
        with pytest.raises(AssertionError):
            before_forecast_walkthrough(parent, path)
        for changed in (source + "\n# unrelated mutation\n", source.replace("\n", "\r\n")):
            with pytest.raises(AssertionError):
                before_forecast_walkthrough(changed, path)
        for patch in row["patches"]:
            assert source.count(patch["new"]) == 1
            for changed in (source.replace(patch["new"], patch["old"], 1),
                            source + patch["new"],
                            source.replace(patch["new"], patch["new"] + " ", 1)):
                with pytest.raises(AssertionError):
                    before_forecast_walkthrough(changed, path)
