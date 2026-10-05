"""M66b standalone contract examples and edge cases; no runtime/native fixture."""
from dataclasses import FrozenInstanceError, replace
import math
import random

import pytest

from chronicler.ruler_ambitions import (
    Ambition, AmbitionCalibration, AmbitionSnapshot, AmbitionType as T,
    ConversionObservation as Observation, ConversionPredicate as Predicate,
    EvidenceEvent as Event, RulerAmbitions, SelectionDraw as Draw,
    evaluate_ambitions, generate_ambitions, start_reign,
)


def calibration(**changes):
    return replace(AmbitionCalibration(3, 20, 40, .10, .05,
        tuple((kind, 1.) for kind in T)), **changes)


def snapshot(**changes):
    return replace(AmbitionSnapshot('Civ', 'reign-1', 7, 10, .5, .2,
        owned_regions=('Home',), conquerable_regions=('Border',),
        frontier_regions=('Frontier',), attainable_trade_partners=('Other',),
        buildable_regions=('Home',), military_eligible=True,
        clergy_eligible=True, arts_available=True, trade_routes_exist=True,
        conversion_predicates=(Predicate('Home', 1, minimum_share=.8),),
        conversion_observations=(Observation('Home', 1, belief_share=.2),)), **changes)


def draws(count=3, value=0.):
    return (Draw(value, value, value),) * count


def goal(kind, target=None, predicate=None, **changes):
    if target is None and kind != T.PATRON_OF_ARTS:
        target = 'Home' if kind in (T.BUILD_MONUMENT, T.RELIGIOUS_CONVERSION) else 'Border'
    return replace(Ambition(kind, target, 7, 27, 10, predicate), **changes)


def reign(*ambitions, **changes):
    return replace(RulerAmbitions('Civ', 'reign-1', 7, 10, ambitions, ('new_ruler',)), **changes)


def only(kind):
    return calibration(weights=((kind, 1.),))


def test_documented_example():
    config = AmbitionCalibration(2, 20, 40, .10, .05,
        ((T.CONQUER_REGION, 2.), (T.PATRON_OF_ARTS, 1.)))
    state = AmbitionSnapshot('Civ', 'reign-1', 7, 10, .5, .2,
        owned_regions=('Home',), conquerable_regions=('Border',),
        military_eligible=True, arts_available=True)
    current = start_reign(state, config, (Draw(.2, .5, 0.),) * 2)
    result = evaluate_ambitions(current, replace(state, turn=8,
        owned_regions=('Home', 'Border')), config)
    assert result.requested_legitimacy_delta == .10
    assert result.legitimacy == .6
    assert result.political_capital == .2
    assert result.governance_effective_turn == 9
    assert result.outcomes[0].event_type == 'ambition_fulfilled'
    assert result.outcomes[0].tag == 'ambition_completed_conquer_region'


def test_generation_is_stable_under_collection_order_and_does_not_consume_rng():
    state = snapshot(conquerable_regions=('Z', 'A', 'Z'),
        frontier_regions=('B', 'A'), attainable_trade_partners=('Z', 'Other'))
    config = calibration(weights=tuple(reversed(calibration().weights)))
    rng_before = random.getstate()
    result = generate_ambitions(state, config, draws())
    assert result == generate_ambitions(replace(state, conquerable_regions=('A', 'Z'),
        frontier_regions=('A', 'B'), attainable_trade_partners=('Other', 'Z')),
        calibration(), draws())
    assert [a.ambition_type for a in result] == sorted(
        (a.ambition_type for a in result), key=tuple(T).index)
    assert len(set(a.ambition_type for a in result)) == 3
    assert random.getstate() == rng_before
    with pytest.raises(FrozenInstanceError):
        state.turn = 8
    assert state.turn == 7


@pytest.mark.parametrize('kind', list(T))
def test_generation_excludes_already_satisfied_or_predicateless_goals(kind):
    state = snapshot(conquerable_regions=('Home',), frontier_regions=('Home',),
        attainable_trade_partners=('Civ', 'Other'), active_trade_partners=('Other',),
        buildable_regions=(), arts_available=False,
        conversion_observations=(Observation('Home', 1, belief_share=.8),))
    assert generate_ambitions(state, only(kind), draws()) == ()


