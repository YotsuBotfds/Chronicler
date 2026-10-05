"""M66a standalone oracle tests; no native extension or runtime integration."""
from dataclasses import FrozenInstanceError, fields, replace
from fractions import Fraction
from itertools import permutations
import math
import random

import pytest

from chronicler.governance_capital import (
    AccessionInput,
    AmbitionLegitimacyInput,
    CapitalCoefficients,
    DynastyPrestigeInput,
    GovernanceAction,
    GovernanceState,
    InstitutionSupportInput,
    LegitimacyInputs,
    SpendCosts,
    SpendRequest,
    SuccessionKind,
    accrue_capital,
    compute_legitimacy,
    resolve_spending,
)


@pytest.fixture
def coefficients():
    # Illustrative test calibration. No values are promoted into runtime.
    return CapitalCoefficients(
        legitimacy_base=0.5,
        political_capital_base=0.1,
        legitimacy_to_capital_rate=0.1,
        institution_support_rate=0.05,
        victory_legitimacy_bonus=0.1,
        defeat_legitimacy_penalty=0.1,
        faction_alignment_bonus=0.3,
        peaceful_succession_bonus=0.1,
        contested_succession_penalty=0.2,
    )


@pytest.fixture
def costs():
    # Costs from M66a's action table, including force repeal (0.15).
    return SpendCosts(0.10, 0.20, 0.15)


def test_empty_evidence_and_institutions_are_valid(coefficients):
    result = compute_legitimacy(LegitimacyInputs(), coefficients)
    assert result.ruler_legitimacy == 0.5
    assert result.sources.base == 0.5
    assert all(getattr(result.sources, f.name) == 0 for f in fields(result.sources)[1:])


def test_inherited_prestige_uses_explicit_one_over_n(coefficients):
    inputs = LegitimacyInputs(dynasty=(
        DynastyPrestigeInput(3, 0.3),
        DynastyPrestigeInput(1, 0.1),
        DynastyPrestigeInput(2, 0.2),
    ))
    result = compute_legitimacy(inputs, coefficients)
    assert result.sources.dynasty == 0.3
    assert result.ruler_legitimacy == 0.8
    # Sparse predecessor numbers are evidence, not renumbered by sequence position.
    sparse = compute_legitimacy(LegitimacyInputs(dynasty=(DynastyPrestigeInput(5, 0.5),)), coefficients)
    assert sparse.sources.dynasty == 0.1


def test_institutions_sum_only_aligned_clamped_legitimacy(coefficients):
    inputs = LegitimacyInputs(ruler_faction="clergy", institutions=(
        InstitutionSupportInput("tithe", "clergy", 0.4),
        InstitutionSupportInput("divine", "clergy", 2.0),
        InstitutionSupportInput("neglected", "clergy", -1.0),
        InstitutionSupportInput("courts", "merchant", 1.0),
    ))
    result = compute_legitimacy(inputs, coefficients)
    assert result.sources.institutions == 0.07
    assert result.ruler_legitimacy == 0.57
    assert inputs.institutions[1].legitimacy == 2.0  # No mutation while clamping.


def test_unresolved_ruler_faction_has_no_institutional_support(coefficients):
    inputs = LegitimacyInputs(institutions=(InstitutionSupportInput("law", "cultural", 1),))
    assert compute_legitimacy(inputs, coefficients).sources.institutions == 0


@pytest.mark.parametrize("ruler,dominant,expected", [
    ("military", "military", 0.3),
    ("military", "merchant", 0.0),
    (None, None, 0.0),
    (None, "military", 0.0),
    ("military", None, 0.0),
])
def test_supplied_faction_alignment_without_threshold_policy(coefficients, ruler, dominant, expected):
    inputs = LegitimacyInputs(ruler_faction=ruler, dominant_faction=dominant)
    assert compute_legitimacy(inputs, coefficients).sources.faction_alignment == expected


def test_successes_and_defeats_have_normalized_signed_deltas(coefficients):
    inputs = LegitimacyInputs(successful_outcomes=3, failed_outcomes=2)
    result = compute_legitimacy(inputs, coefficients)
    assert result.sources.victories == 0.1
    assert result.ruler_legitimacy == 0.6


