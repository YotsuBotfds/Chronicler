"""Pure fake-collection/report contracts; no real suite collection or native."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import importlib.util
import json
import sys

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/native_ci_shards.py'
SPEC = importlib.util.spec_from_file_location('native_shards_under_test', SCRIPT)
S = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = S
SPEC.loader.exec_module(S)


@pytest.fixture
def manifest():
    return {'schema_version': 1, 'shards': {'0': ['tests/test_a.py'], '1': ['tests/test_b.py']}, 'expected_skips': ['tests/test_b.py::test_x'], 'expected_successful_subtests': 2}


@pytest.fixture
def full():
    return ['tests/test_a.py::test_z', 'tests/test_a.py::TestC::test_a[p]', 'tests/test_b.py::test_x']


def parents(nodes, skipped=()):
    result = []
    for node in nodes:
        skip = node in skipped
        result.append({'nodeid': node, 'when': 'setup', 'outcome': 'skipped' if skip else 'passed'})
        if not skip:
            result.append({'nodeid': node, 'when': 'call', 'outcome': 'passed'})
        result.append({'nodeid': node, 'when': 'teardown', 'outcome': 'passed'})
    return result


def build_record(manifest):
    native = {'filename': 'native.so', 'bytes': 10, 'sha256': 'b'*64, 'wheel_member_sha256': 'b'*64}
    return {'kind': 'native-shard-current-build-v1', 'producer_job_key': 'python-native-build', 'manifest_digest': S.digest(manifest),
            'identity': {'source_commit': 'a'*40, 'source_tree_digest': 'c'*64, 'run_id': 10, 'attempt': 1,
                         'classes': ['AgentSimulator', 'EcologySimulator', 'PoliticsSimulator'], 'python': 'test-python',
                         'implementation': 'CPython', 'machine': 'fixture', 'package_scope': 'fixture packages', 'packages': {'pytest': '9'},
                         'wheel': {'schema_version': 1, 'source_commit': 'a'*40, 'installed_native': native,
                                   'wheel': {'filename': 'test.whl', 'bytes': 5, 'sha256': S.hashlib.sha256(b'wheel').hexdigest(), 'native_member': 'package/native.so'}}}}


def subtests(node, n=2):
    # Identical labels are legitimate, and must retain multiplicity/order.
    return [{'nodeid': node, 'when': 'call', 'outcome': 'passed', 'ordinal': i,
             'context': {'representation': S.CONTEXT_FORMAT, 'msg': "'same'", 'kwargs': "{'x': 1}"}} for i in range(n)]


def test_manifest_assigns_all_modules_once_and_preserves_collection_order(manifest, full):
    owners = S.validate_assignment(manifest, ['tests/test_b.py', 'tests/test_a.py'])
    assert S.selected_nodes(full, owners, '0') == full[:2]
    assert S.selected_nodes(full, owners, '1') == full[2:]


@pytest.mark.parametrize('change', ['new', 'missing', 'duplicate', 'empty', 'third', 'unsorted', 'bool_schema'])
def test_unknown_missing_duplicate_and_malformed_modules_refuse(manifest, change):
    actual = ['tests/test_a.py', 'tests/test_b.py']
    if change == 'new': actual.append('tests/test_new.py')
    elif change == 'missing': actual.pop()
    elif change == 'duplicate': manifest['shards']['1'].append('tests/test_a.py'); manifest['shards']['1'].sort()
    elif change == 'empty': manifest['shards']['0'] = []
    elif change == 'third': manifest['shards']['2'] = ['tests/test_c.py']
    elif change == 'unsorted': manifest['shards']['0'] = ['tests/test_z.py', 'tests/test_a.py']
    else: manifest['schema_version'] = True
    with pytest.raises(S.Refused): S.validate_assignment(manifest, actual)


@pytest.mark.parametrize('bad', ['../test_a.py', '/tests/test_a.py', 'tests/../test_a.py', 'tests//test_a.py', 'tests/./test_a.py', 'tests\\test_a.py', 'tests/test_\x00.py', 'tests/helper.py'])
def test_only_canonical_default_test_modules(bad):
    with pytest.raises(S.Refused): S.module_path(bad)


@pytest.mark.parametrize('change', ['duplicate', 'unknown', 'missing_module', 'empty'])
def test_bad_full_collection_refuses(manifest, full, change):
    owners = S.validate_assignment(manifest, ['tests/test_a.py', 'tests/test_b.py'])
    if change == 'duplicate': full.append(full[0])
    elif change == 'unknown': full.append('tests/test_new.py::test_x')
    elif change == 'missing_module': full = full[:2]
    else: full = []
    with pytest.raises(S.Refused): S.selected_nodes(full, owners, '0')


def test_real_parent_owns_repeated_subtest_contexts(full):
    reports = parents(full, skipped=full[2:])
    subs = subtests(full[0])
    assert S.validate_execution(full, reports, subs) == {'passed': 2, 'skipped': 1, 'successful_subtests': 2}
    assert len(subs) == 2 and subs[0]['context'] == subs[1]['context']


@pytest.mark.parametrize('change', ['missing_parent', 'duplicate_phase', 'unowned', 'reordered', 'failed_call', 'failed_teardown', 'call_after_skip', 'subtest_unowned', 'subtest_failed', 'subtest_lost_order'])
def test_incomplete_or_wrong_parent_subtest_execution_refuses(full, change):
    selected = full[:2]; reports = parents(selected); subs = subtests(selected[0])
    if change == 'missing_parent': reports = reports[:3]
    elif change == 'duplicate_phase': reports.append(deepcopy(reports[0]))
    elif change == 'unowned': reports[0]['nodeid'] = full[2]
    elif change == 'reordered': reports = reports[3:] + reports[:3]
    elif change == 'failed_call': reports[1]['outcome'] = 'failed'
    elif change == 'failed_teardown': reports[2]['outcome'] = 'failed'
    elif change == 'call_after_skip': reports[0]['outcome'] = 'skipped'
    elif change == 'subtest_unowned': subs[0]['nodeid'] = full[2]
    elif change == 'subtest_failed': subs[0]['outcome'] = 'skipped'
    else: subs.reverse()
    with pytest.raises(S.Refused): S.validate_execution(selected, reports, subs)


def test_plugin_keeps_modules_order_and_notifies_deselection(manifest, full):
    owners = S.validate_assignment(manifest, ['tests/test_a.py', 'tests/test_b.py'])
    p = S.ShardPlugin(owners, '0'); items = [SimpleNamespace(nodeid=n) for n in full]; dropped = []
    config = SimpleNamespace(hook=SimpleNamespace(pytest_deselected=lambda items: dropped.extend(items)))
    p.pytest_collection_modifyitems(None, config, items)
    p.pytest_collection_finish(SimpleNamespace(items=items))
    assert [i.nodeid for i in items] == full[:2]
    assert [i.nodeid for i in dropped] == full[2:]
    p.pytest_runtest_logreport(SimpleNamespace(**parents(full[:1])[0]))
    context = SimpleNamespace(msg='same', kwargs={}, _to_json=lambda: (_ for _ in ()).throw(AssertionError('raw context serialization forbidden')))
    for unused in range(2):
        p.pytest_runtest_logreport(SimpleNamespace(nodeid=full[0], when='call', outcome='passed', context=context))
    assert len(p.parents) == 1 and [r['ordinal'] for r in p.subtests] == [0, 1]


@pytest.mark.parametrize('change', ['collection_skip', 'selection_after_filter'])
def test_collection_errors_or_late_reordering_refuse(manifest, full, change):
    p = S.ShardPlugin(S.validate_assignment(manifest, ['tests/test_a.py', 'tests/test_b.py']), '0')
    p.selected = full[:2]; items = [SimpleNamespace(nodeid=n) for n in p.selected]
    if change == 'collection_skip': p.pytest_collectreport(SimpleNamespace(failed=False, skipped=True, nodeid='tests/test_a.py', outcome='skipped'))
    else: items.reverse()
    with pytest.raises(S.Refused): p.pytest_collection_finish(SimpleNamespace(items=items))


@pytest.fixture
def cohort(tmp_path, manifest, full):
    build = build_record(manifest)
    receipts, junits = [], []
    for shard, nodes in [('0', full[:2]), ('1', full[2:])]:
        skipped = nodes if shard == '1' else []
        subs = subtests(nodes[0]) if shard == '0' else []
        reports = parents(nodes, skipped)
        counts = S.validate_execution(nodes, reports, subs)
        j = tmp_path / f'{shard}.xml'
        addresses = {
            'tests/test_a.py::test_z': ('tests.test_a', 'test_z'),
            'tests/test_a.py::TestC::test_a[p]': ('tests.test_a.TestC', 'test_a[p]'),
            'tests/test_b.py::test_x': ('tests.test_b', 'test_x'),
        }
        j.write_text(f'<testsuites><testsuite tests="{len(nodes)+len(subs)}" skipped="{counts["skipped"]}">' + ''.join(f'<testcase classname="{addresses[n][0]}" name="{addresses[n][1]}">'+('<skipped/>' if n in skipped else '')+'</testcase>' for n in nodes) + '</testsuite></testsuites>')
        receipts.append({'state': 'PASS', 'exit_code': 0, 'shard': shard, 'identity': deepcopy(build['identity']),
                         'build_digest': S.digest(build), 'manifest_digest': S.digest(manifest), 'full_collection': full[:],
                         'selected': nodes[:], 'collection_errors': [], 'parents': reports, 'subtests': subs,
                         'counts': counts, 'junit_sha256': S.file_hash(j)})
        junits.append(j)
    return build, receipts, junits


def test_both_successful_shards_required_and_counts_separate(manifest, cohort):
    result = S.aggregate(*cohort, manifest)
    assert result['state'] == 'PASS'
    assert result['counts'] == {'passed': 2, 'skipped': 1, 'successful_subtests': 2}
    assert result['modules'] == 2


@pytest.mark.parametrize('change', ['missing', 'duplicate', 'failed', 'build', 'identity', 'manifest', 'full', 'selected', 'collection_error', 'counts', 'junit_hash', 'junit_count'])
def test_partial_mismatched_or_forged_shards_cannot_aggregate(manifest, cohort, change):
    build, receipts, junits = cohort
    if change == 'missing': receipts.pop(); junits.pop()
    elif change == 'duplicate': receipts[1]['shard'] = '0'
    elif change == 'failed': receipts[1]['exit_code'] = 1
    elif change == 'build': receipts[1]['build_digest'] = '0'*64
    elif change == 'identity': receipts[1]['identity']['wheel']['installed_native']['sha256'] = 'd'*64
    elif change == 'manifest': receipts[1]['manifest_digest'] = '0'*64
    elif change == 'full': receipts[1]['full_collection'].reverse()
    elif change == 'selected': receipts[0]['selected'].reverse()
    elif change == 'collection_error': receipts[1]['collection_errors'] = [{'nodeid': 'x'}]
    elif change == 'counts': receipts[1]['counts']['passed'] += 1
    elif change == 'junit_hash': receipts[1]['junit_sha256'] = '0'*64
    else:
        junits[1].write_text('<testsuites><testsuite tests="99" skipped="1"><testcase/></testsuite></testsuites>')
        receipts[1]['junit_sha256'] = S.file_hash(junits[1])
    with pytest.raises(S.Refused): S.aggregate(build, receipts, junits, manifest)


def test_checked_in_partition_preserves_historical_assignment_with_explicit_new_test():
    m = json.loads(S.MANIFEST.read_bytes())
    files = [name for names in m['shards'].values() for name in names]
    owners = S.validate_assignment(m, files)
    additions = {
        'tests/test_artifact_budget.py': '0',
        'tests/test_health_care_capture.py': '1',
        'tests/test_health_care_experiment_policy.py': '1',
        'tests/test_health_care_policy.py': '1',
        'tests/test_wealth_floor_outcome_checkpoints_v2.py': '1',
    }
    assert len(owners) == 305
    assert {name: owners[name] for name in additions} == additions
    old_owners = {name: shard for name, shard in owners.items() if name not in additions}
    assert len(old_owners) == 300
    # Canonical complete owner map from immutable parent 2572d5b9, including
    # the original shard-0 controller test. Equal counts alone allow moves.
    assert S.digest(old_owners) == 'fbde72231a68a0d4df1ca7f261501223df0fff6c3b6c14a99f337face13b26bb'
    assert owners['tests/test_native_ci_shards.py'] == '0'
    assert m['historical_module_counts'] == [159, 140]
    assert m['historical_partition_sha256'] == '0d4f05d3b53f5290f2cba3e6f6f4888a29de098cd0de6060f71a9f38a70d59cb'
    assert m['expected_skips'] == [
        'tests/test_m36_regression.py::TestInvestCultureAcceleration::test_invest_culture_directional',
        'tests/test_m38b_regression.py::TestFullCascade::test_full_cascade_end_to_end',
        'tests/test_m38b_regression.py::TestPilgrimageFrequency::test_pilgrimage_frequency_calibration',
        'tests/test_m51_legacy_integration.py::test_legacy_determinism',
        'tests/test_mutual_aid_adversarial.py::test_multiturn_disabled_matches_untouched_public_source_with_same_repaired_native',
        'tests/test_turn_artifact_lifecycle.py::test_str_wrapper_does_not_retain_view_after_return',
    ]
    # Preserve the qualified care seal: historical 526 plus policy source's 97.
    assert m['expected_successful_subtests'] == 623


@pytest.mark.parametrize('change', ['source', 'run_bool', 'attempt_missing', 'tree', 'producer', 'manifest', 'native', 'classes', 'packages', 'wheel_size', 'wheel_name'])
def test_incomplete_or_cross_source_builder_refuses(manifest, change):
    build = build_record(manifest); i = build['identity']
    if change == 'source': i['source_commit'] = 'short'
    elif change == 'run_bool': i['run_id'] = True
    elif change == 'attempt_missing': i.pop('attempt')
    elif change == 'tree': i['source_tree_digest'] = None
    elif change == 'producer': build['producer_job_key'] = 'other'
    elif change == 'manifest': build['manifest_digest'] = '0'*64
    elif change == 'native': i['wheel']['installed_native']['wheel_member_sha256'] = 'd'*64
    elif change == 'classes': i['classes'].pop()
    elif change == 'packages': i['packages'] = {}
    elif change == 'wheel_size': i['wheel']['wheel']['bytes'] = True
    else: i['wheel']['wheel']['filename'] = '../bad.whl'
    with pytest.raises(S.Refused): S.validate_build_record(build, manifest)


@pytest.mark.parametrize('change', ['none', 'run', 'attempt', 'source', 'tree', 'bytes', 'extra_wheel'])
def test_content_source_and_current_producer_checked_before_install(tmp_path, monkeypatch, manifest, change):
    build = build_record(manifest); wheel = tmp_path/'test.whl'; wheel.write_bytes(b'wheel')
    monkeypatch.setenv('GITHUB_SHA', 'a'*40); monkeypatch.setenv('GITHUB_RUN_ID', '10'); monkeypatch.setenv('GITHUB_RUN_ATTEMPT', '1')
    monkeypatch.setattr(S, 'git', lambda *args: ('a'*40+'\n').encode())
    monkeypatch.setattr(S, 'source_tree_digest', lambda: 'c'*64)
    if change == 'run': monkeypatch.setenv('GITHUB_RUN_ID', '9')
    elif change == 'attempt': monkeypatch.setenv('GITHUB_RUN_ATTEMPT', '2')
    elif change == 'source': monkeypatch.setenv('GITHUB_SHA', 'd'*40)
    elif change == 'tree': monkeypatch.setattr(S, 'source_tree_digest', lambda: 'd'*64)
    elif change == 'bytes': wheel.write_bytes(b'other')
    elif change == 'extra_wheel': (tmp_path/'extra.whl').write_bytes(b'wheel')
    if change == 'none': assert S.verify_transfer(build, tmp_path, manifest) == build['identity']
    else:
        with pytest.raises(S.Refused): S.verify_transfer(build, tmp_path, manifest)


def test_junit_same_count_wrong_nodes_refuses(manifest, cohort):
    build, receipts, junits = cohort
    junits[0].write_text(junits[0].read_text().replace('test_z', 'test_other'))
    receipts[0]['junit_sha256'] = S.file_hash(junits[0])
    with pytest.raises(S.Refused, match='ownership'): S.aggregate(build, receipts, junits, manifest)


def test_dormant_requires_explicit_opt_in(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, 'argv', ['native_ci_shards.py', 'check-manifest', '--output', str(tmp_path/'uncreated.json')])
    with pytest.raises(S.Refused, match='explicit execution'): S.main()
    assert not (tmp_path/'uncreated.json').exists()


def test_dormant_workflow_preserves_other_full_gates_and_blocks_partial_native():
    import hashlib
    import yaml
    root = SCRIPT.parents[1]
    # Historical prototype contract; direct current Tests graph/delegation
    # checks live in test_native_build_lanes and test_native_wheel_receipt.
    historical = root/'tests/fixtures/ci/standard-tests-cbf6e368.yml'
    assert hashlib.sha256(historical.read_bytes()).hexdigest() == '2dc117396d676801153d4458a12d9fdd0021b80268099b85e35f00b7b6b423b1'
    old = yaml.load(historical.read_text(), Loader=yaml.BaseLoader)
    new = yaml.load((root/'docs/workflows/native-two-shards.yml.in').read_text(), Loader=yaml.BaseLoader)
    assert new['on']['push'] == {'branches': ['lead/native-two-shard-qualification-20261029'], 'paths': ['.github/workflows/native-two-shards.yml']}
    branch = "github.ref == 'refs/heads/lead/native-two-shard-qualification-20261029'"
    for job in ('python-offline', 'python-no-rust', 'rust', 'viewer'):
        body = deepcopy(new['jobs'][job]); assert body.pop('if') == branch
        assert body == old['jobs'][job]
    builder = new['jobs']['python-native-build']
    assert builder['if'] == branch
    old_steps = old['jobs']['python-native-tests']['steps']
    expected_preflight = next(step for step in old_steps if step['name'] == 'Check turn-wrapper contracts before the full suite')
    assert expected_preflight in builder['steps']
    assert next(step for step in old_steps if step['name'] == 'Build Rust extension wheel') in builder['steps']
    shards = new['jobs']['python-native-tests']
    assert shards['strategy'] == {'fail-fast': 'false', 'matrix': {'shard': ['0', '1']}}
    assert shards['needs'] == ['python-native-build']
    prepare = next(step for step in shards['steps'] if step['name'] == 'Create private directories before Python starts')
    assert all(name+'=$private_root/' in prepare['run'] for name in S.PRIVATE_ENV)
    assert '>> "$GITHUB_ENV"' in prepare['run']
    names = [step['name'] for step in shards['steps']]
    assert names.index('Create private directories before Python starts') < names.index('Set up Python')
    assert names.index('Verify source producer and whole wheel before install') < names.index('Install the same verified current-source wheel') < names.index('Full default collection then owned module execution')
    barrier = new['jobs']['python-native-shard-aggregate']
    assert barrier['if'] == 'always() && '+branch
    assert barrier['needs'] == ['python-native-build', 'python-native-tests']
    assert new['jobs']['python-native']['needs'] == ['python-native-shard-aggregate', 'rust']
    downloads = [s['with']['name'] for s in barrier['steps'] if s.get('uses') == 'actions/download-artifact@v4']
    assert downloads == [stem+'-${{ github.run_id }}-${{ github.run_attempt }}' for stem in ('native-shard-build', 'native-module-shard-0', 'native-module-shard-1')]


@pytest.mark.parametrize('change', ['skip', 'subtests', 'junit_skip'])
def test_unexpected_skip_or_lost_subtest_stream_refuses(manifest, cohort, change):
    build, receipts, junits = cohort
    if change == 'skip':
        manifest['expected_skips'] = []
    elif change == 'subtests':
        manifest['expected_successful_subtests'] = 3
    else:
        junits[1].write_text(junits[1].read_text().replace('<skipped/>', ''))
        receipts[1]['junit_sha256'] = S.file_hash(junits[1])
    if change != 'junit_skip':
        build['manifest_digest'] = S.digest(manifest)
        for receipt in receipts:
            receipt['build_digest'] = S.digest(build)
            receipt['manifest_digest'] = S.digest(manifest)
    with pytest.raises(S.Refused): S.aggregate(build, receipts, junits, manifest)


@pytest.mark.parametrize('change', ['none', 'alias', 'outside'])
def test_private_evidence_paths_are_distinct_and_owned(tmp_path, monkeypatch, change):
    output = tmp_path/'owned'
    for index, name in enumerate(S.PRIVATE_ENV): monkeypatch.setenv(name, str(output/f'private-{index}'))
    if change == 'alias': monkeypatch.setenv('R007_EVIDENCE_DIR', str(output/'private-1'))
    elif change == 'outside': monkeypatch.setenv('TMPDIR', str(tmp_path/'outside'))
    if change == 'none':
        S.private_paths(output)
        assert all(Path(S.os.environ[name]).is_dir() for name in S.PRIVATE_ENV)
    else:
        with pytest.raises(S.Refused): S.private_paths(output)


class ContextPolicy:
    def __init__(self, scale):
        self.scale = scale

    def __repr__(self):
        return f'ContextPolicy(scale={self.scale!r})'

    def __deepcopy__(self, memo):
        raise AssertionError('diagnostic display must not deepcopy labels')


class ContextReprError:
    def __repr__(self):
        raise RuntimeError('fixture repr failure')


@pytest.mark.parametrize('kind', ['inf', 'negative_inf', 'nan', 'bytes', 'policy', 'repr_error', 'cycle', 'unicode', 'long'])
def test_raw_pytest_9_0_context_values_become_bounded_display_only(kind):
    import math
    cycle = []; cycle.append(cycle)
    values = {'inf': math.inf, 'negative_inf': -math.inf, 'nan': math.nan,
              'bytes': b'\x00raw\xff', 'policy': ContextPolicy(math.inf),
              'repr_error': ContextReprError(), 'cycle': cycle, 'unicode': '\U0001f30d'*4000, 'long': 'x'*8000}
    raw = values[kind]
    context = SimpleNamespace(msg=raw, kwargs={'value': raw},
        _to_json=lambda: (_ for _ in ()).throw(AssertionError('9.0 asdict path forbidden')))
    display = S.context_display(context)
    assert display['representation'] == S.CONTEXT_FORMAT
    assert type(display['msg']) is type(display['kwargs']) is str
    assert len(display['msg']) <= S.CONTEXT_MSG_CHARS and len(display['kwargs']) <= S.CONTEXT_KWARGS_CHARS
    assert len(S.canonical(display)) <= S.CONTEXT_JSON_BYTES
    assert json.loads(S.canonical(display)) == display
    if kind == 'repr_error': assert 'raised in repr()' in display['kwargs']
    if kind in ('inf', 'negative_inf', 'nan'): assert repr(raw) in display['kwargs']
    if kind == 'bytes': assert 'raw' in display['kwargs']
    if kind in ('long', 'unicode'): assert '...' in display['kwargs']


def test_context_capture_freezes_mutable_labels_and_preserves_repeated_reports(manifest, full):
    owners = S.validate_assignment(manifest, ['tests/test_a.py', 'tests/test_b.py'])
    plugin = S.ShardPlugin(owners, '0')
    labels = {'values': [1]}
    context = SimpleNamespace(msg='same', kwargs=labels)
    report = SimpleNamespace(nodeid=full[0], when='call', outcome='passed', context=context)
    plugin.pytest_runtest_logreport(report)
    first = deepcopy(plugin.subtests[0]['context'])
    labels['values'].append(2)
    plugin.pytest_runtest_logreport(report)
    plugin.pytest_runtest_logreport(report)
    assert plugin.subtests[0]['context'] == first
    assert plugin.subtests[1]['context'] == plugin.subtests[2]['context'] != first
    assert [r['ordinal'] for r in plugin.subtests] == [0, 1, 2]
    assert all(r['nodeid'] == full[0] and r['outcome'] == 'passed' for r in plugin.subtests)


@pytest.mark.parametrize('change', ['format', 'missing', 'extra', 'msg_type', 'kwargs_type', 'msg_bound', 'kwargs_bound'])
def test_context_display_contract_cannot_carry_raw_authority_values(change):
    context = {'representation': S.CONTEXT_FORMAT, 'msg': 'None', 'kwargs': '{}'}
    if change == 'format': context['representation'] = 'lossless-input'
    elif change == 'missing': context.pop('msg')
    elif change == 'extra': context['raw'] = b'raw'
    elif change == 'msg_type': context['msg'] = float('inf')
    elif change == 'kwargs_type': context['kwargs'] = {'value': 1}
    elif change == 'msg_bound': context['msg'] = 'x'*(S.CONTEXT_MSG_CHARS+1)
    else: context['kwargs'] = 'x'*(S.CONTEXT_KWARGS_CHARS+1)
    with pytest.raises(S.Refused): S.validate_context_display(context)


@pytest.mark.parametrize('value', [float('inf'), -float('inf'), float('nan')])
def test_authority_json_nonfinite_refusal_is_not_relaxed(value):
    with pytest.raises(ValueError): S.canonical({'identity': {'value': value}})
    assert 'value' in S.context_display(SimpleNamespace(msg=None, kwargs={'value': value}))['kwargs']


def test_actual_installed_pytest_context_uses_display_without_to_json(monkeypatch, tmp_path):
    from dataclasses import dataclass
    import hashlib
    from importlib import metadata
    import os
    import _pytest.subtests as native_pytest_context
    import _pytest._io.saferepr as native_pytest_display

    @dataclass
    class RawPolicy:
        scale: float
        payload: object
        def __deepcopy__(self, memo):
            raise AssertionError('raw label must not be deepcopied')

    cycle = []; cycle.append(cycle)
    policy = RawPolicy(float('inf'), b'raw-context')
    context = native_pytest_context.SubtestContext(msg=float('inf'), kwargs={
        'bytes': b'raw-context', 'policy': policy, 'nan': float('nan'), 'cycle': cycle, 'repr_error': ContextReprError()})
    monkeypatch.setattr(native_pytest_context.SubtestContext, '_to_json',
                        lambda self: (_ for _ in ()).throw(AssertionError('raw asdict path forbidden')))
    display = S.context_display(context)
    assert json.loads(S.canonical(display)) == display and 'raw-context' in display['kwargs']
    assert type(display['msg']) is type(display['kwargs']) is str
    # Real parent/ordinal/status metadata still passes strict JSON and ownership.
    node = 'tests/test_a.py::test_x'
    plugin = S.ShardPlugin({'tests/test_a.py': '0'}, '0')
    plugin.pytest_runtest_logreport(SimpleNamespace(nodeid=node, when='call', outcome='passed', context=context))
    assert S.validate_execution([node], parents([node]), plugin.subtests) == {'passed': 1, 'skipped': 0, 'successful_subtests': 1}
    assert json.loads(S.canonical(plugin.subtests))[0]['ordinal'] == 0
    destination = os.environ.get('SHARD_CONTEXT_METADATA_REPORT')
    if destination:
        result = {'pytest_version': metadata.version('pytest'), 'representation': display,
                  'subtests_source_sha256': hashlib.sha256(Path(native_pytest_context.__file__).read_bytes()).hexdigest(),
                  'saferepr_source_sha256': hashlib.sha256(Path(native_pytest_display.__file__).read_bytes()).hexdigest(),
                  'scope': 'Actual installed context class, scalar/report surrogates only; no suite collection/World/native runtime'}
        Path(destination).write_text(json.dumps(result, indent=2)+'\n')


def test_v2_template_changes_only_closed_registration_and_preserves_failed_v1():
    import hashlib
    root = SCRIPT.parents[1]
    old = (root/'docs/workflows/native-two-shards.yml.in').read_bytes()
    active_old = (root/'.github/workflows/native-two-shards.yml').read_bytes()
    assert old == active_old and hashlib.sha256(old).hexdigest() == '3941604d9bc3f357360f77beb3b93efca4d90faebca8a3469dbcde1b6263dfce'
    expected = old.replace(b'lead/native-two-shard-qualification-20261029', b'lead/native-two-shard-qualification-v2-20261029').replace(b'.github/workflows/native-two-shards.yml', b'.github/workflows/native-two-shards-v2.yml').replace(b'name: Dormant native module shard qualification', b'name: Dormant native module shard qualification V2')
    prepared = (root/'docs/workflows/native-two-shards-v2.yml.in').read_bytes()
    assert prepared == expected
    installed = root/'.github/workflows/native-two-shards-v2.yml'
    if installed.exists(): assert installed.read_bytes() == prepared


@pytest.fixture
def ref_git(monkeypatch, manifest):
    """Finite Git protocol double: no process, source import or real collection."""
    reference, tree, blob = 'a'*40, 'b'*40, 'c'*40
    raw = json.dumps(manifest, indent=2).encode() + b'\n'
    manifest_path = 'scripts/testing/native_shards_manifest.json'
    rows = [(b'100644', b'blob', blob.encode(), manifest_path.encode()),
            (b'100644', b'blob', b'd'*40, b'tests/test_a.py'),
            (b'100755', b'blob', b'e'*40, b'tests/test_b.py'),
            (b'100644', b'blob', b'f'*40, b'tests/helper.py')]
    state = {'reference': reference, 'tree': tree, 'blob': blob, 'raw': raw,
             'rows': rows, 'calls': [], 'kind': b'commit\n'}

    monkeypatch.setenv('GIT_NO_LAZY_FETCH', '0')

    def fake_git(command, *, cwd, env):
        assert command[0] == 'git' and cwd == S.ROOT
        assert env['GIT_NO_LAZY_FETCH'] == '1' and S.os.environ['GIT_NO_LAZY_FETCH'] == '0'
        args = tuple(command[1:])
        state['calls'].append(args)
        assert args[0] == '--no-replace-objects'
        if args[1:] == ('cat-file', '-t', reference): return state['kind']
        if args[1:] == ('rev-parse', '--verify', reference+'^{tree}'): return (tree+'\n').encode()
        if args[1:] == ('ls-tree', '-r', '-z', '--full-tree', tree, '--', manifest_path, 'tests'):
            return b''.join(b' '.join(row[:3])+b'\t'+row[3]+b'\0' for row in state['rows'])
        if args[1:] == ('cat-file', '-s', blob): return (str(len(state['raw']))+'\n').encode()
        if args[1:] == ('cat-file', 'blob', blob): return state['raw']
        raise AssertionError(('unregistered Git request', args))

    monkeypatch.setattr(S.subprocess, 'check_output', fake_git)
    # A sparse view's index, physical manifest and current source must not leak in.
    def no_current(*args): raise AssertionError('current checkout is not the requested Git commit')
    monkeypatch.setattr(S, 'read_json', no_current)
    monkeypatch.setattr(S, 'source_modules', no_current)
    return state


def test_source_ref_cli_reads_manifest_and_default_modules_from_same_immutable_tree(ref_git, monkeypatch, tmp_path, manifest):
    destination = tmp_path/'ref.json'
    monkeypatch.setattr(sys, 'argv', ['native_ci_shards.py', 'check-manifest', '--execute',
        '--source-ref', ref_git['reference'], '--output', str(destination)])
    S.main()
    record = json.loads(destination.read_bytes())
    assert record == {'state': 'PASS', 'source_ref': ref_git['reference'],
        'source_commit': ref_git['reference'], 'source_tree': ref_git['tree'],
        'scope': 'Git manifest/default test-module layout only; no pytest collection, execution or producer/wheel admission',
        'manifest_path': 'scripts/testing/native_shards_manifest.json', 'manifest_blob': ref_git['blob'],
        'manifest_sha256': S.hashlib.sha256(ref_git['raw']).hexdigest(),
        'manifest_digest': S.digest(manifest), 'modules': 2}
    assert len(ref_git['calls']) == 5


@pytest.mark.parametrize('change', ['new', 'missing', 'duplicate_owner', 'wrong_ref_manifest', 'duplicate_source',
                                    'missing_manifest', 'symlink_manifest', 'symlink_module'])
def test_source_ref_layout_mismatch_refuses_before_output(ref_git, monkeypatch, tmp_path, manifest, change):
    rows = ref_git['rows']
    if change == 'new': rows.append((b'100644', b'blob', b'f'*40, b'tests/test_new.py'))
    elif change == 'missing': rows.pop(2)
    elif change == 'duplicate_owner':
        manifest['shards']['1'] = ['tests/test_a.py', 'tests/test_b.py']
        ref_git['raw'] = S.canonical(manifest)
    elif change == 'wrong_ref_manifest':
        manifest['shards']['1'] = ['tests/test_old.py']
        ref_git['raw'] = S.canonical(manifest)
    elif change == 'duplicate_source': rows.append(rows[1])
    elif change == 'missing_manifest': rows.pop(0)
    elif change == 'symlink_manifest': rows[0] = (b'120000', *rows[0][1:])
    else: rows[1] = (b'120000', *rows[1][1:])
    destination = tmp_path/'uncreated.json'
    monkeypatch.setattr(sys, 'argv', ['native_ci_shards.py', 'check-manifest', '--execute',
        '--source-ref', ref_git['reference'], '--output', str(destination)])
    with pytest.raises(S.Refused): S.main()
    assert not destination.exists()


@pytest.mark.parametrize('reference', ['HEAD', 'main', 'a'*39, 'a'*41, 'A'*40, '-'+ 'a'*39, 'a'*40+'^{tree}', '', None, True])
def test_source_ref_requires_literal_full_lowercase_commit_before_git(ref_git, reference):
    with pytest.raises(S.Refused, match='full lowercase 40-hex'): S.check_ref_manifest(reference)
    assert ref_git['calls'] == []


@pytest.mark.parametrize('kind', [b'tree\n', b'tag\n', b'blob\n'])
def test_source_ref_must_name_a_commit_not_another_object(ref_git, kind):
    ref_git['kind'] = kind
    with pytest.raises(S.Refused, match='not a commit'): S.check_ref_manifest(ref_git['reference'])
    assert len(ref_git['calls']) == 1


def test_unavailable_source_ref_refuses_without_physical_fallback(ref_git, monkeypatch):
    def missing(*args, **kwargs): raise S.subprocess.CalledProcessError(128, args[0])
    monkeypatch.setattr(S.subprocess, 'check_output', missing)
    with pytest.raises(S.Refused, match='Git metadata unavailable'): S.check_ref_manifest(ref_git['reference'])


@pytest.mark.parametrize('command', ['record-build', 'verify-transfer', 'run', 'aggregate'])
def test_source_ref_is_illegal_for_every_producer_and_runtime_command(ref_git, monkeypatch, tmp_path, command):
    destination = tmp_path/'uncreated.json'
    monkeypatch.setattr(sys, 'argv', ['native_ci_shards.py', command, '--execute',
        '--source-ref', ref_git['reference'], '--output', str(destination)])
    with pytest.raises(S.Refused, match='only valid with check-manifest'): S.main()
    assert ref_git['calls'] == [] and not destination.exists()


def test_no_ref_check_manifest_preserves_original_current_path_and_output_bytes(monkeypatch, tmp_path, manifest):
    calls = []
    def read_current(path):
        assert path == S.MANIFEST
        calls.append('physical manifest')
        return manifest
    def current_modules():
        calls.append('current index')
        return ['tests/test_b.py', 'tests/test_a.py']
    def no_ref(*args): raise AssertionError('optional Git-ref path was invoked')
    monkeypatch.setattr(S, 'read_json', read_current)
    monkeypatch.setattr(S, 'source_modules', current_modules)
    monkeypatch.setattr(S, 'check_ref_manifest', no_ref)
    destination = tmp_path/'current.json'
    monkeypatch.setattr(sys, 'argv', ['native_ci_shards.py', 'check-manifest', '--execute', '--output', str(destination)])
    S.main()
    assert calls == ['physical manifest', 'current index']
    assert destination.read_bytes() == S.canonical({'state': 'PASS', 'manifest_digest': S.digest(manifest), 'modules': 2})


# Native release cache pure contracts. The full old module above is unchanged.
# These new cases are selectable by -k release_cache for a later guarded gate.
@pytest.fixture
def release_cache_api():
    path = SCRIPT.with_name('native_release_cache.py')
    spec = importlib.util.spec_from_file_location('native_release_cache_under_test', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def release_cache_case(release_cache_api):
    C = release_cache_api
    def row(name, stamp=10, payload=b'x'):
        return {'path': name, 'mode': 0o644, 'bytes': len(payload),
                'sha256': C.hashlib.sha256(payload).hexdigest(), 'mtime_ns': stamp,
                'links': 1, 'inode_group': name}
    source = [row('chronicler-agents/build.rs'), row('chronicler-agents/src/lib.rs')]
    release = [row(C.RELEASE+'/.fingerprint/chronicler-agents-abc/invoked.timestamp', 100),
               row(C.RELEASE+'/libchronicler_agents.so', 100)]
    pin = {'resolved_path': '/synthetic/tool', 'files': C.content_rows([row('tool')])}
    context = {'schema': C.CONTEXT_VERSION, 'helper_sha256': 'c'*64, 'workspace': '/synthetic/source',
               'cargo_home': '/synthetic/cargo', 'public_env': {}, 'argv': C.BUILD_ARGV,
               'features': C.FEATURES, 'tools': {k: deepcopy(pin) for k in ('rustc', 'cargo', 'cc', 'ld', 'ar', 'maturin', 'ldd')},
               'rustc': 'synthetic-rust', 'cargo': 'synthetic-cargo', 'linker': 'synthetic-linker',
               'cc': 'synthetic-cc', 'sysroot_path': '/synthetic/sysroot', 'sysroot_files': C.content_rows([row('lib/tool')]),
               'maturin_version': 'synthetic', 'python': 'synthetic CPython', 'python_implementation': 'CPython',
               'python_executable': deepcopy(pin), 'python_library': deepcopy(pin), 'python_include': '/synthetic/include',
               'headers': C.content_rows([row('include/Python.h')]), 'abi': {k: 'synthetic' for k in ('SOABI', 'EXT_SUFFIX', 'MULTIARCH', 'Py_GIL_DISABLED', 'Py_DEBUG', 'ABIFLAGS', 'SIZEOF_VOID_P', 'HOST_GNU_TYPE', 'BUILD_GNU_TYPE', 'CC', 'LDSHARED')},
               'platform': 'synthetic-platform', 'machine': 'synthetic-machine', 'libc': ['synthetic', '1'],
               'image_os': 'synthetic-image', 'image_version': 'synthetic-version',
               'maturin_prefix': '/synthetic/venv', 'maturin_files': C.content_rows([row('package/__init__.py')]),
               'link_inputs': [deepcopy(pin)], 'runtime_files': [deepcopy(pin)]}
    context['abi']['SIZEOF_VOID_P'] = 8
    prepared = {'schema': C.SCHEMA, 'source_commit': 'a'*40, 'source': deepcopy(source),
                'context': context, 'key': C.cache_key(source, context), 'fresh_wheel_output_checked': True}
    producer = {'source_commit': 'b'*40, 'run_id': 1, 'attempt': 1,
                'build_record_sha256': 'd'*64, 'wheel_sha256': 'e'*64}
    manifest = deepcopy(C.seal_manifest(prepared, source, release, producer))
    return SimpleNamespace(C=C, source=source, release=release, context=context,
                           prepared=prepared, manifest=manifest, row=row)


def release_cache_plan(case, **changes):
    options = {'primary_key': case.prepared['key'], 'matched_key': case.prepared['key'], 'exact_hit': True}
    options.update(changes)
    return case.C.admission_plan(case.prepared, case.manifest, case.source, case.release, **options)


def test_release_cache_import_does_not_probe_or_write(monkeypatch):
    import os
    import subprocess
    import sysconfig
    def forbidden(*args, **kwargs): raise AssertionError('import performed an operation')
    monkeypatch.setattr(subprocess, 'Popen', forbidden)
    monkeypatch.setattr(os, 'utime', forbidden)
    monkeypatch.setattr(sysconfig, 'get_config_var', forbidden)
    path = SCRIPT.with_name('native_release_cache.py')
    spec = importlib.util.spec_from_file_location('cache_import_quiet', path)
    spec.loader.exec_module(importlib.util.module_from_spec(spec))


def test_release_cache_content_identity_ignores_only_timestamps(release_cache_case):
    c = release_cache_case
    later = deepcopy(c.source)
    for row in later: row['mtime_ns'] += 1000
    assert c.C.cache_key(later, c.context) == c.prepared['key']
    # Producer commit differs from current whole source: equal native content is reusable.
    assert c.manifest['producer']['source_commit'] != c.prepared['source_commit']
    assert release_cache_plan(c) == [(r['path'], r['mtime_ns']) for r in c.source]


@pytest.mark.parametrize('change', ['byte', 'mode', 'added', 'removed', 'path', 'order', 'duplicate'])
def test_release_cache_source_change_denies_admission(release_cache_case, change):
    c = release_cache_case
    if change == 'byte': c.source[0]['sha256'] = 'f'*64
    elif change == 'mode': c.source[0]['mode'] = 0o755
    elif change == 'added': c.source.append(c.row('chronicler-agents/z.rs'))
    elif change == 'removed': c.source.pop()
    elif change == 'path': c.source[0]['path'] = 'chronicler-agents/changed.rs'
    elif change == 'order': c.source.reverse()
    else: c.source.append(deepcopy(c.source[-1]))
    with pytest.raises(c.C.Unsupported): release_cache_plan(c)


@pytest.mark.parametrize('field', ['helper_sha256', 'abi', 'rustc', 'linker', 'platform'])
def test_release_cache_context_changes_key_and_refuses_old_manifest(release_cache_case, field):
    c = release_cache_case
    changed = deepcopy(c.context)
    if field == 'abi': changed['abi']['SOABI'] = 'changed'
    else: changed[field] = 'f'*64 if field == 'helper_sha256' else 'changed'
    assert c.C.cache_key(c.source, changed) != c.prepared['key']
    c.prepared['context'] = changed; c.prepared['key'] = c.C.cache_key(c.source, changed)
    with pytest.raises(c.C.Unsupported): release_cache_plan(c)


@pytest.mark.parametrize('options', [{'exact_hit': False}, {'exact_hit': 'true'}, {'matched_key': 'prefix-elsewhere'}, {'matched_key': ''}, {'primary_key': 'old-format'}])
def test_release_cache_miss_prefix_and_old_format_never_restore(release_cache_case, options):
    c = release_cache_case
    with pytest.raises(c.C.Unsupported): release_cache_plan(c, **options)


@pytest.mark.parametrize('change', ['schema', 'extra', 'missing', 'inventory_byte', 'inventory_mode', 'inventory_added', 'inventory_removed', 'inventory_mtime', 'chronology', 'bool_stamp', 'outside_alias'])
def test_release_cache_closed_manifest_and_inventory(release_cache_case, change):
    c = release_cache_case
    if change == 'schema': c.manifest['schema'] = True
    elif change == 'extra': c.manifest['unclosed'] = 1
    elif change == 'missing': del c.manifest['producer']
    elif change == 'inventory_byte': c.release[-1]['sha256'] = 'f'*64
    elif change == 'inventory_mode': c.release[-1]['mode'] = 0o755
    elif change == 'inventory_added': c.release.append(c.row(c.C.RELEASE+'/z', 100))
    elif change == 'inventory_removed': c.release.pop()
    elif change == 'inventory_mtime': c.release[-1]['mtime_ns'] += 1
    elif change == 'chronology': c.manifest['source'][0]['mtime_ns'] = 101
    elif change == 'bool_stamp': c.manifest['source'][0]['mtime_ns'] = True
    else: c.release[-1]['links'] = 2
    with pytest.raises(c.C.Unsupported): release_cache_plan(c)


def test_release_cache_complete_internal_hardlinks_are_supported(release_cache_case):
    c = release_cache_case
    c.release.append(c.row(c.C.RELEASE+'/z-alias', 100))
    first, alias = c.release[1], c.release[2]
    first['links'] = alias['links'] = 2; alias['inode_group'] = first['path']
    c.manifest = deepcopy(c.C.seal_manifest(c.prepared, c.source, c.release, c.manifest['producer']))
    assert len(release_cache_plan(c)) == 2
    alias['links'] = 3
    with pytest.raises(c.C.Unsupported): release_cache_plan(c)


@pytest.mark.parametrize('name', ['RUSTFLAGS', 'CARGO_ENCODED_RUSTFLAGS', 'PYO3_CONFIG_FILE', 'CC', 'CARGO_TARGET_DIR', 'MATURIN_PEP517_ARGS', 'PYTHONPATH'])
def test_release_cache_unknown_semantic_inputs_fall_back(release_cache_api, name):
    with pytest.raises(release_cache_api.Unsupported): release_cache_api.public_environment({name: 'unknown'})


def test_release_cache_credential_values_are_never_accessed(release_cache_api):
    # An actual detached dict is required; use a value that refuses conversion.
    class Secret:
        def __str__(self): raise AssertionError('credential converted')
    result = release_cache_api.public_environment({'CARGO_REGISTRIES_CRATES_IO_TOKEN': Secret(),
                                                   'PASSWORD': Secret(), 'CARGO_INCREMENTAL': '0'})
    assert result == {'CARGO_INCREMENTAL': '0'}
    assert b'TOKEN' not in release_cache_api.canonical(result)


@pytest.mark.parametrize('value', [b'{"x":1,"x":2}', b'NaN', b'\xff'])
def test_release_cache_malformed_or_duplicate_json(release_cache_api, value):
    with pytest.raises(release_cache_api.Unsupported): release_cache_api.parse_json(value)


def test_release_cache_oversized_metadata_refuses_before_parse(release_cache_api, monkeypatch):
    C = release_cache_api
    monkeypatch.setattr(C, 'MAX_JSON', 8)
    with pytest.raises(C.Unsupported): C.parse_json(b' ' * 9)
    with pytest.raises(C.Unsupported): C.canonical({'field': 'long'})


@pytest.mark.parametrize('path', ['../x', '/x', 'a//b', 'a/./b', 'a\\b', 'a/../b', 'a\x00b'])
def test_release_cache_paths_are_closed(release_cache_api, path):
    with pytest.raises(release_cache_api.Unsupported): release_cache_api.path_name(path)


def test_release_cache_precheck_failure_writes_zero_timestamps(release_cache_case):
    c = release_cache_case; calls = []
    fs = SimpleNamespace(set_mtime=lambda *args: calls.append(args))
    changed = deepcopy(c.source); changed[0]['sha256'] = 'f'*64
    with pytest.raises(c.C.SourceDrift):
        c.C.apply_plan(fs, release_cache_plan(c), c.source, lambda: changed)
    assert calls == []


def test_release_cache_restores_exact_producer_timestamps(release_cache_case):
    c = release_cache_case; current = deepcopy(c.source); calls = []
    for row in current: row['mtime_ns'] = 500
    def set_stamp(name, stamp):
        calls.append((name, stamp))
        next(r for r in current if r['path'] == name)['mtime_ns'] = stamp
    c.C.apply_plan(SimpleNamespace(set_mtime=set_stamp), release_cache_plan(c), c.source, lambda: deepcopy(current))
    assert calls == [(r['path'], r['mtime_ns']) for r in c.source]


@pytest.mark.parametrize('failure', ['midwrite', 'precision', 'postwrite_drift'])
def test_release_cache_partial_write_or_postcheck_is_fatal(release_cache_case, failure):
    c = release_cache_case; current = deepcopy(c.source); calls = []
    def write(name, stamp):
        calls.append(name)
        if failure == 'midwrite' and len(calls) == 2: raise OSError('synthetic partial write')
        row = next(r for r in current if r['path'] == name)
        row['mtime_ns'] = stamp+1 if failure == 'precision' else stamp
        if failure == 'postwrite_drift': row['sha256'] = 'f'*64
    with pytest.raises(c.C.TimestampFailure):
        c.C.apply_plan(SimpleNamespace(set_mtime=write), release_cache_plan(c), c.source, lambda: deepcopy(current))
    assert calls  # This fatal result must never become ordinary-build fallback.


def test_release_cache_prepare_requires_fresh_wheel_output(release_cache_case, monkeypatch):
    c = release_cache_case; calls = []
    def wheel_not_empty():
        calls.append('wheel')
        raise c.C.Unsupported('fresh empty wheel output required')
    monkeypatch.setattr(c.C, 'source_snapshot', lambda *args: deepcopy(c.source))
    fs = SimpleNamespace(wheel_empty=wheel_not_empty)
    with pytest.raises(c.C.Unsupported, match='fresh empty'):
        c.C.prepare(fs, None, {}, context_provider=lambda *args: c.context)
    assert calls == ['wheel']


def test_release_cache_drift_during_build_cannot_seal(release_cache_case):
    c = release_cache_case
    changed = deepcopy(c.source); changed[0]['sha256'] = 'f'*64
    with pytest.raises(c.C.Unsupported, match='source drift'):
        c.C.seal_manifest(c.prepared, changed, c.release, c.manifest['producer'])



@pytest.mark.parametrize('name', ['Cargo.lock', 'Cargo.toml', 'build.rs', 'pyproject.toml', 'src/lib.rs'])
def test_release_cache_every_native_input_changes_content_key(release_cache_case, name):
    c = release_cache_case
    rows = [c.row('chronicler-agents/'+name)]
    before = c.C.cache_key(rows, c.context)
    rows[0]['sha256'] = 'f'*64
    assert c.C.cache_key(rows, c.context) != before


def test_release_cache_source_git_mode_and_path_dependency_closure(release_cache_api, tmp_path):
    C = release_cache_api
    crate = tmp_path/'chronicler-agents'; crate.mkdir()
    (crate/'Cargo.toml').write_text('[package]\nname="fixture"\nversion="0.1.0"\n[dependencies]\nx={path="../external"}\n')
    (crate/'Cargo.toml').chmod(0o644)
    raw = (crate/'Cargo.toml').read_bytes()
    blob = C.hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\x00'+raw).hexdigest()
    tools = SimpleNamespace(run=lambda argv: '100644 blob '+blob+'\tchronicler-agents/Cargo.toml')
    with pytest.raises(C.Unsupported, match='nonregistry'):
        C.source_snapshot(C.LocalFS(tmp_path), tools)
    tools.run = lambda argv: '100755 blob '+blob+'\tchronicler-agents/Cargo.toml'
    with pytest.raises(C.Unsupported, match='unsupported tracked'):
        C.source_snapshot(C.LocalFS(tmp_path), tools)


def test_release_cache_prepared_context_has_no_import_time_defaults(release_cache_api):
    import ast
    tree = ast.parse(Path(release_cache_api.__file__).read_text())
    probes = {'Popen', 'utime', 'get_config_var', 'version', 'run'}
    top_calls = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.ClassDef, ast.If)): continue
        top_calls.extend(n for n in ast.walk(node) if isinstance(n, ast.Call))
    assert not any(isinstance(n.func, ast.Attribute) and n.func.attr in probes for n in top_calls)


@pytest.mark.parametrize('change', ['extra', 'missing', 'feature', 'schema_bool'])
def test_release_cache_unknown_context_schema_refuses(release_cache_case, change):
    c = release_cache_case; context = deepcopy(c.context)
    if change == 'extra': context['unclosed_input'] = 'ignored?'
    elif change == 'missing': del context['abi']['SOABI']
    elif change == 'feature': context['features'] = ['jemalloc']
    else: context['schema'] = True
    with pytest.raises(c.C.Unsupported): c.C.cache_key(c.source, context)


def test_release_cache_fresh_wheel_precondition_cannot_be_omitted(release_cache_case):
    c = release_cache_case
    c.prepared['fresh_wheel_output_checked'] = False
    with pytest.raises(c.C.Unsupported, match='fresh wheel'):
        release_cache_plan(c)


# Coherent cache repair contracts. All earlier bytes/cases remain unchanged.
@pytest.mark.parametrize('command', ['admit', 'seal'])
@pytest.mark.parametrize('failure', ['changed_blob', 'mode', 'missing', 'unreadable'])
def test_release_cache_main_prepared_snapshot_refusal_is_fatal(release_cache_case, monkeypatch, command, failure):
    c = release_cache_case; C = c.C; calls = []
    prepared_raw = C.canonical(c.prepared)
    def forbidden(operation):
        calls.append('FORBIDDEN '+operation)
        raise AssertionError('post-prepare refusal reached '+operation)
    class NoOutputPath(type(Path())):
        def open(self, *args, **kwargs): return forbidden('CLI output write')
    class FakeFS:
        root = Path('/synthetic/source')
        def named_rows(self, names, count, size):
            calls.append('native physical rows')
            assert names == [r['path'] for r in c.source]
            assert (count, size) == (C.MAX_SOURCE_FILES, C.MAX_SOURCE_BYTES)
            if failure == 'missing': raise FileNotFoundError('synthetic tracked file missing')
            if failure == 'unreadable': raise PermissionError('synthetic tracked file unreadable')
            rows = deepcopy(c.source)
            if failure == 'mode': rows[0]['mode'] = 0o755
            return rows
        def read(self, name, limit=None):
            calls.append('native blob bytes')
            assert name == c.source[0]['path'] and failure == 'changed_blob'
            return b'changed tracked bytes'
        def physical(self, *args): return forbidden('layout or build-record access')
        def rows(self, *args): return forbidden('release inventory')
        def wheel_empty(self): return forbidden('wheel access')
        def set_mtime(self, *args): return forbidden('timestamp write')
        def write_exclusive(self, *args): return forbidden('cache seal write')
    fs = FakeFS()
    class FakeTools:
        def run(self, argv):
            calls.append('tracked Git listing')
            assert argv == ['git', '-C', str(fs.root), 'ls-tree', '-r', '--full-tree', 'HEAD', '--', 'chronicler-agents']
            blob = C.hashlib.sha1(b'blob 1\x00x').hexdigest()
            return '\n'.join('100644 blob '+blob+'\t'+r['path'] for r in c.source)
    def metadata(path):
        calls.append('prepared metadata')
        assert str(path) == '/synthetic/prepared.json'
        return prepared_raw
    monkeypatch.setattr(C, 'Path', NoOutputPath)
    monkeypatch.setattr(C, 'LocalFS', lambda root: fs)
    monkeypatch.setattr(C, 'LocalTools', FakeTools)
    monkeypatch.setattr(C, 'read_metadata', metadata)
    monkeypatch.setattr(C, 'assert_source', lambda *args: forbidden('row assertion after refused snapshot'))
    monkeypatch.setattr(C, 'context_record', lambda *args: forbidden('context probe'))
    monkeypatch.setattr(C, 'admission_plan', lambda *args, **kwargs: forbidden('admission'))
    monkeypatch.setattr(C, 'seal_manifest', lambda *args: forbidden('manifest seal'))
    monkeypatch.setattr(C, 'canonical', lambda *args: forbidden('result serialization'))
    with pytest.raises(C.SourceDrift, match='could not be revalidated') as caught:
        C.main([command, '--root', '/synthetic/source', '--prepared', '/synthetic/prepared.json',
                '--output', '/synthetic/result.json', '--github-output', '/synthetic/github-output',
                '--build-record', '/synthetic/source/ci-native-wheel/build.json'])
    cause = C.Unsupported if failure in ('changed_blob', 'mode') else OSError
    assert isinstance(caught.value.__cause__, cause)
    assert calls == ['prepared metadata', 'tracked Git listing', 'native physical rows'] + (
        ['native blob bytes'] if failure == 'changed_blob' else [])


@pytest.mark.parametrize('failure', ['unsupported', 'oserror'])
def test_release_cache_main_admit_prewrite_snapshot_refusal_is_fatal(release_cache_case, monkeypatch, failure):
    c = release_cache_case; C = c.C; calls = []
    prepared_raw = C.canonical(c.prepared); manifest_raw = C.canonical(c.manifest)
    def forbidden(operation):
        calls.append('FORBIDDEN '+operation)
        raise AssertionError('pre-write refusal reached '+operation)
    class NoOutputPath(type(Path())):
        def open(self, *args, **kwargs): return forbidden('CLI output write')
    class FakeFS:
        root = Path('/synthetic/source')
        def wheel_empty(self): calls.append('fresh wheel check')
        def read(self, name, limit):
            assert (name, limit) == (C.MANIFEST, C.MAX_JSON)
            calls.append('manifest read'); return manifest_raw
        def rows(self, *args):
            assert args == (C.RELEASE, C.MAX_RELEASE_FILES, C.MAX_RELEASE_BYTES)
            calls.append('release inventory'); return deepcopy(c.release)
        def set_mtime(self, *args): return forbidden('timestamp write')
        def write_exclusive(self, *args): return forbidden('cache seal write')
    def snapshot(*args):
        calls.append('source snapshot')
        if calls.count('source snapshot') == 1: return deepcopy(c.source)
        error = C.Unsupported if failure == 'unsupported' else OSError
        raise error('synthetic second physical snapshot refused')
    def metadata(path):
        assert str(path) == '/synthetic/prepared.json'
        calls.append('prepared metadata'); return prepared_raw
    def context(*args):
        calls.append('context'); return c.context
    monkeypatch.setattr(C, 'Path', NoOutputPath)
    monkeypatch.setattr(C, 'LocalFS', lambda root: FakeFS())
    monkeypatch.setattr(C, 'LocalTools', lambda: SimpleNamespace(run=lambda *args: forbidden('tool probe')))
    monkeypatch.setattr(C, 'read_metadata', metadata)
    monkeypatch.setattr(C, 'source_snapshot', snapshot)
    monkeypatch.setattr(C, 'public_environment', lambda environment: {})
    monkeypatch.setattr(C, 'context_record', context)
    with pytest.raises(C.SourceDrift, match='could not be revalidated'):
        C.main(['admit', '--root', '/synthetic/source', '--prepared', '/synthetic/prepared.json',
                '--output', '/synthetic/result.json', '--github-output', '/synthetic/github-output',
                '--matched-key', c.prepared['key'], '--exact-hit', 'true'])
    assert calls == ['prepared metadata', 'source snapshot', 'context', 'fresh wheel check',
                     'manifest read', 'release inventory', 'source snapshot']


@pytest.mark.parametrize('failure', ['unsupported', 'oserror'])
def test_release_cache_main_initial_prepare_refusal_keeps_ordinary_path(release_cache_api, monkeypatch, tmp_path, failure):
    C = release_cache_api; calls = []
    def initial(*args):
        calls.append('initial preparation')
        error = C.Unsupported if failure == 'unsupported' else OSError
        raise error('synthetic initially unsupported source')
    def forbidden(*args): raise AssertionError('initial fallback performed FS/tool operation')
    monkeypatch.setattr(C, 'LocalFS', lambda root: SimpleNamespace(set_mtime=forbidden, write_exclusive=forbidden))
    monkeypatch.setattr(C, 'LocalTools', lambda: SimpleNamespace(run=forbidden))
    monkeypatch.setattr(C, 'prepare', initial)
    prepared = tmp_path/'uncreated-prepared.json'; output = tmp_path/'ordinary.json'
    github_output = tmp_path/'github-output'
    result = C.main(['prepare', '--root', str(tmp_path), '--prepared', str(prepared),
                     '--output', str(output), '--github-output', str(github_output)])
    expected = {'state': 'ORDINARY_BUILD', 'reason': 'Unsupported' if failure == 'unsupported' else 'OSError'}
    assert result == expected and json.loads(output.read_bytes()) == expected
    assert github_output.read_text() == 'eligible=false\n' and not prepared.exists()
    assert calls == ['initial preparation']


@pytest.mark.parametrize('names', [('COMPILER_PATH',), ('GCC_EXEC_PREFIX',), ('COMPILER_PATH', 'GCC_EXEC_PREFIX')])
def test_release_cache_backend_selector_names_refuse_before_value_handling(release_cache_api, names):
    C = release_cache_api
    class OpaqueValue:
        def __str__(self): raise AssertionError('unsupported value converted')
        def __repr__(self): raise AssertionError('unsupported value represented')
        def encode(self, *args): raise AssertionError('unsupported value encoded')
        def __reduce_ex__(self, *args): raise AssertionError('unsupported value copied')
    # Even the admitted public name has an opaque value: all names must pass
    # before the value-selection/validation comprehension is reached.
    environment = {'CARGO_INCREMENTAL': OpaqueValue()}
    environment.update({name: OpaqueValue() for name in names})
    with pytest.raises(C.Unsupported, match='unsupported semantic environment'):
        C.public_environment(environment)


def test_release_cache_backend_refusal_preserves_supported_context_admission(release_cache_case):
    c = release_cache_case; C = c.C
    assert C.public_environment({}) == {} and C.cache_key(c.source, c.context) == c.prepared['key']
    public = {'CARGO_INCREMENTAL': '0', 'CARGO_TERM_COLOR': 'always', 'PYTHONUNBUFFERED': '1'}
    context = deepcopy(c.context); context['public_env'] = C.public_environment(public)
    prepared = deepcopy(c.prepared); prepared['context'] = context; prepared['key'] = C.cache_key(c.source, context)
    manifest = C.seal_manifest(prepared, c.source, c.release, c.manifest['producer'])
    assert context['public_env'] == public
    assert C.admission_plan(prepared, manifest, c.source, c.release,
                            primary_key=prepared['key'], matched_key=prepared['key'], exact_hit=True) == [
        (r['path'], r['mtime_ns']) for r in c.source]
