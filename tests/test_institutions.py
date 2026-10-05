"""Standalone M63a contract tests; rates/oppositions here are fixtures only.

No production calibration or integrated M67 behavior is claimed by these tests.
"""

from dataclasses import FrozenInstanceError, replace
import doctest
import math
import random

import pytest

from chronicler import institutions as kernel
from chronicler.institutions import (
    Faction, FactionWeights, FundingPolicy, FundingResult, InstitutionCoefficients,
    InstitutionRule, InstitutionSnapshot, InstitutionState, InstitutionType as I,
    INSTITUTION_CONFLICTS, InstitutionOperation, InstitutionSpendDecision,
    InstitutionSpendDecisions, ProposalAttempt, ProposalStatus as S, RepealStatus, ResolutionOrder,
    alignment, enforcement_cost, fund_institutions, proposal_candidates,
    resolve_institutions,
)


def fund(**kwargs):
    return fund_institutions(policy=FundingPolicy.BASE_FIRST_FULL_DEBIT, **kwargs)


def free_approvals(turn):
    # Explicit pre-M66a fixture waiver; the kernel never supplies this default.
    return InstitutionSpendDecisions(turn, tuple(
        InstitutionSpendDecision(op, t, True) for op in InstitutionOperation for t in I
    ))


def coefficients(*, probability=1.0, erosion=0.1, recovery=0.02, rate=2.0,
                 opposition=None):
    """A complete explicit fixture table, not a policy recommendation."""
    return InstitutionCoefficients(probability, erosion, recovery, tuple(
        InstitutionRule(t, (opposition or {}).get(t, Faction.MERCHANT
                        if alignment(t) != Faction.MERCHANT else Faction.MILITARY), rate)
        for t in I
    ))


def state(t=I.CONSCRIPTION, *, cost=2.0, legitimacy=0.5, enacted=0, config=None):
    config = config or coefficients()
    return InstitutionState(t, enacted, legitimacy, cost, config.rule(t).opposing_faction)


def tick(*, snapshot=None, factions=None, config=None, proposals=(), treasury=100.0,
         base=0.0, regions=4, routes=3, order=ResolutionOrder.REPEAL_THEN_PROPOSE,
         funding=None, spending=None):
    snapshot = snapshot or InstitutionSnapshot(1, ())
    return resolve_institutions(
        turn=snapshot.effective_turn, snapshot=snapshot,
        factions=factions or FactionWeights(.6, .1, .2, .1),
        funding=funding or fund(turn=snapshot.effective_turn,
                                            snapshot=snapshot, treasury=treasury,
                                            base_governing_cost=base),
        coefficients=config or coefficients(), region_count=regions,
        trade_route_count=routes, proposals=proposals, resolution_order=order,
        spend_decisions=free_approvals(snapshot.effective_turn) if spending is None else spending,
    )


def test_roadmap_enum_values_order_alignment_and_conflicts():
    assert [t.value for t in I] == [
        "military_acclamation", "conscription", "frontier_garrisons", "martial_law",
        "property_rights", "free_trade", "merchant_courts", "tax_code",
        "written_law", "patronage_system", "education", "republican_virtue",
        "temple_tithe", "divine_right", "holy_inquisition", "commons_management",
    ]
    assert [alignment(t) for t in I] == [f for f in Faction for _ in range(4)]
    pairs = {(I.REPUBLICAN_VIRTUE, I.DIVINE_RIGHT), (I.FREE_TRADE, I.HOLY_INQUISITION)}
    assert sum(len(v) for v in INSTITUTION_CONFLICTS.values()) == 4
    for a, b in pairs:
        assert INSTITUTION_CONFLICTS[a] == frozenset((b,))
        assert a in INSTITUTION_CONFLICTS[b]
    with pytest.raises(TypeError):
        INSTITUTION_CONFLICTS[I.CONSCRIPTION] = frozenset()


@pytest.mark.parametrize("t", list(I))
@pytest.mark.parametrize("regions,routes", [(0, 0), (4, 7)])
def test_all_sixteen_cost_formulas(t, regions, routes):
    per_region = {I.CONSCRIPTION, I.FRONTIER_GARRISONS, I.COMMONS_MANAGEMENT}
    per_route = {I.FREE_TRADE, I.MERCHANT_COURTS, I.TAX_CODE}
    units = regions if t in per_region else routes if t in per_route else 1
    assert enforcement_cost(institution_type=t, coefficients=coefficients(rate=2.5),
                            region_count=regions, trade_route_count=routes) == 2.5 * units


