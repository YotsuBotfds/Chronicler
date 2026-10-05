"""Roadmap M65a examples and boundary tests; no runtime/bridge wiring."""

from dataclasses import FrozenInstanceError, replace
import doctest
import itertools
import random

import pytest

from chronicler import elite_metrics
from chronicler.elite_metrics import (
    AgentEliteInput, CivEliteInput, EliteCalibration, EliteConventions,
    EliteIdentity, EliteRatchetState, EqualWealthOrder, GreatPersonEliteInput,
    Occupation, PositionRounding, WealthPercentileConvention, compute_elite_metrics,
)


CALIBRATION = EliteCalibration(0.4, 0.1, 3.0)
CONVENTIONS = EliteConventions(WealthPercentileConvention.LOWER,
                               PositionRounding.FLOOR, EqualWealthOrder.AGENTS_FIRST)


def civ(civ_id=0, population=200, index=1.0, previous_turn=6):
    return CivEliteInput(civ_id, population, EliteRatchetState(previous_turn, index))


def agent(agent_id, *, civ_id=0, wealth=0.0, occupation=Occupation.FARMER,
          skill=0.0, satisfaction=0.5):
    return AgentEliteInput(agent_id, civ_id, wealth, occupation, skill, satisfaction)


def gp(key="gp", *, civ_id=0, agent_id=None, wealth=0.0, satisfaction=0.5):
    return GreatPersonEliteInput(key, civ_id, agent_id, wealth, satisfaction)


def batch(agents=(), great_persons=(), civilizations=None, *, turn=7,
          calibration=CALIBRATION, conventions=CONVENTIONS):
    return compute_elite_metrics(turn=turn,
                                 civilizations=(civ(),) if civilizations is None else civilizations,
                                 agents=agents, great_persons=great_persons,
                                 calibration=calibration, conventions=conventions)


def result(*args, **kwargs):
    return batch(*args, **kwargs).civilizations[0]


def ids(identities):
    return tuple(identity.agent_id for identity in identities)


def test_documented_runnable_example():
    failures, attempted = doctest.testmod(elite_metrics)
    assert failures == 0
    assert attempted >= 9


def test_empty_world_and_empty_civ_still_decay():
    empty = batch(civilizations=())
    assert empty.civilizations == ()
    assert (empty.snapshot_turn, empty.effective_turn) == (7, 8)
    value = result(civilizations=(civ(population=0),))
    assert value.elite_positions == 2
    assert value.qualifiers == value.office_holders == value.frustrated_aspirants == ()
    assert value.elite_qualifier_count == value.elite_office_holder_count == 0
    assert value.frustrated_aspirant_count == value.emp == 0
    assert value.conspicuous_consumption_index == pytest.approx(0.9)


@pytest.mark.parametrize("convention,expected", [
    (WealthPercentileConvention.LOWER, (19,)),
    (WealthPercentileConvention.UPPER, (19, 18)),
])
def test_strict_wealth_threshold_and_explicit_percentile_convention(convention, expected):
    rows = tuple(agent(i, wealth=float(i)) for i in range(20))
    value = result(rows, conventions=replace(CONVENTIONS, wealth_percentile=convention))
    # LOWER: rank 18/20 == .90 is excluded. UPPER: rank 18/20 is agent 17.
    assert ids(value.qualifiers) == expected


@pytest.mark.parametrize("convention,expected_count", [
    (WealthPercentileConvention.LOWER, 0),
    (WealthPercentileConvention.UPPER, 20),
])
def test_equal_wealth_keeps_equal_percentiles(convention, expected_count):
    rows = tuple(agent(i, wealth=5.0) for i in range(20))
    value = result(rows, conventions=replace(CONVENTIONS, wealth_percentile=convention))
    assert value.elite_qualifier_count == expected_count
    assert ids(value.qualifiers) == tuple(range(expected_count))


def test_wealth_percentiles_are_per_civ_and_population_is_independent():
    rows = tuple(agent(i, wealth=float(i)) for i in range(20)) + tuple(
        agent(100 + i, civ_id=1, wealth=float(i + 1000)) for i in range(20))
    output = batch(rows, civilizations=(civ(1, 500), civ(0, 300)))
    assert tuple(value.civ_id for value in output.civilizations) == (0, 1)
    assert tuple(ids(value.qualifiers) for value in output.civilizations) == ((19,), (119,))
    assert tuple(value.elite_positions for value in output.civilizations) == (3, 5)


