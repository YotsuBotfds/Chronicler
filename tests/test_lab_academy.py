"""Declared seed-42 constructed loss and ordinary re-founding, no forced draw."""
import json
import math

import pytest

from test_learning_services_native import _paid_service_setup, _service_turn

pytestmark = pytest.mark.native


def test_explicit_restoration_and_unchanged_pair(tmp_path):
    from chronicler.scholarship import ACADEMY_FEE
    from chronicler.war.common import build_context
    from chronicler.war.peace import conclude_peace, open_war, reconcile_wars

    world, bridge, region, owner = _paid_service_setup()
    trace = []
    try:
        old_owner = world.civilizations[owner]
        hostile_i = next(i for i, civ in enumerate(world.civilizations) if i != owner)
        hostile = world.civilizations[hostile_i]
        hostile.treasury, hostile.culture, hostile.stability = 500, 80, 80
        for r in world.regions:
            r.stockpile.goods["grain"] = 1000.0
        world.regions[region].stockpile.goods["crafts"] = 1000.0
        _service_turn(world, bridge)
        first = world.scholarship.learning_services.procurement_receipts[0]
        assert first.purchased > 0 and first.paid == math.ceil(first.purchased * first.craft_price)
        _service_turn(world, bridge)
        prior = world.scholarship.learning_services.teaching_receipts[0]
        assert prior.work_delivered > 0 and prior.crafts_used > 0
        held = world.scholarship.learning_services.inventories[0].held
        assert held > 0
        context = build_context(world)
        if not any(set(pair) == {hostile.name, old_owner.name} for pair in world.active_wars):
            world.active_wars.append((hostile.name, old_owner.name))
            open_war(context, hostile, old_owner)
            world.events_timeline.extend(context.events)
        name = world.regions[region].name
        old_owner.regions = [r for r in old_owner.regions if r != name]
        if name not in hostile.regions:
            hostile.regions.append(name)
        world.regions[region].controller = hostile.name
        _service_turn(world, bridge)
        services = world.scholarship.learning_services
        assert world.scholarship.seats[0].fallen_turn == 2
        assert len(services.supply_losses) == 1
        assert services.supply_losses[0].lost == pytest.approx(held)
        assert services.inventories[0].retired and services.inventories[0].held == 0
        interrupted = services.teaching_receipts[0]
        assert interrupted.work_requested == 0 and interrupted.crafts_used in (None, 0)
        assert abs(services.material_balance["residual"]) <= services.material_balance["absolute_tolerance"]
        context = build_context(world)
        reconcile_wars(context)
        for war in list(world.war_state.wars):
            if hostile.name in (war.attacker, war.defender):
                conclude_peace(context, war, "white_peace", None)
        world.events_timeline.extend(context.events)
        hostile.capital_region = name
        while world.turn < 13:
            _service_turn(world, bridge)
        from chronicler.lab_academy import AcademyRestorationRequest as Request, preview_academy_restorations as preview, apply_academy_restorations as apply
        from dataclasses import replace
        from chronicler.run_checkpoint import RunState, write_checkpoint, read_checkpoint
        import random
        request = Request(region, 0, world.scholarship.seats[0].founder, 0, 2, hostile_i)
        path = tmp_path / "common.ckpt"
        def save(w, b, target):
            write_checkpoint(target, RunState(world=w, agent_bridge=b, memories={}, history=[], chronicle_entries=[], era_reflections={}, pending_injections=[], start_turn=0, seed=42, num_turns=20))
        save(world, bridge, path)
        control = read_checkpoint(path).state
        restored = None
        try:
            before, native, rng = world.model_dump_json(), bridge._sim.checkpoint_state(), random.getstate()
            plan, = preview(world, [request], at_turn_boundary=True)
            assert plan.changed and plan.fee == 30 and plan.new_seat_id is None
            assert world.model_dump_json() == before and bridge._sim.checkpoint_state() == native and random.getstate() == rng
            with pytest.raises(ValueError):
                apply(world, [request, Request(999, 0, request.fallen_founder, 0, 2, hostile_i)], at_turn_boundary=True)
            assert world.model_dump_json() == before
            with pytest.raises(ValueError, match="stale"):
                apply(world, [replace(request, fallen_founder=-999)], at_turn_boundary=True)
            with pytest.raises(ValueError, match="duplicate"):
                apply(world, [request, request], at_turn_boundary=True)
            original_treasury = hostile.treasury
            hostile.treasury = 59
            with pytest.raises(ValueError, match="funded"):
                apply(world, [request], at_turn_boundary=True)
            hostile.treasury = original_treasury
            assert world.model_dump_json() == before
            with pytest.raises(ValueError):
                apply(world, [request], at_turn_boundary=False)
            with pytest.raises(ValueError):
                apply(world, [request], at_turn_boundary=True, accumulator=object())
            result, = apply(world, [request], at_turn_boundary=True)
            assert result.changed and result.new_seat_id != 0 and result.event and "[Lab]" in result.event.description
            assert result.treasury_after == result.treasury_before - 30 == hostile.treasury
            assert bridge._sim.checkpoint_state() == native and random.getstate() == rng
            once = world.model_dump_json()
            repeated, = apply(world, [request], at_turn_boundary=True)
            assert not repeated.changed and repeated.fee == 0 and repeated.event is None
            assert world.model_dump_json() == once
            save(world, bridge, tmp_path / "after-fee.ckpt")
            restored = read_checkpoint(tmp_path / "after-fee.ckpt").state
            purchases, deliveries, control_new = [], [], []
            checkpointed = set()
            while world.turn < 20:
                rng = random.getstate()
                _service_turn(world, bridge)
                after = random.getstate()
                random.setstate(rng)
                _service_turn(restored.world, restored.agent_bridge)
                assert random.getstate() == after
                assert world.model_dump_json() == restored.world.model_dump_json()
                assert bridge._sim.checkpoint_state() == restored.agent_bridge._sim.checkpoint_state()
                random.setstate(rng)
                _service_turn(control.world, control.agent_bridge)
                assert random.getstate() == after
                services = world.scholarship.learning_services
                purchases.extend(p for p in services.procurement_receipts if p.seat_id == result.new_seat_id and p.purchased > 0 and p.paid > 0)
                deliveries.extend(t for t in services.teaching_receipts if t.seat_id == result.new_seat_id and (t.work_delivered or 0) > 0)
                control_new.extend(s for s in control.world.scholarship.seats[1:] if s.region == region)
                for label, condition in (("holdings", bool(purchases)), ("work", bool(deliveries))):
                    if condition and label not in checkpointed:
                        cp = tmp_path / f"after-{label}.ckpt"
                        save(world, bridge, cp)
                        roundtrip = read_checkpoint(cp).state
                        assert roundtrip.world.model_dump_json() == world.model_dump_json()
                        assert roundtrip.agent_bridge._sim.checkpoint_state() == bridge._sim.checkpoint_state()
                        roundtrip.agent_bridge.close()
                        checkpointed.add(label)
                assert services.inventories[0].lost_total == pytest.approx(held)
                assert abs(services.material_balance["residual"]) <= services.material_balance["absolute_tolerance"]
            print("RESTORATION_PAIR=" + json.dumps({"fee": result.fee, "seat": result.new_seat_id,
                "purchases": [(p.source_turn, p.purchased, p.paid) for p in purchases],
                "deliveries": [(t.source_turn, t.work_delivered, t.crafts_used) for t in deliveries],
                "control_new_seats": len(control_new), "old_loss": held}))
            assert purchases, "no actual paid supplies after explicit restoration"
            assert deliveries, "no actual native teaching restored after explicit restoration"
            assert all(t.crafts_used > 0 and t.upkeep_satisfied is True for t in deliveries)
            assert not control_new
            assert checkpointed == {"holdings", "work"}
        finally:
            control.agent_bridge.close()
            if restored is not None:
                restored.agent_bridge.close()
    finally:
        bridge.close()
