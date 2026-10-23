"""Read-only measurement of the existing four-kernel governance outputs.

Every expectation here is derived from public fields of the reviewed kernels and
harness, or hand-calculated from the reviewed fixture policy. These are synthetic
fixture measurements: nothing here calibrates, qualifies or accepts M67, and no
test claims production extraction, PSI or scale validation.
"""
from dataclasses import FrozenInstanceError, replace
from fractions import Fraction
from itertools import permutations
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import random
import re
import subprocess
import sys
from types import SimpleNamespace

import pytest

from chronicler import elite_metrics as e
from chronicler import governance_capital as c
from chronicler import governance_kernel_harness as h
from chronicler import governance_measurements as gm
from chronicler import institutions as i
from chronicler import ruler_ambitions as a

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "governance_measurement_report.py"
DOC_PATH = REPO_ROOT / "docs" / "governance" / "m67-readiness.md"
IDENTITY = gm.SourceIdentity(revision="1" * 40, tree="2" * 40, label="fixture source identity")
ORIGIN = gm.MeasurementOrigin.SYNTHETIC_FOUR_KERNEL_HARNESS
# The reviewed fixture policy, byte-identical to the one in the harness tests.
COSTS = c.SpendCosts(.10, .20, .15)


def policy(**changes):
    rules = tuple(i.InstitutionRule(t, i.Faction.MERCHANT if i.alignment(t) != i.Faction.MERCHANT
                                   else i.Faction.MILITARY, 2.) for t in i.InstitutionType)
    base = h.HarnessPolicy(h.POLICY_ID,
        i.InstitutionCoefficients(1., .1, .02, rules),
        e.EliteCalibration(.1, .1, 2.),
        e.EliteConventions(e.WealthPercentileConvention.LOWER, e.PositionRounding.FLOOR,
                           e.EqualWealthOrder.AGENTS_FIRST),
        c.CapitalCoefficients(.5, 0., 0., .05, .1, .1, 0., .1, .2),
        COSTS,
        a.AmbitionCalibration(2, 20, 40, .1, .05,
                              ((a.AmbitionType.CONQUER_REGION, 1.),
                               (a.AmbitionType.PATRON_OF_ARTS, 1.))),
        i.FundingPolicy.BASE_FIRST_FULL_DEBIT,
        'fractional_fixture_no_integer_treasury', 'persisted_enactment_cost',
        'reign_long_no_decay', 'defer_new_objectives', 'carry_remaining',
        'synthetic_living_row_count', 'abort_frame', Fraction(10), 'monotone_complete_cursor_log')
    return replace(base, **changes)


def initial(civ=0, balance=Fraction(3, 10), *, turn=1, institutions=(), reign=None):
    if reign is None:
        reign = a.RulerAmbitions(str(civ), f'reign-{civ}', 0, 0, ())
    return h.CivCarry(civ, i.InstitutionSnapshot(turn, institutions),
                      e.EliteRatchetState(turn - 1, 0.),
                      c.GovernanceState(turn, .5, float(balance), balance), reign)


def carry(*civs):
    civs = civs or (initial(),)
    turn = civs[0].governance.effective_turn
    return h.HarnessCarry(turn, turn - 1, tuple(c.civ_id for c in civs), tuple(civs))


def observation(civ=0, turn=1, **changes):
    base = h.CivObservation(civ, i.FactionWeights(.6, .1, .2, .1), 100., 0., 4, 3, (), (),
        a.AmbitionSnapshot(str(civ), f'reign-{civ}', turn, 0, .5, .3), c.LegitimacyInputs(),
        (), None, (), None)
    return replace(base, **changes)


def frame(*observations, agents=(), great_persons=()):
    if not observations:
        observations = (observation(),)
    turn = observations[0].ambition_snapshot.turn
    return h.SyntheticFrame(turn, turn, 'explicit_synthetic_fixture', tuple(observations),
                            tuple(agents), tuple(great_persons))


def run(opening=None, observations=None, config=None):
    return h.run_kernel_frame(enabled=True, opening=opening or carry(),
                              observations=observations or frame(), policy=config or policy())


def measure(opening, result, *, origin=ORIGIN, source_identity=IDENTITY):
    return gm.measure_governance_result(opening=opening, result=result, origin=origin,
                                        source_identity=source_identity)


def enact_and_suppress(**changes):
    """One enactment plus one eligible mock suppression from one 0.30 wallet."""
    return observation(proposals=(i.ProposalAttempt(i.InstitutionType.CONSCRIPTION, 0.),),
                       mock_suppressions=(h.MockSuppression('synthetic-suppression-1', True),),
                       **changes)


def load_script():
    spec = importlib.util.spec_from_file_location("governance_measurement_report_under_test",
                                                  SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_script(*args, hash_seed="0"):
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT / "src")
    env["PYTHONHASHSEED"] = hash_seed
    return subprocess.run([sys.executable, str(SCRIPT_PATH), *args],
                          capture_output=True, text=True, cwd=str(REPO_ROOT), env=env)


def roadmap_lines():
    return (REPO_ROOT / gm.ROADMAP_PATH).read_text(encoding="utf-8").splitlines()


# --------------------------------------------------------------------------- #
# Report contents versus exact public fields and a hand-calculated wallet.
# --------------------------------------------------------------------------- #

def test_report_matches_exact_public_fields_and_hand_calculated_wallet():
    opening = carry()
    result = run(opening, frame(enact_and_suppress()))
    receipt = result.receipts[0]
    published = result.carry.civilizations[0]
    civ = measure(opening, result).civilization(0)

    # Hand-calculated: a 3/10 wallet funds enact .10 then suppress .20, exactly.
    assert civ.opening_capital.exact_balance.as_fraction() == Fraction(3, 10)
    assert civ.spend_total.as_fraction() == Fraction(3, 10)
    assert civ.capital_after_spend.as_fraction() == Fraction(0)
    assert [(s.action, s.approved, s.exact_capital_before.as_fraction(),
             s.exact_capital_after.as_fraction()) for s in civ.spending] == [
        (c.GovernanceAction.ENACT_INSTITUTION, True, Fraction(3, 10), Fraction(1, 5)),
        (c.GovernanceAction.SUPPRESS_SECESSION, True, Fraction(1, 5), Fraction(0)),
    ]
    assert [d.request.action for d in receipt.spending.decisions] == [s.action
                                                                     for s in civ.spending]
    assert [d.cost for d in receipt.spending.decisions] == [.10, .20]
    assert civ.published_capital.exact_balance == gm.ExactFraction.of(
        published.governance.exact_political_capital)
    assert civ.published_capital.ruler_legitimacy == receipt.accrual.state.ruler_legitimacy == .5

    # One CONSCRIPTION enacted this turn: coefficient 2. x region_count 4 = 8.0.
    assert civ.opening_institution_count == 0
    assert civ.institutions[0].institution_type is i.InstitutionType.CONSCRIPTION
    assert civ.institutions[0].legitimacy == 1.0
    assert civ.institutions[0].enforcement_cost == 8.0
    assert civ.institutions[0].faction_alignment is i.Faction.MILITARY
    assert civ.institutions[0].opposing_faction is i.Faction.MERCHANT
    assert civ.funding.effective_turn == 1
    assert civ.funding.policy is i.FundingPolicy.BASE_FIRST_FULL_DEBIT
    assert civ.funding.treasury_before == 100.0 and civ.funding.treasury_after == 100.0
    assert civ.funding.enforcement_demand == 0.0 and civ.funding.funding_ratio == 1.0
    assert civ.used_spend_operations == 1
    assert len(civ.events) == 1 and civ.events[0].event_type == 'institution_enacted'
    assert [o.status for o in civ.proposal_outcomes] == [i.ProposalStatus.ENACTED]
    assert civ.repeal_outcomes == ()
    assert [r.status for r in civ.requests] == ['acknowledged', 'acknowledged_mock']
    assert civ.reign.objective_count == 0 and civ.reign.evidence_cursor == 0
    assert civ.ambition_outcomes == () and civ.retained_contributions == ()
    assert civ.accrual.accession_pool_applied is False
    assert civ.accrual.generated_capital.as_fraction() == 0
    assert dict(civ.accrual.legitimacy_sources)['base'] == .5
    assert sum(value for _, value in civ.accrual.legitimacy_sources) == pytest.approx(.5)

    measured = measure(opening, result)
    assert measured.metric('institution_count').value == 1
    assert measured.metric('enact_count').value == 1
    assert measured.metric('repeal_count').value == 0
    assert measured.metric('political_capital_max').value.as_fraction() == Fraction(0)


