"""Source lineage checks, independent of candidate runtime parity."""
import hashlib
import json

import pytest

from scripts.testing.scenarios_candidate_witness import ROOT, WITNESS, before_scenarios_candidate


def test_scenarios_candidate_projects_exact_reviewed_sources_and_rejects_mutations():
    witness = json.loads(WITNESS.read_text(encoding="utf-8"))
    assert witness["base"] == "3e852333bcfc6b1e8a33c153ab8a9b8879b979ac"
    assert witness["head"] == "c4fa8afcf8bc783e488fa168d91c121db3de6b0e"
    from scripts.testing.restoration_candidate_witness import before_restoration_candidate
    for path, row in witness["files"].items():
        source = (ROOT / path).read_bytes().decode("utf-8")
        parent = before_scenarios_candidate(source, path)
        assert hashlib.sha256(parent.encode()).hexdigest() == row["sha256"]
        assert before_scenarios_candidate(parent, path, allow_parent=True) == parent
        with pytest.raises(AssertionError):
            before_scenarios_candidate(parent, path)
        for changed in (source + "\n# unrelated mutation\n", source.replace("\n", "\r\n")):
            with pytest.raises(AssertionError):
                before_scenarios_candidate(changed, path)
        source = before_restoration_candidate(source, path, allow_parent=True)
        for patch in row["patches"]:
            assert source.count(patch["new"]) == 1
            for changed in (source.replace(patch["new"], patch["old"], 1),
                            source + patch["new"],
                            source.replace(patch["new"], patch["new"] + " ", 1)):
                with pytest.raises(AssertionError):
                    before_scenarios_candidate(changed, path)
    for path, digest in witness["new_files"].items():
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == digest
