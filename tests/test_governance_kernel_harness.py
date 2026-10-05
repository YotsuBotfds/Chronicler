"""Joint deterministic synthetic experiments; never simulation integration."""
from dataclasses import replace
from fractions import Fraction
from itertools import permutations
import json
import random
import sys

import pytest

from chronicler import governance_kernel_harness as h
from chronicler import institutions as i
from chronicler import elite_metrics as e
from chronicler import governance_capital as c
from chronicler import ruler_ambitions as a


def policy(**changes):
    rules = tuple(i.InstitutionRule(t, i.Faction.MERCHANT if i.alignment(t) != i.Faction.MERCHANT
                                   else i.Faction.MILITARY, 2.) for t in i.InstitutionType)
    p = h.HarnessPolicy(h.POLICY_ID,
        i.InstitutionCoefficients(1., .1, .02, rules),
        e.EliteCalibration(.1, .1, 2.),
        e.EliteConventions(e.WealthPercentileConvention.LOWER, e.PositionRounding.FLOOR, e.EqualWealthOrder.AGENTS_FIRST),
        c.CapitalCoefficients(.5, 0., 0., .05, .1, .1, 0., .1, .2),
        c.SpendCosts(.1, .2, .15),
        a.AmbitionCalibration(2, 20, 40, .1, .05, ((a.AmbitionType.CONQUER_REGION, 1.), (a.AmbitionType.PATRON_OF_ARTS, 1.))),
        i.FundingPolicy.BASE_FIRST_FULL_DEBIT,
        'fractional_fixture_no_integer_treasury', 'persisted_enactment_cost', 'reign_long_no_decay',
        'defer_new_objectives', 'carry_remaining', 'synthetic_living_row_count', 'abort_frame', Fraction(10), 'monotone_complete_cursor_log')
    return replace(p, **changes)


def initial(civ=0, balance=Fraction(3, 10), *, turn=1, institutions=(), reign=None):
    if reign is None:
        reign = a.RulerAmbitions(str(civ), f'reign-{civ}', 0, 0, ())
    return h.CivCarry(civ, i.InstitutionSnapshot(turn, institutions), e.EliteRatchetState(turn - 1, 0.),
                      c.GovernanceState(turn, .5, float(balance), balance), reign)


def carry(*civs):
    civs = civs or (initial(),)
    turn = civs[0].governance.effective_turn
    return h.HarnessCarry(turn, turn - 1, tuple(c.civ_id for c in civs), tuple(civs))


def observation(civ=0, turn=1, **changes):
    o = h.CivObservation(civ, i.FactionWeights(.6, .1, .2, .1), 100., 0., 4, 3, (), (),
        a.AmbitionSnapshot(str(civ), f'reign-{civ}', turn, 0, .5, .3), c.LegitimacyInputs(), (), None, (), None)
    return replace(o, **changes)


def frame(*observations, agents=(), great_persons=()):
    observations = observations or (observation(),)
    turn = observations[0].ambition_snapshot.turn
    return h.SyntheticFrame(turn, turn, 'explicit_synthetic_fixture', tuple(observations), tuple(agents), tuple(great_persons))


def run(opening=None, observations=None, config=None):
    return h.run_kernel_frame(enabled=True, opening=opening or carry(), observations=observations or frame(), policy=config or policy())


def institution(kind, *, legitimacy=.5, cost=2.):
    return i.InstitutionState(kind, 0, legitimacy, cost, policy().institutions.rule(kind).opposing_faction)


def next_observation(result, **changes):
    civ = result.carry.civilizations[0]
    return observation(turn=result.carry.effective_turn,
        ambition_snapshot=a.AmbitionSnapshot('0', civ.reign.ruler_id, result.carry.effective_turn,
                                             civ.evidence_cursor, .5, .3), **changes)


def test_disabled_is_identity_without_kernel_or_rng_calls(monkeypatch):
    opening = carry()
    def forbidden(*args, **kwargs):
        raise AssertionError('disabled kernel called')
    for module, name in [(i, 'fund_institutions'), (e, 'compute_elite_metrics'),
                         (c, 'resolve_spending'), (a, 'start_reign')]:
        monkeypatch.setattr(module, name, forbidden)
    before = random.getstate()
    result = h.run_kernel_frame(opening=opening, observations=object(), policy=object())
    assert result.carry is opening and result.receipts == () and result.elite_metrics is None
    assert random.getstate() == before