def test_elite_counts_and_identities_come_from_the_public_g02_records():
    agents = tuple(e.AgentEliteInput(k, 0, 10., e.Occupation.SCHOLAR, .9, .1)
                   for k in range(3))
    opening = carry()
    result = run(opening, frame(observation(), agents=agents))
    published = result.elite_metrics.civilizations[0]
    measured = measure(opening, result)
    civ = measured.civilization(0)
    assert civ.elite.elite_positions == published.elite_positions == 2
    assert civ.elite.qualifier_count == published.elite_qualifier_count == 3
    assert civ.elite.office_holder_count == published.elite_office_holder_count == 2
    assert civ.elite.frustrated_aspirant_count == published.frustrated_aspirant_count == 1
    assert civ.elite.conspicuous_consumption_index == 0.0
    assert civ.elite.emp == published.emp == 0.0
    assert [x.agent_id for x in civ.elite.qualifiers] == [q.agent_id for q in published.qualifiers]
    assert [x.agent_id for x in civ.elite.office_holders] == [q.agent_id
                                                             for q in published.office_holders]
    assert [x.agent_id for x in civ.elite.frustrated_aspirants] == [
        q.agent_id for q in published.frustrated_aspirants]
    assert measured.metric('emp').value == (0.0,)
    assert measured.metric('elite_qualifier_count').value == (3,)
    assert measured.metric('elite_office_holder_count').value == (2,)
    assert measured.metric('frustrated_aspirant_count').value == (1,)
    assert measured.metric('elite_positions').value == (2,)


def test_ambition_outcome_and_retained_contribution_are_measured_from_public_fields():
    goal = a.Ambition(a.AmbitionType.CONQUER_REGION, 'Border', 0, 20, 0)
    opening = carry(initial(reign=a.RulerAmbitions('0', 'reign-0', 0, 0, (goal,))))
    snapshot = a.AmbitionSnapshot('0', 'reign-0', 1, 0, .5, .3, owned_regions=('Border',))
    result = run(opening, frame(observation(ambition_snapshot=snapshot)))
    outcome = result.receipts[0].ambition_outcomes[0]
    retained = result.carry.civilizations[0].contributions[0]
    civ = measure(opening, result).civilization(0)

    assert len(civ.ambition_outcomes) == 1
    measured_outcome = civ.ambition_outcomes[0]
    assert measured_outcome.ambition_type is outcome.ambition_type
    assert measured_outcome.ambition_type is a.AmbitionType.CONQUER_REGION
    assert measured_outcome.legitimacy_delta == outcome.legitimacy_delta == .1
    assert measured_outcome.event_type == outcome.event_type == 'ambition_fulfilled'
    assert measured_outcome.tag == outcome.tag == 'ambition_completed_conquer_region'
    assert measured_outcome.outcome_turn == outcome.turn == 1
    assert measured_outcome.target == outcome.target == 'Border'
    assert measured_outcome.contribution_id == h.contribution_id(outcome.contribution_key)
    assert len(civ.retained_contributions) == 1
    assert civ.retained_contributions[0].delta == retained.delta == .1
    assert civ.retained_contributions[0].contribution_id == h.contribution_id(retained.key)
    assert civ.retained_contributions[0].ambition_type is retained.key.ambition_type
    assert civ.reign.objective_count == 1 and civ.reign.completed_objectives == 1
    assert civ.reign.failed_objectives == 0
    assert 'ambition_completed_conquer_region' in civ.reign.event_tags
    assert dict(civ.accrual.legitimacy_sources)['ambitions'] == .1
    assert civ.accrual.ruler_legitimacy == .6


# --------------------------------------------------------------------------- #
# Absent output is unavailable with a reason, never a numeric zero.
# --------------------------------------------------------------------------- #

UNAVAILABLE_KEYS = ('psi', 'mmp', 'sfd', 'psi_subindex_cooccurrence',
                    'commons_overshoot_marker', 'commons_collapse_marker',
                    'institutional_effect_modifiers', 'institutional_regime_classification',
                    'secular_cycle_recovery', 'crisis_predictiveness',
                    'transient_reset_matrix', 'production_treasury_commits',
                    'scale_qualification', 'institution_tenure', 'enact_rate', 'repeal_rate',
                    'legitimacy_distribution', 'political_capital_distribution',
                    'legitimacy_action_success_by_quartile', 'degenerate_condition_guards')


def test_absent_output_is_unavailable_with_a_reason_and_never_a_numeric_zero():
    opening = carry()
    measured = measure(opening, run(opening, frame(observation())))
    for key in UNAVAILABLE_KEYS:
        metric = measured.metric(key)
        assert metric.status is gm.MeasurementStatus.UNAVAILABLE
        assert metric.value is None
        assert metric.reason and isinstance(metric.reason, str)
    assert measured.metric('psi').reason.startswith('no M65b PSI producer exists')
    assert 'two-turn synthetic frame' in measured.metric('secular_cycle_recovery').reason
    assert 'no M64 commons kernel' in measured.metric('commons_overshoot_marker').reason
    assert 'M61b' in measured.metric('scale_qualification').reason

    # A true measured zero stays available and carries a value.
    for key, value in (('institution_count', 0), ('enact_count', 0), ('repeal_count', 0),
                       ('elite_qualifier_count', (0,)), ('emp', (0.0,))):
        metric = measured.metric(key)
        assert metric.status is gm.MeasurementStatus.AVAILABLE
        assert metric.value == value
        assert metric.reason is None

    payload = json.loads(gm.measurement_json(measured))
    by_key = {entry["key"]: entry for entry in payload["metrics"]}
    for key in UNAVAILABLE_KEYS:
        assert by_key[key]["status"] == "unavailable"
        assert by_key[key]["value"] is None
        assert by_key[key]["reason"]
    assert by_key["repeal_count"]["status"] == "available"
    assert by_key["repeal_count"]["value"] == 0

    report = gm.render_report(measured)
    assert "[unavailable] psi = no M65b PSI producer exists" in report
    assert "[available]   repeal_count = 0" in report
    assert "  [available]   institution_count = 0" in report
    # No "[unavailable] psi = 0" style substitution anywhere.
    assert not [line for line in report.splitlines()
                if line.startswith("  [unavailable]") and line.endswith("= 0")]


