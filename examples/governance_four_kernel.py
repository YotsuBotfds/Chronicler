"""Run an explicit synthetic four-kernel experiment; no simulation inputs.

From the repository root: PYTHONPATH=src python examples/governance_four_kernel.py
All constants are illustrative test-fixture values, not production calibration.
"""
from dataclasses import replace
from fractions import Fraction
import json

from chronicler import governance_kernel_harness as h
from chronicler import institutions as i
from chronicler import elite_metrics as e
from chronicler import governance_capital as c
from chronicler import ruler_ambitions as a


def synthetic_policy() -> h.HarnessPolicy:
    return h.HarnessPolicy(
        policy_id=h.POLICY_ID,
        institutions=i.InstitutionCoefficients(1., .1, .02, tuple(
            i.InstitutionRule(t, i.Faction.MERCHANT if i.alignment(t) != i.Faction.MERCHANT
                              else i.Faction.MILITARY, 2.) for t in i.InstitutionType)),
        elite_calibration=e.EliteCalibration(.1, .1, 2.),
        elite_conventions=e.EliteConventions(e.WealthPercentileConvention.LOWER,
            e.PositionRounding.FLOOR, e.EqualWealthOrder.AGENTS_FIRST),
        capital=c.CapitalCoefficients(.5, 0., 0., .05, .1, .1, 0., .1, .2),
        spend_costs=c.SpendCosts(.1, .2, .15),
        ambitions=a.AmbitionCalibration(2, 20, 40, .1, .05,
            ((a.AmbitionType.CONQUER_REGION, 1.), (a.AmbitionType.PATRON_OF_ARTS, 1.))),
        funding=i.FundingPolicy.BASE_FIRST_FULL_DEBIT,
        fiscal_rounding='fractional_fixture_no_integer_treasury',
        enforcement_pricing='persisted_enactment_cost',
        contribution_retention='reign_long_no_decay',
        accession_evaluation='defer_new_objectives',
        capital_on_accession='carry_remaining',
        population_source='synthetic_living_row_count',
        missing_observations='abort_frame', capital_limit=Fraction(10),
        evidence_replay='monotone_complete_cursor_log')


def experiment() -> h.HarnessResult:
    config = synthetic_policy()
    opening = h.HarnessCarry(0, -1, (0,), (h.CivCarry(0, i.InstitutionSnapshot(0, ()),
        e.EliteRatchetState(-1, 0.), c.GovernanceState(0, .5, .3), None),))
    obs = h.CivObservation(civ_id=0, factions=i.FactionWeights(.6, .1, .2, .1), treasury=100.,
        base_governing_cost=0., region_count=4, trade_route_count=3, proposals=(), mock_suppressions=(),
        ambition_snapshot=a.AmbitionSnapshot('0', 'synthetic-reign-1', 0, 0, .5, .3,
            owned_regions=('Home',), conquerable_regions=('Border',), military_eligible=True),
        legitimacy=c.LegitimacyInputs(), events=(), accession=c.SuccessionKind.PEACEFUL,
        ambition_draws=(a.SelectionDraw(0., 0., 0.),)*2, accession_event_cursor=0)
    first = h.run_kernel_frame(enabled=True, opening=opening,
        observations=h.SyntheticFrame(0, 0, 'explicit_synthetic_fixture', (obs,), (), ()), policy=config)
    # Prove restart preserves exact carry before spending .1 + .2 from one wallet.
    restored = h.carry_from_json(h.carry_to_json(first.carry))
    next_obs = replace(obs,
        ambition_snapshot=replace(obs.ambition_snapshot, turn=1, owned_regions=('Home', 'Border')),
        accession=None, ambition_draws=(), accession_event_cursor=None,
        proposals=(i.ProposalAttempt(i.InstitutionType.CONSCRIPTION, 0.),),
        mock_suppressions=(h.MockSuppression('synthetic-suppression-1', True),))
    return h.run_kernel_frame(enabled=True, opening=restored,
        observations=h.SyntheticFrame(1, 1, 'explicit_synthetic_fixture', (next_obs,), (), ()), policy=config)


if __name__ == '__main__':
    result = experiment()
    receipt = result.receipts[0]
    state = result.carry.civilizations[0]
    print(json.dumps(dict(policy=result.policy_id, effective_turn=result.carry.effective_turn,
        approved=[d.request.action.value for d in receipt.spending.decisions if d.approved],
        exact_capital=[state.governance.exact_political_capital.numerator, state.governance.exact_political_capital.denominator],
        legitimacy=state.governance.ruler_legitimacy,
        ambition_contributions=len(state.contributions), diagnostics=result.diagnostics), indent=2))
