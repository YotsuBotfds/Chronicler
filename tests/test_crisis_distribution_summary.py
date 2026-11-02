"""Checks analysis of recorded regional numbers, independent of simulations."""
import pytest
from scripts.crisis_distribution_summary import summarize


def food(turn, *regions):
    return {"source_turn":turn, "mode":"hybrid", "timing":"phase2", "regions":[
        {"region_id":rid, "native_count":10, "native":{"demand":demand,"sufficiency":suff}}
        for rid,demand,suff in regions]}


def test_regional_deficits_mean_improvement_and_recovery():
    summary = summarize([food(0, (0, 10, .5), (1, 10, 1.5)),
                         food(1, (0, 10, .6), (1, 10, 1.6)),
                         food(2, (0, 10, 1), (1, 10, 1.4)),
                         food(3, (0, 10, 1.1), (1, 10, 1.4))])
    assert summary['timeline'][0]['weighted_mean'] == pytest.approx(1)
    assert summary['timeline'][0]['regions'][0]['deficit'] == pytest.approx(.5)
    assert summary['first_sustained_recovery_by_region'] == {'0':2, '1':None}
    assert summary['first_sustained_sufficiency_by_region'] == {'0':2, '1':0}
    events = summary['mean_improved_with_regional_shortfall_or_decline']
    assert events[0]['below_one_regions'] == [0]
    assert events[1]['worsening_regions'] == [1]


def test_missing_and_zero_demand_not_misreported_or_compared():
    result = summarize([food(0, (0,10,.5),(1,0,2),(2,None,None)),
                        food(1, (0,10,.6),(1,1,2),(2,None,None)),
                        food(2, (0,10,.6),(1,0,2),(2,None,None))])
    assert result['timeline'][0]['region_coverage'] == pytest.approx(1/3)
    assert result['first_sustained_recovery_by_region']['1'] is None
    assert result['mean_improved_with_regional_shortfall_or_decline'] == []
    assert result['timeline'][0]['regions'][2]['deficit'] is None