@pytest.mark.parametrize("occupation,qualifies", [
    (Occupation.FARMER, False), (Occupation.SOLDIER, False),
    (Occupation.MERCHANT, True), (Occupation.SCHOLAR, True), (Occupation.PRIEST, True),
])
@pytest.mark.parametrize("skill", [0.799999, 0.8, 1.0])
def test_occupation_and_skill_boundary(occupation, qualifies, skill):
    value = result((agent(1, occupation=occupation, skill=skill),))
    assert value.elite_qualifier_count == int(qualifies and skill >= 0.8)


def test_qualifier_rule_is_union_not_sum():
    rows = tuple(agent(i, wealth=float(i), occupation=Occupation.MERCHANT,
                       skill=1.0, satisfaction=0.0) for i in range(20))
    value = result(rows, (gp(agent_id=19), gp("alias", agent_id=19)))
    assert value.elite_qualifier_count == 20
    assert value.elite_office_holder_count == 2
    assert value.frustrated_aspirant_count == 18
    assert ids(value.qualifiers) == tuple(reversed(range(20)))


def test_numeric_agent_id_ties_and_dissatisfied_surplus_only():
    rows = (agent(10, wealth=2.0, occupation=Occupation.SCHOLAR, skill=0.8,
                  satisfaction=0.0),
            agent(2, wealth=2.0, occupation=Occupation.PRIEST, skill=0.8,
                  satisfaction=0.0),
            agent(3, wealth=2.0, occupation=Occupation.MERCHANT, skill=0.8,
                  satisfaction=0.3),
            agent(11, wealth=1.0, occupation=Occupation.SCHOLAR, skill=0.8,
                  satisfaction=0.299999),
            agent(12, wealth=0.0, occupation=Occupation.SCHOLAR, skill=0.8,
                  satisfaction=1.0),
            agent(0, wealth=-1.0, satisfaction=0.0))
    value = result(rows)
    assert ids(value.qualifiers) == (2, 3, 10, 11, 12)
    assert ids(value.office_holders) == (2, 3)
    assert ids(value.frustrated_aspirants) == (10, 11)
    assert value.conspicuous_consumption_index == pytest.approx(1.5)
    assert value.emp == pytest.approx(1.5)  # 2/2 aspirants, not 5/2 qualifiers


def test_no_aspirants_means_zero_emp_even_during_overproduction():
    rows = tuple(agent(i, occupation=Occupation.MERCHANT, skill=0.8,
                       satisfaction=0.3) for i in range(4))
    value = result(rows)
    assert value.elite_qualifier_count == 4
    assert value.elite_office_holder_count == 2
    assert value.frustrated_aspirant_count == value.emp == 0
    assert value.conspicuous_consumption_index == pytest.approx(1.3)


def test_present_backing_snapshot_data_wins_and_gp_is_one_person():
    rows = (agent(4, wealth=9.0, satisfaction=0.0),)
    overlays = (gp("a", agent_id=4, wealth=None, satisfaction=None),
                gp("b", agent_id=4, wealth=float("nan"), satisfaction=9.0))
    value = result(rows, overlays)
    assert value.qualifiers == (EliteIdentity(4, None),)
    assert value.elite_qualifier_count == value.elite_office_holder_count == 1
    assert value.frustrated_aspirant_count == 0


def test_gp_overlay_does_not_change_wealth_percentile_denominator():
    rows = tuple(agent(i, wealth=float(i)) for i in range(20))
    overlays = tuple(gp(f"gp-{i}", wealth=1e100) for i in range(100))
    value = result(rows, overlays)
    assert tuple(identity.agent_id for identity in value.qualifiers
                 if identity.agent_id is not None) == (19,)
    assert value.elite_qualifier_count == 101


def test_absent_backing_gp_dedup_lexical_keys_and_explicit_satisfaction():
    overlays = (gp("z", agent_id=50, wealth=1.0, satisfaction=0.2),
                gp("a", agent_id=50, wealth=1.0, satisfaction=0.2),
                gp("b", wealth=2.0), gp("c", wealth=2.0),
                gp("c", wealth=2.0))
    value = result(great_persons=overlays, civilizations=(civ(population=0),))
    assert value.qualifiers == (EliteIdentity(None, "b"), EliteIdentity(None, "c"),
                                EliteIdentity(None, "a"))
    assert value.elite_qualifier_count == 3
    assert value.elite_office_holder_count == 2
    assert value.frustrated_aspirants == (EliteIdentity(None, "a"),)
    assert value.emp == pytest.approx(0.55)
    # Pure caller inputs are not filled or edited during deduplication.
    assert overlays[0].great_person_key == "z"
    assert overlays[2].agent_id is None


