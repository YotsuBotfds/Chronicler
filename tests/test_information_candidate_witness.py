"""Source lineage checks, independent of candidate runtime parity."""
import hashlib
import json

import pytest

from scripts.testing.frozen_sources import frozen_bytes, frozen_text
from scripts.testing.information_candidate_witness import WITNESS, before_information_candidate


def test_information_candidate_projects_exact_reviewed_sources_and_rejects_mutations():
    witness = json.loads(WITNESS.read_text(encoding="utf-8"))
    assert witness["base"] == "d7061f423b38b804ec9bc03dc32539bf6455400d"
    assert witness["head"] == "747edb9f7d833058cb55ccb5571b7702e6d215fe"
    from scripts.testing.scenarios_candidate_witness import before_scenarios_candidate
    for path, row in witness["files"].items():
        source = frozen_text(path)
        parent = before_information_candidate(source, path)
        assert hashlib.sha256(parent.encode()).hexdigest() == row["sha256"]
        assert before_information_candidate(parent, path, allow_parent=True) == parent
        with pytest.raises(AssertionError):
            before_information_candidate(parent, path)
        for changed in (source + "\n# unrelated mutation\n", source.replace("\n", "\r\n")):
            with pytest.raises(AssertionError):
                before_information_candidate(changed, path)
        source = before_scenarios_candidate(source, path, allow_parent=True)
        for patch in row["patches"]:
            assert source.count(patch["new"]) == 1
            for changed in (source.replace(patch["new"], patch["old"], 1),
                            source + patch["new"],
                            source.replace(patch["new"], patch["new"] + " ", 1)):
                with pytest.raises(AssertionError):
                    before_information_candidate(changed, path)
    for path, digest in witness["new_files"].items():
        assert hashlib.sha256(frozen_bytes(path)).hexdigest() == digest
