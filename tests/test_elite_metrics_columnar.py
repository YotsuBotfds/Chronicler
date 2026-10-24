"""The columnar M65a counts equal the record kernel on randomized civs."""

from dataclasses import replace
import itertools
import random

import numpy as np
import pytest

from chronicler.elite_metrics import (
    AgentEliteInput, CivEliteInput, EliteCalibration, EliteConventions,
    EliteRatchetState, EqualWealthOrder, GreatPersonEliteInput, Occupation,
    PositionRounding, WealthPercentileConvention, compute_elite_metrics,
)
from chronicler.elite_metrics_columnar import compute_civ_elite_counts

_OCCUPATIONS = tuple(Occupation)
ALL_CONVENTIONS = [
    EliteConventions(w, r, e)
    for w, r, e in itertools.product(WealthPercentileConvention, PositionRounding, EqualWealthOrder)
]


def _random_civ(rng: random.Random):
    n = rng.choice([0, 1, 2, 3, 7, 20, 60, 250])
    ids = rng.sample(range(10 * n + 5), n)
    # Few distinct wealth values make long equal-wealth groups.
    palette = [rng.choice([0.0, 1.0, 2.5, 10.0, rng.random() * 50]) for _ in range(rng.randint(1, 6))]
    wealth = [rng.choice(palette) if rng.random() < 0.7 else rng.random() * 60 for _ in range(n)]
    occupation = [rng.randrange(5) for _ in range(n)]
    skill = [rng.choice([0.0, 0.79, 0.8, 1.0, rng.random()]) for _ in range(n)]
    satisfaction = [rng.choice([0.0, 0.29, 0.3, 1.0, rng.random()]) for _ in range(n)]
    gps = []
    for k in range(rng.choice([0, 0, 1, 3, 6])):
        roll = rng.random()
        if roll < 0.3 and ids:
            gps.append(GreatPersonEliteInput(f"gp:{k}", 0, rng.choice(ids), None, None))
        elif roll < 0.5:
            absent = 10 * n + 100 + rng.randrange(3)
            gps.append(GreatPersonEliteInput(f"gp:{k}", 0, absent, 33.0, 0.2))
        else:
            gps.append(GreatPersonEliteInput(f"gp:{k}", 0, None, rng.choice(palette + [99.0]),
                                             rng.choice([0.1, 0.5])))
    if gps and rng.random() < 0.3:
        gps.append(gps[0])  # exact repeat: deduplicated by both
    population = rng.choice([0, 10, 99, 100, 101, 400, 5000])
    previous = EliteRatchetState(6, rng.choice([0.0, 0.5, 1.4]))
    return CivEliteInput(0, population, previous), ids, wealth, occupation, skill, satisfaction, gps


def _both(civ, ids, wealth, occupation, skill, satisfaction, gps, calibration, conventions):
    rows = tuple(AgentEliteInput(i, 0, w, _OCCUPATIONS[o], s, sat)
                 for i, w, o, s, sat in zip(ids, wealth, occupation, skill, satisfaction))
    reference = compute_elite_metrics(turn=7, civilizations=(civ,), agents=rows, great_persons=tuple(gps),
                                      calibration=calibration, conventions=conventions).civilizations[0]
    counts = compute_civ_elite_counts(
        turn=7, civilization=civ,
        agent_ids=np.array(ids, dtype=np.uint32), wealth=np.array(wealth, dtype=np.float64),
        occupation=np.array(occupation, dtype=np.uint8), skill=np.array(skill, dtype=np.float64),
        satisfaction=np.array(satisfaction, dtype=np.float64), great_persons=tuple(gps),
        calibration=calibration, conventions=conventions)
    return reference, counts


@pytest.mark.parametrize("seed", range(40))
def test_counts_equal_kernel_on_random_civs(seed):
    rng = random.Random(seed)
    for _ in range(25):
        civ, *columns, gps = _random_civ(rng)
        calibration = EliteCalibration(0.4, 0.1, 3.0, elite_positions_divisor=rng.choice([1, 20, 100]),
                                       elite_wealth_percentile=rng.choice([0.9, 0.9, 0.0, 0.5, 0.75, 1.0]))
        for conventions in ALL_CONVENTIONS:
            reference, counts = _both(civ, *columns, gps, calibration, conventions)
            assert counts.civ_id == reference.civ_id
            assert counts.elite_positions == reference.elite_positions
            assert counts.elite_qualifier_count == reference.elite_qualifier_count
            assert counts.elite_office_holder_count == reference.elite_office_holder_count
            assert counts.frustrated_aspirant_count == reference.frustrated_aspirant_count
            # Bit-identical floats, not approximately equal.
            assert counts.conspicuous_consumption_index.hex() == reference.conspicuous_consumption_index.hex()
            assert counts.emp.hex() == reference.emp.hex()
            assert counts.next_ratchet_state == reference.next_ratchet_state