def test_exact_boundary_priority_single_wallet_and_lossless_restart():
    obs = observation(proposals=(i.ProposalAttempt(i.InstitutionType.CONSCRIPTION, 0.),),
                      mock_suppressions=(h.MockSuppression('mock-revolt', True),))
    result = run(observations=frame(obs))
    receipt = result.receipts[0]
    assert [d.request.action for d in receipt.spending.decisions] == [c.GovernanceAction.ENACT_INSTITUTION, c.GovernanceAction.SUPPRESS_SECESSION]
    assert [d.approved for d in receipt.spending.decisions] == [True, True]
    assert receipt.spending.state.exact_political_capital == 0
    assert len(receipt.institutions.used_spend_decisions) == 1
    restored = h.carry_from_json(h.carry_to_json(result.carry))
    assert restored == result.carry
    with pytest.raises(ValueError, match='epoch'):
        run(restored, frame(obs))
    assert run(observations=frame(obs)) == result  # deterministic pure preview


def test_fraction_sub_float_residual_persists_and_affects_affordability():
    # Both balances present as .1 but only one covers canonical .1 cost.
    balance = Fraction(1, 10) - Fraction(1, 10**40)
    opening = carry(initial(balance=balance))
    restored = h.carry_from_json(h.carry_to_json(opening))
    assert restored.civilizations[0].governance.exact_political_capital == balance
    result = run(restored, frame(observation(proposals=(i.ProposalAttempt(i.InstitutionType.CONSCRIPTION, 0.),))))
    assert not result.receipts[0].spending.decisions[0].approved
    assert result.carry.civilizations[0].governance.exact_political_capital == balance


@pytest.mark.parametrize('balance', [Fraction(0), Fraction(9, 100)])
def test_insufficient_budget_keeps_institution_and_mock_denials_zero_cost(balance):
    result = run(carry(initial(balance=balance)), frame(observation(
        proposals=(i.ProposalAttempt(i.InstitutionType.CONSCRIPTION, 0.),),
        mock_suppressions=(h.MockSuppression('x', True),))))
    assert all(not d.approved for d in result.receipts[0].spending.decisions)
    assert result.carry.civilizations[0].governance.exact_political_capital == balance
    assert result.carry.civilizations[0].institutions.institutions == ()


def test_same_turn_generated_credit_cannot_fund_request():
    result = run(carry(initial(balance=Fraction(0))), frame(observation(mock_suppressions=(h.MockSuppression('x', True),))),
                 policy(capital=replace(policy().capital, political_capital_base=.3)))
    assert not result.receipts[0].spending.decisions[0].approved
    assert result.receipts[0].spending.state.exact_political_capital == 0
    assert result.carry.civilizations[0].governance.exact_political_capital == Fraction(3, 10)
    assert result.carry.effective_turn == 2


@pytest.mark.parametrize('draw, factions, active, expected', [
    (.9, i.FactionWeights(.6, .1, .2, .1), (), 'roll_failed'),
    (0., i.FactionWeights(.2, .1, .6, .1), (), 'not_dominant'),
    (0., i.FactionWeights(.6, .1, .2, .1), (i.InstitutionType.CONSCRIPTION,), 'already_active'),
    (0., i.FactionWeights(.6, .1, .2, .1), (i.InstitutionType.WRITTEN_LAW, i.InstitutionType.EDUCATION, i.InstitutionType.PATRONAGE_SYSTEM), 'cap_reached'),
])
def test_unused_provisional_approvals_do_not_burn_capital(draw, factions, active, expected):
    opening = carry(initial(institutions=tuple(institution(t) for t in active)))
    result = run(opening, frame(observation(factions=factions,
        proposals=(i.ProposalAttempt(i.InstitutionType.CONSCRIPTION, draw),))),
        policy(institutions=replace(policy().institutions, proposal_probability=.5)))
    assert result.receipts[0].institutions.proposal_outcomes[0].status.value == expected
    assert result.receipts[0].spending.decisions == ()
    assert result.carry.civilizations[0].governance.exact_political_capital == Fraction(3, 10)