def test_rule_order_and_candidate_order_ignore_influence_and_input_order():
    config = coefficients()
    assert replace(config, rules=tuple(reversed(config.rules))) == config
    weights = FactionWeights(.01, .01, .38, .60)
    candidates = proposal_candidates(InstitutionSnapshot(1, ()), weights)
    assert candidates == tuple(I)[8:]
    attempts = (ProposalAttempt(I.TEMPLE_TITHE, 0), ProposalAttempt(I.WRITTEN_LAW, 0))
    first = tick(factions=weights, proposals=attempts)
    assert first == tick(factions=weights, proposals=tuple(reversed(attempts)))
    assert [p.institution_type for p in first.proposal_outcomes] == [I.WRITTEN_LAW, I.TEMPLE_TITHE]
    assert [s.institution_type for s in first.next_state.institutions] == [I.WRITTEN_LAW, I.TEMPLE_TITHE]


@pytest.mark.parametrize("influence,status", [(.35, S.NOT_DOMINANT),
                                             (math.nextafter(.35, 1), S.ENACTED)])
def test_dominance_strict_threshold(influence, status):
    weights = FactionWeights(influence, .1, .3, .6 - influence)
    result = tick(factions=weights, proposals=(ProposalAttempt(I.CONSCRIPTION, 0),))
    assert result.proposal_outcomes[0].status == status
    assert (I.CONSCRIPTION in proposal_candidates(InstitutionSnapshot(1, ()), weights)) == (status == S.ENACTED)


@pytest.mark.parametrize("opposition,status", [(.30, S.ENACTED),
                                              (math.nextafter(.30, 1), S.OPPOSED)])
def test_proposal_opposition_strict_threshold(opposition, status):
    result = tick(factions=FactionWeights(.5, opposition, .1, .4 - opposition),
                  proposals=(ProposalAttempt(I.CONSCRIPTION, 0),))
    assert result.proposal_outcomes[0].status == status


@pytest.mark.parametrize("probability,draw,status", [
    (0.0, 0.0, S.ROLL_FAILED), (1.0, math.nextafter(1., 0.), S.ENACTED),
    (.5, .5, S.ROLL_FAILED), (.5, math.nextafter(.5, 0), S.ENACTED),
])
def test_explicit_proposal_draw_boundaries(probability, draw, status):
    result = tick(config=coefficients(probability=probability),
                  proposals=(ProposalAttempt(I.MARTIAL_LAW, draw),))
    assert result.proposal_outcomes[0].status == status


def test_empty_proposals_do_not_pick_an_institution_or_draw_randomly():
    result = tick()
    assert result.next_state == InstitutionSnapshot(2, ())
    assert result.events == result.proposal_outcomes == ()


def test_active_institution_is_not_proposed_twice():
    snapshot = InstitutionSnapshot(1, (state(),))
    assert I.CONSCRIPTION not in proposal_candidates(snapshot, FactionWeights(.6, .1, .2, .1))
    result = tick(snapshot=snapshot, proposals=(ProposalAttempt(I.CONSCRIPTION, 0),))
    assert result.proposal_outcomes[0].status == S.ALREADY_ACTIVE
    assert len(result.next_state.institutions) == 1


def test_cap_three_filters_candidates_and_denies_proposal():
    snapshot = InstitutionSnapshot(1, tuple(state(t) for t in tuple(I)[:3]))
    result = tick(snapshot=snapshot, proposals=(ProposalAttempt(I.MARTIAL_LAW, 0),))
    assert proposal_candidates(snapshot, FactionWeights(.6, .1, .2, .1)) == ()
    assert result.proposal_outcomes[0].status == S.CAP_REACHED
    assert len(result.next_state.institutions) == 3


def test_multiple_qualifying_factions_fill_last_slot_in_enum_order():
    config = coefficients(opposition={I.MARTIAL_LAW: Faction.CULTURAL,
                                      I.PROPERTY_RIGHTS: Faction.CULTURAL})
    snapshot = InstitutionSnapshot(1, (state(I.EDUCATION, config=config),
                                       state(I.PATRONAGE_SYSTEM, config=config)))
    result = tick(snapshot=snapshot, config=config, factions=FactionWeights(.4, .4, .1, .1),
                  proposals=(ProposalAttempt(I.PROPERTY_RIGHTS, 0),
                             ProposalAttempt(I.MARTIAL_LAW, 0)))
    assert [p.status for p in result.proposal_outcomes] == [S.ENACTED, S.CAP_REACHED]