@pytest.mark.parametrize("convention", list(WealthPercentileConvention))
def test_wealth_qualifiers_match_the_sorted_group_scan(convention):
    from chronicler.elite_metrics import _wealth_qualifiers as reference
    from chronicler.elite_metrics_columnar import _wealth_qualifiers

    rng = random.Random(17)
    for n in list(range(1, 41)) + [99, 100, 101, 1000, 1001]:
        for threshold in (0.0, 0.1, 0.3, 0.5, 0.7, 0.9, 0.95, 0.99, 1.0, rng.random()):
            wealth = [float(rng.choice([0, 1, 2, 3, 5])) if rng.random() < 0.5 else rng.random()
                      for _ in range(n)]
            rows = [AgentEliteInput(i, 0, w, Occupation.FARMER, 0.0, 0.0) for i, w in enumerate(wealth)]
            expected = reference(rows, threshold, convention)
            got = _wealth_qualifiers(np.array(wealth), threshold, convention)
            assert set(np.flatnonzero(got).tolist()) == expected, (n, threshold)


def test_ties_across_agents_and_great_persons_follow_the_equal_wealth_order():
    # Positions 2: which of the equal-wealth candidates holds office decides
    # whether the dissatisfied one is an aspirant.
    civ = CivEliteInput(0, 0, EliteRatchetState(6, 0.0))
    ids, wealth = [5, 9], [10.0, 10.0]
    occupation, skill, satisfaction = [2, 2], [0.9, 0.9], [0.9, 0.1]
    gps = [GreatPersonEliteInput("a", 0, None, 10.0, 0.1), GreatPersonEliteInput("b", 0, None, 10.0, 0.9)]
    calibration = EliteCalibration(0.4, 0.1, 3.0)
    for conventions in ALL_CONVENTIONS:
        reference, counts = _both(civ, ids, wealth, occupation, skill, satisfaction, gps,
                                  calibration, conventions)
        assert counts.frustrated_aspirant_count == reference.frustrated_aspirant_count
    first = ALL_CONVENTIONS[0]
    agents_first = replace(first, equal_wealth_order=EqualWealthOrder.AGENTS_FIRST)
    gps_first = replace(first, equal_wealth_order=EqualWealthOrder.GREAT_PERSONS_FIRST)
    a = _both(civ, ids, wealth, occupation, skill, satisfaction, gps, calibration, agents_first)[1]
    g = _both(civ, ids, wealth, occupation, skill, satisfaction, gps, calibration, gps_first)[1]
    assert (a.frustrated_aspirant_count, g.frustrated_aspirant_count) == (1, 1)
    assert a.elite_qualifier_count == g.elite_qualifier_count == 4


@pytest.mark.parametrize("mutate", [
    lambda c: c.update(ids=[1, 1]),
    lambda c: c.update(wealth=[float("nan"), 1.0]),
    lambda c: c.update(skill=[1.5, 0.0]),
    lambda c: c.update(satisfaction=[-0.1, 0.0]),
    lambda c: c.update(gps=[GreatPersonEliteInput("", 0, None, 1.0, 0.5)]),
    lambda c: c.update(gps=[GreatPersonEliteInput("k", 0, None, None, 0.5)]),
    lambda c: c.update(gps=[GreatPersonEliteInput("k", 0, None, 1.0, 0.5),
                            GreatPersonEliteInput("k", 0, None, 2.0, 0.5)]),
    lambda c: c.update(gps=[GreatPersonEliteInput("k", 0, 77, 1.0, 0.5),
                            GreatPersonEliteInput("m", 0, 77, 2.0, 0.5)]),
])
def test_invalid_inputs_are_rejected_like_the_kernel(mutate):
    columns = dict(ids=[1, 2], wealth=[1.0, 2.0], occupation=[0, 2], skill=[0.5, 0.9],
                   satisfaction=[0.5, 0.1], gps=[])
    mutate(columns)
    civ = CivEliteInput(0, 50, EliteRatchetState(6, 0.0))
    calibration = EliteCalibration(0.4, 0.1, 3.0)
    with pytest.raises(ValueError):
        compute_elite_metrics(
            turn=7, civilizations=(civ,), great_persons=tuple(columns["gps"]),
            agents=tuple(AgentEliteInput(i, 0, w, _OCCUPATIONS[o], s, sat) for i, w, o, s, sat in zip(
                columns["ids"], columns["wealth"], columns["occupation"], columns["skill"],
                columns["satisfaction"])),
            calibration=calibration, conventions=ALL_CONVENTIONS[0])
    with pytest.raises(ValueError):
        compute_civ_elite_counts(
            turn=7, civilization=civ, agent_ids=np.array(columns["ids"]),
            wealth=np.array(columns["wealth"]), occupation=np.array(columns["occupation"]),
            skill=np.array(columns["skill"]), satisfaction=np.array(columns["satisfaction"]),
            great_persons=tuple(columns["gps"]), calibration=calibration,
            conventions=ALL_CONVENTIONS[0])


def test_stale_ratchet_is_rejected():
    civ = CivEliteInput(0, 50, EliteRatchetState(3, 0.0))
    with pytest.raises(ValueError, match="N-1"):
        compute_civ_elite_counts(
            turn=7, civilization=civ, agent_ids=np.zeros(0), wealth=np.zeros(0),
            occupation=np.zeros(0), skill=np.zeros(0), satisfaction=np.zeros(0),
            great_persons=(), calibration=EliteCalibration(0.4, 0.1, 3.0),
            conventions=ALL_CONVENTIONS[0])