def test_metric_presence_invariant_is_structural():
    with pytest.raises(ValueError, match='available but carries no value'):
        gm.Metric('k', 'l', ':1', 'in', 'N', gm.MeasurementStatus.AVAILABLE, None, 'why')
    with pytest.raises(ValueError, match='available but carries a reason'):
        gm.Metric('k', 'l', ':1', 'in', 'N', gm.MeasurementStatus.AVAILABLE, 0, 'why')
    with pytest.raises(ValueError, match='unavailable but carries a value'):
        gm.Metric('k', 'l', ':1', 'in', 'N', gm.MeasurementStatus.UNAVAILABLE, 0, 'why')
    with pytest.raises(ValueError, match='reason'):
        gm.Metric('k', 'l', ':1', 'in', 'N', gm.MeasurementStatus.UNAVAILABLE, None, ' ')


def test_exact_fraction_is_canonical_and_never_a_float():
    with pytest.raises(ValueError, match='canonical reduced form'):
        gm.ExactFraction(2, 4)
    with pytest.raises(ValueError, match='positive integer'):
        gm.ExactFraction(1, 0)
    with pytest.raises(ValueError, match='must be a Fraction'):
        gm.ExactFraction.of(0.1)
    exact = gm.ExactFraction.of(Fraction(3, 10))
    assert (exact.numerator, exact.denominator) == (3, 10)
    assert str(exact) == '3/10'
    assert str(gm.ExactFraction.of(Fraction(-3, 10))) == '-3/10'
    assert str(gm.ExactFraction.of(Fraction(0))) == '0'


# --------------------------------------------------------------------------- #
# Epoch discipline: N spends, N+1 publishes.
# --------------------------------------------------------------------------- #

def test_source_turn_spends_and_n_plus_one_effects_are_never_backdated():
    opening = carry()
    result = run(opening, frame(observation(
        proposals=(i.ProposalAttempt(i.InstitutionType.CONSCRIPTION, 0.),))))
    measured = measure(opening, result)
    civ = measured.civilization(0)
    assert (measured.source_turn, measured.effective_turn) == (1, 2)
    assert measured.opening_last_committed_turn == 0
    assert civ.opening_capital.effective_turn == 1
    assert [spend.effective_turn for spend in civ.spending] == [1]
    assert civ.funding.effective_turn == 1
    assert civ.accrual.effective_turn == 2
    assert civ.published_capital.effective_turn == 2
    assert (civ.elite.snapshot_turn, civ.elite.effective_turn) == (1, 2)
    assert [(event.turn, event.effective_turn) for event in civ.events] == [(1, 2)]
    assert [(ins.enacted_turn, ins.effective_turn) for ins in civ.institutions] == [(1, 2)]
    assert civ.institutions[0].enacted_turn < civ.institutions[0].effective_turn


def test_same_turn_generated_credit_is_measured_as_n_plus_one_only():
    opening = carry(initial(balance=Fraction(0)))
    result = run(opening, frame(observation(mock_suppressions=(h.MockSuppression('x', True),))),
                 policy(capital=replace(policy().capital, political_capital_base=.3)))
    civ = measure(opening, result).civilization(0)
    assert civ.capital_after_spend.as_fraction() == 0
    assert civ.spending[0].approved is False
    assert civ.accrual.opening_capital.as_fraction() == 0
    assert civ.accrual.generated_capital.as_fraction() == Fraction(3, 10)
    assert civ.accrual.effective_turn == 2
    assert civ.published_capital.exact_balance.as_fraction() == Fraction(3, 10)


def test_enforcement_demand_arrives_on_the_following_turn_and_persists():
    first = run(carry(), frame(observation(
        proposals=(i.ProposalAttempt(i.InstitutionType.CONSCRIPTION, 0.),))))
    assert measure(carry(), first).civilization(0).funding.enforcement_demand == 0.0
    second = run(first.carry, frame(next_observation(first)))
    civ = measure(first.carry, second).civilization(0)
    assert civ.funding.enforcement_demand == 8.0
    assert civ.funding.treasury_after == 92.0
    assert civ.funding.funding_ratio == 1.0
    assert civ.institutions[0].enacted_turn == 1
    assert civ.institutions[0].effective_turn == 3
    assert civ.accrual.effective_turn == 3


def next_observation(result, **changes):
    civ = result.carry.civilizations[0]
    return observation(turn=result.carry.effective_turn,
                       ambition_snapshot=a.AmbitionSnapshot('0', civ.reign.ruler_id,
                                                            result.carry.effective_turn,
                                                            civ.evidence_cursor, .5, .3),
                       **changes)


@pytest.mark.parametrize('transfer, expected, applied', [
    ('reset_zero', Fraction(0), True),
    ('carry_remaining', Fraction(3, 10), False),
])
def test_accession_capital_pool_is_recorded_rather_than_hidden(transfer, expected, applied):
    opening = carry()
    obs = observation(accession=c.SuccessionKind.PEACEFUL,
                      ambition_draws=(a.SelectionDraw(0., 0., 0.),) * 2,
                      accession_event_cursor=0,
                      ambition_snapshot=a.AmbitionSnapshot('0', 'new-reign', 1, 0, .5, .3))
    result = run(opening, frame(obs),
                 policy(capital_on_accession=transfer,
                        capital=replace(policy().capital, political_capital_base=.1,
                                        legitimacy_to_capital_rate=.1)))
    civ = measure(opening, result).civilization(0)
    assert civ.capital_after_spend.as_fraction() == Fraction(3, 10)
    assert civ.accrual.opening_capital.as_fraction() == expected
    assert civ.accrual.accession_pool_applied is applied
    assert civ.accrual.generated_capital.as_fraction() == Fraction(16, 100)
    assert civ.published_capital.exact_balance.as_fraction() == expected + Fraction(16, 100)
    assert civ.accrual.ruler_legitimacy == .6
    assert dict(civ.accrual.legitimacy_sources)['succession'] == .1
    assert tuple(name for name, _ in civ.accrual.legitimacy_sources) == gm.LEGITIMACY_SOURCE_ORDER
    assert civ.reign.event_tags == ('new_ruler',)
    assert civ.ambition_outcomes == () and civ.retained_contributions == ()


# --------------------------------------------------------------------------- #
# Determinism of ordering and of exact encoding.
# --------------------------------------------------------------------------- #

