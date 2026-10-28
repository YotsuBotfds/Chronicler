"""Receipt arithmetic/chronology is distinct from efficacy and archive visibility."""
from __future__ import annotations
import copy
import json
import pytest
from chronicler.bundle_codec import dumps_bundle
from chronicler.expansion_audit import Limits, audit_bundle, audit_path, render_markdown
from chronicler.historical_context import AsOf


def event(turn, kind, causes=()):
    return dict(turn=turn, event_type=kind, event_id=f"{turn}:{kind}:0", causes=list(causes))


@pytest.fixture
def science_bundle():
    proposed = event(0, "scientific_claim_proposed")
    funded = event(0, "scientific_trial_funded", [proposed['event_id']])
    resolved = event(1, "scientific_trial_completed", [funded['event_id']])
    received = event(1, "scientific_evidence_received", [resolved['event_id']])
    allocated = event(2, "scientific_adoption_allocated", [received['event_id']])
    context = dict(crop="grain", soil_band=1, water_band=1, season=0,
                   climate_phase="temperate", crew=4, protocol="fixed-crew-grain-v1")
    proposition = dict(id=0, recipe="irrigation", origin_seat=7, proposed_turn=0,
                       context=context, threshold=.02, event_id=proposed['event_id'])
    trial = dict(id=0, claim=0, seat=7, payer=0, funded_turn=0, completion_turn=1,
        resolved_turn=1, cost=2, parent=-1, method="fixed-crew-grain-v1",
        inputs={'turn': 0, 'context': context}, control_output=10, treatment_output=10.5,
        observed_control=9.9, observed_treatment=10.4, informative=True, supports=True,
        status="completed", source_data="source-one", dependence_group="declared-one",
        funded_event_id=funded['event_id'], event_id=resolved['event_id'])
    history=[]
    for turn in range(4):
        belief=[] if turn == 0 else [dict(seat=7, seat_name="Academy <then>", region=1,
            region_name="Here", owner=0, owner_name="Then owner", claim=0,
            confidence=2/3 if turn==1 else .5, independent_groups=int(turn==1),
            last_evidence_turn=1 if turn==1 else None,
            last_evidence_event_id=received['event_id'] if turn==1 else "")]
        allocation=[] if turn < 2 else [dict(seat=7, region=1, recipe="irrigation", share=1.,
            confidence=.5, paid=1, event_id=allocated['event_id'] if turn==2 else "")]
        history.append({'turn':turn+1,'scientific_claims':dict(source_turn=turn,active=True,
            seats=1,claims=1,trials=1,completed=int(turn>=1),cancelled=0,failed=0,
            trial_spent=2,effort_spent=max(0,turn-1),evidence_receipts=int(turn>=1),
            pending_messages=0,expired_messages=0,withheld_results=0,
            controls=dict(withhold_information=False,transmission_enabled=True,uninformative_tests=False),
            propositions=[copy.deepcopy(proposition)], beliefs=belief,
            trials_resolved=[copy.deepcopy(trial)] if turn==1 else [],allocations=allocation)})
    return dict(metadata={'seed':42,'total_turns':4},world_state={'turn':4},history=history,
                events_timeline=[proposed,funded,resolved,received,allocated])


def section(bundle, turn):
    return bundle['history'][turn]['scientific_claims']


def codes(report):
    return {f['code'] for f in report['findings']}


def test_paid_measurement_archive_and_current_policy_are_separate(science_bundle):
    before=copy.deepcopy(science_bundle)
    report=audit_bundle(science_bundle)
    assert report['finding_counts']=={'error':0,'warning':0}
    assert report['scan_complete'] and science_bundle==before
    row=report['observed_mechanisms']['scientific_claims']
    assert row['funding_events']==row['evidence_receipt_events']==row['resolved_trial_receipts']==1
    assert row['costs_attached_to_resolved_trials']==2
    assert row['allocation_funds']==row['paid_seat_allocations']==2
    assert row['reported_allocation_events']==1  # routine second payment has no new event
    assert row['latest_cumulative_counters']['evidence_receipts']==1
    assert row['belief_details'][-1]['confidence']==.5
    assert row['belief_details'][-1]['last_used_receipt_turn'] is None
    assert row['publication_rules_observed']==['current-context-v1']
    assert row['unique_declared_dependence_groups']==1
    assert row['resolved_trial_details'][0]['archived_measurement']['observed_support'] is True
    assert row['resolved_trial_details'][0]['archived_measurement']['control_output']==10
    assert '<then>' not in render_markdown(report)
    assert any('not certified independent' in s for s in report['unobservable'])