@pytest.mark.parametrize("order,expected", [
    (EqualWealthOrder.AGENTS_FIRST, (EliteIdentity(1, None), EliteIdentity(None, "a"))),
    (EqualWealthOrder.GREAT_PERSONS_FIRST, (EliteIdentity(None, "a"), EliteIdentity(1, None))),
])
def test_explicit_cross_kind_equal_wealth_order(order, expected):
    value = result((agent(1),), (gp("a"), gp("present", agent_id=1)),
                   conventions=replace(CONVENTIONS, equal_wealth_order=order))
    assert value.qualifiers == expected


@pytest.mark.parametrize("rounding,population,expected", [
    (PositionRounding.FLOOR, 0, 2), (PositionRounding.CEIL, 0, 2),
    (PositionRounding.FLOOR, 299, 2), (PositionRounding.CEIL, 299, 3),
    (PositionRounding.FLOOR, 300, 3), (PositionRounding.CEIL, 300, 3),
    (PositionRounding.FLOOR, 10**30 + 99, 10**28),
    (PositionRounding.CEIL, 10**30 + 99, 10**28 + 1),
])
def test_position_count_uses_explicit_integer_rounding(rounding, population, expected):
    value = result(civilizations=(civ(population=population),),
                   conventions=replace(CONVENTIONS, position_rounding=rounding))
    assert value.elite_positions == expected


def test_injected_roadmap_constants_control_classification_and_pressure():
    calibration = EliteCalibration(0.8, 0.0, 10.0, elite_wealth_percentile=1.0,
                                    elite_skill_threshold=0.9, elite_positions_divisor=50,
                                    elite_positions_min=1,
                                    frustrated_aspirant_satisfaction_threshold=0.5)
    rows = tuple(agent(i, wealth=float(i), occupation=Occupation.PRIEST,
                       skill=0.9, satisfaction=0.4) for i in range(4)) + (
                           agent(9, wealth=1e300, occupation=Occupation.PRIEST, skill=0.8),)
    value = result(rows, civilizations=(civ(population=100),), calibration=calibration)
    assert value.elite_positions == 2
    assert ids(value.qualifiers) == (3, 2, 1, 0)
    assert value.conspicuous_consumption_index == pytest.approx(1.8)
    assert value.emp == pytest.approx(1.8)


def test_ratchet_growth_cap_equilibrium_recovery_and_previous_state_transfer():
    previous = EliteRatchetState(-1, 0.0)
    rows = tuple(agent(i, occupation=Occupation.SCHOLAR, skill=0.8,
                       satisfaction=0.0) for i in range(4))
    growth = []
    for turn in range(12):
        output = batch(rows, civilizations=(CivEliteInput(0, 200, previous),), turn=turn)
        value = output.civilizations[0]
        assert (output.snapshot_turn, output.effective_turn) == (turn, turn + 1)
        growth.append(value.conspicuous_consumption_index)
        previous = value.next_ratchet_state
    assert growth[:3] == pytest.approx([0.3, 0.6, 0.9])
    assert growth[-1] == 3.0
    assert value.emp == 3.0
    # Exactly enough qualifiers to fill offices still incurs the slow decay.
    equilibrium = batch(rows[:2], civilizations=(CivEliteInput(0, 200, previous),), turn=12)
    value = equilibrium.civilizations[0]
    assert value.conspicuous_consumption_index == pytest.approx(2.9)
    assert value.emp == 0
    previous = value.next_ratchet_state
    for turn in range(13, 45):
        value = result(civilizations=(CivEliteInput(0, 200, previous),), turn=turn)
        previous = value.next_ratchet_state
    assert previous.conspicuous_consumption_index == 0.0
    assert value.emp == 0.0


def test_zero_calibration_and_previous_index_above_new_cap():
    rows = tuple(agent(i, occupation=Occupation.PRIEST, skill=0.8,
                       satisfaction=0.0) for i in range(3))
    value = result(rows, calibration=EliteCalibration(0.0, 0.0, 0.0))
    assert value.conspicuous_consumption_index == value.emp == 0.0
    assert result(calibration=EliteCalibration(0, 0, 0.5)).conspicuous_consumption_index == 0.5


