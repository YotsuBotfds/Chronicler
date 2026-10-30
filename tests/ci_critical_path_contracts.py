"""Explicit-only pure timing contracts; deliberately absent from default collection."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import io
import json
from pathlib import Path

import pytest

from scripts.ci_critical_path import MetadataError, NAMES, analyze, loads, main, markdown


def example():
    zero = datetime(2026, 10, 30, tzinfo=timezone.utc)
    ts = lambda n: (zero + timedelta(seconds=n)).isoformat().replace('+00:00', 'Z')
    times = {'builder': (2, 12), 'shard0': (13, 35), 'shard1': (13, 45),
             'aggregate': (46, 49), 'rust': (2, 7), 'final': (50, 51),
             'offline': (2, 6), 'no_rust': (2, 22), 'viewer': (2, 6)}
    run = {'id': 100, 'run_attempt': 1, 'head_sha': 'a' * 40, 'head_branch': 'lead/example',
           'path': '.github/workflows/tests.yml', 'status': 'completed', 'conclusion': 'success',
           'created_at': ts(0), 'run_started_at': ts(0), 'updated_at': ts(52)}
    jobs = []
    for index, (role, (start, end)) in enumerate(times.items(), 1):
        job = {'id': index, 'name': NAMES[role], 'run_id': 100, 'run_attempt': 1,
               'head_sha': run['head_sha'], 'head_branch': run['head_branch'],
               'status': 'completed', 'conclusion': 'success', 'created_at': ts(start - 1),
               'started_at': ts(start), 'completed_at': ts(end), 'steps': []}
        if role in ('builder', 'shard0', 'shard1'):
            name = 'Build Rust extension wheel' if role == 'builder' else 'Full default collection then owned module execution'
            job['steps'] = [{'name': name, 'started_at': ts(start + 1), 'completed_at': ts(end - 1)}]
        jobs.append(job)
    return run, {'total_count': len(jobs), 'jobs': jobs}


def test_observed_path_bounds_and_exact_redundant_dependency():
    run, jobs = example(); before = deepcopy((run, jobs))
    report = analyze(run, jobs)
    assert (run, jobs) == before
    assert report['analysis_state'] == 'COMPLETE_METADATA'
    assert report['observed_critical_path'] == ['builder', 'shard1', 'aggregate', 'final']
    assert report['needs']['aggregate'] == ['builder', 'shard0', 'shard1']
    assert report['needs']['final'] == ['aggregate', 'rust']
    assert report['observed_job_makespan_seconds'] == 51
    assert report['duration_only_lower_bound_seconds'] == 46
    assert report['scheduling_and_release_gap_seconds'] == 5
    assert report['what_if']['ideal_equal_shard_test_work']['duration_bound_improvement_seconds'] == 5
    assert report['what_if']['zero_wheel_build_step_cost']['duration_bound_improvement_seconds'] == 8
    assert report['profile_is_explicit_source_assumption_not_jobs_API_proof'] is True


def test_parallel_lane_limits_optimistic_builder_benefit():
    run, jobs = example()
    # The parallel no-Rust lane becomes the limit after an ideal build improvement.
    no_rust = next(j for j in jobs['jobs'] if j['name'] == NAMES['no_rust'])
    no_rust['completed_at'] = '2026-10-30T00:00:44Z'
    report = analyze(run, jobs)
    assert report['duration_only_lower_bound_seconds'] == 46
    assert report['what_if']['zero_wheel_build_step_cost']['lower_bound_seconds'] == 42
    assert report['what_if']['zero_wheel_build_step_cost']['duration_bound_improvement_seconds'] == 4


def test_job_order_and_saved_connector_envelopes_do_not_change_results():
    run, jobs = example(); expected = analyze(run, jobs)
    jobs['jobs'].reverse()
    envelope = lambda value: {'structuredContent': {'content': json.dumps(value)}}
    assert analyze(envelope(envelope(run)), envelope(jobs)) == expected


@pytest.mark.parametrize('missing', [('aggregate', 'final'), ('shard0', 'shard1', 'aggregate', 'final')])
def test_partial_known_role_subsets_have_no_invented_remaining_time(missing):
    run, jobs = example(); run.update(status='in_progress', conclusion=None)
    jobs['jobs'] = [j for j in jobs['jobs'] if j['name'] not in {NAMES[r] for r in missing}]
    jobs['total_count'] = len(jobs['jobs'])
    report = analyze(run, jobs)
    assert report['analysis_state'] == 'PARTIAL_METADATA'
    assert report['missing_roles'] == [r for r in report['needs'] if r in missing]
    assert report['observed_job_makespan_seconds'] is None
    assert report['duration_only_lower_bound_seconds'] is None
    assert report['what_if'] is None
    assert 'no invented durations' in markdown(report)


def test_in_progress_job_and_older_run_update_are_valid_partial_snapshots():
    run, jobs = example(); run.update(status='in_progress', conclusion=None, updated_at='2026-10-30T00:00:20Z')
    jobs['jobs'] = [j for j in jobs['jobs'] if j['name'] not in {NAMES['aggregate'], NAMES['final']}]
    job = next(j for j in jobs['jobs'] if j['name'] == NAMES['shard1'])
    job.update(status='in_progress', conclusion=None, completed_at=None)
    job['steps'][0]['completed_at'] = None
    jobs['total_count'] = len(jobs['jobs'])
    report = analyze(run, jobs)
    assert report['roles']['shard1']['execution_seconds'] is None
    assert report['what_if'] is None


def test_queued_run_with_no_created_jobs_is_partial():
    run, _ = example(); run.update(status='queued', conclusion=None, run_started_at=None)
    report = analyze(run, {'jobs': [], 'total_count': 0})
    assert len(report['missing_roles']) == 9
    assert report['analysis_state'] == 'PARTIAL_METADATA'


@pytest.mark.parametrize('field,value', [('run_id', 101), ('run_attempt', 2), ('head_sha', 'b'*40), ('head_branch', 'other'), ('run_id', True)])
def test_job_source_run_attempt_and_branch_mismatch_refuses(field, value):
    run, jobs = example(); jobs['jobs'][0][field] = value
    with pytest.raises(MetadataError, match='join differs'):
        analyze(run, jobs)


@pytest.mark.parametrize('mutation', ['duplicate_id', 'duplicate_role', 'unknown_role', 'incomplete_page', 'terminal_missing', 'pending_in_terminal'])
def test_incomplete_or_ambiguous_job_sets_refuse(mutation):
    run, jobs = example()
    if mutation == 'duplicate_id': jobs['jobs'][1]['id'] = jobs['jobs'][0]['id']
    elif mutation == 'duplicate_role': jobs['jobs'][1]['name'] = jobs['jobs'][0]['name']
    elif mutation == 'unknown_role': jobs['jobs'][1]['name'] = 'another job'
    elif mutation == 'incomplete_page': jobs['total_count'] += 1
    elif mutation == 'terminal_missing': jobs['jobs'].pop(); jobs['total_count'] -= 1
    else: jobs['jobs'][1].update(status='in_progress', conclusion=None, completed_at=None)
    with pytest.raises(MetadataError): analyze(run, jobs)


@pytest.mark.parametrize('field,value', [('created_at', 'bad'), ('started_at', '2026-10-29T23:59:59Z'), ('completed_at', '2026-10-30T00:00:01Z'), ('started_at', '2026-10-30T00:00:02'), ('started_at', '2026-10-30T01:00:02+01:00')])
def test_bad_or_non_utc_job_timestamps_refuse(field, value):
    run, jobs = example(); jobs['jobs'][0][field] = value
    with pytest.raises(MetadataError): analyze(run, jobs)


def test_started_dependent_before_builder_completion_refuses():
    run, jobs = example(); jobs['jobs'][1]['created_at'] = jobs['jobs'][1]['started_at'] = '2026-10-30T00:00:11Z'
    with pytest.raises(MetadataError, match='dependency profile'): analyze(run, jobs)


def test_duplicate_major_step_or_step_outside_job_refuses():
    run, jobs = example(); jobs['jobs'][0]['steps'] *= 2
    with pytest.raises(MetadataError, match='duplicate selected'): analyze(run, jobs)
    run, jobs = example(); jobs['jobs'][0]['steps'][0]['completed_at'] = '2026-10-30T00:00:13Z'
    with pytest.raises(MetadataError, match='outside job'): analyze(run, jobs)


def test_failed_complete_run_has_timing_but_no_optimistic_success_comparison():
    run, jobs = example(); run['conclusion'] = jobs['jobs'][0]['conclusion'] = 'failure'
    report = analyze(run, jobs)
    assert report['observed_job_makespan_seconds'] == 51
    assert report['what_if'] is None


def test_missing_optional_step_timing_does_not_invent_build_savings():
    run, jobs = example(); jobs['jobs'][0]['steps'] = []
    report = analyze(run, jobs)
    assert 'zero_wheel_build_step_cost' not in report['what_if']


def test_job_body_fields_are_unused_data():
    run, jobs = example(); expected = analyze(run, jobs)
    jobs['jobs'][0]['run'] = "raise RuntimeError('job body must never execute')"
    assert analyze(run, jobs) == expected


@pytest.mark.parametrize('text', ['{"id":1,"id":2}', 'not JSON', '['*2000, ' '* (2*1024*1024+1)],
                         ids=['duplicate', 'invalid', 'too-deep', 'oversized'])
def test_invalid_duplicate_deep_or_oversized_json_refuses(text):
    with pytest.raises(MetadataError): loads(text)


def test_cli_reads_only_supplied_saved_files_and_renders_markdown(monkeypatch, capsys):
    run, jobs = example(); payloads = {'run.json': json.dumps(run).encode(), 'jobs.json': json.dumps(jobs).encode()}
    with monkeypatch.context() as patch:
        patch.setattr(Path, 'open', lambda path, mode: io.BytesIO(payloads[path.name]))
        assert main(['--run', 'run.json', '--jobs', 'jobs.json', '--format', 'markdown']) == 0
    output = capsys.readouterr()
    assert 'COMPLETE_METADATA' in output.out and 'Observed job makespan: 51 s' in output.out
    assert not output.err