@pytest.mark.parametrize("a,b", [(I.REPUBLICAN_VIRTUE, I.DIVINE_RIGHT),
                                 (I.DIVINE_RIGHT, I.REPUBLICAN_VIRTUE),
                                 (I.FREE_TRADE, I.HOLY_INQUISITION),
                                 (I.HOLY_INQUISITION, I.FREE_TRADE)])
def test_both_conflicts_are_symmetric(a, b):
    # Explicit fixture opposition avoids an unrelated faction repeal or veto.
    config = coefficients(opposition={a: Faction.MILITARY, b: Faction.MILITARY})
    snapshot = InstitutionSnapshot(1, (state(a, config=config),))
    weights = FactionWeights(.1, .4, .1, .4) if alignment(b) == Faction.MERCHANT else (
        FactionWeights(.1, .1, .4, .4))
    result = tick(snapshot=snapshot, config=config, factions=weights,
                  proposals=(ProposalAttempt(b, 0),))
    assert b not in proposal_candidates(snapshot, weights)
    assert result.proposal_outcomes[0].status == S.CONFLICT
    assert result.next_state.institutions[0].institution_type == a


def test_simultaneous_conflicting_proposals_use_canonical_priority():
    weights = FactionWeights(.1, .1, .4, .4)
    result = tick(factions=weights, proposals=(ProposalAttempt(I.DIVINE_RIGHT, 0),
                                               ProposalAttempt(I.REPUBLICAN_VIRTUE, 0)))
    assert [p.status for p in result.proposal_outcomes] == [S.ENACTED, S.CONFLICT]
    assert len(result.next_state.institutions) == 1


@pytest.mark.parametrize("opposition,repealed", [(.40, False),
                                               (math.nextafter(.40, 1), True)])
def test_faction_repeal_strict_threshold_without_capital(opposition, repealed):
    snapshot = InstitutionSnapshot(1, (state(),))
    result = tick(snapshot=snapshot, factions=FactionWeights(.3, opposition, .1, .6 - opposition))
    assert (len(result.next_state.institutions) == 0) == repealed
    assert tuple(e.reason for e in result.events) == (("faction_opposition",) if repealed else ())


def test_each_existing_institution_uses_its_own_injected_opposition():
    config = coefficients(opposition={I.WRITTEN_LAW: Faction.CLERGY})
    snapshot = InstitutionSnapshot(1, (state(I.CONSCRIPTION, config=config),
                                       state(I.WRITTEN_LAW, config=config)))
    result = tick(snapshot=snapshot, config=config, factions=FactionWeights(.1, .1, .3, .5))
    assert [s.institution_type for s in result.next_state.institutions] == [I.CONSCRIPTION]
    assert result.events[0].institution_type == I.WRITTEN_LAW


def test_caller_selects_whether_repeal_frees_a_slot_for_same_turn_proposal():
    snapshot = InstitutionSnapshot(1, tuple(state(t) for t in tuple(I)[:3]))
    config = coefficients(opposition={I.PROPERTY_RIGHTS: Faction.CULTURAL})
    kwargs = dict(snapshot=snapshot, config=config, factions=FactionWeights(.1, .6, .1, .2),
                  proposals=(ProposalAttempt(I.PROPERTY_RIGHTS, 0),))
    reuse = tick(**kwargs, order=ResolutionOrder.REPEAL_THEN_PROPOSE)
    no_reuse = tick(**kwargs, order=ResolutionOrder.PROPOSE_THEN_REPEAL)
    assert reuse.proposal_outcomes[0].status == S.ENACTED
    assert no_reuse.proposal_outcomes[0].status == S.CAP_REACHED
    assert reuse.next_state.institutions[0].institution_type == I.PROPERTY_RIGHTS
    assert no_reuse.next_state.institutions == ()


def test_caller_selects_whether_repeal_removes_a_conflict_before_proposing():
    config = coefficients(opposition={I.DIVINE_RIGHT: Faction.CULTURAL})
    snapshot = InstitutionSnapshot(1, (state(I.DIVINE_RIGHT, config=config),))
    kwargs = dict(snapshot=snapshot, config=config, factions=FactionWeights(.1, .1, .6, .2),
                  proposals=(ProposalAttempt(I.REPUBLICAN_VIRTUE, 0),))
    assert tick(**kwargs).proposal_outcomes[0].status == S.ENACTED
    assert tick(**kwargs, order=ResolutionOrder.PROPOSE_THEN_REPEAL).proposal_outcomes[0].status == S.CONFLICT