def test_negative_and_extreme_finite_wealth_only_affect_order():
    rows = tuple(agent(i, wealth=wealth, occupation=Occupation.SCHOLAR, skill=1.0)
                 for i, wealth in enumerate((-1e308, -0.0, 0.0, 1e308)))
    assert ids(result(rows).qualifiers) == (3, 1, 2, 0)


def test_all_input_permutations_are_identical():
    rows = (agent(9, wealth=2.0), agent(2, occupation=Occupation.PRIEST, skill=0.8),
            agent(5, civ_id=1, occupation=Occupation.MERCHANT, skill=0.8))
    overlays = (gp("z", agent_id=30), gp("a", agent_id=30), gp("present", agent_id=9))
    civilizations = (civ(1), civ(0))
    expected = batch(rows, overlays, civilizations)
    for rows_order in itertools.permutations(rows):
        for gp_order in itertools.permutations(overlays):
            for civ_order in itertools.permutations(civilizations):
                assert batch(rows_order, gp_order, civ_order) == expected


def test_immutable_outputs_no_input_or_global_rng_mutation():
    rows = [agent(1, occupation=Occupation.MERCHANT, skill=0.8)]
    overlays = [gp()]
    civilizations = [civ()]
    original = (rows[:], overlays[:], civilizations[:])
    rng_state = random.getstate()
    output = batch(rows, overlays, civilizations)
    assert (rows, overlays, civilizations) == original
    assert random.getstate() == rng_state
    assert output == batch(rows, overlays, civilizations)
    with pytest.raises(FrozenInstanceError):
        output.effective_turn = 99
    with pytest.raises(FrozenInstanceError):
        output.civilizations[0].emp = 99


@pytest.mark.parametrize("previous_turn", [-2, 5, 7, 8])
def test_prior_state_must_be_exactly_one_turn_old(previous_turn):
    with pytest.raises(ValueError, match="snapshot_turn|N-1"):
        result(civilizations=(civ(previous_turn=previous_turn),))


@pytest.mark.parametrize("field,value", [
    ("ratchet_up_rate", -0.1), ("ratchet_down_rate", -0.1), ("ratchet_cap", -1.0),
    ("ratchet_up_rate", float("nan")), ("ratchet_down_rate", float("inf")),
    ("ratchet_cap", float("inf")), ("elite_positions_divisor", 0),
    ("elite_positions_divisor", 1.5), ("elite_positions_min", 0),
    ("elite_wealth_percentile", 1.1), ("elite_skill_threshold", -0.1),
    ("frustrated_aspirant_satisfaction_threshold", float("nan")),
    ("ratchet_up_rate", True), ("elite_positions_divisor", True),
])
def test_invalid_calibration_fails_even_with_no_civs(field, value):
    with pytest.raises(ValueError, match=field):
        batch(civilizations=(), calibration=replace(CALIBRATION, **{field: value}))


@pytest.mark.parametrize("field", ["wealth_percentile", "position_rounding", "equal_wealth_order"])
def test_conventions_have_no_implicit_string_or_default_coercion(field):
    with pytest.raises(ValueError, match=field):
        batch(conventions=replace(CONVENTIONS, **{field: "unspecified"}))
    with pytest.raises(TypeError):
        EliteConventions()
    with pytest.raises(TypeError):
        EliteCalibration()


@pytest.mark.parametrize("field,value", [
    ("agent_id", -1), ("agent_id", True), ("civ_id", -1), ("civ_id", 1),
    ("wealth", float("nan")), ("wealth", float("inf")), ("wealth", float("-inf")),
    ("wealth", None), ("skill", -0.1), ("skill", 1.1), ("skill", float("nan")),
    ("satisfaction", -0.1), ("satisfaction", 1.1), ("satisfaction", float("inf")),
    ("occupation", "merchant"),
])
def test_invalid_snapshot_rows_fail(field, value):
    with pytest.raises(ValueError):
        result((replace(agent(0), **{field: value}),))


@pytest.mark.parametrize("field,value", [
    ("civ_id", -1), ("civ_id", True), ("population", -1), ("population", 2.0),
    ("population", True),
])
def test_invalid_civ_inputs_fail(field, value):
    with pytest.raises(ValueError):
        result(civilizations=(replace(civ(), **{field: value}),))