def test_conflict_rejected_enact_is_not_reenabled_by_later_repeal():
    # Holy Inquisition conflicts with Free Trade. Merchant opposition makes it
    # eligible for repeal, but the earlier failed enact remains structurally unused.
    opening = carry(initial(institutions=(institution(i.InstitutionType.HOLY_INQUISITION),)))
    obs = observation(factions=i.FactionWeights(.1, .6, .2, .1),
        proposals=(i.ProposalAttempt(i.InstitutionType.FREE_TRADE, 0.),))
    result = run(opening, frame(obs))
    assert result.receipts[0].institutions.proposal_outcomes[0].status == i.ProposalStatus.CONFLICT
    assert result.receipts[0].spending.decisions[0].request.action == c.GovernanceAction.FORCE_REPEAL_INSTITUTION
    assert result.carry.civilizations[0].institutions.institutions == ()
    assert result.carry.civilizations[0].governance.exact_political_capital == Fraction(15, 100)


def test_rejected_repeal_cannot_free_slot_or_enable_conflicting_proposal():
    opening = carry(initial(balance=Fraction(1, 10), institutions=(institution(i.InstitutionType.HOLY_INQUISITION),)))
    result = run(opening, frame(observation(factions=i.FactionWeights(.1, .6, .2, .1),
        proposals=(i.ProposalAttempt(i.InstitutionType.FREE_TRADE, 0.),))))
    assert not result.receipts[0].spending.decisions[0].approved
    assert len(result.carry.civilizations[0].institutions.institutions) == 1
    assert result.carry.civilizations[0].governance.exact_political_capital == Fraction(1, 10)


def test_funding_erosion_commits_once_and_late_repeal_preserves_current_demand():
    opening = carry(initial(institutions=(institution(i.InstitutionType.HOLY_INQUISITION),)))
    result = run(opening, frame(observation(treasury=0., factions=i.FactionWeights(.1, .6, .2, .1),
        proposals=(i.ProposalAttempt(i.InstitutionType.PROPERTY_RIGHTS, 0.),))))
    receipt = result.receipts[0]
    assert receipt.institutions.funding.last_institution_enforcement_cost == 2.
    assert receipt.institutions.funding.treasury_after == -2.
    assert [ev.event_type for ev in receipt.institutions.events].count('institution_enforcement_lapse') == 1
    assert receipt.institutions.next_state.institutions[0].institution_type == i.InstitutionType.PROPERTY_RIGHTS
    assert receipt.institutions.next_state.institutions[0].enacted_turn == 1


def test_new_enactment_is_charged_first_on_next_frame_and_cost_is_persisted():
    first = run(observations=frame(observation(proposals=(i.ProposalAttempt(i.InstitutionType.CONSCRIPTION, 0.),))))
    assert first.receipts[0].institutions.funding.last_institution_enforcement_cost == 0.
    second = run(first.carry, frame(next_observation(first, region_count=99)))
    assert second.receipts[0].institutions.funding.last_institution_enforcement_cost == 8.
    assert second.carry.civilizations[0].institutions.institutions[0].enforcement_cost == 8.


def test_full_priority_enact_then_repeal_then_sorted_mock_suppression():
    opening = carry(initial(balance=Fraction(45, 100), institutions=(institution(i.InstitutionType.HOLY_INQUISITION),)))
    obs = observation(factions=i.FactionWeights(.1, .6, .2, .1),
        proposals=(i.ProposalAttempt(i.InstitutionType.PROPERTY_RIGHTS, 0.),),
        mock_suppressions=(h.MockSuppression('z', True), h.MockSuppression('a', True)))
    result = run(opening, frame(obs))
    decisions = result.receipts[0].spending.decisions
    assert [d.request.action for d in decisions] == [c.GovernanceAction.ENACT_INSTITUTION,
        c.GovernanceAction.FORCE_REPEAL_INSTITUTION, c.GovernanceAction.SUPPRESS_SECESSION, c.GovernanceAction.SUPPRESS_SECESSION]
    assert [d.approved for d in decisions] == [True, True, True, False]
    assert json.loads(decisions[2].request.request_id)[-1] == 'a'
    assert result.carry.civilizations[0].governance.exact_political_capital == 0


