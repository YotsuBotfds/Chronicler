"""B2 ``--watershed-mode flow`` with the real native extension.

The native tick receives the account's derived index before the Phase 9 sync
and, with the replaced terms switched off in its ``EcologyConfig`` (climate
water terms, irrigation water bonus, deforestation cascade) and its climate
config (harvest-shock water), must leave it as it is: the index observed after
the tick equals the derived one up to the native rounding (4 decimals), in
both native paths (``AgentSimulator`` with ``--agents hybrid``,
``EcologySimulator`` with ``--agents off``), while ``record_only`` shows the
old terms acting. A flow run resumes exactly from a checkpoint. See
docs/integration/watershed.md, section 4.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

chronicler_agents = pytest.importorskip("chronicler_agents")

pytestmark = pytest.mark.native

#: The native write-back rounds the water index to 4 decimals (and f32).
NATIVE_ROUNDING = 5e-5 + 1e-7


def _args(folder: Path, turns: int, mode: str, agents: str, **extra) -> argparse.Namespace:
    args = argparse.Namespace(
        seed=11, turns=turns, civs=10, regions=32, worldgen="procedural",
        output=str(folder / "chronicle.md"), state=str(folder / "state.json"),
        resume=None, reflection_interval=10, llm_actions=False, scenario=None,
        simulate_only=True, agents=agents, tuning_overrides={}, watershed=True, watershed_mode=mode,
    )
    for key, value in extra.items():
        setattr(args, key, value)
    return args


def _records(folder: Path) -> list[dict]:
    from chronicler.bundle_codec import load_bundle
    return [s["livelihoods"]["watershed"] for s in load_bundle(folder / "chronicle_bundle.json")["history"]]


@pytest.mark.parametrize("agents", ["hybrid", "off"])
def test_flow_leaves_the_water_index_to_the_account(tmp_path, agents):
    from chronicler.main import execute_run
    execute_run(_args(tmp_path / "flow", 30, "flow", agents))
    execute_run(_args(tmp_path / "record", 30, "record_only", agents))
    flow, record = _records(tmp_path / "flow"), _records(tmp_path / "record")
    assert len(flow) == 30 and all(r["mode"] == "flow" and r["observed"] for r in flow)
    gaps = [abs(o - d) for r in flow for o, d in zip(r["regions"]["index_observed"], r["regions"]["index_derived"])]
    assert max(gaps) <= NATIVE_ROUNDING          # no climate term, irrigation bonus or cascade acted
    irrigated = sum(1 for r in flow for w in r["regions"]["withdrawal"] if w > 0)
    assert irrigated > 0                         # irrigated regions were in play, with no bonus
    old = [abs(o - d) for r in record for o, d in zip(r["regions"]["index_observed"], r["regions"]["index_derived"])]
    assert max(old) > 0.01                       # in record_only the old terms move the index on their own


def test_a_flow_run_resumes_exactly(tmp_path):
    from chronicler import run_checkpoint as rc
    from chronicler.bundle_codec import load_bundle
    from chronicler.main import execute_run

    def content(path: Path) -> bytes:
        if path.name == "chronicle_bundle.json":
            data = load_bundle(path)
            data["metadata"].pop("generated_at", None)
            return json.dumps(data, sort_keys=True).encode()
        return path.read_bytes()

    def outputs(folder: Path) -> dict[str, bytes]:
        return {p.relative_to(folder).as_posix(): content(p) for p in sorted(folder.rglob("*"))
                if p.is_file() and p.suffix != ".ckpt"}

    straight = tmp_path / "straight"
    execute_run(_args(straight, 20, "flow", "hybrid", checkpoint_every=9, checkpoint=str(straight / "c{turn}.ckpt")))
    resumed = tmp_path / "resumed"
    args = _args(resumed, 20, "flow", "hybrid")
    args.watershed = args.watershed_mode = None
    execute_run(args, checkpoint_resume=rc.read_checkpoint(straight / "c9.ckpt"))
    expected, got = outputs(straight), outputs(resumed)
    assert got.keys() == expected.keys()
    assert [name for name in got if got[name] != expected[name]] == []