@pytest.mark.parametrize("successes,failures,expected,delta", [
    (20, 0, 1.0, 2.0),
    (0, 20, 0.0, -2.0),
    (5, 0, 1.0, 0.5),
    (0, 5, 0.0, -0.5),
])
def test_legitimacy_clamps_preserve_unclamped_sources(coefficients, successes, failures, expected, delta):
    result = compute_legitimacy(LegitimacyInputs(successful_outcomes=successes, failed_outcomes=failures), coefficients)
    assert result.ruler_legitimacy == expected
    assert result.sources.victories == delta


@pytest.mark.parametrize("kind,expected,delta", [
    (SuccessionKind.PEACEFUL, 0.75, 0.1),
    (SuccessionKind.CONTESTED, 0.45, -0.2),
])
def test_accession_rebuilds_from_dynasty_institutions_and_succession(coefficients, kind, expected, delta):
    inputs = LegitimacyInputs(
        dynasty=(DynastyPrestigeInput(2, 0.2),),
        institutions=(InstitutionSupportInput("law", "cultural", 1.0),),
        ruler_faction="cultural", dominant_faction="cultural",
        successful_outcomes=100, failed_outcomes=1,
    )
    result = compute_legitimacy(inputs, coefficients, kind)
    assert result.ruler_legitimacy == expected
    assert result.sources.dynasty == 0.1
    assert result.sources.institutions == 0.05
    assert result.sources.succession == delta
    assert result.sources.victories == result.sources.faction_alignment == 0


@pytest.mark.parametrize("kind,bonus,expected", [
    (SuccessionKind.PEACEFUL, 2.0, 1.0),
    (SuccessionKind.CONTESTED, 2.0, 0.0),
])
def test_accession_clamps(coefficients, kind, bonus, expected):
    name = "peaceful_succession_bonus" if kind is SuccessionKind.PEACEFUL else "contested_succession_penalty"
    c = replace(coefficients, **{name: bonus})
    assert compute_legitimacy(LegitimacyInputs(), c, kind).ruler_legitimacy == expected


def test_source_order_is_deterministic_across_evidence_permutations(coefficients):
    dynasty = (DynastyPrestigeInput(1, 0.1), DynastyPrestigeInput(3, 0.3), DynastyPrestigeInput(2, 0.2))
    institutions = tuple(InstitutionSupportInput(name, "merchant", value)
                         for name, value in (("z", 1.0), ("a", 1e-20), ("m", 0.8)))
    expected = None
    for d in permutations(dynasty):
        for i in permutations(institutions):
            result = compute_legitimacy(LegitimacyInputs(d, i, "merchant", "merchant", 2, 1), coefficients)
            if expected is None:
                expected = result
            assert result == expected
    assert tuple(f.name for f in fields(expected.sources)) == (
        "base", "dynasty", "institutions", "victories", "ambitions", "faction_alignment", "succession",
    )


def test_ambitions_use_keyed_deltas_without_victory_coefficient(coefficients):
    c = replace(coefficients, victory_legitimacy_bonus=0.7, defeat_legitimacy_penalty=0.9)
    inputs = LegitimacyInputs(ambition_contributions=(
        AmbitionLegitimacyInput("ruler:goal:complete", 0.10),
        AmbitionLegitimacyInput("ruler:other:failed", -0.05),
    ))
    result = compute_legitimacy(inputs, c)
    assert result.sources.ambitions == 0.05
    assert result.sources.victories == 0
    assert result.ruler_legitimacy == 0.55


def test_ambition_keys_are_unique_and_order_independent(coefficients):
    contributions = (AmbitionLegitimacyInput("z", 0.10),
                     AmbitionLegitimacyInput("a", -0.05),
                     AmbitionLegitimacyInput("m", 0.10))
    results = [compute_legitimacy(LegitimacyInputs(ambition_contributions=p), coefficients)
               for p in permutations(contributions)]
    assert all(result == results[0] for result in results)
    assert results[0].sources.ambitions == 0.15
    with pytest.raises(ValueError, match="duplicate ambition_contributions"):
        LegitimacyInputs(ambition_contributions=(contributions[0], contributions[0]))