def test_joint_civ_agent_proposal_suppression_permutation_stability():
    agents = tuple(e.AgentEliteInput(k, k % 2, 10., e.Occupation.SCHOLAR, .9, .1) for k in range(6))
    obs0 = observation(factions=i.FactionWeights(.01, .01, .38, .6), proposals=(
        i.ProposalAttempt(i.InstitutionType.TEMPLE_TITHE, 0.), i.ProposalAttempt(i.InstitutionType.WRITTEN_LAW, 0.)),
        mock_suppressions=(h.MockSuppression('z', True), h.MockSuppression('a', True)))
    obs1 = observation(1)
    expected = run(carry(initial(0), initial(1)), frame(obs0, obs1, agents=agents))
    for civs in permutations((initial(0), initial(1))):
        for observations in permutations((obs0, obs1)):
            obs = tuple(replace(o, proposals=tuple(reversed(o.proposals)), mock_suppressions=tuple(reversed(o.mock_suppressions))) for o in observations)
            assert run(carry(*civs), frame(*obs, agents=tuple(reversed(agents)))) == expected


def test_joint_elite_conventions_and_absent_gp_require_explicit_observations():
    agents = tuple(e.AgentEliteInput(k, 0, 5., e.Occupation.FARMER, .1, .1) for k in range(4))
    lower = run(observations=frame(agents=agents))
    upper = run(observations=frame(agents=agents), config=policy(elite_conventions=replace(policy().elite_conventions, wealth_percentile=e.WealthPercentileConvention.UPPER)))
    assert lower.elite_metrics.civilizations[0].elite_qualifier_count == 0
    assert upper.elite_metrics.civilizations[0].elite_qualifier_count == 4
    with pytest.raises(ValueError, match='absent GP'):
        run(observations=frame(great_persons=(e.GreatPersonEliteInput('gp', 0, None, None, None),)))


def completed_goal_opening(*, completed=False):
    goal = a.Ambition(a.AmbitionType.CONQUER_REGION, 'Border', 0, 20, 0, completed=completed)
    return carry(initial(reign=a.RulerAmbitions('0', 'reign-0', 0, 0, (goal,))))


def test_keyed_signed_reward_survives_saturated_preview_reload_and_next_recompute():
    opening = completed_goal_opening()
    civ = opening.civilizations[0]
    opening = replace(opening, civilizations=(replace(civ, governance=replace(civ.governance, ruler_legitimacy=.99)),))
    snapshot = a.AmbitionSnapshot('0', 'reign-0', 1, 0, .99, .3, owned_regions=('Border',))
    obs = observation(ambition_snapshot=snapshot)
    preview = a.evaluate_ambitions(opening.civilizations[0].reign, snapshot, policy().ambitions)
    assert preview.legitimacy == 1. and preview.applied_legitimacy_delta == pytest.approx(.01)
    assert preview.requested_legitimacy_delta == .1
    first = run(opening, frame(obs), policy(capital=replace(policy().capital, legitimacy_base=.97)))
    assert first.carry.civilizations[0].contributions[0].delta == .1
    assert first.carry.civilizations[0].governance.ruler_legitimacy == 1.
    second = run(h.carry_from_json(h.carry_to_json(first.carry)), frame(next_observation(first)))
    assert second.receipts[0].ambition_outcomes == ()
    assert second.receipts[0].accrual.legitimacy_sources.ambitions == .1
    assert second.carry.civilizations[0].governance.ruler_legitimacy == .6


def test_failed_goal_negative_contribution_persists():
    opening = carry(initial(turn=20, reign=a.RulerAmbitions('0', 'reign-0', 0, 0,
        (a.Ambition(a.AmbitionType.CONQUER_REGION, 'Border', 0, 20, 0),))))
    first = run(opening, frame(observation(turn=20)))
    assert first.receipts[0].accrual.legitimacy_sources.ambitions == -.05
    second = run(first.carry, frame(next_observation(first)))
    assert second.receipts[0].accrual.legitimacy_sources.ambitions == -.05
    assert second.receipts[0].ambition_outcomes == ()