def test_v6_single_read_source_identity_and_old_final_state_not_backfilled(science_bundle,tmp_path):
    path=tmp_path/'bundle.json';path.write_text(dumps_bundle(science_bundle))
    assert audit_path(path)['observed_mechanisms']==audit_bundle(science_bundle)['observed_mechanisms']
    old=dict(world_state={'turn':4,'scientific_claims':section(science_bundle,3)},history=[{'turn':4}])
    result=audit_bundle(old)
    assert result['status']=='no_recorded_expansion_history'
    assert result['observed_mechanisms']['scientific_claims']['resolved_trial_receipts']==0


@pytest.mark.parametrize('field,value,code',[
    ('trial_spent',-2,'negative_quantity'),('seats',.5,'fractional_science_count'),
    ('trials',41,'science_capacity_exceeded'),('completed',5,'resolved_counts_exceed_trials'),
    ('trial_spent',3,'trial_cost_total_mismatch'),('publication_rule','unknown','unknown_publication_rule')])
def test_negative_counts_caps_and_contracts(science_bundle,field,value,code):
    section(science_bundle,1)[field]=value
    assert code in codes(audit_bundle(science_bundle))


@pytest.mark.parametrize('table,datefield', [('propositions','proposed_turn'),
    ('trials_resolved','resolved_turn'),('beliefs','last_evidence_turn')])
def test_future_actual_rows_and_counters_are_withheld(science_bundle,table,datefield):
    row=section(science_bundle,1)[table][0]
    row.update({datefield:999,'seat_name':'SECRET_FUTURE','source_data':'SECRET_FUTURE'})
    report=audit_bundle(science_bundle,as_of=AsOf.after(1))
    assert any('future_or_undated' in c for c in codes(report))
    assert 'SECRET_FUTURE' not in json.dumps(report) and 'SECRET_FUTURE' not in render_markdown(report)
    assert report['observed_mechanisms']['scientific_claims']['latest_counter_source_turn']==0


def test_planned_future_completion_for_same_turn_failed_trial_is_allowed(science_bundle):
    row=section(science_bundle,1)['trials_resolved'][0]
    row.update(status='failed',funded_turn=1,completion_turn=99,inputs={},
               control_output=0,treatment_output=0,observed_control=None,observed_treatment=None,
               informative=False,supports=None,source_data='',dependence_group='')
    row['funded_event_id']='1:scientific_trial_funded:0'
    row['event_id']='1:scientific_trial_failed:0'
    science_bundle['events_timeline'][1].update(turn=1,event_id=row['funded_event_id'])
    science_bundle['events_timeline'][2].update(event_id=row['event_id'],event_type='scientific_trial_failed',causes=[row['funded_event_id']])
    section(science_bundle,0).update(trials=0,trial_spent=0)
    for t in range(1,4):
        section(science_bundle,t).update(completed=0,failed=1,evidence_receipts=0,beliefs=[])
    science_bundle['events_timeline']=[e for e in science_bundle['events_timeline'] if e['event_type']!='scientific_evidence_received']
    report=audit_bundle(science_bundle)
    assert report['finding_counts']=={'error':0,'warning':0}


@pytest.mark.parametrize('status,funded,planned,resolved',[
    ('completed',1,1,1),('completed',0,0,1),('completed',0,2,1),
    ('cancelled',1,1,1),('cancelled',0,0,1),('cancelled',0,2,1),
    ('failed',0,99,1),('failed',0,0,1)])
def test_terminal_chronology_rejects_same_turn_completion_or_premature_publication(science_bundle,status,funded,planned,resolved):
    row=section(science_bundle,1)['trials_resolved'][0]
    row.update(status=status,funded_turn=funded,completion_turn=planned,resolved_turn=resolved)
    assert 'inverted_trial_dates' in codes(audit_bundle(science_bundle))


