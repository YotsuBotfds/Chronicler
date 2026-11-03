"""Source lineage checks, independent of candidate runtime parity."""
import hashlib
import json

import pytest

from scripts.testing.scenarios_candidate_witness import ROOT, WITNESS, before_scenarios_candidate


def test_scenarios_candidate_projects_exact_reviewed_sources_and_rejects_mutations():
    witness = json.loads(WITNESS.read_text(encoding="utf-8"))
    assert witness["base"] == "3e852333bcfc6b1e8a33c153ab8a9b8879b979ac"
    assert witness["head"] == "c4fa8afcf8bc783e488fa168d91c121db3de6b0e"
    from scripts.testing.gallery_candidate_witness import before_gallery_candidate
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
        source = before_gallery_candidate(source, path, allow_parent=True)
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


def test_gallery_candidate_exact_inverse_and_historical_scenarios_composition():
    from scripts.testing.gallery_candidate_witness import WITNESS as GALLERY, before_gallery_candidate
    gallery = json.loads(GALLERY.read_text(encoding="utf-8"))
    assert gallery["base"] == "63581a9a1a1297396ce2227ac2683aeefd5ad8a3"
    assert gallery["head"] == "db51b8ea45ae3eeef71af16313fcb5d74242b9f1"
    historical = json.loads(WITNESS.read_text(encoding="utf-8"))
    assert set(gallery["files"]) == {"viewer/src/components/CompletedRunCompare.tsx", "viewer/src/lib/entityRunComparison.ts"}
    for path, row in gallery["files"].items():
        source = (ROOT / path).read_bytes().decode("utf-8")
        parent = before_gallery_candidate(source, path)
        assert hashlib.sha256(parent.encode()).hexdigest() == row["sha256"]
        assert row["sha256"] == historical["files"][path]["current_sha256"]
        assert before_gallery_candidate(parent, path, allow_parent=True) == parent
        with pytest.raises(AssertionError):
            before_gallery_candidate(parent, path)
        older = before_scenarios_candidate(source, path)
        assert hashlib.sha256(older.encode()).hexdigest() == historical["files"][path]["sha256"]
        assert before_gallery_candidate(older, path, allow_parent=True) == older
        for changed in (source + "\n// unrelated mutation\n", "// unrelated prefix\n" + source,
                        source.replace("\n", "\r\n")):
            for inverse in (before_gallery_candidate, before_scenarios_candidate):
                with pytest.raises(AssertionError):
                    inverse(changed, path)
        for patch in row["patches"]:
            assert source.count(patch["new"]) == 1
            for changed in (source.replace(patch["new"], patch["old"], 1),
                            source + patch["new"],
                            source.replace(patch["new"], patch["new"] + " ", 1)):
                with pytest.raises(AssertionError):
                    before_gallery_candidate(changed, path)
                if changed == parent:
                    # The one-site note edit can be completely undone; only
                    # this exact known parent is admitted by composition.
                    assert before_scenarios_candidate(changed, path) == older
                else:
                    with pytest.raises(AssertionError):
                        before_scenarios_candidate(changed, path)
    # An unrelated path is not rewritten by this deliberately narrow layer.
    assert before_gallery_candidate("untouched source", "unrelated.tsx") == "untouched source"
