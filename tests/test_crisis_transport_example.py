"""Real constructed cargo admission and replay using ordinary CLI children."""
import os
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.native


def test_constructed_transport_crisis_reaches_arrival_return_and_recovery(tmp_path):
    from test_what_if_process import _assert_real_native
    _assert_real_native()
    if os.environ.get("PYTHONHASHSEED") != "0" or sys.flags.hash_randomization:
        from test_what_if_process import _run_hash_zero_native_fixture
        _run_hash_zero_native_fixture(tmp_path, fixture_file=__file__,
                                      function_name="test_constructed_transport_crisis_reaches_arrival_return_and_recovery")
        return
    from scripts.crisis_transport_example import generate
    from chronicler.run_checkpoint import read_checkpoint
    result = generate(tmp_path / "transport")
    assert result["state"] == "validated"
    admission = result["admission"]
    assert admission["original_unchanged"] and admission["gross_cargo"] > 0
    assert admission["destination_sufficiency"] < 1
    assert admission["baseline_arrival"] and admission["disruption_return"]
    assert admission["recovery_arrivals"]
    common = Path(result["exact_pair_directory"]) / "common.ckpt"
    loaded = read_checkpoint(common)
    try:
        assert loaded.exact and loaded.state.world.turn == admission["snapshot_turn"]
        assert len(loaded.state.history) == admission["snapshot_turn"]
        assert loaded.state.run_config["output_args"]["simulate_only"] is True
        assert not any(e.event_type == "lab_transport_disruption" for e in loaded.state.world.events_timeline)
    finally:
        loaded.state.agent_bridge.close()
