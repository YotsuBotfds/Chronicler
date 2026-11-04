"""Declared seed-42 constructed loss and ordinary re-founding, no forced draw."""
import json
import math

import pytest

from test_learning_services_native import _paid_service_setup, _service_turn

pytestmark = pytest.mark.native


def test_constructed_loss_and_unrestored_twenty_turn_outcome():
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
        founded = None
        purchases = []
        deliveries = []
        while world.turn < 20:
            source = world.turn
            fees_before = world.scholarship.counters["fees"]
            seats_before = len(world.scholarship.seats)
            _service_turn(world, bridge)
            services = world.scholarship.learning_services
            new = [(i, s) for i, s in enumerate(world.scholarship.seats)
                   if i >= seats_before and s.region == region]
            if new:
                seat_id, seat = new[0]
                founded = (seat_id, seat.founded_turn)
                assert seat_id != 0 and seat.founder == hostile_i
                assert world.scholarship.counters["fees"] - fees_before >= ACADEMY_FEE
                assert any(kind == "founded" for _, kind, _ in seat.history)
            if founded:
                purchases.extend(p for p in services.procurement_receipts
                                 if p.seat_id == founded[0] and p.purchased > 0 and p.paid > 0)
                deliveries.extend(t for t in services.teaching_receipts
                                  if t.seat_id == founded[0] and (t.work_delivered or 0) > 0)
            trace.append({"source": source, "controller": world.regions[region].controller,
                          "treasury": hostile.treasury, "seats": [(i, s.region, s.fallen_turn, s.founded_turn) for i, s in enumerate(world.scholarship.seats)],
                          "fees": world.scholarship.counters["fees"], "founded": founded,
                          "new_purchases": len(purchases), "new_deliveries": len(deliveries),
                          "lost_this_turn": services.material_balance["lost"]})
            assert abs(services.material_balance["residual"]) <= services.material_balance["absolute_tolerance"]
            assert services.inventories[0].lost_total == pytest.approx(held)
            assert services.material_balance["lost"] == 0
        print("DECLARED_CASE_TRACE=" + json.dumps({"region": region, "owner": owner,
              "new_owner": hostile_i, "opening_paid": first.paid, "opening_work": prior.work_delivered,
              "destroyed_held": held, "turns": trace}, default=str))
        # This fixed development case does not establish recovery. The failed
        # admission is an observed result, not an assertion that the model
        # guarantees that recovery cannot happen in any other trajectory.
        assert founded is None
        assert not purchases and not deliveries
    finally:
        bridge.close()