def test_ambition_snapshot_retention_is_explicit_not_incremental(coefficients):
    inputs = LegitimacyInputs(ambition_contributions=(AmbitionLegitimacyInput("ruler:goal", 0.1),))
    first = accrue_capital(GovernanceState(0, 0.5, 0), inputs, coefficients)
    retained = accrue_capital(first.state, inputs, coefficients)
    expired = accrue_capital(first.state, LegitimacyInputs(), coefficients)
    assert first.state.ruler_legitimacy == retained.state.ruler_legitimacy == 0.6
    assert expired.state.ruler_legitimacy == 0.5
    for kind in SuccessionKind:
        reset = compute_legitimacy(inputs, coefficients, kind)
        assert reset.sources.ambitions == 0


@pytest.mark.parametrize("delta,expected", [(10, 1.0), (-10, 0.0)])
def test_ambition_contributions_participate_in_normalized_clamp(coefficients, delta, expected):
    inputs = LegitimacyInputs(ambition_contributions=(AmbitionLegitimacyInput("goal", delta),))
    assert compute_legitimacy(inputs, coefficients).ruler_legitimacy == expected


def test_ambition_contribution_invalid_inputs_rejected():
    with pytest.raises(ValueError):
        AmbitionLegitimacyInput("", 0.1)
    for delta in (float("nan"), float("inf"), -float("inf")):
        with pytest.raises(ValueError):
            AmbitionLegitimacyInput("goal", delta)
    with pytest.raises(TypeError):
        AmbitionLegitimacyInput("goal", True)
    with pytest.raises(TypeError):
        LegitimacyInputs(ambition_contributions=[])


def test_recompute_does_not_accumulate_old_legitimacy_or_repeat_victories(coefficients):
    inputs = LegitimacyInputs(successful_outcomes=1)
    first = accrue_capital(GovernanceState(0, 0.99, 0), inputs, coefficients)
    second = accrue_capital(first.state, inputs, coefficients)
    assert first.state.ruler_legitimacy == second.state.ruler_legitimacy == 0.6
    assert first.generated_capital == second.generated_capital == 0.16
    assert second.state.political_capital == 0.32


@pytest.mark.parametrize("base,expected", [(0.0, 0.0), (0.5, 0.05), (1.0, 0.1)])
def test_generation_scales_with_normalized_legitimacy(coefficients, base, expected):
    c = replace(coefficients, legitimacy_base=base, political_capital_base=0)
    result = accrue_capital(GovernanceState(9, 0.2, 0.3), LegitimacyInputs(), c)
    assert result.generated_capital == expected
    assert result.opening_political_capital == 0.3
    assert result.state.political_capital == pytest.approx(0.3 + expected)
    assert result.state.effective_turn == 10


def test_generation_has_no_invented_cap(coefficients):
    prior = GovernanceState(0, 0.5, 100)
    result = accrue_capital(prior, LegitimacyInputs(), coefficients)
    assert result.state.political_capital == 100.15


@pytest.mark.parametrize("opening", [0, 0.37, 10])
def test_capital_at_accession_requires_explicit_caller_choice(coefficients, opening):
    prior = GovernanceState(4, 0.9, 50)
    accession = AccessionInput(SuccessionKind.CONTESTED, opening)
    result = accrue_capital(prior, LegitimacyInputs(), coefficients, accession)
    assert result.state.ruler_legitimacy == 0.3
    assert result.opening_political_capital == opening
    assert result.generated_capital == 0.13
    assert result.state.political_capital == pytest.approx(opening + 0.13)
    assert prior.political_capital == 50


def test_accession_has_no_implicit_capital_transfer():
    with pytest.raises(TypeError):
        AccessionInput(SuccessionKind.PEACEFUL)


def test_current_requests_cannot_spend_next_turn_generation(coefficients, costs):
    prior = GovernanceState(10, 0.0, 0.0)
    request = SpendRequest("law", GovernanceAction.ENACT_INSTITUTION)
    spent = resolve_spending(prior, (request,), costs)
    assert not spent.decisions[0].approved
    assert spent.state.effective_turn == 10
    next_turn = accrue_capital(spent.state, LegitimacyInputs(), coefficients)
    assert next_turn.state.effective_turn == 11
    assert next_turn.state.political_capital == 0.15
    assert resolve_spending(next_turn.state, (request,), costs).decisions[0].approved
    assert prior == GovernanceState(10, 0, 0)