@pytest.mark.parametrize("treasury,base,demand,ratio,after", [
    (10., 3., 7., 1., 0.), (9., 3., 7., 6./7., -1.),
    (3., 3., 7., 0., -7.), (0., 3., 7., 0., -10.),
    (-5., 3., 7., 0., -15.), (100., 3., 7., 1., 90.),
    (0., 3., 0., 1., -3.), (-5., 3., 0., 1., -8.),
])
def test_funding_bookkeeping_before_debit_and_treasury_exhaustion(treasury, base, demand, ratio, after):
    snapshot = InstitutionSnapshot(1, (state(cost=demand),))
    funded = fund(turn=1, snapshot=snapshot, treasury=treasury, base_governing_cost=base)
    assert funded.last_base_governing_cost == base
    assert funded.last_institution_enforcement_cost == demand
    assert funded.last_institution_funding_ratio == ratio
    assert funded.treasury_before == treasury
    assert funded.treasury_after == after


def test_partial_aggregate_funding_erodes_all_not_enum_priority_allocation():
    snapshot = InstitutionSnapshot(1, (state(I.CONSCRIPTION, cost=1),
                                       state(I.FRONTIER_GARRISONS, cost=9)))
    result = tick(snapshot=snapshot, treasury=1, config=coefficients(erosion=.2))
    assert result.funding.last_institution_funding_ratio == .1
    assert [s.legitimacy for s in result.next_state.institutions] == [.3, .3]
    assert [e.event_type for e in result.events] == ["institution_enforcement_lapse"] * 2


def test_funded_at_exact_exhaustion_recovers_despite_zero_remaining_treasury():
    snapshot = InstitutionSnapshot(1, (state(cost=7),))
    result = tick(snapshot=snapshot, treasury=10, base=3)
    assert result.funding.treasury_after == 0
    assert result.next_state.institutions[0].legitimacy == .52
    assert result.events == ()


def test_late_treasury_does_not_replace_recorded_coverage():
    snapshot = InstitutionSnapshot(1, (state(cost=7),))
    funding = fund(turn=1, snapshot=snapshot, treasury=0, base_governing_cost=0)
    result = tick(snapshot=snapshot, funding=funding, treasury=1000)
    assert result.next_state.institutions[0].legitimacy == .4


def test_recovery_caps_at_one_and_underfunding_can_be_calibrated_to_zero_erosion():
    snapshot = InstitutionSnapshot(1, (state(legitimacy=.99),))
    assert tick(snapshot=snapshot).next_state.institutions[0].legitimacy == 1.
    result = tick(snapshot=snapshot, treasury=0, config=coefficients(erosion=0))
    assert result.next_state.institutions[0].legitimacy == .99
    assert len(result.events) == 1


@pytest.mark.parametrize("legitimacy,collapsed", [(.05, False),
                                                (math.nextafter(.05, 0), True)])
def test_neglect_collapse_strict_threshold(legitimacy, collapsed):
    snapshot = InstitutionSnapshot(1, (state(legitimacy=legitimacy),))
    result = tick(snapshot=snapshot, treasury=0, config=coefficients(erosion=0))
    assert (len(result.next_state.institutions) == 0) == collapsed
    assert [e.reason for e in result.events] == (["underfunded", "neglect"] if collapsed else ["underfunded"])


def test_neglect_clamps_at_zero_then_removes_institution_without_refunding_cost():
    snapshot = InstitutionSnapshot(1, (state(legitimacy=.1, cost=10),))
    result = tick(snapshot=snapshot, treasury=0, config=coefficients(erosion=.5))
    assert result.next_state.institutions == ()
    assert result.funding.treasury_after == -10
    assert [e.event_type for e in result.events] == ["institution_enforcement_lapse", "institution_repealed"]


def test_enactment_repeal_and_burden_are_only_effective_next_turn():
    initial = InstitutionSnapshot(7, ())
    enacted = tick(snapshot=initial, proposals=(ProposalAttempt(I.CONSCRIPTION, 0),), treasury=0)
    assert initial.institutions == ()
    assert enacted.next_state.effective_turn == 8
    new = enacted.next_state.institutions[0]
    assert (new.enacted_turn, new.legitimacy, new.enforcement_cost) == (7, 1., 8.)
    assert enacted.funding.last_institution_enforcement_cost == 0
    assert [(e.turn, e.effective_turn) for e in enacted.events] == [(7, 8)]
    with pytest.raises(ValueError, match="effective"):
        fund(turn=7, snapshot=enacted.next_state, treasury=100, base_governing_cost=0)
    next_funding = fund(turn=8, snapshot=enacted.next_state, treasury=10, base_governing_cost=0)
    assert next_funding.last_institution_enforcement_cost == 8
    removed = tick(snapshot=enacted.next_state, funding=next_funding,
                   factions=FactionWeights(.1, .6, .2, .1))
    assert removed.funding.treasury_after == 2
    assert removed.next_state == InstitutionSnapshot(9, ())
    assert enacted.next_state.institutions == (new,)
    assert fund(turn=9, snapshot=removed.next_state, treasury=2,
                            base_governing_cost=0).last_institution_enforcement_cost == 0