@pytest.mark.parametrize('kind,changes', [
    (T.CONQUER_REGION, {'military_eligible': False}),
    (T.RELIGIOUS_CONVERSION, {'clergy_eligible': False}),
    (T.RELIGIOUS_CONVERSION, {'conversion_predicates': ()}),
    (T.BUILD_MONUMENT, {'buildable_regions': ('Foreign',)}),
    (T.PATRON_OF_ARTS, {'arts_available': False}),
    (T.ESTABLISH_TRADE, {'trade_routes_exist': False}),
])
def test_generation_requires_live_capability(kind, changes):
    assert generate_ambitions(snapshot(**changes), only(kind), draws()) == ()


def test_sparse_pool_returns_shortfall_and_no_diplomatic_objective():
    result = generate_ambitions(snapshot(), calibration(weights=((T.DIPLOMATIC_TRIUMPH, 100.),
        (T.PATRON_OF_ARTS, 1.))), draws())
    assert len(result) == 1
    assert result[0].ambition_type == T.PATRON_OF_ARTS
    assert generate_ambitions(snapshot(), calibration(weights=()), draws()) == ()
    assert generate_ambitions(snapshot(), calibration(weights=((T.PATRON_OF_ARTS, 0.),)), draws()) == ()


@pytest.mark.parametrize('value,expected_target,expected_deadline', [
    (0., 'A', 27), (.9999999999999999, 'Z', 47),
])
def test_uniform_target_and_inclusive_duration_endpoints(value, expected_target, expected_deadline):
    result = generate_ambitions(snapshot(conquerable_regions=('Z', 'A')),
        only(T.CONQUER_REGION), draws(value=value))
    assert result[0].target == expected_target
    assert result[0].deadline_turn == expected_deadline


def test_weighted_type_boundaries_and_large_weights():
    state = snapshot()
    config = calibration(ambitions_per_ruler=2,
        weights=((T.CONQUER_REGION, 1e308), (T.PATRON_OF_ARTS, 1e308)))
    result = generate_ambitions(state, config, (Draw(.5, 0., 0.), Draw(0., 0., 0.)))
    assert {a.ambition_type for a in result} == {T.CONQUER_REGION, T.PATRON_OF_ARTS}
    # Use different duration to observe the first selected type after canonical sorting.
    result = generate_ambitions(state, config, (Draw(.5, 0., 1 - 1e-10), Draw(0., 0., 0.)))
    assert next(a.deadline_turn for a in result if a.ambition_type == T.PATRON_OF_ARTS) == 47


def test_weights_copy_mutable_pairs_and_preserve_subnormal_positive_support():
    supplied = [[T.PATRON_OF_ARTS, 1.]]
    config = calibration(weights=supplied)
    supplied[0][1] = 0.
    assert config.weights == ((T.PATRON_OF_ARTS, 1.),)
    assert len(generate_ambitions(snapshot(), config, draws())) == 1
    config = calibration(ambitions_per_ruler=2, weights=(
        (T.BUILD_MONUMENT, 5e-324), (T.EXPAND_TERRITORY, 1e308),
        (T.PATRON_OF_ARTS, 1e308)))
    result = generate_ambitions(snapshot(), config, draws(2))
    assert [a.ambition_type for a in result] == [T.BUILD_MONUMENT, T.EXPAND_TERRITORY]


@pytest.mark.parametrize('kind,changes', [
    (T.CONQUER_REGION, {'owned_regions': ('Border', 'Home')}),
    (T.EXPAND_TERRITORY, {'owned_regions': ('Border', 'Home')}),
    (T.ESTABLISH_TRADE, {'active_trade_partners': ('Border',)}),
    (T.RELIGIOUS_CONVERSION, {'conversion_observations': (Observation('Home', 1, belief_share=.8),)}),
])
@pytest.mark.parametrize('turn', [7, 26, 27])
def test_state_completion_at_generation_before_deadline_and_on_deadline(kind, changes, turn):
    predicate = Predicate('Home', 1, minimum_share=.8) if kind == T.RELIGIOUS_CONVERSION else None
    current = reign(goal(kind, predicate=predicate))
    result = evaluate_ambitions(current, snapshot(turn=turn, **changes), calibration())
    assert result.reign.ambitions[0].completed
    assert not result.reign.ambitions[0].failed
    assert result.requested_legitimacy_delta == .1
    assert result.outcomes[0].turn == turn
    assert current.ambitions[0].completed is False


@pytest.mark.parametrize('turn,failed', [(26, False), (27, True), (28, True)])
def test_deadline_failure_boundaries(turn, failed):
    result = evaluate_ambitions(reign(goal(T.CONQUER_REGION)), snapshot(turn=turn), calibration())
    assert result.reign.ambitions[0].failed is failed
    assert result.requested_legitimacy_delta == (-.05 if failed else 0.)
    assert len(result.outcomes) == int(failed)
    if failed:
        assert result.outcomes[0].tag == 'ambition_failed_conquer_region'