def test_later_publication_failure_after_planned_completion_is_allowed(science_bundle):
    row=section(science_bundle,1)['trials_resolved'][0]
    row.update(status='failed',event_id='1:scientific_trial_failed:0')
    science_bundle['events_timeline'][2].update(event_id=row['event_id'],event_type='scientific_trial_failed')
    for turn in range(4):
        state=section(science_bundle,turn)
        state['publication_rule']='funded-context-v2'
        if turn>=1:state.update(completed=0,failed=1,evidence_receipts=0,beliefs=[])
    science_bundle['events_timeline']=[e for e in science_bundle['events_timeline'] if e['event_type']!='scientific_evidence_received']
    assert audit_bundle(science_bundle)['finding_counts']=={'error':0,'warning':0}


def test_future_duplicate_event_does_not_poison_historical_prefix(science_bundle):
    before=audit_bundle(science_bundle,as_of=AsOf.after(1))
    duplicate={**science_bundle['events_timeline'][1],'turn':99}
    science_bundle['events_timeline'].append(duplicate)
    assert audit_bundle(science_bundle,as_of=AsOf.after(1))==before


@pytest.mark.parametrize('measured',[None,999])
def test_future_or_undated_physical_input_identities_are_withheld(science_bundle,measured):
    row=section(science_bundle,1)['trials_resolved'][0]
    row['inputs']['turn']=measured
    row.update(source_data='SECRET_FUTURE',dependence_group='SECRET_FUTURE')
    result=audit_bundle(science_bundle,as_of=AsOf.after(1))
    assert 'future_or_undated_measurement_inputs' in codes(result)
    assert 'SECRET_FUTURE' not in json.dumps(result) and 'SECRET_FUTURE' not in render_markdown(result)
    assert result['observed_mechanisms']['scientific_claims']['latest_counter_source_turn']==0


def test_replay_and_changed_proposition_are_errors_not_repeated_trials(science_bundle):
    section(science_bundle,2)['trials_resolved']=copy.deepcopy(section(science_bundle,1)['trials_resolved'])
    section(science_bundle,3)['propositions'][0]['context']['season']=2
    report=audit_bundle(science_bundle)
    assert {'replayed_trial_resolution','changed_proposition_identity'}<=codes(report)
    assert report['observed_mechanisms']['scientific_claims']['resolved_trial_receipts']==1


def test_trial_links_check_recorded_dependencies_without_counterfactual_claim(science_bundle):
    good=audit_bundle(science_bundle)
    assert good['verified_checks']['scientific_claims.recorded_dependencies']['verified']==2
    science_bundle['events_timeline'][2]['causes']=[]
    assert 'missing_recorded_dependency' in codes(audit_bundle(science_bundle))


@pytest.mark.parametrize('change,code',[
    ('support','support_arithmetic_mismatch'),('inputs','funded_context_mismatch'),
    ('split','allocation_split_or_payment_mismatch'),('payment','allocation_split_or_payment_mismatch'),
    ('counter','science_counter_receipt_mismatch'),('regression','science_counter_regression'),
    ('belief','neutral_prior_mismatch')])
def test_receipt_arithmetic_and_paid_allocations(science_bundle,change,code):
    if change=='support':section(science_bundle,1)['trials_resolved'][0]['supports']=False
    elif change=='inputs':section(science_bundle,1)['trials_resolved'][0]['inputs']['turn']=1
    elif change=='split':section(science_bundle,2)['allocations'][0]['share']=.5
    elif change=='payment':section(science_bundle,2)['allocations'][0]['paid']=0
    elif change=='counter':section(science_bundle,2)['effort_spent']=7
    elif change=='regression':section(science_bundle,3)['evidence_receipts']=0
    else:section(science_bundle,2)['beliefs'][0]['confidence']=.9
    assert code in codes(audit_bundle(science_bundle))


def test_uninformative_arm_allows_unequal_noisy_observations(science_bundle):
    for t in range(4):section(science_bundle,t)['controls']['uninformative_tests']=True
    report=audit_bundle(science_bundle)
    assert report['finding_counts']=={'error':0,'warning':0}