def test_three_consumers_compete_for_one_budget_without_double_spend(costs):
    requests = tuple(SpendRequest(action.value, action) for action in GovernanceAction)
    result = resolve_spending(GovernanceState(3, 0.5, 0.3), requests, costs)
    assert [d.approved for d in result.decisions] == [True, True, False]
    assert [d.cost for d in result.decisions] == [0.1, 0.2, 0.15]
    assert [d.capital_after for d in result.decisions] == [0.2, 0, 0]
    assert result.state.political_capital == 0


def test_denial_consumes_nothing_and_later_cheaper_request_can_pass(costs):
    # Forced-repeal placement is an explicit caller choice, absent roadmap priority.
    requests = (SpendRequest("repeal", GovernanceAction.FORCE_REPEAL_INSTITUTION),
                SpendRequest("law", GovernanceAction.ENACT_INSTITUTION))
    result = resolve_spending(GovernanceState(0, 0.2, 0.1), requests, costs)
    assert [d.approved for d in result.decisions] == [False, True]
    assert result.decisions[0].capital_before == result.decisions[0].capital_after == 0.1
    assert result.state.political_capital == 0


def test_forced_repeal_position_is_explicit_and_not_sorted(costs):
    a = SpendRequest("z-first", GovernanceAction.ENACT_INSTITUTION)
    b = SpendRequest("a-second", GovernanceAction.FORCE_REPEAL_INSTITUTION)
    prior = GovernanceState(0, 0.5, 0.2)
    forward = resolve_spending(prior, (a, b), costs)
    backward = resolve_spending(prior, (b, a), costs)
    assert tuple(d.request for d in forward.decisions) == (a, b)
    assert tuple(d.request for d in backward.decisions) == (b, a)
    assert [d.approved for d in forward.decisions] == [True, False]
    assert [d.approved for d in backward.decisions] == [True, False]
    assert forward.state.political_capital == 0.1
    assert backward.state.political_capital == 0.05
    assert resolve_spending(prior, (a, b), costs) == forward


def test_enact_after_suppression_is_rejected_before_allocation(costs):
    prior = GovernanceState(0, 0.5, 0.2)
    requests = (SpendRequest("revolt", GovernanceAction.SUPPRESS_SECESSION),
                SpendRequest("law", GovernanceAction.ENACT_INSTITUTION))
    with pytest.raises(ValueError, match="enact before suppress"):
        resolve_spending(prior, requests, costs)
    assert prior.exact_political_capital == Fraction("0.2")


def test_roadmap_priority_gives_enact_first_access_to_shared_pool(costs):
    requests = (SpendRequest("law", GovernanceAction.ENACT_INSTITUTION),
                SpendRequest("revolt", GovernanceAction.SUPPRESS_SECESSION))
    result = resolve_spending(GovernanceState(0, 0.5, 0.2), requests, costs)
    assert [d.approved for d in result.decisions] == [True, False]
    assert result.state.exact_political_capital == Fraction("0.1")


def test_same_action_ties_keep_explicit_caller_order(costs):
    requests = (SpendRequest("z-first", GovernanceAction.ENACT_INSTITUTION),
                SpendRequest("a-second", GovernanceAction.ENACT_INSTITUTION))
    result = resolve_spending(GovernanceState(0, 0.5, 0.1), requests, costs)
    assert tuple(d.request for d in result.decisions) == requests
    assert [d.approved for d in result.decisions] == [True, False]


def test_priority_validation_ignores_explicit_forced_repeal_placement(costs):
    for actions in (
        (GovernanceAction.FORCE_REPEAL_INSTITUTION, GovernanceAction.ENACT_INSTITUTION, GovernanceAction.SUPPRESS_SECESSION),
        (GovernanceAction.ENACT_INSTITUTION, GovernanceAction.FORCE_REPEAL_INSTITUTION, GovernanceAction.SUPPRESS_SECESSION),
        (GovernanceAction.ENACT_INSTITUTION, GovernanceAction.SUPPRESS_SECESSION, GovernanceAction.FORCE_REPEAL_INSTITUTION),
    ):
        requests = tuple(SpendRequest(str(i), action) for i, action in enumerate(actions))
        result = resolve_spending(GovernanceState(0, 0.5, 1), requests, costs)
        assert tuple(d.request for d in result.decisions) == requests
        assert all(d.approved for d in result.decisions)


