"""Opt-in regional interruption against real hybrid transport."""
import random

import pytest

from chronicler.lab_transport import (
    TransportDisruptionRequest as Request,
    apply_transport_disruptions as apply,
    preview_transport_disruptions as preview,
)
from test_crisis_transport_native import _advance, _checkpoint, _commitment, _rows, _setup

pytestmark = pytest.mark.native


def test_preview_atomic_validation_and_idempotence():
    world, bridge = _setup()
    try:
        region = world.regions[2]
        region.route_suspensions["other"] = 9
        before, native, rng = world.model_dump_json(), bridge._sim.checkpoint_state(), random.getstate()
        receipt, = preview(world, [Request(2, 3)])
        assert (receipt.source_turn, receipt.prior_counter, receipt.effective_counter,
                receipt.effective_through_turn, receipt.neighbor_ids, receipt.changed) == (0, 0, 4, 2, (1,), True)
        assert receipt.event is None
        assert (world.model_dump_json(), bridge._sim.checkpoint_state(), random.getstate()) == (before, native, rng)
        for bad in ([Request(2, 2), Request(9, 1)], [Request(2, 2), Request(2, 1)],
                    [Request(True, 1)], [Request(1, True)], [Request(1, 0)], [Request(1, 7)]):
            with pytest.raises(ValueError):
                apply(world, bad)
            assert world.model_dump_json() == before
        applied, = apply(world, [Request(2, 3)])
        assert applied.event.event_type == "lab_transport_disruption"
        assert applied.event.description.startswith("[Lab]")
        from chronicler.simulation import get_injectable_event_types
        assert applied.event.event_type not in get_injectable_event_types()
        assert region.route_suspensions == {"other": 9, "trade_route": 4}
        again, = apply(world, [Request(2, 3)])
        assert not again.changed and again.event is None and again.effective_counter == 4
        assert random.getstate() == rng and bridge._sim.checkpoint_state() == native
        region.route_suspensions["trade_route"] = 10
        retained, = apply(world, [Request(2, 1)])
        assert not retained.changed and retained.effective_counter == 10 and retained.effective_through_turn == 8
    finally:
        bridge.close()


@pytest.mark.parametrize("duration", range(1, 7))
def test_exact_economy_phase_duration(duration, monkeypatch):
    from chronicler import climate
    world, bridge = _setup()
    try:
        # A separate natural disaster must not create another closure in this timing test.
        monkeypatch.setattr(climate, "check_disasters", lambda *args: [])
        receipt, = apply(world, [Request(2, duration)])
        for offset in range(duration + 1):
            source = world.turn
            _advance(world, bridge)
            counter = world.regions[2].route_suspensions.get("trade_route", 0)
            assert (counter > 0) == (offset < duration)
            if offset < duration:
                assert source <= receipt.effective_through_turn
        assert world.turn == duration + 1
    finally:
        bridge.close()


def test_actual_loaded_voyage_returns_then_recovers_after_ttl(tmp_path):
    world, bridge = _setup()
    control = control_bridge = None
    try:
        for _ in range(3):
            _, rows = _advance(world, bridge)
            candidates = [r for r in _rows(rows, "reserved")
                          if (r.origin_region, r.dest_region, r.good_slot) == (0, 2, 0)]
            if candidates:
                break
        assert candidates, f"no backed 0→2 reservation: {rows!r}"
        reservation = candidates[0]
        assert reservation.cargo_basis == "regional_stock" and reservation.quantity > 0
        assert _commitment(bridge, 0, 0)[0] >= reservation.quantity - 1e-5
        _, rows = _advance(world, bridge)
        departures = _rows(rows, "departed", reservation.voyage_id)
        assert len(departures) == 1 and not _rows(rows, "arrived", reservation.voyage_id)
        qty = departures[0].quantity
        assert qty > 0 and _commitment(bridge, 0, 0)[1] >= qty - 1e-5
        control, control_bridge = _checkpoint(tmp_path, world, bridge)
        treasury = [c.treasury for c in world.civilizations]
        native = bridge._sim.checkpoint_state()
        applied, = apply(world, [Request(2, 1)])
        assert applied.changed and applied.event and applied.effective_counter == 2
        assert [c.treasury for c in world.civilizations] == treasury
        assert bridge._sim.checkpoint_state() == native
        assert not apply(world, [Request(2, 1)])[0].changed
        state = random.getstate()
        _, interrupted = _advance(world, bridge)
        after = random.getstate()
        random.setstate(state)
        _, uninterrupted = _advance(control, control_bridge)
        assert random.getstate() == after
        returned = _rows(interrupted, "returned", reservation.voyage_id)
        assert len(returned) == 1 and returned[0].quantity == pytest.approx(qty)
        assert not _rows(interrupted, "arrived", reservation.voyage_id)
        arrivals = _rows(uninterrupted, "arrived", reservation.voyage_id)
        assert len(arrivals) == 1 and arrivals[0].quantity == pytest.approx(qty)
        recovery = []
        for _ in range(6):
            _, rows = _advance(world, bridge)
            recovery.extend(rows)
        assert "trade_route" not in world.regions[2].route_suspensions
        assert not _rows(recovery, "returned", reservation.voyage_id)
        recovered = [r for r in _rows(recovery, "arrived")
                     if r.dest_region == 2 and r.good_slot == 0
                     and _rows(recovery, "reserved", r.voyage_id)
                     and _rows(recovery, "departed", r.voyage_id)]
        assert recovered, f"no newly reserved and delivered recovery voyage: {recovery!r}"
        _advance(world, bridge)  # consume pending flow buffer with conservation checks
    finally:
        bridge.close()
        if control_bridge is not None:
            control_bridge.close()


def test_rejects_nonphysical_or_nonhybrid_world():
    world, bridge = _setup()
    try:
        world.agent_mode = "off"
        with pytest.raises(ValueError, match="physical hybrid"):
            preview(world, [Request(0, 1)])
        world.agent_mode = "hybrid"
        world._agent_bridge = None
        with pytest.raises(ValueError, match="physical hybrid"):
            apply(world, [Request(0, 1)])
        assert not world.regions[0].route_suspensions
    finally:
        bridge.close()