def test_claimed_informative_zero_comparator_is_diagnostic_not_division(science_bundle):
    row=section(science_bundle,1)['trials_resolved'][0]
    row.update(informative=True,observed_control=0)
    result=audit_bundle(science_bundle)
    assert 'informative_flag_mismatch' in codes(result)
    json.dumps(result,allow_nan=False)


@pytest.mark.parametrize('kind',[[],{}])
def test_unrelated_unhashable_event_kind_does_not_crash_science_index(science_bundle,kind):
    science_bundle['events_timeline'].append(dict(event_id='unrelated',turn=0,event_type=kind))
    result=audit_bundle(science_bundle)
    assert result['finding_counts']=={'error':0,'warning':0}


def test_counters_do_not_bridge_unrecorded_spans(science_bundle):
    science_bundle['history']=[science_bundle['history'][0],science_bundle['history'][3]]
    section_last=science_bundle['history'][-1]['scientific_claims']
    section_last.update(evidence_receipts=0,effort_spent=0,allocations=[])
    result=audit_bundle(science_bundle)
    assert 'science_counter_regression' not in codes(result)
    assert result['coverage']['systems']['scientific_claims']['unknown_completed_turn_spans']==[[1,2]]


def test_bounds_never_claim_complete_and_details_are_explicit(science_bundle):
    limited=audit_bundle(science_bundle,limits=Limits(max_rows=1))
    assert not limited['scan_complete'] and limited['status']=='partial'
    details=audit_bundle(science_bundle,limits=Limits(max_details=1))
    assert details['scan_complete']
    assert details['details_omitted']['belief_details']==2


def test_missing_archive_rows_are_unknown_not_reconstructed(science_bundle):
    for s in science_bundle['history']:s['scientific_claims'].pop('trials_resolved')
    result=audit_bundle(science_bundle)
    assert result['verified_checks']['scientific_claims.trials_resolved_recorded']['unavailable']==4
    assert result['observed_mechanisms']['scientific_claims']['resolved_trial_receipts']==0
    assert any('full archive receipt list' in s for s in result['unobservable'])


def write_study(tmp_path, template):
    source={'source':{'git_sha':'a'*40,'package_digest':'b'*64},
            'native':{'status':'found','sha256':'d'*64}}
    env={'python':'3.13.5','implementation':'CPython','machine':'x86_64','hash_seed':'0',
         'packages':{'pydantic':'2.12.5'},'thread_env':{'RAYON_NUM_THREADS':'1'},'affinity_cpu_count':1}
    before=dict(withhold_information=False,transmission_enabled=True,uninformative_tests=False)
    results=[]
    for arm in ('parent','normal','withheld','no_transmission','uninformative'):
        data=copy.deepcopy(template)
        controls={**before,'withhold_information':arm=='withheld',
                  'transmission_enabled':arm!='no_transmission','uninformative_tests':arm=='uninformative'}
        receipt=dict(schema_version=1,experiment='science-development',feature='scientific_claims',
            cohort='development',seed=42,arm=arm,intervention_fork=arm!='parent',
            applied_before_turn=0 if arm=='parent' else 1,controls_before=before,controls_after=controls,
            registration=None,**source,parent_checkpoint=None if arm=='parent' else
            dict(sha256='c'*64,turn=1,seed=42,exact=True,identity={**source,'environment':env},
                 flags={'scientific_claims':True,'scholarship':True}))
        data['metadata']['expansion_experiment']=receipt
        for turn in range(1,4):
            state=section(data,turn);state['controls']=controls.copy()
            if arm=='withheld':
                state['evidence_receipts']=0;state['withheld_results']=1
                for belief in state['beliefs']:
                    belief.update(confidence=.5,independent_groups=0,last_evidence_turn=None,last_evidence_event_id='')
        if arm=='withheld':
            data['events_timeline']=[e for e in data['events_timeline'] if e['event_type']!='scientific_evidence_received']
        path=tmp_path/arm/'chronicle_bundle.json';path.parent.mkdir()
        path.write_text(dumps_bundle(data))
        (path.parent/'worker_identity.json').write_text(json.dumps(dict(before={**source,'environment':env},
            after={**source,'environment':env},environment_stable=True,identities_stable=True,
            runner_sha256='e'*64,runner_sha256_after='e'*64)))
        results.append(path)
    return results


