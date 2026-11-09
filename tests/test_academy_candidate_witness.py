"""Source lineage checks, independent of candidate runtime parity."""
import hashlib
import json

import pytest

from scripts.testing.frozen_sources import frozen_bytes, frozen_text
from scripts.testing.academy_candidate_witness import WITNESS, before_academy_candidate


def test_academy_candidate_projects_exact_reviewed_sources_and_rejects_mutations():
    witness = json.loads(WITNESS.read_text(encoding="utf-8"))
    assert witness["base"] == "4dddb88b9dfc3625fc52628846ea218718410b95"
    assert witness["head"] == "6768fc5d236e03d3da98fb10b40e07c6d6d6c2ae"
    from scripts.testing.information_candidate_witness import before_information_candidate
    for path, row in witness["files"].items():
        source = frozen_text(path)
        parent = before_academy_candidate(source, path)
        assert hashlib.sha256(parent.encode()).hexdigest() == row["sha256"]
        assert before_academy_candidate(parent, path, allow_parent=True) == parent
        with pytest.raises(AssertionError):
            before_academy_candidate(parent, path)
        for changed in (source + "\n# unrelated mutation\n", source.replace("\n", "\r\n")):
            with pytest.raises(AssertionError):
                before_academy_candidate(changed, path)
        source = before_information_candidate(source, path, allow_parent=True)
        for patch in row["patches"]:
            assert source.count(patch["new"]) == 1
            for changed in (source.replace(patch["new"], patch["old"], 1),
                            source + patch["new"],
                            source.replace(patch["new"], patch["new"] + " ", 1)):
                with pytest.raises(AssertionError):
                    before_academy_candidate(changed, path)
    for path, digest in witness["new_files"].items():
        assert hashlib.sha256(frozen_bytes(path)).hexdigest() == digest