def test_crisis_recovery_then_neglect_across_multiple_turns():
    snapshot = InstitutionSnapshot(1, (state(legitimacy=.4, cost=1),))
    config = coefficients(erosion=.2, recovery=.1)
    for treasury, expected in [(0, .2), (1, .3), (0, .1)]:
        result = tick(snapshot=snapshot, treasury=treasury, config=config)
        assert result.next_state.institutions[0].legitimacy == pytest.approx(expected)
        snapshot = result.next_state
    result = tick(snapshot=snapshot, treasury=0, config=config)
    assert result.next_state.institutions == ()
    assert result.events[-1].reason == "neglect"
    assert tick(snapshot=result.next_state, treasury=0, config=config).events == ()


def test_supplied_persisted_cost_is_not_silently_repriced_for_new_counts():
    snapshot = InstitutionSnapshot(1, (state(cost=17),))
    result = tick(snapshot=snapshot, regions=100, routes=100)
    assert result.funding.last_institution_enforcement_cost == 17
    assert result.next_state.institutions[0].enforcement_cost == 17


def test_all_inputs_and_nested_values_are_immutable_and_rng_is_untouched():
    config = coefficients()
    source_rules = list(config.rules)
    frozen_config = replace(config, rules=source_rules)
    source_rules.clear()
    assert frozen_config == config
    source = [state(I.FRONTIER_GARRISONS), state(I.CONSCRIPTION)]
    snapshot = InstitutionSnapshot(1, source)
    source.clear()
    assert [s.institution_type for s in snapshot.institutions] == [I.CONSCRIPTION, I.FRONTIER_GARRISONS]
    weights = FactionWeights(.6, .1, .2, .1)
    prior_rng = random.getstate()
    first = tick(snapshot=snapshot, factions=weights, config=frozen_config)
    assert first == tick(snapshot=snapshot, factions=weights, config=frozen_config)
    assert prior_rng == random.getstate()
    for obj, attr, value in [(snapshot, "effective_turn", 9),
                             (snapshot.institutions[0], "legitimacy", 0),
                             (weights, "military", 0), (config, "proposal_probability", 0),
                             (first.funding, "treasury_after", 0)]:
        with pytest.raises(FrozenInstanceError):
            setattr(obj, attr, value)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf"), True, "1", 10**1000])
def test_invalid_numeric_inputs_are_rejected(value):
    with pytest.raises(ValueError):
        coefficients(probability=value)
    with pytest.raises(ValueError):
        state(cost=value)
    with pytest.raises(ValueError):
        state(legitimacy=value)
    with pytest.raises(ValueError):
        FactionWeights(value, .1, .2, .1)
    with pytest.raises(ValueError):
        fund(turn=1, snapshot=InstitutionSnapshot(1, ()),
                          treasury=value, base_governing_cost=0)
    with pytest.raises(ValueError):
        ProposalAttempt(I.CONSCRIPTION, value)


@pytest.mark.parametrize("name,value", [("probability", -.1), ("probability", 1.1),
                                        ("erosion", -.1), ("erosion", 1.1),
                                        ("recovery", -.1), ("recovery", 1.1), ("rate", -1)])
def test_invalid_coefficients(name, value):
    with pytest.raises(ValueError):
        coefficients(**{name: value})


@pytest.mark.parametrize("draw", [-.001, 1., 1.001])
def test_invalid_probability_draw(draw):
    with pytest.raises(ValueError):
        ProposalAttempt(I.CONSCRIPTION, draw)