def test_civilization_and_enum_ordering_is_stable_under_input_permutation():
    agents = tuple(e.AgentEliteInput(k, k % 2, 10., e.Occupation.SCHOLAR, .9, .1)
                   for k in range(6))
    factions = i.FactionWeights(.01, .01, .38, .6)
    obs0 = observation(0, factions=factions, proposals=(
        i.ProposalAttempt(i.InstitutionType.TEMPLE_TITHE, 0.),
        i.ProposalAttempt(i.InstitutionType.WRITTEN_LAW, 0.)),
        mock_suppressions=(h.MockSuppression('z', True), h.MockSuppression('a', True)))
    obs1 = observation(1)

    def build(civs, observations, rows):
        opening = carry(*civs)
        return measure(opening, run(opening, frame(*observations, agents=rows)))

    expected = build((initial(0), initial(1)), (obs0, obs1), agents)
    baseline = gm.measurement_json(expected)
    baseline_text = gm.render_report(expected)
    for civs in permutations((initial(0), initial(1))):
        for observations in permutations((obs0, obs1)):
            shuffled = tuple(replace(o, proposals=tuple(reversed(o.proposals)),
                                     mock_suppressions=tuple(reversed(o.mock_suppressions)))
                             for o in observations)
            rebuilt = build(civs, shuffled, tuple(reversed(agents)))
            assert gm.measurement_json(rebuilt) == baseline
            assert gm.render_report(rebuilt) == baseline_text
    assert [civ.civ_id for civ in expected.civilizations] == [0, 1]
    assert tuple(civ.civ_id for civ in expected.civilizations) == expected.identity_registry

    # Two enactments fit the 0.30 wallet exactly; neither 0.20 mock can.
    civ0 = expected.civilization(0)
    order = tuple(i.InstitutionType)
    assert [ins.institution_type for ins in civ0.institutions] == [
        i.InstitutionType.WRITTEN_LAW, i.InstitutionType.TEMPLE_TITHE]
    assert [ins.institution_type for ins in civ0.institutions] == sorted(
        (ins.institution_type for ins in civ0.institutions), key=order.index)
    assert civ0.spend_total.as_fraction() == Fraction(1, 5)
    assert civ0.capital_after_spend.as_fraction() == Fraction(1, 10)
    assert [(spend.action, spend.approved) for spend in civ0.spending] == [
        (c.GovernanceAction.ENACT_INSTITUTION, True),
        (c.GovernanceAction.ENACT_INSTITUTION, True),
        (c.GovernanceAction.SUPPRESS_SECESSION, False),
        (c.GovernanceAction.SUPPRESS_SECESSION, False)]
    assert [request.status for request in civ0.requests] == [
        'acknowledged', 'acknowledged', 'insufficient_capital', 'insufficient_capital']
    assert json.loads(civ0.requests[0].request_id)[-1] == 'written_law'
    assert json.loads(civ0.requests[2].request_id)[-1] == 'a'
    assert json.loads(civ0.requests[3].request_id)[-1] == 'z'
    assert expected.metric('institution_count').value == 2
    assert expected.metric('emp').value == (0.0, 0.0)
    assert expected.metric('elite_qualifier_count').value == (3, 3)
    assert gm.render_report(expected) == gm.render_report(expected)


def test_exact_fractions_survive_report_and_json_encoding():
    balance = Fraction(1, 10) - Fraction(1, 10 ** 40)
    opening = carry(initial(balance=balance))
    result = run(opening, frame(observation(
        proposals=(i.ProposalAttempt(i.InstitutionType.CONSCRIPTION, 0.),))))
    measured = measure(opening, result)
    civ = measured.civilization(0)
    # The residual is invisible in the float view but exact everywhere else.
    assert float(balance) == .1
    assert civ.opening_capital.float_view == .1
    assert civ.opening_capital.exact_balance.as_fraction() == balance
    assert civ.spending[0].approved is False
    assert civ.capital_after_spend.as_fraction() == balance
    assert civ.accrual.closing_capital.as_fraction() == balance
    assert civ.published_capital.exact_balance.as_fraction() == balance

    payload = json.loads(gm.measurement_json(measured))
    civ_json = payload["civilizations"][0]
    pair = [balance.numerator, balance.denominator]
    assert civ_json["capital_after_spend"] == {"fraction": pair}
    assert civ_json["published_capital"]["exact_balance"] == {"fraction": pair}
    assert civ_json["opening_capital"]["exact_balance"] == {"fraction": pair}
    assert civ_json["accrual"]["generated_capital"] == {"fraction": [0, 1]}
    assert Fraction(*civ_json["capital_after_spend"]["fraction"]) == balance
    report = gm.render_report(measured)
    assert f"capital_after_spend={balance.numerator}/{balance.denominator}" in report
    assert str(balance) in report


# --------------------------------------------------------------------------- #
# Rejection of malformed, mismatched, duplicate and disabled inputs.
# --------------------------------------------------------------------------- #

def test_disabled_result_is_refused_instead_of_measured_as_empty():
    opening = carry()
    disabled = h.run_kernel_frame(opening=opening)
    assert disabled.policy_id is None
    assert disabled.receipts == () and disabled.elite_metrics is None
    with pytest.raises(ValueError, match='disabled'):
        measure(opening, disabled)


