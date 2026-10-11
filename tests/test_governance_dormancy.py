"""Dormant standalone governance preserves the corrected Python off-mode oracle."""
import hashlib
import json
import random
from pathlib import Path

import pytest

from chronicler import governance_kernel_harness as harness
from scripts.benchmark_headless import rng_trace, run
from scripts.third_wave_controls import legacy_artifact_bytes


FIXTURES = Path(__file__).parent / "fixtures" / "performance"
BASELINE = json.loads((FIXTURES / "corrected_423a67c.json").read_text())
ARTIFACTS = json.loads((FIXTURES / "corrected_artifacts_423a67c.json").read_text())


@pytest.mark.parametrize("name", BASELINE["workloads"])
@pytest.mark.parametrize("call_disabled", [False, True])
def test_complete_corrected_outputs_with_dormant_governance(
    name, call_disabled, tmp_path, monkeypatch,
):
    monkeypatch.setattr("chronicler.main._create_ecology_runtime", lambda world: None)
    monkeypatch.setattr("chronicler.main._create_politics_runtime", lambda world: None)
    # This callback is a test seam, never a production simulation hook. The
    # empty synthetic carry has no connection to simulation state or extractors.
    opening = harness.HarnessCarry(0, -1, (), ())
    opening_json = harness.carry_to_json(opening)
    turns = []

    def forbidden(*args, **kwargs):
        raise AssertionError("dormant governance invoked a kernel")

    for module, entry in ((harness.g01, "fund_institutions"),
                          (harness.g02, "compute_elite_metrics"),
                          (harness.g03, "resolve_spending"),
                          (harness.g04, "start_reign")):
        monkeypatch.setattr(module, entry, forbidden)

    def capture(snapshot, text, events, named):
        if call_disabled:
            before = random.getstate()
            result = harness.run_kernel_frame(
                opening=opening, observations=object(), policy=object(),
            )
            assert result.carry is opening
            assert result.receipts == () and result.elite_metrics is None
            assert random.getstate() == before
            assert harness.carry_to_json(opening) == opening_json
        data = [snapshot.model_dump(mode="json"), text,
                [event.model_dump(mode="json") for event in events],
                [event.model_dump(mode="json") for event in named]]
        turns.append(hashlib.sha256(json.dumps(
            data, ensure_ascii=False, separators=(",", ":"),
        ).encode()).hexdigest())

    expected = BASELINE["workloads"][name]
    with rng_trace(tmp_path / "rng.jsonl") as trace:
        run(expected["spec"], tmp_path / "artifacts", on_turn=capture)
    assert turns == expected["turn_sha256"]
    assert trace == expected["rng"]
    # Third-wave schema fields intentionally change raw state/bundle bytes.
    # Assert their exact dormant defaults; all original content still matches
    # the unchanged independently captured corrected-baseline oracle. The
    # fixture was captured on Unix; production text writers use platform
    # newlines. Compare their LF representation on Windows without changing
    # production writes or the frozen fixture. State/bundle JSON is already
    # canonicalized by the dormant-schema helper.
    emitted = {}
    for path in sorted((tmp_path / "artifacts").iterdir()):
        if not path.is_file():
            continue
        data = legacy_artifact_bytes(path)
        if path.name not in ("state.json", "chronicle_bundle.json"):
            data = data.replace(b"\r\n", b"\n")
        emitted[path.name] = {"sha256": hashlib.sha256(data).hexdigest(),
                              "bytes": len(data)}
    assert emitted == ARTIFACTS["workloads"][name]