def test_late_state_cannot_retroactively_complete_and_target_does_not_drift():
    current = start_reign(snapshot(), only(T.CONQUER_REGION), draws())
    after = snapshot(turn=28, owned_regions=('Home', 'Border'), conquerable_regions=('Elsewhere',))
    result = evaluate_ambitions(current, after, only(T.CONQUER_REGION))
    assert result.reign.ambitions[0].target == 'Border'
    assert result.reign.ambitions[0].failed


@pytest.mark.parametrize('kind,event_type,target', [
    (T.BUILD_MONUMENT, 'infrastructure_completed', 'Home'),
    (T.PATRON_OF_ARTS, 'cultural_work', None),
    (T.PATRON_OF_ARTS, 'invest_culture', None),
])
@pytest.mark.parametrize('event_turn,sequence,expected', [(7, 10, False), (7, 11, True),
    (6, 11, False), (27, 11, True), (28, 11, False)])
def test_event_generation_cursor_and_deadline_boundaries(kind, event_type, target, event_turn, sequence, expected):
    current = reign(goal(kind))
    result = evaluate_ambitions(current, snapshot(turn=28, event_cursor=11), calibration(),
        (Event(event_turn, sequence, 'Civ', event_type, target),))
    assert result.reign.ambitions[0].completed is expected
    assert result.reign.ambitions[0].failed is not expected


@pytest.mark.parametrize('event', [Event(8, 11, 'Other', 'infrastructure_completed', 'Home'),
    Event(8, 11, 'Civ', 'build_started', 'Home'),
    Event(8, 11, 'Civ', 'infrastructure_completed', 'Foreign'),
    Event(8, 11, 'Civ', 'infrastructure_completed')])
def test_build_ignores_wrong_actor_unfinished_build_or_wrong_target(event):
    result = evaluate_ambitions(reign(goal(T.BUILD_MONUMENT)), snapshot(turn=8, event_cursor=11),
        calibration(), (event,))
    assert result.outcomes == ()


def test_old_art_events_do_not_make_future_art_goal_already_satisfied():
    current = start_reign(snapshot(), only(T.PATRON_OF_ARTS), draws())
    result = evaluate_ambitions(current, snapshot(turn=8), calibration(),
        (Event(6, 9, 'Civ', 'invest_culture'),))
    assert len(current.ambitions) == 1
    assert result.outcomes == ()


@pytest.mark.parametrize('terminal', ['completed', 'failed'])
def test_terminal_ambitions_emit_once_even_when_evidence_replayed(terminal):
    state = snapshot(turn=27, owned_regions=('Home', 'Border') if terminal == 'completed' else ('Home',))
    first = evaluate_ambitions(reign(goal(T.CONQUER_REGION)), state, calibration())
    second = evaluate_ambitions(first.reign, replace(state, legitimacy=first.legitimacy), calibration())
    third = evaluate_ambitions(second.reign, replace(state, turn=30, owned_regions=('Border',)), calibration())
    assert second.outcomes == third.outcomes == ()
    assert second.requested_legitimacy_delta == third.requested_legitimacy_delta == 0.
    assert getattr(third.reign.ambitions[0], terminal)


def test_multiple_event_evidence_order_is_irrelevant_and_settles_once():
    current = reign(goal(T.PATRON_OF_ARTS))
    events = (Event(8, 12, 'Civ', 'invest_culture'), Event(8, 11, 'Civ', 'cultural_work'))
    state = snapshot(turn=8, event_cursor=12)
    a = evaluate_ambitions(current, state, calibration(), events)
    assert a == evaluate_ambitions(current, state, calibration(), tuple(reversed(events)))
    assert len(a.outcomes) == 1
    assert evaluate_ambitions(a.reign, state, calibration(), events).outcomes == ()


def test_religious_delta_predicate_is_injected_faith_scoped_and_not_accumulated():
    predicate = Predicate('Home', 2, minimum_delta=5)
    current = reign(goal(T.RELIGIOUS_CONVERSION, predicate=predicate))
    for observation in (Observation('Home', 1, conversion_delta=9),
                        Observation('Other', 2, conversion_delta=9), Observation('Home', 2),
                        Observation('Home', 2, conversion_delta=4)):
        result = evaluate_ambitions(current, snapshot(turn=8, conversion_observations=(observation,)), calibration())
        assert result.outcomes == ()
    result = evaluate_ambitions(current, snapshot(turn=8,
        conversion_observations=(Observation('Home', 2, conversion_delta=5),)), calibration())
    assert result.reign.ambitions[0].completed
    assert generate_ambitions(snapshot(conversion_predicates=(predicate,),
        conversion_observations=(Observation('Home', 2, conversion_delta=5),)), only(T.RELIGIOUS_CONVERSION), draws()) == ()