def test_mismatched_duplicate_and_misaligned_results_are_rejected_without_mutation():
    opening = carry()
    opening_before = h.carry_to_json(opening)
    result = run(opening, frame(observation(
        proposals=(i.ProposalAttempt(i.InstitutionType.CONSCRIPTION, 0.),))))
    result_before = h.carry_to_json(result.carry)

    with pytest.raises(ValueError, match='receipts must cover'):
        measure(opening, replace(result, receipts=()))
    with pytest.raises(ValueError, match='duplicate civilization receipt'):
        measure(opening, replace(result, receipts=result.receipts * 2))
    with pytest.raises(ValueError, match='receipts must cover'):
        measure(opening, replace(result, receipts=(replace(result.receipts[0], civ_id=7),)))
    with pytest.raises(ValueError, match='identity registry does not match'):
        measure(opening, replace(result, carry=h.HarnessCarry(
            2, 1, (0, 1), (initial(0, turn=2), initial(1, turn=2)))))
    with pytest.raises(ValueError, match='not produced from this opening carry epoch'):
        measure(carry(initial(turn=2)), result)
    with pytest.raises(ValueError, match='elite metrics epochs'):
        measure(opening, replace(result, elite_metrics=replace(result.elite_metrics,
                                                                effective_turn=9)))
    with pytest.raises(ValueError, match='not a HarnessCarry|opening must be'):
        measure(object(), result)
    with pytest.raises(ValueError, match='result must be a HarnessResult'):
        measure(opening, object())
    with pytest.raises(ValueError, match='origin'):
        measure(opening, result, origin='production')
    with pytest.raises(ValueError, match='source_identity'):
        measure(opening, result, source_identity=('1' * 40, '2' * 40, 'x'))
    with pytest.raises(ValueError, match='unreviewed harness policy id'):
        measure(opening, replace(result, policy_id='some-other-policy'))
    for bad in ('0' * 39, 'Z' * 40, '1' * 41, 123):
        with pytest.raises(ValueError, match='40 character lowercase hex'):
            gm.SourceIdentity(revision=bad, tree='2' * 40, label='x')
    with pytest.raises(ValueError, match='nonempty string'):
        gm.SourceIdentity(revision='1' * 40, tree='2' * 40, label='  ')

    # A tampered ledger fails instead of publishing a wrong measurement.
    decisions = result.receipts[0].spending.decisions
    assert decisions
    forged = (replace(decisions[0], exact_capital_after=Fraction(1, 4)),) + decisions[1:]
    broken = replace(result.receipts[0], spending=replace(result.receipts[0].spending,
                                                           decisions=forged))
    with pytest.raises(ValueError, match='did not debit its exact cost'):
        measure(opening, replace(result, receipts=(broken,)))
    shifted = replace(result.receipts[0],
                      spending=replace(result.receipts[0].spending,
                                       state=c.GovernanceState(1, .5, .25, Fraction(1, 4))))
    with pytest.raises(ValueError, match='disagrees with its own ledger'):
        measure(opening, replace(result, receipts=(shifted,)))
    deny_charge = replace(decisions[0], approved=False, exact_capital_after=Fraction(1, 4))
    denied = replace(result.receipts[0], spending=replace(result.receipts[0].spending,
                                                          decisions=(deny_charge,)))
    with pytest.raises(ValueError, match='denied spend consumed political capital'):
        measure(opening, replace(result, receipts=(denied,)))

    assert h.carry_to_json(opening) == opening_before
    assert h.carry_to_json(result.carry) == result_before


def test_empty_registry_reports_absent_rather_than_zero():
    opening = h.HarnessCarry(0, -1, (), ())
    result = h.run_kernel_frame(enabled=True, opening=opening,
                                observations=h.SyntheticFrame(0, 0,
                                                              'explicit_synthetic_fixture',
                                                              (), (), ()),
                                policy=policy())
    measured = measure(opening, result)
    assert measured.civilizations == ()
    assert measured.identity_registry == ()
    assert measured.source_turn == 0 and measured.effective_turn == 1
    for key in ('institution_count', 'enact_count', 'repeal_count', 'legitimacy_min',
                'elite_positions', 'emp'):
        assert measured.metric(key).status is gm.MeasurementStatus.UNAVAILABLE
        assert measured.metric(key).reason == gm.NO_CIVILIZATIONS
    assert {metric.key for metric in measured.unavailable} >= set(UNAVAILABLE_KEYS)
    with pytest.raises(KeyError):
        measured.civilization(0)
    with pytest.raises(KeyError):
        measured.metric('no_such_metric')


def test_measurement_is_immutable_and_leaves_both_arguments_untouched():
    opening = carry()
    result = run(opening, frame(enact_and_suppress()))
    opening_before, result_before = h.carry_to_json(opening), h.carry_to_json(result.carry)
    identities = (id(opening), id(result.carry))
    measured = measure(opening, result)
    gm.render_report(measured)
    gm.measurement_json(measured)
    assert h.carry_to_json(opening) == opening_before
    assert h.carry_to_json(result.carry) == result_before
    assert (id(opening), id(result.carry)) == identities
    assert measured is not measure(opening, result)
    assert gm.measurement_json(measure(opening, result)) == gm.measurement_json(measured)
    with pytest.raises(FrozenInstanceError):
        measured.source_turn = 5
    with pytest.raises(FrozenInstanceError):
        measured.civilizations = ()
    with pytest.raises(FrozenInstanceError):
        measured.civilization(0).institutions = ()
    civ = measured.civilization(0)
    assert isinstance(measured.civilizations, tuple)
    assert isinstance(measured.metrics, tuple)
    assert isinstance(measured.diagnostics, tuple)
    assert isinstance(civ.institutions, tuple) and isinstance(civ.spending, tuple)
    assert isinstance(civ.accrual.legitimacy_sources, tuple)


def test_extraction_invokes_no_kernel_no_draw_and_no_rng(monkeypatch):
    opening = carry()
    result = run(opening, frame(enact_and_suppress()))

    def blocked(*args, **kwargs):
        raise AssertionError('measurement invoked a kernel')

    for module, name in ((h, 'run_kernel_frame'), (i, 'resolve_institutions'),
                         (i, 'fund_institutions'), (i, 'proposal_candidates'),
                         (e, 'compute_elite_metrics'), (c, 'resolve_spending'),
                         (c, 'accrue_capital'), (c, 'compute_legitimacy'),
                         (a, 'start_reign'), (a, 'evaluate_ambitions'),
                         (a, 'generate_ambitions'), (h, 'carry_to_json')):
        monkeypatch.setattr(module, name, blocked)
    before = random.getstate()
    measured = measure(opening, result)
    assert random.getstate() == before
    assert measured.metric('institution_count').value == 1
    assert measured.civilization(0).capital_after_spend.as_fraction() == 0
    assert gm.render_report(measured).startswith(f"REPORT {gm.REPORT_KIND}")


# --------------------------------------------------------------------------- #
# Regime classifier preregistration and source-backed obligations.
# --------------------------------------------------------------------------- #

def test_classifier_definitions_are_recorded_and_never_implemented():
    assert [item.label for item in gm.REGIME_CLASSIFIER_REQUIREMENTS] == [
        'frozen_stable', 'highly_fluctuating', 'complex_cycling']
    definitions = {item.label: item.roadmap_definition
                   for item in gm.REGIME_CLASSIFIER_REQUIREMENTS}
    assert definitions['frozen_stable'] == (
        "<= 1 institution change per 100 turns and mean active count >= 1.")
    assert definitions['highly_fluctuating'] == (
        "mean institution tenure < 10 turns with repeated enact / repeal churn.")
    assert 'at least 2 distinct institutional configurations' in definitions['complex_cycling']
    for item in gm.REGIME_CLASSIFIER_REQUIREMENTS:
        assert item.implemented is False
        assert item.required_measurements
        assert any('window' in text for text in item.unresolved_conventions)
        assert any('censoring' in text for text in item.unresolved_conventions)
        assert any('overlap' in text or 'labels' in text
                   for text in item.unresolved_conventions)
    with pytest.raises(ValueError, match='no regime classifier'):
        gm.RegimeClassifierRequirement('x', 'y', ('a',), ('b',), True)
    measured = measure(carry(), run(carry(), frame(observation())))
    assert measured.regime_classifier_requirements == gm.REGIME_CLASSIFIER_REQUIREMENTS
    report = gm.render_report(measured)
    assert 'REGIME CLASSIFIER PREREGISTRATION (definitions only, not implemented)' in report
    assert report.count('implemented: false') == 3
    assert 'unresolved conventions (recorded here, not decided here)' in report