def test_duplicate_replayed_and_conflicting_contributions():
    key = a.AmbitionContributionKey('0', 'reign/"0', 0, 0, a.AmbitionType.CONQUER_REGION)
    entry = h.Contribution(key, .1)
    merged = h.merge_contributions((entry,), (entry, entry))
    assert merged == (entry,)
    assert json.loads(h.contribution_id(key))[2] == 'reign/"0'
    with pytest.raises(ValueError, match='conflicting replayed'):
        h.merge_contributions(merged, (replace(entry, delta=-.05),))


@pytest.mark.parametrize('transfer, expected', [('carry_remaining', Fraction(3, 10)), ('reset_zero', Fraction(0))])
def test_accession_archives_old_awards_resets_new_reign_and_defers_events(transfer, expected):
    completed = run(completed_goal_opening(), frame(observation(ambition_snapshot=a.AmbitionSnapshot(
        '0', 'reign-0', 1, 0, .5, .3, owned_regions=('Border',)))))
    snapshot = a.AmbitionSnapshot('0', 'new-reign', 2, 12, .5, .3, arts_available=True)
    obs = observation(turn=2, ambition_snapshot=snapshot, accession=c.SuccessionKind.PEACEFUL,
        ambition_draws=(a.SelectionDraw(0., 0., 0.),) * 2, accession_event_cursor=10,
        events=(a.EvidenceEvent(2, 11, '0', 'invest_culture'),))
    first = run(completed.carry, frame(obs), policy(capital_on_accession=transfer))
    civ = first.carry.civilizations[0]
    assert civ.governance.exact_political_capital == expected
    assert first.receipts[0].ambition_outcomes == () and civ.contributions == ()
    assert len(civ.archives) == 1 and len(civ.archives[0].contributions) == 1
    assert civ.governance.ruler_legitimacy == .6
    assert civ.pending_events == obs.events
    assert 'ambition_completed_conquer_region' in civ.reign.ruler_event_tags
    second = run(h.carry_from_json(h.carry_to_json(first.carry)), frame(next_observation(first,
        events=(a.EvidenceEvent(2, 11, '0', 'invest_culture'),))))
    assert len(second.receipts[0].ambition_outcomes) == 1
    assert second.receipts[0].ambition_outcomes[0].ambition_type == a.AmbitionType.PATRON_OF_ARTS
    assert second.carry.civilizations[0].pending_events == ()
    assert second.receipts[0].accrual.legitimacy_sources.ambitions == .1


def test_reused_historical_reign_id_and_implicit_accession_fail():
    first = run(observations=frame(observation(ambition_snapshot=a.AmbitionSnapshot('0', 'new', 1, 0, .5, .3),
        accession=c.SuccessionKind.CONTESTED, accession_event_cursor=0, ambition_draws=(a.SelectionDraw(0., 0., 0.),)*2)))
    with pytest.raises(ValueError, match='historical reign'):
        run(first.carry, frame(observation(turn=2, accession=c.SuccessionKind.PEACEFUL, accession_event_cursor=0,
            ambition_draws=(a.SelectionDraw(0., 0., 0.),)*2)))
    with pytest.raises(ValueError, match='explicit succession'):
        run(observations=frame(observation(ambition_snapshot=a.AmbitionSnapshot('0', 'new', 1, 0, .5, .3))))


def test_partial_multiciv_failure_rolls_back_everything(monkeypatch):
    opening = carry(initial(0), initial(1))
    before = h.carry_to_json(opening)
    real = c.accrue_capital
    calls = []
    def broken(*args, **kwargs):
        calls.append(args[0])
        if len(calls) == 2:
            raise RuntimeError('injected failure after first civ accrual')
        return real(*args, **kwargs)
    monkeypatch.setattr(c, 'accrue_capital', broken)
    with pytest.raises(RuntimeError, match='injected'):
        run(opening, frame(observation(0, proposals=(i.ProposalAttempt(i.InstitutionType.CONSCRIPTION, 0.),)), observation(1)))
    assert len(calls) == 2
    assert h.carry_to_json(opening) == before
    monkeypatch.setattr(c, 'accrue_capital', real)
    retry = run(opening, frame(observation(0), observation(1)))
    assert retry.carry.last_committed_turn == 1