@pytest.mark.parametrize('legitimacy,expected', [(0., .05), (.98, 1.), (1., 1.)])
def test_combined_delta_is_clamped_once_independent_of_order(legitimacy, expected):
    current = reign(goal(T.CONQUER_REGION), goal(T.ESTABLISH_TRADE))
    result = evaluate_ambitions(current, snapshot(turn=27, legitimacy=legitimacy,
        owned_regions=('Border',)), calibration())
    assert result.requested_legitimacy_delta == pytest.approx(.05)
    assert result.legitimacy == pytest.approx(expected)
    assert result.applied_legitimacy_delta == pytest.approx(expected - legitimacy)
    assert [o.event_type for o in result.outcomes] == ['ambition_fulfilled', 'ambition_failed']
    assert result == evaluate_ambitions(replace(current, ambitions=tuple(reversed(current.ambitions))),
        snapshot(turn=27, legitimacy=legitimacy, owned_regions=('Border',)), calibration())


def test_failure_clamps_at_zero_and_calibration_is_used():
    result = evaluate_ambitions(reign(goal(T.CONQUER_REGION)), snapshot(turn=27, legitimacy=.01),
        calibration(failure_legitimacy=.2, completion_legitimacy=.3))
    assert result.legitimacy == 0.
    assert result.requested_legitimacy_delta == -.2
    assert result.applied_legitimacy_delta == -.01


def test_ruler_change_resets_objectives_keeps_civ_tags_and_ignores_old_events():
    old = evaluate_ambitions(reign(goal(T.PATRON_OF_ARTS)), snapshot(turn=8, event_cursor=11),
        calibration(), (Event(8, 11, 'Civ', 'invest_culture'),), event_tags=('offended_foreign_power',)).reign
    state = snapshot(turn=9, event_cursor=11, ruler_id='reign-2', legitimacy=.4)
    current = start_reign(state, only(T.PATRON_OF_ARTS), draws(), old)
    assert current.ruler_id == 'reign-2'
    assert current.accession_turn == 9
    assert current.ambitions[0].generated_event_cursor == 11
    assert not current.ambitions[0].completed
    assert current.ruler_event_tags == ('ambition_completed_patron_of_arts', 'new_ruler', 'offended_foreign_power')
    result = evaluate_ambitions(current, state, calibration(), (Event(8, 11, 'Civ', 'invest_culture'),))
    assert result.outcomes == ()
    assert result.legitimacy == .4
    assert start_reign(state, only(T.PATRON_OF_ARTS), (), current) == current


def test_external_tags_are_sorted_unique_and_do_not_require_agent_memory():
    current = start_reign(snapshot(), only(T.PATRON_OF_ARTS), draws(),
        event_tags=('z', 'new_ruler', 'a', 'z'))
    result = evaluate_ambitions(current, snapshot(), calibration(), event_tags=('a', 'b'))
    assert result.reign.ruler_event_tags == ('a', 'b', 'new_ruler', 'z')
    assert not hasattr(current, 'agent_id')


def test_contribution_keys_are_stable_distinct_and_reign_scoped():
    current = reign(goal(T.CONQUER_REGION), goal(T.ESTABLISH_TRADE))
    state = snapshot(turn=27, owned_regions=('Border',))
    first = evaluate_ambitions(current, state, calibration())
    assert first.outcomes == evaluate_ambitions(current, state, calibration()).outcomes
    keys = [outcome.contribution_key for outcome in first.outcomes]
    assert len(set(keys)) == 2
    assert keys[0].civ_id == 'Civ'
    assert keys[0].ruler_id == 'reign-1'
    assert keys[0].accession_turn == 7
    assert keys[0].accession_event_cursor == 10
    assert keys[0].ambition_type == T.CONQUER_REGION
    new_reign = replace(current, ruler_id='reign-2')
    new_result = evaluate_ambitions(new_reign, replace(state, ruler_id='reign-2'), calibration())
    assert set(keys).isdisjoint(outcome.contribution_key for outcome in new_result.outcomes)
    assert evaluate_ambitions(first.reign, state, calibration()).outcomes == ()