def test_classifier_and_measurement_definitions_come_from_the_roadmap_source():
    roadmap = roadmap_lines()

    def at(number):
        assert 1 <= number <= len(roadmap)
        return roadmap[number - 1]

    assert 'M67' in at(859)
    assert 'GATE MILESTONE' in at(863)
    assert 'extract_governance_metrics()' in at(878)
    assert 'Ship measurement first' in at(877)
    assert 'Frozen / stable' in at(880) and 'per 100 turns' in at(880)
    assert 'Highly fluctuating' in at(881) and 'tenure < 10 turns' in at(881)
    assert 'Complex cycling' in at(882) and 'distinct institutional configurations' in at(882)
    assert 'Transient-reset matrix' in at(883)
    assert '>= 65% of those seeds' in at(888)
    assert '>= 60% show recovery' in at(893)
    assert '>= 10% of tested runs' in at(898)
    assert '>= 70% of seeds' in at(904)
    assert 'after M67 passes' in at(1268)
    for line in ('1272', '1274', '1276'):
        assert 'M67' in at(int(line))
    for line in ('76', '218', '312', '413', '517', '632', '744'):
        assert at(int(line)).startswith('## M')
    assert 'M61b' in at(871)

    # Every cited line reference in the obligation catalogue resolves in the source.
    for obligation in gm.m67_measurement_obligation_catalogue():
        assert obligation.roadmap_reference.startswith(':')
        for chunk in obligation.roadmap_reference.split(','):
            bounds = chunk.lstrip(':').split('-')
            assert len(bounds) in (1, 2) and all(bound.isdigit() for bound in bounds)
            assert int(bounds[0]) <= int(bounds[-1]), obligation.key
            for bound in bounds:
                assert 1 <= int(bound) <= len(roadmap), obligation.key
                assert roadmap[int(bound) - 1].strip(), (obligation.key, bound)


def test_obligation_catalogue_is_complete_and_consistent_with_the_frame():
    catalogue = gm.m67_measurement_obligation_catalogue()
    assert catalogue == gm.M67_OBLIGATIONS
    assert len({item.key for item in catalogue}) == len(catalogue)
    measured = measure(carry(), run(carry(), frame(observation())))
    frame_keys = {metric.key for metric in measured.metrics}
    assert {item.key for item in catalogue} <= frame_keys
    for obligation in catalogue:
        assert measured.metric(obligation.key).reason == obligation.reason
    assert len(frame_keys) == len(measured.metrics)
    report = gm.render_report(measured)
    assert report.count("[unavailable]") == len(measured.unavailable)
    assert report.count("[available]") == len(measured.metrics) - len(measured.unavailable)


def test_readiness_document_covers_every_obligation_and_gate():
    document = DOC_PATH.read_text(encoding="utf-8")
    for obligation in gm.m67_measurement_obligation_catalogue():
        assert obligation.key in document, obligation.key
    for marker in ('M63a', 'M63b', 'M64', 'M65a', 'M65b', 'M66a', 'M66b', 'M61b',
                   'M68a', 'M69', 'M71', 'not qualified', 'G05'):
        assert marker in document, marker
    for requirement in gm.REGIME_CLASSIFIER_REQUIREMENTS:
        assert requirement.roadmap_definition in document
    assert 'docs/superpowers/roadmaps/chronicler-phase8-governance-roadmap.md' in document


# --------------------------------------------------------------------------- #
# Published-record reconciliation: receipts must bind to the published carry.
# --------------------------------------------------------------------------- #

def rejected(opening, result):
    """Assert measurement refuses a malformed result without mutating anything."""
    before = (h.carry_to_json(opening), h.carry_to_json(result.carry))
    with pytest.raises(ValueError):
        measure(opening, result)
    assert (h.carry_to_json(opening), h.carry_to_json(result.carry)) == before


def test_published_institution_state_must_match_the_measured_turn_result():
    opening = carry()
    result = run(opening, frame(enact_and_suppress()))
    civ = result.carry.civilizations[0]
    assert civ.institutions.institutions  # the receipt really enacts something
    stripped = replace(civ, institutions=i.InstitutionSnapshot(2, ()))
    rejected(opening, replace(result, carry=replace(
        result.carry, civilizations=(stripped,))))


def test_published_governance_state_must_match_the_measured_accrual():
    opening = carry()
    result = run(opening, frame(enact_and_suppress()))
    civ = result.carry.civilizations[0]
    assert civ.governance.ruler_legitimacy == result.receipts[0].accrual.state.ruler_legitimacy
    changed = replace(civ, governance=replace(civ.governance, ruler_legitimacy=.75))
    rejected(opening, replace(result, carry=replace(
        result.carry, civilizations=(changed,))))


def test_published_elite_ratchet_must_match_the_measured_g02_output():
    opening = carry()
    result = run(opening, frame(enact_and_suppress()))
    civ = result.carry.civilizations[0]
    assert civ.ratchet.conspicuous_consumption_index == 0.
    changed = replace(civ, ratchet=replace(civ.ratchet,
                                          conspicuous_consumption_index=99.))
    rejected(opening, replace(result, carry=replace(
        result.carry, civilizations=(changed,))))


def test_request_receipts_must_be_unique_and_agree_with_spend_decisions():
    opening = carry()
    result = run(opening, frame(enact_and_suppress()))
    receipt = result.receipts[0]
    assert [decision.approved for decision in receipt.spending.decisions] == [True, True]
    conflicting = replace(receipt.requests[0], approved=False,
                          status='insufficient_capital')
    retained = replace(receipt.requests[0], status='structurally_unused', approved=False)
    for requests in ((conflicting,) + receipt.requests[1:], receipt.requests * 2,
                     (retained,) + receipt.requests[1:]):
        rejected(opening, replace(result, receipts=(replace(receipt, requests=requests),)))
    # Legitimate structurally_unused and ineligible_mock receipts are retained.
    unused = run(carry(), frame(observation(proposals=(
        i.ProposalAttempt(i.InstitutionType.CONSCRIPTION, .9),),
        mock_suppressions=(h.MockSuppression('x', True),))), policy(
            institutions=replace(policy().institutions, proposal_probability=.5)))
    statuses = [item.status for item in unused.receipts[0].requests]
    assert statuses == ['structurally_unused', 'acknowledged_mock']
    civ = measure(carry(), unused).civilization(0)
    assert [item.status for item in civ.requests] == statuses
    assert civ.used_spend_operations == 0
    assert [spend.action for spend in civ.spending] == [
        c.GovernanceAction.SUPPRESS_SECESSION]