@pytest.mark.parametrize("capital,approved", [
    (0.1, True), (math.nextafter(0.1, 0), False), (math.nextafter(0.1, 1), True),
])
def test_exact_affordability_has_no_overdraft_tolerance(costs, capital, approved):
    result = resolve_spending(GovernanceState(0, 0.5, capital),
                              (SpendRequest("law", GovernanceAction.ENACT_INSTITUTION),), costs)
    assert result.decisions[0].approved is approved
    assert result.state.political_capital >= 0


def test_decimal_budget_handles_three_tenths_exactly(costs):
    requests = tuple(SpendRequest(str(i), GovernanceAction.ENACT_INSTITUTION) for i in range(4))
    result = resolve_spending(GovernanceState(0, 0.5, 0.3), requests, costs)
    assert [d.approved for d in result.decisions] == [True, True, True, False]
    assert result.state.political_capital == 0


def test_multiple_batches_use_remaining_state(costs):
    prior = GovernanceState(2, 0.5, 0.2)
    first = resolve_spending(prior, (SpendRequest("law", GovernanceAction.ENACT_INSTITUTION),), costs)
    second = resolve_spending(first.state, (SpendRequest("revolt", GovernanceAction.SUPPRESS_SECESSION),), costs)
    assert not second.decisions[0].approved
    assert second.state.political_capital == 0.1


def test_split_batches_cannot_overdraw_via_float_rounding():
    costs = SpendCosts(0.12345678901234561, 0.8765432109876544, 0)
    requests = (SpendRequest("first", GovernanceAction.ENACT_INSTITUTION),
                SpendRequest("second", GovernanceAction.SUPPRESS_SECESSION))
    prior = GovernanceState(0, 0.5, 1.0)
    whole = resolve_spending(prior, requests, costs)
    first = resolve_spending(prior, requests[:1], costs)
    second = resolve_spending(first.state, requests[1:], costs)
    assert [d.approved for d in whole.decisions] == [True, False]
    assert first.decisions + second.decisions == whole.decisions
    assert second.state == whole.state
    assert second.state.exact_political_capital == Fraction("0.87654321098765439")


def test_many_split_batches_match_whole_batch(costs):
    prior = GovernanceState(0, 0.5, 123.45678901234567)
    requests = tuple(SpendRequest(f"{action.value}:{i}", action)
                     for action in GovernanceAction for i in range(334))
    whole = resolve_spending(prior, requests, costs)
    state = prior
    decisions = []
    for request in requests:
        result = resolve_spending(state, (request,), costs)
        state = result.state
        decisions.extend(result.decisions)
    assert tuple(decisions) == whole.decisions
    assert state == whole.state


def test_large_balances_retain_small_spends_and_generation(coefficients, costs):
    prior = GovernanceState(0, 0.5, 1e16)
    request = SpendRequest("law", GovernanceAction.ENACT_INSTITUTION)
    spent = resolve_spending(prior, (request,), costs)
    # Float view cannot express this debit, but exact accounting retains it.
    assert spent.state.political_capital == prior.political_capital
    assert spent.state.exact_political_capital == Fraction(10**16) - Fraction("0.1")
    accrued = accrue_capital(spent.state, LegitimacyInputs(), coefficients)
    assert accrued.exact_generated_capital == Fraction("0.15")
    assert accrued.state.exact_political_capital == Fraction(10**16) + Fraction("0.05")


def test_exact_accrual_and_accession_preserve_remaining_balance(coefficients):
    exact = Fraction("0.87654321098765439")
    prior = GovernanceState(0, 0.5, float(exact), exact)
    result = accrue_capital(prior, LegitimacyInputs(), coefficients)
    assert result.exact_opening_political_capital == exact
    assert result.state.exact_political_capital == exact + Fraction("0.15")
    accession = AccessionInput(SuccessionKind.PEACEFUL, prior.political_capital,
                               prior.exact_political_capital)
    incoming = accrue_capital(prior, LegitimacyInputs(), coefficients, accession)
    assert incoming.state.exact_political_capital == exact + Fraction("0.16")


@pytest.mark.parametrize("view,exact,error", [
    (0.1, 0.1, TypeError),
    (0.1, Fraction("0.2"), ValueError),
    (0, Fraction("-0.1"), ValueError),
])
def test_exact_balance_requires_consistent_nonnegative_fraction(view, exact, error):
    with pytest.raises(error):
        GovernanceState(0, 0.5, view, exact)
    with pytest.raises(error):
        AccessionInput(SuccessionKind.PEACEFUL, view, exact)


