"""Source lineage checks, independent of candidate runtime parity."""
import hashlib
import json

import pytest

from scripts.testing.crisis_candidate_witness import ROOT, WITNESS, before_crisis_candidate


def test_candidate_projects_exact_reviewed_sources_and_rejects_mutations():
    witness = json.loads(WITNESS.read_text(encoding="utf-8"))
    assert witness["base"] == "ecfa06aca86e1cfbe986f2f853c60d13a2a50723"
    assert witness["head"] == "ae3feb3bbadb60c82694634862b7b364b457d9a4"
    from scripts.testing.household_candidate_witness import before_household_candidate
    for path, row in witness["files"].items():
        source = (ROOT / path).read_bytes().decode("utf-8")
        parent = before_crisis_candidate(source, path)
        assert hashlib.sha256(parent.encode()).hexdigest() == row["sha256"]
        assert before_crisis_candidate(parent, path, allow_parent=True) == parent
        with pytest.raises(AssertionError):
            before_crisis_candidate(parent, path)
        for changed in (source + "\n# unrelated mutation\n", source.replace("\n", "\r\n")):
            with pytest.raises(AssertionError):
                before_crisis_candidate(changed, path)
        source = before_household_candidate(source, path, allow_parent=True)
        for patch in row["patches"]:
            assert source.count(patch["new"]) == 1
            for changed in (source.replace(patch["new"], patch["old"], 1),
                            source + patch["new"],
                            source.replace(patch["new"], patch["new"] + " ", 1)):
                with pytest.raises(AssertionError):
                    before_crisis_candidate(changed, path)
    # Files the candidate added are pinned whole. Later reviewed livelihoods layers
    # (tests/fixtures/livelihoods_*_source_inverse.json, e.g. rs2 in grain_storage.py)
    # are projected out first, exactly as for the edited files above; anything else
    # still changes the digest.
    from scripts.testing.livelihoods_sprint_witness import before_livelihoods_sprint
    for path, digest in witness["new_files"].items():
        source = (ROOT / path).read_bytes().decode("utf-8")
        assert hashlib.sha256(before_livelihoods_sprint(source, path).encode("utf-8")).hexdigest() == digest
        with pytest.raises(AssertionError):
            changed = before_livelihoods_sprint(source + "\n# unrelated mutation\n", path)
            assert hashlib.sha256(changed.encode("utf-8")).hexdigest() == digest