def test_ambition_outcome_epoch_identity_and_delta_must_reconcile():
    goal = a.Ambition(a.AmbitionType.CONQUER_REGION, 'Border', 0, 20, 0)
    opening = carry(initial(reign=a.RulerAmbitions('0', 'reign-0', 0, 0, (goal,))))
    snapshot = a.AmbitionSnapshot('0', 'reign-0', 1, 0, .5, .3, owned_regions=('Border',))
    result = run(opening, frame(observation(ambition_snapshot=snapshot)))
    receipt = result.receipts[0]
    original = receipt.ambition_outcomes[0]
    assert original.turn == 1 and original.legitimacy_delta == .1
    for changed in (replace(original, turn=2),
                    replace(original, legitimacy_delta=.9),
                    replace(original, contribution_key=replace(original.contribution_key,
                                                              ruler_id='other')),
                    replace(original, civ_id='1'),
                    replace(original, ambition_type=a.AmbitionType.PATRON_OF_ARTS),
                    replace(original, target='Elsewhere'),
                    replace(original, event_type='ambition_failed')):
        rejected(opening, replace(result, receipts=(
            replace(receipt, ambition_outcomes=(changed,)),)))
    duplicate = replace(receipt, ambition_outcomes=(original, original))
    rejected(opening, replace(result, receipts=(duplicate,)))


def test_elite_identity_partition_must_be_unique_ranked_and_disjoint():
    opening = carry()
    result = run(opening, frame(enact_and_suppress()))
    elite = result.elite_metrics
    record = elite.civilizations[0]
    person = e.EliteIdentity(7, None)
    other = e.EliteIdentity(8, None)
    for changed in (
            replace(record, qualifiers=(person, person), office_holders=(person,),
                    frustrated_aspirants=(person,)),
            replace(record, qualifiers=(person,), office_holders=(other,),
                    frustrated_aspirants=()),
            replace(record, qualifiers=(person, other), office_holders=(person,),
                    frustrated_aspirants=(person,)),
            replace(record, qualifiers=(person, other), office_holders=(person, other),
                    frustrated_aspirants=(other,)),
            replace(record, emp=-1.0),
            replace(record, conspicuous_consumption_index=-0.5)):
        rejected(opening, replace(result, elite_metrics=replace(
            elite, civilizations=(changed,))))
    # A genuine G02 partition is accepted and keeps its public counts.
    agents = tuple(e.AgentEliteInput(k, 0, 10., e.Occupation.SCHOLAR, .9, .1)
                   for k in range(3))
    populated = run(opening, frame(observation(), agents=agents))
    civ = measure(opening, populated).civilization(0)
    assert civ.elite.qualifier_count == 3
    assert civ.elite.office_holder_count == 2
    assert civ.elite.frustrated_aspirant_count == 1
    assert [x.agent_id for x in civ.elite.office_holders] == [0, 1]
    assert [x.agent_id for x in civ.elite.frustrated_aspirants] == [2]


def test_observed_neglect_repeal_counts_once_in_the_generic_repeal_count():
    institution = i.InstitutionState(i.InstitutionType.CONSCRIPTION, 0, .01, 8.,
                                     i.Faction.MERCHANT)
    opening = carry(initial(institutions=(institution,)))
    result = run(opening, frame(observation(treasury=0.)))
    events = result.receipts[0].institutions.events
    assert [(event.event_type, event.reason) for event in events
            if event.event_type == 'institution_repealed'] == [
        ('institution_repealed', 'neglect')]
    assert result.receipts[0].institutions.repeal_outcomes == ()
    measured = measure(opening, result)
    civ = measured.civilization(0)
    assert civ.institutions == () and civ.opening_institution_count == 1
    assert measured.metric('institution_count').value == 0
    assert measured.metric('repeal_count').value == 1
    assert measured.metric('forced_repeal_count').value == 0
    assert measured.metric('neglect_repeal_count').value == 1
    assert measured.metric('repeal_count').value == (
        measured.metric('forced_repeal_count').value
        + measured.metric('neglect_repeal_count').value)
    # A forced repeal is counted once, not twice, despite both surfaces.
    forced_opening = carry(initial(
        balance=Fraction(1, 2),
        institutions=(i.InstitutionState(i.InstitutionType.HOLY_INQUISITION, 0, .5, 2.,
                                         i.Faction.MERCHANT),)))
    forced = run(forced_opening, frame(observation(factions=i.FactionWeights(.1, .6, .2, .1))))
    assert [outcome.status for outcome in forced.receipts[0].institutions.repeal_outcomes
            ] == [i.RepealStatus.REPEALED]
    assert any(event.event_type == 'institution_repealed'
               for event in forced.receipts[0].institutions.events)
    forced_measured = measure(forced_opening, forced)
    assert forced_measured.metric('repeal_count').value == 1
    assert forced_measured.metric('forced_repeal_count').value == 1
    assert forced_measured.metric('neglect_repeal_count').value == 0
    assert forced_measured.civilization(0).institutions == ()


def test_exact_fraction_domain_matches_the_public_kernel():
    balance = Fraction(1, 2 ** 513)
    opening = carry(initial(balance=balance))
    result = run(opening, frame(observation()))
    measured = measure(opening, result)
    civ = measured.civilization(0)
    assert civ.opening_capital.exact_balance.as_fraction() == balance
    assert civ.published_capital.exact_balance.as_fraction() == balance
    payload = json.loads(gm.measurement_json(measured))
    assert payload['civilizations'][0]['opening_capital']['exact_balance'] == {
        'fraction': [1, 2 ** 513]}
    assert str(balance) in gm.render_report(measured)
    # Canonical form is still required: reduced terms and a positive denominator.
    for arguments in ((2, 4), (1, 0), (1, -2), (0, 0)):
        with pytest.raises(ValueError):
            gm.ExactFraction(*arguments)


def test_mutable_diagnostics_are_rejected_before_they_can_escape():
    opening = carry()
    result = run(opening, frame(observation()))
    measured = measure(opening, result)
    assert all(type(diagnostic) is str for diagnostic in measured.diagnostics)
    assert measured.diagnostics == result.diagnostics
    mutable = ['synthetic marker']
    with pytest.raises(ValueError, match='diagnostics'):
        measure(opening, replace(result, diagnostics=(mutable,)))
    for bad in (["nested"], ('',), ('ok', ['nested']), (object(),)):
        with pytest.raises(ValueError, match='diagnostics'):
            measure(opening, replace(result, diagnostics=bad))


# --------------------------------------------------------------------------- #
# Report determinism and process-level stability.
# --------------------------------------------------------------------------- #

def test_report_is_deterministic_and_free_of_volatile_fields():
    opening = carry()
    measured = measure(opening, run(opening, frame(enact_and_suppress())))
    text = gm.render_report(measured)
    assert text.endswith("\n")
    assert text == gm.render_report(measured)
    assert gm.measurement_json(measured) == gm.measurement_json(measure(
        opening, run(opening, frame(enact_and_suppress()))))
    for volatile in (str(REPO_ROOT), 'timestamp', 'Timestamp', 'elapsed', 'seconds'):
        assert volatile not in text
    assert '\n\n' in text
    assert json.loads(gm.measurement_json(measured))["source_turn"] == 1
    with pytest.raises(ValueError, match='GovernanceMeasurementFrame'):
        gm.render_report(object())
    with pytest.raises(ValueError, match='GovernanceMeasurementFrame'):
        gm.measurement_json(object())
    with pytest.raises(ValueError, match='SourceIdentity'):
        gm.render_obligation_catalogue('not-an-identity')


