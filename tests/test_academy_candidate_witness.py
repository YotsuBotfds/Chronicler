"""Source lineage checks, independent of candidate runtime parity."""
import hashlib
import json

import pytest

from scripts.testing.academy_candidate_witness import ROOT, WITNESS, before_academy_candidate


def test_academy_candidate_projects_exact_reviewed_sources_and_rejects_mutations():
    witness = json.loads(WITNESS.read_text(encoding="utf-8"))
    assert witness["base"] == "4dddb88b9dfc3625fc52628846ea218718410b95"
    assert witness["head"] == "f6277e0c36a77930c9feb8d45e6e0749cee79c73"
    for path, row in witness["files"].items():
        source = (ROOT / path).read_bytes().decode("utf-8")
        parent = before_academy_candidate(source, path)
        assert hashlib.sha256(parent.encode()).hexdigest() == row["sha256"]
        assert before_academy_candidate(parent, path, allow_parent=True) == parent
        with pytest.raises(AssertionError):
            before_academy_candidate(parent, path)
        for changed in (source + "\n# unrelated mutation\n", source.replace("\n", "\r\n")):
            with pytest.raises(AssertionError):
                before_academy_candidate(changed, path)
        for patch in row["patches"]:
            assert source.count(patch["new"]) == 1
            for changed in (source.replace(patch["new"], patch["old"], 1),
                            source + patch["new"],
                            source.replace(patch["new"], patch["new"] + " ", 1)):
                with pytest.raises(AssertionError):
                    before_academy_candidate(changed, path)
    for path, digest in witness["new_files"].items():
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == digest