def test_missing_duplicate_and_self_opposition_rules_are_rejected():
    config = coefficients()
    for rules in (config.rules[:-1], config.rules[:-1] + config.rules[:1]):
        with pytest.raises(ValueError, match="exactly one"):
            replace(config, rules=rules)
    with pytest.raises(ValueError, match="opposition"):
        InstitutionRule(I.CONSCRIPTION, Faction.MILITARY, 1)
    with pytest.raises(ValueError, match="opposition"):
        InstitutionState(I.CONSCRIPTION, 0, 1, 1, Faction.MILITARY)
    with pytest.raises(ValueError, match="disagrees"):
        tick(snapshot=InstitutionSnapshot(1, (state(),)),
             config=coefficients(opposition={I.CONSCRIPTION: Faction.CLERGY}))


def test_illegal_snapshot_cap_duplicates_conflicts_and_same_turn_activation():
    for values in (tuple(state(t) for t in tuple(I)[:4]), (state(), state()),
                   (state(I.REPUBLICAN_VIRTUE), state(I.DIVINE_RIGHT)),
                   (state(I.FREE_TRADE), state(I.HOLY_INQUISITION))):
        with pytest.raises(ValueError):
            InstitutionSnapshot(1, values)
    with pytest.raises(ValueError, match="N\\+1"):
        InstitutionSnapshot(1, (state(enacted=1),))


@pytest.mark.parametrize("count", [-1, True, 1.5])
def test_counts_require_nonnegative_integers(count):
    with pytest.raises(ValueError):
        tick(regions=count)
    with pytest.raises(ValueError):
        tick(routes=count)
    with pytest.raises(ValueError):
        InstitutionSnapshot(count, ())
    with pytest.raises(ValueError):
        state(enacted=count)


def test_inputs_reject_strings_unbalanced_weights_and_duplicate_faction_attempts():
    with pytest.raises(ValueError):
        ProposalAttempt("conscription", 0)
    with pytest.raises(ValueError):
        InstitutionRule(I.CONSCRIPTION, "merchant", 1)
    with pytest.raises(ValueError, match="sum to one"):
        FactionWeights(.6, .3, .2, .1)
    with pytest.raises(ValueError, match="one proposal"):
        tick(proposals=(ProposalAttempt(I.CONSCRIPTION, 0), ProposalAttempt(I.MARTIAL_LAW, 0)))
    with pytest.raises(ValueError):
        tick(order="repeal_then_propose")


def test_funding_must_match_turn_state_and_internal_bookkeeping():
    snapshot = InstitutionSnapshot(1, (state(),))
    funding = fund(turn=1, snapshot=snapshot, treasury=0, base_governing_cost=0)
    for mismatched in (replace(funding, charged_snapshot=InstitutionSnapshot(2, (state(),))),
                       replace(funding, charged_snapshot=InstitutionSnapshot(1, (state(cost=10),))),
                       replace(funding, last_institution_funding_ratio=1),
                       replace(funding, treasury_after=999),
                       replace(funding, last_institution_enforcement_cost=999)):
        with pytest.raises(ValueError, match="funding|bookkeeping"):
            tick(snapshot=snapshot, funding=mismatched)
    assert isinstance(funding, FundingResult)


def test_overflowing_demands_and_costs_are_rejected():
    snapshot = InstitutionSnapshot(1, (state(I.CONSCRIPTION, cost=1e308),
                                       state(I.FRONTIER_GARRISONS, cost=1e308)))
    with pytest.raises(ValueError, match="overflow"):
        fund(turn=1, snapshot=snapshot, treasury=0, base_governing_cost=0)
    with pytest.raises(ValueError, match="finite"):
        enforcement_cost(institution_type=I.CONSCRIPTION, coefficients=coefficients(rate=1e308),
                         region_count=100, trade_route_count=0)
    with pytest.raises(ValueError, match="finite"):
        fund(turn=1, snapshot=InstitutionSnapshot(1, (state(cost=1e308),)),
                          treasury=-1e308, base_governing_cost=0)
    with pytest.raises(ValueError, match="overflow"):
        enforcement_cost(institution_type=I.CONSCRIPTION, coefficients=coefficients(),
                         region_count=10**1000, trade_route_count=0)


def test_documented_runnable_example():
    result = doctest.testmod(kernel)
    assert result.failed == 0
    assert result.attempted == 8


@pytest.mark.parametrize("allowed", [False, None])
def test_missing_or_denied_external_spend_prevents_enactment(allowed):
    decisions = () if allowed is None else (
        InstitutionSpendDecision(InstitutionOperation.ENACT, I.CONSCRIPTION, allowed),)
    result = tick(proposals=(ProposalAttempt(I.CONSCRIPTION, 0),),
                  spending=InstitutionSpendDecisions(1, decisions))
    assert result.proposal_outcomes[0].status == S.SPEND_DENIED
    assert result.next_state.institutions == ()
    assert result.events == result.used_spend_decisions == ()