def test_default_off_report_invokes_no_example(monkeypatch, capsys):
    script = load_script()
    calls = []

    def forbidden(*args, **kwargs):
        calls.append(args)
        raise AssertionError('the default-off report invoked the example')

    monkeypatch.setattr(script, 'run_example', forbidden)
    assert script.main([]) == 0
    out = capsys.readouterr().out
    assert calls == []
    assert 'NO MEASUREMENT' in out
    assert 'no example was invoked' in out
    assert gm.SYNTHETIC_BANNER in out
    assert f"source_revision: {gm.REVIEWED_HARNESS_SOURCE.revision}" in out
    for obligation in gm.m67_measurement_obligation_catalogue():
        assert f"[unavailable] {obligation.key} = {obligation.reason}" in out
    assert 'CIVILIZATION' not in out
    assert 'REGIME CLASSIFIER PREREGISTRATION' in out
    assert out == gm.render_obligation_catalogue(gm.REVIEWED_HARNESS_SOURCE)


def test_opt_in_report_measures_the_existing_example_and_labels_it_synthetic(capsys, tmp_path):
    script = load_script()
    destination = tmp_path / "report.txt"
    assert script.main(['--run-example', '--output', str(destination)]) == 0
    out = capsys.readouterr().out
    assert gm.SYNTHETIC_BANNER in out
    assert 'origin: synthetic_four_kernel_harness' in out
    assert f'policy_id: {h.POLICY_ID}' in out
    assert 'source_turn: 1  effective_turn: 2  opening_last_committed_turn: 0' in out
    assert 'identity_registry: [0]' in out
    assert 'effective_turn=2' in out
    assert '  - enact_institution ' in out and 'approved=true' in out
    assert '  - suppress_secession ' in out
    assert '[available]   institution_count = 1' in out
    assert '[unavailable] psi = ' in out
    assert 'implemented: false' in out
    assert destination.read_text(encoding="utf-8") == out

    assert script.main(['--run-example', '--json']) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload['schema'] == gm.MEASUREMENT_SCHEMA
    assert payload['report_kind'] == gm.REPORT_KIND
    assert payload['origin'] == 'synthetic_four_kernel_harness'
    assert payload['policy_id'] == h.POLICY_ID
    assert payload['source_turn'] == 1 and payload['effective_turn'] == 2
    civ = payload['civilizations'][0]
    assert civ['civ_id'] == 0
    assert civ['published_capital']['exact_balance'] == {"fraction": [0, 1]}
    assert civ['spend_total'] == {"fraction": [3, 10]}
    assert [spend['action'] for spend in civ['spending']] == [
        'enact_institution', 'suppress_secession']
    assert civ['elite']['emp'] == 0.0


def test_cli_rejects_an_invalid_source_identity_or_origin():
    script = load_script()
    with pytest.raises(SystemExit, match='invalid source identity'):
        script.main(['--revision', 'not-a-hash'])
    with pytest.raises(SystemExit, match='invalid source identity'):
        script.main(['--source-label', '  '])
    with pytest.raises(SystemExit):
        script.main(['--origin', 'production'])


def test_opt_in_wraps_then_restores_the_harness_entry_point(monkeypatch):
    script = load_script()
    original = h.run_kernel_frame
    opening, result = script.run_example()
    assert h.run_kernel_frame is original
    assert opening.effective_turn == 1
    assert result.carry.effective_turn == 2
    measured = gm.measure_governance_result(opening=opening, result=result, origin=ORIGIN,
                                             source_identity=IDENTITY)
    assert measured.source_turn == 1
    assert measured.metric('institution_count').value == 1
    assert measured.civilization(0).capital_after_spend.as_fraction() == 0
    assert measured.metric('emp').value == (0.0,)

    def boom(*args, **kwargs):
        raise RuntimeError('injected example failure')

    monkeypatch.setattr(script, 'runpy', SimpleNamespace(run_path=lambda *a, **k: {
        'experiment': boom}))
    with pytest.raises(RuntimeError, match='injected'):
        script.run_example()
    assert h.run_kernel_frame is original
    monkeypatch.setattr(script, 'runpy', SimpleNamespace(run_path=lambda *a, **k: {}))
    with pytest.raises(SystemExit, match='experiment'):
        script.run_example()
    assert h.run_kernel_frame is original


def test_report_bytes_are_stable_across_fresh_processes_and_hash_seeds():
    digests = set()
    for seed in ("0", "1", "424242"):
        first = run_script("--run-example", hash_seed=seed)
        second = run_script("--run-example", hash_seed=seed)
        assert first.returncode == 0, first.stderr
        assert 'Traceback' not in first.stderr
        assert first.stdout == second.stdout
        digests.add(hashlib.sha256(first.stdout.encode("utf-8")).hexdigest())
        payload = run_script("--run-example", "--json", hash_seed=seed)
        assert payload.returncode == 0, payload.stderr
        json.loads(payload.stdout)
        off = run_script(hash_seed=seed)
        assert off.returncode == 0, off.stderr
        assert 'NO MEASUREMENT' in off.stdout
        assert 'CIVILIZATION' not in off.stdout
    assert len(digests) == 1
    assert json.loads(run_script("--run-example", "--json").stdout)["source_turn"] == 1


def test_measurement_module_imports_no_simulation_models_or_analytics():
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT / "src")
    code = ("import sys\n"
            "import chronicler.governance_measurements\n"
            "print(','.join(sorted(m for m in sys.modules if m.startswith('chronicler.'))))\n")
    completed = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                               cwd=str(REPO_ROOT), env=env)
    assert completed.returncode == 0, completed.stderr
    imported = set(completed.stdout.strip().split(','))
    assert imported == {'chronicler.governance_measurements',
                        'chronicler.governance_kernel_harness', 'chronicler.institutions',
                        'chronicler.elite_metrics', 'chronicler.governance_capital',
                        'chronicler.ruler_ambitions'}
    for forbidden in ('chronicler.analytics', 'chronicler.simulation', 'chronicler.models',
                      'chronicler.agent_bridge', 'chronicler.main', 'chronicler.politics',
                      'chronicler.action_engine', 'chronicler.world_gen',
                      'chronicler.main', 'chronicler.batch'):
        assert forbidden not in imported


def test_lane_imports_only_the_reviewed_kernel_surface():
    script_source = SCRIPT_PATH.read_text(encoding="utf-8")
    assert re.findall(r"^from chronicler import (\w+)", script_source, re.MULTILINE) == [
        "governance_kernel_harness", "governance_measurements"]
    library_source = (REPO_ROOT / "src" / "chronicler" / "governance_measurements.py").read_text(
        encoding="utf-8")
    assert re.findall(r"^from \. import (\w+)", library_source, re.MULTILINE) == [
        "elite_metrics", "governance_capital", "governance_kernel_harness", "institutions",
        "ruler_ambitions"]
    for unrelated in ("analytics", "simulation", "models", "agent_bridge", "world_gen",
                      "politics", "action_engine", "nation", "main"):
        for source in (library_source, script_source):
            assert not re.search(rf"^(?:import|from)\s+\S*{unrelated}\b", source, re.MULTILINE)