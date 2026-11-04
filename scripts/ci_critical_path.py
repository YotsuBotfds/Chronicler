"""Opt-in offline timing analysis of saved official Chronicle Tests V2 metadata.

No network, environment discovery, artifact/log reads, or job-body execution.
The selected fixed DAG is an explicit source-profile assumption, not API proof.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys

MAX_INPUT = 2 * 1024 * 1024
PROFILE = 'chronicler-tests-v2'
NAMES = {
    'builder': 'Build one current-source native wheel',
    'shard0': 'Python native module shard 0', 'shard1': 'Python native module shard 1',
    'aggregate': 'Python native execution', 'rust': 'Rust', 'final': 'Python native',
    'offline': 'Python bounded offline', 'no_rust': 'Python no-Rust', 'viewer': 'Viewer',
}
# Fixed topological order; retain even the redundant direct builder→aggregate edge.
NEEDS = {'builder': (), 'shard0': ('builder',), 'shard1': ('builder',),
         'aggregate': ('builder', 'shard0', 'shard1'), 'rust': (),
         'final': ('aggregate', 'rust'), 'offline': (), 'no_rust': (), 'viewer': ()}
MAJOR_STEP = {'builder': 'Build Rust extension wheel',
              'shard0': 'Full default collection then owned module execution',
              'shard1': 'Full default collection then owned module execution',
              'offline': 'Run guarded offline chunks', 'no_rust': 'Run Python tests without Rust extension',
              'rust': 'Run Rust tests', 'viewer': 'Run viewer tests'}


class MetadataError(ValueError):
    """Input is inconsistent with the explicitly selected timing profile."""


def require(value, message):
    if not value:
        raise MetadataError(message)


def loads(text):
    """Bound and reject duplicate keys in saved API data or connector envelopes."""
    require(type(text) is str and len(text.encode('utf-8')) <= MAX_INPUT, 'JSON input exceeds2MiB')
    def pairs(rows):
        result = {}
        for key, value in rows:
            require(key not in result, 'duplicate JSON object key')
            result[key] = value
        return result
    try:
        return json.loads(text, object_pairs_hook=pairs)
    except (ValueError, RecursionError) as exc:
        raise MetadataError('invalid JSON metadata') from exc


def unwrap(value, key):
    for _ in range(4):
        require(type(value) is dict, 'metadata must be an object')
        if key in value:
            return value
        structured = value.get('structuredContent')
        require(type(structured) is dict, 'unsupported connector envelope')
        value = loads(structured['content']) if type(structured.get('content')) is str else structured
    raise MetadataError('connector envelope nesting exceeds4')


def stamp(value):
    require(type(value) is str, 'missing timestamp')
    try:
        result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError as exc:
        raise MetadataError('invalid timestamp') from exc
    require(result.tzinfo is not None and result.utcoffset().total_seconds() == 0, 'timestamp must be UTC')
    return result.astimezone(timezone.utc)


def seconds(end, start):
    return (end - start).total_seconds()


def lower_bound(durations):
    """Duration-only DAG bound: zero scheduling gaps, fixed measured durations."""
    finish, paths = {}, {}
    for role, needs in NEEDS.items():
        parent = max(needs, key=lambda n: finish[n]) if needs else None
        finish[role] = durations[role] + (finish[parent] if parent else 0)
        paths[role] = (paths[parent] if parent else []) + [role]
    last = max(finish, key=finish.get)
    return finish[last], paths[last]


def analyze(run, jobs, *, profile=PROFILE):
    require(profile == PROFILE, 'unknown workflow topology profile')
    run, jobs = unwrap(run, 'head_sha'), unwrap(jobs, 'jobs')
    require(type(run.get('id')) is int and run['id'] > 0 and
            type(run.get('run_attempt')) is int and run['run_attempt'] > 0, 'invalid run/attempt')
    require(type(run.get('head_sha')) is str and re.fullmatch('[0-9a-f]{40}', run['head_sha']), 'invalid source SHA')
    require(type(run.get('head_branch')) is str and bool(run['head_branch']), 'missing branch')
    require(run.get('path') == '.github/workflows/tests.yml', 'profile requires tests.yml')
    require(run.get('status') in ('queued', 'in_progress', 'completed'), 'invalid run status')
    origin, updated = stamp(run.get('created_at')), stamp(run.get('updated_at'))
    require(updated >= origin, 'run update predates creation')
    if run.get('run_started_at') is not None:
        require(origin <= stamp(run['run_started_at']) <= updated, 'invalid run start')
    entries = jobs.get('jobs')
    require(type(entries) is list and type(jobs.get('total_count')) is int and
            jobs['total_count'] == len(entries) <= len(NAMES), 'missing/incomplete job page or too many jobs')
    by_name = {name: role for role, name in NAMES.items()}
    rows, starts, ends, created, ids = {}, {}, {}, {}, set()
    for job in entries:
        require(type(job) is dict and type(job.get('id')) is int and job['id'] > 0 and job['id'] not in ids, 'duplicate/invalid job ID')
        ids.add(job['id']); require(type(job.get('name')) is str, 'invalid job name'); role = by_name.get(job['name'])
        require(role is not None and role not in rows, 'unknown or duplicate job role')
        require(job.get('run_id') == run['id'] and type(job.get('run_id')) is int and
                job.get('run_attempt') == run['run_attempt'] and type(job.get('run_attempt')) is int and
                job.get('head_sha') == run['head_sha'] and job.get('head_branch') == run['head_branch'], 'job run/source/attempt/branch join differs')
        state = job.get('status'); require(state in ('queued', 'in_progress', 'completed'), 'invalid job status')
        created[role] = stamp(job.get('created_at')); require(created[role] >= origin, 'job predates run')
        start = stamp(job['started_at']) if job.get('started_at') is not None else None
        end = stamp(job['completed_at']) if job.get('completed_at') is not None else None
        require((start is None or start >= created[role]) and (end is None or start is not None and end >= start), 'invalid job timestamp order')
        require((state == 'completed') == (end is not None) and (state != 'in_progress' or start is not None), 'job completion/start is inconsistent')
        require((state == 'completed' and type(job.get('conclusion')) is str and bool(job['conclusion'])) or
                (state != 'completed' and job.get('conclusion') is None), 'job conclusion is inconsistent')
        starts[role], ends[role] = start, end
        row = {'job_id': job['id'], 'name': NAMES[role], 'status': state, 'conclusion': job.get('conclusion'),
               'execution_seconds': seconds(end, start) if end is not None else None,
               'created_to_started_seconds': seconds(start, created[role]) if start is not None else None,
               'start_offset_seconds': seconds(start, origin) if start is not None else None,
               'major_step_seconds': None}
        steps = job.get('steps', []); require(type(steps) is list and len(steps) <= 128 and all(type(s) is dict for s in steps), 'invalid step metadata')
        selected = [s for s in steps if s.get('name') == MAJOR_STEP.get(role)]
        require(len(selected) <= 1, 'duplicate selected timing step')
        if selected and selected[0].get('completed_at') is not None:
            step = selected[0]; a, b = stamp(step.get('started_at')), stamp(step['completed_at'])
            require(start is not None and start <= a <= b and (end is None or b <= end), 'step lies outside job')
            row['major_step_seconds'] = seconds(b, a)
        rows[role] = row
    for role in rows:
        if starts[role] is not None:
            require(all(p in rows and ends[p] is not None and ends[p] <= starts[role] for p in NEEDS[role]), 'started job violates selected dependency profile')
            ready = max([origin, *[ends[p] for p in NEEDS[role]]])
            rows[role]['dependencies_ready_to_started_seconds'] = seconds(starts[role], ready)
    complete = run['status'] == 'completed'
    if complete:
        require(set(rows) == set(NAMES) and all(ends.values()), 'completed run lacks complete nine-role job set')
        require(type(run.get('conclusion')) is str and bool(run['conclusion']) and updated >= max(ends.values()), 'inconsistent terminal run metadata')
    else:
        require(run.get('conclusion') is None, 'nonterminal run has terminal conclusion')
    report = {'profile': PROFILE, 'profile_is_explicit_source_assumption_not_jobs_API_proof': True,
              'needs': {r: list(v) for r, v in NEEDS.items()}, 'source': run['head_sha'], 'branch': run['head_branch'],
              'run_id': run['id'], 'attempt': run['run_attempt'], 'analysis_state': 'COMPLETE_METADATA' if complete else 'PARTIAL_METADATA',
              'run_status': run['status'], 'run_conclusion': run.get('conclusion'),
              'roles': {r: rows[r] for r in NEEDS if r in rows}, 'missing_roles': [r for r in NEEDS if r not in rows],
              'observed_job_makespan_seconds': None, 'official_created_to_updated_seconds': seconds(updated, origin),
              'observed_critical_path': None, 'duration_only_lower_bound_seconds': None, 'what_if': None,
              'scope': 'Official timestamp attribution only, not CPU, controlled speedup, artifact/test qualification or inferred runner capacity.'}
    if not complete:
        return report  # No invented duration or completion claim for pending/missing roles.
    finish_role = max(ends, key=ends.get); path = [finish_role]
    while NEEDS[path[-1]]:
        path.append(max(NEEDS[path[-1]], key=lambda p: ends[p]))
    report['observed_critical_path'] = list(reversed(path))
    report['observed_job_makespan_seconds'] = seconds(ends[finish_role], origin)
    durations = {r: rows[r]['execution_seconds'] for r in NEEDS}
    bound, duration_path = lower_bound(durations)
    report.update(duration_only_lower_bound_seconds=bound, duration_only_critical_path=duration_path,
                  complete_job_wall_sum_seconds=sum(durations.values()),
                  scheduling_and_release_gap_seconds=report['observed_job_makespan_seconds'] - bound)
    if run['conclusion'] == 'success' and all(r['conclusion'] == 'success' for r in rows.values()):
        scenarios = {'assumption': 'Optimistic duration-only bounds; fixed other job durations, no scheduling gaps or controlled speedup claim.'}
        a, b = (rows[r]['major_step_seconds'] for r in ('shard0', 'shard1'))
        if a is not None and b is not None:
            balanced = dict(durations)
            for r, observed in (('shard0', a), ('shard1', b)):
                balanced[r] = durations[r] - observed + (a + b) / 2
            after, _ = lower_bound(balanced)
            scenarios['ideal_equal_shard_test_work'] = {'test_step_imbalance_seconds': abs(a-b), 'lower_bound_seconds': after,
                'duration_bound_improvement_seconds': bound-after, 'preserves_measured_total_test_work_assumption': True}
        wheel = rows['builder']['major_step_seconds']
        if wheel is not None:
            no_build = dict(durations); no_build['builder'] -= wheel
            after, _ = lower_bound(no_build)
            scenarios['zero_wheel_build_step_cost'] = {'removed_step_seconds': wheel, 'lower_bound_seconds': after,
                'duration_bound_improvement_seconds': bound-after, 'not_a_proposal_to_skip_build_or_admission': True}
        report['what_if'] = scenarios
    return report


def markdown(report):
    lines = [f"# {PROFILE}: saved metadata", '', f"Run {report['run_id']}, source `{report['source']}`: **{report['analysis_state']}**.",
             'Fixed source-profile DAG assumed; jobs API does not prove topology. No controlled speedup or CI qualification.', '',
             '| Role | Job execution s | Created→started s | Major step s |', '|---|---:|---:|---:|']
    for role, row in report['roles'].items():
        cell = lambda x: 'pending/absent' if x is None else f'{x:g}'
        lines.append(f"| {role} | {cell(row['execution_seconds'])} | {cell(row['created_to_started_seconds'])} | {cell(row['major_step_seconds'])} |")
    if report['analysis_state'] == 'PARTIAL_METADATA':
        lines += ['', 'Pending/missing roles have no invented durations or terminal result.']
    else:
        lines += ['', f"Observed job makespan: {report['observed_job_makespan_seconds']:g} s. Duration-only DAG lower bound: {report['duration_only_lower_bound_seconds']:g} s.",
                  'Observed critical path: ' + ' → '.join(report['observed_critical_path']) + '.', '', 'What-if values are optimistic bounds on these measurements, not measured improvements.',
                  '```json', json.dumps(report['what_if'], sort_keys=True, indent=2), '```']
    return '\n'.join(lines) + '\n'


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', required=True, type=Path); parser.add_argument('--jobs', required=True, type=Path)
    parser.add_argument('--format', choices=('json', 'markdown'), default='json')
    args = parser.parse_args(argv)
    try:
        def saved(path):
            with path.open('rb') as stream:
                raw = stream.read(MAX_INPUT + 1)
            require(len(raw) <= MAX_INPUT, 'JSON input exceeds2MiB')
            return loads(raw.decode('utf-8'))
        result = analyze(saved(args.run), saved(args.jobs))
        sys.stdout.write(markdown(result) if args.format == 'markdown' else json.dumps(result, sort_keys=True, indent=2, allow_nan=False) + '\n')
    except (MetadataError, OSError, UnicodeError) as exc:
        sys.stderr.write('metadata analysis refused: ' + str(exc)[:512] + '\n')
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