@pytest.mark.parametrize("allowed", [False, None])
def test_missing_or_denied_external_spend_prevents_forced_repeal(allowed):
    snapshot = InstitutionSnapshot(1, (state(),))
    decisions = () if allowed is None else (
        InstitutionSpendDecision(InstitutionOperation.FORCE_REPEAL, I.CONSCRIPTION, allowed),)
    result = tick(snapshot=snapshot, factions=FactionWeights(.1, .6, .2, .1),
                  spending=InstitutionSpendDecisions(1, decisions))
    assert result.next_state.institutions[0].institution_type == I.CONSCRIPTION
    assert result.repeal_outcomes[0].status == RepealStatus.SPEND_DENIED
    assert result.events == result.used_spend_decisions == ()


def test_allowed_external_spend_is_used_without_capital_affordability_checks():
    approval = InstitutionSpendDecision(InstitutionOperation.ENACT, I.CONSCRIPTION, True)
    unused = InstitutionSpendDecision(InstitutionOperation.ENACT, I.FRONTIER_GARRISONS, True)
    decisions = InstitutionSpendDecisions(1, (unused, approval))
    result = tick(proposals=(ProposalAttempt(I.CONSCRIPTION, 0),), treasury=-1000,
                  spending=decisions)
    assert result.proposal_outcomes[0].status == S.ENACTED
    assert result.used_spend_decisions == (approval,)
    assert decisions == InstitutionSpendDecisions(1, (approval, unused))
    assert result.funding.treasury_after == -1000  # enactment is effective N+1


def test_forced_repeal_acknowledges_exact_operation_and_does_not_spend_for_neglect():
    approval = InstitutionSpendDecision(InstitutionOperation.FORCE_REPEAL, I.CONSCRIPTION, True)
    snapshot = InstitutionSnapshot(1, (state(),))
    result = tick(snapshot=snapshot, factions=FactionWeights(.1, .6, .2, .1),
                  spending=InstitutionSpendDecisions(1, (approval,)))
    assert result.repeal_outcomes[0].status == RepealStatus.REPEALED
    assert result.used_spend_decisions == (approval,)
    neglected = tick(snapshot=InstitutionSnapshot(1, (state(legitimacy=.1),)),
                     treasury=0, config=coefficients(erosion=.2),
                     spending=InstitutionSpendDecisions(1, ()))
    assert neglected.next_state.institutions == ()
    assert neglected.events[-1].reason == "neglect"
    assert neglected.used_spend_decisions == neglected.repeal_outcomes == ()


def test_spend_approval_does_not_override_structural_or_probability_rules():
    approval = InstitutionSpendDecision(InstitutionOperation.ENACT, I.CONSCRIPTION, True)
    result = tick(proposals=(ProposalAttempt(I.CONSCRIPTION, 0),),
                  config=coefficients(probability=0), spending=InstitutionSpendDecisions(1, (approval,)))
    assert result.proposal_outcomes[0].status == S.ROLL_FAILED
    assert result.used_spend_decisions == ()


def test_spend_decisions_are_detached_and_stale_or_duplicate_keys_rejected():
    approval = InstitutionSpendDecision(InstitutionOperation.ENACT, I.CONSCRIPTION, True)
    original = [approval]
    decisions = InstitutionSpendDecisions(1, original)
    original.clear()
    assert decisions.decisions == (approval,)
    with pytest.raises(FrozenInstanceError):
        decisions.turn = 2
    with pytest.raises(ValueError, match="resolution turn"):
        tick(spending=InstitutionSpendDecisions(0, (approval,)))
    with pytest.raises(ValueError, match="duplicate"):
        InstitutionSpendDecisions(1, (approval, replace(approval, allowed=False)))
    with pytest.raises(ValueError, match="boolean"):
        replace(approval, allowed=1)
    with pytest.raises(ValueError):
        replace(approval, operation="enact")


def test_spend_approval_for_other_operation_or_type_cannot_authorize_enactment():
    spending = InstitutionSpendDecisions(1, (
        InstitutionSpendDecision(InstitutionOperation.FORCE_REPEAL, I.CONSCRIPTION, True),
        InstitutionSpendDecision(InstitutionOperation.ENACT, I.FRONTIER_GARRISONS, True)))
    result = tick(proposals=(ProposalAttempt(I.CONSCRIPTION, 0),), spending=spending)
    assert result.proposal_outcomes[0].status == S.SPEND_DENIED
    assert result.used_spend_decisions == ()