def test_exact_balances_can_be_round_tripped_as_numerator_denominator(costs):
    exact = Fraction("0.87654321098765439")
    prior = GovernanceState(0, 0.5, float(exact), exact)
    saved = (prior.effective_turn, prior.ruler_legitimacy, prior.political_capital,
             exact.numerator, exact.denominator)
    restored = GovernanceState(saved[0], saved[1], saved[2], Fraction(saved[3], saved[4]))
    assert restored == prior
    request = SpendRequest("revolt", GovernanceAction.SUPPRESS_SECESSION)
    assert resolve_spending(restored, (request,), costs) == resolve_spending(prior, (request,), costs)


def test_spending_many_requests_conserves_decimal_budget(costs):
    requests = tuple(SpendRequest(f"{action.value}:{i}", action)
                     for action in GovernanceAction for i in range(334))
    start = 42.15
    result = resolve_spending(GovernanceState(0, 0.5, start), requests, costs)
    expected = Fraction(str(start))
    for decision in result.decisions:
        debit = Fraction(str(decision.cost))
        assert decision.approved == (expected >= debit)
        if decision.approved:
            expected -= debit
        assert decision.capital_after == float(expected)
    assert result.state.political_capital == float(expected)
    assert expected >= 0


def test_zero_cost_and_empty_requests_are_valid():
    prior = GovernanceState(0, 0.5, 0)
    assert resolve_spending(prior, (), SpendCosts(0, 0, 0)).state == prior
    result = resolve_spending(prior, (SpendRequest("law", GovernanceAction.ENACT_INSTITUTION),), SpendCosts(0, 0, 0))
    assert result.decisions[0].approved
    assert result.state == prior


def test_duplicate_request_ids_rejected_even_for_different_actions(costs):
    requests = (SpendRequest("same", GovernanceAction.ENACT_INSTITUTION),
                SpendRequest("same", GovernanceAction.SUPPRESS_SECESSION))
    with pytest.raises(ValueError, match="duplicate request_id"):
        resolve_spending(GovernanceState(0, 0.5, 1), requests, costs)


@pytest.mark.parametrize("values,name", [
    ((DynastyPrestigeInput(1, 0.1), DynastyPrestigeInput(1, 0.2)), "dynasty"),
    ((InstitutionSupportInput("law", "a", 1), InstitutionSupportInput("law", "b", 1)), "institutions"),
])
def test_duplicate_evidence_rejected(values, name):
    with pytest.raises(ValueError, match="duplicate"):
        LegitimacyInputs(**{name: values})


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -float("inf")])
def test_nonfinite_numeric_inputs_rejected(coefficients, bad):
    for item in fields(coefficients):
        with pytest.raises(ValueError):
            replace(coefficients, **{item.name: bad})
    for make in (
        lambda: DynastyPrestigeInput(1, bad),
        lambda: InstitutionSupportInput("law", "a", bad),
        lambda: GovernanceState(0, bad, 0),
        lambda: GovernanceState(0, 0.5, bad),
        lambda: AccessionInput(SuccessionKind.PEACEFUL, bad),
        lambda: SpendCosts(bad, 0.1, 0.1),
    ):
        with pytest.raises(ValueError):
            make()


def test_negative_coefficients_costs_prestige_and_budgets_rejected(coefficients):
    for item in fields(coefficients):
        with pytest.raises(ValueError):
            replace(coefficients, **{item.name: -0.1})
    for make in (
        lambda: DynastyPrestigeInput(1, -0.1),
        lambda: GovernanceState(0, 0.5, -0.1),
        lambda: AccessionInput(SuccessionKind.CONTESTED, -0.1),
        lambda: SpendCosts(0, -0.1, 0),
    ):
        with pytest.raises(ValueError):
            make()


@pytest.mark.parametrize("bad", [True, 1.0, "1"])
def test_counts_and_turns_require_integers(bad):
    for make in (
        lambda: DynastyPrestigeInput(bad, 0.1),
        lambda: LegitimacyInputs(successful_outcomes=bad),
        lambda: LegitimacyInputs(failed_outcomes=bad),
        lambda: GovernanceState(bad, 0.5, 0),
    ):
        with pytest.raises(TypeError):
            make()


