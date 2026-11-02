"""Source lineage checks, independent of candidate runtime parity."""
import hashlib
import json

import pytest

from scripts.testing.information_qualification_witness import ROOT, WITNESS, before_information_qualification


def test_information_qualification_projects_exact_reviewed_sources_and_rejects_mutations():
    witness = json.loads(WITNESS.read_text(encoding="utf-8"))
    assert witness["base"] == "03062059a2d61c911587d4e3d2ab797520fbcb74"
    assert witness["head"] == "a3faca1385d3a8d0eac0a51c0cbdd2e1f2f8ddd0"
    for path, row in witness["files"].items():
        source = (ROOT / path).read_bytes().decode("utf-8")
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
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == digest
