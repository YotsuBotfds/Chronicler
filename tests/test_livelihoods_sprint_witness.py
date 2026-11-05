"""Strict lineage of the livelihoods sprint's reviewed inverse layers.

Source projection only: it does not qualify runtime parity, RNG, checkpoint
identity or efficacy of the sprint's mechanisms.
"""
import hashlib
import json

import pytest

from scripts.testing.livelihoods_sprint_witness import (
    LAYERS, ROOT, before_livelihoods_sprint, layer_fixture,
)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _layers():
    return [(name, json.loads(layer_fixture(name).read_text(encoding="utf-8"))) for name in LAYERS]


def test_layers_are_registered_once_and_well_formed():
    assert len(set(LAYERS)) == len(LAYERS) and LAYERS[0] == "l0"
    for name, layer in _layers():
        assert set(layer) == {"schema_version", "layer", "parent", "files"}
        assert layer["layer"] == name and layer["schema_version"] == 1
        for path, row in layer["files"].items():
            assert set(row) == {"sha256", "current_sha256", "patches"}
            assert row["patches"] and all(set(p) == {"old", "new"} for p in row["patches"])


def test_projection_reaches_each_layer_parent_and_the_baseline():
    seen = {}
    for name, layer in _layers():
        for path, row in layer["files"].items():
            seen.setdefault(path, []).append((name, row))
    for path, rows in seen.items():
        source = (ROOT / path).read_bytes().decode("utf-8")
        assert _sha(source) == rows[-1][1]["current_sha256"], path
        projected = before_livelihoods_sprint(source, path, strict=True)
        # Newer layers start from the bytes the older layer produced.
        for older, newer in zip(rows, rows[1:]):
            assert newer[1]["sha256"] == older[1]["current_sha256"], path
        # The oldest layer's parent digest is the baseline file; the historical
        # chains independently admit only those exact bytes.
        assert _sha(projected) == rows[0][1]["sha256"], path


def test_mutations_are_rejected_in_strict_mode_and_passed_on_otherwise():
    for name, layer in _layers():
        for path, row in layer["files"].items():
            source = (ROOT / path).read_bytes().decode("utf-8")
            for changed in (source + "\n# unrelated mutation\n", source.replace("\n", "\r\n")):
                with pytest.raises(AssertionError):
                    before_livelihoods_sprint(changed, path, strict=True)
                # Non-strict passes unknown bytes on unchanged for the older,
                # exact-hash historical layers to reject.
                assert before_livelihoods_sprint(changed, path) == changed
            for patch in row["patches"]:
                assert source.count(patch["new"]) == 1
                for changed in (source.replace(patch["new"], patch["old"], 1),
                                source.replace(patch["new"], patch["new"] + " ", 1)):
                    with pytest.raises(AssertionError):
                        before_livelihoods_sprint(changed, path, strict=True)


def test_unlisted_paths_pass_through_and_projection_is_idempotent():
    assert before_livelihoods_sprint("anything", "src/chronicler/not_in_any_layer.py") == "anything"
    for name, layer in _layers():
        for path in layer["files"]:
            once = before_livelihoods_sprint((ROOT / path).read_bytes().decode("utf-8"), path)
            assert before_livelihoods_sprint(once, path) == once
