"""Regression for a declared constrained receiver, not an admitted recovery."""
import pytest

pytestmark = pytest.mark.native


def test_receiver_arrival_after_paid_supplies_exhausted(tmp_path, monkeypatch):
    from scripts.crisis_receiving_service_admission import run_receiving_service_admission
    run_receiving_service_admission(tmp_path, monkeypatch, require_positive=False)
