"""Pure service settlement tests: explicit observations, no native-work claim."""
from types import SimpleNamespace as NS
import pickle

import pytest

from chronicler.accumulator import StatAccumulator
from chronicler.learning_services import AcademyServiceInput as Input, academy_service_fraction, settle_academy_services
from chronicler.learning_services_state import LearningServicesState
from chronicler.scholarship_state import ACADEMY, LIBRARY, ScholarshipState, Seat
from chronicler.war.common import projected_treasury


def world(*, budget=10, crafts=20, enabled=True, turn=4):
    civ = NS(name="A", treasury=budget)
    regions = [NS(name="R", controller="A", stockpile=NS(goods={"crafts": crafts}))]
    seat = Seat(name="Academy", region=0, kind=ACADEMY, founder=0, lord=0, founded_turn=1)
    scholarship = ScholarshipState(seats=[seat], learning_services=LearningServicesState() if enabled else None)
    return NS(turn=turn, civilizations=[civ], civ_index_map={"A": 0}, regions=regions, scholarship=scholarship)


def item(**kw):
    return Input(**({"seat_id": 0, "demand": 8, "native_staff": 1, "upkeep_paid": True,
                     "craft_price": 1.0, "crafts_committed": 0.0} | kw))


def test_off_is_noop_and_old_pickle_defaults_absent():
    w = world(enabled=False)
    before = w.scholarship.model_dump()
    assert "learning_services" not in before
    assert settle_academy_services(w, [item()]) == []
    assert academy_service_fraction(w, 0, turn=5) == 1
    assert w.regions[0].stockpile.goods["crafts"] == 20
    state = w.scholarship.__getstate__()
    state["__dict__"].pop("learning_services", None)
    restored = ScholarshipState.__new__(ScholarshipState)
    restored.__setstate__(state)
    assert restored.learning_services is None
    assert "learning_services" not in restored.model_dump()
    assert pickle.loads(pickle.dumps(restored)).learning_services is None


@pytest.mark.parametrize("missing", ["demand", "native_staff", "upkeep_paid", "craft_price", "crafts_committed"])
def test_missing_authoritative_input_cannot_create_delivery(missing):
    w = world()
    [r] = settle_academy_services(w, [item(**{missing: None})])
    assert r.delivered == r.purchase_paid == 0
    assert r.shortfalls and w.regions[0].stockpile.goods["crafts"] == 20
    assert academy_service_fraction(w, 0, turn=5) == 0


def test_funded_without_staff_or_materials_then_paid_recovery_next_turn():
    w = world()
    [r] = settle_academy_services(w, [item(native_staff=0)])
    assert r.funded and r.upkeep_paid and r.delivered == 0 and "staff_capacity" in r.shortfalls
    w.turn += 1
    [r] = settle_academy_services(w, [item(crafts_committed=20)])
    assert r.funded and r.delivered == 0 and "crafts" in r.shortfalls
    w.turn += 1
    [r] = settle_academy_services(w, [item(craft_price=0.75, crafts_committed=14)])
    assert (r.attempted, r.delivered, r.crafts_purchased, r.crafts_used, r.purchase_paid) == (8, 6, 6, 6, 5)
    assert (r.crafts_stock, r.crafts_available, w.regions[0].stockpile.goods["crafts"], w.civilizations[0].treasury) == (20, 6, 14, 5)
    assert academy_service_fraction(w, 0, turn=7) == 0  # future cannot be read
    w.turn = 7
    assert academy_service_fraction(w, 0, turn=7) == .75
    w.turn = 8
    assert academy_service_fraction(w, 0, turn=8) == 0


def test_budget_projection_prevents_double_spend_and_preserves_commitments():
    w = world(budget=5, crafts=15)
    w.regions.append(NS(name="S", controller="A", stockpile=NS(goods={"crafts": 15})))
    w.scholarship.seats.append(Seat(name="Second", region=1, kind=ACADEMY, founder=0, lord=0, founded_turn=2))
    acc = StatAccumulator()
    rows = settle_academy_services(w, [item(seat_id=1, crafts_committed=12), item(crafts_committed=12)], acc=acc)
    assert [r.delivered for r in rows] == [3, 2]
    assert [r.purchase_paid for r in rows] == [3, 2]
    assert [r.budget_initial for r in rows] == [5, 2]
    assert projected_treasury(NS(world=w, acc=acc), w.civilizations[0]) == 0
    assert w.civilizations[0].treasury == 5
    assert w.regions[0].stockpile.goods["crafts"] == 12
    assert w.regions[1].stockpile.goods["crafts"] == 13
    with pytest.raises(ValueError): settle_academy_services(w, [item()], acc=acc)


def test_cash_staff_upkeep_and_identity_limits():
    w = world(budget=2)
    [r] = settle_academy_services(w, [item(craft_price=1.5)])
    assert r.delivered == pytest.approx(2 / 1.5)
    assert r.purchase_paid == 2 and "budget" in r.shortfalls
    w.turn = 5
    assert academy_service_fraction(w, 0, turn=5) == pytest.approx(1 / 6)
    w.scholarship.seats[0].name = "Replacement"
    assert academy_service_fraction(w, 0, turn=5) == 0
    w.scholarship.seats[0].name = "Academy"
    w.scholarship.seats[0].fallen_turn = 4
    assert academy_service_fraction(w, 0, turn=5) == 0
    w.scholarship.seats[0].kind = LIBRARY
    assert academy_service_fraction(w, 0, turn=5) == 1
    w = world(); [r] = settle_academy_services(w, [item(upkeep_paid=False)])
    assert not r.funded and r.delivered == 0 and "upkeep_unpaid" in r.shortfalls


def test_atomic_validation_and_cost_without_comparable_effect_claim():
    w = world(); before = w.regions[0].stockpile.goods.copy()
    with pytest.raises(ValueError): settle_academy_services(w, [item(), item()])
    assert w.civilizations[0].treasury == 10 and w.regions[0].stockpile.goods == before
    [r] = settle_academy_services(w, [item(demand=1, craft_price=2)])
    assert r.purchase_paid == 2 and r.delivered == 1
    assert r.crafts_purchased == r.crafts_used == 1  # same units, not two debits


def test_invalid_input_rejected_before_any_settlement():
    w = world()
    w.regions.append(NS(name="S", controller="A", stockpile=NS(goods={"crafts": 5})))
    w.scholarship.seats.append(Seat(name="Other", region=1, founder=0, lord=0, founded_turn=2))
    with pytest.raises(ValueError, match="craft price"):
        settle_academy_services(w, [item(), item(seat_id=1, craft_price=0)])
    assert w.civilizations[0].treasury == 10
    assert w.regions[0].stockpile.goods["crafts"] == 20
    assert w.scholarship.learning_services.last_source_turn is None


def test_zero_demand_never_divides_or_claims_service():
    w = world()
    [receipt] = settle_academy_services(w, [item(demand=0)])
    assert receipt.delivered == receipt.purchase_paid == 0
    w.turn += 1
    assert academy_service_fraction(w, 0, turn=w.turn) == 0
