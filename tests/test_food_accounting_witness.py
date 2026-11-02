"""Frozen source projection checks; these do not establish runtime parity."""
import hashlib
import json

import pytest

from scripts.testing.food_accounting_witness import ROOT, WITNESS, before_food_accounting


def test_food_layer_projects_exact_source_and_rejects_mutations():
    witness = json.loads(WITNESS.read_text(encoding="utf-8"))
    assert witness["base"] == "6ff45ec33a86ff72b84d0d493fefcc3cd3a89601"
    assert witness["head"] == "5e5cc5ec2062b99270c26411b91a12c1b31b8ad5"
    for path, row in witness["files"].items():
        source = (ROOT / path).read_bytes().decode("utf-8")
        parent = before_food_accounting(source, path)
        assert hashlib.sha256(parent.encode()).hexdigest() == row["sha256"]
        assert before_food_accounting(parent, path, allow_parent=True) == parent
        with pytest.raises(AssertionError):
            before_food_accounting(parent, path)
        for changed in (source + "\n# unrelated mutation\n", source.replace("\n", "\r\n")):
            with pytest.raises(AssertionError):
                before_food_accounting(changed, path)
        for patch in row["patches"]:
            assert source.count(patch["new"]) == 1
            for changed in (source.replace(patch["new"], patch["old"], 1),
                            source + patch["new"],
                            source.replace(patch["new"], patch["new"] + " ", 1)):
                with pytest.raises(AssertionError):
                    before_food_accounting(changed, path)
    for path, digest in witness["new_files"].items():
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == digest