@pytest.mark.parametrize("index", [-1.0, float("nan"), float("inf"), True])
def test_invalid_previous_ratchet_fails(index):
    with pytest.raises(ValueError):
        result(civilizations=(civ(index=index),))


@pytest.mark.parametrize("field", ["wealth", "skill", "satisfaction"])
def test_oversized_snapshot_integer_is_a_validation_error(field):
    with pytest.raises(ValueError, match="must be finite"):
        result((replace(agent(0), **{field: 10**1000}),))


def test_oversized_overlay_calibration_and_state_integers_are_validation_errors():
    with pytest.raises(ValueError, match="must be finite"):
        result(great_persons=(gp(wealth=10**1000),))
    with pytest.raises(ValueError, match="must be finite"):
        result(calibration=replace(CALIBRATION, ratchet_up_rate=10**1000))
    with pytest.raises(ValueError, match="must be finite"):
        result(civilizations=(civ(index=10**1000),))


@pytest.mark.parametrize("turn", [-1, 1.0, True])
def test_invalid_turn_fails(turn):
    with pytest.raises(ValueError, match="turn"):
        batch(turn=turn, civilizations=())


def test_duplicate_civ_and_agent_ids_rejected_including_cross_civ():
    with pytest.raises(ValueError, match="duplicate civ_id"):
        batch(civilizations=(civ(), civ()))
    for duplicate in (agent(1), agent(1, civ_id=1)):
        with pytest.raises(ValueError, match="duplicate agent_id"):
            batch((agent(1), duplicate), civilizations=(civ(), civ(1)))


@pytest.mark.parametrize("field,value", [
    ("great_person_key", ""), ("great_person_key", None), ("civ_id", 1),
    ("agent_id", -1), ("agent_id", True), ("wealth", None),
    ("wealth", float("nan")), ("satisfaction", None),
    ("satisfaction", float("inf")), ("satisfaction", -0.1), ("satisfaction", 1.1),
])
def test_absent_backing_requires_explicit_valid_data(field, value):
    with pytest.raises(ValueError):
        result(great_persons=(replace(gp(), **{field: value}),))


def test_gp_backing_cross_civ_mismatch_rejected():
    with pytest.raises(ValueError, match="civ mismatch"):
        batch((agent(1),), (gp(agent_id=1, civ_id=1),), (civ(), civ(1)))


@pytest.mark.parametrize("other", [gp(wealth=1.0), gp(satisfaction=0.2),
                                   gp(agent_id=9), gp(civ_id=1)])
def test_conflicting_duplicate_gp_keys_rejected(other):
    with pytest.raises(ValueError, match="duplicate GreatPerson key"):
        batch(great_persons=(gp(), other), civilizations=(civ(), civ(1)))


@pytest.mark.parametrize("other", [gp("b", agent_id=9, wealth=1.0),
                                   gp("b", agent_id=9, satisfaction=0.2),
                                   gp("b", agent_id=9, civ_id=1)])
def test_conflicting_absent_backing_aliases_rejected(other):
    with pytest.raises(ValueError, match="duplicate GreatPerson backing ID"):
        batch(great_persons=(gp("a", agent_id=9), other), civilizations=(civ(), civ(1)))


def test_ratchet_and_emp_numeric_overflow_fail_explicitly():
    rows = tuple(agent(i, occupation=Occupation.PRIEST, skill=0.8,
                       satisfaction=0.0) for i in range(6))
    with pytest.raises(ValueError, match="ratchet arithmetic overflow"):
        result(rows, calibration=EliteCalibration(1e308, 0.0, 1e308))
    with pytest.raises(ValueError, match="EMP arithmetic overflow"):
        result(rows, civilizations=(civ(index=1e308),),
               calibration=EliteCalibration(0.0, 0.0, 1e308))


def test_snapshot_scale_example_has_plausible_qualifier_fraction_without_changing_policy():
    # Roadmap's 5–15% gate is distribution-dependent, not a quota to force.
    rows = tuple(agent(i, wealth=float(i)) for i in range(10_000))
    value = result(rows, civilizations=(civ(population=10_000),))
    assert value.elite_qualifier_count == 999
    assert value.elite_office_holder_count == 100
    assert 0.05 <= value.elite_qualifier_count / len(rows) <= 0.15
    assert value.frustrated_aspirant_count == value.emp == 0