@pytest.mark.parametrize('changes', [ {'turn': 6}, {'event_cursor': 9}, {'civ_id': 'Other'}, {'ruler_id': 'new'} ])
def test_evaluation_rejects_wrong_reign_or_backwards_snapshot(changes):
    with pytest.raises(ValueError):
        evaluate_ambitions(reign(goal(T.CONQUER_REGION)), snapshot(**changes), calibration())


def test_evaluation_rejects_rollback_after_evaluation_and_invalid_events():
    current = evaluate_ambitions(reign(goal(T.CONQUER_REGION)), snapshot(turn=9, event_cursor=12), calibration()).reign
    for state in (snapshot(turn=8, event_cursor=12), snapshot(turn=9, event_cursor=11)):
        with pytest.raises(ValueError):
            evaluate_ambitions(current, state, calibration())
    for events in ((Event(10, 11, 'Civ', 'invest_culture'),),
                   (Event(9, 13, 'Civ', 'invest_culture'),),
                   (Event(9, 11, 'Civ', 'invest_culture'),) * 2):
        with pytest.raises(ValueError):
            evaluate_ambitions(current, snapshot(turn=9, event_cursor=12), calibration(), events)


@pytest.mark.parametrize('changes', [ {'legitimacy': -1.}, {'legitimacy': 1.01},
    {'legitimacy': math.nan}, {'political_capital': math.inf}, {'political_capital': -1.},
    {'turn': True}, {'event_cursor': -1}, {'civ_id': ''}, {'arts_available': 1},
    {'owned_regions': ('',)}, {'conversion_observations': (Observation('Home', 1),) * 2},
    {'conversion_predicates': (Predicate('Home', 1, minimum_share=.8),) * 2} ])
def test_snapshot_rejects_invalid_contract(changes):
    with pytest.raises(ValueError):
        snapshot(**changes)


@pytest.mark.parametrize('changes', [ {'ambitions_per_ruler': 1}, {'ambitions_per_ruler': 4},
    {'minimum_duration': 19}, {'maximum_duration': 41}, {'minimum_duration': 40, 'maximum_duration': 20},
    {'completion_legitimacy': math.nan}, {'failure_legitimacy': -.1},
    {'weights': ((T.CONQUER_REGION, math.inf),)}, {'weights': ((T.CONQUER_REGION, -1.),)},
    {'weights': ((T.CONQUER_REGION, 1.),) * 2}, {'weights': (('conquer_region', 1.),)} ])
def test_calibration_rejects_invalid_contract(changes):
    with pytest.raises(ValueError):
        calibration(**changes)


@pytest.mark.parametrize('value', [-1., 1., math.nan, math.inf, True])
def test_selection_draws_reject_nonuniform_contract(value):
    with pytest.raises(ValueError):
        Draw(value, 0., 0.)


def test_invalid_religious_predicates_and_ambition_flags():
    for kwargs in ({}, {'minimum_share': 0.}, {'minimum_share': 1.1},
                   {'minimum_delta': 0}, {'minimum_share': .8, 'minimum_delta': 2}):
        with pytest.raises(ValueError):
            Predicate('Home', 1, **kwargs)
    with pytest.raises(ValueError):
        Predicate('Home', 255, minimum_share=.8)
    for construct in (lambda: goal(T.DIPLOMATIC_TRIUMPH),
                      lambda: goal(T.RELIGIOUS_CONVERSION),
                      lambda: goal(T.CONQUER_REGION, completed=True, failed=True),
                      lambda: goal(T.PATRON_OF_ARTS, target='Home'),
                      lambda: goal(T.CONQUER_REGION, deadline_turn=26)):
        with pytest.raises(ValueError):
            construct()
    with pytest.raises(ValueError):
        generate_ambitions(snapshot(), calibration(), draws(2))
    with pytest.raises(ValueError):
        reign(goal(T.CONQUER_REGION), goal(T.CONQUER_REGION))
    with pytest.raises(ValueError):
        reign(goal(T.CONQUER_REGION), accession_turn=8)


def test_fixed_draw_uses_roadmap_enum_index_before_weighted_selection():
    # Enum: conquer then build; lexical: build then conquer. The first
    # selection has the long deadline, exposing order independently of output sort.
    config = calibration(ambitions_per_ruler=2, weights=(
        (T.BUILD_MONUMENT, 1.), (T.CONQUER_REGION, 1.)))
    result = generate_ambitions(snapshot(), config,
        (Draw(0., 0., .999), Draw(0., 0., 0.)))
    assert [a.ambition_type for a in result] == [T.CONQUER_REGION, T.BUILD_MONUMENT]
    assert [a.deadline_turn for a in result] == [47, 27]
