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


def test_observed_upkeep_and_learning_effect_fail_then_recover(monkeypatch):
    from dataclasses import replace
    from test_scholarship import _world, _seat, _rows, _no_draw, VERDANT
    import chronicler.scholarship as scholarship
    from chronicler.learning_services import settle_observed_academy_services

    _no_draw(monkeypatch, .999)
    w = _world(agent_mode="hybrid")
    seat_id, seat = _seat(w, VERDANT, level=1)
    seat.level_turn = w.turn
    w.scholarship.learning_services = LearningServicesState()
    region = w.regions[VERDANT]
    region.stockpile.goods["crafts"] = 0
    upkeep = {}
    phase = replace(_rows(w, {VERDANT: 1}, others=8), economy=NS(region_goods={region.name: NS(prices={"craft": 1.0})}))
    scholarship.tick_scholarship(w, phase10=phase, service_upkeep=upkeep)
    assert upkeep[seat_id].due == 0 and upkeep[seat_id].paid == 0 and upkeep[seat_id].satisfied
    [receipt] = settle_observed_academy_services(w, phase, upkeep, commitments={region.name: {"crafts": 0}})
    assert (receipt.demand, receipt.native_staff, receipt.upkeep_due, receipt.upkeep_amount_paid) == (8, 1, 0, 0)
    assert receipt.funded and receipt.delivered == 0 and "crafts" in receipt.shortfalls
    owner = w.civilizations[seat.lord]
    w.turn += 1
    assert scholarship.learning_factors(w)[0][VERDANT] == 1.0
    assert scholarship.research_factor(w, owner) == 1.15

    region.stockpile.goods["crafts"] = 8
    phase = replace(_rows(w, {VERDANT: 1}, others=8), economy=NS(region_goods={region.name: NS(prices={"craft": 1.0})}))
    scholarship.tick_scholarship(w, phase10=phase, service_upkeep=upkeep)
    [receipt] = settle_observed_academy_services(w, phase, upkeep, commitments={region.name: {"crafts": 0}})
    assert (receipt.delivered, receipt.purchase_paid, receipt.crafts_used) == (8, 8, 8)
    assert receipt.upkeep_due == receipt.upkeep_amount_paid == 0
    w.turn += 1
    assert scholarship.learning_factors(w)[0][VERDANT] == 1.4
    assert scholarship.research_factor(w, owner) == 1.15
    region.controller = None
    assert scholarship.learning_factors(w)[0][VERDANT] == 1.0
    region.controller = owner.name
    seat.founded_turn -= 1
    assert scholarship.learning_factors(w)[0][VERDANT] == 1.0


def test_native_inputs_are_source_dated_and_missing_never_estimated(monkeypatch):
    from dataclasses import replace
    from test_scholarship import _world, _seat, _rows, _no_draw, VERDANT
    import chronicler.scholarship as scholarship
    from chronicler.learning_services import native_learning_counts, settle_observed_academy_services

    _no_draw(monkeypatch, .999)
    w = _world(agent_mode="hybrid")
    seat_id, seat = _seat(w, VERDANT, level=1)
    seat.level_turn = w.turn
    seat.refugees, seat.masters = 100, 50
    w.scholarship.learning_services = LearningServicesState()
    region = w.regions[VERDANT]
    region.stockpile.goods["crafts"] = 10
    phase = _rows(w, {VERDANT: 0}, others=8)
    assert native_learning_counts(phase, w.turn, len(w.regions))[0][VERDANT] == 0
    assert native_learning_counts(phase, w.turn + 1, len(w.regions)) is None
    upkeep = {}
    scholarship.tick_scholarship(w, phase10=phase, service_upkeep=upkeep)
    phase = replace(phase, economy=NS(region_goods={region.name: NS(prices={"craft": 1.0})}))
    [row] = settle_observed_academy_services(w, phase, upkeep, commitments={region.name: {"crafts": 0}})
    assert row.native_staff == 0 and row.demand == 8 and row.delivered == 0
    assert upkeep[seat_id].source_turn == w.turn

    w.turn += 1
    [unknown] = settle_observed_academy_services(w, phase, upkeep, commitments={})
    assert unknown.native_staff is None and unknown.demand is None and unknown.upkeep_paid is None
    assert unknown.craft_price is None and unknown.crafts_available is None and unknown.delivered == 0


def test_actual_upkeep_observations_preserve_paid_unpaid_and_free_due(monkeypatch):
    from test_scholarship import _world, _seat, _no_draw, VERDANT
    import chronicler.scholarship as scholarship
    _no_draw(monkeypatch, .999)
    w = _world(); seat_id, seat = _seat(w, VERDANT, level=2)
    seat.level_turn = w.turn
    out = {}
    scholarship.tick_scholarship(w, service_upkeep=out)
    assert (out[seat_id].due, out[seat_id].paid, out[seat_id].satisfied) == (0, 0, True)
    w.turn += 1
    scholarship.tick_scholarship(w, service_upkeep=out)
    assert (out[seat_id].due, out[seat_id].paid, out[seat_id].satisfied) == (1, 1, True)
    w.turn += 1
    w.civilizations[seat.lord].treasury = 0
    scholarship.tick_scholarship(w, service_upkeep=out)
    assert (out[seat_id].due, out[seat_id].paid, out[seat_id].satisfied) == (0, 0, True)
    w.turn += 1
    scholarship.tick_scholarship(w, service_upkeep=out)
    assert (out[seat_id].due, out[seat_id].paid, out[seat_id].satisfied) == (1, 0, False)


def test_teaching_demand_zero_does_not_disable_research_or_nonacademy(monkeypatch):
    from test_scholarship import _world, _seat, _no_draw, VERDANT, THORNWOOD
    import chronicler.scholarship as scholarship
    _no_draw(monkeypatch, .999)
    w = _world(); w.agent_mode = "hybrid"
    academy_id, academy = _seat(w, VERDANT, level=1)
    _seat(w, THORNWOOD, kind=LIBRARY, level=1)
    old_hazard, old_forget = scholarship.learning_factors(w)
    owner = w.civilizations[academy.lord]
    old_research = scholarship.research_factor(w, owner)
    w.scholarship.learning_services = LearningServicesState()
    assert scholarship.research_factor(w, owner) == old_research
    assert scholarship.learning_factors(w)[1] == old_forget
    # Academy local service is zero if there is no completed receipt; an
    # adjacent seat may still provide its existing neighboring influence.
    assert scholarship.learning_factors(w)[0][THORNWOOD] == old_hazard[THORNWOOD]
    w.regions[VERDANT].stockpile.goods["crafts"] = 10
    [row] = settle_academy_services(w, [item(seat_id=academy_id, demand=0)])
    assert row.delivered == 0
    w.turn += 1
    assert scholarship.research_factor(w, owner) == old_research
    assert academy_service_fraction(w, academy_id, turn=w.turn) == 0