def test_denied_repeals_do_not_release_capacity_for_authorized_enactment():
    snapshot = InstitutionSnapshot(1, tuple(state(t) for t in tuple(I)[:3]))
    config = coefficients(opposition={I.PROPERTY_RIGHTS: Faction.CULTURAL})
    approval = InstitutionSpendDecision(InstitutionOperation.ENACT, I.PROPERTY_RIGHTS, True)
    result = tick(snapshot=snapshot, config=config, factions=FactionWeights(.1, .6, .1, .2),
                  proposals=(ProposalAttempt(I.PROPERTY_RIGHTS, 0),),
                  spending=InstitutionSpendDecisions(1, (approval,)))
    assert result.proposal_outcomes[0].status == S.CAP_REACHED
    assert len(result.next_state.institutions) == 3
    assert [o.status for o in result.repeal_outcomes] == [RepealStatus.SPEND_DENIED] * 3
    assert result.used_spend_decisions == ()


@pytest.mark.parametrize("before,after,coverage,expected", [
    (-100., -100., 1., .52), (100., 100., .5, .4),
])
def test_external_funding_coverage_is_authoritative_without_fiscal_policy_reinference(
        before, after, coverage, expected):
    snapshot = InstitutionSnapshot(1, (state(cost=2),))
    funding = FundingResult(snapshot, before, after, 0., 2., coverage,
                            FundingPolicy.EXTERNAL_AGGREGATE_RECORD)
    result = tick(snapshot=snapshot, funding=funding)
    assert result.next_state.institutions[0].legitimacy == expected
    assert result.funding is funding


def test_external_funding_rejects_demand_mismatch_without_overriding_coverage():
    snapshot = InstitutionSnapshot(1, (state(cost=2),))
    funding = FundingResult(snapshot, 100., 99., 0., 3., .5,
                            FundingPolicy.EXTERNAL_AGGREGATE_RECORD)
    with pytest.raises(ValueError, match="bookkeeping"):
        tick(snapshot=snapshot, funding=funding)


@pytest.mark.parametrize("coverage", [-.1, 1.1, float("nan"), True])
def test_invalid_external_coverage_is_rejected(coverage):
    with pytest.raises(ValueError):
        FundingResult(InstitutionSnapshot(1, (state(),)), 0., 0., 0., 2., coverage,
                      FundingPolicy.EXTERNAL_AGGREGATE_RECORD)


def test_external_zero_demand_is_neutral_and_cannot_be_generated_by_helper():
    snapshot = InstitutionSnapshot(1, ())
    with pytest.raises(ValueError, match="fully funded"):
        FundingResult(snapshot, 0., 0., 0., 0., 0., FundingPolicy.EXTERNAL_AGGREGATE_RECORD)
    with pytest.raises(ValueError, match="supplied"):
        fund_institutions(turn=1, snapshot=snapshot, treasury=0., base_governing_cost=0.,
                          policy=FundingPolicy.EXTERNAL_AGGREGATE_RECORD)


def test_fiscal_policy_and_spending_have_no_runtime_defaults():
    import inspect
    assert inspect.signature(fund_institutions).parameters["policy"].default is inspect.Parameter.empty
    assert inspect.signature(resolve_institutions).parameters["spend_decisions"].default is inspect.Parameter.empty


@pytest.mark.slow
def test_200_seed_500_turn_kernel_invariants_with_explicit_test_rng():
    """Exercise turnover/funding/order invariants, not M67 calibration targets."""
    for seed in range(200):
        rng = random.Random(seed)
        config = coefficients(probability=.6, erosion=.2, recovery=.05)
        snapshot = InstitutionSnapshot(0, ())
        for _ in range(500):
            dominant = rng.choice(tuple(Faction))
            weights = FactionWeights(*( .7 if f == dominant else .1 for f in Faction))
            candidates = proposal_candidates(snapshot, weights)
            proposals = (ProposalAttempt(rng.choice(candidates), rng.random()),) if candidates else ()
            result = tick(snapshot=snapshot, config=config, factions=weights,
                          treasury=rng.choice((-10., 0., 100.)), proposals=proposals)
            assert len(result.next_state.institutions) <= 3
            assert all(0 <= s.legitimacy <= 1 for s in result.next_state.institutions)
            assert 0 <= result.funding.last_institution_funding_ratio <= 1
            assert result.next_state.effective_turn == snapshot.effective_turn + 1
            assert all(e.effective_turn == e.turn + 1 for e in result.events)
            snapshot = result.next_state