def test_acknowledgement_or_complete_batch_mismatch_aborts(monkeypatch):
    opening = carry()
    before = h.carry_to_json(opening)
    real = c.resolve_spending
    def broken(prior, requests, costs):
        result = real(prior, requests, costs)
        if len(requests) == 2:
            return replace(result, decisions=tuple(reversed(result.decisions)))
        return result
    monkeypatch.setattr(c, 'resolve_spending', broken)
    with pytest.raises(ValueError, match='reconciliation'):
        run(opening, frame(observation(proposals=(i.ProposalAttempt(i.InstitutionType.CONSCRIPTION, 0.),),
            mock_suppressions=(h.MockSuppression('x', True),))))
    assert h.carry_to_json(opening) == before


@pytest.mark.parametrize('changes, message', [
    ({'origin': 'simulation'}, 'synthetic'), ({'source_turn': 0}, 'epoch'),
    ({'ownership_epoch': 0}, 'ownership epoch'), ({'civilizations': ()}, 'registry'),
    ({'civilizations': (observation(), observation())}, 'registry'),
])
def test_missing_stale_or_non_synthetic_frames_fail_atomically(changes, message):
    opening = carry()
    with pytest.raises(ValueError, match=message):
        run(opening, replace(frame(), **changes))
    assert opening == carry()


def test_missing_policy_and_unresolved_choices_fail_clearly():
    with pytest.raises(ValueError, match='complete policy'):
        h.run_kernel_frame(opening=carry(), enabled=True, observations=frame())
    for field in ['fiscal_rounding', 'enforcement_pricing', 'contribution_retention', 'accession_evaluation',
                  'population_source', 'missing_observations', 'policy_id']:
        with pytest.raises(ValueError, match=field):
            policy(**{field: 'unresolved'})
    with pytest.raises(ValueError, match='capital_on_accession'):
        policy(capital_on_accession='unknown')


def test_external_funding_needs_record_and_matches_frozen_epoch():
    p = policy(funding=i.FundingPolicy.EXTERNAL_AGGREGATE_RECORD)
    with pytest.raises(ValueError, match='external fiscal'):
        run(config=p)
    opening = carry(initial(institutions=(institution(i.InstitutionType.CONSCRIPTION),)))
    funding = i.FundingResult(opening.civilizations[0].institutions, 100., 99., 0., 2., .5, p.funding)
    result = run(opening, frame(observation(external_funding=funding)), p)
    assert result.receipts[0].institutions.funding == funding
    assert result.carry.civilizations[0].institutions.institutions[0].legitimacy == .4
    with pytest.raises(ValueError, match='external fiscal'):
        run(opening, frame(observation(external_funding=replace(funding, treasury_before=99.))), p)


def test_duplicate_request_keys_and_ineligible_mock_are_never_spent():
    with pytest.raises(ValueError, match='duplicate mock suppression'):
        run(observations=frame(observation(mock_suppressions=(h.MockSuppression('x', True),)*2)))
    result = run(observations=frame(observation(mock_suppressions=(h.MockSuppression('x', False),))))
    assert result.receipts[0].spending.decisions == ()
    assert result.receipts[0].requests[0].status == 'ineligible_mock'


def test_capital_explicit_bound_and_large_finite_balance_fail_atomically():
    opening = carry()
    with pytest.raises(ValueError, match='opening capital exceeds'):
        run(opening, config=policy(capital_limit=Fraction(1, 10)))
    with pytest.raises(ValueError, match='generated capital exceeds'):
        run(opening, config=policy(capital_limit=Fraction(3, 10), capital=replace(policy().capital, political_capital_base=.01)))
    assert opening == carry()
    result = run(opening, config=policy(capital_limit=Fraction(3, 10)))
    assert result.carry.civilizations[0].governance.exact_political_capital <= Fraction(3, 10)