def test_invalid_counts_and_base_scale_rejected(coefficients):
    with pytest.raises(ValueError):
        replace(coefficients, legitimacy_base=1.1)
    for make in (
        lambda: DynastyPrestigeInput(0, 0.1),
        lambda: DynastyPrestigeInput(-1, 0.1),
        lambda: LegitimacyInputs(successful_outcomes=-1),
        lambda: LegitimacyInputs(failed_outcomes=-1),
        lambda: GovernanceState(-1, 0.5, 0),
        lambda: GovernanceState(0, -0.1, 0),
        lambda: GovernanceState(0, 1.1, 0),
    ):
        with pytest.raises(ValueError):
            make()


@pytest.mark.parametrize("bad", [True, "0.1", None])
def test_numeric_types_are_not_silently_coerced(bad):
    with pytest.raises(TypeError):
        GovernanceState(0, 0.5, bad)
    with pytest.raises(TypeError):
        InstitutionSupportInput("law", "a", bad)


@pytest.mark.parametrize("bad", ["", "   ", None, 1])
def test_invalid_identity_inputs_rejected(bad):
    with pytest.raises(ValueError):
        SpendRequest(bad, GovernanceAction.ENACT_INSTITUTION)
    with pytest.raises(ValueError):
        InstitutionSupportInput("law", bad, 1)


def test_invalid_enum_values_and_mutable_snapshots_rejected(coefficients, costs):
    with pytest.raises(TypeError):
        SpendRequest("law", "enact_institution")
    with pytest.raises(TypeError):
        AccessionInput("peaceful", 0)
    with pytest.raises(TypeError):
        compute_legitimacy(LegitimacyInputs(), coefficients, "peaceful")
    with pytest.raises(TypeError):
        LegitimacyInputs(dynasty=[])
    with pytest.raises(TypeError):
        LegitimacyInputs(institutions=("law",))
    with pytest.raises(TypeError):
        resolve_spending(GovernanceState(0, 0.5, 1), [], costs)
    with pytest.raises(TypeError):
        resolve_spending(GovernanceState(0, 0.5, 1), ("law",), costs)


def test_extreme_valid_values_do_not_return_infinite_results(coefficients):
    max_float = float.fromhex("0x1.fffffffffffffp+1023")
    c = replace(coefficients, political_capital_base=max_float, legitimacy_to_capital_rate=0)
    with pytest.raises(ValueError, match="finite float range"):
        accrue_capital(GovernanceState(0, 0.5, max_float), LegitimacyInputs(), c)
    c = replace(coefficients, victory_legitimacy_bonus=max_float)
    with pytest.raises(ValueError, match="finite float range"):
        compute_legitimacy(LegitimacyInputs(successful_outcomes=2), c)
    with pytest.raises(ValueError):
        SpendCosts(10**400, 0, 0)


def test_smallest_float_budget_and_cost_are_not_treated_as_zero():
    tiny = math.nextafter(0.0, 1.0)
    costs = SpendCosts(tiny, tiny, tiny)
    requests = tuple(SpendRequest(str(i), GovernanceAction.ENACT_INSTITUTION) for i in range(2))
    result = resolve_spending(GovernanceState(0, 0.5, tiny), requests, costs)
    assert [d.approved for d in result.decisions] == [True, False]
    assert result.state.political_capital == 0


def test_all_inputs_and_outputs_are_immutable_without_rng_mutation(coefficients, costs):
    prior = GovernanceState(2, 0.5, 0.3)
    inputs = LegitimacyInputs()
    request = SpendRequest("law", GovernanceAction.ENACT_INSTITUTION)
    rng_before = random.getstate()
    spent = resolve_spending(prior, (request,), costs)
    next_turn = accrue_capital(spent.state, inputs, coefficients)
    assert random.getstate() == rng_before
    assert prior == GovernanceState(2, 0.5, 0.3)
    for obj, name in ((prior, "political_capital"), (inputs, "successful_outcomes"),
                      (request, "request_id"), (spent.decisions[0], "approved"),
                      (next_turn.state, "ruler_legitimacy")):
        with pytest.raises(FrozenInstanceError):
            setattr(obj, name, 0)