def mutate(path, fn):
    from chronicler.bundle_codec import load_bundle
    data=load_bundle(path);fn(data);path.write_text(dumps_bundle(data))


def test_strict_science_comparator_matches_four_controls_and_postfork_scope(science_bundle,tmp_path):
    from chronicler.expansion_compare import compare_paths,render_markdown as compare_md
    paths=write_study(tmp_path,science_bundle)
    report=compare_paths(paths)
    assert report['summary']['matched_contrasts']==3 and report['summary']['blocked_contrasts']==0
    assert all(p['comparable_recorded_window'] for p in report['pairs'])
    normal=next(r for r in report['runs'] if r['arm']=='normal')
    assert normal['controls_after']['publication_rule']=='current-context-v1'
    assert normal['metrics']['funding_events']==0  # funded in the shared prefix
    assert normal['metrics']['costs_attached_to_resolved_trials']==2
    assert normal['metrics']['cumulative_trial_spent_change']==0
    assert normal['metrics']['cumulative_effort_spent_change']==2
    assert normal['metrics']['evidence_receipt_events']==1
    assert normal['window']=={'start':1,'end_exclusive':4}
    assert report['noop_checks'][0]['final_exported_python_world_equal']
    assert report['noop_checks'][0]['provenance_matched']
    assert 'current\\-context\\-v1' in compare_md(report)


@pytest.mark.parametrize('kind,blocker',[
    ('publication','publication_rule_mismatch'),('missing','incomplete_or_unknown_controls'),
    ('named','named_arm_control_mismatch'),('snapshot','science_snapshot_controls_mismatch'),
    ('gap','incomplete_treatment_window'),('rows','incomplete_feature_receipts')])
def test_science_comparison_refuses_semantic_or_record_gaps(science_bundle,tmp_path,kind,blocker):
    from chronicler.expansion_compare import compare_paths
    paths=write_study(tmp_path,science_bundle)
    def change(b):
        receipt=b['metadata']['expansion_experiment']
        if kind=='publication':
            receipt['controls_after']['publication_rule']='funded-context-v2'
            for t in range(1,4):section(b,t)['publication_rule']='funded-context-v2'
        elif kind=='missing':receipt['controls_after'].pop('transmission_enabled')
        elif kind=='named':receipt['controls_after']['withhold_information']=False
        elif kind=='snapshot':section(b,2)['controls']['withhold_information']=False
        elif kind=='gap':b['history'].pop(2)
        else:section(b,2).pop('allocations')
    mutate(paths[2],change)
    pair=next(p for p in compare_paths(paths)['pairs'] if p['arm']=='withheld')
    assert blocker in pair['blockers'] and not pair['comparable_recorded_window']
    assert pair['arm_minus_baseline'] is None


def test_science_comparison_unknown_counter_boundary_stays_null(science_bundle,tmp_path):
    from chronicler.expansion_compare import compare_paths
    paths=write_study(tmp_path,science_bundle)
    for path in paths:
        mutate(path,lambda b:b['history'][0].pop('scientific_claims'))
    normal=next(r for r in compare_paths(paths)['runs'] if r['arm']=='normal')
    assert normal['metrics']['cumulative_trial_spent_change'] is None
    assert normal['metrics']['costs_attached_to_resolved_trials']==2


def test_rejected_future_boundary_counters_never_leak_into_changes(science_bundle,tmp_path):
    from chronicler.expansion_compare import compare_paths
    paths=write_study(tmp_path,science_bundle)
    def future(b):
        state=section(b,0)
        state['propositions'][0]['proposed_turn']=99
        state['effort_spent']=1234567
    mutate(paths[1],future)
    result=compare_paths(paths)
    normal=next(r for r in result['runs'] if r['arm']=='normal')
    assert normal['metrics']['cumulative_effort_spent_change'] is None
    assert '1234567' not in json.dumps(result)