def test_persistence_rejects_unknown_schema_duplicate_fields_and_corruption():
    payload = h.carry_to_json(carry())
    with pytest.raises(ValueError, match='duplicate JSON'):
        h.carry_from_json('{"schema":1,"schema":1,"carry":null}')
    with pytest.raises(ValueError, match='schema'):
        h.carry_from_json(payload.replace('"schema":1', '"schema":2'))
    with pytest.raises(ValueError, match='Fraction'):
        h.carry_from_json(payload.replace('"fraction":[3,10]', '"fraction":[3,0]'))
    with pytest.raises(ValueError, match='unknown/incomplete'):
        h.carry_from_json(payload.replace('"type":"HarnessCarry"', '"type":"WorldState"'))
    assert 'chronicler.governance_inputs' not in sys.modules


def test_committed_cursor_cannot_be_rewound_for_accession_or_changed_evidence():
    first = run(observations=frame(observation(ambition_snapshot=a.AmbitionSnapshot(
        '0', 'reign-0', 1, 10, .5, .3), events=(a.EvidenceEvent(1, 9, '0', 'build_started'),))))
    for event in (a.EvidenceEvent(1, 9, '0', 'infrastructure_completed'),
                  a.EvidenceEvent(1, 8, '0', 'invest_culture')):
        with pytest.raises(ValueError, match='replay below committed'):
            run(first.carry, frame(next_observation(first, events=(event,))))
    with pytest.raises(ValueError, match='accession cursor precedes'):
        run(first.carry, frame(observation(turn=2, ambition_snapshot=a.AmbitionSnapshot(
            '0', 'next', 2, 11, .5, .3), accession=c.SuccessionKind.PEACEFUL,
            accession_event_cursor=5, ambition_draws=(a.SelectionDraw(0., 0., 0.),)*2)))
    restored = h.carry_from_json(h.carry_to_json(first.carry))
    second = run(restored, frame(next_observation(first, events=(a.EvidenceEvent(1, 9, '0', 'build_started'),))))
    assert second.carry.civilizations[0].evidence_log == first.carry.civilizations[0].evidence_log


def test_example_is_usable_standalone_and_exact_after_restart():
    import runpy
    from pathlib import Path
    example = runpy.run_path(str(Path(__file__).resolve().parents[1] / 'examples/governance_four_kernel.py'))
    result = example['experiment']()
    assert result.carry.effective_turn == 2
    assert result.carry.civilizations[0].governance.exact_political_capital == 0
    assert len(result.carry.civilizations[0].contributions) == 1


@pytest.mark.parametrize('partner', ['Unknown display name', '01', '+1', '2'])
def test_trade_partners_must_be_canonical_registered_civ_ids(partner):
    opening = carry(initial(0), initial(1))
    obs = observation(ambition_snapshot=a.AmbitionSnapshot('0', 'reign-0', 1, 0, .5, .3,
        attainable_trade_partners=(partner,), trade_routes_exist=True))
    with pytest.raises(ValueError, match='canonical registered'):
        run(opening, frame(obs, observation(1)))


def test_registered_trade_target_and_persisted_objective_validation():
    obs = observation(ambition_snapshot=a.AmbitionSnapshot('0', 'new', 1, 0, .5, .3,
        attainable_trade_partners=('1',), trade_routes_exist=True), accession=c.SuccessionKind.PEACEFUL,
        accession_event_cursor=0, ambition_draws=(a.SelectionDraw(0., 0., 0.),)*2)
    p = policy(ambitions=replace(policy().ambitions, weights=((a.AmbitionType.ESTABLISH_TRADE, 1.),)))
    result = run(carry(initial(0), initial(1)), frame(obs, observation(1)), p)
    assert result.carry.civilizations[0].reign.ambitions[0].target == '1'
    payload = h.carry_to_json(result.carry)
    assert h.carry_from_json(payload) == result.carry
    with pytest.raises(ValueError, match='canonical registered'):
        h.carry_from_json(payload.replace('"target":"1"', '"target":"display name"'))


def test_persistence_cannot_drop_terminal_award_or_change_its_sign():
    result = run(completed_goal_opening(), frame(observation(ambition_snapshot=a.AmbitionSnapshot(
        '0', 'reign-0', 1, 0, .5, .3, owned_regions=('Border',)))))
    civ = result.carry.civilizations[0]
    with pytest.raises(ValueError, match='terminal objective/contribution ledger'):
        replace(civ, contributions=())
    with pytest.raises(ValueError, match='sign disagrees'):
        replace(civ, contributions=(replace(civ.contributions[0], delta=-.05),))


