"""Source lineage checks, independent of candidate runtime parity."""
import hashlib
import json

import pytest

from scripts.testing.frozen_sources import frozen_bytes, frozen_text
from scripts.testing.restoration_candidate_witness import WITNESS, before_restoration_candidate


def test_restoration_candidate_projects_exact_reviewed_sources_and_rejects_mutations():
    witness = json.loads(WITNESS.read_text(encoding="utf-8"))
    assert witness["base"] == "a298a47b3b2beb9fdac69bc30860074d52226cdd"
    assert witness["head"] == "36a50a2378fb63250f9ce0c267b01242f3cb2724"
    from scripts.testing.information_qualification_witness import before_information_qualification
    for path, row in witness["files"].items():
        source = frozen_text(path)
        parent = before_restoration_candidate(source, path)
        assert hashlib.sha256(parent.encode()).hexdigest() == row["sha256"]
        assert before_restoration_candidate(parent, path, allow_parent=True) == parent
        with pytest.raises(AssertionError):
            before_restoration_candidate(parent, path)
        for changed in (source + "\n# unrelated mutation\n", source.replace("\n", "\r\n")):
            with pytest.raises(AssertionError):
                before_restoration_candidate(changed, path)
        source = before_information_qualification(source, path, allow_parent=True)
        for patch in row["patches"]:
            assert source.count(patch["new"]) == 1
            for changed in (source.replace(patch["new"], patch["old"], 1),
                            source + patch["new"],
                            source.replace(patch["new"], patch["new"] + " ", 1)):
                with pytest.raises(AssertionError):
                    before_restoration_candidate(changed, path)
    for path, digest in witness["new_files"].items():
        assert hashlib.sha256(frozen_bytes(path)).hexdigest() == digest