def test_acknowledgement_prefix_mismatch_rolls_back(monkeypatch):
    opening = carry(initial(balance=Fraction(1)))
    real = i.resolve_institutions
    def broken(**kwargs):
        result = real(**kwargs)
        if len(kwargs['spend_decisions'].decisions) > 1:
            return replace(result, used_spend_decisions=result.used_spend_decisions[1:])
        return result
    monkeypatch.setattr(i, 'resolve_institutions', broken)
    before = h.carry_to_json(opening)
    with pytest.raises(ValueError, match='displaced an accepted'):
        run(opening, frame(observation(factions=i.FactionWeights(.01, .01, .38, .6), proposals=(
            i.ProposalAttempt(i.InstitutionType.WRITTEN_LAW, 0.),
            i.ProposalAttempt(i.InstitutionType.TEMPLE_TITHE, 0.)))))
    assert h.carry_to_json(opening) == before


def test_exact_budget_sweep_and_successive_reload_ledgers():
    for numerator in range(51):
        balance = Fraction(numerator, 100)
        result = run(carry(initial(balance=balance)), frame(observation(
            proposals=(i.ProposalAttempt(i.InstitutionType.CONSCRIPTION, 0.),),
            mock_suppressions=(h.MockSuppression('b', True), h.MockSuppression('a', True)))))
        receipt = result.receipts[0]
        costs = sum((Fraction(str(d.cost)) for d in receipt.spending.decisions if d.approved), Fraction())
        assert receipt.spending.state.exact_political_capital == balance - costs >= 0
        current = result
        for _ in range(3):
            current = run(h.carry_from_json(h.carry_to_json(current.carry)), frame(next_observation(current)))
            assert current.carry.civilizations[0].governance.exact_political_capital == balance - costs


def test_accession_accrues_once_from_explicit_reset_pool():
    obs = observation(ambition_snapshot=a.AmbitionSnapshot('0', 'new', 1, 0, .5, .3),
        accession=c.SuccessionKind.PEACEFUL, accession_event_cursor=0,
        ambition_draws=(a.SelectionDraw(0., 0., 0.),)*2)
    result = run(observations=frame(obs), config=policy(capital_on_accession='reset_zero',
        capital=replace(policy().capital, political_capital_base=.1, legitimacy_to_capital_rate=.1)))
    assert result.receipts[0].accrual.exact_opening_political_capital == 0
    assert result.receipts[0].accrual.exact_generated_capital == Fraction(16, 100)
    assert result.carry.civilizations[0].governance.exact_political_capital == Fraction(16, 100)


def test_carry_rejects_ratchet_epoch_and_future_reign_state():
    with pytest.raises(ValueError, match='carry epochs'):
        replace(initial(), ratchet=e.EliteRatchetState(-1, 0.))
    with pytest.raises(ValueError, match='reign identity/epoch'):
        replace(initial(), reign=replace(initial().reign, last_evaluated_turn=2))


def test_persistence_cannot_drop_unevaluated_accession_evidence():
    snapshot = a.AmbitionSnapshot('0', 'new', 1, 12, .5, .3, arts_available=True)
    obs = observation(ambition_snapshot=snapshot, accession=c.SuccessionKind.PEACEFUL,
        ambition_draws=(a.SelectionDraw(0., 0., 0.),)*2, accession_event_cursor=10,
        events=(a.EvidenceEvent(1, 11, '0', 'invest_culture'),))
    result = run(observations=frame(obs))
    data = json.loads(h.carry_to_json(result.carry))
    data['carry']['fields']['civilizations']['tuple'][0]['fields']['pending_events'] = {'tuple': []}
    with pytest.raises(ValueError, match='unevaluated durable log'):
        h.carry_from_json(json.dumps(data))
    valid = h.carry_from_json(h.carry_to_json(result.carry))
    next_result = run(valid, frame(next_observation(result)))
    assert len(next_result.receipts[0].ambition_outcomes) == 1
